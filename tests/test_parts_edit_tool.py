"""PLAN-023 R9-2: the registration contract of edit_parts_and_rings (offline: no QGIS needed). The maths is in test_parts_ops.py and the real-geometry behaviour in
test_parts_edit_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "edit_parts_and_rings")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_required_arguments(self):
        self.assertIn("edit_parts_and_rings", TOOL_REGISTRY)
        params = schema()["parameters"]
        self.assertEqual(params["required"], ["layer_name", "feature_id", "action"])
        self.assertEqual(sorted(params["properties"]["action"]["enum"]), ["add_part", "add_ring", "delete_part", "delete_ring", "fill_ring"])
        for key in ("geometry_wkt", "part_index", "ring_index", "x", "y"):
            self.assertIn(key, params["properties"], key)

    def test_it_changes_geometry_so_it_is_a_modify_tool_with_a_preview_note(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["edit_parts_and_rings"], tool_operations.MODIFY)
        self.assertIn("preview", schema()["description"])
        self.assertIn("undo_manual_edit", schema()["description"])
        self.assertIn("cut a hole", TOOL_KEYWORDS["edit_parts_and_rings"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["edit_parts_and_rings"]("a", 1, "delete_part", part_index=0), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
