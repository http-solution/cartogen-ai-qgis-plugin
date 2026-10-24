"""free_box: where a layout chart or profile goes when the caller gives no position (rc48 hand test A12: three charts all landed at 10, 10)."""
import unittest

from cartogen_ai.core.agent.tools.gap_options import free_box

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
