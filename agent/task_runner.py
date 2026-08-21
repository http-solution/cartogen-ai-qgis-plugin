# -*- coding: utf-8 -*-
"""
Native QgsTask / Async Runner for Cartogen AI.
Executes non-blocking background LLM requests while keeping the QGIS GUI fully responsive.
"""

import traceback

try:
    from qgis.core import QgsTask, QgsApplication
    QGIS_TASK_AVAILABLE = True
except ImportError:
    QGIS_TASK_AVAILABLE = False
    class QgsTask:
        pass


class AgentQgsTask(QgsTask):
    """QgsTask wrapper running agent inference in QGIS background thread pool."""

    def __init__(self, description: str, agent, user_text: str, on_complete=None, on_status=None, map_context=None, on_tool_step=None):
        if QGIS_TASK_AVAILABLE:
            super().__init__(description, QgsTask.CanCancel)
        self.agent = agent
        self.user_text = user_text
        self.on_complete = on_complete
        self.on_status = on_status
        self.on_tool_step = on_tool_step
        # Gathered on the main thread before this task was scheduled -- PyQGIS
        # objects (QgsProject, layers) aren't thread-safe, so nothing in this
        # background run() may touch them directly; the summary is just a
        # plain dict by the time it gets here.
        self.map_context = map_context
        self.response = None
        self.error = None

    def run(self):
        """Executes in background worker thread."""
        print(f"[TaskRunner] AgentQgsTask.run() started for query: {self.user_text[:60]!r}")
        client = getattr(self.agent, "client", None)
        try:
            if client is not None and hasattr(client, "set_status_callback") and self.on_status:
                client.set_status_callback(self.on_status)

            print("[TaskRunner] Calling agent.run()...")
            # self.isCanceled is QgsTask's own cancellation flag, set by
            # task.cancel() (see dock_widget.py's Stop button) -- passing it
            # through lets the agent loop notice a stop request between tool
            # iterations instead of always running to completion or the
            # iteration limit with no way to interrupt it.
            self.response = self.agent.run(
                self.user_text, map_context=self.map_context, should_stop=self.isCanceled,
                tool_step_callback=self.on_tool_step,
            )
            print(f"[TaskRunner] agent.run() returned: {str(self.response)[:200]!r}")
            return True
        except Exception as e:
            self.error = e
            print(f"[TaskRunner] AgentQgsTask.run() raised: {e}")
            traceback.print_exc()
            return False
        finally:
            # Was inside the try, after agent.run() -- skipped entirely if
            # agent.run() raised, leaving a callback bound to this (possibly
            # about-to-be-destroyed) task object. Must run on every exit path.
            if client is not None and hasattr(client, "set_status_callback"):
                client.set_status_callback(None)

    def finished(self, result):
        """Executes on the main Qt GUI thread when background processing finishes."""
        print(f"[TaskRunner] AgentQgsTask.finished(result={result})")
        if self.on_complete:
            if result and self.response is not None:
                self.on_complete(self.response, None)
            else:
                err_msg = str(self.error) if self.error else "Task failed or was cancelled."
                self.on_complete(None, err_msg)


def run_agent_task(agent, user_text: str, description: str = "Cartogen AI Processing", on_complete=None, on_status=None, map_context=None, on_tool_step=None):
    """Schedules agent task execution using QgsTask Manager or fallback thread.
    map_context must already have been gathered on the main thread by the
    caller (see agent/map_context.py) -- this function and everything it
    schedules may run in a background thread. on_tool_step(name, status, error),
    if given, fires around every individual tool call the agent makes during
    this turn (status "running" then "done"/"failed") -- see agent.py's run()
    docstring."""
    if QGIS_TASK_AVAILABLE:
        try:
            task = AgentQgsTask(description, agent, user_text, on_complete, on_status, map_context, on_tool_step)
            QgsApplication.taskManager().addTask(task)
            return task
        except Exception as e:
            print(f"[TaskRunner] QgsTask dispatch failed, falling back to python thread: {e}")

    # Fallback thread for non-QGIS environments. Previously had no
    # cancellation mechanism at all -- dock_widget.py's Stop button calls
    # .cancel() on whatever this function returns, and a bare threading.Thread
    # has no such method, so Stop silently did nothing on this path (caught by
    # dock_widget's own try/except, not a crash, but a real functionality
    # gap). _FallbackTaskHandle gives it the same .cancel()/should_stop shape
    # AgentQgsTask already provides via QgsTask's isCanceled().
    import threading

    class _FallbackTaskHandle:
        def __init__(self):
            self._canceled = threading.Event()

        def cancel(self):
            self._canceled.set()

        def isCanceled(self):
            return self._canceled.is_set()

    handle = _FallbackTaskHandle()

    def worker():
        try:
            if on_status:
                on_status("Thinking...")
            resp = agent.run(
                user_text, map_context=map_context, should_stop=handle.isCanceled,
                tool_step_callback=on_tool_step,
            )
            if on_complete:
                on_complete(resp, None)
        except Exception as e:
            if on_complete:
                on_complete(None, str(e))

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return handle
