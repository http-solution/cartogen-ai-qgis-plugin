# -*- coding: utf-8 -*-
"""Tests for agent/tools/dataset_status_tools.py -- the registered-tool
surface over agent/dataset_status.py's QA-gate state machine (point 2 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md).

Degrade-path tests run with no QGIS_AVAILABLE patch (matching this dev
environment's real state: no qgis package installed). The layer-lookup and
delegation tests patch QGIS_AVAILABLE True and QgsProject, following the
same convention used throughout tests/test_layout_tools.py,
tests/test_raster_tools.py, etc."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools.dataset_status_tools import (
    get_dataset_status,
    set_dataset_status,
    advance_dataset_status,
)


class TestDegradesGracefullyOutsideQgis(unittest.TestCase):
    def test_get_dataset_status_degrades(self):
        result = get_dataset_status("some_layer")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])

    def test_set_dataset_status_degrades(self):
        result = set_dataset_status("some_layer")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])

    def test_advance_dataset_status_degrades(self):
        result = advance_dataset_status("some_layer", "STAGED")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])


class TestLayerNotFound(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.dataset_status_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.dataset_status_tools.QgsProject", create=True)
    def test_get_dataset_status_missing_layer(self, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        result = get_dataset_status("missing_layer")
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])

    @patch("cartogen_ai.core.agent.tools.dataset_status_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.dataset_status_tools.QgsProject", create=True)
    def test_advance_dataset_status_missing_layer(self, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        result = advance_dataset_status("missing_layer", "STAGED")
        self.assertIn("error", result)
        self.assertIn("not found", result["error"])


class TestDelegatesToCoreModule(unittest.TestCase):
    """These tools are thin wrappers: find the layer, then delegate to the
    already-independently-tested core dataset_status module functions.
    Verified here via a real (non-QGIS) fake layer object standing in for
    the mapLayersByName result, exercised through set_dataset_status then
    get_dataset_status then advance_dataset_status end-to-end -- proving
    the wrapper's plumbing (arg passing, error passthrough, layer_name
    re-attachment) actually works, not just that it calls through."""

    class _FakeLayer:
        def __init__(self):
            self._props = {}

        def name(self):
            return "test_layer"

        def customProperty(self, key, default=""):
            return self._props.get(key, default)

        def setCustomProperty(self, key, value):
            self._props[key] = value

    @patch("cartogen_ai.core.agent.tools.dataset_status_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.dataset_status_tools.QgsProject", create=True)
    def test_set_then_get_round_trips_through_the_tool_layer(self, mock_project):
        layer = self._FakeLayer()
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        set_result = set_dataset_status("test_layer", status="INGESTED", note="new download")
        self.assertTrue(set_result["success"])
        self.assertEqual(set_result["layer_name"], "test_layer")

        get_result = get_dataset_status("test_layer")
        self.assertTrue(get_result["success"])
        self.assertEqual(get_result["status"], "INGESTED")
        self.assertEqual(len(get_result["history"]), 1)

    @patch("cartogen_ai.core.agent.tools.dataset_status_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.dataset_status_tools.QgsProject", create=True)
    def test_advance_propagates_error_from_core_module(self, mock_project):
        layer = self._FakeLayer()
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        # INGESTED -> STAGED now runs the pcode_depth automated check (point
        # 6), which auto-passes as "not applicable" on a plain fields()-less
        # fake layer -- so that transition alone can no longer exercise a
        # bare "no automated check, no note" refusal. Use
        # ANALYSIS_READY -> CARTOGRAPHY_READY instead, which still has no
        # automated check at all.
        set_dataset_status("test_layer", status="ANALYSIS_READY")
        result = advance_dataset_status("test_layer", "CARTOGRAPHY_READY")
        self.assertIn("error", result)

    @patch("cartogen_ai.core.agent.tools.dataset_status_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.dataset_status_tools.QgsProject", create=True)
    def test_advance_succeeds_with_note_and_reattaches_layer_name(self, mock_project):
        layer = self._FakeLayer()
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        set_dataset_status("test_layer", status="INGESTED")
        result = advance_dataset_status("test_layer", "STAGED", note="schema-checked manually")
        self.assertTrue(result["success"])
        self.assertEqual(result["layer_name"], "test_layer")
        self.assertEqual(result["status"], "STAGED")


if __name__ == "__main__":
    unittest.main()
