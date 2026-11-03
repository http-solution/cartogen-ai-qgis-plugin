# All pending work, and the core analysis by professional profile (2026-10-26)

A dated review, not a result. It was written at the owner's request ("review all documentation and make a comprehensive list of all pending work, and add the core analysis that covers the profiles from the very first discussion: humanitarian aid, logistics, security, engineering, GIS and the rest"). It is read from the repository at `main` `fcad1b0` (v1.18.1), the GitHub issue list, and about 60 documents in `docs/`. Nothing was run for it. "Built" means code exists on `main`; it does **not** mean hand-tested. Where a statement rests on CI only, it says so.

Supersede this file with a new dated one rather than editing it.

## 0. Sources read

`docs/IMPLEMENTATION_TRACKER.md` (sections 1 to 4), `docs/BUG_TRACKER.md`, `docs/plans/PLAN-001` to `PLAN-022`, `docs/FEATURE_LEDGER.json`, `docs/OPEN_ISSUES_STATUS_2026-10-25_v2.md`, `docs/OWNER_ACTIONS_2026-10-12.md`, `docs/STATUS_DONE_VS_TESTED_2026-10-16.md`, `docs/ROADMAP_QGIS_COVERAGE_2026-10-14.md`, `docs/ROADMAP_COMPLETION_PLAN_2026-10-16.md`, `docs/QGIS_COVERAGE_GAP_ANALYSIS_2026-10-14.md`, `docs/qgis_coverage/SUMMARY.md`, `docs/PERSONA_TOOLS_STYLING_PLAN_2026-10-04.md` (the 15-persona framework, the "very first discussion"), `docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md`, `docs/HUMANITARIAN_TOOLS_CATALOGUE.md`, `docs/JIAF2_ANALYSIS_SUPPORT_PLAN_2026-10-04.md`, `docs/HYDROLOGY_ENGINEERING_TOOLS_2026-10-04.md`, `docs/HYDROLOGY_WATERSHED_DELINEATION_2026-10-14.md`, `docs/INTEGRATION_AUDIT_2026-10-16.md`, `docs/SELF_AUDIT_2026-10-23.md`, the 2026-09 scoping notes, and the tool registry (296 tools by decorator count).

Not re-read in full: the archive folder (frozen), the per-release smoke reports rc7 to rc22 (their open items were carried into the tracker and are listed below), and the two `.docx` privacy documents.

## 1. State in one table

| Measure | Value | Evidence level |
|---|---|---|
| Version on `main` | 1.18.1 (published as GitHub release `cartogen-ai-v1.18.1`) | verified on GitHub |
| Registered tools / approved Processing algorithms | 296 / 435 | code |
| QGIS actions (164 rows): covered / partial / missing / blocked | 113 / 32 / 17 / 2 | generated from the router; mostly CI only |
| Ledger entries | 83: 66 hand-verified or other, 5 partly, 12 "not verified" | `docs/FEATURE_LEDGER.json` |
| GitHub issues open | 2 (#362, #380) | GitHub |
| Plans | 22 files; 14 carry a stale status; PLAN-022 is on PR #443, not merged | `docs/plans/` |
| Hand-tested algorithms | 21 (rc46 run) | `docs/STATUS_DONE_VS_TESTED_2026-10-16.md` |
| Persona framework (PP0 to PP7) | **not started**; `core/personas/` does not exist | code |

## 2. The master list of pending work

IDs are new (`W-` for work, `O-` for an owner action) so they can be referenced and tracked. Priority: **P1** blocks a claim or a release, **P2** next, **P3** later or optional. "Owner" means it needs the owner's account, data, machine or decision; I cannot do it.

### A. Owner actions

| ID | Item | Why it is pending | Source |
|---|---|---|---|
| O-1 | Run `tools/layout_check_script.py` once in the QGIS console, then rows V1 to V9 of the 1.18.1 bundle; return the folder, `4_RESULTS.csv` and `cartogen_evidence` | Closes #362 and #380, proves the 12 CI-only 1.18.1 fixes on a real machine; gates W-30 | PLAN-021, bundle |
| O-2 | Paste the "CI-checked, not hand-tested" note into the 1.18.1 release | Releases cannot be edited from this session type (403) | PLAN-021 |
| O-3 | Decide: upload to plugins.qgis.org, and stable versus pre-release | Needs the owner's login; nothing is done for it | tracker 1.10, `STATUS_DONE_VS_TESTED` |
| O-4 | Unpublish the old GitHub Pages site (wiki replaced it) | Settings change only the owner can make | PLAN-019 |
| O-5 | JIAF validation blockers: a Flags dashboard export or country records; flag 6 historical table; the flag-3 zero case; thresholds sheet; one real filled Annex 4 file | Two blockers are carried in every JIAF tool result on purpose | JIAF2 plan section 11, task 69 |
| O-6 | HX4 credentialed integrations: Kobo/ODK, ACLED key, GloFAS/CHIRPS, Logistics Cluster, LandScan; ReliefWeb app name | Keys, licence terms, hosted-gateway question | gap analysis H10, task 67 |
| O-7 | Clean-profile install and in-place upgrade test of the exact release zip | Needs a human with a fresh QGIS profile | tracker 1.10 |
| O-8 | Answer the five PLAN-022 decisions (temporary-layer note, undo of rename/delete field, clean-profile row, stable versus pre-release, architecture items) | Product choices | PLAN-022 N6 |
| O-9 | Decide the open persona choices: one primary plus one secondary persona; lens-not-gate; utility colour code and land-use palette defaults | Needed before PP0 | persona plan section 7 |
| O-10 | Decide whether to publish a real stable repo/Pages/Marketplace presence beyond the wiki, and the Pro-tier gateway (`service/`) | Product and legal | CLAUDE.md, tracker 1.3 |
| O-11 | Close the open secret-scanning alert | Repository settings | `STATUS_DONE_VS_TESTED` |

### B. Verification debt (built, never hand-tested)

| ID | Item | Level today |
|---|---|---|
| W-1 | The 12 ledger entries marked "not verified" (PLAN-022 N2: add a `hand_row` to each) | CI only |
| W-2 | The 5 ledger entries marked "partly" | partly |
| W-3 | Wave E1 (8 algorithms), DXF export, Excel export, the 20 later routing additions, packages A to I of the roadmap | CI only. Only 21 algorithms were ever hand-tested |
| W-4 | End-to-end conversations: whether a real model chooses these tools from a plain prompt | Never measured. Router tests prove what is *offered*, not what is *chosen* |
| W-5 | Windows and macOS QGIS (live tests run on Linux Docker only) | Not tested; the Windows font fit of the layout footer can only be seen in the owner's run |
| W-6 | User data: large, messy, non-English, differently projected, database-backed | Not tested |
| W-7 | Numerical correctness of Processing outputs (raster, mixed, GRASS, mesh) | Smoke tests prove completion, not accuracy |
| W-8 | `delineate_watershed` on a real Copernicus DEM at the reported site (31 deg 01 min 47 N 35 deg 48 min E); compare with the city-planning engineer's report | Synthetic terrain only |
| W-9 | Real download and load of a full Geofabrik extract; OpenRouter prompt-cache `cached_tokens` on a second call | Doc-verified only |
| W-10 | The "intermittent empty elevation profile" (#379) was never reproduced; no cause is claimed | Open observation |

### C. Open issues

| ID | Item | State |
|---|---|---|
| W-11 | #362 animate, elevation profile, linked charts | Router offers the right tools; needs rows V4, V5, V6 (model answers) |
| W-12 | #380 plain requests answered by a wrong plan | 385-prompt replay: 34, then 7, now 2 (both right); needs rows V3, V7, V8 |

### D. Engineering hygiene (PLAN-022, work packages N1 to N6)

| ID | Item | Priority |
|---|---|---|
| W-13 | N1: refresh the 14 stale plan statuses; fold PLAN-020 into PLAN-021; mark PLAN-019 done | P2 |
| W-14 | N2: ledger `hand_row` field; guard that a "verified" entry names its row | P2 |
| W-15 | N3: sweep `IMPLEMENTATION_TRACKER.md` (2,746 lines; sections 1.19 to 1.24 appear twice, the list at the top is stale) and `BUG_TRACKER.md` | P2 |
| W-16 | N4: CI and release hygiene: Windows runner pin, `upload-artifact` version, a `status_note` input for `release.yml`, README test count | P3 |
| W-17 | N5: fix what the hand run finds as 1.18.2 | P1, starts after O-1 |
| W-18 | N6: owner decisions (see O-8) | P2 |

### E. QGIS coverage still missing (17 rows) and partial (32 rows)

Missing (from `docs/qgis_coverage/SUMMARY.md`):

| ID | Row | Size |
|---|---|---|
| W-19 | Vertex edit (add, move, delete vertices) | M |
| W-20 | Add part / ring, fill ring, delete part or ring | M |
| W-21 | Reshape, offset curve, chamfer/fillet, reverse line, trim/extend | M |
| W-22 | Copy and paste selected features between layers | S |
| W-23 | Identify a feature by coordinate (a map click is not possible in a chat) | S |
| W-24 | Run a Processing model / batch process / Processing script | M, needs a safety rule |
| W-25 | In-place layer modification with an algorithm | M |
| W-26 | Virtual fields, conditional formatting, forms, widgets, constraints, default values | L |
| W-27 | Layer actions and map tips; auxiliary storage | M |
| W-28 | Merged-features, inverted-polygon, 2.5D, embedded and no-symbol renderers | S |
| W-29 | Pyramids / overviews, raster attribute tables, identify a cell value | S |
| W-30 | Datum transformations, custom CRS, ellipsoid, units; canvas decorations; 3D map view | M, 3D needs a CI image with the module |
| W-31 | QGIS Server publishing; layer authentication storage | Out of scope or owner decision |

Partial rows worth planning (each names its limit in the summary): resample and translate, raster histogram and band statistics, image classification, viewshed/watershed/flow accumulation/ruggedness (watershed itself is built), group-by and aggregate, live joins and relations, labels, diagrams, symbol layers, style manager, reports, snapping and topology checks, temporal controller, elevation profile, GPS, mesh, PostGIS-only databases.

Processing waves (PLAN-005, PLAN-006, status "in progress"):

| ID | Item |
|---|---|
| W-32 | PLAN-005 remaining waves of the 60 file-writing algorithms (E1 built, rest not) |
| W-33 | PLAN-006 E2: the capability probe, E2b and E2a (info reports, plots, remaining exports) |
| W-34 | 16 expression-taking algorithms need expression screening before listing; 17 path-reading ones need per-algorithm review; 34 need layer types now partly loadable (mesh, point cloud, 3D tiles); GRASS (307) optional |
| W-35 | Argument-list and return-type checks against the QGIS 4.2.3 reference (the name check cannot find this class of bug) |

### F. Humanitarian and analysis carry-overs

| ID | Item | Source |
|---|---|---|
| W-36 | HX4 tools once keys exist (O-6): Kobo/ODK pull, ACLED, GloFAS/CHIRPS, Logistics Cluster, LandScan | gap analysis H10 |
| W-37 | JIAF: re-check flag formulas and Annex 4 reader once O-5 material arrives; closing the blockers is the owner's decision | JIAF2 |
| W-38 | Open since rc22: reply-quality failures that are model behaviour (invented facts, wrong country in the JIAF set-up) have no code fix; keep as eval rows | tracker 1.24 |
| W-39 | `travel_time_matrix` still about 8 minutes on a whole country; `optimize_delivery_route` builds the graph per stop pair; assumed speeds by road class (only 0.9 percent of Jordan's roads carry `maxspeed`) | tracker section 1 |
| W-40 | Raster-unit check (people per cell versus density) in population exposure; requiring or reprojecting points into the admin CRS in damage counting; `analysis_tools.py` score-write labels | WP2 notes |
| W-41 | Task-runner callbacks at unload, and the fallback completion marshalled to the Qt thread (#167 tail) | tracker WP6 |
| W-42 | `find_region()` named the wrong country for a Jordan coordinate; needs live Geofabrik data | tracker 1.15 |
| W-43 | "Smart mapping": output layers still pile up across a long multi-step session beyond the one fixed mechanism | tracker 1.16 |

### G. Architecture and deferred decisions

| ID | Item | State |
|---|---|---|
| W-44 | Agent pipeline redesign (intent, inspector, planner stages) | tracker 1.5, owner decision |
| W-45 | Deterministic plan, validate, execute model (typed step schema as a gate) | tracker 1.6, owner decision |
| W-46 | Standard project folder architecture (immutable raw data) | tracker 1.7, product opinion |
| W-47 | `task_matcher` keyword normalisation favours short task definitions | tracker 1.8, partly mitigated by routing work in 1.18.1 |
| W-48 | Chunked k-means for very large rasters (guard shipped, chunking not) and further GUI-thread offloading beyond polygonize and zonal stats | A14, A15 |
| W-49 | Scoped and **not recommended** (record only): LanceDB/Chroma memory, Instructor/Outlines, RestrictedPython, Presidio egress scan, semantic router. Ollama `keep_alive` deliberately not done | `docs/*_SCOPE_*.md` |

### H. Persona programme (PP0 to PP7, none started)

Detailed in section 3. Listed here so the master list is complete.

| ID | Phase | Size |
|---|---|---|
| W-50 | PP0 framework: persona pack loader, one list of 15, picker with honest readiness, router re-rank, `persona` field in the task register, seed tasks, catalogue generator, CI check that every tool is in a task or persona | M |
| W-51 | PP1 spatial statistics: Moran's I, Getis-Ord Gi*, Kulldorff scan with Monte Carlo, rates / relative risk / SMR / smoothing, small-number flag | L |
| W-52 | PP2 indices and time series: SAVI/EVI/NDMI/NBR, STAC *load*, multi-date statistics and anomaly, from-to change matrix, management zones | L |
| W-53 | PP3 terrain and hydrology (rest): HAND / bathtub flood footprint, cut and fill, viewshed tool, mobility cost surface | L |
| W-54 | PP4 network and movement: VRP with capacity and time windows, OD desire lines, GTFS accessibility, utility trace with valve isolation, walking and cycling profiles | L |
| W-55 | PP5 site selection and urban: Huff model, centre of gravity, trade areas, scenario allocation, parcel split | M |
| W-56 | PP6 connectors, one per PR: STAC load, open-data portals (CKAN, ArcGIS Hub, Socrata), DEM/hydrography/soils, CHIRPS/ERA5, WorldCover/WDPA, GTFS, DHIS2, Kobo/ODK, ACLED | M each |
| W-57 | PP7 standards and publication: ISO 19115 sidecar and validation, OGC API / QGIS Server project generator, topology rule checks, publication figure layout | M |
| W-58 | Style track: `style_profiles.py` and one persona look plus layout template per phase (engineering sheet, planning board, route plan, field report, change report, epi bulletin, hazard brief, outage map, patrol brief, publication figure, site comparison) | S each |

## 3. Core analysis by profile

### 3.1 Method and what changed since the first discussion

The first discussion produced the owner's "QGIS System Personas" document: **15 personas**, each with tasks, GIS functions and online data sources. `docs/PERSONA_TOOLS_STYLING_PLAN_2026-10-04.md` compared it with the code. Its findings still hold, with the updates below.

1. **A persona is still only a dropdown.** `prompt_refiner.PROFILE_LABELS` has the same 15 names and a one-sentence guidance each, used only by the optional prompt rewrite. The router, task register, styling, layouts and dashboards ignore the persona. `core/personas/` does not exist.
2. **Only humanitarian has persona-built tools.** Engineering and logistics have since gained real tools (below); the other 12 are still *generic-only*: a skilled user can reach the right general tool, but nothing was built for that profile.
3. **Status vocabulary** (unchanged): **built** (tools, look and output were made for the persona), **partly built**, **generic-only**, **not built**, **out of scope**.
4. **The four capability gaps that unlock most personas are still open:** spatial statistics, raster indices and time series, terrain and hydrology (partly closed: basin delineation exists), and network and movement.
5. **Data catalogue and connectors:** only humanitarian sources exist. None of the persona sources in the first discussion (CHIRPS, WorldCover, SoilGrids, GTFS, DHIS2, CKAN) are connected.

Honesty note: a "tool exists" statement comes from reading names and descriptions in the registry. None of the persona tools below was exercised by the owner against persona tasks, except where the table says "hand-tested".

### 3.2 Profile 2: humanitarian aid and crisis response (status: **built**, partly hand-tested)

**Core questions:** Where are the affected people and what do they need? Which areas are reachable? How severe is it, and how should limited funds be allocated? What changed since the last report? What can I publish safely?

| Need | What exists (code) | Hand-tested? |
|---|---|---|
| Base data | `search_hdx_datasets`, `fetch_hdx_admin_boundaries`, `fetch_geoboundaries`, `fetch_osm_features`, `fetch_building_footprints`, `fetch_worldpop_population`, `fetch_fts_funding_data`, `fetch_usgs_earthquakes`, `fetch_ucdp_conflict_events`, `find_incident_reports`, web research tools with sources | Partly (rc46/rc48 rows) |
| Hazard feeds and triggers | `fetch_gdacs_disaster_alerts`, `fetch_nasa_active_fires`, `fetch_nasa_eonet_events`, `evaluate_forecast_trigger`, `generate_situation_dashboard` | Feeds partly; trigger rule CI only |
| Exposure and need | `estimate_population_exposure`, `calculate_population_in_need`, `calculate_severity_index`, `calculate_presence_gap`, `calculate_damage_exposure_severity`, MCDA with stability check, allocation envelope | CI only |
| Access | service areas, travel-time matrix, `classify_facilities_by_access`, `population_access_gap`, barriers with road closure | rc46 partly |
| Field data | task grid for HOT-style mapping, sampling frame, survey aggregation with small-n suppression, table importers (IPC, INFORM, UNOSAT) | CI only |
| Strategy | JIAF 2 tools: inputs, preliminary calculation, decisions, patterns, finalise | Reproduced on the owner's real Yemen files; **two validation blockers open (O-5)** |
| Output | `sitrep` and `access_map` templates, OCHA-style template and branding profile (PLAN-014), looks for hazard, severity, exposure and rank | Layout partly; new Windows font fit unseen |
| Governance | egress gate, sensitivity, P-code checks, do-no-harm obfuscation, provenance sidecar | Mixed |

**Pending:** O-5, O-6 (Kobo/ODK, ACLED, GloFAS/CHIRPS, Logistics Cluster, LandScan), QField package, damage-assessment loader beyond table import, critical-link performance on national networks, W-39 to W-43, and PP1 spatial statistics (hotspot *tests*, not just density) for needs assessment.

### 3.3 Profile 5: logistics and supply chain (status: **partly built**)

**Core questions:** Where should hubs go? Which vehicle serves which stops in which order within capacity and time? Which roads, if cut, hurt most? How long, by what mode?

| Need | What exists | Gap |
|---|---|---|
| Hub siting and allocation | `optimal_hub_siting`, `location_allocation` | Made for humanitarian access; no weighted centre of gravity |
| Single route | `optimize_delivery_route` (one tour; builds the graph per stop pair) | **No VRP**: no several vehicles, capacity or time windows (W-54, H priority, L effort, heuristic solver without OR-Tools, per the accepted no-new-dependency rule) |
| Time and reach | `calculate_service_area`, `travel_time_matrix`, `estimate_road_speeds` | `travel_time_matrix` about 8 minutes country-wide; assumed speeds by road class not applied (W-39) |
| Disruption | `apply_network_barriers`, closed-road rule, `analyze_critical_links`, `score_route_incident_risk` | Critical-link is a dependence screen, not a closure simulation |
| Output | cost-band and reach looks, route layers | No per-vehicle categorical routes with stop labels; no `route_plan` sheet with a stop table |
| Data | OSM roads, Geofabrik local data offer | AIS, HERE, TomTom, telemetry are licensed or out of scope: user-supplied files only |

**Next:** VRP heuristic (PP4), then a `route_plan` layout and stop table, then the speed-by-class change (needs the owner's go because it changes results).

### 3.4 Profile 12: public safety and security (status: **generic-only, with real ingredients**)

(Profile 15, defence and intelligence, was accepted by the owner on 2026-10-04 as **not built as written**; it maps to an open-source conflict and access analysis pack under profiles 2 and 12, and the picker must say that classified data must never be used with this plugin.)

**Core questions:** Where do incidents cluster and is the cluster real? Which routes and areas are risky? What can be seen from a point? Who must not be exposed in the output?

| Need | What exists | Gap |
|---|---|---|
| Incident data | `find_incident_reports` (sources named, no model-typed coordinates), `fetch_ucdp_conflict_events`, `add_incident_point`, CSV/XY loading | ACLED needs a key (O-6); user incident files are sensitive and pass the egress gate |
| Trend and risk | `analyze_incident_trend`, `score_route_incident_risk`, `forecast_trend` | Hotspot is density only |
| Hotspot | `hotspot_analysis` plus heatmap style | **No significance test** (Getis-Ord Gi*, Kulldorff scan; shared with profile 8, W-51) |
| Visibility | viewshed is reachable as a Processing algorithm in the routing data; the coverage row is PARTIAL | No dedicated tool, no DSM source, no response-time bands |
| Protection | `obfuscate_sensitive_points`, layer sensitivity, small-n suppression, do-no-harm wording | Sensitive-location generalisation in the output look not defined |
| Output | none persona-specific | `patrol_brief` layout, density legend with bandwidth stated |

**Boundaries:** no 3D blast radius; no classified feeds; no individual-level surveillance products. Say so in the picker.

### 3.5 Profile 3: engineering and infrastructure (status: **partly built**, more than on 2026-10-04)

**Core questions:** What is the catchment, slope, flow length and peak flow at a point? How much cut and fill? What does the terrain profile along a corridor look like? Where do I get a DEM and how do I document datum and units?

| Need | What exists | Hand-tested? |
|---|---|---|
| DEM | `fetch_dem` (Copernicus 30 m; showcase scenario S1) | Reached from CI; real DEM not seen by the owner |
| Basin | `delineate_watershed` (priority-flood fill, D8, accumulation, pour-point snapping, longest path, area, H, slope; window capped at 400,000 cells) | Synthetic terrain and a CI live test only (W-8) |
| Peak flow | `parse_dms_location`, `assess_watershed_hydrology_request`, `calculate_rational_watershed_peak_flow` (Kirpich Tc; Rational Method; cites FHWA and NRCS limits; every reply labelled preliminary, requires local engineering review) | Unit tests; the quoted limits were never re-fetched |
| Terrain | slope, aspect, hillshade, `generate_contours`, `elevation_profile` | Profile partly; intermittent empty profile unexplained (W-10) |
| Output | no `engineering_sheet` (title block, datum, units, revision) | Not built |

**Pending:** cut and fill from a DEM difference (S), HAND / bathtub flood footprint (M), IDF/rainfall source (CHIRPS/NOAA, connector), SoilGrids/SSURGO for runoff coefficients, engineering look and sheet, hydrograph methods beyond Rational. Out of scope by decision: IFC/Revit to CityGML and 3D twins (document the hand-off), real hydraulic simulation (say so, never fake it), design values without a cited source.

### 3.6 Profile 1: GIS generalist (status: **generic-only, strongest base**)

**Core questions:** Can I convert, repair, join, reproject and QA data quickly, and prove what I did?

| Need | What exists | Gap |
|---|---|---|
| Data in and out | add by path (containers, rasters, zip/KMZ, XYZ/WMS/WMTS/WFS/vector tiles/point cloud/3D tiles), Save As, package, DXF and spreadsheet export, QLR | W-31/W-26 items; generic portals (CKAN, ArcGIS Hub, Socrata) |
| Repair and QA | `fix_geometries`, `diagnose_topology` (validity, slivers, overlaps), QA checklist, schema contracts, P-code validation, dataset status | Topology rules beyond overlaps (gaps, must-be-covered-by) |
| Processing | 435 approved algorithms, discovery by description (60 percent in the first 15 on a 40-prompt offline test) | W-24 models/batch, W-25 in-place edits |
| Editing | attribute edit, field operations, selection, move/rotate/scale, merge, split, undo (including a new field) | W-19 to W-21 geometry editing |
| Provenance | provenance sidecar, workflow presets, scheduled workflows | ISO 19115 record (W-57) |

The generalist is the persona the existing QGIS roadmap serves most directly; section 2.E is effectively its backlog.

### 3.7 The other profiles in brief

Status is **generic-only** unless stated. "Existing" = general tools a skilled user can combine. All gap sizes are my estimates, unplanned.

| # | Profile | Existing | Core gap (priority, size) | Data to connect |
|---|---|---|---|---|
| 4 | Urban planning and local government | overlay, service areas, exposure, MCDA, dashboards, layouts | Scenario allocation of land use (M, L); parcel split by area or line (M, M); urban heat (needs LST) (M, M); public web map beyond the static dashboard (M, L) | Local cadastre and zoning files (loading works) |
| 6 | Agriculture and food security | `calculate_ndvi`, `calculate_ndwi`, `calculate_ndre`, zonal statistics, unsupervised and supervised classification, STAC search | SAVI/EVI/NDMI/NBR (H, S); multi-date stack, seasonal anomaly (H, M); management zones (M, M); yield prediction is **not recommended** | STAC *load*, SoilGrids, CHIRPS/ERA5 |
| 7 | Environment and natural resources | change detection, classification, weighted overlay | From-to change matrix (H, S); time-series trend (H, M); species-specific habitat guardrails | WorldCover, WDPA (licence to confirm), climate grids |
| 8 | Public health and epidemiology | geocoding, `analyze_incident_trend`, presence gap, small-n suppression, obfuscation, charts | **Moran's I, Getis-Ord Gi*, Kulldorff scan with Monte Carlo, rates, relative risk, SMR and smoothing (H, M each)**, all pure numpy and checkable against published examples; epidemic bulletin layout | DHIS2 (credentials), census tables as files |
| 9 | Disaster risk and climate resilience | GDACS/EONET/FIRMS, triggers, exposure, damage severity, hazard looks | Flood footprint from a DEM and level, HAND (H, M); landslide susceptibility as a documented weighted overlay (M, S); rainfall grids (M, M). Hydraulic simulation is out of scope | CHIRPS, GPM, NOAA, GFDRR layers |
| 10 | Utilities, energy and water | `diagnose_topology`, nearest features, service areas, barriers | Network trace upstream/downstream with valve isolation (H, M, uses the graph code already there); network topology enforcement (H, M); APWA colour code as a *default setting* | As-built CAD (DXF import exists), meter APIs user-supplied; SCADA out of scope |
| 11 | Transport and mobility | service-area isochrones, matrix, access classification, speeds | GTFS ingest and transit accessibility (H, L); origin-destination flow maps (H, M); walking/cycling profiles (M, S) | GTFS feeds; mobile telemetry out of scope (privacy) |
| 13 | Research and academia | provenance sidecar, presets, reports, PyQGIS script in an isolated worker | ISO 19115 metadata (H, M); OGC API / QGIS Server project generation (M, L); publication figure layout | CKAN-style repositories |
| 14 | Real estate and site selection | buffers, exposure, service areas, MCDA, POI fetch, dashboard | Huff gravity model (H, M; pure maths over the existing distance matrix); centre of gravity (M, S); trade areas; scenarios from explicit inputs only | Census and spending indices (user-supplied); Google Places licensed |
| 15 | Defence and intelligence | change detection, slope, geocoding, web search | Not built as written (see 3.4) | ACLED (key); classified data must never be used |

### 3.8 Cross-cutting findings

1. **Reachability, not only capability.** On 2026-10-04, 123 of 190 tools were in no task and so invisible to task matching. HX2 and the 1.18.x routing work fixed this for humanitarian tools; no CI test yet fails when a new tool is in no task and no persona (part of PP0).
2. **The same four primitives feed many profiles.** Spatial statistics serves 2, 4, 7, 8, 12, 14. Indices and time series serve 4, 6, 7, 9. Terrain and hydrology serve 3, 7, 9, 10, 12. Network and movement serve 2, 5, 10, 11. Build the primitive once; add persona looks and layouts on top.
3. **Looks and layouts are the visible half.** Humanitarian and routing have looks; every other profile needs its map conventions (for example ColorBrewer rate maps for health, APWA utility colours, journal figure sizes for research) and a named layout, each with a screenshot row in the hand test. A look without its tool is shelfware, and the reverse is true too.
4. **Standing rules for all profiles** (accepted 2026-10-04): a persona is a lens, not a gate, and never carries tier logic (CLAUDE.md forbids it); numpy/GDAL/QGIS-native only, no OR-Tools or scikit-learn for now; licensed data (HERE, TomTom, Google Places, AIS, Maxar, Planet, SCADA) is user-supplied only; no figure without a supplied source (cholera, famine, funding, yield, revenue); every result states its method and limits.
5. **Every profile needs honest readiness text.** The picker should show built / partly / generic-only / not built, generated from the registry so it cannot drift (PP0).

## 4. Suggested order

The rule from the owner's recent feedback applies: no more hand-test rounds that find avoidable defects. So verification goes first and new capability comes in plans that each ship their own hand row.

1. **Now (no new code):** O-1 results, O-2, and the owner's answers on O-8 and O-9. Merge PR #443.
2. **Next (PLAN-022):** N1 to N4 (W-13 to W-16), then W-17 from the hand results; close #362 and #380 if rows V3 to V8 pass.
3. **Then one plan for PP0** (framework and honest readiness): it changes no analysis and unlocks every profile. Write it as PLAN-023 with its guard tests before building.
4. **Then PP1 (spatial statistics) first.** It serves the most profiles (2, 4, 7, 8, 12, 14), is checkable offline against published examples, and is the biggest gap for health and security. Ship it with the public-health look and an `epi_bulletin` layout and a hand row.
5. **Then PP3 rest (flood footprint, cut and fill)** for engineering and disaster risk, and **PP4 (VRP, OD flow)** for logistics and transport.
6. **In parallel, the cheap QGIS rows** (W-22, W-23, W-28, W-29) as one small package; the geometry-editing rows (W-19 to W-21) as a second.
7. **Connectors (PP6)** one per PR as keys and licence answers arrive; none before O-6 and the catalogue file exist.

## 5. What this review did not do

- It did not run anything; counts come from the generated coverage summary, the ledger and decorator counts.
- Sizes and priorities are estimates from reading, not timed work.
- Items in the archive and in old smoke reports were taken from the tracker's carry-over, not re-read.
- Standards named for styling (APWA, ColorBrewer, ESA/CORINE palettes, FHWA limits) must be checked against current published versions when each phase starts.
- No tracker, plan or ledger entry was changed by this document; W- and O- IDs are proposals until the owner agrees them.
