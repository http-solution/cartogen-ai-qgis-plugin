"""PLAN-023 R3-4: the registration contract of calculate_change_matrix (offline: no QGIS, no numpy needed). The arithmetic is in test_raster_change.py and the
real-raster behaviour in test_raster_change_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools import raster_change_tool as tool
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "calculate_change_matrix")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_two_required_rasters(self):
        self.assertIn("calculate_change_matrix", TOOL_REGISTRY)
        params = schema()["parameters"]
        self.assertEqual(params["required"], ["raster_a", "raster_b"])
        for key in ("classes", "output_name", "chart", "align_to_first", "resampling"):
            self.assertIn(key, params["properties"], key)

    def test_the_description_states_the_class_and_area_limits(self):
        text = schema()["description"]
        self.assertIn("whole numbers", text)
        self.assertIn("at most 50 classes", text)
        self.assertIn("approximate", text)
        self.assertIn("nearest neighbour", text)

    def test_it_is_classified_as_creating_layers_and_has_routing_keywords(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["calculate_change_matrix"], tool_operations.CREATE)
        self.assertIn("change matrix", TOOL_KEYWORDS["calculate_change_matrix"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["calculate_change_matrix"]("a", "b"), {"error": "QGIS not available"})

    def test_the_crs_kind_of_an_unreadable_crs_is_unknown_not_a_crash(self):
        self.assertEqual(tool.crs_area_kind(""), (None, 1.0))
        self.assertEqual(tool.crs_area_kind("not wkt at all"), (None, 1.0))


if __name__ == "__main__":
    unittest.main()
