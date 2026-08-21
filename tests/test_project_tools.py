# -*- coding: utf-8 -*-
"""Tests for agent/tools/project_tools.py (save_project/load_project), added
in the QGIS-feature-coverage pass. load_project follows the same
PREVIEW_REQUIRED destructive-confirmation pattern as vector_tools.remove_layer
since it replaces the entire open project."""
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.tools.project_tools import save_project, load_project


class TestSaveProjectDegradesOutsideQgis(unittest.TestCase):
    def test_degrades(self):
        res = save_project("/tmp/out.qgz")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestSaveProjectBehavior(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.project_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.project_tools.QgsProject", create=True)
    def test_rejects_unsaved_project_without_output_path(self, mock_project_cls):
        instance = MagicMock()
        instance.fileName.return_value = ""
        mock_project_cls.instance.return_value = instance

        res = save_project()

        self.assertIn("error", res)
        self.assertIn("output_path", res["error"])

    @patch("cartogen_ai.core.agent.tools.project_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.project_tools.QgsProject", create=True)
    def test_saves_to_given_path(self, mock_project_cls):
        instance = MagicMock()
        instance.write.return_value = True
        instance.fileName.return_value = "/tmp/out.qgz"
        mock_project_cls.instance.return_value = instance

        res = save_project("/tmp/out.qgz")

        instance.setFileName.assert_called_once_with("/tmp/out.qgz")
        self.assertTrue(res["success"])
        self.assertEqual(res["file_path"], "/tmp/out.qgz")

    @patch("cartogen_ai.core.agent.tools.project_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.project_tools.QgsProject", create=True)
    def test_reports_write_failure(self, mock_project_cls):
        instance = MagicMock()
        instance.write.return_value = False
        instance.fileName.return_value = "/tmp/out.qgz"
        mock_project_cls.instance.return_value = instance

        res = save_project("/tmp/out.qgz")

        self.assertIn("error", res)


class TestLoadProjectRequiresConfirmation(unittest.TestCase):
    def test_unconfirmed_call_returns_preview_required(self):
        res = load_project("/tmp/some.qgz")
        self.assertEqual(res["status"], "PREVIEW_REQUIRED")
        self.assertTrue(res["is_destructive"])
        self.assertEqual(res["arguments"]["confirmed"], True)

    def test_confirmed_call_degrades_outside_qgis(self):
        res = load_project("/tmp/some.qgz", confirmed=True)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    @patch("cartogen_ai.core.agent.tools.project_tools.QGIS_AVAILABLE", True)
    def test_confirmed_call_rejects_missing_file(self):
        res = load_project("/definitely/not/a/real/project.qgz", confirmed=True)
        self.assertIn("error", res)
        self.assertIn("not found", res["error"])


if __name__ == "__main__":
    unittest.main()
