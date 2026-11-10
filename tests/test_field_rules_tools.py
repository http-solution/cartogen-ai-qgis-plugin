"""PLAN-023 R10-1: the registration contract of add_virtual_field, remove_virtual_field, set_field_constraint and set_default_value (offline: no QGIS needed). The checks are in
test_field_rules.py and the real-layer behaviour in test_field_rules_tools_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA

NAMES = ("add_virtual_field", "remove_virtual_field", "set_field_constraint", "set_default_value")


def schema(name):
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == name)


class TestRegistration(unittest.TestCase):
    def test_all_four_are_registered_with_their_required_arguments(self):
        required = {"add_virtual_field": ["layer_name", "name", "expression"], "remove_virtual_field": ["layer_name", "name"],
                    "set_field_constraint": ["layer_name", "field"], "set_default_value": ["layer_name", "field", "expression"]}
        for name in NAMES:
            self.assertIn(name, TOOL_REGISTRY)
            self.assertEqual(schema(name)["parameters"]["required"], required[name], name)
            self.assertTrue(TOOL_KEYWORDS[name], name)
            self.assertEqual(tool_operations.TOOL_OPERATION_TYPES[name], tool_operations.MODIFY, name)

    def test_the_descriptions_say_it_is_the_project_not_the_data_file(self):
        for name in ("add_virtual_field", "set_field_constraint", "set_default_value"):
            self.assertIn("project", schema(name)["description"], name)

    def test_without_qgis_each_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["add_virtual_field"]("a", "b", "1"), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["remove_virtual_field"]("a", "b"), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["set_field_constraint"]("a", "b", not_null=True), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["set_default_value"]("a", "b", "1"), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
