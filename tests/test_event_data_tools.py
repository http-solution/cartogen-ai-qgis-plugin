"""USGS earthquake and UCDP candidate-event tools: the pure parts, plus the network phases with the fetch stubbed.

The sample rows have the shape the live services returned on 2026-10-11 (USGS GeoJSON; UCDP Candidate Events CSV columns). The layer
phase needs QGIS and is not covered here."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools import event_data_tools as ev
from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY

USGS = {"features": [
    {"id": "us1", "geometry": {"coordinates": [26.59, 35.47, 10.0]},
     "properties": {"mag": 4.2, "place": "31 km WNW of Fry, Greece", "time": 1791671580000, "tsunami": 0, "url": "https://x/us1"}},
    {"id": "us2", "geometry": {"coordinates": [-120.0, 36.0, 5.0]}, "properties": {"mag": 6.1, "place": "California", "time": 1791671580000}},
    {"id": "bad", "geometry": {"coordinates": []}, "properties": {"mag": 5}},
]}

HEADER = "id,country,adm_1,latitude,longitude,date_start,type_of_violence,conflict_name,best,high,low,where_prec,event_clarity\n"
UCDP_CSV = HEADER + (
    "1,Sudan,East Darfur state,12.48,25.8,2026-08-31 00:00:00.000,1,Sudan: Government,4,4,4,3,1\n"
    "2,Yemen,Hajjah,16.0,43.0,2026-05-02 00:00:00.000,3,Government of Yemen - Civilians,0,1,0,2,1\n"
    "3,Yemen,Taiz,13.5,44.0,2026-07-10 00:00:00.000,2,Houthis - X,12,15,10,1,1\n"
    "4,Yemen,Bad,,,2026-07-11 00:00:00.000,1,No coordinates,3,3,3,1,1\n")


class TestUsgs(unittest.TestCase):
    def test_parse_skips_unusable_points_and_bands_the_magnitude(self):
        events = ev.parse_usgs_features(USGS)
        self.assertEqual([e["event_id"] for e in events], ["us1", "us2"])
        self.assertEqual(events[0]["category"], "M4-5")
        self.assertEqual(events[1]["category"], "M6-7")
        self.assertEqual(events[0]["time"][:10], "2026-10-10")        # epoch milliseconds -> UTC text

    def test_bbox_is_applied_again_client_side(self):
        events = ev.parse_usgs_features(USGS, [20, 30, 30, 40])
        self.assertEqual([e["event_id"] for e in events], ["us1"])

    def test_bad_arguments_are_errors_not_requests(self):
        with patch.object(ev, "urlopen_with_retry") as op:
            self.assertIn("error", ev.fetch_usgs_earthquakes_network_phase(bbox=[10, 10, 5, 20]))
            self.assertIn("error", ev.fetch_usgs_earthquakes_network_phase(days=0))
            self.assertIn("error", ev.fetch_usgs_earthquakes_network_phase(days="x"))
            op.assert_not_called()

    def test_request_url_carries_the_filters(self):
        seen = {}

        def fake(req, timeout):
            seen["url"] = req.full_url
            raise OSError("stop")
        with patch.object(ev, "urlopen_with_retry", fake):
            out = ev.fetch_usgs_earthquakes_network_phase(bbox=[25, 30, 45, 42], days=3, min_magnitude=5)
        self.assertIn("error", out)
        for part in ("format=geojson", "minmagnitude=5.0", "minlongitude=25", "maxlatitude=42", "orderby=time"):
            self.assertIn(part, seen["url"])


class TestUcdp(unittest.TestCase):
    def test_latest_file_ignores_the_month_range_file_and_picks_the_highest_release(self):
        page = ('<a href="https://ucdp.uu.se/downloads/candidateged/GEDEvent_v26_01_26_06.csv">r</a>'
                '<a href="https://ucdp.uu.se/downloads/candidateged/GEDEvent_v26_0_7.csv">a</a>'
                '<a href="https://ucdp.uu.se/downloads/candidateged/GEDEvent_v26_0_10.csv">b</a>'
                '<a href="https://ucdp.uu.se/downloads/candidateged/GEDEvent_v26_0_8.csv">c</a>')
        self.assertEqual(ev.find_latest_candidate_file(page), "GEDEvent_v26_0_10.csv")
        self.assertIsNone(ev.find_latest_candidate_file("<html>nothing</html>"))

    def test_parse_filters_by_country_dates_deaths_and_drops_rows_without_coordinates(self):
        events, latest, total = ev.parse_ucdp_candidate_csv(UCDP_CSV, country="yemen")
        self.assertEqual((total, latest), (4, "2026-08-31"))
        self.assertEqual(sorted(e["event_id"] for e in events), ["2", "3"])
        events, _l, _t = ev.parse_ucdp_candidate_csv(UCDP_CSV, country="yemen", start_date="2026-06-01", min_deaths=5)
        self.assertEqual([e["event_id"] for e in events], ["3"])
        self.assertEqual(events[0]["category"], "Non-state conflict")
        self.assertEqual((events[0]["deaths_best"], events[0]["deaths_low"], events[0]["deaths_high"]), (12, 10, 15))

    def test_network_phase_reads_page_then_file_and_reports_the_dataset_date(self):
        page = '<a href="https://ucdp.uu.se/downloads/candidateged/GEDEvent_v26_0_8.csv">c</a>'

        def fake_text(url, timeout):
            return page if url == ev._UCDP_DOWNLOADS_PAGE else UCDP_CSV
        with patch.object(ev, "_download_text", fake_text), patch.object(ev.os.path, "isfile", return_value=False), \
                patch.object(ev.os, "makedirs"), patch("builtins.open", unittest.mock.mock_open()):
            out = ev.fetch_ucdp_conflict_events_network_phase(country="Yemen", max_events=1)
        self.assertTrue(out["success"])
        self.assertEqual((out["dataset_file"], out["latest_event_date"], out["matched"], len(out["events"])), ("GEDEvent_v26_0_8.csv", "2026-08-31", 2, 1))
        self.assertTrue(out["truncated"])
        self.assertIn("CC BY 4.0", out["source"])
        self.assertEqual(out["events"][0]["event_id"], "3")                  # newest first

    def test_a_changed_downloads_page_is_a_clear_error(self):
        with patch.object(ev, "_download_text", return_value="<html>moved</html>"):
            self.assertIn("no longer lists", ev.fetch_ucdp_conflict_events_network_phase()["error"])

    def test_bad_dates_are_refused(self):
        self.assertIn("error", ev.fetch_ucdp_conflict_events_network_phase(start_date="March 2026"))


class TestRegistered(unittest.TestCase):
    def test_both_tools_are_registered_and_dispatched_in_two_phases(self):
        from cartogen_ai.core.agent.agent_orchestrator import TWO_PHASE_TOOLS
        from cartogen_ai.core.agent.tool_operations import get_tool_operation_type
        for name in ("fetch_usgs_earthquakes", "fetch_ucdp_conflict_events"):
            self.assertIn(name, TOOL_REGISTRY)
            self.assertIn(name, TWO_PHASE_TOOLS)
            self.assertEqual(get_tool_operation_type(name), "CREATE")


if __name__ == "__main__":
    unittest.main()
