"""GitHub #380 (rc48 hand test): a plain request that one approved Processing algorithm answers must not be steered by a mapping task.

Before: 34 of the 385 plain prompts matched a task at the confident score ("Sort the districts by population, biggest first" -> "Map population
distribution"), and the injected plan sent the model to a WorldPop fetch. After: 7. The same rule must not take the directive from the task
library's own wording: measured on 2026-10-24 over the 792 register titles, 587 matched before and 582 after (5 lost, listed below). The two numbers
are ratcheted so the rule cannot drift either way unnoticed."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import plain_prompts_grass  # noqa: E402
import plain_prompts_raster  # noqa: E402
import plain_prompts_vector  # noqa: E402

from cartogen_ai.core.agent import task_register  # noqa: E402
from cartogen_ai.core.agent.algorithm_topics import algorithm_outranks_task  # noqa: E402
from cartogen_ai.core.agent.task_matcher import classify  # noqa: E402

PROMPTS = {**plain_prompts_vector.PROMPTS, **plain_prompts_raster.PROMPTS, **plain_prompts_grass.PROMPTS}


def _confident(query):
    verdict = classify(query)
    return bool(verdict["best"] and not verdict["ambiguous"])


class AlgorithmBeatsTask(unittest.TestCase):
    def test_the_requests_the_rc48_run_hijacked_get_no_task_directive(self):
        for algorithm in ("native:orderbyexpression", "native:extractbyexpression", "native:renametablefield", "native:joinbylocationsummary",
                          "native:saveselectedfeatures", "grass:r.lake", "grass:r.mask.rast", "native:forcerhr"):
            self.assertFalse(_confident(PROMPTS[algorithm]), f"{algorithm}: {PROMPTS[algorithm]}")

    def test_plain_prompts_that_still_match_a_task_stay_a_small_minority(self):
        matched = [k for k, p in PROMPTS.items() if _confident(p)]
        self.assertLessEqual(len(matched), 10, matched)

    def test_the_task_librarys_own_wording_keeps_its_task(self):
        titles = [e["text"] for e in task_register.load()]
        self.assertGreaterEqual(sum(_confident(t) for t in titles), 575)
        for title in ("Map newly displaced populations", "Map project locations", "Track project progress", "Determine areas reachable within a given time"):
            self.assertTrue(_confident(title), title)

    def test_a_task_that_lists_the_algorithm_keeps_its_directive(self):
        # 16.05 lists native:detectvectorchanges, which is also the topic index's best fit (18.3): no stand-down
        self.assertFalse(algorithm_outranks_task("Detect changes over time", "16.05"))
        # 3.01 does not list native:orderbyexpression, so the same strong hit does stand it down
        self.assertTrue(algorithm_outranks_task("Sort the districts by population, biggest first.", "3.01"))
        # a leading mapping verb keeps the task even when an unlisted algorithm scores well
        self.assertFalse(algorithm_outranks_task("Map project locations", "1.01"))


if __name__ == "__main__":
    unittest.main()
