"""Direct tests for core/agent/history_manager.py.

PLAN-040 / audit finding 11: this module gates every request (the model sees whatever it keeps) yet no test named it; it was only
covered indirectly through test_agent_runner. These pin the behaviour so the planned orchestrator refactors cannot change it silently.
"""
import threading
import unittest

from cartogen_ai.core.agent.history_manager import HistoryManager

MARK = "[Earlier conversation digest]"


def _msg(role, text):
    return {"role": role, "content": text}


class TestTrim(unittest.TestCase):
    def test_under_the_limit_nothing_changes(self):
        hm = HistoryManager()
        hm.history = [_msg("user", "a"), _msg("assistant", "b")]
        hm.trim(5, MARK, 1000)
        self.assertEqual(len(hm.history), 2)

    def test_overflow_is_replaced_by_one_digest_line_per_dropped_message(self):
        hm = HistoryManager()
        hm.history = [_msg("user", f"m{i}") for i in range(6)]
        hm.trim(3, MARK, 1000)
        self.assertEqual(hm.history[0]["role"], "system")
        self.assertTrue(hm.history[0]["content"].startswith(MARK))
        self.assertIn("- user: m0", hm.history[0]["content"])
        self.assertIn("- user: m2", hm.history[0]["content"])
        self.assertEqual([m["content"] for m in hm.history[1:]], ["m3", "m4", "m5"])

    def test_a_second_trim_extends_the_same_digest_instead_of_stacking_another(self):
        hm = HistoryManager()
        hm.history = [_msg("user", f"m{i}") for i in range(6)]
        hm.trim(3, MARK, 1000)
        hm.append([_msg("user", "m6"), _msg("user", "m7")], 3, MARK, 1000)
        digests = [m for m in hm.history if HistoryManager.is_digest_message(m, MARK)]
        self.assertEqual(len(digests), 1)
        self.assertIn("m0", digests[0]["content"])
        self.assertIn("m4", digests[0]["content"])
        self.assertEqual(len(hm.history), 4)  # digest + 3 kept

    def test_the_digest_is_capped_keeping_the_newest_end(self):
        hm = HistoryManager()
        hm.history = [_msg("user", "x" * 90 + str(i)) for i in range(10)]
        hm.trim(2, MARK, 120)
        body = hm.history[0]["content"][len(MARK):].strip()
        self.assertLessEqual(len(body), 120)
        self.assertTrue(body.endswith("7"))  # the last dropped message (index 7) survives the cut

    def test_dropped_messages_with_no_text_do_not_create_an_empty_digest(self):
        hm = HistoryManager()
        hm.history = [_msg("tool", ""), _msg("tool", ""), _msg("user", "keep")]
        hm.trim(1, MARK, 1000)
        self.assertEqual(hm.history, [_msg("user", "keep")])


class TestSummaries(unittest.TestCase):
    def test_long_lines_are_cut_and_whitespace_collapsed(self):
        out = HistoryManager.summarize_dropped_messages([_msg("user", "a   b\n" + "z" * 200)])
        self.assertTrue(out.startswith("- user: a b z"))
        self.assertTrue(out.endswith("..."))
        self.assertLessEqual(len(out), len("- user: ") + 103)

    def test_non_dict_entries_and_non_string_content_are_tolerated(self):
        out = HistoryManager.summarize_dropped_messages(["junk", None, {"role": "tool", "content": {"a": 1}}])
        self.assertEqual(out, "- tool: {'a': 1}")

    def test_is_digest_message_needs_a_system_string_with_the_marker(self):
        self.assertTrue(HistoryManager.is_digest_message(_msg("system", MARK + "\n- x"), MARK))
        self.assertFalse(HistoryManager.is_digest_message(_msg("user", MARK), MARK))
        self.assertFalse(HistoryManager.is_digest_message(_msg("system", "other"), MARK))
        self.assertFalse(HistoryManager.is_digest_message("not a dict", MARK))
        self.assertFalse(HistoryManager.is_digest_message({"role": "system", "content": None}, MARK))


class TestSnapshotAndLocking(unittest.TestCase):
    def test_snapshot_is_a_copy(self):
        hm = HistoryManager()
        hm.append([_msg("user", "a")], 10, MARK, 100)
        snap = hm.snapshot()
        snap.append(_msg("user", "b"))
        self.assertEqual(len(hm.history), 1)

    def test_append_while_holding_the_lock_does_not_deadlock(self):
        # append() calls trim() under the same lock: it has to be re-entrant (RLock), or this hangs.
        hm = HistoryManager()
        done = []

        def work():
            with hm.lock:
                hm.append([_msg("user", "a")] * 5, 2, MARK, 100)
            done.append(True)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(5)
        self.assertEqual(done, [True])

    def test_concurrent_appends_lose_nothing(self):
        hm = HistoryManager()

        def work(n):
            for i in range(50):
                hm.append([_msg("user", f"{n}-{i}")], 10_000, MARK, 100)

        threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(len(hm.history), 200)


class TestCompaction(unittest.TestCase):
    PH = "[old tool result removed]"

    def _tools(self, *contents):
        return [_msg("user", "go")] + [_msg("tool", c) for c in contents]

    def test_only_the_newest_results_stay_full(self):
        msgs = self._tools("r1", "r2", "r3", "r4")
        HistoryManager.compact_old_tool_results(msgs, 2, 10_000, self.PH)
        self.assertEqual([m["content"] for m in msgs[1:]], [self.PH, self.PH, "r3", "r4"])

    def test_an_error_result_is_never_compacted(self):
        msgs = self._tools('{"error": "boom"}', "r2", "r3", "r4")
        HistoryManager.compact_old_tool_results(msgs, 1, 10_000, self.PH)
        self.assertEqual(msgs[1]["content"], '{"error": "boom"}')
        self.assertEqual(msgs[2]["content"], self.PH)

    def test_an_oversized_result_goes_as_soon_as_it_is_not_the_latest(self):
        msgs = self._tools("B" * 500, "small")
        HistoryManager.compact_old_tool_results(msgs, 5, 100, self.PH)
        self.assertEqual(msgs[1]["content"], self.PH)
        self.assertEqual(msgs[2]["content"], "small")

    def test_the_latest_result_is_kept_even_when_oversized(self):
        msgs = self._tools("small", "B" * 500)
        HistoryManager.compact_old_tool_results(msgs, 5, 100, self.PH)
        self.assertEqual(msgs[2]["content"], "B" * 500)

    def test_idempotent_and_safe_with_no_tool_messages_or_odd_content(self):
        msgs = [_msg("user", "hi"), {"role": "tool", "content": None}]
        HistoryManager.compact_old_tool_results(msgs, 1, 10, self.PH)
        HistoryManager.compact_old_tool_results(msgs, 1, 10, self.PH)
        self.assertIsNone(msgs[1]["content"])
        HistoryManager.compact_old_tool_results([_msg("user", "x")], 1, 10, self.PH)

        msgs = self._tools("r1", "r2", "r3")
        HistoryManager.compact_old_tool_results(msgs, 1, 10_000, self.PH)
        once = [dict(m) for m in msgs]
        HistoryManager.compact_old_tool_results(msgs, 1, 10_000, self.PH)
        self.assertEqual(msgs, once)


if __name__ == "__main__":
    unittest.main()
