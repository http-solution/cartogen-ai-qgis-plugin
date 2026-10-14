"""Live-QGIS tests for the M3 selection and editing tools. Written without a QGIS install: CI's first run is their first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestAttributeEditToolsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:integer&field=area:double", "towns", "memory")
        for i, (name, pop) in enumerate((("a", 5), ("b", 50), ("c", 500))):
            f = QgsFeature(self.layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({i} 1)"))
            f.setAttributes([name, pop, 1.5])
            self.layer.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(self.layer)

    def _names(self):
        return sorted(f["name"] for f in self.layer.getFeatures())

    def test_selection_tools(self):
        from cartogen_ai.core.agent.tools.attribute_edit_tools import clear_selection, select_all_features, select_by_expression
        self.assertEqual(select_by_expression("towns", '"pop" > 10')["selected_count"], 2)
        self.assertEqual(select_by_expression("towns", '"pop" > 100', mode="intersect")["selected_count"], 1)
        self.assertEqual(select_by_expression("towns", '"name" = \'a\'', mode="add")["selected_count"], 2)
        self.assertEqual(select_all_features("towns")["selected_count"], 3)
        self.assertEqual(clear_selection("towns")["cleared_layers"], ["towns"])
        self.assertEqual(self.layer.selectedFeatureCount(), 0)

    def test_a_denied_or_broken_expression_is_refused(self):
        from cartogen_ai.core.agent.tools.attribute_edit_tools import select_by_expression
        self.assertIn("env()", select_by_expression("towns", "env('HOME') = 'x'")["error"])
        self.assertIn("Invalid expression", select_by_expression("towns", '"pop" >>> 1')["error"])

    def test_delete_features_previews_then_deletes_exactly_the_match(self):
        from cartogen_ai.core.agent.tools.attribute_edit_tools import delete_features
        preview = delete_features("towns", expression='"pop" < 100')
        self.assertEqual(preview["status"], "PREVIEW_REQUIRED")
        self.assertIn("2 of 3", preview["rationale"])
        self.assertEqual(self._names(), ["a", "b", "c"])   # the preview changed nothing
        res = delete_features("towns", expression='"pop" < 100', confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertEqual((res["deleted"], self._names()), (2, ["c"]))

    def test_delete_needs_exactly_one_selector_and_something_to_delete(self):
        from cartogen_ai.core.agent.tools.attribute_edit_tools import delete_features
        self.assertIn("error", delete_features("towns"))
        self.assertIn("error", delete_features("towns", expression='"pop" > 0', only_selected=True))
        self.assertIn("nothing", delete_features("towns", expression='"pop" > 9999').get("error", ""))
        self.assertIn("Nothing is selected", delete_features("towns", only_selected=True)["error"])

    def test_set_attribute_value(self):
        from cartogen_ai.core.agent.tools.attribute_edit_tools import set_attribute_value
        self.assertEqual(set_attribute_value("towns", "pop", "7", expression='"name" = \'a\'')["status"], "PREVIEW_REQUIRED")
        res = set_attribute_value("towns", "pop", "7", expression='"name" = \'a\'', confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertEqual({f["name"]: f["pop"] for f in self.layer.getFeatures()}["a"], 7)
        self.assertIn("not a number", set_attribute_value("towns", "pop", "lots", feature_id=1)["error"])
        self.assertIn("not found", set_attribute_value("towns", "nope", "1", feature_id=1)["error"])

    def test_field_add_rename_delete(self):
        from cartogen_ai.core.agent.tools.attribute_edit_tools import add_field, delete_field, rename_field
        self.assertTrue(add_field("towns", "notes", "text").get("success"))
        self.assertIn("already exists", add_field("towns", "notes")["error"])
        self.assertTrue(rename_field("towns", "notes", "remarks").get("success"))
        self.assertIn("remarks", self.layer.fields().names())
        self.assertEqual(delete_field("towns", "remarks")["status"], "PREVIEW_REQUIRED")
        self.assertIn("remarks", self.layer.fields().names())
        self.assertTrue(delete_field("towns", "remarks", confirmed=True).get("success"))
        self.assertNotIn("remarks", self.layer.fields().names())

    def test_add_feature_from_wkt(self):
        from cartogen_ai.core.agent.tools.attribute_edit_tools import add_feature_from_wkt
        res = add_feature_from_wkt("towns", "POINT(4000000 3700000)", {"name": "d", "pop": "9"}, crs="EPSG:3857")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["feature_count"], 4)
        new = next(f for f in self.layer.getFeatures() if f["name"] == "d")
        self.assertLess(abs(new.geometry().asPoint().x()), 180)   # transformed to degrees in code
        self.assertIn("geometry type", add_feature_from_wkt("towns", "POLYGON((0 0,1 0,1 1,0 0))")["error"])
        self.assertIn("could not be read", add_feature_from_wkt("towns", "POINT(")["error"])


if __name__ == "__main__":
    unittest.main()
