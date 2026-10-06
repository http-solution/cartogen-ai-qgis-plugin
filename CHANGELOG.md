# Changelog

**[1.3.0] and earlier moved to `CHANGELOG_ARCHIVE.md`** in the 2026-08-31 documentation pass -- this file had grown to 2,146 lines covering every version since `[0.1.2]`, most of it from the very early, rapid `[1.2.x]` patch cycle. The split point is `[1.4.0]`, this project's own documented milestone (the dual-tree-to-single-tree consolidation --
see the `[1.4.0]` entry below and `CONTRIBUTING.md`). Entries were relocated verbatim, not rewritten, per this project's convention that past changelog entries are a historical record (`CONTRIBUTING.md` §2) -- only the file they live in changed.

**Recent releases at a glance:**

| Version | Date | Summary |
|---|---|---|
| [1.16.0-rc18](#v1-16-0-rc18) | 2026-10-06 | **Release candidate 18 for 1.16.0.** No breaking changes. Fixes from the rc15 and rc17 smoke reports: stale-question chat bug, continuation after Apply, router follow-up tools, guard false positives, task matching, overwrite confirmation, imagery download off the main thread; not hand-tested. |
| [1.16.0-rc17](#v1-16-0-rc17) | 2026-10-06 | **Release candidate 17 for 1.16.0.** No breaking changes. Fixes from the rc15 smoke report: tool-naming requests no longer matched to unrelated tasks, result labels from a name field, save warns about memory layers, raster range saved, imagery download message; not hand-tested. |
| [1.16.0-rc16](#v1-16-0-rc16) | 2026-10-06 | **Release candidate 16 for 1.16.0.** No breaking changes. Fixes from the rc15 hand test: list-returning tools no longer reported as failed (regression since rc12), CRS-question retry, one-point print layout extent; live-test discovery; not hand-tested. |
| [1.16.0-rc15](#v1-16-0-rc15) | 2026-10-05 | **Release candidate 15 for 1.16.0.** No breaking changes. Replace-by-name warning for service-area results (#130 point 3), issue verification checklist; JIAF validation items still open; not hand-tested. |
| [1.16.0-rc14](#v1-16-0-rc14) | 2026-10-05 | **Release candidate 14 for 1.16.0.** No breaking changes. JIAF 2 analysis-support tools (OCHA worksheet flag rules, decisions, finals, patterns); an Annex 4 reader that is an unsupported optional format; two validation items still open; not hand-tested. |
| [1.16.0-rc13](#v1-16-0-rc13) | 2026-10-04 | **Release candidate 13 for 1.16.0.** No breaking changes. Humanitarian map looks, task-register corrections, allocation envelope, IPC/INFORM/UNOSAT importers and critical-link screening; not hand-tested. |
| [1.16.0-rc12](#v1-16-0-rc12) | 2026-10-02 | **Release candidate 12 for 1.16.0.** No breaking changes. Fixes from the first full hands-on smoke test of rc11: CRS asked when unstated, origin layers reused, chat scrolling and timestamps, no-basemap dashboard markers, admin boundary labels, population ramp name match, soft graticule, faster two-stop route with one-way and honest "shortest" wording, blue within-reach facilities. CI-verified on QGIS 4.2.2; not yet re-run by hand |
| [1.16.0-rc11](#v1-16-0-rc11) | 2026-10-01 | **Release candidate 11 for 1.16.0.** No breaking changes. Fixes from the first hands-on smoke test of rc10: re-saved API keys, panel at startup, CSV X/Y columns, layer order and visibility, whole-country WorldPop kept in the project folder, clarification loop, router mismatches, hull population labelled an upper bound, results GeoPackage cleanup. CI-verified on QGIS 4.2.2 |
| [1.16.0-rc10](#v1-16-0-rc10) | 2026-10-01 | **Release candidate 10 for 1.16.0.** No breaking changes. Includes rc9 (reply guard, turn limits, download-size guard, single-tree matrix, concave-hull exposure, results store, model view) plus the visualization round: cost-banded routing roads, grouped reach polygons, styled rasters/outputs with legend units, automatic labels, styled print layout with an access-map template, ten more allowlisted analysis algorithms. CI-verified on QGIS 4.2.2; not yet seen in a hands-on session |
| [1.16.0-rc8](#v1-16-0-rc8) | 2026-09-30 | **Release candidate 8 for 1.16.0.** No breaking changes. Fixes from the rc7 Yemen smoke test (F01-F25): project no longer renamed by isolated scripts, gate confirmation works, no fabricated results, coordinates converted in code, service-area guards, explicit-only destructive confirmations, highlight cleanup, memory coordinate guard, findable dashboards, Excel-safe CSV. Several findings remain open (see entry) |
| [1.16.0-rc7](#v1-16-0-rc7) | 2026-09-28 | **Release candidate 7 for 1.16.0.** No breaking changes. Four execute_pyqgis_script isolation-worker Windows bugs found and fixed (wrong-interpreter detection, missing PYTHONPATH, lost stderr, too-short handshake). Local-data download offer no longer loses the request on a typo or names the wrong region; the download/online prompt now decides silently for the routine case and only asks via clickable chips when there's a real decision (large/unknown size, poor/offline connectivity). calculate_service_area's hull polygon styled and deduplicated. Exported CSVs no longer get an unreadable, unstable filename. execute_pyqgis_script now process-isolated with its own QgsApplication. New direct UI control for layer sensitivity tagging. georeference_image gained Linear/Helmert transforms with RMSE/scale reporting. Analysis-tool output styling now remembered per project across similar follow-up requests |
| [1.16.0-rc6](#v1-16-0-rc6) | 2026-09-27 | **Release candidate 6 for 1.16.0.** No breaking changes. Threshold parsing now catches spelled-out/plural time and distance phrasing ("one hour's travel"), not just digits. OSM road ingest fixed to build real lines (not one point per vertex) with Overpass retry-on-transient-failure. In-place upgrades no longer fail on stale cached modules. Automatic model selection actually takes effect and never escalates to an expensive/special-purpose model. Network analysis measures real metres/hours regardless of CRS/ellipsoid, no longer freezes QGIS on a large network (background + Stop button), and `calculate_service_area` routes only over reachable roads. GDACS/EONET alerts carry an `event_id` field; `buffer_analysis` gained `only_selected`. New opt-in tools: `estimate_road_speeds` and an offer to download a local Geofabrik extract before road-network requests. `docs/IMPLEMENTATION_TRACKER.md` §1.10 (clean-profile install/upgrade) closed with a real QGIS session |
| [1.16.0-rc5](#v1-16-0-rc5) | 2026-09-24 | **Release candidate 5 for 1.16.0.** QGIS 4.2+ only (3.x dropped). New opt-in, off-by-default safeguards: a cloud-provider data-protection gate for sensitive layers and attachments, a plan-validation gate for DELETE/PUBLISH tools, and a Project Inspector. New `create_project_folder_structure` tool. Sandbox now also blocks `QgsProject.write()` and `authManager()`. Unnamed processing outputs are added hidden. Clearer errors when a URL doesn't serve geodata |
| [1.16.0-rc4](#v1-16-0-rc4) | 2026-09-23 | **Release candidate 4 for 1.16.0.** Codebase security review with live adversarial testing: 2 real `execute_pyqgis_script` sandbox bypasses found and fixed (`qgis.utils`/`processing` re-exporting `os`/`sys` as plain attributes reachable no matter what's blocked at import time; this plugin's own package never being blocked, letting a script read the live in-memory session credential store directly). Process isolation recorded as the intended real fix, not further denylist patching (`docs/IMPLEMENTATION_TRACKER.md` §1.11). 10 best-effort `except Exception: pass` sites now leave a content-free trace instead of failing silently. `CLAUDE.md` refreshed to match the post-Phase-11 layout and live-QGIS CI job |
| [1.16.0-rc3](#v1-16-0-rc3) | 2026-09-21 | **Release candidate 3 for 1.16.0.** Closes both stable-release gates rc2 left open: Ruff lint fixed for real (125 violations → 0, not accepted as debt, incl. a real `QgsLabelObstacleSettings` import bug found and live-fixed), and the CI post-test segmentation fault root-caused and fixed rather than waived (~40 accumulated live `QDockWidget`s crashing at interpreter shutdown; fixed with explicit `gc.collect()` + Qt event-loop pump before `exitQgis()`), through five rounds of independent review. Both `qgis-live-tests` images now pinned by immutable digest. Only remaining gate before stable: the exact-ZIP clean-profile install/upgrade test, which needs a real interactive QGIS GUI session |
| [1.16.0-rc2](#v1-16-0-rc2) | 2026-09-20 | **Release candidate 2 for 1.16.0.** Security/privacy remediation from a 15-section production-standard audit, refined through two rounds of independent review: QAction lifecycle leak fixed and live-confirmed; plaintext credential persistence removed entirely (session-only in memory, no opt-out); logging moved to structured metadata-only by default (no raw prompt/response/tool content logged); CI matrix expanded to Windows + real QGIS 4.2.2/3.28 LTR docker jobs and actually validated green (3 real environment bugs found and fixed in the process) |
| [1.16.0-rc1](#v1-16-0-rc1) | 2026-09-20 | **Release candidate 1 for 1.16.0.** Renumbers forward from stable `1.15.6`, replacing the `1.5.7-rc1..rc5` line after an independent review confirmed via QGIS's own version-comparison function that `1.5.7-rc5` compares as *older* than `1.15.6`. Same content as rc5 (Phase 11 restructuring, AST-sandbox fix, keyboard-nav fixes) plus a stale CI packaging assertion and stale doc test-counts fixed |
| [1.5.7-rc5](#v1-5-7-rc5) | 2026-09-20 | **Release candidate 5 (superseded — see `1.16.0-rc1` above; this version string sorts *older* than the already-published `1.15.6` stable release, a real defect found and corrected the same day).** Phase 11 architecture restructuring finished for real (a prior pass had left only directory scaffolding), a live-confirmed `execute_pyqgis_script` AST-sandbox bypass found and closed, and 2 keyboard-navigation fixes (Tab trapped in the chat input, Escape doing nothing) |
| [1.5.7-rc4](#v1-5-7-rc4) | 2026-09-20 | **Release candidate 4.** `ingest_osm_features` two-phase OSM vector ingestion + AST sandbox prompt guardrails, and a code-review pass fixing 7 real correctness/security bugs (credential rotation, silent over-export, a reintroduced agent-turn-stalling dialog, an equator/prime-meridian data-loss bug, an opacity-clobber regression, a profiler misclassification) plus a latent circular import |
| [1.5.7-rc3](#v1-5-7-rc3) | 2026-09-19 | **Release candidate 3.** Pre-release audit remediation and PyQGIS API modernization: minimum QGIS version reconciled to 3.28, `writeAsVectorFormatV3`/`QgsClassificationMethodRegistry` migrations replacing deprecated APIs |
| [1.5.7-rc2](#v1-5-7-rc2) | 2026-09-19 | **Release candidate 2.** Centralized settings keys, decoupled provider dependencies, hardened shapefile DBF laundering, shaded relief with blend mode, full-phase engineering self-review, and docs synchronization |
| [1.5.7-rc1](#v1-5-7-rc1) | 2026-09-19 | **Release candidate 1.** QGIS Processing Provider, OGC SLD export, point cluster renderers, OCHA layout elements, geodetics, token economy & caching, structured logging, proxy support, shaded relief, shapefile laundering, settings centralization, and architecture subdivisions |
| [1.15.6](#v1-15-6) | 2026-09-18 | **Stable.** Promoted from rc6, no code changes -- security/audit remediation, crash root-causes, rate-limit resilience, the orchestrator reliability pass, and the full Broadsheet UI redesign, across 6 release candidates |
| [1.15.6-rc6](#v1-15-6-rc6) | 2026-09-18 | Release candidate: search_web's dead duckduckgo-search dependency migrated to ddgs, found via an independent audit-verification pass of every RC5 open item |
| [1.15.6-rc5](#v1-15-6-rc5) | 2026-09-17 | Release candidate: router-confidence, field-width, and confirmation-gate fixes, plus the full Broadsheet redesign (single-scroll dock, inline safety-gate card, layer context picker) |
| [1.15.6-rc4](#v1-15-6-rc4) | 2026-09-16 | Release candidate: crash root-causes confirmed with real tracebacks, a tool-discovery router gap, a UI freeze reverted, and a Settings/chat/Activity visual redesign |
| [1.15.6-rc3](#v1-15-6-rc3) | 2026-09-15 | Release candidate: 2 more fixes on rc2 -- missing first-message echo, tool-argument shape validation |
| [1.15.6-rc2](#v1-15-6-rc2) | 2026-09-15 | Release candidate: 4 fixes on rc1 -- requests dependency, GDACS country filter, dock screen-clamp timing, prompt-preview-to-in-chat conversion |
| [1.15.6-rc1](#v1-15-6-rc1) | 2026-09-14 | Release candidate: fixes 27 of 32 findings from a full security/QGIS/API/performance/code-quality audit |
| [1.15.5](#v1-15-5) | 2026-09-13 | Patch: fixed another instance of the "'str' object has no attribute 'get'" crash, this one in Gemini usage parsing |
| [1.15.4](#v1-15-4) | 2026-09-13 | Patch: root-caused and fixed the "'str' object has no attribute 'get'" crash |
| [1.15.3](#v1-15-3) | 2026-09-13 | Patch: the user's own reply to a clarifying question wasn't showing up in the chat log |
| [1.15.2](#v1-15-2) | 2026-09-13 | Patch: requirement-gate questions now ask in chat instead of a separate boxed panel |
| [1.15.1](#v1-15-1) | 2026-09-13 | Patch: live-hazard-data requests could get refused despite real matching tools existing |
| [1.15.0](#v1-15-0) | 2026-09-13 | Gemini prompt caching (automatic, implicit) + cache-hit visibility for Gemini and Claude |
| [1.14.1](#v1-14-1) | 2026-09-13 | Patch: floating dock clamped to the screen after a report of the chat input row going missing |
| [1.14.0](#v1-14-0) | 2026-09-13 | Modularized the 47-rule base prompt by relevance; "hi" now ~3.2K tokens, down from ~23K originally |
| [1.13.1](#v1-13-1) | 2026-09-12 | Patch: a plain "hi" cost ~23K tokens from tool-router padding; word-boundary matching + stopwords fix it |
| [1.13.0](#v1-13-0) | 2026-09-12 | Rate-limit/task-size resilience: 429-aware backoff on all providers, adaptive pacing, mid-turn compaction |
| [1.12.0](#v1-12-0) | 2026-09-12 | Onboarding profile, Help auto-show, tidier tool-call summary; fixes a v1.11.0 accent-stripe regression |
| [1.11.0](#v1-11-0) | 2026-09-12 | Real-session UI fixes: bubble double-border, Activity tab rename, Help moved to menu |
| [1.10.0](#v1-10-0) | 2026-09-12 | UI & Chat Redesign: brand-accent blending, theme-reactive SVG icons |
| [1.9.0](#v1-9-0) | 2026-09-12 | Live Hazard Monitoring: NASA FIRMS/EONET + GDACS tools, dashboard freshness badges |
| [1.8.3](#v1-8-3) | 2026-09-12 | Patch: release zip was silently missing 4 relocated archive docs |
| [1.8.2](#v1-8-2) | 2026-09-12 | Docs-only: repo reorganization and documentation polish pass |
| [1.8.1](#v1-8-1) | 2026-09-12 | Patch: dashboard OSM-blocked basemap + canvas not following new layers |
| [1.8.0](#v1-8-0) | 2026-09-12 | Cartographic Intelligence: visualization selection, real QA gate, isochrone bands |
| [1.7.1](#v1-7-1) | 2026-09-11 | Patch: portrait print-layout body/footer overlap fixed |
| [1.7.0](#v1-7-0) | 2026-09-11 | Security & Logistics: GDPR export, undo/rollback, sandbox Tier 2, network-aware routing |

The detailed narrative entries below are unchanged -- this table is purely an additive index on
top of them.

<a id="v1-16-0-rc18"></a>
## [1.16.0-rc18] — 2026-10-06 — Release candidate 18 for 1.16.0: fixes from the rc15 and rc17 smoke reports

No breaking changes; QGIS 4.2+. Everything merged after the rc17 build (PRs #204-#206):

- Fix: a fresh full request typed while a clarification question is open no longer gets pasted under the old request as "Details: ...", which ran the old request with the new one underneath. This was behind the wrong clarification questions, previews and the unrelated OpenStreetMap offer in the rc15/rc17 smoke runs. Short answers behave as before.
- Fix: after you click Apply edit on a confirmation card, a request with more than one step ("write the score, then style the layer") resumes once, up to three times per request. Before, it stopped after the confirmed step.
- Fix: a short follow-up such as "EPSG:3857" keeps the tools the previous turn used (at most six, for two turns), so the CRS question can finally be answered with the point being placed (the rc16 retry could not work because the tool was not in the turn's tool list).
- Fix: the reply guard no longer reads metres as millions ("886.49 m" was footnoted as general knowledge), and no longer deletes a table whose rows are found in the tool results just because an unrelated call failed.
- Fix: task matching. A request that names a tool is only matched to a task that uses it; a weak cross-section tie (under 25% keyword coverage) and a single shared word in a long request give no directive; a request that names a loaded layer is not asked "Which facility or service type?"; hub, depot, site and similar words answer that question. The register's own task descriptions match as often as before (453 and 466 of 748, pinned by a test).
- Fix: exporting over a non-empty file the plugin did not write (or one changed since) now asks for confirmation (export_to_csv, export_layer). Hub siting, allocation, route stops and travel-time origins label results with the layer's name field instead of the GeoPackage id. save_project lists temporary layers that come back empty. Raster colour ramps keep their range after a save. buffer_analysis accepts output_name.
- Fix: extract_features_from_imagery downloads its model checkpoint on a background thread (QGIS no longer stops responding for the download), removes a partial file after a failure and retries once, and never prints the signed download URL. Web searches for the latest or current thing carry today's date; script-sandbox "Algorithm not found" errors name the real tools; the agent is nudged once when a tool you named is still not called after four other calls.
- New: plain-language styling. Everyday colour words ("dark red", "pale yellow", "light blue") are resolved to a colour by change_layer_color and the graduated-symbol style instead of being rejected as invalid, and everyday phrasing ("colour the districts by how many people live there", "show where people are crowded", "bigger dots where more people live", "put the names on the map", "make the zones see-through", "highlight the worst affected areas") now reaches the matching style tool. Routing and colour resolution only: whether the model then draws a map a non-GIS reader understands is measured by section 5 of the rc18 run sheet, not claimed. There is still no tool that sets line width from a field.
- Docs: the rc15 and rc17 live smoke reports as received, their triage, and a re-test sheet for this build (docs/SMOKE_RUN_SHEET_rc18_2026-10-06.md).
- Verification: offline suite and ruff pass; the live-QGIS tests passed in CI on QGIS 4.2.2 (PRs #204-#206). NOT hand-tested: the chat flow, task matching and the CRS retry in a real conversation, the continuation after Apply edit, and the imagery download with a real model. No audit issue is closed by this build.

<a id="v1-16-0-rc17"></a>
## [1.16.0-rc17] — 2026-10-06 — Release candidate 17 for 1.16.0: fixes from the rc15 smoke report

No breaking changes; QGIS 4.2+. Everything merged after the rc16 build (PR #204):

- Fix: a request that names a tool ("Use optimal_hub_siting ...", "Run extract_features_from_imagery ...") is only matched to a registered task that uses that tool; otherwise it is sent as typed. In rc15 such requests were matched to unrelated OpenStreetMap export or download tasks and the injected tool list steered the model away (smoke report D01).
- Fix: hub siting, location allocation, route stops and travel-time origins label their results with a name-like field (name, label, title, *_name) instead of the first attribute. On a GeoPackage the first attribute is the primary key, so hubs came back as "1", "2", "3" and the model had to guess which was which (D03). The distances themselves were already correct.
- Fix: save_project lists temporary (memory) layers and warns that they come back empty when the project is reopened (D07).
- Fix: pseudo-colour rasters record their stretch range on the renderer; saved projects had classificationMin/Max = nan and the reopened legend read nan (D08).
- Fix: a failed FastSAM model download no longer prints the signed download URL and says what to do about a partial checkpoint (HTTP 416) (D06). The download still blocks QGIS while it runs; that is not fixed.
- Docs: the rc15 installed-profile smoke report as received and a per-defect triage (docs/RC15_LIVE_SMOKE_REPORT_2026-10-06.md, docs/RC15_SMOKE_TRIAGE_2026-10-06.md). Still open there: no follow-up model turn after Apply edit (D05, needs a decision), the main-thread model download, requests in a cross-section tie that name no tool, D09 and D10.
- Verification: offline suite and ruff pass; the live-QGIS tests passed in CI on QGIS 4.2.2 (PR #204), including new live tests for the raster range and the hub-siting labels and distances. Model-dependent behaviour (task matching in a real chat, the CRS retry from rc16) and the print layout have NOT been hand-tested; no audit issue is closed by this build.

<a id="v1-16-0-rc16"></a>
## [1.16.0-rc16] — 2026-10-06 — Release candidate 16 for 1.16.0: fixes from the rc15 hand test

No breaking changes; QGIS 4.2+. Everything merged after the rc15 build (PR #202):

- Fix: list-returning tools (get_layers, get_attributes) were reported as "Execution failed unexpectedly." since rc12 (a dict-only check in the main-thread wrapper added with audit item #138). Found in the rc15 hand test; they return their results again, confirmed by a new live test in CI on QGIS 4.2.2.
- Fix: when the CRS question for point coordinates (#119) was answered, the model made no tool call and pasted a script instead. The "ask" result now says how to retry and the prompt rule spells it out. Depends on the model; needs a hand re-run.
- Fix: a print layout zoomed to a one-point layer had a zero-size extent ("Scale unavailable", "Invalid scale!", a map stuck on "Rendering map"). The extent is padded around the point (about 2 km, a guess, not a measured value); an empty layer keeps the old fallback. Needs a hand re-run.
- Internal: one tool-result contract (core/agent/tool_result.py) replaces scattered dict checks, and the CI live-test job discovers tests/test_*_live.py by name (a module that does not run must be listed with a reason). test_agent_live is excluded with its reason stated.
- Docs: a blank run sheet for the live smoke test (docs/SMOKE_RUN_SHEET_rc15_2026-10-05.md).
- Verification: offline suite and ruff pass; the live-QGIS tests passed in CI on QGIS 4.2.2 (PR #202). The B1 retry and the layout fix have NOT been hand-tested; no audit issue is closed by this build.

<a id="v1-16-0-rc15"></a>
## [1.16.0-rc15] — 2026-10-05 — Release candidate 15 for 1.16.0: replace-by-name warning

No breaking changes; QGIS 4.2+. Everything merged after the rc14 build (PRs #198-#199):

- New: when a service-area run replaces a same-named result layer that was built with different parameters (strategy, travel cost, speed or direction field, default speed, road layer), the tool result lists what changed and the reply must say so (issue #130, point 3). An identical re-run and layers made before this change stay silent. It reports after the replacement and does not ask first; only the service-area layers record their parameters so far (optimize_delivery_route and the access reach polygons are unchanged).
- Docs: a per-issue hand-verification checklist (docs/ISSUE_VERIFICATION_CHECKLIST_2026-10-05.md) and a corrected README audit-status line (#151 needs a database; #152-#168 addressed in work packages 1-6, some with parts still open; all 32 audit issues stay open until hand-verified).
- Unchanged from rc14: the JIAF 2 analysis-support tools. Flag-formula comparison still awaits the owner's closure and the Annex 4 reader is still an unsupported optional format; do not describe the result as a faithful or complete JIAF implementation.
- Verification: offline suite and ruff pass; the QGIS-side code ran in CI on QGIS 4.2.2, including the new live test for the replacement warning. Nothing in rc15 has been hand-tested in a desktop session, and no audit issue is closed by this build.

<a id="v1-16-0-rc14"></a>
## [1.16.0-rc14] — 2026-10-05 — Release candidate 14 for 1.16.0: JIAF 2 analysis support

No breaking changes; QGIS 4.2+. Everything merged after the rc13 build (PRs #192-#195):

- New: JIAF 2 analysis support (HX5), eight tools -- import_jiaf_inputs, record_jiaf_setup, get_jiaf_setup, compute_jiaf_preliminary, record_jiaf_decisions, get_jiaf_decisions, finalize_jiaf_results, compute_jiaf_patterns. Support for people running the JIAF 2 process: NOT the JIAF method, not endorsed by OCHA or the IASC, and nothing is a final figure. They read sector inputs (OCHA Worksheet 3A/3B read through its Excel tables, HXL tables), compute the preliminary joint PiN (highest sector, never summed or averaged), preliminary severity and the PiN and severity flags, record the multi-partner group's decisions in the project, and keep the preliminary result, review status, final result and justification apart. Intersectoral severity is per unit; there is no national severity.
- New: the flag rules are OCHA's own worksheet formulas (profile ocha_worksheet_2026, read from the official example and template workbooks): ranks of distinct values, a tie for the highest switches flags 2 and 3 off, flag 1 at two missing-or-zero sectors, flag 6 in two parts, and the worksheet's rule that the preliminary PiN is the highest PiN only where severity is above 2. Thresholds come from the workbook's Thresholds cells, else the template defaults, and every result says which. The older reading of the manual is kept as profile manual_reading, comparison only.
- New: incomplete sector coverage is never turned into phase 1 (the unit has no preliminary severity, with lower and upper bounds); missing and zero PiN stay distinct; bulk closure of flags needs a recorded rationale; published final values are shown beside, never over, the calculated ones; blank outcome evidence is not assessable, not passed.
- Change: the Annex 4 sector-template reader is an explicit UNSUPPORTED optional format (implemented from the manual's screenshots, never auto-detected, compatibility unverified).
- Not closed: flag 6 on real output, a zero third-highest PiN in flag 3 (from the formula text, no cached example row), the header/formula mismatch of severity flag 4, a real country's thresholds, and the Yemen analysis team's own flag decisions. Do not describe the result as a faithful or complete JIAF implementation.
- Verification: offline suite and ruff pass; the QGIS-side code ran in CI on QGIS 4.2.2 (live tests written without a local QGIS). The check against OCHA's example workbook (all flag columns, severity and preliminary PiN of its 6 units) and against the Yemen worksheet was run locally; those workbooks are not committed. Nothing in rc14 has been hand-tested in a desktop session, and no audit issue is closed by this build.

<a id="v1-16-0-rc13"></a>
## [1.16.0-rc13] — 2026-10-04 — Release candidate 13 for 1.16.0: humanitarian map looks and new analysis tools

No breaking changes; QGIS 4.2+. Everything merged after the rc12 build (PRs #183-#189):

- New: automatic humanitarian map looks (HX1) -- apply_humanitarian_look draws severity (five classes matching the tool's own), people-in-need / exposure (quantile classes, zero its own class), presence-gap and rank results; the analysis tools return a map_look hint; footprints, OSM layers, roads and detected features get humanitarian styles; a situation-report layout.
- Change: the humanitarian task register was corrected (HX2) -- the new H1-H6 tools are attached to the tasks they serve, and a coverage test keeps every non-guidance task tied to a tool that can acquire its data.
- New: calculate_allocation_envelope (HX3a) -- splits a budget you supply over areas by need (optionally x population) with ceiling, floor, need threshold and rounding; areas with missing values are excluded and listed, never imputed; an advisory calculation, not a recommendation of who should receive what.
- New: import_humanitarian_table (HX3b) -- file-based import and validation of IPC phase, INFORM Risk and UNOSAT damage tables with a P-code join to an admin layer. UNVERIFIED: the recognised column names were not checked against real HDX files; the result shows the mapping used and an explicit mapping overrides it.
- New: analyze_critical_links (HX3c) -- screens a road network for bottlenecks (how much origin-to-destination demand has its shortest path through each segment). A screening of dependence, not a closure simulation or traffic forecast. Performance on a national network has not been measured.
- Change: the in-plugin Help now shows what's new in this version and lists the humanitarian tools by workflow, with tool and task counts read from the live registries; the README, user guide and Help are kept in step with each version by a test.
- Verification: offline suite and ruff pass; the QGIS-side code ran in CI on QGIS 4.2.2 (live tests written without a local QGIS). Nothing in rc13 has been hand-tested in a desktop session, and no audit issue is closed by this build.

<a id="v1-16-0-rc12"></a>
## [1.16.0-rc12] — 2026-10-02 — Release candidate 12 for 1.16.0: fixes from the first full hands-on rc11 smoke test

No breaking changes; QGIS 4.2+. Fixes merged in PR #126 after an operator ran rc11 against real Yemen data in QGIS 4.2.2 (issues #119-#132); see the `v1.16.0-rc12` block in `metadata.txt` for the list and the open items. Verification: offline suite plus the `qgis-live-tests` job on QGIS 4.2.2. Not verified: none of these fixes has been re-run by hand. One correction to the rc11 entry below, which is left as written: it says the band-statistics deprecation warning was gone, but the operator's log still showed it at `raster_tools.py` line 1255; it is only log noise and is still open.

**Added to rc12 after the entry above was first written (2026-10-04).** Same version, rebuilt: the architectural-audit P1 fixes (issues #137-#151: no code execution through Processing parameters, owned and checked edit sessions, SI-unit area and length, ellipsoidal distances, safer script-isolation adoption, an egress gate and lineage that see SQL, workflow and list arguments, project-bound agent turns, main-thread tool state capture, fail-closed read-only SQL); the hydrology engineering tools; the #75 unsupported-claims footnote; and six humanitarian tools -- `apply_network_barriers`, `evaluate_forecast_trigger`, `generate_mapping_task_grid`, `design_sampling_frame`, `calculate_mcda_ranking`, `aggregate_survey_indicator` -- with map looks for the task grid, barrier segments, sample points, hazard alerts and difference rasters, plus `docs/HUMANITARIAN_TOOLS_CATALOGUE.md`. Verification: offline suite and the `qgis-live-tests` job on QGIS 4.2.2 (live tests for the newest code were written without a local QGIS); not verified: none of it has been re-run by hand, and 17 further audit findings (#152-#168) are open.

**Added to rc12 on 2026-10-04, after the audit work (issues #152-#168, PRs #175-#181).** Same version, rebuilt once more. Behaviour changes worth reading: a road "blocked" by `apply_network_barriers` (or given passability 0 in `build_composite_impedance_field`) is now **removed from the network** by `calculate_service_area`, `travel_time_matrix` and `optimize_delivery_route` for either strategy (it used to stay crossable at 0.1 km/h); a closed road is a negative speed, and 0 or empty still means "unset" -- speed fields written by earlier builds must be regenerated; the native service-area algorithm's Fastest cost is now in seconds like the plugin tool (it was 3,600 times too large) and its facilities are transformed into the network CRS; `estimate_population_exposure` no longer adds fields to your layer and reports one total per zone with feature ids; point counting uses intersects and the lowest feature id and reports matched/ambiguous/unmatched; raster arithmetic refuses rasters that are not on one pixel grid; elevation, slope and minimum-area use metres; the large travel-time matrix charges partial-edge costs and both matrix paths are keyed by feature id; a failing layout re-run keeps the old layout and atlas pages never overwrite each other; unload removes the translator and the isolation worker; Python 3.10 is the declared floor. Histogram equalisation and unsupervised classification no longer need SAGA/GDAL tools missing from QGIS 4.2.2. New disclosure text in Settings and the sensitivity dialog about what a cloud provider always sees of a layer. Verification: offline suite and the `qgis-live-tests` job on QGIS 4.2.2; not verified: none of it has been re-run by hand (hand checks: `docs/RC12_LIVE_TEST_AND_AUDIT_PLAN_2026-10-04.md` section I). Still open: #151 (PostGIS) and the parts listed there.

<a id="v1-16-0-rc11"></a>
## [1.16.0-rc11] — 2026-10-01 — Release candidate 11 for 1.16.0: fixes from the first hands-on rc10 smoke test

No breaking changes; QGIS 4.2+. Fixes merged as PRs #113-#117 after an operator ran rc10 against real Yemen data in QGIS 4.2.2; see the `v1.16.0-rc11` block in `metadata.txt` for the list. Verification: offline suite plus the `qgis-live-tests` job on QGIS 4.2.2. Not verified: none of these fixes has been re-run by hand; the model's reply text can still contain claims no tool produced.

<a id="v1-16-0-rc10"></a>
## [1.16.0-rc10] — 2026-10-01 — Release candidate 10 for 1.16.0: rc9 plus the visualization round

No breaking changes; QGIS 4.2+. rc9 was never published as its own release, so this entry also covers it: see `metadata.txt`
for the full rc9 list (F03-F25 fixes). New since rc9: see the `v1.16.0-rc10` block in `metadata.txt` and
`docs/VISUALIZATION_AND_ANALYSIS_GAP_ANALYSIS_2026-10-01.md`. Verification: offline suite plus the `qgis-live-tests` job on
QGIS 4.2.2; not verified: how any colour or layout looks on a real canvas/page. Smoke procedure:
`docs/RC10_SMOKE_TEST_2026-10-01.md`.

<a id="v1-16-0-rc8"></a>
## [1.16.0-rc8] — 2026-09-30 — Release candidate 8 for 1.16.0: fixes from the rc7 interactive smoke test

Source: `docs/RC7_SMOKE_TEST_FINDINGS_2026-09-30.md` (F01-F25; GitHub #72 umbrella, #73-#97). No breaking changes; QGIS 4.2+.
Verification level: offline unit tests (full suite green, ruff clean). Nothing below was re-run in a live
QGIS session; `tests/test_rc8_live.py` is written but has not yet executed in CI.

**Trust and safety**
- F02: cloud-data (egress) gate previews register a confirmable task, survive a re-plan, and `confirmed` is only passed to tools that accept it.
- F03/F14: `core/services/response_guard.py` annotates not-run tool results and appends "No data was retrieved" when a reply presents data with no successful tool behind it; prompt rules 50-52.
- F16: destructive confirmations need an explicit word (`core/ui/reply_vocab.py`); typed confirmations expire after 10 minutes (the Activity-tab button still works).
- F23: `store_project_memory`/`store_global_memory` refuse coordinate pairs.

**Data correctness**
- F04/F20: `add_point_layer(crs=...)` converts in code (`core/agent/coordinates.py`); implausible request coordinates are no longer read as project CRS.
- F05: `calculate_service_area` vets `speed_field`, flags a metre/hour mix-up, never replaces a good layer with a zero-length one.
- F01: isolated scripts no longer rename the live project or clear its dirty flag.

**UX / exports**
- F10 nudge only for user-named outputs; F11 highlights removed from the canvas scene; F12 dashboard location/notice; F13 CSV BOM + X/Y; F06 temporary-layer note; F15 sensitivity confirmation; F24 Memory dialog empty state.

**Still open:** F07, F08, F09, F19, F22, F25, per-turn token display, marker clustering; `SECURITY.md` now documents schema exposure and unprompted downloads.

<a id="v1-16-0-rc7"></a>
## [1.16.0-rc7] — 2026-09-28 — Release candidate 7 for 1.16.0: isolation-worker Windows fixes, local-data UX redesign, georeferencing transforms, smart-mapping memory

Everything merged to `main` since rc6 (PRs #43–#69). No breaking changes; still QGIS 4.2+.

**Fixes, from a live Windows QGIS testing session (`execute_pyqgis_script`'s isolation worker):**
- A wrong interpreter could resolve to the QGIS application binary itself, hanging silently to the
  full 60s timeout with no diagnostic — now refused fast, before ever attempting to spawn it.
- `ModuleNotFoundError: No module named 'qgis'` on a genuinely correct interpreter — QGIS's own
  C++ bootstrap adds the `qgis` bindings to the embedded interpreter's `sys.path` at startup but
  never exports it as `PYTHONPATH`; the worker now inherits the live plugin process's own resolved
  `sys.path`.
- `select.select()` on a pipe silently failed on Windows (sockets only), losing worker stderr for
  diagnostics; rewritten to a kill-then-read pattern that needs no `select()` at all.
- The 20s startup handshake timeout was sized off a lightweight CI Docker image, too short for a
  real desktop QGIS cold start with more providers to register and antivirus scanning a freshly
  spawned `python.exe`; widened to 60s.
- A blank Windows console window briefly appeared during the worker's spawn (Windows' default
  behavior for a console-subsystem process spawned from a GUI parent); suppressed via
  `CREATE_NO_WINDOW`.

**Fixes, local-data download flow:**
- A one-letter typo in a "download"/"online" reply ("dowmload") lost track of the original pending
  request entirely, derailing the rest of the turn onto an unrelated fetch — replies within a
  close-match ratio of the two headline words now resolve correctly.
- The Geofabrik region offered could be the wrong one (a neighboring country, or the literal
  meaningless coordinate "(0.000, 0.000)") because the offer was built from the QGIS canvas's
  current view centre rather than the coordinate the request itself named — now prefers a
  coordinate found in the request text, falling back to the canvas centre only when none is named.
- **Redesigned the interaction entirely**, per direct user feedback that a free-text "reply
  download or online" question interrupted every eligible request, even the routine case with no
  real decision to make: a background connectivity probe now lets the routine case (good
  connection, a reasonable/known extract size) download silently with only an informational note;
  a large/unknown size, or a poor/offline connection regardless of size, asks via clickable chips
  (not free text) — naming the slow/offline reason when that's why it's asking, since field users
  in low-connectivity areas need an explicit choice rather than a silent guess that might hang.

**Fixes, `calculate_service_area`:**
- The single-band hull polygon (the common case — one scalar travel-cost value) got zero styling
  at all, unlike its already-styled line/multi-band siblings — now gets the same
  `proximity_buffer` treatment `buffer_analysis`'s polygon output already uses.
- Re-running the same analysis, or a follow-up reusing the same origin, stacked a new
  identically-named layer on top of the old one every time instead of replacing it (`QgsProject.
  addMapLayer()` doesn't deduplicate by name) — now removes any stale same-named layer first.

**Fix, exports:** an exported CSV from a Processing-algorithm intermediate output got an
unreadable, auto-generated filename (`out_<name>_<uuid>.csv`) sitting in a temp directory QGIS
could clean up at any time, and could not reliably be opened afterward. Exports with no explicit
output path now always land under the project's own `data/20_processed` folder (or a per-profile
QGIS folder for an unsaved project) with a clean, sanitized name — never scattered across the OS,
never an ugly temp basename.

**Security:**
- `execute_pyqgis_script` now runs in a separate, persistent worker process holding its own
  `QgsApplication`, with no Python-level access to this plugin's in-memory credentials or
  conversation history (`IMPLEMENTATION_TRACKER.md` §1.11 Phase 1) — the existing AST/builtins
  sandbox still runs inside the worker as defense in depth, unchanged.
- The cloud-provider data-protection egress gate's remaining `§1.4` deployment decisions (default
  mode, override policy, layer-classification ownership, cloud script-execution scope,
  provider-switch history, policy-setting location) are answered and documented — 5 of 6 resolved
  directly, one deliberately left for a deployment-specific DPIA sign-off.

**New:**
- A direct "Sensitivity" UI control (a new dock header button, alongside Memory/Settings) for
  tagging a loaded layer's data classification — previously reachable only by asking the model to
  do it in chat.
- `georeference_image` gained a `transform_type` parameter (`"tps"` default/unchanged, `"linear"`,
  `"helmert"`), matching QGIS Georeferencer's own transform vocabulary, and now reports **RMSE**
  plus `scale`/`rotation` so alignment quality is visible instead of silently unreported.
- Analysis-tool output styling is now remembered per project: a follow-up request producing a
  similar output (e.g. the same buffer type for a different area) visually matches the one before
  it, instead of always reverting to one hardcoded default per output role. Closes the
  design-state-memory half of `IMPLEMENTATION_TRACKER.md` §1.16 "smart mapping" — the
  request-validator/task-planner/tool-router half of that architecture is deliberately not built
  yet, flagged there for its own dedicated pass rather than guessed at in this one.

**Fix:** map-dashboard feature sampling now spreads evenly across a whole over-cap dataset instead
of only the first N features (which could silently show only one corner of the data for a source
sorted/grouped by region); `estimate_road_speeds` can now be given a country for a more realistic
per-road-class speed default than one flat global assumption.

**Docs/governance:** release tags now use the `cartogen-ai-v<version>` prefix, not
`commercial-plugin-v<version>` (which read as a proprietary-licensing signal on a repo that has
been GPL v2 since its first tag); personal contact info and internal-only business/strategy
documents removed from this open-source repo; README/metadata repo links pointed at this canonical
repo instead of a stale sibling; `pyproject.toml`'s version kept in sync with `metadata.txt`.

Full automated suite: 2,313 tests passing, 139 skipped. Zero Ruff violations. **Not verified in
this environment:** neither GDAL nor numpy is installed in this sandbox, so `georeference_image`'s
actual `gdal.Open`/`CreateCopy`/`SetGeoTransform` I/O path is untested end-to-end (only the
transform-fitting math itself is unit-tested, with exact-recovery assertions); no live QGIS session
confirmed the remembered-styling feature's visual consistency across two real follow-up requests
(the recall/record logic itself is fully unit-tested). The isolation-worker and local-data fixes
were reported and verified against a real Windows QGIS 4.2.2 session by the user directly; the
local-data redesign's live-QGIS test suite (`qgis-live-tests` CI, real QGIS 4.2.2 Docker image)
passed for real.

<a id="v1-16-0-rc6"></a>
## [1.16.0-rc6] — 2026-09-27 — Release candidate 6 for 1.16.0: task-matcher/OSM-ingest fixes, network-analysis perf, §1.10 closed

Everything merged to `main` since rc5 (PRs #24–#41). No breaking changes; still QGIS 4.2+.

**Fixes:**
- **Task-matcher threshold recognition.** A query naming a time or distance threshold in words
  ("beyond one hour's travel", "2 hours", "30 minutes") was silently overridden with a 5 km
  distance default, because the pattern only matched digits with a singular unit. Now recognizes
  spelled-out numbers and plurals. Live-reported: "Health facilities beyond one hour's travel"
  produced "Given: threshold = 5 km" instead of respecting the stated 1-hour limit.
- **OSM road ingest.** `ingest_osm_features` for a linear key (`highway`/`railway`/`waterway`/
  `aerialway`) now builds real `LineString` geometry from a way's vertices, instead of turning every
  vertex into its own point with no lines at all. A point-typed layer passed as a road network to
  `calculate_service_area`/`travel_time_matrix`/`optimize_delivery_route`/`population_access_gap`
  is now refused with a clear error instead of silently producing meaningless output.
- **Overpass resilience.** A transient Overpass failure (`504`, `429`) is now retried with backoff
  before it costs a whole tool call for nothing — the root cause of several live reports where a
  request burned its entire tool-call budget on repeated hazard/facility-ingest failures.
- **In-place upgrade stale-module bug.** Reinstalling over a running plugin folder (upgrade or
  reinstall to the same path) could fail with a stale-module `ImportError` (e.g. `cannot import
  name 'SETTINGS_PROJECT_INSPECTOR_ENABLED'`) because cached `cartogen_ai.*` modules were only
  evicted when the plugin's own path changed. Now evicted unconditionally on every load.
- **Automatic model selection.** Assigning a model from outside a provider client's fallback list
  (the "auto" picker) never actually took effect — every request still went to the configured
  default (the priciest model, on some providers). Fixed, and the picker now never escalates to an
  expensive or special-purpose (deep-research, robotics, computer-use, etc.) model; it only ever
  steps down to something cheaper.
- **Network analysis correctness.** Service area / travel-time / delivery-route calls now measure
  distance and time in real metres/hours regardless of the layers' CRS or whether the project has
  an ellipsoid configured (previously: degrees on a lat/long layer, ~15% error on Web Mercator).
  An origin/stop point in a different CRS than the road network no longer silently routes from the
  wrong location.
- **Network analysis performance.** A large road network (100k+ roads) no longer freezes QGIS
  during routing — large calls now run on a background thread with progress and a Stop button.
  `calculate_service_area` routes only over roads that can actually be reached within the requested
  cost (exact, not approximate — same result, up to ~150x faster on a real 161k-road network).
  `optimize_delivery_route`'s stop-to-stop distance matrix now skips half its calls when the
  network has no one-way data (the route is reversible either way).
- **GDACS/EONET alert selection.** Both tools now store each alert/event's ID as an `event_id`
  layer field, so a request naming specific alerts ("buffer around 5189969,1563615") can select
  them by ID. `buffer_analysis` gained `only_selected`, so an operation can be scoped to a
  selection instead of always running over the whole layer.

**New, opt-in — off by default, never invoked automatically:**
- `estimate_road_speeds`: writes an assumed per-road-class speed field onto a road network when
  real speed-limit data is sparse (common: one real dataset had `maxspeed` on 0.9% of roads). The
  model is told to present the result as an estimate, not the network's real posted limits.
- Before a road-network-dependent request, the assistant now offers to download a full local
  country/region OSM extract (Geofabrik) once, instead of relying on the live, rate-limited
  Overpass API for a small bounding box every time.

**Docs:** `docs/IMPLEMENTATION_TRACKER.md` §1.10 (exact-ZIP clean-profile install/upgrade test) is
closed — verified in a real, live QGIS 4.2.2 desktop session (not just headless tool code) that a
fresh install and an in-place upgrade both load cleanly, with the toolbar icon and Plugins-menu
entry confirmed as real, rendered Qt widgets. Five scoping documents evaluate third-party libraries
against this project's own real pain points (RestrictedPython, Presidio, semantic-router, LanceDB/
Chroma, Instructor/Outlines); one small, verified fold into the sandbox's denylist shipped, the
rest recommend against adoption or further prototyping — none add a new dependency.

Full automated suite: 2,238 tests passing. Zero Ruff violations.

<a id="v1-16-0-rc5"></a>
## [1.16.0-rc5] — 2026-09-24 — Release candidate 5 for 1.16.0: QGIS 4.2+ only, opt-in data-protection safeguards

Everything merged to `main` since rc4 (PRs #4–#22), cut as a candidate so the remaining
stable-release check (`docs/IMPLEMENTATION_TRACKER.md` §1.10) runs on the code that would ship.

**Breaking: QGIS 4.2 or later required.** `metadata.txt` `qgisMinimumVersion` 3.28 → 4.2. QGIS 3.x
will treat this release as incompatible, so users there stay on the version they already have.
CI's live-QGIS tests now run on 4.2.2 only. The internal 3.x compatibility helpers are kept (on 4.x
they already take the 4.x path) but are now unsupported, untested fallbacks.

**New, and all off by default** — nothing below changes behaviour until switched on:
- **Cloud data protection** (Settings). When a non-local AI provider is selected, blocks (or warns
  about) a tool call or file attachment that would send a layer tagged `RESTRICTED`/`SENSITIVE`, or
  an untagged layer derived from one. Strict mode also protects untagged layers. It is a safeguard
  against mistakes, not against someone who edits their own settings — see `SECURITY.md`, "DPIA
  determination and deployment constraints", for exactly what it does and doesn't cover.
- **Plan-validation gate.** Requires the model to state a plan (`create_plan`) once per turn before
  any DELETE- or PUBLISH-classified tool.
- **Project Inspector.** Adds the project's print layouts, saved map themes and metadata to the
  model's context.

**New tool:** `create_project_folder_structure`, an opt-in, non-destructive project folder layout
(`data/00_raw` for immutable source data through `exports/` and `logs/`). 178 tools in total.

**Behaviour change:** `run_allowlisted_processing_algorithm` now adds an output layer hidden when
no `new_layer_name` is given, treating it as an intermediate step; naming the output keeps it
visible. This addresses a live report of scratch layers cluttering the map.

**Fix: loading from a URL that doesn't serve geodata** (#19). A live report on QGIS 4.2.2 showed
only `Invalid layer: C:\...\Temp\tmp_2kgn_72.geojson` after a URL load. The error now names the
URL rather than the temp copy, and says what the URL actually returned: an HTML page (with a hint
to use GitHub's raw link instead of a `/blob/` page), a zip, XML, JSON that isn't GeoJSON (top-level
key names only, never values), or an empty file. A layer loaded from a URL is named after the URL.
Verified live in QGIS 4.2.2 against a real GitHub `/blob/` page, a real JSON API response and a real
raw GeoJSON link.

**Security.** The `execute_pyqgis_script` sandbox now also blocks `QgsProject.write()` (a project
write to any path, bypassing the confirmation gate) and `QgsApplication.authManager()` (auth
config ID enumeration); both were confirmed exploitable live first. A new always-on prompt rule
(49) tells the model never to store personal data in global memory. With data protection on, the
model can no longer lower a layer's sensitivity tag without the user's confirmation.

**Docs.** GDPR: the DPO determination is recorded (DPIA required, approved with conditions); the
signature on `docs/DPIA_SCREENING_WORKSHEET.docx` is still pending. Scoping documents for process
isolation of `execute_pyqgis_script` (with a real benchmark: ~5 s per cold call, memory layers lose
their data on save) and for the data-protection gate. The README now warns to install the release
asset, not GitHub's source zip.

**Verification.** Full automated suite: 2,103 tests passing, 48 skipped. Zero Ruff violations.
The headless smoke check against this candidate's built zip is recorded in
`docs/RELEASE_SMOKE_TEST.md`'s run log. **Still not done:** §1.10's interactive check in a real
QGIS window (toolbar, menu, clean startup, in-place upgrade).

<a id="v1-16-0-rc4"></a>
## [1.16.0-rc4] — 2026-09-23 — Release candidate 4 for 1.16.0: codebase security review with live adversarial testing

A general codebase review flagged `execute_pyqgis_script`'s AST-based sandbox and
`execute_read_only_sql`'s keyword-blocklist guard as the highest-risk paths — both handle
model-influenced input inside the QGIS process. This candidate acts on that review with live
adversarial testing against a real QGIS 4.2.2 session, not just static reading.

**Sandbox: 2 real bypasses found and fixed.** Both confirmed live before the fix, then
independently re-verified live after it.

1. `qgis.utils` and `processing` — both required, never-blocked modules — import `os`/`sys` at
   module scope, leaving them reachable as plain attributes no matter what the script's own
   `import` statements do: `import qgis.utils; qgis.utils.os.getcwd()` ran with no blocked import
   anywhere in the script. `qgis.utils.sys.modules` then handed back every already-loaded module
   object by name — `subprocess`, `socket`, and `ctypes` were each confirmed reachable this way, a
   full process/network escape via an allowed module's own `sys` import.
2. This plugin's own package was never blocked, so a script could
   `from cartogen_ai.infrastructure.auth import CredentialManager` and read the live in-memory
   session credential store directly (the credential-storage policy from rc2 protects against disk
   persistence, not against a malicious script reading memory at runtime).

Fixed by blocking the `os`/`sys`/`modules` *attribute names* — closing the pattern for any allowed
module that might expose them, not just the two found — and adding `cartogen_ai` to the blocked-
import list, since no legitimate PyQGIS script needs this plugin's own internals (QGIS objects are
always passed in via `local_env`). 6 new regression tests, validator-level and end-to-end through
`execute_pyqgis_script` itself, matching this file's existing bypass-fix pattern.

**Process isolation recorded as the intended real fix, not more denylist patching.** By explicit
decision, this is the same shape of gap every prior `system_tools.py` bypass-fix has been — the
attack surface ("any capability-bearing object reachable through an allowed name") is structurally
unbounded, not a finite list to exhaust. `docs/IMPLEMENTATION_TRACKER.md` §1.11 records this as the
architecture decision needed, along with 3 findings from the same adversarial pass deliberately
left open rather than patched piecemeal: unrestricted `QgsProject.write()` to any path from inside
a script with no confirmation gate, enumerable `QgsApplication.authManager().configIds()` with no
gate, and an unverified question of whether a script can invoke a confirmation-gated tool directly
with a forged `confirmed=True`. `execute_read_only_sql`'s keyword-blocklist guard was reviewed
alongside the sandbox but not live-tested against a real PostGIS connection this pass (none
available) — its string-literal false-positive risk and reliance on DB-level read-only enforcement
are noted in §1.11 as open questions, not confirmed bypasses.

**Observability: 10 best-effort `except Exception: pass` sites now leave a trace.** The same
silent-failure class that let the `QgsLabelObstacleSettings` `NameError` (rc3) hide behind a
generic error message existed at 10 other sites whose fallback behavior matters to the user —
logistics distance/CRS-warning fallbacks, HDX P-code field detection, layer geometry-kind lookup,
the memory DB path lookup, and both snapshot-restore failure paths (a failed rollback can leave a
layer stuck in edit mode). Each now emits a content-free `log_event` (site label and error class
only) while keeping its existing fallback behavior unchanged. Genuinely benign guards — logger
internals, UI callbacks, provider error-body parsing, cache eviction hooks — were left as-is.

**Documentation: `CLAUDE.md` refreshed.** It still described the pre-Phase-11 layout
(`agent/agent.py`, `agent/providers/`), said CI has no QGIS at all, and omitted the Ruff/packaging
checks — all three were false and would have misled the next session working in this repo. Updated
to the real `core/` + `infrastructure/` + `processing/` layout, the live-QGIS `qgis-live-tests` CI
job, and the logging/credential rules from rc2/rc3.

**Verification & Testing**: 1,987 automated tests passing (0 failures, 44 skipped), up from 1,981
in rc3. Zero Ruff violations. Both `qgis-live-tests` CI legs confirmed green.

<a id="v1-16-0-rc3"></a>
## [1.16.0-rc3] — 2026-09-21 — Release candidate 3 for 1.16.0: Ruff and CI-stability gates closed for real

`v1.16.0-rc2`'s own changelog entry left two stable-release gates explicitly open: a pre-existing
Ruff lint failure, and a CI post-test segmentation fault that had only been waived, not
root-caused. This candidate closes both, each through multiple rounds of independent review that
caught real gaps in earlier attempts before they shipped.

**Ruff: 125 violations fixed to 0, not accepted as documented technical debt.** Every finding was
individually verified against live usage (grep for other references) before removal, rather than
trusting `ruff --fix` blindly — which caught one real false positive from the tool itself: `--fix`
removed `requests` imports from 5 provider-client files as "unused," but `tests/test_providers.py`
patches e.g. `cartogen_ai.infrastructure.providers.gemini.requests.get`, which requires the name
to still be importable in that module even though nothing in the file calls it directly (the
actual HTTP calls route through `providers/base.py`'s shared `requests` object, and patching that
same object's attribute via any importer's name still affects every caller). Restored with a
`# noqa: F401` explaining why in the 5 files tests depend on; left removed in the one file
(`cartogen.py`) no test patches.

A real bug was found and fixed along the way: `vector_tools.py`'s `apply_labels()` referenced
`QgsLabelObstacleSettings` for polygon obstacle-avoidance labeling without ever importing it — a
`NameError` on every real call to that code path, silently caught by the tool's own broad
exception handling and returned as a generic error rather than crashing visibly. Live-confirmed
the fix against real QGIS 4.2.2: `apply_labels()` on a polygon layer now succeeds.

**CI segmentation fault: root-caused and fixed, not waived.** An earlier pass had wrapped the
crash in a waiver, first assuming it was specific to the `4.2.2` docker image's Qt build, then
(after `release-3_28` also hit it) blaming a numpy/matplotlib ABI mismatch already present in that
image. A fourth review correctly refused to accept either explanation without evidence, and asked
for the standard the review itself proposed: pin the images by immutable digest, reproduce the
crash with a plugin-code-free control process, and only waive if that control also crashes with
the identical signature. Doing that work — not just writing a more convincing waiver — surfaced
the real cause: ~40 test methods across `test_chat_widget_live.py`/`test_plugin_main_live.py` each
create a real `QDockWidget` via `addCleanup(dock.close)`. `.close()` alone never destroys the
underlying C++ object, so ~40 live-but-closed widgets (each owning child `QTimer`s) accumulated
for the whole run and only got garbage-collected whenever Python's own refcounting happened to
drop the last reference — landing unpredictably, evidently sometimes inside the interpreter's own
shutdown sequence. Reproduced independently on Windows/QGIS 4.2.2 locally AND Linux CI, ruling out
both prior environment-specific theories. Fixed with an explicit `gc.collect()` + a short Qt
event-loop pump before `QgsApplication.exitQgis()`, so any `deleteLater()`-deferred C++ destruction
actually runs while `QApplication` is still fully alive. Verified 4/4 clean local runs after the
fix versus a reliable crash before it; confirmed in CI with zero `Segmentation fault`s on either
image and the fallback waiver never triggering.

Two smaller findings from the same review rounds were also fixed: a CI teardown script that caught
its own cleanup/`exitQgis()` exceptions but still reported success if test assertions alone
passed (now requires both to succeed), and a workflow comment that read as self-contradictory
after the digest-pinning fix landed (reworded to past tense with a pointer to the current state).

**CI hardening beyond the crash fix itself:** both `qgis-live-tests` images (`4.2.2`,
`release-3_28`) are now pinned by immutable Docker manifest digest instead of a floating tag —
`release-3_28`'s own moving tag had drifted mid-session and briefly reintroduced the crash under a
different underlying trigger, which is exactly the failure mode a digest pin exists to prevent. A
plugin-code-free control process (`tests/_ci_qgis_control_process.py`) now runs alongside the real
live-test step, so any future reliance on the fallback waiver is evidence-conditioned against that
same run's control result, not asserted independently.

**Explicitly still open, not claimed done:** the exact-ZIP clean-profile install/upgrade-from-
`1.15.6` test needs a real interactive QGIS GUI session this project's development environment
cannot provide (`docs/IMPLEMENTATION_TRACKER.md` §1.10) — the only remaining item before a stable
production-release decision.

**Verification & Testing**: 1,981 automated tests passing (0 failures, 44 skipped), up from 1,978
in rc2. Zero Ruff violations (down from 125). Both `qgis-live-tests` CI legs confirmed green in an
actual GitHub Actions run, with the segfault waiver's fallback logic never triggering.

<a id="v1-16-0-rc2"></a>
## [1.16.0-rc2] — 2026-09-20 — Release candidate 2 for 1.16.0: security/privacy remediation from a 15-section production-standard audit

A third-party audit against a supplied 15-section commercial-QGIS-plugin production standard,
checked against `v1.16.0-rc1`, returned: QGIS 4.2.2 functional RC = GO, stable production release
= NO-GO, with 3 confirmed P1 code bugs plus 2 P1 release-process gaps. Every finding was
independently re-verified against live code before any fix was applied, and the first fix pass was
itself caught overstating its own results by a second independent review — corrected before
shipping, not after. Two open product-policy questions the second review surfaced (plaintext
credential persistence, raw-content logging) were resolved to the strict option, by explicit
instruction, rather than left as documented exceptions.

**QAction lifecycle leak — fixed and live-confirmed.** `plugin_main.py`'s `unload()` used to call
only `removePluginMenu`/`removeToolBarIcon`, which detach an action from QGIS's menu/toolbar
widgets without disconnecting its `triggered` signal or destroying the `QAction` — confirmed via a
live QGIS 4.2.2 probe that a load→unload→reload cycle left the previous instance's actions alive,
still connected, still parented to `iface.mainWindow()`. Now disconnects each signal and calls
`deleteLater()` before clearing bookkeeping. New `tests/test_plugin_main_live.py` (4 tests) drives
a real load→unload→reload cycle and confirms via `qgis.PyQt.sip.isdeleted` that the first
instance's actions are actually gone — live-confirmed 4/4 passing against real QGIS 4.2.2.

**Plaintext credential persistence removed entirely — strict policy, not an opt-in.**
`infrastructure/auth.py`'s `save_credential()` used to silently persist the API key to plaintext
`QgsSettings` (the Windows registry) any time QGIS's encrypted `QgsAuthManager` was
unavailable/disabled. A first fix pass added an opt-in, consent-gated plaintext path; a second
independent review correctly pointed out that informed consent doesn't satisfy the audit's literal
standard ("do not store tokens in plain `QgsSettings`"). By explicit instruction, the opt-in path
is removed entirely: session-only in-memory storage (never touches disk, gone on restart) is now
the only fallback, unconditionally. `ui/settings_dialog.py` states plainly that a key will need
re-entry after restart, with no alternative offered. Migration code that only reads/removes legacy
plaintext keys written by older versions of this file is retained, so existing users' already-saved
keys still work and get cleaned up opportunistically on a successful encrypted save.

**Logging moved to structured, metadata-only by default.** `core/logger.py`'s `log_info`/
`log_warning`/`log_error` used to forward whatever string a caller built — including tool call
arguments/results and the user's own query/the model's response (as truncated `print()`/`log_info`
calls) — with call sites in `agent_orchestrator.py` and `task_runner.py` passing free-form content
that could embed a key, token, coordinates, file paths, or other sensitive data. A first fix pass
added regex-based secret-pattern redaction; a second independent review correctly pointed out this
only stripped known secret *shapes* and left the broader content (names, coordinates, prompts)
logged. By explicit instruction, logging now defaults to `log_event()`: structured, metadata-only
logging with a hard field allowlist (tool name, status, duration, correlation ID, provider, error
class, counts) — any other field is silently dropped, not passed through. Zero raw prompt,
response, tool-argument, or tool-result content is logged by default anymore. A new explicit,
OFF-by-default `log_diagnostic()` escape hatch exists for a developer actively debugging locally,
gated behind a setting that is never on by default and prints a visible warning on first use.

**CI matrix expanded and actually validated green, not just authored.** The existing test job
gained a `windows-latest` leg; a new `qgis-live-tests` job runs the live-QGIS test suite inside the
official `qgis/qgis` docker images at both ends of `metadata.txt`'s declared `3.28`–`4.99` range
(`release-3_28` and a pinned `4.2.2` — deliberately not `latest`, confirmed via the Docker Hub API
to be an unreleased nightly build, not a stable release), plus a smoke test that builds the actual
release zip and imports from the extracted artifact instead of the dev tree. Validating these jobs
surfaced and fixed 3 real, distinct environment bugs: a `pip install --upgrade pip` failure on the
`4.2.2` image (Debian-packaged pip has no RECORD file, refuses to uninstall itself), a
`--break-system-packages` flag disagreement between the two pinned images (one requires it, the
other doesn't recognize it), and an image-specific Qt interpreter-shutdown segfault on `4.2.2`
occurring immediately *after* all 42 live tests had already passed. Final confirmed-green run:
https://github.com/cartogenai-glitch/CARTOGEN-AI/actions/runs/35534755563

**Explicitly still open, not claimed done:**
- The exact-ZIP clean-profile install/upgrade-from-`1.15.6` test still needs a real interactive
  QGIS GUI session this project's development sandbox cannot provide — tracked as
  `docs/IMPLEMENTATION_TRACKER.md` §1.10.
- A pre-existing repo-wide Ruff lint failure (dozens of unused-import/ambiguous-variable findings,
  confirmed present already at the `v1.16.0-rc1` tag commit, unrelated to this candidate) is
  tracked as a separate cleanup task rather than folded into this security-focused release.

**Verification & Testing**: 1,978 automated tests passing (0 failures, 44 skipped), up from 1,973
in rc1. Live QGIS 4.2.2 confirmation run for the new plugin-lifecycle tests: 4/4 passing. Both
pinned `qgis-live-tests` CI jobs confirmed green end-to-end in an actual GitHub Actions run.

<a id="v1-16-0-rc1"></a>
## [1.16.0-rc1] — 2026-09-20 — Release candidate 1 for 1.16.0: renumbered forward from stable 1.15.6, fixing a real version-ordering defect

**Why this version jumps from `1.5.7-rc5` to `1.16.0-rc1`, not `1.5.7-rc6`.** An independent
external review of the just-published `v1.5.7-rc5` release checked it against QGIS's own
`pyplugin_installer.version_compare.compareVersions()` and found `"1.5.7-rc5"` compares as
**older** than the already-published stable `"1.15.6"` — confirmed by directly running that exact
function in a real QGIS 4.2.2 session: `compareVersions('1.5.7-rc5', '1.15.6')` returns `2`
(second argument is newer). This traces back to a 2026-09-19 decision (predating this RC's own
work) to renumber an in-progress `1.16.0` down to `1.5.7-rc1`, inherited unquestioned through
every RC since, including `rc5`. `1.16.0` was the version actually intended at that point and was
never released under any tag, so it's reused here rather than skipping further ahead.
`compareVersions('1.16.0-rc1', '1.15.6')` was independently re-verified to return `1` (correctly
newer) before this bump. The already-tagged `v1.5.7-rc1` through `v1.5.7-rc5` releases are left as
published — per this project's own convention, tags are never rewritten after the fact — and are
superseded by this line going forward; see the `[1.5.7-rc5]` entry directly below for what that
line's own content was.

All functional content carries forward unchanged from `v1.5.7-rc5` (the real Phase 11
architecture restructuring, the AST-sandbox bypass fix, and the 2 keyboard-navigation fixes — full
detail in that entry below), plus 2 more real, independently-confirmed defects the same review
found in the rc5 release itself:

- **CI packaging assertion was stale.** `.github/workflows/tests.yml`'s "Verify release zip
  packaging" step still asserted the packaged zip contains `core/agent/agent.py` — renamed to
  `agent_orchestrator.py` during the Phase 11 work earlier the same day. The next CI run would
  have failed this assertion even though the package itself was correct (the rename sweep that
  found and fixed every other reference to the old path had only searched `src/` and `tests/`,
  missing this workflow file and, separately, `docs/generate_tools_reference.py`). Fixed and
  verified locally against the real built zip before committing.
- **Stale test counts in released docs.** `README.md` carried two leftover figures (`1,947`
  passed/`38` skipped, and `1,904` tests) from before this cycle's work ever started; the
  `v1.5.7-rc5` changelog entry's own "38-test live suite" claim undercounted itself by 1 (it named
  both `test_agent_live.py` and `test_chat_widget_live.py` but only counted the latter's tests).
  Corrected everywhere to the real, independently re-run current numbers.

**Verification & Testing**: 1,962 automated tests passing (0 failures, 40 skipped) — unchanged
from rc5, re-run again after these fixes. The full 39-test live headless-QGIS Qt suite
(`tests/test_agent_live.py` + `tests/test_chat_widget_live.py`) re-confirmed passing against a
real QGIS 4.2.2 session before this release was cut.

<a id="v1-5-7-rc5"></a>
## [1.5.7-rc5] — 2026-09-20 — Release candidate 5: real Phase 11 restructuring, an AST-sandbox bypass fix, and keyboard-navigation fixes

- **Phase 11 architecture restructuring, finished for real.** `docs/IMPLEMENTATION_TRACKER.md`'s
  own resync at the start of this pass caught the prior "Phase 11 complete" claim as false: only
  thin re-export facades and empty scaffolding existed, with all the actual code still sitting in
  `core/agent/`. This RC does the real move:
  - `infrastructure/` now really holds `auth.py`, `deps.py`, and `providers/` (physically moved,
    not re-exported). `core/models/` holds `transactions.py`, `dataset_status.py`,
    `sensitivity.py`, `confidence.py`. `core/validators/` holds `schema_contracts.py` +
    `pcode_validation.py` (plus their `contracts/*.json` data files). `core/services/` holds
    `prompt_refiner.py`, `tool_router.py`, `task_runner.py`, `learning.py`.
  - `agent.py`'s god-class decomposition: extracted `tool_dispatcher.py`, `usage_tracker.py`, and
    `history_manager.py` from `CartogenAi` (via delegation, so every method/attribute external
    code and tests already depended on by name kept working unchanged), then renamed `agent.py`
    itself to `agent_orchestrator.py` to match the plan's own naming. 1,346 → 1,170 lines.
  - `chat_tab_widget.py` split into `chat_view_presenter.py` (tool-step/plan-progress rendering)
    and `chat_input_controller.py` (file-attachment reading/analysis) — the two subsystems that
    were genuinely self-contained; the rest of that file stays composed as one unit, since tracing
    every method found input-handling and view-rendering woven together too tightly elsewhere in
    it to split further without much larger risk for questionable benefit. 1,839 → 1,522 lines.
  - Verified after every single step (never batched): the full test suite, and the live
    36→38-test headless-QGIS Qt suite (`tests/test_chat_widget_live.py`, real `QTest` widget
    clicks against a real QGIS session) run both before touching UI code (clean baseline) and
    after (confirm no regression).
- **Security fix: a novel `execute_pyqgis_script` AST-sandbox bypass, found and closed.**
  `type.__dict__['__subclasses__']` retrieves the exact same dangerous method the already-blocked
  classic `().__class__.__bases__[0].__subclasses__()` escape chain uses, but via a dict subscript
  on `.__dict__` (never in the blocklist) instead of a literal `.__subclasses__` attribute access
  — invisible to the AST walk's attribute-name check, since the dangerous name only ever appears
  as a string constant inside an `ast.Subscript`. Live-verified before the fix: the exact PoC
  script passed `_validate_script_safety` and, run through the real restricted-`__builtins__` exec
  environment, successfully enumerated all 178 currently-loaded subclasses of `object`. Closed by
  adding `__dict__` to `_BLOCKED_DUNDER_ATTRS` in `system_tools.py`; re-verified the PoC is now
  rejected. 2 new regression tests.
- **2 real keyboard-navigation gaps found via live `QTest` verification, both fixed.** Tab pressed
  inside the chat input box only inserted a literal tab character (`QTextEdit`'s own default) —
  live-confirmed a genuine dead end: nothing after the input box (Send, Stop, everything else in
  the dock) was reachable by keyboard at all. Fixed with `ChatInputEdit.setTabChangesFocus(True)`.
  Escape did nothing — live-confirmed typed text survived an Escape press unchanged. Fixed to
  clear the input box (deliberately narrow: doesn't cancel an in-flight request or touch any
  pending requirement/preview-reply state). 2 new permanent regression tests.
- **Verification & Testing**: 1,962 automated tests passing (0 failures, 40 skipped), up from
  RC4's 1,958. The full 39-test live headless-QGIS Qt suite (`tests/test_agent_live.py`'s 1 test +
  `tests/test_chat_widget_live.py`'s 38) re-run against a real QGIS 4.2.2 session and confirmed
  passing before this release was cut.

<a id="v1-5-7-rc4"></a>
## [1.5.7-rc4] — 2026-09-20 — Release candidate 4: OSM feature ingestion, AST sandbox guardrails, and a 7-bug code-review remediation pass

**Correction to RC3's own changelog entry, found while preparing this release**: a later commit
(`9f8e146`) directly edited RC3's already-tagged, already-pushed changelog text to retroactively
claim `ingest_osm_features` and the AST sandbox guardrails shipped in RC3 -- confirmed via `git
show` against the actual `commercial-plugin-v1.5.7-rc3` tag that neither was present in that
release. The already-public RC3 tag/entry is left as-is (tags are never rewritten once pushed,
per this project's own convention), but both features are accurately new here, in RC4, where they
actually first ship. `CHANGELOG.md`'s own missing `[1.5.7-rc3]` section (this file, unlike
`metadata.txt`, never got one written at all) is backfilled below this entry.

- **`ingest_osm_features` two-phase vector ingestion tool** (`humanitarian_tools.py`): fetches OSM
  nodes and polygon ways via the Overpass API into a temporary GeoJSON on the background thread,
  then safely instantiates the `QgsVectorLayer` on the main Qt thread -- lets the agent
  autonomously populate an empty project with real facilities/infrastructure data for a given area
  instead of stalling for lack of a starting layer.
- **AST sandbox prompt guardrails** (`prompts.py` Rule 6): hardened against the model attempting to
  bypass `execute_pyqgis_script`'s security sandbox to fetch external data itself, steering it to
  `ingest_osm_features` instead when a needed layer is simply missing.
- **Code-review remediation, 7 confirmed correctness/security bugs** (a full multi-angle
  `/code-review` pass over every commit since the last verified checkpoint, each finding verified
  against the real current code -- not just the paraphrase -- before being fixed):
  - `auth.py`: `save_credential()` now reuses the existing `QgsAuthMethodConfig` id on re-save
    instead of leaking a new orphaned auth-database entry on every API key rotation.
  - `auth.py`: `get_credential("ollama")` now falls back to the pre-rename
    `cartogen_ai/ollama_url` setting, so an endpoint configured before the settings-centralization
    pass isn't silently invisible after upgrading.
  - `export_tools.py`: `only_selected=True` with nothing actually selected now errors instead of
    silently exporting the entire layer.
  - `export_tools.py`: `export_layer`/`_derive_csv_path`/`print_map` no longer pop a blocking modal
    dialog when `output_path` is omitted -- reverts a regression that reintroduced exactly the
    agent-turn-stall risk a prior fix (RC-era) had removed.
  - `humanitarian_tools.py`: `ingest_osm_features_network_phase` no longer drops OSM features
    sitting exactly on the equator or prime meridian (a falsy-zero `or` bug on `lat`/`lon` `0.0`).
  - `styling_tools.py`: `change_layer_color()` no longer resets opacity to a geometry-type default
    when the `opacity` argument is omitted, matching its own documented contract.
  - `representation/profiler.py`: fixed a vacuous-truth bug that misclassified all-negative
    numeric fields as `positive_quantity`.
- **One additional latent bug found while testing the above**: a real circular import between
  `core.agent.auth` and `infrastructure/__init__.py` (only reproducible when `auth.py` is imported
  in isolation, which is why the full test suite never caught it) -- fixed by making the
  `CredentialManager` re-export lazy via `PEP 562` module `__getattr__`.
- **Verification & Testing**: 1,958 automated tests passing (0 failures, 0 errors, 38 skipped), up
  from RC3's 1,947 -- 11 new regression tests, one per fix, each reproducing the real bug against
  the real code before confirming the fix.

<a id="v1-5-7-rc3"></a>
## [1.5.7-rc3] — 2026-09-19 — Release candidate 3: Pre-release audit remediation and PyQGIS API modernization

Backfilled into this file 2026-09-20 while preparing RC4 -- this section describes what commit
`9845cb2` (the commit the `commercial-plugin-v1.5.7-rc3` tag actually points to) shipped, matching
`metadata.txt`'s changelog text for RC3 as it read at that commit, before a later commit edited it
in place (see the RC4 entry above).

- Reconciled minimum supported QGIS version to 3.28 (Firenze LTR), matching the `Python >=3.9`
  requirement.
- Replaced deprecated `QgsVectorFileWriter.writeAsVectorFormatV2` with `writeAsVectorFormatV3` in
  `export_tools.py`.
- Replaced deprecated `QgsGraduatedSymbolRenderer.createRenderer` with
  `QgsClassificationMethodRegistry` in `styling_tools.py`.
- Packaged and synchronized release archives (`cartogen_ai.zip` and
  `dist/cartogen_ai_v1.5.7-rc3.zip`) with all 176 tools, the Map Intelligence Engine, and the
  Intelligent Representation Planner (both introduced earlier in the RC3 development range, on top
  of RC2).
- Validated 1,937 automated unit/integration tests passing (38 skipped) and 5/5 live headless QGIS
  pipeline tests with zero deprecation warnings.

<a id="v1-5-7-rc2"></a>
## [1.5.7-rc2] — 2026-09-19 — Release candidate 2: Settings centralization, provider decoupling, shapefile DBF laundering, and release stabilization

Release candidate 2 addresses all feedback and remediation items following RC1:

- **100% Settings Centralization (`src/cartogen_ai/infrastructure/settings_keys.py`)**:
  - Unified all persistent configuration strings, layer custom property keys, and QgsSettings lookup paths into `settings_keys.py`.
  - Replaced literal key definitions across `plugin_main.py`, `system_tools.py`, dataset sensitivity/status/lineage, layer metadata snapshots, and test suites.
- **Provider Import Decoupling**:
  - Made external network library dependencies (`requests`) lazy inside `CartogenProviderBase` and specific provider classes.
  - Allowed `cartogen_ai.infrastructure` and `settings_keys` to be imported and tested cleanly in minimal Python test environments.
- **Robust Shapefile Preflight DBF Laundering (`export_tools.py`)**:
  - Upgraded field name laundering to compute encoded byte length (UTF-8) rather than naive character slices.
  - Implemented iterative while-loop disambiguation (`_{i}`) to guarantee zero field collisions against pre-existing identically-truncated field names.
- **Enhanced Shaded Relief Pipeline (`raster_tools.py`)**:
  - Combined hypsometric tinting with hillshade using QGIS `Multiply` blend mode (`QPainter.CompositionMode_Multiply`).
  - Added strict opacity validation (0.0–1.0) with explicit exception handling if layer composition fails.
- **Verification & Testing**:
  - 100% test pass rate across 1,916 tests (0 failures, 0 errors, 38 skipped).
  - Packaged and verified release archives (`dist/cartogen_ai_v1.5.7-rc2.zip` and `cartogen_ai.zip`).

<a id="v1-5-7-rc1"></a>
## [1.5.7-rc1] — 2026-09-19 — Release candidate 1: QGIS Processing Provider, OGC renderers, geodetics, and architecture remediation

Major release executing the full Part A remediation plan, closing all confirmed architecture, cartography, OGC, and performance gaps:

- **Native QGIS Processing Provider (`cartogen_ai.processing`)**:
  - Implemented `CartogenProcessingProvider` registered with `QgsApplication.processingRegistry()`.
  - Added native `OptimalHubSitingAlgorithm` and `CalculateServiceAreaAlgorithm` callable from the Processing Toolbox, Graphical Model Designer, batch processor, and headless `qgis_process` CLI.
  - Manifest updated: `hasProcessingProvider=yes`.
  - Lifecycle cleaned up in `plugin_main.py` (proper registration in `initProcessing()`, removal in `unload()`, and `QTimer.singleShot` tracking/cancellation).

- **OGC SLD 1.1.0 Export & Cluster Renderers (`styling_tools.py`)**:
  - Added `export_layer_sld(layer_name, output_path)` exporting OGC SLD 1.1.0/1.0.0 via `layer.saveSldStyle()`, with desktop fallback for memory layers. Classified as `PUBLISH` in `tool_operations.py`.
  - Added `apply_point_cluster_style(layer_name, mode, tolerance)` supporting native `QgsPointClusterRenderer` and `QgsPointDisplacementRenderer` via `setEmbeddedRenderer()`. Classified as `MODIFY` in `tool_operations.py`.

- **Architectural Boundary Subdivisions**:
  - `src/cartogen_ai/infrastructure/`: Dedicated boundary exporting `CredentialManager` and `get_qgis_proxy_dict`.
  - `src/cartogen_ai/core/models/`: Domain models (`TurnTransactionLog`, `STATUS_ORDER`, sensitivity/confidence models).
  - `src/cartogen_ai/core/validators/`: Schema contracts and P-code depth validation (`list_contracts`, `validate_layer_schema`, P-code uniqueness/hierarchy).
  - `src/cartogen_ai/core/services/`: Core orchestration (`refine`, `ToolRouter`, `AgentQgsTask`, `maybe_infer_preferences`).
  - Updated `pyproject.toml` setuptools package discovery list.

- **OCHA Print Layout Elements (`layout_tools.py`)**:
  - Added coordinate graticule/grid with auto-interval rounding (`_nice_interval()`).
  - Added MAP_INFO metadata label displaying CRS authid/description and representative-fraction scale (`1:50,000`).
  - Added 32x32mm inset overview locator map with linked `QgsLayoutItemMapOverview` rectangle.

- **Geodetics & Concurrency**:
  - Added ellipsoidal distance calculations via `QgsDistanceArea` for geographic-CRS layers in `optimal_hub_siting`, `location_allocation`, and routing. Fixed `'NONE'` ellipsoid string fallback.
  - Added thread-safe synchronization across background tasks and GUI thread via `RLock` in `agent.py` and `Lock` in `transactions.TurnTransactionLog`.

- **API Token Economy & Performance**:
  - Stabilized serialized request bodies with deterministic alphabetical tie-breaking in `tool_router.py`, enabling Gemini 2.5+ implicit prefix caching (up to 90% prompt discount).
  - Narrowed Prompt Rule 5 to avoid redundant `get_attributes()` round-trips when fields are pre-injected in map context.
  - Scaled token budgets dynamically per agent iteration.
  - Added tail-message prompt caching for Claude and OpenRouter providers.

- **Observability & Networking**:
  - Created custom exception hierarchy (`cartogen_ai.core.exceptions`).
  - Integrated structured logging with QGIS Message Log (`QgsMessageLog.logMessage`) under "Cartogen AI".
  - Added QGIS Network Access Manager proxy detection (`get_qgis_proxy_dict`) across provider HTTP sessions.

- **Cartography & Layer Format Defaults**:
  - ColorBrewer CVD-safe `BrBG` ramps for NDVI/NDRE.
  - Added `create_shaded_relief(dem_layer, color_ramp, azimuth, altitude, opacity)` combining hypsometric pseudocolor elevation tinting with hillshade using Multiply blending (`QPainter.CompositionMode_Multiply`).
  - Added preflight checks in `export_layer` for ESRI Shapefile exports detecting field names > 10 characters and post-truncation name collisions, warning users and suggesting GeoPackage.
  - Centralized all `cartogen_ai/*` QgsSettings and QgsProject properties into `infrastructure.settings_keys`.
  - Replaced silent `except Exception: pass` sites with structured logging in `memory.py`, `auth.py`, and `chat_tab_widget.py`.

  - Text buffer halos (0.8mm round-join), priority configuration, and obstacle avoidance in `apply_labels`.
  - StdDev, Pretty Breaks, and Logarithmic classification modes in `apply_graduated_style`.
  - Dynamic `_geographic_z_factor()` for DEM hillshade and slope on geographic CRS.
  - GeoPackage database style persistence (`saveStyleToDatabase`), UTF-8 shapefile encoding fallback, and SpatiaLite spatial index creation.

- **Code Quality, CI & Verification**:
  - Configured `[tool.ruff]` and `[tool.mypy]` in `pyproject.toml`.
  - Enhanced `.github/workflows/tests.yml` with ruff linting and release zip integrity verification.
  - Total tests passing: **1,916 tests, 0 failures, 0 errors, 38 skipped** (+145 tests added).
  - Package size verified: `cartogen_ai.zip` at **1.41 MB**.

<a id="v1-15-6"></a>
## [1.15.6] — 2026-09-18 — Stable, promoted from rc6

**No code changes from `v1.15.6-rc6`** — this release exists to mark that candidate as the
version actually shipped as "Latest," not to introduce anything new. Six release candidates ran
against this version line over 5 days, each checksum-verified against a real QGIS session before
the next one started:

- **rc1** (2026-09-14): remediated 27 of 32 findings from a full security/QGIS/API/performance/
  code-quality audit.
- **rc2** (2026-09-15): 4 fixes — a missing `requests` dependency declaration, a GDACS country
  filter, dock screen-clamp timing, and the prompt-preview panel's first conversion to in-chat.
- **rc3** (2026-09-15): a missing first-message echo fixed, and tool-call argument shape
  validation added (guards against a double-JSON-encoded arguments string).
- **rc4** (2026-09-16): the recurring `'str' object has no attribute 'get'` crash — reported
  identically at wildly different tool-call counts across 5+ separate incidents — finally
  root-caused for real (`_execute_tool`'s snapshot step was receiving raw, unparsed JSON tool-call
  arguments) after two earlier defensive-guard fixes landed without being the actual cause; a
  custom Qt layout that froze the whole application on first real interactive use, reverted
  outright rather than debugged blind; and a Settings/chat/Activity visual pass.
- **rc5** (2026-09-17): three real orchestrator bugs found from close reading of an actual live
  session transcript — a task-router confidence floor that was computed but never checked
  (routing low-confidence requests to a completely unrelated deliverable, the dominant cause of
  reports that answers weren't "relative to the request"); external API values silently dropped
  by a memory layer's shapefile-era field width; and a destructive-action confirmation gate that
  could be silently bypassed by a plain "Confirm" reply in chat, fixed at 3 compounding layers.
  Plus the full 4-phase Broadsheet UI redesign: a single continuous scroll replacing the Chat/
  Activity tab split, an inline destructive-action confirmation card with clickable Apply-edit/
  Cancel links, the Task Inspector and Project Notes/Memory moved into on-demand dialogs, and a
  new layer-context picker for explicit, opt-out control over what schema reaches the model.
- **rc6** (2026-09-18): `search_web`'s `duckduckgo-search` dependency confirmed genuinely broken
  (silently returns zero results for a real query) and migrated to `ddgs` — found by
  independently verifying every item left open by two rounds of external audit of rc5, rather
  than accepting "reported PASS, not independently rerun" as a final answer. Both audit rounds'
  own headline findings (a release-checksum non-issue caused by this build script's zip entries
  embedding real file mtimes; a licensing-contradiction claim traced to a never-merged draft
  proposal misread as current policy) were resolved without any code change.

**Known, honestly-tracked open items at this promotion, not resolved by it** — see
`docs/IMPLEMENTATION_TRACKER.md` for the current, living list: PostGIS live read-only-SQL
enforcement has never been verified against a real database in this development environment
(Docker's backend won't start there without a one-time interactive first run); a live Gemini
network observation from that same environment is blocked on an interactive credential-store
unlock a headless process never triggers; imagery feature extraction (`ultralytics`/`torch`) is
confirmed installable and importable but not end-to-end tested against a real QGIS raster layer;
and the Community/Professional/Enterprise licensing path (`docs/PRODUCT_TIERS.md`) remains an
open business/legal decision that does not affect this edition's shipped functionality — the
Community edition has never been provider-restricted and ships all 6 provider integrations today.

Full suite: 1754 tests, 0 failures.

<a id="v1-15-6-rc6"></a>
## [1.15.6-rc6] — 2026-09-18 — Release candidate: search_web's dead dependency migrated to ddgs

A real fix found by closing out RC5's remaining open items for real rather than leaving them as
"reported PASS, not independently rerun" — two rounds of external audit on RC5 (see below) had
already confirmed the mechanical release state, but 4 items were still genuinely unverified:
PostGIS live enforcement, a real Gemini network observation, QGIS-version-range coverage beyond
4.2.2, and optional-dependency positive-path coverage. Attempted every one for real.

**`search_web`'s dependency was genuinely broken, and is now fixed.** `duckduckgo_search`, even
at 8.1.1 (the version `requirements.txt` pinned as its documented "thin compat shim" floor),
silently returns zero results for a real live query — no exception raised, nothing for
`search_web`'s own `except ImportError` to catch, so the tool just reported "no results found"
for a completely valid query as though that were a normal, unremarkable answer. The identical
query against `ddgs` (the actual current package this dependency was renamed to upstream)
returned real results immediately, confirmed live, not from reading the deprecation notice alone.
`search_web` now imports `ddgs` first, falling back to `duckduckgo_search` only if `ddgs`
genuinely isn't installed — both expose the same `DDGS` class/`.text()` call shape, so nothing
below the import needed to change. `requirements.txt` and the startup dependency-check banner
(`agent/deps.py`) now track `ddgs` (floored at 9.16.0, the version this fix was tested against)
instead of the dead pin. 3 new tests confirm the preference order and the fallback path.

**The other 3 items got honest, closing answers — not silently declared done:**
- **QGIS version-range coverage**: this machine has exactly ONE real, complete QGIS install
  (4.2.2). The other 3 version directories present (`3.44.12`, `3.44.13`, `4.2.0`) are all bare
  OSGeo4W installer shells with no usable Python environment at all — resolved as "not further
  testable in this environment," a real finding, not a gap left open indefinitely.
- **Optional-dependency positive paths**: `python-docx` and `pdfplumber` both confirmed working
  against real generated test files (a real `.docx` with a table, a real PDF with a table)
  through the plugin's own `read_attached_file`/`extract_pdf_tables` code, in an isolated
  throwaway environment. `ultralytics`/`torch` installed and imported successfully the same way,
  confirming the packages work on this machine — completing that specific tool's own end-to-end
  test needs `qgis.core` plus a real raster layer, meaning installing a real ML runtime into the
  live QGIS Python environment rather than a disposable one; deliberately not done without
  explicit sign-off, given that weight and persistence.
- **PostGIS live verification and a live Gemini network observation remain genuinely blocked** —
  Docker Desktop's backend won't start without a one-time interactive first run only a human can
  complete; the real QGIS profile has a Gemini provider configured, but its encrypted credential
  needs the interactive GUI's master-password unlock, which a headless boot never triggers.

**Two rounds of external audit on RC5**, both instructive: the first flagged the release checksum
as unreconciled, which traced to `plugin_upload.py`'s zip embedding real on-disk file mtimes
(never normalized) — a checksum mismatch across independent rebuilds is not, by itself, evidence
of a content problem with this build script, documented plainly so it stops causing false alarms.
The actual published GitHub asset was re-downloaded and re-hashed fresh, twice, confirming the
real release was never in question. The second flagged a "product identity/licensing
contradiction" between the shipped 5/6-provider Community edition and a supposed "Community
contract" limiting it to 3 — traced to `docs/archive/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`, an
explicitly-marked, never-merged DRAFT being misread as current policy; `README.md`, `CLAUDE.md`,
and `docs/PRODUCT_TIERS.md` are actually mutually consistent, and the audit withdrew the finding
once shown the exact quotes. Two small real documentation fixes came out of that exchange anyway:
a stale "165-tool" count in `docs/PRODUCT_TIERS.md` (live count is 169), and a leftover "Internal/
commercial use" phrase in `README.md`'s Support section, inconsistent with the rest of the page's
Community/GPL framing.

Full suite: 1754 tests, 0 failures (up from rc5's 1751).

Still a release candidate, not final.

<a id="v1-15-6-rc5"></a>
## [1.15.6-rc5] — 2026-09-17 — Release candidate: router/field-width/confirmation-gate fixes, and the Broadsheet redesign

An extended live-testing session on top of `v1.15.6-rc4` surfaced 3 more real, code-grounded bugs
in the orchestrator pipeline, all reproduced and fixed against the real agent — not from a chat
transcript's own summary text, but from the raw QGIS Python Console's `[Agent] Tool call:`/
`succeeded`/`FAILED` lines, since two of the three bugs were exactly the case where the model's
own prose confidently described something that never actually happened. Source commits `ce91b6a`,
`96fd84b`, `ed6c42b`.

**1. The task router's own confidence floor was computed but never checked.**
`task_matcher.classify()` already flags a match `ambiguous` when it scores below
`CONFIDENT_SCORE=0.34`, but `prompt_refiner.analyze_request()` built a full "Recognised task X,
deliver Y, prefer tools Z" system-prompt directive from the low-confidence match anyway. Live
evidence: "apply a color ramp to the raster layer" (score 0.33) got routed to an unrelated HDX/3W
CSV-export task; the model then reported a fabricated GPKG/CSV export instead of touching the
raster at all. Fixed by falling through to the same "nothing matched" path a genuinely unmatched
query already gets, but ONLY for the "below confidence floor" reason — a *tied*-but-above-floor
match (e.g. a 0.38-scoring "dashboard" query merely tied against a much weaker cross-section
match) is left alone, since nulling that out would throw away good matches too, not just bad
ones. This was the dominant root cause behind reports of answers "not relative to the request."

**2. External API values wider than a memory layer's field width were silently dropped.**
GDACS's own `country` property is a comma-joined list for multi-country events (observed at 261
chars); the memory layer's shapefile-era `field=country:string(255)` silently rejects anything
over 255 chars via QGIS's own memory-provider width enforcement — no exception, just a missing
attribute and a Qt log line the tool's own return value never reflected. Fixed with a small
`_clip_to_field_width` helper (one copy per file, matching this codebase's existing per-file-
helper convention) applied at all 3 affected write sites (GDACS/EONET/fires, and the two
humanitarian incident-point writers).

**3. A destructive-action confirmation gate could be bypassed by normal chat use, not misuse —
the most serious finding.** Traced a specific live sequence: a `field_calculator` `PREVIEW_
REQUIRED` gate fired mid-plan, the user replied "Confirm" in the chat box rather than the
Activity tab's own "Confirm and Apply Edit" button, and the actual tool log for that turn showed
`field_calculator` was never called — the model fabricated a full "Confirmation Acknowledged...
Evaluated Numeric Severity: 2" narrative while the field was never written. Three compounding
structural gaps, fixed together: `_real_execute_tool` used to only start a fresh safety-gate plan
when the task list was completely empty, otherwise gluing the pending confirmation onto
`tasks[0]` of whatever plan happened to already be active — silently overwriting an unrelated,
possibly already-`DONE` task; a new `add_task()` on the task manager always appends a dedicated
task instead. The chat send path gained the same deterministic resolution the Activity tab's
button already used (`agent._real_execute_tool(pending_tool, pending_args, user_confirmed=True)`
directly, no LLM turn) for a plain-text confirm/cancel reply — narrow enough that only an exact
yes/no-shaped reply is intercepted, so an unrelated new message can never hijack a stale gate.
`get_formatted_task_context()` now also surfaces the pending tool/arguments as defense-in-depth.

**Broadsheet redesign** — a full visual and structural redesign of the dock, from a user-supplied
15-state mockup board reviewed live and confirmed direction-by-direction:
- **Single continuous scroll, no more Chat/Activity tabs.** A sticky plan strip (progress bar,
  now stating e.g. *"3/4 steps complete — 1 needs you"* directly instead of a bare fraction, plus
  the task list) sits above the chat thread in one view — directly fixes a live audit finding
  that the one task genuinely needing a decision could scroll out of view inside the old tab's
  capped list. The Task Inspector moved to a per-task dialog opened by clicking a plan-strip row;
  Project Notes/Memory and Learned Preferences moved to a new dialog opened from a header button.
- **Inline destructive-action confirmation card.** Replaces the plain-text gate message with a
  real card (layer/field summary, rationale, code snippet, clickable Apply-edit/Cancel links) —
  wired to the exact same safe confirmation path fix 3 above built, not new logic.
- **Layer context picker.** A new composer control gives explicit, per-question, opt-out control
  over which loaded layers' schema reaches the model — a layer already tagged via the existing
  `set_layer_sensitivity` tool defaults unchecked; a user who never opens it sees unchanged
  behavior.
- Theme-aware magenta/"danger" color tokens (nudging the live QGIS palette, never a flat
  hardcoded color, so it still adapts across light/dark themes) reserved specifically for the one
  thing that mutates data — found and fixed a real bug along the way: the Confirm button had no
  `:disabled` QSS rule at all, so it looked identically clickable whether it actually was or not.

New `docs/LIVE_TEST_SCENARIOS.md` adds 5 multi-turn workflow scenarios (not single-prompt checks
like `docs/RELEASE_SMOKE_TEST.md`) — 3 reproduce this cycle's own fixed bugs, 2 are grounded
directly in the plugin's stated core purpose (map-visualization accuracy and technical-analysis
accuracy), every one verified against actual canvas/attribute-table state, never chat prose.
`docs/USER_GUIDE.md` and the in-app Help window updated to match the redesign throughout.

Full suite: 1751 tests, 0 failures (up from rc4's 1695 — new coverage for every fix and every
redesign phase, live-verified with real headless screenshots and real `QTest` clicks/keystrokes
against the actual Qt widgets, not just unit-level assertions). 34/34 live-QGIS tests passing.

Still a release candidate, not final.

<a id="v1-15-6-rc4"></a>
## [1.15.6-rc4] — 2026-09-16 — Release candidate: confirmed crash root-causes, a router gap, a UI freeze reverted, and a visual redesign

A large batch of live-reported fixes on top of `v1.15.6-rc3`, every one reproduced and verified
against the packaged plugin across an extended live-testing session, not just the dev tree.

**Crashes, root-caused with real tracebacks:**

1. **`'str' object has no attribute 'get'` — the actual root cause, finally confirmed.** This
   exact error text was reported repeatedly across the cycle, at wildly different tool-call
   counts (18, then 3, then 1, then 15) with no traceback to pin it down — two earlier defensive
   guards landed without full confirmation (see below). A live report finally came with a real
   traceback: `_execute_tool`'s pre-dispatch "snapshot" step (`_snapshot_registry.py`, used by
   MODIFY/DELETE tools like `apply_categorized_style` to capture undo state) received the
   model's tool-call arguments as the raw, still-JSON-encoded string straight off the tool call —
   never parsed into a dict, unlike the two real dispatch paths a few lines later, which each
   parse it internally. Any tool registered with a snapshot function crashed this way every time
   it was actually called, independent of anything else that ran first — exactly why the
   tool-call count varied while the crash didn't. Fixed by parsing once, before the snapshot
   call; covered by a new test that reproduces the real traceback shape (a raw JSON string in,
   not an already-parsed dict).
2. **`_compact_old_tool_results` guarded against a non-dict message entry.** A separate,
   legitimate defensive fix found while investigating (1) above, before the real root cause was
   confirmed — `m.get("role")` assumed every entry in the turn's message list was a dict;
   reproduced in isolation (`['x'][0].get('role')` raises the identical text) and guarded either
   way, though the exact mechanism that could produce a non-dict entry was never conclusively
   identified.
3. **Oversized tool results are now compacted immediately, not after 8 more tool calls.** A
   Gemini 400 "input token count exceeds the maximum" error after only 5 tool calls —
   `inspect_canvas_visually` embeds a full base64 canvas screenshot in its tool result, easily
   hundreds of thousands of tokens on its own, but the existing mid-turn compaction only trimmed
   a result once 8 *other* tool calls had also happened, a rule that assumes no single result is
   enormous enough to blow the budget alone. A single oversized result now gets trimmed as soon
   as it's no longer the latest one, immediately after the model has seen it once.

**Tool discovery:** `geocode_and_enrich`/`geocode_batch` share no vocabulary with
"health facilities beyond one hour's travel"-style requests, so they lost the competition for a
slot in the ~40 tools shown to the model out of ~170 registered — the model, unable to see they
existed, spent an entire turn's tool budget hunting the filesystem via `execute_pyqgis_script`
for a local data file instead. Fixed with curated router aliases (the same mechanism already
tuned for 8 other tools with this exact gap); confirmed end-to-end against the real `agent.run()`
loop, not just the router in isolation, and covered by a new live regression suite
(`tests/test_agent_live.py`) that scripts a full realistic turn — geocode, create a plan, add a
real QGIS layer, style it, mark every task `DONE` — and confirms a real layer lands on the canvas
and the Activity tab's actual data source gets populated, closing the loop on a live report that
a "successful" turn produced neither.

**A real UI freeze, reverted rather than chased.** A custom Qt `FlowLayout`, added this cycle for
the Settings dialog's provider pills (then reused in the Activity tab), triggered a live-reported
total application freeze on its first real interactive use — a known Qt failure mode (a resize
feedback loop inside a `QScrollArea`) that headless/offscreen screenshot verification cannot
catch, since it never drives real interactive resize/paint behavior. Reverted outright to plain,
long-established Qt layouts (a vertical stack for the pills, a fixed grid for the Activity tab's
buttons) rather than risk the same failure mode chasing a fix blind.

**Visual redesign**, following a design proposal drawn up this cycle and iterated against real
screenshots and real live feedback: numbered sections and a masthead status line in Settings; a
"Keys" summary showing a masked value and Set/Verified state per credential, directly targeting
an earlier live report where a saved key gave no confirmation it had actually taken; a redesigned
welcome message (a real capability index and clickable starter prompts, not plain markdown) and a
matching restyle of the prompt-preview card; the "Suggested rewordings" boxed panel converted to
in-chat cards, the same conversion the requirement gate and prompt preview already went through
earlier; an Activity-tab fix for buttons overflowing off the dock's edge; and a real correctness
fix for the Activity tab's memory panel, which was showing raw, unrendered `##`/`**` markdown
instead of formatted text.

Full suite: 1695 tests, 0 failures, including a new live-QGIS regression module
(`tests/test_agent_live.py`) that exercises real tool execution against a real QGIS project and
a real task-tracking pipeline, not mocks — closing a real gap every other agent test left open
(mocking tool dispatch directly proves the tool-calling loop is correct, but never proves a tool
call actually creates a real layer or populates the Activity tab's data).

Still a release candidate, not final.

<a id="v1-15-6-rc3"></a>
## [1.15.6-rc3] — 2026-09-15 — Release candidate: 2 more fixes on rc2

Two more real, live-reported fixes on top of `v1.15.6-rc2`, both verified against the packaged
plugin. Source commit `156fea4`.

1. **The triggering message for an in-chat gate is now echoed as its own bubble.** Real live
   report: "the first message i sent on the chat was not showing in the chat box." When a
   fresh message triggered either in-chat gate (`_ask_requirement_in_chat` or
   `_ask_preview_in_chat`), the user's own typed text was never shown as its own "You" bubble
   -- it only appeared secondhand, quoted inside the AI's own message. Both gates now echo the
   triggering message immediately, before the AI's question; the preview-confirm path gained an
   `already_echoed` flag so the same text isn't shown a second time once dispatch happens.
2. **Tool-call arguments are now validated to actually be an object.** `json.loads` succeeds on
   any well-formed JSON document, not just objects -- a double-JSON-encoded arguments string (a
   known real-world LLM tool-calling quirk: the model's own arguments field is itself a
   JSON-encoded string) decodes to a plain string, not the intended dict, and previously crashed
   uncaught on the next line. Investigated as a candidate cause for a live-reported
   `'str' object has no attribute 'get'` crash immediately after a real 18-tool-call Gemini turn
   where every individual tool call succeeded -- not confirmed as the exact site (no traceback
   was available to pin it down precisely), but a real, demonstrable gap in the same bug class
   as two earlier-fixed usage-parsing crashes (`extract_openai_style_usage`).

Full suite: 1689 tests, 0 failures. Live-verified against the rebuilt package (`dist/`
`cartogen_ai_v1.15.6.zip`, 173 entries, sha256 `1d1cd5b5...6530f810`): the full 16-category
interactive checklist (15/15 runnable categories, PostGIS skipped -- no test DB; one transient
network timeout on the OSM category, clean on retry) plus 2 targeted checks proving both fixes
work against the packaged code, not just the dev tree -- see `docs/RELEASE_SMOKE_TEST.md`'s
2026-09-15 RC3 run log entry for the full detail.

Still a release candidate, not final: licensing/publication decision, package provenance
confirmation, and stable-promotion gates remain open — see
`docs/audits/QGIS_PLUGIN_AUDIT_FINAL_REPORT.md` §16 for the full gate table.

<a id="v1-15-6-rc2"></a>
## [1.15.6-rc2] — 2026-09-15 — Release candidate: 4 fixes on rc1

Four real, live-reported fixes on top of `v1.15.6-rc1`, all verified against the packaged plugin
(not just the dev tree). Source commit `62fcb69`.

1. **`requests` declared as a required dependency.** Every provider client
   (`agent/providers/*.py`) and `account.py` import it directly for all LLM API calls, but it was
   never listed in `requirements.txt` -- worked in practice only because QGIS's own bundled
   Python typically ships it already, an unstated host-environment assumption rather than a real
   dependency declaration.
2. **GDACS `country` filter.** A place-scoped request with no explicit bbox (e.g. "the latest
   GDACS alerts for Yemen") previously fell through to `fetch_gdacs_disaster_alerts`'s
   global-coverage default, returning every disaster alert on Earth. Added a `country` parameter
   that filters against GDACS's own per-alert country field (already extracted, never filtered
   on before). Live-verified: every returned alert's country field genuinely contains "Yemen",
   and the filtered count never exceeds the unfiltered count.
3. **Floating dock proactively re-clamped on panel toggle.** Showing the prompt-preview/
   refinement panels grows the dock's forced minimum size enough to push it past the available
   screen height -- exactly the failure mode `_clamp_to_screen_if_floating` (added in `v1.14.1`)
   exists to catch, but that guard only ran from `resizeEvent`, leaving a timing gap that could
   leave the chat input row under the Windows taskbar. Now called proactively the moment either
   panel's visibility changes.
4. **Prompt-preview panel converted to an in-chat exchange.** The "Prompt that will be sent"
   boxed panel (Send this / Send as typed instead / Cancel) is replaced by `_ask_preview_in_chat`
   -- the reasoning and composed prompt post as a normal chat message, and a typed reply resolves
   the same 3-way choice (confirm / edit / cancel) via free text. Same conversion already applied
   to the requirement-gate panel in `v1.15.2`; this was the last boxed panel in the chat flow.

Also fixed in passing: a stale doc reference in `help_tab_widget.py` (an "Edit request" button
that had already been removed in the `v1.15.2` conversion) and a dangling reference in
`.github/workflows/sync-to-private.yml` found while preparing an unrelated Community-publication
artifact.

Full suite: 1684 tests, 0 failures. Live-verified against the rebuilt package (`dist/`
`cartogen_ai_v1.15.6.zip`, 173 entries, sha256 `5aee5c99...377a950`): the full 16-category
interactive checklist (15/15 runnable categories, PostGIS skipped -- no test DB) plus 4 targeted
checks (plugin load/unload via the real `classFactory()` entry point, the live GDACS network
call described above, the screen-clamp firing on a real panel-visibility change, and the old
boxed preview panel confirmed absent with the new in-chat mechanism confirmed present) -- see
`docs/RELEASE_SMOKE_TEST.md`'s 2026-09-15 run log entry for the full detail.

Still a release candidate, not final: licensing/publication decision, package provenance
confirmation, and stable-promotion gates remain open — see
`docs/audits/QGIS_PLUGIN_AUDIT_FINAL_REPORT.md` §16 for the full gate table.

<a id="v1-15-6-rc1"></a>
## [1.15.6-rc1] — 2026-09-14 — Release candidate: audit remediation (27 of 32 findings)

Full multi-domain audit (Security, QGIS/PyQGIS Integrity, API/Network Client, Performance, Code
Quality) against `cartogen-ai-audit-charter.md`, executed over 2 days against this repo's actual
current state. Complete findings register, remediation log, and a synthesized final report live
in `docs/audits/` (`QGIS_PLUGIN_FINDINGS.md`, `QGIS_PLUGIN_AUDIT_FINAL_REPORT.md`) -- this entry
is a summary; those files are the source of truth for every individual finding's evidence, test
reference, and reasoning.

**32 real findings, 27 fixed/mitigated/partial, 2 accepted risk, 3 deliberately untouched**
(all three explicitly no-action-recommended by the audit itself -- large-scope, low-value
rewrites with no demonstrated bug). Test suite grew 1531 → 1680, 0 failures throughout,
re-verified independently on GitHub Actions CI after every push.

**Security**: SSRF-hardened 4 second-hop URL fetches that bypassed this plugin's own guard
(`humanitarian_tools.py`); sanitized CSV/spreadsheet formula injection in `export_to_csv`;
corrected a license-metadata mismatch and documented an optional dependency's stricter license;
cleaned up cached fetch results' leftover temp files.

**API/network**: redacted provider error bodies that can echo back partial API keys; added
retry/backoff to `list_models()` and the 3 recurring-schedule hazard fetch tools (12 one-shot
fetch tools intentionally left for a follow-up); fixed a real crash on a malformed JSON response
in 2 providers; gave connection/timeout errors an actionable message instead of raw exception
text; added an inline disclosure at the moment of file attachment naming which AI provider the
content is sent to.

**QGIS/PyQGIS**: guarded task-completion callbacks and now cancel in-flight tasks on plugin
unload; the Stop button now takes effect mid-batch, not just between rounds; fixed a latent
export-writer bug and 5 more unresolved-enum gaps of the same class; propagated and extended
CRS-unit-mismatch warnings across 3 logistics tools (numeric correction itself remains an open
design decision -- these tools warn honestly rather than guess a reprojection); extended the
destructive-action confirmation gate to 4 more attribute-mutating tools; a styling failure can
no longer leave a shared layer permanently unstyled.

**Performance**: excluded the 3 network-fetch hazard tools from scheduled/recurring workflows,
closing a real QGIS-GUI-freeze risk (the underlying off-main-thread dispatch rework remains
open); stopped rebuilding a spatial index once per time bucket instead of once; cached
building-footprint tile downloads; moved attachment parsing off the Qt main thread; capped the
candidate×demand pair count in facility-siting tools against unbounded input size.

**Code quality**: pinned an unofficial-API dependency to a known-working range; synced drifted
version metadata across `pyproject.toml`/`README.md`; added real behavioral tests for all 24
previously-untested tools (9 raster/classification, 15 vector/layer-management) -- 0 of 169
tools now have zero test coverage, down from 24.

**CI**: added a `gitleaks` secret-scanning job (GitHub's native secret scanning isn't available
on this private repo without a paid GHAS license -- confirmed directly via the API) and enabled
Dependabot vulnerability alerts and automated security fixes.

Tagged `commercial-plugin-v1.15.6-rc1` rather than promoted straight to a final release: several
release-readiness gates remain open independent of the code itself -- an interactive QGIS smoke
test, a licensing/publication decision, and package identity/provenance confirmation. See
`docs/audits/QGIS_PLUGIN_AUDIT_FINAL_REPORT.md` §16 for the full gate table.

<a id="v1-15-5"></a>
## [1.15.5] — 2026-09-13 — Patch: fixed a second instance of the "'str' object has no attribute 'get'" crash

Three more live reports came in right after v1.15.4 shipped -- same exact crash text, but with
completely different tool sequences each time (4 tools, then 9 tools, none overlapping with
the hazard/HDX tools v1.15.4 fixed), all on a session configured with **Google Gemini**.

Three separate reproduction attempts (a scripted client, a real-QGIS run with real layers, and
a run through the actual cross-thread dispatcher mechanism a live session uses) all came back
clean against the reported tool sequences -- ruling out every individual tool involved and the
dispatch machinery around them a second time. The common factor across all three reports
wasn't any specific tool; it was the provider.

**Root cause**: `providers/base.py`'s `extract_openai_style_usage` (added in v1.15.0's Gemini-
caching-visibility work, and not covered by v1.15.4's audit since that code didn't exist yet
when this bug class was first found) extracted the cache-hit count with:

```python
cached_tokens = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
```

This only degrades safely when the field is missing or falsy. If a provider's OpenAI-compatible
response ever returns `prompt_tokens_details` as a **truthy non-dict** (a bare string being the
most likely real shape for a compatibility-shim quirk), `x or {}` returns `x` itself -- `or`
short-circuits on the first truthy operand -- and the following `.get()` raises uncaught,
producing exactly the reported error text. Confirmed with a one-line repro:
`("some string" or {}).get("cached_tokens")` raises `AttributeError: 'str' object has no
attribute 'get'`.

**Fixed** with an explicit `isinstance(details, dict)` check instead of relying on truthiness.
This is the shared usage-extraction point for all 4 OpenAI-style providers (Gemini, OpenAI,
OpenRouter, and the hosted-gateway prototype), so the fix protects all of them, not just Gemini.
New regression test confirms the exact malformed-response shape now degrades to "no cache-hit
info available" instead of crashing the whole turn. Full suite 1530 -> 1531, 0 failures.

<a id="v1-15-4"></a>
## [1.15.4] — 2026-09-13 — Patch: root-caused the "'str' object has no attribute 'get'" crash

Following up on `BUG-2026-09-13-2` (see `docs/BUG_TRACKER.md`): a full audit of the tool-
dispatch and `.get()` call surface, prompted directly by the live crash report, found the
real gap.

**Root cause**: `agent.py`'s `_execute_two_phase_tool` (the dispatch path used by
`fetch_worldpop_population` and the 3 hazard-monitoring fetch tools, among others) has no
exception handling of its own -- unlike the regular tool dispatch path, which wraps its
function call in a broad `try/except`. Within that unguarded surface, 3 real network-fetch
functions called `.get()` on a freshly `json.loads()`'d API response OUTSIDE their own
`try/except`'s coverage: `fetch_nasa_eonet_events_network_phase` and
`fetch_gdacs_disaster_alerts_network_phase` (`hazard_monitoring_tools.py`),
`fetch_hdx_admin_boundaries_network_phase` (`humanitarian_tools.py`). If any of these APIs
ever returned valid JSON that wasn't a dict (a bare string/list/null error body -- GDACS's
own docs already warn its data "may require further validation"), that `.get()` call raised
an uncaught `AttributeError` that escaped the entire tool-calling loop, surfacing as a bare
Python exception in the chat instead of a normal error message.

**Fixed in two parts**:
- A general safety net in `agent.py`'s `_execute_tool`: any exception from any tool dispatch
  path now becomes a normal `{"error": ...}` result. This closes the whole class of bug for
  every tool -- present or future -- not just the 3 found.
- Proper `isinstance(data, dict)` guards at the 3 specific sites (plus
  `fetch_building_footprints_network_phase`'s per-line JSON parsing, same pattern, lower
  risk), giving a clear, attributable error message instead of relying on the safety net
  alone.

Also fixed a matching but structurally different gap in `chat_tab_widget.py`'s
`_analyze_image` (already caught by its own surrounding `try/except`, so not this specific
bug, but the same risk class, worth closing while auditing this).

5 new tests covering the exact malformed-response scenarios and the general safety net; full
suite 1525 -> 1530, 0 failures.

<a id="v1-15-3"></a>
## [1.15.3] — 2026-09-13 — Patch: the user's own replies weren't showing up in chat

Direct follow-up report after v1.15.2 shipped: "some of my text i sent in the chat is not
showing." Root cause: when a requirement-gate question (see v1.15.2) was answered, the reply
got folded into the pending request behind the scenes -- it was never emitted as its own chat
message. For a request needing only one missing detail this was subtle (the eventual composed
request still appeared once dispatch/preview happened, so something visible did show up
eventually). For a request needing two unresolvable details in a row (e.g. `facility_type` AND
`sector`, both with no safe default to guess), asking a second time silently replaced the first
question with no trace the first answer was ever received -- exactly matching the report.

**Fixed**: `chat_tab_widget.py`'s `send_message()` now echoes the literal reply into the chat
log immediately, in the same `_awaiting_requirement_reply` branch, before merging it into the
pending request text. Live-verified in real QGIS: a genuine 2-round clarification (facility
type, then sector) now shows both replies as their own messages, in order, exactly as typed.
New `test_multi_round_clarification_shows_every_reply_in_chat` plus a new assertion on the
existing single-round test; full live-widget suite 8/8, full suite 1525 tests, 0 failures.

<a id="v1-15-2"></a>
## [1.15.2] — 2026-09-13 — Patch: requirement-gate questions now ask in chat, not a boxed panel

Direct user feedback, with a real screenshot: "i dont like the style of the feedback from
cartogen AI make it more in the chat and get user response interactive chat." The complaint was
about the task-register requirement gate -- asked when a request is missing a slot with no safe
default to guess (e.g. hazard type: guessing wrong produces confidently wrong humanitarian
output) -- which showed as a separate `QGroupBox("One more detail needed")` panel above the
input row, with two buttons and the input box locked read-only. Visually, it read as a foreign
popup rather than part of the conversation above it.

**Fixed** by posting the question as a normal Cartogen chat message instead. The input box stays
fully live the whole time -- answering it is just typing a reply and hitting Send, exactly like
any other turn. Behind the scenes, that reply is merged into the original request (the same
"Details: ..." convention the old Edit-request button used to pre-fill into the box) and re-run
through the same analysis pipeline, so a second still-missing slot asks again the same
conversational way rather than needing a different mechanism.

Also removed "Proceed with stated defaults" as confirmed dead code while making this change: the
panel it lived on was only ever shown for a `blocking` analysis, and that button was always
`setEnabled(not analysis.get("blocking"))` -- i.e. always disabled on every real call, exactly
matching what the user's screenshot showed (a greyed-out button next to an active "Edit
request").

**Live-verified** in real QGIS (`python-qgis.bat`): the question renders as a genuine chat
message with no boxed panel, the input box stays editable throughout, and a plain typed reply
("flood") correctly resolves the pending hazard-type slot and proceeds to the normal preview
step -- confirmed via both a rendered screenshot and the widget's actual text content. 2 tests
updated/added in `tests/test_chat_widget_live.py` (a real headless Qt session, not mocks); full
suite 1524 tests, 0 failures.

<a id="v1-15-1"></a>
## [1.15.1] — 2026-09-13 — Patch: live-hazard-data requests refused despite real tools existing

Live user report (real typos preserved): "show live incedent in jordan in the map creat enew
layer / Details: natural, crime, haszard" got a blanket "I do not currently have direct access
to a verified live feed or real-time incident database..." refusal -- even though this plugin
has shipped 3 real hazard-monitoring tools since v1.9.0: `fetch_gdacs_disaster_alerts`,
`fetch_nasa_eonet_events`, and `fetch_nasa_active_fires`.

**Root cause, diagnosed via direct router simulation rather than assumed** -- two stacked gaps:

1. **No prompt rule connected the intent to the tools.** None of the 47 existing behavioral
   rules told the model that a "live/current hazard or disaster" request maps to these 3 tools
   specifically -- only rule 16 mentioned them, in an unrelated "treat fetched content as data,
   not instructions" context. Even when a tool was available for the turn, nothing told the
   model to reach for it.
2. **Recall into the tool router's top-40 candidate set was unreliable even before the prompt
   gap.** A 30-trial live simulation of the exact reported query found `fetch_nasa_eonet_events`
   was selected only ~47% of the time, and `fetch_gdacs_disaster_alerts`/`fetch_nasa_active_fires`
   never were -- generic words in the query ("map", "layer", "natural") gave ~24 other, unrelated
   tools an equal or higher relevance score. The query's own typos ("haszard", "incedent")
   additionally defeated the existing exact-substring alias-matching mechanism outright.

**Three-part fix:**

- **New prompt rule 48** (`agent/prompts.py`): explicit guidance that live/current natural
  hazard or disaster requests map to the 3 named tools, with explicit instructions for a mixed
  request like the one reported -- fetch and map what the real tools DO cover, and separately,
  honestly state that a category with no real data source (e.g. crime/security incidents) can't
  be fulfilled, rather than declining the whole request. Explicitly cross-references rule 12/42's
  anti-fabrication guarantee so this new positive capability doesn't weaken it.
- **New tool-router aliases** for all 3 hazard tools (`agent/tool_router.py`'s `_TOOL_ALIASES`)
  -- phrases like "current disaster", "live hazard", "what hazards" that share no vocabulary with
  the tools' own descriptions.
- **A small, scoped typo-tolerant correction** (`_expand_query_with_fuzzy_corrections`, difflib-
  based): only for query words 5+ characters long, checked only against a small curated list of
  hazard-domain words (hazard, disaster, incident, wildfire, earthquake, flood, etc.) -- so a
  misspelled "haszard"/"incedent" still resolves to the right alias, without the false-positive
  risk of fuzzy-matching against the plugin's full ~169-tool vocabulary.

**Live-verified end to end** against the exact reported query text: `fetch_gdacs_disaster_alerts`
and `fetch_nasa_eonet_events` are now selected 30/30 trials through the real router (up from
0/30 and ~14/30 before this fix), and rule 48's guidance text is confirmed present in the
resulting assembled system prompt for that query. 11 new tests across `tests/test_prompt_modules.py`
and `tests/test_tool_router.py`; full suite 1512 -> 1523, 0 failures.

**Honest limitation**: the actual downstream model behavior change (does the LLM now correctly
call these tools instead of refusing) cannot be confirmed from this sandbox -- there is no live
network access to a real LLM API here. This release verifies the router selects the right tools
and the prompt carries the right guidance; the user is the one who can confirm the model
actually acts on it in a live session.

<a id="v1-15-0"></a>
## [1.15.0] — 2026-09-13 — Gemini prompt caching (automatic, implicit) + cache-hit visibility

Direct request — "implement gemini caching, check the documentation" — following a real report
of ~168K tokens for one 6-call print-layout turn. Researched Google's current Gemini API docs
before writing any code, not assumed.

**Implicit caching is automatic and free for Gemini 2.5+/3.x models** — no client code needed to
trigger it, ~90% discount on cache hits, no storage cost. It requires the cached content to sit
as a stable prefix above a per-model minimum (2,048 tokens for 2.5 Flash/Pro, 4,096 for 3.x
Flash/3.1 Pro Preview). Confirmed this plugin's system prompt/tools already meet both: they're
computed once before `agent.py`'s tool-calling loop starts and never rebuilt mid-turn — a
multi-call turn's repeated system prompt is exactly the shape implicit caching targets. There was
nothing to implement here beyond confirming it isn't accidentally defeated.

**What was actually missing was visibility.** The Gemini OpenAI-compatible endpoint reports cache
hits via `usage.prompt_tokens_details.cached_tokens` (a sub-breakdown of `prompt_tokens`, not
subtracted from it), but nothing in this codebase surfaced it — so whether caching was helping
was an unverifiable assumption.

- **Explicit caching** (a separate `CachedContent` resource with its own lifecycle/storage cost)
  was considered and deliberately not built: implicit caching already covers the exact scenario
  driving this report — repeated identical content within one turn's loop — for free, and the
  per-turn module-based system prompt (v1.14.0) limits explicit caching's cross-turn reuse value
  for the added complexity.
- `providers/base.py`'s `extract_openai_style_usage` (shared by Gemini/OpenAI/OpenRouter/Ollama)
  now also extracts `cached_tokens` when present.
- `providers/claude.py`'s `from_anthropic_response` gets the same visibility, for symmetry —
  Claude already sends `cache_control` breakpoints (from earlier this session) but never
  surfaced `cache_read`/`cache_creation` token counts either. Anthropic's own `input_tokens`
  deliberately *excludes* cached tokens (unlike Gemini/OpenAI's convention, which includes them
  in the headline total), so it's reconstructed to the full request size for cross-provider
  consistency.
- Session usage now shows e.g. `"~24,747 tokens this session (3 calls, ~14,400 served from
  cache)"` — omitted entirely (not fabricated as 0) when nothing was reported, same honesty
  policy the usage feature has always had.

No new agent tools — 169 tools, unchanged. 18 new tests, full suite 1506 → 1512, 0 failures.
Live-verified end to end in real QGIS 4.2.2: a realistic Gemini response shape parses correctly,
a 3-turn fake-client session accumulates cache hits and produces the exact expected label text,
and the real `ChatTabWidget` renders it.

**Honest limitation, stated plainly**: this sandbox has no live network access to a real Gemini
API key, so whether the actual API genuinely returns `prompt_tokens_details.cached_tokens`
through this specific OpenAI-compatible endpoint (vs. only the native endpoint) is confirmed
against Google's documentation, not confirmed end-to-end against a real response. The parsing
logic is correct for the documented shape and degrades safely (omits `cached_tokens`, doesn't
crash) if the real field name or nesting ever turns out to differ.

<a id="v1-14-1"></a>
## [1.14.1] — 2026-09-13 — Patch: floating dock clamped to the screen

Direct live report: after a long print-layout response, the chat input row was no longer
visible — the floating panel's window appeared to end right where the response content did, no
input box reachable.

Investigated thoroughly before changing anything: tried to reproduce with a small window plus
long content, a bloated Activity tab (many tasks/memory entries accumulated over a session), and
the exact reported scenario (6 API calls, multiple tool-step summaries, a long final response) —
in every headless test, `chat_tab_widget`'s layout correctly kept the input row visible and
positioned within the window (`QTextBrowser.sizeHint()` stays content-independent, confirmed
live; the Activity tab's `QScrollArea` correctly caps its own outward size hint regardless of
its content's real size). Could not reproduce a layout defect in the sandbox.

A floating window that's grown or drifted past the available screen's height/position is a known
Qt/Windows failure mode that produces exactly this symptom — the input row still exists in the
layout, just rendered below the visible screen area, invisible and unreachable without a manual
resize. Added a defensive `resizeEvent` guard: while floating, clamps the dock's geometry to fit
within `QScreen.availableGeometry()` whenever it would otherwise extend past it. Idempotent (a
window already on-screen computes no change), so safe on every resize with no recursion risk.
Only acts while floating — a docked panel is already bounded by the main QGIS window.

Live-verified: forced the dock to an absurdly tall, partly off-screen geometry and confirmed the
guard clamps it back on-screen, with the input row's own on-screen position confirmed within the
visible screen area afterward. `dock_widget.py` has no automated test coverage (no
`QGIS_AVAILABLE` fallback, by its own module docstring), so this relies on live verification per
this file's established convention, not a new unit test. No new agent tools — 169 tools,
unchanged. Full suite unaffected: 1506 tests, 0 failures.

<a id="v1-14-0"></a>
## [1.14.0] — 2026-09-13 — Modularized the 47-rule base prompt by relevance

Follow-up to v1.13.1 (the tool-router side of the same token-waste problem). Direct request: the
remaining ~8,149-token base system prompt should be trimmed the same way tool schemas already
are. Investigated the actual content first, rather than assuming — `BASE_SYSTEM_PROMPT` contains
**no JSON schemas at all** (those are the separate, already-fixed `TOOLS_SCHEMA` path); it's
100% plain-English prose, **47 numbered behavioral rules** always sent in full regardless of
what the request actually needed.

Read and categorized all 47 rules before designing anything, into three tiers — confirmed with
the user via `AskUserQuestion` on risk tolerance for the safety-critical cluster before
implementing:

- **CORE (16 rules, always included)**: task/memory mechanics, the destructive-action safety
  gate, anti-fabrication, output structure, ask-vs-guess defaults. Applies to every request, no
  relevance heuristic needed or wanted.
- **SENSITIVE cluster (10 rules)**: protection-sensitive data handling, never-fabricate-
  security-incidents (rule 42 exists because of a real, cited past incident — a live user report
  of a fabricated Beirut security briefing exported looking authoritative), operational-briefing
  sourcing standards, sensitivity-check-before-export. Included whenever ANY tool from a
  deliberately **wide, hand-verified** trigger list is selected this turn — every export/
  deliverable tool, incident/sensitivity tool, and humanitarian-logistics/routing tool — not
  narrowly gated to "sounds humanitarian." Hand-verified rather than auto-extracted specifically
  for this cluster: a rule's own prose sometimes names the *wrong* tool for triggering purposes
  (rule 42 names `search_web` as the recommended fix for fabrication, not the risky report/
  export action that should actually trigger the rule).
- **Remaining 21 domain rules** (styling, imagery, workflows, documents, forecasting, web
  search, print layouts, time-series dates): trigger tools extracted **automatically** via a
  one-time regex scan of each rule's own backtick-quoted tool mentions against the real
  `TOOLS_SCHEMA` — no hand-maintained list to drift out of sync as tools/rules change.

**Found and fixed a real bug during live verification, not just unit tests**: router-guaranteed
tools (`execute_pyqgis_script`, the 8 always-include core tools) were polluting the
auto-extraction, since their presence in `active_tools` doesn't mean a rule's actual domain is
relevant — rule 30 (print-layout composition) was firing on a plain `"hi"` purely because
`execute_pyqgis_script` is the router's guaranteed no-signal fallback tool, nothing to do with
print layouts. Fixed by excluding router-guaranteed tool names from the auto-extraction signal;
a rule left with zero real trigger tools after that (rule 8) safely falls back to always-on
rather than silently vanishing.

Every rule keeps its **original number permanently** in every tier — 47 rules cross-reference
each other by number (20 such references, confirmed via grep), so renumbering would silently
break them. Included rules are always assembled in ascending numeric order, so the full/
unfiltered `BASE_SYSTEM_PROMPT` (kept for `tests/manual_prompt_rule_evals.py`) is verified
**byte-identical** to this file's pre-modularization content, not just "close enough."
`agent.py`'s `run()` was reordered so `ToolRouter.filter_relevant_tools()` runs before
`build_system_prompt()`, passing the selected tool names through as a new
`active_tool_names` parameter (default `None` reproduces the exact prior behavior for any
caller that doesn't pass it).

No new agent tools — 169 tools, unchanged. **Measured effect**: a real `agent.run("hi")` call's
full payload (system prompt + tools) dropped from ~9,316 tokens (v1.13.1's number) to **~3,184
tokens — ~84% below the original ~22,959-token report** that started this whole thread. Real
GIS requests save 15-30% depending on domain. Live-verified against real QGIS 4.2.2 for a plain
`"hi"`, an export request, a humanitarian-logistics request, and a print-layout request,
confirming the sensitive cluster and the right domain rules appear/don't appear as designed —
plus a spot check across 7 realistic humanitarian-flavored queries confirming the sensitive
cluster fires on every one. 18 new tests, full suite 1488 → 1506, 0 failures.

<a id="v1-13-1"></a>
## [1.13.1] — 2026-09-12 — Patch: a plain "hi" was costing ~23K tokens from tool-router padding

Patch release, found and fixed the same day v1.13.0 shipped: a direct live report that a single
plain `"hi"` message cost **~22,959 tokens for one API call**. Traced to
`tool_router.py`'s `filter_relevant_tools()` always padding out to the full `top_k=40` tool
schemas even for a query with zero real signal — worsened by two real matching bugs, not just
one padding issue:

- **Substring containment, not word-boundary matching.** Name/description scoring used
  `word in text` — a 2-character query word like `"hi"` spuriously substring-matched inside
  completely unrelated tool names (`histogram_equalization`, `highlight_features`, `hillshade`),
  scoring a real-looking +10. That was enough to make the router's own "nothing else matched"
  check evaluate `False`, triggering full `top_k` padding with ~30 more essentially random tool
  schemas. Fixed by splitting tool names on `_` and tokenizing descriptions with the same `\w+`
  regex already used for the query — both checks are now genuine word-boundary membership tests.
- **No-signal queries still padded to `top_k`.** Even once correctly detected as having zero
  real signal, the router still filled the remaining slots with random 0-score filler instead of
  returning only the genuinely useful always-include + fallback set (9 tools). Fixed: a
  no-signal query now returns only tools that scored above 0.
- **A follow-up gap the word-boundary fix alone didn't close**: `"hello there"` still pulled in
  the full padded set, because `"there"` is a genuine standalone word in several tool
  descriptions' ordinary prose (`"is there flooding here"`) — a true match, just for a word
  carrying zero intent signal. A small, conservative stopword list (articles, pronouns, common
  greetings/acknowledgments) is now filtered out of query words before scoring — the curated
  alias list and the always-include/fallback logic are untouched.

Every real-signal query tested (buffer, calculate severity index, NDVI, all 8 existing
alias-coverage tests) is completely unaffected — still gets the full `top_k=40` candidate pool
exactly as before. Measured effect: `"hi"`'s filtered-tools payload dropped from 40 tools
(~8,133 tokens) to 9 tools (~1,027 tokens); a real `agent.run("hi")` call's full payload (system
prompt + tools) dropped from ~22,959 to ~9,316 tokens in live verification against a real QGIS
4.2.2 session, not just the router in isolation. No new agent tools — 169 tools, unchanged. Full
suite 1484 → 1488 tests, 0 failures.

<a id="v1-13-0"></a>
## [1.13.0] — 2026-09-12 — Rate-limit/task-size resilience: 429-aware backoff, adaptive pacing, mid-turn compaction

Direct request: prevent a large/complex request from failing outright when it hits a provider's
API rate limit, or simply from its own size. Investigated actual current behavior before
designing anything, rather than assuming: `agent.py`'s tool-calling loop could fire up to 20
back-to-back `client.complete()` calls with **zero pacing**, and each iteration re-sent every
prior tool result in full — a large task's per-call payload grows unbounded through the turn.
When the iteration limit was hit, the turn just stopped with a static message asking the *user*
to manually break up their own request — no automatic mitigation. Separately, `post_with_retry`
already retried a transient 429/5xx twice with a short 1.5s/3s backoff, but a genuine *sustained*
per-minute quota breach usually outlasts that. OpenRouter's client turned out to already have
real resilience here (a model-fallback chain plus a 30s-wait/3-cycle loop) — confirmed via grep
that Claude, OpenAI, Gemini, and Ollama had nothing like it, only the shared short-backoff path.

- **429 gets its own, longer retry budget** (`providers/base.py`): `RATE_LIMIT_BACKOFF_SECONDS=10`,
  `RATE_LIMIT_MAX_RETRIES=3` (10s/20s/30s, roughly a minute of patience) — separate from the
  existing generic 5xx/network-blip budget, since a rate limit needs to wait out an actual quota
  window while a transient 5xx usually clears in a second or two. Lifts Claude/OpenAI/Gemini/
  Ollama to roughly OpenRouter's own level of sustained-rate-limit resilience. Also fixed
  `gemini.py`'s `grounded_search()` — the one raw `requests.post()` call a grep sweep found
  bypassing the shared retry helper entirely.
- **Adaptive inter-iteration pacing** (`agent.py`): once a turn's tool-calling loop passes 3
  iterations, each further one adds a short `1.2s` delay before the next `client.complete()` call
  — a normal, small request (1-3 tool-call rounds) pays nothing at all; only a genuinely large
  multi-step task starts spacing its own remaining calls out, in direct proportion to how large
  it's getting, reducing the chance of ever tripping a provider's requests-per-minute limit in
  the first place rather than only reacting after the fact.
- **Mid-turn context compaction** (`agent.py`): once a turn's in-flight message list accumulates
  more than 8 tool-result messages, older **successful** ones get replaced with a short
  placeholder — the most recent 8 stay in full. Any tool result containing an `"error"` key is
  **never** compacted, at any age — failures stay load-bearing, the identical call v1.12.0's chat
  tool-steps redesign already made for the identical reason. This is turn-local: the in-flight
  message list never touches persisted conversation history, so compaction only affects what
  gets sent for the rest of the turn already in flight.

No new agent tools — 169 tools, unchanged. Full suite 1484 tests (up from 1478), 0 failures.
Live-verified against a real `CartogenAi` agent instance and real tool dispatch (`get_layers`
against a real `QgsProject`, not a stub) in real QGIS 4.2.2: a 20-iteration looping turn produced
exactly 17 pacing sleeps (iterations 3-19) and correctly compacted 11 old tool results while
keeping the most recent 8 in full.

<a id="v1-12-0"></a>
## [1.12.0] — 2026-09-12 — Onboarding profile, Help auto-show, tidier tool-call summary

Third round of the same real-session feedback thread as v1.11.0, starting with a genuine
regression in that release's own bubble accent stripe, then a further batch of direct requests
clarified via AskUserQuestion before implementing.

- **The v1.11.0 accent stripe wasn't actually rendering.** It looked correct in code and had
  passed a screenshot "confirmation" — but that check only found the expected accent color
  *somewhere* in a full-widget screenshot, not proven to be the bubble itself. The real bug: Qt's
  rich-text table CSS silently drops `border-left` when a `border` shorthand is already set on
  the same cell — confirmed by rendering an unmistakable magenta `border-left` in isolation and
  finding it never appeared in the output at all. Fixed with a two-cell table instead of a CSS
  trick: a dedicated 3px stripe cell using only `background-color` (no border), beside a content
  cell keeping its border but only on 3 sides. Verified properly this time by isolating just the
  `QTextBrowser` (not the whole parent widget, which has its own accent-colored QSS chrome — the
  exact trap that produced the false-positive the first time) and checking for a narrow,
  spatially-consistent run of the exact accent color.
- **Version menu entry removed.** v1.11.0 added a disabled `"Cartogen AI vX.Y.Z"` Plugins-menu
  entry alongside the version already shown inside Help — direct same-day feedback said that was
  one place too many. Version now shows only inside the Help dialog's own content.
- **Help now auto-shows**: the first time the plugin ever loads, and again once after any version
  update (a new `help_last_shown_version` setting compared against `metadata.txt`'s version on
  every `initGui()`) — previously the user had to know to look for it in the Plugins menu at all.
- **New first-use onboarding profile** (`agent/onboarding_profile.py`, `ui/onboarding_dialog.py`):
  a short dialog — narrative intro, then role/use-case, QGIS experience level, and communication
  style pickers — saved as a real, human-readable `user_profile.md` in the QGIS profile directory,
  not a hidden settings blob, so it can be opened and hand-edited directly. Feeds the base system
  prompt on every request via a new `build_system_prompt(user_profile_ctx=...)` parameter,
  deliberately separate from `prompt_refiner.py`'s pre-existing "user_profile" (the Refinement
  Persona sector dropdown, a different concept that only steers the optional prompt-refinement
  rewrite). Deliberately a static dialog, not an LLM-driven conversation — onboarding has to work
  before any API key is configured, which a live "the agent asks you" exchange wouldn't. Re-editable
  anytime via a new Settings → "Edit My Profile…" button.
- **Chat tool-call display redesigned.** Every tool call previously rendered 2 separate lines
  directly in the conversation scrollback (`Using X` / `Used X`) — real feedback called this too
  much visual space, too much raw detail, and too much visual noise for a multi-tool-call turn.
  "Running" status now updates the existing status label in place instead of adding a scrollback
  line; terminal steps are collected per turn and flushed as **one** compact
  `"N tool calls · name, name"` summary with a "Details" toggle — this chat log's first internal
  clickable anchor (intercepted via `anchorClicked` with `openLinks` disabled; real http(s) links
  in AI responses are unaffected, still handled by `openExternalLinks`). Any failed step's error
  text is always shown regardless of toggle state, never collapsed. The toggle is implemented via
  `QTextCursor` position tracking with explicit shift-adjustment for every later block after an
  edited one — directly live-verified with a 2-turn scenario proving stored positions actually
  shift correctly and a later block's toggle still targets the right span afterward, rather than
  trusting that the logic "looks right" (the same lesson this session's bubble-border fix already
  ran into twice).

No new agent tools — 169 tools, unchanged. Full suite 1478 tests (up from 1457), 0 failures.
Live-verified against real QGIS 4.2.2 throughout: `OnboardingDialog` builds and its Other-role
field toggles correctly; a full save writes a real `.md` file to disk and
`get_formatted_onboarding_context()` reads it back; Settings' Edit My Profile button opens it;
`build_system_prompt()` includes the profile block end to end; Help auto-show/onboarding-trigger
logic exercised through all 3 states (first run, same version, version bump) via a mocked
`iface`; the tool-steps toggle mechanism per above.

<a id="v1-11-0"></a>
## [1.11.0] — 2026-09-12 — Real-session UI fixes: bubble double-border, Activity tab rename, Help moved to menu

The v1.10.0 UI redesign above was verified against this session's own synthetic `widget.grab()`
screenshots. A user then shared real screenshots from their own live QGIS session, and they
caught two genuine bugs the synthetic ones never surfaced, plus several direct layout requests.

- **Chat bubbles, two stacked bugs.** `QTextBrowser` renders message HTML through Qt's own
  rich-text engine — a CSS 2.1-ish subset with **no `border-radius` support at all** — so the
  existing `border-radius:8px` had never actually worked; every bubble has always rendered as a
  sharp rectangle in real QGIS, unlike this same dock's QSS-styled buttons/tabs, which do support
  `border-radius` (a completely different rendering path). Separately, the outer alignment
  `<table>` never set `border="0"`, so Qt's rich-text engine drew its own default border around
  it, stacking visibly with the inner bubble's real border — a genuine double border. Fixed both:
  `border="0"` on the outer table, and the dead `border-radius` replaced with a
  `border-left:3px solid` accent stripe (the same flat-message shape GitHub PR review comments
  and Slack thread replies use) — user messages get the brand accent, agent messages stay
  neutral. `chat_formatting.derive_bubble_colors()` now exposes that accent value directly.
- **A Qt mnemonic-parsing bug.** "Tasks & Notes" rendered as "Tasks _Notes" in the screenshots —
  Qt's plain-text widget-label parser treats a bare `&` immediately followed by a space as an
  accelerator marker it can't resolve. (The QGIS Plugins-submenu title `"&Cartogen AI"` is *not*
  affected — `&` immediately followed by a letter is a normal, working mnemonic.) A full sweep
  found the same `"X & Y"` pattern in 3 more `tasks_tab_widget.py` labels (`QGroupBox`,
  `QPushButton` — the same affected widget types) not visible in the screenshots but very likely
  broken the same way, plus 3 rich-text `QLabel`s that aren't actually affected (HTML content
  bypasses the mnemonic parser) but got the same wording fix for consistency. Renamed the tab
  itself to **Activity** — the user's own choice among the options offered — rather than just
  escaping the ampersand, spelling out "and" everywhere else.
- **Help moved out of the dock entirely**, into the QGIS Plugins menu (`Cartogen AI → Help`) as a
  standalone non-modal dialog reusing the existing `HelpTabWidget`. A new disabled
  `"Cartogen AI vX.Y.Z"` menu entry (read at runtime from `metadata.txt`, mirroring
  `plugin_upload.py`'s own `get_plugin_version()`) makes version info discoverable from the main
  menu, per direct request — also shown a second time at the top of the Help dialog's own content.
- **Quick-suggestion chip row removed** from the bottom of the Chat tab ("irrelevant" — direct
  feedback). `QUICK_SUGGESTION_CHIPS` stays defined in `dock_constants.py`; Help's own
  example-prompts list is its only consumer now.
- **Both scrollbars showing at once on the Activity tab, fixed.** Its `QScrollArea` now forces
  `ScrollBarAlwaysOff` horizontally so content wraps instead of ever triggering horizontal
  scroll; vertical scrolling (needed to stop the dock forcing the whole QGIS window taller than
  the screen) is unchanged.

No new agent tools — 169 tools, unchanged. Full suite 1457 tests (up from 1456), 0 failures.
Live-verified against real QGIS 4.2.2: 2 tabs (Chat, Activity, down from 3), zero chip buttons,
horizontal scrollbar policy confirmed `ScrollBarAlwaysOff`, `HelpTabWidget` builds standalone
with a version string, and `dock-panel.png`/`chat-conversation.png` regenerated to show the
corrected UI.

<a id="v1-10-0"></a>
## [1.10.0] — 2026-09-12 — UI & Chat Redesign: brand-accent blending, theme-reactive SVG icons

A visual polish pass on the dock/chat UI, grounded in real QGIS plugin design research rather
than generic web-design advice — published first as a review Artifact, corrected once (a
research agent had reported 3 already-fixed UX-audit items as still open; re-reading the live
code before planning caught it), then implemented as 4 workstreams. Structure, the markdown
renderer, and the message-bubble mechanism are unchanged — this is polish on a sound base, not a
rebuild.

- **Two-tier theme detection.** `ui/theme.py`'s new `_detect_theme_mode()` checks QGIS's own
  named theme (`QgsApplication.instance().themeName()`, `"Night Mapping"`/`"Blend of Gray"`)
  before falling back to the existing palette-luminance read — QFieldSync's real, shipping
  pattern (`qfieldsync/gui/utils.py`), since a named theme can pick a scheme that doesn't show
  up as a clean luminance difference in every `QPalette` role.
- **Brand-accent color blending.** New `_brand_accent()` in `chat_formatting.py` blends QGIS's
  own live accent color toward the Cartogen brand teal (`#1F7A6C`) at a modest 0.35 ratio,
  reusing the already-tested `_blend_hex()` helper — a blend, never a replacement, so the accent
  still varies across QGIS themes instead of becoming one fixed color. Wired into
  `derive_bubble_colors()` (the user-message bubble tint) and `build_dock_stylesheet()`
  (buttons, selected-tab underline, focus border, chip buttons). The first brand color to reach
  the running UI at all — every color before this was purely QGIS-palette-derived, with zero
  connection to the plugin's own documented brand system.
- **Theme-reactive SVG icons.** New `ui/icons.py`: hand-authored, in-repo SVGs (attach, send,
  stop, settings) — matches the observed QGIS plugin-ecosystem convention (custom SVG icons
  in-repo, e.g. `opengeos/qgis-plugin-template`) rather than an icon font. `themed_icon()`
  renders a template at a given color entirely in memory (no temp file), colored from the live
  palette at construction time — the same pattern TerraLabAI's `QGIS_AI-Segmentation` plugin
  uses for its own dock icons. Replaces the plain Unicode emoji (📎 ➤ ⏹ ⚙) in the chat input
  row and the Settings button. The toolbar/menu action icon also switched from a flat `icon.png`
  to `icon.svg`, a copy of the real brand mark — placed at the plugin root specifically because
  `plugin_upload.py`'s `EXCLUDE_DIRS` excludes the whole `branding/` folder from the release
  zip; pointing directly at `branding/cartogen-mark.svg` would have silently shipped a plugin
  with an empty toolbar icon. Caught by checking the exclusion list before wiring it up, not by
  trial and error.
- **One wording alignment.** The Preview panel's bypass-send button ("Send my wording only") now
  matches the Refinement panel's identical action ("Send as typed instead") exactly — the one
  real inconsistency once the other 3 items a prior UX audit flagged were confirmed already
  fixed in code.

No new agent tools — 169 tools, unchanged. 9 new tests (color-blend determinism/non-collapse
behavior, icon SVG generation). Full suite 1456 tests (up from 1447), 0 failures. Live-verified
against real QGIS 4.2.2 via actual rendered screenshots of the wired-up input row, dock header,
gate-panel wording, and toolbar icon, in both light and forced-dark palettes — not just
import-success checks, since a visual redesign can't be verified any other way.

<a id="v1-9-0"></a>
## [1.9.0] — 2026-09-12 — Live Hazard Monitoring: NASA FIRMS/EONET + GDACS tools, dashboard freshness badges

Inspired by [koala73/worldmonitor](https://github.com/koala73/worldmonitor)'s live-event
dashboards (crisis/disaster alerts, satellite fire detections) — adapts the *techniques*, not
code (a completely different stack), and deliberately kept narrow: hazard data feeding this
plugin's existing humanitarian analysis tools, not a general "crisis/geopolitical intelligence"
product. Positioning checked against this project's own commercial strategy docs before
building — see `docs/archive/COMMERCIAL_PRODUCT_STRATEGY.md`'s feature-placement test and
`docs/archive/ENTERPRISE_GROWTH_PLAN.md`'s explicit warning against broadening Cartogen's
positioning beyond humanitarian-GIS-first.

- **3 new live hazard fetch tools**, `agent/tools/hazard_monitoring_tools.py`:
  - `fetch_nasa_active_fires` — NASA FIRMS VIIRS active-fire/thermal-anomaly detections. First
    Cartogen tool needing its own API key, separate from any LLM provider key — a new optional
    field in Settings ("NASA FIRMS API Key"), stored via the same `CredentialManager` every
    provider key already uses.
  - `fetch_nasa_eonet_events` — NASA EONET natural event tracker (wildfires, storms, volcanoes,
    floods, and more). Free, no key.
  - `fetch_gdacs_disaster_alerts` — GDACS UN-coordinated disaster alerts, each with a
    human-assigned Green/Orange/Red severity. Free, no key. Live-verified GDACS's own bbox query
    parameter doesn't actually filter server-side, so filtering happens client-side after
    fetching, the same pattern `fetch_building_footprints` already uses for its tile crop.
  - All 3 use `[min_lon, min_lat, max_lon, max_lat]` (matching `search_stac_satellite_imagery`),
    deliberately not `fetch_building_footprints`'s `[south, west, north, east]` — a real footgun
    confirmed live during this project's own v1.8.3 release smoke test.
  - Re-running any of the 3 (e.g. on a schedule) **replaces** that layer's features with the
    latest fetch rather than accumulating duplicates. Each auto-tags layer confidence
    (`OBSERVED` for FIRMS/EONET, `DERIVED` for GDACS) and stamps a `cartogen_ai/fetched_at`
    custom property.
- **`generate_situation_dashboard`** — one call fetches all 3 sources for a bbox and exports
  them as a single HTML dashboard.
- **Wired into the existing monitoring scheduler** — all 3 tools added to
  `_ALLOWED_WORKFLOW_TOOLS`, extending its documented safety rationale to a second category
  (idempotent external-data-refresh, never touches user-authored data). `run_monitoring_workflow`
  now reports real "N new fire detections since last check" via its existing
  `_diff_unit_results` mechanism — zero new diffing code, the honest analog of a competitor
  product's persistence tracking built on infrastructure this project already had and had
  already tested.
- **Dashboard freshness badges** — the piece most directly asked for. `generate_html_dashboard`/
  `generate_temporal_dashboard` now render a small color-coded pill per layer that carries a
  `fetched_at` stamp: green "Fresh 2m", amber "Stale 3h", red "Very stale 2d", with a hover
  tooltip showing the exact fetch time. Reproduces the competitor product's exact freshness-pill
  visual pattern in plain inline HTML/CSS — no JS framework, no new dependency. Purely additive:
  a layer never fetched from a live source renders with no badge, and every existing caller
  keeps working unchanged.

41 new tests (25 for the hazard tools, 16 for the freshness badges). Full suite 1447 tests, 0
failures (up from 1406 at the start of this release). 169 tools (up from 165). A real bug
(`generate_situation_dashboard` raising `KeyError` when QGIS is unavailable) was caught by this
release's own test suite and fixed before it shipped. Live-verified against real QGIS 4.2.2 and
the real NASA FIRMS/EONET/GDACS APIs throughout — real layers created, confidence/freshness
stamped correctly, replace-in-place confirmed on a second fetch, client-side GDACS bbox
filtering confirmed to actually narrow results (99 → 3 for a regional bbox), the monitoring
scheduler's diff cycle confirmed against real GDACS data, and the Settings dialog's new FIRMS
key field confirmed to round-trip through the same credential storage every provider key uses.

<a id="v1-8-3"></a>
## [1.8.3] — 2026-09-12 — Patch: release zip was silently missing 4 relocated archive docs

Fixed `BUG-2026-09-12-2`, found and fixed the same day v1.8.2 shipped — caught while verifying
that the v1.8.2 release zip installs cleanly in QGIS, before announcing it.

- **Release zip was missing content.** `plugin_upload.py`'s `EXCLUDE_FILES` matches a file by
  basename regardless of directory. `IMPLEMENTATION_TASK_LIST.md`, `LICENSE_AUDIT.md`,
  `CARTOGEN_AI_PRD.md`, and `CARTOGEN_AI_FEATURE_LIST.md` were correctly excluded there when
  they lived at the repo root (internal dev docs). v1.8.2's repo-organization pass moved all 5
  of those docs (the 4 above, plus `DOCUMENTATION.md`) into `docs/archive/` — a directory that
  is *not* excluded and whose other ~29 files ship normally — but the same 4 stale basenames
  kept matching there too, so `cartogen_ai_v1.8.2.zip` silently shipped without them while their
  sibling `DOCUMENTATION.md` (never in `EXCLUDE_FILES`) shipped fine. Did not affect plugin
  functionality: confirmed via a real QGIS 4.2.2 headless import of the extracted v1.8.2 zip
  that `__init__.py` imports cleanly, `classFactory` is present, and all 165 tools register —
  this was a shipped-content-completeness bug, not a functional one. Fixed by removing those 4
  entries from `EXCLUDE_FILES`; rebuilt the zip and re-verified (fresh `unzip -l` plus another
  real-QGIS import) that all 5 moved docs are now present and non-trivial after extraction.

Full suite unchanged: 1406 tests, 0 failures (packaging-script fix only, no `src/` behavior
touched).

<a id="v1-8-2"></a>
## [1.8.2] — 2026-09-12 — Docs-only: repo reorganization and documentation polish pass

No code, tool, or behavior changes. Prompted by a request to make the repo read as professional
for three audiences at once: external GitHub contributors, a humanitarian-org (UN/NGO)
due-diligence reviewer, and general internal tidiness — while keeping every existing technical
detail, not stripping it down.

- **5 frozen historical docs moved into `docs/archive/`** — `CARTOGEN_AI_FEATURE_LIST.md`,
  `CARTOGEN_AI_PRD.md`, `DOCUMENTATION.md`, `IMPLEMENTATION_TASK_LIST.md`, `LICENSE_AUDIT.md`
  (`git mv`, content unchanged, full history preserved). Every live reference updated; the moved
  `DOCUMENTATION.md`'s own ~27 internal relative links fixed for its new location.
- **Stale tool counts fixed.** "131 tools" → 165 in `README.md`, `docs/PRODUCT_TIERS.md`, and
  `docs/RELEASE_SMOKE_TEST.md` — left untouched wherever a document was explicitly describing a
  dated historical snapshot rather than making a present-tense claim.
- **`README.md`** gained a table of contents and a regrouped, expanded Documentation table
  (Getting started / Security & compliance / Engineering & process / Product & humanitarian
  standards / Roadmap & archive / Project reference) — surfacing 9 previously-untabled files,
  including the GDPR compliance review and DPIA screening worksheet that had no discoverable
  path from the README before. Also gained a dedicated Contributing section.
- **New `docs/README.md`** index, reusing the same category grouping, for anyone browsing the
  `docs/` folder directly on GitHub; notes the two dev scripts' purpose inline so their presence
  reads as intentional.
- **`docs/archive/README.md`** gained a one-line-per-file index of all 33 archived documents.
- **`SECURITY.md`** gained a table of contents over its 19 sections.
- **`CHANGELOG.md`** — the 4 previously-undated `[1.7.0]`–`[1.8.1]` headers now carry real
  dates, plus this "Recent releases at a glance" quick-index.

Full suite unchanged: 1406 tests, 0 failures (comment/doc-only changes touch no `src/` behavior).

<a id="v1-8-1"></a>
## [1.8.1] — 2026-09-12 — Patch: dashboard OSM-blocked basemap + canvas not following new layers

Direct live user report, not from a planned workstream.

- **Dashboard basemap blocked by OpenStreetMap.** `generate_html_dashboard`/
  `generate_temporal_dashboard` (`agent/tools/export_tools.py`) both called bare `folium.Map()`,
  which defaults to raw, unthrottled, uncached `tile.openstreetmap.org` requests with no custom
  User-Agent — exactly the pattern OpenStreetMap's own tile usage policy blocks for bulk/
  embedded-app use. Switched both to `tiles="cartodbpositron"`, folium's standard permissively-
  licensed alternative built for exactly this "embed a basemap in your own generated page" case.
  Confirmed directly that the generated HTML no longer references `tile.openstreetmap.org` at
  all, for either dashboard builder.
- **Canvas doesn't follow new/changed layers.** New `zoom_to_layers()` (`ui/canvas_highlight.py`)
  wired into `ChatTabWidget._after_successful_response` — moves the canvas to the union extent of
  whatever layer(s) a turn's response mentions, once per turn, alongside the existing highlight-
  flash behavior. A real bug caught live before shipping: the first version also skipped any
  layer whose extent was "empty" (zero width/height) alongside a genuinely null extent — live-
  confirmed against real QGIS 4.2.2 that a single-point layer's extent is legitimate but
  registers as empty (a point has no area), so that check silently dropped every single-point
  layer, one of the most common layer types this plugin creates. Corrected to match the existing
  single-layer `zoom_to_layer` tool's own behavior.

8 new tests. Full suite 1406 tests, 0 failures. Live-verified against real QGIS 4.2.2 with a real
`QgsMapCanvas` (not mocked): a single-point layer moved the canvas off a deliberately stale
extent, two layers produced a real union extent, and a cross-CRS layer produced a correctly-
transformed extent.

<a id="v1-8-0"></a>
## [1.8.0] — 2026-09-12 — Cartographic Intelligence: visualization selection, real QA gate, isochrone bands

Adapts an external "QGIS Cartographic Intelligence Standard for AI Agents" document to this
plugin's own architecture, as an integration/gap-closure pass on real existing infrastructure
(`_classify_values`'s skewness-driven classification, `_compute_severity_index`'s composite-index
engine, `dataset_status.py`'s QA-gate state machine, `sensitivity.py`/`confidence.py`'s
classification tags) rather than a from-scratch build. Plan:
`~/.claude/plans/idempotent-popping-haven.md`.

- **Visualization selection.** New `recommend_visualization_method(layer_name, field?,
  intended_message?)` — inspects a layer/field's real geometry type, field type, cardinality,
  and distribution, and returns a recommended styling tool + rationale + warnings. Advisory
  only: never applies styling itself, matching the existing "state the default, don't stop to
  ask" convention. Flags the single most common real-world misuse directly — a raw-count-shaped
  field on a polygon layer gets an explicit warning about choropleth-coloring counts instead of
  a normalized rate. New `apply_rule_based_style` — a real `QgsRuleBasedRenderer` (previously
  unused in this codebase), for fixed-vocabulary fields (e.g. route/facility status) needing a
  caller-chosen color per value plus a mandatory "Unknown / No data" catch-all class.
- **Real sensitivity in the QA checklist.** `generate_map_product_qa_checklist`'s disclosure
  section used to be a static "no automated classification exists yet" stub even after
  `set_layer_sensitivity`/`get_layer_sensitivity` shipped — it simply never read them. Now reads
  the real tag, reason, and export warning. Two new informational categories:
  `classification_sanity` (flags a single-symbol-rendered layer with a numeric field worth a
  second look) and `export_integrity` (confirms an exported file actually exists on disk with
  real content).
- **A real blocking cartographic QA gate.** `dataset_status.py`'s `CARTOGRAPHY_READY →
  PUBLICATION_READY` transition — previously the only transition with zero automated checks of
  any kind — now has a real, opt-in `map_qa` check: blocks the advance if a mandatory print-layout
  element is missing or the layer is tagged RESTRICTED/SENSITIVE, with the same
  `override=True` + mandatory-note bypass every other check in this state machine already uses.
- **Isochrone / access-band styling.** `calculate_service_area`'s `travel_cost` now accepts a
  list (e.g. `[15, 30, 60]`) as well as a single number — builds one combined,
  `travel_cost_band`-tagged polygon layer per facility instead of requiring N separate calls,
  auto-styled with a graduated renderer in the same call. The pre-existing single-value path is
  completely unchanged.
- **New behavioral rules.** Missing/suppressed/not-assessed values must never land in the same
  class as a real zero; establish purpose/audience/sensitivity before a finished cartographic
  deliverable (a conversational MapBrief, not a rigid pre-flight form); a raw-count choropleth
  must be normalized or have its denominator named explicitly; a RESTRICTED/SENSITIVE layer's
  tag must be surfaced in chat before an export touching it, not left only to the QA gate.

Full suite: 1398 tests, 0 failures. Live-verified against real QGIS 4.2.2 throughout, including
real rendered-pixel checks (a rule-based route-status layer, a multi-band isochrone map with
monotonically growing hull area per band) and a real blocking-gate test (a SENSITIVE-tagged
layer correctly blocked, then correctly advanced via override).

Explicitly out of scope this release (named, not dropped): bivariate choropleth, flow/OD maps, a
small-multiples/change-map compositor, uncertainty-*rendering* (confidence tags exist, drawing
them doesn't yet), a standard-deviation classification mode, a rigid structured MapBrief object,
and a minimum-count/k-anonymity suppression method for `sensitivity_tools.py`.

<a id="v1-7-1"></a>
## [1.7.1] — 2026-09-11 — Patch: portrait print-layout body/footer overlap fixed

- **`BUG-2026-09-11-1` fixed, same day it was found.** `create_print_layout`'s portrait
  orientation had a `body_h` sized for roughly one line of text, but `QgsLayoutItemLabel`
  doesn't clip overflowing content — any `body_text` longer than that silently overflowed
  downward into the standing disclaimer footer, exactly the multi-line "bullets/findings"
  usage the tool's own schema description encourages. Found live against real QGIS 4.2.2 via
  a real `QgsLayoutExporter` PNG export, visually inspected.
- Two changes in `agent/tools/layout_tools.py`: the disclaimer footer is now pinned to a fixed
  distance from the page bottom instead of being derived from `body_y+body_h`, so its position
  no longer depends on how much `body_text` overflows; new `_fit_text_to_box()` (pure Python,
  calibrated from a real live render) truncates `body_text` — by whole words, with an ellipsis
  — to what the box can actually hold before it's ever handed to the label. This is the real
  fix: since the label itself never clips, only bounding the text content guarantees no
  overflow regardless of exactly how generous the mm budget turns out to be.
- 6 new tests. Full suite 1339 tests (up from 1333), 0 failures, 7 skipped. Live-verified
  against real QGIS 4.2.2 with the exact repro that found the bug — the exported PNG now shows
  a cleanly truncated body paragraph and a fully legible, unobstructed disclaimer footer.
- Landscape untouched — already live-confirmed clean (2026-09-05); the same truncation guard
  isn't applied there yet, flagged as an optional defense-in-depth follow-up, not a known
  failure.

  **Correction, 2026-09-11, same day (documentation only, no code change — kept per this
  project's frozen-changelog convention rather than edited in place):** the line above is
  wrong. `_fit_text_to_box()`'s call site sits in the shared code path after the
  portrait/landscape `if`/`else` block closes, not inside the portrait-only branch, so it
  already ran for landscape too, using landscape's own `(col_w=95, body_h=78)` values, from the
  moment this release shipped — there was no gap to revisit. Verified live against real QGIS
  4.2.2 with an extreme 2774-character `body_text`: truncated cleanly with an ellipsis, footer
  fully legible and unobstructed. A regression test
  (`test_landscape_dimensions_also_truncate_an_extreme_body_text`) locks this in going forward.

<a id="v1-7-0"></a>
## [1.7.0] — 2026-09-11 — Security & Logistics: GDPR export, undo/rollback, sandbox Tier 2, network-aware routing

Scoped for a humanitarian org (UN/NGO) deployment/pilot with an Oct 15, 2026 target — data
protection and operational safety first, sandbox architecture second, logistics third. All four
workstreams are grounded in gaps this repo's own docs had already found and left open, not
invented from scratch: `docs/GDPR_COMPLIANCE_REVIEW.docx` (F6–F9),
`docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md` (points 8, 19, 20),
`docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md` (§2 items 2–3). Plan:
`~/.claude/plans/idempotent-popping-haven.md`.

- **GDPR F6–F9 closure.** `agent/memory.py`'s persistent project-memory writes (the sidecar
  `<project>_spatial_memory.sqlite` file and the embedded `QgsProject` custom property — both a
  second, easy-to-miss copy that travels with the project) are now gated behind the same
  opt-in, default-off settings-dialog toggle `chat_persistence.py` already uses for chat
  history; the in-memory cache stays always-on since the agent needs it within a session. New
  "My Data" export (`agent/data_export.py`, `export_stored_data` tool, and a button in the
  Notes/Memory panel) assembles project memory + global memory + chat history into one JSON
  document a user can save — closing F7/F8's "no consolidated view of what the agent knows
  about me" gap. F9 (erasure can't reach previously-distributed file copies) documented in
  `SECURITY.md` as an inherent property of local files, not a code defect.
- **Undo/rollback for a priority subset of MODIFY/DELETE tools.** New
  `agent/tools/_snapshot_registry.py` — an explicit, auditable `{tool_name: (snapshot_fn,
  restore_fn)}` registry, snapshotted before dispatch and consumed by `undo_last_operation` —
  covers `remove_layer`; `field_calculator`/`calculate_area`/`calculate_length`; the three
  `apply_*_style` tools; and `set_dataset_status`/`set_layer_sensitivity`/
  `set_layer_confidence`/`run_query`. A real bug caught live before shipping: the original
  design (hold a Python reference to a removed layer) is wrong —
  `QgsProject.removeMapLayer()` destroys the underlying C++ object immediately; fixed via
  `layer.clone()` taken before removal. `load_project` undo and MODIFY tools outside this
  priority subset are explicitly out of scope for this release, not silently dropped.
- **Sandbox Tier 2: a real allow-listed Processing path.** New
  `run_allowlisted_processing_algorithm(alg_id, params)`
  (`agent/tools/processing_allowlist_tools.py`) validates `alg_id` against a hard-coded,
  code-derived 36-id allow-list (grepped from every `processing.run()` call already trusted
  across this codebase) and calls `processing.run()` directly with a constrained params
  contract — never executes arbitrary code, so it adds no new sandbox-bypass surface.
  `execute_pyqgis_script`'s description now names this as the preferred path for "run one
  Processing algorithm" requests. The full tiered-allow-list rewrite (point 19's larger
  question) remains open; this closes one real, valuable slice of it.
- **Logistics: composite impedance + network-aware multi-stop routing.** New
  `build_composite_impedance_field` (`agent/tools/impedance_tools.py`) blends OSM
  `highway`-class baseline speed, `surface` penalty, an optional 0.0–1.0 `damage_field`
  (passability), and an optional DEM-derived endpoint-slope penalty into one `impedance_cost`
  field — feeds directly into `calculate_service_area`/`travel_time_matrix`'s existing
  `speed_field` parameter, no changes needed on either tool. `optimize_delivery_route` now
  builds a real road-network distance matrix (`native:shortestpathpointtopoint`'s `cost`
  output per ordered pair — `travel_time_matrix` was tried first but its destination-side
  matrix keys turned out unmappable back to stop names, confirmed live) before running its
  existing nearest-neighbor + 2-opt heuristic, so stop *order* is now road-network-aware, not
  just the final drawn route line. True VRP via OR-Tools and turn-cost/turn-penalty support
  remain real, deliberately unbuilt gaps (QGIS's native algorithms expose no turn-cost
  parameter at all).

All four workstreams live-verified against real QGIS 4.2.2. Full suite 1333 tests, 0 failures.
`docs/TOOLS_REFERENCE.md` regenerated (163 tools). See
`docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md` and `docs/MASTER_TASK_REGISTRY.md`
items 37–40 for full per-workstream detail.

## [1.6.0] — QA-gate infrastructure, GDPR remediation, live-verified QGIS 4.2 fixes

- **Repo reconciliation.** This checkout and `cartogen-ai-community` had diverged as two
  private clones of the same remote with mutually unpushed commits since a shared ancestor.
  Reconciled: fast-forward pulled the already-merged `origin/main`, resolved the remaining
  local working-tree conflicts (a duplicate `clear_global_notes()`, a duplicate `class
  ConnectionType` stub, two silently-shadowed duplicate test methods — all found and fixed,
  not just merged over), and reapplied the held "hosted account" feature's Qt6 enum fix
  through the project's canonical `qgis_compat.enum_member()` helper.
- **QA-gate / dataset-status infrastructure**, built from a 27-point QGIS-first production
  standard review (`docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`): a real
  `INGESTED → STAGED → VALIDATED → ANALYSIS_READY → CARTOGRAPHY_READY` state machine
  (`agent/dataset_status.py`) that layers/tools now advance through, with automated checks
  wired into the gate rather than left as documentation — geometry QA (duplicate/overlapping
  features, small-polygon threshold), P-code uniqueness/hierarchy validation
  (`agent/pcode_validation.py`, alias-list field matching for real COD-AB naming variance),
  and opt-in schema contracts (`agent/schema_contracts.py` + `agent/contracts/*.json` for
  health facilities and admin2 boundaries) that check field presence, type, and controlled
  vocabularies. A machine-readable provenance sidecar (`agent/provenance.py`,
  `write_provenance_sidecar`) assembles QGIS version, tool-lineage, and QA-gate history into
  a `.provenance.json` written beside the layer's own source file.
- **GDPR compliance remediation.** Closed finding F1 (global memory had no bulk erasure
  path) with `MemoryManager.clear_global_notes()` plus a confirm-gated "Clear Global Memory"
  UI control, and remediated four further HIGH findings (F2–F5) from the same review. The F1
  fix had been made independently on both diverged repo lines; the reconciliation above
  de-duplicated it rather than shipping two competing implementations.
- **Task register wired end to end.** The 791-task/35-section Humanitarian Mapping Task
  Register now drives the chat send path (matching, prompt enrichment, output-contract
  routing) instead of sitting beside it as reference data — see the `[1.4.4]` entry below for
  the register itself; this release is where dispatch actually runs through it.
- **QGIS 4.x/Qt6 enum-compatibility, generalized.** Replaced the ~15 site-by-site hand-rolled
  fixes with a shared runtime resolver (`agent/tools/_qgis_enum_compat.py`'s
  `resolve_qgis_enum`) that tries the QGIS 4.x scoped form first and falls back to the QGIS
  3.x flat form — applied across `styling_tools.py`, `raster_tools.py`, `task_runner.py`,
  `layout_tools.py`, `export_tools.py`, and `humanitarian_tools.py`. A live QGIS 4.2.2 smoke
  test (below) caught one class this pattern hadn't yet reached.
- **Live-verified critical fix: `QgsColorRampShaderItem` import crash.** Found by running a
  real headless PyQGIS session (QGIS 4.2.2's own Python, not the sandboxed no-QGIS suite,
  after the plugin's GUI proved undriveable in this deployment environment) against a
  purpose-built test dataset: `agent/tools/raster_tools.py`'s top-level import of
  `QgsColorRampShaderItem` raises `ImportError` on real QGIS 4.2.2 — the class moved to
  `QgsColorRampShader.ColorRampItem` — silently setting `QGIS_AVAILABLE = False` for the
  whole file and degrading all 11 raster tools (hillshade, slope, aspect, zonal statistics,
  clip, both classification tools, histogram equalization, mosaic, band composite,
  pan-sharpening) in any real live session. Invisible to the sandboxed suite by construction.
  Fixed with the same dual-form resolution pattern; re-verified live afterward, 14/14 smoke
  test categories passing including two real network calls. See `docs/BUG_TRACKER.md`
  BUG-2026-09-05-1.
- **Live-verified GUI: the print-layout disclaimer footer.** `[1.5.0]`'s dark-theme fix and
  BUG-2026-09-02-6's fabrication-safety footer had both shipped `fixed-unverified-pending-
  live-session`. Directly confirmed this cycle via a real chat-driven `create_print_layout`
  call in a live QGIS 4.2.2 session (Google Gemini (Hosted) provider): the standing
  disclaimer footer renders correctly and legibly in landscape orientation, alongside a real
  graduated-severity legend, scale bar, and north arrow. Portrait orientation's tighter fit
  remains unconfirmed.
- **Auth-system diagnostic.** From a live bug report (`authManager().isDisabled()` on a real
  QGIS 4.2 session): `CredentialManager.auth_system_status()`/
  `get_auth_system_diagnostic_message()` now surface the two real, documented root causes (a
  QGIS 3.40.4+ proxy-authcfg regression, or a missing QCA-OpenSSL backend) and their fixes
  directly in the existing plaintext-fallback warning, instead of an unexplained generic
  message.
- **Humanitarian incident coding.** `add_incident_point`/`add_point_layer` gained optional
  ACLED-style (`event_type`/`sub_event_type`) and IMSMA/IMAS-style (`hazard_type`/
  `contamination_status`) controlled-vocabulary fields alongside the existing freeform
  `severity`/`category` — advisory validation only, an unrecognized value returns a warning
  rather than rejecting the point.
- **Road-snapped delivery routes.** `optimize_delivery_route` accepts an optional
  `road_network_layer`; when given, it chains `native:shortestpathpointtopoint` across the
  computed stop order into a real road-snapped route line instead of leaving callers to draw
  a straight line through stops and present it as a route.
- **Sandbox hardening.** Closed 4 live bypasses of the `execute_pyqgis_script` safety sandbox
  found on re-review.
- **Release packaging.** `.bak`/`.orig`/`.rej` backup files no longer ship in the release ZIP;
  the ZIP's top-level folder name is now pinned rather than derived from the build directory
  (a prior build had shipped under a scratch-directory name, causing QGIS to install it
  alongside the real plugin instead of replacing it — see `docs/BUG_TRACKER.md`
  BUG-2026-08-21-6 lineage).

## [1.5.0] — adaptive self-learning + confirmed QGIS 4.2/Qt6 fixes

- **Adaptive self-learning system.** New `agent/learning.py` layers four
  mechanisms on top of the existing `SpatialMemoryManager` global-note store
  (no new storage plumbing): passive preference detection (scoped to
  connection-provider choice for this first pass, requiring 5+ samples and a
  70%+ dominant share before acting), correction learning (a text heuristic
  over the message right after a tool call — "that's wrong", "undo that",
  etc. — stored as a standing rule), usage-pattern counters (tool/provider
  frequency, surfaced to the model as context, never silently changing a UI
  default), and a new **🎓 Learned Preferences & Rules** row in the Tasks &
  Memory tab (dropdown + **🗑 Forget Selected**) so anything inferred is
  visible and removable. `get_formatted_memory_context()` now buckets global
  notes under labeled headings (Learned Preferences / Correction Rules /
  Usage Patterns / User Global Preferences) instead of one flat list. 17 new
  tests in `tests/test_learning.py`; the `agent.py` wiring and UI addition
  are unverified in a live QGIS session (same structural limitation as every
  other UI/agent-lifecycle change — see `docs/BUG_TRACKER.md` BUG-2026-09-02-5).
- **QGIS 4.2/Qt6 enum-scoping fixes**, discovered via three rounds of live
  crash reports during real QGIS 4.2 testing and shipped under the unchanged
  `1.4.4` version number without a release cut — recorded here retroactively.
  Fixed flat-vs-scoped enum access across `Qt`, `QScrollArea`,
  `QDialogButtonBox`, `QLineEdit`, and `QPalette` (dock panel open,
  scroll-area frames, dialog buttons, password fields, live theme palette
  extraction) — see `docs/BUG_TRACKER.md` BUG-2026-09-02-1 through -3 for the
  full per-symbol breakdown and verification status.
- **Dark-theme chat rendering fix.** `chat_formatting.py`'s `render_markdown()`
  was hardcoded to fixed light-theme colors for code blocks, inline code,
  tables, blockquotes, and `<hr>`, disconnected from the already
  theme-aware bubble colors — confirmed via a live screenshot showing
  near-invisible white-on-white table text in QGIS dark theme. Colors now
  thread through from the same theme-derived dict the chat bubbles already
  use. Two new system-prompt rules (40, 41) address related live feedback:
  default to creating a real map layer for mappable results instead of only
  describing them in chat, and never silently guess a year/date a tool
  parameter left unspecified. See BUG-2026-09-02-4.

## [1.4.4] — sector-guided mapping experience

### Humanitarian Mapping Task Register, wired end to end

The register (791 tasks across 35 sections) now drives the chat send path
instead of sitting beside it.

- **Every task declares what it takes in and what it puts out.** New
  `agent/file_io.py` models the media kinds the plugin can actually ingest --
  picture, PDF, TXT, Word, spreadsheet, vector, raster, QGIS project -- each
  with a real registered tool behind it, and the artifact each output contract
  leaves on disk (`.pdf`/`.png` for a layout, `.html` for a dashboard, `.csv`
  for an analysis, `.gpkg` for an export). Both fields are derived for all 791
  tasks by `tools/derive_task_io.py`; `tests/test_file_io.py` re-runs the
  derivation and fails if the committed register has drifted from it.
- **Attachments join the task.** A file attached in chat is classified, routed
  to the tool that can read it (a 3W spreadsheet to `load_3w_data`, a damage
  photo to `extract_features_from_imagery`, a sitrep to `extract_pdf_tables`),
  and carried into the next message rather than analysed as a side errand.
- **The prompt is shown before it is sent.** A new preview panel (on by
  default, Settings ▸ *Show the prompt and reasoning before sending*) displays
  the literal text that will be sent -- the user turn, plus the addendum added
  to the system prompt -- together with the reasoning: which task matched and
  how confidently, what will be delivered, which values were assumed, and what
  each attached file will be read as. No extra API call; it renders text that
  has already been composed locally.
- **Only genuinely unanswerable gaps interrupt.** Slots QGIS can answer (area
  of interest, from the open project) are answered; slots with a safe default
  are filled and stated in the preview; only hazard type, facility type and
  sector -- where a guess produces confidently wrong humanitarian output --
  stop and ask. That is ~10% of tasks rather than ~89%.
- **The answer is checked against the contract.** New `agent/output_router.py`
  compares the tools that actually ran against what the task promised. A
  dashboard task that ended in prose gets exactly one follow-up turn naming
  the missing renderer; the reason is written into the chat, and if it is still
  not produced the chat says so rather than describing an artifact that does
  not exist.
- Fixed five tasks that asked "which facility or service type?" about a
  statistical distribution (*Map population distribution*, *Map age and sex
  distribution*, and three others) because `distribution` also names a
  distribution point. Real distribution-point tasks keep the slot.
- **The click-through itself is now verified, not just the logic behind it.**
  New `tests/test_chat_widget_live.py` boots a real `QgsApplication`, builds
  the real dock and chat widgets, and drives them with `QTest.mouseClick` on
  the actual buttons -- the requirement panel, the prompt preview, and the
  output-contract follow-up, previously proven correct only at the level of
  pure-logic unit tests and static source inspection. It caught a real bug
  doing it: `_dispatch_message` had a stale `analysis is None` fallback that
  silently re-applied the register's enrichment -- and its output contract --
  after clicking "Send my wording only", the escape hatch for when the
  matched task is simply wrong. Fixed; the button now dispatches the user's
  own wording with no contract attached, as intended.

- Added sector-aware prompt guidance for humanitarian aid, engineering, urban planning, logistics, agriculture, environment, public health, disaster risk, utilities, transport, public safety, research, real estate, and defense/intelligence profiles.
- Priority rollout documented: humanitarian aid, engineering, urban planning, then logistics.
- Verified against the Community and private prompt-refiner suites.


## [1.4.3] — UI terminology and navigation polish

- Standardized the main tabs as **Chat**, **Tasks & Notes**, and **Help & Guide** in both plugin editions.
- Normalized commercial provider labels to Hosted/Local terminology.
- Clarified Settings connection naming and project-notes labels.
- Automated UI regression suites remain green: 691 private tests and 620 Community tests.


All notable changes to Cartogen AI are documented here, newest first. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/).

> **Repo note:** this file's history up through v1.3.0 was carried over verbatim
> from the old `qgis_ai_assistant` repo as part of a from-scratch copy/restructure
> into this new `cartogen-ai` repo — it is **not** a git history migration. Full
> commit history back to v0.2.0 remains available in the old repo
> (`C:\qgis_ai_assistant`) if ever needed.

## [1.4.2] — 2026-08-22

- **`ui/dock_widget.py` class split**, per `docs/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md`. The
  1,355-line `CartogenAiDockWidget` is now the outer dock (signals, header, tab wiring) with
  the Chat, Tasks & Memory, and Help tabs each extracted into their own `QWidget` class
  (`ChatTabWidget`, `TasksTabWidget`, `HelpTabWidget`), plus two small shared-code extractions
  (`dock_constants.py`, `theme.py`) needed to avoid a circular import. Code moved verbatim —
  no logic changes. Verified by constructing the dock offscreen against a real QGIS Python
  environment (`python-qgis-ltr.bat`, `QT_QPA_PLATFORM=offscreen`): all modules import
  cleanly, all 3 tabs are present, and every cross-tab signal connection fires correctly.
  **Not yet verified in a real interactive QGIS session** — run
  `docs/RELEASE_SMOKE_TEST.md` before relying on this in production.
- **Cartogen Cloud Connect Gateway wired in as a selectable provider** (not yet functional —
  no gateway is deployed anywhere). `CartogenClient` is now exported from `agent/providers`,
  registered in `agent.py`'s provider selection, and added to `ui/settings_dialog.py`'s
  provider dropdown (deliberately placed last, not default, until a real gateway exists).
  `providers/cartogen.py` gained a `list_models()` function for the Settings dialog's model
  picker. See `docs/PRO_TIER_BUILD_PLAN_2026-08-21.md` for what's still needed (gateway
  deployment, billing lifecycle, key-retrieval auth) before this tier has real value.
- **Fixed:** `tests/test_export_tools.py`'s `TestGenerateHtmlDashboardConnectivityNote` now
  skips when `folium` is absent instead of failing, matching every other optional-dependency
  guard in the suite.
- Added placeholder `README.md`s to the empty `cartogen-ai-pro/`/`cartogen-ai-enterprise/`
  sibling directories so they no longer read as "the private repo exists."

## [1.4.1] — 2026-08-21

Follow-up fixes after the `[1.4.0]` consolidation, from direct feedback that two problems slipped
through:

- **Living docs still named/linked like leftovers.** `QGIS_AI_Agent_Feature_List.md` and
  `QGIS_AI_Agent_PRD.md` renamed to `CARTOGEN_AI_FEATURE_LIST.md`/`CARTOGEN_AI_PRD.md` and fully
  rebranded. Unlike `CHANGELOG.md`'s past entries, these are living reference docs, not
  historical logs — renaming/translating them isn't a rewrite-history concern.
- **44 broken links.** Every `file:///c:/qgis_ai_assistant/...` absolute link (hardcoded to the
  old machine's path) converted to a relative link.
- Updated every live reference to the renamed files: `agent/scheduler.py`,
  `agent/tools/monitoring_tools.py`, `CLAUDE.md`, `CONTRIBUTING.md`, `plugin_upload.py`'s
  `EXCLUDE_FILES`, `docs/PRODUCT_TIERS.md`, `docs/HUMANITARIAN_GIS_FEATURE_REVIEW.md`,
  `docs/SAM_IMAGERY_EXTRACTION_SPEC.md`.
- Left the genuinely dated/historical docs untouched (this file's own past entries,
  `docs/STATUS_REVIEW_2026-08-20.md`, `docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md`) — they
  describe real past states, not leftover branding, per this project's frozen-doc convention.

**Added [docs/OPEN_CORE_REPO_STRATEGY.md](docs/OPEN_CORE_REPO_STRATEGY.md):** this repo stays the
single public Community codebase. Professional and Enterprise are decided (not yet built) to live
in a separate private repo that one-way-syncs from this one via GitHub Actions, distributed from
the project website with license-key gating. This resolves the licensing tension
`docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` flagged but didn't settle — Community stays
genuinely GPL v2/open in this repo; only the unbuilt Pro/Enterprise-only code would be
proprietary, in the other repo. Added `.github/workflows/sync-to-private.yml` as an inactive
scaffold (needs a real target repo before it can run).

## [1.4.0] — 2026-08-21

**Consolidated the dual-tree architecture into this single repo.** Previously,
`C:\qgis_ai_assistant` maintained two parallel plugin trees — a root source tree
(`CartogenAiCore`/`cartogen_ai_core`, renamed in `[1.3.0]` below) and a separately
distributed `Cartogen AI/cartogen_ai/` copy (`CartogenAi`/`cartogen_ai`) kept in
sync by `build_cartogen_ai.py`, so two QGIS plugin listings could exist side by
side. This repo (`C:\cartogen-ai`) is the single, consolidated result of copying
the root tree over and dropping the now-unnecessary `_core` suffix.

- Renamed: `CartogenAiCore` → `CartogenAi`, `cartogen_ai_core` → `cartogen_ai`,
  `CartogenAiCoreDockWidget`/`CartogenAiCoreSettingsDialog` → `CartogenAiDockWidget`/
  `CartogenAiSettingsDialog`, `cartogen_ai_core.py` → `cartogen_ai.py`
- **Another breaking change**, same caveat as `[1.3.0]`: the QSettings key prefix
  moved again, `cartogen_ai_core/...` → `cartogen_ai/...`
- `build_cartogen_ai.py` retired — no second tree left to sync into
- `plugin_upload.py` simplified for single-tree packaging (`PLUGIN_NAME = "cartogen_ai"`)
- Added Claude Code / GitHub scaffolding: `CLAUDE.md`, `.github/workflows/tests.yml`,
  issue templates, PR template
- The 3 planned editions (Community/Pro/Enterprise — see
  [docs/PRODUCT_TIERS.md](docs/PRODUCT_TIERS.md)) are reflected in documentation
  only; nothing in this codebase is tier-gated yet, per the project's existing
  honest-status convention (see `CONTRIBUTING.md`)
- `service/data/pgdata/` (a live Postgres data directory that had been committed
  to git in the old repo) was **not** carried over — it's runtime state, not
  source, and shouldn't have been tracked in the first place
- 691 tests, same known baseline, verified in this new tree post-copy

