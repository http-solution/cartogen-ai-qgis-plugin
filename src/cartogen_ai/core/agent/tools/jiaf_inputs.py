# -*- coding: utf-8 -*-
"""JIAF 2 analysis support, stage 2: reading and validating sector inputs, and recording the analysis set-up
(docs/JIAF2_ANALYSIS_SUPPORT_PLAN_2026-10-04.md).

SUPPORT FOR PEOPLE WHO RUN THE JIAF 2 PROCESS. NOT the JIAF method, NOT endorsed by OCHA or the IASC, never "JIAF-compliant". This stage
only reads and checks what sectors submitted; it computes no joint PiN, flag or severity (stage 3) and decides nothing.

Three input shapes are read, all as plain grids so the parsing is testable without any spreadsheet library:
- the OCHA Workspace 3A/3B worksheet ("WS - 3.1 Overall PiN" + "WS - 3.2 Intersectoral Severity"), checked against a real filled Yemen 2026 copy;
- HXL-tagged published tables (`#adm2 +code`, `#inneed +wsh`, `#severity +shl`), checked against the published Yemen HNO 2025 / 2026 files;
- the manual's Annex 4 per-sector template (names, P-codes, Population, "Cluster's PiN (Number)" or "Cluster's Severity (Number)"), read from the
  manual's screenshots only -- NOT checked against a real template file.

Nothing is repaired or imputed. A severity of 0 (used in the real Yemen worksheet for "not applicable", e.g. CCCM where there are no camps) is not a
phase 1-5 value; it is reported and kept out of the overlap counts later, never turned into a phase. A dash placeholder is a missing value.
Stored columns the files carry (Preliminary PiN, Final PiN, Final Severity ...) are returned as stored and flagged: the engine recomputes the
preliminary figures and does not trust them (two Yemen units store a Preliminary PiN of 0 although their sectors have figures: that is OCHA's own
'severity above 2' gate in the worksheet's Preliminary PiN column, see jiaf_rules).

The OCHA worksheet is read TABLE-AWARE when the workbook has its Excel tables (`tblPiNAnalysis`, `tblSeverityAnalysis`, `tblPiNHistorical`) and the
`Thresholds` named cells: columns are found by the table's header text, never by position, and a unit's identity is the worksheet's own (population group +
pocket of need + Admin 3 / Admin 2 / Admin 1 P-code), so a pocket of need in the same Admin 2 is a separate unit. Without the tables (a CSV, a copy that lost
them) the header-row search is used instead.
"""
import json
import os
import re

from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value
from .table_importers import key_of, plan_join

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

STATEMENT = ("Support for the JIAF 2 process. This is not the JIAF method, is not endorsed by OCHA or the IASC, and does not decide any figure. "
             "Results are not for ranking crises.")
_CAP = 50
# Shown in every JIAF result: these are open, and neither is closed by anything the owner has supplied so far.
VALIDATION_BLOCKERS = {
    "claim": ("Do not describe this as a faithful or complete JIAF implementation until the owner has closed the items below. A preview with these limits visible is fine; "
              "neither item is marked complete by this tool."),
    "blockers": [
        {"id": "flag_formulas", "status": "compared_awaiting_owner_closure",
         "text": ("The PiN and severity flags are now OCHA's worksheet formulas (rules profile ocha_worksheet_2026, read from the cells of OCHA's official Worksheet 3A/3B "
                  "example and template workbooks), and they reproduce every cached flag, preliminary severity and preliminary PiN of the example workbook's 6 units and "
                  "the stored preliminary PiN and severity of Yemen's 333 units. NOT yet verified: (1) flag 6 on real output (the example's historical table is empty); "
                  "(2) flag 3 when the 3rd highest PiN is exactly 0 (reproduced from the formula text and Excel's text-versus-number rule, no cached example row); "
                  "(3) severity flag 4, where the worksheet's formula and its header disagree (the formula is implemented); (4) the flag decisions Yemen's analysis team "
                  "actually took: its workbook holds values only, so how many units were really flagged or pending needs the team's records, and a pending count here "
                  "does not by itself show that review was required; (5) the threshold values of a real country workbook (the template defaults are used when it has no "
                  "Thresholds sheet)."),
         "closes_when": ("The owner confirms the comparison with OCHA's worksheet formulas and: a Flags dashboard export or the analysis team's records for a real country show the "
                         "same flags, including missing, zero and partially populated inputs; flag 6 is checked on a populated historical table; the flag-3 zero case is "
                         "confirmed on real worksheet output. Bulk closure of flags needs an analysis-team decision recorded with its rationale.")},
        {"id": "annex4_reader", "status": "open",
         "text": ("The Annex 4 sector-input reader is an UNSUPPORTED OPTIONAL format: it was implemented from the manual's screenshots and its compatibility with real files is "
                  "unverified. It is never detected automatically; it is read only when input_format='sector_template' is given. The Yemen worksheet and OCHA's Worksheet "
                  "3A/3B have a different layout and cannot validate Annex 4 support."),
         "closes_when": ("A real filled Annex 4 sector-input file is read, and sheet detection, headers, geographic codes, sector values, missing cells and imported "
                         "totals are checked against the source.")},
    ],
}
# One adapter per supported layout, with what each has actually been checked against. Only the Yemen layouts are validated; Annex 4 is NOT.
ADAPTERS = {
    "ocha_worksheet": {"status": "validated on OCHA's official example workbook (6 units, flags and severity compared with its cached values) and on the supplied Yemen 2026 worksheet",
                       "evidence": ("example: every cached PiN flag, severity flag, preliminary severity and preliminary PiN reproduced (tests/test_jiaf_worksheet_adapter.py, "
                                    "local-only: the workbook is not committed); Yemen: 333 admin-2 units read, preliminary severity matches the stored column in 333/333")},
    "hxl": {"status": "validated on the supplied published Yemen HNO 2025 and 2026 datasets",
            "evidence": "333 admin-2 units read in both; the 2026 total PiN reconciles with the worksheet's final PiN (22,325,197.74)"},
    "sector_template": {"status": "UNSUPPORTED optional format -- implemented from the manual's Annex 4 screenshots; compatibility unverified",
                        "evidence": ("no real filled Annex 4 file has been read; the Yemen worksheet and OCHA's Worksheet 3A/3B have different layouts and cannot validate it. "
                                     "It is never chosen automatically: it is read only when input_format='sector_template' is given."),
                        "optional": True},
}
SETUP_SCOPE = "cartogen_ai_jiaf"
SETUP_KEY = "setup"

# canonical sector -> (short code used in field names, is_aor). The 8 main sectors feed the joint results; AoRs are kept for display only.
SECTORS = {
    "cccm": ("cccm", False), "education": ("edu", False), "nutrition": ("nut", False), "food_security": ("fsac", False),
    "health": ("hea", False), "protection": ("pro", False), "shelter": ("shl", False), "wash": ("wsh", False),
    "child_protection": ("cp", True), "gbv": ("gbv", True), "mine_action": ("ma", True), "hlp": ("hlp", True),
}
MAIN_SECTORS = [s for s, (_c, aor) in SECTORS.items() if not aor]
SECTOR_LABELS = {  # worksheet header (normalised) -> sector
    "cccm": "cccm", "education": "education", "nutrition": "nutrition", "food security": "food_security", "fsac": "food_security",
    "health": "health", "overarching protection": "protection", "protection": "protection", "shelter": "shelter", "shelter/nfi": "shelter",
    "wash": "wash", "cp": "child_protection", "child protection": "child_protection", "child protection (cp)": "child_protection",
    "gbv": "gbv", "gender-based violence (gbv)": "gbv", "mine action": "mine_action", "hlp": "hlp",
}
HXL_SECTORS = {"wsh": "wash", "wash": "wash", "shl": "shelter", "shelter": "shelter", "nut": "nutrition", "nutrition": "nutrition",
               "edu": "education", "education": "education", "fsac": "food_security", "cccm": "cccm", "hea": "health", "hlt": "health",
               "health": "health", "pro": "protection", "prt": "protection", "protection": "protection", "gbv": "gbv", "ma": "mine_action",
               "cp": "child_protection", "hlp": "hlp"}
_DEMOGRAPHIC = {"boys", "men", "girls", "women", "idps", "residents"}
_STORED_PIN = ("preliminary pin", "final pin")
_STORED_SEV = ("preliminary intersectoral severity", "final severity")
_OUTCOMES = {"mortality": "mortality", "malnutrition": "malnutrition", "epidemics": "epidemics", "livelihood coping": "livelihood_coping",
             "hr/ihl violation": "hr_ihl_violation"}


# ----------------------------------------------------------------- values --
def _norm(text):
    return re.sub(r"\s+", " ", str(text if text is not None else "").replace("\n", " ")).strip().lower()


def _blank(v):
    return v is None or (isinstance(v, str) and (not v.strip() or re.fullmatch(r"\s*-*\s*", v) is not None)) or (isinstance(v, float) and v != v)


def to_num(v):
    """Float from a number or a number-like string (thousands separators allowed); None for blank, dash placeholders, text and bool."""
    if _blank(v) or isinstance(v, bool):
        return None
    if isinstance(v, str):
        v = v.strip().replace(",", "")
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def _text(v):
    return None if _blank(v) else str(v).strip()


# ----------------------------------------------------------------- grids --
def read_grid(path, sheet=None):
    """Rows (lists of cell values) of a CSV or one sheet of an Excel file. Returns (grid, sheet_names)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        import csv
        with open(path, "r", encoding="utf-8-sig", errors="ignore", newline="") as fh:
            return [list(r) for r in csv.reader(fh)], []
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        names = list(wb.sheetnames)
        ws = wb[sheet] if sheet else wb[names[0]]
        return [list(r) for r in ws.iter_rows(values_only=True)], names
    raise ValueError(f"Unsupported file type '{ext}' -- use .xlsx or .csv.")


def read_sheets(path):
    """{sheet name: grid} for every sheet of an Excel file."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def _find_header_row(grid, must):
    for i, row in enumerate(grid[:15]):
        cells = {_norm(c) for c in row if c is not None}
        if all(m in cells for m in must):
            return i
    return None


def _empty_unit(code, name, a1c, a1n, group, a3c=None, a3n=None, pocket=None):
    return {"admin1_code": a1c, "admin1": a1n, "admin2_code": code, "admin2": name, "admin3_code": a3c, "admin3": a3n, "pocket_of_need": pocket,
            "population_group": group, "population": None, "pin": {}, "severity": {}, "stored": {}, "outcomes": {}, "previous_pin": None}


def worksheet_id(group, pocket, a3c, a2c, a1c):
    """The worksheet's own unit ID: population group + pocket of need + the finest P-code present (Admin 3, else Admin 2, else Admin 1)."""
    return (group or "") + (pocket or "") + (a3c or a2c or a1c or "")


def uid(u):
    return worksheet_id(u.get("population_group"), u.get("pocket_of_need"), u.get("admin3_code"), u.get("admin2_code"), u.get("admin1_code"))


def _unit_key(u):
    return (u.get("pocket_of_need"), u.get("admin3_code") or u["admin2_code"] or u["admin2"], u["population_group"])


# ------------------------------------------------------ OCHA 3A/3B worksheet --
# Worksheet flag columns, found by their header TEXT (never by position): normalised header prefix -> flag number.
_PIN_FLAG_HEADERS = (("number of missing / zero pins", 1), ("highest pin greater than", 5), ("highest sector targets sub-population", 4),
                     ("% difference is over a specified threshold between highest and 2nd", 2),
                     ("% difference is over a specified threshold between highest and 3rd", 3),
                     ("change from last year for the highest sector(s) has significantly", "6a"),
                     ("change from last year for the 2nd highest sector(s) has significantly", "6b"))
_SEV_FLAG_HEADERS = (("1 sectors in severity phase 5", 1), ("2+ phase variation", 2), ("1+ phase variation", 3), ("more than 4 sectors in 4 or worse", 4))
_MANUAL_FLAG_HEADERS = ("manual flag",)


def _flag_cell(v):
    return isinstance(v, str) and v.strip().lower() == "flagged"


def _identity(idx, row):
    """(admin1_code, admin1, admin2_code, admin2, admin3_code, admin3, pocket, group) of a worksheet row; each None when blank."""
    g = lambda h: _text(row[idx[h]]) if h in idx else None  # noqa: E731
    return (g("admin 1 p-code"), g("admin 1"), g("admin 2 p-code"), g("admin 2"), g("admin 3 p-code"), g("admin 3"), g("pocket of need"), g("population group"))


def parse_ocha_worksheet(pin_grid, sev_grid):
    """Units from the OCHA worksheet's two tables/sheets. Returns (units, notes). Sector columns are matched by header text; the worksheet's own flag
    columns and stored figures are kept under `stored` (never trusted, only compared); outcome-indicator columns under `outcomes`. The unit identity includes
    the population group, the pocket of need and Admin 3 (see worksheet_id)."""
    notes = []
    units = {}

    def load(grid, kind):
        hdr = _find_header_row(grid, ("admin 2 p-code",))
        if hdr is None:
            notes.append(f"No 'Admin 2 P-Code' header row found on the {kind} sheet.")
            return
        header = [_norm(c) for c in grid[hdr]]
        idx = {h: i for i, h in enumerate(header) if h}
        need = ("admin 1", "admin 1 p-code", "admin 2", "admin 2 p-code")
        if not all(n in idx for n in need):
            notes.append(f"The {kind} sheet lacks one of the location columns {list(need)}.")
            return
        sector_cols = {SECTOR_LABELS[h]: i for h, i in idx.items() if h in SECTOR_LABELS}
        flag_cols = {}
        for i, h in enumerate(header):
            for prefix, n in (_PIN_FLAG_HEADERS if kind == "pin" else _SEV_FLAG_HEADERS):
                if h.startswith(prefix):
                    flag_cols[n] = i
        for row in grid[hdr + 1:]:
            row = list(row) + [None] * (len(header) - len(row))
            a1c, a1n, code, name, a3c, a3n, pocket, group = _identity(idx, row)
            if code is None:
                continue
            key = (pocket, a3c or code, group)
            u = units.setdefault(key, _empty_unit(code, name, a1c, a1n, group, a3c, a3n, pocket))
            if "population" in idx and u["population"] is None:
                u["population"] = row[idx["population"]]
            for sector, i in sector_cols.items():
                (u["pin"] if kind == "pin" else u["severity"])[sector] = row[i]
            if flag_cols:
                u["stored"][kind + "_flags"] = {n: _flag_cell(row[i]) for n, i in flag_cols.items()}
            if "# flags" in idx:
                u["stored"][kind + "_flag_count"] = row[idx["# flags"]]
            if kind == "pin":
                for label in _STORED_PIN:
                    if label in idx:
                        u["stored"][label.replace(" ", "_")] = row[idx[label]]
                if "severity" in idx:
                    u["stored"]["severity_used"] = row[idx["severity"]]
                if "evidence & comments" in idx:
                    u["stored"]["evidence"] = _text(row[idx["evidence & comments"]])
            else:
                for h, i in idx.items():
                    if h.startswith("preliminary intersectoral severity"):
                        u["stored"]["preliminary_severity"] = row[i]
                    elif h == "final severity":
                        u["stored"]["final_severity"] = row[i]
                    elif h in _OUTCOMES:
                        u["outcomes"][_OUTCOMES[h]] = row[i]

    load(pin_grid, "pin")
    load(sev_grid, "severity")
    return list(units.values()), notes


def parse_ocha_history(units, hist_grid):
    """Attach last year's PiN (the 'X - old' columns of the worksheet's historical table) to each unit as `previous_pin`, matched on the worksheet unit ID
    computed from the row's own location columns. A unit with no row keeps previous_pin None (the worksheet then leaves flag 6 blank). Returns notes."""
    hdr = _find_header_row(hist_grid, ("admin 2 p-code",))
    if hdr is None:
        return ["No 'Admin 2 P-Code' header row in the historical table."]
    header = [_norm(c) for c in hist_grid[hdr]]
    idx = {h: i for i, h in enumerate(header) if h}
    old_cols = {SECTOR_LABELS[h[:-6]]: i for h, i in idx.items() if h.endswith(" - old") and h[:-6] in SECTOR_LABELS}
    by_id = {uid(u): u for u in units}
    matched = rows = 0
    for row in hist_grid[hdr + 1:]:
        row = list(row) + [None] * (len(header) - len(row))
        a1c, _a1n, code, _name, a3c, _a3n, pocket, group = _identity(idx, row)
        if code is None:
            continue
        rows += 1
        u = by_id.get(worksheet_id(group, pocket, a3c, code, a1c))
        if u is not None:
            u["previous_pin"] = {sec: row[i] for sec, i in old_cols.items()}
            matched += 1
    return [f"Historical table: {rows} rows, {matched} matched to a unit by the worksheet ID, {len(units) - matched} units without a previous-year row."]


def read_workbook_tables(path):
    """Excel tables and named-cell values of a workbook: {"tables": {name: {"sheet", "ref", "grid"}}, "names": {defined name: value}}. Needs a full (not
    read-only) load because the tables are not visible otherwise. Named cells whose target is broken (#REF!) are left out."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    tables = {}
    for ws in wb.worksheets:
        for t in ws.tables.values():
            tables[t.name] = {"sheet": ws.title, "ref": t.ref, "grid": [[c.value for c in r] for r in ws[t.ref]]}
    names = {}
    for name, d in wb.defined_names.items():
        try:
            for sheet, coord in d.destinations:
                names[name] = wb[sheet][coord.replace("$", "")].value
        except Exception:
            continue
    return {"tables": tables, "names": names}


def worksheet_thresholds(wb_tables):
    """({setting: value}, notes) from the worksheet's named threshold cells and its sub-population sector list. Absent names are simply not returned (the
    caller falls back to the template defaults and says so)."""
    from .jiaf_rules import THRESHOLD_NAMES
    names, notes, out = wb_tables["names"], [], {}
    for ws_name, setting in THRESHOLD_NAMES.items():
        v = to_num(names.get(ws_name))
        if v is not None:
            out[setting] = int(v) if setting in ("f1_min_sectors", "sectors_sev_5", "sectors_sev_4") else v
    sub = wb_tables["tables"].get("tblSubSectorPopulation")
    if sub is not None and sub["grid"]:
        head = [_norm(c) for c in sub["grid"][0]]
        if "sector" in head:
            labels = [_text(r[head.index("sector")]) for r in sub["grid"][1:] if len(r) > head.index("sector")]
            sectors = [SECTOR_LABELS.get(_norm(x)) for x in labels if x]
            unknown = [x for x, sec in zip([x for x in labels if x], sectors) if sec is None]
            if unknown:
                notes.append(f"Sub-population sectors not recognised as JIAF sectors and ignored: {unknown}.")
            out["f4_subpopulation_sectors"] = tuple(dict.fromkeys(sec for sec in sectors if sec))
    if not out:
        notes.append("No Thresholds sheet/named cells in this workbook: the template defaults are used. Confirm the country thresholds.")
    return out, notes


# ----------------------------------------------------------------- HXL --
def _parse_tag(tag):
    parts = str(tag).strip().split()
    return (parts[0].lower(), {p.lstrip("+").lower() for p in parts[1:] if p.startswith("+")}) if parts and parts[0].startswith("#") else (None, set())


def find_hxl_row(grid):
    for i, row in enumerate(grid[:10]):
        if sum(1 for c in row if isinstance(c, str) and c.strip().startswith("#")) >= 3:
            return i
    return None


def parse_hxl_table(grid):
    """Units from an HXL-tagged published table (tag row found automatically). Returns (units, notes). `#inneed` / `#severity` without a sector
    attribute are the stored totals; demographic splits (boys/men/girls/women) are ignored; sectors outside the JIAF list are reported."""
    notes = []
    tr = find_hxl_row(grid)
    if tr is None:
        return [], ["No HXL tag row (cells starting with '#') in the first 10 rows."]
    tags = [_parse_tag(c) if isinstance(c, str) else (None, set()) for c in grid[tr]]
    col = {}
    pin_cols, sev_cols, other = {}, {}, set()
    for i, (base, attrs) in enumerate(tags):
        if base == "#adm2" and "code" in attrs:
            col["admin2_code"] = i
        elif base == "#adm2" and "name" in attrs:
            col["admin2"] = i
        elif base == "#adm1" and "code" in attrs:
            col["admin1_code"] = i
        elif base == "#adm1" and "name" in attrs:
            col["admin1"] = i
        elif base in ("#inneed", "#severity"):
            target = pin_cols if base == "#inneed" else sev_cols
            if attrs & _DEMOGRAPHIC:
                continue
            if not attrs:
                col["total_pin" if base == "#inneed" else "severity_total"] = i
                continue
            sec = next((HXL_SECTORS[a] for a in attrs if a in HXL_SECTORS), None)
            if sec is None:
                other.update(attrs)
            else:
                target[sec] = i
        elif base == "#population" and (not attrs or attrs == {"total"}):
            col.setdefault("population", i)
    if "admin2_code" not in col:
        return [], ["The HXL table has no '#adm2 +code' column."]
    pop_parts = [i for i, (b, a) in enumerate(tags) if b == "#population" and (a & {"idps", "residents"})]
    if other:
        notes.append(f"Ignored tag attributes that are not JIAF sectors: {sorted(other)}.")
    units = []
    for row in grid[tr + 1:]:
        row = list(row) + [None] * (len(tags) - len(row))
        code = _text(row[col["admin2_code"]])
        if code is None or code.startswith("#"):
            continue
        u = _empty_unit(code, _text(row[col["admin2"]]) if "admin2" in col else None,
                        _text(row[col["admin1_code"]]) if "admin1_code" in col else None,
                        _text(row[col["admin1"]]) if "admin1" in col else None, None)
        if "population" in col:
            u["population"] = row[col["population"]]
        elif pop_parts:
            vals = [to_num(row[i]) for i in pop_parts]
            u["population"] = sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None
        for sec, i in pin_cols.items():
            u["pin"][sec] = row[i]
        for sec, i in sev_cols.items():
            u["severity"][sec] = row[i]
        if "total_pin" in col:
            u["stored"]["total_pin"] = row[col["total_pin"]]
        if "severity_total" in col:
            u["stored"]["final_severity"] = row[col["severity_total"]]
        units.append(u)
    return units, notes


# ------------------------------------------------------- Annex 4 template --
def parse_sector_template(grid, sector, kind):
    """Units from the manual's per-sector template (read from the manual's screenshots, not from a real file). `kind` is 'pin' or 'severity'."""
    if sector not in SECTORS:
        return [], [f"Unknown sector '{sector}'. Sectors: {sorted(SECTORS)}."]
    if kind not in ("pin", "severity"):
        return [], ["template_kind must be 'pin' or 'severity'."]
    hdr = _find_header_row(grid, ("admin 2 p-code",))
    if hdr is None:
        return [], ["No 'Admin 2 P-Code' header row in the first rows."]
    header = [_norm(c) for c in grid[hdr]]
    idx = {h: i for i, h in enumerate(header) if h}
    value_col = next((i for h, i in idx.items() if h.startswith("cluster") and ("pin" in h if kind == "pin" else "sev" in h)), None)
    if value_col is None:
        return [], [f"No \"Cluster's {'PiN' if kind == 'pin' else 'Severity'} (Number)\" column."]
    units = []
    for row in grid[hdr + 1:]:
        row = list(row) + [None] * (len(header) - len(row))
        code = _text(row[idx["admin 2 p-code"]])
        if code is None:
            continue
        u = _empty_unit(code, _text(row[idx["admin 2"]]) if "admin 2" in idx else None,
                        _text(row[idx["admin 1 p-code"]]) if "admin 1 p-code" in idx else None,
                        _text(row[idx["admin 1"]]) if "admin 1" in idx else None, None)
        if "population" in idx:
            u["population"] = row[idx["population"]]
        (u["pin"] if kind == "pin" else u["severity"])[sector] = row[value_col]
        units.append(u)
    return units, []


def merge_units(batches):
    """Merge unit lists from several single-sector files (same unit key) into one list."""
    merged = {}
    for units in batches:
        for u in units:
            m = merged.setdefault(_unit_key(u), u)
            if m is not u:
                m["pin"].update(u["pin"])
                m["severity"].update(u["severity"])
                if m["population"] is None:
                    m["population"] = u["population"]
    return list(merged.values())


# ------------------------------------------------------------ validation --
def validate_units(units):
    """Normalise values in place (numbers as floats, severities as ints or None) and return (issues, summary). Nothing is repaired or filled."""
    issues, seen = [], {}

    def add(unit, sector, field, problem, severity="error"):
        issues.append({"unit": unit["admin2_code"], "population_group": unit["population_group"], "sector": sector, "field": field,
                       "problem": problem, "level": severity})

    zero_sev = 0
    for u in units:
        key = _unit_key(u)
        if key in seen:
            add(u, None, "unit", "duplicate unit (same Admin 3/Admin 2 P-Code, population group and pocket of need): both rows are kept, the join will not match them")
        seen[key] = True
        if not u["admin2_code"]:
            add(u, None, "admin2_code", "missing Admin 2 P-Code")
        raw_pop = u["population"]
        u["population"] = to_num(raw_pop)
        if u["population"] is None and not _blank(raw_pop):
            add(u, None, "population", "not a number")
        elif u["population"] is not None and u["population"] < 0:
            add(u, None, "population", "negative")
            u["population"] = None
        if u.get("previous_pin") is not None:
            u["previous_pin"] = {sec: to_num(v) for sec, v in u["previous_pin"].items()}
        for sector in list(u["pin"]):
            raw = u["pin"][sector]
            v = to_num(raw)
            if v is None and not _blank(raw):
                add(u, sector, "pin", f"not a number ({raw!r})")
            elif v is not None and v < 0:
                add(u, sector, "pin", "negative")
                v = None
            elif v is not None and u["population"] is not None and not SECTORS[sector][1] and v > u["population"] * (1 + 1e-9):
                add(u, sector, "pin", "larger than the unit's population (a sector that counts a subset of the population may be right; check the base)", "warning")
            u["pin"][sector] = v
        for sector in list(u["severity"]):
            raw = u["severity"][sector]
            v = to_num(raw)
            if v is None and not _blank(raw):
                add(u, sector, "severity", f"not a number ({raw!r})")
                u["severity"][sector] = None
            elif v is None:
                u["severity"][sector] = None
            elif v == 0:
                zero_sev += 1
                u["severity"][sector] = 0
            elif v != int(v) or not 1 <= v <= 5:
                add(u, sector, "severity", f"not a phase from 1 to 5 ({raw!r}); left empty")
                u["severity"][sector] = None
            else:
                u["severity"][sector] = int(v)
    sectors = sorted({s for u in units for s in list(u["pin"]) + list(u["severity"])})
    per_sector = {}
    for s in sectors:
        pins = [u["pin"].get(s) for u in units if s in u["pin"]]
        sevs = [u["severity"].get(s) for u in units if s in u["severity"]]
        per_sector[s] = {
            "pin_units_with_value": sum(1 for v in pins if v is not None), "pin_units_missing": sum(1 for v in pins if v is None),
            "pin_sum_over_units": round(sum(v for v in pins if v is not None), 4) if pins else None,
            "severity_units_with_phase": sum(1 for v in sevs if v is not None and v > 0),
            "severity_units_zero_or_missing": sum(1 for v in sevs if v is None or v == 0),
            "is_aor": SECTORS[s][1],
        }
    return issues, {"sectors": per_sector, "severity_zero_values": zero_sev, "units": len(units)}


# --------------------------------------------------------------- detection --
def detect_format(sheets):
    """'ocha_worksheet', 'hxl' or 'sector_template' from {sheet name: grid}; None if unrecognised."""
    names = {n: _norm(n) for n in sheets}
    pin = next((n for n, k in names.items() if "3.1" in k and "pin" in k), None)
    sev = next((n for n, k in names.items() if "3.2" in k and "sever" in k), None)
    if pin and sev:
        return "ocha_worksheet"
    first = next(iter(sheets.values()), [])
    if find_hxl_row(first) is not None:
        return "hxl"
    # The Annex 4 sector template is never chosen automatically: it is an unsupported optional format (compatibility unverified), read only when asked for.
    return None


# --------------------------------------------------------------- the tool --
def _layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def load_units(file_path, input_format="auto", sheet_name=None, sector=None, template_kind=None, extras=None):
    """Read `file_path` into (units, fmt, notes) or return {"error": ...}. Shared by the import tool and the calculation tool. If `extras` is a dict it is filled
    with what the OCHA worksheet carries beyond the units: "thresholds" ({setting: value} from its named cells and sub-population list) and "tables"."""
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    fmt = str(input_format or "auto").lower()
    if fmt not in ("auto", "ocha_worksheet", "hxl", "sector_template"):
        return {"error": "input_format must be 'auto', 'ocha_worksheet', 'hxl' or 'sector_template'."}
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".csv":
            sheets = {"csv": read_grid(file_path)[0]}
        elif ext in (".xlsx", ".xlsm"):
            sheets = read_sheets(file_path)
        else:
            return {"error": f"Unsupported file type '{ext}' -- use .xlsx or .csv."}
    except ImportError:
        return {"error": "openpyxl is required to read Excel files. Install via qpip, or in the OSGeo4W Shell: python -m pip install openpyxl"}
    except Exception as e:
        return {"error": f"Could not read '{file_path}': {e}"}
    if fmt == "auto":
        fmt = detect_format(sheets)
        if fmt is None:
            return {"error": ("Could not recognise the file (no OCHA 3.1/3.2 sheets, no HXL tag row). The Annex 4 sector template is an unsupported optional format "
                              "and is never detected automatically: pass input_format='sector_template' (with sector and template_kind) to read it anyway."),
                    "sheets": list(sheets)}
    notes = []
    if fmt == "ocha_worksheet":
        names = {n: _norm(n) for n in sheets}
        pin = next((n for n, k in names.items() if "3.1" in k and "pin" in k), None)
        sev = next((n for n, k in names.items() if "3.2" in k and "sever" in k), None)
        if not (pin and sev):
            return {"error": "The OCHA worksheet needs sheets named like 'WS - 3.1 Overall PiN' and 'WS - 3.2 Intersectoral Severity'.", "sheets": list(sheets)}
        pin_grid, sev_grid, hist_grid = sheets[pin], sheets[sev], None
        if ext in (".xlsx", ".xlsm"):
            try:
                wbt = read_workbook_tables(file_path)
            except Exception as e:
                wbt = None
                notes.append(f"Could not read the workbook's Excel tables ({e}); the header-row search was used instead.")
            if wbt is not None:
                tp, ts, th = (wbt["tables"].get(n) for n in ("tblPiNAnalysis", "tblSeverityAnalysis", "tblPiNHistorical"))
                if tp and ts:
                    pin_grid, sev_grid = tp["grid"], ts["grid"]
                    notes.append(f"Read from the Excel tables tblPiNAnalysis ({tp['ref']} on '{tp['sheet']}') and tblSeverityAnalysis ({ts['ref']} on '{ts['sheet']}'); "
                                 "columns are matched by header text.")
                else:
                    notes.append("The workbook has no tblPiNAnalysis/tblSeverityAnalysis tables; the header-row search was used.")
                hist_grid = th["grid"] if th else None
                found, tnotes = worksheet_thresholds(wbt)
                notes.extend(tnotes)
                if extras is not None:
                    extras["thresholds"] = found
        units, pnotes = parse_ocha_worksheet(pin_grid, sev_grid)
        notes.extend(pnotes)
        if hist_grid is not None:
            notes.extend(parse_ocha_history(units, hist_grid))
    else:
        grid = sheets[sheet_name] if sheet_name and sheet_name in sheets else next(iter(sheets.values()))
        if fmt == "hxl":
            units, notes = parse_hxl_table(grid)
        else:
            notes.append("UNSUPPORTED optional format: the Annex 4 sector template was implemented from the manual's screenshots and its compatibility with real files is unverified.")
            if not sector or not template_kind:
                return {"error": "sector_template needs `sector` and `template_kind` ('pin' or 'severity')."}
            units, tnotes = parse_sector_template(grid, str(sector).lower(), str(template_kind).lower())
            notes.extend(tnotes)
    if not units:
        return {"error": "No units could be read. " + " ".join(notes), "format": fmt}

    return units, fmt, notes


@register_tool(
    "import_jiaf_inputs",
    "Read and validate the sector inputs for a JIAF 2 analysis (support for the JIAF 2 process; not the JIAF method, not endorsed by OCHA or the "
    "IASC, no joint PiN or severity is computed here). Reads an .xlsx/.csv of one of three kinds: the OCHA Workspace 3A/3B worksheet ('WS - 3.1 "
    "Overall PiN' + 'WS - 3.2 Intersectoral Severity'), an HXL-tagged published table (#adm2 +code, #inneed +wsh, #severity +shl ...), or the "
    "manual's per-sector template (give `sector` and `template_kind`). Reports units, sectors found, per-sector totals, and every problem: "
    "severity must be a phase 1-5 (0 is reported as not-applicable, never turned into a phase), PiN must be a non-negative number, duplicates and "
    "missing values are listed and never filled. Stored columns (Preliminary/Final PiN, Final Severity) are returned only as stored and are NOT "
    "trusted. Optionally joins to an admin layer by P-code and, after confirmation, writes the values as new numeric fields (jp_<sector> for PiN, "
    "js_<sector> for severity). Never invent a threshold or fill a missing value.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the .xlsx or .csv file."},
            "input_format": {"type": "string", "description": "'auto' (default), 'ocha_worksheet', 'hxl' or 'sector_template'."},
            "sheet_name": {"type": "string", "description": "Sheet to read for 'hxl' or 'sector_template' (default: the first)."},
            "sector": {"type": "string", "description": "For 'sector_template': the sector the file belongs to (cccm, education, nutrition, food_security, health, protection, shelter, wash, child_protection, gbv, mine_action, hlp)."},
            "template_kind": {"type": "string", "description": "For 'sector_template': 'pin' or 'severity'."},
            "layer_name": {"type": "string", "description": "Optional admin polygon layer to join to."},
            "layer_key_field": {"type": "string", "description": "Field on that layer holding the Admin 2 P-code."},
            "write_fields": {"type": "boolean", "description": "With layer_name: write jp_<sector> (PiN) and js_<sector> (severity) fields. Needs confirmation."},
        },
        "required": ["file_path"],
    },
)
def import_jiaf_inputs(file_path, input_format="auto", sheet_name=None, sector=None, template_kind=None, layer_name=None, layer_key_field=None,
                       write_fields=False, confirmed: bool = False):
    loaded = load_units(file_path, input_format, sheet_name, sector, template_kind)
    if isinstance(loaded, dict):
        return loaded
    units, fmt, notes = loaded

    issues, summary = validate_units(units)
    stored = {}
    for u in units:
        for k, v in u["stored"].items():
            if k != "evidence" and not _blank(v):
                stored[k] = stored.get(k, 0) + 1
    result = {
        "success": True, "statement": STATEMENT, "format": fmt, "adapter": dict(ADAPTERS[fmt], name=fmt), "units": len(units), "notes": notes,
        "sectors_found": sorted(summary["sectors"]),
        "main_sectors_missing": [s for s in MAIN_SECTORS if s not in summary["sectors"]],
        "per_sector": summary["sectors"], "severity_zero_values": summary["severity_zero_values"],
        "issue_count": len(issues), "issues_shown": issues[:_CAP],
        "stored_columns_present": stored,
        "stored_columns_note": "Stored Preliminary/Final figures are returned only as stored; the analysis recomputes them and does not trust them.",
        "validation_blockers": VALIDATION_BLOCKERS,
        "population_note": ("Population is missing for every unit." if all(u["population"] is None for u in units) else None),
    }
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
    records = [{"key": key_of(u["admin2_code"], None), "unit": u} for u in units]
    layer_keys = [(f.id(), key_of(f[layer_key_field], None)) for f in layer.getFeatures()]
    pairs, report = plan_join(records, layer_keys)
    result["join"] = report
    if any(u["population_group"] for u in units):
        result["join_note"] = "The file has population groups, so several rows share a P-code; those areas are ambiguous and are not matched. Filter to one group first."
    if not write_fields or not pairs:
        return result
    pin_fields = {s: f"jp_{SECTORS[s][0]}" for s in summary["sectors"] if any(v is not None for u in units for v in [u["pin"].get(s)])}
    sev_fields = {s: f"js_{SECTORS[s][0]}" for s in summary["sectors"] if any(v for u in units for v in [u["severity"].get(s)])}
    names = sorted(list(pin_fields.values()) + list(sev_fields.values()))
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED", "requires_confirmation": True, "is_destructive": True, "tool_name": "import_jiaf_inputs",
            "arguments": {"file_path": file_path, "input_format": fmt, "sheet_name": sheet_name, "sector": sector, "template_kind": template_kind,
                          "layer_name": layer_name, "layer_key_field": layer_key_field, "write_fields": True, "confirmed": True},
            "code_snippet": f"# Add/update fields {names} on '{layer_name}' for {report['matched']} matched areas",
            "rationale": f"Data Mutation Preview: write JIAF sector inputs to {names} of layer '{layer_name}' ({report['matched']} of {report['layer_features']} areas match).",
            "message": f"Confirmation required before adding fields to '{layer_name}'.", "join": report,
        }
    try:
        with edit_command(layer, "Cartogen AI: import JIAF inputs") as owned:
            idx = {("pin", s): add_numeric_field(layer, n) for s, n in pin_fields.items()}
            idx.update({("sev", s): add_numeric_field(layer, n) for s, n in sev_fields.items()})
            for fid, rec in pairs:
                u = rec["unit"]
                for (kind, s), i in idx.items():
                    v = u["pin"].get(s) if kind == "pin" else u["severity"].get(s)
                    if v is not None and not (kind == "sev" and v == 0):
                        set_value(layer, fid, i, float(v))
        result["fields_written"] = names
        if not owned:
            result["note"] = "The layer is already in edit mode, so the new values are in your edit session and are NOT saved."
    except EditError as e:
        result["write_warning"] = f"Values were not written to the layer: {e}"
    except Exception as e:
        result["write_warning"] = f"Values were not written to the layer: {e}"
    return result


# ----------------------------------------------------- set-up and alignment --
def validate_setup(setup, alignments):
    """(clean_setup, clean_alignments, errors). Alignment records need an explanation whenever a sector is not aligned / adapted (manual Step 2.1)."""
    errors = []
    clean = {}
    for key in ("country", "planning_cycle", "unit_of_analysis", "manual_edition"):
        v = _text(setup.get(key))
        if v is None:
            errors.append(f"{key} is required.")
        clean[key] = v
    for key in ("areas_in_scope", "population_groups", "scope_note"):
        clean[key] = setup.get(key) if setup.get(key) not in ("", None) else None
    hct = setup.get("hct_endorsed_scope")
    if hct is not None and not isinstance(hct, bool):
        errors.append("hct_endorsed_scope must be true, false or omitted.")
    clean["hct_endorsed_scope"] = hct
    out = []
    for a in alignments or []:
        s = _norm(a.get("sector")).replace(" ", "_")
        if s not in SECTORS:
            errors.append(f"Unknown sector '{a.get('sector')}'. Sectors: {sorted(SECTORS)}.")
            continue
        pin_ok, sev = a.get("pin_aligned"), _norm(a.get("severity_alignment"))
        if pin_ok is not None and not isinstance(pin_ok, bool):
            errors.append(f"{s}: pin_aligned must be true or false.")
        if sev and sev not in ("aligned", "adapted"):
            errors.append(f"{s}: severity_alignment must be 'aligned' or 'adapted'.")
        if pin_ok is False and not _text(a.get("pin_explanation")):
            errors.append(f"{s}: a PiN that is not aligned needs pin_explanation (manual Step 2.1).")
        if sev == "adapted" and not _text(a.get("severity_explanation")):
            errors.append(f"{s}: an adapted severity scale needs severity_explanation (manual Step 2.1).")
        out.append({"sector": s, "pin_aligned": pin_ok, "pin_explanation": _text(a.get("pin_explanation")),
                    "severity_alignment": sev or None, "severity_explanation": _text(a.get("severity_explanation")),
                    "indicators_and_thresholds": _text(a.get("indicators_and_thresholds"))})
    return clean, out, errors


@register_tool(
    "record_jiaf_setup",
    "Record the JIAF 2 analysis set-up in the project (support for the JIAF 2 process; not endorsed by OCHA or the IASC): country, planning cycle, "
    "unit of analysis (e.g. admin 2), the manual edition followed (e.g. 'July 2024'), areas and population groups in scope, whether the "
    "Humanitarian Country Team endorsed the scope, and optionally each sector's alignment self-assessment (manual Workspaces 2A/2B): whether its PiN "
    "is aligned with the joint-overall-PiN guidance, whether its severity scale is aligned or adapted, with an explanation whenever it is not aligned "
    "or is adapted, and the indicators and thresholds it used. Replaces any earlier record. Stored in the QGIS project; nothing is computed or decided.",
    {
        "type": "object",
        "properties": {
            "country": {"type": "string"}, "planning_cycle": {"type": "string", "description": "e.g. 'HPC 2026'."},
            "unit_of_analysis": {"type": "string", "description": "e.g. 'admin 2' or 'admin 2 x population group'."},
            "manual_edition": {"type": "string", "description": "The JIAF 2 Technical Manual edition followed, e.g. 'July 2024'."},
            "areas_in_scope": {"type": "string"}, "population_groups": {"type": "string"}, "scope_note": {"type": "string"},
            "hct_endorsed_scope": {"type": "boolean", "description": "Whether the HCT endorsed the scope; omit if unknown."},
            "sector_alignment": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "sector": {"type": "string"}, "pin_aligned": {"type": "boolean"}, "pin_explanation": {"type": "string"},
                    "severity_alignment": {"type": "string", "description": "'aligned' or 'adapted'."}, "severity_explanation": {"type": "string"},
                    "indicators_and_thresholds": {"type": "string"}}},
            },
        },
        "required": ["country", "planning_cycle", "unit_of_analysis", "manual_edition"],
    },
)
def record_jiaf_setup(country, planning_cycle, unit_of_analysis, manual_edition, areas_in_scope=None, population_groups=None, scope_note=None,
                      hct_endorsed_scope=None, sector_alignment=None):
    setup = {"country": country, "planning_cycle": planning_cycle, "unit_of_analysis": unit_of_analysis, "manual_edition": manual_edition,
             "areas_in_scope": areas_in_scope, "population_groups": population_groups, "scope_note": scope_note, "hct_endorsed_scope": hct_endorsed_scope}
    clean, alignments, errors = validate_setup(setup, sector_alignment)
    if errors:
        return {"error": "The set-up record was not saved: " + " ".join(errors)}
    record = {"statement": STATEMENT, "setup": clean, "sector_alignment": alignments}
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    try:
        ok = QgsProject.instance().writeEntry(SETUP_SCOPE, SETUP_KEY, json.dumps(record, ensure_ascii=False))
    except Exception as e:
        return {"error": f"Could not store the record in the project: {e}"}
    if not ok:
        return {"error": "The project refused the record (is a project open?)."}
    return {"success": True, "statement": STATEMENT, "recorded": record,
            "note": "Stored in the QGIS project (save the project to keep it). The calculation stages repeat these details on every output."}


@register_tool(
    "get_jiaf_setup",
    "Read the JIAF 2 analysis set-up and sector alignment records stored in the project by record_jiaf_setup (support for the JIAF 2 process; not "
    "endorsed by OCHA or the IASC).",
    {"type": "object", "properties": {}},
)
def get_jiaf_setup():
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    raw, ok = QgsProject.instance().readEntry(SETUP_SCOPE, SETUP_KEY, "")
    if not ok or not raw:
        return {"success": True, "recorded": None, "note": "No JIAF set-up has been recorded in this project."}
    try:
        return {"success": True, "recorded": json.loads(raw)}
    except ValueError:
        return {"error": "The stored JIAF set-up record is not valid JSON."}
