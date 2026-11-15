"""PLAN-023 R10-3 on real QGIS layers: each renderer kind is applied and its type read back; merged and inverted keep the current look as the inner renderer; the previous style is
saved in the style manager and can be restored; the wrong geometry is refused and changes nothing; 2.5D colours read back. Written without a QGIS install: CI's first run is its first
execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestSetRendererLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _layer(self, spec, wkt, name):
        layer = QgsVectorLayer(f"{spec}?crs=EPSG:32636&field=name:string", name, "memory")
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes(["a"])
        layer.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _call(self, name, kind, **kw):
        from cartogen_ai.core.agent.tools.renderer_tool import set_renderer
        return set_renderer(name, kind, **kw)

    def test_every_kind_is_applied_and_its_type_read_back(self):
        layer = self._layer("Polygon", "POLYGON((0 0,10 0,10 10,0 10,0 0))", "pg")
        expected = {"merged_features": "mergedFeatureRenderer", "inverted_polygons": "invertedPolygonRenderer", "embedded": "embeddedSymbol", "no_symbols": "nullSymbol",
                    "2_5d": "25dRenderer", "single_symbol": "singleSymbol"}
        for kind, renderer_type in expected.items():
            out = self._call("pg", kind)
            self.assertTrue(out.get("success"), (kind, out))
            self.assertEqual(out["renderer_type_now"], renderer_type, kind)
            self.assertEqual(layer.renderer().type(), renderer_type, kind)

    def test_merged_and_inverted_keep_the_current_look_inside(self):
        layer = self._layer("Polygon", "POLYGON((0 0,10 0,10 10,0 10,0 0))", "pg")
        out = self._call("pg", "merged_features")
        self.assertEqual(out["inner_renderer"], "singleSymbol")
        again = self._call("pg", "inverted_polygons")
        self.assertEqual(again["inner_renderer"], "singleSymbol")                       # the merged wrapper was taken off, not nested
        self.assertEqual(layer.renderer().embeddedRenderer().type(), "singleSymbol")

    def test_the_previous_style_is_saved_and_can_be_restored(self):
        layer = self._layer("Polygon", "POLYGON((0 0,10 0,10 10,0 10,0 0))", "pg")
        out = self._call("pg", "no_symbols")
        self.assertEqual(out["previous_style_saved_as"], "before no_symbols")
        self.assertIn("before no_symbols", layer.styleManager().styles())
        self.assertEqual(layer.renderer().type(), "nullSymbol")
        self.assertTrue(layer.styleManager().setCurrentStyle("before no_symbols"))
        self.assertEqual(layer.renderer().type(), "singleSymbol")
        second = self._call("pg", "no_symbols")
        self.assertEqual(second["previous_style_saved_as"], "before no_symbols (2)")

    def test_two_point_five_d_colours_read_back(self):
        layer = self._layer("Polygon", "POLYGON((0 0,10 0,10 10,0 10,0 0))", "pg")
        out = self._call("pg", "2_5d", options={"roof_color": "#ff0000", "wall_color": "#00ff00", "shadow": False})
        self.assertTrue(out.get("success"), out)
        renderer = layer.renderer()
        self.assertEqual(renderer.roofColor().name(), "#ff0000")
        self.assertEqual(renderer.wallColor().name(), "#00ff00")
        self.assertIn("error", self._call("pg", "2_5d", options={"roof_color": "notacolour"}))

    def test_the_wrong_geometry_is_refused_and_changes_nothing(self):
        line = self._layer("LineString", "LINESTRING(0 0,10 0)", "ln")
        before = line.renderer().type()
        self.assertIn("polygon layers", self._call("ln", "inverted_polygons")["error"])
        self.assertIn("polygon layers", self._call("ln", "2_5d")["error"])
        self.assertEqual(line.renderer().type(), before)
        self.assertEqual(self._call("ln", "merged_features")["renderer_type_now"], "mergedFeatureRenderer")
        self._layer("Point", "POINT(1 1)", "pt")
        self.assertIn("this is a point layer", self._call("pt", "merged_features")["error"])
        self.assertTrue(self._call("pt", "embedded").get("success"))


if __name__ == "__main__":
    unittest.main()
