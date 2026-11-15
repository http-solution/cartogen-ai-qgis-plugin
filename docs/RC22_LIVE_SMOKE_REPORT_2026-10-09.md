# RC22 live smoke test — current results, 2026-10-09

Status: IN PROGRESS — Gemini initially remained blocked after the credit top-up, then returned `CREDIT_OK` at 12:28 local time. Provider-dependent execution resumed. No full smoke-test pass is claimed.

Live target verified: QGIS **4.2.3 Belém do Pará**, revision b041a18904a (native About screenshot QGIS_4_2_3_about.jpg); one enabled Cartogen AI **1.16.0-RC22** entry (01_installed_version.png). Provider: Google Gemini (Hosted), gemini-flash-latest. Tests ran through native Windows computer use on disposable fixture copies. This folder retains its original 2026-10-08 name; execution continued on 2026-10-09.

ZIP SHA256: 44BD1742F8D57194F4FF9895757DE6907F6B417C838C083438A0ABC57948414C. A published checksum comparison and installation/restart-twice/reinstall gates were not performed.

120 distinct run-sheet rows tracked: 32 PASS, 33 FAIL, 6 INCONCLUSIVE, 49 NOT RUN. Verdicts apply to full row requirements: successful diagnostic retries do not convert failed original prompts to passes. Component successes and limits are retained below. Counts include carry-over aliases such as R2/A1; they are not counts of independent model requests.

Primary failures include stale intents/plans crossing project chats; ordinary severity requests routed to drought; styling omitted after confirmations; inaccurate legends and report content; rotation lost in layouts; incorrect JIAF setup country and invented district/phase explanations. Correct stored calculation values do not validate contradictory natural-language replies.

Evidence is in screenshots/, outputs/ and logs/. The complete matrix including exact prompts, expected outcomes and source sheet is RC22_RESULT_MATRIX.csv (and JSON). Temporary raster copies explicitly described as tester-preserved are not successful plugin exports. No plugin code was changed.

J17: saved, closed and reopened inputs/jiaf/jiaf.qgz natively. Review map, final/preliminary fields, setup and decision survived. The persisted setup is still the wrong Syria/Damascus record from J3. Current review styling survived; severity styling persistence was not separately completed. QGIS is left open on this saved project, with no active agent request.

Execution resumed after the provider recovered. A8/N5 still needs the pending 54.1 MB tile decision. PostGIS and Yemen rows require their specified fixtures; P-table colleague readability answers must come from an actual human. Local destructive sandbox tests require action-time confirmation under the computer-use skill. Historical connection failures are preserved separately in RC22_LIVE_SMOKE_CHRONOLOGY.md.

## Current row matrix

| Row | Status | Finding / limit |
|---|---|---|
| R1 | PASS | Seven fixture layers, counts, CRS and fields verified live. |
| R2 | FAIL | Hub-siting confirmation produced no calculation; stale/no-pending-task response. |
| R3 | PASS | FastSAM ran, actual detection count zero on synthetic gradient; during-download responsiveness not exercised. |
| R4 | PASS | Viridis actual range 35-214 persisted after save/reopen; verified in saved QGZ. |
| R5 | PASS | Save succeeded and explicitly named smoke_points_buffer_500m as a temporary in-memory layer whose data will not persist after close/reopen unless exported. |
| R6 | PASS | Short EPSG:3857 reply placed one point; persisted coordinates independently checked. |
| R7 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| N1 | PASS | Distinct request replaced unanswered clarification; Apply resumed severity styling above rasters. |
| N2 | PASS | Distinct request replaced unanswered clarification; Apply resumed severity styling above rasters. |
| N3 | FAIL | No overwrite confirmation; claimed CSV export left both prepared sentinel files unchanged. |
| N4 | PASS | Correct WGS84 extent and five real STAC scene records. |
| N5 | INCONCLUSIVE | Correct Jordan extent; 54.1 MB tile stopped at 50 MB confirmation gate, download pending. |
| N6 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| N7 | PASS | Fresh-project run created five 500 m buffers and named the result smoke_points_buffer_500m exactly. |
| N8 | FAIL | Exact layout title created, but claimed PDF export did not exist on disk. |
| N9 | FAIL | Correct four-step plan ran and memory updated, but claimed GeoPackage did not exist on disk. |
| A1 | FAIL | Hub-siting confirmation produced no calculation; stale/no-pending-task response. |
| A2 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| A3 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| A4 | FAIL | Preview invented CSV/OSM workflow for explicitly loaded raster. |
| A5 | PASS | FastSAM ran, actual detection count zero on synthetic gradient; during-download responsiveness not exercised. |
| A6 | INCONCLUSIVE | Stop arrived after cached inference completed; cancellation unverified. |
| A7 | PASS | Correct WGS84 extent and five real STAC scene records. |
| A8 | INCONCLUSIVE | Correct Jordan extent; 54.1 MB tile stopped at 50 MB confirmation gate, download pending. |
| A9 | INCONCLUSIVE | Readable asset links displayed; target availability not opened. |
| A10 | PASS | Distinct request replaced unanswered clarification; Apply resumed severity styling above rasters. |
| A11 | PASS | Viridis 35-214 ramp appeared immediately in the Layers panel. |
| A12 | PASS | Layout_Test created; legend still included rasters including off-map smoke_dem. |
| H1 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| H2 | PASS | Live Stop acknowledged; new CRS request answered without late satellite actions. |
| H3 | PASS | All 16,384 valid cells retained; five minimum cells mapped to 1, NoData remains 0. Actual missing-input cells absent. |
| H4 | PASS | Horizontal US survey feet conversion: slopes identical to metre grid. Separate requested persistent export failed. |
| H5 | FAIL | First attempt executed stale layout instead of export. Fresh-project exporter recovery passed WGS84 GeoJSON. |
| H6 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| H7 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| H8 | INCONCLUSIVE | 225 output rows/fields and agent Stop verified; dedicated zonal worker responsiveness unexercised. |
| H9 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| H10 | PASS | 80 million raster values rejected against 60 million limit; no crash or bypass. |
| F1 | PASS | Out-of-range manual break rejected; no inverted legend. |
| F2 | FAIL | Correct class boundaries, but explicit pale-yellow/dark-red ramp ignored. |
| F3 | FAIL | 30-degree canvas exported with map and arrow rotation zero. |
| F4 | PASS | Zero-rotation map and north arrow verified in rendered PDF. |
| F5 | PASS | Stray fragment mutation rejected; original layers unchanged. |
| F6 | PASS | Short EPSG:3857 reply placed one point; persisted coordinates independently checked. |
| F7 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| D1 | NOT RUN | Disposable PostGIS connection unavailable; additionally provider credits depleted. |
| D2 | NOT RUN | Disposable PostGIS connection unavailable; additionally provider credits depleted. |
| D3 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| D4 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| D5 | PASS | Vertical international feet slope conversion verified to 0.000148 degrees; separate raster export failed honestly. |
| D6 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| D7 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| D8 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| D9 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| D10 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| D11 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| D12 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| D13 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| D14 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| V1 | FAIL | Exact severity prompt routed to drought. Explicit recovery map worked but saved legend contradicted reply. |
| V2 | FAIL | People-in-need legend lacks units and boundary wording does not match rendered class at 7. |
| V3 | FAIL | Equal-weight scores and short map reply worked; required explicit 0-low/1-high explanation omitted. |
| V4 | FAIL | Ranking list returned; Apply did not resume styling and top district not highlighted. |
| V5 | PASS | Allocation totals 100,000, meets 5,000 minimum and 100 rounding; advisory wording present. |
| V6 | FAIL | Situation-report PNG fits; obscured raster/zones remain in legend. |
| V7 | FAIL | RC22 version, workflow groups and displayed counts verified; inspected entries lacked claimed NEW markers. |
| V8 | FAIL | Honest no-setup response; required support-for-JIAF-process statement omitted. |
| V9 | NOT RUN | Required Yemen roads/warehouses/health project unavailable; additionally provider credits depleted. |
| V10 | NOT RUN | Required Yemen roads/warehouses/health project unavailable; additionally provider credits depleted. |
| V11 | FAIL | IPC pass; INFORM and UNOSAT styling failures prevent combined pass. |
| T1 | PASS | IPC imported 3/3 and displayed proper five named phase rules, above rasters. |
| T2 | FAIL | INFORM fields imported; no continuation; short map request routed to heat and explicit follow-up to export. |
| T3 | FAIL | UNOSAT six points loaded; single-symbol renderer despite categorical colour claim, obscured by admin. |
| T4 | FAIL | Exact zonal map request resumed stale INFORM plan. Explicit calculation needed separate styling follow-up. |
| T5 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| T6 | FAIL | Plain clustering request denied capability. Explicit tool recovery produced four paletted clusters. |
| T7 | PASS | Five jitter distances 23.61–187.69 m; original point geometry unchanged; output preserved. |
| T8 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| J1 | FAIL | Read-only HXL four units/eight sectors and totals correct; exact OCHA/IASC non-endorsement statement incomplete. |
| J2 | PASS | Three districts matched; Outside_area explicitly unmatched, no map units missing. |
| J3 | FAIL | Stored Syria/Damascus instead of explicit Smokeland; HCT endorsement NULL instead of explicit not endorsed. |
| J4 | FAIL | Cancel/Apply fields and values correct; required totals, phase5 notice and lower-bound reply absent after Apply. |
| J5 | FAIL | Exact prompt routed to drought; explicit recovery produced correct 3/5/NULL phase renderer. |
| J6 | FAIL | Correct PIN field and three polygons shown; lower-bound note omitted, class-at-600 wording mismatch. |
| J7 | FAIL | Correct incomplete-sector explanation and not-phase1 warning; technical field/NULL terms fail plain-wording requirement. |
| J8 | PASS | 3020/2300/2900 explained with Outside_area exclusion and provisional District_3; dollar-symbol presentation defect. |
| J9 | FAIL | 2900 provisional total and phase5 notice correct; invented District_4 and incorrect District_1 phase2. |
| J10 | FAIL | Rationale/decisionmaker stored; no-reason decision rejected; required tool-only-records disclaimer absent. |
| J11 | PASS | Bulk flag closure asked for rationale and decisionmaker, no closure applied. |
| J12 | PASS | Confirmed final/review fields; District_3 red pending, District_2 green decided; saved readable rules. |
| J13 | FAIL | 20 calls on invented paths then tool limit. Exact-path recovery produced ten sections and required sector counts. |
| J14 | FAIL | Clear not-compliant/not-official/not-endorsed/not-method; explicit team-confirmed thresholds/rules caveat absent. |
| J15 | FAIL | Long technical answer with flag numbers and incorrect preliminary 1200 instead of 1800. |
| J16 | FAIL | Exact prompt routed to drought. After credits recovered, explicit recovery created and exported a valid PDF, but the requested title and non-endorsement note were missing and the legend contained extra/clipped entries. |
| J17 | INCONCLUSIVE | Saved/closed/reopened; fields, setup, decision and review look persist. Severity look not current, so full row unverified. |
| K1 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| K2 | PASS | Both PDF and Word extraction returned A01/10, A02/20, A03/30 from absolute local paths. The initial relative-filename PDF request stalled and was stopped. Evidence: `screenshots/K2_pdf_word_table_extraction_pass_2026-10-09.jpg`. |
| K3 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| K4 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. |
| K5 | PASS | Safe script returned EPSG:32636. `import os` was rejected before and after explicit confirmation. Evidence: `screenshots/K5_safe_script_and_import_rejection_2026-10-09.jpg`, `screenshots/K5_import_os_rejected_after_confirmation_2026-10-09.jpg`. |
| P1 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P2 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P3 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P4 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P5 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P6 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P7 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P8 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P9 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P10 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P11 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P12 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P13 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P14 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P15 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P16 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P17 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P18 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P19 | NOT RUN | Blocked by Gemini HTTP402 RESOURCE_EXHAUSTED: prepayment credits depleted. Human colleague 10-second readability measurement also outstanding. |
| P20 | NOT RUN | Required Yemen roads/warehouses/health project unavailable; additionally provider credits depleted. |

## Detailed live observations

## Live access restored — 2026-10-08 22:38–22:41
Status now IN PROGRESS; earlier NOT RUN entries describe failed connection attempts only. Native QGIS UI verified one enabled Cartogen AI installed version 1.16.0-RC22. Screenshot 01_installed_version.png. Separate baseline fixture copy loaded with seven layers. Baseline inventory PASS: get_layers returned seven exact names, vector counts 3/1/3/5/3, raster types, EPSG:32636 and expected fields. Screenshot 02_inventory_result.png. Baseline project saved with chat. ZIP SHA256 44BD1742F8D57194F4FF9895757DE6907F6B417C838C083438A0ABC57948414C; no published checksum comparison. Remaining run-sheet rows not yet tested.

### A1 — FAIL (22:42–22:43)
Fresh a1 project, empty visible chat. Exact R2 hub-siting prompt showed task21.19 preview, unexpectedly described CSV deliverable. Exact reply Yes, proceed. produced no pending tasks/queued operations, Table removed and No data retrieved warning. No optimal_hub_siting result. Evidence A1_result.png and saved inputs/a1/a1.qgz chat.

### A7 — PASS extent/search routing (22:44)
Fresh chat; get_layers 15ms, get_layer_extent 47ms, search_stac_satellite_imagery 1078ms. Correct WGS84 west/south/east/north [35.914116,31.940192,35.950895,31.969809]. Five dated scenes and asset links remain visible. A9 readable link-label portion PASS; remote link destination availability not yet opened. Evidence A7_scene_table.png and agent_through_A7.txt; saved inputs/a7/a7.qgz.

### A8 footprint execution (pending download decision)
Ordinary Yes executed the task. Correct Jordan WGS84 SWNE [31.940192,35.914116,31.969809,35.950895]. Microsoft tile 54.1 MB triggered the configured 50 MB download confirmation. No footprint layer added yet. Preview incorrectly claims explicitly requested CSV and suggests OSM first. Evidence: screenshots/A8_download_gate.png.

### F5 PASS (tool guard; model attempted mutation)
Fresh chat exact template: access_map. get_layers then create_print_layout attempted; tool rejected short fragment, explicitly nothing changed. Reply asks clarification. Seven original layers remain; no layout success. Evidence screenshots/F5_fragment_guard.png.

### H5 attempt 1 FAIL: stale fragment executed
After F5 tool guard, explicit projected GeoJSON export preview was confirmed with Yes. Instead RC22 called create_print_layout and created Layout_Facility_Access_Map using prior access_map fragment. No requested export performed. This is a stale-intent/confirmation isolation failure; fresh-project export repeat needed to assess exporter independently. Evidence screenshots/H5_stale_fragment_layout.png.

### H5 fresh-project exporter PASS
Fresh h5.qgz/chat repeated explicit request and Yes. GeoJSON has five original features, WGS84 coordinates near 35.92/31.95, no crs member. Loaded H5_smoke_points in fixture area. Extra reprojected memory layer and automatic layer rearrangement occurred. Evidence outputs/H5_smoke_points.geojson, logs/H5_geojson_verification.json, screenshots/H5_export_loaded.png. Earlier stale-intent failure remains.

### H3 PASS valid minimum preservation
Live histogram_equalization done 78 ms. Saved outputs/smoke_dem_equalized.tif, displayed opaque low cells. GDAL independent read: 128x128=16384 cells, all valid, output 1..255 with NoData 0. All five original minimum-35 cells map to 1; zero valid cells lost. Model made 15 calls including scripts and an extra plan; one script failed and was retried. Source fixture has no actual NoData, so actual missing-cell preservation not exercised. Evidence H3_result.png, H3_agent_progress.png, logs/H3_verification.json, logs/H3_gdalinfo.json.

### A4 preview FAIL (execution pending)
Exact imagery prompt. Preview task 19.02 invents CSV deliverable and display suggests fetch_osm_features/add_layer_from_path/search_stac_satellite_imagery before extract. Added system prompt places extract first, so UI/system order inconsistent. No latest-low-cloud scene invented in shown text. Evidence screenshots/A4_preview.png.

### A5/R3 execution PASS (download responsiveness not fully exercised)
extract_features_from_imagery actually ran 23:03:29–23:03:41, duration 12530 ms, done. Reply FastSAM class-agnostic segmentation, confidence .4, actual count 0; no claim synthetic image is real buildings, no HTTP 416. No output layer for zero detections. H9 object-only accuracy not assessed: supplied raster is a synthetic gradient with no known segmented object. UI responsive before/after; no concurrent native action during 12.5 s inference was observed, so responsiveness during model execution remains pending. Completed H3 plan resurfaced on A4 preview after project switch (cross-project stale plan display). Evidence screenshots/A5_FastSAM_result.png and A5_agent_log.png, logs/agent_through_A5.txt.

### A6 Stop attempt inconclusive
Repeated imagery exact prompt and Yes. Stop clicked following active screenshot, but response already completed in returned state, no cancellation acknowledgement. Cannot certify cancellation. Faster cached inference requires another longer-running cancellation target.

### H2 PASS Stop/new-request isolation (satellite analysis)
Long satellite analysis made eight calls, native Stop produced Stopping then [Agent stopped] Stopped by user. New project-CRS question answered only EPSG:32636; no late satellite answer or new layers appeared before this answer. Evidence H2_stopped.png and H2_new_request_result.png. This does not certify A6 cancellation during first-use FastSAM download.

### H10 PASS
Synthetic fixture made with installed GDAL gdal_create (not a headless plugin test): 3200x3125=10000000 cells, eight Byte bands. Native chat add_layer_from_path then unsupervised_classification, four classes/all bands. Tool refused 80000000 values above 60000000 limit, says clip it or use fewer bands. No workaround, no crash. Evidence inputs/h10/eight_band_10M.tif, screenshots/H10_size_guard.png.

### H4 — PASS horizontal US survey feet conversion; FAIL requested persistent export
Live slope_analysis ran twice (23:19:25, 46 ms; 23:19:29, 31 ms). Independent GDAL XYZ comparison: all 16384 cells identical, 0–32.31153106689453 degrees, max absolute difference 0. The response marked export complete but project sources remained temporary TIFFs and the requested output directory contained neither slope raster. Evidence copies preserved as outputs/H4_metres_slope.tif and H4_usfeet_slope.tif; these copies were made by the tester, not the plugin. Screenshots H4_response.jpg/H4_agent_log.jpg and logs/H4_verification.json. Coordinate transform warnings appeared for EPSG:2263 to project CRS/WGS84.

### D5 — PASS vertical international feet conversion; raster export failed honestly
Live slope_analysis on metre horizontal grid with dem_vertical_unit ft. GDAL comparison against metre-elevation DEM: 16384 valid cells, max difference 0.00014781951904296875 degrees (Float32 conversion rounding), range 0–32.31154251098633. The model attempted vector export_layer on QgsRasterLayer, which failed; final response explicitly reported no permanent export. Tester preserved outputs/D5_vertical_feet_slope.tif from the temporary output. Verification logs/D5_verification.json, screenshot D5_export_failure.jpg.

### H8 — PASS output fields/count and agent Stop; INCONCLUSIVE dedicated-tool responsiveness
225 polygons loaded. Model used run_allowlisted_processing_algorithm, 77 ms at 23:26:16, instead of dedicated zonal_statistics. Stop acknowledged after calculation completed; agent stopped with no export until new request. New request explicitly asked dedicated tool but model exported existing result via execute_pyqgis_script (one failed script, then recovered), did not rerun zonal_statistics. Native loaded output and independently verified GeoPackage: 225 features, zs_mean/zs_median/zs_stdev fields. Dedicated worker responsiveness and interruption during calculation remain untested. outputs/H8_zonal_stats.gpkg, logs/H8_verification.json, H8_stop.jpg/H8_result.jpg/H8_agent_log.jpg.

### F1 — PASS invalid-break guard
Prepared three polygons need=5,10,15. Live apply_graduated_style rejected manual break100, response reported range5–15. No inverted class/legend entry; original single pink symbol remained. F1_invalid_break.jpg.
### F2 — PASS class intervals and legend; FAIL explicitly requested colour ramp
Manual breaks8/11 produced three visible classes5–8,8–11,11–15. Legend matches map and input values preserved. The requested pale-yellow-to-dark-red ramp was ignored: map uses purple/teal/yellow (Viridis). F2_valid_breaks.jpg.

### F3 — FAIL rotated current-view layout
Canvas native rotation set30 degrees. create_print_layout/export_print_layout produced F3_rotated_view.pdf but actual rendered main map and north arrow upright. Saved QGZ independently confirms canvas_rotation30, MAP_MAIN mapRotation0, NORTH_ARROW pictureRotation0. PDF page rendered/screenshots/F3_pdf_page.png, logs/F3_layout_verification.json. Extra inset and technical raster-band legend present.

### F4 — PASS zero-rotation north arrow
Canvas reset natively to0. New F4 Unrotated View layout exported to outputs/F4_unrotated_view.pdf; rendered screenshot F4_pdf_page.png confirms upright arrow/map. Existing F3 layout preserved.

### F6 — PASS: projected coordinates and short CRS reply
Live request added (4902068,1799912), followed by EPSG:3857. Plugin requested the CRS, accepted the short reply, and plotted the point. Saved layer F6_added_point.gpkg and project inputs/f6/f6.qgz. Independent ogr2ogr verification: one feature at longitude 44.036026081932143, latitude 15.958453945147442. Evidence: F6_CRS_question.jpg, F6_point_placed.jpg, F6_saved.jpg, logs/F6_point_verification.geojson.

### N1 / N2 / A10 — PASS
Unanswered flood clarification was replaced by a distinct severity request, with no stale Details or OSM question. Apply edit wrote severity_rc22, resumed the styling request, and moved smoke_admin above the enabled RGB/DEM rasters. Saved n1.qgz and independently checked scores District_1=0, District_2=0.7857, District_3=0.75; graduated renderer on severity_rc22 with five 0.2-wide classes. Evidence: N1_flood_question.jpg, N1_severity_confirmation.jpg, N2_A10_severity_visible.jpg, N1_N2_A10_verification.json. A completed H8 export plan briefly resurfaced during prompt processing; no H8 action executed in N1.

### V1 — FAIL on exact prompt; explicit-field follow-up pending
Fresh chat, exact Show the severity on the map for smoke_admin. returned Map drought severity / Which hazard specifically? without reading severity_smoke or styling the map. Evidence V1_wrong_drought_question.jpg.

V1 recovery: explicit severity_smoke follow-up applied the expected five-colour renderer and brought polygons above rasters. GeoPackage SHA256 remains identical to the untouched bundled fixture. Saved legend labels are numeric 1 (score < 0.2) through 5 (0.8 or more), despite response claiming Minimal/Low, Stressed, Crisis, Emergency, Catastrophic; human-readable legend criterion FAIL. Evidence V1_explicit_field_recovery.jpg, V1_verification.json, inputs/v1/V1_saved.qgz.

### V2 — FAIL legend wording; count styling PASS
People-in-need request applied a two-class purple renderer on need. Saved labels 3 to < 7 and 7 to 10 omit people; no zero class was created (fixture has no zero-valued polygon, so zero rendering unexercised). District_2 with value 7 rendered pale despite reply assigning 7 to the dark class. Evidence V2_people_in_need.jpg, V2_response.txt, V2_verification.json, inputs/v1/V2_saved.qgz.

### V3 — PASS calculation and short map reply; explanation incomplete
Apply edit wrote severity_v3: 0,0.7857,0.75. yes show it on the map applied the five-class severity renderer to severity_v3. Reply described ordered score classes and unit scores but omitted an explicit 0=low, 1=high explanation. Evidence V3_mapped.jpg, V3_response.txt, V3_verification.json, inputs/v1/V3_saved.qgz.

### V4 — FAIL map continuation; ranked list PASS
Ranking returned District_2 0.7857, District_3 0.75, District_1 0.0 with sensitivity notes. show the ranking on the map requested rank-field mutation; Apply edit completed but did not continue to styling. After 15 seconds idle the canvas remained severity_v3 (District_2 and District_3 equally red), so top-ranked dark/rest-muted requirement failed. Completed H8 plan resurfaced and accumulated unrelated preview steps. Evidence V4_ranking.jpg, V4_ranking_response.txt, V4_map_not_resumed.jpg.

### V5 — PASS
Advisory allocation returned District_3=47500, District_2=34700, District_1=17800. Sum=100000, each >=5000 and a multiple of 100; excluded units none. Reply explicitly calls it an advisory analytical split for planning, not an operational mandate. No allocation data write requested/performed. Evidence V5_allocation.jpg, V5_advisory.jpg, V5_response.txt.

### V6 — FAIL legend filtering; layout/export/content fit PASS
Plugin created situation-report layout and actual outputs/V6_situation_report.png. Visually inspected exported PNG: masthead, summary, requested District_2 figure, source and handling note fit without truncation. Legend still lists obscured smoke_zones, DEM and RGB beneath opaque admin polygons; therefore only-visible-layer criterion failed. Reading guide uses handling wording rather than explicit severity interpretation. Evidence V6_export_response.jpg, V6_response.txt and exported PNG.

### V8 — PASS missing-setup honesty; process wording absent
Actual get_jiaf_setup returned no setup recorded and listed parameters needed to record one. No final figure or endorsement invented. Reply did not explicitly identify support for the JIAF 2 process. Evidence V8_no_setup.jpg, V8_response.txt.

### V7 — PASS version/workflow grouping/count presentation; NEW markers absent
Native Help opens and identifies 1.16.0-rc22, with RC22 changes, humanitarian workflows grouped by use, task count 792 across 36 sections and tool count 203. Source-of-count derivation not independently executed. No NEW markers were visible in inspected workflow entries despite explanatory text referring to (new) marks. Evidence V7_help_rc22.jpg, V7_workflow_groups.jpg, V7_help_counts.jpg.

### T1 / V11 IPC — PASS
Confirmed import matched 3/3 admin_name values, wrote ipc_phase/ipc_pop/ipc_p3plus correctly. Short Show it on the map applied named IPC phase rules: District_1 phase2 yellow, District_2 phase4 red, District_3 phase3 orange. Independent SQLite/QGZ verification confirms imported values and labels Minimal/Stressed/Crisis/Emergency/Famine/Not analysed. Evidence T1_import_confirmation.jpg, T1_IPC_map.jpg, T1_verification.json, inputs/t1/T1_saved.qgz.

### T2 — FAIL automatic style continuation; import completed
Import INFORM ... and show the risk prompted confirmation for four inf_ fields, matching 3/3. Apply edit completed but no styling resumed after 15 seconds idle; canvas remained IPC phases. Explicit follow-up recovery being tested separately. Evidence T2_no_auto_style.jpg.

T2 explicit recovery also failed routing: Show the INFORM risk ... inf_risk asked Which hazard specifically? for Map extreme-heat risk. Explicit Apply INFORM humanitarian look then generated OSM export-task 19.18 preview (confidence 0.50), preferring export_layer/export_to_csv instead of map styling. Preview was not approved. Evidence T2_wrong_heat_question.jpg and T2_wrong_export_preview.jpg.

T2 independent import verification PASS: inf_risk District_1=2.4, District_2=7.1, District_3=4.6; inf_haz/inf_vuln/inf_coping match CSV. logs/T2_import_verification.json. Original combined import/style row remains FAIL.

### T3 / V11 UNOSAT — FAIL styling and visibility; load/count prose PASS
CSV-backed smoke_unosat loaded in EPSG:4326 with longitude/latitude fields. Reply reported 1 destroyed, 2 severe, 1 moderate, 1 possible, 1 none and claimed class colours. Saved QGZ instead has singleSymbol renderer with no categories/rules; layer is below opaque smoke_admin, so six markers are obscured. Reply also claims green None rather than requested pale blue. Evidence T3_points_obscured.jpg, T3_response.txt, T3_verification.json.

### T4 — FAIL: stale INFORM request resumed (2026-10-09)
Exact elevation prompt followed by Yes, proceed caused an eight-call INFORM-risk workflow and reply, rather than zonal elevation. Evidence: screenshots/T4_wrong_INFORM_resume.jpg. Retrying explicitly for diagnostic coverage.

T4 diagnostic retry computed persistent zs_mean, zs_median, zs_stdev (means 109.7020, 115.2341, 148.0541). Requested mean-only ignored; styling not executed, saved renderer still IPC. Reply overall mean 144.33 contradicts arithmetic mean 124.3301, and stdev median incorrectly 29.20 instead of 29.0375. Evidence T4_verification.json and T4_zonal_unstyled.jpg.

Correction: stdev median 29.20 is correct (middle sorted value 29.19545). Overall mean 144.33 remains incorrect.

T4 separate styling follow-up succeeded (two-class light/dark blue zs_mean). Prior reply now displays 124.33 on recapture, while original screenshot recorded 144.33; keep both as observed. Original end-to-end row remains FAIL, explicit recovery succeeds.

### T6 — FAIL: raster clustering incorrectly unavailable
Exact prompt Cluster smoke_image into four groups produced two calls and a refusal claiming unsupervised raster clustering is unavailable. No new raster or four-class map. H10 previously exercised installed unsupervised_classification, contradicting this capability claim. Diagnostic explicit tool retry follows. Evidence T6_unsupported_claim.jpg.

T6 tool-specific diagnostic PASS: generated smoke_image_classified, paletted Classes 1–4 with distinct green/orange/purple/pink. Statistical-cluster explanation correctly avoids land-cover assignment, but invents Damascus study area (actual Amman). Tester preserved temporary raster as outputs/T6_classified.tif; source project still references temporary file.

### T7 — PASS
Exact natural-language prompt created five violet-ring points; independent original geometry comparison unchanged, displacements 103.0244, 23.6068, 174.0020, 187.6917, 178.3594 m, all <=200m. Original remains visible, reply explicitly advises hiding original for sharing. Tester saved scratch layer via Make Permanent to outputs/T7_obfuscated.gpkg. Evidence T7_violet_rings.jpg, T7_verification.json.

### J1 — PASS computation; wording incomplete
Read-only import_jiaf_inputs reports HXL, four units, eight sectors, zero issues. Sector PiN sums food2980 WASH2670 health1690 education1210 CCCM1050 protection950 shelter660 nutrition570. Reply says support for JIAF2 analytical process, no endorsement of figures, but does not explicitly state not OCHA/IASC endorsed. Evidence J1_HXL_four_units.jpg and J1_sector_totals.jpg.

### J2 — PASS match
Three map districts matched, OUTSIDE_AREA explicitly unmatched, no map units missing data. No silent drop. Evidence J2_matched_unmatched.jpg.

### J3 — FAIL: explicit setup values replaced
Exact sheet prompt specified Smokeland, cycle 2026, admin 2, July 2024, and scope not endorsed. Confirmation recorded Syria and Damascus Region instead. Show the JIAF set-up returned Damascus Region and HCT Endorsed Scope: Not recorded / Unknown, rather than the explicit not-endorsed value. Governance/OCHA/IASC disclaimer was present. Evidence: J3_wrong_country.jpg and J3_setup_readback.jpg.

### J4 — field confirmation PASS; required reply FAIL
Cancel left all jf_ fields absent (J4_cancel_verification.json). Repeating and Apply added expected values: District_1 PIN500 severity3 flags0/0; District_2 PIN1800 severity5 flags2/2; District_3 PIN600 severityNULL flags1/0. The chat stopped at Confirmed & executed, with no required national 3020, phase5 immediate notice or District_3 lower-bound explanation after 10s. Old APPLY INFORM plan resurfaced in JIAF chat. Evidence J4_confirmation.jpg, J4_cancel.jpg, J4_applied_no_summary.jpg, J4_apply_verification.json.

### J5 — FAIL exact prompt; explicit recovery PASS
Show the JIAF severity on the map routed to Map drought severity / Which hazard specifically? Explicit jf_pre_sev humanitarian look recovered orange3, darkred5, greyNULL, polygons above rasters. Saved RuleRenderer contains 1 None/minimal through 5 Catastrophic and ELSE No severity (not assessed or incomplete sector coverage). J5_wrong_drought_question.jpg, J5_explicit_recovery.jpg, J5_renderer.xml.
### J6 — FAIL required lower-bound explanation
Correct jf_pre_pin selected and all three districts drawn, but no District_3 lower-bound note. Reply says 500 to <600 and 600 to1800 whereas District_3=600 appears pale with District_1. J6_PIN_map.jpg.
### J7 — substantive explanation PASS; plain wording incomplete
Explained District_3 incomplete sector coverage / not assessed and explicitly not phase1 or safe. Uses technical terms NULL, field name and inter-sectoral score. J7_missing_sector_explanation.jpg.

### J9 — FAIL explanation; total/notice PASS
Read-only finalize returned provisional2900, provisional component2400, pendingDistrict_2/3, phase5 immediateHCT notice. However table invented District_4 acceptedphase3 and falsely gave District_1 phase2 (actual3). J9_final_total.jpg/J9_final_invented_district4.jpg.
### J8 — numerical explanation PASS; presentation defects
Explained3020 preliminary,2300 worksheet,2900 final: Outside_area120 phase2excluded;District_3 600 provisionallyincluded, flagged2400awaitsreview. Displayed people counts with erroneous dollar suffixes. J8_total_comparison.jpg.
### J10 — rationale storage/refusal PASS; required tool-role note absent
RecordedDistrict_2 health/newerhealthsurvey/working session12October; reply did not explicitly say tool onlyrecords/notdecides. SeparateDistrict_3 decisionwithoutreason rejected, Nothing was saved. J10_recorded_decision.jpg/J10_no_rationale_refused.jpg.
### J11 — PASS
Bulkcloseflag1askedforrationaleanddecisionmaker; not applied. J11_bulk_rationale_required.jpg.

### J12 — PASS
Confirmation named5final/reviewfields. Apply wroteDistrict_1 PIN500 severity3 status0/1;District_2 PIN700 severityNULL PINrank4 status2/3;District_3 PIN600 severityNULL status3/4. ShortreviewrequestproducedDistrict_3redPending,District_2greenDecided,District_1blueNoFlag. Saved readableRuleRenderer. J12_confirmation.jpg,J12_review_map.jpg,J12_field_verification.json,J12_renderer.xml.
### J13 — FAIL exact prompt; explicit-path recovery PASS with wording issue
Show me the JIAF patterns attempted invented paths repeatedly,20toolcalls thenlimit. ProvidingexactCSV recovered10sections,District_2fourlargePiNsectors/sixsevere,sectors/counts/discussiondisclaimer. Pattern9prose saysDistrict_3preliminaryphasebelow4 althoughNULL; no national severity. J13_repeated_tool_failures.jpg,J13_invented_paths_limit.jpg,J13_patterns_recovery.txt.
### J14 — no official claim PASS; threshold confirmation not explicit
PlainNo,notcompliant/notofficial,notendorsed/notmethod/exploratorydiscussion/consensusrequired. Noexplicitthreshold/rulesteamconfirmation. J14_not_official.jpg.
### J15 — FAIL
LengthysectionswithFlags2/3ratherthan2–3plainsentences. IncorrectlyclaimedpreliminaryDistrict_2FoodSecurity1200(actual1800),correcthealthdecision700. No datatoolranwarning. J15_manager_explanation_failure.jpg.
### J16 — FAIL exact prompt
Make a map of the JIAF severity for the report routedMapdroughtseverity/Whichhazard? No layout. J16_wrong_drought_question.jpg.


### Provider blocker and J17 persistence — 2026-10-09
HTTP402 RESOURCE_EXHAUSTED at J16 recovery: prepayment credits depleted. No layout/PDF produced. Native save/close/reopen preserved current review look and chat. QGIS About independently confirms4.2.3. Evidence provider_402_credit_depleted.jpg, J17_reopened_review_map.jpg, QGIS_4_2_3_about.jpg, J17_persistence_verification.json.

### Credit top-up recheck — 2026-10-09 12:26 local
After the user reported adding credit, the live QGIS Cartogen panel was tested with the no-tool prompt `Reply with exactly CREDIT_OK and do not use any tool.` Google Gemini (Hosted) again returned HTTP 402 `RESOURCE_EXHAUSTED` with `Your prepayment credits are depleted.` No provider-dependent smoke row could be resumed, and the saved JIAF project was left unchanged. Evidence: `screenshots/provider_402_after_credit_topup_2026-10-09.jpg`.

### Provider recovered and execution resumed — 2026-10-09 12:28 onward
A repeated no-tool health check returned `CREDIT_OK`. J16 recovery applied the `jf_pre_sev` humanitarian look, created `Layout_J16_JIAF_Report`, and exported `outputs/J16_JIAF_Report.pdf`. The PDF is structurally valid (one-page A4 landscape, QGIS 4.2.3 producer), but it fails the row because the title is `J16_JIAF_Report`, the required non-endorsement note is absent, and the legend includes unrelated layers with a clipped final entry. N7 then passed in a fresh project: five 500 m buffers were created with the exact layer name `smoke_points_buffer_500m`. Evidence: `screenshots/provider_credit_restored_2026-10-09.jpg`, `screenshots/J16_pdf_exported_2026-10-09.jpg`, `screenshots/J16_JIAF_Report_page1.png`, `outputs/J16_JIAF_Report.pdf`, and `screenshots/N7_exact_buffer_name_pass.jpg`.

R5 passed on the same temporary buffer: `Save the project.` saved the QGIS project and explicitly named `smoke_points_buffer_500m` as a temporary in-memory layer whose data will not persist after close/reopen unless exported. Evidence: `screenshots/R5_temporary_layer_warning_pass.jpg`.

N8 failed output verification: Cartogen created `Layout_Smoke_Test_Layout`, displayed the exact title `Smoke Test Layout`, and claimed export to `outputs/smoke_layout.pdf`. No new `smoke_layout.pdf` existed anywhere under the RC22 run after completion. Evidence: `screenshots/N8_layout_export_pass_2026-10-09.jpg`.

N9 failed output verification after strong partial success: the local four-step plan ran without a web-mapping diversion or no-data warning; five buffers were clipped, every step displayed `Completed`, and project memory recorded `buffer_distance=250 meters`. No `plan_rc18.gpkg` existed anywhere under the RC22 run after the claimed export. Evidence: `screenshots/N9_plan_workflow_pass_2026-10-09.jpg`.

A11 passed: the Viridis legend appeared immediately after the single ramp tool call and the response reported the actual 35.0-214.0 range. R4 shares that successful apply/range component and the project was saved, but its required reopen check remains pending. A12 passed its observational requirement: `Layout_Test` was created and reported nine legend layers including rasters, confirming that off-map `smoke_dem` still appears. Evidence: `screenshots/A11_R4_ramp_35_214_immediate_2026-10-09.jpg`, `screenshots/A12_layout_legend_includes_rasters_2026-10-09.jpg`.

N3 failed at its first requirement. No overwrite confirmation card appeared; the response claimed that five features were exported, but both prepared non-empty sentinel CSVs remained byte-for-byte unchanged. The test stopped because the required Cancel/Apply branch was never offered. Evidence: `screenshots/N3_false_export_no_overwrite_prompt_2026-10-09.jpg`.

R4 passed after the confirmed scratch-layer discard and reopen. The Viridis renderer remained visible, and independent QGZ inspection found `singlebandpseudocolor` with `classificationMin=35`, `classificationMax=214`, and endpoints labelled 35.00/214.00. Evidence: `screenshots/R4_ramp_persisted_after_reopen_2026-10-09.jpg`.
