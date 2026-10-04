# -*- coding: utf-8 -*-
"""JIAF 2 stage 2: reading and validating sector inputs, offline. Grids mirror the layouts seen in the real Yemen worksheet and published
HNO files; the real files themselves are not committed (tests/test_jiaf_inputs_yemen_local.py uses them when JIAF_YEMEN_DIR is set)."""
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools import jiaf_inputs as ji

PIN_HDR = ["Admin 1", "Admin 1 P-Code", "Admin 2", "Admin 2 P-Code", "Population", "Population Group", "CCCM", "Education", "Nutrition",
           "Food Security", "Health", "Overarching Protection", "Shelter", "WASH", "CP", "GBV", "Mine Action", "HLP", "Severity",
           "Preliminary PiN", "Final PiN", "Evidence & Comments"]
SEV_HDR = ["Admin 1", "Admin 1 P-Code", "Admin 2", "Admin 2 P-Code", "Population", "Population Group", "CCCM", "Education", "Nutrition",
           "Food Security", "Health", "Overarching Protection", "Shelter", "WASH", "Child Protection (CP)", "Gender-based Violence (GBV)",
           "Mine Action", "HLP", "Preliminary Intersectoral Severity based on overlap of sectoral deprivations", "Mortality", "Malnutrition",
           "Epidemics", "Livelihood Coping", "HR/IHL Violation", "Final Severity", "Evidence & Comments"]


def _pin_grid(rows):
    return [["Location", None, None, None, "Populaton", None, "Sectoral PiN (Number)"], PIN_HDR] + rows


def _sev_grid(rows):
    return [["Location"], ["Location"], SEV_HDR] + rows


class TestValues(unittest.TestCase):
    def test_numbers_dashes_and_text(self):
        for v, want in [(5, 5.0), ("1,234", 1234.0), (" -   ", None), ("", None), (None, None), (float("nan"), None), ("abc", None), (True, None)]:
            self.assertEqual(ji.to_num(v), want, repr(v))


class TestOchaWorksheet(unittest.TestCase):
    def _units(self):
        pin = _pin_grid([
            ["Ibb", "YE11", "Al Qafr", "YE1101", 165527.5, None, 0, 31847.9, 38139, 82763.7, 91040, 33106, 22946, 67717, 27783, 44229, 0, None, 3, 91040, 91040, None],
            ["Ibb", "YE11", "Yarim", "YE1102", 271776.7, None, 419, 52290.4, 62614, 135888.3, 149477, 108710, 271762, 109918, 43967, 72636, 0, None, 3, 271762, 149477, "chose health"],
        ])
        sev = _sev_grid([
            ["Ibb", "YE11", "Al Qafr", "YE1101", 165527.5, None, 0, 3, 3, 4, 4, 2, 3, 3, 2, 4, " -   ", None, 3, "", "", "", "", "", 3, None],
            ["Ibb", "YE11", "Yarim", "YE1102", 271776.7, None, 0, 3, 3, 4, 3, 2, 4, 3, 2, 4, 0, None, 3, "", "", "", "", "", 3, None],
        ])
        return ji.parse_ocha_worksheet(pin, sev)

    def test_units_sectors_and_stored_columns(self):
        units, notes = self._units()
        self.assertEqual(notes, [])
        self.assertEqual([u["admin2_code"] for u in units], ["YE1101", "YE1102"])
        u = units[1]
        self.assertEqual(u["pin"]["shelter"], 271762)
        self.assertEqual(u["pin"]["protection"], 108710)
        self.assertEqual(u["severity"]["food_security"], 4)
        self.assertEqual(u["stored"]["final_pin"], 149477)
        self.assertEqual(u["stored"]["evidence"], "chose health")
        self.assertEqual(u["stored"]["final_severity"], 3)
        self.assertIn("child_protection", u["pin"])
        self.assertIn("child_protection", u["severity"])  # 'Child Protection (CP)' header

    def test_validation_keeps_zero_severity_apart_and_never_fills(self):
        units, _ = self._units()
        issues, summary = ji.validate_units(units)
        self.assertEqual([i for i in issues if i["level"] == "error"], [])
        self.assertEqual(units[0]["severity"]["cccm"], 0)
        self.assertIsNone(units[0]["severity"]["mine_action"])  # dash placeholder is missing, not 0
        self.assertEqual(summary["severity_zero_values"], 3)  # cccm x2 + mine_action 0 on the second unit
        self.assertEqual(summary["sectors"]["cccm"]["severity_units_with_phase"], 0)
        self.assertEqual(summary["sectors"]["wash"]["pin_sum_over_units"], 67717 + 109918)


class TestHxl(unittest.TestCase):
    GRID = [
        ["Demographic Information", None, None, None, "Humanitarian Condition Score", "Total PiN"],
        ["Gov_PCODE", "Governorate", "Dis_PCODE", "District", "Severity", "Total PiN", "Boys", "Total PiN", "Severity", "Total PiN", "Severity", "Total PiN"],
        ["#adm1 +code", "#adm1 +name", "#adm2 +code", "#adm2 +name", "#severity", "#inneed", "#inneed +boys", "#inneed +wsh", "#severity +wsh",
         "#inneed +shl", "#severity +shl", "#inneed +rrm"],
        ["YE11", "Ibb", "YE1101", "Al Qafr", 3, 91040, 5, 67717, 3, 22946, 3, 10],
        ["YE11", "Ibb", "YE1102", "Yarim", 3, 149477, 6, 109918, 3, 271762, 4, 11],
    ]

    def test_tag_row_sectors_totals_and_ignored_tags(self):
        units, notes = ji.parse_hxl_table(self.GRID)
        self.assertEqual(len(units), 2)
        self.assertEqual(units[1]["pin"], {"wash": 109918, "shelter": 271762})
        self.assertEqual(units[1]["severity"], {"wash": 3, "shelter": 4})
        self.assertEqual(units[0]["stored"]["total_pin"], 91040)
        self.assertEqual(units[0]["stored"]["final_severity"], 3)
        self.assertTrue(any("rrm" in n for n in notes))

    def test_population_parts_are_summed_and_a_total_is_not_confused_with_a_part(self):
        grid = [["#adm2 +code", "#population +idps", "#population +residents", "#inneed +wsh"], ["YE1", 100, 900, 50]]
        units, _ = ji.parse_hxl_table(grid)
        self.assertEqual(units[0]["population"], 1000.0)
        grid2 = [["#adm2 +code", "#population", "#inneed +wsh"], ["YE1", 1000, 50]]
        self.assertEqual(ji.parse_hxl_table(grid2)[0][0]["population"], 1000)

    def test_missing_code_column_is_reported(self):
        units, notes = ji.parse_hxl_table([["#adm1 +code", "#inneed", "#severity"], ["YE1", 1, 2]])
        self.assertEqual(units, [])
        self.assertTrue(notes)


class TestSectorTemplate(unittest.TestCase):
    HDR = ["Admin 1", "Admin 1 P-Code", "Admin 2", "Admin 2 P-Code", "Population", "Cluster's PiN (Number)"]

    def test_reads_the_annex_4_layout_and_merges_sectors(self):
        a, _ = ji.parse_sector_template([self.HDR, ["Al-Anbar", "IQG01", "Al-Falluja", "IQG01Q01", "540,532", 1000]], "wash", "pin")
        sev_hdr = self.HDR[:5] + ["Cluster's Severity (Number)"]
        b, _ = ji.parse_sector_template([sev_hdr, ["Al-Anbar", "IQG01", "Al-Falluja", "IQG01Q01", "540,532", 4]], "wash", "severity")
        merged = ji.merge_units([a, b])
        self.assertEqual(len(merged), 1)
        ji.validate_units(merged)
        self.assertEqual(merged[0]["pin"]["wash"], 1000)
        self.assertEqual(merged[0]["severity"]["wash"], 4)
        self.assertEqual(merged[0]["population"], 540532)

    def test_bad_arguments(self):
        self.assertTrue(ji.parse_sector_template([self.HDR], "nope", "pin")[1])
        self.assertTrue(ji.parse_sector_template([self.HDR], "wash", "weird")[1])
        self.assertTrue(ji.parse_sector_template([["Admin 2 P-Code", "x"]], "wash", "pin")[1])


class TestValidation(unittest.TestCase):
    def _unit(self, **kw):
        u = ji._empty_unit("YE1", "A", "YE", "Ye", None)
        u.update(kw)
        return u

    def test_pin_and_severity_rules(self):
        u = self._unit(population=100, pin={"wash": -5, "health": "x", "shelter": 150, "nutrition": 40},
                       severity={"wash": 6, "health": 2.5, "shelter": "3", "nutrition": 0, "cccm": 1})
        issues, _ = ji.validate_units([u])
        by = {(i["sector"], i["field"]): i for i in issues}
        self.assertIn(("wash", "pin"), by)
        self.assertIn(("health", "pin"), by)
        self.assertEqual(by[("shelter", "pin")]["level"], "warning")
        self.assertNotIn(("nutrition", "pin"), by)
        self.assertEqual(u["severity"], {"wash": None, "health": None, "shelter": 3, "nutrition": 0, "cccm": 1})
        self.assertIsNone(u["pin"]["wash"])

    def test_duplicates_are_reported_not_merged(self):
        issues, _ = ji.validate_units([self._unit(), self._unit()])
        self.assertTrue(any("duplicate" in i["problem"] for i in issues))

    def test_aor_pin_above_population_is_not_warned(self):
        u = self._unit(population=10, pin={"gbv": 50})
        self.assertEqual(ji.validate_units([u])[0], [])


class TestSetup(unittest.TestCase):
    OK = {"country": "Yemen", "planning_cycle": "HPC 2026", "unit_of_analysis": "admin 2", "manual_edition": "July 2024"}

    def test_valid_and_required_fields(self):
        clean, al, errors = ji.validate_setup(dict(self.OK), [{"sector": "WASH", "pin_aligned": True, "severity_alignment": "aligned"}])
        self.assertEqual(errors, [])
        self.assertEqual(al[0]["sector"], "wash")
        _c, _a, errors = ji.validate_setup({"country": "Yemen"}, [])
        self.assertEqual(len(errors), 3)

    def test_explanations_are_required_when_not_aligned(self):
        _c, _a, errors = ji.validate_setup(dict(self.OK), [
            {"sector": "health", "pin_aligned": False}, {"sector": "nutrition", "severity_alignment": "adapted"},
            {"sector": "mystery"}, {"sector": "wash", "severity_alignment": "weird"}])
        self.assertEqual(len(errors), 4)
        _c, a, errors = ji.validate_setup(dict(self.OK), [{"sector": "health", "pin_aligned": False, "pin_explanation": "counts all affected"}])
        self.assertEqual(errors, [])

    def test_hct_flag_must_be_boolean(self):
        s = dict(self.OK, hct_endorsed_scope="yes")
        self.assertTrue(ji.validate_setup(s, [])[2])


class TestDetectAndTool(unittest.TestCase):
    def test_detection(self):
        self.assertEqual(ji.detect_format({"WS - 3.1 Overall PiN": [], "WS - 3.2 Intersectoral Severity": []}), "ocha_worksheet")
        self.assertEqual(ji.detect_format({"x": TestHxl.GRID}), "hxl")
        self.assertEqual(ji.detect_format({"x": [TestSectorTemplate.HDR]}), "sector_template")
        self.assertIsNone(ji.detect_format({"x": [["a", "b"]]}))

    def test_tool_on_a_csv_hxl_file(self):
        import csv
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.addCleanup(os.remove, path)
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(TestHxl.GRID)
        out = ji.import_jiaf_inputs(path)
        self.assertTrue(out["success"], out)
        self.assertEqual(out["format"], "hxl")
        self.assertEqual(out["units"], 2)
        self.assertIn("not endorsed", out["statement"])
        self.assertIn("education", out["main_sectors_missing"])
        self.assertEqual(out["per_sector"]["shelter"]["pin_sum_over_units"], 22946 + 271762)

    def test_tool_errors(self):
        self.assertIn("error", ji.import_jiaf_inputs("/nonexistent.xlsx"))
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.addCleanup(os.remove, path)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("a,b\n1,2\n")
        self.assertIn("error", ji.import_jiaf_inputs(path))
        self.assertIn("error", ji.import_jiaf_inputs(path, input_format="bogus"))
        self.assertIn("error", ji.import_jiaf_inputs(path, input_format="sector_template"))


@unittest.skipUnless(os.environ.get("JIAF_YEMEN_DIR"), "set JIAF_YEMEN_DIR to the folder holding the Yemen workbooks")
class TestYemenLocal(unittest.TestCase):
    """Runs on the real supplied files (not committed). Pins what the specification states about them."""

    def _p(self, suffix):
        d = os.environ["JIAF_YEMEN_DIR"]
        return os.path.join(d, next(f for f in os.listdir(d) if f.endswith(suffix)))

    def test_worksheet(self):
        out = ji.import_jiaf_inputs(self._p("jiaf_yemen_2026.xlsx"))
        self.assertEqual((out["format"], out["units"]), ("ocha_worksheet", 333))
        self.assertEqual(out["main_sectors_missing"], [])

    def test_hno_2026_published(self):
        out = ji.import_jiaf_inputs(self._p("yemen_jiaf_hnrp_2026.xlsx"), sheet_name="HNO 2026")
        self.assertEqual((out["format"], out["units"]), ("hxl", 333))
        self.assertEqual(out["main_sectors_missing"], [])


if __name__ == "__main__":
    unittest.main()
