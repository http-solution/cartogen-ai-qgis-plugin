"""PLAN-041, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): the Connections window
builds, lists every connection with a status mark, keeps 'look at a page' separate from 'use this connection', saves keys and the
choice, and Settings opens it. Nothing here calls a provider or a CLI."""
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
class TestConnectionsWindow(unittest.TestCase):
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

    def test_every_connection_has_a_row_a_page_and_a_use_button_and_the_default_is_in_use(self):
        from cartogen_ai.infrastructure.settings_keys import DEFAULT_PROVIDER
        dialog = self._dialog()
        for pv in list(dialog._key_edits):
            self.assertIn(pv, dialog._row_items, pv)
            self.assertIn(pv, dialog._use_buttons, pv)
            self.assertIn(pv, dialog._page_index, pv)
        self.assertIn("firms", dialog._row_items)
        self.assertEqual(dialog._active_provider, DEFAULT_PROVIDER)
        self.assertIn("in use", dialog._row_items[DEFAULT_PROVIDER].text())
        self.assertTrue(dialog._use_buttons[DEFAULT_PROVIDER].isHidden())

    def test_each_group_heading_appears_once_and_headings_cannot_be_selected(self):
        from qgis.PyQt.QtCore import Qt
        dialog = self._dialog()
        headings = [dialog.connection_list.item(i) for i in range(dialog.connection_list.count())
                    if dialog.connection_list.item(i).data(Qt.ItemDataRole.UserRole) is None]
        titles = [h.text() for h in headings]
        self.assertEqual(len(titles), len(set(titles)), titles)
        self.assertEqual(len(titles), 4)
        for heading in headings:
            self.assertEqual(heading.flags(), Qt.ItemFlag.NoItemFlags)

    def test_looking_at_a_page_changes_the_page_but_not_the_connection_in_use(self):
        from cartogen_ai.infrastructure.settings_keys import DEFAULT_PROVIDER
        dialog = self._dialog()
        other = next(pv for pv in dialog._key_edits if pv != DEFAULT_PROVIDER and not pv.endswith("_cli"))
        dialog.connection_list.setCurrentItem(dialog._row_items[other])  # what a click on the row does
        self.assertEqual(dialog.provider_stack.currentIndex(), dialog._page_index[other])
        self.assertEqual(dialog._active_provider, DEFAULT_PROVIDER)
        dialog._use_buttons[other].click()
        self.assertEqual(dialog._active_provider, other)
        self.assertIn("in use", dialog._row_items[other].text())
        self.assertNotIn("in use", dialog._row_items[DEFAULT_PROVIDER].text())

    def test_a_typed_key_changes_the_row_mark_and_ok_saves_the_key_the_choice_and_the_model(self):
        from cartogen_ai.infrastructure.auth import CredentialManager
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_PROVIDER
        dialog = self._dialog()
        self.assertTrue(dialog._row_items["gemini"].text().startswith("○"))
        dialog._key_edits["gemini"].setText("test-key-1234")
        self.assertTrue(dialog._row_items["gemini"].text().startswith("●"))
        dialog._use_buttons["gemini"].click()
        dialog._model_combos["gemini"].setCurrentText("gemini-x")
        dialog.accept()
        self.assertEqual(QgsSettings().value(SETTINGS_PROVIDER), "gemini")
        self.assertEqual(CredentialManager.get_credential("gemini"), "test-key-1234")
        again = self._dialog()
        self.assertEqual(again._active_provider, "gemini")
        self.assertEqual(again._model_combos["gemini"].currentText(), "gemini-x")

    def test_the_firms_key_is_saved_from_its_own_page(self):
        from cartogen_ai.infrastructure.auth import CredentialManager
        dialog = self._dialog()
        dialog.connection_list.setCurrentItem(dialog._row_items["firms"])
        self.assertEqual(dialog.provider_stack.currentIndex(), dialog._page_index["firms"])
        dialog.firms_key_edit.setText("firms-key-9999")
        self.assertTrue(dialog._row_items["firms"].text().startswith("●"))
        dialog.accept()
        self.assertEqual(CredentialManager.get_credential("firms"), "firms-key-9999")

    RESULTS = (
        {"provider": "claude_cli", "label": "Claude Code CLI", "found": False, "path": "", "version": "", "problem": "not found",
         "state": "missing", "note": "", "searched": ("/usr/bin", "/opt/tools/bin")},
        {"provider": "codex_cli", "label": "Codex CLI", "found": True, "path": "/bin/codex", "version": "codex-cli 0.165.0", "problem": "",
         "state": "yes", "note": "Logged in using ChatGPT"},
        {"provider": "gemini_cli", "label": "Gemini CLI", "found": True, "path": "/bin/gemini", "version": "0.9", "problem": "",
         "state": "no", "note": ""},
    )

    def _detecting_dialog(self):
        from unittest.mock import patch

        from cartogen_ai.infrastructure.providers import cli_bridge_status
        with patch.object(cli_bridge_status, "detect_all", return_value=list(self.RESULTS)):
            dialog = self._dialog()
            for t in threading.enumerate():
                if t is not threading.current_thread() and t.daemon:
                    t.join(timeout=5)
        dialog._on_detected(list(self.RESULTS))  # the queued signal would arrive through the event loop; apply it directly
        return dialog

    def test_detection_is_written_on_each_cli_page_and_never_switches_the_connection(self):
        from cartogen_ai.infrastructure.settings_keys import DEFAULT_PROVIDER
        dialog = self._detecting_dialog()
        self.assertIn("Not found", dialog._detect_labels["claude_cli"].text())
        self.assertIn("Found codex-cli 0.165.0 \u00b7 signed in", dialog._detect_labels["codex_cli"].text())
        self.assertIn("not signed in", dialog._detect_labels["gemini_cli"].text())
        self.assertEqual(dialog._active_provider, DEFAULT_PROVIDER, "detection must not change the connection in use")
        self.assertTrue(dialog._row_items["codex_cli"].text().startswith("\u2713"), "signed in is marked in the list")
        self.assertTrue(dialog._row_items["claude_cli"].text().startswith("\u25cb"), "not found is marked empty")
        self.assertTrue(dialog._row_items["gemini_cli"].text().startswith("\u25cf"), "found but not signed in is 'set'")

    def test_a_missing_program_lists_where_it_was_looked_for_and_every_cli_page_has_a_browse_button(self):
        from qgis.PyQt.QtWidgets import QLabel, QPushButton
        dialog = self._detecting_dialog()
        tip = dialog._detect_labels["claude_cli"].toolTip()
        self.assertIn("Looked in:", tip)
        self.assertIn("/opt/tools/bin", tip)
        self.assertIn("looked in 2 folders", dialog._detect_labels["claude_cli"].text())
        self.assertEqual(sum(1 for b in dialog.findChildren(QPushButton) if b.text() == "Browse..."), 3)
        notes = [lab.text() for lab in dialog.findChildren(QLabel) if "18 June 2026" in lab.text()]
        self.assertEqual(len(notes), 1, "only the Gemini CLI page says personal accounts were ended")

    def test_a_stale_saved_path_is_replaced_by_the_program_that_was_found(self):
        dialog = self._dialog()
        dialog._key_edits["codex_cli"].setText("/no/such/codex-xyz")
        results = [dict(r) for r in self.RESULTS]
        dialog._on_detected(results)
        self.assertEqual(dialog._key_edits["codex_cli"].text(), "/bin/codex")
        self.assertEqual(dialog._key_edits["gemini_cli"].text(), "/bin/gemini")

    def test_using_a_cli_needs_the_acknowledgement_and_then_makes_it_the_connection_in_use(self):
        dialog = self._detecting_dialog()
        self.assertFalse(dialog._use_buttons["codex_cli"].isEnabled())
        self.assertFalse(dialog._cli_ack_notes["codex_cli"].isHidden())
        dialog.experimental_cli_checkbox.setChecked(True)
        self.assertTrue(dialog._use_buttons["codex_cli"].isEnabled())
        self.assertTrue(dialog._cli_ack_notes["codex_cli"].isHidden())
        dialog._use_buttons["codex_cli"].click()
        self.assertEqual(dialog._active_provider, "codex_cli")
        self.assertTrue(dialog._use_buttons["codex_cli"].isHidden(), "no Use button for the connection already in use")

    def test_settings_shows_the_connection_in_use_and_no_longer_has_the_connection_widgets(self):
        from cartogen_ai.core.ui.settings_dialog import CartogenAiSettingsDialog
        dialog = CartogenAiSettingsDialog()
        self.assertIn("Connection in use:", dialog.connection_summary_label.text())
        self.assertEqual(dialog.open_connections_button.text(), "Connections…")
        for gone in ("provider_stack", "_key_edits", "firms_key_edit", "experimental_cli_checkbox"):
            self.assertFalse(hasattr(dialog, gone), gone)

    def test_settings_ok_does_not_overwrite_the_connection_chosen_in_the_connections_window(self):
        from cartogen_ai.core.ui.settings_dialog import CartogenAiSettingsDialog
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_PROVIDER
        QgsSettings().setValue(SETTINGS_PROVIDER, "gemini")
        dialog = CartogenAiSettingsDialog()
        dialog.accept()
        self.assertEqual(QgsSettings().value(SETTINGS_PROVIDER), "gemini")


if __name__ == "__main__":
    unittest.main()
