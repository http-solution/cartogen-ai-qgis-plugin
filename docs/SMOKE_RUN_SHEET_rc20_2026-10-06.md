# rc20 live smoke test sheet (prepared 2026-10-06)

A blank sheet, not a result. rc20 adds the audit fixes and CI coverage made after rc19 (see the `v1.16.0-rc20` block in `metadata.txt`). **The rc19 sheet (`docs/SMOKE_RUN_SHEET_rc19_2026-10-06.md`) stays the master for rows A1-A12, and the rc18 sheet (`docs/SMOKE_RUN_SHEET_rc18_2026-10-06.md`) for rows V, T, J and P and the fixtures.** Install and gate steps are the same as rc18 section 0. Nothing in rc20 has been hand-tested; every row below is a question, not a known pass. If a prerequisite is missing write "not run: <reason>", never an inferred pass.

## D. New in rc20
| Id | Prompt / action | Expected | Result |
|---|---|---|---|
| D1 | With a PostGIS connection in the QGIS Browser: ask the agent for a read-only SQL query against it. Afterwards edit a table through the same connection in the DB Manager (an UPDATE or insert) | The query runs. The later write is **not** refused with "read-only transaction". (rc19 left the shared connection read-only.) | |
| D2 | A request with a DELETE or a function that writes (`SELECT nextval('some_sequence')`) over the same connection | Refused or blocked; the sequence does not advance | |
| D3 | Load a roads layer where one segment has an empty `oneway` and others hold F/B (the Yemen roads layer if available). Service area from a point beside a one-way street, then the same with the one-way field ignored | The two results differ; the one-way street is respected (#132) | |
| D4 | Two rasters on different grids (resolution or origin): ask for NDVI, or a weighted overlay, with `align_to_first` | The reply says the other raster was warped onto the first one's grid; your project rasters are unchanged (#153) | |
| D5 | `slope_analysis` on a DEM stored in feet: pass `dem_vertical_unit` "ft" | The result states the unit it used (#154) | |
| D6 | Estimate population exposure with a raster named like a density raster (`..._popden...`) and no unit given | Refused until you say people_per_km2 or people_per_cell (#160) | |
| D7 | Severity index on an admin layer where two districts share a name | Both get their own score; the reply says how many labels were changed (#159) | |
| D8 | Mark a layer SENSITIVE (Layer Data Sensitivity), buffer it, then **rename** the source layer. With a cloud provider and the egress gate on, ask the agent to summarise the buffer layer | Blocked until the card override; the reason names the renamed source (#150) | |
| D9 | Same setup: save a workflow preset and ask the agent to schedule it every 5 minutes | Needs the same override as running it (#149) | |
| D10 | Put a layer into edit mode and change one attribute but do not save. Ask the agent to run `estimate_road_speeds` on it (or add an incident point to the Incidents layer while it is in edit mode) | Your unsaved edit is still unsaved afterwards; the reply says the new values are not saved yet; undo (Ctrl+Z) removes the tool's step first, then your own edit (#143) | |
| D11 | Make a layer read-only (Layer Properties, Source, or a read-only file) and ask for `estimate_road_speeds` on it | A clear error; no "success" with a feature count (#144) | |
| D12 | Generate the same dashboard twice quickly (same title) | Two different files, not one overwritten (#158) | |
| D13 | Open a long request, then switch project (open another .qgz) while it is running | Nothing lands in the new project or its chat (#147) | |
| D14 | Print layout (standard) with a raster that lies off the map | The legend lists only layers that meet the map; right and top coordinate labels are not clipped by the legend frame (rc18 R7/N8) | |

## E. Carry-over
Run A1-A12 (rc19 sheet) and the V, T, J and P rows (rc18 sheet) on rc20; run the gates (fresh-profile install, upgrade from the previous zip, restart twice, uninstall and reinstall).

Known open, do not expect a pass: model-added plans and arrange steps (N3/N9), geography suggested from project memory in prose (N1), PostGIS connections that authenticate through a QGIS auth configuration (not tested in CI).
