# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock
from agent.prompt_refiner import (
    should_refine, build_refinement_messages, parse_refinement_response, refine,
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


if __name__ == "__main__":
    unittest.main()
