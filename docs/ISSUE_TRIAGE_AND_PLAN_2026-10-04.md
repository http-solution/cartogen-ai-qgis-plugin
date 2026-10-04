# Open issue triage and plan (2026-10-04)

Snapshot of the 62 open GitHub issues (all issues are open; none of the audit issues has been closed), sorted into what is already fixed in code and waiting for a hand check, what can still be solved here, and what is limited by something outside this sandbox. A dated snapshot: supersede it with a new doc rather than editing it.

**How to read this.** "Fixed in code" means a change is merged and covered by offline tests and, where the table says so, by the QGIS 4.2.2 live tests in CI -- **not** that it works in a desktop session. This sandbox has no QGIS, so every QGIS-side change is written blind and its first real execution is the CI run on the pull request. Sizes are S / M / L by amount of code and risk, not time. The audit findings were confirmed statically against `main` (reading the code), not re-run, as the issues themselves say.

## 1. Fixed in code, waiting for your hand verification (no more code work unless the check fails)

| Issues | What | Verification so far |
|---|---|---|
| #137-#150 (audit P1) | Processing code execution, snapshot threading, hub siting / service-area crashes, SI units, CRS mixing, owned edit sessions, checked writes, script-isolation adoption and reconciliation, project-bound turns, bounding-box nearest neighbour, egress gate and lineage inputs | Offline tests + CI live tests where a live test exists (see each issue comment). #138 (main-thread boundary) and #147 (project switch) have offline fakes only |
| #151 (audit P1, PostGIS) | Read-only SQL fails closed, real query layer | Offline fakes only. Needs a real PostGIS to finish (see 3) |
| #119, #121, #122, #123, #124, #125, #127, #128, #129 (part), #130, #131, #132 | rc11-smoke fixes shipped in rc12 | CI live tests; hand check is on the rc12 plan doc |
| #75 | Unsupported-claims footnote | Offline tests; live check is section C of `docs/RC12_LIVE_TEST_AND_AUDIT_PLAN_2026-10-04.md` |
| #79, #80, #81, #84, #86, #87, #88, #92, #93, #94, #95, #97, #91, #72, #89 | rc7 / rc10 / rc11 smoke findings, fixed or partly fixed in rc8-rc12 | Each issue's last comment says which part is verified. Most are waiting on a hand test, not on code |

## 2. Still open and solvable here

Order within each batch is the proposed build order. "Blind" means the QGIS-side part cannot be run here; it is covered by a live test written without QGIS and first run in CI.

### Batch 1 -- small, low risk (offline-testable)
| Issue | Problem (confirmed) | Fix | Size | Limitation |
|---|---|---|---|---|
| #165 audit F29 | The print-layout reading guide says within-reach facilities are **green**; `routing_style.ACCESS_STYLES` makes them blue (confirmed in `layout_style.py:71`) | Generate the guide text from `ACCESS_STYLES`; add a test that fails if they diverge. North-arrow rotation, attribution and legend-by-role are separate, larger parts | S for the text; M for the rest | Rotation / attribution need a live layout test (blind) |
| #158 audit F22 | `results_store.new_table_name` has one-second resolution (confirmed): two persists of one stem in a second overwrite | Add a sequence / random suffix; test two persists in the same second | S | None |
| #166 audit F30 | Wheel package data lists only `*.md` for `cartogen_ai.core` (confirmed in `pyproject.toml`), so the task register and schema contracts are missing from a wheel | Declare the JSON as package data; build a wheel and check its contents in a test | S | `requests` as a wheel dependency is a design choice that is yours (the QGIS zip is the product) |
| #168 audit F32 | `requires-python`, ruff and mypy targets say 3.9; the CI test job runs Python 3.11 and the QGIS 4.2 image is newer | Align the targets with the real floor and run ruff / mypy | S | **Decision needed:** which floor. I would use 3.11, the version the test job already proves |
| #120 part 2 | Scratch origin layers are lost on close; the reply should say they are temporary | Prompt wording + the existing `tidy_project_layers` pointer | S | Wording only; the layers are intentionally scratch |
| #129 (rest) | A visible plain service-area polygon is not in the legend | Add it to the access-map legend selection | S-M | Blind (layout / legend) |

### Batch 2 -- data correctness
| Issue | Problem | Fix | Size | Limitation |
|---|---|---|---|---|
| #159 audit F23 | Hub candidates, matrix origins, route stops and population totals are keyed by the first attribute; duplicate or NULL names overwrite each other and totals undercount | Key by feature id, keep the label separately; tests with duplicate-name and NULL fixtures | M (5 call sites) | Mock-based offline tests; live fixture for population |
| #160 audit F24 | Zonal statistics write fields into the user's layer, a repeated run reads a stale field, overlapping polygons are summed twice | Run on a detached copy, resolve the real output field, report the overlap rule | M | Blind (QgsZonalStatistics). **Decision:** union total vs per-zone for overlaps |
| #161 audit F25 | Point counts use `contains` (boundary points lost) and overlaps are resolved by iteration order | Deterministic documented rule, report unmatched / ambiguous counts | S-M | **Decision (policy):** how to allocate a boundary point and an overlap. Proposal: `intersects`, give to the unit with the lowest id, report ambiguous counts |
| #153 audit F17 | Raster tools compare only CRS auth ids, not extent / resolution / origin | Compare full CRS equivalence and geotransform; reject mismatches with a clear message (aligning is a second step) | M | Blind; GDAL fixtures can be created in the live test |
| #154 audit F18 | Elevation / slope sampling and the imagery min-area filter use raw CRS units | Transform sample points into the DEM CRS; metric areas / lengths | M | Blind; a foot-unit fixture needs care |
| #155 audit F19 (and my H1) | `damage_field = 0` and H1 "block" are a 0.1 km/h speed, so a route can still cross a "closed" road | Treat blocked as a separate flag and drop those edges before routing | M | Cross-tool change to three routing tools; blind. Changes behaviour users may rely on, so I would flag it in the release notes |

### Batch 3 -- native Processing provider and the algorithm registry
| Issue | Problem | Fix | Size | Limitation |
|---|---|---|---|---|
| #156 audit F20 | Service-area algorithm: seconds-vs-hours label, facility points not transformed, sink schema | Derive the schema, transform points, set units explicitly | M | Blind; a 3,600 s fixture on a known-speed road |
| #157 audit F21 | Sink creation / `addFeature` unchecked, no cancellation or size limit | Raise `QgsProcessingException`, check feedback in the loops, cap or stream | M | Blind |
| #162 audit F26 | Allowlist / tools reference algorithm ids the 4.2.2 registry may not contain | **Step 1:** a live test that resolves every referenced id and prints the missing ones. **Step 2:** fix or remove them from that output | S then M | I cannot query a registry here; step 2 depends on the CI output of step 1. SAGA ids are host-dependent |
| #163 audit F27 | Generic Processing tool harvests only `OUTPUT`, accepts unknown parameters | Per-algorithm parameter and output definitions | M-L | Depends on #162's inventory |

### Batch 4 -- deliverables and lifecycle
| Issue | Problem | Fix | Size | Limitation |
|---|---|---|---|---|
| #164 audit F28 | A same-name layout is deleted before the new one is built; atlas file names can collide | Build and export privately, swap on success; unique atlas names | M | Blind (layouts) |
| #167 audit F31 | No `removeTranslator`, isolation worker not stopped on unload, namespace bootstrap evicts every `cartogen_ai.*` module | Add the translator removal and worker shutdown; narrow the eviction | M | Blind and the riskiest edit to plugin startup: needs a hand reload test |

### Batch 5 -- hard
| Issue | Problem | Why hard |
|---|---|---|
| #152 audit F16 | Above 200 destinations `travel_time_matrix` reads each cost from the nearest graph vertex, which can be a different edge | Correct fix is direction-aware partial-edge costs, i.e. a routing change. A cheaper partial step: raise the threshold or disclose the error bound in the result. The approximation is already stated in the result note |

## 3. Limited by something outside this sandbox

| Issue | Limit | What would unblock it |
|---|---|---|
| #151 PostGIS | No PostGIS server here; the result layer still uses its own connection, so a read-only database role is the real guarantee | A PostGIS test database (or your confirmation of the role-based approach) |
| #138, #147 | Thread affinity under a real `AgentQgsTask` and a project switch mid-request cannot be exercised here | Your hand test (section A/B of the rc12 plan) |
| All QGIS-side work | No QGIS here: first execution is CI; looks are never seen on a canvas | Hand verification |
| #91 WorldPop | worldpop.org does not support HTTP Range, so a partial download is impossible | Nothing on our side; the clip happens after the download |
| #93 | Field names and counts of a SENSITIVE layer reach the cloud model | A policy choice (what to hide), not a defect |
| #97 | Export / toggle / delete of the chat transcript | Your hand test |
| #169 tracking | Closes when the 32 audit issues close | Hand verification of the P1s and the work above |

## 4. Plan

1. **Decisions I need from you (all small):** the Python floor (#168, proposal 3.11); the boundary-point and overlap rule (#161, proposal above); the overlap rule for zonal totals (#160); whether a blocked road should be removed from the network (#155, changes behaviour); whether the wheel should declare `requests` (#166, proposal: no).
2. **Batch 1**, one pull request, then Batch 2, 3, 4 each as its own pull request, so a CI failure in one cannot hold up the others. Each pull request: offline tests, a live test where the code touches QGIS, an honest note in each issue ("fixed in code, CI-verified / blind, not hand-verified"). No audit issue gets closed by me; closing needs your hand check.
3. **#162 step 1 goes first inside Batch 3** because its output decides the size of #163.
4. **Batch 5 (#152)** only after the rest, as a disclosure change unless you want the routing rewrite.
5. After Batches 1-4, rebuild rc12 once, so you test one build that has everything.

What does not get done by code, however long I work: hand verification (sections 1 and 3).


---

## 5. Decisions received (2026-10-04) and the complete fix plan

### 5.1 Decisions

| # | Issue | Decision | What changes in the plan |
|---|---|---|---|
| 1 | #168 | Python floor **3.10** (follows QGIS's requirement) | `requires-python >=3.10`, ruff `py310`, mypy 3.10, and the CI `test` job gains a Python 3.10 entry so the floor is proven, not declared. Anything that needs 3.11+ is rewritten |
| 2 | #161 | Boundary point / overlap: **`intersects`, lowest feature id wins, ambiguous counts reported** | Implemented as proposed; result gains `boundary_points`, `ambiguous_points`, `unmatched_points` |
| 3 | #160 | Overlapping zones: **per zone** | Each zone reports its own total; the result states that zone totals can add up to more than the union; no silent de-duplication |
| 4 | #155 | A blocked road is **removed from the network entirely** | A shared "routable network" step drops blocked segments before every routing tool; a fully blocked network is an explicit error. Behaviour change, goes in the release notes |
| 5 | #166 | The wheel does **not** declare `requests` | JSON resources are packaged; the missing dependency stays a documented design choice |
| 6 | #152 | **Full fix**: direction-aware partial-edge costs | Moved from "hard / maybe disclose" into the plan as work package 5 |
| 7 | #91 | WorldPop: download the **full file, use only what is needed** | Already how the tool behaves when a range read is refused (download once, keep in `data/00_raw/worldpop`, clip locally, load only the clipped area). Plan: say so up front in the confirmation text, test the cache path, then leave to your hand check |
| 8 | #93 | Schema exposure is acceptable **if declared and the user is told**, with no sensitive values exposed | The rc8 "model view" already withholds values for a protected layer. Plan: audit exactly what it sends, write it into `SECURITY.md`, the Settings help and the chat (a notice when a protected layer is present and a cloud model is active). Layer names remain visible by design and the notice says so |

### 5.2 Work packages

Each package is its own branch and pull request, cut from `main`, so one CI failure cannot block the others. Every package: offline tests, a live test where QGIS code is touched (written blind, first run in CI), an honest status comment on each issue it touches. **No audit issue is closed by me; closing follows your hand check.**

**WP1 -- quick corrections** (#165, #158, #166, #168, #120, #129)
- #165: build the reading-guide colour wording from `routing_style.ACCESS_STYLES`; a test fails if they diverge. Then the north arrow follows map rotation, attribution is derived from layer source metadata, the legend filter works by role instead of provider type, and manual class breaks are validated (these four are the live-test-heavy part of F29).
- #158: sequence suffix on `new_table_name`; two persists in one second keep both.
- #166: package the task register and schema contracts as package data; a test builds a wheel and lists its contents.
- #168: floor 3.10 as above, plus the CI 3.10 job.
- #120 part 2: wording that scratch layers are temporary, pointing to `tidy_project_layers`.
- #129: plain service-area polygon in the access-map legend.

**WP2 -- data correctness** (#159, #160, #161, #153, #154)
- #159: key every dictionary by feature id and keep the label separate (hub candidates, matrix origins, route stops, population totals); duplicate-name and NULL-name fixtures.
- #160: zonal statistics on a detached copy of the zones; the real output field is resolved, not assumed; per-zone reporting; the input layer is not modified.
- #161: the rule in 5.1.
- #153: compare full CRS equivalence and the geotransform in the raster tools; a mismatch is rejected with the reason (alignment with a stated resampling rule is a follow-up only if you ask for it). Zero-denominator and NoData behaviour tested.
- #154: sample points are transformed into the DEM CRS; slope and lengths are metric; the imagery `min_area_m2` filter uses an ellipsoidal or projected area; missing elevations are reported.

**WP3 -- blocked roads** (#155, also my H1 and `build_composite_impedance_field`)
- Convention: a speed of 0 (or an explicit blocked flag) means closed. `build_composite_impedance_field` writes 0 for `damage_field = 0`; `apply_network_barriers` "block" writes 0.
- A shared helper returns the network with blocked segments removed; used by `calculate_service_area`, `travel_time_matrix`, `classify_facilities_by_access`, `optimize_delivery_route`, `population_access_gap`.
- The result reports how many segments were removed; if nothing is left, an explicit error. Tests: a service area and a route never cross a blocked segment.
- Affects three tools' behaviour: stated in the release notes and in the tool descriptions.

**WP4 -- Processing provider and registry** (#162, #163, #156, #157)
- Step 1 (first, no behaviour change): a live test that resolves every algorithm id the allowlist and tools reference against the real 4.2.2 registry and prints the missing ones. Its CI output decides the size of the rest.
- #162: replace or remove ids the registry does not contain (SAGA ids are host-dependent: such tools are registered only when the id resolves).
- #163: inspect each approved algorithm's parameter and output definitions; return all approved outputs; reject unknown parameters before running; classify mutating algorithms.
- #156: facility points transformed to the network CRS, the real child output schema, the time unit stated and converted (hours vs seconds).
- #157: `QgsProcessingException` on failed sinks and `addFeature`, cancellation checks in the O(C x D) loops, a stated size limit.

**WP5 -- `travel_time_matrix` partial-edge costs** (#152, after WP3)
- Design: for each destination, find the nearest road segment (spatial index, true geometry distance), compute its fractional position along the segment, and take the minimum over the segment's two endpoints of (cost to that endpoint from the origin) + (the partial-segment cost), respecting one-way direction and the speed field. Keys stay consistent with the small-set path.
- Acceptance fixture from the issue: a 1,000 m road, points at 490 m and 510 m, cost must equal the native routing cost on both sides of the 200-destination threshold.
- Risk: it touches the core matrix path. Mitigation: the existing equivalence live test (`classify_facilities_by_access` vs `travel_time_matrix`) is extended to cover partial edges, and the old approximation note is removed only when that passes.

**WP6 -- deliverables, lifecycle, disclosure** (#164, #167, #93, #91)
- #164: build and export a replacement layout privately and swap only on success; unique atlas file names; `feature_count` counts exported pages.
- #167: remove the translator on unload, stop the isolation worker, scope module eviction to modules this plugin owns. Needs a hand reload test: it is the riskiest edit to startup.
- #93: audit and document what a protected layer exposes to a cloud model (layer name, field names, counts; not values or geometry), write it into `SECURITY.md` and the Settings help, and show a chat notice when a protected layer is present with a cloud model active.
- #91: confirmation text states "full file download, kept in the project, only the clipped area is loaded"; cache-hit path tested.

**WP7 -- hand over for verification**
- Extend `docs/RC12_LIVE_TEST_AND_AUDIT_PLAN_2026-10-04.md` with a section per package (what to run, what a pass looks like).
- Update the implementation tracker and `CHANGELOG.md` / the rc12 block, including the four behaviour changes (blocked roads, boundary rule, per-zone totals, Python 3.10 floor).
- Rebuild rc12 once, after WP1-WP6 are merged, so you test one build.
- After your hand checks, I post results on the issues; you decide which to close. #169 closes when the 32 audit issues do.

### 5.3 Order and dependencies

WP4 step 1 first (diagnostic only), then WP1 and WP2 in parallel, WP3, WP4 remainder, WP5 (needs WP3), WP6, WP7. The rc12 rebuild waits for all of them.

### 5.4 What stays outside code

The hand verification of everything in section 1, a real PostGIS server for #151, and a real canvas for every map look. Those need you.
