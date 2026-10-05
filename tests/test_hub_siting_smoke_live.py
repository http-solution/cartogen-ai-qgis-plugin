# -*- coding: utf-8 -*-
"""optimal_hub_siting on the release smoke fixture, against distances computed independently (rc15 hand test D03, 2026-10-06).

The hand test reported Hub_A at 1,632.74 m where the straight-line average is 886.98 m, but the raw tool return was not captured, so
it was unclear whether the tool or the model's narration was wrong. This pins the tool's own output: if it passes, the fault was in
the reply. Needs real qgis.core and skips itself without it; runs in the qgis-live-tests CI job."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

GPKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "docs", "release_smoke_assets", "inputs", "smoke_data.gpkg")
# Planar averages in EPSG:32636 from the fixture's own coordinates, computed with sqlite + math (no QGIS).
EXPECTED = {"Hub_A": 886.979, "Hub_B": 1035.773, "Hub_C": 1622.391}


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE and os.path.exists(GPKG), "needs real qgis.core and the smoke fixture")
class TestHubSitingOnTheSmokeFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _boot_qgis()

    def setUp(self):
        QgsProject.instance().clear()
        for name in ("smoke_hubs", "smoke_points"):
            layer = QgsVectorLayer(f"{GPKG}|layername={name}", name, "ogr")
            self.assertTrue(layer.isValid(), name)
            QgsProject.instance().addMapLayer(layer)
        self.addCleanup(QgsProject.instance().clear)

    def test_average_distances_match_the_independent_calculation(self):
        from cartogen_ai.core.agent.tools.logistics_tools import optimal_hub_siting
        res = optimal_hub_siting("smoke_hubs", "smoke_points")
        self.assertTrue(res.get("success"), res)
        got = {r["candidate"]: r["avg_distance"] for r in res["ranked_candidates"]}
        self.assertEqual(set(got), set(EXPECTED), got)
        for name, expected in EXPECTED.items():
            # 2 m allows for ellipsoidal vs planar measurement on the projected CRS; the hand-test error was 746 m.
            self.assertAlmostEqual(got[name], expected, delta=2.0, msg=f"{name}: {got}")
        self.assertEqual(res["ranked_candidates"][0]["avg_distance"], min(got.values()))


if __name__ == "__main__":
    unittest.main()
