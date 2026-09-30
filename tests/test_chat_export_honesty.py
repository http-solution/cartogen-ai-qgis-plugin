# -*- coding: utf-8 -*-
"""F25 (rc7 smoke test, 2026-09-30): the data export held 8 chat messages from a ~50 minute session.

Cause, from the code: the stored history is the agent's rolling window (MAX_HISTORY_MESSAGES = 10);
older messages are replaced by a short extractive digest (role "system"), and the export filtered
that digest out, so stored text went unreported and the gap looked like data loss. Also, every
message new since the last save got one shared timestamp, so a user message was stamped with the
time the reply finished."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent import chat_persistence as cp
from cartogen_ai.core.agent.data_export import build_export_document


class TestAttachTimestamps(unittest.TestCase):
    def test_a_new_user_message_takes_the_time_it_was_sent(self):
        history = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
        out = cp._attach_timestamps(history, [], user_ts="2026-09-30T01:24:05")
        self.assertEqual(out[0]["ts"], "2026-09-30T01:24:05")
        self.assertNotEqual(out[1]["ts"], "2026-09-30T01:24:05")     # the reply keeps the save time

    def test_without_a_send_time_behaviour_is_unchanged(self):
        out = cp._attach_timestamps([{"role": "user", "content": "q"}], [])
        self.assertTrue(out[0]["ts"])

    def test_an_already_stored_message_keeps_its_timestamp(self):
        prev = [{"role": "user", "content": "q", "ts": "old"}]
        out = cp._attach_timestamps([{"role": "user", "content": "q"}], prev, user_ts="new")
        self.assertEqual(out[0]["ts"], "old")


class TestDigestAndRetention(unittest.TestCase):
    def test_the_digest_is_returned_even_though_history_loading_filters_it(self):
        raw = [
            {"role": "system", "content": "[Earlier conversation digest] user: export the csv", "ts": "t0"},
            {"role": "user", "content": "hi", "ts": "t1"},
        ]
        with patch.object(cp, "_load_raw_entries", return_value=raw):
            self.assertEqual([e["role"] for e in cp.load_chat_digest()], ["system"])
            self.assertEqual([e["role"] for e in cp.load_chat_history_with_timestamps()], ["user"])

    def test_retention_note_when_saving_is_off(self):
        with patch.object(cp, "is_persist_enabled", return_value=False):
            info = cp.describe_retention(10)
        self.assertFalse(info["persistence_enabled"])
        self.assertIn("empty by design", info["note"])

    def test_retention_note_with_no_transcript_yet_names_the_window(self):
        with patch.object(cp, "is_persist_enabled", return_value=True), \
                patch.object(cp, "_read_transcript_document", return_value={"messages": [], "dropped": 0}):
            info = cp.describe_retention(10)
        self.assertTrue(info["persistence_enabled"])
        self.assertEqual(info["max_messages_kept"], 10)
        self.assertIn("No full transcript is stored", info["note"])
        self.assertIn("most recent 10 messages", info["note"])

    def test_retention_note_with_a_transcript_reports_its_size_and_any_drops(self):
        msgs = [{"role": "user", "content": "q", "ts": "t"}, {"role": "assistant", "content": "a", "ts": "t"}]
        with patch.object(cp, "is_persist_enabled", return_value=True), \
                patch.object(cp, "_read_transcript_document", return_value={"messages": msgs, "dropped": 7}):
            info = cp.describe_retention(10)
        self.assertEqual(info["transcript_messages"], 2)
        self.assertEqual(info["transcript_dropped"], 7)
        self.assertIn("Full stored conversation for this project: 2 messages", info["note"])
        self.assertIn("7 older messages were dropped", info["note"])
        self.assertIn("Saving is currently ON", info["note"])

    def test_a_transcript_stays_reportable_after_saving_is_turned_off(self):
        msgs = [{"role": "user", "content": "q", "ts": "t"}]
        with patch.object(cp, "is_persist_enabled", return_value=False), \
                patch.object(cp, "_read_transcript_document", return_value={"messages": msgs, "dropped": 0}):
            info = cp.describe_retention(10)
        self.assertIn("Saving is currently OFF", info["note"])
        self.assertEqual(info["transcript_messages"], 1)


class TestTranscriptMerge(unittest.TestCase):
    """merge_into_transcript appends only what the stored transcript does not hold yet."""

    @staticmethod
    def _m(*pairs):
        return [{"role": r, "content": c} for r, c in pairs]

    def test_an_empty_transcript_takes_the_whole_window(self):
        window = self._m(("user", "q1"), ("assistant", "a1"))
        _, new = cp.merge_into_transcript([], window)
        self.assertEqual(new, window)

    def test_only_the_new_turn_is_appended(self):
        t = self._m(("user", "q1"), ("assistant", "a1"))
        window = t + self._m(("user", "q2"), ("assistant", "a2"))
        _, new = cp.merge_into_transcript(t, window)
        self.assertEqual(new, self._m(("user", "q2"), ("assistant", "a2")))

    def test_a_trimmed_window_that_starts_later_still_finds_its_overlap(self):
        t = self._m(("user", "q1"), ("assistant", "a1"), ("user", "q2"), ("assistant", "a2"))
        window = self._m(("user", "q2"), ("assistant", "a2"), ("user", "q3"), ("assistant", "a3"))
        _, new = cp.merge_into_transcript(t, window)
        self.assertEqual(new, self._m(("user", "q3"), ("assistant", "a3")))

    def test_the_digest_system_message_is_ignored(self):
        t = self._m(("user", "q1"), ("assistant", "a1"))
        window = self._m(("system", "[Earlier conversation digest] ...")) + t + self._m(("user", "q2"))
        _, new = cp.merge_into_transcript(t, window)
        self.assertEqual(new, self._m(("user", "q2")))

    def test_an_identical_repeated_turn_is_still_appended(self):
        t = self._m(("user", "yes"), ("assistant", "ok"))
        window = t + self._m(("user", "yes"), ("assistant", "ok"))
        _, new = cp.merge_into_transcript(t, window)
        self.assertEqual(len(new), 2)

    def test_nothing_new_appends_nothing(self):
        t = self._m(("user", "q1"), ("assistant", "a1"))
        _, new = cp.merge_into_transcript(t, list(t))
        self.assertEqual(new, [])


class TestTranscriptCaps(unittest.TestCase):
    def test_under_the_bounds_nothing_is_dropped(self):
        msgs = [{"role": "user", "content": "x"}] * 5
        kept, dropped = cp.apply_transcript_caps(msgs, max_messages=10, max_chars=100)
        self.assertEqual((len(kept), dropped), (5, 0))

    def test_the_oldest_go_first_when_over_the_message_bound(self):
        msgs = [{"role": "user", "content": str(i)} for i in range(10)]
        kept, dropped = cp.apply_transcript_caps(msgs, max_messages=4, max_chars=10_000)
        self.assertEqual([m["content"] for m in kept], ["6", "7", "8", "9"])
        self.assertEqual(dropped, 6)

    def test_the_character_bound_also_drops_oldest_first(self):
        msgs = [{"role": "user", "content": "a" * 100} for _ in range(5)]
        kept, dropped = cp.apply_transcript_caps(msgs, max_messages=100, max_chars=250)
        self.assertEqual((len(kept), dropped), (2, 3))

    def test_the_newest_message_is_always_kept_even_if_it_alone_is_too_big(self):
        kept, dropped = cp.apply_transcript_caps([{"role": "user", "content": "a" * 500}], max_messages=1, max_chars=10)
        self.assertEqual((len(kept), dropped), (1, 0))


class TestPersistDefaultIsOn(unittest.TestCase):
    def test_the_default_constant_is_on(self):
        self.assertTrue(cp.PERSIST_DEFAULT)


class TestExportDocumentCarriesThem(unittest.TestCase):
    def test_digest_and_info_are_in_the_document(self):
        doc = build_export_document({}, {}, [], chat_digest=[{"role": "system", "content": "d"}],
                                    chat_info={"note": "n"})
        self.assertEqual(doc["chat_history_digest"], [{"role": "system", "content": "d"}])
        self.assertEqual(doc["chat_history_info"], {"note": "n"})

    def test_old_three_argument_calls_still_work(self):
        doc = build_export_document({}, {}, [])
        self.assertEqual(doc["chat_history_digest"], [])
        self.assertEqual(doc["chat_history_info"], {})


if __name__ == "__main__":
    unittest.main()
