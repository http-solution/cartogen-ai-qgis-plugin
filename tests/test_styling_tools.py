# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.tools.styling_tools import (
    _classify_values, apply_graduated_style, apply_graduated_symbol_style,
    apply_categorized_style, _geometry_sort_key, _apply_opacity,
    _default_opacity_for_geometry, set_layer_transparency, auto_arrange_layer_order,
    set_layer_order, change_layer_color, hotspot_analysis, _match_cluster_color,
    save_layer_style, load_layer_style, _derive_style_path, apply_rule_based_style,
    apply_heatmap_style, _logarithmic_breaks, _resolve_classification_method,
)


class TestClassifyValues(unittest.TestCase):
    def test_low_cardinality_uses_equal_interval(self):
        result = _classify_values([1, 1, 2, 2, 3, 3, 1, 2, 3, 1])
        self.assertEqual(result["method"], "equal_interval")

    def test_highly_skewed_uses_jenks(self):
        result = _classify_values([1, 1, 1, 1, 1, 1, 1, 1, 1, 1000])
        self.assertEqual(result["method"], "jenks")
        self.assertIn("Skew", result["method_label"])

    def test_uniform_high_cardinality_uses_quantile(self):
        result = _classify_values(list(range(1, 21)))
        self.assertEqual(result["method"], "quantile")

    def test_explicit_mode_overrides_auto_detection(self):
        self.assertEqual(_classify_values([1, 2, 3, 4, 5, 6, 7, 8], mode="equal")["method"], "equal_interval")
        self.assertEqual(_classify_values([1, 2, 3, 4, 5, 6, 7, 8], mode="quantile")["method"], "quantile")

    def test_ramp_choice_tracks_skewness(self):
        low_skew = _classify_values(list(range(1, 21)))
        high_skew = _classify_values([1, 1, 1, 1, 1, 1, 1, 1, 1, 1000])
        self.assertEqual(low_skew["ramp"], "Viridis")
        self.assertEqual(high_skew["ramp"], "Cividis")

    def test_few_values_skips_skewness_analysis_without_crashing(self):
        result = _classify_values([1, 2])
        self.assertIn("method", result)

    def test_stddev_mode(self):
        result = _classify_values([1, 2, 3, 4, 5, 6, 7, 8], mode="stddev")
        self.assertEqual(result["method"], "stddev")
        self.assertEqual(result["method_label"], "Standard Deviation")

    def test_pretty_mode(self):
        result = _classify_values([1, 2, 3, 4, 5, 6, 7, 8], mode="pretty")
        self.assertEqual(result["method"], "pretty")
        self.assertEqual(result["method_label"], "Pretty Breaks")

    def test_logarithmic_mode_returns_breaks(self):
        result = _classify_values([1, 10, 100, 1000, 10000], mode="logarithmic", num_classes=5)
        self.assertEqual(result["method"], "logarithmic")
        self.assertNotIn("error", result)
        self.assertEqual(len(result["breaks"]), 4)
        # Interior breaks must be strictly increasing and inside the data range.
        self.assertEqual(result["breaks"], sorted(result["breaks"]))
        self.assertGreater(result["breaks"][0], 1)
        self.assertLess(result["breaks"][-1], 10000)

    def test_logarithmic_mode_with_non_positive_value_reports_error(self):
        result = _classify_values([-5, 1, 10, 100], mode="logarithmic")
        self.assertEqual(result["method"], "logarithmic")
        self.assertIn("error", result)
        self.assertNotIn("breaks", result)

    def test_logarithmic_mode_all_identical_values_reports_error(self):
        result = _classify_values([5, 5, 5], mode="logarithmic")
        self.assertIn("error", result)


class TestLogarithmicBreaks(unittest.TestCase):
    def test_evenly_spaced_in_log_space(self):
        breaks = _logarithmic_breaks([1, 10000], num_classes=4)
        # log10(1)=0, log10(10000)=4 -- 3 interior breaks at 1, 2, 3 in log space.
        self.assertEqual(len(breaks), 3)
        for b, expected_log in zip(breaks, [1, 2, 3]):
            self.assertAlmostEqual(b, 10 ** expected_log, places=6)

    def test_none_when_any_value_non_positive(self):
        self.assertIsNone(_logarithmic_breaks([0, 5, 10], num_classes=3))
        self.assertIsNone(_logarithmic_breaks([-1, 5, 10], num_classes=3))

    def test_none_when_all_values_identical(self):
        self.assertIsNone(_logarithmic_breaks([7, 7, 7], num_classes=3))

    def test_none_for_empty_values(self):
        self.assertIsNone(_logarithmic_breaks([], num_classes=3))


class TestResolveClassificationMethod(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsGraduatedSymbolRenderer", create=True)
    def test_stddev_and_pretty_resolve_to_distinct_enum_members(self, mock_renderer_cls):
        mock_renderer_cls.Mode.StdDev = "stddev-sentinel"
        mock_renderer_cls.Mode.Pretty = "pretty-sentinel"
        mock_renderer_cls.Mode.Jenks = "jenks-sentinel"
        self.assertEqual(_resolve_classification_method("stddev"), "stddev-sentinel")
        self.assertEqual(_resolve_classification_method("pretty"), "pretty-sentinel")

    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsGraduatedSymbolRenderer", create=True)
    def test_unknown_method_falls_back_to_jenks(self, mock_renderer_cls):
        mock_renderer_cls.Mode.Jenks = "jenks-sentinel"
        self.assertEqual(_resolve_classification_method("logarithmic"), "jenks-sentinel")


class TestMatchClusterColor(unittest.TestCase):
    """Pure Python, no QGIS needed -- the IASC cluster name/alias lookup
    powering apply_categorized_style's palette='humanitarian_cluster' and
    apply_graduated_style's cluster= parameters."""

    def test_exact_cluster_names_case_and_whitespace_insensitive(self):
        self.assertEqual(_match_cluster_color("Health"), "#DC2626")
        self.assertEqual(_match_cluster_color("  wash  "), "#38BDF8")
        self.assertEqual(_match_cluster_color("WASH"), "#38BDF8")
        self.assertEqual(_match_cluster_color("Food Security"), "#F59E0B")

    def test_common_aliases_resolve_to_the_same_color_as_the_canonical_name(self):
        self.assertEqual(_match_cluster_color("FSL"), _match_cluster_color("Food Security"))
        self.assertEqual(_match_cluster_color("Shelter"), _match_cluster_color("Emergency Shelter"))
        self.assertEqual(_match_cluster_color("CCCM"), _match_cluster_color("Camp Coordination and Camp Management"))
        self.assertEqual(_match_cluster_color("Water, Sanitation and Hygiene"), _match_cluster_color("WASH"))

    def test_unknown_value_returns_none(self):
        self.assertIsNone(_match_cluster_color("District"))
        self.assertIsNone(_match_cluster_color("Aden"))

    def test_non_string_input_returns_none_without_crashing(self):
        self.assertIsNone(_match_cluster_color(None))
        self.assertIsNone(_match_cluster_color(42))

    def test_all_eleven_iasc_clusters_are_covered(self):
        # The 11 IASC global clusters -- confirms none were dropped/typoed.
        for name in [
            "Camp Coordination and Camp Management", "Early Recovery", "Education",
            "Emergency Shelter", "Emergency Telecommunications", "Food Security",
            "Health", "Logistics", "Nutrition", "Protection", "WASH",
        ]:
            self.assertIsNotNone(_match_cluster_color(name), name)


class TestStylingToolsDegradeOutsideQgis(unittest.TestCase):
    def test_apply_graduated_style_degrades(self):
        res = apply_graduated_style("layer", "field")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_apply_graduated_style_degrades_with_cluster_param(self):
        res = apply_graduated_style("layer", "field", cluster="WASH")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_apply_graduated_symbol_style_degrades(self):
        res = apply_graduated_symbol_style("layer", "field")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_apply_categorized_style_degrades(self):
        res = apply_categorized_style("layer", "field")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_apply_categorized_style_degrades_with_palette_param(self):
        res = apply_categorized_style("layer", "field", palette="humanitarian_cluster")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestApplyGraduatedStyleWithBreaks(unittest.TestCase):
    """Point 13 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: no
    fixed-operational-threshold classification existed at all -- apply_graduated_style
    always went through an auto-selected Jenks/equal-interval/quantile method. breaks=
    bypasses that entirely and builds QgsRendererRange objects directly from caller-
    supplied boundaries."""

    def _make_layer(self, values, field_name="pop_affected"):
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

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsGraduatedSymbolRenderer", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsRendererRange", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsSymbol", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsStyle", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_breaks_builds_manual_ranges_from_data_min_max(
        self, mock_find, mock_style, mock_symbol, mock_range, mock_renderer_cls, mock_wkb,
    ):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        layer = self._make_layer([5000, 15000, 30000, 60000, 120000])
        layer.geometryType.return_value = "polygon-sentinel"
        mock_find.return_value = layer
        mock_renderer_instance = MagicMock()
        mock_renderer_cls.return_value = mock_renderer_instance

        res = apply_graduated_style("districts", "pop_affected", breaks=[10000, 25000, 50000, 100000])

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["classes"], 5)
        self.assertEqual(res["classification_method"], "Manual (defined breaks)")
        self.assertEqual(res["breaks"], [10000, 25000, 50000, 100000])
        self.assertEqual(mock_range.call_count, 5)
        first_call_args = mock_range.call_args_list[0][0]
        self.assertEqual(first_call_args[0], 5000.0)
        self.assertEqual(first_call_args[1], 10000)
        last_call_args = mock_range.call_args_list[-1][0]
        self.assertEqual(last_call_args[0], 100000)
        self.assertEqual(last_call_args[1], 120000.0)
        mock_renderer_instance.updateColorRamp.assert_called_once()
        layer.setRenderer.assert_called_once_with(mock_renderer_instance)

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_unsorted_breaks_are_sorted(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        layer = self._make_layer([1, 2, 3], field_name="field")
        layer.geometryType.return_value = "polygon-sentinel"
        mock_find.return_value = layer

        with patch("cartogen_ai.core.agent.tools.styling_tools.QgsGraduatedSymbolRenderer", create=True), \
             patch("cartogen_ai.core.agent.tools.styling_tools.QgsRendererRange", create=True), \
             patch("cartogen_ai.core.agent.tools.styling_tools.QgsSymbol", create=True), \
             patch("cartogen_ai.core.agent.tools.styling_tools.QgsStyle", create=True):
            res = apply_graduated_style("layer", "field", breaks=[3, 1, 2])

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["breaks"], [1, 2, 3])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_empty_breaks_list_rejected(self):
        res = apply_graduated_style("layer", "field", breaks=[])
        self.assertIn("error", res)
        self.assertIn("breaks", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_num_classes_below_2_rejected(self):
        res = apply_graduated_style("layer", "field", num_classes=1)
        self.assertIn("error", res)
        self.assertIn("num_classes", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsGraduatedSymbolRenderer", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsRendererRange", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsSymbol", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsStyle", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_logarithmic_mode_routes_through_manual_breaks_path(
        self, mock_find, mock_style, mock_symbol, mock_range, mock_renderer_cls, mock_wkb,
    ):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        layer = self._make_layer([1, 10, 100, 1000, 10000])
        layer.geometryType.return_value = "polygon-sentinel"
        mock_find.return_value = layer
        mock_renderer_cls.return_value = MagicMock()

        res = apply_graduated_style("districts", "pop_affected", mode="logarithmic", num_classes=5)

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["classification_method"], "Manual (defined breaks)")
        self.assertEqual(len(res["breaks"]), 4)

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_logarithmic_mode_with_non_positive_values_reports_error(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        layer = self._make_layer([-5, 10, 100])
        layer.geometryType.return_value = "polygon-sentinel"
        mock_find.return_value = layer

        res = apply_graduated_style("districts", "pop_affected", mode="logarithmic")

        self.assertIn("error", res)
        self.assertIn("logarithmic", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsGraduatedSymbolRenderer", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsSymbol", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsStyle", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_num_classes_is_passed_through_to_create_renderer(
        self, mock_find, mock_style, mock_symbol, mock_renderer_cls, mock_wkb,
    ):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        layer = self._make_layer(list(range(1, 21)), field_name="field")
        layer.geometryType.return_value = "polygon-sentinel"
        mock_find.return_value = layer
        mock_renderer_cls.createRenderer.return_value = MagicMock()

        res = apply_graduated_style("layer", "field", mode="quantile", num_classes=7)

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["classes"], 7)
        _, _, classes_arg, *_ = mock_renderer_cls.createRenderer.call_args[0]
        self.assertEqual(classes_arg, 7)


class TestApplyRuleBasedStyle(unittest.TestCase):
    """v1.8.0 workstream 1: apply_rule_based_style, for a fixed-vocabulary
    field (e.g. route/facility status) needing a caller-chosen color per
    value plus a mandatory 'Unknown / No data' catch-all class."""

    def test_degrades_gracefully_outside_qgis(self):
        res = apply_rule_based_style("layer", "status", [{"value": "open", "color_hex": "#2E7D32"}])
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_rejects_empty_rules(self):
        res = apply_rule_based_style("layer", "status", [])
        self.assertIn("error", res)
        self.assertIn("rules", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_reports_missing_layer(self, mock_find):
        mock_find.return_value = None
        res = apply_rule_based_style("layer", "status", [{"value": "open", "color_hex": "#2E7D32"}])
        self.assertIn("error", res)
        self.assertIn("not found", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_reports_missing_field(self, mock_find):
        field_mock = MagicMock()
        field_mock.name.return_value = "other_field"
        layer = MagicMock()
        layer.fields.return_value = [field_mock]
        mock_find.return_value = layer
        res = apply_rule_based_style("layer", "status", [{"value": "open", "color_hex": "#2E7D32"}])
        self.assertIn("error", res)
        self.assertIn("Field 'status'", res["error"])

    def _make_status_layer(self):
        field_mock = MagicMock()
        field_mock.name.return_value = "status"
        layer = MagicMock()
        layer.fields.return_value = [field_mock]
        return layer

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsRuleBasedRenderer", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsSymbol", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QColor", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_builds_one_rule_per_value_plus_catch_all(
        self, mock_find, mock_color, mock_symbol_cls, mock_renderer_cls, mock_expr,
    ):
        layer = self._make_status_layer()
        mock_find.return_value = layer

        mock_expr.quotedColumnRef.return_value = '"status"'
        mock_expr.quotedValue.side_effect = lambda v: f"'{v}'"

        first_rule = MagicMock()
        root_rule = MagicMock()
        root_rule.children.return_value = [first_rule]
        renderer_instance = MagicMock()
        renderer_instance.rootRule.return_value = root_rule
        mock_renderer_cls.return_value = renderer_instance

        cloned_rules = [MagicMock(), MagicMock()]  # "closed" value rule, then the catch-all
        first_rule.clone.side_effect = cloned_rules

        rules = [
            {"value": "open", "label": "Open", "color_hex": "#2E7D32"},
            {"value": "closed", "label": "Closed", "color_hex": "#B3261E"},
        ]
        res = apply_rule_based_style("route_layer", "status", rules)

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["rules_applied"], 2)
        self.assertEqual(res["classes"], 3)  # 2 rules + catch-all
        first_rule.setFilterExpression.assert_called_once_with("\"status\" = 'open'")
        first_rule.setLabel.assert_called_once_with("Open")
        cloned_rules[0].setFilterExpression.assert_called_once_with("\"status\" = 'closed'")
        cloned_rules[0].setLabel.assert_called_once_with("Closed")
        cloned_rules[1].setIsElse.assert_called_once_with(True)
        cloned_rules[1].setLabel.assert_called_once_with("Unknown / No data")
        # "ELSE" matches how QGIS Desktop's own "Add rule" dialog labels an
        # else rule's filter column -- setIsElse(True) is what actually
        # restricts it to unmatched features at render time (confirmed via
        # a real QgsMapRendererCustomPainterJob paint against QGIS 4.2.2:
        # "" and "ELSE" both rendered every segment correctly).
        cloned_rules[1].setFilterExpression.assert_called_once_with("ELSE")
        self.assertEqual(root_rule.appendChild.call_count, 2)
        layer.setRenderer.assert_called_once_with(renderer_instance)
        layer.triggerRepaint.assert_called_once()

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsRuleBasedRenderer", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsSymbol", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QColor", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_label_defaults_to_value_when_omitted(
        self, mock_find, mock_color, mock_symbol_cls, mock_renderer_cls, mock_expr,
    ):
        layer = self._make_status_layer()
        mock_find.return_value = layer
        mock_expr.quotedColumnRef.return_value = '"status"'
        mock_expr.quotedValue.side_effect = lambda v: f"'{v}'"

        first_rule = MagicMock()
        root_rule = MagicMock()
        root_rule.children.return_value = [first_rule]
        renderer_instance = MagicMock()
        renderer_instance.rootRule.return_value = root_rule
        mock_renderer_cls.return_value = renderer_instance
        first_rule.clone.return_value = MagicMock()  # the catch-all only, for this single-rule input

        res = apply_rule_based_style("route_layer", "status", [{"value": "open", "color_hex": "#2E7D32"}])

        self.assertTrue(res.get("success"), res)
        first_rule.setLabel.assert_called_once_with("open")

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsExpression", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsRuleBasedRenderer", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsSymbol", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QColor", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_exception_inside_renderer_construction_returns_error_dict(
        self, mock_find, mock_color, mock_symbol_cls, mock_renderer_cls, mock_expr,
    ):
        layer = self._make_status_layer()
        mock_find.return_value = layer
        mock_expr.quotedColumnRef.return_value = '"status"'
        mock_expr.quotedValue.side_effect = lambda v: f"'{v}'"
        mock_renderer_cls.side_effect = RuntimeError("boom")

        res = apply_rule_based_style("route_layer", "status", [{"value": "open", "color_hex": "#2E7D32"}])
        self.assertIn("error", res)
        self.assertIn("boom", res["error"])


class TestApplyGraduatedSymbolStyleValidation(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_rejects_non_point_layers(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PointGeometry = "point-geometry-sentinel"
        fake_field = MagicMock()
        fake_field.name.return_value = "field"
        fake_layer = MagicMock()
        fake_layer.fields.return_value = [fake_field]
        fake_layer.geometryType.return_value = "not-a-point"
        mock_find.return_value = fake_layer

        res = apply_graduated_symbol_style("layer", "field")

        self.assertIn("error", res)
        self.assertIn("point layers", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_rejects_invalid_size_range(self):
        # Validated before any layer lookup, so this doesn't need QGIS mocks.
        res = apply_graduated_symbol_style("layer", "field", min_size=10, max_size=5)
        self.assertIn("error", res)
        self.assertIn("min_size", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_rejects_num_classes_below_2(self):
        res = apply_graduated_symbol_style("layer", "field", num_classes=1)
        self.assertIn("error", res)
        self.assertIn("num_classes", res["error"])

    def _make_point_layer(self, values, field_name="magnitude"):
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

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_rejects_logarithmic_mode(self, mock_find, mock_wkb):
        mock_wkb.GeometryType.PointGeometry = "point-sentinel"
        layer = self._make_point_layer([1, 10, 100, 1000, 10000])
        layer.geometryType.return_value = "point-sentinel"
        mock_find.return_value = layer

        res = apply_graduated_symbol_style("layer", "magnitude", mode="logarithmic")

        self.assertIn("error", res)
        self.assertIn("logarithmic", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsGraduatedSymbolRenderer", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsSymbol", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsStyle", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QColor", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_color_parameter_is_used_instead_of_hardcoded_default(
        self, mock_find, mock_qcolor, mock_style, mock_symbol, mock_renderer_cls, mock_wkb,
    ):
        mock_wkb.GeometryType.PointGeometry = "point-sentinel"
        layer = self._make_point_layer([1, 2, 3, 4, 5, 6, 7, 8], field_name="field")
        layer.geometryType.return_value = "point-sentinel"
        mock_find.return_value = layer
        fake_range = MagicMock()
        mock_renderer_cls.createRenderer.return_value.ranges.return_value = [fake_range]

        res = apply_graduated_symbol_style("layer", "field", color="#ff0000")

        self.assertTrue(res.get("success"), res)
        mock_qcolor.assert_called_once_with("#ff0000")


class TestGeometrySortKey(unittest.TestCase):
    """Pure Python, no QGIS import needed -- see styling_tools.py for why this
    ordering exists: points/lines must sort ahead of polygons/rasters so a
    solid-fill area layer added later doesn't bury small point markers."""

    def test_draw_order_points_first_rasters_last(self):
        order = sorted(
            ["raster", "polygon", "point", "line"],
            key=_geometry_sort_key,
        )
        self.assertEqual(order, ["point", "line", "polygon", "raster"])

    def test_unknown_kind_sorts_last(self):
        order = sorted(["polygon", "unknown", "point"], key=_geometry_sort_key)
        self.assertEqual(order[-1], "unknown")


class TestApplyOpacity(unittest.TestCase):
    def test_sets_layer_opacity_as_fraction(self):
        layer = MagicMock()
        resolved = _apply_opacity(layer, 75)
        layer.setOpacity.assert_called_once_with(0.75)
        self.assertEqual(resolved, 75)

    def test_clamps_out_of_range_values(self):
        layer = MagicMock()
        self.assertEqual(_apply_opacity(layer, 150), 100)
        layer.setOpacity.assert_called_with(1.0)

        layer2 = MagicMock()
        self.assertEqual(_apply_opacity(layer2, -10), 0)
        layer2.setOpacity.assert_called_with(0.0)


class TestDefaultOpacityForGeometry(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsWkbTypes", create=True)
    def test_polygons_default_semi_transparent(self, mock_wkb):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        self.assertEqual(_default_opacity_for_geometry("polygon-sentinel"), 75)

    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsWkbTypes", create=True)
    def test_points_and_lines_stay_fully_opaque(self, mock_wkb):
        mock_wkb.GeometryType.PolygonGeometry = "polygon-sentinel"
        self.assertEqual(_default_opacity_for_geometry("point-sentinel"), 100)


class TestLayerOrderingToolsDegradeOutsideQgis(unittest.TestCase):
    def test_set_layer_transparency_degrades(self):
        res = set_layer_transparency("layer", 50)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_auto_arrange_layer_order_degrades(self):
        res = auto_arrange_layer_order()
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_set_layer_order_degrades(self):
        res = set_layer_order(["a", "b"])
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestLayerOrderingToolsValidation(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_set_layer_transparency_rejects_out_of_range(self):
        # Validated before any layer lookup, so this doesn't need QGIS mocks.
        res = set_layer_transparency("layer", 150)
        self.assertIn("error", res)
        self.assertIn("opacity_percent", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_set_layer_order_rejects_empty_list(self):
        res = set_layer_order([])
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_set_layer_order_reports_missing_layers(self, mock_find):
        mock_find.return_value = None
        res = set_layer_order(["ghost_layer"])
        self.assertIn("error", res)
        self.assertIn("ghost_layer", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_change_layer_color_rejects_out_of_range_opacity(self):
        # Validated before any layer lookup, so this doesn't need QGIS mocks.
        res = change_layer_color("layer", "#ff0000", opacity=150)
        self.assertIn("error", res)
        self.assertIn("opacity", res["error"])


class TestHotspotAnalysisDegradesOutsideQgis(unittest.TestCase):
    def test_degrades(self):
        res = hotspot_analysis("incidents", 500)
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])


class TestHotspotAnalysisValidation(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_rejects_non_positive_radius(self):
        # Validated before any layer lookup, so this doesn't need QGIS mocks.
        res = hotspot_analysis("incidents", 0)
        self.assertIn("error", res)
        self.assertIn("radius", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_reports_missing_layer(self, mock_find):
        mock_find.return_value = None
        res = hotspot_analysis("ghost_layer", 500)
        self.assertIn("error", res)
        self.assertIn("ghost_layer", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_rejects_unknown_weight_field(self, mock_find):
        fake_field = MagicMock()
        fake_field.name.return_value = "severity"
        fake_layer = MagicMock()
        fake_layer.fields.return_value = [fake_field]
        mock_find.return_value = fake_layer

        res = hotspot_analysis("incidents", 500, weight_field="nonexistent")

        self.assertIn("error", res)
        self.assertIn("nonexistent", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsRasterLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.processing", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_defaults_pixel_size_to_one_tenth_radius(self, mock_find, mock_project, mock_processing, mock_raster_cls):
        fake_layer = MagicMock()
        fake_layer.fields.return_value = []
        mock_find.return_value = fake_layer
        mock_processing.run.return_value = {"OUTPUT": "/tmp/density.tif"}
        mock_raster_cls.return_value.isValid.return_value = True

        res = hotspot_analysis("incidents", 100)

        self.assertTrue(res["success"])
        self.assertEqual(res["pixel_size"], 10.0)
        called_params = mock_processing.run.call_args[0][1]
        self.assertEqual(called_params["PIXEL_SIZE"], 10.0)


class TestStyleToolsDegradeOutsideQgis(unittest.TestCase):
    def test_save_layer_style_degrades_gracefully(self):
        res = save_layer_style("districts")
        self.assertIn("error", res)
        self.assertIn("QGIS", res["error"])

    def test_load_layer_style_degrades_gracefully(self):
        res = load_layer_style("districts", "/tmp/does_not_matter.qml")
        self.assertIn("error", res)
        self.assertIn("QGIS", res["error"])


class TestSaveLayerStyle(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_reports_missing_layer(self, mock_find):
        mock_find.return_value = None
        res = save_layer_style("ghost_layer")
        self.assertIn("error", res)
        self.assertIn("ghost_layer", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_explicit_output_path_used_directly(self, mock_find):
        layer = MagicMock()
        layer.saveNamedStyle.return_value = ("Created default style file as foo.qml", True)
        mock_find.return_value = layer

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = os.path.join(tmp_dir, "custom_style.qml")
            res = save_layer_style("districts", output_path=out_path)

            self.assertTrue(res["success"])
            self.assertEqual(res["path"], out_path)
            self.assertNotIn("warning", res)
            layer.saveNamedStyle.assert_called_once_with(out_path)

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_qgis_save_failure_reports_the_real_message(self, mock_find):
        layer = MagicMock()
        layer.source.return_value = ""
        layer.name.return_value = "districts"
        layer.saveNamedStyle.return_value = ("permission denied", False)
        mock_find.return_value = layer

        res = save_layer_style("districts")

        self.assertIn("error", res)
        self.assertIn("permission denied", res["error"])


class TestDeriveStylePath(unittest.TestCase):
    def test_sits_beside_a_real_on_disk_source(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "districts.gpkg")
            with open(source_path, "w") as f:
                f.write("not a real geopackage, just needs to exist")
            layer = MagicMock()
            layer.source.return_value = source_path
            layer.name.return_value = "districts"

            path, used_fallback = _derive_style_path(layer, None)

            self.assertEqual(path, f"{source_path}.qml")
            self.assertFalse(used_fallback)

    def test_strips_qgis_uri_suffix_before_checking_for_a_real_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = os.path.join(tmp_dir, "admin.gpkg")
            with open(source_path, "w") as f:
                f.write("not a real geopackage, just needs to exist")
            layer = MagicMock()
            layer.source.return_value = f"{source_path}|layername=admin2"
            layer.name.return_value = "admin2"

            path, used_fallback = _derive_style_path(layer, None)

            self.assertEqual(path, f"{source_path}.qml")
            self.assertFalse(used_fallback)

    def test_falls_back_to_desktop_for_a_scratch_layer(self):
        layer = MagicMock()
        layer.source.return_value = "memory layer, no real file"
        layer.name.return_value = "scratch points"

        path, used_fallback = _derive_style_path(layer, None)

        self.assertTrue(used_fallback)
        self.assertTrue(path.endswith("scratch points.qml"))

    def test_explicit_output_path_always_wins(self):
        layer = MagicMock()
        path, used_fallback = _derive_style_path(layer, "/explicit/path.qml")
        self.assertEqual(path, "/explicit/path.qml")
        self.assertFalse(used_fallback)
        layer.source.assert_not_called()


class TestLoadLayerStyle(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_reports_missing_layer(self, mock_find):
        mock_find.return_value = None
        res = load_layer_style("ghost_layer", "/tmp/style.qml")
        self.assertIn("error", res)
        self.assertIn("ghost_layer", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_reports_missing_style_file(self, mock_find):
        mock_find.return_value = MagicMock()
        res = load_layer_style("districts", "/tmp/does_not_exist_at_all.qml")
        self.assertIn("error", res)
        self.assertIn("not found", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_qgis_load_failure_reports_the_real_message(self, mock_find):
        layer = MagicMock()
        layer.loadNamedStyle.return_value = ("not a valid style file", False)
        mock_find.return_value = layer

        with tempfile.NamedTemporaryFile(suffix=".qml", delete=False) as f:
            style_path = f.name
        try:
            res = load_layer_style("districts", style_path)
            self.assertIn("error", res)
            self.assertIn("not a valid style file", res["error"])
            layer.triggerRepaint.assert_not_called()
        finally:
            os.remove(style_path)

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    def test_success_loads_style_and_repaints(self, mock_find):
        layer = MagicMock()
        layer.loadNamedStyle.return_value = ("", True)
        mock_find.return_value = layer

        with tempfile.NamedTemporaryFile(suffix=".qml", delete=False) as f:
            style_path = f.name
        try:
            res = load_layer_style("districts", style_path)
            self.assertTrue(res["success"])
            self.assertEqual(res["style_path"], style_path)
            layer.loadNamedStyle.assert_called_once_with(style_path)
            layer.triggerRepaint.assert_called_once()
        finally:
            os.remove(style_path)


class TestApplyHeatmapStyle(unittest.TestCase):
    """apply_heatmap_style: no test coverage at all before QUAL-006 (2026-09-14 audit)."""

    def test_degrades_outside_qgis(self):
        res = apply_heatmap_style("incidents")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name", return_value=None)
    def test_reports_missing_layer(self, mock_find):
        res = apply_heatmap_style("ghost_layer")
        self.assertIn("error", res)
        self.assertIn("ghost_layer", res["error"])

    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsHeatmapRenderer", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_success_sets_renderer_without_a_field(self, mock_find, mock_renderer_cls):
        layer = MagicMock()
        layer.fields.return_value = []
        mock_find.return_value = layer
        renderer = mock_renderer_cls.return_value

        res = apply_heatmap_style("incidents")

        self.assertTrue(res.get("success"), res)
        layer.setRenderer.assert_called_once_with(renderer)
        layer.triggerRepaint.assert_called_once()
        renderer.setWeightExpression.assert_not_called()

    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsHeatmapRenderer", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_known_field_sets_weight_expression(self, mock_find, mock_renderer_cls):
        layer = MagicMock()
        severity_field = MagicMock()
        severity_field.name.return_value = "severity"
        layer.fields.return_value = [severity_field]
        mock_find.return_value = layer
        renderer = mock_renderer_cls.return_value

        res = apply_heatmap_style("incidents", field="severity")

        self.assertTrue(res.get("success"), res)
        renderer.setWeightExpression.assert_called_once_with('"severity"')

    @patch("cartogen_ai.core.agent.tools.styling_tools.QgsHeatmapRenderer", create=True)
    @patch("cartogen_ai.core.agent.tools.styling_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.styling_tools.QGIS_AVAILABLE", True)
    def test_unknown_field_is_silently_ignored_not_an_error(self, mock_find, mock_renderer_cls):
        # Matches the tool's own actual behavior (a field check with no error branch) --
        # documented here so a future change to this is a deliberate choice, not a surprise.
        layer = MagicMock()
        layer.fields.return_value = []
        mock_find.return_value = layer
        renderer = mock_renderer_cls.return_value

        res = apply_heatmap_style("incidents", field="not_a_real_field")

        self.assertTrue(res.get("success"), res)
        renderer.setWeightExpression.assert_not_called()


if __name__ == "__main__":
    unittest.main()
