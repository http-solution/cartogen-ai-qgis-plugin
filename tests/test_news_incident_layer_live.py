"""Live-QGIS check that news records become a mapped, correctly labelled layer. No network: the records are built from fixtures. Written
without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsProject
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestNewsIncidentLayer(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_news_records_are_mapped_with_source_link_and_an_inferred_rating(self):
        from cartogen_ai.core.agent.tools import incident_search_tools as inc
        arts = [{"title": "Floods kill 12 in Irbid as heavy rain hits northern Jordan", "url": "https://jordantimes.com/a", "outlet": "jordantimes.com",
                 "date": "2026-10-12"},
                {"title": "Heavy rain expected this week", "url": "https://example.org/b", "outlet": "example.org", "date": "2026-10-12"}]
        records = inc.news_records(arts, "Jordan", lambda name: {"lat": 32.55, "lon": 35.85, "location": "Irbid, Jordan"})
        fetch = {"success": True, "records": records, "total_matched": 2, "truncated": False, "since": "2026-10-05", "sources_checked":
                 [{"source": "news", "name": "News", "tier": 3, "records": 2}], "sources_failed": [], "not_searched": {}}
        res = inc.add_incident_reports_layer_main_thread_phase(fetch, "News incidents")
        self.assertTrue(res.get("success"), res)
        self.assertEqual((res["mapped"], res["unmapped_reports"]), (1, 1))     # the second headline names no place
        layer = QgsProject.instance().mapLayersByName("News incidents")[0]
        feature = next(layer.getFeatures())
        self.assertEqual(feature["url"], "https://jordantimes.com/a")
        self.assertIn("not verified", feature["detail"])
        from cartogen_ai.core.models.confidence import get_layer_confidence
        self.assertEqual(get_layer_confidence(layer)["level"], "INFERRED")


if __name__ == "__main__":
    unittest.main()
