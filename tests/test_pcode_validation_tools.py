# -*- coding: utf-8 -*-
"""Tests for agent/tools/pcode_validation_tools.py -- the registered-tool
surface over agent/pcode_validation.py (point 6 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md).

Degrade-path tests run with no QGIS_AVAILABLE patch (matching this dev
environment's real state). Layer-lookup/delegation tests patch
QGIS_AVAILABLE True and QgsProject, following the same convention used in
tests/test_dataset_status_tools.py and tests/test_schema_contract_tools.py."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools.pcode_validation_tools import (
    check_pcode_uniqueness,
    check_pcode_hierarchy,
)


class TestDegradesGracefullyOutsideQgis(unittest.TestCase):
    def test_check_pcode_uniqueness_degrades(self):
        result = check_pcode_uniqueness("some_layer")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])

    def test_check_pcode_hierarchy_degrades(self):
        result = check_pcode_hierarchy("some_layer")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])


class TestLayerNotFound(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QgsProject", create=True)
    def test_check_pcode_uniqueness_missing_layer(self, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        result = check_pcode_uniqueness("missing_layer")
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])

    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QgsProject", create=True)
    def test_check_pcode_hierarchy_missing_layer(self, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        result = check_pcode_hierarchy("missing_layer")
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])


class TestDelegatesToCoreModule(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QgsProject", create=True)
    def test_check_pcode_uniqueness_delegates_and_reattaches_layer_name(self, mock_project):
        layer = MagicMock()
        layer.fields.return_value.names.return_value = ["admin2_pcode"]
        layer.getFeatures.return_value = []
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        result = check_pcode_uniqueness("districts")

        self.assertTrue(result["success"])
        self.assertEqual(result["layer_name"], "districts")
        self.assertTrue(result["passed"])

    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QgsProject", create=True)
    def test_check_pcode_uniqueness_propagates_core_error(self, mock_project):
        layer = MagicMock()
        layer.fields.return_value.names.return_value = ["some_other_field"]
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        result = check_pcode_uniqueness("districts")

        self.assertIn("error", result)
        self.assertNotIn("layer_name", result)

    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QgsProject", create=True)
    def test_check_pcode_hierarchy_delegates_and_reattaches_layer_name(self, mock_project):
        feature = MagicMock()
        feature.attribute.side_effect = lambda name: {
            "admin2_pcode": "YE1201",
            "admin1_pcode": "YE12",
        }[name]
        feature.id.return_value = 0
        layer = MagicMock()
        layer.fields.return_value.names.return_value = ["admin2_pcode", "admin1_pcode"]
        layer.getFeatures.return_value = [feature]
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        result = check_pcode_hierarchy("districts")

        self.assertTrue(result["success"])
        self.assertEqual(result["layer_name"], "districts")
        self.assertTrue(result["passed"])

    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QgsProject", create=True)
    def test_check_pcode_hierarchy_propagates_core_error(self, mock_project):
        layer = MagicMock()
        layer.fields.return_value.names.return_value = ["some_other_field"]
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        result = check_pcode_hierarchy("districts")

        self.assertIn("error", result)
        self.assertNotIn("layer_name", result)

    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.pcode_validation_tools.QgsProject", create=True)
    def test_explicit_field_names_are_passed_through(self, mock_project):
        feature = MagicMock()
        feature.attribute.side_effect = lambda name: {
            "child_code": "YE1201",
            "parent_code": "YE12",
        }[name]
        feature.id.return_value = 0
        layer = MagicMock()
        layer.fields.return_value.names.return_value = ["child_code", "parent_code"]
        layer.getFeatures.return_value = [feature]
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        result = check_pcode_hierarchy(
            "districts", child_pcode_field="child_code", parent_pcode_field="parent_code"
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["child_pcode_field"], "child_code")
        self.assertEqual(result["parent_pcode_field"], "parent_code")


if __name__ == "__main__":
    unittest.main()
