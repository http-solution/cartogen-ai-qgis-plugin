# -*- coding: utf-8 -*-
"""Match a user request to a task in the Humanitarian Mapping Task Register,
work out what information is still missing, and describe what the answer
should turn into.

Two-stage by design (see docs): stage 1 is pure local scoring -- no API call,
no latency, works offline, fully testable. Stage 2 is only reached when the
local result is genuinely ambiguous, and is the caller's job to run; this
module just says so via `ambiguous`.

Nothing here raises. A failure to match is a normal outcome, reported as an
empty match list, and the caller falls through to today's unmodified
behaviour.
"""
import re

from . import task_register as reg

# A local match is trusted when it clears this score...
CONFIDENT_SCORE = 0.34
# ...and beats the runner-up by this margin. Otherwise: ambiguous.
AMBIGUITY_MARGIN = 0.08
MAX_CANDIDATES = 5

_WORD = re.compile(r"[a-z][a-z\-]{2,}")
_STOP = frozenset("""and or the a an of for to in on with by from at into over under across per
that this these those please can you i we need want show make give help me my our it is are was
were be been being do does did how what which where when who why all any some""".split())

# Query words that carry no discriminating power inside this register: nearly
# every task contains them, so they inflate every score equally.
_REGISTER_STOP = frozenset(["map", "mapping", "data", "produce", "create", "area", "areas"])


def _tokens(text):
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def _score(qtokens, entry):
    """Overlap of query tokens with the task's vocabulary, length-normalised.

    Normalising by the TASK's token count (not the query's) stops long queries
    being dragged toward long tasks, and keeps short precise tasks findable.
    """
    kw = set(entry["kw"])
    if not kw:
        return 0.0
    strong = kw - _REGISTER_STOP
    hits = qtokens & kw
    if not hits:
        return 0.0
    # a hit on a discriminating word is worth more than one on 'map'/'data'
    weight = sum(1.0 if h in strong else 0.25 for h in hits)
    denom = len(strong) or len(kw)
    base = weight / (denom + 1.0)
    # small nudge when the section name is echoed in the query
    if _tokens(entry["cname"]) & qtokens:
        base += 0.05
    return round(min(base, 1.0), 4)


def match(query, limit=MAX_CANDIDATES):
    """Return [(entry, score)] best first. Empty when nothing scores."""
    q = _tokens(query)
    if not q:
        return []
    scored = []
    for e in reg.load():
        s = _score(q, e)
        if s > 0:
            scored.append((e, s))
    scored.sort(key=lambda x: (-x[1], x[0]["id"]))
    return scored[:limit]


def classify(query):
    """Full local verdict for a query.

    {"matches": [...], "best": entry|None, "score": float,
     "ambiguous": bool, "reason": str}

    `ambiguous` is the single signal telling the caller a disambiguation API
    call is worth making. It is True when the best score is below the
    confidence floor, or when the runner-up is within AMBIGUITY_MARGIN and
    belongs to a different section (same-section neighbours are usually
    interchangeable enough not to be worth an extra call).
    """
    ms = match(query)
    if not ms:
        return {"matches": [], "best": None, "score": 0.0,
                "ambiguous": False, "reason": "no match"}
    best, top = ms[0]
    if top < CONFIDENT_SCORE:
        return {"matches": ms, "best": best, "score": top,
                "ambiguous": True, "reason": "below confidence floor"}
    if len(ms) > 1:
        second, s2 = ms[1]
        if (top - s2) < AMBIGUITY_MARGIN and second["cat"] != best["cat"]:
            return {"matches": ms, "best": best, "score": top,
                    "ambiguous": True, "reason": "tie across sections"}
    return {"matches": ms, "best": best, "score": top,
            "ambiguous": False, "reason": "confident"}


# The user naming an output explicitly beats the task's default contract.
# "make a dashboard of displacement over time" matches a task whose contract
# is `layer`; the word "dashboard" is a direct instruction and must win.
_OUTPUT_OVERRIDE = [
    ("dashboard", r"\bdashboard\b"),
    ("report",    r"\breport\b|\bsitrep\b|\bsituation report\b|\bwrite[- ]?up\b|\bprofile\b"),
    ("layout",    r"\bprint layout\b|\bmap book\b|\batlas\b|\bprintable\b|\bpdf map\b|\bposter\b"),
    ("dataset",   r"\bexport\b|\bgeopackage\b|\bshapefile\b|\bgeojson\b|\bcsv\b|\bdownload\b"),
    ("analysis",  r"\bhow many\b|\bhow much\b|\bcalculate\b|\bstatistics\b|\btable\b|\bcount\b"),
    ("layer",     r"\bon the map\b|\badd .*layer\b|\bstyle\b|\bsymboli[sz]e\b"),
]


def output_override(query):
    """The output the user explicitly asked for, or None."""
    q = (query or "").lower()
    for kind, pat in _OUTPUT_OVERRIDE:
        if re.search(pat, q):
            return kind
    return None


# --------------------------------------------------------------- slots -----

# Evidence in the query itself that a slot is already answered.
_SLOT_EVIDENCE = {
    "aoi":            r"\bin ([A-Z][\w\-']+)|\bfor ([A-Z][\w\-']+)|current (extent|canvas|view)|"
                      r"\bthis layer\b|\bloaded\b|\bselected\b",
    "admin_level":    r"admin\s*[0-3]|district|province|governorate|country level|admin level",
    "time_range":     r"\b(19|20)\d{2}\b|last \w+ (day|week|month|year)|since |between .* and |"
                      r"q[1-4]\b|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec",
    "hazard_type":    r"flood|drought|earthquake|cyclone|landslide|wildfire|tsunami|volcan|storm|"
                      r"conflict|heat|avalanche",
    "imagery":        r"sentinel|landsat|planet|maxar|drone|orthomos|radar|sar\b|ndvi|imagery from",
    "population_src": r"worldpop|hdx|census|gridded|facebook|meta population|our own|existing layer",
    "facility_type":  r"health|school|clinic|hospital|water point|borehole|latrine|market|warehouse|"
                      r"shelter|distribution point",
    "threshold":      r"\d+\s*(km|kilometre|kilometer|m\b|metre|meter|min|minute|hour|hr)\b",
    "sector":         r"\bwash\b|nutrition|food security|protection|education|shelter|livelihood|health",
}


def missing_slots(entry, query, context=None):
    """Slots the task needs that neither the query nor QGIS context supplies.

    `context` is an optional dict of things the host already knows, e.g.
    {"aoi": "canvas extent", "admin_level": "admin2"}; pass what QGIS can
    answer so the user is never asked for it.
    """
    if not entry:
        return []
    ctx = context or {}
    q = (query or "").lower()
    out = []
    for slot in entry.get("slots", []):
        if ctx.get(slot):
            continue
        pat = _SLOT_EVIDENCE.get(slot)
        if pat and re.search(pat, query or "", re.I):
            continue
        if pat and re.search(pat, q):
            continue
        out.append(slot)
    return out


def clarify_question(entry, missing):
    """One consolidated question covering every missing slot.

    Policy is 'ask once, then default': this is asked a single time. If the
    user does not answer, the caller applies defaults() and states them.
    """
    if not entry or not missing:
        return ""
    lines = ["To do this well I need a bit more: **%s**" % entry["text"], ""]
    for s in missing:
        lines.append("- %s" % reg.SLOT_QUESTIONS.get(s, s))
    lines.append("")
    stated = defaults(missing)
    if stated:
        lines.append("If you'd rather I just proceed, I'll use: "
                     + "; ".join("%s = %s" % (k, v) for k, v in stated.items()) + ".")
    return "\n".join(lines)


def defaults(missing):
    """{slot: value} for the missing slots that have a safe default.

    Slots whose default is None are deliberately excluded -- guessing a hazard
    type or a sector produces confidently wrong humanitarian output.
    """
    out = {}
    for s in missing:
        val, kind = reg.SLOT_DEFAULTS.get(s, (None, "ask"))
        if val is not None and kind != "ask":
            out[s] = val
    return out


def unresolvable(missing):
    """Missing slots that have no safe default and genuinely need an answer."""
    return [s for s in missing if reg.SLOT_DEFAULTS.get(s, (None, "ask"))[0] is None]


# ------------------------------------------------------- prompt + output ---

def task_directive(entry, filled=None, query=None):
    """The compact instruction injected into the model prompt.

    Deliberately short: this rides alongside the existing system prompt, and
    prompt_refiner.py's budget discipline applies here too.
    """
    if not entry:
        return ""
    parts = [
        "Recognised task %s (%s): %s." % (entry["id"], entry["cname"], entry["text"]),
        "Deliver: %s." % reg.OUTPUT_INTENT.get(output_override(query) or entry["out"],
                                              entry["out"]),
    ]
    if entry.get("tools"):
        parts.append("Prefer these tools, in order: %s." % ", ".join(entry["tools"]))
    if filled:
        parts.append("Given: " + "; ".join("%s = %s" % (k, v) for k, v in filled.items()) + ".")
    return " ".join(parts)


def output_contract(entry, query=None):
    """What the caller should do with the model's answer.

    {"kind": "layer", "intent": "...", "render": [tool names], "task": "id"}
    `render` is the tail of the tool chain -- the part that turns a result
    into something the user can see.
    """
    if not entry:
        return None
    kind = output_override(query) or entry["out"]
    RENDER = {
        "layer":     ["apply_categorized_style", "zoom_to_layer"],
        "layout":    ["create_print_layout", "print_map"],
        "dashboard": ["generate_html_dashboard"],
        "report":    ["generate_report", "generate_spatial_report"],
        "analysis":  ["field_statistics", "export_to_csv"],
        "dataset":   ["export_layer", "export_to_csv"],
        "guidance":  [],
    }
    return {
        "task": entry["id"],
        "kind": kind,
        "overridden": kind != entry["out"],
        "intent": reg.OUTPUT_INTENT.get(kind, kind),
        "render": [t for t in RENDER.get(kind, []) if t in entry.get("tools", [])]
                  or RENDER.get(kind, []),
    }
