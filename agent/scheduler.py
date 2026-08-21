# -*- coding: utf-8 -*-
"""
In-session recurring workflow scheduler for Cartogen AI.

Session-scoped only: a schedule lives for as long as QGIS stays open with
this plugin loaded, driven by QTimer on the main Qt thread. Nothing here
runs while QGIS is closed, and nothing here touches the OS scheduler (cron /
Windows Task Scheduler) -- see QGIS_AI_Agent_PRD.md 5.1/5.3 for why a true
headless trigger was scoped out of this pass.
"""

try:
    from qgis.PyQt.QtCore import QTimer, QObject, pyqtSignal
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    class QObject:
        pass
    def pyqtSignal(*args, **kwargs):
        return None


# A shorter interval turns each tick into a self-inflicted denial-of-service
# against the main Qt thread -- e.g. 0.001 minutes becomes a ~60ms QTimer
# re-running full geoprocessing (zonal statistics, severity scoring) on
# every fire. Found live in a security review (docs/
# SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md A.1) -- interval_minutes <= 0
# was the only guard before this.
_MIN_INTERVAL_MINUTES = 1

# No cap previously meant a model could spin up an unbounded number of
# independent QTimers (one per preset_name), each re-running geoprocessing
# forever -- same review, same finding. A small constant is enough; nothing
# in this codebase's actual use cases needs more than a handful of
# concurrent monitoring schedules at once.
_MAX_CONCURRENT_SCHEDULES = 5


class WorkflowScheduler(QObject):
    """Registry of active recurring-workflow QTimers, keyed by preset name.
    Everything here is expected to run on the main Qt thread: start()/stop()
    are only ever called from registered tool functions, which the
    dispatcher (agent.py's _execute_tool) already guarantees run on the main
    thread -- the same assumption every other QGIS-facing module in this
    codebase makes, so no extra locking is done here."""

    workflow_tick_completed = pyqtSignal(str, str)  # preset_name, summary_text

    def __init__(self):
        if QGIS_AVAILABLE:
            super().__init__()
        self._timers = {}
        self._meta = {}

    def is_active(self, preset_name):
        return preset_name in self._timers

    def start(self, preset_name, interval_minutes, on_tick, max_runs=None):
        """on_tick(preset_name) is called on every timer fire, on the main
        thread. Starting a schedule for a preset_name that's already active
        replaces it rather than stacking a second timer."""
        # Argument validation runs before the QGIS-availability gate on
        # purpose -- both checks are pure Python (no Qt/QTimer needed), so
        # this keeps them unit-testable without a real QGIS environment.
        if interval_minutes < _MIN_INTERVAL_MINUTES:
            return {
                "error": f"interval_minutes must be at least {_MIN_INTERVAL_MINUTES} (got {interval_minutes}) "
                         "-- a shorter interval would hammer the QGIS UI thread with repeated geoprocessing."
            }
        if preset_name not in self._timers and len(self._timers) >= _MAX_CONCURRENT_SCHEDULES:
            return {
                "error": f"Already at the limit of {_MAX_CONCURRENT_SCHEDULES} concurrent schedules. "
                         "Stop one with stop_recurring_workflow first."
            }
        if not QGIS_AVAILABLE:
            return {"error": "QGIS not available"}
        self.stop(preset_name)

        timer = QTimer()
        timer.setInterval(int(interval_minutes * 60 * 1000))

        def _fire():
            meta = self._meta.get(preset_name)
            if meta is None:
                return
            meta["run_count"] += 1
            try:
                on_tick(preset_name)
            finally:
                if meta.get("max_runs") and meta["run_count"] >= meta["max_runs"]:
                    self.stop(preset_name)

        timer.timeout.connect(_fire)
        self._timers[preset_name] = timer
        self._meta[preset_name] = {"interval_minutes": interval_minutes, "max_runs": max_runs, "run_count": 0}
        timer.start()
        return {"success": True, "preset_name": preset_name, "interval_minutes": interval_minutes, "max_runs": max_runs}

    def stop(self, preset_name):
        timer = self._timers.pop(preset_name, None)
        self._meta.pop(preset_name, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
            return True
        return False

    def stop_all(self):
        """Called on plugin unload so no timer keeps firing against a
        dock widget that no longer exists."""
        for name in list(self._timers):
            self.stop(name)

    def list_active(self):
        return [{"preset_name": name, **meta} for name, meta in self._meta.items()]


_scheduler = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = WorkflowScheduler()
    return _scheduler
