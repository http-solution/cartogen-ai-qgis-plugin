# -*- coding: utf-8 -*-
"""Tests for agent/transactions.py's TurnTransactionLog -- see that
module's docstring for exactly what this narrow undo mechanism covers
(new layers a call added) and what it deliberately doesn't (in-place
MODIFY edits, DELETE calls, anything from a previous turn)."""
import unittest

from cartogen_ai.core.agent.transactions import TurnTransactionLog


class TestRecord(unittest.TestCase):
    def test_successful_create_with_new_layer_is_undoable(self):
        log = TurnTransactionLog()
        entry = log.record(
            "buffer_analysis", "CREATE", {"success": True, "layer_name": "buf_1"},
            layer_ids_before={"a"}, layer_ids_after={"a", "b"},
        )
        self.assertIsNotNone(entry["undo"])
        self.assertEqual(entry["undo"]["layer_ids"], ["b"])
        self.assertFalse(entry["undone"])

    def test_successful_call_with_no_new_layer_is_not_undoable(self):
        log = TurnTransactionLog()
        entry = log.record(
            "field_calculator", "MODIFY", {"success": True},
            layer_ids_before={"a"}, layer_ids_after={"a"},
        )
        self.assertIsNone(entry["undo"])

    def test_append_to_existing_layer_is_not_undoable(self):
        """add_point_layer's documented create-OR-append ambiguity: appending
        to an already-existing layer must not be reported as undoable, since
        removing that layer would destroy more than this call added."""
        log = TurnTransactionLog()
        entry = log.record(
            "add_point_layer", "CREATE", {"success": True, "layer_name": "incidents"},
            layer_ids_before={"incidents_id"}, layer_ids_after={"incidents_id"},
        )
        self.assertIsNone(entry["undo"])

    def test_failed_call_is_never_undoable_even_if_layer_set_changed(self):
        log = TurnTransactionLog()
        entry = log.record(
            "buffer_analysis", "CREATE", {"error": "boom"},
            layer_ids_before={"a"}, layer_ids_after={"a", "b"},
        )
        self.assertIsNone(entry["undo"])
        self.assertFalse(entry["success"])
        self.assertEqual(entry["error"], "boom")

    def test_non_dict_result_is_treated_as_not_successful(self):
        log = TurnTransactionLog()
        entry = log.record("search_web", "READ", None, layer_ids_before=set(), layer_ids_after=set())
        self.assertFalse(entry["success"])
        self.assertIsNone(entry["undo"])

    def test_entries_are_indexed_in_order(self):
        log = TurnTransactionLog()
        e0 = log.record("get_layers", "READ", {"success": True}, set(), set())
        e1 = log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        self.assertEqual(e0["index"], 0)
        self.assertEqual(e1["index"], 1)


class TestSummary(unittest.TestCase):
    def test_summary_returns_all_entries_oldest_first(self):
        log = TurnTransactionLog()
        log.record("get_layers", "READ", {"success": True}, set(), set())
        log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        names = [e["name"] for e in log.summary()]
        self.assertEqual(names, ["get_layers", "buffer_analysis"])

    def test_summary_is_a_copy_not_the_live_list(self):
        log = TurnTransactionLog()
        log.record("get_layers", "READ", {"success": True}, set(), set())
        snapshot = log.summary()
        log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        self.assertEqual(len(snapshot), 1)


class TestLastUndoable(unittest.TestCase):
    def test_returns_none_when_nothing_undoable(self):
        log = TurnTransactionLog()
        log.record("get_layers", "READ", {"success": True}, set(), set())
        self.assertIsNone(log.last_undoable())

    def test_returns_most_recent_undoable_entry(self):
        log = TurnTransactionLog()
        log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        log.record("get_layers", "READ", {"success": True}, set(), set())
        log.record("clip_layer", "CREATE", {"success": True}, {"a", "b"}, {"a", "b", "c"})
        entry = log.last_undoable()
        self.assertEqual(entry["name"], "clip_layer")

    def test_skips_already_undone_entries(self):
        log = TurnTransactionLog()
        first = log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        log.mark_undone(first["index"])
        self.assertIsNone(log.last_undoable())

    def test_falls_back_to_earlier_undoable_entry_once_later_one_is_undone(self):
        log = TurnTransactionLog()
        first = log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        second = log.record("clip_layer", "CREATE", {"success": True}, {"a", "b"}, {"a", "b", "c"})
        log.mark_undone(second["index"])
        entry = log.last_undoable()
        self.assertEqual(entry["index"], first["index"])


class TestMarkUndone(unittest.TestCase):
    def test_mark_undone_returns_true_for_existing_index(self):
        log = TurnTransactionLog()
        entry = log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        self.assertTrue(log.mark_undone(entry["index"]))
        self.assertTrue(log.summary()[0]["undone"])

    def test_mark_undone_returns_false_for_unknown_index(self):
        log = TurnTransactionLog()
        self.assertFalse(log.mark_undone(999))


class TestReset(unittest.TestCase):
    def test_reset_clears_all_entries_and_undo_never_reaches_a_prior_turn(self):
        log = TurnTransactionLog()
        log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        log.reset()
        self.assertEqual(log.summary(), [])
        self.assertIsNone(log.last_undoable())
