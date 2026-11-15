"""PLAN-023 R2-2: Getis-Ord Gi*, the Benjamini-Hochberg correction and the hot/cold classes (pure). Offline, no QGIS. Every expected number is worked out by hand in the test that uses it."""
import math
import unittest

from cartogen_ai.core.agent.tools import _spatial_stats as ss
from cartogen_ai.core.agent.tools import _spatial_weights as sw


def grid_rook(rows, cols):
    return [sorted((a * cols + b) for a, b in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)) if 0 <= a < rows and 0 <= b < cols) for r in range(rows) for c in range(cols)]


def single_high(n=25, high=10.0, position=12):
    values = [0.0] * n
    values[position] = high
    return values


class TestGiStar(unittest.TestCase):
    def test_a_uniform_field_has_z_zero_everywhere(self):
        rows = ss.gi_star([5.0] * 25, grid_rook(5, 5))
        self.assertTrue(all(r["z"] == 0.0 and r["p_value"] == 1.0 for r in rows))

    def test_one_cell_of_10_among_zeros_on_a_5_by_5_rook_grid_with_self_gives_exactly_z_2_at_the_centre(self):
        # centre: window = itself + 4 neighbours (k = 5 binary weights); sum w x = 10; Xbar = 10/25 = 0.4; S = sqrt(100/25 - 0.16) = sqrt(3.84);
        # numerator = 10 - 0.4 x 5 = 8; denominator = S x sqrt((25 x 5 - 5^2) / 24) = sqrt(3.84) x sqrt(100/24) = sqrt(3.84 x 4.1667) = sqrt(16) = 4; z = 8 / 4 = 2
        rows = ss.gi_star(single_high(), grid_rook(5, 5))
        self.assertAlmostEqual(rows[12]["z"], 2.0, places=12)

    def test_the_high_cell_has_the_maximum_z_which_its_four_neighbours_share(self):
        # each rook neighbour's window also holds the 10 and has 5 cells, so it scores exactly the same 2.0
        rows = ss.gi_star(single_high(), grid_rook(5, 5))
        top = max(r["z"] for r in rows)
        self.assertAlmostEqual(top, 2.0, places=12)
        self.assertAlmostEqual(rows[12]["z"], top, places=12)
        for j in (7, 11, 13, 17):
            self.assertAlmostEqual(rows[j]["z"], 2.0, places=12)

    def test_a_far_corner_is_slightly_negative_by_the_same_formula(self):
        # corner: k = 3 (itself + 2 neighbours), sum w x = 0: numerator = -0.4 x 3 = -1.2; denominator = sqrt(3.84) x sqrt((25 x 3 - 9) / 24) = sqrt(3.84 x 2.75) = 3.2496; z = -0.36927
        rows = ss.gi_star(single_high(), grid_rook(5, 5))
        self.assertAlmostEqual(rows[0]["z"], -1.2 / math.sqrt(3.84 * 2.75), places=12)
        self.assertAlmostEqual(rows[0]["z"], -0.36927, places=5)

    def test_p_is_the_two_sided_normal_p_of_z(self):
        self.assertAlmostEqual(ss.normal_two_sided_p(1.959964), 0.05, places=5)
        self.assertAlmostEqual(ss.normal_two_sided_p(2.575829), 0.01, places=5)
        self.assertAlmostEqual(ss.normal_two_sided_p(0.0), 1.0, places=12)
        self.assertEqual(ss.normal_two_sided_p(-2.0), ss.normal_two_sided_p(2.0))
        rows = ss.gi_star(single_high(), grid_rook(5, 5))
        self.assertAlmostEqual(rows[12]["p_value"], 0.0455003, places=6)

    def test_a_feature_with_no_neighbour_is_not_tested(self):
        rows = ss.gi_star([1.0, 2.0, 3.0, 9.0], [[1], [0, 2], [1], []])
        self.assertIsNone(rows[3]["z"])
        self.assertIsNone(rows[3]["p_value"])
        self.assertEqual(rows[3]["neighbours"], 0)

    def test_two_tight_groups_of_highs_and_lows_give_opposite_signs(self):
        # a path of 6: the first three high, the last three low, each window of 3 neighbours
        values = [9.0, 9.0, 9.0, 1.0, 1.0, 1.0]
        nb = [[1], [0, 2], [1, 3], [2, 4], [3, 5], [4]]
        rows = ss.gi_star(values, nb)
        self.assertGreater(rows[0]["z"], 0)
        self.assertLess(rows[5]["z"], 0)
        self.assertAlmostEqual(rows[0]["z"], -rows[5]["z"], places=12)

    def test_distance_band_neighbours_feed_it(self):
        points = [(float(x), float(y)) for y in range(5) for x in range(5)]
        rows = ss.gi_star(single_high(), sw.distance_band(points, 1.0))
        self.assertAlmostEqual(rows[12]["z"], 2.0, places=12)          # distance 1 on a unit grid is the rook neighbourhood

    def test_refusals(self):
        nb = grid_rook(3, 3)
        for values in ([1, 2, "x", 4, 5, 6, 7, 8, 9], [1, 2, None, 4, 5, 6, 7, 8, 9], [1, 2, 3]):
            with self.assertRaises(ValueError, msg=repr(values)):
                ss.gi_star(values, nb)
        with self.assertRaises(ValueError):
            ss.gi_star([1, 2], [[1], [0]])


class TestBenjaminiHochberg(unittest.TestCase):
    P = (0.001, 0.008, 0.039, 0.041, 0.2)

    def test_the_adjusted_values_by_hand(self):
        # m = 5, sorted p x m / rank: 0.005, 0.02, 0.065, 0.05125, 0.2; then the running minimum from the largest rank down: q5 = 0.2, q4 = 0.05125, q3 = min(0.05125, 0.065) = 0.05125, q2 = 0.02, q1 = 0.005
        q = ss.benjamini_hochberg(list(self.P))
        for got, expected in zip(q, (0.005, 0.02, 0.05125, 0.05125, 0.2), strict=True):
            self.assertAlmostEqual(got, expected, places=12)

    def test_at_alpha_005_it_rejects_exactly_the_first_two(self):
        q = ss.benjamini_hochberg(list(self.P))
        self.assertEqual([i for i, v in enumerate(q) if v <= 0.05], [0, 1])

    def test_order_is_preserved_for_unsorted_input(self):
        q = ss.benjamini_hochberg([0.2, 0.001, 0.041, 0.008, 0.039])
        self.assertAlmostEqual(q[1], 0.005)
        self.assertAlmostEqual(q[3], 0.02)
        self.assertAlmostEqual(q[0], 0.2)

    def test_adjusted_is_never_smaller_than_raw_and_never_above_one(self):
        raw = [0.3, 0.9, 0.5, 0.04, 0.8]
        for r, q in zip(raw, ss.benjamini_hochberg(raw), strict=True):
            self.assertGreaterEqual(q, r - 1e-12)
            self.assertLessEqual(q, 1.0)

    def test_a_single_test_is_unchanged(self):
        self.assertEqual(ss.benjamini_hochberg([0.03]), [0.03])
        self.assertEqual(ss.benjamini_hochberg([]), [])

    def test_a_bad_p_value_is_refused(self):
        for bad in (-0.1, 1.1, None, "0.5", True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                ss.benjamini_hochberg([0.5, bad])


class TestClasses(unittest.TestCase):
    def test_levels_from_the_p_value_and_the_sign_of_z(self):
        self.assertEqual(ss.hot_cold_class(3.0, 0.002), "Hot spot 99%")
        self.assertEqual(ss.hot_cold_class(-3.0, 0.002), "Cold spot 99%")
        self.assertEqual(ss.hot_cold_class(2.0, 0.0455), "Hot spot 95%")
        self.assertEqual(ss.hot_cold_class(-2.0, 0.0455), "Cold spot 95%")
        self.assertEqual(ss.hot_cold_class(1.7, 0.089, alpha=0.10), "Hot spot 90%")

    def test_nothing_weaker_than_alpha_is_reported(self):
        self.assertEqual(ss.hot_cold_class(1.7, 0.089, alpha=0.05), "Not significant")
        self.assertEqual(ss.hot_cold_class(2.0, 0.0455, alpha=0.01), "Not significant")
        self.assertEqual(ss.hot_cold_class(3.0, 0.002, alpha=0.01), "Hot spot 99%")

    def test_zero_or_missing_is_never_a_spot(self):
        self.assertEqual(ss.hot_cold_class(0, 0.0), "Not significant")
        self.assertEqual(ss.hot_cold_class(None, 0.01), "Not significant")
        self.assertEqual(ss.hot_cold_class(2.0, None), "Not significant")

    def test_the_boundaries_belong_to_the_stricter_class(self):
        self.assertEqual(ss.hot_cold_class(2.6, 0.01), "Hot spot 99%")
        self.assertEqual(ss.hot_cold_class(2.0, 0.05), "Hot spot 95%")
        self.assertEqual(ss.hot_cold_class(1.7, 0.10, alpha=0.10), "Hot spot 90%")


class TestHotspots(unittest.TestCase):
    def _block(self):
        # a 6 by 6 grid with a 2 by 2 block of high counts: strong enough to survive the correction
        values = [1.0] * 36
        for r in (2, 3):
            for c in (2, 3):
                values[r * 6 + c] = 20.0
        return values

    def test_the_high_block_is_found_and_the_corrected_p_is_never_below_the_raw_p(self):
        result = ss.hotspots(self._block(), grid_rook(6, 6), fdr=True, alpha=0.05)
        classes = [f["class"] for f in result["features"]]
        hot = {i for i, c in enumerate(classes) if c.startswith("Hot")}
        self.assertTrue(hot)
        self.assertTrue(hot <= {2 * 6 + 2, 2 * 6 + 3, 3 * 6 + 2, 3 * 6 + 3, 1 * 6 + 2, 1 * 6 + 3, 4 * 6 + 2, 4 * 6 + 3, 2 * 6 + 1, 3 * 6 + 1, 2 * 6 + 4, 3 * 6 + 4}, hot)
        for f in result["features"]:
            self.assertGreaterEqual(f["p_adjusted"], f["p_value"] - 1e-12)
        self.assertEqual(sum(result["counts"].values()), 36)
        self.assertEqual(result["tested"], 36)

    def test_the_correction_can_remove_a_spot_the_raw_p_would_report(self):
        values = [1.0] * 36
        values[14] = 6.0
        values[15] = 5.0
        corrected = ss.hotspots(values, grid_rook(6, 6), fdr=True, alpha=0.05)
        raw = ss.hotspots(values, grid_rook(6, 6), fdr=False, alpha=0.05)
        n_raw = sum(1 for f in raw["features"] if f["class"] != "Not significant")
        n_fdr = sum(1 for f in corrected["features"] if f["class"] != "Not significant")
        self.assertGreaterEqual(n_raw, n_fdr)
        self.assertTrue(all(f["p_adjusted"] is None for f in raw["features"]))
        self.assertFalse(raw["fdr"])

    def test_a_uniform_field_has_no_spots(self):
        result = ss.hotspots([3.0] * 25, grid_rook(5, 5))
        self.assertEqual(result["counts"], {"Not significant": 25})

    def test_islands_are_labelled_and_left_out_of_the_correction(self):
        values = [1.0, 2.0, 3.0, 4.0, 50.0]
        nb = [[1], [0, 2], [1, 3], [2], []]
        result = ss.hotspots(values, nb)
        self.assertEqual(result["features"][4]["class"], "No neighbours")
        self.assertIsNone(result["features"][4]["p_adjusted"])
        self.assertEqual(result["tested"], 4)

    def test_alpha_is_validated(self):
        for alpha in (0, 1, -0.5, 2, True, None):
            with self.assertRaises(ValueError, msg=repr(alpha)):
                ss.hotspots([1.0, 2.0, 3.0, 4.0], [[1], [0, 2], [1, 3], [2]], alpha=alpha)

    def test_the_result_is_deterministic(self):
        a = ss.hotspots(self._block(), grid_rook(6, 6))
        b = ss.hotspots(self._block(), grid_rook(6, 6))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
