# -*- coding: utf-8 -*-
"""Finish the map step a request asked for when the model stops one call short.

rc22 hand test (issue 232, rows T3, V11, T2/V4): after an import or analysis tool wrote its result field, the tool returned the exact
`apply_humanitarian_look` call that draws it (`map_look` / `map_looks`), but the model sometimes ended the turn without making it -- the
reply even claimed class colours that were never applied (T3: UNOSAT points left single-symbol). The tools deliberately do not restyle
layers on their own; this keeps that rule and instead makes ONE deterministic follow-up when (a) the user's request asked to see the
result on the map and (b) a hint from this turn was never acted on. Also covers UNOSAT, whose layer only exists after
load_tabular_data_as_layer, so no hint can come from the import itself. Pure: no QGIS."""
import re

_WANTS_MAP = re.compile(r"\b(map|show|display|visuali[sz]\w*|style|colou?r\w*|symboli[sz]\w*|draw|plot|render|look)\b", re.I)


def wants_map(query):
    return bool(_WANTS_MAP.search(query or ""))


def _hints_from(result):
    out = []
    if not isinstance(result, dict):
        return out
    for hint in ([result.get("map_look")] if result.get("map_look") else []) + list(result.get("map_looks") or []):
        if isinstance(hint, dict) and hint.get("tool") == "apply_humanitarian_look" and isinstance(hint.get("args"), dict):
            out.append(dict(hint["args"]))
    return out


def _ok(result):
    return isinstance(result, dict) and "error" not in result and result.get("status") not in ("PREVIEW_REQUIRED", "EGRESS_BLOCKED")


def collect_hints(turn_calls):
    """Look arguments suggested by this turn's results, plus the UNOSAT hint (import_humanitarian_table kind=unosat followed by a
    successful load_tabular_data_as_layer). `turn_calls` = [(tool, arguments dict, result)]. Pure."""
    hints = []
    unosat_field = None
    for name, args, result in turn_calls:
        if not _ok(result):
            continue
        hints += _hints_from(result)
        if name == "import_humanitarian_table" and str((args or {}).get("kind", "")).lower() == "unosat":
            unosat_field = (result.get("mapping_used") or {}).get("damage_class")
        elif name == "load_tabular_data_as_layer" and unosat_field and result.get("layer_name"):
            hints.append({"layer_name": result["layer_name"], "look": "damage_class", "field": unosat_field})
            unosat_field = None
    return hints


def pending_hints(turn_calls):
    """Hints with no later successful apply_humanitarian_look on the same layer and field. Pure."""
    applied = {(a.get("layer_name"), a.get("field")) for n, a, r in turn_calls if n == "apply_humanitarian_look" and _ok(r)}
    seen, out = set(), []
    for hint in collect_hints(turn_calls):
        key = (hint.get("layer_name"), hint.get("field"))
        if key not in applied and key not in seen:
            seen.add(key)
            out.append(hint)
    return out


def nudge_for(query, turn_calls):
    """The one-time follow-up message, or None. Pure."""
    if not wants_map(query):
        return None
    pending = pending_hints(turn_calls)
    if not pending:
        return None
    calls = "; ".join("apply_humanitarian_look(layer_name=%r, look=%r, field=%r)" % (h["layer_name"], h["look"], h["field"]) for h in pending[:3])
    return ("The request asked to see the result on the map, and the result is still in default colours. Call " + calls +
            " now with exactly these arguments, then say what the map shows. Do not describe colours or classes that were not applied.")
