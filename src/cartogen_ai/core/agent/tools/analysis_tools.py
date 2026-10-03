# -*- coding: utf-8 -*-
"""
Data Analysis & Prediction Tools for Cartogen AI.

Pure-Python statistics throughout (no numpy/pandas/scipy), matching the
distribution-analysis approach already used in styling_tools.py's
apply_graduated_style (mean/variance/skewness computed by hand there too).
"""

import datetime
import os
from .registry import register_tool
from .raster_tools import estimate_population_exposure
from .multimodal_remote_sensing import calculate_raster_change_detection

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


_MAX_RESULT_ENTRIES = 50


def _cap_entries(entries, limit=_MAX_RESULT_ENTRIES):
    """Truncates an already worst-first-sorted list before it's returned to
    the model. An uncapped one-entry-per-admin-unit result (routinely
    hundreds of units at ADM3) gets resent on every remaining iteration of
    the same turn and lingers in conversation history for several turns
    afterward -- real, compounding token cost for data the model rarely
    needs in full (it can ask for a specific unit or class if it does).
    Callers that also write results back to a layer must do so with the
    FULL list before calling this, not the capped one, or units past the
    cutoff would silently go unwritten."""
    total = len(entries)
    if total <= limit:
        return entries, total, False
    return entries[:limit], total, True


def _parse_date(value):
    """Best-effort parse of a feature attribute value into a date object.
    QGIS date-field values commonly arrive as QDate/QDateTime (has
    .toPyDate()), a Python date/datetime, or a plain string -- handles all
    three without needing a QGIS import here, so this stays testable
    outside QGIS. Returns None (not an exception) for anything unparseable
    -- the caller skips those rows rather than failing the whole forecast."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if hasattr(value, "toPyDate"):
        try:
            return value.toPyDate()
        except Exception:
            pass
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s[:10])
    except ValueError:
        pass
    for fmt in ("%Y/%m/%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _linear_regression(x_values, y_values):
    """Ordinary least squares for y = slope*x + intercept, plus R^2 fit
    quality. Pure Python, no numpy."""
    n = len(x_values)
    mean_x = sum(x_values) / n
    mean_y = sum(y_values) / n
    ss_xx = sum((x - mean_x) ** 2 for x in x_values)
    if ss_xx == 0:
        return {"slope": 0.0, "intercept": mean_y, "r_squared": 0.0}
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values))
    slope = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in y_values)
    if ss_tot == 0:
        r_squared = 1.0 if slope == 0 else 0.0
    else:
        ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(x_values, y_values))
        r_squared = 1 - ss_res / ss_tot
    return {"slope": slope, "intercept": intercept, "r_squared": r_squared}


def _forecast_series(dates, values, periods_ahead):
    """Pure-Python trend projection over a (date, value) series -- fully
    testable without QGIS. dates/values must be the same length and need
    not be pre-sorted. Returns an error dict for too little/degenerate
    data, otherwise the fit plus projected future points."""
    if len(dates) < 3:
        return {"error": f"Need at least 3 data points to fit a trend, got {len(dates)}."}

    pairs = sorted(zip(dates, values), key=lambda p: p[0])
    dates_sorted = [p[0] for p in pairs]
    values_sorted = [p[1] for p in pairs]

    first_date = dates_sorted[0]
    x_values = [(d - first_date).days for d in dates_sorted]

    fit = _linear_regression(x_values, values_sorted)

    # Project at the data's own observation cadence (median gap between
    # consecutive points), not an arbitrary fixed interval.
    gaps = sorted(b - a for a, b in zip(x_values, x_values[1:])) or [1]
    cadence_days = gaps[len(gaps) // 2] or 1

    last_x = x_values[-1]
    projections = []
    for i in range(1, periods_ahead + 1):
        future_x = last_x + cadence_days * i
        future_value = fit["slope"] * future_x + fit["intercept"]
        future_date = first_date + datetime.timedelta(days=future_x)
        projections.append({"date": future_date.isoformat(), "projected_value": round(future_value, 2)})

    if fit["slope"] > 0:
        direction = "increasing"
    elif fit["slope"] < 0:
        direction = "decreasing"
    else:
        direction = "flat"

    r2 = fit["r_squared"]
    confidence = "strong" if r2 >= 0.7 else "moderate" if r2 >= 0.4 else "weak"

    return {
        "success": True,
        "observed_points": len(values_sorted),
        "date_range": {"start": dates_sorted[0].isoformat(), "end": dates_sorted[-1].isoformat()},
        "historical_mean": round(sum(values_sorted) / len(values_sorted), 2),
        "trend_direction": direction,
        "trend_slope_per_day": round(fit["slope"], 4),
        "fit_quality_r_squared": round(r2, 3),
        "fit_confidence": confidence,
        "projections": projections,
    }


def _bucket_dates_by_period(dates, period_days):
    """Buckets a list of dates into period_days-sized periods counted from
    the earliest date. Returns (first_date, last_date, num_periods,
    bucket_indices), where bucket_indices[i] is dates[i]'s period index
    (0-based). Pure Python, no geometry involved -- kept separate from
    analyze_incident_trend's actual point-counting (which needs real QGIS
    geometries) so the date arithmetic itself is testable without QGIS,
    same split _forecast_series/forecast_trend already use."""
    first_date = min(dates)
    last_date = max(dates)
    num_periods = (last_date - first_date).days // period_days + 1
    bucket_indices = [(d - first_date).days // period_days for d in dates]
    return first_date, last_date, num_periods, bucket_indices


def _normalize_minmax(values, invert=False):
    """Rescales values to 0-1, where 1 always means "worse" (higher severity).
    invert=True is for indicators where a HIGHER raw value means a BETTER
    situation (e.g. % of population with water access, health facilities per
    capita) -- without it, a well-served district would score as high-severity.

    Only min-max is offered, deliberately. A "z-score" option would be a knob
    that does nothing here: z = (x - mean) / std is an affine transform, so
    rescaling z-scores back to 0-1 for the composite is algebraically
    identical to plain min-max on the raw values ((x - min) / (max - min)
    either way). Offering it as a distinct choice would imply a difference in
    the result that doesn't exist.

    Returns (normalized_list, had_variation). had_variation is False when
    every value is identical -- that indicator can't discriminate between
    units at all, so it contributes 0 to every unit's score and is reported
    back to the caller rather than silently counting as if it had signal."""
    lo, hi = min(values), max(values)
    span = hi - lo
    if span == 0:
        return [0.0] * len(values), False
    normalized = [(v - lo) / span for v in values]
    if invert:
        normalized = [1.0 - n for n in normalized]
    return normalized, True


def _severity_class(score):
    """Maps a 0-1 composite score to a 1-5 severity class on equal intervals
    (<0.2 -> 1, ... >=0.8 -> 5), matching the 5-phase convention JIAF/IPC-style
    severity scales use. Equal-interval (not quantile) on purpose: quantiles
    would force a fixed proportion of units into the worst class regardless of
    how bad things actually are, which is exactly the wrong behavior when the
    output drives funding allocation."""
    return min(5, int(score * 5) + 1)


def _compute_severity_index(rows, indicators, weights=None, invert_indicators=None):
    """Pure-Python composite severity index over already-extracted rows --
    fully testable without QGIS, same split as _forecast_series above.

    rows: list of {"unit": <name>, <indicator field>: <numeric>, ...}
    indicators: ordered list of indicator field names to combine
    weights: optional {field: weight}; missing entries default to 1.0, and
        the whole set is normalized to sum to 1 so weights are relative, not
        absolute.
    invert_indicators: list of fields where higher raw value = better.

    Units missing any indicator value are EXCLUDED and reported separately
    rather than imputed -- silently filling a gap with a mean/zero would
    invent a severity score for a place with no data, which is the single
    most dangerous failure mode for an allocation input."""
    if not indicators:
        return {"error": "At least one indicator field is required."}
    if not rows:
        return {"error": "No rows to score."}

    invert_set = set(invert_indicators or [])
    unknown_inverts = invert_set - set(indicators)
    if unknown_inverts:
        return {"error": f"invert_indicators names fields that aren't in indicators: {sorted(unknown_inverts)}"}

    weights = weights or {}
    unknown_weights = set(weights) - set(indicators)
    if unknown_weights:
        return {"error": f"weights names fields that aren't in indicators: {sorted(unknown_weights)}"}
    raw_weights = [float(weights.get(f, 1.0)) for f in indicators]
    if any(w < 0 for w in raw_weights):
        return {"error": "Weights must be non-negative."}
    weight_total = sum(raw_weights)
    if weight_total == 0:
        return {"error": "Weights sum to zero -- at least one indicator must carry weight."}
    norm_weights = [w / weight_total for w in raw_weights]

    complete, excluded = [], []
    for row in rows:
        missing = [f for f in indicators if not isinstance(row.get(f), (int, float))]
        (excluded if missing else complete).append(
            {"unit": row.get("unit"), "missing_fields": missing} if missing else row
        )

    if not complete:
        return {"error": "No units had a value for every indicator -- nothing to score."}

    normalized_columns = {}
    no_variation = []
    for field in indicators:
        column = [float(r[field]) for r in complete]
        normalized, had_variation = _normalize_minmax(column, invert=field in invert_set)
        normalized_columns[field] = normalized
        if not had_variation:
            no_variation.append(field)

    scored = []
    for i, row in enumerate(complete):
        score = sum(normalized_columns[f][i] * w for f, w in zip(indicators, norm_weights))
        scored.append({
            "unit": row.get("unit"),
            "severity_score": round(score, 4),
            "severity_class": _severity_class(score),
            "indicator_values": {f: row[f] for f in indicators},
        })
    scored.sort(key=lambda r: r["severity_score"], reverse=True)

    return {
        "success": True,
        "method": "min-max normalization to 0-1, weighted sum, equal-interval 1-5 severity class",
        "indicators": list(indicators),
        "applied_weights": {f: round(w, 4) for f, w in zip(indicators, norm_weights)},
        "inverted_indicators": sorted(invert_set),
        "scored_units": len(scored),
        "results": scored,
        # Surfaced, not swallowed: both of these change how the output should
        # be read, and an allocation decision shouldn't be made without them.
        "indicators_with_no_variation": no_variation,
        "excluded_units_missing_data": excluded,
    }


@register_tool(
    "calculate_severity_index",
    "Build a composite multi-indicator severity/needs index across admin units (JIAF/INFORM-style), "
    "the standard basis for prioritizing which areas receive funding. Takes several numeric indicator "
    "fields already on a polygon layer's attribute table (e.g. food insecurity %, displacement %, "
    "protection incidents, WASH coverage), min-max normalizes each so higher always means worse, "
    "applies relative weights, and returns a 0-1 composite score plus a 1-5 severity class per unit, "
    "ranked worst-first. Use invert_indicators for fields where a HIGHER value means a BETTER "
    "situation (e.g. % with water access) -- otherwise well-served areas score as high-severity. "
    "Units missing any indicator are excluded and listed, never imputed. Always report the weights "
    "and any excluded units alongside the ranking, since both change how it should be read. Results "
    "are capped to the worst 50 units (see truncated/scored_units) -- output_field still writes the "
    "score for every unit to the layer regardless of the cap, so styling/mapping the full set is "
    "unaffected; only the returned JSON is capped.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Polygon layer of admin units."},
            "indicator_fields": {"type": "array", "items": {"type": "string"}, "description": "Numeric indicator fields to combine."},
            "unit_name_field": {"type": "string", "description": "Field holding each unit's name/P-code, used to label results."},
            "weights": {"type": "object", "description": "Optional {field: weight}; defaults to equal. Normalized to sum to 1, so these are relative."},
            "invert_indicators": {"type": "array", "items": {"type": "string"}, "description": "Indicator fields where a HIGHER raw value means a BETTER situation."},
            "output_field": {"type": "string", "description": "Optional: write the composite score back to the layer under this field name."},
        },
        "required": ["layer_name", "indicator_fields", "unit_name_field"],
    },
)
def calculate_severity_index(layer_name, indicator_fields, unit_name_field, weights=None, invert_indicators=None, output_field=None, confirmed: bool = False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    field_names = [f.name() for f in layer.fields()]
    missing = [f for f in list(indicator_fields) + [unit_name_field] if f not in field_names]
    if missing:
        return {"error": f"Field(s) {missing} not found on '{layer_name}'. Available: {field_names}"}

    # QGIS-008, 2026-09-13 audit: output_field writes the composite score into the layer's
    # attribute table via the same provider.changeAttributeValues() mutation
    # field_calculator/calculate_area/calculate_length already gate behind confirmation
    # (BUG-2026-08-21-3) -- this must too, for the same reason. Gated on output_field being
    # requested specifically, not the whole function: the analysis itself (no output_field)
    # is read-only and must stay ungated, or every plain "rank these districts" call would
    # need a pointless confirmation click for something that never touches the layer.
    if output_field and not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "calculate_severity_index",
            "arguments": {
                "layer_name": layer_name, "indicator_fields": indicator_fields,
                "unit_name_field": unit_name_field, "weights": weights,
                "invert_indicators": invert_indicators, "output_field": output_field,
                "confirmed": True,
            },
            "code_snippet": f"layer.startEditing()\n# Add/update field '{output_field}' = composite severity score across features\nlayer.commitChanges()",
            "rationale": f"Data Mutation Preview: Add/update field '{output_field}' on layer '{layer_name}' with each unit's composite severity score.",
            "message": f"Confirmation required before mutating attribute field '{output_field}' on '{layer_name}'.",
        }

    rows = []
    for feat in layer.getFeatures():
        row = {"unit": str(feat[unit_name_field]), "__fid__": feat.id()}
        for f in indicator_fields:
            row[f] = feat[f]
        rows.append(row)

    result = _compute_severity_index(rows, list(indicator_fields), weights, invert_indicators)
    if "error" in result:
        return result

    if output_field:
        # Full, untruncated list -- every unit needs its score written, not
        # just the ones that end up in the capped response below.
        write_error = _write_scores_to_layer(layer, rows, result["results"], output_field)
        if write_error:
            result["output_field_warning"] = write_error
        else:
            result["output_field"] = output_field
            result["layer_name"] = layer_name

    result["results"], _, result["truncated"] = _cap_entries(result["results"])
    if result["truncated"]:
        result["truncation_note"] = (
            f"Showing the top {len(result['results'])} of {result['scored_units']} units, worst-first. "
            "Ask for a specific unit or severity class to see more."
        )
    return result


def _write_scores_to_layer(layer, rows, scored_results, output_field):
    """Adds/updates a numeric field holding each unit's composite score, so it
    can be styled with apply_graduated_style straight after. Returns an error
    string on failure, or None on success -- a write failure downgrades to a
    warning on an otherwise-valid result rather than discarding the scores."""
    try:
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QVariant
    except ImportError:
        return "QGIS field API unavailable -- scores not written to the layer."

    score_by_unit = {r["unit"]: r["severity_score"] for r in scored_results}
    fid_by_unit = {r["unit"]: r["__fid__"] for r in rows if "__fid__" in r}

    provider = layer.dataProvider()
    if output_field not in [f.name() for f in layer.fields()]:
        if not provider.addAttributes([QgsField(output_field, QVariant.Double)]):
            return f"Could not add field '{output_field}' to the layer."
        layer.updateFields()

    idx = layer.fields().indexOf(output_field)
    if idx < 0:
        return f"Field '{output_field}' not present after creation attempt."

    updates = {
        fid_by_unit[unit]: {idx: score}
        for unit, score in score_by_unit.items()
        if unit in fid_by_unit
    }
    if not provider.changeAttributeValues(updates):
        return f"Could not write scores into '{output_field}'."
    layer.updateFields()
    return None


def _write_presence_gap_status_to_layer(layer, rows, gap_units, covered_units, unmatched_units, output_field):
    """Adds/updates a text field holding each high-severity unit's presence-gap
    status ('gap'/'covered'/'unmatched'), so it can be styled with
    apply_categorized_style or placed on generate_html_dashboard straight
    after -- mirrors _write_scores_to_layer's pattern for
    calculate_severity_index above. Units outside the high-severity classes
    (never classified by this analysis at all) are left unset, not given a
    fabricated 'fine' status. Returns an error string on failure, or None on
    success -- a write failure downgrades to a warning on an otherwise-valid
    result rather than discarding the classification."""
    try:
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QVariant
    except ImportError:
        return "QGIS field API unavailable -- presence-gap status not written to the layer."

    status_by_unit = {}
    for e in gap_units:
        status_by_unit[e["unit"]] = "gap"
    for e in covered_units:
        status_by_unit[e["unit"]] = "covered"
    for e in unmatched_units:
        status_by_unit[e["unit"]] = "unmatched"

    fid_by_unit = {r["unit"]: r["__fid__"] for r in rows if "__fid__" in r}

    provider = layer.dataProvider()
    if output_field not in [f.name() for f in layer.fields()]:
        if not provider.addAttributes([QgsField(output_field, QVariant.String)]):
            return f"Could not add field '{output_field}' to the layer."
        layer.updateFields()

    idx = layer.fields().indexOf(output_field)
    if idx < 0:
        return f"Field '{output_field}' not present after creation attempt."

    updates = {
        fid_by_unit[unit]: {idx: status}
        for unit, status in status_by_unit.items()
        if unit in fid_by_unit
    }
    if not provider.changeAttributeValues(updates):
        return f"Could not write presence-gap status into '{output_field}'."
    layer.updateFields()
    return None


@register_tool(
    "calculate_presence_gap",
    "Cross-reference a computed severity/needs index (see calculate_severity_index) against 3W/4W "
    "('who does what where') operational-presence data to find admin units with HIGH severity but "
    "LOW or NO organizational presence -- the classic humanitarian coverage-gap question for "
    "targeting where a response is most under-resourced relative to need. Computes the severity "
    "index internally (same method and indicator handling as calculate_severity_index) from "
    "indicator fields already on a polygon layer, reads the 3W/4W file, and joins the two by admin "
    "unit name (case/whitespace-insensitive match). High-severity units with no match at all in the "
    "3W data are reported separately as unmatched, since that could mean genuinely zero presence or "
    "just a name mismatch between the two datasets -- don't treat it the same as a confirmed zero. "
    "Pass output_field to write each high-severity unit's status ('gap'/'covered'/'unmatched') back "
    "to the layer, then style it directly with apply_categorized_style or place it on "
    "generate_html_dashboard -- do NOT hand-write PyQGIS renderer code for this via "
    "execute_pyqgis_script, use output_field plus the existing styling tools instead. Each of the "
    "three result lists is capped to 50 entries (see the matching _total fields and truncated) -- "
    "output_field still writes every classified unit's status to the layer regardless of the cap.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Polygon layer of admin units with severity indicator fields."},
            "indicator_fields": {"type": "array", "items": {"type": "string"}, "description": "Numeric indicator fields to combine into the severity score."},
            "unit_name_field": {"type": "string", "description": "Field on the polygon layer holding each unit's name/P-code."},
            "presence_file_path": {"type": "string", "description": "Absolute path to the 3W/4W .csv/.xlsx/.xls file."},
            "presence_admin_field": {"type": "string", "description": "Column in the 3W/4W file holding the admin unit name/P-code."},
            "presence_org_field": {"type": "string", "description": "Column in the 3W/4W file holding the organization name."},
            "weights": {"type": "object", "description": "Optional {indicator_field: weight} for the severity score. Defaults to equal."},
            "invert_indicators": {"type": "array", "items": {"type": "string"}, "description": "Indicator fields where a HIGHER raw value means a BETTER situation."},
            "high_severity_classes": {"type": "array", "items": {"type": "integer"}, "description": "Severity classes (1-5) counted as 'high need'. Defaults to [4, 5]."},
            "low_presence_threshold": {"type": "integer", "description": "Organization count strictly below this counts as a presence gap. Defaults to 1 (i.e. zero organizations)."},
            "sheet_name": {"type": "string", "description": "Sheet name if presence_file_path is a multi-sheet Excel file."},
            "delimiter": {"type": "string", "description": "CSV delimiter for presence_file_path. Defaults to ','."},
            "output_field": {"type": "string", "description": "Optional: write each high-severity unit's presence-gap status ('gap'/'covered'/'unmatched') back to the layer under this field name."},
        },
        "required": ["layer_name", "indicator_fields", "unit_name_field", "presence_file_path", "presence_admin_field", "presence_org_field"],
    },
)
def calculate_presence_gap(layer_name, indicator_fields, unit_name_field, presence_file_path, presence_admin_field, presence_org_field,
                            weights=None, invert_indicators=None, high_severity_classes=None, low_presence_threshold=1,
                            sheet_name=None, delimiter=",", output_field=None, confirmed: bool = False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    field_names = [f.name() for f in layer.fields()]
    missing = [f for f in list(indicator_fields) + [unit_name_field] if f not in field_names]
    if missing:
        return {"error": f"Field(s) {missing} not found on '{layer_name}'. Available: {field_names}"}

    # QGIS-008, 2026-09-13 audit -- see calculate_severity_index's identical gate above for
    # the full rationale. Gated on output_field specifically, not the whole function.
    if output_field and not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "calculate_presence_gap",
            "arguments": {
                "layer_name": layer_name, "indicator_fields": indicator_fields,
                "unit_name_field": unit_name_field, "presence_file_path": presence_file_path,
                "presence_admin_field": presence_admin_field, "presence_org_field": presence_org_field,
                "weights": weights, "invert_indicators": invert_indicators,
                "high_severity_classes": high_severity_classes, "low_presence_threshold": low_presence_threshold,
                "sheet_name": sheet_name, "delimiter": delimiter, "output_field": output_field,
                "confirmed": True,
            },
            "code_snippet": f"layer.startEditing()\n# Add/update field '{output_field}' = presence-gap status ('gap'/'covered'/'unmatched') across features\nlayer.commitChanges()",
            "rationale": f"Data Mutation Preview: Add/update field '{output_field}' on layer '{layer_name}' with each high-severity unit's presence-gap status.",
            "message": f"Confirmation required before mutating attribute field '{output_field}' on '{layer_name}'.",
        }

    rows = [{"unit": str(feat[unit_name_field]), "__fid__": feat.id(), **{f: feat[f] for f in indicator_fields}} for feat in layer.getFeatures()]
    severity = _compute_severity_index(rows, list(indicator_fields), weights, invert_indicators)
    if "error" in severity:
        return severity

    high_classes = set(high_severity_classes) if high_severity_classes else {4, 5}
    unknown_classes = high_classes - {1, 2, 3, 4, 5}
    if unknown_classes:
        return {"error": f"high_severity_classes must be within 1-5, got {sorted(unknown_classes)}."}

    if not os.path.exists(presence_file_path):
        return {"error": f"File not found: {presence_file_path}"}

    from .reporting_tools import _read_tabular_rows, _aggregate_3w_presence
    try:
        presence_rows, presence_columns = _read_tabular_rows(presence_file_path, sheet_name=sheet_name, delimiter=delimiter)
    except ImportError:
        return {"error": "pandas and openpyxl are required to read Excel files. Install via qpip, or in the OSGeo4W Shell: python -m pip install pandas openpyxl"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Could not read '{presence_file_path}': {e}"}

    presence_missing = [f for f in [presence_admin_field, presence_org_field] if f not in presence_columns]
    if presence_missing:
        return {"error": f"Field(s) {presence_missing} not found in '{presence_file_path}'. Available columns: {presence_columns}"}

    presence_by_unit, presence_skipped = _aggregate_3w_presence(presence_rows, presence_admin_field, presence_org_field)

    gap_units, covered_units, unmatched_units = [], [], []
    for r in severity["results"]:
        if r["severity_class"] not in high_classes:
            continue
        bucket = presence_by_unit.get(r["unit"].strip().lower())
        org_count = len(bucket["orgs"]) if bucket else 0
        entry = {
            "unit": r["unit"],
            "severity_score": r["severity_score"],
            "severity_class": r["severity_class"],
            "organization_count": org_count,
            "organizations": sorted(bucket["orgs"]) if bucket else [],
        }
        if bucket is None:
            unmatched_units.append(entry)
        elif org_count < low_presence_threshold:
            gap_units.append(entry)
        else:
            covered_units.append(entry)

    gap_units.sort(key=lambda e: e["severity_score"], reverse=True)
    covered_units.sort(key=lambda e: e["severity_score"], reverse=True)
    unmatched_units.sort(key=lambda e: e["severity_score"], reverse=True)

    write_error = None
    if output_field:
        # Full, untruncated lists -- every classified unit needs its status
        # written, not just the ones that end up in the capped response below.
        write_error = _write_presence_gap_status_to_layer(layer, rows, gap_units, covered_units, unmatched_units, output_field)

    gap_capped, gap_total, gap_truncated = _cap_entries(gap_units)
    covered_capped, covered_total, covered_truncated = _cap_entries(covered_units)
    unmatched_capped, unmatched_total, unmatched_truncated = _cap_entries(unmatched_units)

    result = {
        "success": True,
        "method": severity["method"],
        "applied_weights": severity["applied_weights"],
        "high_severity_classes": sorted(high_classes),
        "low_presence_threshold": low_presence_threshold,
        "presence_gap_units": gap_capped,
        "presence_gap_units_total": gap_total,
        "covered_high_severity_units": covered_capped,
        "covered_high_severity_units_total": covered_total,
        "unmatched_high_severity_units": unmatched_capped,
        "unmatched_high_severity_units_total": unmatched_total,
        "truncated": gap_truncated or covered_truncated or unmatched_truncated,
        "excluded_units_missing_data": severity["excluded_units_missing_data"],
        "indicators_with_no_variation": severity["indicators_with_no_variation"],
        "presence_total_rows": len(presence_rows),
        "presence_skipped_rows": presence_skipped,
        "presence_distinct_admin_units": len(presence_by_unit),
    }

    if output_field:
        if write_error:
            result["output_field_warning"] = write_error
        else:
            result["output_field"] = output_field
            result["layer_name"] = layer_name
    return result


def _write_population_to_layer(layer, rows, unit_results, output_field):
    """Adds/updates a numeric field holding each unit's population-in-need
    figure, so it can be styled with apply_graduated_style straight after --
    mirrors _write_scores_to_layer's identical pattern for severity score.
    Units excluded from severity scoring, or with no population data, are
    left unset rather than given a fabricated zero. Returns an error string
    on failure, or None on success -- a write failure downgrades to a
    warning on an otherwise-valid result rather than discarding the figures."""
    try:
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QVariant
    except ImportError:
        return "QGIS field API unavailable -- population not written to the layer."

    pop_by_unit = {r["unit"]: r["population"] for r in unit_results}
    fid_by_unit = {r["unit"]: r["__fid__"] for r in rows if "__fid__" in r}

    provider = layer.dataProvider()
    if output_field not in [f.name() for f in layer.fields()]:
        if not provider.addAttributes([QgsField(output_field, QVariant.Double)]):
            return f"Could not add field '{output_field}' to the layer."
        layer.updateFields()

    idx = layer.fields().indexOf(output_field)
    if idx < 0:
        return f"Field '{output_field}' not present after creation attempt."

    updates = {
        fid_by_unit[unit]: {idx: pop}
        for unit, pop in pop_by_unit.items()
        if unit in fid_by_unit
    }
    if not provider.changeAttributeValues(updates):
        return f"Could not write population into '{output_field}'."
    layer.updateFields()
    return None


@register_tool(
    "calculate_population_in_need",
    "Combines calculate_severity_index's classification with population-per-pixel data to answer "
    "the number every HRP, donor brief, and allocation committee actually quotes -- 'X people in "
    "need in District Y', not just 'District Y is severity class 5'. Computes the severity index "
    "internally (same method and indicator handling as calculate_severity_index) from indicator "
    "fields already on a polygon layer, sums population within each admin unit via zonal statistics "
    "against an already-loaded population raster (same mechanism as estimate_population_exposure, "
    "which this calls internally -- e.g. a layer from fetch_worldpop_population), and reports a "
    "population_in_need total for the high-severity classes plus a population breakdown per severity "
    "class. Closes a gap where getting this number previously required manually chaining "
    "calculate_severity_index and estimate_population_exposure and matching the two up by hand -- "
    "easy to get subtly wrong (double-counting, or forgetting to exclude units calculate_severity_index "
    "itself flagged as missing data). Units excluded from severity scoring (missing indicator data) "
    "are excluded from the total, not silently counted as needy or safe -- same for units the "
    "population raster doesn't cover (no pop_sum value), listed separately rather than treated as "
    "zero population. Pass output_field to write each unit's population figure back to the layer, "
    "then style it directly with apply_graduated_style. Results are capped to 50 units (see "
    "unit_results_total/truncated) -- output_field still writes every unit's figure to the layer "
    "regardless of the cap.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Polygon layer of admin units with severity indicator fields."},
            "indicator_fields": {"type": "array", "items": {"type": "string"}, "description": "Numeric indicator fields to combine into the severity score."},
            "unit_name_field": {"type": "string", "description": "Field on the polygon layer holding each unit's name/P-code."},
            "population_raster_layer": {"type": "string", "description": "A population-per-pixel raster layer already loaded (e.g. from fetch_worldpop_population)."},
            "weights": {"type": "object", "description": "Optional {indicator_field: weight} for the severity score. Defaults to equal."},
            "invert_indicators": {"type": "array", "items": {"type": "string"}, "description": "Indicator fields where a HIGHER raw value means a BETTER situation."},
            "high_severity_classes": {"type": "array", "items": {"type": "integer"}, "description": "Severity classes (1-5) counted toward the population_in_need total. Defaults to [4, 5]."},
            "output_field": {"type": "string", "description": "Optional: write each unit's population figure back to the layer under this field name."},
        },
        "required": ["layer_name", "indicator_fields", "unit_name_field", "population_raster_layer"],
    },
)
def calculate_population_in_need(layer_name, indicator_fields, unit_name_field, population_raster_layer,
                                  weights=None, invert_indicators=None, high_severity_classes=None, output_field=None,
                                  confirmed: bool = False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    field_names = [f.name() for f in layer.fields()]
    missing = [f for f in list(indicator_fields) + [unit_name_field] if f not in field_names]
    if missing:
        return {"error": f"Field(s) {missing} not found on '{layer_name}'. Available: {field_names}"}

    high_classes = set(high_severity_classes) if high_severity_classes else {4, 5}
    unknown_classes = high_classes - {1, 2, 3, 4, 5}
    if unknown_classes:
        return {"error": f"high_severity_classes must be within 1-5, got {sorted(unknown_classes)}."}

    # QGIS-008, 2026-09-13 audit -- see calculate_severity_index's identical gate for the
    # full rationale. Gated on output_field specifically, not the whole function.
    if output_field and not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "calculate_population_in_need",
            "arguments": {
                "layer_name": layer_name, "indicator_fields": indicator_fields,
                "unit_name_field": unit_name_field, "population_raster_layer": population_raster_layer,
                "weights": weights, "invert_indicators": invert_indicators,
                "high_severity_classes": high_severity_classes, "output_field": output_field,
                "confirmed": True,
            },
            "code_snippet": f"layer.startEditing()\n# Add/update field '{output_field}' = population-in-need figure across features\nlayer.commitChanges()",
            "rationale": f"Data Mutation Preview: Add/update field '{output_field}' on layer '{layer_name}' with each unit's population figure.",
            "message": f"Confirmation required before mutating attribute field '{output_field}' on '{layer_name}'.",
        }

    rows = [{"unit": str(feat[unit_name_field]), "__fid__": feat.id(), **{f: feat[f] for f in indicator_fields}} for feat in layer.getFeatures()]
    severity = _compute_severity_index(rows, list(indicator_fields), weights, invert_indicators)
    if "error" in severity:
        return severity

    # Reused purely for its zonal-statistics side effect (adds a "pop_sum"
    # field to `layer`). Its own returned "totals" dict is keyed by the
    # layer's first attribute field, not necessarily unit_name_field, so
    # it isn't trustworthy to match against severity's "unit" keys -- read
    # pop_sum back per-feature by fid instead, below.
    exposure = estimate_population_exposure(population_raster_layer, layer_name)
    if "error" in exposure:
        return exposure

    fid_by_unit = {r["unit"]: r["__fid__"] for r in rows if "__fid__" in r}
    pop_by_fid = {feat.id(): feat["pop_sum"] for feat in layer.getFeatures()}

    unit_results = []
    units_missing_population = []
    class_population = {c: 0.0 for c in range(1, 6)}
    population_in_need = 0.0

    for r in severity["results"]:
        fid = fid_by_unit.get(r["unit"])
        pop = pop_by_fid.get(fid) if fid is not None else None
        if pop is None:
            units_missing_population.append(r["unit"])
            continue
        pop = float(pop)
        class_population[r["severity_class"]] += pop
        if r["severity_class"] in high_classes:
            population_in_need += pop
        unit_results.append({
            "unit": r["unit"],
            "severity_score": r["severity_score"],
            "severity_class": r["severity_class"],
            "population": pop,
        })

    write_error = None
    if output_field:
        # Full, untruncated list -- every unit needs its figure written, not
        # just the ones that end up in the capped response below.
        write_error = _write_population_to_layer(layer, rows, unit_results, output_field)

    unit_results_capped, unit_results_total, truncated = _cap_entries(unit_results)

    result = {
        "success": True,
        "method": severity["method"],
        "applied_weights": severity["applied_weights"],
        "high_severity_classes": sorted(high_classes),
        "population_raster_layer": population_raster_layer,
        "population_in_need": round(population_in_need, 1),
        "population_by_severity_class": {str(c): round(v, 1) for c, v in class_population.items()},
        "unit_results": unit_results_capped,
        "unit_results_total": unit_results_total,
        "truncated": truncated,
        "units_missing_population_data": units_missing_population,
        "excluded_units_missing_indicator_data": severity["excluded_units_missing_data"],
        "indicators_with_no_variation": severity["indicators_with_no_variation"],
    }

    if output_field:
        if write_error:
            result["output_field_warning"] = write_error
        else:
            result["output_field"] = output_field
            result["layer_name"] = layer_name
    return result


def _write_damage_severity_to_layer(layer, rows, unit_results, output_field):
    """Adds/updates a numeric field holding each unit's damage-severity score,
    so it can be styled with apply_graduated_style straight after -- mirrors
    _write_scores_to_layer's identical pattern. Returns an error string on
    failure, or None on success."""
    try:
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QVariant
    except ImportError:
        return "QGIS field API unavailable -- scores not written to the layer."

    score_by_unit = {r["unit"]: r["severity_score"] for r in unit_results}
    fid_by_unit = {r["unit"]: r["__fid__"] for r in rows if "__fid__" in r}

    provider = layer.dataProvider()
    if output_field not in [f.name() for f in layer.fields()]:
        if not provider.addAttributes([QgsField(output_field, QVariant.Double)]):
            return f"Could not add field '{output_field}' to the layer."
        layer.updateFields()

    idx = layer.fields().indexOf(output_field)
    if idx < 0:
        return f"Field '{output_field}' not present after creation attempt."

    updates = {
        fid_by_unit[unit]: {idx: score}
        for unit, score in score_by_unit.items()
        if unit in fid_by_unit
    }
    if not provider.changeAttributeValues(updates):
        return f"Could not write scores into '{output_field}'."
    layer.updateFields()
    return None


def _build_polygon_index(admin_layer):
    """Builds the QgsSpatialIndex + feature-id map that _count_points_in_polygons
    needs, as a standalone step so a caller counting against the SAME admin_layer
    many times (e.g. analyze_incident_trend, once per time bucket -- PERF-003,
    2026-09-13 audit) can build it once and reuse it, instead of paying
    O(admin features) index/dict construction again on every call."""
    from qgis.core import QgsSpatialIndex

    index = QgsSpatialIndex(admin_layer.getFeatures())
    admin_features_by_id = {f.id(): f for f in admin_layer.getFeatures()}
    return index, admin_features_by_id


def _count_points_in_polygons_indexed(index, admin_features_by_id, point_geometries):
    """Same counting logic as _count_points_in_polygons, against an
    already-built (index, admin_features_by_id) pair from _build_polygon_index."""
    counts = {fid: 0 for fid in admin_features_by_id}

    for geom in point_geometries:
        if geom is None or geom.isEmpty():
            continue
        for fid in index.intersects(geom.boundingBox()):
            if admin_features_by_id[fid].geometry().contains(geom):
                counts[fid] += 1
                break

    return counts


def _count_points_in_polygons(admin_layer, point_geometries):
    """Counts how many of point_geometries fall within each admin_layer
    feature, keyed by admin feature id. Takes point QgsGeometry objects
    directly (callers pass footprint CENTROIDS, not raw polygon geometries
    -- testing full-polygon containment would undercount buildings that
    straddle an admin boundary, attributing them to neither unit). Mirrors
    the QgsSpatialIndex + bbox-then-contains pattern already used by
    obfuscate_sensitive_points' admin_unit_snap method.

    Single-call convenience wrapper around _build_polygon_index +
    _count_points_in_polygons_indexed -- callers that count against the same
    admin_layer more than once should call those two directly instead, to
    avoid rebuilding the index every time (see analyze_incident_trend)."""
    index, admin_features_by_id = _build_polygon_index(admin_layer)
    return _count_points_in_polygons_indexed(index, admin_features_by_id, point_geometries)


@register_tool(
    "calculate_damage_exposure_severity",
    "Composite post-crisis damage-and-exposure assessment, in the same thin-composite pattern as "
    "calculate_population_in_need: combines calculate_raster_change_detection's before/after pixel "
    "diff with fetch_building_footprints' building counts (and, optionally, a user-supplied "
    "hazard-intensity raster -- e.g. a shake-intensity or flood-depth layer) into one severity score "
    "per admin unit, plus a total building count in the high-severity units. Inspired by UNDP "
    "RAPIDA's rapid post-crisis assessment approach, deliberately scoped down to what's actually "
    "available here -- no seismic/hazard modeling, no social-media/night-light signal ingestion (see "
    "docs/archive/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md B.3 for that gap; this tool doesn't close it, "
    "just narrows it). Change magnitude is the MEAN absolute pixel difference within each unit, not "
    "the raw sum, which would just scale with unit area/pixel count. Building exposure counts "
    "footprint centroids falling within each unit -- units the change-detection raster doesn't cover "
    "are excluded from the severity index (never imputed as zero), matching "
    "calculate_severity_index's own rule; units with genuinely zero buildings still get a real 0, "
    "since that's an actual count, not missing data. Pass output_field to write each unit's severity "
    "score back to the layer for apply_graduated_style. Never hand-write this composition via "
    "execute_pyqgis_script -- use this tool.",
    {
        "type": "object",
        "properties": {
            "admin_layer": {"type": "string", "description": "Polygon layer of admin units."},
            "unit_name_field": {"type": "string", "description": "Field holding each unit's name/P-code."},
            "raster_before": {"type": "string", "description": "Pre-event raster layer (see calculate_raster_change_detection)."},
            "raster_after": {"type": "string", "description": "Post-event raster layer."},
            "building_footprints_layer": {"type": "string", "description": "Building footprint polygon layer, e.g. from fetch_building_footprints."},
            "hazard_intensity_raster": {"type": "string", "description": "Optional hazard-intensity raster (shake intensity, flood depth, etc.) to weight the severity score alongside raw change magnitude."},
            "high_severity_classes": {"type": "array", "items": {"type": "integer"}, "description": "Severity classes (1-5) counted toward the exposed-building total. Defaults to [4, 5]."},
            "output_field": {"type": "string", "description": "Optional: write each unit's severity score back to the layer under this field name."},
        },
        "required": ["admin_layer", "unit_name_field", "raster_before", "raster_after", "building_footprints_layer"],
    },
)
def calculate_damage_exposure_severity(admin_layer, unit_name_field, raster_before, raster_after,
                                        building_footprints_layer, hazard_intensity_raster=None,
                                        high_severity_classes=None, output_field=None,
                                        confirmed: bool = False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(admin_layer)
    if layer is None:
        return {"error": f"Layer '{admin_layer}' not found"}
    if unit_name_field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{unit_name_field}' not found on '{admin_layer}'. Available: {[f.name() for f in layer.fields()]}"}

    footprints = _find_layer_by_name(building_footprints_layer)
    if footprints is None:
        return {"error": f"Layer '{building_footprints_layer}' not found"}

    high_classes = set(high_severity_classes) if high_severity_classes else {4, 5}
    unknown_classes = high_classes - {1, 2, 3, 4, 5}
    if unknown_classes:
        return {"error": f"high_severity_classes must be within 1-5, got {sorted(unknown_classes)}."}

    # QGIS-008, 2026-09-13 audit -- see calculate_severity_index's identical gate for the
    # full rationale. Gated on output_field specifically, not the whole function.
    if output_field and not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "calculate_damage_exposure_severity",
            "arguments": {
                "admin_layer": admin_layer, "unit_name_field": unit_name_field,
                "raster_before": raster_before, "raster_after": raster_after,
                "building_footprints_layer": building_footprints_layer,
                "hazard_intensity_raster": hazard_intensity_raster,
                "high_severity_classes": high_severity_classes, "output_field": output_field,
                "confirmed": True,
            },
            "code_snippet": f"layer.startEditing()\n# Add/update field '{output_field}' = damage-exposure severity score across features\nlayer.commitChanges()",
            "rationale": f"Data Mutation Preview: Add/update field '{output_field}' on layer '{admin_layer}' with each unit's damage-exposure severity score.",
            "message": f"Confirmation required before mutating attribute field '{output_field}' on '{admin_layer}'.",
        }

    change = calculate_raster_change_detection(raster_before, raster_after)
    if "error" in change:
        return change

    # QgsZonalStatistics lives in qgis.analysis, not qgis.core (QGIS 4.2.2: "cannot import name 'QgsZonalStatistics' from
    # 'qgis.core'", found by the 2026-10-03 external audit; raster_tools.py already imports it from the right module).
    from qgis.analysis import QgsZonalStatistics
    stat_enum = getattr(QgsZonalStatistics, "Statistic", QgsZonalStatistics)
    mean_flag = getattr(stat_enum, "Mean", None)
    if mean_flag is None:
        return {"error": "Could not resolve QgsZonalStatistics.Mean in this QGIS version."}

    change_raster = _find_layer_by_name(change["layer_name"])
    zonal = QgsZonalStatistics(layer, change_raster, "chg_", 1, mean_flag)
    zonal.calculateStatistics(None)
    if layer.fields().indexFromName("chg_mean") < 0:
        return {"error": "Zonal statistics ran but no 'chg_mean' field was created -- check admin_layer overlaps the change-detection raster."}

    intensity_raster = None
    if hazard_intensity_raster:
        intensity_raster = _find_layer_by_name(hazard_intensity_raster)
        if intensity_raster is None:
            return {"error": f"Layer '{hazard_intensity_raster}' not found"}
        zonal2 = QgsZonalStatistics(layer, intensity_raster, "hzd_", 1, mean_flag)
        zonal2.calculateStatistics(None)
        if layer.fields().indexFromName("hzd_mean") < 0:
            return {"error": "Zonal statistics ran but no 'hzd_mean' field was created -- check hazard_intensity_raster overlaps admin_layer."}

    footprint_centroids = (feat.geometry().centroid() for feat in footprints.getFeatures())
    building_counts = _count_points_in_polygons(layer, footprint_centroids)

    rows = []
    for feat in layer.getFeatures():
        row = {"unit": str(feat[unit_name_field]), "__fid__": feat.id(), "change_magnitude": feat["chg_mean"]}
        if intensity_raster is not None:
            row["hazard_intensity"] = feat["hzd_mean"]
        rows.append(row)

    indicators = ["change_magnitude"] + (["hazard_intensity"] if intensity_raster is not None else [])
    severity = _compute_severity_index(rows, indicators)
    if "error" in severity:
        return severity

    fid_by_unit = {r["unit"]: r["__fid__"] for r in rows if "__fid__" in r}
    unit_results = []
    class_buildings = {c: 0 for c in range(1, 6)}
    buildings_in_high_severity = 0
    for r in severity["results"]:
        fid = fid_by_unit.get(r["unit"])
        count = building_counts.get(fid, 0)
        class_buildings[r["severity_class"]] += count
        if r["severity_class"] in high_classes:
            buildings_in_high_severity += count
        unit_results.append({
            "unit": r["unit"],
            "severity_score": r["severity_score"],
            "severity_class": r["severity_class"],
            "building_count": count,
        })

    write_error = None
    if output_field:
        write_error = _write_damage_severity_to_layer(layer, rows, unit_results, output_field)

    unit_results_capped, unit_results_total, truncated = _cap_entries(unit_results)

    result = {
        "success": True,
        "method": severity["method"],
        "applied_weights": severity["applied_weights"],
        "high_severity_classes": sorted(high_classes),
        "change_detection_layer": change["layer_name"],
        "hazard_intensity_used": intensity_raster is not None,
        "buildings_in_high_severity_areas": buildings_in_high_severity,
        "building_count_by_severity_class": {str(c): v for c, v in class_buildings.items()},
        "unit_results": unit_results_capped,
        "unit_results_total": unit_results_total,
        "truncated": truncated,
        "excluded_units_missing_data": severity["excluded_units_missing_data"],
        "indicators_with_no_variation": severity["indicators_with_no_variation"],
    }

    if output_field:
        if write_error:
            result["output_field_warning"] = write_error
        else:
            result["output_field"] = output_field
            result["layer_name"] = admin_layer
    return result


@register_tool(
    "forecast_trend",
    "Project a simple linear trend forward from historical numeric data already in a layer's "
    "attribute table (e.g. case counts, incident counts, or any numeric field over time). Returns "
    "a mathematical trend projection with a stated fit confidence -- NOT a certain prediction; "
    "always present it as a projection, not a fact. Optionally group by a categorical field to get "
    "one forecast per group (e.g. one per district) instead of a single overall forecast.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "date_field": {"type": "string", "description": "Field holding the date/time of each observation."},
            "value_field": {"type": "string", "description": "Numeric field to forecast."},
            "periods_ahead": {"type": "integer", "description": "How many future points to project. Defaults to 3."},
            "group_by_field": {"type": "string", "description": "Optional categorical field -- returns one forecast per distinct value instead of one overall forecast."},
        },
        "required": ["layer_name", "date_field", "value_field"],
    },
)
def forecast_trend(layer_name, date_field, value_field, periods_ahead=3, group_by_field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    field_names = [f.name() for f in layer.fields()]
    if date_field not in field_names:
        return {"error": f"Field '{date_field}' not found on '{layer_name}'. Available: {field_names}"}
    if value_field not in field_names:
        return {"error": f"Field '{value_field}' not found on '{layer_name}'. Available: {field_names}"}
    if group_by_field and group_by_field not in field_names:
        return {"error": f"Field '{group_by_field}' not found on '{layer_name}'. Available: {field_names}"}
    if not (1 <= periods_ahead <= 24):
        return {"error": "periods_ahead must be between 1 and 24."}

    groups = {}
    for feat in layer.getFeatures():
        d = _parse_date(feat[date_field])
        raw_value = feat[value_field]
        if d is None or not isinstance(raw_value, (int, float)):
            continue
        key = str(feat[group_by_field]) if group_by_field else "__all__"
        series = groups.setdefault(key, {"dates": [], "values": []})
        series["dates"].append(d)
        series["values"].append(float(raw_value))

    if not groups:
        return {"error": f"No usable (date, numeric value) pairs found in '{date_field}'/'{value_field}'."}

    results = {key: _forecast_series(s["dates"], s["values"], periods_ahead) for key, s in groups.items()}

    if group_by_field:
        return {"success": True, "grouped_by": group_by_field, "forecasts": results}
    return results["__all__"]


@register_tool(
    "analyze_incident_trend",
    "Is incident density in each zone rising or falling over time -- e.g. security incidents by "
    "district over the last few months. hotspot_analysis answers 'where is density high right now' "
    "(a single snapshot); this answers 'is it getting worse here.' A thin composite, not a new "
    "statistic: buckets point_layer's incidents into period_days-sized time periods per zone_layer "
    "feature, then feeds each zone's (period, count) series into the same _forecast_series/"
    "_linear_regression math forecast_trend already uses -- so results carry the same "
    "fit_confidence/trend_direction framing, and the same 'present as a projection, not a certain "
    "fact' rule applies. Needs at least 3 time periods of data to fit a trend (i.e. the date range "
    "in point_layer must span at least 3x period_days) -- returns a clear error naming how much "
    "data is actually available if not. A zone with zero incidents in every period is a valid, "
    "confidently-flat result, not an error.",
    {
        "type": "object",
        "properties": {
            "point_layer": {"type": "string", "description": "Point layer of incidents, e.g. the shared 'Incidents' layer from add_incident_point."},
            "date_field": {"type": "string", "description": "Date field on point_layer."},
            "zone_layer": {"type": "string", "description": "Polygon layer of zones to analyze per-zone trend within (e.g. districts, or a hand-drawn area of interest)."},
            "zone_name_field": {"type": "string", "description": "Field on zone_layer holding each zone's name."},
            "period_days": {"type": "integer", "description": "Size of each time bucket in days. Defaults to 30."},
            "periods_ahead": {"type": "integer", "description": "How many future periods to project per zone. Defaults to 1."},
        },
        "required": ["point_layer", "date_field", "zone_layer", "zone_name_field"],
    },
)
def analyze_incident_trend(point_layer, date_field, zone_layer, zone_name_field, period_days=30, periods_ahead=1):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if period_days <= 0:
        return {"error": "period_days must be positive."}
    if not (1 <= periods_ahead <= 24):
        return {"error": "periods_ahead must be between 1 and 24."}

    layer = _find_layer_by_name(point_layer)
    if layer is None:
        return {"error": f"Layer '{point_layer}' not found"}
    if date_field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{date_field}' not found on '{point_layer}'. Available: {[f.name() for f in layer.fields()]}"}

    zones = _find_layer_by_name(zone_layer)
    if zones is None:
        return {"error": f"Layer '{zone_layer}' not found"}
    if zone_name_field not in [f.name() for f in zones.fields()]:
        return {"error": f"Field '{zone_name_field}' not found on '{zone_layer}'. Available: {[f.name() for f in zones.fields()]}"}

    dated_geoms = []
    for feat in layer.getFeatures():
        d = _parse_date(feat[date_field])
        geom = feat.geometry()
        if d is None or geom is None or geom.isEmpty():
            continue
        dated_geoms.append((d, geom))

    if not dated_geoms:
        return {"error": f"No usable (date, geometry) pairs found in '{point_layer}' via '{date_field}'."}

    dates = [d for d, g in dated_geoms]
    geoms = [g for d, g in dated_geoms]
    first_date, last_date, num_periods, bucket_indices = _bucket_dates_by_period(dates, period_days)
    if num_periods < 3:
        return {
            "error": f"Only {num_periods} period(s) of data available at period_days={period_days} "
                     f"(date range {first_date.isoformat()} to {last_date.isoformat()}) -- need at least 3 "
                     "periods to fit a trend. Use a smaller period_days, or wait for more data."
        }

    buckets = {}
    for idx, geom in zip(bucket_indices, geoms):
        buckets.setdefault(idx, []).append(geom)

    zone_features = list(zones.getFeatures())
    zone_names = {f.id(): str(f[zone_name_field]) for f in zone_features}

    # PERF-003, 2026-09-13 audit: was calling _count_points_in_polygons(zones, ...) once
    # per bucket, rebuilding the same QgsSpatialIndex + feature-id map against the same,
    # unchanged zones layer every time -- O(periods x zones) of redundant index
    # construction for a fine-grained/long-range analysis. Built once here instead.
    zone_index, zone_features_by_id = _build_polygon_index(zones)
    bucket_zone_counts = {
        idx: _count_points_in_polygons_indexed(zone_index, zone_features_by_id, geoms)
        for idx, geoms in buckets.items()
    }

    results = []
    for fid, zone_name in zone_names.items():
        dates_series, values_series = [], []
        for idx in range(num_periods):
            period_start = first_date + datetime.timedelta(days=idx * period_days)
            count = bucket_zone_counts.get(idx, {}).get(fid, 0)
            dates_series.append(period_start)
            values_series.append(float(count))

        forecast = _forecast_series(dates_series, values_series, periods_ahead)
        if "error" in forecast:
            continue
        results.append({
            "zone": zone_name,
            "most_recent_period_count": int(values_series[-1]),
            "trend_direction": forecast["trend_direction"],
            "fit_confidence": forecast["fit_confidence"],
            "fit_quality_r_squared": forecast["fit_quality_r_squared"],
            "projections": forecast["projections"],
        })

    results.sort(key=lambda e: e["most_recent_period_count"], reverse=True)
    results_capped, results_total, truncated = _cap_entries(results)

    return {
        "success": True,
        "period_days": period_days,
        "periods_analyzed": num_periods,
        "date_range": {"start": first_date.isoformat(), "end": last_date.isoformat()},
        "results": results_capped,
        "results_total": results_total,
        "truncated": truncated,
        "note": (
            "The most recent period may be partial (less than a full period_days if the data's date "
            "range doesn't divide evenly) -- treat most_recent_period_count for that period as a "
            "possible undercount, not a confirmed drop."
        ),
    }
