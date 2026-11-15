"""Cartogen AI account/session client for the QGIS plugin.

Account identity and application API access are deliberately separate:
- this client manages the Cartogen service session cookie/token;
- the Cartogen provider still receives only an assigned application key.

Passwords and session credentials never enter logs, settings text, or return
messages. The caller owns the client instance for the duration of the session.
"""

import json
from urllib.parse import urlsplit, urlunsplit

import requests  # type: ignore[import-untyped]

from .. import net


DEFAULT_ACCOUNT_BASE_URL = "http://localhost:3000"

# BUG-2026-09-08-1 fix (2026-09-08): account_dialog.py tells the user their password
# "is sent only over HTTPS," but nothing enforced that claim -- normalize_account_base_url()
# accepted any http(s) URL, including the http:// default. Plain HTTP is now rejected unless
# the host is a local-development loopback address, so a real deployment can't silently send
# credentials in the clear while the UI still claims HTTPS-only.
_LOCAL_DEV_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def normalize_account_base_url(value):
    value = str(value or DEFAULT_ACCOUNT_BASE_URL).strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Cartogen account URL must be an absolute HTTP(S) URL")
    if parsed.scheme == "http" and parsed.hostname not in _LOCAL_DEV_HOSTNAMES:
        raise ValueError(
            "Cartogen account URL must use HTTPS (plain HTTP is only allowed for "
            "localhost/127.0.0.1 during local development)"
        )
    path = parsed.path.rstrip("/")
    for suffix in ("/api", "/auth"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


class CartogenAccountClient:
    """Small, session-preserving client for the Cartogen account service."""

    def __init__(self, base_url=DEFAULT_ACCOUNT_BASE_URL, session=None, timeout=15, session_cookie=None):
        self.base_url = normalize_account_base_url(base_url)
        # Inside QGIS the requests go through QGIS's network stack (proxy, authentication, SSL settings) and the session cookie is kept
        # here; outside QGIS (the unit tests) or with an injected session the requests library is used, as before.
        self._use_qgis = session is None and net.QGIS_NETWORK_AVAILABLE
        self._cookies = {}
        self.session = None if self._use_qgis else (session or requests.Session())
        if session_cookie:
            if self._use_qgis:
                self._cookies["cartogen_session"] = session_cookie
            else:
                self.session.cookies.set("cartogen_session", session_cookie, path="/")
        self.timeout = timeout

    def session_cookie(self):
        """Returns the opaque service session cookie for encrypted persistence."""
        if self._use_qgis:
            return self._cookies.get("cartogen_session", "")
        return self.session.cookies.get("cartogen_session", "")

    def _remember_cookies(self, header_pairs):
        """Applies the Set-Cookie headers of a reply to the cookie store (QGIS path). Only the name=value pair matters here; a cookie
        that is emptied or expired by the service is dropped."""
        for name, value in header_pairs:
            if name.lower() != "set-cookie":
                continue
            for line in str(value).split("\n"):
                pair, *attrs = [part.strip() for part in line.split(";")]
                if "=" not in pair:
                    continue
                key, val = pair.split("=", 1)
                expired = any(a.lower() == "max-age=0" for a in attrs) or not val
                if expired:
                    self._cookies.pop(key, None)
                else:
                    self._cookies[key] = val

    def _send_qgis(self, method, path, headers, kwargs):
        data = json.dumps(kwargs["json"]).encode("utf-8") if "json" in kwargs else None
        if self._cookies:
            headers = {**headers, "Cookie": "; ".join(f"{k}={v}" for k, v in self._cookies.items())}
        try:
            status, reply_headers, raw = net.request(method, self.base_url + path, headers, data, kwargs.get("timeout", self.timeout))
        except net.NetworkError as e:
            # Raised as RuntimeError so the account dialog shows one safe message; the cause (a host name, no credentials) is kept.
            raise RuntimeError("The Cartogen account service could not be reached.") from e
        self._remember_cookies(reply_headers)
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            body = {}
        return status, (body if isinstance(body, dict) else {})

    def _request(self, method, path, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        headers = {"Accept": "application/json", **kwargs.pop("headers", {})}
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")
        if self._use_qgis:
            status, body = self._send_qgis(method, path, headers, kwargs)
            ok = status < 400
        else:
            response = self.session.request(method, self.base_url + path, headers=headers, **kwargs)
            try:
                body = response.json()
            except ValueError:
                body = {}
            status, ok = response.status_code, response.ok
        if not ok:
            message = body.get("error") or body.get("message") or f"Cartogen account request failed ({status})"
            error = RuntimeError(message)
            error.status_code = status
            raise error
        return body

    def register(self, email, password, first_name="", last_name=""):
        body = self._request("POST", "/auth/register", json={
            "email": str(email).strip(),
            "password": password,
            "first_name": str(first_name).strip(),
            "last_name": str(last_name).strip(),
        })
        if body.get("verification_required"):
            return {"status": "verification_required", "message": body.get("message", "Account activation is required before sign in.")}
        return {"status": "authenticated" if body.get("ok") else "registered", "message": body.get("message", "Account created.")}

    def login(self, email, password):
        body = self._request("POST", "/auth/login", json={"email": str(email).strip(), "password": password})
        result = {"status": "authenticated", "message": body.get("message", "Signed in.")}
        # Some compatible gateways return a token; the hosted website uses an
        # HttpOnly session cookie instead. Support both without exposing either
        # in UI messages or persistent settings.
        if body.get("access_token"):
            result["access_token"] = body["access_token"]
        return result

    def current_user(self, access_token=None):
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
        body = self._request("GET", "/api/me", headers=headers)
        user = body.get("user", body.get("data", body))
        return {key: user[key] for key in ("id", "email", "first_name", "last_name") if key in user}

    def logout(self):
        self._request("POST", "/auth/logout", json={})
        if self._use_qgis:
            self._cookies.clear()
        else:
            self.session.cookies.clear()
        return {"status": "signed_out"}

    def registration_status(self):
        return self._request("GET", "/api/auth/status")
