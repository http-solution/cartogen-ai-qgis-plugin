# Cartogen AI RC18 live smoke test — 2026-10-06

Status: IN PROGRESS. User installed RC18 and authorized proceeding; Plugin Manager verified 1.16.0-RC18 (01_verified_rc18.png). QGIS was closed and relaunched through native UI before functional tests.

- QGIS 4.2.3 launched through native UI.
- Initial pre-install observation was RC17. After the user installed RC18, Plugin Manager showed one enabled RC18 entry. Evidence: ../screenshots/01_verified_rc18.png.
- RC18 ZIP: E:\Cartogen-AI-QGIS-Plugin\Smoke test\cartogen_ai_v1.16.0-rc18.zip.
- ZIP metadata: Cartogen AI, version 1.16.0-rc18, QGIS minimum 4.2, maximum 4.99.
- SHA-256: 1F32B70DBF78E8347F128C955450C5E1B524AD3738C4A16AE58209B876777718. No published checksum file found locally; no published-checksum match claimed.
- Installation was performed by the user; the staged ZIP dialog is historical setup evidence only. Installed RC18 was independently verified before this run.
- Complete RC18 inputs copied into this dedicated writable run folder, preserving smoke_start.qgz relative data sources. Includes IPC, INFORM, UNOSAT and JIAF HXL fixtures.
- Existing profile will be used. Fresh installation, stable-release upgrade, two restarts and uninstall/reinstall gates are not yet certified.
- Applicable run sheet: sibling RC18 cartogen-ai/docs/SMOKE_RUN_SHEET_rc18_2026-10-06.md, plus RELEASE_LIVE_TEST_SCENARIOS.md. Expanded sheet includes R1–R7, N1–N9, K1–K5, V/T/J feature tests and P readability tests.
- Yemen project path and availability of a non-GIS colleague for the mandated 10-second readability test requested; supplied-fixture testing can proceed independently after installation.
- No plugin/profile folders were deleted and no security settings changed.

Remaining: finish the independently available expanded live test rows and verify produced artifacts. Record unavailable Yemen, external database and human-readability prerequisites honestly rather than certifying them from AI inspection.

## Live observations

- Existing profile, Google Gemini (Hosted), gemini-flash-latest. Default startup log: plan_validation_gate=ON, egress_gate_mode=off, persist_chat=ON. User added OSM Standard basemap during setup, giving eight actual layers (seven synthetic fixtures plus OSM). Historical notes were visible in Memory; these were preserved. No dedicated New Chat control found in dock/Memory; initial R1 used blank restarted chat, subsequent rows currently share the session. This limits exact NEW CHAT compliance until isolated project sessions are prepared.
- R1 core PASS: exact layer-list prompt returned all eight actual layers, five points, three hubs/admin/zones, one boundary, original EPSG:32636; OSM EPSG:3857 correctly distinguished. get_layers done 0 ms at 21:11:37. R1_layer_list.png and agent_early.txt.
- R2 first confirmation FAIL: after task 21.19 preview, reply "Yes, proceed." produced no tool call and said no pending operation. R2_confirmation_lost.png. Reposted original request, replied exactly "Yes": optimal_hub_siting done 62 ms at 21:14:56, correct Hub_A 886.49 / Hub_B 1035.21 / Hub_C 1621.51 m, no facility question or false general-knowledge footnote. Core retry PASS; original confirmation failure retained.
- R3 preview FAIL: exact imagery prompt routed to task 19.02 (OSM/crowdsourced buildings), inserted latest low-cloud scene assumption and MD report output override. Original imagery request remained in message. R3_wrong_OSM_preview.png. Confirmed with exactly "Yes" to test actual tool execution; result pending.
- V7 partial: Help top shows version rc18 and What's new; task registry count shown 792 across 36 sections. Remaining Help listing/NEW marks not yet assessed. V7_help_rc18.png.

### R3 completed observation
FAIL: extract_features_from_imagery failed after 356828 ms with HTTP 416 while acquiring the FastSAM checkpoint. No actual detections were produced. QGIS remained responsive during the wait. Stop showed Stopping, and the refiner's unrelated MD output contract automatically requested a spatial report after the agent was stopped. The unwanted follow-up was cancelled using QGIS's active-task cancellation dialog. The session was saved as outputs/early_regressions.qgz. Screenshots R3_failed_after_stop_auto_report.png and log agent_R3_failure.txt preserve the evidence.

Opened untouched isolated/regressions/inputs/smoke_start.qgz afterward; the visible chat reset successfully and the original seven fixture layers loaded.

### R4 and R5
R4 core PASS: apply_raster_stretch ran in 77 ms without a data-standards preview. Spectral multicolour ramp and range 35–214 survived native save/reopen in outputs/regressions.qgz. Visual issue: the Layers panel remained grayscale until the subsequent auto_arrange_layer_order refreshed it; screenshots preserve both states.
R5 PASS for the run-sheet requirement: Save the project named smoke_points_buffer_500m as a temporary in-memory layer and explained that its contents would not persist after reopen. Native QGIS also warned of temporary scratch data loss. Reopening was cancelled to preserve the data, then native Make Permanent saved the test buffer to outputs/buffer_500_preserved.gpkg for independent geometry verification. This preservation step occurred after the R5 observation and is not evidence of automatic persistence.
N7 naming core PASS as a companion check: buffer_analysis created smoke_points_buffer_500m exactly and five visible buffers, followed by auto_arrange_layer_order. This turn used the existing R4 chat, so its NEW CHAT condition has not yet been rerun.

### R6, R7 and N8 companion
R6 PASS: project CRS was changed through native QGIS to EPSG:4326. The exact coordinate request produced a CRS clarification. Reply EPSG:3857 triggered add_point_layer (46 ms), added one feature and computed approximately 44.036026 E, 15.958454 N. New Points was preserved afterward as outputs/coordinate_point.gpkg. The pre-clarification add_point_layer attempt also appeared in the log; the final feature is independently checkable.
R7 PASS: a layout focused on the one-feature New Points layer exported as single_point_rc18.pdf, visually rendered and inspected with valid scale 1:20,810 and no Invalid scale message. Extra defect: its legend still includes smoke_dem outside the visible extent, despite asking to use only New Points.
N8 companion core PASS: Smoke Test Layout exact title and outputs/smoke_layout.pdf exact path, real one-page PDF visually rendered and inspected. Valid scale 1:16,437. This turn was in the current regression chat rather than NEW CHAT. The canvas changed after creation, but the PDF preserved the requested current single-point view. Legend includes the off-map DEM.

### N1 / N2
PASS for both required functional checks. In a fresh project/chat, Estimate flood exposure for the area asked a question. Without answering, the exact severity_rc18 request produced a new severity confirmation card and no OSM question or Details attachment. Apply edit executed calculation and displayed Continuing with the rest of your request, followed by apply_humanitarian_look (46 ms). Correct scores: District_1 0, District_2 0.7857, District_3 0.75. Presentation defect: the image and DEM still obscured the styled administrative polygons; toggling both off manually revealed the expected yellow/red map. Evidence N1_unanswered_flood.png, N1_severity_new_request_card.png, N2_styled_but_raster_obscures.png, N2_revealed_severity.png. Saved project outputs/fixes_severity.qgz references the isolated/fixes inputs. Flood answer also suggested Syria despite the fixture boundary being in Jordan; treat that suggestion as unverified.

### N3
PASS in fresh n3.qgz chat. A synthetic pre-existing CSV had SHA256 363E5AFC04593D5650C50A59C636F94FB201AC14140523686B1252A5BBDA25A5. Export presented a replacement card; Cancel explicitly reported Cancelled Task 2 and left the hash unchanged. Repeated export again showed confirmation; Apply completed with feature count 5 and the CSV contains all fixture values and X/Y geometry columns. Immediate same-file export then completed silently, as rc18 expects. Evidence screenshots N3_overwrite_card.png, N3_cancelled.png, N3_applied.png, N3_immediate_silent_export.png and tool-status log agent_through_N3.txt. Each export also made an unnecessary one-step plan and repeated the export tool before updating the task; this overhead did not violate the overwrite checks.

### N4 — PASS core search; preview-link rendering defect
Fresh n4.qgz reset visible chat. Exact run-sheet request called search_stac_satellite_imagery as the fifth tool call (1750 ms), after create_plan, get_layers, get_attributes and recommend_visualization_method. Five dated Sentinel-2 rows remain in the answer with cloud percentages and TCI links; no “Table removed”. Thumbnail links render as literal malformed Markdown with a document icon and preview.jpg rather than usable preview labels. Existing CSV plan remains visible across project change alongside the new STAC plan; no extra CSV execution occurred. Evidence: N4_completed.png, N4_scene_table.png, agent_through_N4.txt; saved n4.qgz.


### N4/N5 extent verification correction — FAIL geographic correctness
Independent read-only fixture verification found smoke_boundary EPSG:32636 bounds 775482.5306198237,3537606.55004007–778876.1935027302,3540801.64432782. Installed GDAL gdaltransform converted all four corners to a WGS84 bounding envelope [south,west,north,east] approximately [31.9401917668625,35.9141156995706,31.9698086420047,35.9508951918742] (Jordan). Saved N4 answer instead says Damascus Region and [west,south,east,north]=[36.20,33.45,36.35,33.55]. Thus N4 passes the narrow fifth-call/table-retention check but FAILS the requested extent transformation and overall geographic correctness. Historical Damascus profile memory was present, but causation cannot be proved from this run.

N5 exact prompt produced a task 1.03 preview with an invented MD-file requirement. After Yes, fetch_building_footprints failed first (5575 ms), then a retry completed in 69703 ms, creating Syria_building_footprints with 50 features. Answer describes Jordan returning zero and silently switching to Syria, using the same incorrect Damascus extent. Tool log marked the first attempt failed, so the prose zero-feature characterization is not independently established. The saved GeoJSON confirms 50 actual features; this is the wrong geography/country, not a successful Jordan fixture fetch. Auto-generated fake User follow-up requested generate_spatial_report, which ran despite no report-file request from the tester. Evidence: N5_wrong_report_preview.png, N5_wrong_extent_and_country.png, agent_through_N5.txt, N4_saved_chat.json, N5_saved_chat.json, outputs/N5_wrong_country_Syria.geojson. No rerun accepted as a replacement pass.

### Independent core output verification
core_geometry_verification.json confirms five persisted buffer polygons with radius 500 m (floating-point tolerance <1e-9 m), one coordinate point in EPSG:4326 at 44.03602608193214,15.958453945147442, and three severity_rc18 scores 0,0.7857,0.75. These are independent read-only output checks, not substitute live tool execution.

### N6 — PASS
Fresh n6.qgz, exact latest-stable-release prompt. gemini_grounded_search plus three search_web calls completed; answer correctly distinguishes stable feature release QGIS 4.2 (Changelog for QGIS 4.2, July 3, 2026) from October LTR scheduling news and current point version 4.2.3. Official title/date/source verified independently at https://qgis.org/project/visual-changelogs/visualchangelog42/. Well-formed source link visible. Evidence N6_current_release.png, agent_through_N6.txt, saved n6.qgz.

### N7 — PASS fresh-chat run
After restarting QGIS, untouched n7.qgz with blank chat ran exact named-buffer prompt. buffer_analysis done 110 ms, auto_arrange_layer_order done 61 ms. Native layer tree shows exact smoke_points_buffer_500m and five visible circles. Native Make Permanent preserved scratch layer as outputs/N7_fresh_buffer.gpkg before saving n7.qgz; preservation is tester evidence handling, not automatic persistence. N7_named_layer_confirmed.png and agent_N7_restart.txt. QGIS window closed during attempted coordinate-based window enlargement before this test; cause not established, not asserted as a plugin crash. Relaunched successfully; native accessible Maximize control subsequently worked.

### N8 — PASS fresh-chat title/path export
Untouched n8.qgz blank chat. Tester used native Zoom Full to set the current fixture view, then exact run-sheet prompt with absolute smoke_layout.pdf destination. Preview still maps to web task 28.15 (routing defect retained); Yes executes only create_print_layout (453 ms). Actual one-page 595264-byte PDF visually verified, exact Smoke Test Layout title/path, fixture current view, legend/north arrow/scalebar and valid scale 1:22,602. Right-edge coordinate labels partially overlap/clip against legend frame. Default fixture rasters obscure vectors, matching the prepared current view. Earlier single-point companion PDF preserved as companion_smoke_layout.pdf. Evidence N8_fresh_pdf_render.png, N8_fresh_pdf_response.png, agent_through_N8_restart.txt and saved n8.qgz.


### N9 — PASS core local plan (22:25–22:27)
Fresh n9 project/chat. Exact four-step prompt ran create_plan, buffer_analysis, clip, export and store_project_memory; all four steps displayed DONE. Actual plan_rc18.gpkg exists (98,304 bytes), five circles visible. Project memory buffer_distance = 250 meters reported. No web mapping routing or No Data warning. Extra auto_arrange_layer_order ran. Intermediate scratch layers preserved separately through native Make Permanent, then project saved. Evidence: N9_plan_progress.png, N9_completed.png, agent_through_N9.txt. Independent geometry and memory round-trip verification pending.
