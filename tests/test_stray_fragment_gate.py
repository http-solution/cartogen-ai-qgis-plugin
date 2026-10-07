# -*- coding: utf-8 -*-
"""A stray pasted fragment ("template: access_map") is not a request: the agent may read the project but must not create, change or
export anything for it (GitHub #130; the rc20 hand test saw a real model create a print layout for that fragment alone)."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent import agent_orchestrator as agent_mod
from cartogen_ai.core.agent import task_matcher as tm


class TestIsStrayFragment(unittest.TestCase):
    def test_the_reported_fragment_is_one(self):
        self.assertTrue(tm.is_stray_fragment("template: access_map"))

    def test_natural_short_replies_are_not(self):
        for reply in ("yes", "ok", "Sanaa", "Hub_A", "use the roads layer"):
            self.assertFalse(tm.is_stray_fragment(reply), reply)

    def test_a_crs_answer_to_a_question_is_not(self):
        self.assertTrue(tm.is_stray_fragment("EPSG:3857"))                                   # alone it is label-shaped...
        self.assertFalse(tm.is_stray_fragment("EPSG:3857", "Which CRS are those coordinates in?"))   # ...but here it answers

    def test_a_real_request_is_not_even_when_it_contains_a_colon(self):
        self.assertFalse(tm.is_stray_fragment("create a layout: access_map"))
        self.assertFalse(tm.is_stray_fragment("what is template: access_map?"))

    def test_longer_text_is_not(self):
        self.assertFalse(tm.is_stray_fragment("template: access_map with the five facility types shown"))


class TestFragmentTurnBlocksChanges(unittest.TestCase):
    def _agent(self, fragment):
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent.task_manager = MagicMock()
        agent.memory_manager = MagicMock()
        agent._last_tool_call = None
        agent._stray_fragment_turn = fragment
        agent._plan_gate = MagicMock()
        agent._plan_gate.check.return_value = None
        agent._egress_gate_decision = lambda n, a: None
        return agent

    def _call(self, agent, name, user_confirmed=False):
        calls = []

        def fake(**kwargs):
            calls.append(kwargs)
            return {"success": True}
        with patch.dict(agent_mod.TOOL_REGISTRY, {name: fake}):
            return agent._real_execute_tool(name, "{}", user_confirmed=user_confirmed), calls

    def test_a_layout_is_not_created_for_a_fragment(self):
        res, calls = self._call(self._agent(True), "create_print_layout")
        self.assertTrue(res.get("blocked"), res)
        self.assertIn("nothing was changed", res["error"])
        self.assertEqual(calls, [])

    def test_reading_the_project_is_still_allowed(self):
        res, calls = self._call(self._agent(True), "get_layers")
        self.assertEqual(res, {"success": True})
        self.assertEqual(len(calls), 1)

    def test_a_normal_turn_is_untouched(self):
        res, calls = self._call(self._agent(False), "create_print_layout")
        self.assertEqual(res, {"success": True})
        self.assertEqual(len(calls), 1)

    def test_a_human_confirmed_card_still_runs(self):
        res, calls = self._call(self._agent(True), "create_print_layout", user_confirmed=True)
        self.assertNotIn("blocked", res)
        self.assertEqual(len(calls), 1)


class TestIsStrayFragmentTurn(unittest.TestCase):
    def _agent(self, history, tasks=()):
        agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        agent.task_manager = MagicMock()
        agent.task_manager.tasks = list(tasks)
        agent._read_history_snapshot = lambda: list(history)
        return agent

    def test_a_fragment_after_a_statement_is_stray(self):
        agent = self._agent([{"role": "assistant", "content": "Here are your layers."}])
        self.assertTrue(agent._is_stray_fragment_turn("template: access_map"))

    def test_a_fragment_after_a_question_is_an_answer(self):
        agent = self._agent([{"role": "assistant", "content": "Which CRS do you mean?"}])
        self.assertFalse(agent._is_stray_fragment_turn("EPSG:3857"))

    def test_a_pending_confirmation_means_it_is_not_stray(self):
        agent = self._agent([], tasks=[{"status": "PREVIEW_READY"}])
        self.assertFalse(agent._is_stray_fragment_turn("template: access_map"))


if __name__ == "__main__":
    unittest.main()
