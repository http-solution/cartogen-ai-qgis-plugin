"""Opening a shared workflow file (PLAN-048 stage 3): everything that is not a dialog. Pure: no QGIS, no Qt.

workflow_file.validate decides whether a file may be shown at all. This module takes a VALID document and the person's choices (which of their layers
each role stands for, which step to start at) and produces what the runner needs, or says why it cannot:
  * every role used by a step that will run must be mapped to an existing layer; the layer must be the right KIND (vector or raster) and should have
    the right geometry and fields (a mismatch of geometry or fields is a warning, because the person may know better; a wrong kind is a refusal);
  * `@role` becomes the layer's name, only as a whole string, exactly the places the file put it;
  * starting at step N > 1 renumbers `$k.field` references, and refuses one that points before the start (that step's result is not available);
  * the run result is turned into a plain message for the chat.
Nothing here runs a tool."""
import json

from . import step_runner, workflow_file


def used_roles(steps):
    """The role names referenced by `steps`' arguments, in order of first use. Pure."""
    seen = []
    for step in steps:
        for match in workflow_file._role_refs(step.get("arguments", {})):
            if match.group(1) not in seen:
                seen.append(match.group(1))
    return seen


def _substitute(value, mapping, start_at, problems, where, depth=0):
    if depth > workflow_file.MAX_DEPTH:
        return value
    if isinstance(value, str):
        ref = step_runner._REF.match(value)
        if ref:
            if ref.group(1) == "prev":
                return value
            k = int(ref.group(1))
            if k < start_at:
                problems.append(f"{where}: refers to step {k}, which is before step {start_at} where you chose to start; its result is not available.")
                return value
            return f"${k - start_at + 1}.{ref.group(2)}"
        role = workflow_file._ROLE_REF.match(value)
        if role:
            return mapping.get(role.group(1), value)
        return value
    if isinstance(value, dict):
        return {k: _substitute(v, mapping, start_at, problems, where, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, mapping, start_at, problems, where, depth + 1) for v in value]
    return value


def apply_mapping(document, mapping, start_at=1, available=None):
    """(steps for the runner, problems). `mapping` is {role: project layer name}; `available` (a set of layer names) is optional. Pure."""
    problems = []
    steps = document.get("steps", [])
    if not isinstance(start_at, int) or isinstance(start_at, bool) or not 1 <= start_at <= len(steps):
        return [], [f"Start at a step from 1 to {len(steps)}."]
    chosen = steps[start_at - 1:]
    for role in used_roles(chosen):
        layer = mapping.get(role)
        if not isinstance(layer, str) or not layer.strip():
            problems.append(f"Choose a layer for the role '{role}'.")
        elif available is not None and layer not in available:
            problems.append(f"The layer '{layer}' chosen for '{role}' is not in the project.")
    if problems:
        return [], problems
    out = []
    for offset, step in enumerate(chosen):
        where = f"Step {start_at + offset} ({step['tool']})"
        out.append({"tool": step["tool"], "arguments": _substitute(step["arguments"], mapping, start_at, problems, where)})
    return ([] if problems else out), problems


def compatibility(document, mapping, layer_info):
    """(problems, warnings) about whether the chosen layers fit their roles. `layer_info(name)` returns {"kind", "geometry", "fields"} or None. Pure."""
    problems, warnings = [], []
    for role, spec in document.get("roles", {}).items():
        layer = mapping.get(role)
        if not layer:
            continue
        info = layer_info(layer) or {}
        if not info:
            problems.append(f"The layer '{layer}' chosen for '{role}' is not in the project.")
            continue
        if spec.get("kind") and info.get("kind") and spec["kind"] != info["kind"]:
            problems.append(f"'{layer}' is a {info['kind']} layer but the role '{role}' needs a {spec['kind']} layer.")
            continue
        if spec.get("geometry") and info.get("geometry") and spec["geometry"] != info["geometry"]:
            warnings.append(f"'{layer}' has {info['geometry']} geometry; the role '{role}' was made for {spec['geometry']}.")
        missing = [f for f in spec.get("fields", []) if f not in (info.get("fields") or [])]
        if missing:
            warnings.append(f"'{layer}' has no field(s) {', '.join(missing[:6])} that the role '{role}' expects.")
    return problems, warnings


def step_rows(document, mapping, operation_of):
    """Rows for the dialog's step table: number, tool, kind of change, arguments with each @role shown as the chosen layer (or the role while
    unchosen), and the author's note. Pure."""
    rows = []
    for n, step in enumerate(document.get("steps", []), 1):
        shown = _substitute(step["arguments"], {role: layer for role, layer in mapping.items() if layer}, 1, [], "")
        rows.append({"n": n, "tool": step["tool"], "operation": operation_of(step["tool"]), "note": step.get("note", ""),
                     "arguments": json.dumps(shown, ensure_ascii=False, sort_keys=True)})
    return rows


def result_text(document, result, start_at=1):
    """The chat message for a finished (or stopped) run. `result` is what CartogenAi.run_workflow_steps returned. Pure."""
    name = document.get("name", "workflow")
    if not isinstance(result, dict):
        return f"The workflow '{name}' did not return a result."
    if result.get("error") and "completed" in result and "stopped_at_step" not in result and "total" not in result:
        return f"The workflow '{name}' was not started: {result['error']}"
    total = result.get("total", 0)
    offset = start_at - 1
    if result.get("success"):
        return (f"The workflow '{name}' finished: all {total} step(s) ran" + (f" (steps {start_at} to {start_at + total - 1} of the file)" if offset else "")
                + ". The steps came from a file; read each result before relying on it.")
    stopped = result.get("stopped_at_step", 0) + offset
    because = result.get("stopped_because", "stopped")
    lines = [f"The workflow '{name}' stopped at step {stopped} of {len(document.get('steps', []))}: {because}"]
    if result.get("completed"):
        lines.append(f"{result['completed']} step(s) ran before that.")
    if result.get("not_run"):
        lines.append(result["not_run"].replace("Steps ", "Steps (counted from where this run began) "))
    if result.get("status") == "PREVIEW_REQUIRED":
        lines.append(f"Confirm or cancel the card above. Confirming runs step {stopped} only; to carry on, open the file again and start at step {stopped + 1}.")
    return "\n\n".join(lines)
