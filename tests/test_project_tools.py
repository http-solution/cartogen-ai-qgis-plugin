# -*- coding: utf-8 -*-
"""Tests for agent/tools/project_tools.py (save_project/load_project), added
in the QGIS-feature-coverage pass. load_project follows the same
PREVIEW_REQUIRED destructive-confirmation pattern as vector_tools.remove_layer
since it replaces the entire open project."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.tools.project_tools import (
    save_project, load_project, create_map_theme, apply_map_theme, list_map_themes,
    create_project_folder_structure, _PROJECT_FOLDER_LAYOUT,
)


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

        # save_project anchors/normalises the path (tools/_paths.py), so on Windows "/tmp/out.qgz" becomes "\\tmp\\out.qgz"
        instance.setFileName.assert_called_once_with(os.path.normpath("/tmp/out.qgz"))
        self.assertTrue(res["success"])
        self.assertEqual(res["file_path"], "/tmp/out.qgz")      # the mock project's fileName(), reported as is

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


class TestMapThemesDegradeOutsideQgis(unittest.TestCase):
    def test_create_map_theme_degrades(self):
        res = create_map_theme("overview")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_apply_map_theme_degrades(self):
        res = apply_map_theme("overview")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_list_map_themes_degrades(self):
        res = list_map_themes()
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestCreateMapTheme(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.project_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.project_tools.QgsLayerTreeModel", create=True)
    @patch("cartogen_ai.core.agent.tools.project_tools.QgsProject", create=True)
    def test_saves_theme_from_current_state(self, mock_project_cls, mock_model_cls):
        themes = MagicMock()
        themes.mapThemes.return_value = ["overview"]
        instance = MagicMock()
        instance.mapThemeCollection.return_value = themes
        mock_project_cls.instance.return_value = instance

        res = create_map_theme("overview")

        self.assertTrue(res["success"])
        self.assertEqual(res["theme_name"], "overview")
        self.assertEqual(res["existing_themes"], ["overview"])
        # Confirms the None-model segfault workaround: applyTheme/create must
        # always be called with a real model, never None.
        mock_model_cls.assert_called_once_with(instance.layerTreeRoot.return_value)
        themes.createThemeFromCurrentState.assert_called_once_with(
            instance.layerTreeRoot.return_value, mock_model_cls.return_value,
        )
        themes.insert.assert_called_once_with("overview", themes.createThemeFromCurrentState.return_value)


class TestApplyMapTheme(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.project_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.project_tools.QgsProject", create=True)
    def test_reports_missing_theme(self, mock_project_cls):
        themes = MagicMock()
        themes.hasMapTheme.return_value = False
        themes.mapThemes.return_value = ["overview"]
        instance = MagicMock()
        instance.mapThemeCollection.return_value = themes
        mock_project_cls.instance.return_value = instance

        res = apply_map_theme("ghost_theme")

        self.assertIn("error", res)
        self.assertIn("ghost_theme", res["error"])
        self.assertEqual(res["existing_themes"], ["overview"])
        themes.applyTheme.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.project_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.project_tools.QgsLayerTreeModel", create=True)
    @patch("cartogen_ai.core.agent.tools.project_tools.QgsProject", create=True)
    def test_applies_existing_theme_with_a_real_model(self, mock_project_cls, mock_model_cls):
        themes = MagicMock()
        themes.hasMapTheme.return_value = True
        instance = MagicMock()
        instance.mapThemeCollection.return_value = themes
        mock_project_cls.instance.return_value = instance

        res = apply_map_theme("overview")

        self.assertTrue(res["success"])
        themes.applyTheme.assert_called_once_with(
            "overview", instance.layerTreeRoot.return_value, mock_model_cls.return_value,
        )


class TestListMapThemes(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.project_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.project_tools.QgsProject", create=True)
    def test_returns_theme_names(self, mock_project_cls):
        themes = MagicMock()
        themes.mapThemes.return_value = ["overview", "health_only"]
        instance = MagicMock()
        instance.mapThemeCollection.return_value = themes
        mock_project_cls.instance.return_value = instance

        res = list_map_themes()

        self.assertTrue(res["success"])
        self.assertEqual(res["themes"], ["overview", "health_only"])


class TestCreateProjectFolderStructure(unittest.TestCase):
    """IMPLEMENTATION_TRACKER.md SS1.7, option (c) -- opt-in scaffolding tool, doesn't need
    QGIS_AVAILABLE at all (pure filesystem, unlike every other tool in this file)."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_rejects_missing_base_path(self):
        res = create_project_folder_structure("")
        self.assertIn("error", res)

    def test_creates_every_layout_folder(self):
        res = create_project_folder_structure(self.tmp_dir)

        self.assertTrue(res["success"])
        self.assertEqual(sorted(res["created"]), sorted(_PROJECT_FOLDER_LAYOUT))
        self.assertEqual(res["already_existed"], [])
        for rel_dir in _PROJECT_FOLDER_LAYOUT:
            self.assertTrue(os.path.isdir(os.path.join(self.tmp_dir, *rel_dir.split("/"))))

    def test_never_overwrites_existing_folders_or_files(self):
        raw_dir = os.path.join(self.tmp_dir, "data", "00_raw")
        os.makedirs(raw_dir)
        sentinel_file = os.path.join(raw_dir, "do_not_touch.gpkg")
        with open(sentinel_file, "w") as f:
            f.write("real source data")

        res = create_project_folder_structure(self.tmp_dir)

        self.assertTrue(res["success"])
        self.assertIn("data/00_raw", res["already_existed"])
        self.assertNotIn("data/00_raw", res["created"])
        with open(sentinel_file) as f:
            self.assertEqual(f.read(), "real source data")

    def test_second_call_is_idempotent(self):
        create_project_folder_structure(self.tmp_dir)
        res = create_project_folder_structure(self.tmp_dir)

        self.assertTrue(res["success"])
        self.assertEqual(res["created"], [])
        self.assertEqual(sorted(res["already_existed"]), sorted(_PROJECT_FOLDER_LAYOUT))

    def test_creates_base_path_itself_if_missing(self):
        nested_base = os.path.join(self.tmp_dir, "does", "not", "exist", "yet")

        res = create_project_folder_structure(nested_base)

        self.assertTrue(res["success"])
        self.assertTrue(os.path.isdir(os.path.join(nested_base, "data", "00_raw")))


if __name__ == "__main__":
    unittest.main()
