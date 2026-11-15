"""PLAN-048 stage 2: export_workflow_file on real layers -- the preview, the write after confirmation, and a file that passes the validator.

Written without a QGIS install: CI's first run is its first execution."""
import json
import os
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestWorkflowExportLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        layer = QgsVectorLayer("Point?crs=EPSG:32638&field=name:string", "Clinics", "memory")
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(500000, 3800000)))
        feature.setAttributes(["c1"])
        layer.dataProvider().addFeatures([feature])
        QgsProject.instance().addMapLayer(layer)

    def _make_buffer(self):
        from cartogen_ai.core.agent.lineage import tag_layer_lineage
        from cartogen_ai.core.agent.tools.vector_tools import buffer_analysis
        args = {"layer_name": "Clinics", "distance": 1000, "output_name": "clinic_reach"}
        result = buffer_analysis(**args)
        self.assertTrue(result.get("success"), result)
        out = QgsProject.instance().mapLayersByName(result.get("layer_name") or "clinic_reach")[0]
        tag_layer_lineage(out, "buffer_analysis", args, ["Clinics"])          # what the orchestrator does after a successful call
        return out.name()

    def test_preview_first_then_a_file_that_the_validator_accepts(self):
        from cartogen_ai.core import tool_operations
        from cartogen_ai.core.agent import workflow_file
        from cartogen_ai.core.agent.tools.registry import TOOLS_SCHEMA
        from cartogen_ai.core.agent.tools.workflow_file_tools import export_workflow_file
        name = self._make_buffer()
        target = os.path.join(tempfile.mkdtemp(), "reach")
        preview = export_workflow_file([name], "Reach", "d", target)
        self.assertEqual(preview.get("status"), "PREVIEW_REQUIRED", preview)
        self.assertIn("buffer_analysis", preview["code_snippet"])
        self.assertFalse(os.path.exists(target + ".cgworkflow.json"), "nothing is written before the person confirms")
        written = export_workflow_file(**preview["arguments"])
        self.assertTrue(written.get("success"), written)
        path = written["output_path"]
        self.assertTrue(path.endswith(".cgworkflow.json") and os.path.isfile(path), path)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        doc, problems, _w = workflow_file.validate(text, workflow_file.schemas_from(TOOLS_SCHEMA), tool_operations.get_tool_operation_type)
        self.assertEqual(problems, [])
        self.assertEqual(list(doc["roles"]), ["clinics"])
        self.assertEqual(doc["steps"][0]["arguments"]["layer_name"], "@clinics")
        self.assertEqual(doc["roles"]["clinics"].get("geometry"), "point")
        self.assertNotIn("Users", text)
        self.assertEqual(json.loads(text)["steps"][0]["tool"], "buffer_analysis")

    def test_a_layer_with_no_history_is_an_error_not_an_empty_file(self):
        from cartogen_ai.core.agent.tools.workflow_file_tools import export_workflow_file
        result = export_workflow_file(["Clinics"], output_path=os.path.join(tempfile.mkdtemp(), "x"))
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
