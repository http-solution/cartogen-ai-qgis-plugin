"""run_processing_batch (PLAN-023 R11-2): one approved Processing algorithm over up to 20 layers, results grouped.

Each layer is one call of run_allowlisted_processing_algorithm, so every run gets exactly the checks a single run gets: the approved list, the parameter and expression screens, temporary
outputs, the geometry and layer-kind checks. What this tool adds: the request check (batch_ops.py, pure), a refusal of any algorithm that changes the user's own layer (a batch would change many
layers at once), a check that every named layer exists BEFORE the first run (so a typo costs nothing), a result layer per input named <layer>_<algorithm>, all of them gathered in one new
layer group, and an honest summary: a run that fails does not stop the others, the reply lists each failure with its reason, and Stop ends the batch and says how far it got.
The group name must be new (an existing group is never added to). Results are temporary layers, as for a single run. Written without a QGIS install; tests/test_batch_tool_live.py is its first
execution in CI."""
from . import batch_ops as bo
from ._processing_allowlist import MUTATES_INPUT_ALGORITHM_IDS
from .map_view_tools import _move_into, check_group_name
from .processing_allowlist_tools import _not_approved_error, run_allowlisted_processing_algorithm
from .registry import register_tool

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _prepare(algorithm_id, names, group_name):
    """(group name, error): the new group's name, or why the batch cannot start. Nothing has run at this point. Needs QGIS."""
    refusal = _not_approved_error(algorithm_id)
    if refusal:
        return None, refusal["error"]
    if algorithm_id in MUTATES_INPUT_ALGORITHM_IDS:
        return None, f"'{algorithm_id}' changes the layer it is given (a selection), which a batch may not do to many layers at once."
    project = QgsProject.instance()
    missing = [n for n in names if not project.mapLayersByName(n)]
    if missing:
        return None, f"Layer(s) not found: {', '.join(missing)}. Nothing was run."
    group, problem = check_group_name(group_name or f"{bo.short_name(algorithm_id)}_batch")
    if problem:
        return None, problem
    if project.layerTreeRoot().findGroup(group) is not None:
        return None, f"A layer group called '{group}' already exists; give a different group_name. Nothing was run."
    return group, None


@register_tool(
    "run_processing_batch",
    "Run ONE approved Processing algorithm over several layers (1 to 20), one run per layer, with the same settings for each, and put the results together in a new layer group. For example "
    "buffer 5 layers by 100 m, or compute slope for 8 rasters. `layers` are layer names; `parameters` are the settings shared by all runs (not the input and not an output); `input_parameter` "
    "names the algorithm's input (default INPUT). Each result layer is named <layer>_<algorithm> and is temporary. A layer that fails does not stop the others: the reply lists each failure and its "
    "reason. Algorithms that change your own layers (selections) are refused. The group name must be new. Stop ends the batch and the reply says how far it got.",
    {"type": "object", "properties": {
        "algorithm_id": {"type": "string", "description": "An approved algorithm id such as native:buffer."},
        "layers": {"type": "array", "items": {"type": "string"}, "description": "1 to 20 layer names, each once."},
        "parameters": {"type": "object", "description": "Settings shared by all runs, for example {\"DISTANCE\": 100}."},
        "input_parameter": {"type": "string", "description": "The algorithm's input parameter name (default INPUT)."},
        "group_name": {"type": "string", "description": "Name of the new layer group (default <algorithm>_batch); it must not exist yet."}},
     "required": ["algorithm_id", "layers"]},
    keywords=["batch process", "run it on all the layers", "run on each layer", "the same algorithm on several layers", "apply to each of these layers", "batch of layers", "process several layers",
              "buffer all these layers", "run the same tool on every layer", "to every layer in the group", "on every layer", "apply it to every layer", "for each layer"],
)
def run_processing_batch(algorithm_id, layers, parameters=None, input_parameter="INPUT", group_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = bo.check_request(algorithm_id, layers, parameters, input_parameter)
    if problem:
        return {"error": problem}
    names = [n.strip() for n in layers]
    group, problem = _prepare(algorithm_id, names, group_name)
    if problem:
        return {"error": problem, "nothing_was_run": True}
    short = bo.short_name(algorithm_id)
    rows, made = [], []
    for name in names:
        result = run_allowlisted_processing_algorithm(algorithm_id, {**(parameters or {}), input_parameter: name}, new_layer_name=f"{name}_{short}")
        ok = bool(result.get("success")) and bool(result.get("layer_name"))
        stopped = bool(result.get("cancelled"))
        rows.append((name, ok, result.get("layer_name") if ok else str(result.get("error") or "the run produced no layer"), stopped))
        if ok:
            made.append((name, [result["layer_name"], *[e["layer_name"] for e in result.get("additional_outputs", []) if isinstance(e, dict) and e.get("layer_name")]]))
        if stopped:
            break
    summary = bo.summarise(rows)
    out = {"algorithm": algorithm_id, "requested": len(names), "ran": summary["ran"], "succeeded": summary["succeeded"], "failed": summary["failed"], "partial": summary["partial"],
           "success": summary["succeeded"] > 0, "temporary": True}
    if summary["stopped_after"] is not None:
        out["stopped"] = f"Stopped during layer {summary['stopped_after'] + 1} of {len(names)}; the layers after it were not run."
    if made:
        root = QgsProject.instance().layerTreeRoot()
        target = root.addGroup(group)
        moved = _move_into(root, target, [layer for _input, produced in made for layer in produced])
        out["group"] = group
        out["results"] = [{"input": name, "layers": produced} for name, produced in made]
        out["layers_in_group"] = len(moved)
    else:
        out["error"] = "No run produced a layer, so no group was made. " + (out["failed"][0]["error"] if out["failed"] else "")
    out["note"] = "The result layers are temporary: they are not saved with the project until you export them. Your own layers were not changed."
    return out
