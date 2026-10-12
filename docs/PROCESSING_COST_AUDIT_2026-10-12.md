# Processing-cost audit: what freezes QGIS, and what was done (2026-10-12)

Owner report: several freezes and hangs; wanted better queue and memory management, and big processing split into smaller functions.

**What this is and is not.** A code audit plus fixes, built without a QGIS install or real data: no run time below is a measurement of QGIS
on a real project, except the 2-opt figures, which are pure Python timings (section 3). Everything else is a count of code patterns or
reasoning from the code. The fixes are tested offline, plus CI's QGIS job; none is hand-tested. `tools/audit_processing_cost.py` re-runs the
ranking at any time (`python tools/audit_processing_cost.py --markdown`).

## 1. Why QGIS freezes: the structure

- Every ordinary tool runs **on QGIS's GUI thread**: the agent turn runs on a worker, but each tool call is marshalled to the GUI thread
  (`ToolDispatcher`, a blocking queued connection), because `QgsVectorLayer`/`QgsFeature`/`QgsProject` are only safe there. A tool that
  loops for 20 seconds therefore blocks the window for 20 seconds: "Not Responding", no repaint, and Stop cannot be heard.
- Before this change `QCoreApplication.processEvents` was called **nowhere** in the plugin. Only Processing algorithms run through
  `_background_processing.run_algorithm` (a nested event loop around a worker task) and the two image-model steps through `run_callable`
  were responsive.
- 210 tools are registered. Before this change there were about 90 `getFeatures()` call sites in the tool modules (the largest: `logistics_tools`
  23, `analysis_tools` 9, `raster_tools` 7, `vector_tools` 5), none of them yielding.

## 2. Findings, worst first

| # | Finding | Evidence | Status |
|---|---|---|---|
| 1 | Loops over features, pairs and pixels never yield to Qt, so any long loop freezes the window and ignores Stop | `processEvents` appears nowhere; about 90 `getFeatures()` sites across the tool modules | **Fixed (sliced)**: `tools/_chunked.py`; 62 of those sites (the loops in `logistics`, `analysis`, `raster`, `vector`, `task_grid`, `allocation`, `barrier`, `sampling`, `survey`, `mcda`, `impedance`, `corridor`, `critical_link`, `jiaf_*` and `_network_closure`) now go through `_ck.features(...)`, which hands control to Qt every ~50 ms, reports progress every 3 s and raises `AnalysisCancelledError` on Stop. A Stop inside an edit command rolls the edit back (`edit_command` already did). |
| 2 | `geocode_batch` (up to 25 lookups with a 1 s pause each, ~25 s) ran on the GUI thread | It was missing from `NETWORK_ONLY_TOOLS`, though it touches no QGIS object | **Fixed**: added; Stop ends the batch between lookups. A test now fails if any network-calling tool is on neither `NETWORK_ONLY_TOOLS` nor `TWO_PHASE_TOOLS` |
| 3 | `optimal_hub_siting` / `location_allocation`: the candidates x demand distance matrix (up to 2,000,000 ellipsoidal measurements) and the pure-Python ranking / greedy p-median ran in one unbroken stretch | `logistics_tools.py` | **Fixed**: matrix built in slices (`_fill_candidate_distances`); ranking and greedy selection run through `run_callable` (worker thread, plain numbers only) |
| 4 | `optimize_delivery_route`: 2-opt re-measured two whole tours per candidate move (O(n) each) and was capped at 2000 moves, so it was both slow and weak | `_two_opt` | **Fixed**: symmetric matrices judge a move by its 4 changed edges (O(1)); asymmetric ones (one-way streets) keep the exact old path. See section 3. The route ordering runs through `run_callable` |
| 5 | `score_route_incident_risk`: features were merged one at a time (`acc = acc.combine(g)`, which re-unions the growing result each time, so cost grows with the square of the feature count), and each incident was tested against the big buffer with `intersects()` | `logistics_tools.py` | **Fixed**: one `unaryUnion`; GEOS prepared geometry for the incident test. Not timed (needs QGIS) |
| 6 | Recurring workflows (`scheduler.py`) could fire while another tick or a chat request was running; now that loops yield to Qt, a tick could re-enter | no overlap guard | **Fixed**: one heavy job at a time. A tick that would overlap is skipped and counted (`skipped` in `list_active`), and does not use up `max_runs`; `cancel_signal.request_active()` tells the scheduler a chat request is running (a request older than 30 minutes is ignored so a missing `end()` cannot silence schedules forever) |
| 7 | Raster classification held the whole raster in memory | audit A15 / #222 | **Fixed earlier today (PR #280)**: block-wise two-pass k-means |
| 8 | Chat window: every message is appended as a nested HTML table to one `QTextBrowser`; Qt lays tables out slowly and the cost grows with the number of messages in a long session | `chat_tab_widget.py` (`chat_browser.append(html)`); not measured | **Open**: needs a design decision (render only the latest N messages and keep the rest in the saved transcript). Trimming blocks from the top would cut tables mid-way, so it is not a one-line fix |
| 9 | Python-implemented Processing algorithms (`gdal:*`, `qgis:*`, `script:*`) stay on the GUI thread because running them on a worker crashed the QGIS 4.2.2 live job (PR #249/#251) | `_background_processing.is_thread_safe_algorithm` | **Open**: a known safety trade; a cause for the crash has not been found |
| 10 | Pure-Python compute after the QGIS read still runs on the GUI thread in a few tools (`calculate_allocation_envelope`, `compute_jiaf_patterns`, sampling and survey helpers) | audit ranking below | **Open**: the remaining 30 `getFeatures()` sites (styling, export, hazard and small helper modules, and non-loop uses such as spatial-index builds) are not sliced yet. Same recipe as finding 3 (read with QGIS, compute in `run_callable`), tool by tool |
| 11 | Agent history and tool results | `MAX_HISTORY_MESSAGES` 10, `MAX_FULL_TOOL_RESULTS_PER_TURN` 8, mid-turn compaction, per-turn token budget, loop guard | **Already bounded; no change** |

## 3. Measured: the 2-opt route improvement (pure Python, random stops, one core)

| Stops | Nearest-neighbour tour | Old 2-opt (2000-move cap) | New 2-opt (O(1) moves) |
|---:|---:|---:|---:|
| 30 | 547.5 | 523.8 in 0.01 s | 485.9 in 0.00 s |
| 100 | 968.2 | 931.0 in 0.03 s | 828.7 in 0.00 s |
| 200 | 1275.5 | 1261.4 in 0.06 s | 1094.3 in 0.02 s |

The old version was cheap only because its cap stopped it after a tenth of one pass: at 200 stops it improved the tour by 1.1 percent, the
new one by 14.2 percent, faster. (Tour lengths are in the units of the random coordinates.) So this was a quality fix as well as a speed fix.

## 4. How the work is now split

- **GUI-thread work that touches QGIS objects** is cut into slices of about 50 ms (`_chunked.Yielder` / `features` / `chunked`): Qt gets a
  turn, Stop is checked, progress is reported. This cannot move to a worker, so it is sliced.
- **Pure-data work** (numbers, lists, numpy) goes to `run_callable`, a worker thread behind a nested event loop with Stop.
- **Native Processing algorithms** keep `run_algorithm` (unchanged).
- **Large rasters** are read and written in row blocks (`raster_numpy.classify_in_blocks`).
- **Work budgets** are stated in one place with one wording (`_chunked.ensure_within`); the existing per-tool limits (for example the
  2,000,000 hub-siting pairs) are unchanged, and their message no longer needs to say the interface will freeze.
- **Queue:** one heavy job at a time for scheduled ticks (finding 6). Several jobs pasted into one chat message are already run one after
  another (`job_queue.py`); a chat request is not queued behind a tick, the tick yields to it.

## 5. Static ranking (top 30 of 210 tools; a risk score, not a timing)

Columns: `loops` = deepest nesting of feature/pixel loops (own body plus same-module helpers), `get_features` = getFeatures calls,
`processing_run` = synchronous `processing.run` calls, `background` = goes through the background runner, `cancel` = polls Stop, `caps` =
mentions a limit. The score adds cost patterns and subtracts guards. After this change the loops are sliced, so the first columns
overstate the risk for tools that now use `_ck.features`; the audit script does not yet credit that.

| score | tool | module | loops | get_features | processing_run | raster_reads | network | sleep | spatial_index | background | cancel | caps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 9 | compute_jiaf_patterns | jiaf_patterns | 2 | 0 | 0 | 0 |  | 0 |  |  |  |  |
| 9 | optimize_delivery_route | logistics_tools | 2 | 1 | 1 | 0 |  | 0 |  | yes |  |  |
| 9 | population_access_gap | logistics_tools | 1 | 1 | 1 | 0 |  | 0 |  |  |  |  |
| 7 | calculate_allocation_envelope | allocation_tools | 2 | 0 | 0 | 0 |  | 0 |  |  |  | yes |
| 7 | estimate_population_exposure | raster_tools | 1 | 2 | 0 | 0 |  | 0 | yes |  |  |  |
| 6 | fetch_gdacs_disaster_alerts | hazard_monitoring_tools | 1 | 0 | 0 | 0 | yes | 0 |  |  |  |  |
| 6 | fetch_worldpop_population | humanitarian_tools | 1 | 0 | 0 | 0 | yes | 0 |  |  |  |  |
| 6 | ingest_osm_features | humanitarian_tools | 1 | 0 | 0 | 0 | yes | 0 |  |  |  |  |
| 5 | add_point_layer | humanitarian_tools | 1 | 1 | 0 | 0 |  | 0 |  |  |  |  |
| 5 | analyze_incident_trend | analysis_tools | 1 | 2 | 0 | 0 |  | 0 | yes |  |  | yes |
| 5 | apply_graduated_style | styling_tools | 1 | 1 | 0 | 0 |  | 0 |  |  |  |  |
| 5 | apply_network_barriers | barrier_tools | 1 | 1 | 0 | 0 |  | 0 | yes |  |  |  |
| 5 | calculate_service_area | logistics_tools | 1 | 1 | 0 | 0 |  | 0 |  |  |  |  |
| 5 | classify_facilities_by_access | logistics_tools | 1 | 1 | 0 | 0 |  | 0 |  |  |  |  |
| 5 | diagnose_topology | vector_tools | 1 | 1 | 0 | 0 |  | 0 | yes |  |  |  |
| 5 | elevation_profile | raster_tools | 1 | 1 | 0 | 0 |  | 0 |  |  |  |  |
| 5 | generate_map_product_qa_checklist | qa_checklist_tools | 1 | 1 | 0 | 0 |  | 0 |  |  |  |  |
| 5 | generate_mapping_task_grid | task_grid_tools | 1 | 0 | 1 | 0 |  | 0 | yes |  |  | yes |
| 5 | obfuscate_sensitive_points | vector_tools | 1 | 1 | 0 | 0 |  | 0 | yes |  |  |  |
| 5 | recommend_visualization_method | cartographic_advisory_tools | 1 | 1 | 0 | 0 |  | 0 |  |  |  |  |
| 5 | tidy_project_layers | project_tidy_tools | 1 | 1 | 0 | 0 |  | 0 |  |  |  |  |
| 4 | apply_raster_stretch | raster_tools | 1 | 0 | 0 | 1 |  | 0 |  |  |  | yes |
| 4 | buffer_analysis | vector_tools | 0 | 0 | 1 | 0 |  | 0 |  |  |  |  |
| 4 | centroid | vector_tools | 0 | 0 | 1 | 0 |  | 0 |  |  |  |  |
| 4 | clip_layer | vector_tools | 0 | 0 | 1 | 0 |  | 0 |  |  |  |  |
| 4 | convert_to_singlepart | vector_tools | 0 | 0 | 1 | 0 |  | 0 |  |  |  |  |
| 4 | convex_hull | vector_tools | 0 | 0 | 1 | 0 |  | 0 |  |  |  |  |
| 4 | delaunay_triangulation | vector_tools | 0 | 0 | 1 | 0 |  | 0 |  |  |  |  |
| 4 | difference_layers | vector_tools | 0 | 0 | 1 | 0 |  | 0 |  |  |  |  |
| 4 | dissolve_layer | vector_tools | 0 | 0 | 1 | 0 |  | 0 |  |  |  |  |


## 6. What this does not fix

- A single very long GEOS or Processing call (one `buffer`, one `unaryUnion` of millions of vertices) is still one C++ call: nothing in
  Python can interrupt it. Splitting those means splitting the input (tile the layer), which is a design change.
- Time per slice depends on the machine; 50 ms is a default, not a measurement.
- Nothing here was run against a large real project. The first real test is the full live-test pack (`docs/FULL_LIVE_TEST_rc34.md`) with a
  few large layers and the QGIS task manager open, watching that the window keeps repainting and Stop ends a long tool within a second.
