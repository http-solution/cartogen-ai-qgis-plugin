"""PLAN-031: the verified result gate on real QGIS layers, including a real tool's result and the cost on a 50,000-feature layer.

Written without a QGIS install: CI's first run is its first execution."""
import time
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestResultGateLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _squares(self, name, values, wkt_override=None):
        layer = QgsVectorLayer("Polygon?crs=EPSG:32638&field=admin_name:string&field=population:double&field=need:double&field=sev:double",
                               name, "memory")
        feats = []
        for i, value in enumerate(values):
            f = QgsFeature(layer.fields())
            x = i * 10
            wkt = (wkt_override or {}).get(i, f"POLYGON(({x} 0,{x + 9} 0,{x + 9} 9,{x} 9,{x} 0))")
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([f"D{i}", 100.0 + i, 5.0 + i * 2, value])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _gate(self, layer_name, field="sev"):
        from cartogen_ai.core.agent import result_gate
        return result_gate.attach_checks("some_tool", {"success": True, "layer_name": layer_name, "output_field": field}, "MODIFY")

    def test_a_good_result_passes(self):
        self._squares("good", [0.1, 0.4, 0.7, 0.9])
        result = self._gate("good")
        self.assertIn("checks", result, result)
        self.assertNotIn("checks_note", result)
        self.assertTrue(all(c["status"] == "pass" for c in result["checks"]), result["checks"])

    def test_a_score_that_is_the_same_everywhere_fails(self):
        self._squares("flat", [0.5, 0.5, 0.5, 0.5])
        result = self._gate("flat")
        self.assertIn("field:sev", [c["id"] for c in result["checks"] if c["status"] == "fail"], result["checks"])
        self.assertIn("checks_note", result)

    def test_an_empty_score_field_fails(self):
        layer = self._squares("empty", [0.1, 0.2, 0.3, 0.4])
        layer.startEditing()
        for f in layer.getFeatures():
            layer.changeAttributeValue(f.id(), layer.fields().indexOf("sev"), None)
        layer.commitChanges()
        result = self._gate("empty")
        self.assertIn("field:sev", [c["id"] for c in result["checks"] if c["status"] == "fail"], result["checks"])

    def test_invalid_geometries_are_reported(self):
        bowtie = "POLYGON((0 0,9 9,9 0,0 9,0 0))"
        self._squares("bad", [0.1, 0.4, 0.7, 0.9], wkt_override={1: bowtie})
        result = self._gate("bad")
        geometry = next(c for c in result["checks"] if c["id"] == "geometry")
        self.assertIn(geometry["status"], ("warn", "fail"), geometry)

    def test_a_real_tool_result_carries_checks(self):
        from cartogen_ai.core.agent.tools import analysis_tools
        self._squares("admin", [0.0, 0.0, 0.0, 0.0])
        res = analysis_tools.calculate_severity_index("admin", ["population", "need"], "admin_name", output_field="score_out", confirmed=True)
        self.assertTrue(res.get("success"), res)
        from cartogen_ai.core.agent import result_gate
        res = result_gate.attach_checks("calculate_severity_index", res, "MODIFY")
        self.assertIn("checks", res, "a successful severity result must name layer_name and output_field so the gate runs on it")
        self.assertIn("passed", res["checks_summary"])

    def test_nothing_is_attached_when_the_gate_is_switched_off(self):
        from qgis.core import QgsSettings
        settings = QgsSettings()
        settings.setValue("cartogen_ai/result_gate", False)
        self.addCleanup(lambda: settings.remove("cartogen_ai/result_gate"))
        self._squares("good", [0.1, 0.4, 0.7, 0.9])
        self.assertNotIn("checks", self._gate("good"))

    def test_the_cost_on_a_50000_feature_layer_is_bounded_and_the_sample_is_stated(self):
        layer = QgsVectorLayer("Point?crs=EPSG:32638&field=sev:double", "big", "memory")
        feats = []
        for i in range(50000):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(i % 500, i // 500)))
            f.setAttributes([float(i % 97)])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        started = time.monotonic()
        result = self._gate("big")
        elapsed = time.monotonic() - started
        print(f"[result gate] 50,000 features, {elapsed:.2f} s")
        self.assertLess(elapsed, 10.0)
        self.assertIn("first 5000 of 50000 features checked", result["checks_summary"])


if __name__ == "__main__":
    unittest.main()
