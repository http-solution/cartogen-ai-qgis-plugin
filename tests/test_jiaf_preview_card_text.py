"""DEF-35 (round-3 smoke row D3): the JIAF write confirmation card showed only the description and the code; the statement, the open validation items
and the empty-severity warning were in the payload but not on the card, which shows `rationale`."""
import unittest

from cartogen_ai.core.agent.tools.jiaf_engine import preview_card_text

BLOCKERS = {"claim": "x", "blockers": [{"id": "flag_formulas", "text": "long text"}, {"id": "owner_closure", "text": "more long text"}]}


class TestPreviewCardText(unittest.TestCase):
    def test_the_card_carries_the_statement_the_open_items_and_the_empty_severity(self):
        text = preview_card_text("Write fields.", "PRELIMINARY, not endorsed by OCHA.", BLOCKERS, 2, 3)
        self.assertIn("Write fields.", text)
        self.assertIn("not endorsed by OCHA", text)
        self.assertIn("flag_formulas, owner_closure", text)
        self.assertIn("jf_pre_sev will be EMPTY for 2 of 3 areas", text)

    def test_no_empty_severity_line_when_every_area_has_one(self):
        self.assertNotIn("EMPTY", preview_card_text("d", "s", BLOCKERS, 0, 3))

    def test_missing_or_odd_blockers_do_not_break_the_card(self):
        for blockers in (None, {}, {"blockers": ["not a dict"]}, {"blockers": [{"text": "no id"}]}):
            text = preview_card_text("d", "s", blockers, 0, 3)
            self.assertNotIn("Validation items", text)
            self.assertIn("Standing statement: s", text)

    def test_the_long_blocker_texts_are_not_pasted_on_the_card(self):
        self.assertNotIn("long text", preview_card_text("d", "s", BLOCKERS, 0, 3))


if __name__ == "__main__":
    unittest.main()
