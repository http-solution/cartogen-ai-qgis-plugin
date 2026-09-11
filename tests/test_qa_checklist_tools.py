# -*- coding: utf-8 -*-
"""Tests for agent/tools/qa_checklist_tools.py -- point 26 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: an automated
per-map-product QA checklist, confirmed distinct from this plugin's own
docs/RELEASE_SMOKE_TEST.md.

Pure assembly over three already-tested composed functions
(get_dataset_status, get_provenance_record, list_layout_items) -- these
tests mock those three directly at the point qa_checklist_tools imports
them, rather than re-mocking QgsProject for each one's own internal
lookup (already covered by their own test files)."""
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.tools.qa_checklist_tools import generate_map_product_qa_checklist


class TestDegradesGracefullyOutsideQgis(unittest.TestCase):
    def test_degrades(self):
        res = generate_map_product_qa_checklist("districts")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestGenerateMapProductQaChecklist(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._find_layer_by_name")
    def test_reports_missing_layer(self, mock_find):
        mock_find.return_value = None
        res = generate_map_product_qa_checklist("ghost_layer")
        self.assertIn("error", res)
        self.assertIn("ghost_layer", res["error"])

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_provenance_record")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_dataset_status")
    def test_untracked_layer_reports_honestly_without_layout(self, mock_status, mock_prov, mock_find):
        mock_find.return_value = MagicMock()
        mock_status.return_value = {"success": True, "layer_name": "districts", "status": None, "history": [], "checks": {}}
        mock_prov.return_value = {"success": False, "error": "boom"}

        res = generate_map_product_qa_checklist("districts")

        self.assertTrue(res["success"])
        self.assertFalse(res["categories"]["data"]["tracked"])
        self.assertIn("note", res["categories"]["cartography"])
        # A plain MagicMock layer's customProperty() returns a MagicMock,
        # not a real stored JSON string -- agent/sensitivity.py's own
        # get_layer_sensitivity() (real, unmocked here) correctly reads
        # that as "never tagged" (level=None), the same as a real untagged
        # layer would.
        self.assertFalse(res["categories"]["disclosure"]["tracked"])
        self.assertIsNone(res["categories"]["disclosure"]["level"])
        self.assertFalse(res["categories"]["export_provenance"]["tracked"])

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_provenance_record")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_dataset_status")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._sens")
    def test_sensitive_layer_reports_real_tag_and_warning(self, mock_sens, mock_status, mock_prov, mock_find):
        # v1.8.0 workstream 2: the disclosure section used to be a static
        # "no classification exists" stub even after set_layer_sensitivity
        # shipped -- this checklist simply never read it. Confirms it now
        # does, and surfaces the real export_warning_for() text.
        mock_find.return_value = MagicMock()
        mock_status.return_value = {"success": True, "status": None, "history": [], "checks": {}}
        mock_prov.return_value = {"success": False, "error": "boom"}
        mock_sens.get_layer_sensitivity.return_value = {"level": "SENSITIVE", "reason": "individual beneficiary GPS coordinates"}
        mock_sens.export_warning_for.return_value = "This layer is tagged 'SENSITIVE' (individual beneficiary GPS coordinates) -- confirm this export is intended."

        res = generate_map_product_qa_checklist("districts")

        disclosure = res["categories"]["disclosure"]
        self.assertTrue(disclosure["tracked"])
        self.assertEqual(disclosure["level"], "SENSITIVE")
        self.assertEqual(disclosure["reason"], "individual beneficiary GPS coordinates")
        self.assertIn("confirm this export is intended", disclosure["warning"])

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_provenance_record")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_dataset_status")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._sens")
    def test_public_tagged_layer_has_no_warning(self, mock_sens, mock_status, mock_prov, mock_find):
        mock_find.return_value = MagicMock()
        mock_status.return_value = {"success": True, "status": None, "history": [], "checks": {}}
        mock_prov.return_value = {"success": False, "error": "boom"}
        mock_sens.get_layer_sensitivity.return_value = {"level": "PUBLIC", "reason": None}
        mock_sens.export_warning_for.return_value = ""

        res = generate_map_product_qa_checklist("districts")

        disclosure = res["categories"]["disclosure"]
        self.assertTrue(disclosure["tracked"])
        self.assertEqual(disclosure["level"], "PUBLIC")
        self.assertIsNone(disclosure["warning"])

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_provenance_record")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_dataset_status")
    def test_tracked_layer_reports_status_and_checks(self, mock_status, mock_prov, mock_find):
        mock_find.return_value = MagicMock()
        mock_status.return_value = {
            "success": True, "layer_name": "districts", "status": "VALIDATED",
            "history": [{"to": "VALIDATED"}], "checks": {"geometry_validity": {"passed": True}},
        }
        mock_prov.return_value = {
            "success": True, "layer_name": "districts", "qgis_version": "4.2.2",
            "lineage": [{"tool": "buffer_analysis"}, {"tool": "field_calculator"}],
            "qa_status": {"status": "VALIDATED"},
        }

        res = generate_map_product_qa_checklist("districts")

        self.assertTrue(res["success"])
        self.assertTrue(res["categories"]["data"]["tracked"])
        self.assertEqual(res["categories"]["data"]["status"], "VALIDATED")
        self.assertIn("geometry_validity", res["categories"]["data"]["checks"])
        self.assertTrue(res["categories"]["export_provenance"]["tracked"])
        self.assertEqual(res["categories"]["export_provenance"]["tool_execution_count"], 2)
        self.assertEqual(res["categories"]["export_provenance"]["qgis_version"], "4.2.2")

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_provenance_record")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_dataset_status")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.list_layout_items")
    def test_layout_with_all_mandatory_elements(self, mock_items, mock_status, mock_prov, mock_find):
        mock_find.return_value = MagicMock()
        mock_status.return_value = {"success": True, "status": None, "history": [], "checks": {}}
        mock_prov.return_value = {"success": True, "lineage": [], "qgis_version": None}
        mock_items.return_value = {
            "success": True, "layout_name": "Layout_SITREP",
            "items": [
                {"id": "MAP_MAIN", "type": "QgsLayoutItemMap"},
                {"id": "TITLE", "type": "QgsLayoutItemLabel", "text": "Map"},
                {"id": "LEGEND", "type": "QgsLayoutItemLegend"},
                {"id": "SCALEBAR", "type": "QgsLayoutItemScaleBar"},
                {"id": "NORTH_ARROW", "type": "QgsLayoutItemPicture"},
            ],
        }

        res = generate_map_product_qa_checklist("districts", layout_name="Layout_SITREP")

        cart = res["categories"]["cartography"]
        self.assertEqual(cart["layout_name"], "Layout_SITREP")
        self.assertEqual(set(cart["mandatory_elements_present"]), {"map", "title", "legend", "scale bar", "north arrow"})
        self.assertEqual(cart["mandatory_elements_missing"], [])

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_provenance_record")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_dataset_status")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.list_layout_items")
    def test_layout_missing_mandatory_elements_are_flagged(self, mock_items, mock_status, mock_prov, mock_find):
        mock_find.return_value = MagicMock()
        mock_status.return_value = {"success": True, "status": None, "history": [], "checks": {}}
        mock_prov.return_value = {"success": True, "lineage": [], "qgis_version": None}
        mock_items.return_value = {
            "success": True, "layout_name": "Layout_partial",
            "items": [{"id": "MAP_MAIN", "type": "QgsLayoutItemMap"}],
        }

        res = generate_map_product_qa_checklist("districts", layout_name="Layout_partial")

        cart = res["categories"]["cartography"]
        self.assertEqual(cart["mandatory_elements_present"], ["map"])
        self.assertEqual(set(cart["mandatory_elements_missing"]), {"title", "legend", "scale bar", "north arrow"})

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_provenance_record")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.get_dataset_status")
    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.list_layout_items")
    def test_missing_layout_reports_error_in_that_category_only(self, mock_items, mock_status, mock_prov, mock_find):
        mock_find.return_value = MagicMock()
        mock_status.return_value = {"success": True, "status": None, "history": [], "checks": {}}
        mock_prov.return_value = {"success": True, "lineage": [], "qgis_version": None}
        mock_items.return_value = {"error": "Layout 'Layout_Ghost' not found"}

        res = generate_map_product_qa_checklist("districts", layout_name="Layout_Ghost")

        self.assertTrue(res["success"])
        self.assertIn("error", res["categories"]["cartography"])


if __name__ == "__main__":
    unittest.main()
