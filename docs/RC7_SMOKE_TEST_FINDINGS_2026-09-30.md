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
| F08 | high (perf) | `travel_time_matrix` took **42.6 min** on Yemen (known BUG-2026-09-25-2) | Open |
| F09 | medium | Population exposure (778,156) computed inside a **convex hull** — overstates reach | Open |
| F10 | medium | Router injects tools/deliverables at low confidence (0.42) and auto-nudges unrequested exports; ~1.86M tokens / 102 calls in one session | Open |
| F11 | medium | Highlight overlays never deleted (7 stuck `QgsHighlight` items; large orange block) | Open |
| F12 | medium | Dashboard: Temp file with random name, no full path in reply, no "sample" notice inside the file, poor first view | Open |
| F13 | med-low | CSV: no UTF-8 BOM, no coordinate columns, awkward file name | Open |
| F14 | low-med | Two confirmation prompts per action (model prose + real card); model-authored "Preview Ready" text | Open |
| F15 | low | Sensitivity dialog silent on success; raw LaTeX in chat; stray `)`; ~130 "no route" lines logged CRITICAL | Open |
| F16 | medium (unverified) | Generic replies ("yes", "ok", "sure", "go") can resolve a **stale pending destructive preview** (source reading only) | Open |
| F17 | medium | `qgis-live-tests` do not cover F01/F02/F07/F11 — none of these was caught by CI | Open |

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
After run 2 the lines layer (`output_f72d39e3`) had 1 feature, `wkbType` 5, **length 0.0**, extent a single point; run 1's
network layer (`output_0d1f4267`) was removed; the hull (`output_1417a1d0`, valid, 17 vertices) was run 1's. The tool
still reported success. `_replace_named_layer` removes the old layer before checking the new one is meaningful. Cause of the
empty result unknown (tool arguments are not visible in the UI by design). Also unexplained: 5.8 s (run 1) vs 52 s (run 2),
and differing catchment extents.

### F07 — layer tree
`layerTreeRoot().findLayers()` returned 10 nodes for 7 layers: two live layers listed twice and one orphan
(`layer() is None`). `_reorder_top_level_layers` moves nodes via `insertChildNode(0, node.clone())` + `removeChildNode(node)`
and skips a layer if `node.parent() is not root`. Mechanism not proven. The corrupted tree is written into the saved `.qgz`
and reappeared after `load_project`.

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

## 5. Not covered by this run
R5 routing lines · R9 georeference · R10 design-state memory · R11 prompt caching · Part 3 (16 categories) ·
Part 4 clean-profile/upgrade gate (§1.10) · download cancel · typo/chip path · live sandbox tool call · Windows-only
observations on a single machine.
