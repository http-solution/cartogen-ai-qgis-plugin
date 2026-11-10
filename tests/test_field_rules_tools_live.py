"""PLAN-023 R10-1 on real QGIS layers: a virtual field's value equals its expression for each feature and nothing is written to the data; a not-null / unique / expression
constraint is read back and the existing features that break it are counted by QgsVectorLayerUtils; a default value fills a new feature; denied expression functions are refused;
a real column cannot be removed as a virtual field. Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestFieldRulesLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.layer = QgsVectorLayer("Point?crs=EPSG:32636&field=name:string&field=pop:integer&field=area:double", "pts", "memory")
        feats = []
        for i, (name, pop, area) in enumerate([("a", 100, 10.0), ("b", 50, 5.0), ("b", None, 2.0), ("d", -4, 1.0)]):
            f = QgsFeature(self.layer.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(i, 0)))
            f.setAttributes([name, pop, area])
            feats.append(f)
        self.layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(self.layer)

    def test_a_virtual_field_equals_its_expression_and_writes_nothing(self):
        from cartogen_ai.core.agent.tools.field_rules_tools import add_virtual_field, remove_virtual_field
        out = add_virtual_field("pts", "double_area", '"area" * 2', field_type="double")
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["value_on_first_feature"], 20.0)
        values = sorted(f["double_area"] for f in self.layer.getFeatures())
        self.assertEqual(values, [2.0, 4.0, 10.0, 20.0])
        self.assertEqual([f.name() for f in self.layer.dataProvider().fields()], ["name", "pop", "area"])          # the data source never got the column
        self.assertIn("already exists", add_virtual_field("pts", "double_area", "1")["error"])
        self.assertTrue(remove_virtual_field("pts", "double_area").get("success"))
        self.assertEqual(self.layer.fields().indexOf("double_area"), -1)
        self.assertIn("real column", remove_virtual_field("pts", "area")["error"])

    def test_a_bad_or_denied_expression_is_refused(self):
        from cartogen_ai.core.agent.tools.field_rules_tools import add_virtual_field
        self.assertIn("error", add_virtual_field("pts", "x", '"area" +'))
        self.assertIn("error", add_virtual_field("pts", "x", '"nope" * 2'))
        self.assertIn("error", add_virtual_field("pts", "x", "eval('1+1')"))
        self.assertEqual(self.layer.fields().indexOf("x"), -1)

    def test_not_null_and_unique_and_expression_constraints_are_read_back_and_counted(self):
        from cartogen_ai.core.agent.tools.field_rules_tools import set_field_constraint
        out = set_field_constraint("pts", "pop", not_null=True)
        self.assertTrue(out.get("success"), out)
        self.assertTrue(out["rules_now"]["not_null"])
        self.assertEqual(out["existing_features"]["violations"], 1)                # the feature with no pop
        out = set_field_constraint("pts", "name", unique=True)
        self.assertEqual(out["existing_features"]["violations"], 2)                # both features named b
        out = set_field_constraint("pts", "pop", expression='"pop" >= 0', description="no negatives")
        self.assertEqual(out["rules_now"]["description"], "no negatives")
        self.assertGreaterEqual(out["existing_features"]["violations"], 1)
        cleared = set_field_constraint("pts", "pop", not_null=False, expression="")
        self.assertFalse(cleared["rules_now"]["not_null"])
        self.assertEqual(cleared["rules_now"]["expression"], "")
        self.assertEqual(cleared["existing_features"]["violations"], 0)

    def test_a_request_that_sets_nothing_or_a_missing_field_is_refused(self):
        from cartogen_ai.core.agent.tools.field_rules_tools import set_field_constraint
        self.assertIn("Nothing to set", set_field_constraint("pts", "pop")["error"])
        self.assertIn("not found", set_field_constraint("pts", "zzz", not_null=True)["error"])

    def test_a_default_value_fills_a_new_feature_and_can_be_removed(self):
        from cartogen_ai.core.agent.tools.field_rules_tools import set_default_value
        out = set_default_value("pts", "pop", "42")
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["default_now"], "42")
        idx = self.layer.fields().indexOf("pop")
        from qgis.core import QgsVectorLayerUtils
        created = QgsVectorLayerUtils.createFeature(self.layer)
        self.assertEqual(created.attribute(idx), 42)
        self.assertEqual(self.layer.featureCount(), 4)                                # existing features untouched
        cleared = set_default_value("pts", "pop", "")
        self.assertEqual(cleared["default_now"], "")
        self.assertIn("error", set_default_value("pts", "pop", "eval('1')"))


if __name__ == "__main__":
    unittest.main()
