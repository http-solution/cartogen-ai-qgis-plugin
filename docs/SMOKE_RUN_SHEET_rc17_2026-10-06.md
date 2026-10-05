# rc17 re-test sheet (prepared 2026-10-06)

A blank sheet, not a result. Nothing here has been run. It re-tests what the rc15 report found and what rc16 and rc17 changed. Use the
smoke fixture (`docs/release_smoke_assets/`, copied to a writable folder). An issue is closed only on a hand-verified pass.

## Install
1. Download the attached asset `cartogen_ai_v1.16.0-rc17.zip` from the `cartogen-ai-v1.16.0-rc17` pre-release (not "Source code (zip)")
   and check its SHA-256 against `SHA256-1.16.0-rc17.txt`.
2. Close QGIS. In `...\profiles\default\python\plugins\` delete every folder with `cartogen` in its name (the report found two Cartogen
   entries in Plugin Manager), then unzip the asset there. One folder, `cartogen-ai`, is created. Settings must show `1.16.0-rc17`.

## Rows
| # | Prompt / action | Expected | rc15 result | Result |
|---|---|---|---|---|
| 1 | "List the layers in the project." | Real layer list, no "Execution failed unexpectedly" | failed | |
| 2 | "Use optimal_hub_siting to rank the three candidate locations in smoke_hubs by average straight-line distance to all five demand features in smoke_points. Tell me the winning hub name and each candidate's computed average distance; do not claim road-network routing or population weighting." | The "Why this prompt" card does NOT show an OpenStreetMap export task; the answer names Hub_A, Hub_B, Hub_C (not 1, 2, 3) with about 886 / 1036 / 1622 m | task 19.18 injected; wrong figure | |
| 3 | "Run extract_features_from_imagery on loaded raster smoke_image with confidence threshold 0.4. Report the model used and actual detection count." | No OSM task card. If the checkpoint cannot be downloaded: a clear message, no long URL in the chat | OSM task card; URL shown; QGIS not responding ~1 min | |
| 4 | Apply a colour ramp to smoke_dem, save the project, reopen it | Legend still shows 35-214, not nan | nan / nan | |
| 5 | With a temporary buffer layer present: "Save the project." | The reply lists the temporary layer(s) and says they come back empty | said everything persisted | |
| 6 | Project CRS EPSG:4326. "Add a point at 4902068.0, 1799912.0." then reply "EPSG:3857" | Asks first; then places the point (rc16 fix, depends on the model) | (rc15) not run | |
| 7 | A print layout when the Points layer holds one point | A scale is shown, no "Invalid scale!" (rc16 fix) | failed in an earlier run | |

Known open, so do not expect a pass: after **Apply edit** the rest of a multi-step request does not continue (D05, needs a decision), and
the imagery model download still blocks QGIS while it runs (D06). For a failure send the row number, the exact prompt, what you saw, and
the Cartogen log lines for that turn (tool names and any CRITICAL lines; no coordinates).
