"""DEF-12 (B7), live QGIS: a script that prints, or returns something JSON cannot hold, must come back as a normal reply from the worker's
real job runner. Calls the worker's `_run_job` in-process (CI has no spawnable worker interpreter check); the spawn path stays covered by
tests/manual_isolation_bench. CI-only: written without a QGIS here, nobody has run it by hand."""
import json
import os
import tempfile
import unittest

try:
    from qgis.core import QgsProject
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestWorkerRunJob(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        from cartogen_ai.core.agent.services import _script_isolation_worker as w
        self.w = w
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        QgsProject.instance().clear()
        self.project_path = os.path.join(self.tmp.name, "scratch.qgz")
        QgsProject.instance().write(self.project_path)

    def _run(self, script):
        job = {"script": script, "project_path": self.project_path,
               "result_project_path": os.path.join(self.tmp.name, "result.qgz")}
        factory = lambda: {"QgsProject": QgsProject}  # noqa: E731
        return self.w._run_job(job, factory)

    def test_printed_text_is_returned_not_written_to_the_reply_channel(self):
        response = self._run("def run():\n    print('hello dashboard')\n    return 1\n")
        self.assertTrue(response["success"], response)
        self.assertIn("hello dashboard", response["printed"])

    def test_a_set_result_survives_the_reply_encoding(self):
        response = self._run("def run():\n    return {'ids': {1, 2}}\n")
        self.assertTrue(response["success"], response)
        self.assertEqual(json.loads(self.w._encode_response(response))["success"], True)

    def test_a_failing_script_keeps_what_it_printed(self):
        response = self._run("def run():\n    print('before')\n    raise ValueError('bad')\n")
        self.assertEqual(response["error"], "bad")
        self.assertIn("before", response["printed"])


if __name__ == "__main__":
    unittest.main()
