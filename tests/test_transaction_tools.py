# -*- coding: utf-8 -*-
"""Tests for agent/tools/transaction_tools.py -- the registered-tool
surface over models/transactions.py's TurnTransactionLog (point 20).
Follows the same bind-then-patch convention as tests/test_task_tools.py
(bind_agent_context) for the module-level global this file's tools read
from, and tests/test_sensitivity_tools.py's QGIS_AVAILABLE/QgsProject
patch convention for the QGIS-touching half of undo_last_operation."""
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.models.transactions import TurnTransactionLog
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


class TestUndoLastOperationViaSnapshot(unittest.TestCase):
    """v1.7.0: the priority-subset MODIFY/DELETE undo kinds
    (_snapshot_registry.py), dispatched through _undo_via_snapshot rather
    than the remove_layers-specific path above."""

    def setUp(self):
        self.log = TurnTransactionLog()
        bind_transaction_log(self.log)

    def tearDown(self):
        bind_transaction_log(None)

    def _record_snapshot_entry(self, tool_name="field_calculator", kind="restore_field"):
        snapshot = {"kind": kind, "layer_id": "x", "field_name": "score", "field_existed": True, "values": {1: "old"}}
        return self.log.record(tool_name, "MODIFY", {"success": True}, set(), set(), snapshot=snapshot)

    def test_unconfirmed_call_returns_preview_required(self):
        self._record_snapshot_entry()
        result = undo_last_operation(confirmed=False)
        self.assertEqual(result["status"], "PREVIEW_REQUIRED")
        self.assertIn("field_calculator", result["rationale"])

    def test_confirmed_without_qgis_returns_error(self):
        self._record_snapshot_entry()
        result = undo_last_operation(confirmed=True)
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])

    @patch("cartogen_ai.core.agent.tools.transaction_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.transaction_tools.get_restore_fn")
    def test_confirmed_calls_the_matching_restore_fn_and_marks_undone(self, mock_get_restore_fn):
        entry = self._record_snapshot_entry()
        mock_restore = MagicMock(return_value=True)
        mock_get_restore_fn.return_value = mock_restore

        result = undo_last_operation(confirmed=True)

        self.assertTrue(result["success"])
        self.assertEqual(result["undone_tool"], "field_calculator")
        mock_get_restore_fn.assert_called_once_with("restore_field", "field_calculator")
        mock_restore.assert_called_once()
        self.assertTrue(self.log.summary()[entry["index"]]["undone"])

    @patch("cartogen_ai.core.agent.tools.transaction_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.transaction_tools.get_restore_fn")
    def test_restore_fn_returning_false_reports_error_and_does_not_mark_undone(self, mock_get_restore_fn):
        entry = self._record_snapshot_entry()
        mock_get_restore_fn.return_value = MagicMock(return_value=False)

        result = undo_last_operation(confirmed=True)

        self.assertIn("error", result)
        self.assertFalse(self.log.summary()[entry["index"]]["undone"])

    @patch("cartogen_ai.core.agent.tools.transaction_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.transaction_tools.get_restore_fn")
    def test_no_restore_fn_available_reports_error(self, mock_get_restore_fn):
        self._record_snapshot_entry(tool_name="some_unregistered_tool")
        mock_get_restore_fn.return_value = None

        result = undo_last_operation(confirmed=True)

        self.assertIn("error", result)
        self.assertIn("some_unregistered_tool", result["error"])

    @patch("cartogen_ai.core.agent.tools.transaction_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.transaction_tools.get_restore_fn")
    def test_style_kind_dispatches_correctly(self, mock_get_restore_fn):
        self._record_snapshot_entry(tool_name="apply_categorized_style", kind="restore_style")
        mock_restore = MagicMock(return_value=True)
        mock_get_restore_fn.return_value = mock_restore

        result = undo_last_operation(confirmed=True)

        self.assertTrue(result["success"])
        mock_get_restore_fn.assert_called_once_with("restore_style", "apply_categorized_style")

    @patch("cartogen_ai.core.agent.tools.transaction_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.transaction_tools.get_restore_fn")
    def test_property_kind_dispatches_correctly(self, mock_get_restore_fn):
        self._record_snapshot_entry(tool_name="run_query", kind="restore_property")
        mock_restore = MagicMock(return_value=True)
        mock_get_restore_fn.return_value = mock_restore

        result = undo_last_operation(confirmed=True)

        self.assertTrue(result["success"])
        mock_get_restore_fn.assert_called_once_with("restore_property", "run_query")

    @patch("cartogen_ai.core.agent.tools.transaction_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.transaction_tools.get_restore_fn")
    def test_layer_kind_dispatches_correctly(self, mock_get_restore_fn):
        self._record_snapshot_entry(tool_name="remove_layer", kind="restore_layer")
        mock_restore = MagicMock(return_value=True)
        mock_get_restore_fn.return_value = mock_restore

        result = undo_last_operation(confirmed=True)

        self.assertTrue(result["success"])
        mock_get_restore_fn.assert_called_once_with("restore_layer", "remove_layer")
