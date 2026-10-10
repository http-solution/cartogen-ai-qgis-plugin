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
        mock_wkb.GeometryType.LineGeometry = "LINE"
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
        mock_wkb.GeometryType.LineGeometry = "LINE"
        mock_wkb.GeometryType.PolygonGeometry = "POLY"
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


class _FakeMemoryManager:
    """Same fake used by tests/test_map_state_memory.py -- matches
    SpatialMemoryManager's get_project_notes()/store_project_note() surface."""
    def __init__(self):
        self._notes = {}

    def get_project_notes(self):
        return dict(self._notes)

    def store_project_note(self, key, value):
        self._notes[key] = value
        return {"success": True}


class TestProcessMapOutputDesignStateMemory(unittest.TestCase):
    """§1.16 "smart mapping": process_map_output should reuse a project's own prior
    styling choice for a given output_role on a later, similar request -- rather than
    silently reverting to STYLE_PROFILES' hardcoded default every time -- unless the
    caller explicitly asks for something different. Mocks apply_component_symbology/
    insert_layer_semantically themselves rather than every individual qgis.core symbol
    class they touch -- this isolates the actual thing under test (process_map_output's
    recall-before/record-after wiring in map_intelligence.py) from that unrelated
    styling-internals machinery, which is already covered by TestLineComponentSymbology
    and the STYLE_PROFILES tests above."""

    def _mock_layer(self, geom_type="POLY"):
        layer = MagicMock()
        layer.id.return_value = "layer_new"
        layer.name.return_value = "New Layer"
        layer.geometryType.return_value = geom_type
        return layer

    @patch("cartogen_ai.core.agent.map_intelligence.insert_layer_semantically")
    @patch("cartogen_ai.core.agent.map_intelligence.apply_component_symbology")
    @patch("cartogen_ai.core.agent.tools.task_tools.get_memory_manager")
    def test_a_remembered_style_is_reused_when_the_caller_asks_for_nothing_specific(
        self, mock_get_mm, mock_apply_symbology, mock_insert,
    ):
        mock_apply_symbology.return_value = True
        mm = _FakeMemoryManager()
        mock_get_mm.return_value = mm
        from cartogen_ai.core.agent.map_state_memory import record_output
        record_output(mm, "proximity_buffer", "layer_old", "Old Buffer",
                       style_profile="proximity_buffer", properties={"color": "#123456"})

        layer = self._mock_layer()
        process_map_output(layer, output_role="proximity_buffer")

        # The remembered color was carried into the descriptor apply_component_symbology
        # actually received, rather than an empty properties dict.
        descriptor = mock_apply_symbology.call_args[0][1]
        self.assertEqual(descriptor.properties.get("color"), "#123456")
        self.assertEqual(descriptor.style_profile, "proximity_buffer")

    @patch("cartogen_ai.core.agent.map_intelligence.insert_layer_semantically")
    @patch("cartogen_ai.core.agent.map_intelligence.apply_component_symbology")
    @patch("cartogen_ai.core.agent.tools.task_tools.get_memory_manager")
    def test_an_explicit_caller_color_overrides_whatever_is_remembered(
        self, mock_get_mm, mock_apply_symbology, mock_insert,
    ):
        mock_apply_symbology.return_value = True
        mm = _FakeMemoryManager()
        mock_get_mm.return_value = mm
        from cartogen_ai.core.agent.map_state_memory import record_output
        record_output(mm, "proximity_buffer", "layer_old", "Old Buffer",
                       properties={"color": "#123456"})

        layer = self._mock_layer()
        process_map_output(layer, output_role="proximity_buffer", properties={"color": "#abcdef"})

        descriptor = mock_apply_symbology.call_args[0][1]
        self.assertEqual(descriptor.properties.get("color"), "#abcdef")

    @patch("cartogen_ai.core.agent.map_intelligence.insert_layer_semantically")
    @patch("cartogen_ai.core.agent.map_intelligence.apply_component_symbology")
    @patch("cartogen_ai.core.agent.tools.task_tools.get_memory_manager")
    def test_a_successful_styling_call_is_recorded_for_the_next_one_to_recall(
        self, mock_get_mm, mock_apply_symbology, mock_insert,
    ):
        mock_apply_symbology.return_value = True
        mm = _FakeMemoryManager()
        mock_get_mm.return_value = mm

        layer = self._mock_layer()
        process_map_output(layer, output_role="hazard_extent", properties={"color": "#ff8800"})

        from cartogen_ai.core.agent.map_state_memory import recall_output
        recalled = recall_output(mm, "hazard_extent")
        self.assertEqual(recalled["properties"]["color"], "#ff8800")
        self.assertEqual(recalled["layer_name"], "New Layer")

    @patch("cartogen_ai.core.agent.map_intelligence.insert_layer_semantically")
    @patch("cartogen_ai.core.agent.map_intelligence.apply_component_symbology")
    @patch("cartogen_ai.core.agent.tools.task_tools.get_memory_manager")
    def test_a_failed_styling_call_is_not_recorded(self, mock_get_mm, mock_apply_symbology, mock_insert):
        mock_apply_symbology.return_value = False
        mm = _FakeMemoryManager()
        mock_get_mm.return_value = mm

        layer = self._mock_layer()
        process_map_output(layer, output_role="hazard_extent", properties={"color": "#ff8800"})

        from cartogen_ai.core.agent.map_state_memory import recall_output
        self.assertIsNone(recall_output(mm, "hazard_extent"))

    @patch("cartogen_ai.core.agent.map_intelligence.insert_layer_semantically")
    @patch("cartogen_ai.core.agent.map_intelligence.apply_component_symbology")
    @patch("cartogen_ai.core.agent.tools.task_tools.get_memory_manager")
    def test_no_active_memory_manager_is_a_safe_no_op(self, mock_get_mm, mock_apply_symbology, mock_insert):
        mock_apply_symbology.return_value = True
        mock_get_mm.return_value = None
        layer = self._mock_layer()
        res = process_map_output(layer, output_role="proximity_buffer")
        self.assertTrue(res["success"])


if __name__ == "__main__":
    unittest.main()
