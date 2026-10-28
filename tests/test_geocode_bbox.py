"""A geocoded place carries its own bounding box (1.18.4 smoke A5, A6, A13: the model had a point for Aden but no area)."""
import unittest

from cartogen_ai.core.agent.tools.system_tools import _nominatim_bbox


class TestNominatimBbox(unittest.TestCase):
    def test_boundingbox_is_reordered_for_both_conventions(self):
        # Nominatim sends [south, north, west, east] as strings.
        out = _nominatim_bbox({"boundingbox": ["12.70", "12.90", "44.90", "45.10"]})
        self.assertEqual(out["bbox_south_west_north_east"], [12.7, 44.9, 12.9, 45.1])
        self.assertEqual(out["bbox_west_south_east_north"], [44.9, 12.7, 45.1, 12.9])

    def test_missing_or_broken_boundingbox_adds_nothing(self):
        for item in ({}, {"boundingbox": None}, {"boundingbox": ["a", "b", "c", "d"]}, {"boundingbox": ["1", "2"]}):
            self.assertEqual(_nominatim_bbox(item), {})


if __name__ == "__main__":
    unittest.main()
