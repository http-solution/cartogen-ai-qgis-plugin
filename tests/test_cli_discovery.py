"""CLI program discovery (PLAN-038): finds a CLI that the terminal finds but a GUI-launched QGIS PATH does not."""
import os
import stat
import tempfile
import unittest
from unittest import mock

from cartogen_ai.infrastructure.providers import cli_bridge as cb
from cartogen_ai.infrastructure.providers import cli_bridge_status as st

POSIX = os.name != "nt"


def _make_exe(folder, name):
    path = os.path.join(folder, name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\necho ok\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


@unittest.skipUnless(POSIX, "uses POSIX executable bits and ~/.local/bin")
class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.bin = os.path.join(self.home, ".npm-global", "bin")
        os.makedirs(self.bin)
        self.exe = _make_exe(self.bin, "codex")
        env = {"HOME": self.home, "PATH": "/nonexistent"}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_bare_name_found_in_usual_install_folder_when_path_is_short(self):
        self.assertEqual(cb.find_executable("codex"), self.exe)

    def test_quotes_spaces_and_tilde_are_tolerated(self):
        self.assertEqual(cb.find_executable(f'  "{self.exe}"  '), self.exe)
        self.assertEqual(cb.find_executable("~/.npm-global/bin/codex"), self.exe)

    def test_folder_alone_is_not_a_program_but_find_in_folder_resolves_it(self):
        self.assertIsNone(cb.find_executable(self.bin))
        self.assertEqual(cb.find_in_folder(self.bin, "codex"), self.exe)
        self.assertEqual(st.locate("codex_cli", self.bin), self.exe)

    def test_missing_program_is_none(self):
        self.assertIsNone(cb.find_executable("no-such-cli"))
        self.assertIsNone(cb.find_executable(""))

    def test_child_path_gains_install_folders_without_dropping_keys_scrub(self):
        env = cb.scrubbed_environment({"PATH": "/nonexistent", "OPENAI_API_KEY": "x"})
        self.assertIn(self.bin, env["PATH"].split(os.pathsep))
        self.assertTrue(env["PATH"].startswith("/nonexistent"))
        self.assertNotIn("OPENAI_API_KEY", env)

    def test_not_found_message_tells_user_how_to_paste_the_path(self):
        msg = st.not_found_message("codex_cli", "")
        self.assertIn("which codex", msg)
        self.assertIn("paste the full path", msg)

    def test_detect_reports_found_via_extra_folder(self):
        with mock.patch.object(cb, "run_cli", return_value=(0, "codex 1.0\n", "")):
            result = st.detect("codex_cli", "")
        self.assertTrue(result["found"])
        self.assertEqual(result["path"], self.exe)


class TestWindowsExtension(unittest.TestCase):
    def test_path_without_extension_gains_cmd(self):
        with tempfile.TemporaryDirectory() as d:
            shim = os.path.join(d, "codex.cmd")
            open(shim, "w").close()
            with mock.patch.dict(os.environ, {"PATHEXT": ".exe;.cmd"}):
                self.assertEqual(cb._with_pathext(os.path.join(d, "codex")), shim)
                self.assertIsNone(cb._with_pathext(os.path.join(d, "other")))


if __name__ == "__main__":
    unittest.main()
