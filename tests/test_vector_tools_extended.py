# -*- coding: utf-8 -*-
"""Tests for the geoprocessing/selection tools added to vector_tools.py in the
QGIS-feature-coverage pass (difference, convex hull/Voronoi/Delaunay, nearest-
feature join, singlepart/simplify, field statistics, select-by-location).
Follows the same QGIS_AVAILABLE=False degrade-path convention used
throughout tests/test_new_tools.py and tests/test_styling_tools.py."""
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.tools.vector_tools import (
    difference_layers, convex_hull, voronoi_polygons, delaunay_triangulation,
    find_nearest_features, convert_to_singlepart, simplify_geometry,
    field_statistics, select_by_location, invert_selection,
    _compute_field_statistics, zoom_to_layer, zoom_to_feature, _extent_to_canvas_crs,
    apply_labels, get_layers, diagnose_topology, _run_and_add, buffer_analysis,
    rename_layer, toggle_visibility, intersect_layers, union_layers, dissolve_layer,
    merge_layers, reproject_layer, fix_geometries, select_by_attribute,
    get_feature_count, open_attribute_table, verify_crs_compatibility,
    _ensure_shapefile_encoding, add_layer_from_path, _ensure_spatialite_index,
)


class TestComputeFieldStatistics(unittest.TestCase):
    """Pure Python, no QGIS import needed."""

    def test_basic_stats(self):
        stats = _compute_field_statistics([1, 2, 3, 4, 5])
        self.assertEqual(stats["count"], 5)
        self.assertEqual(stats["sum"], 15)
        self.assertEqual(stats["mean"], 3)
        self.assertEqual(stats["median"], 3)
        self.assertEqual(stats["min"], 1)
        self.assertEqual(stats["max"], 5)
        self.assertEqual(stats["range"], 4)

    def test_even_count_median_averages_middle_two(self):
        stats = _compute_field_statistics([1, 2, 3, 4])
        self.assertEqual(stats["median"], 2.5)

    def test_empty_list_returns_none(self):
        self.assertIsNone(_compute_field_statistics([]))

    def test_constant_values_have_zero_stdev(self):
        stats = _compute_field_statistics([5, 5, 5, 5])
        self.assertEqual(stats["stdev"], 0)


class TestVectorToolsDegradeOutsideQgis(unittest.TestCase):
    def test_difference_layers_degrades(self):
        res = difference_layers("a", "b")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_convex_hull_degrades(self):
        res = convex_hull("layer")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_voronoi_polygons_degrades(self):
        res = voronoi_polygons("layer")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_delaunay_triangulation_degrades(self):
        res = delaunay_triangulation("layer")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_find_nearest_features_degrades(self):
        res = find_nearest_features("a", "b")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_convert_to_singlepart_degrades(self):
        res = convert_to_singlepart("layer")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_simplify_geometry_degrades(self):
        res = simplify_geometry("layer", 1.0)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_field_statistics_degrades(self):
        res = field_statistics("layer", "field")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_select_by_location_degrades(self):
        res = select_by_location("a", "b")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_invert_selection_degrades(self):
        res = invert_selection("layer")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestVectorToolsValidation(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_simplify_geometry_rejects_non_positive_tolerance(self):
        # Validated before any layer lookup, so this doesn't need QGIS mocks.
        res = simplify_geometry("layer", 0)
        self.assertIn("error", res)
        self.assertIn("tolerance", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_find_nearest_features_rejects_zero_neighbors(self):
        res = find_nearest_features("a", "b", neighbors=0)
        self.assertIn("error", res)
        self.assertIn("neighbors", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_select_by_location_rejects_unknown_predicate(self):
        res = select_by_location("a", "b", predicate="nonsense")
        self.assertIn("error", res)
        self.assertIn("predicate", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_select_by_location_rejects_unknown_method(self):
        res = select_by_location("a", "b", method="nonsense")
        self.assertIn("error", res)
        self.assertIn("method", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_voronoi_polygons_rejects_non_point_layers(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PointGeometry = "point-sentinel"
        fake_layer = MagicMock()
        fake_layer.geometryType.return_value = "not-a-point"
        mock_find.return_value = fake_layer

        res = voronoi_polygons("layer")

        self.assertIn("error", res)
        self.assertIn("point layers", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_delaunay_triangulation_rejects_non_point_layers(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PointGeometry = "point-sentinel"
        fake_layer = MagicMock()
        fake_layer.geometryType.return_value = "not-a-point"
        mock_find.return_value = fake_layer

        res = delaunay_triangulation("layer")

        self.assertIn("error", res)
        self.assertIn("point layers", res["error"])


class TestExtentToCanvasCrs(unittest.TestCase):
    """No live QGIS needed -- canvas/CRS/transform are all mocked. This is
    the fix for a real live-session bug: canvas.setExtent() expects the
    extent already in the canvas's own CRS, but zoom_to_layer/zoom_to_feature
    were passing the extent straight from the layer's own CRS with no
    transform -- silently landing the view near the map's coordinate origin
    instead of the actual layer whenever layer CRS != project CRS (e.g. a
    freshly fetched WGS84 boundary layer against a Web Mercator OSM-basemap
    project, a near-universal setup)."""

    def _fake_canvas(self, dest_crs):
        canvas = MagicMock()
        canvas.mapSettings.return_value.destinationCrs.return_value = dest_crs
        return canvas

    def test_same_crs_object_returns_extent_unchanged(self):
        crs = MagicMock()
        crs.isValid.return_value = True
        canvas = self._fake_canvas(crs)  # canvas destination CRS is the same object
        extent = object()

        result = _extent_to_canvas_crs(canvas, extent, crs)

        self.assertIs(result, extent)

    def test_invalid_source_crs_returns_extent_unchanged(self):
        source_crs = MagicMock()
        source_crs.isValid.return_value = False
        canvas = self._fake_canvas(MagicMock())
        extent = object()

        result = _extent_to_canvas_crs(canvas, extent, source_crs)

        self.assertIs(result, extent)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsCoordinateTransform", create=True)
    def test_different_valid_crs_transforms_the_extent(self, mock_transform_cls, mock_project):
        source_crs = MagicMock()
        source_crs.isValid.return_value = True
        dest_crs = MagicMock()  # a distinct object -- default Mock equality is identity-based
        canvas = self._fake_canvas(dest_crs)
        extent = MagicMock()
        transformed = MagicMock()
        mock_transform_cls.return_value.transformBoundingBox.return_value = transformed

        result = _extent_to_canvas_crs(canvas, extent, source_crs)

        mock_transform_cls.assert_called_once_with(source_crs, dest_crs, mock_project.instance.return_value)
        mock_transform_cls.return_value.transformBoundingBox.assert_called_once_with(extent)
        self.assertIs(result, transformed)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsCoordinateTransform", create=True)
    def test_transform_failure_returns_none_not_the_original_extent(self, mock_transform_cls, mock_project):
        source_crs = MagicMock()
        source_crs.isValid.return_value = True
        canvas = self._fake_canvas(MagicMock())
        extent = object()
        mock_transform_cls.side_effect = Exception("boom")

        result = _extent_to_canvas_crs(canvas, extent, source_crs)

        self.assertIsNone(result)   # audit A13: a failed transform must not masquerade as a good extent


class TestZoomToolsDegradeOutsideQgis(unittest.TestCase):
    def test_zoom_to_layer_degrades(self):
        res = zoom_to_layer("layer")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_zoom_to_feature_degrades(self):
        res = zoom_to_feature("layer", 1)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestZoomToLayerUsesCanvasCrsTransform(unittest.TestCase):
    """Confirms zoom_to_layer/zoom_to_feature actually route the extent
    through _extent_to_canvas_crs rather than passing the layer's raw extent
    straight to canvas.setExtent() -- the exact bug this fix addresses."""

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._extent_to_canvas_crs")
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.iface")
    def test_zoom_to_layer_transforms_extent_before_setting_it(self, mock_iface, mock_find, mock_transform_fn):
        fake_layer = MagicMock()
        fake_extent = MagicMock()
        fake_layer.extent.return_value = fake_extent
        mock_find.return_value = fake_layer
        mock_canvas = MagicMock()
        mock_iface.mapCanvas.return_value = mock_canvas
        transformed_extent = MagicMock()
        mock_transform_fn.return_value = transformed_extent

        res = zoom_to_layer("layer")

        self.assertTrue(res.get("success"), res)
        mock_transform_fn.assert_called_once_with(mock_canvas, fake_extent, fake_layer.crs.return_value)
        mock_canvas.setExtent.assert_called_once_with(transformed_extent)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._extent_to_canvas_crs")
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.iface")
    def test_zoom_to_feature_transforms_extent_before_setting_it(self, mock_iface, mock_find, mock_transform_fn):
        fake_layer = MagicMock()
        fake_feature = MagicMock()
        fake_feature.isValid.return_value = True
        fake_geom = MagicMock()
        fake_geom.isEmpty.return_value = False
        fake_bbox = MagicMock()
        fake_geom.boundingBox.return_value = fake_bbox
        fake_feature.geometry.return_value = fake_geom
        fake_layer.getFeature.return_value = fake_feature
        mock_find.return_value = fake_layer
        mock_canvas = MagicMock()
        mock_iface.mapCanvas.return_value = mock_canvas
        transformed_extent = MagicMock()
        mock_transform_fn.return_value = transformed_extent

        res = zoom_to_feature("layer", 1)

        self.assertTrue(res.get("success"), res)
        mock_transform_fn.assert_called_once_with(mock_canvas, fake_bbox, fake_layer.crs.return_value)
        mock_canvas.setExtent.assert_called_once_with(transformed_extent)


class TestZoomToFeatureByExpression(unittest.TestCase):
    """zoom_to_feature previously required a numeric feature_id known in
    advance, forcing hand-written execute_pyqgis_script lookups (which
    reproduced the exact CRS bug this whole file's other fix already closed,
    confirmed live) whenever the model only had an attribute value like a
    governorate name. The expression parameter closes that gap."""

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.iface")
    def test_rejects_neither_feature_id_nor_expression(self, mock_iface, mock_find):
        mock_find.return_value = MagicMock()
        res = zoom_to_feature("layer")
        self.assertIn("error", res)
        self.assertIn("feature_id or expression", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.iface")
    def test_rejects_both_feature_id_and_expression(self, mock_iface, mock_find):
        mock_find.return_value = MagicMock()
        res = zoom_to_feature("layer", feature_id=1, expression="name = 'X'")
        self.assertIn("error", res)
        self.assertIn("only one of", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.iface")
    def test_rejects_invalid_expression(self, mock_iface, mock_find, mock_expr_cls):
        mock_find.return_value = MagicMock()
        mock_expr_cls.return_value.hasParserError.return_value = True
        mock_expr_cls.return_value.parserErrorString.return_value = "syntax error"

        res = zoom_to_feature("layer", expression="not valid ((")

        self.assertIn("error", res)
        self.assertIn("syntax error", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsFeatureRequest", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.iface")
    def test_expression_matching_no_features_is_rejected(self, mock_iface, mock_find, mock_expr_cls, mock_request_cls):
        mock_expr_cls.return_value.hasParserError.return_value = False
        fake_layer = MagicMock()
        fake_layer.getFeatures.return_value = []
        mock_find.return_value = fake_layer

        res = zoom_to_feature("layer", expression="name = 'Nowhere'")

        self.assertIn("error", res)
        self.assertIn("No feature", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsFeatureRequest", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.iface")
    def test_expression_matching_multiple_features_is_rejected(self, mock_iface, mock_find, mock_expr_cls, mock_request_cls):
        mock_expr_cls.return_value.hasParserError.return_value = False
        fake_layer = MagicMock()
        fake_layer.getFeatures.return_value = [MagicMock(), MagicMock()]
        mock_find.return_value = fake_layer

        res = zoom_to_feature("layer", expression="phase = 4")

        self.assertIn("error", res)
        self.assertIn("expected exactly one", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._extent_to_canvas_crs")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsFeatureRequest", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.iface")
    def test_expression_matching_one_feature_zooms_and_selects(self, mock_iface, mock_find, mock_expr_cls, mock_request_cls, mock_transform_fn):
        mock_expr_cls.return_value.hasParserError.return_value = False
        fake_feature = MagicMock()
        fake_feature.id.return_value = 14
        fake_geom = MagicMock()
        fake_geom.isEmpty.return_value = False
        fake_feature.geometry.return_value = fake_geom
        fake_layer = MagicMock()
        fake_layer.getFeatures.return_value = [fake_feature]
        mock_find.return_value = fake_layer
        mock_canvas = MagicMock()
        mock_iface.mapCanvas.return_value = mock_canvas
        mock_transform_fn.return_value = MagicMock()

        res = zoom_to_feature("layer", expression="name = 'Ma\\'rib'")

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["feature_id"], 14)
        mock_canvas.setExtent.assert_called_once()
        fake_layer.selectByIds.assert_called_once_with([14])


class TestGetLayersEnrichedFields(unittest.TestCase):
    """Point 21 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: get_layers
    used to return only {name, type, id}, forcing a separate get_attributes call per
    layer for fields, and no way at all to see CRS/feature_count without yet another
    call -- now returns crs/fields/feature_count in the same call, with fields/
    feature_count only present for layer types that actually have them (e.g. not a
    raster)."""

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    def test_vector_layer_includes_crs_fields_and_feature_count(self, mock_project):
        vector_layer = MagicMock(spec=["name", "type", "crs", "fields", "featureCount"])
        vector_layer.name.return_value = "districts"
        vector_layer.type.return_value = "VectorLayer"
        vector_layer.crs.return_value.authid.return_value = "EPSG:4326"
        vector_layer.fields.return_value.names.return_value = ["admin2_name", "admin2_pcode"]
        vector_layer.featureCount.return_value = 287
        mock_project.instance.return_value.mapLayers.return_value = {"layer1": vector_layer}

        result = get_layers()

        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["name"], "districts")
        self.assertEqual(entry["id"], "layer1")
        self.assertEqual(entry["crs"], "EPSG:4326")
        self.assertEqual(entry["fields"], ["admin2_name", "admin2_pcode"])
        self.assertEqual(entry["feature_count"], 287)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    def test_raster_layer_omits_fields_and_feature_count(self, mock_project):
        raster_layer = MagicMock(spec=["name", "type", "crs"])
        raster_layer.name.return_value = "population_raster"
        raster_layer.type.return_value = "RasterLayer"
        raster_layer.crs.return_value.authid.return_value = "EPSG:32637"
        mock_project.instance.return_value.mapLayers.return_value = {"layer2": raster_layer}

        result = get_layers()

        entry = result[0]
        self.assertEqual(entry["crs"], "EPSG:32637")
        self.assertNotIn("fields", entry)
        self.assertNotIn("feature_count", entry)


class TestApplyLabels(unittest.TestCase):
    def test_degrades_gracefully_outside_qgis(self):
        res = apply_labels("layer", target_field="name")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_rejects_neither_target_field_nor_expression(self, mock_find):
        mock_find.return_value = MagicMock()
        res = apply_labels("layer")
        self.assertIn("error", res)
        self.assertIn("target_field or expression", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_rejects_both_target_field_and_expression(self, mock_find):
        mock_find.return_value = MagicMock()
        res = apply_labels("layer", target_field="name", expression="1+1")
        self.assertIn("error", res)
        self.assertIn("only one of", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsPalLayerSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextFormat", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_rejects_invalid_expression(self, mock_find, mock_expr_cls, mock_fmt_cls, mock_settings_cls):
        mock_find.return_value = MagicMock()
        mock_expr_cls.return_value.hasParserError.return_value = True
        mock_expr_cls.return_value.parserErrorString.return_value = "syntax error"

        res = apply_labels("layer", expression="not valid ((")

        self.assertIn("error", res)
        self.assertIn("syntax error", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QColor", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsUnitTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.Qt", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextBufferSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsPalLayerSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextFormat", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayerSimpleLabeling", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_valid_expression_sets_is_expression_true(
        self, mock_find, mock_expr_cls, mock_labeling_cls, mock_fmt_cls, mock_settings_cls,
        mock_buffer_cls, mock_qt, mock_unit_types, mock_qcolor, mock_wkb,
    ):
        fake_layer = MagicMock()
        fake_layer.geometryType.return_value = "NOT_A_POINT"
        mock_wkb.GeometryType.PointGeometry = "POINT_SENTINEL"
        mock_find.return_value = fake_layer
        mock_expr_cls.return_value.hasParserError.return_value = False
        settings_instance = mock_settings_cls.return_value

        res = apply_labels("layer", expression="a || b")

        self.assertTrue(res.get("success"), res)
        self.assertEqual(settings_instance.fieldName, "a || b")
        self.assertTrue(settings_instance.isExpression)
        fake_layer.setLabelsEnabled.assert_called_once_with(True)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QColor", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsUnitTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.Qt", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextBufferSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsPalLayerSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextFormat", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayerSimpleLabeling", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_applies_text_buffer_halo_by_default(
        self, mock_find, mock_expr_cls, mock_labeling_cls, mock_fmt_cls, mock_settings_cls,
        mock_buffer_cls, mock_qt, mock_unit_types, mock_qcolor, mock_wkb,
    ):
        fake_layer = MagicMock()
        fake_layer.geometryType.return_value = "NOT_A_POINT"
        mock_wkb.GeometryType.PointGeometry = "POINT_SENTINEL"
        mock_find.return_value = fake_layer
        mock_expr_cls.return_value.hasParserError.return_value = False
        buffer_instance = mock_buffer_cls.return_value
        text_format_instance = mock_fmt_cls.return_value

        res = apply_labels("layer", expression="a")

        self.assertTrue(res.get("success"), res)
        buffer_instance.setEnabled.assert_called_once_with(True)
        buffer_instance.setSize.assert_called_once_with(0.8)
        text_format_instance.setBuffer.assert_called_once_with(buffer_instance)
        self.assertIn("halo enabled", res["message"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QColor", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsUnitTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.Qt", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextBufferSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsPalLayerSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextFormat", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayerSimpleLabeling", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_font_size_and_priority_are_configurable(
        self, mock_find, mock_expr_cls, mock_labeling_cls, mock_fmt_cls, mock_settings_cls,
        mock_buffer_cls, mock_qt, mock_unit_types, mock_qcolor, mock_wkb,
    ):
        fake_layer = MagicMock()
        fake_layer.geometryType.return_value = "NOT_A_POINT"
        mock_wkb.GeometryType.PointGeometry = "POINT_SENTINEL"
        mock_find.return_value = fake_layer
        mock_expr_cls.return_value.hasParserError.return_value = False
        settings_instance = mock_settings_cls.return_value
        text_format_instance = mock_fmt_cls.return_value

        res = apply_labels("layer", expression="a", font_size=14, priority=9)

        self.assertTrue(res.get("success"), res)
        text_format_instance.setSize.assert_called_once_with(14)
        self.assertEqual(settings_instance.priority, 9)
        self.assertIn("priority=9", res["message"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QColor", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsUnitTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.Qt", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextBufferSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsPalLayerSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextFormat", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayerSimpleLabeling", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_point_layer_gets_ordered_positions_placement(
        self, mock_find, mock_expr_cls, mock_labeling_cls, mock_fmt_cls, mock_settings_cls,
        mock_buffer_cls, mock_qt, mock_unit_types, mock_qcolor, mock_wkb,
    ):
        fake_layer = MagicMock()
        mock_wkb.GeometryType.PointGeometry = "POINT_SENTINEL"
        fake_layer.geometryType.return_value = "POINT_SENTINEL"
        mock_find.return_value = fake_layer
        mock_expr_cls.return_value.hasParserError.return_value = False
        mock_settings_cls.Placement.OrderedPositionsAroundPoint = "ORDERED_POSITIONS_SENTINEL"
        settings_instance = mock_settings_cls.return_value

        res = apply_labels("layer", expression="a")

        self.assertTrue(res.get("success"), res)
        self.assertEqual(settings_instance.placement, "ORDERED_POSITIONS_SENTINEL")

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QColor", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsUnitTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.Qt", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextBufferSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsPalLayerSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextFormat", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayerSimpleLabeling", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_sets_obstacle_settings_as_obstacle(
        self, mock_find, mock_expr_cls, mock_labeling_cls, mock_fmt_cls, mock_settings_cls,
        mock_buffer_cls, mock_qt, mock_unit_types, mock_qcolor, mock_wkb,
    ):
        fake_layer = MagicMock()
        fake_layer.geometryType.return_value = "NOT_A_POINT"
        mock_wkb.GeometryType.PointGeometry = "POINT_SENTINEL"
        mock_find.return_value = fake_layer
        mock_expr_cls.return_value.hasParserError.return_value = False
        settings_instance = mock_settings_cls.return_value

        res = apply_labels("layer", expression="a")

        self.assertTrue(res.get("success"), res)
        settings_instance.obstacleSettings.return_value.setIsObstacle.assert_called_once_with(True)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsPalLayerSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextFormat", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_target_field_not_on_layer_is_rejected(self, mock_find, mock_fmt_cls, mock_settings_cls):
        fake_field = MagicMock()
        fake_field.name.return_value = "other"
        fake_layer = MagicMock()
        fake_layer.fields.return_value = [fake_field]
        mock_find.return_value = fake_layer

        res = apply_labels("layer", target_field="missing")

        self.assertIn("error", res)
        self.assertIn("not found", res["error"])


class TestEnsureShapefileEncoding(unittest.TestCase):
    """No .cpg -> a shapefile's text encoding is whatever GDAL's platform default happens
    to be (commonly Windows-1252 on Windows), silently corrupting non-Latin-script
    attribute values (Arabic, Cyrillic) with no error raised anywhere -- relevant given
    this project's humanitarian/OCHA data. _ensure_shapefile_encoding overrides to UTF-8
    when no .cpg is present, and leaves GDAL's own encoding detection alone when one is."""

    def test_cpg_present_leaves_encoding_untouched(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            shp_path = os.path.join(tmp_dir, "districts.shp")
            cpg_path = os.path.join(tmp_dir, "districts.cpg")
            open(shp_path, "w").close()
            open(cpg_path, "w").close()
            layer = MagicMock()

            note = _ensure_shapefile_encoding(layer, shp_path)

            self.assertIsNone(note)
            layer.dataProvider.assert_not_called()

    def test_missing_cpg_sets_utf8_encoding(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            shp_path = os.path.join(tmp_dir, "districts.shp")
            open(shp_path, "w").close()
            layer = MagicMock()

            note = _ensure_shapefile_encoding(layer, shp_path)

            self.assertIsNotNone(note)
            self.assertIn("UTF-8", note)
            layer.dataProvider.return_value.setEncoding.assert_called_once_with("UTF-8")

    def test_encoding_override_failure_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            shp_path = os.path.join(tmp_dir, "districts.shp")
            open(shp_path, "w").close()
            layer = MagicMock()
            layer.dataProvider.side_effect = RuntimeError("no provider")

            note = _ensure_shapefile_encoding(layer, shp_path)

            self.assertIsNotNone(note)
            self.assertIn("could not override", note.lower())


class TestEnsureSpatialiteIndex(unittest.TestCase):
    def test_index_already_exists_or_created_returns_none(self):
        layer = MagicMock()
        layer.dataProvider.return_value.createSpatialIndex.return_value = True
        self.assertIsNone(_ensure_spatialite_index(layer))

    def test_index_creation_failure_returns_a_note(self):
        layer = MagicMock()
        layer.dataProvider.return_value.createSpatialIndex.return_value = False
        note = _ensure_spatialite_index(layer)
        self.assertIsNotNone(note)
        self.assertIn("spatial index", note)

    def test_no_data_provider_returns_none(self):
        layer = MagicMock()
        layer.dataProvider.return_value = None
        self.assertIsNone(_ensure_spatialite_index(layer))

    def test_exception_is_reported_not_raised(self):
        layer = MagicMock()
        layer.dataProvider.side_effect = RuntimeError("boom")
        note = _ensure_spatialite_index(layer)
        self.assertIsNotNone(note)
        self.assertIn("boom", note)


class TestAddLayerFromPathShapefileEncoding(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayer", create=True)
    def test_shp_with_no_cpg_reports_encoding_note(self, mock_layer_cls, mock_project):
        with tempfile.TemporaryDirectory() as tmp_dir:
            shp_path = os.path.join(tmp_dir, "districts.shp")
            open(shp_path, "w").close()
            fake_layer = MagicMock()
            fake_layer.isValid.return_value = True
            fake_layer.name.return_value = "districts"
            mock_layer_cls.return_value = fake_layer

            res = add_layer_from_path(shp_path)

            self.assertTrue(res["success"], res)
            self.assertIn("encoding_note", res)
            self.assertIn("UTF-8", res["encoding_note"])
            fake_layer.dataProvider.return_value.setEncoding.assert_called_once_with("UTF-8")

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayer", create=True)
    def test_shp_with_cpg_has_no_encoding_note(self, mock_layer_cls, mock_project):
        with tempfile.TemporaryDirectory() as tmp_dir:
            shp_path = os.path.join(tmp_dir, "districts.shp")
            cpg_path = os.path.join(tmp_dir, "districts.cpg")
            open(shp_path, "w").close()
            open(cpg_path, "w").close()
            fake_layer = MagicMock()
            fake_layer.isValid.return_value = True
            fake_layer.name.return_value = "districts"
            mock_layer_cls.return_value = fake_layer

            res = add_layer_from_path(shp_path)

            self.assertTrue(res["success"], res)
            self.assertNotIn("encoding_note", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayer", create=True)
    def test_non_shapefile_vector_is_unaffected(self, mock_layer_cls, mock_project):
        with tempfile.TemporaryDirectory() as tmp_dir:
            geojson_path = os.path.join(tmp_dir, "districts.geojson")
            open(geojson_path, "w").close()
            fake_layer = MagicMock()
            fake_layer.isValid.return_value = True
            fake_layer.name.return_value = "districts"
            mock_layer_cls.return_value = fake_layer

            res = add_layer_from_path(geojson_path)

            self.assertTrue(res["success"], res)
            self.assertNotIn("encoding_note", res)
            fake_layer.dataProvider.return_value.setEncoding.assert_not_called()


class TestAddLayerFromPathSpatialiteIndex(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayer", create=True)
    def test_sqlite_file_triggers_spatial_index_check(self, mock_layer_cls, mock_project):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sqlite_path = os.path.join(tmp_dir, "districts.sqlite")
            open(sqlite_path, "w").close()
            fake_layer = MagicMock()
            fake_layer.isValid.return_value = True
            fake_layer.name.return_value = "districts"
            fake_layer.dataProvider.return_value.createSpatialIndex.return_value = True
            mock_layer_cls.return_value = fake_layer

            res = add_layer_from_path(sqlite_path)

            self.assertTrue(res["success"], res)
            self.assertNotIn("spatial_index_note", res)
            fake_layer.dataProvider.return_value.createSpatialIndex.assert_called_once()

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayer", create=True)
    def test_sqlite_index_creation_failure_is_reported(self, mock_layer_cls, mock_project):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sqlite_path = os.path.join(tmp_dir, "districts.sqlite")
            open(sqlite_path, "w").close()
            fake_layer = MagicMock()
            fake_layer.isValid.return_value = True
            fake_layer.name.return_value = "districts"
            fake_layer.dataProvider.return_value.createSpatialIndex.return_value = False
            mock_layer_cls.return_value = fake_layer

            res = add_layer_from_path(sqlite_path)

            self.assertTrue(res["success"], res)
            self.assertIn("spatial_index_note", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayer", create=True)
    def test_non_spatialite_file_skips_index_check(self, mock_layer_cls, mock_project):
        with tempfile.TemporaryDirectory() as tmp_dir:
            geojson_path = os.path.join(tmp_dir, "districts.geojson")
            open(geojson_path, "w").close()
            fake_layer = MagicMock()
            fake_layer.isValid.return_value = True
            fake_layer.name.return_value = "districts"
            mock_layer_cls.return_value = fake_layer

            res = add_layer_from_path(geojson_path)

            self.assertTrue(res["success"], res)
            self.assertNotIn("spatial_index_note", res)
            fake_layer.dataProvider.return_value.createSpatialIndex.assert_not_called()


class TestAddLayerFromPathDownloadDiagnostics(unittest.TestCase):
    """Reported live 2026-09-24 (QGIS 4.2.2): a URL load failed with only
    "Invalid layer: C:\\...\\Temp\\tmp_2kgn_72.geojson". The error named the temp
    copy instead of the URL and gave no reason."""

    def _write(self, tmp_dir, data, name="tmp_2kgn_72.geojson"):
        path = os.path.join(tmp_dir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_classifies_common_wrong_content(self):
        cases = [
            (b"", "empty"),
            (b"PK\x03\x04rest-of-zip", "zip archive"),
            (b"\n<!DOCTYPE html><html><body>GitHub</body></html>", "HTML web page"),
            (b'<?xml version="1.0"?><ServiceExceptionReport/>', "XML"),
            (b'{"message": "Not Found", "documentation_url": "x"}', "documentation_url, message"),
            (b'{"type": "FeatureCollection", "features": []}', "no features"),
            (b'[{"a": 1}]', "JSON array"),
            (b'{"type": "FeatureCollection", "feat', "not valid JSON"),
        ]
        from cartogen_ai.core.agent.tools.vector_tools import _describe_unreadable_download
        with tempfile.TemporaryDirectory() as tmp_dir:
            for data, expected in cases:
                with self.subTest(expected=expected):
                    reason = _describe_unreadable_download(self._write(tmp_dir, data))
                    self.assertIsNotNone(reason)
                    self.assertIn(expected, reason)

    def test_real_geojson_and_unknown_binary_give_no_guess(self):
        from cartogen_ai.core.agent.tools.vector_tools import _describe_unreadable_download
        with tempfile.TemporaryDirectory() as tmp_dir:
            fc = b'{"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": null, "properties": {}}]}'
            self.assertIsNone(_describe_unreadable_download(self._write(tmp_dir, fc)))
            self.assertIsNone(_describe_unreadable_download(self._write(tmp_dir, b"\x00\x01binary")))

    def test_json_key_listing_never_includes_values(self):
        from cartogen_ai.core.agent.tools.vector_tools import _describe_unreadable_download
        with tempfile.TemporaryDirectory() as tmp_dir:
            reason = _describe_unreadable_download(
                self._write(tmp_dir, b'{"error": "secret-token-abc123"}'))
            self.assertIn("error", reason)
            self.assertNotIn("secret-token-abc123", reason)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayer", create=True)
    def test_invalid_downloaded_layer_reports_url_and_reason(self, mock_layer_cls, mock_project):
        url = "https://github.com/org/repo/blob/main/districts.geojson"
        with tempfile.TemporaryDirectory() as tmp_dir:
            local = self._write(tmp_dir, b"<!DOCTYPE html><html></html>")
            mock_layer_cls.return_value.isValid.return_value = False

            res = add_layer_from_path(local, source_label=url)

            self.assertIn(url, res["error"])
            self.assertNotIn("tmp_2kgn_72", res["error"])
            self.assertIn("raw.githubusercontent.com", res["error"])
            mock_project.instance.return_value.addMapLayer.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayer", create=True)
    def test_downloaded_layer_default_name_comes_from_url(self, mock_layer_cls, mock_project):
        with tempfile.TemporaryDirectory() as tmp_dir:
            local = self._write(tmp_dir, b"{}")
            mock_layer_cls.return_value.isValid.return_value = True

            add_layer_from_path(local, source_label="https://example.org/data/districts.geojson?x=1")

            self.assertEqual(mock_layer_cls.call_args[0][0], local)
            self.assertEqual(mock_layer_cls.call_args[0][1], "districts")

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayer", create=True)
    def test_invalid_local_file_error_is_unchanged(self, mock_layer_cls, mock_project):
        # Local files get no download diagnosis: the user's own file on disk is not a
        # "wrong content served by a URL" case, and the old message stays as-is.
        with tempfile.TemporaryDirectory() as tmp_dir:
            local = self._write(tmp_dir, b"<html></html>", name="mine.geojson")
            mock_layer_cls.return_value.isValid.return_value = False

            res = add_layer_from_path(local)

            self.assertEqual(res["error"], f"Invalid layer: {local}")


if __name__ == "__main__":
    unittest.main()


class TestDiagnoseTopologyExtended(unittest.TestCase):
    """Point 4 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md:
    diagnose_topology used to only check single-geometry validity and
    exact-zero-area slivers. Extended (2026-09-04, same session that built
    point 2's QA gate) to also report exact-duplicate geometries, and, for
    polygon layers, real area-sharing overlaps (QgsGeometry.overlaps, not
    mere touching) and an optional min_area small-polygon threshold. Does
    NOT add a gap check -- see the tool's own updated description for why
    that's a deliberate, documented gap rather than an oversight.

    This function had zero prior test coverage (confirmed via grep across
    tests/ before this change) despite already being relied on by point 2's
    QA gate -- these tests are its first, not a regression suite for an
    existing one."""

    @staticmethod
    def _make_feature(fid, wkt="POLYGON((0 0,1 0,1 1,0 1,0 0))", area=1.0,
                       is_valid=True, is_empty=False, geom_type=2, bbox="bbox"):
        geom = MagicMock()
        geom.isEmpty.return_value = is_empty
        geom.isGeomValid.return_value = is_valid
        geom.type.return_value = geom_type
        geom.area.return_value = area
        geom.asWkt.return_value = wkt
        geom.boundingBox.return_value = bbox
        geom.overlaps.return_value = False
        feature = MagicMock()
        feature.id.return_value = fid
        feature.geometry.return_value = geom
        return feature, geom

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_reports_invalid_and_zero_area_as_before(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        mock_wkb.geometryType.return_value = "not-polygon-sentinel"
        f1, _ = self._make_feature(1, wkt="A", is_valid=False, area=1.0)
        f2, _ = self._make_feature(2, wkt="B", is_valid=True, area=0.0)
        layer = MagicMock()
        layer.featureCount.return_value = 2
        layer.getFeatures.return_value = [f1, f2]
        mock_find.return_value = layer

        result = diagnose_topology("layer")

        self.assertTrue(result["success"])
        self.assertEqual(result["invalid_geometries"], 1)
        self.assertEqual(result["zero_area_slivers"], 1)
        self.assertNotIn("overlapping_feature_pairs", result)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_duplicate_geometries_counted_beyond_the_first(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        mock_wkb.geometryType.return_value = "not-polygon-sentinel"
        same_wkt = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        f1, _ = self._make_feature(1, wkt=same_wkt)
        f2, _ = self._make_feature(2, wkt=same_wkt)
        f3, _ = self._make_feature(3, wkt=same_wkt)
        f4, _ = self._make_feature(4, wkt="DIFFERENT")
        layer = MagicMock()
        layer.featureCount.return_value = 4
        layer.getFeatures.return_value = [f1, f2, f3, f4]
        mock_find.return_value = layer

        result = diagnose_topology("layer")

        # 3 identical features -> 2 duplicates beyond the first; the 4th,
        # distinct feature contributes nothing.
        self.assertEqual(result["duplicate_geometries"], 2)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsSpatialIndex", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_overlapping_polygons_detected_via_spatial_index_and_overlaps(self, mock_find, mock_wkb, mock_index_cls):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        mock_wkb.geometryType.return_value = "polygon-sentinel"
        f1, g1 = self._make_feature(1, wkt="A")
        f2, g2 = self._make_feature(2, wkt="B")
        g1.overlaps.return_value = True
        g2.overlaps.return_value = True
        layer = MagicMock()
        layer.featureCount.return_value = 2
        layer.getFeatures.return_value = [f1, f2]
        layer.wkbType.return_value = "polygon-sentinel"
        mock_find.return_value = layer
        mock_index_cls.return_value.intersects.return_value = [1, 2]

        result = diagnose_topology("layer")

        self.assertEqual(result["overlapping_feature_pairs"], 1)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsSpatialIndex", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_adjacent_non_overlapping_polygons_report_zero(self, mock_find, mock_wkb, mock_index_cls):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        mock_wkb.geometryType.return_value = "polygon-sentinel"
        f1, g1 = self._make_feature(1, wkt="A")
        f2, g2 = self._make_feature(2, wkt="B")
        g1.overlaps.return_value = False
        g2.overlaps.return_value = False
        layer = MagicMock()
        layer.featureCount.return_value = 2
        layer.getFeatures.return_value = [f1, f2]
        layer.wkbType.return_value = "polygon-sentinel"
        mock_find.return_value = layer
        # Bounding boxes touch (candidates found via the index) but the
        # actual geometries don't truly overlap -- e.g. two adjacent admin
        # polygons sharing a border.
        mock_index_cls.return_value.intersects.return_value = [1, 2]

        result = diagnose_topology("layer")

        self.assertEqual(result["overlapping_feature_pairs"], 0)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_non_polygon_layer_omits_overlap_key_entirely(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        mock_wkb.geometryType.return_value = "point-sentinel"
        f1, _ = self._make_feature(1, wkt="A", geom_type=0)
        layer = MagicMock()
        layer.featureCount.return_value = 1
        layer.getFeatures.return_value = [f1]
        mock_find.return_value = layer

        result = diagnose_topology("layer")

        self.assertNotIn("overlapping_feature_pairs", result)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_min_area_flags_small_but_nonzero_polygons(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        mock_wkb.geometryType.return_value = "not-polygon-sentinel"
        f1, _ = self._make_feature(1, wkt="A", area=0.5)
        f2, _ = self._make_feature(2, wkt="B", area=50.0)
        layer = MagicMock()
        layer.featureCount.return_value = 2
        layer.getFeatures.return_value = [f1, f2]
        mock_find.return_value = layer

        result = diagnose_topology("layer", min_area=1.0)

        self.assertEqual(result["small_polygons"], 1)
        self.assertEqual(result["zero_area_slivers"], 0)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_min_area_key_absent_when_not_requested(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        mock_wkb.geometryType.return_value = "not-polygon-sentinel"
        f1, _ = self._make_feature(1, wkt="A", area=0.5)
        layer = MagicMock()
        layer.featureCount.return_value = 1
        layer.getFeatures.return_value = [f1]
        mock_find.return_value = layer

        result = diagnose_topology("layer")

        self.assertNotIn("small_polygons", result)

    def test_degrades_gracefully_outside_qgis(self):
        result = diagnose_topology("layer")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])


class TestRunAndAddZeroResultWarning(unittest.TestCase):
    """Point 22 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md:
    _run_and_add is the shared helper behind ~18 vector tools (intersect,
    union, spatial_join, buffer, dissolve, clip, etc.) -- a spatial op that
    runs without error but produces an empty output previously looked
    identical to a real result. These are the first direct tests of this
    function (previously zero coverage, same gap point 4's diagnose_topology
    extension found in that function before its own fix)."""

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.processing", create=True)
    def test_zero_features_adds_warning_and_count(self, mock_processing, mock_project):
        output_layer = MagicMock()
        output_layer.featureCount.return_value = 0
        mock_processing.run.return_value = {"OUTPUT": output_layer}

        res = _run_and_add("native:intersection", {}, "result_layer")

        self.assertTrue(res["success"])
        self.assertEqual(res["feature_count"], 0)
        self.assertIn("warning", res)
        self.assertIn("0 features", res["warning"])
        mock_project.instance.return_value.addMapLayer.assert_called_once_with(output_layer)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.processing", create=True)
    def test_nonzero_features_reports_count_without_warning(self, mock_processing, mock_project):
        output_layer = MagicMock()
        output_layer.featureCount.return_value = 42
        mock_processing.run.return_value = {"OUTPUT": output_layer}

        res = _run_and_add("native:intersection", {}, "result_layer")

        self.assertTrue(res["success"])
        self.assertEqual(res["feature_count"], 42)
        self.assertNotIn("warning", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.processing", create=True)
    def test_output_without_feature_count_is_unaffected(self, mock_processing, mock_project):
        # e.g. a raster-producing algorithm run through the same helper.
        output_layer = MagicMock(spec=["setName"])
        mock_processing.run.return_value = {"OUTPUT": output_layer}

        res = _run_and_add("gdal:some_raster_alg", {}, "result_layer")

        self.assertTrue(res["success"])
        self.assertNotIn("feature_count", res)
        self.assertNotIn("warning", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools.processing", create=True)
    def test_processing_exception_still_reports_a_clean_error(self, mock_processing):
        mock_processing.run.side_effect = Exception("boom")
        res = _run_and_add("native:intersection", {}, "result_layer")
        self.assertIn("error", res)
        self.assertIn("boom", res["error"])


class TestBufferAnalysisCrsWarning(unittest.TestCase):
    """Point 3 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md,
    confirmed live against real QGIS 4.2.2: native:buffer's DISTANCE param
    is applied in the input layer's own CRS units with no conversion --
    buffering an EPSG:4326 (geographic) layer by 500 (meaning 500 meters)
    actually produces a buffer 500 *degrees* wide, not ~1km."""

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_geographic_crs_gets_a_warning(self, mock_find, mock_processing, mock_project):
        layer = MagicMock()
        layer.crs.return_value.isGeographic.return_value = True
        layer.crs.return_value.authid.return_value = "EPSG:4326"
        mock_find.return_value = layer
        output_layer = MagicMock()
        mock_processing.run.return_value = {"OUTPUT": output_layer}

        res = buffer_analysis("wgs84_points", 500)

        self.assertTrue(res["success"])
        self.assertIn("warning", res)
        self.assertIn("EPSG:4326", res["warning"])
        self.assertIn("DEGREES", res["warning"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_projected_crs_gets_no_warning(self, mock_find, mock_processing, mock_project):
        layer = MagicMock()
        layer.crs.return_value.isGeographic.return_value = False
        mock_find.return_value = layer
        output_layer = MagicMock()
        mock_processing.run.return_value = {"OUTPUT": output_layer}

        res = buffer_analysis("utm_points", 500)

        self.assertTrue(res["success"])
        self.assertNotIn("warning", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_reports_missing_layer(self, mock_find):
        mock_find.return_value = None
        res = buffer_analysis("ghost_layer", 500)
        self.assertIn("error", res)
        self.assertIn("ghost_layer", res["error"])

    def test_degrades_gracefully_outside_qgis(self):
        res = buffer_analysis("layer", 500)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestBufferAnalysisOnlySelected(unittest.TestCase):
    """only_selected added 2026-09-24: a live report ("buffer 5 km around active GDACS
    alerts X,Y") had no way to scope buffer_analysis to specific features -- it always
    buffered the whole layer regardless of any selection, the same silent-wrong-scope
    risk export_tools.py's _write_vector already guards against for only_selected."""

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_only_selected_with_nothing_selected_is_a_clean_error(self, mock_find):
        layer = MagicMock()
        layer.selectedFeatureCount.return_value = 0
        mock_find.return_value = layer

        res = buffer_analysis("alerts", 5000, only_selected=True)

        self.assertIn("error", res)
        self.assertIn("no features", res["error"])
        self.assertIn("currently selected", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProcessingFeatureSourceDefinition", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_only_selected_wraps_input_with_selected_features_only(
        self, mock_find, mock_processing, mock_source_def, mock_project
    ):
        layer = MagicMock()
        layer.selectedFeatureCount.return_value = 2
        layer.crs.return_value.isGeographic.return_value = False
        layer.id.return_value = "alerts_layer_id"
        mock_find.return_value = layer
        mock_processing.run.return_value = {"OUTPUT": MagicMock()}
        mock_source_def.return_value = "wrapped-selected-only-source"

        res = buffer_analysis("alerts", 5000, only_selected=True)

        self.assertTrue(res["success"], res)
        self.assertTrue(res["only_selected_features"])
        self.assertEqual(res["input_feature_count"], 2)
        mock_source_def.assert_called_once_with("alerts_layer_id", selectedFeaturesOnly=True)
        self.assertEqual(mock_processing.run.call_args[0][1]["INPUT"], "wrapped-selected-only-source")

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_default_still_buffers_the_whole_layer(self, mock_find, mock_processing, mock_project):
        # only_selected defaults to False -- existing callers that never pass it must be
        # completely unaffected by this change.
        layer = MagicMock()
        layer.crs.return_value.isGeographic.return_value = False
        layer.featureCount.return_value = 40
        mock_find.return_value = layer
        mock_processing.run.return_value = {"OUTPUT": MagicMock()}

        res = buffer_analysis("alerts", 5000)

        self.assertTrue(res["success"], res)
        self.assertFalse(res["only_selected_features"])
        self.assertEqual(res["input_feature_count"], 40)
        self.assertIs(mock_processing.run.call_args[0][1]["INPUT"], layer)
        layer.selectedFeatureCount.assert_not_called()


class TestRenameAndToggleVisibility(unittest.TestCase):
    """rename_layer/toggle_visibility: no test coverage at all before QUAL-006
    (2026-09-14 audit)."""

    def test_rename_degrades_outside_qgis(self):
        res = rename_layer("old", "new")
        self.assertIn("error", res)

    def test_toggle_degrades_outside_qgis(self):
        res = toggle_visibility("layer")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name", return_value=None)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_rename_reports_missing_layer(self, mock_find):
        res = rename_layer("ghost", "new_name")
        self.assertIn("error", res)
        self.assertIn("ghost", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_rename_calls_setname_and_reports_success(self, mock_find):
        layer = MagicMock()
        mock_find.return_value = layer

        res = rename_layer("old_name", "new_name")

        self.assertTrue(res["success"])
        layer.setName.assert_called_once_with("new_name")

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name", return_value=None)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_toggle_reports_missing_layer(self, mock_find):
        res = toggle_visibility("ghost")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_toggle_reports_missing_tree_node(self, mock_find, mock_project):
        mock_find.return_value = MagicMock()
        mock_project.instance.return_value.layerTreeRoot.return_value.findLayer.return_value = None
        res = toggle_visibility("layer")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_toggle_sets_visibility_checked_state(self, mock_find, mock_project):
        layer = MagicMock()
        layer.id.return_value = "layer123"
        mock_find.return_value = layer
        node = mock_project.instance.return_value.layerTreeRoot.return_value.findLayer.return_value

        res = toggle_visibility("layer", visible=False)

        self.assertTrue(res["success"])
        node.setItemVisibilityChecked.assert_called_once_with(False)


class TestIntersectAndUnionLayers(unittest.TestCase):
    """intersect_layers/union_layers: no test coverage at all before QUAL-006 (2026-09-14
    audit)."""

    def test_intersect_degrades_outside_qgis(self):
        res = intersect_layers("a", "b")
        self.assertIn("error", res)

    def test_union_degrades_outside_qgis(self):
        res = union_layers("a", "b")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_intersect_reports_missing_second_layer(self, mock_find):
        mock_find.side_effect = lambda name: MagicMock() if name == "a" else None
        res = intersect_layers("a", "b")
        self.assertIn("error", res)
        self.assertIn("b", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools._run_and_add")
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_intersect_calls_native_intersection_with_both_layers(self, mock_find, mock_run):
        a, b = MagicMock(), MagicMock()
        mock_find.side_effect = lambda name: {"a": a, "b": b}[name]
        mock_run.return_value = {"success": True, "layer_name": "a_intersect_b"}

        res = intersect_layers("a", "b")

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "native:intersection")
        self.assertIs(params["INPUT"], a)
        self.assertIs(params["OVERLAY"], b)
        self.assertEqual(new_name, "a_intersect_b")

    @patch("cartogen_ai.core.agent.tools.vector_tools._run_and_add")
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_intersect_attaches_crs_mismatch_warning(self, mock_find, mock_run):
        a, b = MagicMock(), MagicMock()
        a.crs.return_value.authid.return_value = "EPSG:4326"
        a.crs.return_value.__eq__ = lambda self, other: False
        b.crs.return_value.authid.return_value = "EPSG:3857"
        mock_find.side_effect = lambda name: {"a": a, "b": b}[name]
        mock_run.return_value = {"success": True, "layer_name": "a_intersect_b"}

        res = intersect_layers("a", "b")

        self.assertIn("crs_warning", res)
        self.assertIn("CRS mismatch", res["crs_warning"])

    @patch("cartogen_ai.core.agent.tools.vector_tools._run_and_add")
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_union_calls_native_union_with_both_layers(self, mock_find, mock_run):
        a, b = MagicMock(), MagicMock()
        mock_find.side_effect = lambda name: {"a": a, "b": b}[name]
        mock_run.return_value = {"success": True, "layer_name": "a_union_b"}

        res = union_layers("a", "b")

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "native:union")
        self.assertIs(params["INPUT"], a)
        self.assertIs(params["OVERLAY"], b)


class TestDissolveAndMergeLayers(unittest.TestCase):
    """dissolve_layer/merge_layers: no test coverage at all before QUAL-006 (2026-09-14
    audit)."""

    def test_dissolve_degrades_outside_qgis(self):
        res = dissolve_layer("layer")
        self.assertIn("error", res)

    def test_merge_degrades_outside_qgis(self):
        res = merge_layers(["a", "b"])
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools._run_and_add")
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_dissolve_without_field_passes_empty_field_list(self, mock_find, mock_run):
        layer = MagicMock()
        mock_find.return_value = layer
        mock_run.return_value = {"success": True, "layer_name": "layer_dissolved"}

        res = dissolve_layer("layer")

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "native:dissolve")
        self.assertEqual(params["FIELD"], [])
        self.assertIs(params["INPUT"], layer)

    @patch("cartogen_ai.core.agent.tools.vector_tools._run_and_add")
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_dissolve_with_field_wraps_it_in_a_list(self, mock_find, mock_run):
        mock_find.return_value = MagicMock()
        mock_run.return_value = {"success": True, "layer_name": "layer_dissolved"}

        dissolve_layer("layer", field="district")

        _, params, _ = mock_run.call_args[0]
        self.assertEqual(params["FIELD"], ["district"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_merge_rejects_fewer_than_two_layers(self):
        res = merge_layers(["only_one"])
        self.assertIn("error", res)
        self.assertIn("at least 2", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_merge_reports_first_missing_layer(self, mock_find):
        mock_find.side_effect = lambda name: MagicMock() if name == "a" else None
        res = merge_layers(["a", "b"])
        self.assertIn("error", res)
        self.assertIn("b", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools._run_and_add")
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_merge_passes_every_resolved_layer(self, mock_find, mock_run):
        a, b, c = MagicMock(), MagicMock(), MagicMock()
        mock_find.side_effect = lambda name: {"a": a, "b": b, "c": c}[name]
        mock_run.return_value = {"success": True, "layer_name": "merged"}

        res = merge_layers(["a", "b", "c"])

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "native:mergevectorlayers")
        self.assertEqual(params["LAYERS"], [a, b, c])


class TestReprojectAndFixGeometries(unittest.TestCase):
    """reproject_layer/fix_geometries: no test coverage at all before QUAL-006 (2026-09-14
    audit)."""

    def test_reproject_degrades_outside_qgis(self):
        res = reproject_layer("layer", "EPSG:4326")
        self.assertIn("error", res)

    def test_fix_geometries_degrades_outside_qgis(self):
        res = fix_geometries("layer")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsCoordinateReferenceSystem", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_reproject_rejects_invalid_crs_code(self, mock_find, mock_crs_cls):
        mock_find.return_value = MagicMock()
        mock_crs_cls.return_value.isValid.return_value = False

        res = reproject_layer("layer", "not-a-real-crs")

        self.assertIn("error", res)
        self.assertIn("not-a-real-crs", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools._run_and_add")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsCoordinateReferenceSystem", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_reproject_calls_native_reprojectlayer_with_target_crs(self, mock_find, mock_crs_cls, mock_run):
        layer = MagicMock()
        mock_find.return_value = layer
        target_crs = mock_crs_cls.return_value
        target_crs.isValid.return_value = True
        mock_run.return_value = {"success": True, "layer_name": "layer_EPSG_3857"}

        res = reproject_layer("layer", "EPSG:3857")

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "native:reprojectlayer")
        self.assertIs(params["INPUT"], layer)
        self.assertIs(params["TARGET_CRS"], target_crs)
        self.assertEqual(new_name, "layer_EPSG_3857")

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name", return_value=None)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_fix_geometries_reports_missing_layer(self, mock_find):
        res = fix_geometries("ghost")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools._run_and_add")
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_fix_geometries_calls_native_fixgeometries(self, mock_find, mock_run):
        layer = MagicMock()
        mock_find.return_value = layer
        mock_run.return_value = {"success": True, "layer_name": "layer_fixed"}

        res = fix_geometries("layer")

        self.assertTrue(res["success"])
        alg, params, new_name = mock_run.call_args[0]
        self.assertEqual(alg, "native:fixgeometries")
        self.assertIs(params["INPUT"], layer)
        self.assertEqual(new_name, "layer_fixed")


class TestSelectByAttributeAndFeatureCount(unittest.TestCase):
    """select_by_attribute/get_feature_count/open_attribute_table: no test coverage at all
    before QUAL-006 (2026-09-14 audit)."""

    def test_select_by_attribute_degrades_outside_qgis(self):
        res = select_by_attribute("layer", "field", "value")
        self.assertIn("error", res)

    def test_get_feature_count_degrades_outside_qgis(self):
        res = get_feature_count("layer")
        self.assertIn("error", res)

    def test_open_attribute_table_degrades_outside_qgis(self):
        res = open_attribute_table("layer")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_select_by_attribute_reports_unknown_field(self, mock_find):
        layer = MagicMock()
        layer.fields.return_value = []
        mock_find.return_value = layer
        res = select_by_attribute("layer", "not_a_field", "value")
        self.assertIn("error", res)
        self.assertIn("not_a_field", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_select_by_attribute_builds_a_quoted_expression_and_selects(self, mock_find, mock_expr_cls):
        mock_expr_cls.quotedColumnRef.side_effect = lambda f: f'"{f}"'
        mock_expr_cls.quotedValue.side_effect = lambda v: f"'{v}'"
        field_mock = MagicMock()
        field_mock.name.return_value = "district"
        layer = MagicMock()
        layer.fields.return_value = [field_mock]
        layer.selectedFeatureCount.return_value = 3
        mock_find.return_value = layer

        res = select_by_attribute("layer", "district", "Zaatari")

        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 3)
        self.assertIn("district", res["expression"])
        self.assertIn("Zaatari", res["expression"])
        layer.selectByExpression.assert_called_once()

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name", return_value=None)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_get_feature_count_reports_missing_layer(self, mock_find):
        res = get_feature_count("ghost")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_get_feature_count_returns_the_real_count(self, mock_find):
        layer = MagicMock()
        layer.featureCount.return_value = 137
        mock_find.return_value = layer

        res = get_feature_count("layer")

        self.assertEqual(res["feature_count"], 137)
        self.assertEqual(res["layer_name"], "layer")

    @patch("cartogen_ai.core.agent.tools.vector_tools.iface", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_open_attribute_table_reports_missing_iface(self, mock_iface):
        with patch("cartogen_ai.core.agent.tools.vector_tools.iface", None):
            res = open_attribute_table("layer")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools.iface", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_open_attribute_table_calls_iface_showattributetable(self, mock_find, mock_iface):
        layer = MagicMock()
        mock_find.return_value = layer

        res = open_attribute_table("layer")

        self.assertTrue(res["success"])
        mock_iface.showAttributeTable.assert_called_once_with(layer)


class TestVerifyCrsCompatibility(unittest.TestCase):
    """verify_crs_compatibility: no test coverage at all before QUAL-006 (2026-09-14
    audit)."""

    def test_degrades_outside_qgis(self):
        res = verify_crs_compatibility("a", "b")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_reports_missing_second_layer(self, mock_find):
        mock_find.side_effect = lambda name: MagicMock() if name == "a" else None
        res = verify_crs_compatibility("a", "b")
        self.assertIn("error", res)
        self.assertIn("b", res["error"])

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_matching_crs_reports_compatible_with_no_warning(self, mock_find):
        shared_crs = MagicMock()
        shared_crs.authid.return_value = "EPSG:4326"
        a, b = MagicMock(), MagicMock()
        a.crs.return_value = shared_crs
        b.crs.return_value = shared_crs
        mock_find.side_effect = lambda name: {"a": a, "b": b}[name]

        res = verify_crs_compatibility("a", "b")

        self.assertTrue(res["success"])
        self.assertTrue(res["compatible"])
        self.assertEqual(res["warning"], "")

    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    def test_mismatched_crs_reports_incompatible_with_warning(self, mock_find):
        crs_a, crs_b = MagicMock(), MagicMock()
        crs_a.authid.return_value = "EPSG:4326"
        crs_b.authid.return_value = "EPSG:3857"
        crs_a.__eq__ = lambda self, other: False
        a, b = MagicMock(), MagicMock()
        a.crs.return_value = crs_a
        b.crs.return_value = crs_b
        mock_find.side_effect = lambda name: {"a": a, "b": b}[name]

        res = verify_crs_compatibility("a", "b")

        self.assertTrue(res["success"])
        self.assertFalse(res["compatible"])
        self.assertIn("CRS mismatch", res["warning"])
        self.assertIn("EPSG:4326", res["warning"])
        self.assertIn("EPSG:3857", res["warning"])
