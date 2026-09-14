# -*- coding: utf-8 -*-
"""Tests for agent/tools/hazard_monitoring_tools.py -- NASA FIRMS/EONET and GDACS live hazard
fetch tools. Network calls are mocked; QGIS isn't available in this test environment, so these
cover the network_phase functions (pure Python, no qgis.core) plus the main_thread_phase/
composite functions' graceful degrade when QGIS_AVAILABLE is False (returns a count-only stub
rather than raising -- confirmed against the real behavior in humanitarian_tools.py's equivalent
functions)."""
import json
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.tools import hazard_monitoring_tools as hz


def _mock_response(text_or_bytes):
    resp = MagicMock()
    resp.read.return_value = text_or_bytes if isinstance(text_or_bytes, bytes) else text_or_bytes.encode()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


class TestValidateBbox(unittest.TestCase):
    def test_none_is_valid(self):
        self.assertIsNone(hz._validate_bbox(None))

    def test_wrong_length_rejected(self):
        self.assertIsNotNone(hz._validate_bbox([1, 2, 3]))

    def test_non_numeric_rejected(self):
        self.assertIsNotNone(hz._validate_bbox(["a", 2, 3, 4]))

    def test_lon_out_of_range_rejected(self):
        self.assertIsNotNone(hz._validate_bbox([-200, 0, 10, 10]))

    def test_lat_out_of_range_rejected(self):
        self.assertIsNotNone(hz._validate_bbox([0, -100, 10, 10]))

    def test_min_greater_than_max_rejected(self):
        self.assertIsNotNone(hz._validate_bbox([10, 10, 0, 0]))

    def test_valid_bbox_accepted(self):
        self.assertIsNone(hz._validate_bbox([34.9, 30.9, 35.2, 31.3]))


class TestPointInBbox(unittest.TestCase):
    def test_none_bbox_always_true(self):
        self.assertTrue(hz._point_in_bbox(999, 999, None))

    def test_inside(self):
        self.assertTrue(hz._point_in_bbox(35.0, 31.0, [34.9, 30.9, 35.2, 31.3]))

    def test_outside(self):
        self.assertFalse(hz._point_in_bbox(0, 0, [34.9, 30.9, 35.2, 31.3]))


class TestFetchNasaActiveFiresNetworkPhase(unittest.TestCase):
    def test_missing_bbox_rejected(self):
        res = hz.fetch_nasa_active_fires_network_phase(None)
        self.assertIn("error", res)

    def test_invalid_days_rejected(self):
        res = hz.fetch_nasa_active_fires_network_phase([0, 0, 1, 1], days=99)
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.CredentialManager.get_credential", return_value="")
    def test_missing_api_key_gives_clear_error(self, mock_cred):
        res = hz.fetch_nasa_active_fires_network_phase([0, 0, 1, 1])
        self.assertIn("error", res)
        self.assertIn("firms.modaps.eosdis.nasa.gov", res["error"])

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.CredentialManager.get_credential", return_value="TESTKEY")
    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen")
    def test_parses_csv_and_filters_by_confidence(self, mock_urlopen, mock_cred):
        csv_body = (
            "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"
            "31.95,35.93,330.5,0.4,0.4,2026-09-12,0130,N,high,2.0NRT,290.1,12.3,N\n"
            "31.96,35.94,300.1,0.4,0.4,2026-09-12,0130,N,low,2.0NRT,285.0,4.1,N\n"
        )
        mock_urlopen.return_value = _mock_response(csv_body)
        res = hz.fetch_nasa_active_fires_network_phase([34.9, 30.9, 35.2, 31.3], min_confidence="nominal")
        self.assertTrue(res["success"])
        # Only the "high"-confidence row passes a "nominal" minimum threshold.
        self.assertEqual(len(res["detections"]), 1)
        self.assertEqual(res["detections"][0]["confidence"], "high")
        self.assertIn("unit", res["detections"][0])

    @patch("cartogen_ai.core.agent.tools._urllib_retry.time.sleep")
    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.CredentialManager.get_credential", return_value="TESTKEY")
    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen")
    def test_retries_on_transient_503_then_succeeds(self, mock_urlopen, mock_cred, mock_sleep):
        # API-003, 2026-09-14 audit: this fetch used to have zero retry/backoff at all --
        # unlike every LLM provider call, a single transient 5xx failed the whole tool call
        # outright, on a tool specifically designed to be re-run on a recurring schedule.
        import io
        import urllib.error
        csv_body = (
            "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"
            "31.95,35.93,330.5,0.4,0.4,2026-09-12,0130,N,high,2.0NRT,290.1,12.3,N\n"
        )
        err = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, io.BytesIO())
        mock_urlopen.side_effect = [err, _mock_response(csv_body)]
        res = hz.fetch_nasa_active_fires_network_phase([34.9, 30.9, 35.2, 31.3])
        self.assertTrue(res.get("success"), res)
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.CredentialManager.get_credential", return_value="BADKEY")
    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen")
    def test_firms_error_body_detected(self, mock_urlopen, mock_cred):
        mock_urlopen.return_value = _mock_response("Invalid MAP_KEY")
        res = hz.fetch_nasa_active_fires_network_phase([0, 0, 1, 1])
        self.assertIn("error", res)


class TestAddNasaActiveFiresLayerMainThreadPhase(unittest.TestCase):
    def test_error_passes_through(self):
        res = hz.add_nasa_active_fires_layer_main_thread_phase({"error": "boom"})
        self.assertEqual(res, {"error": "boom"})

    def test_no_qgis_degrades_to_count_stub(self):
        res = hz.add_nasa_active_fires_layer_main_thread_phase({"success": True, "detections": [{"lat": 1, "lon": 2}]})
        self.assertTrue(res["success"])
        self.assertEqual(res["detection_count"], 1)
        self.assertNotIn("layer_name", res)


class TestFetchNasaEonetEventsNetworkPhase(unittest.TestCase):
    def test_invalid_status_rejected(self):
        res = hz.fetch_nasa_eonet_events_network_phase(status="bogus")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen")
    def test_uses_most_recent_geometry_and_bbox_filters(self, mock_urlopen):
        payload = {
            "events": [
                {
                    "id": "EONET_1", "title": "Storm A", "closed": None, "link": "http://x",
                    "categories": [{"title": "Severe Storms"}],
                    "geometry": [
                        {"type": "Point", "date": "2026-09-10T00:00:00Z", "coordinates": [-120, 16]},
                        {"type": "Point", "date": "2026-09-11T00:00:00Z", "coordinates": [35.0, 31.0]},
                    ],
                },
                {
                    "id": "EONET_2", "title": "Wildfire B", "closed": None, "link": "http://y",
                    "categories": [{"title": "Wildfires"}],
                    "geometry": [{"type": "Point", "date": "2026-09-11T00:00:00Z", "coordinates": [0, 0]}],
                },
            ]
        }
        mock_urlopen.return_value = _mock_response(json.dumps(payload))
        res = hz.fetch_nasa_eonet_events_network_phase(bbox=[34.9, 30.9, 35.2, 31.3])
        self.assertTrue(res["success"])
        # EONET_1's most recent geometry (35.0, 31.0) is inside bbox; EONET_2's only point (0,0) is not.
        self.assertEqual(len(res["events"]), 1)
        self.assertEqual(res["events"][0]["unit"], "EONET_1")
        self.assertEqual(res["events"][0]["lat"], 31.0)

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen")
    def test_non_dict_json_response_returns_clean_error_not_a_crash(self, mock_urlopen):
        """Real live crash, 2026-09-13: a chat turn ended in a bare 'Error: 'str' object
        has no attribute 'get'' -- traced to this exact gap. The request/decode try/except
        only guarantees valid JSON, not a dict; a bare JSON string (e.g. a CDN error page
        served with a JSON content-type) used to reach data.get(...) below and crash
        uncaught, escaping the whole tool-calling loop instead of becoming a normal
        {"error": ...} result."""
        mock_urlopen.return_value = _mock_response(json.dumps("Service temporarily unavailable"))
        res = hz.fetch_nasa_eonet_events_network_phase(bbox=[34.9, 30.9, 35.2, 31.3])
        self.assertIn("error", res)
        self.assertIn("unexpected response shape", res["error"])

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen")
    def test_null_json_response_returns_clean_error_not_a_crash(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(json.dumps(None))
        res = hz.fetch_nasa_eonet_events_network_phase()
        self.assertIn("error", res)


class TestFetchGdacsDisasterAlertsNetworkPhase(unittest.TestCase):
    def _payload(self):
        return {
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [35.0, 31.0]},
                 "properties": {"eventid": 1, "eventtype": "EQ", "eventname": "Quake A",
                                 "alertlevel": "Red", "country": "Jordan"}},
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [35.0, 31.0]},
                 "properties": {"eventid": 2, "eventtype": "DR", "eventname": "Drought B",
                                 "alertlevel": "Green", "country": "Jordan"}},
            ]
        }

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen")
    def test_default_excludes_green(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(json.dumps(self._payload()))
        res = hz.fetch_gdacs_disaster_alerts_network_phase()
        self.assertTrue(res["success"])
        self.assertEqual(len(res["alerts"]), 1)
        self.assertEqual(res["alerts"][0]["alert_level"], "Red")

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen")
    def test_min_alert_level_green_includes_everything(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(json.dumps(self._payload()))
        res = hz.fetch_gdacs_disaster_alerts_network_phase(min_alert_level="Green")
        self.assertEqual(len(res["alerts"]), 2)

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen")
    def test_bbox_filters_client_side(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(json.dumps(self._payload()))
        res = hz.fetch_gdacs_disaster_alerts_network_phase(bbox=[0, 0, 1, 1], min_alert_level="Green")
        self.assertEqual(len(res["alerts"]), 0)

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen", side_effect=OSError("timeout"))
    def test_network_failure_returns_clean_error(self, mock_urlopen):
        res = hz.fetch_gdacs_disaster_alerts_network_phase()
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen")
    def test_non_dict_json_response_returns_clean_error_not_a_crash(self, mock_urlopen):
        """Same live crash class as TestFetchNasaEonetEventsNetworkPhase's identical test --
        GDACS's own docs already warn its data 'may require further validation', so a
        malformed non-dict body here is a real, not hypothetical, risk."""
        mock_urlopen.return_value = _mock_response(json.dumps(["not", "a", "dict"]))
        res = hz.fetch_gdacs_disaster_alerts_network_phase()
        self.assertIn("error", res)
        self.assertIn("unexpected response shape", res["error"])


class TestGenerateSituationDashboardDegradesWithoutQgis(unittest.TestCase):
    """QGIS isn't available in this test environment, so every fetch tool's main-thread phase
    returns a count-only stub with no layer_name -- this must degrade to a clean 'no data'
    error, never a KeyError (the exact bug this test would have caught, found and fixed before
    this test was written)."""

    def test_missing_bbox_rejected(self):
        res = hz.generate_situation_dashboard(None)
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.CredentialManager.get_credential", return_value="")
    @patch("cartogen_ai.core.agent.tools.hazard_monitoring_tools.urllib.request.urlopen")
    def test_no_qgis_degrades_cleanly_not_keyerror(self, mock_urlopen, mock_cred):
        mock_urlopen.return_value = _mock_response(json.dumps({"features": [], "events": []}))
        res = hz.generate_situation_dashboard([34.9, 30.9, 35.2, 31.3])
        self.assertIn("error", res)  # no FIRMS key + no QGIS layers -> no data available


if __name__ == "__main__":
    unittest.main()
