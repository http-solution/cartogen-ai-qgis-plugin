"""#162 step 2: the numpy kernels that replace gdal:contraststretch and saga k-means. GDAL I/O is in test_raster_numpy_live.py."""
import unittest

try:
    import numpy as np
    from cartogen_ai.core.agent.tools import raster_numpy as rn
except ImportError:      # pragma: no cover - the sandbox has numpy; a machine without it skips
    np = None


@unittest.skipIf(np is None, "numpy not installed")
class TestEqualize(unittest.TestCase):
    def test_spreads_a_clumped_band_over_the_full_range(self):
        values = np.array([[1, 1, 1, 2], [2, 2, 3, 100]], dtype=float)
        out = rn.equalize(values, np.ones(values.shape, dtype=bool))
        self.assertEqual(out.dtype, np.uint8)
        self.assertEqual(int(out.max()), 255)
        self.assertEqual(int(out.min()), 1)               # 0 is reserved for no-data
        self.assertTrue((np.diff(out.flatten()[np.argsort(values.flatten(), kind="stable")]) >= 0).all())   # order preserved

    def test_invalid_cells_stay_zero_and_do_not_count(self):
        values = np.array([[1.0, 2.0], [3.0, 9999.0]])
        valid = np.array([[True, True], [True, False]])
        out = rn.equalize(values, valid)
        self.assertEqual(int(out[1, 1]), 0)
        self.assertEqual(int(out[0, 0]), 1)               # the lowest valid value maps to 1, never the nodata 0
        self.assertEqual(int(out[1, 0]), 255)

    def test_a_flat_band_stays_valid(self):
        out = rn.equalize(np.full((3, 3), 7.0), np.ones((3, 3), dtype=bool))
        self.assertTrue((out == 1).all())

    def test_no_valid_pixel_becomes_nodata(self):
        """Audit A09: [10,20,30,40] with one invalid cell must keep all three valid cells non-zero."""
        values = np.array([[10.0, 20.0], [30.0, 40.0]])
        valid = np.array([[True, True], [True, False]])
        out = rn.equalize(values, valid)
        self.assertTrue((out[valid] >= 1).all())
        self.assertEqual(int(out[~valid][0]), 0)

    def test_no_valid_cells(self):
        out = rn.equalize(np.ones((2, 2)), np.zeros((2, 2), dtype=bool))
        self.assertEqual(int(out.max()), 0)


class TestMemoryBudget(unittest.TestCase):
    """Audit A15: the guard counts cells x bands, not just cells."""

    def test_small_raster_passes(self):
        rn.check_memory_budget(1000, 1000, 8)

    def test_many_bands_over_the_value_budget_is_refused(self):
        with self.assertRaisesRegex(ValueError, "bands"):
            rn.check_memory_budget(5000, 5000, 8)          # 25M cells (allowed alone) x 8 = 200M values

    def test_too_many_cells_is_refused(self):
        with self.assertRaisesRegex(ValueError, "cells"):
            rn.check_memory_budget(10000, 10000, 1)


@unittest.skipIf(np is None, "numpy not installed")
class TestKmeans(unittest.TestCase):
    def _blobs(self):
        rng = np.random.RandomState(0)
        a = rng.normal([0, 0], 0.1, (200, 2))
        b = rng.normal([10, 10], 0.1, (200, 2))
        c = rng.normal([0, 10], 0.1, (200, 2))
        return np.vstack([a, b, c])

    def test_recovers_three_well_separated_clusters(self):
        x = self._blobs()
        labels, centres = rn.kmeans(x, 3, seed=1)
        self.assertEqual(len(set(labels[:200])), 1)
        self.assertEqual(len(set(labels[200:400])), 1)
        self.assertEqual(len(set(labels[400:])), 1)
        self.assertEqual(len(set(labels)), 3)
        self.assertEqual(centres.shape, (3, 2))

    def test_reproducible_for_a_seed(self):
        x = self._blobs()
        a, _ = rn.kmeans(x, 3, seed=5)
        b, _ = rn.kmeans(x, 3, seed=5)
        self.assertTrue((a == b).all())

    def test_fit_on_a_sample_still_labels_every_pixel(self):
        x = self._blobs()
        labels, _ = rn.kmeans(x, 3, seed=2, fit_sample=100)
        self.assertEqual(len(labels), len(x))
        self.assertEqual(len(set(labels)), 3)

    def test_too_few_pixels_is_an_error(self):
        with self.assertRaises(ValueError):
            rn.kmeans(np.zeros((2, 2)), 5)

    def test_identical_pixels_do_not_crash(self):
        labels, _ = rn.kmeans(np.ones((50, 2)), 3, seed=0)
        self.assertEqual(len(labels), 50)


class TestValidateClassCount(unittest.TestCase):
    def test_bounds(self):
        if np is None:
            self.skipTest("numpy not installed")
        self.assertIsNone(rn.validate_class_count(2))
        self.assertIsNone(rn.validate_class_count("7"))
        for bad in (1, 51, "x", None, 2.5 if False else "two"):
            self.assertIsNotNone(rn.validate_class_count(bad), bad)


class TestAllowlistNoLongerOffersMissingIds(unittest.TestCase):
    def test_the_four_ids_the_registry_lacks_are_gone(self):
        from cartogen_ai.core.agent.tools import _processing_allowlist as al
        everything = set(al.ALLOWED_ALGORITHM_IDS)
        with open(al.__file__, encoding="utf-8") as fh:
            text = fh.read()
        for gone in ("gdal:contraststretch", "gdal:pansharpening", "saga:kmeansclassificationforgrid",
                     "saga:supervisedclassificationforgrids"):
            self.assertNotIn(f'"{gone}"', text)
            self.assertNotIn(gone, everything)
        self.assertIn('"gdal:pansharp"', text)


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(np is None, "numpy not installed")
class TestBlockedClassification(unittest.TestCase):
    """GitHub #222 / audit A15: classify_in_blocks never holds more than a block, and matches the in-memory result in kind."""

    def _raster(self, rows=60, cols=40):
        rng = np.random.RandomState(1)
        arr = np.zeros((rows, cols, 2), dtype=np.float32)
        arr[: rows // 2] = rng.normal([0, 0], 0.05, (rows // 2, cols, 2))
        arr[rows // 2:] = rng.normal([10, 10], 0.05, (rows - rows // 2, cols, 2))
        valid = np.ones((rows, cols), dtype=bool)
        if rows > 10:
            valid[5, 5] = False
            valid[rows - 3, 7] = False
        return arr, valid

    def _run(self, arr, valid, k=2, block_rows=7):
        out = np.zeros(valid.shape, dtype=np.uint8)
        peak = []

        def read_block(row0, n):
            peak.append(n)
            return arr[row0:row0 + n], valid[row0:row0 + n]

        def write_block(row0, block):
            out[row0:row0 + block.shape[0]] = block
        res = rn.classify_in_blocks(read_block, write_block, arr.shape[0], arr.shape[1], arr.shape[2], k, seed=0, block_rows=block_rows)
        return res, out, peak

    def test_two_clusters_are_found_and_invalid_cells_stay_zero(self):
        arr, valid = self._raster()
        res, out, _peak = self._run(arr, valid)
        self.assertEqual(res["valid_cells"], int(valid.sum()))
        self.assertTrue((out[~valid] == 0).all())
        top, bottom = set(np.unique(out[:30][valid[:30]])), set(np.unique(out[30:][valid[30:]]))
        self.assertEqual(len(top), 1)
        self.assertEqual(len(bottom), 1)
        self.assertNotEqual(top, bottom)
        self.assertTrue(set(np.unique(out[valid])) <= {1, 2})

    def test_no_block_is_larger_than_requested(self):
        arr, valid = self._raster()
        _res, _out, peak = self._run(arr, valid, block_rows=7)
        self.assertLessEqual(max(peak), 7)
        self.assertGreater(len(peak), 2 * (60 // 7))            # read twice: a sampling pass and an assignment pass

    def test_same_seed_same_result(self):
        arr, valid = self._raster()
        self.assertTrue((self._run(arr, valid)[1] == self._run(arr, valid)[1]).all())

    def test_fewer_valid_cells_than_classes_is_a_plain_error(self):
        arr, valid = self._raster(rows=4, cols=4)
        valid[:] = False
        valid[0, 0] = True
        with self.assertRaisesRegex(ValueError, "fewer than the 2 classes"):
            self._run(arr, valid, k=2, block_rows=2)

    def test_default_block_size_is_derived_from_the_value_budget(self):
        arr, valid = self._raster(rows=10, cols=10)
        seen = []
        rn.classify_in_blocks(lambda r, n: (seen.append(n) or (arr[r:r + n], valid[r:r + n])), lambda r, b: None, 10, 10, 2, 2)
        self.assertEqual(seen[0], 10)                              # 4M values per block holds a 10 x 10 x 2 raster whole
