"""export_layers_to_dxf (PLAN-006 package E2c): the checks that need no QGIS. The real write is `tests/test_export_dxf_live.py`, CI only."""
import unittest

from cartogen_ai.core.agent.tool_operations import PUBLISH, get_tool_operation_type
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools import export_tools


class TestExportLayersToDxf(unittest.TestCase):
    def test_it_is_registered_and_classified_as_a_file_write(self):
        names = {t["function"]["name"] for t in TOOLS_SCHEMA}
        self.assertIn("export_layers_to_dxf", names)
        self.assertEqual(get_tool_operation_type("export_layers_to_dxf"), PUBLISH)

    def test_the_model_cannot_pass_confirmed(self):
        schema = next(t for t in TOOLS_SCHEMA if t["function"]["name"] == "export_layers_to_dxf")["function"]["parameters"]
        self.assertNotIn("confirmed", schema["properties"])

    def test_no_layer_is_an_error_not_an_empty_file(self):
        self.assertIn("error", export_tools.export_layers_to_dxf([]))
        self.assertIn("error", export_tools.export_layers_to_dxf(["", "  "]))

    def test_too_many_layers_are_refused(self):
        result = export_tools.export_layers_to_dxf([f"l{i}" for i in range(export_tools._DXF_MAX_LAYERS + 1)])
        self.assertIn("at most", result["error"])

    def test_a_dxf_target_is_known_to_the_overwrite_check(self):
        self.assertIn(".dxf", export_tools._DRIVER_EXTENSIONS)


class TestExportLayersToSpreadsheet(unittest.TestCase):
    """PLAN-006 package E2c: the spreadsheet export shares the DXF export's refusals; the real write is test_export_spreadsheet_live."""

    def test_it_is_registered_and_classified_as_a_file_write(self):
        self.assertIn("export_layers_to_spreadsheet", {t["function"]["name"] for t in TOOLS_SCHEMA})
        self.assertEqual(get_tool_operation_type("export_layers_to_spreadsheet"), PUBLISH)

    def test_the_model_cannot_pass_confirmed(self):
        schema = next(t for t in TOOLS_SCHEMA if t["function"]["name"] == "export_layers_to_spreadsheet")["function"]["parameters"]
        self.assertNotIn("confirmed", schema["properties"])

    def test_empty_and_too_many_layers_are_refused(self):
        self.assertIn("error", export_tools.export_layers_to_spreadsheet([]))
        result = export_tools.export_layers_to_spreadsheet([f"l{i}" for i in range(export_tools._DXF_MAX_LAYERS + 1)])
        self.assertIn("spreadsheet export takes at most", result["error"])

    def test_spreadsheet_targets_are_known_to_the_overwrite_check(self):
        self.assertTrue({".xlsx", ".ods"} <= set(export_tools._DRIVER_EXTENSIONS))


if __name__ == "__main__":
    unittest.main()
