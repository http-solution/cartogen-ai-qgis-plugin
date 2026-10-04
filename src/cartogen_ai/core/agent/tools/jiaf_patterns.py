# -*- coding: utf-8 -*-
"""JIAF 2 analysis support, stage 4b: the intersectoral pattern outputs of Workspace 3C (Reference Table 3C, July 2024 manual, pp.48-49).

SUPPORT FOR PEOPLE WHO RUN THE JIAF 2 PROCESS. NOT the JIAF method, NOT endorsed by OCHA or the IASC. These are the lists and counts the manual asks the
analysts to look at for the ten questions; the answers (the narrative) are the analysts'. Every threshold is a country-level setting
("The threshold can be set at country level"); the manual's own default is used where it states one (40% of the administrative population, five or
more sectors in phase 4-5, the three highest sectors, a correlation above 0.7, phases 4-5) and the others (marked `module default`) are this module's
choice, echoed in every result.

Severity used here is the FINAL severity where a decision was recorded or the unit was unflagged, and the preliminary severity for units still pending
(counted and reported, so the reader knows). There is no national severity. Results are not for ranking crises.
"""
import math

from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value
from .jiaf_engine import run_analysis
from .jiaf_inputs import STATEMENT
from .jiaf_review import finalize, load_decisions
from .table_importers import key_of, plan_join

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_CAP = 25
DEFAULTS = {  # (value, where it comes from)
    "sector_population_share": (0.40, "manual, prompt 2"),
    "many_sectors_with_large_pin": (3, "module default"),
    "top_units": (10, "module default"),
    "high_pin_share": (0.40, "module default (same 40% as prompt 2)"),
    "severe_phases": ((4, 5), "manual, prompts 6-7"),
    "many_severe_sectors": (5, "manual, prompt 6"),
    "top_sectors": (3, "manual, prompt 3"),
    "correlation_threshold": (0.7, "manual, prompt 10"),
}


def pearson(xs, ys):
    """Pearson correlation of paired values; None with fewer than 3 pairs or no variance."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None
    mx, my = sum(x for x, _ in pairs) / n, sum(y for _, y in pairs) / n
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    syy = sum((y - my) ** 2 for _, y in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in pairs) / math.sqrt(sxx * syy)


def merge_thresholds(overrides=None):
    t = {k: v[0] for k, v in DEFAULTS.items()}
    for k, v in (overrides or {}).items():
        if k not in DEFAULTS:
            raise ValueError(f"Unknown threshold '{k}'. Thresholds: {sorted(DEFAULTS)}.")
        if v is not None:
            t[k] = tuple(int(x) for x in v) if k == "severe_phases" else v
    for k in ("sector_population_share", "high_pin_share"):
        if not 0 < float(t[k]) <= 1:
            raise ValueError(f"{k} must be above 0 and at most 1.")
    if not t["severe_phases"] or any(p not in (1, 2, 3, 4, 5) for p in t["severe_phases"]):
        raise ValueError("severe_phases must be phases from 1 to 5.")
    for k in ("many_sectors_with_large_pin", "top_units", "many_severe_sectors", "top_sectors"):
        t[k] = int(t[k])
        if t[k] < 1:
            raise ValueError(f"{k} must be at least 1.")
    t["correlation_threshold"] = float(t["correlation_threshold"])
    return t


def patterns(units, analysis, final_rows, previous_analysis=None, thresholds=None, group_shares=None):
    """The ten Workspace 3C outputs as plain data. Pure."""
    t = merge_thresholds(thresholds)
    expected = analysis["expected_sectors"]
    by = {(r["admin2_code"], r["population_group"]): r for r in final_rows}
    out = {"thresholds": {k: (list(v) if isinstance(v, tuple) else v) for k, v in t.items()}}
    unit_info = []
    for u in units:
        fr = by[(u["admin2_code"], u["population_group"])]
        sev = fr["final_severity"] if fr["final_severity"] is not None else fr["preliminary_severity"]
        unit_info.append({"u": u, "fr": fr, "sev": sev, "provisional_sev": fr["final_severity"] is None and fr["preliminary_severity"] is not None})
    has_pop = sum(1 for i in unit_info if i["u"]["population"]) > 0
    pop_note = None if has_pop else "No population in the file, so every share-of-population output is not evaluable."

    # Q1 -- where is the highest concentration of PiN
    ranked = sorted((i for i in unit_info if i["fr"]["final_pin"] is not None), key=lambda i: -i["fr"]["final_pin"])
    q1 = []
    for i in ranked[:t["top_units"]]:
        pop = i["u"]["population"]
        share = i["fr"]["final_pin"] / pop if pop else None
        q1.append({"unit": i["u"]["admin2_code"], "name": i["u"]["admin2"], "final_pin": i["fr"]["final_pin"], "share_of_population": share,
                   "high_absolute_and_high_share": bool(share is not None and share >= t["high_pin_share"])})
    out["q1_highest_pin"] = {"top_units": q1, "note": pop_note}

    # Q2 -- units with many sectors above a share of the population
    q2_counts = {}
    if has_pop:
        for i in unit_info:
            pop = i["u"]["population"]
            n = sum(1 for s in expected if pop and (i["u"]["pin"].get(s) or 0) > t["sector_population_share"] * pop)
            q2_counts[i["u"]["admin2_code"]] = n
    many = sorted(((c, n) for c, n in q2_counts.items() if n >= t["many_sectors_with_large_pin"]), key=lambda x: -x[1])
    out["q2_sectors_above_share"] = {"units_with_many_sectors": [{"unit": c, "sectors": n} for c, n in many[:_CAP]], "count_of_such_units": len(many),
                                     "distribution": _dist(q2_counts.values()), "note": pop_note}

    # Q3 -- which sectors drive the PiN
    sums = {s: (sum(i["u"]["pin"].get(s) or 0 for i in unit_info) if any(i["u"]["pin"].get(s) is not None for i in unit_info) else None) for s in expected}
    highest = {s: sum(1 for i in unit_info if s in i["fr"]["pin_drivers"]) for s in expected}
    out["q3_sector_pin"] = {
        "national_pin_by_sector": {s: (round(v, 2) if v is not None else None) for s, v in sums.items()},
        "note_on_sums": "Each figure is one sector's PiN summed over units; the sectors' figures are NOT added together.",
        "units_where_sector_is_highest": highest,
        "top_sectors_by_pin": sorted((s for s in sums if sums[s] is not None), key=lambda s: -sums[s])[:t["top_sectors"]],
        "top_sectors_by_units_highest": sorted(highest, key=lambda s: -highest[s])[:t["top_sectors"]],
    }

    # Q4 -- change against last year (same basis: the highest sectoral PiN)
    if previous_analysis is None:
        out["q4_trend"] = {"note": "No previous-year file given, so the trend was not computed."}
    else:
        prev = {(r["admin2_code"], r["population_group"]): r["preliminary_pin"] for r in previous_analysis["rows"]}
        cur = {(r["admin2_code"], r["population_group"]): r["preliminary_pin"] for r in analysis["rows"]}
        both = [k for k in cur if cur[k] is not None and prev.get(k) is not None]
        changes = sorted(((cur[k] - prev[k], k, prev[k], cur[k]) for k in both), key=lambda x: x[0])
        row = lambda c: {"unit": c[1][0], "previous": c[2], "current": c[3], "change": c[0]}  # noqa: E731
        out["q4_trend"] = {
            "basis": "highest sectoral PiN (preliminary) this year against the same last year; not the Final PiN",
            "units_compared": len(both), "national_previous": round(sum(prev[k] for k in both), 2), "national_current": round(sum(cur[k] for k in both), 2),
            "largest_increases": [row(c) for c in reversed(changes[-10:])], "largest_decreases": [row(c) for c in changes[:10]],
        }

    # Q5 -- by population group share (extrapolation, never a measurement)
    total_pin = sum(i["fr"]["final_pin"] or 0 for i in unit_info)
    if group_shares:
        out["q5_group_estimates"] = {
            "estimates": {g: round(total_pin * float(sh), 2) for g, sh in group_shares.items()},
            "caveat": "Estimated as the Final PiN total times the group's share of the population (manual Box 27). It reflects the group's population share, "
                      "not any difference in its needs."}
    else:
        out["q5_group_estimates"] = {"note": "Give group_shares (e.g. {'girls': 0.25}) to extrapolate; the module does not assume demographic shares."}

    # Q6/Q7/Q8 -- severity
    sev_known = [i for i in unit_info if i["sev"] is not None]
    high = [i for i in sev_known if i["sev"] in t["severe_phases"]]
    sev_n = {}
    for i in unit_info:
        n = sum(1 for s in expected if (i["u"]["severity"].get(s) or 0) in (4, 5))
        sev_n[i["u"]["admin2_code"]] = n
    many_sev = sorted(((c, n) for c, n in sev_n.items() if n >= t["many_severe_sectors"]), key=lambda x: -x[1])
    sector_hi = {s: sum(1 for i in unit_info if (i["u"]["severity"].get(s) or 0) in (4, 5)) for s in expected}
    out["q6_severity"] = {
        "units_in_high_phases": [{"unit": i["u"]["admin2_code"], "phase": i["sev"], "provisional": i["provisional_sev"]} for i in high[:_CAP]],
        "count_of_such_units": len(high), "units_with_many_sectors_in_phase_4_or_5": [{"unit": c, "sectors": n} for c, n in many_sev[:_CAP]],
        "top_sectors_by_units_in_phase_4_or_5": sorted(sector_hi, key=lambda s: -sector_hi[s])[:t["top_sectors"]],
        "units_whose_severity_is_still_preliminary": sum(1 for i in unit_info if i["provisional_sev"]),
        "note": "There is no national severity; this is per unit.",
    }
    out["q7_sectors_in_phase_4_or_5"] = {"distribution_of_units": _dist(sev_n.values())}
    out["q8_sector_severity_distribution"] = {s: _dist(i["u"]["severity"].get(s) for i in unit_info if i["u"]["severity"].get(s)) for s in expected}

    # Q9 -- coexistence of high PiN share and high severity
    both_hi = []
    for i in sev_known:
        pop = i["u"]["population"]
        share = i["fr"]["final_pin"] / pop if (pop and i["fr"]["final_pin"] is not None) else None
        if share is not None and share >= t["high_pin_share"] and i["sev"] in t["severe_phases"]:
            both_hi.append({"unit": i["u"]["admin2_code"], "phase": i["sev"], "share_of_population": share})
    per_sector_both = {}
    for s in expected:
        per_sector_both[s] = sum(1 for i in unit_info if i["u"]["population"] and (i["u"]["pin"].get(s) or 0) / i["u"]["population"] >= t["high_pin_share"]
                                 and (i["u"]["severity"].get(s) or 0) in (4, 5))
    out["q9_high_pin_and_high_severity"] = {"units": both_hi[:_CAP], "count_of_such_units": len(both_hi),
                                            "top_sectors_by_units_with_both": sorted(per_sector_both, key=lambda s: -per_sector_both[s])[:t["top_sectors"]],
                                            "note": pop_note}

    # Q10 -- correlation between sectoral PiNs
    pairs = []
    for a in range(len(expected)):
        for b in range(a + 1, len(expected)):
            r = pearson([i["u"]["pin"].get(expected[a]) for i in unit_info], [i["u"]["pin"].get(expected[b]) for i in unit_info])
            if r is not None and r > t["correlation_threshold"]:
                pairs.append({"sectors": [expected[a], expected[b]], "correlation": round(r, 4)})
    out["q10_pin_correlation"] = {"pairs_above_threshold": sorted(pairs, key=lambda p: -p["correlation"]),
                                  "note": "Pearson correlation of the two sectors' PiN across units where both have a figure."}
    out["_unit_counts"] = {"sectors_above_share": q2_counts, "sectors_in_phase_4_or_5": sev_n}
    return out


def _dist(values):
    d = {}
    for v in values:
        d[v] = d.get(v, 0) + 1
    return {str(k): d[k] for k in sorted(d)}


@register_tool(
    "compute_jiaf_patterns",
    "Produce the JIAF 2 intersectoral pattern outputs of Workspace 3C (support for the JIAF 2 process; not the JIAF method, not endorsed by OCHA or the "
    "IASC): where the PiN is concentrated, which units have many sectors with more than 40% of the population in need, which sectors drive the PiN, the "
    "change against last year, units in severity phases 4-5 and with five or more sectors in phase 4-5, sector severity distributions, units with both "
    "high PiN and high severity, and the sector pairs whose PiN correlates above 0.7. These are lists and counts for the analysts' discussion, not "
    "conclusions. Thresholds are country-level settings (the manual's defaults where it gives one; the others are the module's and are echoed). Uses the "
    "recorded group decisions where they exist and the preliminary severity otherwise (reported). No national severity; not for ranking crises. "
    "Optionally writes jf_nsec40 and jf_nsev45 (counts per unit, for mapping) to an admin layer after confirmation.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"}, "input_format": {"type": "string"}, "sheet_name": {"type": "string"},
            "previous_file_path": {"type": "string"}, "previous_sheet_name": {"type": "string"},
            "sectors_in_scope": {"type": "array", "items": {"type": "string"}, "description": "Main sectors the HCT activated. Default: all eight."},
            "zero_severity_as": {"type": "string", "description": "'not_applicable' (default) or 'missing'."},
            "sector_population_share": {"type": "number", "description": "Share of a unit's population that makes a sector's PiN 'large'. Manual: 0.40."},
            "many_sectors_with_large_pin": {"type": "integer"}, "top_units": {"type": "integer"}, "high_pin_share": {"type": "number"},
            "severe_phases": {"type": "array", "items": {"type": "integer"}, "description": "Default [4, 5]."},
            "many_severe_sectors": {"type": "integer", "description": "Manual: 5."}, "top_sectors": {"type": "integer", "description": "Manual: 3."},
            "correlation_threshold": {"type": "number", "description": "Manual: 0.7."},
            "group_shares": {"type": "object", "description": "Optional population shares per group, e.g. {'girls': 0.25}, for the extrapolated estimates."},
            "layer_name": {"type": "string"}, "layer_key_field": {"type": "string"},
            "write_fields": {"type": "boolean", "description": "With layer_name: write jf_nsec40 and jf_nsev45. Needs confirmation."},
        },
        "required": ["file_path"],
    },
)
def compute_jiaf_patterns(file_path, input_format="auto", sheet_name=None, previous_file_path=None, previous_sheet_name=None,
                          sectors_in_scope=None, zero_severity_as=None, sector_population_share=None, many_sectors_with_large_pin=None, top_units=None, high_pin_share=None, severe_phases=None,
                          many_severe_sectors=None, top_sectors=None, correlation_threshold=None, group_shares=None, layer_name=None,
                          layer_key_field=None, write_fields=False, confirmed: bool = False):
    th = {k: v for k, v in {"sector_population_share": sector_population_share, "many_sectors_with_large_pin": many_sectors_with_large_pin,
                            "top_units": top_units, "high_pin_share": high_pin_share, "severe_phases": severe_phases,
                            "many_severe_sectors": many_severe_sectors, "top_sectors": top_sectors,
                            "correlation_threshold": correlation_threshold}.items() if v is not None}
    try:
        merge_thresholds(th)
    except (ValueError, TypeError) as e:
        return {"error": str(e)}
    if group_shares is not None and not (isinstance(group_shares, dict) and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in group_shares.values())):
        return {"error": "group_shares must be an object of shares between 0 and 1."}
    scope = {k: v for k, v in {"sectors_in_scope": sectors_in_scope, "zero_severity_as": zero_severity_as}.items() if v is not None}
    try:
        run = run_analysis(file_path, input_format, sheet_name, previous_file_path, previous_sheet_name, scope)
    except (ValueError, TypeError) as e:
        return {"error": str(e)}
    if "error" in run:
        return run
    prev_analysis = None
    if run["previous"] is not None:
        from .jiaf_engine import analyze
        prev_analysis = analyze(run["previous"], overrides=scope)
    decisions = load_decisions()
    rows, summary = finalize(run["units"], run["analysis"], decisions)
    res = patterns(run["units"], run["analysis"], rows, prev_analysis, th, group_shares)
    counts = res.pop("_unit_counts")
    result = {"success": True, "statement": STATEMENT, "units": len(rows), "format": run["format"], "decisions_used": {k: len(v) for k, v in decisions.items()},
              "pending_flagged_units": summary["pending_pin_units"], "provisional": summary["provisional"],
              "provisional_note": ("Some flagged units have no recorded decision: PiN outputs use their highest sectoral PiN and severity outputs use the preliminary "
                                   "phase for them." if summary["provisional"] else None),
              **res}
    if not layer_name:
        return result
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers or not hasattr(layers[0], "getFeatures"):
        return {"error": f"Vector layer '{layer_name}' not found"}
    layer = layers[0]
    if not layer_key_field or layer.fields().indexOf(layer_key_field) < 0:
        return {"error": f"layer_key_field '{layer_key_field}' not found on '{layer_name}'. Available: {[f.name() for f in layer.fields()]}"}
    pairs, report = plan_join([{"key": key_of(r["admin2_code"], None), "code": r["admin2_code"]} for r in rows],
                              [(f.id(), key_of(f[layer_key_field], None)) for f in layer.getFeatures()])
    result["join"] = report
    if not write_fields or not pairs:
        return result
    names = ["jf_nsec40", "jf_nsev45"]
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED", "requires_confirmation": True, "is_destructive": True, "tool_name": "compute_jiaf_patterns",
            "arguments": dict({"file_path": file_path, "input_format": input_format, "sheet_name": sheet_name, "layer_name": layer_name,
                               "layer_key_field": layer_key_field, "write_fields": True, "confirmed": True}, **th),
            "code_snippet": f"# Add/update fields {names} on '{layer_name}' for {report['matched']} matched areas",
            "rationale": f"Data Mutation Preview: write JIAF pattern counts to {names} of layer '{layer_name}' ({report['matched']} of {report['layer_features']} areas match).",
            "message": f"Confirmation required before adding fields to '{layer_name}'.", "join": report,
        }
    try:
        with edit_command(layer, "Cartogen AI: JIAF pattern counts") as owned:
            idx = [add_numeric_field(layer, n) for n in names]
            for fid, rec in pairs:
                for i, key in zip(idx, ("sectors_above_share", "sectors_in_phase_4_or_5")):
                    v = counts[key].get(rec["code"])
                    if v is not None:
                        set_value(layer, fid, i, float(v))
        result["fields_written"] = names
        result["field_note"] = "jf_nsec40: sectors whose PiN exceeds the share of the unit's population (empty without population); jf_nsev45: sectors in phase 4 or 5."
        if not owned:
            result["note"] = "The layer is already in edit mode, so the new values are in your edit session and are NOT saved."
    except EditError as e:
        result["write_warning"] = f"Values were not written to the layer: {e}"
    except Exception as e:
        result["write_warning"] = f"Values were not written to the layer: {e}"
    return result
