# -*- coding: utf-8 -*-
"""Tests for agent/tools/imagery_extraction.py -- SAM-family (FastSAM)
imagery feature extraction, see docs/SAM_IMAGERY_EXTRACTION_SPEC.md. Only
the pure-Python pieces (coordinate math, mask pixel counting) and the
degrade-outside-QGIS path are testable here -- real segmentation quality,
timing, and memory behavior need a live QGIS session with a downloaded
model checkpoint, explicitly out of scope for this suite (see the spec's
section 9)."""
import unittest
from agent.tools.imagery_extraction import (
    _pixel_to_map, _mask_pixel_count, extract_features_from_imagery,
)


class TestPixelToMap(unittest.TestCase):
    def test_no_rotation_geotransform(self):
        # origin (100, 200), 0.5 map-units/pixel east, -0.5 map-units/pixel south
        geotransform = (100.0, 0.5, 0.0, 200.0, 0.0, -0.5)
        self.assertEqual(_pixel_to_map(0, 0, geotransform), (100.0, 200.0))
        self.assertEqual(_pixel_to_map(10, 20, geotransform), (105.0, 190.0))

    def test_with_rotation_terms(self):
        geotransform = (0.0, 1.0, 0.5, 0.0, 0.5, 1.0)
        x, y = _pixel_to_map(2, 3, geotransform)
        self.assertEqual(x, 2 * 1.0 + 3 * 0.5)
        self.assertEqual(y, 2 * 0.5 + 3 * 1.0)

    def test_negative_pixel_coordinates(self):
        geotransform = (0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
        self.assertEqual(_pixel_to_map(-5, -5, geotransform), (-5.0, -5.0))


class TestMaskPixelCount(unittest.TestCase):
    def test_plain_nested_list_above_threshold(self):
        mask = [[0.9, 0.1], [0.6, 0.2]]
        self.assertEqual(_mask_pixel_count(mask), 2)

    def test_plain_nested_list_all_below_threshold(self):
        mask = [[0.1, 0.2], [0.1, 0.2]]
        self.assertEqual(_mask_pixel_count(mask), 0)

    def test_custom_threshold(self):
        mask = [[0.9, 0.5], [0.4, 0.1]]
        self.assertEqual(_mask_pixel_count(mask, threshold=0.5), 1)

    def test_numpy_array_if_available(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not available in this environment")
        mask = np.array([[0.9, 0.1], [0.6, 0.2]])
        self.assertEqual(_mask_pixel_count(mask), 2)


class TestExtractFeaturesFromImageryTool(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = extract_features_from_imagery("raster")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_degrades_gracefully_outside_qgis_with_all_params(self):
        res = extract_features_from_imagery(
            "raster", output_layer_name="features", min_area_m2=10,
            confidence_threshold=0.6, max_pixel_dimension=1024,
        )
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


if __name__ == "__main__":
    unittest.main()
