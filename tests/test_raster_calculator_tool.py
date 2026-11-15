import unittest

from cartogen_ai.core.agent.tools import raster_calculator_tool as tool
from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY, TOOLS_SCHEMA


class TestRegistration(unittest.TestCase):
    def test_registered_with_a_required_expression(self):
        self.assertIn("raster_calculator", TOOL_REGISTRY)
        schema = next(t for t in TOOLS_SCHEMA if t["function"]["name"] == "raster_calculator")["function"]["parameters"]
        self.assertEqual(schema["required"], ["expression"])

    def test_degrades_cleanly_without_qgis(self):
        if tool.QGIS_AVAILABLE:
            self.skipTest("QGIS present")
        self.assertEqual(tool.raster_calculator('"a@1"'), {"error": "QGIS not available"})


if __name__ == "__main__":
    unittest.main()
