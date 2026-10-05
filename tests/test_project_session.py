# -*- coding: utf-8 -*-
"""GitHub #147 (audit F11): a turn is bound to the project that started it. Offline: the generation counter, and the orchestrator's
guards (tool entry point, history write) driven through a bare object. The real readProject/cleared wiring is not run here."""
import unittest
from unittest.mock import MagicMock

from cartogen_ai.core.agent import project_session
from cartogen_ai.core.agent.agent_orchestrator import CartogenAi


class TestGeneration(unittest.TestCase):
    def test_invalidate_makes_earlier_captures_stale(self):
        g = project_session.current()
        self.assertFalse(project_session.is_stale(g))
        project_session.invalidate()
        self.assertTrue(project_session.is_stale(g))
        self.assertFalse(project_session.is_stale(project_session.current()))

    def test_none_means_not_bound(self):
        project_session.invalidate()
        self.assertFalse(project_session.is_stale(None))


class TestAgentGuards(unittest.TestCase):
    def _agent(self, bound):
        a = CartogenAi.__new__(CartogenAi)
        a._turn_project_session = bound
        return a

    def test_stale_turn_runs_no_tool(self):
        a = self._agent(project_session.current())
        a._execute_tool_dispatch = MagicMock(return_value={"success": True})
        project_session.invalidate()
        res = a._execute_tool("buffer", "{}")
        self.assertTrue(res.get("project_changed"))
        a._execute_tool_dispatch.assert_not_called()

    def test_stale_turn_writes_no_history(self):
        a = self._agent(project_session.current())
        a._get_history_manager = MagicMock()
        project_session.invalidate()
        a._append_history({"role": "user", "content": "x"})
        a._get_history_manager.assert_not_called()

    def test_current_turn_still_writes_history(self):
        a = self._agent(project_session.current())
        a._get_history_manager = MagicMock()
        a._append_history({"role": "user", "content": "x"})
        a._get_history_manager.return_value.append.assert_called_once()


if __name__ == "__main__":
    unittest.main()


def a_registry():
    from cartogen_ai.core.agent import agent_orchestrator
    return agent_orchestrator.TOOL_REGISTRY


class TestToolCommandBoundary(unittest.TestCase):
    """GitHub #138 (audit F02): before-state, tool and after-state are one main-thread unit for ordinary tools; for network-only
    tools only the project-state reads are marshalled. A fake `_run_on_main_thread` records what would cross the thread boundary."""

    def _agent(self):
        a = CartogenAi.__new__(CartogenAi)
        a._turn_project_session = None
        a.on_main = []
        a._transaction_log = MagicMock()
        a._live_layer_ids = MagicMock(return_value={"l1"})
        a._execute_tool_dispatch = MagicMock(return_value={"success": True})

        def fake_run(func, arg):
            a.on_main.append(func)
            return func(arg)
        a._run_on_main_thread = fake_run
        return a

    def test_a_tool_that_returns_a_list_is_not_reported_as_a_failure(self):
        # rc15 hand test: get_layers returns a list; the #138 dict-only check turned it into "Execution failed unexpectedly."
        a = self._agent()
        a._execute_tool_dispatch = MagicMock(return_value=[{"name": "Points"}])
        res = a._execute_tool("get_layers", "{}")
        self.assertEqual(res, [{"name": "Points"}])

    def test_a_tool_that_returns_nothing_is_a_failure_on_every_path(self):
        from unittest.mock import patch
        a = self._agent()
        with patch.dict(a_registry(), {"noop": lambda: None}, clear=False):
            a.memory_manager = MagicMock()
            a.task_manager = MagicMock()
            a._plan_gate = MagicMock()
            a._plan_gate.check.return_value = None
            res = a._real_execute_tool("noop", "{}")
        self.assertEqual(res, {"error": "Execution failed unexpectedly."})

    def test_a_missing_result_is_still_a_failure(self):
        a = self._agent()
        a._run_on_main_thread = lambda func, arg: None
        res = a._execute_tool("get_layers", "{}")
        self.assertEqual(res, {"error": "Execution failed unexpectedly."})

    def test_ordinary_tool_is_a_single_main_thread_command(self):
        a = self._agent()
        res = a._execute_tool("buffer", "{}")
        self.assertEqual(len(a.on_main), 1)
        self.assertTrue(res["success"])
        a._transaction_log.record.assert_called_once()

    def test_network_tool_marshals_only_the_state_reads(self):
        a = self._agent()
        a._execute_tool("search_web", "{}")
        self.assertEqual(len(a.on_main), 2)  # before-state and record; the tool itself ran on the calling thread
        a._transaction_log.record.assert_called_once()

    def test_a_failing_snapshot_function_does_not_abort_the_call(self):
        from unittest.mock import patch
        a = self._agent()
        with patch("cartogen_ai.core.agent.agent_orchestrator.get_snapshot_fn", return_value=MagicMock(side_effect=ValueError("x"))):
            res = a._execute_tool("buffer", "{}")
        self.assertTrue(res["success"])
        self.assertIsNone(a._transaction_log.record.call_args.kwargs["snapshot"])
