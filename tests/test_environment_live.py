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


if __name__ == "__main__":
    unittest.main()
