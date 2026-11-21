"""LR-25: the router's per-tool caches must change speed, never answers."""
import re
import unittest
from unittest.mock import patch

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services import tool_router as tr


class TestRouterCaches(unittest.TestCase):
    def test_cached_description_words_equal_a_fresh_split(self):
        for tool in TOOLS_SCHEMA:
            desc = tool["function"].get("description", "")
            self.assertEqual(tr._description_words(desc), frozenset(re.findall(r"\w+", desc)), tool["function"]["name"])

    def test_folded_phrases_equal_folding_the_routing_phrases_for_every_tool(self):
        for tool in TOOLS_SCHEMA:
            name = tool["function"]["name"]
            self.assertEqual(tr._folded_routing_phrases(name), tuple(tr.fold(p) for p in tr.routing_phrases(name)), name)

    def test_changing_the_aliases_of_a_tool_is_seen_not_served_from_the_cache(self):
        name = "generate_chart"
        before = tr._folded_routing_phrases(name)
        extra = dict(tr._TOOL_ALIASES)
        extra[name] = (*extra.get(name, ()), "zzz brand new alias")
        with patch.object(tr, "_TOOL_ALIASES", extra):
            self.assertIn("zzz brand new alias", tr._folded_routing_phrases(name))
        self.assertEqual(tr._folded_routing_phrases(name), before)

    def test_the_selection_is_what_it_was_for_a_few_plain_requests(self):
        router = tr.ToolRouter(TOOLS_SCHEMA)
        for query in ("bar chart of cases per district", "buffer the hospitals by 500 m", "zoom to the roads layer"):
            first = [t["function"]["name"] for t in router.filter_relevant_tools(query)]
            second = [t["function"]["name"] for t in router.filter_relevant_tools(query)]
            self.assertEqual(first, second, query)         # a warm cache gives the same list as a cold one


if __name__ == "__main__":
    unittest.main()
