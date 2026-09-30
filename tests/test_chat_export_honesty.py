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

    def test_retention_note_when_saving_is_on_names_the_window(self):
        with patch.object(cp, "is_persist_enabled", return_value=True):
            info = cp.describe_retention(10)
        self.assertTrue(info["persistence_enabled"])
        self.assertEqual(info["max_messages_kept"], 10)
        self.assertIn("most recent 10 messages", info["note"])
        self.assertIn("Not a full transcript", info["note"])
        self.assertIn("chat_history_digest", info["note"])


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
