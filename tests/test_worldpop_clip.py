# -*- coding: utf-8 -*-
"""F19 (rc7 smoke test, 2026-09-30): fetch_worldpop_population downloaded the WHOLE-country raster
(Yemen, 141 s) for a ~77 x 71 km catchment. With extent_layer/bbox only that window is read through
GDAL /vsicurl/. Network and GDAL are mocked here; tests/test_worldpop_clip_live.py clips a real raster."""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools import humanitarian_tools as ht

_LISTING = {"data": [{"popyear": "2020", "files": ["https://data.worldpop.org/GIS/Population/yem_ppp_2020.tif"]}]}


def _resp(payload):
    r = MagicMock()
    r.read.return_value = json.dumps(payload).encode()
    r.__enter__.return_value = r
    r.__exit__.return_value = False
    return r


class TestParseAndPadBbox(unittest.TestCase):
    def test_list_and_string_forms(self):
        self.assertEqual(ht.parse_bbox([43.5, 15.0, 44.5, 16.0]), (43.5, 15.0, 44.5, 16.0))
        self.assertEqual(ht.parse_bbox("43.5, 15.0; 44.5, 16.0"), (43.5, 15.0, 44.5, 16.0))

    def test_projected_metres_are_refused_with_advice(self):
        with self.assertRaises(ValueError) as ctx:
            ht.parse_bbox([4902068, 1799912, 4990000, 1850000])
        self.assertIn("extent_layer", str(ctx.exception))

    def test_bad_shapes_are_refused(self):
        for bad in ([1, 2, 3], "a,b,c,d", [44, 15, 43, 16], [43, 16, 44, 15], None):
            with self.assertRaises(ValueError, msg=str(bad)):
                ht.parse_bbox(bad)

    def test_padding_grows_the_box_and_stays_inside_the_world(self):
        self.assertEqual(ht.pad_bbox((43.5, 15.0, 44.5, 16.0), 0.02), (43.48, 14.98, 44.52, 16.02))
        self.assertEqual(ht.pad_bbox((-180, -90, 180, 90), 1), (-180.0, -90.0, 180.0, 90.0))


class TestWindowInsideRaster(unittest.TestCase):
    """gdal.Translate(projWin) does not fail for a window outside the raster -- it writes an empty
    raster -- so the overlap is checked first (found by the first CI run of the live clip test)."""
    RASTER = (40.0, 10.0, 50.0, 20.0)

    def test_inside_is_unchanged(self):
        self.assertEqual(ht._window_inside_raster((42, 14, 44, 16), self.RASTER), ((42, 14, 44, 16), False))

    def test_partly_outside_is_clamped(self):
        self.assertEqual(ht._window_inside_raster((48, 14, 55, 16), self.RASTER), ((48, 14, 50, 16), True))

    def test_entirely_outside_raises_naming_the_raster_extent(self):
        with self.assertRaises(RuntimeError) as ctx:
            ht._window_inside_raster((100, 50, 101, 51), self.RASTER)
        self.assertIn("does not overlap the raster", str(ctx.exception))
        self.assertIn("40.000..50.000", str(ctx.exception))

    def test_touching_only_at_an_edge_is_no_overlap(self):
        with self.assertRaises(RuntimeError):
            ht._window_inside_raster((50, 14, 52, 16), self.RASTER)


class TestClipSourceAllowlist(unittest.TestCase):
    def test_worldpop_https_hosts_only(self):
        ok = ht._worldpop_clip_source_allowed
        self.assertTrue(ok("https://data.worldpop.org/a.tif"))
        self.assertTrue(ok("https://worldpop.org/a.tif"))
        self.assertFalse(ok("http://data.worldpop.org/a.tif"))
        self.assertFalse(ok("https://evil.example.com/worldpop.org/a.tif"))
        self.assertFalse(ok("https://worldpop.org.evil.example.com/a.tif"))
        self.assertFalse(ok("https://notworldpop.org/a.tif"))
        self.assertFalse(ok(""))


class TestNetworkPhaseWithABox(unittest.TestCase):
    def setUp(self):
        ht._LOOKUP_CACHE._store.clear()
        # _is_safe_url resolves the host over DNS; these tests are about what happens AFTER that guard.
        patcher = patch.object(ht, "_is_safe_url", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch.object(ht, "_build_safe_opener")
    @patch.object(ht, "_clip_raster_to_bbox")
    @patch.object(ht.urllib.request, "urlopen")
    def test_a_box_reads_only_the_window_and_never_downloads_the_country(self, urlopen, clip, opener):
        urlopen.return_value = _resp(_LISTING)
        clip.side_effect = lambda src, box, dest: (open(dest, "wb").write(b"x"), {"width": 40, "height": 30})[1]
        res = ht.fetch_worldpop_population_network_phase("YEM", "2020", [43.5, 15.0, 44.5, 16.0])
        try:
            self.assertTrue(res["success"], res)
            opener.assert_not_called()                       # the full-download path was not taken
            src, box, _dest = clip.call_args[0]
            self.assertTrue(src.startswith("/vsicurl/https://data.worldpop.org/"))
            self.assertEqual(box, (43.48, 14.98, 44.52, 16.02))
            self.assertEqual(res["clipped_to_bbox"], [43.48, 14.98, 44.52, 16.02])
            self.assertEqual(res["clipped_pixels"], [40, 30])
            self.assertNotIn("note", res)
        finally:
            os.remove(res["local_path"])

    @patch.object(ht, "_build_safe_opener")
    @patch.object(ht.urllib.request, "urlopen")
    def test_without_a_box_the_whole_country_is_fetched_and_the_result_says_so(self, urlopen, opener):
        urlopen.return_value = _resp(_LISTING)
        body = MagicMock()
        body.read.return_value = b"tiff"
        body.__enter__.return_value = body
        body.__exit__.return_value = False
        opener.return_value.open.return_value = body
        res = ht.fetch_worldpop_population_network_phase("YEM", "2020", allow_whole_country=True)
        try:
            self.assertTrue(res["success"])
            self.assertIn("WHOLE-country", res["note"])
            self.assertEqual(res["bytes_on_disk"], 4)
        finally:
            os.remove(res["local_path"])

    @patch.object(ht.urllib.request, "urlopen")
    def test_a_whole_country_download_is_kept_in_the_cache_folder_and_reused(self, urlopen):
        # rc10 smoke test: the whole-country raster was written to a random temp file (so a saved project pointed into
        # %TEMP%) and never reused. With a cache folder it is streamed to <cache>/yem_ppp_2020.tif and kept.
        import tempfile
        urlopen.return_value = _resp(_LISTING)
        cache_dir = os.path.join(tempfile.mkdtemp(), "worldpop")
        calls = []

        def fake_download(url, dest, chunk=1 << 20):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(b"tiff-bytes")
            calls.append(dest)

        with patch.object(ht, "_download_to_file", side_effect=fake_download):
            ht._LOOKUP_CACHE._store.clear()
            first = ht.fetch_worldpop_population_network_phase("YEM", "2020", allow_whole_country=True, cache_dir=cache_dir)
            ht._LOOKUP_CACHE._store.clear()
            second = ht.fetch_worldpop_population_network_phase("YEM", "2020", allow_whole_country=True, cache_dir=cache_dir)
        expected = os.path.join(cache_dir, "yem_ppp_2020.tif")
        self.assertEqual(first["local_path"], expected)
        self.assertEqual(first["country_file_cache"], "downloaded")
        self.assertEqual(second["country_file_cache"], "reused")
        self.assertEqual(len(calls), 1, "the second request must not download again")
        self.assertEqual(first["bytes_on_disk"], 10)

    @patch.object(ht, "_clip_raster_to_bbox", side_effect=RuntimeError("window outside the raster"))
    @patch.object(ht.urllib.request, "urlopen")
    def test_a_failed_clip_is_an_error_not_a_silent_full_download(self, urlopen, clip):
        urlopen.return_value = _resp(_LISTING)
        with patch.object(ht, "_build_safe_opener") as opener:
            res = ht.fetch_worldpop_population_network_phase("YEM", "2020", [100, 10, 101, 11])
            opener.assert_not_called()
        self.assertIn("error", res)
        self.assertIn("Nothing was downloaded", res["error"])
        self.assertIn("window outside the raster", res["error"])

    @patch.object(ht, "_clip_raster_to_bbox")
    @patch.object(ht.urllib.request, "urlopen")
    def test_a_file_not_on_worldpop_is_not_read_remotely(self, urlopen, clip):
        urlopen.return_value = _resp({"data": [{"popyear": "2020", "files": ["https://files.example.com/a.tif"]}]})
        res = ht.fetch_worldpop_population_network_phase("YEM", "2020", [43.5, 15.0, 44.5, 16.0])
        clip.assert_not_called()
        self.assertIn("not on worldpop.org", res["error"])

    def test_a_bad_box_is_refused_before_any_request(self):
        with patch.object(ht.urllib.request, "urlopen") as urlopen:
            res = ht.fetch_worldpop_population_network_phase("YEM", "2020", [1, 2, 3])
            urlopen.assert_not_called()
        self.assertIn("four numbers", res["error"])

    @patch.object(ht, "_clip_raster_to_bbox")
    @patch.object(ht.urllib.request, "urlopen")
    def test_different_boxes_are_cached_separately(self, urlopen, clip):
        urlopen.return_value = _resp(_LISTING)
        clip.side_effect = lambda src, box, dest: (open(dest, "wb").write(b"x"), {"width": 1, "height": 1})[1]
        a = ht.fetch_worldpop_population_network_phase("YEM", "2020", [43.5, 15.0, 44.5, 16.0])
        b = ht.fetch_worldpop_population_network_phase("YEM", "2020", [45.5, 15.0, 46.5, 16.0])
        again = ht.fetch_worldpop_population_network_phase("YEM", "2020", [43.5, 15.0, 44.5, 16.0])
        try:
            self.assertNotEqual(a["local_path"], b["local_path"])
            self.assertTrue(again.get("cached"))
            self.assertEqual(clip.call_count, 2)
        finally:
            for r in (a, b):
                os.remove(r["local_path"])


class TestWholeCountryIsRefusedByDefault(unittest.TestCase):
    """F22: a whole-country raster is 100 MB to over 1 GB; asking for it needs an explicit opt-in."""

    def setUp(self):
        ht._LOOKUP_CACHE._store.clear()

    def test_no_box_and_no_opt_in_is_refused_before_any_request(self):
        with patch.object(ht.urllib.request, "urlopen") as urlopen:
            res = ht.fetch_worldpop_population_network_phase("YEM", "2020")
            urlopen.assert_not_called()
        self.assertIn("WHOLE country", res["error"])
        self.assertIn("extent_layer", res["error"])
        self.assertIn("allow_whole_country=true", res["error"])
        self.assertEqual(res["suggested_args"], ["extent_layer", "bbox"])

    def test_the_direct_tool_call_is_refused_too(self):
        with patch.object(ht.urllib.request, "urlopen") as urlopen:
            res = ht.fetch_worldpop_population("YEM", "2020")
            urlopen.assert_not_called()
        self.assertIn("error", res)

    def test_a_box_needs_no_opt_in(self):
        with patch.object(ht, "_is_safe_url", return_value=None), \
                patch.object(ht.urllib.request, "urlopen", return_value=_resp(_LISTING)), \
                patch.object(ht, "_clip_raster_to_bbox",
                             side_effect=lambda s, b, d: (open(d, "wb").write(b"x"), {"width": 1, "height": 1})[1]):
            res = ht.fetch_worldpop_population_network_phase("YEM", "2020", [43.5, 15.0, 44.5, 16.0])
        try:
            self.assertTrue(res["success"], res)
        finally:
            os.remove(res["local_path"])

    def test_the_schema_offers_the_opt_in_and_says_when_to_use_it(self):
        from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
        fn = next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "fetch_worldpop_population")
        self.assertIn("allow_whole_country", fn["parameters"]["properties"])
        self.assertIn("ONLY after the user agreed", fn["parameters"]["properties"]["allow_whole_country"]["description"])


class TestToolSchema(unittest.TestCase):
    def test_extent_layer_and_bbox_are_offered_and_the_description_says_always_pass_one(self):
        from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
        fn = next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "fetch_worldpop_population")
        self.assertIn("extent_layer", fn["parameters"]["properties"])
        self.assertIn("bbox", fn["parameters"]["properties"])
        self.assertIn("ALWAYS pass extent_layer", fn["description"])
        self.assertEqual(fn["parameters"]["required"], ["iso3"])


if __name__ == "__main__":
    unittest.main()


class TestCountryFileCacheFallback(unittest.TestCase):
    """F19: when the remote window read fails and the user agreed to the whole-country download, the file is fetched
    ONCE, kept, and clipped from disk; an area that misses the raster must never trigger that download."""

    def test_cache_file_is_per_country_and_year(self):
        from cartogen_ai.core.agent.tools import humanitarian_tools as ht
        import os
        self.assertEqual(ht._worldpop_cache_file(os.path.join("d", "worldpop"), "YEM", 2020),
                         os.path.join("d", "worldpop", "yem_ppp_2020.tif"))
        self.assertIsNone(ht._worldpop_cache_file(None, "YEM", 2020))

    def test_a_non_overlapping_window_is_not_a_transport_failure(self):
        from cartogen_ai.core.agent.tools import humanitarian_tools as ht
        self.assertFalse(ht._is_transport_failure(RuntimeError("the requested area (1, 2, 3, 4) does not overlap the raster")))
        self.assertFalse(ht._is_transport_failure(RuntimeError("the raster is rotated or not north-up")))
        self.assertTrue(ht._is_transport_failure(RuntimeError("HTTP error 403 while reading the file")))
        self.assertTrue(ht._is_transport_failure(RuntimeError("Connection timed out")))

    def test_the_cache_folder_sits_beside_the_osm_folder(self):
        from unittest.mock import patch
        import os
        from cartogen_ai.core.agent.tools import humanitarian_tools as ht
        with patch("cartogen_ai.core.agent.local_data_loader.data_dir", return_value=os.path.join("p", "data", "00_raw", "osm")):
            self.assertEqual(ht.worldpop_cache_dir(), os.path.join("p", "data", "00_raw", "worldpop"))
