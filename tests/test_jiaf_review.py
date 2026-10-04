# -*- coding: utf-8 -*-
"""JIAF 2 stage 4: decision records, final figures, pattern outputs, offline. The project store and layer writes are covered by
tests/test_jiaf_review_live.py; the real Yemen files only when JIAF_YEMEN_DIR is set."""
import csv
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools import jiaf_engine as je
from cartogen_ai.core.agent.tools import jiaf_inputs as ji
from cartogen_ai.core.agent.tools import jiaf_patterns as jp
from cartogen_ai.core.agent.tools import jiaf_review as jr


def unit(code, pin=None, sev=None, pop=None, outcomes=None):
    u = ji._empty_unit(code, code, "A1", "A1", None)
    u["pin"], u["severity"], u["population"], u["outcomes"] = dict(pin or {}), dict(sev or {}), pop, outcomes or {}
    return u


def scope_of(units):
    """The sectors a toy file actually has: the tests state their scope explicitly (the default is all eight main sectors, so that a sector with no data is
    missing, never silently phase 1)."""
    return [s for s in je.MAIN_SECTORS if any(s in u["pin"] or s in u["severity"] for u in units)]


def run(units, decisions=None, bulk=(), overrides=None, previous=None):
    a = je.analyze(units, previous, {"sectors_in_scope": scope_of(units), **(overrides or {})})
    rows, summary = jr.finalize(units, a, decisions or {"pin": {}, "severity": {}}, bulk)
    return a, rows, summary


FLAGGED = dict(pin={"wash": 300, "health": 100, "shelter": 90, "nutrition": 80}, sev={"wash": 3, "health": 3, "shelter": 3, "nutrition": 3})
CALM = dict(pin={"wash": 100, "health": 95, "shelter": 90, "nutrition": 85}, sev={"wash": 2, "health": 2, "shelter": 2, "nutrition": 2})


class TestDecisionValidation(unittest.TestCase):
    def test_pin_decision_needs_unit_main_sector_and_rationale(self):
        clean, errors = jr.validate_pin_decisions([
            {"unit": "YE1", "sector": "Health", "rationale": "wash counts all affected", "decided_by": "session"},
            {"unit": "", "sector": "wash", "rationale": "x"}, {"unit": "YE2", "sector": "gbv", "rationale": "x"}, {"unit": "YE3", "sector": "wash"}])
        self.assertEqual(list(clean), ["YE1"])
        self.assertEqual(clean["YE1"]["sector"], "health")
        self.assertTrue(clean["YE1"]["date"])
        self.assertEqual(len(errors), 3)

    def test_severity_decision_needs_phase_basis_and_evidence(self):
        clean, errors = jr.validate_severity_decisions([
            {"unit": "YE1", "phase": 4, "evidence_basis": "outcome_indicators", "evidence": "CDR 1.2"},
            {"unit": "YE2", "phase": 6, "evidence_basis": "outcome_indicators", "evidence": "x"},
            {"unit": "YE3", "phase": 3, "evidence_basis": "gut_feeling", "evidence": "x"},
            {"unit": "YE4", "phase": 3, "evidence_basis": "proxy_indicators", "evidence": ""},
            {"unit": "YE5", "phase": 2.5, "evidence_basis": "expert_judgement", "evidence": "x"}])
        self.assertEqual(list(clean), ["YE1"])
        self.assertEqual(len(errors), 4)

    def test_population_group_makes_a_distinct_unit_id(self):
        self.assertEqual(jr.unit_id("YE1", "IDPs"), "YE1|IDPs")
        self.assertEqual(jr.unit_id("YE1"), "YE1")

    def test_store_functions_degrade_without_qgis(self):
        if not jr.QGIS_AVAILABLE:
            self.assertEqual(jr.load_decisions(), {"pin": {}, "severity": {}})
            self.assertIn("error", jr.record_jiaf_decisions([{"unit": "YE1", "sector": "wash", "rationale": "x"}]))


class TestFinalize(unittest.TestCase):
    def test_unflagged_unit_keeps_the_preliminary_figures(self):
        _a, rows, s = run([unit("U1", **CALM)])
        r = rows[0]
        self.assertEqual((r["final_pin"], r["final_pin_status"]), (100, "no_flag"))
        self.assertEqual(r["final_severity_status"], "preliminary_accepted")
        self.assertEqual(r["final_severity"], 2)
        self.assertFalse(s["provisional"])

    def test_flagged_without_a_decision_is_pending_and_provisional(self):
        _a, rows, s = run([unit("U1", **FLAGGED)])
        r = rows[0]
        self.assertEqual(r["final_pin_status"], "pending_flagged")
        self.assertEqual(r["final_pin"], 300)  # provisional: the highest
        self.assertTrue(s["provisional"])
        self.assertEqual(s["provisional_part_of_total"], 300)
        self.assertEqual(s["pending_pin_units"], 1)

    def test_a_decision_picks_the_chosen_sector_and_reports_its_rank(self):
        units = [unit("U1", **FLAGGED), unit("U2", **FLAGGED), unit("U3", **FLAGGED)]
        dec = {"pin": {"U1": {"sector": "health", "rationale": "r"}, "U2": {"sector": "shelter", "rationale": "r"}, "U3": {"sector": "wash", "rationale": "r"}},
               "severity": {}}
        _a, rows, s = run(units, dec)
        self.assertEqual([r["final_pin"] for r in rows], [100, 90, 300])
        self.assertEqual([r["final_pin_rank"] for r in rows], [2, 3, 1])
        self.assertEqual(s["chosen_sector_rank_counts"], {"2": 1, "3": 1, "1": 1})
        self.assertEqual(s["final_pin_total"], 490)
        self.assertFalse(s["provisional"])
        self.assertEqual(rows[0]["pin_decision_note"], "r")

    def test_a_decision_naming_a_sector_without_a_pin_is_ignored_and_reported(self):
        _a, rows, s = run([unit("U1", **FLAGGED)], {"pin": {"U1": {"sector": "education", "rationale": "r"}}, "severity": {}})
        self.assertEqual(rows[0]["final_pin_status"], "pending_flagged")
        self.assertTrue(any("no PiN" in i["problem"] for i in s["decision_issues"]))

    def test_decision_for_an_unknown_unit_is_reported(self):
        _a, _r, s = run([unit("U1", **CALM)], {"pin": {"NOPE": {"sector": "wash", "rationale": "r"}}, "severity": {"NOPE": {"phase": 3}}})
        self.assertEqual(len(s["decision_issues"]), 2)

    def test_bulk_accepting_flags_closes_only_units_with_nothing_else_fired(self):
        u1 = unit("U1", pin={"wash": 100, "health": 95, "shelter": 90, "nutrition": 0}, sev=CALM["sev"])  # only flag 1 (zero sector)
        u2 = unit("U2", **FLAGGED)  # flag 2 etc.
        _a, rows, s = run([u1, u2], bulk=[1])
        self.assertEqual(rows[0]["final_pin_status"], "flags_closed_in_bulk")
        self.assertEqual(rows[1]["final_pin_status"], "pending_flagged")
        self.assertEqual(s["bulk_accepted_flags"], [1])

    def test_severity_decision_and_pending_and_no_national_severity(self):
        flagged_sev = dict(pin=CALM["pin"], sev={"wash": 5, "health": 3, "shelter": 3, "nutrition": 3})  # severity flag 1: any sector in phase 5
        units = [unit("U1", **flagged_sev), unit("U2", **flagged_sev)]
        dec = {"pin": {}, "severity": {"U1": {"phase": 4, "evidence_basis": "outcome_indicators", "evidence": "CDR 1.2"}}}
        _a, rows, s = run(units, dec)
        self.assertEqual((rows[0]["final_severity"], rows[0]["final_severity_status"]), (4, "decided"))
        self.assertIn("CDR 1.2", rows[0]["severity_evidence"])
        self.assertEqual((rows[1]["final_severity"], rows[1]["final_severity_status"]), (None, "pending_flagged"))
        self.assertEqual(s["pending_severity_units"], 1)
        self.assertNotIn("national_severity", s)
        self.assertIn("U1", s["phase_5_units"])

    def test_the_total_is_a_sum_over_units_of_one_sector_each(self):
        _a, _r, s = run([unit("U1", **CALM), unit("U2", **CALM)])
        self.assertEqual(s["final_pin_total"], 200)


class TestCoverage(unittest.TestCase):
    """Incomplete sector coverage is never silently phase 1; 0 is not-applicable, not missing; missing inputs stay missing."""

    def test_the_four_published_examples(self):
        for phases, want in [([3, 3, 3, 3, 2, 1], 3), ([4, 4, 4, 4, 2, 1], 4), ([5, 5, 4, 4, 2, 1], 5), ([5, 4, 3, 2, 2, 1], 2)]:
            self.assertEqual(je.preliminary_severity(phases), want, phases)
        f = je.severity_flags(unit("U1"), [5, 4, 3, 2, 2, 1], 2, je.merge_settings())
        self.assertTrue(f[1]["fired"])  # a phase 5 sector in a unit classified 2 is flagged for review

    def test_too_few_reporting_sectors_is_not_phase_1(self):
        out = je.severity_with_coverage([4, 4, 4], 5)  # three sectors report phase 4, five report nothing
        self.assertIsNone(out["value"])
        self.assertEqual(out["status"], "incomplete_coverage")
        self.assertEqual((out["lower"], out["upper"]), (1, 5))

    def test_a_result_the_missing_sectors_cannot_change_is_determinate(self):
        out = je.severity_with_coverage([3, 3, 3, 3], 4)  # four more at 5 would make it phase 5? n5=4, n4=4 -> yes, so this is NOT determinate
        self.assertEqual(out["status"], "incomplete_coverage")
        out = je.severity_with_coverage([4, 4, 4, 4, 4, 4, 4], 1)  # one missing sector cannot turn phase 4 into 5 (needs two at 5)
        self.assertEqual((out["value"], out["status"]), (4, "determinate"))

    def test_nothing_reporting_is_no_data_and_zero_is_not_applicable_by_default(self):
        self.assertEqual(je.severity_with_coverage([], 0)["status"], "no_data")
        u = unit("U1", sev={"wash": 3, "health": 3, "shelter": 3, "nutrition": 3, "cccm": 0, "education": 0, "protection": 0, "food_security": 0})
        reporting, missing, na = je.severity_inputs(u, je.MAIN_SECTORS, "not_applicable")
        self.assertEqual((len(reporting), missing, len(na)), (4, [], 4))
        self.assertEqual(je.severity_with_coverage(reporting, len(missing))["value"], 3)
        reporting, missing, na = je.severity_inputs(u, je.MAIN_SECTORS, "missing")
        self.assertEqual((len(missing), na), (4, []))
        self.assertEqual(je.severity_with_coverage(reporting, len(missing))["status"], "incomplete_coverage")

    def test_default_scope_is_all_eight_sectors_so_a_four_sector_file_is_incomplete(self):
        u = unit("U1", sev={"wash": 3, "health": 3, "shelter": 3, "nutrition": 3}, pin={"wash": 10})
        row = je.analyze([u])["rows"][0]
        self.assertIsNone(row["preliminary_severity"])
        self.assertEqual(row["severity_coverage"]["status"], "incomplete_coverage")
        self.assertEqual(len(row["severity_coverage"]["missing_sectors"]), 4)
        narrowed = je.analyze([u], overrides={"sectors_in_scope": ["wash", "health", "shelter", "nutrition"]})["rows"][0]
        self.assertEqual(narrowed["preliminary_severity"], 3)

    def test_scope_and_zero_setting_are_validated(self):
        for bad in ({"sectors_in_scope": []}, {"sectors_in_scope": ["gbv"]}, {"zero_severity_as": "one"}):
            with self.assertRaises(ValueError):
                je.merge_settings(bad)

    def test_a_missing_sector_pin_marks_the_figure_as_a_lower_bound_and_is_counted(self):
        res = je.analyze([unit("U1", pin={"wash": 100})])
        row = res["rows"][0]
        self.assertEqual(row["preliminary_pin"], 100)
        self.assertTrue(row["pin_coverage"]["preliminary_pin_is_lower_bound"])
        self.assertEqual(res["totals"]["units_with_missing_pin_sector"], 1)
        full = je.analyze([unit("U1", pin={s: 5 for s in je.MAIN_SECTORS})])["rows"][0]
        self.assertFalse(full["pin_coverage"]["preliminary_pin_is_lower_bound"])

    def test_incomplete_coverage_needs_a_decision_and_is_kept_apart_from_the_other_fields(self):
        u = unit("U1", pin={"wash": 100}, sev={"wash": 4, "health": 4, "shelter": 4})
        a = je.analyze([u])
        rows, s = jr.finalize([u], a, {"pin": {}, "severity": {}})
        r = rows[0]
        self.assertEqual((r["preliminary_severity"], r["final_severity"], r["final_severity_status"]), (None, None, "incomplete_coverage"))
        self.assertEqual(s["incomplete_coverage_severity_units"], 1)
        dec = {"pin": {}, "severity": {"U1": {"phase": 4, "evidence_basis": "expert_judgement", "evidence": "partners confirm", "decided_by": "session", "date": "2026-10-04"}}}
        rows, _ = jr.finalize([u], a, dec)
        r = rows[0]
        self.assertEqual((r["preliminary_severity"], r["final_severity"], r["final_severity_status"]), (None, 4, "decided"))
        self.assertEqual((r["severity_evidence_basis"], r["severity_evidence"], r["severity_decided_by"], r["severity_decision_date"]),
                         ("expert_judgement", "partners confirm", "session", "2026-10-04"))
        csv_row = jr._csv_row(r)
        self.assertEqual((csv_row["preliminary_severity"], csv_row["severity_review_status"], csv_row["final_severity"]), (None, "decided", 4))


class TestMissingVersusZero(unittest.TestCase):
    """The 'missing or zero PiN' trigger of flag 1 is an UNVERIFIED interpretation. Missing and explicit zero stay distinct everywhere, and the team
    chooses whether the flag counts either or both."""

    def _flag1(self, pin, **settings):
        u = unit("U1", pin=pin)
        row = je.analyze([u], overrides={"sectors_in_scope": ["wash", "health", "shelter", "nutrition"], **settings})["rows"][0]
        return row, row["pin_flags"][1]

    def test_missing_and_zero_are_listed_apart(self):
        row, f = self._flag1({"wash": 100, "health": 0, "shelter": 50})  # nutrition absent, health explicitly zero
        self.assertEqual(f["detail"], {"missing_sectors": ["nutrition"], "zero_sectors": ["health"]})
        self.assertEqual(row["pin_coverage"]["missing_sectors"], ["nutrition"])
        self.assertEqual(row["pin_coverage"]["zero_sectors"], ["health"])
        self.assertEqual(f["value"], 2)

    def test_the_team_can_count_only_one_of_them(self):
        pin = {"wash": 100, "health": 0, "shelter": 50}
        self.assertEqual(self._flag1(pin, f1_count_zero=False)[1]["value"], 1)  # only the missing nutrition
        self.assertEqual(self._flag1(pin, f1_count_missing=False)[1]["value"], 1)  # only the explicit zero
        self.assertFalse(self._flag1(pin, f1_count_zero=False, f1_min_sectors=2)[1]["fired"])
        with self.assertRaises(ValueError):
            je.merge_settings({"f1_count_missing": False, "f1_count_zero": False})
        with self.assertRaises(ValueError):
            je.merge_settings({"f1_count_zero": "yes"})

    def test_partially_populated_inputs(self):
        _row, f = self._flag1({"wash": 100})  # three of four sectors have no figure
        self.assertEqual(set(f["detail"]["missing_sectors"]), {"health", "shelter", "nutrition"})
        self.assertEqual(f["detail"]["zero_sectors"], [])
        _row, f = self._flag1({s: 10 for s in ("wash", "health", "shelter", "nutrition")})
        self.assertFalse(f["fired"])
        self.assertEqual(f["detail"], {"missing_sectors": [], "zero_sectors": []})

    def test_an_explicit_zero_is_not_turned_into_missing_by_the_reader(self):
        units, _ = ji.parse_hxl_table([["#adm2 +code", "#inneed +wsh", "#inneed +hea"], ["YE1", 0, ""]])
        ji.validate_units(units)
        self.assertEqual(units[0]["pin"]["wash"], 0.0)
        self.assertIsNone(units[0]["pin"]["health"])

    def test_the_csv_and_rows_carry_both_lists(self):
        u = unit("U1", pin={"wash": 100, "health": 0}, sev={"wash": 3})
        a = je.analyze([u], overrides={"sectors_in_scope": ["wash", "health", "nutrition"]})
        rows, _ = jr.finalize([u], a, {"pin": {}, "severity": {}})
        csv_row = jr._csv_row(rows[0])
        self.assertEqual((csv_row["pin_missing_sectors"], csv_row["pin_zero_sectors"]), ("nutrition", "health"))
        self.assertEqual(je._row_for_csv(a["rows"][0])["pin_zero_sectors"], "health")


class TestBulkClosureAndBlockers(unittest.TestCase):
    def test_bulk_closure_is_recorded_against_every_unit_it_closes(self):
        u = unit("U1", pin={"wash": 100, "health": 95, "shelter": 90, "nutrition": 0}, sev=CALM["sev"])
        a = je.analyze([u], overrides={"sectors_in_scope": scope_of([u])})
        info = {"rationale": "no camps in these districts", "decided_by": "analysis group", "date": "2026-10-12"}
        rows, s = jr.finalize([u], a, {"pin": {}, "severity": {}}, (1,), info)
        r = rows[0]
        self.assertEqual(r["final_pin_status"], "flags_closed_in_bulk")
        self.assertEqual((r["pin_decision_note"], r["pin_decided_by"], r["pin_decision_date"]), ("no camps in these districts", "analysis group", "2026-10-12"))
        self.assertEqual(s["bulk_closure"]["units_closed"], 1)
        self.assertIsNone(run([unit("U2", **CALM)])[2]["bulk_closure"])

    def test_every_jiaf_result_carries_both_open_blockers(self):
        b = ji.VALIDATION_BLOCKERS
        self.assertEqual([x["id"] for x in b["blockers"]], ["flag_formulas", "annex4_reader"])
        self.assertTrue(all(x["status"] == "open" and x["closes_when"] for x in b["blockers"]))
        self.assertIn("faithful or complete", b["claim"])
        self.assertIn("screenshots", b["blockers"][1]["text"])
        self.assertIn("unverified", b["blockers"][1]["text"])
        self.assertIn("different layout", b["blockers"][1]["text"])
        self.assertIn("does not by itself show", b["blockers"][0]["text"])
        grid = TestTools.GRID
        import tempfile as _t
        fd, path = _t.mkstemp(suffix=".csv")
        os.close(fd)
        self.addCleanup(os.remove, path)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(grid)
        for out in (ji.import_jiaf_inputs(path), je.compute_jiaf_preliminary(path), jr.finalize_jiaf_results(path), jp.compute_jiaf_patterns(path)):
            self.assertTrue(out["success"], out)
            self.assertEqual(out["validation_blockers"], b)


class TestPatterns(unittest.TestCase):
    def _pat(self, units, **kw):
        a, rows, _ = run(units)
        return jp.patterns(units, a, rows, **kw)

    def test_pearson(self):
        self.assertAlmostEqual(jp.pearson([1, 2, 3, 4], [2, 4, 6, 8]), 1.0)
        self.assertAlmostEqual(jp.pearson([1, 2, 3], [3, 2, 1]), -1.0)
        self.assertIsNone(jp.pearson([1, 1, 1], [1, 2, 3]))
        self.assertIsNone(jp.pearson([1, 2], [1, 2]))
        self.assertIsNone(jp.pearson([1, None, 3, 4], [1, 2, None, None]))

    def test_threshold_validation(self):
        for bad in ({"nope": 1}, {"sector_population_share": 0}, {"severe_phases": [6]}, {"top_units": 0}):
            with self.assertRaises(ValueError):
                jp.merge_thresholds(bad)
        self.assertEqual(jp.merge_thresholds({"severe_phases": [5]})["severe_phases"], (5,))

    def test_q1_to_q3_and_the_manual_defaults(self):
        units = [unit("A", pin={"wash": 600, "health": 100}, pop=1000, sev={"wash": 4, "health": 2}),
                 unit("B", pin={"wash": 50, "health": 450}, pop=500, sev={"wash": 1, "health": 4})]
        out = self._pat(units)
        top = out["q1_highest_pin"]["top_units"]
        self.assertEqual([t["unit"] for t in top], ["A", "B"])
        self.assertTrue(top[0]["high_absolute_and_high_share"])
        self.assertEqual(out["q3_sector_pin"]["national_pin_by_sector"], {"health": 550, "wash": 650})
        self.assertIn("NOT added", out["q3_sector_pin"]["note_on_sums"])
        self.assertEqual(out["q3_sector_pin"]["units_where_sector_is_highest"], {"health": 1, "wash": 1})
        self.assertEqual(out["thresholds"]["correlation_threshold"], 0.7)
        self.assertEqual(out["thresholds"]["sector_population_share"], 0.4)

    def test_q2_counts_sectors_above_the_share(self):
        units = [unit("A", pin={"wash": 450, "health": 420, "shelter": 410, "nutrition": 5}, pop=1000)]
        out = self._pat(units)
        self.assertEqual(out["q2_sectors_above_share"]["count_of_such_units"], 1)
        self.assertEqual(self._pat(units, thresholds={"sector_population_share": 0.5})["q2_sectors_above_share"]["count_of_such_units"], 0)

    def test_no_population_means_not_evaluable_not_zero(self):
        out = self._pat([unit("A", pin={"wash": 5, "health": 4})])
        self.assertIn("No population", out["q1_highest_pin"]["note"])
        self.assertEqual(out["q2_sectors_above_share"]["count_of_such_units"], 0)
        self.assertIn("No population", out["q2_sectors_above_share"]["note"])

    def test_q6_to_q9_severity(self):
        sev = {"wash": 4, "health": 4, "shelter": 4, "nutrition": 5, "education": 4}
        pin = {s: 450 for s in sev}
        units = [unit("A", pin=pin, sev=sev, pop=1000), unit("B", pin={"wash": 1, "health": 1}, sev={"wash": 2, "health": 1}, pop=1000)]
        out = self._pat(units)
        self.assertEqual(out["q6_severity"]["units_with_many_sectors_in_phase_4_or_5"], [{"unit": "A", "sectors": 5}])
        self.assertEqual(out["q7_sectors_in_phase_4_or_5"]["distribution_of_units"], {"0": 1, "5": 1})
        self.assertEqual(out["q8_sector_severity_distribution"]["wash"], {"2": 1, "4": 1})
        self.assertEqual(out["q9_high_pin_and_high_severity"]["count_of_such_units"], 1)
        self.assertEqual(out["q6_severity"]["note"], "There is no national severity; this is per unit.")

    def test_q4_trend_needs_a_previous_year_and_uses_the_same_basis(self):
        cur = [unit("A", pin={"wash": 300, "health": 10})]
        prev = [unit("A", pin={"wash": 100, "health": 90})]
        a, rows, _ = run(cur)
        out = jp.patterns(cur, a, rows)
        self.assertIn("not computed", out["q4_trend"]["note"])
        out = jp.patterns(cur, a, rows, previous_analysis=je.analyze(prev))
        self.assertEqual(out["q4_trend"]["largest_increases"][0]["change"], 200)
        self.assertIn("not the Final PiN", out["q4_trend"]["basis"])

    def test_q5_never_assumes_shares(self):
        out = self._pat([unit("A", pin={"wash": 100, "health": 10})])
        self.assertIn("group_shares", out["q5_group_estimates"]["note"])
        a, rows, _ = run([unit("A", pin={"wash": 100})])
        out = jp.patterns([unit("A", pin={"wash": 100})], a, rows, group_shares={"girls": 0.3})
        self.assertEqual(out["q5_group_estimates"]["estimates"], {"girls": 30.0})
        self.assertIn("not any difference in its needs", out["q5_group_estimates"]["caveat"])

    def test_q10_correlated_sectors_are_listed(self):
        units = [unit(f"U{i}", pin={"wash": i * 10, "health": i * 20 + 1, "shelter": 5 + (i % 2) * 100}) for i in range(1, 8)]
        pairs = self._pat(units)["q10_pin_correlation"]["pairs_above_threshold"]
        self.assertEqual(pairs[0]["sectors"], ["health", "wash"])


class TestTools(unittest.TestCase):
    GRID = [
        ["#adm2 +code", "#adm2 +name", "#inneed", "#severity", "#inneed +wsh", "#severity +wsh", "#inneed +shl", "#severity +shl",
         "#inneed +hea", "#severity +hea", "#inneed +nut", "#severity +nut"],
        ["YE1", "A", 300, 3, 100, 3, 300, 3, 200, 3, 50, 3],
        ["YE2", "B", 120, 2, 120, 2, 90, 2, 110, 2, 80, 2],
    ]

    def _csv(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(self.GRID)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_finalize_tool_reports_provisional_and_exports_csv_once(self):
        path = self._csv()
        target = path + ".final.csv"
        self.addCleanup(lambda: os.path.exists(target) and os.remove(target))
        scope = ["nutrition", "health", "shelter", "wash"]
        out = jr.finalize_jiaf_results(path, sectors_in_scope=scope, export_csv_path=target)
        self.assertTrue(out["success"], out)
        self.assertIn("not endorsed", out["statement"])
        self.assertTrue(out["provisional"])
        self.assertIn("PROVISIONAL", out["total_note"])
        self.assertIn("no national severity", out["severity_note"])
        with open(target, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["pin_review_status"], "pending_flagged")
        for col in ("preliminary_pin", "pin_review_status", "final_pin", "pin_justification", "pin_decided_by", "preliminary_severity",
                    "severity_coverage_status", "severity_review_status", "final_severity", "severity_justification", "evidence_and_comments"):
            self.assertIn(col, rows[0])  # preliminary result, review status, final result and justification are separate columns
        self.assertIn("error", jr.finalize_jiaf_results(path, export_csv_path=target))
        self.assertIn("error", jr.finalize_jiaf_results(path, bulk_accepted_flags=[9]))
        self.assertIn("bulk_rationale", jr.finalize_jiaf_results(path, sectors_in_scope=scope, bulk_accepted_flags=[1])["error"])
        closed = jr.finalize_jiaf_results(path, sectors_in_scope=scope, bulk_accepted_flags=[1, 2, 3, 4, 5, 6],
                                          bulk_rationale="analysis group agreed these flags are expected here", bulk_decided_by="session 1")
        self.assertFalse(closed["provisional"])
        self.assertEqual(closed["bulk_closure"]["rationale"], "analysis group agreed these flags are expected here")
        self.assertEqual(closed["bulk_closure"]["units_closed"], closed["pin_status_counts"]["flags_closed_in_bulk"])
        self.assertGreaterEqual(closed["bulk_closure"]["units_closed"], 1)  # only a flagged unit has anything to close
        self.assertIn("validation_blockers", closed)

    def test_patterns_tool(self):
        out = jp.compute_jiaf_patterns(self._csv(), sectors_in_scope=["nutrition", "health", "shelter", "wash"], high_pin_share=0.5)
        self.assertTrue(out["success"], out)
        self.assertEqual(out["thresholds"]["high_pin_share"], 0.5)
        self.assertIn("q10_pin_correlation", out)
        self.assertIn("error", jp.compute_jiaf_patterns(self._csv(), correlation_threshold="x"))
        self.assertIn("error", jp.compute_jiaf_patterns(self._csv(), sectors_in_scope=["gbv"]))
        self.assertIn("error", jp.compute_jiaf_patterns(self._csv(), group_shares={"girls": 1.5}))


@unittest.skipUnless(os.environ.get("JIAF_YEMEN_DIR"), "set JIAF_YEMEN_DIR to the folder holding the Yemen workbooks")
class TestYemenLocal(unittest.TestCase):
    def test_the_recorded_choices_reproduce_the_published_final_pin(self):
        d = os.environ["JIAF_YEMEN_DIR"]
        path = os.path.join(d, next(f for f in os.listdir(d) if f.endswith("jiaf_yemen_2026.xlsx")))
        run_ = je.run_analysis(path)
        units, analysis = run_["units"], run_["analysis"]
        expected = analysis["expected_sectors"]
        decisions = {"pin": {}, "severity": {}}
        for u in units:
            ranked = je.ranked_pins(u, expected)
            stored = float(u["stored"]["final_pin"])
            rank = je.rank_of_value(ranked, stored)
            if rank != 1:
                sector = next(s for s, v in ranked if abs(v - stored) < 1)
                decisions["pin"][jr.unit_id(u["admin2_code"])] = {"sector": sector, "rationale": "recorded in the supplied worksheet"}
        _rows, summary = jr.finalize(units, analysis, decisions, bulk_accepted_flags=[1, 2, 3, 4, 5, 6])
        self.assertAlmostEqual(summary["final_pin_total"], 22325198, delta=1)
        self.assertEqual(summary["chosen_sector_rank_counts"], {"2": 11, "3": 17})
        self.assertFalse(summary["provisional"])
        self.assertEqual(sum(summary["final_severity_distribution"].values()) + summary["pending_severity_units"], 333)


if __name__ == "__main__":
    unittest.main()
