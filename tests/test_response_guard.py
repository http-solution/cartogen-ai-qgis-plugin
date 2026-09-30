# -*- coding: utf-8 -*-
"""
Tests for services/response_guard.py -- the code-level defence against the assistant
presenting invented tool output (rc7 smoke test, 2026-09-30, finding F03).

Live symptom, reproduced three times: a read of a SENSITIVE layer was blocked (plan showed
0/1 done), yet the assistant answered with a five-row table whose osm_ids, names and
feature classes do not exist in the layer, plus "Retrieved Records: 5".
"""
import unittest

from cartogen_ai.core.services import response_guard as rg

FAKE_TABLE = """Here are the first 5 rows:

| fid | osm_id | fclass | name |
|---|---|---|---|
| 1 | 368412095 | hospital | Al-Thawra Modern General Hospital |
| 2 | 439812401 | clinic | Al-Kuwait University Hospital Clinic |
| 3 | 512938102 | pharmacy | *NULL* |

Retrieved Records: 5
"""


class TestCountTableRows(unittest.TestCase):
    def test_header_and_data_rows_are_counted_but_not_the_separator(self):
        self.assertEqual(rg.count_table_rows(FAKE_TABLE), 4)

    def test_plain_prose_has_no_rows(self):
        self.assertEqual(rg.count_table_rows("The read is waiting for your confirmation."), 0)

    def test_a_single_pipe_in_prose_is_not_a_table(self):
        self.assertEqual(rg.count_table_rows("use a | b when piping"), 0)


class TestAnnotateNotRun(unittest.TestCase):
    def test_a_preview_required_result_is_marked_as_not_run(self):
        res = rg.annotate_not_run({"status": "PREVIEW_REQUIRED", "rationale": "x"})
        self.assertIn("did not run", res["assistant_note"].lower())
        self.assertIn("confirm", res["assistant_note"].lower())

    def test_an_egress_block_is_marked_as_not_run(self):
        res = rg.annotate_not_run({"status": "EGRESS_BLOCKED", "layers": ["a"]})
        self.assertIn("assistant_note", res)

    def test_ordinary_results_are_untouched(self):
        for original in ({"success": True}, {"error": "boom"}, {"status": "PLAN_REQUIRED"}, [1, 2], "text", None):
            self.assertEqual(rg.annotate_not_run(original), original)

    def test_the_original_dict_is_not_mutated(self):
        original = {"status": "PREVIEW_REQUIRED"}
        rg.annotate_not_run(original)
        self.assertNotIn("assistant_note", original)


class TestUnbackedDataWarning(unittest.TestCase):
    def test_a_table_after_a_pending_call_is_flagged(self):
        note = rg.unbacked_data_warning(FAKE_TABLE, pending_tools=["execute_pyqgis_script"], unresolved_errors=[])
        self.assertIsNotNone(note)
        self.assertIn("execute_pyqgis_script", note)
        self.assertIn("not", note.lower())

    def test_a_table_after_an_unresolved_error_is_flagged(self):
        note = rg.unbacked_data_warning(FAKE_TABLE, pending_tools=[], unresolved_errors=["get_attributes"])
        self.assertIsNotNone(note)
        self.assertIn("get_attributes", note)

    def test_a_table_with_no_pending_or_failed_call_is_left_alone(self):
        self.assertIsNone(rg.unbacked_data_warning(FAKE_TABLE, pending_tools=[], unresolved_errors=[]))

    def test_prose_only_reply_after_a_pending_call_is_left_alone(self):
        self.assertIsNone(rg.unbacked_data_warning(
            "This read is waiting for your confirmation.", ["execute_pyqgis_script"], []))

    def test_tool_names_are_deduplicated(self):
        note = rg.unbacked_data_warning(FAKE_TABLE, ["a", "a", "b"], [])
        self.assertEqual(note.count("`a`"), 1)

    def test_apply_appends_the_warning_once(self):
        out = rg.apply_unbacked_data_warning(FAKE_TABLE, ["execute_pyqgis_script"], [])
        self.assertTrue(out.startswith(FAKE_TABLE.rstrip()))
        self.assertEqual(out.count("No data was retrieved"), 1)
        again = rg.apply_unbacked_data_warning(out, ["execute_pyqgis_script"], [])
        self.assertEqual(again.count("No data was retrieved"), 1)


class TestPromptRulesForNotRunCalls(unittest.TestCase):
    """Rules 50-52 are core (always sent): they are the prompt half of F03/F04/F23."""

    def test_new_core_rules_exist_and_are_always_included(self):
        from cartogen_ai.core.agent import prompts
        for n in (50, 51, 52):
            self.assertIn(n, prompts._ALL_RULES)
            self.assertIn(n, prompts.CORE_RULE_NUMBERS)

    def test_rule_50_forbids_inventing_results_and_prose_confirmations(self):
        from cartogen_ai.core.agent import prompts
        text = prompts._ALL_RULES[50].lower()
        self.assertIn("preview_required", text)
        self.assertIn("invent", text)
        self.assertIn('"confirm"', text)

    def test_rule_51_forbids_hand_conversion_of_coordinates(self):
        from cartogen_ai.core.agent import prompts
        self.assertIn("never convert coordinates", prompts._ALL_RULES[51].lower())


if __name__ == "__main__":
    unittest.main()
