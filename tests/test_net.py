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

    def test_stream_uses_the_incremental_qgis_reader_not_the_buffered_one_when_qgis_is_there(self):
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", True), \
                patch.object(net, "_qgis_urlopen", side_effect=AssertionError("buffered path used")), \
                patch.object(net, "_qgis_stream_open", create=True, return_value="stream") as opener, \
                patch("urllib.request.urlopen", side_effect=AssertionError("urllib used")):
            self.assertEqual(net.urlopen(urllib.request.Request("https://example.org/big"), timeout=5, stream=True), "stream")
        self.assertEqual(opener.call_args.args[1], 5)

    def test_stream_falls_back_to_urllib_only_for_the_relative_redirect_case(self):
        err = urllib.error.URLError('Protocol "" is unknown')
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", True), \
                patch.object(net, "_qgis_stream_open", create=True, side_effect=err), \
                patch("urllib.request.urlopen", return_value="resp"):
            self.assertEqual(net.urlopen(urllib.request.Request("https://example.org/big"), timeout=5, stream=True), "resp")
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", True), \
                patch.object(net, "_qgis_stream_open", create=True, side_effect=urllib.error.URLError("refused")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("urllib used")), \
                self.assertRaises(urllib.error.URLError):
            net.urlopen(urllib.request.Request("https://example.org/big"), timeout=5, stream=True)

    def test_stream_without_qgis_stays_on_urllib(self):
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", False), patch("urllib.request.urlopen", return_value="resp"):
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


class TestRedirectedHopFallsBackToTheQgisStack(unittest.TestCase):
    """A redirected hop is opened with urllib; where that cannot connect (a PAC / authenticated / system proxy it does not know about)
    the hop is retried through QGIS's own stack. Fakes only: the real stack is exercised by tests/test_net_live.py in CI."""

    class _Redirect:
        status = 302
        headers = net._Headers([("Location", "https://files.example.org/data.geojson")])

        def close(self):
            pass

    def _run(self, urllib_error, qgis_reply):
        opener = unittest.mock.MagicMock()
        opener.open.side_effect = urllib_error
        reply = unittest.mock.MagicMock(return_value=qgis_reply)
        with unittest.mock.patch.object(net, "QGIS_NETWORK_AVAILABLE", True), \
             unittest.mock.patch.object(net, "_qgis_stream_open", return_value=self._Redirect()), \
             unittest.mock.patch.object(net.urllib.request, "build_opener", return_value=opener), \
             unittest.mock.patch.object(net, "_qgis_hop", reply):
            return net.stream_following("https://api.example.org/x", timeout=5), reply

    def test_a_connection_failure_on_the_redirected_hop_is_retried_through_qgis(self):
        ok = net.Reply(ok=True, status=200, headers=[("Content-Type", "application/json")], body=b"{}", error="", timed_out=False)
        resp, hop = self._run(net.urllib.error.URLError("proxy needs authentication"), ok)
        self.assertEqual(resp.read(), b"{}")
        self.assertEqual(hop.call_args.args[1], "https://files.example.org/data.geojson")

    def test_a_proxy_like_status_from_urllib_is_retried_through_qgis(self):
        # 2026-10-26 field report: HDX 403 and geoBoundaries 500 on the redirected download hop, first request fine.
        ok = net.Reply(ok=True, status=200, headers=[], body=b"zip", error="", timed_out=False)
        for code in (403, 407, 500, 502):
            with self.subTest(code=code):
                err = net.urllib.error.HTTPError("https://files.example.org/data.geojson", code, "x", net._Headers([]), io.BytesIO(b""))
                resp, hop = self._run(err, ok)
                self.assertEqual(resp.read(), b"zip")
                self.assertEqual(hop.call_count, 1)

    def test_when_qgis_gets_the_same_refusal_that_status_is_raised(self):
        err = net.urllib.error.HTTPError("https://files.example.org/data.geojson", 403, "Forbidden", net._Headers([]), io.BytesIO(b""))
        denied = net.Reply(ok=False, status=403, headers=[], body=b"no", error="Forbidden", timed_out=False)
        with self.assertRaises(net.urllib.error.HTTPError) as cm:
            self._run(err, denied)
        self.assertEqual(cm.exception.code, 403)

    def test_an_ordinary_missing_file_is_not_retried(self):
        for code in (400, 404, 410):
            with self.subTest(code=code):
                err = net.urllib.error.HTTPError("https://files.example.org/data.geojson", code, "x", net._Headers([]), io.BytesIO(b""))
                with self.assertRaises(net.urllib.error.HTTPError) as cm:
                    self._run(err, None)
                self.assertEqual(cm.exception.code, code)

    def test_when_both_stacks_fail_the_message_names_both(self):
        dead = net.Reply(ok=False, status=0, headers=[], body=b"", error="Host files.example.org not found", timed_out=False)
        with self.assertRaises(net.urllib.error.URLError) as cm:
            self._run(net.urllib.error.URLError("proxy refused"), dead)
        self.assertIn("proxy refused", str(cm.exception))
        self.assertIn("QGIS network stack also failed", str(cm.exception))

    def test_a_status_from_the_qgis_hop_is_raised_as_an_http_error(self):
        denied = net.Reply(ok=False, status=404, headers=[], body=b"nope", error="Not Found", timed_out=False)
        with self.assertRaises(net.urllib.error.HTTPError) as cm:
            self._run(net.urllib.error.URLError("proxy refused"), denied)
        self.assertEqual(cm.exception.code, 404)

    def test_outside_qgis_there_is_no_fallback(self):
        opener = unittest.mock.MagicMock()
        opener.open.side_effect = net.urllib.error.URLError("refused")
        with unittest.mock.patch.object(net, "QGIS_NETWORK_AVAILABLE", False), \
             unittest.mock.patch.object(net.urllib.request, "build_opener", return_value=opener), \
             self.assertRaises(net.urllib.error.URLError):
            net._stream_open_once(net.build_request("https://x.example.org/"), 5, qgis=False, qgis_fallback=True)


class TestRedirectDoesNotCarryTheHostHeader(unittest.TestCase):
    """2026-10-26, Yemen ADM1: HDX redirects to a presigned S3 link; the first request's Host header was copied onto the second request, S3
    took the bucket from it and answered 403 SignatureDoesNotMatch. curl got 200 for the same link."""

    class _Redirect:
        status = 302
        headers = net._Headers([("Location", "https://s3.example.org/bucket/file.zip?Signature=abc%3D&Expires=1")])

        def close(self):
            pass

    class _Ok:
        status = 200
        headers = net._Headers([])

        def close(self):
            pass

    def test_host_is_not_copied_but_the_other_headers_are(self):
        seen = []

        def fake(req, timeout, qgis=True, qgis_fallback=False):
            seen.append(req)
            return self._Redirect() if len(seen) == 1 else self._Ok()
        first = net.build_request("https://data.example.org/download/file.zip", headers={"User-Agent": "Cartogen-test", "Host": "data.example.org"})
        first.add_unredirected_header("Host", "data.example.org")      # what urllib adds when it opens a request
        with unittest.mock.patch.object(net, "_stream_open_once", side_effect=fake):
            net.stream_following(first, timeout=5)
        self.assertEqual(len(seen), 2)
        names = [k.lower() for k, _v in seen[1].header_items()]
        self.assertNotIn("host", names)
        self.assertIn("user-agent", names)

    def test_the_signed_query_string_reaches_the_second_request_unchanged(self):
        seen = []

        def fake(req, timeout, qgis=True, qgis_fallback=False):
            seen.append(req)
            return self._Redirect() if len(seen) == 1 else self._Ok()
        with unittest.mock.patch.object(net, "_stream_open_once", side_effect=fake):
            net.stream_following("https://data.example.org/download/file.zip", timeout=5)
        self.assertEqual(seen[1].full_url, "https://s3.example.org/bucket/file.zip?Signature=abc%3D&Expires=1")


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

    def test_the_kill_switch_sends_hosted_requests_with_requests_again(self):
        # 2026-10-11 field report: Gemini answered 403 to the QGIS-stack request while the same key worked elsewhere. Turning
        # cartogen_ai/hosted_requests_via_qgis off must restore the pre-rc28 sender without a new release.
        with patch.object(net, "QGIS_NETWORK_AVAILABLE", True), \
                patch.object(self.base, "_qgis_network_enabled", return_value=False), \
                patch.object(net, "request", side_effect=AssertionError("QGIS path used with the switch off")), \
                patch.object(self.base, "requests") as req:
            req.post.return_value = self.base.QgisResponse(200, [], b"{}", "u")
            r = self.base.post_with_retry("https://api.example.org/v1", {}, "{}", 30)
        self.assertEqual(r.status_code, 200)
        req.post.assert_called_once()

    def test_the_switch_defaults_to_on_without_qgis(self):
        self.assertTrue(self.base._qgis_network_enabled())

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


class TestStreamFollowing(unittest.TestCase):
    """net.stream_following vets every redirect target before it is requested (urllib fallback path; the QGIS path is covered by
    tests/test_net_live.py in CI)."""

    def _server(self, routes):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                status, location, body = routes.get(self.path, (404, None, b"missing"))
                self.send_response(status)
                if location:
                    self.send_header("Location", location)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def test_follows_a_relative_redirect(self):
        base = self._server({"/a": (302, "/b", b""), "/b": (200, None, b"ok")})
        with net.stream_following(base + "/a", timeout=5) as r:
            self.assertEqual(r.read(), b"ok")

    def test_refuses_a_target_the_check_rejects(self):
        base = self._server({"/a": (302, "/secret", b""), "/secret": (200, None, b"internal")})
        with self.assertRaises(net.urllib.error.URLError) as cm:
            net.stream_following(base + "/a", timeout=5, check_url=lambda u: "non-public" if "secret" in u else None)
        self.assertIn("Redirect blocked", str(cm.exception))

    def test_a_redirect_loop_ends(self):
        base = self._server({"/a": (302, "/a", b"")})
        with self.assertRaises(net.urllib.error.URLError) as cm:
            net.stream_following(base + "/a", timeout=5)
        self.assertIn("too many redirects", str(cm.exception))
