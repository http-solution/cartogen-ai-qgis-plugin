# -*- coding: utf-8 -*-
"""Tests for fetch_worldpop_population (agent/tools/humanitarian_tools.py),
the WorldPop open-data population tool added in the ArcGIS-parity pass, an
open-data approximation of ArcGIS Business Analyst's demographic layer.
Network calls are mocked -- the actual live-API schema (dataset list under
data[], each entry with popyear/files) and the download-size consideration
(WorldPop rasters run 100MB-1GB+, hence the two-phase split and the
deliberate choice not to delete the downloaded file after loading, unlike
geoBoundaries' geojson) were both verified by hand against the real API
before writing this tool; see the session notes."""
import json
import unittest
from unittest.mock import patch, MagicMock
from agent.tools.humanitarian_tools import (
    fetch_worldpop_population_network_phase, add_worldpop_population_layer_main_thread_phase,
    fetch_worldpop_population, _LOOKUP_CACHE,
)


def _mock_response(payload_or_bytes):
    resp = MagicMock()
    if isinstance(payload_or_bytes, (bytes, bytearray)):
        resp.read.return_value = payload_or_bytes
    else:
        resp.read.return_value = json.dumps(payload_or_bytes).encode()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


_YEM_LISTING = {
    "data": [
        {"popyear": "2015", "files": ["https://data.worldpop.org/.../yem_ppp_2015.tif"]},
        {"popyear": "2020", "files": ["https://data.worldpop.org/.../yem_ppp_2020.tif"]},
    ]
}


class TestFetchWorldpopNetworkPhaseValidation(unittest.TestCase):
    def test_rejects_non_three_letter_code(self):
        res = fetch_worldpop_population_network_phase("YE")
        self.assertIn("error", res)
        self.assertIn("ISO", res["error"])


class TestFetchWorldpopNetworkPhase(unittest.TestCase):
    def setUp(self):
        _LOOKUP_CACHE._store.clear()

    @patch("agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_auto_selects_most_recent_year(self, mock_urlopen):
        mock_urlopen.side_effect = [_mock_response(_YEM_LISTING), _mock_response(b"fake-tiff-bytes")]

        res = fetch_worldpop_population_network_phase("yem")

        self.assertTrue(res["success"])
        self.assertEqual(res["iso3"], "YEM")
        self.assertEqual(res["year"], "2020")
        self.assertTrue(res["local_path"].endswith(".tif"))
        import os
        self.assertTrue(os.path.exists(res["local_path"]))
        os.remove(res["local_path"])

    @patch("agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_selects_requested_year(self, mock_urlopen):
        mock_urlopen.side_effect = [_mock_response(_YEM_LISTING), _mock_response(b"fake-tiff-bytes")]

        res = fetch_worldpop_population_network_phase("YEM", year="2015")

        self.assertTrue(res["success"])
        self.assertEqual(res["year"], "2015")
        import os
        os.remove(res["local_path"])

    @patch("agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_unavailable_year_is_a_clean_error(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(_YEM_LISTING)

        res = fetch_worldpop_population_network_phase("YEM", year="1999")

        self.assertIn("error", res)
        self.assertIn("1999", res["error"])

    @patch("agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_no_datasets_found_is_a_clean_error(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"data": []})

        res = fetch_worldpop_population_network_phase("ZZZ")

        self.assertIn("error", res)

    @patch("agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_result_is_cached_on_repeated_call(self, mock_urlopen):
        mock_urlopen.side_effect = [_mock_response(_YEM_LISTING), _mock_response(b"fake-tiff-bytes")]

        first = fetch_worldpop_population_network_phase("YEM")
        second = fetch_worldpop_population_network_phase("YEM")

        self.assertNotIn("cached", first)
        self.assertTrue(second.get("cached"))
        self.assertEqual(mock_urlopen.call_count, 2)  # not 4 -- second call served from cache
        import os
        os.remove(first["local_path"])

    @patch("agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_handles_network_failure_gracefully(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("network unreachable")
        res = fetch_worldpop_population_network_phase("YEM")
        self.assertIn("error", res)


class TestAddWorldpopLayerMainThreadPhase(unittest.TestCase):
    def test_passes_through_errors(self):
        res = add_worldpop_population_layer_main_thread_phase({"error": "boom"})
        self.assertIn("error", res)

    def test_degrades_outside_qgis_without_crashing(self):
        # QGIS_AVAILABLE is False in this test environment -- confirms the
        # main-thread phase doesn't blow up when there's no real QGIS to load
        # the raster into, matching every other QGIS-touching tool's degrade path.
        res = add_worldpop_population_layer_main_thread_phase(
            {"success": True, "iso3": "YEM", "year": "2020", "local_path": "/tmp/fake.tif"}
        )
        self.assertTrue(res["success"])


class TestFetchWorldpopPopulationCombined(unittest.TestCase):
    def setUp(self):
        _LOOKUP_CACHE._store.clear()

    @patch("agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_leaves_downloaded_file_on_disk_after_loading(self, mock_urlopen):
        # Regression guard for the correctness issue found while designing this
        # tool: a raster layer reads its backing file lazily, so (unlike
        # fetch_geoboundaries) the downloaded file must NOT be deleted after
        # QgsRasterLayer construction, or the layer would silently break later.
        mock_urlopen.side_effect = [_mock_response(_YEM_LISTING), _mock_response(b"fake-tiff-bytes")]

        res = fetch_worldpop_population("YEM")

        self.assertTrue(res["success"])
        # Outside QGIS, add_worldpop_population_layer_main_thread_phase never
        # even reports local_path, so check indirectly: the network-phase
        # cache should still resolve to a file that exists on disk.
        cached = fetch_worldpop_population_network_phase("YEM")
        self.assertTrue(cached.get("cached"))
        import os
        self.assertTrue(os.path.exists(cached["local_path"]))
        os.remove(cached["local_path"])


if __name__ == "__main__":
    unittest.main()
