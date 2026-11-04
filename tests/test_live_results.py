"""docs/LIVE_RESULTS.json is the record of what a live run actually showed per feature (PLAN-057). These tests keep it honest: every id is a real
ledger entry, every row a real smoke row, no feature the run could not test is claimed, and a feature recorded as working has an automated guard so a
later change cannot silently break it. They also pin the regression gate's rule."""
import json
import sys
import unittest
from pathlib import Path
from types import MappingProxyType

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import live_results  # noqa: E402


class TestRecord(unittest.TestCase):
    def test_the_committed_record_has_no_problems(self):
        self.assertEqual(live_results.problems(live_results.load(), live_results.ledger(), live_results.row_ids(), live_results.not_testable()), [])

    def test_summary_counts_add_up_to_the_testable_total(self):
        s = live_results.summary(live_results.load(), live_results.ledger(), live_results.not_testable())
        self.assertEqual(s["working"] + s["partly"] + s["failing"] + s["not_tested"], s["testable"])
        self.assertEqual(s["testable"] + s["not_testable"], s["ledger"])


class TestProblems(unittest.TestCase):
    LEDGER = ({"id": "a", "guards": ["tests/x.py::T"]}, {"id": "b", "guards": []}, {"id": "c", "guards": ["t"]})

    def check(self, features, nht=()):
        doc = {"runs": {"r": {"baseline_commit": "x"}}, "features": features}
        return live_results.problems(doc, self.LEDGER, {"R1"}, set(nht))

    def test_clean_record(self):
        self.assertEqual(self.check({"a": {"status": "working", "rows": "R1", "note": "n"}}), [])

    def test_unknown_feature_row_and_status_are_named(self):
        text = " | ".join(self.check({"zzz": {"status": "working", "rows": "R1", "note": "n"},
                                      "a": {"status": "great", "rows": "R9", "note": "n"}}))
        for needle in ("zzz", "great", "R9"):
            self.assertIn(needle, text)

    def test_not_testable_feature_cannot_be_claimed(self):
        self.assertTrue(self.check({"a": {"status": "working", "rows": "R1", "note": "n"}}, nht={"a"}))

    def test_working_feature_without_a_guard_is_refused(self):
        self.assertTrue(self.check({"b": {"status": "working", "rows": "R1", "note": "n"}}))

    def test_a_note_is_required(self):
        self.assertTrue(self.check({"a": {"status": "working", "rows": "R1", "note": ""}}))


class TestGate(unittest.TestCase):
    LEDGER = ({"id": "a", "sources": ["s/a.py"]}, {"id": "b", "sources": ["s/b.py"]}, {"id": "c", "sources": ["s/c.py"]})
    DOC = MappingProxyType({"features": {"a": {"status": "working"}, "b": {"status": "partly"}, "c": {"status": "failing"}}})

    def test_only_working_or_partly_features_with_changed_sources_need_a_recheck(self):
        hit = live_results.needs_recheck(self.DOC, self.LEDGER, {"s/a.py", "s/c.py", "other.py"})
        self.assertEqual(hit, ["a"])

    def test_nothing_changed_nothing_to_recheck(self):
        self.assertEqual(live_results.needs_recheck(self.DOC, self.LEDGER, set()), [])

    def test_rechecked_features_are_released_from_the_gate(self):
        doc = json.loads(json.dumps(dict(self.DOC)))
        doc["features"]["a"]["rechecked_at"] = "deadbeef"
        self.assertEqual(live_results.needs_recheck(doc, self.LEDGER, {"s/a.py"}, head="deadbeef"), [])
        self.assertEqual(live_results.needs_recheck(doc, self.LEDGER, {"s/a.py"}, head="other"), ["a"])


if __name__ == "__main__":
    unittest.main()
