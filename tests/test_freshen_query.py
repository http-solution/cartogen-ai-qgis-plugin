# -*- coding: utf-8 -*-
"""Web searches for the latest/current thing carry today's date (rc17 hand test B5, 2026-10-06)."""
import datetime
import unittest

from cartogen_ai.infrastructure.providers.base import freshen_query


class TestFreshenQuery(unittest.TestCase):
    DAY = datetime.date(2026, 10, 6)

    def test_a_recency_query_gets_the_date_and_a_freshness_instruction(self):
        out = freshen_query("latest stable QGIS release announcement", self.DAY)
        self.assertTrue(out.startswith("latest stable QGIS release announcement"))
        self.assertIn("2026-10-06", out)
        self.assertIn("publication date", out)

    def test_a_query_without_a_recency_word_is_unchanged(self):
        self.assertEqual(freshen_query("history of the Sanaa airport", self.DAY), "history of the Sanaa airport")

    def test_common_words_that_do_not_ask_for_fresh_data_do_not_trigger_it(self):
        # Code review of the first version: "current administrative boundary" is a definition, not a request for news.
        for query in ("population of the current administrative boundary of Sanaa", "recent history of the airport",
                      "what is now part of Taiz governorate"):
            self.assertEqual(freshen_query(query, self.DAY), query)
        self.assertIn("2026-10-06", freshen_query("most recent UN report on Yemen", self.DAY))

    def test_none_and_empty_are_safe(self):
        self.assertEqual(freshen_query(None, self.DAY), "")
        self.assertEqual(freshen_query("", self.DAY), "")

    def test_the_word_must_stand_alone(self):
        self.assertEqual(freshen_query("nowhere to be found", self.DAY), "nowhere to be found")


if __name__ == "__main__":
    unittest.main()
