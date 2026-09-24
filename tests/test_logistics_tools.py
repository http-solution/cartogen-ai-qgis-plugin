# -*- coding: utf-8 -*-
"""Tests for agent/tools/logistics_tools.py -- the Phase 3 humanitarian-ops
improvement (hub siting, service-area, travel-distance analysis), plus
location_allocation/optimize_delivery_route added in the ArcGIS-parity pass.
Follows the QGIS_AVAILABLE=False degrade-path convention used throughout the
suite."""
import math
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.tools.logistics_tools import (
    _rank_hub_candidates, optimal_hub_siting, calculate_service_area, travel_time_matrix,
    _greedy_p_median, location_allocation, _tsp_nearest_neighbor, _two_opt,
    _tour_length, _optimize_route, optimize_delivery_route, population_access_gap,
    score_route_incident_risk, _build_road_snapped_route, _network_direction_speed_params,
    _build_network_distance_matrix, _make_distance_area, _measure_distance,
    _network_geometry_error,
)


class TestMakeDistanceArea(unittest.TestCase):
    """QGIS-006 follow-up (2026-09-19): geographic-CRS layers previously measured distance
    in raw planar degrees -- _make_distance_area sets up real ellipsoidal (WGS84 geodesic)
    measurement instead, when the layer's CRS is geographic."""

    def test_projected_crs_returns_none(self):
        layer = MagicMock()
        layer.crs.return_value.isGeographic.return_value = False
        self.assertIsNone(_make_distance_area(layer))

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsDistanceArea", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    def test_geographic_crs_configures_a_distance_area(self, mock_project, mock_da_cls):
        layer = MagicMock()
        layer.crs.return_value.isGeographic.return_value = True
        mock_project.instance.return_value.ellipsoid.return_value = "WGS84"
        da_instance = mock_da_cls.return_value

        result = _make_distance_area(layer)

        self.assertIs(result, da_instance)
        da_instance.setSourceCrs.assert_called_once()
        da_instance.setEllipsoid.assert_called_once_with("WGS84")

    def test_exception_during_setup_returns_none(self):
        layer = MagicMock()
        layer.crs.side_effect = RuntimeError("boom")
        self.assertIsNone(_make_distance_area(layer))

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsDistanceArea", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    def test_project_ellipsoid_none_sentinel_falls_back_to_wgs84(self, mock_project, mock_da_cls):
        """Live-caught 2026-09-19 (real QGIS 4.2.2): a fresh/default
        QgsProject.instance().ellipsoid() returns the literal string 'NONE' -- QGIS's own
        sentinel meaning 'no ellipsoid configured, use planar Cartesian math' -- which is
        truthy in Python. An earlier version of this fix used `ellipsoid() or "WGS84"`,
        which never caught this because 'NONE' is a non-empty, truthy string -- silently
        leaving ellipsoidal mode OFF (measureLine returned the same wrong value as the old
        planar distance() call). Must explicitly check for the 'NONE' sentinel, not just
        falsiness."""
        layer = MagicMock()
        layer.crs.return_value.isGeographic.return_value = True
        mock_project.instance.return_value.ellipsoid.return_value = "NONE"
        da_instance = mock_da_cls.return_value

        _make_distance_area(layer)

        da_instance.setEllipsoid.assert_called_once_with("WGS84")

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsDistanceArea", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    def test_real_project_ellipsoid_is_used_when_set(self, mock_project, mock_da_cls):
        layer = MagicMock()
        layer.crs.return_value.isGeographic.return_value = True
        mock_project.instance.return_value.ellipsoid.return_value = "EPSG:7030"
        da_instance = mock_da_cls.return_value

        _make_distance_area(layer)

        da_instance.setEllipsoid.assert_called_once_with("EPSG:7030")


class TestMeasureDistance(unittest.TestCase):
    def test_none_distance_area_uses_planar_distance(self):
        geom_a, geom_b = MagicMock(), MagicMock()
        geom_a.distance.return_value = 42.0

        result = _measure_distance(None, geom_a, geom_b)

        self.assertEqual(result, 42.0)
        geom_a.distance.assert_called_once_with(geom_b)

    def test_distance_area_given_uses_ellipsoidal_measurement(self):
        distance_area = MagicMock()
        distance_area.measureLine.return_value = 123456.7
        geom_a, geom_b = MagicMock(), MagicMock()

        result = _measure_distance(distance_area, geom_a, geom_b)

        self.assertEqual(result, 123456.7)
        distance_area.measureLine.assert_called_once_with(geom_a.asPoint(), geom_b.asPoint())
        geom_a.distance.assert_not_called()

    def test_ellipsoidal_failure_falls_back_to_planar_distance(self):
        distance_area = MagicMock()
        distance_area.measureLine.side_effect = RuntimeError("boom")
        geom_a, geom_b = MagicMock(), MagicMock()
        geom_a.distance.return_value = 7.0

        result = _measure_distance(distance_area, geom_a, geom_b)

        self.assertEqual(result, 7.0)


class TestRankHubCandidates(unittest.TestCase):
    """Pure Python, no QGIS needed."""

    def test_lower_average_distance_ranks_first(self):
        ranked = _rank_hub_candidates({"A": [5, 10, 15], "B": [40, 50, 60]})
        self.assertEqual([r["candidate"] for r in ranked], ["A", "B"])
        self.assertEqual(ranked[0]["avg_distance"], 10.0)

    def test_reports_served_count_within_max_distance(self):
        ranked = _rank_hub_candidates({"A": [5, 10, 15]}, max_distance=12)
        self.assertEqual(ranked[0]["demand_points_served"], 2)
        self.assertAlmostEqual(ranked[0]["demand_points_served_percent"], 66.7, places=1)

    def test_omits_served_fields_when_max_distance_not_given(self):
        ranked = _rank_hub_candidates({"A": [5, 10]})
        self.assertNotIn("demand_points_served", ranked[0])

    def test_skips_candidates_with_no_distances(self):
        ranked = _rank_hub_candidates({"A": [5, 10], "B": []})
        self.assertEqual([r["candidate"] for r in ranked], ["A"])


class TestLogisticsToolsDegradeOutsideQgis(unittest.TestCase):
    def test_optimal_hub_siting_degrades(self):
        res = optimal_hub_siting("candidates", "demand")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_calculate_service_area_degrades(self):
        res = calculate_service_area("facilities", "roads", 1000)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_travel_time_matrix_degrades(self):
        res = travel_time_matrix("origins", "destinations", "roads")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_population_access_gap_degrades(self):
        res = population_access_gap("facilities", "roads", "pop_raster", "districts", 1000)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestLogisticsToolsValidation(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    def test_calculate_service_area_rejects_non_positive_travel_cost(self):
        # Validated before any layer lookup, so this doesn't need QGIS mocks.
        res = calculate_service_area("facilities", "roads", 0)
        self.assertIn("error", res)
        self.assertIn("travel_cost", res["error"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    def test_calculate_service_area_rejects_unknown_strategy(self):
        res = calculate_service_area("facilities", "roads", 1000, strategy="teleport")
        self.assertIn("error", res)
        self.assertIn("strategy", res["error"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_optimal_hub_siting_reports_missing_candidate_layer(self, mock_find):
        mock_find.return_value = None
        res = optimal_hub_siting("ghost_candidates", "demand")
        self.assertIn("error", res)
        self.assertIn("ghost_candidates", res["error"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_optimal_hub_siting_reports_missing_demand_layer(self, mock_find):
        def side_effect(name):
            return MagicMock() if name == "candidates" else None
        mock_find.side_effect = side_effect
        res = optimal_hub_siting("candidates", "ghost_demand")
        self.assertIn("error", res)
        self.assertIn("ghost_demand", res["error"])


class _LineNetworkMixin:
    """These tests pass a MagicMock as the road network, and QgsWkbTypes doesn't exist outside
    QGIS, so the line-geometry check (_network_geometry_error) is stubbed to "it's a line layer".
    That check has its own tests in TestNetworkGeometryGuard."""

    def setUp(self):
        super().setUp()
        p = patch("cartogen_ai.core.agent.tools.logistics_tools._network_geometry_error", return_value=None)
        p.start()
        self.addCleanup(p.stop)


class TestNetworkDirectionSpeedParams(unittest.TestCase):
    """Point 8 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md, per
    docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md section 2 item 1 -- wiring
    SPEED_FIELD/DIRECTION_FIELD through to the real processing algorithms
    instead of always using a flat DEFAULT_SPEED with no direction awareness."""

    def _network(self, existing_fields):
        network = MagicMock()
        network.fields.return_value.indexOf.side_effect = lambda name: 0 if name in existing_fields else -1
        return network

    def test_no_fields_given_returns_empty_extra_params(self):
        extra, error = _network_direction_speed_params(self._network([]))
        self.assertEqual(extra, {})
        self.assertIsNone(error)

    def test_speed_field_present_is_wired_through(self):
        extra, error = _network_direction_speed_params(self._network(["speed_kmh"]), speed_field="speed_kmh")
        self.assertIsNone(error)
        self.assertEqual(extra["SPEED_FIELD"], "speed_kmh")

    def test_speed_field_missing_reports_error(self):
        extra, error = _network_direction_speed_params(self._network([]), speed_field="ghost_field")
        self.assertIsNone(extra)
        self.assertIn("ghost_field", error)

    def test_direction_field_present_sets_default_osm_values(self):
        extra, error = _network_direction_speed_params(self._network(["oneway"]), direction_field="oneway")
        self.assertIsNone(error)
        self.assertEqual(extra["DIRECTION_FIELD"], "oneway")
        self.assertEqual(extra["VALUE_FORWARD"], "yes")
        self.assertEqual(extra["VALUE_BACKWARD"], "-1")
        self.assertEqual(extra["VALUE_BOTH"], "no")
        self.assertEqual(extra["DEFAULT_DIRECTION"], 2)

    def test_direction_field_missing_reports_error(self):
        extra, error = _network_direction_speed_params(self._network([]), direction_field="ghost_field")
        self.assertIsNone(extra)
        self.assertIn("ghost_field", error)

    def test_direction_field_values_are_overridable(self):
        extra, error = _network_direction_speed_params(
            self._network(["dir"]), direction_field="dir",
            value_forward="F", value_backward="B", value_both="T",
        )
        self.assertIsNone(error)
        self.assertEqual((extra["VALUE_FORWARD"], extra["VALUE_BACKWARD"], extra["VALUE_BOTH"]), ("F", "B", "T"))

    def test_both_fields_present_combine(self):
        extra, error = _network_direction_speed_params(
            self._network(["speed_kmh", "oneway"]), speed_field="speed_kmh", direction_field="oneway",
        )
        self.assertIsNone(error)
        self.assertIn("SPEED_FIELD", extra)
        self.assertIn("DIRECTION_FIELD", extra)


class TestCalculateServiceAreaNetworkParams(_LineNetworkMixin, unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_bad_speed_field_errors_before_touching_processing(self, mock_find):
        network = MagicMock()
        network.fields.return_value.indexOf.return_value = -1
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Warehouse"]), "roads": network}.get(name)

        res = calculate_service_area("facilities", "roads", 1000, speed_field="ghost_field")

        self.assertIn("error", res)
        self.assertIn("ghost_field", res["error"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_speed_and_direction_fields_reach_processing_run_and_result(
        self, mock_find, _mock_processing_enum, _mock_context_cls, mock_processing, mock_project
    ):
        network = MagicMock()
        network.fields.return_value.indexOf.side_effect = lambda name: 0 if name in ("speed_kmh", "oneway") else -1
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Warehouse"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        lines_layer.featureCount.return_value = 1
        hull_layer = MagicMock()

        def run_side_effect(alg_id, params, context=None):
            if alg_id == "native:serviceareafrompoint":
                self.assertEqual(params["SPEED_FIELD"], "speed_kmh")
                self.assertEqual(params["DIRECTION_FIELD"], "oneway")
                self.assertEqual(params["STRATEGY"], 1)  # 'fastest'
                return {"OUTPUT_LINES": lines_layer}
            if alg_id == "native:convexhull":
                return {"OUTPUT": hull_layer}
            raise AssertionError(f"unexpected alg_id {alg_id}")
        mock_processing.run.side_effect = run_side_effect

        res = calculate_service_area(
            "facilities", "roads", 30, strategy="fastest", speed_field="speed_kmh", direction_field="oneway",
        )

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["speed_field"], "speed_kmh")
        self.assertEqual(res["direction_field"], "oneway")

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_no_fields_given_omits_them_from_params_and_result(
        self, mock_find, _mock_processing_enum, _mock_context_cls, mock_processing, mock_project
    ):
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Warehouse"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        lines_layer.featureCount.return_value = 1
        hull_layer = MagicMock()

        def run_side_effect(alg_id, params, context=None):
            if alg_id == "native:serviceareafrompoint":
                self.assertNotIn("SPEED_FIELD", params)
                self.assertNotIn("DIRECTION_FIELD", params)
                return {"OUTPUT_LINES": lines_layer}
            if alg_id == "native:convexhull":
                return {"OUTPUT": hull_layer}
            raise AssertionError(f"unexpected alg_id {alg_id}")
        mock_processing.run.side_effect = run_side_effect

        res = calculate_service_area("facilities", "roads", 1000)

        self.assertTrue(res.get("success"), res)
        self.assertNotIn("speed_field", res)
        self.assertNotIn("direction_field", res)


class TestCalculateServiceAreaMultiBand(_LineNetworkMixin, unittest.TestCase):
    """v1.8.0 workstream 4: travel_cost as a list builds one combined,
    auto-styled isochrone/access-band polygon layer per facility (one ring
    per band value) instead of requiring N separate calls."""

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    def test_rejects_empty_list(self):
        res = calculate_service_area("facilities", "roads", [])
        self.assertIn("error", res)
        self.assertIn("travel_cost", res["error"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    def test_rejects_non_positive_value_in_list(self):
        res = calculate_service_area("facilities", "roads", [10, -5, 20])
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.apply_graduated_style")
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QVariant", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsVectorLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_builds_one_merged_layer_per_facility_and_auto_styles_it(
        self, mock_find, _mock_qgis_enum, _mock_context_cls, mock_processing, mock_project,
        mock_vector_layer_cls, mock_field_cls, mock_qvariant, mock_feature_cls, mock_apply_graduated,
    ):
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Warehouse"]), "roads": network}.get(name)

        # Two bands -> two lines_layer/hull_layer pairs.
        def make_lines_and_hull(band):
            lines_layer = MagicMock()
            lines_layer.featureCount.return_value = 1
            hull_layer = MagicMock()
            hull_feat = MagicMock()
            hull_feat.geometry.return_value = MagicMock(isEmpty=lambda: False)
            hull_layer.getFeatures.return_value = [hull_feat]
            return lines_layer, hull_layer

        pairs = {15.0: make_lines_and_hull(15.0), 30.0: make_lines_and_hull(30.0)}

        def run_side_effect(alg_id, params, context=None):
            if alg_id == "native:serviceareafrompoint":
                band = params["TRAVEL_COST2"]
                return {"OUTPUT_LINES": pairs[band][0]}
            if alg_id == "native:convexhull":
                # INPUT is whichever lines_layer was just passed in -- find its band.
                lines_layer = params["INPUT"]
                for band, (ll, hl) in pairs.items():
                    if ll is lines_layer:
                        return {"OUTPUT": hl}
                raise AssertionError("unmatched lines_layer")
            raise AssertionError(f"unexpected alg_id {alg_id}")
        mock_processing.run.side_effect = run_side_effect

        merged_layer_mock = MagicMock()
        mock_vector_layer_cls.return_value = merged_layer_mock

        res = calculate_service_area("facilities", "roads", [15, 30])

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["travel_cost"], [15.0, 30.0])
        self.assertIn("facilities_service_area_bands_0", res["layers_created"])
        # Two band hulls, one feature each -> addFeatures called with 2 features.
        add_features_calls = merged_layer_mock.dataProvider().addFeatures.call_args_list
        self.assertEqual(len(add_features_calls), 1)
        self.assertEqual(len(add_features_calls[0][0][0]), 2)
        # Auto-styled via the real apply_graduated_style, on the merged layer's name and field.
        mock_apply_graduated.assert_called_once_with("facilities_service_area_bands_0", "travel_cost_band")

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.apply_graduated_style")
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_scalar_travel_cost_never_calls_auto_style(
        self, mock_find, _mock_qgis_enum, _mock_context_cls, mock_processing, mock_project, mock_apply_graduated,
    ):
        # Regression guard: the pre-existing single-band path must be
        # completely unaffected by the multi-band addition -- no merge, no
        # auto-styling call, exact original layer-naming behavior.
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Warehouse"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        lines_layer.featureCount.return_value = 1
        hull_layer = MagicMock()

        def run_side_effect(alg_id, params, context=None):
            if alg_id == "native:serviceareafrompoint":
                return {"OUTPUT_LINES": lines_layer}
            if alg_id == "native:convexhull":
                return {"OUTPUT": hull_layer}
            raise AssertionError(f"unexpected alg_id {alg_id}")
        mock_processing.run.side_effect = run_side_effect

        res = calculate_service_area("facilities", "roads", 1000)

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["travel_cost"], 1000)
        self.assertEqual(res["layers_created"], ["facilities_service_area_lines_0", "facilities_service_area_0"])
        mock_apply_graduated.assert_not_called()


class TestCalculateServiceAreaDegenerateNetworkIsolation(_LineNetworkMixin, unittest.TestCase):
    """BUG-2026-09-05-2: a small/degenerate road network can make either
    native:serviceareafrompoint or native:convexhull raise for one facility --
    that must no longer abort the whole multi-facility call. Mocked reproduction
    of the two exact error shapes recorded in docs/BUG_TRACKER.md; this sandbox has
    no live QGIS to re-run the original real-QGIS reproduction against, so this
    covers the fix's logic, not a live re-verification of the underlying QGIS
    behavior itself.

    2026-09-10: both failure shapes now have an actual fix attempted, not just
    isolation -- see logistics_tools._degenerate_hull_fallback and the
    QgsProcessingContext/GeometrySkipInvalid wiring in calculate_service_area
    itself. The first test below (unchanged from 2026-09-08) still exercises the
    isolation-only safety net: QgsGeometry/QgsVectorLayer/QgsFeature are not
    mocked in this sandbox, so _degenerate_hull_fallback's own NameError is
    caught by its blanket except-clause and it returns None here, same
    end-to-end outcome as before the fallback existed. The new tests further
    below (TestDegenerateHullFallback, and
    test_convexhull_failure_recovers_via_degenerate_hull_fallback) mock those
    QGIS geometry classes directly to verify the fallback's actual logic and its
    wiring into calculate_service_area."""

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_convexhull_failure_on_one_facility_keeps_its_lines_and_the_other_facility(
        self, mock_find, _mock_processing_enum, _mock_context_cls, mock_processing, mock_project
    ):
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Degenerate", "Normal"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        lines_layer.featureCount.return_value = 1
        hull_layer = MagicMock()

        def run_side_effect(alg_id, params, context=None):
            if alg_id == "native:serviceareafrompoint":
                return {"OUTPUT_LINES": lines_layer}
            if alg_id == "native:convexhull":
                # First facility's reachable network is collinear -- convexhull's own
                # Polygon-typed sink refuses the resulting LineString, exactly as
                # BUG-2026-09-05-2 recorded against real QGIS.
                if params["INPUT"] is lines_layer and not hasattr(run_side_effect, "_called_once"):
                    run_side_effect._called_once = True
                    raise RuntimeError(
                        "Could not add feature with geometry type LineString to layer of type Polygon"
                    )
                return {"OUTPUT": hull_layer}
            raise AssertionError(f"unexpected alg_id {alg_id}")
        mock_processing.run.side_effect = run_side_effect

        res = calculate_service_area("facilities", "roads", 1000)

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["facility_count"], 2)
        self.assertIn("skipped", res)
        self.assertEqual(len(res["skipped"]), 1)
        self.assertEqual(res["skipped"][0]["stage"], "convexhull")
        self.assertIn("warnings", res)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_serviceareafrompoint_failure_on_one_facility_does_not_abort_the_other(
        self, mock_find, _mock_processing_enum, _mock_context_cls, mock_processing, mock_project
    ):
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Degenerate", "Normal"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        lines_layer.featureCount.return_value = 1
        hull_layer = MagicMock()
        calls = {"count": 0}

        def run_side_effect(alg_id, params, context=None):
            if alg_id == "native:serviceareafrompoint":
                calls["count"] += 1
                if calls["count"] == 1:
                    # L-shaped 2-segment network -- native:serviceareafrompoint itself
                    # raises on invalid intermediate geometry, per BUG-2026-09-05-2.
                    raise RuntimeError(
                        "Feature has invalid geometry. Please fix the geometry or change "
                        "the 'Invalid features filtering' option."
                    )
                return {"OUTPUT_LINES": lines_layer}
            if alg_id == "native:convexhull":
                return {"OUTPUT": hull_layer}
            raise AssertionError(f"unexpected alg_id {alg_id}")
        mock_processing.run.side_effect = run_side_effect

        res = calculate_service_area("facilities", "roads", 1000)

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["facility_count"], 1)
        self.assertEqual(res["skipped"][0]["stage"], "serviceareafrompoint")

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_all_facilities_failing_still_reports_a_clean_error(
        self, mock_find, _mock_processing_enum, _mock_context_cls, mock_processing, mock_project
    ):
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Degenerate"]), "roads": network}.get(name)

        def run_side_effect(alg_id, params, context=None):
            raise RuntimeError("invalid geometry")
        mock_processing.run.side_effect = run_side_effect

        res = calculate_service_area("facilities", "roads", 1000)

        self.assertIn("error", res)
        self.assertNotIn("success", res)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.logistics_tools._degenerate_hull_fallback")
    def test_convexhull_failure_recovers_via_degenerate_hull_fallback(
        self, mock_fallback, mock_find, _mock_processing_enum, _mock_context_cls, mock_processing, mock_project
    ):
        """2026-09-10 fix: when native:convexhull raises the recorded LineString-
        into-Polygon-sink error, _degenerate_hull_fallback is invoked and, if it
        returns a usable layer, that facility is fully served -- no 'skipped'
        entry, hull layer registered like any successful facility. Mocks the
        fallback itself directly since its own internals (QgsGeometry etc.) are
        covered separately by TestDegenerateHullFallback."""
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Degenerate"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        lines_layer.featureCount.return_value = 1
        recovered_hull_layer = MagicMock()
        mock_fallback.return_value = recovered_hull_layer

        def run_side_effect(alg_id, params, context=None):
            if alg_id == "native:serviceareafrompoint":
                return {"OUTPUT_LINES": lines_layer}
            if alg_id == "native:convexhull":
                raise RuntimeError(
                    "Could not add feature with geometry type LineString to layer of type Polygon"
                )
            raise AssertionError(f"unexpected alg_id {alg_id}")
        mock_processing.run.side_effect = run_side_effect

        res = calculate_service_area("facilities", "roads", 1000)

        mock_fallback.assert_called_once_with(lines_layer, 1000)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["facility_count"], 1)
        self.assertNotIn("skipped", res)
        mock_project.instance.return_value.addMapLayer.assert_any_call(recovered_hull_layer)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_serviceareafrompoint_gets_a_geometry_skip_invalid_context(
        self, mock_find, mock_processing_enum, mock_context_cls, mock_processing, mock_project
    ):
        """2026-09-10 fix: serviceareafrompoint's own 'invalid geometry' abort is
        the exact failure the error message names its own remedy for ('change
        the Invalid features filtering option') -- confirm calculate_service_area
        actually asks for that remedy via QgsProcessingContext.setInvalidGeometryCheck
        rather than just isolating the failure after the fact."""
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Warehouse"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        lines_layer.featureCount.return_value = 1
        hull_layer = MagicMock()
        mock_context_instance = mock_context_cls.return_value

        def run_side_effect(alg_id, params, context=None):
            if alg_id == "native:serviceareafrompoint":
                self.assertIs(context, mock_context_instance)
                return {"OUTPUT_LINES": lines_layer}
            if alg_id == "native:convexhull":
                return {"OUTPUT": hull_layer}
            raise AssertionError(f"unexpected alg_id {alg_id}")
        mock_processing.run.side_effect = run_side_effect

        res = calculate_service_area("facilities", "roads", 1000)

        self.assertTrue(res.get("success"), res)
        mock_context_instance.setInvalidGeometryCheck.assert_called_once_with(
            mock_processing_enum.InvalidGeometryCheck.GeometrySkipInvalid
        )


class TestDegenerateHullFallback(unittest.TestCase):
    """Direct unit tests for _degenerate_hull_fallback, the 2026-09-10
    BUG-2026-09-05-2 fix helper. Mocks QgsGeometry/QgsWkbTypes/QgsVectorLayer/
    QgsFeature directly (they are real QGIS classes not otherwise exercised by
    this sandbox's degrade-path tests) to verify the actual geometry-handling
    logic, not just that calculate_service_area calls this function."""

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsVectorLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsGeometry", create=True)
    def test_degenerate_line_hull_is_buffered_into_a_polygon(
        self, mock_qgsgeometry, mock_wkbtypes, mock_vectorlayer_cls, mock_feature_cls
    ):
        from cartogen_ai.core.agent.tools.logistics_tools import _degenerate_hull_fallback

        feat = MagicMock()
        feat.geometry.return_value.isEmpty.return_value = False
        lines_layer = MagicMock()
        lines_layer.getFeatures.return_value = [feat]
        lines_layer.crs.return_value.authid.return_value = "EPSG:4326"

        combined = MagicMock()
        combined.isEmpty.return_value = False
        mock_qgsgeometry.unaryUnion.return_value = combined

        degenerate_hull = MagicMock()
        degenerate_hull.isEmpty.return_value = False
        combined.convexHull.return_value = degenerate_hull

        buffered_polygon = MagicMock()
        buffered_polygon.isEmpty.return_value = False
        buffered_polygon.type.return_value = mock_wkbtypes.GeometryType.PolygonGeometry
        degenerate_hull.buffer.return_value = buffered_polygon

        # First .type() check (on the raw hull) says it's NOT a polygon --
        # trigger the buffer path; the buffered result's .type() (checked again
        # after buffering) says it now IS one.
        degenerate_hull.type.return_value = "not-a-polygon-type"

        result = _degenerate_hull_fallback(lines_layer, travel_cost=1000)

        combined.convexHull.assert_called_once()
        degenerate_hull.buffer.assert_called_once()
        mock_vectorlayer_cls.assert_called_once_with("Polygon?crs=EPSG:4326", "service_area_hull", "memory")
        mock_feature_cls.return_value.setGeometry.assert_called_once_with(buffered_polygon)
        self.assertIsNotNone(result)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsVectorLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsGeometry", create=True)
    def test_hull_already_polygon_is_used_without_buffering(
        self, mock_qgsgeometry, mock_wkbtypes, mock_vectorlayer_cls, mock_feature_cls
    ):
        from cartogen_ai.core.agent.tools.logistics_tools import _degenerate_hull_fallback

        feat = MagicMock()
        feat.geometry.return_value.isEmpty.return_value = False
        lines_layer = MagicMock()
        lines_layer.getFeatures.return_value = [feat]
        lines_layer.crs.return_value.authid.return_value = "EPSG:4326"

        combined = MagicMock()
        combined.isEmpty.return_value = False
        mock_qgsgeometry.unaryUnion.return_value = combined

        polygon_hull = MagicMock()
        polygon_hull.isEmpty.return_value = False
        polygon_hull.type.return_value = mock_wkbtypes.GeometryType.PolygonGeometry
        combined.convexHull.return_value = polygon_hull

        result = _degenerate_hull_fallback(lines_layer, travel_cost=1000)

        polygon_hull.buffer.assert_not_called()
        self.assertIsNotNone(result)

    def test_no_usable_geometry_returns_none(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _degenerate_hull_fallback

        empty_geom = MagicMock()
        empty_geom.isEmpty.return_value = True
        feat = MagicMock()
        feat.geometry.return_value = empty_geom
        lines_layer = MagicMock()
        lines_layer.getFeatures.return_value = [feat]

        result = _degenerate_hull_fallback(lines_layer, travel_cost=1000)

        self.assertIsNone(result)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsGeometry", create=True)
    def test_exception_during_hull_computation_returns_none_not_raises(self, mock_qgsgeometry):
        from cartogen_ai.core.agent.tools.logistics_tools import _degenerate_hull_fallback

        feat = MagicMock()
        feat.geometry.return_value.isEmpty.return_value = False
        lines_layer = MagicMock()
        lines_layer.getFeatures.return_value = [feat]
        mock_qgsgeometry.unaryUnion.side_effect = RuntimeError("boom")

        result = _degenerate_hull_fallback(lines_layer, travel_cost=1000)

        self.assertIsNone(result)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsVectorLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsGeometry", create=True)
    def test_buffer_still_degenerate_returns_none(
        self, mock_qgsgeometry, mock_wkbtypes, mock_vectorlayer_cls, mock_feature_cls
    ):
        """Extreme edge case: even the buffered result fails to become a real
        polygon (e.g. a zero-length degenerate geometry). Must not fabricate a
        layer from it."""
        from cartogen_ai.core.agent.tools.logistics_tools import _degenerate_hull_fallback

        feat = MagicMock()
        feat.geometry.return_value.isEmpty.return_value = False
        lines_layer = MagicMock()
        lines_layer.getFeatures.return_value = [feat]

        combined = MagicMock()
        combined.isEmpty.return_value = False
        mock_qgsgeometry.unaryUnion.return_value = combined

        degenerate_hull = MagicMock()
        degenerate_hull.isEmpty.return_value = False
        degenerate_hull.type.return_value = "not-a-polygon-type"
        combined.convexHull.return_value = degenerate_hull

        still_bad_buffer = MagicMock()
        still_bad_buffer.isEmpty.return_value = True
        degenerate_hull.buffer.return_value = still_bad_buffer

        result = _degenerate_hull_fallback(lines_layer, travel_cost=1000)

        self.assertIsNone(result)
        mock_vectorlayer_cls.assert_not_called()


class TestTravelTimeMatrixNetworkParams(_LineNetworkMixin, unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    def test_rejects_unknown_strategy(self):
        res = travel_time_matrix("origins", "destinations", "roads", strategy="teleport")
        self.assertIn("error", res)
        self.assertIn("strategy", res["error"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_bad_direction_field_errors_before_touching_processing(self, mock_find):
        network = MagicMock()
        network.fields.return_value.indexOf.return_value = -1
        mock_find.side_effect = lambda name: {
            "origins": _stop_layer(["A"]), "destinations": _stop_layer(["B"]), "roads": network,
        }.get(name)

        res = travel_time_matrix("origins", "destinations", "roads", direction_field="ghost_field")

        self.assertIn("error", res)
        self.assertIn("ghost_field", res["error"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_default_strategy_is_shortest_and_fields_reach_processing_run(self, mock_find, mock_processing):
        network = MagicMock()
        network.fields.return_value.indexOf.side_effect = lambda name: 0 if name in ("speed_kmh", "oneway") else -1
        mock_find.side_effect = lambda name: {
            "origins": _stop_layer(["A"]), "destinations": _stop_layer(["B"]), "roads": network,
        }.get(name)

        result_layer = MagicMock()
        result_layer.fields.return_value = []
        result_layer.getFeatures.return_value = []

        def run_side_effect(alg_id, params, context=None):
            self.assertEqual(alg_id, "native:shortestpathpointtolayer")
            self.assertEqual(params["STRATEGY"], 0)  # default 'shortest'
            self.assertEqual(params["SPEED_FIELD"], "speed_kmh")
            self.assertEqual(params["DIRECTION_FIELD"], "oneway")
            return {"OUTPUT": result_layer}
        mock_processing.run.side_effect = run_side_effect

        res = travel_time_matrix("origins", "destinations", "roads", speed_field="speed_kmh", direction_field="oneway")

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["strategy"], "shortest")
        self.assertEqual(res["speed_field"], "speed_kmh")
        self.assertEqual(res["direction_field"], "oneway")

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_fastest_strategy_sets_strategy_1(self, mock_find, mock_processing):
        network = MagicMock()
        mock_find.side_effect = lambda name: {
            "origins": _stop_layer(["A"]), "destinations": _stop_layer(["B"]), "roads": network,
        }.get(name)

        result_layer = MagicMock()
        result_layer.fields.return_value = []
        result_layer.getFeatures.return_value = []

        def run_side_effect(alg_id, params, context=None):
            self.assertEqual(params["STRATEGY"], 1)
            return {"OUTPUT": result_layer}
        mock_processing.run.side_effect = run_side_effect

        res = travel_time_matrix("origins", "destinations", "roads", strategy="fastest")

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["strategy"], "fastest")


class TestPopulationAccessGapEstimateFields(unittest.TestCase):
    """Point 9 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md:
    population_access_gap's return should carry the same estimate/provenance
    fields as estimate_population_exposure (which it composes over), not a
    bare gap_population number restated as if it were a verified count. Mocks
    calculate_service_area, processing.run, and raster_tools's
    estimate_population_exposure directly rather than simulating real QGIS
    geometry -- population_access_gap already carries its own
    not-run-against-a-real-QGIS-session caveat in this module's docstring, and
    this test is only about the estimate-field propagation, not the
    geometry/network-analysis steps in between."""

    @patch("cartogen_ai.core.agent.tools.raster_tools.estimate_population_exposure")
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.logistics_tools.calculate_service_area")
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    def test_propagates_estimate_fields_from_population_exposure(
        self, mock_wkb, mock_calc_service_area, mock_find, mock_processing, mock_project, mock_estimate_pop,
    ):
        mock_wkb.geometryType.return_value = "polygon-sentinel"
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"

        area = MagicMock()
        hull = MagicMock()
        mock_find.side_effect = lambda name: {"districts": area, "Facilities_service_area_0": hull}.get(name)

        mock_calc_service_area.return_value = {
            "facility_count": 3,
            "layers_created": ["Facilities_service_area_0"],
        }

        reachable_mock = MagicMock()
        intersect_mock = MagicMock()
        intersect_mock.featureCount.return_value = 10
        mock_processing.run.side_effect = [
            {"OUTPUT": reachable_mock},
            {"OUTPUT": intersect_mock},
        ]

        mock_estimate_pop.side_effect = [
            {"success": True, "total_population": 1000.0, "pop_source": "WorldPop", "pop_reference_year": "2020"},
            {"success": True, "total_population": 400.0, "pop_source": "WorldPop", "pop_reference_year": "2020"},
        ]

        res = population_access_gap("Facilities", "roads", "YEM_population_2020", "districts", 1000)

        self.assertTrue(res.get("success"))
        self.assertEqual(res["total_population"], 1000.0)
        self.assertEqual(res["reachable_population"], 400.0)
        self.assertEqual(res["gap_population"], 600.0)
        self.assertEqual(res["gap_population_est"], 600.0)
        self.assertEqual(res["gap_percent"], 60.0)
        self.assertEqual(res["pop_source"], "WorldPop")
        self.assertEqual(res["pop_reference_year"], "2020")
        self.assertEqual(
            res["confidence"],
            "estimate (modeled network reachability + gridded population raster; not field-verified)",
        )


class TestOptimalHubSitingWithMockedLayers(unittest.TestCase):
    """Exercises the QGIS-touching wrapper around _rank_hub_candidates with
    fake feature/geometry objects, confirming the glue code (distance calls,
    attribute reads) is wired correctly end to end."""

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_ranks_candidates_by_mocked_geometry_distances(self, mock_find):
        # Two candidates, three demand points -- candidate at (0,0) is closer
        # on average than the one at (100,100).
        demand_layer = MagicMock()
        demand_feats = []
        for coord in [(1, 1), (2, 2), (3, 3)]:
            f = MagicMock()
            g = MagicMock()
            g.isEmpty.return_value = False
            f.geometry.return_value = g
            demand_feats.append(f)
        demand_layer.getFeatures.return_value = demand_feats

        candidates_layer = MagicMock()
        near_feat = MagicMock()
        near_geom = MagicMock()
        near_geom.isEmpty.return_value = False
        near_geom.distance.side_effect = [1.0, 2.0, 3.0]
        near_feat.geometry.return_value = near_geom
        near_feat.fields.return_value.count.return_value = 1
        near_feat.attribute.return_value = "near"

        far_feat = MagicMock()
        far_geom = MagicMock()
        far_geom.isEmpty.return_value = False
        far_geom.distance.side_effect = [100.0, 200.0, 300.0]
        far_feat.geometry.return_value = far_geom
        far_feat.fields.return_value.count.return_value = 1
        far_feat.attribute.return_value = "far"

        candidates_layer.getFeatures.return_value = [near_feat, far_feat]
        candidates_layer.featureCount.return_value = 2  # PERF-002 pair-count guard

        def side_effect(name):
            return {"candidates": candidates_layer, "demand": demand_layer}.get(name)
        mock_find.side_effect = side_effect

        res = optimal_hub_siting("candidates", "demand")

        self.assertTrue(res["success"])
        self.assertEqual(res["demand_point_count"], 3)
        self.assertEqual(res["ranked_candidates"][0]["candidate"], "near")
        self.assertEqual(res["ranked_candidates"][1]["candidate"], "far")

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_warns_when_candidate_layer_is_geographic(self, mock_find):
        """QGIS-006, 2026-09-13 audit: same CRS-unit-mismatch class buffer_analysis already
        warns about -- distances here are raw, unconverted CRS-unit values, degrees on a
        geographic CRS despite the tool's own docstring saying 'usually meters'."""
        demand_layer = MagicMock()
        g = MagicMock()
        g.isEmpty.return_value = False
        f = MagicMock()
        f.geometry.return_value = g
        demand_layer.getFeatures.return_value = [f]

        candidates_layer = MagicMock()
        cand_geom = MagicMock()
        cand_geom.isEmpty.return_value = False
        cand_geom.distance.return_value = 1.0
        cand_feat = MagicMock()
        cand_feat.geometry.return_value = cand_geom
        cand_feat.fields.return_value.count.return_value = 1
        cand_feat.attribute.return_value = "A"
        candidates_layer.getFeatures.return_value = [cand_feat]
        candidates_layer.featureCount.return_value = 1  # PERF-002 pair-count guard
        candidates_layer.crs.return_value.isGeographic.return_value = True
        candidates_layer.crs.return_value.authid.return_value = "EPSG:4326"

        mock_find.side_effect = lambda name: {"candidates": candidates_layer, "demand": demand_layer}.get(name)

        res = optimal_hub_siting("candidates", "demand")
        self.assertIn("warning", res)
        self.assertIn("DEGREES", res["warning"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsDistanceArea", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_geographic_crs_with_working_ellipsoidal_setup_gets_a_note_not_a_warning(
        self, mock_find, mock_project, mock_da_cls,
    ):
        """When ellipsoidal measurement CAN be set up (unlike the mocked-failure test
        above, where QgsDistanceArea isn't configured to succeed), the old DEGREES alarm
        is replaced by an informational note -- the distances are now real meters, not a
        caveat about them being wrong."""
        demand_layer = MagicMock()
        g = MagicMock()
        g.isEmpty.return_value = False
        f = MagicMock()
        f.geometry.return_value = g
        demand_layer.getFeatures.return_value = [f]

        candidates_layer = MagicMock()
        cand_geom = MagicMock()
        cand_geom.isEmpty.return_value = False
        cand_feat = MagicMock()
        cand_feat.geometry.return_value = cand_geom
        cand_feat.fields.return_value.count.return_value = 1
        cand_feat.attribute.return_value = "A"
        candidates_layer.getFeatures.return_value = [cand_feat]
        candidates_layer.featureCount.return_value = 1
        candidates_layer.crs.return_value.isGeographic.return_value = True
        candidates_layer.crs.return_value.authid.return_value = "EPSG:4326"

        mock_project.instance.return_value.ellipsoid.return_value = "WGS84"
        mock_da_cls.return_value.measureLine.return_value = 111000.0

        mock_find.side_effect = lambda name: {"candidates": candidates_layer, "demand": demand_layer}.get(name)

        res = optimal_hub_siting("candidates", "demand")

        self.assertNotIn("warning", res)
        self.assertIn("note", res)
        self.assertIn("ellipsoidal", res["note"])
        self.assertNotIn("DEGREES", res["note"])
        self.assertEqual(res["ranked_candidates"][0]["avg_distance"], 111000.0)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_rejects_an_oversized_candidate_times_demand_pair_count(self, mock_find):
        """PERF-002, 2026-09-14 audit: candidate x demand distance computation is O(pairs)
        pure Python with no upper bound -- this proves the new safety cap actually engages
        (and does so BEFORE the expensive distance() loop runs, not after) for an input
        that would exceed it, instead of freezing the QGIS main thread."""
        demand_layer = MagicMock()
        demand_geom = MagicMock()
        demand_geom.isEmpty.return_value = False
        demand_feat = MagicMock()
        demand_feat.geometry.return_value = demand_geom
        demand_layer.getFeatures.return_value = [demand_feat] * 10

        candidates_layer = MagicMock()
        candidates_layer.featureCount.return_value = 1_000_000  # 1M x 10 = 10M pairs > cap
        # getFeatures() must never even be consulted -- the cap check happens first.
        candidates_layer.getFeatures.side_effect = AssertionError(
            "must not iterate candidate features once the pair-count cap is exceeded"
        )

        mock_find.side_effect = lambda name: {"candidates": candidates_layer, "demand": demand_layer}.get(name)

        res = optimal_hub_siting("candidates", "demand")
        self.assertIn("error", res)
        self.assertIn("safety limit", res["error"])
        self.assertIn("1,000,000", res["error"])


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TestGreedyPMedian(unittest.TestCase):
    """Pure Python, no QGIS needed. Verified by hand against a symmetric
    4-corner scenario where multiple candidate pairs are provably tied-
    optimal -- see the session notes for the manual distance verification."""

    def _corner_scenario(self):
        candidates = {"A": (0, 0), "B": (10, 10), "C": (0, 10), "D": (10, 0)}
        demand_points = [(1, 1), (1, 9), (9, 1), (9, 9)]
        distances = {name: [_dist(pos, dp) for dp in demand_points] for name, pos in candidates.items()}
        return distances

    def test_selects_requested_number_of_facilities(self):
        distances = self._corner_scenario()
        result = _greedy_p_median(distances, [1.0] * 4, 2)
        self.assertEqual(len(result["selected_facilities"]), 2)

    def test_total_distance_matches_hand_verified_value(self):
        # Confirmed by hand: any 2 of these 4 symmetric corner candidates
        # produce the same total (20.94), since each pair covers all 4
        # demand points equally well by symmetry.
        distances = self._corner_scenario()
        result = _greedy_p_median(distances, [1.0] * 4, 2)
        self.assertAlmostEqual(result["total_weighted_distance"], 20.94, places=1)

    def test_selecting_all_candidates_gives_zero_distance_improvement_floor(self):
        distances = self._corner_scenario()
        result = _greedy_p_median(distances, [1.0] * 4, 4)
        self.assertEqual(len(result["selected_facilities"]), 4)
        # With every candidate selected, distance is dominated by each demand
        # point's single closest candidate (1.41 in this scenario).
        self.assertAlmostEqual(result["avg_distance_per_demand_point"], 1.41, places=1)

    def test_caps_at_available_candidate_count(self):
        distances = {"A": [1.0, 2.0], "B": [3.0, 4.0]}
        result = _greedy_p_median(distances, [1.0, 1.0], 5)
        self.assertEqual(len(result["selected_facilities"]), 2)


class TestLocationAllocationDegradesOutsideQgis(unittest.TestCase):
    def test_degrades(self):
        res = location_allocation("candidates", "demand", 2)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestLocationAllocationValidation(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    def test_rejects_non_positive_num_facilities(self):
        res = location_allocation("candidates", "demand", 0)
        self.assertIn("error", res)
        self.assertIn("num_facilities", res["error"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_rejects_num_facilities_exceeding_candidates(self, mock_find):
        candidates_layer = MagicMock()
        cand_feat = MagicMock()
        cand_geom = MagicMock()
        cand_geom.isEmpty.return_value = False
        cand_feat.geometry.return_value = cand_geom
        cand_feat.fields.return_value.count.return_value = 0
        candidates_layer.getFeatures.return_value = [cand_feat]
        candidates_layer.featureCount.return_value = 1  # PERF-002 pair-count guard

        demand_layer = MagicMock()
        demand_feat = MagicMock()
        demand_geom = MagicMock()
        demand_geom.isEmpty.return_value = False
        demand_feat.geometry.return_value = demand_geom
        demand_layer.getFeatures.return_value = [demand_feat]

        def side_effect(name):
            return {"candidates": candidates_layer, "demand": demand_layer}.get(name)
        mock_find.side_effect = side_effect

        res = location_allocation("candidates", "demand", 5)

        self.assertIn("error", res)
        self.assertIn("num_facilities", res["error"])


class TestTourLength(unittest.TestCase):
    """Pure Python, no QGIS needed."""

    def test_sums_consecutive_edge_lengths(self):
        dm = [[0, 3, 5], [3, 0, 4], [5, 4, 0]]
        self.assertEqual(_tour_length([0, 1, 2], dm), 7)


class TestTspNearestNeighbor(unittest.TestCase):
    def test_visits_every_city_exactly_once(self):
        points = [(0, 0), (10, 10), (10, 0), (0, 10), (5, 5)]
        n = len(points)
        dm = [[_dist(points[i], points[j]) for j in range(n)] for i in range(n)]
        tour = _tsp_nearest_neighbor(dm, start_index=0)
        self.assertEqual(sorted(tour), list(range(n)))
        self.assertEqual(tour[0], 0)


class TestTwoOptAndOptimizeRoute(unittest.TestCase):
    """Verified by hand: a 10x10 square's 4 corners, given in a deliberately
    crossed initial order, must resolve to the true optimal 3-side open-path
    tour (length 30) with no crossing diagonals."""

    def test_untangles_a_crossed_square_to_the_known_optimal_tour(self):
        points = [(0, 0), (10, 10), (10, 0), (0, 10)]
        n = len(points)
        dm = [[_dist(points[i], points[j]) for j in range(n)] for i in range(n)]

        tour, length = _optimize_route(dm, start_index=0)

        self.assertAlmostEqual(length, 30.0, places=1)
        self.assertEqual(sorted(tour), list(range(n)))

    def test_two_opt_never_makes_a_tour_worse(self):
        points = [(0, 0), (10, 10), (10, 0), (0, 10), (3, 7), (8, 2)]
        n = len(points)
        dm = [[_dist(points[i], points[j]) for j in range(n)] for i in range(n)]
        initial_tour = list(range(n))  # arbitrary, likely suboptimal order
        improved = _two_opt(initial_tour, dm)
        self.assertLessEqual(_tour_length(improved, dm), _tour_length(initial_tour, dm))


class TestOptimizeDeliveryRouteDegradesOutsideQgis(unittest.TestCase):
    def test_degrades(self):
        res = optimize_delivery_route("stops")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestOptimizeDeliveryRouteValidation(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_rejects_fewer_than_two_stops(self, mock_find):
        layer = MagicMock()
        feat = MagicMock()
        geom = MagicMock()
        geom.isEmpty.return_value = False
        feat.geometry.return_value = geom
        layer.getFeatures.return_value = [feat]
        mock_find.return_value = layer

        res = optimize_delivery_route("stops")

        self.assertIn("error", res)
        self.assertIn("at least 2", res["error"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_rejects_unknown_start_stop_name(self, mock_find):
        layer = MagicMock()
        feats = []
        for i in range(3):
            feat = MagicMock()
            geom = MagicMock()
            geom.isEmpty.return_value = False
            feat.geometry.return_value = geom
            feat.fields.return_value.count.return_value = 1
            feat.attribute.return_value = f"stop_{i}"
            feats.append(feat)
        layer.getFeatures.return_value = feats
        mock_find.return_value = layer

        res = optimize_delivery_route("stops", start_stop_name="nonexistent")

        self.assertIn("error", res)
        self.assertIn("nonexistent", res["error"])


def _stop_layer(names):
    """Builds a MagicMock point layer with `names` as its first-field values,
    at distinct integer coordinates 0,1,2... along the x-axis, matching the
    feat.geometry()/attribute(0) shape optimize_delivery_route reads."""
    layer = MagicMock()
    feats = []
    for i, name in enumerate(names):
        feat = MagicMock()
        geom = MagicMock()
        geom.isEmpty.return_value = False
        geom.asPoint.return_value = MagicMock(x=lambda i=i: float(i), y=lambda: 0.0)
        # distance() is called pairwise for every (i, j); a simple constant
        # keeps the TSP heuristic deterministic without needing real geometry.
        geom.distance.side_effect = lambda other, i=i: abs(i - names.index(names[0]))
        feat.geometry.return_value = geom
        feat.fields.return_value.count.return_value = 1
        feat.attribute.return_value = name
        feats.append(feat)
    layer.getFeatures.return_value = feats
    return layer


class TestOptimizeDeliveryRouteRoadSnapping(_LineNetworkMixin, unittest.TestCase):
    """Covers the 2026-09-04 road-snapped-route upgrade: optimize_delivery_route
    now accepts an optional road_network_layer and, when given, builds a real
    routable line via native:shortestpathpointtopoint instead of leaving the
    output as a straight-line stop order (docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md
    Section IV)."""

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_without_road_network_returns_straight_line_warning(self, mock_find):
        layer = _stop_layer(["a", "b", "c"])
        layer.crs.return_value.isGeographic.return_value = False
        mock_find.return_value = layer

        res = optimize_delivery_route("stops")

        self.assertTrue(res["success"])
        self.assertNotIn("route_layer", res)
        self.assertIn("warning", res)
        self.assertIn("straight-line", res["warning"])
        self.assertNotIn("DEGREES", res["warning"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_geographic_stops_layer_extends_the_straight_line_warning(self, mock_find):
        """QGIS-006, 2026-09-13 audit: same CRS-unit-mismatch class buffer_analysis already
        warns about -- the straight-line distance_matrix is a raw, unconverted CRS-unit
        distance, with total_distance carrying no unit label at all."""
        layer = _stop_layer(["a", "b", "c"])
        layer.crs.return_value.isGeographic.return_value = True
        layer.crs.return_value.authid.return_value = "EPSG:4326"
        mock_find.return_value = layer

        res = optimize_delivery_route("stops")

        self.assertTrue(res["success"])
        self.assertIn("warning", res)
        self.assertIn("DEGREES", res["warning"])
        self.assertIn("EPSG:4326", res["warning"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_unknown_road_network_layer_reports_missing(self, mock_find):
        def side_effect(name):
            return _stop_layer(["a", "b"]) if name == "stops" else None
        mock_find.side_effect = side_effect

        res = optimize_delivery_route("stops", road_network_layer="ghost_roads")

        self.assertIn("error", res)
        self.assertIn("ghost_roads", res["error"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_with_road_network_builds_and_registers_route_layer(self, mock_find, mock_processing, mock_project):
        def side_effect(name):
            return {"stops": _stop_layer(["a", "b", "c"]), "roads": MagicMock()}.get(name)
        mock_find.side_effect = side_effect

        segment = MagicMock()
        segment.featureCount.return_value = 1
        mock_processing.run.return_value = {"OUTPUT": segment}

        res = optimize_delivery_route("stops", road_network_layer="roads")

        self.assertTrue(res["success"])
        self.assertNotIn("warning", res)
        self.assertEqual(res.get("route_layer"), "stops_road_route")
        self.assertTrue(res.get("road_snapped"))
        # Two segments (3 stops -> 2 legs) get merged into one output layer.
        mock_processing.run.assert_any_call("native:mergevectorlayers", unittest.mock.ANY)
        mock_project.instance.return_value.addMapLayer.assert_called()

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_road_network_present_but_no_segment_buildable_falls_back_with_warning(self, mock_find, mock_processing, mock_project):
        def side_effect(name):
            return {"stops": _stop_layer(["a", "b"]), "roads": MagicMock()}.get(name)
        mock_find.side_effect = side_effect
        mock_processing.run.side_effect = Exception("network too far from points")

        res = optimize_delivery_route("stops", road_network_layer="roads")

        self.assertTrue(res["success"])
        self.assertNotIn("route_layer", res)
        self.assertIn("warning", res)
        self.assertIn("Could not build", res["warning"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_network_aware_ordering_flag_true_with_road_network(self, mock_find, mock_processing, mock_project):
        def side_effect(name):
            return {"stops": _stop_layer(["a", "b", "c"]), "roads": MagicMock()}.get(name)
        mock_find.side_effect = side_effect

        segment = MagicMock()
        segment.featureCount.return_value = 1
        mock_processing.run.return_value = {"OUTPUT": segment}

        res = optimize_delivery_route("stops", road_network_layer="roads")

        self.assertTrue(res["network_aware_ordering"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_network_aware_ordering_flag_false_without_road_network(self, mock_find):
        mock_find.return_value = _stop_layer(["a", "b", "c"])

        res = optimize_delivery_route("stops")

        self.assertFalse(res["network_aware_ordering"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_speed_and_direction_fields_reach_the_distance_matrix_build(self, mock_find, mock_processing, mock_project):
        network = MagicMock()
        network.fields.return_value.indexOf.side_effect = lambda name: 0 if name in ("speed_kmh", "oneway") else -1

        def side_effect(name):
            return {"stops": _stop_layer(["a", "b"]), "roads": network}.get(name)
        mock_find.side_effect = side_effect

        segment = MagicMock()
        segment.featureCount.return_value = 1
        mock_processing.run.return_value = {"OUTPUT": segment}

        res = optimize_delivery_route(
            "stops", road_network_layer="roads", speed_field="speed_kmh", direction_field="oneway",
        )

        self.assertTrue(res["success"])
        # The distance-matrix build (native:shortestpathpointtopoint) must have
        # received the resolved speed/direction params on at least one call.
        matrix_calls = [c for c in mock_processing.run.call_args_list if c.args[0] == "native:shortestpathpointtopoint"]
        self.assertTrue(matrix_calls)
        self.assertEqual(matrix_calls[0].args[1].get("SPEED_FIELD"), "speed_kmh")
        self.assertEqual(matrix_calls[0].args[1].get("DIRECTION_FIELD"), "oneway")

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_bad_speed_field_errors_before_touching_processing(self, mock_find):
        network = MagicMock()
        network.fields.return_value.indexOf.return_value = -1

        def side_effect(name):
            return {"stops": _stop_layer(["a", "b"]), "roads": network}.get(name)
        mock_find.side_effect = side_effect

        res = optimize_delivery_route("stops", road_network_layer="roads", speed_field="ghost_field")

        self.assertIn("error", res)
        self.assertIn("ghost_field", res["error"])


class TestBuildNetworkDistanceMatrix(unittest.TestCase):
    """Direct unit tests for _build_network_distance_matrix -- the 2026-09-11
    v1.7.0 workstream 4 addition: real road-network distance driving
    optimize_delivery_route's visiting-order decision, not just the final
    drawn line. Deliberately uses native:shortestpathpointtopoint's own
    'cost' output field rather than travel_time_matrix, which was
    confirmed live to key its destination-side matrix by an internal
    coordinate string, not by any of the stop layer's own attributes."""

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    def test_reads_the_real_cost_field(self, mock_processing):
        result_feat = MagicMock()
        result_feat.__getitem__.side_effect = lambda key: 1234.5 if key == "cost" else None
        result_layer = MagicMock()
        result_layer.getFeatures.return_value = [result_feat]
        mock_processing.run.return_value = {"OUTPUT": result_layer}

        geoms = [MagicMock(), MagicMock()]
        for i, g in enumerate(geoms):
            g.asPoint.return_value = MagicMock(x=lambda i=i: float(i), y=lambda: 0.0)

        matrix = _build_network_distance_matrix(MagicMock(), geoms)

        self.assertEqual(matrix[0][1], 1234.5)
        self.assertEqual(matrix[1][0], 1234.5)

    def test_diagonal_is_always_zero_no_processing_call(self):
        geoms = [MagicMock()]
        geoms[0].asPoint.return_value = MagicMock(x=lambda: 0.0, y=lambda: 0.0)

        matrix = _build_network_distance_matrix(MagicMock(), geoms)

        self.assertEqual(matrix, [[0.0]])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    def test_unreachable_pair_becomes_infinity_not_a_crash(self, mock_processing):
        result_layer = MagicMock()
        result_layer.getFeatures.return_value = []  # no path found -- empty result
        mock_processing.run.return_value = {"OUTPUT": result_layer}

        geoms = [MagicMock(), MagicMock()]
        for i, g in enumerate(geoms):
            g.asPoint.return_value = MagicMock(x=lambda i=i: float(i), y=lambda: 0.0)

        matrix = _build_network_distance_matrix(MagicMock(), geoms)

        self.assertEqual(matrix[0][1], float("inf"))

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    def test_processing_run_exception_becomes_infinity_not_a_crash(self, mock_processing):
        mock_processing.run.side_effect = Exception("boom")

        geoms = [MagicMock(), MagicMock()]
        for i, g in enumerate(geoms):
            g.asPoint.return_value = MagicMock(x=lambda i=i: float(i), y=lambda: 0.0)

        matrix = _build_network_distance_matrix(MagicMock(), geoms)

        self.assertEqual(matrix[0][1], float("inf"))
        self.assertEqual(matrix[1][0], float("inf"))

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    def test_extra_params_are_merged_into_every_call(self, mock_processing):
        result_layer = MagicMock()
        result_layer.getFeatures.return_value = []
        mock_processing.run.return_value = {"OUTPUT": result_layer}

        geoms = [MagicMock(), MagicMock()]
        for i, g in enumerate(geoms):
            g.asPoint.return_value = MagicMock(x=lambda i=i: float(i), y=lambda: 0.0)

        _build_network_distance_matrix(MagicMock(), geoms, extra_params={"SPEED_FIELD": "speed_kmh"})

        for call in mock_processing.run.call_args_list:
            self.assertEqual(call.args[1].get("SPEED_FIELD"), "speed_kmh")


class TestBuildRoadSnappedRoute(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    def test_single_leg_skips_merge_step(self, mock_processing, mock_project):
        segment = MagicMock()
        segment.featureCount.return_value = 1
        mock_processing.run.return_value = {"OUTPUT": segment}

        geoms = [MagicMock(), MagicMock()]
        for i, g in enumerate(geoms):
            g.asPoint.return_value = MagicMock(x=lambda i=i: float(i), y=lambda: 0.0)

        name = _build_road_snapped_route("stops", MagicMock(), geoms, [0, 1])

        self.assertEqual(name, "stops_road_route")
        mock_processing.run.assert_called_once()  # only the point-to-point call, no merge
        segment.setName.assert_called_once_with("stops_road_route")

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    def test_returns_none_when_every_segment_fails(self, mock_processing):
        mock_processing.run.side_effect = Exception("boom")
        geoms = [MagicMock(), MagicMock()]
        for i, g in enumerate(geoms):
            g.asPoint.return_value = MagicMock(x=lambda i=i: float(i), y=lambda: 0.0)

        name = _build_road_snapped_route("stops", MagicMock(), geoms, [0, 1])

        self.assertIsNone(name)


class TestScoreRouteIncidentRiskDegradesOutsideQgis(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = score_route_incident_risk("route", "incidents", 500)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_degrades_gracefully_outside_qgis_with_date_filter(self):
        res = score_route_incident_risk("route", "incidents", 500, date_field="date", days_back=30)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_degrades_gracefully_outside_qgis_with_weight_field(self):
        res = score_route_incident_risk("route", "incidents", 500, weight_field="severity_score")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestScoreRouteIncidentRiskPropagatesCrsWarning(unittest.TestCase):
    """QGIS-006/QGIS-007, 2026-09-13 audit: this tool used to discard buffer_analysis's own
    CRS warning entirely (only checked "error" in buffer_result) -- the same underlying
    geographic-CRS issue also silently mislabels distance_to_route_m as meters when it's
    actually degrees, the more safety-relevant half of the bug since this tool exists
    specifically to score incident proximity to a route for humanitarian/security decisions."""

    def _run(self, buffer_warning):
        route = MagicMock()
        route_geom = MagicMock()
        route_geom.isEmpty.return_value = False
        route_geom.distance.return_value = 42.0
        route_feat = MagicMock()
        route_feat.geometry.return_value = route_geom
        route.getFeatures.return_value = [route_feat]

        incidents = MagicMock()
        incidents.fields.return_value = []
        incident_geom = MagicMock()
        incident_geom.isEmpty.return_value = False
        incident_feat = MagicMock()
        incident_feat.geometry.return_value = incident_geom
        incident_feat.id.return_value = 1
        incidents.getFeatures.return_value = [incident_feat]

        buffer_layer = MagicMock()
        buffer_geom = MagicMock()
        buffer_geom.isEmpty.return_value = False
        buffer_geom.intersects.return_value = True
        buffer_feat = MagicMock()
        buffer_feat.geometry.return_value = buffer_geom
        buffer_layer.getFeatures.return_value = [buffer_feat]

        def fake_find(name):
            return {"route": route, "incidents": incidents, "route_buffer_500": buffer_layer}.get(name)

        buffer_result = {"success": True, "layer_name": "route_buffer_500"}
        if buffer_warning:
            buffer_result["warning"] = buffer_warning

        with patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name", side_effect=fake_find), \
             patch("cartogen_ai.core.agent.tools.logistics_tools.buffer_analysis", return_value=buffer_result), \
             patch("cartogen_ai.core.agent.tools.logistics_tools._style_risk_buffer_layer"):
            return score_route_incident_risk("route", "incidents", 500)

    def test_no_warning_when_buffer_analysis_reports_none(self):
        res = self._run(buffer_warning=None)
        self.assertTrue(res["success"])
        self.assertNotIn("warning", res)

    def test_geographic_crs_warning_is_propagated_and_extended(self):
        res = self._run(buffer_warning="'route' is in a geographic CRS (EPSG:4326), so distance=500 was applied in DEGREES.")
        self.assertTrue(res["success"])
        self.assertIn("warning", res)
        self.assertIn("EPSG:4326", res["warning"])
        self.assertIn("distance_to_route_m", res["warning"])
        self.assertIn("DEGREES", res["warning"])


class TestNetworkGeometryGuard(unittest.TestCase):
    """Live-reported 2026-09-24: a Road Network ingested as points went through
    calculate_service_area as a "success". The network tools now refuse a non-line layer."""

    def _wkb(self, geometry_type):
        wkb = MagicMock()
        wkb.GeometryType.LineGeometry = "line"
        wkb.geometryType.return_value = geometry_type
        return wkb

    def test_point_layer_is_rejected_with_a_pointer_to_the_fix(self):
        with patch("cartogen_ai.core.agent.tools.logistics_tools.QgsWkbTypes", self._wkb("point"), create=True):
            err = _network_geometry_error(MagicMock(), "Road Network")
        self.assertIn("'Road Network' is not a line layer", err)
        self.assertIn("key='highway'", err)

    def test_line_layer_passes(self):
        with patch("cartogen_ai.core.agent.tools.logistics_tools.QgsWkbTypes", self._wkb("line"), create=True):
            self.assertIsNone(_network_geometry_error(MagicMock(), "Road Network"))

    def test_service_area_and_matrix_stop_before_processing_on_a_point_network(self):
        with patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True),              patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name", return_value=MagicMock()),              patch("cartogen_ai.core.agent.tools.logistics_tools.QgsWkbTypes", self._wkb("point"), create=True),              patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True) as proc:
            r1 = calculate_service_area("Health Facilities", "Road Network", 5000)
            r2 = travel_time_matrix("Origin", "Health Facilities", "Road Network")
            r3 = optimize_delivery_route("Stops", road_network_layer="Road Network")
        for r in (r1, r2, r3):
            self.assertIn("is not a line layer", r.get("error", ""), r)
        proc.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
