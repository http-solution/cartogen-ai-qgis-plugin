# -*- coding: utf-8 -*-
"""Pure half of the routing/reach styling (tools/routing_style.py): band edges, labels, palettes, group order."""
import unittest

from cartogen_ai.core.agent.tools import routing_style as rs


class TestBandEdges(unittest.TestCase):
    def test_equal_bands_cover_zero_to_max(self):
        edges = rs.cost_band_edges(5000, 5)
        self.assertEqual(len(edges), 5)
        self.assertEqual(edges[0][0], 0.0)
        self.assertEqual(edges[-1][1], 5000.0)
        for (_, hi), (lo, _) in zip(edges, edges[1:]):
            self.assertAlmostEqual(hi, lo)

    def test_a_degenerate_max_still_gives_one_band(self):
        for bad in (0, -5, None, "x"):
            self.assertEqual(len(rs.cost_band_edges(bad)), 1)

    def test_band_count_is_respected(self):
        self.assertEqual(len(rs.cost_band_edges(10, 3)), 3)
        self.assertEqual(len(rs.cost_band_edges(10, 0)), 1)


class TestLabels(unittest.TestCase):
    def test_metres_become_km_when_large(self):
        self.assertEqual(rs.format_cost(800, "meters"), "800 m")
        self.assertEqual(rs.format_cost(3000, "meters"), "3 km")
        self.assertEqual(rs.format_cost(2500, "meters"), "2.5 km")

    def test_hours_become_minutes_then_hours(self):
        self.assertEqual(rs.format_cost(0.25, "hours"), "15 min")
        self.assertEqual(rs.format_cost(0.75, "hours"), "45 min")
        self.assertEqual(rs.format_cost(2, "hours"), "2 h")
        self.assertEqual(rs.format_cost(1.5, "hours"), "1.5 h")

    def test_band_labels_read_low_to_high(self):
        labels = rs.band_labels(rs.cost_band_edges(1, 4), "hours")
        self.assertEqual(labels[0], "0 min - 15 min")
        self.assertEqual(labels[-1], "45 min - 60 min")


class TestPalette(unittest.TestCase):
    def test_five_bands_use_the_whole_ramp_in_order(self):
        self.assertEqual(rs.band_colors(5), list(rs.COST_RAMP))

    def test_fewer_bands_still_span_near_to_far(self):
        three = rs.band_colors(3)
        self.assertEqual(three[0], rs.COST_RAMP[0])
        self.assertEqual(three[-1], rs.COST_RAMP[-1])

    def test_one_band_is_the_near_colour(self):
        self.assertEqual(rs.band_colors(1), [rs.COST_RAMP[0]])

    def test_every_colour_is_a_hex_triplet(self):
        for c in rs.COST_RAMP:
            self.assertRegex(c, r"^#[0-9a-f]{6}$")


class TestReachGroup(unittest.TestCase):
    METHODS = ["concave_hull", "road_buffer", "convex_hull"]

    def test_headline_is_first_then_tightest_to_loosest(self):
        self.assertEqual(rs.reach_layer_order(self.METHODS, "concave_hull"), ["concave_hull", "road_buffer", "convex_hull"])
        self.assertEqual(rs.reach_layer_order(self.METHODS, "road_buffer"), ["road_buffer", "convex_hull", "concave_hull"])

    def test_only_the_headline_is_visible(self):
        vis = rs.reach_visibility(self.METHODS, "concave_hull")
        self.assertEqual([m for m, v in vis.items() if v], ["concave_hull"])

    def test_a_missing_method_is_left_out(self):
        self.assertEqual(rs.reach_layer_order(["concave_hull", "convex_hull"], "concave_hull"), ["concave_hull", "convex_hull"])

    def test_group_name_names_the_facility_layer(self):
        self.assertEqual(rs.group_name_for("Clinics"), "Reach figures: Clinics")

    def test_every_method_has_a_distinct_fill_and_the_upper_bound_is_dashed(self):
        fills = {m: s["fill"] for m, s in rs.REACH_STYLES.items()}
        self.assertEqual(len(set(fills.values())), 3)
        self.assertEqual(rs.REACH_STYLES["convex_hull"]["style"], "dash")
        self.assertEqual(rs.REACH_STYLES["concave_hull"]["style"], "solid")

    def test_fills_are_translucent(self):
        for spec in rs.REACH_STYLES.values():
            self.assertLess(int(spec["fill"].split(",")[3]), 128)


class TestAccessStyles(unittest.TestCase):
    def test_beyond_is_larger_and_drawn_above_within(self):
        within, beyond = rs.ACCESS_STYLES["within"], rs.ACCESS_STYLES["beyond"]
        self.assertGreater(float(beyond["size"]), float(within["size"]))
        self.assertGreater(beyond["pass"], within["pass"])
        self.assertNotEqual(beyond["color"], within["color"])


class TestNoQgisIsSafe(unittest.TestCase):
    def test_styling_calls_are_no_ops_without_qgis(self):
        if rs.QGIS_AVAILABLE:
            self.skipTest("QGIS present")
        self.assertFalse(rs.style_lines_by_cost(object(), "c", [(0, 1)], "meters"))
        self.assertFalse(rs.style_reach_polygon(object(), "concave_hull"))
        self.assertFalse(rs.style_access_points(object()))
        self.assertIsNone(rs.group_reach_layers({}, "concave_hull", "x"))


if __name__ == "__main__":
    unittest.main()
