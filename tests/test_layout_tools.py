# -*- coding: utf-8 -*-
"""Tests for agent/tools/layout_tools.py's create_print_layout -- extended to
support PNG/JPEG image export (dpi-controlled) alongside the existing PDF
export, plus an optional body_text summary panel, closing the gap that was
forcing hand-written QgsPrintLayout code via execute_pyqgis_script for real
sitrep exports (and the real API mistakes that came with it, e.g.
QFont.Italic/QgsLegendStyle.Item, which aren't real PyQGIS/Qt attributes).

Also covers the zoom_to_layer parameter -- added after a live export came
back cropped, missing large parts of Yemen: create_print_layout captures
whatever extent the canvas currently shows, and nothing previously
guaranteed that extent was the full area of interest rather than a leftover
zoomed-in view from an earlier tool call.

No live-QGIS object-graph test for the main composition -- create_print_layout
constructs a long chain of QgsPrintLayout/QgsLayoutItem* objects with no
validation before the first QGIS object touch, matching the same "too deep to
mock meaningfully, degrade-test only" convention already used throughout this
suite for similarly deep QGIS-object-graph functions (calculate_service_area,
travel_time_matrix, _write_scores_to_layer). The zoom_to_layer extent-routing
logic sits before that heavy construction, so it's tested directly."""
import unittest
from unittest.mock import MagicMock, patch
from cartogen_ai.core.agent.tools.layout_tools import (
    create_print_layout, list_layouts, list_layout_items, update_layout_item_text,
)


class TestCreatePrintLayoutDegradesOutsideQgis(unittest.TestCase):
    def test_degrades_gracefully(self):
        res = create_print_layout("Test Layout")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_degrades_gracefully_with_new_params(self):
        res = create_print_layout(
            "Test Layout", output_path="C:/tmp/out.png", dpi=150, body_text="Summary text",
        )
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_degrades_gracefully_with_zoom_to_layer(self):
        res = create_print_layout("Test Layout", zoom_to_layer="YEM_ADM1_boundary_hdx")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_list_layouts_degrades_gracefully(self):
        res = list_layouts()
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestListLayouts(unittest.TestCase):
    """Point 21 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: the agent had no
    way to check what layouts already exist in the project before create_print_layout runs."""

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_lists_existing_layout_names(self, mock_project):
        layout_a = MagicMock()
        layout_a.name.return_value = "Layout_SITREP"
        layout_b = MagicMock()
        layout_b.name.return_value = "Layout_Access"
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout_a, layout_b]

        res = list_layouts()

        self.assertEqual(res["layouts"], ["Layout_SITREP", "Layout_Access"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_empty_project_returns_empty_list(self, mock_project):
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = []
        res = list_layouts()
        self.assertEqual(res["layouts"], [])


class TestListLayoutItems(unittest.TestCase):
    """Point 15 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: create_print_layout
    now gives every item a stable id; this tool surfaces them."""

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_reports_missing_layout(self, mock_project):
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = []
        res = list_layout_items("Layout_Ghost")
        self.assertIn("error", res)
        self.assertIn("Layout_Ghost", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_lists_only_items_with_a_real_id_and_includes_text(self, mock_project):
        title_item = MagicMock(spec=["id", "text"])
        title_item.id.return_value = "TITLE"
        title_item.text.return_value = "Health Facilities Situation Map"

        map_item = MagicMock(spec=["id"])
        map_item.id.return_value = "MAP_MAIN"

        # Internal plumbing QGIS itself adds: a QgsLayoutItemPage with id() == "".
        page_item = MagicMock(spec=["id"])
        page_item.id.return_value = ""

        layout = MagicMock()
        layout.name.return_value = "Layout_SITREP"
        layout.items.return_value = [title_item, map_item, page_item]
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]

        res = list_layout_items("Layout_SITREP")

        self.assertTrue(res["success"])
        ids = {item["id"] for item in res["items"]}
        self.assertEqual(ids, {"TITLE", "MAP_MAIN"})
        title_entry = next(i for i in res["items"] if i["id"] == "TITLE")
        self.assertEqual(title_entry["text"], "Health Facilities Situation Map")
        map_entry = next(i for i in res["items"] if i["id"] == "MAP_MAIN")
        self.assertNotIn("text", map_entry)

    def test_degrades_gracefully_outside_qgis(self):
        res = list_layout_items("Layout_SITREP")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestUpdateLayoutItemText(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_reports_missing_layout(self, mock_project):
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = []
        res = update_layout_item_text("Layout_Ghost", "TITLE", "New title")
        self.assertIn("error", res)
        self.assertIn("Layout_Ghost", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_reports_missing_item_id(self, mock_project):
        layout = MagicMock()
        layout.itemById.return_value = None
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]
        layout.name.return_value = "Layout_SITREP"

        res = update_layout_item_text("Layout_SITREP", "GHOST_ID", "text")

        self.assertIn("error", res)
        self.assertIn("GHOST_ID", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_rejects_item_with_no_settable_text(self, mock_project):
        item = MagicMock(spec=["id"])  # no setText -- e.g. MAP_MAIN
        layout = MagicMock()
        layout.name.return_value = "Layout_SITREP"
        layout.itemById.return_value = item
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]

        res = update_layout_item_text("Layout_SITREP", "MAP_MAIN", "text")

        self.assertIn("error", res)
        self.assertIn("settable text", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_updates_text_and_refreshes(self, mock_project):
        item = MagicMock()
        layout = MagicMock()
        layout.name.return_value = "Layout_SITREP"
        layout.itemById.return_value = item
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]

        res = update_layout_item_text("Layout_SITREP", "TITLE", "Updated Title")

        self.assertTrue(res["success"])
        item.setText.assert_called_once_with("Updated Title")
        item.refresh.assert_called_once()

    def test_degrades_gracefully_outside_qgis(self):
        res = update_layout_item_text("Layout_SITREP", "TITLE", "text")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestZoomToLayerParam(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools._find_layer_by_name")
    def test_missing_layer_returns_error_before_touching_project(self, mock_find):
        mock_find.return_value = None

        res = create_print_layout("Test Layout", zoom_to_layer="NotALayer")

        self.assertIn("error", res)
        self.assertIn("NotALayer", res["error"])
        self.assertIn("not found", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsPageSize", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsUnitTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutPoint", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutSize", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsApplication", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutExporter", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutItemPicture", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutItemLabel", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutItemScaleBar", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutItemLegend", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutItemMap", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsPrintLayout", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools._extent_to_canvas_crs")
    @patch("cartogen_ai.core.agent.tools.layout_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.iface", create=True)
    def test_found_layer_routes_extent_through_crs_transform(
        self, mock_iface, mock_project, mock_find, mock_transform_fn,
        mock_layout_cls, mock_map_item_cls, mock_legend_cls, mock_scalebar_cls,
        mock_label_cls, mock_picture_cls, mock_exporter_cls, mock_app,
        mock_layout_size_cls, mock_layout_point_cls, mock_unit_types, mock_page_size,
    ):
        fake_layer = MagicMock()
        fake_extent = MagicMock()
        fake_layer.extent.return_value = fake_extent
        mock_find.return_value = fake_layer

        mock_canvas = MagicMock()
        mock_iface.mapCanvas.return_value = mock_canvas
        transformed_extent = MagicMock()
        mock_transform_fn.return_value = transformed_extent

        mock_app.svgPaths.return_value = []  # skip north-arrow file lookup
        # layout.pageCollection().pages()[0] needs a real subscriptable list --
        # a bare MagicMock doesn't support __getitem__.
        mock_layout_cls.return_value.pageCollection.return_value.pages.return_value = [MagicMock()]
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = []

        res = create_print_layout("Test Layout", zoom_to_layer="YEM_ADM1_boundary_hdx")

        self.assertTrue(res.get("success"), res)
        mock_transform_fn.assert_called_once_with(mock_canvas, fake_extent, fake_layer.crs.return_value)
        mock_canvas.setExtent.assert_called_once_with(transformed_extent)
        mock_canvas.refresh.assert_called_once()
        map_item_instance = mock_map_item_cls.return_value
        map_item_instance.setExtent.assert_called_once_with(transformed_extent)


if __name__ == "__main__":
    unittest.main()
