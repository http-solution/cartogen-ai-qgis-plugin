"""PLAN-014 phase 3c, offline: the COD flag and credit wording of a profile, and the P-code notes of an export report."""
import unittest

from cartogen_ai.core.agent.tools.layout_export_checks import export_report, pcode_field_of, pcode_notes
from cartogen_ai.core.agent.tools.map_profiles import validate_profile


class TestCodFields(unittest.TestCase):
    def test_flag_with_wording_is_kept(self):
        clean, problems = validate_profile({"cod_boundaries": True, "cod_credit": " Boundaries: COD, see source metadata "})
        self.assertEqual(problems, [])
        self.assertEqual((clean["cod_boundaries"], clean["cod_credit"]), (True, "Boundaries: COD, see source metadata"))

    def test_the_flag_without_wording_is_refused_because_the_plugin_supplies_none(self):
        _, problems = validate_profile({"cod_boundaries": True})
        self.assertTrue(any("needs cod_credit" in p for p in problems), problems)

    def test_wording_without_the_flag_is_refused_rather_than_silently_ignored(self):
        for data in ({"cod_credit": "x"}, {"cod_boundaries": False, "cod_credit": "x"}):
            _, problems = validate_profile(data)
            self.assertTrue(any("no effect" in p for p in problems), data)

    def test_bad_values(self):
        for data in ({"cod_boundaries": "yes", "cod_credit": "x"}, {"cod_boundaries": True, "cod_credit": ""},
                     {"cod_boundaries": True, "cod_credit": "x" * 101}, {"cod_boundaries": True, "cod_credit": "a\nb"}):
            self.assertTrue(validate_profile(data)[1], data)

    def test_the_flag_off_alone_is_valid_and_adds_nothing(self):
        clean, problems = validate_profile({"cod_boundaries": False})
        self.assertEqual((problems, "cod_boundaries" in clean), ([], False))


class TestPcodeNotes(unittest.TestCase):
    def test_finest_admin_level_field_wins_and_case_is_ignored(self):
        self.assertEqual(pcode_field_of(["name", "ADMIN1_PCODE", "Admin2_PCode"]), "Admin2_PCode")
        self.assertEqual(pcode_field_of(["ADM1_PCODE"]), "ADM1_PCODE")
        self.assertIsNone(pcode_field_of(["name", "pcode"]))

    def test_only_layers_with_duplicates_are_reported(self):
        notes, findings = pcode_notes([{"layer": "a", "field": "admin2_pcode", "duplicates": 0}, {"layer": "b", "field": "admin2_pcode", "duplicates": 3}])
        self.assertEqual([f["layer"] for f in findings], ["b"])
        self.assertIn("'b' has 3 duplicated", notes[0])

    def test_the_export_report_carries_them_and_stays_empty_without(self):
        report = export_report([], ["MAP_MAIN", "TITLE", "LEGEND", "SCALEBAR", "NORTH_ARROW"],
                               pcode_checks=[{"layer": "b", "field": "admin2_pcode", "duplicates": 3}])
        self.assertEqual(report["pcode_findings"][0]["duplicates"], 3)
        self.assertTrue(any("COD check" in w for w in report["export_warnings"]))
        self.assertEqual(export_report([], ["MAP_MAIN", "TITLE", "LEGEND", "SCALEBAR", "NORTH_ARROW"]), {})


if __name__ == "__main__":
    unittest.main()
