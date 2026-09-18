import json
import time
from .base import (
    BaseAiProvider, post_with_retry, get_with_retry, DEFAULT_MAX_TOKENS,
    extract_openai_style_usage, format_http_error, format_request_exception,
    requests, HTTPError, RequestException,
)
from ..model_selector import filter_chat_model_ids


def list_models(api_key=None):
    """Fetches the live model catalog from OpenRouter's public /api/v1/models
    endpoint. No auth required, but an API key (if provided) is sent anyway
    in case it unlocks account-specific models."""
    try:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        response = get_with_retry(
            "https://openrouter.ai/api/v1/models",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        ids = [m.get("id", "") for m in data.get("data", [])]
        return {"success": True, "models": filter_chat_model_ids(ids)}
    except HTTPError as e:
        return {"error": format_http_error("OpenRouter models list failed", e)}
    except Exception as e:
        return {"error": format_request_exception("OpenRouter models list request failed", e)}

FALLBACK_MODELS = [
    # Auto-router: OpenRouter itself picks a currently-free model. Listed first because
    # it self-heals against exactly the kind of deprecation churn that has broken this
    # list three times already — verified against the live /api/v1/models catalog.
    "openrouter/free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-20b:free",
]

RATE_LIMIT_WAIT_SECONDS = 30
MAX_FULL_CYCLES = 3

def _short_name(model_id):
    return model_id.split("/", 1)[-1].split(":", 1)[0]


def _apply_anthropic_cache_control(messages, model_id):
    """Marks the system prompt with an Anthropic cache_control breakpoint,
    the same mechanism agent/providers/claude.py's native client already
    uses -- OpenRouter documents passing this field through unmodified to
    the underlying Anthropic API for anthropic/* models specifically. The
    system prompt and tool schemas are near-identical across every iteration
    of a tool-calling turn (often 5-20+ requests), so this should let
    Anthropic serve iterations 2+ from cache instead of reprocessing the
    ~3,000-4,000 token system prompt on every single request.

    2026-09-19 cost/performance pass: confirmed against OpenRouter's own docs
    (openrouter.ai/docs/features/prompt-caching, fetched 2026-09-18, not
    assumed) that this per-block placement is real and that cached/written
    token counts come back for anthropic/* models in the same
    usage.prompt_tokens_details shape as every other OpenAI-compatible
    provider here -- meaning base.extract_openai_style_usage's existing
    cached_tokens extraction already surfaces OpenRouter+Anthropic cache
    hits with no further code change needed. Still not confirmed against a
    LIVE response in this sandbox (no network access) -- see docs/
    IMPLEMENTATION_TRACKER.md for the open item to verify usage.
    prompt_tokens_details.cached_tokens > 0 on a real second-iteration call
    once a live OpenRouter+anthropic/* key is available.

    No-op for every other model, including the default free-tier
    FALLBACK_MODELS chain, none of which are anthropic/*."""
    if not model_id.startswith("anthropic/"):
        return messages
    marked = []
    system_marked = False
    for msg in messages:
        if not system_marked and msg.get("role") == "system" and isinstance(msg.get("content"), str):
            marked.append({
                **msg,
                "content": [{"type": "text", "text": msg["content"], "cache_control": {"type": "ephemeral"}}],
            })
            system_marked = True
        else:
            marked.append(msg)
    return marked

class OpenRouterClient(BaseAiProvider):
    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key, model=None, status_callback=None):
        self.api_key = api_key
        primary = model or FALLBACK_MODELS[0]
        chain = [primary] + [m for m in FALLBACK_MODELS if m != primary]
        self.models = chain
        self.model = primary
        self.current_index = 0
        self.last_status = ""
        self._status_callback = status_callback

    def set_status_callback(self, callback):
        self._status_callback = callback

    def _emit_status(self, text):
        self.last_status = text
        if self._status_callback:
            try:
                self._status_callback(text)
            except Exception:
                pass

    def _post(self, messages, tools, model_id, max_tokens=None):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_id,
            "messages": _apply_anthropic_cache_control(messages, model_id),
            "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
        }
        if tools:
            payload["tools"] = tools
        if model_id.startswith("anthropic/"):
            # Same "robust combination for agent loops" as claude.py's native client: an
            # explicit breakpoint on the static system prefix (_apply_anthropic_cache_control
            # above) plus a top-level cache_control field for automatic caching of the
            # growing messages tail across a multi-iteration tool-calling turn. Confirmed
            # supported for OpenRouter's anthropic/* models specifically (openrouter.ai/docs/
            # features/prompt-caching, fetched 2026-09-18) -- no-op for every other model.
            payload["cache_control"] = {"type": "ephemeral"}
        # A transient 5xx on the CURRENT model gets a short retry here before
        # the outer _request_with_fallback loop gives up on it and moves to
        # the next model in the chain -- retry-then-fallback, not fallback-only.
        return post_with_retry(self.BASE_URL, headers, json.dumps(payload), timeout=60)

    def _request_with_fallback(self, messages, tools, max_tokens=None):
        for cycle in range(MAX_FULL_CYCLES):
            any_rate_limited = False
            for idx, model_id in enumerate(self.models):
                self.current_index = idx
                self.model = model_id
                self._emit_status(f"Using: {_short_name(model_id)}")
                try:
                    response = self._post(messages, tools, model_id, max_tokens=max_tokens)
                    # 429 = rate limited (transient, worth waiting out); 404 = model
                    # retired/renamed/paid-only (permanent, waiting won't help). Both are
                    # reasons to try the next model in the chain rather than fail outright —
                    # free-tier model availability on OpenRouter changes over time.
                    if response.status_code in (429, 404):
                        if response.status_code == 429:
                            any_rate_limited = True
                        reason = "Rate limited" if response.status_code == 429 else "Model unavailable"
                        next_idx = idx + 1
                        if next_idx < len(self.models):
                            self._emit_status(
                                f"{reason}, switching to {_short_name(self.models[next_idx])}..."
                            )
                        continue
                    response.raise_for_status()
                    # API-006, 2026-09-14 audit: response.json() used to be called directly in
                    # the return statement above -- a malformed/non-JSON body (a proxy error
                    # page, a truncated response) raised json.JSONDecodeError here, uncaught by
                    # either except clause below (both only catch requests.exceptions.*), and
                    # propagated all the way out of complete() uncaught. OpenAI/Gemini/Cartogen's
                    # equivalent complete() methods already wrap this same call in a broad
                    # except Exception, so they didn't have this specific gap -- OpenRouter's own
                    # narrower per-clause exception handling here is what needed the explicit fix.
                    try:
                        data = response.json()
                    except ValueError as e:
                        return {"ok": False, "error": f"Response was not valid JSON: {e}", "model": model_id}
                    return {"ok": True, "data": data, "model": model_id}
                except HTTPError as e:
                    return {
                        "ok": False,
                        "error": format_http_error("HTTP error", e),
                        "model": model_id,
                    }
                except RequestException as e:
                    return {"ok": False, "error": format_request_exception("Request failed", e), "model": model_id}

            if not any_rate_limited:
                # Every model in the chain 404'd — none were merely rate-limited, so
                # sleeping and retrying the identical requests would just waste time.
                # Names are listed explicitly so a stale-plugin-reload (still running an
                # old model list) is immediately distinguishable from a genuinely new
                # deprecation wave, instead of both looking like the same static message.
                tried = ", ".join(self.models)
                return {
                    "ok": False,
                    "error": (
                        f"No configured fallback model is currently available on OpenRouter "
                        f"(all returned 404 - retired/renamed/paid-only). Models tried: [{tried}]. "
                        "If this list doesn't match what you expect, the plugin likely needs "
                        "reloading (Plugins -> Plugin Reloader). Otherwise FALLBACK_MODELS in "
                        "openrouter.py needs updating."
                    ),
                }

            self._emit_status(
                f"All models rate limited. Waiting {RATE_LIMIT_WAIT_SECONDS}s before retry..."
            )
            time.sleep(RATE_LIMIT_WAIT_SECONDS)

        return {"ok": False, "error": "All models rate limited after multiple retries"}

    def complete(self, messages, tools=None, max_tokens=None):
        result = self._request_with_fallback(messages, tools, max_tokens=max_tokens)
        if not result["ok"]:
            return {"error": result["error"]}
        try:
            out = {"message": result["data"]["choices"][0]["message"], "model": result["model"]}
            usage = extract_openai_style_usage(result["data"])
            if usage is not None:
                out["usage"] = usage
            return out
        except (KeyError, IndexError, ValueError) as e:
            return {"error": f"Unexpected response format: {e}"}
