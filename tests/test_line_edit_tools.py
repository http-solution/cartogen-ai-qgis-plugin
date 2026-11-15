"""PLAN-023 R9-3: the registration contract of reshape_geometry, reverse_line, trim_extend_lines and offset_curve (offline: no QGIS needed). The line maths is in
test_line_ops.py and the real-geometry behaviour in test_line_edit_tools_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA

NAMES = ("reshape_geometry", "reverse_line", "trim_extend_lines", "offset_curve")


def schema(name):
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == name)


class TestRegistration(unittest.TestCase):
    def test_all_four_are_registered_with_their_required_arguments(self):
        required = {"reshape_geometry": ["layer_name", "feature_id", "line_wkt"], "reverse_line": ["layer_name"],
                    "trim_extend_lines": ["layer_name", "tolerance"], "offset_curve": ["layer_name", "distance"]}
        for name in NAMES:
            self.assertIn(name, TOOL_REGISTRY)
            self.assertEqual(schema(name)["parameters"]["required"], required[name], name)
            self.assertTrue(TOOL_KEYWORDS[name], name)

    def test_the_three_in_place_edits_are_modify_tools_with_a_preview_and_offset_creates_a_layer(self):
        for name in ("reshape_geometry", "reverse_line", "trim_extend_lines"):
            self.assertEqual(tool_operations.TOOL_OPERATION_TYPES[name], tool_operations.MODIFY, name)
            self.assertIn("preview", schema(name)["description"], name)
            self.assertIn("undo_manual_edit", schema(name)["description"], name)
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["offset_curve"], tool_operations.CREATE)
        self.assertIn("NEW layer", schema("offset_curve")["description"])

    def test_without_qgis_each_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["reshape_geometry"]("a", 1, "LINESTRING(0 0,1 1)"), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["reverse_line"]("a"), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["trim_extend_lines"]("a", 1), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["offset_curve"]("a", 1), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
