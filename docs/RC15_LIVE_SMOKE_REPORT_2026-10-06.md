# Installed RC15 live smoke rerun — 6 October 2026

**Overall: FAIL. Do not treat this installed-profile run as stable-release approval.**

The real QGIS desktop and installed Cartogen AI chat were used. No repository tool imports or headless QGIS calls substituted for the live tests. Successful artifacts were inspected independently afterward. Fifteen functional categories were exercised; PostGIS was skipped. Several local operations worked, but routing, result accuracy, workflow continuation, imagery responsiveness, and project persistence failed.

## Environment and scope

- QGIS Desktop **4.2.3**, Windows, existing **default** profile.
- Enabled plugin version **1.16.0-RC15**, confirmed in Plugin Manager; screenshot `00_installed_rc15.png`. Plugin Manager listed two Cartogen AI entries, with only the first enabled. The disabled entry's version was not inspected.
- Provider: existing **Google Gemini (Hosted)**, automatic model; activity reported `gemini-flash-latest`.
- Run time: approximately 00:51–01:43 local time, Asia/Beirut, 2026-10-06.
- Candidate ZIP identity/SHA and installed-source equivalence: **not established**. This report identifies the installed version, not a publication ZIP.
- Runbooks: `cartogen-ai/docs/RELEASE_SMOKE_TEST.md` and `RELEASE_LIVE_TEST_SCENARIOS.md`.
- Test root: `E:/Cartogen-AI-QGIS-Plugin/Smoke test/cartogen_ai_v1.16.0-rc15/release_smoke_assets/run_rc15_2026-10-06`.
- Inputs copied from the available top-level `release_smoke_assets/inputs`. The seven spatial layers loaded; counts were points 5, hubs 3, boundary 1, zones 3, admin 3; both rasters 128×128. Spatial CRS EPSG:32636. Originals were not edited.
- The available admin fixture already contained `severity_smoke`; therefore the absent-field confirmation subcheck could not be established.
- Chat and project-note persistence were enabled. Prompt rewrite suggestions were temporarily disabled during diagnostic retries, then restored to their original checked state. Prompt/reasoning preview and plan validation remained enabled. No security/privacy setting was changed.
- Proxy/VPN state was not established. External imagery checkpoint download failed; this is recorded as an environment-dependent failure, not assumed to be an RC15-only regression.

### Interpretation of results

`CORE PASS*` means the requested artifact or behavior worked after manually resending the original prompt at an incorrect refinement preview. It is **not** a clean end-to-end PASS. `PARTIAL` means some required checks remain unverified. The shared routing defect affects multiple categories and must be repaired before repeating the normal workflow. This run does not provide a 16/16 release pass.

## Result sheet

Evidence filenames below are in `../screenshots/`.

| # | Category/scenario | Result | Tool or behavior observed | Verified result / limitation | Evidence / defect |
|---:|---|---|---|---|---|
| 1 | Vector A1 | PARTIAL / FAIL naming | `buffer_analysis`, auto arrangement; `get_layers` failed | Five visible polygons in metric CRS; source still five points. Output called `smoke_points_buffer_500`, missing requested `m`. 500 m radius was not independently measured. Memory geometries lost on reload. | A1_buffer.png; D02, D07 |
| 2 | Raster A2 | PARTIAL; persistence FAIL | `apply_raster_stretch` | Grayscale changed to Viridis, range 35–214. Saved XML has shader values 35–214 but classification min/max `nan`; reopened legend becomes nan. Full visibility-toggle test not completed. | A2_raster.png, C3_reloaded_lost_buffers.png; D08 |
| 3 | Humanitarian Data B1 | FAIL | 20-call limit; requested footprint fetch never appeared | No footprint artifact. Unrelated reports, dashboard, routing/analysis calls; plan showed DONE despite no requested dataset. | B1_tool_limit_failure.png; D01, D04 |
| 4 | Humanitarian Logistics A3 | FAIL | `optimal_hub_siting`, repeated highlighting; SQL/attributes/layers failures | Claimed Hub_A average 1,632.74 m; independent correct average 886.98 m. Three-candidate table suppressed. | A3_tools_and_winner.png, A3_failed_ranking.png; D03 |
| 5 | Data Analysis A4 | FAIL | `calculate_severity_index` confirmation applied | Severity preview/Apply edit worked; execution stopped after field operation. Requested graduated styling never occurred; saved admin renderer still singleSymbol. Existing field baseline limits write-gate conclusion. | A4_severity_preview.png, A4_confirmed_no_style.png; D01, D05 |
| 6 | Styling/Labeling A5 | CORE PASS* | Categorized style and labels | Three zone categories; visible `Smoke Area` label; categorized renderer and labels survived reload. Opaque admin polygons obscure much zone fill. | A5_style_label.png; D01 |
| 7 | Imagery Extraction B2 | FAIL | `extract_features_from_imagery` | FastSAM-s checkpoint download HTTP 416. QGIS Not Responding observed for approximately one minute, then recovered. No successful inference or truthful completed zero-result test. | B2_QGIS_not_responding.png, B2_checkpoint_download_failed.png; D06 |
| 8 | Satellite/STAC B3 | FAIL | STAC search appeared among 20 calls | No scene IDs/dates/cloud/asset result delivered. Unrelated buffers, change raster, CSV reload and layout/report operations mutated project. | B3_tool_limit_failure.png; D01, D04 |
| 9 | Scheduling C1 | CORE PASS*; reopen subcheck limited | Save/load preset, schedule/list/stop | Preset contained severity allowlisted step with no output field. Active at 0 runs, actual first tick at 01:21; responsive UI. Stop returned true and active list empty; no later tick observed through remaining run. Plugin restart/orphan test not independently run. | C1_preset.png, C1_tick_0121.png, C1_stopped.png; D01 |
| 10 | Database C2 | SKIP — no test DB | None | No disposable PostGIS database supplied; read-only enforcement not claimed. | — |
| 11 | CSV Export A6 | PARTIAL / primary artifact PASS* | `export_to_csv` | Real UTF-8 BOM CSV; five rows, all attributes plus X/Y/fid. Unicode/formula-like inputs and existing-file overwrite behavior not exercised. | A6_export.png, artifact_verification.json; D01 |
| 12 | Print Layout A7 | CORE PASS* | `create_print_layout` | Exactly one `Layout_Smoke_Test_Layout` immediately after A7; PDF rendered nonblank with title, map, legend, north arrow, scale bar. A later unrelated call added a second layout. | A7_layout_manager.png, A7_pdf_render.png; D01, D04 |
| 13 | PDF/Word Tables B4 | PASS | `extract_pdf_tables`, `extract_word_tables` | Both separately returned exact id/value headers and A01/10, A02/20, A03/30 in order. | B4_pdf_tables.png, B4_word_tables.png |
| 14 | Project C3 | FAIL persistence; confirmation PASS | `save_project`, `load_project` preview/Apply edit | Cancel kept canvas; approval reloaded saved project and chat. Names, labels, CRS and categorized style survived. Temporary buffer features disappeared and DEM legend degraded to nan. | C3_load_cancelled.png, C3_reloaded_lost_buffers.png; D07, D08 |
| 15 | Task/Memory C4 | PARTIAL / core artifact PASS* | Plan, PyQGIS scripts, task updates | 0/4 before approval, real export afterward, DONE claim; five 250 m polygons verified. Note recalled and visible in Memory panel after final-project reopen. Failed layer lookup, blocked os import and unavailable native buffer algorithm occurred before recovery. Every intermediate status/artifact was not captured. | C4_plan_before_approval.png, C4_plan_completed_warnings.png, C4_memory_after_reload.png; D01, D02, D09 |
| 16 | Web/Scripting B5+C5 | FAIL web; scripting checks PASS | Grounded Gemini search; `execute_pyqgis_script` | Web source link malformed; required `search_web` absent in B5. Safe script returned EPSG:32636 and 12 correct names. Prohibited import blocked twice, including confirmation retry; target file absent. Default CartogenAI GUI log contains only startup settings, no raw scripts/prompts/data. | B5_grounded_search.png, C5_safe_script_memory_recall.png, C5_os_import_blocked.png, C5_confirmation_cannot_bypass.png, C5_default_log.png; D10 |

## Defects and reproduction

All failures below were observed in this one run. Root cause and cross-profile reproducibility are unproven. D01 occurred repeatedly across different prompts. Screenshots preserve the visible activity and responses; raw provider internals were not available.

### D01 — Prompt refinement substitutes unrelated task contracts (high)

Local severity requests became Jordan OSM download or WorldPop service-area tasks. Layout, footprint and STAC prompts became export/report/acquisition tasks. C4 buffer/clip/memory plan was matched to task 28.15 web mapping and given only export tools. Requirement loops repeatedly requested facility/source/threshold slots unrelated to the original request, even after explicit local inputs.

Expected: retain the named tools, inputs, requested outputs and constraints. Actual: incorrect task enrichment, clarifications, misleading output contract and tool suggestions. Disabling rewrite suggestions did not stop matching. Diagnostic workaround: resend the exact original prompt as a preview edit; resulting core successes are qualified above.

Evidence: A3_refiner_wrong_task.png, A4_stale_OSM_prompt.png, A4_repeat_stale_OSM.png, A7_wrong_export_refinement.png, C1_requirement_loop.png.

### D02 — Basic context tools fail repeatedly (high)

`get_layers` repeatedly displayed “Execution failed unexpectedly.” Attribute and read-only SQL context retrieval also failed. Successful operations were followed by generic no-data warnings. Tool failure messages alone do not establish their source-level cause.

Evidence: A1_buffer.png, A3_tools_and_winner.png, B3_tool_limit_failure.png, C4_plan_completed_warnings.png.

### D03 — Incorrect hub distance and missing ranking table (high)

Prompt: “Use optimal_hub_siting to rank the three candidate locations in smoke_hubs by average straight-line distance to all five demand features in smoke_points. Tell me the winning hub name and each candidate's computed average distance; do not claim road-network routing or population weighting.”

The tool appeared, but final response claimed Hub_A 1,632.74 m and removed the candidate table with “no tool produced it in this turn.” Independent Euclidean calculation from the copied GeoPackage's EPSG:32636 coordinates:

| Candidate | Correct average meters |
|---|---:|
| Hub_A | 886.979311 |
| Hub_B | 1035.772977 |
| Hub_C | 1622.390701 |

Winner name correct; numerical response incorrect. Raw tool return was not captured, so the calculation tool versus narration fault is unresolved.

### D04 — Unrelated operations and false completion in network tasks (high)

B1 asked: “For Jordan, convert smoke_boundary's extent to WGS84 [south, west, north, east] and fetch up to 50 Microsoft building footprints inside it. Add the result to the project and report the actual feature count.” A diagnostic retry requested count in chat. No footprint fetch occurred; 20-call limit, unrelated operations and DONE plan instead.

B3 asked: “Transform smoke_boundary's extent to WGS84 [west, south, east, north] and call search_stac_satellite_imagery for Sentinel-2 scenes from 2026-08-01 through 2026-08-31, limit 5. Report actual IDs, dates, cloud cover, and available asset links.” It reached 20 calls with no delivered scene result. It added `change_detection_smoke_dem_vs_smoke_dem`, `smoke_boundary_buffer_1`, a second `smoke_points` from CSV, and an additional layout. These were outside the requested search scope.

### D05 — Confirmed severity edit does not continue to styling (high)

After the explicit severity confirmation preview, Apply edit displayed task completion but the requested graduated style did not run. Admin remained singleSymbol in the saved project. Field values were already present before this scenario, so this does not prove a fresh field was added or that baseline values changed.

### D06 — Imagery checkpoint failure freezes QGIS (high; environment-dependent)

Prompt: “Run extract_features_from_imagery on loaded raster smoke_image with confidence threshold 0.4. Report the model used and actual detection count; do not label synthetic shapes as real buildings.”

FastSAM-s download returned HTTP 416 Range Not Satisfiable. QGIS Not Responding persisted approximately one minute. Chat exposed a lengthy raw signed download URL. App recovered without a forced restart. This is not an allowed clean degraded dependency result.

### D07 — Project-save success overstates memory-layer persistence (high)

Save to `outputs/smoke_roundtrip.qgz` said all active layers were persisted. After approved reload, buffer names remained but five visible 500 m buffer polygons disappeared. Saved XML refers to memory provider URIs; no durable geometry source was produced. QGIS memory layers ordinarily need separate persistence, but the plugin must state that limitation or persist the outputs before claiming everything is saved.

### D08 — Raster classification range serializes as nan (medium)

Before save, DEM legend showed 35–214. XML has `classificationMin="nan"` / `classificationMax="nan"`, although color shader items retain 35–214. After reload, continuous legend displays nan/nan. Color strips still appear around overlaid polygons; loss of all pixel rendering is not claimed.

### D09 — QGIS 4 processing/script recovery and response rendering issues (medium)

C4 encountered blocked import `os` and “Algorithm native:buffer not found” in scripting attempts before producing the final GeoPackage. Safe inspection first attempted unavailable `QgsProject.customProperties`, then recovered. Plan and ranking tables were removed by response postprocessing despite related tool calls. This makes intermediate success/failure difficult to audit.

### D10 — Web source rendering fails (medium)

Latest QGIS release prompt used a Gemini grounded search rather than required `search_web`. Source rendered as malformed `download.html">https://changelog.qgis.org)*`. The official [QGIS changelog](https://changelog.qgis.org/en/version/list/) independently confirms QGIS 4.2 release date 3 July 2026; the chat's 4.2.3 publication date was not independently verified. Separate `search_web` attempts in B3 showed timeout/no-results failures.

## Artifact verification and recovery

- `../outputs/smoke_points.csv`: 5 rows; headers X,Y,fid,name,category,population,need; UTF-8 BOM.
- `../outputs/smoke_layout.pdf`: 885,542 bytes at verification; rendered page evidence `A7_pdf_render.png`.
- `../outputs/smoke_plan_result.gpkg`: 5 real feature rows, EPSG:32636. Every exterior vertex is 250 m from its corresponding input point within 2e-10 m. All buffers fit inside the boundary, so clipping has no visible trimming effect; independent topology validation was not performed.
- `../outputs/smoke_roundtrip.qgz`: pre-plan persistence specimen, 11 layers and 2 layouts; memory-buffer failure preserved.
- `../outputs/smoke_final.qgz`: final project after C4/C5, saved through QGIS and reopened; durable plan polygons and memory note survived. Earlier temporary-layer limitations remain.
- `artifact_verification.json` includes output SHA-256 values and saved renderer/source state. `verify_artifacts.py` is a read-only file verifier, not a substitute live test.
- Scheduler stopped; no further tick observed. Original rewrite setting restored and saved (`99_original_setting_restored.png`). No source fixes, installations, uninstalls, credential changes or fixture-master edits were performed.
- Sanitized GUI log: `cartogen_ai_gui_log.txt`: startup_settings plan_validation_gate=ON egress_gate_mode=off persist_chat=ON. Only the CartogenAI GUI log channel was checked; an audit of all disk logs was not performed.

## Remaining release-gate coverage

Fresh-profile installation, exact candidate ZIP hash/equivalence, upgrade from last stable, restart-twice action/dock checks, uninstall/reinstall cleanup, optional PostGIS enforcement, CSV malicious/formula/Unicode/overwrite cases, complete intermediate plan transitions, and quantitative A1 radius measurement remain unverified. The user's installed-profile rerun is complete with these explicit limits. Repeat mandatory paths in a fresh profile after repairing the observed failures; current results already block an overall PASS.
