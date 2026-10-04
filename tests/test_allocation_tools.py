# -*- coding: utf-8 -*-
"""H8 allocation envelope: the arithmetic, offline. The layer work needs QGIS (tests/test_allocation_tools_live.py)."""
import random
import unittest

from cartogen_ai.core.agent.tools import allocation_tools as at


class TestAllocate(unittest.TestCase):
    def test_proportional_split_uses_the_whole_budget(self):
        out = at.allocate([1, 2, 3, 4], 1000)
        self.assertEqual(out["amounts"], [100.0, 200.0, 300.0, 400.0])
        self.assertEqual(out["unallocated"], 0.0)

    def test_a_ceiling_gives_the_capped_area_exactly_its_ceiling_and_resplits_the_rest(self):
        out = at.allocate([1, 1, 1, 10], 1000, max_share=0.4)
        self.assertEqual(out["amounts"], [200.0, 200.0, 200.0, 400.0])
        self.assertEqual(out["capped"], [3])

    def test_a_cascade_of_ceilings(self):
        out = at.allocate([1, 2, 4, 40], 1000, max_share=0.3)
        self.assertAlmostEqual(sum(out["amounts"]), 1000.0)
        self.assertTrue(all(a <= 300.0 + 1e-9 for a in out["amounts"]))
        self.assertEqual(out["capped"], [3] if out["amounts"][2] < 300 - 1e-9 else [2, 3])

    def test_ceilings_that_cannot_absorb_the_budget_leave_it_unallocated_not_over_a_ceiling(self):
        out = at.allocate([1, 1], 1000, max_share=0.3)
        self.assertEqual(out["amounts"], [300.0, 300.0])
        self.assertAlmostEqual(out["unallocated"], 400.0)
        self.assertTrue(any("unallocated" in n for n in out["notes"]))

    def test_floor_is_guaranteed_to_positive_weights_only(self):
        out = at.allocate([0, 1, 9], 1000, min_amount=100)
        self.assertEqual(out["amounts"][0], 0.0)
        self.assertGreaterEqual(out["amounts"][1], 100.0)
        self.assertAlmostEqual(sum(out["amounts"]), 1000.0)

    def test_impossible_floor_ceiling_budget_and_no_weight_are_errors(self):
        self.assertIn("error", at.allocate([1, 1], 100, min_amount=60))
        self.assertIn("error", at.allocate([1, 1], 100, max_share=0.1, min_amount=20))
        self.assertIn("error", at.allocate([0, 0], 100))
        self.assertIn("error", at.allocate([1], 0))
        self.assertIn("error", at.allocate([1], "lots"))
        self.assertIn("error", at.allocate([1], 10, max_share=1.5))

    def test_rounding_keeps_the_total_and_respects_the_unit(self):
        out = at.allocate([1, 2, 3], 1000, rounding=100)
        self.assertEqual(out["amounts"], [200.0, 300.0, 500.0])
        self.assertEqual(sum(out["amounts"]), 1000.0)

    def test_random_inputs_never_break_the_invariants(self):
        rng = random.Random(7)
        for _ in range(300):
            n = rng.randint(1, 12)
            weights = [rng.choice([0, 0, rng.random() * 10]) for _ in range(n)]
            if not any(w > 0 for w in weights):
                continue
            budget = rng.choice([100, 1000, 12345.67])
            share = rng.choice([None, 0.2, 0.5, 1.0])
            rounding = rng.choice([None, 1, 50])
            out = at.allocate(weights, budget, max_share=share, rounding=rounding)
            if "error" in out:
                continue
            amounts = out["amounts"]
            self.assertAlmostEqual(sum(amounts) + out["unallocated"], budget, places=4)
            self.assertTrue(all(a >= 0 for a in amounts))
            self.assertTrue(all(a == 0 for a, w in zip(amounts, weights) if w == 0))
            if share is not None:
                self.assertTrue(all(a <= share * budget + 1e-6 for a in amounts), (weights, budget, share, rounding, amounts))


class TestWeightFor(unittest.TestCase):
    def test_need_times_population_with_exponent(self):
        self.assertEqual(at.weight_for(0.5, 200, 2), (50.0, None))
        self.assertEqual(at.weight_for(3, None), (3.0, None))

    def test_missing_negative_and_below_threshold_are_excluded_with_a_reason(self):
        self.assertEqual(at.weight_for(None, 1)[1], "missing or non-numeric need")
        self.assertEqual(at.weight_for("x", 1)[0], None)
        self.assertEqual(at.weight_for(-1, 1)[1], "negative need")
        self.assertEqual(at.weight_for(0.1, 1, 1, 0.2)[1], "need below the exclusion threshold")
        self.assertEqual(at.weight_for(0.5, None, 1)[0], 0.5)
        self.assertEqual(at.weight_for(0.5, "n/a")[1], "missing or non-numeric population")
        self.assertEqual(at.weight_for(0.5, -5)[1], "negative population")


class TestToolIsWired(unittest.TestCase):
    def test_registered_classified_and_routed(self):
        from cartogen_ai.core.agent import tool_operations
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        self.assertIn("calculate_allocation_envelope", TOOL_REGISTRY)
        self.assertEqual(tool_operations.get_tool_operation_type("calculate_allocation_envelope"), tool_operations.MODIFY)

    def test_the_allocation_look_exists(self):
        from cartogen_ai.core.agent.tools import humanitarian_style as h
        self.assertIn("allocation", h.LOOKS)
        self.assertEqual(h.look_hint("L", "allocation", "amt")["args"]["look"], "allocation")

    def test_without_qgis_it_says_so(self):
        if at.QGIS_AVAILABLE:
            self.skipTest("QGIS present")
        self.assertIn("QGIS not available", at.calculate_allocation_envelope("L", 100, "need")["error"])


if __name__ == "__main__":
    unittest.main()
