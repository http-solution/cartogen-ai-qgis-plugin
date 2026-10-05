# -*- coding: utf-8 -*-
"""JIAF 2 stage 3 on a real QGIS layer: writing the preliminary figures after confirmation. Written without a local QGIS: CI's first run is its first execution."""
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
    ["#adm2 +code", "#adm2 +name", "#inneed", "#severity", "#inneed +wsh", "#severity +wsh", "#inneed +shl", "#severity +shl",
     "#inneed +hea", "#severity +hea", "#inneed +nut", "#severity +nut"],
    ["YE1101", "A", 300, 3, 100, 3, 300, 3, 200, 3, 50, 3],
    ["YE1102", "B", 120, 2, 120, 2, 90, 2, 10, 1, 0, 1],
    ["YE1109", "C", 5, 1, 5, 1, 1, 1, 1, 1, 1, 1],
]


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestJiafEngineLive(unittest.TestCase):
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
        from cartogen_ai.core.agent.tools.jiaf_engine import compute_jiaf_preliminary
        return compute_jiaf_preliminary(self.path, sectors_in_scope=["nutrition", "health", "shelter", "wash"], layer_name="districts", layer_key_field="pcode", **kw)

    def test_report_only_leaves_the_layer_alone(self):
        out = self._call()
        self.assertTrue(out["success"], out)
        self.assertEqual(out["join"]["matched"], 2)
        self.assertEqual(self.layer.fields().indexOf("jf_pre_pin"), -1)

    def test_writing_needs_confirmation_then_writes_the_preliminary_figures(self):
        first = self._call(write_fields=True)
        self.assertEqual(first.get("status"), "PREVIEW_REQUIRED", first)
        self.assertEqual(self.layer.fields().indexOf("jf_pre_pin"), -1)
        out = self._call(write_fields=True, confirmed=True)
        self.assertNotIn("write_warning", out, out)
        by = {str(f["pcode"]).upper(): f for f in self.layer.getFeatures()}
        self.assertEqual(by["YE1101"]["jf_pre_pin"], 300)
        self.assertEqual(by["YE1101"]["jf_pre_sev"], 3)
        self.assertEqual(by["YE1102"]["jf_pre_pin"], 120)
        self.assertEqual(by["YE1102"]["jf_pre_sev"], 1)
        self.assertIsNone(by["YE1103"]["jf_pre_pin"])  # not in the file
        self.assertGreaterEqual(by["YE1101"]["jf_npinfl"], 1)  # flag 2 fires: 300 vs 200 is +50%, above the 30% default


if __name__ == "__main__":
    unittest.main()
