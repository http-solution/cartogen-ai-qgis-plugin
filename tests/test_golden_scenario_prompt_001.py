"""
Golden Scenario GS-PROMPT-001: Natural-Language Intent -> Exact Humanitarian Analysis Contract Mapping.

Validates the complete positive semantic translation:
Human Request:
"Show the population outside 60-minute health-service access in Admin 2 areas."
      ↓
Contract Parsing:
- objective: population_access_gap
- cluster_sector: health
- admin_level: 2
- travel_cost: 60.0
- travel_unit: minutes
- population_measure: population
- expected_outputs: map_symbology=True, dashboard_kpis=True, export_deliverable=True
- unresolved_parameters: [] (Contract valid, no HALT needed)
      ↓
Tool Selection / Routing:
- Identifies 'population_access_gap' as primary tool
- Generates reproducible Analysis ID (e.g. 'HUM-YYYYMMDD-...')
- Validates that every semantic parameter survives the translation intact.
"""

import unittest
from cartogen_ai.core.validators.humanitarian_contract import (
    parse_humanitarian_intent,
    generate_analysis_id,
    check_contract_for_tool,
)


class TestGoldenScenarioPrompt001(unittest.TestCase):
    def test_gs_prompt_001_complete_positive_intent_mapping(self):
        query = "Show the population outside 60-minute health-service access in Admin 2 areas, with a map and summary statistics."

        # 1. Parse natural-language intent to contract
        contract = parse_humanitarian_intent(query)
        self.assertIsNotNone(contract)

        # 2. Validate extracted semantic parameters
        self.assertEqual(contract.objective, "population_access_gap")
        self.assertEqual(contract.humanitarian_context.cluster_sector, "health")
        self.assertEqual(contract.geography.admin_level, 2)
        self.assertEqual(contract.humanitarian_context.unit_of_measurement, "population")

        thresholds = contract.methodology.thresholds
        self.assertEqual(thresholds.get("travel_cost"), 60.0)
        self.assertEqual(thresholds.get("travel_unit"), "minutes")

        # 3. Assert deliverables
        self.assertTrue(contract.expected_outputs.map_symbology)
        self.assertTrue(contract.expected_outputs.dashboard_kpis)
        self.assertEqual(contract.expected_outputs.output_format, "gpkg")

        # 4. Assert contract validates with 0 unresolved parameters (no HALT_AND_CLARIFY needed)
        val_res = contract.validate()
        self.assertTrue(val_res["valid"], f"Validation failed: {val_res}")
        self.assertFalse(val_res["needs_clarification"])
        self.assertEqual(len(contract.unresolved_parameters), 0)

        # 5. Check tool gate: with travel_cost=60, check_contract_for_tool passes cleanly
        tool_args = {
            "facility_layer": "hospitals",
            "road_network_layer": "roads",
            "population_raster_layer": "worldpop",
            "area_layer": "admin2_districts",
            "travel_cost": thresholds["travel_cost"],
        }
        gate_res = check_contract_for_tool("population_access_gap", tool_args)
        self.assertIsNone(gate_res)  # None indicates tool execution approved

        # 6. Provenance & Analysis ID generation
        analysis_id = generate_analysis_id(contract)
        self.assertTrue(analysis_id.startswith("HUM-"))
        self.assertIn("-", analysis_id)
        self.assertEqual(len(analysis_id.split("-")), 3)


if __name__ == "__main__":
    unittest.main()
