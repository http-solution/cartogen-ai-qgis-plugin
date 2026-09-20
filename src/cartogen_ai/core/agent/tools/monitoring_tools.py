# -*- coding: utf-8 -*-
"""
Recurring monitoring workflows for Cartogen AI.

Session-scoped scheduling only (see agent/scheduler.py) -- re-runs a saved
sequence of already-registered analysis tools at an interval for as long as
QGIS stays open, and diffs each run's per-unit results against the previous
run so a change ("3 units moved into severity class 5 since last check") can
be surfaced without an extra API call every tick. Closes the "scheduled/
recurring monitoring" gap flagged in docs/archive/HUMANITARIAN_GIS_FEATURE_REVIEW.md
and docs/archive/CARTOGEN_AI_PRD.md 5.1/5.3.
"""

import datetime
import json
from .registry import register_tool, TOOL_REGISTRY
from ....infrastructure.settings_keys import (
    SETTINGS_WORKFLOW_PREFIX,
    SETTINGS_WORKFLOW_RUNS_PREFIX,
)

try:
    from qgis.core import QgsSettings
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# An unattended recurring run must never be able to silently repeat a destructive/
# geometry-editing operation against USER-authored data. Extend this set deliberately, not by
# default, when a new tool is added -- and only for one of two categories:
#
# 1. Read-only analysis tools (the 7 below) -- never write anything, and (relevant to PERF-001
#    below) never do network I/O either, so running one synchronously on the main thread (the
#    same way every other single-tool dispatch in this codebase already works) is bounded by
#    ordinary local computation time, not an HTTP round-trip.
# 2. Idempotent external-data-refresh tools -- would DO write, but only ever REPLACE the
#    features of their own auto-named, auto-managed layer with the latest fetch from a fixed
#    external source, so that part is safe. PERF-001 (2026-09-13 audit): fetch_nasa_active_fires/
#    fetch_nasa_eonet_events/fetch_gdacs_disaster_alerts were allowed here, but
#    run_monitoring_workflow calls each step's plain combined function directly -- unlike a
#    normal single call to one of these tools (dispatched through agent_orchestrator.py's TWO_PHASE_TOOLS,
#    which runs the network fetch off the main thread), a scheduled/manual WORKFLOW run executes
#    the combined network+QGIS function synchronously on the main Qt thread (scheduler.py's
#    QTimer fires _fire() there, and run_monitoring_workflow is called directly from it) --
#    repeatedly, every tick, for as long as a schedule runs. That freezes the whole QGIS GUI for
#    each fetch's HTTP round-trip. Deliberately excluded here until run_monitoring_workflow (or
#    the scheduler tick) is reworked to dispatch a network step's own *_network_phase function
#    off-thread first, mirroring agent_orchestrator.py's _execute_two_phase_tool -- see the register for why
#    that's a real design decision, not a same-session mechanical fix. Manually calling one of
#    these 3 tools (not via a workflow) is unaffected -- that path already dispatches correctly.
_ALLOWED_WORKFLOW_TOOLS = {
    "calculate_severity_index",
    "calculate_presence_gap",
    "calculate_population_in_need",
    "forecast_trend",
    "field_statistics",
    "population_access_gap",
    "estimate_population_exposure",
}

_WORKFLOW_KEY_PREFIX = SETTINGS_WORKFLOW_PREFIX
_RUN_KEY_PREFIX = SETTINGS_WORKFLOW_RUNS_PREFIX


def _load_steps(preset_name):
    """Loads and validates a saved workflow preset (see save_workflow_preset)
    against the shape a monitoring workflow needs. Returns (steps, None) on
    success or (None, error_message) -- never raises, so callers can return
    the error directly as a tool result."""
    settings = QgsSettings()
    raw = settings.value(_WORKFLOW_KEY_PREFIX + preset_name, "")
    if not raw:
        return None, (
            f"Workflow preset '{preset_name}' not found. Save one first with save_workflow_preset, e.g. "
            f'save_workflow_preset(preset_name="{preset_name}", workflow_json=\'{{"steps": [{{"tool": '
            '"calculate_severity_index", "args": {...}}, ...]}\') -- using concrete layer/field/file '
            "names already loaded in the project, never placeholders."
        )
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as e:
        return None, f"Workflow preset '{preset_name}' is not valid JSON: {e}"
    steps = parsed.get("steps") if isinstance(parsed, dict) else None
    if not isinstance(steps, list) or not steps:
        return None, (
            f"Workflow preset '{preset_name}' has no usable 'steps' list. Expected "
            '\'{"steps": [{"tool": "calculate_severity_index", "args": {...}}, ...]}\'.'
        )
    unknown_tools = sorted({s.get("tool") for s in steps if s.get("tool") not in _ALLOWED_WORKFLOW_TOOLS})
    if unknown_tools:
        return None, (
            f"Step(s) reference tool(s) not allowed in a recurring workflow: {unknown_tools}. "
            f"Allowed (read-only analysis tools only): {sorted(_ALLOWED_WORKFLOW_TOOLS)}."
        )
    return steps, None


def _find_unit_list(result):
    """Finds the first list-of-dicts value (at any top-level key) whose items
    carry a "unit" key -- the convention every severity/presence/population
    analysis tool in this codebase already follows. Returns None when no
    such list exists, since not every allowed tool's output fits this shape
    (e.g. forecast_trend's ungrouped result)."""
    if not isinstance(result, dict):
        return None
    for value in result.values():
        if isinstance(value, list) and value and all(isinstance(item, dict) and "unit" in item for item in value):
            return value
    return None


def _diff_unit_results(old_result, new_result):
    """Best-effort per-unit change summary between two runs of the same
    step. Returns None (not an error) when either side has no per-unit
    result list to compare."""
    old_list, new_list = _find_unit_list(old_result), _find_unit_list(new_result)
    if old_list is None or new_list is None:
        return None

    old_by_unit = {item["unit"]: item for item in old_list}
    new_by_unit = {item["unit"]: item for item in new_list}

    appeared = sorted(set(new_by_unit) - set(old_by_unit))
    disappeared = sorted(set(old_by_unit) - set(new_by_unit))
    changed = []
    for unit in sorted(set(old_by_unit) & set(new_by_unit)):
        old_item, new_item = old_by_unit[unit], new_by_unit[unit]
        field_changes = {}
        for field, new_v in new_item.items():
            if field == "unit":
                continue
            old_v = old_item.get(field)
            if isinstance(new_v, (int, float, str, bool)) and old_v != new_v:
                field_changes[field] = {"before": old_v, "after": new_v}
        if field_changes:
            changed.append({"unit": unit, "changes": field_changes})

    return {"units_appeared": appeared, "units_disappeared": disappeared, "units_changed": changed}


def _summarize_diffs(preset_name, result):
    """Short human-readable summary of a run's diffs_since_last_run, used
    for the scheduled-tick chat notification so it doesn't need an extra
    API call every tick -- ask a follow-up question if a full explanation
    is wanted."""
    if result.get("previous_run_at") is None:
        return f"Scheduled check '{preset_name}' ran for the first time -- nothing to compare against yet."
    diffs = result.get("diffs_since_last_run") or []
    total_changed = sum(len(d.get("units_changed", [])) for d in diffs)
    total_appeared = sum(len(d.get("units_appeared", [])) for d in diffs)
    total_disappeared = sum(len(d.get("units_disappeared", [])) for d in diffs)
    if not (total_changed or total_appeared or total_disappeared):
        return f"Scheduled check '{preset_name}' ran -- no changes since the last run."
    parts = []
    if total_changed:
        parts.append(f"{total_changed} unit(s) changed")
    if total_appeared:
        parts.append(f"{total_appeared} new unit(s)")
    if total_disappeared:
        parts.append(f"{total_disappeared} unit(s) dropped out")
    return f"Scheduled check '{preset_name}' ran -- {', '.join(parts)} since the last run. Ask me to explain what changed for details."


@register_tool(
    "run_monitoring_workflow",
    "Re-run a saved sequence of analysis tools (a 'monitoring workflow', see save_workflow_preset) in "
    "one shot and diff each step's per-unit results against the last time this preset was run -- e.g. "
    "re-running calculate_severity_index weekly and seeing which admin units moved into a worse "
    "severity class. Only read-only analysis tools are allowed as steps (calculate_severity_index, "
    "calculate_presence_gap, calculate_population_in_need, forecast_trend, field_statistics, "
    "population_access_gap, estimate_population_exposure) -- never geometry edits, file writes, or "
    "network-fetch tools, so an unattended recurring run can't silently repeat a destructive action "
    "or freeze the QGIS interface on a slow network call. For live hazard data (fire detections, "
    "GDACS alerts), call fetch_nasa_active_fires/fetch_nasa_eonet_events/fetch_gdacs_disaster_alerts "
    "directly instead -- they are not usable as a workflow step. The preset must be saved "
    'first via save_workflow_preset as \'{"steps": [{"tool": "calculate_severity_index", "args": '
    '{...}}, ...]}\'. The first run has nothing to compare against (previous_run_at is null); later '
    "runs report units_appeared/units_disappeared/units_changed per step, wherever that step's result "
    "contains a list of per-unit entries.",
    {
        "type": "object",
        "properties": {
            "preset_name": {"type": "string", "description": "Name of a workflow preset already saved via save_workflow_preset."},
        },
        "required": ["preset_name"],
    },
)
def run_monitoring_workflow(preset_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    steps, error = _load_steps(preset_name)
    if error:
        return {"error": error}

    settings = QgsSettings()
    run_key = _RUN_KEY_PREFIX + preset_name
    previous_raw = settings.value(run_key, "")
    previous = json.loads(previous_raw) if previous_raw else None

    step_results = []
    for step in steps:
        tool_name = step.get("tool")
        args = step.get("args") or {}
        func = TOOL_REGISTRY.get(tool_name)
        if func is None:
            step_results.append({"tool": tool_name, "args": args, "result": {"error": f"Unknown tool: {tool_name}"}})
            continue
        try:
            result = func(**args)
        except Exception as e:
            result = {"error": f"Step failed: {e}"}
        step_results.append({"tool": tool_name, "args": args, "result": result})

    ran_at = datetime.datetime.now().isoformat(timespec="seconds")

    diffs = []
    if previous is not None:
        prev_by_key = {
            (s["tool"], json.dumps(s["args"], sort_keys=True)): s["result"]
            for s in previous.get("step_results", [])
        }
        for s in step_results:
            key = (s["tool"], json.dumps(s["args"], sort_keys=True))
            prev_result = prev_by_key.get(key)
            if prev_result is not None:
                diff = _diff_unit_results(prev_result, s["result"])
                if diff is not None:
                    diffs.append({"tool": s["tool"], "args": s["args"], **diff})

    settings.setValue(run_key, json.dumps({"ran_at": ran_at, "step_results": step_results}))

    return {
        "success": True,
        "preset_name": preset_name,
        "ran_at": ran_at,
        "previous_run_at": previous.get("ran_at") if previous else None,
        "step_results": step_results,
        "diffs_since_last_run": diffs,
    }


@register_tool(
    "schedule_recurring_workflow",
    "Start re-running a saved monitoring workflow (see run_monitoring_workflow) automatically every "
    "interval_minutes, for as long as QGIS stays open with this plugin loaded. This is session-scoped, "
    "NOT a headless/background-service schedule -- it stops when QGIS closes or the plugin is "
    "unloaded, nothing runs while QGIS is closed. Each tick posts a short change summary into chat "
    "('no changes since the last run', or a count of changed/new/dropped units) without an extra API "
    "call -- ask a follow-up question if you want the model to explain what changed. Starting a "
    "schedule for a preset_name that's already scheduled replaces the old schedule. Use "
    "stop_recurring_workflow to cancel, list_scheduled_workflows to see what's active. "
    "interval_minutes must be at least 1 (a shorter interval would hammer the QGIS UI thread with "
    "repeated geoprocessing), and at most 5 schedules can be active at once -- stop one first if "
    "already at that limit.",
    {
        "type": "object",
        "properties": {
            "preset_name": {"type": "string", "description": "Name of a workflow preset already saved via save_workflow_preset."},
            "interval_minutes": {"type": "number", "description": "Minutes between runs. Must be at least 1."},
            "max_runs": {"type": "integer", "description": "Optional: stop automatically after this many runs. Otherwise runs until QGIS closes or stop_recurring_workflow is called."},
        },
        "required": ["preset_name", "interval_minutes"],
    },
)
def schedule_recurring_workflow(preset_name, interval_minutes, max_runs=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    steps, error = _load_steps(preset_name)
    if error:
        return {"error": error}

    from ..scheduler import get_scheduler
    scheduler = get_scheduler()

    def _tick(name):
        result = run_monitoring_workflow(name)
        summary = f"Scheduled check '{name}' failed: {result['error']}" if "error" in result else _summarize_diffs(name, result)
        scheduler.workflow_tick_completed.emit(name, summary)

    return scheduler.start(preset_name, interval_minutes, _tick, max_runs=max_runs)


@register_tool(
    "stop_recurring_workflow",
    "Cancel a recurring workflow schedule started with schedule_recurring_workflow.",
    {
        "type": "object",
        "properties": {"preset_name": {"type": "string"}},
        "required": ["preset_name"],
    },
)
def stop_recurring_workflow(preset_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from ..scheduler import get_scheduler
    if get_scheduler().stop(preset_name):
        return {"success": True, "preset_name": preset_name, "stopped": True}
    return {"error": f"No active schedule found for preset '{preset_name}'."}


@register_tool(
    "list_scheduled_workflows",
    "List currently active recurring workflow schedules (session-scoped -- cleared when QGIS closes).",
    {"type": "object", "properties": {}, "required": []},
)
def list_scheduled_workflows():
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from ..scheduler import get_scheduler
    return {"success": True, "active_schedules": get_scheduler().list_active()}
