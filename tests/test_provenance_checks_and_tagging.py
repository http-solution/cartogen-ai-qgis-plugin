"""PLAN-051 follow-up (hand-test run 2026-11-03, rows W3/W9 and the W11 evidence): two smaller defects, tested first.

D3: the provenance record's `qa_status` is the manual dataset-lifecycle gate (empty unless the status tools were used), so a layer whose result
checks had run was described as having "no status, checks, or history recorded". The record now also carries `result_checks`, the automatic checks
stored on the layer, and its description says the two are different things.
D4: tagging tools write a record about a layer, not a result; the result gate recorded 'The output has 3 features' against a layer after
set_layer_sensitivity."""
import json
import unittest

from cartogen_ai.core.agent import provenance, result_gate
from cartogen_ai.core.agent.tools.registry import TOOLS_SCHEMA
import cartogen_ai.core.agent.agent_orchestrator  # noqa: F401  (registers every tool)


class Layer:
    def __init__(self, name="smoke_admin"):
        self._name, self._props = name, {}

    def name(self):
        return self._name

    def customProperty(self, key, default=""):
        return self._props.get(key, default)

    def setCustomProperty(self, key, value):
        self._props[key] = value


class TestProvenanceCarriesTheStoredResultChecks(unittest.TestCase):
    def test_a_layer_with_stored_checks_shows_them_beside_the_empty_lifecycle_status(self):
        layer = Layer()
        layer.setCustomProperty("cartogen/checks", json.dumps([{"tool": "calculate_severity_index", "at": "2026-11-03 10:00:00", "sampled_of": None,
                                                                  "checks": [{"id": "geometry", "status": "pass", "detail": "All 3 valid."}]}]))
        record = provenance.build_provenance_record(layer)
        self.assertEqual(record["qa_status"]["status"], None)
        self.assertEqual(record["result_checks"][0]["tool"], "calculate_severity_index")
        self.assertEqual(record["result_checks"][0]["checks"][0]["status"], "pass")

    def test_no_stored_checks_is_an_empty_list_and_a_damaged_property_does_not_break_the_record(self):
        self.assertEqual(provenance.build_provenance_record(Layer())["result_checks"], [])
        broken = Layer()
        broken.setCustomProperty("cartogen/checks", "{not json")
        self.assertEqual(provenance.build_provenance_record(broken)["result_checks"], [])

    def test_the_property_key_is_the_one_the_result_gate_writes(self):
        self.assertEqual(provenance.CHECKS_PROPERTY_KEY, result_gate.CHECKS_PROPERTY_KEY)

    def test_the_tool_description_says_the_two_records_are_different(self):
        text = next(i["function"]["description"] for i in TOOLS_SCHEMA if i["function"]["name"] == "get_provenance_record")
        self.assertIn("result_checks", text)
        self.assertIn("qa_status", text)


class TestTaggingToolsAreNotResults(unittest.TestCase):
    def test_a_successful_tagging_call_is_not_eligible_for_result_checks(self):
        result = {"success": True, "layer_name": "smoke_zones", "level": "RESTRICTED"}
        for tool in ("set_layer_sensitivity", "set_dataset_status", "advance_dataset_status", "set_layer_confidence", "set_layer_metadata"):
            self.assertFalse(result_gate.eligible("MODIFY", result, tool), tool)

    def test_other_modifying_tools_are_still_checked(self):
        result = {"success": True, "layer_name": "smoke_admin"}
        self.assertTrue(result_gate.eligible("MODIFY", result, "calculate_severity_index"))
        self.assertTrue(result_gate.eligible("MODIFY", result))        # the old two-argument call still works

    def test_the_listed_tools_exist_and_are_classified_as_changes(self):
        from cartogen_ai.core import tool_operations
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        for tool in result_gate.RECORD_ONLY_TOOLS:
            self.assertIn(tool, TOOL_REGISTRY)
            self.assertIn(tool_operations.get_tool_operation_type(tool), ("CREATE", "MODIFY"), tool)


if __name__ == "__main__":
    unittest.main()
