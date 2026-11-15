"""Watershed delineation (tools/watershed_delineation.py) on synthetic terrain with known answers. Pure numpy; skipped without numpy."""
import itertools
import math
import unittest

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

if HAVE_NUMPY:
    from cartogen_ai.core.agent.tools import watershed_delineation as wd

DX = DY = 30.0


def two_valleys(rows=80, cols=50, fall=0.5):
    """Two parallel V-shaped valleys (channels at columns 12 and 38) separated by a ridge at column 25; each channel falls `fall` m per row
    toward the south edge. The left valley is the one under test."""
    r, c = np.indices((rows, cols))
    lateral = np.where(c <= 25, 10.0 * np.abs(c - 12), 10.0 * np.abs(c - 38))
    return (rows - r) * fall + lateral


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestKnownTerrain(unittest.TestCase):
    def setUp(self):
        self.dem = two_valleys()
        self.res = wd.delineate(self.dem, DX, DY, row=60, col=12, snap_radius_m=0)

    def test_the_basin_is_the_left_valley_and_nothing_of_the_right_one(self):
        mask = self.res["mask"]
        self.assertTrue(self.res["success"])
        self.assertEqual(self.res["outlet_rc"], (60, 12))
        self.assertFalse(mask[:, 27:].any(), "a cell of the right valley was counted")
        self.assertTrue(mask[:61, :25].all(), "a cell of the left valley upstream of the outlet is missing")
        self.assertFalse(mask[61:, :].any(), "a cell downstream of the outlet was counted")

    def test_area_is_cells_times_cell_area(self):
        self.assertAlmostEqual(self.res["area_km2"], self.res["cells"] * DX * DY / 1e6)
        self.assertGreaterEqual(self.res["cells"], 25 * 61)
        self.assertLessEqual(self.res["cells"], 26 * 61)

    def test_longest_path_runs_from_the_far_corner_to_the_outlet(self):
        path = self.res["path_rc"]
        self.assertEqual(path[-1], (60, 12))
        self.assertEqual(path[0], self.res["upstream_rc"])
        self.assertEqual(self.res["upstream_rc"][0], 0)                     # the farthest cell is on the northern edge
        straight = 60 * DY
        self.assertGreaterEqual(self.res["longest_flow_path_m"], straight)
        # a D8 path cannot be longer than the Manhattan route (60 rows + 12 columns), plus one cell for the tie-breaking wobble on flats
        self.assertLessEqual(self.res["longest_flow_path_m"], straight + 13 * DX)
        steps = [math.hypot((b[1] - a[1]) * DX, (b[0] - a[0]) * DY) for a, b in itertools.pairwise(path)]
        self.assertAlmostEqual(sum(steps), self.res["longest_flow_path_m"], places=6)

    def test_H_and_slope_use_the_original_elevations(self):
        far, out = self.res["upstream_rc"], self.res["outlet_rc"]
        self.assertAlmostEqual(self.res["H_m"], self.dem[far] - self.dem[out])
        self.assertAlmostEqual(self.res["main_channel_slope_m_per_m"], self.res["H_m"] / self.res["longest_flow_path_m"])
        self.assertGreater(self.res["H_m"], 0)

    def test_a_basin_reaching_the_dem_edge_is_flagged_as_possibly_truncated(self):
        self.assertTrue(self.res["touches_dem_edge"])

    def test_a_closed_bowl_is_not_flagged(self):
        r, c = np.indices((61, 61))
        bowl = np.hypot(r - 30, c - 30) * 5.0            # a cone-shaped hollow: drains to the centre
        bowl[30, 30] = -50.0
        res = wd.delineate(bowl[10:51, 10:51] * 0 + wd.fill_depressions(bowl)[10:51, 10:51], DX, DY, row=20, col=20, snap_radius_m=0)
        self.assertTrue(res["success"])


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestDepressionsAndSnapping(unittest.TestCase):
    def test_a_spurious_pit_in_the_channel_does_not_change_the_basin(self):
        clean = wd.delineate(two_valleys(), DX, DY, row=60, col=12, snap_radius_m=0)
        pitted_dem = two_valleys()
        pitted_dem[30, 12] -= 40.0                         # a one-cell sink in the middle of the channel
        pitted = wd.delineate(pitted_dem, DX, DY, row=60, col=12, snap_radius_m=0)
        self.assertEqual(pitted["cells"], clean["cells"])
        self.assertAlmostEqual(pitted["area_km2"], clean["area_km2"])
        self.assertAlmostEqual(pitted["longest_flow_path_m"], clean["longest_flow_path_m"], places=6)

    def test_fill_raises_a_pit_and_leaves_other_cells(self):
        dem = np.full((9, 9), 10.0)
        dem[4, 4] = 2.0
        filled = wd.fill_depressions(dem)
        self.assertGreaterEqual(filled[4, 4], 10.0)
        self.assertTrue((filled >= dem).all())

    def test_the_outlet_is_snapped_onto_the_channel_and_the_move_is_reported(self):
        res = wd.delineate(two_valleys(), DX, DY, row=60, col=14, snap_radius_m=90)    # two cells off the channel
        self.assertTrue(res["snapped_to_channel"])
        self.assertEqual(res["outlet_rc"][1], 12)
        self.assertGreater(res["snap_moved_m"], 0)
        self.assertLessEqual(res["snap_moved_m"], 90 + 1e-6)

    def test_snap_radius_zero_keeps_the_point(self):
        res = wd.delineate(two_valleys(), DX, DY, row=60, col=14, snap_radius_m=0)
        self.assertEqual(res["outlet_rc"], (60, 14))
        self.assertEqual(res["snap_moved_m"], 0)


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestRefusals(unittest.TestCase):
    def test_bad_inputs_are_refused_with_a_reason(self):
        dem = two_valleys()
        self.assertIn("too small", wd.delineate(np.zeros((3, 3)), DX, DY, 1, 1)["error"])
        self.assertIn("outside", wd.delineate(dem, DX, DY, 500, 5)["error"])
        self.assertIn("cell size", wd.delineate(dem, 0, DY, 5, 5)["error"])
        holey = dem.copy()
        holey[:40, :] = np.nan
        self.assertIn("no data", wd.delineate(holey, DX, DY, 60, 12)["error"])


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestHelpers(unittest.TestCase):
    def test_row_runs_describe_the_mask_exactly(self):
        mask = np.zeros((4, 8), dtype=bool)
        mask[1, 2:5] = True
        mask[2, 0:2] = True
        mask[2, 4:8] = True
        runs = wd.mask_to_row_runs(mask)
        self.assertEqual(runs, [(1, 2, 4), (2, 0, 1), (2, 4, 7)])
        rebuilt = np.zeros_like(mask)
        for r, a, b in runs:
            rebuilt[r, a:b + 1] = True
        self.assertTrue((rebuilt == mask).all())

    def test_cell_size_in_metres(self):
        gt = (35.0, 1 / 3600.0, 0, 32.0, 0, -1 / 3600.0)                  # one arc-second, as in Copernicus GLO-30 (about 30 m)
        dx, dy = wd.cell_size_metres(gt, 32.0, geographic=True)
        self.assertAlmostEqual(dy, 30.7, delta=0.2)
        self.assertAlmostEqual(dx, 26.0, delta=0.3)                       # shrinks with cos(latitude)
        self.assertEqual(wd.cell_size_metres((0, 30.0, 0, 0, 0, -30.0), 0, geographic=False), (30.0, 30.0))


if __name__ == "__main__":
    unittest.main()
