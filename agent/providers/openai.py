import json
import requests
from .base import BaseAiProvider, post_with_retry, DEFAULT_MAX_TOKENS, extract_openai_style_usage
from ..model_selector import filter_chat_model_ids
from ._search_cache import TTLCache

_SEARCH_CACHE = TTLCache(ttl_seconds=1800)


def list_models(api_key):
    """Fetches the live model list from OpenAI's /v1/models endpoint."""
    try:
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        ids = [m.get("id", "") for m in data.get("data", [])]
        return {"success": True, "models": filter_chat_model_ids(ids)}
    except requests.exceptions.HTTPError as e:
        return {"error": f"OpenAI models list failed ({e.response.status_code}): {e.response.text}"}
    except Exception as e:
        return {"error": f"OpenAI models list request failed: {e}"}


def grounded_search(api_key, query, model="gpt-5-search-api"):
    """Standalone call to OpenAI's dedicated web-search Chat Completions model
    for real-time, source-cited facts.

    Kept separate from OpenAIClient.complete() (the normal tool-calling loop),
    same reasoning as Gemini's grounded_search(): OpenAI's Chat Completions
    web search only works with a small set of purpose-built search models
    (verified against developers.openai.com/api/docs/guides/tools-web-search
    -- "The Chat Completions API supports only specialized search models for
    web search... These models do not support Responses API web_search
    features"). They don't combine with our custom function-calling tools
    schema, so this plugs into the agent loop as a normal tool result instead,
    exactly like Gemini's standalone grounding call. gpt-5-search-api is the
    current (non-deprecated) Chat Completions search model -- gpt-4o-search-
    preview and gpt-4o-mini-search-preview were both retired 2026-07-23.

    Cached by (query, model) for 30 minutes -- unlike search_web (free
    DuckDuckGo), this is a real, billed LLM API call, so a re-issued or
    near-identical follow-up search within the same turn/session shouldn't
    pay for it twice. Not cached on error, so a transient failure doesn't
    get "stuck" for the TTL window."""
    cache_key = (query.strip().lower(), model)
    cached = _SEARCH_CACHE.get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": query}],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = post_with_retry(url, headers, json.dumps(payload), timeout=30)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return {"error": "OpenAI grounded search returned no choices."}

        message = choices[0].get("message", {}) or {}
        text = message.get("content", "") or ""

        sources = []
        for annotation in message.get("annotations", []) or []:
            citation = annotation.get("url_citation") or {}
            if citation.get("url"):
                sources.append({"title": citation.get("title", ""), "url": citation["url"]})

        result = {"success": True, "text": text, "sources": sources}
        _SEARCH_CACHE.set(cache_key, result)
        return result
    except requests.exceptions.HTTPError as e:
        return {"error": f"OpenAI grounded search failed ({e.response.status_code}): {e.response.text}"}
    except Exception as e:
        return {"error": f"OpenAI grounded search request failed: {e}"}


# gpt-5.2-chat-latest is a self-updating alias (always the current GPT-5.2-tier
# Instant model) -- included for the same reason as Gemini's "-latest" fallback
# and OpenRouter's "openrouter/free": it resists exactly the kind of snapshot-ID
# deprecation churn that has hit this integration before (verified live via
# openai.com's GPT-5.2 announcement). gpt-5-mini is the version-generic small
# tier, confirmed to support Chat Completions + function calling, as a cheap
# last-resort fallback -- gpt-4o-mini was deliberately NOT used here since the
# entire GPT-4o family is being actively retired through 2026.
FALLBACK_MODELS = ["gpt-5.6", "gpt-5.2-chat-latest", "gpt-5-mini"]


class OpenAIClient(BaseAiProvider):
    def __init__(self, api_key, model=None, status_callback=None):
        self.api_key = api_key
        primary = model or FALLBACK_MODELS[0]
        # Whatever model the user actually configured stays first in the chain --
        # fallback only kicks in if THAT one 404s, it never silently overrides a choice.
        self.models = [primary] + [m for m in FALLBACK_MODELS if m != primary]
        self.model = primary
        self._status_callback = status_callback
        self.base_url = "https://api.openai.com/v1/chat/completions"

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
            self._emit_status(f"Using OpenAI: {model_id}")
            try:
                response = self._post(messages, tools, model_id, max_tokens=max_tokens)
                if response.status_code == 404:
                    # Model retired, renamed, or not available on this account --
                    # try the next one in the chain instead of failing outright.
                    next_idx = idx + 1
                    if next_idx < len(self.models):
                        self._emit_status(f"Model unavailable, switching to {self.models[next_idx]}...")
                    continue
                response.raise_for_status()
                data = response.json()
                out = {"message": data["choices"][0]["message"], "model": model_id}
                usage = extract_openai_style_usage(data)
                if usage is not None:
                    out["usage"] = usage
                return out
            except requests.exceptions.HTTPError as e:
                return {"error": f"OpenAI API error ({e.response.status_code}): {e.response.text}"}
            except Exception as e:
                return {"error": f"OpenAI API request failed: {e}"}

        tried = ", ".join(self.models)
        return {
            "error": (
                f"No configured OpenAI model is currently available (all returned 404). "
                f"Models tried: [{tried}]. Open Settings and pick a different model, or "
                "FALLBACK_MODELS in openai.py needs updating."
            )
        }
