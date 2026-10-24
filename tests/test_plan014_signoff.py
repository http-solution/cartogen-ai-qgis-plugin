"""PLAN-014 phase 3b, offline: footer lines, reviewer sign-off and the publication rule for a profile."""
import unittest

from cartogen_ai.core.agent.tools.layout_export_checks import publication_problems
from cartogen_ai.core.agent.tools.layout_style import footer_block, profile_footer_lines
from cartogen_ai.core.agent.tools.map_profiles import sign_off_line, sign_off_missing, validate_profile, validate_sign_off

FULL = {"prepared_by": "A. Analyst", "reviewed_by": "B. Reviewer", "review_date": "2026-10-20", "status": "Reviewed"}


class TestValidation(unittest.TestCase):
    def test_valid_fields_are_kept(self):
        clean, problems = validate_profile({"footer_lines": [" Contact: info@example.org "], "sign_off": FULL, "require_sign_off": True})
        self.assertEqual(problems, [])
        self.assertEqual(clean["footer_lines"], ["Contact: info@example.org"])
        self.assertEqual(clean["sign_off"]["status"], "Reviewed")

    def test_bad_footer_lines_are_refused(self):
        for bad in ([], ["a", "b", "c", "d"], ["x" * 121], ["two\nlines"], [""], "text", [3]):
            _, problems = validate_profile({"footer_lines": bad})
            self.assertTrue(any("footer_lines" in p for p in problems), bad)

    def test_a_status_cannot_claim_a_review_nobody_is_named_for(self):
        for status in ("Reviewed", "Approved"):
            _, problems = validate_sign_off({"prepared_by": "A", "status": status})
            self.assertTrue(any("needs reviewed_by and review_date" in p for p in problems), status)
        _, problems = validate_sign_off({"reviewed_by": "B", "status": "Approved"})
        self.assertTrue(any("review_date" in p for p in problems))

    def test_dates_statuses_and_keys_are_checked(self):
        self.assertTrue(validate_sign_off({"review_date": "2026-13-01"})[1])
        self.assertTrue(validate_sign_off({"status": "Done"})[1])
        self.assertTrue(validate_sign_off({"signature": "x"})[1])
        self.assertTrue(validate_sign_off({})[1])
        self.assertEqual(validate_sign_off({"status": "draft"})[0], {"status": "Draft"})

    def test_require_sign_off_must_be_a_boolean(self):
        self.assertTrue(validate_profile({"require_sign_off": "yes"})[1])


class TestLine(unittest.TestCase):
    def test_full_sign_off_line(self):
        self.assertEqual(sign_off_line(FULL), "Prepared by A. Analyst | Reviewed by B. Reviewer on 2026-10-20 | Status: Reviewed")

    def test_without_a_reviewer_the_status_is_always_draft_not_reviewed(self):
        self.assertEqual(sign_off_line({"prepared_by": "A. Analyst"}), "Prepared by A. Analyst | Status: Draft - not reviewed")
        self.assertEqual(sign_off_line({"status": "Draft"}), "Status: Draft - not reviewed")

    def test_no_sign_off_adds_nothing(self):
        self.assertEqual(sign_off_line(None), "")
        self.assertEqual(profile_footer_lines({}), [])

    def test_lines_go_before_the_disclaimer(self):
        extra = profile_footer_lines({"footer_lines": ["Contact X"], "sign_off": {"prepared_by": "A"}})
        text = footer_block("Note", [], "Sources: s", "Disclaimer.", "Credits: c", extra)
        self.assertEqual(text.split("\n")[-3:], ["Contact X", "Prepared by A | Status: Draft - not reviewed", "Disclaimer."])


class TestPublicationRule(unittest.TestCase):
    def test_required_sign_off_is_missing_until_named_dated_and_reviewed(self):
        self.assertFalse(sign_off_missing({}))                                              # not required: never a problem
        self.assertTrue(sign_off_missing({"require_sign_off": True}))
        self.assertTrue(sign_off_missing({"require_sign_off": True, "sign_off": {"prepared_by": "A"}}))
        self.assertTrue(sign_off_missing({"require_sign_off": True, "sign_off": {**FULL, "status": "Draft"}}))
        self.assertFalse(sign_off_missing({"require_sign_off": True, "sign_off": FULL}))
        self.assertFalse(sign_off_missing({"require_sign_off": True, "sign_off": {**FULL, "status": "Approved"}}))

    def test_it_joins_the_publication_problems_only_when_missing(self):
        self.assertEqual(publication_problems([], [], False), [])
        problems = publication_problems([], [], True)
        self.assertEqual(len(problems), 1)
        self.assertIn("sign-off", problems[0])


if __name__ == "__main__":
    unittest.main()
