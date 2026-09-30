# -*- coding: utf-8 -*-
"""
run()-level test of the anti-fabrication guard (rc7 smoke test F03, 2026-09-30): a blocked tool
call followed by a model answer that contains an invented table must not reach the user
unflagged, and the model must be told, inside the tool result itself, that the call did not run.
"""
import unittest
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent.task_manager import AgentTaskManager

from tests.test_agent_runner import _make_bare_agent

FAKE_ROWS = (
    "Here are the first 5 rows:\n\n"
    "| fid | osm_id | fclass | name |\n|---|---|---|---|\n"
    "| 1 | 368412095 | hospital | Al-Thawra Modern General Hospital |\n"
    "| 2 | 439812401 | clinic | Al-Kuwait University Hospital Clinic |\n"
)


class _ToolThenTextClient:
    """First response: one tool call. Second response: `final_text`."""

    def __init__(self, tool_name, final_text):
        self.tool_name = tool_name
        self.final_text = final_text
        self.calls = 0
        self.messages_per_call = []

    def complete(self, messages, tools=None, max_tokens=None):
        self.calls += 1
        self.messages_per_call.append([dict(m) for m in messages])
        if self.calls == 1:
            return {"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "function": {"name": self.tool_name, "arguments": "{}"}}]}}
        return {"message": {"role": "assistant", "content": self.final_text}}


def _run(tool_result, final_text=FAKE_ROWS, task_manager=None):
    client = _ToolThenTextClient("execute_pyqgis_script", final_text)
    agent = _make_bare_agent(client)
    if task_manager is not None:
        agent.task_manager = task_manager
    with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
         patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: dict(tool_result)), \
         patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
         patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []), \
         patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
        text = agent.run("List the first 5 rows of the Health Facilities attribute table.")
    return text, client


class TestUnbackedDataGuardInRun(unittest.TestCase):
    def test_an_invented_table_after_a_blocked_call_is_flagged(self):
        text, _ = _run({"status": "PREVIEW_REQUIRED", "rationale": "protected data"})
        self.assertIn("No data was retrieved", text)
        self.assertIn("execute_pyqgis_script", text)
        self.assertNotIn("368412095", text)  # rows no tool produced are replaced by a notice

    def test_the_model_is_told_inside_the_tool_result_that_the_call_did_not_run(self):
        _, client = _run({"status": "PREVIEW_REQUIRED", "rationale": "protected data"})
        tool_msgs = [m for m in client.messages_per_call[1] if m.get("role") == "tool"]
        self.assertEqual(len(tool_msgs), 1)
        self.assertIn("did not run", tool_msgs[0]["content"].lower())

    def test_an_egress_block_is_treated_the_same_way(self):
        text, _ = _run({"status": "EGRESS_BLOCKED", "layers": ["Health Facilities"]})
        self.assertIn("No data was retrieved", text)

    def test_a_table_backed_by_a_successful_call_is_left_alone(self):
        text, _ = _run({"success": True, "result": "rows"})
        self.assertNotIn("No data was retrieved", text)
        self.assertEqual(text, FAKE_ROWS)

    def test_prose_after_a_blocked_call_is_left_alone(self):
        prose = "This read is waiting for your confirmation in the app."
        text, _ = _run({"status": "PREVIEW_REQUIRED"}, final_text=prose)
        self.assertEqual(text, prose)

    def test_a_gate_task_still_pending_from_an_earlier_turn_also_counts(self):
        tm = AgentTaskManager()
        task = tm.add_task("Preview execute_pyqgis_script operation")["task"]
        tm.set_task_preview(task["id"], "", "protected data", True)
        task["pending_tool"] = "execute_pyqgis_script"
        text, _ = _run({"success": True}, task_manager=tm)
        self.assertIn("No data was retrieved", text)


class TestConfirmationProseInRun(unittest.TestCase):
    def test_the_models_own_confirm_request_is_dropped_when_a_gate_card_is_pending(self):
        text, _ = _run({"status": "PREVIEW_REQUIRED", "rationale": "protected data"},
                       final_text="The read is pending.\nPlease reply with Confirm to proceed.")
        self.assertIn("pending", text)
        self.assertNotIn("reply with Confirm", text)

    def test_the_same_text_is_kept_when_nothing_is_pending(self):
        text, _ = _run({"success": True}, final_text="Please reply with Confirm to proceed.")
        self.assertIn("reply with Confirm", text)


if __name__ == "__main__":
    unittest.main()
