# -*- coding: utf-8 -*-
"""Tests for agent/tools/impedance_tools.py -- the composite impedance
field builder, point 8 / docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md
section 2 item 2, v1.7.0 workstream 4."""
import unittest
from unittest.mock import patch, MagicMock

from cartogen_ai.core.agent.tools.impedance_tools import (
    build_composite_impedance_field, _slope_penalty,
    _HIGHWAY_BASE_SPEED_KMH, _SURFACE_PENALTY, _DEFAULT_BASE_SPEED_KMH,
    _DEFAULT_SURFACE_PENALTY, _MIN_EFFECTIVE_SPEED_KMH,
)


def _mock_network(field_names, features):
    """A MagicMock road-network layer with real-enough field/feature
    plumbing for build_composite_impedance_field's own logic to exercise
    correctly, matching this suite's established convention (e.g.
    tests/test_logistics_tools.py's _stop_layer helper). fields() must
    support BOTH iteration ([f.name() for f in layer.fields()]) and
    .indexOf() -- a plain list supports the former but not arbitrary
    attribute assignment for the latter, so this uses a MagicMock
    configured for both instead."""
    field_objs = [MagicMock() for _ in field_names]
    for f, n in zip(field_objs, field_names):
        f.name.return_value = n
    fields_mock = MagicMock()
    fields_mock.__iter__.side_effect = lambda: iter(field_objs)
    fields_mock.indexOf.side_effect = lambda name: field_names.index(name) if name in field_names else -1

    layer = MagicMock()
    layer.fields.return_value = fields_mock
    layer.getFeatures.return_value = features
    layer.featureCount.return_value = len(features)
    return layer


def _mock_feature(attrs, geom=None):
    feat = MagicMock()
    feat.attribute.side_effect = lambda key: attrs.get(key)
    feat.id.return_value = id(feat)
    if geom is None:
        geom = MagicMock()
        geom.isEmpty.return_value = False
    feat.geometry.return_value = geom
    return feat


class TestDegradesGracefullyOutsideQgis(unittest.TestCase):
    def test_degrades(self):
        result = build_composite_impedance_field("roads")
        self.assertIn("error", result)
        self.assertIn("QGIS not available", result["error"])


class TestValidation(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    def test_reports_missing_network_layer(self, mock_project):
        mock_project.instance.return_value.mapLayersByName.return_value = []
        result = build_composite_impedance_field("ghost_roads")
        self.assertIn("error", result)
        self.assertIn("ghost_roads", result["error"])

    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    def test_reports_missing_dem_layer(self, mock_project):
        network = _mock_network(["highway"], [])

        def side_effect(name):
            return [network] if name == "roads" else []
        mock_project.instance.return_value.mapLayersByName.side_effect = side_effect

        result = build_composite_impedance_field("roads", dem_layer="ghost_dem")
        self.assertIn("error", result)
        self.assertIn("ghost_dem", result["error"])

    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    def test_reports_missing_damage_field(self, mock_project):
        network = _mock_network(["highway"], [])
        mock_project.instance.return_value.mapLayersByName.return_value = [network]

        result = build_composite_impedance_field("roads", damage_field="ghost_damage")
        self.assertIn("error", result)
        self.assertIn("ghost_damage", result["error"])


class TestBaseSpeedAndSurfaceBlending(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QVariant", create=True)
    def test_known_highway_and_surface_combination_produces_expected_speed(self, mock_variant, mock_field, mock_project):
        feat = _mock_feature({"highway": "primary", "surface": "gravel"})
        network = _mock_network(["highway", "surface"], [feat])
        mock_project.instance.return_value.mapLayersByName.return_value = [network]

        result = build_composite_impedance_field("roads")

        self.assertTrue(result.get("success"), result)
        expected_speed = _HIGHWAY_BASE_SPEED_KMH["primary"] * _SURFACE_PENALTY["gravel"]
        network.changeAttributeValue.assert_called_once()
        called_fid, called_idx, called_value = network.changeAttributeValue.call_args[0]
        self.assertAlmostEqual(called_value, expected_speed)

    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QVariant", create=True)
    def test_missing_highway_and_surface_fields_uses_defaults_no_crash(self, mock_variant, mock_field, mock_project):
        feat = _mock_feature({})
        network = _mock_network([], [feat])
        mock_project.instance.return_value.mapLayersByName.return_value = [network]

        result = build_composite_impedance_field("roads")

        self.assertTrue(result.get("success"), result)
        called_value = network.changeAttributeValue.call_args[0][2]
        self.assertAlmostEqual(called_value, _DEFAULT_BASE_SPEED_KMH * _DEFAULT_SURFACE_PENALTY)

    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QVariant", create=True)
    def test_unknown_highway_value_falls_back_to_default_speed(self, mock_variant, mock_field, mock_project):
        feat = _mock_feature({"highway": "some_future_osm_tag_value"})
        network = _mock_network(["highway"], [feat])
        mock_project.instance.return_value.mapLayersByName.return_value = [network]

        build_composite_impedance_field("roads")

        called_value = network.changeAttributeValue.call_args[0][2]
        self.assertAlmostEqual(called_value, _DEFAULT_BASE_SPEED_KMH)


class TestDamageField(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QVariant", create=True)
    def test_numeric_damage_value_multiplies_speed(self, mock_variant, mock_field, mock_project):
        feat = _mock_feature({"highway": "residential", "damage": "0.5"})
        network = _mock_network(["highway", "damage"], [feat])
        mock_project.instance.return_value.mapLayersByName.return_value = [network]

        result = build_composite_impedance_field("roads", damage_field="damage")

        self.assertTrue(result.get("success"), result)
        called_value = network.changeAttributeValue.call_args[0][2]
        self.assertAlmostEqual(called_value, _HIGHWAY_BASE_SPEED_KMH["residential"] * 0.5)
        self.assertNotIn("warning", result)

    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QVariant", create=True)
    def test_damage_value_out_of_range_is_clamped(self, mock_variant, mock_field, mock_project):
        feat = _mock_feature({"highway": "residential", "damage": "5.0"})
        network = _mock_network(["highway", "damage"], [feat])
        mock_project.instance.return_value.mapLayersByName.return_value = [network]

        build_composite_impedance_field("roads", damage_field="damage")

        called_value = network.changeAttributeValue.call_args[0][2]
        self.assertAlmostEqual(called_value, _HIGHWAY_BASE_SPEED_KMH["residential"] * 1.0)

    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QVariant", create=True)
    def test_non_numeric_damage_value_defaults_and_warns(self, mock_variant, mock_field, mock_project):
        feat = _mock_feature({"highway": "residential", "damage": "Destroyed"})
        network = _mock_network(["highway", "damage"], [feat])
        mock_project.instance.return_value.mapLayersByName.return_value = [network]

        result = build_composite_impedance_field("roads", damage_field="damage")

        self.assertTrue(result.get("success"), result)
        called_value = network.changeAttributeValue.call_args[0][2]
        self.assertAlmostEqual(called_value, _HIGHWAY_BASE_SPEED_KMH["residential"] * 1.0)
        self.assertIn("warning", result)

    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QVariant", create=True)
    def test_zero_damage_value_floors_at_minimum_speed_not_zero(self, mock_variant, mock_field, mock_project):
        feat = _mock_feature({"highway": "residential", "damage": "0.0"})
        network = _mock_network(["highway", "damage"], [feat])
        mock_project.instance.return_value.mapLayersByName.return_value = [network]

        build_composite_impedance_field("roads", damage_field="damage")

        called_value = network.changeAttributeValue.call_args[0][2]
        self.assertEqual(called_value, _MIN_EFFECTIVE_SPEED_KMH)


class TestFieldCreation(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QVariant", create=True)
    def test_creates_output_field_when_missing(self, mock_variant, mock_field, mock_project):
        network = _mock_network([], [])
        mock_project.instance.return_value.mapLayersByName.return_value = [network]

        build_composite_impedance_field("roads", output_field="impedance_cost")

        network.dataProvider.return_value.addAttributes.assert_called_once()
        network.updateFields.assert_called_once()

    @patch("cartogen_ai.core.agent.tools.impedance_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsField", create=True)
    @patch("cartogen_ai.core.agent.tools.impedance_tools.QVariant", create=True)
    def test_reuses_existing_output_field(self, mock_variant, mock_field, mock_project):
        network = _mock_network(["impedance_cost"], [])
        mock_project.instance.return_value.mapLayersByName.return_value = [network]

        build_composite_impedance_field("roads", output_field="impedance_cost")

        network.dataProvider.return_value.addAttributes.assert_not_called()


class TestSlopePenaltyFunction(unittest.TestCase):
    """Pure-ish tests for _slope_penalty -- takes a real dataProvider mock
    since it's a small, directly-testable unit."""

    def test_zero_length_returns_no_penalty(self):
        dem = MagicMock()
        result = _slope_penalty(dem, MagicMock(x=lambda: 0, y=lambda: 0), MagicMock(x=lambda: 0, y=lambda: 0), 0)
        self.assertEqual(result, 1.0)

    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsPointXY", create=True)
    def test_sample_outside_extent_returns_no_penalty(self, mock_pointxy):
        dem = MagicMock()
        dem.dataProvider.return_value.sample.return_value = (float("nan"), False)
        start = MagicMock(x=lambda: 0, y=lambda: 0)
        end = MagicMock(x=lambda: 10, y=lambda: 0)
        result = _slope_penalty(dem, start, end, 10)
        self.assertEqual(result, 1.0)

    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsPointXY", create=True)
    def test_steep_slope_reduces_penalty_floored_at_minimum(self, mock_pointxy):
        dem = MagicMock()
        # Huge elevation change over a short distance -- steep slope.
        dem.dataProvider.return_value.sample.side_effect = [(0.0, True), (1000.0, True)]
        start = MagicMock(x=lambda: 0, y=lambda: 0)
        end = MagicMock(x=lambda: 10, y=lambda: 0)
        result = _slope_penalty(dem, start, end, 10)
        self.assertEqual(result, 0.2)  # _MIN_SLOPE_PENALTY floor

    @patch("cartogen_ai.core.agent.tools.impedance_tools.QgsPointXY", create=True)
    def test_flat_terrain_no_penalty(self, mock_pointxy):
        dem = MagicMock()
        dem.dataProvider.return_value.sample.side_effect = [(100.0, True), (100.0, True)]
        start = MagicMock(x=lambda: 0, y=lambda: 0)
        end = MagicMock(x=lambda: 100, y=lambda: 0)
        result = _slope_penalty(dem, start, end, 100)
        self.assertEqual(result, 1.0)


if __name__ == "__main__":
    unittest.main()
