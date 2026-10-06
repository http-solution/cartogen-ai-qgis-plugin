"""#167: a task created before the plugin was unloaded must not call back into the (destroyed) UI."""
import unittest

from cartogen_ai.core.agent import project_session
from cartogen_ai.core.services import task_runner


class _Agent:
    client = None

    def run(self, *a, **k):
        return "reply"


class TestPluginEpoch(unittest.TestCase):
    def test_retiring_the_plugin_marks_earlier_epochs_but_not_new_ones(self):
        before = project_session.plugin_epoch()
        project_session.retire_plugin()
        self.assertTrue(project_session.plugin_retired(before))
        self.assertFalse(project_session.plugin_retired(project_session.plugin_epoch()))
        self.assertFalse(project_session.plugin_retired(None))

    def test_a_project_switch_does_not_retire_the_plugin(self):
        epoch = project_session.plugin_epoch()
        project_session.invalidate()
        self.assertFalse(project_session.plugin_retired(epoch))

    def test_finished_calls_back_normally(self):
        got = []
        t = task_runner.AgentQgsTask("d", _Agent(), "hi", on_complete=lambda r, e: got.append((r, e)))
        t.isCanceled = lambda: False      # the QgsTask stub used without QGIS has no isCanceled
        self.assertTrue(t.run())
        t.finished(True)
        self.assertEqual(got, [("reply", None)])

    def test_finished_after_an_unload_does_not_call_back(self):
        got = []
        t = task_runner.AgentQgsTask("d", _Agent(), "hi", on_complete=lambda r, e: got.append((r, e)))
        t.isCanceled = lambda: False      # the QgsTask stub used without QGIS has no isCanceled
        t.run()
        project_session.retire_plugin()
        t.finished(True)
        self.assertEqual(got, [])

    def test_function_task_after_an_unload_does_not_call_back(self):
        got = []
        t = task_runner.FunctionQgsTask("d", lambda cancelled: 42, lambda r, e: got.append((r, e)))
        t.isCanceled = lambda: False
        t.run()
        project_session.retire_plugin()
        t.finished(True)
        self.assertEqual(got, [])


if __name__ == "__main__":
    unittest.main()
