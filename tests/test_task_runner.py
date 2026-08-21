# -*- coding: utf-8 -*-
import threading
import time
import unittest
from unittest.mock import MagicMock

from cartogen_ai.core.agent.task_runner import AgentQgsTask, run_agent_task, QGIS_TASK_AVAILABLE


class _FakeAgent:
    """Minimal stand-in exercising both the happy path and the
    status-callback-reset-on-exception path, without needing a real client."""
    def __init__(self, client=None, raise_error=None, response="ok", capture_should_stop=None):
        self.client = client
        self._raise_error = raise_error
        self._response = response
        self._capture_should_stop = capture_should_stop

    def run(self, user_text, map_context=None, should_stop=None, tool_step_callback=None):
        if self._capture_should_stop is not None:
            self._capture_should_stop["fn"] = should_stop
        if self._raise_error:
            raise self._raise_error
        return self._response


def _make_bare_task(*args, **kwargs):
    """AgentQgsTask.run() reads self.isCanceled -- a real QgsTask always
    provides this, but the fallback stub used outside QGIS (QGIS_TASK_AVAILABLE
    is False in this test environment) doesn't. Filling it in here is a
    test-only stand-in for what a real QgsTask base class supplies in
    production, not a change to AgentQgsTask itself."""
    task = AgentQgsTask(*args, **kwargs)
    if not hasattr(task, "isCanceled"):
        task.isCanceled = lambda: False
    return task


class TestAgentQgsTaskRun(unittest.TestCase):
    def test_status_callback_reset_on_success(self):
        client = MagicMock()
        client.set_status_callback = MagicMock()
        agent = _FakeAgent(client=client)
        task = _make_bare_task("desc", agent, "hello", on_status=lambda s: None)
        ok = task.run()
        self.assertTrue(ok)
        # First call sets the real callback, second call (in `finally`) resets it to None.
        self.assertEqual(client.set_status_callback.call_count, 2)
        self.assertIsNone(client.set_status_callback.call_args.args[0])

    def test_status_callback_reset_even_when_agent_run_raises(self):
        # B4: the reset used to sit right after agent.run() succeeded, inside
        # the try -- an exception skipped it entirely, leaving a callback
        # bound to a task object that may be about to be discarded.
        client = MagicMock()
        agent = _FakeAgent(client=client, raise_error=RuntimeError("boom"))
        task = _make_bare_task("desc", agent, "hello", on_status=lambda s: None)
        ok = task.run()
        self.assertFalse(ok)
        self.assertIsInstance(task.error, RuntimeError)
        self.assertEqual(client.set_status_callback.call_count, 2)
        self.assertIsNone(client.set_status_callback.call_args.args[0])


class TestFallbackTaskCancellation(unittest.TestCase):
    """These exercise run_agent_task's non-QgsTask fallback thread path,
    which is exactly what runs in this test environment (QGIS_TASK_AVAILABLE
    is False here, same as any non-QGIS Python process)."""

    def setUp(self):
        if QGIS_TASK_AVAILABLE:
            self.skipTest("QGIS is available in this environment -- fallback path isn't exercised.")

    def test_returned_handle_has_a_working_cancel_interface(self):
        # B3: previously returned a bare threading.Thread, which has no
        # .cancel() -- dock_widget.py's Stop button calling .cancel() on it
        # silently did nothing (caught by its own try/except).
        done = threading.Event()

        def on_complete(resp, err):
            done.set()

        handle = run_agent_task(_FakeAgent(), "hello", on_complete=on_complete)
        self.assertTrue(hasattr(handle, "cancel"))
        self.assertFalse(handle.isCanceled())
        handle.cancel()
        self.assertTrue(handle.isCanceled())
        done.wait(timeout=2)

    def test_should_stop_is_threaded_through_to_agent_run(self):
        capture = {}
        done = threading.Event()
        agent = _FakeAgent(capture_should_stop=capture)

        def on_complete(resp, err):
            done.set()

        handle = run_agent_task(agent, "hello", on_complete=lambda r, e: on_complete(r, e))
        done.wait(timeout=2)
        self.assertIn("fn", capture)
        self.assertFalse(capture["fn"]())  # not canceled yet
        handle.cancel()
        self.assertTrue(capture["fn"]())  # now reflects the cancellation


if __name__ == "__main__":
    unittest.main()
