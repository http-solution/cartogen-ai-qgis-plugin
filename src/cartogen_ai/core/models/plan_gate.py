# -*- coding: utf-8 -*-
"""
Turn-scoped plan-validation gate for high-risk tool calls.

IMPLEMENTATION_TRACKER.md §1.6, option (b), decided by Alaa 2026-09-24: the narrow experiment
over the full deterministic plan-then-validate-then-execute pipeline (option (c)) point 27 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md describes. Gates only tool calls already
classified DELETE or PUBLISH in tool_operations.py's operation taxonomy -- routine reads/creates
see zero added friction, per the tracker's own stated tradeoff (a gate on every request adds
latency to trivial calls too).

Deliberately reuses the EXISTING `create_plan` tool (task_tools.py, already freeform, already
used for UI progress display) as "the plan," rather than inventing a new typed step schema
(`task`/`aoi`/`inputs`/`workflow:`/`outputs:`) the way the full point-27 proposal describes. That
schema would need live-LLM validation this sandbox cannot run -- "needs to be something the LLM
can reliably and consistently populate... this sandbox has no live LLM to validate that against
real queries" (tracker's own words). Reusing `create_plan` sidesteps that exact blocker: nothing
new for the model to learn to populate correctly, since it already calls this tool today.

Feature-flagged OFF by default (SETTINGS_PLAN_VALIDATION_GATE_ENABLED in settings_keys.py) --
this is a real, working, testable feature, not a silent behavior change forced onto every
installation. Per the tracker's decision record: "Build it, evaluate later" -- the live-LLM
evaluation of whether this actually helps (vs. just adding friction) is explicitly a separate,
not-yet-done follow-up, same as every other item in this taxonomy that needs a live LLM this
sandbox doesn't have.
"""

from ..agent.tool_operations import TOOL_OPERATION_TYPES, DELETE, PUBLISH

_GATED_OPERATION_TYPES = frozenset({DELETE, PUBLISH})


class PlanValidationGate:
    """One instance per CartogenAi session. reset() at the start of every run() call --
    same turn-scoped lifecycle as TurnTransactionLog (see models/transactions.py), so a plan
    made in a previous turn never silently satisfies this turn's gate check."""

    def __init__(self):
        self._plan_created_this_turn = False

    def reset(self):
        self._plan_created_this_turn = False

    def mark_plan_created(self):
        self._plan_created_this_turn = True

    def has_plan(self) -> bool:
        return self._plan_created_this_turn

    @staticmethod
    def requires_plan(tool_name: str) -> bool:
        """True only for tools this session's operation taxonomy classifies DELETE or
        PUBLISH -- an unclassified/unknown tool name is treated as NOT requiring a plan
        (fails open, not closed: a tool this taxonomy doesn't know about yet should not
        silently become ungated blocked, since test_tool_operations.py already guarantees
        every registered tool has an entry here in the first place)."""
        return TOOL_OPERATION_TYPES.get(tool_name) in _GATED_OPERATION_TYPES

    def check(self, tool_name: str, enabled: bool):
        """Returns a PLAN_REQUIRED dict if this call should be blocked pending a plan, or
        None if the call may proceed. Mirrors the existing PREVIEW_REQUIRED confirmation-gate
        response shape (SECURITY.md §5) so callers/UI code have one familiar pattern to
        handle, not two unrelated ones."""
        if not enabled or not self.requires_plan(tool_name) or self._plan_created_this_turn:
            return None
        op_type = TOOL_OPERATION_TYPES.get(tool_name)
        return {
            "status": "PLAN_REQUIRED",
            "requires_plan": True,
            "tool_name": tool_name,
            "operation_type": op_type,
            "message": (
                f"'{tool_name}' is a {op_type} operation. This session has plan-validation "
                "enabled (IMPLEMENTATION_TRACKER.md §1.6, option (b)): call create_plan first "
                f"to state what you're about to do and why, THEN call '{tool_name}' again. "
                "This is a one-time step for this turn, not needed before every individual "
                "call -- once create_plan has been called once, every other DELETE/PUBLISH "
                "call this turn proceeds normally."
            ),
        }
