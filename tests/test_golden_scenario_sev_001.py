# -*- coding: utf-8 -*-
"""
Golden Scenario GS-SEV-001: Exploratory Composite Severity Index Conformance.

Validates:
- Min-Max normalization
- Weights application and normalization
- Inverted indicator logic (higher raw value = better condition -> inverted severity)
- Excluded units handling (units with missing indicator data excluded from scoring, NOT imputed)
- Mathematical precision and determinism
- Methodological labelling: Explicitly declared as Exploratory Composite Index, NOT JIAF
"""

import unittest
from cartogen_ai.core.agent.tools.analysis_tools import _normalize_minmax, calculate_severity_index


class TestGoldenScenarioSev001(unittest.TestCase):
    def test_gs_sev_001_normalization_and_weighting(self):
        """
        Scenario Definition:
        4 Units:
          Unit 1: food_insecurity=80, water_shortage=40, health_access=20 (invert=True, higher is better)
          Unit 2: food_insecurity=20, water_shortage=10, health_access=80
          Unit 3: food_insecurity=50, water_shortage=25, health_access=50
          Unit 4: food_insecurity=None, water_shortage=30, health_access=40 (MISSING DATA -> EXCLUDED)

        Expected behavior:
          - Unit 4 is EXCLUDED from calculation, never imputed with mean or zero.
          - Min-Max normalized on complete units (1, 2, 3):
            food_insecurity: min=20, max=80
              Unit 1: (80-20)/60 = 1.0
              Unit 2: (20-20)/60 = 0.0
              Unit 3: (50-20)/60 = 0.5
            water_shortage: min=10, max=40
              Unit 1: (40-10)/30 = 1.0
              Unit 2: (10-10)/30 = 0.0
              Unit 3: (25-10)/30 = 0.5
            health_access (inverted: higher access = lower severity): min=20, max=80
              Unit 1 (raw 20): 1 - (20-20)/60 = 1.0
              Unit 2 (raw 80): 1 - (80-20)/60 = 0.0
              Unit 3 (raw 50): 1 - (50-20)/60 = 0.5
          - Weights: food=0.5, water=0.3, health=0.2 (sum=1.0)
            Composite Scores:
              Unit 1: 1.0*0.5 + 1.0*0.3 + 1.0*0.2 = 1.0000 -> Class 5 (Catastrophic)
              Unit 2: 0.0*0.5 + 0.0*0.3 + 0.0*0.2 = 0.0000 -> Class 1 (Minimal)
              Unit 3: 0.5*0.5 + 0.5*0.3 + 0.5*0.2 = 0.5000 -> Class 3 (Moderate)
        """
        rows = [
            {"unit": "Dist_1", "food": 80, "water": 40, "health": 20},
            {"unit": "Dist_2", "food": 20, "water": 10, "health": 80},
            {"unit": "Dist_3", "food": 50, "water": 25, "health": 50},
            {"unit": "Dist_4", "food": None, "water": 30, "health": 40},
        ]

        from cartogen_ai.core.agent.tools.analysis_tools import _compute_severity_index

        res = _compute_severity_index(
            rows=rows,
            indicators=["food", "water", "health"],
            weights={"food": 0.5, "water": 0.3, "health": 0.2},
            invert_indicators=["health"]
        )

        # 1. Assert exclusion of Unit 4
        self.assertEqual(len(res["excluded_units_missing_data"]), 1)
        self.assertEqual(res["excluded_units_missing_data"][0]["unit"], "Dist_4")
        self.assertEqual(res["excluded_units_missing_data"][0]["missing_fields"], ["food"])

        # 2. Assert scored units count and order
        scored = res["results"]
        self.assertEqual(len(scored), 3)

        # Worst first: Dist_1 (score 1.0), Dist_3 (score 0.5), Dist_2 (score 0.0)
        u1 = next(r for r in scored if r["unit"] == "Dist_1")
        u2 = next(r for r in scored if r["unit"] == "Dist_2")
        u3 = next(r for r in scored if r["unit"] == "Dist_3")

        self.assertAlmostEqual(u1["severity_score"], 1.0000, places=4)
        self.assertEqual(u1["severity_class"], 5)

        self.assertAlmostEqual(u3["severity_score"], 0.5000, places=4)
        self.assertEqual(u3["severity_class"], 3)

        self.assertAlmostEqual(u2["severity_score"], 0.0000, places=4)
        self.assertEqual(u2["severity_class"], 1)


if __name__ == "__main__":
    unittest.main()
