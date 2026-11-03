# PLAN-055: The three gaps PLAN-051 left open on fetch tools

Status: done

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
- 2026-11-03: gaps B and C built, tests first (`tests/test_fetch_tools_stray_fragment.py`; the refusal and shared-method tests failed before the fix). The check now lives in `_stray_fragment_block`, called from `_real_execute_tool` and `_execute_two_phase_tool`; the fetch tools classified CREATE are refused on a fragment turn, the two READ grounded searches and a normal turn are untouched, a person's confirmation still runs. The plan gate is pinned as not applicable. Offline suite: only the 54 errors that also occur on a clean checkout here; ruff and mypy clean. Not run in a real QGIS and not hand-tested. Still planned: gap D (MCP review) and gap A (needs the owner's decision).
- 2026-11-03: gap D reviewed (read-only; code read, nothing run; no QGIS). Finding: the claim is **true in kind but not about fetch tools, and MCP is no worse than the chat agent**.
  - What is exposed: 24 READ tools and 26 WRITE tools (`mcp_policy.ALLOWED_TOOLS`, `WRITE_TOOLS`). None is a `TWO_PHASE_TOOLS` member and none is a downloader, so gap A cannot occur over MCP and no MCP call fetches from the network.
  - Where a call can run long: `mcp_server.run_allowed_tool` runs every tool on the QGIS main thread (by design, so tools never touch QGIS from the HTTP thread). The 26 write tools include the geoprocessing group (buffer, clip, dissolve, union, intersect, difference, spatial join, delaunay, voronoi and similar); 18 vector tools funnel through `vector_tools._run_and_add`, a single synchronous `processing.run`. On a large layer that blocks QGIS ("Not Responding") for the whole algorithm, with no Stop. The 2026-10-12 processing-cost audit ranks these tools at risk 4 for the same reason. The chat agent has the identical limit for these tools; MCP only adds that the caller is an outside program that cannot press Stop in the chat and waits on the HTTP request.
  - What limits the damage today: every write over MCP needs a person to approve that exact call in a dialog inside QGIS (default Deny, no "always allow"), and writes are off unless the person turned them on. The 24 READ tools return metadata and statistics; the ones that scan features (for example `field_statistics`) go through the sliced loop `_chunked.features`, which keeps QGIS responsive (checked for that one tool, not all 24).
  - Not found: any per-call time limit or input-size budget in `mcp_server.py` (no timeout, no `ensure_within`). That is the gap, and it is small.
  - Proposed, not built (owner's choice): (1) the approval dialog for a geoprocessing write states the feature count of its input layers, so the person sees the size before saying yes; (2) a stated work budget for MCP write calls using the existing `_chunked.ensure_within` wording; (3) leave as is and say in the MCP help that large layers can pause QGIS. None needs a hand test beyond the existing MCP rows; (1) is the cheapest and changes nothing for small layers.
  - Left unchecked: I did not read all 24 READ tools for feature scans; the review above covers the exposure and the write path, not a tool-by-tool timing. Gap D is closed as reviewed; the three options above are new open items for the owner.
- 2026-11-03: owner chose option 1 for gap D; built, tests first (`tests/test_mcp_approval_sizes.py`, 12 tests failed before; one live test added to `tests/test_mcp_server_live.py`, written without a QGIS install). The MCP approval dialog now lists the feature count of every vector layer named in the call's arguments (`mcp_policy.layer_name_candidates`, `approval_text(..., sizes=)`, `mcp_server.layer_sizes`, main thread, counts only) and, from 50,000 features, says QGIS may stop responding and cannot be stopped from the outside program. A failing lookup never stops the question being asked; read tools ask nobody. The 50,000 threshold is a judgement, not a measurement. Not run in a real QGIS; never seen by a person at the dialog.
- 2026-11-03: gap A closed the cheap way, by the owner's choice: the confirmation card for a download tool now says that QGIS may pause until the download finishes (`egress_gate.preview_required(..., downloads=)`, passed from `_egress_precheck` for every `TWO_PHASE_TOOLS` member; other cards unchanged). The Apply path still runs the download on the UI thread; moving it to a worker was not done. Tests first (`tests/test_fetch_confirm_card_warning.py`, 4 of 5 failed before). Offline only, not seen by a person. All four gaps of PLAN-055 are now closed or accepted: B and C built, D built (option 1), A warned.
