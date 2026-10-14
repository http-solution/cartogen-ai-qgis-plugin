"""No tool, parameter or required flag may disappear without a deliberate snapshot update.

Why (owner, 2026-10-14: "if you optimize something you have to make sure all previous progress still working"): the rc23 router
regression removed no tool, so nothing noticed. This pins the other half: the tool list and each tool's parameter names. Adding is
free (the test only reports it); removing or renaming a tool or parameter, or making an optional parameter required, fails.
After a deliberate removal run tools/snapshot_tool_schema.py and say why in the PR."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from snapshot_tool_schema import current_snapshot  # noqa: E402

with open(os.path.join(ROOT, "tests", "fixtures", "tool_schema_snapshot.json"), encoding="utf-8") as _fh:
    PINNED = json.load(_fh)


class TestToolSchemaSnapshot(unittest.TestCase):
    def setUp(self):
        self.now = current_snapshot()

    def test_no_tool_was_removed_or_renamed(self):
        self.assertEqual(sorted(set(PINNED) - set(self.now)), [])

    def test_no_parameter_was_removed_or_renamed(self):
        lost = {t: sorted(set(p["properties"]) - set(self.now[t]["properties"]))
                for t, p in PINNED.items() if t in self.now}
        self.assertEqual({t: v for t, v in lost.items() if v}, {})

    def test_no_optional_parameter_became_required(self):
        newly = {t: sorted(set(self.now[t]["required"]) - set(p["required"]))
                 for t, p in PINNED.items() if t in self.now}
        self.assertEqual({t: v for t, v in newly.items() if v}, {})

    def test_the_tool_count_never_drops(self):
        self.assertGreaterEqual(len(self.now), len(PINNED))


if __name__ == "__main__":
    unittest.main()
