"""tools/prune_branches.py (HY-4): the decision rules are pure and pinned here; the git calls are mocked, so nothing ever touches a remote."""
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("prune_branches", ROOT / "tools" / "prune_branches.py")
pb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pb)

TIP, OTHER = "a" * 40, "b" * 40


class TestReadPlan(unittest.TestCase):
    def test_the_dry_run_document_gives_40_merged_and_15_undecided_branches(self):
        merged, undecided = pb.read_plan(pb.DOC.read_text(encoding="utf-8"))
        self.assertEqual((len(merged), len(undecided)), (40, 15))
        self.assertTrue(all(b.startswith("claude/") for b, _ in merged + undecided))
        self.assertNotIn("main", [b for b, _ in merged + undecided])
        self.assertIn(("claude/results-cleanup", [246, 117]), merged)


class TestDecide(unittest.TestCase):
    def test_a_merged_branch_is_deleted_only_when_its_tip_is_a_pr_head(self):
        self.assertEqual(pb.decide("claude/x", "199", TIP, {199: TIP})[0], "delete")
        self.assertEqual(pb.decide("claude/x", "246 117", TIP, {117: TIP})[0], "delete")
        self.assertEqual(pb.decide("claude/x", "199", OTHER, {199: TIP})[0], "skip")       # the branch moved after the merge
        self.assertEqual(pb.decide("claude/x", "199", TIP, {})[0], "skip")                 # the pull request ref is gone

    def test_a_closed_unmerged_pr_branch_is_deleted_only_when_the_pr_keeps_the_same_commit(self):
        state = "PR #287 closed, never merged"
        self.assertEqual(pb.decide("claude/x", state, TIP, {287: TIP})[0], "delete")
        self.assertEqual(pb.decide("claude/x", state, OTHER, {287: TIP})[0], "tag_then_delete")

    def test_commits_only_on_the_branch_are_tagged_before_deletion(self):
        self.assertEqual(pb.decide("claude/x", "no pull request", TIP, {})[0], "tag_then_delete")
        self.assertEqual(pb.decide("claude/x", "PR #173 merged, but later commits exist on the branch", OTHER, {173: TIP})[0], "tag_then_delete")

    def test_main_the_current_branch_other_namespaces_and_missing_branches_are_never_touched(self):
        self.assertEqual(pb.decide("main", "199", TIP, {199: TIP})[0], "skip")
        self.assertEqual(pb.decide("feature/x", "199", TIP, {199: TIP})[0], "skip")
        self.assertEqual(pb.decide("claude/me", "199", TIP, {199: TIP}, current_branch="claude/me")[0], "skip")
        self.assertEqual(pb.decide("claude/x", "199", None, {199: TIP})[0], "skip")


class TestMain(unittest.TestCase):
    def _run(self, argv):
        calls = []

        def fake_git(*args):
            calls.append(args)
            return mock.Mock(returncode=0, stderr="", stdout="")

        with mock.patch.object(pb, "_git", fake_git), mock.patch.object(pb, "remote_state", return_value=({}, {})):
            code = pb.main(argv)
        return code, calls

    def test_a_dry_run_never_pushes_tags_or_deletes(self):
        code, calls = self._run([])
        self.assertEqual(code, 0)
        self.assertFalse([c for c in calls if c[0] in ("push", "tag")], calls)

    def test_execute_with_every_branch_gone_from_the_remote_changes_nothing(self):
        code, calls = self._run(["--execute"])
        self.assertEqual(code, 0)
        self.assertFalse([c for c in calls if c[0] in ("push", "tag")], calls)


if __name__ == "__main__":
    unittest.main()
