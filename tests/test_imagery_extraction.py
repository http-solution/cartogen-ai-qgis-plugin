# -*- coding: utf-8 -*-
"""Tests for agent/tools/imagery_extraction.py -- SAM-family (FastSAM)
imagery feature extraction, see docs/archive/SAM_IMAGERY_EXTRACTION_SPEC.md. Only
the pure-Python pieces (coordinate math, mask pixel counting) and the
degrade-outside-QGIS path are testable here -- real segmentation quality,
timing, and memory behavior need a live QGIS session with a downloaded
model checkpoint, explicitly out of scope for this suite (see the spec's
section 9)."""
import unittest
from unittest.mock import MagicMock
from cartogen_ai.core.agent.tools.imagery_extraction import (
    _pixel_to_map, _mask_pixel_count, extract_features_from_imagery,
    _finalize_extracted_geometry,
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


class TestFinalizeExtractedGeometry(unittest.TestCase):
    """Phase 4 (2026-09-19): gdal.Polygonize output is a jagged pixel-grid staircase with
    no simplification/validity/min-area handling beyond min_area_m2 alone -- extracted from
    extract_features_from_imagery's per-feature loop so this decision logic is directly
    testable with a mocked QgsGeometry, without the GDAL/OGR/FastSAM pipeline around it."""

    def test_simplifies_by_pixel_size(self):
        geom = MagicMock()
        geom.simplify.return_value = geom
        geom.isGeosValid.return_value = True
        geom.isEmpty.return_value = False
        geom.area.return_value = 100.0

        result = _finalize_extracted_geometry(geom, pixel_size=0.5, min_area_m2=None)

        geom.simplify.assert_called_once_with(0.5)
        self.assertIs(result, geom)

    def test_zero_pixel_size_skips_simplify(self):
        geom = MagicMock()
        geom.isGeosValid.return_value = True
        geom.isEmpty.return_value = False
        geom.area.return_value = 100.0

        _finalize_extracted_geometry(geom, pixel_size=0, min_area_m2=None)

        geom.simplify.assert_not_called()

    def test_invalid_geometry_gets_repaired(self):
        geom = MagicMock()
        geom.simplify.return_value = geom
        geom.isGeosValid.return_value = False
        repaired = MagicMock()
        repaired.isEmpty.return_value = False
        repaired.area.return_value = 100.0
        geom.makeValid.return_value = repaired

        result = _finalize_extracted_geometry(geom, pixel_size=0.5, min_area_m2=None)

        geom.makeValid.assert_called_once()
        self.assertIs(result, repaired)

    def test_empty_after_repair_is_dropped(self):
        geom = MagicMock()
        geom.simplify.return_value = geom
        geom.isGeosValid.return_value = False
        repaired = MagicMock()
        repaired.isEmpty.return_value = True
        geom.makeValid.return_value = repaired

        result = _finalize_extracted_geometry(geom, pixel_size=0.5, min_area_m2=None)

        self.assertIsNone(result)

    def test_below_min_area_is_dropped(self):
        geom = MagicMock()
        geom.simplify.return_value = geom
        geom.isGeosValid.return_value = True
        geom.isEmpty.return_value = False
        geom.area.return_value = 5.0

        result = _finalize_extracted_geometry(geom, pixel_size=0.5, min_area_m2=10.0)

        self.assertIsNone(result)

    def test_above_min_area_is_kept(self):
        geom = MagicMock()
        geom.simplify.return_value = geom
        geom.isGeosValid.return_value = True
        geom.isEmpty.return_value = False
        geom.area.return_value = 50.0

        result = _finalize_extracted_geometry(geom, pixel_size=0.5, min_area_m2=10.0)

        self.assertIs(result, geom)

    def test_min_area_uses_the_metre_measure_not_planar_crs_units(self):
        # #154: in EPSG:4326 the planar area is in degrees squared (tiny), so every feature fell under a metre threshold.
        geom = MagicMock()
        geom.simplify.return_value = geom
        geom.isGeosValid.return_value = True
        geom.isEmpty.return_value = False
        geom.area.return_value = 1e-9
        self.assertIs(_finalize_extracted_geometry(geom, 0.5, 10.0, area_m2=lambda g: 500.0), geom)
        self.assertIsNone(_finalize_extracted_geometry(geom, 0.5, 10.0, area_m2=lambda g: 2.0))


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


class TestMaskGeotransformAndPolygonize(unittest.TestCase):
    """Audit A10 (rotated resized masks) and A01 (the background polygonized as a detection)."""

    def test_both_terms_of_each_axis_are_scaled(self):
        from cartogen_ai.core.agent.tools.imagery_extraction import _scaled_geotransform
        # the audit's numbers: gt1=10, gt2=2, gt4=3, gt5=-10 with scales (x=2, y=4)
        self.assertEqual(_scaled_geotransform((100.0, 10.0, 2.0, 200.0, 3.0, -10.0), 2, 4),
                         (100.0, 20.0, 8.0, 200.0, 6.0, -40.0))

    def test_a_north_up_grid_is_unchanged_apart_from_the_pixel_size(self):
        from cartogen_ai.core.agent.tools.imagery_extraction import _scaled_geotransform
        self.assertEqual(_scaled_geotransform((0.0, 10.0, 0.0, 0.0, 0.0, -10.0), 2, 2), (0.0, 20.0, 0.0, 0.0, 0.0, -20.0))

    def test_the_pixel_size_follows_a_rotated_grid(self):
        from cartogen_ai.core.agent.tools.imagery_extraction import _pixel_size
        self.assertEqual(_pixel_size((0, 10.0, 0, 0, 0, -10.0)), 10.0)
        self.assertAlmostEqual(_pixel_size((0, 6.0, 0, 0, 8.0, -10.0)), 10.0)

    def test_only_the_object_is_polygonized_not_the_background(self):
        try:
            import numpy as np
            from osgeo import osr
        except ImportError:
            self.skipTest("requires GDAL and numpy")
        from cartogen_ai.core.agent.tools.imagery_extraction import _polygonize_mask
        mask = np.zeros((10, 10), dtype="uint8")
        mask[3:7, 3:7] = 1                                   # a 4x4 object in a 10x10 mask
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32636)
        layer, _a, _b = _polygonize_mask(mask, (500000.0, 10.0, 0.0, 3000000.0, 0.0, -10.0), srs.ExportToWkt(), srs)
        areas = sorted(f.GetGeometryRef().GetArea() for f in layer)
        self.assertEqual(areas, [1600.0], "only the 16-pixel object (1,600 m2) may come back, not the 84-pixel background")

    def test_an_empty_mask_gives_no_polygons(self):
        try:
            import numpy as np
            from osgeo import osr
        except ImportError:
            self.skipTest("requires GDAL and numpy")
        from cartogen_ai.core.agent.tools.imagery_extraction import _polygonize_mask
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32636)
        layer, _a, _b = _polygonize_mask(np.zeros((6, 6), dtype="uint8"), (0.0, 1.0, 0.0, 0.0, 0.0, -1.0), srs.ExportToWkt(), srs)
        self.assertEqual(len(list(layer)), 0)
