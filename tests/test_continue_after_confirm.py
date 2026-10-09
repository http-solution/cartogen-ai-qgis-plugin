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

    def test_ordinary_requests_with_show_map_list_or_find_do_not_trigger_a_followup(self):
        for request in ("Show me a map of schools", "list the districts and find the biggest one", "map the health facilities"):
            self.assertFalse(rv.has_followup_steps(request), request)


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


class TestDisplayStepAfterAWrite(unittest.TestCase):
    """rc22 smoke T2/V4/J4: a confirmed data write whose request also asked to show the result must resume."""

    def test_show_the_ranking_after_a_confirmed_write_resumes(self):
        from cartogen_ai.core.agent import tool_operations as ops
        write_tools = [n for n, op in ops.TOOL_OPERATION_TYPES.items()
                       if op in (ops.CREATE, ops.MODIFY) and not any(p in n for p in rv._PRESENTATION_TOOL_PARTS)]
        self.assertTrue(write_tools)
        self.assertTrue(rv.has_followup_steps("Show the ranking on the map", write_tools[0]))

    def test_a_presentation_tool_never_triggers_it(self):
        self.assertFalse(rv.has_followup_steps("Show the ranking on the map", "apply_graduated_style"))

    def test_a_read_tool_or_no_tool_keeps_the_old_behaviour(self):
        self.assertFalse(rv.has_followup_steps("Show me a map of schools", "get_layers"))
        self.assertFalse(rv.has_followup_steps("Show me a map of schools"))

    def test_a_request_without_display_intent_does_not(self):
        self.assertFalse(rv.has_followup_steps("Remove the layer smoke_points", "remove_layer"))
