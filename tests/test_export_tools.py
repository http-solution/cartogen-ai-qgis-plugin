# -*- coding: utf-8 -*-
"""Tests for the provenance-footer addition to generate_report/generate_spatial_report
(agent/tools/export_tools.py) -- Tier-2 item #7 from the humanitarian feature review:
surface what agent/lineage.py already tracks per layer (tool, params, sources,
timestamp) in generated reports, instead of leaving it invisible to a report's
actual audience (often not QGIS users, e.g. a fund-allocation committee)."""
import os
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.tools.export_tools import (
    generate_report, generate_spatial_report, _layer_provenance_entries, _format_lineage_entry,
    generate_html_dashboard, _build_dashboard_html, _iter_geojson_coords, _humanize_field_name,
    _write_vector, export_to_csv, _sanitize_csv_formula_injection,
    _classify_freshness, _humanize_age, _freshness_legend_html,
    _resolve_basemap_kwargs, _prepare_dashboard_layer, _DASHBOARD_BASEMAPS,
    _check_shapefile_field_names,
)

import datetime


def _skip_if_missing(test_case, module_name):
    try:
        __import__(module_name)
    except ImportError:
        test_case.skipTest(f"{module_name} not installed")


class TestResolveBasemapKwargs(unittest.TestCase):
    """Phase 4 (2026-09-19): the dashboard's basemap was hardcoded to CartoDB Positron with
    no satellite/HOT toggle -- _resolve_basemap_kwargs adds that without needing an API key
    or reintroducing OSM's own directly-embedded tiles (the exact pattern OSM's tile usage
    policy blocks, already documented in _build_dashboard_html's own comment)."""

    def test_default_is_positron_when_none_given(self):
        kwargs, warning = _resolve_basemap_kwargs(None)
        self.assertEqual(kwargs, _DASHBOARD_BASEMAPS["positron"])
        self.assertIsNone(warning)

    def test_known_basemap_resolves_case_insensitively(self):
        kwargs, warning = _resolve_basemap_kwargs("SATELLITE")
        self.assertEqual(kwargs, _DASHBOARD_BASEMAPS["satellite"])
        self.assertIsNone(warning)

    def test_hot_basemap_has_required_attribution(self):
        kwargs, warning = _resolve_basemap_kwargs("hot")
        self.assertIn("Humanitarian", kwargs["attr"])
        self.assertIsNone(warning)

    def test_unknown_basemap_falls_back_to_default_with_warning(self):
        kwargs, warning = _resolve_basemap_kwargs("bogus_basemap")
        self.assertEqual(kwargs, _DASHBOARD_BASEMAPS["positron"])
        self.assertIsNotNone(warning)
        self.assertIn("bogus_basemap", warning)


class TestPrepareDashboardLayer(unittest.TestCase):
    """Phase 4 (2026-09-19): generate_html_dashboard/generate_temporal_dashboard previously
    embedded a layer's full, unbounded GeoJSON with no feature cap or simplification -- a
    large/detailed layer could produce a 25MB+ HTML file that freezes the viewer's browser."""

    def test_small_simple_layer_is_returned_unchanged(self):
        layer = MagicMock()
        layer.featureCount.return_value = 10
        layer.extent.return_value.width.return_value = 0.0
        layer.extent.return_value.height.return_value = 0.0

        result_layer, warning = _prepare_dashboard_layer(layer, max_features=2500)

        self.assertIs(result_layer, layer)
        self.assertIsNone(warning)

    @patch("cartogen_ai.core.agent.tools.export_tools.QgsFeatureRequest", create=True)
    @patch("cartogen_ai.core.agent.tools.export_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.export_tools.QgsVectorLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.export_tools.QgsWkbTypes", create=True)
    def test_over_cap_layer_is_truncated_with_warning(self, mock_wkb, mock_layer_cls, mock_feat_cls, mock_request_cls):
        layer = MagicMock()
        layer.featureCount.return_value = 5000
        layer.extent.return_value.width.return_value = 0.0
        layer.extent.return_value.height.return_value = 0.0
        layer.getFeatures.return_value = []
        mem_layer = mock_layer_cls.return_value

        result_layer, warning = _prepare_dashboard_layer(layer, max_features=2500)

        self.assertIs(result_layer, mem_layer)
        self.assertIsNotNone(warning)
        self.assertIn("evenly-sampled", warning)
        self.assertIn("5,000", warning)

    @patch("cartogen_ai.core.agent.tools.export_tools.QgsFeatureRequest", create=True)
    @patch("cartogen_ai.core.agent.tools.export_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.export_tools.QgsVectorLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.export_tools.QgsWkbTypes", create=True)
    def test_over_cap_layer_samples_across_whole_source_not_just_the_start(
        self, mock_wkb, mock_layer_cls, mock_feat_cls, mock_request_cls
    ):
        """Regression for the 'first N features only' bug: a layer whose features happen to be
        grouped by region (a common real shape for a paginated/region-by-region ingest) must
        still get features kept from throughout the whole source, not just its first slice."""
        total = 5000
        max_features = 2500

        def make_feat(region_tag):
            f = MagicMock()
            f.geometry.return_value.isEmpty.return_value = True
            f.attributes.return_value = [region_tag]
            return f

        # First half tagged "region-A", second half "region-B" -- the exact ordering shape
        # that made the old "first N" truncation silently drop region-B entirely.
        layer = MagicMock()
        layer.featureCount.return_value = total
        layer.extent.return_value.width.return_value = 0.0
        layer.extent.return_value.height.return_value = 0.0
        layer.getFeatures.return_value = (
            [make_feat("region-A") for _ in range(total // 2)]
            + [make_feat("region-B") for _ in range(total // 2)]
        )
        mem_provider = mock_layer_cls.return_value.dataProvider.return_value
        mock_feat_cls.side_effect = lambda *a, **k: MagicMock()

        _prepare_dashboard_layer(layer, max_features=max_features)

        kept_feats = mem_provider.addFeatures.call_args.args[0]
        kept_regions = {f.setAttributes.call_args.args[0][0] for f in kept_feats}
        self.assertEqual(kept_regions, {"region-A", "region-B"})

    @patch("cartogen_ai.core.agent.tools.export_tools.QgsFeatureRequest", create=True)
    @patch("cartogen_ai.core.agent.tools.export_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.export_tools.QgsVectorLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.export_tools.QgsWkbTypes", create=True)
    def test_large_extent_simplifies_geometry_with_warning(self, mock_wkb, mock_layer_cls, mock_feat_cls, mock_request_cls):
        layer = MagicMock()
        layer.featureCount.return_value = 10
        layer.extent.return_value.width.return_value = 4000.0
        layer.extent.return_value.height.return_value = 3000.0
        fake_feat = MagicMock()
        fake_feat.geometry.return_value.isEmpty.return_value = False
        layer.getFeatures.return_value = [fake_feat]

        result_layer, warning = _prepare_dashboard_layer(layer, max_features=2500)

        self.assertIsNotNone(warning)
        self.assertIn("simplified", warning)
        fake_feat.geometry.return_value.simplify.assert_called_once()

    def test_exception_during_inspection_falls_back_to_original_layer(self):
        layer = MagicMock()
        layer.featureCount.side_effect = RuntimeError("boom")

        result_layer, warning = _prepare_dashboard_layer(layer, max_features=2500)

        self.assertIs(result_layer, layer)
        self.assertIsNone(warning)


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
    candidate, invoked or not -- see docs/archive/API_COST_OPTIMIZATION_REVIEW.md
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


class TestWriteVectorSensitivityWarning(unittest.TestCase):
    """Point 24 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md:
    _write_vector (the shared helper behind export_layer/export_to_csv) now
    adds an advisory warning -- never blocks -- when the layer being
    exported is tagged RESTRICTED/SENSITIVE via set_layer_sensitivity."""

    def _run_write_vector(self, layer):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod

        fake_writer = MagicMock()
        fake_writer.SaveVectorOptions.return_value = MagicMock()

        with patch.object(export_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(export_tools_mod, "QgsVectorFileWriter", fake_writer, create=True), \
             patch.object(export_tools_mod, "QgsCoordinateTransformContext", MagicMock(), create=True), \
             patch.object(export_tools_mod, "_VFW_NO_ERROR", 0):
            fake_writer.writeAsVectorFormatV2.return_value = (0, "")
            fake_writer.writeAsVectorFormatV3.return_value = (0, "", "", "")
            return _write_vector(layer, "/tmp/out.gpkg", "GPKG")

    def test_sensitive_layer_gets_a_warning_but_still_succeeds(self):
        layer = MagicMock()
        layer.customProperty.return_value = '{"level": "SENSITIVE", "reason": "beneficiary GPS"}'

        res = self._run_write_vector(layer)

        self.assertTrue(res["success"])
        self.assertIn("output_path", res)
        self.assertIn("warning", res)
        self.assertIn("SENSITIVE", res["warning"])
        self.assertIn("beneficiary GPS", res["warning"])

    def test_untagged_layer_gets_no_warning(self):
        layer = MagicMock()
        layer.customProperty.return_value = ""

        res = self._run_write_vector(layer)

        self.assertTrue(res["success"])
        self.assertNotIn("warning", res)

    def test_public_tagged_layer_gets_no_warning(self):
        layer = MagicMock()
        layer.customProperty.return_value = '{"level": "PUBLIC", "reason": null}'

        res = self._run_write_vector(layer)

        self.assertTrue(res["success"])
        self.assertNotIn("warning", res)


class TestExportLayerNoPathNeverPrompts(unittest.TestCase):
    """Same regression as TestExportToCsvDefaultOutputPath's own no-prompt test, for
    export_layer specifically: a prior version popped a blocking QFileDialog when
    output_path was omitted and an interactive session (iface/iface.mainWindow() both
    truthy) was present -- found in a code-review pass (2026-09-20). print_map has the
    identical fix but isn't covered here: it hits QGIS_AVAILABLE's early-return before
    reaching the output-path logic at all in this headless test environment, same as
    other QGIS-object-graph-heavy code in this codebase (see layout_tools.py's own tests'
    docstring for the same, already-established convention) -- only reachable via a real
    QGIS session, not a unit test."""

    def test_no_path_never_prompts_even_when_an_interactive_session_is_present(self):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod
        import tempfile
        import shutil
        tmp_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_home, True)
        fake_iface = MagicMock()
        fake_iface.mainWindow.return_value = MagicMock()
        layer = MagicMock()
        layer.name.return_value = "Scratch Layer"
        captured = {}

        def fake_write_vector(layer, output_path, driver, layer_options=None, only_selected=None):
            captured["output_path"] = output_path
            return {"success": True}

        with patch.object(export_tools_mod, "iface", fake_iface), \
             patch.object(export_tools_mod, "_find_layer_by_name", return_value=layer), \
             patch.object(export_tools_mod, "_write_vector", side_effect=fake_write_vector), \
             patch("os.path.expanduser", return_value=tmp_home):
            res = export_tools_mod.export_layer("Scratch Layer", "gpkg")

        self.assertTrue(res.get("success"), res)
        self.assertTrue(captured["output_path"].endswith("Scratch Layer.gpkg"))
        # export_layer no longer reads iface at all -- confirms no dialog branch was reached.
        fake_iface.mainWindow.assert_not_called()


class TestWriteVectorOnlySelectedWithNoSelection(unittest.TestCase):
    """Real bug found in a code-review pass (2026-09-20): only_selected=True with zero
    features actually selected used to silently fall through to a full-layer export (
    `use_selection and has_selection` is False either way), reporting only_selected_features
    as False with no warning at all -- an explicit "just the selected records" request was
    silently downgraded. Now fails loudly instead, since an export tool silently returning
    MORE data than requested is a real risk for sensitive/humanitarian layers."""

    def _run_write_vector(self, only_selected):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod

        fake_writer = MagicMock()
        fake_writer.SaveVectorOptions.return_value = MagicMock()
        layer = MagicMock()
        layer.customProperty.return_value = ""
        layer.selectedFeatureCount.return_value = 0

        with patch.object(export_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(export_tools_mod, "QgsVectorFileWriter", fake_writer, create=True), \
             patch.object(export_tools_mod, "QgsCoordinateTransformContext", MagicMock(), create=True), \
             patch.object(export_tools_mod, "_VFW_NO_ERROR", 0):
            fake_writer.writeAsVectorFormatV2.return_value = (0, "")
            fake_writer.writeAsVectorFormatV3.return_value = (0, "", "", "")
            return _write_vector(layer, "/tmp/out.gpkg", "GPKG", only_selected=only_selected)

    def test_only_selected_true_with_no_selection_errors_instead_of_exporting_everything(self):
        res = self._run_write_vector(only_selected=True)
        self.assertIn("error", res)
        self.assertNotIn("success", res)

    def test_only_selected_omitted_with_no_selection_still_exports_the_full_layer(self):
        # Unaffected case -- only_selected=None (not requested at all) must still export
        # the whole layer normally, same as before this fix.
        res = self._run_write_vector(only_selected=None)
        self.assertTrue(res["success"])


class TestWriteVectorUnresolvedNoErrorSentinel(unittest.TestCase):
    """QGIS-004, 2026-09-13 audit: _VFW_NO_ERROR being None (resolve_qgis_enum failed to
    resolve either QGIS 4.x's scoped or QGIS 3.x's flat WriterError.NoError -- a future QGIS
    API change neither form survives) used to make `error != _VFW_NO_ERROR` evaluate as
    `error != None`, which is ALWAYS True for a real (non-None) success code -- a fully
    successful export would silently report itself as failed, with nothing to catch the
    wrong answer since it never raises. Must now return a clear, explicit error instead."""

    def test_unresolved_sentinel_reports_a_clear_error_not_a_false_failure(self):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod

        fake_writer = MagicMock()
        fake_writer.SaveVectorOptions.return_value = MagicMock()
        layer = MagicMock()
        layer.customProperty.return_value = ""

        with patch.object(export_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(export_tools_mod, "QgsVectorFileWriter", fake_writer, create=True), \
             patch.object(export_tools_mod, "QgsCoordinateTransformContext", MagicMock(), create=True), \
             patch.object(export_tools_mod, "_VFW_NO_ERROR", None):
            # A real successful write -- error code 0, exactly what a genuine success
            # looks like. Before the fix, this was misreported as a failure purely
            # because the sentinel itself failed to resolve, an unrelated fact.
            fake_writer.writeAsVectorFormatV2.return_value = (0, "")
            fake_writer.writeAsVectorFormatV3.return_value = (0, "", "", "")
            res = _write_vector(layer, "/tmp/out.gpkg", "GPKG")

        self.assertIn("error", res)
        self.assertNotIn("success", res)
        self.assertIn("Could not resolve", res["error"])


class TestSanitizeCsvFormulaInjection(unittest.TestCase):
    """SEC-002, 2026-09-13 audit: export_to_csv wrote layer attribute values into CSV with
    no sanitization -- a string field's value beginning with =/+/-/@ is interpreted as a
    formula by Excel/LibreOffice/Sheets when opened there (CSV/formula injection, OWASP).
    Exercises _sanitize_csv_formula_injection directly against a real temp file -- pure
    Python (the csv module), no QGIS needed."""

    def _write_temp_csv(self, header, rows):
        import csv
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        self.addCleanup(os.remove, path)
        return path

    def _read_csv(self, path):
        import csv
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.reader(f))

    def test_quotes_formula_prefixed_string_field_values(self):
        path = self._write_temp_csv(
            ["name", "notes"],
            [["Site A", "=HYPERLINK(\"http://evil\")"], ["Site B", "+1;=cmd|'/calc'!A1"]],
        )
        err = _sanitize_csv_formula_injection(path, string_field_names={"name", "notes"})
        self.assertIsNone(err)
        rows = self._read_csv(path)
        self.assertEqual(rows[1], ["Site A", "'=HYPERLINK(\"http://evil\")"])
        self.assertEqual(rows[2], ["Site B", "'+1;=cmd|'/calc'!A1"])

    def test_leaves_non_string_columns_untouched_even_with_leading_minus(self):
        # A negative number (e.g. longitude) legitimately starts with "-" -- must never be
        # quoted into a string, which would break numeric use of the exported CSV. Only
        # columns named in string_field_names are eligible at all.
        path = self._write_temp_csv(["lon", "name"], [["-73.985", "Plain name"]])
        err = _sanitize_csv_formula_injection(path, string_field_names={"name"})
        self.assertIsNone(err)
        rows = self._read_csv(path)
        self.assertEqual(rows[1], ["-73.985", "Plain name"])

    def test_leaves_ordinary_string_values_untouched(self):
        path = self._write_temp_csv(["name"], [["Ordinary text"], [""]])
        err = _sanitize_csv_formula_injection(path, string_field_names={"name"})
        self.assertIsNone(err)
        rows = self._read_csv(path)
        self.assertEqual(rows[1], ["Ordinary text"])
        self.assertEqual(rows[2], [""])

    def test_no_string_fields_is_a_no_op(self):
        path = self._write_temp_csv(["lon", "lat"], [["-73.985", "40.7"]])
        err = _sanitize_csv_formula_injection(path, string_field_names=set())
        self.assertIsNone(err)
        rows = self._read_csv(path)
        self.assertEqual(rows[1], ["-73.985", "40.7"])


class TestExportToCsvSanitizesStringFields(unittest.TestCase):
    """Wiring test: export_to_csv must compute string_field_names from the real layer's
    fields (QVariant.String only) and route the written file through the sanitizer above --
    not just that the sanitizer works in isolation."""

    def test_string_field_sanitized_after_real_export_succeeds(self):
        import tempfile
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod

        fake_writer = MagicMock()
        fake_writer.SaveVectorOptions.return_value = MagicMock()

        def fake_write(layer, output_path, ctx, options):
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                f.write("name,WKT\n=cmd|'/calc'!A1,POINT (1 2)\n")
            return (0, "", "", "")

        fake_writer.writeAsVectorFormatV2.side_effect = fake_write
        fake_writer.writeAsVectorFormatV3.side_effect = fake_write

        name_field = MagicMock()
        name_field.name.return_value = "name"
        name_field.type.return_value = 10

        layer = MagicMock()
        layer.customProperty.return_value = ""
        layer.fields.return_value = [name_field]

        fake_qvariant = MagicMock()
        fake_qvariant.String = 10

        fd, output_path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(output_path) and os.remove(output_path))

        with patch.object(export_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(export_tools_mod, "QgsVectorFileWriter", fake_writer, create=True), \
             patch.object(export_tools_mod, "QgsCoordinateTransformContext", MagicMock(), create=True), \
             patch.object(export_tools_mod, "_VFW_NO_ERROR", 0), \
             patch.object(export_tools_mod, "QVariant", fake_qvariant, create=True), \
             patch.object(export_tools_mod, "_find_layer_by_name", return_value=layer):
            res = export_to_csv("incidents", output_path)

        self.assertTrue(res.get("success"), res)
        with open(output_path, newline="", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("'=cmd|'/calc'!A1", content)


class TestExportToCsvDefaultOutputPath(unittest.TestCase):
    """Live-reported bug, 2026-09-19: output_path was a hard-required argument with no
    default -- a turn that ran out of tool-call budget before the model supplied a path
    ended in "please specify a destination file path" after the real analysis had already
    completed. An explicit path always wins; otherwise the file lands under the project's
    own data/20_processed folder, or the QGIS profile folder if the project isn't saved yet.

    Live-reported, 2026-09-28: an EARLIER version of this default-derivation sat the CSV
    beside the layer's own on-disk source file -- fine for a layer loaded from a real file
    the user chose, but for a layer that is itself a Processing algorithm's intermediate
    output (the common case for an analysis result), that source is an auto-generated,
    QGIS-managed temp file with an ugly, unreadable name sitting in a directory QGIS can
    clean up at any time. The tests below replaced the ones asserting that old "beside the
    source" behavior, which is deliberately gone now -- every fallback path uses a clean,
    sanitized name under a stable project/profile folder instead, never the source's own
    basename."""

    def _fake_layer(self, name="incidents", source=""):
        layer = MagicMock()
        layer.name.return_value = name
        layer.source.return_value = source
        layer.customProperty.return_value = ""
        layer.fields.return_value = []
        return layer

    def test_explicit_output_path_always_wins(self):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod
        path, used_fallback = export_tools_mod._derive_csv_path(
            self._fake_layer(), "/explicit/path.csv")
        self.assertEqual(path, "/explicit/path.csv")
        self.assertFalse(used_fallback)

    @patch("cartogen_ai.core.agent.tools.export_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.export_tools.QgsProject", create=True)
    def test_no_path_uses_the_saved_projects_processed_data_folder(self, mock_project):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod
        import tempfile
        import shutil
        tmp_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_home, True)
        mock_project.instance.return_value.homePath.return_value = tmp_home

        # A real (but ugly, Processing-generated-looking) on-disk source must be IGNORED --
        # this is exactly the mechanism that produced an unopenable, unfindable CSV.
        ugly_source = os.path.join(tmp_home, "out_Health_Facilities_278d9021_6333.gpkg")
        path, used_fallback = export_tools_mod._derive_csv_path(
            self._fake_layer(name="Health Facilities Beyond 1 Hour", source=ugly_source), None)

        expected_dir = os.path.join(tmp_home, "data", "20_processed")
        self.assertEqual(path, os.path.join(expected_dir, "Health Facilities Beyond 1 Hour.csv"))
        self.assertTrue(used_fallback)
        self.assertTrue(os.path.isdir(expected_dir))

    @patch("cartogen_ai.core.agent.tools.export_tools.QGIS_AVAILABLE", False)
    def test_no_path_and_no_saved_project_uses_a_stable_folder_not_the_ugly_source_basename(self):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod
        import tempfile
        import shutil
        tmp_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_home, True)
        with patch("os.path.expanduser", return_value=tmp_home):
            path, used_fallback = export_tools_mod._derive_csv_path(
                self._fake_layer(name="Scratch Layer", source=f"{tmp_home}/out_weird_uuid.gpkg"), None)
        self.assertTrue(path.endswith(os.path.join("cartogen_ai", "exports", "geospatial", "Scratch Layer.csv")))
        self.assertTrue(used_fallback)

    def test_no_path_never_prompts_even_when_an_interactive_session_is_present(self):
        # Real bug found in a code-review pass (2026-09-20): a prior version of
        # _derive_csv_path briefly reintroduced a blocking QFileDialog.getSaveFileName()
        # call whenever `iface`/`iface.mainWindow()` were both truthy (i.e. a real
        # interactive QGIS session) -- reversing the whole point of this class's own
        # documented fix (a live-reported agent-turn stall). Mocks iface as present here
        # specifically because the OTHER tests in this class run with iface=None (headless
        # test env), which is exactly why that regression slipped past them silently: the
        # dialog branch was simply never reached by any existing test.
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod
        import tempfile
        import shutil
        tmp_home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_home, True)
        fake_iface = MagicMock()
        fake_iface.mainWindow.return_value = MagicMock()
        with patch.object(export_tools_mod, "iface", fake_iface),              patch("os.path.expanduser", return_value=tmp_home):
            path, used_fallback = export_tools_mod._derive_csv_path(
                self._fake_layer(name="Scratch Layer", source=""), None)
        self.assertTrue(path.endswith("Scratch Layer.csv"))
        self.assertTrue(used_fallback)
        # _derive_csv_path no longer reads `iface` at all -- confirms no dialog branch
        # was reached (a dialog path would have called mainWindow() to parent the prompt).
        fake_iface.mainWindow.assert_not_called()

    def test_export_to_csv_no_longer_requires_output_path_argument(self):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod
        # Calling with only layer_name must not raise TypeError for a missing
        # required positional argument -- the specific failure mode the live report
        # hit (the model had no path to give and the argument had no default).
        with patch.object(export_tools_mod, "_find_layer_by_name", return_value=None):
            res = export_to_csv("nonexistent")
        self.assertIn("error", res)
        self.assertIn("not found", res["error"])


def _iso_ago(**timedelta_kwargs):
    """ISO-8601 UTC timestamp `timedelta_kwargs` in the past -- e.g.
    _iso_ago(hours=2) for a 2-hour-old fetch."""
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(**timedelta_kwargs)).isoformat()


class TestClassifyFreshness(unittest.TestCase):
    """Dashboard freshness-pill classification (Live Hazard Monitoring, v1.9.0) --
    hazard_monitoring_tools.py's fetch tools stamp cartogen_ai/fetched_at on the layers they
    create; these classify that timestamp into the green/amber/red pill WorldMonitor's own
    dashboards use, reproduced here as plain HTML/CSS."""

    def test_missing_timestamp_returns_none(self):
        self.assertIsNone(_classify_freshness(None))
        self.assertIsNone(_classify_freshness(""))

    def test_unparseable_timestamp_returns_none(self):
        self.assertIsNone(_classify_freshness("not a date"))

    def test_just_now_is_fresh(self):
        status, age = _classify_freshness(_iso_ago(seconds=5))
        self.assertEqual(status, "fresh")

    def test_thirty_minutes_is_fresh(self):
        status, _ = _classify_freshness(_iso_ago(minutes=30))
        self.assertEqual(status, "fresh")

    def test_three_hours_is_stale(self):
        status, age = _classify_freshness(_iso_ago(hours=3))
        self.assertEqual(status, "stale")
        self.assertEqual(age, "3h")

    def test_two_days_is_very_stale(self):
        status, age = _classify_freshness(_iso_ago(days=2))
        self.assertEqual(status, "very_stale")
        self.assertEqual(age, "2d")

    def test_naive_timestamp_treated_as_utc(self):
        # datetime.fromisoformat on a timestamp with no timezone info -- confirm this doesn't
        # crash and still classifies sensibly (treated as UTC, matching how
        # hazard_monitoring_tools.py's _stamp_fetched_at always writes a timezone-aware one, but
        # a naive value shouldn't be able to reach an exception here either).
        naive = datetime.datetime.now().isoformat()
        result = _classify_freshness(naive)
        self.assertIsNotNone(result)


class TestHumanizeAge(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(_humanize_age(30), "30s")

    def test_minutes(self):
        self.assertEqual(_humanize_age(150), "2m")

    def test_hours(self):
        self.assertEqual(_humanize_age(7200), "2h")

    def test_days(self):
        self.assertEqual(_humanize_age(3 * 86400), "3d")


class TestFreshnessLegendHtml(unittest.TestCase):
    def test_no_layers_with_fetched_at_renders_nothing(self):
        html = _freshness_legend_html([{"name": "Regular Layer"}])
        self.assertEqual(html, "")

    def test_layer_with_fetched_at_renders_a_pill(self):
        html = _freshness_legend_html([{"name": "NASA Active Fires", "fetched_at": _iso_ago(minutes=5)}])
        self.assertIn("NASA Active Fires", html)
        self.assertIn("Fresh", html)

    def test_mixed_layers_only_badges_the_fetched_one(self):
        html = _freshness_legend_html([
            {"name": "Admin Boundaries"},  # never fetched live -- no badge
            {"name": "GDACS Disaster Alerts", "fetched_at": _iso_ago(hours=5)},
        ])
        self.assertNotIn("Admin Boundaries", html)
        self.assertIn("GDACS Disaster Alerts", html)
        self.assertIn("Stale", html)


class TestBuildDashboardHtmlFreshnessIntegration(unittest.TestCase):
    """End-to-end through _build_dashboard_html -- confirms the freshness legend actually gets
    embedded in the real generated page, not just tested in isolation."""

    def setUp(self):
        _skip_if_missing(self, "folium")

    def test_freshness_badge_appears_in_rendered_html(self):
        layer = {
            "name": "NASA Active Fires", "geojson": _fake_severity_geojson(),
            "fetched_at": _iso_ago(minutes=2),
        }
        res = _build_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("Data freshness", res["html"])
        self.assertIn("Fresh", res["html"])

    def test_no_fetched_at_produces_no_freshness_panel(self):
        layer = {"name": "Severity Index", "geojson": _fake_severity_geojson()}
        res = _build_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertNotIn("Data freshness", res["html"])


class TestShapefileFieldTruncation(unittest.TestCase):
    """Part B remediation: ESRI Shapefile exports must detect field names > 10 chars
    and report warnings and collision mappings."""

    def _make_field(self, name):
        f = MagicMock()
        f.name.return_value = name
        return f

    def test_short_fields_produce_no_warning(self):
        layer = MagicMock()
        layer.fields.return_value = [self._make_field("id"), self._make_field("pop_total")]
        warning, mapping = _check_shapefile_field_names(layer)
        self.assertIsNone(warning)
        self.assertEqual(mapping, {"id": "id", "pop_total": "pop_total"})

    def test_field_longer_than_10_chars_triggers_warning(self):
        layer = MagicMock()
        layer.fields.return_value = [self._make_field("population_density_2026")]
        warning, mapping = _check_shapefile_field_names(layer)
        self.assertIsNotNone(warning)
        self.assertIn("10 characters", warning)
        self.assertIn("population_density_2026", warning)
        self.assertEqual(mapping["population_density_2026"], "population")

    def test_collision_detected_when_two_fields_truncate_to_same_prefix(self):
        layer = MagicMock()
        layer.fields.return_value = [
            self._make_field("population_density"),
            self._make_field("population_growth"),
            self._make_field("POPULATION_DENSITY"),
        ]
        warning, mapping = _check_shapefile_field_names(layer)
        self.assertIsNotNone(warning)
        self.assertIn("collision", warning.lower())
        self.assertIn("GeoPackage", warning)
        self.assertEqual(mapping["population_density"], "population")
        self.assertEqual(mapping["population_growth"], "populati_1")
        self.assertEqual(mapping["POPULATION_DENSITY"], "POPULATI_2")

    def test_collision_when_existing_field_already_has_suffix_name(self):
        # A real field named "populati_1" already exists before or after a field
        # that truncates and needs suffix disambiguation
        layer = MagicMock()
        layer.fields.return_value = [
            self._make_field("population_density"),
            self._make_field("populati_1"),
            self._make_field("population_growth"),
        ]
        warning, mapping = _check_shapefile_field_names(layer)
        self.assertIsNotNone(warning)
        self.assertIn("collision", warning.lower())
        self.assertEqual(mapping["population_density"], "population")
        self.assertEqual(mapping["populati_1"], "populati_1")
        # Since populati_1 was taken, population_growth must loop to populati_2
        self.assertEqual(mapping["population_growth"], "populati_2")
        # Ensure all laundered names are distinct
        self.assertEqual(len(set(mapping.values())), 3)

    def test_collision_when_suffix_named_field_appears_first(self):
        layer = MagicMock()
        layer.fields.return_value = [
            self._make_field("populati_1"),
            self._make_field("population_density"),
            self._make_field("population_growth"),
        ]
        warning, mapping = _check_shapefile_field_names(layer)
        self.assertIsNotNone(warning)
        self.assertEqual(mapping["populati_1"], "populati_1")
        self.assertEqual(mapping["population_density"], "population")
        self.assertEqual(mapping["population_growth"], "populati_2")
        self.assertEqual(len(set(mapping.values())), 3)


if __name__ == "__main__":
    unittest.main()

