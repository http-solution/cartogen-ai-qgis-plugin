# -*- coding: utf-8 -*-
"""Tests for core/models/plan_gate.py -- IMPLEMENTATION_TRACKER.md §1.6, option (b)."""
import unittest

from cartogen_ai.core.models.plan_gate import PlanValidationGate


class TestRequiresPlan(unittest.TestCase):
    def test_delete_classified_tool_requires_a_plan(self):
        self.assertTrue(PlanValidationGate.requires_plan("remove_layer"))

    def test_publish_classified_tool_requires_a_plan(self):
        self.assertTrue(PlanValidationGate.requires_plan("export_to_csv"))

    def test_create_classified_tool_does_not_require_a_plan(self):
        self.assertFalse(PlanValidationGate.requires_plan("add_point_layer"))

    def test_read_classified_tool_does_not_require_a_plan(self):
        self.assertFalse(PlanValidationGate.requires_plan("get_layers"))

    def test_unknown_tool_name_fails_open_not_closed(self):
        self.assertFalse(PlanValidationGate.requires_plan("definitely_not_a_real_tool"))


class TestCheck(unittest.TestCase):
    def test_disabled_never_blocks_even_a_delete_tool(self):
        gate = PlanValidationGate()
        self.assertIsNone(gate.check("remove_layer", enabled=False))

    def test_enabled_blocks_delete_tool_before_any_plan(self):
        gate = PlanValidationGate()
        res = gate.check("remove_layer", enabled=True)
        self.assertEqual(res["status"], "PLAN_REQUIRED")
        self.assertTrue(res["requires_plan"])
        self.assertEqual(res["tool_name"], "remove_layer")
        self.assertIn("create_plan", res["message"])

    def test_enabled_never_blocks_a_read_tool(self):
        gate = PlanValidationGate()
        self.assertIsNone(gate.check("get_layers", enabled=True))

    def test_enabled_never_blocks_a_create_tool(self):
        gate = PlanValidationGate()
        self.assertIsNone(gate.check("add_point_layer", enabled=True))

    def test_after_mark_plan_created_the_same_delete_call_proceeds(self):
        gate = PlanValidationGate()
        self.assertIsNotNone(gate.check("remove_layer", enabled=True))

        gate.mark_plan_created()

        self.assertIsNone(gate.check("remove_layer", enabled=True))

    def test_a_plan_covers_every_gated_tool_this_turn_not_just_the_one_that_triggered_it(self):
        gate = PlanValidationGate()
        gate.mark_plan_created()

        self.assertIsNone(gate.check("remove_layer", enabled=True))
        self.assertIsNone(gate.check("export_to_csv", enabled=True))
        self.assertIsNone(gate.check("execute_pyqgis_script", enabled=True))

    def test_reset_clears_an_established_plan(self):
        gate = PlanValidationGate()
        gate.mark_plan_created()
        self.assertTrue(gate.has_plan())

        gate.reset()

        self.assertFalse(gate.has_plan())
        self.assertIsNotNone(gate.check("remove_layer", enabled=True))


if __name__ == "__main__":
    unittest.main()
