"""PLAN-045: the workflow report from real layers -- checks stored by the gate, lineage from the tagger, the real tool writing a file.

Written without a QGIS install: CI's first run is its first execution."""
import os
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestWorkflowReportLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _layer(self, name, values):
        layer = QgsVectorLayer("Polygon?crs=EPSG:32638&field=score:double", name, "memory")
        feats = []
        for i, v in enumerate(values):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({i * 10} 0,{i * 10 + 9} 0,{i * 10 + 9} 9,{i * 10} 9,{i * 10} 0))"))
            f.setAttributes([v])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(layer)
        return layer

    def test_a_two_step_chain_with_a_failed_check_is_documented(self):
        from cartogen_ai.core.agent import result_gate, source_record
        from cartogen_ai.core.agent.lineage import tag_layer_lineage
        from cartogen_ai.core.agent.tools.provenance_tools import write_workflow_report
        districts = self._layer("Districts", [1.0, 2.0, 3.0])
        coverage = self._layer("Coverage", [5.0, 5.0, 5.0])
        source_record.tag_layer(districts, source_record.build("fetch_geoboundaries", {"iso3": "YEM", "admin_level": "ADM2"}, {"success": True}))
        tag_layer_lineage(districts, "fetch_geoboundaries", {"iso3": "YEM"}, [])
        tag_layer_lineage(coverage, "service_area", {"minutes": 30}, ["Districts"])
        self.assertTrue(result_gate.record_checks(coverage, "service_area", [{"id": "value_range", "status": "fail", "detail": "all values equal"}]))
        out = os.path.join(tempfile.mkdtemp(), "report.md")
        result = write_workflow_report("Access to care", ["Coverage"], ["Roads as of 2024."], out)
        self.assertTrue(result.get("success"), result)
        self.assertEqual((result["layers"], result["failed_checks"]), (2, 1))
        with open(out, encoding="utf-8") as fh:
            text = fh.read()
        for part in ("FAILED checks", "value_range -- all values equal", "geoBoundaries", "service_area from Districts -> Coverage", "Roads as of 2024.",
                     "No automated result checks were recorded for: Districts"):
            self.assertIn(part, text)

    def test_a_missing_layer_is_an_error_not_an_empty_report(self):
        from cartogen_ai.core.agent.tools.provenance_tools import write_workflow_report
        self.assertIn("error", write_workflow_report("x", ["Nope"], None, os.path.join(tempfile.mkdtemp(), "r.md")))


if __name__ == "__main__":
    unittest.main()
