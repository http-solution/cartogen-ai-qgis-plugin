"""PLAN-011 phase D, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution).

The phase B tests call the export tools with confirmed=True. This runs the whole path through the real agent method `_real_execute_tool`:
the model's call -> PREVIEW_REQUIRED and a pending task -> the user's Apply (user_confirmed=True with the stored arguments) -> the file. It also
shows that a `confirmed` the MODEL puts in its own arguments is stripped, so the card cannot be skipped by the model."""
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

try:
    from qgis.core import (QgsFeature, QgsGeometry, QgsLayoutItemMap, QgsLayoutPoint, QgsLayoutSize, QgsPrintLayout, QgsProject, QgsRectangle,
                           QgsVectorLayer)
    LIVE = True
except ImportError:
    LIVE = False


def _agent():
    from cartogen_ai.core.agent import agent_orchestrator as agent_mod
    from cartogen_ai.core.agent.task_manager import AgentTaskManager
    from cartogen_ai.core.models.plan_gate import PlanValidationGate
    agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
    agent.task_manager = AgentTaskManager()
    agent.memory_manager = MagicMock()
    agent._last_tool_call = None
    agent._plan_gate = PlanValidationGate()
    agent._is_plan_gate_enabled = lambda: False
    agent._egress_gate_decision = lambda name, args: None        # this is the export gate under test, not the cloud-data gate
    return agent


def _pending(agent):
    return [t for t in agent.task_manager.tasks if t.get("status") == "PREVIEW_READY" and t.get("pending_tool")]


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestExportConfirmFlow(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        project = QgsProject.instance()
        project.clear()
        self.addCleanup(project.clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.incidents = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", "incidents", "memory")
        feature = QgsFeature(self.incidents.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POINT(44 15)"))
        feature.setAttributes([1])
        self.incidents.dataProvider().addFeatures([feature])
        self.incidents.updateExtents()
        project.addMapLayer(self.incidents)
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName("flow")
        map_item = QgsLayoutItemMap(layout)
        map_item.setId("MAP_MAIN")
        layout.addLayoutItem(map_item)
        map_item.attemptMove(QgsLayoutPoint(10, 10))
        map_item.attemptResize(QgsLayoutSize(100, 100))
        map_item.setExtent(QgsRectangle(43, 14, 45, 16))
        project.layoutManager().addLayout(layout)
        self.out = os.path.join(self.tmp.name, "flow.png")
        self.agent = _agent()

    def _tag(self, layer, level="SENSITIVE"):
        from cartogen_ai.core.models import sensitivity
        self.assertTrue(sensitivity.set_layer_sensitivity(layer, level, "test"))

    def _call(self, name, args, user_confirmed=False):
        return self.agent._real_execute_tool(name, json.dumps(args) if isinstance(args, dict) else args, user_confirmed=user_confirmed)

    def _apply_pending(self):
        tasks = _pending(self.agent)
        self.assertEqual(len(tasks), 1, tasks)
        return self.agent._real_execute_tool(tasks[0]["pending_tool"], tasks[0]["pending_args"], user_confirmed=True)

    def test_card_then_apply_writes_the_file(self):
        self._tag(self.incidents)
        first = self._call("export_layout", {"layout_name": "flow", "output_path": self.out, "dpi": 60})
        self.assertEqual(first.get("status"), "PREVIEW_REQUIRED", first)
        self.assertFalse(os.path.exists(self.out))
        done = self._apply_pending()
        self.assertTrue(done.get("success"), done)
        self.assertTrue(os.path.isfile(self.out))
        self.assertEqual(done["protected_layers"], [{"layer": "incidents", "level": "SENSITIVE"}], done)

    def test_a_confirmed_flag_in_the_models_own_arguments_is_stripped(self):
        self._tag(self.incidents)
        res = self._call("export_layout", {"layout_name": "flow", "output_path": self.out, "dpi": 60, "confirmed": True})
        self.assertEqual(res.get("status"), "PREVIEW_REQUIRED", res)
        self.assertFalse(os.path.exists(self.out), "the model skipped the confirm card by passing confirmed itself")

    def test_publication_asks_for_a_reason_then_a_card_then_records_it(self):
        refused = self._call("export_layout", {"layout_name": "flow", "output_path": self.out, "dpi": 60, "purpose": "publication"})
        self.assertIn("error", refused, refused)
        self.assertIn("missing", refused["error"])
        card = self._call("export_layout", {"layout_name": "flow", "output_path": self.out, "dpi": 60, "purpose": "publication",
                                            "override_reason": "internal review copy"})
        self.assertEqual(card.get("status"), "PREVIEW_REQUIRED", card)
        done = self._apply_pending()
        self.assertTrue(done.get("success"), done)
        with open(done["publication_record"], encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["reason_given"], "internal review copy")

    def _add_atlas_coverage(self):
        districts = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string", "districts", "memory")
        features = []
        for name, wkt in (("north", "POLYGON((43 15,45 15,45 16,43 16,43 15))"), ("south", "POLYGON((43 14,45 14,45 15,43 15,43 14))")):
            f = QgsFeature(districts.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([name])
            features.append(f)
        districts.dataProvider().addFeatures(features)
        districts.updateExtents()
        QgsProject.instance().addMapLayer(districts)
        return districts

    def test_atlas_with_a_protected_coverage_layer_waits_then_writes_one_file_per_feature(self):
        districts = self._add_atlas_coverage()
        self._tag(districts)
        outdir = os.path.join(self.tmp.name, "atlas")
        args = {"layout_name": "flow", "coverage_layer_name": "districts", "output_directory": outdir, "filename_field": "name",
                "output_format": "png", "dpi": 60}
        first = self._call("export_layout_atlas", args)
        self.assertEqual(first.get("status"), "PREVIEW_REQUIRED", first)
        self.assertFalse(os.path.exists(outdir), "files were written before the user confirmed")
        done = self._apply_pending()
        self.assertTrue(done.get("success"), done)
        self.assertEqual(sorted(os.path.basename(p) for p in done["output_files"]), ["north.png", "south.png"])
        self.assertTrue(any(p["layer"] == "districts" for p in done["protected_layers"]), done)

    def test_atlas_without_a_protected_layer_needs_no_card(self):
        self._add_atlas_coverage()
        outdir = os.path.join(self.tmp.name, "atlas_open")
        res = self._call("export_layout_atlas", {"layout_name": "flow", "coverage_layer_name": "districts", "output_directory": outdir,
                                                 "filename_field": "name", "output_format": "png", "dpi": 60})
        self.assertTrue(res.get("success"), res)
        self.assertNotIn("protected_layers", res)


if __name__ == "__main__":
    unittest.main()
