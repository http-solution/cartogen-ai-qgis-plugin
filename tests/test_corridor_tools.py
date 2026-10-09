# -*- coding: utf-8 -*-
"""Pure parts of corridor_tools (no QGIS needed)."""
import unittest

from cartogen_ai.core.agent.tools import corridor_tools as ct


class TestPure(unittest.TestCase):
    def test_utm_zone_for_known_places(self):
        self.assertEqual(ct.utm_epsg_for(45.2, 15.4), 32638)       # Marib
        self.assertEqual(ct.utm_epsg_for(43.4, 13.0), 32638)       # Mocha corridor
        self.assertEqual(ct.utm_epsg_for(-74.0, 40.7), 32618)
        self.assertEqual(ct.utm_epsg_for(151.2, -33.9), 32756)     # southern hemisphere

    def test_total_and_longest_are_different_numbers(self):
        s = ct.summarise_pieces([1000, 3000, 2000], [1000, 1000])
        self.assertEqual(s["clear_length_km"], 6.0)
        self.assertEqual(s["longest_clear_segment_km"], 3.0)
        self.assertEqual(s["compromised_length_km"], 2.0)
        self.assertEqual(s["total_length_km"], 8.0)
        self.assertEqual((s["clear_segment_count"], s["compromised_segment_count"]), (3, 2))

    def test_no_clear_piece_means_zero_not_an_error(self):
        s = ct.summarise_pieces([], [500])
        self.assertEqual((s["clear_length_km"], s["longest_clear_segment_km"]), (0.0, 0.0))

    def test_tools_degrade_outside_qgis(self):
        self.assertIn("error", ct.split_lines_by_zones("a", "b"))
        self.assertIn("error", ct.generate_contours("dem"))


if __name__ == "__main__":
    unittest.main()
