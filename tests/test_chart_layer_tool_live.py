"""Live QGIS test of chart_field_by_category (LR-24). Written without a QGIS install: CI's first run is its first execution."""
import os
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestChartFieldByCategory(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=zone_type:string&field=pop:integer", "zones", "memory")
        feats = []
        for zone, pop in (("urban", 10), ("urban", 30), ("open", 5), ("mixed", 7), ("open", None), (None, 1)):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt("POINT(1 1)"))
            f.setAttributes([zone, pop])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        self.before = set(QgsProject.instance().mapLayers())

    def _run(self, **kw):
        from cartogen_ai.core.agent.tools.chart_layer_tool import chart_field_by_category
        return chart_field_by_category("zones", "zone_type", **kw)

    def test_a_count_chart_in_one_call_with_the_figures_and_no_new_layer(self):
        res = self._run()
        self.assertTrue(res.get("success"), res)
        self.addCleanup(lambda: os.path.exists(res["output_path"]) and os.remove(res["output_path"]))
        self.assertTrue(os.path.isfile(res["output_path"]))
        self.assertEqual({p["label"]: p["value"] for p in res["plotted"]}, {"urban": 2, "open": 2, "mixed": 1, "(no value)": 1})
        self.assertEqual(res["aggregate"], "count")
        self.assertEqual(set(QgsProject.instance().mapLayers()), self.before)          # the row C16 run left four tables behind

    def test_a_sum_chart_skips_a_missing_number_and_says_so(self):
        res = self._run(value_field="pop", chart_type="pie")
        self.assertTrue(res.get("success"), res)
        self.addCleanup(lambda: os.path.exists(res["output_path"]) and os.remove(res["output_path"]))
        self.assertEqual({p["label"]: p["value"] for p in res["plotted"]}, {"urban": 40.0, "mixed": 7.0, "open": 5.0, "(no value)": 1.0})
        self.assertEqual(res["aggregate"], "sum")

    def test_refusals_name_the_cause(self):
        from cartogen_ai.core.agent.tools.chart_layer_tool import chart_field_by_category as chart
        self.assertIn("not found", chart("nope", "zone_type")["error"])
        self.assertIn("Fields:", chart("zones", "nope")["error"])
        self.assertIn("needs value_field", chart("zones", "zone_type", aggregate="mean")["error"])
        self.assertIn("not a numeric field", chart("zones", "zone_type", value_field="zone_type", aggregate="sum")["error"])
        self.assertIn("aggregate must be one of", chart("zones", "zone_type", aggregate="median")["error"])
