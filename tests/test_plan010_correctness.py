"""PLAN-010 audit fixes that need no QGIS: a missing coverage target is not charted as 0%, an unreadable layer is not a clean QA result, and a
failed attempt to keep a result layer is reported. The cross-CRS obfuscation and the replacement order are in tests/test_plan010_live.py."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools.logistics_tools import persist_warning
from cartogen_ai.core.agent.tools.qa_checklist_tools import generate_map_product_qa_checklist
from cartogen_ai.core.agent.tools.reporting_tools import generate_sector_coverage_report


_ROWS = [
    {"sector": "Health", "reached": "900", "target": "1000"},
    {"sector": "Protection", "reached": "150", "target": "N/A"},
    {"sector": "WASH", "reached": "10", "target": "0"},
]


class TestCoverageChartSkipsMissingTargets(unittest.TestCase):
    def test_groups_without_a_target_are_not_plotted_as_zero(self):
        with patch("cartogen_ai.core.agent.tools.reporting_tools.generate_chart", return_value={"output_path": "x.png"}) as chart:
            res = generate_sector_coverage_report(_ROWS, "sector", "reached", target_field="target")
        labels, values = chart.call_args.args[2], chart.call_args.args[3]
        self.assertEqual((labels, values), (["Health"], [90.0]))
        self.assertEqual(sorted(res["no_target_groups"]), ["Protection", "WASH"])
        self.assertIn("not 0% coverage", res["chart_note"])
        self.assertEqual(len(res["table"]), 3)           # still in the table, sorted first, coverage None
        self.assertIsNone(res["table"][0]["coverage_percent"])

    def test_no_usable_target_anywhere_is_an_error_not_an_all_zero_chart(self):
        rows = [{"sector": "A", "reached": "5", "target": ""}]   # aggregate_data finds no usable target at all and errors before charting
        with patch("cartogen_ai.core.agent.tools.reporting_tools.generate_chart") as chart:
            res = generate_sector_coverage_report(rows, "sector", "reached", target_field="target")
        chart.assert_not_called()
        self.assertIn("error", res)


class _SingleSymbol:
    pass


class TestQaUnreadableLayerIsNotClean(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.QgsSingleSymbolRenderer", _SingleSymbol, create=True)
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._ck.features", side_effect=TimeoutError("provider timeout"))
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_provenance_record", return_value={"success": False, "error": "x"})
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_dataset_status", return_value={"success": True, "status": None, "history": [], "checks": {}})
    def test_feature_read_failure_reports_unknown(self, _status, _prov, find, _features):
        layer = MagicMock()
        layer.renderer.return_value = _SingleSymbol()
        find.return_value = layer
        note = generate_map_product_qa_checklist("districts")["categories"]["classification_sanity"]
        self.assertEqual(note["status"], "unknown")
        self.assertNotIn("No concern found", note["note"])
        self.assertIn("TimeoutError", note["note"])


class TestPersistWarning(unittest.TestCase):
    def test_a_failed_write_is_reported(self):
        self.assertIn("disk full", persist_warning({"persisted": False, "reason": "disk full"}))

    def test_expected_non_persistence_is_silent(self):
        for reason in ("not a memory layer", "the project has not been saved yet; save it to keep analysis results", "QGIS not available"):
            self.assertEqual(persist_warning({"persisted": False, "reason": reason}), "")

    def test_success_and_unknown_shapes_are_silent(self):
        self.assertEqual(persist_warning({"persisted": True, "path": "p"}), "")
        self.assertEqual(persist_warning(None), "")


if __name__ == "__main__":
    unittest.main()
