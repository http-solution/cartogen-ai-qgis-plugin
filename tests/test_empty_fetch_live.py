"""A data fetch that matches nothing adds no empty layer (1.18.4 smoke A10: 'UCDP Conflict Events - Yemen 2025' was left in the project empty).
The helper is tested offline; the four add-layer functions in real QGIS (CI's first run is their first execution)."""
import unittest

from cartogen_ai.core.agent.tools._layer_checks import empty_fetch_result

try:
    from qgis.core import QgsProject
    LIVE = True
except ImportError:
    LIVE = False


class TestEmptyFetchResult(unittest.TestCase):
    def test_says_no_layer_was_added_and_why_the_model_should_stop(self):
        res = empty_fetch_result("UCDP Conflict Events - Yemen 2025", "UCDP events")
        self.assertTrue(res["success"])
        self.assertFalse(res["layer_added"])
        self.assertEqual(res["event_count"], 0)
        self.assertIn("no layer 'UCDP Conflict Events - Yemen 2025' was added", res["message"])


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestNoEmptyLayerIsAdded(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_each_fetch_that_matched_nothing_leaves_the_project_empty(self):
        from cartogen_ai.core.agent.tools import event_data_tools as ev
        from cartogen_ai.core.agent.tools import hazard_monitoring_tools as hz
        cases = (
            (ev.add_ucdp_conflict_events_layer_main_thread_phase, {"events": []}),
            (ev.add_usgs_earthquakes_layer_main_thread_phase, {"events": []}),
            (hz.add_nasa_eonet_events_layer_main_thread_phase, {"events": []}),
            (hz.add_gdacs_disaster_alerts_layer_main_thread_phase, {"alerts": []}),
        )
        for fn, fetched in cases:
            res = fn(fetched)
            self.assertTrue(res.get("success"), (fn.__name__, res))
            self.assertFalse(res.get("layer_added"), (fn.__name__, res))
            self.assertEqual(len(QgsProject.instance().mapLayers()), 0, fn.__name__)


if __name__ == "__main__":
    unittest.main()
