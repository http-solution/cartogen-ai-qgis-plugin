"""Master list AR-3: does task_matcher's keyword normalisation (by the TASK's keyword count) favour tasks with short keyword lists? Measured on 2026-11-05 by
asking every task's own title for its task (792 tasks): 613 find their own task, 165 find none ("too short to be a request": the fragment guard, by design),
13 lose to a task whose keyword set is IDENTICAL (indistinguishable by keywords), 1 loses to a task with fewer strong keywords, none to one with more. So there is
no measurable short-definition bias on the register's own wording; the live case that prompted the note (25c.01 over 7.23, 2026-09-19) was fixed by a targeted
re-rank, and the shared formula was deliberately not changed (wide blast radius, see the comment above _ACCESS_TIME_LANGUAGE).
This pins the measurement so a later change to the scoring cannot introduce the bias unnoticed. Offline, no QGIS."""
import collections
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cartogen_ai.core.agent import task_matcher as tm   # noqa: E402


def strong(task):
    return len(set(task["kw"]) - tm._REGISTER_STOP)


class TestNoLengthBias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = tm.reg.load()
        cls.outcome = collections.Counter()
        cls.no_match_reasons = collections.Counter()
        cls.identical_keyword_ties = 0
        for task in cls.tasks:
            verdict = tm.classify(task["text"])
            best = verdict.get("best")
            if not best:
                cls.outcome["none"] += 1
                cls.no_match_reasons[verdict.get("reason")] += 1
            elif best["id"] == task["id"]:
                cls.outcome["own"] += 1
            else:
                difference = strong(best) - strong(task)
                cls.outcome["more" if difference > 0 else "equal" if difference == 0 else "fewer"] += 1
                cls.identical_keyword_ties += set(best["kw"]) == set(task["kw"])

    def test_the_register_is_the_size_that_was_measured(self):
        self.assertGreaterEqual(len(self.tasks), 792)

    def test_almost_no_task_loses_to_a_task_with_fewer_strong_keywords(self):
        self.assertLessEqual(self.outcome["fewer"], 3, dict(self.outcome))

    def test_no_task_loses_to_a_task_with_more_strong_keywords_either(self):
        self.assertEqual(self.outcome["more"], 0, dict(self.outcome))

    def test_the_only_other_losses_are_ties_on_identical_keyword_sets(self):
        self.assertEqual(self.outcome["equal"], self.identical_keyword_ties, dict(self.outcome))

    def test_a_title_that_finds_no_task_is_only_ever_the_fragment_guard(self):
        self.assertEqual(set(self.no_match_reasons), {"too short to be a request"}, dict(self.no_match_reasons))

    def test_most_titles_find_their_own_task(self):
        self.assertGreaterEqual(self.outcome["own"] / len(self.tasks), 0.75, dict(self.outcome))


if __name__ == "__main__":
    unittest.main()
