# -*- coding: utf-8 -*-
"""
HTTP for the data-fetch tools, through QGIS's own network stack when it is there.

plugins.qgis.org asks plugins to use QgsNetworkAccessManager so a request honours the proxy, authentication and SSL
settings the user configured in QGIS (2026-10-10 directory review; docs/IMPLEMENTATION_TRACKER.md, task #71). `urlopen` is a
drop-in for `urllib.request.urlopen` that does that through QgsBlockingNetworkRequest, which is safe on a worker thread (the
agent runs tools on one). It raises the same urllib.error.HTTPError / URLError, so every existing `except` keeps working.

Limits, found by the first CI runs of tests/test_net_live.py and stated rather than hidden:
  * QgsNetworkAccessManager sets its own User-Agent ("Mozilla/5.0 QGIS/<version>/<os>") and overwrites the one a caller passes.
  * It also applies QGIS's own network timeout (Settings > Options > Network, default 60 s) in place of the per-call `timeout`,
    so a call that asked for 15 s can wait longer. A caller that needs a short, exact timeout uses `stream=True`.
  * A redirect with a relative Location fails inside QGIS ("Protocol "" is unknown"), so redirects are resolved here.
Two deliberate limits on the buffered path:
  * QgsBlockingNetworkRequest returns the whole reply in memory, so a request whose body is large (a Geofabrik extract, a model
    checkpoint) must use `stream=True`, which stays on urllib and streams to disk. That path still honours the QGIS proxy.
  * Outside QGIS (the plain unit-test job, the script-isolation worker) there is no QgsNetworkAccessManager, so this falls
    back to urllib. The fallback looks `urllib.request.urlopen` up at call time, which is also what lets the existing tests
    keep patching it.
Only http and https URLs are opened; file:, ftp: and custom schemes are refused (Bandit B310).
"""

import io
import socket
import urllib.error
import urllib.parse
import urllib.request

try:
    from qgis.core import QgsBlockingNetworkRequest, QgsNetworkAccessManager  # noqa: F401
    from qgis.PyQt.QtCore import QByteArray, QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest
    QGIS_NETWORK_AVAILABLE = True
except ImportError:  # no QGIS: unit tests, the isolation worker
    QGIS_NETWORK_AVAILABLE = False

ALLOWED_SCHEMES = ("http", "https")


def _as_request(request):
    return request if isinstance(request, urllib.request.Request) else urllib.request.Request(str(request))


def _check_scheme(url):
    if url.split(":", 1)[0].lower() not in ALLOWED_SCHEMES:
        raise urllib.error.URLError(f"unsupported URL scheme (only http and https are allowed): {url.split(':', 1)[0]}")


class _Headers:
    """Case-insensitive header lookup with the .get() the callers use."""

    def __init__(self, pairs):
        self._h = {str(k).lower(): str(v) for k, v in pairs}

    def get(self, name, default=None):
        return self._h.get(name.lower(), default)

    def __getitem__(self, name):
        return self._h[name.lower()]

    def __contains__(self, name):
        return name.lower() in self._h

    def items(self):
        return self._h.items()


class Response:
    """What urllib's response gave the callers: a context manager with read(), status, headers, geturl()."""

    def __init__(self, body, status, headers, url):
        self._body = io.BytesIO(body)
        self.status = self.code = status
        self.headers = _Headers(headers)
        self._url = url

    def read(self, amt=-1):
        return self._body.read(amt)

    def getcode(self):
        return self.status

    def geturl(self):
        return self._url

    def info(self):
        return self.headers

    def close(self):
        self._body.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _enum(owner, group, name):
    """Qt5 flat enums and Qt6 scoped enums both."""
    scoped = getattr(owner, group, None)
    return getattr(scoped, name) if scoped is not None and hasattr(scoped, name) else getattr(owner, name)


def _qgis_urlopen(req, timeout, _redirects_left=5):
    url = req.full_url
    qreq = QNetworkRequest(QUrl(url))
    for key, value in req.header_items():
        qreq.setRawHeader(QByteArray(key.encode("utf-8")), QByteArray(str(value).encode("utf-8")))
    if timeout and hasattr(qreq, "setTransferTimeout"):
        qreq.setTransferTimeout(int(timeout * 1000))
    try:
        qreq.setAttribute(_enum(QNetworkRequest, "Attribute", "RedirectPolicyAttribute"),
                          _enum(QNetworkRequest, "RedirectPolicy", "ManualRedirectPolicy"))
    except (AttributeError, TypeError):
        pass
    method = req.get_method()
    if method == "POST" and not req.has_header("Content-type"):
        # urllib sends this for a POST body with no type; without it Qt logs a warning and guesses.
        qreq.setRawHeader(QByteArray(b"Content-Type"), QByteArray(b"application/x-www-form-urlencoded"))
    blocking = QgsBlockingNetworkRequest()
    if method == "GET":
        err = blocking.get(qreq, True)
    elif method == "HEAD":
        err = blocking.head(qreq, True)
    elif method == "POST":
        err = blocking.post(qreq, QByteArray(req.data or b""))
    else:
        raise urllib.error.URLError(f"unsupported method: {method}")
    reply = blocking.reply()
    content = bytes(reply.content())
    status = reply.attribute(_enum(QNetworkRequest, "Attribute", "HttpStatusCodeAttribute"))
    status = int(status) if status is not None else 0
    # QgsNetworkReplyContent has rawHeaderList()/rawHeader(), not Qt's rawHeaderPairs() (found by the first CI run of test_net_live).
    headers = [(bytes(name).decode("latin-1"), bytes(reply.rawHeader(name)).decode("latin-1")) for name in reply.rawHeaderList()]
    ok = _enum(QgsBlockingNetworkRequest, "ErrorCode", "NoError")
    if err == ok:
        return Response(content, status or 200, headers, url)
    location = dict((k.lower(), v) for k, v in headers).get("location")
    if status in (301, 302, 303, 307, 308) and location and method in ("GET", "HEAD") and _redirects_left > 0:
        target = urllib.parse.urljoin(url, location)
        _check_scheme(target)
        follow = urllib.request.Request(target, headers=dict(req.header_items()), method=method)
        return _qgis_urlopen(follow, timeout, _redirects_left - 1)
    if status >= 400:
        # Same exception urllib raises, with the body readable from it as callers expect.
        raise urllib.error.HTTPError(url, status, reply.errorString(), _Headers(headers), io.BytesIO(content))
    if err == _enum(QgsBlockingNetworkRequest, "ErrorCode", "TimeoutError"):
        raise urllib.error.URLError(socket.timeout("timed out"))
    raise urllib.error.URLError(f"{reply.errorString() or 'network error'} (HTTP status {status or 'none'}, url {url})")


def _urllib_open(req, timeout):
    """The single audited urllib call: the scheme was checked by the caller, and the proxy QGIS is configured with is used."""
    handlers = []
    try:
        from .proxy import get_qgis_proxy_dict
        proxies = get_qgis_proxy_dict()
        if proxies:
            handlers.append(urllib.request.ProxyHandler(proxies))
    except Exception:  # nosec B110 (best-effort: no proxy configured is the normal case)
        pass
    if handlers:
        return urllib.request.build_opener(*handlers).open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)  # nosec B310 (scheme checked above)


def urlopen(request, timeout=30, stream=False):
    """Drop-in for urllib.request.urlopen. `stream=True` for a large body that is read in chunks and written to disk."""
    try:
        req = _as_request(request)
    except ValueError:
        # Not a URL at all (e.g. a bare word). Let urllib raise its own error for it, as before.
        return _urllib_open(request, timeout)
    _check_scheme(req.full_url)
    if QGIS_NETWORK_AVAILABLE and not stream:
        return _qgis_urlopen(req, timeout)
    return _urllib_open(req, timeout)
