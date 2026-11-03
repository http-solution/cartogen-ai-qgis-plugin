# PLAN-055: The three gaps PLAN-051 left open on fetch tools

Status: planned

## Goal
PLAN-051 closed the two defects the first hand-test run found and recorded three gaps it did not close. This plan sizes each against the code (read 2026-11-03), says which are real, and proposes the smallest fix for each. Nothing here is built; building waits for the owner's go-ahead.

## Scope
Findings from reading the code (no QGIS, no run):

**Gap A - a confirmed fetch downloads on the UI thread. Real.**
`CartogenAi.execute_confirmed` (what the Apply button runs, on the main thread) calls `_real_execute_tool(..., user_confirmed=True)`, which calls the tool function directly. For the 15 `TWO_PHASE_TOOLS` that means the HTTP download runs on the main thread, which is what `_run_two_phase_tool` exists to avoid (QGIS froze about 43 s on a model download in an earlier hand test). Only reachable after a person confirms a card (a RESTRICTED-layer override), so rare, but when it happens QGIS freezes for the length of the download.
- Proposed fix (smallest): in `execute_confirmed`, for a name in `TWO_PHASE_TOOLS`, do not call the tool on the main thread. Run the existing background path with the person's override instead: `_run_two_phase_tool` on a worker thread, results back to the widget by signal. This changes the Apply handler from synchronous to asynchronous for these tools only, which is the real cost and the reason it needs the owner's decision.
- Alternative: leave as is and say so in the confirmation card ("QGIS may pause while this downloads"). No code risk, no fix.

**Gap B - the stray-fragment gate is not asked for fetch tools. Real, small.**
`_execute_two_phase_tool` asks the egress gate (PLAN-051) but not the stray-fragment check, which `_real_execute_tool` applies to CREATE/MODIFY/DELETE/PUBLISH tools. Thirteen of the 15 fetch tools are classified CREATE, so a pasted fragment ("template: access_map") can still make the model fetch and add layers. (`gemini_grounded_search` and `openai_grounded_search` are READ and unaffected by that gate.)
- Proposed fix: one small method `_stray_fragment_block(name, user_confirmed)` holding the existing check, called from both `_real_execute_tool` and `_execute_two_phase_tool`. Tests first: a stray-fragment turn plus a CREATE fetch tool returns the same `blocked` result; a READ tool and a human-confirmed call still run.

**Gap C - the plan gate for fetch tools. Not a gap.**
`PlanValidationGate.requires_plan` is true only for DELETE and PUBLISH tools. No fetch tool is either, so the gate would never block one. PLAN-051 listed this as open; it can be closed as "not applicable". A test pinning that no `TWO_PHASE_TOOLS` member is DELETE or PUBLISH would keep it true if a tool is ever reclassified.

**Gap D - "the MCP server freezes QGIS" claim. Unchecked, narrower than recorded.**
No `TWO_PHASE_TOOLS` member is in the MCP read or write allowlists (checked with the allowlists loaded), so no fetch tool is reachable over MCP and Gap A cannot occur there. The remaining question is whether any allowed MCP tool can run long on the main thread (`mcp_server.py` runs every tool there by design). That needs a look at the allowlisted tools for network or large-data work, then either a documented bound or a timeout. It is a read-only review first; no change until it finds something.

Out of scope: D1 to D4 (merged), the hand rerun of W11 and W1 (needs a person and a QGIS).

## Acceptance
- B: new offline test file, written first, failing before the fix; the existing stray-fragment tests still pass.
- C: one test pinning that no fetch tool needs a plan.
- A (if the owner chooses the fix): a live test that a confirmed fetch does not block the main thread, written without a QGIS install and honestly labelled "CI only"; a hand row added to the next bundle.
- D: a short written finding listing each allowed MCP tool that touches the network or large data, or "none".

## Guard tests
Extends ledger entry `gates-on-fetch-and-confirm-paths`.

## Rollback
Each gap is its own small change; revert it alone. B is a pure refactor plus one call; A touches only `execute_confirmed` and the Apply handler.

## Status log
- 2026-11-03: written from a read of `agent_orchestrator.py`, `plan_gate.py`, `mcp_policy.py` and `tool_operations.py`. Nothing run, nothing built. Recommended order: B and C (small, no behaviour a user will notice beyond a stray fragment being refused), then D (review), then A only if the owner wants the asynchronous Apply path.
