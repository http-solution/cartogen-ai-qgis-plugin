# Cartogen AI RC17 live smoke test — 2026-10-06

Status: **COMPLETE — OVERALL FAIL** for the installed RC17 functional smoke run. Seven categories passed their core checks, eight failed a required subcheck, and PostGIS was skipped. This is a live test through normal QGIS chat and native UI, not a repository unit-test run or certification of all release lifecycle gates. Native task timestamps span approximately 02:13–03:09 on 2026-10-06.

## Candidate and environment

- Installed QGIS: 4.2.3, Windows; executable `C:\Program Files\QGIS 4.2.3\bin\qgis-bin.exe`.
- Plugin Manager shows one Cartogen AI entry, version **1.16.0-RC17**.
- Provider: Google Gemini (Hosted), `gemini-flash-latest`; existing profile, rewrite suggestions enabled.
- ZIP: `E:\Cartogen-AI-QGIS-Plugin\Smoke test\cartogen_ai_v1.16.0-rc17.zip`.
- Computed SHA-256: `BC59DF280230ADF6527485243E68A0672F66B6C08D964FEE8D273A0DA1BBCAE8`. Published checksum was not available locally; installed-file equivalence to ZIP not verified.
- Test root is this report's parent run directory, under the writable RC15 workspace. Folder name does not describe the installed version. RC17 fixture inputs were copied into this run directory.
- Existing profile used; fresh-profile, upgrade, uninstall/reinstall gates not performed. No disposable PostGIS connection supplied.
- RC17 admin fixture already has `severity_smoke`; A4 uses fresh field `severity_rc17` to test the absent-field confirmation gate.
- Runbook: RC17 `SMOKE_RUN_SHEET_rc17_2026-10-06.md` and `RELEASE_LIVE_TEST_SCENARIOS.md`.

## Seven RC17 regression rows

| Row | Result | Live observation | Evidence in ../screenshots |
|---|---|---|---|
| R1 layer list | PASS | Exact prompt returned all seven real fixture layers, counts, CRS and fields. Activity and Agent log show `get_layers` success. | R1_real_layer_list.png; R1_get_layers_activity.png |
| R2 hub ranking | Core ranking PASS; additional defects | Exact prompt asked facility type twice. Synthetic supply hubs was not accepted; health clinics was accepted. Correct spatial-analysis task 21.19, no OSM task. `optimal_hub_siting` ran once successfully. Hub_A 886.49 m, Hub_B 1035.21 m, Hub_C 1621.51 m; Hub_A wins. Response incorrectly appends “Not from a tool result… model's general knowledge”. It also calls these Euclidean distances; numerical difference from planar baseline is consistent with tool ellipsoidal measurement. | R2_repeated_facility_question.png; R2_ranked_table.png; R2_tool_success.png; R2_result_warning.png |
| R3 imagery routing/error cleanup | Cleanup PASS; extraction FAIL | Exact prompt reached `extract_features_from_imagery` without OSM preview. FastSAM-s.pt checkpoint download failed HTTP 416, URL replaced by `<url removed>`, useful explanation supplied. QGIS showed Not Responding during download. Agent log reports CRITICAL ToolError after 43063 ms; whole task 48890 ms. No inference/detection count was established; response's 0 is accompanied by “Extraction could not be completed”. | R3_not_responding.png; R3_clean_error.png; R3_failed_tool.png |
| R4 raster save/reopen | PASS with preview defect | Applied multicolour ramp to smoke_dem, band 1, 35–214. Initial refiner incorrectly matched data-standards task 29.05; corrected confirmation constrained original styling. `apply_raster_stretch` succeeded. Saved XML classificationMin=35, classificationMax=214. Reopened through plugin confirmation, legend remains 35–214. | R4_wrong_refiner.png; R4_ramp_before_save.png; R4_reopened_valid_legend.png |
| R5 temporary-layer save warning | PASS | With live temporary buffer present, exact “Save the project.” named smoke_points_buffer_500 and explicitly warned that it reopens empty; recommends exporting data. On reopen polygons disappeared while memory layer entry remained, matching warning. | R5_exact_save_warning.png; R5_save_as_memory_warning.png; R4_reopened_valid_legend.png |
| R6 CRS clarification | FAIL; explicit retry PASS | In EPSG:4326 project, exact point prompt correctly asked CRS. Reply EPSG:3857 caused no tool call and claimed add_point_layer unavailable. Full explicit retry created a point in EPSG:3857 while project stayed EPSG:4326. | R6_crs_clarification.png; R6_followup_no_tool.png; R6_explicit_retry_created_point.png |
| R7 single-point layout scale | PASS | `create_print_layout` produced real PDF with one point, title, legend, north arrow, scalebar and valid Scale 1:20,808. PDF visually rendered and inspected; no Invalid scale. | R7_single_point_layout.png; R7_single_point_pdf.png; ../outputs/single_point_layout.pdf |

## Functional observations

- A1: buffer_analysis and auto_arrange_layer_order succeeded; five visible buffers for the 500 m request. Requested name smoke_points_buffer_500m became smoke_points_buffer_500 (name mismatch). Radius was not independently measured before memory features were lost on reopen. Evidence A1_buffer_canvas.png.
- A4: natural-language severity request incorrectly routed to an OSM/online-data question. After restriction to local tools, a confirmation targeted historical severity_smoke rather than fresh severity_rc17; cancelled before mutation. Explicit new tool request produced the correct confirmation and persisted scores (0, 0.7857, 0.75). Apply edit did not continue the requested graduated styling; singleSymbol renderer remained. FAIL. Evidence A4_unrelated_OSM_question.png, A4_wrong_field_preview.png, A4_correct_field_preview.png, A4_applied_no_style_continuation.png.
- A5: categorical zone_type styling produced three real legend classes and visibly distinct colours; boundary label showed Smoke Area after apply_labels. Final saved/reopened project preserves categorizedSymbol, mixed/urban/open categories and admin_name labeling. XML has obstacle=1, obstacleType=1, obstacleFactor=1. Evidence A5_categorical_canvas.png, A5_boundary_label.png, A5_zones_after_roundtrip.png and artifact_verification.json.
- A6: CSV export contains five exact fixture rows and all attributes. Repeat request explicitly asking for an overwrite preview replaced the existing disposable CSV without confirmation. FAIL overwrite subcheck. Unicode/formula-like inputs were not present in the shipped fixture, so those subchecks remain unexercised. Evidence A6_csv_export.png, A6_overwrite_without_preview.png.
- A7: initial refiner claimed a dataset override despite explicit PDF request; execution used historical title Smoke Test Severity Map and smoke_map.pdf rather than requested title/path. Explicit retry created the correct smoke_layout.pdf. Both PDFs rendered and inspected: real nonblank maps, legend, north arrow and valid scale. Initial scenario FAIL; retry core PASS. Evidence A7_wrong_dataset_override.png, A7_wrong_title_and_path.png, A7_exact_retry_pdf.png, A7_correct_pdf.png.
- B1: after confirming footprint-only scope, 14 tool calls created/reprojected/exported/loaded unrelated data and added test_pt; unrelated point labels appeared. No fetch_building_footprints call or genuine building layer. Agent stopped manually after visible deviation, plan remained 0/3 DONE. FAIL. Evidence B1_wrong_report_override.png, B1_unrelated_layers.png, B1_stopped_14_wrong_tools.png. No user data were used; all mutations were in the disposable fixture project/output folder.
- B3: 15 tool calls included unrelated failing SQL, spatial reports, severity, web/grounded search; eventually search_stac_satellite_imagery ran successfully at 02:51:45–46 (1578 ms). Operator pressed Stop after the unrelated sequence; a final answer still arrived. It claimed five scenes but replaced metadata with “Table removed: no tool produced it in this turn” and a contradictory “No data was retrieved” warning. Actual IDs, dates, clouds and asset links were absent. Output FAIL; STAC result content cannot be independently certified from that response. Evidence B3_metadata_table_removed.png and Agent log.
- B4 PDF PASS and Word PASS separately: one extraction call per format, one table, headers id/value and exact ordered rows A01/10, A02/20, A03/30. Independently checked source documents. Evidence B4_pdf_exact_rows.png, B4_docx_exact_rows.png.
- B5 FAIL required-tool/latest subchecks: Activity shows two gemini_grounded_search calls and no search_web for this request. It returned QGIS 4.0, March 9, 2026, as latest. The cited [official article](https://blog.qgis.org/2026/03/09/qgis-4-0-norrkoping-is-released/) opens and confirms that date/title, but the [official QGIS 4.2 announcement/changelog](https://qgis.org/project/visual-changelogs/visualchangelog42/) states release date July 3, 2026. Thus the citation is real while the latest-release claim is stale. Evidence B5_grounded_search_stale_release.png.
- C3: actual saved project exists; first load confirmation cancelled, canvas/buffers remained. Repeated request produced fresh confirmation; Apply edit loaded project, restored saved conversation and valid raster style. Evidence C3_load_preview.png, C3_load_cancelled.png, R4_reopened_valid_legend.png.
- C1: saved/loaded unique preset smoke_admin_severity_rc17 (avoids overwriting prior RC15 preset). Exactly one calculate_severity_index step, population/need, admin_name, no output field; default equal weights. Started 1-minute/max-2 timer and observed real first/second check at 02:56/02:57. It stopped automatically at max_runs before first cancellation request; list showed none. A separate reschedule/list/immediate-stop/list sequence then successfully cancelled an active timer before its first tick and returned empty list. After project reload and Cartogen dock close/reopen, list_scheduled_workflows again showed count 0 at 03:09. Plugin menu showed one Cartogen action. This was a dock reopen, not a QGIS process restart. Evidence C1_preset_saved_loaded.png, C1_timer_active.png, C1_real_first_tick.png, C1_real_second_tick.png, C1_auto_stop_none_active.png, C1_active_cancelled_none.png, C1_single_plugin_menu_action.png, C1_no_orphan_after_dock_reopen.png.
- C5: safe execute_pyqgis_script returned actual EPSG:32636 and 11 loaded layer names, matching GUI. Prohibited import os/os.system request reached the scripting tool and was rejected before execution. A second explicitly confirmed request was still rejected with the same blocked-import validation message. Disposable target absent in independent filesystem check. This certifies the tested forbidden import, not every possible sandbox escape. Evidence C5_safe_script_result.png, C5_os_import_rejected.png, C5_confirmation_still_rejected.png.

## Sanitized log evidence

`agent_gui_log.txt` is an accessible-text excerpt copied from the native QGIS Agent log, ending mid-entry at 02:54:06 because UI text capture was capped. It is not the complete run log. Captured entries contain tool names, timestamps, statuses, correlation IDs and durations without coordinates or raw prompts/scripts. Later operations are evidenced by screenshots, Activity cards, saved artifacts and `task_runner_gui_log.txt`, which includes final completion at 03:09:59. Full-run log privacy cannot be certified from this excerpt. Default CartogenAI channel showed two identical startup lines: plan_validation_gate=ON, egress_gate_mode=off, persist_chat=ON (cartogen_default_log.png). Duplicate startup lines do not establish duplicate UI instances; Plugin Manager has one entry.

Key failure:

```text
2026-10-06T02:26:48 INFO tool_call tool=extract_features_from_imagery status=running correlation_id=faf75209 provider=GeminiClient
2026-10-06T02:27:31 CRITICAL tool_call tool=extract_features_from_imagery status=failed duration_ms=43063 correlation_id=faf75209 provider=GeminiClient error_class=ToolError
```

## Coverage limits

No result here certifies fresh installation, upgrade migration, duplicate-action absence after restarts, or uninstall/reinstall. The existing installed version was verified and used. These gates remain untested, and an overall release PASS must not be inferred from the seven regression rows.

## Sixteen-category disposition

PASS below means the tested core behavior passed; associated routing or answer defects remain recorded above. Explicit retries do not erase failures of the original scenario.

| Category | Result | Basis |
|---|---|---|
| 1 Vector | FAIL | A1 requested buffer layer name changed; C4 independently validates 250 m geometry. |
| 2 Raster | PASS | R4/A2 finite 35–214 ramp persisted; varied DEM renders and visibility toggles work. |
| 3 Humanitarian data | FAIL | B1 never fetched footprints; unrelated 14-tool sequence stopped. |
| 4 Logistics | PASS, core | R2 correct three-hub ranking; clarification/provenance defects remain. |
| 5 Analysis | FAIL | A4 wrong field proposed, then graduated styling omitted after explicit retry. |
| 6 Styling | PASS | A5 real categories and boundary label persisted after reload. |
| 7 Imagery | FAIL | R3 checkpoint HTTP 416 and approximately 43-second UI stall; no extraction result. |
| 8 Satellite | FAIL | B3 successful STAC call followed by missing metadata table and contradictory warning. |
| 9 Monitoring | PASS | C1 real two timer ticks, auto-stop, explicit active cancellation and empty list after dock reopen. |
| 10 Database | SKIP | No disposable PostGIS database supplied. B3 SQL failures do not substitute for this test. |
| 11 Export | FAIL | A6 correct five-row CSV, but explicit overwrite-preview request ignored. |
| 12 Layout | FAIL | A7 initial title/path wrong; explicit retry and R7 single-point layout passed. |
| 13 Documents | PASS | PDF and DOCX extracted separately, exact headers and all three rows. |
| 14 Project | PASS, core | C3 cancel/load/save/reload, styles, layouts and chat restoration verified in existing profile. |
| 15 Task and memory | PASS, core | C4 reviewed four-step plan completed, durable GPKG and 250 m memory persisted. |
| 16 System, search and scripting | FAIL | B5 stale latest-release claim/required search tool missing; C5 safe and blocked scripting checks passed. |

## Final persistence and independent verification

- A2: reopened DEM shows spatial variation; checkbox off/on removes/restores it. Evidence A2_reopened_dem_variation.png, A2_dem_toggled_off.png, A2_dem_toggled_on.png.
- C4: initial refiner incorrectly proposed web-mapping task 28.15. Full local-only clarification produced an ordered four-step TODO plan before editing. Following approval, buffer, clip, exact-path GeoPackage export and project-memory store completed; all four steps marked DONE. An unrelated “No data was retrieved” warning appeared on plan metadata. Evidence C4_wrong_refiner_task.png, C4_ordered_plan_before_edit.png, C4_real_export_completed.png, C4_four_completed_steps.png.
- Independent read-only SQLite/WKB checks of smoke_plan_result.gpkg find five features, EPSG:32636, all vertices inside the boundary, and measured buffer vertex distances 249.99999999986–250.00000000018 m. This certifies C4's 250 m result, not A1's earlier 500 m geometry.
- Final smoke_roundtrip.qgz contains 13 layer definitions, original fixture layers plus disposable memory results from the test. The seven original spatial fixtures remain present. Saved zones renderer, boundary label, DEM limits and both layout definitions were independently read from project XML. Layout Manager has one requested Layout_Smoke_Test_Layout and one distinct Layout_Smoke_Test_Severity_Map from the failed initial attempt; no duplicate requested layout entry. Evidence A7_layout_manager_after_reopen.png.
- Final plugin save and reviewed native load confirmation actually reloaded the project and restored conversation/style/layout state. The requested 250 m memory note appeared after reload; saved project memory independently contains the same value. Evidence C3_final_saved_state.png, C3_final_load_proposal.png, C3_final_native_load_preview.png, C3_final_reopened_state.png, C4_memory_250_after_reopen.png.
- Memory layers reopen empty as expected; a QGZ layer definition does not preserve their geometry. The separate exported GPKG is the durable buffer/clip result. Initial R5 explicitly warned about emptiness; the later verbose save response only described memory-session status and referenced the durable export, so warning consistency across every save response is not established.
- Correct full layout PDF is 895346 bytes; single-point PDF is 102515 bytes. Both were rendered and visually inspected. CSV has five exact data rows with all fixture attributes and a UTF-8 BOM. No Unicode/formula-like fixture values were available for those export subchecks.
- Read-only verifier and detailed outputs: verify_artifacts.py and artifact_verification.json beside this report. Evidence manifest lists relative files, sizes and SHA-256 hashes.

## Defects to address before another release smoke pass

| ID | Observed defect | Reproduction/evidence |
|---|---|---|
| D01 | Refiner proposes unrelated tasks or stale context | R4 raster→data standards; A4 severity→OSM; A7 PDF→dataset; B1/B3→report; C4 plan→web mapping. Original scenario followed by full scope correction, screenshots listed above. |
| D02 | Valid tool data mislabeled as model knowledge or removed | R2 successful ranking receives false provenance disclaimer; B3 STAC metadata table removed; C4 plan gets unrelated no-data warning. |
| D03 | Imagery checkpoint failure stalls QGIS | R3 imagery extraction, HTTP 416, Not Responding and 43063 ms tool duration. |
| D04 | CRS clarification does not resume point creation | R6 projected coordinates 4902068,1799912 in EPSG:4326 project; answer EPSG:3857 produces no tool call. Full new request succeeds. |
| D05 | Severity field/context and continuation incorrect | A4 fresh severity_rc17 requested; historical severity_smoke proposed. Explicit retry applies numeric values but omits requested graduated styling. |
| D06 | Explicit overwrite preview ignored | Repeat A6 CSV export to existing disposable output with preview-before-replace instruction; file overwritten without preview. |
| D07 | Layout uses historical title and output path | A7 Smoke Test Layout/smoke_layout.pdf request yields Smoke Test Severity Map/smoke_map.pdf; full new explicit request succeeds. |
| D08 | Footprint task executes unrelated mutations | B1 Jordan/Microsoft/limit-50 footprint-only request; no fetch_building_footprints in 14 calls, unrelated layers and exports. |
| D09 | Satellite search drifts and final metadata is unusable | B3 Sentinel/August 2026/limit-5 search; 15 calls with unrelated operations, eventual STAC success but scene IDs/date/cloud/assets absent. |
| D10 | Latest-release web response stale and required tool absent | B5 latest stable QGIS announcement request uses grounded_search twice, claims March 2026 QGIS 4.0 despite July 2026 QGIS 4.2 announcement. |
| D11 | Buffer output name does not match request | A1 smoke_points_buffer_500m becomes smoke_points_buffer_500. |
| D12 | Repeated hub clarification despite synthetic inputs | R2 facility type asked twice; synthetic supply-hub answer not accepted, health-clinic answer proceeds. |

These are observations from this run, not a multi-run reproducibility study. Successful explicit retries are documented separately to show available core functionality.

## End state

No scheduled workflows remain active after the final dock reopen check. QGIS remains open with the disposable smoke project. Test outputs and failure layers are retained as evidence; installed plugin files and security settings were not changed. Fresh-profile/upgrade/two-process-restart/uninstall gates remain untested. Network/provider configuration beyond the visible hosted Gemini setting was not independently audited. Screenshot evidence contains fixture coordinates and chat text; the sanitized-log observation applies only to the captured native log excerpt.
