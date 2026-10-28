"""PLAN-038: the experimental CLI provider wiring in a real QGIS process (CI live job; written without a QGIS install, so CI's first run
is its first execution). Checks the Settings dialog with the switch off and on, what Save writes, and that the agent builds the matching
client. No CLI is run."""
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
        from cartogen_ai.core.ui.settings_dialog import CartogenAiSettingsDialog
        return CartogenAiSettingsDialog()

    def test_off_by_default_no_cli_entries_and_a_saved_cli_provider_falls_back(self):
        from cartogen_ai.infrastructure.settings_keys import DEFAULT_PROVIDER, SETTINGS_PROVIDER, normalize_provider
        QgsSettings().setValue(SETTINGS_PROVIDER, "claude_cli")
        self.assertEqual(normalize_provider("claude_cli"), DEFAULT_PROVIDER)
        dialog = self._dialog()
        self.assertFalse(dialog.experimental_cli_checkbox.isChecked())
        for p in ("claude_cli", "codex_cli", "gemini_cli"):
            self.assertNotIn(p, dialog._key_edits)

    def test_ticking_the_switch_then_reopening_shows_the_entries_and_save_writes_the_path_as_a_plain_setting(self):
        from cartogen_ai.infrastructure.auth import CredentialManager
        from cartogen_ai.infrastructure.settings_keys import (
            SETTINGS_CLAUDE_CLI_MODEL, SETTINGS_PROVIDER, cli_path_setting_key, normalize_provider,
        )
        first = self._dialog()
        first.experimental_cli_checkbox.setChecked(True)
        first.accept()
        self.assertEqual(normalize_provider("claude_cli"), "claude_cli")

        dialog = self._dialog()
        self.assertTrue(dialog.experimental_cli_checkbox.isChecked())
        self.assertEqual(dialog._key_edits["claude_cli"].text(), "claude")  # the default program name
        dialog._key_edits["claude_cli"].setText("/opt/tools/claude")
        dialog._select_provider("claude_cli")
        dialog._model_combos["claude_cli"].setCurrentText("sonnet")
        dialog.accept()

        settings = QgsSettings()
        self.assertEqual(settings.value(SETTINGS_PROVIDER), "claude_cli")
        self.assertEqual(settings.value(cli_path_setting_key("claude_cli")), "/opt/tools/claude")
        self.assertEqual(settings.value(SETTINGS_CLAUDE_CLI_MODEL), "sonnet")
        self.assertEqual(CredentialManager.get_credential("claude_cli"), "", "a program path must not go in the credential store")

        again = self._dialog()
        self.assertEqual(again._key_edits["claude_cli"].text(), "/opt/tools/claude")
        self.assertEqual(again._active_provider, "claude_cli")

    def test_the_agent_builds_the_matching_client_from_the_saved_settings(self):
        import cartogen_ai.core.agent.agent_orchestrator as agent_mod
        from cartogen_ai.infrastructure.providers.cli_bridge import ClaudeCliClient, CodexCliClient, GeminiCliClient
        from cartogen_ai.infrastructure.settings_keys import (
            SETTINGS_CODEX_CLI_MODEL, SETTINGS_EXPERIMENTAL_CLI, SETTINGS_PROVIDER, cli_path_setting_key,
        )
        settings = QgsSettings()
        settings.setValue(SETTINGS_EXPERIMENTAL_CLI, True)
        settings.setValue(cli_path_setting_key("codex_cli"), "/opt/tools/codex")
        settings.setValue(SETTINGS_CODEX_CLI_MODEL, "gpt-x")
        for provider, cls in (("claude_cli", ClaudeCliClient), ("codex_cli", CodexCliClient), ("gemini_cli", GeminiCliClient)):
            settings.setValue(SETTINGS_PROVIDER, provider)
            agent = agent_mod.CartogenAi()
            self.assertIsInstance(agent.client, cls, provider)
        settings.setValue(SETTINGS_PROVIDER, "codex_cli")
        agent = agent_mod.CartogenAi()
        self.assertEqual((agent.client.executable, agent.client.model), ("/opt/tools/codex", "gpt-x"))

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
