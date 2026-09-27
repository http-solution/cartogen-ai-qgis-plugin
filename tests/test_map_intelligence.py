# -*- coding: utf-8 -*-
"""Unit tests for the Map Intelligence Engine and ChatActionRegistry."""

import unittest
from unittest.mock import MagicMock, patch
from cartogen_ai.core.agent.map_intelligence import (
    ChatActionRegistry,
    STYLE_PROFILES,
    MapOutputDescriptor,
    apply_component_symbology,
    process_map_output,
)


class TestChatActionRegistry(unittest.TestCase):
    def setUp(self):
        ChatActionRegistry.clear()

    def test_register_and_retrieve_action(self):
        act_id = ChatActionRegistry.register(
            kind="export",
            label="Export Layer",
            payload={"layer_name": "TestLayer", "format": "csv"},
            safety="dialog",
        )
        self.assertTrue(act_id.startswith("act_"))
        action = ChatActionRegistry.get(act_id)
        self.assertIsNotNone(action)
        self.assertEqual(action.kind, "export")
        self.assertEqual(action.label, "Export Layer")
        self.assertEqual(action.payload["layer_name"], "TestLayer")

    def test_invalid_action_id_returns_none(self):
        self.assertIsNone(ChatActionRegistry.get("act_nonexistent"))

    def test_clear_registry(self):
        act_id = ChatActionRegistry.register(kind="zoom", label="Zoom", payload={})
        self.assertIsNotNone(ChatActionRegistry.get(act_id))
        ChatActionRegistry.clear()
        self.assertIsNone(ChatActionRegistry.get(act_id))


class TestStyleProfiles(unittest.TestCase):
    def test_proximity_buffer_profile_uses_component_alpha(self):
        profile = STYLE_PROFILES["proximity_buffer"]
        self.assertLessEqual(profile["fill_alpha"], 60)   # Faint interior (~20%)
        self.assertEqual(profile["stroke_alpha"], 255)    # 100% crisp border
        self.assertEqual(profile["join_style"], "round")

    def test_administrative_boundary_profile_is_hollow(self):
        profile = STYLE_PROFILES["administrative_boundary"]
        self.assertEqual(profile["fill_alpha"], 0)        # 0% fill (hollow)
        self.assertGreaterEqual(profile["stroke_alpha"], 200) # Defined boundary outline

    def test_route_line_profile_defines_a_casing_wider_than_its_fill(self):
        """BUG-2026-09-27-3: every profile above this one is polygon-only --
        apply_component_symbology returned False for any line-geometry layer with no
        styling at all. route_line's casing (the outline beneath the fill line) must be
        wider than the fill itself for the standard road/route "casing" technique to
        actually read as a route rather than a flat, single-width line."""
        profile = STYLE_PROFILES["route_line"]
        self.assertGreater(profile["casing_width"], profile["stroke_width"])
        self.assertNotEqual(profile["default_hue"], profile["casing_hue"])


class TestLineComponentSymbology(unittest.TestCase):
    """BUG-2026-09-27-3: optimize_delivery_route's road-snapped route layer, and
    calculate_service_area's reachable-network lines layer, were both added to the
    project with zero styling -- apply_component_symbology unconditionally returned
    False for any non-polygon geometry. These tests exercise the new line-casing path
    directly, mocking the qgis.core symbols the same way other test files in this repo
    already do for QGIS-touching code with no real QGIS installation available."""

    @patch("cartogen_ai.core.agent.map_intelligence.Qt", create=True)
    @patch("cartogen_ai.core.agent.map_intelligence.QColor", create=True)
    @patch("cartogen_ai.core.agent.map_intelligence.QgsUnitTypes", create=True)
    @patch("cartogen_ai.core.agent.map_intelligence.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.map_intelligence.QgsSingleSymbolRenderer", create=True)
    @patch("cartogen_ai.core.agent.map_intelligence.QgsLineSymbol", create=True)
    @patch("cartogen_ai.core.agent.map_intelligence.QgsSimpleLineSymbolLayer", create=True)
    @patch("cartogen_ai.core.agent.map_intelligence.QgsVectorLayer", MagicMock, create=True)
    @patch("cartogen_ai.core.agent.map_intelligence.QGIS_AVAILABLE", True)
    def test_line_geometry_gets_a_two_layer_casing_symbol(
        self, mock_line_symbol_layer_cls, mock_line_symbol_cls,
        mock_renderer_cls, mock_wkb, mock_unit_types, mock_qcolor_cls, mock_qt,
    ):
        mock_wkb.LineGeometry = "LINE"
        mock_qcolor_cls.return_value.isValid.return_value = True
        layer = MagicMock()  # a real MagicMock instance -- isinstance(layer, MagicMock) is trivially True
        layer.geometryType.return_value = "LINE"
        mock_line_symbol_layer_cls.side_effect = lambda: MagicMock()
        symbol_instance = mock_line_symbol_cls.return_value

        descriptor = MapOutputDescriptor(layer_id="x", output_role="route_line")
        result = apply_component_symbology(layer, descriptor)

        self.assertTrue(result)
        # Two symbol layers: the wider casing at index 0, the narrower fill appended after.
        self.assertEqual(mock_line_symbol_layer_cls.call_count, 2)
        symbol_instance.changeSymbolLayer.assert_called_once()
        symbol_instance.appendSymbolLayer.assert_called_once()
        layer.setRenderer.assert_called_once_with(mock_renderer_cls.return_value)
        layer.triggerRepaint.assert_called_once()

    @patch("cartogen_ai.core.agent.map_intelligence.QgsWkbTypes", create=True)
    @patch("cartogen_ai.core.agent.map_intelligence.QgsVectorLayer", MagicMock, create=True)
    @patch("cartogen_ai.core.agent.map_intelligence.QGIS_AVAILABLE", True)
    def test_non_polygon_non_line_geometry_still_declines(self, mock_wkb):
        """Point geometry (or anything else) is untouched by this engine -- only the
        LineGeometry branch is new here; polygon and point behavior must stay as before."""
        mock_wkb.LineGeometry = "LINE"
        mock_wkb.PolygonGeometry = "POLY"
        layer = MagicMock()
        layer.geometryType.return_value = "POINT"

        descriptor = MapOutputDescriptor(layer_id="x", output_role="facilities")
        result = apply_component_symbology(layer, descriptor)

        self.assertFalse(result)
        layer.setRenderer.assert_not_called()


class TestMapOutputProcess(unittest.TestCase):
    def test_process_map_output_outside_qgis_degrades_gracefully(self):
        mock_layer = MagicMock()
        mock_layer.id.return_value = "layer_123"
        mock_layer.name.return_value = "Hospitals_5km_buffer"
        mock_layer.isValid.return_value = False

        res = process_map_output(mock_layer, output_role="proximity_buffer")
        self.assertTrue(res["success"])
        self.assertIn("action_chips", res)
        # Verify action chips were registered with opaque IDs
        chips = res["action_chips"]
        self.assertGreaterEqual(len(chips), 1)
        self.assertTrue(chips[0]["url"].startswith("cartogen://action/act_"))


if __name__ == "__main__":
    unittest.main()
