# -*- coding: utf-8 -*-
"""A multi-step request resumes once after a confirmed step (rc15/rc17 hand tests, D05)."""
import unittest

from cartogen_ai.core.ui import reply_vocab as rv


class TestFollowupDetection(unittest.TestCase):
    def test_the_reported_severity_request_has_a_followup(self):
        req = ("Calculate a severity index for the three polygons in smoke_admin using its numeric population and need fields, "
               "write the score to severity_rc17, and then style smoke_admin by that field.")
        self.assertTrue(rv.has_followup_steps(req))

    def test_a_single_step_request_has_none(self):
        self.assertFalse(rv.has_followup_steps("Remove the layer smoke_points_buffer_500"))
        self.assertFalse(rv.has_followup_steps(""))
        self.assertFalse(rv.has_followup_steps(None))

    def test_a_sequence_word_is_enough(self):
        self.assertTrue(rv.has_followup_steps("fix the field then check it"))

    def test_questions_do_not_count_as_two_steps(self):
        self.assertFalse(rv.has_followup_steps("how many points are there and what is the area"))


class TestContinuationPrompt(unittest.TestCase):
    def test_it_is_marked_names_the_step_and_carries_the_original_request(self):
        text = rv.continuation_prompt("write it, then style it", "calculate_severity_index", "field written")
        self.assertTrue(text.startswith(rv.CONTINUATION_MARKER))
        self.assertIn("calculate_severity_index", text)
        self.assertIn("Do not repeat it", text)
        self.assertTrue(text.endswith("write it, then style it"))

    def test_the_budget_is_small(self):
        self.assertLessEqual(rv.MAX_CONTINUATIONS, 3)


if __name__ == "__main__":
    unittest.main()
