# -*- coding: utf-8 -*-
"""Per-call measurement (call_metrics): measured tokens are never guessed, estimates are labelled, nothing raises."""
import unittest

from cartogen_ai.core.agent import call_metrics as cm


def _tools(*names):
    return [{"type": "function", "function": {"name": n, "description": "d" * 40, "parameters": {}}} for n in names]


class TestBreakdown(unittest.TestCase):
    def test_splits_system_tools_history_and_user(self):
        messages = [{"role": "system", "content": "s" * 400}, {"role": "user", "content": "old"},
                    {"role": "assistant", "content": "a" * 80}, {"role": "user", "content": "u" * 40}]
        b = cm.prompt_breakdown(messages, _tools("a", "b"))
        self.assertEqual(b["est_system_tokens"], 100)
        self.assertEqual(b["est_user_tokens"], 10)
        self.assertEqual(b["tool_count"], 2)
        self.assertGreater(b["est_history_tokens"], 0)
        self.assertGreater(b["est_tools_tokens"], 0)

    def test_empty_inputs_do_not_raise(self):
        self.assertEqual(cm.prompt_breakdown(None, None)["tool_count"], 0)
        self.assertEqual(cm.estimate_tokens(object()) >= 0, True)


class TestRecords(unittest.TestCase):
    def test_measured_fields_stay_none_when_the_provider_reports_nothing(self):
        record = cm.new_record(1, 0, "m", "P", _tools("a"), [], 0.0)
        cm.finish_record(record, None, 1.5, tool_calls=2)
        self.assertIsNone(record["input_tokens"])
        self.assertEqual(record["latency_ms"], 1500)
        self.assertEqual(record["tool_calls"], 2)

    def test_reported_usage_is_copied_not_estimated(self):
        record = cm.new_record(1, 0, "m", "P", [], [], 0.0)
        cm.finish_record(record, {"input_tokens": 27000, "cached_tokens": 12000, "output_tokens": 300}, 0.2)
        self.assertEqual((record["input_tokens"], record["cached_tokens"], record["output_tokens"]), (27000, 12000, 300))


class TestTurnSummary(unittest.TestCase):
    def _rec(self, i, inp, cached, out, est_fixed=(9000, 16000)):
        r = {"turn_id": 1, "call_index": i, "input_tokens": inp, "cached_tokens": cached, "output_tokens": out, "latency_ms": 100,
             "est_system_tokens": est_fixed[0], "est_tools_tokens": est_fixed[1]}
        return r

    def test_sums_split_fresh_from_cached_and_say_which_calls_reported_nothing(self):
        records = [self._rec(0, 26000, 0, 200), self._rec(1, 28000, 20000, 100), self._rec(2, None, None, None)]
        s = cm.turn_summary(records)
        self.assertEqual((s["calls"], s["calls_with_usage"], s["calls_without_usage"]), (3, 2, 1))
        self.assertEqual((s["input_tokens"], s["cached_tokens"], s["fresh_input_tokens"], s["output_tokens"]), (54000, 20000, 34000, 300))
        self.assertEqual(s["avg_input_per_call"], 27000)
        self.assertEqual(s["est_fixed_tokens_per_call"], 25000)

    def test_next_call_estimate_is_the_last_measurement_or_none(self):
        self.assertIsNone(cm.next_call_estimate([]))
        self.assertIsNone(cm.next_call_estimate([self._rec(0, None, None, None)]))
        self.assertEqual(cm.next_call_estimate([self._rec(0, 100, 0, 1), self._rec(1, 250, 0, 1)]), 250)

    def test_usage_line_is_observed_only(self):
        self.assertIsNone(cm.turn_usage_line([]))
        self.assertIsNone(cm.turn_usage_line([self._rec(0, None, None, None)]))
        line = cm.turn_usage_line([self._rec(0, 26000, 1000, 200), self._rec(1, None, None, None)])
        self.assertIn("26,000 input (1,000 cached)", line)
        self.assertIn("1 call(s) reported no usage", line)
        self.assertNotIn("26k", line)


class TestCallLog(unittest.TestCase):
    def test_turn_ids_and_filtering_and_bound(self):
        log = cm.CallLog(maxlen=3)
        a, b = log.next_turn_id(), log.next_turn_id()
        for i in range(5):
            log.add({"turn_id": a if i < 2 else b, "call_index": i})
        self.assertEqual(len(log.records), 3)
        self.assertEqual([r["call_index"] for r in log.turn_records(b)], [2, 3, 4])


if __name__ == "__main__":
    unittest.main()


class TestAgentRecordsEveryCall(unittest.TestCase):
    def test_a_turn_with_one_tool_round_records_two_calls_with_provider_usage(self):
        from cartogen_ai.core.agent.agent_orchestrator import CartogenAi
        agent = CartogenAi()
        agent.conversation_history = []
        replies = [
            {"message": {"role": "assistant", "content": None,
                         "tool_calls": [{"id": "1", "type": "function", "function": {"name": "get_layers", "arguments": "{}"}}]},
             "model": "fake-model", "usage": {"input_tokens": 26000, "cached_tokens": 0, "output_tokens": 40}},
            {"message": {"role": "assistant", "content": "done", "tool_calls": None},
             "model": "fake-model", "usage": {"input_tokens": 26500, "cached_tokens": 20000, "output_tokens": 10}},
        ]

        class Client:
            model = "fake-model"

            def complete(self, messages, tools=None, max_tokens=None):
                return replies.pop(0)

        agent.client = Client()
        agent.run("list the layers")
        records = agent.get_turn_call_records()
        self.assertEqual([r["call_index"] for r in records], [0, 1])
        self.assertEqual(records[0]["tool_calls"], 1)
        self.assertEqual(records[0]["input_tokens"], 26000)
        self.assertGreater(records[0]["tool_count"], 0)
        self.assertEqual(records[0]["model"], "fake-model")
        line = agent.get_turn_usage_detail_text()
        self.assertIn("52,500 input (20,000 cached)", line)
