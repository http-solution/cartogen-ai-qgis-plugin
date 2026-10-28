import re
import time
from abc import ABC, abstractmethod

# QGIS Network Access Manager proxy integration (Phase 8):
# If QGIS has proxy settings configured (e.g. corporate or UN agency proxy),
# extract them so requests calls don't bypass user network configurations.
from ...core.proxy import get_qgis_proxy_dict
from ...core import net as _net
from ...core.logger import log_event

try:
    import requests  # type: ignore[import-untyped]
    HTTPError = requests.exceptions.HTTPError
    RequestException = requests.exceptions.RequestException
    ConnectionError_ = requests.exceptions.ConnectionError
    Timeout_ = requests.exceptions.Timeout
except (ImportError, AttributeError):
    requests = None  # type: ignore[assignment]
    class HTTPError(Exception):  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            super().__init__(*args)
            self.response = kwargs.get("response")
    class RequestException(Exception):  # type: ignore[no-redef]
        pass
    class ConnectionError_(RequestException):  # type: ignore[misc,no-redef,valid-type]
        pass
    class Timeout_(RequestException):  # type: ignore[misc,no-redef,valid-type]
        pass

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


def _quota_will_not_clear(response):
    """True for a 429 that waiting a minute cannot fix: a quota of zero (the plan has no access to the model) or a retry delay the
    provider puts at more than two minutes. The retry loop below waits 10 + 20 + 30 s before giving up, which is what made a free-tier
    key on a Pro model look 'stuck' for a minute per attempt (2026-10-11 report: limit 0, retry in 11 h)."""
    text = getattr(response, "text", "") or ""
    if not isinstance(text, str):
        return False
    if re.search(r"limit:\s*0\b", text):
        return True
    delay = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', text)
    return bool(delay and float(delay.group(1)) > 120)


def _user_stopped():
    """True once the user pressed Stop: a request that was dropped for that reason must not be retried."""
    try:
        from ...core import cancel_signal
        return cancel_signal.is_cancelled()
    except Exception:
        return False


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
        except RequestException as e:
            last_exc = e
            if attempt < max_retries and not _user_stopped():
                time.sleep(DEFAULT_BACKOFF_SECONDS * (attempt + 1))
                continue
            raise
        if response.status_code == 429:
            if _quota_will_not_clear(response):
                return response
            if attempt < RATE_LIMIT_MAX_RETRIES:
                time.sleep(RATE_LIMIT_BACKOFF_SECONDS * (attempt + 1))
                continue
            return response
        if response.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
            time.sleep(DEFAULT_BACKOFF_SECONDS * (attempt + 1))
            continue
        return response
    raise last_exc


class QgisResponse:
    """The slice of requests.Response the provider clients use, over a reply from QGIS's network stack (task #71 phase 2):
    status_code, text, content, headers, json(), raise_for_status()."""

    def __init__(self, status, headers, body, url):
        self.status_code = status
        self.headers = _net._Headers(headers)
        self.content = body
        self.url = url
        self.reason = ""

    @property
    def text(self):
        return self.content.decode("utf-8", "replace")

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        import json as _json
        return _json.loads(self.content.decode("utf-8"))

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError(f"{self.status_code} Error for url: {self.url}", response=self)


def _use_qgis_network(local):
    """Hosted providers go through QGIS's network stack when it exists, so QGIS proxy, authentication and SSL settings apply.
    `local` (Ollama) stays on requests: a local model can take minutes to answer, and QGIS applies its own network timeout
    (default 60 s) instead of the per-call one, so routing it through QGIS would cut long generations short."""
    return _net.QGIS_NETWORK_AVAILABLE and not local and _qgis_network_enabled()


def _qgis_network_enabled():
    """The user-facing kill-switch for the QGIS network path (default on); a missing QGIS or an unreadable setting counts as on."""
    try:
        from qgis.core import QgsSettings
        from ..settings_keys import SETTINGS_HOSTED_VIA_QGIS_NETWORK
        return bool(QgsSettings().value(SETTINGS_HOSTED_VIA_QGIS_NETWORK, True, type=bool))
    except Exception:
        return True


def _qgis_send(method, url, headers, payload, timeout):
    try:
        status, reply_headers, body = _net.request(method, url, headers=headers, data=payload, timeout=timeout)
    except _net.NetworkError as e:
        raise (Timeout_ if e.timed_out else ConnectionError_)(str(e)) from e
    if status in (401, 403):
        # Metadata only (no key, header or body): lets a field report say which sender and proxy setup produced a refusal.
        from urllib.parse import urlparse
        log_event("provider_auth_refused", tag="Providers", sender="qgis", status=status, host=urlparse(url).hostname or "",
                  qgis_proxy=bool(get_qgis_proxy_dict()), error=True)
    return QgisResponse(status, reply_headers, body, url)


def post_with_retry(url, headers, payload_json, timeout, max_retries=DEFAULT_MAX_RETRIES, local=False):
    """Shared HTTP POST for every provider's raw requests-based client -- see
    _request_with_retry for the retry behavior. Drop-in replacement for a bare
    requests.post(...) call. `local=True` keeps a local server (Ollama) on requests, see _use_qgis_network."""
    if _use_qgis_network(local):
        return _request_with_retry(lambda: _qgis_send("POST", url, headers, payload_json, timeout), timeout, max_retries)
    if requests is None:
        raise RuntimeError("The 'requests' package is required for network LLM provider calls.")
    proxies = get_qgis_proxy_dict()
    return _request_with_retry(
        lambda: requests.post(url, headers=headers, data=payload_json, timeout=timeout, proxies=proxies),
        timeout, max_retries,
    )


def get_with_retry(url, headers, timeout, max_retries=DEFAULT_MAX_RETRIES, local=False):
    """API-002, 2026-09-14 audit: every provider's list_models() used a bare requests.get(...)
    with no retry at all -- unlike the chat-completion path, which has had post_with_retry's
    resilience since 2026-09-12. A transient network hiccup or a 429 while just listing models
    (e.g. populating the settings dialog's model dropdown) used to fail outright with no retry,
    inconsistent with every other HTTP call this codebase makes. Same retry/backoff behavior as
    post_with_retry, just for GET -- drop-in replacement for a bare requests.get(...) call."""
    if _use_qgis_network(local):
        return _request_with_retry(lambda: _qgis_send("GET", url, headers, None, timeout), timeout, max_retries)
    if requests is None:
        raise RuntimeError("The 'requests' package is required for network LLM provider calls.")
    proxies = get_qgis_proxy_dict()
    return _request_with_retry(
        lambda: requests.get(url, headers=headers, timeout=timeout, proxies=proxies),
        timeout, max_retries,
    )


_REASON_CODE = re.compile(r"^(?:[A-Z][A-Z_]{2,60}|[a-z]+(?:_[a-z]+){1,6})$")


def _auth_reason_codes(response):
    """The machine-readable reason codes in a 401/403 body (Gemini: PERMISSION_DENIED, API_KEY_INVALID, SERVICE_DISABLED; OpenAI:
    invalid_api_key), which tell the user why the provider refused without showing the body. A 403 chat message that only said
    'check your API key' sent a user with a disabled API and a good key looking in the wrong place (2026-10-11 report). Only values
    shaped like an enum name (letters and underscores, no digits or hyphens) are returned, so a key echoed back in the body can
    never pass through: API keys carry digits or hyphens."""
    import json as _json
    try:
        error = _json.loads(response.text).get("error")
    except Exception:
        return []
    if not isinstance(error, dict):
        return []
    found = [error.get("status"), error.get("code")]
    details = error.get("details")
    if isinstance(details, list):
        found.extend(d.get("reason") for d in details if isinstance(d, dict))
    codes = []
    for value in found:
        if isinstance(value, str) and _REASON_CODE.match(value) and value not in codes:
            codes.append(value)
    return codes


def _header_value(response, name):
    """A response header as short printable ASCII, or ''. Headers such as Server and Via name software, never a credential."""
    try:
        value = response.headers.get(name)
    except Exception:
        return ""
    return "".join(c for c in str(value or "") if " " <= c <= "~")[:60].strip()


def _unrecognised_reply_note(response):
    """What a 401/403 looks like when it carries no provider reason code: the server software, content type and body size. A refusal
    that is not the provider's own JSON error (an empty body, an HTML page) usually comes from something in between, such as a proxy or
    firewall, and these three facts say so without showing the body. Added after a 2026-10-11 report where a 403 gave nothing to go on."""
    try:
        size = len(response.content if response.content is not None else b"")
    except Exception:
        size = -1
    facts = [f"{label}: {value}" for label, value in
             (("server", _header_value(response, "Server")), ("via", _header_value(response, "Via")),
              ("content-type", _header_value(response, "Content-Type"))) if value]
    facts.append("empty body" if size == 0 else f"body {size} bytes" if size > 0 else "body unreadable")
    return " No provider reason code in the reply (" + "; ".join(facts) + ")."


_KEY_SOURCE_LABELS = {
    "auth_store": "QGIS's saved credentials",
    "session_memory": "memory for this session only (not saved)",
    "legacy_settings": "an old plaintext setting from an earlier version",
}


def key_in_use_note(provider, api_key):
    """Which key a refused request carried, described without revealing it: where it was found, its length and its last four
    characters (what Google AI Studio and OpenAI show next to a key), plus a warning when it holds a space or line break. Lets a
    user see that the key sent is not the one they just entered. Never the whole key."""
    key = str(api_key or "")
    if not key:
        return " The request carried no API key."
    try:
        from ..auth import CredentialManager
        source = CredentialManager.last_credential_source(provider)
    except Exception:
        source = ""
    note = f" Key sent: {len(key)} characters, ending {key[-4:]}, from {_KEY_SOURCE_LABELS.get(source, 'an unknown source')}."
    if any(c.isspace() for c in key) or not key.isascii():
        note += " It contains a space, line break or non-ASCII character, which providers reject."
    return note


def _quota_summary(response):
    """A Google 429 (RESOURCE_EXHAUSTED) as one readable sentence, or '' when the body is not that shape. The raw body is a screenful of
    JSON; what the user needs is the model, whether it is the free tier, whether the limit is zero (the plan has no access to the model at
    all), and how long to wait. Quota errors carry no credential, so showing these facts is safe."""
    import json as _json
    try:
        data = _json.loads(response.text)
        error = (data[0] if isinstance(data, list) else data).get("error", {})
        details = error.get("details", [])
    except Exception:
        return ""
    if not isinstance(error, dict) or error.get("status") != "RESOURCE_EXHAUSTED" or not isinstance(details, list):
        return ""
    models, free_tier, retry = [], False, ""
    for d in details:
        if not isinstance(d, dict):
            continue
        for v in d.get("violations", []) if isinstance(d.get("violations"), list) else []:
            if isinstance(v, dict):
                free_tier = free_tier or "FreeTier" in str(v.get("quotaId", ""))
                model = (v.get("quotaDimensions") or {}).get("model") if isinstance(v.get("quotaDimensions"), dict) else None
                if model and model not in models:
                    models.append(str(model)[:60])
        delay = d.get("retryDelay")
        if isinstance(delay, str) and delay.endswith("s") and delay[:-1].replace(".", "", 1).isdigit():
            seconds = int(float(delay[:-1]))
            retry = f" Google says to retry in about {seconds // 3600} h {seconds % 3600 // 60} min." if seconds >= 3600 else f" Google says to retry in about {max(seconds // 60, 1)} min."
    zero = bool(re.search(r"limit:\s*0\b", str(error.get("message", ""))))
    what = ", ".join(models) or "this model"
    if free_tier and zero:
        return (f"the free tier has no quota at all for {what} (limit 0), so it needs a paid plan: enable billing on the key's Google "
                f"project, or choose a Flash model such as gemini-flash-latest.{retry}")
    return f"quota exceeded for {what}{' on the free tier' if free_tier else ''}.{retry}"


def reply_summary(response):
    """One short line on a provider reply that was not usable: the status plus either the provider's own error text (JSON `error.status`
    and `error.message`, first line, long key-like strings blanked) or, when the body is not that, the server software, content type and
    size. Used to list what every model in a fallback chain answered. Provider error text names models and quotas, not credentials; the
    blanking is a second guard."""
    import json as _json
    status = getattr(response, "status_code", "?")
    try:
        data = _json.loads(response.text)
        error = (data[0] if isinstance(data, list) else data).get("error", {})
        text = f"{error.get('status', '')} {str(error.get('message', '')).splitlines()[0] if error.get('message') else ''}".strip()
    except Exception:
        text = ""
    if text:
        text = re.sub(r"[A-Za-z0-9_\-]{30,}", "[redacted]", text)[:140]
        return f"{status} {text}"
    return f"{status}{_unrecognised_reply_note(response).rstrip('.')}"


def format_http_error(prefix, e, key_note=""):
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
        reasons = _auth_reason_codes(e.response)
        reason_note = f" Provider reason: {', '.join(reasons)}." if reasons else _unrecognised_reply_note(e.response)
        return (
            f"{prefix} ({status}): Authentication failed -- check your API key.{reason_note}{key_note} "
            "(Response body withheld: some providers echo part of the submitted key back "
            "in this specific error.)"
        )
    if status == 429 and e.response is not None:
        summary = _quota_summary(e.response)
        if summary:
            return f"{prefix} (429): {summary}"
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
    if isinstance(e, ConnectionError_):
        return f"{prefix}: could not reach the server -- check your internet connection. ({e})"
    if isinstance(e, Timeout_):
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


class ModelChainMixin:
    """`model` as "the model to try first", with `models` as the fallback chain behind it.

    Live-reported 2026-09-25 (cost review): agent_orchestrator._apply_auto_model_selection picks a
    cheaper model for simple requests by assigning `client.model = picked`, but Gemini, OpenAI,
    OpenRouter and Cartogen's complete() looped over `self.models` (built once in __init__, the
    configured model first) and overwrote `self.model` with each entry, so the pick was discarded
    and the configured -- usually most expensive -- model was sent every time. Reproduced by
    setting `client.model` to a made-up id and recording what `_post` received: always the
    configured model, on all three providers tested. Claude and Ollama use `self.model` directly
    and were never affected.

    The fix: assigning `model` from outside records a preference, and `_model_chain()` puts it
    first. The fallback loop records the model it is currently trying in `_model` only, so a
    fallback (a 404 or a 429) does not become the next call's preferred model: each call starts
    again from the preference, as it did before this change."""

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, value):
        self._model = value
        self._preferred_model = value

    def _model_chain(self):
        preferred = getattr(self, "_preferred_model", None)
        chain = [m for m in self.models if m != preferred]
        return ([preferred] if preferred else []) + chain


class BaseAiProvider(ABC):
    @abstractmethod
    def complete(self, messages, tools=None, max_tokens=None):
        pass

    def set_status_callback(self, callback):
        self._status_callback = callback


_RECENCY = re.compile(r"\b(latest|newest|most recent|up[- ]to[- ]date|currently|today|right now|this (?:week|month|year))\b", re.I)


def freshen_query(query, today=None):
    """Adds today's date and a freshness instruction to a web-search query that asks for the latest or current thing. Pure given `today`.

    rc17 hand test B5 (2026-10-06): "the latest stable QGIS release announcement" came back as QGIS 4.0 (March 2026) when 4.2 had been
    announced in July; the search backend had no idea what "latest" meant relative to today. A query with no recency word is
    returned unchanged."""
    text = str(query or "")
    if not _RECENCY.search(text):
        return text
    import datetime
    day = (today or datetime.date.today()).isoformat()
    return (f"{text.rstrip()} (Today is {day}. Use the most recent official sources available, check whether anything newer than "
            "your first result exists, and state each source's publication date.)")

