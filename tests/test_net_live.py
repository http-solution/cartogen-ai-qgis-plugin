"""Live-QGIS tests for core/net.py (task #71): urlopen goes through QgsBlockingNetworkRequest and behaves like urllib's, on the
main thread and on a worker thread. Talks to a throwaway HTTP server on 127.0.0.1. Written without hand-testing; the Docker QGIS
run is the only execution evidence."""
import json
import os
import threading
import time
import unittest
from typing import ClassVar
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
        elif self.path == "/chat":
            self._send(200, json.dumps({"method": "GET", "auth": self.headers.get("Authorization")}).encode(), {"Content-Type": "application/json"})
        elif self.path == "/missing":
            self._send(404, b"no such thing")
        elif self.path == "/unauthorized":
            self._send(401, b"Incorrect API key provided: sk-ab***yz")
        elif self.path == "/busy":
            self._send(503, b"later")
        elif self.path == "/redirect":
            self._send(302, b"", {"Location": "/ok"})            # relative, as RFC 7231 allows
        elif self.path == "/redirect-abs":
            self._send(302, b"", {"Location": "http://{}/ok".format(self.headers.get("Host"))})
        elif self.path == "/slow":
            time.sleep(4)
            self._send(200, b"late")
        elif self.path == "/big":
            self._send(200, bytes(range(256)) * 12288)                      # 3 MiB with a known pattern
        elif self.path == "/stall":
            self.send_response(200)
            self.send_header("Content-Length", "10")
            self.end_headers()
            self.wfile.flush()
            time.sleep(5)                                                   # headers now, body only after the client gave up
            with __import__("contextlib").suppress(OSError):
                self.wfile.write(b"0123456789")
        elif self.path == "/cut":
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            self.wfile.write(b"x" * 100)                                    # promises 1000, sends 100, hangs up
            self.wfile.flush()
            self.close_connection = True
        else:
            self._send(500, b"?")

    def do_HEAD(self):
        self._send(200, b"x" * 321)

    seen: ClassVar[list] = []     # (path, Authorization, body length) of every POST the server received, to explain a failure

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n)
        type(self).seen.append((self.path, self.headers.get("Authorization"), len(body)))
        if self.path == "/hop-307-loop":
            self._send(307, b"", {"Location": "http://{}/hop-307-loop".format(self.headers.get("Host"))})
        elif self.path.startswith("/hop-"):
            self._send(int(self.path[5:]), b"", {"Location": "http://{}/chat".format(self.headers.get("Host"))})
        elif self.path.startswith("/hopr-"):
            self._send(int(self.path[6:]), b"", {"Location": "/chat"})                       # relative target
        elif self.path.startswith("/hopx-"):
            port = self.headers.get("Host").split(":")[1]
            self._send(int(self.path[6:]), b"", {"Location": f"http://localhost:{port}/chat"})   # same machine, different site name
        elif self.path == "/chat":
            self._send(200, json.dumps({"auth": self.headers.get("Authorization"), "ctype": self.headers.get("Content-Type"),
                                        "body": json.loads(body.decode())}).encode(), {"Content-Type": "application/json"})
        else:
            self._send(200, body)


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestNetLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
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

    def test_get_returns_body_and_status_and_qgis_sets_the_user_agent(self):
        with self._open("/ok", headers={"User-Agent": "CartogenTest"}) as r:
            self.assertEqual(r.status, 200)
            # QgsNetworkAccessManager replaces the caller's User-Agent with its own.
            self.assertIn("QGIS", json.loads(r.read().decode())["ua"])

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

    def test_relative_and_absolute_redirects_are_followed(self):
        for path in ("/redirect", "/redirect-abs"):
            with self._open(path) as r:
                self.assertEqual(r.status, 200, path)
                self.assertIn("ua", json.loads(r.read().decode()))

    def test_stream_following_vets_each_redirect_target_on_the_qgis_path(self):
        # Replaces urllib's build_opener for LLM-named URLs (tracker task 71). Not run outside QGIS: CI live job only.
        from cartogen_ai.core import net
        with net.stream_following(self.base + "/redirect", timeout=10) as r:
            self.assertEqual(r.status, 200)
            self.assertIn("ua", json.loads(r.read().decode()))
        with self.assertRaises(urllib.error.URLError) as cm:
            net.stream_following(self.base + "/redirect", timeout=10, check_url=lambda u: "non-public" if u.endswith("/ok") else None)
        self.assertIn("Redirect blocked", str(cm.exception))

    def test_refused_connection_is_a_urlerror(self):
        from cartogen_ai.core import net
        with self.assertRaises(urllib.error.URLError):
            net.urlopen(urllib.request.Request("http://127.0.0.1:9/"), timeout=3)

    def test_works_on_a_worker_thread(self):
        out = {}

        def work():
            try:
                with self._open("/ok") as r:
                    out["status"] = r.status
                    out["has_ua"] = "ua" in json.loads(r.read().decode())
            except Exception as e:  # pragma: no cover - reported through the assertion below
                out["error"] = repr(e)

        t = threading.Thread(target=work)
        t.start()
        t.join(30)
        self.assertEqual(out, {"status": 200, "has_ua": True})

    def test_provider_post_sends_auth_and_json_and_parses_the_reply(self):
        from cartogen_ai.infrastructure.providers.base import post_with_retry
        r = post_with_retry(self.base + "/chat", {"Authorization": "Bearer k", "Content-Type": "application/json"},
                            json.dumps({"q": 1}), timeout=10)
        r.raise_for_status()
        self.assertEqual(r.json(), {"auth": "Bearer k", "ctype": "application/json", "body": {"q": 1}})

    def test_provider_401_raises_httperror_with_a_redacted_message(self):
        from cartogen_ai.infrastructure.providers.base import HTTPError, format_http_error, get_with_retry
        r = get_with_retry(self.base + "/unauthorized", {}, timeout=10)
        self.assertEqual(r.status_code, 401)
        with self.assertRaises(HTTPError) as cm:
            r.raise_for_status()
        self.assertNotIn("sk-ab", format_http_error("Provider error", cm.exception))

    def test_provider_connection_refused_is_a_requests_style_error(self):
        from cartogen_ai.infrastructure.providers.base import RequestException, get_with_retry
        with self.assertRaises(RequestException):
            get_with_retry("http://127.0.0.1:9/", {}, timeout=3, max_retries=0)

    def test_stream_still_reads_in_chunks(self):
        from cartogen_ai.core import net
        with net.urlopen(urllib.request.Request(self.base + "/ok"), timeout=5, stream=True) as r:
            self.assertEqual(r.status, 200)
            self.assertTrue(r.read(4))

    # --- streamed downloads (the QGIS-native incremental path that replaced urllib for large bodies) ---

    def _stream(self, path, timeout=10):
        from cartogen_ai.core import net
        return net.urlopen(urllib.request.Request(self.base + path), timeout=timeout, stream=True)

    def test_stream_reads_a_large_body_in_chunks_with_headers(self):
        expected = bytes(range(256)) * 12288
        got = bytearray()
        with self._stream("/big") as r:
            self.assertEqual(r.status, 200)
            self.assertEqual(r.headers.get("Content-Length"), str(len(expected)))
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                got.extend(chunk)
        self.assertEqual(bytes(got), expected)

    def test_stream_read_all_returns_everything(self):
        with self._stream("/big") as r:
            self.assertEqual(len(r.read()), 3 * 1024 * 1024)

    def test_stream_404_is_an_httperror_with_a_body(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._stream("/missing")
        self.assertEqual(cm.exception.code, 404)
        self.assertEqual(cm.exception.read(), b"no such thing")
        cm.exception.close()

    def test_stream_refused_connection_is_a_urlerror(self):
        from cartogen_ai.core import net
        with self.assertRaises(urllib.error.URLError):
            net.urlopen(urllib.request.Request("http://127.0.0.1:9/"), timeout=3, stream=True)

    def test_stream_idle_timeout_is_enforced_exactly(self):
        started = time.monotonic()
        with self._stream("/stall", timeout=1) as r, self.assertRaises(OSError):
            r.read(10)
        self.assertLess(time.monotonic() - started, 4.5)    # the server sleeps 5 s; QGIS's own timeout is longer than that

    def test_stream_cut_short_is_an_error_not_a_short_file(self):
        with self._stream("/cut") as r, self.assertRaises(OSError):
            while r.read(50):
                pass

    def test_stream_works_on_a_worker_thread(self):
        out = {}

        def work():
            try:
                with self._stream("/big") as r:
                    out["n"] = len(r.read())
            except Exception as e:  # pragma: no cover - reported through the assertion below
                out["error"] = repr(e)

        t = threading.Thread(target=work)
        t.start()
        t.join(60)
        self.assertEqual(out, {"n": 3 * 1024 * 1024})

    def test_the_hosted_request_kill_switch_reads_the_real_setting(self):
        from qgis.core import QgsSettings
        from cartogen_ai.infrastructure.providers import base
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_HOSTED_VIA_QGIS_NETWORK
        settings = QgsSettings()
        self.addCleanup(settings.remove, SETTINGS_HOSTED_VIA_QGIS_NETWORK)
        settings.remove(SETTINGS_HOSTED_VIA_QGIS_NETWORK)
        self.assertTrue(base._qgis_network_enabled(), "on by default")
        settings.setValue(SETTINGS_HOSTED_VIA_QGIS_NETWORK, False)
        self.assertFalse(base._qgis_network_enabled())
        self.assertFalse(base._use_qgis_network(False), "off means requests, even inside QGIS")

    def test_a_post_keeps_its_key_and_body_across_a_307_or_308_redirect(self):
        """2026-10-11 field report: Gemini answered 403 to the QGIS-stack POST. QgsBlockingNetworkRequest follows a redirect by building
        a new QNetworkRequest from the target URL alone (src/core/network/qgsblockingnetworkrequest.cpp, replyFinished), which would drop
        Authorization and Content-Type and re-send a body that was already read. A hosted-AI call that is redirected once (a proxy, a
        gateway) would then reach the provider without its key. This pins what must hold: the key and the whole body arrive."""
        from cartogen_ai.core import net
        payload = json.dumps({"model": "m", "messages": [{"role": "user", "content": "hi"}]})
        for code in (307, 308):
            with self.subTest(redirect=code):
                _Handler.seen.clear()
                status, _headers, body = net.request(
                    "POST", f"{self.base}/hop-{code}", headers={"Authorization": "Bearer k", "Content-Type": "application/json"},
                    data=payload, timeout=10)
                note = f"server saw {_Handler.seen}"
                self.assertEqual(status, 200, note)
                echoed = json.loads(body.decode())
                self.assertEqual(echoed["auth"], "Bearer k", note)
                self.assertEqual(echoed["body"]["model"], "m", note)

    def test_a_relative_redirect_of_a_post_is_followed_with_its_key(self):
        from cartogen_ai.core import net
        _Handler.seen.clear()
        status, _h, body = net.request("POST", f"{self.base}/hopr-307", headers={"Authorization": "Bearer k", "Content-Type": "application/json"},
                                       data=json.dumps({"model": "m"}), timeout=10)
        self.assertEqual(status, 200, f"server saw {_Handler.seen}")
        self.assertEqual(json.loads(body.decode())["auth"], "Bearer k")

    def test_a_redirect_to_another_site_does_not_carry_the_key(self):
        """Same rule as requests and curl: credentials stay with the site they were given to."""
        from cartogen_ai.core import net
        _Handler.seen.clear()
        status, _h, body = net.request("POST", f"{self.base}/hopx-307", headers={"Authorization": "Bearer k", "Content-Type": "application/json"},
                                       data=json.dumps({"model": "m"}), timeout=10)
        self.assertEqual(status, 200, f"server saw {_Handler.seen}")
        self.assertIsNone(json.loads(body.decode())["auth"], "the key must not follow a redirect to a different host name")

    def test_a_302_turns_a_post_into_a_get_without_a_body(self):
        from cartogen_ai.core import net
        status, _h, body = net.request("POST", f"{self.base}/hop-302", headers={"Authorization": "Bearer k", "Content-Type": "application/json"},
                                       data=json.dumps({"model": "m"}), timeout=10)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body.decode())["method"], "GET")

    def test_a_redirect_loop_ends_with_an_error_not_a_hang(self):
        from cartogen_ai.core import net
        with self.assertRaises(net.NetworkError):
            net.request("POST", f"{self.base}/hop-307-loop", headers={"Authorization": "Bearer k"}, data="{}", timeout=5)

    def test_credential_lookup_records_which_source_supplied_the_key(self):
        """A refused key can then be reported with its source (session memory, saved credentials or an old plaintext setting)."""
        from qgis.core import QgsSettings
        from cartogen_ai.infrastructure.auth import CredentialManager
        provider = "unit-test-provider"
        self.addCleanup(CredentialManager._session_credentials.pop, provider, None)
        self.addCleanup(CredentialManager._last_source.pop, provider, None)
        from cartogen_ai.infrastructure.settings_keys import auth_id_setting_key
        QgsSettings().remove(auth_id_setting_key(provider))
        CredentialManager._session_credentials[provider] = "k" * 12
        self.assertEqual(CredentialManager.get_credential(provider), "k" * 12)
        self.assertEqual(CredentialManager.last_credential_source(provider), "session_memory")

    def test_stream_redirects_are_followed_through_the_urllib_fallback(self):
        for path in ("/redirect-abs", "/redirect"):
            with self._stream(path) as r:
                self.assertEqual(r.status, 200, path)
                self.assertIn("ua", json.loads(r.read().decode()))


if __name__ == "__main__":
    unittest.main()
