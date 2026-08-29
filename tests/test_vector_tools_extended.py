# -*- coding: utf-8 -*-
"""Tests for the geoprocessing/selection tools added to vector_tools.py in the
QGIS-feature-coverage pass (difference, convex hull/Voronoi/Delaunay, nearest-
feature join, singlepart/simplify, field statistics, select-by-location).
Follows the same QGIS_AVAILABLE=False degrade-path convention used
throughout tests/test_new_tools.py and tests/test_styling_tools.py."""
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.tools.vector_tools import (
    difference_layers, convex_hull, voronoi_polygons, delaunay_triangulation,
    find_nearest_features, convert_to_singlepart, simplify_geometry,
    field_statistics, select_by_location, invert_selection,
    _compute_field_statistics, zoom_to_layer, zoom_to_feature, _extent_to_canvas_crs,
    apply_labels,
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
    def test_transform_failure_falls_back_to_original_extent(self, mock_transform_cls, mock_project):
        source_crs = MagicMock()
        source_crs.isValid.return_value = True
        canvas = self._fake_canvas(MagicMock())
        extent = object()
        mock_transform_cls.side_effect = Exception("boom")

        result = _extent_to_canvas_crs(canvas, extent, source_crs)

        self.assertIs(result, extent)


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

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsPalLayerSettings", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsTextFormat", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsVectorLayerSimpleLabeling", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_valid_expression_sets_is_expression_true(self, mock_find, mock_expr_cls, mock_labeling_cls, mock_fmt_cls, mock_settings_cls):
        fake_layer = MagicMock()
        mock_find.return_value = fake_layer
        mock_expr_cls.return_value.hasParserError.return_value = False
        settings_instance = mock_settings_cls.return_value

        res = apply_labels("layer", expression="a || b")

        self.assertTrue(res.get("success"), res)
        self.assertEqual(settings_instance.fieldName, "a || b")
        self.assertTrue(settings_instance.isExpression)
        fake_layer.setLabelsEnabled.assert_called_once_with(True)

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


if __name__ == "__main__":
    unittest.main()
