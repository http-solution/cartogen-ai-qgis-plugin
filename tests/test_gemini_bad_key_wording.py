"""DEF-31 (round-3 smoke row A2): Gemini answers a bad key with HTTP 400 and reason API_KEY_INVALID, not 401/403, so the Test button showed the
raw JSON body. A 400 that names API_KEY_INVALID is an authentication failure and reads like the 401 of the other providers."""
import json
import unittest

from cartogen_ai.infrastructure.providers import provider_check as pc
from cartogen_ai.infrastructure.providers.base import format_http_error

BODY = json.dumps({"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT",
                             "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID",
                                          "domain": "googleapis.com", "metadata": {"service": "generativelanguage.googleapis.com"}}]}})


class _Resp:
    def __init__(self, status, text):
        self.status_code, self.text, self.headers = status, text, {}


class _HttpError(Exception):
    def __init__(self, status, text):
        super().__init__(text)
        self.response = _Resp(status, text)


class TestInvalidKeyIs400(unittest.TestCase):
    def test_a_400_with_api_key_invalid_reads_as_an_authentication_failure(self):
        text = format_http_error("Gemini models list failed", _HttpError(400, BODY))
        self.assertIn("Authentication failed", text)
        self.assertIn("API_KEY_INVALID", text)
        self.assertNotIn('{"error"', text)
        self.assertNotIn("googleapis.com", text)
        self.assertEqual(pc.classify_error(text), "key")

    def test_the_body_stays_withheld_like_a_401(self):
        self.assertIn("Response body withheld", format_http_error("Gemini models list failed", _HttpError(400, BODY)))

    def test_any_other_400_still_shows_the_providers_own_text(self):
        body = json.dumps({"error": {"code": 400, "message": "Invalid JSON payload received.", "status": "INVALID_ARGUMENT"}})
        text = format_http_error("Gemini request failed", _HttpError(400, body))
        self.assertIn("Invalid JSON payload received.", text)
        self.assertNotIn("Authentication failed", text)

    def test_401_and_403_are_unchanged(self):
        self.assertIn("Authentication failed", format_http_error("X", _HttpError(401, "")))
        self.assertIn("Authentication failed", format_http_error("X", _HttpError(403, "")))


if __name__ == "__main__":
    unittest.main()
