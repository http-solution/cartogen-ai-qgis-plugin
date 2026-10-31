# PLAN-033: arguments must reach the tool (the drift class)

Status: planned

## Goal
Stop the class of bug where a tool offers an argument that never arrives. Three were found in two days: the GDACS `country` filter was dropped by the orchestrator's own call (1.18.5), `population_access_gap` had no way to name a speed field (PLAN-029 item 4), and `add_layer_from_path` drops `sublayer` on every live call (found while writing this plan, below).

## What was measured (2026-10-28, not assumed)
- Schema against function signature, all 296 tools: no schema property is missing from its function; two function parameters are deliberately not offered to the model (`source_label`, `model_path`). The registry layer is consistent.
- The risk is in the orchestrator's special-cased branches (16 `if name == ...` paths with their own two-phase calls). A scan of those branches found one more real drop: `add_layer_from_path` is handled in the orchestrator, which calls the function with the file path, layer name and source label but never `sublayer`, so "open the roads layer of this GeoPackage" always opens the first layer and appends a note. (Three other scan hits were false positives: a variable read earlier, and a separate handler.)
- Composite tools that call another tool can drop that tool's arguments the same way (the access-gap case). There is no check for this yet.

## Scope
In (first slice):
1. Fix `add_layer_from_path` to pass `sublayer` through, with a test.
2. Generalise the existing test (`tests/test_orchestrator_passes_all_arguments.py`, today limited to the `*_network_phase` calls) to every special-cased branch: each schema property of the tool must be read or forwarded in its branch, with an explicit allow-list for deliberate omissions.
3. A test for composite tools: every argument of a called tool that changes the answer (a speed or direction field, a unit, a threshold) is either forwarded or listed as intentionally fixed.
4. For new tools only: build the schema from the function signature and type hints, so a new argument cannot exist in one place only.
Out of this slice, separate plans when picked up: splitting the largest modules (`agent_orchestrator`, `analysis_tools`, `vector_tools`, `layout_tools`), burning down the broad-except baseline with a ratchet test, typed result dictionaries. These are style debts the analysis document is right to name; they do not cause wrong answers the way dropped arguments do, so they come second.

## Acceptance
1. Offline: the generalised drift test fails on a deliberately broken branch (shown once, as for the GDACS fix) and passes on `main`.
2. `add_layer_from_path` with `sublayer` opens that sublayer (CI live, with a two-layer GeoPackage).
3. No hand test needed for items 2 to 4; item 1 has one hand row (open a named layer from the smoke GeoPackage).

## Guard tests
To be written: `tests/test_orchestrator_passes_all_arguments.py` (extended), `tests/test_composite_tools_forward_arguments.py`, `tests/test_add_layer_sublayer_live.py`.

## Rollback
Each item is its own commit; revert it.

## Status log
- 2026-10-28: plan written after measuring the drift; item 1 recorded as master list DEF-20. No code in this PR.
- 2026-10-28: item 1 done (DEF-20): the orchestrator's `add_layer_from_path` branch now forwards `sublayer`. Test `tests/test_add_layer_sublayer_through_orchestrator.py` drives the real branch with the tool function replaced; it fails (both cases) with the fix removed and passes with it. The tool's own sublayer behaviour was already covered live. CI-only; no person has seen it. Items 2 to 4 not started.
- 2026-10-31: item 2 done: `tests/test_orchestrator_branches_forward_schema_arguments.py` reads the source of every TWO_PHASE_TOOLS branch (15 tools, no QGIS) and fails when a schema property is neither read from `filtered_args` nor forwarded wholesale; passes on main with an empty allow-list (no deliberate drops found). Mutation: removing the GDACS `country` read fails it. Limit, stated in the test: it checks that a branch reads each property, not that the read value reaches the final call, so a lambda that drops `sublayer` after the dict still reads it is not caught (that hop stays with the existing sublayer test). Items 3 (composite tools) and 4 (schema from signature) not started. Status stays 'planned' until they are.

