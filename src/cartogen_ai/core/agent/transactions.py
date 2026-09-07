# -*- coding: utf-8 -*-
"""
Turn-scoped operation log + best-effort undo for the tool calls the agent
makes while answering one user request.

Point 20 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md, the
half tool_operations.py doesn't close: "No snapshot/rollback mechanism
exists for partial multi-step failure -- that part of the original
finding stands, unaddressed, a real (if narrow) remaining gap."

What this module actually does, precisely, so it isn't mistaken for more
than it is:

- CartogenAi.run()'s tool-call loop (see agent.py) is the natural
  "transaction" boundary this point's "multi-step failure" language
  describes -- several tool calls answering one user request. A
  TurnTransactionLog instance is reset at the start of every run() call
  and records every tool call made during it.
- Reversibility is determined empirically, not from tool_operations.py's
  static labels: agent.py's _execute_tool wrapper snapshots the set of
  layer ids in the live QgsProject immediately before and after every
  call. If a call succeeds and the project has a layer id afterward that
  it didn't have before, that layer is offered as undoable (remove it).
  This is deliberately more trustworthy than trusting each tool's CREATE
  label alone -- it also correctly handles add_point_layer/
  add_incident_point's documented "create OR append to an existing layer"
  ambiguity for free: if the call appended to an already-existing layer
  instead of creating a new one, no new layer id appears, and the entry
  is correctly reported as not undoable.
- undo_last_operation (agent/tools/transaction_tools.py) removes the
  layer(s) a past CREATE call added, gated by the exact same
  confirmed=False -> PREVIEW_REQUIRED pattern remove_layer already uses
  (see vector_tools.remove_layer) -- it never removes anything without
  the same explicit confirmation any other destructive tool call needs.

What this module deliberately does NOT do -- the real, still-open part
of point 20's gap, left unaddressed rather than silently declared closed:

- No rollback exists for a MODIFY call: field_calculator, calculate_area/
  calculate_length, the four analysis_tools.py composite-index tools'
  optional output_field write, apply_*_style, run_query's subset filter,
  set_dataset_status/set_layer_sensitivity, and every other in-place edit
  are not undoable through this mechanism. Undoing those would need a
  real before/after snapshot of the specific field(s)/property touched on
  every single MODIFY call -- a much larger piece of engineering (one
  snapshot strategy per tool shape, not a generic diff) that is
  legitimately a separate, larger decision, the same shape as point 18's
  PLAN->EXECUTE->OBSERVE->VALIDATE->REPAIR loop or point 19's tiered
  allow-list question -- flagged here, not guessed at.
- No rollback exists for a DELETE call (remove_layer, load_project) --
  by the time either of those succeeds, the removed layer/prior project
  state is already gone from QGIS's own memory; recovering it would need
  a full project snapshot taken *before* every destructive call, not
  after, which this turn-scoped log does not attempt.
- This is in-memory and per-agent-instance only. It does not survive a
  QGIS restart, and it is deliberately cleared at the start of every new
  run() call -- undo only ever reaches back into the CURRENT turn, never
  a previous one. Asking to undo something from an earlier message in
  the conversation returns "nothing to undo" rather than reaching back
  further than a user would expect.
"""


class TurnTransactionLog:
    """Records what happened during one CartogenAi.run() call. Not
    thread-safe on its own -- agent.py only ever touches it from the
    dispatcher thread, same as every other piece of live QGIS state it
    reads while building an entry."""

    def __init__(self):
        self._entries = []

    def reset(self):
        """Called at the start of every run() call -- undo must never reach
        back into a previous turn (see module docstring)."""
        self._entries = []

    def record(self, name, operation_type, result, layer_ids_before, layer_ids_after):
        """Adds one entry for a completed tool call.

        layer_ids_before/layer_ids_after: the live QgsProject's layer id
        sets immediately before and after the call (empty sets when QGIS
        isn't available -- every new-layer id then comes back empty and
        nothing is ever offered as undoable, which is the correct
        no-QGIS behavior, not a bug).
        """
        success = isinstance(result, dict) and bool(result.get("success"))
        error = result.get("error") if isinstance(result, dict) and "error" in result else None
        new_layer_ids = sorted(set(layer_ids_after) - set(layer_ids_before)) if success else []

        entry = {
            "index": len(self._entries),
            "name": name,
            "operation_type": operation_type,
            "success": success,
            "error": error,
            "undo": {"kind": "remove_layers", "layer_ids": new_layer_ids} if new_layer_ids else None,
            "undone": False,
        }
        self._entries.append(entry)
        return entry

    def summary(self):
        """Returns every entry recorded so far this turn, oldest first."""
        return list(self._entries)

    def last_undoable(self):
        """Returns the most recent not-yet-undone entry with an available
        undo, or None if nothing in this turn qualifies."""
        for entry in reversed(self._entries):
            if entry.get("undo") and not entry.get("undone"):
                return entry
        return None

    def mark_undone(self, index):
        """Marks an entry's undo as applied, so a second undo_last_operation
        call doesn't try to remove already-removed layers."""
        for entry in self._entries:
            if entry["index"] == index:
                entry["undone"] = True
                return True
        return False
