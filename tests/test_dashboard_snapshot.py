"""PLAN-052: the dashboard's data generator works against this repository and keeps the shapes the dashboard page reads. Offline; no QGIS, no network."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dashboard_snapshot", ROOT / "tools" / "dashboard_snapshot.py")
snap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snap)

SUMMARY_KEYS = {"live_recheck_label", "live_testable", "live_working", "live_partly", "live_failing", "live_not_seen", "live_not_testable", "live_run_date", "live_needs_recheck", "as_of", "version", "release_state", "tools", "tests_run", "tests_sandbox_errors", "open_prs", "open_pr_note", "ledger_total",
                "ledger_by_hand", "ledger_partly", "ledger_not", "plans_total", "plans_planned", "plans_abandoned", "plans_in_progress", "plans_done",
                "tasks_open", "tasks_waiting_on_owner"}


class TestLedgerClass(unittest.TestCase):
    def test_the_three_classes(self):
        self.assertEqual(snap.ledger_class("partly: the owner's run"), "Partly verified")
        for text in ("not verified: CI only", "not hand-tested; x", "none: no entry point", "offline only by design", "", None):
            self.assertEqual(snap.ledger_class(text), "Not hand-verified", text)
        self.assertEqual(snap.ledger_class("hand-tested rc46 retest 3: Pass"), "Verified by hand")
        self.assertEqual(snap.ledger_class("2026-10-25: pages pushed and the owner looked at the rendered wiki and found it fine"), "Verified by hand")

    def test_text_that_only_mentions_hand_testing_is_not_counted(self):
        for text in ("plain-language hand test (385 prompts) not run; rows B1-B40", "rc45 smoke run confirmed the misroutes; fix not hand-tested",
                     "CI live only; the hand-test observations were not reproduced", "rows A1-A3, A15 of the rc47 bundle"):
            self.assertEqual(snap.ledger_class(text), "Not hand-verified", text)

    def test_the_real_ledger_counts_what_it_says(self):
        ledger = json.loads((ROOT / "docs" / "FEATURE_LEDGER.json").read_text(encoding="utf-8"))["features"]
        by_hand = [f["id"] for f in ledger if snap.ledger_class(f["hand_verified"]) == "Verified by hand"]
        for known_true in ("docs-published-to-wiki", "processing-layer-kind", "undo-across-messages"):
            self.assertIn(known_true, by_hand)
        for known_false in ("fragment-guard", "plain-language-discovery", "named-algorithm-no-task", "gate-and-ramp-real-flow-guards"):
            self.assertNotIn(known_false, by_hand)


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        self.summary = snap.build(self.out, ROOT, {"tests": 10, "sandbox_errors": 2, "open_prs": 1, "open_pr_note": "x"})

    def test_the_summary_has_every_column_the_page_reads_and_the_ledger_adds_up(self):
        self.assertEqual(set(self.summary), SUMMARY_KEYS)
        self.assertEqual(self.summary["ledger_by_hand"] + self.summary["ledger_partly"] + self.summary["ledger_not"], self.summary["ledger_total"])
        self.assertGreater(self.summary["tools"], 200)
        self.assertEqual(self.summary["tests_run"], 10)

    def test_each_file_is_a_list_of_row_objects_with_the_columns_the_page_reads(self):
        needed = {"summary.json": SUMMARY_KEYS, "work_items.json": {"id", "stream", "who", "priority", "size", "status", "task"},
                  "activity.json": {"date", "change", "pr"}, "hand_tests.json": {"row", "what", "agent_result", "after_recheck", "note", "needs_rerun"},
                  "defects.json": {"id", "defect", "found_by", "status", "pr", "next"}}
        for name, columns in needed.items():
            rows = json.loads((self.out / name).read_text(encoding="utf-8"))
            self.assertIsInstance(rows, list, name)
            self.assertTrue(rows, name)
            for row in rows:
                self.assertEqual(set(row), columns, name)

    def test_open_work_items_exclude_closed_rows(self):
        rows = json.loads((self.out / "work_items.json").read_text(encoding="utf-8"))
        self.assertFalse([r for r in rows if r["status"].startswith("Closed")])
        self.assertEqual(len(rows), self.summary["tasks_open"])

    def test_the_hand_kept_files_use_known_values(self):
        for row in json.loads((ROOT / "docs" / "dashboard_data" / "hand_tests.json").read_text(encoding="utf-8")):
            self.assertIn(row["after_recheck"], ("Pass", "Partial", "Fail", "Skip"), row["row"])
        for row in json.loads((ROOT / "docs" / "dashboard_data" / "defects.json").read_text(encoding="utf-8")):
            self.assertTrue(row["status"] and row["defect"], row["id"])

    def test_no_credential_shaped_text_reaches_the_output(self):
        import re
        text = "".join(p.read_text(encoding="utf-8") for p in self.out.glob("*.json"))
        self.assertFalse(re.search(r"sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|Bearer\s+[A-Za-z0-9._-]{16,}", text))


class TestLiveRecheckCount(unittest.TestCase):
    """The recheck count is a number or -1 (unknown); the page must say 'unknown' for -1, never print it as a count."""

    def test_a_missing_baseline_gives_minus_one_not_a_guess(self):
        from unittest import mock
        import live_results
        with mock.patch.object(live_results, "changed_since", side_effect=live_results.BaselineMissingError("no baseline")):
            out = Path(tempfile.mkdtemp())
            self.assertEqual(snap.build(out, ROOT, {})["live_needs_recheck"], -1)

    def test_a_present_baseline_gives_the_count_that_the_gate_prints(self):
        import live_results
        doc, feats = live_results.load(), live_results.ledger()
        expected = len(live_results.needs_recheck(doc, feats, live_results.changed_since(next(iter(doc["runs"].values()))["baseline_commit"]),
                                                  live_results.head_sha(), live_results.dependencies(feats)))
        out = Path(tempfile.mkdtemp())
        self.assertEqual(snap.build(out, ROOT, {})["live_needs_recheck"], expected)

    def test_the_label_the_page_prints_says_unknown_for_minus_one_and_the_number_otherwise(self):
        self.assertEqual(snap.recheck_label(-1), "unknown")
        self.assertEqual(snap.recheck_label(0), "0")
        self.assertEqual(snap.recheck_label(17), "17")


class TestRunTestsParser(unittest.TestCase):
    def test_the_summary_line_is_read(self):
        from unittest import mock
        fake = mock.Mock(stderr="....\nRan 5792 tests in 120.5s\n\nFAILED (errors=54, skipped=980)\n", stdout="")
        with mock.patch.object(snap.subprocess, "run", return_value=fake):
            self.assertEqual(snap.run_tests(ROOT), (5792, 54))
        ok = mock.Mock(stderr="Ran 3 tests in 0.1s\n\nOK\n", stdout="")
        with mock.patch.object(snap.subprocess, "run", return_value=ok):
            self.assertEqual(snap.run_tests(ROOT), (3, 0))


if __name__ == "__main__":
    unittest.main()
