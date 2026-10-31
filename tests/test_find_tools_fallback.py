"""PLAN-042 step 4: find_tools uses the router's curated phrases, is always offered, and rule 56 tells the model to call it before refusing."""
import unittest

from cartogen_ai.core.agent import prompts
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools.tool_discovery import find_tools, rank_tools

OSM_AND_GEOCODERS = {"ingest_osm_features", "geocode_and_enrich", "geocode_batch"}


class TestFindToolsUsesCuratedPhrases(unittest.TestCase):
    def test_a_medical_wording_finds_the_osm_and_geocoding_tools(self):
        """Before: calculate_service_area, list_bookmarks, list_layouts (measured 2026-10-30)."""
        for query in ("list medical service in Al Maharah", "any dispensary around here", "where are the nearest pharmacies"):
            top = {name for _s, name, _d in rank_tools(query, TOOLS_SCHEMA, limit=4)}
            self.assertTrue(OSM_AND_GEOCODERS & top, f"{query!r} -> {sorted(top)}")

    def test_the_tool_returns_them_for_the_rest_of_the_turn(self):
        result = find_tools("list medical service in Al Maharah")
        self.assertTrue(OSM_AND_GEOCODERS & set(result["tool_names"]))

    def test_a_request_with_no_phrase_still_ranks_by_name_and_description(self):
        names = [n for _s, n, _d in rank_tools("reproject the layer to another coordinate system", TOOLS_SCHEMA)]
        self.assertIn("reproject_layer", names)


class TestRuleFiftySix(unittest.TestCase):
    def test_the_rule_is_core_and_names_find_tools(self):
        self.assertIn(56, prompts.CORE_RULE_NUMBERS)
        self.assertIn("find_tools", prompts._ALL_RULES[56])
        self.assertIn("BEFORE telling the user a capability is missing", prompts._ALL_RULES[56])

    def test_the_rule_is_in_the_assembled_prompt_even_for_a_small_tool_set(self):
        self.assertIn("56. The tools you were given are a selection", prompts._assemble_base_prompt({"get_layers"}))


if __name__ == "__main__":
    unittest.main()
