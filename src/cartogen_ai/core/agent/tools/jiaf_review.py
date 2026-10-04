# -*- coding: utf-8 -*-
"""JIAF 2 analysis support, stage 4a: recording the group's decisions and producing the FINAL figures
(docs/JIAF2_ANALYSIS_SUPPORT_PLAN_2026-10-04.md, sections 2, 4 and 5).

SUPPORT FOR PEOPLE WHO RUN THE JIAF 2 PROCESS. NOT the JIAF method, NOT endorsed by OCHA or the IASC. This module decides nothing: it records what
the multi-partner session decided and applies it.

- PiN decision (manual Step 3.4): for a flagged unit the group decides which SECTOR's PiN is used as the Final PiN. The manual offers the highest or the
  second highest, but the real Yemen 2026 figures use the third highest in 17 of 333 units, so any main sector is accepted and the rank of the chosen
  sector (1st, 2nd, 3rd, other) is reported. A rationale is required ("must be fully and transparently documented", Box 24).
- Severity decision (Step 3.5): for a flagged unit the group's AGREED phase 1-5 with its evidence. Never computed here.
- A unit with no flag keeps the preliminary figures (the manual: "the available evidence converged"). A flagged unit with no recorded decision is
  PENDING: its Final PiN is shown at the highest sectoral PiN as a PROVISIONAL figure and counted separately, and its final severity is left empty.
- `bulk_accepted_flags` closes units whose only fired PiN flags are the listed ones (Annex 6 describes bringing a common pattern, such as the zero PiN of a
  sector with no camps, "in a package, discussed and closed"); it is the team's choice, recorded in the result, and applies to PiN flags only.
- A unit whose preliminary severity cannot be given because sectors in scope have no phase (status `incomplete_coverage`, with lower and upper bounds) is
  never shown as phase 1: it needs a recorded severity decision like a flagged unit.
There is no national severity and no PiN per severity phase (Box 25). Decisions are stored in the QGIS project.

Four things are kept apart, in the result rows, the CSV and the layer fields: the PRELIMINARY result (recomputed, never trusted from the file), the REVIEW
STATUS (no_flag / flags_closed_in_bulk / decided / pending_flagged, and for severity preliminary_accepted / decided / pending_flagged /
incomplete_coverage / no_severity_data), the FINAL result, and the JUSTIFICATION with who decided and when.
"""
import csv
import datetime
import json
import os

from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value
from .jiaf_engine import ranked_pins, rank_of_value, run_analysis
from .jiaf_inputs import MAIN_SECTORS, STATEMENT, VALIDATION_BLOCKERS
from .table_importers import key_of, plan_join

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

SCOPE = "cartogen_ai_jiaf"
KEY = "decisions"
PIN_STATUS_CODE = {"no_flag": 0, "flags_closed_in_bulk": 1, "decided": 2, "pending_flagged": 3}
SEV_STATUS_CODE = {"no_severity_data": 0, "preliminary_accepted": 1, "decided": 2, "pending_flagged": 3, "incomplete_coverage": 4}
EVIDENCE_BASES = ("outcome_indicators", "proxy_indicators", "expert_judgement", "sector_overlap_accepted")
_CAP = 50


def unit_id(code, group=None):
    return f"{code}|{group}" if group else str(code)


# ------------------------------------------------------------------ store --
def load_decisions():
    """{"pin": {unit_id: {...}}, "severity": {unit_id: {...}}}; empty when there is no project or nothing recorded."""
    empty = {"pin": {}, "severity": {}}
    if not QGIS_AVAILABLE:
        return empty
    try:
        raw, ok = QgsProject.instance().readEntry(SCOPE, KEY, "")
        if ok and raw:
            data = json.loads(raw)
            return {"pin": dict(data.get("pin", {})), "severity": dict(data.get("severity", {}))}
    except Exception:
        pass
    return empty


def save_decisions(decisions):
    if not QGIS_AVAILABLE:
        return False
    return bool(QgsProject.instance().writeEntry(SCOPE, KEY, json.dumps(decisions, ensure_ascii=False)))


# ------------------------------------------------------------- validation --
def validate_pin_decisions(items):
    """(clean {unit_id: record}, errors). A rationale and a main sector are required."""
    clean, errors = {}, []
    today = datetime.date.today().isoformat()
    for i, d in enumerate(items or [], start=1):
        code = str((d or {}).get("unit") or "").strip()
        sector = str(d.get("sector") or "").strip().lower().replace(" ", "_")
        why = str(d.get("rationale") or "").strip()
        if not code:
            errors.append(f"PiN decision {i}: unit (Admin 2 P-code) is required.")
        elif sector not in MAIN_SECTORS:
            errors.append(f"PiN decision {i} ({code}): sector must be one of the eight main sectors {MAIN_SECTORS}.")
        elif not why:
            errors.append(f"PiN decision {i} ({code}): a rationale is required (manual Box 24).")
        else:
            clean[unit_id(code, d.get("population_group"))] = {"unit": code, "population_group": d.get("population_group"), "sector": sector,
                                                              "rationale": why, "decided_by": str(d.get("decided_by") or "").strip() or None, "date": today}
    return clean, errors


def validate_severity_decisions(items):
    """(clean {unit_id: record}, errors). An integer phase 1-5, an evidence basis and the evidence text are required."""
    clean, errors = {}, []
    today = datetime.date.today().isoformat()
    for i, d in enumerate(items or [], start=1):
        code = str((d or {}).get("unit") or "").strip()
        try:
            f = float(d.get("phase"))
            phase = int(f) if f == int(f) and 1 <= f <= 5 else None
        except (TypeError, ValueError):
            phase = None
        basis = str(d.get("evidence_basis") or "").strip().lower()
        evidence = str(d.get("evidence") or "").strip()
        if not code:
            errors.append(f"Severity decision {i}: unit (Admin 2 P-code) is required.")
        elif phase is None:
            errors.append(f"Severity decision {i} ({code}): phase must be a whole number from 1 to 5.")
        elif basis not in EVIDENCE_BASES:
            errors.append(f"Severity decision {i} ({code}): evidence_basis must be one of {list(EVIDENCE_BASES)}.")
        elif not evidence:
            errors.append(f"Severity decision {i} ({code}): the evidence behind the agreed phase is required.")
        else:
            clean[unit_id(code, d.get("population_group"))] = {
                "unit": code, "population_group": d.get("population_group"), "phase": phase, "evidence_basis": basis, "evidence": evidence,
                "decided_by": str(d.get("decided_by") or "").strip() or None, "date": today}
    return clean, errors


# ------------------------------------------------------------- finalising --
def _fired(flags):
    return [n for n, f in flags.items() if f["fired"]]


def finalize(units, analysis, decisions, bulk_accepted_flags=(), bulk_info=None):
    """Apply the recorded decisions to an `analyze` result. Returns (rows, summary). Pure."""
    expected = analysis["expected_sectors"]
    by_unit = {unit_id(u["admin2_code"], u["population_group"]): u for u in units}
    bulk = set(int(x) for x in bulk_accepted_flags or ())
    issues, rows = [], []
    final_total = provisional_total = 0.0
    counts = {"pin_status": {}, "severity_status": {}, "rank": {}}
    sev_dist = {}
    for r in analysis["rows"]:
        uid = unit_id(r["admin2_code"], r["population_group"])
        u = by_unit[uid]
        ranked = ranked_pins(u, expected)
        pin_fired, sev_fired = _fired(r["pin_flags"]), _fired(r["severity_flags"])
        pd, sd = decisions["pin"].get(uid), decisions["severity"].get(uid)
        fin_pin, status, rank, sector, note = r["preliminary_pin"], None, None, None, None
        if pd is not None:
            chosen = u["pin"].get(pd["sector"])
            if chosen is None:
                issues.append({"unit": uid, "problem": f"decision names {pd['sector']}, which has no PiN in this unit; the decision is ignored"})
                pd = None
        if pd is not None:
            fin_pin, status, sector, note = u["pin"][pd["sector"]], "decided", pd["sector"], pd.get("rationale")
            rank = rank_of_value(ranked, fin_pin)
        elif not pin_fired:
            status = "no_flag"
        elif set(pin_fired) <= bulk:
            status = "flags_closed_in_bulk"
            note = (bulk_info or {}).get("rationale")
        else:
            status = "pending_flagged"
        if fin_pin is not None:
            final_total += fin_pin
            if status == "pending_flagged":
                provisional_total += fin_pin
        counts["pin_status"][status] = counts["pin_status"].get(status, 0) + 1
        if rank is not None:
            counts["rank"][str(rank)] = counts["rank"].get(str(rank), 0) + 1
        psev = r["preliminary_severity"]
        cov = r["severity_coverage"]
        fin_sev, sstatus, sev_evidence = None, None, None
        if sd is not None:
            fin_sev, sstatus, sev_evidence = sd["phase"], "decided", sd.get("evidence")
        elif cov["status"] == "incomplete_coverage":
            sstatus = "incomplete_coverage"
        elif psev is None:
            sstatus = "no_severity_data"
        elif not sev_fired:
            fin_sev, sstatus = psev, "preliminary_accepted"
        else:
            sstatus = "pending_flagged"
        counts["severity_status"][sstatus] = counts["severity_status"].get(sstatus, 0) + 1
        if fin_sev is not None:
            sev_dist[fin_sev] = sev_dist.get(fin_sev, 0) + 1
        rows.append({"admin2_code": r["admin2_code"], "admin2": r["admin2"], "population_group": r["population_group"], "population": r["population"],
                     "preliminary_pin": r["preliminary_pin"], "pin_drivers": r["drivers"], "pin_flags_fired": pin_fired,
                     "final_pin": fin_pin, "final_pin_status": status, "final_pin_sector": sector, "final_pin_rank": rank, "pin_decision_note": note,
                     "pin_decided_by": pd.get("decided_by") if pd else (bulk_info or {}).get("decided_by") if status == "flags_closed_in_bulk" else None,
                     "pin_decision_date": pd.get("date") if pd else (bulk_info or {}).get("date") if status == "flags_closed_in_bulk" else None,
                     "pin_missing_sectors": r["pin_coverage"]["missing_sectors"], "pin_zero_sectors": r["pin_coverage"]["zero_sectors"],
                     "preliminary_severity": psev, "severity_coverage_status": cov["status"], "severity_lower": cov["lower"], "severity_upper": cov["upper"],
                     "severity_missing_sectors": cov["missing_sectors"], "severity_flags_fired": sev_fired,
                     "final_severity": fin_sev, "final_severity_status": sstatus,
                     "severity_evidence_basis": sd.get("evidence_basis") if sd else None, "severity_evidence": sev_evidence,
                     "severity_decided_by": sd.get("decided_by") if sd else None, "severity_decision_date": sd.get("date") if sd else None})
    for kind in ("pin", "severity"):
        for uid in decisions[kind]:
            if uid not in by_unit:
                issues.append({"unit": uid, "problem": f"a {kind} decision is recorded for a unit that is not in this file; it is ignored"})
    pending_pin = counts["pin_status"].get("pending_flagged", 0)
    pending_sev = counts["severity_status"].get("pending_flagged", 0)
    incomplete_sev = counts["severity_status"].get("incomplete_coverage", 0)
    summary = {
        "final_pin_total": round(final_total, 2), "provisional_part_of_total": round(provisional_total, 2),
        "provisional": bool(pending_pin), "pending_pin_units": pending_pin, "pending_severity_units": pending_sev, "incomplete_coverage_severity_units": incomplete_sev,
        "pin_status_counts": counts["pin_status"], "severity_status_counts": counts["severity_status"],
        "chosen_sector_rank_counts": counts["rank"], "final_severity_distribution": dict(sorted(sev_dist.items())),
        "decision_issues": issues,
        "bulk_accepted_flags": sorted(bulk),
        "bulk_closure": ({"flags": sorted(bulk), "rationale": (bulk_info or {}).get("rationale"), "decided_by": (bulk_info or {}).get("decided_by"),
                          "date": (bulk_info or {}).get("date"), "units_closed": counts["pin_status"].get("flags_closed_in_bulk", 0)} if bulk else None),
        "phase_5_units": [r["admin2_code"] for r in rows if 5 in (r["final_severity"], r["preliminary_severity"]) or 1 in r["severity_flags_fired"]],
    }
    return rows, summary


def _csv_row(r):
    """One row with the four things kept apart: preliminary result, review status, final result, justification (+ who and when)."""
    return {"admin2_code": r["admin2_code"], "admin2": r["admin2"], "population_group": r["population_group"], "population": r["population"],
            "preliminary_pin": r["preliminary_pin"], "pin_missing_sectors": "|".join(r["pin_missing_sectors"]),
            "pin_zero_sectors": "|".join(r["pin_zero_sectors"]), "pin_flags_fired": "|".join(str(n) for n in r["pin_flags_fired"]),
            "pin_review_status": r["final_pin_status"], "final_pin": r["final_pin"], "final_pin_sector": r["final_pin_sector"],
            "final_pin_rank": r["final_pin_rank"], "pin_justification": r["pin_decision_note"], "pin_decided_by": r["pin_decided_by"],
            "pin_decision_date": r["pin_decision_date"],
            "preliminary_severity": r["preliminary_severity"], "severity_coverage_status": r["severity_coverage_status"],
            "severity_lower_bound": r["severity_lower"], "severity_upper_bound": r["severity_upper"],
            "severity_missing_sectors": "|".join(r["severity_missing_sectors"]),
            "severity_flags_fired": "|".join(str(n) for n in r["severity_flags_fired"]),
            "severity_review_status": r["final_severity_status"], "final_severity": r["final_severity"],
            "severity_evidence_basis": r["severity_evidence_basis"], "severity_justification": r["severity_evidence"],
            "severity_decided_by": r["severity_decided_by"], "severity_decision_date": r["severity_decision_date"],
            "evidence_and_comments": "; ".join(x for x in (r["pin_decision_note"], r["severity_evidence"]) if x)}


# ------------------------------------------------------------------ tools --
@register_tool(
    "record_jiaf_decisions",
    "Record the multi-partner group's JIAF 2 decisions for flagged units (support for the JIAF 2 process; not endorsed by OCHA or the IASC; this tool "
    "decides nothing, it only records what the group decided). pin_decisions: for a flagged unit, which main sector's PiN is used as the Final PiN "
    "(the manual offers the highest or second highest; any main sector is accepted and the rank of the chosen one is reported) with the rationale "
    "(required). severity_decisions: the agreed intersectoral severity phase 1-5 for a flagged unit with the evidence basis (outcome_indicators, "
    "proxy_indicators, expert_judgement or sector_overlap_accepted) and the evidence (required). Stored in the QGIS project, merged with earlier "
    "records unless replace=true. Never invent a decision; ask the team.",
    {
        "type": "object",
        "properties": {
            "pin_decisions": {"type": "array", "items": {"type": "object", "properties": {
                "unit": {"type": "string", "description": "Admin 2 P-code."}, "population_group": {"type": "string"},
                "sector": {"type": "string", "description": "Main sector whose PiN becomes the Final PiN."},
                "rationale": {"type": "string"}, "decided_by": {"type": "string", "description": "e.g. 'HCT working session, 12 Oct'."}}}},
            "severity_decisions": {"type": "array", "items": {"type": "object", "properties": {
                "unit": {"type": "string"}, "population_group": {"type": "string"}, "phase": {"type": "integer"},
                "evidence_basis": {"type": "string"}, "evidence": {"type": "string"}, "decided_by": {"type": "string"}}}},
            "replace": {"type": "boolean", "description": "Replace all stored decisions instead of merging."},
        },
    },
)
def record_jiaf_decisions(pin_decisions=None, severity_decisions=None, replace=False):
    pin, e1 = validate_pin_decisions(pin_decisions)
    sev, e2 = validate_severity_decisions(severity_decisions)
    if e1 or e2:
        return {"error": "Nothing was saved. " + " ".join(e1 + e2)}
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    stored = {"pin": {}, "severity": {}} if replace else load_decisions()
    stored["pin"].update(pin)
    stored["severity"].update(sev)
    if not save_decisions(stored):
        return {"error": "The project refused the record (is a project open?)."}
    return {"success": True, "statement": STATEMENT, "recorded_now": {"pin": len(pin), "severity": len(sev)},
            "stored_totals": {"pin": len(stored["pin"]), "severity": len(stored["severity"])},
            "phase_5_notice": ([d["unit"] for d in sev.values() if d["phase"] == 5] or None),
            "note": "Stored in the QGIS project (save the project to keep it). Run finalize_jiaf_results to apply them."}


@register_tool(
    "get_jiaf_decisions",
    "Read the JIAF 2 group decisions stored in the project by record_jiaf_decisions (support for the JIAF 2 process; not endorsed by OCHA or the IASC).",
    {"type": "object", "properties": {}},
)
def get_jiaf_decisions():
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    d = load_decisions()
    return {"success": True, "statement": STATEMENT, "decisions": d, "counts": {"pin": len(d["pin"]), "severity": len(d["severity"])}}


@register_tool(
    "finalize_jiaf_results",
    "Apply the recorded JIAF 2 group decisions to the preliminary figures and report the FINAL results (support for the JIAF 2 process; NOT the JIAF "
    "method, not endorsed by OCHA or the IASC; never call the result JIAF-compliant or official). A unit with no flag keeps the preliminary figures; a "
    "flagged unit uses its recorded decision; a flagged unit with no decision is PENDING: its Final PiN is shown at the highest sectoral PiN as a "
    "provisional figure (counted and totalled separately) and its final severity is left empty. The Final PiN total is the sum over units; there is no "
    "national severity and no PiN per severity phase. bulk_accepted_flags (e.g. [1]) closes units whose only fired PiN flags are those; this is an "
    "analysis-team decision and REQUIRES bulk_rationale (why) and ideally bulk_decided_by, which are recorded in the result and against every unit closed. The flag "
    "conditions are unverified interpretations of the manual (see validation_blockers in the result): the number of pending units depends on them. Reads the same files and uses the same flag settings as compute_jiaf_preliminary. Optionally writes jf_fin_pin, jf_fin_sev, "
    "jf_pin_rk to an admin layer (needs confirmation) and a per-unit CSV with the Evidence & Comments (never overwrites).",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string"}, "input_format": {"type": "string"}, "sheet_name": {"type": "string"},
            "previous_file_path": {"type": "string"}, "previous_sheet_name": {"type": "string"},
            "bulk_accepted_flags": {"type": "array", "items": {"type": "integer"}, "description": "PiN flag numbers the team agreed to close in bulk, e.g. [1]. Needs bulk_rationale."},
            "bulk_rationale": {"type": "string", "description": "Why the team closed these flags in bulk (required with bulk_accepted_flags)."},
            "bulk_decided_by": {"type": "string", "description": "Who decided, e.g. 'JIAF analysis group, 12 Oct'."},
            "f1_min_sectors": {"type": "integer"}, "f1_count_missing": {"type": "boolean"}, "f1_count_zero": {"type": "boolean"},
            "sectors_in_scope": {"type": "array", "items": {"type": "string"}, "description": "Main sectors the HCT activated. Default: all eight; a sector with no value is missing, never phase 1."},
            "zero_severity_as": {"type": "string", "description": "'not_applicable' (default) or 'missing'."},
            "f2_pct": {"type": "number"}, "f3_pct": {"type": "number"},
            "f4_subpopulation_sectors": {"type": "array", "items": {"type": "string"}}, "f5_share": {"type": "number"},
            "f6_pct": {"type": "number"}, "f6_min_previous_pin": {"type": "number"}, "s4_sector_count": {"type": "integer"},
            "export_csv_path": {"type": "string", "description": "Optional new .csv file (refuses to overwrite)."},
            "layer_name": {"type": "string"}, "layer_key_field": {"type": "string"},
            "write_fields": {"type": "boolean", "description": "With layer_name: write jf_fin_pin, jf_fin_sev, jf_pin_rk. Needs confirmation."},
        },
        "required": ["file_path"],
    },
)
def finalize_jiaf_results(file_path, input_format="auto", sheet_name=None, previous_file_path=None, previous_sheet_name=None,
                          bulk_accepted_flags=None, bulk_rationale=None, bulk_decided_by=None, sectors_in_scope=None, zero_severity_as=None,
                          f1_min_sectors=None, f1_count_missing=None, f1_count_zero=None, f2_pct=None, f3_pct=None, f4_subpopulation_sectors=None, f5_share=None,
                          f6_pct=None, f6_min_previous_pin=None, s4_sector_count=None, export_csv_path=None, layer_name=None, layer_key_field=None,
                          write_fields=False, confirmed: bool = False):
    overrides = {k: v for k, v in {"sectors_in_scope": sectors_in_scope, "zero_severity_as": zero_severity_as, "f1_min_sectors": f1_min_sectors,
                                   "f1_count_missing": f1_count_missing, "f1_count_zero": f1_count_zero, "f2_pct": f2_pct, "f3_pct": f3_pct, "f4_subpopulation_sectors": f4_subpopulation_sectors,
                                   "f5_share": f5_share, "f6_pct": f6_pct, "f6_min_previous_pin": f6_min_previous_pin,
                                   "s4_sector_count": s4_sector_count}.items() if v is not None}
    if bulk_accepted_flags and any(n not in (1, 2, 3, 4, 5, 6) for n in bulk_accepted_flags):
        return {"error": "bulk_accepted_flags must be PiN flag numbers from 1 to 6."}
    if bulk_accepted_flags and not str(bulk_rationale or "").strip():
        return {"error": "bulk_accepted_flags needs bulk_rationale: closing flags in bulk is an analysis-team decision and must be recorded with its reason."}
    if export_csv_path and os.path.exists(export_csv_path):
        return {"error": f"'{export_csv_path}' already exists; choose a new file name (nothing is overwritten)."}
    bulk_info = ({"rationale": str(bulk_rationale).strip(), "decided_by": str(bulk_decided_by or "").strip() or None, "date": datetime.date.today().isoformat()}
                 if bulk_accepted_flags else None)
    try:
        run = run_analysis(file_path, input_format, sheet_name, previous_file_path, previous_sheet_name, overrides)
    except (ValueError, TypeError) as e:
        return {"error": str(e)}
    if "error" in run:
        return run
    decisions = load_decisions()
    rows, summary = finalize(run["units"], run["analysis"], decisions, bulk_accepted_flags or (), bulk_info)
    result = {
        "success": True, "statement": STATEMENT, "format": run["format"], "units": len(rows),
        "settings": {k: (list(v) if isinstance(v, tuple) else v) for k, v in run["analysis"]["settings"].items()},
        "decisions_stored": {"pin": len(decisions["pin"]), "severity": len(decisions["severity"])},
        "validation_blockers": VALIDATION_BLOCKERS,
        **summary,
        "total_note": ("PROVISIONAL: %d flagged unit(s) have no recorded PiN decision and are included at the highest sectoral PiN." % summary["pending_pin_units"]
                       if summary["provisional"] else "Every flagged unit is decided or closed; the total is the sum of the Final PiN over units."),
        "severity_note": "Intersectoral severity is per unit only; there is no national severity and no PiN per severity phase.",
        "pending_units_shown": [{"unit": r["admin2_code"], "pin_flags": r["pin_flags_fired"], "severity_flags": r["severity_flags_fired"]}
                                for r in rows if "pending_flagged" in (r["final_pin_status"], r["final_severity_status"])
                                or r["final_severity_status"] == "incomplete_coverage"][:_CAP],
    }
    if summary["phase_5_units"]:
        result["phase_5_notice"] = "Phase 5 appears in the preliminary or final results: the manual says this must be flagged immediately to the HCT."
    if export_csv_path:
        try:
            table = [_csv_row(r) for r in rows]
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
    pairs, report = plan_join([{"key": key_of(r["admin2_code"], None), "row": r} for r in rows],
                              [(f.id(), key_of(f[layer_key_field], None)) for f in layer.getFeatures()])
    result["join"] = report
    if not write_fields or not pairs:
        return result
    names = ["jf_fin_pin", "jf_fin_sev", "jf_pin_rk", "jf_pin_st", "jf_sev_st"]
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED", "requires_confirmation": True, "is_destructive": True, "tool_name": "finalize_jiaf_results",
            "arguments": dict({"file_path": file_path, "input_format": input_format, "sheet_name": sheet_name, "previous_file_path": previous_file_path,
                               "previous_sheet_name": previous_sheet_name, "bulk_accepted_flags": bulk_accepted_flags,
                               "bulk_rationale": bulk_rationale, "bulk_decided_by": bulk_decided_by, "layer_name": layer_name,
                               "layer_key_field": layer_key_field, "write_fields": True, "confirmed": True}, **overrides),
            "code_snippet": f"# Add/update fields {names} on '{layer_name}' for {report['matched']} matched areas",
            "rationale": (f"Data Mutation Preview: write the JIAF final figures to {names} of layer '{layer_name}' ({report['matched']} of "
                          f"{report['layer_features']} areas match)." + (" The PiN total is provisional." if summary["provisional"] else "")),
            "message": f"Confirmation required before adding fields to '{layer_name}'.", "join": report,
        }
    try:
        with edit_command(layer, "Cartogen AI: final JIAF figures") as owned:
            idx = [add_numeric_field(layer, n) for n in names]
            for fid, rec in pairs:
                r = rec["row"]
                rank = r["final_pin_rank"]
                vals = [r["final_pin"], r["final_severity"], (rank if isinstance(rank, int) else (4 if rank == "other" else None)),
                        PIN_STATUS_CODE.get(r["final_pin_status"]), SEV_STATUS_CODE.get(r["final_severity_status"])]
                for i, v in zip(idx, vals):
                    if v is not None:
                        set_value(layer, fid, i, float(v))
        result["fields_written"] = names
        result["field_note"] = ("jf_pin_rk: 1/2/3 = the chosen sector was the 1st/2nd/3rd highest, 4 = another rank; empty when no decision was recorded. "
                                "jf_pin_st (PiN review status): 0 no flag, 1 flags closed in bulk, 2 decided, 3 pending. "
                                "jf_sev_st (severity review status): 0 no data, 1 preliminary accepted, 2 decided, 3 pending flagged, 4 incomplete coverage.")
        if not owned:
            result["note"] = "The layer is already in edit mode, so the new values are in your edit session and are NOT saved."
    except EditError as e:
        result["write_warning"] = f"Values were not written to the layer: {e}"
    except Exception as e:
        result["write_warning"] = f"Values were not written to the layer: {e}"
    return result
