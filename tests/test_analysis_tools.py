# -*- coding: utf-8 -*-
import unittest
import datetime
from unittest.mock import patch, MagicMock
import cartogen_ai.core.agent.tools.analysis_tools as analysis_tools_mod
from cartogen_ai.core.agent.tools.analysis_tools import (
    _parse_date, _linear_regression, _forecast_series, forecast_trend,
    _normalize_minmax, _severity_class, _compute_severity_index, calculate_severity_index,
    calculate_presence_gap, calculate_population_in_need, calculate_damage_exposure_severity,
    _bucket_dates_by_period, analyze_incident_trend,
    _cap_entries, _MAX_RESULT_ENTRIES,
)


class TestParseDate(unittest.TestCase):
    def test_iso_string(self):
        self.assertEqual(_parse_date("2026-03-05"), datetime.date(2026, 3, 5))

    def test_iso_datetime_string(self):
        self.assertEqual(_parse_date("2026-03-05T12:30:00"), datetime.date(2026, 3, 5))

    def test_slash_format(self):
        self.assertEqual(_parse_date("2026/03/05"), datetime.date(2026, 3, 5))

    def test_python_date_and_datetime_passthrough(self):
        self.assertEqual(_parse_date(datetime.date(2026, 3, 5)), datetime.date(2026, 3, 5))
        self.assertEqual(_parse_date(datetime.datetime(2026, 3, 5, 9)), datetime.date(2026, 3, 5))

    def test_none_and_empty_and_garbage(self):
        self.assertIsNone(_parse_date(None))
        self.assertIsNone(_parse_date(""))
        self.assertIsNone(_parse_date("not a date"))


class TestLinearRegression(unittest.TestCase):
    def test_perfect_fit(self):
        x = [0, 1, 2, 3, 4]
        y = [10, 20, 30, 40, 50]
        fit = _linear_regression(x, y)
        self.assertAlmostEqual(fit["slope"], 10.0)
        self.assertAlmostEqual(fit["intercept"], 10.0)
        self.assertAlmostEqual(fit["r_squared"], 1.0)

    def test_flat_line_zero_slope(self):
        fit = _linear_regression([0, 1, 2, 3], [5, 5, 5, 5])
        self.assertAlmostEqual(fit["slope"], 0.0)

    def test_degenerate_single_x_value(self):
        fit = _linear_regression([5, 5, 5], [1, 2, 3])
        self.assertEqual(fit["slope"], 0.0)


class TestForecastSeries(unittest.TestCase):
    def test_too_few_points(self):
        dates = [datetime.date(2026, 1, 1), datetime.date(2026, 1, 2)]
        res = _forecast_series(dates, [1.0, 2.0], periods_ahead=2)
        self.assertIn("error", res)

    def test_perfect_linear_series_projects_correctly(self):
        dates = [datetime.date(2026, 1, i) for i in range(1, 6)]
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        res = _forecast_series(dates, values, periods_ahead=2)
        self.assertTrue(res["success"])
        self.assertEqual(res["trend_direction"], "increasing")
        self.assertEqual(res["fit_confidence"], "strong")
        self.assertAlmostEqual(res["fit_quality_r_squared"], 1.0)
        self.assertEqual(len(res["projections"]), 2)
        self.assertAlmostEqual(res["projections"][0]["projected_value"], 60.0)
        self.assertAlmostEqual(res["projections"][1]["projected_value"], 70.0)
        self.assertEqual(res["projections"][0]["date"], "2026-01-06")

    def test_decreasing_trend_direction(self):
        dates = [datetime.date(2026, 1, i) for i in range(1, 6)]
        values = [50.0, 40.0, 30.0, 20.0, 10.0]
        res = _forecast_series(dates, values, periods_ahead=1)
        self.assertEqual(res["trend_direction"], "decreasing")

    def test_noisy_data_gives_weak_or_moderate_confidence(self):
        dates = [datetime.date(2026, 1, i) for i in range(1, 8)]
        values = [10.0, 45.0, 12.0, 40.0, 15.0, 38.0, 11.0]
        res = _forecast_series(dates, values, periods_ahead=1)
        self.assertIn(res["fit_confidence"], ("weak", "moderate"))

    def test_unsorted_input_is_sorted_internally(self):
        dates = [datetime.date(2026, 1, 3), datetime.date(2026, 1, 1), datetime.date(2026, 1, 2)]
        values = [30.0, 10.0, 20.0]
        res = _forecast_series(dates, values, periods_ahead=1)
        self.assertEqual(res["date_range"]["start"], "2026-01-01")
        self.assertEqual(res["date_range"]["end"], "2026-01-03")


class TestForecastTrendTool(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = forecast_trend("layer", "date", "value")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestNormalizeMinmax(unittest.TestCase):
    def test_scales_to_zero_one(self):
        norm, had_variation = _normalize_minmax([10, 50, 90])
        self.assertEqual(norm, [0.0, 0.5, 1.0])
        self.assertTrue(had_variation)

    def test_invert_flips_so_higher_raw_means_lower_severity(self):
        # % of population WITH water access: 100 is the best-off unit, so it
        # must normalize to 0 severity, not 1.
        norm, _ = _normalize_minmax([100, 50, 0], invert=True)
        self.assertEqual(norm, [0.0, 0.5, 1.0])

    def test_no_variation_reported_not_silently_scored(self):
        norm, had_variation = _normalize_minmax([7, 7, 7])
        self.assertEqual(norm, [0.0, 0.0, 0.0])
        self.assertFalse(had_variation)

    def test_zscore_then_rescale_would_be_identical_to_minmax(self):
        # Documents why no "z-score" method option is offered: z = (x-mean)/std
        # is affine, so rescaling z-scores to 0-1 for the composite collapses
        # to exactly min-max on the raw values. Offering it as a distinct
        # choice would imply a difference in the result that doesn't exist.
        import statistics as st
        values = [3.0, 7.0, 11.0, 40.0]
        direct, _ = _normalize_minmax(values)
        mean, sd = st.mean(values), st.pstdev(values)
        via_z, _ = _normalize_minmax([(v - mean) / sd for v in values])
        for a, b in zip(direct, via_z):
            self.assertAlmostEqual(a, b, places=9)


class TestSeverityClass(unittest.TestCase):
    def test_equal_interval_boundaries(self):
        self.assertEqual(_severity_class(0.0), 1)
        self.assertEqual(_severity_class(0.19), 1)
        self.assertEqual(_severity_class(0.2), 2)
        self.assertEqual(_severity_class(0.5), 3)
        self.assertEqual(_severity_class(0.79), 4)
        self.assertEqual(_severity_class(0.8), 5)

    def test_top_of_range_does_not_overflow_to_class_six(self):
        self.assertEqual(_severity_class(1.0), 5)


class TestComputeSeverityIndex(unittest.TestCase):
    def _rows(self):
        return [
            {"unit": "A", "food_insec": 10, "water_pct": 100},
            {"unit": "B", "food_insec": 50, "water_pct": 50},
            {"unit": "C", "food_insec": 90, "water_pct": 0},
        ]

    def test_hand_verified_scores_and_classes(self):
        # Worked by hand: food_insec minmax -> 0.0/0.5/1.0; water_pct inverted
        # -> 0.0/0.5/1.0; equal weights 0.5 each -> 0.0/0.5/1.0 composite,
        # classes 1/3/5.
        res = _compute_severity_index(
            self._rows(), ["food_insec", "water_pct"], invert_indicators=["water_pct"]
        )
        got = {r["unit"]: (r["severity_score"], r["severity_class"]) for r in res["results"]}
        self.assertEqual(got, {"A": (0.0, 1), "B": (0.5, 3), "C": (1.0, 5)})

    def test_results_ranked_worst_first(self):
        res = _compute_severity_index(
            self._rows(), ["food_insec", "water_pct"], invert_indicators=["water_pct"]
        )
        self.assertEqual([r["unit"] for r in res["results"]], ["C", "B", "A"])

    def test_forgetting_to_invert_silently_cancels_the_indicators(self):
        # Guards the reason invert_indicators exists at all: these two fields
        # are perfectly anti-correlated, so without inversion every unit scores
        # an identical 0.5 -- a uniform, useless ranking that still looks like
        # a valid result.
        res = _compute_severity_index(self._rows(), ["food_insec", "water_pct"])
        self.assertEqual({r["severity_score"] for r in res["results"]}, {0.5})

    def test_weights_are_relative_and_normalized_to_sum_one(self):
        res = _compute_severity_index(
            self._rows(), ["food_insec", "water_pct"],
            weights={"food_insec": 3, "water_pct": 1}, invert_indicators=["water_pct"],
        )
        self.assertEqual(res["applied_weights"], {"food_insec": 0.75, "water_pct": 0.25})

    def test_units_missing_an_indicator_are_excluded_not_imputed(self):
        rows = self._rows() + [{"unit": "D", "food_insec": 20, "water_pct": None}]
        res = _compute_severity_index(rows, ["food_insec", "water_pct"], invert_indicators=["water_pct"])
        self.assertNotIn("D", [r["unit"] for r in res["results"]])
        self.assertEqual(res["excluded_units_missing_data"][0]["unit"], "D")
        self.assertEqual(res["excluded_units_missing_data"][0]["missing_fields"], ["water_pct"])

    def test_indicator_with_no_variation_is_reported(self):
        rows = [
            {"unit": "A", "a": 1, "flat": 5},
            {"unit": "B", "a": 9, "flat": 5},
        ]
        res = _compute_severity_index(rows, ["a", "flat"])
        self.assertEqual(res["indicators_with_no_variation"], ["flat"])

    def test_rejects_unknown_weight_or_invert_field_names(self):
        self.assertIn("error", _compute_severity_index(self._rows(), ["food_insec"], weights={"nope": 1}))
        self.assertIn("error", _compute_severity_index(self._rows(), ["food_insec"], invert_indicators=["nope"]))

    def test_rejects_degenerate_inputs(self):
        self.assertIn("error", _compute_severity_index([], ["a"]))
        self.assertIn("error", _compute_severity_index(self._rows(), []))
        self.assertIn("error", _compute_severity_index(self._rows(), ["food_insec"], weights={"food_insec": 0}))
        self.assertIn("error", _compute_severity_index(self._rows(), ["food_insec"], weights={"food_insec": -1}))

    def test_all_units_missing_data_is_an_error_not_an_empty_ranking(self):
        rows = [{"unit": "A", "x": None}, {"unit": "B", "x": None}]
        res = _compute_severity_index(rows, ["x"])
        self.assertIn("error", res)

    def test_method_is_stated_in_the_output(self):
        # An allocation input has to be able to explain itself.
        res = _compute_severity_index(self._rows(), ["food_insec"])
        self.assertIn("min-max", res["method"])


class TestCapEntries(unittest.TestCase):
    """Pure-Python, no QGIS -- caps an already worst-first-sorted list before
    it's returned to the model, so an uncapped one-entry-per-admin-unit
    result (routinely hundreds at ADM3) doesn't get resent on every
    remaining iteration of a turn and linger in conversation history for
    several turns afterward."""

    def test_under_limit_returned_unchanged_and_not_truncated(self):
        entries = list(range(5))
        capped, total, truncated = _cap_entries(entries, limit=10)
        self.assertEqual(capped, entries)
        self.assertEqual(total, 5)
        self.assertFalse(truncated)

    def test_over_limit_is_capped_and_flagged(self):
        entries = list(range(120))
        capped, total, truncated = _cap_entries(entries, limit=50)
        self.assertEqual(len(capped), 50)
        self.assertEqual(capped, entries[:50])
        self.assertEqual(total, 120)
        self.assertTrue(truncated)

    def test_exactly_at_limit_is_not_truncated(self):
        entries = list(range(50))
        capped, total, truncated = _cap_entries(entries, limit=50)
        self.assertEqual(capped, entries)
        self.assertFalse(truncated)

    def test_default_limit_matches_module_constant(self):
        entries = list(range(_MAX_RESULT_ENTRIES + 1))
        capped, total, truncated = _cap_entries(entries)
        self.assertEqual(len(capped), _MAX_RESULT_ENTRIES)
        self.assertTrue(truncated)


class TestComputeSeverityIndexResultCap(unittest.TestCase):
    """calculate_severity_index/calculate_presence_gap cap their returned
    results (see TestCapEntries) but _compute_severity_index itself -- the
    shared internal helper -- must NOT cap, since callers need the full
    scored list: calculate_presence_gap scans all of it for high-severity
    classes, and output_field write-back needs every unit's score, not just
    the top N that end up in a capped response."""

    def test_internal_helper_returns_uncapped_results(self):
        rows = [{"unit": f"unit-{i}", "a": float(i)} for i in range(_MAX_RESULT_ENTRIES + 10)]
        res = _compute_severity_index(rows, ["a"])
        self.assertEqual(len(res["results"]), _MAX_RESULT_ENTRIES + 10)
        self.assertEqual(res["scored_units"], _MAX_RESULT_ENTRIES + 10)


class TestCalculateSeverityIndexTool(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = calculate_severity_index("units", ["a", "b"], "name")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


def _fake_layer_with_fields(*field_names):
    """A minimal fake layer for the QGIS-008 gate tests below -- just enough surface
    (fields()/getFeatures()) for the gate to be reached; getFeatures() is never actually
    called when the gate fires first, since these tests all pass confirmed=False.
    `name` is a reserved MagicMock constructor kwarg (sets the mock's repr, not an
    attribute) -- field.name.return_value is set explicitly afterward instead."""
    layer = MagicMock()
    fields = []
    for n in field_names:
        f = MagicMock()
        f.name.return_value = n
        fields.append(f)
    layer.fields.return_value = fields
    return layer


class TestQgis008DestructiveOutputFieldGate(unittest.TestCase):
    """2026-09-13 audit (QGIS-008): the 4 composite-index tools write output_field into the
    layer's attribute table via the same provider.changeAttributeValues() mutation
    field_calculator/calculate_area/calculate_length already gate behind confirmation
    (BUG-2026-08-21-3) -- this was a real, confirmed inconsistency, not a duplicate of that
    earlier fix. Gated on output_field being requested specifically: a plain analysis call
    (no output_field) must stay fully ungated, since it never touches the layer."""

    def test_severity_index_gated_only_when_output_field_requested(self):
        layer = _fake_layer_with_fields("a", "b", "name")
        with patch.object(analysis_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(analysis_tools_mod, "_find_layer_by_name", return_value=layer):
            gated = calculate_severity_index("units", ["a", "b"], "name", output_field="score", confirmed=False)
            self.assertEqual(gated.get("status"), "PREVIEW_REQUIRED")
            self.assertTrue(gated.get("requires_confirmation"))
            self.assertEqual(gated["arguments"]["confirmed"], True)

            ungated = calculate_severity_index("units", ["a", "b"], "name")
            self.assertNotEqual(ungated.get("status"), "PREVIEW_REQUIRED")

    def test_presence_gap_gated_only_when_output_field_requested(self):
        layer = _fake_layer_with_fields("a", "b", "name")
        with patch.object(analysis_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(analysis_tools_mod, "_find_layer_by_name", return_value=layer):
            gated = calculate_presence_gap(
                "units", ["a", "b"], "name", "3w.csv", "district", "org", output_field="gap_status", confirmed=False
            )
            self.assertEqual(gated.get("status"), "PREVIEW_REQUIRED")

            # No output_field -- the file doesn't exist, but that's a DIFFERENT (later)
            # validation than the gate; confirms the gate itself isn't what's blocking it.
            ungated = calculate_presence_gap("units", ["a", "b"], "name", "3w.csv", "district", "org")
            self.assertNotEqual(ungated.get("status"), "PREVIEW_REQUIRED")

    def test_population_in_need_gated_only_when_output_field_requested(self):
        layer = _fake_layer_with_fields("a", "b", "name")
        with patch.object(analysis_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(analysis_tools_mod, "_find_layer_by_name", return_value=layer):
            gated = calculate_population_in_need(
                "units", ["a", "b"], "name", "pop_raster", output_field="pop", confirmed=False
            )
            self.assertEqual(gated.get("status"), "PREVIEW_REQUIRED")

    def test_damage_exposure_severity_gated_only_when_output_field_requested(self):
        admin = _fake_layer_with_fields("name")
        footprints = MagicMock()

        def fake_find(n):
            return footprints if n == "footprints" else admin

        with patch.object(analysis_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(analysis_tools_mod, "_find_layer_by_name", side_effect=fake_find):
            gated = calculate_damage_exposure_severity(
                "units", "name", "before", "after", "footprints", output_field="dmg", confirmed=False
            )
            self.assertEqual(gated.get("status"), "PREVIEW_REQUIRED")

    def test_dispatcher_schema_filtering_prevents_bypass_for_severity_index(self):
        """Same protection field_calculator/calculate_area already have (test_new_tools.py's
        test_dispatcher_schema_filtering_prevents_bypass): confirmed isn't in this tool's
        declared JSON schema, so the dispatcher strips a model-injected confirmed=True
        before it ever reaches the function -- only a real UI confirm click (which injects
        it AFTER schema filtering, via user_confirmed) can actually set it."""
        from cartogen_ai.core.agent.agent import CartogenAi
        layer = _fake_layer_with_fields("a", "b", "name")
        with patch.object(analysis_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(analysis_tools_mod, "_find_layer_by_name", return_value=layer):
            agent = CartogenAi()
            res = agent._real_execute_tool(
                "calculate_severity_index",
                {"layer_name": "units", "indicator_fields": ["a", "b"], "unit_name_field": "name",
                 "output_field": "score", "confirmed": True},
            )
        self.assertEqual(res.get("status"), "PREVIEW_REQUIRED")


class TestCalculatePresenceGapTool(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = calculate_presence_gap("units", ["a", "b"], "name", "3w.csv", "district", "org")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_degrades_gracefully_outside_qgis_with_output_field(self):
        res = calculate_presence_gap("units", ["a", "b"], "name", "3w.csv", "district", "org", output_field="gap_status")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestCalculatePopulationInNeedTool(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = calculate_population_in_need("units", ["a", "b"], "name", "worldpop")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_degrades_gracefully_outside_qgis_with_output_field(self):
        res = calculate_population_in_need("units", ["a", "b"], "name", "worldpop", output_field="pop_in_need")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_degrades_gracefully_outside_qgis_with_high_severity_classes(self):
        res = calculate_population_in_need("units", ["a", "b"], "name", "worldpop", high_severity_classes=[3, 4, 5])
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestCalculateDamageExposureSeverityTool(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = calculate_damage_exposure_severity("units", "name", "before", "after", "footprints")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_degrades_gracefully_outside_qgis_with_hazard_intensity(self):
        res = calculate_damage_exposure_severity(
            "units", "name", "before", "after", "footprints", hazard_intensity_raster="shake_intensity"
        )
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_degrades_gracefully_outside_qgis_with_output_field(self):
        res = calculate_damage_exposure_severity(
            "units", "name", "before", "after", "footprints", output_field="damage_score"
        )
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestBucketDatesByPeriod(unittest.TestCase):
    def test_all_dates_in_one_period(self):
        dates = [datetime.date(2026, 1, 1), datetime.date(2026, 1, 10), datetime.date(2026, 1, 20)]
        first, last, num_periods, indices = _bucket_dates_by_period(dates, 30)
        self.assertEqual(first, datetime.date(2026, 1, 1))
        self.assertEqual(last, datetime.date(2026, 1, 20))
        self.assertEqual(num_periods, 1)
        self.assertEqual(indices, [0, 0, 0])

    def test_spans_multiple_periods(self):
        dates = [datetime.date(2026, 1, 1), datetime.date(2026, 1, 15), datetime.date(2026, 2, 10), datetime.date(2026, 3, 5)]
        first, last, num_periods, indices = _bucket_dates_by_period(dates, 30)
        self.assertEqual(num_periods, 3)
        self.assertEqual(indices, [0, 0, 1, 2])

    def test_unsorted_input_still_finds_correct_first_last(self):
        dates = [datetime.date(2026, 3, 5), datetime.date(2026, 1, 1), datetime.date(2026, 2, 10)]
        first, last, num_periods, indices = _bucket_dates_by_period(dates, 30)
        self.assertEqual(first, datetime.date(2026, 1, 1))
        self.assertEqual(last, datetime.date(2026, 3, 5))

    def test_single_date(self):
        dates = [datetime.date(2026, 1, 1)]
        first, last, num_periods, indices = _bucket_dates_by_period(dates, 30)
        self.assertEqual(num_periods, 1)
        self.assertEqual(indices, [0])

    def test_boundary_falls_into_next_period(self):
        # exactly period_days apart -- the period_days'th day starts a new bucket
        dates = [datetime.date(2026, 1, 1), datetime.date(2026, 1, 31)]
        first, last, num_periods, indices = _bucket_dates_by_period(dates, 30)
        self.assertEqual(indices, [0, 1])
        self.assertEqual(num_periods, 2)


class TestAnalyzeIncidentTrendTool(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = analyze_incident_trend("incidents", "date", "zones", "name")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_degrades_gracefully_outside_qgis_with_custom_periods(self):
        res = analyze_incident_trend("incidents", "date", "zones", "name", period_days=7, periods_ahead=2)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


def _fake_feature(field_values, geom_is_empty=False):
    """Minimal fake QgsFeature: supports feat[field] item access and
    feat.geometry(); id() defaults to a fresh MagicMock identity."""
    feat = MagicMock()
    feat.__getitem__.side_effect = lambda k: field_values[k]
    geom = MagicMock()
    geom.isEmpty.return_value = geom_is_empty
    feat.geometry.return_value = geom
    return feat


class TestAnalyzeIncidentTrendPerf003IndexReuse(unittest.TestCase):
    """PERF-003, 2026-09-13 audit: analyze_incident_trend used to call
    _count_points_in_polygons(zones, ...) once per time bucket, rebuilding the same
    QgsSpatialIndex + feature-id map against the unchanged zones layer every time. Now
    builds it once (_build_polygon_index) and reuses it across buckets
    (_count_points_in_polygons_indexed). qgis.core isn't importable in this sandbox, so
    both helpers are mocked rather than exercised for real -- this test verifies the
    CALL PATTERN (index built once, not once per bucket), which is exactly what the
    performance bug was."""

    def test_builds_index_once_regardless_of_bucket_count(self):
        point_layer = MagicMock()
        point_layer.fields.return_value = [MagicMock(**{"name.return_value": "date"})]
        # 4 points, each 30 days apart -- period_days=30 puts each in its own bucket,
        # so 4 distinct buckets get counted, but the index must still build only once.
        base = datetime.date(2026, 1, 1)
        points = [
            _fake_feature({"date": (base + datetime.timedelta(days=30 * i)).isoformat()})
            for i in range(4)
        ]
        point_layer.getFeatures.return_value = points

        zone_layer = MagicMock()
        zone_layer.fields.return_value = [MagicMock(**{"name.return_value": "name"})]
        zone_feat = _fake_feature({"name": "Zone A"})
        zone_feat.id.return_value = 1
        zone_layer.getFeatures.return_value = [zone_feat]

        def fake_find(n):
            return point_layer if n == "incidents" else zone_layer

        with patch.object(analysis_tools_mod, "QGIS_AVAILABLE", True), \
             patch.object(analysis_tools_mod, "_find_layer_by_name", side_effect=fake_find), \
             patch.object(analysis_tools_mod, "_build_polygon_index", return_value=("idx", {1: zone_feat})) as mock_build, \
             patch.object(analysis_tools_mod, "_count_points_in_polygons_indexed", return_value={1: 0}) as mock_count:
            res = analyze_incident_trend("incidents", "date", "zones", "name", period_days=30)

        self.assertNotIn("error", res)
        mock_build.assert_called_once_with(zone_layer)
        self.assertEqual(mock_count.call_count, 4)
        for call in mock_count.call_args_list:
            self.assertEqual(call.args[0], "idx")
            self.assertEqual(call.args[1], {1: zone_feat})


if __name__ == "__main__":
    unittest.main()
