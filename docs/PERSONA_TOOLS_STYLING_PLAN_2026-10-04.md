# Persona framework: tools, data, styling and visualization plan (2026-10-04)

Source: the owner's "QGIS System Personas" document (15 personas: tasks, GIS functionalities, online data sources). Compared with what is in
this repository on `main` at `d6abd29` (190 registered tools, 792 registered tasks, four styling modules, two layout templates). A dated plan,
not a result. **Static reading only:** "have" means a tool exists for the step, not that it was hand-tested; nothing here was run, and the new
capabilities below are proposals, not promises. Supersede with a new doc rather than editing this one.

## 1. What the review found (the short version)

1. **The 15 personas already exist, but only as a prompt dropdown.** `core/services/prompt_refiner.py` has `PROFILE_LABELS` (the same 15 names as
   the document, in the same order) and a one-sentence `PROFILE_GUIDANCE` for each. The only thing they do is steer the optional, off-by-default
   "prompt refinement" rewrite. A second, unrelated concept, `onboarding_profile.ROLE_CHOICES` (7 roles), feeds the base system prompt. The two
   do not agree (for example "cartographer" and "emergency responder" have no persona; "defense_intel" has no role).
2. **Nothing else is persona-aware.** The tool router (`services/tool_router.py`, keyword top-40), the task register, the styling modules, the
   layout templates and the dashboards ignore which persona the user is.
3. **The task register is written from a humanitarian/NGO point of view.** 792 tasks in 37 categories, almost all of them framed around
   humanitarian programmes (a few, such as 16 remote sensing, 20 GIS database management, 21 spatial analysis, overlap with other personas);
   category 36 is engineering hydrology (1 task). Only **67 of the 190 tools** appear in any task, so 123 tools (65%) are invisible to task
   matching. No persona other than humanitarian has tasks written for it (agriculture, utilities, transport, real estate and research only
   overlap by accident, for example through 9 food security or 11 accessibility).
4. **Coverage is lopsided.** Humanitarian is well covered and was reviewed in detail (`HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md`,
   `HUMANITARIAN_TOOLS_CATALOGUE.md`). Generalist, logistics, agriculture (indices), engineering (partly) and disaster risk are partly covered.
   Public health, utilities, transport, urban planning, real estate, research and environment are mostly missing their *defining* capability.
5. **Four capability gaps unlock most of the personas** (section 4): spatial statistics, raster indices and time series, terrain and hydrology,
   and network/movement. All four can be built on numpy/GDAL/QGIS-native pieces already used here, and their core can be unit-tested without
   QGIS, which is the verification this environment allows.
6. **Styling is strong where a persona has been designed for** (humanitarian hazards, routing/access, task grids, rasters, labels) **and absent
   elsewhere.** There is no place that says "what does a health-rate map, a utility network or a land-cover change map look like".
7. **Two items in the document need an owner decision, not a build:** persona 15 (defense and intelligence) and the licensed or classified data
   sources (section 7).

## 2. What exists today

| Area | What is there | Persona awareness |
|---|---|---|
| Persona concepts | `PROFILE_LABELS` + `PROFILE_GUIDANCE` (15, prompt refiner only); `ROLE_CHOICES` (7, onboarding `.md` profile) | Two lists that do not match |
| Tools (190) | vector 43, raster 21, styling 14, humanitarian data 10, logistics 9, export 8, analysis 6, hazard 4, plus ~40 small groups (engineering 3, barrier 1, MCDA 1, survey 1, sampling 1, trigger 1, task grid 1, ...) | None |
| Task register | 792 tasks, `{id, cat, text, out, slots, tools, kw, acc, prod}` | No persona field; humanitarian-centric |
| Router | keyword scoring + `_TOOL_ALIASES`, top 40 of 190 | None; a semantic prototype was scoped, not built |
| Prompt | `build_system_prompt` with the onboarding profile (role, experience, style) | Role only, 7 values |
| Styling | `output_style` (roles, ramps, labels, algorithm outputs), `routing_style` (cost bands, reach, access), `humanitarian_style` (task grid, barriers, samples, hazards, diverging raster), `layout_style` (palette, access-map template), 14 styling tools, 4 representation tools | Humanitarian and routing only |
| Layouts | `standard` and `access_map` print templates, atlas export | None per persona |
| Dashboards | situation dashboard, temporal dashboard, generic HTML dashboard | Humanitarian |
| Data sources | HDX, geoBoundaries, OSM (Overpass/Geofabrik), Microsoft footprints, WorldPop, GDACS, NASA FIRMS/EONET, OCHA FTS, STAC *search* (Sentinel-2), geocoding, web search | Humanitarian; each guarded by the F22 size check and the egress gate |
| Governance | egress gate, layer sensitivity, provenance sidecar, schema contracts, P-code checks, do-no-harm obfuscation | Humanitarian-shaped |

## 3. The persona pack: how personas should work

A persona is a **lens, not a gate.** It changes defaults and ordering; it never hides or blocks a tool, and it never carries licensing or
tier logic (`CLAUDE.md` forbids tier-gating in this repo).

**One data file per persona** (`core/personas/<id>.json`, loaded by one small module; same style as `task_register.json`):

| Field | Used by |
|---|---|
| `id`, `label`, `aliases`, `summary` | the picker, the prompt |
| `guidance` (what to ask and what never to assert) | system prompt and the refiner (replaces `PROFILE_GUIDANCE`) |
| `workflows`: the document's tasks as named workflows with their tools in order | task matching, "what can you do for me" |
| `tool_priority` and `tool_aliases` | the router (re-rank only, never remove) |
| `task_ids` (slice of the register) | task matcher |
| `data_sources`: ids into a central source catalogue | data offers and the download guard |
| `style_profile` id | output styling (section 5) |
| `layout_templates`, `dashboard` | print and web outputs |
| `readiness`: per capability `covered` / `partial` / `missing` / `out_of_scope`, with the tool or the reason | the picker and `docs/PERSONA_CATALOGUE.md`, so the plugin says honestly what it can do for you |
| `guardrails`: method limits the model must state (for example "no discharge without a cited IDF value") | the response guard and prompt |

**Rules.** (1) One primary persona plus an optional secondary, set in Settings and the onboarding dialog, never inferred silently. (2) The 15
ids are the single list; the old 7 roles map onto them (`humanitarian_analyst`->`humanitarian`, `urban_planner`->`urban_planning`,
`researcher`->`research`, `emergency_responder`->`humanitarian` or `public_safety`, `cartographer`/`gis_student`/`other`->`general`);
experience level and answer style stay as they are. (3) Readiness is generated from the registry where possible (a tool name that no longer
exists fails a test) so the catalogue cannot drift. (4) A user's explicit instruction always beats a persona default, and a style the user
already changed is never overwritten (the per-project remembered style already does this).

## 4. Persona by persona

Legend: **Have** = tools that exist. **Gap** = what the document asks for that has no tool (priority H/M/L = how many personas need it and
how central it is to this one; effort S/M/L; "offline" = the core can be verified without QGIS). Data: **have / missing**.

| # | Persona | Have | Gap (priority, effort) | Data |
|---|---|---|---|---|
| 1 | **GIS Generalist** | format conversion (`add_layer_from_path`, `export_layer`, reproject, merge, join), `fix_geometries`, `diagnose_topology` (validity, slivers, overlaps; **not** gaps), schema contracts and P-code checks, dataset status, provenance sidecar, workflow presets, `execute_pyqgis_script` | Topology rules beyond overlaps (gaps, must-be-covered-by) **M, M**; ISO 19115 metadata **see 13**; model-builder style reusable workflows beyond presets **L, L** | have: HDX search, file loads. missing: generic open-data portals (CKAN, ArcGIS Hub, Socrata) **M, M** |
| 2 | **Humanitarian aid and crisis response** | the 792-task register, HDX/OSM/WorldPop/GDACS/FIRMS/FTS, H1-H6 tools, service areas and access, severity/JIAF-style scoring, task grid, survey aggregation, sitrep/dashboard | already itemised in the humanitarian gap analysis: Kobo/ODK pull, QField package, UNOSAT/damage loader, critical-link analysis | have most; missing: Kobo/ODK, ACLED (key), Maxar/Planet open-data STAC |
| 3 | **Engineering and infrastructure** | slope/aspect/hillshade/profile, `weighted_overlay_analysis`, `calculate_mcda_ranking`, `georeference_image`, rational-method peak flow, DMS parsing, mosaic/clip | Basin delineation and flow accumulation **H, M** (the hydrology tool still needs a basin from elsewhere); cut/fill volume from DEM difference **M, S**; contour lines **M, S**; IFC/Revit to CityGML and 3D rendering **L, out of reach** (needs FME or ifcopenshell, see section 7) | missing: OpenTopography/3DEP/Copernicus DEM, NHD/HydroSHEDS, SSURGO/SoilGrids |
| 4 | **Urban planning and local government** | overlay/zoning checks (`intersect_layers`, `spatial_join`), service areas, `estimate_population_exposure`, MCDA, HTML dashboard, print layouts | Scenario allocation of future land use **M, L**; parcel subdivision (split by area/line) **M, M**; urban heat island (needs land-surface temperature) **M, M**; line-of-sight **L, M**; public web-map publishing beyond the static HTML dashboard **M, L** | missing: cadastre/zoning are local files (supported by loading); drone orthomosaic loading works as a raster |
| 5 | **Logistics and supply chain** | `optimize_delivery_route` (a single-vehicle tour, not a VRP), `travel_time_matrix`, `optimal_hub_siting`, `location_allocation`, barriers, route incident risk, hazard feeds | **VRP with capacity and time windows H, L** (heuristic solver, no external dependency); weighted centre of gravity **M, S**; choke-point/critical-link analysis **H, M**; real-time telemetry **out of scope** (section 7) | missing: AIS/MarineTraffic and HERE/TomTom are licensed; user-supplied only |
| 6 | **Agriculture and food security** | `calculate_ndvi/ndwi/ndre`, `zonal_statistics`, `reclassify` via the allowlist, k-means classification, `export_layer`, STAC search | SAVI, EVI, NDMI, NBR **H, S** (same pattern as NDVI); multi-date stacks, seasonal comparison and anomaly **H, M**; management zones for variable-rate maps (k-means on an index with a minimum zone area) **M, M**; yield prediction **L, not recommended** without ground truth | have: Sentinel-2 search. missing: loading a scene (not just searching it), SoilGrids, CHIRPS/ERA5 |
| 7 | **Environment and natural resources** | change detection (two dates), unsupervised classification, buffers/overlays, weighted overlay for suitability | Supervised classification (the SAGA tool is absent in QGIS 4.2.2; needs a numpy classifier) **H, M**; land-cover from-to change matrix **H, S**; time-series raster statistics and trend **H, M**; habitat suitability is MCDA (have) with species-specific guardrails | missing: WDPA/IUCN protected areas, ESA WorldCover, climate grids |
| 8 | **Public health and epidemiology** | geocoding, `analyze_incident_trend`, `calculate_presence_gap`, `hotspot_analysis` (kernel density only), `aggregate_survey_indicator` (with small-number suppression), `obfuscate_sensitive_points`, charts | **Spatial scan statistic (Kulldorff, Monte Carlo) H, M**; global and local autocorrelation (Moran's I, Getis-Ord Gi*) **H, M**; rates, relative risk, standardised ratios and smoothing **H, M**; DHIS2/HMIS connector **M, M**. All four statistics are pure numpy, so they can be tested against published examples offline | missing: DHIS2 (needs credentials, goes through the egress gate), WHO/census tables as files |
| 9 | **Disaster risk and climate resilience** | GDACS/EONET/FIRMS, `evaluate_forecast_trigger`, scheduled workflows, `estimate_population_exposure`, `calculate_damage_exposure_severity`, hazard styling | Flood-depth footprint from a DEM and a water level ("bathtub") and HAND **H, M**; landslide susceptibility as a documented weighted overlay **M, S**; rainfall grids **M, M**. Real hydraulic simulation is **out of scope** (say so, do not fake it) | missing: CHIRPS/GPM/NOAA precipitation, OpenDRI/GFDRR layers (HDX covers some) |
| 10 | **Utilities, energy and water** | `diagnose_topology`, `find_nearest_features`, service areas, barriers | Geometric network + upstream/downstream trace with valve isolation **H, M** (QgsGraph is already used here); topology enforcement for networks (dangles, disconnected) **H, M**; anomaly isolation (DBSCAN exists) **L**; SCADA and live meters **out of scope** | missing: as-built CAD (DXF import is a QGIS capability, not a tool), smart-meter APIs (user-supplied) |
| 11 | **Transport and mobility** | `calculate_service_area` (multi-band isochrones), `travel_time_matrix`, `classify_facilities_by_access`, `population_access_gap`, `estimate_road_speeds` | **GTFS ingest and transit accessibility H, L**; origin-destination desire lines and flow maps **H, M**; walking and cycling profiles (speed presets) **M, S**; mobile-phone telemetry **out of scope** (privacy) | missing: GTFS feeds (open, per agency) |
| 12 | **Public safety and security** | `hotspot_analysis` + heatmap styling, `score_route_incident_risk`, routing with barriers, `obfuscate_sensitive_points` | Hotspot *tests* (Gi*, scan statistic) beyond a density surface **H, M** (shared with 8); viewshed **M, M**; 2D buffers exist, 3D blast radius does not **L**; CAD/RMS import is tabular loading | missing: high-resolution DSM; incident data is user-supplied and sensitive (egress gate applies) |
| 13 | **Research and academia** | provenance sidecar, workflow presets, `generate_report`, `execute_pyqgis_script` | ISO 19115 metadata record (extend the sidecar) **H, M**; OGC API Features publishing (generate a QGIS Server project and layer config) **M, L**; metadata validation **M, M**; Jupyter/R **out of scope** | missing: repository/SDI clearinghouse connectors (CKAN covers many) |
| 14 | **Real estate and site selection** | buffers + `estimate_population_exposure`, service areas as drive-time polygons, MCDA, OSM POI fetch, dashboard | **Huff gravity model H, M** (pure maths over a distance matrix that already exists); weighted centre of gravity **M, S**; revenue scenarios from explicit inputs only (no invented market rates) **M, S** | missing: census and spending indices (user-supplied), Google Places is licensed (user key only) |
| 15 | **Defense and intelligence** | change detection, slope, geocoding, web search | **Not planned as written. Needs an owner decision (section 7).** What is safe and useful (open-source conflict and access analysis for aid and security teams) belongs under personas 2 and 12 | ACLED needs a licence key; classified feeds must never be used with this plugin |

### Common shortfalls that cut across personas (not tied to one)
- **Task register coverage:** seed it with the document's three-to-four tasks per persona (about 50 tasks), then grow it the way category 36 was
  started; add a `persona` list to every task so the matcher can prefer the active persona's tasks.
- **123 tools unreachable from tasks:** a one-off job to attach each to the tasks that should use it (and a CI test that fails when a new tool is
  in no task and no persona).
- **Router:** persona re-rank first (cheap), the semantic router later if the scoped prototype is still wanted.

## 5. Styling and visualization system

Today styling decisions are spread over four modules and are decided per tool. The plan keeps those modules and adds one layer above them.

**Layers (each overrides the one above only when it has something to say):**
- **L0 global rules (exists, extend):** colour-blind-safe pairs (blue beside red, never red beside green), zero/NoData transparent, heavy-tailed
  rasters crowd stops toward the low end, labels only when a meaningful name field exists, basemap below analysis, helper layers hidden.
- **L1 role defaults (exists):** `output_style.vector_role_for`, `raster_kind_for`, algorithm profiles.
- **L2 persona style profile (new):** `style_profiles.py`, a pure registry `{persona: {role: spec}}` that only supplies the *choices* (palette
  family, class count, label units, symbol convention); the existing modules still draw. A user's remembered per-project style wins.
- **L3 layout templates (extend):** one named template per output type, not per persona, with personas choosing defaults.
- **L4 dashboards and charts (extend):** a small set of dashboard recipes reusing `generate_chart` and the HTML dashboard.

**What each persona's maps should look like** (conventions are named so they can be checked; where a regional standard varies it becomes a setting):

| Persona | Map looks to add | Layout / dashboard |
|---|---|---|
| Generalist | QA overlays: topology error markers (red/orange by kind), changed-vs-original diff | `qa_report` template (existing QA checklist output) |
| Humanitarian | have: hazard, task grid, access, barriers, samples, difference raster; add severity 1-5 ramp consistency and P-code labelling | have `access_map`; add `sitrep` (2-page, key figures, source line, do-no-harm note) |
| Engineering | contour (index + intermediate) over hillshade (multiply), basin outline and flow path, profile chart, cut/fill diverging raster | `engineering_sheet`: title block, datum and units, scale, north arrow, revision |
| Urban planning | categorical land use (a published palette to be chosen), zoning compliance pass/fail, service-catchment bands, heat ramp | `planning_board`; public web map |
| Logistics | have: cost bands, reach, access points; add per-vehicle categorical routes with stop sequence labels, depot/hub symbols, choke-point highlight | `route_plan` sheet with a stop table |
| Agriculture | NDVI/NDRE diverging (have), index classes with units, management zones (3-5 sequential classes with the rate in the legend), field boundaries as outlines | `field_report` per field (atlas) |
| Environment | selectable official land-cover palettes (ESA WorldCover, CORINE), change classes (loss / gain / stable), protected-area hatch | `change_report` before/after pair + change matrix chart |
| Public health | sequential single-hue rate maps (ColorBrewer), cluster outlines in a non-red contrasting colour, hatch for suppressed small numbers, never patient-level points (aggregate or obfuscate), uncertainty/confidence note | `epi_bulletin`; epidemic curve (`generate_chart`) + rate map |
| Disaster risk | hazard intensity ramps (have), exposed-population labels, scenario name and assumptions in the legend | `hazard_brief` with a "scenario, not forecast" line |
| Utilities | APWA uniform colour code as the *default setting* (blue water, green sewer, red electric, yellow gas, orange communications, purple reclaimed), traced segments highlighted, isolation valves as symbols | `outage_map` |
| Transport | isochrone bands (have), flow lines with width proportional to flow, stops and routes by mode | `access_map` variant, OD flow map |
| Public safety | density surface with the bandwidth stated in the legend, response-time bands, sensitive locations generalised | `patrol_brief` |
| Research | greyscale-safe ramps, journal figure sizes, source / CRS / date line on every figure, reproducibility appendix from the provenance record | `publication_figure` |
| Real estate | trade-area bands, probability (Huff) surface, site-score choropleth | `site_comparison`; BI-style dashboard |

**How it is built and checked:** pure palette and class-break functions with offline tests (including a colour-blindness simulation on every
categorical palette); renderer-level assertions in the CI live job (type, class count, colours, transparency, layer order); layouts rendered
to PNG in CI. As in the rc10 smoke test, **the owner looks at the real output**: each look ships with a screenshot checklist row in the
hand-test plan and is not called done until it has been seen.

## 6. Data-source catalogue

One central file (`core/agent/data_sources.json`) replaces knowledge scattered in tool descriptions: `{id, label, personas, kind (file / API /
STAC / feed), access (open / free key / licensed), licence, size class, egress class, cache folder, tool}`. The existing size guard (F22), the
cache folder and the egress gate read from it, and the persona picker shows what is available, what needs a key, and what is not supported.

Order by how many personas a source serves and how little it needs:
1. **STAC load** (not only search): Sentinel-2, Landsat, Copernicus DEM, ESA WorldCover. Serves 3, 4, 6, 7, 9, 12.
2. **Open-data portals** (CKAN, ArcGIS Hub, Socrata generic reader). Serves 1, 2, 4, 13.
3. **Terrain and hydrography:** Copernicus/OpenTopography DEM, HydroSHEDS/NHD, SoilGrids. Serves 3, 9, 7.
4. **Climate and rainfall:** CHIRPS, ERA5 subsets. Serves 6, 7, 9.
5. **Protected areas and land cover:** WDPA (licence terms to confirm), WorldCover. Serves 7.
6. **GTFS** feeds. Serves 11.
7. **DHIS2** and **Kobo/ODK** (credentials; always through the egress gate, never logged). Serves 8, 2.
8. **ACLED** (free key, strict terms). Serves 2, 12.

Licensed or closed sources (HERE, TomTom, Google Places, MarineTraffic/AIS, commercial Maxar/Planet, SCADA, mobile telemetry, classified
feeds) are **not integrated**: the plugin accepts a user-supplied file or user-supplied key and says so; it never bundles or resells them.

## 7. Decisions and boundaries that need the owner

1. **Persona 15 (defense and intelligence).** Terrain mobility for mechanised units, fusing classified imagery, and OSINT scraping for targeting
   are dual-use, and this plugin sends context to cloud models by default, which is incompatible with classified work. Recommendation: do not
   ship a "defense" persona as written; keep the id so existing settings do not break, map it to a **"conflict and access analysis (open
   sources)"** pack under personas 2 and 12 (access constraints, ACLED-style event density, route risk), and state in the picker that classified
   data must not be used with this plugin. Your call.
2. **One persona or several?** Recommendation: one primary + one optional secondary.
3. **Re-rank only, never hide tools?** Recommendation: yes (and never tier-gate).
4. **Dependency policy.** Everything above is planned on numpy/GDAL/QGIS-native (what the repo uses now). OR-Tools (VRP), scikit-learn
   (classification), scipy and rasterio would make some tools better but are not guaranteed in a QGIS install and the plugin has no installer for
   them. Recommendation: numpy-only first; optional accelerators later, detected at run time.
5. **Regional conventions:** the utility colour code (APWA is US; other regions differ) and the land-use palette. Needs your choice or a setting.
6. **IFC/Revit to CityGML and 3D digital twins:** needs FME or ifcopenshell and a 3D pipeline. Recommendation: out of scope; document the
   hand-off (export from the BIM tool, load in QGIS) instead.
7. **Prediction tools** (crop yield, scenario land use, revenue): only with explicit user inputs and a stated model; no default coefficients.
   Recommendation: build scenario *allocation* and *calculators*, not forecasts.

## 8. Phased plan

Each phase is one or a few PRs in the same shape as WP1-WP7: pure logic with offline tests, QGIS parts with live tests in CI (written without a
local QGIS, so CI is their first run), a catalogue entry, hand-test rows, and no issue closed before a hand pass.

| Phase | Content | Why this order | Size |
|---|---|---|---|
| **PP0 Framework** | persona pack loader and schema, unify the two persona lists, picker with readiness, router re-rank, `persona` field in the task register, seed tasks for personas 1,3-14, catalogue generator, CI test that every tool is in a task or persona | everything else hangs on it; no new analysis, so low risk | M |
| **PP1 Spatial statistics pack** (personas 8, 12, 2, 4, 7, 14) | Moran's I, Getis-Ord Gi*, Kulldorff scan with Monte Carlo, rates / relative risk / SMR / smoothing, small-number flag, cluster map + epidemic bulletin | serves the most personas; fully verifiable offline against published worked examples | L |
| **PP2 Indices and time series** (6, 7, 4, 9) | SAVI/EVI/NDMI/NBR, STAC load, multi-date stats and anomaly, from-to change matrix, numpy supervised classifier, management zones, LST if a thermal band is found | builds on the existing NDVI pattern and numpy raster code | L |
| **PP3 Terrain and hydrology** (3, 9, 12, 7, 10) | D8 flow direction and accumulation, basin delineation, HAND/bathtub flood footprint, contours, cut/fill, viewshed, mobility cost surface; link into the rational-method tool | closes the "needs a basin from elsewhere" limit | L |
| **PP4 Network and movement** (5, 11, 10, 2) | VRP heuristic with capacity and time windows, critical-link analysis, OD desire lines, GTFS accessibility, utility trace with valve isolation, walking profiles | reuses the routing code and the closure rule from WP3 | L |
| **PP5 Site selection and urban** (14, 4, 5) | Huff model, centre of gravity, trade areas, scenario allocation, parcel split | smaller, mostly formulas | M |
| **PP6 Connectors** | the catalogue in section 6, one source per PR with licence, size guard, cache and egress class | each is independent; do in the order of section 6 | M each |
| **PP7 Standards and publication** (13, 1) | ISO 19115 sidecar, metadata validation, QGIS Server / OGC API project generator, topology rule checks, publication figure layout | after the tools it documents exist | M |
| **Style track** (alongside) | `style_profiles.py` in PP0; one persona look + layout template per phase, shipped with the tools it serves, each with a screenshot row in the hand-test plan | a look without its tool is shelfware | S per phase |

**What I would do first, if you agree:** PP0, then PP1 with the public-health look, because it adds the most capability for the most personas
and is the part I can verify best from here.

## 9. Honesty notes
- Gap priorities and sizes are my estimates from reading the code; they have not been planned in detail or timed.
- "Offline" means the algorithm can be checked against known answers without QGIS. The QGIS-facing wiring still needs the live job and your hand check.
- Where a standard is named (APWA colours, ColorBrewer, ESA/CORINE palettes, FHWA limits) it should be checked against the current published version
  when the phase starts; I have not fetched them.
- The persona list in the document matches `PROFILE_LABELS` exactly, so existing user settings keep working; nothing in this plan changes
  behaviour until PP0 is built.
