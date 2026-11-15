"""PLAN-023 R1-2 and R1-3 in real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): the persona picker with its two dropdowns and readiness panel, the Settings
window and the onboarding dialog that embed it, and the migration of a stored old choice through the real QgsSettings."""
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
class TestPersonaPickerLive(unittest.TestCase):
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

    def test_the_picker_lists_all_fifteen_personas_and_the_panel_follows_the_choice(self):
        from cartogen_ai.core.ui.persona_picker import PersonaPicker
        picker = PersonaPicker()
        self.assertEqual(picker.primary_combo.count(), 15)
        self.assertEqual(picker.secondary_combo.count(), 16)                      # none + 15
        self.assertEqual(picker.selection(), ("general", ""))
        self.assertIn("GIS Generalist", picker.readiness_panel.toPlainText())
        picker.set_selection("public_health", "logistics")
        text = picker.readiness_panel.toPlainText()
        for expected in ("Primary: Public Health / Epidemiology", "Secondary: Logistics / Supply Chain", "Not built yet", "Moran's I", "vehicle routing", "Every tool stays available"):
            self.assertIn(expected, text)
        self.assertTrue(picker.readiness_panel.isReadOnly())

    def test_choosing_the_secondary_as_the_primary_drops_the_secondary_and_unknown_ids_fall_back(self):
        from cartogen_ai.core.ui.persona_picker import PersonaPicker
        picker = PersonaPicker(primary="agriculture", secondary="logistics")
        picker.primary_combo.setCurrentIndex(picker.primary_combo.findData("logistics"))
        self.assertEqual(picker.selection(), ("logistics", ""))
        self.assertNotIn("Secondary:", picker.readiness_panel.toPlainText())
        picker.set_selection("nonsense", "also nonsense")
        self.assertEqual(picker.selection(), ("general", ""))

    def test_the_settings_window_embeds_the_picker_and_saves_both_choices(self):
        from cartogen_ai.core.personas.selection import read_selection
        from cartogen_ai.core.ui.settings_dialog import CartogenAiSettingsDialog
        dialog = CartogenAiSettingsDialog()
        self.assertIs(dialog.user_profile_combo, dialog.persona_picker.primary_combo)
        dialog.persona_picker.set_selection("engineering", "utilities")
        dialog.accept()
        settings = QgsSettings()
        self.assertEqual(read_selection(settings), ("engineering", "utilities"))
        self.assertEqual(settings.value("cartogen_ai/user_profile"), "engineering")             # the old key mirrors the primary
        reopened = CartogenAiSettingsDialog()
        self.assertEqual(reopened.persona_picker.selection(), ("engineering", "utilities"))

    def test_an_old_stored_choice_becomes_the_primary_persona_on_the_first_read(self):
        from cartogen_ai.core.services.prompt_refiner import get_persona_selection, get_user_profile
        settings = QgsSettings()
        settings.setValue("cartogen_ai/user_profile", "transport")
        self.assertEqual(get_user_profile(), "transport")
        self.assertEqual(settings.value("cartogen_ai/persona_primary"), "transport")
        self.assertEqual(get_persona_selection(), ("transport", ""))
        from cartogen_ai.core.ui.settings_dialog import CartogenAiSettingsDialog
        self.assertEqual(CartogenAiSettingsDialog().persona_picker.selection(), ("transport", ""))

    def test_the_onboarding_dialog_suggests_a_persona_from_the_role_until_the_person_picks_one(self):
        from cartogen_ai.core.ui.onboarding_dialog import OnboardingDialog
        dialog = OnboardingDialog()
        dialog.role_combo.setCurrentIndex(dialog.role_combo.findData("urban_planner"))
        self.assertEqual(dialog.persona_picker.selection()[0], "urban_planning")
        dialog.role_combo.setCurrentIndex(dialog.role_combo.findData("researcher"))
        self.assertEqual(dialog.persona_picker.selection()[0], "research")
        dialog.persona_picker.primary_combo.setCurrentIndex(dialog.persona_picker.primary_combo.findData("agriculture"))
        dialog.persona_picker.primary_combo.activated.emit(dialog.persona_picker.primary_combo.currentIndex())     # a person's own pick
        dialog.role_combo.setCurrentIndex(dialog.role_combo.findData("urban_planner"))
        self.assertEqual(dialog.persona_picker.selection()[0], "agriculture")                   # the role no longer overwrites it
        self.assertIn("Not built yet", dialog.persona_picker.readiness_panel.toPlainText())


if __name__ == "__main__":
    unittest.main()
