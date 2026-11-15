# Hand test results, 1.17.0-rc48 (run 2026-10-23 and 2026-10-24)

Source: `4_RESULTS.csv` of the rc48 bundle, filled in by the owner. Plugin zip SHA-256 `9d7a0ce1232f4e84063fcef12d440367c1bd800b0fa8d497bef22129de39fc88` (the published pre-release).
Rows: 87. **Pass 52, Partial 18, Fail 16, Skip 1.** The saved CartogenAI log in the bundle was empty (0 lines), so no cost table could be made; `log_TaskRunner_qgis.txt` is kept in the owner's copy.

## What this run proved (hand-tested, rc48)
- Wave E1 works: raster statistics (A19: min 33.82, max 170.00, mean 100.09, 6,400 cells), field statistics (A20), polygonize (A21: 3 polygons, classes 1 to 3).
- `export_layer` to GeoPackage (A24), `export_layers_to_dxf` writes a DXF (A25 first run), `export_layers_to_spreadsheet` writes an .xlsx with the right sheets (A26), `package_layers_offline` packages vector layers (A23, output location unverified).
- Open-issue rows that passed: #80 and #122 (OI-80), #81 and #123 (OI-123), #124 (OI-124), #91 and #94 (OI-91).

## Findings, by kind

### Fixed in the pull request that records this run (CI only until the next hand test)
| Row | Finding | Fix |
|---|---|---|
| A22 | `print_map` to PDF always failed: `QPdfWriter` has no `layout()` (it is `pageLayout()`); a blank file was left behind | `export_tools.print_map`; live test `tests/test_print_map_live.py` writes a real PDF |
| OI-120 | the tidy tool reported and applied in the same turn, so the user never saw the report | `tidy_project_layers(apply=true)` now returns a confirm card; `confirmed` is set only by the user's button |

### Real defects, not fixed yet (plan: PLAN-008)
| Row | Finding | Next step |
|---|---|---|
| OI-150 (#150) | **Leak.** With Cloud data protection = Block and `smoke_points` SENSITIVE, merging it with `smoke_hubs`, renaming the result, then asking for its attributes sent category values and source counts to the cloud model with no card. The renamed output shows 'untagged' | needs the evidence folder of that run (about 00:16 on 24 Oct); then a CI test of the exact flow merge, rename, rename, read |
| OI-148 (#148) | road distance wrong: `Inside_the_U` reported 69.96 m from the start, expected about 1.2 km along the road | needs evidence folder `20261023-201442_t3`; test the tool on the U-shaped road fixture |
| OI-128 (#128) | reply says a population ramp was applied but the canvas and legend show plain grey | reproduce `apply_raster_stretch` on a layer named `yem_ppp_2020` in CI |
| A12 | the three layout charts sit at the same spot and the bar and pie draw empty grids | placement defaults and chart data refresh |
| A6 | the elevation profile draws axes and no curve, overlaps the charts | check the profile data source and refresh |
| A16 (#362) | profile request took 6 model calls and `list_layout_items` twice (limit 4) | loop guard |
| B28, B32, B41 and 31 more plain prompts | the task library answers a plain operation request with an unrelated plan (satellite damage plan, WorldPop plan, flood plan). Measured offline: 34 of the 385 plain prompts match a task at the confident score | PLAN-008, section 'plain requests vs task library' |
| B7, B3 | `r.circle` stopped after repeated identical calls; `linestopolygons` took 29 calls | loop guard and tool choice |
| B15 | `grass:r.sunmask.datetime` fails when run (twice) | read the error, then drop or fix the id |

### Not a code defect (the sheet or the design was wrong, or the call is the owner's)
| Row | Finding | Decision |
|---|---|---|
| A25 | the second identical DXF export did not ask before replacing | by design: re-writing a file this plugin wrote and that has not changed is a re-run; the row text is corrected |
| A20, A26 | counts differ (towns 5 not 8) | three towns were deleted by earlier rows; the row texts now say so |
| OI-95 (#95) | Memory dialog says 'Saved with the project: ON' | ON is the default since the F25 option B decision (project-lifetime transcript); owner to confirm or switch the default to OFF |
| OI-130 (#130) | 'template: access_map' produced a layout template plan | run in a chat whose last assistant message was a question, where the fragment guard correctly stands down; re-run in a new chat |
| OI-145, OI-146 | script blocked 'import os'; edits to a file layer not labelled as a copy | owner decision on file-layer edits (already open) |
| OI-147 | undo does not cover `add_field` | feature gap, listed in the tool reference |
| OI-129, OI-84, OI-127, OI-97, OI-223 | partial: layout frame follows the DEM, dashboard lacks the offline note in the file, HDX labels missing, export came from the live chat, Stop not exercised | owner decisions (#129, #84) or a re-run; see the status table |
| OI-224 | not run (needs an older version installed) | owner |

## Full list of rows that are not Pass

| id | row | result |
|---|---|---|
| OI-148 | #148 | Fail |
| OI-130 | #130 | Fail |
| OI-128 | #128 | Fail |
| OI-120 | #120 | Fail |
| OI-129 | #129, #165 | Partial |
| OI-84 | #84 | Partial |
| OI-150 | #150 | Fail |
| OI-145 | #145, #146 | Fail |
| OI-147 | #147, #138 | Partial |
| OI-95 | #95 | Fail |
| OI-97 | #97 | Partial |
| OI-127 | #127 | Partial |
| OI-223 | #223 | Partial |
| OI-224 | #224, #167, #297 | Skip |
| A6 | add_layout_elevation_profile | Fail |
| A7 | apply_saved_symbol | Partial |
| A12 | add_layout_chart | Fail |
| A13 | set_layer_elevation | Partial |
| A16 | I6 profile | Fail |
| A17 | I9 chart | Partial |
| A22 | E2c pdf | Fail |
| A23 | E2c package | Partial |
| A25 | E2c dxf | Partial |
| A26 | E2c excel | Partial |
| B3 | qgis:linestopolygons | Partial |
| B7 | grass:r.circle | Fail |
| B14 | grass:r.stats.zonal | Partial |
| B15 | grass:r.sunmask.datetime | Fail |
| B25 | grass:v.neighbors | Partial |
| B27 | grass:v.net.iso | Partial |
| B28 | grass:v.patch | Fail |
| B29 | grass:v.rast.stats | Partial |
| B31 | grass:v.surf.bspline | Partial |
| B32 | grass:v.to.rast | Fail |
| B41 | native:meshrasterize | Fail |
