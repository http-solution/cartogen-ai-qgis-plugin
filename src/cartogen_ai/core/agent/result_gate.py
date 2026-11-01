"""Verified result gate (PLAN-031, roadmap step A): after a tool creates or modifies a layer, check the result itself and put the outcome in
the tool result, so a wrong answer is reported as wrong even when the model would have accepted it.

The checks are pure (core/validators/result_checks.py). This module is the part that touches QGIS: it decides whether a result is worth
checking, reads the output layer into the plain summary the checks take, and attaches `checks`, `checks_summary` and a note to the result.

What runs today, honestly:
  * Eligible: a tool classified CREATE or MODIFY (tool_operations.py) whose successful result names an output layer in `layer_name`. A tool
    inherits the gate by being classified and returning that key; nothing is registered per tool.
  * Always: output not empty, geometries valid. When the result also names `output_field` (the tools that write a score into a layer): that
    field is not empty, not one value everywhere.
  * NOT enabled for any tool yet: the CRS-in-degrees check (DISTANCE_BASED_TOOLS is empty on purpose) and the stale-field check. A tool
    that computes in a projected CRS and reprojects its output back to EPSG:4326 would be reported as "computed in degrees", a false
    alarm on a correct result, and a rerun with the same inputs legitimately writes identical values. Each needs a tool-by-tool decision
    from a real run before it is switched on; the pure checks exist and are tested.
  * Tools that run through the network-only or two-phase paths (fetch_* tools) are not gated yet.
Large layers are sampled (SAMPLE_CAP features) so the gate has a bounded cost; the summary says so. Switched off by the QgsSettings value
cartogen_ai/result_gate = false. Never raises: a failure inside the gate must not fail the tool call that already succeeded."""
import contextlib

from ..logger import log_event
from ..validators import result_checks

try:
    from qgis.core import QgsProject, QgsSettings, QgsVectorLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

SETTINGS_KEY = "cartogen_ai/result_gate"
SAMPLE_CAP = 5000                       # features read per layer; bounds the cost on a 50,000-feature layer
GATED_OPERATIONS = frozenset({"CREATE", "MODIFY"})
DISTANCE_BASED_TOOLS: frozenset[str] = frozenset()      # see the module docstring: empty until a real run shows a tool computes in the layer's own CRS
ONE_TO_ONE_TOOLS: frozenset[str] = frozenset()          # likewise: needs the input feature count, which the result does not carry yet


def gate_enabled():
    """True unless the user switched it off (cartogen_ai/result_gate = false). Outside QGIS: True."""
    if not QGIS_AVAILABLE:
        return True
    with contextlib.suppress(Exception):
        return bool(QgsSettings().value(SETTINGS_KEY, True, type=bool))
    return True


def output_layer_name(result):
    """The project layer name a result says it wrote to, else None. Pure."""
    name = result.get("layer_name") if isinstance(result, dict) else None
    return name if isinstance(name, str) and name.strip() else None


def eligible(operation_type, result):
    """True for a successful CREATE/MODIFY result that names its output layer. Pure."""
    if operation_type not in GATED_OPERATIONS or not isinstance(result, dict) or "error" in result or result.get("success") is False:
        return False
    return output_layer_name(result) is not None


def context_for(name, result):
    """The check context for a tool's result. Pure."""
    written = {}
    field = result.get("output_field") if isinstance(result, dict) else None
    if isinstance(field, str) and field:
        written[field] = ""             # unit unknown: the field is checked for empty and constant, not for a range
    return {"distance_based": name in DISTANCE_BASED_TOOLS, "one_to_one": name in ONE_TO_ONE_TOOLS, "written_fields": written}


def attach(result, checks, sampled_of=None):
    """`result` with the checks, a one-line summary and, when something failed, a note the model must act on. Mutates and returns it. Pure."""
    text, failed = result_checks.summarize(checks)
    result["checks"] = checks
    result["checks_summary"] = text + (f" (first {sampled_of[0]} of {sampled_of[1]} features checked)" if sampled_of else "")
    if failed:
        result["checks_note"] = ("A check on this result FAILED. Say so plainly in your answer and do not present the result as correct: "
                                 + " ".join(c["detail"] for c in checks if c["status"] == result_checks.FAIL))
    return result


def _is_null(value):
    return value is None or str(value) == "NULL" or (isinstance(value, float) and value != value)


def summarize_layer(layer, written_fields, cap=SAMPLE_CAP):
    """The plain summary result_checks takes, read from a QgsVectorLayer. MAIN THREAD ONLY. Reads at most `cap` features."""
    from qgis.core import QgsFeatureRequest
    crs = layer.crs()
    total = int(layer.featureCount())
    seen = invalid = empty = 0
    stats = {f: {"count": 0, "null": 0, "distinct": 0, "min": None, "max": None, "fingerprint": None, "_values": set()} for f in written_fields
             if layer.fields().indexOf(f) >= 0}
    for feature in layer.getFeatures(QgsFeatureRequest().setLimit(cap)):
        seen += 1
        geometry = feature.geometry()
        if geometry is None or geometry.isNull() or geometry.isEmpty():
            empty += 1
        elif not geometry.isGeosValid():
            invalid += 1
        for field, stat in stats.items():
            value = feature[field]
            if _is_null(value):
                stat["null"] += 1
                continue
            stat["count"] += 1
            if len(stat["_values"]) < 2:
                stat["_values"].add(str(value))
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                stat["min"] = value if stat["min"] is None else min(stat["min"], value)
                stat["max"] = value if stat["max"] is None else max(stat["max"], value)
    for stat in stats.values():
        stat["distinct"] = len(stat.pop("_values"))      # capped at 2: all the checks need is "one value or more"
    summary = {"name": layer.name(), "crs_authid": crs.authid() if crs.isValid() else None,
               "crs_geographic": crs.isGeographic() if crs.isValid() else None, "feature_count": total, "input_feature_count": None,
               "geometry": {"total": seen, "invalid": invalid, "empty": empty} if seen else None, "fields": stats}
    return summary, ((seen, total) if total > seen else None)


def attach_checks(name, result, operation_type):
    """The hook: returns `result`, with checks attached when it is eligible. MAIN THREAD ONLY. Never raises."""
    try:
        if not QGIS_AVAILABLE or not gate_enabled() or not eligible(operation_type, result):
            return result
        layers = QgsProject.instance().mapLayersByName(output_layer_name(result))
        layer = next((candidate for candidate in layers if isinstance(candidate, QgsVectorLayer) and candidate.isValid()), None)
        if layer is None:
            return result
        context = context_for(name, result)
        summary, sampled_of = summarize_layer(layer, list(context["written_fields"]))
        checks = result_checks.run_checks(summary, context)
        if checks:
            attach(result, checks, sampled_of)
            log_event("result_gate", tag="Agent", tool=name, status="failed" if any(c["status"] == "fail" for c in checks) else "ok")
    except Exception as e:
        log_event("swallowed_exception", tag="Agent", tool="result_gate", error_class=type(e).__name__, error=True)
    return result
