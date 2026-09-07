# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch
from cartogen_ai.core.agent.prompts import build_system_prompt
from cartogen_ai.core.agent.memory import SpatialMemoryManager
from cartogen_ai.core.agent.task_manager import AgentTaskManager
import cartogen_ai.core.agent.agent as agent_mod
from cartogen_ai.core.agent.transactions import TurnTransactionLog


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
    # run() resets this unconditionally at the top of every call (point 20's
    # transaction log, see agent/transactions.py) -- a bare __new__()'d agent
    # needs one too, even though these tests patch _execute_tool itself and
    # never exercise the log's actual recording.
    agent._transaction_log = TurnTransactionLog()
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



class TestExecuteToolTransactionRecording(unittest.TestCase):
    """_execute_tool (agent.py) wraps every tool call with a before/after
    live-layer-id snapshot and records it into self._transaction_log --
    point 20's transaction log (see agent/transactions.py). This exercises
    that wrapper directly, independent of run()'s loop."""

    def _make_agent(self):
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent._transaction_log = TurnTransactionLog()
        return agent

    def test_records_operation_type_and_result(self):
        agent = self._make_agent()
        with patch.object(agent_mod.CartogenAi, "_execute_tool_dispatch",
                           lambda self, name, args: {"success": True, "layers": []}), \
             patch.object(agent_mod.CartogenAi, "_live_layer_ids", lambda self: set()):
            result = agent._execute_tool("get_layers", "{}")

        self.assertEqual(result, {"success": True, "layers": []})
        entries = agent._transaction_log.summary()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "get_layers")
        self.assertEqual(entries[0]["operation_type"], "READ")
        self.assertTrue(entries[0]["success"])

    def test_new_layer_after_a_create_tool_is_recorded_as_undoable(self):
        agent = self._make_agent()
        layer_ids = iter([{"a"}, {"a", "b"}])  # before, then after
        with patch.object(agent_mod.CartogenAi, "_execute_tool_dispatch",
                           lambda self, name, args: {"success": True, "layer_name": "buf_1"}), \
             patch.object(agent_mod.CartogenAi, "_live_layer_ids", lambda self: next(layer_ids)):
            agent._execute_tool("buffer_analysis", "{}")

        entry = agent._transaction_log.last_undoable()
        self.assertIsNotNone(entry)
        self.assertEqual(entry["name"], "buffer_analysis")
        self.assertEqual(entry["undo"]["layer_ids"], ["b"])

    def test_unknown_tool_name_records_none_operation_type(self):
        agent = self._make_agent()
        with patch.object(agent_mod.CartogenAi, "_execute_tool_dispatch",
                           lambda self, name, args: {"error": "Unknown tool: bogus_tool"}), \
             patch.object(agent_mod.CartogenAi, "_live_layer_ids", lambda self: set()):
            agent._execute_tool("bogus_tool", "{}")

        entries = agent._transaction_log.summary()
        self.assertIsNone(entries[0]["operation_type"])
        self.assertFalse(entries[0]["success"])


if __name__ == "__main__":
    unittest.main()
