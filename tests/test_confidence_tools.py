# -*- coding: utf-8 -*-
"""Tests for agent/tools/confidence_tools.py -- the registered-tool surface
over models/confidence.py (point 23 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md). Mirrors
tests/test_sensitivity_tools.py (point 24) exactly, since confidence.py was
deliberately built to the same shape as sensitivity.py. Degrade-path tests
run with no QGIS_AVAILABLE patch (matching this dev environment's real
state); layer-lookup tests patch QGIS_AVAILABLE True and QgsProject,
following the same convention as tests/test_dataset_status_tools.py."""
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.tools.confidence_tools import (
    set_layer_confidence, get_layer_confidence,
)


class TestDegradesGracefullyOutsideQgis(unittest.TestCase):
    def test_set_layer_confidence_degrades(self):
        result = set_layer_confidence("some_layer", "MODELED")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])

    def test_get_layer_confidence_degrades(self):
        result = get_layer_confidence("some_layer")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])


class TestSetLayerConfidence(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.confidence_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.confidence_tools.QgsProject", create=True)
    def test_reports_missing_layer(self, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        result = set_layer_confidence("ghost_layer", "OBSERVED")
        self.assertIn("error", result)
        self.assertIn("ghost_layer", result["error"])

    @patch("cartogen_ai.core.agent.tools.confidence_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.confidence_tools.QgsProject", create=True)
    def test_rejects_unknown_level(self, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = [MagicMock()]
        result = set_layer_confidence("districts", "PRETTY_SURE")
        self.assertIn("error", result)
        self.assertIn("PRETTY_SURE", result["error"])

    @patch("cartogen_ai.core.agent.tools.confidence_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.confidence_tools.QgsProject", create=True)
    def test_tags_real_layer_via_custom_property(self, mock_project):
        layer = MagicMock()
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        result = set_layer_confidence("districts", "MODELED", reason="service area, flat speed assumption")

        self.assertTrue(result["success"])
        self.assertEqual(result["level"], "MODELED")
        layer.setCustomProperty.assert_called_once()
        prop_key, prop_value = layer.setCustomProperty.call_args[0]
        self.assertEqual(prop_key, "cartogen_ai/confidence")
        self.assertIn("MODELED", prop_value)
        self.assertIn("service area, flat speed assumption", prop_value)


class TestGetLayerConfidence(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.confidence_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.confidence_tools.QgsProject", create=True)
    def test_untagged_layer_returns_none_level(self, mock_project):
        layer = MagicMock()
        layer.customProperty.return_value = ""
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        result = get_layer_confidence("districts")

        self.assertTrue(result["success"])
        self.assertIsNone(result["level"])

    @patch("cartogen_ai.core.agent.tools.confidence_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.confidence_tools.QgsProject", create=True)
    def test_tagged_layer_round_trips_via_real_set_then_get(self, mock_project):
        # Real layer.customProperty()/setCustomProperty() behavior, not a
        # mock -- a plain dict-backed fake that actually stores what's set.
        store = {}

        class FakeLayer:
            def setCustomProperty(self, key, value):
                store[key] = value

            def customProperty(self, key, default=""):
                return store.get(key, default)

        layer = FakeLayer()
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        set_result = set_layer_confidence("districts", "INFERRED", reason="beyond what the data directly shows")
        self.assertTrue(set_result["success"])

        get_result = get_layer_confidence("districts")
        self.assertTrue(get_result["success"])
        self.assertEqual(get_result["level"], "INFERRED")
        self.assertEqual(get_result["reason"], "beyond what the data directly shows")


if __name__ == "__main__":
    unittest.main()
