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


def unbacked_data_warning(final_text, pending_tools, unresolved_errors):
    """A warning string, or None. Flags a final answer that contains a data table while a tool
    call this turn is still pending (waiting for the user) or ended in an unresolved error --
    i.e. the table cannot have come from that call."""
    pending = _unique(pending_tools)
    failed = _unique(unresolved_errors)
    if not pending and not failed:
        return None
    if count_table_rows(final_text) < MIN_TABLE_ROWS_TO_FLAG:
        return None
    parts = []
    if pending:
        names = ", ".join(f"`{n}`" for n in pending)
        parts.append(f"{names} has not run (it is waiting for your confirmation or was blocked)")
    if failed:
        names = ", ".join(f"`{n}`" for n in failed)
        parts.append(f"{names} failed")
    return (
        f"⚠️ **{_WARNING_MARKER} for the table above.** " + "; ".join(parts) + ". "
        "The table was not produced by a tool and must not be relied on."
    )


def apply_unbacked_data_warning(final_text, pending_tools, unresolved_errors):
    """`final_text` with the warning appended (once), or unchanged."""
    if final_text and _WARNING_MARKER in final_text:
        return final_text
    warning = unbacked_data_warning(final_text, pending_tools, unresolved_errors)
    if not warning:
        return final_text
    return f"{final_text.rstrip()}\n\n{warning}"
