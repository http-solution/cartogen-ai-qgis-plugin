# -*- coding: utf-8 -*-
"""Capability table, router selection and task directives on the five 2026-10-09 scenarios (cost investigation)."""
import json
import unittest

from cartogen_ai.core.agent import capabilities as cap
from cartogen_ai.core.agent import task_matcher as tm
from cartogen_ai.core.agent.prompts import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter
from tests.fixtures.humanitarian_scenarios import SCEN

REGISTERED = {t["function"]["name"] for t in TOOLS_SCHEMA}


class TestTable(unittest.TestCase):
    def test_every_tool_named_in_the_table_is_registered(self):
        missing = [(cid, n) for cid, _rx, tools, via in cap._TABLE for n in (*tools, *via) if n not in REGISTERED]
        self.assertEqual(missing, [])

    def test_the_named_data_source_and_actions_are_found(self):
        self.assertIn("fetch_osm_features", cap.required_tools(SCEN["aden"]))
        self.assertIn("dissolve_layer", cap.required_tools(SCEN["aden"]))
        self.assertIn("difference_layers", cap.required_tools(SCEN["aden"]))
        self.assertIn("fetch_hdx_admin_boundaries", cap.required_tools(SCEN["districts"]))
        self.assertIn("reproject_layer", cap.required_tools(SCEN["marib"]))

    def test_steps_without_a_dedicated_tool_are_reported(self):
        # contours and the highway split now have tools; only the elevation DOWNLOAD (source not yet verified) has none
        self.assertEqual(cap.uncovered_capabilities(SCEN["taizz"]), ["elevation_download"])
        self.assertEqual(cap.uncovered_capabilities(SCEN["highway"]), [])
        self.assertIn("generate_contours", cap.required_tools(SCEN["taizz"]))
        self.assertIn("split_lines_by_zones", cap.required_tools(SCEN["highway"]))
        self.assertEqual(cap.uncovered_capabilities(SCEN["aden"]), [])

    def test_fallback_tools_are_offered_only_when_a_step_has_no_tool(self):
        self.assertIn("run_allowlisted_processing_algorithm", cap.required_tools(SCEN["taizz"]))
        self.assertNotIn("execute_pyqgis_script", cap.required_tools(SCEN["aden"]))

    def test_a_simple_request_names_few_capabilities(self):
        self.assertFalse(cap.is_multi_step("Show the severity on the map for smoke_admin"))
        self.assertTrue(all(cap.is_multi_step(q) for q in SCEN.values()))

    def test_the_geojson_word_alone_does_not_ask_for_an_export(self):
        self.assertNotIn("export", [c for c, _t, _v in cap.needed_capabilities(SCEN["districts"])])


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = ToolRouter(TOOLS_SCHEMA)

    def test_every_scenario_gets_the_tools_it_requires(self):
        for key, query in SCEN.items():
            names = {t["function"]["name"] for t in self.router.filter_relevant_tools(query, top_k=40)}
            self.assertEqual([n for n in cap.required_tools(query) if n not in names], [], key)

    def test_generic_verbs_do_not_pull_in_unrelated_tools(self):
        names = {t["function"]["name"] for t in self.router.filter_relevant_tools(SCEN["aden"], top_k=40)}
        for noise in ("generate_temporal_dashboard", "extract_pdf_tables", "extract_word_tables", "generate_situation_dashboard"):
            self.assertNotIn(noise, names)

    def test_find_tools_is_offered_when_a_step_has_no_tool(self):
        names = {t["function"]["name"] for t in self.router.filter_relevant_tools(SCEN["taizz"], top_k=40)}
        self.assertIn("find_tools", names)
        simple = {t["function"]["name"] for t in self.router.filter_relevant_tools("buffer the hospitals by 500 m", top_k=40)}
        self.assertNotIn("find_tools", simple)

    def test_tool_schemas_sent_stay_in_the_measured_range(self):
        for key, query in SCEN.items():
            tokens = len(json.dumps(self.router.filter_relevant_tools(query, top_k=40))) // 4
            self.assertLess(tokens, 20000, key)        # a ceiling from the measured ~15-17k; a jump means the router regressed


class TestDirectives(unittest.TestCase):
    def test_osm_requests_lead_with_the_fetch_tools_and_end_with_the_file_loader(self):
        entry, _s = tm.match(SCEN["marib"], limit=1)[0]
        directive = tm.task_directive(entry, query=SCEN["marib"])
        chain = directive.split("in order: ")[1].rstrip(".").split(", ")
        self.assertEqual(chain[0], "fetch_osm_features")
        self.assertEqual(chain[-1], "add_layer_from_path")

    def test_a_named_file_keeps_the_loader_where_it_was(self):
        self.assertEqual(cap.lead_tools_for_task(["add_layer_from_path", "zoom_to_layer"], "load roads.gpkg"),
                         ["add_layer_from_path", "zoom_to_layer"])

    def test_a_workflow_directive_lists_the_steps_in_the_requests_order_and_the_gaps(self):
        text = cap.workflow_directive(SCEN["taizz"])
        self.assertIn("multi-step workflow", text)
        self.assertLess(text.index("buffer"), text.index("slope"))
        self.assertIn("elevation (DEM) download: no dedicated tool", text)
        self.assertIn("contour lines: generate_contours", text)
        self.assertIn("never report the whole request as complete", text)


class TestFindTools(unittest.TestCase):
    def test_it_ranks_by_name_and_description(self):
        from cartogen_ai.core.agent.tools.tool_discovery import find_tools
        result = find_tools("slope from a DEM")
        self.assertTrue(result["success"])
        self.assertIn("slope_analysis", result["tool_names"])
        self.assertNotIn("find_tools", result["tool_names"])

    def test_nothing_matching_says_so_instead_of_inventing(self):
        from cartogen_ai.core.agent.tools.tool_discovery import find_tools
        result = find_tools("zzzzqq xxyyzz")
        self.assertEqual(result["tools"], [])
        self.assertIn("last resort", result["note"])

    def test_the_agent_loop_offers_the_found_tools_on_the_next_call(self):
        from unittest.mock import patch
        from cartogen_ai.core.agent.agent_orchestrator import CartogenAi
        seen = []
        calls = [("find_tools", '{"need": "slope from a DEM"}'), (None, None)]

        class Client:
            model = "fake"

            def complete(self, messages, tools=None, max_tokens=None):
                seen.append({t["function"]["name"] for t in tools})
                name, args = calls.pop(0)
                if name is None:
                    return {"message": {"role": "assistant", "content": "done", "tool_calls": None}, "model": "fake"}
                return {"message": {"role": "assistant", "content": None,
                                    "tool_calls": [{"id": "1", "function": {"name": name, "arguments": args}}]}, "model": "fake"}

        agent = CartogenAi()
        agent.conversation_history = []
        agent.client = Client()
        from cartogen_ai.core.agent.tools import TOOL_REGISTRY
        agent._execute_tool = lambda name, args: TOOL_REGISTRY[name](**json.loads(args))      # no QGIS main thread offline
        with patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
            agent.run("draw contour lines")      # a step with no dedicated tool: find_tools is offered, slope_analysis is not
        self.assertNotIn("slope_analysis", seen[0])
        self.assertIn("slope_analysis", seen[1])


if __name__ == "__main__":
    unittest.main()
