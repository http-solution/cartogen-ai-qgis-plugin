# -*- coding: utf-8 -*-
import unittest
from cartogen_ai.core.agent.tools import get_tool_registry, get_tools_schema


class TestToolRegistry(unittest.TestCase):
    def test_tool_registry_registration(self):
        registry = get_tool_registry()
        schema = get_tools_schema()

        self.assertGreater(len(registry), 0, "Tool registry should contain registered functions.")
        self.assertEqual(len(schema), len(registry), "Tools schema count should match registered tools.")

        # Check key tools presence
        self.assertIn("get_layers", registry)
        self.assertIn("buffer_analysis", registry)
        self.assertIn("calculate_ndvi", registry)
        self.assertIn("execute_pyqgis_script", registry)
        self.assertIn("create_plan", registry)
        self.assertIn("store_project_memory", registry)

    def test_tool_schema_structure(self):
        schema = get_tools_schema()
        for item in schema:
            self.assertEqual(item["type"], "function")
            fn = item["function"]
            self.assertIn("name", fn)
            self.assertIn("description", fn)
            self.assertIn("parameters", fn)


if __name__ == "__main__":
    unittest.main()
