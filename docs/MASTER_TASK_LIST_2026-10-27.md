# Master task list (2026-10-27, after release 1.18.4)

One list to follow up and plan from. It replaces the session task list (101 entries: 84 done, 17 open) and consolidates the open work of PLAN-022, PLAN-023 and the unmerged master list (W-1 to W-58, O-1 to O-11), the roadmap audit, and what the 1.18.2 to 1.18.4 hand runs found. The same rows are in `docs/MASTER_TASK_LIST_2026-10-27.csv` for a spreadsheet.

**Status words:** Not started, Waiting on you (only you can do it), Decision needed, Blocked (waiting on another row), In progress, Closed. **Priority:** P0 do now, P1 next, P2 soon, P3 later. **Size:** XS under an hour, S a day, M a few days, L a release, XL several. Sizes are planning guesses, not measurements. Nothing here is claimed done on CI evidence alone.

## State today

| Item | Value |
|---|---|
| Latest release | 1.18.5 (published 2026-10-28). `main` on 2026-10-30 holds unreleased work (Connections window, CLI guided setup, PLAN-040 structure audit); 1.18.6 is held. Checked by the offline suite and CI on QGIS 4.2.2; hand verification of the new work is OWN-16 |
| Offline tests / registered tools | about 5,450 run in CI (about 790 skipped, live-QGIS only) / 296 |
| Open GitHub issues | 2: #362, #380 (waiting on hand rows V3 to V8) |
| Feature ledger | 119 entries; 48 'not verified', 5 'partly' |
| Plans | 40 plan files (PLAN-001 to PLAN-041; HY-1 corrected the stale statuses) |
| Remote branches | 13 (the work branches of 2026-10-29/30 and main) |
| Unmerged documents | branch claude/pending-work-master-list (earlier master list and PLAN-023) |

## Do these first (the next two weeks)

1. **OWN-16** (added 2026-10-30): run the Connections window and the guided Claude Code / Codex setup on your Windows machine and send screenshots; the CLI work is CI-only until you do.
2. **OWN-1**: run Section N of the 1.18.4 package and send the folder with logs. Everything else about 1.18.x quality hangs on it.
3. **OWN-5**: confirm the roadmap order so RM-A can get a plan.
4. **HT-1**: Claude triages your results into 1.18.5.
5. **DEF-1**: Claude adds the empty-render capture to CI so release builds stop failing at random.
6. **OWN-3 and OWN-4**: the logs and rows that close the unexplained defects and the two open issues.

## A. Your actions and decisions

| ID | Task | Why | Who | Depends on | Size | Pri | Status | Source |
|---|---|---|---|---|---|---|---|---|
| OWN-1 | Install 1.18.4 and run Section N of the 1.18.4 test package (8 checks, about 15 minutes); then the rest as time allows. Save the CartogenAI log and a screenshot per row. | Hand-verifies the fixes of PRs 449, 452-456 (damage score, distances in degrees, wrong task card, IPC names, GDACS). Nothing from 1.18.2 to 1.18.4 is hand-verified yet except the three 1.18.2 checks. | You | - | S | P0 | Waiting on you | 1.18.4 test package, TEST_RUNBOOK.md |
| OWN-2 | Send the screenshot of the change-layer legend (row D6: is it blue-to-red, is the no-change area transparent?). | The colour stops are correct in code; without the picture the fault cannot be located. | You | - | XS | P2 | Waiting on you | 1.18.3 hand run D6 |
| OWN-3 | For the rows that failed without a found cause, send the per-prompt Log Messages text: unrequested layers (A5 country layer, A7 Incident layer), C5 inverted labels, D3, D4, S5. | Last two runs' logs held only the verdict line; the causes of these rows are unknown. | You | OWN-1 | S | P1 | Waiting on you | 1.18.3 hand run |
| OWN-4 | Run the 1.18.1-bundle rows V3 to V8 so issues #362 (V4, V5, V6) and #380 (V3, V7, V8) can be closed or fixed. | The only two open GitHub issues; waiting since 2026-10-23. | You | - | S | P1 | Waiting on you | PLAN-021, PLAN-022 N0 |
| OWN-5 | Confirm or change the roadmap order A to G in the roadmap audit (this unlocks plans and issues for RM-A to RM-D). | Nothing in the roadmap can start without it. | You | - | XS | P1 | Decision needed | ROADMAP_AUDIT_2026-10-27.md |
| OWN-6 | Answer the PLAN-022 N6 questions: temporary-layer note for incident, hazard and event layers; undo for rename_field and delete_field; add a clean-profile install row; stable versus pre-release channel; architecture items. | Small product choices that block HY work and wording of releases. | You | - | S | P2 | Decision needed | PLAN-022 N6 |
| OWN-7 | Confirm or change the PLAN-023 defaults (questions Q1 to Q15: persona model 'lens, never a gate', one primary plus one secondary persona, Power BI hand-off files only, assumed speeds only on request, and so on). | Needed before the profile programme starts. | You | - | S | P2 | Decision needed | PLAN-023 (branch claude/pending-work-master-list) |
| OWN-8 | Decide what happens to branch claude/pending-work-master-list (the earlier master list W-1 to W-58 and PLAN-023): merge for the record, or discard because this list replaces it. | It has never been merged; two lists must not drift apart. | You | - | XS | P2 | Decision needed | docs/PENDING_WORK_AND_PROFILE_ANALYSIS_2026-10-26.md |
| OWN-9 | Close the JIAF validation blockers: a Flags dashboard export or country records, the flag-6 historical table, the flag-3 zero case, the thresholds sheet, one real filled Annex 4 file. | The two JIAF blockers are printed in every JIAF result. | You | - | M | P2 | Waiting on you | session task 69, JIAF2 docs |
| OWN-10 | Provide credentials and terms for the deferred integrations: ACLED key, ReliefWeb app name, Kobo/ODK, GloFAS/CHIRPS, Logistics Cluster, LandScan. | Cannot be built without keys and licence terms. | You | - | M | P3 | Waiting on you | session task 67, gap analysis H10 |
| OWN-11 | Clean-profile install and in-place upgrade test of the exact release zip (tracker 1.10). | Needs a person with a fresh QGIS profile. | You | - | S | P2 | Waiting on you | IMPLEMENTATION_TRACKER 1.10 |
| OWN-12 | Upload to plugins.qgis.org if wanted (needs your login) and unpublish the old GitHub Pages site (replaced by the wiki). | Only you can do either. | You | - | XS | P3 | Waiting on you | PLAN-019, STATUS_DONE_VS_TESTED |
| OWN-13 | Close the open secret-scanning alert in repository settings (CI gitleaks passes on every push). | Repository setting only you can change. | You | - | XS | P3 | Waiting on you | STATUS_DONE_VS_TESTED |
| OWN-14 | Provide real-data samples when the matching release approaches: case-count file (R2), a DEM site and the engineer's report (R4), a depot and orders sample (R5), parcels and a store list (R6). | Known-answer tests and hand rows need real inputs. | You | - | M | P3 | Waiting on you | PLAN-023 Q7 to Q11 |
| OWN-15 | Re-run the nine model-choice rows (A5, A6, C1, C3, C4, C6, D4, E2, S5) with the Claude provider, and send the 40 MB evidence folder (needed for DEF-10, DEF-11, DEF-12). | The runbook's own method for telling a model problem from a tool problem. | You | - | S | P1 | Waiting on you | 1.18.4 smoke run 2026-10-27/28 |
| OWN-16 | Hand-verify the Connections window and the guided Claude Code / Codex setup on your Windows machine with the 2026-10-30 zip: open Plugins > Cartogen AI > Connections..., on each CLI page press the main button and follow it (install, sign in, connect, use), press OK, send one chat message; send a screenshot of each CLI page and the first error text. | Everything about the CLI connections is CI-only (stand-ins for the registry, where.exe, the login shell, the sign-in terminal and the model); the first real Codex run found three faults that CI could not see. | You | LEAD-8 | S | P0 | Waiting on you | PLAN-041 |

## B. Verification and hand-test follow-up

| ID | Task | Why | Who | Depends on | Size | Pri | Status | Source |
|---|---|---|---|---|---|---|---|---|
| HT-1 | Triage the 1.18.4 results into defects, write a failing test per defect, fix, and cut 1.18.5. | The loop that has produced 1.18.2, 1.18.3 and 1.18.4. | Claude | OWN-1, OWN-3 | M | P0 | In progress | release process |
| HT-2 | Ledger traceability: add a hand_row (a row id or 'none: reason') to every 'not verified' ledger entry (27 now, 12 at the time of PLAN-022) and make a test fail when a new entry has neither. | The ledger is the contract; 'not verified' must say which hand row would verify it. | Claude | - | M | P2 | Closed | PLAN-022 N2 |
| HT-3 | Build eval rows for model tool choice (prompt, expected tool) and measure them: D3 (survey tool), D4 (presence-gap write), S5 (refuse a trigger with no threshold). Change prompts or descriptions only with a measured gain. | The router already offers the right tools; what the model picks has never been measured. | Claude | OWN-3 | M | P2 | Not started | 1.18.3 hand run, W-4 |
| HT-4 | Verification debt, CI only today: Windows and macOS QGIS; large, messy, non-English and database-backed user data; numerical correctness of Processing outputs; delineate_watershed on a real DEM versus the engineer's report; a real Geofabrik extract and prompt-cache check. | Built and passing in CI, never run by a person. | Both | OWN-11, OWN-14 | L | P3 | Not started | W-5 to W-9 |
| HT-5 | Re-check 'partly' ledger entries (5) and wave E1, DXF and Excel export and the 20 later routing additions by hand. | Only 21 algorithms were ever hand-tested. | Both | OWN-1 | M | P3 | Not started | W-2, W-3 |
| HT-6 | Prove tools/collect_evidence.py in a real QGIS 4.2 session (written without QGIS, never run) and fix what breaks; then add it to the repo with a live test. | The agent-edition smoke package depends on it for logs, screenshots and layer tables; until run, evidence may fall back to manual capture. | Claude | OWN-1 | S | P1 | In progress | smoke package 2026-10-27 |
| HT-7 | Routing vocabulary audit: replay everyday synonyms and alternative wordings of each tool family through the real router and list the requests that are offered none of the right tools (found: 'list medical service in Al Maharah' offered no OSM or geocoding tool). Fix with aliases and a ratchet test. | The model tells the truth about the tools it is given, so a wording the router misses reads as 'I cannot do that'; the owner hit it in the first real chat through the CLI. | Claude | - | M | P2 | In progress | PR 508 |
| ML-1 | Decide which languages the tool router must serve beyond English (Arabic first, French?), then add their phrases for the most used tools as concept groups in routing_concepts.json. Measured 2026-11-01: an Arabic or French request is offered only the 10 always-on tools; the model understands the language, but the router and find_tools match English words only. | Users in Yemen and francophone Africa will write in their own language; today the tools are not offered and only the model's translation in a find_tools call can recover. | You | HT-7 | M | P2 | Decision needed | HT-7 audit round 3 |

## C. Open defects and observations

| ID | Task | Why | Who | Depends on | Size | Pri | Status | Source |
|---|---|---|---|---|---|---|---|---|
| DEF-1 | Elevation-profile print item renders empty intermittently in CI (#379 observation). It failed twice on one commit and passed on a third run with no change. Add a CI step that saves the PNG when the render is empty, then debug on QGIS 4.2. | Makes release CI fail at random; cause not found (a QGIS 3.34 reproduction in the sandbox was not comparable). | Claude | - | M | P1 | Not started | PLAN-026, PR 453 CI history |
| DEF-2 | Change-layer legend (D6): confirm blue-to-red with a transparent no-change area; fix if the screenshot shows otherwise. | Open since the 1.18.3 run. | Claude | OWN-2 | S | P2 | Blocked | 1.18.3 hand run D6 |
| DEF-3 | Unrequested layers: an 'Incident' layer after GDACS (A7), a country layer after building footprints (A5). No tool in the code adds them; trace the plan that does. | Surprises the user; cause unknown. | Claude | OWN-3 | S | P2 | Blocked | 1.18.2 and 1.18.3 hand runs |
| DEF-4 | C5 labels reported inverted: find which layer and labels. | Reported without detail. | Claude | OWN-3 | S | P2 | Blocked | 1.18.2 hand run |
| DEF-5 | Zonal-statistics columns (chg_mean, chg2_mean...) stay on the admin layer after the damage tool runs; remove them or run on a copy. | Side effect on the user's layer; a file-based layer keeps them. | Claude | - | S | P2 | In progress | PLAN-026 class C |
| DEF-6 | Nationwide 5 km task grid is refused above 5,000 cells: add a 'suggest a cell size' path. | Clear message today; a design choice. | Claude | OWN-6 | S | P3 | Decision needed | 1.18.2 hand run B1 |
| DEF-7 | OSM Overpass road download answered HTTP 502 after 4 retries: consider a mirror fallback and a clearer message. | Server side; the fixtures covered it in the test. | Claude | - | S | P3 | Not started | 1.18.2 hand run C1 |
| DEF-8 | Quiet-release clean-up: 24 unused noqa comments; the baseline of 504 broad-except handlers (none silent) recorded for review. | Lint hygiene. | Claude | - | S | P3 | In progress | PLAN-026 class G, H |
| DEF-9 | Evidence collector captured no log text in QGIS 4.2.3: log_cartogenai.txt and log_all.txt were empty for every row, so the tools each row called are not in the CSV. Cause not found (the signal connects; nothing arrives). Try the explicit overload messageReceived[str, str, Qgis.MessageLevel], and read tool calls from the plugin's own evidence folders (steps.jsonl) instead. | Every row's 'tools called' column is blank without it. | Claude | HT-6 | S | P1 | In progress | 1.18.4 smoke run 2026-10-27/28 |
| DEF-10 | A13: Sentinel-2 STAC search not executed ('tool execution stopped', no scenes, no layer). Read evidence/A13 steps and the plugin_evidence folder to find the failing call; add a failing test. | 1.18.4 added the cloud filter; its first live run failed. | Claude | - | M | P1 | In progress | 1.18.4 smoke run 2026-10-27/28 |
| DEF-11 | D6 (and S1): rasters not loaded and calculate_raster_change_detection 'could not find the layers' on both attempts, while .asc is on the loader's list. Find out whether the model never called add_layer_from_path or the tool rejected the file; read evidence/D6 and D6_retry. | Change-layer legend (DEF-2) cannot be judged until the rasters load. | Claude | - | M | P1 | In progress | 1.18.4 smoke run 2026-10-27/28 |
| DEF-12 | B7: execute_pyqgis_script failed twice (missing argument, isolation worker crashed) before the dashboard retry worked. Reproduce with the dashboard prompt and fix the argument handling / worker crash. | A crashing script worker costs the user a turn and an empty reply. | Claude | - | M | P1 | In progress | 1.18.4 smoke run 2026-10-27/28 |
| DEF-13 | N7c: update_task called with a null task id returns "Task ID 'None' not found" in the reply. Treat a missing id as 'the first open task' (as the auto-complete path already does) or return a plain message. | Visible error text after a successful GDACS layer. | Claude | - | XS | P3 | In progress | 1.18.4 smoke run 2026-10-27/28 |
| DEF-14 | B8: the print layout's KEY FIGURES (120,000 / 85,000 / 45,000) are not in the layer (94,000 / 76,000 / 52,000): the model typed numbers into a deliverable. Decide the guard: figures in layout text must come from a layer field or a tool result, else the tool refuses or marks them unverified. | Invented numbers on a map product are the worst failure this tool can have. | Claude | - | M | P0 | In progress | 1.18.4 smoke run 2026-10-27/28 |
| DEF-15 | N4/N6: a blur of 1000 and a heatmap radius of 5000 on a lat/lon layer were not refused; the model reprojected to UTM (EPSG:32638) and ran in metres. Decide: is reprojecting and working in metres correct (then the runbook expectation is wrong), or must a bare metre value on a lat/lon layer be refused? | 1.18.4 class-A guard covers the direct tools; the model found another path. | You | - | XS | P2 | Closed | 1.18.4 smoke run 2026-10-27/28 |
| DEF-16 | Runbook expectations to correct in the next package: D7 and S1 expect mean change 70/45 but damage_score has been normalised 0 to 1 since 1.18.4 (N1 already expects the ranking only); N5 layer name; R3 date bound cannot be tested before 2026-11-05; S5 refusal wording; A11 and C8 need the exact wording recorded. | Test-design faults, not tool defects. | Claude | - | S | P2 | In progress | 1.18.4 smoke run 2026-10-27/28 |
| DEF-17 | Model-choice failures on Gemini flash-latest: A5, A6, C1, C3, C4, C6, D4, E2, S5. E2: compute_jiaf_preliminary left jf_pre_sev empty with two sectors; check the tool result itself carries the two open blockers and a severity-not-computed reason, so a weak model cannot drop them. | Separates model from tool; the tool must carry the message. | Claude | OWN-15 | M | P2 | In progress | 1.18.4 smoke run 2026-10-27/28 |
| DEF-18 | C5: first run stopped by the loop guard (population_access_gap called 3 times with the same arguments) and the reachable figure differed between runs (1,028 vs 994). Find why identical calls are repeated and why the figure moves. | A figure that changes between identical runs cannot be trusted. | Claude | - | M | P1 | In progress | 1.18.4 smoke run 2026-10-27/28 |
| DEF-19 | Side effects: A10 added an empty 'UCDP Conflict Events - Yemen 2025' layer and printed a literal '&nbsp;'; A12 left hidden buffer_output and deletecolumn_output layers; A7/A9 loaded global GDACS/USGS layers for a Yemen request. | Unrequested layers (see DEF-3). | Claude | DEF-3 | S | P3 | In progress | 1.18.4 smoke run 2026-10-27/28 |
| DEF-20 | add_layer_from_path drops 'sublayer' on every live call: the orchestrator's special-cased branch calls the function with the path, name and source label only, so a named layer of a GeoPackage is never opened. Found while measuring drift for PLAN-033; fix with a CI live test. | A documented argument that never arrives. | Claude | - | S | P2 | In progress | codebase analysis 2026-10-28 |

## D. Product roadmap (from the roadmap audit)

| ID | Task | Why | Who | Depends on | Size | Pri | Status | Source |
|---|---|---|---|---|---|---|---|---|
| RM-A | Verified result gate: after each analysis that writes a layer or field, run applicable checks (CRS, geometry, not-all-null or constant, value range and unit, no stale field) and add them to the result; the answer must quote a failed check. | Three result errors in three hand runs were silent; this is the defensible differentiator. | Claude | OWN-5 | L | P1 | Decision needed | ROADMAP_AUDIT step A, session task 97 |
| RM-B | Attach the map canvas (or a region) plus legend text and layer list to the next message as an image part. | inspect_canvas_visually sends the map as base64 text in a tool result; the chat clients already accept image parts. | Claude | OWN-5 | M | P1 | Decision needed | ROADMAP_AUDIT step B, task 98 |
| RM-C | Record source URL, licence, retrieval date and coverage on every fetch result, the provenance sidecar and the report. | Needed for donors and for the verified workflow report. | Claude | OWN-5 | M | P1 | Decision needed | ROADMAP_AUDIT step C, task 99 |
| RM-D | Verified workflow report: sources, parameters, checks, assumptions and limitations, a rerun recipe, for one worked example (service coverage). | The lead feature; mostly assembly once A and C exist. | Claude | RM-A, RM-C | M | P1 | Not started | ROADMAP_AUDIT step D, task 100 |
| RM-E | Data discovery ranking (licence, coverage, freshness); STAC scene load, change detection and a validation step; one-prompt report. | Builds on D. | Claude | RM-D | L | P2 | Not started | ROADMAP_AUDIT step E, task 101 |
| RM-F | MCP transport over the tool registry with the existing write, egress and sensitivity gates intact. | Reach for little code, but only after A so exposed tools inherit the checks. | Claude | RM-A | M | P2 | Not started | ROADMAP_AUDIT step F, task 102 |
| RM-G | Record owner decisions before designing the workflow builder, specialist agents, cloud workers (no tier gating in this codebase) and a skills marketplace. | Each depends on a product or security decision. | You | - | M | P3 | Decision needed | ROADMAP_AUDIT step G, task 103 |

## E. Engineering hygiene

| ID | Task | Why | Who | Depends on | Size | Pri | Status | Source |
|---|---|---|---|---|---|---|---|---|
| HY-1 | Set the 14 stale plan statuses from their own logs; fold PLAN-020 into PLAN-021; close PLAN-024 to PLAN-026 when their hand rows pass; mark PLAN-019 done. | Status words no longer match the logs. | Claude | - | S | P2 | In progress | PLAN-022 N1 |
| HY-2 | Sweep IMPLEMENTATION_TRACKER.md (2,746 lines; duplicate sections 1.19 to 1.24; stale list at the top) and BUG_TRACKER.md. | The trackers are the planning source and are out of date. | Claude | - | M | P2 | Not started | PLAN-022 N3 |
| HY-3 | CI and release hygiene: pin the Windows runner, check upload-artifact against the Node notice, add an optional status_note input to release.yml (releases cannot be edited from this session type), generate the README test count. | A release cannot say 'not hand-tested' without a manual edit. | Claude | - | S | P2 | In progress | PLAN-022 N4 |
| HY-4 | Prune the 190-odd remote branches (merged and abandoned claude/* branches); keep the open ones. | 193 remote branches; it hides what is live. | Both | OWN-8 | S | P3 | Not started | repository state |
| HY-5 | Clean the session task list: drop the 84 completed entries, keep this list's open rows. | The list is a history, not a plan. | Claude | - | XS | P3 | Not started | this document |

## F. Capability programme (PLAN-023: releases R1 to R12, one release per package)

| ID | Task | Why | Who | Depends on | Size | Pri | Status | Source |
|---|---|---|---|---|---|---|---|---|
| PR-R1 | 1.19.0 Profiles: persona pack loader and picker with honest readiness, router re-rank, 52 seed tasks, catalogue generator, style profiles skeleton, data-source catalogue. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | OWN-7 | L | P3 | Not started | PLAN-023 |
| PR-R2 | 1.20.0 Spatial statistics: Moran's I, Getis-Ord Gi*, Kulldorff scan with Monte Carlo, rates, relative risk, SMR and smoothing, small-number flag. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | OWN-14 | L | P3 | Not started | PLAN-023 |
| PR-R3 | 1.21.0 Indices, time series, STAC: SAVI/EVI/NDMI/NBR, STAC load, multi-date statistics and anomaly, from-to change matrix, management zones, WorldCover, CHIRPS. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | - | L | P3 | Not started | PLAN-023 |
| PR-R4 | 1.22.0 Terrain, flood, engineering: cut and fill, HAND, bathtub flood footprint, viewshed, engineering sheet, mobility cost surface. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | OWN-14 | L | P3 | Not started | PLAN-023 |
| PR-R5 | 1.23.0 Network and movement: VRP with capacity and time windows, OD desire lines, GTFS accessibility, utility trace with valve isolation, walking and cycling profiles. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | OWN-14 | L | P3 | Not started | PLAN-023 |
| PR-R6 | 1.24.0 Site selection and urban: Huff model, centre of gravity, trade areas, scenario allocation, parcel split. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | OWN-14 | M | P3 | Not started | PLAN-023 |
| PR-R7 | 1.25.0 Connectors and Power BI: CKAN, ArcGIS Hub, Socrata, DEM/hydrography/soils, ERA5, WDPA, GTFS, DHIS2, Kobo/ODK, ACLED; Power BI hand-off files. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | OWN-10, OWN-7 | L | P3 | Not started | PLAN-023 |
| PR-R8 | 1.26.0 Standards and publication: ISO 19115 sidecar and validation, OGC API or QGIS Server project generator, topology rule checks, publication figure layout. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | - | M | P3 | Not started | PLAN-023 |
| PR-R9 | 1.27.0 Geometry editing: vertex edit, add part and ring, reshape, offset, chamfer, trim/extend, copy and paste between layers, identify by coordinate. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | - | M | P3 | Not started | PLAN-023 |
| PR-R10 | 1.28.0 Attributes, project, raster rows: virtual fields, conditional formatting, forms, actions, extra renderers, pyramids, raster attribute tables, datum transformations. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | - | L | P3 | Not started | PLAN-023 |
| PR-R11 | 1.29.0 Processing models and waves: Processing models and batch, in-place modification, the remaining file-writing algorithm waves, expression screening, argument-list checks against 4.2.3. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | - | L | P3 | Not started | PLAN-023 |
| PR-R12 | 1.30.0 Close-out: verification debt, JIAF re-check, reply-quality eval rows, remaining architecture records. | Scoped with acceptance and known-answer tests in PLAN-023; none started. | Claude | OWN-9, OWN-11 | M | P3 | Not started | PLAN-023 |

## G. Humanitarian and analysis carry-overs

| ID | Task | Why | Who | Depends on | Size | Pri | Status | Source |
|---|---|---|---|---|---|---|---|---|
| HU-1 | HX4 tools once keys exist: Kobo/ODK pull, ACLED, GloFAS/CHIRPS, Logistics Cluster, LandScan. | Blocked on OWN-10. | Claude | OWN-10 | L | P3 | Blocked | gap analysis H10 |
| HU-2 | JIAF: re-check flag formulas and the Annex 4 reader when OWN-9 material arrives; closing the blockers stays your decision. | Two open validation blockers. | Claude | OWN-9 | M | P3 | Blocked | JIAF2 |
| HU-3 | travel_time_matrix about 8 minutes on a whole country; optimize_delivery_route builds the graph per stop pair; assumed speeds by road class (only 0.9 percent of Jordan's roads carry a speed). | Performance and realism limits. | Claude | - | L | P3 | Not started | BUG-2026-09-25-3, W-39 |
| HU-4 | Raster-unit check (people per cell versus density) in population exposure; points into the admin CRS in damage counting; score-write labels. | Result-correctness items in the same class as RM-A. | Claude | RM-A | M | P2 | Not started | W-40 |
| HU-5 | Smaller carry-overs: task-runner callbacks at unload (#167 tail), find_region naming the wrong country, output layers piling up in long sessions. | Known, minor. | Claude | - | M | P3 | Not started | W-41 to W-43 |

## H. Architecture decisions (deferred, yours)

| ID | Task | Why | Who | Depends on | Size | Pri | Status | Source |
|---|---|---|---|---|---|---|---|---|
| AR-1 | Agent pipeline redesign (intent, inspector, planner) and a deterministic plan, validate, execute model. | Large change; only after RM-A shows what a gate buys. | You | RM-A | XL | P3 | Decision needed | tracker 1.5, 1.6 |
| AR-2 | Standard project folder architecture with immutable raw data. | Product opinion. | You | - | M | P3 | Decision needed | tracker 1.7 |
| AR-3 | task_matcher keyword normalisation favours short task definitions (partly mitigated in 1.18.1 and 1.18.4). | Routing fairness. | Claude | - | M | P3 | Not started | tracker 1.8 |
| AR-4 | Chunked k-means for very large rasters; further GUI-thread offloading. | Guard shipped, chunking not. | Claude | - | M | P3 | Not started | A14, A15 |
| AR-5 | Recorded as scoped and not recommended: vector memory stores, constrained decoding libraries, RestrictedPython, Presidio egress scan, semantic router. | Keep the record so they are not rediscovered. | You | - | - | - | Closed (record) | W-49 |
| AR-6 | Whole-code-base structure audit and staged reorganisation (PLAN-040): import cycle of 30 tool modules, 20 copies of one helper, unenforced layering, unused exception hierarchy. Stages 0 to 6 proposed; moving tool files into subpackages is not recommended. | You asked to reorganise everything; the audit says where the real problems are and what each fix costs. | You | - | M | P2 | Waiting on you | owner request 2026-10-28, PLAN-040 |

## I. Leadership plan (from the 2026-10-28 codebase analysis)

Source: the owner's analysis document of nine flagship QGIS AI plugins, checked against this repository. Umbrella plan: `docs/plans/PLAN-030-leadership-strategy.md`; the other plans are PLAN-031 (RM-A), PLAN-032 (RM-B), PLAN-033 (LEAD-4), PLAN-034 (RM-F), PLAN-035 (LEAD-5), PLAN-036 (LEAD-2, LEAD-3), PLAN-037 (LEAD-6).

| ID | Task | Why | Who | Depends on | Size | Pri | Status | Source |
|---|---|---|---|---|---|---|---|---|
| LEAD-1 | Decide the positioning ('the trusted GIS agent for humanitarian and field work') and the order of PLAN-030: result gate, canvas image, MCP, benchmark, directory listing. Absorbs OWN-5. | Everything in this stream depends on one stated direction. | You | - | XS | P1 | Decision needed | codebase analysis 2026-10-28 |
| LEAD-2 | Decide whether to support QGIS 3.x (stay 4.2+; current 3.x LTR only; 3.28 upward) after reading the PLAN-036 study. | The listing's audience; the cost is large and unknown until LEAD-3 reports. | You | LEAD-3 | XS | P1 | Decision needed | codebase analysis 2026-10-28 |
| LEAD-3 | Run the QGIS 3.x feasibility study: Qt5/Qt6 and PyQGIS differences counted by a script kept in tools/, CI cost, three options with a size each. No plugin change. | Replaces a guess with a number; can start before LEAD-2. | Claude | - | M | P2 | Not started | codebase analysis 2026-10-28 |
| LEAD-4 | Tool-argument drift (PLAN-033): fix the dropped sublayer, extend the drift test to every special-cased branch and to composite tools, build new tools' schemas from the signature. | Three dropped arguments in two days; the registry layer itself is consistent (measured), the orchestrator branches are not. | Claude | - | M | P1 | In progress | codebase analysis 2026-10-28 |
| LEAD-5 | Public, reproducible benchmark from the smoke fixtures: machine-checkable cases, a headless runner, a scoring definition written first, a per-provider table on a public page. Extends HT-3. | A number beats an adjective in a directory listing; the fixtures and expected answers already exist. | Claude | LEAD-1, HT-3 | L | P2 | Not started | codebase analysis 2026-10-28 |
| LEAD-6 | Directory listing pack and adoption material: metadata and tags checked against the directory rules, screenshots from the fixtures, a two-minute demo, worked examples per tool family, a fair comparison page, monthly download/rating record, two pilot teams. | Visibility, not features, is the current limit (OWN-12 still open; fewer than ten stars). | Both | LEAD-1, OWN-12 | M | P1 | Not started | codebase analysis 2026-10-28 |
| LEAD-7 | Structural debt after LEAD-4: split the largest modules (agent_orchestrator, analysis_tools, vector_tools, layout_tools), burn down the 504 broad-except baseline with a ratchet test, typed result shapes for one tool family. Plan to be written when LEAD-4 lands. | Reviewers notice size and broad excepts first; it does not cause wrong answers the way dropped arguments do, so it follows LEAD-4. | Claude | LEAD-4 | XL | P3 | Not started | codebase analysis 2026-10-28 |
| LEAD-8 | CLI bridge providers (PLAN-038): run the plugin on a local Claude Code, Codex or Gemini CLI login with no API key, tools and gates stay in the plugin. Starts with a spike on the Claude Code adapter. | Closes the no-key gap and widens who can try the plugin; priority raised by the owner 2026-10-28. | Claude | LEAD-1 | L | P1 | In progress | owner request 2026-10-28 |
| LEAD-9 | Settings connection redesign and CLI panel (PLAN-039): group connections by where the prompts go, an in-dialog acknowledgement for the CLI group, and Check connection / Sign in buttons per CLI. | The CLI providers need setup, a test and sign-in help to be usable by someone who is not a developer. | Claude | LEAD-8 | M | P1 | In progress | owner request 2026-10-28 |
| LEAD-10 | Decide whether to build an Antigravity CLI (agy) provider to replace the removed Gemini CLI one. Needs a real signed-in agy run first: third-party reports say `agy -p` prints nothing or hangs when its output is not a terminal (v1.0.6), which is how the bridge runs a CLI, and its flags are not from official documentation. | Google ended personal-account use of Gemini CLI on 2026-06-18 and moved those users to the Antigravity CLI; the plugin now has no Google-account CLI route (the Gemini API key connection stays). | You | OWN-16 | M | P2 | Decision needed | PLAN-041 |

## Counts by status

| Status | Rows |
|---|---|
| Not started | 32 |
| In progress | 21 |
| Decision needed | 15 |
| Waiting on you | 13 |
| Blocked | 5 |
| Closed | 2 |
| Closed (record) | 1 |
| **Total** | **89** |

## How to keep it current

Edit the status column when a row changes; add a dated line to the plan or issue the row points at; when a row is done write what verified it (CI only, or the hand row). Do not delete rows: set them to Closed with a reason. A new defect from a hand run gets a DEF row before work starts.

## Change log

Newest last. One line per status change; written by `tools/master_list.py set`.
- 2026-10-27: OWN-1 Waiting on you -> Waiting on you. 2026-10-27: use the agent-edition package cartogen_ai_live_smoke_1.18.4.zip (AGENT_INSTRUCTIONS.md, 61 rows, shapefile/GPKG/GeoTIFF copies, collect_evidence.py); return the whole results folder zipped
- 2026-10-27: OWN-2 Waiting on you -> Waiting on you. 2026-10-27: the smoke package asks for a close legend screenshot at row D6
- 2026-10-28: OWN-1 Waiting on you -> Closed. Results received 2026-10-28: 66 rows, 44 PASS, 19 FAIL, 1 SKIP (A4 network), 2 UNVERIFIED (A11, C8); Gemini flash-latest, QGIS 4.2.3. Triage in DEF-9 to DEF-19
- 2026-10-28: HT-1 Waiting on you -> In progress. 1.18.4 results triaged 2026-10-28; defects DEF-9 to DEF-19; waiting on the 40 MB evidence folder (OWN-15)
- 2026-10-28: HT-6 Not started -> In progress. First real run 2026-10-28 on QGIS 4.2.3: screenshots, layer tables and project state worked; log capture was empty (DEF-9)
- 2026-10-28: DEF-9 Not started -> In progress. 2026-10-28 PLAN-027: collector now copies the plugin evidence folders per snap and lists tools called; explicit signal overload tried, NOT verified in QGIS
- 2026-10-28: DEF-10 Not started -> In progress. 2026-10-28 evidence read: the model never called the STAC tool (find_tools for geocoding, then stopped). Root gap: no bbox for a named place; geocode now returns one (PLAN-027). Needs rerun
- 2026-10-28: DEF-11 Not started -> In progress. 2026-10-28 cause found: single-backslash Windows path, JSON turned \f and \b into control characters. arg_repair.py restores them (PLAN-027). Needs rerun of D6
- 2026-10-28: DEF-13 Not started -> In progress. 2026-10-28 fixed in PLAN-027 (null id updates the one open task or says there is no plan); awaiting PR merge
- 2026-10-28: DEF-15 Decision needed -> Closed. 2026-10-28 not a defect: N6 evidence shows the degrees guard fired (5000 degrees is about 555,000 km); the model then reprojected to UTM and worked in metres. Runbook expectation was wrong
- 2026-10-28: DEF-16 Not started -> In progress. 2026-10-28 also: C6 demand points sit about 5 km off the roads (default snap 2000 m; model retried with a larger one) - fixture note, not a tool fault
- 2026-10-28: DEF-19 Not started -> In progress. 2026-10-28 root cause of the global GDACS layer (A7, N7c): the orchestrator dropped the country argument; fixed in PLAN-027 with a guard that checks every *_network_phase call. USGS has no country concept (needs bbox, see geocode bbox)
- 2026-10-28: HT-1 In progress -> In progress. 1.18.5 published 2026-10-28 (tag cartogen-ai-v1.18.5, not pre-release); agent-edition package sent; next: owner run of Section P and Section N
- 2026-10-28: DEF-11 In progress -> In progress. Fixed in 1.18.5 (path escapes); needs hand rerun: runbook row P2
- 2026-10-28: DEF-13 In progress -> In progress. Fixed in 1.18.5; no hand row (hard to trigger)
- 2026-10-28: DEF-10 In progress -> In progress. 1.18.5 geocode bbox; hand rerun: runbook rows P3 to P5
- 2026-10-28: DEF-19 In progress -> In progress. GDACS country fixed in 1.18.5; hand rerun: runbook row P1
- 2026-10-28: DEF-9 In progress -> In progress. 1.18.5 collector copies plugin evidence and writes tools_called.txt; hand check: runbook row P6
- 2026-10-28: OWN-1 Closed -> Waiting on you. Run the 1.18.5 package (cartogen_ai_live_smoke_1.18.5.zip): Section P first (6 rows), then Section N; return the whole results folder. Rerun the nine model-choice rows with the Claude provider (OWN-15)
- 2026-10-28: DEF-14 Not started -> In progress. 2026-10-28 PLAN-028: key_figures_from reads figures from a layer; typed figures not found in the project data are marked on the layout and named in the reply. Awaiting merge; hand rerun of B8
- 2026-10-28: HY-1 Not started -> In progress. 2026-10-28: 8 plans updated from their own logs and the GitHub release list (001 abandoned, 007/013/015/016/017 done, 020 abandoned, 021 in progress). Left as they are: 018 (no 1.18.0 release tag exists), 024-026 (close when hand rows pass), 002/003/005/006/008/009/014 (open items remain)
- 2026-10-28: HT-2 Not started -> Closed. 2026-10-28: every 'not verified' ledger entry (32) now has a hand_row, and tests/test_feature_ledger.py fails for a new one without it. 'none: reason' is allowed where no person can check it
- 2026-10-28: DEF-5 Not started -> In progress. 2026-10-28 PLAN-029: the damage run deletes the working columns it created; merged-pending; unreleased
- 2026-10-28: DEF-19 In progress -> In progress. 2026-10-28 PLAN-029: no empty layer when a UCDP/USGS/EONET/GDACS fetch matches nothing; &nbsp; shown as a space. A12 hidden Processing layers still open (no cause without evidence)
- 2026-10-28: DEF-18 Not started -> In progress. 2026-10-28 cause found in the C5/A6 evidence: population_access_gap had no speed_field/direction_field, so 'using speed_blocked' was ignored (1,028 = bridge passable, 994 = blocked). Now passed through (PLAN-029 item 4); unreleased. The loop-guard stop: the first call also carried no speed field; not reproduced
- 2026-10-28: DEF-18 In progress -> In progress. 2026-10-28 correction: the 1,028 vs 994 gap is most likely the missing speed field (the C5 first call carried none), not proven. Fix stands on its own: population_access_gap now takes speed_field/direction_field (PLAN-029 item 4); unreachable by the loop-guard stop, not reproduced
- 2026-10-28: DEF-17 Not started -> In progress. 2026-10-28 E2 read from the evidence: the tool result carried the blockers; its write PREVIEW did not, nor that jf_pre_sev would be empty (2 of 8 sectors is by design). The preview now carries both (PLAN-029 item 5). The other eight model-choice rows still need the Claude-provider rerun (OWN-15)
- 2026-10-28: RM-A Decision needed -> Decision needed. Plan written: docs/plans/PLAN-031-verified-result-gate.md (2026-10-28). Starts when LEAD-1 fixes the order
- 2026-10-28: RM-B Decision needed -> Decision needed. Plan written: docs/plans/PLAN-032-canvas-as-an-image.md (2026-10-28). Starts when LEAD-1 fixes the order
- 2026-10-28: RM-F Not started -> Not started. Plan written: docs/plans/PLAN-034-mcp-server.md (2026-10-28). Depends on RM-A
- 2026-10-28: OWN-5 Decision needed -> Decision needed. 2026-10-28: widened by LEAD-1 (positioning and order); answer there
- 2026-10-28: LEAD-8 Decision needed -> Not started. PLAN-038 research done; owner confirmed interpretation; build starts with runner + Claude adapter
- 2026-10-28: LEAD-8 Not started -> In progress. runner + Claude adapter built, CI-only; spike script tools/cli_bridge_spike.py waits for the owner (SPIKE-1)
- 2026-10-28: DEF-20 Not started -> In progress. fixed in code (orchestrator forwards sublayer), offline test fails without the fix; CI-only until the hand row: open a named layer of the smoke GeoPackage
- 2026-10-28: LEAD-8 In progress -> In progress. runner + Claude and Codex adapters built, CI-only; spike (tools/cli_bridge_spike.py --cli claude|codex) waits for the owner (SPIKE-1); Gemini not started
- 2026-10-28: LEAD-8 In progress -> In progress. runner + Claude, Codex and Gemini adapters built, CI-only; spike (tools/cli_bridge_spike.py --cli claude|codex|gemini) waits for the owner (SPIKE-1); Settings wiring waits for the spike
- 2026-10-28: LEAD-8 In progress -> In progress. adapters wired into Settings behind an opt-in box (off by default), CI-only; owner: tick the box, reopen Settings, run the spike (SPIKE-1); Settings 'Test connection' and hand-test rows not done
- 2026-10-28: LEAD-9 In progress -> In progress. slice 1 (CLI panel, groups) merged; slice 2 (rest of the window regrouped by purpose) in PR, CI-only; owner: look at the window
- 2026-10-28: LEAD-9 In progress -> In progress. slices 1 and 2 merged; slice 3 (Test button for key-based providers) in PR, CI-only; owner: look at Settings, press Test and the CLI Check connection buttons
- 2026-10-28: LEAD-8 In progress -> In progress. CLI program discovery fix (shorter GUI PATH), in PR, CI-only; owner: retry Check connection or paste the path from where/which
- 2026-10-28: DEF-12 Not started -> In progress. worker no longer dies on print or non-JSON result; clearer missing-argument message; PR open, CI only; cause inferred, original crash never logged
- 2026-10-28: DEF-10 In progress -> In progress. second cause found and fixed: geocode tool not offered for the scene prompt, model not told today's date, malformed dates unexplained; PR open, CI only, no model run; hand rows R1/A13/P5
- 2026-10-28: DEF-11 In progress -> In progress. second cause fixed: change detection only looked up layer names, now also loaded-file paths and raster files; PR open, CI only; hand rows P2/D6
- 2026-10-28: DEF-13 In progress -> In progress. audit found 3 more gaps (finished plan message, null status raised, omitted id raised); fixed with tests; PR open, CI only; no hand row
- 2026-10-28: DEF-17 In progress -> In progress. A5/A6 router gap fixed (place lookup not offered); other 7 rows already offered their tools so need the Claude rerun OWN-15 + eval HT-3; PR open, CI only
- 2026-10-28: DEF-16 In progress -> In progress. expectations checked against fixtures and tool wording; S5/R3/N5/A11/C8 corrected, D7/N1 verified; rev2 package built; stays open until the corrected runbook is used in a real run; record docs/RUNBOOK_EXPECTATION_CHECKS_2026-10-28.md
- 2026-10-28: AR-6 added (Decision needed). Whole-code-base audit done (PLAN-040, tools/structure_audit.py); no code moved; owner to confirm the intended import direction and pick stages
- 2026-10-28: AR-6 Decision needed -> In progress. stage 0 guard test + stage 3a (3 leaf modules moved below the agent) built, violations 17 -> 4; stage 1 rejected (583 test patches); stages 2, 4, 5, 6 open
- 2026-10-28: AR-6 In progress -> Waiting on you. PLAN-040 stages 0, 3, 4, 5a, 6 merged (#485 #486 #489 #490 #491 #488), all CI-only. Not done by decision: styling-cluster cycle break, large-file splits (patch seams), JIAF function refactors (owner sign-off pending), token trim (needs your hand test, evidence in the plan). Needs the one full QGIS test before it is closed.
- 2026-10-29: AR-6 Waiting on you -> Waiting on you. PLAN-040 stages 0, 3, 4, 5a-5d, 6 merged (#485 #486 #488 #489 #490 #491 #493 #494 #495 #496), all CI-only. Not done by decision: styling-cluster cycle break, large-file splits (patch seams), JIAF refactors (owner sign-off), token trim (needs your hand test), live-job coverage collection (CI change). Needs the one full QGIS test before it is closed.
- 2026-10-30: LEAD-9 In progress -> In progress. slices 1 to 3 merged; slice 4 (PLAN-041): connections moved out of Settings into their own Connections window with a Plugins menu link, in PR, CI-only; owner: open Plugins > Cartogen AI > Connections..., look at every page, press Use this connection, Test and Check connection
- 2026-10-30: LEAD-8 In progress -> In progress. Claude Code and Codex CLI providers only; Gemini CLI removed 2026-10-30 (Google ended personal accounts 2026-06-18); owner: install the zip, tick Allow CLI logins, Use Claude Code CLI and Codex CLI and send one message each
- 2026-10-30: LEAD-8 In progress -> In progress. 2026-10-30: Claude Code and Codex CLI providers merged (PRs 498, 499, 504-507): program found the way the terminal finds it (registry PATH, login shell, npm prefix, where.exe), detection of installed/signed-in CLIs, guided install/sign-in/connect/use with consent. Gemini CLI removed (Google ended personal accounts 2026-06-18). CI-only: first real Codex run is OWN-16; Antigravity is LEAD-10
- 2026-10-30: LEAD-9 In progress -> In progress. 2026-10-30: Connections window merged (PRs 500-503, 505-507): native list, one accent, Plugins menu link, Settings keeps privacy/behaviour/layout/diagnostics. Looked at only in my offscreen PyQt6 renders, plus the owner's screenshot of the first build (which led to the redesign); the real QGIS look after the redesign is part of OWN-16
- 2026-10-30: DEF-7 Not started -> Not started. 2026-10-30: seen again (Hadramawt hospitals: timeout, then HTTP 502 after 4 retries, public overpass-api.de). Not fixed: no mirror fallback yet; needs a choice of mirrors (owner) and a test with a stand-in server
- 2026-10-30: OWN-16 Waiting on you -> Waiting on you. 2026-10-30: added; run the Connections window and the guided CLI setup on your Windows machine, send screenshots of each CLI page and the first error text
- 2026-10-30: HT-7 Not started -> Not started. 2026-10-30: added after 'list medical service in Al Maharah' offered no OSM tool (PR 508 fixed that wording)
- 2026-10-30: LEAD-10 Decision needed -> Decision needed. 2026-10-30: added; no Google-account CLI route since Gemini CLI was removed; needs a real signed-in agy headless check before any code
- 2026-10-31: HT-7 Not started -> In progress. PLAN-042 steps 1-4 merged (#512 data file and add/check command, #513 and #515 keywords beside each tool, #514 shared concept groups, #516 find_tools uses the phrases, is always offered, rule 56). Still open: the audit itself (replay everyday synonyms per tool family and add the misses as rows with tools/routing_golden.py) and a hand test that a model now calls find_tools (ledger entry find-tools-fallback).
- 2026-10-31: LEAD-4 Not started -> In progress. PLAN-033 items 1 and 2 done (sublayer forwarded; tests/test_orchestrator_branches_forward_schema_arguments.py covers all 15 two-phase branches, mutation-checked on the GDACS country read; it cannot see a drop after the read, stated in the test). Items 3 (composite tools) and 4 (schema from signature) open.
- 2026-10-31: DEF-8 Not started -> In progress. Unused noqa: none left (ruff RUF100 is part of the enforced RUF set and CI passes at zero, re-checked 2026-10-31); the 504 broad-except baseline is still only recorded, not reviewed.
- 2026-10-31: HY-3 Not started -> In progress. release.yml status_note input done (PR open, CI only, workflow not run). Left: pin windows-latest (renames the 'test (windows-latest, 3.11)' check, which branch protection may require by name; owner can confirm), upload-artifact vs Node 24 notice, README test count generated.
- 2026-10-31: HT-7 In progress -> In progress. First audit round done (PR open): 30 everyday wordings replayed with real tool names, 11 missed the right tool, fixed by phrases beside 8 tools and 12 rows in routing_requests.json. More families to audit (rasters, layout, hazards, logistics, editing); and the hand test that a model calls find_tools (ledger entry find-tools-fallback).
- 2026-10-31: HT-7 In progress -> In progress. Audit rounds 1 and 2 done: 91 everyday wordings replayed with real tool names, 23 missed the right tool and are fixed (phrases beside 20 tools) and kept as rows in routing_requests.json (27). Still to audit: JIAF and survey tools, web research, imagery extraction, reporting, non-English wording; plus the hand test that a model calls find_tools (ledger entry find-tools-fallback).
- 2026-11-01: HT-7 In progress -> In progress. Rounds 1 to 3 done: 160 everyday wordings, 31 misses fixed, kept as 35 rows. Open: non-English routing (Arabic and French get only the 10 always-on tools; mitigation in the round 3 PR tells the model to call find_tools in English, unverified; real fix needs the languages decided, see new row ML-1), plus the hand test that a model calls find_tools.
- 2026-11-01: ML-1 Decision needed -> Decision needed. Which languages (Arabic, French) should the router serve? Owner choice.
- 2026-11-01: HT-7 In progress -> In progress. Rounds 1 to 4 done: 246 everyday wordings, 47 misses fixed, kept as 51 rows; every user-facing tool has now been named in at least one wording. Open: non-English routing (ML-1) and the hand test that a model calls find_tools and then chooses the right tool.
