"""PLAN-023 R10-4: the registration contract of get_raster_value, raster_attribute_table and build_pyramids (offline: no QGIS needed). The maths is in test_pyramid_ops.py and the
real-raster behaviour in test_raster_inspect_tools_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools import pyramid_ops as po
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA

NAMES = ("get_raster_value", "raster_attribute_table", "build_pyramids")


def schema(name):
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == name)


class TestRegistration(unittest.TestCase):
    def test_all_three_are_registered_with_their_required_arguments(self):
        required = {"get_raster_value": ["layer_name", "x", "y"], "raster_attribute_table": ["layer_name"], "build_pyramids": ["layer_name"]}
        for name in NAMES:
            self.assertIn(name, TOOL_REGISTRY)
            self.assertEqual(schema(name)["parameters"]["required"], required[name], name)
            self.assertTrue(TOOL_KEYWORDS[name], name)
        self.assertEqual(schema("build_pyramids")["parameters"]["properties"]["method"]["enum"], list(po.METHODS))

    def test_the_two_readers_are_read_tools_and_the_pyramid_builder_creates_a_sidecar_file(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["get_raster_value"], tool_operations.READ)
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["raster_attribute_table"], tool_operations.READ)
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["build_pyramids"], tool_operations.CREATE)
        text = schema("build_pyramids")["description"]
        for word in ("NEXT TO the raster", "never rewritten", "preview"):
            self.assertIn(word, text)

    def test_without_qgis_each_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["get_raster_value"]("a", 1, 2), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["raster_attribute_table"]("a"), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["build_pyramids"]("a"), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
