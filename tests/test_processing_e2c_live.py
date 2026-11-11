"""PLAN-023 R11-4 (PLAN-006 package E2c): native:pointstopath and native:relief through the generic tool in the QGIS image CI uses. Read back from real QGIS objects: the line layer's
geometry (ordered points joined into one line of the right length) and the relief raster (a valid layer of the dem's size). A destination path the caller supplies is ignored. An id that fails its
first run leaves the allow-list with the reason written next to it (as for the mesh and GRASS families). Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestE2cFamily(unittest.TestCase):
    def setUp(self):
        from tests._geometry_probe import _make_rasters
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.folder = tempfile.mkdtemp()
        for name, path in _make_rasters(self.folder).items():
            QgsProject.instance().addMapLayer(QgsRasterLayer(path, name))
        track = QgsVectorLayer("Point?crs=EPSG:32636&field=seq:integer", "track", "memory")
        features = []
        for i, (x, y) in enumerate(((0.0, 0.0), (300.0, 0.0), (300.0, 400.0))):       # legs of 300 m and 400 m: 700 m in all
            f = QgsFeature(track.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({x} {y})"))
            f.setAttributes([i])
            features.append(f)
        track.dataProvider().addFeatures(features)
        QgsProject.instance().addMapLayer(track)

    def _run(self, alg_id, params, **kw):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        result = run_allowlisted_processing_algorithm(alg_id, params, **kw)
        print(f"E2CRESULT {alg_id} {'ok' if result.get('success') else 'FAILED'} {str(result)[:300]}")
        self.assertTrue(result.get("success"), result)
        return result

    def test_points_to_path_joins_the_ordered_points_into_one_line(self):
        self._run("native:pointstopath", {"INPUT": "track", "ORDER_EXPRESSION": '"seq"', "CLOSE_PATH": False}, new_layer_name="track_path")
        layer = QgsProject.instance().mapLayersByName("track_path")[0]
        self.assertEqual(layer.featureCount(), 1)
        self.assertAlmostEqual(next(layer.getFeatures()).geometry().length(), 700.0, places=3)

    def test_a_text_folder_the_caller_supplies_is_ignored(self):
        evil = os.path.join(self.folder, "evil_dir")
        self._run("native:pointstopath", {"INPUT": "track", "ORDER_EXPRESSION": '"seq"', "OUTPUT_TEXT_DIR": evil}, new_layer_name="track_path2")
        self.assertFalse(os.path.exists(evil))

    def test_relief_gives_a_raster_of_the_dems_size(self):
        self._run("native:relief", {"INPUT": "dem", "Z_FACTOR": 1.0, "AUTO_COLORS": True}, new_layer_name="dem_relief")
        layer = QgsProject.instance().mapLayersByName("dem_relief")[0]
        self.assertTrue(layer.isValid())
        self.assertEqual((layer.width(), layer.height()), (40, 40))


if __name__ == "__main__":
    unittest.main()
