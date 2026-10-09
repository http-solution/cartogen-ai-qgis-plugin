# -*- coding: utf-8 -*-
"""LoopGuard: catches stuck turns (duplicates, repeated failure, no progress) without stopping legitimate work."""
import unittest

from cartogen_ai.core.agent import loop_guard as lg


class TestDuplicates(unittest.TestCase):
    def test_the_third_identical_call_stops_but_two_do_not(self):
        g = lg.LoopGuard()
        self.assertIsNone(g.record_call("buffer_analysis", '{"a":1,"b":2}', False))
        self.assertIsNone(g.record_call("buffer_analysis", '{"b": 2, "a": 1}', False))      # same arguments, other key order
        stop = g.record_call("buffer_analysis", {"a": 1, "b": 2}, False)
        self.assertEqual(stop["reason"], "duplicate_call")

    def test_different_arguments_are_not_duplicates(self):
        g = lg.LoopGuard()
        for i in range(5):
            self.assertIsNone(g.record_call("buffer_analysis", {"distance": i}, False))

    def test_bookkeeping_tools_may_repeat(self):
        g = lg.LoopGuard()
        for _ in range(6):
            self.assertIsNone(g.record_call("update_task", {"id": "1"}, False))


class TestFailures(unittest.TestCase):
    def test_three_failures_in_a_row_of_one_tool_stop(self):
        g = lg.LoopGuard()
        g.record_call("x", {"i": 1}, True, "boom")
        g.record_call("x", {"i": 2}, True, "boom")
        self.assertEqual(g.record_call("x", {"i": 3}, True, "boom")["reason"], "repeated_failure")

    def test_a_success_resets_the_streak(self):
        g = lg.LoopGuard()
        g.record_call("x", {"i": 1}, True)
        g.record_call("x", {"i": 2}, True)
        g.record_call("x", {"i": 3}, False)
        self.assertIsNone(g.record_call("x", {"i": 4}, True))

    def test_eight_failures_across_tools_stop(self):
        g = lg.LoopGuard()
        stop = None
        for i in range(8):
            stop = g.record_call(f"tool{i}", {}, True, "e")
        self.assertEqual(stop["reason"], "repeated_failure")


class TestNoProgress(unittest.TestCase):
    def test_six_read_only_rounds_stall(self):
        g = lg.LoopGuard()
        stop = None
        for i in range(6):
            g.record_call("get_layer_extent", {"i": i}, False, operation_type="READ")
            stop = g.end_round()
        self.assertEqual(stop["reason"], "no_progress")

    def test_a_state_changing_success_resets_the_count(self):
        g = lg.LoopGuard()
        for i in range(5):
            g.record_call("get_layer_extent", {"i": i}, False, operation_type="READ")
            self.assertIsNone(g.end_round())
        g.record_call("buffer_analysis", {}, False, operation_type="CREATE")
        self.assertIsNone(g.end_round())
        for i in range(5):
            g.record_call("get_layer_extent", {"j": i}, False, operation_type="READ")
            self.assertIsNone(g.end_round())


class TestReportAndBudget(unittest.TestCase):
    def test_the_report_says_what_is_done_and_not_complete(self):
        g = lg.LoopGuard()
        g.record_call("fetch_osm_features", {}, False, operation_type="CREATE")
        g.record_call("buffer_analysis", {}, True, "no layer")
        text = g.partial_report({"reason": "repeated_failure", "detail": "`buffer_analysis` failed 3 times in a row"})
        self.assertTrue(text.startswith("[Agent stopped]"))
        self.assertIn("`fetch_osm_features`", text)
        self.assertIn("`buffer_analysis` (no layer)", text)
        self.assertIn("NOT complete", text)

    def test_budget_uses_the_observed_next_call_size(self):
        self.assertFalse(lg.budget_exceeded(100, 0))
        self.assertFalse(lg.budget_exceeded(100_000, 500_000, None))
        self.assertTrue(lg.budget_exceeded(480_000, 500_000, 27_000))
        self.assertFalse(lg.budget_exceeded(400_000, 500_000, 27_000))


if __name__ == "__main__":
    unittest.main()


class TestAgentStopsAStuckTurn(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        patcher = patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep")      # the loop paces itself after a few rounds
        patcher.start()
        self.addCleanup(patcher.stop)

    def _agent(self, calls):
        from cartogen_ai.core.agent.agent_orchestrator import CartogenAi
        agent = CartogenAi()
        agent.conversation_history = []
        seq = list(calls)

        class Client:
            model = "fake"

            def complete(self, messages, tools=None, max_tokens=None):
                name, args = seq.pop(0) if seq else ("get_layer_extent", '{"layer_name": "x"}')
                return {"message": {"role": "assistant", "content": None,
                                    "tool_calls": [{"id": "1", "function": {"name": name, "arguments": args}}]},
                        "model": "fake", "usage": {"input_tokens": 1000, "output_tokens": 10}}

        agent.client = Client()
        return agent

    def test_a_model_repeating_the_same_call_is_stopped_with_a_partial_report(self):
        agent = self._agent([])
        text = agent.run("measure it")
        self.assertTrue(text.startswith("[Agent stopped]"), text)
        self.assertIn("same arguments", text)
        self.assertIn("NOT complete", text)
        self.assertLessEqual(len(agent.get_turn_call_records()), 4)         # stopped on the third identical call, not after 20 rounds

    def test_the_guard_can_be_switched_off(self):
        agent = self._agent([])
        agent.loop_guard_enabled = False
        text = agent.run("measure it")
        self.assertIn("tool-call limit", text)

    def test_the_token_budget_checks_the_next_call_before_sending(self):
        agent = self._agent([("get_layer_extent", f'{{"layer_name": "l{i}"}}') for i in range(8)])
        agent._turn_limits = lambda: (20, 2500)         # observed 1,010 per call: two calls fit, the third (est. 1,000 more) would not
        text = agent.run("measure each layer")
        self.assertTrue(text.startswith("[Agent stopped]"), text)
        self.assertIn("token budget", text)
        self.assertEqual(len(agent.get_turn_call_records()), 2)


class TestMissingFileNudge(unittest.TestCase):
    """#231 (rc22 hand test J13): twenty calls on invented file paths."""

    def test_two_missing_file_errors_in_a_row_give_a_nudge(self):
        log = [("load_csv", True, "File not found: /data/a.csv"), ("load_csv", True, "File not found: /data/b.csv")]
        self.assertIn("Stop guessing paths", lg.missing_file_nudge(log))

    def test_one_missing_file_error_is_not_enough(self):
        self.assertIsNone(lg.missing_file_nudge([("load_csv", True, "File not found: /data/a.csv")]))

    def test_a_success_between_resets_it(self):
        log = [("load_csv", True, "File not found: a"), ("get_layers", False, ""), ("load_csv", True, "File not found: b")]
        self.assertIsNone(lg.missing_file_nudge(log))

    def test_other_errors_do_not_count(self):
        log = [("calculate_area", True, "Field x missing"), ("calculate_area", True, "Field y missing")]
        self.assertIsNone(lg.missing_file_nudge(log))
