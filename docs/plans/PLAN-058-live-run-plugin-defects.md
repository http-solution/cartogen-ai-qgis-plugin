# PLAN-058: Fix the plugin defects the 2026-11-04 live run found

Status: in progress

## Goal
Four plugin faults seen in the 2026-11-04 agent live run (Windows 11, QGIS 4.2.3, Gemini; triage in `docs/HAND_TEST_RESULTS_full_smoke_2026-11-04.md`, record in `docs/LIVE_RESULTS.json`) are fixed, each with a test that fails first, so the live rows that found them can pass on a rerun. Issue 362 (animate) is among them. Master list rows DEF-23 to DEF-26.

## Scope
- DEF-23 (row V9): undoing a filled new column must be refused before any confirmation card, not after Apply.
- DEF-24 (row V4, issue 362): find why "animate the layer over time" did not call `export_temporal_animation_frames`, and fix the routing if the cause is the plugin's.
- DEF-25 (row A1): reproduce the empty Legend and blank map frame in the CI live job; decide plugin or script; fix the cause.
- DEF-26 (row B5): reproduce the 32-of-40 chat export; fix or record the cause as unconfirmed.
- Out of scope: any change to behaviour not listed; closing an issue (needs a live pass); the round-2 live run itself.

## Acceptance
- DEF-23: `tests/test_undo_add_field.py::TestTheUndoToolPassesTheReasonOn` (offline) and the live case in `tests/test_undo_add_field_live.py` (CI live): a filled column's undo preview returns the refusal and no confirmation card; an empty column still gets the card.
- DEF-24, DEF-25, DEF-26: written as each lands; each states whether the cause was confirmed.
- Live (by an agent or a person): rows V9, V4, A1, B5 of the full smoke package rerun in round 2. Until then every fix is CI only.

## Guard tests
Ledger entries `undo-add-field` and `chat-export-after-reopen` (existing); new entries are added for DEF-24 and DEF-25 if they change behaviour. See each status line.

## Rollback
Each fix is a separate pull request; revert that pull request. The undo precheck is one registry (`PRECHECK_REGISTRY` in `_snapshot_registry.py`) and one call in `_undo_via_snapshot`.

## Status log
- 2026-11-04: DEF-23 built. The cause: `_undo_via_snapshot` built the confirmation card before asking whether the undo could happen; the "field now holds values" refusal lived only in the restore that runs after Apply. Added `PRECHECK_REGISTRY` (add_field only) asked before the card. Offline tests fail on the old code (the card appears) and pass; a live test is added for CI. Not rerun in a live run.
