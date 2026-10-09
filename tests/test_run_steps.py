# -*- coding: utf-8 -*-
"""run_steps: validation before anything runs, reference resolution, stop rules, and the round-trip saving in the agent loop.
The tool dispatcher is stubbed (no QGIS main thread offline), so this proves the loop logic, not any real tool or any real model."""
import json
import unittest
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent import step_runner as sr
from tests.test_agent_runner import _make_bare_agent

SCHEMAS = {"buffer_layer": {"required": ["layer_name", "distance"]}, "clip_layer": {"required": ["input_layer", "overlay_layer"]},
           "delete_layer": {"required": ["layer_name"]}, "get_layers": {}}


def op(name):
    return "DELETE" if name == "delete_layer" else "CREATE"


class TestValidation(unittest.TestCase):
    def check(self, steps):
        return sr.validate_steps(steps, SCHEMAS, op)

    def test_a_good_chain_passes(self):
        self.assertIsNone(self.check([{"tool": "buffer_layer", "arguments": {"layer_name": "a", "distance": 5}},
                                      {"tool": "clip_layer", "arguments": {"input_layer": "$prev.layer_name", "overlay_layer": "b"}}]))

    def test_bad_plans_are_refused_before_running(self):
        self.assertIn("not one of the tools", self.check([{"tool": "nope", "arguments": {}}]))
        self.assertIn("missing required", self.check([{"tool": "buffer_layer", "arguments": {"layer_name": "a"}}]))
        self.assertIn("own", self.check([{"tool": "delete_layer", "arguments": {"layer_name": "a"}}]))
        self.assertIn("cannot be used", self.check([{"tool": "run_steps", "arguments": {}}]))
        self.assertIn("EARLIER", self.check([{"tool": "buffer_layer", "arguments": {"layer_name": "$1.x", "distance": 1}}]))
        self.assertIn("At most", self.check([{"tool": "get_layers"}] * 9))

    def test_references_resolve_or_fail_clearly(self):
        got, err = sr.resolve_arguments({"a": "$1.layer_name", "b": ["$prev.n", "plain"]}, [{"layer_name": "L"}, {"n": 3}])
        self.assertEqual((got, err), ({"a": "L", "b": [3, "plain"]}, None))
        got, err = sr.resolve_arguments({"a": "$1.missing"}, [{"layer_name": "L"}])
        self.assertIsNone(got)
        self.assertIn("no field", err)

    def test_text_that_merely_contains_a_dollar_is_left_alone(self):
        self.assertEqual(sr.resolve_arguments({"a": "cost $1.50"}, [{}])[0], {"a": "cost $1.50"})


class _Scripted:
    """Replays model responses; counts calls (each is one full-size round trip)."""

    def __init__(self, responses):
        self.responses, self.calls, self.last_messages = list(responses), 0, []

    def complete(self, messages, tools=None, max_tokens=None):
        self.calls += 1
        self.last_messages = list(messages)
        return {"message": self.responses.pop(0), "usage": {"input_tokens": 100, "output_tokens": 20}}


def _call(i, name, args):
    return {"id": "c%d" % i, "function": {"name": name, "arguments": json.dumps(args)}}


def _tools(*names):
    return [{"type": "function", "function": {"name": n, "description": n, "parameters": SCHEMAS.get(n) or {"type": "object", "properties": {}}}}
            for n in names]


class TestLoop(unittest.TestCase):
    def run_agent(self, responses, execute):
        client = _Scripted(responses)
        agent = _make_bare_agent(client)
        ran = []

        def fake(self_, name, args):
            ran.append((name, json.loads(args) if isinstance(args, str) else args))
            return execute(name, ran[-1][1])
        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", fake), \
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", _tools("buffer_layer", "clip_layer", "run_steps")), \
             patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
            text = agent.run("buffer then clip")
        return text, client, ran

    chain = [{"tool": "buffer_layer", "arguments": {"layer_name": "roads", "distance": 100}},
             {"tool": "clip_layer", "arguments": {"input_layer": "$prev.layer_name", "overlay_layer": "zones"}}]

    def test_a_chain_costs_two_model_calls_instead_of_three(self):
        done = {"role": "assistant", "content": "done"}
        batched, c1, ran = self.run_agent(
            [{"role": "assistant", "content": None, "tool_calls": [_call(1, "run_steps", {"steps": self.chain})]}, done],
            lambda n, a: {"success": True, "layer_name": n + "_out"})
        self.assertEqual(batched, "done")
        self.assertEqual(c1.calls, 2)
        self.assertEqual(ran[1], ("clip_layer", {"input_layer": "buffer_layer_out", "overlay_layer": "zones"}))
        one_by_one, c2, _ = self.run_agent(
            [{"role": "assistant", "content": None, "tool_calls": [_call(1, "buffer_layer", self.chain[0]["arguments"])]},
             {"role": "assistant", "content": None, "tool_calls": [_call(2, "clip_layer", {"input_layer": "buffer_layer_out", "overlay_layer": "zones"})]},
             done], lambda n, a: {"success": True, "layer_name": n + "_out"})
        self.assertEqual(c2.calls, 3)

    def tool_payload(self, client):
        return json.loads([m for m in client.last_messages if m.get("role") == "tool"][-1]["content"])

    def test_it_stops_at_the_first_error_and_says_what_ran(self):
        text, client, ran = self.run_agent(
            [{"role": "assistant", "content": None, "tool_calls": [_call(1, "run_steps", {"steps": self.chain})]},
             {"role": "assistant", "content": "stopped"}],
            lambda n, a: {"error": "bad layer"})
        self.assertEqual(len(ran), 1)
        payload = self.tool_payload(client)
        self.assertEqual((payload["completed"], payload["total"], payload["stopped_at_step"]), (0, 2, 1))
        self.assertIn("bad layer", payload["error"])
        self.assertIn("NOT run", payload["not_run"])

    def test_it_stops_at_a_pending_confirmation(self):
        text, client, ran = self.run_agent(
            [{"role": "assistant", "content": None, "tool_calls": [_call(1, "run_steps", {"steps": self.chain})]},
             {"role": "assistant", "content": "waiting"}],
            lambda n, a: {"status": "PREVIEW_REQUIRED"})
        self.assertEqual(len(ran), 1)
        payload = self.tool_payload(client)
        self.assertEqual(payload["status"], "PREVIEW_REQUIRED")
        self.assertNotIn("error", payload)

    def test_an_invalid_plan_runs_nothing(self):
        bad = [{"tool": "buffer_layer", "arguments": {"layer_name": "roads"}}]
        text, client, ran = self.run_agent(
            [{"role": "assistant", "content": None, "tool_calls": [_call(1, "run_steps", {"steps": bad})]},
             {"role": "assistant", "content": "fixed later"}], lambda n, a: {"success": True})
        self.assertEqual(ran, [])
        self.assertIn("missing required", self.tool_payload(client)["error"])


if __name__ == "__main__":
    unittest.main()
