"""Round 3 of the live smoke test (PLAN-062): the rows that make every testable feature get seen working live on the current build. Offline and hermetic: reads the
repository's own records, not git history."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_full_smoke as full  # noqa: E402
import live_results as lr  # noqa: E402

ROUND3 = ROOT / "docs" / "ROUND3_ROWS.json"
ROUND2 = ROOT / "docs" / "ROUND2_ROWS.json"


def rows():
    return json.loads(ROUND3.read_text(encoding="utf-8"))["rows"]


class TestRound3Rows(unittest.TestCase):
    def test_every_listed_row_exists_and_says_why(self):
        known = {row["id"] for row in full.all_rows()}
        for row_id, reason in rows().items():
            self.assertIn(row_id, known, row_id)
            self.assertTrue(reason.strip(), row_id)

    def test_the_nine_rows_round_2_did_not_run_are_in(self):
        ran = set(json.loads(ROUND2.read_text(encoding="utf-8"))["rows"])
        for row_id in ("A3-cli-bridge", "D2-damage-and-risk", "E2-obfuscate", "F1-mcp-size", "F3-check-evidence", "V1-update", "V6-charts",
                       "W6-mcp-probe", "W7-mcp-dialog"):
            self.assertNotIn(row_id, ran)
            self.assertIn(row_id, rows())

    def test_every_feature_never_seen_live_is_covered_by_a_listed_row(self):
        doc, listed = lr.load(), set(rows())
        covered = {c for row in full.all_rows() if row["id"] in listed for c in row.get("covers", [])}
        ledger = lr.ledger()
        ledger = ledger if isinstance(ledger, list) else [dict(id=k, **v) for k, v in ledger.items()]
        untestable = lr.not_testable()
        # a feature whose ledger entry says a person already hand-tested it has no row at all, so it cannot be listed here
        every_row_covers = {c for row in full.all_rows() for c in row.get("covers", [])}
        missing = [f["id"] for f in ledger if f["id"] not in untestable and f["id"] not in doc["features"]
                   and f["id"] in every_row_covers and f["id"] not in covered]
        self.assertEqual(missing, [])

    def test_the_six_rows_left_out_are_named_in_the_about_text(self):
        about = json.loads(ROUND3.read_text(encoding="utf-8"))["_about"]
        for row_id in {row["id"] for row in full.all_rows()} - set(rows()):
            self.assertIn(row_id, about)


class TestTheReadmeNamesTheRound(unittest.TestCase):
    def test_a_round_3_package_does_not_call_itself_round_2(self):
        text = full.readme("1.18.5", 39, "round3")
        self.assertIn("ROUND 3", text)
        self.assertNotIn("ROUND 2", text)
        self.assertIn("ROUND 2", full.readme("1.18.5", 30, "round2"))


if __name__ == "__main__":
    unittest.main()


class TestTheEvidenceTable(unittest.TestCase):
    """Every package carries EVIDENCE_TABLE.md: for each row what is needed, the input files, the evidence to save and when it passes."""
    def test_every_row_has_its_evidence_and_input_lines(self):
        chosen = [row for row in full.all_rows() if row["id"] in rows()]
        text = full.evidence_table(chosen, "1.18.5")
        for row in chosen:
            self.assertIn(f"## {row['id']}:", text)
        self.assertEqual(text.count("**Evidence to save:**"), len(chosen))
        self.assertEqual(text.count("**Input files (in 3_test_files):**"), len(chosen))
        self.assertEqual(text.count("**Pass when:**"), len(chosen))

    def test_it_says_what_to_do_for_every_row_and_on_a_failure(self):
        text = full.evidence_table(full.all_rows()[:1], "1.18.5")
        self.assertIn("snap(", text)
        self.assertIn("FAILURE_PROTOCOL.md", text)

    def test_a_row_with_input_files_names_them(self):
        row = next(r for r in full.all_rows() if r.get("files"))
        self.assertIn(row["files"][0], full.evidence_table([row], "1.18.5"))


class TestInstructionsMatchThePackageLayout(unittest.TestCase):
    """Round 3 audit, 2026-11-07: rows named scripts and results folders the package does not have (python mcp_probe.py, python tools/check_evidence.py,
    results/outputs/W10). Every instruction must point at something the unzipped package contains."""
    FIELDS = ("starts_from", "do", "expect", "evidence", "inputs", "outputs", "pass_if")

    def texts(self):
        for row in full.all_rows():
            for key in self.FIELDS:
                if isinstance(row.get(key), str):
                    yield row["id"], key, row[key]

    def test_no_row_names_a_script_by_a_path_the_package_does_not_have(self):
        import re
        scripts = {Path(name).name for name in full.TOOLS_FOLDER}
        for row_id, key, text in self.texts():
            self.assertNotRegex(text, r"python3? (?!6_tools/|5_check_evidence\.py)(?:tools[\\/])?[A-Za-z_]+\.py", f"{row_id}.{key}")
            for name in re.findall(r"python3? 6_tools/([A-Za-z_]+\.py)", text):
                self.assertIn(name, scripts, f"{row_id}.{key}")

    def test_every_results_folder_a_row_names_is_a_row_folder(self):
        import re
        ids = {row["id"] for row in full.all_rows()}
        for row_id, key, text in self.texts():
            for folder in re.findall(r"results[\\/]+(?:outputs|evidence)[\\/]+([A-Za-z0-9_\-]+)", text):
                self.assertIn(folder, ids, f"{row_id}.{key}: results folder {folder}")

    def test_the_localising_is_what_does_it(self):
        self.assertEqual(full.localize_text("python mcp_probe.py A B", "W6-mcp-probe"), "python 6_tools/mcp_probe.py A B")
        self.assertEqual(full.localize_text("python tools/check_evidence.py shows", "W6-mcp-probe"), "python 5_check_evidence.py results shows")
        self.assertEqual(full.localize_text("results\\outputs\\W10\\expected.json", "W10-import-bad"), "results\\outputs\\W10-import-bad\\expected.json")
        self.assertEqual(full.localize_text("results\\outputs\\W10-import-bad\\x", "W10-import-bad"), "results\\outputs\\W10-import-bad\\x")
        self.assertEqual(full.localize_text("results\\outputs\\<row id>\\", "V4-animate"), "results\\outputs\\V4-animate\\")
