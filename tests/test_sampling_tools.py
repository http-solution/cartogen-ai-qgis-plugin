# -*- coding: utf-8 -*-
"""H3 design_sampling_frame: sample-size statistics and the reproducible draw are pure; layer work is in test_sampling_tools_live.py."""
import unittest

from cartogen_ai.core.agent.tools import sampling_tools as s


class TestZScore(unittest.TestCase):
    def test_standard_values(self):
        self.assertAlmostEqual(s.z_score(0.95), 1.959964, places=5)
        self.assertAlmostEqual(s.z_score(0.90), 1.644854, places=5)
        self.assertAlmostEqual(s.z_score(0.99), 2.575829, places=5)


class TestSampleSize(unittest.TestCase):
    def test_textbook_value_for_an_unknown_population(self):
        self.assertEqual(s.sample_size(None), 385)                      # 1.96^2 * .25 / .05^2 = 384.16

    def test_finite_population_correction(self):
        self.assertEqual(s.sample_size(1000), 278)
        self.assertEqual(s.sample_size(100), 80)

    def test_design_effect_multiplies_before_the_correction(self):
        self.assertEqual(s.sample_size(None, design_effect=2.0), 769)

    def test_nonresponse_inflates_after_the_correction(self):
        self.assertEqual(s.sample_size(1000, nonresponse_rate=0.1), 309)    # 277.7 / 0.9

    def test_never_more_than_the_stratum_and_zero_for_empty(self):
        self.assertEqual(s.sample_size(30), 28)
        self.assertEqual(s.sample_size(30, nonresponse_rate=0.5), 30)
        self.assertEqual(s.sample_size(0), 0)

    def test_tighter_margin_needs_more(self):
        self.assertGreater(s.sample_size(5000, margin_of_error=0.03), s.sample_size(5000, margin_of_error=0.05))

    def test_a_lower_expected_proportion_needs_fewer(self):
        self.assertLess(s.sample_size(None, expected_proportion=0.1), s.sample_size(None, expected_proportion=0.5))


class TestValidate(unittest.TestCase):
    def test_defaults_are_valid(self):
        self.assertIsNone(s.validate_design(0.95, 0.05, 0.5, 1.0, 0.0))

    def test_each_bound(self):
        for args in ((1.0, 0.05, 0.5, 1.0, 0.0), (0.3, 0.05, 0.5, 1.0, 0.0), (0.95, 0.0, 0.5, 1.0, 0.0),
                     (0.95, 0.05, 0.0, 1.0, 0.0), (0.95, 0.05, 1.0, 1.0, 0.0), (0.95, 0.05, 0.5, 0.9, 0.0),
                     (0.95, 0.05, 0.5, 1.0, 1.0), (0.95, "x", 0.5, 1.0, 0.0)):
            self.assertIsNotNone(s.validate_design(*args), args)


class TestDraw(unittest.TestCase):
    def test_reproducible_for_a_seed_and_distinct(self):
        a = s.draw_indices(1000, 50, 7)
        self.assertEqual(a, s.draw_indices(1000, 50, 7))
        self.assertEqual(len(set(a)), 50)
        self.assertNotEqual(a, s.draw_indices(1000, 50, 8))

    def test_takes_everything_when_the_sample_is_not_smaller(self):
        self.assertEqual(s.draw_indices(5, 9, 1), [0, 1, 2, 3, 4])
        self.assertEqual(s.draw_indices(0, 3, 1), [])

    def test_stratum_seeds_are_stable_and_independent_of_other_strata(self):
        self.assertEqual(s.stratum_seed(42, "A"), s.stratum_seed(42, "A"))
        self.assertNotEqual(s.stratum_seed(42, "A"), s.stratum_seed(42, "B"))
        self.assertNotEqual(s.stratum_seed(42, "A"), s.stratum_seed(43, "A"))


class TestText(unittest.TestCase):
    def test_assumptions_are_stated(self):
        t = s.design_text(0.95, 0.05, 0.5, 1.0, 0.1, 99)
        for part in ("95% confidence", "+/-5 percentage points", "expected proportion of 0.5", "design effect of 1", "10% non-response", "seed 99"):
            self.assertIn(part, t)


class TestTool(unittest.TestCase):
    def test_wired_as_create(self):
        from cartogen_ai.core.agent import tool_operations
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        self.assertIn("design_sampling_frame", TOOL_REGISTRY)
        self.assertEqual(tool_operations.get_tool_operation_type("design_sampling_frame"), tool_operations.CREATE)

    def test_bad_design_is_refused_before_qgis(self):
        self.assertIn("design_effect", s.design_sampling_frame("strata", design_effect=0.5)["error"])


if __name__ == "__main__":
    unittest.main()
