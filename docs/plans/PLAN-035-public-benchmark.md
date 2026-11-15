# PLAN-035: a published, reproducible benchmark

Status: planned

## Goal
A number a visitor to the directory can check. A competitor quotes 43.8 out of 100 on a geospatial benchmark; this plugin has no figure, though it already has what a benchmark needs: invented fixtures around Aden with a stated expected answer for each row (`fixtures/README_FIXTURES.md` in the smoke package) and a 72-row runbook. The aim is a model-free scoring of what the plugin did, per provider, that anyone can rerun.

## Scope
In:
1. Turn the runbook rows that have an unambiguous expected result into machine-checkable cases: prompt, fixture files, the tool(s) that must be called, and the numeric or structural assertion on the result (for example "Khormaksar ranks first", "2 incidents within 500 m", "refuses 1000 degrees").
2. A runner that drives the plugin's agent loop headlessly (no QGIS GUI where possible, a QGIS docker image where not) against a provider and records the per-case result, tools called, tokens and cost. The plugin's evidence folders already hold the data.
3. A score definition written down before any run: cases passed, split into tool correctness and answer correctness, with the model-choice failures counted (they are the point), and a per-provider table.
4. A public page with the method, the fixtures, the results and the date and model versions of each run.
Out: scoring free-text quality with another model; comparing against other plugins' numbers (different tasks, not comparable); real-world data.
Relates to master list HT-3 (eval rows for model tool choice), which this extends.

## Acceptance
1. Offline: every case's assertion is exercised on a canned result (pass and fail).
2. A full run on one provider finishes unattended and writes a results file.
3. Two runs on the same provider and commit agree on every deterministic case; disagreements are listed as model variance, not hidden.
4. Hand (owner): the published number matches a spot check of five cases by hand.
Limits stated in the page: invented data, one region, the humanitarian slice of GIS; it measures this plugin, not GIS assistants in general.

## Guard tests
To be written: `tests/test_benchmark_cases.py`, `tests/test_benchmark_runner.py`.

## Rollback
Remove the page; nothing in the plugin depends on it.

## Status log
- 2026-10-28: plan written. Depends on the owner's choice of providers to run (cost). No code.
