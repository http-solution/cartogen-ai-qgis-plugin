"""Live-QGIS test for the incident layer phase (stubbed fetch result, no network). Written without a local QGIS: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsProject
    LIVE = True
except ImportError:
    LIVE = False


def _fetch(records):
    return {"success": True, "country": "Yemen", "bbox": None, "days": 30, "since": "2026-09-12", "records": records, "total_matched": len(records),
            "truncated": False, "sources_checked": [{"source": "usgs", "name": "USGS", "tier": 1, "records": 1}], "sources_failed": [],
            "not_searched": {"ACLED": "needs a key"}}


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestIncidentLayer(unittest.TestCase):
    def setUp(self):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _rec(self, rid, lat, lon):
        from cartogen_ai.core.agent.tools import incident_search_tools as inc
        return inc._record("usgs", rid, "earthquake", "quake", "2026-10-10", lat, lon, "https://x", "m4", "Yemen", "M4-5")

    def test_mapped_records_become_points_and_unmapped_ones_are_counted_not_dropped(self):
        from cartogen_ai.core.agent.tools import incident_search_tools as inc
        records = [self._rec("a", 15.0, 44.0), self._rec("b", 16.0, 45.0), inc._record("reliefweb", "R1", "declared disaster", "Yemen: Floods", "2026-10-01", None, None, "https://r", "", "Yemen")]
        res = inc.add_incident_reports_layer_main_thread_phase(_fetch(records), "incidents")
        self.assertTrue(res.get("success"), res)
        self.assertEqual((res["mapped"], res["unmapped_reports"], res["total_matched"]), (2, 1, 3))
        layer = QgsProject.instance().mapLayersByName("incidents")[0]
        self.assertEqual(layer.featureCount(), 2)
        feat = next(layer.getFeatures())
        self.assertEqual((feat["tier"], feat["country"], feat["url"]), (1, "Yemen", "https://x"))
        self.assertIn("Sources answered", res["message"])

    def test_a_second_run_replaces_the_features(self):
        from cartogen_ai.core.agent.tools import incident_search_tools as inc
        inc.add_incident_reports_layer_main_thread_phase(_fetch([self._rec("a", 15.0, 44.0), self._rec("b", 16.0, 45.0)]), "incidents")
        inc.add_incident_reports_layer_main_thread_phase(_fetch([self._rec("c", 17.0, 46.0)]), "incidents")
        layers = QgsProject.instance().mapLayersByName("incidents")
        self.assertEqual((len(layers), layers[0].featureCount()), (1, 1))

    def test_an_error_result_passes_through(self):
        from cartogen_ai.core.agent.tools import incident_search_tools as inc
        self.assertEqual(inc.add_incident_reports_layer_main_thread_phase({"error": "x"}, "i"), {"error": "x"})


if __name__ == "__main__":
    unittest.main()
