# -*- coding: utf-8 -*-
"""H7 importer join on a real layer. Written without a local QGIS: CI's first run is its first execution."""
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


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestImporterJoin(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=pcode:string", "admin", "memory")
        feats = []
        for i, code in enumerate(["YE01", "YE02", "YE03"]):
            f = QgsFeature(layer.fields())
            x = 44.0 + i * 0.1
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 15, {x + 0.09} 15, {x + 0.09} 15.09, {x} 15.09, {x} 15))"))
            f.setAttributes([code.lower() if i == 0 else code])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        self.layer = layer
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("admin_pcode,phase,population\nYE01,3,1000\nYE02,,500\nYE09,4,10\n")
        self.addCleanup(os.remove, self.path)

    def _call(self, **kw):
        from cartogen_ai.core.agent.tools.table_importers import import_humanitarian_table
        return import_humanitarian_table(self.path, "ipc", layer_name="admin", layer_key_field="pcode", **kw)

    def test_report_only_does_not_touch_the_layer(self):
        out = self._call()
        self.assertTrue(out["success"], out)
        self.assertEqual(out["join"]["matched"], 2)
        self.assertEqual(out["join"]["layer_features_unmatched"], 1)
        self.assertEqual(out["join"]["table_rows_unmatched"], 1)
        self.assertEqual(self.layer.fields().indexOf("ipc_phase"), -1)

    def test_writing_needs_confirmation_then_writes_and_leaves_unknowns_null(self):
        first = self._call(write_fields=True)
        self.assertEqual(first.get("status"), "PREVIEW_REQUIRED", first)
        self.assertEqual(self.layer.fields().indexOf("ipc_phase"), -1)
        out = self._call(write_fields=True, confirmed=True)
        self.assertNotIn("write_warning", out, out)
        by_code = {str(f["pcode"]).upper(): f for f in self.layer.getFeatures()}
        self.assertEqual(by_code["YE01"]["ipc_phase"], 3)
        self.assertEqual(by_code["YE01"]["ipc_pop"], 1000)
        self.assertIsNone(by_code["YE02"]["ipc_phase"])  # blank phase is not phase 1
        self.assertEqual(by_code["YE02"]["ipc_pop"], 500)
        self.assertIsNone(by_code["YE03"]["ipc_phase"])  # not in the file


if __name__ == "__main__":
    unittest.main()
