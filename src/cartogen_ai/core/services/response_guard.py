# -*- coding: utf-8 -*-
"""
Code-level defences against the assistant presenting invented tool output.

Found in the rc7 interactive smoke test (2026-09-30, finding F03): a read of a SENSITIVE layer
was correctly blocked by the cloud-data gate (the plan stayed at 0/1 done), yet the assistant
answered three times with a five-row table -- osm_ids, names and feature classes that do not
exist in the layer -- and "Retrieved Records: 5". The prompt rules alone do not stop that, so this
module adds two deterministic, QGIS-free backstops, in the same "cheap code-level safety net, not
a second agent" shape as agent_orchestrator.py's _reconcile_final_text_with_tool_log:

1. annotate_not_run(): a tool result that means "this call did NOT run" (PREVIEW_REQUIRED, waiting
   for the user's Confirm; EGRESS_BLOCKED) gets an explicit note for the model, so the fact is in
   the data it reasons over and not only in a rule it may not weigh.
2. apply_unbacked_data_warning(): if the turn ended with a call still pending or failed and the
   final answer nevertheless contains a data table, a visible warning is appended.

Both are pure functions so they can be unit-tested without QGIS or a model.
"""

import re

# Statuses meaning "the call did not run and is waiting on / blocked by the user".
NOT_RUN_STATUSES = frozenset({"PREVIEW_REQUIRED", "EGRESS_BLOCKED"})

NOT_RUN_NOTE = (
    "This call DID NOT RUN. It is waiting for the user's Confirm/Cancel in the app, or it was "
    "blocked. Do not state, summarize, estimate or invent what it would have returned -- no row "
    "values, counts, names or coordinates. Do not ask the user to type 'confirm' or 'yes' in "
    "chat: the app shows its own confirmation control. Say in one sentence what is pending, "
    "then stop."
)

_TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")

# A table this short is more likely a formatting aid than a claim of retrieved data.
MIN_TABLE_ROWS_TO_FLAG = 3

_WARNING_MARKER = "No data was retrieved"


def count_table_rows(text):
    """Number of markdown table rows (header and data, not the |---| separator) in `text`."""
    if not text:
        return 0
    return sum(
        1 for line in str(text).splitlines()
        if _TABLE_ROW.match(line) and not _TABLE_SEPARATOR.match(line)
    )


def annotate_not_run(result):
    """Returns `result` with an `assistant_note` when it means the call did not run; anything
    else is returned unchanged (and the input dict is never mutated)."""
    if isinstance(result, dict) and result.get("status") in NOT_RUN_STATUSES:
        annotated = dict(result)
        annotated["assistant_note"] = NOT_RUN_NOTE
        return annotated
    return result


def _unique(names):
    seen = []
    for name in names or []:
        if name and name not in seen:
            seen.append(name)
    return seen


# --- F03 widening (rc8 audit): records presented as data in a bulleted list or prose, and a turn in which
# NO data tool ran at all. A record-like line carries an identifier/count/coordinate (a run of 3+ digits or a
# decimal coordinate), a word (Latin or Arabic), and a separator; a pros/cons table or a how-to list has no such digits.
_LIST_ITEM = re.compile(r"^\s*(?:[-*\u2022]|\d{1,3}[.)])\s+(?P<body>.*\S)\s*$")
_BIG_NUMBER = re.compile(r"\d{3,}")
_COORD = re.compile(r"-?\d{1,3}\.\d{3,}")
_WORD = re.compile(r"[A-Za-z\u0600-\u06FF]{3,}")
_SEPARATOR = re.compile(r"[|:,;\u2014\u2013]|\s-\s")
_RETRIEVAL_CLAIM = re.compile(
    r"\b(?:retrieved|fetched|returned|found)\s+(?:records?|rows?|features?)\s*[:\-]?\s*\d+"
    r"|\b(?:records?|rows?)\s+(?:retrieved|returned)\s*[:\-]?\s*\d+", re.IGNORECASE)

MIN_RECORD_LINES_TO_FLAG = 3

# Bookkeeping calls that produce no data: a turn made only of these has nothing behind a data claim.
NO_DATA_TOOLS = frozenset({
    "create_plan", "set_task_preview", "update_task", "store_project_memory", "store_global_memory",
})

_SOFT_MARKER = "other calls succeeded"
_NOTICE_TABLE_REMOVED = "_(Table removed: no tool produced it in this turn.)_"


def _record_like(text):
    t = str(text)
    return bool((_BIG_NUMBER.search(t) or _COORD.search(t)) and _WORD.search(t) and _SEPARATOR.search(t))


def _is_table_row(line):
    return bool(_TABLE_ROW.match(line)) and not _TABLE_SEPARATOR.match(line)


def count_record_lines(text):
    """Number of record-like lines: data rows of a pipe table and bullet/numbered items."""
    if not text:
        return 0
    n = 0
    for line in str(text).splitlines():
        if _is_table_row(line):
            if _record_like(line):
                n += 1
            continue
        m = _LIST_ITEM.match(line)
        if m and _record_like(m.group("body")):
            n += 1
    return n


def claims_retrieval(text):
    return bool(text and _RETRIEVAL_CLAIM.search(str(text)))


def looks_like_retrieved_data(text):
    return count_record_lines(text) >= MIN_RECORD_LINES_TO_FLAG or (
        claims_retrieval(text) and count_record_lines(text) >= 1)


def strip_ungrounded_tables(text):
    """Replaces every pipe table whose data rows are record-like with a one-line notice. A table of
    something else (options, pros/cons) is left alone. Only called when nothing grounds the data."""
    if not text:
        return text
    lines = str(text).splitlines()
    out, i = [], 0
    while i < len(lines):
        if _TABLE_ROW.match(lines[i]):
            j = i
            while j < len(lines) and (_TABLE_ROW.match(lines[j]) or _TABLE_SEPARATOR.match(lines[j])):
                j += 1
            block = lines[i:j]
            data = [ln for ln in block if _is_table_row(ln)]
            if sum(1 for ln in data if _record_like(ln)) >= 2:
                out.append(_NOTICE_TABLE_REMOVED)
            else:
                out.extend(block)
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


# F14: a model-written "please confirm" next to the app's real confirmation card reads as a second,
# unbacked prompt (typing it goes to the model, not the gate). Lines that only ask for that are removed.
_CONFIRM_PROSE = re.compile(
    r"\b(?:please\s+)?(?:reply|respond|type|say|answer)\b[^.\n]{0,80}\b(?:confirm|proceed|yes|apply)\b"
    r"|\bplease\s+confirm\b|\bconfirm\s+(?:to\s+)?(?:proceed|continue|execute)\b"
    r"|\bpreview\s+ready\b|destructive\s+action\s+confirmation|\bawaiting\s+(?:your\s+)?confirmation\b",
    re.IGNORECASE)
_MAX_CONFIRM_LINE = 300
CONFIRM_CARD_NOTICE = "Waiting for your confirmation in the card above."


def strip_confirmation_prose(text):
    """Removes the model's own confirm-it-in-chat lines. Returns CONFIRM_CARD_NOTICE if nothing is left."""
    if not text:
        return text
    kept = [ln for ln in str(text).splitlines()
            if not (len(ln) <= _MAX_CONFIRM_LINE and _CONFIRM_PROSE.search(ln))]
    cleaned = "\n".join(kept).strip()
    if cleaned == str(text).strip():
        return text
    return cleaned or CONFIRM_CARD_NOTICE


def unbacked_data_warning(final_text, pending_tools, unresolved_errors, data_tool_ran=True, backed_by_success=False):
    """A warning string, or None.

    Flags a final answer that contains data (a table, or record-like bullets) while a tool call this
    turn is still pending (waiting for the user) or ended in an unresolved error -- i.e. the data cannot
    have come from that call -- or while no data tool ran at all this turn (`data_tool_ran` False)."""
    pending = _unique(pending_tools)
    failed = _unique(unresolved_errors)
    parts = []
    if pending or failed:
        if count_table_rows(final_text) < MIN_TABLE_ROWS_TO_FLAG and not looks_like_retrieved_data(final_text):
            return None
        if pending:
            names = ", ".join(f"`{n}`" for n in pending)
            parts.append(f"{names} has not run (it is waiting for your confirmation or was blocked)")
        if failed:
            names = ", ".join(f"`{n}`" for n in failed)
            parts.append(f"{names} failed")
        if failed and not pending and backed_by_success:
            # A data tool DID succeed this turn, so the table may well be its output. rc17 hand test B3: a STAC search succeeded and
            # three unrelated SQL calls failed, and the real scene table was replaced by "no tool produced it".
            return (f"⚠️ **Note:** {'; '.join(parts)} in this turn; {_SOFT_MARKER}. Check the data above against "
                    "the tool results, since it cannot be tied to a single call.")
    elif not data_tool_ran and looks_like_retrieved_data(final_text):
        parts.append("no data tool ran in this turn, so the figures come from the model's memory or from earlier "
                     "in the conversation")
    else:
        return None
    return (
        f"⚠️ **{_WARNING_MARKER} for the data above.** " + "; ".join(parts) + ". "
        "It was not produced by a tool in this turn and must not be relied on."
    )


def apply_unbacked_data_warning(final_text, pending_tools, unresolved_errors, data_tool_ran=True, backed_by_success=False):
    """`final_text` with ungrounded tables replaced by a notice and the warning appended (once), or unchanged.

    `backed_by_success`: a data tool succeeded this turn and nothing is pending. Failed calls then only add a note; the tables stay."""
    if final_text and (_WARNING_MARKER in final_text or _SOFT_MARKER in final_text):
        return final_text
    warning = unbacked_data_warning(final_text, pending_tools, unresolved_errors, data_tool_ran, backed_by_success)
    if not warning:
        return final_text
    if backed_by_success and not _unique(pending_tools):
        return f"{str(final_text).rstrip()}\n\n{warning}"
    return f"{strip_ungrounded_tables(final_text).rstrip()}\n\n{warning}"


# --- F03, second half (rc11 smoke test, GitHub #75): the narrative AROUND real numbers. The model answered with counts and
# percentages that came from tools, plus claims no tool returned: "Amran Governorate", "~29.0M national remainder", "rugged
# mountainous terrain ... unpaved valley tracks", a WorldPop file of "240 MB" (the real one was 481.70 MB). The table/record
# guard above cannot see those. This one checks three narrow kinds of claim against what the conversation actually contained
# (the user's words, the project summary and every tool result) and appends a visible footnote for the ones that are in none
# of it. It never rewrites the answer, and it is deliberately limited to claim shapes that are cheap to verify, because a
# loose check would flag every rounding and derived figure and train people to ignore the note.
_UNGROUNDED_MARKER = "Not from a tool result"
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# A lowercase "m" is metres ("886.49 m") and "b" is rarely a billion, so the one-letter suffixes count only as capitals ("29.8M").
# rc17 hand test R2 (2026-10-06): every metre distance in a hub-ranking answer was read as "886.49 million", matched no number
# in the evidence, and the whole table was footnoted as coming from the model's general knowledge.
_SCALED = re.compile(r"(?<![\w.])~?\s*(\d[\d,]*(?:\.\d+)?)\s*((?i:million|billion|bn)|[MB])\b(?![\w-])")
_SIZE = re.compile(r"(?<![\w.])~?\s*(\d[\d,]*(?:\.\d+)?)\s*(kb|mb|gb)\b", re.IGNORECASE)
# Only comma-grouped numbers (29,812,345): a bare 9-digit run is an identifier (an osm_id), not a total.
_BIG_PLAIN = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3}){2,})(?![\w.])")
_PLACE = re.compile(
    r"\b([A-Z][a-z]+(?:[ -][A-Z][a-z]+)?)\s+(Governorate|Province|District|Directorate|Sub-?district|Region|Valley|Mountains|Desert)\b")
_PLACE_STOPWORDS = frozenset({
    "the", "this", "that", "each", "every", "any", "all", "selected", "chosen", "same", "other", "another", "new", "old",
    "first", "second", "third", "last", "next", "which", "what", "your", "our", "its", "their", "per", "one", "both",
})
_TERRAIN = re.compile(
    r"\b(mountainous|rugged|hilly|steep|unpaved|paved|gravel|asphalt|desert|plateau|escarpment|rocky)\b", re.IGNORECASE)
_TERRAIN_TOOL_HINTS = ("slope", "elevation", "hillshade", "terrain", "dem")
_NUMBER_TOLERANCE = 0.01     # 1%: rounding ("29.8M" for 29,812,345) is not a fabrication
_MAX_EVIDENCE_NUMBERS = 400
_MAX_FLAGGED = 6


def _evidence_numbers(evidence):
    values = set()
    for m in _NUMBER.finditer(evidence or ""):
        try:
            v = float(m.group(0).replace(",", ""))
        except ValueError:
            continue
        if v > 0:
            values.add(v)
    return sorted(values, reverse=True)[:_MAX_EVIDENCE_NUMBERS]


def _near(a, b):
    return abs(a - b) <= _NUMBER_TOLERANCE * max(abs(a), abs(b))


def _number_grounded(candidates, numbers):
    """True when any candidate value equals an evidence number, or the sum / difference of two of them, within 1%."""
    for c in candidates:
        if any(_near(c, n) for n in numbers):
            return True
    top = numbers[:150]
    for i, a in enumerate(top):
        for b in top[i + 1:]:
            for c in candidates:
                if _near(c, a + b) or _near(c, a - b):
                    return True
    return False


def _to_float(text):
    return float(text.replace(",", ""))


def ungrounded_claims(final_text, evidence):
    """Short descriptions of claims in `final_text` that nothing in `evidence` supports. Pure.

    Three kinds: large or scaled numbers (a million or more, "29.8M") and file sizes ("240 MB") that match no number in the
    evidence (nor the sum/difference of two, within 1%); named administrative places ("Amran Governorate") whose name is not
    in the evidence; and terrain / road-surface descriptions ("rugged", "unpaved") when neither the evidence nor a terrain
    tool run mentions them. `evidence` is the plain text of the user's messages, the project summary and the tool results."""
    if not final_text:
        return []
    text = str(final_text)
    low_evidence = (evidence or "").lower()
    numbers = _evidence_numbers(evidence)
    found = []

    def add(label):
        if label not in found:
            found.append(label)

    scaled_spans = []
    for m in _SCALED.finditer(text):
        scale = {"million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9}[m.group(2).lower()]
        value = _to_float(m.group(1)) * scale
        scaled_spans.append(m.span())
        if value >= 1e6 and not _number_grounded([value], numbers):
            add(m.group(0).strip().lstrip("~").strip())
    for m in _SIZE.finditer(text):
        unit = {"kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}[m.group(2).lower()]
        decimal_unit = {"kb": 1e3, "mb": 1e6, "gb": 1e9}[m.group(2).lower()]
        x = _to_float(m.group(1))
        if not _number_grounded([x, x * unit, x * decimal_unit], numbers):
            add(m.group(0).strip().lstrip("~").strip())
    for m in _BIG_PLAIN.finditer(text):
        if any(s <= m.start() < e for s, e in scaled_spans):
            continue
        if not _number_grounded([_to_float(m.group(1))], numbers):
            add(m.group(1))
    for m in _PLACE.finditer(text):
        words = m.group(1).split()
        if words[0].lower() in _PLACE_STOPWORDS:
            continue
        if not any(re.search(r"\b" + re.escape(w.lower()) + r"\b", low_evidence) for w in re.split(r"[ -]", m.group(1))):
            add(m.group(0))
    terrain_tool_ran = any(h in low_evidence for h in _TERRAIN_TOOL_HINTS)
    for m in _TERRAIN.finditer(text):
        word = m.group(1).lower()
        if terrain_tool_ran or re.search(r"\b" + re.escape(word) + r"\b", low_evidence):
            continue
        add(f"\"{word}\"")
    return found[:_MAX_FLAGGED]


def apply_ungrounded_claims_note(final_text, evidence, data_tool_ran=True):
    """`final_text` with a one-paragraph footnote naming claims the conversation's data does not support, or unchanged.

    Only after a data tool ran this turn -- that is when a reader assumes every line came from their own data. A purely
    conceptual answer ("how does a service area work?") is general knowledge by nature and is left alone."""
    if not final_text or not data_tool_ran or _UNGROUNDED_MARKER in str(final_text):
        return final_text
    claims = ungrounded_claims(final_text, evidence)
    if not claims:
        return final_text
    listed = "; ".join(claims)
    return (f"{str(final_text).rstrip()}\n\nℹ️ **{_UNGROUNDED_MARKER} in this conversation:** {listed}. "
            "These come from the model's general knowledge, not from your data or a tool run here; verify them before relying on them.")
