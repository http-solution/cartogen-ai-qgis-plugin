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
from cartogen_ai.core.agent.tools.humanitarian_tools import (
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


def _mock_safe_opener(response):
    """SEC-001 (2026-09-13): the actual file-download request now goes through
    _build_safe_opener().open(...), not the bare urllib.request.urlopen(...) these
    tests already mock for the FIRST (listing) request -- this stands in for the
    opener so the second request is served from the test's own fixture too, not a
    real network call."""
    opener = MagicMock()
    opener.open.return_value = response
    return opener


_YEM_LISTING = {
    "data": [
        {"popyear": "2015", "files": ["https://data.worldpop.org/.../yem_ppp_2015.tif"]},
        {"popyear": "2020", "files": ["https://data.worldpop.org/.../yem_ppp_2020.tif"]},
    ]
}


class TestFetchWorldpopNetworkPhaseValidation(unittest.TestCase):
    def test_rejects_non_three_letter_code(self):
        res = fetch_worldpop_population_network_phase("YE", allow_whole_country=True)
        self.assertIn("error", res)
        self.assertIn("ISO", res["error"])


class TestFetchWorldpopNetworkPhase(unittest.TestCase):
    def setUp(self):
        _LOOKUP_CACHE._store.clear()

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools._build_safe_opener")
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_auto_selects_most_recent_year(self, mock_urlopen, mock_opener):
        mock_urlopen.return_value = _mock_response(_YEM_LISTING)
        mock_opener.return_value = _mock_safe_opener(_mock_response(b"fake-tiff-bytes"))

        res = fetch_worldpop_population_network_phase("yem", allow_whole_country=True)

        self.assertTrue(res["success"])
        self.assertEqual(res["iso3"], "YEM")
        self.assertEqual(res["year"], "2020")
        self.assertTrue(res["local_path"].endswith(".tif"))
        import os
        self.assertTrue(os.path.exists(res["local_path"]))
        os.remove(res["local_path"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools._build_safe_opener")
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_selects_requested_year(self, mock_urlopen, mock_opener):
        mock_urlopen.return_value = _mock_response(_YEM_LISTING)
        mock_opener.return_value = _mock_safe_opener(_mock_response(b"fake-tiff-bytes"))

        res = fetch_worldpop_population_network_phase("YEM", year="2015", allow_whole_country=True)

        self.assertTrue(res["success"])
        self.assertEqual(res["year"], "2015")
        import os
        os.remove(res["local_path"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_unavailable_year_is_a_clean_error(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(_YEM_LISTING)

        res = fetch_worldpop_population_network_phase("YEM", year="1999", allow_whole_country=True)

        self.assertIn("error", res)
        self.assertIn("1999", res["error"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_rejects_unsafe_second_hop_file_url(self, mock_urlopen):
        """SEC-001 (2026-09-13 security audit): file_urls[0] comes from WorldPop's own API
        listing -- third-party content, not a hardcoded endpoint. A response pointing that
        field at a loopback/private/metadata address must be refused, not silently fetched."""
        unsafe_listing = {
            "data": [{"popyear": "2020", "files": ["http://169.254.169.254/latest/meta-data/"]}]
        }
        mock_urlopen.return_value = _mock_response(unsafe_listing)

        res = fetch_worldpop_population_network_phase("YEM", allow_whole_country=True)

        self.assertIn("error", res)
        self.assertIn("Refusing to fetch", res["error"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_no_datasets_found_is_a_clean_error(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({"data": []})

        res = fetch_worldpop_population_network_phase("ZZZ", allow_whole_country=True)

        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools._build_safe_opener")
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_result_is_cached_on_repeated_call(self, mock_urlopen, mock_opener):
        mock_urlopen.return_value = _mock_response(_YEM_LISTING)
        mock_opener.return_value = _mock_safe_opener(_mock_response(b"fake-tiff-bytes"))

        first = fetch_worldpop_population_network_phase("YEM", allow_whole_country=True)
        second = fetch_worldpop_population_network_phase("YEM", allow_whole_country=True)

        self.assertNotIn("cached", first)
        self.assertTrue(second.get("cached"))
        # SEC-001 (2026-09-13) split the single fetch pair across two request paths --
        # the listing still via urlopen, the actual raster download via the safe opener
        # -- so each is 1 real call (not 2), for the whole pair across both invocations,
        # confirming the second invocation made no network calls of either kind.
        self.assertEqual(mock_urlopen.call_count, 1)
        self.assertEqual(mock_opener.return_value.open.call_count, 1)
        import os
        os.remove(first["local_path"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_handles_network_failure_gracefully(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("network unreachable")
        res = fetch_worldpop_population_network_phase("YEM", allow_whole_country=True)
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

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools._build_safe_opener")
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_leaves_downloaded_file_on_disk_after_loading(self, mock_urlopen, mock_opener):
        # Regression guard for the correctness issue found while designing this
        # tool: a raster layer reads its backing file lazily, so (unlike
        # fetch_geoboundaries) the downloaded file must NOT be deleted after
        # QgsRasterLayer construction, or the layer would silently break later.
        mock_urlopen.return_value = _mock_response(_YEM_LISTING)
        mock_opener.return_value = _mock_safe_opener(_mock_response(b"fake-tiff-bytes"))

        res = fetch_worldpop_population("YEM", allow_whole_country=True)

        self.assertTrue(res["success"])
        # Outside QGIS, add_worldpop_population_layer_main_thread_phase never
        # even reports local_path, so check indirectly: the network-phase
        # cache should still resolve to a file that exists on disk.
        cached = fetch_worldpop_population_network_phase("YEM", allow_whole_country=True)
        self.assertTrue(cached.get("cached"))
        import os
        self.assertTrue(os.path.exists(cached["local_path"]))
        os.remove(cached["local_path"])


if __name__ == "__main__":
    unittest.main()
