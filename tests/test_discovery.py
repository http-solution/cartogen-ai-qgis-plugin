# -*- coding: utf-8 -*-
"""Input discovery and data-aware chain context (pure), preflight geometry/field checks, and the turn-level injection."""
import unittest
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent import chains, discovery as d, step_runner as sr
from tests.fixtures.humanitarian_scenarios import SCEN
from tests.test_agent_runner import _make_bare_agent
from tests.test_run_steps import _Scripted, _tools, op

BOX = (44.4, 15.4, 44.6, 15.6)
FACTS = {
    "checkpoints": {"kind": "vector", "geometry": "point", "features": 12, "geographic": True, "extent_wgs84": BOX, "fields": [("id", True)]},
    "coastal_highway": {"kind": "vector", "geometry": "line", "features": 40, "geographic": True, "extent_wgs84": BOX, "fields": [("name", False)]},
    "districts": {"kind": "vector", "geometry": "polygon", "features": 5, "geographic": True, "extent_wgs84": BOX,
                  "fields": [("name", False), ("pop", True)]},
}
CHAIN = next(c for c in chains.CHAINS if c["id"] == "exclusion_zone_split")


class TestBinding(unittest.TestCase):
    def test_a_layer_named_in_the_request_wins(self):
        self.assertEqual(d.bind_slot("point", FACTS, "split the highway around the checkpoints"), ("named", ["checkpoints"]))

    def test_the_only_layer_of_the_right_kind_is_used(self):
        self.assertEqual(d.bind_slot("line", FACTS, "do the analysis"), ("only", ["coastal_highway"]))

    def test_several_candidates_are_listed_not_chosen(self):
        facts = dict(FACTS, second={"kind": "vector", "geometry": "polygon", "features": 1, "fields": []})
        status, names = d.bind_slot("polygon", facts, "do the analysis")
        self.assertEqual((status, sorted(names)), ("ambiguous", ["districts", "second"]))

    def test_no_candidate(self):
        self.assertEqual(d.bind_slot("raster", FACTS, "x"), ("none", []))

    def test_the_utm_zone_comes_from_the_layers_own_extent(self):
        self.assertEqual(d.utm_for_fact(FACTS["checkpoints"]), "EPSG:32638")
        self.assertEqual(d.utm_for_fact({"extent_wgs84": (-0.3, 51.4, -0.1, 51.6)}), "EPSG:32630")
        self.assertIsNone(d.utm_for_fact({}))


class TestContext(unittest.TestCase):
    def test_the_report_binds_slots_and_derives_the_projection(self):
        text = d.chain_context("split the highway by 5 km buffers around the checkpoints", FACTS, [CHAIN])
        self.assertIn("<points> = 'checkpoints' (point, 12 features, named in the request)", text)
        self.assertIn("<line> = 'coastal_highway'", text)
        self.assertIn("<utm> suggested EPSG:32638", text)

    def test_a_missing_input_blocks_and_says_what_to_do(self):
        only_points = {"checkpoints": FACTS["checkpoints"]}
        text = d.chain_context("split the highway by buffers around the checkpoints", only_points, [CHAIN])
        self.assertIn("NO candidate", text)
        self.assertIn("Cannot run as is", text)
        self.assertIn("instead of guessing", text)

    def test_a_non_numeric_style_field_is_flagged(self):
        clip_style = next(c for c in chains.CHAINS if c["id"] == "clip_and_style")
        facts = {"districts": FACTS["districts"], "bound": dict(FACTS["districts"], fields=[("n", False)])}
        text = d.chain_context("clip districts to bound and colour it", facts, [clip_style])
        self.assertIn("pop", text)           # the numeric candidate fields of the bound layer are listed

    def test_questions_about_method_get_no_chain(self):
        self.assertEqual(d.chain_context("How do I split a highway by buffer zones?", FACTS, [CHAIN]), "")
        self.assertFalse(d.is_execution_request("Explain how to clip a raster"))
        self.assertTrue(d.is_execution_request("Clip the raster to the district"))

    def test_no_qgis_means_no_context(self):
        self.assertEqual(d.chain_context("anything", None, [CHAIN]), "")

    def test_the_workflow_directive_drops_chains_for_questions(self):
        from cartogen_ai.core.agent import capabilities as cap
        self.assertNotIn("Known-good chain", cap.workflow_directive("How would I " + SCEN["highway"]))


class TestPreflightFacts(unittest.TestCase):
    def check(self, steps):
        return sr.preflight(steps, FACTS, op)

    def test_wrong_geometry_is_refused(self):
        msg = self.check([{"tool": "split_lines_by_zones", "arguments": {"line_layer": "districts", "zone_layer": "districts"}}])
        self.assertIn("needs a line layer", msg)

    def test_graduating_a_text_field_is_refused(self):
        steps = [{"tool": "apply_graduated_style", "arguments": {"layer_name": "districts", "field": "name"}}]
        self.assertIn("not numeric", self.check(steps))
        self.assertIsNone(self.check([{"tool": "apply_graduated_style", "arguments": {"layer_name": "districts", "field": "pop"}}]))
        self.assertIn("no field 'nope'", self.check([{"tool": "apply_graduated_style", "arguments": {"layer_name": "districts", "field": "nope"}}]))


class TestTurnInjection(unittest.TestCase):
    def test_the_system_prompt_carries_the_project_check_only_for_a_fitting_chain(self):
        class Client(_Scripted):
            def complete(self, messages, tools=None, max_tokens=None):
                self.system = messages[0]["content"]
                return super().complete(messages, tools, max_tokens)

        def run(query):
            client = Client([{"role": "assistant", "content": "ok"}])
            agent = _make_bare_agent(client)
            with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
                 patch("cartogen_ai.core.agent.discovery.gather_facts", lambda _=None: FACTS), \
                 patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
                 patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA",
                       _tools("run_steps", "reproject_layer", "buffer_analysis", "split_lines_by_zones", "get_layers")), \
                 patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
                agent.run(query)
            return client.system

        self.assertIn("Project check for chain 'exclusion_zone_split'", run(SCEN["highway"]))
        self.assertEqual(run("Show the layers"), "sys")


if __name__ == "__main__":
    unittest.main()
