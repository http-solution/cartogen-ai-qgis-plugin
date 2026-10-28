"""PLAN-039: what Settings shows about a CLI provider (program found, version, signed in, how to sign in). Uses the Python interpreter as a
stand-in program for the real subprocess paths and mocks the model call; no vendor CLI is involved (CI-only evidence)."""
import sys
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.infrastructure.providers import cli_bridge as cb
from cartogen_ai.infrastructure.providers import cli_bridge_status as st


class TestDetect(unittest.TestCase):
    def test_finds_a_program_and_reads_its_version(self):
        info = st.detect("claude_cli", sys.executable)
        self.assertTrue(info["found"], info)
        self.assertTrue(info["version"].startswith("Python"), info)
        self.assertEqual(info["problem"], "")

    def test_missing_program_says_how_to_install(self):
        info = st.detect("codex_cli", "/no/such/program-xyz")
        self.assertFalse(info["found"])
        self.assertIn("codex login", info["problem"])

    def test_blank_setting_uses_the_default_program_name(self):
        for p, name in st.DEFAULT_PROGRAM.items():
            self.assertEqual(st.program_for(p, "  "), name)
            self.assertEqual(st.program_for(p, "/x/y"), "/x/y")

    def test_a_program_that_fails_to_run_is_reported_not_raised(self):
        with patch.object(cb, "find_executable", return_value="/bin/x"), \
             patch.object(cb, "run_cli", side_effect=cb.CliBridgeError("timed out")):
            info = st.detect("gemini_cli")
        self.assertTrue(info["found"])
        self.assertEqual(info["problem"], "timed out")


class TestStage(unittest.TestCase):
    def test_which_step_failed(self):
        self.assertEqual(st.stage_of("Claude Code CLI not found. Install it"), "install")
        self.assertEqual(st.stage_of("Could not start the CLI (OSError). Check the executable path in Settings."), "install")
        self.assertEqual(st.stage_of("The Codex CLI exited with status 1. Is it signed in (`codex login`)?"), "signin")
        self.assertEqual(st.stage_of("run `gemini` once and choose Login with Google"), "signin")
        self.assertEqual(st.stage_of("The Codex CLI reported an error: Reconnecting... 2/5 (unexpected status 401 Unauthorized: "
                                     "Missing bearer or basic authentication in header, url: wss://api.openai.com/v1/responses)"), "signin")
        self.assertEqual(st.stage_of("The CLI did not answer within 180 seconds."), "other")
        self.assertEqual(st.stage_of(""), "other")


class TestCheckConnection(unittest.TestCase):
    def _check(self, client_result, found=True):
        client = MagicMock()
        client.complete.return_value = client_result
        ctor = MagicMock(return_value=client)
        info = {"found": found, "path": "/bin/claude", "version": "2.1.0", "problem": "" if found else "Program 'claude' was not found."}
        with patch.object(st, "detect", return_value=info), patch.dict(st._SPECS, {"claude_cli": (ctor, [], "hint")}):
            return st.check_connection("claude_cli", "claude", "sonnet"), ctor, client

    def test_ready_when_the_model_answers(self):
        result, ctor, client = self._check({"message": {"content": "ok"}})
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "ready")
        self.assertEqual(result["version"], "2.1.0")
        ctor.assert_called_once_with(executable="/bin/claude", model="sonnet", timeout=120)
        self.assertEqual(client.complete.call_args.args[0][0]["content"], st.CHECK_PROMPT)

    def test_an_error_keeps_its_stage(self):
        result, _, _ = self._check({"error": "The Claude CLI exited with status 1. Is it signed in (`claude` once, then /login)?"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "signin")

    def test_a_missing_program_is_the_install_stage_and_no_model_call_is_made(self):
        result, ctor, _ = self._check({"message": {"content": "ok"}}, found=False)
        self.assertEqual((result["ok"], result["stage"]), (False, "install"))
        ctor.assert_not_called()


class TestTerminalCommand(unittest.TestCase):
    def test_windows(self):
        self.assertEqual(st.terminal_command("codex_cli", "C:\\npm\\codex.cmd", "win32"),
                         ["cmd.exe", "/c", "start", "", "cmd.exe", "/k", "C:\\npm\\codex.cmd", "login"])

    def test_macos(self):
        argv = st.terminal_command("claude_cli", "/usr/local/bin/claude", "darwin")
        self.assertEqual(argv[:2], ["osascript", "-e"])
        self.assertIn('do script "/usr/local/bin/claude"', argv[2])

    def test_linux_uses_the_first_terminal_found(self):
        which = {"konsole": "/usr/bin/konsole", "xterm": "/usr/bin/xterm"}.get
        self.assertEqual(st.terminal_command("gemini_cli", "/usr/bin/gemini", "linux", which=which),
                         ["/usr/bin/konsole", "-e", "/usr/bin/gemini"])

    def test_linux_without_a_terminal_gives_none(self):
        self.assertIsNone(st.terminal_command("claude_cli", "/usr/bin/claude", "linux", which=lambda _n: None))

    def test_unsafe_paths_are_never_handed_to_a_launcher(self):
        for bad in ("/opt/my tools/claude", '/x/"y', "/x/y;rm", "/x/$(id)", "", "/x/y&z"):
            for platform in ("win32", "darwin", "linux"):
                self.assertIsNone(st.terminal_command("claude_cli", bad, platform, which=lambda n: "/usr/bin/" + n), (bad, platform))


class TestOpenSignin(unittest.TestCase):
    def test_launches_with_a_scrubbed_environment_and_no_shell(self):
        with patch.object(cb, "find_executable", return_value="/usr/bin/codex"), \
             patch.object(st, "terminal_command", return_value=["/usr/bin/xterm", "-e", "/usr/bin/codex", "login"]), \
             patch.object(st.subprocess, "Popen") as popen:
            out = st.open_signin_terminal("codex_cli")
        self.assertTrue(out["launched"])
        self.assertEqual(out["command"], "/usr/bin/codex login")
        kwargs = popen.call_args.kwargs
        self.assertNotIn("shell", kwargs)
        self.assertNotIn("ANTHROPIC_API_KEY", kwargs["env"])

    def test_without_a_terminal_it_shows_the_command(self):
        with patch.object(cb, "find_executable", return_value="/usr/bin/codex"), patch.object(st, "terminal_command", return_value=None):
            out = st.open_signin_terminal("codex_cli")
        self.assertFalse(out["launched"])
        self.assertIn("/usr/bin/codex login", out["message"])

    def test_missing_program(self):
        with patch.object(cb, "find_executable", return_value=None):
            out = st.open_signin_terminal("claude_cli", "nope")
        self.assertFalse(out["launched"])
        self.assertIn("was not found", out["message"])

    def test_a_launch_failure_never_raises(self):
        with patch.object(cb, "find_executable", return_value="/usr/bin/codex"), \
             patch.object(st, "terminal_command", return_value=["/x"]), patch.object(st.subprocess, "Popen", side_effect=OSError("no")):
            out = st.open_signin_terminal("codex_cli")
        self.assertFalse(out["launched"])
        self.assertIn("Run:", out["message"])


class TestSigninCommandText(unittest.TestCase):
    def test_text(self):
        self.assertEqual(st.signin_command("codex_cli", configured="codex"), "codex login")
        self.assertEqual(st.signin_command("claude_cli", "/x/claude"), "/x/claude")
        self.assertTrue(st.known("gemini_cli"))
        self.assertFalse(st.known("openrouter"))


if __name__ == "__main__":
    unittest.main()
