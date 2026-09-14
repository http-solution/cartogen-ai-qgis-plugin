import time
from abc import ABC, abstractmethod

import requests

# Status codes worth retrying: 429 (rate limited) and the common transient
# 5xx server errors. Anything else (400/401/403/404/etc.) is a real client-side
# or permanent problem that retrying won't fix.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_SECONDS = 1.5

# 429 gets its own, longer retry budget, separate from DEFAULT_MAX_RETRIES/
# DEFAULT_BACKOFF_SECONDS above -- a rate limit means an actual per-minute quota window has to
# clear, not a one-off network blip, so the short generic backoff (at most ~4.5s total) usually
# isn't enough. 10s/20s/30s gives roughly a minute of patience, on the same order as
# openrouter.py's own RATE_LIMIT_WAIT_SECONDS=30 sustained-wait loop -- OpenRouter's client
# already had real rate-limit resilience (a model-fallback chain plus that wait-and-retry loop);
# Claude/OpenAI/Gemini/Ollama only ever had the short generic path below, confirmed via grep, so
# this is the concrete gap that let a sustained rate limit kill an otherwise-fine multi-tool-call
# task on 4 of 5 providers. A normal, non-rate-limited request never touches this -- only 429
# responses reach it, and other retryable statuses (5xx) keep using the original short budget.
RATE_LIMIT_BACKOFF_SECONDS = 10
RATE_LIMIT_MAX_RETRIES = 3

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


def _request_with_retry(send, timeout, max_retries):
    """Shared retry loop behind post_with_retry/get_with_retry -- `send` is a zero-arg
    callable that performs the actual requests.post/requests.get call. A single transient
    network hiccup or 429/5xx used to kill the whole agent turn with no retry at all -- this
    gives every provider (except OpenRouter, which already has its own multi-model fallback
    loop as an outer layer) a short exponential backoff before giving up, PLUS a separate,
    longer budget specifically for 429 (see RATE_LIMIT_BACKOFF_SECONDS/RATE_LIMIT_MAX_RETRIES
    above -- large multi-tool-call tasks, 2026-09-12). Returns the final requests.Response;
    the caller still calls .raise_for_status() as before."""
    last_exc = None
    # The loop bound has to fit whichever retry budget is larger -- 429 may need more
    # attempts than a plain 5xx/network blip does.
    total_attempts = max(max_retries, RATE_LIMIT_MAX_RETRIES) + 1
    for attempt in range(total_attempts):
        try:
            response = send()
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(DEFAULT_BACKOFF_SECONDS * (attempt + 1))
                continue
            raise
        if response.status_code == 429:
            if attempt < RATE_LIMIT_MAX_RETRIES:
                time.sleep(RATE_LIMIT_BACKOFF_SECONDS * (attempt + 1))
                continue
            return response
        if response.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
            time.sleep(DEFAULT_BACKOFF_SECONDS * (attempt + 1))
            continue
        return response
    raise last_exc


def post_with_retry(url, headers, payload_json, timeout, max_retries=DEFAULT_MAX_RETRIES):
    """Shared HTTP POST for every provider's raw requests-based client -- see
    _request_with_retry for the retry behavior. Drop-in replacement for a bare
    requests.post(...) call."""
    return _request_with_retry(
        lambda: requests.post(url, headers=headers, data=payload_json, timeout=timeout),
        timeout, max_retries,
    )


def get_with_retry(url, headers, timeout, max_retries=DEFAULT_MAX_RETRIES):
    """API-002, 2026-09-14 audit: every provider's list_models() used a bare requests.get(...)
    with no retry at all -- unlike the chat-completion path, which has had post_with_retry's
    resilience since 2026-09-12. A transient network hiccup or a 429 while just listing models
    (e.g. populating the settings dialog's model dropdown) used to fail outright with no retry,
    inconsistent with every other HTTP call this codebase makes. Same retry/backoff behavior as
    post_with_retry, just for GET -- drop-in replacement for a bare requests.get(...) call."""
    return _request_with_retry(
        lambda: requests.get(url, headers=headers, timeout=timeout),
        timeout, max_retries,
    )


def format_http_error(prefix, e):
    """Formats a requests.exceptions.HTTPError into a user-facing error string, shared by
    every provider client's list_models/grounded_search/chat-completion error paths.

    API-005, 2026-09-13 audit: every provider surfaced e.response.text -- the raw HTTP error
    body -- unfiltered into chat/conversation history. Several providers' own 401/403 error
    messages echo back a masked/partial copy of the invalid key that was actually sent (e.g.
    OpenAI's real format: "Incorrect API key provided: sk-ab***...yz. You can find your API
    key at..."), which would otherwise sit in plain view in the chat log, get resent to the
    model as part of conversation history on a later turn, and could end up in an exported
    chat transcript. Redacted specifically for auth-shaped statuses (401/403) -- every other
    status still surfaces the provider's real response text, which is usually genuinely
    useful for debugging (quota errors, malformed-request details) and isn't credential-
    bearing."""
    status = e.response.status_code if e.response is not None else None
    if status in (401, 403):
        return (
            f"{prefix} ({status}): Authentication failed -- check your API key. "
            "(Response body withheld: some providers echo part of the submitted key back "
            "in this specific error.)"
        )
    body = e.response.text if e.response is not None else str(e)
    return f"{prefix} ({status}): {body}"


def format_request_exception(prefix, e):
    """API-10, 2026-09-14 audit: every provider's generic `except Exception as e: return
    {"error": f"{prefix}: {e}"}` fallback surfaced whatever requests' own exception __str__
    happened to produce -- bounded (no raw traceback ever reached the user), but for the most
    common real-world case, no internet connection or a DNS failure, that text is genuinely
    unhelpful: something like "HTTPSConnectionPool(host='api.openai.com', port=443): Max
    retries exceeded... Failed to establish a new connection: [Errno 11001] getaddrinfo
    failed". Detects requests.exceptions.ConnectionError specifically (DNS failure, refused
    connection, no route to host all raise this) and gives a clear, actionable message
    instead; a requests.exceptions.Timeout gets its own equally direct message. Every other
    exception type (a malformed-response KeyError/IndexError, a JSON decode ValueError, etc.)
    falls through to the original str(e) behavior unchanged -- this only replaces the one
    genuinely common, genuinely unhelpful case."""
    if isinstance(e, requests.exceptions.ConnectionError):
        return f"{prefix}: could not reach the server -- check your internet connection. ({e})"
    if isinstance(e, requests.exceptions.Timeout):
        return f"{prefix}: the request timed out -- the server may be slow or unreachable. ({e})"
    return f"{prefix}: {e}"


def extract_openai_style_usage(data):
    """Normalizes the OpenAI-Chat-Completions-shaped 'usage' object
    ({'prompt_tokens', 'completion_tokens', ...}) that OpenRouter, OpenAI, Gemini
    (via its OpenAI-compatible endpoint), and Ollama's OpenAI-compatible endpoint
    all return into this plugin's common {'input_tokens', 'output_tokens'} shape
    (matching Anthropic's native naming, picked as the common form since
    ui/dock_widget.py only ever needs the two numbers, not the provider-specific
    field names). Returns None -- not a dict of zeros -- when the response has no
    'usage' object at all, so a provider/model that doesn't report usage is
    honestly reported as unknown rather than fabricated as zero cost. See
    docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md SS3.2 ("no cost/usage
    visibility in the UI") -- this is the shared extraction point every
    OpenAI-compatible client's complete() calls.

    cached_tokens (2026-09-13, direct request: "implement gemini caching" --
    confirmed against ai.google.dev/gemini-api/docs docs before implementing, not
    assumed): Gemini 2.5+/3.x models cache repeated prompt prefixes automatically
    at the infrastructure level (implicit caching, ~90% discount on cache hits,
    no client code needed to trigger it -- this plugin's own system prompt/tools
    already sit as a stable, unchanged prefix across a whole turn's tool-calling
    loop, exactly the shape implicit caching is designed for) -- but nothing
    previously surfaced whether it was actually happening. The standard
    OpenAI-compatible response shape (confirmed live by OpenAI's own docs and
    Gemini's OpenAI-compat endpoint following the same convention) reports the
    cache-hit portion as usage.prompt_tokens_details.cached_tokens -- a
    sub-breakdown of prompt_tokens, not subtracted from it, so prompt_tokens
    already reflects the FULL request size either way. Only included in the
    returned dict when present/truthy, same "don't fabricate what wasn't
    reported" policy as input_tokens/output_tokens themselves."""
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    if input_tokens is None and output_tokens is None:
        return None
    result = {"input_tokens": input_tokens or 0, "output_tokens": output_tokens or 0}
    # Real live crash, 2026-09-13 (reported against Gemini specifically, this field's own
    # provider): `(x or {}).get(...)` only degrades safely when x is falsy (None/""/0) --
    # if a provider's OpenAI-compat shim ever returns prompt_tokens_details as a TRUTHY
    # non-dict (a bare string being the most likely real shape, matching the exact
    # "'str' object has no attribute 'get'" crash reported live), `x or {}` evaluates to
    # x itself (truthy short-circuits `or`), and .get() on that raises uncaught. Explicit
    # isinstance check instead of relying on truthiness to decide "is this usable."
    details = usage.get("prompt_tokens_details")
    cached_tokens = details.get("cached_tokens") if isinstance(details, dict) else None
    if cached_tokens:
        result["cached_tokens"] = cached_tokens
    return result


class BaseAiProvider(ABC):
    @abstractmethod
    def complete(self, messages, tools=None, max_tokens=None):
        pass

    def set_status_callback(self, callback):
        self._status_callback = callback
