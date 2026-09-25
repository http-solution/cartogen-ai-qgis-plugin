# -*- coding: utf-8 -*-
"""
Shared retry/backoff for urllib.request-based fetches -- API-003, 2026-09-14 audit.

Mirrors infrastructure/providers/base.py's post_with_retry/get_with_retry (LLM provider HTTP calls
already had this resilience since 2026-09-12) -- humanitarian/hazard urllib fetch tools had
none at all, so a single transient network hiccup or a 5xx from an external data source
(NASA FIRMS/EONET, GDACS, HDX, geoBoundaries, etc.) failed the whole tool call outright with
no retry, unlike every LLM API call this plugin makes. Deliberately narrower in scope than the
provider retry helpers: these are all GET-shaped, idempotent-by-construction fetches of public
data (never a POST, never a request with side effects), so there's no equivalent to API-001's
non-idempotent-POST concern here -- retrying is always safe.
"""

import time
import urllib.error
import urllib.request

DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_SECONDS = 1.5

# Same retryable-status reasoning as providers/base.py's RETRYABLE_STATUS_CODES: 429 and the
# common transient 5xx codes are worth a retry; a 4xx client error (400/401/403/404/etc.) is a
# real, permanent problem retrying won't fix.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def urlopen_with_retry(request, timeout, opener=None, max_retries=DEFAULT_MAX_RETRIES,
                       backoff_seconds=DEFAULT_BACKOFF_SECONDS):
    """Drop-in replacement for `urllib.request.urlopen(request, timeout=timeout)` (or
    `opener.open(request, timeout=timeout)` when an SSRF-safe opener from vector_tools.py's
    _build_safe_opener() is given instead) -- retries a transient network error or a
    retryable HTTP status with a short exponential backoff before giving up. Returns the same
    context-manager response object the caller already unpacks with `with ... as response:`.
    A permanent HTTPError (4xx other than 429) is NOT retried -- it's raised immediately, same
    as an unretried call would, so callers that already special-case e.g. 404 keep working
    unchanged."""
    opener_call = opener.open if opener is not None else urllib.request.urlopen
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return opener_call(request, timeout=timeout)
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                time.sleep(backoff_seconds * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(backoff_seconds * (attempt + 1))
                continue
            raise
    raise last_exc
