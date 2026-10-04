# -*- coding: utf-8 -*-
"""H6 aggregate_survey_indicator: the estimates, intervals and suppression are pure; layer work is in test_survey_tools_live.py."""
import unittest

from cartogen_ai.core.agent.tools import survey_tools as s


class TestParseBinary(unittest.TestCase):
    def test_usual_spellings(self):
        for yes in (1, "1", "Yes", "TRUE", "y", True, 1.0):
            self.assertEqual(s.parse_binary(yes), 1.0, yes)
        for no in (0, "0", "No", "false", False, 0.0):
            self.assertEqual(s.parse_binary(no), 0.0, no)

    def test_unknown_and_missing_are_none(self):
        for v in (None, "", "NULL", "maybe", "dk"):
            self.assertIsNone(s.parse_binary(v), v)

    def test_positive_values_define_yes_and_everything_else_is_no(self):
        self.assertEqual(s.parse_binary("No access", ["no access"]), 1.0)
        self.assertEqual(s.parse_binary("Piped", ["No access"]), 0.0)
        self.assertIsNone(s.parse_binary("", ["No access"]))


class TestStatistics(unittest.TestCase):
    def test_kish_effective_n(self):
        self.assertEqual(s.kish_effective_n([1, 1, 1, 1]), 4.0)
        self.assertAlmostEqual(s.kish_effective_n([1, 3]), 1.6)

    def test_wilson_matches_the_textbook_value(self):
        low, high = s.wilson_interval(0.5, 100, 1.959964)
        self.assertAlmostEqual(low, 0.4038, places=3)
        self.assertAlmostEqual(high, 0.5962, places=3)

    def test_wilson_stays_inside_zero_and_one_at_the_extremes(self):
        low, high = s.wilson_interval(1.0, 40, 1.96)
        self.assertLessEqual(high, 1.0)
        self.assertGreater(low, 0.85)
        self.assertEqual(s.wilson_interval(0.5, 0, 1.96), (None, None))

    def test_weighted_mean_interval(self):
        mean, low, high, n_eff = s.weighted_mean_interval([1, 2, 3, 4], [1, 1, 1, 1], 1.96)
        self.assertAlmostEqual(mean, 2.5)
        self.assertAlmostEqual(n_eff, 4.0)
        self.assertAlmostEqual(low, 2.5 - 1.96 * (1.25 / 4) ** 0.5, places=6)

    def test_design_effect_widens_the_interval(self):
        a = s.weighted_mean_interval([1, 2, 3, 4], [1] * 4, 1.96, 1.0)
        b = s.weighted_mean_interval([1, 2, 3, 4], [1] * 4, 1.96, 2.0)
        self.assertGreater(b[2] - b[1], a[2] - a[1])


def recs():
    return ([{"group": "A", "value": "yes", "weight": 2.0}] * 20 + [{"group": "A", "value": "no", "weight": 1.0}] * 20
            + [{"group": "B", "value": "yes", "weight": 1.0}] * 5)


class TestAggregate(unittest.TestCase):
    def test_weighted_proportion_and_suppression(self):
        out = s.aggregate(recs(), min_n=30)
        a, b = out["groups"]
        self.assertEqual((a["group"], a["respondents"], a["suppressed"]), ("A", 40, False))
        self.assertAlmostEqual(a["estimate"], 0.6667, places=4)       # 40 / 60
        self.assertEqual(a["effective_n"], 36.0)
        self.assertLess(a["ci_low"], a["estimate"])
        self.assertGreater(a["ci_high"], a["estimate"])
        self.assertTrue(b["suppressed"])
        self.assertNotIn("estimate", b)
        self.assertEqual(b["respondents"], "<30")                       # the exact small count is not given out

    def test_unweighted_when_no_weight_is_given(self):
        r = [{"group": "A", "value": 1}] * 15 + [{"group": "A", "value": 0}] * 15
        self.assertEqual(s.aggregate(r, min_n=30)["groups"][0]["estimate"], 0.5)

    def test_bad_records_are_excluded_and_counted(self):
        r = ([{"group": "A", "value": 1, "weight": 1.0}] * 30 + [{"group": None, "value": 1}, {"group": "A", "value": "dk"},
             {"group": "A", "value": 1, "weight": -2}, {"group": "A", "value": 1, "weight": "x"}])
        out = s.aggregate(r, min_n=30)
        self.assertEqual(out["excluded"], {"missing_group": 1, "missing_or_invalid_value": 1, "invalid_weight": 2})
        self.assertEqual(out["groups"][0]["respondents"], 30)

    def test_mean(self):
        r = [{"group": "A", "value": float(i), "weight": 1.0} for i in range(1, 41)]
        g = s.aggregate(r, kind="mean", min_n=30)["groups"][0]
        self.assertAlmostEqual(g["estimate"], 20.5)
        self.assertLess(g["ci_low"], 20.5)

    def test_positive_values(self):
        r = [{"group": "A", "value": "No access"}] * 10 + [{"group": "A", "value": "Piped"}] * 30
        self.assertEqual(s.aggregate(r, min_n=30, positive_values=["no access"])["groups"][0]["estimate"], 0.25)

    def test_min_n_is_inclusive(self):
        r = [{"group": "A", "value": 1}] * 30
        self.assertFalse(s.aggregate(r, min_n=30)["groups"][0]["suppressed"])
        self.assertTrue(s.aggregate(r, min_n=31)["groups"][0]["suppressed"])


class TestValidateAndWiring(unittest.TestCase):
    def test_validate(self):
        self.assertIsNone(s.validate_options("proportion", 30, 0.95, 1.0))
        for args in (("share", 30, 0.95, 1.0), ("mean", 0, 0.95, 1.0), ("mean", 30, 1.0, 1.0), ("mean", 30, 0.95, 0.5), ("mean", "x", 0.95, 1)):
            self.assertIsNotNone(s.validate_options(*args), args)

    def test_wired_as_read(self):
        from cartogen_ai.core.agent import tool_operations
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        self.assertIn("aggregate_survey_indicator", TOOL_REGISTRY)
        self.assertEqual(tool_operations.get_tool_operation_type("aggregate_survey_indicator"), tool_operations.READ)

    def test_bad_options_are_refused_before_qgis(self):
        self.assertIn("min_n", s.aggregate_survey_indicator("l", "g", "i", min_n=0)["error"])


if __name__ == "__main__":
    unittest.main()
