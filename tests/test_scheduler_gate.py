"""One heavy job at a time (processing-cost audit 2026-10-12): a recurring-workflow tick is skipped while another tick or a chat request is
running. No Qt needed: _guarded_tick holds the logic and the timer only calls it."""
import unittest

from cartogen_ai.core.agent import cancel_signal
from cartogen_ai.core.agent.scheduler import WorkflowScheduler


class TestTickGate(unittest.TestCase):
    def setUp(self):
        self.s = WorkflowScheduler()
        self.meta = {"run_count": 0, "skipped": 0}
        self.addCleanup(lambda: cancel_signal.end(None))

    def test_an_idle_tick_runs_and_counts(self):
        ran = []
        self.assertTrue(self.s._guarded_tick("p", ran.append, self.meta))
        self.assertEqual((ran, self.meta["run_count"], self.meta["skipped"]), (["p"], 1, 0))
        self.assertEqual(self.s._running, set())

    def test_a_tick_that_fires_inside_another_is_skipped_not_run(self):
        inner = []

        def outer(_name):
            inner.append(self.s._guarded_tick("q", lambda n: inner.append("ran"), {"run_count": 0, "skipped": 0}))
        self.assertTrue(self.s._guarded_tick("p", outer, self.meta))
        self.assertEqual(inner, [False])

    def test_a_tick_is_skipped_while_a_chat_request_is_running(self):
        previous = cancel_signal.begin(lambda: False, None)
        try:
            ran = []
            self.assertFalse(self.s._guarded_tick("p", ran.append, self.meta))
            self.assertEqual((ran, self.meta["run_count"], self.meta["skipped"]), ([], 0, 1))
        finally:
            cancel_signal.end(previous)
        self.assertTrue(self.s._guarded_tick("p", lambda n: None, self.meta))

    def test_the_busy_flag_is_released_when_a_tick_raises(self):
        def boom(_name):
            raise RuntimeError("tool failed")
        with self.assertRaises(RuntimeError):
            self.s._guarded_tick("p", boom, self.meta)
        self.assertEqual(self.s._running, set())
        self.assertTrue(self.s._guarded_tick("p", lambda n: None, self.meta))


class TestRequestActive(unittest.TestCase):
    def test_nested_requests_keep_it_active_until_the_outer_one_ends(self):
        self.assertFalse(cancel_signal.request_active())
        outer = cancel_signal.begin(lambda: False, None)
        inner = cancel_signal.begin(lambda: False, None)
        self.assertTrue(cancel_signal.request_active())
        cancel_signal.end(inner)
        self.assertTrue(cancel_signal.request_active())
        cancel_signal.end(outer)
        self.assertFalse(cancel_signal.request_active())

    def test_a_request_that_never_ended_stops_blocking_after_the_age_limit(self):
        previous = cancel_signal.begin(lambda: False, None)
        try:
            self.assertTrue(cancel_signal.request_active(max_age_s=60))
            self.assertFalse(cancel_signal.request_active(max_age_s=0))
        finally:
            cancel_signal.end(previous)


if __name__ == "__main__":
    unittest.main()
