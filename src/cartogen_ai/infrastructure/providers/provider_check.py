"""The Settings window's Test button for the key-based providers (PLAN-039), free of Qt so it is testable without QGIS.

It uses the key typed in the field (not necessarily saved) and does two things in order: lists the provider's models (proves the address
works and, for Gemini, that the key is accepted), then asks the chosen model one tiny question (proves the key and the model really work).
The question spends a few tokens of the user's own key. The model-list step alone could not catch a bad OpenRouter key, because that list
is public.

Status: UNVERIFIED against real provider accounts here (no key in the sandbox); error classification is by wording and was checked only
against the project's own error formatters (base.format_http_error / format_request_exception)."""
import re
import time

CHECK_PROMPT = "Reply with the single word: ok"
KEYED = ("openrouter", "gemini")          # a key is required
TESTABLE = ("openrouter", "gemini", "ollama", "cartogen")

_KEY = re.compile(r"\b(401|403)\b|authentication failed|invalid api key|incorrect api key|unauthori[sz]ed", re.I)
_LIMIT = re.compile(r"\b429\b|quota|rate.?limit|too many requests", re.I)
_NETWORK = re.compile(r"could not reach|timed out|timeout|connection|proxy|resolve|is ollama running", re.I)
_MODEL = re.compile(r"\b404\b|model.{0,40}(not found|not available|no longer)|no endpoints found", re.I)

HINTS = {
    "key": "Paste the key again (no spaces) or create a new one.",
    "limit": "The key's rate limit or quota is used up. Try later or check billing for this key.",
    "model": "Pick another model in the box below.",
    "network": "Check your internet connection or proxy.",
}


def classify_error(text):
    """Which part failed, from the error wording: 'key', 'limit', 'network', 'model' or 'other'. Order matters: an authentication failure
    mentions the key before anything else, and a quota message can also contain the word 'model'."""
    text = text or ""
    for stage, pattern in (("key", _KEY), ("limit", _LIMIT), ("network", _NETWORK), ("model", _MODEL)):
        if pattern.search(text):
            return stage
    return "other"


def ollama_chat_url(endpoint):
    """The chat endpoint for an Ollama address as typed in Settings (same normalisation the agent applies)."""
    url = (endpoint or "").strip() or "http://localhost:11434/v1/chat/completions"
    return url if url.endswith("chat/completions") else url.rstrip("/") + "/v1/chat/completions"


def _default_list_fn(provider):
    if provider == "openrouter":
        from .openrouter import list_models
    elif provider == "gemini":
        from .gemini import list_models
    else:
        from .ollama import list_models
    return list_models


def _default_client(provider, key, model):
    if provider == "openrouter":
        from .openrouter import OpenRouterClient
        return OpenRouterClient(api_key=key, model=model)
    if provider == "gemini":
        from .gemini import GeminiClient
        return GeminiClient(api_key=key, model=model or "gemini-flash-latest")
    from .ollama import OllamaClient
    return OllamaClient(endpoint_url=ollama_chat_url(key), model=model or "llama3.1")


def _fail(stage, message, seconds=0.0):
    return {"ok": False, "stage": stage, "message": message, "seconds": seconds, "models": []}


def check_provider(provider, key, model=None, list_fn=None, client_factory=None):
    """{'ok', 'stage', 'message', 'seconds', 'models'}; stage is 'ready' on success, else 'unavailable', 'key', 'limit', 'network', 'model'
    or 'other'. `list_fn(key)` and `client_factory(provider, key, model)` are injectable for tests. Never raises."""
    if provider not in TESTABLE:
        return _fail("other", f"No test is defined for {provider}.")
    if provider == "cartogen":
        return _fail("unavailable", "No hosted gateway is deployed yet, so there is nothing to test.")
    key = (key or "").strip()
    if provider in KEYED and not key:
        return _fail("key", "Enter the API key first.")
    started = time.monotonic()
    try:
        listing = (list_fn or _default_list_fn(provider))(key)
        models = listing.get("models", []) if isinstance(listing, dict) and listing.get("success") else []
        if isinstance(listing, dict) and "error" in listing:
            return _fail(classify_error(listing["error"]), listing["error"], round(time.monotonic() - started, 1))
        if provider == "ollama" and model and models and model not in models:
            return _fail("model", f"The model '{model}' is not on this Ollama server. It has: {', '.join(models[:6])}.", round(time.monotonic() - started, 1))
        client = (client_factory or _default_client)(provider, key, model)
        asked = time.monotonic()
        result = client.complete([{"role": "user", "content": CHECK_PROMPT}], None, max_tokens=8)
    except Exception as e:  # a provider module raising must not break the dialog
        return _fail("other", f"Unexpected error: {type(e).__name__}", round(time.monotonic() - started, 1))
    seconds = round(time.monotonic() - started, 1)
    if "error" in result:
        return _fail(classify_error(result["error"]), result["error"], seconds)
    used = result.get("model") or model or ""
    note = f" (the provider fell back to {used})" if model and used and used != model else ""
    answer = ((result.get("message") or {}).get("content") or "").strip()[:30]
    return {"ok": True, "stage": "ready", "seconds": seconds, "models": models,
            "message": f"Works. {len(models)} models listed; {used or 'the model'} answered in {round(time.monotonic() - asked, 1)} s"
                       f"{' (' + answer + ')' if answer else ''}{note}."}
