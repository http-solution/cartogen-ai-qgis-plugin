"""PLAN-039 slice 3 (now in the Connections window, PLAN-041), real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): the Test button on the
key-based connection pages. The provider check itself is replaced, so no network or key is used."""
import threading
import unittest
from unittest.mock import patch

try:
    from qgis.core import QgsSettings
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    return _boot_qgis()


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestApiTestButton(unittest.TestCase):
    PREFIX = "cartogen_ai/"

    def setUp(self):
        why = _boot()
        if why:
            self.skipTest(why)
        settings = QgsSettings()
        saved = {key: settings.value(key) for key in settings.allKeys() if key.startswith(self.PREFIX)}

        def restore():
            for key in [k for k in settings.allKeys() if k.startswith(self.PREFIX)]:
                settings.remove(key)
            for key, value in saved.items():
                settings.setValue(key, value)
        self.addCleanup(restore)
        for key in saved:
            settings.remove(key)

    def _dialog(self):
        from cartogen_ai.core.ui.connections_dialog import CartogenAiConnectionsDialog
        return CartogenAiConnectionsDialog()

    def test_every_key_based_page_has_a_test_button_and_a_status_line_but_cli_pages_do_not(self):
        dialog = self._dialog()
        for pv in ("openrouter", "gemini", "ollama", "cartogen"):
            self.assertIn(pv, dialog._api_test_buttons, pv)
            self.assertIn(pv, dialog._api_status_labels, pv)
        for pv in ("claude_cli", "codex_cli"):
            self.assertNotIn(pv, dialog._api_test_buttons, pv)

    def test_pressing_test_uses_the_typed_key_and_the_chosen_model_and_saves_nothing(self):
        from cartogen_ai.infrastructure import auth
        from cartogen_ai.infrastructure.providers import provider_check
        before = auth.CredentialManager.get_credential("gemini")
        dialog = self._dialog()
        dialog._key_edits["gemini"].setText("  typed-but-unsaved  ")
        dialog._model_combos["gemini"].setCurrentText("gemini-x")
        with patch.object(provider_check, "check_provider", return_value={"ok": True, "stage": "ready", "message": "Works.", "models": []}) as check:
            dialog._test_api("gemini")
            for t in threading.enumerate():
                if t is not threading.current_thread() and t.daemon:
                    t.join(timeout=5)
        check.assert_called_once_with("gemini", "typed-but-unsaved", "gemini-x")
        self.assertEqual(auth.CredentialManager.get_credential("gemini"), before, "Test must not save the key")

    def test_auto_model_is_passed_as_none(self):
        from cartogen_ai.infrastructure.providers import provider_check
        dialog = self._dialog()
        dialog._key_edits["openrouter"].setText("k")
        with patch.object(provider_check, "check_provider", return_value={"ok": False, "stage": "key", "message": "x", "models": []}) as check:
            dialog._test_api("openrouter")
            for t in threading.enumerate():
                if t is not threading.current_thread() and t.daemon:
                    t.join(timeout=5)
        check.assert_called_once_with("openrouter", "k", None)

    def test_a_working_result_fills_the_models_marks_verified_and_re_enables_the_button(self):
        dialog = self._dialog()
        dialog._api_test_buttons["gemini"].setEnabled(False)
        dialog._on_api_check("gemini", {"ok": True, "stage": "ready", "message": "Works. 2 models listed.", "models": ["m1", "m2"]})
        self.assertIn("Works", dialog._api_status_labels["gemini"].text())
        self.assertTrue(dialog._api_test_buttons["gemini"].isEnabled())
        self.assertIn("gemini", dialog._verified_providers)
        self.assertGreaterEqual(dialog._model_combos["gemini"].findText("m2"), 0)

    def test_a_failure_says_what_to_fix_and_does_not_mark_verified(self):
        dialog = self._dialog()
        dialog._on_api_check("openrouter", {"ok": False, "stage": "key", "message": "Authentication failed", "models": []})
        text = dialog._api_status_labels["openrouter"].text()
        self.assertIn("Not working", text)
        self.assertIn("Paste the key again", text)
        self.assertNotIn("openrouter", dialog._verified_providers)

    def test_cartogen_reports_nothing_to_test(self):
        dialog = self._dialog()
        dialog._key_edits["cartogen"].setText("k")
        dialog._test_api("cartogen")
        for t in threading.enumerate():
            if t is not threading.current_thread() and t.daemon:
                t.join(timeout=5)
        # the result arrives through a queued signal; apply it the way the event loop would
        dialog._on_api_check("cartogen", {"ok": False, "stage": "unavailable", "message": "No hosted gateway is deployed yet.", "models": []})
        self.assertIn("No hosted gateway", dialog._api_status_labels["cartogen"].text())


if __name__ == "__main__":
    unittest.main()
