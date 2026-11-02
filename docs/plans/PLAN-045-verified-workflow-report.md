# PLAN-045: Verified workflow report (roadmap step D, master list RM-D)

Status: in progress

## Goal
One tool, `write_workflow_report`, writes a Markdown document for the layer(s) that hold a result: what was checked (failed checks first), where fetched data came from, the steps that made the result in order with their parameters (a rerun recipe), and the assumptions and limitations, including every gap the plugin found. Built only from what the plugin recorded, never from what the model remembers.

## Scope
In: `core/agent/workflow_report.py` (pure assembly); the result gate now keeps the checks of its last 10 runs on the layer (`cartogen/checks`); the tool in `provenance_tools.py`, classified PUBLISH (it writes a file); tool count 296 to 297 in the README and the reference.
Out (later): a Word/PDF version; a one-click rerun; the data-discovery ranking (RM-E); including the canvas picture; checks for the results of tools that bypass the gate (fetch tools, `run_steps` inner calls).

## Honest limits
- A layer with no recorded checks is listed as "none recorded" and in the limitations as not checked, never as passed.
- Only tools the gate covers store checks today (CREATE/MODIFY results that name a layer through the main-thread path).
- The steps are what was recorded; the report says rerunning them was NOT tested, so "the same numbers" is expected, not shown. The step-D acceptance in the roadmap audit ("reruns to the same numbers") is therefore not met and is not claimed.
- Licence text is the plugin's table (PLAN-044), not read from the providers; the report says so.
- Lineage parameters are what the model passed to the tool, cut at 200 characters each.

## Acceptance
1. A report for a two-step chain lists upstream layers first, steps in time order with inputs and parameters, sources with licence caveat, and the analyst's assumptions as given.
2. A failed check is printed before the table and counted in the tool result.
3. Gaps (no checks, unknown origin, layer missing, sampled checks) are each listed.
4. Cycles in lineage do not loop; a missing layer is an error, not an empty report.

## Guard tests
`tests/test_workflow_report.py` (offline), `tests/test_workflow_report_live.py` (CI only, written without QGIS).

## Rollback
Delete the tool and `workflow_report.py`; `record_checks` is harmless on its own.

## Status log
- 2026-11-02: built. Offline tests pass; live test has not run. Hand test not done: the worked example (service coverage) with a real project.
