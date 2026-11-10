"""PLAN-023 R3-5: management-zone core, hand-computed known answers and a brute-force cross-check of the connected-patch labelling. Pure numpy: skipped where numpy is
missing (the CI test job installs it)."""
import unittest

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

from cartogen_ai.core.agent.tools import raster_zones as rz


def bfs_components(labels):
    """Reference implementation: 4-neighbour patches of equal non-negative label by flood fill."""
    rows, cols = labels.shape
    seen = np.zeros(labels.shape, dtype=bool)
    count = 0
    for r in range(rows):
        for c in range(cols):
            if labels[r, c] < 0 or seen[r, c]:
                continue
            count += 1
            stack = [(r, c)]
            seen[r, c] = True
            while stack:
                y, x = stack.pop()
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < rows and 0 <= xx < cols and not seen[yy, xx] and labels[yy, xx] == labels[y, x]:
                        seen[yy, xx] = True
                        stack.append((yy, xx))
    return count


def two_patches(rows=6, cols=8):
    """Left half 0.2, right half 0.8, as a one-band stack."""
    arr = np.full((rows, cols, 1), 0.2)
    arr[:, cols // 2:, 0] = 0.8
    return arr, np.ones((rows, cols), dtype=bool)


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestKnownAnswers(unittest.TestCase):
    def test_two_flat_patches_give_two_zones_with_exact_means(self):
        values, valid = two_patches()
        labels, _z = rz.cluster(values, valid, 2, seed=1)
        stats = rz.zone_stats(labels, values, valid, [0.09] * 6)
        self.assertEqual([s["zone"] for s in stats], [1, 2])
        self.assertAlmostEqual(stats[0]["means"][0], 0.2, places=9)
        self.assertAlmostEqual(stats[1]["means"][0], 0.8, places=9)
        self.assertEqual((stats[0]["cells"], stats[1]["cells"]), (24, 24))
        self.assertAlmostEqual(stats[0]["area_ha"], 24 * 0.09, places=9)
        self.assertEqual(stats[0]["percent"], 50.0)

    def test_zone_1_is_always_the_lowest_whatever_the_seed(self):
        values, valid = two_patches()
        for seed in range(6):
            labels, _z = rz.cluster(values, valid, 2, seed=seed)
            self.assertEqual(int(labels[0, 0]), 0, seed)         # the 0.2 patch is zone 1
            self.assertEqual(int(labels[0, -1]), 1, seed)

    def test_a_stray_cell_below_the_minimum_area_is_merged_into_the_neighbouring_zone(self):
        values, valid = two_patches()
        values[2, 1, 0] = 0.8                                    # one 0.8 cell inside the 0.2 patch
        labels, z = rz.cluster(values, valid, 2, seed=1)
        self.assertEqual(int(labels[2, 1]), 1)                   # clustered with the 0.8 zone first
        merged, count = rz.merge_small(labels, z, valid, [1.0] * 6, min_area_ha=2.0)     # a patch needs at least 2 ha = 2 cells here
        self.assertEqual(int(merged[2, 1]), 0)                   # now part of the 0.2 zone
        self.assertEqual(count, 1)
        self.assertEqual(int((merged == 0).sum()), 24)

    def test_a_patch_at_or_above_the_minimum_stays(self):
        values, valid = two_patches()
        values[2, 1, 0] = 0.8
        labels, z = rz.cluster(values, valid, 2, seed=1)
        kept, count = rz.merge_small(labels, z, valid, [1.0] * 6, min_area_ha=1.0)      # the stray cell is exactly 1 ha: not below the minimum
        self.assertEqual(count, 0)
        self.assertEqual(int(kept[2, 1]), 1)

    def test_the_merge_picks_the_neighbour_with_the_nearest_mean(self):
        # three bands of values 0.0 | 0.5 | 1.0 in columns; a stray 0.45 cell in the 1.0 column touches only the 1.0 zone and the 0.5 zone's neighbour is not adjacent
        values = np.zeros((4, 9, 1))
        values[:, 3:6, 0] = 0.5
        values[:, 6:, 0] = 1.0
        values[1, 4, 0] = 0.05                                   # a low cell inside the 0.5 band: neighbours are 0.5 cells only
        valid = np.ones((4, 9), dtype=bool)
        labels, z = rz.cluster(values, valid, 3, seed=2)
        merged, _n = rz.merge_small(labels, z, valid, [1.0] * 4, min_area_ha=2.0)
        self.assertEqual(int(merged[1, 4]), int(merged[1, 3]))   # absorbed by the surrounding 0.5 zone


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestConnectedComponents(unittest.TestCase):
    def test_hand_example(self):
        labels = np.array([[0, 0, 1, 1],
                           [0, 1, 1, 0],
                           [-1, -1, 0, 0]])
        comp, n = rz.connected_components(labels)
        self.assertEqual(n, 3)                                   # {0 top-left L}, {1 snake}, {0 bottom-right}
        self.assertEqual(int(comp[0, 0]), int(comp[1, 0]))
        self.assertNotEqual(int(comp[0, 0]), int(comp[1, 3]))
        self.assertEqual(int(comp[2, 0]), -1)
        self.assertEqual(int(comp[1, 3]), int(comp[2, 3]))

    def test_diagonal_cells_are_not_connected(self):
        _comp, n = rz.connected_components(np.array([[0, 1], [1, 0]]))
        self.assertEqual(n, 4)

    def test_it_agrees_with_a_flood_fill_on_random_grids(self):
        rng = np.random.RandomState(5)
        for _ in range(25):
            rows, cols = rng.randint(2, 14), rng.randint(2, 14)
            labels = rng.randint(-1, 3, (rows, cols))
            comp, n = rz.connected_components(labels)
            self.assertEqual(n, bfs_components(labels))
            self.assertEqual(sorted(set(comp[comp >= 0].tolist())), list(range(n)))

    def test_a_long_snake_converges(self):
        labels = np.zeros((1, 400), dtype=int)
        self.assertEqual(rz.connected_components(labels)[1], 1)


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class TestSmoothingAndStats(unittest.TestCase):
    def test_the_majority_filter_removes_an_isolated_cell(self):
        labels = np.zeros((5, 5), dtype=int)
        labels[2, 2] = 1
        out = rz.majority_filter(labels)
        self.assertEqual(int(out[2, 2]), 0)
        self.assertEqual(int(out.sum()), 0)

    def test_ties_keep_the_cells_own_zone_and_invalid_cells_stay_invalid(self):
        labels = np.array([[0, 1], [-1, 0]])
        out = rz.majority_filter(labels)
        self.assertEqual(int(out[1, 0]), -1)
        one = np.zeros((3, 3), dtype=int)
        self.assertEqual(rz.majority_filter(one).tolist(), one.tolist())            # a single zone is unchanged

    def test_stats_report_means_per_band_in_original_units(self):
        values = np.zeros((2, 2, 2))
        values[:, :, 0] = [[1.0, 1.0], [3.0, 3.0]]
        values[:, :, 1] = [[10.0, 20.0], [30.0, 50.0]]
        labels = np.array([[0, 0], [1, 1]])
        stats = rz.zone_stats(labels, values, np.ones((2, 2), dtype=bool), [2.0, 4.0])
        self.assertEqual(stats[0]["means"], [1.0, 15.0])
        self.assertEqual(stats[1]["means"], [3.0, 40.0])
        self.assertEqual((stats[0]["area_ha"], stats[1]["area_ha"]), (4.0, 8.0))      # 2 cells x 2 ha and 2 cells x 4 ha

    def test_standardise_gives_zero_mean_unit_sd_and_zeros_for_a_flat_band(self):
        values = np.zeros((2, 3, 2))
        values[:, :, 0] = [[1, 2, 3], [1, 2, 3]]
        values[:, :, 1] = 7.0
        z, means, sds = rz.standardise(values, np.ones((2, 3), dtype=bool))
        self.assertAlmostEqual(float(z[:, :, 0].mean()), 0.0, places=9)
        self.assertAlmostEqual(float(z[:, :, 0].std()), 1.0, places=9)
        self.assertEqual(float(np.abs(z[:, :, 1]).sum()), 0.0)
        self.assertEqual((means[1], sds[1]), (7.0, 0.0))

    def test_cluster_refuses_a_bad_count_or_too_few_cells(self):
        values, valid = two_patches()
        with self.assertRaises(ValueError):
            rz.cluster(values, valid, 1)
        with self.assertRaises(ValueError):
            rz.cluster(values, valid, 9)
        with self.assertRaises(ValueError) as ctx:
            rz.cluster(values, np.zeros(valid.shape, dtype=bool), 3)
        self.assertIn("not enough", str(ctx.exception))

    def test_nodata_cells_are_never_zoned(self):
        values, valid = two_patches()
        valid[0, 0] = False
        labels, _z = rz.cluster(values, valid, 2, seed=1)
        self.assertEqual(int(labels[0, 0]), -1)
        self.assertEqual(int((labels >= 0).sum()), 47)


class TestChecks(unittest.TestCase):
    def test_check_request(self):
        self.assertIsNone(rz.check_request(3, 2, 1000))
        self.assertIn("between 2 and 8", rz.check_request(1, 1, 10))
        self.assertIn("whole number", rz.check_request("x", 1, 10))
        self.assertIn("between 1 and 5", rz.check_request(3, 6, 10))
        self.assertIn("limit", rz.check_request(3, 1, 5_000_000))

    def test_default_minimum_is_one_percent_of_the_area(self):
        self.assertEqual(rz.default_min_area_ha(250.0), 2.5)


if __name__ == "__main__":
    unittest.main()
