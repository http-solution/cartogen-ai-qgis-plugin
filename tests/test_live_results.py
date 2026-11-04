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


class TestBaselineAndDependencies(unittest.TestCase):
    """PLAN-057 Track 1: the gate must say 'cannot check' rather than pass or show a wrong number when the baseline commit is missing (a shallow CI clone),
    and a change to a module a feature imports directly must count as touching that feature."""

    def make_tree(self, root):
        pkg = Path(root) / "src" / "cartogen_ai" / "core"
        (pkg / "sub").mkdir(parents=True)
        for init in (Path(root) / "src" / "cartogen_ai" / "__init__.py", pkg / "__init__.py", pkg / "sub" / "__init__.py"):
            init.write_text("", encoding="utf-8")
        (pkg / "net.py").write_text("X = 1\n", encoding="utf-8")
        (pkg / "log.py").write_text("Y = 1\n", encoding="utf-8")
        (pkg / "deep.py").write_text("Z = 1\n", encoding="utf-8")
        (pkg / "sub" / "tool.py").write_text("from ..net import X\nfrom .. import log\nimport cartogen_ai.core.sub.helper\nimport os\n", encoding="utf-8")
        (pkg / "sub" / "helper.py").write_text("from ..deep import Z\n", encoding="utf-8")
        return "src/cartogen_ai/core/sub/tool.py"

    def test_direct_imports_absolute_and_relative_count_but_not_their_imports(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            tool = self.make_tree(root)
            deps = live_results.dependencies([{"id": "f", "sources": [tool, "docs/x.md"]}], Path(root))["f"]
        self.assertEqual(deps, {tool, "docs/x.md", "src/cartogen_ai/core/net.py", "src/cartogen_ai/core/log.py", "src/cartogen_ai/core/sub/helper.py"})
        self.assertNotIn("src/cartogen_ai/core/deep.py", deps)

    def test_a_change_to_a_direct_import_flags_the_feature(self):
        ledger = [{"id": "f", "sources": ["s/a.py"]}, {"id": "g", "sources": ["s/b.py"]}]
        doc = {"features": {"f": {"status": "working"}, "g": {"status": "working"}}}
        deps = {"f": {"s/a.py", "lib/net.py"}, "g": {"s/b.py"}}
        self.assertEqual(live_results.needs_recheck(doc, ledger, {"lib/net.py"}, deps=deps), ["f"])

    def test_a_missing_baseline_is_reported_not_swallowed(self):
        with self.assertRaises(live_results.BaselineMissingError) as caught:
            live_results.changed_since("0" * 40, fetch=False)
        self.assertIn("baseline", str(caught.exception))

    def test_main_gate_exits_2_when_the_baseline_is_missing(self):
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        with mock.patch.object(live_results, "changed_since", side_effect=live_results.BaselineMissingError("baseline abc is not in this clone")):
            out = io.StringIO()
            with redirect_stdout(out), mock.patch.object(sys, "argv", ["live_results.py", "--gate"]):
                code = live_results.main()
        self.assertEqual(code, 2)
        self.assertIn("cannot check", out.getvalue())
