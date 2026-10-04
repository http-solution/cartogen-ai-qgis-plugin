# -*- coding: utf-8 -*-
"""H8 allocation envelope on a real layer. Written without a local QGIS: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsGraduatedSymbolRenderer, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


ROWS = [("A", 0.2, 1000), ("B", 0.4, 1000), ("C", 0.8, 1000), ("D", None, 500), ("E", 0.6, None)]


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestAllocationEnvelope(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=need:double&field=pop:double", "districts", "memory")
        feats = []
        for i, (name, need, pop) in enumerate(ROWS):
            f = QgsFeature(layer.fields())
            x = 44.0 + i * 0.1
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 15, {x + 0.09} 15, {x + 0.09} 15.09, {x} 15.09, {x} 15))"))
            f.setAttributes([name, need, pop])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        self.layer = layer

    def _run(self, **kw):
        from cartogen_ai.core.agent.tools.allocation_tools import calculate_allocation_envelope
        return calculate_allocation_envelope("districts", kw.pop("budget", 1200), "need", unit_name_field="name", **kw)

    def test_split_is_proportional_and_incomplete_areas_are_listed_not_imputed(self):
        res = self._run(population_field="pop")
        self.assertTrue(res.get("success"), res)
        amounts = {r["unit"]: r["amount"] for r in res["results"]}
        self.assertEqual({e["unit"] for e in res["excluded_units"]}, {"D", "E"}, res)
        self.assertAlmostEqual(amounts["A"], 1200 * 0.2 / 1.4, places=3)
        self.assertAlmostEqual(amounts["C"], 1200 * 0.8 / 1.4, places=3)
        self.assertAlmostEqual(res["allocated"], 1200.0, places=3)
        self.assertIn("advisory", res)

    def test_ceiling_and_unallocated_are_reported(self):
        # four areas have a need value; at 20% of 1,200 each they can absorb only 960, so 240 stays unallocated
        res = self._run(max_share_per_unit=0.2)
        self.assertTrue(res.get("success"), res)
        self.assertTrue(all(r["amount"] <= 240.0 + 1e-6 for r in res["results"]))
        self.assertAlmostEqual(res["unallocated"], 240.0, places=3)
        self.assertEqual(res["areas_at_ceiling"], 4)

    def test_writing_the_field_needs_confirmation_then_writes_and_styles_nothing_by_itself(self):
        preview = self._run(output_field="alloc")
        self.assertEqual(preview.get("status"), "PREVIEW_REQUIRED")
        self.assertLess(self.layer.fields().indexOf("alloc"), 0)
        res = self._run(output_field="alloc", confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertGreaterEqual(self.layer.fields().indexOf("alloc"), 0)
        self.assertEqual(res["map_look"]["args"]["look"], "allocation")
        by_name = {f["name"]: f["alloc"] for f in self.layer.getFeatures()}
        self.assertEqual(by_name["D"], 0.0)                       # excluded areas get nothing
        self.assertAlmostEqual(sum(by_name.values()), 1200.0, places=3)
        self.assertNotIsInstance(self.layer.renderer(), QgsGraduatedSymbolRenderer)   # the look is applied only on request

    def test_the_allocation_look_draws_the_field(self):
        self._run(output_field="alloc", confirmed=True)
        from cartogen_ai.core.agent.tools.humanitarian_look_tools import apply_humanitarian_look
        res = apply_humanitarian_look("districts", "allocation", "alloc")
        self.assertTrue(res.get("success"), res)
        self.assertIsInstance(self.layer.renderer(), QgsGraduatedSymbolRenderer)

    def test_bad_inputs_are_errors_that_change_nothing(self):
        self.assertIn("error", self._run(budget=0))
        self.assertIn("error", self._run(need_exponent=0))
        self.assertIn("error", self._run(min_amount_per_unit=10000))
        self.assertLess(self.layer.fields().indexOf("alloc"), 0)


if __name__ == "__main__":
    unittest.main()
