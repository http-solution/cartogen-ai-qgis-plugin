# -*- coding: utf-8 -*-
"""Automatic model selection, end to end (cost review, 2026-09-25).

Found: agent_orchestrator._apply_auto_model_selection assigned `client.model = picked`, but the
Gemini, OpenAI, OpenRouter and Cartogen clients loop over a fallback list built once in __init__
and overwrote `self.model` with its first entry, so the pick was discarded and the configured (on
OpenAI, the priciest) model was sent every time. Fresh installs default to auto, so this affected
default installs. Making the pick take effect exposed the next problem, found by running the
picker on a real cached Gemini model list: substring keywords made every "gemini-*" a "mini", and
a complex request would have gone to "deep-research-max-preview-04-2026". Both are covered here."""
import importlib
import json
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent import agent_orchestrator as agent_mod
from cartogen_ai.core.agent.model_selector import (
    is_cheap_tier, is_special_purpose, pick_model_for_complexity,
)

# A real list: the 31 models cached in a user's QGIS profile, section [cartogen_ai], by Settings >
# "Fetch models" (Gemini), 2026-09-25.
REAL_GEMINI_LIST = [
    "antigravity-preview-05-2026", "deep-research-max-preview-04-2026",
    "deep-research-preview-04-2026", "deep-research-pro-preview-12-2025",
    "gemini-2.5-computer-use-preview-10-2025", "gemini-2.5-flash", "gemini-2.5-flash-lite",
    "gemini-2.5-pro", "gemini-3-flash-preview", "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview", "gemini-3.1-pro-preview",
    "gemini-3.1-pro-preview-customtools", "gemini-3.5-flash", "gemini-3.5-flash-lite",
    "gemini-3.5-transcribe", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash",
    "gemini-flash-latest", "gemini-flash-lite-latest", "gemini-omni-1.1-flash",
    "gemini-omni-flash-preview", "gemini-pro-latest", "gemini-robotics-er-2-preview",
    "gemma-4-26b-a4b-it", "gemma-4-31b-it", "lyria-3-clip-preview", "lyria-3-pro-preview",
    "lyria-3.5", "nano-banana-pro-preview",
]
OPENAI_LIST = ["gpt-5.6", "gpt-5.2-chat-latest", "gpt-5-mini", "gpt-5-nano", "gpt-5-pro", "o4-mini",
               "gpt-4.1", "gpt-5-codex", "gpt-realtime", "gpt-5-search-api"]
CLAUDE_LIST = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5-20251001", "claude-opus-4-1"]


class TestPickerOnRealLists(unittest.TestCase):
    def test_special_purpose_models_are_never_picked(self):
        for tier in ("simple", "complex"):
            picked = pick_model_for_complexity(REAL_GEMINI_LIST, tier)
            self.assertFalse(is_special_purpose(picked), (tier, picked))
        self.assertTrue(is_special_purpose("deep-research-max-preview-04-2026"))
        self.assertTrue(is_special_purpose("gemini-robotics-er-2-preview"))
        self.assertTrue(is_special_purpose("gpt-5-codex"))
        self.assertFalse(is_special_purpose("gemini-2.5-pro"))

    def test_gemini_is_not_mistaken_for_mini(self):
        # substring matching made "gemini-2.5-pro" a "cheap" model
        self.assertFalse(is_cheap_tier("gemini-2.5-pro"))
        self.assertFalse(is_cheap_tier("gemini-pro-latest"))
        self.assertTrue(is_cheap_tier("gemini-2.5-flash"))
        self.assertTrue(is_cheap_tier("gpt-5-mini"))
        self.assertTrue(is_cheap_tier("claude-haiku-4-5-20251001"))

    def test_simple_prefers_flash_over_the_weaker_lite_and_a_latest_alias_over_a_version(self):
        self.assertEqual(pick_model_for_complexity(REAL_GEMINI_LIST, "simple"), "gemini-flash-latest")
        without_alias = [m for m in REAL_GEMINI_LIST if "latest" not in m]
        picked = pick_model_for_complexity(without_alias, "simple")
        self.assertEqual(picked, "gemini-3.8-flash")           # newest stable plain flash
        self.assertNotIn("lite", picked)

    def test_openai_and_claude_lists(self):
        self.assertEqual(pick_model_for_complexity(OPENAI_LIST, "simple"), "gpt-5-mini")  # not nano
        self.assertEqual(pick_model_for_complexity(CLAUDE_LIST, "simple"), "claude-haiku-4-5-20251001")
        self.assertEqual(pick_model_for_complexity(CLAUDE_LIST, "complex"), "claude-opus-5")

    def test_a_list_of_only_special_purpose_models_returns_nothing(self):
        # Review finding P1: this used to fall back to the whole list, so "nano-banana-pro-preview"
        # (a special-purpose model carrying the cheap token "nano") could be picked for simple
        # requests and then accepted as cheap. "Don't optimise" beats picking an unsuitable model.
        only = ["nano-banana-pro-preview", "lyria-3-clip-preview", "deep-research-preview-04-2026"]
        for tier in ("simple", "complex"):
            self.assertEqual(pick_model_for_complexity(only, tier), "", tier)
        self.assertEqual(pick_model_for_complexity([], "simple"), "")

    def test_stability_ranks_before_a_latest_alias(self):
        # Review finding P2: a name containing "latest" does not make the model stable.
        self.assertEqual(
            pick_model_for_complexity(["model-flash-latest-preview", "model-flash-3.6"], "simple"),
            "model-flash-3.6")
        self.assertEqual(
            pick_model_for_complexity(["model-flash-3.6", "model-flash-latest"], "simple"),
            "model-flash-latest")                         # a stable alias still wins over a version
        self.assertEqual(
            pick_model_for_complexity(["model-flash-preview", "model-flash-2.5"], "simple"),
            "model-flash-2.5")                            # even an older stable model beats a preview


PROVIDERS = [("gemini", "GeminiClient"), ("openai", "OpenAIClient"),
             ("openrouter", "OpenRouterClient"), ("cartogen", "CartogenClient")]


def _resp(code, ok_body=None):
    r = MagicMock()
    r.status_code = code
    r.json.return_value = ok_body or {"choices": [{"message": {"role": "assistant", "content": "hi"}}],
                                      "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    r.text = "{}"
    r.raise_for_status.return_value = None
    return r


class TestProvidersSendTheChosenModel(unittest.TestCase):
    def _client(self, mod, cls):
        m = importlib.import_module("cartogen_ai.infrastructure.providers." + mod)
        return getattr(m, cls)("test-key")

    def test_the_model_assigned_from_outside_is_the_first_one_sent(self):
        for mod, cls in PROVIDERS:
            c = self._client(mod, cls)
            sent = []
            with patch.object(c, "_post", side_effect=lambda msgs, tools, model_id, max_tokens=None:
                              (sent.append(model_id), _resp(200))[1]):
                c.model = "cheap-pick"
                c.complete([{"role": "user", "content": "hi"}])
            self.assertEqual(sent, ["cheap-pick"], mod)          # was: the configured model
            self.assertEqual(c.model, "cheap-pick", mod)          # `model` reports what was used

    def test_without_an_outside_assignment_the_configured_model_is_still_first(self):
        for mod, cls in PROVIDERS:
            c = self._client(mod, cls)
            configured = c.model
            sent = []
            with patch.object(c, "_post", side_effect=lambda msgs, tools, model_id, max_tokens=None:
                              (sent.append(model_id), _resp(200))[1]):
                c.complete([{"role": "user", "content": "hi"}])
            self.assertEqual(sent, [configured], mod)

    def test_a_dead_pick_falls_back_to_the_chain_and_the_fallback_does_not_stick(self):
        for mod, cls in PROVIDERS:
            c = self._client(mod, cls)
            configured = c.model
            sent = []

            def post(msgs, tools, model_id, max_tokens=None):
                sent.append(model_id)
                return _resp(404 if model_id == "dead-pick" else 200)
            with patch.object(c, "_post", side_effect=post):
                c.model = "dead-pick"
                c.complete([{"role": "user", "content": "a"}])
                self.assertEqual(sent, ["dead-pick", configured], mod)
                self.assertEqual(c.model, configured, mod)        # reports the model that answered
                c.model = configured                              # the next turn assigns again
                c.complete([{"role": "user", "content": "b"}])
            self.assertEqual(sent[-1], configured, mod)

    def test_the_preference_survives_a_fallback_without_reassignment(self):
        # Review finding P3: the test above reassigns `model` itself before the second call, so it
        # doesn't show what the provider does on its own. After a fallback the original preference
        # must still be the first model attempted next time (a fallback is not a new preference).
        for mod, cls in PROVIDERS:
            c = self._client(mod, cls)
            configured = c.model
            sent = []

            def post(msgs, tools, model_id, max_tokens=None):
                sent.append(model_id)
                return _resp(404 if model_id == "dead-pick" else 200)
            with patch.object(c, "_post", side_effect=post):
                c.model = "dead-pick"
                c.complete([{"role": "user", "content": "a"}])
                self.assertEqual(c._preferred_model, "dead-pick", mod)
                self.assertEqual(c.model, configured, mod)     # reports what actually answered
                sent.clear()
                c.complete([{"role": "user", "content": "b"}])  # no reassignment
            self.assertEqual(sent[0], "dead-pick", mod)         # the preference is tried first again

    def test_when_every_model_404s_the_error_lists_the_models_tried_including_the_pick(self):
        for mod, cls in PROVIDERS:
            c = self._client(mod, cls)
            with patch.object(c, "_post", side_effect=lambda *a, **k: _resp(404)), \
                 patch("time.sleep"):
                c.model = "dead-pick"
                out = c.complete([{"role": "user", "content": "hi"}])
            self.assertIn("dead-pick", json.dumps(out), mod)


class TestOrchestratorPolicy(unittest.TestCase):
    """_apply_auto_model_selection: only ever steps down from the built-in default."""

    def _agent(self, default, provider="openai"):
        a = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        a._auto_model_provider = provider
        a._auto_default_model = default
        a.client = MagicMock()
        a.client.model = default
        return a

    def _select(self, agent, query, model_list):
        settings = MagicMock()
        settings.value.return_value = json.dumps(model_list)
        with patch.object(agent_mod, "QgsSettings", return_value=settings):
            agent._apply_auto_model_selection(query)
        return agent.client.model

    def test_simple_request_steps_down_from_an_expensive_default(self):
        a = self._agent("gpt-5.6")
        self.assertEqual(self._select(a, "list layers", OPENAI_LIST), "gpt-5-mini")

    def test_complex_request_uses_the_default_never_a_pricier_model(self):
        a = self._agent("gpt-5.6")
        q = "buffer the roads and then clip them, then calculate the area of each zone"
        self.assertEqual(self._select(a, q, OPENAI_LIST), "gpt-5.6")   # not gpt-5-pro

    def test_the_cheap_pick_does_not_stick_to_the_next_complex_request(self):
        a = self._agent("gpt-5.6")
        self.assertEqual(self._select(a, "list layers", OPENAI_LIST), "gpt-5-mini")
        q = "compare each of the districts and then buffer them"
        self.assertEqual(self._select(a, q, OPENAI_LIST), "gpt-5.6")

    def test_a_default_that_is_already_cheap_is_left_alone(self):
        a = self._agent("gemini-flash-latest", provider="gemini")
        for q in ("list layers", "buffer the roads and then clip them"):
            self.assertEqual(self._select(a, q, REAL_GEMINI_LIST), "gemini-flash-latest")

    def test_a_list_with_no_suitable_model_keeps_the_default(self):
        a = self._agent("gpt-5.6")
        only_special = ["nano-banana-pro-preview", "lyria-3-clip-preview"]
        self.assertEqual(self._select(a, "list layers", only_special), "gpt-5.6")

    def test_no_model_list_fetched_uses_the_default(self):
        a = self._agent("gpt-5.6")
        self.assertEqual(self._select(a, "list layers", []), "gpt-5.6")

    def test_not_in_auto_mode_does_nothing(self):
        a = self._agent("gpt-5.6", provider=None)
        self.assertEqual(self._select(a, "list layers", OPENAI_LIST), "gpt-5.6")

    def test_a_status_line_is_shown_only_when_the_model_actually_changes(self):
        a = self._agent("gpt-5.6")
        self._select(a, "list layers", OPENAI_LIST)
        a.client._emit_status.assert_called_once()
        a.client._emit_status.reset_mock()
        self._select(a, "compare each of the districts and then buffer them", OPENAI_LIST)
        a.client._emit_status.assert_not_called()


class TestEndToEnd(unittest.TestCase):
    def test_the_model_in_the_outgoing_request_is_the_one_auto_selection_chose(self):
        """Real OpenAIClient, real orchestrator method; only the HTTP call is replaced. This is
        the check that did not exist: the unit tests only looked at classification."""
        m = importlib.import_module("cartogen_ai.infrastructure.providers.openai")
        client = m.OpenAIClient("test-key", model="gpt-5.6")
        a = agent_mod.CartogenAi.__new__(agent_mod.CartogenAi)
        a._auto_model_provider, a._auto_default_model, a.client = "openai", "gpt-5.6", client
        payload_models = []

        def fake_post(url, headers, payload_json, timeout, **kw):
            payload_models.append(json.loads(payload_json)["model"])
            return _resp(200)

        settings = MagicMock()
        settings.value.return_value = json.dumps(OPENAI_LIST)
        with patch.object(agent_mod, "QgsSettings", return_value=settings), \
             patch.object(m, "post_with_retry", side_effect=fake_post):
            a._apply_auto_model_selection("list layers")
            client.complete([{"role": "user", "content": "list layers"}])
            a._apply_auto_model_selection("compare each of the districts and then buffer them")
            client.complete([{"role": "user", "content": "compare ..."}])
        self.assertEqual(payload_models, ["gpt-5-mini", "gpt-5.6"])


if __name__ == "__main__":
    unittest.main()
