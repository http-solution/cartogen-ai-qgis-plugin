"""Keywords a tool declares beside its own @register_tool (PLAN-042 step 2) reach the router, stay out of the model's schema, and are not
duplicated in tool_router._TOOL_ALIASES."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS
from cartogen_ai.core.services import tool_router
from cartogen_ai.core.services.tool_router import _TOOL_ALIASES, ToolRouter, _concepts, expand_phrases


class TestToolKeywords(unittest.TestCase):
    def test_declared_keywords_belong_to_registered_tools_and_are_lower_case(self):
        registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
        self.assertTrue(TOOL_KEYWORDS, "no tool declares keywords")
        for name, words in TOOL_KEYWORDS.items():
            self.assertIn(name, registered)
            for word in expand_phrases(words):
                self.assertEqual(word, word.lower().strip(), f"{name}: {word!r}")

    def test_a_phrase_is_declared_in_one_place_only(self):
        for name, words in TOOL_KEYWORDS.items():
            both = set(expand_phrases(words)) & set(expand_phrases(_TOOL_ALIASES.get(name, ())))
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
        self.assertEqual(tool_router._declared_keywords("geocode_batch"), expand_phrases(TOOL_KEYWORDS["geocode_batch"]))
        self.assertEqual(tool_router._declared_keywords("no_such_tool"), ())


class TestConceptGroups(unittest.TestCase):
    def test_every_concept_reference_names_a_defined_group(self):
        refs = [(n, w) for n, ws in list(TOOL_KEYWORDS.items()) + list(_TOOL_ALIASES.items()) for w in ws if w.startswith("concept:")]
        self.assertTrue(refs, "no tool uses a concept group")
        for name, ref in refs:
            self.assertIn(ref[len("concept:"):], _concepts(), f"{name} references the undefined concept {ref}")

    def test_groups_are_lower_case_non_empty_phrases(self):
        self.assertTrue(_concepts(), "routing_concepts.json did not load")
        for concept, phrases in _concepts().items():
            self.assertTrue(phrases, concept)
            for phrase in phrases:
                self.assertEqual(phrase, phrase.lower().strip(), f"{concept}: {phrase!r}")

    def test_the_health_group_reaches_all_three_tools_with_the_same_phrases(self):
        group = set(_concepts()["health_facility"])
        for name in ("geocode_and_enrich", "geocode_batch", "ingest_osm_features"):
            self.assertLessEqual(group, set(tool_router._declared_keywords(name)), name)
        self.assertEqual(expand_phrases(["concept:no_such_group", "x"]), ("x",))


if __name__ == "__main__":
    unittest.main()
