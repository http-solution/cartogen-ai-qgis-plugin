# -*- coding: utf-8 -*-
"""JIAF 2 stage 2 on a real QGIS project: the set-up record and the P-code join. Written without a local QGIS: CI's first run is its first execution."""
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


GRID = [
    ["#adm1 +code", "#adm2 +code", "#adm2 +name", "#inneed +wsh", "#severity +wsh", "#inneed +shl", "#severity +shl"],
    ["YE11", "YE1101", "Al Qafr", 67717, 3, 22946, 0],
    ["YE11", "YE1102", "Yarim", 109918, 4, 271762, 4],
    ["YE11", "YE1109", "Elsewhere", 5, 2, 6, 2],
]


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestJiafInputsLive(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=pcode:string", "districts", "memory")
        feats = []
        for i, code in enumerate(["ye1101", "YE1102", "YE1103"]):
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

    def _call(self, **kw):
        from cartogen_ai.core.agent.tools.jiaf_inputs import import_jiaf_inputs
        return import_jiaf_inputs(self.path, layer_name="districts", layer_key_field="pcode", **kw)

    def test_report_only_does_not_touch_the_layer(self):
        out = self._call()
        self.assertTrue(out["success"], out)
        self.assertEqual(out["join"]["matched"], 2)
        self.assertEqual(out["join"]["layer_features_unmatched"], 1)
        self.assertEqual(out["join"]["table_rows_unmatched"], 1)
        self.assertEqual(self.layer.fields().indexOf("jp_wsh"), -1)

    def test_writing_needs_confirmation_then_writes_pin_and_severity_and_skips_zero_severity(self):
        first = self._call(write_fields=True)
        self.assertEqual(first.get("status"), "PREVIEW_REQUIRED", first)
        self.assertEqual(self.layer.fields().indexOf("jp_wsh"), -1)
        out = self._call(write_fields=True, confirmed=True)
        self.assertNotIn("write_warning", out, out)
        by = {str(f["pcode"]).upper(): f for f in self.layer.getFeatures()}
        self.assertEqual(by["YE1101"]["jp_wsh"], 67717)
        self.assertEqual(by["YE1101"]["js_wsh"], 3)
        self.assertEqual(by["YE1102"]["js_shl"], 4)
        self.assertIsNone(by["YE1101"]["js_shl"])  # severity 0 is not a phase
        self.assertIsNone(by["YE1103"]["jp_wsh"])  # not in the file

    def test_setup_record_round_trip_and_replacement(self):
        from cartogen_ai.core.agent.tools.jiaf_inputs import get_jiaf_setup, record_jiaf_setup
        self.assertIsNone(get_jiaf_setup()["recorded"])
        out = record_jiaf_setup("Yemen", "HPC 2026", "admin 2", "July 2024", hct_endorsed_scope=True,
                                sector_alignment=[{"sector": "health", "pin_aligned": False, "pin_explanation": "counts all affected"}])
        self.assertTrue(out["success"], out)
        rec = get_jiaf_setup()["recorded"]
        self.assertEqual(rec["setup"]["manual_edition"], "July 2024")
        self.assertEqual(rec["sector_alignment"][0]["sector"], "health")
        self.assertIn("not endorsed", rec["statement"])
        record_jiaf_setup("Yemen", "HPC 2027", "admin 2", "July 2024")
        self.assertEqual(get_jiaf_setup()["recorded"]["setup"]["planning_cycle"], "HPC 2027")

    def test_invalid_setup_is_not_saved(self):
        from cartogen_ai.core.agent.tools.jiaf_inputs import get_jiaf_setup, record_jiaf_setup
        out = record_jiaf_setup("Yemen", "HPC 2026", "admin 2", "July 2024", sector_alignment=[{"sector": "health", "pin_aligned": False}])
        self.assertIn("error", out)
        self.assertIsNone(get_jiaf_setup()["recorded"])


if __name__ == "__main__":
    unittest.main()
