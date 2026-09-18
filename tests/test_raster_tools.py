# -*- coding: utf-8 -*-
"""Tests for weighted_overlay_analysis, added to raster_tools.py in the
QGIS-feature-coverage pass, and interpolate_surface/elevation_profile/
georeference_image/estimate_population_exposure, added in the ArcGIS-parity
pass. Follows the QGIS_AVAILABLE=False degrade-path convention used
throughout the rest of the test suite."""
import math
import unittest
from unittest.mock import patch, MagicMock
import sys
from cartogen_ai.core.agent.tools.raster_tools import (
    weighted_overlay_analysis, _compute_normalized_weights, interpolate_surface,
    elevation_profile, georeference_image, estimate_population_exposure,
    calculate_ndvi, calculate_ndwi, calculate_ndre,
    apply_raster_stretch, _auto_raster_style, _describe_population_raster,
    _run_raster_and_add, slope_analysis, aspect_analysis, zonal_statistics,
    raster_clip, unsupervised_classification, supervised_classification,
    mosaic_rasters, band_composite, pan_sharpening, hillshade, _geographic_z_factor,
    create_shaded_relief,
)



class TestGeographicZFactor(unittest.TestCase):
    """QGIS-006-follow-up: Z_FACTOR was hardcoded to 1 for hillshade/slope regardless of
    the DEM's CRS -- correct only on a projected (meters) CRS. On a geographic CRS
    (degrees), 1 vertical meter was being treated as 1 horizontal DEGREE (~111km),
    producing a flat/washed-out hillshade. _geographic_z_factor scales by the DEM's
    center latitude so vertical meters and horizontal degrees are comparable again."""

    def test_projected_crs_returns_1(self):
        dem = MagicMock()
        dem.crs.return_value.isGeographic.return_value = False
        self.assertEqual(_geographic_z_factor(dem), 1)

    def test_geographic_crs_at_equator_returns_inverse_of_111320(self):
        dem = MagicMock()
        dem.crs.return_value.isGeographic.return_value = True
        dem.extent.return_value.center.return_value.y.return_value = 0.0
        self.assertAlmostEqual(_geographic_z_factor(dem), 1.0 / 111320.0, places=9)

    def test_geographic_crs_at_high_latitude_returns_larger_z_factor(self):
        dem = MagicMock()
        dem.crs.return_value.isGeographic.return_value = True
        dem.extent.return_value.center.return_value.y.return_value = 50.0
        z = _geographic_z_factor(dem)
        # cos(50 deg) < 1, so 1/(111320*cos(50)) > 1/111320 (the equator value) --
        # higher latitudes need more vertical exaggeration to compensate for
        # longitude degrees shrinking, matching the report's own distortion table.
        self.assertGreater(z, 1.0 / 111320.0)

    def test_crs_lookup_failure_falls_back_to_1(self):
        dem = MagicMock()
        dem.crs.side_effect = RuntimeError("no CRS")
        self.assertEqual(_geographic_z_factor(dem), 1)

    def test_none_crs_falls_back_to_1(self):
        dem = MagicMock()
        dem.crs.return_value = None
        self.assertEqual(_geographic_z_factor(dem), 1)


class TestHillshadeUsesGeographicZFactor(unittest.TestCase):
    def test_hillshade_degrades_outside_qgis(self):
        res = hillshade("dem")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name", return_value=None)
    def test_hillshade_reports_missing_layer(self, mock_find):
        res = hillshade("ghost_dem")
        self.assertIn("error", res)
        self.assertIn("ghost_dem", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_hillshade_passes_computed_z_factor_not_hardcoded_1(self, mock_find, mock_run):
        dem = MagicMock()
        dem.crs.return_value.isGeographic.return_value = True
        dem.extent.return_value.center.return_value.y.return_value = 36.0
        mock_find.return_value = dem
        mock_run.return_value = {"success": True, "layer_name": "dem_hillshade"}

        res = hillshade("dem")

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "native:hillshade")
        self.assertAlmostEqual(params["Z_FACTOR"], 1.0 / (111320.0 * math.cos(math.radians(36.0))), places=9)

    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_hillshade_projected_crs_keeps_z_factor_1(self, mock_find, mock_run):
        dem = MagicMock()
        dem.crs.return_value.isGeographic.return_value = False
        mock_find.return_value = dem
        mock_run.return_value = {"success": True, "layer_name": "dem_hillshade"}

        res = hillshade("dem")

        self.assertTrue(res["success"])
        _, params, _ = mock_run.call_args[0]
        self.assertEqual(params["Z_FACTOR"], 1)


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
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_fewer_than_two_rasters(self):
        # Validated before any layer lookup, so this doesn't need QGIS mocks.
        res = weighted_overlay_analysis(["a"], [1.0])
        self.assertIn("error", res)
        self.assertIn("at least 2", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_too_many_rasters(self):
        names = [f"r{i}" for i in range(7)]
        weights = [1.0] * 7
        res = weighted_overlay_analysis(names, weights)
        self.assertIn("error", res)
        self.assertIn("at most", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_mismatched_weights_length(self):
        res = weighted_overlay_analysis(["a", "b"], [1.0])
        self.assertIn("error", res)
        self.assertIn("weights", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_all_zero_weights(self):
        res = weighted_overlay_analysis(["a", "b"], [0, 0])
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
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
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_unknown_method(self):
        res = interpolate_surface("points", "field", method="kriging")
        self.assertIn("error", res)
        self.assertIn("method", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
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
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_too_few_samples(self):
        res = elevation_profile("line", "dem", num_samples=1)
        self.assertIn("error", res)
        self.assertIn("num_samples", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
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

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
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
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_missing_file(self):
        res = georeference_image("/definitely/not/a/real/file.png", [{"pixel_x": 0, "pixel_y": 0, "lon": 0, "lat": 0}] * 3, "/out.tif")
        self.assertIn("error", res)
        self.assertIn("not found", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
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
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    def test_reports_missing_raster_layer(self, mock_find):
        mock_find.return_value = None
        res = estimate_population_exposure("ghost_pop", "districts")
        self.assertIn("error", res)
        self.assertIn("ghost_pop", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    def test_rejects_non_polygon_area_layer(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        raster = MagicMock()
        vector = MagicMock()
        vector.geometryType.return_value = "not-a-polygon"

        def side_effect(name):
            return {"pop": raster, "districts": vector}.get(name)
        mock_find.side_effect = side_effect

        res = estimate_population_exposure("pop", "districts")

        self.assertIn("error", res)
        self.assertIn("polygon", res["error"])


class TestDescribePopulationRaster(unittest.TestCase):
    """Pure Python, no QGIS needed -- point 9 of
    docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: provenance for a
    population raster must come only from what's actually knowable, never
    guessed."""

    def test_recognizes_worldpop_layer_naming_convention(self):
        source, year = _describe_population_raster("YEM_population_2020")
        self.assertEqual(source, "WorldPop")
        self.assertEqual(year, "2020")

    def test_falls_back_to_layer_name_for_non_worldpop_naming(self):
        source, year = _describe_population_raster("custom_pop_raster")
        self.assertEqual(source, "custom_pop_raster")
        self.assertIsNone(year)

    def test_handles_none_layer_name(self):
        source, year = _describe_population_raster(None)
        self.assertIsNone(source)
        self.assertIsNone(year)


class TestEstimatePopulationExposureEstimateFields(unittest.TestCase):
    """Point 9 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: the
    success return should carry explicit estimate/provenance fields
    (pop_exposed_est, pop_source, pop_reference_year, analysis_resolution,
    confidence) rather than a bare, unqualified total_population number --
    verified against a real invocation with QgsZonalStatistics injected into
    sys.modules (no qgis package is installed in this dev environment), not
    just the pure-Python helper above in isolation."""

    def _run(self, population_raster_layer):
        fake_zonal_module = MagicMock()
        fake_zonal_instance = MagicMock()
        fake_zonal_module.QgsZonalStatistics = MagicMock(return_value=fake_zonal_instance)

        raster = MagicMock()
        raster.rasterUnitsPerPixelX.return_value = 100.0
        raster.rasterUnitsPerPixelY.return_value = 100.0
        raster.crs.return_value.authid.return_value = "EPSG:4326"

        vector = MagicMock()
        vector.geometryType.return_value = "polygon-sentinel"
        vector.fields.return_value.indexFromName.return_value = 0
        vector.fields.return_value.count.return_value = 0
        feat = MagicMock()
        feat.attribute.side_effect = lambda f: 1000 if f == "pop_sum" else None
        vector.getFeatures.return_value = [feat]

        with patch.dict(sys.modules, {"qgis.analysis": fake_zonal_module}):
            with patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True), \
                 patch("cartogen_ai.core.agent.tools.raster_tools.QgsWkbTypes", create=True) as mock_wkb, \
                 patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name") as mock_find:
                mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
                mock_find.side_effect = lambda name: {population_raster_layer: raster, "districts": vector}.get(name)
                return estimate_population_exposure(population_raster_layer, "districts")

    def test_worldpop_named_raster_gets_source_and_year(self):
        res = self._run("YEM_population_2020")
        self.assertTrue(res.get("success"))
        self.assertEqual(res["total_population"], 1000)
        self.assertEqual(res["pop_exposed_est"], 1000)
        self.assertEqual(res["pop_source"], "WorldPop")
        self.assertEqual(res["pop_reference_year"], "2020")
        self.assertEqual(
            res["analysis_resolution"],
            {"pixel_width": 100.0, "pixel_height": 100.0, "crs": "EPSG:4326"},
        )
        self.assertEqual(res["confidence"], "estimate (gridded population raster; not field-verified)")

    def test_non_worldpop_named_raster_falls_back_to_layer_name(self):
        res = self._run("custom_pop_raster")
        self.assertEqual(res["pop_source"], "custom_pop_raster")
        self.assertIsNone(res["pop_reference_year"])


class TestAutoRasterStyle(unittest.TestCase):
    """Pure Python, no QGIS import needed -- see apply_raster_stretch below for the
    tool that consumes this."""

    def test_auto_picks_color_ramp_for_ndvi_named_layer(self):
        self.assertEqual(_auto_raster_style("NDVI", "auto"), ("color_ramp", "BrBG"))

    def test_auto_matches_case_insensitively_and_as_substring(self):
        self.assertEqual(_auto_raster_style("field3_ndwi_2026", "auto"), ("color_ramp", "RdBu"))

    def test_auto_picks_stretch_for_non_index_layer(self):
        self.assertEqual(_auto_raster_style("dem_hillshade", "auto"), ("stretch", None))

    def test_ndre_maps_to_diverging_ramp(self):
        self.assertEqual(_auto_raster_style("NDRE", "auto"), ("color_ramp", "BrBG"))

    def test_explicit_stretch_mode_ignores_name(self):
        self.assertEqual(_auto_raster_style("NDVI", "stretch"), ("stretch", None))

    def test_explicit_color_ramp_mode_on_non_index_name_has_no_default_ramp(self):
        self.assertEqual(_auto_raster_style("random_raster", "color_ramp"), ("color_ramp", None))

    def test_defaults_to_auto_when_mode_is_none(self):
        self.assertEqual(_auto_raster_style("NDVI", None), ("color_ramp", "BrBG"))

    def test_invalid_mode_returns_none(self):
        self.assertEqual(_auto_raster_style("NDVI", "bogus"), (None, None))


class TestApplyRasterStretchDegradesOutsideQgis(unittest.TestCase):
    def test_degrades(self):
        res = apply_raster_stretch("NDVI")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestApplyRasterStretchValidation(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_invalid_mode(self):
        res = apply_raster_stretch("NDVI", mode="bogus")
        self.assertIn("error", res)
        self.assertIn("mode", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_non_positive_band(self):
        res = apply_raster_stretch("NDVI", band=0)
        self.assertIn("error", res)
        self.assertIn("band", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_rejects_min_greater_or_equal_max(self):
        res = apply_raster_stretch("NDVI", min_value=5, max_value=5)
        self.assertIn("error", res)
        self.assertIn("min_value", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    def test_reports_missing_layer(self, mock_find):
        mock_find.return_value = None
        res = apply_raster_stretch("ghost_raster")
        self.assertIn("error", res)
        self.assertIn("ghost_raster", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    def test_rejects_band_beyond_band_count(self, mock_find):
        layer = MagicMock()
        layer.bandCount.return_value = 1
        mock_find.return_value = layer
        res = apply_raster_stretch("single_band_raster", band=2)
        self.assertIn("error", res)
        self.assertIn("band", res["error"].lower())

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
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

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools._RBS_MIN", None)
    def test_unresolved_raster_stats_enum_reports_a_clear_error(self, mock_find):
        # QGIS-005, 2026-09-14 audit: _RBS_MIN/etc. used to be usable with no explicit check --
        # a genuine resolution failure surfaced as a raw Python TypeError from `None | None`
        # instead of a clear message, same class of gap QGIS-004 fixed for _VFW_NO_ERROR.
        layer = MagicMock()
        layer.bandCount.return_value = 1
        mock_find.return_value = layer
        res = apply_raster_stretch("single_band_raster", band=1)
        self.assertIn("error", res)
        self.assertIn("Could not resolve", res["error"])


class TestRunRasterAndAdd(unittest.TestCase):
    """QUAL-006, 2026-09-14 audit: _run_raster_and_add is the shared helper 9 previously
    zero-coverage raster tools (slope_analysis, aspect_analysis, zonal_statistics,
    raster_clip, unsupervised_classification, supervised_classification, mosaic_rasters,
    band_composite, pan_sharpening) all route through -- none of them, nor the helper
    itself, ever had a real success-path test before this (only degrade-outside-QGIS
    existed for the sibling calculate_ndvi/ndwi/ndre, which use it too). Tested thoroughly
    once here; each tool's own test class below only needs to prove ITS wiring (which
    algorithm, which params) is correct, by mocking this helper directly."""

    def test_degrades_outside_qgis(self):
        res = _run_raster_and_add("native:slope", {"INPUT": None}, "out")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools.QgsRasterLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_success_path_adds_layer_and_returns_layer_name(self, mock_processing, mock_layer_cls, mock_project):
        # _temp_raster_path() creates a REAL (empty) temp file via tempfile.mkstemp, so
        # os.path.exists(out_path) is genuinely true here -- no need to mock the filesystem.
        new_layer = MagicMock()
        new_layer.isValid.return_value = True
        mock_layer_cls.return_value = new_layer

        params = {"INPUT": "fake-layer-object"}
        res = _run_raster_and_add("native:slope", params, "DEM_slope")

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["layer_name"], "DEM_slope")
        mock_processing.run.assert_called_once()
        alg_name, alg_params = mock_processing.run.call_args[0]
        self.assertEqual(alg_name, "native:slope")
        self.assertIn("OUTPUT", alg_params)  # default output_key
        mock_project.instance.return_value.addMapLayer.assert_called_once_with(new_layer)

    @patch("cartogen_ai.core.agent.tools.raster_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools.QgsRasterLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_custom_output_key_is_used_for_the_output_path(self, mock_processing, mock_layer_cls, mock_project):
        # unsupervised_classification/supervised_classification pass output_key="CLUSTER"/
        # "CLASSES" instead of the SAGA-incompatible default "OUTPUT" -- confirms that
        # actually reaches processing.run's params, not just accepted and ignored.
        mock_layer_cls.return_value = MagicMock(isValid=lambda: True)
        _run_raster_and_add("saga:kmeansclassificationforgrid", {"GRIDS": []}, "out", output_key="CLUSTER")
        _, alg_params = mock_processing.run.call_args[0]
        self.assertIn("CLUSTER", alg_params)
        self.assertNotIn("OUTPUT", alg_params)

    @patch("cartogen_ai.core.agent.tools.raster_tools.QgsRasterLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_invalid_generated_layer_reports_a_clear_error(self, mock_processing, mock_layer_cls):
        mock_layer_cls.return_value = MagicMock(isValid=lambda: False)
        res = _run_raster_and_add("native:slope", {"INPUT": "x"}, "out")
        self.assertIn("error", res)
        self.assertIn("invalid", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_processing_exception_is_caught_and_reported(self, mock_processing):
        mock_processing.run.side_effect = RuntimeError("GDAL error: no such algorithm")
        res = _run_raster_and_add("native:slope", {"INPUT": "x"}, "out")
        self.assertIn("error", res)
        self.assertIn("native:slope failed", res["error"])


class TestSlopeAndAspectAnalysis(unittest.TestCase):
    """slope_analysis/aspect_analysis: no test coverage at all before QUAL-006."""

    def test_slope_degrades_outside_qgis(self):
        res = slope_analysis("dem")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_aspect_degrades_outside_qgis(self):
        res = aspect_analysis("dem")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name", return_value=None)
    def test_slope_reports_missing_layer(self, mock_find):
        res = slope_analysis("ghost_dem")
        self.assertIn("error", res)
        self.assertIn("ghost_dem", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_slope_calls_native_slope_with_the_dem_layer(self, mock_find, mock_run):
        dem = MagicMock()
        mock_find.return_value = dem
        mock_run.return_value = {"success": True, "layer_name": "dem_slope"}

        res = slope_analysis("dem")

        self.assertTrue(res["success"])
        mock_run.assert_called_once()
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "native:slope")
        self.assertIs(params["INPUT"], dem)
        self.assertEqual(new_name, "dem_slope")

    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_aspect_calls_native_aspect_with_the_dem_layer(self, mock_find, mock_run):
        dem = MagicMock()
        mock_find.return_value = dem
        mock_run.return_value = {"success": True, "layer_name": "dem_aspect"}

        res = aspect_analysis("dem")

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "native:aspect")
        self.assertIs(params["INPUT"], dem)


class TestZonalStatisticsTool(unittest.TestCase):
    """zonal_statistics: no test coverage at all before QUAL-006. Doesn't use
    _run_raster_and_add (writes attributes onto the vector layer in place instead), so
    tested against a directly-mocked processing.run."""

    def test_degrades_outside_qgis(self):
        res = zonal_statistics("dem", "zones")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    def test_reports_missing_raster_layer(self, mock_find):
        mock_find.side_effect = lambda name: None if name == "dem" else MagicMock()
        res = zonal_statistics("dem", "zones")
        self.assertIn("error", res)
        self.assertIn("dem", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    def test_reports_missing_vector_layer(self, mock_find):
        mock_find.side_effect = lambda name: MagicMock() if name == "dem" else None
        res = zonal_statistics("dem", "zones")
        self.assertIn("error", res)
        self.assertIn("zones", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_success_runs_qgis_zonalstatistics_with_both_layers(self, mock_find, mock_processing):
        ras, vec = MagicMock(), MagicMock()
        mock_find.side_effect = lambda name: {"dem": ras, "zones": vec}[name]

        res = zonal_statistics("dem", "zones")

        self.assertTrue(res.get("success"), res)
        self.assertIn("zones", res["message"])
        alg, params = mock_processing.run.call_args[0]
        self.assertEqual(alg, "qgis:zonalstatistics")
        self.assertIs(params["INPUT_RASTER"], ras)
        self.assertIs(params["INPUT_VECTOR"], vec)

    @patch("cartogen_ai.core.agent.tools.raster_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_processing_exception_is_reported_not_raised(self, mock_find, mock_processing):
        mock_find.side_effect = lambda name: MagicMock()
        mock_processing.run.side_effect = RuntimeError("boom")
        res = zonal_statistics("dem", "zones")
        self.assertIn("error", res)
        self.assertIn("zonal_statistics failed", res["error"])


class TestRasterClipTool(unittest.TestCase):
    """raster_clip: no test coverage at all before QUAL-006."""

    def test_degrades_outside_qgis(self):
        res = raster_clip("dem", "mask")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    def test_reports_missing_mask_layer(self, mock_find):
        mock_find.side_effect = lambda name: MagicMock() if name == "dem" else None
        res = raster_clip("dem", "mask")
        self.assertIn("error", res)
        self.assertIn("mask", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_calls_gdal_clip_with_crop_to_cutline(self, mock_find, mock_run):
        ras, mask = MagicMock(), MagicMock()
        mock_find.side_effect = lambda name: {"dem": ras, "mask": mask}[name]
        mock_run.return_value = {"success": True, "layer_name": "dem_clipped"}

        res = raster_clip("dem", "mask")

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "gdal:cliprasterbymasklayer")
        self.assertIs(params["INPUT"], ras)
        self.assertIs(params["MASK"], mask)
        self.assertTrue(params["CROP_TO_CUTLINE"])
        self.assertEqual(new_name, "dem_clipped")


class TestClassificationTools(unittest.TestCase):
    """unsupervised_classification/supervised_classification: no test coverage at all
    before QUAL-006."""

    def test_unsupervised_degrades_outside_qgis(self):
        res = unsupervised_classification("img", 5)
        self.assertIn("error", res)

    def test_supervised_degrades_outside_qgis(self):
        res = supervised_classification("img", "training")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_unsupervised_passes_num_classes_as_clusters_and_custom_output_key(self, mock_find, mock_run):
        img = MagicMock()
        mock_find.return_value = img
        mock_run.return_value = {"success": True, "layer_name": "img_classified"}

        res = unsupervised_classification("img", 7)

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "saga:kmeansclassificationforgrid")
        self.assertEqual(params["CLUSTERS"], 7)
        self.assertEqual(mock_run.call_args[1]["output_key"], "CLUSTER")

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name", return_value=None)
    def test_supervised_reports_missing_raster_layer(self, mock_find):
        res = supervised_classification("img", "training")
        self.assertIn("error", res)
        self.assertIn("img", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_supervised_passes_training_layer_and_custom_output_key(self, mock_find, mock_run):
        img, training = MagicMock(), MagicMock()
        mock_find.side_effect = lambda name: {"img": img, "training": training}[name]
        mock_run.return_value = {"success": True, "layer_name": "img_classified"}

        res = supervised_classification("img", "training")

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "saga:supervisedclassificationforgrids")
        self.assertIs(params["TRAINING"], training)
        self.assertEqual(mock_run.call_args[1]["output_key"], "CLASSES")


class TestMosaicBandCompositePanSharpening(unittest.TestCase):
    """mosaic_rasters/band_composite/pan_sharpening: no test coverage at all before
    QUAL-006."""

    def test_mosaic_degrades_outside_qgis(self):
        res = mosaic_rasters(["a", "b"])
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_mosaic_rejects_fewer_than_two_rasters(self):
        res = mosaic_rasters(["only_one"])
        self.assertIn("error", res)
        self.assertIn("at least 2", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    def test_mosaic_reports_first_missing_layer(self, mock_find):
        mock_find.side_effect = lambda name: MagicMock() if name == "a" else None
        res = mosaic_rasters(["a", "b"])
        self.assertIn("error", res)
        self.assertIn("b", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_mosaic_passes_every_resolved_layer_to_gdal_merge(self, mock_find, mock_run):
        a, b, c = MagicMock(), MagicMock(), MagicMock()
        mock_find.side_effect = lambda name: {"a": a, "b": b, "c": c}[name]
        mock_run.return_value = {"success": True, "layer_name": "mosaic_raster"}

        res = mosaic_rasters(["a", "b", "c"])

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "gdal:merge")
        self.assertEqual(params["INPUT"], [a, b, c])
        self.assertFalse(params["SEPARATE"])

    def test_band_composite_degrades_outside_qgis(self):
        res = band_composite("rgb", "r", "g", "b")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    def test_band_composite_reports_any_missing_band(self, mock_find):
        mock_find.side_effect = lambda name: MagicMock() if name != "blue" else None
        res = band_composite("rgb", "red", "green", "blue")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_band_composite_uses_separate_true_for_gdal_merge(self, mock_find, mock_run):
        r, g, b = MagicMock(), MagicMock(), MagicMock()
        mock_find.side_effect = lambda name: {"red": r, "green": g, "blue": b}[name]
        mock_run.return_value = {"success": True, "layer_name": "rgb"}

        res = band_composite("rgb", "red", "green", "blue")

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "gdal:merge")
        self.assertEqual(params["INPUT"], [r, g, b])
        self.assertTrue(params["SEPARATE"])
        self.assertEqual(new_name, "rgb")

    def test_pan_sharpening_degrades_outside_qgis(self):
        res = pan_sharpening("ms", "pan")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    def test_pan_sharpening_reports_missing_pan_layer(self, mock_find):
        mock_find.side_effect = lambda name: MagicMock() if name == "ms" else None
        res = pan_sharpening("ms", "pan")
        self.assertIn("error", res)
        self.assertIn("pan", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_pan_sharpening_wires_spectral_and_panchromatic_bands(self, mock_find, mock_run):
        ms, pan = MagicMock(), MagicMock()
        mock_find.side_effect = lambda name: {"ms": ms, "pan": pan}[name]
        mock_run.return_value = {"success": True, "layer_name": "ms_pansharpened"}

        res = pan_sharpening("ms", "pan")

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "gdal:pansharpening")
        self.assertIs(params["SPECTRAL"], ms)
        self.assertIs(params["PANCHROMATIC"], pan)


class TestCreateShadedRelief(unittest.TestCase):
    """Part B remediation: combines hypsometric elevation tint with hillshade
    using Multiply blending mode (QPainter.CompositionMode_Multiply)."""

    def test_degrades_outside_qgis(self):
        res = create_shaded_relief("dem")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    def test_reports_missing_dem_layer(self, mock_find):
        mock_find.return_value = None
        res = create_shaded_relief("dem")
        self.assertIn("error", res)
        self.assertIn("dem", res["error"])

    def test_invalid_opacity_rejected(self):
        with patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True), \
             patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name", return_value=MagicMock()):
            res = create_shaded_relief("elevation", opacity=1.5)
            self.assertIn("error", res)
            self.assertIn("opacity", res["error"])

            res2 = create_shaded_relief("elevation", opacity="invalid")
            self.assertIn("error", res2)
            self.assertIn("opacity", res2["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools.apply_raster_stretch")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_blend_mode_unsupported_returns_error(self, mock_find, mock_stretch, mock_run):
        dem_mock = MagicMock()
        hs_mock = MagicMock()
        del hs_mock.setBlendMode  # Simulate layer lacking setBlendMode
        mock_find.side_effect = lambda name: dem_mock if name == "elevation" else (hs_mock if name == "elevation_hillshade" else None)
        mock_stretch.return_value = {"success": True, "color_ramp": "BrBG"}
        mock_run.return_value = {"success": True, "layer_name": "elevation_hillshade"}

        res = create_shaded_relief("elevation")
        self.assertIn("error", res)
        self.assertIn("Multiply", res["error"])

    @patch("cartogen_ai.core.agent.tools.raster_tools._COMPOSITION_MULTIPLY", new=13)
    @patch("cartogen_ai.core.agent.tools.raster_tools._run_raster_and_add")
    @patch("cartogen_ai.core.agent.tools.raster_tools.apply_raster_stretch")
    @patch("cartogen_ai.core.agent.tools.raster_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.raster_tools.QGIS_AVAILABLE", True)
    def test_successful_shaded_relief_pipeline(self, mock_find, mock_stretch, mock_run):
        dem_mock = MagicMock()
        hs_mock = MagicMock()
        mock_find.side_effect = lambda name: dem_mock if name == "elevation" else (hs_mock if name == "elevation_hillshade" else None)
        mock_stretch.return_value = {"success": True, "color_ramp": "BrBG"}
        mock_run.return_value = {"success": True, "layer_name": "elevation_hillshade"}

        res = create_shaded_relief("elevation", color_ramp="BrBG", azimuth=315, altitude=45, opacity=0.8)



        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["dem_layer"], "elevation")
        self.assertEqual(res["hillshade_layer"], "elevation_hillshade")
        self.assertEqual(res["blend_mode"], "Multiply")
        self.assertEqual(res["opacity"], 0.8)
        mock_stretch.assert_called_once_with("elevation", mode="color_ramp", color_ramp="BrBG")
        mock_run.assert_called_once()
        hs_mock.setOpacity.assert_called_once_with(0.8)



if __name__ == "__main__":
    unittest.main()
