# -*- coding: utf-8 -*-
"""Tests for agent/tools/transaction_tools.py -- the registered-tool
surface over agent/transactions.py's TurnTransactionLog (point 20).
Follows the same bind-then-patch convention as tests/test_task_tools.py
(bind_agent_context) for the module-level global this file's tools read
from, and tests/test_sensitivity_tools.py's QGIS_AVAILABLE/QgsProject
patch convention for the QGIS-touching half of undo_last_operation."""
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.transactions import TurnTransactionLog
from cartogen_ai.core.agent.tools.transaction_tools import (
    bind_transaction_log, get_turn_transaction_log, undo_last_operation,
)


class TestUnbound(unittest.TestCase):
    def setUp(self):
        bind_transaction_log(None)

    def test_get_turn_transaction_log_unbound(self):
        result = get_turn_transaction_log()
        self.assertIn("error", result)

    def test_undo_last_operation_unbound(self):
        result = undo_last_operation()
        self.assertIn("error", result)


class TestGetTurnTransactionLog(unittest.TestCase):
    def setUp(self):
        self.log = TurnTransactionLog()
        bind_transaction_log(self.log)

    def tearDown(self):
        bind_transaction_log(None)

    def test_empty_log(self):
        result = get_turn_transaction_log()
        self.assertEqual(result["entries"], [])
        self.assertFalse(result["undo_available"])

    def test_reports_undo_availability(self):
        self.log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        result = get_turn_transaction_log()
        self.assertEqual(len(result["entries"]), 1)
        self.assertTrue(result["undo_available"])

    def test_no_undo_available_for_read_only_turn(self):
        self.log.record("get_layers", "READ", {"success": True}, set(), set())
        result = get_turn_transaction_log()
        self.assertFalse(result["undo_available"])


class TestUndoLastOperationNothingToUndo(unittest.TestCase):
    def setUp(self):
        self.log = TurnTransactionLog()
        bind_transaction_log(self.log)

    def tearDown(self):
        bind_transaction_log(None)

    def test_empty_turn(self):
        result = undo_last_operation(confirmed=True)
        self.assertFalse(result["success"])
        self.assertIn("Nothing undoable", result["message"])

    def test_read_only_turn(self):
        self.log.record("get_layers", "READ", {"success": True}, set(), set())
        result = undo_last_operation(confirmed=True)
        self.assertFalse(result["success"])


class TestUndoLastOperationPreviewGate(unittest.TestCase):
    def setUp(self):
        self.log = TurnTransactionLog()
        bind_transaction_log(self.log)
        self.log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})

    def tearDown(self):
        bind_transaction_log(None)

    def test_unconfirmed_call_returns_preview_required(self):
        result = undo_last_operation(confirmed=False)
        self.assertEqual(result["status"], "PREVIEW_REQUIRED")
        self.assertTrue(result["requires_confirmation"])
        self.assertTrue(result["is_destructive"])
        self.assertEqual(result["arguments"], {"confirmed": True})

    def test_unconfirmed_call_does_not_mark_anything_undone(self):
        undo_last_operation(confirmed=False)
        entry = self.log.last_undoable()
        self.assertIsNotNone(entry)
        self.assertFalse(entry["undone"])


class TestUndoLastOperationConfirmedNoQgis(unittest.TestCase):
    def setUp(self):
        self.log = TurnTransactionLog()
        bind_transaction_log(self.log)
        self.log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})

    def tearDown(self):
        bind_transaction_log(None)

    def test_confirmed_without_qgis_returns_error(self):
        result = undo_last_operation(confirmed=True)
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])


class TestUndoLastOperationConfirmedWithQgis(unittest.TestCase):
    def setUp(self):
        self.log = TurnTransactionLog()
        bind_transaction_log(self.log)

    def tearDown(self):
        bind_transaction_log(None)

    @patch("cartogen_ai.core.agent.tools.transaction_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.transaction_tools.QgsProject", create=True)
    def test_removes_the_added_layers(self, mock_project_cls):
        entry = self.log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        mock_instance = mock_project_cls.instance.return_value
        mock_instance.mapLayer.return_value = MagicMock()  # layer "b" still present

        result = undo_last_operation(confirmed=True)

        self.assertTrue(result["success"])
        self.assertEqual(result["removed_layer_ids"], ["b"])
        mock_instance.removeMapLayer.assert_called_once_with("b")
        self.assertTrue(self.log.summary()[entry["index"]]["undone"])

    @patch("cartogen_ai.core.agent.tools.transaction_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.transaction_tools.QgsProject", create=True)
    def test_already_removed_layer_reports_warning_not_error(self, mock_project_cls):
        self.log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        mock_instance = mock_project_cls.instance.return_value
        mock_instance.mapLayer.return_value = None  # layer "b" already gone

        result = undo_last_operation(confirmed=True)

        self.assertTrue(result["success"])
        self.assertEqual(result["removed_layer_ids"], [])
        self.assertIn("warning", result)
        mock_instance.removeMapLayer.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.transaction_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.transaction_tools.QgsProject", create=True)
    def test_second_undo_call_finds_nothing_left(self, mock_project_cls):
        self.log.record("buffer_analysis", "CREATE", {"success": True}, {"a"}, {"a", "b"})
        mock_instance = mock_project_cls.instance.return_value
        mock_instance.mapLayer.return_value = MagicMock()

        undo_last_operation(confirmed=True)
        second = undo_last_operation(confirmed=True)

        self.assertFalse(second["success"])
        self.assertIn("Nothing undoable", second["message"])
