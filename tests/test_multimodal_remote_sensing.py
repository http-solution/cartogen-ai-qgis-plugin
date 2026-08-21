# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
from agent.tools import multimodal_remote_sensing as mrs


class TestCalculateRasterChangeDetectionDegradesOutsideQgis(unittest.TestCase):
    """No test coverage at all existed for this tool before this -- not even
    the baseline QGIS_AVAILABLE=False degrade check every other tool in this
    suite has -- found during a router/prompt-coverage audit, not related to
    any behavior change in the tool itself."""

    def test_degrades(self):
        res = mrs.calculate_raster_change_detection("before", "after")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


def _mock_stac_response(scene_count=1):
    resp = MagicMock()
    features = [
        {
            "id": f"scene-{i}",
            "properties": {"datetime": "2026-08-01T00:00:00Z", "eo:cloud_cover": 5.0},
            "assets": {"thumbnail": {"href": "http://example.com/thumb.png"}, "visual": {"href": "http://example.com/visual.tif"}},
        }
        for i in range(scene_count)
    ]
    resp.read.return_value = __import__("json").dumps({"features": features}).encode()
    resp.__enter__ = lambda self: resp
    resp.__exit__ = lambda self, *a: False
    return resp


class TestStacCacheAndQuota(unittest.TestCase):
    def setUp(self):
        # Module-global cache/counter persist across tests in the same process -- reset before each.
        mrs._STAC_CACHE.clear()
        mrs._STAC_REQUEST_COUNT = 0

    @patch("agent.tools.multimodal_remote_sensing.urllib.request.urlopen")
    def test_second_identical_query_is_served_from_cache(self, mock_urlopen):
        mock_urlopen.return_value = _mock_stac_response()

        first = mrs.search_stac_satellite_imagery([1, 2, 3, 4], "2026-01-01", "2026-01-31")
        self.assertTrue(first["success"])
        self.assertNotIn("cached", first)

        second = mrs.search_stac_satellite_imagery([1, 2, 3, 4], "2026-01-01", "2026-01-31")
        self.assertTrue(second["cached"])
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("agent.tools.multimodal_remote_sensing.urllib.request.urlopen")
    def test_different_query_is_not_cached(self, mock_urlopen):
        mock_urlopen.return_value = _mock_stac_response()
        mrs.search_stac_satellite_imagery([1, 2, 3, 4], "2026-01-01", "2026-01-31")
        mrs.search_stac_satellite_imagery([5, 6, 7, 8], "2026-01-01", "2026-01-31")
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch("agent.tools.multimodal_remote_sensing.urllib.request.urlopen")
    def test_quota_exceeded_returns_error_without_calling_api(self, mock_urlopen):
        mock_urlopen.return_value = _mock_stac_response()
        mrs._STAC_REQUEST_COUNT = mrs._STAC_MAX_REQUESTS
        res = mrs.search_stac_satellite_imagery([1, 2, 3, 4], "2026-01-01", "2026-01-31")
        self.assertIn("error", res)
        self.assertIn("quota", res["error"].lower())
        mock_urlopen.assert_not_called()

    def test_invalid_bbox_rejected_before_touching_cache_or_quota(self):
        res = mrs.search_stac_satellite_imagery([1, 2, 3], "2026-01-01", "2026-01-31")
        self.assertIn("error", res)
        self.assertEqual(mrs._STAC_REQUEST_COUNT, 0)

    @patch("agent.tools.multimodal_remote_sensing.urllib.request.urlopen")
    def test_request_sets_a_timeout(self, mock_urlopen):
        # A fixed, hardcoded endpoint (Earth Search STAC API), not attacker-controlled
        # -- missing timeout was a reliability/hang risk on a background thread, not
        # a security hole. Every requests.get/post call in the provider modules
        # already sets one explicitly; this closes the same gap here.
        mock_urlopen.return_value = _mock_stac_response()
        mrs.search_stac_satellite_imagery([1, 2, 3, 4], "2026-01-01", "2026-01-31")
        self.assertEqual(mock_urlopen.call_args.kwargs.get("timeout"), 15)


if __name__ == "__main__":
    unittest.main()
