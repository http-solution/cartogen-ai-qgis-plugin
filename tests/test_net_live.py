# -*- coding: utf-8 -*-
"""Live-QGIS tests for core/net.py (task #71): urlopen goes through QgsBlockingNetworkRequest and behaves like urllib's, on the
main thread and on a worker thread. Talks to a throwaway HTTP server on 127.0.0.1. Written without hand-testing; the Docker QGIS
run is the only execution evidence."""
import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsBlockingNetworkRequest  # noqa: F401
    LIVE = True
except ImportError:
    LIVE = False


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body=b"", headers=None):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        if self.path == "/ok":
            self._send(200, json.dumps({"ua": self.headers.get("User-Agent")}).encode(), {"Content-Type": "application/json"})
        elif self.path == "/missing":
            self._send(404, b"no such thing")
        elif self.path == "/busy":
            self._send(503, b"later")
        elif self.path == "/redirect":
            self._send(302, b"", {"Location": "/ok"})
        elif self.path == "/slow":
            time.sleep(4)
            self._send(200, b"late")
        else:
            self._send(500, b"?")

    def do_HEAD(self):
        self._send(200, b"x" * 321)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self._send(200, self.rfile.read(n))


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestNetLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _open(self, path, **kw):
        from cartogen_ai.core import net
        headers = kw.pop("headers", {})
        req = urllib.request.Request(self.base + path, headers=headers, **kw)
        return net.urlopen(req, timeout=10)

    def test_uses_the_qgis_path_here(self):
        from cartogen_ai.core import net
        self.assertTrue(net.QGIS_NETWORK_AVAILABLE)

    def test_get_returns_body_status_and_sends_headers(self):
        with self._open("/ok", headers={"User-Agent": "CartogenTest"}) as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(json.loads(r.read().decode())["ua"], "CartogenTest")

    def test_head_gives_content_length(self):
        with self._open("/ok", method="HEAD") as r:
            self.assertEqual(r.headers.get("Content-Length"), "321")

    def test_post_sends_the_body(self):
        with self._open("/echo", data=b"hello", method="POST") as r:
            self.assertEqual(r.read(), b"hello")

    def test_404_is_an_httperror_with_a_readable_body(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._open("/missing")
        self.assertEqual(cm.exception.code, 404)
        self.assertEqual(cm.exception.read(), b"no such thing")
        cm.exception.close()

    def test_503_is_retried_by_the_retry_helper_then_raised(self):
        from cartogen_ai.core.agent.tools._urllib_retry import urlopen_with_retry
        req = urllib.request.Request(self.base + "/busy")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urlopen_with_retry(req, timeout=5, max_retries=1, backoff_seconds=0.01)
        self.assertEqual(cm.exception.code, 503)
        cm.exception.close()

    def test_redirect_is_followed(self):
        with self._open("/redirect") as r:
            self.assertEqual(r.status, 200)

    def test_timeout_is_a_urlerror(self):
        from cartogen_ai.core import net
        with self.assertRaises(urllib.error.URLError):
            net.urlopen(urllib.request.Request(self.base + "/slow"), timeout=1)

    def test_refused_connection_is_a_urlerror(self):
        from cartogen_ai.core import net
        with self.assertRaises(urllib.error.URLError):
            net.urlopen(urllib.request.Request("http://127.0.0.1:9/"), timeout=3)

    def test_works_on_a_worker_thread(self):
        out = {}

        def work():
            try:
                with self._open("/ok", headers={"User-Agent": "worker"}) as r:
                    out["ua"] = json.loads(r.read().decode())["ua"]
            except Exception as e:  # pragma: no cover - reported through the assertion below
                out["error"] = repr(e)

        t = threading.Thread(target=work)
        t.start()
        t.join(30)
        self.assertEqual(out, {"ua": "worker"})

    def test_stream_still_reads_in_chunks(self):
        from cartogen_ai.core import net
        with net.urlopen(urllib.request.Request(self.base + "/ok"), timeout=5, stream=True) as r:
            self.assertEqual(r.status, 200)
            self.assertTrue(r.read(4))


if __name__ == "__main__":
    unittest.main()
