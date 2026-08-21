# -*- coding: utf-8 -*-
"""Tests for obfuscate_sensitive_points (agent/tools/vector_tools.py) -- a
Do No Harm geoprivacy safeguard for plotting sensitive point data (GBV
survivors, individual IDP households, protection incidents). The two pure
helpers (_uniform_disk_offset, _grid_snap) are the load-bearing math and are
tested rigorously, including a Monte Carlo check that the jitter distribution
is genuinely uniform-area and not the common "uniform radius" bug that would
concentrate obfuscated points near their true location."""
import math
import random
import statistics
import unittest

from agent.tools.vector_tools import (
    _uniform_disk_offset, _grid_snap, obfuscate_sensitive_points,
)


class TestUniformDiskOffset(unittest.TestCase):
    def test_zero_radius_is_a_true_no_op(self):
        self.assertEqual(_uniform_disk_offset(0, random.Random(1)), (0.0, 0.0))
        self.assertEqual(_uniform_disk_offset(-5, random.Random(1)), (0.0, 0.0))

    def test_offset_never_exceeds_the_requested_radius(self):
        rng = random.Random(123)
        radius = 50.0
        for _ in range(2000):
            dx, dy = _uniform_disk_offset(radius, rng)
            self.assertLessEqual(math.hypot(dx, dy), radius + 1e-9)

    def test_same_seed_is_reproducible(self):
        a = [_uniform_disk_offset(10, random.Random(7)) for _ in range(5)]
        b = [_uniform_disk_offset(10, random.Random(7)) for _ in range(5)]
        self.assertEqual(a, b)

    def test_distribution_is_uniform_area_not_uniform_radius(self):
        # For a uniform-AREA distribution over a disk of radius R,
        # P(r < R/2) = (R/2)^2 / R^2 = 0.25 -- area scales with r^2. A common
        # bug (drawing the radius itself from a uniform distribution, paired
        # with a uniform angle) instead gives P(r < R/2) = 0.5, since it
        # ignores that an annulus at larger r covers more area than one at
        # smaller r for the same radial width. This is the check that
        # distinguishes the two implementations, not just "stays in bounds."
        rng = random.Random(42)
        radius = 100.0
        n = 20000
        within_half = sum(
            1 for _ in range(n)
            if math.hypot(*_uniform_disk_offset(radius, rng)) < radius / 2
        )
        fraction = within_half / n
        self.assertAlmostEqual(fraction, 0.25, delta=0.02)

    def test_angle_coverage_is_not_biased_to_one_side(self):
        # Mean of many offsets should be close to (0, 0) if angles are
        # genuinely uniform over the full circle, not clustered in one quadrant.
        rng = random.Random(99)
        offsets = [_uniform_disk_offset(10, rng) for _ in range(20000)]
        mean_x = statistics.mean(o[0] for o in offsets)
        mean_y = statistics.mean(o[1] for o in offsets)
        self.assertAlmostEqual(mean_x, 0.0, delta=0.3)
        self.assertAlmostEqual(mean_y, 0.0, delta=0.3)


class TestGridSnap(unittest.TestCase):
    def test_snaps_to_cell_centroid(self):
        self.assertEqual(_grid_snap(12, 12, 10), (15.0, 15.0))

    def test_boundary_belongs_to_the_upper_cell(self):
        # x=10.0 with cell_size=10 is the start of cell 1 ([10, 20)), not the
        # end of cell 0 ([0, 10)) -- floor(10/10)=1, matching Python's own
        # floor-division convention used throughout this codebase.
        self.assertEqual(_grid_snap(10.0, 0.0, 10), (15.0, 5.0))
        self.assertEqual(_grid_snap(9.999, 0.0, 10), (5.0, 5.0))

    def test_negative_coordinates_use_floor_not_truncation(self):
        # floor(-0.3) = -1, not 0 -- truncation-toward-zero would put x=-3 in
        # the wrong cell relative to x=3.
        self.assertEqual(_grid_snap(-3, -3, 10), (-5.0, -5.0))

    def test_points_in_the_same_cell_collapse_to_an_identical_output(self):
        # The actual privacy property this method exists to provide: multiple
        # true locations must become indistinguishable after snapping.
        a = _grid_snap(10.001, 10.001, 10)
        b = _grid_snap(19.999, 19.999, 10)
        self.assertEqual(a, b)

    def test_points_in_different_cells_do_not_collapse(self):
        a = _grid_snap(1, 1, 10)
        b = _grid_snap(11, 11, 10)
        self.assertNotEqual(a, b)


class TestObfuscateSensitivePointsTool(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = obfuscate_sensitive_points("layer", "jitter", radius=100)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


if __name__ == "__main__":
    unittest.main()
