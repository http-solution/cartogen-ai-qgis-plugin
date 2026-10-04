# -*- coding: utf-8 -*-
"""
Forecast trigger evaluation for anticipatory action (H4, docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md).

A trigger model says: "if the forecast for this area reaches THRESHOLD within LEAD days (with at least PROBABILITY), release the
pre-arranged action". This tool only EVALUATES such a rule against forecast values already in a layer's attribute table (one or
more forecast rows per area). It does not fetch forecasts, does not predict anything, and never supplies a threshold: the
threshold, the lead window and the probability cut-off come from the user (from their own trigger protocol) and are printed back
in the result so the rule that produced an "activated" is always visible. Missing or unparsable values are counted and reported,
never treated as exceedances. The rule logic is pure and unit tested; reading the layer needs QGIS.
"""
import datetime

from .registry import register_tool

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

COMPARISONS = {
    ">=": lambda v, t: v >= t,
    ">": lambda v, t: v > t,
    "<=": lambda v, t: v <= t,
    "<": lambda v, t: v < t,
}
_MAX_ROWS = 500_000


# ---------------------------------------------------------------- pure --

def to_date(value):
    """date from a date/datetime, a QDate/QDateTime-like object, or an ISO 'YYYY-MM-DD[...]' string; None when it cannot be read. Pure."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    for attr in ("toPyDateTime", "toPyDate"):
        fn = getattr(value, attr, None)
        if callable(fn):
            try:
                return to_date(fn())
            except Exception:
                return None
    text = str(value).strip()
    if not text or text.upper() == "NULL":
        return None
    try:
        return datetime.date.fromisoformat(text[:10])
    except ValueError:
        return None


def to_number(value):
    """float, or None for missing / non-numeric / NaN. Pure."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def validate_rule(threshold, comparison, lead_days, min_probability, min_exceedances):
    """Error text for an invalid rule, else None. Pure. A threshold is mandatory: there is no default."""
    if threshold is None or to_number(threshold) is None:
        return "threshold is required and must be a number: it comes from your trigger protocol, there is no default."
    if comparison not in COMPARISONS:
        return f"comparison must be one of {list(COMPARISONS)}."
    if lead_days is not None and (to_number(lead_days) is None or float(lead_days) < 0):
        return "lead_days must be zero or a positive number of days."
    if min_probability is not None and not (to_number(min_probability) is not None and 0.0 <= float(min_probability) <= 1.0):
        return "min_probability must be between 0 and 1."
    if to_number(min_exceedances) is None or int(min_exceedances) < 1:
        return "min_exceedances must be 1 or more."
    return None


def evaluate_triggers(rows, value_key, threshold, comparison=">=", unit_key=None, date_key=None, as_of=None, lead_days=None,
                      probability_key=None, min_probability=None, min_exceedances=1):
    """Apply the rule to forecast rows (dicts). Pure. Returns {units, activated_count, unit_count, rows_used, rows_skipped, ...}.

    A row counts toward a unit when its value is numeric and, if lead_days is given, its date lies within [as_of, as_of+lead_days]
    (rows without a readable date are skipped and counted, never assumed to be in the window). With probability_key and
    min_probability a row exceeds only if its probability is also numeric and at least min_probability. A unit is activated when
    it has at least min_exceedances exceeding rows."""
    compare = COMPARISONS[comparison]
    threshold = float(threshold)
    window = None
    if lead_days is not None:
        if date_key is None:
            raise ValueError("lead_days needs date_key.")
        start = as_of or datetime.date.today()
        window = (start, start + datetime.timedelta(days=float(lead_days)))
    use_probability = probability_key is not None and min_probability is not None

    units = {}
    skipped = {"non_numeric_value": 0, "outside_lead_window": 0, "unreadable_date": 0, "missing_probability": 0}
    used = 0
    for row in rows:
        unit = "all" if unit_key is None else str(row.get(unit_key))
        entry = units.setdefault(unit, {"unit": unit, "rows": 0, "max_value": None, "min_value": None,
                                        "exceedances": 0, "first_exceedance": None})
        value = to_number(row.get(value_key))
        if value is None:
            skipped["non_numeric_value"] += 1
            continue
        when = None
        if window is not None:
            when = to_date(row.get(date_key))
            if when is None:
                skipped["unreadable_date"] += 1
                continue
            if not window[0] <= when <= window[1]:
                skipped["outside_lead_window"] += 1
                continue
        elif date_key is not None:
            when = to_date(row.get(date_key))
        probability_ok = True
        if use_probability:
            probability = to_number(row.get(probability_key))
            if probability is None:
                skipped["missing_probability"] += 1
                continue
            probability_ok = probability >= float(min_probability)
        used += 1
        entry["rows"] += 1
        entry["max_value"] = value if entry["max_value"] is None else max(entry["max_value"], value)
        entry["min_value"] = value if entry["min_value"] is None else min(entry["min_value"], value)
        if compare(value, threshold) and probability_ok:
            entry["exceedances"] += 1
            if when is not None and (entry["first_exceedance"] is None or when < entry["first_exceedance"]):
                entry["first_exceedance"] = when

    out = []
    for entry in units.values():
        entry["activated"] = entry["exceedances"] >= int(min_exceedances)
        if entry["first_exceedance"] is not None:
            entry["first_exceedance"] = entry["first_exceedance"].isoformat()
        out.append(entry)
    out.sort(key=lambda e: (not e["activated"], -(e["exceedances"]), e["unit"]))
    return {
        "units": out,
        "unit_count": len(out),
        "activated_count": sum(1 for e in out if e["activated"]),
        "rows_used": used,
        "rows_skipped": {k: v for k, v in skipped.items() if v},
    }


def describe_rule(value_key, threshold, comparison, unit_key, date_key, as_of, lead_days, probability_key, min_probability,
                  min_exceedances):
    """The rule in one sentence, echoed in the result so an 'activated' can always be traced to it. Pure."""
    text = f"{value_key} {comparison} {float(threshold):g}"
    if probability_key is not None and min_probability is not None:
        text += f" with {probability_key} >= {float(min_probability):g}"
    if lead_days is not None:
        start = as_of or datetime.date.today()
        text += f", forecast dated {start.isoformat()} to {(start + datetime.timedelta(days=float(lead_days))).isoformat()} ({float(lead_days):g} days lead)"
    text += f"; activated when at least {int(min_exceedances)} forecast row(s) meet it"
    if unit_key is not None:
        text += f", evaluated per '{unit_key}'"
    return text + "."


# ---------------------------------------------------------------- QGIS --

@register_tool(
    "evaluate_forecast_trigger",
    "Evaluate an anticipatory-action trigger rule against forecast values already in a layer's attribute table: for each area, does "
    "the forecast reach the threshold within the lead window (optionally with a minimum probability)? Returns which areas are "
    "activated, with the maximum forecast value, the number of exceeding forecast rows and the first exceedance date, plus the "
    "rule restated in words. The threshold, lead window and probability cut-off MUST come from the user's own trigger protocol "
    "-- this tool has no defaults and never invents one; if the user has not given a threshold, ask for it. It evaluates a rule; "
    "it does not fetch or generate forecasts and its answer is only as good as the forecast data in the layer. Read-only.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Layer (or table) holding forecast rows: one or more per area."},
            "value_field": {"type": "string", "description": "Numeric field with the forecast value (e.g. river discharge, rainfall, wind speed)."},
            "threshold": {"type": "number", "description": "Trigger threshold, from the user's protocol. Required."},
            "comparison": {"type": "string", "enum": list(COMPARISONS), "description": "Default '>='."},
            "unit_field": {"type": "string", "description": "Field identifying the area (admin name/code, station). Omit to evaluate the whole layer as one unit."},
            "date_field": {"type": "string", "description": "Field with the date the forecast is valid for. Required with lead_days."},
            "lead_days": {"type": "number", "description": "Only count forecast rows dated from as_of to as_of + lead_days."},
            "as_of": {"type": "string", "description": "ISO date the lead window starts from. Default today."},
            "probability_field": {"type": "string", "description": "Optional numeric field (0-1) with the forecast probability of the value."},
            "min_probability": {"type": "number", "description": "With probability_field: minimum probability (0-1) for a row to count."},
            "min_exceedances": {"type": "integer", "description": "Exceeding forecast rows needed to activate a unit. Default 1."},
        },
        "required": ["layer_name", "value_field", "threshold"],
    },
)
def evaluate_forecast_trigger(layer_name, value_field, threshold=None, comparison=">=", unit_field=None, date_field=None,
                              lead_days=None, as_of=None, probability_field=None, min_probability=None, min_exceedances=1):
    problem = validate_rule(threshold, comparison, lead_days, min_probability, min_exceedances)
    if problem:
        return {"error": problem}
    if lead_days is not None and not date_field:
        return {"error": "lead_days needs date_field (the field holding each forecast row's valid date)."}
    if (probability_field is None) != (min_probability is None):
        return {"error": "probability_field and min_probability go together: give both or neither."}
    start = None
    if as_of:
        start = to_date(as_of)
        if start is None:
            return {"error": "as_of must be an ISO date such as 2026-10-04."}
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        return {"error": f"Layer '{layer_name}' not found"}
    layer = layers[0]
    names = [f.name() for f in layer.fields()]
    for label, field in (("value_field", value_field), ("unit_field", unit_field), ("date_field", date_field),
                         ("probability_field", probability_field)):
        if field is not None and field not in names:
            return {"error": f"{label} '{field}' not found in '{layer_name}'. Fields: {names}"}
    if layer.featureCount() > _MAX_ROWS:
        return {"error": f"'{layer_name}' has {layer.featureCount()} rows; the limit is {_MAX_ROWS}."}

    keys = [k for k in (value_field, unit_field, date_field, probability_field) if k]
    rows = [{k: feat.attribute(k) for k in keys} for feat in layer.getFeatures()]
    result = evaluate_triggers(rows, value_field, threshold, comparison, unit_field, date_field, start,
                               lead_days, probability_field, min_probability, min_exceedances)
    result.update({
        "success": True,
        "layer_name": layer_name,
        "rule": describe_rule(value_field, threshold, comparison, unit_field, date_field, start, lead_days,
                              probability_field, min_probability, min_exceedances),
        "note": "This evaluates the rule you gave against the forecast values in the layer; it is not a forecast and the "
                "threshold is not validated here.",
    })
    if result["rows_used"] == 0:
        result["warning"] = "No forecast row could be used (see rows_skipped); no unit can be activated from this data."
    return result
