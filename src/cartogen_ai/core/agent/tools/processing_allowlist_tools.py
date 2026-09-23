# -*- coding: utf-8 -*-
"""
run_allowlisted_processing_algorithm -- a Tier 2 slice of the tiered
allow-list model point 19's "larger question" describes
(docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md), sitting between
this codebase's ~150 declarative tools (Tier 1) and execute_pyqgis_script's
denylist sandbox (Tier 4, "LAST RESORT ONLY" per point 1's routing fix).
Runs exactly one Processing algorithm from a hard-coded allow-list
(_processing_allowlist.py, derived from this codebase's own existing
processing.run() call sites) with a caller-supplied flat params dict --
never executes Python code at all, so it has none of execute_pyqgis_script's
attack surface (no eval/exec, no denylist to bypass) while covering the
common "I need one Processing algorithm not wrapped by a dedicated tool"
case that would otherwise reach for raw script execution.

Deliberately does NOT touch or loosen execute_pyqgis_script's existing
sandbox in any way -- this is a new, narrower, safer path offered as a
preference, not a replacement.
"""

from .registry import register_tool
from ._processing_allowlist import ALLOWED_ALGORITHM_IDS

try:
    from qgis.core import QgsProject
    import processing
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# Any params key matching one of these (case-insensitive) is forced to an
# in-memory/temporary sink regardless of what value is supplied -- this
# tool's whole point is a bounded, in-memory Processing call, not a way to
# write to an arbitrary file path the way a dedicated, audited export tool
# (export_layer, write_provenance_sidecar) already does deliberately and
# visibly. Matches the exact "OUTPUT": "memory:" convention every existing
# processing.run() call in this codebase already uses.
_OUTPUT_KEY_SUFFIXES = ("output", "output_lines")
_SAFE_OUTPUT_VALUE = "memory:"


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _resolve_params(params):
    """Any string value that matches a layer currently loaded in the
    project is resolved to that QgsMapLayer object -- the same shape every
    existing processing.run() call in this codebase already uses
    ("INPUT": a_real_layer_object, not a name string). A string that
    doesn't match a loaded layer is passed through literally (e.g. a
    genuine text param, or "memory:"/"TEMPORARY_OUTPUT" for an output
    key). Non-string values (numbers, bools, lists) pass through
    unchanged -- this tool never accepts nested objects or code, only
    JSON-primitive params, so there's nothing here to execute.

    Confirmed live against QGIS 4.2.2: unlike this codebase's other
    processing.run() call sites, which always build their own OUTPUT key
    explicitly, a caller here may omit it entirely -- and Processing does
    NOT default it, it fails outright ("no value specified for parameter
    OUTPUT"). If the caller's params has neither OUTPUT nor OUTPUT_LINES
    at all, one is added ("OUTPUT": "memory:") -- every allow-listed
    algorithm's real call site (see _processing_allowlist.py) uses one of
    these two keys for its sink, so this default covers the whole list."""
    resolved = {}
    has_output_key = False
    for key, value in params.items():
        key_lower = key.lower()
        if any(key_lower == suffix or key_lower.endswith("_" + suffix) for suffix in _OUTPUT_KEY_SUFFIXES):
            resolved[key] = _SAFE_OUTPUT_VALUE
            has_output_key = True
            continue
        if isinstance(value, str):
            layer = _find_layer_by_name(value)
            resolved[key] = layer if layer is not None else value
        else:
            resolved[key] = value
    if not has_output_key:
        resolved["OUTPUT"] = _SAFE_OUTPUT_VALUE
    return resolved


@register_tool(
    "run_allowlisted_processing_algorithm",
    "Runs one QGIS Processing algorithm from a fixed, pre-approved list -- prefer this over "
    "execute_pyqgis_script when the task is achievable via a single Processing algorithm that "
    "isn't already covered by a dedicated tool. Safer than execute_pyqgis_script: this never runs "
    "Python code at all, only calls the named algorithm with the given parameters, so there is no "
    "code-execution surface to sandbox. Only algorithms already used elsewhere in this codebase "
    "are allowed -- an unlisted algorithm id is rejected outright, not run. Output is always kept "
    "in-memory as a new project layer (auto-named), never written to a file path -- use a "
    "dedicated export tool (export_layer, export_to_csv) afterward if a file is actually needed. "
    "Don't specify an OUTPUT/OUTPUT_LINES parameter yourself -- it's set automatically and any "
    "value you give is ignored. Any string parameter value matching a currently-loaded layer's "
    "name is automatically resolved to that layer; every other value is passed through as-is.",
    {
        "type": "object",
        "properties": {
            "alg_id": {
                "type": "string",
                "description": f"Processing algorithm id, e.g. 'native:buffer'. Must be one of: {sorted(ALLOWED_ALGORITHM_IDS)}",
            },
            "params": {
                "type": "object",
                "description": "Flat dict of algorithm parameters, e.g. {\"INPUT\": \"my_layer\", \"DISTANCE\": 500}. String values matching a loaded layer's name are resolved to that layer automatically.",
            },
            "new_layer_name": {
                "type": "string",
                "description": "Name to give the algorithm's output layer once added to the project. Defaults to '<alg_id>_output' if omitted -- and an omitted name is treated as a signal that this output is an internal/scratch step (e.g. a reprojection before a buffer), so it's added to the project hidden (unchecked in the layer tree) rather than cluttering the visible map. Give this an explicit name whenever the output IS the deliverable you want the user to see.",
            },
        },
        "required": ["alg_id", "params"],
    },
)
def run_allowlisted_processing_algorithm(alg_id, params, new_layer_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if alg_id not in ALLOWED_ALGORITHM_IDS:
        return {
            "error": f"'{alg_id}' is not on the allowed algorithm list. Allowed: {sorted(ALLOWED_ALGORITHM_IDS)}. "
                     "Use execute_pyqgis_script as a last resort if genuinely nothing else covers this."
        }
    if not isinstance(params, dict):
        return {"error": "params must be an object/dict of algorithm parameters."}

    try:
        resolved_params = _resolve_params(params)
        output = processing.run(alg_id, resolved_params)
    except Exception as e:
        return {"error": f"'{alg_id}' failed: {e}"}

    new_layer = output.get("OUTPUT") if isinstance(output, dict) else None
    if new_layer is None or not hasattr(new_layer, "setName"):
        return {"success": True, "alg_id": alg_id, "message": f"'{alg_id}' ran successfully with no new layer output."}

    # IMPLEMENTATION_TRACKER.md §1.9, option 1 (narrow fix, 2026-09-24): a real turn calling this
    # tool 4x to reproject/buffer/intersect its way to one answer left 3 purely-internal scratch
    # layers fully visible and unaccounted-for in the model's own set_layer_order call, cluttering
    # the map. Can't default to always-hidden -- plenty of allowed algorithms (native:buffer for a
    # requested buffer map) ARE the deliverable, and output_router.satisfied()'s `layer` branch
    # relies on seeing them rendered. Betting on an implicit convention instead: if the caller
    # bothered to name the output, treat that as "this is a result I mean to keep visible"; if it
    # fell back to the auto-generated "<alg_id>_output" name, treat it as scratch and hide its
    # checkbox (still added to the project/legend -- inspectable, exportable, just not cluttering
    # the visible map by default). Not a schema change, so no prompt-rule update needed; if this
    # naming-convention bet doesn't hold up in practice, the tracker entry lists the costlier
    # explicit `visible` parameter as the real fix.
    caller_named_it = new_layer_name is not None
    layer_name = new_layer_name or f"{alg_id.split(':')[-1]}_output"
    new_layer.setName(layer_name)
    project = QgsProject.instance()
    project.addMapLayer(new_layer)
    if not caller_named_it:
        layer_node = project.layerTreeRoot().findLayer(new_layer.id())
        if layer_node is not None:
            layer_node.setItemVisibilityChecked(False)

    result = {"success": True, "alg_id": alg_id, "layer_name": layer_name, "visible": caller_named_it}
    if hasattr(new_layer, "featureCount"):
        count = new_layer.featureCount()
        result["feature_count"] = count
        if count == 0:
            result["warning"] = "The output layer has 0 features -- check the inputs before treating this as a real empty result."
    return result
