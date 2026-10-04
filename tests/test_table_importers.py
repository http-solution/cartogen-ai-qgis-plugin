# -*- coding: utf-8 -*-
"""H7 table importers (IPC / INFORM / UNOSAT): detection, validation, joining and the CSV read, offline. The layer join needs QGIS
(tests/test_table_importers_live.py). Column layouts are UNVERIFIED against real HDX files; these tests pin the behaviour, not the files."""
import os
import tempfile
import unittest

from cartogen_ai.core.agent.tools import table_importers as ti


class TestDetect(unittest.TestCase):
    def test_aliases_match_ignoring_case_and_punctuation(self):
        used, missing, amb, prob = ti.detect_columns(["Admin_PCode", "Area Name", "Overall Phase", "Total Population"], "ipc")
        self.assertEqual(used["area_code"], "Admin_PCode")
        self.assertEqual(used["phase"], "Overall Phase")
        self.assertEqual(used["population"], "Total Population")
        self.assertEqual((missing, amb, prob), ([], {}, []))

    def test_missing_required_role_is_reported_not_guessed(self):
        used, missing, _a, _p = ti.detect_columns(["pcode", "value"], "ipc")
        self.assertEqual(missing, ["phase"])
        self.assertNotIn("phase", used)

    def test_two_candidate_columns_are_ambiguous_and_left_unmapped(self):
        used, missing, amb, _p = ti.detect_columns(["pcode", "phase", "current_phase"], "ipc")
        self.assertEqual(set(amb["phase"]), {"phase", "current_phase"})
        self.assertNotIn("phase", used)
        self.assertEqual(missing, ["phase"])

    def test_explicit_mapping_wins_and_a_bad_column_is_a_problem(self):
        used, missing, amb, prob = ti.detect_columns(["pcode", "phase", "current_phase"], "ipc", {"phase": "current_phase"})
        self.assertEqual(used["phase"], "current_phase")
        self.assertEqual((missing, amb, prob), ([], {}, []))
        _u, _m, _a, prob = ti.detect_columns(["pcode"], "ipc", {"phase": "nope", "bogus": "pcode"})
        self.assertEqual(len(prob), 2)


class TestValidation(unittest.TestCase):
    def test_phase_parsing(self):
        for v, want in [(3, 3), (3.0, 3), ("3", 3), ("Phase 3", 3), ("Phase 4 - Emergency", 4), ("IPC 2", 2),
                        ("3+", None), (0, None), (6, None), (3.5, None), ("", None), (None, None), (float("nan"), None), ("Famine", None), (True, None)]:
            self.assertEqual(ti.parse_phase(v), want, repr(v))

    def test_a_missing_phase_is_not_phase_one_and_is_reported(self):
        used = {"area_code": "c", "phase": "p"}
        recs, issues = ti.normalise_rows([{"c": "A", "p": ""}, {"c": "B", "p": "9"}, {"c": "C", "p": "2"}], "ipc", used)
        self.assertEqual([r["phase"] for r in recs], [None, None, 2])
        self.assertEqual([i["row"] for i in issues], [1, 2])

    def test_ipc_population_checks(self):
        used = {"area_code": "c", "phase": "p", "population": "n", "phase3plus_population": "q"}
        recs, issues = ti.normalise_rows([
            {"c": "A", "p": 3, "n": "1,000", "q": "400"},
            {"c": "B", "p": 3, "n": -5, "q": "x"},
            {"c": "C", "p": 3, "n": 100, "q": 500},
        ], "ipc", used)
        self.assertEqual((recs[0]["population"], recs[0]["phase3plus_population"]), (1000.0, 400.0))
        self.assertIsNone(recs[1]["population"])
        self.assertIsNone(recs[1]["phase3plus_population"])
        self.assertEqual(sorted(i["row"] for i in issues), [2, 2, 3])

    def test_inform_scale(self):
        used = {"area_name": "n", "risk": "r"}
        recs, issues = ti.normalise_rows([{"n": "A", "r": 7.5}, {"n": "B", "r": 11}, {"n": "C", "r": "x"}], "inform", used)
        self.assertEqual([r["risk"] for r in recs], [7.5, None, None])
        self.assertEqual(len(issues), 2)

    def test_unosat_coordinates_and_classes(self):
        used = {"latitude": "y", "longitude": "x", "damage_class": "d"}
        recs, issues = ti.normalise_rows([
            {"y": 15.3, "x": 44.2, "d": "Destroyed"},
            {"y": 95, "x": 44.2, "d": "Severe Damage"},
            {"y": 15.3, "x": "", "d": "Rubble-ish"},
        ], "unosat", used)
        self.assertEqual(recs[0]["damage_class"], "destroyed")
        self.assertEqual(recs[1]["damage_class"], "severe")
        self.assertIsNone(recs[1]["latitude"])
        self.assertIsNone(recs[2]["damage_class"])
        self.assertIsNone(recs[2]["longitude"])
        self.assertEqual(len(issues), 3)


class TestJoin(unittest.TestCase):
    def test_code_wins_name_falls_back_and_blank_is_none(self):
        self.assertEqual(ti.key_of(" ye01 ", "x"), "code:YE01")
        self.assertEqual(ti.key_of(None, "Al  Hudaydah"), "name:al hudaydah")
        self.assertIsNone(ti.key_of("", None))

    def test_duplicates_on_either_side_are_never_matched(self):
        recs = [{"key": "code:A"}, {"key": "code:B"}, {"key": "code:B"}, {"key": "code:C"}, {"key": "code:Z"}]
        layer = [(1, "code:A"), (2, "code:B"), (3, "code:C"), (4, "code:C"), (5, "code:Q"), (6, None)]
        pairs, rep = ti.plan_join(recs, layer)
        self.assertEqual([p[0] for p in pairs], [1])
        self.assertEqual(rep["matched"], 1)
        self.assertEqual(rep["layer_features_ambiguous"], 3)  # B (dup in table), C twice (dup on layer)
        self.assertEqual(rep["layer_features_unmatched"], 2)
        self.assertEqual(rep["table_duplicate_keys"], ["code:B"])
        self.assertIn("code:Z", rep["table_rows_unmatched_keys"])


class TestTool(unittest.TestCase):
    def _csv(self, text):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_end_to_end_ipc_csv(self):
        path = self._csv("admin_pcode,area,phase,population\nYE01,A,3,1000\nYE02,B,,500\nYE02,B2,4,10\n")
        out = ti.import_humanitarian_table(path, "ipc")
        self.assertTrue(out["success"])
        self.assertEqual(out["summary"]["areas_by_phase"], {"3": 1, "4": 1})
        self.assertEqual(out["summary"]["areas_without_valid_phase"], 1)
        self.assertEqual(out["duplicate_area_keys"], ["code:YE02"])
        self.assertEqual(out["mapping_used"]["phase"], "phase")

    def test_unidentified_required_column_stops_with_the_remedy(self):
        out = ti.import_humanitarian_table(self._csv("pcode,x\nA,1\n"), "ipc")
        self.assertIn("error", out)
        self.assertEqual(out["unmapped_required_roles"], ["phase"])
        ok = ti.import_humanitarian_table(self._csv("pcode,x\nA,2\n"), "ipc", mapping={"phase": "x"})
        self.assertTrue(ok["success"])

    def test_unosat_points_to_the_loader_and_rejects_join(self):
        out = ti.import_humanitarian_table(self._csv("lat,lon,damage\n15.3,44.2,Destroyed\n"), "unosat", layer_name="x")
        self.assertTrue(out["success"])
        self.assertIn("load_tabular_data_as_layer", out["next_step"])
        self.assertIn("join_note", out)

    def test_bad_inputs(self):
        self.assertIn("error", ti.import_humanitarian_table("/nonexistent.csv", "ipc"))
        self.assertIn("error", ti.import_humanitarian_table(self._csv("a\n1\n"), "bogus"))
        self.assertIn("error", ti.import_humanitarian_table(self._csv("pcode,phase\n"), "ipc"))
        self.assertIn("error", ti.import_humanitarian_table(self._csv("phase\n3\n"), "ipc"))  # no area column


if __name__ == "__main__":
    unittest.main()
