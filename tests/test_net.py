# -*- coding: utf-8 -*-
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
