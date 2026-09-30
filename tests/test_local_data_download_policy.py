# -*- coding: utf-8 -*-
"""F22 (rc7 smoke test, 2026-09-30): a 103 MB OSM extract downloaded with no question because the
silent-download threshold was a fixed 150 MB. The default is now 50 MB (owner decision 2026-09-30; it was 150), but the threshold is now a
setting, and a fresh local copy no longer triggers a question about a download that will not happen."""
import os
import tempfile
import time
import unittest
import zipfile

from cartogen_ai.core.agent import local_data_loader as ldl

MB = 1000 * 1000


class TestAskThreshold(unittest.TestCase):
    def test_default_is_the_previous_fixed_threshold(self):
        self.assertEqual(ldl.ask_threshold_bytes(lambda: None), 50 * MB)
        self.assertEqual(ldl.ask_threshold_bytes(lambda: ""), 50 * MB)

    def test_a_setting_in_megabytes_overrides_it(self):
        self.assertEqual(ldl.ask_threshold_bytes(lambda: 50), 50 * MB)
        self.assertEqual(ldl.ask_threshold_bytes(lambda: "75.5"), int(75.5 * MB))

    def test_zero_means_always_ask(self):
        self.assertEqual(ldl.ask_threshold_bytes(lambda: 0), 0)

    def test_garbage_or_negative_falls_back_to_the_default(self):
        self.assertEqual(ldl.ask_threshold_bytes(lambda: "lots"), 50 * MB)
        self.assertEqual(ldl.ask_threshold_bytes(lambda: -5), 50 * MB)

        def boom():
            raise RuntimeError("settings unavailable")
        self.assertEqual(ldl.ask_threshold_bytes(boom), 50 * MB)


class TestShouldAsk(unittest.TestCase):
    REGION = {"id": "yemen", "name": "Yemen", "size_bytes": 103 * MB}

    def test_the_observed_103mb_case_is_asked_at_the_default_but_silent_at_150(self):
        self.assertTrue(ldl.should_ask_before_download(self.REGION, True, False, ldl.ask_threshold_bytes(lambda: None)))
        self.assertFalse(ldl.should_ask_before_download(self.REGION, True, False, 150 * MB))

    def test_zero_threshold_asks_for_everything_with_a_known_size(self):
        self.assertTrue(ldl.should_ask_before_download(self.REGION, True, False, 0))

    def test_poor_connection_always_asks(self):
        self.assertTrue(ldl.should_ask_before_download(self.REGION, False, False, 50 * MB))

    def test_unknown_size_asks(self):
        self.assertTrue(ldl.should_ask_before_download({"id": "x", "size_bytes": 0}, True, False, 50 * MB))
        self.assertTrue(ldl.should_ask_before_download({"id": "x"}, True, False, 50 * MB))

    def test_a_cached_extract_never_asks_even_if_huge_or_offline(self):
        big = {"id": "x", "size_bytes": 900 * MB}
        self.assertFalse(ldl.should_ask_before_download(big, True, True, 50 * MB))
        self.assertFalse(ldl.should_ask_before_download(big, False, True, 0))


class TestExtractIsCached(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.region = {"id": "yemen"}
        self.path = os.path.join(self.tmp.name, "yemen-latest-free.shp.zip")

    def _write_zip(self):
        with zipfile.ZipFile(self.path, "w") as z:
            z.writestr("a.txt", "x")

    def test_no_file_is_not_cached(self):
        self.assertFalse(ldl.extract_is_cached(self.region, self.tmp.name))

    def test_a_fresh_valid_zip_is_cached(self):
        self._write_zip()
        self.assertTrue(ldl.extract_is_cached(self.region, self.tmp.name))

    def test_an_old_zip_is_not(self):
        self._write_zip()
        old = time.time() - ldl.EXTRACT_MAX_AGE_S - 60
        os.utime(self.path, (old, old))
        self.assertFalse(ldl.extract_is_cached(self.region, self.tmp.name))

    def test_a_truncated_download_is_not(self):
        with open(self.path, "wb") as f:
            f.write(b"not a zip")
        self.assertFalse(ldl.extract_is_cached(self.region, self.tmp.name))


if __name__ == "__main__":
    unittest.main()


class TestMeteredConnection(unittest.TestCase):
    REGION = {"id": "x", "name": "X", "size_bytes": 5 * MB}  # well under any threshold

    def test_a_metered_connection_asks_even_for_a_small_known_size(self):
        self.assertFalse(ldl.should_ask_before_download(self.REGION, True, False, 50 * MB))
        self.assertTrue(ldl.should_ask_before_download(self.REGION, True, False, 50 * MB, metered=True))

    def test_a_cached_extract_never_asks_even_when_metered(self):
        self.assertFalse(ldl.should_ask_before_download(self.REGION, True, True, 50 * MB, metered=True))

    def test_the_platform_answer_is_passed_through(self):
        self.assertTrue(ldl.is_metered_connection(lambda: True))
        self.assertFalse(ldl.is_metered_connection(lambda: False))

    def test_an_unreadable_platform_answer_is_not_metered(self):
        def boom():
            raise RuntimeError("no backend")
        self.assertFalse(ldl.is_metered_connection(boom))

    def test_without_qt_it_is_not_metered(self):
        self.assertFalse(ldl.is_metered_connection())
