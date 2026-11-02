"""PLAN-051: the two gaps the first real hand-test run found (2026-11-03), reproduced offline first, then closed.

D1 (row W11): the fetch tools in TWO_PHASE_TOOLS were dispatched by _execute_two_phase_tool, which never asked the egress gate, so a fetch over a
RESTRICTED layer went out with no confirmation card.
D2 (row W1): the Apply button called _real_execute_tool(..., user_confirmed=True) directly, so a confirmed write was not checked by the result gate
and was not recorded for Undo. Both fixes make those paths do what _execute_tool does for an ordinary call.
Offline: the QGIS-backed pieces are stubbed; the live behaviour is hand-test rows W1 and W11."""
import inspect
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent import result_gate
from cartogen_ai.core.agent.task_manager import AgentTaskManager
from cartogen_ai.core.models.plan_gate import PlanValidationGate

BLOCK = {"action": "block", "layers": {"smoke_zones": "tagged RESTRICTED"}, "result": {"error": "blocked"}, "warning": "w"}
ROOT = Path(__file__).resolve().parents[1]


def make_agent(decision=BLOCK):
    agent = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
    agent.task_manager = AgentTaskManager()
    agent.memory_manager = MagicMock()
    agent._last_tool_call = None
    agent._plan_gate = PlanValidationGate()
    agent._is_plan_gate_enabled = lambda: False
    agent._egress_gate_decision = lambda name, args: decision
    agent.dispatcher = None                       # no Qt: _run_on_main_thread runs inline
    agent._turn_is_stale = lambda: False
    return agent


def pending(agent):
    return [t for t in agent.task_manager.tasks if t.get("status") == "PREVIEW_READY" and t.get("pending_tool")]


class TestFetchToolsAskTheEgressGate(unittest.TestCase):
    def test_every_two_phase_tool_is_stopped_with_a_confirmable_card_before_anything_is_fetched(self):
        for name in sorted(agent_mod.TWO_PHASE_TOOLS):
            agent = make_agent()
            agent._run_two_phase_tool = MagicMock(side_effect=AssertionError(f"{name} reached the network"))
            result = agent._execute_two_phase_tool(name, {"iso3": "YEM", "extent_layer": "smoke_zones", "file_path": "x"})
            self.assertEqual(result.get("status"), "PREVIEW_REQUIRED", name)
            self.assertEqual(len(pending(agent)), 1, name)
            self.assertEqual(pending(agent)[0]["pending_tool"], name)

    def test_with_no_decision_the_call_goes_through_unchanged(self):
        agent = make_agent(decision=None)
        agent._run_two_phase_tool = MagicMock(return_value={"success": True})
        self.assertEqual(agent._execute_two_phase_tool("fetch_worldpop_population", {"iso3": "YEM"}), {"success": True})
        self.assertEqual(pending(agent), [])

    def test_a_warn_decision_lets_the_call_run_and_says_so_in_the_result(self):
        agent = make_agent(decision={"action": "warn", "layers": {"smoke_zones": "x"}, "result": None, "warning": "sent to the provider"})
        agent._run_two_phase_tool = MagicMock(return_value={"success": True})
        result = agent._execute_two_phase_tool("fetch_worldpop_population", {"iso3": "YEM"})
        self.assertEqual(result["egress_warning"], "sent to the provider")

    def test_a_gate_that_fails_blocks_rather_than_lets_the_fetch_through(self):
        agent = make_agent()
        agent._egress_precheck = MagicMock(side_effect=RuntimeError("boom"))
        agent._run_two_phase_tool = MagicMock(side_effect=AssertionError("reached the network"))
        result = agent._execute_two_phase_tool("fetch_worldpop_population", {"iso3": "YEM"})
        self.assertIn("error", result)

    def test_bad_arguments_are_still_reported_the_way_they_were(self):
        agent = make_agent(decision=None)
        self.assertIn("Invalid tool arguments", agent._execute_two_phase_tool("fetch_worldpop_population", "{not json")["error"])


class TestConfirmedCallsGoThroughTheSameWrapper(unittest.TestCase):
    def setUp(self):
        self.agent = make_agent(decision=None)
        self.agent._real_execute_tool = MagicMock(return_value={"success": True, "layer_name": "out"})
        self.agent._capture_before = MagicMock(return_value=({"a"}, "snapshot"))
        self.agent._record_after = MagicMock()

    def test_the_result_gate_and_the_transaction_record_run_for_a_confirmed_write(self):
        with patch.object(result_gate, "attach_checks", side_effect=lambda n, r, o: {**r, "checks_summary": "3 passed"}) as gate:
            result = self.agent.execute_confirmed("calculate_severity_index", {"layer_name": "smoke_admin"})
        self.agent._real_execute_tool.assert_called_once_with("calculate_severity_index", {"layer_name": "smoke_admin"}, user_confirmed=True)
        self.agent._record_after.assert_called_once()
        gate.assert_called_once()
        self.assertEqual(result["checks_summary"], "3 passed")

    def test_arguments_given_as_a_json_string_are_accepted(self):
        with patch.object(result_gate, "attach_checks", side_effect=lambda n, r, o: r):
            self.agent.execute_confirmed("calculate_severity_index", '{"layer_name": "smoke_admin"}')
        self.agent._capture_before.assert_called_once_with("calculate_severity_index", {"layer_name": "smoke_admin"})

    def test_a_failure_in_the_after_steps_never_hides_the_tools_own_result(self):
        self.agent._record_after.side_effect = RuntimeError("boom")
        with patch.object(result_gate, "attach_checks", side_effect=lambda n, r, o: r):
            result = self.agent.execute_confirmed("calculate_severity_index", {})
        self.assertTrue(result["success"])

    def test_a_confirmed_fetch_also_gets_its_source_record(self):
        self.agent._real_execute_tool.return_value = {"success": True, "layer_name": "Yemen"}
        with patch.object(agent_mod.source_record, "attach", side_effect=lambda n, a, r: {**r, "data_source": {"name": "geoBoundaries"}}) as attach, \
                patch.object(result_gate, "attach_checks", side_effect=lambda n, r, o: r):
            result = self.agent.execute_confirmed("fetch_geoboundaries", {"iso3": "YEM"})
        attach.assert_called_once()
        self.assertEqual(result["data_source"]["name"], "geoBoundaries")

    def test_the_apply_button_calls_the_wrapper_not_the_bare_tool(self):
        text = (ROOT / "src" / "cartogen_ai" / "core" / "ui" / "chat_tab_widget.py").read_text(encoding="utf-8")
        self.assertIn("agent.execute_confirmed(pending_tool, pending_args)", text)
        self.assertNotIn("agent._real_execute_tool(pending_tool, pending_args, user_confirmed=True)", text)

    def test_the_wrapper_and_the_ordinary_path_share_their_after_steps(self):
        source = inspect.getsource(agent_mod.CartogenAi.execute_confirmed)
        self.assertIn("result_gate.attach_checks(", source)
        self.assertIn("_record_after(", source)


if __name__ == "__main__":
    unittest.main()
