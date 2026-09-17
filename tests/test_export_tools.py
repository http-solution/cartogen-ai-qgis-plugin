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
    _write_vector, export_layer, export_to_csv, _sanitize_csv_formula_injection,
    _classify_freshness, _humanize_age, _freshness_legend_html,
)
import datetime


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
            return (0, "")

        fake_writer.writeAsVectorFormatV2.side_effect = fake_write

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
    completed. Same default-derivation convention styling_tools.py's save_layer_style
    (_derive_style_path) already established: an explicit path always wins; otherwise sit
    beside the layer's real on-disk source, or fall back to Desktop for a scratch/memory
    layer."""

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

    def test_no_path_falls_back_beside_a_real_on_disk_source(self):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod
        import tempfile
        fd, real_file = tempfile.mkstemp(suffix=".gpkg")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(real_file) and os.remove(real_file))
        path, used_fallback = export_tools_mod._derive_csv_path(
            self._fake_layer(source=f"{real_file}|layername=incidents"), None)
        self.assertEqual(path, f"{os.path.splitext(real_file)[0]}.csv")
        self.assertFalse(used_fallback)

    def test_no_path_and_no_real_source_falls_back_to_desktop(self):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod
        path, used_fallback = export_tools_mod._derive_csv_path(
            self._fake_layer(name="Scratch Layer", source=""), None)
        self.assertTrue(path.endswith("Scratch Layer.csv"))
        self.assertTrue(used_fallback)

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


if __name__ == "__main__":
    unittest.main()
