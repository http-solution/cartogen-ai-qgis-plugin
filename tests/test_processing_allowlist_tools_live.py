"""Live-QGIS tests for the generic Processing tool (#163, audit F27). Written without a QGIS install: CI's first run is their first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _layer(kind, crs, wkts, name):
    layer = QgsVectorLayer(f"{kind}?crs={crs}&field=name:string", name, "memory")
    feats = []
    for i, wkt in enumerate(wkts):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([f"{name}{i}"])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestGenericProcessingTool(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_an_unknown_parameter_is_rejected_with_the_valid_names(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        _layer("Point", "EPSG:4326", ["POINT(0 0)"], "pts")
        res = run_allowlisted_processing_algorithm("native:buffer", {"INPUT": "pts", "DISTANC": 5})
        self.assertIn("error", res)
        self.assertIn("DISTANC", res["error"])
        self.assertIn("DISTANCE", res["error"])

    def test_a_valid_buffer_still_works_with_the_definition_driven_sink(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        _layer("Point", "EPSG:4326", ["POINT(0 0)"], "pts")
        res = run_allowlisted_processing_algorithm("native:buffer", {"INPUT": "pts", "DISTANCE": 0.01}, new_layer_name="buf")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["layer_name"], "buf")
        self.assertEqual(res["feature_count"], 1)

    def test_a_report_table_is_read_back_and_kept_out_of_the_project_unless_named(self):
        """LR-7, live run 2026-11-20 row C16: report algorithms left their tables in the project. Unnamed: rows returned, nothing added. Named: kept."""
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        _layer("Point", "EPSG:4326", ["POINT(0 0)", "POINT(1 1)", "POINT(2 2)"], "pts")
        before = set(QgsProject.instance().mapLayers())
        res = run_allowlisted_processing_algorithm("native:listuniquevalues", {"INPUT": "pts", "FIELDS": "name"})
        self.assertTrue(res.get("success"), res)
        self.assertIs(res.get("layer_created"), False)
        self.assertEqual(set(QgsProject.instance().mapLayers()), before)
        self.assertEqual(res["table"]["row_count"], 3)         # the helper names the points pts0, pts1, pts2
        self.assertIn("NOT added", res["message"])
        kept = run_allowlisted_processing_algorithm("native:listuniquevalues", {"INPUT": "pts", "FIELDS": "name"}, new_layer_name="names_table")
        self.assertTrue(kept.get("success"), kept)
        self.assertEqual(len(QgsProject.instance().mapLayersByName("names_table")), 1)

    def test_a_spatial_result_of_the_same_kind_of_call_is_still_added(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        _layer("Point", "EPSG:4326", ["POINT(0 0)"], "pts")
        res = run_allowlisted_processing_algorithm("native:buffer", {"INPUT": "pts", "DISTANCE": 0.01})
        self.assertTrue(res.get("success"), res)
        self.assertEqual(len(QgsProject.instance().mapLayersByName("buffer_output")), 1)

    def test_select_by_location_changes_the_selection_and_keeps_the_layer_name(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        _layer("Polygon", "EPSG:4326", ["POLYGON((0 0,1 0,1 1,0 1,0 0))", "POLYGON((5 5,6 5,6 6,5 6,5 5))"], "districts")
        _layer("Point", "EPSG:4326", ["POINT(0.5 0.5)"], "pts")
        res = run_allowlisted_processing_algorithm(
            "native:selectbylocation", {"INPUT": "districts", "PREDICATE": [0], "INTERSECT": "pts", "METHOD": 0})
        self.assertTrue(res.get("success"), res)
        self.assertTrue(res.get("changed_existing_layer"))
        self.assertEqual(res["layer_name"], "districts")
        self.assertEqual(res["selected_feature_count"], 1)
        self.assertEqual(len(QgsProject.instance().mapLayersByName("districts")), 1)

    def test_a_multi_output_algorithm_returns_every_layer(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        _layer("LineString", "EPSG:4326", ["LINESTRING(0 0, 0.02 0)"], "roads")
        res = run_allowlisted_processing_algorithm(
            "native:serviceareafrompoint",
            {"INPUT": "roads", "START_POINT": "0,0", "STRATEGY": 0, "TRAVEL_COST2": 1000, "DEFAULT_SPEED": 50, "TOLERANCE": 0},
            new_layer_name="reach")
        self.assertTrue(res.get("success"), res)
        names = {res["layer_name"]} | {e["layer_name"] for e in res.get("additional_outputs", [])}
        self.assertGreaterEqual(len(names), 2, res)
        for name in names:
            self.assertTrue(QgsProject.instance().mapLayersByName(name), name)


if __name__ == "__main__":
    unittest.main()
