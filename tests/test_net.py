"""core/net.py: the urllib-compatible wrapper over QGIS's network stack (task #71). These run without QGIS, so they cover the
scheme check, the urllib fallback and the response object; the QgsBlockingNetworkRequest path is in test_net_live.py."""
import io
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from cartogen_ai.core import net


class TestNet(unittest.TestCase):
    def test_non_http_schemes_are_refused(self):
        for url in ("file:///etc/passwd", "ftp://example.org/x", "gopher://example.org/"):
            with self.assertRaises(urllib.error.URLError):
                net.urlopen(urllib.request.Request(url), timeout=1)

    def test_https_goes_to_urllib_when_there_is_no_qgis(self):
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", False), \
                patch("urllib.request.urlopen", return_value="resp") as m:
            self.assertEqual(net.urlopen(urllib.request.Request("https://example.org/a"), timeout=5), "resp")
        self.assertEqual(m.call_args.kwargs["timeout"], 5)

    def test_stream_stays_on_urllib_even_with_qgis(self):
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", True), \
                patch.object(net, "_qgis_urlopen", side_effect=AssertionError("buffered path used")), \
                patch("urllib.request.urlopen", return_value="resp"):
            self.assertEqual(net.urlopen(urllib.request.Request("https://example.org/big"), timeout=5, stream=True), "resp")

    def test_non_url_is_left_to_urllib(self):
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", False), patch("urllib.request.urlopen", return_value="r"):
            self.assertEqual(net.urlopen("req", timeout=1), "r")

    def test_response_behaves_like_urllibs(self):
        with net.Response(b'{"a": 1}', 200, [("Content-Length", "8")], "https://x/") as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.headers.get("content-length"), "8")
            self.assertEqual(r.read(), b'{"a": 1}')
        self.assertIsNone(net.Response(b"", 200, [], "u").headers.get("missing"))

    def test_http_error_body_is_readable(self):
        e = urllib.error.HTTPError("u", 404, "nf", net._Headers([]), io.BytesIO(b"gone"))
        self.addCleanup(e.close)
        self.assertEqual(e.read(), b"gone")


if __name__ == "__main__":
    unittest.main()


class TestProviderTransport(unittest.TestCase):
    """infrastructure/providers/base.py: hosted providers use QGIS's network stack when it exists (task #71 phase 2)."""

    def setUp(self):
        from cartogen_ai.infrastructure.providers import base
        self.base = base

    def test_post_uses_qgis_network_for_hosted_providers(self):
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", True), \
                patch.object(net, "request", return_value=(200, [("Content-Type", "application/json")], b'{"ok": true}')) as m:
            r = self.base.post_with_retry("https://api.example.org/v1", {"Authorization": "Bearer k"}, '{"a": 1}', timeout=30)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True})
        self.assertEqual(m.call_args.args[:2], ("POST", "https://api.example.org/v1"))
        self.assertEqual(m.call_args.kwargs["data"], '{"a": 1}')

    def test_local_provider_stays_on_requests(self):
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", True), \
                patch.object(net, "request", side_effect=AssertionError("QGIS path used for a local server")), \
                patch.object(self.base, "requests") as req:
            req.post.return_value = self.base.QgisResponse(200, [], b"{}", "u")
            r = self.base.post_with_retry("http://localhost:11434/x", {}, "{}", 180, local=True)
        self.assertIs(r, req.post.return_value)

    def test_without_qgis_requests_is_used_as_before(self):
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", False), patch.object(self.base, "requests") as req:
            req.post.return_value = self.base.QgisResponse(200, [], b"{}", "u")
            r = self.base.post_with_retry("https://api.example.org/x", {}, "{}", 30)
        self.assertIs(r, req.post.return_value)

    def test_http_error_status_raises_the_providers_httperror_with_the_body(self):
        resp = self.base.QgisResponse(401, [], b"bad key sk-abc", "https://x/")
        with self.assertRaises(self.base.HTTPError) as cm:
            resp.raise_for_status()
        self.assertIs(cm.exception.response, resp)
        self.assertNotIn("sk-abc", self.base.format_http_error("X", cm.exception))   # 401 body stays withheld

    def test_no_answer_becomes_connection_or_timeout_error_and_is_retried(self):
        calls = []

        def fake(*a, **k):
            calls.append(1)
            raise net.NetworkError("refused", timed_out=len(calls) == 1)

        with patch.object(net, "QGIS_NETWORK_AVAILABLE", True), patch.object(net, "request", side_effect=fake), \
                patch.object(self.base.time, "sleep"), self.assertRaises(self.base.RequestException):
            self.base.get_with_retry("https://x/", {}, 5, max_retries=1)
        self.assertEqual(len(calls), 2)

    def test_503_then_200_retries(self):
        seq = [(503, [], b"busy"), (200, [], b"{}")]
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", True), patch.object(net, "request", side_effect=seq), \
                patch.object(self.base.time, "sleep"):
            self.assertEqual(self.base.get_with_retry("https://x/", {}, 5).status_code, 200)


class TestSizeCeilings(unittest.TestCase):
    """2026-10-11 audit: remote answers were read with an unbounded .read(), and gzip/zip data was expanded without a ceiling,
    so one hostile or broken data service could exhaust memory. The helpers refuse instead of holding it all."""

    def test_read_capped_returns_a_body_within_the_limit(self):
        self.assertEqual(net.read_capped(io.BytesIO(b"abc"), limit=3), b"abc")

    def test_read_capped_refuses_one_byte_over(self):
        with self.assertRaises(net.ResponseTooLargeError):
            net.read_capped(io.BytesIO(b"abcd"), limit=3)

    def test_gunzip_capped_expands_normal_data(self):
        import gzip
        self.assertEqual(net.gunzip_capped(gzip.compress(b"x" * 1000), limit=2000), b"x" * 1000)

    def test_gunzip_capped_refuses_a_bomb_without_inflating_it(self):
        import gzip
        bomb = gzip.compress(b"\0" * (5 * 1024 * 1024))   # ~5 KB on the wire, 5 MB expanded
        with self.assertRaises(net.ResponseTooLargeError):
            net.gunzip_capped(bomb, limit=1024 * 1024)

    def test_gunzip_capped_reports_a_non_gzip_body_as_oserror(self):
        with self.assertRaises(OSError):
            net.gunzip_capped(b"<html>not gzip</html>")

    def test_zip_member_capped_checks_the_declared_size_first(self):
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("big.geojson", b"\0" * (2 * 1024 * 1024))
            z.writestr("small.geojson", b"{}")
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as z:
            self.assertEqual(net.zip_member_capped(z, "small.geojson", limit=1024), b"{}")
            with self.assertRaises(net.ResponseTooLargeError):
                net.zip_member_capped(z, "big.geojson", limit=1024 * 1024)
