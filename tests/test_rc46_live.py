"""Live-QGIS checks for the rc46 changes that need a real QGIS: the layer-kind check refuses a raster where a table is needed, a GRASS algorithm
still runs through the repainting feedback, and the dedicated-tool hint for the raster calculator. Written without a QGIS install: CI's first
run is its first execution."""
import tempfile
import unittest

try:
    from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestRc46Live(unittest.TestCase):
    def setUp(self):
        from tests._geometry_probe import _make_rasters
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.pts = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=val:double", "pts", "memory")
        for i in range(3):
            f = QgsFeature(self.pts.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({i + 0.5} {i + 0.5})"))
            f.setAttributes([f"p{i}", float(i + 1)])
            self.pts.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(self.pts)
        for name, path in _make_rasters(tempfile.mkdtemp()).items():
            QgsProject.instance().addMapLayer(QgsRasterLayer(path, name))

    def test_a_raster_given_as_a_table_is_refused_before_anything_runs(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        result = run_allowlisted_processing_algorithm("native:reclassifybylayer", {"INPUT_RASTER": "dem", "RASTER_BAND": 1, "INPUT_TABLE": "dem2",
                                                                                  "MIN_FIELD": "val", "MAX_FIELD": "val", "VALUE_FIELD": "val"})
        self.assertIn("error", result)
        self.assertIn("needs a vector layer", result["error"], result)

    def test_a_vector_in_a_raster_stack_is_still_refused(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        result = run_allowlisted_processing_algorithm("native:cellstackpercentile", {"INPUT": ["dem", "pts"], "REFERENCE_LAYER": "dem"})
        self.assertIn("error", result)

    def test_a_grass_algorithm_still_runs_through_the_repainting_feedback(self):
        if QgsApplication.processingRegistry().algorithmById("grass:r.slope.aspect") is None:
            self.skipTest("the GRASS provider is not installed in this QGIS")
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        result = run_allowlisted_processing_algorithm("grass:r.slope.aspect", {"elevation": "dem"}, new_layer_name="slope_rc46")
        self.assertTrue(result.get("success"), result)

    def test_the_raster_calculator_ids_point_at_the_dedicated_tool(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        result = run_allowlisted_processing_algorithm("gdal:rastercalculator", {"FORMULA": "A>1"})
        self.assertEqual(result.get("use_tool"), "raster_calculator")

    def test_a_loosely_typed_layout_name_is_found(self):
        from qgis.core import QgsPrintLayout

        from cartogen_ai.core.agent.tools._layout_names import lookup
        layout = QgsPrintLayout(QgsProject.instance())
        layout.initializeDefaults()
        layout.setName("Layout_Test_Layout")
        QgsProject.instance().layoutManager().addLayout(layout)
        self.assertEqual(lookup(QgsProject.instance().layoutManager(), "Test Layout").name(), "Layout_Test_Layout")
        self.assertIsNone(lookup(QgsProject.instance().layoutManager(), "Something Else"))


if __name__ == "__main__":
    unittest.main()
