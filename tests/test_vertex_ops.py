"""PLAN-023 R9-1: the pure vertex-editing helpers, with the plan's square as the known answer. No QGIS and no numpy needed."""
import unittest

from cartogen_ai.core.agent.tools import vertex_ops as vo

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]          # closed ring: 5 vertices, side 10


class TestKnownAnswers(unittest.TestCase):
    def test_the_square_has_area_100(self):
        self.assertEqual(vo.ring_area(SQUARE), 100.0)
        self.assertEqual(vo.ring_area(SQUARE[:-1]), 100.0)            # closed or not

    def test_deleting_vertex_2_leaves_a_triangle_of_area_50(self):
        triangle = [v for i, v in enumerate(SQUARE) if i != 2]
        self.assertEqual(len(triangle), 4)                            # (0,0), (10,0), (0,10), (0,0)
        self.assertEqual(vo.ring_area(triangle), 50.0)

    def test_a_vertex_added_on_an_edge_does_not_change_the_area(self):
        with_midpoint = [*SQUARE[:1], (5, 0), *SQUARE[1:]]
        self.assertEqual(len(with_midpoint), 6)
        self.assertEqual(vo.ring_area(with_midpoint), 100.0)

    def test_moving_a_corner_gives_the_trapezoid_of_area_150(self):
        moved = [(0, 0), (10, 0), (20, 10), (0, 10), (0, 0)]
        self.assertEqual(vo.ring_area(moved), 150.0)                  # (10 + 20) / 2 x 10

    def test_the_perimeter_of_the_square_is_40_and_a_degenerate_ring_has_no_area(self):
        self.assertEqual(vo.path_length(SQUARE), 40.0)
        self.assertEqual(vo.ring_area([(0, 0), (1, 1)]), 0.0)
        self.assertEqual(vo.path_length([(0, 0)]), 0.0)


class TestNearestVertex(unittest.TestCase):
    def test_the_nearest_vertex_and_the_tie_rule(self):
        self.assertEqual(vo.nearest_vertex(SQUARE, 9, 9), (2, 2 ** 0.5))
        self.assertEqual(vo.nearest_vertex(SQUARE, 0.1, 0)[0], 0)
        self.assertEqual(vo.nearest_vertex(SQUARE, 0, 0)[0], 0)        # vertex 4 is the same corner: the lowest index wins

    def test_tolerance_and_empty_input(self):
        self.assertIsNone(vo.nearest_vertex(SQUARE, 5, 5, tolerance=1.0))
        self.assertEqual(vo.nearest_vertex(SQUARE, 9.5, 10, tolerance=1.0)[0], 2)
        self.assertIsNone(vo.nearest_vertex([], 0, 0))


class TestCheckRequest(unittest.TestCase):
    def test_valid_requests(self):
        self.assertIsNone(vo.check_request("delete", index=2))
        self.assertIsNone(vo.check_request("delete", near_x=9, near_y=9, tolerance=2))
        self.assertIsNone(vo.check_request("move", index=2, x=20, y=10))
        self.assertIsNone(vo.check_request("move", near_x=9, near_y=9, x=20, y=10))
        self.assertIsNone(vo.check_request("add", x=5, y=0.2))
        self.assertIsNone(vo.check_request(" ADD ", x="5", y="0"))

    def test_each_wrong_request_says_what_is_missing_or_extra(self):
        self.assertIn("action must be", vo.check_request("insert", index=1))
        self.assertIn("exactly one of index or near", vo.check_request("delete"))
        self.assertIn("exactly one of index or near", vo.check_request("delete", index=1, near_x=1, near_y=1))
        self.assertIn("takes no x and y", vo.check_request("delete", index=1, x=1, y=1))
        self.assertIn("needs x and y: where", vo.check_request("move", index=1))
        self.assertIn("needs x and y: the point", vo.check_request("add"))
        self.assertIn("add takes x and y only", vo.check_request("add", x=1, y=1, index=2))
        self.assertIn("tolerance only applies", vo.check_request("delete", index=1, tolerance=1))

    def test_bad_numbers(self):
        for bad in (-1, 1.5, "x", True):
            self.assertIn("index must be", vo.check_request("delete", index=bad), repr(bad))
        self.assertIn("near_x and near_y", vo.check_request("delete", near_x=1))
        self.assertIn("x and y must both", vo.check_request("move", index=1, x=1))
        self.assertIn("tolerance must be", vo.check_request("delete", near_x=1, near_y=1, tolerance=0))
        self.assertIn("x and y must both", vo.check_request("add", x=float("nan"), y=1))


class TestDescribe(unittest.TestCase):
    def test_sentences(self):
        self.assertEqual(vo.describe("delete", index=2), "Delete vertex 2")
        self.assertEqual(vo.describe("move", index=2, x=20, y=10), "Move vertex 2 to (20, 10)")
        self.assertEqual(vo.describe("move", near=(9, 9), x=20, y=10), "Move the vertex nearest (9, 9) to (20, 10)")
        self.assertEqual(vo.describe("add", x=5, y=0.2), "Add a vertex on the segment nearest (5, 0.2)")


if __name__ == "__main__":
    unittest.main()
