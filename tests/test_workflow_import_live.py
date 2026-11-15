"""PLAN-048 stage 3 on real QGIS: the import dialog builds, only enables Run when the roles are mapped, and the model-free runner executes a mapped file
through the real tools and records where the layers came from.

Written without a QGIS install: CI's first run is its first execution. Nobody has looked at the dialog."""
import copy
import unittest
from unittest.mock import MagicMock

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False

SOURCE = {
    "format": "cartogen-workflow", "version": 1, "name": "Reach", "description": "d",
    "roles": {"facilities": {"kind": "vector", "geometry": "point"}},
    "steps": [
        {"tool": "buffer_analysis", "arguments": {"layer_name": "@facilities", "distance": 1000, "output_name": "wf_reach"}},
        {"tool": "get_feature_count", "arguments": {"layer_name": "$prev.layer_name"}},
    ],
}


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestWorkflowImportLive(unittest.TestCase):
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

    def _document(self):
        from cartogen_ai.core import tool_operations
        from cartogen_ai.core.agent import workflow_file
        from cartogen_ai.core.agent.tools.registry import TOOLS_SCHEMA
        doc, problems, _w = workflow_file.validate(copy.deepcopy(SOURCE), workflow_file.schemas_from(TOOLS_SCHEMA), tool_operations.get_tool_operation_type)
        self.assertEqual(problems, [])
        return doc

    def test_the_dialog_enables_run_only_when_every_role_is_mapped(self):
        from cartogen_ai.core import tool_operations
        from cartogen_ai.core.agent.tools.workflow_file_tools import project_layers
        from cartogen_ai.core.ui.workflow_import_dialog import WorkflowImportDialog
        dialog = WorkflowImportDialog(None, "x.cgworkflow.json", self._document(), [], [], project_layers(), tool_operations.get_tool_operation_type)
        self.assertFalse(dialog._run.isEnabled())
        self.assertEqual(dialog._table.rowCount(), 2)
        combo = dialog._combos["facilities"]
        combo.setCurrentIndex(combo.findData("Clinics"))
        self.assertTrue(dialog._run.isEnabled(), dialog._messages.text())
        self.assertEqual(dialog.mapping(), {"facilities": "Clinics"})
        self.assertEqual(dialog.start_at(), 1)

    def test_a_refused_file_shows_its_problems_and_has_no_run_button(self):
        from cartogen_ai.core import tool_operations
        from cartogen_ai.core.ui.workflow_import_dialog import WorkflowImportDialog
        dialog = WorkflowImportDialog(None, "bad.json", None, ["Step 1: not allowed."], [], [], tool_operations.get_tool_operation_type)
        self.assertFalse(hasattr(dialog, "_run"))

    def test_the_runner_executes_the_mapped_file_through_the_real_tools_and_records_the_file(self):
        import cartogen_ai.core.agent.agent_orchestrator as agent_mod
        from cartogen_ai.core.agent import workflow_import
        from cartogen_ai.core.agent.lineage import get_layer_lineage
        from tests.test_agent_runner import _make_bare_agent
        doc = self._document()
        steps, problems = workflow_import.apply_mapping(doc, {"facilities": "Clinics"})
        self.assertEqual(problems, [])
        agent = _make_bare_agent(MagicMock())
        agent.dispatcher = None                       # no worker thread here: the tools run inline on this (main) thread
        agent._on_dispatcher_thread = lambda: True
        agent._turn_project_session = None
        result = agent.run_workflow_steps(steps, {"name": doc["name"], "fingerprint": doc["fingerprint"]})
        self.assertTrue(result.get("success"), result)
        made = QgsProject.instance().mapLayersByName("wf_reach")
        self.assertTrue(made, [layer.name() for layer in QgsProject.instance().mapLayers().values()])
        history = get_layer_lineage(made[0])
        self.assertEqual(history[-1]["tool"], "buffer_analysis")
        self.assertEqual(history[-1].get("workflow", {}).get("fingerprint"), doc["fingerprint"])
        self.assertIsNone(agent._workflow_context)
        self.assertIs(agent_mod.CartogenAi, type(agent))


if __name__ == "__main__":
    unittest.main()
