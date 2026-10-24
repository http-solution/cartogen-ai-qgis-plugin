"""PLAN-011 phase A, no QGIS needed: the missing-element rule and the wording of the export report."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools.layout_export_checks import MANDATORY_LAYOUT_ELEMENTS, export_report, missing_elements


def _layer(name):
    layer = MagicMock()
    layer.name.return_value = name
    return layer


class TestMissingElements(unittest.TestCase):
    def test_all_present_reports_nothing(self):
        self.assertEqual(missing_elements(list(MANDATORY_LAYOUT_ELEMENTS)), [])

    def test_names_what_is_absent_in_a_fixed_order(self):
        self.assertEqual(missing_elements(["MAP_MAIN", "TITLE"]), ["legend", "scale bar", "north arrow"])

    def test_empty_layout_misses_everything(self):
        self.assertEqual(len(missing_elements([])), len(MANDATORY_LAYOUT_ELEMENTS))


_ALL = list(MANDATORY_LAYOUT_ELEMENTS)


class TestExportReport(unittest.TestCase):
    def test_clean_layout_with_public_layers_says_nothing(self):
        with patch("cartogen_ai.core.agent.tools._sensitivity_notes.get_layer_sensitivity", return_value={"level": "PUBLIC"}), \
                patch("cartogen_ai.core.agent.tools.layout_export_checks.get_layer_sensitivity", return_value={"level": "PUBLIC"}):
            self.assertEqual(export_report([_layer("roads")], _ALL), {})

    def test_a_sensitive_layer_is_named_with_its_level(self):
        record = {"level": "SENSITIVE", "reason": "GBV cases"}
        with patch("cartogen_ai.core.agent.tools._sensitivity_notes.get_layer_sensitivity", return_value=record), \
                patch("cartogen_ai.core.agent.tools.layout_export_checks.get_layer_sensitivity", return_value=record):
            report = export_report([_layer("incidents")], _ALL)
        self.assertEqual(report["protected_layers"], [{"layer": "incidents", "level": "SENSITIVE"}])
        self.assertIn("'incidents' is tagged SENSITIVE (GBV cases)", report["export_warnings"][0])
        self.assertNotIn("missing_elements", report)

    def test_missing_elements_are_a_warning_and_the_file_is_not_blocked(self):
        with patch("cartogen_ai.core.agent.tools._sensitivity_notes.get_layer_sensitivity", return_value={"level": "PUBLIC"}), \
                patch("cartogen_ai.core.agent.tools.layout_export_checks.get_layer_sensitivity", return_value={"level": "PUBLIC"}):
            report = export_report([_layer("roads")], ["MAP_MAIN"])
        self.assertEqual(report["missing_elements"], ["title", "legend", "scale bar", "north arrow"])
        self.assertIn("The file was written as it is", report["export_warnings"][-1])

    def test_no_layers_and_all_elements_is_empty(self):
        self.assertEqual(export_report([], _ALL), {})


if __name__ == "__main__":
    unittest.main()
