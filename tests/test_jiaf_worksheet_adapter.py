# -*- coding: utf-8 -*-
"""The OCHA Worksheet 3A/3B adapter: table-aware reading, header-matched columns, unit identity (population group + pocket of need + Admin 3/2/1 P-code),
the worksheet's own flag columns, its `Thresholds` named cells and its historical table.

The grid-level tests always run. The workbook tests need openpyxl (skipped otherwise). The golden test runs only when JIAF_OCHA_DIR points at the folder holding
OCHA's official `Worksheet_3A_3B_PiNSev_Example.xlsx`: that file is NOT committed (its licence is unknown), so CI never sees it; it was run locally and every
cached PiN flag, severity flag, preliminary severity and preliminary PiN of its 6 units is reproduced."""
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools import jiaf_engine as je
from cartogen_ai.core.agent.tools import jiaf_inputs as ji

SECTOR_HEADERS = ["CCCM", "Education", "Nutrition", "Food Security", "Health", "Overarching Protection", "Shelter", "WASH"]
PIN_FLAG_HEADERS = ["Number of missing / zero PiNs greater than threshold - Data quality", "Highest PiN greater than 90% of total affected population",
                    "Highest sector targets sub-population group(s)", "% difference is over a specified threshold between Highest and 2nd Highest",
                    "% difference is over a specified threshold between Highest and 3rd Highest",
                    "Change from last year for the highest sector(s) has significantly increased or decreased",
                    "Change from last year for the 2nd highest sector(s) has significantly increased or decreased"]
LOC = ["Admin 1", "Admin 1 P-Code", "Admin 2", "Admin 2 P-Code", "Admin 3", "Admin 3 P-Code", "Pocket of need", "Population", "Population Group"]


def pin_grid(rows, flags=True):
    head = ["ID"] + LOC + SECTOR_HEADERS + (PIN_FLAG_HEADERS if flags else []) + ["Severity", "Preliminary PiN", "# Flags", "Final PiN"]
    return [head] + rows


def row(admin2="HT0311", pocket=None, group=None, a3=None, pop=1000, pins=None, flag_cells=None, n_flags=None, prelim=None):
    pins = pins or {}
    cells = ["", "Nord", "HT03", "Cap", admin2, None, a3, pocket, pop, group] + [pins.get(h) for h in SECTOR_HEADERS]
    cells += list(flag_cells or [None] * len(PIN_FLAG_HEADERS))
    return cells + [None, prelim, n_flags, None]


def sev_grid(rows):
    head = ["ID"] + LOC + SECTOR_HEADERS + ["Preliminary Intersectoral Severity based on overlap of sectoral deprivations", "Mortality", "Malnutrition",
                                            "1 sectors in severity phase 5 [modify the threshold]", "2+ phase variation between preliminary severity and severity of any of the outcome indicators",
                                            "# Flags", "Final Severity"]
    return [head] + rows


def srow(admin2="HT0311", pocket=None, group=None, a3=None, phases=None, prelim=None, mort=None, flag1=None):
    phases = phases or {}
    return (["", "Nord", "HT03", "Cap", admin2, None, a3, pocket, 1000, group] + [phases.get(h) for h in SECTOR_HEADERS] + [prelim, mort, None, flag1, None, None, prelim])


class TestIdentity(unittest.TestCase):
    def test_worksheet_id_rule(self):
        self.assertEqual(ji.worksheet_id(None, None, None, "HT0311", "HT03"), "HT0311")
        self.assertEqual(ji.worksheet_id(None, "IDP camp", None, "HT0311", "HT03"), "IDP campHT0311")
        self.assertEqual(ji.worksheet_id("IDPs", None, "HT031101", "HT0311", "HT03"), "IDPsHT031101")  # Admin 3 wins over Admin 2
        self.assertEqual(ji.worksheet_id(None, None, None, None, "HT03"), "HT03")

    def test_a_pocket_of_need_in_the_same_admin2_is_a_separate_unit(self):
        pins = {h: 10 for h in SECTOR_HEADERS}
        units, _ = ji.parse_ocha_worksheet(pin_grid([row(pins=pins), row(pocket="IDP camp", pins=pins), row(group="IDPs", pins=pins)]), sev_grid([]))
        self.assertEqual(len(units), 3)
        self.assertEqual(sorted(ji.uid(u) for u in units), sorted(["IDP campHT0311", "HT0311", "IDPsHT0311"]))
        camp = next(u for u in units if u["pocket_of_need"] == "IDP camp")
        self.assertEqual(camp["admin2_code"], "HT0311")

    def test_pin_and_severity_rows_of_the_same_unit_are_merged_including_the_pocket(self):
        pins = {h: 10 for h in SECTOR_HEADERS}
        phases = {h: 3 for h in SECTOR_HEADERS}
        units, _ = ji.parse_ocha_worksheet(pin_grid([row(pins=pins), row(pocket="IDP camp", pins=pins)]),
                                           sev_grid([srow(phases=phases, prelim=3), srow(pocket="IDP camp", phases=dict(phases, WASH=5), prelim=3)]))
        self.assertEqual(len(units), 2)
        camp = next(u for u in units if u["pocket_of_need"] == "IDP camp")
        self.assertEqual(camp["severity"]["wash"], 5)
        main = next(u for u in units if not u["pocket_of_need"])
        self.assertEqual(main["severity"]["wash"], 3)

    def test_admin3_rows_are_distinct_units_under_one_admin2(self):
        pins = {h: 10 for h in SECTOR_HEADERS}
        units, _ = ji.parse_ocha_worksheet(pin_grid([row(a3="HT031101", pins=pins), row(a3="HT031102", pins=pins)]), sev_grid([]))
        self.assertEqual(sorted(ji.uid(u) for u in units), ["HT031101", "HT031102"])


class TestColumnsByHeaderText(unittest.TestCase):
    def test_reordered_and_extra_columns_are_still_read(self):
        grid = pin_grid([row(pins={"WASH": 7, "Health": 9}, pop=500)])
        # shuffle: move the WASH column to the front, add an unknown column, and put a title row above the headers
        head, body = grid[0], grid[1]
        i = head.index("WASH")
        head2 = [head[i], "Notes"] + head[:i] + head[i + 1:]
        body2 = [body[i], "x"] + body[:i] + body[i + 1:]
        units, _ = ji.parse_ocha_worksheet([["Title row"], head2, body2], sev_grid([]))
        self.assertEqual(units[0]["pin"]["wash"], 7)
        self.assertEqual(units[0]["pin"]["health"], 9)
        self.assertEqual(units[0]["population"], 500)

    def test_the_worksheets_own_flag_columns_are_kept_by_header_text(self):
        cells = ["Flagged", "", "", "Flagged", "", "Flagged", ""]
        units, _ = ji.parse_ocha_worksheet(pin_grid([row(pins={"WASH": 5}, flag_cells=cells, n_flags=3)]), sev_grid([srow(phases={"WASH": 3}, prelim=3, flag1="Flagged")]))
        u = units[0]
        self.assertEqual(u["stored"]["pin_flags"], {1: True, 5: False, 4: False, 2: True, 3: False, "6a": True, "6b": False})
        self.assertEqual(u["stored"]["pin_flag_count"], 3)
        self.assertEqual(u["stored"]["severity_flags"], {1: True, 2: False})

    def test_a_sheet_without_flag_columns_has_no_stored_flags(self):
        units, _ = ji.parse_ocha_worksheet(pin_grid([row(pins={"WASH": 5})], flags=False), sev_grid([]))
        self.assertNotIn("pin_flags", units[0]["stored"])


class TestHistoryAndThresholds(unittest.TestCase):
    def hist(self, rows):
        head = ["ID"] + LOC + [f"{h} - old" for h in SECTOR_HEADERS]
        return [head] + rows

    def test_previous_pin_is_attached_by_worksheet_id_including_pocket_and_a_unit_without_a_row_stays_none(self):
        pins = {h: 10 for h in SECTOR_HEADERS}
        units, _ = ji.parse_ocha_worksheet(pin_grid([row(pins=pins), row(pocket="IDP camp", pins=pins), row(admin2="HT0312", pins=pins)]), sev_grid([]))
        old_main = ["", "Nord", "HT03", "Cap", "HT0311", None, None, None, 1000, None] + [100] * 8
        old_camp = ["", "Nord", "HT03", "Cap", "HT0311", None, None, "IDP camp", 1000, None] + [50] * 8
        notes = ji.parse_ocha_history(units, self.hist([old_main, old_camp, [None] * 18]))
        by = {ji.uid(u): u for u in units}
        self.assertEqual(by["HT0311"]["previous_pin"]["wash"], 100)
        self.assertEqual(by["IDP campHT0311"]["previous_pin"]["wash"], 50)
        self.assertIsNone(by["HT0312"]["previous_pin"])
        self.assertIn("2 matched", notes[0])

    def test_named_threshold_cells_and_the_sub_population_list(self):
        wbt = {"names": {"zero_pin_thresh": 3, "perc_1st_2nd": 0.25, "flag_pin_perc": "0.8", "sectors_sev_5": 3, "flag_pin_historical": None},
               "tables": {"tblSubSectorPopulation": {"grid": [["Sector", "Proportion"], ["Education", 0.3], ["Nutrition", None], ["Moon base", None]]}}}
        found, notes = ji.worksheet_thresholds(wbt)
        self.assertEqual(found["f1_min_sectors"], 3)
        self.assertEqual(found["f2_pct"], 0.25)
        self.assertEqual(found["f5_share"], 0.8)
        self.assertEqual(found["sectors_sev_5"], 3)
        self.assertNotIn("f6_pct", found)  # a blank named cell is not a threshold
        self.assertEqual(found["f4_subpopulation_sectors"], ("education", "nutrition"))
        self.assertTrue(any("Moon base" in n for n in notes))

    def test_an_empty_sub_population_table_means_flag_4_has_no_sectors(self):
        found, _ = ji.worksheet_thresholds({"names": {}, "tables": {"tblSubSectorPopulation": {"grid": [["Sector", "Proportion"], [None, None]]}}})
        self.assertEqual(found["f4_subpopulation_sectors"], ())

    def test_no_thresholds_at_all_says_so(self):
        found, notes = ji.worksheet_thresholds({"names": {}, "tables": {}})
        self.assertEqual(found, {})
        self.assertIn("template defaults", notes[0])


def _openpyxl():
    try:
        import openpyxl  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_openpyxl(), "openpyxl not installed")
class TestWorkbookRead(unittest.TestCase):
    def _book(self, with_thresholds=True):
        import openpyxl
        from openpyxl.workbook.defined_name import DefinedName
        from openpyxl.worksheet.table import Table
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "WS - 3.1 Overall PiN"
        pins = {h: 100 for h in SECTOR_HEADERS}
        pins["CCCM"] = 0
        pins["Education"] = 0
        grid = pin_grid([row(pins=pins, pop=1000), row(pocket="IDP camp", pins=pins, pop=1000)], flags=False)
        grid = [["A title row above the table"]] + grid  # the table does not start at A1
        for r in grid:
            ws.append(r)
        ws.add_table(Table(displayName="tblPiNAnalysis", ref=f"A2:{openpyxl.utils.get_column_letter(len(grid[1]))}{len(grid)}"))
        sv = wb.create_sheet("WS - 3.2 Intersectoral Severity")
        sg = sev_grid([srow(phases={h: 3 for h in SECTOR_HEADERS}, prelim=3), srow(pocket="IDP camp", phases={h: 3 for h in SECTOR_HEADERS}, prelim=3)])
        for r in sg:
            sv.append(r)
        sv.add_table(Table(displayName="tblSeverityAnalysis", ref=f"A1:{openpyxl.utils.get_column_letter(len(sg[0]))}{len(sg)}"))
        if with_thresholds:
            th = wb.create_sheet("Thresholds")
            th["D8"] = 3
            th["D9"] = 0.3
            th["A19"], th["B19"] = "x", "Sector"
            th["B20"] = "Nutrition"
            th.add_table(Table(displayName="tblSubSectorPopulation", ref="B19:B20"))
            wb.defined_names["zero_pin_thresh"] = DefinedName("zero_pin_thresh", attr_text="Thresholds!$D$8")
            wb.defined_names["perc_1st_2nd"] = DefinedName("perc_1st_2nd", attr_text="Thresholds!$D$9")
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        wb.save(path)
        self.addCleanup(os.remove, path)
        return path

    def test_table_aware_read_with_workbook_thresholds(self):
        run = je.run_analysis(self._book())
        self.assertNotIn("error", run, run)
        self.assertTrue(any("tblPiNAnalysis (A2:" in n for n in run["notes"]), run["notes"])
        a = run["analysis"]
        self.assertEqual(len(a["rows"]), 2)
        self.assertEqual(sorted(r["unit_id"] for r in a["rows"]), ["HT0311", "IDP campHT0311"])
        self.assertEqual(a["settings"]["f1_min_sectors"], 3)
        self.assertEqual(a["settings"]["f4_subpopulation_sectors"], ("nutrition",))
        self.assertEqual(a["threshold_sources"]["f1_min_sectors"], "workbook Thresholds sheet")
        self.assertEqual(a["threshold_sources"]["f5_share"], "template default")
        self.assertIs(a["rows"][0]["pin_flags"][1]["fired"], False)  # two zero sectors < the workbook's threshold of 3

    def test_an_explicit_argument_beats_the_workbook(self):
        run = je.run_analysis(self._book(), overrides={"f1_min_sectors": 2})
        a = run["analysis"]
        self.assertEqual(a["settings"]["f1_min_sectors"], 2)
        self.assertEqual(a["threshold_sources"]["f1_min_sectors"], "explicit argument")
        self.assertIs(a["rows"][0]["pin_flags"][1]["fired"], True)

    def test_without_a_thresholds_sheet_the_template_defaults_are_used_and_the_note_says_so(self):
        run = je.run_analysis(self._book(with_thresholds=False))
        self.assertEqual(run["analysis"]["settings"]["f1_min_sectors"], 2)
        self.assertEqual(set(run["analysis"]["threshold_sources"].values()), {"template default"})
        self.assertTrue(any("template defaults" in n for n in run["notes"]))

    def test_the_manual_reading_profile_ignores_the_workbooks_thresholds(self):
        run = je.run_analysis(self._book(), overrides={"rules_profile": "manual_reading"})
        self.assertEqual(run["analysis"]["settings"]["f1_min_sectors"], 1)


@unittest.skipUnless(os.environ.get("JIAF_OCHA_DIR"), "set JIAF_OCHA_DIR to the folder holding OCHA's Worksheet_3A_3B_PiNSev_Example.xlsx")
@unittest.skipUnless(_openpyxl(), "openpyxl not installed")
class TestOfficialExampleGolden(unittest.TestCase):
    """OCHA's own example workbook (6 units incl. an 'IDP camp' pocket of need): every flag column, the preliminary severity and the preliminary PiN that Excel
    cached in the file must be reproduced by the rules profile."""

    @classmethod
    def setUpClass(cls):
        d = os.environ["JIAF_OCHA_DIR"]
        cls.path = os.path.join(d, next(f for f in os.listdir(d) if f.endswith("Example.xlsx")))
        cls.loaded = je.run_analysis(cls.path)
        cls.a = cls.loaded["analysis"]

    def test_read_from_the_tables_with_the_workbooks_thresholds(self):
        self.assertEqual(len(self.a["rows"]), 6)
        self.assertTrue(any("tblPiNAnalysis" in n for n in self.loaded["notes"]))
        self.assertEqual({k: v for k, v in self.a["settings"].items() if k.startswith(("f", "sectors_sev"))},
                         {"f1_min_sectors": 2, "f2_pct": 0.3, "f3_pct": 0.5, "f5_share": 0.9, "f6_pct": 1.0, "sectors_sev_5": 2, "sectors_sev_4": 5,
                          "f4_subpopulation_sectors": ("education",)})
        self.assertIn("IDP campHT0311", [r["unit_id"] for r in self.a["rows"]])  # the pocket of need is its own unit

    def test_every_cached_flag_column_is_reproduced(self):
        fc = self.a["flag_check_against_file"]
        self.assertEqual(set(fc["pin"]), {"1", "2", "3", "4", "5", "6a", "6b"})
        self.assertEqual(set(fc["severity"]), {"1", "2", "3", "4"})
        for kind in ("pin", "severity"):
            for n, c in fc[kind].items():
                self.assertEqual((c["compared"], c["agree"], c["disagree"]), (6, 6, []), (kind, n))

    def test_cached_preliminary_pin_severity_and_flag_counts(self):
        sc = self.a["stored_comparison"]
        self.assertEqual((sc["pin_compared"], sc["pin_match"], sc["pin_mismatch"]), (6, 6, []))
        self.assertEqual((sc["severity_compared"], sc["severity_match"]), (5, 5))  # the sixth has incomplete coverage: no silent phase 1
        counts = {r["admin2_code"] + (r["pocket_of_need"] or ""): r["worksheet"]["flag_count"] for r in self.a["rows"]}
        self.assertEqual(counts, {"HT0311": 2, "HT0312": 2, "HT0313": 0, "HT0321": 1, "HT0322": 2, "HT0311IDP camp": 1})

    def test_the_tied_pocket_of_need_row_suppresses_flags_2_and_3_at_exactly_30_percent(self):
        camp = next(r for r in self.a["rows"] if r["pocket_of_need"] == "IDP camp")
        self.assertEqual(camp["pin_flags"][2]["status"], "suppressed_tie")
        self.assertAlmostEqual(camp["pin_flags"][2]["value"], 0.3)
        self.assertTrue(camp["pin_flags"][5]["fired"])  # highest = 100% of the population

    def test_the_incomplete_coverage_unit_gets_no_preliminary_severity_but_the_worksheets_rule_value(self):
        u = next(r for r in self.a["rows"] if r["admin2_code"] == "HT0322")
        self.assertIsNone(u["preliminary_severity"])
        self.assertEqual(u["worksheet"]["severity_rule_value"], 2)
        self.assertEqual(u["worksheet"]["rule_preliminary_pin"], 0.0)
        self.assertIsNone(u["worksheet"]["preliminary_pin"])


if __name__ == "__main__":
    unittest.main()
