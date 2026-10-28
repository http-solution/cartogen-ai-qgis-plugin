# PLAN-031: verified result gate (master list RM-A)

Status: planned

## Goal
After an analysis that writes a layer or a field, the plugin checks the result itself and puts the outcome in the tool result, so a wrong answer is reported as wrong even when the model would have accepted it. Three classes of silent wrong answer were found by hand runs and not by the model (PLAN-026): degrees treated as metres (class A), a signed value ranked as worse (class B), stale state read as a result (class C). The 1.18.4 run added two more: figures typed into a layout that were not in the data (PLAN-028) and a blocked road network that was silently ignored (PLAN-029 item 4). Each was fixed one at a time; this makes the check general.

## Scope
In (first slice):
1. A pure module of checks over a written layer or field, each returning `{id, status: pass|warn|fail, detail}`:
   - CRS: a distance, buffer or area result on a geographic layer without a stated projection;
   - geometry: share of invalid or empty geometries in the output;
   - field not all null, and not a single constant value (a score that is the same everywhere);
   - value range for the stated unit (percent 0 to 100, fraction 0 to 1, counts not negative, travel hours not above a plausible bound);
   - no stale field: a field the run claims to have written is not byte-identical to its previous contents;
   - feature count: output not empty and, for a one-to-one tool, equal to input.
2. A hook in the dispatcher for tools that `tool_operations.py` already classifies as creating or modifying a layer or field, so a new tool inherits the gate by being classified.
3. The result gains `checks` and `checks_summary`; `response_guard.py` flags a reply that omits a failed check.
Out: repairing results automatically; new geoprocessing; checks that need a second model call; the later slices (licence capture RM-C, workflow report RM-D).

## Acceptance
1. Offline: each check, given a deliberately wrong input, returns `fail`; given a correct input, `pass`.
2. The five historical defects above are reproduced as tests that the gate flags (not only the fix that removed them).
3. CI live: the damage score, the allocation tool and a service-area result each carry `checks` in a real QGIS run.
4. A reply that leaves out a failed check is flagged by the response guard (offline).
5. Hand (owner): a request whose correct answer is known (the smoke fixtures) reports its failed check in plain words.
Checks add time: the cost on a 50,000-feature layer is measured and capped in the plan's status log before merge.

## Guard tests
To be written with the first code line, named here when they exist: `tests/test_result_checks.py` (pure checks), `tests/test_result_gate_live.py` (hook on three real tools), `tests/test_response_guard.py::TestFailedCheckIsQuoted`.

## Rollback
A setting turns the gate off (tools then return no `checks`, as today). Revert the commit for a full rollback.

## Status log
- 2026-10-28: plan written (master list RM-A, LEAD-1 decides the order). No code.
