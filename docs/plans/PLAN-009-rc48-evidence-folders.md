# PLAN-009: act on the rc48 evidence folders

Status: in progress

## Goal
The owner supplied the rc48 evidence folders (they were in the rc48 bundle all along; PLAN-008 wrongly said they were missing). Check each PLAN-008 conclusion against them, fix what the evidence shows, and say plainly where it does not support an earlier claim.

## What the evidence showed, row by row
- **OI-148** (`20261023-201442_t3`): PLAN-008 was incomplete. The reply came from `classify_facilities_by_access` (default snap 500 m: both facilities "within"; model-chosen snap 50 m: both "beyond"), which ignores the road-to-facility leg. Fixed: for a distance budget and up to 200 facilities it now routes each one and decides by road cost + leg (370 m Inside_the_U beyond, 280 m Beside_the_arm within, whatever the snap).
- **OI-150** (`20261024-001545_t105`, `..._t106`): PLAN-008's root cause (a caller-named output counted as an input) is a real bug in the generic Processing route but is NOT what happened here: the real `merge_layers` call named no output, and the gate did not even block the merge of `smoke_points` itself. A faithful reproduction (real gpkg layers, real agent, real dispatch path, gate = Block, `smoke_points` SENSITIVE) passes on current main AND on the rc48 code (run in CI through a throwaway pull request based on the rc48 commit): merge gated, lineage recorded, both renames and later reads blocked. So the rc48 observation is not explained by the code; the gate worked for other reads in the same session (t7, t30, t36, t132 to t135). Unresolved, most likely session state (the gate setting or `smoke_points`' tag at that moment). Added `context.json` to every evidence folder (gate mode, strictness, provider endpoint, each layer's sensitivity, lineage count and renderer) so the next run settles it.
- **OI-128** (`20261023-204053_t3`): the reply said `population_ramp`; the saved project ends with `yem_ppp_2020` as plain grey. A faithful reproduction (vector layers above the raster, the move under the vectors, a canvas render, a save and reload) passes on current main and on the rc48 code: the ramp is warm on the canvas and survives the reload. Not explained by the code; same `context.json` remedy (it records each raster's renderer type).
- **OI-120** (`20261023-204448_t4`): "apply ran without waiting" was real and is fixed by PLAN-008 (apply now asks). The missed duplicate is not explained by the folder (it does not record the two source strings). The duplicate test now normalises the data source (path separators, drive-letter case, `|geometrytype=`), and the report lists same-name layers that were NOT matched, with their sources.
- **OI-145/146** (`20261023-213054_t33`, `..._t35`): the script that made `script_points` ran fine on its second attempt; its first attempt used `import os`, which is blocked by design. The file-layer edit (t35) returned `success: true` with the "NOT applied" text only in a side field, so the answer showed the edit as done. Fixed: a script whose changes were all not applied is now a failure that says so; a partly applied one carries `partially_applied`. A blocked import now says what scripts can do instead.
- **#84**: the dashboard file now carries the "needs an internet connection" note.
- **#95**: the code default is already OFF everywhere it is read. The "ON" was a saved setting in that QGIS profile. The Memory dialog's ON line now says so and names the setting that turns it off.
- **#127**: an ADM2 layer (about 330 districts) was skipped by the always-on label rule; such a layer now gets labels that appear when zoomed in to 1:1,000,000 or closer.
- **#129**: after "Zoom Full" the layout's main frame followed the DEM; when the canvas shows the whole project and the visible vector layers fill under half of it, the frame now follows the vector layers (a zoomed-in canvas is still followed).

## Guard tests
`tests/test_classify_routed_total.py`, `tests/test_ubend_access_live.py` (classify), `tests/test_evidence_repro_live.py`, `tests/test_evidence_context.py`, `tests/test_script_reply.py`, `tests/test_project_tidy_extra.py`, `tests/test_layout_extent_pick.py`, `tests/test_zoom_labels_live.py`, `tests/test_export_csv_helpers.py` (internet note).

## Rollback
One pull request; revert it.

## Status log
- 2026-10-24: evidence read, fixes above built and CI-checked (live results recorded in the pull request). Nothing is hand-verified; OI-128 and OI-150 are the two findings the code does not explain and stay open for a re-run with `context.json`.
