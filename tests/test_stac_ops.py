"""PLAN-023 R3-2: the pure helpers of load_stac_assets, checked by hand and against one real item the Earth Search service returned on 2026-11-11 (tests/fixtures/stac_sentinel2_item_2026-11-11.json)."""
import json
import math
import os
import unittest

from cartogen_ai.core.agent.tools import stac_ops as so

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "stac_sentinel2_item_2026-11-11.json")


def _items():
    with open(FIXTURE, encoding="utf-8") as fh:
        return so.parse_items(json.load(fh))


class TestRequest(unittest.TestCase):
    OK = ([36.8, -1.35, 36.85, -1.30], "2026-10-01", "2026-11-10", ["red", "nir"], 20, 1)

    def test_a_good_request_passes(self):
        self.assertIsNone(so.check_request(*self.OK))

    def test_bad_requests_are_refused_with_the_reason(self):
        bbox, start, end, assets, cloud, limit = self.OK
        cases = [(([1, 2, 3], start, end, assets, cloud, limit), "four numbers"), (([10, 0, 5, 1], start, end, assets, cloud, limit), "valid WGS84"),
                 ((bbox, "2026-13-01", end, assets, cloud, limit), "YYYY-MM-DD"), ((bbox, end, start, assets, cloud, limit), "after end_date"),
                 ((bbox, start, end, [], cloud, limit), "1 to 6"), ((bbox, start, end, ["blue"] * 7, cloud, limit), "1 to 6"),
                 ((bbox, start, end, ["landsat_red"], cloud, limit), "requester-pays"), ((bbox, start, end, ["purple"], cloud, limit), "Unknown band"),
                 ((bbox, start, end, ["red", "red"], cloud, limit), "more than once"), ((bbox, start, end, assets, 120, limit), "max_cloud"),
                 ((bbox, start, end, assets, cloud, 4), "1 to 3"), ((bbox, start, end, assets, cloud, True), "1 to 3")]
        for args, word in cases:
            self.assertIn(word, so.check_request(*args) or "", args)

    def test_scene_ids_must_be_plain(self):
        self.assertIsNone(so.check_item_ids(["S2A_37MBU_20261110_0_L2A"]))
        for bad in ([], ["../x"], ["a b"], "S2A", ["a"] * 4, [5]):
            self.assertIsNotNone(so.check_item_ids(bad), bad)


class TestAddresses(unittest.TestCase):
    def test_only_the_sentinel_bucket_over_https_is_allowed(self):
        good = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/37/M/BU/2026/11/S2A_37MBU_20261110_0_L2A/B02.tif"
        self.assertTrue(so.asset_url_ok(good))
        for bad in (good.replace("https", "http"), "https://evil.example.com/B02.tif", "https://user@sentinel-cogs.s3.us-west-2.amazonaws.com/x.tif",
                    "https://sentinel-cogs.s3.us-west-2.amazonaws.com:8443/x.tif", "s3://sentinel-s2-l2a/x.tif", "file:///etc/passwd", "", None,
                    "https://sentinel-cogs.s3.us-west-2.amazonaws.com.evil.example.com/x.tif"):
            self.assertFalse(so.asset_url_ok(bad), bad)
        self.assertIn("requester-pays", so.refusal_for_href("s3://usgs-landsat/x.tif"))


class TestWindowSize(unittest.TestCase):
    def test_hand_computed_window_cells(self):
        # 0.1 x 0.1 degrees at the equator, 10 m cells: width 11,132 m -> 1,114 cells (ceil of 1113.2), height 11,054 m -> 1,106 cells (ceil of 1105.4)
        self.assertEqual(so.window_cells((0.0, 0.0, 0.1, 0.1), 10), 1114 * 1106)
        # the same box at 60 degrees north is half as wide: 5,566 m -> 557 cells, 11,054 m -> 1,106 cells (mid latitude 60.05, so a hair under half)
        near = so.window_cells((10.0, 60.0, 10.1, 60.1), 10)
        self.assertEqual(near, math.ceil(0.1 * 111320 * math.cos(math.radians(60.05)) / 10) * 1106)
        self.assertEqual(so.window_cells((0.0, 0.0, 0.1, 0.1), 20), 557 * 553)

    def test_sizes_read_naturally(self):
        self.assertEqual(so.human_size(500), "500 bytes")
        self.assertEqual(so.human_size(2 * 1024 * 1024), "2.0 MB")
        self.assertEqual(so.human_size(3 * 1024 ** 3), "3.0 GB")

    def test_overlap(self):
        self.assertEqual(so.bbox_overlap((0, 0, 2, 2), (1, 1, 3, 3)), (1, 1, 2, 2))
        self.assertIsNone(so.bbox_overlap((0, 0, 1, 1), (1, 1, 2, 2)))


class TestRealItem(unittest.TestCase):
    def test_the_recorded_item_is_understood(self):
        item = _items()[0]
        self.assertEqual((item["id"], item["epsg"]), ("S2A_37MBU_20261110_0_L2A", 32737))
        self.assertAlmostEqual(item["cloud"], 76.074558)
        self.assertTrue(so.asset_url_ok(item["assets"]["blue"]))
        self.assertTrue(item["assets"]["blue-jp2"].startswith("s3://"))

    def test_a_plan_for_two_bands_of_the_real_item(self):
        rows, problems = so.plan(_items(), ["blue", "swir16"], (36.8, -1.35, 36.85, -1.30))
        self.assertEqual((problems, [r["asset"] for r in rows]), ([], ["blue", "swir16"]))
        blue, swir = rows
        self.assertEqual(blue["cells"], so.window_cells((36.8, -1.35, 36.85, -1.30), 10))
        self.assertEqual(blue["bytes"], blue["cells"] * 2)
        self.assertEqual(swir["cells"], so.window_cells((36.8, -1.35, 36.85, -1.30), 20))

    def test_problems_are_named_and_nothing_is_skipped_silently(self):
        item = _items()[0]
        rows, problems = so.plan([item], ["blue"], (100.0, 10.0, 100.1, 10.1))
        self.assertEqual((rows, len(problems)), ([], 1))
        self.assertIn("does not cover", problems[0])
        item = {**item, "assets": {**item["assets"], "red": "s3://sentinel-s2-l2a/x/B04.tif", "nir": None}}
        rows, problems = so.plan([item], ["blue", "red", "nir"], (36.8, -1.35, 36.85, -1.30))
        self.assertEqual([r["asset"] for r in rows], ["blue"])
        self.assertEqual(len(problems), 2)
        self.assertTrue(any("requester-pays" in p for p in problems) and any("no 'nir' band" in p for p in problems))

    def test_a_window_above_the_cell_limit_and_a_total_above_the_byte_limit_are_refused(self):
        item = _items()[0]
        rows, problems = so.plan([item], ["blue"], (36.4, -1.8, 37.2, -1.0))      # 0.8 x 0.8 degrees at 10 m is about 79 million cells
        self.assertEqual(rows, [])
        self.assertIn("above the limit", problems[0])
        # 0.69 x 0.69 degrees at 10 m is 7,681 x 7,629 = 58.6 million cells (under the cell limit), 117 MB per band: two scenes x four 10 m bands is 937 MB, over the 600 MB total limit
        item2 = {**item, "id": "second_scene"}
        rows, problems = so.plan([item, item2], ["blue", "green", "red", "nir"], (36.4, -1.8, 37.09, -1.11))
        self.assertEqual(rows, [])
        self.assertEqual(len(problems), 1)
        self.assertIn("ask for fewer bands", problems[0])

    def test_the_provenance_carries_the_origin_and_the_licence(self):
        item = _items()[0]
        rows, _ = so.plan([item], ["red"], (36.8, -1.35, 36.85, -1.30))
        record = so.provenance(item, rows[0], "2026-11-11")
        self.assertEqual((record["scene"], record["band"], record["cloud_cover_percent"]), ("S2A_37MBU_20261110_0_L2A", "red", item["cloud"]))
        self.assertIn("Contains modified Copernicus Sentinel data (2026)", record["licence_notice"])
        self.assertTrue(record["source_address"].startswith("https://sentinel-cogs.s3.us-west-2.amazonaws.com/"))


if __name__ == "__main__":
    unittest.main()
