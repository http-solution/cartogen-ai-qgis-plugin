# PLAN-052: A project status dashboard that can be refreshed from the repository

Status: in progress

## Goal
The owner asked for a page to visit that shows the project's status and stays updated. The page is a private Claude Artifact (a Dashboard). This plan keeps what feeds it in the repository, so any session can rebuild its data and a scheduled task can do it daily.

## Scope
- `tools/dashboard_snapshot.py` builds five data files from the repository (version, tool count, ledger, plans, master task list, activity, two hand-kept files).
- `docs/dashboard_data/hand_tests.json` and `defects.json`: the hand-kept inputs.
- `docs/DASHBOARD.md`: what feeds the dashboard, the refresh steps, the limits.
- Out of scope: any change to the plugin; a live data source (the page shows files, not queries); putting the artifact's link in this public repository.

## Acceptance
- `tests/test_dashboard_snapshot.py` passes: the generator runs against this repository, every file has the columns the page reads, the ledger classes add up, and the "verified by hand" rule does not count entries that say "not run" or "not hand-tested".
- The dashboard shows the generator's output after a refresh, and a scheduled task refreshes it daily.

## Guard tests
`tests/test_dashboard_snapshot.py`.

## Rollback
Delete the tool, the two data files, the doc and this plan; the dashboard keeps showing its last data.

## Status log
- 2026-11-03: generator, hand-kept files, doc and tests written. A first version of the "verified by hand" rule overcounted (7, truth 3: it counted entries that said "not run" or "fix not hand-tested"); the rule is now conservative and a test pins the known cases. The dashboard published earlier the same day showed the wrong figure until its refresh from this generator. Scheduled refresh: set up after this merges (see the task list).
