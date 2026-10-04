# -*- coding: utf-8 -*-
"""The OCHA worksheet rules profile (`ocha_worksheet_2026`), offline: ties, zero denominators, all-zero and all-blank rows, exact threshold boundaries, the
worksheet's rounding and its 'severity above 2' PiN gate. Every expectation below is read off the formulas in OCHA's official Worksheet 3A/3B example/template
workbook (see the jiaf_rules docstring); tests/test_jiaf_worksheet_adapter.py checks the same rules against that workbook's cached values when it is available
locally. Cases that rest on formula text or Excel's comparison rules rather than on a cached example row are named `..._formula_text_only`."""
import unittest

from cartogen_ai.core.agent.tools import jiaf_engine as je
from cartogen_ai.core.agent.tools import jiaf_rules as jr

SEC = list(je.MAIN_SECTORS)  # cccm education nutrition food_security health protection shelter wash
S = je.merge_settings()


def vals(**kw):
    return {s: kw.get(s) for s in SEC}


def flags(v, pop=1000, old=None, **settings):
    return jr.pin_flags(v, pop, je.merge_settings(settings or None), old)[0]


class TestDefaultsAreTheTemplates(unittest.TestCase):
    def test_template_thresholds(self):
        self.assertEqual((S["f1_min_sectors"], S["f2_pct"], S["f3_pct"], S["f5_share"], S["f6_pct"], S["sectors_sev_5"], S["sectors_sev_4"]), (2, 0.3, 0.5, 0.9, 1.0, 2, 5))
        self.assertEqual(S["f4_subpopulation_sectors"], ("education",))
        self.assertEqual(S["rules_profile"], "ocha_worksheet_2026")

    def test_the_manual_reading_profile_is_not_the_default_and_keeps_its_own_settings(self):
        m = je.merge_settings({"rules_profile": "manual_reading"})
        self.assertEqual((m["f1_min_sectors"], m["s4_sector_count"]), (1, 4))
        self.assertNotIn("sectors_sev_5", m)
        with self.assertRaises(ValueError):
            je.merge_settings({"rules_profile": "nope"})
        with self.assertRaises(ValueError):
            je.merge_settings({"s4_sector_count": 4})  # a manual_reading setting is rejected under the worksheet profile


class TestRanksAreOfDistinctValues(unittest.TestCase):
    def test_distinct_ranks_with_ties_zeros_and_blanks(self):
        self.assertEqual(jr.distinct_ranks([100, 100, 50, None, 50, 0]), (100, 50, 0))
        self.assertEqual(jr.distinct_ranks([None, None]), (None, None, None))
        self.assertEqual(jr.distinct_ranks([7]), (7, None, None))
        self.assertEqual(jr.distinct_ranks([5, 5, 5]), (5, None, None))

    def test_a_tie_for_the_highest_makes_the_next_value_second_not_the_tied_sector(self):
        f, x = jr.pin_flags(vals(health=100, wash=100, shelter=40, nutrition=10), 1000, S, None)
        self.assertEqual((x["highest"], x["second"], x["third"]), (100, 40, 10))
        self.assertEqual(sorted(x["highest_sectors"]), ["health", "wash"])


class TestTies(unittest.TestCase):
    def test_a_tie_for_the_highest_suppresses_flags_2_and_3(self):
        f = flags(vals(health=130, wash=130, shelter=100, nutrition=50))
        for n in (2, 3):
            self.assertIs(f[n]["fired"], False)
            self.assertEqual(f[n]["status"], "suppressed_tie")
        self.assertAlmostEqual(f[2]["value"], 0.3)  # exactly at the threshold, yet not flagged: the percentage is still shown; only the flag is switched off

    def test_a_tie_for_the_highest_stops_flag_4_matching(self):
        f = flags(vals(education=500, wash=500, shelter=10))
        self.assertIs(f[4]["fired"], False)
        self.assertEqual(f[4]["status"], "suppressed_tie")
        self.assertTrue(flags(vals(education=500, wash=100))[4]["fired"])  # a single highest sector in the list fires

    def test_a_tie_below_the_top_does_not_suppress(self):
        f = flags(vals(wash=300, health=100, shelter=100, nutrition=50))
        self.assertTrue(f[2]["fired"])
        self.assertTrue(f[3]["fired"])


class TestZeroDenominatorsAndBlankRows(unittest.TestCase):
    def test_second_highest_of_zero_leaves_flag_2_blank_not_fired(self):
        f = flags(vals(wash=100, health=0, shelter=0))
        self.assertIsNone(f[2]["fired"])
        self.assertIsNone(f[3]["fired"])  # no distinct third value
        f = flags(vals(wash=100, health=0, shelter=0), )
        self.assertIsNone(f[2]["value"])

    def test_flag_2_blank_beats_the_tie_test(self):
        f = flags(vals(wash=100, health=100, shelter=0))  # tied top, 2nd highest = 0: the percentage column is blank first
        self.assertIsNone(f[2]["fired"])

    def test_flag_3_with_a_third_highest_of_zero_formula_text_only(self):
        # The worksheet tests the difference column for blank, not the percentage column, so with H3 = 0 the percentage is "" and Excel's text >= number is TRUE.
        f = flags(vals(wash=100, health=50, shelter=0))
        self.assertTrue(f[3]["fired"])
        self.assertEqual(f[3]["status"], "worksheet_text_comparison")
        self.assertTrue(f[2]["fired"])  # (100-50)/50 = 1.0
        # ...but not when the top is tied (the tie test comes first), and not when there is no zero cell at all.
        self.assertIs(flags(vals(wash=100, health=100, shelter=50, nutrition=0))[3]["fired"], False)
        self.assertIsNone(flags(vals(wash=100, health=50))[3]["fired"])

    def test_no_population_leaves_flag_5_blank(self):
        for pop in (None, 0):
            self.assertIsNone(flags(vals(wash=95), pop=pop)[5]["fired"])

    def test_all_zero_row(self):
        f = flags(vals(**{s: 0 for s in SEC}))
        self.assertIsNone(f[1]["fired"])  # the worksheet leaves flag 1 blank when the sectors sum to 0
        self.assertIsNone(f[2]["fired"])
        self.assertIsNone(f[3]["fired"])
        self.assertIsNone(f[4]["fired"])
        self.assertIs(f[5]["fired"], False)  # 0 / population = 0
        self.assertEqual(f[5]["value"], 0)

    def test_all_blank_row(self):
        f = flags(vals())
        self.assertTrue(all(f[n]["fired"] is None for n in range(1, 7)))

    def test_flag_1_counts_blank_and_zero_cells_apart_in_the_detail(self):
        f = flags(vals(wash=100, health=0, shelter=50))
        self.assertEqual(f[1]["value"], 6)  # 1 zero + 5 blank of the eight sectors
        self.assertEqual(f[1]["detail"]["zero_sectors"], ["health"])
        self.assertEqual(len(f[1]["detail"]["missing_sectors"]), 5)
        self.assertTrue(f[1]["fired"])


class TestExactThresholdBoundaries(unittest.TestCase):
    def test_flag_1_fires_at_exactly_the_threshold(self):
        base = {s: 10 for s in SEC}
        one = dict(base, cccm=0)
        two = dict(base, cccm=0, education=0)
        self.assertIs(flags(one)[1]["fired"], False)
        self.assertIs(flags(two)[1]["fired"], True)
        one_zero_one_blank = dict(base, cccm=0, education=None)
        self.assertIs(flags(one_zero_one_blank)[1]["fired"], True)  # a blank counts like a zero
        self.assertIs(flags(two, f1_min_sectors=3)[1]["fired"], False)

    def test_flag_2_at_exactly_30_percent_fires_and_just_below_does_not(self):
        self.assertTrue(flags(vals(wash=130, health=100))[2]["fired"])
        self.assertIs(flags(vals(wash=129.99, health=100))[2]["fired"], False)
        self.assertTrue(flags(vals(wash=140, health=100), f2_pct=0.4)[2]["fired"])
        self.assertIs(flags(vals(wash=139, health=100), f2_pct=0.4)[2]["fired"], False)

    def test_flag_3_at_exactly_50_percent_fires_and_just_below_does_not(self):
        self.assertTrue(flags(vals(wash=150, health=120, shelter=100))[3]["fired"])
        self.assertIs(flags(vals(wash=149, health=120, shelter=100))[3]["fired"], False)

    def test_flags_2_and_3_exceed_100_percent_because_they_are_relative_to_the_lower_value(self):
        f = flags(vals(wash=300, health=100, shelter=90))
        self.assertAlmostEqual(f[2]["value"], 2.0)
        self.assertAlmostEqual(f[3]["value"], 300 / 90 - 1)

    def test_flag_5_at_exactly_90_percent_fires_and_uses_the_unrounded_share(self):
        self.assertTrue(flags(vals(wash=90), pop=100)[5]["fired"])
        self.assertIs(flags(vals(wash=89.99), pop=100)[5]["fired"], False)
        self.assertIn("data error", flags(vals(wash=120), pop=100)[5]["note"])

    def test_flag_4_fires_for_a_single_highest_sub_population_sector_only(self):
        self.assertTrue(flags(vals(education=500, wash=100))[4]["fired"])
        self.assertIs(flags(vals(education=100, wash=500))[4]["fired"], False)
        self.assertTrue(flags(vals(nutrition=500, wash=100), f4_subpopulation_sectors=["nutrition"])[4]["fired"])
        self.assertIsNone(flags(vals(**{s: 0 for s in SEC}))[4]["fired"])  # highest PiN 0: blank

    def test_the_worksheets_rounding_is_half_away_from_zero_on_fifteen_digits(self):
        self.assertEqual(jr.excel_round(0.95), 1.0)
        self.assertEqual(jr.excel_round(0.25), 0.3)
        self.assertEqual(jr.excel_round(-0.95), -1.0)
        self.assertEqual(jr.excel_round(0.94), 0.9)
        self.assertEqual(jr.excel_round(0.9499999999999999), 1.0)  # beyond Excel's 15 significant digits this is 0.95

    def test_flag_6_boundary_uses_the_change_rounded_to_a_tenth(self):
        old = {"wash": 100}
        self.assertTrue(flags(vals(wash=200), old=old)[6]["fired"])  # exactly +100%
        self.assertTrue(flags(vals(wash=195), old=old)[6]["fired"])  # +95% rounds to +100%
        self.assertIs(flags(vals(wash=194), old=old)[6]["fired"], False)  # +94% rounds to +90%

    def test_flag_6_fires_on_a_decrease_too(self):
        # highest = health 50 (old 0 -> blank change, so use a case where the highest has an old value)
        f = flags(vals(wash=1, health=0), old={"wash": 100})
        self.assertTrue(f[6]["parts"]["highest"]["fired"])  # -99% rounds to -100%, ABS >= 1


class TestFlag6Parts(unittest.TestCase):
    def test_a_blank_change_makes_the_whole_part_blank_even_if_another_sector_fires(self):
        # two sectors tied for the highest; one has no previous-year value: the worksheet's array formula errors and the flag is blank
        f = flags(vals(wash=500, health=500, shelter=10), old={"wash": 100, "health": None})
        self.assertIsNone(f[6]["parts"]["highest"]["fired"])
        self.assertIsNone(f[6]["fired"])

    def test_old_zero_or_blank_gives_a_blank_change_never_infinite(self):
        self.assertEqual(jr.historical_changes({"wash": 10}, {"wash": 0}), {"wash": None})
        self.assertEqual(jr.historical_changes({"wash": 10}, {}), {"wash": None})
        self.assertEqual(jr.historical_changes({"wash": None}, {"wash": 5}), {"wash": None})

    def test_second_highest_part_counts_separately(self):
        f, x = jr.pin_flags(vals(wash=500, health=300), 10000, S, {"wash": 480, "health": 100})
        self.assertIs(f[6]["parts"]["highest"]["fired"], False)
        self.assertTrue(f[6]["parts"]["second_highest"]["fired"])  # 300 vs 100 = +200%
        self.assertEqual(x["worksheet_flag_count"], sum(1 for n, fl in f.items() if n != 6 and fl["fired"]) + 1)

    def test_a_unit_without_a_previous_year_row_is_blank(self):
        self.assertIsNone(flags(vals(wash=500), old=None)[6]["fired"])


class TestSeverityFlagsAndGate(unittest.TestCase):
    def sf(self, phases, prelim, outcomes=None, **settings):
        return jr.severity_flags(phases, prelim, outcomes or {}, je.merge_settings(settings or None))

    def test_flag_1_needs_sectors_sev_5_sectors_in_phase_5(self):
        self.assertIs(self.sf([5, 3, 3, 3], 3)[1]["fired"], False)
        self.assertIs(self.sf([5, 5, 3, 3], 3)[1]["fired"], True)
        self.assertIs(self.sf([5, 5, 3, 3], 3, sectors_sev_5=3)[1]["fired"], False)

    def test_flag_4_is_the_formula_not_the_header(self):
        # formula: preliminary 5 AND sectors in phases 1-4 >= sectors_sev_5; the header's "more than 4 sectors in 4 or worse, preliminary <= 4" is reported beside it
        f = self.sf([5, 5, 4, 4], 5)[4]
        self.assertTrue(f["fired"])
        self.assertEqual(f["value"], 2)
        self.assertIs(f["header_text_reading"], False)
        f = self.sf([5, 5, 5, 5, 4], 5)[4]
        self.assertIs(f["fired"], False)  # only one sector in phases 1-4
        f = self.sf([4, 4, 4, 4, 4, 1, 1, 1], 4)[4]
        self.assertIs(f["fired"], False)  # preliminary is not 5
        self.assertIs(f["header_text_reading"], True)  # but the header's wording would have flagged it

    def test_outcome_flag_2_is_two_phases_either_way(self):
        self.assertTrue(self.sf([3] * 4, 3, {"mortality": 5})[2]["fired"])
        self.assertTrue(self.sf([3] * 4, 3, {"mortality": 1})[2]["fired"])
        self.assertIs(self.sf([3] * 4, 3, {"mortality": 4, "malnutrition": 2})[2]["fired"], False)

    def test_outcome_flag_3_is_two_outcomes_one_or_more_away_in_the_same_direction(self):
        self.assertTrue(self.sf([3] * 4, 3, {"a": 2, "b": 2})[3]["fired"])
        self.assertTrue(self.sf([3] * 4, 3, {"a": 4, "b": 5})[3]["fired"])
        self.assertTrue(self.sf([3] * 4, 3, {"a": 1, "b": 2})[3]["fired"])  # 2+ below counts too: the worksheet counts <= prelim-1
        self.assertIs(self.sf([3] * 4, 3, {"a": 2, "b": 4})[3]["fired"], False)  # one each way
        self.assertIs(self.sf([3] * 4, 3, {"a": 2})[3]["fired"], False)

    def test_no_outcomes_is_not_assessable_not_a_pass(self):
        f = self.sf([3] * 4, 3, {})
        self.assertIsNone(f[2]["fired"])
        self.assertEqual(f[3]["status"], "not_assessable")

    def test_no_preliminary_severity_makes_flags_2_to_4_not_assessable(self):
        f = self.sf([3, 3], None, {"a": 5})
        self.assertTrue(all(f[n]["fired"] is None for n in (2, 3, 4)))

    def test_preliminary_pin_gate(self):
        self.assertEqual(jr.preliminary_pin(100, 3), 100)
        self.assertEqual(jr.preliminary_pin(100, 2), 0.0)
        self.assertEqual(jr.preliminary_pin(100, 1), 0.0)
        self.assertIsNone(jr.preliminary_pin(100, None))  # a missing severity is not passed through as "above 2"
        self.assertIsNone(jr.preliminary_pin(None, 4))


class TestEngineUsesTheProfile(unittest.TestCase):
    def unit(self, pin, sev, pop=None, code="U1"):
        from cartogen_ai.core.agent.tools import jiaf_inputs as ji
        u = ji._empty_unit(code, code, "A1", "A1", None)
        u["pin"], u["severity"], u["population"] = dict(pin), dict(sev), pop
        return u

    def test_a_severity_2_unit_gets_a_worksheet_preliminary_pin_of_zero_and_keeps_the_highest(self):
        u = self.unit({s: 100 for s in SEC}, {s: 2 for s in SEC})
        row = je.analyze([u])["rows"][0]
        self.assertEqual(row["preliminary_severity"], 2)
        self.assertEqual(row["preliminary_pin"], 100)  # the Mosaic highest PiN
        self.assertEqual(row["worksheet"]["preliminary_pin"], 0.0)  # OCHA's gate

    def test_incomplete_severity_coverage_has_no_worksheet_pin_but_shows_what_the_worksheet_would(self):
        u = self.unit({s: 100 for s in SEC}, {"wash": 3, "health": 3, "shelter": 3, "nutrition": 3})
        row = je.analyze([u])["rows"][0]
        self.assertIsNone(row["preliminary_severity"])
        self.assertIsNone(row["worksheet"]["preliminary_pin"])
        self.assertEqual(row["worksheet"]["severity_rule_value"], 3)
        self.assertEqual(row["worksheet"]["rule_preliminary_pin"], 100)
        self.assertIn("worksheet's rule value", row["worksheet"]["severity_flags_basis"])

    def test_workbook_thresholds_are_overridden_by_explicit_arguments_in_run_analysis_order(self):
        # analyze() takes the merged overrides; the precedence itself (explicit > workbook > template) is exercised in test_jiaf_worksheet_adapter
        a = je.analyze([self.unit({"wash": 100, "health": 70}, {})], overrides={"f2_pct": 0.5, "sectors_in_scope": ["wash", "health"]})
        self.assertIs(a["rows"][0]["pin_flags"][2]["fired"], False)  # 43% < 50%


if __name__ == "__main__":
    unittest.main()
