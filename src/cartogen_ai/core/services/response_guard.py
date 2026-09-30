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


def unbacked_data_warning(final_text, pending_tools, unresolved_errors, data_tool_ran=True):
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
    elif not data_tool_ran and looks_like_retrieved_data(final_text):
        parts.append("no data tool ran in this turn, so the figures come from the model's memory or from earlier "
                     "in the conversation")
    else:
        return None
    return (
        f"⚠️ **{_WARNING_MARKER} for the data above.** " + "; ".join(parts) + ". "
        "It was not produced by a tool in this turn and must not be relied on."
    )


def apply_unbacked_data_warning(final_text, pending_tools, unresolved_errors, data_tool_ran=True):
    """`final_text` with ungrounded tables replaced by a notice and the warning appended (once), or unchanged."""
    if final_text and _WARNING_MARKER in final_text:
        return final_text
    warning = unbacked_data_warning(final_text, pending_tools, unresolved_errors, data_tool_ran)
    if not warning:
        return final_text
    return f"{strip_ungrounded_tables(final_text).rstrip()}\n\n{warning}"
