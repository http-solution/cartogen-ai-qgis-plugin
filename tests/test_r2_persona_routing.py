"""PLAN-023 R2-6: twelve plain-language requests, each in the words of the persona that would ask, must reach the right R2 tool among the ten most relevant tools the router offers. 'Most relevant' means after the eight
tools that are offered on every request (the core planning and memory tools, which score 1000 whatever is asked). Offline, no QGIS: it runs the real router over the real tool list."""
import unittest

from cartogen_ai.core import personas as pp
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter

CORE = {"get_layers", "get_attributes", "create_plan", "update_task", "set_task_preview", "store_project_memory", "store_global_memory", "generate_spatial_report"}
M, G, K, R, L = "calculate_spatial_autocorrelation", "analyze_hotspots_gi_star", "detect_spatial_clusters", "calculate_health_rates", "apply_public_health_look"
PROMPTS = [
    ("public_health", "Is this cluster of cases real or just chance?", {K}),
    ("public_health", "Are cases more concentrated in some districts than a random pattern would give?", {M}),
    ("public_health", "Find the statistically significant hot spots of cases by district", {G}),
    ("public_health", "What is the rate per 100,000 and the relative risk in each district?", {R}),
    ("public_health", "Colour the district rates and hatch the ones with fewer than 5 cases", {L}),
    ("public_safety", "Is the clustering of incidents statistically significant?", {G, K, M}),
    ("public_safety", "Run a hotspot test on the burglary counts by neighbourhood", {G}),
    ("humanitarian", "We have an outbreak in the camps, is there a cluster of cases?", {K}),
    ("urban_planning", "Are vacant buildings clustered across neighbourhoods?", {M, G}),
    ("environment", "Where are the significantly high pollution readings?", {G}),
    ("real_estate", "Are high prices clustered in particular areas?", {M, G}),
    ("public_health", "Make an epidemic bulletin PDF for last week's cases", {"create_print_layout"}),
]


class TestPlainRequestsReachTheRightTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = ToolRouter(TOOLS_SCHEMA)

    def ranked(self, prompt, persona):
        names = [t["function"]["name"] for t in self.router.filter_relevant_tools(prompt, personas=(persona, None))]
        return [n for n in names if n not in CORE]

    def test_every_request_reaches_one_of_its_tools_in_the_top_ten(self):
        for persona, prompt, wanted in PROMPTS:
            top = self.ranked(prompt, persona)[:10]
            self.assertTrue(wanted & set(top), f"{persona}: {prompt!r} -> {top}")

    def test_the_twelve_requests_cover_all_four_r2_analysis_tools_and_the_look(self):
        covered = set().union(*(w for _p, _q, w in PROMPTS))
        self.assertTrue({M, G, K, R, L} <= covered)

    def test_every_persona_named_here_exists_and_lists_the_tools_it_asks_for(self):
        for persona, _prompt, wanted in PROMPTS:
            data = pp.get(persona)
            self.assertIsNotNone(data, persona)
            named = set(data["tool_priority"]) | set(data["tool_aliases"]) | {t for w in data["workflows"] for t in w["tools"]}
            self.assertTrue(wanted & named, f"{persona} names none of {wanted}")


if __name__ == "__main__":
    unittest.main()
