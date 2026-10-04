# -*- coding: utf-8 -*-
"""Partial-edge costs for the single-tree travel-time matrix (audit F16, #152), offline pure parts.
The graph work needs QGIS: tests/test_partial_edge_costs_live.py."""
import unittest

from cartogen_ai.core.agent.tools import logistics_tools as lt


class TestProjectOnSegment(unittest.TestCase):
    def test_midpoint_projection(self):
        t, dist = lt.project_on_segment(5, 3, 0, 0, 10, 0)
        self.assertAlmostEqual(t, 0.5)
        self.assertAlmostEqual(dist, 3.0)

    def test_beyond_the_ends_is_clamped(self):
        self.assertEqual(lt.project_on_segment(-4, 0, 0, 0, 10, 0)[0], 0.0)
        self.assertEqual(lt.project_on_segment(14, 0, 0, 0, 10, 0)[0], 1.0)

    def test_zero_length_segment(self):
        self.assertEqual(lt.project_on_segment(1, 1, 2, 2, 2, 2)[0], 0.0)


class TestPartialEdgeCost(unittest.TestCase):
    """The acceptance case from #152: a 1,000 m road, points at 490 m and 510 m, origin at one end."""

    def test_points_either_side_of_the_middle_cost_their_own_distance(self):
        # origin at A (cost 0); B costs 1000; both directions exist
        self.assertAlmostEqual(lt.partial_edge_cost(0.0, 1000.0, 1000.0, 1000.0, 0.49), 490.0)
        self.assertAlmostEqual(lt.partial_edge_cost(0.0, 1000.0, 1000.0, 1000.0, 0.51), 510.0)

    def test_the_cheaper_way_in_wins(self):
        # A is reached for 900 and B for 100 on a 1,000 m edge: a point 20% from A is 80% from B
        self.assertAlmostEqual(lt.partial_edge_cost(900.0, 100.0, 1000.0, 1000.0, 0.2), min(900 + 200, 100 + 800))

    def test_one_way_edge_only_allows_its_own_direction(self):
        # only A->B exists: entering at B and walking back is not allowed
        self.assertAlmostEqual(lt.partial_edge_cost(0.0, 5.0, 1000.0, None, 0.3), 300.0)
        # only B->A exists and A is the (cost 0) origin side: the point is reached through B
        self.assertAlmostEqual(lt.partial_edge_cost(0.0, 1000.0, None, 1000.0, 0.3), 1000.0 + 0.7 * 1000.0)

    def test_unreachable_ends_give_none(self):
        self.assertIsNone(lt.partial_edge_cost(lt.UNREACHABLE_COST, lt.UNREACHABLE_COST, 10.0, 10.0, 0.5))
        self.assertIsNone(lt.partial_edge_cost(0.0, 0.0, None, None, 0.5))


class TestNativeKeyMatching(unittest.TestCase):
    def test_parse_xy_reads_the_first_two_numbers(self):
        self.assertEqual(lt.parse_xy("44.0049, 15.0"), (44.0049, 15.0))
        self.assertEqual(lt.parse_xy("POINT(-1.5e1 2)"), (-15.0, 2.0))
        self.assertIsNone(lt.parse_xy("nothing"))

    def test_nearest_candidate_within_tolerance(self):
        candidates = [(7, 0.0, 0.0), (9, 10.0, 0.0)]
        self.assertEqual(lt.match_destination_key(9.99995, 0.0, candidates, 1e-3), 9)
        self.assertIsNone(lt.match_destination_key(5.0, 0.0, candidates, 1e-3))


if __name__ == "__main__":
    unittest.main()
