# -*- coding: utf-8 -*-
"""Tests for agent/tools/logistics_tools.py -- the Phase 3 humanitarian-ops
improvement (hub siting, service-area, travel-distance analysis), plus
location_allocation/optimize_delivery_route added in the ArcGIS-parity pass.
Follows the QGIS_AVAILABLE=False degrade-path convention used throughout the
suite."""
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.tools import logistics_tools as lt
from cartogen_ai.core.agent.tools.logistics_tools import (
    _rank_hub_candidates, optimal_hub_siting, calculate_service_area, travel_time_matrix,
    _greedy_p_median, location_allocation, _tsp_nearest_neighbor, _two_opt,
    _tour_length, _optimize_route, optimize_delivery_route, population_access_gap,
    score_route_incident_risk, _build_road_snapped_route, _network_direction_speed_params,
    _build_network_distance_matrix, _make_distance_area, _measure_distance,
    _network_geometry_error, _network_context, _point_for_network,
    _reach_metres, _max_speed_in_field, _clip_network_to_reach,
)



def _real_looking_lines(layer, length=1234.5):
    """Gives a mock reachable-network layer one non-degenerate feature. calculate_service_area now
    refuses a zero-length result (rc7 smoke test F05, 2026-09-30) and so reads each feature's
    geometry length -- a bare MagicMock has no geometry at all."""
    feature = MagicMock()
    feature.geometry.return_value.isNull.return_value = False
    feature.geometry.return_value.length.return_value = length
    layer.featureCount.return_value = 1
    layer.getFeatures.side_effect = lambda *a, **k: iter([feature])
    return layer

class TestMakeDistanceArea(unittest.TestCase):
    """QGIS-006 follow-up (2026-09-19): geographic-CRS layers previously measured distance
    in raw planar degrees -- _make_distance_area sets up real ellipsoidal (WGS84 geodesic)
    measurement instead, when the layer's CRS is geographic."""

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsDistanceArea", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    def test_projected_crs_is_measured_ellipsoidally_too(self, mock_project, mock_da_cls):
        # #142: it used to return None here and fall back to QgsGeometry.distance(), which is wrong for Web Mercator
        # (inflated by 1/cos(lat)) and for any CRS whose unit is not the metre.
        layer = MagicMock()
        layer.crs.return_value.isGeographic.return_value = False
        mock_project.instance.return_value.ellipsoid.return_value = "WGS84"
        self.assertIs(_make_distance_area(layer), mock_da_cls.return_value)
        mock_da_cls.return_value.setEllipsoid.assert_called_once_with("WGS84")

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

    def test_an_ellipsoidal_failure_is_raised_not_replaced_by_a_planar_number(self):
        # #142: the planar fallback used to be returned silently and the tool then reported geodesic metres.
        distance_area = MagicMock()
        distance_area.measureLine.side_effect = RuntimeError("boom")
        geom_a, geom_b = MagicMock(), MagicMock()
        geom_a.distance.return_value = 7.0

        with self.assertRaises(RuntimeError):
            _measure_distance(distance_area, geom_a, geom_b)
        geom_a.distance.assert_not_called()


class TestGeomsInCrs(unittest.TestCase):
    """#142: demand points must be in the candidates' CRS before any distance is measured."""

    def test_same_crs_returns_the_geometries_untouched(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _geoms_in_crs
        crs = MagicMock()
        crs.isValid.return_value = True
        geoms = [MagicMock(), MagicMock()]
        self.assertEqual(_geoms_in_crs(geoms, crs, crs), geoms)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsCoordinateTransform", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    def test_a_different_crs_is_transformed_on_copies(self, _project, mock_geom_cls, _transform):
        from cartogen_ai.core.agent.tools.logistics_tools import _geoms_in_crs
        a, b = MagicMock(), MagicMock()
        a.isValid.return_value = b.isValid.return_value = True
        original = MagicMock()
        copy = mock_geom_cls.return_value
        copy.transform.return_value = 0
        out = _geoms_in_crs([original], a, b)
        self.assertEqual(out, [copy])
        mock_geom_cls.assert_called_once_with(original)
        original.transform.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsCoordinateTransform", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    def test_a_failed_transform_raises_instead_of_measuring_the_wrong_numbers(self, _project, mock_geom_cls, _transform):
        from cartogen_ai.core.agent.tools.logistics_tools import _geoms_in_crs
        a, b = MagicMock(), MagicMock()
        a.isValid.return_value = b.isValid.return_value = True
        mock_geom_cls.return_value.transform.return_value = 1
        with self.assertRaises(ValueError):
            _geoms_in_crs([MagicMock()], a, b)


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
    """These tests pass a MagicMock as the road network, and QgsWkbTypes/QgsProcessingContext/
    QgsPointXY don't exist outside QGIS, so the QGIS-dependent helpers the network tools call
    are stubbed to their no-op behaviour: the network is "a line layer" (_network_geometry_error),
    a start point is passed through as "x,y" (_point_for_network), and the processing context is a
    plain mock (_network_context). Their real behaviour has its own tests: TestNetworkGeometryGuard
    and TestNetworkContextAndStartPoint here, and tests/test_network_units_live.py in real QGIS."""

    def setUp(self):
        super().setUp()
        base = "cartogen_ai.core.agent.tools.logistics_tools."
        self.mock_context = MagicMock(name="network_context")
        for attr, target, kwargs in (
            ("mock_geometry_error", base + "_network_geometry_error", {"return_value": None}),
            ("mock_point_for_network", base + "_point_for_network",
             {"side_effect": lambda point, crs, net: f"{point.x()},{point.y()}"}),
            ("mock_point_xy", base + "_point_xy_in_network_crs", {"side_effect": lambda point, crs, net: point}),
            ("mock_network_context_fn", base + "_network_context", {"return_value": self.mock_context}),
        ):
            p = patch(target, **kwargs)
            setattr(self, attr, p.start())
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
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_a_two_stop_route_runs_one_shortest_path_search_not_three(self, mock_find, mock_processing, mock_project):
        # rc11 smoke test C1: a two-stop route took 14 minutes (matrix A->B and B->A, then the route, ~3 min each).
        network = MagicMock()
        network.fields.return_value.indexOf.side_effect = lambda name: 0 if name in ("speed_kmh", "oneway") else -1
        mock_find.side_effect = lambda name: {"stops": _stop_layer(["a", "b"]), "roads": network}.get(name)
        segment = MagicMock()
        segment.featureCount.return_value = 1
        mock_processing.run.return_value = {"OUTPUT": segment}

        res = optimize_delivery_route("stops", road_network_layer="roads", speed_field="speed_kmh", direction_field="oneway")

        self.assertTrue(res["success"])
        searches = [c for c in mock_processing.run.call_args_list if c.args[0] == "native:shortestpathpointtopoint"]
        self.assertEqual(len(searches), 1)
        self.assertEqual(searches[0].args[1].get("DIRECTION_FIELD"), "oneway")     # the route itself honours one-way now

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_a_fastest_route_runs_the_time_strategy_and_reports_an_estimate(self, mock_find, mock_processing, mock_project):
        # #131: "fastest route" used to return a shortest-distance route. strategy='fastest' now runs STRATEGY 1.
        network = MagicMock()
        network.fields.return_value.indexOf.side_effect = lambda name: 0 if name == "speed_kmh" else -1
        mock_find.side_effect = lambda name: {"stops": _stop_layer(["a", "b"]), "roads": network}.get(name)
        segment = MagicMock()
        segment.featureCount.return_value = 1
        mock_processing.run.return_value = {"OUTPUT": segment}

        with patch("cartogen_ai.core.agent.tools.logistics_tools._route_cost_sum", return_value=0.75), \
                patch("cartogen_ai.core.agent.tools.logistics_tools._route_length_m", return_value=41250.0):
            res = optimize_delivery_route("stops", road_network_layer="roads", speed_field="speed_kmh",
                                          strategy="fastest", default_speed=40)

        self.assertTrue(res["success"])
        search = [c for c in mock_processing.run.call_args_list if c.args[0] == "native:shortestpathpointtopoint"][0]
        self.assertEqual(search.args[1]["STRATEGY"], 1)
        self.assertEqual(search.args[1]["DEFAULT_SPEED"], 40)
        self.assertEqual(res["total_travel_time_hours"], 0.75)
        self.assertEqual(res["total_travel_time_minutes"], 45.0)
        self.assertEqual(res["route_length_m"], 41250.0)
        self.assertNotIn("total_distance", res)                    # the cost is hours, never labelled metres
        self.assertIn("estimate", res["route_note"])
        self.assertIn("speed_kmh", res["route_note"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    def test_strategy_arguments_are_validated_before_any_layer_lookup(self):
        self.assertIn("strategy", optimize_delivery_route("stops", road_network_layer="roads", strategy="teleport")["error"])
        self.assertIn("road_network_layer", optimize_delivery_route("stops", strategy="fastest")["error"])
        self.assertIn("default_speed", optimize_delivery_route("stops", road_network_layer="roads",
                                                                strategy="fastest", default_speed=0)["error"])

    def test_the_default_route_still_says_shortest(self):
        from cartogen_ai.core.agent.tools.logistics_tools import route_strategy_summary
        out = route_strategy_summary(False, 1200.0, 50, None)
        self.assertEqual(out["route_strategy"], "shortest distance")
        self.assertIn("strategy='fastest'", out["route_note"])
        self.assertNotIn("total_travel_time_hours", out)
        flat = route_strategy_summary(True, 0.5, 50, None)
        self.assertIn("flat 50 km/h", flat["route_note"])
        self.assertEqual(flat["total_travel_time_minutes"], 30.0)

    def test_geofabrik_one_way_codes_are_detected_from_the_layers_own_values(self):
        # rc11 smoke test: the Yemen roads hold F/B in 'oneway'; the OSM defaults yes/-1/no matched nothing.
        from cartogen_ai.core.agent.tools.logistics_tools import _network_direction_speed_params
        net = MagicMock()
        net.fields.return_value.indexOf.return_value = 3
        net.uniqueValues.return_value = {"F", "B", "T"}
        extra, err = _network_direction_speed_params(net, direction_field="oneway")
        self.assertIsNone(err)
        self.assertEqual((extra["VALUE_FORWARD"], extra["VALUE_BACKWARD"], extra["VALUE_BOTH"]), ("F", "T", "B"))

    def test_osm_one_way_values_keep_the_defaults(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _network_direction_speed_params
        net = MagicMock()
        net.fields.return_value.indexOf.return_value = 3
        net.uniqueValues.return_value = {"yes", "-1", "no"}
        extra, _ = _network_direction_speed_params(net, direction_field="oneway")
        self.assertEqual((extra["VALUE_FORWARD"], extra["VALUE_BACKWARD"], extra["VALUE_BOTH"]), ("yes", "-1", "no"))

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
        _real_looking_lines(lines_layer)
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
        _real_looking_lines(lines_layer)
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


class TestCalculateServiceAreaNeverReplacesAGoodResultWithAnEmptyOne(_LineNetworkMixin, unittest.TestCase):
    """rc7 smoke test, 2026-09-30 (F05): a re-run produced a zero-length reachable network, the
    previous good layer of the same name was removed by _replace_named_layer, and success was
    reported. A zero-length result must leave existing layers alone and say so."""

    def _run(self, lines_layer, mock_find, mock_processing, **kwargs):
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Origin Point"]), "roads": network}.get(name)
        hull_layer = MagicMock()

        def run_side_effect(alg_id, params, context=None):
            if alg_id == "native:serviceareafrompoint":
                return {"OUTPUT_LINES": lines_layer}
            if alg_id == "native:convexhull":
                return {"OUTPUT": hull_layer}
            raise AssertionError(f"unexpected alg_id {alg_id}")
        mock_processing.run.side_effect = run_side_effect
        return calculate_service_area("facilities", "roads", 1000, **kwargs)

    @patch("cartogen_ai.core.agent.tools.logistics_tools._replace_named_layer")
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_a_zero_length_result_does_not_touch_the_project(
        self, mock_find, _enum, _ctx, mock_processing, _project, mock_replace
    ):
        degenerate = MagicMock()
        _real_looking_lines(degenerate, length=0.0)  # one feature, zero length -- the observed shape

        res = self._run(degenerate, mock_find, mock_processing)

        mock_replace.assert_not_called()
        self.assertIn("error", res)
        self.assertIn("zero length", res["error"])
        self.assertEqual(res["skipped"][0]["stage"], "serviceareafrompoint")

    @patch("cartogen_ai.core.agent.tools.logistics_tools._replace_named_layer")
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_a_real_result_still_replaces_as_before(
        self, mock_find, _enum, _ctx, mock_processing, _project, mock_replace
    ):
        good = MagicMock()
        _real_looking_lines(good, length=5400.0)

        res = self._run(good, mock_find, mock_processing)

        self.assertTrue(res.get("success"), res)
        self.assertTrue(mock_replace.called)

    @patch("cartogen_ai.core.agent.tools.logistics_tools._replace_named_layer")
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_a_metres_versus_hours_mixup_is_called_out(
        self, mock_find, _enum, _ctx, mock_processing, _project, mock_replace
    ):
        good = MagicMock()
        _real_looking_lines(good, length=1.0)
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Origin Point"]), "roads": network}.get(name)
        mock_processing.run.side_effect = lambda alg_id, params, context=None: (
            {"OUTPUT_LINES": good} if alg_id == "native:serviceareafrompoint" else {"OUTPUT": MagicMock()})

        res = calculate_service_area("facilities", "roads", 1)  # "1 hour" meant, strategy left at 'shortest'

        self.assertTrue(any("METRES" in n for n in res.get("notes", [])), res)


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
            _real_looking_lines(lines_layer)
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
        _real_looking_lines(lines_layer)
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

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.map_intelligence.process_map_output")
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProcessingContext", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_single_band_hull_gets_proximity_buffer_styling(
        self, mock_find, _mock_qgis_enum, _mock_context_cls, mock_processing, mock_project, mock_process_output,
    ):
        # Live-reported, 2026-09-28: the single-band hull polygon (the common case)
        # was left at QGIS's raw default new-layer symbology -- unlike the lines_layer
        # (already gets output_role="route_line") and the multi-band merged layer
        # (already gets apply_graduated_style) right next to it. This is the fix.
        facilities_layer = _stop_layer(["Warehouse"])
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": facilities_layer, "roads": network}.get(name)

        lines_layer = MagicMock()
        _real_looking_lines(lines_layer)
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
        # Called once for the lines_layer (route_line) and once for the hull (proximity_buffer).
        hull_calls = [c for c in mock_process_output.call_args_list if c.args[0] is hull_layer]
        self.assertEqual(len(hull_calls), 1)
        self.assertEqual(hull_calls[0].kwargs.get("output_role"), "proximity_buffer")
        self.assertEqual(hull_calls[0].kwargs.get("source_layer_id"), facilities_layer.id())


class TestReplaceNamedLayer(unittest.TestCase):
    """Live-reported, 2026-09-28: a multi-step session ("health facilities beyond 1hr", then
    "population outside the catchment") left THREE separately-named-but-identical
    "Origin Point_service_area_0"-style layers stacked in the project -- described as the map
    "losing control" on anything beyond a single simple request. Root cause:
    calculate_service_area's output layer names are deterministic (derived from the facility
    layer's own name and feature index, not a per-call id), and QgsProject.addMapLayer() does
    not deduplicate by name at all -- re-running the same analysis just buried the old layer
    under a new one with the identical name. _replace_named_layer is the fix: remove every
    existing layer already using that name before adding the new one."""

    def test_removes_every_existing_layer_with_that_name_before_adding(self):
        project = MagicMock()
        stale_a, stale_b = MagicMock(), MagicMock()
        stale_a.id.return_value = "stale_a_id"
        stale_b.id.return_value = "stale_b_id"
        project.mapLayersByName.return_value = [stale_a, stale_b]
        new_layer = MagicMock()

        with patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True) as mock_qgs_project:
            mock_qgs_project.instance.return_value = project
            lt._replace_named_layer("Origin Point_service_area_0", new_layer)

        project.mapLayersByName.assert_called_once_with("Origin Point_service_area_0")
        project.removeMapLayer.assert_any_call("stale_a_id")
        project.removeMapLayer.assert_any_call("stale_b_id")
        self.assertEqual(project.removeMapLayer.call_count, 2)
        new_layer.setName.assert_called_once_with("Origin Point_service_area_0")
        project.addMapLayer.assert_called_once_with(new_layer)

    def test_no_existing_layer_just_adds(self):
        project = MagicMock()
        project.mapLayersByName.return_value = []
        new_layer = MagicMock()

        with patch("cartogen_ai.core.agent.tools.logistics_tools.QgsProject", create=True) as mock_qgs_project:
            mock_qgs_project.instance.return_value = project
            lt._replace_named_layer("fresh_layer", new_layer)

        project.removeMapLayer.assert_not_called()
        project.addMapLayer.assert_called_once_with(new_layer)


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
        _real_looking_lines(lines_layer)
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
        _real_looking_lines(lines_layer)
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
        _real_looking_lines(lines_layer)
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
    @patch("cartogen_ai.core.agent.tools.logistics_tools.Qgis", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_serviceareafrompoint_gets_a_geometry_skip_invalid_context(
        self, mock_find, mock_processing_enum, mock_processing, mock_project
    ):
        """2026-09-10 fix: serviceareafrompoint's own 'invalid geometry' abort is
        the exact failure the error message names its own remedy for ('change
        the Invalid features filtering option') -- confirm calculate_service_area
        actually asks for that remedy (it builds its context through _network_context,
        which applies setInvalidGeometryCheck -- see TestNetworkContextAndStartPoint)
        rather than just isolating the failure after the fact."""
        network = MagicMock()
        mock_find.side_effect = lambda name: {"facilities": _stop_layer(["Warehouse"]), "roads": network}.get(name)

        lines_layer = MagicMock()
        _real_looking_lines(lines_layer)
        hull_layer = MagicMock()
        mock_context_instance = self.mock_context

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
        self.mock_network_context_fn.assert_called_once_with(
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

    # people counted inside each reach polygon, by the name of the layer the zonal statistics is asked about
    POP_BY_LAYER_SUFFIX = {"_concave_hull": 500.0, "_road_buffer": 400.0, "_convex_hull": 700.0}

    def _run(self, reach_geometry=None, concave_error=None, **kw):
        """population_access_gap with every QGIS-touching collaborator mocked. Returns (result, mocks)."""
        from contextlib import ExitStack
        lt_path = "cartogen_ai.core.agent.tools.logistics_tools"
        with ExitStack() as stack:
            mock_estimate_pop = stack.enter_context(
                patch("cartogen_ai.core.agent.tools.raster_tools.estimate_population_exposure"))
            stack.enter_context(patch(f"{lt_path}.QgsProject", create=True))
            mock_processing = stack.enter_context(patch(f"{lt_path}.processing", create=True))
            mock_find = stack.enter_context(patch(f"{lt_path}._find_layer_by_name"))
            mock_calc = stack.enter_context(patch(f"{lt_path}.calculate_service_area"))
            mock_reach = stack.enter_context(patch(f"{lt_path}._road_reach_polygon"))
            mock_concave = stack.enter_context(patch(f"{lt_path}._concave_reach_polygon"))
            mock_wkb = stack.enter_context(patch(f"{lt_path}.QgsWkbTypes", create=True))
            stack.enter_context(patch(f"{lt_path}.QGIS_AVAILABLE", True))
            mock_wkb.geometryType.return_value = "polygon-sentinel"
            mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"

            area, hull, lines = MagicMock(), MagicMock(), MagicMock()
            mock_find.side_effect = lambda name: {
                "districts": area, "Facilities_service_area_0": hull,
                "Facilities_service_area_lines_0": lines}.get(name)
            mock_calc.return_value = {
                "facility_count": 3,
                "layers_created": ["Facilities_service_area_lines_0", "Facilities_service_area_0"],
            }
            intersect_mock = MagicMock()
            intersect_mock.featureCount.return_value = 10
            mock_reach.return_value = MagicMock()
            if concave_error:
                mock_concave.side_effect = RuntimeError(concave_error)
            else:
                mock_concave.return_value = MagicMock()
            mock_processing.run.side_effect = lambda alg, params: {"OUTPUT": intersect_mock if alg == "native:intersection" else MagicMock()}

            def pop(raster, layer_name):
                if layer_name == "districts":
                    return {"success": True, "total_population": 1000.0, "pop_source": "WorldPop", "pop_reference_year": "2020"}
                for suffix, value in self.POP_BY_LAYER_SUFFIX.items():
                    if layer_name.endswith(suffix):
                        return {"success": True, "total_population": value, "pop_source": "WorldPop", "pop_reference_year": "2020"}
                # the headline figure's layer carries no suffix
                head = {"convex_hull": 700.0, "road_buffer": 400.0}.get(reach_geometry, 500.0)
                return {"success": True, "total_population": head, "pop_source": "WorldPop", "pop_reference_year": "2020"}
            mock_estimate_pop.side_effect = pop
            args = ("Facilities", "roads", "YEM_population_2020", "districts", 1000)
            if reach_geometry:
                kw["reach_geometry"] = reach_geometry
            res = population_access_gap(*args, **kw)
            return res, mock_reach, mock_processing

    def test_propagates_estimate_fields_from_population_exposure(self):
        res, _, _ = self._run()
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["total_population"], 1000.0)
        self.assertEqual(res["reachable_population"], 500.0)        # the headline is the concave hull
        self.assertEqual(res["gap_population"], 500.0)
        self.assertEqual(res["gap_population_est"], 500.0)
        self.assertEqual(res["gap_percent"], 50.0)
        self.assertEqual(res["pop_source"], "WorldPop")
        self.assertEqual(res["pop_reference_year"], "2020")
        self.assertEqual(
            res["confidence"],
            "estimate (modeled network reachability + gridded population raster; not field-verified)",
        )

    def test_three_labelled_figures_and_their_range_are_reported(self):
        """F09 (owner decision 2026-09-30): concave hull is the headline; buffer and convex hull bracket it."""
        res, _, _ = self._run()
        self.assertEqual(res["reach_geometry"], "concave_hull")
        by_method = {f["method"]: f for f in res["reach_figures"]}
        self.assertEqual(set(by_method), {"concave_hull", "road_buffer", "convex_hull"})
        self.assertEqual(by_method["road_buffer"]["reachable_population"], 400.0)
        self.assertEqual(by_method["concave_hull"]["reachable_population"], 500.0)
        self.assertEqual(by_method["convex_hull"]["reachable_population"], 700.0)
        self.assertTrue(by_method["concave_hull"]["is_headline"])
        self.assertTrue(by_method["convex_hull"]["is_upper_bound"])
        self.assertFalse(res["is_upper_bound_on_reach"])
        self.assertEqual(res["reachable_population_range"], [400.0, 700.0])

    def test_the_headline_can_be_the_buffer(self):
        res, mock_reach, _ = self._run(reach_geometry="road_buffer")
        self.assertEqual(res["reach_geometry"], "road_buffer")
        self.assertEqual(res["reachable_population"], 400.0)
        self.assertIn("buffered by 500 m", res["reach_note"])
        mock_reach.assert_called_once()

    def test_the_convex_hull_headline_is_labelled_an_upper_bound(self):
        res, _, _ = self._run(reach_geometry="convex_hull")
        self.assertEqual(res["reach_geometry"], "convex_hull")
        self.assertTrue(res["is_upper_bound_on_reach"])
        self.assertIn("UPPER BOUND", res["reach_note"])

    def test_an_unavailable_concave_hull_falls_back_and_says_so(self):
        res, _, _ = self._run(concave_error="GEOS older than 3.11")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["reach_geometry"], "road_buffer")
        self.assertIn("could not be computed", res["headline_fallback"])
        failed = next(f for f in res["reach_figures"] if f["method"] == "concave_hull")
        self.assertFalse(failed["available"])
        self.assertEqual(res["reachable_population_range"], [400.0, 700.0])

    def test_bad_reach_arguments_are_refused_before_any_work(self):
        from cartogen_ai.core.agent.tools import logistics_tools as lt
        with patch.object(lt, "QGIS_AVAILABLE", True):
            self.assertIn("error", population_access_gap("f", "r", "p", "a", 1, reach_geometry="blob"))
            self.assertIn("error", population_access_gap("f", "r", "p", "a", 1, reach_buffer_m=0))
            self.assertIn("error", population_access_gap("f", "r", "p", "a", 1, reach_buffer_m="far"))


@patch("cartogen_ai.core.agent.tools.logistics_tools._geoms_in_crs", new=lambda geoms, a, b: list(geoms))
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


@patch("cartogen_ai.core.agent.tools.logistics_tools._geoms_in_crs", new=lambda geoms, a, b: list(geoms))
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


class TestBuildNetworkDistanceMatrix(_LineNetworkMixin, unittest.TestCase):
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

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    def test_no_direction_field_mirrors_instead_of_recomputing(self, mock_processing):
        """BUG-2026-09-25-2 follow-up: without a direction_field the network is
        undirected for this call, so (j, i) should be copied from (i, j) rather
        than triggering its own processing.run() call -- n(n-1)/2 calls for n
        stops instead of n(n-1)."""
        result_feat = MagicMock()
        result_feat.__getitem__.side_effect = lambda key: 777.0 if key == "cost" else None
        result_layer = MagicMock()
        result_layer.getFeatures.return_value = [result_feat]
        mock_processing.run.return_value = {"OUTPUT": result_layer}

        geoms = [MagicMock(), MagicMock(), MagicMock()]
        for i, g in enumerate(geoms):
            g.asPoint.return_value = MagicMock(x=lambda i=i: float(i), y=lambda: 0.0)

        matrix = _build_network_distance_matrix(MagicMock(), geoms)

        self.assertEqual(mock_processing.run.call_count, 3)  # 3 choose 2, not 3*2
        for i in range(3):
            for j in range(3):
                if i != j:
                    self.assertEqual(matrix[i][j], 777.0)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.processing", create=True)
    def test_direction_field_keeps_full_n_squared_calls(self, mock_processing):
        """A one-way-aware network is NOT safe to mirror -- A->B and B->A can be
        genuinely different routes, so every ordered pair still gets its own call."""
        result_layer = MagicMock()
        result_layer.getFeatures.return_value = []
        mock_processing.run.return_value = {"OUTPUT": result_layer}

        geoms = [MagicMock(), MagicMock(), MagicMock()]
        for i, g in enumerate(geoms):
            g.asPoint.return_value = MagicMock(x=lambda i=i: float(i), y=lambda: 0.0)

        _build_network_distance_matrix(MagicMock(), geoms, extra_params={"DIRECTION_FIELD": "oneway"})

        self.assertEqual(mock_processing.run.call_count, 6)  # 3*2, unchanged


class TestBuildRoadSnappedRoute(_LineNetworkMixin, unittest.TestCase):
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


_LT = "cartogen_ai.core.agent.tools.logistics_tools."


class TestNetworkContextAndStartPoint(unittest.TestCase):
    """The two helpers behind BUG-2026-09-24-5. Their measured behaviour in real QGIS is in
    tests/test_network_units_live.py; these pin the logic that must not regress."""

    def _context(self, project_ellipsoid, check=None):
        with patch(_LT + "QgsProcessingContext", create=True) as ctx_cls,              patch(_LT + "QgsProject", create=True) as project_cls:
            project_cls.instance.return_value.ellipsoid.return_value = project_ellipsoid
            ctx = _network_context(check)
        return ctx_cls.return_value, ctx, project_cls.instance.return_value

    def test_no_project_ellipsoid_falls_back_to_wgs84(self):
        # 'NONE' is QGIS's own truthy sentinel for "no ellipsoid": the same trap _make_distance_area documents
        for none_like in ("NONE", "", None):
            ctx, returned, _ = self._context(none_like)
            self.assertIs(returned, ctx)
            ctx.setEllipsoid.assert_called_once_with("WGS84")

    def test_the_projects_own_ellipsoid_is_respected(self):
        ctx, _, _ = self._context("EPSG:7019")
        ctx.setEllipsoid.assert_called_once_with("EPSG:7019")

    def test_the_context_gets_the_project_and_an_explicit_ellipsoid(self):
        # setProject alone leaves the context's ellipsoid unset (measured in real QGIS: 'NONE' even
        # when the project had EPSG:7030), so the explicit setEllipsoid is what makes costs metres.
        ctx, _, project = self._context("NONE")
        ctx.setProject.assert_called_once_with(project)
        ctx.setEllipsoid.assert_called_once()

    def test_invalid_geometry_check_is_applied_only_when_given(self):
        ctx, _, _ = self._context("NONE", check="skip-invalid")
        ctx.setInvalidGeometryCheck.assert_called_once_with("skip-invalid")
        ctx2, _, _ = self._context("NONE")
        ctx2.setInvalidGeometryCheck.assert_not_called()

    @staticmethod
    def _crs(valid=True, name="x"):
        c = MagicMock(name=name)
        c.isValid.return_value = valid
        return c

    def _start_point(self, source_crs, net_crs, transformed=(7.0, 8.0)):
        network = MagicMock()
        network.crs.return_value = net_crs
        point = MagicMock()
        with patch(_LT + "QgsPointXY", create=True) as pt_cls,              patch(_LT + "QgsCoordinateTransform", create=True) as xf_cls,              patch(_LT + "QgsProject", create=True):
            pt_cls.return_value.x.return_value, pt_cls.return_value.y.return_value = 1.0, 2.0
            out_pt = MagicMock()
            out_pt.x.return_value, out_pt.y.return_value = transformed
            xf_cls.return_value.transform.return_value = out_pt
            text = _point_for_network(point, source_crs, network)
        return text, xf_cls

    def test_same_crs_passes_the_coordinates_through(self):
        crs = self._crs()
        text, xf_cls = self._start_point(crs, crs)
        self.assertEqual(text, "1.0,2.0")
        xf_cls.assert_not_called()

    def test_a_different_crs_is_transformed_into_the_networks(self):
        src, net = self._crs(name="src"), self._crs(name="net")
        text, xf_cls = self._start_point(src, net)
        self.assertEqual(text, "7.0,8.0")
        self.assertEqual(xf_cls.call_args.args[:2], (src, net))    # source -> network, not the reverse

    def test_unknown_or_invalid_crs_is_not_guessed_at(self):
        text, xf_cls = self._start_point(None, self._crs())
        self.assertEqual(text, "1.0,2.0")
        text, xf_cls = self._start_point(self._crs(valid=False), self._crs())
        self.assertEqual(text, "1.0,2.0")
        xf_cls.assert_not_called()

    def test_a_failing_transform_raises_instead_of_routing_from_the_wrong_place(self):
        network = MagicMock()
        network.crs.return_value = self._crs(name="net")
        with patch(_LT + "QgsPointXY", create=True),              patch(_LT + "QgsProject", create=True),              patch(_LT + "QgsCoordinateTransform", create=True) as xf_cls:
            xf_cls.return_value.transform.side_effect = RuntimeError("no transform")
            with self.assertRaises(RuntimeError):
                _point_for_network(MagicMock(), self._crs(name="src"), network)


class TestReachBound(unittest.TestCase):
    """_reach_metres must be a true UPPER bound on how far (straight line) anything can be and still be
    within the cost: the clip is exact only if it is."""

    def test_shortest_is_the_cost_itself_and_multi_band_uses_the_largest(self):
        self.assertEqual(_reach_metres([500], "shortest", 50), 500.0)
        self.assertEqual(_reach_metres([300, 5000, 900], "shortest", 50), 5000.0)

    def test_fastest_uses_the_fastest_speed_anywhere_in_the_network(self):
        self.assertEqual(_reach_metres([0.5], "fastest", 50), 25000.0)                 # 0.5 h at 50 km/h
        self.assertEqual(_reach_metres([0.5], "fastest", 50, max_field_speed=90), 45000.0)
        self.assertEqual(_reach_metres([0.5], "fastest", 100, max_field_speed=30), 50000.0)   # default can be the fastest
        self.assertEqual(_reach_metres([0.2, 1.0], "fastest", 50), 50000.0)

    def test_max_speed_reads_the_field_and_says_none_when_it_cannot(self):
        network = MagicMock()
        network.maximumValue.return_value = 90.0
        self.assertEqual(_max_speed_in_field(network, "speed"), 90.0)
        for bad in (None, 0, -5, "not a number"):
            network.maximumValue.return_value = bad
            self.assertIsNone(_max_speed_in_field(network, "speed"), bad)
        network.maximumValue.side_effect = RuntimeError("provider gone")
        self.assertIsNone(_max_speed_in_field(network, "speed"))


@patch(_LT + "log_event")
class TestClipNetworkToReach(unittest.TestCase):
    """Every way _clip_network_to_reach must decline to clip, so the answer is exactly what the whole
    network would give (the geometry equality itself is tested in tests/test_network_clip_live.py)."""

    def _network(self, total):
        net = MagicMock()
        net.featureCount.return_value = total
        return net

    def _clip(self, network, reach=1000.0, clipped_count=100, hit=True, materialize_error=None):
        clipped = MagicMock()
        clipped.featureCount.return_value = clipped_count
        feat = MagicMock()
        feat.geometry.return_value.intersects.return_value = hit
        clipped.getFeatures.return_value = [feat]
        if materialize_error:
            network.materialize.side_effect = materialize_error
        else:
            network.materialize.return_value = clipped
        point = SimpleNamespace(x=lambda: 35.93, y=lambda: 31.95)      # a real-looking start point
        with patch(_LT + "QgsProject", create=True),              patch(_LT + "QgsCoordinateReferenceSystem", create=True) as crs_cls,              patch(_LT + "QgsCoordinateTransform", create=True) as xf_cls,              patch(_LT + "QgsGeometry", create=True),              patch(_LT + "QgsPointXY", create=True),              patch(_LT + "QgsFeatureRequest", create=True):
            crs_cls.fromProj.return_value.isValid.return_value = True
            xf_cls.return_value.transform.return_value = point
            out = _clip_network_to_reach(network, point, reach)
        return out, clipped, crs_cls

    def test_a_worthwhile_clip_returns_the_smaller_layer(self, _log):
        net = self._network(10000)
        (layer, info), clipped, crs_cls = self._clip(net, clipped_count=800)
        self.assertIs(layer, clipped)
        self.assertEqual(info, {"applied": True, "roads_full": 10000, "roads_used": 800})
        proj = crs_cls.fromProj.call_args.args[0]
        self.assertIn("+proj=aeqd +lat_0=31.95", proj)        # centred on the start: distances from it are true metres
        self.assertIn("+lon_0=35.93", proj)
        self.assertIn("+units=m", proj)

    def test_small_networks_are_left_alone(self, _log):
        net = self._network(lt.BACKGROUND_MIN_FEATURES - 1)
        (layer, info), _, _ = self._clip(net)
        self.assertIs(layer, net)
        self.assertFalse(info["applied"])
        net.materialize.assert_not_called()

    def test_an_enormous_reach_is_not_clipped(self, _log):
        net = self._network(10000)
        (layer, info), _, _ = self._clip(net, reach=lt._CLIP_MAX_REACH_METRES)
        self.assertIs(layer, net)
        self.assertFalse(info["applied"])

    def test_a_box_that_still_holds_most_roads_is_not_worth_copying(self, _log):
        net = self._network(10000)
        (layer, info), _, _ = self._clip(net, clipped_count=9000)        # 90%
        self.assertIs(layer, net)
        self.assertFalse(info["applied"])

    def test_no_road_within_reach_keeps_the_whole_network(self, _log):
        # QGIS snaps a far-away start to the nearest road however far; a clipped network could snap
        # to a different one, so the old behaviour is kept.
        net = self._network(10000)
        (layer, info), _, _ = self._clip(net, clipped_count=50, hit=False)
        self.assertIs(layer, net)
        self.assertFalse(info["applied"])

    def test_anything_going_wrong_keeps_the_whole_network(self, _log):
        net = self._network(10000)
        (layer, info), _, _ = self._clip(net, materialize_error=RuntimeError("cannot transform"))
        self.assertIs(layer, net)
        self.assertFalse(info["applied"])
        _log.assert_called()                                   # and it is recorded (metadata only)

    def test_an_unreadable_size_keeps_the_whole_network(self, _log):
        net = MagicMock()
        net.featureCount.side_effect = RuntimeError("provider gone")
        layer, info = _clip_network_to_reach(net, MagicMock(), 1000.0)
        self.assertIs(layer, net)
        self.assertFalse(info["applied"])


class TestEstimateRoadSpeeds(unittest.TestCase):
    """BUG-2026-09-25-3: with real maxspeed data present on almost no roads, this tool fills an
    'assumed_speed_kmh' field from a fixed per-road-class table, keyed off 'fclass' (Geofabrik) or
    'highway' (OSM/Overpass)."""

    def test_confirmation_gate(self):
        res = lt.estimate_road_speeds("Roads", confirmed=False)
        self.assertEqual(res.get("status"), "PREVIEW_REQUIRED")
        self.assertTrue(res.get("requires_confirmation"))
        self.assertTrue(res.get("is_destructive"))

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_layer_not_found(self, mock_find):
        mock_find.return_value = None
        res = lt.estimate_road_speeds("Roads", confirmed=True)
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._network_geometry_error", return_value=None)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_no_class_field_errors(self, mock_find, mock_geom_err):
        layer = MagicMock()
        layer.fields.return_value = [MagicMock(name=lambda: "osm_id")]
        layer.fields.return_value[0].name.return_value = "osm_id"
        mock_find.return_value = layer
        res = lt.estimate_road_speeds("Roads", confirmed=True)
        self.assertIn("error", res)
        self.assertIn("fclass", res["error"])

    def _make_road_layer(self, features, existing_fields=("fclass",), index_map=None):
        """index_map covers indexOf() after the tool's own addAttributes()/updateFields()
        would have run -- a MagicMock layer doesn't actually gain a new field from those
        calls, so the test supplies the post-update index mapping directly (fclass=0,
        assumed_speed_kmh=1 by default, matching what the real tool would end up with)."""
        field_mocks = [MagicMock() for _ in existing_fields]
        for m, name in zip(field_mocks, existing_fields):
            m.name.return_value = name
        mapping = index_map or {name: i for i, name in enumerate(existing_fields)}
        if "assumed_speed_kmh" not in mapping:
            mapping = {**mapping, "assumed_speed_kmh": len(existing_fields)}

        class _Fields:
            def __iter__(self):
                return iter(field_mocks)

            def indexOf(self, name):
                return mapping.get(name, -1)

        layer = MagicMock()
        layer.fields.return_value = _Fields()
        layer.getFeatures.return_value = features
        return layer

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QVariant", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._network_geometry_error", return_value=None)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_fills_speed_from_road_class_table(self, mock_find, mock_geom_err, mock_qvariant, mock_qfield):
        feat_motorway = MagicMock()
        feat_motorway.attribute.side_effect = lambda k: "motorway" if k == "fclass" else None
        feat_residential = MagicMock()
        feat_residential.attribute.side_effect = lambda k: "residential" if k == "fclass" else None
        layer = self._make_road_layer([feat_motorway, feat_residential])
        # After addAttributes/updateFields, indexOf('assumed_speed_kmh') should resolve -- fixed index 1.
        mock_find.return_value = layer

        res = lt.estimate_road_speeds("Roads", confirmed=True)

        self.assertTrue(res.get("success"))
        self.assertEqual(res["features_updated"], 2)
        layer.startEditing.assert_called_once()
        layer.commitChanges.assert_called_once()
        calls = layer.changeAttributeValue.call_args_list
        self.assertEqual(calls[0].args, (feat_motorway.id(), 1, 100.0))
        self.assertEqual(calls[1].args, (feat_residential.id(), 1, 40.0))

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QVariant", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._network_geometry_error", return_value=None)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_a_refused_new_field_is_a_clear_error_not_a_bare_minus_one(self, mock_find, mock_geom_err, mock_qv, mock_qf):
        # rc11 smoke test C1: "estimate_road_speeds failed: '-1'" when the provider would not add the field.
        feat = MagicMock()
        feat.attribute.side_effect = lambda k: "primary" if k == "fclass" else None
        # indexOf never resolves assumed_speed_kmh: map it to -1 explicitly
        layer = self._make_road_layer([feat], existing_fields=("fclass", "speed_kmh"),
                                      index_map={"fclass": 0, "speed_kmh": 1, "assumed_speed_kmh": -1})
        mock_find.return_value = layer

        res = lt.estimate_road_speeds("Roads", confirmed=True)

        self.assertNotIn("success", res)
        self.assertIn("does not accept new fields", res["error"])
        self.assertIn("speed_kmh", res["error"])          # points at the speed field the layer already has
        layer.startEditing.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QVariant", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._network_geometry_error", return_value=None)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_unknown_road_class_uses_default_speed(self, mock_find, mock_geom_err, mock_qvariant, mock_qfield):
        feat = MagicMock()
        feat.attribute.side_effect = lambda k: "made_up_class" if k == "fclass" else None
        layer = self._make_road_layer([feat])
        mock_find.return_value = layer

        res = lt.estimate_road_speeds("Roads", default_speed_kmh=25, confirmed=True)

        self.assertTrue(res.get("success"))
        self.assertIn("made_up_class", res.get("unknown_road_classes", []))
        layer.changeAttributeValue.assert_called_once_with(feat.id(), 1, 25.0)

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QVariant", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._network_geometry_error", return_value=None)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_default_overwrite_false_skips_features_with_existing_value(self, mock_find, mock_geom_err,
                                                                          mock_qvariant, mock_qfield):
        feat = MagicMock()
        # attribute(0) = fclass, attribute(1) = existing assumed_speed_kmh already set
        feat.attribute.side_effect = lambda k: "motorway" if k == "fclass" else 55.0
        layer = self._make_road_layer([feat], existing_fields=("fclass", "assumed_speed_kmh"))
        mock_find.return_value = layer

        res = lt.estimate_road_speeds("Roads", confirmed=True)

        self.assertTrue(res.get("success"))
        self.assertEqual(res["features_updated"], 0)
        self.assertEqual(res["features_left_unchanged"], 1)
        layer.changeAttributeValue.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._network_geometry_error",
           return_value="'Roads' is not a line layer, so it can't be used as a road network.")
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_non_line_layer_rejected(self, mock_find, mock_geom_err):
        layer = self._make_road_layer([])
        mock_find.return_value = layer
        res = lt.estimate_road_speeds("Roads", confirmed=True)
        self.assertIn("error", res)
        self.assertIn("line layer", res["error"])

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QVariant", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._network_geometry_error", return_value=None)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_country_override_scales_known_country(self, mock_find, mock_geom_err, mock_qvariant, mock_qfield):
        """BUG-2026-09-25-3 follow-up: a known country code should use its real legal
        urban/rural/motorway defaults (COUNTRY_SPEED_TIERS_KMH) instead of the generic table."""
        feat_motorway = MagicMock()
        feat_motorway.attribute.side_effect = lambda k: "motorway" if k == "fclass" else None
        feat_residential = MagicMock()
        feat_residential.attribute.side_effect = lambda k: "residential" if k == "fclass" else None
        layer = self._make_road_layer([feat_motorway, feat_residential])
        mock_find.return_value = layer

        res = lt.estimate_road_speeds("Roads", country="jo", confirmed=True)

        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("country_used"), "JO")
        calls = layer.changeAttributeValue.call_args_list
        self.assertEqual(calls[0].args, (feat_motorway.id(), 1, 110.0))  # Jordan motorway
        self.assertEqual(calls[1].args, (feat_residential.id(), 1, 40.0))  # Jordan urban

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QVariant", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._network_geometry_error", return_value=None)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_country_override_leaves_pedestrian_classes_untouched(self, mock_find, mock_geom_err, mock_qvariant, mock_qfield):
        """A country override should scale vehicle road classes only -- walking/cycling speeds
        aren't legal-speed-limit-driven and should stay exactly as the generic table has them."""
        feat = MagicMock()
        feat.attribute.side_effect = lambda k: "footway" if k == "fclass" else None
        layer = self._make_road_layer([feat])
        mock_find.return_value = layer

        res = lt.estimate_road_speeds("Roads", country="DE", confirmed=True)

        self.assertTrue(res.get("success"))
        layer.changeAttributeValue.assert_called_once_with(feat.id(), 1, 5.0)  # unchanged footway speed

    @patch("cartogen_ai.core.agent.tools.logistics_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools.QVariant", create=True)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._network_geometry_error", return_value=None)
    @patch("cartogen_ai.core.agent.tools.logistics_tools._find_layer_by_name")
    def test_unrecognized_country_falls_back_to_generic_table(self, mock_find, mock_geom_err, mock_qvariant, mock_qfield):
        feat = MagicMock()
        feat.attribute.side_effect = lambda k: "motorway" if k == "fclass" else None
        layer = self._make_road_layer([feat])
        mock_find.return_value = layer

        res = lt.estimate_road_speeds("Roads", country="ZZ", confirmed=True)

        self.assertTrue(res.get("success"))
        self.assertNotIn("country_used", res)
        self.assertIn("ZZ", res["note"])
        layer.changeAttributeValue.assert_called_once_with(feat.id(), 1, 100.0)  # generic motorway speed

    def test_country_speed_overrides_helper_is_empty_for_unknown_country(self):
        self.assertEqual(lt._country_speed_overrides("ZZ"), {})
        self.assertEqual(lt._country_speed_overrides(None), {})

    def test_country_speed_overrides_helper_applies_link_factor(self):
        overrides = lt._country_speed_overrides("DE")
        self.assertEqual(overrides["motorway"], 130)
        self.assertEqual(overrides["motorway_link"], round(130 * 0.75))
        self.assertEqual(overrides["residential"], 50)


if __name__ == "__main__":
    unittest.main()
