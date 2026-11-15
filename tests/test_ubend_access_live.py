"""GitHub #148, rc48 hand test OI-148 (2026-10-24), on the U-shaped road fixture of docs/release_smoke_assets/inputs/smoke_network.gpkg.

The road runs 400 m south, 600 m east and 400 m north from its start (777700, 3541300). `Inside_the_U` sits 300 m from both arms; the nearest
road point on the west arm is 70 m from the start. `Beside_the_arm` is 80 m west of the west arm, 200 m from the start. So travel_time_matrix
gives road costs of about 70 and 200 m, and the access legs are about 300 and 80 m: counting them, 370 m (not within 300) and 280 m (within).
The answer in the hand test called both facilities reached because the legs were not reported. This pins all four numbers.
Written without a QGIS install: CI's first run is its first execution."""
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot
from tests.test_smoke_network_live import NETWORK, _add

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestUBendLegs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.road = _add(NETWORK, "smoke_ubend_road")
        self.facilities = _add(NETWORK, "smoke_ubend_facilities")
        origin = QgsVectorLayer("Point?crs=EPSG:32636&field=name:string", "ubend_start", "memory")
        f = QgsFeature(origin.fields())
        f.setGeometry(QgsGeometry.fromWkt("POINT(777700 3541300)"))
        f.setAttributes(["start"])
        origin.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(origin)

    def _ids(self):
        return {f["name"]: str(f.id()) for f in self.facilities.getFeatures()}

    def test_the_matrix_gives_road_costs_and_the_access_legs(self):
        from cartogen_ai.core.agent.tools.logistics_tools import travel_time_matrix
        result = travel_time_matrix("ubend_start", "smoke_ubend_facilities", "smoke_ubend_road")
        print(f"UBENDRESULT {str(result)[:600]}")
        self.assertTrue(result.get("success"), result)
        costs = next(iter(result["matrix"].values()))
        legs = result["access_leg_m"]
        ids = self._ids()
        inside, beside = ids["Inside_the_U"], ids["Beside_the_arm"]
        self.assertAlmostEqual(float(costs[inside]), 70.0, delta=2.0)
        self.assertAlmostEqual(float(costs[beside]), 200.0, delta=2.0)
        self.assertAlmostEqual(legs[inside], 300.0, delta=2.0)
        self.assertAlmostEqual(legs[beside], 80.0, delta=2.0)
        self.assertIn("TOTAL travel", result["access_leg_note"])

    def test_the_totals_decide_a_300_m_budget(self):
        from cartogen_ai.core.agent.tools.logistics_tools import travel_time_matrix
        result = travel_time_matrix("ubend_start", "smoke_ubend_facilities", "smoke_ubend_road")
        costs = next(iter(result["matrix"].values()))
        legs = result["access_leg_m"]
        ids = self._ids()
        totals = {name: float(costs[key]) + legs[key] for name, key in ids.items()}
        self.assertGreater(totals["Inside_the_U"], 300.0)
        self.assertLess(totals["Beside_the_arm"], 300.0)

    def test_classify_facilities_counts_the_leg_whatever_the_snap_distance(self):
        # rc48 OI-148, the actual run: classify_facilities_by_access said both facilities were within 300 m (default snap 500 m) or, with snap 50 m,
        # both beyond. Routed totals are 370 m (Inside_the_U, beyond) and 280 m (Beside_the_arm, within); the snap distance must not change that.
        from cartogen_ai.core.agent.tools.logistics_tools import classify_facilities_by_access
        for snap in (50, 500, 5000):
            result = classify_facilities_by_access("ubend_start", "smoke_ubend_facilities", "smoke_ubend_road", 300, snap_distance_m=snap)
            self.assertTrue(result.get("success"), result)
            self.assertEqual(result.get("method"), "routed", result)
            self.assertEqual((result["within"], result["beyond"]), (1, 1), (snap, result))
            self.assertEqual(result.get("beyond_examples"), ["Inside_the_U"], (snap, result))


if __name__ == "__main__":
    unittest.main()
