# PLAN-063: Round-3 live results (2026-11-07 and 2026-11-08) read against the evidence

Status: in progress

## Goal
Turn the returned round-3 folder into a record the project can act on, as for round 2 (PLAN-061): what was seen working on the current build, what failed, what has no evidence. The tester's own verdicts are not available (see the log), so every verdict below is from the saved files.

## Scope
`results_round3.zip` (35.2 MB, sent in two parts, rejoined and tested: 2413 entries). Plugin build: the round-3 package's zip (the same file as `main` at 58d69b4, plugin 1.18.5), QGIS 4.2.3 on Windows 11, Gemini (hosted), and Claude Code CLI 2.1.314 for A3. Read for this plan: the A1 PDFs and `layout_check.json`; the W13 Help and About screenshots; the Connections screenshots; `steps.jsonl` of C1, E4, B3, B6 and D1; the B5 export; the per-request screenshot of D1; the tool-error list of every request. Not read closely: most routing rows beyond their tool lists, the layout rows E1 and E3, D2 to D4, the workflow rows.

## Acceptance
Every feature whose evidence was read is in `docs/LIVE_RESULTS.json` under run `2026-11-08-agent-windows-round3` with a note naming the files; the new defect has a master-list row and a dashboard line; nothing is closed without the owner; `python tools/live_results.py`, `python tools/ledger_guard.py` and `python tools/master_list.py check` pass.

## Guard tests
`tests/test_live_results.py`, `tests/test_dashboard_snapshot.py`, `tests/test_tracker_hygiene.py`, `tests/test_plans.py`.

## Rollback
Revert the commit: records under `docs/` only.

## Status log
- 2026-11-08: results read. **Folder:** 39 rows, 35 with a snap folder; V1-update, F1-mcp-size, W6-mcp-probe and W7-mcp-dialog have none; 218 evidence folders by the checker, 110 distinct requests; 37 of 41 log files empty (DEF-9 again). `tools/check_evidence.py`: layout check 11 of 11, 18 request groups matched on tools, one FAIL (B3 French, a false alarm: see below). **`4_RESULTS.csv` is not in the upload.** The tester's own F3 output says "39 rows, 0 left blank", so it exists; its verdicts (and the four missing rows' reasons) are unknown until it is sent.
- 2026-11-08: **seen fixed live (evidence read):** DEF-27 legend: `layout_check.json` L1-A4 and L1-A3 say measured true and fits true; the A4 page shows 4 layers of 14 classes in 4 columns at scale 0.7, the A3 page shows zones_6 in 4 columns, every entry whole, titles 'Legend (3 more layers not shown)' and '(6 more ...)'. DEF-28: the statistics table's checks are only `feature_count` pass. DEF-29: `generate_situation_dashboard` with the round-2 bbox succeeded and wrote its HTML. DEF-26: 20 requests delivered, the export holds 40 messages and `transcript_dropped` 0. W13: the Help line agrees with the About window (Qt 6.11.1, Python 3.12.14) and names the PyQt build 6.11.0, which explains round 2's console reading. V9 refusal at once, V4 animation tool, V5 profile, V6 `add_layout_chart` (tool level), F2's card says QGIS may pause while it downloads.
- 2026-11-08: **A3 and the Connections window.** Claude Code CLI 2.1.314 was found and signed in on a real Windows install; Check connection said 'Answered in 10.0 s (ok)'; Codex showed ready. The window is readable and grouped. A chat answered by the CLI was not evidenced; OWN-16 (a person's look) is still outstanding.
- 2026-11-08: **new defect DEF-30 (B6, evidence t1):** native:meshrasterize was called with PIXEL_SIZE 5 in EPSG:4326 for a tiny mesh; the plugin answered 'ran successfully with no new layer output' (the no-layers branch of `run_allowlisted_processing_algorithm`), and two more calls failed with 'writeBlock() called on read-only provider'. The second request (0.001) made `flood_depth_raster`. Fix not built.
- 2026-11-08: **retracted suspicion.** Round 2's agent reported that the reply claimed a zoom to one district while the canvas stayed at country extent. In round 3 the plugin's own per-request screenshot of D1 t13 shows the Yarim district zoomed with labels; the later snap D1.png shows the whole country because it was taken after other steps. `zoom_to_feature` worked in both rounds; this was a timing artefact of the snapshot, not a defect.
- 2026-11-08: **B3:** the Arabic request called `ingest_osm_features` and was answered in Arabic; the French request was answered in French with no tool call because the layer already existed, so the checker's FAIL is a false alarm of the row setup (the row asks for a fresh project). Overpass answered this time (39.7 s, 33 facilities).
- 2026-11-08: **model-side errors, not plugin faults:** E3's `execute_pyqgis_script` calls used PyQGIS names that do not exist (`hasFrame`, `unit`, `point`); D4's `population_access_gap` omitted `road_network_layer` and the plugin said so plainly; E1's `get_attributes` named a layer that had been renamed. **Observation for a person:** every A1 page has an empty white inset box at the map's top-left (a red dot appears in it on one page); the template adds an inset, so it is probably intended, and the scale bar on the single-point test data reads 500,000,000,000,000 km, a script artefact.
- 2026-11-08: **not read closely, so not recorded:** about 40 features covered by routing, data and layout rows have evidence in the folder that was not judged; the counts on the dashboard understate round 3 until the tester's `4_RESULTS.csv` arrives and the rows are read.
