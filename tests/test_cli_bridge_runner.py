"""PLAN-038: the CLI runner. Uses the Python interpreter itself as a stand-in CLI, so the subprocess, timeout, cap, cancel and
environment behaviour are really exercised (CI-only evidence; no vendor CLI is involved)."""
import os
import subprocess
import sys
import threading
import time
import unittest

from cartogen_ai.infrastructure.providers import cli_bridge as cb


def py(code):
    return [sys.executable, "-c", code]


class TestRunCli(unittest.TestCase):
    def test_round_trips_stdin_to_stdout(self):
        code, out, err = cb.run_cli(py("import sys; print(sys.stdin.read().upper())"), "hello", timeout=20)
        self.assertEqual((code, out.strip(), err), (0, "HELLO", ""))

    def test_returns_nonzero_exit_without_raising(self):
        code, _out, err = cb.run_cli(py("import sys; sys.stderr.write('bad'); sys.exit(3)"), "", timeout=20)
        self.assertEqual((code, err), (3, "bad"))

    def test_refuses_a_shell_string(self):
        with self.assertRaises(cb.CliBridgeError):
            cb.run_cli("echo hi", "")

    def test_missing_executable_is_a_clear_error(self):
        with self.assertRaises(cb.CliBridgeError) as cm:
            cb.run_cli(["/no/such/cli-xyz"], "")
        self.assertIn("executable path", str(cm.exception))

    def test_timeout_kills_the_process(self):
        started = time.monotonic()
        with self.assertRaises(cb.CliBridgeError) as cm:
            cb.run_cli(py("import time; time.sleep(60)"), "", timeout=1)
        self.assertIn("did not answer", str(cm.exception))
        self.assertLess(time.monotonic() - started, 20)

    def test_output_over_the_cap_stops_the_process(self):
        with self.assertRaises(cb.CliBridgeError) as cm:
            cb.run_cli(py("import sys\nwhile True: sys.stdout.write('x'*65536); sys.stdout.flush()"), "",
                       timeout=30, max_output_bytes=100_000)
        self.assertIn("size limit", str(cm.exception))

    def test_cancel_event_kills_the_process(self):
        ev = threading.Event()
        threading.Timer(0.5, ev.set).start()
        started = time.monotonic()
        with self.assertRaises(cb.CliBridgeError) as cm:
            cb.run_cli(py("import time; time.sleep(60)"), "", timeout=60, cancel_event=ev)
        self.assertIn("cancelled", str(cm.exception))
        self.assertLess(time.monotonic() - started, 20)

    @unittest.skipIf(os.name == "nt", "process-group kill is checked on POSIX; Windows uses taskkill /T")
    def test_cancel_also_kills_a_child_the_cli_started(self):
        marker = f"{os.getpid()}_{time.monotonic_ns()}"
        code = ("import subprocess,sys,time\n"
                f"subprocess.Popen([sys.executable,'-c','import time;time.sleep(60) # {marker}'])\n"
                "time.sleep(60)")
        ev = threading.Event()
        threading.Timer(1.0, ev.set).start()
        with self.assertRaises(cb.CliBridgeError):
            cb.run_cli(py(code), "", timeout=60, cancel_event=ev)
        time.sleep(0.5)
        alive = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True, check=False).stdout.strip()  # noqa: S607
        self.assertEqual(alive, "", "the CLI's child process survived the cancel")

    def test_provider_keys_are_not_passed_to_the_cli(self):
        base = {"PATH": os.environ.get("PATH", ""), "ANTHROPIC_API_KEY": "sk-secret", "OPENAI_API_KEY": "sk-other", "KEEP": "1"}
        env = cb.scrubbed_environment(base)
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertEqual(env["KEEP"], "1")
        probe = "import os; print(os.environ.get('ANTHROPIC_API_KEY','absent'), os.environ.get('KEEP','absent'))"
        os.environ["ANTHROPIC_API_KEY"] = "sk-secret"
        try:
            _c, out, _e = cb.run_cli(py(probe), "", timeout=20)
        finally:
            del os.environ["ANTHROPIC_API_KEY"]
        self.assertEqual(out.split()[0], "absent")

    @unittest.skipUnless(os.name == "nt", "Windows .cmd shims go through cmd.exe")
    def test_cmd_shim_rejects_metacharacters(self):
        with self.assertRaises(cb.CliBridgeError):
            cb.run_cli(["C:\\x\\claude.cmd", "a&b"], "")


class TestFindExecutable(unittest.TestCase):
    def test_empty_and_missing(self):
        self.assertIsNone(cb.find_executable(""))
        self.assertIsNone(cb.find_executable("/no/such/file-xyz"))

    def test_finds_a_real_file(self):
        self.assertEqual(cb.find_executable(sys.executable), sys.executable)


if __name__ == "__main__":
    unittest.main()
