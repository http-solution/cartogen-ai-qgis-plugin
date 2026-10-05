# rc16 re-test sheet (prepared 2026-10-06)

A blank sheet, not a result. Nothing here has been run. It covers only what the rc15 hand test found; after it passes, continue with
`docs/SMOKE_RUN_SHEET_rc15_2026-10-05.md` from step 2 (the rows there still apply). An issue is closed only on a hand-verified pass.

## Install (about 10 minutes)
1. Download the **attached asset** `cartogen_ai_v1.16.0-rc16.zip` from the `cartogen-ai-v1.16.0-rc16` pre-release, not "Source code (zip)".
2. Check its SHA-256 against `SHA256-1.16.0-rc16.txt` on the same page.
3. Close QGIS. In `...\profiles\default\python\plugins\` delete every folder with `cartogen` in its name, then unzip the asset there
   (one folder, `cartogen_ai`, with underscores). Start QGIS; Settings must show `1.16.0-rc16`.

## Re-test rows
| # | Action | Expected | Found in rc15 | Result |
|---|---|---|---|---|
| 1 | Gate: panel opens, key present, no traceback in the log | all three | passed | |
| 2 | "List the layers in the project." then "Show the attributes of the Points layer." | Both answer with real data; no "Execution failed unexpectedly" | get_layers / get_attributes failed | |
| 3 | Project CRS EPSG:4326. Send "Add a point at 4902068.0, 1799912.0." | Asks which CRS, places nothing | passed | |
| 4 | Reply "EPSG:3857" | A tool call runs and the point is placed at about 15.958 N, 44.036 E; no script is pasted | model pasted a script | |
| 5 | A layout with the Points layer holding ONE point: "Create a print layout" (access_map) | A scale is shown, no "Invalid scale!" box, the map finishes rendering | "Scale unavailable", stuck on "Rendering map" | |
| 6 | Same layout after a service-area run (Yemen project) | Legend lists the reach polygon; reading guide says within-reach is blue | not testable on rc15 | |

For a failure send: the row number, the exact prompt, what you saw, and the Cartogen log lines for that turn (`tool_call` lines and any
`CRITICAL`; no coordinates needed). Row 4 depends on the model (Gemini); if it still fails, also say which provider and model you used.
