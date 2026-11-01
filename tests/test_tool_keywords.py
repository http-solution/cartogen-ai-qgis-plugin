"""Keywords a tool declares beside its own @register_tool (PLAN-042 step 2) reach the router, stay out of the model's schema, and are not
duplicated in tool_router._TOOL_ALIASES."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools.registry import TOOL_KEYWORDS
from cartogen_ai.core.services import tool_router
from cartogen_ai.core.services.tool_router import _TOOL_ALIASES, ToolRouter, _concepts, expand_phrases, fold


class TestToolKeywords(unittest.TestCase):
    def test_declared_keywords_belong_to_registered_tools_and_are_lower_case(self):
        registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
        self.assertTrue(TOOL_KEYWORDS, "no tool declares keywords")
        for name, words in TOOL_KEYWORDS.items():
            self.assertIn(name, registered)
            for word in expand_phrases(words):
                # lower-case only: a deliberate leading or trailing space (" is over ") makes the phrase match whole words
                self.assertEqual(word, word.lower(), f"{name}: {word!r}")
                self.assertTrue(word.strip(), f"{name}: an empty phrase")

    def test_a_phrase_is_declared_in_one_place_only(self):
        for name, words in TOOL_KEYWORDS.items():
            both = set(expand_phrases(words)) & set(expand_phrases(_TOOL_ALIASES.get(name, ())))
            self.assertEqual(both, set(), f"{name} has the same phrase in tool_router._TOOL_ALIASES and in its own keywords")

    def test_no_tool_is_registered_twice(self):
        """The registry keeps one keyword tuple per name, so a second registration of the same name would silently replace the first's
        phrases (the same mistake the old duplicate-key test guarded in the central dict)."""
        names = [t["function"]["name"] for t in TOOLS_SCHEMA]
        self.assertEqual(sorted({n for n in names if names.count(n) > 1}), [])

    def test_the_curated_phrase_count_has_not_shrunk(self):
        total = sum(len(tool_router.routing_phrases(n)) for n in tool_router.routing_phrase_tools())
        self.assertGreaterEqual(total, 2105)   # the count when the central dict was moved into the tools; raise it, never lower it

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


class TestLanguagePhrases(unittest.TestCase):
    """ML-1: Arabic and French phrases for the top tools (core/services/routing_languages.json), matched after folding accents and Arabic spellings."""

    @classmethod
    def setUpClass(cls):
        import json
        path = tool_router._LANGUAGES_PATH
        with open(path, encoding="utf-8") as handle:
            cls.table = json.load(handle)

    def test_both_languages_are_present_and_cover_the_same_tools(self):
        self.assertEqual(set(self.table), {"ar", "fr"})
        self.assertEqual(set(self.table["ar"]), set(self.table["fr"]))
        self.assertGreaterEqual(len(self.table["ar"]), 90)

    def test_every_tool_is_registered_and_every_phrase_is_long_enough_once_folded(self):
        registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
        for lang, tools in self.table.items():
            for name, phrases in tools.items():
                self.assertIn(name, registered, f"{lang}: {name}")
                self.assertTrue(phrases, f"{lang}: {name}")
                for phrase in phrases:
                    # a 2-letter Arabic root would match inside unrelated words
                    self.assertGreaterEqual(len(fold(phrase).strip()), 3, f"{lang} {name}: {phrase!r}")

    def test_arabic_phrases_are_arabic_and_french_phrases_are_not(self):
        arabic = lambda text: any("\u0600" <= c <= "\u06ff" for c in text)   # noqa: E731
        for phrases in self.table["ar"].values():
            for phrase in phrases:
                self.assertTrue(arabic(phrase) or phrase.isascii(), phrase)   # 'csv' and 'pdf' stay Latin inside Arabic phrases
        for phrases in self.table["fr"].values():
            for phrase in phrases:
                self.assertFalse(arabic(phrase), phrase)

    def test_folding_makes_spelling_variants_meet(self):
        self.assertEqual(fold("أين"), fold("اين"))
        self.assertEqual(fold("مستشفى"), fold("مستشفي"))
        self.assertEqual(fold("المنطقة"), fold("المنطقه"))
        self.assertEqual(fold("Hôpitaux"), fold("hopitaux"))
        self.assertEqual(fold("English text stays"), "english text stays")

    def test_the_language_phrases_reach_the_merged_phrase_list(self):
        self.assertIn("masquer la couche", tool_router.routing_phrases("toggle_visibility"))
        self.assertIn("calculate_area", tool_router.routing_phrase_tools())

    def test_an_arabic_or_french_request_is_offered_its_tool_and_english_is_unchanged(self):
        router = ToolRouter(TOOLS_SCHEMA)
        for query, need in (("اعرض المستشفيات في تعز", "ingest_osm_features"), ("Montre les hôpitaux à Taïz", "ingest_osm_features"),
                            ("هل هناك زلازل اليوم", "fetch_usgs_earthquakes"), ("masquer la couche des routes", "toggle_visibility")):
            self.assertIn(need, {t["function"]["name"] for t in router.filter_relevant_tools(query)}, query)


if __name__ == "__main__":
    unittest.main()
