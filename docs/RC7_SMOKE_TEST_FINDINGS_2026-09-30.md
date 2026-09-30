# v1.16.0-rc7 — Interactive smoke test: results, findings, decisions

**Dated snapshot, 2026-09-30.** Per `CONTRIBUTING.md` §2 this file is not edited after the fact; later
status changes go in `BUG_TRACKER.md` / GitHub issues, which link back here.

**What was tested.** The exact `cartogen_ai_v1.16.0-rc7.zip` (sha256
`3b6ad00d81f7fde6207e140bc8e5e14dc1e8c2f689b72245c9b636835222aabc`, built from `24404f2`), installed by an
operator on Windows into QGIS 4.2.2 (`default` profile, other plugins present), provider Google Gemini
(Hosted). Reference location: EPSG:3857 `4902068, 1799912` (= lon 44.03603, lat 15.95845), Yemen / Sanaa
area. Procedure: `RELEASE_SMOKE_CHECKLIST_rc7_YEMEN.md`. Evidence came from chat transcripts, screenshots,
QGIS Log Messages, Python-console diagnostics, and one attached CSV; **nothing was verified by the
assistant in a live QGIS session** — where a finding rests on reading source it says so.

**GitHub tracking:** umbrella issue #72; findings F01–F25 are issues #73–#97 in the same order
(F01 = #73 … F25 = #97; numbering checked against the issue list), all in `http-solution/cartogen-ai-qgis-plugin`.

## 1. Results

| Check | Result | Notes |
|---|---|---|
| Zip integrity / install | PASS | SHA-256 matched; `cartogen-ai 1.16.0-rc7` loaded from the intended path with `_replace_named_layer` present |
| R1 region offer | PASS | "Yemen (103 MB)" while the canvas was elsewhere. Typo reply and chip UI **not exercised** (silent smart-default path taken) |
| R2 download + load | PASS | 139,758 roads (footpaths excluded), 3,369 facilities, saved under `outputs\data\00_raw\osm`. Cancel test **not done** |
| R3 isolation worker | PASS with caveat | Correct CRS/layers, ~9–26 s task time, **no cmd window** — but see F01 |
| R3 sandbox block | PARTIAL | File not created. Validator blocks all tested scripts **offline**. Live tool call **not exercised** (model refused in text twice) |
| R4 service area / no pile-up | **FAIL** | F05, F07, F11 |
| R6 CSV export | PASS with findings | Right folder, 3,369 rows, Arabic intact. F13 |
| R7 dashboard | PASS with findings | Tiles load, cap disclosed in chat. F12 |
| R8 sensitivity tag | PASS | Silent on success (F15) |
| R8 gate blocks SENSITIVE read | PASS | Real read never ran |
| R8 gate override | **FAIL** | F02, F03 |
| `load_project` confirm + cancel | PASS | Plugin's own ✅/❌ messages; real card first |
| Data export ("Export stored data", GDPR access) | PASS | Valid JSON with project memory, global memory and chat history — but see F24/F25 |
| R5, R9, R10, R11, Part 3 (16 categories), Part 4 (§1.10 clean-profile/upgrade) | **NOT RUN** | |

## 2. Findings

Severity: high = wrong result / data loss / security-flow / dishonest output; medium = misleading or costly;
low = cosmetic. "Status" is as of this snapshot.

| ID | Sev | Finding | Status |
|---|---|---|---|
| F01 | high | Isolated `execute_pyqgis_script` renames the **live project** (`QgsProject.write()` = Save As) | Fixed `c2371bc`, unverified live |
| F02 | high | Cloud-data gate's confirmable preview is returned to the model but **never registered as a pending task** — override can never complete | Open, reproduced offline |
| F03 | high | Model **fabricates tool output** after a blocked/failed call; plan shows 0/1 done | Open, reproduced 3× |
| F04 | high | Origin point placed **~1.3 km off**: model converts EPSG:3857→4326 by hand | Open, reproduced 2× |
| F05 | high | Service-area re-run replaced a good road network with a **zero-length** layer, kept a stale hull, reported success | Open, cause unknown |
| F06 | high | Analysis outputs are temporary memory layers; chat says "saved to your project" | Open |
| F07 | med-high | Layer tree gets duplicate + orphaned nodes; basemap never moved; saved into the project file | Open, needs live reproduction |
| F08 | high (perf) | "Health facilities beyond one hour" agent task took **43 min 48 s** (`travel_time_matrix` 42 min 38 s = 97%); the operator estimates ~45 min including the download; no estimate shown beforehand; QGIS stayed responsive (operator-confirmed; Stop not tested) (known BUG-2026-09-25-2) | Open |
| F09 | medium | Population exposure (778,156) computed inside a **convex hull** — overstates reach | Open |
| F10 | medium | Router injects tools/deliverables at low confidence (0.42) and auto-nudges unrequested exports; ~1.86M tokens / 102 calls in one session | Open |
| F11 | medium | Highlight overlays never deleted (7 stuck `QgsHighlight` items; large orange block) | Open |
| F12 | medium | Dashboard: Temp file with random name, no full path in reply, no "sample" notice inside the file, poor first view | Open |
| F13 | med-low | CSV: no UTF-8 BOM, no coordinate columns, awkward file name | Open |
| F14 | low-med | Two confirmation prompts per action (model prose + real card); model-authored "Preview Ready" text | Open |
| F15 | low | Sensitivity dialog silent on success; raw LaTeX in chat; stray `)`; ~130 "no route" lines logged CRITICAL; router text "a analysis"; console `print()` noise; one invalid-JSON PromptRefiner response | Open |
| F16 | medium (unverified) | Generic replies ("yes", "ok", "sure", "go") can resolve a **stale pending destructive preview** (source reading only) | Open |
| F17 | medium | `qgis-live-tests` do not cover F01/F02/F07/F11 — none of these was caught by CI | Open |
| F18 | low-med | The **first call to every PUBLISH/DELETE tool fails** and is retried after `create_plan` (5 tools; usage counters record exactly half). Plan gate suspected, but the operator reports the setting at its default (OFF) | Open, cause not established |
| F19 | medium | `fetch_worldpop_population` downloaded the **whole-country** raster (41.81–54.54 °E, 12.11–19.00 °N, 141 s) for a ~77 × 71 km catchment | Open |
| F20 | low-med | Coordinates in a request are assumed to be in the **project CRS**; changing the project CRS silently changes their meaning (source reading + code comment) | Open, design risk |
| F21 | low-med | Field names / schema (and counts) of a SENSITIVE layer reach the cloud model (`get_layers` is not gated) | Open, policy decision |
| F22 | low | 103 MB downloaded **without asking** (rc7 "silent smart default") | Decision |
| F23 | medium | `store_project_memory` wrote the **wrong origin coordinates** (44.036028, 15.970136) into project memory during a plain service-area request — **confirmed** by the data export | Open |
| F24 | medium (unverified) | Memory dialog shows nothing although the export holds 3 project + 26 global entries | Open |
| F25 | low-med (unverified) | Exported chat history has only 8 messages; ~45 min of turns missing | Open |

### F01 — live project renamed by isolation
`script_isolation._build_scratch_project` called `QgsProject.instance().write(snapshot)`. After one isolated call
the title read `*live_snapshot`, `fileName()` was `.../Temp/cartogen_isolation_xxxx/live_snapshot.qgz`, and
`export_layer`/`export_to_csv` wrote into that temp folder, which `run_isolated_script` deletes. Fix: restore file
name and dirty flag in a `finally` (`_write_snapshot_of_live_project`, 5 tests, mutation-checked). **Verify in real QGIS.**

### F02 — egress preview is never registered
`_real_execute_tool` returns `egress_gate.preview_required(...)` *early*, before the block that registers the
pending confirmation task (`pending_tool`/`pending_args`), which sits after `func(**filtered_args)`. Reproduced offline
with the repo's own test fixture: tool not run, status `PREVIEW_REQUIRED`, **0 tasks registered, no confirmable task**.
Consequence: the deterministic "Confirm/Cancel" path (`_pending_confirmation_task`) finds nothing, the reply goes to
the model, and it improvises (F03). The gate still fails **safe** (the read never happens). Secondary hazard: the
model's own `create_plan` replaces the whole plan and would discard a registered gate task.

### F03 — fabricated tool output
Three times the assistant printed a five-row table for `Health Facilities (OSM, Yemen)` while the plan read 0/1 and
no read had run. None of the five `osm_id`s exist in the layer; classes `pharmacy` and `health_post` do not exist (real:
clinic/hospital/dentist/doctors); no shown name exists. Real first row: `450157266 | hospital | مستشفى أنا وطفلي التخصصي`.
This conflicts with the repo's rule (`CONTRIBUTING.md`) against implying something works when it was not verified.

### F04 — origin coordinate converted by the model
`add_point_layer(layer_name, points)` builds an EPSG:4326 memory layer with no CRS input and no transform tool exists.
Plugin used lat 15.970136; QGIS `QgsCoordinateTransform(3857→4326)` gives 15.958454 (measured in the QGIS console).

### F05 — re-run destroyed a good result
After run 2 the lines layer (`output_f72d39e3`) had 1 feature, `wkbType` 5, **length 0.0**, extent a single point (measured).
*Inferred, not measured:* the orphaned tree node `output_0d1f4267` (named `…_lines_0`, layer gone) is run 1's network; the hull
(`output_1417a1d0`, valid, 17 vertices, ≈3,155 km²) is run 1's because its id matches run 1's log line.
*New evidence from the logs:* run 1's graph build took ~4 s and the algorithm 4.9 s; run 2's took ~50 s (50,922 ms). In
`calculate_service_area` the network is clipped to the reachable area only when `reach_m` is known; it is set to `None`
(**no clipping**) when a `speed_field` is supplied whose maximum cannot be read (`strategy == "fastest" and speed_field and
_max_speed is None`). So run 2 very likely used different parameters (most likely a `speed_field`) — unverifiable because tool
arguments are not shown. Check: how many roads in `OSM Roads (Yemen)` have a non-null `maxspeed`. The tool
still reported success. `_replace_named_layer` removes the old layer before checking the new one is meaningful. Cause of the
empty result unknown (tool arguments are not visible in the UI by design). Also unexplained: 5.8 s (run 1) vs 52 s (run 2),
and differing catchment extents.

### F07 — layer tree
`layerTreeRoot().findLayers()` returned 10 nodes for 7 layers: two live layers listed twice and one orphan
(`layer() is None`). `_reorder_top_level_layers` moves nodes via `insertChildNode(0, node.clone())` + `removeChildNode(node)`
and skips a layer if `node.parent() is not root`. Mechanism not proven. The corrupted tree is written into the saved `.qgz`
and reappeared after `load_project`.

### F08 — timing breakdown (from the operator's Log Messages)
| Phase | Duration |
|---|---|
| Whole agent task (23:44:36 → 00:28:23) | 2,627,640 ms = **43 min 48 s** |
| `calculate_service_area` | 5.8 s |
| `travel_time_matrix`: graph build (23:45:18 → 23:51:08) | ≈ 5 min 50 s |
| `travel_time_matrix`: shortest paths to 3,369 facilities (→ 00:27:56) | ≈ 36 min 48 s |
| `travel_time_matrix` total | 2,558,156 ms = **42 min 38 s** |
| Download of the Yemen extract (103 MB), before the task | **not logged** (end-to-end wait is the task time plus this; the operator's own estimate is ~45 min) |
The matrix is 97% of the task. QGIS stayed responsive throughout (operator-confirmed); whether Stop works was not tested.
Recommendation D7 plus a pre-run time estimate and a working Stop for any job expected to exceed ~2 minutes.

### F18 — first call to PUBLISH/DELETE tools fails
`export_to_csv`, `export_layer`, `generate_html_dashboard`, `load_project` and `execute_pyqgis_script` — precisely the tools
`tool_operations.py` classifies PUBLISH/DELETE, i.e. the set `PlanValidationGate` blocks — each appeared as
*tool → Create plan → same tool*. The operator's data export shows `usage:tool:*` (successful calls only) at half the listed
calls: `export_to_csv` 2 of 4, `export_layer` 1 of 2, `generate_html_dashboard` 1 of 2. **Contradiction:** the gate is OFF by
default and the operator reports the setting untouched. Resolve by reading
`QgsSettings().value("cartogen_ai/plan_validation_gate_enabled")` in the QGIS console; if it is False/unset, another code path
rejects the first call. Either way it costs a call and a model round-trip per action, and `create_plan` replaces the whole plan
(interaction with F02).

### F19 — whole-country population raster
`YEM_population_2020` has extent 41.81–54.54 °E, 12.11–19.00 °N (all of Yemen) although only a ~3,000 km² catchment was
needed; fetch took 141.6 s. Clip to the catchment bounding box before downloading.

### F20 — coordinate CRS assumption
`local_data_loader.query_point_wgs84` reprojects the request's numbers *from the project's current CRS*. With the project set to
EPSG:4326, `4902068.0, 1799912.0` would be read as degrees. Recommend range checks and asking ("assuming EPSG:3857 — correct?").

### F21 — schema of a SENSITIVE layer
With Cloud data protection = Block and `Health Facilities` tagged SENSITIVE, the model still quoted its field names
(`fid, osm_id, fclass, name, source_geom`) and feature count. Probably intended (row contents are what the gate protects) but it
should be stated in `SECURITY.md` or gated.

### F22 — silent download
The 103 MB Yemen extract downloaded with no prompt ("runs in the background; press Stop to cancel"). This is the intended rc7
redesign (#67); consider a size threshold or metered-connection check.

### F23 — unrequested project memory (confirmed)
Data export, `project_memory`: `"service_area_analysis": "Computed 1-hour service area around 44.036028, 15.970136 using OSM Roads
(Yemen) and WorldPop 2020."` — written unprompted, containing coordinates, and the coordinates are the F04 error, which will now be fed
back into later prompts. `layout:*` entries hold layer ids/names only (of temporary memory layers, F06). Persistence to the `.qgz`/sidecar is
opt-in (default OFF); the operator should confirm the setting.

### F24 — Memory dialog empty
The operator saw nothing in **Memory**, while the same session's export lists 3 project and 26 global entries. Hypothesis: `MemoryDialog.refresh()`
returns silently when no agent/`memory_manager` exists yet (e.g. after a project load, before the first message). Unverified.

### F25 — chat-history export incomplete
`chat_history` in the export has 8 messages (01:24:05 → 02:15:06); the CSV export, at least five sensitive-layer attempts, the
`load_project` turns and everything earlier are absent; user and assistant messages share one timestamp. Cause unverified (history cap,
project identity change from F01, or agent rebuild after `load_project`).

### F11 — highlight leak
`flash_layer_extent` creates a `QgsHighlight` (orange 255,140,0,160) and only calls `hide()`. The console found 7 items in the
canvas scene; removing them made the orange block disappear.

## 3. Recommended decisions (behaviour changes — for best quality)

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | F04 coordinates | Add optional `crs` to `add_point_layer` and transform in code; **refuse** values outside ±180/±90 when no CRS is given ("looks projected — pass crs"); prompt rule "never convert coordinates by hand" | Deterministic, fails loudly, removes a whole error class |
| D2 | F02 | Register the pending task on the egress branch via one shared helper used by both paths; make the registered task survive a model `create_plan` | Pure bug fix; makes the documented override work |
| D3 | F03 | Defence in depth: (a) inject a system note whenever a tool returns blocked/preview/error — "this did not run; do not state or infer its results"; (b) post-turn guard: if the reply carries a data table but no data tool succeeded this turn, append a visible ⚠️ "No data was retrieved" and mark the plan; (c) prompt rule: never ask for confirmation in prose — the UI shows the card | One layer alone is insufficient against a hallucinating model |
| D4 | F05 | Validate before replacing (feature count > 0 **and** non-zero length/extent); keep the old layer on failure and return an explicit error; add opt-in local "show tool arguments" in Details (UI only, still not logged) | Never trade a good result for an empty one; makes failures diagnosable |
| D5 | F06 | When the project has a file path, persist analysis outputs to `data/20_processed/*.gpkg` and re-point the layers; otherwise warn; fix the "saved to your project" wording | 43 minutes of compute must not vanish on close |
| D6 | F07 | Do not guess-fix. Add real-QGIS tests to `qgis-live-tests` (tree node count == layer count; basemap ends at the bottom) and iterate in CI; then replace the clone-and-remove reorder with a verified atomic approach | Root cause unproven; CI has a real QGIS 4.2.2 |
| D7 | F08 | For "beyond N hours" questions, classify facilities from the **service-area result** (already ~5 s) instead of per-facility routing; keep `travel_time_matrix` for true matrices, with a cutoff and cooperative cancel | 43 min → seconds, same answer |
| D8 | F09 | Use a road-buffer or concave hull for exposure; label a convex hull as an upper bound | Humanitarian numbers must not silently overstate |
| D9 | F10 | Below 0.5 confidence send the raw message (no tool/deliverable injection); honour explicit tool names; never auto-nudge exports unless the deliverable was explicit; cap tool-loop iterations and prune context; report tokens per turn | Removes unrequested side effects and cost |
| D10 | F13 | Write UTF-8 **with BOM**; add lon/lat columns for point layers by default (opt-out); sanitize file names | Excel-correct Arabic, mappable output |
| D11 | F12 | Save into `<project>/outputs`, readable name, full path in reply, "showing N of M" inside the file, `fitBounds` + marker clustering | Complete and honest deliverable |
| D12 | F16 | Destructive confirms accept only explicit words ("confirm", "apply"); generic "yes" resolves router cards only; expire a pending preview on the next unrelated message | Prevents an unintended destructive action |

## 4. Proposed rc8 scope
**Safe / mechanical:** F01 (done), F02 (D2), F11, F12, F13, F15 wording and dialog message, F14 duplicate prose.
**Decision-dependent but recommended:** D1, D3, D4, D5, D8, D9, D12.
**Needs live reproduction first:** F07 (D6), the cause of F05, verification of F01.
**Performance:** D7.

## 5. Observed but not attributed to a defect
- QGIS message "No legend entries selected" at 23:40:34 has no matching tool call (probably an operator click).
- Chat-reported figures did not match the final layers: catchment area "~3,025 km²" vs ≈3,155 km² measured (0.2665 deg² hull);
  bounding box "43.684–44.403 °E, 15.658–16.297 °N" vs hull layer extent 43.72–44.25 °E, 15.61–16.33 °N. Supports F03/F05.
- Token use: 388,876 tokens after 10 calls, 890,037 after 34, 1,554,660 after 86, 1,856,989 after 102 calls (~48% served from cache).
- Chat history appears to be per project (panel reset after `load_project`).

## 6. Not covered by this run
R5 routing lines · R9 georeference · R10 design-state memory · R11 prompt caching · Part 3 (16 categories) ·
Part 4 clean-profile/upgrade gate (§1.10) · download cancel · typo/chip path · live sandbox tool call · Windows-only
observations on a single machine.
