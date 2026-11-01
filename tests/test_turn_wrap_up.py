"""DEF-21: a turn that runs out of rounds, or whose data source is down, ends with an answer, not a bare stop.

Why: the owner's Taiz run (2026-11-01) ended at the tool-call limit with a generic "[Agent stopped]" and, earlier, kept trying other routes
after the OSM download tool said the server was overloaded and not to try again."""
import unittest
from typing import ClassVar
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent import loop_guard

from tests.test_agent_runner import _make_bare_agent

SCHEMA = [{"type": "function", "function": {"name": "get_layers", "description": "list layers", "parameters": {"type": "object", "properties": {}}}}]


class _Settings:
    values: ClassVar = {}

    def value(self, key, default=None, *a, **k):
        return self.values.get(key, default)


class _ToolsThenAnswer:
    """Asks for a tool while tools are offered; answers in plain text once none are."""

    def __init__(self):
        self.calls = []

    def complete(self, messages, tools=None, max_tokens=None):
        self.calls.append((list(tools or []), [m.get("content") for m in messages if m.get("role") == "user"]))
        if tools:
            return {"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"c{len(self.calls)}", "function": {"name": "get_layers", "arguments": "{}"}}]}}
        return {"message": {"role": "assistant", "content": "Here is what is done and what is not."}}


def _run(settings, tool_result=None):
    _Settings.values = settings
    client = _ToolsThenAnswer()
    agent = _make_bare_agent(client)
    agent.loop_guard_enabled = False
    with patch.object(agent_mod, "QgsSettings", _Settings), \
         patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
         patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: tool_result or {"success": True}), \
         patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
         patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", SCHEMA), \
         patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
        text = agent.run("look at the layers")
    return text, client


class TestTurnWrapUp(unittest.TestCase):
    def test_the_last_round_is_an_answer_round_with_no_tools(self):
        text, client = _run({"cartogen_ai/max_tool_iterations": 5})
        self.assertEqual(len(client.calls), 5)
        self.assertEqual(client.calls[-1][0], [], "the last call must not offer tools")
        self.assertIn(loop_guard.LAST_ROUND_NUDGE, client.calls[-1][1])
        self.assertTrue(all(tools for tools, _ in client.calls[:-1]))
        self.assertEqual(text, "Here is what is done and what is not.")

    def test_a_tiny_cap_has_no_wrap_up_round(self):
        text, client = _run({"cartogen_ai/max_tool_iterations": 3})
        self.assertEqual(len(client.calls), 3)
        self.assertTrue(all(tools for tools, _ in client.calls))
        self.assertIn("tool-call limit", text)
        self.assertIn("Done so far", text)

    def test_a_data_source_that_is_down_ends_the_turn_with_one_answer_round(self):
        down = {"error": "The OpenStreetMap Overpass server is overloaded right now", "retryable_later": True}
        text, client = _run({"cartogen_ai/max_tool_iterations": 20}, tool_result=down)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[1][0], [])
        self.assertIn(loop_guard.DATA_SOURCE_DOWN_NUDGE, client.calls[1][1])
        self.assertTrue(text.startswith("Here is what is done and what is not."), text)
        self.assertIn("overloaded", text)         # the existing reconcile note about the failed tool is kept

    def test_pure_helpers(self):
        self.assertTrue(loop_guard.last_round_due(4, 5))
        self.assertFalse(loop_guard.last_round_due(3, 5))
        self.assertFalse(loop_guard.last_round_due(2, 3))
        self.assertFalse(loop_guard.last_round_due(0, 0))
        self.assertTrue(loop_guard.data_source_down({"retryable_later": True}))
        self.assertFalse(loop_guard.data_source_down({"retryable_later": False}))
        self.assertFalse(loop_guard.data_source_down("retryable_later"))


if __name__ == "__main__":
    unittest.main()
