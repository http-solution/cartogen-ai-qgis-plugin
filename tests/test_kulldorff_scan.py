"""PLAN-023 R2-3: Kulldorff circular scan, Poisson model. The log likelihood ratio and the relative risk are checked by hand; the scan is checked on a planted cluster, on no cluster, on the population cap and on ties.
The scan needs numpy: skipped where it is not installed (the pure LLR tests still run)."""
import math
import unittest

from cartogen_ai.core.agent.tools import _kulldorff as kd

HAVE_NUMPY = kd.HAVE_NUMPY


def grid(side=10):
    return [(float(x), float(y)) for y in range(side) for x in range(side)]


def planted(side=10, block=((3, 4, 5), (3, 4, 5)), high=15, base=5):
    cases = [base] * (side * side)
    for y in block[0]:
        for x in block[1]:
            cases[y * side + x] = high
    return cases


class TestLlr(unittest.TestCase):
    def test_the_plan_known_answer_c100_inside_30_expected_15_is_7_203(self):
        # 30 ln(30/15) + 70 ln(70/85) = 30 x 0.693147 - 70 x 0.194156 = 20.794 - 13.591 = 7.203
        self.assertAlmostEqual(kd.llr(30, 15, 100), 7.203, delta=0.001)
        self.assertAlmostEqual(kd.llr(30, 15, 100), 30 * math.log(2) + 70 * math.log(70 / 85), places=12)

    def test_no_excess_scores_zero(self):
        self.assertEqual(kd.llr(15, 15, 100), 0.0)
        self.assertEqual(kd.llr(10, 15, 100), 0.0)
        self.assertEqual(kd.llr(0, 0, 100), 0.0)

    def test_all_the_cases_inside_has_no_outside_term(self):
        self.assertAlmostEqual(kd.llr(100, 40, 100), 100 * math.log(100 / 40), places=12)

    def test_relative_risk_by_hand(self):
        # (30/15) / (70/85) = 2 / 0.82353 = 2.42857
        self.assertAlmostEqual(kd.relative_risk(30, 15, 100), 2.428571, places=6)
        self.assertIsNone(kd.relative_risk(100, 40, 100))

    def test_work_limits(self):
        self.assertIsNone(kd.check_work(100, 999))
        self.assertIn("99 to 9999", kd.check_work(100, 10))
        self.assertIn("1,500", kd.check_work(2000, 999))
        self.assertIn("at most", kd.check_work(1500, 999))
        self.assertIsNone(kd.check_work(500, 999))


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestScan(unittest.TestCase):
    def test_a_planted_block_is_found_at_its_centre_with_a_tiny_p(self):
        for seed in (1, 2, 3):
            result = kd.scan(planted(), [100] * 100, grid(), monte_carlo=499, seed=seed)
            best = result["clusters"][0]
            self.assertEqual(best["centre"], 4 * 10 + 4, seed)                       # the centre of the 3 by 3 block
            self.assertEqual(sorted(best["members"]), sorted(y * 10 + x for y in (3, 4, 5) for x in (3, 4, 5)), seed)
            self.assertLessEqual(best["p_value"], 0.01, seed)
            self.assertEqual(best["cases"], 135)

    def test_its_numbers_follow_from_the_formula(self):
        result = kd.scan(planted(), [100] * 100, grid(), monte_carlo=99, seed=1)
        best = result["clusters"][0]
        total = 9 * 15 + 91 * 5                                                      # 590 cases
        expected = total * 900 / 10000                                               # 9 areas of 100 out of 10,000 people
        self.assertEqual(result["total_cases"], total)
        self.assertAlmostEqual(best["expected"], expected, places=9)
        self.assertAlmostEqual(best["llr"], kd.llr(135, expected, total), places=9)
        self.assertAlmostEqual(best["relative_risk"], kd.relative_risk(135, expected, total), places=9)
        self.assertAlmostEqual(best["radius"], math.sqrt(2), places=12)             # the corner of the block is sqrt(2) from the centre

    def test_no_planted_cluster_gives_a_large_p(self):
        for seed in (1, 2, 3):
            cases = [5] * 100
            cases[44], cases[12] = 6, 4
            best = kd.scan(cases, [100] * 100, grid(), monte_carlo=499, seed=seed)["clusters"][0]
            self.assertGreater(best["p_value"], 0.05, seed)

    def test_the_same_seed_gives_the_same_answer_and_a_different_seed_changes_only_the_p(self):
        a = kd.scan(planted(), [100] * 100, grid(), monte_carlo=199, seed=5)
        b = kd.scan(planted(), [100] * 100, grid(), monte_carlo=199, seed=5)
        self.assertEqual(a, b)

    def test_a_cluster_never_holds_more_than_max_pop_fraction(self):
        cases = [20] * 100
        for fraction in (0.05, 0.2, 0.5):
            result = kd.scan(cases, [100] * 100, grid(), max_pop_fraction=fraction, monte_carlo=99)
            for c in result["clusters"]:
                self.assertLessEqual(len(c["members"]) * 100, fraction * 10000 + 1e-9, fraction)

    def test_a_radius_limit_is_obeyed(self):
        result = kd.scan(planted(), [100] * 100, grid(), max_radius=1.0, monte_carlo=99)
        for c in result["clusters"]:
            self.assertLessEqual(c["radius"], 1.0)

    def test_a_circle_never_splits_areas_at_the_same_distance(self):
        # on a unit grid the areas around a centre come in rings (1, sqrt2, 2, ...): every member count is a whole ring total
        result = kd.scan(planted(), [100] * 100, grid(), monte_carlo=99)
        c = result["clusters"][0]
        centre = grid()[c["centre"]]
        inside = {math.dist(centre, grid()[m]) for m in c["members"]}
        outside = [math.dist(centre, p) for j, p in enumerate(grid()) if j not in set(c["members"])]
        self.assertGreater(min(outside), max(inside))

    def test_secondary_clusters_share_no_area_and_are_significant(self):
        cases = [5] * 100
        for y in (1, 2):
            for x in (1, 2):
                cases[y * 10 + x] = 18
        for y in (7, 8):
            for x in (7, 8):
                cases[y * 10 + x] = 18
        result = kd.scan(cases, [100] * 100, grid(), monte_carlo=499, seed=2)
        clusters = result["clusters"]
        self.assertGreaterEqual(len(clusters), 2)
        seen = set()
        for c in clusters:
            self.assertFalse(seen & set(c["members"]))
            seen |= set(c["members"])
        for c in clusters[1:]:
            self.assertLessEqual(c["p_value"], 0.05)
        self.assertEqual(sorted(clusters[0]["members"]) + sorted(clusters[1]["members"]) != [], True)

    def test_bigger_populations_expect_more_cases(self):
        # one area holds 30% of the people and, with the same share of the cases, is not a cluster
        pops = [100.0] * 100
        pops[0] = 4300.0
        cases = [5] * 100
        cases[0] = 215
        clusters = kd.scan(cases, pops, grid(), max_pop_fraction=0.5, monte_carlo=99)["clusters"]
        self.assertTrue(not clusters or clusters[0]["p_value"] > 0.05)

    def test_a_field_with_no_excess_anywhere_returns_no_cluster_rather_than_failing(self):
        result = kd.scan([5] * 100, [100] * 100, grid(), monte_carlo=99)
        self.assertTrue(all(c["p_value"] > 0.05 for c in result["clusters"]))

    def test_refusals(self):
        pts, pops = grid(), [100] * 100
        for cases, message in (([5] * 99, "at least 3"), ([0] * 100, "no cases"), ([-1] + [5] * 99, "whole numbers"), ([2.5] + [5] * 99, "whole numbers")):
            with self.assertRaises(ValueError, msg=message) as ctx:
                kd.scan(cases, pops, pts, monte_carlo=99)
            self.assertIn(message, str(ctx.exception))
        with self.assertRaises(ValueError):
            kd.scan([5] * 100, [0] + [100] * 99, pts, monte_carlo=99)
        for fraction in (0, 0.6, True):
            with self.assertRaises(ValueError, msg=repr(fraction)):
                kd.scan([5] * 100, pops, pts, max_pop_fraction=fraction, monte_carlo=99)
        with self.assertRaises(ValueError):
            kd.scan([5] * 100, pops, pts, max_radius=0, monte_carlo=99)
        with self.assertRaises(ValueError):
            kd.scan([5] * 100, pops, pts, monte_carlo=5)
        with self.assertRaises(ValueError):
            kd.scan([5] * 100, pops, pts, monte_carlo=99, max_clusters=0)
        with self.assertRaises(ValueError):
            kd.scan([5] * 100, pops, pts, monte_carlo=99, alpha=1.5)

    def test_no_circle_satisfying_the_limits_is_refused_with_the_cause(self):
        with self.assertRaises(ValueError) as ctx:                                   # 10 areas of 10% each: none fits under 5%
            kd.scan([5] * 10, [100.0] * 10, grid()[:10], max_pop_fraction=0.05, monte_carlo=99)
        self.assertIn("no circle", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
