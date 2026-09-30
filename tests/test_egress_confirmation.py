# -*- coding: utf-8 -*-
"""
Regression tests for the cloud-data-protection override flow (rc7 smoke test, 2026-09-30,
findings F02 / F03).

Live symptom: with a SENSITIVE layer and "Cloud data protection" on, a read via
execute_pyqgis_script was correctly blocked, but the user never got a working Confirm /
Cancel. The model wrote its own "please confirm" text, a typed "confirm" went back to the
model, and the model then invented the rows.

Two independent defects, both reproduced offline with the repo's own fixtures:
  1. _real_execute_tool returned egress_gate.preview_required(...) early, BEFORE the code
     that registers the pending confirmation task, so nothing confirmable existed.
  2. Even with a task registered, confirming injected confirmed=True into the tool's
     arguments unconditionally; only 11 tools accept that parameter, so
     execute_pyqgis_script(script, confirmed=True) raised TypeError.
A third hazard: the model's own create_plan replaces the whole plan and discarded any
gate task registered earlier in the turn.
"""
import unittest
from unittest.mock import MagicMock, patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent.task_manager import AgentTaskManager
from cartogen_ai.core.models.plan_gate import PlanValidationGate

SENSITIVE_DECISION = {
    "action": "block",
    "layers": {"Health Facilities (OSM, Yemen)": "tagged SENSITIVE"},
    "result": {"error": "blocked"},
    "warning": "w",
}


def _agent():
    agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
    agent.task_manager = AgentTaskManager()
    agent.memory_manager = MagicMock()
    agent._last_tool_call = None
    agent._plan_gate = PlanValidationGate()
    agent._is_plan_gate_enabled = lambda: False
    agent._egress_gate_decision = lambda name, args: SENSITIVE_DECISION
    return agent


def _pending(agent):
    return [t for t in agent.task_manager.tasks
            if t.get("status") == "PREVIEW_READY" and t.get("pending_tool")]


class TestBlockedCallIsConfirmable(unittest.TestCase):
    def test_a_blocked_call_registers_a_confirmable_pending_task(self):
        agent = _agent()
        ran = []
        with patch.dict(agent_mod.TOOL_REGISTRY, {"execute_pyqgis_script": lambda script: ran.append(script)}):
            res = agent._real_execute_tool("execute_pyqgis_script", '{"script": "x"}')
        self.assertEqual(res["status"], "PREVIEW_REQUIRED")
        self.assertEqual(ran, [], "a blocked call must not execute")
        pending = _pending(agent)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["pending_tool"], "execute_pyqgis_script")
        self.assertEqual(pending[0]["pending_args"], {"script": "x"})

    def test_confirming_runs_a_tool_that_has_no_confirmed_parameter(self):
        agent = _agent()
        ran = []

        def fake_execute(script):  # deliberately NO `confirmed` parameter, like the real tool
            ran.append(script)
            return {"success": True, "result": "rows"}

        with patch.dict(agent_mod.TOOL_REGISTRY, {"execute_pyqgis_script": fake_execute}):
            agent._real_execute_tool("execute_pyqgis_script", '{"script": "x"}')
            task = _pending(agent)[0]
            res = agent._real_execute_tool(task["pending_tool"], task["pending_args"], user_confirmed=True)
        self.assertNotIn("error", res, res)
        self.assertEqual(ran, ["x"])
        self.assertIn("egress_override_note", res)

    def test_a_tool_that_does_accept_confirmed_still_receives_it(self):
        agent = _agent()
        seen = {}

        def destructive(layer_name, confirmed=False):
            seen["confirmed"] = confirmed
            return {"success": True}

        with patch.dict(agent_mod.TOOL_REGISTRY, {"remove_layer": destructive}):
            agent._real_execute_tool("remove_layer", {"layer_name": "Health Facilities (OSM, Yemen)"}, user_confirmed=True)
        self.assertTrue(seen.get("confirmed"))

    def test_the_gate_still_blocks_when_nobody_confirmed(self):
        agent = _agent()
        ran = []
        with patch.dict(agent_mod.TOOL_REGISTRY, {"execute_pyqgis_script": lambda script: ran.append(script)}):
            agent._real_execute_tool("execute_pyqgis_script", '{"script": "x"}')
            agent._real_execute_tool("execute_pyqgis_script", '{"script": "x"}')
        self.assertEqual(ran, [])


class TestPendingTaskSurvivesCreatePlan(unittest.TestCase):
    def test_a_models_create_plan_does_not_discard_the_pending_task(self):
        agent = _agent()
        with patch.dict(agent_mod.TOOL_REGISTRY, {"execute_pyqgis_script": lambda script: None}):
            agent._real_execute_tool("execute_pyqgis_script", '{"script": "x"}')
        self.assertEqual(len(_pending(agent)), 1)

        agent.task_manager.create_plan("Inspect attributes", ["Retrieve the first 5 rows"])

        pending = _pending(agent)
        self.assertEqual(len(pending), 1, "the confirmable task was lost by create_plan")
        self.assertEqual(pending[0]["pending_tool"], "execute_pyqgis_script")
        self.assertEqual(agent.task_manager.tasks[0]["description"], "Retrieve the first 5 rows")

    def test_ids_stay_unique_after_the_carry_over(self):
        tm = AgentTaskManager()
        tm.create_plan("first", ["a"])
        task = tm.add_task("Preview x operation")["task"]
        tm.set_task_preview(task["id"], "code", "why", True)
        task["pending_tool"] = "x"
        tm.create_plan("second", ["b", "c"])
        ids = [t["id"] for t in tm.tasks]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(tm.tasks), 3)

    def test_finished_tasks_are_still_archived_not_carried(self):
        tm = AgentTaskManager()
        tm.create_plan("first", ["a"])
        tm.update_task("1", "DONE", "ok")
        tm.create_plan("second", ["b"])
        self.assertEqual([t["description"] for t in tm.tasks], ["b"])
        self.assertEqual(len(tm.plan_history), 1)


if __name__ == "__main__":
    unittest.main()
