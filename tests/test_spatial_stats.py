"""PLAN-023 R2-1: global Moran's I and Local Moran (pure). Offline, no QGIS, no numpy. Known answers are hand-computed (written out in each test); p-values rest on a shuffler that is stable across Python versions, so exact seeded values
are pinned. The published Columbus crime example (I = 0.4857) is NOT tested: its data cannot be committed with a clear licence from this sandbox, so no claim is made that this code reproduces it; the hand-computed cases below stand in
for it and the gap is recorded in docs/plans/PLAN-023 (the plan's own risk table allows exactly this)."""
import unittest
from typing import ClassVar

from cartogen_ai.core.agent.tools import _spatial_stats as ss
from cartogen_ai.core.agent.tools import _spatial_weights as sw


def grid_rook(rows, cols):
    return [sorted((a * cols + b) for a, b in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)) if 0 <= a < rows and 0 <= b < cols) for r in range(rows) for c in range(cols)]


CHECKER = [(-1) ** (r + c) for r in range(4) for c in range(4)]


class TestGlobalMoran(unittest.TestCase):
    def test_a_4_by_4_checkerboard_with_rook_binary_weights_is_exactly_minus_one(self):
        # z = +-1 (mean 0), 24 edges -> 48 links all between opposite signs: sum w z z = -48, S0 = 48, sum z^2 = 16, I = (16/48) x (-48/16) = -1
        result = ss.morans_i(CHECKER, grid_rook(4, 4), "binary", 99, 1)
        self.assertEqual(result["I"], -1.0)
        self.assertEqual(result["S0"], 48)

    def test_the_expected_value_for_16_features_is_minus_one_fifteenth(self):
        self.assertAlmostEqual(ss.morans_i(CHECKER, grid_rook(4, 4), "binary", 99, 1)["expected_I"], -1 / 15)
        self.assertEqual(f"{ss.morans_i(CHECKER, grid_rook(4, 4), 'binary', 99, 1)['expected_I']:.4f}", "-0.0667")

    def test_a_path_of_four_values_1_2_3_4_has_I_one_third(self):
        # z = -1.5 -0.5 0.5 1.5; the three edges give 0.75, -0.25, 0.75; sum w z z over both directions = 2 x 1.25 = 2.5; S0 = 6; sum z^2 = 5; I = (4/6) x (2.5/5) = 1/3
        result = ss.morans_i([1, 2, 3, 4], [[1], [0, 2], [1, 3], [2]], "binary", 99, 1)
        self.assertAlmostEqual(result["I"], 1 / 3, places=12)

    def test_row_standardised_weights_give_the_same_I_formula_with_S0_equal_to_n(self):
        result = ss.morans_i([1, 2, 3, 4], [[1], [0, 2], [1, 3], [2]], "row", 99, 1)
        self.assertAlmostEqual(result["S0"], 4.0)
        # z = -1.5 -0.5 0.5 1.5; lags (mean of the neighbours' z) = -0.5, -0.5, 0.5, 0.5; sum z x lag = 0.75 + 0.25 + 0.25 + 0.75 = 2.0; I = 2.0 / sum z^2 (5) = 0.4
        self.assertAlmostEqual(result["I"], 0.4, places=12)

    def test_a_constant_field_is_refused_with_the_cause(self):
        with self.assertRaisesRegex(ValueError, "all values are equal"):
            ss.morans_i([5] * 16, grid_rook(4, 4), "row", 99, 1)

    def test_weights_with_no_link_are_refused(self):
        with self.assertRaisesRegex(ValueError, "no feature has a neighbour"):
            ss.morans_i([1, 2, 3, 4], [[], [], [], []], "row", 99, 1)

    def test_a_smooth_gradient_is_significantly_clustered_and_a_checkerboard_significantly_alternating(self):
        gradient = ss.morans_i([r + c for r in range(6) for c in range(6)], grid_rook(6, 6), "row", 999, 1)
        self.assertAlmostEqual(gradient["I"], 8 / 9, places=12)
        self.assertLessEqual(gradient["p_value"], 0.01)
        board = ss.morans_i(CHECKER, grid_rook(4, 4), "binary", 999, 1)
        self.assertLessEqual(board["p_value"], 0.01)
        self.assertLess(board["z_sim"], -3)

    def test_an_arbitrary_arrangement_is_not_distinguishable_from_random(self):
        x, values = 12345, []
        for _ in range(36):
            x = (1103515245 * x + 12345) % 2147483648
            values.append(x % 100)
        result = ss.morans_i(values, grid_rook(6, 6), "row", 999, 1)
        self.assertGreater(result["p_value"], 0.05)

    def test_the_same_seed_gives_identical_numbers_and_another_seed_does_not(self):
        values = [r * 3 + (c * 7) % 5 for r in range(5) for c in range(5)]
        a = ss.morans_i(values, grid_rook(5, 5), "row", 199, 7)
        b = ss.morans_i(values, grid_rook(5, 5), "row", 199, 7)
        c = ss.morans_i(values, grid_rook(5, 5), "row", 199, 8)
        self.assertEqual(a, b)
        self.assertEqual(a["I"], c["I"])
        self.assertNotEqual(a["z_sim"], c["z_sim"])

    def test_the_seeded_shuffler_is_pinned_so_a_python_upgrade_cannot_change_every_p_value(self):
        self.assertEqual(ss.SeededShuffler(1).shuffle(list(range(10))), [8, 0, 3, 4, 5, 2, 9, 6, 7, 1])
        result = ss.morans_i(CHECKER, grid_rook(4, 4), "binary", 999, 1)
        self.assertEqual(result["p_value"], 0.002)
        self.assertEqual(result["p_less"], 0.001)
        self.assertAlmostEqual(result["z_sim"], -4.887222631353143, places=9)

    def test_islands_are_reported_and_take_no_part(self):
        result = ss.morans_i([1, 2, 3, 4, 9], [[1], [0, 2], [1, 3], [2], []], "binary", 99, 1)
        self.assertEqual(result["islands"], [4])
        self.assertEqual(result["S0"], 6)

    def test_bad_input_is_refused(self):
        nb = grid_rook(2, 2)
        for values in ([1, 2, "x", 4], [1, 2, None, 4], [1, 2, float("nan"), 4], [1, 2, True, 4], [1, 2]):
            with self.assertRaises(ValueError, msg=repr(values)):
                ss.morans_i(values, nb, "row", 99, 1)
        with self.assertRaises(ValueError):
            ss.morans_i([1, 2, 3], [[1], [0]], "row", 99, 1)

    def test_the_work_cap_and_the_permutation_range_are_enforced(self):
        nb = grid_rook(4, 4)
        for permutations in (98, 10000, 0, -5, 99.5, True, None):
            self.assertIsNotNone(ss.check_work(nb, permutations), repr(permutations))
        self.assertIsNone(ss.check_work(nb, 99))
        self.assertIsNone(ss.check_work(nb, 9999))
        big = [[(i + 1) % 2000, (i + 2) % 2000, (i + 3) % 2000, (i + 4) % 2000, (i + 5) % 2000, (i + 6) % 2000] for i in range(2000)]
        self.assertIn("will run in one go", ss.check_work(big, 9999))
        self.assertIsNone(ss.check_work(big, 999))


class TestLocalMoran(unittest.TestCase):
    BLOCK: ClassVar[set] = {0, 1, 6, 7}

    def _values(self):
        values = [0.0] * 36
        for r in (0, 1):
            for c in (0, 1):
                values[r * 6 + c] = 10.0
        values[35] = 10.0
        return values

    def test_the_local_values_average_to_the_global_value_for_row_weights(self):
        # with row-standardised weights S0 = n and I = (sum z lag) / (sum z^2) = (1/n) x sum_i I_i, by the definitions in the module docstring
        values = self._values()
        local = ss.local_morans(values, grid_rook(6, 6), "row", 99, 1)
        global_i = ss.morans_i(values, grid_rook(6, 6), "row", 99, 1)["I"]
        self.assertAlmostEqual(sum(f["local_i"] for f in local["features"]) / 36, global_i, places=12)

    def test_a_high_block_in_a_low_field_is_hh_inside_and_ll_around(self):
        local = ss.local_morans(self._values(), grid_rook(6, 6), "row", 999, 1)
        classes = [f["class"] for f in local["features"]]
        hh = {i for i, c in enumerate(classes) if c == "HH"}
        self.assertTrue(hh and hh <= self.BLOCK, hh)
        self.assertIn("LL", classes)
        for i, c in enumerate(classes):
            if c == "LL":
                self.assertNotIn(i, self.BLOCK)
        self.assertEqual(sum(local["counts"].values()), 36)

    def test_a_lone_high_among_the_lowest_values_is_hl_when_the_test_is_loose_enough(self):
        # lows vary (0, 1, 2 in turn) so that shuffling can change what the centre cell sits next to; the centre is 20 and its four rook neighbours are all 0, the lowest value
        values = [float(i % 3) for i in range(25)]
        values[12] = 20.0
        for j in (7, 11, 13, 17):
            values[j] = 0.0
        local = ss.local_morans(values, grid_rook(5, 5), "row", 999, 1, alpha=0.2)
        centre = local["features"][12]
        self.assertEqual(centre["class"], "HL")
        self.assertGreater(centre["z"], 0)
        self.assertLess(centre["lag"], 0)
        self.assertLess(centre["local_i"], 0)

    def test_identical_neighbours_cannot_be_distinguished_by_shuffling_so_a_lone_high_among_equal_lows_is_not_significant(self):
        values = [0.0] * 25
        values[12] = 10.0
        local = ss.local_morans(values, grid_rook(5, 5), "row", 99, 1, alpha=0.5)
        self.assertEqual(local["features"][12]["class"], "not significant")
        self.assertEqual(local["features"][12]["p_value"], 1.0)

    def test_the_quadrant_rule(self):
        self.assertEqual(ss.quadrant(1, 1), "HH")
        self.assertEqual(ss.quadrant(-1, -1), "LL")
        self.assertEqual(ss.quadrant(1, -1), "HL")
        self.assertEqual(ss.quadrant(-1, 1), "LH")
        self.assertIsNone(ss.quadrant(0, 1))
        self.assertIsNone(ss.quadrant(1, 0))

    def test_a_feature_with_no_neighbour_gets_no_statistic(self):
        local = ss.local_morans([1, 2, 3, 4, 9], [[1], [0, 2], [1, 3], [2], []], "binary", 99, 1)
        last = local["features"][4]
        self.assertEqual(last["class"], "no neighbours")
        self.assertIsNone(last["local_i"])
        self.assertIsNone(last["p_value"])
        self.assertEqual(local["counts"]["no neighbours"], 1)

    def test_refusals(self):
        nb = grid_rook(3, 3)
        with self.assertRaisesRegex(ValueError, "all values are equal"):
            ss.local_morans([2] * 9, nb, "row", 99, 1)
        with self.assertRaisesRegex(ValueError, "no feature has a neighbour"):
            ss.local_morans(list(range(9)), [[] for _ in range(9)], "row", 99, 1)
        for alpha in (0, 1, -0.1, 1.5, True, None):
            with self.assertRaises(ValueError, msg=repr(alpha)):
                ss.local_morans(list(range(9)), nb, "row", 99, 1, alpha)

    def test_local_results_are_reproducible_and_carry_the_uncorrected_caveat(self):
        a = ss.local_morans(self._values(), grid_rook(6, 6), "row", 199, 3)
        b = ss.local_morans(self._values(), grid_rook(6, 6), "row", 199, 3)
        self.assertEqual(a, b)
        self.assertIn("not corrected", a["note"])


class TestInterpretation(unittest.TestCase):
    def _result(self, i, p):
        return {"I": i, "expected_I": -0.0667, "p_value": p, "permutations": 999}

    def test_the_three_sentences(self):
        similar = ss.interpret_global(self._result(0.5, 0.001))
        different = ss.interpret_global(self._result(-0.5, 0.001))
        neither = ss.interpret_global(self._result(0.05, 0.4))
        self.assertIn("SIMILAR values", similar)
        self.assertIn("DIFFERENT values", different)
        self.assertIn("not distinguishable from a random arrangement", neither)
        self.assertIn("Moran's I = 0.500", similar)

    def test_no_sentence_claims_a_cause(self):
        for result in (self._result(0.5, 0.001), self._result(-0.5, 0.001), self._result(0.05, 0.4)):
            text = ss.interpret_global(result).lower()
            for banned in ("because", "caused", "due to", "outbreak", "hotspot"):
                self.assertNotIn(banned, text)


class TestWeightsAndStatsTogether(unittest.TestCase):
    def test_queen_weights_on_a_grid_of_squares_feed_the_statistic(self):
        polygons = [[[(c, r), (c + 1, r), (c + 1, r + 1), (c, r + 1), (c, r)]] for r in range(4) for c in range(4)]
        queen = ss.morans_i(CHECKER, sw.contiguity(polygons, "queen"), "binary", 99, 1)
        rook = ss.morans_i(CHECKER, sw.contiguity(polygons, "rook"), "binary", 99, 1)
        self.assertEqual(rook["I"], -1.0)
        self.assertGreater(queen["I"], rook["I"])      # queen adds diagonal neighbours of the SAME sign, which pulls I up from -1


if __name__ == "__main__":
    unittest.main()
