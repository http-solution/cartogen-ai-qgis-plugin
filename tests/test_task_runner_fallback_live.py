# -*- coding: utf-8 -*-
"""Audit A03: when QGIS task scheduling fails and the thread fallback runs, the completion callback must run on the Qt MAIN thread
(it touches widgets), never on the worker. Real Qt threads, a real QgsApplication."""
import threading
import time
import unittest
from unittest import mock

try:
    from qgis.core import QgsApplication
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


class _FakeAgent:
    def __init__(self, fail=False):
        self.fail = fail
        self.run_thread = None

    def run(self, text, map_context=None, should_stop=None, tool_step_callback=None):
        self.run_thread = threading.current_thread()
        if self.fail:
            raise RuntimeError("model exploded")
        return "answer"


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestFallbackDeliversOnTheMainThread(unittest.TestCase):
    def setUp(self):
        _boot_qgis()

    def _run_fallback(self, agent):
        from cartogen_ai.core.services import task_runner
        seen = {}

        def on_complete(resp, err):
            seen["thread"] = threading.current_thread()
            seen["resp"], seen["err"] = resp, err

        with mock.patch.object(task_runner, "AgentQgsTask", side_effect=RuntimeError("scheduling refused")):
            task_runner.run_agent_task(agent, "hello", "t", on_complete=on_complete)
        deadline = time.time() + 10
        while "thread" not in seen and time.time() < deadline:
            QgsApplication.processEvents()
            time.sleep(0.01)
        return seen

    def test_the_callback_runs_on_the_main_thread_after_a_scheduling_failure(self):
        agent = _FakeAgent()
        seen = self._run_fallback(agent)
        self.assertIn("thread", seen, "the completion callback was never delivered")
        self.assertIsNot(agent.run_thread, threading.main_thread(), "the agent should have run on a worker thread")
        self.assertIs(seen["thread"], threading.main_thread(), "the widget callback ran on the worker thread")
        self.assertEqual((seen["resp"], seen["err"]), ("answer", None))

    def test_an_agent_error_is_also_delivered_on_the_main_thread(self):
        seen = self._run_fallback(_FakeAgent(fail=True))
        self.assertIs(seen["thread"], threading.main_thread())
        self.assertIsNone(seen["resp"])
        self.assertIn("model exploded", seen["err"])


if __name__ == "__main__":
    unittest.main()
