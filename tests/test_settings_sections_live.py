"""PLAN-039 slice 2, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): the regrouped Settings
window builds, the two collapsible groups open themselves when something inside is on, and every moved setting still saves and reloads."""
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
class TestSettingsSections(unittest.TestCase):
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

    def test_defaults_collapsed_groups_are_hidden(self):
        dialog = self._dialog()
        titles = {title: body for title, _toggle, body in dialog._collapsibles}
        self.assertEqual(set(titles), {"Experimental options", "Diagnostic recording"})
        self.assertTrue(all(body.isHidden() for body in titles.values()))

    def test_a_group_opens_itself_when_a_setting_inside_is_on(self):
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_API_TRACE_ENABLED, SETTINGS_PLAN_VALIDATION_GATE_ENABLED
        settings = QgsSettings()
        settings.setValue(SETTINGS_API_TRACE_ENABLED, True)
        settings.setValue(SETTINGS_PLAN_VALIDATION_GATE_ENABLED, True)
        dialog = self._dialog()
        for title, _toggle, body in dialog._collapsibles:
            self.assertFalse(body.isHidden(), title)

    def test_the_arrow_toggle_shows_and_hides_the_group(self):
        dialog = self._dialog()
        _title, toggle, body = next(c for c in dialog._collapsibles if c[0] == "Diagnostic recording")
        toggle.setChecked(True)
        self.assertFalse(body.isHidden())
        toggle.setChecked(False)
        self.assertTrue(body.isHidden())

    def test_every_moved_setting_saves_and_reloads(self):
        from cartogen_ai.infrastructure.settings_keys import (
            SETTINGS_API_TRACE_ENABLED, SETTINGS_EGRESS_GATE_MODE, SETTINGS_EGRESS_GATE_STRICT, SETTINGS_EVIDENCE_ENABLED,
            SETTINGS_PLAN_VALIDATION_GATE_ENABLED, SETTINGS_PROJECT_INSPECTOR_ENABLED,
        )
        dialog = self._dialog()
        dialog.egress_gate_mode_combo.setCurrentIndex(dialog.egress_gate_mode_combo.findData("enforce"))
        dialog.egress_gate_strict_checkbox.setChecked(True)
        dialog.persist_history_checkbox.setChecked(False)
        dialog.persist_project_memory_checkbox.setChecked(True)
        dialog.evidence_checkbox.setChecked(True)
        dialog.api_trace_checkbox.setChecked(True)
        dialog.project_inspector_checkbox.setChecked(True)
        dialog.plan_validation_gate_checkbox.setChecked(True)
        dialog.max_tool_iterations_spin.setValue(7)
        dialog.local_data_ask_spin.setValue(12)
        dialog.layout_masthead_edit.setText("#123456")
        dialog.accept()

        settings = QgsSettings()
        self.assertEqual(settings.value(SETTINGS_EGRESS_GATE_MODE), "enforce")
        for key in (SETTINGS_EGRESS_GATE_STRICT, SETTINGS_EVIDENCE_ENABLED, SETTINGS_API_TRACE_ENABLED,
                    SETTINGS_PROJECT_INSPECTOR_ENABLED, SETTINGS_PLAN_VALIDATION_GATE_ENABLED):
            self.assertTrue(settings.value(key, False, type=bool), key)

        again = self._dialog()
        self.assertEqual(again.egress_gate_mode_combo.currentData(), "enforce")
        self.assertTrue(again.egress_gate_strict_checkbox.isChecked())
        self.assertFalse(again.persist_history_checkbox.isChecked())
        self.assertTrue(again.persist_project_memory_checkbox.isChecked())
        self.assertEqual(again.max_tool_iterations_spin.value(), 7)
        self.assertEqual(again.local_data_ask_spin.value(), 12)
        self.assertEqual(again.layout_masthead_edit.text(), "#123456")
        # the groups that hold the on switches are open, so nothing in effect is hidden
        for title, _toggle, body in again._collapsibles:
            self.assertFalse(body.isHidden(), title)


if __name__ == "__main__":
    unittest.main()
