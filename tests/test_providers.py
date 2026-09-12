# -*- coding: utf-8 -*-
import json
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.providers import OpenAIClient, ClaudeClient
from cartogen_ai.core.agent.providers.claude import to_anthropic_request, from_anthropic_response
from cartogen_ai.core.agent.providers import openrouter as openrouter_mod
from cartogen_ai.core.agent.providers import gemini as gemini_mod
from cartogen_ai.core.agent.providers import ollama as ollama_mod
from cartogen_ai.core.agent.providers import openai as openai_mod
from cartogen_ai.core.agent.providers import claude as claude_mod
from cartogen_ai.core.agent.providers import cartogen as cartogen_mod


def _mock_get_response(json_body):
    resp = MagicMock()
    resp.json.return_value = json_body
    resp.raise_for_status.return_value = None
    return resp


class TestNewProviders(unittest.TestCase):
    def test_openai_client_defaults(self):
        client = OpenAIClient(api_key="dummy")
        self.assertEqual(client.model, "gpt-5.6")
        self.assertEqual(client.base_url, "https://api.openai.com/v1/chat/completions")

    def test_claude_client_defaults(self):
        client = ClaudeClient(api_key="dummy")
        self.assertEqual(client.model, "claude-opus-5")
        self.assertEqual(client.base_url, "https://api.anthropic.com/v1/messages")

    def test_providers_accept_custom_model(self):
        client = OpenAIClient(api_key="dummy", model="some-custom-model")
        self.assertEqual(client.model, "some-custom-model")


class TestClaudeTranslation(unittest.TestCase):
    """The Claude adapter is the one provider that actually transforms the
    request/response shape (system field, input_schema, tool_use/tool_result
    content blocks) rather than just changing a URL -- so it gets its own
    focused round-trip tests."""

    def test_system_message_extracted_to_top_level(self):
        messages = [
            {"role": "system", "content": "You are a QGIS assistant."},
            {"role": "user", "content": "hello"},
        ]
        system_text, anthropic_messages, tools = to_anthropic_request(messages, None)
        self.assertEqual(system_text, "You are a QGIS assistant.")
        self.assertEqual(anthropic_messages, [{"role": "user", "content": "hello"}])
        self.assertIsNone(tools)

    def test_tools_schema_translated_to_input_schema(self):
        openai_tools = [{
            "type": "function",
            "function": {
                "name": "get_layers",
                "description": "List layers",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        _, _, anthropic_tools = to_anthropic_request([], openai_tools)
        self.assertEqual(anthropic_tools, [{
            "name": "get_layers",
            "description": "List layers",
            "input_schema": {"type": "object", "properties": {}},
        }])

    def test_assistant_tool_call_becomes_tool_use_block(self):
        messages = [{
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_layers", "arguments": "{}"},
            }],
        }]
        _, anthropic_messages, _ = to_anthropic_request(messages, None)
        self.assertEqual(anthropic_messages, [{
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "call_1", "name": "get_layers", "input": {}}],
        }])

    def test_tool_result_message_merged_into_single_user_turn(self):
        messages = [
            {"role": "tool", "tool_call_id": "call_1", "name": "get_layers", "content": '["a"]'},
            {"role": "tool", "tool_call_id": "call_2", "name": "get_crs", "content": '"EPSG:4326"'},
        ]
        _, anthropic_messages, _ = to_anthropic_request(messages, None)
        self.assertEqual(len(anthropic_messages), 1)
        self.assertEqual(anthropic_messages[0]["role"], "user")
        blocks = anthropic_messages[0]["content"]
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0], {"type": "tool_result", "tool_use_id": "call_1", "content": '["a"]'})
        self.assertEqual(blocks[1]["tool_use_id"], "call_2")

    def test_response_text_only_translates_to_openai_shape(self):
        data = {"content": [{"type": "text", "text": "Hello!"}], "model": "claude-opus-5"}
        result = from_anthropic_response(data, "claude-opus-5")
        self.assertEqual(result["message"], {"role": "assistant", "content": "Hello!"})
        self.assertNotIn("tool_calls", result["message"])

    def test_response_tool_use_translates_to_tool_calls(self):
        data = {
            "content": [{"type": "tool_use", "id": "toolu_1", "name": "get_layers", "input": {"x": 1}}],
            "model": "claude-opus-5",
        }
        result = from_anthropic_response(data, "claude-opus-5")
        message = result["message"]
        self.assertEqual(len(message["tool_calls"]), 1)
        call = message["tool_calls"][0]
        self.assertEqual(call["id"], "toolu_1")
        self.assertEqual(call["function"]["name"], "get_layers")
        self.assertEqual(json.loads(call["function"]["arguments"]), {"x": 1})

    def test_round_trip_assistant_tool_call_survives_reingestion(self):
        # Simulates agent.py: the OpenAI-shaped message returned by complete()
        # gets appended to history verbatim and fed back in on the next call.
        data = {
            "content": [{"type": "tool_use", "id": "toolu_9", "name": "buffer_analysis", "input": {"distance": 100}}],
            "model": "claude-opus-5",
        }
        first_result = from_anthropic_response(data, "claude-opus-5")
        history = [first_result["message"]]
        _, anthropic_messages, _ = to_anthropic_request(history, None)
        self.assertEqual(anthropic_messages, [{
            "role": "assistant",
            "content": [{
                "type": "tool_use", "id": "toolu_9", "name": "buffer_analysis", "input": {"distance": 100},
            }],
        }])

    def test_refusal_with_no_content_gets_readable_fallback_text(self):
        data = {"content": [], "model": "claude-opus-5", "stop_reason": "refusal"}
        result = from_anthropic_response(data, "claude-opus-5")
        self.assertIn("declined", result["message"]["content"])


class TestListModels(unittest.TestCase):
    """Each list_models() is tested against a mocked response matching that
    provider's real, WebFetch-verified schema -- no live network calls."""

    @patch("cartogen_ai.core.agent.providers.openrouter.requests.get")
    def test_openrouter_list_models(self, mock_get):
        mock_get.return_value = _mock_get_response({
            "data": [{"id": "openrouter/free"}, {"id": "openai/gpt-oss-20b:free"}]
        })
        result = openrouter_mod.list_models()
        self.assertTrue(result["success"])
        self.assertIn("openrouter/free", result["models"])

    @patch("cartogen_ai.core.agent.providers.openai.requests.get")
    def test_openai_list_models(self, mock_get):
        mock_get.return_value = _mock_get_response({"data": [{"id": "gpt-5.6-sol"}, {"id": "text-embedding-3-large"}]})
        result = openai_mod.list_models("dummy")
        self.assertTrue(result["success"])
        self.assertIn("gpt-5.6-sol", result["models"])
        self.assertNotIn("text-embedding-3-large", result["models"])

    @patch("cartogen_ai.core.agent.providers.claude.requests.get")
    def test_claude_list_models(self, mock_get):
        mock_get.return_value = _mock_get_response({
            "data": [{"type": "model", "id": "claude-opus-5"}, {"type": "model", "id": "claude-haiku-4-5"}]
        })
        result = claude_mod.list_models("dummy")
        self.assertTrue(result["success"])
        self.assertIn("claude-opus-5", result["models"])

    @patch("cartogen_ai.core.agent.providers.gemini.requests.get")
    def test_gemini_list_models_strips_prefix_and_filters(self, mock_get):
        mock_get.return_value = _mock_get_response({
            "models": [
                {"name": "models/gemini-flash-latest", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
            ]
        })
        result = gemini_mod.list_models("dummy")
        self.assertTrue(result["success"])
        self.assertIn("gemini-flash-latest", result["models"])
        self.assertNotIn("models/gemini-flash-latest", result["models"])
        self.assertNotIn("embedding-001", result["models"])

    @patch("cartogen_ai.core.agent.providers.gemini.requests.post")
    def test_gemini_grounded_search_extracts_text_and_sources(self, mock_post):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": "It rained yesterday."}]},
                "groundingMetadata": {
                    "groundingChunks": [{"web": {"uri": "https://example.com", "title": "Example"}}]
                },
            }]
        }
        mock_post.return_value = resp
        result = gemini_mod.grounded_search("dummy-key", "did it rain yesterday")
        self.assertTrue(result["success"])
        self.assertEqual(result["text"], "It rained yesterday.")
        self.assertEqual(result["sources"], [{"title": "Example", "url": "https://example.com"}])

    @patch("cartogen_ai.core.agent.providers.gemini.requests.post")
    def test_gemini_grounded_search_handles_empty_candidates(self, mock_post):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"candidates": []}
        mock_post.return_value = resp
        result = gemini_mod.grounded_search("dummy-key", "query")
        self.assertIn("error", result)

    @patch("cartogen_ai.core.agent.providers.gemini.requests.get")
    def test_gemini_list_models_uses_header_auth_not_query_param(self, mock_get):
        # docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md SS2.3: query-string
        # credentials are more likely to end up in server/proxy access logs than
        # a header, so list_models() must send the key via x-goog-api-key and
        # must NOT pass it as a '?key=' query param.
        mock_get.return_value = _mock_get_response({"models": []})
        gemini_mod.list_models("dummy-key")
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs.get("headers", {}).get("x-goog-api-key"), "dummy-key")
        self.assertNotIn("params", kwargs)

    @patch("cartogen_ai.core.agent.providers.gemini.requests.post")
    def test_gemini_grounded_search_uses_header_auth_not_query_param(self, mock_post):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"candidates": []}
        mock_post.return_value = resp
        gemini_mod.grounded_search("dummy-key", "header auth check query")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs.get("headers", {}).get("x-goog-api-key"), "dummy-key")
        self.assertNotIn("params", kwargs)

    def test_gemini_client_keeps_configured_model_first_in_chain(self):
        client = gemini_mod.GeminiClient(api_key="dummy", model="some-custom-model")
        self.assertEqual(client.models[0], "some-custom-model")
        self.assertEqual(client.model, "some-custom-model")
        # No duplicate if the configured model happens to also be a fallback
        client2 = gemini_mod.GeminiClient(api_key="dummy", model=gemini_mod.FALLBACK_MODELS[0])
        self.assertEqual(client2.models.count(gemini_mod.FALLBACK_MODELS[0]), 1)

    @patch("cartogen_ai.core.agent.providers.gemini.requests.post")
    def test_gemini_client_falls_back_on_404(self, mock_post):
        dead_model_resp = MagicMock()
        dead_model_resp.status_code = 404
        working_resp = MagicMock()
        working_resp.status_code = 200
        working_resp.raise_for_status.return_value = None
        working_resp.json.return_value = {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}
        mock_post.side_effect = [dead_model_resp, working_resp]

        client = gemini_mod.GeminiClient(api_key="dummy", model="gemini-2.5-pro")
        result = client.complete([{"role": "user", "content": "hello"}])
        self.assertEqual(result["message"]["content"], "hi")
        self.assertEqual(result["model"], client.models[1])

    @patch("cartogen_ai.core.agent.providers.gemini.requests.post")
    def test_gemini_client_returns_clear_error_when_all_models_404(self, mock_post):
        dead_resp = MagicMock()
        dead_resp.status_code = 404
        mock_post.return_value = dead_resp

        client = gemini_mod.GeminiClient(api_key="dummy", model="gemini-2.5-pro")
        result = client.complete([{"role": "user", "content": "hello"}])
        self.assertIn("error", result)
        self.assertIn("404", result["error"])

    def test_openai_client_keeps_configured_model_first_in_chain(self):
        client = openai_mod.OpenAIClient(api_key="dummy", model="some-custom-model")
        self.assertEqual(client.models[0], "some-custom-model")
        self.assertEqual(client.model, "some-custom-model")
        # No duplicate if the configured model happens to also be a fallback
        client2 = openai_mod.OpenAIClient(api_key="dummy", model=openai_mod.FALLBACK_MODELS[0])
        self.assertEqual(client2.models.count(openai_mod.FALLBACK_MODELS[0]), 1)

    @patch("cartogen_ai.core.agent.providers.openai.requests.post")
    def test_openai_client_falls_back_on_404(self, mock_post):
        dead_model_resp = MagicMock()
        dead_model_resp.status_code = 404
        working_resp = MagicMock()
        working_resp.status_code = 200
        working_resp.raise_for_status.return_value = None
        working_resp.json.return_value = {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}
        mock_post.side_effect = [dead_model_resp, working_resp]

        client = openai_mod.OpenAIClient(api_key="dummy", model="some-retired-model")
        result = client.complete([{"role": "user", "content": "hello"}])
        self.assertEqual(result["message"]["content"], "hi")
        self.assertEqual(result["model"], client.models[1])

    @patch("cartogen_ai.core.agent.providers.openai.requests.post")
    def test_openai_client_returns_clear_error_when_all_models_404(self, mock_post):
        dead_resp = MagicMock()
        dead_resp.status_code = 404
        mock_post.return_value = dead_resp

        client = openai_mod.OpenAIClient(api_key="dummy", model="some-retired-model")
        result = client.complete([{"role": "user", "content": "hello"}])
        self.assertIn("error", result)
        self.assertIn("404", result["error"])

    @patch("cartogen_ai.core.agent.providers.openai.requests.post")
    def test_openai_grounded_search_extracts_text_and_sources(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": "It rained yesterday.",
                    "annotations": [
                        {"url_citation": {"url": "https://example.com", "title": "Example"}},
                    ],
                },
            }],
        }
        mock_post.return_value = resp
        result = openai_mod.grounded_search("dummy-key", "did it rain yesterday")
        self.assertTrue(result["success"])
        self.assertEqual(result["text"], "It rained yesterday.")
        self.assertEqual(result["sources"], [{"title": "Example", "url": "https://example.com"}])

    @patch("cartogen_ai.core.agent.providers.openai.requests.post")
    def test_openai_grounded_search_handles_empty_choices(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"choices": []}
        mock_post.return_value = resp
        result = openai_mod.grounded_search("dummy-key", "query")
        self.assertIn("error", result)

    @patch("cartogen_ai.core.agent.providers.ollama.requests.get")
    def test_ollama_list_models(self, mock_get):
        mock_get.return_value = _mock_get_response({"models": [{"name": "llama3.1:latest"}]})
        result = ollama_mod.list_models("http://localhost:11434/v1/chat/completions")
        self.assertTrue(result["success"])
        self.assertIn("llama3.1:latest", result["models"])

    @patch("cartogen_ai.core.agent.providers.openai.requests.get")
    def test_list_models_http_error_returns_error_dict(self, mock_get):
        import requests
        http_error = requests.exceptions.HTTPError()
        http_error.response = MagicMock(status_code=401, text="unauthorized")
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = http_error
        mock_get.return_value = mock_response
        result = openai_mod.list_models("bad-key")
        self.assertIn("error", result)


class TestRetryWithBackoff(unittest.TestCase):
    """post_with_retry (agent/providers/base.py) is the shared HTTP call every
    raw-requests provider client now goes through -- a single transient
    429/5xx used to kill the whole agent turn with no retry at all."""

    @patch("cartogen_ai.core.agent.providers.base.time.sleep")
    @patch("cartogen_ai.core.agent.providers.base.requests.post")
    def test_retries_on_503_then_succeeds(self, mock_post, mock_sleep):
        from cartogen_ai.core.agent.providers.base import post_with_retry
        bad_resp = MagicMock(status_code=503)
        good_resp = MagicMock(status_code=200)
        mock_post.side_effect = [bad_resp, good_resp]

        result = post_with_retry("https://example.com", {}, "{}", timeout=60)

        self.assertIs(result, good_resp)
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("cartogen_ai.core.agent.providers.base.time.sleep")
    @patch("cartogen_ai.core.agent.providers.base.requests.post")
    def test_gives_up_after_max_retries_on_persistent_failure(self, mock_post, mock_sleep):
        from cartogen_ai.core.agent.providers.base import post_with_retry
        bad_resp = MagicMock(status_code=503)
        mock_post.return_value = bad_resp

        result = post_with_retry("https://example.com", {}, "{}", timeout=60, max_retries=2)

        # Returns the last (still-bad) response rather than raising -- the
        # caller's existing raise_for_status()/status-code handling takes it
        # from there, unchanged from before this fix.
        self.assertIs(result, bad_resp)
        self.assertEqual(mock_post.call_count, 3)  # 1 initial + 2 retries

    @patch("cartogen_ai.core.agent.providers.base.time.sleep")
    @patch("cartogen_ai.core.agent.providers.base.requests.post")
    def test_does_not_retry_on_permanent_client_error(self, mock_post, mock_sleep):
        from cartogen_ai.core.agent.providers.base import post_with_retry
        auth_error_resp = MagicMock(status_code=401)
        mock_post.return_value = auth_error_resp

        result = post_with_retry("https://example.com", {}, "{}", timeout=60)

        self.assertIs(result, auth_error_resp)
        self.assertEqual(mock_post.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("cartogen_ai.core.agent.providers.base.time.sleep")
    @patch("cartogen_ai.core.agent.providers.base.requests.post")
    def test_429_gets_the_longer_rate_limit_backoff_not_the_generic_one(self, mock_post, mock_sleep):
        """Large-multi-tool-call-task rate-limit resilience (2026-09-12): a 429 needs to wait
        out an actual per-minute quota window, not just a network blip, so it gets its own
        longer/higher-retry-count budget (RATE_LIMIT_BACKOFF_SECONDS/RATE_LIMIT_MAX_RETRIES) --
        distinct from DEFAULT_BACKOFF_SECONDS/DEFAULT_MAX_RETRIES, which 5xx still uses."""
        from cartogen_ai.core.agent.providers.base import (
            post_with_retry, RATE_LIMIT_BACKOFF_SECONDS, RATE_LIMIT_MAX_RETRIES,
        )
        rate_limited = MagicMock(status_code=429)
        good_resp = MagicMock(status_code=200)
        # max_retries=2 (the generic default) -- 429 must still get its own bigger budget,
        # not be capped by the smaller generic one.
        mock_post.side_effect = [rate_limited, rate_limited, rate_limited, good_resp]

        result = post_with_retry("https://example.com", {}, "{}", timeout=60, max_retries=2)

        self.assertIs(result, good_resp)
        self.assertEqual(mock_post.call_count, 4)
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertEqual(sleep_calls, [
            RATE_LIMIT_BACKOFF_SECONDS * 1, RATE_LIMIT_BACKOFF_SECONDS * 2, RATE_LIMIT_BACKOFF_SECONDS * 3,
        ])

    @patch("cartogen_ai.core.agent.providers.base.time.sleep")
    @patch("cartogen_ai.core.agent.providers.base.requests.post")
    def test_429_retries_exhausted_returns_response_does_not_raise(self, mock_post, mock_sleep):
        from cartogen_ai.core.agent.providers.base import post_with_retry
        rate_limited = MagicMock(status_code=429)
        mock_post.return_value = rate_limited

        # Caller's own raise_for_status()/status-code handling takes it from here, same
        # contract as the generic 5xx-exhausted case (test_gives_up_after_max_retries_...).
        result = post_with_retry("https://example.com", {}, "{}", timeout=60)

        self.assertIs(result, rate_limited)
        self.assertEqual(mock_post.call_count, 4)  # 1 initial + RATE_LIMIT_MAX_RETRIES (3)

    @patch("cartogen_ai.core.agent.providers.base.time.sleep")
    @patch("cartogen_ai.core.agent.providers.base.requests.post")
    def test_mixed_429_then_503_both_get_retried_correctly(self, mock_post, mock_sleep):
        from cartogen_ai.core.agent.providers.base import (
            post_with_retry, RATE_LIMIT_BACKOFF_SECONDS, DEFAULT_BACKOFF_SECONDS,
        )
        rate_limited = MagicMock(status_code=429)
        server_error = MagicMock(status_code=503)
        good_resp = MagicMock(status_code=200)
        mock_post.side_effect = [rate_limited, server_error, good_resp]

        result = post_with_retry("https://example.com", {}, "{}", timeout=60)

        self.assertIs(result, good_resp)
        self.assertEqual(mock_post.call_count, 3)
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        # First retry uses the 429 (attempt=0) budget, second uses the generic 5xx (attempt=1)
        # budget -- each status code's own backoff schedule, not a shared/confused one.
        self.assertEqual(sleep_calls, [RATE_LIMIT_BACKOFF_SECONDS * 1, DEFAULT_BACKOFF_SECONDS * 2])


class TestOllamaRetryAndErrorHandling(unittest.TestCase):
    """ollama.py previously called requests.post directly, bypassing the
    shared retry helper every other provider client uses (docs/
    docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md §2.1) -- the local server is
    the client most likely to hit a transient failure in practice (still
    loading a model), so it's the one that most needed the retry. It also had
    a generic except-Exception handler that mislabeled a malformed-response
    KeyError as "connection failed" (§2.2) -- both fixed together since
    they're in the same method."""

    @patch("cartogen_ai.core.agent.providers.base.time.sleep")
    @patch("cartogen_ai.core.agent.providers.base.requests.post")
    def test_ollama_retries_on_transient_5xx_then_succeeds(self, mock_post, mock_sleep):
        bad_resp = MagicMock(status_code=503)
        good_resp = MagicMock(status_code=200)
        good_resp.raise_for_status.return_value = None
        good_resp.json.return_value = {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}
        mock_post.side_effect = [bad_resp, good_resp]

        client = ollama_mod.OllamaClient()
        result = client.complete([{"role": "user", "content": "hi"}])

        self.assertEqual(result["message"]["content"], "hi")
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("cartogen_ai.core.agent.providers.ollama.post_with_retry")
    def test_ollama_malformed_response_reports_unexpected_format_not_connection_failure(self, mock_post):
        resp = MagicMock(status_code=200)
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"unexpected": "shape, no 'choices' key"}
        mock_post.return_value = resp

        client = ollama_mod.OllamaClient()
        result = client.complete([{"role": "user", "content": "hi"}])

        self.assertIn("error", result)
        self.assertIn("Unexpected response format", result["error"])
        self.assertNotIn("connection failed", result["error"].lower())

    @patch("cartogen_ai.core.agent.providers.ollama.post_with_retry")
    def test_ollama_real_connection_failure_still_reports_connection_failed(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")

        client = ollama_mod.OllamaClient()
        result = client.complete([{"role": "user", "content": "hi"}])

        self.assertIn("error", result)
        self.assertIn("Ollama connection failed", result["error"])


class TestProviderReturnContract(unittest.TestCase):
    """agent.py's tool-calling loop depends on every provider client's
    complete() returning exactly one of two shapes: {"message": ..., "model":
    ...} on success, or {"error": ...} on failure -- nothing else, no extra
    top-level keys agent.py doesn't know to look for. This is the shared
    contract docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md §2.5 flagged as
    worth enforcing explicitly so a future provider (or a change to an
    existing one) can't silently drift from it and only be noticed when
    agent.py's loop breaks somewhere downstream. Covers all 6 provider
    clients, including the not-yet-wired-in cartogen.py stub -- the contract
    should hold for it too, same as every real client."""

    SUCCESS_KEYS = {"message", "model"}
    # 'usage' is optional on success -- present when the provider's raw response
    # actually reported token counts (see base.extract_openai_style_usage's
    # docstring: never fabricated as zero when a provider/model omits it).
    OPTIONAL_SUCCESS_KEYS = {"usage"}
    ERROR_KEYS = {"error"}

    def _assert_contract_shape(self, result):
        keys = set(result.keys())
        if keys == self.ERROR_KEYS:
            return
        self.assertTrue(
            self.SUCCESS_KEYS.issubset(keys) and keys.issubset(self.SUCCESS_KEYS | self.OPTIONAL_SUCCESS_KEYS),
            f"complete() returned unexpected top-level keys {keys} -- must be exactly "
            f"{self.SUCCESS_KEYS} (optionally plus {self.OPTIONAL_SUCCESS_KEYS}) on success, "
            f"or exactly {self.ERROR_KEYS} on failure.",
        )

    @patch("cartogen_ai.core.agent.providers.openrouter.post_with_retry")
    def test_openrouter_success_shape(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"role": "assistant", "content": "hi"}}]},
        )
        client = openrouter_mod.OpenRouterClient(api_key="dummy")
        self._assert_contract_shape(client.complete([{"role": "user", "content": "hi"}]))

    @patch("cartogen_ai.core.agent.providers.openrouter.post_with_retry")
    def test_openrouter_error_shape(self, mock_post):
        # 404 on every model in the fallback chain exhausts it without ever
        # reaching raise_for_status() -- matches this client's own real
        # control flow (only 429/404 are special-cased; see _request_with_fallback).
        mock_post.return_value = MagicMock(status_code=404)
        client = openrouter_mod.OpenRouterClient(api_key="dummy")
        result = client.complete([{"role": "user", "content": "hi"}])
        self._assert_contract_shape(result)
        self.assertIn("error", result)

    @patch("cartogen_ai.core.agent.providers.gemini.post_with_retry")
    def test_gemini_success_shape(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"role": "assistant", "content": "hi"}}]},
        )
        client = gemini_mod.GeminiClient(api_key="dummy")
        self._assert_contract_shape(client.complete([{"role": "user", "content": "hi"}]))

    @patch("cartogen_ai.core.agent.providers.openai.post_with_retry")
    def test_openai_success_shape(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"role": "assistant", "content": "hi"}}]},
        )
        client = openai_mod.OpenAIClient(api_key="dummy")
        self._assert_contract_shape(client.complete([{"role": "user", "content": "hi"}]))

    @patch("cartogen_ai.core.agent.providers.claude.post_with_retry")
    def test_claude_success_shape(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"content": [{"type": "text", "text": "hi"}], "model": "claude-opus-5"},
        )
        client = claude_mod.ClaudeClient(api_key="dummy")
        self._assert_contract_shape(client.complete([{"role": "user", "content": "hi"}]))

    @patch("cartogen_ai.core.agent.providers.ollama.post_with_retry")
    def test_ollama_success_shape(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"role": "assistant", "content": "hi"}}]},
        )
        client = ollama_mod.OllamaClient()
        self._assert_contract_shape(client.complete([{"role": "user", "content": "hi"}]))

    @patch("cartogen_ai.core.agent.providers.ollama.post_with_retry")
    def test_ollama_error_shape(self, mock_post):
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")
        client = ollama_mod.OllamaClient()
        result = client.complete([{"role": "user", "content": "hi"}])
        self._assert_contract_shape(result)
        self.assertIn("error", result)

    @patch("cartogen_ai.core.agent.providers.cartogen.post_with_retry")
    def test_cartogen_stub_success_shape(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"role": "assistant", "content": "hi"}}]},
        )
        client = cartogen_mod.CartogenClient(api_key="dummy")
        self._assert_contract_shape(client.complete([{"role": "user", "content": "hi"}]))

    @patch("cartogen_ai.core.agent.providers.cartogen.post_with_retry")
    def test_cartogen_stub_error_shape(self, mock_post):
        mock_post.return_value = MagicMock(status_code=404)
        client = cartogen_mod.CartogenClient(api_key="dummy")
        result = client.complete([{"role": "user", "content": "hi"}])
        self._assert_contract_shape(result)
        self.assertIn("error", result)


class TestUsageExtraction(unittest.TestCase):
    """docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md SS3.2 ("no cost/usage
    visibility in the UI"): every provider's complete() now pulls a normalized
    {'input_tokens', 'output_tokens'} 'usage' dict out of the raw response when
    the provider actually reported one, via base.extract_openai_style_usage
    (OpenAI-compatible providers) or its own inline extraction (Claude's native
    field names already match; Ollama's endpoint uses different native field
    names entirely). Never fabricated as zero when the response omits it --
    covered by TestProviderReturnContract's success-shape tests above, which
    use mock responses with no 'usage' key at all and assert the strict
    {'message', 'model'} shape still holds with nothing extra added."""

    @patch("cartogen_ai.core.agent.providers.openrouter.post_with_retry")
    def test_openrouter_extracts_usage_when_present(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
            },
        )
        client = openrouter_mod.OpenRouterClient(api_key="dummy")
        result = client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(result["usage"], {"input_tokens": 120, "output_tokens": 30})

    @patch("cartogen_ai.core.agent.providers.openai.post_with_retry")
    def test_openai_extracts_usage_when_present(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 200, "completion_tokens": 50, "total_tokens": 250},
            },
        )
        client = openai_mod.OpenAIClient(api_key="dummy")
        result = client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(result["usage"], {"input_tokens": 200, "output_tokens": 50})

    @patch("cartogen_ai.core.agent.providers.gemini.post_with_retry")
    def test_gemini_extracts_usage_when_present(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
            },
        )
        client = gemini_mod.GeminiClient(api_key="dummy")
        result = client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(result["usage"], {"input_tokens": 80, "output_tokens": 20})

    @patch("cartogen_ai.core.agent.providers.claude.post_with_retry")
    def test_claude_extracts_usage_when_present(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "content": [{"type": "text", "text": "hi"}],
                "model": "claude-opus-5",
                "usage": {"input_tokens": 300, "output_tokens": 75},
            },
        )
        client = claude_mod.ClaudeClient(api_key="dummy")
        result = client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(result["usage"], {"input_tokens": 300, "output_tokens": 75})

    @patch("cartogen_ai.core.agent.providers.ollama.post_with_retry")
    def test_ollama_extracts_usage_when_present(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "prompt_eval_count": 40,
                "eval_count": 10,
            },
        )
        client = ollama_mod.OllamaClient()
        result = client.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(result["usage"], {"input_tokens": 40, "output_tokens": 10})

    @patch("cartogen_ai.core.agent.providers.openrouter.post_with_retry")
    def test_openrouter_omits_usage_key_entirely_when_not_reported(self, mock_post):
        # The critical honesty check: no 'usage' key at all, not a fabricated
        # {'input_tokens': 0, 'output_tokens': 0} -- a model/provider that
        # doesn't report usage must show as unknown to the UI, not as free.
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"role": "assistant", "content": "hi"}}]},
        )
        client = openrouter_mod.OpenRouterClient(api_key="dummy")
        result = client.complete([{"role": "user", "content": "hi"}])
        self.assertNotIn("usage", result)


class TestGroundedSearchCaching(unittest.TestCase):
    """gemini_grounded_search/openai_grounded_search are real, billed LLM API
    calls with no caching before this (unlike search_web, free DuckDuckGo).
    Each test uses a query string not used by any other test in this file --
    the cache is a module-level singleton shared across the whole test run,
    so a reused query would silently hit an earlier test's cached result."""

    @patch("cartogen_ai.core.agent.providers.gemini.requests.post")
    def test_gemini_second_identical_call_is_served_from_cache(self, mock_post):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "answer"}]}}]}
        mock_post.return_value = resp

        first = gemini_mod.grounded_search("dummy-key", "unique gemini cache query")
        second = gemini_mod.grounded_search("dummy-key", "unique gemini cache query")

        self.assertEqual(mock_post.call_count, 1)
        self.assertNotIn("cached", first)
        self.assertTrue(second.get("cached"))
        self.assertEqual(second["text"], "answer")

    @patch("cartogen_ai.core.agent.providers.gemini.requests.post")
    def test_gemini_cache_key_is_case_and_whitespace_insensitive(self, mock_post):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "answer"}]}}]}
        mock_post.return_value = resp

        gemini_mod.grounded_search("dummy-key", "  Gemini Case Query  ")
        gemini_mod.grounded_search("dummy-key", "gemini case query")

        self.assertEqual(mock_post.call_count, 1)

    @patch("cartogen_ai.core.agent.providers.gemini.requests.post")
    def test_gemini_error_response_is_not_cached(self, mock_post):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"candidates": []}
        mock_post.return_value = resp

        gemini_mod.grounded_search("dummy-key", "gemini error not cached query")
        gemini_mod.grounded_search("dummy-key", "gemini error not cached query")

        self.assertEqual(mock_post.call_count, 2)

    @patch("cartogen_ai.core.agent.providers.openai.post_with_retry")
    def test_openai_second_identical_call_is_served_from_cache(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"choices": [{"message": {"content": "answer"}}]}
        mock_post.return_value = resp

        first = openai_mod.grounded_search("dummy-key", "unique openai cache query")
        second = openai_mod.grounded_search("dummy-key", "unique openai cache query")

        self.assertEqual(mock_post.call_count, 1)
        self.assertNotIn("cached", first)
        self.assertTrue(second.get("cached"))

    @patch("cartogen_ai.core.agent.providers.openai.post_with_retry")
    def test_openai_error_response_is_not_cached(self, mock_post):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"choices": []}
        mock_post.return_value = resp

        openai_mod.grounded_search("dummy-key", "openai error not cached query")
        openai_mod.grounded_search("dummy-key", "openai error not cached query")

        self.assertEqual(mock_post.call_count, 2)


class TestOpenRouterAnthropicCacheControl(unittest.TestCase):
    """OpenRouter's OpenAI-compatible endpoint passes cache_control through
    unmodified to the underlying Anthropic API for anthropic/* models --
    unverified against a live response in this environment (no network
    access), see the function's own docstring."""

    def test_noop_for_non_anthropic_model(self):
        messages = [{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "hi"}]
        result = openrouter_mod._apply_anthropic_cache_control(messages, "openai/gpt-oss-20b:free")
        self.assertEqual(result, messages)

    def test_marks_system_message_for_anthropic_model(self):
        messages = [{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "hi"}]
        result = openrouter_mod._apply_anthropic_cache_control(messages, "anthropic/claude-opus-5")
        self.assertEqual(
            result[0]["content"],
            [{"type": "text", "text": "You are helpful.", "cache_control": {"type": "ephemeral"}}],
        )
        self.assertEqual(result[1], {"role": "user", "content": "hi"})

    def test_only_marks_first_system_message(self):
        messages = [
            {"role": "system", "content": "First."},
            {"role": "system", "content": "Second."},
        ]
        result = openrouter_mod._apply_anthropic_cache_control(messages, "anthropic/claude-opus-5")
        self.assertIsInstance(result[0]["content"], list)
        self.assertEqual(result[1]["content"], "Second.")

    def test_leaves_non_string_system_content_untouched(self):
        # Defensive: if a system message's content is ever already
        # multi-part (a list), don't assume it's a plain string and corrupt it.
        messages = [{"role": "system", "content": [{"type": "text", "text": "already structured"}]}]
        result = openrouter_mod._apply_anthropic_cache_control(messages, "anthropic/claude-opus-5")
        self.assertEqual(result, messages)

    @patch("cartogen_ai.core.agent.providers.openrouter.post_with_retry")
    def test_post_applies_cache_control_for_anthropic_model_id(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        client = openrouter_mod.OpenRouterClient(api_key="dummy", model="anthropic/claude-opus-5")
        client._post([{"role": "system", "content": "sys"}], None, "anthropic/claude-opus-5")

        sent_payload = json.loads(mock_post.call_args[0][2])
        self.assertEqual(
            sent_payload["messages"][0]["content"][0]["cache_control"], {"type": "ephemeral"}
        )


class TestMaxTokensCap(unittest.TestCase):
    """Only Claude's client capped output size before this (its own local
    DEFAULT_MAX_TOKENS) -- see docs/archive/API_COST_OPTIMIZATION_REVIEW.md section
    3: rarely an issue in practice, but a real, if uncommon, runaway-output
    cost risk with nothing standardizing it across the other 4 clients."""

    @patch("cartogen_ai.core.agent.providers.openai.post_with_retry")
    def test_openai_sends_max_tokens(self, mock_post):
        from cartogen_ai.core.agent.providers.base import DEFAULT_MAX_TOKENS
        mock_post.return_value = MagicMock(status_code=200)
        client = openai_mod.OpenAIClient(api_key="dummy")
        client._post([{"role": "user", "content": "hi"}], None, client.model)
        sent_payload = json.loads(mock_post.call_args[0][2])
        self.assertEqual(sent_payload["max_tokens"], DEFAULT_MAX_TOKENS)

    @patch("cartogen_ai.core.agent.providers.gemini.post_with_retry")
    def test_gemini_sends_max_tokens(self, mock_post):
        from cartogen_ai.core.agent.providers.base import DEFAULT_MAX_TOKENS
        mock_post.return_value = MagicMock(status_code=200)
        client = gemini_mod.GeminiClient(api_key="dummy")
        client._post([{"role": "user", "content": "hi"}], None, client.model)
        sent_payload = json.loads(mock_post.call_args[0][2])
        self.assertEqual(sent_payload["max_tokens"], DEFAULT_MAX_TOKENS)

    @patch("cartogen_ai.core.agent.providers.openrouter.post_with_retry")
    def test_openrouter_sends_max_tokens(self, mock_post):
        from cartogen_ai.core.agent.providers.base import DEFAULT_MAX_TOKENS
        mock_post.return_value = MagicMock(status_code=200)
        client = openrouter_mod.OpenRouterClient(api_key="dummy")
        client._post([{"role": "user", "content": "hi"}], None, client.model)
        sent_payload = json.loads(mock_post.call_args[0][2])
        self.assertEqual(sent_payload["max_tokens"], DEFAULT_MAX_TOKENS)

    @patch("cartogen_ai.core.agent.providers.ollama.post_with_retry")
    def test_ollama_sends_max_tokens(self, mock_post):
        from cartogen_ai.core.agent.providers.base import DEFAULT_MAX_TOKENS
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}
        mock_post.return_value = resp
        client = ollama_mod.OllamaClient()
        client.complete([{"role": "user", "content": "hi"}])
        sent_payload = json.loads(mock_post.call_args[0][2])
        self.assertEqual(sent_payload["max_tokens"], DEFAULT_MAX_TOKENS)

    # An explicit max_tokens override reaches the payload for every client --
    # needed for agent/prompt_refiner.py (docs/archive/PROMPT_REFINEMENT_LAYER_SPEC.md
    # §5.2), whose refinement call needs a few hundred tokens, not
    # DEFAULT_MAX_TOKENS=8096. Each test picks a value distinct from the
    # default so a regression to "always DEFAULT_MAX_TOKENS" would fail loudly.

    @patch("cartogen_ai.core.agent.providers.claude.post_with_retry")
    def test_claude_honors_max_tokens_override(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"content": [{"type": "text", "text": "hi"}], "model": "claude-opus-5"},
        )
        client = ClaudeClient(api_key="dummy")
        client.complete([{"role": "user", "content": "hi"}], max_tokens=400)
        sent_payload = json.loads(mock_post.call_args[0][2])
        self.assertEqual(sent_payload["max_tokens"], 400)

    @patch("cartogen_ai.core.agent.providers.openai.post_with_retry")
    def test_openai_honors_max_tokens_override(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        client = openai_mod.OpenAIClient(api_key="dummy")
        client._post([{"role": "user", "content": "hi"}], None, client.model, max_tokens=400)
        sent_payload = json.loads(mock_post.call_args[0][2])
        self.assertEqual(sent_payload["max_tokens"], 400)

    @patch("cartogen_ai.core.agent.providers.gemini.post_with_retry")
    def test_gemini_honors_max_tokens_override(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        client = gemini_mod.GeminiClient(api_key="dummy")
        client._post([{"role": "user", "content": "hi"}], None, client.model, max_tokens=400)
        sent_payload = json.loads(mock_post.call_args[0][2])
        self.assertEqual(sent_payload["max_tokens"], 400)

    @patch("cartogen_ai.core.agent.providers.openrouter.post_with_retry")
    def test_openrouter_honors_max_tokens_override(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        client = openrouter_mod.OpenRouterClient(api_key="dummy")
        client._post([{"role": "user", "content": "hi"}], None, client.model, max_tokens=400)
        sent_payload = json.loads(mock_post.call_args[0][2])
        self.assertEqual(sent_payload["max_tokens"], 400)

    @patch("cartogen_ai.core.agent.providers.ollama.post_with_retry")
    def test_ollama_honors_max_tokens_override(self, mock_post):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}
        mock_post.return_value = resp
        client = ollama_mod.OllamaClient()
        client.complete([{"role": "user", "content": "hi"}], max_tokens=400)
        sent_payload = json.loads(mock_post.call_args[0][2])
        self.assertEqual(sent_payload["max_tokens"], 400)


class TestClaudePromptCaching(unittest.TestCase):
    @patch("cartogen_ai.core.agent.providers.claude.post_with_retry")
    def test_system_and_last_tool_marked_as_cache_breakpoints(self, mock_post):
        mock_post.return_value = _mock_get_response({"content": [{"type": "text", "text": "hi"}], "model": "claude-opus-5"})
        client = ClaudeClient(api_key="dummy")
        tools = [
            {"type": "function", "function": {"name": "a", "description": "", "parameters": {}}},
            {"type": "function", "function": {"name": "b", "description": "", "parameters": {}}},
        ]
        client.complete([{"role": "system", "content": "You are helpful."}, {"role": "user", "content": "hi"}], tools=tools)

        sent_payload = json.loads(mock_post.call_args[0][2])
        self.assertEqual(sent_payload["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("cache_control", sent_payload["tools"][0])
        self.assertEqual(sent_payload["tools"][-1]["cache_control"], {"type": "ephemeral"})


if __name__ == "__main__":
    unittest.main()
