# -*- coding: utf-8 -*-
"""JIAF 2 analysis support, stage 3: the preliminary calculations the July 2024 manual makes mechanical
(docs/JIAF2_ANALYSIS_SUPPORT_PLAN_2026-10-04.md, sections 2, 4 and 6).

SUPPORT FOR PEOPLE WHO RUN THE JIAF 2 PROCESS. NOT the JIAF method, NOT endorsed by OCHA or the IASC, never "JIAF-compliant".

What is computed, per unit of analysis, from the eight main sectors (the AoRs CP, GBV, Mine Action and HLP are display-only and never enter):
- PRELIMINARY joint PiN = the highest sectoral PiN (Mosaic Method, Box 21); the national figure is the sum over units. Never an average and never a
  sum across sectors. This is NOT the Final PiN: the Final PiN is a recorded group decision per flagged unit (stage 4).
- the PiN flags of Table 3A (1-6; flag 7 is manual and is not computed);
- PRELIMINARY intersectoral severity from the overlap of sectoral severities (Box 22);
- the severity flags of Table 3B1 (1-4; 5 is manual). Severity flags 2 and 3 need outcome-indicator phases that the analyst assigned; without them
  they are "not evaluable", not "not fired".
The final severity of a flagged unit is NEVER computed here.

CHECKED against the real Yemen 2026 worksheet and the published HNO 2026 file (333 units): the preliminary-severity rule reproduces the stored
severity in 333/333 units; the national total of the stored Final PiN is 22,325,198 and the chosen sector is the highest in 305 units, the second
highest in 11 and the third highest in 17 (so a Final PiN is "the PiN of a chosen sector", not only first or second).

READINGS THE MANUAL LEAVES OPEN (plan section 6) -- each is a setting, echoed in every result, and none is verified against the OCHA worksheet formulas
(the supplied copy has values only, no flags):
- Flag 1 fires when the number of sectors with a missing or zero PiN is at least `f1_min_sectors` (default 1; the table says "1 or 2").
- Flags 2 and 3 measure the difference of the highest PiN to the 2nd / 3rd highest RELATIVE TO THE 2nd / 3rd (so it can exceed 100%): Annex 5 speaks of a
  ">200 percent difference between 1st and second PiN", which is impossible if measured against the highest. They fire at >= the threshold; if the
  2nd/3rd highest is 0 and the highest is above 0 the difference is undefined and the flag fires.
- Flag 4 is only evaluated when the sectors that count a sub-population are named (`f4_subpopulation_sectors`); it then fires when the highest PiN
  belongs to one of them. The manual's 50% threshold is not applied (unknown meaning).
- Flag 5 fires when the highest PiN is above `f5_share` (default 90%) of the unit's population. A highest PiN above 100% is also marked as a likely data
  error (Annex 5) -- but a sector that counts a subset of the population may legitimately be compared with that subset, which is not known here.
- Flag 6 compares the highest sector's PiN with the SAME sector's previous-year PiN and fires on an increase of at least `f6_pct` (default 100%), only
  when the previous PiN is at least `f6_min_previous_pin` (default 1,000: Annex 5 says "preferably only for PiN figures above one thousand").
- Severity flag 4 fires when MORE THAN `s4_sector_count` (default 4) sectors are in phase 4 and the preliminary phase is 4.
"""
import csv
import os

from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value
from .jiaf_inputs import MAIN_SECTORS, STATEMENT, load_units, validate_units
from .table_importers import key_of, plan_join

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_CAP = 50
_TOL = 1e-9
DEFAULTS = {"f1_min_sectors": 1, "f2_pct": 0.30, "f3_pct": 0.50, "f4_subpopulation_sectors": (), "f5_share": 0.90, "f6_pct": 1.00,
            "f6_min_previous_pin": 1000.0, "s4_sector_count": 4}
READINGS = [
    "Flag 1: fires when the number of sectors with missing or zero PiN is at least f1_min_sectors (the table says '1 or 2').",
    "Flags 2/3: the difference is measured relative to the 2nd/3rd highest PiN and fires at >= the threshold (Annex 5 implies this).",
    "Flag 4: only evaluated when f4_subpopulation_sectors is given; fires when the highest PiN belongs to one of them; the 50% is not applied.",
    "Flag 5: highest PiN above f5_share of the unit's population; above 100% is also marked as a likely data error.",
    "Flag 6: the highest sector's PiN against the same sector's previous-year PiN; increase >= f6_pct; only when the previous PiN >= f6_min_previous_pin.",
    "Severity flag 4: more than s4_sector_count sectors in phase 4 and a preliminary phase 4.",
]


# ------------------------------------------------------------------ pure --
def merge_settings(overrides=None):
    s = dict(DEFAULTS)
    for k, v in (overrides or {}).items():
        if k not in DEFAULTS:
            raise ValueError(f"Unknown setting '{k}'. Settings: {sorted(DEFAULTS)}.")
        if v is not None:
            s[k] = v
    if int(s["f1_min_sectors"]) < 1:
        raise ValueError("f1_min_sectors must be at least 1.")
    for k in ("f2_pct", "f3_pct", "f5_share", "f6_pct", "f6_min_previous_pin"):
        s[k] = float(s[k])
        if s[k] < 0:
            raise ValueError(f"{k} must not be negative.")
    s["f4_subpopulation_sectors"] = tuple(s["f4_subpopulation_sectors"] or ())
    bad = [x for x in s["f4_subpopulation_sectors"] if x not in MAIN_SECTORS]
    if bad:
        raise ValueError(f"f4_subpopulation_sectors must be main sectors {MAIN_SECTORS}; got {bad}.")
    s["f1_min_sectors"] = int(s["f1_min_sectors"])
    s["s4_sector_count"] = int(s["s4_sector_count"])
    return s


def ranked_pins(unit, expected):
    """[(sector, pin)] for the expected main sectors that have a PiN, highest first (ties in the canonical sector order)."""
    items = [(s, unit["pin"].get(s)) for s in expected]
    present = [(s, v) for s, v in items if v is not None]
    order = {s: i for i, s in enumerate(MAIN_SECTORS)}
    return sorted(present, key=lambda sv: (-sv[1], order[sv[0]]))


def preliminary_pin(ranked):
    """(value, drivers): the highest sectoral PiN and every sector within tolerance of it. (None, []) with no PiN at all."""
    if not ranked:
        return None, []
    top = ranked[0][1]
    return top, [s for s, v in ranked if abs(v - top) <= _TOL * max(1.0, abs(top))]


def _rel_diff(top, other):
    """(value, fired_if_undefined): (top - other) / other; undefined when other is 0 and top is above 0."""
    if other is None:
        return None, False
    if other == 0:
        return (None, True) if top > 0 else (0.0, False)
    return (top - other) / other, False


def pin_flags(unit, ranked, settings, expected, previous_unit=None):
    """{flag number: {"fired": bool or None (not evaluable), "value": ..., "note": ...}} for flags 1-6."""
    flags = {}
    missing = [s for s in expected if unit["pin"].get(s) is None or unit["pin"].get(s) == 0]
    flags[1] = {"fired": len(missing) >= settings["f1_min_sectors"], "value": len(missing), "note": ", ".join(missing) or None}
    top = ranked[0][1] if ranked else None
    for n, idx, key in ((2, 1, "f2_pct"), (3, 2, "f3_pct")):
        if top is None or len(ranked) <= idx:
            flags[n] = {"fired": None, "value": None, "note": "fewer sectors with a PiN than needed"}
            continue
        val, undefined = _rel_diff(top, ranked[idx][1])
        fired = True if undefined else val >= settings[key] - _TOL
        flags[n] = {"fired": fired, "value": val, "note": "undefined: the comparison PiN is 0" if undefined else None}
    subs = settings["f4_subpopulation_sectors"]
    if not subs or top is None:
        flags[4] = {"fired": None, "value": None, "note": "no sub-population sectors named" if not subs else None}
    else:
        drivers = preliminary_pin(ranked)[1]
        hit = [s for s in drivers if s in subs]
        flags[4] = {"fired": bool(hit), "value": None, "note": ", ".join(hit) or None}
    pop = unit.get("population")
    if top is None or not pop or pop <= 0:
        flags[5] = {"fired": None, "value": None, "note": "no population for the unit" if top is not None else None}
    else:
        share = top / pop
        flags[5] = {"fired": share > settings["f5_share"] + _TOL, "value": share,
                    "note": "above 100% of the population: likely a data error unless the sector counts a subset" if share > 1 + _TOL else None}
    if top is None or previous_unit is None:
        flags[6] = {"fired": None, "value": None, "note": "no previous-year figure" if top is not None else None}
    else:
        prev = previous_unit["pin"].get(preliminary_pin(ranked)[1][0])
        if prev is None or prev <= 0 or prev < settings["f6_min_previous_pin"]:
            flags[6] = {"fired": None, "value": None, "note": "previous-year PiN missing or below f6_min_previous_pin"}
        else:
            change = (top - prev) / prev
            flags[6] = {"fired": change >= settings["f6_pct"] - _TOL, "value": change, "note": None}
    return flags


def preliminary_severity(phases):
    """Preliminary intersectoral severity (Box 22) from the sectors' phases (1-5; None or 0 = not reporting). None when nothing reports."""
    vals = [p for p in phases if p]
    if not vals:
        return None
    n = lambda p: sum(1 for x in vals if x >= p)  # noqa: E731
    if n(5) >= 2 and n(4) >= 4:
        return 5
    if n(4) >= 4:
        return 4
    if n(3) >= 4:
        return 3
    if n(2) >= 4:
        return 2
    return 1


def clean_outcome(v):
    """An analyst-assigned indicator phase: an integer 1-5, else None."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) and 1 <= f <= 5 else None


def severity_flags(unit, phases, prelim, settings):
    """{flag number: {...}} for severity flags 1-4 (5 is manual). Flags 2 and 3 are None (not evaluable) without outcome phases."""
    flags = {}
    flags[1] = {"fired": any(p == 5 for p in phases), "value": sum(1 for p in phases if p == 5), "note": None}
    outcomes = {k: clean_outcome(v) for k, v in (unit.get("outcomes") or {}).items()}
    outcomes = {k: v for k, v in outcomes.items() if v is not None}
    if prelim is None or not outcomes:
        flags[2] = flags[3] = {"fired": None, "value": None, "note": "no outcome-indicator phases assigned"}
    else:
        diffs = {k: v - prelim for k, v in outcomes.items()}
        flags[2] = {"fired": any(abs(d) >= 2 for d in diffs.values()), "value": diffs, "note": None}
        flags[3] = {"fired": sum(1 for d in diffs.values() if abs(d) == 1) >= 2, "value": diffs, "note": None}
    n4 = sum(1 for p in phases if p == 4)
    flags[4] = {"fired": prelim == 4 and n4 > settings["s4_sector_count"], "value": n4, "note": None}
    return flags


def rank_of_value(ranked, value):
    """1, 2, 3 when `value` equals the highest / 2nd / 3rd highest sectoral PiN (within 1), else 'other'; None when there is nothing to compare."""
    if value is None or not ranked:
        return None
    for i, (_s, v) in enumerate(ranked[:3], start=1):
        if abs(v - value) < 1:
            return i
    return "other"


def analyze(units, previous_units=None, overrides=None):
    """The full preliminary analysis of validated units (see validate_units). Returns a dict with per-unit rows and totals."""
    settings = merge_settings(overrides)
    expected = [s for s in MAIN_SECTORS if any(s in u["pin"] or s in u["severity"] for u in units)]
    prev = {}
    for u in previous_units or []:
        prev[(u["admin2_code"], u["population_group"])] = u
    rows = []
    totals = {"preliminary_pin": 0.0, "units_without_pin": 0}
    pin_counts = {n: {"fired": 0, "not_evaluable": 0} for n in range(1, 7)}
    sev_counts = {n: {"fired": 0, "not_evaluable": 0} for n in range(1, 5)}
    sev_dist, phase5 = {}, []
    stored = {"pin_compared": 0, "pin_match": 0, "pin_mismatch": [], "severity_compared": 0, "severity_match": 0, "severity_mismatch": [],
              "final_pin_total": 0.0, "final_pin_rank": {}}
    for u in units:
        ranked = ranked_pins(u, expected)
        pre, drivers = preliminary_pin(ranked)
        pf = pin_flags(u, ranked, settings, expected, prev.get((u["admin2_code"], u["population_group"])))
        phases = [u["severity"].get(s) for s in expected]
        psev = preliminary_severity(phases)
        sf = severity_flags(u, phases, psev, settings)
        if pre is None:
            totals["units_without_pin"] += 1
        else:
            totals["preliminary_pin"] += pre
        for counts, flags in ((pin_counts, pf), (sev_counts, sf)):
            for n, f in flags.items():
                if f["fired"]:
                    counts[n]["fired"] += 1
                elif f["fired"] is None:
                    counts[n]["not_evaluable"] += 1
        if psev is not None:
            sev_dist[psev] = sev_dist.get(psev, 0) + 1
        if psev == 5 or sf[1]["fired"]:
            phase5.append(u["admin2_code"])
        st = u["stored"]
        spre, ssev, sfin = _num(st.get("preliminary_pin")), _num(st.get("preliminary_severity", st.get("final_severity"))), _num(st.get("final_pin", st.get("total_pin")))
        if spre is not None and pre is not None:
            stored["pin_compared"] += 1
            if abs(spre - pre) < 1:
                stored["pin_match"] += 1
            else:
                stored["pin_mismatch"].append({"unit": u["admin2_code"], "stored": spre, "computed": pre})
        if ssev is not None and psev is not None:
            stored["severity_compared"] += 1
            if int(ssev) == psev:
                stored["severity_match"] += 1
            else:
                stored["severity_mismatch"].append({"unit": u["admin2_code"], "stored": ssev, "computed": psev})
        if sfin is not None:
            stored["final_pin_total"] += sfin
            r = rank_of_value(ranked, sfin)
            stored["final_pin_rank"][str(r)] = stored["final_pin_rank"].get(str(r), 0) + 1
        rows.append({"admin2_code": u["admin2_code"], "admin2": u["admin2"], "population_group": u["population_group"], "population": u["population"],
                     "preliminary_pin": pre, "drivers": drivers, "pin_flags": pf, "preliminary_severity": psev, "severity_flags": sf,
                     "stored": {k: v for k, v in st.items() if k != "evidence"}})
    return {"settings": settings, "expected_sectors": expected, "rows": rows, "totals": totals, "pin_flag_counts": pin_counts,
            "severity_flag_counts": sev_counts, "preliminary_severity_distribution": dict(sorted(sev_dist.items())),
            "phase5_units": phase5, "stored_comparison": stored}


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


# ------------------------------------------------------------------ tool --
def _row_for_csv(r):
    out = {"admin2_code": r["admin2_code"], "admin2": r["admin2"], "population_group": r["population_group"], "population": r["population"],
           "preliminary_pin": r["preliminary_pin"], "pin_drivers": "|".join(r["drivers"]), "preliminary_severity": r["preliminary_severity"]}
    for n, f in r["pin_flags"].items():
        out[f"pin_flag_{n}"] = "" if f["fired"] is None else int(f["fired"])
    for n, f in r["severity_flags"].items():
        out[f"severity_flag_{n}"] = "" if f["fired"] is None else int(f["fired"])
    return out


@register_tool(
    "compute_jiaf_preliminary",
    "Compute the PRELIMINARY JIAF 2 figures from sector inputs (support for the JIAF 2 process; NOT the JIAF method, not endorsed by OCHA or the IASC; "
    "never call the result JIAF-compliant or official). Per unit: the preliminary joint PiN (the highest of the eight main sectors' PiN -- the Mosaic "
    "Method; never an average, never a sum across sectors; AoRs excluded), the PiN flags 1-6 of Reference Table 3A, the preliminary intersectoral "
    "severity from the overlap of sectoral severities, and the severity flags 1-4 of Table 3B1. The national figure is the sum over units. This is not "
    "the Final PiN or the final severity: those are group decisions for flagged units, recorded later, and nothing here decides them. Intersectoral "
    "severity is per unit; there is no national severity and no PiN per severity phase. Several flag thresholds are readings of the manual that are not "
    "verified against OCHA's worksheet formulas: they are settings, echoed in the result, to be confirmed by the analysis team. Reads the same files as "
    "import_jiaf_inputs; give previous_file_path for flag 6. Optionally writes jf_pre_pin, jf_pre_sev, jf_npinfl, jf_nsevfl to an admin layer "
    "(needs confirmation) and a per-unit CSV.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "The sector-input file (OCHA worksheet, HXL table or sector template), as for import_jiaf_inputs."},
            "input_format": {"type": "string", "description": "'auto' (default), 'ocha_worksheet', 'hxl' or 'sector_template'."},
            "sheet_name": {"type": "string"},
            "previous_file_path": {"type": "string", "description": "Optional previous-year file of the same kind, for flag 6."},
            "previous_sheet_name": {"type": "string"},
            "f1_min_sectors": {"type": "integer", "description": "Flag 1 fires at this many sectors with missing/zero PiN or more. Default 1 (the table says 1 or 2)."},
            "f2_pct": {"type": "number", "description": "Flag 2 threshold as a fraction (0.30 = 30%). Default 0.30."},
            "f3_pct": {"type": "number", "description": "Flag 3 threshold as a fraction. Default 0.50."},
            "f4_subpopulation_sectors": {"type": "array", "items": {"type": "string"}, "description": "Sectors that count a sub-population (e.g. nutrition). Flag 4 is evaluated only if given."},
            "f5_share": {"type": "number", "description": "Flag 5 threshold as a share of population. Default 0.90."},
            "f6_pct": {"type": "number", "description": "Flag 6 threshold, increase on last year as a fraction. Default 1.0."},
            "f6_min_previous_pin": {"type": "number", "description": "Flag 6 is only evaluated when last year's PiN is at least this. Default 1000."},
            "s4_sector_count": {"type": "integer", "description": "Severity flag 4 fires when MORE THAN this many sectors are in phase 4 (and the preliminary phase is 4). Default 4."},
            "export_csv_path": {"type": "string", "description": "Optional new .csv file for the per-unit table (refuses to overwrite)."},
            "layer_name": {"type": "string"}, "layer_key_field": {"type": "string", "description": "Admin 2 P-code field on that layer."},
            "write_fields": {"type": "boolean", "description": "With layer_name: write jf_pre_pin, jf_pre_sev, jf_npinfl, jf_nsevfl. Needs confirmation."},
        },
        "required": ["file_path"],
    },
)
def compute_jiaf_preliminary(file_path, input_format="auto", sheet_name=None, previous_file_path=None, previous_sheet_name=None,
                             f1_min_sectors=None, f2_pct=None, f3_pct=None, f4_subpopulation_sectors=None, f5_share=None, f6_pct=None,
                             f6_min_previous_pin=None, s4_sector_count=None, export_csv_path=None, layer_name=None, layer_key_field=None,
                             write_fields=False, confirmed: bool = False):
    try:
        merge_settings({"f1_min_sectors": f1_min_sectors, "f2_pct": f2_pct, "f3_pct": f3_pct, "f4_subpopulation_sectors": f4_subpopulation_sectors,
                        "f5_share": f5_share, "f6_pct": f6_pct, "f6_min_previous_pin": f6_min_previous_pin, "s4_sector_count": s4_sector_count})
    except (ValueError, TypeError) as e:
        return {"error": str(e)}
    overrides = {k: v for k, v in {"f1_min_sectors": f1_min_sectors, "f2_pct": f2_pct, "f3_pct": f3_pct, "f4_subpopulation_sectors": f4_subpopulation_sectors,
                                   "f5_share": f5_share, "f6_pct": f6_pct, "f6_min_previous_pin": f6_min_previous_pin,
                                   "s4_sector_count": s4_sector_count}.items() if v is not None}
    if export_csv_path and os.path.exists(export_csv_path):
        return {"error": f"'{export_csv_path}' already exists; choose a new file name (nothing is overwritten)."}
    loaded = load_units(file_path, input_format, sheet_name)
    if isinstance(loaded, dict):
        return loaded
    units, fmt, notes = loaded
    issues, _summary = validate_units(units)
    previous = None
    if previous_file_path:
        prev_loaded = load_units(previous_file_path, input_format, previous_sheet_name)
        if isinstance(prev_loaded, dict):
            return {"error": "Previous-year file: " + prev_loaded["error"]}
        previous = prev_loaded[0]
        validate_units(previous)
    res = analyze(units, previous, overrides)
    rows = res["rows"]
    nflags = lambda r: sum(1 for f in r["pin_flags"].values() if f["fired"]) + sum(1 for f in r["severity_flags"].values() if f["fired"])  # noqa: E731
    top = sorted(rows, key=lambda r: (-nflags(r), -(r["preliminary_pin"] or 0)))[:_CAP]
    result = {
        "success": True, "statement": STATEMENT, "stage": "preliminary only -- not the Final PiN, not the final severity",
        "format": fmt, "units": len(rows), "notes": notes, "input_issue_count": len(issues), "expected_sectors": res["expected_sectors"],
        "settings": {k: (list(v) if isinstance(v, tuple) else v) for k, v in res["settings"].items()}, "readings_to_confirm": READINGS,
        "national_preliminary_pin": round(res["totals"]["preliminary_pin"], 2), "units_without_any_pin": res["totals"]["units_without_pin"],
        "national_note": "Sum over units of the highest sectoral PiN. It is a preliminary figure, not the Final Joint Overall PiN.",
        "pin_flag_counts": res["pin_flag_counts"], "severity_flag_counts": res["severity_flag_counts"],
        "preliminary_severity_distribution": res["preliminary_severity_distribution"],
        "phase_5_notice": ({"units": res["phase5_units"][:_CAP], "count": len(res["phase5_units"]),
                            "message": "Phase 5 is present in the preliminary results: the manual says this must be flagged immediately to the HCT."}
                           if res["phase5_units"] else None),
        "stored_comparison": {k: (v[:10] if isinstance(v, list) else v) for k, v in res["stored_comparison"].items()},
        "stored_comparison_note": "Compares the file's stored columns with the recomputed values; the stored values are not used.",
        "most_flagged_units": [_row_for_csv(r) for r in top[:10]], "unit_rows_shown": 10,
    }
    if previous is None:
        result["flag_6_note"] = "No previous-year file given, so flag 6 was not evaluated."
    if export_csv_path:
        try:
            table = [_row_for_csv(r) for r in rows]
            with open(export_csv_path, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
                w.writeheader()
                w.writerows(table)
            result["csv_written"] = export_csv_path
        except OSError as e:
            result["csv_warning"] = f"The CSV was not written: {e}"
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
    records = [{"key": key_of(r["admin2_code"], None), "row": r} for r in rows]
    pairs, report = plan_join(records, [(f.id(), key_of(f[layer_key_field], None)) for f in layer.getFeatures()])
    result["join"] = report
    if not write_fields or not pairs:
        return result
    names = ["jf_pre_pin", "jf_pre_sev", "jf_npinfl", "jf_nsevfl"]
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED", "requires_confirmation": True, "is_destructive": True, "tool_name": "compute_jiaf_preliminary",
            "arguments": dict({"file_path": file_path, "input_format": input_format, "sheet_name": sheet_name, "previous_file_path": previous_file_path,
                               "previous_sheet_name": previous_sheet_name, "layer_name": layer_name, "layer_key_field": layer_key_field,
                               "write_fields": True, "confirmed": True}, **overrides),
            "code_snippet": f"# Add/update fields {names} on '{layer_name}' for {report['matched']} matched areas",
            "rationale": f"Data Mutation Preview: write PRELIMINARY JIAF figures to {names} of layer '{layer_name}' ({report['matched']} of {report['layer_features']} areas match).",
            "message": f"Confirmation required before adding fields to '{layer_name}'.", "join": report,
        }
    try:
        with edit_command(layer, "Cartogen AI: preliminary JIAF figures") as owned:
            idx = [add_numeric_field(layer, n) for n in names]
            for fid, rec in pairs:
                r = rec["row"]
                vals = [r["preliminary_pin"], r["preliminary_severity"], sum(1 for f in r["pin_flags"].values() if f["fired"]),
                        sum(1 for f in r["severity_flags"].values() if f["fired"])]
                for i, v in zip(idx, vals):
                    if v is not None:
                        set_value(layer, fid, i, float(v))
        result["fields_written"] = names
        if not owned:
            result["note"] = "The layer is already in edit mode, so the new values are in your edit session and are NOT saved."
    except EditError as e:
        result["write_warning"] = f"Values were not written to the layer: {e}"
    except Exception as e:
        result["write_warning"] = f"Values were not written to the layer: {e}"
    return result
