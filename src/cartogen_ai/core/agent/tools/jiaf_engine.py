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

RULES PROFILES (setting `rules_profile`). The default, `ocha_worksheet_2026` (jiaf_rules.py), reproduces the flag formulas read from OCHA's official
Worksheet 3A/3B example and template workbooks: distinct-value ranks, tie suppression, the worksheet's thresholds and its 'severity above 2' gate on the
preliminary PiN. Thresholds come from the workbook's own `Thresholds` named cells when it has them (an explicit tool argument wins), else the template
defaults, and every result says which. The older `manual_reading` profile keeps this module's earlier INTERPRETATION of the manual's wording for comparison
only: it is not OCHA's rule set and is never the default.
manual_reading, for the record:
- Flag 1 fires when the number of sectors with a missing or zero PiN is at least `f1_min_sectors` (default 1; the table says "1 or 2").
- Flags 2 and 3 measure the difference of the highest PiN to the 2nd / 3rd highest RELATIVE TO THE 2nd / 3rd and fire at >= the threshold.
- Flag 4 is only evaluated when the sectors that count a sub-population are named; the manual's 50% is not applied.
- Flag 5 fires when the highest PiN is above `f5_share` of the unit's population.
- Flag 6 compares the highest sector's PiN with the same sector's previous-year PiN (increase >= `f6_pct`, previous PiN >= `f6_min_previous_pin`).
- Severity flag 4 fires when MORE THAN `s4_sector_count` sectors are in phase 4 and the preliminary phase is 4.

INCOMPLETE COVERAGE is never turned into a phase 1. The sectors in scope (`sectors_in_scope`, default all eight main sectors; narrow it only to the
sectors the HCT activated) that have no phase are MISSING: the overlap rule is applied with them contributing nothing and with all of them at phase 5,
and if the two disagree the preliminary severity is empty, with both bounds, and the unit is reported as 'incomplete_coverage'. A severity of 0 is
'not applicable' by default (`zero_severity_as`; the real Yemen worksheet uses 0 for CCCM where there are no camps) or MISSING if the team says so.
A unit with a missing sector PiN keeps its highest-of-the-reporting-sectors figure, marked as a lower bound. The preliminary result, the review status,
the final result and the justification are separate fields throughout (see jiaf_review).
"""
import csv
import os

from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value
from . import jiaf_rules as rules
from .jiaf_inputs import ADAPTERS, MAIN_SECTORS, SECTORS, STATEMENT, VALIDATION_BLOCKERS, load_units, uid, validate_units
from .table_importers import key_of, plan_join

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_CAP = 50
_TOL = 1e-9
MANUAL = "manual_reading"
_COMMON = {"rules_profile": rules.PROFILE_ID, "sectors_in_scope": tuple(MAIN_SECTORS), "zero_severity_as": "not_applicable"}
PROFILE_DEFAULTS = {
    rules.PROFILE_ID: dict(rules.TEMPLATE_DEFAULTS),
    MANUAL: {"f1_min_sectors": 1, "f1_count_missing": True, "f1_count_zero": True, "f2_pct": 0.30, "f3_pct": 0.50, "f4_subpopulation_sectors": (), "f5_share": 0.90,
             "f6_pct": 1.00, "f6_min_previous_pin": 1000.0, "s4_sector_count": 4},
}
DEFAULTS = dict(_COMMON, **PROFILE_DEFAULTS[rules.PROFILE_ID])  # the default profile's settings
ALL_SETTINGS = sorted(set(_COMMON) | set(PROFILE_DEFAULTS[rules.PROFILE_ID]) | set(PROFILE_DEFAULTS[MANUAL]))
READINGS_OCHA = [
    "Flag 3 with a 3rd highest PiN of exactly 0: the worksheet formula tests the difference column for blank, so Excel's text-versus-number comparison flags it. Reproduced from the formula text; no cached example row contains this case, so it is unconfirmed on real output.",
    "Flag 6 (change from last year): reproduced from the formulas; the supplied example's historical table is empty, so it is checked on synthetic cases only. Each of its two parts (highest sector(s), 2nd highest sector(s)) counts separately in the worksheet's '# Flags'.",
    "Severity flag 4: the worksheet FORMULA (preliminary 5 and at least sectors_sev_5 sectors in phases 1-4) disagrees with its HEADER ('more than 4 sectors in 4 or worse while preliminary is 4 or lower'). The formula is implemented; the header's reading is returned beside it as header_text_reading.",
    "Flag 4 uses the sub-population sector list: the template ships with only 'Education'. A workbook's own list is used when it has one; otherwise the team must set it.",
    "Outcome-indicator phases (severity flags 2 and 3) are read as assigned by analysts; the worksheet's 'Reference Table Indicators' sheet that can derive them from raw indicators is not implemented.",
    "Coverage: the worksheet applies its severity rule to the sectors that have a value and silently gives phase 1 when too few report; this tool is stricter by design (incomplete coverage gives no preliminary severity, with bounds). The worksheet's own rule value is returned beside it as worksheet_rule_severity.",
    "Narrowing sectors_in_scope departs from the worksheet, whose ranges always cover all eight main sectors.",
]
READINGS = [
    "Flag 1: fires when the number of sectors with a missing PiN and/or an explicit zero PiN (f1_count_missing, f1_count_zero; both by default) is at least f1_min_sectors (the table says 'missing or zero' and '1 or 2'). UNVERIFIED interpretation.",
    "Flags 2/3: the difference is measured relative to the 2nd/3rd highest PiN and fires at >= the threshold (Annex 5 implies this).",
    "Flag 4: only evaluated when f4_subpopulation_sectors is given; fires when the highest PiN belongs to one of them; the 50% is not applied.",
    "Flag 5: highest PiN above f5_share of the unit's population; above 100% is also marked as a likely data error.",
    "Flag 6: the highest sector's PiN against the same sector's previous-year PiN; increase >= f6_pct; only when the previous PiN >= f6_min_previous_pin.",
    "Severity flag 4: more than s4_sector_count sectors in phase 4 and a preliminary phase 4.",
    "Coverage: sectors_in_scope defaults to all eight main sectors; a sector with no phase is missing, never phase 1; 0 is 'not applicable' unless zero_severity_as='missing'.",
]


def readings_for(settings):
    return READINGS_OCHA if settings["rules_profile"] == rules.PROFILE_ID else ["manual_reading profile (this module's INTERPRETATION of the manual, not OCHA's rules; for comparison only):"] + READINGS


# ------------------------------------------------------------------ pure --
def merge_settings(overrides=None):
    profile = (overrides or {}).get("rules_profile") or rules.PROFILE_ID
    if profile not in PROFILE_DEFAULTS:
        raise ValueError(f"Unknown rules_profile '{profile}'. Profiles: {sorted(PROFILE_DEFAULTS)}.")
    s = dict(_COMMON, **PROFILE_DEFAULTS[profile])
    s["rules_profile"] = profile
    for k, v in (overrides or {}).items():
        if k not in ALL_SETTINGS:
            raise ValueError(f"Unknown setting '{k}'. Settings: {ALL_SETTINGS}.")
        if k not in s:
            if v is not None:
                raise ValueError(f"'{k}' is not a setting of the {profile} profile (settings: {sorted(s)}).")
            continue
        if v is not None:
            s[k] = v
    if int(s["f1_min_sectors"]) < 1:
        raise ValueError("f1_min_sectors must be at least 1.")
    for k in ("f2_pct", "f3_pct", "f5_share", "f6_pct", "f6_min_previous_pin"):
        if k in s:
            s[k] = float(s[k])
            if s[k] < 0:
                raise ValueError(f"{k} must not be negative.")
    for k in ("f1_count_missing", "f1_count_zero"):
        if k in s and not isinstance(s[k], bool):
            raise ValueError(f"{k} must be true or false.")
    if "f1_count_missing" in s and not (s["f1_count_missing"] or s["f1_count_zero"]):
        raise ValueError("flag 1 must count missing sectors, zero sectors or both.")
    s["sectors_in_scope"] = tuple(s["sectors_in_scope"] or ())
    if not s["sectors_in_scope"] or any(x not in MAIN_SECTORS for x in s["sectors_in_scope"]):
        raise ValueError(f"sectors_in_scope must be a non-empty list of main sectors {MAIN_SECTORS}.")
    if s["zero_severity_as"] not in ("not_applicable", "missing"):
        raise ValueError("zero_severity_as must be 'not_applicable' or 'missing'.")
    s["f4_subpopulation_sectors"] = tuple(s["f4_subpopulation_sectors"] or ())
    bad = [x for x in s["f4_subpopulation_sectors"] if x not in MAIN_SECTORS]
    if bad:
        raise ValueError(f"f4_subpopulation_sectors must be main sectors {MAIN_SECTORS}; got {bad}.")
    s["f1_min_sectors"] = int(s["f1_min_sectors"])
    for k in ("s4_sector_count", "sectors_sev_5", "sectors_sev_4"):
        if k in s:
            s[k] = int(s[k])
            if s[k] < 1:
                raise ValueError(f"{k} must be at least 1.")
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


def old_pins_of(unit, previous_unit=None):
    """Last year's {sector: PiN} for a unit: the worksheet's own historical table if the file had one, else the matching unit of a previous-year file, else None."""
    if unit.get("previous_pin") is not None:
        return unit["previous_pin"]
    return previous_unit["pin"] if previous_unit is not None else None


def pin_flags_worksheet(unit, expected, settings, previous_unit=None):
    """(flags, extra) under the ocha_worksheet_2026 profile (see jiaf_rules)."""
    return rules.pin_flags({sec: unit["pin"].get(sec) for sec in expected}, unit.get("population"), settings, old_pins_of(unit, previous_unit))


def pin_flags(unit, ranked, settings, expected, previous_unit=None):
    """{flag number: {"fired": bool or None (not evaluable), "value": ..., "note": ...}} for flags 1-6, under the profile in `settings`."""
    if settings["rules_profile"] == rules.PROFILE_ID:
        return pin_flags_worksheet(unit, expected, settings, previous_unit)[0]
    flags = {}
    # An absent PiN and an explicit zero are different facts and stay different: they are listed apart, and the team chooses whether flag 1 counts
    # either or both (default both: the table says "missing or zero"). This trigger is an UNVERIFIED interpretation (see VALIDATION_BLOCKERS).
    absent = [s for s in expected if unit["pin"].get(s) is None]
    zero = [s for s in expected if unit["pin"].get(s) == 0]
    counted = (len(absent) if settings["f1_count_missing"] else 0) + (len(zero) if settings["f1_count_zero"] else 0)
    flags[1] = {"fired": counted >= settings["f1_min_sectors"], "value": counted, "note": None, "detail": {"missing_sectors": absent, "zero_sectors": zero}}
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


def severity_inputs(unit, expected, zero_as="not_applicable"):
    """(reporting phases, missing sectors, not-applicable sectors) for the sectors in scope. A phase 1-5 is reporting; None (and an invalid value) is
    MISSING -- unknown, never read as phase 1; 0 is NOT APPLICABLE by default (the real Yemen worksheet uses 0 for CCCM where there are no camps) or
    MISSING when zero_as='missing'."""
    reporting, missing, na = [], [], []
    for sector in expected:
        v = unit["severity"].get(sector)
        if v in (1, 2, 3, 4, 5):
            reporting.append(v)
        elif v == 0 and zero_as == "not_applicable":
            na.append(sector)
        else:
            missing.append(sector)
    return reporting, missing, na


def severity_with_coverage(reporting, n_missing):
    """Preliminary severity that does not hide incomplete coverage. The missing sectors are unknown, so the rule is applied twice: once with them
    contributing nothing (lower) and once with every one of them at phase 5 (upper). If the two agree the result is determinate; if not, the value is
    None with status 'incomplete_coverage' and both bounds, never a silent phase 1. With nothing reporting the status is 'no_data'.
    Returns {"value", "lower", "upper", "status"}."""
    if not reporting and n_missing == 0:
        return {"value": None, "lower": None, "upper": None, "status": "no_data"}
    lower = preliminary_severity(reporting)
    upper = preliminary_severity(list(reporting) + [5] * n_missing)
    if lower == upper and lower is not None:
        return {"value": lower, "lower": lower, "upper": upper, "status": "determinate"}
    return {"value": None, "lower": lower if lower is not None else 1, "upper": upper, "status": "incomplete_coverage"}


def clean_outcome(v):
    """An analyst-assigned indicator phase: an integer 1-5, else None."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) and 1 <= f <= 5 else None


def severity_flags(unit, phases, prelim, settings):
    """{flag number: {...}} for severity flags 1-4 (5 is manual). Flags 2 and 3 are None (not evaluable) without outcome phases."""
    outcomes = {k: clean_outcome(v) for k, v in (unit.get("outcomes") or {}).items()}
    outcomes = {k: v for k, v in outcomes.items() if v is not None}
    if settings["rules_profile"] == rules.PROFILE_ID:
        return rules.severity_flags(phases, prelim, outcomes, settings)
    flags = {}
    flags[1] = {"fired": any(p == 5 for p in phases), "value": sum(1 for p in phases if p == 5), "note": None}
    if prelim is None or not outcomes:
        flags[2] = flags[3] = {"fired": None, "value": None, "status": "not_assessable",
                               "note": "not assessable: no outcome-indicator phases assigned (blank evidence is not a passed check)"}
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
    expected = [s for s in MAIN_SECTORS if s in settings["sectors_in_scope"]]
    absent_from_file = [s for s in expected if not any(s in u["pin"] or s in u["severity"] for u in units)]
    prev = {}
    for u in previous_units or []:
        prev[uid(u)] = u
    ocha = settings["rules_profile"] == rules.PROFILE_ID
    rows = []
    totals = {"preliminary_pin": 0.0, "units_without_pin": 0, "units_with_missing_pin_sector": 0, "units_with_incomplete_severity": 0,
              "worksheet_preliminary_pin": 0.0, "units_without_worksheet_preliminary_pin": 0}
    flag_check = {"pin": {}, "severity": {}}  # worksheet's own cached flag columns (when the file has them) against the recomputed flags
    pin_counts = {n: {"fired": 0, "not_evaluable": 0} for n in range(1, 7)}
    sev_counts = {n: {"fired": 0, "not_evaluable": 0} for n in range(1, 5)}
    sev_dist, phase5 = {}, []
    stored = {"pin_compared": 0, "pin_match": 0, "pin_mismatch": [], "severity_compared": 0, "severity_match": 0, "severity_mismatch": [],
              "final_pin_total": 0.0, "final_pin_rank": {}}
    for u in units:
        ranked = ranked_pins(u, expected)
        pre, drivers = preliminary_pin(ranked)
        wx = None
        if ocha:
            pf, wx = pin_flags_worksheet(u, expected, settings, prev.get(uid(u)))
        else:
            pf = pin_flags(u, ranked, settings, expected, prev.get(uid(u)))
        phases, miss_sev, na_sev = severity_inputs(u, expected, settings["zero_severity_as"])
        sc = severity_with_coverage(phases, len(miss_sev))
        psev = sc["value"]
        # The worksheet evaluates its severity flags against ITS rule value even when coverage is incomplete. The preliminary severity itself stays empty in
        # that case (never a silent phase 1), but the flags are still computed on the worksheet's value and labelled, so the team sees what the worksheet shows.
        flag_basis = psev if (psev is not None or not ocha) else preliminary_severity(phases)
        sf = severity_flags(u, phases, flag_basis, settings)
        aor = {s: {"pin": u["pin"].get(s), "severity": u["severity"].get(s)} for s, (_c, is_aor) in SECTORS.items()
               if is_aor and (s in u["pin"] or s in u["severity"])}
        miss_pin = [s for s in expected if u["pin"].get(s) is None]
        zero_pin = [s for s in expected if u["pin"].get(s) == 0]
        if miss_pin and pre is not None:
            totals["units_with_missing_pin_sector"] += 1
        if sc["status"] == "incomplete_coverage":
            totals["units_with_incomplete_severity"] += 1
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
        worksheet = None
        if ocha:
            gated = rules.preliminary_pin(pre, psev)
            worksheet = {"preliminary_pin": gated, "highest_pin": wx["highest"], "second_highest_pin": wx["second"], "third_highest_pin": wx["third"],
                         "highest_sectors": wx["highest_sectors"], "second_highest_sectors": wx["second_sectors"], "flag_count": wx["worksheet_flag_count"],
                         "severity_rule_value": preliminary_severity(phases),
                         "severity_flags_basis": "preliminary severity" if psev is not None else ("the worksheet's rule value (coverage incomplete: the preliminary severity is empty)"
                                                                                                 if flag_basis is not None else "none"),
                         "rule_preliminary_pin": rules.preliminary_pin(pre, preliminary_severity(phases))}
            if gated is None:
                totals["units_without_worksheet_preliminary_pin"] += 1
            else:
                totals["worksheet_preliminary_pin"] += gated
        for kind, flags, got in (("pin", pf, u["stored"].get("pin_flags")), ("severity", sf, u["stored"].get("severity_flags"))):
            for n, was in (got or {}).items():
                key = str(n)
                mine = flags.get(n) if isinstance(n, int) else flags.get(6)
                if mine is None:
                    continue
                if isinstance(n, str):  # 6a / 6b: compare with the matching part of flag 6
                    part = (mine.get("parts") or {}).get("highest" if n == "6a" else "second_highest")
                    fired = bool(part and part["fired"])
                else:
                    fired = bool(mine["fired"])
                c = flag_check[kind].setdefault(key, {"compared": 0, "agree": 0, "disagree": []})
                c["compared"] += 1
                if fired == was:
                    c["agree"] += 1
                else:
                    c["disagree"].append({"unit": u["admin2_code"], "worksheet": was, "computed": fired})
        if psev is not None:
            sev_dist[psev] = sev_dist.get(psev, 0) + 1
        if psev == 5 or sf[1]["fired"]:
            phase5.append(u["admin2_code"])
        st = u["stored"]
        spre, ssev, sfin = _num(st.get("preliminary_pin")), _num(st.get("preliminary_severity", st.get("final_severity"))), _num(st.get("final_pin", st.get("total_pin")))
        cmp_pre = pre if not worksheet else worksheet["rule_preliminary_pin"] if worksheet["rule_preliminary_pin"] is not None else pre
        if spre is not None and cmp_pre is not None:
            stored["pin_compared"] += 1
            if abs(spre - cmp_pre) < 1:
                stored["pin_match"] += 1
            else:
                stored["pin_mismatch"].append({"unit": u["admin2_code"], "stored": spre, "computed": cmp_pre, "highest_pin": pre})
        if ssev is not None and psev is None and sc["status"] == "incomplete_coverage":
            stored.setdefault("severity_indeterminate", []).append({"unit": u["admin2_code"], "stored": ssev, "lower": sc["lower"], "upper": sc["upper"]})
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
        rows.append({"unit_id": uid(u), "admin2_code": u["admin2_code"], "admin2": u["admin2"], "admin3_code": u.get("admin3_code"),
                     "pocket_of_need": u.get("pocket_of_need"), "population_group": u["population_group"], "population": u["population"],
                     "preliminary_pin": pre, "drivers": drivers, "pin_flags": pf, "preliminary_severity": psev, "severity_flags": sf, "worksheet": worksheet,
                     "aor_evidence": aor,
                     "pin_coverage": {"missing_sectors": miss_pin, "zero_sectors": zero_pin, "preliminary_pin_is_lower_bound": bool(miss_pin and pre is not None)},
                     "severity_coverage": {"status": sc["status"], "lower": sc["lower"], "upper": sc["upper"], "missing_sectors": miss_sev,
                                           "not_applicable_sectors": na_sev, "reporting_sectors": len(phases)},
                     "stored": {k: v for k, v in st.items() if k != "evidence"}})
    # How many units flag 1 would flag at each threshold, and counting only missing or only zero PiN, for the team to look at (the threshold is theirs).
    miss_n = [len(r["pin_coverage"]["missing_sectors"]) for r in rows]
    zero_n = [len(r["pin_coverage"]["zero_sectors"]) for r in rows]
    top = max([a + b for a, b in zip(miss_n, zero_n)] + [3])
    sensitivity = {"missing_and_zero": {t: sum(1 for a, b in zip(miss_n, zero_n) if a + b >= t) for t in range(1, top + 1)},
                   "missing_only": {t: sum(1 for a in miss_n if a >= t) for t in range(1, top + 1)},
                   "zero_only": {t: sum(1 for b in zero_n if b >= t) for t in range(1, top + 1)}}
    assessable = sum(1 for r in rows if r["severity_flags"][2]["fired"] is not None)
    aors_present = sorted({s for r in rows for s in r["aor_evidence"]})
    return {"settings": settings, "expected_sectors": expected, "sectors_absent_from_file": absent_from_file, "rows": rows,
            "sectors_shown_as_separate_evidence": aors_present, "flag_1_sensitivity": sensitivity,
            "outcome_checks": {"assessable_units": assessable, "not_assessable_units": len(rows) - assessable}, "totals": totals, "flag_check_against_file": flag_check, "pin_flag_counts": pin_counts,
            "severity_flag_counts": sev_counts, "preliminary_severity_distribution": dict(sorted(sev_dist.items())),
            "phase5_units": phase5, "stored_comparison": stored}


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def run_analysis(file_path, input_format="auto", sheet_name=None, previous_file_path=None, previous_sheet_name=None, overrides=None):
    """Load, validate and analyse: {"error"} or {"units", "format", "notes", "issues", "previous", "analysis"}. Shared by the JIAF tools."""
    extras = {}
    loaded = load_units(file_path, input_format, sheet_name, extras=extras)
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
    # Thresholds: an explicit argument wins, then the workbook's own Thresholds cells (OCHA profile only), then the template default.
    explicit = {k: v for k, v in (overrides or {}).items() if v is not None}
    from_workbook = extras.get("thresholds") or {}
    use_wb = (explicit.get("rules_profile") or rules.PROFILE_ID) == rules.PROFILE_ID
    merged = dict(from_workbook if use_wb else {}, **explicit)
    analysis = analyze(units, previous, merged)
    analysis["threshold_sources"] = {k: ("explicit argument" if k in explicit else "workbook Thresholds sheet" if use_wb and k in from_workbook else "template default"
                                         if analysis["settings"]["rules_profile"] == rules.PROFILE_ID else "manual_reading default")
                                     for k in analysis["settings"] if k not in ("rules_profile", "sectors_in_scope", "zero_severity_as")}
    return {"units": units, "format": fmt, "notes": notes, "issues": issues, "previous": previous, "analysis": analysis}


# ------------------------------------------------------------------ tool --
def _row_for_csv(r):
    out = {"unit_id": r.get("unit_id"), "admin2_code": r["admin2_code"], "admin2": r["admin2"], "admin3_code": r.get("admin3_code"), "pocket_of_need": r.get("pocket_of_need"),
           "population_group": r["population_group"], "population": r["population"], "preliminary_pin": r["preliminary_pin"],
           "worksheet_preliminary_pin": (r.get("worksheet") or {}).get("preliminary_pin"), "pin_drivers": "|".join(r["drivers"]),
           "pin_missing_sectors": "|".join(r["pin_coverage"]["missing_sectors"]), "pin_zero_sectors": "|".join(r["pin_coverage"]["zero_sectors"]),
           "preliminary_severity": r["preliminary_severity"]}
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
    "severity is per unit; there is no national severity and no PiN per severity phase. Incomplete sector coverage is never turned into phase 1: the "
    "sectors in scope (default all eight main sectors) that have no phase are missing, and if they could change the result the unit has NO preliminary "
    "severity (status incomplete_coverage, with lower and upper bounds); a severity of 0 means not-applicable unless zero_severity_as='missing'. Several flag thresholds are readings of the manual that are not "
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
            "rules_profile": {"type": "string", "description": "'ocha_worksheet_2026' (default: the flag formulas read from OCHA's official Worksheet 3A/3B) or 'manual_reading' (this tool's older interpretation of the manual, for comparison only)."},
            "sectors_sev_5": {"type": "integer", "description": "Worksheet profile: severity flag 1 fires at this many sectors in phase 5 (and flag 4 uses it too). Default: the workbook's Thresholds cell, else 2."},
            "sectors_sev_4": {"type": "integer", "description": "Worksheet profile: the header-text reading of severity flag 4 (reported only, not used by the formula). Default 5."},
            "sectors_in_scope": {"type": "array", "items": {"type": "string"}, "description": "Main sectors the HCT activated. Default: all eight. A sector in scope with no value is MISSING, never phase 1."},
            "zero_severity_as": {"type": "string", "description": "'not_applicable' (default) or 'missing': what a severity of 0 means."},
            "f1_min_sectors": {"type": "integer", "description": "Flag 1 fires at this many sectors that are missing or zero. Worksheet profile: the workbook's zero_pin_thresh, else 2 (manual_reading: 1)."},
            "f1_count_missing": {"type": "boolean", "description": "manual_reading profile only. Flag 1 counts sectors with NO PiN. Default true."},
            "f1_count_zero": {"type": "boolean", "description": "manual_reading profile only. Flag 1 counts sectors with an explicit PiN of 0. Default true. Missing and zero are different facts."},
            "f2_pct": {"type": "number", "description": "Flag 2 threshold as a fraction (0.30 = 30%). Default: the workbook's perc_1st_2nd, else 0.30."},
            "f3_pct": {"type": "number", "description": "Flag 3 threshold as a fraction. Default: the workbook's perc_1st_3rd, else 0.50."},
            "f4_subpopulation_sectors": {"type": "array", "items": {"type": "string"}, "description": "Sectors that count a sub-population. Worksheet profile: the workbook's own list, else the template's (education). manual_reading: flag 4 is evaluated only if given."},
            "f5_share": {"type": "number", "description": "Flag 5 threshold as a share of population (fires at >=). Default: the workbook's flag_pin_perc, else 0.90."},
            "f6_pct": {"type": "number", "description": "Flag 6 threshold on the (rounded to 0.1) change from last year, up or down, as a fraction. Default: the workbook's flag_pin_historical, else 1.0."},
            "f6_min_previous_pin": {"type": "number", "description": "manual_reading profile only. Flag 6 is only evaluated when last year's PiN is at least this. Default 1000."},
            "s4_sector_count": {"type": "integer", "description": "manual_reading profile only. Severity flag 4 fires when MORE THAN this many sectors are in phase 4 (and the preliminary phase is 4). Default 4."},
            "export_csv_path": {"type": "string", "description": "Optional new .csv file for the per-unit table (refuses to overwrite)."},
            "layer_name": {"type": "string"}, "layer_key_field": {"type": "string", "description": "Admin 2 P-code field on that layer."},
            "write_fields": {"type": "boolean", "description": "With layer_name: write jf_pre_pin, jf_pre_sev, jf_npinfl, jf_nsevfl. Needs confirmation."},
        },
        "required": ["file_path"],
    },
)
def compute_jiaf_preliminary(file_path, input_format="auto", sheet_name=None, previous_file_path=None, previous_sheet_name=None,
                             rules_profile=None, sectors_sev_5=None, sectors_sev_4=None, sectors_in_scope=None, zero_severity_as=None, f1_min_sectors=None, f1_count_missing=None, f1_count_zero=None, f2_pct=None, f3_pct=None, f4_subpopulation_sectors=None, f5_share=None, f6_pct=None,
                             f6_min_previous_pin=None, s4_sector_count=None, export_csv_path=None, layer_name=None, layer_key_field=None,
                             write_fields=False, confirmed: bool = False):
    try:
        merge_settings({"rules_profile": rules_profile, "sectors_sev_5": sectors_sev_5, "sectors_sev_4": sectors_sev_4, "sectors_in_scope": sectors_in_scope, "zero_severity_as": zero_severity_as, "f1_min_sectors": f1_min_sectors, "f1_count_missing": f1_count_missing, "f1_count_zero": f1_count_zero, "f2_pct": f2_pct, "f3_pct": f3_pct, "f4_subpopulation_sectors": f4_subpopulation_sectors,
                        "f5_share": f5_share, "f6_pct": f6_pct, "f6_min_previous_pin": f6_min_previous_pin, "s4_sector_count": s4_sector_count})
    except (ValueError, TypeError) as e:
        return {"error": str(e)}
    overrides = {k: v for k, v in {"rules_profile": rules_profile, "sectors_sev_5": sectors_sev_5, "sectors_sev_4": sectors_sev_4, "sectors_in_scope": sectors_in_scope, "zero_severity_as": zero_severity_as, "f1_min_sectors": f1_min_sectors,
                                   "f1_count_missing": f1_count_missing, "f1_count_zero": f1_count_zero, "f2_pct": f2_pct, "f3_pct": f3_pct, "f4_subpopulation_sectors": f4_subpopulation_sectors,
                                   "f5_share": f5_share, "f6_pct": f6_pct, "f6_min_previous_pin": f6_min_previous_pin,
                                   "s4_sector_count": s4_sector_count}.items() if v is not None}
    if export_csv_path and os.path.exists(export_csv_path):
        return {"error": f"'{export_csv_path}' already exists; choose a new file name (nothing is overwritten)."}
    run = run_analysis(file_path, input_format, sheet_name, previous_file_path, previous_sheet_name, overrides)
    if "error" in run:
        return run
    fmt, notes, issues, previous, res = run["format"], run["notes"], run["issues"], run["previous"], run["analysis"]
    rows = res["rows"]
    nflags = lambda r: sum(1 for f in r["pin_flags"].values() if f["fired"]) + sum(1 for f in r["severity_flags"].values() if f["fired"])  # noqa: E731
    top = sorted(rows, key=lambda r: (-nflags(r), -(r["preliminary_pin"] or 0)))[:_CAP]
    result = {
        "success": True, "statement": STATEMENT, "stage": "preliminary only -- not the Final PiN, not the final severity",
        "format": fmt, "units": len(rows), "notes": notes, "input_issue_count": len(issues), "expected_sectors": res["expected_sectors"],
        "settings": {k: (list(v) if isinstance(v, tuple) else v) for k, v in res["settings"].items()}, "rules_profile": {"id": res["settings"]["rules_profile"], "label": rules.PROFILE_LABEL if res["settings"]["rules_profile"] == rules.PROFILE_ID else "manual_reading: INTERPRETATION of the manual's wording, not OCHA's rules; comparison only"},
        "threshold_sources": res.get("threshold_sources"), "readings_to_confirm": readings_for(res["settings"]),
        "validation_blockers": VALIDATION_BLOCKERS,
        "national_preliminary_pin": round(res["totals"]["preliminary_pin"], 2), "units_without_any_pin": res["totals"]["units_without_pin"],
        "national_note": "Sum over units of the highest sectoral PiN. It is a preliminary figure, not the Final Joint Overall PiN.",
        "worksheet_preliminary_pin": ({"national": round(res["totals"]["worksheet_preliminary_pin"], 2), "units_without": res["totals"]["units_without_worksheet_preliminary_pin"],
                                       "note": ("The worksheet's own 'Preliminary PiN' column: the highest PiN where the unit's severity is above 2, else 0. This gate is in OCHA's worksheet, not in "
                                                "the manual's text; it is why a severity-2 unit stores a preliminary PiN of 0. A unit with no preliminary severity (incomplete coverage) has none.")}
                                      if res["settings"]["rules_profile"] == rules.PROFILE_ID else None),
        "flag_check_against_file": ({k: {n: {"compared": c["compared"], "agree": c["agree"], "disagree": c["disagree"][:10]} for n, c in v.items()} for k, v in res["flag_check_against_file"].items()}
                                    if any(res["flag_check_against_file"].values()) else None),
        "sectors_absent_from_file": res["sectors_absent_from_file"],
        "sectors_counted": res["expected_sectors"], "sectors_shown_as_separate_evidence": res["sectors_shown_as_separate_evidence"],
        "sector_note": ("Only the sectors counted take part in the joint PiN, the flags and the severity. The AoRs (Child Protection, GBV, Mine Action, HLP) are kept "
                        "as separate evidence in each unit's aor_evidence and are never counted as additional independent sectors (doing so does not reproduce the "
                        "Yemen worksheet's severity)."),
        "flag_1_sensitivity": res["flag_1_sensitivity"],
        "flag_1_sensitivity_note": "Units flagged at each threshold, counting missing and zero together or each alone. The threshold is the team's choice.",
        "outcome_checks": dict(res["outcome_checks"], note=("Severity flags 2 and 3 need analyst-assigned outcome-indicator phases. Where they are blank the check is NOT ASSESSABLE; "
                                                           "it is not a passed comparison.")),
        "source_discrepancies": [dict(d, note="Stored value preserved; the computed value is shown beside it; nothing was corrected.")
                                 for d in res["stored_comparison"]["pin_mismatch"][:_CAP]],
        "adapter": dict(ADAPTERS[fmt], name=fmt),
        "coverage": {
            "units_with_a_missing_sector_pin": res["totals"]["units_with_missing_pin_sector"],
            "units_with_incomplete_severity": res["totals"]["units_with_incomplete_severity"],
            "note": ("A unit with a missing sector PiN keeps the highest of the reporting sectors, which can only understate it (a lower bound). A unit whose "
                     "preliminary severity depends on a missing sector has NO preliminary severity (status incomplete_coverage, with lower and upper bounds) -- "
                     "it is never reported as phase 1. Narrow sectors_in_scope only to the sectors the HCT activated."),
        },
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
