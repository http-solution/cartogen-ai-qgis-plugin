"""PLAN-041: finding the program where the user's own terminal would, on every OS. The registry read and the login shell are replaced by
stand-ins (the sandbox is Linux); nothing here proves them on a real Windows or macOS machine."""
import os
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from cartogen_ai.infrastructure.providers import cli_bridge as cb
from cartogen_ai.infrastructure.providers import cli_bridge_status as st
from cartogen_ai.infrastructure.providers import cli_locator as loc


def _script(folder, name, body):
    path = os.path.join(folder, name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


class _FreshCache(unittest.TestCase):
    def setUp(self):
        self._saved = dict(loc._cache)
        loc._cache["dirs"] = None
        self.addCleanup(lambda: loc._cache.update(self._saved))


@unittest.skipIf(os.name == "nt", "uses a POSIX shell script as the login shell")
class TestLoginShell(_FreshCache):
    def test_reads_only_the_text_between_the_markers(self):
        with tempfile.TemporaryDirectory() as d:
            shell = _script(d, "bash", 'echo "banner noise"; printf "%s" "__CARTOGEN_PATH_START__/opt/a:/opt/b__CARTOGEN_PATH_END__"; echo trailing')
            with patch.dict(os.environ, {"SHELL": shell}):
                self.assertEqual(loc.login_shell_path(), ["/opt/a", "/opt/b"])

    def test_a_shell_that_is_not_a_plain_shell_is_never_run(self):
        with tempfile.TemporaryDirectory() as d:
            marker = os.path.join(d, "ran")
            evil = _script(d, "evil", f'touch "{marker}"')
            with patch.dict(os.environ, {"SHELL": evil}):
                self.assertEqual(loc.login_shell_path(), [])
            self.assertFalse(os.path.exists(marker))
        with patch.dict(os.environ, {"SHELL": "bash"}):  # not an absolute path
            self.assertEqual(loc.login_shell_path(), [])

    def test_a_shell_that_hangs_is_given_up_on(self):
        with tempfile.TemporaryDirectory() as d:
            shell = _script(d, "bash", "sleep 5")
            with patch.dict(os.environ, {"SHELL": shell}):
                self.assertEqual(loc.login_shell_path(timeout=0.3), [])


@unittest.skipIf(os.name == "nt", "uses a POSIX script as npm")
class TestNpmPrefix(unittest.TestCase):
    def test_the_bin_folder_under_the_global_prefix_is_returned(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "prefix", "bin"))
            tools = os.path.join(d, "tools")
            os.makedirs(tools)
            _script(tools, "npm", f'echo "{os.path.join(d, "prefix")}"')
            self.assertEqual(loc.npm_global_bin([tools]), [os.path.join(d, "prefix", "bin")])

    def test_no_npm_means_no_extra_folder(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"PATH": d}):
            self.assertEqual(loc.npm_global_bin([d]), [])


class TestEnsureAndCache(_FreshCache):
    def test_cached_dirs_never_starts_a_program(self):
        with patch.object(loc.subprocess, "run", side_effect=AssertionError("must not run")):
            self.assertEqual(loc.cached_dirs(), [])

    def test_ensure_looks_once_and_refresh_looks_again(self):
        with tempfile.TemporaryDirectory() as d, patch.object(loc, "_compute", return_value=[d]) as compute:
            self.assertEqual(loc.ensure(), [d])
            self.assertEqual(loc.ensure(), [d])
            self.assertEqual(compute.call_count, 1)
            loc.ensure(refresh=True)
            self.assertEqual(compute.call_count, 2)
            self.assertEqual(loc.cached_dirs(), [d])

    def test_a_failure_while_looking_leaves_an_empty_list_not_an_error(self):
        with patch.object(loc, "_compute", side_effect=RuntimeError("boom")):
            self.assertEqual(loc.ensure(), [])

    def test_off_windows_the_registry_is_not_read(self):
        if os.name != "nt":
            self.assertEqual(loc.windows_registry_path(), [])

    def test_windows_uses_the_registry_and_other_systems_the_login_shell(self):
        with patch.object(loc, "windows_registry_path", return_value=["/reg"]) as reg, \
             patch.object(loc, "login_shell_path", return_value=["/sh"]) as shell, \
             patch.object(loc, "npm_global_bin", return_value=[]), patch.object(loc.os.path, "lexists", return_value=True), \
             patch.object(loc, "windows_where", return_value=({}, {})):
            with patch.object(loc.os, "name", "nt"):
                self.assertEqual(loc._compute(), ["/reg"])
            with patch.object(loc.os, "name", "posix"):
                self.assertEqual(loc._compute(), ["/sh"])
        self.assertTrue(reg.called and shell.called)


@unittest.skipIf(os.name == "nt", "uses a POSIX script as the program")
class TestFindExecutableUsesTheOsPath(_FreshCache):
    def test_a_program_only_the_terminal_path_has_is_found_once_the_cache_is_filled(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"PATH": "/nonexistent"}):
            _script(d, "fakecli", "echo ok")
            self.assertIsNone(cb.find_executable("fakecli"))
            loc._cache["dirs"] = [d]
            self.assertEqual(cb.find_executable("fakecli"), os.path.join(d, "fakecli"))
            self.assertIn(d, cb.search_folders())

    def test_finding_a_program_never_starts_the_shell_or_npm(self):
        with patch.object(loc.subprocess, "run", side_effect=AssertionError("must not run")), patch.dict(os.environ, {"PATH": "/nonexistent"}):
            self.assertIsNone(cb.find_executable("no-such-program-xyz"))

    def test_the_child_process_gets_the_os_folders_too(self):
        with tempfile.TemporaryDirectory() as d:
            loc._cache["dirs"] = [d]
            self.assertIn(d, cb.scrubbed_environment({"PATH": "/usr/bin"})["PATH"].split(os.pathsep))


class TestWhatTheOsSays(_FreshCache):
    """The owner's Codex ran in PowerShell but the plugin said "not found" (2026-10-30, 29 folders searched). The OS's own answer is used
    even when Python cannot open the file (an app alias or link)."""

    def test_where_exe_output_is_read_and_a_miss_is_kept_as_the_reason(self):
        class Done:
            def __init__(self, code, text):
                self.returncode, self.stdout = code, text

        answers = {"codex": Done(0, b"C:\\Users\\u\\AppData\\Local\\Programs\\OpenAI\\Codex\\bin\\codex.exe\r\n"),
                   "claude": Done(1, b"INFO: Could not find files for the given pattern(s).\r\n")}
        with patch.object(loc.subprocess, "run", side_effect=lambda argv, **kw: answers[argv[1]]) as run:
            found, said = loc.windows_where(("claude", "codex"), ["C:\\reg"])
        self.assertEqual(found, {"codex": "C:\\Users\\u\\AppData\\Local\\Programs\\OpenAI\\Codex\\bin\\codex.exe"})
        self.assertIn("Could not find files", said["claude"])
        self.assertIn("C:\\reg", run.call_args.kwargs["env"]["PATH"])

    def test_where_exe_that_cannot_run_is_a_note_not_an_error(self):
        with patch.object(loc.subprocess, "run", side_effect=OSError("no")):
            found, said = loc.windows_where(("codex",), [])
        self.assertEqual(found, {})
        self.assertIn("could not be run", said["codex"])

    @unittest.skipIf(os.name == "nt", "uses a POSIX symlink")
    def test_a_program_python_cannot_open_is_still_found_by_name_and_by_where(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"PATH": d}):
            os.symlink(os.path.join(d, "nowhere"), os.path.join(d, "alias-cli"))  # a link whose target Python cannot open
            self.assertFalse(os.path.isfile(os.path.join(d, "alias-cli")))
            self.assertEqual(cb.find_executable("alias-cli"), os.path.join(d, "alias-cli"))
            self.assertEqual(cb.find_executable(os.path.join(d, "alias-cli")), os.path.join(d, "alias-cli"))
        loc._cache["resolved"] = {"zz-cli": "C:\\somewhere\\zz-cli.exe"}
        with patch.dict(os.environ, {"PATH": "/nonexistent"}):
            self.assertEqual(cb.find_executable("zz-cli"), "C:\\somewhere\\zz-cli.exe")

    @unittest.skipIf(os.name == "nt", "uses a POSIX symlink")
    def test_look_alikes_and_the_diagnosis_say_what_exists_but_cannot_be_used(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"PATH": d}):
            os.symlink(os.path.join(d, "nowhere"), os.path.join(d, "codex"))
            alikes = loc.look_alikes("codex", [d])
            self.assertEqual(alikes[0][0], os.path.join(d, "codex"))
            self.assertIn("cannot be opened", alikes[0][1])
            loc._cache["where"] = {"codex": "INFO: Could not find files for the given pattern(s)."}
            lines = cb.diagnose_missing("codex")
            self.assertTrue(any("where.exe codex said" in ln for ln in lines))
            self.assertTrue(any("cannot be opened" in ln for ln in lines))

    def test_a_missing_program_with_a_diagnosis_says_so_instead_of_only_not_installed(self):
        entry = {"provider": "codex_cli", "label": "Codex CLI", "found": False, "state": "missing", "version": "", "problem": "",
                 "diagnosis": ["C:\\x\\codex.exe: cannot be opened: OSError 1920"]}
        step = st.setup_step(entry, platform="win32")
        self.assertIn("could not use them", step["detail"])
        self.assertIn("OSError 1920", step["detail"])
        self.assertIn("Browse...", step["detail"])
        self.assertNotIn("could not use them", st.setup_step({**entry, "diagnosis": []}, platform="win32")["detail"])

    def test_a_program_that_was_found_but_cannot_be_started_says_why(self):
        entry = {"provider": "codex_cli", "label": "Codex CLI", "found": True, "path": "C:\\x\\codex.exe", "version": "",
                 "problem": "Could not start the CLI (PermissionError).", "state": "unknown", "note": ""}
        self.assertIn("could not be started", st.describe(entry, short=True))
        self.assertIn("PermissionError", st.describe(entry))


class TestDetectionUsesIt(unittest.TestCase):
    def test_detect_all_asks_the_os_afresh_and_reports_where_it_looked(self):
        with patch.object(st.cli_locator, "ensure") as ensure, patch.object(cb, "search_folders", return_value=["/a", "/b"]), \
             patch.object(st, "detect", return_value={"found": False, "path": "", "version": "", "problem": "nf"}):
            result = st.detect_all({})
        ensure.assert_called_once_with(refresh=True)
        self.assertTrue(all(e["searched"] == ["/a", "/b"] for e in result))
        self.assertIn("looked in 2 folders", st.describe(result[0], short=True))

    def test_a_chat_request_looks_at_the_os_path_before_giving_up(self):
        with patch.object(cb.cli_locator, "ensure") as ensure, patch.object(cb, "find_executable", return_value=None):
            reply = cb.CodexCliClient().complete([{"role": "user", "content": "hi"}], [])
        ensure.assert_called_once()
        self.assertIn("not found", reply["error"])


if __name__ == "__main__":
    sys.exit(unittest.main())
