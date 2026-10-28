# PLAN-027: fixes from the 1.18.4 live smoke run

Status: in progress

## Goal
The 1.18.4 agent-edition smoke run (2026-10-27/28, QGIS 4.2.3, Gemini flash-latest, 66 rows: 44 PASS, 19 FAIL, 1 SKIP, 2 UNVERIFIED) is read against the plugin's own per-request evidence folders (steps.jsonl). Every failure that the evidence traces to plugin code is fixed with a regression test; the rest is named with what is missing.

## Scope
In (traced to code by the evidence):
1. GDACS (N7c, A7): `agent_orchestrator.py` called `fetch_gdacs_disaster_alerts_network_phase` with bbox and alert level only, so the country filter that has existed since 2026-09-15 never ran in the live path: a "Yemen" request returned 86 alerts from around the world. The country is now passed. Guard: a test that reads the orchestrator and fails when any `*_network_phase` call omits a parameter the function declares.
2. D6: the model wrote a Windows path with single backslashes; JSON turned `\f` and `\b` into control characters and the change-detection tool looked for "C:\...ixturesefore_fixture.asc". `arg_repair.py` restores the backslash letters in drive paths before a tool runs.
3. N7c: `update_task` with a null id answered "Task ID 'None' not found"; it now updates the one open task, or says there is no plan, or asks for the id.
4. A5, A6, A13: the model had a point for "Aden" and no area, then asked the user for a bounding box or searched for boundary layers. `geocode_and_enrich` (and `geocode_batch`) now return the place's bounding box in both orders.
5. DEF-9: the evidence collector's log capture was empty on every row; `tools/collect_evidence.py` now copies the plugin's evidence folders written since the previous snap and lists the tools called. Whether the explicit signal overload fixes the empty log is not verified.
Checked and NOT defects:
- N4, N6: the 1.18.4 degrees guard fired on the direct call (N6: "5000 degrees is about 555,000 km"); the model then reprojected to UTM and worked in metres, which is correct. The runbook expectation (refuse and stop) was wrong.
- D7, S1: `damage_score` is normalised 0 to 1 since 1.18.4; the runbook still expected mean change 70 and 45.
- C6: the demand points lie about 5 km from the nearest road, beyond the default 2,000 m snap; the model retried with a larger `max_snap_m` and succeeded. Fixture design, not a tool fault.
Open, needs more than the evidence holds:
- B8: the model typed key figures (120,000 / 85,000 / 45,000) into `create_print_layout` after reading only field names, never values. Proposal for the owner: key figures taken from a layer field by the tool (`key_figures_from`), so a typed number is flagged unverified. Not built.
- B7 worker crash, C5 loop and 1,028 vs 994 variance, E2 severity not computed, A11 and C8 wording: the folders matched to those rows hold the wrong or truncated requests.

## Acceptance
1. Offline suite, ruff and `tools/ledger_guard.py` pass; CI live passes.
2. Hand (owner): rerun N7c and A7 (GDACS for Yemen returns only Yemen alerts or says none), D6 with a single-backslash path, A13 and A5 ("Aden" resolves to an area).

## Guard tests
tests/test_orchestrator_passes_all_arguments.py::TestNetworkPhaseCalls::test_every_network_phase_call_passes_every_declared_argument
tests/test_arg_repair.py::TestRepairWindowsPath::test_form_feed_and_backspace_are_turned_back_into_backslash_letters
tests/test_task_manager.py::TestUpdateTaskWithoutAnId::test_no_plan_gives_a_plain_message_not_none
tests/test_geocode_bbox.py::TestNominatimBbox::test_boundingbox_is_reordered_for_both_conventions

## Rollback
Each fix is its own hunk; revert the commit. Released fixes ship as 1.18.5.

## Status log
- 2026-10-28: owner returned the 1.18.4 results and the evidence folders. Fixes 1 to 5 written with offline tests (the orchestrator guard was shown to fail without fix 1). Not hand-verified.
- 2026-10-28: PR merged; version 1.18.5 prepared and published. Not hand-verified.
