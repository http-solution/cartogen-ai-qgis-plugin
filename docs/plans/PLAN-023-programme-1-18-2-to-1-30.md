# PLAN-023: programme from 1.18.2 to 1.30, every pending item with an owner, a release and a test

Status: planned

Written 2026-10-26 from `docs/PENDING_WORK_AND_PROFILE_ANALYSIS_2026-10-26.md` (the list, IDs W-1 to W-58 and O-1 to O-11) and the owner's answers of the same day: all profiles are planned; a persona is a lens and never a gate, one primary and one optional secondary; one release per package with its own short hand rows; connectors approved to plan: STAC load, CKAN / ArcGIS Hub / Socrata, WorldCover, GTFS, CHIRPS (open, no key), ACLED and the ReliefWeb app name (free key), and Power BI. Kobo/ODK and DHIS2 were not selected and are **not planned** here (they stay as tracker item HX4 until the owner asks).

Reading rules. Sizes are in "build days" of one agent session, my estimate, not measured. "CI" = offline suite or the QGIS 4.2.2 live job. "Hand" = a row the owner runs in desktop QGIS. Every number written as an expected value in an acceptance line is computed by hand in this file and becomes the assertion; a package whose code cannot reproduce it does not merge.

## Goal

After the programme, a QGIS user who picks a profile (humanitarian aid, logistics, security, engineering, GIS generalist, and the other ten) gets: the right tools ranked first for that profile, tools that exist for the profile's real tasks (spatial statistics, indices and time series, flood and cut/fill, vehicle routing, transit access, site selection, utility tracing, metadata and publishing), a map look and a layout built for the profile, data connectors for the sources the profile uses, and an honest readiness line that says what the plugin does for that profile and what it does not. Every item in the master list is either delivered in a named release with a hand row, or recorded as declined with a reason. Open issues: #362, #380 (closed by releases R0/R1 hand rows).

## Scope

### S1. Programme rules (apply to every work package)

1. **One package = one plan section here + one pull request + one ledger entry + at least one regression test + one hand row.** Nothing merges without `python tools/ledger_guard.py` and `tools/local_ci.sh --offline` passing.
2. **Pure core first**: the maths in a Qt-free module with known-answer tests; QGIS wiring second; a live test third that reads the result back from real QGIS objects.
3. **Every tool result states its method, its inputs echoed back, its limits, and what it did not do.** No figure without a supplied source.
4. **Hand rows are written before the code**, in the package section below ("Hand row"), and are added to `docs/HAND_TEST_V2_ROWS.json` format with `tools/check_evidence.py` expectations (`expected tools`, `forbidden tools`, `max_calls`). A package is `done` only after its hand row passes; before that its status log says "CI-checked".
5. **Release = cut after each release package** with the full procedure in S3. The owner's hand test is the bundle of that release only (target: 15 minutes, at most 6 rows), run after the model-free `tools/layout_check_script.py` when layouts changed.
6. **Dependencies**: numpy, GDAL and QGIS-native only (accepted 2026-10-04). Licensed data is user-supplied only. A persona never hides or blocks a tool and carries no tier logic.
7. **Wording in docs and replies**: states are `hand-verified`, `CI-checked`, `not verified`, `declined`. No other words.

### S2. Release map

| Release | Name | Work packages | Closes (master list) | Owner input needed before start | Build days |
|---|---|---|---|---|---|
| R0 | 1.18.2 Hygiene and the hand-run fixes | R0-1 to R0-6 | W-13 to W-18, W-1, W-2, W-11, W-12, W-10 | O-1 results | 6 + fixes |
| R1 | 1.19.0 Profiles | R1-1 to R1-9 | W-50, W-58 (skeleton), part of W-56 (catalogue file) | O-9 answered (below, Q3 to Q5) | 10 |
| R2 | 1.20.0 Spatial statistics | R2-1 to R2-6 | W-51 | case-count sample file (Q7) | 9 |
| R3 | 1.21.0 Indices, time series, STAC | R3-1 to R3-6 | W-52, STAC load, WorldCover, CHIRPS | none | 10 |
| R4 | 1.22.0 Terrain, flood, engineering | R4-1 to R4-6 | W-53, W-8 | a real DEM site and the engineer's report (Q8) | 10 |
| R5 | 1.23.0 Network and movement | R5-1 to R5-7 | W-54, W-39 | a depot/orders sample (Q9); Q10 on assumed speeds | 12 |
| R6 | 1.24.0 Site selection and urban | R6-1 to R6-5 | W-55 | a parcels layer and a store list (Q11) | 7 |
| R7 | 1.25.0 Connectors and Power BI | R7-1 to R7-6 | W-56, W-36 (ACLED only), Power BI | ACLED key (O-6); Power BI answers (Q1, Q2) | 10 |
| R8 | 1.26.0 Standards and publication | R8-1 to R8-4 | W-57, W-31 (server project) | none | 8 |
| R9 | 1.27.0 Geometry editing | R9-1 to R9-6 | W-19, W-20, W-21, W-22, W-23 | none | 9 |
| R10 | 1.28.0 Attributes, project, raster rows | R10-1 to R10-6 | W-26, W-27, W-28, W-29, W-30 | none | 9 |
| R11 | 1.29.0 Processing models and remaining waves | R11-1 to R11-6 | W-24, W-25, W-32 to W-35 | none | 11 |
| R12 | 1.30.0 Close-out | R12-1 to R12-4 | W-3 to W-9, W-37, W-38, W-40 to W-49, O-5 | O-5 material; O-7 | 6 + fixes |

Total about 117 build days of agent work plus the owner's hand tests (12 bundles of at most 15 minutes each). The first release is the only one whose scope depends on results I do not have yet.

Order rule: a release starts only when the previous release's hand rows are returned and its failures are fixed (as a patch release if needed). Releases R2 to R6 may be re-ordered by the owner without changing their content; R1 must come first; R7 needs R3 (STAC loader) and R5 (GTFS parser); R8 needs R1 (catalogue) and R7 (portals).

### S3. Release procedure (copy into every release's status log, tick as done)

1. All packages of the release merged with CI green on the merge head (12 jobs).
2. `metadata.txt` version, `pyproject.toml`, `CHANGELOG.md`, `README.md` "What's new" and tool/algorithm counts, `release_notes.py`, `docs/LEAN_HAND_TEST_PROTOCOL.md`, plugin Help text (`tests/test_release_docs_in_sync.py` passes).
3. `docs/TOOLS_REFERENCE.md` regenerated; `python tools/build_qgis_coverage.py --write-baseline` run when coverage rows moved.
4. `docs/OPEN_ISSUES_STATUS_<date>.md` and this plan's status log updated; `FEATURE_LEDGER.json` entries present with `hand_row`.
5. `release.yml` run (tag `cartogen-ai-v<version>`), assets zip + SHA256.txt checked against the local build's file list.
6. Bundle built with `tools/build_hand_test_v2.py` around the **published** zip (hash recorded), including only the rows of this release plus the regression rows listed in S4.
7. Owner runs the bundle; `python tools/check_evidence.py <folder>` gives verdicts; failures become a patch release before the next one starts.

### S4. Standing regression rows (always in every bundle, 5 minutes)

RG-1 install over previous version (toolbar count, log tab `CartogenAI`); RG-2 "list my layers" returns the project's layers; RG-3 a service-area request keeps the window responsive and Stop ends it within 2 seconds; RG-4 one print layout exports with the footer inside the page; RG-5 undo of the last change.

### S5. Work packages

Format per package: **What** (exact tools and parameters), **How** (method, source), **Files**, **Acceptance** (offline / CI-live / hand), **Hand row**, **Size**. File names are new unless marked "exists".

#### R0 (1.18.2): hygiene and the hand-run fixes

| Package | What | Files | Acceptance | Size |
|---|---|---|---|---|
| R0-1 (N1, W-13) | Set every plan's status from its own log: PLAN-001 to 003, 007 to 009, 013 to 018 get `done` or `abandoned` with a closing log line; PLAN-020 folded into PLAN-021 (`abandoned`, "folded into PLAN-021"); PLAN-019 `done`. PLAN-005, 006 stay `in progress` and get a remaining-work checklist that points to R11. A test rejects `in progress` on a plan whose log's last line is older than 30 days without a "next step" sentence | `docs/plans/*.md`, `tests/test_plans.py::TestPlans::test_in_progress_plans_name_a_next_step` | Offline | 1 |
| R0-2 (N2, W-14, W-1, W-2) | Add `hand_row` (a row id from a bundle, or `none: <reason>`) to all 83 ledger entries; guard: an entry with `hand_verified: true` must name a row; the 12 "not verified" entries and the 5 entries with an incomplete hand check each get a row id in the R0 bundle or in the release that touches them (table kept in the plan log) | `docs/FEATURE_LEDGER.json`, `tools/ledger_guard.py`, `tests/test_ledger.py::TestLedger::test_verified_entries_name_a_hand_row` | Offline | 2 |
| R0-3 (N3, W-15) | `IMPLEMENTATION_TRACKER.md`: delete the duplicate sections 1.19 to 1.24 that appear twice (keep the later, dated ones), put a current index of open items at the top, move closed items under section 4; `BUG_TRACKER.md` top table lists only open bugs | the two docs | Offline: `tests/test_docs_links.py` (new) fails on a section number that repeats | 1 |
| R0-4 (N4, W-16) | Pin the Windows runner image, update `upload-artifact`, add `status_note` input to `release.yml` appended to the release body, README test count generated by `tools/count_tests.py` and checked by `tests/test_release_docs_in_sync.py` | `.github/workflows/*.yml`, `tools/count_tests.py` | CI runs; a dry-run release shows the note | 1 |
| R0-5 (W-17) | Fix every defect the 1.18.1 hand run finds. Each defect: a ledger entry, a failing test first, a fix, a hand row | by defect | Hand | by results |
| R0-6 (W-10, W-11, W-12) | Close #362 (rows V4, V5, V6) and #380 (V3, V7, V8) if they pass, with the evidence folder named in the comment. If V5 shows an empty profile again: add the QGIS version, DEM size and layer CRS to `elevation_profile` results, then re-plan | issue comments | Hand | 0.5 |

Hand rows R0: the nine V rows already in the 1.18.1 bundle; no new rows.

#### R1 (1.19.0): profiles (PP0). Changes no analysis. Everything else hangs on it.

**Data model** (`src/cartogen_ai/core/personas/<id>.json`, 15 files, one loader `core/personas/__init__.py`):

```
{ "id": "public_health", "number": 8, "label": "...", "aliases": ["epidemiology"], "summary": "...",
  "guidance": "...",                          // replaces PROFILE_GUIDANCE text
  "workflows": [{"id": "ph.cluster", "title": "...", "tools": ["calculate_spatial_autocorrelation", "..."]}],
  "tool_priority": ["tool_a", "..."],         // max 12 names; each must exist in the registry
  "tool_aliases": {"tool_a": ["phrase", "..."]},
  "task_ids": ["38.01", "..."],
  "data_sources": ["hdx", "worldpop"],        // ids in data_sources.json
  "style_profile": "public_health",
  "layout_templates": ["epi_bulletin"],
  "readiness": [{"capability": "cluster detection", "state": "built|not built|out of scope|declined",
                 "tool": "detect_spatial_clusters", "since": "1.20.0", "hand_row": "R2-H3", "reason": ""}],
  "guardrails": ["Never show patient-level points; aggregate or obfuscate."] }
```

State vocabulary in `readiness` is only `built` (tool exists, hand row passed), `CI-checked`, `not built`, `out of scope`, `declined`. A guard test fails when a `built` entry has no passed `hand_row`.

| Package | What | Files | Acceptance | Size |
|---|---|---|---|---|
| R1-1 | Schema, loader, 15 files filled from the 2026-10-04 persona table (tools that exist now; capabilities not yet built marked `not built` with the release that will deliver them) | `core/personas/__init__.py`, `core/personas/*.json`, `tests/test_personas.py::TestSchema` | Offline: every `tools` name exists in `registry`; every `task_ids` exists; every `readiness.tool` exists or state is `not built`; 15 ids equal `PROFILE_LABELS` keys | 2 |
| R1-2 | One list: `ROLE_CHOICES` kept for the onboarding sentence, mapped to persona ids (`humanitarian_analyst` to `humanitarian`, `urban_planner` to `urban_planning`, `researcher` to `research`, `emergency_responder` to `humanitarian`, `cartographer`, `gis_student`, `other` to `general`); new settings keys `persona_primary`, `persona_secondary` in `infrastructure/settings_keys.py`; first read migrates the old `USER_PROFILE_KEY` value | `onboarding_profile.py`, `prompt_refiner.py`, `settings_keys.py` | Offline: migration test for each of the 15 old values | 1 |
| R1-3 | Settings dialog and onboarding: two dropdowns, a readiness panel generated from the persona file ("Built: ...; Not built: ...; Out of scope: ...") | `core/ui/settings_dialog.py`, `onboarding_dialog.py` (UI imports Qt; picture check per CLAUDE.md headless method) | CI live widget test reads the panel text; Hand row R1-H1 | 2 |
| R1-4 | Router re-rank: `tool_router` adds a score bonus to the primary persona's `tool_priority` (full) and secondary (half), capped so at most `PERSONA_BOOST_SLOTS = 5` tools enter the top 40 because of it; nothing is removed | `core/services/tool_router.py` | Offline: with persona `general` the 385-prompt replay and all golden rows are identical to today; for each other persona, the offered set for the golden rows is a superset of today's offered set minus at most 5 displaced low-score tools, and no golden row's expected tool is displaced | 2 |
| R1-5 | Task register: `persona` list on every task; 13 new categories 38 to 50 (one per persona except general and defence), 4 tasks each (52 tasks) written from the owner's persona document (tasks only for capabilities that exist or are scheduled; each names its tools or `guidance`); task matcher adds +0.1 for tasks listing the active persona | `task_register.json`, `task_matcher.py`, `tools/derive_task_io.py` | Offline: `tests/test_task_register.py` invariants; 52 tasks each have `persona` | 2 |
| R1-6 | Catalogue generator and the reachability ratchet: `docs/generate_persona_catalogue.py` writes `docs/PERSONA_CATALOGUE.md` from the persona files; `tests/test_tool_reachability.py` fails when a tool is in no task and no persona, with a frozen exception list that may only shrink (today's 123 become the list, then R1-5/R1-6 cut it) | docs script, test | Offline | 1.5 |
| R1-7 | Style layer L2: `core/representation/style_profiles.py` pure registry `{persona: {role: spec}}` for palette family, class count, label units; L0 rules enforced by test: colour-blind simulation (deuteranopia, protanopia, tritanopia matrices) keeps every categorical palette's adjacent pairs at CIEDE2000 >= 10; no red beside green | new module, `tests/test_style_profiles.py` | Offline | 1.5 |
| R1-8 | Data-source catalogue `core/agent/data_sources.json` and loader: `{id, label, personas, kind, access (open / free key / licensed), licence, size_class, egress_class, cache_folder, tool}`; the F22 size guard and the egress gate read it; existing sources migrated (HDX, geoBoundaries, OSM, Microsoft footprints, WorldPop, GDACS, FIRMS, EONET, FTS, USGS, UCDP, STAC search, geocoding, web search) | `data_sources.json`, size guard, egress gate | Offline: every `tool` exists; every personas id exists | 1.5 |
| R1-9 | Persona 15 pack: `defense_intel` readiness says: "Not built as written. Open-source conflict and access analysis is available under Humanitarian and Public Safety. Classified data must never be used with this plugin." Picker shows it | persona file | Offline text test | 0.5 |

Hand rows R1: **R1-H1** open Settings, pick primary "Public Health", secondary "Logistics": the readiness panel names built and not built items. **R1-H2** with primary "Engineering" type "delineate the watershed at 31.0297 N 35.8058 E": tools offered include `delineate_watershed`. **R1-H3** pick "GIS Generalist": the same request from the previous session returns the same tool as 1.18.1. Pass: tools called equal the expected ones in `check_evidence.py`.

#### R2 (1.20.0): spatial statistics (profiles 8, 12, 2, 4, 7, 14)

All four tools share `core/agent/tools/_spatial_weights.py` (pure): `build_weights(points_or_polygons, kind, k, distance, row_standardise)`. Kinds: `queen`, `rook` (polygons by shared vertex/edge), `knn` (k), `distance_band` (metres in a projected CRS; geographic CRS is reprojected to local UTM and the result says so). Islands (no neighbours) are reported by id and excluded from the statistic, never given a made-up neighbour. Seeded permutation (`seed` argument, recorded). Fields are numeric, features with NULL or non-numeric values are excluded and listed, never imputed.

| Package | Tool and parameters | Method and source | Known-answer tests (the pull request fails without them) | Size |
|---|---|---|---|---|
| R2-1 | `_spatial_weights.py` plus `calculate_spatial_autocorrelation(layer, field, weights="queen", k=None, distance=None, permutations=999, seed=1, write_local=False)`: global Moran's I with permutation p-value and z; optional Local Moran (LISA) writing `lisa_i`, `lisa_p`, `lisa_class` (HH, LL, HL, LH, not significant) after a confirm | Moran 1950; Anselin 1995 | (a) 4 by 4 grid, alternating +1/-1 checkerboard, rook binary weights: I = -1 exactly. (b) constant field: statistic undefined, tool returns a refusal naming the cause. (c) E[I] = -1/(n-1): for n = 16 it prints -0.0667. (d) row-standardisation: every weights row sums to 1. (e) Columbus crime data (public PySAL example, queen, row-standardised): I = 0.4857 to 3 decimals as published in the GeoDa documentation; the fixture is committed with its licence note in the PR, or this test is removed and the gap recorded in the log | 2 |
| R2-2 | `analyze_hotspots_gi_star(layer, field, weights, distance, fdr=True, alpha=0.05, seed=1, output_layer_name)`: Getis-Ord Gi* z-score per feature, p-value, optional Benjamini-Hochberg correction, class (99, 95, 90 percent hot or cold, not significant); writes a new layer (not the input) | Getis and Ord 1992; Ord and Getis 1995; BH 1995 | (a) uniform field: all z = 0. (b) one feature = 10 with all others = 0 on a 5 by 5 rook grid with self included: the high cell has the maximum z and its value equals the hand-computed Gi* formula (sum of weights x values minus mean x sum of weights, divided by sd x sqrt((n x S1 - W^2)/(n-1))), written out in the test comment. (c) BH: with p-values [0.001, 0.008, 0.039, 0.041, 0.2] and alpha 0.05 the adjusted rejects exactly the first two | 2 |
| R2-3 | `detect_spatial_clusters(layer, case_field, population_field, model="poisson", max_pop_fraction=0.5, max_radius=None, monte_carlo=999, seed=1)`: Kulldorff circular scan, most likely cluster and secondary non-overlapping clusters, relative risk, LLR, Monte Carlo p | Kulldorff 1997 | (a) LLR formula by hand: C = 100 total cases, c = 30 inside, E = 15: LLR = 30 ln(30/15) + 70 ln(70/85) = 20.794 - 13.591 = 7.203 (assert 7.203 +/- 0.001). (b) planted cluster on a 10 by 10 point grid with fixed seed: the scan returns the planted centre and p <= 0.01; no cluster planted: p > 0.05. (c) cluster limit: never exceeds `max_pop_fraction` | 3 |
| R2-4 | `calculate_health_rates(layer, cases, population, method="crude|smr|eb", expected_field=None, per=100000, min_population=...)`: crude rate, relative risk (rate / overall rate), indirect SMR with expected counts supplied by the user (never invented), empirical-Bayes smoothing (global, Marshall 1991); a **small-number flag** per feature (population below `min_population` or cases below 5) and suppression of the flagged value in the output look | Marshall 1991 | (a) 3 areas cases [10,20,30], pop [1000,2000,3000]: crude rate per 100,000 = 1000 each; RR = 1 each. (b) EB: two areas with equal rate: smoothed = unsmoothed. (c) flag at cases < 5 | 1.5 |
| R2-5 | Looks and layout: `style_profiles['public_health']`: single-hue sequential rate ramp (ColorBrewer Blues or Oranges, 5 classes, quantile), cluster outlines in black/white double stroke (never red), hatch for suppressed small numbers, legend says "Rate per 100,000; suppressed where n < 5"; layout template `epi_bulletin` (title block, rate map, epidemic curve via `generate_chart`, method box, "scenario / cases reported by" line); `apply_persona_look` is not a new tool: `apply_humanitarian_look` pattern extended with `look="rate"|"cluster"|"lisa"` | `humanitarian_style.py`, `layout_style.py`, new template | CI live: renderer type, class count, colours, hatch symbol layer present; layout geometry check from `layout_check_script.py` | 2 |
| R2-6 | Persona wiring: public_health, public_safety, humanitarian, urban_planning, environment, real_estate files get the four tools in `tool_priority`; tasks 38.xx written; ledger entries; aliases ("is this a real cluster", "hotspot test", "outbreak", "clustering of incidents") | persona files, task register | Offline routing rows: 12 plain prompts reach the right tool in the top 10 | 0.5 |

Hand rows R2 (data: `docs/hand_test_v2_inputs/cases_by_district.gpkg`, built from a file the owner supplies, Q7): **R2-H1** "is there spatial clustering of cases?" returns Moran's I with p and a sentence of method and limits; tools = `calculate_spatial_autocorrelation` only, no more than 3 calls. **R2-H2** "find hotspots with a significance test" produces a layer with 99/95/90 classes, legend readable. **R2-H3** "find the most likely cluster" gives centre, radius, relative risk, p. **R2-H4** "make an epidemic bulletin" exports a one-page PDF where the footer is inside the page and no patient-level points appear.

#### R3 (1.21.0): indices, time series, STAC load, change (profiles 6, 7, 4, 9)

| Package | What | Method and tests | Size |
|---|---|---|---|
| R3-1 | `calculate_spectral_index(index, raster, bands={...}, output)` replacing three duplicate patterns: indices NDVI (exists), NDWI, NDRE, plus SAVI, EVI, NDMI, NBR, MNDWI, BSI. Pure formulas in `raster_indices.py`. Division by zero returns NoData, not 0. Rasters must share CRS, size, origin (existing check) | Hand-computed: SAVI(NIR 0.5, R 0.1, L 0.5) = 0.4/1.1 x 1.5 = 0.5455; EVI(NIR 0.5, R 0.1, B 0.05) = 2.5 x 0.4 / (0.5 + 0.6 - 0.375 + 1) = 1.0/1.725 = 0.5797; NDMI(NIR 0.5, SWIR 0.3) = 0.2/0.8 = 0.25; NBR(NIR 0.5, SWIR2 0.1) = 0.4/0.6 = 0.6667; NoData where NIR + R + L = 0 | 2 |
| R3-2 | `load_stac_assets(catalog, collection, bbox or layer, datetime, assets=[...], max_cloud=20, limit=1)` (STAC **load**, not only search): downloads COG windows with GDAL `/vsicurl/` clipped to the AOI, size shown and confirmed first (existing F22 guard), cache folder, provenance sidecar; catalogs allowed: Element 84 Earth Search (Sentinel-2 L2A, Landsat C2, Copernicus DEM, ESA WorldCover), no key | Offline: STAC JSON fixtures (item with `assets`, `proj:epsg`, `eo:cloud_cover`) parse; asset URL allow-list by host; size estimate = window cells x bytes. CI live (network, non-blocking like package J): one item loads, its CRS and band count read back | 3 |
| R3-3 | `raster_time_series_stats(rasters or items, statistic="mean|trend|anomaly", baseline=...)`: per-pixel mean, OLS slope per time unit (years), z-score anomaly against baseline mean and sd; cell budget guard (existing 60M) | Known answers: values 1,2,3,4 at t = 0,1,2,3 give slope 1.0 exactly; baseline mean 10, sd 2, value 14 gives z = 2.0 | 2 |
| R3-4 | `calculate_change_matrix(raster_a, raster_b, classes=table)`: from-to cross-tabulation in cells, hectares (cell area from CRS, ellipsoidal for geographic) and percent; gain, loss, net, persistence; writes a table layer and a chart | Known answer: 2 by 2 rasters [[1,1],[2,2]] to [[1,2],[2,2]]: matrix [[1,1],[0,2]], loss class 1 = 1 cell, gain class 2 = 1 cell | 1.5 |
| R3-5 | `create_management_zones(raster_or_stack, n_zones=3..5, min_zone_area_ha, smooth)`: k-means (numpy, seeded) on one or more index rasters, small-zone merge into the neighbour with the nearest mean, polygonize; legend carries the mean index per zone; **no yield or rate recommendation** | Known answer: two flat patches with values 0.2 and 0.8, n = 2: two zones with exact means; zone under min area merges | 2 |
| R3-6 | Looks and layouts: `style_profiles` agriculture (index classes with units, zones 3 to 5 sequential), environment (ESA WorldCover official class colours, change classes loss/gain/stable, protected-area hatch), layouts `field_report` and `change_report`; persona files; tasks | CI live renderer assertions; layouts via check script | 2 |

Hand rows R3: **R3-H1** "compute NDRE and SAVI for this Sentinel-2 scene": two rasters, values range in [-1,1], names carry the formula. **R3-H2** "load Sentinel-2 for this polygon from last month with under 20 percent cloud" (needs network; confirm card shows size first). **R3-H3** "what changed between these two land-cover rasters" returns the matrix with hectares and a chart. **R3-H4** "make three management zones for this field" returns 3 polygons and a legend with mean per zone.

#### R4 (1.22.0): terrain, flood, engineering (profiles 3, 9, 10, 12, 7)

| Package | What | Method and tests | Size |
|---|---|---|---|
| R4-1 | `calculate_cut_fill(dem_before, dem_after, boundary=None, datum_note)`: per-cell difference, cut and fill volumes (m3) and net, grid of change classes; DEM vertical unit must be metres or the tool refuses naming the unit | Known answer: 10 by 10 cells of 30 m, constant +2 m: fill = 2 x 100 x 900 = 180,000 m3, cut = 0; mixed ±1 m halves: cut = fill = 45,000 m3 for 50 cells each | 1.5 |
| R4-2 | `calculate_hand(dem, stream_threshold_cells)`: Height Above Nearest Drainage with the existing priority-flood fill, D8 and accumulation from `watershed_delineation.py` (reused, not copied) | Known answer: a V-shaped valley with channel at elevation 0 and slopes rising 1 m per cell: HAND at distance d cells = d m; cells in the channel = 0 | 2.5 |
| R4-3 | `flood_footprint_bathtub(dem, water_level_m, source=point_or_cells, connectivity="8", population_layer=None)`: cells below the level **connected to the source** (flood fill), depth raster, flooded area, optional exposure through `estimate_population_exposure`. The result says: "static level, no flow, no time, not a hydraulic simulation" and carries the scenario name in the layer and legend ("scenario, not forecast") | Known answer: bowl DEM 5 by 5, centre 0, rim 5, level 2 with source at centre: flooded cells = those with z < 2 connected to the centre; a separate pit below 2 not connected is excluded and listed | 2.5 |
| R4-4 | `viewshed_analysis(dem, observer, observer_height_m, target_height_m=0, max_distance_m, curvature=True)` wrapping `gdal:viewshed` (checked on the real registry by the existing dump test), output visible/hidden raster and visible area; observer must be inside the DEM | Live: flat DEM with a 50 m wall: cells behind the wall hidden; offline: parameter validation | 1.5 |
| R4-5 | `engineering_sheet` layout (title block with project, datum, units, revision, drawn-by; scale bar; north arrow; sheet number) and engineering look (index contour every 5th line heavier; hillshade multiply; basin outline and flow path; cut/fill diverging ramp centred on zero); `generate_contours` gets `index_every` | `layout_style.py`, `engineering_style.py` | Layout check script row; renderer assertions | 2 |
| R4-6 | Persona wiring for engineering, disaster_risk, utilities, public_safety, environment; landslide-susceptibility is **not a new tool**: a documented task using `weighted_overlay_analysis` with required guardrail text ("weights are supplied by the user; no calibration; screening only"); tasks; ledger | persona files, task register | Offline routing rows | 0.5 |

Hand rows R4: **R4-H1** (Q8) "delineate the watershed at <site> and compute the peak flow for 20 years" compared with the engineer's report: area, length, H, slope, Tc each within the tolerance the owner states in advance (default 10 percent for area and length, since the DEM source differs). **R4-H2** cut/fill between two DEMs the owner supplies. **R4-H3** flood footprint for a stated level at a stated point, depth raster visible, legend names the scenario. **R4-H4** viewshed from a point; hidden cells behind a ridge look hidden.

#### R5 (1.23.0): network and movement (profiles 5, 11, 10, 2)

| Package | What | Method and tests | Size |
|---|---|---|---|
| R5-1 | `solve_vehicle_routing(depot, stops_layer, demand_field, vehicles=[{capacity, max_minutes}], time_window_fields=(open, close), service_minutes, network, seed)`: capacitated VRP with time windows by construction (cheapest insertion) then improvement (2-opt within routes, relocate and swap between routes), time from the road network cost matrix (existing `travel_time_matrix`/graph code); output: routes layer (one per vehicle), stops layer with `route`, `seq`, `arrive`, `load`, and an unassigned list with the reason (capacity or window) | Known answers: (a) 5 stops on a line, one vehicle, ample capacity: the tour is the optimal one found by brute force over 5! permutations. (b) 2 vehicles capacity 10, demands [6,6,4,4]: feasible assignment sums to <= 10 per route, none unassigned; demands [11]: unassigned with reason capacity. (c) time window closed before earliest arrival: stop unassigned with reason window. Heuristic limit stated in every result: "no optimality guarantee; solved by heuristic; seed N" | 4 |
| R5-2 | `create_od_flow_map(od_table, origin_layer, dest_layer, flow_field, min_flow)`: desire lines with width proportional to flow (square-root scaling), top-N filter, legend in flow units | Known answer: flow 400 vs 100 gives width ratio 2.0 | 1.5 |
| R5-3 | `calculate_transit_accessibility(gtfs_zip, origin_points, departure_window, max_minutes, walk_speed_kmh)`: GTFS reader (stops, stop_times, trips, calendar) in `gtfs_reader.py` (pure); earliest arrival by a connection scan (RAPTOR-style, one transfer limit configurable) with walking access/egress by straight line at the walk speed (stated); output isochrone-like reach polygons or stop reach table | Known answer: fixture feed with 3 stops A->B 10 min, B->C 10 min, departures at 08:00 and 08:20, window 08:00 to 08:30: arrival at C = 08:20; transfer wait respected; calendar exclusions respected | 4 |
| R5-4 | `trace_network(network_layer, start, direction="upstream|downstream|connected", valve_layer=None)` and `isolate_segment(network_layer, segment_id, valve_layer)`: connectivity tracing on `QgsGraph` (already used) with a snapping tolerance in metres; isolation returns the valves to close and the segments cut off | Known answer: Y-shaped network (3 edges meeting at a node, valves on two edges): isolating the stem requires both valves; downstream of a source follows the stated edge direction; disconnected component is not reached | 3 |
| R5-5 | `check_network_topology(layer, tolerance)`: dangles, disconnected components, duplicate edges, zero-length edges; markers layer; no auto-fix (a fix goes through existing `fix_geometries` with confirmation) | Known answer: a line network with one 0.5 m gap and tolerance 1 m connects; tolerance 0.1 m reports two dangles | 1.5 |
| R5-6 | Travel profiles: `profile="driving|walking|cycling"` on service area and matrix tools: speed table in `travel_profiles.py` (walking 5 km/h, cycling 15 km/h, stated as assumptions and echoed); road classes not allowed for the profile are excluded (motorway for walking) | Known answer: 1 km edge walking at 5 km/h = 12 min | 1 |
| R5-7 | W-39 speeds by road class (see Q10) and the layouts `route_plan` (route map with sequence labels, depot and hub symbols, a stop table with arrive/load) and `outage_map`; looks (per-vehicle categorical colours from a colour-blind-safe set, choke-point highlight); persona files for logistics, transport, utilities | `logistics_style`, templates | Layout check; renderer assertions | 2 |

Hand rows R5: **R5-H1** (Q9 data) "plan deliveries from this depot to these 12 stops with 2 vehicles of capacity X" produces 2 routes, a stop table, nothing unassigned unless the data says so. **R5-H2** "show flows between these districts" desire lines. **R5-H3** GTFS accessibility from a point for 45 minutes. **R5-H4** "what valves close to isolate this pipe" lists valves and shows the cut-off segments.

#### R6 (1.24.0): site selection and urban (profiles 14, 4, 5)

| Package | What | Method and tests | Size |
|---|---|---|---|
| R6-1 | `calculate_huff_model(demand_points_or_zones, sites, attractiveness_field, beta=2.0, distance="network|euclidean")`: probability of a zone choosing each site, expected demand per site; all inputs echoed; distance matrix from existing travel-time code | Known answer: two sites equal attractiveness and equal distance: 0.5 each; attractiveness 2 vs 1 at equal distance, beta any: 0.667 vs 0.333; distance 1 vs 2 with beta 2, equal attractiveness: 1/(1+1/4) = 0.8 vs 0.2 | 1.5 |
| R6-2 | `calculate_centre_of_gravity(layer, weight_field, group_field=None)`: weighted mean centre, standard distance, optional per group | Known answer: points (0,0) weight 1 and (10,0) weight 3 give (7.5, 0) | 0.5 |
| R6-3 | `create_trade_areas(sites, method="voronoi|drive_time", minutes=[...])` using existing service-area and Voronoi algorithms, unioned per site; the output look uses bands | Known answer: 2 sites, Voronoi boundary equidistant (assert on the perpendicular bisector) | 1 |
| R6-4 | `allocate_land_use_scenario(zones, suitability_field, classes=[{name, target_ha}], constraints)`: greedy allocation by suitability rank until each class target hits; stops when the targets are met or zones run out; reports unmet targets; labelled "scenario allocation from your targets, not a forecast" | Known answer: 5 zones of 10 ha with suitability [9,8,7,6,5], target 20 ha class A: zones 1 and 2 | 2 |
| R6-5 | `split_parcel(polygon, parts=N or area_each, direction)`: equal-area subdivision by moving a parallel line (bisection search to 0.01 percent) ; `planning_board` and `site_comparison` layouts, looks (trade-area bands, probability surface, site score), persona files for real_estate, urban_planning | Known answer: 100 by 50 rectangle into 4: four 1,250 m2 strips; sum of parts equals the parcel to 1e-6 | 2 |

Hand rows R6: **R6-H1** Huff for the owner's store list (Q11): probabilities sum to 1 per zone. **R6-H2** split a parcel into 3 equal parts and check areas in the attribute table. **R6-H3** `site_comparison` PDF exports with the footer inside the page.

#### R7 (1.25.0): connectors and Power BI

Every connector: entry in `data_sources.json`; size guard; egress class; cache folder; provenance sidecar; no key in logs; failure is reported with the HTTP status and never mocked.

| Package | What | Notes | Size |
|---|---|---|---|
| R7-1 | `search_open_data_portal(portal_url_or_id, query)` and `fetch_portal_dataset(portal, dataset_id, resource)` for **CKAN** (`package_search`, `resource_show`), **ArcGIS Hub** (`/api/search/v1`, then a FeatureServer query layer), **Socrata** (SODA `$limit`, `$where`); allow-list of portal hosts held in `data_sources.json` plus "user-added host" with a confirm | Offline fixtures per portal; CI live non-blocking against one public portal each, reported as "reached" or "not reachable" | 4 |
| R7-2 | `load_worldcover(bbox_or_layer, year)` through the R3-2 loader (ESA WorldCover COG, open licence CC BY 4.0, attribution line added to the layout credit) | Offline fixture; the class legend uses the official 11 classes | 1 |
| R7-3 | `fetch_chirps_rainfall(bbox, start, end, product="daily|pentad|monthly")` from the open CHIRPS COG/GeoTIFF store; window reads, size guard; result raster stack + summary table; units mm and the product's native resolution (0.05 deg) stated | Offline fixture; CI live non-blocking | 2 |
| R7-4 | `fetch_acled_events(country, start, end, event_types)`: key held only in the QGIS Auth Manager (same path as provider keys), terms shown on first use, results are points with source, date, "reported by ACLED"; goes through the egress gate; **blocked until O-6** | Offline: request building with a stubbed transport; no key in any log line (test greps the log capture) | 2 |
| R7-5 | ReliefWeb structured API when the app name exists (O-6): `find_incident_reports` gains `reliefweb_api` as a source with filters; until then the RSS path stays and the reply says so | Offline stub | 1 |
| R7-6 | **Power BI hand-off** (Q1, Q2): `export_for_power_bi(layers, folder, date_field=None, include=["table","geojson","shape_map"])` writes: a flat UTF-8 CSV per layer with `latitude`, `longitude` for points (centroids for polygons, labelled), a GeoJSON (RFC 7946) for the Azure Maps / ArcGIS visuals, a TopoJSON for the Shape Map visual, a date table CSV when a date field is given, and `POWERBI_STEPS.md` with the exact click path (Get data, Text/CSV; Map visual; Shape Map, Add map, Topo JSON). Sensitive layers pass the existing sensitivity and obfuscation gate; the egress gate applies. No credentials, nothing is uploaded | Offline: column names, coordinate order (lon, lat in GeoJSON; separate fields in CSV), CRS 4326 transform, header BOM-free UTF-8; TopoJSON validity by structural check (`type`, `objects`, `arcs`, `transform` optional); live: layer read-back. **Not verifiable here:** that Power BI Desktop loads the files; that is hand row R7-H4. **Push to the Power BI service (REST push dataset) is a separate package R7-6b, planned only if Q1 answers "push"**: needs an Azure AD app registration, workspace id and a token stored in the Auth Manager | 3 |

Hand rows R7: **R7-H1** search a public CKAN portal for "health facilities", fetch one resource as a layer. **R7-H2** load WorldCover for a small polygon and see the official colours. **R7-H3** CHIRPS rainfall total for a month for a polygon. **R7-H4** open the exported folder in Power BI Desktop: the CSV loads, the map visual shows points, Shape Map shows the polygons; owner reports pass/fail per file. **R7-H5** (after key) ACLED events for a country and month.

#### R8 (1.26.0): standards and publication (profiles 13, 1)

| Package | What | Method and tests | Size |
|---|---|---|---|
| R8-1 | `export_iso19115_metadata(layer, folder)`: ISO 19115-1 XML (`mdb:MD_Metadata`) from layer metadata + the provenance sidecar (lineage steps, tools, dates, sources); a checker lists missing mandatory elements (title, abstract, date, language, topic category, extent, reference system, contact, lineage) and refuses to call the file complete if any is missing | Offline: required-element set; XML well-formed; round trip: elements written equal elements read | 3 |
| R8-2 | `check_topology_rules(layer_a, layer_b, rule)`: rules `polygons_no_gaps`, `polygons_no_overlap` (exists as diagnose), `must_be_covered_by`, `points_inside_polygons`, `lines_no_dangles`; marker layer per violation with the rule id | Known answers: two squares sharing an edge have no gap; with a 1 m sliver gap, one gap polygon of area 1 x edge length | 2.5 |
| R8-3 | `create_ogc_api_project(layers, folder, title)`: writes a QGIS project with WFS / OGC API Features publication properties (`WFSLayers`, `WFSUrl`, CRS list) for the chosen layers and a README with the QGIS Server start command; no server is started and nothing is uploaded; reports clearly that serving needs the owner's QGIS Server | Offline: project XML properties read back; live: project opens | 1.5 |
| R8-4 | `publication_figure` layout (figure sizes 85 / 180 mm wide at 300 dpi, greyscale-safe ramps by test, source / CRS / date line on every figure, scale bar) and the persona entries for research and generalist | Layout check script; ramp test (grey-level differences >= 8 percent between classes) | 1.5 |

Hand rows R8: **R8-H1** export metadata for a layer: the XML opens in a browser and the checker output lists exactly what is missing. **R8-H2** topology rule on two layers shows markers. **R8-H3** open the OGC API project in QGIS. **R8-H4** publication figure PDF at the stated size.

#### R9 (1.27.0): geometry editing (QGIS rows D and C)

Each tool uses the existing edit session and transaction log, so each is undoable with `undo_last_operation`, asks for confirmation before changing a layer the user did not create, and reports the count of features changed.

| Package | Tool | Notes and tests | Size |
|---|---|---|---|
| R9-1 | `edit_vertices(layer, feature_id, action="add|move|delete", index or x,y, tolerance)` | Known answer: square with 4 vertices; delete vertex 2 gives a triangle of the expected area; add vertex at a midpoint leaves area unchanged | 2 |
| R9-2 | `edit_parts_and_rings(layer, feature_id, action="add_part|add_ring|fill_ring|delete_part|delete_ring", geometry_wkt)` | Known answer: add a ring inside a 10 by 10 square: area drops by the ring's area; fill_ring restores it | 2 |
| R9-3 | `reshape_geometry(layer, feature_id, line_wkt)`, `offset_curve(layer, distance, join)`, `reverse_line`, `trim_extend_lines(layer, tolerance)` | Known answer: offset a 10 m line by 2 m gives a parallel line of length 10; reverse swaps the first and last vertex | 2 |
| R9-4 | `copy_features_between_layers(source, target, selection_or_filter, field_mapping)`: only to a layer of compatible geometry type, field mapping shown first | Known answer: 3 selected features arrive with the mapped fields; type mismatch is refused | 1.5 |
| R9-5 | `identify_at_point(x, y, crs, layers=None, radius)`: features and raster cell values at a coordinate, no map click needed; results limited to 50 features and say so | Live: point inside a polygon returns it with its attributes; raster cell value read back equals the known cell | 1 |
| R9-6 | Router aliases, tasks, ledger, coverage baseline moved (D and C rows from MISSING to COVERED) | Offline golden rows | 0.5 |

Hand rows R9: **R9-H1** delete a vertex then undo. **R9-H2** add and fill a ring. **R9-H3** "what is at 35.9 E 31.9 N" returns attributes.

#### R10 (1.28.0): attributes, project and raster rows

| Package | Tool | Notes and tests | Size |
|---|---|---|---|
| R10-1 | `add_virtual_field(layer, name, type, expression)` with the existing expression screen; `set_field_constraint(layer, field, not_null, unique, expression)`; `set_default_value(layer, field, expression, apply_on_update)` | Live: virtual field value equals the expression for each feature; constraint violation is reported by `QgsVectorLayerUtils` check; denied expression functions refused | 2.5 |
| R10-2 | `set_conditional_formatting(layer, field, rules)` and `set_map_tip(layer, template)`: map tip template is HTML with expression fields only; **layer actions that run commands are refused** (policy: no command execution) and the reply says why | Live read-back; refusal test | 1.5 |
| R10-3 | Renderers: `set_renderer(layer, kind="merged_features|inverted_polygons|embedded|no_symbols|2_5d", options)` | Live: renderer type read back | 1.5 |
| R10-4 | Raster: `build_pyramids(raster, levels, method)` (writes next to the file after the overwrite confirm), `raster_attribute_table(raster)` (read), `get_raster_value(raster, x, y, band)` (shares R9-5 reader) | Live: overview count read back; value equals known cell | 1.5 |
| R10-5 | Project: `set_project_transform_context(source_crs, dest_crs, operation_id)` listing available datum operations, custom CRS from a WKT / PROJ string after validation, project ellipsoid and distance/area units; canvas decoration settings (title, copyright, scale bar, north arrow, grid) stored as project properties; documented as not renderable in CI (no canvas), hand-only | Live: transform context read back; custom CRS `isValid()` | 2 |
| R10-6 | 3D map view probe: live test lists whether the 3D module is present; if present a `create_3d_view` package is planned in R12 with its own plan; if absent the coverage row is set to `declined (module absent in the CI image)` | Probe test | 0.5 |

Hand rows R10: **R10-H1** add a virtual field and see it in the attribute table. **R10-H2** map tip shows on hover. **R10-H3** pyramids built; raster draws faster (owner observation). **R10-H4** datum transformation choice listed for two CRSs.

#### R11 (1.29.0): Processing models and the remaining waves

| Package | What | Notes | Size |
|---|---|---|---|
| R11-1 | `run_processing_model(model_file)`: reads a `.model3` from the project folder, **parses every child algorithm id and refuses the model unless each id is on the approved list**; runs through the existing background runner with outputs forced to temporary layers; Python-script algorithms and expression inputs with denied functions refused | Offline: a model with an unapproved child is refused naming the child; live: a two-step approved model runs | 3 |
| R11-2 | `run_processing_batch(algorithm_id, inputs_layer_list, parameters)`: the same algorithm over N layers, N capped at 20, results grouped | Live | 2 |
| R11-3 | In-place edit: `run_algorithm_in_place(algorithm_id, layer, selected_only)` for the approved in-place algorithms (those flagged `FlagSupportsInPlaceEdit`), through the edit session and undo | Live: result equals the not-in-place output copied back | 2 |
| R11-4 | PLAN-005 remaining waves: the 60 file-writing algorithms in dispositions order, each with outputs forced to temporary layers; per-algorithm live smoke; an algorithm that fails smoke is listed with its error and stays off | Live per algorithm | 3 |
| R11-5 | PLAN-006 E2b and E2a: information reports and plots as tools returning numbers in the reply and a chart; the 16 expression-taking algorithms after the expression screen; the 17 path-reading algorithms reviewed one by one (allow, or `declined` with reason) | Live | 2 |
| R11-6 | Argument-list and return-type check against the QGIS 4.2.3 reference (`tests/test_pyqgis_call_arity.py`): parse every `qgis.core` call in `src/` and compare positional counts to the reference signatures committed as a JSON snapshot; failures listed with file and line | Offline | 2 |

Hand rows R11: **R11-H1** run a two-step model the owner saves. **R11-H2** a model containing an unapproved algorithm is refused with its name. **R11-H3** in-place smooth on selected features, then undo.

#### R12 (1.30.0): close-out

| Package | What | Size |
|---|---|---|
| R12-1 | Verification sweep: every ledger entry whose `hand_row` is `none` gets a row in the 1.30.0 bundle or a written decision `declined (reason)`; goal: zero "not verified" entries. Rows for W-3 (wave E1, DXF, Excel), W-5 (Windows font fit), W-6 (messy data), W-7 (numerical correctness: five Processing outputs compared with values computed by GDAL/numpy on fixtures) | 3 |
| R12-2 | JIAF blockers (O-5): when the material arrives, run the comparison, record each difference, and change the rules only with the owner's decision; if no material by 1.30.0, the blockers stay in every JIAF result and this package is `declined for this release, carried` | 1 |
| R12-3 | Architecture decisions W-44 to W-47 recorded as decisions (accept / reject / schedule) from Q12; W-48 chunked k-means built if Q13 says so; W-40 to W-43 fixed with a failing test each | 3 |
| R12-4 | Stable-release gate: all of R0 to R12 hand rows passed on at least one Windows machine; clean-profile install and upgrade (O-7); then the owner decides stable and plugins.qgis.org (O-3) | 0.5 |

### S6. Risk register

| Risk | Effect | Mitigation | Trigger |
|---|---|---|---|
| A published value (Columbus Moran's I) cannot be reproduced | R2-1 test removed, claim weakened | Test uses hand-computed cases; the published case is added only if it reproduces to 3 decimals | R2-1 PR |
| Heuristic VRP gives poor routes on real data | R5-H1 fails | Report the gap to brute force on small cases; seeds; increase improvement passes; state "no optimality guarantee" | R5-H1 |
| Network sources change response format | Connector breaks | Fixtures from real responses; non-blocking live probe per source; error reports status, never mocked | R7 CI live |
| Hand rows expand beyond 15 minutes | Owner cost | Max 6 rows per bundle; the model-free script covers layouts; rows needing a model answer are limited to the new tools | each release |
| A persona re-rank displaces a needed tool | Wrong tool offered | Cap of 5 slots; golden rows and 385-prompt replay run with every persona in CI | R1-4 |
| Power BI cannot load an export | R7-H4 fails | Files follow Microsoft's documented input formats; each file type is separate so one failing does not block the rest; fix in a patch release | R7-H4 |
| QGIS 4.2.x API change | Live job fails | CI image pinned; call-arity check (R11-6) | any |

### S7. Open questions and the default used if unanswered

| # | Question | Default used | Effect if the answer differs |
|---|---|---|---|
| Q1 | Power BI: hand-off files only (no login), or also push to the Power BI service (needs an Azure AD app, workspace id, token in the Auth Manager)? | Hand-off files only (R7-6) | Add R7-6b: push dataset via REST, 4 days, blocked on credentials |
| Q2 | Power BI visuals you use: Shape Map, Azure Maps, ArcGIS Maps, or a custom visual? | All three file types are written | Drops the unused files |
| Q3 | Persona picker: show all 15 or hide Defense and intelligence (shown with its "not built as written" text)? | Show, with the text | Hide: R1-9 shrinks |
| Q4 | Utility colour code default: APWA (US) or another? | APWA, as a setting | A different default table in `style_profiles` |
| Q5 | Land-use palette default: ESA WorldCover classes, CORINE, or your own list? | ESA WorldCover | One more palette (0.5 day) |
| Q6 | Is a Windows machine available for every hand bundle (the layout footer font fit differs by OS)? | Yes, Windows only | A second OS adds a row set per release |
| Q7 | Case-count data for the R2 hand rows: which districts file can you supply (any country; no patient-level points)? | I build a synthetic districts file; the hand row then proves the tool, not a real outbreak | Real file gives a real check |
| Q8 | The engineer's report for the watershed site (area, length, H, slope, Tc, Q) and the tolerance you accept? | Tolerance 10 percent on area and length | Tighter tolerance may fail on DEM differences, and the plan records why |
| Q9 | A depot, 12 stops with demand and time windows, and vehicle capacities? | Synthetic sample | Real sample |
| Q10 | W-39 assumed speeds by road class when `maxspeed` is missing (only 0.9 percent of Jordan's roads carry it): apply by default, or only when the user asks? | Only when asked (`use_assumed_speeds=true`), the result lists the table used | Default-on changes existing results; needs a release note |
| Q11 | A store list and a parcels layer for R6? | Synthetic | Real data |
| Q12 | Architecture items W-44 to W-47 (agent pipeline, typed plan gate, project folder structure, matcher normalisation): accept, reject or schedule each? | Reject W-44 and W-46 as not needed; schedule W-45 as a typed-step validator in R12; W-47 accept with a test | Scheduling W-44 adds a multi-release plan |
| Q13 | Chunked k-means (W-48): do you work with rasters above 60M cells? | No; guard stays | Build in R12-3, 2 days |
| Q14 | Kobo/ODK and DHIS2: confirm not planned? | Not planned | A new release R13 |
| Q15 | Release names: stay on 1.x minor numbers for each release above? | Yes | Rename in S2 only |

Owner inputs by date: O-1 results now; O-9 and Q3 to Q5 before R1; Q7 before R2; Q8 before R4; Q9 before R5; Q11 before R6; O-6 and Q1 before R7; O-5 before R12.

## Acceptance

The programme is `done` when all of these hold, each checked by a named test or file:

1. Every row of S2 has a merged release, a GitHub release `cartogen-ai-v<version>`, and a returned bundle with `tools/check_evidence.py` verdicts stored in `docs/` as `HAND_TEST_RESULTS_<version>.md`. Offline check: `tests/test_programme_plan.py::TestProgramme::test_each_release_row_has_a_results_file_or_a_declined_line` (new, reads this file).
2. `docs/FEATURE_LEDGER.json`: every entry has `hand_row`; none says `not verified`. Offline: `tests/test_ledger.py::TestLedger::test_no_entry_is_not_verified_at_1_30`.
3. `docs/qgis_coverage/SUMMARY.md`: missing rows reduced from 17 to the rows recorded `declined` with a reason (QGIS Server hosting, layer credential storage, 3D map view if the module is absent); the baseline file proves it.
4. `docs/PERSONA_CATALOGUE.md` (generated) lists, for each of the 15 profiles, every capability as `built` with its passed hand row, or `not built`, `out of scope` or `declined` with a reason. A `built` entry without a passed row fails the build.
5. GitHub: #362 and #380 closed with evidence; no other issue opened by a defect of this programme remains open at 1.30.0.
6. Hand-test cost: each bundle at most 6 new rows plus RG-1 to RG-5; total owner time per release at most 20 minutes (recorded by the owner in the results file).

## Guard tests

New, created by the packages above (names are fixed here so the ledger can reference them): `tests/test_personas.py::TestSchema`, `tests/test_personas.py::TestMigration`, `tests/test_tool_reachability.py`, `tests/test_style_profiles.py`, `tests/test_spatial_weights.py`, `tests/test_spatial_autocorrelation.py`, `tests/test_gi_star.py`, `tests/test_kulldorff_scan.py`, `tests/test_health_rates.py`, `tests/test_raster_indices.py`, `tests/test_stac_loader.py`, `tests/test_time_series_stats.py`, `tests/test_change_matrix.py`, `tests/test_management_zones.py`, `tests/test_cut_fill.py`, `tests/test_hand.py`, `tests/test_flood_bathtub.py`, `tests/test_vehicle_routing.py`, `tests/test_gtfs_reader.py`, `tests/test_transit_accessibility.py`, `tests/test_network_trace.py`, `tests/test_huff.py`, `tests/test_parcel_split.py`, `tests/test_portal_clients.py`, `tests/test_power_bi_export.py`, `tests/test_iso19115_export.py`, `tests/test_topology_rules.py`, `tests/test_geometry_edit_tools_live.py`, `tests/test_virtual_fields_live.py`, `tests/test_processing_model_gate.py`, `tests/test_pyqgis_call_arity.py`, plus one `*_live.py` per QGIS-facing package (auto-discovered by `tests/_live_modules.py`). Existing guards that must stay green on every package: `tests/test_plans.py`, `tests/test_release_docs_in_sync.py`, `tests/test_metadata_parses.py`, `tests/test_pyqgis_call_names.py`, the golden routing tests, the 385-prompt replay, `tools/ledger_guard.py`.

## Rollback

Per package: revert its pull request; each tool is registered by its own decorator and listed in the ledger, so reverting removes it cleanly, and `tests/test_tool_reachability.py` and the tool-schema snapshot (`tools/snapshot_tool_schema.py`) tell the reviewer exactly which names disappear. Per release: the previous GitHub release stays installable; the plugin zip is never replaced after publication (a defect gets a patch release). Persona re-ranking has a Settings switch `persona_rerank_enabled` (default on) that restores the 1.18.1 router order; the persona keys migrate back by keeping the old `USER_PROFILE_KEY` value untouched. A connector is disabled by its entry in `data_sources.json` (`"enabled": false`) without a release.

## Status log

- 2026-10-26: plan written from the master list and the owner's answers (all profiles planned; lens-not-gate persona model; one release per package; connectors: open sources, ACLED and ReliefWeb, Power BI). Nothing built. Questions Q1 to Q15 are open with the defaults above; R0 starts when the owner's 1.18.1 hand results (O-1) are returned.
