# -*- coding: utf-8 -*-
"""
Weighted survey indicators per area, with small-cell suppression (H6, docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md).

Turns household/individual survey records into one figure per area (admin unit, camp, ...): the weighted share of respondents with a
yes/no answer, or the weighted mean of a numeric answer, with a confidence interval. Groups with fewer than `min_n` respondents are
SUPPRESSED (no estimate is returned), because a figure built on a handful of households is both unreliable and, in a small
community, potentially identifying (see SECURITY.md / the sensitivity tooling for the project's disclosure stance).

Method, and what it does not do. Weights are used as given (the survey's own sampling or post-stratification weights); the tool does
not compute them. Precision uses Kish's effective sample size n_eff = (sum w)^2 / sum w^2 in a simple-random-sampling formula
(Wilson interval for a proportion, normal interval for a mean). That DOES reflect unequal weights but IGNORES clustering and
stratification, so intervals from a cluster survey are too narrow unless a design effect is supplied (`design_effect` divides n_eff).
min_n defaults to 30 as a common rule of thumb and is NOT a disclosure-control standard: the owner's data-protection policy decides
the real threshold. Records with a missing indicator or a missing/non-positive weight are excluded and counted, never imputed.
Pure logic is unit tested offline; the layer work needs QGIS (tests/test_survey_tools_live.py, written without a local QGIS).
"""
import math
import statistics

from .registry import register_tool

try:
    from qgis.core import QgsFeature, QgsProject, QgsVectorLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

DEFAULT_MIN_N = 30
_TRUE_WORDS = {"1", "true", "yes", "y", "t"}
_FALSE_WORDS = {"0", "false", "no", "n", "f"}
KINDS = ("proportion", "mean")


# ---------------------------------------------------------------- pure --

def to_number(value):
    """float or None (missing, non-numeric, NaN, bool). Pure."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def parse_binary(value, positive_values=None):
    """1.0 / 0.0 / None for a yes/no answer. With positive_values, those values (compared as lower-case text) are 1 and every other
    non-empty value is 0; without, the usual 1/0, yes/no, true/false spellings are understood and anything else is None. Pure."""
    if value is None or str(value).strip() == "" or str(value).strip().upper() == "NULL":
        return None
    text = str(value).strip().lower()
    if positive_values:
        return 1.0 if text in {str(p).strip().lower() for p in positive_values} else 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if text in _TRUE_WORDS or text in {"1.0"}:
        return 1.0
    if text in _FALSE_WORDS or text in {"0.0"}:
        return 0.0
    return None


def kish_effective_n(weights):
    """(sum w)^2 / sum w^2. Equals the count when all weights are equal. Pure."""
    total = sum(weights)
    squares = sum(w * w for w in weights)
    return (total * total) / squares if squares > 0 else 0.0


def wilson_interval(p, n_eff, z):
    """(low, high) Wilson score interval for a proportion p with effective sample size n_eff. Pure."""
    if n_eff <= 0:
        return (None, None)
    denom = 1.0 + z * z / n_eff
    centre = (p + z * z / (2.0 * n_eff)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n_eff + z * z / (4.0 * n_eff * n_eff)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def weighted_mean_interval(values, weights, z, design_effect=1.0):
    """(mean, low, high, n_eff) for a weighted mean, using the weighted variance and Kish n_eff / design_effect. Pure."""
    total = sum(weights)
    mean = sum(v * w for v, w in zip(values, weights)) / total
    n_eff = kish_effective_n(weights) / design_effect
    var = sum(w * (v - mean) ** 2 for v, w in zip(values, weights)) / total
    if n_eff <= 1:
        return (mean, None, None, n_eff)
    half = z * math.sqrt(var / n_eff)
    return (mean, mean - half, mean + half, n_eff)


def validate_options(kind, min_n, confidence, design_effect):
    """Error text for an invalid option, else None. Pure."""
    if kind not in KINDS:
        return f"kind must be one of {list(KINDS)}."
    try:
        if int(min_n) < 1:
            return "min_n must be 1 or more."
        if not 0.5 <= float(confidence) < 1.0:
            return "confidence must be at least 0.5 and below 1 (e.g. 0.95)."
        if float(design_effect) < 1.0:
            return "design_effect must be 1 or more (1 = no clustering adjustment)."
    except (TypeError, ValueError):
        return "min_n, confidence and design_effect must be numbers."
    return None


def aggregate(records, kind="proportion", min_n=DEFAULT_MIN_N, confidence=0.95, design_effect=1.0, positive_values=None):
    """Per-group estimates from records ({'group', 'value', 'weight'}; weight None = unweighted, counted as 1). Pure.

    Returns {'groups': [...], 'excluded': {...}}; a group below min_n respondents has suppressed=True and no estimate."""
    z = statistics.NormalDist().inv_cdf((1.0 + float(confidence)) / 2.0)
    excluded = {"missing_group": 0, "missing_or_invalid_value": 0, "invalid_weight": 0}
    by_group = {}
    for rec in records:
        group = rec.get("group")
        if group is None or str(group).strip() == "":
            excluded["missing_group"] += 1
            continue
        value = parse_binary(rec.get("value"), positive_values) if kind == "proportion" else to_number(rec.get("value"))
        if value is None:
            excluded["missing_or_invalid_value"] += 1
            continue
        weight = rec.get("weight", 1.0)
        if weight is not None and weight != 1.0:
            weight = to_number(weight)
            if weight is None or weight <= 0:
                excluded["invalid_weight"] += 1
                continue
        by_group.setdefault(str(group), []).append((value, 1.0 if weight is None else float(weight)))

    groups = []
    for name in sorted(by_group):
        pairs = by_group[name]
        n = len(pairs)
        entry = {"group": name, "respondents": n, "suppressed": n < int(min_n)}
        if entry["suppressed"]:
            entry["respondents"] = f"<{int(min_n)}"
            entry["note"] = f"Fewer than {int(min_n)} respondents: no estimate is given."
            groups.append(entry)
            continue
        values, weights = [v for v, _w in pairs], [w for _v, w in pairs]
        if kind == "proportion":
            p = sum(v * w for v, w in pairs) / sum(weights)
            n_eff = kish_effective_n(weights) / float(design_effect)
            low, high = wilson_interval(p, n_eff, z)
            entry.update({"estimate": round(p, 4), "ci_low": None if low is None else round(low, 4),
                          "ci_high": None if high is None else round(high, 4)})
        else:
            mean, low, high, n_eff = weighted_mean_interval(values, weights, z, float(design_effect))
            entry.update({"estimate": round(mean, 4), "ci_low": None if low is None else round(low, 4),
                          "ci_high": None if high is None else round(high, 4)})
        entry["effective_n"] = round(n_eff, 1)
        groups.append(entry)
    return {"groups": groups, "excluded": {k: v for k, v in excluded.items() if v}}


# ---------------------------------------------------------------- QGIS --

def _layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


@register_tool(
    "aggregate_survey_indicator",
    "Summarise survey records into one figure per area (admin unit, camp, ...): the weighted share of respondents answering yes "
    "(kind='proportion') or the weighted mean of a numeric answer (kind='mean'), each with a confidence interval. Groups with fewer "
    "than min_n respondents (default 30) are SUPPRESSED -- no estimate is returned -- because a figure from a handful of households "
    "is unreliable and can identify people in a small community; the real threshold is the organisation's data-protection policy, "
    "so ask for it if it matters. Uses the survey's own weights as given (weight_field); intervals use Kish's effective sample size "
    "and IGNORE clustering and stratification, so for a cluster survey supply design_effect or treat the intervals as too narrow. "
    "Records with a missing answer or an invalid weight are excluded and counted, never imputed. Optionally creates a table layer "
    "of the results that can be joined to admin polygons.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Layer or table of survey records (one row per respondent/household)."},
            "group_field": {"type": "string", "description": "Field naming the area/stratum each record belongs to."},
            "indicator_field": {"type": "string", "description": "Field with the answer: yes/no-style for a proportion, numeric for a mean."},
            "kind": {"type": "string", "enum": list(KINDS), "description": "'proportion' (default) or 'mean'."},
            "positive_values": {"type": "array", "items": {"type": "string"}, "description": "For a proportion: the answers that count as 'yes' (e.g. ['No access'] to measure lack of access). Default: the usual 1/yes/true spellings."},
            "weight_field": {"type": "string", "description": "Optional numeric survey-weight field; omit for unweighted."},
            "min_n": {"type": "integer", "description": f"Minimum respondents per group, default {DEFAULT_MIN_N}. Smaller groups are suppressed."},
            "confidence": {"type": "number", "description": "Confidence level of the intervals, default 0.95."},
            "design_effect": {"type": "number", "description": "Design effect from the survey design (>= 1); divides the effective sample size. Default 1 (no clustering adjustment)."},
            "output_table_name": {"type": "string", "description": "Optional name for a results table layer."},
        },
        "required": ["layer_name", "group_field", "indicator_field"],
    },
)
def aggregate_survey_indicator(layer_name, group_field, indicator_field, kind="proportion", positive_values=None, weight_field=None,
                               min_n=DEFAULT_MIN_N, confidence=0.95, design_effect=1.0, output_table_name=None):
    problem = validate_options(kind, min_n, confidence, design_effect)
    if problem:
        return {"error": problem}
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not hasattr(layer, "getFeatures"):
        return {"error": f"'{layer_name}' must be a vector layer or table."}
    names = [f.name() for f in layer.fields()]
    for label, field in (("group_field", group_field), ("indicator_field", indicator_field), ("weight_field", weight_field)):
        if field is not None and field not in names:
            return {"error": f"{label} '{field}' not found in '{layer_name}'. Fields: {names}"}

    records = []
    for feat in layer.getFeatures():
        rec = {"group": feat[group_field], "value": feat[indicator_field]}
        rec["weight"] = feat[weight_field] if weight_field else None
        records.append(rec)
    out = aggregate(records, kind, min_n, confidence, design_effect, positive_values)

    shown = [g for g in out["groups"] if not g["suppressed"]]
    result = {
        "success": True,
        "kind": kind,
        "groups": out["groups"],
        "groups_reported": len(shown),
        "groups_suppressed": len(out["groups"]) - len(shown),
        "excluded_records": out["excluded"],
        "method": ("weighted share" if kind == "proportion" else "weighted mean") + f", {float(confidence) * 100:g}% interval"
                  + (" (Wilson, Kish effective n)" if kind == "proportion" else " (normal, Kish effective n)")
                  + f", design effect {float(design_effect):g}; clustering and stratification are not otherwise modelled",
        "min_n": int(min_n),
        "weights": f"field '{weight_field}' used as given" if weight_field else "none (unweighted)",
    }
    if kind == "proportion" and positive_values:
        result["counted_as_yes"] = list(positive_values)
    if not out["groups"]:
        result["warning"] = "No usable records: every record was excluded (see excluded_records)."
    if result["groups_suppressed"]:
        result["suppression_note"] = (f"{result['groups_suppressed']} group(s) have fewer than {int(min_n)} respondents and are not "
                                      "reported. Do not infer their values from totals or neighbouring groups.")
    if output_table_name and shown:
        table = QgsVectorLayer("None?field=group:string&field=respondents:integer&field=estimate:double&field=ci_low:double"
                               "&field=ci_high:double&field=effective_n:double", output_table_name, "memory")
        feats = []
        for g in shown:
            f = QgsFeature(table.fields())
            f.setAttributes([g["group"], g["respondents"], g["estimate"], g["ci_low"], g["ci_high"], g["effective_n"]])
            feats.append(f)
        table.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(table)
        result["table_layer"] = output_table_name
        result["table_note"] = "Suppressed groups are left out of the table."
    return result
