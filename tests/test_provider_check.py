"""PLAN-039 slice 3: the Test button of the key-based providers. Provider calls are replaced (no network, no key); error wording used in
the classification cases comes from the project's own formatters in providers/base.py."""
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from cartogen_ai.infrastructure.providers import provider_check as pc
from cartogen_ai.infrastructure.providers.base import format_http_error


class _Resp:
    def __init__(self, status, text="", headers=None):
        self.status_code, self.text, self.headers = status, text, headers or {}

    def json(self):
        raise ValueError("no body")


class _HttpError(Exception):
    def __init__(self, status, text=""):
        super().__init__(text)
        self.response = _Resp(status, text)


def _client(result):
    client = MagicMock()
    client.complete.return_value = result
    return MagicMock(return_value=client), client


class TestClassify(unittest.TestCase):
    def test_the_projects_own_error_texts(self):
        self.assertEqual(pc.classify_error(format_http_error("OpenRouter HTTP error", _HttpError(401))), "key")
        self.assertEqual(pc.classify_error(format_http_error("Gemini HTTP error", _HttpError(403))), "key")
        self.assertEqual(pc.classify_error(format_http_error("Claude HTTP error", _HttpError(404, "model not found"))), "model")
        self.assertEqual(pc.classify_error("OpenRouter: could not reach the server -- check your internet connection."), "network")
        self.assertEqual(pc.classify_error("Ollama connection failed: could not reach the server (is Ollama running?)"), "network")
        self.assertEqual(pc.classify_error("Gemini HTTP error (429): quota exceeded for this key"), "limit")
        self.assertEqual(pc.classify_error("something odd"), "other")
        self.assertEqual(pc.classify_error(None), "other")

    def test_a_key_failure_wins_over_wording_that_also_mentions_a_model(self):
        self.assertEqual(pc.classify_error("(401): Authentication failed -- check your API key. model foo"), "key")

    def test_a_quota_message_is_a_limit_not_a_model_problem(self):
        self.assertEqual(pc.classify_error("(429): quota for model gemini-pro is used up"), "limit")


class TestCheckProvider(unittest.TestCase):
    def test_works_when_the_list_and_the_question_both_succeed(self):
        factory, client = _client({"message": {"content": "ok"}, "model": "m1"})
        out = pc.check_provider("gemini", " KEY ", "m1", list_fn=lambda k: {"success": True, "models": ["m1", "m2"]}, client_factory=factory)
        self.assertTrue(out["ok"], out)
        self.assertEqual((out["stage"], out["models"]), ("ready", ["m1", "m2"]))
        self.assertIn("2 models listed", out["message"])
        factory.assert_called_once_with("gemini", "KEY", "m1")  # the typed key is trimmed and used as typed
        self.assertEqual(client.complete.call_args.args[0][0]["content"], pc.CHECK_PROMPT)
        self.assertEqual(client.complete.call_args.kwargs["max_tokens"], 8)

    def test_a_missing_key_is_reported_before_anything_is_called(self):
        list_fn = MagicMock()
        out = pc.check_provider("openrouter", "  ", list_fn=list_fn)
        self.assertEqual((out["ok"], out["stage"]), (False, "key"))
        list_fn.assert_not_called()

    def test_a_list_error_is_classified(self):
        out = pc.check_provider("gemini", "k", list_fn=lambda k: {"error": "Gemini models list failed (403): Authentication failed -- check your API key."})
        self.assertEqual((out["ok"], out["stage"]), (False, "key"))

    def test_a_bad_openrouter_key_is_caught_by_the_question_because_the_list_is_public(self):
        factory, _ = _client({"error": "OpenRouter HTTP error (401): Authentication failed -- check your API key."})
        out = pc.check_provider("openrouter", "bad", list_fn=lambda k: {"success": True, "models": ["a"]}, client_factory=factory)
        self.assertEqual((out["ok"], out["stage"]), (False, "key"))

    def test_the_provider_falling_back_to_another_model_is_said_out_loud(self):
        factory, _ = _client({"message": {"content": "ok"}, "model": "other-model"})
        out = pc.check_provider("openrouter", "k", "wanted", list_fn=lambda k: {"success": True, "models": []}, client_factory=factory)
        self.assertTrue(out["ok"])
        self.assertIn("fell back to other-model", out["message"])

    def test_ollama_needs_no_key_and_checks_the_model_is_pulled(self):
        listing = lambda url: {"success": True, "models": ["llama3.1", "qwen"]}  # noqa: E731
        factory, _ = _client({"message": {"content": "ok"}})
        self.assertTrue(pc.check_provider("ollama", "", "qwen", list_fn=listing, client_factory=factory)["ok"])
        out = pc.check_provider("ollama", "", "mistral", list_fn=listing, client_factory=factory)
        self.assertEqual((out["ok"], out["stage"]), (False, "model"))
        self.assertIn("llama3.1", out["message"])

    def test_cartogen_has_nothing_to_test_yet(self):
        called = MagicMock()
        out = pc.check_provider("cartogen", "k", list_fn=called, client_factory=called)
        self.assertEqual((out["ok"], out["stage"]), (False, "unavailable"))
        called.assert_not_called()

    def test_an_unexpected_exception_never_escapes(self):
        def boom(_key):
            raise RuntimeError("secret-key-material")
        out = pc.check_provider("gemini", "k", list_fn=boom)
        self.assertEqual((out["ok"], out["stage"]), (False, "other"))
        self.assertNotIn("secret-key-material", out["message"])

    def test_unknown_provider(self):
        self.assertEqual(pc.check_provider("nope", "k")["stage"], "other")

    def test_the_key_is_never_part_of_a_result_message(self):
        factory, _ = _client({"message": {"content": "ok"}, "model": "m"})
        out = pc.check_provider("gemini", "AIzaSECRET", list_fn=lambda k: {"success": True, "models": []}, client_factory=factory)
        self.assertNotIn("AIzaSECRET", out["message"])


class TestOllamaUrl(unittest.TestCase):
    def test_normalisation(self):
        self.assertEqual(pc.ollama_chat_url(""), "http://localhost:11434/v1/chat/completions")
        self.assertEqual(pc.ollama_chat_url("http://10.0.0.5:11434"), "http://10.0.0.5:11434/v1/chat/completions")
        self.assertEqual(pc.ollama_chat_url("http://h/v1/chat/completions"), "http://h/v1/chat/completions")


class TestDialogWiring(unittest.TestCase):
    SOURCE = (Path(__file__).resolve().parents[1] / "src" / "cartogen_ai" / "core" / "ui" / "connections_dialog.py").read_text(encoding="utf-8")

    def test_the_test_button_uses_what_is_typed_and_saves_nothing(self):
        text = self.SOURCE
        body = text[text.index("    def _test_api"):text.index("    def _on_api_check")]
        self.assertIn("self._key_edits[provider].text().strip()", body)
        self.assertIn("_provider_check.check_provider(provider, key_text, model)", body)
        self.assertNotIn("save_credential", body)
        self.assertNotIn("setValue", body)

    def test_a_success_marks_the_provider_verified(self):
        text = self.SOURCE
        body = text[text.index("    def _on_api_check"):text.index("    def _signin_cli")]
        self.assertIn("_on_models_fetched(provider", body)
        self.assertIn("_verified_providers.add(provider)", body)


if __name__ == "__main__":
    unittest.main()
