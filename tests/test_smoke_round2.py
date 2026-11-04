"""PLAN-059 (round 2): a smoke package of just the rows that must be rerun, built with `build_full_smoke.py --only`. Offline, no QGIS.

Why: PR 573 changed shared modules, so the regression gate lists 40 features seen working live that need a recheck, and the four Track 2 fixes (V9, V4, A1, B5)
have never been seen working live. The full package is 44 rows; round 2 is the rows those features and fixes need, plus the one case of issue 380 that no row ever tested
(B41, the mesh). What this cannot prove: that any row passes. That is what the live run is for."""
import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_full_smoke as full           # noqa: E402
import cartogen_ai.core.agent.agent_orchestrator  # noqa: E402,F401  (registers every tool)
from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY      # noqa: E402

ROUND2 = ROOT / "docs" / "ROUND2_ROWS.json"
TRACK2_ROWS = {"V9-undo-field", "V4-animate", "A1-layout-script", "B5-chat-formatting"}


class TestSelectRows(unittest.TestCase):
    ROWS = ({"id": "A1"}, {"id": "B2"}, {"id": "C3"})

    def test_the_subset_keeps_the_running_order_not_the_order_asked(self):
        self.assertEqual([r["id"] for r in full.select_rows(self.ROWS, ["C3", "A1"])], ["A1", "C3"])

    def test_an_unknown_id_is_named_not_ignored(self):
        with self.assertRaises(SystemExit) as caught:
            full.select_rows(self.ROWS, ["A1", "Z9-nope"])
        self.assertIn("Z9-nope", str(caught.exception))

    def test_an_empty_list_is_refused(self):
        with self.assertRaises(SystemExit):
            full.select_rows(self.ROWS, [])

    def test_only_accepts_a_comma_list_or_a_json_file(self):
        self.assertEqual(full.parse_only("A1,B2 , C3"), ["A1", "B2", "C3"])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rows.json"
            path.write_text(json.dumps({"rows": {"A1": "reason one is long enough", "B2": "reason two is long enough"}}), encoding="utf-8")
            self.assertEqual(full.parse_only("@" + str(path)), ["A1", "B2"])


class TestTheRoundTwoList(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(ROUND2.read_text(encoding="utf-8"))
        cls.all_ids = {r["id"] for r in full.all_rows()}

    def test_every_listed_row_exists(self):
        self.assertEqual(sorted(set(self.doc["rows"]) - self.all_ids), [])

    def test_every_row_says_why_it_is_there(self):
        for row_id, reason in self.doc["rows"].items():
            self.assertGreater(len(reason), 20, row_id)

    def test_the_four_track_2_fixes_and_the_new_mesh_row_are_in_it(self):
        self.assertTrue(set(self.doc["rows"]) >= TRACK2_ROWS, sorted(TRACK2_ROWS - set(self.doc["rows"])))
        self.assertIn("B6-mesh-to-raster", self.doc["rows"])


class TestTheMeshRow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.row = next(r for r in full.all_rows() if r["id"] == "B6-mesh-to-raster")

    def test_it_is_issue_380s_third_case_with_the_issues_own_wording(self):
        self.assertEqual(self.row["issue"], "#380")
        self.assertIn("Turn the mesh results of the flood model into a raster map I can overlay", self.row["do"])

    def test_it_ships_the_mesh_and_covers_the_routing_entry(self):
        self.assertIn("smoke_mesh.2dm", self.row["files"])
        self.assertIn("plain-requests-not-sent-to-a-wrong-task", self.row["covers"])

    def test_its_checks_name_real_tools_and_forbid_the_wrong_plan(self):
        names = list(self.row.get("expected_tools", [])) + list(self.row.get("forbidden_tools", []))
        self.assertTrue(names)
        for name in names:
            self.assertIn(name, TOOL_REGISTRY, name)
        self.assertIn("native:meshrasterize", self.row["expect"])


class TestTheSubsetPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        version = full.v2.version()
        plugin = Path(cls.tmp.name) / f"cartogen_ai_v{version}.zip"
        with zipfile.ZipFile(plugin, "w") as z:
            z.writestr("stub.txt", "a stand-in so the real dist/ zip is never touched")
        out = Path(cls.tmp.name) / "out"
        with contextlib.redirect_stdout(io.StringIO()):
            full.main(["x", "--plugin-zip", str(plugin), "--out-dir", str(out), "--only", "@" + str(ROUND2), "--label", "round2"])
        cls.zip = zipfile.ZipFile(out / f"cartogen_ai_full_smoke_{version}_round2.zip")
        cls.addClassCleanup(cls.zip.close)
        cls.top = cls.zip.namelist()[0].split("/")[0]
        cls.ids = list(json.loads(ROUND2.read_text(encoding="utf-8"))["rows"])

    def read(self, name):
        return self.zip.read(f"{self.top}/{name}").decode("utf-8")

    def test_the_rows_file_holds_exactly_the_chosen_rows_in_running_order(self):
        rows = json.loads(self.read("3_ROWS.json"))["rows"]
        self.assertEqual({r["id"] for r in rows}, set(self.ids))
        order = [r["id"] for r in full.all_rows() if r["id"] in set(self.ids)]
        self.assertEqual([r["id"] for r in rows], order)

    def test_it_is_smaller_than_the_full_package(self):
        self.assertLess(len(self.ids), len(full.all_rows()))

    def test_the_results_sheet_has_one_line_per_chosen_row(self):
        lines = list(csv.reader(io.StringIO(self.read("4_RESULTS.csv"))))
        self.assertEqual({line[0] for line in lines[1:]}, set(self.ids))

    def test_only_the_chosen_rows_have_a_checklist_and_an_output_folder(self):
        checklists = {n.split("/")[3] for n in self.zip.namelist() if "/results/evidence/" in n and n.endswith("CHECKLIST.txt")}
        self.assertEqual(checklists, set(self.ids))

    def test_the_coverage_page_lists_only_what_these_rows_cover(self):
        text = self.read("COVERAGE.md")
        self.assertIn("legend-not-filtered-away", text)
        self.assertNotIn("task-grid-aoi-where", text)          # row D5 is not in round 2

    def test_every_file_a_chosen_row_names_is_shipped_and_summed(self):
        names = set(self.zip.namelist())
        sums = self.read("3_test_files/SHA256SUMS.txt")
        rows = json.loads(self.read("3_ROWS.json"))["rows"]
        for row in rows:
            for name in row.get("files", []):
                self.assertIn(f"{self.top}/3_test_files/{name}", names, f"{row['id']}: {name}")
                self.assertIn(name, sums)
        self.assertIn("smoke_mesh.2dm", sums)

    def test_the_package_says_which_build_it_carries_so_an_old_1_18_5_is_not_tested_by_mistake(self):
        import re
        text = self.read("1_plugin/BUILD.txt")
        self.assertRegex(text, r"commit: [0-9a-f]{40}")
        self.assertIn("same version number", text)
        self.assertEqual(re.search(r"sha256: ([0-9a-f]{64})", text).group(1), self.read("1_plugin/checksum_sha256.txt").split()[0])
        self.assertIn("BUILD.txt", self.read("README_FIRST.txt"))

    def test_the_readme_says_it_is_round_two_and_why(self):
        text = self.read("README_FIRST.txt")
        self.assertIn("ROUND 2", text)
        self.assertIn(str(len(self.ids)), text)


class TestTheAgentPrompt(unittest.TestCase):
    def test_it_tells_the_agent_to_check_the_build_before_running_rows(self):
        text = (ROOT / "docs" / "FULL_SMOKE_AGENT_PROMPT.md").read_text(encoding="utf-8")
        self.assertIn("BUILD.txt", text)
        self.assertIn("SHA-256", text)


class TestTheFullPackageIsUnchanged(unittest.TestCase):
    def test_the_full_build_still_covers_every_unverified_entry(self):
        doc = full.load()
        self.assertEqual(full.coverage_problems(full.all_rows(doc), doc, full.ledger_not_verified()), [])


if __name__ == "__main__":
    unittest.main()
