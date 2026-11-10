"""PLAN-023 R10-3: the registration contract of set_renderer (offline: no QGIS needed). The check is in test_renderer_ops.py and the real-layer behaviour in
test_renderer_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools import renderer_ops as ro
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "set_renderer")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_the_kinds_as_an_enum(self):
        self.assertIn("set_renderer", TOOL_REGISTRY)
        params = schema()["parameters"]
        self.assertEqual(params["required"], ["layer_name", "kind"])
        self.assertEqual(params["properties"]["kind"]["enum"], list(ro.KINDS))
        self.assertIn("options", params["properties"])

    def test_it_is_a_modify_tool_that_says_the_data_is_untouched_and_the_style_is_saved(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["set_renderer"], tool_operations.MODIFY)
        text = schema()["description"]
        for word in ("never touched", "style manager", "before <kind>"):
            self.assertIn(word, text)
        self.assertIn("inverted polygons", TOOL_KEYWORDS["set_renderer"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["set_renderer"]("a", "no_symbols"), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
