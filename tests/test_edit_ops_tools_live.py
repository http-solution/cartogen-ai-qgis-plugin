"""Live-QGIS tests for the M3 editing operations (edit_ops_tools.py). Written without a QGIS install: CI's first run is their first execution.
Everything is read back from real layers."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _add(layer, wkt, attrs):
    f = QgsFeature(layer.fields())
    f.setGeometry(QgsGeometry.fromWkt(wkt))
    f.setAttributes(attrs)
    layer.dataProvider().addFeatures([f])


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestEditOpsToolsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.polys = QgsVectorLayer("Polygon?crs=EPSG:3857&field=name:string&field=pop:string", "plots", "memory")
        _add(self.polys, "POLYGON((0 0,10 0,10 10,0 10,0 0))", ["a", "12"])
        _add(self.polys, "POLYGON((10 0,20 0,20 10,10 10,10 0))", ["b", "7.5"])
        _add(self.polys, "POLYGON((30 0,40 0,40 10,30 10,30 0))", ["c", "abc"])
        QgsProject.instance().addMapLayer(self.polys)

    def _geoms(self):
        return {f["name"]: f.geometry() for f in self.polys.getFeatures()}

    def test_transform_previews_then_moves_scales_rotates(self):
        from cartogen_ai.core.agent.tools.edit_ops_tools import transform_features
        args = {"layer_name": "plots", "expression": "\"name\" = 'a'"}
        self.assertEqual(transform_features(**args, move_x=5)["status"], "PREVIEW_REQUIRED")
        self.assertEqual(self._geoms()["a"].boundingBox().xMinimum(), 0)
        res = transform_features(**args, move_x=5, move_y=2, confirmed=True)
        self.assertTrue(res.get("success"), res)
        box = self._geoms()["a"].boundingBox()
        self.assertEqual((box.xMinimum(), box.yMinimum()), (5, 2))
        res = transform_features(**args, scale_factor=2, confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertAlmostEqual(self._geoms()["a"].area(), 400.0, places=3)
        res = transform_features(**args, rotate_degrees=90, confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertAlmostEqual(self._geoms()["a"].area(), 400.0, places=3)
        self.assertAlmostEqual(self._geoms()["b"].area(), 100.0, places=3)   # the other features were not touched

    def test_transform_refuses_bad_input(self):
        from cartogen_ai.core.agent.tools.edit_ops_tools import transform_features
        self.assertIn("error", transform_features("plots", expression="1=1"))
        self.assertIn("error", transform_features("plots", move_x=1))
        self.assertIn("error", transform_features("plots", expression="1=1", scale_factor=0))

    def test_merge_features(self):
        from cartogen_ai.core.agent.tools.edit_ops_tools import merge_features
        self.assertIn("at least two", merge_features("plots", expression="\"name\" = 'a'")["error"])
        self.assertEqual(merge_features("plots", expression="\"name\" IN ('a','b')")["status"], "PREVIEW_REQUIRED")
        res = merge_features("plots", expression="\"name\" IN ('a','b')", confirmed=True)
        self.assertTrue(res.get("success"), res)
        geoms = self._geoms()
        self.assertEqual(sorted(geoms), ["a", "c"])
        self.assertAlmostEqual(geoms["a"].area(), 200.0, places=3)
        self.assertEqual(self.polys.featureCount(), 2)

    def test_split_features_by_line(self):
        from cartogen_ai.core.agent.tools.edit_ops_tools import split_features_by_line
        args = {"layer_name": "plots", "line_wkt": "LINESTRING(5 -5, 5 15)", "expression": "\"name\" = 'a'"}
        self.assertEqual(split_features_by_line(**args)["status"], "PREVIEW_REQUIRED")
        self.assertEqual(self.polys.featureCount(), 3)
        res = split_features_by_line(**args, confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertEqual((res["features_before"], res["features_after"]), (3, 4))
        self.assertAlmostEqual(sum(f.geometry().area() for f in self.polys.getFeatures() if f["name"] == "a"), 100.0, places=3)

    def test_split_reports_a_line_that_misses(self):
        from cartogen_ai.core.agent.tools.edit_ops_tools import split_features_by_line
        res = split_features_by_line("plots", "LINESTRING(100 -5, 100 15)", expression="\"name\" = 'a'", confirmed=True)
        self.assertIn("error", res)
        self.assertEqual(self.polys.featureCount(), 3)
        self.assertIn("error", split_features_by_line("plots", "POINT(1 1)", expression="1=1"))

    def test_change_field_type(self):
        from cartogen_ai.core.agent.tools.edit_ops_tools import change_field_type
        pre = change_field_type("plots", "pop", "double")
        self.assertEqual(pre["status"], "PREVIEW_REQUIRED")
        self.assertIn("1 value", pre["rationale"])
        res = change_field_type("plots", "pop", "double", confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(self.polys.fields().field("pop").typeName().lower() in ("double", "real"), True)
        values = {f["name"]: f["pop"] for f in self.polys.getFeatures()}
        self.assertEqual(values["a"], 12.0)
        self.assertEqual(values["b"], 7.5)
        self.assertFalse(values["c"])   # 'abc' became NULL
        self.assertFalse(self.polys.isEditable())

    def test_change_field_type_refuses_unknown(self):
        from cartogen_ai.core.agent.tools.edit_ops_tools import change_field_type
        self.assertIn("error", change_field_type("plots", "nope", "double"))
        self.assertIn("error", change_field_type("plots", "pop", "geometry"))

    def test_editing_undo_redo_and_save_discard(self):
        from cartogen_ai.core.agent.tools.edit_ops_tools import redo_manual_edit, set_layer_editing, transform_features, undo_manual_edit
        self.assertIn("error", undo_manual_edit("plots"))   # not in edit mode
        self.assertTrue(set_layer_editing("plots", "start")["success"])
        res = transform_features("plots", expression="\"name\" = 'a'", move_x=3, confirmed=True)
        self.assertIn("NOT saved", res.get("note", ""))
        self.assertEqual(self._geoms()["a"].boundingBox().xMinimum(), 3)
        self.assertTrue(undo_manual_edit("plots")["success"])
        self.assertEqual(self._geoms()["a"].boundingBox().xMinimum(), 0)
        self.assertTrue(redo_manual_edit("plots")["success"])
        self.assertEqual(self._geoms()["a"].boundingBox().xMinimum(), 3)
        self.assertEqual(set_layer_editing("plots", "discard")["status"], "PREVIEW_REQUIRED")
        self.assertTrue(set_layer_editing("plots", "discard", confirmed=True)["success"])
        self.assertEqual(self._geoms()["a"].boundingBox().xMinimum(), 0)
        self.assertFalse(self.polys.isEditable())
        self.assertIn("error", set_layer_editing("plots", "save"))
        self.assertIn("error", set_layer_editing("plots", "explode"))

    def test_set_layer_filter(self):
        from cartogen_ai.core.agent.tools.edit_ops_tools import set_layer_filter
        res = set_layer_filter("plots", "\"name\" <> 'c'")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["feature_count"], 2)
        self.assertIn("error", set_layer_filter("plots", "1=1; DROP TABLE plots"))
        self.assertEqual(self.polys.featureCount(), 2)
        res = set_layer_filter("plots", clear=True)
        self.assertEqual((res["feature_count"], res["previous_filter"]), (3, "\"name\" <> 'c'"))


if __name__ == "__main__":
    unittest.main()
