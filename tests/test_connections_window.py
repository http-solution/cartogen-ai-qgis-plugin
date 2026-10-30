"""PLAN-041, offline half: the Connections window and its entry points, checked from source (the dialog imports Qt; the real widgets are
exercised in tests/test_connections_window_live.py in the CI live job)."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src" / "cartogen_ai" / "core" / "ui"
DIALOG = (UI / "connections_dialog.py").read_text(encoding="utf-8")
SETTINGS = (UI / "settings_dialog.py").read_text(encoding="utf-8")
DOCK = (UI / "dock_widget.py").read_text(encoding="utf-8")
PLUGIN = (ROOT / "plugin_main.py").read_text(encoding="utf-8")


class TestCatalogIsQtFree(unittest.TestCase):
    def test_the_catalog_imports_without_qgis_and_lists_every_connection_once(self):
        from cartogen_ai.core.ui import connections_catalog as c
        values = [e["value"] for e in c.PROVIDERS + c._CLI_PROVIDERS]
        self.assertEqual(len(values), len(set(values)))
        self.assertTrue({"claude_cli", "codex_cli"} <= set(values))
        self.assertNotIn("gemini_cli", values)
        for entry in c.PROVIDERS + c._CLI_PROVIDERS:
            self.assertIn(c._group_of(entry), c._GROUP_TITLES)

    def test_no_qt_import_in_the_catalog(self):
        tree = ast.parse((UI / "connections_catalog.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self.assertNotIn("qgis", ast.unparse(node))


class TestWindowStructure(unittest.TestCase):
    def test_choosing_which_page_to_see_is_separate_from_choosing_the_connection_in_use(self):
        self.assertIn("def _show_provider", DIALOG)
        self.assertIn("def _use_provider", DIALOG)
        show = DIALOG[DIALOG.index("    def _show_provider"):DIALOG.index("    def _use_provider")]
        self.assertNotIn("_active_provider =", show, "looking at a page must not change the connection in use")
        display = DIALOG[DIALOG.index("    def _display"):DIALOG.index("    def _show_provider")]
        self.assertNotIn("_active_provider =", display)
        self.assertIn("self.connection_list.currentItemChanged.connect(self._on_row_changed)", DIALOG)
        self.assertIn("use_btn.clicked.connect(lambda _checked=False, p=pv: self._use_provider(p))", DIALOG)

    def test_save_writes_the_choice_the_keys_the_models_and_the_cli_path(self):
        accept = DIALOG[DIALOG.index("    def accept"):]
        for needle in ("setValue(PROVIDER_KEY, self._active_provider)", "EXPERIMENTAL_CLI_KEY", "save_credential(pv, key_text)",
                       "cli_path_setting_key(pv)", "save_credential(FIRMS_KEY", 'entry["model_setting_key"]'):
            self.assertIn(needle, accept, needle)

    def test_the_ok_and_cancel_buttons_sit_outside_the_scroll_areas(self):
        self.assertIn("outer_layout.addWidget(self.button_box)", DIALOG)

    def test_the_firms_key_has_its_own_page_and_is_not_a_model_choice(self):
        from cartogen_ai.core.ui import connections_catalog as c
        self.assertIn("def _build_firms_page", DIALOG)
        self.assertIn("credentials.get_credential(FIRMS_KEY)", DIALOG)
        self.assertNotIn("firms", {e["value"] for e in c.PROVIDERS + c._CLI_PROVIDERS})


class TestDetection(unittest.TestCase):
    def test_the_window_looks_for_installed_clis_on_a_background_thread_when_it_opens(self):
        self.assertIn("self._start_detect()", DIALOG[DIALOG.index("        self.init_ui()"):DIALOG.index("    # ----")])
        body = DIALOG[DIALOG.index("    def _start_detect"):DIALOG.index("    def _on_detected")]
        self.assertIn("threading.Thread(target=worker, daemon=True).start()", body)
        self.assertIn("_cli_status.detect_all(configured)", body)

    def test_detection_never_switches_the_connection_by_itself(self):
        for name in ("_start_detect", "_on_detected", "_apply_detection"):
            start = DIALOG.index(f"    def {name}")
            end = DIALOG.index("\n    def ", start + 10)
            self.assertNotIn("_use_provider(", DIALOG[start:end], name)
            self.assertNotIn("_active_provider =", DIALOG[start:end], name)

    def test_a_stale_saved_path_is_replaced_only_when_the_program_was_found(self):
        start = DIALOG.index("    def _apply_detection")
        body = DIALOG[start:DIALOG.index("\n    def ", start + 10)]
        self.assertIn('if entry["found"]:', body)
        self.assertIn("edit.setText(entry[\"path\"])", body)

    def test_using_a_detected_cli_still_needs_the_acknowledgement_box(self):
        body = DIALOG[DIALOG.index("    def _on_cli_ack_toggled"):DIALOG.index("    @staticmethod\n    def _cli_quick_status")]
        self.assertIn("self._use_buttons[pv].setEnabled(checked)", body)


class TestGeminiCliIsGone(unittest.TestCase):
    """Owner decision 2026-10-30: only Claude Code and Codex stay as CLI connections (Google ended personal-account use of Gemini CLI on
    2026-06-18). The Gemini API key connection is a different thing and stays."""

    def test_no_gemini_cli_in_the_provider_tables_or_the_settings_keys(self):
        from cartogen_ai.core.ui import connections_catalog as c
        from cartogen_ai.infrastructure import settings_keys as sk
        self.assertEqual([e["value"] for e in c._CLI_PROVIDERS], ["claude_cli", "codex_cli"])
        self.assertEqual(sk.CLI_PROVIDERS, ("claude_cli", "codex_cli"))
        self.assertFalse(hasattr(sk, "SETTINGS_GEMINI_CLI_MODEL"))
        self.assertIn("gemini", [e["value"] for e in c.PROVIDERS], "the Gemini API key connection stays")

    def test_the_gemini_cli_client_and_parser_are_gone_but_the_api_client_stays(self):
        from cartogen_ai.infrastructure import providers
        from cartogen_ai.infrastructure.providers import cli_bridge as cb
        self.assertFalse(hasattr(cb, "GeminiCliClient"))
        self.assertFalse(hasattr(cb, "parse_gemini_result"))
        self.assertNotIn("GeminiCliClient", providers.__all__)
        self.assertIn("GeminiClient", providers.__all__)


class TestEntryPoints(unittest.TestCase):
    def test_a_plugins_menu_action_opens_the_connections_window_through_the_panel(self):
        self.assertIn('QAction(self.tr("Connections...")', PLUGIN)
        self.assertIn("connections_action.triggered.connect(self.show_connections)", PLUGIN)
        self.assertIn("self.iface.addPluginToMenu(self.menu, connections_action)", PLUGIN)
        self.assertIn("self.actions.append(connections_action)", PLUGIN)  # so unload removes it
        body = PLUGIN[PLUGIN.index("    def show_connections"):PLUGIN.index("    def show_help")]
        self.assertIn("self._ensure_dock()", body)
        self.assertIn("self.dock_widget.open_connections()", body)

    def test_the_panel_refreshes_its_provider_dropdown_after_either_window_saves(self):
        self.assertIn("def open_connections", DOCK)
        self.assertEqual(DOCK.count("self._refresh_after_connection_change()"), 2)

    def test_settings_opens_the_connections_window_and_no_longer_holds_its_settings(self):
        self.assertIn("self.open_connections_button.clicked.connect(self._open_connections)", SETTINGS)
        self.assertIn("from .connections_dialog import CartogenAiConnectionsDialog", SETTINGS)


if __name__ == "__main__":
    unittest.main()
