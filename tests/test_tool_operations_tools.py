# -*- coding: utf-8 -*-
"""Tests for agent/tools/tool_operations_tools.py -- the registered-tool
surface over agent/tool_operations.py (point 20)."""
import unittest

from cartogen_ai.core.agent.tools.tool_operations_tools import (
    get_tool_operation_type, list_tools_by_operation_type,
)


class TestGetToolOperationTypeTool(unittest.TestCase):
    def test_known_tool_returns_its_category(self):
        result = get_tool_operation_type("remove_layer")
        self.assertEqual(result, {"tool_name": "remove_layer", "operation_type": "DELETE"})

    def test_unknown_tool_returns_error(self):
        result = get_tool_operation_type("not_a_real_tool")
        self.assertIn("error", result)
        self.assertIn("not_a_real_tool", result["error"])


class TestListToolsByOperationTypeTool(unittest.TestCase):
    def test_valid_category_returns_names_and_count(self):
        result = list_tools_by_operation_type("DELETE")
        self.assertEqual(result["operation_type"], "DELETE")
        self.assertIn("remove_layer", result["tool_names"])
        self.assertEqual(result["count"], len(result["tool_names"]))

    def test_invalid_category_returns_error_not_exception(self):
        result = list_tools_by_operation_type("DESTROY")
        self.assertIn("error", result)
