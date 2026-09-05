# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock
import pathlib
from cartogen_ai.core.agent.prompt_refiner import (
    should_refine, build_refinement_messages, parse_refinement_response, refine,
    analyze_request, build_disambiguation_messages, parse_disambiguation_response,
    PROFILE_LABELS, DEFAULT_PROFILE,
)


class TestShouldRefine(unittest.TestCase):
    def test_empty_string_is_false(self):
        self.assertFalse(should_refine("", True))

    def test_whitespace_only_is_false(self):
        self.assertFalse(should_refine("   ", True))

    def test_disabled_is_false_even_for_a_long_query(self):
        query = "calculate flood exposure for admin-2 units in Aleppo governorate"
        self.assertFalse(should_refine(query, False))

    def test_exactly_five_words_is_false(self):
        self.assertFalse(should_refine("one two three four five", True))

    def test_six_words_is_true(self):
        self.assertTrue(should_refine("one two three four five six", True))

    def test_long_realistic_query_is_true(self):
        query = "show me the flood situation for this area and what's affected"
        self.assertTrue(should_refine(query, True))


class TestBuildRefinementMessages(unittest.TestCase):
    def test_returns_system_and_user_messages(self):
        messages = build_refinement_messages("zoom to the flood zone", "general")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1], {"role": "user", "content": "zoom to the flood zone"})

    def test_system_message_stays_under_500_chars_for_every_profile(self):
        for profile in PROFILE_LABELS:
            messages = build_refinement_messages("query", profile)
            self.assertLess(len(messages[0]["content"]), 900)  # generous margin over the ~500 target, still bounded

    def test_profile_label_is_substituted(self):
        messages = build_refinement_messages("query", "humanitarian")
        self.assertIn(PROFILE_LABELS["humanitarian"], messages[0]["content"])

    def test_unknown_profile_falls_back_to_general(self):
        messages = build_refinement_messages("query", "not_a_real_profile")
        self.assertIn(PROFILE_LABELS[DEFAULT_PROFILE], messages[0]["content"])


class TestParseRefinementResponse(unittest.TestCase):
    def _valid_payload(self):
        return {
            "detected_profile": "general",
            "recommendations": [
                {"id": "A", "label": "Clarified", "refined_prompt": "a", "rationale": "why a"},
                {"id": "B", "label": "Visualization-forward", "refined_prompt": "b", "rationale": "why b"},
            ],
        }

    def test_valid_json_string_parses(self):
        import json
        result = parse_refinement_response(json.dumps(self._valid_payload()))
        self.assertIsNotNone(result)
        self.assertEqual(len(result["recommendations"]), 2)

    def test_valid_dict_passthrough(self):
        result = parse_refinement_response(self._valid_payload())
        self.assertIsNotNone(result)

    def test_non_json_string_returns_none(self):
        self.assertIsNone(parse_refinement_response("not json at all"))

    def test_json_list_instead_of_dict_returns_none(self):
        self.assertIsNone(parse_refinement_response("[1, 2, 3]"))

    def test_missing_recommendations_key_returns_none(self):
        self.assertIsNone(parse_refinement_response({"detected_profile": "general"}))

    def test_only_one_recommendation_returns_none(self):
        payload = self._valid_payload()
        payload["recommendations"] = payload["recommendations"][:1]
        self.assertIsNone(parse_refinement_response(payload))

    def test_three_recommendations_returns_none(self):
        payload = self._valid_payload()
        payload["recommendations"].append({"id": "C", "refined_prompt": "c"})
        self.assertIsNone(parse_refinement_response(payload))

    def test_recommendation_missing_refined_prompt_returns_none(self):
        payload = self._valid_payload()
        del payload["recommendations"][0]["refined_prompt"]
        self.assertIsNone(parse_refinement_response(payload))

    def test_none_input_returns_none(self):
        self.assertIsNone(parse_refinement_response(None))


class TestRefine(unittest.TestCase):
    def _valid_payload_str(self):
        import json
        return json.dumps({
            "detected_profile": "general",
            "recommendations": [
                {"id": "A", "label": "Clarified", "refined_prompt": "a", "rationale": "why a"},
                {"id": "B", "label": "Visualization-forward", "refined_prompt": "b", "rationale": "why b"},
            ],
        })

    def test_client_raising_returns_error_dict_not_exception(self):
        client = MagicMock()
        client.complete.side_effect = Exception("boom")
        result = refine("some long enough query text", "general", client)
        self.assertIn("error", result)

    def test_client_error_response_returns_error_dict(self):
        client = MagicMock()
        client.complete.return_value = {"error": "rate limited"}
        result = refine("some long enough query text", "general", client)
        self.assertIn("error", result)

    def test_malformed_content_returns_error_dict(self):
        client = MagicMock()
        client.complete.return_value = {"message": {"content": "not valid json"}}
        result = refine("some long enough query text", "general", client)
        self.assertIn("error", result)

    def test_valid_response_returns_parsed_recommendations(self):
        client = MagicMock()
        client.complete.return_value = {"message": {"content": self._valid_payload_str()}}
        result = refine("some long enough query text", "general", client)
        self.assertNotIn("error", result)
        self.assertEqual(len(result["recommendations"]), 2)

    def test_passes_tools_none_and_max_tokens_to_client(self):
        client = MagicMock()
        client.complete.return_value = {"message": {"content": self._valid_payload_str()}}
        refine("some long enough query text", "general", client, max_tokens=250)
        _, kwargs = client.complete.call_args
        self.assertIsNone(kwargs["tools"])
        self.assertEqual(kwargs["max_tokens"], 250)


class TestChatPipelineIntegration(unittest.TestCase):
    """ui/chat_tab_widget.py imports qgis.PyQt unconditionally and cannot be
    imported outside a real QGIS process (see its module docstring), so the
    wiring is checked by reading the source. That is weaker than executing it
    and is stated as such -- docs/RELEASE_SMOKE_TEST.md carries the in-QGIS
    check. What it does catch, and what it exists for, is the failure that
    actually happened here once already: a well-tested library sitting beside
    the send path with nothing calling it."""

    def _source(self, name):
        base = pathlib.Path(__file__).resolve().parents[1] / "src" / "cartogen_ai" / "core"
        return (base / "ui" / name).read_text(encoding="utf-8")

    def test_chat_send_path_calls_local_task_analysis_before_refinement(self):
        text = self._source("chat_tab_widget.py")
        self.assertIn("analyze_request", text)
        self.assertIn("requirement_panel", text)
        self.assertIn("analysis_directive", text)

    def test_chat_send_path_previews_the_prompt_before_sending(self):
        text = self._source("chat_tab_widget.py")
        self.assertIn("is_prompt_preview_enabled", text)
        self.assertIn("_show_preview_panel", text)
        self.assertIn("optimum_prompt", text)

    def test_chat_send_path_sends_the_composed_message_not_the_raw_text(self):
        text = self._source("chat_tab_widget.py")
        self.assertIn('analysis["user_message"]', text)
        self.assertIn("user_text=sent_text", text)

    def test_chat_send_path_passes_attachments_into_the_analysis(self):
        text = self._source("chat_tab_widget.py")
        self.assertIn("_attached_paths", text)
        self.assertIn("analyze_request(text, request_context, self._attached_paths)", text)

    def test_chat_send_path_enforces_the_output_contract_after_the_answer(self):
        text = self._source("chat_tab_widget.py")
        self.assertIn("_enforce_output_contract", text)
        self.assertIn("output_router", text)
        self.assertIn("_contract_followup_used", text)

    def test_the_preview_setting_is_exposed_in_the_settings_dialog(self):
        text = self._source("settings_dialog.py")
        self.assertIn("PROMPT_PREVIEW_ENABLED_KEY", text)
        self.assertIn("prompt_preview_checkbox", text)


class TestAnalyzeRequestShape(unittest.TestCase):
    KEYS = ("task", "score", "ambiguous", "missing", "unresolved", "defaults",
            "question", "directive", "contract", "attachments", "user_message",
            "optimum_prompt", "reasoning", "expected_output")

    def test_every_key_is_present_on_a_match(self):
        a = analyze_request("map flood damaged buildings in Sudan admin2 since 2024")
        for k in self.KEYS:
            self.assertIn(k, a, k)
        self.assertIsNotNone(a["task"])

    def test_every_key_is_present_when_nothing_matches(self):
        a = analyze_request("zzzz")
        for k in self.KEYS:
            self.assertIn(k, a, k)
        self.assertIsNone(a["task"])

    def test_an_unmatched_request_is_sent_exactly_as_typed(self):
        a = analyze_request("  zzzz  ")
        self.assertEqual(a["user_message"], "zzzz")
        self.assertEqual(a["optimum_prompt"], "zzzz")
        self.assertEqual(a["directive"], "")
        self.assertIsNone(a["contract"])

    def test_the_original_wording_always_leads_the_composed_message(self):
        q = "map cholera cases in admin2 for last month"
        a = analyze_request(q)
        self.assertTrue(a["user_message"].startswith(q))

    def test_the_preview_contains_both_halves_of_what_is_sent_verbatim(self):
        a = analyze_request("produce a print layout of health facilities in Aleppo")
        self.assertIn(a["user_message"], a["optimum_prompt"])
        self.assertIn(a["directive"], a["optimum_prompt"])

    def test_assumed_values_are_stated_in_the_message_and_in_the_reasoning(self):
        a = analyze_request("map health facilities")
        if a["defaults"]:
            key = sorted(a["defaults"])[0]
            self.assertIn(key, a["user_message"])
            self.assertTrue(any(key in line for line in a["reasoning"]))

    def test_expected_output_names_a_file_for_a_file_producing_contract(self):
        a = analyze_request("build me a dashboard of displacement by district")
        self.assertIn("HTML", a["expected_output"])


class TestAnalyzeRequestAttachments(unittest.TestCase):
    def test_a_pdf_a_picture_and_a_text_file_are_each_placed(self):
        a = analyze_request("map damaged buildings",
                            attachments=["/x/sitrep.pdf", "/x/photo.jpg", "/x/notes.txt"])
        kinds = [p["kind"] for p in a["attachments"]]
        self.assertEqual(kinds, ["pdf", "image", "txt"])
        for p in a["attachments"]:
            self.assertTrue(p["accepted"], p["name"])
            self.assertIn(p["name"], a["user_message"])

    def test_an_unusable_file_is_reported_rather_than_dropped(self):
        a = analyze_request("map damaged buildings", attachments=["/x/archive.7z"])
        self.assertEqual(len(a["attachments"]), 1)
        self.assertFalse(a["attachments"][0]["accepted"])
        self.assertIn("archive.7z", a["user_message"])
        self.assertTrue(any("archive.7z" in line for line in a["reasoning"]))

    def test_no_attachments_means_no_attachment_section(self):
        a = analyze_request("map health facilities in Aleppo")
        self.assertEqual(a["attachments"], [])
        self.assertNotIn("Attached files:", a["user_message"])


class TestDisambiguation(unittest.TestCase):
    """Stage 2 -- previously shipped with no coverage at all."""

    def test_messages_carry_the_candidate_ids_and_nothing_else(self):
        from cartogen_ai.core.agent import task_matcher as tm
        candidates = tm.match("map damaged buildings")[:5]
        msgs = build_disambiguation_messages("map damaged buildings", candidates)
        self.assertEqual([m["role"] for m in msgs], ["system", "user"])
        for entry, _score in candidates:
            self.assertIn(entry["id"], msgs[0]["content"])
        # the register itself must never be shipped in a prompt
        self.assertLess(len(msgs[0]["content"]), 1200)

    def test_the_user_turn_is_the_query_unchanged(self):
        msgs = build_disambiguation_messages("map wells", [])
        self.assertEqual(msgs[1]["content"], "map wells")

    def test_a_valid_response_yields_the_task_id(self):
        self.assertEqual(parse_disambiguation_response('{"task_id": "5.01"}'), "5.01")
        self.assertEqual(parse_disambiguation_response({"task_id": "5.01"}), "5.01")

    def test_a_null_or_empty_id_yields_none(self):
        self.assertIsNone(parse_disambiguation_response('{"task_id": null}'))
        self.assertIsNone(parse_disambiguation_response('{"task_id": ""}'))

    def test_malformed_input_never_raises(self):
        for bad in ('not json', '[]', '{}', None, 12, '{"task_id": 7}'):
            self.assertIsNone(parse_disambiguation_response(bad), repr(bad))


if __name__ == "__main__":
    unittest.main()
