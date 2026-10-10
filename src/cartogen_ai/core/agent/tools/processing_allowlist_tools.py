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
from . import _background_processing as _bg
from ._processing_allowlist import (ALLOWED_ALGORITHM_IDS, MUTATES_INPUT_ALGORITHM_IDS, RASTER_OUTPUT_ALGORITHM_IDS,
                                    parameter_violation)

try:
    from qgis.core import QgsApplication, QgsProcessingContext, QgsProject, QgsRasterLayer
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
_SAFE_RASTER_OUTPUT_VALUE = "TEMPORARY_OUTPUT"   # a temporary file: rasters cannot go to "memory:"


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def unknown_parameters(supplied_keys, defined_names):
    """Sorted parameter names the caller supplied that the algorithm does not define (case-sensitive, as Processing is). Pure.
    GitHub #163 (audit F27): these used to be passed straight through, so a typo was either silently ignored or surfaced as an
    unrelated Processing error."""
    defined = set(defined_names)
    return sorted(k for k in supplied_keys if k not in defined)


def _algorithm_definition(alg_id):
    """(parameter names, destination parameter names, raster destination names, output definitions) of the algorithm in the
    running registry, or None when it cannot be asked (no registry, unknown id). Callers fall back to the old behaviour then."""
    try:
        algorithm = QgsApplication.processingRegistry().algorithmById(alg_id)
        if algorithm is None:
            return None
        params = list(algorithm.parameterDefinitions())
        names = {p.name() for p in params}
        destinations = {p.name() for p in params if p.isDestination()}
        raster_destinations = {p.name() for p in params if p.isDestination() and "raster" in str(p.type()).lower()}
        return names, destinations, raster_destinations, list(algorithm.outputDefinitions())
    except Exception:
        return None


def harvest_outputs(output, definition=None):
    """[(key, value)] for every output of a finished algorithm that is a layer or a raster file path, in algorithm order. Pure
    given plain values: a value is a layer when it has setName(), or a raster path when the output is declared a raster. GitHub #163:
    only the key 'OUTPUT' used to be looked at, so multi-output algorithms lost their other results."""
    if not isinstance(output, dict):
        return []
    raster_keys = set()
    order = list(output.keys())
    if definition is not None:
        raster_keys = {d.name() for d in definition[3] if "raster" in str(d.type()).lower()}
        declared = [d.name() for d in definition[3]]
        order = [k for k in declared if k in output] + [k for k in output if k not in declared]
    found = []
    for key in order:
        value = output[key]
        if hasattr(value, "setName"):
            found.append((key, value))
        elif isinstance(value, str) and (key in raster_keys or (definition is None and key == "OUTPUT")) and value:
            found.append((key, value))
    return found


def _resolve_params(params, raster_output=False, destination_keys=None, raster_keys=None):
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
        if destination_keys is not None:
            is_destination = key in destination_keys
        else:
            is_destination = any(key_lower == suffix or key_lower.endswith("_" + suffix) for suffix in _OUTPUT_KEY_SUFFIXES)
        if is_destination:
            as_raster = (key in raster_keys) if raster_keys is not None else raster_output
            resolved[key] = _SAFE_RASTER_OUTPUT_VALUE if as_raster else _SAFE_OUTPUT_VALUE
            has_output_key = True
            continue
        if isinstance(value, str):
            layer = _find_layer_by_name(value)
            resolved[key] = layer if layer is not None else value
        else:
            resolved[key] = value
    if destination_keys is not None:
        # every destination the algorithm defines gets a safe sink, whether or not the caller named it (a second output such as
        # OUTPUT_LINES used to be left unset, so Processing failed or wrote to its own default)
        for key in destination_keys:
            if key not in resolved:
                as_raster = (key in raster_keys) if raster_keys is not None else raster_output
                resolved[key] = _SAFE_RASTER_OUTPUT_VALUE if as_raster else _SAFE_OUTPUT_VALUE
    elif not has_output_key:
        resolved["OUTPUT"] = _SAFE_RASTER_OUTPUT_VALUE if raster_output else _SAFE_OUTPUT_VALUE
    return resolved


@register_tool(
    "run_allowlisted_processing_algorithm",
    "Runs one QGIS Processing algorithm from a fixed, pre-approved list -- prefer this over "
    "execute_pyqgis_script when the task is achievable via a single Processing algorithm that "
    "isn't already covered by a dedicated tool. It calls only the named, pre-approved algorithm with "
    "the given parameters and never accepts a FORMULA or EXTRA (raw backend arguments) parameter; "
    "algorithms that evaluate free-form expressions as code (such as the GDAL raster calculator) are "
    "not on the list. Only algorithms already used elsewhere in this codebase "
    "are allowed -- an unlisted algorithm id is rejected outright, not run. Output is always kept "
    "in-memory as a new project layer (auto-named), never written to a file path -- use a "
    "dedicated export tool (export_layer, export_to_csv) afterward if a file is actually needed. "
    "Don't specify the output (destination) parameters yourself -- they are set automatically and any "
    "value you give is ignored. An unknown parameter name is rejected before the algorithm runs, with the list of valid names; an algorithm with several outputs returns each as its own layer (additional_outputs); native:selectbylocation changes the selection of the existing layer instead of creating one. Any string parameter value matching a currently-loaded layer's "
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
def _run_allowlisted(alg_id, resolved_params):
    """processing.run(alg_id, params), off the GUI thread when that is safe (rc20 audit A14, #221).

    An algorithm that changes the user's own layer (a selection) stays synchronous: edits to a project layer are only safe on the
    GUI thread. Every other approved algorithm creates new data, which QGIS's task runner handles, so a long one no longer shows
    "Not Responding" and Stop works. Outside a real GUI thread (tests, the kill-switch setting) this is exactly processing.run."""
    if alg_id in MUTATES_INPUT_ALGORITHM_IDS or not _bg.can_run_in_background():
        return processing.run(alg_id, resolved_params)
    context = QgsProcessingContext()
    context.setProject(QgsProject.instance())
    return _bg.run_algorithm(alg_id, resolved_params, context,
                             fallback=lambda a, p, context=None: processing.run(a, p), label=alg_id.split(":")[-1])


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
    violation = parameter_violation(alg_id, params)
    if violation:
        return {"error": violation}

    definition = _algorithm_definition(alg_id)
    destination_keys = raster_keys = None
    if definition is not None:
        wrong = unknown_parameters(params.keys(), definition[0])
        if wrong:
            return {"error": f"'{alg_id}' has no parameter(s) {wrong}. Its parameters are: {sorted(definition[0])}.",
                    "rejected_before_running": True}
        destination_keys, raster_keys = definition[1], definition[2]

    try:
        resolved_params = _resolve_params(params, raster_output=alg_id in RASTER_OUTPUT_ALGORITHM_IDS,
                                          destination_keys=destination_keys, raster_keys=raster_keys)
        output = _run_allowlisted(alg_id, resolved_params)
    except _bg.AnalysisCancelled:
        return {"error": f"Stopped before '{alg_id}' finished. Nothing was added to the project.", "cancelled": True}
    except Exception as e:
        return {"error": f"'{alg_id}' failed: {e}"}

    if alg_id in MUTATES_INPUT_ALGORITHM_IDS:
        # The result IS the user's own layer (for example a changed selection): never rename it or call it new.
        target = resolved_params.get("INPUT")
        result = {"success": True, "alg_id": alg_id, "changed_existing_layer": True,
                  "message": f"'{alg_id}' changed the existing layer rather than creating a new one."}
        if hasattr(target, "name"):
            result["layer_name"] = target.name()
        if hasattr(target, "selectedFeatureCount"):
            result["selected_feature_count"] = target.selectedFeatureCount()
        return result

    harvested = harvest_outputs(output, definition)
    layers = []
    for key, value in harvested:
        if isinstance(value, str):                      # a raster algorithm returns the path of the file it wrote
            loaded = QgsRasterLayer(value, "raster_output")
            value = loaded if loaded.isValid() else None
        if value is not None and hasattr(value, "setName"):
            layers.append((key, value))
    if not layers:
        return {"success": True, "alg_id": alg_id, "message": f"'{alg_id}' ran successfully with no new layer output."}
    primary_key, new_layer = layers[0]

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
    try:
        from .output_style import style_algorithm_output
        styled = style_algorithm_output(new_layer, alg_id)
        if styled:
            result["styled_as"] = styled
    except Exception:
        pass   # a result with the default look beats a failed tool call
    if hasattr(new_layer, "featureCount"):
        count = new_layer.featureCount()
        result["feature_count"] = count
        if count == 0:
            result["warning"] = "The output layer has 0 features -- check the inputs before treating this as a real empty result."

    # GitHub #163: algorithms with several outputs (for example a lines output AND a points output) return all of them, each as its
    # own layer named <layer_name>_<output key>; the first output keeps the plain name above.
    extra = []
    for key, layer in layers[1:]:
        extra_name = f"{layer_name}_{key.lower()}"
        layer.setName(extra_name)
        project.addMapLayer(layer)
        node = project.layerTreeRoot().findLayer(layer.id())
        if node is not None and not caller_named_it:
            node.setItemVisibilityChecked(False)
        entry = {"output": key, "layer_name": extra_name}
        if hasattr(layer, "featureCount"):
            entry["feature_count"] = layer.featureCount()
        extra.append(entry)
    if extra:
        result["primary_output"] = primary_key
        result["additional_outputs"] = extra
    return result
