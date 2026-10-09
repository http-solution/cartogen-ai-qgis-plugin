# -*- coding: utf-8 -*-
"""Tests for agent/tools/data_export_tools.py -- the registered-tool
surface over agent/data_export.py (GDPR review findings F7/F8). Mocks the
live memory-manager accessor and chat_persistence directly, matching
tests/test_task_runner.py's / task_tools.py's own bind_agent_context
convention for cross-module live state."""
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.tools.data_export_tools import export_stored_data


import os as _os
EXPORT_PATH = _os.path.abspath(_os.path.join(_os.sep, "tmp", "export.json"))   # absolute on every OS: relative paths are anchored to the project (tools/_paths.py)


class TestExportStoredData(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.data_export_tools.get_memory_manager")
    def test_reports_missing_memory_manager(self, mock_get_manager):
        mock_get_manager.return_value = None
        result = export_stored_data(EXPORT_PATH)
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
        mock_chat.load_chat_transcript.return_value = []       # no full transcript -> falls back to the window
        mock_chat.load_chat_history_with_timestamps.return_value = [{"role": "user", "content": "hi", "ts": "t"}]
        mock_chat.load_chat_digest.return_value = []
        mock_chat.describe_retention.return_value = {"note": "rolling window"}

        mock_export.build_export_document.return_value = {
            "project_memory": {"a": "1", "b": "2"},
            "global_memory": {"pref:x": "y"},
            "chat_history": [{"role": "user", "content": "hi", "ts": "t"}],
            "chat_history_info": {"note": "rolling window"},
        }
        mock_export.write_export_document.return_value = True

        result = export_stored_data(EXPORT_PATH)

        self.assertTrue(result["success"])
        self.assertEqual(result["output_path"], EXPORT_PATH)
        self.assertEqual(result["project_memory_count"], 2)
        self.assertEqual(result["global_memory_count"], 1)
        self.assertEqual(result["chat_history_count"], 1)
        self.assertEqual(result["chat_history_note"], "rolling window")
        mock_export.build_export_document.assert_called_once_with(
            {"a": "1", "b": "2"}, {"pref:x": "y"}, [{"role": "user", "content": "hi", "ts": "t"}],
            chat_digest=[], chat_info={"note": "rolling window"},
        )

    @patch("cartogen_ai.core.agent.tools.data_export_tools._chat_persistence")
    @patch("cartogen_ai.core.agent.tools.data_export_tools._export")
    @patch("cartogen_ai.core.agent.tools.data_export_tools.get_memory_manager")
    def test_the_full_transcript_is_preferred_over_the_rolling_window(self, mock_get_manager, mock_export, mock_chat):
        manager = MagicMock()
        manager.get_project_notes.return_value = {}
        manager.get_global_notes.return_value = {}
        mock_get_manager.return_value = manager
        full = [{"role": "user", "content": f"m{i}", "ts": "t"} for i in range(40)]
        mock_chat.load_chat_transcript.return_value = full
        mock_chat.load_chat_history_with_timestamps.return_value = full[-10:]
        mock_chat.load_chat_digest.return_value = []
        mock_chat.describe_retention.return_value = {}
        mock_export.build_export_document.return_value = {"project_memory": {}, "global_memory": {}, "chat_history": full}
        mock_export.write_export_document.return_value = True

        result = export_stored_data(EXPORT_PATH)

        self.assertEqual(result["chat_history_count"], 40)
        self.assertEqual(mock_export.build_export_document.call_args[0][2], full)

    @patch("cartogen_ai.core.agent.tools.data_export_tools._chat_persistence")
    @patch("cartogen_ai.core.agent.tools.data_export_tools._export")
    @patch("cartogen_ai.core.agent.tools.data_export_tools.get_memory_manager")
    def test_reports_write_failure(self, mock_get_manager, mock_export, mock_chat):
        manager = MagicMock()
        manager.get_project_notes.return_value = {}
        manager.get_global_notes.return_value = {}
        mock_get_manager.return_value = manager
        mock_chat.load_chat_transcript.return_value = []
        mock_chat.load_chat_history_with_timestamps.return_value = []
        mock_export.build_export_document.return_value = {"project_memory": {}, "global_memory": {}, "chat_history": []}
        mock_export.write_export_document.return_value = False

        result = export_stored_data("C:/bad/path/export.json")

        self.assertIn("error", result)
        self.assertIn(_os.path.normpath("C:/bad/path/export.json"), result["error"])   # the path is normalised: backslashes on Windows

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
        mock_chat.load_chat_transcript.return_value = []
        mock_chat.load_chat_history_with_timestamps.side_effect = Exception("boom")
        mock_chat.load_chat_digest.return_value = []
        mock_chat.describe_retention.return_value = {}

        with patch("cartogen_ai.core.agent.tools.data_export_tools._export") as mock_export:
            mock_export.build_export_document.return_value = {"project_memory": {"a": "1"}, "global_memory": {}, "chat_history": []}
            mock_export.write_export_document.return_value = True
            result = export_stored_data(EXPORT_PATH)

        self.assertTrue(result["success"])
        mock_export.build_export_document.assert_called_once_with({"a": "1"}, {}, [], chat_digest=[], chat_info={})


if __name__ == "__main__":
    unittest.main()
