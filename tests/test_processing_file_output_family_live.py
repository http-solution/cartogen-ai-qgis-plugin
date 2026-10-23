"""Live run of the PLAN-005 wave E1 algorithms (statistics reports and the two GDAL vector tools) through the generic tool, in the QGIS image
CI uses. Every result is read back from real QGIS objects: the numbers in `statistics`, the temporary report file, the layer and its feature
count. An id that fails its first run leaves the allow-list with the reason written next to it (as for the mesh and GRASS families).
Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestFileOutputFamily(unittest.TestCase):
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
        towns = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:integer", "towns", "memory")
        features = []
        for i, (x, y, pop) in enumerate(((0.5, 0.5, 10), (1.0, 1.2, 40), (1.1, 0.4, 70), (3.0, 3.1, 100), (3.4, 3.3, 5), (2.2, 1.9, 60))):
            f = QgsFeature(towns.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({x} {y})"))
            f.setAttributes([f"t{i}", pop])
            features.append(f)
        towns.dataProvider().addFeatures(features)
        QgsProject.instance().addMapLayer(towns)

    def _run(self, alg_id, params, **kw):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        result = run_allowlisted_processing_algorithm(alg_id, params, **kw)
        print(f"FILEOUTPUTRESULT {alg_id} {'ok' if result.get('success') else 'FAILED'} {str(result)[:300]}")
        self.assertTrue(result.get("success"), result)
        return result

    def _assert_report_is_ours(self, result):
        files = result.get("report_files") or {}
        self.assertTrue(files, result)
        for path in files.values():
            self.assertTrue(os.path.isfile(path), path)

    def test_basic_statistics_for_fields_returns_the_numbers(self):
        result = self._run("native:basicstatisticsforfields", {"INPUT_LAYER": "towns", "FIELD_NAME": "pop"})
        self.assertAlmostEqual(result["statistics"]["MEAN"], 47.5)
        self.assertEqual(result["statistics"]["MAX"], 100)
        self.assertEqual(result["statistics"]["MIN"], 5)
        self._assert_report_is_ours(result)

    def test_a_report_path_the_caller_supplies_is_ignored(self):
        evil = os.path.join(self.folder, "evil_report.html")
        result = self._run("native:basicstatisticsforfields", {"INPUT_LAYER": "towns", "FIELD_NAME": "pop", "OUTPUT_HTML_FILE": evil})
        self.assertFalse(os.path.exists(evil))
        self._assert_report_is_ours(result)

    def test_list_unique_values(self):
        result = self._run("native:listuniquevalues", {"INPUT": "towns", "FIELDS": ["pop"]}, new_layer_name="unique_pops")
        self.assertEqual(result["statistics"]["TOTAL_VALUES"], 6)
        self.assertEqual(QgsProject.instance().mapLayersByName("unique_pops")[0].featureCount(), 6)

    def test_nearest_neighbour_analysis(self):
        result = self._run("native:nearestneighbouranalysis", {"INPUT": "towns"})
        self.assertEqual(result["statistics"]["POINT_COUNT"], 6)
        self.assertIn("NN_INDEX", result["statistics"])

    def test_raster_layer_statistics(self):
        result = self._run("native:rasterlayerstatistics", {"INPUT": "dem", "BAND": 1})
        self.assertIn("MEAN", result["statistics"])
        self.assertLessEqual(result["statistics"]["MIN"], result["statistics"]["MAX"])
        self._assert_report_is_ours(result)

    def test_raster_layer_unique_values_report(self):
        result = self._run("native:rasterlayeruniquevaluesreport", {"INPUT": "dem2", "BAND": 1}, new_layer_name="raster_classes")
        self.assertGreater(result["statistics"]["TOTAL_PIXEL_COUNT"], 0)

    def test_raster_surface_volume(self):
        result = self._run("native:rastersurfacevolume", {"INPUT": "dem", "BAND": 1, "LEVEL": 10, "METHOD": 0}, new_layer_name="volume_table")
        self.assertIn("VOLUME", result["statistics"])

    def test_polygonize_gives_a_small_memory_layer_flagged_temporary(self):
        result = self._run("gdal:polygonize", {"INPUT": "dem", "BAND": 1, "FIELD": "DN", "EIGHT_CONNECTEDNESS": False}, new_layer_name="cells")
        layer = QgsProject.instance().mapLayersByName("cells")[0]
        self.assertGreater(layer.featureCount(), 0)
        self.assertEqual(layer.providerType(), "memory")      # rule R1: a small result is copied so the project does not point at a temporary file
        self.assertTrue(result.get("temporary"))

    def test_contour_polygons(self):
        result = self._run("gdal:contour_polygon", {"INPUT": "dem", "BAND": 1, "INTERVAL": 10, "FIELD_NAME_MIN": "ELEV_MIN",
                                                    "FIELD_NAME_MAX": "ELEV_MAX"}, new_layer_name="bands")
        layer = QgsProject.instance().mapLayersByName("bands")[0]
        self.assertGreater(layer.featureCount(), 1)
        self.assertTrue(result.get("temporary"))

    def test_raw_arguments_are_still_refused(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        result = run_allowlisted_processing_algorithm("gdal:polygonize", {"INPUT": "dem", "BAND": 1, "EXTRA": "-q"})
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
