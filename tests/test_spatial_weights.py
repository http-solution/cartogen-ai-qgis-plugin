"""PLAN-023 R2-1: spatial weights (pure). Offline, no QGIS, no numpy. Polygons are built as unit squares on a grid so every expected neighbour count is countable by hand."""
import unittest
from typing import ClassVar

from cartogen_ai.core.agent.tools import _spatial_weights as sw


def square(x, y, size=1.0):
    return [[(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)]]


def grid(rows, cols):
    return [square(c, r) for r in range(rows) for c in range(cols)]


class TestContiguity(unittest.TestCase):
    def test_on_a_3_by_3_grid_the_centre_has_8_queen_and_4_rook_neighbours_a_corner_3_and_2(self):
        queen = sw.contiguity(grid(3, 3), "queen")
        rook = sw.contiguity(grid(3, 3), "rook")
        self.assertEqual(len(queen[4]), 8)
        self.assertEqual(len(rook[4]), 4)
        self.assertEqual(len(queen[0]), 3)
        self.assertEqual(len(rook[0]), 2)
        self.assertEqual(rook[4], [1, 3, 5, 7])

    def test_the_link_counts_of_a_4_by_4_grid(self):
        # rook: 24 shared edges -> 48 links; queen adds 18 diagonal pairs -> 48 + 36 = 84 links
        self.assertEqual(sw.link_count(sw.contiguity(grid(4, 4), "rook")), 48)
        self.assertEqual(sw.link_count(sw.contiguity(grid(4, 4), "queen")), 84)

    def test_contiguity_is_symmetric_and_sorted(self):
        for mode in ("queen", "rook"):
            nb = sw.contiguity(grid(3, 4), mode)
            for i, row in enumerate(nb):
                self.assertEqual(row, sorted(row))
                for j in row:
                    self.assertIn(i, nb[j])

    def test_two_squares_touching_only_at_a_corner_are_queen_but_not_rook_neighbours(self):
        polygons = [square(0, 0), square(1, 1)]
        self.assertEqual(sw.contiguity(polygons, "queen"), [[1], [0]])
        self.assertEqual(sw.contiguity(polygons, "rook"), [[], []])

    def test_a_polygon_far_away_is_an_island(self):
        polygons = [square(0, 0), square(1, 0), square(10, 10)]
        nb = sw.contiguity(polygons, "rook")
        self.assertEqual(sw.islands(nb), [2])
        self.assertEqual(sw.components(nb), 2)

    def test_a_t_junction_is_not_detected_and_shows_up_as_an_island(self):
        # the second square's corner lies on the middle of the first square's right edge: no shared corner point
        polygons = [square(0, 0, 2.0), square(2, 0.5, 0.5)]
        self.assertEqual(sw.islands(sw.contiguity(polygons, "queen")), [0, 1])

    def test_corners_are_matched_within_the_tolerance_and_not_beyond_it(self):
        near = [square(0, 0), [[(1 + 1e-12, 0), (2, 0), (2, 1), (1 + 1e-12, 1), (1 + 1e-12, 0)]]]
        far = [square(0, 0), [[(1.001, 0), (2, 0), (2, 1), (1.001, 1), (1.001, 0)]]]
        self.assertEqual(sw.contiguity(near, "rook"), [[1], [0]])
        self.assertEqual(sw.contiguity(far, "rook"), [[], []])

    def test_a_multipart_polygon_counts_every_part(self):
        multi = square(0, 0) + square(5, 0)
        polygons = [multi, square(1, 0), square(6, 0)]
        self.assertEqual(sw.contiguity(polygons, "rook"), [[1, 2], [0], [0]])

    def test_a_hole_ring_counts_as_a_boundary(self):
        outer = [(0, 0), (3, 0), (3, 3), (0, 3), (0, 0)]
        hole = [(1, 1), (1, 2), (2, 2), (2, 1), (1, 1)]
        plug = square(1, 1)
        self.assertEqual(sw.contiguity([[outer, hole], plug], "rook"), [[1], [0]])

    def test_an_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            sw.contiguity(grid(2, 2), "bishop")


class TestPointWeights(unittest.TestCase):
    POINTS: ClassVar[list] = [(0, 0), (1, 0), (2, 0), (10, 0)]

    def test_knn_takes_the_k_nearest_other_points(self):
        self.assertEqual(sw.knn(self.POINTS, 1), [[1], [0], [1], [2]])
        self.assertEqual(sw.knn(self.POINTS, 2), [[1, 2], [0, 2], [0, 1], [1, 2]])

    def test_knn_is_not_symmetric_and_every_row_has_exactly_k(self):
        nb = sw.knn(self.POINTS, 1)
        self.assertIn(2, nb[3])
        self.assertNotIn(3, nb[2])
        self.assertTrue(all(len(r) == 2 for r in sw.knn(self.POINTS, 2)))

    def test_knn_breaks_a_tie_by_position(self):
        self.assertEqual(sw.knn([(0, 0), (1, 0), (-1, 0)], 1)[0], [1])

    def test_knn_refuses_a_bad_k(self):
        for k in (0, 4, -1, 1.5, True, None):
            with self.assertRaises(ValueError, msg=repr(k)):
                sw.knn(self.POINTS, k)

    def test_a_distance_band_is_inclusive_and_leaves_an_island(self):
        nb = sw.distance_band(self.POINTS, 1.0)
        self.assertEqual(nb, [[1], [0, 2], [1], []])
        self.assertEqual(sw.islands(nb), [3])
        self.assertEqual(sw.distance_band(self.POINTS, 2.0)[0], [1, 2])

    def test_a_distance_band_refuses_a_bad_distance(self):
        for d in (0, -1, None, True, float("inf"), "5"):
            with self.assertRaises(ValueError, msg=repr(d)):
                sw.distance_band(self.POINTS, d)


class TestStandardise(unittest.TestCase):
    NB: ClassVar[list] = [[1, 2], [0], [0], []]

    def test_row_standardisation_makes_every_non_empty_row_sum_to_one(self):
        rows = sw.standardise(self.NB, "row")
        for row in rows[:3]:
            self.assertAlmostEqual(sum(w for _j, w in row), 1.0)
        self.assertEqual(rows[0], [(1, 0.5), (2, 0.5)])
        self.assertEqual(rows[3], [])

    def test_binary_gives_one_per_link(self):
        self.assertEqual(sw.standardise(self.NB, "binary")[0], [(1, 1.0), (2, 1.0)])

    def test_an_unknown_style_is_refused(self):
        with self.assertRaises(ValueError):
            sw.standardise(self.NB, "variance")

    def test_summaries(self):
        self.assertEqual(sw.link_count(self.NB), 4)
        self.assertEqual(sw.mean_neighbours(self.NB), 1.0)
        self.assertEqual(sw.islands(self.NB), [3])
        self.assertEqual(sw.components(self.NB), 2)
        self.assertEqual(sw.mean_neighbours([]), 0.0)

    def test_a_one_way_link_still_joins_two_features_into_one_group(self):
        self.assertEqual(sw.components([[1], []]), 1)


if __name__ == "__main__":
    unittest.main()
