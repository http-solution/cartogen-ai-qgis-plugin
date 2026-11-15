# -*- coding: utf-8 -*-
"""
Golden Scenario GS-PROMPT-002: Mandatory Contract Execution Gate & HALT & CLARIFY Verification.

Validates:
- Ambiguous humanitarian requests or missing critical parameters (e.g. population_access_gap missing travel_cost)
  are intercepted by the mandatory Humanitarian Analysis Contract gate.
- Prevents LLM tool execution from proceeding with invented defaults (Rule 37).
- Returns structured HALT_AND_CLARIFY status with actionable clarification prompts.
"""

import unittest
from cartogen_ai.core.validators.humanitarian_contract import check_contract_for_tool


class TestGoldenScenarioPrompt002(unittest.TestCase):
    def test_gs_prompt_002_halt_and_clarify_on_missing_travel_cost(self):
        # Scenario: Agent calls population_access_gap without specifying travel_cost
        args_missing_cost = {
            "facility_layer": "health_facilities",
            "road_network_layer": "roads",
            "population_raster_layer": "pop_grid",
            "area_layer": "districts",
            # travel_cost missing!
        }

        gate_res = check_contract_for_tool("population_access_gap", args_missing_cost)
        self.assertIsNotNone(gate_res)
        self.assertEqual(gate_res["status"], "HALT_AND_CLARIFY")
        self.assertTrue(gate_res["needs_clarification"])
        self.assertEqual(gate_res["parameter"], "travel_cost")
        self.assertIn("Rule 37", gate_res["message"])

        # Scenario: When travel_cost is explicitly provided (e.g. 60 minutes)
        args_with_cost = {
            "facility_layer": "health_facilities",
            "road_network_layer": "roads",
            "population_raster_layer": "pop_grid",
            "area_layer": "districts",
            "travel_cost": 60,
        }
        gate_pass = check_contract_for_tool("population_access_gap", args_with_cost)
        self.assertIsNone(gate_pass)  # Pass through gate to PyQGIS execution


if __name__ == "__main__":
    unittest.main()
