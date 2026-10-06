# -*- coding: utf-8 -*-
"""IPC / INFORM / damage / measure looks, the classified-raster palette and the obfuscated-point style, in real QGIS.
Written without a local QGIS: CI's first run is its first execution."""
import os
import unittest

try:
    from qgis.core import (QgsFeature, QgsGeometry, QgsGraduatedSymbolRenderer, QgsPalettedRasterRenderer,
                           QgsProject, QgsRasterLayer, QgsRuleBasedRenderer, QgsSingleSymbolRenderer, QgsVectorLayer)
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestTableLooksLive(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=ipc:double&field=risk:double&field=dmg:string&field=m:double",
                               "areas", "memory")
        rows = [("A", 1.0, 1.5, "No Visible Damage", 10.0), ("B", 3.0, 4.0, "Severe Damage", 20.0), ("C", 5.0, 8.0, "Destroyed", 40.0), ("D", None, None, None, None)]
        feats = []
        for i, r in enumerate(rows):
            f = QgsFeature(layer.fields())
            x = 44.0 + i * 0.1
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 15, {x + 0.09} 15, {x + 0.09} 15.09, {x} 15.09, {x} 15))"))
            f.setAttributes(list(r))
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        self.layer = layer

    def _look(self, look, field):
        from cartogen_ai.core.agent.tools.humanitarian_look_tools import apply_humanitarian_look
        return apply_humanitarian_look("areas", look, field)

    def test_ipc_phase_is_rule_based_with_a_grey_not_analysed_class(self):
        res = self._look("ipc_phase", "ipc")
        self.assertTrue(res.get("success"), res)
        self.assertIsInstance(self.layer.renderer(), QgsRuleBasedRenderer)
        self.assertEqual(res["classes"][0], "1 Minimal")
        self.assertEqual(res["classes"][-1], "Not analysed")

    def test_inform_risk_is_five_graduated_classes(self):
        res = self._look("inform_risk", "risk")
        self.assertTrue(res.get("success"), res)
        self.assertIsInstance(self.layer.renderer(), QgsGraduatedSymbolRenderer)
        self.assertEqual(len(self.layer.renderer().ranges()), 5)

    def test_damage_class_matches_the_files_own_wording(self):
        res = self._look("damage_class", "dmg")
        self.assertTrue(res.get("success"), res)
        self.assertIsInstance(self.layer.renderer(), QgsRuleBasedRenderer)
        self.assertEqual(res["classes"], ["Destroyed", "Severe damage", "No visible damage", "Other / not classified"])
        self.assertIn("error", self._look("damage_class", "name"))

    def test_measure_is_graduated(self):
        res = self._look("measure", "m")
        self.assertTrue(res.get("success"), res)
        self.assertIsInstance(self.layer.renderer(), QgsGraduatedSymbolRenderer)

    def test_the_data_is_never_written(self):
        self._look("ipc_phase", "ipc")
        self.assertEqual([f["ipc"] for f in sorted(self.layer.getFeatures(), key=lambda f: f.id())], [1.0, 3.0, 5.0, None])

    def test_classified_raster_gets_a_palette_with_class_labels(self):
        from cartogen_ai.core.agent.tools import raster_numpy
        from cartogen_ai.core.agent.tools.humanitarian_style import style_classified_raster
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not available")
        arr = np.array([[1, 2], [2, 3]], dtype="uint8")
        from qgis.core import QgsCoordinateReferenceSystem
        info = {"geotransform": (44.0, 0.01, 0.0, 15.0, 0.0, -0.01), "projection": QgsCoordinateReferenceSystem("EPSG:4326").toWkt()}
        try:
            path = raster_numpy.write_single_band(arr, info, nodata=0)
        except Exception as e:
            self.skipTest(f"could not write the test raster here: {e}")
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        ras = QgsRasterLayer(path, "cls")
        self.assertTrue(ras.isValid())
        QgsProject.instance().addMapLayer(ras)
        self.assertTrue(style_classified_raster(ras, 3))
        self.assertIsInstance(ras.renderer(), QgsPalettedRasterRenderer)
        self.assertEqual([c.label for c in ras.renderer().classes()], ["Class 1", "Class 2", "Class 3"])

    def test_obfuscated_points_get_a_ring_marker(self):
        from cartogen_ai.core.agent.tools.humanitarian_style import style_obfuscated_points
        pts = QgsVectorLayer("Point?crs=EPSG:4326&field=n:string", "pts", "memory")
        QgsProject.instance().addMapLayer(pts)
        self.assertTrue(style_obfuscated_points(pts))
        self.assertIsInstance(pts.renderer(), QgsSingleSymbolRenderer)


if __name__ == "__main__":
    unittest.main()
