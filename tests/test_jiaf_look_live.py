# -*- coding: utf-8 -*-
"""JIAF 2 map looks in real QGIS. Written without a local QGIS: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsRuleBasedRenderer, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestJiafLookLive(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=sev:double&field=st:double", "districts", "memory")
        rows = [("A", 2.0, 1.0), ("B", 3.0, 3.0), ("C", 5.0, 2.0), ("D", None, None)]
        feats = []
        for i, (name, sev, st) in enumerate(rows):
            f = QgsFeature(layer.fields())
            x = 44.0 + i * 0.1
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 15, {x + 0.09} 15, {x + 0.09} 15.09, {x} 15.09, {x} 15))"))
            f.setAttributes([name, sev, st])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        self.layer = layer

    def _look(self, look, field):
        from cartogen_ai.core.agent.tools.humanitarian_look_tools import apply_humanitarian_look
        return apply_humanitarian_look("districts", look, field)

    def _symbols_by_name(self):
        """{feature name: symbols the renderer draws it with}, through the renderer itself."""
        from qgis.core import QgsRenderContext
        renderer = self.layer.renderer()
        ctx = QgsRenderContext()
        renderer.startRender(ctx, self.layer.fields())
        try:
            return {f["name"]: renderer.symbolsForFeature(f, ctx) for f in self.layer.getFeatures()}
        finally:
            renderer.stopRender(ctx)

    def test_phase_look_is_rule_based_with_a_not_assessed_class(self):
        res = self._look("jiaf_severity", "sev")
        self.assertTrue(res.get("success"), res)
        self.assertIsInstance(self.layer.renderer(), QgsRuleBasedRenderer)
        self.assertEqual(res["classes"][:2], ["1 None / minimal", "2 Stress"])
        self.assertIn("not assessed", res["classes"][-1])
        self.assertTrue(self.layer.renderer().rootRule().children()[-1].isElse())

    def test_a_unit_without_a_phase_is_still_drawn(self):
        self._look("jiaf_severity", "sev")
        drawn = self._symbols_by_name()
        self.assertTrue(drawn["D"], "the unit with no phase must still get a symbol (grey), not vanish")
        self.assertTrue(drawn["C"])

    def test_review_status_look_applies(self):
        res = self._look("jiaf_review_severity", "st")
        self.assertTrue(res.get("success"), res)
        self.assertIn("Pending: flagged, needs the group", res["classes"])

    def test_the_data_is_never_written(self):
        self._look("jiaf_severity", "sev")
        self.assertEqual([f["sev"] for f in sorted(self.layer.getFeatures(), key=lambda f: f.id())], [2.0, 3.0, 5.0, None])

    def test_errors_change_nothing(self):
        before = type(self.layer.renderer())
        self.assertIn("error", self._look("jiaf_severity", "name"))
        self.assertIn("error", self._look("jiaf_severity", "nope"))
        self.assertIs(type(self.layer.renderer()), before)


if __name__ == "__main__":
    unittest.main()
