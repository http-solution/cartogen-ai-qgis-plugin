# -*- coding: utf-8 -*-
"""Tests for the animated/temporal dashboard feature added to
agent/tools/export_tools.py -- Baron's "animated dashboard from several
views ... status of fighting groups from 2016-2026 ... control areas"
request, built as a generic, reusable "animate a multi-period status
dataset" capability (not hardcoded to Syria/any specific conflict --
Baron's own instruction was "just build the capability, data later"). All
synthetic/placeholder data below; no real historical/operational data is
fabricated anywhere in this test file or the feature itself.

Same split as test_export_tools.py's TestBuildDashboardHtml: the pure
HTML-generation core (_build_temporal_dashboard_html and its helpers) needs
only folium/branca, no live QGIS session, so it's tested directly with
synthetic GeoJSON; the registered tools' QGIS-touching wrappers are tested
only for their outside-QGIS/validation behavior plus one mocked success
path, mirroring TestGenerateHtmlDashboardConnectivityNote's mocking style."""
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.tools.export_tools import (
    _categorical_color_map,
    _date_to_epoch_ms,
    _month_bucket_label,
    _resolve_feature_locations,
    _resolve_temporal_colors,
    _resolve_temporal_bounds,
    _build_trend_chart_data,
    _build_temporal_dashboard_html,
    _compute_animation_frame_epochs,
    _temporal_subset_expression,
    generate_temporal_dashboard,
    export_temporal_animation_frames,
)


def _skip_if_missing(test_case, module_name):
    try:
        __import__(module_name)
    except ImportError:
        test_case.skipTest(f"{module_name} not installed")


def _control_areas_geojson():
    """Synthetic placeholder "control areas" features -- deliberately
    generic (Faction A/B/C, made-up dates), never a real conflict dataset."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"faction": "Faction A", "area_name": "Sector 1", "start_date": "2016-01-01", "end_date": "2018-06-15"},
                "geometry": {"type": "Polygon", "coordinates": [[[36.0, 34.0], [36.2, 34.0], [36.2, 34.2], [36.0, 34.2], [36.0, 34.0]]]},
            },
            {
                "type": "Feature",
                "properties": {"faction": "Faction B", "area_name": "Sector 1", "start_date": "2018-06-16", "end_date": None},
                "geometry": {"type": "Polygon", "coordinates": [[[36.0, 34.0], [36.2, 34.0], [36.2, 34.2], [36.0, 34.2], [36.0, 34.0]]]},
            },
            {
                "type": "Feature",
                "properties": {"faction": "Faction C", "area_name": "Sector 2", "start_date": "2020-03-01", "end_date": "2022-01-01"},
                "geometry": {"type": "Polygon", "coordinates": [[[36.3, 34.0], [36.5, 34.0], [36.5, 34.2], [36.3, 34.2], [36.3, 34.0]]]},
            },
        ],
    }


class TestCategoricalColorMap(unittest.TestCase):
    def test_assigns_stable_distinct_colors_in_first_seen_order(self):
        cmap = _categorical_color_map(["A", "B", "A", "C"])
        self.assertEqual(len(cmap), 3)
        self.assertEqual(len(set(cmap.values())), 3)

    def test_cycles_palette_past_eight_categories(self):
        values = [f"cat_{i}" for i in range(10)]
        cmap = _categorical_color_map(values)
        self.assertEqual(len(cmap), 10)
        self.assertEqual(cmap["cat_0"], cmap["cat_8"])  # palette has 8 colors, wraps

    def test_empty_input(self):
        self.assertEqual(_categorical_color_map([]), {})


class TestDateToEpochMs(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(_date_to_epoch_ms(None))

    def test_known_date_round_trips_to_utc_midnight(self):
        import datetime
        ms = _date_to_epoch_ms(datetime.date(2020, 1, 1))
        self.assertEqual(
            datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).date(),
            datetime.date(2020, 1, 1),
        )

    def test_later_date_gives_larger_epoch(self):
        import datetime
        self.assertLess(_date_to_epoch_ms(datetime.date(2016, 1, 1)), _date_to_epoch_ms(datetime.date(2026, 1, 1)))


class TestResolveTemporalColors(unittest.TestCase):
    def test_category_field_colors_by_category(self):
        features = _control_areas_geojson()["features"]
        warnings = []
        colors = _resolve_temporal_colors("Control Areas", features, "faction", None, warnings)
        self.assertEqual(len(colors), 3)
        # Features 0/1/2 are Faction A/B/C respectively (all distinct) --
        # each gets its own color.
        self.assertEqual(len(set(colors)), 3)
        self.assertEqual(warnings, [])

    def test_color_field_numeric_fallback_when_no_category_field(self):
        features = [
            {"properties": {"score": 0.1}}, {"properties": {"score": 0.9}},
        ]
        warnings = []
        colors = _resolve_temporal_colors("Layer", features, None, "score", warnings)
        self.assertEqual(len(colors), 2)
        self.assertNotEqual(colors[0], colors[1])

    def test_color_field_with_no_numeric_values_warns_and_uses_default(self):
        features = [{"properties": {"score": "not a number"}}]
        warnings = []
        colors = _resolve_temporal_colors("Layer", features, None, "score", warnings)
        self.assertEqual(colors, ["#3388ff"])
        self.assertTrue(any("no numeric values" in w for w in warnings))

    def test_neither_field_gives_single_default_color(self):
        features = [{"properties": {}}, {"properties": {}}]
        colors = _resolve_temporal_colors("Layer", features, None, None, [])
        self.assertEqual(colors, ["#3388ff", "#3388ff"])


class TestResolveTemporalBounds(unittest.TestCase):
    def test_parses_start_and_end_dates(self):
        features = _control_areas_geojson()["features"]
        bounds = _resolve_temporal_bounds(features, "start_date", "end_date", "Control Areas", [])
        self.assertEqual(len(bounds), 3)
        start0, end0 = bounds[0]
        self.assertIsNotNone(start0)
        self.assertIsNotNone(end0)
        self.assertLess(start0, end0)

    def test_missing_end_field_value_is_open_ended_none(self):
        features = _control_areas_geojson()["features"]
        bounds = _resolve_temporal_bounds(features, "start_date", "end_date", "Control Areas", [])
        # Feature index 1 has end_date=None in the fixture.
        self.assertIsNotNone(bounds[1][0])
        self.assertIsNone(bounds[1][1])

    def test_no_end_field_given_at_all_leaves_every_end_none(self):
        features = _control_areas_geojson()["features"]
        bounds = _resolve_temporal_bounds(features, "start_date", None, "Control Areas", [])
        self.assertTrue(all(end is None for _, end in bounds))

    def test_unparseable_start_is_none_and_warns(self):
        features = [{"properties": {"start_date": "not a date"}}]
        warnings = []
        bounds = _resolve_temporal_bounds(features, "start_date", None, "Layer", warnings)
        self.assertEqual(bounds, [(None, None)])
        self.assertTrue(any("start_field" in w for w in warnings))

    def test_missing_start_field_value_entirely_is_none_without_warning(self):
        # No start_date key at all (not even None) -- distinct from "present
        # but unparseable"; treated the same functionally (always visible)
        # but shouldn't falsely claim a parse failure happened.
        features = [{"properties": {}}]
        warnings = []
        bounds = _resolve_temporal_bounds(features, "start_date", None, "Layer", warnings)
        self.assertEqual(bounds, [(None, None)])
        self.assertEqual(warnings, [])


class TestBuildTemporalDashboardHtml(unittest.TestCase):
    def setUp(self):
        _skip_if_missing(self, "folium")

    def test_rejects_empty_layers(self):
        res = _build_temporal_dashboard_html([])
        self.assertIn("error", res)

    def test_requires_at_least_one_temporal_layer(self):
        layer = {"name": "Static Only", "geojson": _control_areas_geojson()}
        res = _build_temporal_dashboard_html([layer])
        self.assertIn("error", res)
        self.assertIn("generate_html_dashboard", res["error"])

    def test_builds_html_with_slider_and_play_control(self):
        layer = {
            "name": "Control Areas", "geojson": _control_areas_geojson(),
            "start_field": "start_date", "end_field": "end_date", "category_field": "faction",
        }
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("cartogen-slider", res["html"])
        self.assertIn("cartogen-play-btn", res["html"])
        self.assertIn("__cartogen_start_ms", res["html"])
        self.assertIn("Control Areas", res["html"])

    def test_bakes_per_feature_color_and_window_into_geojson(self):
        layer = {
            "name": "Control Areas", "geojson": _control_areas_geojson(),
            "start_field": "start_date", "end_field": "end_date", "category_field": "faction",
        }
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("__cartogen_color", res["html"])
        self.assertIn("__cartogen_end_ms", res["html"])

    def test_mixes_static_reference_layer_with_temporal_layer(self):
        static_layer = {"name": "Country Outline", "geojson": {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"name": "Country"}, "geometry": {"type": "Polygon", "coordinates": [[[36.0, 34.0], [36.5, 34.0], [36.5, 34.3], [36.0, 34.3], [36.0, 34.0]]]}}],
        }}
        temporal_layer = {
            "name": "Control Areas", "geojson": _control_areas_geojson(),
            "start_field": "start_date", "end_field": "end_date", "category_field": "faction",
        }
        res = _build_temporal_dashboard_html([static_layer, temporal_layer])
        self.assertNotIn("error", res)
        self.assertIn("Country Outline", res["html"])
        self.assertIn("Control Areas", res["html"])

    def test_internal_cartogen_fields_never_default_into_popup(self):
        layer = {
            "name": "Control Areas", "geojson": _control_areas_geojson(),
            "start_field": "start_date", "end_field": "end_date", "category_field": "faction",
        }
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        # The raw properties (embedded as the GeoJSON data blob) will still
        # mention these internal keys -- the point is they aren't turned
        # into GeoJsonPopup field/alias entries. Checking for the alias
        # markup pattern folium emits for popup fields is enough here.
        self.assertNotIn("__cartogen_start_ms</th", res["html"])

    def test_all_features_unparseable_dates_returns_error_with_warnings(self):
        geojson = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"start_date": "garbage"}, "geometry": {"type": "Point", "coordinates": [36.0, 34.0]}},
        ]}
        layer = {"name": "Bad Dates", "geojson": geojson, "start_field": "start_date"}
        res = _build_temporal_dashboard_html([layer])
        self.assertIn("error", res)
        self.assertIn("warnings", res)

    def test_title_is_escaped_and_embedded(self):
        layer = {
            "name": "Control Areas", "geojson": _control_areas_geojson(),
            "start_field": "start_date", "end_field": "end_date",
        }
        res = _build_temporal_dashboard_html([layer], title="<b>Status Over Time</b>")
        self.assertNotIn("error", res)
        self.assertNotIn("<b>Status Over Time</b>", res["html"])
        self.assertIn("&lt;b&gt;", res["html"])

    def test_step_days_changes_slider_step_attribute(self):
        layer = {
            "name": "Control Areas", "geojson": _control_areas_geojson(),
            "start_field": "start_date", "end_field": "end_date",
        }
        res_default = _build_temporal_dashboard_html([layer], step_days=30)
        res_weekly = _build_temporal_dashboard_html([layer], step_days=7)
        self.assertNotIn("error", res_default)
        self.assertNotIn("error", res_weekly)
        self.assertNotEqual(res_default["html"], res_weekly["html"])


class TestGenerateTemporalDashboardValidation(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = generate_temporal_dashboard([{"layer_name": "some_layer", "start_field": "start_date"}])
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_rejects_empty_layers(self):
        res = generate_temporal_dashboard([])
        self.assertIn("error", res)


class TestGenerateTemporalDashboardMockedSuccess(unittest.TestCase):
    """Same mocking convention as test_export_tools.py's
    TestGenerateHtmlDashboardConnectivityNote: mocks just enough of the
    QGIS layer-reading path to reach the response dict."""

    def test_success_path_returns_connectivity_note_and_layer_count(self):
        _skip_if_missing(self, "folium")
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod
        import json as _json

        def fake_write(layer, output_path):
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(_json.dumps(_control_areas_geojson()))
            return {}

        fake_layer = MagicMock()
        fake_layer.isSpatial.return_value = True

        with patch.object(export_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(export_tools_mod, "_find_layer_by_name", return_value=fake_layer), \
             patch.object(export_tools_mod, "_write_layer_geojson_wgs84", side_effect=fake_write):
            res = generate_temporal_dashboard([{
                "layer_name": "control_areas", "start_field": "start_date",
                "end_field": "end_date", "category_field": "faction",
            }])

        self.assertTrue(res.get("success"), res)
        self.assertIn("connectivity_note", res)
        self.assertEqual(res["layer_count"], 1)


class TestComputeAnimationFrameEpochs(unittest.TestCase):
    def test_single_instant_returns_one_frame(self):
        self.assertEqual(_compute_animation_frame_epochs(1000, 1000, 30), [1000])

    def test_steps_evenly_and_always_includes_final_endpoint(self):
        day_ms = 86400000
        frames = _compute_animation_frame_epochs(0, 10 * day_ms, 3)
        self.assertEqual(frames[0], 0)
        self.assertEqual(frames[-1], 10 * day_ms)
        self.assertTrue(all(frames[i] < frames[i + 1] for i in range(len(frames) - 1)))

    def test_step_days_less_than_one_treated_as_one_day(self):
        day_ms = 86400000
        frames = _compute_animation_frame_epochs(0, 2 * day_ms, 0)
        self.assertEqual(frames, [0, day_ms, 2 * day_ms])


class TestTemporalSubsetExpression(unittest.TestCase):
    def test_start_only(self):
        expr = _temporal_subset_expression("start_date", None, "2020-06-01")
        self.assertEqual(expr, "\"start_date\" <= '2020-06-01'")

    def test_start_and_end_treats_null_end_as_open_ended(self):
        expr = _temporal_subset_expression("start_date", "end_date", "2020-06-01")
        self.assertIn("\"start_date\" <= '2020-06-01'", expr)
        self.assertIn("\"end_date\" IS NULL", expr)
        self.assertIn("\"end_date\" >= '2020-06-01'", expr)


class TestExportTemporalAnimationFramesValidation(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = export_temporal_animation_frames("some_layer", "start_date")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestExportTemporalAnimationFramesMockedSuccess(unittest.TestCase):
    def test_renders_one_frame_per_computed_timestamp_and_restores_filter(self):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod

        def _fake_feature(start, end):
            f = MagicMock()
            f.__getitem__ = lambda self, key, _s=start, _e=end: {"start_date": _s, "end_date": _e}[key]
            return f

        fake_field_a = MagicMock()
        fake_field_a.name.return_value = "start_date"
        fake_field_b = MagicMock()
        fake_field_b.name.return_value = "end_date"

        fake_layer = MagicMock()
        fake_layer.fields.return_value = [fake_field_a, fake_field_b]
        fake_layer.getFeatures.return_value = [
            _fake_feature("2016-01-01", "2016-04-01"),
            _fake_feature("2016-07-01", None),
        ]
        fake_layer.subsetString.return_value = "ORIGINAL FILTER"
        fake_layer.setSubsetString.return_value = True

        fake_canvas = MagicMock()
        fake_iface = MagicMock()
        fake_iface.mapCanvas.return_value = fake_canvas

        with patch.object(export_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(export_tools_mod, "iface", fake_iface), \
             patch.object(export_tools_mod, "_find_layer_by_name", return_value=fake_layer):
            import tempfile
            out_dir = tempfile.mkdtemp()
            res = export_temporal_animation_frames(
                "control_areas", "start_date", end_field="end_date", output_dir=out_dir, step_days=90,
            )

        self.assertTrue(res.get("success"), res)
        self.assertGreaterEqual(res["frame_count"], 1)
        self.assertIn("note", res)
        # Filter restored to its original value once done.
        fake_layer.setSubsetString.assert_called_with("ORIGINAL FILTER")

    def test_missing_start_field_errors(self):
        import cartogen_ai.core.agent.tools.export_tools as export_tools_mod
        fake_field = MagicMock()
        fake_field.name.return_value = "some_other_field"
        fake_layer = MagicMock()
        fake_layer.fields.return_value = [fake_field]

        with patch.object(export_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(export_tools_mod, "iface", MagicMock()), \
             patch.object(export_tools_mod, "_find_layer_by_name", return_value=fake_layer):
            res = export_temporal_animation_frames("control_areas", "start_date")
        self.assertIn("error", res)
        self.assertIn("not found", res["error"])


if __name__ == "__main__":
    unittest.main()


class TestMonthBucketLabel(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(_month_bucket_label(None))

    def test_formats_year_month(self):
        import datetime
        self.assertEqual(_month_bucket_label(datetime.date(2018, 6, 15)), "2018-06")

    def test_pads_single_digit_month(self):
        import datetime
        self.assertEqual(_month_bucket_label(datetime.date(2020, 1, 1)), "2020-01")


class TestResolveFeatureLocations(unittest.TestCase):
    def test_no_location_field_returns_all_none(self):
        features = [{"properties": {"governorate": "Aleppo"}}, {"properties": {"governorate": "Homs"}}]
        self.assertEqual(_resolve_feature_locations(features, None), [None, None])

    def test_extracts_the_named_field(self):
        features = [{"properties": {"governorate": "Aleppo"}}, {"properties": {"governorate": "Homs"}}]
        self.assertEqual(_resolve_feature_locations(features, "governorate"), ["Aleppo", "Homs"])

    def test_missing_field_on_a_feature_is_none(self):
        features = [{"properties": {}}]
        self.assertEqual(_resolve_feature_locations(features, "governorate"), [None])


class TestResolveTemporalColorsSortedOrder(unittest.TestCase):
    def test_colors_assigned_in_sorted_not_first_seen_order(self):
        # Feature order is C, A, B but colors should be assigned as if
        # sorted alphabetically (A, B, C) -- this is what keeps the map's
        # colors lined up with the trend chart's legend for a single layer.
        features = [
            {"properties": {"faction": "Faction C"}},
            {"properties": {"faction": "Faction A"}},
            {"properties": {"faction": "Faction B"}},
        ]
        colors = _resolve_temporal_colors("Layer", features, "faction", None, [])
        from cartogen_ai.core.agent.tools.export_tools import _categorical_color_map as _cc
        expected_map = _cc(["Faction A", "Faction B", "Faction C"])
        self.assertEqual(colors[0], expected_map["Faction C"])
        self.assertEqual(colors[1], expected_map["Faction A"])
        self.assertEqual(colors[2], expected_map["Faction B"])

    def test_none_category_value_gets_default_color(self):
        features = [{"properties": {"faction": None}}, {"properties": {"faction": "Faction A"}}]
        colors = _resolve_temporal_colors("Layer", features, "faction", None, [])
        self.assertEqual(colors[0], "#999999")


class TestBuildTrendChartData(unittest.TestCase):
    def test_returns_none_when_no_layer_has_category_field(self):
        features = _control_areas_geojson()["features"]
        bounds = _resolve_temporal_bounds(features, "start_date", "end_date", "Control Areas", [])
        start_ms_list = [s for s, _e in bounds]
        locations = _resolve_feature_locations(features, None)
        result = _build_trend_chart_data([(features, None, locations, start_ms_list)])
        self.assertIsNone(result)

    def test_aggregates_counts_by_month_and_category(self):
        features = _control_areas_geojson()["features"]
        bounds = _resolve_temporal_bounds(features, "start_date", "end_date", "Control Areas", [])
        start_ms_list = [s for s, _e in bounds]
        locations = _resolve_feature_locations(features, None)
        result = _build_trend_chart_data([(features, "faction", locations, start_ms_list)])
        self.assertIsNotNone(result)
        self.assertIn("2016-01", result["months"])
        self.assertIn("Faction A", result["categories"])
        self.assertEqual(result["by_location"]["__none__"]["2016-01"]["Faction A"], 1)

    def test_splits_by_location_when_location_field_given(self):
        features = [
            {"properties": {"faction": "Faction A", "start_date": "2020-01-05", "governorate": "Aleppo"}},
            {"properties": {"faction": "Faction A", "start_date": "2020-01-10", "governorate": "Homs"}},
        ]
        bounds = _resolve_temporal_bounds(features, "start_date", None, "Layer", [])
        start_ms_list = [s for s, _e in bounds]
        locations = _resolve_feature_locations(features, "governorate")
        result = _build_trend_chart_data([(features, "faction", locations, start_ms_list)])
        self.assertEqual(result["by_location"]["Aleppo"]["2020-01"]["Faction A"], 1)
        self.assertEqual(result["by_location"]["Homs"]["2020-01"]["Faction A"], 1)

    def test_feature_with_unparseable_start_is_excluded_from_chart(self):
        # category_field IS set (so this isn't the "no category_field
        # anywhere" None case), but the only feature has no usable start_ms
        # -- it contributes nothing, leaving an empty-but-present chart.
        features = [{"properties": {"faction": "Faction A"}}]
        result = _build_trend_chart_data([(features, "faction", [None], [None])])
        self.assertIsNotNone(result)
        self.assertEqual(result["months"], [])
        self.assertEqual(result["categories"], [])


class TestBuildTemporalDashboardHtmlNewFeatures(unittest.TestCase):
    def setUp(self):
        _skip_if_missing(self, "folium")

    def test_point_layer_renders_with_circle_marker_point_to_layer(self):
        geojson = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"faction": "Faction A", "start_date": "2020-01-01"},
             "geometry": {"type": "Point", "coordinates": [36.0, 34.0]}},
        ]}
        layer = {"name": "Events", "geojson": geojson, "start_field": "start_date", "category_field": "faction"}
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("pointToLayer", res["html"])
        self.assertIn("CircleMarker", res["html"])

    def test_location_filter_panel_rendered_when_location_field_set(self):
        layer = {
            "name": "Control Areas", "geojson": _control_areas_geojson(),
            "start_field": "start_date", "end_field": "end_date", "category_field": "faction",
            "location_field": "area_name",
        }
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("cartogen-location-panel", res["html"])
        self.assertIn("Sector 1", res["html"])
        self.assertIn("Sector 2", res["html"])

    def test_no_location_panel_when_location_field_omitted(self):
        layer = {
            "name": "Control Areas", "geojson": _control_areas_geojson(),
            "start_field": "start_date", "end_field": "end_date", "category_field": "faction",
        }
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertNotIn("cartogen-location-panel", res["html"])

    def test_trend_chart_rendered_when_category_field_set(self):
        layer = {
            "name": "Control Areas", "geojson": _control_areas_geojson(),
            "start_field": "start_date", "end_field": "end_date", "category_field": "faction",
        }
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("cartogen-trend-chart", res["html"])
        self.assertIn("chart.umd.min.js", res["html"])
        self.assertIn("__cartogenChartData", res["html"])

    def test_no_chart_when_no_category_field_anywhere(self):
        geojson = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"start_date": "2020-01-01", "end_date": None},
             "geometry": {"type": "Point", "coordinates": [36.0, 34.0]}},
        ]}
        layer = {"name": "Events", "geojson": geojson, "start_field": "start_date", "end_field": "end_date"}
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertNotIn("cartogen-trend-chart", res["html"])

    def test_date_range_sliders_present(self):
        layer = {
            "name": "Control Areas", "geojson": _control_areas_geojson(),
            "start_field": "start_date", "end_field": "end_date",
        }
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("cartogen-range-from", res["html"])
        self.assertIn("cartogen-range-to", res["html"])

    def test_location_checkbox_panel_html_escapes_location_values(self):
        # The visible checkbox panel is real page markup -- a location name
        # with HTML-special characters must not break it.
        geojson = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"faction": "Faction A", "start_date": "2020-01-01", "loc": "<b>Zone</b>"},
             "geometry": {"type": "Point", "coordinates": [36.0, 34.0]}},
        ]}
        layer = {"name": "Events", "geojson": geojson, "start_field": "start_date",
                 "category_field": "faction", "location_field": "loc"}
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn("&lt;b&gt;Zone&lt;/b&gt;", res["html"])

    def test_chart_data_script_embedding_survives_a_script_breakout_attempt(self):
        # A location/category value containing a literal '</script>' must
        # not be able to prematurely close the chart's <script> block --
        # see _json_for_inline_script.
        evil = "</script><script>alert(1)</script>"
        geojson = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"faction": evil, "start_date": "2020-01-01", "loc": evil},
             "geometry": {"type": "Point", "coordinates": [36.0, 34.0]}},
        ]}
        layer = {"name": "Events", "geojson": geojson, "start_field": "start_date",
                 "category_field": "faction", "location_field": "loc"}
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertNotIn("</script><script>alert(1)</script>", res["html"])
        self.assertIn("<\\/script>", res["html"])

    def test_custom_marker_radius_applied(self):
        geojson = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"faction": "Faction A", "start_date": "2020-01-01"},
             "geometry": {"type": "Point", "coordinates": [36.0, 34.0]}},
        ]}
        layer = {"name": "Events", "geojson": geojson, "start_field": "start_date",
                 "category_field": "faction", "marker_radius": 12}
        res = _build_temporal_dashboard_html([layer])
        self.assertNotIn("error", res)
        self.assertIn('"radius": 12', res["html"])
