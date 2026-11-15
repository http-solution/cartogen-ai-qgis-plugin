"""PLAN-055 gap B: a stray pasted fragment ("template: access_map") must not make the model fetch and add layers either.
_real_execute_tool already refused changes on such a turn (GitHub #130, tests/test_stray_fragment_gate.py), but the fetch tools in TWO_PHASE_TOOLS
go through _execute_two_phase_tool, which did not ask. 13 of the 15 are CREATE tools. Offline: nothing is fetched, the QGIS-backed pieces are stubbed."""
import unittest
from unittest.mock import MagicMock

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.task_manager import AgentTaskManager

CHANGING = (tool_operations.CREATE, tool_operations.MODIFY, tool_operations.DELETE, tool_operations.PUBLISH)


def make_agent(fragment):
    agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
    agent.task_manager = AgentTaskManager()
    agent.memory_manager = MagicMock()
    agent._last_tool_call = None
    agent._stray_fragment_turn = fragment
    agent._egress_gate_decision = lambda name, args: None
    agent.dispatcher = None                       # no Qt: _run_on_main_thread runs inline
    agent._turn_is_stale = lambda: False
    return agent


def changing_fetch_tools():
    return sorted(n for n in agent_mod.TWO_PHASE_TOOLS if tool_operations.get_tool_operation_type(n) in CHANGING)


class TestFetchToolsOnAStrayFragmentTurn(unittest.TestCase):
    def test_there_are_changing_fetch_tools_to_check(self):
        self.assertGreaterEqual(len(changing_fetch_tools()), 13)

    def test_every_changing_fetch_tool_is_refused_and_nothing_is_fetched(self):
        for name in changing_fetch_tools():
            agent = make_agent(True)
            agent._run_two_phase_tool = MagicMock(side_effect=AssertionError(f"{name} reached the network"))
            result = agent._execute_two_phase_tool(name, {"iso3": "YEM", "file_path": "x"})
            self.assertTrue(result.get("blocked"), name)
            self.assertIn("nothing was changed", result["error"], name)

    def test_the_refusal_asks_no_confirmation_card(self):
        agent = make_agent(True)
        agent._run_two_phase_tool = MagicMock()
        agent._execute_two_phase_tool("fetch_worldpop_population", {"iso3": "YEM"})
        self.assertEqual([t for t in agent.task_manager.tasks if t.get("pending_tool")], [])

    def test_a_reading_fetch_tool_still_runs(self):
        reads = sorted(n for n in agent_mod.TWO_PHASE_TOOLS if n not in changing_fetch_tools())
        self.assertTrue(reads)
        for name in reads:
            agent = make_agent(True)
            agent._run_two_phase_tool = MagicMock(return_value={"success": True})
            self.assertEqual(agent._execute_two_phase_tool(name, {"query": "q"}), {"success": True}, name)

    def test_a_normal_turn_is_untouched(self):
        agent = make_agent(False)
        agent._run_two_phase_tool = MagicMock(return_value={"success": True})
        self.assertEqual(agent._execute_two_phase_tool("fetch_worldpop_population", {"iso3": "YEM"}), {"success": True})

    def test_both_dispatch_paths_use_the_one_shared_check(self):
        agent = make_agent(True)
        self.assertEqual(agent._stray_fragment_block("fetch_worldpop_population", False)["blocked"], True)
        self.assertIsNone(agent._stray_fragment_block("fetch_worldpop_population", True))   # a person's confirmation still runs
        self.assertIsNone(agent._stray_fragment_block("get_layers", False))


class TestNoFetchToolNeedsAPlan(unittest.TestCase):
    """PLAN-055 gap C: the plan gate only covers DELETE and PUBLISH tools, so it never applied to a fetch tool. Pinned so a reclassification is noticed."""
    def test_no_fetch_tool_is_delete_or_publish(self):
        from cartogen_ai.core.models.plan_gate import PlanValidationGate
        for name in sorted(agent_mod.TWO_PHASE_TOOLS):
            self.assertFalse(PlanValidationGate.requires_plan(name), name)


if __name__ == "__main__":
    unittest.main()
