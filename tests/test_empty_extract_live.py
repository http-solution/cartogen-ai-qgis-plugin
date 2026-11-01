"""DEF-22: a zero-feature extraction names the likely cause, run through the real Processing algorithm.

Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestEmptyExtractLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _layer(self, name, geometry, rows, crs="EPSG:4326"):
        layer = QgsVectorLayer(f"{geometry}?crs={crs}&field=gov:string", name, "memory")
        feats = []
        for wkt, gov in rows:
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([gov])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_an_expression_that_matches_nothing_lists_the_field_values(self):
        from cartogen_ai.core.agent.tools import processing_allowlist_tools as tools
        self._layer("districts", "Polygon", [("POLYGON((0 0,1 0,1 1,0 1,0 0))", "Taizz"), ("POLYGON((2 2,3 2,3 3,2 3,2 2))", "Aden")])
        result = tools.run_allowlisted_processing_algorithm(
            "native:extractbyexpression", {"INPUT": "districts", "EXPRESSION": "\"gov\" = 'Taiz'"}, new_layer_name="taiz_only")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result.get("feature_count"), 0, result)
        self.assertIn("'Taizz'", result.get("why_empty", ""), result)

    def test_a_location_test_against_non_overlapping_layers_says_so(self):
        from cartogen_ai.core.agent.tools import processing_allowlist_tools as tools
        self._layer("facilities", "Point", [("POINT(50 50)", "x")])
        self._layer("districts", "Polygon", [("POLYGON((0 0,1 0,1 1,0 1,0 0))", "Taizz")])
        result = tools.run_allowlisted_processing_algorithm(
            "native:extractbylocation", {"INPUT": "facilities", "PREDICATE": [0], "INTERSECT": "districts"}, new_layer_name="inside")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result.get("feature_count"), 0, result)
        self.assertIn("extents do not overlap", result.get("why_empty", ""), result)


if __name__ == "__main__":
    unittest.main()
