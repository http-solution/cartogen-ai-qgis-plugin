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


class _FakeEmptyFields:
    """Trivial stand-in for QgsFields with no fields at all."""

    def names(self):
        return []


class FakeLayer:
    """Minimal stand-in for a QGIS layer: just enough customProperty storage
    for the state machine to read/write against, plus a name() and an
    optional getFeatures() to control whether it looks like a vector layer
    to _run_automated_check's geometry_validity duck-typing check.
    fields() is always present (trivial) so the schema_contract duck-typing
    check passes too -- schema-contract gate tests mock validate_layer_schema
    itself, so what fields() actually returns doesn't matter, only that the
    attribute exists."""

    def __init__(self, name="test_layer", is_vector=True):
        self._name = name
        self._props = {}
        if is_vector:
            self.getFeatures = lambda: []

    def name(self):
        return self._name

    def fields(self):
        # A trivial real stand-in (not None) -- schema_contract/pcode_depth
        # gate tests mock the underlying validate_layer_schema/
        # check_pcode_* functions directly, but pcode_depth's own
        # "not applicable" auto-detection calls layer.fields().names() for
        # real (see _run_automated_check), so this needs to behave like an
        # empty QgsFields, not crash like None.names() would.
        return _FakeEmptyFields()


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


class TestAdvanceDatasetStatusStrengthenedGate(unittest.TestCase):
    """diagnose_topology was extended (2026-09-04, same session) to also
    report duplicate_geometries and overlapping_feature_pairs -- the gate
    now checks those too, not just invalid_geometries, per point 2's own
    cross-reference note that point 4 extensions should be picked up
    automatically with no state-machine change."""

    @patch("cartogen_ai.core.agent.tools.vector_tools.diagnose_topology")
    def test_blocks_on_duplicate_geometries_even_with_no_invalid_geometries(self, mock_diagnose):
        mock_diagnose.return_value = {
            "success": True, "invalid_geometries": 0, "zero_area_slivers": 0,
            "duplicate_geometries": 2, "overlapping_feature_pairs": 0,
        }
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(layer, "VALIDATED")
        self.assertIn("error", result)
        self.assertEqual(get_dataset_status(layer)["status"], "STAGED")

    @patch("cartogen_ai.core.agent.tools.vector_tools.diagnose_topology")
    def test_blocks_on_overlapping_feature_pairs_even_with_no_invalid_geometries(self, mock_diagnose):
        mock_diagnose.return_value = {
            "success": True, "invalid_geometries": 0, "zero_area_slivers": 0,
            "duplicate_geometries": 0, "overlapping_feature_pairs": 3,
        }
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(layer, "VALIDATED")
        self.assertIn("error", result)
        self.assertEqual(get_dataset_status(layer)["status"], "STAGED")

    @patch("cartogen_ai.core.agent.tools.vector_tools.diagnose_topology")
    def test_passes_when_all_three_are_clean(self, mock_diagnose):
        mock_diagnose.return_value = {
            "success": True, "invalid_geometries": 0, "zero_area_slivers": 0,
            "duplicate_geometries": 0, "overlapping_feature_pairs": 0,
        }
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(layer, "VALIDATED")
        self.assertTrue(result["success"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.diagnose_topology")
    def test_legacy_result_missing_new_keys_defaults_to_passing_on_them(self, mock_diagnose):
        # A diagnose_topology double that predates this extension (only
        # reports invalid_geometries/zero_area_slivers) must not suddenly
        # start failing the gate on keys it never claimed to report.
        mock_diagnose.return_value = {"success": True, "invalid_geometries": 0, "zero_area_slivers": 0}
        layer = FakeLayer()
        set_initial_status(layer, status="STAGED")
        result = advance_dataset_status(layer, "VALIDATED")
        self.assertTrue(result["success"])


class TestAdvanceDatasetStatusSchemaContractGate(unittest.TestCase):
    """VALIDATED -> ANALYSIS_READY runs a schema_contract check (point 5),
    but ONLY when contract_name is supplied -- opt-in, since not every
    dataset has a contract yet (see agent/contracts/)."""

    @patch("cartogen_ai.core.agent.schema_contracts.validate_layer_schema")
    def test_passes_when_contract_validates_clean(self, mock_validate):
        mock_validate.return_value = {
            "success": True, "passed": True, "missing_fields": [],
            "type_mismatches": [], "value_violations": [],
        }
        layer = FakeLayer()
        set_initial_status(layer, status="VALIDATED")
        result = advance_dataset_status(layer, "ANALYSIS_READY", contract_name="admin2")
        self.assertTrue(result["success"])
        self.assertEqual(get_dataset_status(layer)["status"], "ANALYSIS_READY")

    @patch("cartogen_ai.core.agent.schema_contracts.validate_layer_schema")
    def test_blocks_when_contract_fails_and_no_override(self, mock_validate):
        mock_validate.return_value = {
            "success": True, "passed": False, "missing_fields": ["admin1_pcode"],
            "type_mismatches": [], "value_violations": [],
        }
        layer = FakeLayer()
        set_initial_status(layer, status="VALIDATED")
        result = advance_dataset_status(layer, "ANALYSIS_READY", contract_name="admin2")
        self.assertIn("error", result)
        self.assertEqual(get_dataset_status(layer)["status"], "VALIDATED")

    @patch("cartogen_ai.core.agent.schema_contracts.validate_layer_schema")
    def test_override_with_note_bypasses_a_failed_contract_check(self, mock_validate):
        mock_validate.return_value = {
            "success": True, "passed": False, "missing_fields": ["admin1_pcode"],
            "type_mismatches": [], "value_violations": [],
        }
        layer = FakeLayer()
        set_initial_status(layer, status="VALIDATED")
        result = advance_dataset_status(
            layer, "ANALYSIS_READY", contract_name="admin2",
            override=True, note="admin1_pcode not needed for this analysis",
        )
        self.assertTrue(result["success"])

    def test_no_contract_name_falls_through_to_ordinary_note_requirement(self):
        # No contract_name supplied -- this must behave exactly like any
        # other transition with no automated check at all, not like a
        # schema_contract check that has nothing to check against.
        layer = FakeLayer()
        set_initial_status(layer, status="VALIDATED")
        without_note = advance_dataset_status(layer, "ANALYSIS_READY")
        self.assertIn("error", without_note)
        with_note = advance_dataset_status(layer, "ANALYSIS_READY", note="reviewed manually, no contract yet")
        self.assertTrue(with_note["success"])


class TestAdvanceDatasetStatusPcodeDepthGate(unittest.TestCase):
    """INGESTED -> STAGED runs a pcode_depth check (point 6): P-code
    uniqueness + parent/child hierarchy prefix-match, via
    agent/pcode_validation.py. Unlike the schema_contract gate, this one is
    NOT opt-in -- it auto-detects P-code-shaped fields and passes as
    "not applicable" when none exist, so it never blocks a non-admin-
    boundary layer. The default FakeLayer has no fields at all
    (fields().names() == []), which is exactly the "not applicable" case
    exercised for real (unmocked) below; the pass/fail cases mock the
    underlying check_pcode_* functions directly, the same way the
    schema_contract gate tests mock validate_layer_schema."""

    def test_not_applicable_when_layer_has_no_pcode_fields_passes_without_note(self):
        layer = FakeLayer()
        set_initial_status(layer, status="INGESTED")
        result = advance_dataset_status(layer, "STAGED")
        self.assertTrue(result["success"])
        self.assertEqual(get_dataset_status(layer)["status"], "STAGED")

    @patch("cartogen_ai.core.agent.pcode_validation.check_pcode_hierarchy")
    @patch("cartogen_ai.core.agent.pcode_validation.check_pcode_uniqueness")
    def test_blocks_when_uniqueness_check_fails(self, mock_uniqueness, mock_hierarchy):
        mock_uniqueness.return_value = {
            "success": True, "passed": False, "pcode_field": "admin2_pcode",
            "duplicate_pcodes": {"YE1201": [0, 2]},
        }
        mock_hierarchy.return_value = {"error": "Could not find both a child and parent P-code field on this layer."}
        layer = FakeLayer()
        set_initial_status(layer, status="INGESTED")
        result = advance_dataset_status(layer, "STAGED")
        self.assertIn("error", result)
        self.assertEqual(get_dataset_status(layer)["status"], "INGESTED")

    @patch("cartogen_ai.core.agent.pcode_validation.check_pcode_hierarchy")
    @patch("cartogen_ai.core.agent.pcode_validation.check_pcode_uniqueness")
    def test_blocks_when_hierarchy_check_fails(self, mock_uniqueness, mock_hierarchy):
        mock_uniqueness.return_value = {"error": "No P-code field found or specified."}
        mock_hierarchy.return_value = {
            "success": True, "passed": False,
            "mismatches": [{"feature_id": 1, "child_pcode": "YE0902", "parent_pcode": "YE12"}],
        }
        layer = FakeLayer()
        set_initial_status(layer, status="INGESTED")
        result = advance_dataset_status(layer, "STAGED")
        self.assertIn("error", result)
        self.assertEqual(get_dataset_status(layer)["status"], "INGESTED")

    @patch("cartogen_ai.core.agent.pcode_validation.check_pcode_hierarchy")
    @patch("cartogen_ai.core.agent.pcode_validation.check_pcode_uniqueness")
    def test_override_with_note_bypasses_a_failed_pcode_check(self, mock_uniqueness, mock_hierarchy):
        mock_uniqueness.return_value = {"success": True, "passed": False, "duplicate_pcodes": {"YE1201": [0, 2]}}
        mock_hierarchy.return_value = {"error": "Could not find both a child and parent P-code field on this layer."}
        layer = FakeLayer()
        set_initial_status(layer, status="INGESTED")
        result = advance_dataset_status(
            layer, "STAGED", override=True, note="known duplicate, source data confirmed correct",
        )
        self.assertTrue(result["success"])

    @patch("cartogen_ai.core.agent.pcode_validation.check_pcode_hierarchy")
    @patch("cartogen_ai.core.agent.pcode_validation.check_pcode_uniqueness")
    def test_passes_when_both_checks_pass(self, mock_uniqueness, mock_hierarchy):
        mock_uniqueness.return_value = {"success": True, "passed": True, "duplicate_pcodes": {}}
        mock_hierarchy.return_value = {"success": True, "passed": True, "mismatches": []}
        layer = FakeLayer()
        set_initial_status(layer, status="INGESTED")
        result = advance_dataset_status(layer, "STAGED")
        self.assertTrue(result["success"])
        self.assertEqual(get_dataset_status(layer)["status"], "STAGED")


class TestAdvanceDatasetStatusMapQaGate(unittest.TestCase):
    """v1.8.0 workstream 3: CARTOGRAPHY_READY -> PUBLICATION_READY runs a
    map_qa check (generate_map_product_qa_checklist), but ONLY when
    layout_name is supplied -- opt-in, the same shape as the
    schema_contract gate above, since not every map product has a print
    layout to check."""

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.generate_map_product_qa_checklist")
    def test_passes_when_layout_complete_and_layer_not_sensitive(self, mock_checklist):
        mock_checklist.return_value = {
            "success": True, "layer_name": "districts",
            "categories": {
                "cartography": {"mandatory_elements_missing": []},
                "disclosure": {"level": None},
            },
        }
        layer = FakeLayer()
        set_initial_status(layer, status="CARTOGRAPHY_READY")
        result = advance_dataset_status(layer, "PUBLICATION_READY", layout_name="Layout_SITREP")
        self.assertTrue(result["success"])
        self.assertEqual(get_dataset_status(layer)["status"], "PUBLICATION_READY")

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.generate_map_product_qa_checklist")
    def test_blocks_when_mandatory_layout_element_missing(self, mock_checklist):
        mock_checklist.return_value = {
            "success": True, "layer_name": "districts",
            "categories": {
                "cartography": {"mandatory_elements_missing": ["scale bar"]},
                "disclosure": {"level": None},
            },
        }
        layer = FakeLayer()
        set_initial_status(layer, status="CARTOGRAPHY_READY")
        result = advance_dataset_status(layer, "PUBLICATION_READY", layout_name="Layout_partial")
        self.assertIn("error", result)
        self.assertEqual(get_dataset_status(layer)["status"], "CARTOGRAPHY_READY")

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.generate_map_product_qa_checklist")
    def test_blocks_when_layer_tagged_sensitive(self, mock_checklist):
        mock_checklist.return_value = {
            "success": True, "layer_name": "beneficiaries",
            "categories": {
                "cartography": {"mandatory_elements_missing": []},
                "disclosure": {"level": "SENSITIVE"},
            },
        }
        layer = FakeLayer()
        set_initial_status(layer, status="CARTOGRAPHY_READY")
        result = advance_dataset_status(layer, "PUBLICATION_READY", layout_name="Layout_SITREP")
        self.assertIn("error", result)
        self.assertEqual(get_dataset_status(layer)["status"], "CARTOGRAPHY_READY")

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.generate_map_product_qa_checklist")
    def test_restricted_level_also_blocks(self, mock_checklist):
        mock_checklist.return_value = {
            "success": True, "layer_name": "beneficiaries",
            "categories": {
                "cartography": {"mandatory_elements_missing": []},
                "disclosure": {"level": "RESTRICTED"},
            },
        }
        layer = FakeLayer()
        set_initial_status(layer, status="CARTOGRAPHY_READY")
        result = advance_dataset_status(layer, "PUBLICATION_READY", layout_name="Layout_SITREP")
        self.assertIn("error", result)

    @patch("cartogen_ai.core.agent.tools.qa_checklist_tools.generate_map_product_qa_checklist")
    def test_override_with_note_bypasses_a_failed_map_qa_check(self, mock_checklist):
        mock_checklist.return_value = {
            "success": True, "layer_name": "beneficiaries",
            "categories": {
                "cartography": {"mandatory_elements_missing": []},
                "disclosure": {"level": "SENSITIVE"},
            },
        }
        layer = FakeLayer()
        set_initial_status(layer, status="CARTOGRAPHY_READY")
        result = advance_dataset_status(
            layer, "PUBLICATION_READY", layout_name="Layout_SITREP",
            override=True, note="Disclosure reviewed and approved for this authorized audience",
        )
        self.assertTrue(result["success"])
        self.assertEqual(get_dataset_status(layer)["status"], "PUBLICATION_READY")

    def test_no_layout_name_falls_through_to_ordinary_note_requirement(self):
        # No layout_name supplied -- must behave exactly like any other
        # transition with no automated check at all, not like a map_qa
        # check that has nothing to check against.
        layer = FakeLayer()
        set_initial_status(layer, status="CARTOGRAPHY_READY")
        without_note = advance_dataset_status(layer, "PUBLICATION_READY")
        self.assertIn("error", without_note)
        with_note = advance_dataset_status(layer, "PUBLICATION_READY", note="reviewed manually, no layout yet")
        self.assertTrue(with_note["success"])


class TestStatusOrderConstant(unittest.TestCase):
    def test_status_order_matches_review_doc(self):
        self.assertEqual(
            STATUS_ORDER,
            ["INGESTED", "STAGED", "VALIDATED", "ANALYSIS_READY", "CARTOGRAPHY_READY", "PUBLICATION_READY"],
        )


if __name__ == "__main__":
    unittest.main()
