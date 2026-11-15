"""Boundary tests for the helpers split out of profiler._classify_field_semantics (audit finding 6). The old function and the split one were
compared on 60,000 fuzzed fields with no difference; these keep the thresholds from drifting."""
import unittest

from cartogen_ai.core.representation import profiler as p


class TestSkewnessAndDistribution(unittest.TestCase):
    def test_five_or_fewer_values_or_a_constant_series_have_zero_skew(self):
        self.assertEqual(p._skewness([1, 2, 3, 4, 100], 22.0), 0.0)
        self.assertEqual(p._skewness([5.0] * 10, 5.0), 0.0)

    def test_a_long_right_tail_is_positive(self):
        vals = [1.0] * 9 + [50.0]
        self.assertGreater(p._skewness(vals, sum(vals) / len(vals)), 1.2)

    def test_distribution_label_thresholds(self):
        self.assertEqual(p._distribution_label(0.0), "normal")
        self.assertEqual(p._distribution_label(0.49), "normal")
        self.assertEqual(p._distribution_label(0.5), "uniform")
        self.assertEqual(p._distribution_label(-1.2), "uniform")
        self.assertEqual(p._distribution_label(1.21), "right_skewed")
        self.assertEqual(p._distribution_label(-1.21), "left_skewed")


class TestNumericSemanticType(unittest.TestCase):
    def kind(self, name, values):
        return p._numeric_semantic_type(name, values, min(values), max(values))

    def test_bearing_in_range_is_directional_but_not_out_of_range(self):
        self.assertEqual(self.kind("wind_dir", [0.0, 90.0, 360.0]), "directional")
        self.assertNotEqual(self.kind("wind_dir", [0.0, 361.0]), "directional")

    def test_unit_interval_and_fractional_percentages_are_rates(self):
        self.assertEqual(self.kind("x", [0.1, 0.9]), "rate_percentage")
        self.assertEqual(self.kind("x", [10.5, 99.0]), "rate_percentage")
        self.assertEqual(self.kind("coverage_rate", [3.0, 5000.0]), "rate_percentage")

    def test_non_negative_integers_are_counts_and_an_all_negative_field_is_not(self):
        # The 2026-09-20 vacuous-truth bug: only-negative values must not be called a positive quantity.
        self.assertEqual(self.kind("x", [3.0, 250.0]), "positive_quantity")
        self.assertEqual(self.kind("x", [-1.5, -2.3]), "nominal")
        self.assertEqual(self.kind("elevation", [100.5, 2500.5]), "positive_quantity")


class TestClassifyField(unittest.TestCase):
    def test_status_name_is_ordered_status_and_other_text_is_nominal(self):
        self.assertEqual(p._classify_field_semantics("severity", ["low", "high"], "String").semantic_type, "ordered_status")
        self.assertEqual(p._classify_field_semantics("colour", ["red", "blue"], "String").semantic_type, "nominal")

    def test_date_name_or_type_wins_before_the_values_are_read(self):
        self.assertEqual(p._classify_field_semantics("x", ["1", "2"], "Date").semantic_type, "datetime")
        self.assertEqual(p._classify_field_semantics("created_at", [1, 2], "Integer").semantic_type, "datetime")

    def test_missing_percent_counts_none_and_blank(self):
        prof = p._classify_field_semantics("x", [1, None, "", 4], "Integer")
        self.assertEqual(prof.missing_percent, 50.0)


if __name__ == "__main__":
    unittest.main()
