# -*- coding: utf-8 -*-
"""Live-QGIS tests for H5 calculate_mcda_ranking. Written without a QGIS install: CI's first run is their first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _districts():
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=need:double&field=access:double", "districts", "memory")
    rows = [("A", 90.0, 10.0), ("B", 50.0, 50.0), ("C", 10.0, 90.0), ("D", None, 20.0)]
    feats = []
    for i, (name, need, access) in enumerate(rows):
        f = QgsFeature(layer.fields())
        x = 44.0 + i * 0.1
        f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 15, {x + 0.05} 15, {x + 0.05} 15.05, {x} 15.05, {x} 15))"))
        f.setAttributes([name, need, access])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


CRITERIA = [{"field": "need", "weight": 1, "direction": "higher"}, {"field": "access", "weight": 1, "direction": "lower"}]


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestCalculateMcdaRanking(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        QgsProject.instance().addMapLayer(_districts())

    def test_ranks_and_excludes_the_incomplete_unit(self):
        from cartogen_ai.core.agent.tools.mcda_tools import calculate_mcda_ranking
        res = calculate_mcda_ranking("districts", CRITERIA, unit_name_field="name", top_k=1, seed=4)
        self.assertTrue(res.get("success"), res)
        self.assertEqual([r["unit"] for r in res["results"]], ["A", "B", "C"])
        self.assertEqual(res["excluded_units_missing_data"], ["D"])
        self.assertEqual(res["sensitivity"]["seed"], 4)

    def test_writing_fields_needs_confirmation_then_writes_and_saves(self):
        from cartogen_ai.core.agent.tools.mcda_tools import calculate_mcda_ranking
        layer = QgsProject.instance().mapLayersByName("districts")[0]
        preview = calculate_mcda_ranking("districts", CRITERIA, unit_name_field="name", output_prefix="mc", seed=1)
        self.assertEqual(preview.get("status"), "PREVIEW_REQUIRED")
        self.assertLess(layer.fields().indexOf("mc_rank"), 0)
        res = calculate_mcda_ranking("districts", CRITERIA, unit_name_field="name", output_prefix="mc", seed=1, confirmed=True)
        self.assertTrue(res.get("success"), res)
        self.assertNotIn("output_field_warning", res)
        ranks = {f["name"]: f["mc_rank"] for f in layer.getFeatures()}
        self.assertEqual((ranks["A"], ranks["B"], ranks["C"]), (1, 2, 3))

    def test_unknown_layer_and_field(self):
        from cartogen_ai.core.agent.tools.mcda_tools import calculate_mcda_ranking
        self.assertIn("error", calculate_mcda_ranking("ghost", CRITERIA))
        self.assertIn("error", calculate_mcda_ranking("districts", [{"field": "need"}, {"field": "nope"}]))


if __name__ == "__main__":
    unittest.main()
