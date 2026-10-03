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
