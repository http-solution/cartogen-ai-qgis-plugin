# -*- coding: utf-8 -*-
"""v1.8.0 workstream 1: recommend_visualization_method -- an advisory tool
that recommends a styling tool from a layer/field's real geometry/field
type/cardinality/distribution. Never applies styling itself."""
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.tools.cartographic_advisory_tools import (
    _looks_like_rate_or_percentage, _looks_like_raw_count, _recommend_for_geometry,
    recommend_visualization_method,
)


class TestLooksLikeRateOrPercentage(unittest.TestCase):
    def test_name_hint_matches(self):
        self.assertTrue(_looks_like_rate_or_percentage("access_rate", [50, 60]))
        self.assertTrue(_looks_like_rate_or_percentage("coverage_pct", [50, 60]))
        self.assertTrue(_looks_like_rate_or_percentage("severity_index", [1, 2, 3]))

    def test_value_range_0_to_1_matches(self):
        self.assertTrue(_looks_like_rate_or_percentage("unnamed_field", [0.1, 0.5, 0.9]))

    def test_fractional_0_to_100_matches(self):
        self.assertTrue(_looks_like_rate_or_percentage("unnamed_field", [12.5, 60.25, 99.9]))

    def test_pure_integer_0_to_100_does_not_match_on_value_alone(self):
        # Ambiguous with a small raw count -- left to the count-hint check,
        # not guessed here.
        self.assertFalse(_looks_like_rate_or_percentage("unnamed_field", [10, 20, 30]))

    def test_large_raw_counts_do_not_match(self):
        self.assertFalse(_looks_like_rate_or_percentage("total_cases", [500, 12000, 45000]))

    def test_empty_values_does_not_crash(self):
        self.assertFalse(_looks_like_rate_or_percentage("field", []))


class TestLooksLikeRawCount(unittest.TestCase):
    def test_name_hint_matches(self):
        self.assertTrue(_looks_like_raw_count("total_affected", [10, 20]))
        self.assertTrue(_looks_like_raw_count("population_2025", [10, 20]))
        self.assertTrue(_looks_like_raw_count("num_incidents", [10, 20]))

    def test_large_whole_numbers_match_without_a_name_hint(self):
        self.assertTrue(_looks_like_raw_count("unnamed_field", [500, 12000, 45000]))

    def test_small_or_fractional_values_do_not_match(self):
        self.assertFalse(_looks_like_raw_count("unnamed_field", [1, 2, 3]))
        self.assertFalse(_looks_like_raw_count("unnamed_field", [12.5, 60.25]))

    def test_empty_values_does_not_crash(self):
        self.assertFalse(_looks_like_raw_count("field", []))


class TestRecommendForGeometry(unittest.TestCase):
    """Pure decision logic -- no QGIS import, mirrors the external standard's
    decision matrix adapted to this codebase's real tool names."""

    def test_raster_recommends_stretch(self):
        res = _recommend_for_geometry("raster", False, False, None, False, False, None)
        self.assertEqual(res["recommended_tool"], "apply_raster_stretch")

    def test_no_field_point_many_features_recommends_hotspot(self):
        res = _recommend_for_geometry("point", False, False, None, False, False, 500)
        self.assertEqual(res["recommended_tool"], "hotspot_analysis")

    def test_no_field_point_few_features_recommends_nothing(self):
        res = _recommend_for_geometry("point", False, False, None, False, False, 5)
        self.assertIsNone(res["recommended_tool"])

    def test_no_field_polygon_recommends_nothing(self):
        res = _recommend_for_geometry("polygon", False, False, None, False, False, None)
        self.assertIsNone(res["recommended_tool"])

    def test_nominal_field_line_low_cardinality_recommends_rule_based(self):
        res = _recommend_for_geometry("line", True, False, 3, False, False, None)
        self.assertEqual(res["recommended_tool"], "apply_rule_based_style")

    def test_nominal_field_line_high_cardinality_recommends_categorized(self):
        res = _recommend_for_geometry("line", True, False, 20, False, False, None)
        self.assertEqual(res["recommended_tool"], "apply_categorized_style")
        self.assertTrue(any("distinct category values" in w for w in res["warnings"]))

    def test_nominal_field_polygon_recommends_categorized(self):
        res = _recommend_for_geometry("polygon", True, False, 5, False, False, None)
        self.assertEqual(res["recommended_tool"], "apply_categorized_style")

    def test_nominal_field_point_recommends_categorized(self):
        res = _recommend_for_geometry("point", True, False, 4, False, False, None)
        self.assertEqual(res["recommended_tool"], "apply_categorized_style")

    def test_numeric_raw_count_on_polygon_warns_and_still_recommends_graduated(self):
        res = _recommend_for_geometry("polygon", True, True, None, False, True, None)
        self.assertEqual(res["recommended_tool"], "apply_graduated_style")
        self.assertTrue(any("raw count" in w for w in res["warnings"]))

    def test_numeric_rate_on_polygon_recommends_graduated_no_warning(self):
        res = _recommend_for_geometry("polygon", True, True, None, True, False, None)
        self.assertEqual(res["recommended_tool"], "apply_graduated_style")
        self.assertEqual(res["warnings"], [])

    def test_numeric_point_recommends_graduated_symbol(self):
        res = _recommend_for_geometry("point", True, True, None, False, False, None)
        self.assertEqual(res["recommended_tool"], "apply_graduated_symbol_style")

    def test_numeric_line_recommends_graduated_style(self):
        res = _recommend_for_geometry("line", True, True, None, False, False, None)
        self.assertEqual(res["recommended_tool"], "apply_graduated_style")

    def test_unknown_geometry_recommends_nothing_with_rationale(self):
        res = _recommend_for_geometry("unknown", True, True, None, False, False, None)
        self.assertIsNone(res["recommended_tool"])
        self.assertIn("geometry type", res["rationale"])

    def test_classification_hint_surfaced_in_suggested_params(self):
        classification = {"method": "jenks", "method_label": "Jenks Natural Breaks", "ramp": "Viridis", "skewness": 0.1}
        res = _recommend_for_geometry("polygon", True, True, None, False, False, None, classification)
        self.assertEqual(res["suggested_params"]["expected_classification_method"], "Jenks Natural Breaks")
        self.assertEqual(res["suggested_params"]["expected_color_ramp"], "Viridis")


class TestRecommendVisualizationMethodDegradesOutsideQgis(unittest.TestCase):
    def test_degrades_gracefully(self):
        res = recommend_visualization_method("layer")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestRecommendVisualizationMethodWiring(unittest.TestCase):
    """Confirms the QGIS-touching wrapper gathers real inputs and passes them
    through to _recommend_for_geometry correctly -- not re-testing the
    decision logic itself (covered above)."""

    def _make_layer(self, field_name, values, geometry_kind="polygon"):
        field_mock = MagicMock()
        field_mock.name.return_value = field_name
        layer = MagicMock()
        layer.fields.return_value = [field_mock]
        feats = []
        for v in values:
            feat = MagicMock()
            feat.__getitem__.side_effect = lambda key, v=v: v
            feats.append(feat)
        layer.getFeatures.return_value = feats
        return layer

    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._layer_geometry_kind")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._styling_tools")
    def test_reports_missing_layer(self, mock_st, mock_find, mock_geom):
        mock_st.QGIS_AVAILABLE = True
        mock_find.return_value = None
        res = recommend_visualization_method("layer")
        self.assertIn("error", res)
        self.assertIn("not found", res["error"])

    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._layer_geometry_kind")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._styling_tools")
    def test_reports_missing_field(self, mock_st, mock_find, mock_geom):
        mock_st.QGIS_AVAILABLE = True
        layer = self._make_layer("other_field", [1, 2, 3])
        mock_find.return_value = layer
        mock_geom.return_value = "polygon"
        res = recommend_visualization_method("layer", field="access_rate")
        self.assertIn("error", res)
        self.assertIn("Field 'access_rate'", res["error"])

    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._layer_geometry_kind")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._styling_tools")
    def test_real_rate_field_recommends_graduated_style(self, mock_st, mock_find, mock_geom):
        mock_st.QGIS_AVAILABLE = True
        layer = self._make_layer("access_rate", [10.5, 20.1, 30.9, 40.2, 50.7, 60.3])
        mock_find.return_value = layer
        mock_geom.return_value = "polygon"

        res = recommend_visualization_method("districts", field="access_rate")

        self.assertEqual(res["recommended_tool"], "apply_graduated_style")
        self.assertEqual(res["layer_name"], "districts")
        self.assertEqual(res["field"], "access_rate")
        self.assertEqual(res["geometry_kind"], "polygon")
        self.assertEqual(res["warnings"], [])

    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._layer_geometry_kind")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._styling_tools")
    def test_real_raw_count_field_on_polygon_warns(self, mock_st, mock_find, mock_geom):
        mock_st.QGIS_AVAILABLE = True
        layer = self._make_layer("total_affected", [500, 12000, 45000, 8000, 3000, 9000])
        mock_find.return_value = layer
        mock_geom.return_value = "polygon"

        res = recommend_visualization_method("districts", field="total_affected")

        self.assertEqual(res["recommended_tool"], "apply_graduated_style")
        self.assertTrue(any("raw count" in w for w in res["warnings"]))

    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._layer_geometry_kind")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._styling_tools")
    def test_nominal_field_wired_as_non_numeric_with_cardinality(self, mock_st, mock_find, mock_geom):
        mock_st.QGIS_AVAILABLE = True
        layer = self._make_layer("district_name", ["A", "B", "C", "A", "B"])
        mock_find.return_value = layer
        mock_geom.return_value = "polygon"

        res = recommend_visualization_method("districts", field="district_name")

        self.assertEqual(res["recommended_tool"], "apply_categorized_style")

    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._layer_geometry_kind")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._styling_tools")
    def test_no_field_uses_feature_count_for_point_layers(self, mock_st, mock_find, mock_geom):
        mock_st.QGIS_AVAILABLE = True
        layer = MagicMock()
        layer.featureCount.return_value = 5000
        mock_find.return_value = layer
        mock_geom.return_value = "point"

        res = recommend_visualization_method("incidents")

        self.assertEqual(res["recommended_tool"], "hotspot_analysis")

    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._layer_geometry_kind")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.cartographic_advisory_tools._styling_tools")
    def test_intended_message_passed_through_when_given(self, mock_st, mock_find, mock_geom):
        mock_st.QGIS_AVAILABLE = True
        layer = self._make_layer("access_rate", [10.5, 20.1, 30.9, 40.2, 50.7, 60.3])
        mock_find.return_value = layer
        mock_geom.return_value = "polygon"

        res = recommend_visualization_method("districts", field="access_rate", intended_message="show access gaps")

        self.assertEqual(res["intended_message"], "show access gaps")
