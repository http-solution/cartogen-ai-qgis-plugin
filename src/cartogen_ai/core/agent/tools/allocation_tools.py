# -*- coding: utf-8 -*-
"""Allocation envelope: split a budget the user supplies across areas by need (H8,
docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md).

An ADVISORY CALCULATION, not a recommendation of who should receive what. The budget, the weights, the caps and the exclusion rule
are the user's; this only does the arithmetic consistently and shows it. Each area's weight is need ** exponent (times its
population, when a population field is given); the budget is split in proportion to the weights, then
- an optional ceiling per area (`max_share_per_unit`, a share of the budget) is enforced by giving a capped area exactly its ceiling
  and re-splitting the rest among the others (repeated until nobody exceeds it),
- an optional floor (`min_amount_per_unit`) is guaranteed to every area that has a positive weight,
- areas with a missing, non-numeric or negative value, or with need below `exclude_need_below`, get nothing and are listed (never
  imputed),
- an optional `rounding` unit (e.g. 100) rounds amounts down to that unit and hands the leftover units out by largest remainder, so
  the total stays exactly what was allocated.
If the ceilings make it impossible to spend the whole budget, the difference is reported as unallocated rather than pushed onto
areas above their ceiling. No rate, price or coefficient is ever supplied by this tool.

Areas are identified by feature id, so duplicate names cannot merge two areas. Pure logic is unit tested offline; the layer work needs
QGIS (tests/test_allocation_tools_live.py, written without a local QGIS).
"""
from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value
from .humanitarian_style import look_hint
from .mcda_tools import to_number

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_RESPONSE_CAP = 50
_EPS = 1e-9


# ---------------------------------------------------------------- pure --

def allocate(weights, budget, max_share=None, min_amount=0.0, rounding=None):
    """Split `budget` over areas in proportion to `weights` (list of floats >= 0; zero means no allocation). Pure.

    Returns {'amounts': [float], 'unallocated': float, 'capped': [index], 'notes': [str]} or {'error': text}."""
    try:
        budget = float(budget)
    except (TypeError, ValueError):
        return {"error": "budget must be a number."}
    if not budget > 0:
        return {"error": "budget must be above zero."}
    n = len(weights)
    eligible = [i for i, w in enumerate(weights) if w is not None and w > 0]
    if not eligible:
        return {"error": "No area has a positive weight, so there is nothing to allocate to."}
    floor = float(min_amount or 0.0)
    if floor < 0:
        return {"error": "min_amount_per_unit cannot be negative."}
    if floor * len(eligible) > budget + _EPS:
        return {"error": (f"The floor of {floor:g} for each of {len(eligible)} areas needs {floor * len(eligible):g}, which is more than "
                          f"the budget of {budget:g}.")}
    cap = None
    if max_share is not None:
        try:
            share = float(max_share)
        except (TypeError, ValueError):
            return {"error": "max_share_per_unit must be a number between 0 and 1."}
        if not 0 < share <= 1:
            return {"error": "max_share_per_unit must be above 0 and at most 1 (a share of the budget)."}
        cap = share * budget
        if cap + _EPS < floor:
            return {"error": f"The ceiling per area ({cap:g}) is below the floor ({floor:g})."}

    amounts = [0.0] * n
    fixed = {}
    active = list(eligible)
    while active:
        remaining = budget - sum(fixed.values()) - floor * len(active)
        total_w = sum(weights[i] for i in active)
        proposed = {i: floor + remaining * weights[i] / total_w for i in active}
        over = [i for i in active if cap is not None and proposed[i] > cap + _EPS]
        if not over:
            for i in active:
                amounts[i] = proposed[i]
            break
        for i in over:
            fixed[i] = cap
        active = [i for i in active if i not in over]
    for i, value in fixed.items():
        amounts[i] = value
    capped = [i for i in eligible if cap is not None and amounts[i] >= cap - 1e-9]

    notes = []
    if rounding:
        try:
            unit = float(rounding)
        except (TypeError, ValueError):
            return {"error": "rounding must be a number."}
        if unit <= 0:
            return {"error": "rounding must be above zero."}
        total_target = sum(amounts)
        floored = [int((a + _EPS) // unit) * unit for a in amounts]
        pieces = int(round((total_target - sum(floored)) / unit))
        order = sorted(range(n), key=lambda i: (-(amounts[i] - floored[i]), i))
        for i in order:
            if pieces <= 0:
                break
            if amounts[i] <= 0:
                continue
            if cap is not None and floored[i] + unit > cap + _EPS:
                continue
            floored[i] += unit
            pieces -= 1
        amounts = floored
        notes.append(f"Amounts are rounded down to multiples of {unit:g}; the leftover units go to the areas with the largest remainders.")
    unallocated = budget - sum(amounts)
    if abs(unallocated) < 1e-6:
        unallocated = 0.0
    if unallocated > 0:
        notes.append(f"{unallocated:g} of the budget is unallocated" +
                     (": every eligible area is at its ceiling." if cap is not None and len(capped) == len(eligible) else "."))
    return {"amounts": amounts, "unallocated": unallocated, "capped": capped, "notes": notes}


def weight_for(need, population, exponent=1.0, exclude_below=None):
    """(weight or None, reason or None) for one area. Pure. Missing / non-numeric / negative values are excluded with a reason."""
    n = to_number(need)
    if n is None:
        return None, "missing or non-numeric need"
    if n < 0:
        return None, "negative need"
    if exclude_below is not None and n < float(exclude_below):
        return None, "need below the exclusion threshold"
    w = n ** float(exponent)
    if population is not None:
        p = to_number(population)
        if p is None:
            return None, "missing or non-numeric population"
        if p < 0:
            return None, "negative population"
        w *= p
    return w, None


# ---------------------------------------------------------------- QGIS --

def _layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


@register_tool(
    "calculate_allocation_envelope",
    "Split a budget the user gives across areas in proportion to need (optionally times population), with optional ceiling and floor "
    "per area, optional rounding, and areas below a need threshold left out. This is an ADVISORY CALCULATION of an envelope, not a "
    "recommendation of who should receive what: the budget, the need field, the exponent, the ceiling/floor and the exclusion "
    "threshold are the user's decisions, so ask for them and state them with the result. Need can be a severity score, a people-in-need "
    "count or any non-negative field; population is optional. Areas with a missing or negative value are excluded and listed, never "
    "imputed. If ceilings stop the whole budget being spent the rest is reported as unallocated. Optionally writes each area's amount "
    "to the layer (needs confirmation). Never invent a budget, a cost per person or a coefficient.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Vector layer with the areas (e.g. admin polygons)."},
            "budget": {"type": "number", "description": "The total to split, in the user's own unit. Must be given by the user."},
            "need_field": {"type": "string", "description": "Non-negative numeric field that drives the split (e.g. a 0-1 severity score or people in need)."},
            "population_field": {"type": "string", "description": "Optional numeric field; when given the weight is need x population."},
            "unit_name_field": {"type": "string", "description": "Optional field used to label areas in the results."},
            "need_exponent": {"type": "number", "description": "Weight = need ** exponent. Default 1 (proportional). Above 1 favours the neediest areas more, below 1 spreads more evenly."},
            "max_share_per_unit": {"type": "number", "description": "Optional ceiling per area as a share of the budget, above 0 and at most 1 (e.g. 0.15)."},
            "min_amount_per_unit": {"type": "number", "description": "Optional floor guaranteed to every area with a positive weight."},
            "exclude_need_below": {"type": "number", "description": "Optional: areas with need below this get nothing."},
            "rounding": {"type": "number", "description": "Optional: round amounts to multiples of this (e.g. 100); the total is preserved."},
            "unit_label": {"type": "string", "description": "Optional label for the budget's unit (e.g. 'USD'); echoed in the result."},
            "output_field": {"type": "string", "description": "Optional: write each area's amount to the layer under this field name."},
        },
        "required": ["layer_name", "budget", "need_field"],
    },
)
def calculate_allocation_envelope(layer_name, budget, need_field, population_field=None, unit_name_field=None, need_exponent=1.0,
                                  max_share_per_unit=None, min_amount_per_unit=0.0, exclude_need_below=None, rounding=None,
                                  unit_label=None, output_field=None, confirmed: bool = False):
    try:
        need_exponent = float(need_exponent)
    except (TypeError, ValueError):
        return {"error": "need_exponent must be a number."}
    if not need_exponent > 0:
        return {"error": "need_exponent must be above zero."}
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not hasattr(layer, "getFeatures"):
        return {"error": f"'{layer_name}' must be a vector layer."}
    names = [f.name() for f in layer.fields()]
    wanted = [need_field] + [f for f in (population_field, unit_name_field) if f]
    missing = [f for f in wanted if f not in names]
    if missing:
        return {"error": f"Field(s) {missing} not found on '{layer_name}'. Available: {names}"}

    if output_field and not confirmed:
        return {
            "status": "PREVIEW_REQUIRED", "requires_confirmation": True, "is_destructive": True,
            "tool_name": "calculate_allocation_envelope",
            "arguments": {"layer_name": layer_name, "budget": budget, "need_field": need_field, "population_field": population_field,
                          "unit_name_field": unit_name_field, "need_exponent": need_exponent, "max_share_per_unit": max_share_per_unit,
                          "min_amount_per_unit": min_amount_per_unit, "exclude_need_below": exclude_need_below, "rounding": rounding,
                          "unit_label": unit_label, "output_field": output_field, "confirmed": True},
            "code_snippet": f"# Add/update field '{output_field}' on '{layer_name}' with each area's allocation amount",
            "rationale": f"Data Mutation Preview: write allocation amounts to field '{output_field}' of layer '{layer_name}'.",
            "message": f"Confirmation required before adding field '{output_field}' to '{layer_name}'.",
        }

    rows, weights, excluded = [], [], []
    for feat in layer.getFeatures():
        label = str(feat[unit_name_field]) if unit_name_field else str(feat.id())
        w, reason = weight_for(feat[need_field], feat[population_field] if population_field else None, need_exponent, exclude_need_below)
        if w is None:
            excluded.append({"unit": label, "reason": reason})
        else:
            rows.append({"id": feat.id(), "unit": label})
            weights.append(w)
    out = allocate(weights, budget, max_share_per_unit, min_amount_per_unit or 0.0, rounding)
    if "error" in out:
        out["excluded_units"] = excluded
        return out

    results = [{"unit": r["unit"], "id": r["id"], "amount": round(a, 6), "share_of_budget": round(a / float(budget), 4),
                "at_ceiling": i in out["capped"]} for i, (r, a) in enumerate(zip(rows, out["amounts"]))]
    results.sort(key=lambda x: (-x["amount"], str(x["unit"])))
    result = {
        "success": True,
        "advisory": "A calculation of an envelope from the user's inputs; not a recommendation of who should receive what.",
        "budget": float(budget), "unit_label": unit_label,
        "allocated": round(sum(out["amounts"]), 6), "unallocated": round(out["unallocated"], 6),
        "inputs": {"need_field": need_field, "population_field": population_field, "need_exponent": need_exponent,
                   "max_share_per_unit": max_share_per_unit, "min_amount_per_unit": min_amount_per_unit or 0.0,
                   "exclude_need_below": exclude_need_below, "rounding": rounding},
        "method": "weight = need ** exponent" + (" x population" if population_field else "") + "; budget split in proportion to weight",
        "areas_allocated": sum(1 for r in results if r["amount"] > 0),
        "areas_at_ceiling": len(out["capped"]),
        "excluded_units": excluded,
        "notes": out["notes"],
    }
    if len(results) > _RESPONSE_CAP:
        result["results"], result["truncated"] = results[:_RESPONSE_CAP], True
        result["truncation_note"] = f"Showing the largest {_RESPONSE_CAP} of {len(results)} areas; output_field writes all of them."
    else:
        result["results"], result["truncated"] = results, False

    if output_field:
        by_id = {r["id"]: a for r, a in zip(rows, out["amounts"])}
        try:
            with edit_command(layer, "Cartogen AI: write " + output_field) as owned:
                idx = add_numeric_field(layer, output_field)
                for fid in (f.id() for f in layer.getFeatures()):
                    set_value(layer, fid, idx, by_id.get(fid, 0.0))
            result["output_field"] = output_field
            result["layer_name"] = layer_name
            result["map_look"] = look_hint(layer_name, "allocation", output_field)
            if not owned:
                result["note"] = "The layer is already in edit mode, so the new values are in your edit session and are NOT saved."
        except EditError as e:
            result["output_field_warning"] = f"Amounts were not written to the layer: {e}"
        except Exception as e:
            result["output_field_warning"] = f"Amounts were not written to the layer: {e}"
    return result
