# PLAN-057: Measure progress by what a live run saw working, and stop changes breaking it

Status: in progress

## Goal
The owner's rule: a stable release or a big change is judged by the live smoke test, and a feature seen working live must stay working after later changes. Until now the dashboard counted "verified by hand" (3 of 151), which could not move because an agent run is not counted as a person. This plan replaces that measure with one that can be checked and cannot be inflated.

## Scope
- `docs/LIVE_RESULTS.json`: per ledger feature, what a live run saw (working / partly / failing), the rows, a note of what was seen, and the baseline commit of the run. A feature not listed has not been seen live. Written from the 2026-11-04 agent run (Windows 11, QGIS 4.2.3, Gemini); 85 entries: 68 working, 16 partly, 1 failing. The agent's evidence is not a person's: the note says so where it matters.
- `tools/live_results.py`: validates the record (every id is a ledger entry, every row a smoke row, nothing claimed for the 14 features a person cannot test, a note on each, an automated guard for each "working" feature) and prints the counts. `--gate` lists features seen working or partly whose source files changed since the run's baseline commit, and exits 1 if any has not been rechecked (`rechecked_at` = the commit it was rechecked on).
- `tools/dashboard_snapshot.py` adds the live counts (`live_*`) to the summary; the dashboard shows features seen working / failing and how many need a recheck, and drops the "verified by hand" bar.
- Release rule (stable release or big change): the live smoke package is run; no open plugin defect from it; `python tools/live_results.py --gate` lists nothing, or each listed feature's row has been rerun.
- Out of scope: running the rows (needs QGIS and a model); changing plugin behaviour.

## Acceptance
`tests/test_live_results.py` (10 tests): the committed record has no problems; counts add up; unknown ids, rows and statuses, a claimed untestable feature, a "working" feature with no guard and a missing note are each refused; the gate lists only working/partly features whose sources changed and releases a feature rechecked on the current head. `tests/test_dashboard_snapshot.py` pins the new summary columns.

## Guard tests
`tests/test_live_results.py`, `tests/test_dashboard_snapshot.py`; ledger entry `live-results-gate`.

## Rollback
Delete the three files; the dashboard falls back to the ledger counts.

## Status log
- 2026-11-04: built. First gate result: 6 features seen working or partly have changed sources since the run (the layout script and its footer features, the settings sections and Connections window, environment detection): all of them from the fixes made after the run, so their rows (A1, A2, W13) are the first round-2 rerun.
- Next: round-2 package of the failed and partial rows (`--only`), reproduce the A1 empty legend in the CI live job, fix V9 and V4, comment on issues 362, 380 and 510 (none can be closed on the evidence so far).
