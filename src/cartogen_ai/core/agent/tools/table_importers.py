# -*- coding: utf-8 -*-
"""File-based importers for published humanitarian tables: IPC phase classification, INFORM Risk and UNOSAT damage points (H7,
docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md). No network and no credentials: the user supplies a CSV/Excel file
(typically downloaded from HDX).

UNVERIFIED: the column layouts below are alias lists written from general knowledge of how these tables are usually published, NOT
checked against real HDX files (none were available when this was written). That is why the tool never guesses silently:
- every role is matched by case/punctuation-insensitive alias; a role matched by several different columns is reported as ambiguous
  and left unmapped, and a role matched by none is reported as missing;
- the user (or the model, after asking) can always pass an explicit `mapping` {role: column}, which wins over detection;
- the result lists the mapping that was actually used so it can be checked against the file.

Validation never repairs a value: a phase outside 1-5, a score outside 0-10, a negative or non-numeric population, a coordinate out of
range or an unknown damage class is reported and the row's value is left empty (a missing phase is NOT phase 1). Duplicate area keys are
reported and excluded from any join, not merged.

Pure logic (everything except the layer join) is unit tested offline; the join needs QGIS (tests/test_table_importers_live.py, written
without a local QGIS).
"""
import os
import re

from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_RESPONSE_CAP = 50

# role -> (aliases, required). Aliases are compared after _norm().
SPECS = {
    "ipc": {
        "area_code": (["admin_pcode", "pcode", "p_code", "adm2_pcode", "adm1_pcode", "adm3_pcode", "admin2_pcode", "admin1_pcode", "area_code", "code"], False),
        "area_name": (["area", "area_name", "admin_name", "admin2", "admin1", "adm2_en", "adm1_en", "district", "name", "region"], False),
        "phase": (["phase", "overall_phase", "area_phase", "ipc_phase", "current_phase", "phase_class", "cl_phase", "classification"], True),
        "population": (["population", "total_population", "analysed_population", "population_analysed", "pop", "total_pop"], False),
        "phase3plus_population": (["phase3plus", "phase_3_plus", "p3plus", "population_phase3plus", "people_phase3plus", "pop_phase3plus", "phase_3+", "p3+"], False),
        "period": (["period", "analysis_period", "projection_period", "validity_period", "date", "reference_period"], False),
    },
    "inform": {
        "area_code": (["admin_pcode", "pcode", "p_code", "iso3", "adm1_pcode", "adm2_pcode", "area_code", "code"], False),
        "area_name": (["area", "area_name", "admin_name", "country", "admin1", "admin2", "district", "name", "region"], False),
        "risk": (["inform_risk", "risk", "risk_index", "inform", "inform_risk_index", "overall_risk"], True),
        "hazard_exposure": (["hazard_exposure", "hazard_and_exposure", "hazard", "hazard_exposure_index"], False),
        "vulnerability": (["vulnerability", "vulnerability_index"], False),
        "lack_of_coping_capacity": (["lack_of_coping_capacity", "coping_capacity", "lack_coping", "lack_of_coping"], False),
    },
    "unosat": {
        "latitude": (["latitude", "lat", "y", "ycoord", "point_y"], True),
        "longitude": (["longitude", "lon", "long", "lng", "x", "xcoord", "point_x"], True),
        "damage_class": (["main_damage_site_class", "damage", "damage_class", "damage_level", "damage_status", "sitedamage", "damage_site", "class", "status", "main_damage"], True),
        "site_id": (["id", "site_id", "objectid", "fid", "unosat_id", "site"], False),
    },
}
KINDS = tuple(SPECS)

# Normalised damage vocabulary. Only these (and their listed spellings) are accepted; anything else is reported, never guessed.
DAMAGE_CLASSES = {
    "destroyed": "destroyed", "destroyed building": "destroyed",
    "severe damage": "severe", "severely damaged": "severe", "severe": "severe",
    "moderate damage": "moderate", "moderately damaged": "moderate", "moderate": "moderate",
    "possible damage": "possible", "possibly damaged": "possible", "possible": "possible",
    "no visible damage": "none", "no damage": "none", "not damaged": "none", "none": "none",
}

IPC_FIELDS = {"phase": "ipc_phase", "population": "ipc_pop", "phase3plus_population": "ipc_p3plus"}
INFORM_FIELDS = {"risk": "inf_risk", "hazard_exposure": "inf_haz", "vulnerability": "inf_vuln", "lack_of_coping_capacity": "inf_coping"}
JOIN_FIELDS = {"ipc": IPC_FIELDS, "inform": INFORM_FIELDS}


def _norm(text):
    return re.sub(r"[^a-z0-9+]+", "_", str(text).strip().lower()).strip("_")


def detect_columns(columns, kind, mapping=None):
    """Role -> column for `kind`. Returns (used, missing, ambiguous, problems). An explicit mapping wins; an explicit mapping naming a
    column that is not in the file is a problem (never silently replaced by detection)."""
    spec = SPECS[kind]
    cols = list(columns)
    used, ambiguous, problems = {}, {}, []
    mapping = mapping or {}
    for role, col in mapping.items():
        if role not in spec:
            problems.append(f"Unknown role '{role}' for kind '{kind}'. Roles: {sorted(spec)}.")
        elif col not in cols:
            problems.append(f"Mapped column '{col}' for role '{role}' is not in the file. Columns: {cols}.")
        else:
            used[role] = col
    normalised = {c: _norm(c) for c in cols}
    for role, (aliases, _required) in spec.items():
        if role in used or role in mapping:
            continue
        alias_set = {_norm(a) for a in aliases}
        hits = [c for c in cols if normalised[c] in alias_set]
        if len(hits) == 1:
            used[role] = hits[0]
        elif len(hits) > 1:
            ambiguous[role] = hits
    missing = [r for r, (_a, req) in spec.items() if req and r not in used]
    return used, missing, ambiguous, problems


def _blank(v):
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, float) and v != v)


def _number(v):
    if _blank(v) or isinstance(v, bool):
        return None
    if isinstance(v, str):
        v = v.strip().replace(",", "")
        if v.endswith("%"):
            return None
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def parse_phase(v):
    """IPC phase 1-5 from 3, 3.0, '3', 'Phase 3', 'Phase 3 - Crisis'; anything else (including '3+', 'Famine' alone, 0, 6) is None."""
    if _blank(v):
        return None
    if isinstance(v, str):
        m = re.fullmatch(r"\s*(?:ipc\s*)?(?:phase\s*)?([1-5])\s*(?:[-:(].*)?", v.strip(), flags=re.I)
        return int(m.group(1)) if m else None
    n = _number(v)
    return int(n) if n is not None and n in (1, 2, 3, 4, 5) else None


def key_of(code, name):
    """Join key: the P-code (trimmed, case-insensitive) when present, else the name (casefolded, whitespace collapsed)."""
    if not _blank(code):
        return "code:" + str(code).strip().upper()
    if not _blank(name):
        return "name:" + " ".join(str(name).split()).casefold()
    return None


def normalise_rows(rows, kind, used):
    """Validated records plus a list of issues. Values that fail validation become None and are reported (row numbers are 1-based
    data rows)."""
    records, issues = [], []
    for i, raw in enumerate(rows, start=1):
        get = lambda role: raw.get(used[role]) if role in used else None  # noqa: E731
        rec = {"row": i}

        def bad(role, why):
            issues.append({"row": i, "role": role, "value": None if _blank(get(role)) else str(get(role)), "problem": why})

        if kind == "ipc":
            rec["area_code"] = None if _blank(get("area_code")) else str(get("area_code")).strip()
            rec["area_name"] = None if _blank(get("area_name")) else str(get("area_name")).strip()
            rec["key"] = key_of(rec["area_code"], rec["area_name"])
            rec["phase"] = parse_phase(get("phase"))
            if rec["phase"] is None:
                bad("phase", "missing" if _blank(get("phase")) else "not a phase from 1 to 5; left empty (not treated as phase 1)")
            for role in ("population", "phase3plus_population"):
                n = _number(get(role)) if role in used else None
                if role in used and n is None and not _blank(get(role)):
                    bad(role, "not a number")
                elif n is not None and n < 0:
                    bad(role, "negative")
                    n = None
                rec[role] = n
            if rec["population"] is not None and rec["phase3plus_population"] is not None and rec["phase3plus_population"] > rec["population"] + 1e-9:
                bad("phase3plus_population", "larger than the area's population; both left as given, check the file")
            rec["period"] = None if _blank(get("period")) else str(get("period")).strip()
        elif kind == "inform":
            rec["area_code"] = None if _blank(get("area_code")) else str(get("area_code")).strip()
            rec["area_name"] = None if _blank(get("area_name")) else str(get("area_name")).strip()
            rec["key"] = key_of(rec["area_code"], rec["area_name"])
            for role in ("risk", "hazard_exposure", "vulnerability", "lack_of_coping_capacity"):
                n = _number(get(role)) if role in used else None
                if role in used and n is None and not _blank(get(role)):
                    bad(role, "not a number")
                elif n is not None and not 0 <= n <= 10:
                    bad(role, "outside the 0-10 INFORM scale; left empty")
                    n = None
                rec[role] = n
        else:  # unosat
            lat, lon = _number(get("latitude")), _number(get("longitude"))
            if lat is None or not -90 <= lat <= 90:
                bad("latitude", "missing, not a number or outside -90..90")
                lat = None
            if lon is None or not -180 <= lon <= 180:
                bad("longitude", "missing, not a number or outside -180..180")
                lon = None
            rec["latitude"], rec["longitude"] = lat, lon
            raw_class = get("damage_class")
            cls = None if _blank(raw_class) else DAMAGE_CLASSES.get(str(raw_class).strip().lower())
            if cls is None:
                bad("damage_class", "missing" if _blank(raw_class) else "unrecognised damage class; left empty, not guessed")
            rec["damage_class"] = cls
            rec["site_id"] = None if _blank(get("site_id")) else str(get("site_id")).strip()
        records.append(rec)
    return records, issues


def duplicate_keys(records):
    seen, dup = {}, set()
    for r in records:
        k = r.get("key")
        if k is None:
            continue
        if k in seen:
            dup.add(k)
        seen[k] = True
    return dup


def plan_join(records, layer_keys):
    """Match records to layer features. `layer_keys` = [(feature_id, key)]. A key that is duplicated in the table or on the layer is
    never matched (ambiguous), nothing is merged or guessed. Returns (pairs [(feature_id, record)], report)."""
    table_dup = duplicate_keys(records)
    layer_count = {}
    for _fid, k in layer_keys:
        if k is not None:
            layer_count[k] = layer_count.get(k, 0) + 1
    by_key = {r["key"]: r for r in records if r.get("key") and r["key"] not in table_dup}
    pairs, unmatched_layer, ambiguous_layer = [], [], []
    matched = set()
    for fid, k in layer_keys:
        if k is None:
            unmatched_layer.append(fid)
        elif layer_count[k] > 1 or k in table_dup:
            ambiguous_layer.append(fid)
        elif k in by_key:
            pairs.append((fid, by_key[k]))
            matched.add(k)
        else:
            unmatched_layer.append(fid)
    unmatched_table = sorted(k for k in by_key if k not in matched)
    return pairs, {
        "matched": len(pairs), "layer_features": len(layer_keys),
        "layer_features_unmatched": len(unmatched_layer),
        "layer_features_ambiguous": len(ambiguous_layer),
        "table_rows_unmatched": len(unmatched_table), "table_rows_unmatched_keys": unmatched_table[:_RESPONSE_CAP],
        "table_duplicate_keys": sorted(table_dup)[:_RESPONSE_CAP],
    }


def summarise(records, kind):
    if kind == "ipc":
        counts = {}
        for r in records:
            if r["phase"] is not None:
                counts[r["phase"]] = counts.get(r["phase"], 0) + 1
        return {"areas_by_phase": {str(k): counts[k] for k in sorted(counts)},
                "areas_without_valid_phase": sum(1 for r in records if r["phase"] is None)}
    if kind == "inform":
        vals = [r["risk"] for r in records if r["risk"] is not None]
        return {"risk_min": min(vals) if vals else None, "risk_max": max(vals) if vals else None,
                "areas_without_risk": len(records) - len(vals)}
    counts = {}
    for r in records:
        if r["damage_class"]:
            counts[r["damage_class"]] = counts.get(r["damage_class"], 0) + 1
    return {"points_by_damage_class": counts, "points_with_valid_coordinates": sum(1 for r in records if r["latitude"] is not None and r["longitude"] is not None),
            "points_without_damage_class": sum(1 for r in records if r["damage_class"] is None)}


# ---------------------------------------------------------------- tool --
def _layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


@register_tool(
    "import_humanitarian_table",
    "Read a published humanitarian table from a CSV/Excel file the user supplies (typically downloaded from HDX) and validate it: "
    "kind 'ipc' (IPC area phase 1-5, population, phase 3+ population), 'inform' (INFORM Risk 0-10 scores) or 'unosat' (damage points "
    "with coordinates and damage class). Columns are matched by common names, but the layouts are UNVERIFIED against real files: the "
    "result shows the mapping used, and anything not matched or ambiguous is listed, so check it and pass an explicit `mapping` "
    "({role: column}) if needed. Nothing is repaired or imputed: an invalid or missing value is reported and left empty (a missing "
    "IPC phase is not phase 1). For ipc and inform, giving `layer_name` and `layer_key_field` (P-code preferred) reports how the rows "
    "join to the admin layer and, with `write_fields`, writes the values to it as new numeric fields (needs confirmation); unmatched "
    "and duplicate keys are never guessed. For unosat, load the points with load_tabular_data_as_layer using the detected "
    "latitude/longitude columns. Official-source values: quote the file and its date, not this tool, as the source.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the .csv/.xlsx/.xls file."},
            "kind": {"type": "string", "description": "'ipc', 'inform' or 'unosat'."},
            "mapping": {"type": "object", "description": "Optional explicit {role: column}. Roles -- ipc: area_code, area_name, phase, population, phase3plus_population, period; inform: area_code, area_name, risk, hazard_exposure, vulnerability, lack_of_coping_capacity; unosat: latitude, longitude, damage_class, site_id."},
            "sheet_name": {"type": "string", "description": "Sheet for Excel files. Defaults to the first."},
            "delimiter": {"type": "string", "description": "CSV delimiter. Defaults to ','."},
            "layer_name": {"type": "string", "description": "Optional admin polygon layer to join to (ipc/inform)."},
            "layer_key_field": {"type": "string", "description": "Field on that layer holding the P-code (or name when the file has no code)."},
            "write_fields": {"type": "boolean", "description": "With layer_name: write the values to the layer as new numeric fields (ipc_phase, ipc_pop, ipc_p3plus / inf_risk, inf_haz, inf_vuln, inf_coping). Needs confirmation."},
        },
        "required": ["file_path", "kind"],
    },
)
def import_humanitarian_table(file_path, kind, mapping=None, sheet_name=None, delimiter=",", layer_name=None, layer_key_field=None,
                              write_fields=False, confirmed: bool = False):
    kind = str(kind or "").strip().lower()
    if kind not in SPECS:
        return {"error": f"kind must be one of {list(KINDS)}."}
    if mapping is not None and not isinstance(mapping, dict):
        return {"error": "mapping must be an object {role: column}."}
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    from .reporting_tools import _read_tabular_rows
    try:
        rows, columns = _read_tabular_rows(file_path, sheet_name=sheet_name, delimiter=delimiter)
    except ImportError:
        return {"error": "pandas and openpyxl are required to read Excel files. Install via qpip, or in the OSGeo4W Shell: python -m pip install pandas openpyxl"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Could not read '{file_path}': {e}"}
    if not rows:
        return {"error": f"'{file_path}' has no data rows."}

    used, missing, ambiguous, problems = detect_columns(columns, kind, mapping)
    base = {"kind": kind, "columns_in_file": columns, "mapping_used": used}
    if problems or missing or ambiguous:
        base["unmapped_required_roles"] = missing
        base["ambiguous_roles"] = ambiguous
        base["mapping_problems"] = problems
    if problems or missing:
        base["error"] = ("Required column(s) could not be identified, so nothing was imported. Pass `mapping` naming the file's "
                         f"column for each of: {missing or 'see mapping_problems'}.")
        return base
    if kind != "unosat" and "area_code" not in used and "area_name" not in used:
        base["error"] = "No area code or name column was identified, so rows cannot be joined to areas. Pass `mapping` for area_code or area_name."
        return base

    records, issues = normalise_rows(rows, kind, used)
    dup = duplicate_keys(records) if kind != "unosat" else set()
    result = dict(base)
    result.update({
        "success": True, "total_rows": len(records), "summary": summarise(records, kind),
        "issues": issues[:_RESPONSE_CAP], "issue_count": len(issues),
        "duplicate_area_keys": sorted(dup)[:_RESPONSE_CAP],
        "source_note": "Values are exactly as in the file (after validation); cite the file and its date as the source.",
        "records": records[:_RESPONSE_CAP], "records_truncated": len(records) > _RESPONSE_CAP,
    })
    if kind == "unosat":
        result["next_step"] = (f"Load the points with load_tabular_data_as_layer(x_field='{used['longitude']}', y_field='{used['latitude']}') "
                               "if the file's coordinates are WGS84 (check the file's documentation). Then draw them by damage class: "
                               "apply_humanitarian_look(look='damage_class', field=<the damage column of the loaded layer>) (the file's own "
                               "wording such as 'Severe Damage' is matched).")
        if layer_name or write_fields:
            result["join_note"] = "Joining is for ipc and inform only; unosat points have no area key."
        return result
    if ambiguous:
        result["warning"] = f"Role(s) {sorted(ambiguous)} matched several columns and were left unmapped; pass `mapping` to use one."

    if not layer_name:
        return result
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not hasattr(layer, "getFeatures"):
        return {"error": f"'{layer_name}' must be a vector layer."}
    if not layer_key_field or layer.fields().indexOf(layer_key_field) < 0:
        return {"error": f"layer_key_field '{layer_key_field}' not found on '{layer_name}'. Available: {[f.name() for f in layer.fields()]}"}
    use_code = "area_code" in used
    layer_keys = []
    for feat in layer.getFeatures():
        v = feat[layer_key_field]
        layer_keys.append((feat.id(), key_of(v, None) if use_code else key_of(None, v)))
    pairs, report = plan_join(records, layer_keys)
    result["join"] = report
    result["join_key"] = "area_code (P-code)" if use_code else "area_name"
    if not pairs:
        result["join_warning"] = "No row matched the layer; check layer_key_field and the file's key column (P-code vs name)."
    if not write_fields:
        return result
    if not pairs:
        return result

    fields = {role: name for role, name in JOIN_FIELDS[kind].items() if role in used}
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED", "requires_confirmation": True, "is_destructive": True,
            "tool_name": "import_humanitarian_table",
            "arguments": {"file_path": file_path, "kind": kind, "mapping": mapping, "sheet_name": sheet_name, "delimiter": delimiter,
                          "layer_name": layer_name, "layer_key_field": layer_key_field, "write_fields": True, "confirmed": True},
            "code_snippet": f"# Add/update fields {sorted(fields.values())} on '{layer_name}' for {report['matched']} matched areas",
            "rationale": f"Data Mutation Preview: write {kind} values to {sorted(fields.values())} of layer '{layer_name}' "
                         f"({report['matched']} of {report['layer_features']} areas match; unmatched areas keep empty values).",
            "message": f"Confirmation required before adding fields to '{layer_name}'.",
            "join": report,
        }
    try:
        with edit_command(layer, "Cartogen AI: import " + kind) as owned:
            idx = {role: add_numeric_field(layer, name) for role, name in fields.items()}
            for fid, rec in pairs:
                for role, i in idx.items():
                    if rec.get(role) is not None:
                        set_value(layer, fid, i, float(rec[role]))
        result["fields_written"] = sorted(fields.values())
        from .humanitarian_style import table_look_hints
        result["map_looks"] = table_look_hints(layer_name, result["fields_written"])
        if not owned:
            result["note"] = "The layer is already in edit mode, so the new values are in your edit session and are NOT saved."
    except EditError as e:
        result["write_warning"] = f"Values were not written to the layer: {e}"
    except Exception as e:
        result["write_warning"] = f"Values were not written to the layer: {e}"
    return result
