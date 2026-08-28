"""Cartogen AI account/session client for the QGIS plugin.

Account identity and application API access are deliberately separate:
- this client manages the Cartogen service session cookie/token;
- the Cartogen provider still receives only an assigned application key.

Passwords and session credentials never enter logs, settings text, or return
messages. The caller owns the client instance for the duration of the session.
"""

from urllib.parse import urlsplit, urlunsplit

import requests


DEFAULT_ACCOUNT_BASE_URL = "http://localhost:3000"


def normalize_account_base_url(value):
    value = str(value or DEFAULT_ACCOUNT_BASE_URL).strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Cartogen account URL must be an absolute HTTP(S) URL")
    path = parsed.path.rstrip("/")
    for suffix in ("/api", "/auth"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


class CartogenAccountClient:
    """Small, session-preserving client for the Cartogen account service."""

    def __init__(self, base_url=DEFAULT_ACCOUNT_BASE_URL, session=None, timeout=15, session_cookie=None):
        self.base_url = normalize_account_base_url(base_url)
        self.session = session or requests.Session()
        if session_cookie:
            self.session.cookies.set("cartogen_session", session_cookie, path="/")
        self.timeout = timeout

    def session_cookie(self):
        """Returns the opaque service session cookie for encrypted persistence."""
        return self.session.cookies.get("cartogen_session", "")

    def _request(self, method, path, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        headers = {"Accept": "application/json", **kwargs.pop("headers", {})}
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")
        response = self.session.request(method, self.base_url + path, headers=headers, **kwargs)
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not response.ok:
            message = body.get("error") or body.get("message") or f"Cartogen account request failed ({response.status_code})"
            error = RuntimeError(message)
            error.status_code = response.status_code
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
        self.session.cookies.clear()
        return {"status": "signed_out"}

    def registration_status(self):
        return self._request("GET", "/api/auth/status")
