"""PLAN-031: the part of the verified result gate that needs no QGIS: which results are eligible, the context built from a result, what is
attached, and the reply guard that stops a failed check being left out of the answer."""
import unittest
from typing import ClassVar

from cartogen_ai.core.agent import result_gate
from cartogen_ai.core.services import response_guard
from cartogen_ai.core.validators import result_checks as rc

from tests.test_agent_runner import _make_bare_agent


def failed(detail="The field 'sev' has the same value for all 4 features, so it ranks nothing."):
    return {"id": "field:sev", "status": rc.FAIL, "detail": detail}


class TestEligibility(unittest.TestCase):
    def test_only_a_successful_create_or_modify_result_that_names_a_layer(self):
        ok = {"success": True, "layer_name": "districts", "output_field": "sev"}
        self.assertTrue(result_gate.eligible("MODIFY", ok))
        self.assertTrue(result_gate.eligible("CREATE", {"layer_name": "out"}))
        self.assertFalse(result_gate.eligible("READ", ok))
        self.assertFalse(result_gate.eligible("DELETE", ok))
        self.assertFalse(result_gate.eligible("MODIFY", {"error": "boom", "layer_name": "x"}))
        self.assertFalse(result_gate.eligible("MODIFY", {"success": False, "layer_name": "x"}))
        self.assertFalse(result_gate.eligible("MODIFY", {"success": True}))
        self.assertFalse(result_gate.eligible("MODIFY", {"layer_name": "  "}))
        self.assertFalse(result_gate.eligible("MODIFY", ["not", "a", "dict"]))

    def test_context_names_the_written_field_and_enables_no_risky_check(self):
        context = result_gate.context_for("calculate_severity_index", {"layer_name": "d", "output_field": "sev"})
        self.assertEqual(context["written_fields"], {"sev": ""})
        self.assertFalse(context["distance_based"], "the CRS check stays off until a real run shows the tool computes in the layer's CRS")
        self.assertFalse(context["one_to_one"])
        self.assertEqual(result_gate.context_for("t", {"layer_name": "d"})["written_fields"], {})
        self.assertEqual(result_gate.DISTANCE_BASED_TOOLS, frozenset())

    def test_without_qgis_the_hook_returns_the_result_untouched(self):
        result = {"success": True, "layer_name": "d", "output_field": "sev"}
        self.assertIs(result_gate.attach_checks("t", result, "MODIFY"), result)
        self.assertNotIn("checks", result)


class TestAttach(unittest.TestCase):
    def test_a_failed_check_adds_a_note_the_model_must_act_on(self):
        result = result_gate.attach({"success": True}, [{"id": "geometry", "status": rc.PASS, "detail": "ok"}, failed()])
        self.assertEqual(result["checks_summary"], "1 passed, 0 warnings, 1 failed: field:sev")
        self.assertIn("FAILED", result["checks_note"])
        self.assertIn("ranks nothing", result["checks_note"])

    def test_passing_checks_add_no_note_and_a_sample_is_stated(self):
        result = result_gate.attach({"success": True}, [{"id": "geometry", "status": rc.PASS, "detail": "ok"}], sampled_of=(5000, 50000))
        self.assertNotIn("checks_note", result)
        self.assertIn("first 5000 of 50000 features checked", result["checks_summary"])


class TestReplyGuard(unittest.TestCase):
    CALLS: ClassVar[list] = [("calculate_severity_index", {}, {"success": True, "checks": [failed()]})]

    def test_failed_checks_are_collected_from_the_turns_results(self):
        self.assertEqual(response_guard.failed_checks(self.CALLS), [("calculate_severity_index", failed()["detail"])])
        self.assertEqual(response_guard.failed_checks(None), [])
        self.assertEqual(response_guard.failed_checks([("t", {}, "text"), ("t", {}, {"checks": [{"status": "pass", "detail": "x"}]})]), [])

    def test_a_reply_that_leaves_the_failure_out_gets_a_visible_warning(self):
        text = response_guard.apply_failed_checks_note("The severity scores are ready.", response_guard.failed_checks(self.CALLS))
        self.assertIn("A result check failed", text)
        self.assertIn("ranks nothing", text)

    def test_a_reply_that_says_it_in_its_own_words_or_quotes_it_is_left_alone(self):
        calls = response_guard.failed_checks(self.CALLS)
        for reply in ("A check failed on the result, so treat it with care.",
                      "Note: " + failed()["detail"] + " I would not rely on it."):
            self.assertEqual(response_guard.apply_failed_checks_note(reply, calls), reply)
        self.assertEqual(response_guard.apply_failed_checks_note("fine", []), "fine")

    def test_the_agents_final_guard_appends_it(self):
        agent = _make_bare_agent(None)
        agent._turn_calls = list(self.CALLS)
        agent._grounding_texts = []
        agent.task_manager = type("T", (), {"tasks": []})()
        text = agent._guard_unbacked_data("The severity scores are ready.", [("calculate_severity_index", False, None)], [])
        self.assertIn("A result check failed", text)


if __name__ == "__main__":
    unittest.main()
