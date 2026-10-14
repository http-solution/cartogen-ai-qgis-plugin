"""Replays 26 real sessions from the rc40 hand test (tests/fixtures/recorded_sessions_rc40.json) through the CURRENT agent loop.

What it covers: given the model's recorded behaviour (the tool calls it made, in order, and the reply it wrote), the loop still runs every
call with the arguments the model chose, hands the recorded results back, and delivers the model's reply. A guard, gate, loop-limit, history
or tool-dispatch change that swallows a call, rewrites its arguments, turns a good reply into an error or replaces the reply fails here.
What it does NOT cover: the model's own choices (a different release offers different tools and prompts, so a real model may choose
differently), the QGIS tools themselves (their results are the recorded ones), and the UI. Those need the hand-test rows.

The sessions are synthetic-data requests (smoke_* layers); user names in paths were scrubbed."""
import json
import os
import unittest
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from tests.test_agent_runner import _make_bare_agent

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "recorded_sessions_rc40.json")
with open(FIXTURE, encoding="utf-8") as fh:
    SESSIONS = json.load(fh)


class _ScriptedModel:
    """One recorded tool call per model round, then the recorded final reply."""

    def __init__(self, session):
        self.steps = session["steps"]
        self.final = session["final_reply"]
        self.calls = 0

    def complete(self, messages, tools=None, max_tokens=None):
        i = self.calls
        self.calls += 1
        if i < len(self.steps):
            step = self.steps[i]
            return {"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"c{i}", "function": {"name": step["tool"], "arguments": json.dumps(step["arguments"])}}]}}
        return {"message": {"role": "assistant", "content": self.final}}


def _replay(session):
    model = _ScriptedModel(session)
    agent = _make_bare_agent(model)
    executed = []
    results = {s["tool"] + json.dumps(s["arguments"], sort_keys=True): s["result"] for s in session["steps"]}

    def fake_execute(self, name, args):
        args = json.loads(args) if isinstance(args, str) else args          # the loop hands over the model's raw JSON text
        executed.append((name, args))
        raw = results.get(name + json.dumps(args, sort_keys=True))
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return {"result": raw}

    with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
         patch.object(agent_mod.CartogenAi, "_execute_tool", fake_execute), \
         patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
         patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", []), \
         patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
        text = agent.run(session["request"])
    return text, executed


class TestRecordedSessionsStillRun(unittest.TestCase):
    def test_fixture_is_not_empty(self):
        self.assertGreaterEqual(len(SESSIONS), 20)

    def test_every_recorded_call_is_executed_with_the_models_arguments(self):
        problems = []
        for s in SESSIONS:
            _text, executed = _replay(s)
            want = [(st["tool"], st["arguments"]) for st in s["steps"]]
            if executed != want:
                problems.append(f"{s['id']} {s['request'][:40]!r}: executed {[e[0] for e in executed]} wanted {[w[0] for w in want]}")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_models_reply_is_delivered_not_replaced_by_an_error(self):
        problems = []
        for s in SESSIONS:
            text, _executed = _replay(s)
            lead = s["final_reply"][:80].strip()
            if text.startswith(("[API error]", "[Agent stopped]")) or lead not in text:
                problems.append(f"{s['id']} {s['request'][:40]!r}: got {text[:90]!r}")
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
