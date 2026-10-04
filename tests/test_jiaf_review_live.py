# -*- coding: utf-8 -*-
"""JIAF 2 stage 4 on a real QGIS project: the decision store, the final figures on a layer and the pattern counts. Written without a local QGIS: CI's first
run is its first execution."""
import csv
import os
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


SCOPE = ["nutrition", "health", "shelter", "wash"]  # the toy file has four sectors; the default scope is all eight
GRID = [
    ["#adm2 +code", "#adm2 +name", "#inneed", "#severity", "#inneed +wsh", "#severity +wsh", "#inneed +shl", "#severity +shl",
     "#inneed +hea", "#severity +hea", "#inneed +nut", "#severity +nut"],
    ["YE1101", "A", 300, 3, 100, 3, 300, 3, 200, 3, 50, 3],
    ["YE1102", "B", 120, 2, 120, 2, 90, 2, 110, 2, 80, 2],
]


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestJiafReviewLive(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=pcode:string", "districts", "memory")
        feats = []
        for i, code in enumerate(["YE1101", "ye1102", "YE1103"]):
            f = QgsFeature(layer.fields())
            x = 44.0 + i * 0.1
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 15, {x + 0.09} 15, {x + 0.09} 15.09, {x} 15.09, {x} 15))"))
            f.setAttributes([code])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        self.layer = layer
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(self.path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(GRID)
        self.addCleanup(os.remove, self.path)

    def test_decisions_round_trip_merge_and_replace(self):
        from cartogen_ai.core.agent.tools.jiaf_review import get_jiaf_decisions, record_jiaf_decisions
        out = record_jiaf_decisions([{"unit": "YE1101", "sector": "health", "rationale": "shelter counts all affected"}])
        self.assertTrue(out["success"], out)
        record_jiaf_decisions(severity_decisions=[{"unit": "YE1101", "phase": 5, "evidence_basis": "outcome_indicators", "evidence": "CDR 2.1"}])
        got = get_jiaf_decisions()
        self.assertEqual(got["counts"], {"pin": 1, "severity": 1})
        self.assertEqual(got["decisions"]["pin"]["YE1101"]["sector"], "health")
        out = record_jiaf_decisions([{"unit": "YE1102", "sector": "wash", "rationale": "r"}], replace=True)
        self.assertEqual(get_jiaf_decisions()["counts"], {"pin": 1, "severity": 0})
        self.assertIn("error", record_jiaf_decisions([{"unit": "YE1102", "sector": "wash"}]))

    def test_finalize_applies_the_stored_decision_and_writes_fields_after_confirmation(self):
        from cartogen_ai.core.agent.tools.jiaf_review import finalize_jiaf_results, record_jiaf_decisions
        record_jiaf_decisions([{"unit": "YE1101", "sector": "health", "rationale": "shelter counts all affected"}],
                              [{"unit": "YE1101", "phase": 4, "evidence_basis": "expert_judgement", "evidence": "partner reports"}])
        report = finalize_jiaf_results(self.path, sectors_in_scope=SCOPE, bulk_accepted_flags=[1, 2, 3, 4, 5, 6], layer_name="districts", layer_key_field="pcode")
        self.assertTrue(report["success"], report)
        self.assertEqual(report["chosen_sector_rank_counts"], {"2": 1})
        self.assertEqual(report["final_pin_total"], 200 + 120)
        self.assertEqual(self.layer.fields().indexOf("jf_fin_pin"), -1)
        first = finalize_jiaf_results(self.path, sectors_in_scope=SCOPE, bulk_accepted_flags=[1, 2, 3, 4, 5, 6], layer_name="districts", layer_key_field="pcode", write_fields=True)
        self.assertEqual(first.get("status"), "PREVIEW_REQUIRED", first)
        out = finalize_jiaf_results(self.path, sectors_in_scope=SCOPE, bulk_accepted_flags=[1, 2, 3, 4, 5, 6], layer_name="districts", layer_key_field="pcode",
                                    write_fields=True, confirmed=True)
        self.assertNotIn("write_warning", out, out)
        by = {str(f["pcode"]).upper(): f for f in self.layer.getFeatures()}
        self.assertEqual(by["YE1101"]["jf_fin_pin"], 200)
        self.assertEqual(by["YE1101"]["jf_fin_sev"], 4)
        self.assertEqual(by["YE1101"]["jf_pin_rk"], 2)
        self.assertEqual(by["YE1102"]["jf_fin_pin"], 120)
        self.assertIsNone(by["YE1103"]["jf_fin_pin"])

    def test_patterns_write_the_two_count_fields(self):
        from cartogen_ai.core.agent.tools.jiaf_patterns import compute_jiaf_patterns
        out = compute_jiaf_patterns(self.path, sectors_in_scope=SCOPE, layer_name="districts", layer_key_field="pcode", write_fields=True, confirmed=True)
        self.assertTrue(out["success"], out)
        self.assertNotIn("write_warning", out, out)
        self.assertGreaterEqual(self.layer.fields().indexOf("jf_nsev45"), 0)
        by = {str(f["pcode"]).upper(): f for f in self.layer.getFeatures()}
        self.assertEqual(by["YE1101"]["jf_nsev45"], 0)  # no sector is in phase 4 or 5
        self.assertIsNone(by["YE1103"]["jf_nsev45"])


if __name__ == "__main__":
    unittest.main()
