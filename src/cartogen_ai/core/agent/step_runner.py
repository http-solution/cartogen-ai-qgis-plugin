# -*- coding: utf-8 -*-
"""Validation, reference resolution and summaries for run_steps: several tool calls in ONE model round trip.

Why (2026-10-09 cost plan, step 6): every model call resends the system prompt, the tool schemas and the history, so a workflow of N
dependent tool calls costs N full-size requests even when the model already knows every argument of every step (it chose the output
names itself). run_steps lets the model send the whole ordered chain once. The plugin validates it BEFORE running anything, runs the
steps one at a time through the normal tool path (so egress gates, confirmations, undo snapshots and the loop guard all still apply),
and stops at the first error or at the first call waiting for the user's Confirm, reporting exactly what completed.

Deliberately narrow: whole-string references only ("$2.layer_name" = field `layer_name` of step 2's result, "$prev.x" = the previous
step), at most MAX_STEPS steps, no nested run_steps, no deleting tools. Whether a real model uses it well is NOT measured yet.
Pure: no QGIS, no Qt."""
import json
import re

MAX_STEPS = 8
RESULT_CHARS = 1500            # per intermediate step in the summary the model reads back
LAST_RESULT_CHARS = 4000
NOT_BATCHABLE = frozenset({"run_steps", "find_tools", "create_plan", "update_task", "set_task_preview"})
_REF = re.compile(r"^\$(\d+|prev)\.([A-Za-z_][A-Za-z0-9_]*)$")


def parse_steps(arguments):
    """The steps list from the raw tool arguments, or (None, error)."""
    try:
        data = arguments if isinstance(arguments, dict) else json.loads(arguments or "{}")
    except (TypeError, ValueError):
        return None, "run_steps arguments must be valid JSON."
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, list) or not steps:
        return None, "run_steps needs a non-empty `steps` list of {tool, arguments}."
    return steps, None


def _refs_in(value):
    if isinstance(value, str):
        m = _REF.match(value)
        if m:
            yield m.group(1), m.group(2)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _refs_in(v)
    elif isinstance(value, list):
        for v in value:
            yield from _refs_in(v)


def validate_steps(steps, schemas, operation_of):
    """Error text, or None when every step may run. `schemas` maps offered tool name -> its parameters schema; `operation_of(name)`
    gives READ/CREATE/MODIFY/DELETE/PUBLISH. Checks happen before anything runs, so a bad plan costs nothing."""
    if len(steps) > MAX_STEPS:
        return f"At most {MAX_STEPS} steps per run_steps call (got {len(steps)}); send the rest in a second call."
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict) or not isinstance(step.get("tool"), str):
            return f"Step {i} must be an object with a `tool` name."
        name = step["tool"]
        args = step.get("arguments", {})
        if not isinstance(args, dict):
            return f"Step {i} ({name}): `arguments` must be an object."
        if name in NOT_BATCHABLE:
            return f"Step {i}: `{name}` cannot be used inside run_steps."
        if name not in schemas:
            return f"Step {i}: `{name}` is not one of the tools offered for this request (use find_tools to look it up)."
        if operation_of(name) == "DELETE":
            return f"Step {i}: `{name}` deletes or replaces project state and must be called on its own so the user can confirm it."
        for ref_step, field in _refs_in(args):
            target = i - 1 if ref_step == "prev" else int(ref_step)
            if not 1 <= target < i:
                return f"Step {i} ({name}): reference ${ref_step}.{field} must point to an EARLIER step."
        required = (schemas[name] or {}).get("required") or []
        missing = [r for r in required if r not in args]
        if missing:
            return f"Step {i} ({name}) is missing required argument(s): {', '.join(missing)}."
    return None


def resolve_arguments(args, results):
    """(resolved arguments, error). `results` is the list of earlier step results, index 0 = step 1."""
    def walk(value):
        if isinstance(value, str):
            m = _REF.match(value)
            if not m:
                return value
            target = len(results) - 1 if m.group(1) == "prev" else int(m.group(1)) - 1
            result = results[target] if 0 <= target < len(results) else None
            if not isinstance(result, dict) or m.group(2) not in result:
                raise KeyError(f"{value} (that step's result has no field '{m.group(2)}')")
            return result[m.group(2)]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value
    try:
        return walk(args), None
    except KeyError as e:
        return None, f"Could not resolve reference {e.args[0]}"


def step_summary(index, tool, result, ok, limit):
    text = json.dumps(result, default=str)
    if len(text) > limit:
        text = text[:limit] + "...(truncated)"
    return {"step": index, "tool": tool, "ok": ok, "result": text}


def final_result(total, summaries, stopped=None, status=None):
    """The single result the model reads for the whole batch."""
    done = sum(1 for s in summaries if s["ok"])
    out = {"success": stopped is None, "completed": done, "total": total, "steps": summaries}
    if stopped:
        out["stopped_at_step"] = len(summaries)
        out["stopped_because"] = stopped
        if status:
            out["status"] = status
        else:
            out["error"] = stopped
        if len(summaries) < total:
            first = len(summaries) if status else len(summaries) + 1       # a step waiting for Confirm did not run either
            out["not_run"] = f"Steps {first}-{total} were NOT run."
    return out


# --- preflight: check the chain against the real project BEFORE the first step runs --------------------------------------------
VECTOR_PARAMS = frozenset({"layer_name", "input_layer", "mask_layer", "overlay_layer", "zone_layer", "line_layer", "facility_layer",
                           "road_network_layer", "area_layer", "vector_layer", "extent_layer"})
RASTER_PARAMS = frozenset({"raster_layer", "dem_layer", "population_raster_layer"})
# Tools whose `layer_name` names a layer that must already exist as a vector layer; for the rest `layer_name` is an output name or an
# extent source, so only the unambiguous parameter names above are checked and only against steps that run before anything is created.
GEOGRAPHIC_SENSITIVE = frozenset({"buffer_analysis"})
# `layer_name` is the INPUT layer for these tools but a new layer's name for others (add_point_layer) and any layer kind for others
# still; it is only checked for tools known to take an existing vector layer there.
INPUT_LAYER_NAME_TOOLS = frozenset({"buffer_analysis", "reproject_layer", "dissolve_layer", "calculate_area", "calculate_length",
                                    "apply_graduated_style", "apply_categorized_style", "export_layer", "fetch_dem",
                                    "select_by_attribute", "field_statistics", "check_pcode_uniqueness", "check_pcode_hierarchy"})


def _literal_layer_args(step):
    for key, value in (step.get("arguments") or {}).items():
        if isinstance(value, str) and not _REF.match(value) and not (value.startswith("<") and value.endswith(">")):
            if key == "layer_name" and step.get("tool") not in INPUT_LAYER_NAME_TOOLS:
                continue
            if key in VECTOR_PARAMS:
                yield key, value, "vector"
            elif key in RASTER_PARAMS:
                yield key, value, "raster"


def preflight(steps, facts, operation_of):
    """Error text or None. `facts` = {layer name: {"kind": "vector"|"raster", "geographic": bool}} from the open project.

    Only what can be known BEFORE running is checked, and only where it is sound: a literal layer name must exist and be the right kind
    while no earlier step has created anything (afterwards a name may legitimately be one a previous step is about to create);
    buffer_analysis on a geographic-CRS layer applies the distance in degrees and is refused with the fix. A bad chain is refused with
    no step run, which costs one model call instead of a half-run chain."""
    created = False
    available = sorted(facts)[:15]
    for i, step in enumerate(steps, 1):
        tool = step["tool"]
        for key, name, kind in _literal_layer_args(step):
            if created:
                continue
            info = facts.get(name)
            if info is None:
                return (f"Step {i} ({tool}): layer '{name}' ({key}) is not in the project. Layers present: "
                        f"{', '.join(available) if available else '(none)'}. Use one of these names exactly.")
            if key != "layer_name" and info.get("kind") != kind:
                return f"Step {i} ({tool}): '{name}' is a {info.get('kind')} layer but `{key}` needs a {kind} layer."
            if tool in GEOGRAPHIC_SENSITIVE and key == "layer_name" and info.get("geographic"):
                return (f"Step {i} ({tool}): '{name}' is in a geographic CRS, so the distance would be applied in degrees. Add a "
                        "reproject_layer step to a projected CRS first and buffer its result.")
        if operation_of(tool) in ("CREATE",):
            created = True
    return None
