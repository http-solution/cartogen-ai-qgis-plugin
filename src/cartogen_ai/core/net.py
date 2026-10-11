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
    if not reply.isFinished():
        loop.exec()
    guard.stop()
    reply.finished.disconnect(loop.quit)
    status = reply.attribute(_enum(QNetworkRequest, "Attribute", "HttpStatusCodeAttribute"))
    headers = [(bytes(n).decode("latin-1"), bytes(reply.rawHeader(n)).decode("latin-1")) for n in reply.rawHeaderList()]
    error = reply.error()
    result = Reply(
        ok=(error == _enum(QNetworkReply, "NetworkError", "NoError")),
        status=int(status) if status is not None else 0,
        headers=headers,
        body=bytes(reply.readAll()),
        error=reply.errorString() or "network error",
        timed_out=error in (_enum(QNetworkReply, "NetworkError", "TimeoutError"), _enum(QNetworkReply, "NetworkError", "OperationCanceledError")),
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
        if _origin(target) != _origin(url):
            headers = [(k, v) for k, v in headers if k.lower() not in _CREDENTIAL_HEADERS]
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


def _qgis_stream_open(req, timeout):
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
    if resp.status in _REDIRECT_STATUSES:
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
