"""Keywords a tool declares beside its own @register_tool (PLAN-042 step 2) reach the router, stay out of the model's schema, and are not
duplicated in tool_router._TOOL_ALIASES."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS
from cartogen_ai.core.services import tool_router
from cartogen_ai.core.services.tool_router import _TOOL_ALIASES, ToolRouter


class TestToolKeywords(unittest.TestCase):
    def test_declared_keywords_belong_to_registered_tools_and_are_lower_case(self):
        registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
        self.assertTrue(TOOL_KEYWORDS, "no tool declares keywords")
        for name, words in TOOL_KEYWORDS.items():
            self.assertIn(name, registered)
            for word in words:
                self.assertEqual(word, word.lower().strip(), f"{name}: {word!r}")

    def test_a_phrase_is_declared_in_one_place_only(self):
        for name, words in TOOL_KEYWORDS.items():
            both = set(words) & set(_TOOL_ALIASES.get(name, ()))
            self.assertEqual(both, set(), f"{name} has the same phrase in tool_router._TOOL_ALIASES and in its own keywords")

    def test_keywords_are_not_sent_to_the_model(self):
        for tool in TOOLS_SCHEMA:
            self.assertEqual(set(tool), {"type", "function"})
            self.assertEqual(set(tool["function"]), {"name", "description", "parameters"})

    def test_a_declared_keyword_alone_offers_its_tool(self):
        router = ToolRouter(TOOLS_SCHEMA)
        offered = {t["function"]["name"] for t in router.filter_relevant_tools("any dispensary around here")}
        self.assertIn("ingest_osm_features", offered)

    def test_the_router_reads_the_registry_keywords(self):
        self.assertEqual(tool_router._declared_keywords("geocode_batch"), TOOL_KEYWORDS["geocode_batch"])
        self.assertEqual(tool_router._declared_keywords("no_such_tool"), ())


if __name__ == "__main__":
    unittest.main()
