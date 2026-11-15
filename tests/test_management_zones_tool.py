"""PLAN-023 R3-5: the registration contract of create_zoning_map (offline: no QGIS, no numpy needed). The zone maths is in test_raster_zones.py and the real-raster
behaviour in test_management_zones_tool_live.py."""
import unittest

from cartogen_ai.core import tool_operations
from cartogen_ai.core.agent.tools import management_zones_tool as tool
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS, TOOL_REGISTRY, TOOLS_SCHEMA


def schema():
    return next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "create_zoning_map")


class TestRegistration(unittest.TestCase):
    def test_it_is_registered_with_required_rasters(self):
        self.assertIn("create_zoning_map", TOOL_REGISTRY)
        params = schema()["parameters"]
        self.assertEqual(params["required"], ["rasters"])
        for key in ("n_zones", "min_zone_area_ha", "smooth", "seed", "output_name", "align_to_first", "resampling"):
            self.assertIn(key, params["properties"], key)

    def test_the_description_says_there_is_no_yield_or_rate_recommendation(self):
        text = schema()["description"]
        self.assertIn("NO yield forecast", text)
        self.assertIn("input-rate recommendation", text)
        self.assertIn("4 million cells", text)

    def test_it_is_classified_as_creating_a_layer_and_has_routing_keywords(self):
        self.assertEqual(tool_operations.TOOL_OPERATION_TYPES["create_zoning_map"], tool_operations.CREATE)
        self.assertIn("management zones", TOOL_KEYWORDS["create_zoning_map"])

    def test_without_qgis_it_says_so_instead_of_crashing(self):
        self.assertEqual(TOOL_REGISTRY["create_zoning_map"](["a"]), {"error": "QGIS not available"})

    def test_the_tool_name_has_no_zone_word_that_a_layer_name_would_match(self):
        """The router gives +10 for a tool-name word found in the request, and layers are often called "*_zones": a first name with the word 'zones' pushed get_layer_extent out of
        the offered tools for "zoom to the layer smoke_zones" (tests.test_tool_router_basics golden requests)."""
        words = ["create", "zoning", "map"]                 # the words of the tool name
        self.assertIn("create_zoning_map", TOOL_REGISTRY)
        for word in ("zone", "zones"):
            self.assertNotIn(word, words)

    def test_the_reply_note_and_the_legend_label(self):
        self.assertIn("not a yield forecast", tool.NOTE)
        self.assertEqual(tool.legend_label(2, [0.54], ["NDVI"]), "Zone 2: NDVI mean 0.54")
        self.assertEqual(tool.legend_label(1, [0.2345, 31.0], ["NDVI", "elev"]), "Zone 1: NDVI mean 0.234; elev mean 31")


if __name__ == "__main__":
    unittest.main()
