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
  * A redirect with a relative Location fails inside QGIS ("Protocol "" is unknown"; CI run of 2026-10-10, and neither a manual
    redirect policy nor re-resolving the target could intercept it), so that one case is retried once through urllib.
  * A request with a body or a credential header (every hosted-AI call) does NOT go through QgsBlockingNetworkRequest: that class
    follows a redirect with a brand-new request, which loses the Authorization header (reproduced in QGIS 4.2.2, 2026-10-11, see
    test_a_post_keeps_its_key_and_body_across_a_307_or_308_redirect). Those requests use QgsNetworkAccessManager directly and follow
    redirects in _qgis_send_following: the credential stays on the same site and is dropped for another one.
Two deliberate limits on the buffered path:
  * QgsBlockingNetworkRequest returns the whole reply in memory, so a request whose body is large (a Geofabrik extract, a model
    checkpoint) must use `stream=True`, which stays on urllib and streams to disk. That path still honours the QGIS proxy.
  * Outside QGIS (the plain unit-test job, the script-isolation worker) there is no QgsNetworkAccessManager, so this falls
    back to urllib. The fallback looks `urllib.request.urlopen` up at call time, which is also what lets the existing tests
    keep patching it.
Only http and https URLs are opened; file:, ftp: and custom schemes are refused (Bandit B310).
"""

import collections
import io
import urllib.error
import urllib.request
import contextlib
import socket
import ssl
import urllib.parse

try:
    from qgis.core import QgsBlockingNetworkRequest, QgsNetworkAccessManager
    from qgis.PyQt.QtCore import QByteArray, QEventLoop, QTimer, QUrl
    from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
    QGIS_NETWORK_AVAILABLE = True
except ImportError:  # no QGIS: unit tests, the isolation worker
    QGIS_NETWORK_AVAILABLE = False

ALLOWED_SCHEMES = ("http", "https")

# Ceilings on what one remote answer may make this process hold in memory. A data service that is hostile, hijacked or just
# wrong could otherwise answer a small query with gigabytes (or a gzip/zip that expands to gigabytes) and take QGIS down with
# it. Generous for the real sources (a WorldPop country raster is the largest at a few hundred MB), tight enough to stop that.
MAX_TEXT_BYTES = 64 * 1024 * 1024          # JSON / CSV / listings
MAX_DOWNLOAD_BYTES = 1536 * 1024 * 1024    # a raster or boundary file kept in memory before it is written to disk
MAX_EXPANDED_BYTES = 256 * 1024 * 1024     # what a gzip tile or zip member may expand to


class ResponseTooLargeError(OSError):
    """A remote answer, or what it expands to, is bigger than the ceiling for that kind of data."""


def redact_url(url):
    """scheme://host/path without the query or fragment. A signed download link carries its credentials in the query (AWSAccessKeyId,
    Signature, x-amz-security-token), and an error message that quotes the link would show them in the chat and the log. Pure."""
    try:
        parts = urllib.parse.urlsplit(str(url))
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except ValueError:
        return "(link)"


def describe_download_failure(exc, url=None):
    """One plain sentence for a person: which site, what kind of failure, what to try. Never quotes the exception text, because that text
    can hold the whole signed link (the Yemen ADM1 report of 2026-10-26 printed an Amazon S3 key and token in the chat). Pure."""
    host = urllib.parse.urlsplit(str(url)).hostname if url else None
    where = f" from {host}" if host else ""
    code = getattr(exc, "code", None)
    reason = getattr(exc, "reason", None)
    if isinstance(code, int):
        if code == 407:
            return (f"The download{where} was stopped by a proxy that asks for a login (HTTP 407). Check the proxy settings and login in QGIS "
                    "(Settings > Options > Network).")
        if code in (401, 403):
            return (f"The download{where} was refused (HTTP {code}). The file host, or a proxy or firewall on this network, did not allow this "
                    "request. Try again in a minute; if it keeps happening, download the file in a browser and load it with add_layer_from_path.")
        if code in (404, 410):
            return f"The file{where} was not found (HTTP {code}); the dataset may have moved or been removed."
        if code == 429:
            return f"The server{where} says there were too many requests (HTTP 429). Wait a few minutes and try again."
        if code >= 500:
            return (f"The server{where} answered with an error (HTTP {code}). It may be down, or a proxy or gateway on this network could "
                    "not reach it. Try again later.")
        return f"The download{where} failed (HTTP {code})."
    inner = reason if isinstance(reason, BaseException) else exc
    if isinstance(inner, (socket.timeout, TimeoutError)) or "timed out" in str(exc).lower():
        return f"The download{where} timed out. The connection may be slow or blocked; try again, or check the proxy settings in QGIS."
    if isinstance(inner, socket.gaierror) or ("not found" in str(inner).lower() and "host" in str(inner).lower()):
        return f"The site{where} could not be found (DNS or proxy). Check the internet connection and the proxy settings in QGIS."
    if isinstance(inner, ssl.SSLError) or "ssl" in str(inner).lower() or "certificate" in str(inner).lower():
        return (f"A secure connection{where} could not be made (certificate or SSL). A proxy that inspects traffic can cause this; check "
                "the proxy and certificate settings in QGIS.")
    if isinstance(inner, ResponseTooLargeError):
        return f"The file{where} is larger than this tool accepts."
    return f"The download{where} failed ({type(exc).__name__}). Check the internet connection and the proxy settings in QGIS."


def read_capped(response, limit=MAX_TEXT_BYTES):
    """response.read(), refusing a body larger than `limit` bytes instead of holding it all."""
    data = response.read(limit + 1)
    if len(data) > limit:
        raise ResponseTooLargeError(f"the remote answer is larger than the {limit // (1024 * 1024)} MB this tool accepts")
    return data


def gunzip_capped(data, limit=MAX_EXPANDED_BYTES):
    """gzip.decompress with a ceiling on the expanded size (a gzip bomb is a few KB that expands to gigabytes)."""
    import zlib
    inflater = zlib.decompressobj(wbits=31)   # 31 = gzip container
    try:
        out = inflater.decompress(data, limit + 1)
    except zlib.error as e:
        raise OSError(f"not a valid gzip stream: {e}") from e
    if len(out) > limit or inflater.unconsumed_tail:
        raise ResponseTooLargeError(f"the gzip data expands to more than {limit // (1024 * 1024)} MB")
    return out


def zip_member_capped(archive, name, limit=MAX_EXPANDED_BYTES):
    """ZipFile.read(name), refusing a member whose declared size is above `limit` (checked before anything is inflated)."""
    if archive.getinfo(name).file_size > limit:
        raise ResponseTooLargeError(f"'{name}' in the archive expands to more than {limit // (1024 * 1024)} MB")
    return archive.read(name)


def _check_scheme(url):
    if url.split(":", 1)[0].lower() not in ALLOWED_SCHEMES:
        raise urllib.error.URLError(f"unsupported URL scheme (only http and https are allowed): {url.split(':', 1)[0]}")


def build_request(url, data=None, headers=None, method=None):
    """The one place a urllib Request is made for a data fetch: the scheme is checked first (http and https only; file:, ftp: and
    custom schemes are refused), which is what Bandit B310 / ruff S310 ask for."""
    if ":" not in str(url):
        raise ValueError(f"unknown url type: {url!r}")   # what urllib itself raises for a string that is not a URL
    _check_scheme(str(url))
    return urllib.request.Request(str(url), data=data, headers=headers or {}, method=method)  # noqa: S310 (scheme checked above)


def _as_request(request):
    return request if isinstance(request, urllib.request.Request) else build_request(request)


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


Reply = collections.namedtuple("Reply", "ok status headers body error timed_out")


def _qgis_send_blocking(method, url, header_items, data, timeout):
    """One request through QgsBlockingNetworkRequest. Never raises for an HTTP error status: the caller decides."""
    qreq = QNetworkRequest(QUrl(url))
    has_content_type = False
    for key, value in header_items:
        has_content_type = has_content_type or str(key).lower() == "content-type"
        qreq.setRawHeader(QByteArray(str(key).encode("utf-8")), QByteArray(str(value).encode("utf-8")))
    if timeout and hasattr(qreq, "setTransferTimeout"):
        qreq.setTransferTimeout(int(timeout * 1000))
    with contextlib.suppress(AttributeError, TypeError):
        qreq.setAttribute(_enum(QNetworkRequest, "Attribute", "RedirectPolicyAttribute"),
                          _enum(QNetworkRequest, "RedirectPolicy", "NoLessSafeRedirectPolicy"))
    if method == "POST" and not has_content_type:
        # urllib sends this for a POST body with no type; without it Qt logs a warning and guesses.
        qreq.setRawHeader(QByteArray(b"Content-Type"), QByteArray(b"application/x-www-form-urlencoded"))
    blocking = QgsBlockingNetworkRequest()
    if method == "GET":
        err = blocking.get(qreq, True)
    elif method == "HEAD":
        err = blocking.head(qreq, True)
    elif method == "POST":
        err = blocking.post(qreq, QByteArray(data or b""))
    else:
        raise urllib.error.URLError(f"unsupported method: {method}")
    reply = blocking.reply()
    status = reply.attribute(_enum(QNetworkRequest, "Attribute", "HttpStatusCodeAttribute"))
    # QgsNetworkReplyContent has rawHeaderList()/rawHeader(), not Qt's rawHeaderPairs() (found by the first CI run of test_net_live).
    headers = [(bytes(name).decode("latin-1"), bytes(reply.rawHeader(name)).decode("latin-1")) for name in reply.rawHeaderList()]
    return Reply(
        ok=(err == _enum(QgsBlockingNetworkRequest, "ErrorCode", "NoError")),
        status=int(status) if status is not None else 0,
        headers=headers,
        body=bytes(reply.content()),
        error=reply.errorString() or "network error",
        timed_out=(err == _enum(QgsBlockingNetworkRequest, "ErrorCode", "TimeoutError")),
    )


# Headers that carry a credential: dropped when a redirect leaves the original site (what requests and curl do), kept on the same site.
# A Host header names the site the request was MADE to. It must not follow a redirect: S3 picks the bucket from Host, so a presigned
# download link on s3.amazonaws.com that received "Host: data.humdata.org" answered 403 SignatureDoesNotMatch (the signed resource became
# /data.humdata.org/...). Reproduced 2026-10-26 with this module's own stream_following against HDX's yem_admin_boundaries.geojson.zip while
# curl got 200; it is what blocked the HDX boundary download in the Yemen ADM1 field report. urllib and QGIS each set Host for the new target.
_HOST_HEADER = "host"
_CREDENTIAL_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "x-api-key", "api-key", "x-goog-api-key"})
_REDIRECT_CODES = (301, 302, 303, 307, 308)
_MAX_REDIRECTS = 5


def _origin(url):
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    default = {"http": 80, "https": 443}.get(parts.scheme.lower())
    return parts.scheme.lower(), (parts.hostname or "").lower(), parts.port or default


def _needs_own_redirects(method, header_items):
    """A request with a body or a credential must follow redirects here, not inside QgsBlockingNetworkRequest.

    Found 2026-10-11 by tests/test_net_live.py in QGIS 4.2.2: QgsBlockingNetworkRequest follows a redirect by building a NEW
    QNetworkRequest from the target URL alone (qgsblockingnetworkrequest.cpp, replyFinished), so the Authorization header is lost: a
    hosted-AI call redirected once (a proxy, a gateway) reached the provider with no key and drew a 403. Plain keyless GETs are fine
    there and keep QGIS's cache and its main-thread handling."""
    return method == "POST" or any(str(k).lower() in _CREDENTIAL_HEADERS for k, _v in header_items)


def _qgis_hop(method, url, header_items, data, timeout):
    """One request through QgsNetworkAccessManager, redirects NOT followed. Pumps the event loop on the calling thread (each thread has
    its own manager), as _StreamResponse does. Never raises for an HTTP status."""
    nam = QgsNetworkAccessManager.instance()
    qreq = QNetworkRequest(QUrl(url))
    has_content_type = False
    for key, value in header_items:
        has_content_type = has_content_type or str(key).lower() == "content-type"
        qreq.setRawHeader(QByteArray(str(key).encode("utf-8")), QByteArray(str(value).encode("utf-8")))
    if timeout and hasattr(qreq, "setTransferTimeout"):
        qreq.setTransferTimeout(int(timeout * 1000))
    with contextlib.suppress(AttributeError, TypeError):
        qreq.setAttribute(_enum(QNetworkRequest, "Attribute", "RedirectPolicyAttribute"),
                          _enum(QNetworkRequest, "RedirectPolicy", "ManualRedirectPolicy"))
        qreq.setAttribute(_enum(QNetworkRequest, "Attribute", "CacheLoadControlAttribute"),
                          _enum(QNetworkRequest, "CacheLoadControl", "PreferCache" if method in ("GET", "HEAD") else "AlwaysNetwork"))
    if method == "POST" and not has_content_type:
        qreq.setRawHeader(QByteArray(b"Content-Type"), QByteArray(b"application/x-www-form-urlencoded"))
    if method == "GET":
        reply = nam.get(qreq)
    elif method == "HEAD":
        reply = nam.head(qreq)
    elif method == "POST":
        reply = nam.post(qreq, QByteArray(data or b""))
    else:
        raise urllib.error.URLError(f"unsupported method: {method}")
    loop = QEventLoop()
    guard = QTimer()
    guard.setSingleShot(True)
    guard.timeout.connect(reply.abort)         # backstop for a transfer timeout that never fires; the reply then finishes as aborted
    reply.finished.connect(loop.quit)
    if timeout:
        guard.start(int(timeout * 1000) + 5000)
    # rc40 hand test RC37-F2 / OI-223: Stop pressed while a model call was in flight took 25-30 s to take effect, because this wait
    # only ended when the reply did. Poll the user's Stop here so the request is dropped within a fraction of a second.
    stop_state = {"stopped": False}
    stop_poll = QTimer()
    stop_poll.setInterval(250)

    def _abort_if_stopped():
        from . import cancel_signal
        if cancel_signal.is_cancelled():
            stop_state["stopped"] = True
            stop_poll.stop()
            reply.abort()
    stop_poll.timeout.connect(_abort_if_stopped)
    stop_poll.start()
    if not reply.isFinished():
        loop.exec()
    guard.stop()
    stop_poll.stop()
    reply.finished.disconnect(loop.quit)
    status = reply.attribute(_enum(QNetworkRequest, "Attribute", "HttpStatusCodeAttribute"))
    headers = [(bytes(n).decode("latin-1"), bytes(reply.rawHeader(n)).decode("latin-1")) for n in reply.rawHeaderList()]
    error = reply.error()
    result = Reply(
        ok=(error == _enum(QNetworkReply, "NetworkError", "NoError")),
        status=int(status) if status is not None else 0,
        headers=headers,
        body=bytes(reply.readAll()),
        error="stopped by the user" if stop_state["stopped"] else (reply.errorString() or "network error"),
        timed_out=(not stop_state["stopped"]) and error in (_enum(QNetworkReply, "NetworkError", "TimeoutError"), _enum(QNetworkReply, "NetworkError", "OperationCanceledError")),
    )
    reply.deleteLater()
    return result


def _qgis_send_following(method, url, header_items, data, timeout):
    """_qgis_hop plus redirects, done the way requests and curl do them: the same method, headers and body on a 307 or 308, a GET without
    body on 301, 302 and 303, and credential headers dropped when the target is a different site."""
    from urllib.parse import urljoin
    headers = [(str(k), str(v)) for k, v in header_items]
    for _hop in range(_MAX_REDIRECTS + 1):
        reply = _qgis_hop(method, url, headers, data, timeout)
        location = next((v for k, v in reply.headers if k.lower() == "location"), None)
        if reply.status not in _REDIRECT_CODES or not location:
            return reply
        target = urljoin(url, location)
        _check_scheme(target)
        other_site = _origin(target) != _origin(url)
        if other_site:
            headers = [(k, v) for k, v in headers if k.lower() not in _CREDENTIAL_HEADERS]
        headers = [(k, v) for k, v in headers if k.lower() != _HOST_HEADER]
        # Metadata only (no URL path, query, header or body): a later 401/403 report can then say whether a redirect was in the way.
        from .logger import log_event
        log_event("http_redirect", tag="Net", status=reply.status, from_host=_origin(url)[1], to_host=_origin(target)[1],
                  other_site=other_site)
        if reply.status in (301, 302, 303) and method == "POST":
            method, data = "GET", None
            headers = [(k, v) for k, v in headers if k.lower() not in ("content-type", "content-length")]
        url = target
    return Reply(ok=False, status=0, headers=[], body=b"", error=f"too many redirects (more than {_MAX_REDIRECTS})", timed_out=False)


def _qgis_send(method, url, header_items, data, timeout):
    """One request through QGIS's network stack. Never raises for an HTTP error status: the caller decides."""
    header_items = list(header_items)
    if _needs_own_redirects(method, header_items):
        return _qgis_send_following(method, url, header_items, data, timeout)
    return _qgis_send_blocking(method, url, header_items, data, timeout)


def _qgis_urlopen(req, timeout):
    url = req.full_url
    r = _qgis_send(req.get_method(), url, req.header_items(), req.data, timeout)
    if r.ok:
        return Response(r.body, r.status or 200, r.headers, url)
    if r.status >= 400:
        # Same exception urllib raises, with the body readable from it as callers expect.
        raise urllib.error.HTTPError(url, r.status, r.error, _Headers(r.headers), io.BytesIO(r.body))
    if r.timed_out:
        raise urllib.error.URLError(TimeoutError("timed out"))
    raise urllib.error.URLError(f"{r.error} (HTTP status {r.status or 'none'}, url {url})")


class _StreamResponse:
    """The body of a QNetworkReply, read incrementally on the thread that opened it (QgsNetworkAccessManager hands each thread its own
    manager, so the reply must be pumped there). Keeps the large-download behaviour of the old urllib path -- chunked reads, progress,
    cancellation between chunks -- while the request itself goes through QGIS's network stack (proxy, authentication, SSL settings).

    `timeout` is an idle limit: how long a wait for more data may last. QGIS applies its own transfer timeout to the request as well,
    so a stall can end sooner than this, never later."""

    READ_BUFFER = 1024 * 1024    # Qt stops reading the socket while this much is unread, so a big file never piles up in memory

    def __init__(self, reply, timeout, url):
        self._reply = reply
        self._timeout_ms = int(max(timeout or 30, 0.1) * 1000)
        self._url = url
        reply.setReadBufferSize(self.READ_BUFFER)
        self.status = self.code = 0
        self.headers = _Headers([])

    def _wait(self, until):
        """Runs the event loop until `until()` is true, the reply finishes, or the idle timeout passes with no new data."""
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        self._reply.readyRead.connect(loop.quit)
        self._reply.finished.connect(loop.quit)
        self._reply.metaDataChanged.connect(loop.quit)
        try:
            while not until() and not self._reply.isFinished():
                seen = self._reply.bytesAvailable()
                timer.start(self._timeout_ms)
                loop.exec()
                if not self._reply.isFinished() and self._reply.bytesAvailable() == seen and not until():
                    self._reply.abort()
                    raise TimeoutError("timed out waiting for data")
        finally:
            timer.stop()
            self._reply.readyRead.disconnect(loop.quit)
            self._reply.finished.disconnect(loop.quit)
            self._reply.metaDataChanged.disconnect(loop.quit)

    def _read_headers(self):
        self._wait(lambda: self._reply.attribute(_enum(QNetworkRequest, "Attribute", "HttpStatusCodeAttribute")) is not None
                   or self._reply.bytesAvailable() > 0)
        status = self._reply.attribute(_enum(QNetworkRequest, "Attribute", "HttpStatusCodeAttribute"))
        self.status = self.code = int(status) if status is not None else 0
        self.headers = _Headers([(bytes(n).decode("latin-1"), bytes(self._reply.rawHeader(n)).decode("latin-1"))
                                 for n in self._reply.rawHeaderList()])

    def read(self, amt=-1):
        if amt is None or amt < 0:
            # Everything: drain as it arrives, because Qt stops reading the socket while READ_BUFFER bytes are waiting unread.
            chunks = []
            while True:
                self._wait(lambda: self._reply.bytesAvailable() > 0)
                data = bytes(self._reply.readAll())
                if not data and self._reply.isFinished():
                    self._raise_if_cut_short()
                    return b"".join(chunks)
                chunks.append(data)
        want = min(amt, self.READ_BUFFER)
        self._wait(lambda: self._reply.bytesAvailable() >= want)
        data = bytes(self._reply.read(min(amt, self._reply.bytesAvailable())))
        if not data and amt > 0 and self._reply.isFinished():
            self._raise_if_cut_short()
        return data

    def _raise_if_cut_short(self):
        """A transfer that ended in an error after the status line must not look like a complete, shorter file (urllib raised
        IncompleteRead for this)."""
        reason = self.failure()
        if reason and self.status < 400:
            raise OSError(f"the download was cut short: {reason}")

    def failure(self):
        """The reply's error as a URLError reason, or None when it ended cleanly."""
        if self._reply.error() == _enum(QNetworkReply, "NetworkError", "NoError"):
            return None
        return self._reply.errorString() or "network error"

    def getcode(self):
        return self.status

    def geturl(self):
        return self._url

    def info(self):
        return self.headers

    def close(self):
        reply, self._reply = self._reply, None
        if reply is not None:
            reply.abort()
            reply.deleteLater()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


def _qgis_stream_open(req, timeout, follow=True):
    """GET through QgsNetworkAccessManager and return a _StreamResponse once the status line and headers are in.

    A redirect is handed to urllib instead (with the QGIS proxy, as every stream was before). A plain QgsNetworkAccessManager reply does
    not follow redirects itself, and following one by hand (even after draining the first reply instead of aborting it) left the second
    reply without a body in the QGIS 4.2.2 CI runs of 2026-10-11, so this is a stated limitation, not a solved one: the cause was not
    found. Large downloads that redirect (a model checkpoint from a release page) therefore use urllib; direct ones, such as Geofabrik's,
    use QGIS."""
    url = req.full_url
    qreq = QNetworkRequest(QUrl(url))
    for key, value in req.header_items():
        qreq.setRawHeader(QByteArray(str(key).encode("utf-8")), QByteArray(str(value).encode("utf-8")))
    reply = QgsNetworkAccessManager.instance().get(qreq)
    resp = _StreamResponse(reply, timeout, url)
    try:
        resp._read_headers()
    except TimeoutError:
        resp.close()
        raise urllib.error.URLError(TimeoutError("timed out")) from None
    # Status alone decides, not the Location header: the 2026-10-11 rc30 CI run returned the bare 302 to the caller on one run (the same
    # code passed on the run before), i.e. the headers were not all in yet when they were read. urllib re-requests and follows it properly.
    if resp.status in _REDIRECT_STATUSES and follow:
        resp.close()
        return _urllib_open(req, timeout)
    if resp.status >= 400:
        body = resp.read()
        resp.close()
        raise urllib.error.HTTPError(url, resp.status, f"HTTP {resp.status}", resp.headers, io.BytesIO(body))
    reason = resp.failure()
    if reason and resp.status == 0:
        resp.close()
        raise urllib.error.URLError(reason)
    return resp


class NetworkError(Exception):
    """No HTTP answer at all (DNS failure, refused connection, timeout). `timed_out` tells the two kinds apart."""

    def __init__(self, message, timed_out=False):
        super().__init__(message)
        self.timed_out = timed_out


def request(method, url, headers=None, data=None, timeout=30):
    """requests-style call for the AI provider clients: returns (status, headers, body) for ANY HTTP status, including 4xx and
    5xx, and raises NetworkError when there was no answer. Only valid when QGIS_NETWORK_AVAILABLE."""
    _check_scheme(url)
    if isinstance(data, str):
        data = data.encode("utf-8")
    r = _qgis_send(method.upper(), url, list((headers or {}).items()), data, timeout)
    if r.ok or r.status:
        return r.status or 200, r.headers, r.body
    raise NetworkError(r.error, timed_out=r.timed_out)


def _urllib_open(req, timeout):
    """The single audited urllib call: the scheme was checked by the caller, and the proxy QGIS is configured with is used."""
    handlers = []
    with contextlib.suppress(Exception):
        from .proxy import get_qgis_proxy_dict
        proxies = get_qgis_proxy_dict()
        if proxies:
            handlers.append(urllib.request.ProxyHandler(proxies))
    if handlers:
        return urllib.request.build_opener(*handlers).open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310  # nosec B310 (scheme checked by build_request/urlopen)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _qgis_buffered_hop(req, timeout, first_error):
    """One redirect-free GET of a redirected hop through QGIS's network stack, the whole body held in memory (<= MAX_DOWNLOAD_BYTES).

    Why it exists: a redirected hop is opened with urllib plus QGIS's proxy DICTIONARY (see _stream_open_once), which does not carry
    everything QGIS's own stack does: a PAC script or system proxy, proxy authentication, the SSL/CA setup of the Authentication
    database. On such a machine the first request (QGIS stack) works and the redirected one (urllib) fails, which is how a
    geoBoundaries download behind a proxy can fail after its API lookup succeeded (the unexplained 2026-10-13 tester failure; not
    reproduced here, so this is the best-supported explanation, not a confirmed one). The buffered QGIS hop (_qgis_hop) is used for
    sequential requests elsewhere in this module; only the STREAMING reply was seen to stall on a second request. Used only after
    urllib failed to connect, so a machine where urllib works keeps its streaming download unchanged."""
    reply = _qgis_hop("GET", req.full_url, list(req.header_items()), None, timeout)
    from .logger import log_event
    log_event("net_redirect_hop_via_qgis", tag="Net", urllib_error_class=type(first_error).__name__, ok=bool(reply.ok or reply.status),
              status=reply.status)
    if not reply.status:
        raise urllib.error.URLError(f"{first_error}; the QGIS network stack also failed: {reply.error}")
    if len(reply.body) > MAX_DOWNLOAD_BYTES:
        raise ResponseTooLargeError(f"the response is larger than {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB")
    if reply.status >= 400:
        raise urllib.error.HTTPError(req.full_url, reply.status, reply.error, _Headers(reply.headers), io.BytesIO(reply.body))
    return Response(reply.body, reply.status, reply.headers, req.full_url)


_PROXY_LIKE_STATUSES = (403, 407)


def _stream_open_once(req, timeout, qgis=True, qgis_fallback=False):
    """One streaming GET hop with redirects NOT followed: a 3xx comes back as a response whose .status is 3xx (QGIS path) or as the
    HTTPError urllib raises for it (fallback path, same .status and .headers).

    `qgis=False` forces urllib (with the QGIS proxy). Used for the hops AFTER a redirect: the 2026-10-11 CI run of
    tests/test_net_live.py showed the same fault _qgis_stream_open documents, a second streamed QGIS reply opened after the first was
    closed never delivers its body ("timed out waiting for data"), cause still unknown. So only the first request of a download uses
    QGIS's stack; a redirected hop uses urllib, after its target has been vetted."""
    if QGIS_NETWORK_AVAILABLE and qgis:
        try:
            return _qgis_stream_open(req, timeout, follow=False)
        except urllib.error.URLError as e:
            if 'Protocol ""' not in str(e.reason):
                raise
    handlers = [_NoRedirect()]
    with contextlib.suppress(Exception):
        from .proxy import get_qgis_proxy_dict
        proxies = get_qgis_proxy_dict()
        if proxies:
            handlers.append(urllib.request.ProxyHandler(proxies))
    try:
        return urllib.request.build_opener(*handlers).open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in _REDIRECT_STATUSES:
            return e
        # A proxy that urllib cannot authenticate to (or a gateway that does not know the CDN host) answers with its own 403, 407 or
        # 5xx page, not a connection error: field report 2026-10-26, Yemen ADM1: HDX "403 Forbidden" and geoBoundaries "500 Domain Not
        # Found" on the redirected download hop, after the first request (QGIS stack) had worked. Retry that status once through the
        # QGIS stack; if QGIS gets the same status it is raised instead (the server really refuses), so a genuine 403 costs one request.
        if qgis_fallback and QGIS_NETWORK_AVAILABLE and (e.code in _PROXY_LIKE_STATUSES or e.code >= 500):
            e.close()
            return _qgis_buffered_hop(req, timeout, e)
        raise
    except OSError as e:          # URLError, timeouts, SSL and proxy failures; an HTTP status was handled above
        if qgis_fallback and QGIS_NETWORK_AVAILABLE:
            return _qgis_buffered_hop(req, timeout, e)
        raise


def stream_following(request, timeout=30, check_url=None):
    """Streaming GET that follows redirects here, one hop at a time, so every target can be vetted before it is requested.

    `check_url(url)` returns a reason string to refuse a redirect target (the caller's SSRF check), or None. Used for LLM-named URLs:
    a URL that passed the check at call time can 302 to an internal address, and a client that follows redirects on its own would
    fetch it. Credential headers are dropped when the target is another site, as in _qgis_send_following. GET only."""
    from urllib.parse import urljoin
    req = _as_request(request)
    for hop in range(_MAX_REDIRECTS + 1):
        resp = _stream_open_once(req, timeout, qgis=(hop == 0), qgis_fallback=(hop > 0))
        if resp.status not in _REDIRECT_STATUSES:
            return resp
        location = resp.headers.get("Location")
        resp.close()
        if not location and hop == 0 and QGIS_NETWORK_AVAILABLE:
            # The status line can arrive before the other headers on a streamed QGIS reply (the rc30 CI run saw a bare 302; the first run of
            # the redirect live test on the rc35 branch saw it again, one run in two). Ask once more through urllib, which reads the headers whole.
            resp = _stream_open_once(req, timeout, qgis=False)
            if resp.status not in _REDIRECT_STATUSES:
                return resp
            location = resp.headers.get("Location")
            resp.close()
        if not location:
            raise urllib.error.URLError(f"HTTP {resp.status} redirect without a Location header")
        target = urljoin(req.full_url, location)
        _check_scheme(target)
        reason = check_url(target) if check_url else None
        if reason:
            raise urllib.error.URLError(f"Redirect blocked: {reason}")
        other_site = _origin(target) != _origin(req.full_url)
        from .logger import log_event
        log_event("http_redirect", tag="Net", status=resp.status, from_host=_origin(req.full_url)[1], to_host=_origin(target)[1],
                  other_site=other_site)
        headers = {k: v for k, v in req.header_items()
                   if k.lower() != _HOST_HEADER and not (other_site and k.lower() in _CREDENTIAL_HEADERS)}
        req = build_request(target, headers=headers)
    raise urllib.error.URLError(f"too many redirects (more than {_MAX_REDIRECTS})")


def urlopen(request, timeout=30, stream=False):
    """Drop-in for urllib.request.urlopen. `stream=True` for a large body that is read in chunks and written to disk."""
    try:
        req = _as_request(request)
    except ValueError:
        # Not a URL at all (e.g. a bare word). Let urllib raise its own error for it, as before.
        return _urllib_open(request, timeout)
    _check_scheme(req.full_url)
    if QGIS_NETWORK_AVAILABLE:
        try:
            return _qgis_stream_open(req, timeout) if stream else _qgis_urlopen(req, timeout)
        except urllib.error.URLError as e:
            if 'Protocol ""' not in str(e.reason):
                raise
            return _urllib_open(req, timeout)
    return _urllib_open(req, timeout)
