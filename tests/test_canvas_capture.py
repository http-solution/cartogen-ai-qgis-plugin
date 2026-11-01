"""PLAN-032 (the model sees the map), offline part: the pure helpers, the message each client receives, and the agent loop taking the picture out of
the tool result and sending it as an image message.

Not shown here: a live vision call on any provider (needs a person and an API key), and the render on a real canvas (tests/test_canvas_capture_live.py)."""
import unittest
from typing import ClassVar
from unittest.mock import patch

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.models import egress_gate
from cartogen_ai.core.services import canvas_capture as cc
from cartogen_ai.infrastructure.providers.claude import _translate_user_content

from tests.test_agent_runner import _make_bare_agent

B64 = "QUJD" * 5000        # a stand-in for a 15 KB PNG


def captured(**kw):
    base = {"success": True, "mime": "png", "image_b64": B64, "legend_text": "roads: primary, secondary", "layers_text": "roads, districts",
            "blank": False}
    base.update(kw)
    return base


class TestPureHelpers(unittest.TestCase):
    def test_fit_size_scales_down_only(self):
        self.assertEqual(cc.fit_size(2560, 1280), (1280, 640))
        self.assertEqual(cc.fit_size(800, 600), (800, 600))
        self.assertEqual(cc.fit_size(1000, 5000), (256, 1280))
        self.assertEqual(cc.fit_size(0, 0), (1, 1))

    def test_vision_support_by_client_and_model(self):
        self.assertTrue(cc.provider_supports_vision("GeminiClient"))
        self.assertTrue(cc.provider_supports_vision("ClaudeClient", "claude-x"))
        self.assertTrue(cc.provider_supports_vision("OpenRouterClient", "google/gemini-2.5-flash"))
        self.assertFalse(cc.provider_supports_vision("OpenRouterClient", "meta-llama/llama-3-8b-instruct"))
        self.assertTrue(cc.provider_supports_vision("OllamaClient", "llava:13b"))
        self.assertFalse(cc.provider_supports_vision("OllamaClient", "llama3"))
        self.assertFalse(cc.provider_supports_vision("ClaudeCliClient", "sonnet"))
        self.assertFalse(cc.provider_supports_vision("SomethingElse"))

    def test_the_message_is_image_then_legend_then_layers(self):
        message = cc.build_image_message("AAAA", "roads: primary", "roads, districts")
        kinds = [part["type"] for part in message["content"]]
        self.assertEqual(kinds, ["image_url", "text", "text"])
        self.assertEqual(message["content"][0]["image_url"]["url"], "data:image/png;base64,AAAA")
        self.assertIn("Legend: roads: primary", message["content"][1]["text"])
        self.assertIn("Visible layers, top to bottom: roads, districts", message["content"][2]["text"])
        self.assertTrue(cc.is_image_message(message))
        self.assertFalse(cc.is_image_message({"role": "user", "content": "hello"}))

    def test_the_claude_client_converts_the_same_message_to_an_image_block(self):
        blocks = _translate_user_content(cc.build_image_message("AAAA", "l", "x")["content"])
        self.assertEqual([b["type"] for b in blocks], ["image", "text", "text"])
        self.assertEqual(blocks[0]["source"], {"type": "base64", "media_type": "image/png", "data": "AAAA"})

    def test_the_picture_leaves_the_tool_result(self):
        clean, message = cc.split_image(captured(), True)
        self.assertNotIn("image_b64", clean)
        self.assertIn("next message", clean["note"])
        self.assertIsNotNone(message)
        self.assertEqual(clean["layers_text"], "roads, districts")

    def test_without_vision_the_model_gets_the_text_and_a_reason(self):
        clean, message = cc.split_image(captured(), False)
        self.assertIsNone(message)
        self.assertNotIn("image_b64", clean)
        self.assertIn("cannot be sent a picture", clean["note"])
        self.assertIn("roads: primary, secondary", clean["note"])

    def test_a_blank_canvas_is_reported_not_described(self):
        clean, message = cc.split_image(captured(blank=True), True)
        self.assertIsNone(message)
        self.assertIn("blank", clean["note"])

    def test_results_without_a_picture_are_untouched(self):
        for result in ({"success": True}, "text", None, {"image_b64": ""}):
            self.assertEqual(cc.split_image(result, True), (result, None))

    def test_only_the_newest_picture_stays(self):
        messages = [{"role": "user", "content": "q"}, cc.build_image_message("OLD", "a", "b"), {"role": "tool", "content": "{}"}]
        self.assertEqual(cc.compact_old_images(messages), 1)
        self.assertEqual(messages[1]["content"], cc.OLD_IMAGE_PLACEHOLDER)
        self.assertEqual(cc.compact_old_images(messages), 0)


class TestEgressForAPicture(unittest.TestCase):
    LEVELS: ClassVar[dict] = {"secret_points": "RESTRICTED", "districts": "PUBLIC"}

    def _decide(self, visible):
        return egress_gate.evaluate(
            mode=egress_gate.MODE_ENFORCE, provider_is_local=False, tool_name="inspect_canvas_visually", arguments={},
            project_layer_names=list(self.LEVELS), get_level=self.LEVELS.get, get_sources=lambda n: [], strict=False,
            visible_layer_names=visible)

    def test_a_visible_protected_layer_blocks_the_picture_to_a_cloud_model(self):
        decision = self._decide(["secret_points", "districts"])
        self.assertEqual(decision["action"], "block")
        self.assertIn("secret_points", decision["layers"])

    def test_a_hidden_protected_layer_does_not(self):
        self.assertIsNone(self._decide(["districts"]))

    def test_unknown_visibility_counts_the_whole_project(self):
        self.assertEqual(self._decide(None)["action"], "block")


SCHEMA = [{"type": "function", "function": {"name": "inspect_canvas_visually", "description": "look",
                                           "parameters": {"type": "object", "properties": {}}}}]


def _client(class_name, model="m"):
    class Client:
        def __init__(self):
            self.calls = []
            self.model = model

        def complete(self, messages, tools=None, max_tokens=None):
            self.calls.append([dict(m) if isinstance(m, dict) else m for m in messages])
            if len(self.calls) == 1:
                return {"message": {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "c1", "function": {"name": "inspect_canvas_visually", "arguments": "{}"}}]}}
            return {"message": {"role": "assistant", "content": "I can see the roads and the districts."}}
    Client.__name__ = class_name
    return Client()


def _run(client):
    agent = _make_bare_agent(client)
    with patch.object(agent_mod.CartogenAi, "_apply_auto_model_selection", lambda self, q: None), \
         patch.object(agent_mod.CartogenAi, "_execute_tool", lambda self, name, args: captured()), \
         patch("cartogen_ai.core.agent.agent_orchestrator.build_system_prompt", return_value="sys"), \
         patch("cartogen_ai.core.agent.agent_orchestrator.TOOLS_SCHEMA", SCHEMA), \
         patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep"):
        return agent.run("what is wrong with this map")


class TestAgentLoopSendsThePicture(unittest.TestCase):
    def test_a_vision_model_gets_the_picture_after_the_tool_message_and_not_as_text(self):
        client = _client("GeminiClient")
        _run(client)
        second = client.calls[1]
        tool = next(m for m in second if m.get("role") == "tool")
        self.assertNotIn(B64, tool["content"])
        self.assertLess(len(tool["content"]), 2000)
        image = [m for m in second if cc.is_image_message(m)]
        self.assertEqual(len(image), 1)
        self.assertGreater(second.index(image[0]), second.index(tool), "the picture must come after the tool message")
        self.assertEqual([p["type"] for p in image[0]["content"]], ["image_url", "text", "text"])

    def test_a_model_without_vision_gets_text_only(self):
        client = _client("OllamaClient", "llama3")
        _run(client)
        second = client.calls[1]
        self.assertFalse(any(cc.is_image_message(m) for m in second))
        tool = next(m for m in second if m.get("role") == "tool")
        self.assertNotIn(B64, tool["content"])
        self.assertIn("cannot be sent a picture", tool["content"])


if __name__ == "__main__":
    unittest.main()
