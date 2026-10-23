"""Every file in docs/plans/ named PLAN-*.md follows the template of docs/plans/README.md, so a plan can always be read the same way."""
import re
import unittest
from pathlib import Path

PLANS = sorted((Path(__file__).resolve().parents[1] / "docs" / "plans").glob("PLAN-*.md"))
HEADINGS = ("## Goal", "## Scope", "## Acceptance", "## Guard tests", "## Rollback", "## Status log")
STATUSES = ("planned", "in progress", "done", "abandoned")


class TestPlans(unittest.TestCase):
    def test_there_is_at_least_one_plan(self):
        self.assertTrue(PLANS)

    def test_every_plan_has_the_template_headings_in_order_and_a_status(self):
        for path in PLANS:
            text = path.read_text(encoding="utf-8")
            positions = [text.find(h) for h in HEADINGS]
            self.assertTrue(all(p >= 0 for p in positions), f"{path.name}: missing heading")
            self.assertEqual(positions, sorted(positions), f"{path.name}: headings out of order")
            status = re.search(r"^Status: (.+)$", text, re.M)
            self.assertIsNotNone(status, path.name)
            self.assertIn(status.group(1).strip(), STATUSES, path.name)

    def test_the_status_log_has_a_dated_line(self):
        for path in PLANS:
            log = path.read_text(encoding="utf-8").split("## Status log")[1]
            self.assertRegex(log, r"- 20\d\d-\d\d-\d\d:", path.name)


if __name__ == "__main__":
    unittest.main()
