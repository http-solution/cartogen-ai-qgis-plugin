# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch
from cartogen_ai.core.agent.prompts import build_system_prompt
from cartogen_ai.core.agent.memory import SpatialMemoryManager
from cartogen_ai.core.agent.task_manager import AgentTaskManager
import cartogen_ai.core.agent.agent as agent_mod


class TestAgentRunner(unittest.TestCase):
    def test_dynamic_prompt_builder(self):
        tm = AgentTaskManager()
        tm.create_plan("Urban Growth Analysis", ["Load Landuse", "Calculate Centroids"])

        mm = SpatialMemoryManager()
        mm.store_project_note("city", "Damascus")

        prompt = build_system_prompt(task_manager=tm, memory_manager=mm)
        self.assertIn("Urban Growth Analysis", prompt)
        self.assertIn("Damascus", prompt)
        self.assertIn("AGENTIC TASK & MEMORY RULES", prompt)

    def test_system_prompt_includes_compact_registered_task_context(self):
        prompt = build_system_prompt(map_context={"task_directive": "Recognised task 01.01. Deliver: an HTML dashboard."})
        self.assertIn("REGISTERED TASK CONTEXT", prompt)
        self.assertIn("Recognised task 01.01", prompt)

class _FakeClient:
    """Returns one tool call, then a final answer -- just enough to exercise
    run()'s tool-calling loop once."""
    def __init__(self, tool_name="get_layers", tool_result=None):
        self.calls = 0
        self.tool_name = tool_name

    def complete(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return {"message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "c1", "function": {"name": self.tool_name, "arguments": "{}"}}],
            }}
        return {"message": {"role": "assistant", "content": "All done."}}


def _make_bare_agent(client):
    agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
    agent.client = client
    agent.conversation_history = []
    agent.task_manager = MagicMock()
    agent.task_manager.get_plan.return_value = None
    agent.memory_manager = MagicMock()
    agent._auto_model_provider = None
    return agent


class TestToolStepCallback(unittest.TestCase):
    """agent.run()'s tool_step_callback is what lets the UI show live
    per-tool-call progress in chat (previously nothing was visible during a
    multi-tool-call turn) -- verified live against a real run() call, not
    just that the parameter exists."""

    def _run_with_tool_result(self, tool_result):
        client = _FakeClient()
        agent = _make_bare_agent(client)
        steps = []

        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: tool_result), \
             patch("cartogen_ai.core.agent.agent.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent.TOOLS_SCHEMA", []):
            final_text = agent.run("list my layers", tool_step_callback=lambda n, s, e: steps.append((n, s, e)))
        return final_text, steps

    def test_fires_running_then_done_on_success(self):
        final_text, steps = self._run_with_tool_result({"success": True, "layers": []})
        self.assertEqual(final_text, "All done.")
        self.assertEqual(steps, [("get_layers", "running", None), ("get_layers", "done", None)])

    def test_fires_running_then_failed_on_tool_error(self):
        final_text, steps = self._run_with_tool_result({"error": "Layer 'X' not found"})
        self.assertEqual(steps, [
            ("get_layers", "running", None),
            ("get_layers", "failed", "Layer 'X' not found"),
        ])

    def test_run_still_works_with_no_callback_given(self):
        # tool_step_callback is optional -- confirms the loop doesn't require it.
        client = _FakeClient()
        agent = _make_bare_agent(client)
        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: {"success": True}), \
             patch("cartogen_ai.core.agent.agent.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent.TOOLS_SCHEMA", []):
            final_text = agent.run("list my layers")
        self.assertEqual(final_text, "All done.")

    def test_a_broken_callback_does_not_break_the_agent_loop(self):
        # tool_step_callback is UI-side rendering -- a bug there must never
        # take down the actual agent turn.
        client = _FakeClient()
        agent = _make_bare_agent(client)

        def broken_callback(name, status, error):
            raise RuntimeError("UI rendering bug")

        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: {"success": True}), \
             patch("cartogen_ai.core.agent.agent.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent.TOOLS_SCHEMA", []):
            final_text = agent.run("list my layers", tool_step_callback=broken_callback)
        self.assertEqual(final_text, "All done.")


if __name__ == "__main__":
    unittest.main()
