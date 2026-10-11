"""Live-QGIS tests for the USGS earthquake and UCDP layer phases (stubbed fetch results, no network). Written without a local QGIS:
CI's first run is their first execution."""
import unittest

try:
    from qgis.core import QgsProject
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


QUAKES = {"success": True, "days": 7, "min_magnitude": 4.5, "truncated": False, "source": "USGS", "events": [
    {"event_id": "us1", "lat": 35.47, "lon": 26.59, "title": "Greece", "magnitude": 4.8, "category": "M4-5", "depth_km": 10.0,
     "time": "2026-10-10 22:33 UTC", "alert": "", "tsunami": 0, "link": "https://x/us1"},
    {"event_id": "us2", "lat": 36.0, "lon": 36.5, "title": "Turkey", "magnitude": 6.1, "category": "M6-7", "depth_km": 8.0,
     "time": "2026-10-10 20:00 UTC", "alert": "orange", "tsunami": 1, "link": "https://x/us2"},
]}
CONFLICT = {"success": True, "matched": 1, "truncated": False, "dataset_file": "GEDEvent_v26_0_8.csv", "latest_event_date": "2026-08-31",
            "source": "UCDP", "events": [
                {"event_id": "639816", "lat": 12.48, "lon": 25.8, "date": "2026-08-31", "country": "Sudan", "adm_1": "East Darfur state",
                 "conflict_name": "Sudan: Government", "category": "State-based conflict", "deaths_best": 4, "deaths_low": 4,
                 "deaths_high": 4, "location_precision": 3, "clarity": "1"}]}


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestEventLayers(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_earthquake_layer_is_built_then_replaced_not_duplicated(self):
        from cartogen_ai.core.agent.tools.event_data_tools import add_usgs_earthquakes_layer_main_thread_phase as add
        res = add(QUAKES, "quakes")
        self.assertTrue(res.get("success"), res)
        layers = QgsProject.instance().mapLayersByName("quakes")
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0].featureCount(), 2)
        self.assertEqual(sorted(f["magnitude"] for f in layers[0].getFeatures()), [4.8, 6.1])
        add(dict(QUAKES, events=QUAKES["events"][:1]), "quakes")
        layers = QgsProject.instance().mapLayersByName("quakes")
        self.assertEqual((len(layers), layers[0].featureCount()), (1, 1))

    def test_conflict_layer_has_the_deaths_and_type_fields(self):
        from cartogen_ai.core.agent.tools.event_data_tools import add_ucdp_conflict_events_layer_main_thread_phase as add
        res = add(CONFLICT, "conflict")
        self.assertTrue(res.get("success"), res)
        self.assertIn("2026-08-31", res["message"])
        feat = next(QgsProject.instance().mapLayersByName("conflict")[0].getFeatures())
        self.assertEqual((feat["deaths_best"], feat["category"], feat["country"]), (4, "State-based conflict", "Sudan"))

    def test_an_error_result_is_passed_through(self):
        from cartogen_ai.core.agent.tools.event_data_tools import add_usgs_earthquakes_layer_main_thread_phase as add
        self.assertEqual(add({"error": "boom"}, "x"), {"error": "boom"})
        self.assertEqual(QgsProject.instance().mapLayersByName("x"), [])


if __name__ == "__main__":
    unittest.main()
