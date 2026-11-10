"""PLAN-023 R9-1: edit_vertices on real QGIS geometries: a 10 x 10 square (area 100, 5 ring vertices) loses vertex 2 (a triangle, area 50), gains a vertex on an edge
without changing the area, moves a corner (area 150), refuses an invalid result and a point layer, and one undo restores it. Written without a QGIS install: CI's first run
is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestEditVerticesLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.layer = QgsVectorLayer("Polygon?crs=EPSG:32636&field=name:string", "sq", "memory")
        feature = QgsFeature(self.layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POLYGON((0 0,10 0,10 10,0 10,0 0))"))
        self.layer.dataProvider().addFeatures([feature])
        QgsProject.instance().addMapLayer(self.layer)
        self.fid = next(self.layer.getFeatures()).id()

    def _call(self, **kw):
        from cartogen_ai.core.agent.tools.vertex_edit_tool import edit_vertices
        return edit_vertices("sq", self.fid, **kw)

    def _geom(self):
        return self.layer.getFeature(self.fid).geometry()

    def test_the_first_call_is_only_a_preview(self):
        out = self._call(action="delete", index=2)
        self.assertEqual(out.get("status"), "PREVIEW_REQUIRED")
        self.assertAlmostEqual(self._geom().area(), 100.0)

    def test_delete_vertex_makes_a_triangle(self):
        out = self._call(action="delete", index=2, confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertEqual((out["vertices_before"], out["vertices_after"]), (5, 4))
        self.assertAlmostEqual(out["area_after"], 50.0)

    def test_add_vertex_keeps_the_shape(self):
        out = self._call(action="add", x=5.0, y=-1.0, confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["vertices_after"], 6)
        self.assertAlmostEqual(out["area_after"], 100.0)
        self.assertEqual(out["added_at"], [5.0, 0.0])

    def test_move_vertex_by_position(self):
        out = self._call(action="move", near_x=10.2, near_y=9.9, x=20.0, y=10.0, confirmed=True)
        self.assertTrue(out.get("success"), out)
        self.assertAlmostEqual(out["area_after"], 150.0)

    def test_a_vertex_that_does_not_exist_is_refused(self):
        self.assertIn("does not exist", self._call(action="delete", index=9, confirmed=True)["error"])

    def test_a_move_that_makes_the_polygon_self_crossing_is_refused_and_changes_nothing(self):
        out = self._call(action="move", index=2, x=0.0, y=-10.0, confirmed=True)
        self.assertIn("error", out)
        self.assertAlmostEqual(self._geom().area(), 100.0)

    def test_one_undo_restores_the_square_when_the_layer_is_in_edit_mode(self):
        self.layer.startEditing()                                  # the tool never takes over an edit session the user already has
        self._call(action="delete", index=2, confirmed=True)
        self.assertAlmostEqual(self._geom().area(), 50.0)
        self.layer.undoStack().undo()
        self.assertAlmostEqual(self._geom().area(), 100.0)
        self.assertTrue(self.layer.isEditable())

    def test_a_point_layer_is_refused(self):
        pts = QgsVectorLayer("Point?crs=EPSG:32636", "pts", "memory")
        QgsProject.instance().addMapLayer(pts)
        from cartogen_ai.core.agent.tools.vertex_edit_tool import edit_vertices
        self.assertIn("point layer", edit_vertices("pts", 1, "delete", index=0)["error"])


if __name__ == "__main__":
    unittest.main()
