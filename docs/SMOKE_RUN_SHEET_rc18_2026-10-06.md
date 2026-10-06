# rc18 live smoke test sheet (prepared 2026-10-06)

A blank sheet, not a result. Nothing here has been run. It covers (1) the seven rc17 regression rows, (2) every fix made after the rc15 and rc17
reports, and (3) the checks that passed in rc17 and must still pass. Use the release smoke fixture (`docs/release_smoke_assets/`, copied to a
fresh writable folder; `smoke_start.qgz`, CRS EPSG:32636). An issue is closed only on a hand-verified pass.

## 0. Install (10 minutes)
1. Download `cartogen_ai_v1.16.0-rc18.zip` from the `cartogen-ai-v1.16.0-rc18` pre-release (not "Source code (zip)"); check its SHA-256 against `SHA256-1.16.0-rc18.txt`.
2. Close QGIS. In `...\profiles\default\python\plugins\` delete every folder with `cartogen` in its name, then unzip the asset there. One folder, `cartogen-ai`, appears.
3. Start QGIS 4.2. **Gate:** Plugin Manager shows ONE Cartogen AI entry, Settings shows `1.16.0-rc18`, the panel opens, the key is present, the log has no traceback.
4. Open a **new** chat before every row marked NEW CHAT; copy the fixture again if a row says so. Keep the Log Messages panel visible.

Result column: PASS / FAIL, then what you saw. For a FAIL send the row id, the exact prompt, a screenshot, and the Cartogen log lines for that turn (tool names, statuses, CRITICAL lines; no coordinates).

## 1. The seven rc17 regression rows
| Id | Prompt / action | Expected on rc18 | Was in rc17 | Result |
|---|---|---|---|---|
| R1 | NEW CHAT. "List the layers in the project." | Seven fixture layers with counts, CRS, fields | passed | |
| R2 | NEW CHAT. "Use optimal_hub_siting to rank the three candidate locations in smoke_hubs by average straight-line distance to all five demand features in smoke_points. Tell me the winning hub name and each candidate's computed average distance; do not claim road-network routing or population weighting." | **No** "Which facility type?" question; task 21.19, no OSM task card; Hub_A 886.49 / Hub_B 1035.21 / Hub_C 1621.51 m; **no** "Not from a tool result" footnote | asked twice; false footnote | |
| R3 | NEW CHAT. "Run extract_features_from_imagery on loaded raster smoke_image with confidence threshold 0.4. Report the model used and actual detection count; do not label synthetic shapes as real buildings." | QGIS keeps responding during any download; a clear message or a real result; no URL in the chat | froze 43 s, HTTP 416 | |
| R4 | "Apply a multicolour color ramp to the raster layer smoke_dem using band 1 with its actual minimum and maximum values." Save the project, reopen it. | **No** data-standards task preview; ramp 35-214; legend still 35-214 after reopen | wrong preview; range fine | |
| R5 | With a temporary buffer layer present: "Save the project." | Names the temporary layer and says it comes back empty | passed | |
| R6 | Project CRS EPSG:4326. "Add a point at 4902068.0, 1799912.0." then reply "EPSG:3857" | Asks first; after the reply a point is placed (a tool call appears) | no tool call, "add_point_layer unavailable" | |
| R7 | A print layout with the Points layer holding one point | A valid scale, no "Invalid scale!" | passed | |

## 2. Fixes made after the reports (new behaviour)
| Id | Prompt / action | Expected | Result |
|---|---|---|---|
| N1 | NEW CHAT. Send a request that makes Cartogen ask a question (for example "Estimate flood exposure for the area"). **Do not answer.** Type instead: "Calculate a severity index for the three polygons in smoke_admin using its numeric population and need fields, with admin_name as the unit name. Use equal weights and write the score to severity_rc18." | The new request runs (a severity confirmation card for `severity_rc18`); it is NOT shown as "Details:" under the flood request; no OpenStreetMap question | |
| N2 | Continue from N1: click **Apply edit**. Request used: "...write the score to severity_rc18, and then style smoke_admin by that field." (use this wording in N1 if you want to test N2 together) | After Apply, "Continuing with the rest of your request..." appears and smoke_admin gets a graduated renderer on `severity_rc18` | |
| N3 | NEW CHAT. Export smoke_points to CSV at a path where a non-empty file already exists: "Export smoke_points to CSV at outputs/smoke_points.csv". Then Cancel. Repeat and Apply. Then export the same file again straight away. | A confirmation card first; Cancel leaves the file untouched; Apply replaces it; the immediate re-export of the file Cartogen just wrote is silent | |
| N4 | NEW CHAT. "Transform smoke_boundary's extent to WGS84 and call search_stac_satellite_imagery for Sentinel-2 scenes from 2026-08-01 through 2026-08-31, limit 5. Report actual IDs, dates, cloud cover, and available asset links." | `search_stac_satellite_imagery` is called within about five tool calls; the scene table stays in the answer (not "Table removed") | |
| N5 | NEW CHAT. "For Jordan, convert smoke_boundary's extent to WGS84 [south, west, north, east] and fetch up to 50 Microsoft building footprints inside it. Add the result to the project and report the actual feature count." | `fetch_building_footprints` is called; no unrelated layers or exports | |
| N6 | NEW CHAT. "Search the web for the latest stable QGIS release announcement. Return title, publication date and source URL." | The release it names is the newest one, with its date; links are well-formed | |
| N7 | NEW CHAT. "Buffer smoke_points by 500 meters and name the result smoke_points_buffer_500m." | The new layer is named `smoke_points_buffer_500m` exactly | |
| N8 | NEW CHAT. "Create a print layout titled Smoke Test Layout for the current map view and export it as a PDF to outputs/smoke_layout.pdf." | Title and file path exactly as asked | |
| N9 | NEW CHAT. "Create a plan: buffer smoke_points by 250 meters, clip the buffers to smoke_boundary, export the result to a GeoPackage at outputs/plan_rc18.gpkg and store a project memory note that the buffer distance was 250 meters." | A local four-step plan (no "web mapping" task); all four steps run; no "No data was retrieved" warning on the plan | |

## 3. Must still pass (passed in rc17)
| Id | Check | Result |
|---|---|---|
| K1 | Categorical zone styling and the boundary label survive save and reopen | |
| K2 | PDF and Word table extraction return id/value rows A01/10, A02/20, A03/30 | |
| K3 | Scheduler: a 1-minute workflow with max 2 runs ticks twice and stops; listing shows none after the dock is closed and reopened | |
| K4 | Project save, load confirmation (Cancel then Apply), chat and styles restored | |
| K5 | Sandbox: safe script returns EPSG:32636; `import os` is rejected, also after a confirmation | |

Known open, do not expect a pass: PostGIS read-only SQL needs a database (skipped); fresh-profile install, upgrade, restart-twice and
uninstall/reinstall gates are not covered by this sheet; the layout title and the output field the model chooses are model decisions and can
still go wrong; the imagery model needs `ultralytics` and a download on first use.
