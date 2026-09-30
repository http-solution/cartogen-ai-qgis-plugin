# -*- coding: utf-8 -*-
"""Tests for agent/output_router.py -- the step that checks the answer came
back in the shape the task promised, and asks once when it did not."""
import unittest

from cartogen_ai.core.agent import output_router as router
from cartogen_ai.core.agent import task_matcher as tm
from cartogen_ai.core.agent import task_register as reg


def contract_for(query):
    return tm.output_contract(tm.classify(query)["best"], query)


class TestSatisfied(unittest.TestCase):
    def test_no_contract_is_always_satisfied(self):
        self.assertTrue(router.satisfied(None, []))

    def test_guidance_needs_nothing(self):
        self.assertTrue(router.satisfied({"kind": "guidance", "render": []}, []))

    def test_dashboard_needs_its_renderer(self):
        c = {"kind": "dashboard", "render": ["generate_html_dashboard"]}
        self.assertFalse(router.satisfied(c, ["add_layer_from_path", "apply_labels"]))
        self.assertTrue(router.satisfied(c, ["add_layer_from_path", "generate_html_dashboard"]))

    def test_layout_needs_a_layout_tool(self):
        c = {"kind": "layout", "render": ["create_print_layout", "print_map"]}
        self.assertFalse(router.satisfied(c, ["zoom_to_layer"]))
        self.assertTrue(router.satisfied(c, ["create_print_layout"]))

    def test_a_layer_contract_is_met_by_anything_that_puts_a_layer_on_the_canvas(self):
        # Styling is the nominal renderer, but a layer that cannot be
        # categorised is still a delivered layer.
        c = {"kind": "layer", "render": ["apply_categorized_style", "zoom_to_layer"]}
        self.assertTrue(router.satisfied(c, ["fetch_osm_features"]))
        self.assertTrue(router.satisfied(c, ["buffer_analysis"]))
        self.assertTrue(router.satisfied(c, ["apply_categorized_style"]))

    def test_a_layer_contract_is_not_met_by_a_read_only_turn(self):
        c = {"kind": "layer", "render": ["apply_categorized_style", "zoom_to_layer"]}
        self.assertFalse(router.satisfied(c, ["get_layers", "get_attributes"]))
        self.assertFalse(router.satisfied(c, []))

    def test_a_layer_contract_is_met_by_point_layer_creation(self):
        c = {"kind": "layer", "render": ["apply_categorized_style", "zoom_to_layer"]}
        self.assertTrue(router.satisfied(c, ["add_point_layer"]))
        self.assertTrue(router.satisfied(c, ["add_incident_point"]))
        self.assertTrue(router.satisfied(c, ["create_memory_layer"]))

    def test_every_contract_kind_in_the_register_is_handled(self):
        for kind in reg.OUTPUTS:
            # must not raise, and must give a definite answer either way
            self.assertIn(router.satisfied({"kind": kind, "render": []}, []), (True, False))


class TestFollowup(unittest.TestCase):
    def setUp(self):
        self.contract = {"kind": "dashboard", "render": ["generate_html_dashboard"], "explicit": True}

    def test_no_followup_when_already_delivered(self):
        self.assertIsNone(router.followup_instruction(self.contract, ["generate_html_dashboard"]))

    def test_followup_names_the_artifact_and_the_tool(self):
        msg = router.followup_instruction(self.contract, ["add_layer_from_path"])
        self.assertIn("HTML", msg)
        self.assertIn("generate_html_dashboard", msg)

    def test_followup_tells_the_model_not_to_redo_the_work(self):
        msg = router.followup_instruction(self.contract, [])
        self.assertIn("Do not redo", msg)

    def test_only_one_followup_ever(self):
        self.assertIsNone(
            router.followup_instruction(self.contract, [], already_retried=True))

    def test_a_contract_with_no_renderer_never_asks_for_anything(self):
        self.assertIsNone(router.followup_instruction({"kind": "guidance", "render": []}, []))

    def test_missing_layer_followup_demands_layer_creation(self):
        layer_contract = {"kind": "layer", "render": ["apply_categorized_style", "zoom_to_layer"], "explicit": True}
        # When no layer was created in the turn
        msg = router.followup_instruction(layer_contract, ["get_layers", "get_attributes"])
        self.assertIn("no layer has been created yet", msg)
        self.assertIn("add_point_layer", msg)
        self.assertNotIn("Do not redo", msg)

    def test_missing_layer_followup_with_has_layers_false(self):
        layer_contract = {"kind": "layer", "render": ["apply_categorized_style", "zoom_to_layer"], "explicit": True}
        msg = router.followup_instruction(layer_contract, [], has_layers=False)
        self.assertIn("Call an appropriate layer creation tool now", msg)

    def test_layer_followup_with_existing_layer_demands_styling(self):
        layer_contract = {"kind": "layer", "render": ["apply_categorized_style", "zoom_to_layer"], "explicit": True}
        # When a layer was created but styling didn't run and satisfied() returned False
        msg = router.followup_instruction(layer_contract, ["custom_layer_creator"], has_layers=True)
        self.assertIn("apply_categorized_style", msg)
        self.assertIn("Do not redo the analysis", msg)


class TestImpliedDeliverableIsNotNudged(unittest.TestCase):
    """F10: a contract inferred from a task match (not named by the user) never forces a tool call."""

    def test_implied_contract_gets_no_followup(self):
        c = {"kind": "dataset", "render": ["export_layer", "export_to_csv"], "explicit": False}
        self.assertIsNone(router.followup_instruction(c, ["get_layers"]))
        self.assertIsNone(router.followup_instruction({"kind": "dashboard", "render": ["generate_html_dashboard"]}, []))

    def test_only_a_named_output_is_explicit(self):
        self.assertTrue(contract_for("export the flood extent as a geopackage")["explicit"])
        self.assertFalse(contract_for("which clinics are within 1 hour of Sanaa")["explicit"])


class TestNotes(unittest.TestCase):
    def test_delivery_note_is_honest_when_nothing_was_written(self):
        note = router.delivery_note({"kind": "dashboard", "render": ["generate_html_dashboard"]}, [])
        self.assertIn("did not run", note)

    def test_delivery_note_states_the_artifact_when_it_was(self):
        note = router.delivery_note({"kind": "dashboard", "render": ["generate_html_dashboard"]},
                                    ["generate_html_dashboard"])
        self.assertIn("Delivered", note)
        self.assertIn("HTML", note)

    def test_describe_contract_flags_a_user_override(self):
        line = router.describe_contract(
            {"kind": "dashboard", "render": [], "overridden": True})
        self.assertIn("dashboard", line)
        self.assertIn("overrides", line)

    def test_describe_contract_is_empty_without_one(self):
        self.assertEqual(router.describe_contract(None), "")


class TestAgainstRealRegisterContracts(unittest.TestCase):
    def test_a_dashboard_request_end_to_end(self):
        c = contract_for("build me a dashboard of displacement by district")
        self.assertEqual(c["kind"], "dashboard")
        self.assertFalse(router.satisfied(c, ["fetch_geoboundaries"]))
        self.assertIn("generate_html_dashboard", router.followup_instruction(c, ["fetch_geoboundaries"]))

    def test_an_export_request_end_to_end(self):
        c = contract_for("export the flood extent as a geopackage")
        self.assertEqual(c["kind"], "dataset")
        self.assertTrue(router.satisfied(c, ["export_layer"]))


if __name__ == "__main__":
    unittest.main()
