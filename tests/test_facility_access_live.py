# -*- coding: utf-8 -*-
"""classify_facilities_by_access agrees with routed costs (real QGIS) -- F08, rc7 smoke test.

Facilities sit ON road crossings of a grid network, so the access leg is ~0 and the only difference
between the two methods is the method itself: 'within' must equal 'travel_time_matrix cost <= limit'.
Facilities whose routed cost is within MARGIN_M of the limit are skipped: the partial last road
segment of a service area is cut at the limit, and a facility sitting right at it can go either way.

Needs real qgis.core + the Processing plugin (skipped otherwise). Written without a QGIS install;
its first execution is CI."""
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsProject
    from tests.test_network_clip_live import CENTRE, LAT, LON0, SPAN, _grid, _origins
    STEP = SPAN / 100

LIMIT_M = 3000.0
MARGIN_M = 250.0
N = 100
# (rows, columns) offsets from the origin's own crossing (row 50, column 50)
OFFSETS = [(0, 1), (5, 5), (10, 0), (0, 15), (20, 20), (30, 30), (45, 0), (0, -8), (-12, 9), (-40, -40)]


def _lonlat(di, dj):
    return (LON0 + (50 + dj) * STEP, LAT + (50 + di) * STEP)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings -- run from an OSGeo4W/QGIS Python")
class TestClassificationMatchesRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)
        from cartogen_ai.core.agent.tools import logistics_tools as lt
        cls.lt = lt

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        _grid("EPSG:4326", N)
        _origins("EPSG:4326", [CENTRE], name="origin")

    def _routed_cost(self, index, lonlat):
        name = f"one_facility_{index}"
        _origins("EPSG:4326", [lonlat], name=name)
        res = self.lt.travel_time_matrix("origin", name, "roads")
        self.assertTrue(res.get("success"), res)
        costs = [c for row in res["matrix"].values() for c in row.values() if c is not None]
        self.assertTrue(costs, res)
        return float(costs[0])

    def test_within_equals_routed_cost_under_the_limit(self):
        lonlats = [_lonlat(di, dj) for di, dj in OFFSETS]
        facilities = _origins("EPSG:4326", lonlats, name="facilities")
        res = self.lt.classify_facilities_by_access("origin", "facilities", "roads", LIMIT_M)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["total"], len(OFFSETS))
        out = QgsProject.instance().mapLayersByName(res["layer_created"])[0]
        classes = [f["access_class"] for f in out.getFeatures()]
        dists = [f["dist_to_reach_m"] for f in out.getFeatures()]
        checked = 0
        for i, lonlat in enumerate(lonlats):
            cost = self._routed_cost(i, lonlat)
            if abs(cost - LIMIT_M) < MARGIN_M:
                continue
            checked += 1
            expected = "within" if cost <= LIMIT_M else "beyond"
            self.assertEqual(classes[i], expected, f"facility {i} routed cost {cost:.0f} m, limit {LIMIT_M:.0f} m")
        self.assertGreaterEqual(checked, 6, "too few facilities away from the limit to mean anything")
        self.assertEqual(facilities.featureCount(), len(OFFSETS))
        self.assertIn("within", classes)
        self.assertIn("beyond", classes)
        self.assertTrue(all(d is None or d >= 0 for d in dists))

    def test_a_small_matrix_is_not_blocked_by_the_size_guard(self):
        _origins("EPSG:4326", [_lonlat(0, k) for k in range(1, 6)], name="many")
        # 5 destinations is below the guard: it must still run.
        ok = self.lt.travel_time_matrix("origin", "many", "roads")
        self.assertTrue(ok.get("success"), ok)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings -- run from an OSGeo4W/QGIS Python")
class TestRoadBufferReachPolygon(unittest.TestCase):
    """F09: the reach polygon used for population is the reached roads buffered in metres, and is
    smaller than the convex hull that overstated the exposure (778,156 people) in the rc7 smoke test."""

    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)
        from cartogen_ai.core.agent.tools import logistics_tools as lt
        cls.lt = lt

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        # A network covering only the lower-left corner, so the reached roads form an L-shaped region:
        # a convex hull of them fills the empty corner, a road buffer does not.
        _grid("EPSG:4326", N, only_rows=30)
        _origins("EPSG:4326", [(LON0 + 10 * STEP, LAT + 10 * STEP)], name="origin")

    def _lines(self):
        res = self.lt.calculate_service_area("origin", "roads", 2500.0)
        self.assertTrue(res.get("success"), res)
        names = [n for n in res["layers_created"] if "_lines_" in n]
        return [QgsProject.instance().mapLayersByName(n)[0] for n in names]

    def _area_m2(self, layer):
        from qgis.core import QgsDistanceArea
        da = QgsDistanceArea()
        da.setEllipsoid("WGS84")
        da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
        return sum(da.measureArea(f.geometry()) for f in layer.getFeatures())

    def test_buffered_reach_is_smaller_than_the_hull_and_still_covers_the_roads(self):
        from qgis.core import QgsGeometry, QgsPointXY
        lines = self._lines()
        # 50 m against ~220 m road spacing: a buffer narrower than the gaps between roads, which is the
        # case where a hull overstates. (A 300 m buffer here came out LARGER than the hull -- 16.3 vs 12.0
        # km2 in CI -- because on a dense grid the buffer adds a margin past the last road and fills every
        # gap; see ROAD_BUFFER_REACH_NOTE.)
        reach = self.lt._road_reach_polygon(lines, 50.0, "reach")
        self.assertGreater(reach.featureCount(), 0)
        import processing
        hull = processing.run("native:convexhull", {"INPUT": lines[0], "OUTPUT": "memory:"})["OUTPUT"]
        self.assertLess(self._area_m2(reach), self._area_m2(hull), "the buffer must not be as large as the hull")
        reach_geom = QgsGeometry.unaryUnion([f.geometry() for f in reach.getFeatures()])
        self.assertTrue(reach_geom.contains(QgsGeometry.fromPointXY(QgsPointXY(LON0 + 10 * STEP, LAT + 10 * STEP))))
        for f in lines[0].getFeatures():
            self.assertTrue(reach_geom.contains(f.geometry().interpolate(f.geometry().length() / 2)),
                            "every reached road must lie inside its own buffer")

    def test_a_wider_buffer_covers_more(self):
        lines = self._lines()
        narrow = self._area_m2(self.lt._road_reach_polygon(lines, 100.0, "narrow"))
        wide = self._area_m2(self.lt._road_reach_polygon(lines, 600.0, "wide"))
        self.assertGreater(wide, narrow)


if __name__ == "__main__":
    unittest.main()
