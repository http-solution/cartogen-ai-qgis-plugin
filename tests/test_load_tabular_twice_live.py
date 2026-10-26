"""Live QGIS: loading the same file twice does not add a second layer (1.18.2 hand test D5: three identical loads in one turn tripped the
loop guard). Written without a local QGIS: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsProject
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestLoadTabularTwice(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as fh:
            fh.write("district,rain_mm\nAden,85\nLahj,90\n")
        self.addCleanup(os.remove, self.path)

    def test_second_identical_load_adds_nothing_and_says_so(self):
        from cartogen_ai.core.agent.tools.vector_tools import load_tabular_data_as_layer
        first = load_tabular_data_as_layer(self.path, layer_name="forecast")
        self.assertTrue(first.get("success"), first)
        self.assertNotIn("already_loaded", first)
        second = load_tabular_data_as_layer(self.path, layer_name="forecast")
        self.assertTrue(second.get("success"), second)
        self.assertTrue(second.get("already_loaded"), second)
        self.assertEqual(len(QgsProject.instance().mapLayersByName("forecast")), 1)
        self.assertEqual(second["feature_count"], 2)


if __name__ == "__main__":
    unittest.main()
