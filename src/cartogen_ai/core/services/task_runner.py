# -*- coding: utf-8 -*-
"""
Native QgsTask / Async Runner for Cartogen AI.
Executes non-blocking background LLM requests while keeping the QGIS GUI fully responsive.
"""

import time
import traceback
from ..agent import project_session
from ..agent.tools._qgis_enum_compat import resolve_qgis_enum
from ..logger import log_event

try:
    from qgis.core import QgsTask, QgsApplication
    QGIS_TASK_AVAILABLE = True
    # QGIS 4.x/Qt6 scopes this under QgsTask.Flag.CanCancel; QGIS 3.x/Qt5
    # exposes it flat. Resolved once here rather than assuming one form --
    # see tools/_qgis_enum_compat.py.
    _TASK_CAN_CANCEL = resolve_qgis_enum(QgsTask, "Flag", "CanCancel")
except ImportError:
    QGIS_TASK_AVAILABLE = False
    _TASK_CAN_CANCEL = None
    class QgsTask:
        pass


class AgentQgsTask(QgsTask):
    """QgsTask wrapper running agent inference in QGIS background thread pool."""

    def __init__(self, description: str, agent, user_text: str, on_complete=None, on_status=None, map_context=None, on_tool_step=None):
        if QGIS_TASK_AVAILABLE:
            super().__init__(description, _TASK_CAN_CANCEL)
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
        self._plugin_epoch = project_session.plugin_epoch()

    def run(self):
        """Executes in background worker thread."""
        # Structured-logging policy, 2026-09-20 audit (strict option chosen): this used
        # to log the first 60/200 characters of the raw user query/agent response
        # (secret-redacted, but still free-form content -- coordinates, names, file
        # paths, whatever the user typed or the model echoed back). log_event below
        # logs only status/duration -- never query/response content. See
        # core/logger.py's log_event docstring; use log_diagnostic() (off by default)
        # if raw content is ever needed while actively debugging locally.
        log_event("agent_task", tag="TaskRunner", status="started")
        _start = time.monotonic()
        client = getattr(self.agent, "client", None)
        try:
            if client is not None and hasattr(client, "set_status_callback") and self.on_status:
                client.set_status_callback(self.on_status)

            # self.isCanceled is QgsTask's own cancellation flag, set by
            # task.cancel() (see dock_widget.py's Stop button) -- passing it
            # through lets the agent loop notice a stop request between tool
            # iterations instead of always running to completion or the
            # iteration limit with no way to interrupt it.
            self.response = self.agent.run(
                self.user_text, map_context=self.map_context, should_stop=self.isCanceled,
                tool_step_callback=self.on_tool_step,
            )
            log_event("agent_task", tag="TaskRunner", status="done",
                      duration_ms=int((time.monotonic() - _start) * 1000))
            return True
        except Exception as e:
            self.error = e
            log_event("agent_task", tag="TaskRunner", status="failed",
                      duration_ms=int((time.monotonic() - _start) * 1000),
                      error_class=type(e).__name__, error=True)
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
        log_event("agent_task_finished", tag="TaskRunner", status="ok" if result else "failed")
        if project_session.plugin_retired(self._plugin_epoch):
            # The plugin was unloaded while this ran (#167): the widgets on_complete touches are already destroyed.
            log_event("agent_task_finished", tag="TaskRunner", status="skipped_plugin_unloaded")
            return
        if self.on_complete:
            # QGIS-001, 2026-09-13 audit: run() (background thread) wraps agent.run() in
            # try/except, but this call was not guarded at all -- on_complete is a closure
            # touching a live Qt widget (self._dock in chat_tab_widget.py). If the dock has
            # already been destroyed by the time this runs (see QGIS-002's unload() fix,
            # which narrows but doesn't eliminate the window), this would raise
            # `RuntimeError: wrapped C/C++ object has been deleted` from inside a
            # QGIS-task-manager-invoked callback with nothing to catch it. Matches this
            # codebase's own established convention (tool_step_callback's identical
            # try/except in agent_orchestrator.py's run()): a UI-side failure here must never look like
            # the agent run itself failed, and must never propagate into QGIS's own task-
            # manager machinery uncaught.
            try:
                if result and self.response is not None:
                    self.on_complete(self.response, None)
                else:
                    err_msg = str(self.error) if self.error else "Task failed or was cancelled."
                    self.on_complete(None, err_msg)
            except Exception as e:
                print(f"[TaskRunner] AgentQgsTask.finished()'s on_complete callback raised: {e}")
                traceback.print_exc()


_main_thread_invoker = None


def _get_main_thread_invoker():
    """A QObject that lives on the Qt main thread and runs the callables emitted to it there (queued signal).

    Audit A03: the thread fallback used to hand the completion callback to QTimer.singleShot(0, receiver, callable), which the Qt6
    binding does not offer; the broad except then called the widget callback directly on the WORKER thread. A queued signal is the
    supported way to cross threads. Create it first from the main thread (run_agent_task does); it is also moved there explicitly.
    Returns None when Qt is not available."""
    global _main_thread_invoker
    if _main_thread_invoker is not None:
        return _main_thread_invoker
    if not QGIS_TASK_AVAILABLE:
        return None
    try:
        from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
        queued = getattr(getattr(Qt, "ConnectionType", Qt), "QueuedConnection")

        class _Invoker(QObject):
            call = pyqtSignal(object)

            def __init__(self):
                super().__init__()
                self.call.connect(self._run, queued)

            def _run(self, fn):
                try:
                    fn()
                except Exception:
                    traceback.print_exc()

        invoker = _Invoker()
        app = QgsApplication.instance()
        if app is not None:
            invoker.moveToThread(app.thread())
        _main_thread_invoker = invoker
        return invoker
    except Exception as e:
        print(f"[TaskRunner] could not create the main-thread invoker: {e}")
        return None


def run_agent_task(agent, user_text: str, description: str = "Cartogen AI Processing", on_complete=None, on_status=None, map_context=None, on_tool_step=None):
    """Schedules agent task execution using QgsTask Manager or fallback thread.
    map_context must already have been gathered on the main thread by the
    caller (see agent/map_context.py) -- this function and everything it
    schedules may run in a background thread. on_tool_step(name, status, error),
    if given, fires around every individual tool call the agent makes during
    this turn (status "running" then "done"/"failed") -- see agent_orchestrator.py's run()
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

    epoch = project_session.plugin_epoch()
    # Made here, on the thread that called run_agent_task (the GUI thread), never lazily from the worker.
    invoker = _get_main_thread_invoker()

    def deliver(*args):
        """Run on_complete on the Qt main thread when there is one (it touches widgets), and never after an unload. With Qt
        available but no way to reach the main thread, the callback is NOT run on the worker: a widget must not be touched from
        there (audit A03), so the failure is logged instead."""
        if on_complete is None or project_session.plugin_retired(epoch):
            return
        if QGIS_TASK_AVAILABLE:
            if invoker is None:
                log_event("task_callback_dropped", tag="TaskRunner", error=True, reason="no main-thread invoker")
                return
            invoker.call.emit(lambda: None if project_session.plugin_retired(epoch) else on_complete(*args))
            return
        on_complete(*args)

    def worker():
        try:
            if on_status:
                on_status("Thinking...")
            resp = agent.run(
                user_text, map_context=map_context, should_stop=handle.isCanceled,
                tool_step_callback=on_tool_step,
            )
            deliver(resp, None)
        except Exception as e:
            deliver(None, str(e))

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return handle


class FunctionQgsTask(QgsTask):
    """Runs fn(is_cancelled) on a QGIS worker thread, then on_done(result, error) on the main
    thread. For non-agent background work started from the UI, e.g. local_data_loader's
    download (tens of MB -- blocking the GUI thread for it would freeze QGIS). Same guarded
    finished() as AgentQgsTask above, for the same reason (QGIS-001)."""

    def __init__(self, description, fn, on_done):
        if QGIS_TASK_AVAILABLE:
            super().__init__(description, _TASK_CAN_CANCEL)
        self.fn = fn
        self.on_done = on_done
        self.result_value = None
        self.error = None
        self._plugin_epoch = project_session.plugin_epoch()

    def run(self):
        try:
            self.result_value = self.fn(self.isCanceled)
            return True
        except Exception as e:
            self.error = e
            return False

    def finished(self, result):
        if project_session.plugin_retired(self._plugin_epoch):
            return
        try:
            if result:
                self.on_done(self.result_value, None)
            else:
                self.on_done(None, self.error or InterruptedError("Cancelled"))
        except Exception as e:
            print(f"[TaskRunner] FunctionQgsTask.finished()'s on_done callback raised: {e}")
            traceback.print_exc()


def run_background_call(description, fn, on_done):
    """Schedules FunctionQgsTask and returns it (it has .cancel()). Needs QGIS: the only callers
    are UI code, which already only exists inside QGIS."""
    task = FunctionQgsTask(description, fn, on_done)
    QgsApplication.taskManager().addTask(task)
    return task
