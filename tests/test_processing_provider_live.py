# -*- coding: utf-8 -*-
"""Live-QGIS tests for the native Processing algorithms (audit F03, F04, F06 -> GitHub #139, #140, #142).

Written without a QGIS install: CI's first run is their first execution. The algorithms are run (not only their metadata) with
QgsProcessingAlgorithm.run(), the way the Processing dialog and a model would run them."""
import unittest

try:
    from qgis.core import (QgsFeature, QgsGeometry, QgsProcessingContext, QgsProcessingFeedback, QgsProject, QgsVectorLayer)
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _layer(kind, crs, wkts, name):
    layer = QgsVectorLayer(f"{kind}?crs={crs}&field=name:string", name, "memory")
    feats = []
    for i, wkt in enumerate(wkts):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(wkt))
        f.setAttributes([f"{name}{i}"])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


_KEEP_ALIVE = []        # a QgsProcessingContext owns the temporary output layers: if it is collected the layers are deleted


def _run(alg, params):
    context = QgsProcessingContext()
    _KEEP_ALIVE.append(context)
    context.setProject(QgsProject.instance())
    feedback = QgsProcessingFeedback()
    alg.initAlgorithm({})
    results, ok = alg.run(params, context, feedback)
    return results, ok, context, feedback


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestNativeProcessingAlgorithmsRun(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _hub(self, candidates, demand, **extra):
        from cartogen_ai.processing.provider import OptimalHubSitingAlgorithm
        params = {"INPUT_CANDIDATES": candidates, "INPUT_DEMAND": demand, "OUTPUT": "memory:"}
        params.update(extra)
        results, ok, context, _fb = _run(OptimalHubSitingAlgorithm(), params)
        out = context.getMapLayer(results["OUTPUT"]) if ok else None
        return ok, out

    def test_hub_siting_runs_on_valid_points_and_ranks_the_nearer_candidate_first(self):
        cands = _layer("Point", "EPSG:4326", ["POINT(0 0)", "POINT(0.1 0)"], "cand")
        demand = _layer("Point", "EPSG:4326", ["POINT(0.005 0)"], "dem")
        ok, out = self._hub(cands, demand)
        self.assertTrue(ok)
        rows = sorted(out.getFeatures(), key=lambda f: f["rank"])
        self.assertEqual([f["name"] for f in rows], ["cand0", "cand1"])
        self.assertAlmostEqual(rows[0]["avg_dist_m"], 556.6, delta=15)

    def test_demand_in_another_crs_is_transformed_not_misread(self):
        # 556.6 m east of the origin, written in EPSG:3857 metres. Read as degrees (the old behaviour) it was ~18 million m.
        cands = _layer("Point", "EPSG:4326", ["POINT(0 0)"], "cand")
        demand = _layer("Point", "EPSG:3857", ["POINT(556.6 0)"], "dem")
        ok, out = self._hub(cands, demand)
        self.assertTrue(ok)
        self.assertAlmostEqual(next(out.getFeatures())["avg_dist_m"], 556.6, delta=15)

    def test_a_multipart_candidate_is_skipped_not_a_crash(self):
        cands = _layer("Point", "EPSG:4326", ["POINT(0 0)", "MULTIPOINT((0.2 0),(0.3 0))"], "cand")
        demand = _layer("Point", "EPSG:4326", ["POINT(0.005 0)"], "dem")
        ok, out = self._hub(cands, demand)
        self.assertTrue(ok)
        self.assertEqual(out.featureCount(), 1)

    def test_no_usable_demand_is_an_error_not_a_success(self):
        cands = _layer("Point", "EPSG:4326", ["POINT(0 0)"], "cand")
        demand = _layer("Point", "EPSG:4326", [], "dem")
        ok, _out = self._hub(cands, demand)
        self.assertFalse(ok)

    def test_the_service_distance_threshold_is_in_metres(self):
        cands = _layer("Point", "EPSG:4326", ["POINT(0 0)"], "cand")
        demand = _layer("Point", "EPSG:4326", ["POINT(0.005 0)", "POINT(0.5 0)"], "dem")
        ok, out = self._hub(cands, demand, MAX_DISTANCE=1000.0)
        self.assertTrue(ok)
        feat = next(out.getFeatures())
        self.assertEqual(feat["served_count"], 1)

    def test_service_area_runs_on_a_valid_road(self):
        from cartogen_ai.processing.provider import CalculateServiceAreaAlgorithm
        roads = _layer("LineString", "EPSG:4326", ["LINESTRING(0 0, 0.01 0)"], "roads")
        fac = _layer("Point", "EPSG:4326", ["POINT(0 0)"], "fac")
        params = {"INPUT_FACILITIES": fac, "INPUT_NETWORK": roads, "TRAVEL_COST": 500.0, "STRATEGY": 0,
                  "DEFAULT_SPEED": 50.0, "OUTPUT_LINES": "memory:"}
        results, ok, context, _fb = _run(CalculateServiceAreaAlgorithm(), params)
        self.assertTrue(ok)
        out = context.getMapLayer(results["OUTPUT_LINES"])
        self.assertGreater(out.featureCount(), 0)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestServiceAreaUnitsCrsAndSchema(unittest.TestCase):
    """#156 / #157 (audit F20, F21)."""

    # About 5 km along the equator as 45 separate ~111 m road features. CI showed the network algorithm returns WHOLE road features
    # (a single 5 km feature, or one polyline with many vertices, came back entirely for a 1,000 m cost), so the reach can only be
    # told apart from the whole road when the road is made of many features.
    ROADS = [f"LINESTRING({i * 0.001:.3f} 0, {(i + 1) * 0.001:.3f} 0)" for i in range(45)]

    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _run_service_area(self, facility, strategy, cost, speed=36.0):
        from cartogen_ai.processing.provider import CalculateServiceAreaAlgorithm
        roads = _layer("LineString", "EPSG:4326", self.ROADS, "roads")
        params = {"INPUT_FACILITIES": facility, "INPUT_NETWORK": roads, "TRAVEL_COST": cost, "STRATEGY": strategy,
                  "DEFAULT_SPEED": speed, "OUTPUT_LINES": "memory:"}
        results, ok, context, _fb = _run(CalculateServiceAreaAlgorithm(), params)
        return ok, context.getMapLayer(results["OUTPUT_LINES"]) if ok else None

    def _length_m(self, layer):
        from qgis.core import QgsDistanceArea
        da = QgsDistanceArea()
        da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
        da.setEllipsoid("WGS84")
        from qgis.core import QgsGeometry
        merged = QgsGeometry.unaryUnion([f.geometry() for f in layer.getFeatures()])      # overlapping duplicates counted once
        return da.measureLength(merged)

    def test_fastest_cost_is_in_seconds_at_36_kmh_100_s_reaches_about_one_km(self):
        fac = _layer("Point", "EPSG:4326", ["POINT(0 0)"], "fac")
        ok, out = self._run_service_area(fac, 1, 100.0)
        self.assertTrue(ok)
        self.assertAlmostEqual(self._length_m(out), 1000.0, delta=250.0)       # 36 km/h = 10 m/s

    def test_fastest_cost_of_3600_seconds_covers_the_whole_road(self):
        fac = _layer("Point", "EPSG:4326", ["POINT(0 0)"], "fac")
        ok, out = self._run_service_area(fac, 1, 3600.0)
        self.assertAlmostEqual(self._length_m(out), 5000.0, delta=300.0)

    def test_a_facility_in_another_crs_starts_where_it_really_is(self):
        fac = _layer("Point", "EPSG:3857", ["POINT(0 0)"], "fac")          # (0, 0) in 3857 is (0, 0) in 4326: start of the road
        ok, out = self._run_service_area(fac, 0, 1000.0)
        self.assertTrue(ok)
        self.assertAlmostEqual(self._length_m(out), 1000.0, delta=150.0)

    def test_the_output_schema_is_the_child_algorithms_plus_the_facility_id(self):
        fac = _layer("Point", "EPSG:4326", ["POINT(0 0)"], "fac")
        ok, out = self._run_service_area(fac, 0, 500.0)
        names = [f.name() for f in out.fields()]
        self.assertIn("facility_fid", names)
        self.assertNotIn("name", names)                    # the road layer's own fields are not what the child returns
        feature = next(out.getFeatures())
        self.assertEqual(len(feature.attributes()), len(names))

    def test_no_usable_facility_is_an_error_not_an_empty_success(self):
        fac = _layer("Point", "EPSG:4326", [], "fac")
        ok, _out = self._run_service_area(fac, 0, 500.0)
        self.assertFalse(ok)

    def test_a_hub_siting_run_over_the_pair_limit_stops_with_a_message(self):
        from unittest.mock import patch
        from cartogen_ai.processing.provider import OptimalHubSitingAlgorithm
        cands = _layer("Point", "EPSG:4326", ["POINT(0 0)", "POINT(1 1)"], "c")
        demand = _layer("Point", "EPSG:4326", ["POINT(0 1)", "POINT(1 0)"], "d")
        with patch("cartogen_ai.processing.provider.MAX_DISTANCE_PAIRS", 3):
            results, ok, _ctx, feedback = _run(OptimalHubSitingAlgorithm(),
                                               {"INPUT_CANDIDATES": cands, "INPUT_DEMAND": demand, "OUTPUT": "memory:"})
        self.assertFalse(ok)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestHubSitingToolsMixedCrs(unittest.TestCase):
    """#142 for the agent tools (not only the native algorithm)."""

    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_optimal_hub_siting_measures_a_3857_demand_point_against_4326_candidates_correctly(self):
        from cartogen_ai.core.agent.tools.logistics_tools import optimal_hub_siting
        QgsProject.instance().addMapLayer(_layer("Point", "EPSG:4326", ["POINT(0 0)"], "cands"))
        QgsProject.instance().addMapLayer(_layer("Point", "EPSG:3857", ["POINT(556.6 0)"], "demand"))
        res = optimal_hub_siting("cands", "demand")
        self.assertTrue(res.get("success"), res)
        self.assertAlmostEqual(res["ranked_candidates"][0]["avg_distance"], 556.6, delta=15)

    def test_the_same_pair_in_one_crs_gives_the_same_distance(self):
        from cartogen_ai.core.agent.tools.logistics_tools import optimal_hub_siting
        QgsProject.instance().addMapLayer(_layer("Point", "EPSG:4326", ["POINT(0 0)"], "cands"))
        QgsProject.instance().addMapLayer(_layer("Point", "EPSG:4326", ["POINT(0.005 0)"], "demand"))
        res = optimal_hub_siting("cands", "demand")
        self.assertAlmostEqual(res["ranked_candidates"][0]["avg_distance"], 556.6, delta=15)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestNearestReachedRoadIsExact(unittest.TestCase):
    """#148 (audit F12): bounding-box ranking missed a straight road 1 m away behind three U-shaped roads whose envelopes
    enclose the facility."""

    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)

    def test_a_close_straight_road_beats_three_enclosing_u_shapes(self):
        from cartogen_ai.core.agent.tools.logistics_tools import _nearest_distances_m
        u = lambda a: f"LINESTRING({-a} {a}, {-a} {-a}, {a} {-a}, {a} {a})"        # noqa: E731  -- about 111 m away at a=0.001
        roads = _layer("LineString", "EPSG:4326",
                       [u(0.001), u(0.0011), u(0.0012), "LINESTRING(0.00001 -0.0005, 0.00001 0.0005)"], "roads")
        facility = _layer("Point", "EPSG:4326", ["POINT(0 0)"], "fac")
        distances = _nearest_distances_m(list(facility.getFeatures()), facility.crs(), [roads])
        self.assertEqual(len(distances), 1)
        self.assertLess(distances[0], 3.0)                       # ~1.1 m; the old box ranking returned ~111 m


if __name__ == "__main__":
    unittest.main()
