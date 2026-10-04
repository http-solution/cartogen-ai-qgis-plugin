# -*- coding: utf-8 -*-
"""JIAF 2 flag rules, profile `ocha_worksheet_2026`: the PiN and severity flags exactly as OCHA's Worksheet 3A/3B computes them.

SUPPORT FOR PEOPLE WHO RUN THE JIAF 2 PROCESS. NOT the JIAF method, NOT endorsed by OCHA or the IASC.

Where these rules come from: the formulas were READ from the cells of OCHA's official "Worksheet_3A_3B_PiNSev_Example.xlsx" and "_Template.xlsx" (sheets
'WS - 3.1 Overall PiN', 'WS - 3.2 Intersectoral Severity', 'PiN Historical Trend', 'Thresholds'), not inferred from the manual's wording. The example
workbook's cached values reproduce (tests/test_jiaf_worksheet_adapter.py, local-only because the workbook's licence is unknown and it is not committed).

Worksheet behaviour that differs from a plain reading of the manual, and is reproduced here ON PURPOSE (each is also reported in the result):
- RANKS ARE OF DISTINCT VALUES. The 2nd highest PiN is the largest value strictly below the highest, the 3rd the largest strictly below the 2nd. Two sectors
  tied for the highest are both "highest"; the next distinct value is "2nd". Zeros count as values, blanks do not.
- A TIE FOR THE HIGHEST SUPPRESSES flags 2 and 3 (the worksheet leaves them blank); it also stops flag 4 matching (the highest-sector text has several lines).
- FLAG 1 counts sectors that are blank OR zero and fires at `zero_pin_thresh` (template default 2); it is left blank when all sectors sum to 0.
- FLAGS 2 and 3 are (highest - Nth) / Nth, so they can exceed 100%, and fire at >= the threshold. Division by a 0 or absent comparison PiN leaves flag 2 blank.
  Flag 3 is the exception: its formula tests the DIFFERENCE column for blank, not the percentage column, so with a 3rd highest of exactly 0 the percentage is ""
  and Excel's text-greater-than-number rule makes `"" >= threshold` TRUE. That is reproduced and labelled `worksheet_text_comparison`; it was NOT seen in a cached
  example row (no example row has a 3rd highest of 0), so it rests on the formula text and on Excel's documented comparison order.
- FLAG 4 fires when the single highest sector is one of the sub-population sectors (the template list ships with only "Education"; the country edits it). There is
  no 50% comparison in the formula.
- FLAG 5 compares the UNROUNDED highest PiN / population with `flag_pin_perc` (template 90%) at >=; blank when the population is 0 or missing.
- FLAG 6 is two flags in the worksheet (highest sector(s), and 2nd-highest sector(s)), each counted separately in '# Flags'. The change per sector is
  ROUND((new - old) / old, 1); blank when old is blank/0 or new is blank. If any sector involved has a blank change the whole flag is blank.
- SEVERITY flags use the thresholds sectors_sev_5 (template 2) and sectors_sev_4 (template 5). The formulas: flag 1 = count of sectors in phase 5 >= sectors_sev_5;
  flag 4 = preliminary 5 AND the number of sectors in phases 1-4 >= sectors_sev_5. Its HEADER says "More than 4 sectors in 4 or worse while preliminary is 4 or
  lower" and sectors_sev_4 is defined but no formula uses it: the formula and the header disagree, the FORMULA is implemented, and the header's reading is returned
  beside it as `header_text_reading`. Flag 2 = any outcome phase 2+ away from the preliminary; flag 3 = at least two outcomes 1+ below OR at least two 1+ above it.
- PRELIMINARY PiN (worksheet) = the highest PiN if the severity is above 2, else 0. This gate is in the worksheet's column 'Preliminary PiN' and not in the
  manual's text. It is why Yemen's two severity-2 units carry a stored preliminary PiN of 0: a rule, not a data error.

What this module does NOT verify: the Yemen worksheet holds values only (no flag formulas), so the flag decisions its analysis team actually took are not in any
supplied file; the example workbook's historical table is empty, so flag 6 is checked on synthetic cases only; the 'Reference Table Indicators' sheet that can derive
outcome phases from raw indicators is not implemented.
"""
from decimal import ROUND_HALF_UP, Decimal

PROFILE_ID = "ocha_worksheet_2026"
PROFILE_LABEL = "OCHA Worksheet 3A/3B rules (formulas read from the official example and template workbooks)"
# Worksheet named cells -> this module's setting names.
THRESHOLD_NAMES = {"zero_pin_thresh": "f1_min_sectors", "perc_1st_2nd": "f2_pct", "perc_1st_3rd": "f3_pct", "flag_pin_perc": "f5_share",
                   "flag_pin_historical": "f6_pct", "sectors_sev_5": "sectors_sev_5", "sectors_sev_4": "sectors_sev_4"}
# Template defaults (the 'Country Threshold' column of the supplied example; the template's "Recommended" column is identical).
TEMPLATE_DEFAULTS = {"f1_min_sectors": 2, "f2_pct": 0.30, "f3_pct": 0.50, "f5_share": 0.90, "f6_pct": 1.0, "sectors_sev_5": 2, "sectors_sev_4": 5,
                     "f4_subpopulation_sectors": ("education",)}


def excel_round(x, digits=1):
    """Excel's ROUND: half away from zero, on the 15 significant digits Excel keeps."""
    d = Decimal(format(float(x), ".15g"))
    return float(d.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def distinct_ranks(values):
    """(highest, 2nd, 3rd) as the worksheet defines them: successive DISTINCT values, None where there is none. `values` may contain None (blank)."""
    nums = sorted({v for v in values if v is not None}, reverse=True)
    return tuple(nums[i] if len(nums) > i else None for i in range(3))


def _gap(top, other):
    """(top - other) / other, or None when `other` is absent or 0 (the worksheet's IFERROR -> blank)."""
    if other is None or other == 0:
        return None
    return (top - other) / other


def historical_changes(current, old):
    """{sector: ROUND((new - old) / old, 1) or None}. None (blank) when old is blank or 0, or new is blank. `old` None = the unit is not in the table."""
    out = {}
    for sector, new in current.items():
        o = None if old is None else old.get(sector)
        out[sector] = None if (new is None or o is None or o == 0) else excel_round((new - o) / o, 1)
    return out


def _flag(fired, value=None, note=None, **extra):
    return dict({"fired": fired, "value": value, "note": note}, **extra)


def pin_flags(vals, population, s, old_pins=None):
    """PiN flags 1-6 as {n: {"fired": True/False/None, "value", "note", ...}}. `vals` = {sector: PiN or None} for the sectors counted; `old_pins` = last year's
    {sector: PiN} for the unit, or None when the unit is not in the historical table. fired None = the worksheet shows a blank because the inputs make the test
    undefined (missing, zero denominator, no data); False with status 'suppressed_tie' = the test was switched off by a tie for the highest."""
    present = [v for v in vals.values() if v is not None]
    h1, h2, h3 = distinct_ranks(present)
    top = [k for k, v in vals.items() if h1 is not None and v == h1]
    second = [k for k, v in vals.items() if h2 is not None and v == h2]
    flags = {}

    n_zero = sum(1 for v in present if v == 0)
    absent = [k for k, v in vals.items() if v is None]
    zero = [k for k, v in vals.items() if v == 0]
    detail = {"missing_sectors": absent, "zero_sectors": zero}
    counted = n_zero + len(absent)
    if sum(present) == 0:
        flags[1] = _flag(None, counted, "left blank by the worksheet: the sectors sum to 0 (all zero or missing)", detail=detail)
    else:
        flags[1] = _flag(counted >= s["f1_min_sectors"], counted, None, detail=detail)

    for n, other, key in ((2, h2, "f2_pct"), (3, h3, "f3_pct")):
        pct = None if h1 is None else _gap(h1, other)
        if h1 is None or other is None:
            flags[n] = _flag(None, None, "left blank by the worksheet: no distinct " + ("2nd" if n == 2 else "3rd") + " highest PiN")
        elif n == 2 and pct is None:
            # Flag 2's formula tests the percentage column for blank BEFORE it tests for a tie, so a 2nd highest of 0 is blank even when the top is tied.
            flags[n] = _flag(None, None, "left blank by the worksheet: the 2nd highest PiN is 0 (division by zero)")
        elif len(top) > 1:
            flags[n] = _flag(False, pct, "suppressed: " + str(len(top)) + " sectors are tied for the highest PiN", status="suppressed_tie")
        elif pct is None and n == 3:
            # Worksheet quirk, see the module docstring: the 3rd-highest flag tests the difference column, so "" >= threshold is TRUE in Excel.
            flags[n] = _flag(True, None, "the 3rd highest PiN is 0, so the percentage is blank and the worksheet's text-versus-number comparison flags it",
                             status="worksheet_text_comparison")
        else:
            flags[n] = _flag(pct >= s[key], pct, None)

    sub = set(s["f4_subpopulation_sectors"])
    if h1 is None or h1 == 0:
        flags[4] = _flag(None, None, "left blank by the worksheet: no highest PiN above 0")
    elif len(top) > 1:
        flags[4] = _flag(False, None, "tie for the highest PiN: the worksheet's highest-sector text has several lines and matches no sector", status="suppressed_tie")
    else:
        flags[4] = _flag(top[0] in sub, None, top[0] if top[0] in sub else None)

    if h1 is None or not population or population <= 0:
        flags[5] = _flag(None, None, "left blank by the worksheet: no highest PiN, or the population is 0 or missing")
    else:
        share = h1 / population
        flags[5] = _flag(share >= s["f5_share"], share,
                         "above 100% of the population: likely a data error unless the sector counts a subset" if share > 1 else None)

    parts = {}
    if old_pins is None or h1 is None:
        flags[6] = _flag(None, None, "no previous-year row for this unit" if old_pins is None else "no highest PiN")
    else:
        ch = historical_changes(vals, old_pins)
        for label, sectors in (("highest", top), ("second_highest", second)):
            if not sectors or any(ch[x] is None for x in sectors):
                parts[label] = {"fired": None, "sectors": sectors, "changes": {x: ch[x] for x in sectors}}
            else:
                parts[label] = {"fired": any(abs(ch[x]) >= s["f6_pct"] for x in sectors), "sectors": sectors, "changes": {x: ch[x] for x in sectors}}
        states = [p["fired"] for p in parts.values()]
        fired = True if any(states) else (None if all(x is None for x in states) else False)
        flags[6] = _flag(fired, None, "two worksheet flags (highest sector(s); 2nd highest sector(s)), each counted in '# Flags'" if fired else None, parts=parts)
    return flags, {"highest": h1, "second": h2, "third": h3, "highest_sectors": top, "second_sectors": second,
                   "worksheet_flag_count": sum(1 for n, f in flags.items() if n != 6 and f["fired"]) + sum(1 for p in parts.values() if p["fired"])}


def preliminary_pin(highest, severity):
    """Worksheet 'Preliminary PiN': the highest PiN if the severity is above 2, else 0. None when either is unknown (the worksheet would treat a blank severity
    as above 2 and pass the highest PiN through; that is not reproduced because it hides a missing severity)."""
    if highest is None or severity is None:
        return None
    return highest if severity > 2 else 0.0


def severity_flags(phases, prelim, outcomes, s):
    """Severity flags 1-4 as {n: {...}}. `phases` = the reporting sectors' phases (1-5), `prelim` = preliminary severity or None, `outcomes` = {name: phase 1-5}."""
    n = lambda p: sum(1 for x in phases if x == p)  # noqa: E731
    thr5 = s["sectors_sev_5"]
    flags = {1: _flag(n(5) > 0 and n(5) >= thr5, n(5))}
    if prelim is None:
        flags[2] = flags[3] = flags[4] = _flag(None, None, "no preliminary severity (incomplete coverage or no data)", status="not_assessable")
        return flags
    low = sum(n(p) for p in (1, 2, 3, 4))
    flags[4] = _flag(prelim == 5 and low >= thr5, low,
                     "the worksheet FORMULA is implemented (preliminary 5 and at least sectors_sev_5 sectors in phases 1-4); its header says something else",
                     header_text_reading=bool(prelim <= 4 and sum(1 for x in phases if x >= 4) >= s["sectors_sev_4"]))
    if not outcomes:
        flags[2] = flags[3] = _flag(None, None, "not assessable: no outcome-indicator phases assigned (blank evidence is not a passed check)", status="not_assessable")
    else:
        diffs = {k: v - prelim for k, v in outcomes.items()}
        flags[2] = _flag(any(abs(d) >= 2 for d in diffs.values()), diffs)
        flags[3] = _flag(sum(1 for d in diffs.values() if d <= -1) >= 2 or sum(1 for d in diffs.values() if d >= 1) >= 2, diffs)
    return flags
