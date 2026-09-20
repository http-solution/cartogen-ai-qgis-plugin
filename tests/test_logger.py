# -*- coding: utf-8 -*-
"""P1 fix, 2026-09-20 audit: core/logger.py used to forward whatever string a
caller built straight to QgsMessageLog/stdout -- including tool arguments and
tool results, which can embed a provider API key, a bearer token, or a
password. These tests drive the actual log_info/log_warning/log_error entry
points (not just the private _redact helper) so a regression in how/whether
redaction gets applied at the public API is caught, not just in the regex."""
import io
import sys
import unittest

from cartogen_ai.core import logger


class TestLogRedaction(unittest.TestCase):
    def _captured(self, fn, message):
        buf = io.StringIO()
        stream = sys.stdout if fn is logger.log_info else sys.stderr
        old = stream.write
        stream.write = buf.write
        try:
            fn(message, tag="Test")
        finally:
            stream.write = old
        return buf.getvalue()

    def test_log_info_redacts_openrouter_style_key(self):
        out = self._captured(logger.log_info, 'Tool call: save_key({"api_key": "sk-or-v1-abcdefghijklmnopqrstuvwxyz"})')
        self.assertNotIn("sk-or-v1-abcdefghijklmnopqrstuvwxyz", out)
        self.assertIn("***REDACTED***", out)

    def test_log_error_redacts_gemini_style_key(self):
        out = self._captured(logger.log_error, "request failed for key=AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ1234567")
        self.assertNotIn("AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ1234567", out)
        self.assertIn("***REDACTED***", out)

    def test_log_warning_redacts_bearer_token(self):
        out = self._captured(logger.log_warning, "Authorization: Bearer sk-ant-abc123DEF456ghi789")
        self.assertNotIn("sk-ant-abc123DEF456ghi789", out)
        self.assertIn("***REDACTED***", out)

    def test_log_info_redacts_password_field(self):
        out = self._captured(logger.log_info, 'config = {"password": "hunter2secret"}')
        self.assertNotIn("hunter2secret", out)

    def test_log_info_leaves_ordinary_content_alone(self):
        out = self._captured(logger.log_info, "Tool get_layers succeeded: {'count': 3}")
        self.assertIn("count", out)
        self.assertIn("3", out)
        self.assertNotIn("REDACTED", out)

    def test_redact_helper_is_idempotent_on_non_string_input(self):
        # Callers pass f-strings that may embed non-str values (exceptions, dicts) --
        # _redact must coerce via str() rather than raise on a non-str message.
        self.assertIsInstance(logger._redact(ValueError("boom")), str)


if __name__ == "__main__":
    unittest.main()
