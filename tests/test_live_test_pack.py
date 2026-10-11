"""The full live-test pack (docs/FULL_LIVE_TEST_rc34.md): the row list is complete and consistent, the fixtures match their checksums, and
tools/live_test_pack.py prepares a run folder and checks its evidence. Runs without QGIS."""
import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("live_test_pack", REPO / "tools" / "live_test_pack.py")
pack = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pack)


def _rows():
    return pack.read_rows(pack.ROWS)


class TestRowList(unittest.TestCase):
    def test_ids_are_unique_and_every_row_has_a_prompt_and_an_expectation(self):
        rows = _rows()
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)))
        for r in rows:
            self.assertTrue(r["prompt_or_action"].strip(), r["id"])
            self.assertTrue(r["expected"].strip(), r["id"])
            self.assertEqual(r["screenshot_file"], f"screenshots/{r['id']}.png")

    def test_every_earlier_matrix_row_is_still_in_the_list(self):
        earlier = pack.read_rows(REPO / "docs" / "RC22_RESULT_MATRIX_2026-10-09.csv")
        have = {r["id"] for r in _rows()}
        self.assertEqual({r["id"] for r in earlier} - have, set())

    def test_the_rc34_sheet_rows_are_all_present(self):
        text = (REPO / "docs" / "RC34_HAND_VERIFICATION_SHEET.md").read_text(encoding="utf-8")
        in_sheet = set(re.findall(r"^\| ([A-Z]\d) \|", text, re.M))
        have = {r["id"] for r in _rows() if r["id"].startswith("RC34-")}
        self.assertEqual({"RC34-" + i for i in in_sheet}, have)

    def test_inputs_named_by_a_row_exist_and_no_placeholder_is_left_unresolved(self):
        names = {p.name for p in pack.INPUTS.iterdir()}
        for r in _rows():
            for f in [x.strip() for x in re.split(r"[;,]", r["inputs_used"]) if x.strip().startswith("smoke_")]:
                self.assertIn(f, names, r["id"])
            for placeholder in re.findall(r"<[^>]{1,40}>", r["prompt_or_action"]):
                self.assertEqual((r["id"], placeholder), ("Q5", "<table>"))   # the one operator-supplied database table name

    def test_promised_output_files_are_relative_to_test_root(self):
        for r in _rows():
            out = r["expected_output_file"]
            self.assertNotIn("{TEST_ROOT}", out, r["id"])


class TestFixtures(unittest.TestCase):
    def test_every_fixture_matches_its_checksum_and_none_is_unlisted(self):
        manifest = pack.read_manifest()
        self.assertEqual(set(manifest), {p.name for p in pack.INPUTS.iterdir() if p.is_file()})
        for name, digest in manifest.items():
            self.assertEqual(pack.sha256(pack.INPUTS / name), digest, name)


class TestPrepareAndCheck(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "run"

    def test_prepare_builds_the_tree_and_fills_the_paths(self):
        self.assertEqual(pack.prepare(self.root), 0)
        for sub in pack.SUBFOLDERS:
            self.assertTrue((self.root / sub).is_dir(), sub)
        self.assertTrue((self.root / "inputs" / "smoke_start.qgz").is_file())
        filled = pack.read_rows(self.root / "results" / "prompts_filled.csv")
        self.assertFalse(any("{TEST_ROOT}" in r["prompt_or_action"] for r in filled))
        t1 = next(r for r in filled if r["id"] == "T1")
        self.assertIn(self.root.resolve().as_posix() + "/inputs/smoke_ipc.csv", t1["prompt_or_action"])

    def test_prepare_refuses_a_folder_that_already_has_files(self):
        self.root.mkdir()
        (self.root / "x.txt").write_text("x")
        self.assertEqual(pack.prepare(self.root), 2)

    def test_check_reports_missing_evidence_and_missing_output_files(self):
        pack.prepare(self.root)
        results = self.root / "results" / "results.csv"
        rows = pack.read_rows(results)
        for r in rows:
            if r["id"] == "N3":
                r["result"] = "PASS"
            if r["id"] == "R1":
                r["result"] = "PASS"
                r["model_calls"] = "6"
            if r["id"] == "SC-C5":
                r["result"] = "PASS"
        pack.write_rows(results, rows, list(rows[0].keys()))
        (self.root / "screenshots" / "R1_layers.png").write_bytes(b"x")
        (self.root / "outputs" / "sandbox_should_not_exist.txt").write_text("it exists")
        self.assertEqual(pack.check(self.root, strict=True), 1)
        summary = (self.root / "results" / "summary.md").read_text(encoding="utf-8")
        self.assertIn("- N3", summary)                       # PASS with no screenshot
        self.assertIn("N3: outputs/smoke_points.csv", summary)  # promised file absent
        self.assertIn("SC-C5: outputs/sandbox_should_not_exist.txt", summary)   # forbidden file present
        self.assertIn("R1: 6 calls", summary)
        self.assertNotIn("- R1\n", summary.split("Rows with a result but no screenshot")[1].split("##")[0])   # R1 has its screenshot

    def test_check_passes_a_row_with_screenshot_and_output(self):
        pack.prepare(self.root)
        results = self.root / "results" / "results.csv"
        rows = pack.read_rows(results)
        next(r for r in rows if r["id"] == "SC-A6")["result"] = "PASS"
        pack.write_rows(results, rows, list(rows[0].keys()))
        (self.root / "screenshots" / "SC-A6_file.png").write_bytes(b"x")
        (self.root / "outputs" / "smoke_points.csv").write_text("name\n")
        self.assertEqual(pack.check(self.root, strict=True), 0)


if __name__ == "__main__":
    unittest.main()
