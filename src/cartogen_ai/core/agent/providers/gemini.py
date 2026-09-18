import json
from .base import (
    BaseAiProvider, post_with_retry, get_with_retry, DEFAULT_MAX_TOKENS,
    extract_openai_style_usage, format_http_error, format_request_exception,
    requests, HTTPError, RequestException,
)
from ..model_selector import filter_chat_model_ids
from ._search_cache import TTLCache

_SEARCH_CACHE = TTLCache(ttl_seconds=1800)


def list_models(api_key):
    """Fetches the live model list from the Gemini API's ListModels endpoint.
    Model IDs come back as 'models/{id}' and must be stripped to the bare
    name to match what GeminiClient sends as 'model' in its payload. Filtered
    to models that actually support generateContent (chat).

    Authenticates via the x-goog-api-key header rather than a '?key=' query
    parameter -- docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md §2.3 flagged
    this endpoint as the one place in this file still using query-param auth
    while GeminiClient.complete()'s main chat path already used a header;
    query-string credentials are more likely to end up in server access logs,
    proxy logs, or browser history than a header. Confirmed against Google's
    own docs (ai.google.dev/api -- REST reference and quickstart examples)
    that x-goog-api-key is a real, supported header for this exact endpoint,
    not a guess -- still worth exercising via docs/RELEASE_SMOKE_TEST.md's
    Humanitarian Data/provider row before the next release, since this
    sandbox has no live network access to confirm it end-to-end itself."""
    try:
        response = get_with_retry(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": api_key},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        ids = []
        for m in data.get("models", []):
            if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                continue
            name = m.get("name", "")
            ids.append(name.split("/", 1)[-1] if name.startswith("models/") else name)
        return {"success": True, "models": filter_chat_model_ids(ids)}
    except HTTPError as e:
        return {"error": format_http_error("Gemini models list failed", e)}
    except Exception as e:
        return {"error": format_request_exception("Gemini models list request failed", e)}


def grounded_search(api_key, query, model="gemini-flash-latest"):
    """Standalone call to Gemini's native (legacy) generateContent endpoint with
    Google Search grounding enabled, for real-time, source-cited facts.

    Kept separate from GeminiClient.complete() (which talks to the OpenAI-compat
    endpoint) rather than trying to combine grounding with our custom
    function-calling tools in one request: that combination currently requires
    Google's new "Interactions API", which is a Gemini-3-only preview feature
    with an entirely different endpoint and request/response shape (verified
    against ai.google.dev/gemini-api/docs/tool-combination). Standalone
    grounding via this legacy endpoint works across a much broader range of
    Gemini models and plugs cleanly into our existing tool-calling loop as a
    normal tool result instead.

    Cached by (query, model) for 30 minutes -- unlike search_web (free
    DuckDuckGo), this is a real, billed LLM API call, so a re-issued or
    near-identical follow-up search within the same turn/session shouldn't
    pay for it twice. Not cached on error, so a transient failure doesn't
    get "stuck" for the TTL window."""
    cache_key = (query.strip().lower(), model)
    cached = _SEARCH_CACHE.get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": query}]}],
        "tools": [{"google_search": {}}],
    }
    try:
        # See list_models()'s docstring above for why this uses the x-goog-api-key
        # header instead of a '?key=' query param (docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md
        # SS2.3) -- same endpoint family, same reasoning applies here.
        # post_with_retry (not a bare requests.post) -- found via a grep sweep confirming every
        # provider call goes through the shared retry helper (large-request rate-limit
        # resilience, 2026-09-12); this was the one real gap, a standalone call outside the main
        # complete()/_post path that had no retry/backoff at all.
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        response = post_with_retry(url, headers, json.dumps(payload), timeout=30)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return {"error": "Gemini grounded search returned no candidates."}

        parts = candidates[0].get("content", {}).get("parts", []) or []
        text = "".join(p.get("text", "") for p in parts)

        grounding = candidates[0].get("groundingMetadata", {}) or {}
        sources = []
        for chunk in grounding.get("groundingChunks", []) or []:
            web = chunk.get("web", {}) or {}
            if web.get("uri"):
                sources.append({"title": web.get("title", ""), "url": web["uri"]})

        result = {"success": True, "text": text, "sources": sources}
        _SEARCH_CACHE.set(cache_key, result)
        return result
    except HTTPError as e:
        return {"error": format_http_error("Gemini grounded search failed", e)}
    except Exception as e:
        return {"error": format_request_exception("Gemini grounded search request failed", e)}


# "-latest" is a self-updating alias on Google's side, so it resists exactly the
# kind of snapshot-ID deprecation that broke this integration before: a live user
# hit a 404 "no longer available to new users" on gemini-2.5-pro even though
# Google's own docs still listed it as stable at the time -- Google appears to
# gate specific model IDs off for newer accounts ahead of removing them from
# docs. Concrete IDs below are the last-verified-live fallback if the alias
# itself ever breaks (checked against ai.google.dev/gemini-api/docs/models).
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-3.6-flash", "gemini-2.5-flash"]


class GeminiClient(BaseAiProvider):
    def __init__(self, api_key, model="gemini-flash-latest", status_callback=None):
        self.api_key = api_key
        primary = model or FALLBACK_MODELS[0]
        # Whatever model the user actually configured stays first in the chain --
        # fallback only kicks in if THAT one 404s, it never silently overrides a choice.
        self.models = [primary] + [m for m in FALLBACK_MODELS if m != primary]
        self.model = primary
        self._status_callback = status_callback
        # Using Gemini's OpenAI compatibility endpoint natively supports our tools schema
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    def set_status_callback(self, callback):
        self._status_callback = callback

    def _emit_status(self, text):
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
        payload = {"model": model_id, "messages": messages, "max_tokens": max_tokens or DEFAULT_MAX_TOKENS}
        if tools:
            payload["tools"] = tools
        return post_with_retry(self.base_url, headers, json.dumps(payload), timeout=60)

    def complete(self, messages, tools=None, max_tokens=None):
        for idx, model_id in enumerate(self.models):
            self.model = model_id
            self._emit_status(f"Using Gemini: {model_id}")
            try:
                response = self._post(messages, tools, model_id, max_tokens=max_tokens)
                if response.status_code == 404:
                    # Model retired, renamed, or gated off this account -- try the next
                    # one in the chain instead of failing outright on a single bad ID.
                    next_idx = idx + 1
                    if next_idx < len(self.models):
                        self._emit_status(f"Model unavailable, switching to {self.models[next_idx]}...")
                    continue
                response.raise_for_status()
                data = response.json()
                out = {"message": data["choices"][0]["message"], "model": model_id}
                # GeminiClient.complete() goes through Google's OpenAI-compatibility
                # endpoint (self.base_url above), confirmed by the URL path
                # ('/v1beta/openai/chat/completions') -- so its 'usage' object is
                # OpenAI-shaped too, same extraction as OpenRouter/OpenAI/Ollama.
                # grounded_search() below uses the native generateContent endpoint
                # instead, which reports usage under 'usageMetadata' -- a different
                # shape not covered by this call site.
                usage = extract_openai_style_usage(data)
                if usage is not None:
                    out["usage"] = usage
                return out
            except HTTPError as e:
                return {"error": format_http_error("Gemini API error", e)}
            except Exception as e:
                return {"error": format_request_exception("Gemini API request failed", e)}

        tried = ", ".join(self.models)
        return {
            "error": (
                f"No configured Gemini model is currently available (all returned 404). "
                f"Models tried: [{tried}]. Open Settings and pick a different Gemini model, "
                "or FALLBACK_MODELS in gemini.py needs updating."
            )
        }
