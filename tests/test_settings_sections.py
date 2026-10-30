"""PLAN-039 slice 2: the Settings window's sections follow what a setting governs. The dialog imports Qt, so this reads its source; the
real widgets are exercised in tests/test_settings_sections_live.py (CI live job)."""
import re
import unittest
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "src" / "cartogen_ai" / "core" / "ui" / "settings_dialog.py").read_text(encoding="utf-8")
INIT = SOURCE[SOURCE.index("    def init_ui"):SOURCE.index("    def _section_note")]

EXPECTED_SECTIONS = [
    ("01", "Privacy and data protection"), ("02", "How the assistant works"), ("03", "Who the assistant writes for"),
    ("04", "Print layouts"), ("05", "Diagnostics"),
]
# widget attribute -> the column (and so the section) it must be placed in
PLACEMENT = {
    "egress_gate_mode_combo": "privacy_gate_col", "egress_gate_strict_checkbox": "privacy_gate_col",
    "persist_history_checkbox": "privacy_keep_col", "persist_project_memory_checkbox": "privacy_keep_col",
    "auto_open_dock_checkbox": "behaviour_col", "prompt_refinement_checkbox": "behaviour_col", "prompt_preview_checkbox": "behaviour_col",
    "project_inspector_checkbox": "experimental_col", "plan_validation_gate_checkbox": "experimental_col",
    "evidence_checkbox": "diag_col", "api_trace_checkbox": "diag_col",
}


class TestSections(unittest.TestCase):
    def test_the_connection_settings_left_for_the_connections_window(self):
        """PLAN-041: provider keys, models, CLI paths and the FIRMS key are the Connections window's, so Settings only reads which one is in use (to show it) and never writes them."""
        for gone in ("provider_stack", "_key_edits", "firms_key_edit", "experimental_cli_checkbox", "save_credential", "setValue(PROVIDER_KEY"):
            self.assertNotIn(gone, SOURCE, gone)
        self.assertIn("CartogenAiConnectionsDialog", SOURCE)
        self.assertIn("Connections…", SOURCE)

    def test_sections_are_numbered_in_order_with_the_agreed_titles(self):
        found = re.findall(r'_section_header\("(\d\d)", "([^"]+)"\)', INIT)
        self.assertEqual(found, EXPECTED_SECTIONS)

    def test_each_setting_is_placed_in_its_sections_column(self):
        for widget, column in PLACEMENT.items():
            self.assertRegex(INIT, rf"{column}\.add(?:Widget|Row)\([^\n]*self\.{widget}\b|{column}\.addLayout\(egress_form\)",
                             f"{widget} should go in {column}")

    def test_the_privacy_section_comes_before_behaviour_and_the_gate_before_the_saved_files(self):
        self.assertLess(INIT.index('"Privacy and data protection"'), INIT.index('"How the assistant works"'))
        self.assertLess(INIT.index("layout.addLayout(privacy_gate_col)"), INIT.index("layout.addLayout(privacy_keep_col)"))

    def test_print_layout_settings_are_in_their_own_form(self):
        for label in ("Print layout title colour:", "Layout disclaimer:", "Disclaimer wording:"):
            self.assertIn(f'layout_form.addRow("{label}"', INIT)
        for label in ("Max tool-call rounds per request:", "Max tokens per request:", "Ask before downloads larger than:"):
            self.assertIn(f'limits_form.addRow("{label}"', INIT)

    def test_no_widget_was_left_out_of_every_section(self):
        names = set(re.findall(r"self\.(\w+) = Q(?:CheckBox|SpinBox|LineEdit|ComboBox|PushButton)\(", INIT))
        for name in names:
            self.assertRegex(INIT, rf"(addWidget|addRow)\([^\n]*self\.{name}\b|addRow\([^\n]*, self\.{name}\)", f"{name} is never added")

    def test_collapsible_sections_open_by_themselves_when_anything_inside_is_on(self):
        self.assertIn("expanded=self.project_inspector_checkbox.isChecked() or self.plan_validation_gate_checkbox.isChecked()", INIT)
        self.assertIn("expanded=self.evidence_checkbox.isChecked() or self.api_trace_checkbox.isChecked()", INIT)

    def test_every_saved_setting_is_still_written_on_accept(self):
        accept = SOURCE[SOURCE.index("    def accept"):]
        for widget in PLACEMENT:
            if widget.endswith("_combo"):
                continue
            self.assertIn(f"self.{widget}.isChecked()", accept, widget)
        for widget in ("egress_gate_mode_combo", "max_tool_iterations_spin", "max_turn_tokens_spin", "local_data_ask_spin",
                       "layout_masthead_edit", "layout_disclaimer_checkbox", "layout_disclaimer_edit", "user_profile_combo"):
            self.assertIn(f"self.{widget}.", accept, widget)


if __name__ == "__main__":
    unittest.main()
