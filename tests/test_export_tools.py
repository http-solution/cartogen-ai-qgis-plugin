# -*- coding: utf-8 -*-
"""Tests for the provenance-footer addition to generate_report/generate_spatial_report
(agent/tools/export_tools.py) -- Tier-2 item #7 from the humanitarian feature review:
surface what agent/lineage.py already tracks per layer (tool, params, sources,
timestamp) in generated reports, instead of leaving it invisible to a report's
actual audience (often not QGIS users, e.g. a fund-allocation committee)."""
import os
import unittest
from cartogen_ai.core.agent.tools.export_tools import (
    generate_report, generate_spatial_report, _layer_provenance_entries, _format_lineage_entry,
    generate_html_dashboard, _build_dashboard_html, _iter_geojson_coords, _humanize_field_name,
)


def _skip_if_missing(test_case, module_name):
    try:
        __import__(module_name)
    except ImportError:
        test_case.skipTest(f"{module_name} not installed")


class TestLayerProvenanceEntries(unittest.TestCase):
    """Outside QGIS, _find_layer_by_name always returns None, so every named
    layer resolves to a deterministic 'not found' entry -- fully testable
    without a live QGIS session."""

    def test_no_source_layers_returns_empty_list(self):
        self.assertEqual(_layer_provenance_entries(None), [])
        self.assertEqual(_layer_provenance_entries([]), [])

    def test_unfound_layers_reported_not_silently_dropped(self):
        entries = _layer_provenance_entries(["districts", "health_facilities"])
        self.assertEqual(len(entries), 2)
        for entry, name in zip(entries, ["districts", "health_facilities"]):
            self.assertEqual(entry["layer"], name)
            self.assertFalse(entry["found"])
            self.assertEqual(entry["history"], [])


class TestFormatLineageEntry(unittest.TestCase):
    """Pure string formatting, no QGIS needed."""

    def test_formats_tool_timestamp_sources_and_params(self):
        h = {
            "tool": "calculate_severity_index",
            "timestamp": "2026-08-14 10:00:00",
            "sources": ["indicators"],
            "params": {"unit_name_field": "district"},
        }
        text = _format_lineage_entry(h)
        self.assertIn("calculate_severity_index", text)
        self.assertIn("2026-08-14 10:00:00", text)
        self.assertIn("from: indicators", text)
        self.assertIn("unit_name_field=district", text)

    def test_handles_missing_sources_and_params(self):
        h = {"tool": "fetch_geoboundaries", "timestamp": "2026-08-14 10:00:00"}
        text = _format_lineage_entry(h)
        self.assertEqual(text, "2026-08-14 10:00:00 -- fetch_geoboundaries")

    def test_handles_missing_keys_entirely(self):
        text = _format_lineage_entry({})
        self.assertEqual(text, "unknown time -- unknown tool")


class TestGenerateSpatialReportProvenance(unittest.TestCase):
    """generate_spatial_report needs no QGIS/optional deps at all, so its
    provenance behavior is fully testable here, including outside QGIS."""

    def test_no_source_layers_leaves_report_unchanged(self):
        res = generate_spatial_report("Flood Impact", "1200 households affected.")
        self.assertTrue(res["message"])
        self.assertNotIn("Provenance", res["report"])
        self.assertIn("Flood Impact", res["report"])

    def test_source_layers_append_provenance_section_reporting_not_found(self):
        res = generate_spatial_report("Flood Impact", "1200 households affected.", source_layers=["flood_extent"])
        self.assertIn("Data Sources & Provenance", res["report"])
        self.assertIn("flood_extent", res["report"])
        self.assertIn("layer not found in the current project", res["report"])


class TestGenerateReportValidation(unittest.TestCase):
    def setUp(self):
        _skip_if_missing(self, "docx")

    def test_generates_docx_without_source_layers(self):
        res = generate_report("Test Report", "Some content.")
        try:
            self.assertTrue(res.get("success"), res)
            self.assertTrue(os.path.exists(res["path"]))
        finally:
            if res.get("path") and os.path.exists(res["path"]):
                os.remove(res["path"])

    def test_generates_docx_with_provenance_section_for_unfound_layer(self):
        from docx import Document
        res = generate_report("Test Report With Sources", "Some content.", source_layers=["nonexistent_layer"])
        try:
            self.assertTrue(res.get("success"), res)
            doc = Document(res["path"])
            full_text = "\n".join(p.text for p in doc.paragraphs)
            self.assertIn("Data Sources & Provenance", full_text)
            self.assertIn("nonexistent_layer", full_text)
            self.assertIn("Layer not found in the current project", full_text)
        finally:
            if res.get("path") and os.path.exists(res["path"]):
                os.remove(res["path"])


class TestHumanizeFieldName(unittest.TestCase):
    """Pure string transformation, no QGIS/folium needed -- the mechanical
    fallback label used by _build_dashboard_html for any popup field without
    an explicit popup_labels entry."""

    def test_snake_case_becomes_title_case_with_spaces(self):
        self.assertEqual(_humanize_field_name("food_insec_pct"), "Food Insec Pct")
        self.assertEqual(_humanize_field_name("adm1_name"), "Adm1 Name")
        self.assertEqual(_humanize_field_name("severity_score"), "Severity Score")

    def test_kebab_case_also_handled(self):
        self.assertEqual(_humanize_field_name("wash-depriv-pct"), "Wash Depriv Pct")

    def test_no_underscores_returns_capitalized_as_is(self):
        self.assertEqual(_humanize_field_name("district"), "District")

    def test_empty_string_does_not_crash(self):
        self.assertEqual(_humanize_field_name(""), "")


class TestIterGeojsonCoords(unittest.TestCase):
    """Pure recursion over GeoJSON coordinate nesting, no QGIS needed."""

    def test_point(self):
        self.assertEqual(list(_iter_geojson_coords({"type": "Point", "coordinates": [10, 20]})), [(10, 20)])

    def test_polygon(self):
        poly = {"type": "Polygon", "coordinates": [[[10, 20], [11, 20], [11, 21], [10, 21], [10, 20]]]}
        self.assertEqual(len(list(_iter_geojson_coords(poly))), 5)

    def test_multipoint(self):
        mp = {"type": "MultiPoint", "coordinates": [[1, 2], [3, 4]]}
        self.assertEqual(list(_iter_geojson_coords(mp)), [(1, 2), (3, 4)])

    def test_geometry_collection_recurses_into_members(self):
        poly = {"type": "Polygon", "coordinates": [[[10, 20], [11, 20], [11, 21], [10, 21], [10, 20]]]}
        mp = {"type": "MultiPoint", "coordinates": [[1, 2], [3, 4]]}
        gc = {"type": "GeometryCollection", "geometries": [poly, mp]}
        self.assertEqual(len(list(_iter_geojson_coords(gc))), 7)

    def test_none_geometry_yields_nothing(self):
        self.assertEqual(list(_iter_geojson_coords(None)), [])
        self.assertEqual(list(_iter_geojson_coords({})), [])


def _fake_severity_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"district": "Aden", "severity_score": 0.9, "severity_class": 5},
             "geometry": {"type": "Polygon", "coordinates": [[[45.0, 12.7], [45.2, 12.7], [45.2, 12.9], [45.0, 12.9], [45.0, 12.7]]]}},
            {"type": "Feature", "properties": {"district": "Taiz", "severity_score": 0.2, "severity_class": 1},
             "geometry": {"type": "Polygon", "coordinates": [[[44.0, 13.5], [44.2, 13.5], [44.2, 13.7], [44.0, 13.7], [44.0, 13.5]]]}},
        ],
    }


class TestBuildDashboardHtml(unittest.TestCase):
    """Pure HTML-generation core -- no QGIS needed, only folium/branca.
    Verified live in a real browser during scoping (real OSM tiles,
    choropleth coloring, layer toggles, and popups all confirmed working
    end-to-end through this exact function); these tests check the
    generation logic itself stays correct."""

    def setUp(self):
        _skip_if_missing(self, "folium")

    def test_rejects_empty_layers(self):
        res = _build_dashboard_html([])
        self.assertIn("error", res)

    def test_popup_labels_show_human_readable_text_not_raw_field_names(self):
        layer = {
            "name": "Severity Index",
            "geojson": _fake_severity_geojson(),
            "popup_fields": ["district", "severity_score"],
            "popup_labels": {"district": "Governorate", "severity_score": "Composite Severity Score"},
        }
        res = _build_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("Governorate", res["html"])
        self.assertIn("Composite Severity Score", res["html"])

    def test_unlabeled_popup_field_falls_back_to_humanized_name(self):
        layer = {
            "name": "Severity Index",
            "geojson": _fake_severity_geojson(),
            "popup_fields": ["district", "severity_score"],
            "popup_labels": {"district": "Governorate"},  # severity_score deliberately left unlabeled
        }
        res = _build_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("Governorate", res["html"])
        self.assertIn("Severity Score", res["html"])  # humanized fallback, not raw "severity_score"

    def test_no_popup_labels_at_all_still_uses_humanized_fallback_everywhere(self):
        layer = {"name": "Severity Index", "geojson": _fake_severity_geojson(), "popup_fields": ["district", "severity_score"]}
        res = _build_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("Severity Score", res["html"])

    def test_produces_html_with_layer_names_and_popup_fields(self):
        layer = {"name": "Severity Index", "geojson": _fake_severity_geojson(), "popup_fields": ["district", "severity_score"]}
        res = _build_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("Severity Index", res["html"])
        self.assertIn("district", res["html"])
        self.assertEqual(res["warnings"], [])

    def test_color_field_adds_a_colormap_legend(self):
        layer = {"name": "Severity Index", "geojson": _fake_severity_geojson(), "color_field": "severity_score"}
        res = _build_dashboard_html([layer])
        self.assertNotIn("error", res)
        # branca's LinearColormap renders as an inline SVG legend containing the caption text
        self.assertIn("severity_score", res["html"])

    def test_color_field_with_no_numeric_values_warns_but_still_renders(self):
        geojson = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"district": "Aden", "name_field": "not a number"},
             "geometry": {"type": "Point", "coordinates": [45.0, 12.7]}},
        ]}
        layer = {"name": "Facilities", "geojson": geojson, "color_field": "name_field"}
        res = _build_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertTrue(any("no numeric values" in w for w in res["warnings"]))

    def test_popup_fields_default_to_all_properties_when_omitted(self):
        layer = {"name": "Severity Index", "geojson": _fake_severity_geojson()}
        res = _build_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("severity_class", res["html"])

    def test_popup_fields_truncated_beyond_the_cap_and_warns(self):
        many_fields = [f"field_{i}" for i in range(20)]
        geojson = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {f: i for i, f in enumerate(many_fields)},
             "geometry": {"type": "Point", "coordinates": [45.0, 12.7]}},
        ]}
        layer = {"name": "Big", "geojson": geojson, "popup_fields": many_fields}
        res = _build_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertTrue(any("truncated" in w for w in res["warnings"]))

    def test_missing_geojson_field_missing_from_first_feature_is_dropped_not_crashed(self):
        # A popup field the caller asked for that isn't actually on the
        # layer's features must be silently dropped, not raise -- this is
        # the real-world case of a stale/mistyped field name.
        layer = {"name": "Severity Index", "geojson": _fake_severity_geojson(), "popup_fields": ["district", "not_a_real_field"]}
        res = _build_dashboard_html([layer])
        self.assertNotIn("error", res)

    def test_no_features_anywhere_falls_back_to_world_view_without_crashing(self):
        empty_geojson = {"type": "FeatureCollection", "features": []}
        res = _build_dashboard_html([{"name": "Empty", "geojson": empty_geojson}])
        self.assertNotIn("error", res)

    def test_title_is_escaped_and_embedded(self):
        layer = {"name": "Severity Index", "geojson": _fake_severity_geojson()}
        res = _build_dashboard_html([layer], title="<script>alert(1)</script>")
        self.assertNotIn("error", res)
        self.assertNotIn("<script>alert(1)</script>", res["html"])
        self.assertIn("&lt;script&gt;", res["html"])

    def test_multiple_layers_each_become_a_toggleable_overlay(self):
        severity = {"name": "Severity Index", "geojson": _fake_severity_geojson()}
        facilities = {"name": "Health Facilities", "geojson": {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"name": "Aden Clinic"}, "geometry": {"type": "Point", "coordinates": [45.1, 12.8]}}],
        }}
        res = _build_dashboard_html([severity, facilities])
        self.assertNotIn("error", res)
        self.assertIn("Severity Index", res["html"])
        self.assertIn("Health Facilities", res["html"])


class TestGenerateHtmlDashboardValidation(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = generate_html_dashboard([{"layer_name": "some_layer"}])
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_rejects_empty_layers(self):
        res = generate_html_dashboard([])
        self.assertIn("error", res)


class TestGenerateHtmlDashboardConnectivityNote(unittest.TestCase):
    """The CDN/offline caveat used to live only in the tool's own description
    (paid on every call where ToolRouter merely selects this tool as a
    candidate, invoked or not -- see docs/API_COST_OPTIMIZATION_REVIEW.md
    section 2.3). Moved into the result instead, since it's only actually
    needed on the call where the tool runs. Mocks just enough of the QGIS
    layer-reading path (_find_layer_by_name, _write_layer_geojson_wgs84) to
    reach the response dict without a full QGIS object graph."""

    def test_result_includes_connectivity_note(self):
        _skip_if_missing(self, "folium")
        from unittest.mock import patch, MagicMock
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod

        def fake_write(layer, output_path):
            with open(output_path, "w", encoding="utf-8") as f:
                f.write('{"type": "FeatureCollection", "features": []}')
            return {}

        fake_layer = MagicMock()
        fake_layer.isSpatial.return_value = True

        with patch.object(export_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(export_tools_mod, "_find_layer_by_name", return_value=fake_layer), \
             patch.object(export_tools_mod, "_write_layer_geojson_wgs84", side_effect=fake_write):
            res = generate_html_dashboard([{"layer_name": "some_layer"}])

        self.assertTrue(res.get("success"), res)
        self.assertIn("connectivity_note", res)
        self.assertIn("internet access", res["connectivity_note"])


if __name__ == "__main__":
    unittest.main()
