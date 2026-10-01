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
from unittest.mock import patch, MagicMock

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


class TestLogEvent(unittest.TestCase):
    """Product policy decision, 2026-09-20 (strict option chosen): tool-call and
    agent-turn logging moved from truncated/redacted free-form content to
    structured, metadata-only logging. log_event is the only sanctioned way to log
    those -- these tests drive it directly to confirm it never emits a field it
    wasn't explicitly told is safe, and that unsafe kwargs are silently dropped
    rather than passed through (a future call site adding a new kwarg must not be
    able to widen what gets logged without deliberately extending
    _SAFE_EVENT_FIELDS)."""

    def _captured_stdout(self, fn, *args, **kwargs):
        buf = io.StringIO()
        old = sys.stdout.write
        sys.stdout.write = buf.write
        try:
            fn(*args, **kwargs)
        finally:
            sys.stdout.write = old
        return buf.getvalue()

    def test_log_event_includes_only_safe_fields(self):
        out = self._captured_stdout(
            logger.log_event, "tool_call", tag="Agent", tool="get_layers", status="done",
            duration_ms=42, correlation_id="abc123", provider="OpenRouterClient",
        )
        self.assertIn("tool_call", out)
        self.assertIn("tool=get_layers", out)
        self.assertIn("status=done", out)
        self.assertIn("duration_ms=42", out)
        self.assertIn("correlation_id=abc123", out)
        self.assertIn("provider=OpenRouterClient", out)

    def test_log_event_drops_unsafe_kwargs_instead_of_passing_them_through(self):
        out = self._captured_stdout(
            logger.log_event, "tool_call", tag="Agent", tool="execute_pyqgis_script",
            status="done", raw_arguments="SELECT * FROM secret_table WHERE ssn='123-45-6789'",
        )
        self.assertNotIn("123-45-6789", out)
        self.assertNotIn("raw_arguments", out)
        self.assertNotIn("secret_table", out)

    def test_log_event_error_true_routes_to_stderr(self):
        buf = io.StringIO()
        old = sys.stderr.write
        sys.stderr.write = buf.write
        try:
            logger.log_event("tool_call", tag="Agent", tool="get_layers", status="failed",
                              error_class="KeyError", error=True)
        finally:
            sys.stderr.write = old
        out = buf.getvalue()
        self.assertIn("status=failed", out)
        self.assertIn("error_class=KeyError", out)


class TestLogDiagnostic(unittest.TestCase):
    """log_diagnostic is the explicit, OFF-by-default escape hatch for raw-content
    logging -- must be a true no-op outside QGIS (where the opt-in setting can't
    exist), which is exactly this test environment."""

    def test_log_diagnostic_is_a_no_op_outside_qgis(self):
        buf = io.StringIO()
        old = sys.stdout.write
        sys.stdout.write = buf.write
        try:
            logger.log_diagnostic("this should never be printed: sk-or-v1-realkey123456")
        finally:
            sys.stdout.write = old
        self.assertEqual(buf.getvalue(), "")

    def test_diagnostic_logging_disabled_by_default(self):
        self.assertFalse(logger._diagnostic_logging_enabled())


class TestDiagnosticLoggingIsTimeBound(unittest.TestCase):
    """Second-review correction, 2026-09-20: a plain persistent boolean setting
    doesn't meet the "explicit, TIME-BOUND diagnostic mode" policy -- a developer
    could enable it and forget to turn it back off. enable_diagnostic_logging()
    now stores an expiry timestamp instead of a boolean; these tests drive that
    mechanism directly with a mocked QgsSettings (real QgsSettings isn't
    available in this headless test environment)."""

    def test_enabled_immediately_after_enable_call(self):
        store = {}
        fake_settings = MagicMock()
        fake_settings.setValue.side_effect = lambda k, v: store.__setitem__(k, v)
        fake_settings.value.side_effect = lambda k, default, type=None: store.get(k, default)

        with patch("cartogen_ai.core.logger.QGIS_LOG_AVAILABLE", True), \
             patch("cartogen_ai.core.logger.QgsSettings", return_value=fake_settings, create=True):
            logger.enable_diagnostic_logging(duration_seconds=3600)
            self.assertTrue(logger._diagnostic_logging_enabled())

    def test_expires_on_its_own_without_manual_disable(self):
        store = {}
        fake_settings = MagicMock()
        fake_settings.setValue.side_effect = lambda k, v: store.__setitem__(k, v)
        fake_settings.value.side_effect = lambda k, default, type=None: store.get(k, default)

        with patch("cartogen_ai.core.logger.QGIS_LOG_AVAILABLE", True), \
             patch("cartogen_ai.core.logger.QgsSettings", return_value=fake_settings, create=True):
            # Already-expired window (negative duration) -- simulates time having
            # passed without anyone calling disable_diagnostic_logging().
            logger.enable_diagnostic_logging(duration_seconds=-1)
            self.assertFalse(logger._diagnostic_logging_enabled())

    def test_disable_ends_it_immediately(self):
        store = {}
        fake_settings = MagicMock()
        fake_settings.setValue.side_effect = lambda k, v: store.__setitem__(k, v)
        fake_settings.remove.side_effect = lambda k: store.pop(k, None)
        fake_settings.value.side_effect = lambda k, default, type=None: store.get(k, default)

        with patch("cartogen_ai.core.logger.QGIS_LOG_AVAILABLE", True), \
             patch("cartogen_ai.core.logger.QgsSettings", return_value=fake_settings, create=True):
            logger.enable_diagnostic_logging(duration_seconds=3600)
            self.assertTrue(logger._diagnostic_logging_enabled())
            logger.disable_diagnostic_logging()
            self.assertFalse(logger._diagnostic_logging_enabled())


class TestSwallowedExceptionsAreLogged(unittest.TestCase):
    """Fifth-review follow-up, 2026-09-23: best-effort fallbacks that used to
    `except Exception: pass` now leave a content-free log_event trace (error class
    only) while still returning their fallback value -- the QgsLabelObstacleSettings
    NameError this cycle hid behind exactly this kind of silent swallow."""

    def test_distance_fallback_still_returns_value_and_logs_class_only(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _measure_distance
        da = MagicMock()
        da.measureLine.side_effect = RuntimeError("secret-looking detail")
        a, b = MagicMock(), MagicMock()
        a.distance.return_value = 7.0
        buf = io.StringIO()
        old = sys.stderr.write
        sys.stderr.write = buf.write
        try:
            result = _measure_distance(da, a, b)
        finally:
            sys.stderr.write = old
        self.assertEqual(result, 7.0)
        out = buf.getvalue()
        self.assertIn("swallowed_exception", out)
        self.assertIn("error_class=RuntimeError", out)
        self.assertNotIn("secret-looking detail", out)


if __name__ == "__main__":
    unittest.main()


class TestStartupStateFields(unittest.TestCase):
    """rc7 smoke test F18: the plan-validation gate was silently ON; the startup log now says so."""

    def test_reports_each_setting(self):
        from cartogen_ai.core.logger import startup_state_fields
        values = {"cartogen_ai/plan_validation_gate_enabled": "true", "cartogen_ai/egress_gate_mode": "block"}
        out = startup_state_fields(lambda k, d=None: values.get(k, d))
        self.assertEqual(out["plan_validation_gate"], "ON")
        self.assertEqual(out["egress_gate_mode"], "block")
        self.assertEqual(out["persist_chat"], "ON")          # default ON (F25 option B)

    def test_defaults_when_nothing_is_set(self):
        from cartogen_ai.core.logger import startup_state_fields
        out = startup_state_fields(lambda k, d=None: d)
        self.assertEqual(out["plan_validation_gate"], "OFF")

    def test_an_unreadable_setting_is_unknown_not_a_crash(self):
        from cartogen_ai.core.logger import startup_state_fields

        def boom(k, d=None):
            raise RuntimeError("no settings")
        self.assertEqual(startup_state_fields(boom)["plan_validation_gate"], "unknown")

    def test_the_fields_are_whitelisted_for_log_event(self):
        from cartogen_ai.core import logger
        for f in ("plan_validation_gate", "egress_gate_mode", "persist_chat"):
            self.assertIn(f, logger._SAFE_EVENT_FIELDS)
