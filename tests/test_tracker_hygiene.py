"""Master list HY-2: docs/IMPLEMENTATION_TRACKER.md had six section numbers used twice (1.19 to 1.24: two unrelated sets, the later one appended after the 'How to keep this
current' heading) and opened with a 2026-09-20 snapshot (177 tools, 1,958 tests) as if it were current. This keeps both fixed. Offline, reads the file only."""
import collections
import re
import unittest
from pathlib import Path

TRACKER = Path(__file__).resolve().parents[1] / "docs" / "IMPLEMENTATION_TRACKER.md"


class TestTheTracker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines = TRACKER.read_text(encoding="utf-8").split("\n")

    def test_no_numbered_section_heading_is_used_twice(self):
        seen = collections.defaultdict(list)
        for number, line in enumerate(self.lines, 1):
            match = re.match(r"^#{2,4}\s+(?:~~)?(\d+(?:\.\d+)*[a-z]?)[\s.:]", line)
            if match:
                seen[match.group(1)].append(number)
        self.assertEqual({k: v for k, v in seen.items() if len(v) > 1}, {})

    def test_it_opens_with_a_current_status_block_that_points_to_the_living_records(self):
        head = "\n".join(self.lines[:30])
        self.assertIn("Current status (", head)
        for pointer in ("MASTER_TASK_LIST", "FEATURE_LEDGER.json", "LIVE_RESULTS.json"):
            self.assertIn(pointer, head)

    def test_the_old_opening_is_marked_as_history_not_current(self):
        self.assertIn("history", "\n".join(self.lines[:30]).lower())

    def test_the_two_notes_this_sweep_added_are_there(self):
        text = "\n".join(self.lines)
        self.assertIn("Update 2026-11-05 (AR-3)", text)
        self.assertIn("Update 2026-11-05 (HU-3)", text)


class TestTheBugTracker(unittest.TestCase):
    def test_its_open_bugs_section_points_to_where_open_defects_are_tracked_now(self):
        text = (TRACKER.parent / "BUG_TRACKER.md").read_text(encoding="utf-8")
        section = text[text.index("## Open bugs"):text.index("## Known non-bugs")]
        self.assertIn("Update 2026-11-05", section)
        self.assertIn("MASTER_TASK_LIST", section)
        self.assertIn("DEF-", section)


if __name__ == "__main__":
    unittest.main()
