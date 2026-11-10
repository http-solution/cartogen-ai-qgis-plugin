"""PLAN-023 R9-3: the pure line-editing helpers with hand-computed known answers. No QGIS and no numpy needed."""
import unittest

from cartogen_ai.core.agent.tools import line_ops as lo


class TestSnapEnds(unittest.TestCase):
    wall = ("wall", [(10.0, -5.0), (10.0, 5.0)])

    def test_a_line_that_stops_short_is_extended_to_the_other_line(self):
        moves = lo.snap_ends([("a", [(0.0, 0.0), (9.0, 0.0)]), self.wall], 1.5)
        self.assertEqual(moves, {"a": (None, (10.0, 0.0))})

    def test_a_line_that_overshoots_is_trimmed_back_to_where_they_cross(self):
        moves = lo.snap_ends([("a", [(0.0, 0.0), (11.0, 0.0)]), self.wall], 1.5)
        self.assertEqual(moves, {"a": (None, (10.0, 0.0))})

    def test_nothing_moves_beyond_the_tolerance_or_when_already_touching(self):
        self.assertEqual(lo.snap_ends([("a", [(0.0, 0.0), (8.0, 0.0)]), self.wall], 1.5), {})
        self.assertEqual(lo.snap_ends([("a", [(0.0, 0.0), (10.0, 0.0)]), self.wall], 1.5), {})

    def test_the_result_does_not_depend_on_the_order_of_the_features(self):
        a = ("a", [(0.0, 0.0), (9.0, 0.0)])
        self.assertEqual(lo.snap_ends([a, self.wall], 1.5), lo.snap_ends([self.wall, a], 1.5))

    def test_a_line_is_never_snapped_to_itself(self):
        self.assertEqual(lo.snap_ends([("a", [(0.0, 0.0), (1.0, 0.0), (1.0, 0.1), (0.05, 0.1)])], 1.0), {})

    def test_both_ends_can_move(self):
        moves = lo.snap_ends([("a", [(1.0, 0.0), (9.0, 0.0)]), ("l", [(0.0, -5.0), (0.0, 5.0)]), self.wall], 1.5)
        self.assertEqual(moves["a"], ((0.0, 0.0), (10.0, 0.0)))


class TestNearest(unittest.TestCase):
    def test_nearest_point_on_a_polyline(self):
        self.assertEqual(lo.nearest_on_polyline((5.0, 3.0), [(0.0, 0.0), (10.0, 0.0)]), (3.0, (5.0, 0.0)))
        self.assertEqual(lo.nearest_on_polyline((13.0, 4.0), [(0.0, 0.0), (10.0, 0.0)]), (5.0, (10.0, 0.0)))     # beyond the end: the end itself


class TestReverseAndChecks(unittest.TestCase):
    def test_reverse_swaps_the_first_and_last_vertex(self):
        line = [(0, 0), (4, 0), (4, 3)]
        self.assertEqual(lo.reverse_points(line), [(4, 3), (4, 0), (0, 0)])
        self.assertEqual(lo.reverse_points(lo.reverse_points(line)), line)

    def test_offset_checks(self):
        self.assertIsNone(lo.check_offset(2))
        self.assertIsNone(lo.check_offset(-2, "Miter", 16, 3))
        for bad in ({"distance": 0}, {"distance": "x"}, {"distance": 2, "join": "square"}, {"distance": 2, "segments": 0}, {"distance": 2, "segments": 100},
                    {"distance": 2, "miter_limit": 0.5}):
            self.assertIsNotNone(lo.check_offset(**bad), bad)

    def test_snap_and_reshape_checks(self):
        self.assertIsNone(lo.check_snap(0.5))
        self.assertIsNotNone(lo.check_snap(0))
        self.assertIsNotNone(lo.check_snap(None))
        self.assertEqual(lo.check_reshape("LINESTRING(0 5, 10 5)"), ([(0.0, 5.0), (10.0, 5.0)], None))
        self.assertIsNotNone(lo.check_reshape("POLYGON((0 0,1 0,1 1,0 0))")[1])
        self.assertIsNotNone(lo.check_reshape("LINESTRING(0 0)")[1])


if __name__ == "__main__":
    unittest.main()
