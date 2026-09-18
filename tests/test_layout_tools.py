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
    export_layout_atlas, _fit_text_to_box, _nice_interval, _format_scale_denominator,
)


class TestFitTextToBox(unittest.TestCase):
    """BUG-2026-09-11-1: QgsLayoutItemLabel doesn't clip overflowing content
    to its own box -- _fit_text_to_box is the guard against that, so these
    are pure-Python and need no QGIS install."""

    def test_short_text_returned_unchanged(self):
        text = "Short summary."
        self.assertEqual(_fit_text_to_box(text, box_w_mm=180, box_h_mm=6), text)

    def test_long_text_is_truncated_with_ellipsis(self):
        text = "word " * 200  # far exceeds any realistic box budget
        result = _fit_text_to_box(text, box_w_mm=180, box_h_mm=6)
        self.assertLess(len(result), len(text))
        self.assertTrue(result.endswith("…"))

    def test_truncation_breaks_on_a_whole_word_boundary(self):
        text = "word " * 200
        result = _fit_text_to_box(text, box_w_mm=180, box_h_mm=6)
        # Never cuts mid-word -- the char before the ellipsis is a full
        # "word" token, not a partial fragment like "wor".
        self.assertTrue(result[:-1].strip().endswith("word") or result == "…")

    def test_larger_box_allows_more_text_before_truncating(self):
        text = "word " * 200
        small = _fit_text_to_box(text, box_w_mm=180, box_h_mm=6)
        large = _fit_text_to_box(text, box_w_mm=180, box_h_mm=30)
        self.assertGreater(len(large), len(small))

    def test_degenerate_zero_height_box_still_returns_at_least_one_line_budget(self):
        # max(1, ...) floor -- a box_h_mm of 0 (or negative, from a bad
        # caller) must not crash or return an empty/zero-char result.
        result = _fit_text_to_box("A short line.", box_w_mm=180, box_h_mm=0)
        self.assertEqual(result, "A short line.")

    def test_very_long_single_word_has_no_space_to_break_on(self):
        # rsplit(" ", 1) on a string with no space returns the whole string
        # unchanged -- confirm this degrades to "truncate at the char
        # boundary anyway" rather than raising.
        text = "a" * 5000
        result = _fit_text_to_box(text, box_w_mm=180, box_h_mm=6)
        self.assertTrue(result.endswith("…"))
        self.assertLess(len(result), len(text))

    def test_landscape_dimensions_also_truncate_an_extreme_body_text(self):
        # _fit_text_to_box's call site in create_print_layout sits in the
        # shared code path after the portrait/landscape if/else closes, not
        # inside the portrait-only branch -- so it already protects
        # landscape's own (col_w=95, body_h=78) box too. Confirmed live
        # against real QGIS 4.2.2 with a 2774-char extreme body_text
        # (2026-09-11): the exported PNG showed a cleanly truncated
        # paragraph and a fully legible, unobstructed disclaimer footer.
        # This test locks that in against a future regression -- e.g. an
        # edit that moves the call site back inside the portrait branch.
        text = "word " * 400  # far exceeds landscape's real body_h=78 budget
        result = _fit_text_to_box(text, box_w_mm=95, box_h_mm=78)
        self.assertLess(len(result), len(text))
        self.assertTrue(result.endswith("…"))


class TestNiceInterval(unittest.TestCase):
    """Phase 3 (2026-09-19), OCHA-standard coordinate graticule: _nice_interval rounds a raw
    target spacing up to the nearest 1/2/5 x 10^n, the same 'nice round number' convention
    QGIS's own scale bar uses -- pure Python, no QGIS needed. Live-verified (real QGIS 4.2.2,
    python-qgis.bat, real QgsLayoutExporter.exportToImage PNG visually inspected) that the
    grid this feeds actually renders with visible tick annotations on all 4 borders, in both
    landscape and portrait, with no overlap with the map/legend/scalebar around it."""

    def test_rounds_up_to_nearest_nice_value(self):
        self.assertEqual(_nice_interval(0.3), 0.5)
        self.assertEqual(_nice_interval(3), 5)
        self.assertEqual(_nice_interval(37), 50)
        self.assertEqual(_nice_interval(150), 200)

    def test_exact_nice_value_returned_unchanged(self):
        self.assertEqual(_nice_interval(5), 5)
        self.assertEqual(_nice_interval(100), 100)

    def test_zero_or_negative_falls_back_to_1(self):
        self.assertEqual(_nice_interval(0), 1.0)
        self.assertEqual(_nice_interval(-5), 1.0)


class TestFormatScaleDenominator(unittest.TestCase):
    """Phase 3 (2026-09-19): the OCHA-standard textual representative-fraction scale
    ('1:N') alongside the existing graphical scale bar, which alone never stated an exact
    numeric ratio."""

    def test_formats_with_thousands_separators(self):
        self.assertEqual(_format_scale_denominator(1234567), "1:1,234,567")

    def test_rounds_to_nearest_integer(self):
        self.assertEqual(_format_scale_denominator(50000.6), "1:50,001")

    def test_small_scale(self):
        self.assertEqual(_format_scale_denominator(500), "1:500")


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

    def test_degrades_gracefully_with_include_inset_map(self):
        res = create_print_layout("Test Layout", include_inset_map=False)
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


class TestExportLayoutAtlas(unittest.TestCase):
    """The full-atlas half of point 15 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md
    -- one output file per coverage-layer feature via QgsLayoutAtlas, live-verified against real
    QGIS 4.2.2 (real PDF/PNG files written, filename sanitization, MAP_MAIN-less layouts
    correctly rejected). These are the mocked degrade/routing tests; see the live-verification
    note in the point 15 review-doc entry for the real-QGIS evidence."""

    def test_degrades_gracefully_outside_qgis(self):
        res = export_layout_atlas("Layout_SITREP", "districts", "C:/tmp/atlas", "pcode")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_reports_missing_layout(self, mock_project):
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = []
        res = export_layout_atlas("Layout_Ghost", "districts", "C:/tmp/atlas", "pcode")
        self.assertIn("error", res)
        self.assertIn("Layout_Ghost", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_reports_missing_coverage_layer(self, mock_project, mock_find_layer):
        layout = MagicMock()
        layout.name.return_value = "Layout_SITREP"
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]
        mock_find_layer.return_value = None

        res = export_layout_atlas("Layout_SITREP", "ghost_layer", "C:/tmp/atlas", "pcode")

        self.assertIn("error", res)
        self.assertIn("ghost_layer", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_reports_missing_field(self, mock_project, mock_find_layer):
        layout = MagicMock()
        layout.name.return_value = "Layout_SITREP"
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]

        layer = MagicMock()
        field_a, field_b = MagicMock(), MagicMock()
        field_a.name.return_value = "district_pcode"
        field_b.name.return_value = "district_name"
        fields_mock = MagicMock()
        fields_mock.indexOf.return_value = -1
        fields_mock.__iter__.return_value = iter([field_a, field_b])
        layer.fields.return_value = fields_mock
        mock_find_layer.return_value = layer

        res = export_layout_atlas("Layout_SITREP", "districts", "C:/tmp/atlas", "ghost_field")

        self.assertIn("error", res)
        self.assertIn("ghost_field", res["error"])
        self.assertIn("district_pcode", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_reports_no_map_main_item(self, mock_project, mock_find_layer):
        # A hand-built layout (not from create_print_layout) has no MAP_MAIN --
        # itemById returns None, matching real QGIS behavior for an unknown id.
        layout = MagicMock()
        layout.name.return_value = "HandBuilt"
        layout.itemById.return_value = None
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]

        layer = MagicMock()
        layer.fields.return_value.indexOf.return_value = 0
        mock_find_layer.return_value = layer

        res = export_layout_atlas("HandBuilt", "districts", "C:/tmp/atlas", "pcode")

        self.assertIn("error", res)
        self.assertIn("MAP_MAIN", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_rejects_unsupported_output_format(self, mock_project, mock_find_layer):
        layout = MagicMock()
        layout.name.return_value = "Layout_SITREP"
        layout.itemById.return_value = MagicMock(spec=["setAtlasDriven"])
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]

        layer = MagicMock()
        layer.fields.return_value.indexOf.return_value = 0
        mock_find_layer.return_value = layer

        res = export_layout_atlas("Layout_SITREP", "districts", "C:/tmp/atlas", "pcode", output_format="tiff")

        self.assertIn("error", res)
        self.assertIn("tiff", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.os.makedirs")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutExporter", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_reports_invalid_filename_expression(self, mock_project, mock_find_layer, mock_exporter_cls, mock_makedirs):
        atlas = MagicMock()
        atlas.setFilenameExpression.return_value = (False, "parser error")
        layout = MagicMock()
        layout.name.return_value = "Layout_SITREP"
        layout.atlas.return_value = atlas
        layout.itemById.return_value = MagicMock(spec=["setAtlasDriven"])
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]

        layer = MagicMock()
        layer.fields.return_value.indexOf.return_value = 0
        mock_find_layer.return_value = layer

        res = export_layout_atlas("Layout_SITREP", "districts", "C:/tmp/atlas", "pcode")

        self.assertIn("error", res)
        self.assertIn("parser error", res["error"])

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.os.makedirs")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutExporter", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_reports_empty_coverage_layer(self, mock_project, mock_find_layer, mock_exporter_cls, mock_makedirs):
        atlas = MagicMock()
        atlas.setFilenameExpression.return_value = (True, "")
        atlas.first.return_value = False
        atlas.count.return_value = 0
        layout = MagicMock()
        layout.name.return_value = "Layout_SITREP"
        layout.atlas.return_value = atlas
        layout.itemById.return_value = MagicMock(spec=["setAtlasDriven"])
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]

        layer = MagicMock()
        layer.fields.return_value.indexOf.return_value = 0
        mock_find_layer.return_value = layer

        res = export_layout_atlas("Layout_SITREP", "districts", "C:/tmp/atlas", "pcode")

        self.assertIn("error", res)
        self.assertIn("no features", res["error"])
        atlas.endRender.assert_called_once()

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.os.makedirs")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutExporter", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_successful_pdf_export_iterates_all_features_and_sanitizes_filenames(
        self, mock_project, mock_find_layer, mock_exporter_cls, mock_makedirs,
    ):
        atlas = MagicMock()
        atlas.setFilenameExpression.return_value = (True, "")
        # Two features, then done. currentFilename() has a real "/" that must
        # not become a raw path separator in the output file path.
        atlas.first.return_value = True
        atlas.next.side_effect = [True, False]
        atlas.currentFilename.side_effect = ["D001", "Beta/Bravo", "unused"]

        map_item = MagicMock(spec=["setAtlasDriven"])
        layout = MagicMock()
        layout.name.return_value = "Layout_SITREP"
        layout.atlas.return_value = atlas
        layout.itemById.return_value = map_item
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]

        layer = MagicMock()
        layer.fields.return_value.indexOf.return_value = 0
        mock_find_layer.return_value = layer

        mock_exporter_instance = mock_exporter_cls.return_value
        mock_exporter_instance.exportToPdf.return_value = mock_exporter_cls.Success

        res = export_layout_atlas("Layout_SITREP", "districts", "C:/tmp/atlas", "pcode", output_format="pdf")

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["feature_count"], 2)
        self.assertEqual(len(res["output_files"]), 2)
        self.assertIn("D001.pdf", res["output_files"][0])
        # "/" sanitized to "_", not left as a path separator mid-filename.
        self.assertIn("Beta_Bravo.pdf", res["output_files"][1])
        self.assertNotIn("Beta/Bravo", res["output_files"][1])
        atlas.setCoverageLayer.assert_called_once_with(layer)
        atlas.setEnabled.assert_called_once_with(True)
        map_item.setAtlasDriven.assert_called_once_with(True)
        atlas.beginRender.assert_called_once()
        atlas.endRender.assert_called_once()
        self.assertEqual(mock_exporter_instance.exportToPdf.call_count, 2)

    @patch("cartogen_ai.core.agent.tools.layout_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.layout_tools.os.makedirs")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsLayoutExporter", create=True)
    @patch("cartogen_ai.core.agent.tools.layout_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.layout_tools.QgsProject", create=True)
    def test_export_failure_mid_loop_still_ends_render_and_reports_error(
        self, mock_project, mock_find_layer, mock_exporter_cls, mock_makedirs,
    ):
        atlas = MagicMock()
        atlas.setFilenameExpression.return_value = (True, "")
        atlas.first.return_value = True
        atlas.currentFilename.return_value = "D001"

        map_item = MagicMock(spec=["setAtlasDriven"])
        layout = MagicMock()
        layout.name.return_value = "Layout_SITREP"
        layout.atlas.return_value = atlas
        layout.itemById.return_value = map_item
        mock_project.instance.return_value.layoutManager.return_value.printLayouts.return_value = [layout]

        layer = MagicMock()
        layer.fields.return_value.indexOf.return_value = 0
        mock_find_layer.return_value = layer

        mock_exporter_instance = mock_exporter_cls.return_value
        # Distinct sentinel from Success so the failure branch is unambiguous.
        mock_exporter_instance.exportToPdf.return_value = "SomeFailureCode"

        res = export_layout_atlas("Layout_SITREP", "districts", "C:/tmp/atlas", "pcode", output_format="pdf")

        self.assertIn("error", res)
        self.assertIn("D001", res["error"])
        atlas.endRender.assert_called_once()


if __name__ == "__main__":
    unittest.main()
