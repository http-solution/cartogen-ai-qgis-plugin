# -*- coding: utf-8 -*-
"""Pure half of tools/humanitarian_style.py: palettes and ordering rules. The QGIS half is in test_humanitarian_style_live.py."""
import unittest

from cartogen_ai.core.agent.tools import humanitarian_style as hs


class TestPriority(unittest.TestCase):
    def test_order_is_high_to_low_then_unranked(self):
        cats = hs.priority_categories(["Low", "High", None, "Medium", "High"])
        self.assertEqual([c[0] for c in cats], ["High", "Medium", "Low", ""])
        self.assertEqual(cats[-1][2], "unranked")

    def test_only_present_values_and_no_unranked_when_all_ranked(self):
        cats = hs.priority_categories(["High", "Low"])
        self.assertEqual([c[0] for c in cats], ["High", "Low"])

    def test_all_unranked_has_no_ranked_category(self):
        self.assertEqual([c[0] for c in hs.priority_categories([None, None])], [""])

    def test_high_is_the_darkest(self):
        def lum(h):
            return sum(int(h[i:i + 2], 16) for i in (1, 3, 5))
        self.assertLess(lum(hs.PRIORITY_COLORS["High"]), lum(hs.PRIORITY_COLORS["Medium"]))
        self.assertLess(lum(hs.PRIORITY_COLORS["Medium"]), lum(hs.PRIORITY_COLORS["Low"]))


class TestAlerts(unittest.TestCase):
    def test_red_orange_green_and_unknowns_in_grey(self):
        cats = hs.alert_categories(["Green", "Red", "Weird", "Orange", None, ""])
        self.assertEqual([c[0] for c in cats], ["Red", "Orange", "Green", "Weird"])
        self.assertEqual(cats[-1][1], "#808080")


class TestQualitative(unittest.TestCase):
    def test_deterministic_and_distinct(self):
        a = hs.qualitative_colors(["North", "South", "East", None, ""])
        self.assertEqual(a, hs.qualitative_colors(["East", "South", "North"]))
        self.assertEqual(len(set(a.values())), 3)

    def test_cycles_beyond_the_palette(self):
        many = hs.qualitative_colors([f"s{i:02d}" for i in range(13)])
        self.assertEqual(len(many), 13)
        self.assertEqual(many["s00"], many["s10"])


class TestDiverging(unittest.TestCase):
    def test_symmetric_about_zero_with_a_transparent_zero(self):
        stops = hs.diverging_stops(-2.0, 8.0)
        values = [v for v, _c, _l in stops]
        self.assertEqual(values, sorted(values))
        self.assertAlmostEqual(values[0], -8.0)
        self.assertAlmostEqual(values[-1], 8.0)
        zero = next(c for v, c, _l in stops if v == 0)
        self.assertEqual(zero[3], 0)

    def test_blue_for_decrease_red_for_increase(self):
        stops = hs.diverging_stops(-1, 1)
        self.assertGreater(stops[0][1][2], stops[0][1][0])     # blue channel above red
        self.assertGreater(stops[-1][1][0], stops[-1][1][2])   # red channel above blue

    def test_flat_or_bad_range_falls_back(self):
        self.assertAlmostEqual(hs.diverging_stops(0, 0)[-1][0], 1.0)
        self.assertAlmostEqual(hs.diverging_stops("x", None)[-1][0], 1.0)


class TestWiring(unittest.TestCase):
    def test_stylers_are_safe_without_qgis(self):
        if hs.QGIS_AVAILABLE:
            self.skipTest("QGIS present")
        for fn in (hs.style_task_grid, hs.style_sample_points, hs.style_diverging_raster):
            self.assertFalse(fn(None))
        self.assertFalse(hs.style_barrier_segments(None))
        self.assertFalse(hs.style_hazard_layer(None, "gdacs"))


if __name__ == "__main__":
    unittest.main()
