# -*- coding: utf-8 -*-
"""Tests for agent/tool_operations.py -- the READ/CREATE/MODIFY/DELETE/
PUBLISH taxonomy (point 20 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md). The completeness
check below is the point of this file: a new registered tool with no
taxonomy entry (or a stale entry for a removed tool) fails the suite
instead of silently going unclassified."""
import unittest

from cartogen_ai.core.agent.tools import TOOL_REGISTRY
from cartogen_ai.core.agent.tool_operations import (
    TOOL_OPERATION_TYPES, VALID_OPERATION_TYPES,
    get_tool_operation_type, list_tools_by_operation_type,
)


class TestCompleteness(unittest.TestCase):
    def test_every_registered_tool_is_classified(self):
        registered = set(TOOL_REGISTRY.keys())
        classified = set(TOOL_OPERATION_TYPES.keys())
        missing = registered - classified
        self.assertEqual(
            missing, set(),
            f"{len(missing)} registered tool(s) have no operation-type entry: {sorted(missing)}",
        )

    def test_no_stale_entries_for_removed_tools(self):
        registered = set(TOOL_REGISTRY.keys())
        classified = set(TOOL_OPERATION_TYPES.keys())
        stale = classified - registered
        self.assertEqual(
            stale, set(),
            f"{len(stale)} operation-type entries reference tools no longer registered: {sorted(stale)}",
        )

    def test_every_value_is_a_valid_category(self):
        invalid = {name: op for name, op in TOOL_OPERATION_TYPES.items() if op not in VALID_OPERATION_TYPES}
        self.assertEqual(invalid, {}, f"Invalid operation type(s): {invalid}")


class TestGetToolOperationType(unittest.TestCase):
    def test_known_tool(self):
        self.assertEqual(get_tool_operation_type("remove_layer"), "DELETE")
        self.assertEqual(get_tool_operation_type("get_layers"), "READ")
        self.assertEqual(get_tool_operation_type("buffer_analysis"), "CREATE")
        self.assertEqual(get_tool_operation_type("field_calculator"), "MODIFY")
        self.assertEqual(get_tool_operation_type("export_layer"), "PUBLISH")

    def test_unknown_tool_returns_none(self):
        self.assertIsNone(get_tool_operation_type("not_a_real_tool"))


class TestListToolsByOperationType(unittest.TestCase):
    def test_returns_sorted_names_for_each_category(self):
        for op in VALID_OPERATION_TYPES:
            names = list_tools_by_operation_type(op)
            self.assertEqual(names, sorted(names))
            for n in names:
                self.assertEqual(TOOL_OPERATION_TYPES[n], op)

    def test_covers_all_classified_tools_across_categories(self):
        total = sum(len(list_tools_by_operation_type(op)) for op in VALID_OPERATION_TYPES)
        self.assertEqual(total, len(TOOL_OPERATION_TYPES))

    def test_unknown_category_raises(self):
        with self.assertRaises(ValueError):
            list_tools_by_operation_type("DESTROY")

    def test_delete_category_includes_known_destructive_tools(self):
        delete_tools = set(list_tools_by_operation_type("DELETE"))
        self.assertIn("remove_layer", delete_tools)
        self.assertIn("load_project", delete_tools)
        self.assertIn("execute_pyqgis_script", delete_tools)
