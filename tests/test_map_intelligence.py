# -*- coding: utf-8 -*-
"""Unit tests for the Map Intelligence Engine and ChatActionRegistry."""

import unittest
from unittest.mock import MagicMock, patch
from cartogen_ai.core.agent.map_intelligence import (
    MapOutputDescriptor,
    ChatActionRegistry,
    ChatAction,
    STYLE_PROFILES,
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
