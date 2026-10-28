"""PLAN-038: the Claude adapter's command line, result parsing and the prompt/reply round trip. The command line is asserted exactly
because it is what keeps the CLI from acting outside the plugin's gates."""
import json
import unittest
from unittest.mock import patch

from cartogen_ai.infrastructure.providers import cli_bridge as cb

TOOLS = [{"type": "function", "function": {"name": "add_layer", "description": "Add a layer", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
         {"type": "function", "function": {"name": "delete_layer", "description": "Delete", "parameters": {"type": "object"}}}]
NAMES = ["add_layer", "delete_layer"]


def claude_json(result, **extra):
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": result, **extra})


class TestClaudeArgv(unittest.TestCase):
    def test_exact_command_line_switches_every_tool_off(self):
        argv = cb.claude_argv("/bin/claude", "/tmp/sys.txt")
        self.assertEqual(argv, ["/bin/claude", "-p", "--output-format", "json", "--tools", "", "--strict-mcp-config",
                                "--disable-slash-commands", "--no-session-persistence", "--max-turns", "1",
                                "--system-prompt-file", "/tmp/sys.txt"])

    def test_model_is_added_and_validated(self):
        self.assertEqual(cb.claude_argv("c", "f", "sonnet")[-2:], ["--model", "sonnet"])
        for bad in ("a b", "x;rm", "$(id)", "", "-x", "m\nn"):
            if bad:
                with self.assertRaises(cb.CliBridgeError):
                    cb.claude_argv("c", "f", bad)

    def test_no_prompt_text_in_argv(self):
        self.assertNotIn("hello", " ".join(cb.claude_argv("c", "f")))


class TestParseClaudeResult(unittest.TestCase):
    def test_text_and_reported_usage_with_cache_counted(self):
        out = claude_json("hi", usage={"input_tokens": 10, "cache_read_input_tokens": 5, "cache_creation_input_tokens": 1, "output_tokens": 7},
                          modelUsage={"claude-sonnet-x": {}})
        text, usage, model = cb.parse_claude_result(out)
        self.assertEqual((text, usage, model), ("hi", {"input_tokens": 16, "output_tokens": 7}, "claude-sonnet-x"))

    def test_error_result_raises(self):
        with self.assertRaises(cb.CliBridgeError) as cm:
            cb.parse_claude_result(json.dumps({"type": "result", "is_error": True, "result": "Not logged in"}))
        self.assertIn("Not logged in", str(cm.exception))

    def test_non_json_raises(self):
        with self.assertRaises(cb.CliBridgeError):
            cb.parse_claude_result("Welcome to Claude")

    def test_event_list_uses_the_result_event(self):
        events = [{"type": "system"}, {"type": "result", "is_error": False, "result": "ok"}]
        self.assertEqual(cb.parse_claude_result(json.dumps(events))[0], "ok")

    def test_missing_usage_is_none_so_the_caller_estimates(self):
        self.assertIsNone(cb.parse_claude_result(claude_json("x"))[1])


class TestParseReply(unittest.TestCase):
    def test_final_answer(self):
        msg = cb.parse_reply('{"final": "Done."}', NAMES)
        self.assertEqual((msg["content"], "tool_calls" in msg), ("Done.", False))

    def test_tool_call_becomes_openai_shape(self):
        msg = cb.parse_reply('{"tool_calls":[{"name":"add_layer","arguments":{"path":"C:\\\\a\\\\b.shp"}}]}', NAMES)
        call = msg["tool_calls"][0]
        self.assertEqual(call["function"]["name"], "add_layer")
        self.assertEqual(json.loads(call["function"]["arguments"]), {"path": "C:\\a\\b.shp"})
        self.assertTrue(call["id"].startswith("cli_"))

    def test_prose_and_code_fence_around_the_json_are_tolerated(self):
        text = 'Sure, here you go:\n```json\n{"tool_calls":[{"name":"add_layer","arguments":{}}]}\n```\nThanks.'
        self.assertEqual(cb.parse_reply(text, NAMES)["tool_calls"][0]["function"]["name"], "add_layer")

    def test_unknown_tool_is_an_error_not_a_guess(self):
        with self.assertRaises(cb.CliBridgeError):
            cb.parse_reply('{"tool_calls":[{"name":"format_disk","arguments":{}}]}', NAMES)

    def test_malformed_arguments_are_an_error(self):
        with self.assertRaises(cb.CliBridgeError):
            cb.parse_reply('{"tool_calls":[{"name":"add_layer","arguments":"path=x"}]}', NAMES)

    def test_empty_tool_calls_is_an_error(self):
        with self.assertRaises(cb.CliBridgeError):
            cb.parse_reply('{"tool_calls":[]}', NAMES)

    def test_plain_words_are_treated_as_the_answer(self):
        self.assertEqual(cb.parse_reply("I could not find that layer.", NAMES)["content"], "I could not find that layer.")

    def test_unrelated_json_is_treated_as_text_not_a_call(self):
        text = '{"layers": 3}'
        self.assertEqual(cb.parse_reply(text, NAMES)["content"], text)


class TestBuildPrompt(unittest.TestCase):
    def test_system_goes_to_system_text_and_tools_to_prompt(self):
        msgs = [{"role": "system", "content": "Be careful."}, {"role": "user", "content": "add roads"},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "1", "function": {"name": "add_layer", "arguments": '{"path":"r.shp"}'}}]},
                {"role": "tool", "tool_call_id": "1", "content": "ok"}]
        system, prompt = cb.build_prompt(msgs, TOOLS)
        self.assertIn("Be careful.", system)
        self.assertIn(cb.REPLY_INSTRUCTIONS, system)
        self.assertNotIn("Be careful.", prompt)
        self.assertIn('"name":"add_layer"', prompt)
        self.assertIn("[tool result for 1]\nok", prompt)
        self.assertIn('{"tool_calls": [{"name": "add_layer", "arguments": {"path": "r.shp"}}]}', prompt)

    def test_image_blocks_are_not_sent(self):
        msgs = [{"role": "user", "content": [{"type": "text", "text": "look"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}]
        _s, prompt = cb.build_prompt(msgs, None)
        self.assertNotIn("AAAA", prompt)
        self.assertIn("[image omitted]", prompt)


class TestClaudeCliClient(unittest.TestCase):
    def _run(self, stdout, code=0, tools=TOOLS):
        with patch.object(cb, "find_executable", return_value="/bin/claude"), patch.object(cb, "run_cli", return_value=(code, stdout, "")) as run:
            result = cb.ClaudeCliClient(model="sonnet").complete([{"role": "user", "content": "hi"}], tools)
        return result, run

    def test_final_answer_with_estimated_usage(self):
        result, run = self._run(claude_json('{"final": "Hello"}'))
        self.assertEqual(result["message"]["content"], "Hello")
        self.assertTrue(result["usage"]["estimated"])
        self.assertIn("hi", run.call_args.args[1])  # prompt is on stdin, not argv
        self.assertEqual(run.call_args.kwargs["cwd"] is not None, True)

    def test_tool_call_round_trip(self):
        result, _ = self._run(claude_json('{"tool_calls":[{"name":"delete_layer","arguments":{}}]}', usage={"input_tokens": 3, "output_tokens": 2}))
        self.assertEqual(result["message"]["tool_calls"][0]["function"]["name"], "delete_layer")
        self.assertEqual(result["usage"], {"input_tokens": 3, "output_tokens": 2})

    def test_unknown_tool_returns_error_dict(self):
        result, _ = self._run(claude_json('{"tool_calls":[{"name":"nope","arguments":{}}]}'))
        self.assertIn("error", result)

    def test_not_signed_in_exit_is_explained(self):
        result, _ = self._run("", code=1)
        self.assertIn("signed in", result["error"])

    def test_missing_cli_is_explained_without_running_anything(self):
        with patch.object(cb, "find_executable", return_value=None), patch.object(cb, "run_cli") as run:
            result = cb.ClaudeCliClient().complete([{"role": "user", "content": "hi"}])
        self.assertIn("not found", result["error"])
        run.assert_not_called()

    def test_runner_failure_becomes_error_dict(self):
        with patch.object(cb, "find_executable", return_value="/bin/claude"), patch.object(cb, "run_cli", side_effect=cb.CliBridgeError("timed out")):
            self.assertEqual(cb.ClaudeCliClient().complete([{"role": "user", "content": "hi"}]), {"error": "timed out"})


if __name__ == "__main__":
    unittest.main()
