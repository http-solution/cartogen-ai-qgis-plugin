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


if __name__ == "__main__":
    unittest.main()
