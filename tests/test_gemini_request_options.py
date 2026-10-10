# -*- coding: utf-8 -*-
"""tool_choice / extra_body on GeminiClient (API-call optimisation plan, phase 0). Offline: the HTTP call is mocked, so this proves what
is SENT, not what Google's endpoint accepts (tools/diagnose_gemini_endpoint.py does that with a real key)."""
import json
import unittest
from unittest import mock

from cartogen_ai.infrastructure.providers import gemini
from cartogen_ai.infrastructure.providers.gemini import GeminiClient, validate_tool_choice

TOOLS = [{"type": "function", "function": {"name": "get_layers", "description": "x", "parameters": {"type": "object", "properties": {}}}}]


class _Resp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 1}}


def _sent_payload(**kwargs):
    with mock.patch.object(gemini, "post_with_retry", return_value=_Resp()) as post:
        out = GeminiClient("k", model="m").complete([{"role": "user", "content": "hi"}], tools=TOOLS, **kwargs)
    assert "error" not in out, out
    return json.loads(post.call_args.args[2])


class TestRequestOptions(unittest.TestCase):
    def test_the_default_request_is_unchanged(self):
        payload = _sent_payload()
        self.assertNotIn("tool_choice", payload)
        self.assertEqual(set(payload), {"model", "messages", "max_tokens", "tools"})

    def test_tool_choice_none_is_sent_when_asked(self):
        self.assertEqual(_sent_payload(tool_choice="none")["tool_choice"], "none")

    def test_a_named_function_is_sent(self):
        choice = {"type": "function", "function": {"name": "get_layers"}}
        self.assertEqual(_sent_payload(tool_choice=choice)["tool_choice"], choice)

    def test_extra_body_is_merged_but_cannot_override_core_fields(self):
        payload = _sent_payload(extra_body={"google": {"thinking_config": {"thinking_budget": 0}}, "model": "evil", "tools": []})
        self.assertEqual(payload["google"], {"thinking_config": {"thinking_budget": 0}})
        self.assertEqual(payload["model"], "m")
        self.assertEqual(payload["tools"], TOOLS)

    def test_an_unsupported_tool_choice_returns_an_error_instead_of_sending(self):
        with mock.patch.object(gemini, "post_with_retry") as post:
            out = GeminiClient("k", model="m").complete([{"role": "user", "content": "hi"}], tools=TOOLS, tool_choice="sometimes")
        self.assertIn("error", out)
        post.assert_not_called()


class TestValidateToolChoice(unittest.TestCase):
    def test_accepts_the_openai_forms(self):
        for value in ("auto", "none", "required", {"type": "function", "function": {"name": "f"}}):
            self.assertEqual(validate_tool_choice(value), value)

    def test_rejects_everything_else(self):
        for value in ("", "ANY", {"type": "function"}, {"type": "function", "function": {}}, 3, ["none"]):
            with self.assertRaises(ValueError):
                validate_tool_choice(value)


if __name__ == "__main__":
    unittest.main()
