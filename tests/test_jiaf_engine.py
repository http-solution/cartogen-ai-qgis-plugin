# -*- coding: utf-8 -*-
"""JIAF 2 stage 3 engine, offline. The flag readings are settings, not verified against OCHA's worksheet formulas (docs/JIAF2_ANALYSIS_SUPPORT_PLAN_2026-10-04.md
section 6); these tests pin the readings the module makes, plus the manual's own rules (Box 21, Box 22, Tables 3A and 3B1)."""
import csv
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools import jiaf_engine as je
from cartogen_ai.core.agent.tools import jiaf_inputs as ji

S = je.DEFAULTS


def unit(pin=None, sev=None, pop=None, outcomes=None, code="U1", stored=None):
    u = ji._empty_unit(code, code, "A1", "A1", None)
    u["pin"] = dict(pin or {})
    u["severity"] = dict(sev or {})
    u["population"] = pop
    u["outcomes"] = outcomes or {}
    u["stored"] = stored or {}
    return u


def flags(u, settings=None, previous=None):
    expected = list(je.MAIN_SECTORS)
    ranked = je.ranked_pins(u, expected)
    return je.pin_flags(u, ranked, je.merge_settings(settings), expected, previous), ranked


class TestMosaic(unittest.TestCase):
    def test_highest_sector_wins_and_aors_never_enter(self):
        u = unit(pin={"wash": 100, "health": 250, "gbv": 9999, "child_protection": 9999})
        ranked = je.ranked_pins(u, je.MAIN_SECTORS)
        self.assertEqual(je.preliminary_pin(ranked), (250, ["health"]))

    def test_ties_list_every_driver_and_nothing_is_summed(self):
        ranked = je.ranked_pins(unit(pin={"wash": 100, "health": 100, "shelter": 40}), je.MAIN_SECTORS)
        self.assertEqual(je.preliminary_pin(ranked), (100, ["health", "wash"]))

    def test_no_pin_at_all(self):
        self.assertEqual(je.preliminary_pin(je.ranked_pins(unit(), je.MAIN_SECTORS)), (None, []))

    def test_national_is_the_sum_over_units_of_the_highest_not_a_cross_sector_sum(self):
        units = [unit(pin={"wash": 100, "health": 300}, code="A"), unit(pin={"wash": 50, "health": 10}, code="B")]
        res = je.analyze(units)
        self.assertEqual(res["totals"]["preliminary_pin"], 350.0)


class TestPinFlags(unittest.TestCase):
    def test_flag_1_counts_missing_and_zero_sectors_against_the_setting(self):
        u = unit(pin={s: 10 for s in je.MAIN_SECTORS[:6]} | {"wash": 0})
        f, _ = flags(u)
        self.assertTrue(f[1]["fired"])
        self.assertEqual(f[1]["value"], 2)  # shelter absent + wash at zero
        f, _ = flags(u, {"f1_min_sectors": 3})
        self.assertFalse(f[1]["fired"])

    def test_flags_2_and_3_are_relative_to_the_second_and_third(self):
        f, _ = flags(unit(pin={"wash": 300, "health": 100, "shelter": 90}))
        self.assertAlmostEqual(f[2]["value"], 2.0)  # a ">200 percent difference" is possible only against the second value
        self.assertTrue(f[2]["fired"])
        self.assertAlmostEqual(f[3]["value"], 300 / 90 - 1)
        f, _ = flags(unit(pin={"wash": 120, "health": 100, "shelter": 90}))
        self.assertFalse(f[2]["fired"])
        self.assertFalse(f[3]["fired"])

    def test_the_threshold_itself_fires(self):
        f, _ = flags(unit(pin={"wash": 130, "health": 100, "shelter": 100}))
        self.assertTrue(f[2]["fired"])

    def test_an_undefined_difference_fires_and_too_few_sectors_is_not_evaluable(self):
        f, _ = flags(unit(pin={"wash": 100, "health": 0, "shelter": 0}))
        self.assertTrue(f[2]["fired"])
        self.assertIsNone(f[2]["value"])
        f, _ = flags(unit(pin={"wash": 100}))
        self.assertIsNone(f[2]["fired"])
        self.assertIsNone(f[3]["fired"])

    def test_flag_4_only_when_sub_population_sectors_are_named(self):
        u = unit(pin={"nutrition": 500, "wash": 100})
        self.assertIsNone(flags(u)[0][4]["fired"])
        self.assertTrue(flags(u, {"f4_subpopulation_sectors": ["nutrition"]})[0][4]["fired"])
        self.assertFalse(flags(unit(pin={"wash": 500, "nutrition": 100}), {"f4_subpopulation_sectors": ["nutrition"]})[0][4]["fired"])

    def test_flag_5_share_of_population_and_the_over_100_percent_note(self):
        f, _ = flags(unit(pin={"wash": 95}, pop=100))
        self.assertTrue(f[5]["fired"])
        self.assertIsNone(f[5]["note"])
        f, _ = flags(unit(pin={"wash": 120}, pop=100))
        self.assertIn("data error", f[5]["note"])
        self.assertFalse(flags(unit(pin={"wash": 80}, pop=100))[0][5]["fired"])
        self.assertIsNone(flags(unit(pin={"wash": 80}))[0][5]["fired"])

    def test_flag_6_compares_the_same_sector_with_last_year(self):
        cur = unit(pin={"wash": 5000, "health": 100})
        prev = unit(pin={"wash": 2000, "health": 9000})
        f, _ = flags(cur, previous=prev)
        self.assertTrue(f[6]["fired"])  # wash 5000 vs wash 2000: +150%, not vs health
        self.assertAlmostEqual(f[6]["value"], 1.5)
        self.assertFalse(flags(cur, previous=unit(pin={"wash": 4000}))[0][6]["fired"])
        self.assertIsNone(flags(cur, previous=unit(pin={"wash": 500}))[0][6]["fired"])  # base below 1,000
        self.assertIsNone(flags(cur)[0][6]["fired"])  # no previous year


class TestSeverity(unittest.TestCase):
    def test_the_overlap_rule_of_box_22(self):
        cases = [
            ([1, 1, 1, 1, 1, 1, 1, 1], 1), ([2, 2, 2, 1, 1, 1, 1, 1], 1), ([2, 2, 2, 2, 1, 1, 1, 1], 2),
            ([3, 3, 3, 3, 1, 1, 1, 1], 3), ([4, 4, 4, 3, 3, 2, 1, 1], 3), ([4, 4, 4, 4, 1, 1, 1, 1], 4),
            ([5, 5, 4, 4, 1, 1, 1, 1], 5), ([5, 5, 4, 3, 3, 3, 3, 3], 3), ([5, 5, 5, 5, 4, 1, 1, 1], 5), ([5, 4, 4, 4, 1, 1, 1, 1], 4),
        ]
        for phases, want in cases:
            self.assertEqual(je.preliminary_severity(phases), want, phases)

    def test_zero_and_missing_do_not_count_and_nothing_reporting_is_none(self):
        self.assertEqual(je.preliminary_severity([0, 0, None, 3, 3, 3, 3]), 3)
        self.assertIsNone(je.preliminary_severity([0, None, None]))

    def test_severity_flag_1_and_4(self):
        f = je.severity_flags(unit(), [5, 3, 3, 3, 1, 1, 1, 1], 3, je.merge_settings())
        self.assertTrue(f[1]["fired"])
        self.assertFalse(f[4]["fired"])
        f = je.severity_flags(unit(), [4, 4, 4, 4, 4, 1, 1, 1], 4, je.merge_settings())
        self.assertTrue(f[4]["fired"])  # more than 4 sectors in phase 4
        f = je.severity_flags(unit(), [4, 4, 4, 4, 1, 1, 1, 1], 4, je.merge_settings())
        self.assertFalse(f[4]["fired"])  # exactly 4

    def test_outcome_flags_are_not_evaluable_without_analyst_phases(self):
        f = je.severity_flags(unit(), [3, 3, 3, 3], 3, je.merge_settings())
        self.assertIsNone(f[2]["fired"])
        self.assertIsNone(f[3]["fired"])

    def test_outcome_flags_2_and_3(self):
        s = je.merge_settings()
        f = je.severity_flags(unit(outcomes={"mortality": 5}), [3, 3, 3, 3], 3, s)
        self.assertTrue(f[2]["fired"])
        self.assertFalse(f[3]["fired"])
        f = je.severity_flags(unit(outcomes={"mortality": 4, "malnutrition": 2, "epidemics": 3}), [3, 3, 3, 3], 3, s)
        self.assertFalse(f[2]["fired"])
        self.assertTrue(f[3]["fired"])
        f = je.severity_flags(unit(outcomes={"mortality": 4, "malnutrition": "x", "epidemics": 3}), [3, 3, 3, 3], 3, s)
        self.assertFalse(f[3]["fired"])  # a non-phase value is ignored, not guessed


class TestRankAndSettings(unittest.TestCase):
    def test_final_pin_rank(self):
        ranked = je.ranked_pins(unit(pin={"wash": 300, "health": 200, "shelter": 100, "nutrition": 50}), je.MAIN_SECTORS)
        self.assertEqual([je.rank_of_value(ranked, v) for v in (300, 200.4, 100, 50, 7)], [1, 2, 3, "other", "other"])
        self.assertIsNone(je.rank_of_value([], 5))

    def test_settings_validation(self):
        for bad in ({"nope": 1}, {"f1_min_sectors": 0}, {"f2_pct": -1}, {"f4_subpopulation_sectors": ["gbv"]}):
            with self.assertRaises(ValueError):
                je.merge_settings(bad)
        self.assertEqual(je.merge_settings({"f2_pct": None})["f2_pct"], 0.30)


class TestAnalyzeAndTool(unittest.TestCase):
    GRID = [
        ["#adm2 +code", "#adm2 +name", "#inneed", "#severity", "#inneed +wsh", "#severity +wsh", "#inneed +shl", "#severity +shl",
         "#inneed +hea", "#severity +hea", "#inneed +nut", "#severity +nut"],
        ["YE1", "A", 300, 3, 100, 3, 300, 3, 200, 3, 50, 3],
        ["YE2", "B", 120, 2, 120, 2, 90, 2, 10, 1, 0, 1],
    ]

    def _csv(self, grid):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(grid)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_tool_end_to_end(self):
        out = je.compute_jiaf_preliminary(self._csv(self.GRID))
        self.assertTrue(out["success"], out)
        self.assertEqual(out["units"], 2)
        self.assertEqual(out["national_preliminary_pin"], 420.0)  # 300 + 120, not 300 + 120 + others
        self.assertEqual(out["preliminary_severity_distribution"], {1: 1, 3: 1})  # four sectors in phase 3; and only two sectors at phase 2 or worse
        self.assertIn("not endorsed", out["statement"])
        self.assertIn("not the Final PiN", out["stage"])
        self.assertTrue(out["readings_to_confirm"])
        self.assertEqual(out["stored_comparison"]["final_pin_rank"], {"1": 2})  # the file's total equals the highest in both units
        self.assertIn("flag_6_note", out)

    def test_previous_year_enables_flag_6(self):
        prev = [self.GRID[0], ["YE1", "A", 100, 3, 100, 3, 100, 3, 100, 3, 50, 3], self.GRID[2]]
        out = je.compute_jiaf_preliminary(self._csv(self.GRID), previous_file_path=self._csv([prev[0]] + prev[1:2]))
        self.assertNotIn("flag_6_note", out)

    def test_csv_export_never_overwrites(self):
        path = self._csv(self.GRID)
        target = path + ".out.csv"
        self.addCleanup(lambda: os.path.exists(target) and os.remove(target))
        out = je.compute_jiaf_preliminary(path, export_csv_path=target)
        self.assertEqual(out["csv_written"], target)
        with open(target, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["preliminary_pin"], "300.0")
        self.assertIn("error", je.compute_jiaf_preliminary(path, export_csv_path=target))

    def test_bad_settings_and_files_are_errors(self):
        path = self._csv(self.GRID)
        self.assertIn("error", je.compute_jiaf_preliminary(path, f2_pct=-1))
        self.assertIn("error", je.compute_jiaf_preliminary(path, f4_subpopulation_sectors=["gbv"]))
        self.assertIn("error", je.compute_jiaf_preliminary("/nonexistent.xlsx"))


@unittest.skipUnless(os.environ.get("JIAF_YEMEN_DIR"), "set JIAF_YEMEN_DIR to the folder holding the Yemen workbooks")
class TestYemenLocal(unittest.TestCase):
    """The real supplied files (not committed): what the specification says they show."""

    def _p(self, suffix):
        d = os.environ["JIAF_YEMEN_DIR"]
        return os.path.join(d, next(f for f in os.listdir(d) if f.endswith(suffix)))

    def test_worksheet_reproduces_the_recorded_results(self):
        out = je.compute_jiaf_preliminary(self._p("jiaf_yemen_2026.xlsx"))
        sc = out["stored_comparison"]
        self.assertEqual((sc["severity_compared"], sc["severity_match"]), (333, 333))
        self.assertEqual(sc["final_pin_rank"], {"1": 305, "2": 11, "3": 17})
        self.assertAlmostEqual(sc["final_pin_total"], 22325198, delta=1)
        self.assertEqual(sorted(m["unit"] for m in sc["pin_mismatch"]), ["YE1920", "YE1928"])
        self.assertGreater(out["national_preliminary_pin"], sc["final_pin_total"])

    def test_published_hno_gives_the_same_severity_and_ranks(self):
        out = je.compute_jiaf_preliminary(self._p("yemen_jiaf_hnrp_2026.xlsx"), sheet_name="HNO 2026")
        sc = out["stored_comparison"]
        self.assertEqual((sc["severity_compared"], sc["severity_match"]), (333, 333))
        self.assertEqual(sc["final_pin_rank"], {"1": 305, "2": 11, "3": 17})


if __name__ == "__main__":
    unittest.main()
