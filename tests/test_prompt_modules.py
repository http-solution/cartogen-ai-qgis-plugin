# -*- coding: utf-8 -*-
"""
Coverage for agent/prompts.py's rule modularization (2026-09-12) -- the 47-rule,
~7,830-token base prompt used to always be sent in full regardless of what the turn actually
needs (the same always-everything shape the tool router had before v1.13.1 fixed it). See
prompts.py's own module docstring for the full design: CORE rules always included, a
hand-verified SENSITIVE cluster (protection-sensitive data, anti-fabrication for security
content, export sensitivity checks) triggered by a deliberately wide tool list, and the
remaining domain rules auto-triggered by tool names their own text already mentions.
"""
import unittest
from cartogen_ai.core.agent import prompts


class TestFullPromptUnchangedWhenNoToolNamesGiven(unittest.TestCase):
    """active_tool_names=None (the default) must reproduce this file's pre-modularization
    behavior exactly -- the safe fallback for any caller that doesn't pass the new parameter."""

    def test_none_matches_base_system_prompt_exactly(self):
        assembled = prompts._assemble_base_prompt(None)
        self.assertEqual(assembled, prompts.BASE_SYSTEM_PROMPT)

    def test_base_system_prompt_contains_the_exact_text_of_all_rules(self):
        for n in prompts._ALL_RULES:
            self.assertIn(prompts._ALL_RULES[n].strip(), prompts.BASE_SYSTEM_PROMPT)


class TestCoreRulesAlwaysIncluded(unittest.TestCase):
    def test_core_rules_present_even_with_no_active_tools(self):
        assembled = prompts._assemble_base_prompt(set())
        for n in prompts.CORE_RULE_NUMBERS:
            self.assertIn(prompts._ALL_RULES[n].strip(), assembled)

    def test_core_rules_present_regardless_of_which_tools_are_active(self):
        assembled = prompts._assemble_base_prompt({"buffer_analysis"})
        for n in prompts.CORE_RULE_NUMBERS:
            self.assertIn(prompts._ALL_RULES[n].strip(), assembled)


class TestSensitiveClusterTriggering(unittest.TestCase):
    def test_included_when_an_export_tool_is_active(self):
        assembled = prompts._assemble_base_prompt({"create_print_layout"})
        for n in prompts.SENSITIVE_RULE_NUMBERS:
            self.assertIn(prompts._ALL_RULES[n].strip(), assembled)

    def test_included_when_an_incident_tool_is_active(self):
        assembled = prompts._assemble_base_prompt({"add_incident_point"})
        for n in prompts.SENSITIVE_RULE_NUMBERS:
            self.assertIn(prompts._ALL_RULES[n].strip(), assembled)

    def test_included_when_a_humanitarian_logistics_tool_is_active(self):
        assembled = prompts._assemble_base_prompt({"calculate_service_area"})
        for n in prompts.SENSITIVE_RULE_NUMBERS:
            self.assertIn(prompts._ALL_RULES[n].strip(), assembled)

    def test_not_included_for_an_unrelated_tool(self):
        assembled = prompts._assemble_base_prompt({"apply_raster_stretch"})
        for n in prompts.SENSITIVE_RULE_NUMBERS:
            self.assertNotIn(prompts._ALL_RULES[n].strip(), assembled)

    def test_rule_42_anti_fabrication_specifically_present_when_triggered(self):
        # Rule 42 exists because of a real, cited incident (a fabricated Beirut security
        # briefing) -- confirm it specifically, not just "some sensitive rule".
        assembled = prompts._assemble_base_prompt({"generate_report"})
        self.assertIn("NEVER invent specific real-world security incidents", assembled)


class TestDomainRuleAutoTriggering(unittest.TestCase):
    def test_print_layout_rule_included_only_when_its_tool_is_active(self):
        with_tool = prompts._assemble_base_prompt({"create_print_layout"})
        without_tool = prompts._assemble_base_prompt({"buffer_analysis"})
        self.assertIn(prompts._ALL_RULES[30].strip(), with_tool)
        self.assertNotIn(prompts._ALL_RULES[30].strip(), without_tool)

    def test_imagery_rule_included_only_when_extraction_tool_is_active(self):
        with_tool = prompts._assemble_base_prompt({"extract_features_from_imagery"})
        without_tool = prompts._assemble_base_prompt({"buffer_analysis"})
        self.assertIn(prompts._ALL_RULES[34].strip(), with_tool)
        self.assertNotIn(prompts._ALL_RULES[34].strip(), without_tool)

    def test_workflow_rules_31_and_32_both_included_together(self):
        # Rule 32 has no tool mention of its own -- manually paired with rule 31's trigger set.
        assembled = prompts._assemble_base_prompt({"schedule_recurring_workflow"})
        self.assertIn(prompts._ALL_RULES[31].strip(), assembled)
        self.assertIn(prompts._ALL_RULES[32].strip(), assembled)

    def test_a_request_with_only_a_generic_tool_stays_small(self):
        # buffer_analysis isn't mentioned by name in any domain rule's own text and isn't in
        # the hand-verified sensitive cluster trigger list either -- only core should show up.
        assembled = prompts._assemble_base_prompt({"buffer_analysis"})
        for n in prompts.SENSITIVE_RULE_NUMBERS:
            self.assertNotIn(prompts._ALL_RULES[n].strip(), assembled)
        self.assertLess(len(assembled), len(prompts.BASE_SYSTEM_PROMPT) * 0.6)

    def test_execute_pyqgis_script_alone_does_not_spuriously_trigger_other_rules(self):
        # Real bug found live: execute_pyqgis_script is the router's guaranteed no-signal
        # fallback tool (ToolRouter's nothing_else_matched path), present even for a plain "hi"
        # -- rule 30 (print-layout composition) mentions it in its own text ("...via
        # execute_pyqgis_script") and was firing on every no-signal query purely because of
        # that shared mention, nothing to do with print layouts actually being relevant.
        assembled = prompts._assemble_base_prompt({"execute_pyqgis_script"})
        self.assertNotIn(prompts._ALL_RULES[30].strip(), assembled)
        self.assertNotIn(prompts._ALL_RULES[13].strip(), assembled)
        self.assertNotIn(prompts._ALL_RULES[21].strip(), assembled)

    def test_rule_8_with_no_real_trigger_tool_falls_back_to_always_on(self):
        # rule 8's only tool mention (generate_spatial_report) is itself router-guaranteed, so
        # after excluding always-guaranteed tools its trigger set is empty -- must default to
        # always-on rather than silently vanishing, same policy as "no tool mentioned at all".
        assembled = prompts._assemble_base_prompt({"buffer_analysis"})
        self.assertIn(prompts._ALL_RULES[8].strip(), assembled)


class TestRule48LiveHazardIntentRecognition(unittest.TestCase):
    """Rule 48 (added 2026-09-13, live user report: 'show live incident in jordan... natural,
    crime, hazard' got a blanket refusal even though fetch_nasa_eonet_events was an available
    tool for that turn) -- confirms the new rule is domain-tier (not core/sensitive) and is
    correctly auto-triggered by exactly the 3 hazard-monitoring tools it names."""

    def test_rule_48_not_core(self):
        self.assertNotIn(48, prompts.CORE_RULE_NUMBERS)

    def test_rule_48_not_sensitive(self):
        self.assertNotIn(48, prompts.SENSITIVE_RULE_NUMBERS)

    def test_rule_48_excluded_for_an_unrelated_tool(self):
        assembled = prompts._assemble_base_prompt({"buffer_analysis"})
        self.assertNotIn(prompts._ALL_RULES[48].strip(), assembled)

    def test_rule_48_included_for_each_of_its_three_trigger_tools(self):
        for tool_name in (
            "fetch_gdacs_disaster_alerts",
            "fetch_nasa_eonet_events",
            "fetch_nasa_active_fires",
        ):
            assembled = prompts._assemble_base_prompt({tool_name})
            self.assertIn(
                prompts._ALL_RULES[48].strip(), assembled,
                f"rule 48 should be included when {tool_name} is active",
            )

    def test_rule_48_trigger_tools_are_exactly_the_three_hazard_tools(self):
        self.assertEqual(
            prompts._DOMAIN_RULE_TRIGGER_TOOLS.get(48),
            {"fetch_gdacs_disaster_alerts", "fetch_nasa_eonet_events", "fetch_nasa_active_fires"},
        )


class TestBuildSystemPromptIntegration(unittest.TestCase):
    def test_active_tool_names_none_matches_full_prompt(self):
        prompt = prompts.build_system_prompt()
        self.assertIn(prompts.BASE_SYSTEM_PROMPT, prompt)

    def test_active_tool_names_trims_the_prompt_for_a_narrow_request(self):
        full = prompts.build_system_prompt()
        trimmed = prompts.build_system_prompt(active_tool_names={"get_layers"})
        self.assertLess(len(trimmed), len(full))

    def test_active_tool_names_still_includes_sensitive_cluster_when_relevant(self):
        prompt = prompts.build_system_prompt(active_tool_names={"export_to_csv", "get_layers"})
        self.assertIn("NEVER invent specific real-world security incidents", prompt)


class TestRule5NarrowingWhenMapContextHasFields(unittest.TestCase):
    """Phase 6 (2026-09-19, cost/performance pass): rule 5 used to unconditionally direct the
    model to call get_attributes(layer_name) before any query/selection op, even when the
    turn's own CURRENT MAP CONTEXT block (map_context.py) already lists that exact layer's
    field names. Narrowed the same way rule 4 already handles get_layers() -- only when
    map_context actually carries field data for at least one layer."""

    def test_no_map_context_keeps_the_original_unconditional_rule_5(self):
        prompt = prompts.build_system_prompt(map_context=None)
        self.assertIn(prompts._ALL_RULES[5].strip(), prompt)

    def test_map_context_with_no_field_data_keeps_the_original_rule_5(self):
        # A raster-only project: layers present, but no 'fields' (rasters have none) --
        # must behave identically to no map_context at all, not silently relax rule 5.
        map_context = {"layers": [{"name": "dem.tif", "fields": []}]}
        prompt = prompts.build_system_prompt(map_context=map_context)
        self.assertIn(prompts._ALL_RULES[5].strip(), prompt)

    def test_map_context_with_field_data_relaxes_rule_5(self):
        map_context = {"layers": [{"name": "roads", "fields": ["osm_id", "highway"]}]}
        prompt = prompts.build_system_prompt(map_context=map_context)
        self.assertNotIn(prompts._ALL_RULES[5].strip(), prompt)
        self.assertIn("already listed under CURRENT MAP", prompt)
        self.assertIn("get_attributes", prompt)

    def test_rule_5_override_does_not_change_base_system_prompt(self):
        # BASE_SYSTEM_PROMPT is the cached, unfiltered assembly other code relies on staying
        # exactly the full rule set -- confirms the new rule_overrides parameter is opt-in,
        # not a change to _assemble_base_prompt's default behavior.
        self.assertIn(prompts._ALL_RULES[5], prompts.BASE_SYSTEM_PROMPT)


class TestProjectInspectorContext(unittest.TestCase):
    """§1.5 option (b): _format_project_inspector + build_system_prompt's
    project_inspector_ctx parameter. Feature-flagging itself lives in the caller
    (agent_orchestrator.py) -- here, passing a context (or not) is the only signal this
    layer cares about, matching map_context's own tested shape."""

    def test_none_produces_no_project_inspector_section(self):
        prompt = prompts.build_system_prompt(project_inspector_ctx=None)
        self.assertNotIn("PROJECT INSPECTOR", prompt)

    def test_empty_dict_produces_no_project_inspector_section(self):
        prompt = prompts.build_system_prompt(project_inspector_ctx={})
        self.assertNotIn("PROJECT INSPECTOR", prompt)

    def test_layouts_and_themes_appear_in_the_prompt(self):
        ctx = {"layouts": ["Sitrep A3"], "themes": ["overview"], "metadata": {}}
        prompt = prompts.build_system_prompt(project_inspector_ctx=ctx)
        self.assertIn("PROJECT INSPECTOR", prompt)
        self.assertIn("Sitrep A3", prompt)
        self.assertIn("overview", prompt)

    def test_metadata_fields_appear_in_the_prompt(self):
        ctx = {
            "layouts": [], "themes": [],
            "metadata": {"title": "Flood Response", "abstract": "2026 flood analysis",
                         "author": "Alaa", "keywords": {"theme": ["flood"]}},
        }
        prompt = prompts.build_system_prompt(project_inspector_ctx=ctx)
        self.assertIn("Flood Response", prompt)
        self.assertIn("2026 flood analysis", prompt)
        self.assertIn("Alaa", prompt)
        self.assertIn("theme: flood", prompt)

    def test_truncated_layouts_are_flagged(self):
        ctx = {"layouts": ["A", "B"], "layouts_truncated": True, "themes": [], "metadata": {}}
        prompt = prompts.build_system_prompt(project_inspector_ctx=ctx)
        self.assertIn("(truncated)", prompt)

    def test_coexists_with_map_context_in_the_same_prompt(self):
        map_context = {"layers": [{"name": "roads", "fields": []}], "layer_count": 1}
        inspector_ctx = {"layouts": ["Sitrep A3"], "themes": [], "metadata": {}}
        prompt = prompts.build_system_prompt(map_context=map_context, project_inspector_ctx=inspector_ctx)
        self.assertIn("CURRENT MAP CONTEXT", prompt)
        self.assertIn("PROJECT INSPECTOR", prompt)
