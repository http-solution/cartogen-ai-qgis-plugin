"""PLAN-023 R2-4: rates, relative risk, standardised ratios, Byar intervals, empirical-Bayes smoothing and the small-number flag (pure). Every expected number is worked out by hand in the test that uses it."""
import math
import unittest

from cartogen_ai.core.agent.tools import _health_rates as h


class TestCrudeAndRisk(unittest.TestCase):
    def test_three_areas_with_the_same_rate_each_have_1000_per_100000_and_relative_risk_1(self):
        # 10/1000 = 20/2000 = 30/3000 = 0.01 -> 1,000 per 100,000; the overall rate is 60/6000, also 1,000, so every relative risk is 1
        result = h.analyse([10, 20, 30], [1000, 2000, 3000])
        self.assertEqual([a["rate"] for a in result["areas"]], [1000.0, 1000.0, 1000.0])
        self.assertEqual([a["rel_risk"] for a in result["areas"]], [1.0, 1.0, 1.0])
        self.assertEqual(result["overall_rate"], 1000.0)

    def test_relative_risk_is_the_area_rate_over_the_overall_rate(self):
        # 10/1000 = 0.01 and 30/1000 = 0.03; overall 40/2000 = 0.02; RR = 0.5 and 1.5
        result = h.analyse([10, 30], [1000, 1000])
        self.assertAlmostEqual(result["areas"][0]["rel_risk"], 0.5)
        self.assertAlmostEqual(result["areas"][1]["rel_risk"], 1.5)

    def test_per_changes_only_the_scale(self):
        a = h.analyse([10, 30], [1000, 1000], per=1000)
        self.assertEqual([x["rate"] for x in a["areas"]], [10.0, 30.0])
        self.assertEqual(a["per"], 1000)

    def test_a_zero_case_area_has_rate_zero_and_a_real_upper_bound(self):
        result = h.analyse([0, 40], [1000, 1000])
        self.assertEqual(result["areas"][0]["rate"], 0.0)
        self.assertEqual(result["areas"][0]["rate_lo"], 0.0)
        self.assertGreater(result["areas"][0]["rate_hi"], 0.0)


class TestIntervals(unittest.TestCase):
    def test_byar_is_close_to_the_exact_poisson_interval(self):
        # exact 95% limits: 10 cases 4.795 to 18.390; 100 cases 81.36 to 121.63; 0 cases 0 to 3.689
        lo, hi = h.poisson_interval(10)
        self.assertAlmostEqual(lo, 4.795, delta=0.02)
        self.assertAlmostEqual(hi, 18.390, delta=0.02)
        lo, hi = h.poisson_interval(100)
        self.assertAlmostEqual(lo, 81.36, delta=0.02)
        self.assertAlmostEqual(hi, 121.63, delta=0.02)
        lo, hi = h.poisson_interval(0)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 3.689, delta=0.03)

    def test_the_interval_always_contains_the_count_and_widens_for_fewer_cases(self):
        for c in (1, 2, 5, 17, 60):
            lo, hi = h.poisson_interval(c)
            self.assertLess(lo, c)
            self.assertGreater(hi, c)
        relative = [(h.poisson_interval(c)[1] - h.poisson_interval(c)[0]) / c for c in (5, 50, 500)]
        self.assertGreater(relative[0], relative[1])
        self.assertGreater(relative[1], relative[2])

    def test_a_negative_count_is_refused(self):
        with self.assertRaises(ValueError):
            h.poisson_interval(-1)


class TestSmr(unittest.TestCase):
    def test_observed_over_expected(self):
        ratio, lo, hi = h.smr(30, 20)
        self.assertEqual(ratio, 1.5)
        self.assertAlmostEqual(lo, h.poisson_interval(30)[0] / 20)
        self.assertAlmostEqual(hi, h.poisson_interval(30)[1] / 20)

    def test_expected_must_be_above_zero(self):
        for bad in (0, -3, None, True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                h.smr(5, bad)

    def test_method_smr_without_expected_counts_is_refused_and_says_they_are_never_invented(self):
        with self.assertRaises(ValueError) as ctx:
            h.analyse([10, 20], [1000, 2000], method="smr")
        self.assertIn("does not invent", str(ctx.exception))

    def test_method_smr_uses_the_supplied_expected_counts(self):
        result = h.analyse([30, 10], [1000, 1000], method="smr", expected=[20, 20])
        self.assertEqual([a["value"] for a in result["areas"]], [1.5, 0.5])
        self.assertEqual(result["areas"][0]["expected"], 20.0)

    def test_a_zero_or_missing_expected_count_is_refused(self):
        with self.assertRaises(ValueError):
            h.analyse([30, 10], [1000, 1000], method="smr", expected=[20, 0])
        with self.assertRaises(ValueError):
            h.analyse([30, 10], [1000, 1000], method="smr", expected=[20])


class TestEmpiricalBayes(unittest.TestCase):
    def test_two_areas_with_the_same_rate_are_unchanged(self):
        out = h.eb_global([10, 40], [1000, 4000])
        self.assertEqual(out["rates"], [1000.0, 1000.0])
        self.assertEqual(out["weights"], [0.0, 0.0])

    def test_a_hand_computed_case_with_real_spread(self):
        # pops 10,000 each, cases 10, 30, 50: r = 0.001, 0.003, 0.005, m = 0.003, mean pop 10,000
        # s2 = ((0.002^2 + 0 + 0.002^2) / 3) - 0.003/10000 = 2.66667e-6 - 3e-7 = 2.36667e-6
        # W = s2 / (s2 + m/p) = 2.36667e-6 / 2.66667e-6 = 0.8875; smoothed(first) = 0.8875 x 0.001 + 0.1125 x 0.003 = 0.001225 -> 122.5 per 100,000
        out = h.eb_global([10, 30, 50], [10000, 10000, 10000])
        self.assertAlmostEqual(out["between_variance"], 2.36667e-6, places=10)
        self.assertAlmostEqual(out["weights"][0], 0.8875, places=4)
        self.assertAlmostEqual(out["rates"][0], 122.5, places=2)
        self.assertAlmostEqual(out["rates"][1], 300.0, places=9)
        self.assertAlmostEqual(out["rates"][2], 477.5, places=2)

    def test_small_areas_are_pulled_further_toward_the_overall_rate_than_large_ones(self):
        cases, pops = [1, 400, 50], [100, 20000, 4000]
        out = h.eb_global(cases, pops)
        self.assertLess(out["weights"][0], out["weights"][1])
        self.assertLess(out["weights"][0], out["weights"][2])

    def test_smoothing_keeps_every_rate_between_the_raw_rate_and_the_overall_rate(self):
        cases, pops = [2, 30, 90, 5], [400, 3000, 6000, 1000]
        out = h.eb_global(cases, pops)
        m = out["overall"]
        for c, p, s in zip(cases, pops, out["rates"], strict=True):
            raw = c / p * 100000
            self.assertLessEqual(min(raw, m) - 1e-9, s)
            self.assertLessEqual(s, max(raw, m) + 1e-9)

    def test_the_population_weighted_mean_is_preserved_when_there_is_spread(self):
        cases, pops = [10, 30, 50], [10000, 10000, 10000]
        out = h.eb_global(cases, pops)
        mean = sum(r * p for r, p in zip(out["rates"], pops, strict=True)) / sum(pops)
        self.assertAlmostEqual(mean, out["overall"], places=9)

    def test_method_eb_reports_the_smoothed_rate_as_the_value(self):
        result = h.analyse([10, 30, 50], [10000] * 3, method="eb")
        self.assertAlmostEqual(result["areas"][0]["value"], 122.5, places=2)
        self.assertAlmostEqual(result["areas"][0]["rate"], 100.0, places=9)


class TestSmallNumbers(unittest.TestCase):
    def test_cases_below_five_are_flagged_and_five_is_not(self):
        flags = h.small_number_flags([4, 5, 0, 100], [1000] * 4)
        self.assertEqual(flags, ["cases below 5", None, "cases below 5", None])

    def test_a_population_floor_flags_small_populations(self):
        flags = h.small_number_flags([50, 50], [800, 5000], min_population=1000)
        self.assertEqual(flags, ["population below 1000", None])

    def test_both_reasons_are_named(self):
        self.assertEqual(h.small_number_flags([2], [300], min_population=1000), ["cases below 5 and population below 1000"])

    def test_the_threshold_can_be_changed(self):
        self.assertEqual(h.small_number_flags([9, 10], [1000, 1000], min_cases=10), ["cases below 10", None])

    def test_analyse_counts_the_flagged_areas(self):
        result = h.analyse([2, 50, 10], [500, 5000, 1000])
        self.assertEqual(result["flagged"], 1)
        self.assertEqual(result["areas"][0]["flag"], "cases below 5")


class TestRefusals(unittest.TestCase):
    def test_bad_inputs_name_the_cause(self):
        cases = {"whole": ([2.5, 5], [100, 100]), "pop": ([5, 5], [100, 0]), "none": ([0, 0], [100, 100]), "few": ([5], [100]), "len": ([5, 5], [100])}
        messages = {"whole": "whole numbers", "pop": "above zero", "none": "no cases", "few": "at least 2", "len": "at least 2"}
        for key, (c, p) in cases.items():
            with self.assertRaises(ValueError, msg=key) as ctx:
                h.analyse(c, p)
            self.assertIn(messages[key], str(ctx.exception), key)

    def test_bad_options_are_refused(self):
        for kwargs in ({"per": 0}, {"per": True}, {"min_population": 0}, {"min_cases": -1}, {"min_cases": True}, {"method": "median"}):
            with self.assertRaises(ValueError, msg=repr(kwargs)):
                h.analyse([5, 6], [100, 100], **kwargs)

    def test_nan_and_infinite_values_are_refused(self):
        with self.assertRaises(ValueError):
            h.analyse([5, float("nan")], [100, 100])
        with self.assertRaises(ValueError):
            h.analyse([5, 6], [100, math.inf])


if __name__ == "__main__":
    unittest.main()
