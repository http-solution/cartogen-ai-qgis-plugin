# -*- coding: utf-8 -*-
"""Pre-built run_steps chains: each skeleton must pass run_steps' own validation against the REAL registered tool schemas, chains are
selected only when the request names all their steps, and the router offers the chain's tools."""
import json
import unittest

from cartogen_ai.core.agent import capabilities as cap, chains, tool_operations
from cartogen_ai.core.agent.prompts import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter
from tests.fixtures.humanitarian_scenarios import SCEN

SCHEMAS = {t["function"]["name"]: t["function"]["parameters"] for t in TOOLS_SCHEMA}


class TestChains(unittest.TestCase):
    def test_every_chain_is_valid_against_the_real_schemas(self):
        for chain in chains.CHAINS:
            self.assertIsNone(chains.validate_chain(chain, SCHEMAS, tool_operations.get_tool_operation_type), chain["id"])

    def test_every_slot_is_used_and_every_placeholder_is_a_declared_slot(self):
        for chain in chains.CHAINS:
            text = chains.skeleton_json(chain)
            used = {w.strip("<>") for w in __import__("re").findall(r"<[a-z0-9_]+>", text)}
            self.assertEqual(used, set(chain["slots"]), chain["id"])

    def test_chain_needs_are_real_capability_ids(self):
        ids = {row[0] for row in cap._TABLE}
        for chain in chains.CHAINS:
            self.assertTrue(set(chain["needs"]) <= ids, chain["id"])

    def test_selection_follows_the_named_steps(self):
        self.assertEqual([c["id"] for c in chains.chains_for([i for i, _t, _v in cap.needed_capabilities(SCEN["highway"])])],
                         ["exclusion_zone_split"])
        self.assertEqual([c["id"] for c in chains.chains_for([i for i, _t, _v in cap.needed_capabilities(SCEN["taizz"])])],
                         ["terrain_contours", "terrain_slope"])
        self.assertEqual(chains.chains_for([i for i, _t, _v in cap.needed_capabilities(SCEN["districts"])]), [])
        self.assertEqual(chains.chains_for(["buffer"]), [])
        self.assertEqual([c["id"] for c in chains.chains_for(["population_data"])], ["population_exposure"])
        self.assertEqual([c["id"] for c in chains.chains_for(["hdx_boundaries", "pcode_check"])], ["admin_boundary_validation"])
        # the Aden coverage-gap request fits buffer+difference too, but the more specific chain replaces it
        self.assertEqual([c["id"] for c in chains.chains_for([i for i, _t, _v in cap.needed_capabilities(SCEN["aden"])])],
                         ["coverage_gap"])

    def test_the_directive_carries_a_parseable_skeleton(self):
        text = cap.workflow_directive(SCEN["highway"])
        self.assertIn("Known-good chain", text)
        start = text.index('{"steps"')
        depth = 0
        for i, ch in enumerate(text[start:], start):
            depth += (ch == "{") - (ch == "}")
            if depth == 0:
                break
        self.assertEqual(len(json.loads(text[start:i + 1])["steps"]), 3)
        self.assertNotIn("Known-good chain", cap.workflow_directive(SCEN["districts"]))

    def test_the_router_offers_the_chains_tools(self):
        names = {t["function"]["name"] for t in ToolRouter(TOOLS_SCHEMA).filter_relevant_tools(SCEN["highway"])}
        for needed in ("run_steps", "reproject_layer", "buffer_analysis", "split_lines_by_zones"):
            self.assertIn(needed, names)


if __name__ == "__main__":
    unittest.main()


class TestPlainRequests(unittest.TestCase):
    def test_short_requests_are_recognised_and_carry_the_chain(self):
        q = "Download the HDX admin2 boundaries for Yemen and check the P-codes are unique and nested correctly"
        self.assertTrue(cap.is_multi_step(q))
        self.assertIn("check_pcode_uniqueness", cap.workflow_directive(q))
        q2 = "How many people live in each district? Use WorldPop for Yemen"
        self.assertIn("estimate_population_exposure", cap.workflow_directive(q2))

    def test_the_coverage_gap_chain_states_its_limits(self):
        self.assertIn("straight-line distance gap only", cap.workflow_directive(SCEN["aden"]))

    def test_a_simple_request_is_still_not_a_workflow(self):
        self.assertFalse(cap.is_multi_step("Show the severity on the map for smoke_admin"))
