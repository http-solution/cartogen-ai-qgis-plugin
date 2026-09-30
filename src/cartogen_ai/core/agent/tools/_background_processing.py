# -*- coding: utf-8 -*-
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


class AnalysisCancelled(Exception):
    """The user pressed Stop while the analysis was running."""


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

        def reportError(self, error, fatalError=False):  # noqa: N802 -- Qt override
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


# Objects whose worker thread did not stop when asked. Kept referenced for the life of the process:
# destroying a context/feedback under a running thread crashes QGIS.
_ABANDONED = []


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


def can_run_in_background():
    return bool(QGIS_AVAILABLE and _on_gui_thread() and _enabled_in_settings())


def run_algorithm(algorithm_id, params, context, fallback, use_background=True, label="Analysis",
                  poll_ms=100, status_every_s=3.0, first_status_after_s=2.0, abandon_after_s=20.0):
    """processing.run(algorithm_id, params, context=context), without freezing the GUI.

    `fallback(algorithm_id, params, context=context)` is the plain synchronous call, used whenever
    background execution isn't possible or wanted. Raises AnalysisCancelled on Stop, and
    RuntimeError (with the algorithm's own message) if it fails -- like processing.run raises.
    Returns the same results dict as processing.run, with output layers as QgsMapLayer objects."""
    if not use_background or not can_run_in_background():
        return fallback(algorithm_id, params, context=context)

    algorithm = QgsApplication.processingRegistry().createAlgorithmById(algorithm_id)
    if algorithm is None:
        return fallback(algorithm_id, params, context=context)   # let processing.run raise its own error

    feedback = _CollectingFeedback()
    task = QgsProcessingAlgRunnerTask(algorithm, params, context, feedback)
    state = {"finished": False, "ok": False, "results": {}, "cancelled_at": None}
    loop = QEventLoop()

    def on_executed(ok, results):
        state.update(finished=True, ok=bool(ok), results=results or {})
        loop.quit()

    task.executed.connect(on_executed)
    started = time.monotonic()
    last_status = [started - status_every_s + first_status_after_s]   # a fast call says nothing

    def tick():
        now = time.monotonic()
        if state["cancelled_at"] is None and cancel_signal.is_cancelled():
            state["cancelled_at"] = now
            feedback.cancel()
            task.cancel()
            cancel_signal.report(f"{label}: stopping...")
        elif state["cancelled_at"] is not None and now - state["cancelled_at"] > abandon_after_s:
            loop.quit()                                  # the algorithm is ignoring the cancel
        elif state["cancelled_at"] is None and now - last_status[0] >= status_every_s:
            last_status[0] = now
            cancel_signal.report(f"{label}: working on the road network... {now - started:.0f}s "
                                 "(press Stop to cancel)")

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
        _ABANDONED.append((task, algorithm, feedback, context, params))
        log_event("network_analysis", tag="Tools", tool=algorithm_id, status="abandoned",
                  duration_ms=int(elapsed * 1000))
        raise AnalysisCancelled("Stopped; the analysis is still winding down in the background.")
    if state["cancelled_at"] is not None:
        log_event("network_analysis", tag="Tools", tool=algorithm_id, status="cancelled",
                  duration_ms=int(elapsed * 1000))
        raise AnalysisCancelled("Stopped by the user.")
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
