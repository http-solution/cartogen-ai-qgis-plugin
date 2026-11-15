"""Offline tests for the worker-process handling in core/agent/services/script_isolation.py (_IsolationWorker).

PLAN-040 audit finding 11 (coverage): this file was 37% covered offline, and the uncovered part that CAN be tested without QGIS is the
safety machinery around model-written code: refusing to start the QGIS binary as the "Python" worker, the READY handshake, the per-job
timeout that kills a runaway script, crash detection, and restart after a kill. A fake subprocess stands in for the real one; the live job
covers the real worker and the layer reconciliation."""
import json
import threading
import unittest
from unittest import mock

from cartogen_ai.core.agent.services import script_isolation as si


class FakeProc:
    """Enough of subprocess.Popen: readline() blocks until a line is queued or the process is killed (then EOF)."""

    def __init__(self, lines=(), stderr_text="", write_error=None):
        self._lines = list(lines)
        self._cond = threading.Condition()
        self._killed = False
        self.stderr_text = stderr_text
        self.written = []
        self.returncode = None
        self.stdin = mock.Mock()
        self.stdin.write.side_effect = self._write
        self._write_error = write_error
        self.stdout = mock.Mock()
        self.stdout.readline.side_effect = self._readline
        self.stderr = mock.Mock()
        self.stderr.read.side_effect = lambda: self.stderr_text

    def _write(self, text):
        if self._write_error:
            raise self._write_error
        self.written.append(text)

    def push(self, line):
        with self._cond:
            self._lines.append(line)
            self._cond.notify_all()

    def _readline(self):
        with self._cond:
            while not self._lines and not self._killed:
                self._cond.wait(0.05)
            return self._lines.pop(0) if self._lines else ""

    def poll(self):
        return self.returncode

    def kill(self):
        with self._cond:
            self._killed = True
            self.returncode = -9
            self._cond.notify_all()

    def wait(self, timeout=None):
        return self.returncode


READY = json.dumps({"ready": True}) + "\n"


class WorkerCase(unittest.TestCase):
    def setUp(self):
        self.worker = si._IsolationWorker()
        self.addCleanup(self.worker.shutdown)
        patches = [
            mock.patch.object(si, "find_python_interpreter", return_value="/usr/bin/python3"),
            mock.patch.object(si, "_build_worker_environment", return_value={}),
            mock.patch.object(si, "_WORKER_HANDSHAKE_TIMEOUT_SECONDS", 0.3),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def popen(self, *procs):
        return mock.patch.object(si.subprocess, "Popen", side_effect=list(procs))


class TestStarting(WorkerCase):
    def test_it_refuses_to_start_when_the_interpreter_is_the_qgis_binary_itself(self):
        with mock.patch.object(si, "find_python_interpreter", return_value="C:/QGIS/bin/qgis-bin.exe"), self.popen() as popen:
            out = self.worker.submit({"script": "1"})
        self.assertIn("looks like the QGIS application binary", out["error"])
        popen.assert_not_called()

    def test_a_spawn_failure_is_reported_not_raised(self):
        with mock.patch.object(si.subprocess, "Popen", side_effect=OSError("no such file")):
            out = self.worker.submit({"script": "1"})
        self.assertIn("Could not spawn the isolation worker", out["error"])
        self.assertIn("no such file", out["error"])

    def test_a_worker_that_never_says_ready_is_killed_with_its_stderr_in_the_message(self):
        proc = FakeProc(stderr_text="ImportError: qgis")
        with self.popen(proc):
            out = self.worker.submit({"script": "1"})
        self.assertIn("did not answer within", out["error"])
        self.assertIn("ImportError: qgis", out["error"])
        self.assertEqual(proc.returncode, -9)

    def test_a_handshake_that_is_not_json_is_an_error_and_kills_the_worker(self):
        proc = FakeProc(lines=["not json\n"], stderr_text="boom")
        with self.popen(proc):
            out = self.worker.submit({"script": "1"})
        self.assertIn("not valid JSON", out["error"])
        self.assertEqual(proc.returncode, -9)

    def test_a_handshake_without_ready_true_is_an_error(self):
        proc = FakeProc(lines=[json.dumps({"ready": False}) + "\n"])
        with self.popen(proc):
            out = self.worker.submit({"script": "1"})
        self.assertIn("did not report ready", out["error"])


class TestRunningJobs(WorkerCase):
    def test_a_job_goes_to_the_worker_as_one_json_line_and_the_reply_comes_back_parsed(self):
        proc = FakeProc(lines=[READY])
        with self.popen(proc):
            proc.push(json.dumps({"result": 42}) + "\n")
            out = self.worker.submit({"script": "print(1)", "project_path": "p"})
        self.assertEqual(out, {"result": 42})
        sent = json.loads(proc.written[0])
        self.assertEqual(sent["script"], "print(1)")
        self.assertTrue(proc.written[0].endswith("\n"))

    def test_the_worker_is_reused_for_the_next_job_not_respawned(self):
        proc = FakeProc(lines=[READY, json.dumps({"result": 1}) + "\n", json.dumps({"result": 2}) + "\n"])
        with self.popen(proc) as popen:
            first = self.worker.submit({"script": "a"})
            second = self.worker.submit({"script": "b"})
        self.assertEqual((first, second), ({"result": 1}, {"result": 2}))
        self.assertEqual(popen.call_count, 1)

    def test_a_job_that_outlives_its_timeout_kills_the_worker_and_the_next_job_starts_a_fresh_one(self):
        hung = FakeProc(lines=[READY], stderr_text="stuck in a loop")
        fresh = FakeProc(lines=[READY, json.dumps({"result": "ok"}) + "\n"])
        with self.popen(hung, fresh) as popen:
            out = self.worker.submit({"script": "while True: pass"}, timeout=0.2)
            self.assertIn("exceeded the 0.2s isolation timeout", out["error"])
            self.assertIn("stuck in a loop", out["error"])
            self.assertEqual(hung.returncode, -9)
            again = self.worker.submit({"script": "1"})
        self.assertEqual(again, {"result": "ok"})
        self.assertEqual(popen.call_count, 2)

    def test_the_default_timeout_is_read_when_the_job_runs_not_when_the_function_was_defined(self):
        hung = FakeProc(lines=[READY])
        with self.popen(hung), mock.patch.object(si, "_JOB_TIMEOUT_SECONDS", 0.2):
            out = self.worker.submit({"script": "x"})
        self.assertIn("0.2s isolation timeout", out["error"])

    def test_a_broken_pipe_on_send_means_the_worker_had_crashed(self):
        proc = FakeProc(lines=[READY], stderr_text="segfault", write_error=BrokenPipeError())
        with self.popen(proc):
            out = self.worker.submit({"script": "1"})
        self.assertIn("not running when the job was sent", out["error"])
        self.assertIn("segfault", out["error"])

    def test_a_reply_that_is_not_json_is_an_error_and_kills_the_worker(self):
        proc = FakeProc(lines=[READY, "garbage\n"])
        with self.popen(proc):
            out = self.worker.submit({"script": "1"})
        self.assertIn("unreadable response", out["error"])
        self.assertEqual(proc.returncode, -9)


class TestHelpers(WorkerCase):
    def test_drain_stderr_tolerates_no_process_and_a_failing_pipe(self):
        self.assertEqual(self.worker._drain_stderr(None), "")
        proc = FakeProc()
        proc.stderr.read.side_effect = ValueError("closed")
        self.assertEqual(self.worker._drain_stderr(proc), "")

    def test_shutdown_kills_a_running_worker_and_is_safe_to_repeat(self):
        proc = FakeProc(lines=[READY, json.dumps({"result": 0}) + "\n"])
        with self.popen(proc):
            self.worker.submit({"script": "1"})
        self.worker.shutdown()
        self.worker.shutdown()
        self.assertEqual(proc.returncode, -9)
        self.assertIsNone(self.worker._proc)

    def test_end_of_output_is_no_answer_but_a_bare_newline_is_still_a_line(self):
        self.worker._proc = FakeProc(lines=["\n"])
        self.assertEqual(self.worker._read_line_with_timeout(0.2), "\n")
        self.worker._proc = FakeProc(lines=[])
        self.assertIsNone(self.worker._read_line_with_timeout(0.1))
        self.worker._proc.kill()
        self.worker._proc = None


if __name__ == "__main__":
    unittest.main()
