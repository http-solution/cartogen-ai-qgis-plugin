# PLAN-051: The egress gate on fetch tools, and the result gate on confirmed calls

Status: in progress

## Goal
Close the two plugin defects the first real hand-test run found (2026-11-03; triage in `docs/HAND_TEST_RESULTS_1.18.5_2026-11-03.md`): D1 (row W11) a fetch over a RESTRICTED layer was not stopped by the egress gate; D2 (row W1) a call the person confirmed with the Apply button got no result checks and no Undo record.

## Scope
- D1: `_execute_two_phase_tool` now asks the egress gate before dispatch (new `_egress_precheck`, shared with `_real_execute_tool`, which behaves as before). The old body is `_run_two_phase_tool`. The check is marshalled to the main thread (it reads the project); a check that fails blocks; a warn decision is added to the result as `egress_warning`. The person's override comes through the confirm path.
- D2: new `CartogenAi.execute_confirmed(name, arguments)` is what the Apply button runs (`chat_tab_widget._resolve_pending_confirmation`). It captures the before-state, calls `_real_execute_tool(..., user_confirmed=True)`, attaches the source record for fetch tools, records the call for Undo, and applies the result gate. The after-steps cannot hide the tool's own result.
- Out of scope, recorded as known gaps: a confirmed fetch still downloads on the UI thread (the Apply path calls the tool directly); the stray-fragment and plan gates are still not asked for fetch tools; the provenance "QA" text (D3) and the result check recorded after `set_layer_sensitivity` (D4) are separate.

## Acceptance
- Offline: `tests/test_confirm_and_fetch_gates.py` (written first; 9 of 11 failed on the unfixed code) passes, along with the existing egress and result-gate tests.
- CI live: `tests/test_egress_flow_live.py::TestFetchToolStopsAtTheCardForAProtectedLayer`.
- By hand: rerun rows W11 (card appears, nothing is sent, no layer) and W1 (`cartogen/checks` on `smoke_admin` after Apply) with a build that has this change.

## Guard tests
Ledger entry `gates-on-fetch-and-confirm-paths`.

## Rollback
Revert the change to `agent_orchestrator.py` and `chat_tab_widget.py`; the Apply button then calls `_real_execute_tool` as before.

## Status log
- 2026-11-03: failing tests written first, fix made, offline suite green apart from the 54 errors that also occur on a clean checkout in this sandbox. Live test written without a QGIS install. Not re-run by hand. Changed behaviour a user can see: a fetch tool called with a protected layer now shows the confirmation card; a confirmed write now reports result checks and can be undone.
