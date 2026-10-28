"""DEF-11 (hand run D6), live QGIS: calculate_raster_change_detection given FILE PATHS, as the D6 prompt supplies them, loads the rasters and
produces the change layer. Written without a local QGIS: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsProject
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

_PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
        'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _write_asc(folder, name, value):
    path = os.path.join(folder, name + ".asc")
    rows = "\n".join(" ".join(str(value) for _ in range(4)) for _ in range(4))
    with open(path, "w") as handle:
        handle.write(f"ncols 4\nnrows 4\nxllcorner 44.0\nyllcorner 15.0\ncellsize 0.01\nNODATA_value -9999\n{rows}\n")
    with open(os.path.join(folder, name + ".prj"), "w") as handle:
        handle.write(_PRJ)
    return path


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestChangeDetectionByPath(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.before = _write_asc(self.tmp.name, "before_fixture", 10)
        self.after = _write_asc(self.tmp.name, "after_fixture", 30)

    def test_file_paths_load_the_rasters_and_make_the_change_layer(self):
        from cartogen_ai.core.agent.tools.multimodal_remote_sensing import calculate_raster_change_detection
        result = calculate_raster_change_detection(self.before, self.after)
        self.assertTrue(result.get("success"), result)
        self.assertIn("was not in the project", result["loaded"])
        names = {layer.name() for layer in QgsProject.instance().mapLayers().values()}
        self.assertTrue({"before_fixture", "after_fixture"} <= names, names)
        self.assertIn("change_detection_after_fixture_vs_before_fixture", names)

    def test_layer_names_still_work_and_load_nothing_extra(self):
        from cartogen_ai.core.agent.tools.multimodal_remote_sensing import calculate_raster_change_detection
        from cartogen_ai.core.agent.tools.vector_tools import add_layer_from_path
        for path in (self.before, self.after):
            self.assertTrue(add_layer_from_path(path).get("success"))
        count = len(QgsProject.instance().mapLayers())
        result = calculate_raster_change_detection("before_fixture", "after_fixture")
        self.assertTrue(result.get("success"), result)
        self.assertNotIn("loaded", result)
        self.assertEqual(len(QgsProject.instance().mapLayers()), count + 1)

    def test_an_unknown_name_gets_a_helpful_error(self):
        from cartogen_ai.core.agent.tools.multimodal_remote_sensing import calculate_raster_change_detection
        result = calculate_raster_change_detection("nope", "after_fixture")
        self.assertIn("name of a raster layer", result["error"])


if __name__ == "__main__":
    unittest.main()
