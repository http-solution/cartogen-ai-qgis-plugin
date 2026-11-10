"""PLAN-023 R10-5: the registration contract of set_project_transform_context, define_custom_crs, set_project_measurement and set_canvas_decoration (offline: no QGIS needed). The checks are in
test_project_settings_ops.py and the real-project behaviour in test_project_settings_tools_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools import project_settings_ops as ps
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA

NAMES = ("set_project_transform_context", "define_custom_crs", "set_project_measurement", "set_canvas_decoration")


def schema(name):
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == name)


class TestRegistration(unittest.TestCase):
    def test_all_four_are_registered_with_their_required_arguments(self):
        required = {"set_project_transform_context": ["source_crs", "dest_crs"], "define_custom_crs": ["name", "definition"], "set_project_measurement": [], "set_canvas_decoration": ["kind"]}
        for name in NAMES:
            self.assertIn(name, TOOL_REGISTRY)
            self.assertEqual(schema(name)["parameters"]["required"], required[name], name)
            self.assertTrue(TOOL_KEYWORDS[name], name)
            self.assertEqual(tool_operations.TOOL_OPERATION_TYPES[name], tool_operations.MODIFY, name)
        self.assertEqual(schema("set_canvas_decoration")["parameters"]["properties"]["kind"]["enum"], list(ps.DECORATIONS))

    def test_the_descriptions_state_the_limits(self):
        self.assertIn("preview", schema("set_project_transform_context")["description"])
        self.assertIn("only an operation QGIS", schema("set_project_transform_context")["description"].replace("Only", "only"))
        self.assertIn("not added to the shared", schema("define_custom_crs")["description"])
        self.assertIn("Hand-verified only", schema("set_canvas_decoration")["description"])

    def test_no_new_tool_name_has_the_word_create_or_layer_that_the_router_would_score_everywhere(self):
        for name in NAMES:
            for word in ("create", "layer"):
                self.assertNotIn(word, name.split("_"), name)

    def test_without_qgis_each_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["set_project_transform_context"]("EPSG:4326", "EPSG:32636"), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["define_custom_crs"]("n", "+proj=utm"), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["set_project_measurement"](distance_units="meters"), {"error": "QGIS not available"})
        self.assertEqual(TOOL_REGISTRY["set_canvas_decoration"]("title", enabled=True), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
