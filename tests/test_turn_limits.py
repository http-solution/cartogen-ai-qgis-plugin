# -*- coding: utf-8 -*-
"""rc7 smoke test F10: per-turn tool-call cap, optional per-turn token budget, and a per-turn token figure.

The cap defaults to the long-standing MAX_ITERATIONS; the token budget defaults to a provisional figure derived from rc22 hand-test logs (0 stored = no limit). Both are read from QGIS settings and fall back to those defaults on any bad value."""
import unittest
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent.usage_tracker import UsageTracker

from tests.test_agent_runner import _make_bare_agent


class _Settings:
    values = {}

    def value(self, key, default=None, *a, **k):
        return self.values.get(key, default)


class _LoopingClient:
    """Always asks for another tool call; reports 100 input + 50 output tokens per call."""

    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools=None, max_tokens=None):
        self.calls += 1
        return {"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c%d" % self.calls, "function": {"name": "get_layers", "arguments": "{}"}}]},
            "usage": {"input_tokens": 100, "output_tokens": 50}}


def _run(settings):
    _Settings.values = settings
    client = _LoopingClient()
    agent = _make_bare_agent(client)
    with patch.object(agent_mod, "QgsSettings", _Settings), \
         patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
         patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: {"success": True}), \
         patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
         patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []), \
         patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
        text = agent.run("look at the layers")
    return text, client, agent


class TestTurnLimits(unittest.TestCase):
    def test_defaults(self):
        _Settings.values = {}
        with patch.object(agent_mod, "QgsSettings", _Settings):
            self.assertEqual(agent_mod.CartogenAi._turn_limits(_make_bare_agent(None)), (agent_mod.MAX_ITERATIONS, agent_mod.DEFAULT_TURN_TOKEN_BUDGET))

    def test_stored_zero_means_no_limit(self):
        _Settings.values = {"cartogen_ai/max_turn_tokens": "0"}
        with patch.object(agent_mod, "QgsSettings", _Settings):
            self.assertEqual(agent_mod.CartogenAi._turn_limits(_make_bare_agent(None))[1], 0)

    def test_bad_values_fall_back_to_defaults(self):
        _Settings.values = {"cartogen_ai/max_tool_iterations": "lots", "cartogen_ai/max_turn_tokens": "x"}
        with patch.object(agent_mod, "QgsSettings", _Settings):
            self.assertEqual(agent_mod.CartogenAi._turn_limits(_make_bare_agent(None)), (agent_mod.MAX_ITERATIONS, agent_mod.DEFAULT_TURN_TOKEN_BUDGET))

    def test_the_cap_is_clamped(self):
        _Settings.values = {"cartogen_ai/max_tool_iterations": 0}
        with patch.object(agent_mod, "QgsSettings", _Settings):
            self.assertEqual(agent_mod.CartogenAi._turn_limits(_make_bare_agent(None))[0], 1)
        _Settings.values = {"cartogen_ai/max_tool_iterations": 9999}
        with patch.object(agent_mod, "QgsSettings", _Settings):
            self.assertEqual(agent_mod.CartogenAi._turn_limits(_make_bare_agent(None))[0], 100)

    def test_a_low_cap_stops_the_turn_after_that_many_model_calls(self):
        text, client, _ = _run({"cartogen_ai/max_tool_iterations": 3})
        self.assertEqual(client.calls, 3)
        self.assertIn("tool-call limit", text)

    def test_a_token_budget_stops_the_turn_and_says_so(self):
        text, client, _ = _run({"cartogen_ai/max_turn_tokens": 400})   # 150 per call -> stops after 3 calls
        self.assertEqual(client.calls, 3)
        self.assertIn("token budget", text)
        self.assertIn("400", text)

    def test_no_budget_means_the_cap_alone_decides(self):
        _, client, _ = _run({"cartogen_ai/max_tool_iterations": 4})
        self.assertEqual(client.calls, 4)


class TestTurnUsageText(unittest.TestCase):
    def test_nothing_before_a_turn_begins(self):
        self.assertIsNone(UsageTracker().turn_text())

    def test_only_this_turns_tokens_are_reported(self):
        t = UsageTracker()
        t.accumulate({"input_tokens": 1000, "output_tokens": 500})
        t.begin_turn()
        t.accumulate({"input_tokens": 200, "output_tokens": 100})
        t.accumulate({"input_tokens": 300, "output_tokens": 0})
        self.assertEqual(t.turn_tokens(), 600)
        self.assertEqual(t.turn_text(), "This turn ~600 tokens (2 calls)")

    def test_no_reported_usage_gives_no_figure_not_zero(self):
        t = UsageTracker()
        t.begin_turn()
        t.accumulate(None)
        self.assertIsNone(t.turn_text())

    def test_silent_calls_are_mentioned(self):
        t = UsageTracker()
        t.begin_turn()
        t.accumulate({"input_tokens": 10, "output_tokens": 5})
        t.accumulate(None)
        self.assertIn("1 with no usage reported", t.turn_text())

    def test_the_agent_exposes_the_turn_text_after_a_run(self):
        _, _, agent = _run({"cartogen_ai/max_tool_iterations": 2})
        self.assertEqual(agent.get_turn_usage_text(), "This turn ~300 tokens (2 calls)")


if __name__ == "__main__":
    unittest.main()
