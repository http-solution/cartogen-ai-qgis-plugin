"""free_box: where a layout chart or profile goes when the caller gives no position (rc48 hand test A12: three charts all landed at 10, 10)."""
import unittest
from typing import ClassVar

from cartogen_ai.core.agent.tools.gap_options import fit_free_box, free_box

A4_LANDSCAPE = (297.0, 210.0)


class TestFreeBox(unittest.TestCase):
    def test_an_empty_page_gives_the_top_left_margin(self):
        self.assertEqual(free_box([], *A4_LANDSCAPE, 120, 80), (10.0, 10.0))

    def test_three_charts_never_overlap(self):
        taken = []
        for _ in range(3):
            spot = free_box(taken, *A4_LANDSCAPE, 120, 80)
            self.assertIsNotNone(spot)
            taken.append((spot[0], spot[1], 120, 80))
        for i, a in enumerate(taken):
            for b in taken[i + 1:]:
                overlap = a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
                self.assertFalse(overlap, (a, b))

    def test_the_second_chart_goes_beside_the_first_when_it_fits(self):
        self.assertEqual(free_box([(10, 10, 120, 80)], *A4_LANDSCAPE, 120, 80), (135.0, 10.0))

    def test_when_the_row_is_full_it_starts_the_next_row(self):
        taken = [(10, 10, 120, 80), (135, 10, 120, 80)]
        self.assertEqual(free_box(taken, *A4_LANDSCAPE, 120, 80), (10.0, 95.0))

    def test_a_full_page_gives_none(self):
        self.assertIsNone(free_box([(0, 0, 297, 210)], *A4_LANDSCAPE, 120, 80))

    def test_a_box_bigger_than_the_page_gives_none(self):
        self.assertIsNone(free_box([], *A4_LANDSCAPE, 400, 80))

    def test_boxes_are_kept_apart_by_the_gap(self):
        spot = free_box([(10, 10, 100, 50)], *A4_LANDSCAPE, 50, 50, gap_mm=5.0)
        self.assertGreaterEqual(spot[0], 115.0)


if __name__ == "__main__":
    unittest.main()


class TestFitFreeBox(unittest.TestCase):
    """DEF-37 (round-3 smoke row E3): on a layout whose map fills most of the page a full-size chart had no spot and landed on the map."""

    # a header band across the top and a map filling the rest except a 270 x 45 mm strip at the bottom
    CROWDED: ClassVar = [(0, 0, 297, 25), (10, 30, 277, 120)]

    def test_full_size_when_it_fits(self):
        self.assertEqual(fit_free_box([], *A4_LANDSCAPE, 120, 80), (10.0, 10.0, 120, 80, False))

    def test_it_shrinks_into_the_free_strip_instead_of_overlapping(self):
        self.assertIsNone(free_box(self.CROWDED, *A4_LANDSCAPE, 120, 80))
        x, y, w, h, shrunk = fit_free_box(self.CROWDED, *A4_LANDSCAPE, 120, 80)
        self.assertTrue(shrunk)
        self.assertLess(w, 120)
        for tx, ty, tw, th in self.CROWDED:
            self.assertFalse(x < tx + tw and tx < x + w and y < ty + th and ty < y + h, (x, y, w, h))

    def test_the_shape_is_kept_when_shrinking(self):
        _, _, w, h, _ = fit_free_box(self.CROWDED, *A4_LANDSCAPE, 120, 80)
        self.assertAlmostEqual(w / h, 120 / 80)

    def test_a_wide_profile_also_shrinks_to_fit(self):
        x, _, w, _, shrunk = fit_free_box(self.CROWDED, *A4_LANDSCAPE, 180, 80)
        self.assertTrue(shrunk)
        self.assertLessEqual(x + w, 297 - 10 + 1e-9)

    def test_never_below_the_minimum_size(self):
        self.assertIsNone(fit_free_box([(0, 0, 297, 210)], *A4_LANDSCAPE, 120, 80))
        full_but_small_gap = [(0, 0, 297, 170)]            # only a 30 mm strip left: under the 35 mm minimum height
        self.assertIsNone(fit_free_box(full_but_small_gap, *A4_LANDSCAPE, 120, 80))
