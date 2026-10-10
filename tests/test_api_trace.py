# -*- coding: utf-8 -*-
"""The opt-in model-call trace (core/agent/api_trace.py) and its summary. 2026-10-10: the exported captures held only the system
instruction, so the many-calls investigation could not be finished; this records requests, replies and usage per call."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent import api_trace
from tests.test_agent_runner import _make_bare_agent

SYSTEM = "You are Cartogen AI. " * 50
TOOLS = [{"type": "function", "function": {"name": "get_layers", "description": "d", "parameters": {"type": "object"}}},
         {"type": "function", "function": {"name": "buffer_analysis", "description": "d", "parameters": {"type": "object"}}}]


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cartogen_trace_test_")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.trace = api_trace.ApiTrace(self.dir)

    def lines(self):
        files = [f for f in os.listdir(self.dir) if f.endswith(".jsonl")]
        out = []
        for f in files:
            with open(os.path.join(self.dir, f), encoding="utf-8") as fh:
                out += [json.loads(line) for line in fh]
        return out


class TestRecording(_Base):
    def test_a_call_is_one_line_with_request_reply_tools_and_usage(self):
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "List the layers"}]
        reply = {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "function": {"name": "get_layers", "arguments": "{}"}}]}
        self.assertTrue(self.trace.record("t1", 0, "GeminiClient", "gemini-flash", messages, TOOLS, response=reply,
                                          usage={"input_tokens": 9000, "output_tokens": 20}, latency_ms=850))
        (line,) = self.lines()
        self.assertEqual((line["turn_id"], line["call_index"], line["model"], line["outcome"]), ("t1", 0, "gemini-flash", "ok"))
        self.assertEqual([m["role"] for m in line["messages"]], ["user"])          # the system text is not repeated here
        self.assertEqual(line["tools"]["names"], ["get_layers", "buffer_analysis"])
        self.assertEqual(line["response"]["tool_calls"][0]["name"], "get_layers")
        self.assertEqual(line["usage"]["input_tokens"], 9000)
        self.assertEqual(line["system_instruction"]["chars"], len(SYSTEM))

    def test_the_system_instruction_is_stored_once_per_distinct_text(self):
        for i in range(3):
            self.trace.record("t1", i, "P", "m", [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "x"}], TOOLS)
        self.trace.record("t2", 0, "P", "m", [{"role": "system", "content": SYSTEM + "more"}, {"role": "user", "content": "y"}], TOOLS)
        files = os.listdir(os.path.join(self.dir, "system_instructions"))
        self.assertEqual(len(files), 2)
        hashes = {rec["system_instruction"]["sha256_12"] for rec in self.lines()}
        self.assertEqual({h + ".txt" for h in hashes}, set(files))

    def test_secrets_are_redacted_and_images_are_not_stored(self):
        key = "sk-" + "a" * 40
        messages = [{"role": "user", "content": [{"type": "text", "text": f"my key is {key}"},
                                                   {"type": "image_url", "image_url": {"url": "data:image/png;base64," + "A" * 5000}}]}]
        self.trace.record("t1", 0, "P", "m", messages, [])
        text = json.dumps(self.lines())
        self.assertNotIn(key, text)
        self.assertNotIn("A" * 100, text)
        self.assertIn("image", text)

    def test_a_long_message_is_truncated_with_a_note(self):
        self.trace.record("t1", 0, "P", "m", [{"role": "tool", "content": "x" * 50000, "tool_call_id": "c1"}], [])
        content = self.lines()[0]["messages"][0]["content"]
        self.assertLess(len(content), 31000)
        self.assertIn("truncated", content)

    def test_an_error_call_records_the_error_and_no_reply(self):
        self.trace.record("t1", 0, "P", "m", [{"role": "user", "content": "x"}], [], outcome="provider_error", error="HTTP 429")
        line = self.lines()[0]
        self.assertEqual((line["outcome"], line["error"], line["response"]), ("provider_error", "HTTP 429", None))

    def test_recording_never_raises(self):
        trace = api_trace.ApiTrace(os.path.join(self.dir, "a", "b"))
        with patch("os.makedirs", side_effect=OSError("disk full")):
            self.assertFalse(trace.record("t", 0, "P", "m", [], []))


class TestSummary(_Base):
    def _turn(self, turn, n, tool="get_layers", args="{}", system=SYSTEM):
        for i in range(n):
            reply = {"role": "assistant", "tool_calls": [{"id": f"c{i}", "function": {"name": tool, "arguments": args}}]} if i < n - 1 \
                else {"role": "assistant", "content": "done"}
            self.trace.record(turn, i, "P", "m", [{"role": "system", "content": system}, {"role": "user", "content": "q"}], TOOLS,
                              response=reply, usage={"input_tokens": 1000, "output_tokens": 10, "cached_tokens": 100})

    def test_one_row_per_turn_with_totals(self):
        self._turn("t1", 2)
        rows, flags = api_trace.summarize(api_trace.read_records(self.dir))
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["calls"], rows[0]["input_tokens"], rows[0]["cached_tokens"]), (2, 2000, 200))
        self.assertEqual(rows[0]["tools_called"], ["get_layers"])
        self.assertEqual(flags, [])

    def test_a_long_turn_and_a_repeated_identical_call_are_flagged(self):
        self._turn("loop", 8)
        _rows, flags = api_trace.summarize(api_trace.read_records(self.dir))
        self.assertTrue(any("8 model calls" in f for f in flags))
        self.assertTrue(any("identical tool call repeated" in f and "get_layers x7" in f for f in flags))

    def test_a_system_instruction_that_changes_inside_one_turn_is_flagged(self):
        self.trace.record("t1", 0, "P", "m", [{"role": "system", "content": "A"}], [])
        self.trace.record("t1", 1, "P", "m", [{"role": "system", "content": "B"}], [])
        _rows, flags = api_trace.summarize(api_trace.read_records(self.dir))
        self.assertTrue(any("system instruction changed" in f for f in flags))

    def test_a_failed_call_is_flagged(self):
        self.trace.record("t1", 0, "P", "m", [], [], outcome="provider_error", error="x")
        _rows, flags = api_trace.summarize(api_trace.read_records(self.dir))
        self.assertTrue(any("provider_error" in f for f in flags))


class _ToolThenText:
    def __init__(self):
        self.calls = 0
        self.model = "scripted-model"

    def complete(self, messages, tools=None, max_tokens=None):
        self.calls += 1
        if self.calls == 1:
            return {"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "function": {"name": "get_layers", "arguments": "{}"}}]}, "usage": {"input_tokens": 50, "output_tokens": 5}}
        return {"message": {"role": "assistant", "content": "3 layers"}, "usage": {"input_tokens": 80, "output_tokens": 4}}


class TestOrchestratorWritesTheTrace(_Base):
    def _run(self, enabled):
        agent = _make_bare_agent(_ToolThenText())
        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: {"success": True}), \
             patch.object(agent_mod.CartogenAi, "_api_trace", lambda self: self_trace if enabled else None), \
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="the system text"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", TOOLS), \
             patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
            self_trace = self.trace
            return agent.run("Show me something")

    def test_every_model_call_of_a_run_is_recorded_with_its_reply_when_on(self):
        self._run(True)
        lines = self.lines()
        self.assertEqual([rec["call_index"] for rec in lines], [0, 1])
        self.assertEqual(lines[0]["response"]["tool_calls"][0]["name"], "get_layers")
        self.assertEqual(lines[1]["response"]["content"], "3 layers")
        self.assertEqual(lines[1]["usage"]["input_tokens"], 80)
        self.assertEqual(len({rec["turn_id"] for rec in lines}), 1)
        self.assertTrue(any(m["role"] == "tool" for m in lines[1]["messages"]))        # the second request carries the tool result

    def test_nothing_is_written_when_off(self):
        self._run(False)
        self.assertEqual(self.lines(), [])


if __name__ == "__main__":
    unittest.main()
