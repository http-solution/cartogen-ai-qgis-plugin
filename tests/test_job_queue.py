# -*- coding: utf-8 -*-
"""Job splitting is conservative: only whole requests at explicit boundaries become jobs."""
import unittest

from cartogen_ai.core.agent import job_queue as jq
from tests.fixtures.humanitarian_scenarios import SCEN

FIVE = list(SCEN.values())


class TestSplit(unittest.TestCase):
    def test_five_paragraphs_become_five_jobs(self):
        jobs = jq.split_jobs("\n\n".join(FIVE))
        self.assertEqual(jobs, FIVE)

    def test_numbered_blocks_that_are_each_a_whole_request_split(self):
        text = "\n".join(f"{i}. {s}" for i, s in enumerate(FIVE, 1))
        jobs = jq.split_jobs(text)
        self.assertEqual(len(jobs), 5)
        self.assertTrue(jobs[0].startswith("I need an urgent health access"))

    def test_scenario_headings_split_too(self):
        text = "\n".join(f"Scenario {i}: {s}" for i, s in enumerate(FIVE[:3], 1))
        self.assertEqual(len(jq.split_jobs(text)), 3)

    def test_short_numbered_steps_of_one_analysis_do_not_split(self):
        steps = ("Please do this: 1. fetch OpenStreetMap hospitals for Marib 2. buffer them by 1.2 km "
                 "3. report the total area 4. export the result as GeoPackage for the team to review tomorrow morning")
        self.assertIsNone(jq.split_jobs(steps))
        multiline = "1. fetch OpenStreetMap hospitals\n2. buffer them by 1.2 km\n3. report the area in square kilometers"
        self.assertIsNone(jq.split_jobs(multiline))

    def test_one_long_request_about_several_places_does_not_split(self):
        one = ("Fetch OpenStreetMap hospitals for Marib, Taizz and Aden, buffer each by 1.2 km, dissolve the buffers per city and "
               "report the total area in square kilometers for all three cities together in one table I can send to the cluster lead.")
        self.assertIsNone(jq.split_jobs(one))

    def test_a_single_scenario_is_not_a_queue(self):
        self.assertIsNone(jq.split_jobs(FIVE[0]))

    def test_short_or_empty_input(self):
        self.assertIsNone(jq.split_jobs(""))
        self.assertIsNone(jq.split_jobs(None))
        self.assertIsNone(jq.split_jobs("yes\n\nno"))


class TestQueue(unittest.TestCase):
    def test_jobs_run_one_at_a_time_with_their_own_status(self):
        q = jq.JobQueue(["a", "b", "c"])
        self.assertEqual(q.next_pending(), (0, "a"))
        q.finish_current(True)
        self.assertEqual(q.next_pending(), (1, "b"))
        q.finish_current(False)
        self.assertEqual(q.pending_count(), 1)
        self.assertEqual(q.summary(), "1 done, 1 failed, 1 not run, of 3")
        self.assertEqual(q.next_pending(), (2, "c"))
        q.finish_current(True)
        self.assertIsNone(q.next_pending())

    def test_keep_only_first(self):
        q = jq.JobQueue(["a", "b"])
        q.keep_only_first()
        self.assertEqual(len(q), 1)

    def test_preview_numbers_and_truncates(self):
        text = jq.preview_text(["x" * 200, "short"])
        self.assertTrue(text.startswith("1. " + "x" * 90 + "..."))
        self.assertIn("\n2. short", text)


if __name__ == "__main__":
    unittest.main()
