"""LEAD-10: tools/agy_probe.py reports each way a CLI can behave (answers, silent, hangs, fails, missing) in plain words. The process cases use small
stand-in programs and run only where a POSIX shell exists; the verdict wording and the lookup are pure and run everywhere. Not run against a real agy."""
import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("agy_probe", ROOT / "tools" / "agy_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class TestVerdict(unittest.TestCase):
    def test_each_outcome_has_its_own_plain_sentence(self):
        self.assertTrue(probe.verdict(None, "", "", 60, 60).startswith("HUNG"))
        self.assertTrue(probe.verdict(3, "", "not signed in", 0.2, 60).startswith("FAILED"))
        self.assertIn("not signed in", probe.verdict(3, "", "not signed in", 0.2, 60))
        self.assertTrue(probe.verdict(0, "  \n", "", 0.2, 60).startswith("SILENT"))
        self.assertTrue(probe.verdict(0, "ok\n", "", 0.2, 60).startswith("ANSWERED"))


class TestFind(unittest.TestCase):
    def test_a_missing_exe_is_said_not_guessed(self):
        path, how = probe.find_agy("/no/such/agy")
        self.assertIsNone(path)
        self.assertIn("not a file", how)

    def test_an_exe_that_exists_is_used(self):
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            name = handle.name
        self.addCleanup(os.remove, name)
        self.assertEqual(probe.find_agy(name), (name, "--exe"))


@unittest.skipIf(sys.platform.startswith("win"), "stand-in programs are shell scripts")
class TestRunsAProgram(unittest.TestCase):
    def fake(self, body):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "agy")
        Path(path).write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return path

    def test_answer_silence_failure_and_a_hang_are_all_reported(self):
        out = os.path.join(tempfile.mkdtemp(), "r.md")
        cases = {"echo ok": ("ANSWERED", 0), "exit 0": ("SILENT", 1), "echo no >&2; exit 3": ("FAILED", 1), 'if [ "$1" = "-p" ]; then sleep 20; fi': ("HUNG", 1)}
        for body, (word, exit_code) in cases.items():
            self.assertEqual(probe.main(["--exe", self.fake(body), "--out", out, "--timeout", "2"]), exit_code, body)
            self.assertIn(word, Path(out).read_text(encoding="utf-8"), body)

    def test_a_report_names_the_machine_and_never_needs_a_terminal(self):
        out = os.path.join(tempfile.mkdtemp(), "r.md")
        probe.main(["--exe", self.fake("echo ok"), "--out", out, "--timeout", "2"])
        text = Path(out).read_text(encoding="utf-8")
        self.assertIn("machine:", text)
        self.assertIn("stdin closed, output piped", text)


if __name__ == "__main__":
    unittest.main()
