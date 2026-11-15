"""PLAN-053 stage 1 in a real QGIS: the versions are read from QGIS itself, the CI image (QGIS 4.2.2) is inside the supported range, and the start-up
check logs without a warning and without raising. Written without a QGIS install: CI's first run is its first execution."""
import os
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import Qgis
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestEnvironmentLive(unittest.TestCase):
    def test_qgis_qt_and_python_are_read_and_the_ci_image_is_supported(self):
        from cartogen_ai.core import environment
        found = environment.detect()
        self.assertEqual(found["qgis"], Qgis.QGIS_VERSION)
        self.assertTrue(found["qt"])
        self.assertGreaterEqual(environment.parse_version(found["qgis"])[:2], environment.MINIMUM_QGIS)
        self.assertEqual(environment.findings(found), [], environment.describe(found))

    def test_the_start_up_check_stays_quiet_on_a_supported_machine_and_warns_on_an_old_one(self):
        from unittest import mock
        import plugin_main
        from cartogen_ai.core import environment
        plugin = plugin_main.CartogenAi.__new__(plugin_main.CartogenAi)
        plugin.iface = MagicMock()
        plugin._check_environment()
        plugin.iface.messageBar().pushWarning.assert_not_called()
        old = dict(environment.detect(), qgis="3.40.1")
        with mock.patch.object(environment, "detect", return_value=old):
            plugin._check_environment()
        plugin.iface.messageBar().pushWarning.assert_called_once()
        self.assertIn("3.40.1", plugin.iface.messageBar().pushWarning.call_args[0][1])


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestSettingsSectionLive(unittest.TestCase):
    """PLAN-053 stage 3, real QGIS (written without one; CI's first run is its first execution): Settings has a 'This computer' section whose text is the
    environment report and whose Copy button puts exactly that text on the clipboard."""

    def test_the_section_shows_the_report_and_copy_puts_it_on_the_clipboard(self):
        from tests.test_chat_widget_live import _boot_qgis
        why = _boot_qgis()
        if why:
            self.skipTest(why)
        from qgis.PyQt.QtWidgets import QApplication, QPlainTextEdit, QPushButton
        from cartogen_ai.core.ui.settings_dialog import CartogenAiSettingsDialog
        dialog = CartogenAiSettingsDialog()
        box = dialog.findChild(QPlainTextEdit, "environmentReportText")
        button = dialog.findChild(QPushButton, "environmentCopyButton")
        self.assertIsNotNone(box)
        self.assertIsNotNone(button)
        self.assertTrue(box.isReadOnly())
        self.assertIn("Cartogen AI", box.toPlainText())
        self.assertIn(Qgis.QGIS_VERSION, box.toPlainText())
        self.assertIn("inside the range", box.toPlainText())
        button.click()
        self.assertEqual(QApplication.clipboard().text(), box.toPlainText())


if __name__ == "__main__":
    unittest.main()
