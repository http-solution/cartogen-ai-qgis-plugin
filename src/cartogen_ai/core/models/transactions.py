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

- CartogenAi.run()'s tool-call loop (see agent_orchestrator.py) is the natural
  "transaction" boundary this point's "multi-step failure" language
  describes -- several tool calls answering one user request. A
  TurnTransactionLog instance is reset at the start of every run() call
  and records every tool call made during it.
- Reversibility is determined empirically, not from tool_operations.py's
  static labels: agent_orchestrator.py's _execute_tool wrapper snapshots the set of
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

v1.7.0, 2026-09-11: a priority subset of MODIFY/DELETE tools also now
undoable, via agent/tools/_snapshot_registry.py -- see that module's own
docstring for exactly which tools and why. agent_orchestrator.py's _execute_tool calls
the registered snapshot_fn (if any) for the tool being called BEFORE
dispatching it, and passes the result into record() below; record() uses
it in preference to the new-layer-id-diff mechanism when both a snapshot
and new layer ids happen to be present (in practice they never are, since
CREATE-classified tools that add layers aren't in the snapshot registry).

What this module still deliberately does NOT do -- the real, still-open
remainder of point 20's gap, left unaddressed rather than silently
declared closed:

- No rollback exists for load_project, or for any MODIFY tool not in
  _snapshot_registry.py's priority subset (advance_dataset_status, the
  four analysis_tools.py composite-index tools' optional output_field
  write, and any other in-place edit not explicitly listed there). Each
  would need its own snapshot strategy designed and verified the same way
  the priority subset's were -- a real, separate follow-up, not guessed at
  here.
- This is in-memory and per-agent-instance only. It does not survive a
  QGIS restart, and it is deliberately cleared at the start of every new
  run() call -- undo only ever reaches back into the CURRENT turn, never
  a previous one. Asking to undo something from an earlier message in
  the conversation returns "nothing to undo" rather than reaching back
  further than a user would expect.
"""

import threading


class TurnTransactionLog:
    """Records what happened during one CartogenAi.run() call. Each entry's own
    construction (reading layer ids from the live QgsProject) only ever happens from the
    dispatcher thread, same as every other piece of live QGIS state agent_orchestrator.py reads while
    building an entry -- but reset() is called directly from run() on the background
    QgsTask thread (not marshaled through the dispatcher), so a previous turn's still-
    in-flight record() (main thread, via a tool call not yet returned when a new turn
    starts) could race a new turn's reset() (background thread). Internally locked
    (2026-09-19) to close that narrow cross-turn window -- cheap (simple list ops under a
    lock held only for the duration of each method), and safe regardless of how narrow
    the actual race window turns out to be in practice."""

    def __init__(self):
        self._entries = []
        self._lock = threading.Lock()

    def reset(self):
        """Called at the start of every run() call -- undo must never reach
        back into a previous turn (see module docstring)."""
        with self._lock:
            self._entries = []

    def record(self, name, operation_type, result, layer_ids_before, layer_ids_after, snapshot=None):
        """Adds one entry for a completed tool call.

        layer_ids_before/layer_ids_after: the live QgsProject's layer id
        sets immediately before and after the call (empty sets when QGIS
        isn't available -- every new-layer id then comes back empty and
        nothing is ever offered as undoable, which is the correct
        no-QGIS behavior, not a bug).

        snapshot: the dict _snapshot_registry.py's snapshot_fn returned for
        this tool (taken by agent_orchestrator.py BEFORE dispatch), or None if the tool
        has no registered snapshot function or the snapshot_fn itself found
        nothing to snapshot (e.g. layer not found). Preferred over the
        new-layer-id-diff mechanism when both are present -- in practice
        they never both fire on the same call, since CREATE-classified
        tools that add layers aren't in the snapshot registry.
        """
        success = isinstance(result, dict) and bool(result.get("success"))
        error = result.get("error") if isinstance(result, dict) and "error" in result else None
        new_layer_ids = sorted(set(layer_ids_after) - set(layer_ids_before)) if success else []

        if success and snapshot is not None:
            undo = {**snapshot, "tool_name": name}
        elif new_layer_ids:
            undo = {"kind": "remove_layers", "layer_ids": new_layer_ids}
        else:
            undo = None

        entry = {
            "name": name,
            "operation_type": operation_type,
            "success": success,
            "error": error,
            "undo": undo,
            "undone": False,
        }
        with self._lock:
            # index assigned here, under the lock, rather than from a len() read taken
            # before acquiring it -- avoids a stale index if another record() call
            # interleaved between that earlier read and this append.
            entry["index"] = len(self._entries)
            self._entries.append(entry)
        return entry

    def summary(self):
        """Returns every entry recorded so far this turn, oldest first."""
        with self._lock:
            return list(self._entries)

    def last_undoable(self):
        """Returns the most recent not-yet-undone entry with an available
        undo, or None if nothing in this turn qualifies."""
        with self._lock:
            for entry in reversed(self._entries):
                if entry.get("undo") and not entry.get("undone"):
                    return entry
        return None

    def mark_undone(self, index):
        """Marks an entry's undo as applied, so a second undo_last_operation
        call doesn't try to remove already-removed layers."""
        with self._lock:
            for entry in self._entries:
                if entry["index"] == index:
                    entry["undone"] = True
                    return True
        return False
