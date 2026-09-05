import time
from abc import ABC, abstractmethod

import requests

# Status codes worth retrying: 429 (rate limited) and the common transient
# 5xx server errors. Anything else (400/401/403/404/etc.) is a real client-side
# or permanent problem that retrying won't fix.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_SECONDS = 1.5

# Only claude.py previously capped output size (its own local DEFAULT_MAX_TOKENS,
# same value, left as-is there rather than migrated here for no functional
# reason). Every other raw-requests client sent no max_tokens at all -- rarely
# an issue since tool-calling responses are typically short, but a real, if
# uncommon, runaway-output cost risk with nothing stopping a degenerate
# response from running to whatever the provider's own default cap is (often
# much higher than this plugin ever needs). Shared here so OpenAI/Gemini/
# OpenRouter/Ollama's clients standardize on the same value instead of each
# picking their own.
DEFAULT_MAX_TOKENS = 8096


def post_with_retry(url, headers, payload_json, timeout, max_retries=DEFAULT_MAX_RETRIES):
    """Shared HTTP POST for every provider's raw requests-based client. A single
    transient network hiccup or 429/5xx used to kill the whole agent turn with
    no retry at all -- this gives every provider (except OpenRouter/Gemini,
    which already have their own multi-model fallback loop as an outer layer)
    a short exponential backoff before giving up. Returns the final
    requests.Response; the caller still calls .raise_for_status() as before,
    so this is a drop-in replacement for a bare requests.post(...) call."""
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, headers=headers, data=payload_json, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(DEFAULT_BACKOFF_SECONDS * (attempt + 1))
                continue
            raise
        if response.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
            time.sleep(DEFAULT_BACKOFF_SECONDS * (attempt + 1))
            continue
        return response
    raise last_exc


def extract_openai_style_usage(data):
    """Normalizes the OpenAI-Chat-Completions-shaped 'usage' object
    ({'prompt_tokens', 'completion_tokens', ...}) that OpenRouter, OpenAI, and
    Ollama's OpenAI-compatible endpoint all return into this plugin's common
    {'input_tokens', 'output_tokens'} shape (matching Anthropic's native naming,
    picked as the common form since ui/dock_widget.py only ever needs the two
    numbers, not the provider-specific field names). Returns None -- not a
    dict of zeros -- when the response has no 'usage' object at all, so a
    provider/model that doesn't report usage is honestly reported as unknown
    rather than fabricated as zero cost. See
    docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md SS3.2 ("no cost/usage
    visibility in the UI") -- this is the shared extraction point every
    OpenAI-compatible client's complete() calls."""
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    if input_tokens is None and output_tokens is None:
        return None
    return {"input_tokens": input_tokens or 0, "output_tokens": output_tokens or 0}


class BaseAiProvider(ABC):
    @abstractmethod
    def complete(self, messages, tools=None, max_tokens=None):
        pass

    def set_status_callback(self, callback):
        self._status_callback = callback
