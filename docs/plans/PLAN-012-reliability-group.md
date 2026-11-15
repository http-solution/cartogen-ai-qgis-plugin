# PLAN-012: reliability group from the architecture audit

Status: done

## Goal
Act on the reliability findings of the external audit, but only on those the code supports. Each claim was checked against the source on 2026-10-24 (nothing run: there is no QGIS in this sandbox, so anything about runtime behaviour is marked as needing CI).

## Scope
**Confirmed in the code, to fix:**
1. **MultiPoint input to `obfuscate_sensitive_points`** (`vector_tools.py`, `pt = geom.asPoint()` in the main loop). The tool accepts any layer whose geometry type is point, which includes MultiPoint layers, but `QgsGeometry.asPoint()` is documented as for single points only and returns an empty point otherwise. Expected result: every point of a MultiPoint layer is jittered or snapped around (0, 0) and the tool reports success. That is a silent wrong-location result on a privacy tool. Not yet shown by a run: step one is a live test that proves or disproves it, then the fix (read the first vertex of each part, or reject multipart input with a clear message; one output feature per part, owner to choose, recommendation below).
2. **`generate_mapping_task_grid` `export_geojson_path="auto"`** (`task_grid_tools.py`): the file name is `{output_layer_name}.geojson` joined onto the temp folder with no sanitising. The name is model-supplied, so `../` or path separators write outside the temp folder, and a second run with the same name silently overwrites the first. Fix: reduce the name to a safe file stem and make it unique (the same helper the other exports use), no change to explicit paths.
3. **Temporary folders that are never removed** (`dem_tools.py` `cartogen_dem_*`, `corridor_tools.py` `cartogen_contours_*`, `export_tools.py` `cartogen_temporal_frames_*`). Each run leaves a folder in the system temp directory; the DEM one holds a GeoTIFF. The script sandbox already cleans its own folder. A layer loaded from such a folder, or a saved project that refers to it, would break if the folder were removed, so this needs a decision (below), not a blind sweep.

**Checked and not defects (withdrawn from the audit, reasons recorded so they are not re-raised):**
- *Python algorithms (gdal:, qgis:, script:) run on the GUI thread.* Deliberate and documented in `_background_processing.is_thread_safe_algorithm`: running `gdal:slope` in a worker segfaulted the QGIS 4.2.2 CI job in 2 of 4 runs (PR #249/#251); the GUI-thread path keeps the window painting and says Stop cannot reach it. Changing it would trade a known crash for a freeze. Left as is.
- *Abandoned Processing tasks are retained for ever.* Fixed earlier (rc20 audit A16): entries are released when the task reaches a terminal state (`release_finished_abandoned`).
- *`run_callable` leaves a worker thread after Stop.* True but harmless in practice: every caller (JIAF patterns, allocation, hub ranking, p-median, route ordering, imagery tracing) is pure computation whose result is discarded; none writes a file.
- *Nested event loops can re-enter the agent.* The send button is disabled while a request is in flight (`chat_tab_widget.py`), and the pump excludes user input events.
- *Multi-facility service area is missing in the Processing provider.* It exists (`processing/provider.py`: one run per facility, partial-output warning on cancel, multipart facilities reported as skipped).

**Needs evidence before any work (no defect shown):** feature-request optimisation and in-memory accumulation (the chunking helpers from the 2026-10-12 cost audit exist; the `network_analysis` log events already give start and duration per call, so timings from the next hand test decide what, if anything, to optimise); a single geometry-validity policy (a product decision, not a bug).

## Acceptance
1. Item 1: a live test with a MultiPoint layer fails on current main (to confirm the defect) and passes after the fix; if it passes on current main the item is withdrawn and recorded as such.
2. Item 2: tests show `../x`, an absolute path and a name with separators all end up as a plain file inside the temp folder, and a repeat run does not overwrite the first file.
3. Item 3 (decided: leave and say so): each of the three tools reports the folder it wrote to; nothing is deleted.
4. Ledger entries, `ruff check .` clean, nothing called hand-verified.

## Guard tests
To be listed per item when built.

## Rollback
One pull request per item; revert it.

## Status log
- 2026-10-24: plan written after reading `_background_processing.py`, `vector_tools.py`, `task_grid_tools.py`, `processing/provider.py` and the temp-folder users. No code changed. 
- 2026-10-24: owner decisions: item 1, one output point per part (same attributes), and only if the live test confirms the defect; item 3, leave the folders and say where they are in each tool's result (no deletion, no startup sweep). Item 3's acceptance test therefore becomes: each of the three tools names the folder it wrote to. Build starts on the owner's go.
- 2026-10-24: built (draft PR #397). Item 1 was reproduced in CI before any fix: on QGIS 4.2.2 `asPoint()` on a MultiPoint raises `TypeError: MultiPoint geometry cannot be converted to a point`. This CORRECTS the plan's guess of a silent (0, 0): the tool crashed rather than writing wrong locations, so the severity was lower than stated. Fixed: one output point per part, same attributes (`_geometry_points`). Item 2 fixed (`safe_file_stem`, `unique_path`). Item 3 done as decided (`temp_location_note`; the contour tool now also returns its `path`; nothing is deleted). Not hand-tested. The two evidence-first items (feature-request optimisation, geometry-validity policy) remain open.
