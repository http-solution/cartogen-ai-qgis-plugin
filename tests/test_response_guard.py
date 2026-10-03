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
        self.assertNotIn("368412095", out)            # the invented rows are gone
        self.assertIn(rg._NOTICE_TABLE_REMOVED, out)    # replaced by a notice, not silently dropped
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


BULLETS = """Here are the first clinics I found:

- 450157266 | clinic | Al Noor Medical Centre
- 450157301 | hospital | Sanaa General Hospital
- 450158112 | dentist | Smile Dental, 15.3547
"""

PROSE_CLAIM = "Retrieved Records: 5\n\n- 450157266: clinic, Al Noor\n"

HOWTO = """To do this:

1. Open the layer properties
2. Choose the Symbology tab
3. Pick a categorized style
"""

OPTIONS_TABLE = """| Option | Pros | Cons |
|---|---|---|
| Buffer | simple | can overcount |
| Hull | tight | jagged |
| Grid | regular | coarse |
"""


class TestRecordLikeLines(unittest.TestCase):
    def test_bulleted_records_are_counted(self):
        self.assertEqual(rg.count_record_lines(BULLETS), 3)

    def test_a_how_to_list_has_no_records(self):
        self.assertEqual(rg.count_record_lines(HOWTO), 0)

    def test_an_options_table_has_no_records(self):
        self.assertEqual(rg.count_record_lines(OPTIONS_TABLE), 0)

    def test_arabic_names_count_as_words(self):
        self.assertEqual(rg.count_record_lines("- 450157266 | hospital | \u0645\u0633\u062a\u0634\u0641\u0649\n" * 3), 3)

    def test_a_retrieval_claim_needs_at_least_one_record(self):
        self.assertTrue(rg.looks_like_retrieved_data(PROSE_CLAIM))
        self.assertFalse(rg.looks_like_retrieved_data("Retrieved Records: 5"))


class TestNoDataToolRanAtAll(unittest.TestCase):
    def test_bullets_with_no_tool_in_the_turn_are_flagged(self):
        note = rg.unbacked_data_warning(BULLETS, [], [], data_tool_ran=False)
        self.assertIsNotNone(note)
        self.assertIn("no data tool ran", note)

    def test_the_same_bullets_after_a_successful_tool_are_left_alone(self):
        self.assertIsNone(rg.unbacked_data_warning(BULLETS, [], [], data_tool_ran=True))

    def test_a_how_to_list_with_no_tool_is_left_alone(self):
        self.assertIsNone(rg.unbacked_data_warning(HOWTO, [], [], data_tool_ran=False))

    def test_an_options_table_with_no_tool_is_left_alone_and_kept(self):
        self.assertIsNone(rg.unbacked_data_warning(OPTIONS_TABLE, [], [], data_tool_ran=False))
        self.assertEqual(rg.strip_ungrounded_tables(OPTIONS_TABLE).strip(), OPTIONS_TABLE.strip())

    def test_an_invented_table_is_replaced_not_kept(self):
        out = rg.apply_unbacked_data_warning(FAKE_TABLE, [], [], data_tool_ran=False)
        self.assertNotIn("368412095", out)
        self.assertIn("No data was retrieved", out)

    def test_bullets_are_warned_about_but_kept(self):
        out = rg.apply_unbacked_data_warning(BULLETS, [], [], data_tool_ran=False)
        self.assertIn("450157266", out)
        self.assertIn("No data was retrieved", out)


class TestConfirmationProse(unittest.TestCase):
    def test_the_models_own_confirm_lines_are_removed(self):
        text = ("The read of Health Facilities is pending.\n\n"
                "\u26a0\ufe0f **Destructive Action Confirmation**\n"
                "Please reply with Confirm to proceed.\n")
        out = rg.strip_confirmation_prose(text)
        self.assertIn("pending", out)
        self.assertNotIn("Confirm", out)

    def test_only_a_confirm_request_leaves_the_card_notice(self):
        self.assertEqual(rg.strip_confirmation_prose("Preview Ready. Reply Confirm or Proceed."),
                         rg.CONFIRM_CARD_NOTICE)

    def test_ordinary_text_is_untouched(self):
        text = "I counted 12 facilities. Confirming the CRS is EPSG:3857."
        self.assertEqual(rg.strip_confirmation_prose(text), text)


if __name__ == "__main__":
    unittest.main()


class TestUngroundedClaims(unittest.TestCase):
    """GitHub #75: the narrative around real numbers (rc11 smoke test) -- place names, national totals, terrain, file sizes."""

    EVIDENCE = ("user asked: what population lives within one hour of Sanaa? tool: reachable 815,039 of total 1,200,000 "
                "people; roads reached 31,583; worldpop file size_mb 481.70; layer YEM_ADM1_boundary_hdx")

    def claims(self, text, evidence=None):
        from cartogen_ai.core.services.response_guard import ungrounded_claims
        return ungrounded_claims(text, self.EVIDENCE if evidence is None else evidence)

    def test_the_rc11_examples_are_flagged(self):
        found = self.claims("Amran Governorate is next. The WorldPop file is 240 MB. The national baseline is ~29.8M. "
                            "The terrain is rugged and mountainous, with unpaved valley tracks.")
        for expected in ("Amran Governorate", "240 MB", "29.8M", '"rugged"', '"mountainous"', '"unpaved"'):
            self.assertIn(expected, found)

    def test_figures_the_tools_returned_are_not_flagged(self):
        self.assertEqual(self.claims("About 815,039 people (0.8M) are reached, of 1.2M in total; the file is 481.7 MB."), [])

    def test_rounding_and_simple_derived_figures_are_not_flagged(self):
        self.assertEqual(self.claims("Roughly 384,961 people (1,200,000 minus 815,039) are not reached."), [])

    def test_a_place_the_user_or_a_tool_named_is_not_flagged(self):
        self.assertEqual(self.claims("The Sanaa District is covered.", "user said Sanaa"), [])
        self.assertIn("Amran Governorate", self.claims("Amran Governorate is covered.", "user said Sanaa"))

    def test_generic_words_before_a_place_suffix_are_ignored(self):
        self.assertEqual(self.claims("Each District is scored. The Region is large. This Province matters."), [])

    def test_terrain_words_are_fine_when_the_user_or_a_terrain_tool_mentioned_them(self):
        self.assertEqual(self.claims("The area is mountainous.", "user: analyse the mountainous terrain"), [])
        self.assertEqual(self.claims("Steep roads slow the route.", "tool: slope raster computed"), [])
        self.assertIn('"steep"', self.claims("Steep roads slow the route."))

    def test_unpaved_is_not_grounded_by_the_word_paved(self):
        self.assertIn('"unpaved"', self.claims("The roads are unpaved.", "surface field values: paved"))

    def test_identifiers_and_coordinates_are_not_totals(self):
        self.assertEqual(self.claims("osm_id 368412095 at 44.036028, 15.970136"), [])

    def test_the_list_is_capped(self):
        from cartogen_ai.core.services.response_guard import ungrounded_claims
        text = " ".join(f"{n}00 MB" for n in range(2, 30))
        self.assertLessEqual(len(ungrounded_claims(text, "")), 6)

    def test_the_note_is_appended_once_after_a_data_tool_ran_and_is_visible_text(self):
        from cartogen_ai.core.services.response_guard import apply_ungrounded_claims_note
        out = apply_ungrounded_claims_note("Amran Governorate is next.", self.EVIDENCE, data_tool_ran=True)
        self.assertIn("Not from a tool result", out)
        self.assertTrue(out.startswith("Amran Governorate is next."))        # the answer itself is never rewritten
        self.assertEqual(apply_ungrounded_claims_note(out, self.EVIDENCE, True), out)    # idempotent

    def test_a_conceptual_answer_with_no_data_tool_is_left_alone(self):
        from cartogen_ai.core.services.response_guard import apply_ungrounded_claims_note
        text = "Yemen has about 34,000,000 people and mountainous terrain."
        self.assertEqual(apply_ungrounded_claims_note(text, "", data_tool_ran=False), text)
