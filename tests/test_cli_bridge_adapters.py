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


def codex_events(*events):
    return "\n".join(json.dumps(e) for e in events) + "\n"


def agent_message(text):
    return {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": text}}


TURN_DONE = {"type": "turn.completed", "usage": {"input_tokens": 20, "cached_input_tokens": 5, "output_tokens": 6, "reasoning_output_tokens": 4}}


class TestCodexArgv(unittest.TestCase):
    def test_exact_command_line(self):
        self.assertEqual(cb.codex_argv("/bin/codex"), ["/bin/codex", "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check",
                                                       "--ephemeral", "--ignore-user-config", "--ignore-rules", "-"])

    def test_model_goes_before_the_stdin_marker_and_is_validated(self):
        self.assertEqual(cb.codex_argv("c", "gpt-x")[-3:], ["--model", "gpt-x", "-"])
        for bad in ("a b", "x;rm", "$(id)", "-x", "m\nn"):
            with self.assertRaises(cb.CliBridgeError):
                cb.codex_argv("c", bad)

    def test_no_write_access_and_no_prompt_in_argv(self):
        argv = cb.codex_argv("c")
        self.assertIn("read-only", argv)
        self.assertNotIn("workspace-write", argv)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)


class TestParseCodexEvents(unittest.TestCase):
    def test_answer_and_usage_with_reasoning_counted_as_output(self):
        out = codex_events({"type": "thread.started", "thread_id": "t"}, {"type": "turn.started"}, agent_message("hi"), TURN_DONE)
        self.assertEqual(cb.parse_codex_events(out), ("hi", {"input_tokens": 20, "output_tokens": 10}, None))

    def test_last_agent_message_wins(self):
        out = codex_events(agent_message("draft"), agent_message("final"), TURN_DONE)
        self.assertEqual(cb.parse_codex_events(out)[0], "final")

    def test_no_usage_event_gives_none(self):
        self.assertIsNone(cb.parse_codex_events(codex_events(agent_message("x")))[1])

    def test_non_json_lines_between_events_are_skipped(self):
        out = "Reading prompt from stdin...\n" + codex_events(agent_message("ok"))
        self.assertEqual(cb.parse_codex_events(out)[0], "ok")

    def test_no_events_or_no_answer_raises(self):
        for out in ("", "Welcome to Codex", codex_events({"type": "turn.started"}, TURN_DONE)):
            with self.assertRaises(cb.CliBridgeError):
                cb.parse_codex_events(out)

    def test_error_and_failed_turn_raise_with_the_message(self):
        for ev in ({"type": "error", "message": "not logged in"}, {"type": "turn.failed", "error": {"message": "not logged in"}}):
            with self.assertRaises(cb.CliBridgeError) as cm:
                cb.parse_codex_events(codex_events(ev, agent_message("ignored")))
            self.assertIn("not logged in", str(cm.exception))

    def test_acting_on_its_own_is_rejected(self):
        for kind in ("command_execution", "file_change", "mcp_tool_call", "web_search"):
            for event in ("item.started", "item.completed"):
                out = codex_events({"type": event, "item": {"id": "i", "type": kind}}, agent_message("done"))
                with self.assertRaises(cb.CliBridgeError, msg=f"{event}/{kind}") as cm:
                    cb.parse_codex_events(out)
                self.assertIn("on its own", str(cm.exception))

    def test_reasoning_items_are_allowed(self):
        out = codex_events({"type": "item.completed", "item": {"id": "i", "type": "reasoning", "text": "thinking"}}, agent_message("ok"))
        self.assertEqual(cb.parse_codex_events(out)[0], "ok")


class TestCodexCliClient(unittest.TestCase):
    def _run(self, stdout, code=0):
        with patch.object(cb, "find_executable", return_value="/bin/codex"), patch.object(cb, "run_cli", return_value=(code, stdout, "")) as run:
            result = cb.CodexCliClient(model="gpt-x").complete([{"role": "system", "content": "Be careful."}, {"role": "user", "content": "hi"}], TOOLS)
        return result, run

    def test_tool_call_round_trip_with_reported_usage(self):
        reply = '{"tool_calls":[{"name":"delete_layer","arguments":{}}]}'
        result, run = self._run(codex_events(agent_message(reply), TURN_DONE))
        self.assertEqual(result["message"]["tool_calls"][0]["function"]["name"], "delete_layer")
        self.assertEqual(result["usage"], {"input_tokens": 20, "output_tokens": 10})
        self.assertEqual(result["model"], "gpt-x")
        argv, stdin = run.call_args.args[0], run.call_args.args[1]
        self.assertEqual(argv[:2], ["/bin/codex", "exec"])
        self.assertIn("Be careful.", stdin)           # system text leads the single stdin prompt
        self.assertIn(cb.REPLY_INSTRUCTIONS, stdin)
        self.assertNotIn("hi", " ".join(argv))

    def test_plain_answer_with_estimated_usage(self):
        result, _ = self._run(codex_events(agent_message('{"final": "Hello"}')))
        self.assertEqual(result["message"]["content"], "Hello")
        self.assertTrue(result["usage"]["estimated"])

    def test_unknown_tool_is_an_error_dict(self):
        result, _ = self._run(codex_events(agent_message('{"tool_calls":[{"name":"nope","arguments":{}}]}')))
        self.assertIn("error", result)

    def test_acting_on_its_own_is_an_error_dict(self):
        result, _ = self._run(codex_events({"type": "item.started", "item": {"type": "command_execution"}}, agent_message("x")))
        self.assertIn("on its own", result["error"])

    def test_not_signed_in_exit_is_explained(self):
        result, _ = self._run("", code=1)
        self.assertIn("codex login", result["error"])

    def test_missing_cli_is_explained_without_running_anything(self):
        with patch.object(cb, "find_executable", return_value=None), patch.object(cb, "run_cli") as run:
            result = cb.CodexCliClient().complete([{"role": "user", "content": "hi"}])
        self.assertIn("Codex CLI not found", result["error"])
        run.assert_not_called()

    def test_runs_in_an_empty_temp_folder(self):
        _, run = self._run(codex_events(agent_message('{"final": "x"}')))
        self.assertIsNotNone(run.call_args.kwargs["cwd"])


def gemini_json(response="ok", **extra):
    return json.dumps({"response": response, "stats": {"models": {"gemini-x": {"tokens": {"prompt": 30, "candidates": 8, "total": 38}}},
                                                       "tools": {"totalCalls": 0}}, **extra})


class TestGeminiArgv(unittest.TestCase):
    def test_exact_command_line(self):
        self.assertEqual(cb.gemini_argv("/bin/gemini"), ["/bin/gemini", "-p", cb._GEMINI_PROMPT_ARG, "--output-format", "json",
                                                         "--approval-mode", "plan"])

    def test_model_and_validation(self):
        self.assertEqual(cb.gemini_argv("g", "flash")[-2:], ["--model", "flash"])
        for bad in ("a b", "x;rm", "$(id)", "-x", "m\nn"):
            with self.assertRaises(cb.CliBridgeError):
                cb.gemini_argv("g", bad)

    def test_never_auto_approves_and_the_fixed_prompt_text_is_cmd_safe(self):
        argv = cb.gemini_argv("g")
        for forbidden in ("--yolo", "-y", "yolo", "auto_edit"):
            self.assertNotIn(forbidden, argv)
        self.assertIsNone(cb._CMD_UNSAFE.search(cb._GEMINI_PROMPT_ARG))


class TestParseGeminiResult(unittest.TestCase):
    def test_response_usage_and_model(self):
        self.assertEqual(cb.parse_gemini_result(gemini_json("hi")), ("hi", {"input_tokens": 30, "output_tokens": 8}, "gemini-x"))

    def test_leading_log_lines_before_the_json_are_skipped(self):
        self.assertEqual(cb.parse_gemini_result("Loaded cached credentials.\n" + gemini_json("hi"))[0], "hi")

    def test_unknown_stats_shape_gives_no_usage_so_the_caller_estimates(self):
        out = json.dumps({"response": "x", "stats": {"something": 1}})
        self.assertEqual(cb.parse_gemini_result(out), ("x", None, None))

    def test_error_object_and_non_json_and_missing_response_raise(self):
        for out in (json.dumps({"error": {"message": "not logged in"}}), "Welcome", json.dumps({"stats": {}}), json.dumps([1])):
            with self.assertRaises(cb.CliBridgeError):
                cb.parse_gemini_result(out)
        with self.assertRaises(cb.CliBridgeError) as cm:
            cb.parse_gemini_result(json.dumps({"error": {"message": "not logged in"}}))
        self.assertIn("not logged in", str(cm.exception))

    def test_tool_calls_in_the_stats_are_rejected(self):
        out = json.dumps({"response": "done", "stats": {"tools": {"totalCalls": 2}}})
        with self.assertRaises(cb.CliBridgeError) as cm:
            cb.parse_gemini_result(out)
        self.assertIn("on its own", str(cm.exception))


class TestGeminiCliClient(unittest.TestCase):
    def _run(self, stdout, code=0):
        with patch.object(cb, "find_executable", return_value="/bin/gemini"), patch.object(cb, "run_cli", return_value=(code, stdout, "")) as run:
            result = cb.GeminiCliClient(model="flash").complete([{"role": "system", "content": "Be careful."}, {"role": "user", "content": "hi"}], TOOLS)
        return result, run

    def test_tool_call_round_trip(self):
        reply = '{"tool_calls":[{"name":"add_layer","arguments":{"path":"r.shp"}}]}'
        result, run = self._run(gemini_json(reply))
        self.assertEqual(result["message"]["tool_calls"][0]["function"]["name"], "add_layer")
        self.assertEqual(result["usage"], {"input_tokens": 30, "output_tokens": 8})
        self.assertEqual(result["model"], "gemini-x")
        argv, stdin = run.call_args.args[0], run.call_args.args[1]
        self.assertEqual(argv[0], "/bin/gemini")
        self.assertIn("Be careful.", stdin)
        self.assertNotIn("hi", " ".join(argv))
        self.assertIsNotNone(run.call_args.kwargs["cwd"])

    def test_plain_answer_with_estimated_usage_when_stats_are_missing(self):
        result, _ = self._run(json.dumps({"response": '{"final": "Hello"}'}))
        self.assertEqual(result["message"]["content"], "Hello")
        self.assertTrue(result["usage"]["estimated"])
        self.assertEqual(result["model"], "flash")

    def test_unknown_tool_and_own_tool_calls_are_error_dicts(self):
        self.assertIn("error", self._run(gemini_json('{"tool_calls":[{"name":"nope","arguments":{}}]}'))[0])
        out = json.dumps({"response": "x", "stats": {"tools": {"totalCalls": 1}}})
        self.assertIn("on its own", self._run(out)[0]["error"])

    def test_not_signed_in_exit_is_explained(self):
        self.assertIn("Login with Google", self._run("", code=41)[0]["error"])

    def test_missing_cli_is_explained_without_running_anything(self):
        with patch.object(cb, "find_executable", return_value=None), patch.object(cb, "run_cli") as run:
            result = cb.GeminiCliClient().complete([{"role": "user", "content": "hi"}])
        self.assertIn("Gemini CLI not found", result["error"])
        run.assert_not_called()

    def test_api_keys_for_gemini_are_scrubbed_so_the_cli_uses_its_own_login(self):
        for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            self.assertIn(key, cb.SCRUBBED_ENV)



class TestCliFailuresShowTheCliOwnReason(unittest.TestCase):
    """User report 2026-10-29: Codex "completely not working" and every failure read only "exited with status N"."""

    MSGS = ({"role": "user", "content": "hi"},)

    def _complete(self, client, exe, code, out, err):
        with patch.object(cb, "find_executable", return_value=exe), patch.object(cb, "run_cli", return_value=(code, out, err)):
            return client.complete(list(self.MSGS), TOOLS)

    def test_codex_exit_error_carries_stderr(self):
        r = self._complete(cb.CodexCliClient(), "/bin/codex", 2, "", "error: unexpected argument '--ignore-rules'\n")
        self.assertIn("status 2", r["error"])
        self.assertIn("unexpected argument '--ignore-rules'", r["error"])

    def test_codex_unusable_stdout_with_failing_exit_carries_stderr(self):
        r = self._complete(cb.CodexCliClient(), "/bin/codex", 1, "garbage", "not logged in")
        self.assertIn("did not return JSON events", r["error"])
        self.assertIn("not logged in", r["error"])

    def test_claude_and_gemini_exit_errors_carry_stderr(self):
        for client, exe in ((cb.ClaudeCliClient(), "/bin/claude"), (cb.GeminiCliClient(), "/bin/gemini")):
            r = self._complete(client, exe, 1, "", "boom reason")
            self.assertIn("boom reason", r["error"])

    def test_stderr_tail_is_one_line_and_capped(self):
        tail = cb._stderr_tail("a\n" * 1000)
        self.assertNotIn("\n", tail)
        self.assertLessEqual(len(tail), 300 + len(" CLI said: "))
        self.assertEqual(cb._stderr_tail(""), "")

    def test_expired_claude_login_gets_a_sign_in_hint(self):
        out = '{"type":"result","is_error":true,"result":"Failed to authenticate: OAuth session expired and could not be refreshed"}'
        r = self._complete(cb.ClaudeCliClient(), "/bin/claude", 1, out, "")
        self.assertIn("claude auth login", r["error"])

    def test_other_claude_errors_get_no_sign_in_hint(self):
        out = '{"type":"result","is_error":true,"result":"Max turns reached"}'
        r = self._complete(cb.ClaudeCliClient(), "/bin/claude", 0, out, "")
        self.assertNotIn("auth login", r["error"])


if __name__ == "__main__":
    unittest.main()
