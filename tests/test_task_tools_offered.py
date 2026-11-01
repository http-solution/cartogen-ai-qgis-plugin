"""A recognised task's prescribed tools are always offered to the model.

Why: in the owner's second Taiz run (2026-11-01) the task directive said "Prefer these tools, in order: fetch_osm_features,
add_layer_from_path, apply_categorized_style, zoom_to_layer", yet none of the four was in the first call's tool list (it held
ingest_osm_features instead), so the model improvised and spent extra find_tools rounds."""
import unittest

from cartogen_ai.core.agent import task_matcher
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter

TAIZ = ("Show me all the hospitals and clinics in Taiz governorate, count how many fall inside each district, colour the districts by that "
        "count and put the result on a printable map with a legend")


class TestTaskToolsOffered(unittest.TestCase):
    def test_taiz_request_is_offered_the_tools_its_task_names(self):
        best = task_matcher.classify(TAIZ)["best"]
        self.assertEqual(best["id"], "6.02")
        offered = {t["function"]["name"] for t in ToolRouter(TOOLS_SCHEMA).filter_relevant_tools(TAIZ)}
        self.assertLessEqual(set(best["tools"]), offered)

    def test_an_unrelated_request_is_not_widened(self):
        offered = {t["function"]["name"] for t in ToolRouter(TOOLS_SCHEMA).filter_relevant_tools("hi")}
        self.assertNotIn("fetch_osm_features", offered)


if __name__ == "__main__":
    unittest.main()
