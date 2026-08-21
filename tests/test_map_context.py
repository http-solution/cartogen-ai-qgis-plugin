# -*- coding: utf-8 -*-
import unittest
from agent.map_context import get_map_context_summary
from agent.prompts import build_system_prompt, _format_map_context


class TestMapContext(unittest.TestCase):
    def test_returns_empty_dict_outside_qgis(self):
        # Test environment has no qgis.core -- QGIS_AVAILABLE is False.
        self.assertEqual(get_map_context_summary(), {})


class TestFormatMapContext(unittest.TestCase):
    def test_empty_context_produces_no_section(self):
        self.assertEqual(_format_map_context({}), "")
        self.assertEqual(_format_map_context(None), "")

    def test_formats_layers_and_metadata(self):
        ctx = {
            "project_title": "Jordan Analysis",
            "canvas_crs": "EPSG:4326",
            "active_layer": "Jordan_Governorates",
            "layer_count": 1,
            "layers": [
                {"name": "Jordan_Governorates", "type": "VectorLayer", "crs": "EPSG:4326",
                 "feature_count": 12, "fields": ["shapeName", "Population"]},
            ],
            "truncated": False,
        }
        text = _format_map_context(ctx)
        self.assertIn("Jordan Analysis", text)
        self.assertIn("Jordan_Governorates", text)
        self.assertIn("shapeName", text)
        self.assertIn("12 features", text)

    def test_build_system_prompt_includes_map_context_section(self):
        ctx = {"project_title": "Test", "canvas_crs": "EPSG:4326", "active_layer": "None", "layers": []}
        prompt = build_system_prompt(map_context=ctx)
        self.assertIn("CURRENT MAP CONTEXT", prompt)

    def test_build_system_prompt_omits_section_when_no_context(self):
        # Rule #4 in the base prompt references "CURRENT MAP CONTEXT" by name
        # regardless of whether the section is rendered -- check for the
        # actual section header, not just the substring.
        prompt = build_system_prompt()
        self.assertNotIn("## 🗺️ CURRENT MAP CONTEXT", prompt)


if __name__ == "__main__":
    unittest.main()
