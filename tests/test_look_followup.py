# -*- coding: utf-8 -*-
"""Issue 232: finish the map step when the model ends a turn without making the look call a tool handed it."""
import json
import unittest
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent import look_followup as lf
from tests.test_agent_runner import _make_bare_agent
from tests.test_run_steps import _Scripted, _call, _tools

HINT = {"tool": "apply_humanitarian_look", "args": {"layer_name": "adm", "look": "inform_risk", "field": "inf_risk"}}


class TestPure(unittest.TestCase):
    def test_a_hint_never_acted_on_is_pending(self):
        calls = [("import_humanitarian_table", {"kind": "inform"}, {"success": True, "map_looks": [HINT]})]
        self.assertEqual(lf.pending_hints(calls), [HINT["args"]])
        self.assertIn("apply_humanitarian_look(layer_name='adm', look='inform_risk', field='inf_risk')", lf.nudge_for("import INFORM and show it on the map", calls))

    def test_an_applied_hint_is_not_pending(self):
        calls = [("x", {}, {"map_look": HINT}), ("apply_humanitarian_look", HINT["args"], {"success": True})]
        self.assertEqual(lf.pending_hints(calls), [])

    def test_a_failed_apply_leaves_it_pending(self):
        calls = [("x", {}, {"map_look": HINT}), ("apply_humanitarian_look", HINT["args"], {"error": "nope"})]
        self.assertEqual(len(lf.pending_hints(calls)), 1)

    def test_unosat_needs_the_loaded_layer_to_make_a_hint(self):
        imp = ("import_humanitarian_table", {"kind": "UNOSAT"}, {"success": True, "mapping_used": {"damage_class": "Main_Damage_Site_Class"}})
        self.assertEqual(lf.pending_hints([imp]), [])
        load = ("load_tabular_data_as_layer", {}, {"success": True, "layer_name": "unosat_pts"})
        self.assertEqual(lf.pending_hints([imp, load]),
                         [{"layer_name": "unosat_pts", "look": "damage_class", "field": "Main_Damage_Site_Class"}])

    def test_no_nudge_unless_the_user_asked_to_see_it(self):
        calls = [("x", {}, {"map_look": HINT})]
        self.assertIsNone(lf.nudge_for("calculate the INFORM total", calls))
        self.assertIsNotNone(lf.nudge_for("show the INFORM risk on the map", calls))

    def test_a_pending_confirmation_is_not_a_hint(self):
        self.assertEqual(lf.pending_hints([("x", {}, {"status": "PREVIEW_REQUIRED", "map_look": HINT})]), [])


class TestLoop(unittest.TestCase):
    def run_turn(self, query, tool_result):
        client = _Scripted([
            {"role": "assistant", "content": None, "tool_calls": [_call(1, "import_humanitarian_table", {"kind": "inform"})]},
            {"role": "assistant", "content": "Imported."},
            {"role": "assistant", "content": "Drawn."}])
        agent = _make_bare_agent(client)
        ran = []

        def fake(self_, name, args):
            ran.append(name)
            return tool_result if name == "import_humanitarian_table" else {"success": True}
        with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
             patch.object(agent_mod.CartogenAi, "_execute_tool", fake), \
             patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
             patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", _tools("import_humanitarian_table", "apply_humanitarian_look")), \
             patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
            text = agent.run(query)
        return text, client

    def test_the_model_is_asked_once_to_make_the_look_call(self):
        text, client = self.run_turn("import the INFORM file and show it on the map", {"success": True, "map_looks": [HINT]})
        self.assertEqual(client.calls, 3)                    # tool call, premature final answer, answer after the nudge
        nudges = [m["content"] for m in client.last_messages if m.get("role") == "user" and "default colours" in str(m.get("content"))]
        self.assertEqual(len(nudges), 1)
        self.assertEqual(text, "Drawn.")

    def test_no_nudge_when_the_user_did_not_ask_for_a_map(self):
        text, client = self.run_turn("import the INFORM file", {"success": True, "map_looks": [HINT]})
        self.assertEqual(client.calls, 2)
        self.assertEqual(text, "Imported.")
        self.assertEqual(json.dumps(text), '"Imported."')


if __name__ == "__main__":
    unittest.main()
