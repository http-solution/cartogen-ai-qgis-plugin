# -*- coding: utf-8 -*-
"""Tests for agent/dataset_status.py -- the QA-gate lifecycle state machine
that closes point 2 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md
(first pass: the state machine + sequential gate + one real automated check,
geometry_validity, wired to STAGED -> VALIDATED via the existing
diagnose_topology tool -- see that module's docstring for full scope and
deliberate deferrals).

Uses a plain fake layer object (not a QGIS mock) since the module's core
functions are deliberately duck-typed rather than QGIS-object-specific --
see the "Unlike lineage.py" comment in dataset_status.py."""
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.dataset_status import (
    STATUS_ORDER,
    get_dataset_status,
    set_initial_status,
    advance_dataset_status,
)


class FakeLayer:
    """Minimal stand-in for a QGIS layer: just enough customProperty storage
    for the state machine to read/write against, plus a name() and an
    optional getFeatures() to control whether it looks like a vector layer
    to _run_automated_check's duck-typing check."""

    def __init__(self, name="test_layer", is_vector=True):
        self._name = name
        self._props = {}
        if is_vector:
            self.getFeatures = lambda: []

    def name(self):
        return self._name

    def customProperty(self, key, default=""):
        return self._props.get(key, default)

    def setCustomProperty(self, key, value):
        self._props[key] = value


class TestGetDatasetStatusDefaults(unittest.TestCase):
    def test_untagged_layer_returns_default_record(self):
        record = get_dataset_status(FakeLayer())
        self.assertIsNone(record["status"])
        self.assertEqual(record["history"], [])
        self.assertEqual(record["checks"], {})

    def test_none_layer_returns_default_record(self):
        record = get_dataset_status(None)
        self.assertIsNone(record["status"])

    def test_corrupt_property_value_returns_default_record(self):
        layer = FakeLayer()
        layer.setCustomProperty("cartogen_ai/dataset_status", "{not valid json")
        record = get_dataset_status(layer)
        self.assertIsNone(record["status"])


class TestSetInitialStatus(unittest.TestCase):
    def test_defaults_to_ingested(self):
        layer = FakeLayer()
        result = set_initial_status(layer)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "INGESTED")
        self.assertEqual(get_dataset_status(layer)["status"], "INGESTED")

    def test_rejects_unknown_status(self):
        result = set_initial_status(FakeLayer(), status="NOT_A_REAL_STATUS")
        self.assertIn("error", result)

    def test_refuses_to_overwrite_existing_tracked_status(self):
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = set_initial_status(layer, status="INGESTED")
        self.assertIn("error", result)
        self.assertEqual(get_dataset_status(layer)["status"], "STAGED")

    def test_records_history_entry_with_note(self):
        layer = FakeLayer()
        set_initial_status(layer, status="INGESTED", note="fresh WorldPop download")
        history = get_dataset_status(layer)["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["note"], "fresh WorldPop download")


class TestAdvanceDatasetStatusOrdering(unittest.TestCase):
    def test_requires_initial_status_first(self):
        result = advance_dataset_status(FakeLayer(), "STAGED")
        self.assertIn("error", result)

    def test_rejects_unknown_target_status(self):
        layer = FakeLayer()
        set_initial_status(layer)
        result = advance_dataset_status(layer, "NOT_A_REAL_STATUS")
        self.assertIn("error", result)

    def test_refuses_to_skip_states(self):
        layer = FakeLayer()
        set_initial_status(layer, status="INGESTED")
        result = advance_dataset_status(layer, "ANALYSIS_READY", note="skip ahead")
        self.assertIn("error", result)
        self.assertIn("skips", result["error"])
        self.assertEqual(get_dataset_status(layer)["status"], "INGESTED")

    def test_restating_current_status_is_allowed_without_note(self):
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(layer, "STAGED")
        self.assertTrue(result["success"])

    def test_backward_move_requires_note(self):
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(layer, "INGESTED")
        self.assertIn("error", result)

    def test_backward_move_with_note_succeeds(self):
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(layer, "INGESTED", note="upstream source retracted")
        self.assertTrue(result["success"])
        self.assertEqual(get_dataset_status(layer)["status"], "INGESTED")

    def test_forward_step_with_no_automated_check_requires_note(self):
        layer = FakeLayer()
        set_initial_status(layer, status="VALIDATED")
        result = advance_dataset_status(layer, "ANALYSIS_READY")
        self.assertIn("error", result)
        self.assertIn("note", result["error"])

    def test_forward_step_with_no_automated_check_and_note_succeeds(self):
        layer = FakeLayer()
        set_initial_status(layer, status="VALIDATED")
        result = advance_dataset_status(layer, "ANALYSIS_READY", note="admin boundaries joined and reviewed")
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ANALYSIS_READY")


class TestAdvanceDatasetStatusAutomatedGeometryCheck(unittest.TestCase):
    """STAGED -> VALIDATED is the one transition with a real automated check
    wired in: geometry_validity via the existing diagnose_topology tool."""

    @patch("cartogen_ai.core.agent.tools.vector_tools.diagnose_topology")
    def test_passes_through_when_geometry_is_clean(self, mock_diagnose):
        mock_diagnose.return_value = {"success": True, "invalid_geometries": 0, "zero_area_slivers": 0}
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(layer, "VALIDATED")
        self.assertTrue(result["success"])
        self.assertEqual(get_dataset_status(layer)["status"], "VALIDATED")
        self.assertIn("VALIDATED", get_dataset_status(layer)["checks"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.diagnose_topology")
    def test_blocks_advance_when_geometry_check_fails(self, mock_diagnose):
        mock_diagnose.return_value = {"success": True, "invalid_geometries": 3, "zero_area_slivers": 1}
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(layer, "VALIDATED")
        self.assertIn("error", result)
        self.assertEqual(get_dataset_status(layer)["status"], "STAGED")

    @patch("cartogen_ai.core.agent.tools.vector_tools.diagnose_topology")
    def test_override_with_note_bypasses_a_failed_check(self, mock_diagnose):
        mock_diagnose.return_value = {"success": True, "invalid_geometries": 2, "zero_area_slivers": 0}
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(
            layer, "VALIDATED", note="known slivers accepted for this delivery", override=True,
        )
        self.assertTrue(result["success"])
        self.assertEqual(get_dataset_status(layer)["status"], "VALIDATED")

    @patch("cartogen_ai.core.agent.tools.vector_tools.diagnose_topology")
    def test_override_without_note_is_rejected(self, mock_diagnose):
        mock_diagnose.return_value = {"success": True, "invalid_geometries": 2, "zero_area_slivers": 0}
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(layer, "VALIDATED", override=True)
        self.assertIn("error", result)
        self.assertEqual(get_dataset_status(layer)["status"], "STAGED")

    def test_non_vector_layer_fails_geometry_check_cleanly(self):
        layer = FakeLayer(is_vector=False)
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(layer, "VALIDATED")
        self.assertIn("error", result)
        self.assertEqual(get_dataset_status(layer)["status"], "STAGED")


class TestStatusOrderConstant(unittest.TestCase):
    def test_status_order_matches_review_doc(self):
        self.assertEqual(
            STATUS_ORDER,
            ["INGESTED", "STAGED", "VALIDATED", "ANALYSIS_READY", "CARTOGRAPHY_READY", "PUBLICATION_READY"],
        )


if __name__ == "__main__":
    unittest.main()
