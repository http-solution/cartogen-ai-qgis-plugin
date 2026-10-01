# -*- coding: utf-8 -*-
"""rc7 smoke test F22: the other fetch tools (geoBoundaries, HDX, building footprints) ask before a large download.

The rule: a server-reported size above the user's threshold stops the tool with a message telling the model to ask,
and only allow_large_download=true proceeds. No reported size is not blocked."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools import humanitarian_tools as ht

MB = 1_000_000


class TestLargeDownloadError(unittest.TestCase):
    def test_under_threshold_goes_ahead(self):
        self.assertIsNone(ht.large_download_error("x", 10 * MB, 50 * MB, False))

    def test_over_threshold_stops_and_says_how_to_proceed(self):
        err = ht.large_download_error("The YEM ADM2 boundary file", 120 * MB, 50 * MB, False)
        self.assertIn("120 MB", err["error"])
        self.assertIn("allow_large_download=true", err["error"])
        self.assertTrue(err["requires_user_decision"])

    def test_opt_in_goes_ahead(self):
        self.assertIsNone(ht.large_download_error("x", 120 * MB, 50 * MB, True))

    def test_unknown_size_is_not_blocked(self):
        self.assertIsNone(ht.large_download_error("x", None, 50 * MB, False))
        self.assertIsNone(ht.large_download_error("x", 0, 50 * MB, False))


class TestCheckDownloadSize(unittest.TestCase):
    def test_sizes_are_summed_across_urls(self):
        with patch.object(ht, "_content_length", side_effect=[30 * MB, 40 * MB]), \
             patch.object(ht, "_ask_threshold_bytes", return_value=50 * MB):
            err = ht.check_download_size("tiles", ["a", "b"])
        self.assertEqual(err["size_mb"], 70.0)

    def test_opt_in_skips_the_probe_entirely(self):
        with patch.object(ht, "_content_length") as probe:
            self.assertIsNone(ht.check_download_size("tiles", ["a"], allow_large_download=True))
        probe.assert_not_called()

    def test_a_failed_probe_does_not_block(self):
        with patch.object(ht, "_content_length", return_value=None), \
             patch.object(ht, "_ask_threshold_bytes", return_value=50 * MB):
            self.assertIsNone(ht.check_download_size("tiles", ["a"]))


class TestGeoBoundariesAsksBeforeDownloading(unittest.TestCase):
    def test_a_large_geojson_is_not_downloaded_without_opt_in(self):
        api = b'{"gjDownloadURL": "https://example.invalid/big.geojson", "boundaryName": "Yemen"}'

        class _Resp:
            def __init__(self, body): self.body = body
            def read(self): return self.body
            def __enter__(self): return self
            def __exit__(self, *a): return False

        ht._LOOKUP_CACHE.clear() if hasattr(ht._LOOKUP_CACHE, "clear") else None
        with patch.object(ht.urllib.request, "urlopen", return_value=_Resp(api)), \
             patch.object(ht, "_is_safe_url", return_value=None), \
             patch.object(ht, "_content_length", return_value=200 * MB), \
             patch.object(ht, "_ask_threshold_bytes", return_value=50 * MB), \
             patch.object(ht, "_build_safe_opener") as opener:
            res = ht.fetch_geoboundaries_network_phase("ZZZ", "ADM9")
        self.assertIn("allow_large_download=true", res["error"])
        opener.assert_not_called()          # nothing was downloaded


if __name__ == "__main__":
    unittest.main()
