"""PLAN-053 stage 2: the CLI bridge copes with a CLI version that does not know a flag, without ever running with a safety switch missing.

The flags on both command lines turn off what would let the CLI act on its own (its tools, MCP servers, user slash commands, user config and rules, a
writable sandbox). Those are REQUIRED: a CLI that rejects one is not run, and the message names the flag and the CLI's version. Two kinds of flag only
change what is kept on disk or how long a run may go (`--no-session-persistence`, `--ephemeral`, `--max-turns`, `--skip-git-repo-check`): a CLI that
rejects one is run once more without it, the user is told what that means, and the choice is remembered for that program file. Unknown error text is
never guessed at: the old message is kept. Nothing here runs a real CLI: the rejection texts are written from the usual wording of the CLIs'
argument parsers (commander for Claude Code, clap for Codex) and are NOT copied from a run of either."""
import unittest
from unittest.mock import patch

from cartogen_ai.infrastructure.providers import cli_bridge as cb
from cartogen_ai.infrastructure.providers import cli_flags as cf

CLAUDE_DEFAULT = ['claude', '-p', '--output-format', 'json', '--tools', '', '--strict-mcp-config', '--disable-slash-commands', '--no-session-persistence',
                  '--max-turns', '1', '--system-prompt-file', '/tmp/s.txt']
CODEX_DEFAULT = ['codex', 'exec', '--json', '--sandbox', 'read-only', '--skip-git-repo-check', '--ephemeral', '--ignore-user-config', '--ignore-rules', '-']


class TestCommandLinesAreUnchangedByDefault(unittest.TestCase):
    """Captured from the code before the refactor (2026-11-03): the default command lines must stay exactly as they were."""

    def test_claude(self):
        self.assertEqual(cb.claude_argv("claude", "/tmp/s.txt"), CLAUDE_DEFAULT)
        self.assertEqual(cb.claude_argv("claude", "/tmp/s.txt", "sonnet"), [*CLAUDE_DEFAULT, "--model", "sonnet"])

    def test_codex(self):
        self.assertEqual(cb.codex_argv("codex"), CODEX_DEFAULT)
        self.assertEqual(cb.codex_argv("codex", "gpt-5"), [*CODEX_DEFAULT[:-1], "--model", "gpt-5", "-"])


class TestRejectedFlags(unittest.TestCase):
    def test_the_usual_wordings_of_an_argument_parser(self):
        cases = {
            "error: unknown option '--no-session-persistence'\n(Did you mean --no-session?)": ["--no-session-persistence"],
            "error: unexpected argument '--ephemeral' found\n\nUsage: codex exec [OPTIONS]": ["--ephemeral"],
            "Error: Unknown option '--max-turns'": ["--max-turns"],
            "error: unrecognized option '--ignore-rules'": ["--ignore-rules"],
            "error: unknown option `--tools`": ["--tools"],
            "Unknown argument: ephemeral": ["--ephemeral"],
        }
        for text, wanted in cases.items():
            self.assertEqual(cf.rejected_flags(text), wanted, text)

    def test_text_that_is_not_a_rejection_gives_nothing(self):
        for text in ("", None, "Please sign in with /login", "exited with status 1", "usage: claude [options] --help shows --everything",
                     "error: could not read /home/me/--odd-folder", "network error: unexpected response"):
            self.assertEqual(cf.rejected_flags(text), [], text)

    def test_several_flags_in_one_text_are_all_found_once_each_in_order(self):
        text = "error: unknown option '--ephemeral'\nerror: unknown option '--ignore-rules'\nerror: unknown option '--ephemeral'"
        self.assertEqual(cf.rejected_flags(text), ["--ephemeral", "--ignore-rules"])


class TestSortingWhatWasRejected(unittest.TestCase):
    def test_optional_flags_can_be_dropped_and_say_what_that_means(self):
        droppable, required, notes = cf.sort_rejected(cf.CLAUDE_FLAGS, ["--no-session-persistence", "--max-turns"])
        self.assertEqual(droppable, {"--no-session-persistence", "--max-turns"})
        self.assertEqual(required, [])
        self.assertIn("history", notes["--no-session-persistence"])

    def test_every_safety_flag_is_required_for_both_clis(self):
        for flags, names in ((cf.CLAUDE_FLAGS, ["--tools", "--strict-mcp-config", "--disable-slash-commands", "--output-format", "--system-prompt-file", "-p"]),
                             (cf.CODEX_FLAGS, ["--sandbox", "--ignore-user-config", "--ignore-rules", "--json"])):
            for name in names:
                droppable, required, _notes = cf.sort_rejected(flags, [name])
                self.assertEqual((droppable, required), (set(), [name]), name)

    def test_the_four_droppable_flags_are_exactly_these(self):
        self.assertEqual({n for n, _t, req, _c in cf.CLAUDE_FLAGS if not req}, {"--no-session-persistence", "--max-turns"})
        self.assertEqual({n for n, _t, req, _c in cf.CODEX_FLAGS if not req}, {"--skip-git-repo-check", "--ephemeral"})

    def test_a_flag_the_adapter_never_sent_is_ignored(self):
        self.assertEqual(cf.sort_rejected(cf.CLAUDE_FLAGS, ["--made-up"]), (set(), [], {}))


class TestBuild(unittest.TestCase):
    def test_skipping_a_droppable_flag_removes_it_with_its_value(self):
        argv = cb.claude_argv("claude", "/tmp/s.txt", skip={"--max-turns", "--no-session-persistence"})
        self.assertNotIn("--max-turns", argv)
        self.assertNotIn("--no-session-persistence", argv)
        self.assertEqual(argv[-2:], ["--system-prompt-file", "/tmp/s.txt"])
        self.assertIn("--tools", argv)

    def test_a_required_flag_can_never_be_skipped(self):
        for skip in ({"--tools"}, {"--strict-mcp-config"}, {"--disable-slash-commands"}):
            with self.assertRaises(cb.CliBridgeError):
                cb.claude_argv("claude", "/tmp/s.txt", skip=skip)
        with self.assertRaises(cb.CliBridgeError):
            cb.codex_argv("codex", skip={"--sandbox"})

    def test_codex_keeps_the_prompt_marker_last_when_flags_are_skipped(self):
        argv = cb.codex_argv("codex", "gpt-5", skip={"--ephemeral", "--skip-git-repo-check"})
        self.assertEqual(argv[-3:], ["--model", "gpt-5", "-"])
        self.assertNotIn("--ephemeral", argv)


class TestTheRetryFlow(unittest.TestCase):
    def setUp(self):
        cb._FLAG_SKIPS.clear()
        self.addCleanup(cb._FLAG_SKIPS.clear)
        self.statuses = []

    def client(self, cls=None):
        cls = cls or cb.ClaudeCliClient
        return cls(status_callback=self.statuses.append)

    def run_with(self, calls, cls=None, version="9.9.9 (test)"):
        """Runs complete() with run_cli answering from `calls` in turn: (code, stdout, stderr). Returns (result, argvs)."""
        seen = []
        answers = list(calls)

        def fake(argv, *args, **kwargs):
            seen.append(list(argv))
            if list(argv)[1:2] == ["--version"]:
                return 0, version + "\n", ""
            return answers.pop(0) if len(answers) > 1 else answers[0]

        ok = (0, '{"type":"result","result":"{\\"final\\": \\"hello\\"}","usage":{"input_tokens":1,"output_tokens":1}}', "")
        with patch.object(cb, "find_executable", return_value="/bin/cli"), patch.object(cb, "run_cli", side_effect=fake), patch.object(cb.cli_locator, "ensure"):
            client = self.client(cls)
            result = client.complete([{"role": "user", "content": "hi"}])
        return result, [a for a in seen if a[1:2] != ["--version"]], ok

    def claude_ok(self):
        return (0, '{"type":"result","subtype":"success","is_error":false,"result":"hello","usage":{"input_tokens":1,"output_tokens":1}}', "")

    def test_a_droppable_flag_is_dropped_once_the_user_is_told_and_the_run_succeeds(self):
        rejected = (1, "", "error: unknown option '--no-session-persistence'")
        result, argvs, _ = self.run_with([rejected, self.claude_ok()])
        self.assertNotIn("error", result)
        self.assertEqual(len(argvs), 2)
        self.assertIn("--no-session-persistence", argvs[0])
        self.assertNotIn("--no-session-persistence", argvs[1])
        said = " ".join(self.statuses)
        self.assertIn("--no-session-persistence", said)
        self.assertIn("9.9.9", said)

    def test_the_choice_is_remembered_so_the_next_call_starts_without_the_flag(self):
        rejected = (1, "", "error: unknown option '--no-session-persistence'")
        self.run_with([rejected, self.claude_ok()])
        result, argvs, _ = self.run_with([self.claude_ok()])
        self.assertEqual(len(argvs), 1)
        self.assertNotIn("--no-session-persistence", argvs[0])
        self.assertNotIn("error", result)

    def test_a_required_flag_is_never_run_without_and_the_message_names_the_flag_and_the_version(self):
        rejected = (1, "", "error: unknown option '--tools'")
        result, argvs, _ = self.run_with([rejected, self.claude_ok()])
        self.assertEqual(len(argvs), 1, "it must not retry without a safety flag")
        self.assertIn("--tools", result["error"])
        self.assertIn("9.9.9", result["error"])
        self.assertIn("update", result["error"].lower())

    def test_unrecognised_error_text_keeps_the_old_message_and_does_not_retry(self):
        result, argvs, _ = self.run_with([(1, "", "something else went wrong")])
        self.assertEqual(len(argvs), 1)
        self.assertIn("exited with status 1", result["error"])

    def test_a_rejection_text_next_to_a_real_answer_is_not_a_failure(self):
        result, argvs, _ = self.run_with([(0, self.claude_ok()[1], "warning: unknown option '--max-turns' ignored")])
        self.assertEqual(len(argvs), 1)
        self.assertNotIn("error", result)

    def test_it_stops_after_a_few_drops_rather_than_looping(self):
        endless = (1, "", "error: unknown option '--max-turns'")
        result, argvs, _ = self.run_with([endless])
        self.assertLessEqual(len(argvs), 3)
        self.assertIn("error", result)

    def test_codex_drops_ephemeral_but_never_the_sandbox(self):
        ok = (0, '{"type":"item.completed","item":{"type":"agent_message","text":"hello"}}\n{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}', "")
        _result, argvs, _ = self.run_with([(2, "", "error: unexpected argument '--ephemeral' found"), ok], cls=cb.CodexCliClient)
        self.assertEqual(len(argvs), 2)
        self.assertNotIn("--ephemeral", argvs[1])
        self.assertIn("--sandbox", argvs[1])
        result2, argvs2, _ = self.run_with([(2, "", "error: unexpected argument '--sandbox' found")], cls=cb.CodexCliClient)
        self.assertEqual(len(argvs2), 1)
        self.assertIn("--sandbox", result2["error"])

    def test_the_model_flag_the_user_chose_is_not_dropped(self):
        seen = []

        def fake(argv, *args, **kwargs):
            seen.append(list(argv))
            return (1, "", "error: unknown option '--model'") if "--model" in argv else (0, "9.9.9", "")

        with patch.object(cb, "find_executable", return_value="/bin/cli"), patch.object(cb, "run_cli", side_effect=fake), patch.object(cb.cli_locator, "ensure"):
            result = cb.ClaudeCliClient(model="sonnet").complete([{"role": "user", "content": "hi"}])
        self.assertIn("--model", result["error"])


class TestLogFields(unittest.TestCase):
    def test_the_log_can_name_the_dropped_flags_and_the_version(self):
        from cartogen_ai.core import logger
        for field in ("flags", "cli_version"):
            self.assertIn(field, logger._SAFE_EVENT_FIELDS)


if __name__ == "__main__":
    unittest.main()
