# -*- coding: utf-8 -*-
"""H4 evaluate_forecast_trigger: the rule evaluator is pure, so the whole rule is tested here; reading a layer needs QGIS."""
import datetime
import unittest

from cartogen_ai.core.agent.tools import trigger_tools as t

D = datetime.date
TODAY = D(2026, 10, 4)


def rows():
    return [
        {"unit": "A", "q": 120.0, "day": "2026-10-05", "p": 0.8},
        {"unit": "A", "q": 90.0, "day": "2026-10-06", "p": 0.9},
        {"unit": "B", "q": 130.0, "day": "2026-10-20", "p": 0.9},   # outside a 7-day window
        {"unit": "B", "q": 80.0, "day": "2026-10-05", "p": 0.9},
        {"unit": "C", "q": None, "day": "2026-10-05", "p": 0.9},
        {"unit": "C", "q": "n/a", "day": "2026-10-05", "p": 0.9},
    ]


def by_unit(res):
    return {u["unit"]: u for u in res["units"]}


class TestHelpers(unittest.TestCase):
    def test_to_date(self):
        self.assertEqual(t.to_date("2026-10-04T12:00:00"), D(2026, 10, 4))
        self.assertEqual(t.to_date(datetime.datetime(2026, 10, 4, 3)), D(2026, 10, 4))
        for bad in (None, "", "NULL", "soon", "04/10/2026"):
            self.assertIsNone(t.to_date(bad), bad)

    def test_to_date_reads_qdate_like_objects(self):
        class QD:
            def toPyDate(self):
                return D(2026, 1, 2)
        self.assertEqual(t.to_date(QD()), D(2026, 1, 2))

    def test_to_number(self):
        self.assertEqual(t.to_number("3.5"), 3.5)
        for bad in (None, "x", True, float("nan")):
            self.assertIsNone(t.to_number(bad), bad)


class TestValidateRule(unittest.TestCase):
    def test_threshold_is_mandatory(self):
        self.assertIn("no default", t.validate_rule(None, ">=", None, None, 1))
        self.assertIn("no default", t.validate_rule("abc", ">=", None, None, 1))

    def test_other_checks(self):
        self.assertIsNone(t.validate_rule(100, ">=", 7, 0.5, 1))
        self.assertIsNotNone(t.validate_rule(100, "=>", None, None, 1))
        self.assertIsNotNone(t.validate_rule(100, ">=", -1, None, 1))
        self.assertIsNotNone(t.validate_rule(100, ">=", None, 1.5, 1))
        self.assertIsNotNone(t.validate_rule(100, ">=", None, None, 0))


class TestEvaluate(unittest.TestCase):
    def test_threshold_per_unit_without_a_window(self):
        res = t.evaluate_triggers(rows(), "q", 100, ">=", unit_key="unit")
        u = by_unit(res)
        self.assertTrue(u["A"]["activated"])
        self.assertTrue(u["B"]["activated"])          # the 130 row counts when there is no lead window
        self.assertFalse(u["C"]["activated"])
        self.assertEqual(res["activated_count"], 2)
        self.assertEqual(res["rows_skipped"], {"non_numeric_value": 2})

    def test_lead_window_excludes_late_forecasts(self):
        res = t.evaluate_triggers(rows(), "q", 100, ">=", "unit", "day", TODAY, lead_days=7)
        u = by_unit(res)
        self.assertTrue(u["A"]["activated"])
        self.assertFalse(u["B"]["activated"])         # its only exceedance is 16 days out
        self.assertEqual(res["rows_skipped"]["outside_lead_window"], 1)
        self.assertEqual(u["A"]["first_exceedance"], "2026-10-05")

    def test_window_edges_are_inclusive(self):
        r = [{"unit": "A", "q": 5, "day": "2026-10-11"}, {"unit": "A", "q": 5, "day": "2026-10-04"}]
        res = t.evaluate_triggers(r, "q", 5, ">=", "unit", "day", TODAY, lead_days=7, min_exceedances=2)
        self.assertTrue(by_unit(res)["A"]["activated"])

    def test_unreadable_dates_are_skipped_never_assumed_in_window(self):
        r = [{"unit": "A", "q": 500, "day": "someday"}, {"unit": "A", "q": 500, "day": None}]
        res = t.evaluate_triggers(r, "q", 100, ">=", "unit", "day", TODAY, lead_days=7)
        self.assertFalse(by_unit(res)["A"]["activated"])
        self.assertEqual(res["rows_skipped"]["unreadable_date"], 2)
        self.assertEqual(res["rows_used"], 0)

    def test_probability_must_also_be_met(self):
        r = [{"unit": "A", "q": 200, "p": 0.3}, {"unit": "B", "q": 200, "p": 0.7}, {"unit": "C", "q": 200, "p": None}]
        res = t.evaluate_triggers(r, "q", 100, ">=", "unit", probability_key="p", min_probability=0.5)
        u = by_unit(res)
        self.assertFalse(u["A"]["activated"])
        self.assertTrue(u["B"]["activated"])
        self.assertEqual(res["rows_skipped"], {"missing_probability": 1})

    def test_min_exceedances(self):
        r = [{"unit": "A", "q": 200}, {"unit": "A", "q": 50}]
        self.assertFalse(by_unit(t.evaluate_triggers(r, "q", 100, ">=", "unit", min_exceedances=2))["A"]["activated"])
        self.assertTrue(by_unit(t.evaluate_triggers(r + [{"unit": "A", "q": 300}], "q", 100, ">=", "unit",
                                                    min_exceedances=2))["A"]["activated"])

    def test_comparison_operators_and_strictness(self):
        r = [{"unit": "A", "q": 100}]
        self.assertTrue(by_unit(t.evaluate_triggers(r, "q", 100, ">=", "unit"))["A"]["activated"])
        self.assertFalse(by_unit(t.evaluate_triggers(r, "q", 100, ">", "unit"))["A"]["activated"])
        self.assertTrue(by_unit(t.evaluate_triggers(r, "q", 100, "<=", "unit"))["A"]["activated"])
        self.assertFalse(by_unit(t.evaluate_triggers(r, "q", 100, "<", "unit"))["A"]["activated"])

    def test_no_unit_field_means_one_unit(self):
        res = t.evaluate_triggers(rows(), "q", 100, ">=")
        self.assertEqual(res["unit_count"], 1)
        self.assertEqual(res["units"][0]["unit"], "all")

    def test_lead_days_without_date_key_is_an_error(self):
        with self.assertRaises(ValueError):
            t.evaluate_triggers(rows(), "q", 100, ">=", "unit", lead_days=7)

    def test_activated_units_sort_first(self):
        res = t.evaluate_triggers(rows(), "q", 100, ">=", "unit")
        self.assertEqual([u["activated"] for u in res["units"]], [True, True, False])


class TestDescribeRule(unittest.TestCase):
    def test_states_every_part_of_the_rule(self):
        s = t.describe_rule("q", 100, ">=", "unit", "day", TODAY, 7, "p", 0.5, 2)
        for part in ("q >= 100", "p >= 0.5", "2026-10-04 to 2026-10-11", "7 days lead", "at least 2", "per 'unit'"):
            self.assertIn(part, s)


class TestTool(unittest.TestCase):
    def test_wired_as_read_only(self):
        from cartogen_ai.core.agent import tool_operations
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        self.assertIn("evaluate_forecast_trigger", TOOL_REGISTRY)
        self.assertEqual(tool_operations.get_tool_operation_type("evaluate_forecast_trigger"), tool_operations.READ)

    def test_a_missing_threshold_is_refused_before_anything_else(self):
        res = t.evaluate_forecast_trigger("forecast", "q")
        self.assertIn("no default", res["error"])

    def test_inconsistent_arguments(self):
        self.assertIn("date_field", t.evaluate_forecast_trigger("f", "q", threshold=1, lead_days=3)["error"])
        self.assertIn("go together", t.evaluate_forecast_trigger("f", "q", threshold=1, probability_field="p")["error"])
        self.assertIn("ISO date", t.evaluate_forecast_trigger("f", "q", threshold=1, as_of="tomorrow")["error"])


if __name__ == "__main__":
    unittest.main()
