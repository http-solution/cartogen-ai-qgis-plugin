# -*- coding: utf-8 -*-
"""Tests for agent/tools/schema_contract_tools.py -- the registered-tool
surface over agent/schema_contracts.py (point 5 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md).

Degrade-path tests run with no QGIS_AVAILABLE patch (matching this dev
environment's real state). Layer-lookup/delegation tests patch
QGIS_AVAILABLE True and QgsProject, following the same convention used in
tests/test_dataset_status_tools.py."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools.schema_contract_tools import (
    list_schema_contracts,
    validate_schema,
)


class TestListSchemaContracts(unittest.TestCase):
    def test_lists_the_two_real_contracts_regardless_of_qgis_availability(self):
        # list_schema_contracts only reads JSON files off disk -- no QGIS
        # layer lookup involved, so it works even with QGIS unavailable.
        result = list_schema_contracts()
        self.assertTrue(result["success"])
        self.assertIn("admin2", result["contracts"])
        self.assertIn("health_facilities", result["contracts"])


class TestValidateSchemaDegradesOutsideQgis(unittest.TestCase):
    def test_degrades_gracefully(self):
        result = validate_schema("some_layer", "admin2")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])


class TestValidateSchemaLayerLookup(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.schema_contract_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.schema_contract_tools.QgsProject", create=True)
    def test_missing_layer_is_an_error(self, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        result = validate_schema("missing_layer", "admin2")
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])

    @patch("cartogen_ai.core.agent.tools.schema_contract_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.schema_contract_tools.QgsProject", create=True)
    def test_delegates_to_core_module_and_reattaches_layer_name(self, mock_project):
        layer = MagicMock()
        layer.fields.return_value.names.return_value = ["admin2_pcode", "admin2_name", "admin1_pcode"]
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        result = validate_schema("districts", "admin2")

        self.assertTrue(result["success"])
        self.assertEqual(result["layer_name"], "districts")
        self.assertTrue(result["passed"])

    @patch("cartogen_ai.core.agent.tools.schema_contract_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.schema_contract_tools.QgsProject", create=True)
    def test_unknown_contract_name_propagates_as_error(self, mock_project):
        layer = MagicMock()
        layer.fields.return_value.names.return_value = []
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        result = validate_schema("districts", "not_a_real_contract")

        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
