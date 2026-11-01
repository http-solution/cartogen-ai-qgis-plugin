# PLAN-031: verified result gate (master list RM-A)

Status: in progress

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
- 2026-11-01: owner said "Go ahead with the roadmap order" (OWN-5, LEAD-1): step A of the roadmap audit starts. Slice 1, part 1 built: `core/validators/result_checks.py`, a pure module (no QGIS import) with six checks over a plain summary of the output layer (CRS in degrees for a distance result, invalid or empty geometries, a written field empty or constant, a value outside its unit's range, a field identical to its previous contents, an empty or wrong-sized output), `run_checks` and `summarize`. Acceptance 1 (a deliberately wrong input fails, a correct one passes) is met offline; acceptance 2 is met for three of the five defects (PLAN-026 classes A, B, C, as inputs the checks flag); the layout-figures defect (PLAN-028) and the ignored blocked network (PLAN-029 item 4) are not layer checks and stay open. NOT built yet: the adapter that reads a real layer into the summary, the dispatcher hook that adds `checks` and `checks_summary` to a tool result, the response-guard rule, the off switch, the live tests and the 50,000-feature timing. So no tool result carries checks and nothing is checked in a real run.
- 2026-11-01 (owner said go to the adapter and hook): built `core/agent/result_gate.py` (the adapter and the hook) and wired it into `_execute_tool`'s main-thread `command`, so it covers every ordinary tool, including run_steps inner calls; the network-only and two-phase tools (fetch_*) are NOT gated yet. A tool inherits the gate by being classified CREATE or MODIFY and returning a successful result with `layer_name`; a result that also names `output_field` gets that field checked (not empty, not one value everywhere). Each result gains `checks`, `checks_summary` and, on a failure, a `checks_note`; `response_guard.apply_failed_checks_note` appends a visible warning to the final reply when a failed check is not mentioned (`_guard_unbacked_data`). Off switch: QgsSettings `cartogen_ai/result_gate` = false. Bounded cost: at most 5,000 features are read per layer, and the summary says when it sampled. Deliberately NOT enabled for any tool: the CRS-in-degrees check (a tool that computes in a projected CRS and reprojects its output to EPSG:4326 would be falsely reported as computed in degrees) and the stale-field check (a rerun with the same inputs legitimately writes identical values); each needs a tool-by-tool decision from a real run. Acceptance status: 1 met (pure), 2 met for three of five defects, 3 (CI live: damage score, allocation and service-area results each carry checks) is NOT met: the live test covers the severity-index result and synthetic layers, and the damage, allocation and service-area tools do not all return `layer_name` yet, 4 met offline, 5 needs a person. The 50,000-feature timing is printed by the live test (limit 10 s) and is to be copied here from the first CI run; the live tests were written without a QGIS install.
