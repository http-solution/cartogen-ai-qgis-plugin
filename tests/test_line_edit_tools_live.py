"""PLAN-023 R9-3 on real QGIS geometries: reverse swaps the first and last vertex; a 10 m line offset by 2 m gives a parallel line of length 10 two metres to the left (negative: to
the right); trim_extend_lines extends a line that stops short and trims one that overshoots; reshape cuts a 4 x 2 notch out of a 10 x 10 square (area 92) and refuses a line
that does not cross; one undo. Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestLineEditToolsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _layer(self, spec, wkts, name):
        layer = QgsVectorLayer(f"{spec}?crs=EPSG:32636&field=name:string", name, "memory")
        feats = []
        for i, wkt in enumerate(wkts):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([f"f{i}"])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer, [f.id() for f in layer.getFeatures()]

    def _points(self, layer, fid):
        return [(p.x(), p.y()) for p in layer.getFeature(fid).geometry().asPolyline()]

    def test_reverse_line_previews_then_swaps_first_and_last(self):
        from cartogen_ai.core.agent.tools.line_edit_tools import reverse_line
        layer, ids = self._layer("LineString", ["LINESTRING(0 0,4 0,4 3)"], "ln")
        self.assertEqual(reverse_line("ln")["status"], "PREVIEW_REQUIRED")
        self.assertEqual(self._points(layer, ids[0])[0], (0.0, 0.0))
        out = reverse_line("ln", confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertEqual(self._points(layer, ids[0]), [(4.0, 3.0), (4.0, 0.0), (0.0, 0.0)])

    def test_offset_curve_makes_a_parallel_line_of_the_same_length_to_the_left(self):
        from cartogen_ai.core.agent.tools.line_edit_tools import offset_curve
        layer, _ids = self._layer("LineString", ["LINESTRING(0 0,10 0)"], "ln")
        out = offset_curve("ln", 2.0)
        self.assertTrue(out.get("success"), out)
        new = QgsProject.instance().mapLayersByName("ln_offset")[0]
        feature = next(new.getFeatures())
        self.assertAlmostEqual(feature.geometry().length(), 10.0)
        self.assertAlmostEqual(feature.geometry().asPolyline()[0].y(), 2.0)
        self.assertEqual(feature["name"], "f0")
        right = offset_curve("ln", -2.0, output_name="ln_right")
        self.assertAlmostEqual(next(QgsProject.instance().mapLayersByName("ln_right")[0].getFeatures()).geometry().asPolyline()[0].y(), -2.0)
        self.assertEqual(right["features"], 1)
        self.assertEqual(next(layer.getFeatures()).geometry().asWkt(), QgsGeometry.fromWkt("LINESTRING(0 0,10 0)").asWkt())      # the input is untouched

    def test_trim_extend_lines_extends_a_short_line_and_trims_an_overshoot(self):
        from cartogen_ai.core.agent.tools.line_edit_tools import trim_extend_lines
        layer, ids = self._layer("LineString", ["LINESTRING(0 0,9 0)", "LINESTRING(0 3,11 3)", "LINESTRING(10 -5,10 5)"], "ln")
        self.assertEqual(trim_extend_lines("ln", 1.5)["status"], "PREVIEW_REQUIRED")
        out = trim_extend_lines("ln", 1.5, confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertEqual((out["ends_moved"], out["features_changed"]), (2, 2))
        self.assertEqual(self._points(layer, ids[0])[-1], (10.0, 0.0))
        self.assertEqual(self._points(layer, ids[1])[-1], (10.0, 3.0))
        self.assertEqual(self._points(layer, ids[2]), [(10.0, -5.0), (10.0, 5.0)])
        again = trim_extend_lines("ln", 1.5)
        self.assertEqual(again.get("ends_moved"), 0)

    def test_reshape_cuts_a_notch_and_a_line_that_misses_is_refused(self):
        from cartogen_ai.core.agent.tools.line_edit_tools import reshape_geometry
        layer, ids = self._layer("Polygon", ["POLYGON((0 0,10 0,10 10,0 10,0 0))"], "sq")
        out = reshape_geometry("sq", ids[0], "LINESTRING(3 -1,3 2,7 2,7 -1)", confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertAlmostEqual(out["area_after"], 92.0)
        miss = reshape_geometry("sq", ids[0], "LINESTRING(20 20,30 30)", confirmed=True)
        self.assertIn("does not cross", miss["error"])
        self.assertAlmostEqual(layer.getFeature(ids[0]).geometry().area(), 92.0)

    def test_one_undo_restores_the_line_when_the_layer_is_in_edit_mode(self):
        from cartogen_ai.core.agent.tools.line_edit_tools import reverse_line
        layer, ids = self._layer("LineString", ["LINESTRING(0 0,4 0)"], "ln")
        layer.startEditing()
        reverse_line("ln", confirmed=True)
        self.assertEqual(self._points(layer, ids[0])[0], (4.0, 0.0))
        layer.undoStack().undo()
        self.assertEqual(self._points(layer, ids[0])[0], (0.0, 0.0))
        self.assertTrue(layer.isEditable())

    def test_a_polygon_layer_is_refused_by_the_line_only_tools(self):
        from cartogen_ai.core.agent.tools.line_edit_tools import offset_curve, reverse_line
        self._layer("Polygon", ["POLYGON((0 0,1 0,1 1,0 0))"], "pg")
        self.assertIn("not a line layer", reverse_line("pg")["error"])
        self.assertIn("not a line layer", offset_curve("pg", 1.0)["error"])


if __name__ == "__main__":
    unittest.main()
