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
    score_route_incident_risk,
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
