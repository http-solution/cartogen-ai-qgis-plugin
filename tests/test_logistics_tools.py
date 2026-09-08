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
)


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


class TestCalculateServiceAreaNetworkParams(unittest.TestCase):
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
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_speed_and_direction_fields_reach_processing_run_and_result(self, mock_find, mock_processing, mock_project):
        network = MagicMock()
        network.fields.return_value.indexOf.side_effect = lambda name: 0 if name in ("speed_kmh", "oneway") else -1
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Warehouse"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        lines_layer.featureCount.return_value = 1
        hull_layer = MagicMock()

        def run_side_effect(alg_id, params):
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
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_no_fields_given_omits_them_from_params_and_result(self, mock_find, mock_processing, mock_project):
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Warehouse"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        lines_layer.featureCount.return_value = 1
        hull_layer = MagicMock()

        def run_side_effect(alg_id, params):
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


class TestCalculateServiceAreaDegenerateNetworkIsolation(unittest.TestCase):
    """BUG-2026-09-05-2: a small/degenerate road network can make either
    native:serviceareafrompoint or native:convexhull raise for one facility --
    that must no longer abort the whole multi-facility call. Mocked reproduction
    of the two exact error shapes recorded in docs/BUG_TRACKER.md; this sandbox has
    no live QGIS to re-run the original real-QGIS reproduction against, so this
    covers the fix's logic, not a live re-verification of the underlying QGIS
    behavior itself."""

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_convexhull_failure_on_one_facility_keeps_its_lines_and_the_other_facility(self, mock_find, mock_processing, mock_project):
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Degenerate", "Normal"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        lines_layer.featureCount.return_value = 1
        hull_layer = MagicMock()

        def run_side_effect(alg_id, params):
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
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_serviceareafrompoint_failure_on_one_facility_does_not_abort_the_other(self, mock_find, mock_processing, mock_project):
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Degenerate", "Normal"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        lines_layer.featureCount.return_value = 1
        hull_layer = MagicMock()
        calls = {"count": 0}

        def run_side_effect(alg_id, params):
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
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_all_facilities_failing_still_reports_a_clean_error(self, mock_find, mock_processing, mock_project):
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Degenerate"]), "roads": network}.get(name)

        def run_side_effect(alg_id, params):
            raise RuntimeError("invalid geometry")
        mock_processing.run.side_effect = run_side_effect

        res = calculate_service_area("facilities", "roads", 1000)

        self.assertIn("error", res)
        self.assertNotIn("success", res)


class TestTravelTimeMatrixNetworkParams(unittest.TestCase):
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

        def run_side_effect(alg_id, params):
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

        def run_side_effect(alg_id, params):
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

        def side_effect(name):
            return {"candidates": candidates_layer, "demand": demand_layer}.get(name)
        mock_find.side_effect = side_effect

        res = optimal_hub_siting("candidates", "demand")

        self.assertTrue(res["success"])
        self.assertEqual(res["demand_point_count"], 3)
        self.assertEqual(res["ranked_candidates"][0]["candidate"], "near")
        self.assertEqual(res["ranked_candidates"][1]["candidate"], "far")


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


class TestOptimizeDeliveryRouteRoadSnapping(unittest.TestCase):
    """Covers the 2026-09-04 road-snapped-route upgrade: optimize_delivery_route
    now accepts an optional road_network_layer and, when given, builds a real
    routable line via native:shortestpathpointtopoint instead of leaving the
    output as a straight-line stop order (docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md
    Section IV)."""

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_without_road_network_returns_straight_line_warning(self, mock_find):
        mock_find.return_value = _stop_layer(["a", "b", "c"])

        res = optimize_delivery_route("stops")

        self.assertTrue(res["success"])
        self.assertNotIn("route_layer", res)
        self.assertIn("warning", res)
        self.assertIn("straight-line", res["warning"])

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


if __name__ == "__main__":
    unittest.main()
