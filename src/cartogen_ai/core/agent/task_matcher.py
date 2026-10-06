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
import os
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



def _indefinite_article(word):
    """'an' before a vowel letter, else 'a' (F15: the router card said 'a analysis')."""
    first = str(word or "")[:1].lower()
    return "an" if first and first in "aeiou" else "a"


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


# Travel-time/access phrasing ("beyond one hour's travel", "within 30 minutes",
# "reachable in under an hour", "drive time") signals a service-area/travel-time
# analysis task, not a plain facility-mapping one -- but _score's own normalisation
# (by the TASK's keyword count, "keeps short precise tasks findable" above)
# structurally favours short, generic keyword lists over longer, more specific
# ones: a 2-word hit against a 3-word kw list scores far higher than an equally
# strong 3-word hit against a 5-word kw list. Live-reported bug, 2026-09-19:
# "Health facilities beyond one hour's travel" matched 25c.01 ("Map health
# facilities", score 0.72, kw={facilities,health,map}) over 7.23 ("Calculate
# travel time to health facilities", the actually-correct task, score 0.55,
# kw={calculate,facilities,health,time,travel}) purely because 7.23's kw list is
# longer. 25c.01's tool hints (add_layer_from_path/apply_categorized_style/
# zoom_to_layer) assume a local data file that doesn't exist; the model then had
# no calculate_service_area in its directive, couldn't find that file, and burned
# its entire tool-call budget probing execute_pyqgis_script's sandbox internals
# instead of ever calling the right tool. Re-ranks toward whichever ALREADY-
# scored candidate uses calculate_service_area when this language is present,
# rather than reweighting the shared scoring formula itself (a change with much
# wider blast radius across every other task in the register -- flagged in
# docs/IMPLEMENTATION_TRACKER.md as a real, unresolved scoring-design tension,
# not silently "fixed" by this narrower, targeted re-rank).
_ACCESS_TIME_LANGUAGE = re.compile(
    r"\b(within|beyond|under|over)\b.{0,20}\b(hour|hr|minute|min)s?\b|"
    r"\b(hour|hr|minute|min)'?s?\s+(travel|driv(?:e|ing)|walk(?:ing)?|reach)|"
    r"\bservice[\s-]?areas?\b.{0,40}\b(hour|hr|minute|min)s?\b|\b(hour|hr|minute|min)s?\b.{0,30}\bservice[\s-]?areas?\b|"
    r"\btravel[\s-]?time\b|\bdrive[\s-]?time\b|\breachable\b|\bunreachable\b|\bisochrone\b"
)


# A short fragment with no action word and no question is not a request. rc11 smoke test (#130): the pasted fragment
# "template: access_map" matched a conflict-analysis task at 0.42, the preview invented "threshold = 5 km", and the user's "yes"
# ran a whole new analysis. Such a message is sent as typed, with no task directive.
_ACTION_WORDS = re.compile(
    r"\b(calculate|compute|create|make|build|show|map|find|list|download|fetch|load|add|remove|delete|export|estimate|"
    r"generate|run|classify|compare|analy[sz]e|draw|plot|clip|buffer|merge|join|style|label|zoom|select|count|"
    r"summari[sz]e|identify|extract|convert|how|what|which|where|who|when|why|can|could|please)\b"
)
_FRAGMENT_MAX_WORDS = 4


def _is_non_request_fragment(query):
    text = (query or "").lower()
    if "?" in text or len(_tokens(text)) > _FRAGMENT_MAX_WORDS:
        return False
    return not _ACTION_WORDS.search(text)


# A request that names a tool ("Use optimal_hub_siting to ...") has already said what to run. rc15 hand test (2026-10-06): that request
# matched an OpenStreetMap export task at 0.50, and "Run extract_features_from_imagery on ..." matched an OSM download task at 0.50; the
# injected "prefer these tools" list then steered the model away from the tool the user named, into unrelated calls and a spent call
# budget. A matched task is trusted only if it uses a tool the request names.
_TOOL_NAME = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
# A candidate that does use the named tool must still clear this share of the confidence floor to replace the best match.
_NAMED_TOOL_FLOOR = 0.75


def _known_tool_names():
    """Every tool name the register mentions, plus the live registry when the tools package is loaded. Never raises."""
    names = set()
    for e in reg.load():
        names.update(e.get("tools") or [])
    try:
        from .tools.registry import TOOL_REGISTRY
        names.update(TOOL_REGISTRY)
    except Exception:
        pass
    return names


def named_tools(query):
    """Tool names the query spells out, e.g. {"optimal_hub_siting"}."""
    candidates = set(_TOOL_NAME.findall((query or "").lower()))
    return candidates & _known_tool_names() if candidates else set()


_TIE_MIN_COVERAGE = 0.25
_SINGLE_HIT_MAX_TOKENS = 8


def _coverage(query, entry):
    """Share of the request's content words that the task's keywords account for (0..1)."""
    tokens = _tokens(query)
    return len(tokens & set(entry.get("kw") or ())) / len(tokens) if tokens else 0.0


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
    if _is_non_request_fragment(query):
        return {"matches": [], "best": None, "score": 0.0,
                "ambiguous": False, "reason": "too short to be a request"}
    ms = match(query)
    if not ms:
        return {"matches": [], "best": None, "score": 0.0,
                "ambiguous": False, "reason": "no match"}
    named = named_tools(query)
    if named:
        usable = [(e, sc) for e, sc in ms if named & set(e.get("tools") or [])]
        if not usable or usable[0][1] < CONFIDENT_SCORE * _NAMED_TOOL_FLOOR:
            return {"matches": ms, "best": None, "score": 0.0, "ambiguous": False,
                    "reason": "names a tool the matched task does not use"}
        ms = usable
    best, top = ms[0]
    if _ACCESS_TIME_LANGUAGE.search((query or "").lower()) and \
            "calculate_service_area" not in best.get("tools", []):
        for e, s in ms:
            if "calculate_service_area" in e.get("tools", []):
                best, top = e, s
                break
    # An access/drive-time request whose best task is NOT led by calculate_service_area is a wrong match, and a wrong directive is
    # worse than none (rc10 smoke test: "Calculate a one-hour driving service area from the point ..." matched 21.23 "Calculate
    # area and density" at 0.42 and the model went on to fetch a population raster, estimate exposure and export a CSV nobody
    # asked for). Treat it like a below-floor match: no directive, the message is sent as typed.
    if _ACCESS_TIME_LANGUAGE.search((query or "").lower()) and (best.get("tools") or [None])[0] != "calculate_service_area":
        return {"matches": ms, "best": best, "score": top,
                "ambiguous": True, "reason": "below confidence floor"}
    if top < CONFIDENT_SCORE:
        return {"matches": ms, "best": best, "score": top,
                "ambiguous": True, "reason": "below confidence floor"}
    # In a long request one shared word is a coincidence, whatever it scores: a task with a two-word keyword list scores 0.33-0.5 on
    # a single hit. rc17 hand test R4: a raster colour-ramp request shared one word with a data-standards task. A long request needs
    # two distinct hits; a short one ("a dashboard of displacement by district") may be matched on one.
    if len(_tokens(query)) > _SINGLE_HIT_MAX_TOKENS and len(_tokens(query) & set(best.get("kw") or ())) < 2:
        return {"matches": ms, "best": best, "score": top,
                "ambiguous": True, "reason": "below confidence floor"}
    if len(ms) > 1:
        second, s2 = ms[1]
        if (top - s2) < AMBIGUITY_MARGIN and second["cat"] != best["cat"]:
            # A tie is only trusted when the winner's keywords cover a fair share of the request's own content words. rc15 and rc17
            # hand tests: a 22-word severity request matched "Spatial analysis" and an 18-word buffer-clip-export plan matched a
            # water and sanitation task, each on two generic words ("calculate", "population"; "distance", "points"), and the
            # injected task directive sent the model after WorldPop and service-area tools nobody asked for. A short request that
            # the task really describes ("build me a dashboard of displacement by district") covers about half of its words.
            # Below the bar the verdict is the same as "below confidence floor": no directive, message sent as typed.
            if _coverage(query, best) < _TIE_MIN_COVERAGE:
                return {"matches": ms, "best": best, "score": top,
                        "ambiguous": True, "reason": "below confidence floor"}
            return {"matches": ms, "best": best, "score": top,
                    "ambiguous": True, "reason": "tie across sections"}
    return {"matches": ms, "best": best, "score": top,
            "ambiguous": False, "reason": "confident"}


# The user naming an output explicitly beats the task's default contract.
# "make a dashboard of displacement over time" matches a task whose contract
# is `layer`; the word "dashboard" is a direct instruction and must win.
_OUTPUT_OVERRIDE = [
    ("dashboard", r"\bdashboard\b"),
    # "report" as a NOUN names a deliverable ("write a report", "a situation report", "report on ..."); as a VERB it only asks for the answer
    # ("Report the model used and the detection count", "report each ID"). rc18 hand test R3/N5 (2026-10-06): the verb form forced an
    # MD-file deliverable, and after a failed run a follow-up turn demanded generate_spatial_report that nobody asked for.
    ("report",    r"\b(?:a|an|the|my|our|this|that|full|short|written|pdf|word|spatial|situation|summary)\s+(?:\w+\s+)?report\b|"
                  r"\breport\s+(?:on|about)\b|\bsitrep\b|\bwrite[- ]?up\b|\bprofile\b|\b(?:generate|write|produce|prepare|draft|create|make)\s+(?:\w+\s+){0,2}report\b"),
    ("layout",    r"\bprint layout\b|\bmap book\b|\batlas\b|\bprintable\b|\bpdf map\b|\bposter\b"),
    # "download" is deliberately NOT here: "download the whole Yemen population raster and then estimate ..." names the INPUT to
    # fetch, not a file to produce. Matching it forced a GPKG+CSV deliverable and a follow-up call that wrote four unrequested
    # export files (rc10 smoke test, 2026-10-01). A file is requested by naming a format or the word export.
    ("dataset",   r"\bexport\b|\bgeopackage\b|\bshapefile\b|\bgeojson\b|\bcsv\b"),
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
    "imagery":        r"sentinel|landsat|planet|maxar|drone|orthomos|radar|sar\b|ndvi|imagery from|\bloaded raster\b|\braster\b|\.tiff?\b|"
                      r"\bimage layer\b",
    "population_src": r"worldpop|hdx|census|gridded|facebook|meta population|our own|existing layer",
    # A coordinate pair or "the point/origin" also answers it: a service area can start from a point rather than a
    # facility, and asking "which facility type?" of "population within one hour's drive of the point 4902068.0, 1799912.0"
    # was a question with no answer (rc10 smoke test, 2026-10-01).
    "facility_type":  r"health|school|clinic|hospital|water point|borehole|latrine|market|warehouse|"
                      r"shelter|distribution point|\bhubs?\b|\bdepots?\b|\bfacilit(?:y|ies)\b|\bsites?\b|\bcamps?\b|"
                      r"\bcent(?:re|er)s?\b|\bstations?\b|-?\d+\.\d+\s*,\s*-?\d+\.\d+|"
                      r"\b(?:the|this|that|my|an?)\s+(?:point|origin|location|site|coordinates?)\b",
    # A number (digits or a word) followed by a distance or time unit, plurals included. This was
    # digits-only with singular-only units ("hour\b" can't match "hours"), so "one hour's travel",
    # "2 hours" and "30 minutes" all counted as no threshold. The 5 km default was then added
    # next to the user's own one-hour limit. Live-reported 2026-09-24: "Health facilities beyond
    # one hour's travel" became "Given: threshold = 5 km" and a plan step saying "(1 hour / 5 km)".
    "threshold":      r"\b(?:\d+(?:\.\d+)?\s*|(?:an?|one|two|three|four|five|six|seven|eight|nine|ten|"
                      r"fifteen|twenty|thirty|forty|forty-five|fifty|sixty|ninety|half an?)\s+)"
                      r"(?:km|kms|kilomet(?:er|re)s?|m|met(?:er|re)s?|mins?|minutes?|hours?|hrs?)\b",
    "sector":         r"\bwash\b|nutrition|food security|protection|education|shelter|livelihood|health",
    # Engineering hydrology (task 36.01): none of these has a default, because a guessed DEM, IDF curve or runoff coefficient
    # produces a confident-looking design number with nothing behind it.
    "dem_source":     r"\bdem\b|digital elevation|copernicus dem|srtm|alos aw3d|elevation raster",
    "idf_source":     r"\bidf\b|intensity.duration.frequency|rainfall station|design rainfall (?:curve|source)",
    "runoff_coefficient": r"runoff coefficient|coefficient\s+c\b|\bc\s*=\s*(?:0(?:\.\d+)?|1(?:\.0+)?)\b",
}


# A request that names its own data ("candidate locations in smoke_hubs ... demand in smoke_points") has said where the facilities,
# the area and the population are; asking "Which facility or service type?" of it was a question with no answer (rc17 hand test R2,
# 2026-10-06: asked twice and "Synthetic humanitarian supply hubs" was not accepted). Slots with no safe default that name a
# real-world choice (hazard, sector, DEM ...) are NOT satisfied this way.
_DATA_REFERENCE_SLOTS = frozenset({"facility_type", "aoi", "admin_level", "population_src"})
_SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def has_explicit_data_reference(query, layer_names=None):
    """True when the query names data the user already has.

    With `layer_names` (the project's loaded layers) it is true only if one of them is named in the query: a snake_case word that is
    a column or an algorithm name is not a data reference (code review of the first version). Without it (no project information,
    e.g. offline tests) a snake_case word that is not a tool name, or a data file name, counts."""
    low = (query or "").lower()
    if layer_names is not None:
        return any(n and re.search(r"(?<![\w])" + re.escape(str(n).lower()) + r"(?![\w])", low) for n in layer_names)
    tools = _known_tool_names()
    if any(t not in tools for t in _SNAKE.findall(low)):
        return True
    return bool(re.search(r"\b[\w\-]+\.(?:gpkg|shp|geojson|csv|tif|tiff|kml)\b", low))


def missing_slots(entry, query, context=None, layer_names=None):
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
    own_data = has_explicit_data_reference(query, layer_names)
    for slot in entry.get("slots", []):
        if ctx.get(slot):
            continue
        if own_data and slot in _DATA_REFERENCE_SLOTS:
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
    tools = list(entry.get("tools") or [])
    # A tool the user named leads the chain: "Run extract_features_from_imagery on loaded raster smoke_image" matched a task whose chain starts
    # with OSM fetches (rc18 R3), and the model was told to try those first.
    named = [t for t in tools if t in named_tools(query or "")]
    if named:
        tools = named + [t for t in tools if t not in named]
    # When the user overrides the output ("...as a dashboard"), the task's own
    # chain ends in the wrong renderer. Append the one the requested output
    # actually needs, or the model is told to deliver an HTML dashboard while
    # being handed a chain that ends in zoom_to_layer.
    for t in (output_contract(entry, query) or {}).get("render", []):
        if t not in tools:
            tools.append(t)
    if tools:
        parts.append("Prefer these tools, in order: %s." % ", ".join(tools))
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
    explicit = output_override(query)
    kind = explicit or entry["out"]
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
        # True only when the user's own words named the output. The auto-follow-up in
        # output_router acts on this alone: a task match merely *implying* a deliverable is
        # not a request for one (rc7 smoke test F10: an unrequested CSV export was forced).
        "explicit": explicit is not None,
        "intent": reg.OUTPUT_INTENT.get(kind, kind),
        "render": [t for t in RENDER.get(kind, []) if t in entry.get("tools", [])]
                  or RENDER.get(kind, []),
    }


# ------------------------------------------------------- files in and out --

def attachment_plan(entry, attachments):
    """What will be done with each attached file, and whether it fits the task.

    Returns [{"path", "name", "kind", "tool", "line", "accepted"}]. `accepted`
    is False when the task does not list that media kind -- the file is still
    described and still sent, but the caller can say so rather than silently
    ignoring it.
    """
    from . import file_io

    out = []
    acc = set((entry or {}).get("acc", []) or [])
    for path in attachments or []:
        kind = file_io.classify(path)
        line = file_io.describe_attachment(path, (entry or {}).get("text", ""))
        out.append({
            "path": path,
            "name": os.path.basename(path or ""),
            "kind": kind,
            "tool": file_io.reader_for(kind, (entry or {}).get("text", "")) if kind else None,
            "line": line or "%s -- unrecognised file type, sent as plain text"
                            % os.path.basename(path or ""),
            "accepted": bool(kind) and (not acc or kind in acc),
        })
    return out


def compose_user_message(query, filled=None, plan=None):
    """The exact text that will be sent as the user turn.

    The original wording is never rewritten -- it leads, verbatim. What is
    appended is only the facts the model would otherwise have to guess at:
    the slot values that were resolved on its behalf, and what each attached
    file is. Nothing here restates the system prompt.
    """
    parts = [(query or "").strip()]
    if filled:
        parts.append("Given: " + "; ".join("%s = %s" % (k, v)
                                           for k, v in sorted(filled.items())) + ".")
    if plan:
        lines = ["Attached files:"]
        for p in plan:
            lines.append("- " + p["line"])
        parts.append("\n".join(lines))
    return "\n\n".join(p for p in parts if p)


def expected_output(entry, query=None):
    """One sentence naming the artifact the user should end up with."""
    from . import file_io

    if not entry:
        return ""
    kind = output_override(query) or entry["out"]
    return file_io.artifact_sentence(kind, entry.get("tools", []))


def reasoning(entry, score, filled, plan, query=None):
    """Why this request is being sent the way it is -- shown to the user.

    Every line is a statement about a decision that was actually made, in the
    order it was made. No line is decorative: if there were no attachments,
    there is no attachment line.
    """
    if not entry:
        return ["No register task matched -- sending the request unchanged."]
    lines = [
        "Matched task %s in section %s (%s), confidence %.2f."
        % (entry["id"], entry["cat"], entry["cname"], score),
    ]
    over = output_override(query)
    if over and over != entry["out"]:
        lines.append("You asked for %s %s, so that overrides the task's usual %s output."
                     % (_indefinite_article(over), over, entry["out"]))
    lines.append("Deliverable: %s." % expected_output(entry, query))
    if filled:
        lines.append("Assumed, because you did not specify: "
                     + "; ".join("%s = %s" % (k, v) for k, v in sorted(filled.items())) + ".")
    for p in plan or []:
        if p["accepted"]:
            lines.append("Attachment %s will be read as %s." % (p["name"], p["kind"]))
        else:
            lines.append("Attachment %s is not a file type this task uses -- "
                         "it will be passed as plain text." % p["name"])
    if entry.get("tools"):
        lines.append("Tool order suggested to the model: %s." % ", ".join(entry["tools"]))
    return lines


def slot_context_from_map(map_context):
    """Slot values QGIS can answer without asking the user.

    The register's slots are questions; some of them the host already knows
    the answer to, and asking anyway is the difference between a plugin that
    helps and one that interrogates. Only facts that are actually true of the
    open project are returned -- nothing is invented to suppress a question.

    Today that is the area of interest: if the project has layers, there is an
    extent and an active layer, and 'the area you are looking at' is a real
    answer to "which area?". It is still stated back to the user in the prompt
    preview, so a wrong assumption is visible before anything is sent.
    """
    ctx = {}
    if not isinstance(map_context, dict):
        return ctx
    layers = map_context.get("layers") or []
    if layers:
        active = map_context.get("active_layer")
        # map_context reports the string "None" when nothing is active.
        if active and active != "None":
            ctx["aoi"] = "the current canvas extent (active layer: %s)" % active
        else:
            ctx["aoi"] = "the current canvas extent"
    return ctx
