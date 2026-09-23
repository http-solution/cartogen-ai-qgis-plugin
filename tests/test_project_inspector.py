# -*- coding: utf-8 -*-
"""Tests for core/services/project_inspector.py -- IMPLEMENTATION_TRACKER.md §1.5, option (b)."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.services import project_inspector


class TestDegradesGracefullyOutsideQgis(unittest.TestCase):
    def test_returns_empty_dict(self):
        with patch.object(project_inspector, "QGIS_AVAILABLE", False):
            self.assertEqual(project_inspector.inspect_project(), {})


class TestInspectProject(unittest.TestCase):
    def _mock_project(self, layouts=(), themes=(), title="", abstract="", author="", keywords=None):
        project = MagicMock()
        project.layoutManager.return_value.layouts.return_value = [
            MagicMock(**{"name.return_value": n}) for n in layouts
        ]
        project.mapThemeCollection.return_value.mapThemes.return_value = list(themes)
        md = MagicMock()
        md.title.return_value = title
        md.abstract.return_value = abstract
        md.author.return_value = author
        md.keywords.return_value = keywords or {}
        project.metadata.return_value = md
        return project

    @patch.object(project_inspector, "QGIS_AVAILABLE", True)
    @patch.object(project_inspector, "QgsProject", create=True)
    def test_empty_project_returns_empty_dict(self, mock_project_cls):
        mock_project_cls.instance.return_value = self._mock_project()
        self.assertEqual(project_inspector.inspect_project(), {})

    @patch.object(project_inspector, "QGIS_AVAILABLE", True)
    @patch.object(project_inspector, "QgsProject", create=True)
    def test_layouts_and_themes_are_captured(self, mock_project_cls):
        mock_project_cls.instance.return_value = self._mock_project(
            layouts=["Sitrep A3", "Operational A4"], themes=["overview", "health_only"],
        )
        res = project_inspector.inspect_project()
        self.assertEqual(res["layouts"], ["Sitrep A3", "Operational A4"])
        self.assertEqual(res["themes"], ["overview", "health_only"])
        self.assertFalse(res["layouts_truncated"])
        self.assertFalse(res["themes_truncated"])

    @patch.object(project_inspector, "QGIS_AVAILABLE", True)
    @patch.object(project_inspector, "QgsProject", create=True)
    def test_metadata_is_captured(self, mock_project_cls):
        mock_project_cls.instance.return_value = self._mock_project(
            title="Flood Response", abstract="2026 flood analysis", author="Alaa",
            keywords={"theme": ["flood", "response"]},
        )
        res = project_inspector.inspect_project()
        self.assertEqual(res["metadata"]["title"], "Flood Response")
        self.assertEqual(res["metadata"]["abstract"], "2026 flood analysis")
        self.assertEqual(res["metadata"]["author"], "Alaa")
        self.assertEqual(res["metadata"]["keywords"], {"theme": ["flood", "response"]})

    @patch.object(project_inspector, "QGIS_AVAILABLE", True)
    @patch.object(project_inspector, "QgsProject", create=True)
    def test_layout_list_is_capped_and_flagged_truncated(self, mock_project_cls):
        mock_project_cls.instance.return_value = self._mock_project(
            layouts=[f"Layout {i}" for i in range(15)],
        )
        res = project_inspector.inspect_project()
        self.assertEqual(len(res["layouts"]), project_inspector.MAX_LAYOUTS)
        self.assertTrue(res["layouts_truncated"])

    @patch.object(project_inspector, "QGIS_AVAILABLE", True)
    @patch.object(project_inspector, "QgsProject", create=True)
    def test_exception_returns_empty_dict_not_raised(self, mock_project_cls):
        mock_project_cls.instance.side_effect = RuntimeError("boom")
        self.assertEqual(project_inspector.inspect_project(), {})


if __name__ == "__main__":
    unittest.main()
