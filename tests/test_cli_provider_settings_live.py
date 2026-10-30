"""PLAN-038 (the dialog is the Connections window since PLAN-041): the experimental CLI provider wiring in a real QGIS process (CI live job; written without a QGIS install, so CI's first run
is its first execution). Checks the Connections window with the switch off and on, what Save writes, and that the agent builds the matching
client. No CLI is run."""
import threading
import unittest

try:
    from qgis.core import QgsSettings
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    return _boot_qgis()


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestCliProviderSettings(unittest.TestCase):
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

    def test_off_by_default_cli_pages_are_listed_and_a_saved_cli_provider_falls_back(self):
        from cartogen_ai.infrastructure.settings_keys import DEFAULT_PROVIDER, SETTINGS_PROVIDER, normalize_provider
        QgsSettings().setValue(SETTINGS_PROVIDER, "claude_cli")
        self.assertEqual(normalize_provider("claude_cli"), DEFAULT_PROVIDER)
        dialog = self._dialog()
        self.assertFalse(dialog.experimental_cli_checkbox.isChecked())
        for p in ("claude_cli", "codex_cli"):
            self.assertIn(p, dialog._key_edits)
        self.assertEqual(dialog._active_provider, DEFAULT_PROVIDER)

    def test_a_cli_chosen_after_consent_is_saved_as_a_plain_setting_and_survives_reopening(self):
        from cartogen_ai.infrastructure.auth import CredentialManager
        from cartogen_ai.infrastructure.settings_keys import (
            DEFAULT_PROVIDER, SETTINGS_CLAUDE_CLI_MODEL, SETTINGS_PROVIDER, cli_path_setting_key, normalize_provider,
        )
        dialog = self._dialog()
        dialog.experimental_cli_checkbox.setChecked(True)
        self.assertEqual(dialog._key_edits["claude_cli"].text(), "claude")  # the default program name
        dialog._key_edits["claude_cli"].setText("/opt/tools/claude")
        dialog.connection_list.setCurrentItem(dialog._row_items["claude_cli"])
        self.assertEqual(dialog._active_provider, DEFAULT_PROVIDER, "looking at a page must not change the connection in use")
        dialog._use_provider("claude_cli")  # what the guided setup does at its last step (tests/test_connections_window_live.py)
        self.assertEqual(dialog._active_provider, "claude_cli")
        dialog._model_combos["claude_cli"].setCurrentText("sonnet")
        dialog.accept()

        settings = QgsSettings()
        self.assertEqual(settings.value(SETTINGS_PROVIDER), "claude_cli")
        self.assertEqual(settings.value(cli_path_setting_key("claude_cli")), "/opt/tools/claude")
        self.assertEqual(settings.value(SETTINGS_CLAUDE_CLI_MODEL), "sonnet")
        self.assertEqual(normalize_provider("claude_cli"), "claude_cli")
        self.assertEqual(CredentialManager.get_credential("claude_cli"), "", "a program path must not go in the credential store")

        again = self._dialog()
        self.assertTrue(again.experimental_cli_checkbox.isChecked())
        self.assertEqual(again._key_edits["claude_cli"].text(), "/opt/tools/claude")
        self.assertEqual(again._active_provider, "claude_cli")

    def test_unticking_while_a_cli_provider_is_active_returns_to_the_default(self):
        from cartogen_ai.infrastructure.settings_keys import DEFAULT_PROVIDER
        dialog = self._dialog()
        dialog.experimental_cli_checkbox.setChecked(True)
        dialog._use_provider("codex_cli")
        self.assertEqual(dialog._active_provider, "codex_cli")
        dialog.experimental_cli_checkbox.setChecked(False)
        self.assertEqual(dialog._active_provider, DEFAULT_PROVIDER)
        self.assertEqual(dialog.provider_stack.currentIndex(), dialog._page_index[DEFAULT_PROVIDER])
        self.assertTrue(dialog._row_items[DEFAULT_PROVIDER].isSelected())

    def test_each_cli_page_shows_a_status_and_the_check_and_signin_buttons(self):
        dialog = self._dialog()
        for p in ("claude_cli", "codex_cli"):
            self.assertIn(p, dialog._cli_status_labels)
            self.assertEqual(len(dialog._cli_buttons[p]), 2)
        dialog._key_edits["codex_cli"].setText("/no/such/codex-xyz")
        self.assertIn("not found", dialog._cli_status_labels["codex_cli"].text())

    def test_check_results_update_the_status_and_re_enable_the_buttons(self):
        dialog = self._dialog()
        dialog.experimental_cli_checkbox.setChecked(True)
        pv = "claude_cli"
        for btn in dialog._cli_buttons[pv]:
            btn.setEnabled(False)
        dialog._on_cli_check(pv, {"ok": True, "stage": "ready", "message": "Answered in 2.0 s (ok).", "version": "2.1.0"})
        self.assertIn("Signed in", dialog._cli_status_labels[pv].text())
        self.assertIn("2.1.0", dialog._cli_status_labels[pv].text())
        self.assertTrue(all(b.isEnabled() for b in dialog._cli_buttons[pv]))
        dialog._on_cli_check(pv, {"ok": False, "stage": "signin", "message": "Is it signed in?"})
        self.assertIn("Sign in", dialog._cli_status_labels[pv].text())
        dialog._on_cli_check(pv, {"ok": False, "stage": "install", "message": "not found"})
        self.assertIn("program name or path", dialog._cli_status_labels[pv].text())

    def test_the_check_and_signin_buttons_call_the_status_helpers_with_the_form_values(self):
        from unittest.mock import patch

        from cartogen_ai.infrastructure.providers import cli_bridge_status
        dialog = self._dialog()
        dialog.experimental_cli_checkbox.setChecked(True)
        dialog._key_edits["codex_cli"].setText("/opt/codex")
        with patch.object(cli_bridge_status, "open_signin_terminal",
                          return_value={"launched": True, "command": "x", "message": "A terminal window should have opened"}) as signin:
            dialog._signin_cli("codex_cli")
        signin.assert_called_once_with("codex_cli", "/opt/codex")
        self.assertIn("terminal", dialog._cli_status_labels["codex_cli"].text())
        with patch.object(cli_bridge_status, "check_connection", return_value={"ok": True, "stage": "ready", "message": "m", "version": "v"}) as check:
            dialog._check_cli("codex_cli")
            for t in threading.enumerate():
                if t is not threading.current_thread() and t.daemon:
                    t.join(timeout=5)
        check.assert_called_once_with("codex_cli", "/opt/codex", None)

    def test_the_agent_builds_the_matching_client_from_the_saved_settings(self):
        import cartogen_ai.core.agent.agent_orchestrator as agent_mod
        from cartogen_ai.infrastructure.providers.cli_bridge import ClaudeCliClient, CodexCliClient
        from cartogen_ai.infrastructure.settings_keys import (
            SETTINGS_CODEX_CLI_MODEL, SETTINGS_EXPERIMENTAL_CLI, SETTINGS_PROVIDER, cli_path_setting_key,
        )
        settings = QgsSettings()
        settings.setValue(SETTINGS_EXPERIMENTAL_CLI, True)
        settings.setValue(cli_path_setting_key("codex_cli"), "/opt/tools/codex")
        settings.setValue(SETTINGS_CODEX_CLI_MODEL, "gpt-x")
        for provider, cls in (("claude_cli", ClaudeCliClient), ("codex_cli", CodexCliClient)):
            settings.setValue(SETTINGS_PROVIDER, provider)
            agent = agent_mod.CartogenAi()
            self.assertIsInstance(agent.client, cls, provider)
        settings.setValue(SETTINGS_PROVIDER, "codex_cli")
        agent = agent_mod.CartogenAi()
        self.assertEqual((agent.client.executable, agent.client.model), ("/opt/tools/codex", "gpt-x"))

    def test_a_saved_gemini_cli_provider_from_an_earlier_build_falls_back_to_the_default(self):
        import cartogen_ai.core.agent.agent_orchestrator as agent_mod
        from cartogen_ai.infrastructure.providers import OpenRouterClient
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_EXPERIMENTAL_CLI, SETTINGS_PROVIDER, normalize_provider
        settings = QgsSettings()
        settings.setValue(SETTINGS_EXPERIMENTAL_CLI, True)
        settings.setValue(SETTINGS_PROVIDER, "gemini_cli")
        self.assertEqual(normalize_provider("gemini_cli"), "openrouter")
        self.assertIsInstance(agent_mod.CartogenAi().client, OpenRouterClient)

    def test_with_the_switch_off_the_agent_ignores_a_saved_cli_provider(self):
        import cartogen_ai.core.agent.agent_orchestrator as agent_mod
        from cartogen_ai.infrastructure.providers import OpenRouterClient
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_EXPERIMENTAL_CLI, SETTINGS_PROVIDER
        settings = QgsSettings()
        settings.setValue(SETTINGS_EXPERIMENTAL_CLI, False)
        settings.setValue(SETTINGS_PROVIDER, "claude_cli")
        self.assertIsInstance(agent_mod.CartogenAi().client, OpenRouterClient)


if __name__ == "__main__":
    unittest.main()
