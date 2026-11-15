"""Live check that the tools refuse a denied expression and still run an ordinary one. Written without a QGIS install."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestExpressionScreenLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:integer", "towns", "memory")
        for name, pop, x in (("a", 5, 1), ("b", 50, 2)):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({x} 1)"))
            f.setAttributes([name, pop])
            layer.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(layer)

    def test_denied_expressions_are_refused_by_every_entry_point(self):
        from cartogen_ai.core.agent.tools.vector_tools import highlight_features, run_query, zoom_to_feature
        bad = "env('HOME') = 'x'"
        for res in (run_query("towns", bad), highlight_features("towns", bad), zoom_to_feature("towns", expression=bad)):
            self.assertIn("env()", res.get("error", ""), res)

    def test_an_ordinary_expression_still_selects(self):
        from cartogen_ai.core.agent.tools.vector_tools import highlight_features
        res = highlight_features("towns", '"pop" > 10')
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["count"], 1)


if __name__ == "__main__":
    unittest.main()
