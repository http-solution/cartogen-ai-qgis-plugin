"""The per-request token budget counts cached input at 10 percent (BUD-1).

Why: the owner's Taiz run reported 439,564 input tokens over 16 calls, 55 percent of it served from the provider's cache, and stopped at
the 450,000 budget although cached tokens cost a fraction of fresh ones. The budget is a cost guardrail, so it should follow spend."""
import unittest

from cartogen_ai.core.agent import call_metrics
from cartogen_ai.core.agent.usage_tracker import UsageTracker


class TestBudgetCachedTokens(unittest.TestCase):
    def _turn(self, *calls):
        tracker = UsageTracker()
        tracker.begin_turn()
        for usage in calls:
            tracker.accumulate(usage)
        return tracker

    def test_cached_input_counts_at_ten_percent(self):
        tracker = self._turn({"input_tokens": 20_000, "cached_tokens": 15_000, "output_tokens": 100})
        self.assertEqual(tracker.turn_tokens(), 20_100)          # what the user is shown stays the full size
        self.assertEqual(tracker.turn_budget_tokens(), 5_000 + 1_500 + 100)

    def test_no_cache_figure_counts_in_full(self):
        tracker = self._turn({"input_tokens": 20_000, "output_tokens": 100})
        self.assertEqual(tracker.turn_budget_tokens(), 20_100)

    def test_only_this_turn_counts(self):
        tracker = UsageTracker()
        tracker.accumulate({"input_tokens": 50_000, "cached_tokens": 40_000, "output_tokens": 10})
        tracker.begin_turn()
        tracker.accumulate({"input_tokens": 1_000, "cached_tokens": 0, "output_tokens": 0})
        self.assertEqual(tracker.turn_budget_tokens(), 1_000)

    def test_cached_cannot_exceed_input(self):
        tracker = self._turn({"input_tokens": 1_000, "cached_tokens": 5_000, "output_tokens": 0})
        self.assertEqual(tracker.turn_budget_tokens(), 100)

    def test_never_begun_is_zero(self):
        self.assertEqual(UsageTracker().turn_budget_tokens(), 0)

    def test_next_call_estimate_follows_the_same_rule(self):
        records = [{"input_tokens": 26_000, "cached_tokens": 23_000}]
        self.assertEqual(call_metrics.next_call_budget_estimate(records), 3_000 + 2_300)
        self.assertEqual(call_metrics.next_call_budget_estimate([{"input_tokens": 26_000}]), 26_000)
        self.assertIsNone(call_metrics.next_call_budget_estimate([]))

    def test_the_taiz_run_would_not_have_hit_the_budget(self):
        """16 calls of about 27,000 input with 55 percent cached: 439,564 counted in full, about 214,000 at 10 percent."""
        call = {"input_tokens": 27_473, "cached_tokens": 15_110, "output_tokens": 50}
        tracker = self._turn(*([call] * 16))
        self.assertGreater(tracker.turn_tokens(), 430_000)
        self.assertLess(tracker.turn_budget_tokens(), 250_000)


if __name__ == "__main__":
    unittest.main()
