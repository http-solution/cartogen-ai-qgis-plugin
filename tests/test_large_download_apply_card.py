"""RM-C option B (owner, 2026-11-23): a large download is confirmed by the person on an Apply card, never by the model.

Before: geoBoundaries, HDX boundaries and building footprints told the MODEL to ask in chat and re-call with allow_large_download=true, a flag it could
send itself. Now the schema does not offer the flag, a model call that meets a large file gets a card, the card is registered as a pending confirmation
(a card returned by a two-phase tool was never registered, so it had no Apply button: also the case for load_stac_assets), and only the person's
Apply reaches the registered function with confirmed=True. Offline; how the card looks in QGIS is a hand row."""
import unittest
from unittest.mock import MagicMock, patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent.prompts import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools import humanitarian_tools as ht
from tests.test_confirm_and_fetch_gates import make_agent, pending

THREE = ("fetch_geoboundaries", "fetch_hdx_admin_boundaries", "fetch_building_footprints")
CARD = {"status": "PREVIEW_REQUIRED", "requires_confirmation": True, "is_destructive": False, "tool_name": "fetch_geoboundaries",
        "arguments": {"iso3": "YEM", "admin_level": "ADM2", "confirmed": True}, "code_snippet": "", "rationale": "about 120 MB", "message": "Confirmation required"}


class TestTheModelCannotApproveItsOwnDownload(unittest.TestCase):
    def test_neither_flag_is_in_the_schema_of_the_three_tools(self):
        props = {t["function"]["name"]: set(t["function"]["parameters"].get("properties", {})) for t in TOOLS_SCHEMA}
        for tool in THREE:
            self.assertNotIn("allow_large_download", props[tool], tool)
            self.assertNotIn("confirmed", props[tool], tool)

    def test_a_model_call_that_sends_the_old_flag_still_gets_the_card_not_the_download(self):
        agent = make_agent(decision=None)
        seen = {}

        def network_phase(iso3, admin_level, large):
            seen["large"] = large
            return dict(CARD)

        with patch.object(ht, "fetch_geoboundaries_network_phase", side_effect=network_phase):
            result = agent._execute_two_phase_tool("fetch_geoboundaries", {"iso3": "YEM", "admin_level": "ADM2", "allow_large_download": True})
        self.assertIs(seen["large"], False)
        self.assertEqual(result["status"], "PREVIEW_REQUIRED")

    def test_the_card_is_registered_so_the_apply_button_exists(self):
        agent = make_agent(decision=None)
        with patch.object(ht, "fetch_geoboundaries_network_phase", return_value=dict(CARD)):
            agent._execute_two_phase_tool("fetch_geoboundaries", {"iso3": "YEM", "admin_level": "ADM2"})
        tasks = pending(agent)
        self.assertEqual([t["pending_tool"] for t in tasks], ["fetch_geoboundaries"])
        self.assertEqual(tasks[0]["pending_args"], CARD["arguments"])

    def test_a_card_from_the_sentinel_tool_is_registered_too(self):
        agent = make_agent(decision=None)
        card = {**CARD, "tool_name": "load_stac_assets", "arguments": {"start_date": "2026-01-01", "end_date": "2026-02-01", "assets": ["red"], "confirmed": True}}
        agent._run_two_phase_tool = MagicMock(return_value=card)
        agent._execute_two_phase_tool("load_stac_assets", {"start_date": "2026-01-01", "end_date": "2026-02-01", "assets": ["red"], "bbox": [1, 2, 3, 4]})
        self.assertEqual([t["pending_tool"] for t in pending(agent)], ["load_stac_assets"])

    def test_a_result_that_is_not_a_card_registers_nothing(self):
        agent = make_agent(decision=None)
        agent._run_two_phase_tool = MagicMock(return_value={"success": True})
        agent._execute_two_phase_tool("fetch_geoboundaries", {"iso3": "YEM"})
        self.assertEqual(pending(agent), [])


class TestOnlyApplyReachesTheConfirmedCall(unittest.TestCase):
    def test_the_registered_functions_pass_confirmed_to_the_network_phase_and_default_to_not(self):
        cases = ((ht.fetch_geoboundaries, "fetch_geoboundaries_network_phase", {"iso3": "YEM", "admin_level": "ADM2"}),
                 (ht.fetch_hdx_admin_boundaries, "fetch_hdx_admin_boundaries_network_phase", {"iso3": "YEM", "admin_level": "ADM2"}),
                 (ht.fetch_building_footprints, "fetch_building_footprints_network_phase", {"country_name": "Yemen", "bbox": [1, 2, 3, 4]}))
        for func, phase, kwargs in cases:
            for confirmed, expected in ((None, False), (True, True)):
                with patch.object(ht, phase, return_value={"error": "stop here"}) as network:
                    func(**kwargs, **({} if confirmed is None else {"confirmed": confirmed}))
                self.assertIs(network.call_args.args[-1], expected, (phase, confirmed))

    def test_the_apply_path_would_inject_confirmed_because_the_functions_declare_it(self):
        for func in (ht.fetch_geoboundaries, ht.fetch_hdx_admin_boundaries, ht.fetch_building_footprints):
            self.assertTrue(agent_mod._accepts_confirmed(func), func.__name__)

    def test_each_add_phase_passes_a_card_through_without_making_a_layer(self):
        for add in (ht.add_geoboundaries_layer_main_thread_phase, ht.add_hdx_admin_boundaries_layer_main_thread_phase, ht.add_building_footprints_layer_main_thread_phase):
            self.assertEqual(add(dict(CARD)), CARD, add.__name__)


class TestAWorkflowFileCannotApproveEither(unittest.TestCase):
    """The three tools stay allowed as workflow-file steps (the step runner stops at a card and waits for the person), but a file can neither send
    `confirmed` nor the removed allow_large_download."""

    @staticmethod
    def _check(arguments):
        from cartogen_ai.core import tool_operations
        from cartogen_ai.core.agent import workflow_file as wf
        doc = {"format": "cartogen-workflow", "version": 1, "name": "Boundaries", "description": "d", "roles": {},
               "steps": [{"tool": "fetch_geoboundaries", "arguments": arguments}]}
        return wf.validate(doc, wf.schemas_from(TOOLS_SCHEMA), tool_operations.get_tool_operation_type)

    def test_a_plain_fetch_step_is_accepted(self):
        parsed, problems, _warnings = self._check({"iso3": "YEM", "admin_level": "ADM2"})
        self.assertEqual(problems, [])
        self.assertIsNotNone(parsed)

    def test_a_step_that_tries_to_approve_is_refused(self):
        for key in ("confirmed", "allow_large_download"):
            parsed, problems, _warnings = self._check({"iso3": "YEM", "admin_level": "ADM2", key: True})
            self.assertIsNone(parsed, key)
            self.assertTrue(problems, key)


if __name__ == "__main__":
    unittest.main()
