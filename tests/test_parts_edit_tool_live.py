"""PLAN-023 R9-2: edit_parts_and_rings on real QGIS geometries: a hole of side 4 in a 10 x 10 square takes the area from 100 to 84 and filling it restores 100; a second part,
deleting a part, the refusals (hole outside the polygon, single-part layer, last part) and one undo. Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False

SQUARE = "POLYGON((0 0,10 0,10 10,0 10,0 0))"
HOLE = "POLYGON((3 3,3 7,7 7,7 3,3 3))"


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestEditPartsAndRingsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _layer(self, spec, wkt, name):
        layer = QgsVectorLayer(f"{spec}?crs=EPSG:32636&field=name:string", name, "memory")
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        layer.dataProvider().addFeatures([feature])
        QgsProject.instance().addMapLayer(layer)
        return layer, next(layer.getFeatures()).id()

    def _call(self, layer, fid, **kw):
        from cartogen_ai.core.agent.tools.parts_edit_tool import edit_parts_and_rings
        return edit_parts_and_rings(layer.name(), fid, **kw)

    def test_the_first_call_is_only_a_preview(self):
        layer, fid = self._layer("Polygon", SQUARE, "sq")
        out = self._call(layer, fid, action="add_ring", geometry_wkt=HOLE)
        self.assertEqual(out.get("status"), "PREVIEW_REQUIRED")
        self.assertAlmostEqual(layer.getFeature(fid).geometry().area(), 100.0)

    def test_a_hole_takes_the_area_to_84_and_filling_it_restores_100(self):
        layer, fid = self._layer("Polygon", SQUARE, "sq")
        out = self._call(layer, fid, action="add_ring", geometry_wkt=HOLE, confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertAlmostEqual(out["area_after"], 84.0)
        out = self._call(layer, fid, action="fill_ring", x=5.0, y=5.0, confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertAlmostEqual(out["area_after"], 100.0)

    def test_fill_ring_previews_the_hole_it_found_and_a_point_outside_every_hole_is_refused(self):
        layer, fid = self._layer("Polygon", SQUARE, "sq")
        self._call(layer, fid, action="add_ring", geometry_wkt=HOLE, confirmed=True)
        preview = self._call(layer, fid, action="fill_ring", x=5.0, y=5.0)
        self.assertEqual(preview["status"], "PREVIEW_REQUIRED")
        self.assertEqual((preview["arguments"]["action"], preview["arguments"]["ring_index"]), ("delete_ring", 1))
        self.assertIn("No hole", self._call(layer, fid, action="fill_ring", x=1.0, y=1.0, confirmed=True)["error"])

    def test_delete_ring_by_number(self):
        layer, fid = self._layer("Polygon", SQUARE, "sq")
        self._call(layer, fid, action="add_ring", geometry_wkt=HOLE, confirmed=True)
        out = self._call(layer, fid, action="delete_ring", ring_index=1, confirmed=True)
        self.assertAlmostEqual(out["area_after"], 100.0)
        self.assertIn("does not exist", self._call(layer, fid, action="delete_ring", ring_index=1, confirmed=True)["error"])

    def test_a_hole_outside_the_polygon_is_refused_and_changes_nothing(self):
        layer, fid = self._layer("Polygon", SQUARE, "sq")
        out = self._call(layer, fid, action="add_ring", geometry_wkt="POLYGON((20 20,20 24,24 24,24 20,20 20))", confirmed=True)
        self.assertIn("error", out)
        self.assertAlmostEqual(layer.getFeature(fid).geometry().area(), 100.0)

    def test_add_part_and_delete_part_on_a_multipolygon_layer(self):
        layer, fid = self._layer("MultiPolygon", f"MULTIPOLYGON((({SQUARE[9:-2]})))", "mp")
        out = self._call(layer, fid, action="add_part", geometry_wkt="POLYGON((20 0,30 0,30 10,20 10,20 0))", confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertEqual((out["parts_before"], out["parts_after"]), (1, 2))
        self.assertAlmostEqual(out["area_after"], 200.0)
        out = self._call(layer, fid, action="delete_part", part_index=1, confirmed=True)
        self.assertEqual(out["parts_after"], 1)
        self.assertIn("only one part", self._call(layer, fid, action="delete_part", part_index=0, confirmed=True)["error"])

    def test_a_part_that_overlaps_is_refused(self):
        layer, fid = self._layer("MultiPolygon", f"MULTIPOLYGON((({SQUARE[9:-2]})))", "mp")
        out = self._call(layer, fid, action="add_part", geometry_wkt="POLYGON((5 5,15 5,15 15,5 15,5 5))", confirmed=True)
        self.assertIn("error", out)
        self.assertAlmostEqual(layer.getFeature(fid).geometry().area(), 100.0)

    def test_a_single_part_layer_cannot_take_a_second_part(self):
        layer, fid = self._layer("Polygon", SQUARE, "sq")
        self.assertIn("single-part", self._call(layer, fid, action="add_part", geometry_wkt="POLYGON((20 0,30 0,30 10,20 10,20 0))", confirmed=True)["error"])

    def test_one_undo_restores_the_square_when_the_layer_is_in_edit_mode(self):
        layer, fid = self._layer("Polygon", SQUARE, "sq")
        layer.startEditing()
        self._call(layer, fid, action="add_ring", geometry_wkt=HOLE, confirmed=True)
        self.assertAlmostEqual(layer.getFeature(fid).geometry().area(), 84.0)
        layer.undoStack().undo()
        self.assertAlmostEqual(layer.getFeature(fid).geometry().area(), 100.0)
        self.assertTrue(layer.isEditable())


if __name__ == "__main__":
    unittest.main()
