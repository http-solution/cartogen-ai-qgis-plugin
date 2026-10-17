"""Run a QGIS Processing algorithm on a worker thread while the GUI keeps responding.

The problem (live-reported 2026-09-25, BUG-2026-09-25-2): tools run on QGIS's GUI thread, and
native:serviceareafrompoint / native:shortestpathpointtolayer spend their time building a routing
graph from every road in the network layer. Measured on real Jordan OSM roads: 25 s at 39,017
roads, 60 s at 68,123, 125 s at 107,719, and 292-572 s per call on the full 161,041, during which
QGIS showed "Not Responding" and offered no way to stop. (Not the ellipsoid: planar and
ellipsoidal times matched within 2 s.)

The approach, prototyped on the real 39,017-road network before building on it: the algorithm runs
in a QgsProcessingAlgRunnerTask (a QGIS worker thread) while this call spins a nested Qt event
loop on the calling (GUI) thread. That keeps the window alive -- 293 UI ticks during an 18.5 s run,
worst gap 77 ms against a 50 ms timer, where the synchronous call gives none -- returns the same
result as processing.run (same feature count), and honours Stop: a cancel returned 0.0 s after it
was requested. The call still blocks *this tool*, which is what the agent loop needs (it waits for
the tool's result); it just no longer blocks QGIS.

Deliberately conservative:
  * Only used on the GUI thread of a real QgsApplication, and only when asked (`use_background`);
    everywhere else -- tests, other threads, the kill-switch setting -- it is exactly processing.run.
  * If the algorithm ignores a cancel, the worker's objects are kept alive (never destroyed under a
    running thread) and the call returns anyway after `abandon_after_s`.
  * Failure messages from the algorithm are surfaced, not just "failed".
"""
import contextlib
import threading
import time

from ...logger import log_event
from .. import cancel_signal

try:
    from qgis.core import (
        QgsApplication, QgsMapLayer, QgsProcessingAlgRunnerTask, QgsProcessingFeedback,
        QgsProcessingOutputMapLayer, QgsProcessingOutputRasterLayer, QgsProcessingOutputVectorLayer,
    )
    from qgis.PyQt.QtCore import QCoreApplication, QEventLoop, QThread, QTimer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


class AnalysisCancelledError(Exception):
    """The user pressed Stop while the analysis was running."""


class AnalysisTimedOutError(AnalysisCancelledError):
    """The analysis ran longer than its time limit and was stopped (rc46). A subclass so every existing `except AnalysisCancelledError`
    still stops cleanly."""


def timeout_message(label, limit_s, still_running=False):
    """What the chat says when an analysis hit its time limit. Pure."""
    tail = " It may still be winding down in the background." if still_running else ""
    return (f"'{label}' ran longer than {limit_s:.0f} seconds and was stopped; nothing was added to the project.{tail} "
            "Try a smaller area or fewer layers, or another algorithm that does the same job.")


def is_no_route_message(error):
    """True for QGIS's per-destination 'There is no route from start point ... to end point ...' message."""
    return "no route from start point" in str(error).lower()


def new_feedback():
    """A QgsProcessingFeedback that keeps unreachable-destination messages out of the CRITICAL log, or None
    outside QGIS. Used by both the background and the synchronous routing paths."""
    return _CollectingFeedback() if QGIS_AVAILABLE else None


if QGIS_AVAILABLE:
    class _CollectingFeedback(QgsProcessingFeedback):
        """Keeps the algorithm's error messages so a failure can say why."""

        def __init__(self):
            super().__init__()
            self.errors = []
            self.no_route_count = 0

        def reportError(self, error, fatalError=False):
            # rc7 smoke test F15: ~130 "There is no route from start point ... to end point ..." lines were logged at
            # CRITICAL for facilities the road network never reaches (islands, disconnected clusters). That is a normal
            # result, not a failure: count it (see no_route_count) instead of raising it to CRITICAL, and let every
            # other non-fatal message through unchanged. QgsProcessingFeedback::reportError(error, fatalError=false)
            # is the documented virtual this overrides.
            if not fatalError and is_no_route_message(error):
                self.no_route_count += 1
                return
            self.errors.append(str(error))
            super().reportError(error, fatalError)


# Objects whose worker thread did not stop when asked. Kept referenced while the thread may still run:
# destroying a context/feedback under a running thread crashes QGIS.
# Rc20 audit A16: they used to stay referenced for the life of the process, so every abandoned analysis leaked its task, routing
# context and (large) parameter layers forever. An entry is now released as soon as its task reports a terminal state
# (see _abandon / release_finished_abandoned).
_ABANDONED: list = []


def _task_is_done(task):
    """True when the QgsTask has reached Complete or Terminated, i.e. its worker thread is finished with the objects."""
    try:
        from qgis.core import QgsTask
        return task.status() in (QgsTask.TaskStatus.Complete, QgsTask.TaskStatus.Terminated)
    except Exception:
        return False   # unknown -> keep it: leaking is safer than destroying under a live thread


def release_finished_abandoned(is_done=None):
    """Drops abandoned entries whose task has finished; returns how many were released. `is_done(task)` is injectable for tests."""
    check = is_done or _task_is_done
    kept = [entry for entry in _ABANDONED if not check(entry[0])]
    released = len(_ABANDONED) - len(kept)
    _ABANDONED[:] = kept
    return released


def _abandon(entry):
    """Keep `entry` alive until its task finishes, then let it go (also swept on every later run)."""
    _ABANDONED.append(entry)
    task = entry[0]
    # the sweep at the start of the next run still releases it
    with contextlib.suppress(Exception):
        task.taskCompleted.connect(release_finished_abandoned)
        task.taskTerminated.connect(release_finished_abandoned)


def _on_gui_thread():
    try:
        app = QCoreApplication.instance()
        return app is not None and QThread.currentThread() == app.thread()
    except Exception:
        return False


def _enabled_in_settings():
    try:
        from qgis.core import QgsSettings
        from ....infrastructure.settings_keys import SETTINGS_BACKGROUND_NETWORK_ANALYSIS
        return bool(QgsSettings().value(SETTINGS_BACKGROUND_NETWORK_ANALYSIS, True, type=bool))
    except Exception:
        return True


def is_thread_safe_algorithm(algorithm_id):
    """True for native (C++) QGIS algorithms, the only ones this module runs on a worker thread without a special reason.

    PR #249 / #251 evidence: running gdal:slope (a Python-implemented algorithm) through the task runner crashed the QGIS 4.2.2
    live CI job with a segfault in 2 of 4 runs, while the native algorithms (network analysis since rc12, native:buffer) were stable.
    Python-implemented algorithms (gdal:, qgis:, script:) therefore stay on the GUI thread until a cause is found and fixed. Pure."""
    return str(algorithm_id).startswith("native:")


def can_run_in_background():
    return bool(QGIS_AVAILABLE and _on_gui_thread() and _enabled_in_settings())


def run_algorithm(algorithm_id, params, context, fallback, use_background=True, label="Analysis",
                  poll_ms=100, status_every_s=3.0, first_status_after_s=2.0, abandon_after_s=20.0, max_runtime_s=None):
    """processing.run(algorithm_id, params, context=context), without freezing the GUI.

    `fallback(algorithm_id, params, context=context)` is the plain synchronous call, used whenever
    background execution isn't possible or wanted. Raises AnalysisCancelledError on Stop, and
    RuntimeError (with the algorithm's own message) if it fails -- like processing.run raises.
    Returns the same results dict as processing.run, with output layers as QgsMapLayer objects.

    max_runtime_s (rc46): stop the run by itself after this many seconds and raise AnalysisTimedOutError. The rc45 smoke run had four
    raster algorithms and one vector one that showed the progress line for 3 to 10 minutes on 80 by 80 test data until the tester pressed
    Stop; CI ran the same algorithms in seconds, so the cause is not known. A bounded wait with a clear message beats an open-ended one.
    The default None keeps every other caller (network analysis on large road networks) unlimited."""
    if not use_background or not can_run_in_background():
        return fallback(algorithm_id, params, context=context)

    release_finished_abandoned()
    algorithm = QgsApplication.processingRegistry().createAlgorithmById(algorithm_id)
    if algorithm is None:
        return fallback(algorithm_id, params, context=context)   # let processing.run raise its own error

    feedback = _CollectingFeedback()
    task = QgsProcessingAlgRunnerTask(algorithm, params, context, feedback)
    state = {"finished": False, "ok": False, "results": {}, "cancelled_at": None, "timed_out": False}
    loop = QEventLoop()
    log_event("network_analysis", tag="Tools", tool=algorithm_id, status="started")   # a hang shows as a start with no done/abandoned

    def on_executed(ok, results):
        state.update(finished=True, ok=bool(ok), results=results or {})
        loop.quit()

    task.executed.connect(on_executed)
    started = time.monotonic()
    last_status = [started - status_every_s + first_status_after_s]   # a fast call says nothing

    def tick():
        now = time.monotonic()
        if state["cancelled_at"] is None and max_runtime_s and now - started > max_runtime_s:
            state["cancelled_at"] = now
            state["timed_out"] = True
            feedback.cancel()
            task.cancel()
            cancel_signal.report(f"{label}: taking longer than {max_runtime_s:.0f}s, stopping...")
        elif state["cancelled_at"] is None and cancel_signal.is_cancelled():
            state["cancelled_at"] = now
            feedback.cancel()
            task.cancel()
            cancel_signal.report(f"{label}: stopping...")
        elif state["cancelled_at"] is not None and now - state["cancelled_at"] > abandon_after_s:
            loop.quit()                                  # the algorithm is ignoring the cancel
        elif state["cancelled_at"] is None and now - last_status[0] >= status_every_s:
            last_status[0] = now
            # was "working on the road network" for every algorithm, which told people running a raster algorithm about a road network
            cancel_signal.report(f"{label}: still running... {now - started:.0f}s (press Stop to cancel)")

    timer = QTimer()
    timer.setInterval(poll_ms)
    timer.timeout.connect(tick)
    timer.start()
    QgsApplication.taskManager().addTask(task)
    try:
        loop.exec()
    finally:
        timer.stop()

    elapsed = time.monotonic() - started
    if not state["finished"]:
        # abandoned: the worker still owns these -- see _ABANDONED
        _abandon((task, algorithm, feedback, context, params))
        log_event("network_analysis", tag="Tools", tool=algorithm_id, status="abandoned",
                  duration_ms=int(elapsed * 1000))
        if state["timed_out"]:
            raise AnalysisTimedOutError(timeout_message(label, max_runtime_s, still_running=True))
        raise AnalysisCancelledError("Stopped; the analysis is still winding down in the background.")
    if state["cancelled_at"] is not None:
        log_event("network_analysis", tag="Tools", tool=algorithm_id, status="timed_out" if state["timed_out"] else "cancelled",
                  duration_ms=int(elapsed * 1000))
        if state["timed_out"]:
            raise AnalysisTimedOutError(timeout_message(label, max_runtime_s))
        raise AnalysisCancelledError("Stopped by the user.")
    if not state["ok"]:
        log_event("network_analysis", tag="Tools", tool=algorithm_id, status="failed",
                  duration_ms=int(elapsed * 1000), error=True)
        raise RuntimeError("; ".join(feedback.errors) or f"{algorithm_id} failed")

    # Same post-processing as processing.run: output layer ids become the layer objects.
    results = dict(state["results"])
    for out in algorithm.outputDefinitions():
        if out.name() in results and isinstance(
                out, (QgsProcessingOutputVectorLayer, QgsProcessingOutputRasterLayer, QgsProcessingOutputMapLayer)):
            value = results[out.name()]
            if not isinstance(value, QgsMapLayer):
                layer = context.takeResultLayer(value)
                if layer:
                    results[out.name()] = layer
    log_event("network_analysis", tag="Tools", tool=algorithm_id, status="done", duration_ms=int(elapsed * 1000),
              count=feedback.no_route_count)
    return results


def run_synchronously_with_repaint(algorithm_id, run, min_interval_s=0.25):
    """processing.run for algorithms that must stay on the GUI thread (GRASS, GDAL, QGIS Python algorithms), but with the window kept
    painting (rc46).

    rc45 smoke run on Windows: GRASS algorithms took 2 to 12 minutes each even on 80 by 80 test data (v.voronoi 12 min, r.fillnulls 12 min,
    v.net.iso 8 min) and QGIS showed "Not Responding" the whole time. CI on Linux ran the same algorithms in seconds, so the time is the
    GRASS start-up and file import on that machine, which this cannot shorten. What it can do: the feedback object below lets Qt paint and
    run timers every `min_interval_s` while the algorithm reports progress, so the window does not freeze and the user sees that
    something is happening. User input events are excluded on purpose (no clicks on other tools while an algorithm runs on this thread),
    which also means Stop cannot reach a run on this thread; that limit is stated in the tool description. Outside a real GUI thread, or
    with the background-analysis setting off, this is exactly processing.run. Not verified in a desktop session.

    `run(feedback)` performs the plain processing.run call; it is given None when no repainting feedback is wanted. The caller owns the
    call so that its own processing import (and tests that replace it) stay in charge.
    """
    if not (QGIS_AVAILABLE and _on_gui_thread() and _enabled_in_settings()):
        return run(None)

    class _RepaintingFeedback(QgsProcessingFeedback):
        def __init__(self):
            super().__init__()
            self._last = 0.0

        def _pump(self):
            now = time.monotonic()
            if now - self._last >= min_interval_s:
                self._last = now
                QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

        def setProgress(self, progress):  # noqa: N802
            super().setProgress(progress)
            self._pump()

        def pushInfo(self, info):  # noqa: N802
            super().pushInfo(info)
            self._pump()

        def pushConsoleInfo(self, info):  # noqa: N802
            super().pushConsoleInfo(info)
            self._pump()

        def pushCommandInfo(self, info):  # noqa: N802
            super().pushCommandInfo(info)
            self._pump()

    feedback = _RepaintingFeedback()
    log_event("network_analysis", tag="Tools", tool=algorithm_id, status="started")
    started = time.monotonic()
    try:
        return run(feedback)
    finally:
        log_event("network_analysis", tag="Tools", tool=algorithm_id, status="finished_on_gui_thread",
                  duration_ms=int((time.monotonic() - started) * 1000))


def run_callable(fn, label="Analysis", use_background=True, poll_ms=100, status_every_s=3.0, first_status_after_s=2.0,
                 abandon_after_s=20.0):
    """fn() without freezing the GUI, for work that touches NO QGIS objects (GDAL/OGR datasets, numpy arrays, plain data) --
    rc20 audit A14. fn runs on a plain worker thread while this call spins a nested Qt event loop on the GUI thread, exactly as
    run_algorithm does for Processing algorithms: the window stays alive and Stop is honoured.

    Do NOT pass a callable that reads or writes QgsMapLayer/QgsProject objects: those are only safe on the GUI thread (use
    run_algorithm for Processing algorithms, which QGIS itself makes thread-safe). Returns fn's result; re-raises its exception;
    raises AnalysisCancelledError on Stop. Outside a real GUI thread (tests, the kill-switch setting) it simply calls fn()."""
    if not use_background or not can_run_in_background():
        return fn()

    state = {"done": False, "result": None, "error": None, "cancelled_at": None}

    def work():
        try:
            state["result"] = fn()
        except BaseException as exc:      # handed back to the caller, not lost on the worker thread
            state["error"] = exc
        finally:
            state["done"] = True

    thread = threading.Thread(target=work, name=f"cartogen-{label}", daemon=True)
    loop = QEventLoop()
    started = time.monotonic()
    last_status = [started - status_every_s + first_status_after_s]

    def tick():
        now = time.monotonic()
        if state["done"]:
            loop.quit()
        elif state["cancelled_at"] is None and cancel_signal.is_cancelled():
            state["cancelled_at"] = now
            cancel_signal.report(f"{label}: stopping...")
        elif state["cancelled_at"] is not None and now - state["cancelled_at"] > min(abandon_after_s, 2.0):
            loop.quit()                   # a plain thread cannot be interrupted: give up waiting for it
        elif state["cancelled_at"] is None and now - last_status[0] >= status_every_s:
            last_status[0] = now
            cancel_signal.report(f"{label}: working... {now - started:.0f}s (press Stop to cancel)")

    timer = QTimer()
    timer.setInterval(poll_ms)
    timer.timeout.connect(tick)
    timer.start()
    thread.start()
    try:
        loop.exec()
    finally:
        timer.stop()
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if state["cancelled_at"] is not None and not state["done"]:
        log_event("background_callable", tag="Tools", tool=label, status="abandoned", duration_ms=elapsed_ms)
        raise AnalysisCancelledError("Stopped; the work is still winding down in the background.")
    if state["cancelled_at"] is not None:
        raise AnalysisCancelledError("Stopped by the user.")
    if state["error"] is not None:
        log_event("background_callable", tag="Tools", tool=label, status="failed", duration_ms=elapsed_ms, error=True)
        raise state["error"]
    log_event("background_callable", tag="Tools", tool=label, status="done", duration_ms=elapsed_ms)
    return state["result"]
