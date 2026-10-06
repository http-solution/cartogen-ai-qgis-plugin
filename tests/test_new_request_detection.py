# -*- coding: utf-8 -*-
"""A fresh full request typed while a question is open is not an answer to it (rc15/rc17 hand tests, 2026-10-06)."""
import unittest

from cartogen_ai.core.ui.reply_vocab import is_new_request


class TestIsNewRequest(unittest.TestCase):
    def test_short_answers_are_answers(self):
        for reply in ("health clinics", "Synthetic humanitarian supply hubs", "admin2", "30 minutes", "the whole country", "EPSG:3857",
                      "yes", "Hub_A"):
            self.assertFalse(is_new_request(reply), reply)

    def test_a_question_back_is_not_a_new_request(self):
        self.assertFalse(is_new_request("which one do you mean?"))

    def test_full_requests_from_the_reports_are_new(self):
        for request in (
            "Calculate a severity index for the three polygons in smoke_admin using its numeric population and need fields.",
            "Create a print layout titled Smoke Test Layout for the current map view and export it as a PDF.",
            "Use optimal_hub_siting to rank the hubs",
            "Export smoke_points to CSV at outputs/smoke_points.csv",
        ):
            self.assertTrue(is_new_request(request), request)

    def test_a_long_descriptive_answer_without_an_action_word_is_still_an_answer(self):
        self.assertFalse(is_new_request("the clinics and hospitals inside the Sanaa governorate boundary only"))

    def test_empty_is_not_new(self):
        self.assertFalse(is_new_request(""))
        self.assertFalse(is_new_request(None))


if __name__ == "__main__":
    unittest.main()
