# -*- coding: utf-8 -*-
"""Tests for agent/tools/data_export_tools.py -- the registered-tool
surface over agent/data_export.py (GDPR review findings F7/F8). Mocks the
live memory-manager accessor and chat_persistence directly, matching
tests/test_task_runner.py's / task_tools.py's own bind_agent_context
convention for cross-module live state."""
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.tools.data_export_tools import export_stored_data


class TestExportStoredData(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.data_export_tools.get_memory_manager")
    def test_reports_missing_memory_manager(self, mock_get_manager):
        mock_get_manager.return_value = None
        result = export_stored_data("C:/tmp/export.json")
        self.assertIn("error", result)
        self.assertIn("Memory manager", result["error"])

    @patch("cartogen_ai.core.agent.tools.data_export_tools._chat_persistence")
    @patch("cartogen_ai.core.agent.tools.data_export_tools._export")
    @patch("cartogen_ai.core.agent.tools.data_export_tools.get_memory_manager")
    def test_assembles_and_writes_real_counts(self, mock_get_manager, mock_export, mock_chat):
        manager = MagicMock()
        manager.get_project_notes.return_value = {"a": "1", "b": "2"}
        manager.get_global_notes.return_value = {"pref:x": "y"}
        mock_get_manager.return_value = manager
        mock_chat.load_chat_history_with_timestamps.return_value = [{"role": "user", "content": "hi", "ts": "t"}]

        mock_export.build_export_document.return_value = {
            "project_memory": {"a": "1", "b": "2"},
            "global_memory": {"pref:x": "y"},
            "chat_history": [{"role": "user", "content": "hi", "ts": "t"}],
        }
        mock_export.write_export_document.return_value = True

        result = export_stored_data("C:/tmp/export.json")

        self.assertTrue(result["success"])
        self.assertEqual(result["output_path"], "C:/tmp/export.json")
        self.assertEqual(result["project_memory_count"], 2)
        self.assertEqual(result["global_memory_count"], 1)
        self.assertEqual(result["chat_history_count"], 1)
        mock_export.build_export_document.assert_called_once_with(
            {"a": "1", "b": "2"}, {"pref:x": "y"}, [{"role": "user", "content": "hi", "ts": "t"}]
        )

    @patch("cartogen_ai.core.agent.tools.data_export_tools._chat_persistence")
    @patch("cartogen_ai.core.agent.tools.data_export_tools._export")
    @patch("cartogen_ai.core.agent.tools.data_export_tools.get_memory_manager")
    def test_reports_write_failure(self, mock_get_manager, mock_export, mock_chat):
        manager = MagicMock()
        manager.get_project_notes.return_value = {}
        manager.get_global_notes.return_value = {}
        mock_get_manager.return_value = manager
        mock_chat.load_chat_history_with_timestamps.return_value = []
        mock_export.build_export_document.return_value = {"project_memory": {}, "global_memory": {}, "chat_history": []}
        mock_export.write_export_document.return_value = False

        result = export_stored_data("C:/bad/path/export.json")

        self.assertIn("error", result)
        self.assertIn("C:/bad/path/export.json", result["error"])

    @patch("cartogen_ai.core.agent.tools.data_export_tools._chat_persistence")
    @patch("cartogen_ai.core.agent.tools.data_export_tools.get_memory_manager")
    def test_chat_history_read_failure_degrades_to_empty_not_error(self, mock_get_manager, mock_chat):
        # If reading chat history raises for any reason, the export should
        # still proceed with the memory it does have rather than failing
        # the whole export over an unrelated read.
        manager = MagicMock()
        manager.get_project_notes.return_value = {"a": "1"}
        manager.get_global_notes.return_value = {}
        mock_get_manager.return_value = manager
        mock_chat.load_chat_history_with_timestamps.side_effect = Exception("boom")

        with patch("cartogen_ai.core.agent.tools.data_export_tools._export") as mock_export:
            mock_export.build_export_document.return_value = {"project_memory": {"a": "1"}, "global_memory": {}, "chat_history": []}
            mock_export.write_export_document.return_value = True
            result = export_stored_data("C:/tmp/export.json")

        self.assertTrue(result["success"])
        mock_export.build_export_document.assert_called_once_with({"a": "1"}, {}, [])


if __name__ == "__main__":
    unittest.main()
