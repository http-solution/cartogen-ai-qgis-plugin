# -*- coding: utf-8 -*-
"""A short follow-up keeps the tools the previous turn used (rc17 hand test R6, 2026-10-06)."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter


def _names(tools):
    return {t["function"]["name"] for t in tools}


class TestCarryOver(unittest.TestCase):
    def setUp(self):
        self.router = ToolRouter(TOOLS_SCHEMA)

    def test_a_bare_crs_answer_loses_the_placing_tool_without_carry_over(self):
        # The bug: nothing in "EPSG:3857" points at add_point_layer.
        self.assertNotIn("add_point_layer", _names(self.router.filter_relevant_tools("EPSG:3857", top_k=40)))

    def test_carry_over_keeps_the_tool_the_conversation_was_using(self):
        tools = self.router.filter_relevant_tools("EPSG:3857", top_k=40, carry_over_tools=("add_point_layer",))
        self.assertIn("add_point_layer", _names(tools))

    def test_unknown_names_and_the_sandbox_fallback_are_not_carried_over(self):
        tools = self.router.filter_relevant_tools(
            "EPSG:3857", top_k=40, carry_over_tools=("no_such_tool", "execute_pyqgis_script"))
        self.assertNotIn("no_such_tool", _names(tools))
        # execute_pyqgis_script keeps its last-resort status: carried only if it scores or nothing else matches.
        base = self.router.filter_relevant_tools("EPSG:3857", top_k=40)
        self.assertEqual("execute_pyqgis_script" in _names(tools), "execute_pyqgis_script" in _names(base))

    def test_at_most_six_tools_are_carried_so_the_list_stays_within_top_k(self):
        many = [t["function"]["name"] for t in TOOLS_SCHEMA][:30]
        tools = self.router.filter_relevant_tools("EPSG:3857", top_k=40, carry_over_tools=many)
        self.assertLessEqual(len(tools), 40)
        base = _names(self.router.filter_relevant_tools("EPSG:3857", top_k=40))
        self.assertLessEqual(len(_names(tools) - base), 6)

    def test_carry_over_does_not_change_a_normal_query(self):
        query = "buffer the point layer by 500 meters"
        self.assertEqual(_names(self.router.filter_relevant_tools(query, top_k=40)),
                         _names(self.router.filter_relevant_tools(query, top_k=40, carry_over_tools=())))


if __name__ == "__main__":
    unittest.main()
