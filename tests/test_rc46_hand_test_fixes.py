"""Regression tests for the defects found by the rc46 hand test (checkpoint 2026-10-18)."""
import unittest
from unittest import mock

from cartogen_ai.core.agent import task_matcher as tm
from cartogen_ai.core.agent.tools.registry import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter


def _offered(query):
    return {t["function"]["name"] for t in ToolRouter(TOOLS_SCHEMA).filter_relevant_tools(query)}


class TestRc46HandTestFixes(unittest.TestCase):
    def test_set_project_crs_is_not_a_fragment(self):
        self.assertFalse(tm._is_non_request_fragment("Set the project CRS to EPSG:3857."))

    def test_pasted_key_value_is_still_a_fragment(self):
        self.assertTrue(tm._is_non_request_fragment("template: access_map"))

    def test_reading_metadata_has_no_task(self):
        self.assertEqual(tm.classify("Show the metadata of towns.")["reason"], "reads layer metadata")

    def test_creating_metadata_still_matches_a_task(self):
        self.assertNotEqual(tm.classify("Create metadata for the districts layer")["reason"], "reads layer metadata")

    def test_raster_expression_offers_raster_calculator(self):
        self.assertIn("raster_calculator", _offered("Calculate dem@1 > 100 as a new layer called high_ground."))

    def test_metadata_read_offers_get_layer_metadata(self):
        self.assertIn("get_layer_metadata", _offered("Show the metadata of towns."))

    def test_tidy_scan_skips_layers_without_feature_count(self):
        from cartogen_ai.core.agent.tools import project_tidy_tools as pt

        class VectorTile:  # no bandCount, no featureCount: the rc46 crash
            def id(self): return "vt"

        class Node:
            def layer(self): return VectorTile()

        class Root:
            def findLayers(self): return [Node()]

        class Project:
            def layerTreeRoot(self): return Root()

        scan = pt._entries
        with mock.patch.object(pt, "QGIS_AVAILABLE", True, create=True):
            self.assertEqual(scan(Project()), [])


if __name__ == "__main__":
    unittest.main()



class TestHandTestToolPromptsRouteOffline(unittest.TestCase):
    """Replays every prompt of the tool hand test through the router and the task matcher with no model and no QGIS. It would have caught
    three of the rc46 defects (set_project_crs fragment, get_layer_metadata task misroute, raster_calculator not offered) before the
    tester spent API credit on them. A row passes when the named tool is offered, the prompt is not dismissed as a fragment, and
    any confident task directive actually lists that tool."""

    def test_every_tool_row_routes(self):
        import csv
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "docs" / "HAND_TEST_rc44_tools.csv"
        if not path.exists():
            self.skipTest("tool sheet CSV not present")
        names = {t["function"]["name"] for t in TOOLS_SCHEMA}
        router = ToolRouter(TOOLS_SCHEMA)
        problems = []
        for row in csv.DictReader(path.open(encoding="utf-8-sig")):
            tool, prompt = row["tool"].split(" ")[0], row["prompt"]
            if tool not in names or "<" in prompt:
                continue
            offered = {t["function"]["name"] for t in router.filter_relevant_tools(prompt)}
            verdict = tm.classify(prompt)
            if tool not in offered:
                problems.append(f"{tool}: not offered for {prompt!r}")
            if verdict["reason"] == "too short to be a request":
                problems.append(f"{tool}: treated as a fragment: {prompt!r}")
            best = verdict.get("best")
            if best and not verdict["ambiguous"] and tool not in best.get("tools", []):
                problems.append(f"{tool}: task {best['id']} {best['text']!r} would steer away from it: {prompt!r}")
        self.assertEqual(problems, [])


class TestPart4Wording(unittest.TestCase):
    def test_animate_and_produce_are_requests(self):
        for q in ("animate the layer over time", "Produce charts linked to maps"):
            self.assertFalse(tm._is_non_request_fragment(q), q)

    def test_linked_charts_offer_layout_chart(self):
        self.assertIn("add_layout_chart", _offered("Produce charts linked to maps"))
