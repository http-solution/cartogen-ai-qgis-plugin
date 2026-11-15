"""DEF-12 (B7): the isolation worker's reply stream must survive whatever a script prints or returns.

Uses the worker's QGIS-free `serve` loop and `_encode_response`; the live-QGIS path is covered by the CI live job's isolation tests.
"""
import io
import json
import unittest

from cartogen_ai.core.agent.services import _script_isolation_worker as w


def _replies(jobs, run_job):
    out = io.StringIO()
    w.serve([json.dumps(j) + "\n" for j in jobs], out, run_job)
    return [json.loads(line) for line in out.getvalue().splitlines()]


class TestEncode(unittest.TestCase):
    def test_non_json_results_are_turned_into_text_not_raised(self):
        import datetime
        reply = json.loads(w._encode_response({"success": True, "result": {"ids": {1, 2}, "day": datetime.date(2026, 1, 2)}}))
        self.assertTrue(reply["success"])
        self.assertEqual(reply["result"]["day"], "2026-01-02")

    def test_an_unencodable_reply_becomes_an_error_reply(self):
        circular = {}
        circular["self"] = circular
        reply = json.loads(w._encode_response({"result": circular}))
        self.assertIn("could not be sent back as JSON", reply["error"])


class TestServe(unittest.TestCase):
    def test_a_job_that_raises_does_not_end_the_loop(self):
        def run_job(job):
            if job["n"] == 1:
                raise RuntimeError("boom")
            return {"success": True, "result": job["n"]}
        replies = _replies([{"n": 1}, {"n": 2}], run_job)
        self.assertIn("crashed running the job: boom", replies[0]["error"])
        self.assertEqual(replies[1], {"success": True, "result": 2})

    def test_an_unencodable_result_does_not_end_the_loop(self):
        circular = {}
        circular["self"] = circular
        replies = _replies([{"n": 1}, {"n": 2}], lambda job: {"result": circular} if job["n"] == 1 else {"success": True})
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[1], {"success": True})

    def test_garbage_and_blank_lines_are_answered_or_skipped(self):
        out = io.StringIO()
        w.serve(["\n", "not json\n", json.dumps({"n": 1}) + "\n"], out, lambda job: {"success": True})
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("unreadable job", json.loads(lines[0])["error"])


class TestPrinted(unittest.TestCase):
    def test_output_is_capped(self):
        buf = io.StringIO("x" * (w._MAX_CAPTURED_OUTPUT + 50))
        self.assertTrue(w._printed(buf)["printed"].endswith("[truncated]"))
        self.assertEqual(w._printed(io.StringIO()), {})


if __name__ == "__main__":
    unittest.main()
