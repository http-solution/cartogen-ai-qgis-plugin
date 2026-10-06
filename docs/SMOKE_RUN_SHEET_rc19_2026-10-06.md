# rc19 live smoke test sheet (prepared 2026-10-06)

A blank sheet, not a result. It re-tests the fixes made after the rc18 hand test (`docs/RC18_SMOKE_TRIAGE_2026-10-06.md`) and carries over the rows the rc18 hand test did not run. **The rc18 sheet (`docs/SMOKE_RUN_SHEET_rc18_2026-10-06.md`) stays the master for sections 4 to 6 (V, J, T, P rows) and its fixtures; run those rows on rc19.** Install and gate steps are the same as rc18 section 0, with `cartogen_ai_v1.16.0-rc19.zip` and version `1.16.0-rc19`. Use a new project and a new chat for every row marked NEW CHAT (close the project and reopen it, or use the Memory dialog's reset, so the chat really is empty).

## A. Re-tests of the rc18 failures
| Id | Prompt / action | Expected | Result |
|---|---|---|---|
| A1 | NEW CHAT. R2 prompt from the rc18 sheet. At the task card reply exactly: `Yes, proceed.` | The analysis runs (optimal_hub_siting); no "no pending operation" | |
| A2 | Same prompt, reply `Yes please`, then another run with `ok go ahead` | Both run | |
| A3 | Same prompt, reply `Yes but only use Hub_A and Hub_B` | Treated as an edit (the card is rebuilt or the request changed); nothing runs on the old text | |
| A4 | NEW CHAT. R3 prompt (extract_features_from_imagery on smoke_image). Look at the task card before you reply | **No** "imagery = most recent low-cloud scene"; no MD-report deliverable; if a task is shown, `extract_features_from_imagery` is first in its tool list | |
| A5 | Reply `Yes`. Watch QGIS | QGIS keeps responding. The checkpoint downloads (about 24 MB) in seconds to a minute, then a real detection result or a clear message. **No HTTP 416** | |
| A6 | Repeat A5 and press Stop while it downloads | Stops; **no** follow-up message asking for a report | |
| A7 | NEW CHAT. N4 prompt (transform smoke_boundary's extent to WGS84, then STAC). Check the tool log | `get_layer_extent` is called; the STAC bbox is about [35.914, 31.940, 35.951, 31.970] (west, south, east, north); scenes are over Jordan, not Damascus | |
| A8 | NEW CHAT. N5 prompt (building footprints for Jordan inside smoke_boundary). | `get_layer_extent`, then `fetch_building_footprints` with a south-west-north-east box near [31.940, 35.914, 31.970, 35.951]; **no** Syria layer, no forced report. A zero-feature result for Jordan is reported as zero, not silently replaced | |
| A9 | Scene table of A7: look at the "Preview" column | A working link label, not `[Preview Image](http...` text | |
| A10 | Load smoke_start.qgz. Run the N1 severity request and click Apply edit | The severity map is visible without switching the image and DEM off; the reply or the Layers panel shows the polygon layer moved above the rasters | |
| A11 | R4 prompt (multicolour ramp on smoke_dem 35-214) | The Layers panel legend shows the ramp immediately, without another tool call | |
| A12 | NEW CHAT. "Create a map of smoke_points" then "Print layout titled Test for the current view", look at the legend | Record whether smoke_dem still appears in the legend although it is off the map (open item R7/N8) | |

## B. Carry-over: rows the rc18 hand test did not run
Run V1 to V10, T1 to T8, J1 to J17 and P1 to P20 from the rc18 sheet unchanged, on rc19 (they need `smoke_jiaf_hxl.csv`, `smoke_ipc.csv`, `smoke_inform.csv`, `smoke_unosat.csv`, the Yemen project for V9/V10/T5, and a colleague for the 10-second test). If a prerequisite is missing, write "not run: <reason>" in the result, never an inferred pass.

## C. Gates still owed
Fresh-profile install, upgrade from the previous zip, restart twice, uninstall and reinstall. The Plugin Manager duplicate entry and the earlier Install-from-ZIP failure are environment questions; send the QGIS error text if it recurs.

Known open, do not expect a pass: legend listing an off-map raster (R7/N8), clipped coordinate labels at the legend frame (N8), model-added plans and arrange steps (N3/N9), geography suggested from project memory in prose (N1), PostGIS read-only SQL (needs a database).
