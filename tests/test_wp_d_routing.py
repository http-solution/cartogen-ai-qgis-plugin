"""PLAN-021 WP-D, no QGIS needed: plain requests are not sent to a wrong task plan (#380), a loaded DEM is not turned into a fetch (the contour
row of the 1.18.0 hand run), and a repeating listing tool says why it stopped (#362 I6)."""
import csv
import unittest
from pathlib import Path

from cartogen_ai.core.agent import capabilities as cap
from cartogen_ai.core.agent import task_matcher as tm
from cartogen_ai.core.agent.loop_guard import LoopGuard, duplicate_detail
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter

ROOT = Path(__file__).resolve().parents[1]
# the prompts whose matched task is right: a duplicates task for "find duplicates" and a clean-up task for "clean the road layer"
LEGITIMATE = {"native:checkgeometryduplicate", "grass:v.clean"}


def _plain_prompts():
    with open(ROOT / "docs" / "HAND_TEST_rc46_algorithms_plain.csv", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class TestPlainRequestsAreNotSentToAWrongTask(unittest.TestCase):
    def test_no_plain_prompt_is_answered_by_a_wrong_mapping_task(self):
        """The 1.18.0 replay: 34 of 385 before the first fix, 7 after it, 5 of those a mapping task that cannot do the operation."""
        wrong = []
        for row in _plain_prompts():
            verdict = tm.classify(row["plain_prompt"])
            if verdict["best"] is not None and not verdict["ambiguous"] and row["algorithm_id"] not in LEGITIMATE:
                wrong.append((row["algorithm_id"], verdict["best"]["id"], verdict["best"].get("text")))
        self.assertEqual(wrong, [])

    def test_the_two_requests_a_task_really_describes_keep_their_task(self):
        for row in _plain_prompts():
            if row["algorithm_id"] in LEGITIMATE:
                verdict = tm.classify(row["plain_prompt"])
                self.assertIsNotNone(verdict["best"], row["algorithm_id"])
                self.assertFalse(verdict["ambiguous"], row["algorithm_id"])

    def test_the_prompts_named_in_the_issue_get_no_task_plan(self):
        for query in ("Combine the layers from the different survey teams into one layer.",
                      "Convert the districts to a raster with the population in each cell.",
                      "Turn the mesh results of the flood model into a raster map I can overlay.",
                      "sort the districts by population, biggest first"):
            verdict = tm.classify(query)
            self.assertTrue(verdict["best"] is None or verdict["ambiguous"], query)

    def test_a_mapping_request_still_gets_its_mapping_task(self):
        verdict = tm.classify("Map population distribution")
        self.assertIsNotNone(verdict["best"])
        self.assertFalse(verdict["ambiguous"])


class TestALoadedDemIsNotAFetch(unittest.TestCase):
    CONTOUR = "draw contour lines of the dem every 100"

    def test_a_bare_dem_is_not_a_download_request(self):
        self.assertNotIn("elevation_download", [c for c, _t, _v in cap.needed_capabilities(self.CONTOUR)])
        self.assertFalse(cap.is_multi_step(self.CONTOUR))
        self.assertNotIn("fetch_dem", cap.required_tools(self.CONTOUR))

    def test_the_router_offers_the_contour_tool_and_no_workflow_runner(self):
        names = {t["function"]["name"] for t in ToolRouter(TOOLS_SCHEMA).filter_relevant_tools(self.CONTOUR)}
        self.assertIn("generate_contours", names)
        self.assertNotIn("run_steps", names)

    def test_a_real_download_request_is_still_one(self):
        for query in ("get the dem for Taizz and draw contours", "download the DEM for the area", "fetch srtm for yemen", "elevation data for Sanaa"):
            self.assertIn("elevation_download", [c for c, _t, _v in cap.needed_capabilities(query)], query)

    def test_the_two_tool_descriptions_say_which_to_use(self):
        desc = {t["function"]["name"]: t["function"]["description"] for t in TOOLS_SCHEMA}
        self.assertIn("already in the project", desc["generate_contours"])
        self.assertIn("do not call this", desc["fetch_dem"])


class TestRepeatedListingSaysWhy(unittest.TestCase):
    def test_a_repeated_layout_listing_names_the_next_step(self):
        guard = LoopGuard()
        for _ in range(3):
            stop = guard.record_call("list_layout_items", {"layout_name": "Test Layout"}, False)
        self.assertEqual(stop["reason"], "duplicate_call")
        self.assertIn("add_layout_elevation_profile", stop["detail"])
        self.assertIn("add_layout_elevation_profile", guard.partial_report())

    def test_another_tool_gets_the_plain_sentence(self):
        self.assertEqual(duplicate_detail("buffer_analysis", 3), "`buffer_analysis` was called 3 times with the same arguments")


class TestTheThreeIssueRowsAreOffered(unittest.TestCase):
    def test_the_tools_each_prompt_needs_are_offered(self):
        router = ToolRouter(TOOLS_SCHEMA)
        wanted = {
            "animate the layer over time": {"export_temporal_animation_frames"},
            "Turn on elevation for the dem, then draw an elevation profile along the road in Test Layout": {"set_layer_elevation", "add_layout_elevation_profile"},
            "Produce charts linked to maps": {"add_layout_chart"},
        }
        for query, tools in wanted.items():
            names = {t["function"]["name"] for t in router.filter_relevant_tools(query)}
            self.assertLessEqual(tools, names, query)


if __name__ == "__main__":
    unittest.main()
