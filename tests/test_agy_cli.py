"""PLAN-071: the Antigravity CLI (`agy`) connection and the model choices on the CLI pages. Offline: no agy, no login. The event shapes below are the
ones in Google's headless page (antigravity.google/docs/cli/headless, read 2026-11-09), NOT output from a real run: a real run is still owed."""
import ast
import json
import unittest
from pathlib import Path
from unittest import mock

from cartogen_ai.core.agent.agent_orchestrator import AgyCliClient as _OrchestratorAgy  # noqa: F401  (the orchestrator imports the client)
from cartogen_ai.infrastructure import settings_keys as sk
from cartogen_ai.infrastructure.providers import cli_bridge as cb
from cartogen_ai.infrastructure.providers import cli_bridge_status as st

ROOT = Path(__file__).resolve().parents[1]


def _events(*objs):
    return "\n".join(json.dumps(o) for o in objs) + "\n"


OK_STREAM = _events(
    {"event": "init", "init": {"cwd": "/tmp/x", "tools": ["read_file"], "permission_mode": "default", "model": "gemini-3.8-flash-medium"}},
    {"event": "step_update", "step_update": {"step_index": 0, "state": "DONE", "step_type": "user_input"}},
    {"event": "step_update", "step_update": {"step_index": 1, "state": "DONE", "step_type": "agent_response", "text_delta": "ok"}},
    {"event": "result", "result": {"conversation_id": "c1", "status": "SUCCESS", "response": '{"final": "ok"}\n',
                                   "usage": {"input_tokens": 12, "output_tokens": 3, "thinking_tokens": 4, "total_tokens": 19}}},
)


class TestAgyCommandLine(unittest.TestCase):
    def test_the_prompt_goes_on_stdin_and_the_answer_comes_back_as_stream_json(self):
        argv = cb.agy_argv("/x/agy")
        self.assertEqual(argv[0], "/x/agy")
        self.assertIn("--input-format", argv)
        self.assertEqual(argv[argv.index("--input-format") + 1], "stream-json")
        self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")
        self.assertNotIn("-p", argv, "-p drops the prompt in stream-json input mode (Google's warning)")

    def test_it_never_asks_the_cli_to_skip_its_permission_checks_and_it_sandboxes(self):
        argv = cb.agy_argv("/x/agy", "gemini-3.8-flash-medium")
        self.assertNotIn("--dangerously-skip-permissions", argv)
        self.assertIn("--sandbox", argv)

    def test_the_chosen_model_is_passed_and_a_bad_name_is_refused(self):
        argv = cb.agy_argv("/x/agy", "gemini-3.8-flash-medium")
        self.assertEqual(argv[-2:], ["--model", "gemini-3.8-flash-medium"])
        self.assertNotIn("--model", cb.agy_argv("/x/agy"))
        with self.assertRaises(cb.CliBridgeError):
            cb.agy_argv("/x/agy", "bad name; rm -rf /")

    def test_no_agy_flag_can_be_left_out(self):
        for name in ("--input-format", "--output-format", "--sandbox"):
            with self.assertRaises(cb.CliBridgeError):
                cb.agy_argv("/x/agy", skip=(name,))

    def test_the_input_is_one_json_line_in_the_documented_shape(self):
        line = cb.agy_input('say "hi"\nplease')
        self.assertTrue(line.endswith("\n") and line.count("\n") == 1)
        self.assertEqual(json.loads(line), {"event": "user", "message": {"content": 'say "hi"\nplease'}})


class TestParseAgyStream(unittest.TestCase):
    def test_the_answer_usage_and_model_are_read_from_the_result_event(self):
        text, usage, model = cb.parse_agy_stream(OK_STREAM)
        self.assertEqual(text.strip(), '{"final": "ok"}')
        self.assertEqual(usage, {"input_tokens": 12, "output_tokens": 7})      # thinking tokens count as output
        self.assertEqual(model, "gemini-3.8-flash-medium")

    def test_a_failed_run_says_what_the_cli_said(self):
        out = _events({"event": "result", "result": {"status": "ERROR", "error": "authentication required"}})
        with self.assertRaises(cb.CliBridgeError) as ctx:
            cb.parse_agy_stream(out)
        self.assertIn("authentication required", str(ctx.exception))
        self.assertIn("ERROR", str(ctx.exception))

    def test_a_run_waiting_for_approval_is_not_an_answer(self):
        out = _events({"event": "result", "result": {"status": "WAITING", "response": "x"}})
        with self.assertRaises(cb.CliBridgeError):
            cb.parse_agy_stream(out)

    def test_a_tool_step_of_its_own_is_refused(self):
        out = _events({"event": "step_update", "step_update": {"state": "ACTIVE", "step_type": "tool", "tool_name": "run_command"}},
                      {"event": "result", "result": {"status": "SUCCESS", "response": "done"}})
        with self.assertRaises(cb.CliBridgeError) as ctx:
            cb.parse_agy_stream(out)
        self.assertIn("act on its own", str(ctx.exception))

    def test_no_json_no_result_and_an_empty_answer_are_each_an_error(self):
        for out in ("", "plain text, not json\n", _events({"event": "init", "init": {}}),
                    _events({"event": "result", "result": {"status": "SUCCESS", "response": "  \n"}})):
            with self.assertRaises(cb.CliBridgeError):
                cb.parse_agy_stream(out)

    def test_noise_lines_between_events_are_ignored(self):
        text, _usage, _model = cb.parse_agy_stream("banner\n" + OK_STREAM + "bye\n")
        self.assertIn("ok", text)


class TestAgyClient(unittest.TestCase):
    def _complete(self, code, out, err=""):
        runs = []

        def fake_run(argv, stdin_text="", **kw):
            runs.append((argv, stdin_text))
            return code, out, err

        with mock.patch.object(cb, "run_cli", fake_run), mock.patch.object(cb, "find_executable", return_value="/x/agy"), \
                mock.patch.object(cb.cli_locator, "ensure"):
            reply = cb.AgyCliClient(executable="/x/agy", model="gemini-3.8-flash-medium").complete([{"role": "user", "content": "hello"}], None)
        return reply, runs

    def test_a_reply_round_trips_through_stdin_and_stream_json(self):
        reply, runs = self._complete(0, OK_STREAM)
        self.assertEqual(reply["message"]["content"], "ok")
        self.assertEqual(reply["model"], "gemini-3.8-flash-medium")
        argv, stdin_text = runs[0]
        self.assertNotIn("hello", " ".join(argv), "the prompt must not be on the command line")
        self.assertIn("hello", json.loads(stdin_text.splitlines()[0])["message"]["content"])

    def test_a_non_zero_exit_with_no_output_points_at_signing_in(self):
        reply, _ = self._complete(1, "", "authentication required")
        self.assertIn("error", reply)
        self.assertIn("signed in", reply["error"])
        self.assertIn("authentication required", reply["error"])
        self.assertEqual(st.stage_of(reply["error"]), "signin")


class TestAgyModels(unittest.TestCase):
    def test_slugs_are_read_from_the_documented_listing(self):
        text = ("gemini-3.8-flash-medium   Gemini 3.8 Flash (Medium)\n"
                "gemini-3.1-pro-high       Gemini 3.1 Pro (High)\n\n"
                "gemini-3.8-flash-medium   duplicate line\n")
        self.assertEqual(cb.parse_agy_models(text), ["gemini-3.8-flash-medium", "gemini-3.1-pro-high"])

    def test_headings_and_errors_are_not_models(self):
        self.assertEqual(cb.parse_agy_models("Available models:\nerror: not signed in\n"), [])
        self.assertEqual(cb.parse_agy_models(""), [])
        self.assertEqual(cb.parse_agy_models(None), [])

    def test_list_models_runs_agy_models_and_only_for_agy(self):
        with mock.patch.object(cb, "run_cli", return_value=(0, "gemini-3.8-flash-medium  X\n", "")) as run:
            self.assertEqual(st.list_models("agy_cli", "/x/agy"), ["gemini-3.8-flash-medium"])
            self.assertEqual(run.call_args.args[0], ["/x/agy", "models"])
            self.assertEqual(st.list_models("codex_cli", "/x/codex"), [])
            self.assertEqual(st.list_models("agy_cli", ""), [])

    def test_a_failing_or_missing_list_is_an_empty_list_not_an_error(self):
        with mock.patch.object(cb, "run_cli", return_value=(1, "", "boom")):
            self.assertEqual(st.list_models("agy_cli", "/x/agy"), [])
        with mock.patch.object(cb, "run_cli", side_effect=cb.CliBridgeError("gone")):
            self.assertEqual(st.list_models("agy_cli", "/x/agy"), [])


class TestAgyIsRegisteredEverywhereTheOtherCliProvidersAre(unittest.TestCase):
    def test_settings_keys(self):
        self.assertIn("agy_cli", sk.CLI_PROVIDERS)
        self.assertEqual(sk.SETTINGS_AGY_CLI_MODEL, "cartogen_ai/agy_cli_model")
        self.assertNotIn("agy_cli", sk.ENABLED_PROVIDERS)          # off unless "Allow CLI logins" is ticked

    def test_status_tables_cover_it(self):
        self.assertTrue(st.known("agy_cli"))
        self.assertEqual(st.DEFAULT_PROGRAM["agy_cli"], "agy")
        self.assertEqual(st.LABELS["agy_cli"], "Antigravity CLI")
        self.assertIn("Google", st.consent_text("agy_cli"))
        self.assertEqual(st.signin_command("agy_cli", configured="agy"), "agy")
        for platform in ("win32", "darwin", "linux"):
            self.assertTrue(st.install_commands("agy_cli", platform)[0].startswith(("irm https://antigravity.google/", "curl -fsSL https://antigravity.google/")))

    def test_the_sign_in_state_is_not_guessed(self):
        self.assertEqual(st.signin_status("agy_cli", "/x/agy")["state"], "unknown")

    def test_the_program_finder_asks_the_os_about_agy(self):
        self.assertIn("agy", cb.cli_locator.PROGRAM_NAMES)

    def test_catalog_entry_and_the_model_seeds(self):
        tree = ast.parse((ROOT / "src/cartogen_ai/core/ui/connections_catalog.py").read_text(encoding="utf-8"))
        text = ast.unparse(tree)
        for needle in ("'agy_cli'", "SETTINGS_AGY_CLI_MODEL", "'gemini-3.8-flash-medium'", "'gpt-6.1-sol'", "'gpt-6.1-terra'", "'sonnet'"):
            self.assertIn(needle, text)

    def test_the_orchestrator_builds_the_agy_client_from_the_saved_settings(self):
        source = (ROOT / "src/cartogen_ai/core/agent/agent_orchestrator.py").read_text(encoding="utf-8")
        self.assertIn('"agy_cli": (AgyCliClient, SETTINGS_AGY_CLI_MODEL)', source)

    def test_the_dock_has_a_label_for_it(self):
        from cartogen_ai.core.ui.dock_constants import CLI_PROVIDER_LABELS
        self.assertEqual(CLI_PROVIDER_LABELS["agy_cli"], "Antigravity CLI (experimental)")


if __name__ == "__main__":
    unittest.main()
