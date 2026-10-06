# Open issues: what the code does today (2026-10-06, after rc19)

Supersedes the "Still open inside it" column of `docs/ISSUE_VERIFICATION_CHECKLIST_2026-10-05.md` (that file is a dated snapshot and is not edited). "In code" means a change exists and its tests pass offline; "CI" means the QGIS 4.2.2 live job covers it; **nothing here is hand-verified**, and no issue is closed by this document. Closing is the owner's call after a hand pass.

## The parts that were still open after the rc12-rc14 work packages
| Issue | What was still open | What is in the code now | Covered by |
|---|---|---|---|
| #153 raster arithmetic grid | Only refusal; no alignment | `align_to_first` + `resampling` on NDVI, NDWI, NDRE, weighted overlay and change detection warp the other rasters onto the first raster's grid into temporary files (project layers untouched) and say so in the result | `test_raster_alignment_live` (CI) |
| #154 vertical unit | DEM vertical unit assumed metres | `dem_vertical_unit` ('m', 'ft', 'us_ft') on `elevation_profile`, `slope_analysis`, `build_composite_impedance_field`; a raster carries no unit, so it is an argument and the result states it | `test_vertical_unit` (offline) |
| #159 display names collapse features | Score writes in analysis_tools | Severity, presence-gap, population-in-need and damage-exposure tools label units uniquely (`name [#id]`, `feature <id>`), write each score to its own feature, and say how many labels were changed. Presence matching by name: a same-named unit is reported unmatched, not silently merged | `test_unit_labels` (offline) |
| #160 zonal tools / raster units | Raster-unit validation | `estimate_population_exposure(raster_unit=...)`: a layer named like a density raster is refused until `people_per_km2` or `people_per_cell` is stated; density cells are multiplied by their area | `test_population_unit` (offline); the area maths is not live-tested |
| #161 boundary points / CRS | Points not moved into the admin CRS | Footprint centroids and incident points are transformed into the admin/zone CRS before assignment | `test_point_assignment_crs_live` (CI) |
| #166 wheel | Never built | Built and installed into a clean venv on 2026-10-06: task register and both contracts load. `pyproject.toml` said rc12; now matches `metadata.txt`, enforced by a test, and declares `requests` | `test_packaging_metadata`; wheel by hand |
| #167 lifecycle | Running-task invalidation at unload | `plugin_epoch` retired in `unload()`: an agent task or function task that finishes after unload no longer calls back into the destroyed UI; the thread fallback marshals to the Qt thread and also skips after unload | `test_plugin_epoch` (offline) |

## Still open for real
| Issue | Why |
|---|---|
| #151 PostGIS read-only SQL | Query-layer construction and named-connection errors were fixed earlier, but there is no integration test: it needs a PostGIS database, which neither this sandbox nor the CI job has. A CI service container would be the next step |
| #154 | The imagery `min_area_m2` filter was fixed earlier; geographic-unit DEMs rely on `Z_FACTOR` from a heuristic and are not live-tested |
| Everything else in the open list | Fixed in code in rc8-rc19 per the checklist; waiting for a hand pass |

## From the rc18 hand test (`docs/RC18_SMOKE_TRIAGE_2026-10-06.md`) now addressed
- The legend listed a raster that lay outside the map (R7/N8): the standard layout legend now lists only layers whose extent meets the map (`test_layout_legend_live`).
- Right/top graticule labels clipped by the legend panel (N8): hidden (left and bottom remain).
- Remembered notes steering geography (N1): prompt rule 55.
