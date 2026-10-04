# -*- coding: utf-8 -*-
"""H1 apply_network_barriers: the pure rules and the early validation. The distance work needs QGIS (tests/test_barrier_tools_live.py)."""
import unittest

from cartogen_ai.core.agent.tools import barrier_tools as b


class TestUtmEpsg(unittest.TestCase):
    def test_known_zones(self):
        self.assertEqual(b.utm_epsg(44.2, 15.35), 32638)    # Sanaa, Yemen
        self.assertEqual(b.utm_epsg(-0.1, 51.5), 32630)     # London
        self.assertEqual(b.utm_epsg(151.2, -33.9), 32756)   # Sydney (southern hemisphere)

    def test_edges_of_the_longitude_range(self):
        self.assertEqual(b.utm_epsg(-180.0, 10), 32601)
        self.assertEqual(b.utm_epsg(179.99, 10), 32660)
        self.assertEqual(b.utm_epsg(180.0, 10), 32601)


class TestEffectiveSpeed(unittest.TestCase):
    def test_a_miss_keeps_the_base_speed(self):
        self.assertEqual(b.effective_speed(50.0, False, "block", 0.25), 50.0)

    def test_block_gives_the_floor(self):
        self.assertEqual(b.effective_speed(50.0, True, "block", 0.25), b._BLOCKED_SPEED_KMH)

    def test_penalise_scales_and_never_goes_below_the_floor(self):
        self.assertEqual(b.effective_speed(40.0, True, "penalise", 0.25), 10.0)
        self.assertEqual(b.effective_speed(0.2, True, "penalise", 0.25), b._BLOCKED_SPEED_KMH)


class TestValidateOptions(unittest.TestCase):
    def test_valid(self):
        self.assertIsNone(b.validate_options("block", 50, 0.25))
        self.assertIsNone(b.validate_options("penalise", 0, 0.5))

    def test_bad_values(self):
        for args in (("close", 50, 0.25), ("block", -1, 0.25), ("block", "x", 0.25),
                     ("penalise", 50, 0), ("penalise", 50, 1), ("penalise", 50, 1.5), ("penalise", 50, "x")):
            self.assertIsNotNone(b.validate_options(*args), args)

    def test_penalty_factor_is_ignored_for_block(self):
        self.assertIsNone(b.validate_options("block", 50, 99))


class TestNotes(unittest.TestCase):
    def test_always_warns_that_shortest_ignores_the_speed_field(self):
        self.assertTrue(any("shortest" in n for n in b._result_notes("penalise", True)))

    def test_block_note_says_it_is_not_a_true_closure(self):
        self.assertTrue(any("not a true closure" in n for n in b._result_notes("block", True)))
        self.assertFalse(any("not a true closure" in n for n in b._result_notes("penalise", True)))

    def test_missing_speed_field_is_disclosed(self):
        self.assertTrue(any("30 km/h" in n for n in b._result_notes("block", False)))
        self.assertFalse(any("30 km/h" in n for n in b._result_notes("block", True)))


class TestToolIsWired(unittest.TestCase):
    def test_registered_and_classified_as_modifying(self):
        from cartogen_ai.core.agent import tool_operations
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        self.assertIn("apply_network_barriers", TOOL_REGISTRY)
        self.assertEqual(tool_operations.get_tool_operation_type("apply_network_barriers"), tool_operations.MODIFY)

    def test_without_qgis_it_reports_that_plainly(self):
        if b.QGIS_AVAILABLE:
            self.skipTest("QGIS present")
        self.assertIn("error", b.apply_network_barriers("roads", "bridges"))


if __name__ == "__main__":
    unittest.main()
