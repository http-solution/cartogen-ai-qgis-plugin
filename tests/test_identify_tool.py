"""PLAN-023 R9-5: the registration contract of identify_at_point (offline: no QGIS needed). The cap and checks are in test_identify_ops.py and the real-layer behaviour in
test_identify_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "identify_at_point")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_required_coordinates(self):
        self.assertIn("identify_at_point", TOOL_REGISTRY)
        params = schema()["parameters"]
        self.assertEqual(params["required"], ["x", "y"])
        for key in ("crs", "layers", "radius", "max_features"):
            self.assertIn(key, params["properties"], key)

    def test_it_is_read_only_and_says_it_caps_at_fifty(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["identify_at_point"], tool_operations.READ)
        text = schema()["description"]
        for word in ("50 features", "radius", "Read-only"):
            self.assertIn(word, text)
        self.assertIn("what is at this point", TOOL_KEYWORDS["identify_at_point"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["identify_at_point"](1, 2), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
