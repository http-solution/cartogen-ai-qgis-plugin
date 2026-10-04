# -*- coding: utf-8 -*-
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
        self.assertEqual(int(out.min()), 0)
        self.assertTrue((np.diff(out.flatten()[np.argsort(values.flatten(), kind="stable")]) >= 0).all())   # order preserved

    def test_invalid_cells_stay_zero_and_do_not_count(self):
        values = np.array([[1.0, 2.0], [3.0, 9999.0]])
        valid = np.array([[True, True], [True, False]])
        out = rn.equalize(values, valid)
        self.assertEqual(int(out[1, 1]), 0)
        self.assertEqual(int(out[0, 0]), 0)               # the lowest valid value maps to 0 (the 9999 outlier is ignored)
        self.assertEqual(int(out[1, 0]), 255)

    def test_a_flat_band_gives_zeros(self):
        out = rn.equalize(np.full((3, 3), 7.0), np.ones((3, 3), dtype=bool))
        self.assertEqual(int(out.max()), 0)

    def test_no_valid_cells(self):
        out = rn.equalize(np.ones((2, 2)), np.zeros((2, 2), dtype=bool))
        self.assertEqual(int(out.max()), 0)


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
