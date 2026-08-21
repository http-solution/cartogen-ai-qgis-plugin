# -*- coding: utf-8 -*-
"""Tests for weighted_overlay_analysis, added to raster_tools.py in the
QGIS-feature-coverage pass, and interpolate_surface/elevation_profile/
georeference_image/estimate_population_exposure, added in the ArcGIS-parity
pass. Follows the QGIS_AVAILABLE=False degrade-path convention used
throughout the rest of the test suite."""
import unittest
from unittest.mock import patch, MagicMock
from agent.tools.raster_tools import (
    weighted_overlay_analysis, _compute_normalized_weights, interpolate_surface,
    elevation_profile, georeference_image, estimate_population_exposure,
    calculate_ndvi, calculate_ndwi, calculate_ndre,
    apply_raster_stretch, _auto_raster_style,
)


class TestVegetationIndexToolsDegradeOutsideQgis(unittest.TestCase):
    """calculate_ndvi/ndwi/ndre had no test coverage at all before this --
    not even the baseline QGIS_AVAILABLE=False degrade check every other
    tool in this suite has -- found during a router/prompt-coverage audit,
    not related to any behavior change in the tools themselves."""

    def test_calculate_ndvi_degrades(self):
        res = calculate_ndvi("red", "nir")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_calculate_ndwi_degrades(self):
        res = calculate_ndwi("green", "nir")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_calculate_ndre_degrades(self):
        res = calculate_ndre("red_edge", "nir")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestComputeNormalizedWeights(unittest.TestCase):
    """Pure Python, no QGIS import needed."""

    def test_normalizes_to_sum_one(self):
        normalized, err = _compute_normalized_weights([1, 1, 2])
        self.assertIsNone(err)
        self.assertAlmostEqual(sum(normalized), 1.0)
        self.assertAlmostEqual(normalized[2], 0.5)

    def test_already_normalized_weights_unchanged(self):
        normalized, err = _compute_normalized_weights([0.25, 0.75])
        self.assertIsNone(err)
        self.assertAlmostEqual(normalized[0], 0.25)
        self.assertAlmostEqual(normalized[1], 0.75)

    def test_negative_weight_rejected(self):
        normalized, err = _compute_normalized_weights([1, -1])
        self.assertIsNone(normalized)
        self.assertIn("non-negative", err)

    def test_all_zero_weights_rejected(self):
        normalized, err = _compute_normalized_weights([0, 0])
        self.assertIsNone(normalized)
        self.assertIn("positive", err)


class TestWeightedOverlayAnalysisDegradesOutsideQgis(unittest.TestCase):
    def test_degrades(self):
        res = weighted_overlay_analysis(["a", "b"], [0.5, 0.5])
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestWeightedOverlayAnalysisValidation(unittest.TestCase):
    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_fewer_than_two_rasters(self):
        # Validated before any layer lookup, so this doesn't need QGIS mocks.
        res = weighted_overlay_analysis(["a"], [1.0])
        self.assertIn("error", res)
        self.assertIn("at least 2", res["error"])

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_too_many_rasters(self):
        names = [f"r{i}" for i in range(7)]
        weights = [1.0] * 7
        res = weighted_overlay_analysis(names, weights)
        self.assertIn("error", res)
        self.assertIn("at most", res["error"])

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_mismatched_weights_length(self):
        res = weighted_overlay_analysis(["a", "b"], [1.0])
        self.assertIn("error", res)
        self.assertIn("weights", res["error"])

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_all_zero_weights(self):
        res = weighted_overlay_analysis(["a", "b"], [0, 0])
        self.assertIn("error", res)

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("agent.tools.raster_tools._find_layer_by_name")
    def test_rejects_mismatched_crs(self, mock_find):
        layer_a = MagicMock()
        layer_a.crs.return_value.authid.return_value = "EPSG:4326"
        layer_b = MagicMock()
        layer_b.crs.return_value.authid.return_value = "EPSG:32636"
        mock_find.side_effect = [layer_a, layer_b]

        res = weighted_overlay_analysis(["a", "b"], [0.5, 0.5])

        self.assertIn("error", res)
        self.assertIn("CRS", res["error"])


class TestNewToolsDegradeOutsideQgis(unittest.TestCase):
    def test_interpolate_surface_degrades(self):
        res = interpolate_surface("points", "field")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_elevation_profile_degrades(self):
        res = elevation_profile("line", "dem")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_georeference_image_degrades(self):
        res = georeference_image("/some/image.png", [{"pixel_x": 0, "pixel_y": 0, "lon": 0, "lat": 0}] * 3, "/out.tif")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_estimate_population_exposure_degrades(self):
        res = estimate_population_exposure("pop_raster", "districts")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestInterpolateSurfaceValidation(unittest.TestCase):
    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_unknown_method(self):
        res = interpolate_surface("points", "field", method="kriging")
        self.assertIn("error", res)
        self.assertIn("method", res["error"])

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("agent.tools.raster_tools._find_layer_by_name")
    def test_rejects_unknown_field(self, mock_find):
        fake_field = MagicMock()
        fake_field.name.return_value = "value"
        fake_layer = MagicMock()
        fake_layer.fields.return_value = [fake_field]
        mock_find.return_value = fake_layer

        res = interpolate_surface("points", "nonexistent")

        self.assertIn("error", res)
        self.assertIn("nonexistent", res["error"])


class TestElevationProfileValidation(unittest.TestCase):
    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_too_few_samples(self):
        res = elevation_profile("line", "dem", num_samples=1)
        self.assertIn("error", res)
        self.assertIn("num_samples", res["error"])

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("agent.tools.raster_tools._find_layer_by_name")
    def test_samples_along_line_using_mocked_geometry_and_provider(self, mock_find):
        line_layer = MagicMock()
        line_geom = MagicMock()
        line_geom.isEmpty.return_value = False
        line_geom.length.return_value = 100.0
        line_geom.interpolate.return_value.asPoint.return_value = (0, 0)
        line_feat = MagicMock()
        line_feat.geometry.return_value = line_geom
        line_layer.getFeatures.return_value = [line_feat]

        dem_layer = MagicMock()
        dem_layer.dataProvider.return_value.sample.return_value = (123.4, True)

        def side_effect(name):
            return {"line": line_layer, "dem": dem_layer}.get(name)
        mock_find.side_effect = side_effect

        res = elevation_profile("line", "dem", num_samples=5)

        self.assertTrue(res["success"])
        self.assertEqual(res["sample_count"], 5)
        self.assertEqual(res["valid_sample_count"], 5)
        self.assertEqual(res["elevations"], [123.4] * 5)

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("agent.tools.raster_tools._find_layer_by_name")
    def test_reports_error_when_no_valid_samples(self, mock_find):
        line_layer = MagicMock()
        line_geom = MagicMock()
        line_geom.isEmpty.return_value = False
        line_geom.length.return_value = 100.0
        line_geom.interpolate.return_value.asPoint.return_value = (0, 0)
        line_feat = MagicMock()
        line_feat.geometry.return_value = line_geom
        line_layer.getFeatures.return_value = [line_feat]

        dem_layer = MagicMock()
        dem_layer.dataProvider.return_value.sample.return_value = (None, False)

        def side_effect(name):
            return {"line": line_layer, "dem": dem_layer}.get(name)
        mock_find.side_effect = side_effect

        res = elevation_profile("line", "dem", num_samples=3)

        self.assertIn("error", res)


class TestGeoreferenceImageValidation(unittest.TestCase):
    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_missing_file(self):
        res = georeference_image("/definitely/not/a/real/file.png", [{"pixel_x": 0, "pixel_y": 0, "lon": 0, "lat": 0}] * 3, "/out.tif")
        self.assertIn("error", res)
        self.assertIn("not found", res["error"])

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_fewer_than_three_control_points(self):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            res = georeference_image(path, [{"pixel_x": 0, "pixel_y": 0, "lon": 0, "lat": 0}], "/out.tif")
            self.assertIn("error", res)
            self.assertIn("3 control points", res["error"])
        finally:
            os.remove(path)


class TestEstimatePopulationExposureValidation(unittest.TestCase):
    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("agent.tools.raster_tools._find_layer_by_name")
    def test_reports_missing_raster_layer(self, mock_find):
        mock_find.return_value = None
        res = estimate_population_exposure("ghost_pop", "districts")
        self.assertIn("error", res)
        self.assertIn("ghost_pop", res["error"])

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("agent.tools.raster_tools.QgsWkbTypes", create=True)
    @patch("agent.tools.raster_tools._find_layer_by_name")
    def test_rejects_non_polygon_area_layer(self, mock_find, mock_wkb):
        mock_wkb.PolygonGeometry = "polygon-sentinel"
        raster = MagicMock()
        vector = MagicMock()
        vector.geometryType.return_value = "not-a-polygon"

        def side_effect(name):
            return {"pop": raster, "districts": vector}.get(name)
        mock_find.side_effect = side_effect

        res = estimate_population_exposure("pop", "districts")

        self.assertIn("error", res)
        self.assertIn("polygon", res["error"])


class TestAutoRasterStyle(unittest.TestCase):
    """Pure Python, no QGIS import needed -- see apply_raster_stretch below for the
    tool that consumes this."""

    def test_auto_picks_color_ramp_for_ndvi_named_layer(self):
        self.assertEqual(_auto_raster_style("NDVI", "auto"), ("color_ramp", "RdYlGn"))

    def test_auto_matches_case_insensitively_and_as_substring(self):
        self.assertEqual(_auto_raster_style("field3_ndwi_2026", "auto"), ("color_ramp", "RdBu"))

    def test_auto_picks_stretch_for_non_index_layer(self):
        self.assertEqual(_auto_raster_style("dem_hillshade", "auto"), ("stretch", None))

    def test_ndre_maps_to_diverging_ramp(self):
        self.assertEqual(_auto_raster_style("NDRE", "auto"), ("color_ramp", "RdYlGn"))

    def test_explicit_stretch_mode_ignores_name(self):
        self.assertEqual(_auto_raster_style("NDVI", "stretch"), ("stretch", None))

    def test_explicit_color_ramp_mode_on_non_index_name_has_no_default_ramp(self):
        self.assertEqual(_auto_raster_style("random_raster", "color_ramp"), ("color_ramp", None))

    def test_defaults_to_auto_when_mode_is_none(self):
        self.assertEqual(_auto_raster_style("NDVI", None), ("color_ramp", "RdYlGn"))

    def test_invalid_mode_returns_none(self):
        self.assertEqual(_auto_raster_style("NDVI", "bogus"), (None, None))


class TestApplyRasterStretchDegradesOutsideQgis(unittest.TestCase):
    def test_degrades(self):
        res = apply_raster_stretch("NDVI")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestApplyRasterStretchValidation(unittest.TestCase):
    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_invalid_mode(self):
        res = apply_raster_stretch("NDVI", mode="bogus")
        self.assertIn("error", res)
        self.assertIn("mode", res["error"])

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_non_positive_band(self):
        res = apply_raster_stretch("NDVI", band=0)
        self.assertIn("error", res)
        self.assertIn("band", res["error"])

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_min_greater_or_equal_max(self):
        res = apply_raster_stretch("NDVI", min_value=5, max_value=5)
        self.assertIn("error", res)
        self.assertIn("min_value", res["error"])

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("agent.tools.raster_tools._find_layer_by_name")
    def test_reports_missing_layer(self, mock_find):
        mock_find.return_value = None
        res = apply_raster_stretch("ghost_raster")
        self.assertIn("error", res)
        self.assertIn("ghost_raster", res["error"])

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("agent.tools.raster_tools._find_layer_by_name")
    def test_rejects_band_beyond_band_count(self, mock_find):
        layer = MagicMock()
        layer.bandCount.return_value = 1
        mock_find.return_value = layer
        res = apply_raster_stretch("single_band_raster", band=2)
        self.assertIn("error", res)
        self.assertIn("band", res["error"].lower())

    @patch("agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("agent.tools.raster_tools._find_layer_by_name")
    def test_explicit_min_max_skips_band_statistics_call(self, mock_find):
        layer = MagicMock()
        layer.bandCount.return_value = 1
        mock_find.return_value = layer
        # With min_value/max_value both given, bandStatistics should never be
        # called, regardless of what happens in the renderer-construction step
        # beyond this (which needs a real QGIS install to exercise fully --
        # matches this file's existing testing depth, e.g.
        # TestWeightedOverlayAnalysisValidation above).
        apply_raster_stretch("some_raster", mode="stretch", min_value=0, max_value=1)
        layer.dataProvider.return_value.bandStatistics.assert_not_called()


if __name__ == "__main__":
    unittest.main()
