"""PLAN-023 R11-3: the registration contract of run_algorithm_in_place (offline: no QGIS needed). Real-layer behaviour is in test_in_place_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "run_algorithm_in_place")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_the_three_required_arguments(self):
        self.assertIn("run_algorithm_in_place", TOOL_REGISTRY)
        self.assertEqual(schema()["parameters"]["required"], ["algorithm_id", "layer_name", "selected_only"])
        self.assertIn("parameters", schema()["parameters"]["properties"])

    def test_the_description_states_what_it_does_to_the_data(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["run_algorithm_in_place"], tool_operations.MODIFY)
        text = schema()["description"]
        for word in ("DIRECTLY", "preview", "ONE undoable step", "UNSAVED", "selection is put back"):
            self.assertIn(word, text)
        self.assertIn("edit in place", TOOL_KEYWORDS["run_algorithm_in_place"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["run_algorithm_in_place"]("native:smoothgeometry", "a", True), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
