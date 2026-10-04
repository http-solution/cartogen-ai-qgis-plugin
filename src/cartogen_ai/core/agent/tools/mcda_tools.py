# -*- coding: utf-8 -*-
"""
Multi-criteria ranking of areas, with a check that the ranking is not just an artefact of the weights (H5,
docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md).

calculate_severity_index already builds a 0-1 composite for admin units. This tool is the general version for any vector layer and
any criteria: each criterion says which end of its scale gets priority (`direction`), values are min-max scaled to 0-1, scores are
the weighted sum, and units are ranked (ties share a rank). Because the weights are a judgement call, it then re-ranks many times
with the weights randomly perturbed and reports, per unit, the best and worst rank it reached and (for a top-k cut) the share of
trials in which it stayed in the top k. A unit whose rank barely moves is a robust priority; one that swings widely is a result of
the chosen weights, and that is what a decision maker should be told.

Units are identified by feature id, not by name, so duplicate names cannot merge two units. A unit missing any criterion value is
excluded and listed, never imputed. The perturbation is a sensitivity check on WEIGHTS only: it says nothing about errors in the
data, the choice of criteria, or the min-max scaling. Pure logic is unit tested offline; the layer work needs QGIS
(tests/test_mcda_tools_live.py, written without a local QGIS).
"""
import random

from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value
from .humanitarian_style import look_hint

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

DIRECTIONS = ("higher", "lower")
DEFAULT_TRIALS = 500
MAX_TRIALS = 5000
_RESPONSE_CAP = 50


# ---------------------------------------------------------------- pure --

def validate_criteria(criteria):
    """Error text for an unusable criteria list, else None. Pure. Each criterion: {field, weight>0, direction in DIRECTIONS}."""
    if not isinstance(criteria, list) or len(criteria) < 2:
        return "criteria must be a list of at least two {field, weight, direction} objects."
    seen = set()
    for c in criteria:
        if not isinstance(c, dict) or not c.get("field"):
            return "every criterion needs a 'field'."
        if c["field"] in seen:
            return f"criterion '{c['field']}' appears more than once."
        seen.add(c["field"])
        try:
            if float(c.get("weight", 1.0)) <= 0:
                return f"criterion '{c['field']}' needs a weight above zero."
        except (TypeError, ValueError):
            return f"criterion '{c['field']}' has a non-numeric weight."
        if c.get("direction", "higher") not in DIRECTIONS:
            return f"criterion '{c['field']}': direction must be one of {list(DIRECTIONS)} (which end of the scale gets priority)."
    return None


def to_number(value):
    """float or None (missing, non-numeric, NaN, bool). Pure."""
    if value is None or isinstance(value, bool):
        return None
    # A NULL read from a QGIS layer arrives as a QVariant, not None; depending on the binding float() of it can return 0.0 instead of
    # raising, which would turn a missing value into a real zero. Ask the variant itself.
    is_null = getattr(value, "isNull", None)
    if callable(is_null):
        try:
            if is_null():
                return None
        except Exception:
            pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def normalise(values, direction="higher"):
    """Min-max scale to 0-1 so that 1 always means highest priority. Returns (scaled, had_variation). A column with no variation
    scales to all 0.0 and had_variation False (it cannot discriminate between units). Pure."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.0 for _ in values], False
    scaled = [(v - lo) / (hi - lo) for v in values]
    if direction == "lower":
        scaled = [1.0 - s for s in scaled]
    return scaled, True


def normalise_weights(weights):
    """Weights scaled to sum to 1. Pure."""
    total = float(sum(weights))
    return [w / total for w in weights]


def weighted_scores(columns, weights):
    """Per-unit weighted sum of already-scaled columns (list of lists, one per criterion). Pure."""
    n = len(columns[0])
    return [sum(col[i] * w for col, w in zip(columns, weights)) for i in range(n)]


def rank(scores):
    """Competition ranks (1 = highest score); equal scores share the best rank. Pure."""
    order = sorted(scores, reverse=True)
    first = {}
    for position, s in enumerate(order, 1):
        first.setdefault(s, position)
    return [first[s] for s in scores]


def stability(columns, weights, trials=DEFAULT_TRIALS, perturbation=0.2, seed=0, top_k=None):
    """Re-rank `trials` times with each weight multiplied by a random factor in [1-perturbation, 1+perturbation] (then renormalised)
    and report per unit {rank_min, rank_max, top_k_share}. Reproducible for a seed. Pure."""
    n = len(columns[0])
    rng = random.Random(seed)
    best, worst, in_top = [n + 1] * n, [0] * n, [0] * n
    for _ in range(trials):
        w = normalise_weights([base * (1.0 + rng.uniform(-perturbation, perturbation)) for base in weights])
        ranks = rank(weighted_scores(columns, w))
        for i, r in enumerate(ranks):
            best[i] = min(best[i], r)
            worst[i] = max(worst[i], r)
            if top_k is not None and r <= top_k:
                in_top[i] += 1
    return [{"rank_min": best[i], "rank_max": worst[i],
             "top_k_share": (round(in_top[i] / trials, 3) if top_k is not None else None)} for i in range(n)]


def evaluate(rows, criteria, trials=DEFAULT_TRIALS, perturbation=0.2, seed=0, top_k=None):
    """Rank rows ({'id', 'label', field values...}) on the criteria. Pure. Returns {'results', 'excluded', 'no_variation', 'weights'}."""
    fields = [c["field"] for c in criteria]
    complete, excluded = [], []
    for row in rows:
        values = [to_number(row.get(f)) for f in fields]
        if any(v is None for v in values):
            excluded.append(row.get("label"))
        else:
            complete.append((row, values))
    if len(complete) < 2:
        return {"error": f"Fewer than two units have a value for every criterion ({len(complete)}); nothing to rank.",
                "excluded": excluded}
    columns, no_variation = [], []
    for j, c in enumerate(criteria):
        scaled, varied = normalise([vals[j] for _row, vals in complete], c.get("direction", "higher"))
        columns.append(scaled)
        if not varied:
            no_variation.append(c["field"])
    weights = normalise_weights([float(c.get("weight", 1.0)) for c in criteria])
    scores = weighted_scores(columns, weights)
    ranks = rank(scores)
    spread = stability(columns, weights, trials, perturbation, seed, top_k)
    results = []
    for (row, _vals), score, r, sp in zip(complete, scores, ranks, spread):
        results.append({"id": row.get("id"), "unit": row.get("label"), "score": round(score, 4), "rank": r,
                        "rank_min": sp["rank_min"], "rank_max": sp["rank_max"], "top_k_share": sp["top_k_share"]})
    results.sort(key=lambda x: (x["rank"], str(x["unit"])))
    return {"results": results, "excluded": excluded, "no_variation": no_variation,
            "weights": {f: round(w, 4) for f, w in zip(fields, weights)}}


# ---------------------------------------------------------------- QGIS --

def _layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


@register_tool(
    "calculate_mcda_ranking",
    "Rank areas (or any features) on several weighted criteria and test how much the ranking depends on the weights. For each "
    "criterion give the field, a weight and which end gets priority: direction 'higher' (a high value means higher priority, e.g. "
    "people in need) or 'lower' (a low value means higher priority, e.g. water coverage). Values are min-max scaled to 0-1, scores "
    "are the weighted sum, ranks are 1 = top priority. It then re-ranks many times with the weights randomly perturbed (default "
    "+/-20%) and returns each unit's best and worst rank and, with top_k, the share of trials it stayed in the top k -- so say "
    "which priorities are robust and which only come from the chosen weights. Units missing any criterion are excluded and listed, "
    "never imputed. The weights are the user's judgement: ask for them rather than inventing them, and report them with the ranking. "
    "Optionally writes score and rank to the layer (needs confirmation). The sensitivity check covers the weights only, not data "
    "errors or the choice of criteria.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Vector layer with the units to rank (e.g. admin polygons)."},
            "criteria": {"type": "array", "description": "At least two criteria.", "items": {
                "type": "object", "properties": {
                    "field": {"type": "string"},
                    "weight": {"type": "number", "description": "Relative weight above zero; normalised to sum to 1."},
                    "direction": {"type": "string", "enum": list(DIRECTIONS), "description": "'higher' (default): high values get priority; 'lower': low values get priority."}},
                "required": ["field"]}},
            "unit_name_field": {"type": "string", "description": "Optional field used to label units in the results."},
            "top_k": {"type": "integer", "description": "Report, per unit, the share of weight-perturbation trials in which it stays in the top k."},
            "perturbation": {"type": "number", "description": "Relative weight change tested, 0 to 0.9. Default 0.2 (+/-20%)."},
            "trials": {"type": "integer", "description": f"Number of perturbation trials, default {DEFAULT_TRIALS}, maximum {MAX_TRIALS}."},
            "seed": {"type": "integer", "description": "Random seed for the perturbation. Omit for a generated one (returned)."},
            "output_prefix": {"type": "string", "description": "Optional: write <prefix>_score, <prefix>_rank, <prefix>_rank_min, <prefix>_rank_max to the layer."},
        },
        "required": ["layer_name", "criteria"],
    },
)
def calculate_mcda_ranking(layer_name, criteria, unit_name_field=None, top_k=None, perturbation=0.2, trials=DEFAULT_TRIALS,
                           seed=None, output_prefix=None, confirmed: bool = False):
    problem = validate_criteria(criteria)
    if problem:
        return {"error": problem}
    try:
        perturbation, trials = float(perturbation), int(trials)
    except (TypeError, ValueError):
        return {"error": "perturbation must be a number and trials an integer."}
    if not 0.0 <= perturbation <= 0.9:
        return {"error": "perturbation must be between 0 and 0.9."}
    if not 1 <= trials <= MAX_TRIALS:
        return {"error": f"trials must be between 1 and {MAX_TRIALS}."}
    if top_k is not None and int(top_k) < 1:
        return {"error": "top_k must be 1 or more."}
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not hasattr(layer, "getFeatures"):
        return {"error": f"'{layer_name}' must be a vector layer."}
    names = [f.name() for f in layer.fields()]
    wanted = [c["field"] for c in criteria] + ([unit_name_field] if unit_name_field else [])
    missing = [f for f in wanted if f not in names]
    if missing:
        return {"error": f"Field(s) {missing} not found on '{layer_name}'. Available: {names}"}

    if output_prefix and not confirmed:
        return {
            "status": "PREVIEW_REQUIRED", "requires_confirmation": True, "is_destructive": True,
            "tool_name": "calculate_mcda_ranking",
            "arguments": {"layer_name": layer_name, "criteria": criteria, "unit_name_field": unit_name_field, "top_k": top_k,
                          "perturbation": perturbation, "trials": trials, "seed": seed, "output_prefix": output_prefix,
                          "confirmed": True},
            "code_snippet": f"# Add/update fields {output_prefix}_score, _rank, _rank_min, _rank_max on '{layer_name}'",
            "rationale": f"Data Mutation Preview: write the MCDA score and rank fields with prefix '{output_prefix}' to layer '{layer_name}'.",
            "message": f"Confirmation required before adding fields '{output_prefix}_*' to '{layer_name}'.",
        }

    if seed is None:
        seed = random.SystemRandom().randrange(2 ** 31)
    seed = int(seed)
    rows = []
    for feat in layer.getFeatures():
        row = {"id": feat.id(), "label": str(feat[unit_name_field]) if unit_name_field else str(feat.id())}
        for c in criteria:
            row[c["field"]] = feat[c["field"]]
        rows.append(row)
    out = evaluate(rows, criteria, trials, perturbation, seed, int(top_k) if top_k else None)
    if "error" in out:
        return out

    result = {
        "success": True,
        "method": "min-max scaling to 0-1 per criterion, weighted sum, rank 1 = top priority; ties share a rank",
        "criteria": [{"field": c["field"], "direction": c.get("direction", "higher")} for c in criteria],
        "applied_weights": out["weights"],
        "scored_units": len(out["results"]),
        "excluded_units_missing_data": out["excluded"],
        "criteria_with_no_variation": out["no_variation"],
        "sensitivity": {"trials": trials, "weight_perturbation": perturbation, "seed": seed, "top_k": top_k,
                        "scope": "weights only -- not data errors, criteria choice or scaling"},
    }
    if len(out["results"]) > _RESPONSE_CAP:
        result["results"] = out["results"][:_RESPONSE_CAP]
        result["truncated"] = True
        result["truncation_note"] = f"Showing the top {_RESPONSE_CAP} of {len(out['results'])} units."
    else:
        result["results"] = out["results"]
        result["truncated"] = False
    swings = [r for r in out["results"] if r["rank_max"] - r["rank_min"] >= max(3, len(out["results"]) // 5)]
    result["unstable_units"] = len(swings)

    if output_prefix:
        by_id = {r["id"]: r for r in out["results"]}
        fields = {"score": "score", "rank": "rank", "rank_min": "rank_min", "rank_max": "rank_max"}
        try:
            with edit_command(layer, "Cartogen AI: write " + output_prefix + "_* fields") as owned:
                idx = {k: add_numeric_field(layer, f"{output_prefix}_{k}") for k in fields}
                for fid, r in by_id.items():
                    for k in fields:
                        set_value(layer, fid, idx[k], r[k])
            result["output_prefix"] = output_prefix
            result["layer_name"] = layer_name
            result["map_look"] = look_hint(layer_name, "rank", f"{output_prefix}_rank", top_k=top_k)
            if not owned:
                result["note"] = "The layer is already in edit mode, so the new values are in your edit session and are NOT saved."
        except EditError as e:
            result["output_field_warning"] = f"Scores were not written to the layer: {e}"
        except Exception as e:
            result["output_field_warning"] = f"Scores were not written to the layer: {e}"
    return result
