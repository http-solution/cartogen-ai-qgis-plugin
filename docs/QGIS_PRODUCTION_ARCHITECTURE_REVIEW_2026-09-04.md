# QGIS Production Architecture Review — 2026-09-04

This document records a 27-point architectural review Baron supplied on
2026-09-04 proposing a "QGIS-first production standard" for Cartogen AI --
centered on making QGIS Processing algorithms the default execution path
(with PyQGIS as a controlled fallback), and adding project-architecture,
QA-gate, schema-contract, provenance, and agent-decision-loop layers that
don't currently exist -- and maps it against what the live source tree
actually does today, verified file-by-file rather than assumed, consistent
with this project's evidence-before-assertion rule.

Companion documents: `docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md` covers
humanitarian *content/compliance* standards (P-codes, symbology, layout,
metadata) for map products. This document is about the *engineering
architecture* underneath those products -- execution model, sandboxing,
QA state, provenance. The two overlap at a few points (P-codes, incident
coding, layout metadata) and are cross-referenced below where they do.

## A. The proposal (verbatim, as supplied)

> Your framework is already broad, but for a QGIS-first production standard I would strengthen it in five places: reproducibility, QGIS project architecture, QA gates, Processing-framework automation, and the boundary between the AI agent and QGIS itself.
>
> The biggest technical correction is architectural: the agent should not default to generating arbitrary PyQGIS scripts. Most operations should first resolve to an allow-listed QGIS Processing algorithm with validated parameters. PyQGIS should be the controlled fallback for operations that cannot be expressed through Processing. That makes the system safer, easier to audit, more portable across QGIS versions, and easier to test.
>
> I would restructure Sections 3–8 around the following QGIS-native production model.
>
> **Revised QGIS operational architecture**
>
> ```
> ┌──────────────────────────────────────────────────────────────────────────────┐
> │                 HUMANITARIAN QGIS PRODUCTION ARCHITECTURE                   │
> ├──────────────────────────────────────────────────────────────────────────────┤
> │                                                                              │
> │  1. MISSION SPECIFICATION                                                    │
> │     AOI │ Audience │ Scale │ Theme │ Sensitivity │ Deliverables             │
> │                              │                                               │
> │                              ▼                                               │
> │  2. DATA ACQUISITION                                                        │
> │     HDX │ COD │ OSM │ STAC │ Kobo │ QField │ CSV │ GeoPackage │ PostGIS     │
> │                              │                                               │
> │                              ▼                                               │
> │  3. STAGING / NORMALIZATION                                                  │
> │     CRS → Geometry → Schema → P-Code → Temporal → Metadata → PII            │
> │                              │                                               │
> │                              ▼                                               │
> │  4. QA GATE                                                                  │
> │     Geometry │ Topology │ CRS │ Completeness │ Join │ Temporal │ Provenance  │
> │                              │                                               │
> │                              ▼                                               │
> │  5. QGIS PROCESSING                                                         │
> │     Native │ GDAL │ GRASS │ Network │ Raster │ Vector │ Models              │
> │                              │                                               │
> │                              ▼                                               │
> │  6. ANALYTICAL PRODUCTS                                                     │
> │     Exposure │ Accessibility │ Damage │ Coverage │ Gaps │ Prioritization     │
> │                              │                                               │
> │                              ▼                                               │
> │  7. CARTOGRAPHIC ENGINE                                                     │
> │     QML │ PAL │ Expressions │ Themes │ Rules │ Scale Visibility             │
> │                              │                                               │
> │                              ▼                                               │
> │  8. LAYOUT ENGINE                                                           │
> │     QPT Templates │ Atlas │ Tables │ Insets │ Legends │ Dynamic Metadata    │
> │                              │                                               │
> │                              ▼                                               │
> │  9. VALIDATION GATE                                                         │
> │     Map QA │ Data QA │ Classification QA │ Layout QA │ Disclosure Review    │
> │                              │                                               │
> │                              ▼                                               │
> │ 10. PUBLICATION                                                             │
> │     PDF │ GeoPDF │ PNG │ SVG │ GeoPackage │ MBTiles │ COG │ QGIS Server     │
> │                              │                                               │
> │                              ▼                                               │
> │ 11. PROVENANCE / AUDIT                                                      │
> │     Inputs │ Parameters │ Algorithms │ QGIS Version │ Outputs │ Checksums    │
> │                                                                              │
> └──────────────────────────────────────────────────────────────────────────────┘
> ```
>
> ### 1. Add a formal QGIS project architecture
>
> Your framework discusses data and processing extensively but not enough about how the .qgz project itself is engineered. For operational deployment, this should be a first-class standard.
>
> I recommend a mandatory project structure such as:
>
> ```
> PROJECT_ROOT/
> │
> ├── project/
> │   ├── humanitarian_mapping.qgz
> │   └── templates/
> │       ├── sitrep_A3.qpt
> │       ├── operational_A4.qpt
> │       └── atlas_admin2.qpt
> │
> ├── data/
> │   ├── 00_raw/              # Immutable source data
> │   ├── 10_staging/          # Normalized/reprojected
> │   ├── 20_processed/        # Analysis outputs
> │   ├── 30_reference/        # CODs, gazetteers, P-codes
> │   └── 40_raster/
> │
> ├── styles/
> │   ├── boundaries.qml
> │   ├── settlements.qml
> │   ├── humanitarian_points.qml
> │   └── hazards.qml
> │
> ├── models/
> │   └── humanitarian_pipeline.model3
> │
> ├── scripts/
> │   ├── processing/
> │   ├── atlas/
> │   └── validation/
> │
> ├── exports/
> │   ├── pdf/
> │   ├── geospatial/
> │   ├── web/
> │   └── field/
> │
> ├── metadata/
> │   ├── sources.csv
> │   ├── processing_log.json
> │   └── qa_report.json
> │
> └── logs/
> ```
>
> The critical principle should be:
>
> > Raw source data is immutable.
>
> The agent, Processing models, and analysts operate on staging or derived datasets. This dramatically reduces the chance of accidental source corruption.
>
> For portable projects, use relative paths wherever possible.
>
> ### 2. Introduce explicit QA gates
>
> Currently QA appears throughout the framework, but it should be treated as a state transition.
>
> A dataset should not simply flow from ingestion into analysis.
>
> Use:
>
> ```
> INGESTED
>     ↓
> STAGED
>     ↓
> VALIDATED
>     ↓
> ANALYSIS_READY
>     ↓
> CARTOGRAPHY_READY
>     ↓
> PUBLICATION_READY
> ```
>
> Each transition has tests. For example:
>
> | Gate | Mandatory validation |
> |---|---|
> | Ingestion → Staging | source available, CRS identified, timestamp captured |
> | Staging → Analysis | valid geometry, projected CRS where required, schema validated |
> | Analysis → Cartography | output count plausible, joins validated, NULLs inspected |
> | Cartography → Layout | classifications validated, labels checked, scale visibility tested |
> | Layout → Publication | legend, scale, sources, date, CRS, disclaimer, AOI checked |
> | Publication → Release | disclosure classification and sensitive-data review |
>
> The agent should refuse to silently bypass failed gates.
>
> ### 3. Make CRS handling operation-aware
>
> Your rule about EPSG:4326 is directionally correct but too absolute. The real rule should be:
>
> > CRS selection must be determined by the spatial operation, geographic extent, and required accuracy.
>
> | Operation | Preferred CRS |
> |---|---|
> | Web/API interchange | EPSG:4326 |
> | Web tiles | EPSG:3857 |
> | Local distance/buffering | Appropriate local projected CRS |
> | Area comparison across large regions | Equal-area CRS |
> | Local tactical mapping | UTM/local national grid |
> | Global raster analytics | Dataset-native/equal-area CRS where appropriate |
>
> Also, don't hard-code 32636/32637 based simply on "Levant." The agent should calculate the suitable UTM zone from the AOI centroid where UTM is appropriate. A useful agent rule is:
>
> ```
> IF operation requires distance/area:
>     inspect source CRS
>     inspect AOI extent
>     determine suitable projected CRS
>     estimate distortion
>     reproject working copy
>     record transformation
> ELSE:
>     preserve native CRS unless transformation is necessary
> ```
>
> That is much more robust than simply rejecting EPSG:4326.
>
> ### 4. Expand geometry QA beyond fixgeometries
>
> `native:fixgeometries` is useful, but geometry repair alone is not topology validation. Your pipeline needs separate tests for geometry validity vs. topology validity.
>
> For polygons, check: invalid geometries, overlaps, unintended gaps, duplicate geometries, slivers, multipart anomalies, empty geometries, ring problems, minimum polygon area, administrative containment.
>
> For networks: disconnected edges, dangling lines, duplicate segments, invalid intersections, missing nodes, direction inconsistencies, speed anomalies, isolated network components.
>
> For points: duplicate coordinates, points outside AOI, impossible coordinates, missing P-Codes, spatial/admin disagreement.
>
> This is particularly important for humanitarian administrative boundaries. For example: `admin2.admin1_pcode` MUST correspond spatially to parent admin1 polygon. This gives you semantic topology, not just geometric topology.
>
> ### 5. Add schema contracts
>
> This is missing and would substantially improve the system. Every operational dataset should have a machine-readable schema definition. Example:
>
> ```yaml
> dataset: health_facilities
>
> geometry: Point
>
> required_fields:
>   facility_id: string
>   facility_name: string
>   admin1_pcode: string
>   admin2_pcode: string
>   facility_type: enum
>   operational_status: enum
>   source: string
>   source_date: date
>
> domains:
>   operational_status:
>     - operational
>     - partially_operational
>     - non_operational
>     - unknown
>
> constraints:
>   facility_id:
>     unique: true
>     nullable: false
>   admin2_pcode:
>     foreign_key: cod_admin2.pcode
> ```
>
> Then the AI assistant can validate data before geoprocessing. This is much stronger than allowing the LLM to infer what columns mean.
>
> ### 6. Strengthen P-Code handling
>
> Your P-Code rule is excellent and should become foundational. I would establish:
>
> ```
> P-Code = primary administrative join key
> Name   = display attribute
> ```
>
> Never `"Damascus" == "دمشق" == "Dimashq"` as an analytical join mechanism. Instead:
>
> ```
> SY01XXXX
>      ↓
> authoritative admin record
>      ├── name_en
>      ├── name_ar
>      ├── admin_level
>      └── parent_pcode
> ```
>
> Also validate: P-Code existence, P-Code uniqueness, P-Code hierarchy, spatial containment, parent-child relationship, temporal validity. That last point matters because administrative boundaries can change over time.
>
> ### 7. Add temporal GIS as a core capability
>
> This is one of the biggest omissions. Humanitarian mapping is rarely static. QGIS temporal functionality should therefore be part of the framework.
>
> Every event dataset should preferably include: `event_id`, `event_start`, `event_end`, `report_date`, `source_date`, `last_verified`, `status`.
>
> This allows QGIS Temporal Controller workflows for: displacement evolution, flood progression, road accessibility, incidents, facility operational status, conflict/access constraints, population movements.
>
> The agent should understand requests such as "Show health facilities that became inaccessible during the last seven days" as a combined TEMPORAL FILTER + SPATIAL FILTER + NETWORK ANALYSIS, rather than simply a spatial query.
>
> ### 8. Rework the network analysis section
>
> Your `serviceareafrompoint` example needs more caution. A travel-time model is only as good as the network impedance model. A stronger formulation is:
>
> ```
> Travel Cost = road length ÷ effective speed
>
> Effective Speed = baseline speed × surface factor × condition factor × weather factor × access factor
> ```
>
> For example: Primary paved road 1.00, Secondary paved 0.80, Unpaved 0.55, Damaged 0.30, Restricted 0.15, Closed BLOCKED. But these factors must be operationally calibrated rather than treated as universal constants.
>
> Your framework should distinguish geometric reachability from operational accessibility. A route may geometrically exist but be unusable due to closures, damaged bridges, vehicle limitations, seasonal conditions, administrative restrictions, temporary access constraints. That distinction is critical.
>
> ### 9. Improve population exposure methodology
>
> A simple zonal sum can overstate analytical certainty. You should distinguish population inside hazard footprint from population actually affected -- those are not equivalent.
>
> I recommend output fields such as: `pop_exposed_est`, `pop_source`, `pop_reference_year`, `hazard_date`, `hazard_threshold`, `analysis_resolution`, `confidence`.
>
> The resulting map should say "Estimated population within modeled flood extent" rather than "Flood-affected population" unless field verification supports the stronger claim. This is an important methodological safeguard.
>
> ### 10. Strengthen Earth Observation processing
>
> The SAR section is too simplified for an operational standard. A fixed >3 dB change should not be presented as a universal flood threshold. Sentinel-1 flood extraction can be affected by: incidence angle, terrain, vegetation, urban double bounce, permanent water, acquisition geometry, orbit direction, speckle, wind conditions.
>
> A stronger workflow is: Sentinel-1 GRD → Orbit/calibration → Speckle treatment → Terrain correction → Pre/post normalization → Change metric → Permanent-water mask → Terrain/slope exclusion → Adaptive threshold → Morphological cleanup → Vector extraction → Validation.
>
> For advanced EO processing, QGIS can orchestrate the workflow, but dedicated EO tools or cloud processing may perform parts of the chain more reliably.
>
> ### 11. Add QGIS Processing Models as the primary automation layer
>
> This is one of the most important changes I would make. Your architecture currently jumps from manual GIS to PyQGIS. Add an intermediate layer:
>
> ```
> QGIS GUI → Processing Algorithm → Processing Model (.model3) → PyQGIS → Agent orchestration
> ```
>
> Reusable humanitarian workflows should preferably exist as Processing Models. Example:
>
> ```
> MODEL: Flood Exposure Assessment
> Inputs: Hazard polygon, Population raster, Admin boundaries, Health facilities
> Pipeline: Fix geometries → Reproject → Clip hazard → Zonal statistics →
>           Intersect facilities → Aggregate Admin2 → Apply style → Generate QA report
> Outputs: exposure_admin2.gpkg, exposed_facilities.gpkg, analysis_summary.csv
> ```
>
> The AI agent can then execute a known, tested model instead of inventing the workflow every time.
>
> ### 12. Make QGIS styles reusable assets
>
> Symbology should not be generated from scratch for every map. Maintain a controlled style library (`styles/admin0.qml`, `admin1.qml`, `admin2.qml`, `health.qml`, `education.qml`, `displacement.qml`, `access.qml`, `flood.qml`, `damage.qml`). The agent should preferentially LOAD APPROVED QML instead of GENERATE NEW STYLE -- this improves consistency between analysts and offices. Also add rule-based renderers, categorized renderers, graduated renderers, scale-dependent visibility, symbol levels, data-defined properties, geometry generators, blend modes where justified, map themes.
>
> ### 13. Make classification selection data-driven
>
> I would remove "Jenks Natural Breaks: Default choice." There should be no universal default classification. Instead: inspect distribution → identify analytical purpose → select classification.
>
> | Objective | Candidate |
> |---|---|
> | Absolute operational thresholds | Manual classes |
> | Relative ranking | Quantiles |
> | Highly skewed observations | Jenks/log transformation |
> | Standard deviation analysis | Standard deviation |
> | Fixed measurement intervals | Equal interval |
> | Policy thresholds | Defined breaks |
>
> For humanitarian decision maps, operational thresholds often matter more than statistically elegant classes. Example: `<10,000 / 10,000–25,000 / 25,000–50,000 / 50,000–100,000 / >100,000` may be more useful than Jenks if those thresholds correspond to response capacity.
>
> ### 14. Introduce QGIS Expression Engine as a core technology
>
> Expressions should power labels, titles, legends, visibility, classifications, conditional warnings, Atlas content, filenames, map metadata. For example:
>
> ```
> CASE WHEN "severity" = 5 THEN 'CRITICAL' WHEN "severity" = 4 THEN 'HIGH'
>      WHEN "severity" = 3 THEN 'MODERATE' ELSE 'LOW' END
> ```
>
> Atlas filenames can use `concat('SITREP_', "admin2_pcode", '_', format_date(now(),'yyyyMMdd'))`. This reduces unnecessary Python. A good architectural principle: Expression first → Processing second → PyQGIS third.
>
> ### 15. Expand Atlas into a true publication engine
>
> Your Atlas section is good but should include: Coverage layer → Page filtering → Dynamic extent → Dynamic title → Dynamic statistics → Filtered legend → Locator map → Dynamic source statement → Dynamic filename → Batch export.
>
> The layout should expose stable item IDs such as `MAP_MAIN`, `MAP_LOCATOR`, `TITLE`, `SUBTITLE`, `LEGEND`, `SCALEBAR`, `NORTH_ARROW`, `SOURCE_TEXT`, `DISCLAIMER`, `DATE`, `SUMMARY_TABLE`, `LOGO`. The agent then manipulates IDs instead of trying to infer layout elements.
>
> ### 16. Add map themes
>
> QGIS Map Themes are ideal for your architecture: `THEME_SITREP`, `THEME_HEALTH`, `THEME_ACCESS`, `THEME_DAMAGE`, `THEME_DISPLACEMENT`, `THEME_LOGISTICS`. One project can therefore produce several products without repeatedly changing layer visibility. Agent request "Create an access map" could resolve to: Activate THEME_ACCESS → Apply ACCESS_A3 layout → Set AOI → Refresh Atlas → Validate → Export. That is far safer than allowing the model to reconstruct the project.
>
> ### 17. Introduce deterministic provenance
>
> Every generated analytical product should have a machine-readable sidecar, e.g.:
>
> ```json
> {
>   "product": "flood_exposure_admin2",
>   "generated_at": "2026-09-04T18:30:00+03:00",
>   "qgis_version": "...",
>   "project": "syria_flood_response.qgz",
>   "sources": [
>     {"dataset": "COD Admin2", "version": "2026-08"},
>     {"dataset": "WorldPop", "reference_year": 2025}
>   ],
>   "processing": ["native:fixgeometries", "native:reprojectlayer", "native:zonalstatisticsfb"],
>   "parameters": {},
>   "qa": {"geometry_valid": true, "join_validated": true, "null_pcodes": 0}
> }
> ```
>
> This makes the workflow reproducible and defensible.
>
> ### 18. Redesign the AI architecture
>
> I would substantially change Section 8. Instead of Natural Language → LLM generates Python → AST validator → Execute, use:
>
> ```
> USER INTENT → Intent Interpreter → Project Inspector (Layers/CRS/Fields/Layouts/Themes/Metadata)
>            → Spatial Planner → {Expression Engine | Processing Model | PyQGIS Fallback}
>            → Parameter Validator (CRS/Fields/AOI/Output/Geometry) → Risk Classifier
>            → {READ ONLY: auto-run | DERIVATIVE: auto/preview | DESTRUCTIVE: confirm}
>            → QgsTask Queue → Output Validator → Map QA Engine → Human Preview Gate
>            → EXPORT → AUDIT/PROVENANCE
> ```
>
> That is a much stronger QGIS agent architecture.
>
> ### 19. Do not rely on AST filtering as the security boundary
>
> This is important. Blocking `os.system`/`subprocess`/`socket`/`eval` does not make arbitrary Python safe -- Python is far too dynamic for a simple AST denylist to constitute a robust sandbox. The stronger approach is a tiered model:
>
> - **Tier 1 — Declarative tools:** QGIS expressions, Processing parameters, layer queries, style changes, layout properties.
> - **Tier 2 — Allow-listed Processing algorithms:** `native:buffer`, `native:clip`, `native:intersection`, `native:joinattributesbylocation`, `native:fixgeometries`, ...
> - **Tier 3 — Approved internal functions:** `tools.buffer_layer(...)`, `tools.create_atlas(...)`, `tools.validate_pcodes(...)`.
> - **Tier 4 — Generated PyQGIS:** only when necessary, with stronger isolation and operator approval according to risk.
>
> This drastically reduces attack surface.
>
> ### 20. Add transaction and rollback behavior
>
> Every write operation should be classified: READ, CREATE, MODIFY, DELETE, PUBLISH.
>
> | Action | Policy |
> |---|---|
> | Inspect layer | Automatic |
> | Select features | Automatic |
> | Create memory layer | Automatic |
> | Create new GeoPackage | Automatic/preview |
> | Modify source layer | Confirmation |
> | Delete features | Confirmation |
> | Overwrite file | Confirmation |
> | Drop database table | Strong confirmation |
> | Publish externally | Confirmation |
>
> Before destructive operations: Snapshot → Validate → Preview → Confirm → Execute → Validate → Commit. If validation fails: ROLLBACK.
>
> ### 21. Add a QGIS project inspector
>
> Before planning anything, the agent should interrogate the active project, with an internal representation similar to:
>
> ```json
> {
>   "project_crs": "EPSG:32637",
>   "layers": [{"name": "Admin2", "geometry": "Polygon", "crs": "EPSG:4326",
>               "feature_count": 287, "fields": ["admin2_name", "admin2_pcode"]}],
>   "layouts": ["SITREP_A3", "ATLAS_ADMIN2"],
>   "themes": ["ACCESS", "HEALTH", "DISPLACEMENT"]
> }
> ```
>
> The LLM should plan against this structured state, not hallucinate layer names.
>
> ### 22. Add a verification loop
>
> This is probably the most important feature for an autonomous mapping agent. Execution success does not mean analytical success. After every step: PLAN → EXECUTE → OBSERVE → VALIDATE → PASS?  NO → REPAIR/REPLAN; YES → NEXT STEP.
>
> For a buffer: Expected (output polygon exists, feature_count > 0, CRS metric, geometry valid) vs. Observed → PASS/FAIL. For an intersection: input A = 145 features, input B = 23 features, output = 0 → suspicious result → inspect CRS → inspect spatial extent → inspect geometry. This turns the agent from a script generator into a GIS reasoning system.
>
> ### 23. Add confidence and uncertainty reporting
>
> Every AI-generated analytical conclusion should distinguish OBSERVED, DERIVED, MODELED, INFERRED, UNKNOWN. For example: Hospital location = OBSERVED; Road closure = REPORTED; 60-min accessibility = MODELED; Population exposure = ESTIMATED; Operational impact = INFERRED. The final layout could even expose a "DATA CONFIDENCE: MEDIUM" summary broken out by layer. This would significantly improve humanitarian decision support.
>
> ### 24. Add sensitivity classification
>
> Your PII section should be expanded beyond redaction. A humanitarian GIS system needs layer-level disclosure classification: PUBLIC, INTERNAL, RESTRICTED, SENSITIVE. Publication logic then becomes: if target == PUBLIC, reject layers classified RESTRICTED/SENSITIVE, inspect attributes, generalize where required, remove operational metadata, run disclosure QA -- and this should happen before export, not afterward.
>
> ### 25. Correct the tactical mapping assumption
>
> I would modify one part of your typology. Your Tactical/Logistics category includes "safe route planning" and checkpoints. In operational humanitarian GIS, the mapping framework should distinguish route accessibility/logistics analysis from definitive safety claims. GIS can model road conditions, closures, travel impedance, communications coverage, and verified access constraints, but it should not label a route "safe" solely from spatial data. Use "Route accessibility and operational constraints" rather than "Safe route planning" unless a responsible security function provides that determination.
>
> ### 26. Introduce a standard humanitarian map QA checklist
>
> Before publication, automatically evaluate categories: DATA (authoritative boundary version, P-Code integrity, geometry validity, CRS appropriateness, source dates, NULL inspection), ANALYSIS (processing parameters recorded, units verified, join cardinality, output counts plausible, exposure estimates labeled correctly, temporal reference defined), CARTOGRAPHY (operational message dominant, classification appropriate, colorblind accessibility, labels readable, scale-dependent rendering, no misleading symbology), LAYOUT (title/AOI/date/legend/scale/sources/CRS/disclaimer/locator/version), DISCLOSURE (PII removed, sensitive attributes removed, sensitive layers excluded, public/generalized geometry), EXPORT (dimensions, DPI, fonts, georeferencing, file opens, filename standardized). The agent should generate this as part of every production run.
>
> ### 27. Define a standard agent command model
>
> Natural-language commands should ultimately become deterministic execution plans. E.g. "Create an Admin 2 flood exposure map for northwest Syria showing affected population and health facilities" resolves to a structured plan (task, aoi, inputs, an ordered `workflow:` list of named steps like `validate_inputs`/`validate_crs`/`repair_geometry`/`calculate_population_exposure`/`intersect`/`classify`/`style`/`layout`/`validate_map`/`disclosure_review`, and declared `outputs:`). Only after this plan is validated should QGIS execute it. That gives you Natural language → GIS plan → validated tools → QGIS execution, rather than Natural language → Python → hope it works.
>
> ### Recommended final architecture
>
> I would ultimately describe the complete system as six layers:
>
> ```
> LAYER 6 — HUMAN / OPERATIONAL GOVERNANCE:  Approval, Disclosure, QA, Security, Publication
> LAYER 5 — AGENTIC GIS:                     Intent, Planning, Memory, Validation, Recovery, Provenance
> LAYER 4 — CARTOGRAPHIC ENGINE:             QML, PAL, Expressions, Themes, Layouts, Atlas
> LAYER 3 — QGIS ANALYTICAL ENGINE:          Processing, Models, PyQGIS, GDAL, GRASS, Network, Raster
> LAYER 2 — DATA ENGINEERING:                CRS, Geometry, Schema, P-Code, Temporal, Metadata, QA
> LAYER 1 — DATA SOURCES:                    COD, HDX, OSM, EO, Kobo, QField, PostGIS, GeoPackage
> ```
>
> The central design principle I would use for the entire QGIS AI project is:
>
> > The LLM decides what should be done; QGIS determines how GIS operations are executed; deterministic validators determine whether the result is acceptable.
>
> That separation is important. An LLM should not become the spatial engine, topology engine, CRS authority, or numerical engine. QGIS/GDAL/PROJ/GEOS remain the computational authority. The agent provides planning, orchestration, interpretation, recovery, and interaction.
>
> With these changes, your document moves from a strong humanitarian GIS methodology toward something much closer to a production specification for an autonomous QGIS cartographic and spatial-analysis platform.

## B. Gap analysis against the live source tree (2026-09-04)

Each point below was checked directly against the code by four parallel
research passes over `src/cartogen_ai/core/agent/`, not inferred from tool
names or docstrings alone. Verdicts: **ALREADY TRUE** (the codebase already
does this), **PARTIAL** (some of it exists, materially incomplete),
**REAL GAP** (nothing found, a fresh finding), or **CONFLICTS WITH A LOGGED
DECISION** (the project already considered and explicitly decided against
this, on the record).

**Headline, before the point-by-point:** of the 28 items checked (27
numbered points + the standalone project-folder-structure recommendation),
1 is already true (point 25) and 4 have since been acted on (2026-09-04,
same day as this document -- see each point's own entry below for exact
before/after detail, not restated here): **point 19** was re-reviewed
against the audit doc it appeared to conflict with -- the audit's narrow
conclusion holds, but re-testing the underlying concern found and fixed
four live, working sandbox bypasses the same session; **point 9**
(population exposure vs. affected) was closed outright, adding explicit
estimate/provenance fields rather than a bare number that invites
overclaiming; **point 21** (project inspector) gained CRS/feature_count/
fields on `get_layers` and a new `list_layouts` tool (map themes, a
separate concept per point 16, are untouched); **point 13**
(classification) gained a manual/defined-breaks mode for operational
thresholds (a standard-deviation mode was deliberately left out -- see its
entry); and **point 2** (QA-gate state machine) had its first pass built
the same day, on Baron's explicit "start the shared infrastructure"
instruction -- the ordered lifecycle states, a sequential advancement
gate, and one real automated check (geometry validity, gating
STAGED -> VALIDATED) now exist and are wired to a registered tool set,
not just a design doc (see point 2's own entry for exact scope and what
points 4/5/6/7/17 still need to build on top of it); **point 4**
(geometry QA) then had its overlaps/duplicates/min-area follow-on built
immediately after, on Baron's own choice of what to build next, with
point 2's gate updated in the same slice to actually check the new
fields (gap detection and the semantic admin1/admin2 topology check
remain deliberately unbuilt -- see point 4's own entry); **point 5**
(schema contracts) then got its first two real contracts
(`health_facilities`, `admin2`) built the same day, wired into point 2's
gate as an opt-in check on VALIDATED -> ANALYSIS_READY (only runs when a
`contract_name` is actually supplied -- see point 5's own entry for why
opt-in, not automatic). **Update, 2026-09-05:** point 12 (style-library
reuse) closed too -- `save_layer_style`/`load_layer_style` round-trip a
layer's symbology through a real `.qml` file, live-verified against QGIS
4.2.2. Everything else
keeps its original verdict from the initial gap-check; this paragraph is
a change log, not a fresh recount of the whole document. Point 19's
entry is worth reading first regardless, both for what it found and for
what it didn't resolve (the larger tiered-architecture question is still
open).

1. **Processing-first execution model -- PARTIAL, the description half
   closed 2026-09-05; the routing half is a real policy call, not a
   mechanical fix, flagged rather than changed.** Processing algorithms
   already are the dominant path for core vector/raster ops: most
   spatial-operation tools (`buffer_analysis`, `intersect_layers`,
   `union_layers`, `spatial_join`, etc.) route through a shared
   `_run_and_add` helper (`vector_tools.py:36-44`) that calls
   `processing.run(...)`. But `execute_pyqgis_script`
   (`system_tools.py:346`) was not a rare, clearly-fenced fallback --
   `tool_router.py:96-100`'s `always_include` set hard-codes it into every
   filtered tool list the model sees, regardless of query relevance, and
   its own description was a bare "execute arbitrary PyQGIS script" with no
   fallback framing. Several other tools' descriptions tell the model to
   prefer themselves over it (a prompt-level nudge, not an architectural
   gate). **Fixed:** the tool's own description now opens with "LAST
   RESORT ONLY -- run this only when no other registered tool covers the
   task," plus an explicit note that its sandbox is denylist-based, not
   formally proven -- consistent with what other tools already say to
   steer the model away from it, now stated once at the source instead of
   scattered as reminders in each of them. **Deliberately not changed:**
   whether to remove it from `tool_router.py`'s `always_include` set (so
   it competes on relevance score like every other tool instead of being
   guaranteed visible on literally every query) -- that changes when the
   model can even see this tool as an option at all, which cuts both ways:
   less prominent exposure to a risky escape hatch is a real security
   improvement, but a genuine edge case with no other matching tool could
   become unreachable if it stops scoring into the top_k on a query that
   shares no vocabulary with anything else registered. Untested routing
   changes to a security-relevant tool's visibility are exactly the kind
   of thing this project's own Hermes Charter Rule 9 flags as needing
   Baron's call, not an engineering default -- same shape as point 19's
   still-open tiered-allow-list question, not resolved here.
   `docs/TOOLS_REFERENCE.md` regenerated. Full suite 1049 tests, same
   known baseline, 0 new failures (pure description text change, no new
   branch to test).
2. **Explicit QA-gate state machine (INGESTED→...→PUBLICATION_READY) --
   PARTIAL, first pass closed 2026-09-04.** Was a REAL GAP (no
   dataset-lifecycle state concept existed anywhere, nothing preventing a
   tool from running on data that "failed" an earlier check because
   there was no earlier-check result to consult). Now: `agent/
   dataset_status.py` implements the exact six-state ordered lifecycle
   named in the proposal, persisted as a JSON custom property on the
   layer (same durable-storage pattern already proven by `lineage.py` --
   survives project save/reload for free), with three registered tools
   (`get_dataset_status`, `set_dataset_status`, `advance_dataset_status`)
   exposing it to the agent. The gate is real, not cosmetic: it refuses
   to skip states, refuses a forward move across a checked transition
   unless the check passes (override requires a note, recorded in
   history), and refuses an unchecked forward move or any backward move
   without a note. Three transitions now have a real automated check
   wired in: INGESTED -> STAGED runs a P-code depth check (point 6,
   uniqueness + hierarchy, auto-passing "not applicable" when a layer
   isn't P-code-shaped); STAGED -> VALIDATED runs the existing
   `diagnose_topology` geometry-validity check (point 4's work); and
   VALIDATED -> ANALYSIS_READY runs a schema-contract check (point 5's
   work) when a `contract_name` is supplied. Still PARTIAL, deliberately:
   no automated check exists yet for the other three transitions, and
   point 7 (temporal GIS) hasn't been built to attach its own check to
   this record yet -- still a real, separate gap; see that entry below.
   Point 17 (provenance sidecar) has since been built, but deliberately
   reads this record rather than gating against it -- a provenance file
   is a generated artifact a caller asks for, not a QA-gate transition;
   see that entry below.
3. **CRS handling should be operation-aware, not a blanket rule --
   PARTIAL, buffer_analysis's warning closed 2026-09-05.** No hardcoded
   `32636`/`32637` exists anywhere in `agent/tools/*.py` -- so there's no
   "hardcoded Levant UTM" to correct -- and there's still no computed-UTM-
   from-AOI logic at all (`grep -rn "utm"` returns only 2 unrelated
   comment mentions) -- deliberately not built (see below). `buffer_analysis`
   ran `native:buffer` in whatever CRS the layer already had, with no
   CRS-suitability check or warning. **Confirmed live, not assumed:**
   `$area`/`$length` (used by `calculate_area`/`calculate_length`) turned
   out to already be ellipsoidal-aware and correct regardless of CRS --
   a real ~1km×1km square in EPSG:4326 evaluated to 1,003,754 m² via a
   plain `layer.createExpressionContext()`, no explicit ellipsoid
   configuration needed, so those two tools needed no fix (verified before
   assuming a bug existed, not after). `buffer_analysis` is a different,
   real bug: `native:buffer`'s `DISTANCE` parameter is applied in the
   input layer's own CRS units with no conversion -- confirmed live,
   buffering an EPSG:4326 point by 500 (meaning 500 meters) produced a
   buffer 1000 degrees wide (500 on each side), not ~1km, a silently
   nonsensical result. No other tool in the codebase passes a raw
   `DISTANCE` to Processing this way (`grep -n '"DISTANCE":'` across
   `agent/tools/*.py` returns exactly this one call site), so the fix is
   scoped to this tool alone. Fixed with an honest warning, not a guessed
   auto-fix: `buffer_analysis` now checks `layer.crs().isGeographic()`
   and returns an explicit `warning` naming the CRS and telling the
   caller to reproject first, plus a strengthened tool/parameter
   description stating the units caveat up front. Deliberately does
   **not** auto-reproject to a computed UTM zone and buffer there instead
   -- that's a real, bigger design decision (which CRS to pick, whether
   to return the result in the original CRS or the working one) this
   session didn't decide unilaterally, matching the same "warn honestly,
   don't invent unverifiable behavior" restraint as point 4's declined
   gap-detection and point 13's declined standard-deviation mode. 4 new
   tests. Full suite 1053 tests, same known baseline, 0 new failures.
   `docs/TOOLS_REFERENCE.md` regenerated. `obfuscate_sensitive_points`'s
   docstring remains the only other place that discusses CRS-for-operation,
   as unenforced prose advice -- untouched, out of scope for this slice.
4. **Geometry QA beyond fixgeometries -- PARTIAL, overlaps/duplicates/
   min-area closed 2026-09-04.** `diagnose_topology` originally only
   checked single-geometry validity and exact-zero-area polygons,
   feeding `fix_geometries` → `native:fixgeometries`. Extended, same
   session as point 2's QA gate: now also reports `duplicate_geometries`
   (exact WKT match across features) and, for polygon layers,
   `overlapping_feature_pairs` (real area-sharing overlap via
   `QgsGeometry.overlaps`, not mere touching -- bbox-prefiltered with the
   same `QgsSpatialIndex(layer.getFeatures())` pattern already used by
   `obfuscate_sensitive_points`'s admin-unit-snap path in this file), plus
   an optional `min_area` parameter flagging small-but-nonzero slivers
   separately from exact zero-area ones. Point 2's gate now checks all
   three (invalid/duplicate/overlapping), not just invalid geometries --
   exactly the "extend the same function, gate picks it up automatically"
   path this entry predicted. 8 new tests; this function had zero prior
   test coverage at all (confirmed via grep across `tests/` before this
   change) despite already being load-bearing for point 2's gate.
   **Still PARTIAL, deliberately:** gap detection (missing coverage
   inside a polygon layer meant to tile an area) was NOT added -- it
   needs a reference boundary to diff against that this tool has no way
   to infer, and a dissolve-and-look-for-interior-holes heuristic would
   misfire as a false gap on almost any real humanitarian admin-boundary
   layer (a coastline, an unmapped buffer zone, a deliberately excluded
   area are real holes, not QA failures) -- left alone rather than
   guessed at, per this project's own verify-by-execution standard (same
   reasoning as point 13's skipped standard-deviation classification).
   Ring problems are not handled as a separate check -- GEOS's
   `isGeomValid()`, already run, catches self-intersecting/malformed
   rings as invalid geometries; no evidence found that a distinct check
   is needed on top of that. The semantic topology check (admin2 sits
   inside claimed admin1 parent) remains untouched -- out of scope for
   this slice, which was specifically "point 4's overlaps/gaps/
   duplicates." P-code hierarchy/uniqueness (point 6) was a separate,
   attribute-level check (not a spatial one) and has since been closed;
   see that entry.
5. **Machine-readable schema contracts -- PARTIAL, first two contracts
   closed 2026-09-04.** Was a REAL GAP (no YAML/JSON schema files, no
   `foreign_key`/`required_fields`/`validate_schema` symbol anywhere in
   `src/` -- column meaning only ever inferred by the model at call
   time). Now: `agent/schema_contracts.py` + two real JSON contract
   files, `agent/contracts/health_facilities.json` and `admin2.json` --
   exactly the minimal start this entry's own earlier note suggested.
   Each contract declares required fields by an ALIAS LIST rather than
   one fixed name (`admin2_pcode`/`adm2_pcode`/`ADM2_PCODE` all satisfy
   the same slot, matched case-insensitively) -- deliberately, because
   this codebase's own `calculate_severity_index`/`calculate_presence_gap`
   already treat admin/pcode field names as caller-supplied parameters,
   not fixed strings, since real-world naming varies by source; a
   contract requiring one exact name would be a step backward from that.
   Field types check against `QVariant.<name>` (the same enum vocabulary
   `_qvariant_type_for_dtype` in `vector_tools.py` already uses), not a
   provider-dependent `field.typeName()` string. Optional `allowed_values`
   gives a real controlled-vocabulary/domain check (e.g.
   `health_facilities`'s `facility_type`). Two new registered tools,
   `list_schema_contracts`/`validate_schema`. Wired into point 2's gate
   as the second option this entry originally named: a `schema_contract`
   check on VALIDATED -> ANALYSIS_READY, but OPT-IN -- it only actually
   runs when `advance_dataset_status` is called with a `contract_name`;
   omitted, that transition falls through to the ordinary
   note-required path rather than failing a check with nothing to check
   against (not every dataset has a contract yet). 22 new tests. Still
   PARTIAL: only 2 contracts exist, no `foreign_key` cross-dataset
   concept was built. Point 6's P-code hierarchy check has since been
   closed and now validates against exactly the `admin2` contract's
   `admin1_pcode` field this entry originally left as a future hook.
6. **P-Code handling depth (uniqueness, hierarchy, temporal validity) --
   PARTIAL, uniqueness + hierarchy closed 2026-09-04.**
   `HUMANITARIAN_CARTOGRAPHY_STANDARDS.md` §I already logs basic P-code
   *usage* as substantially met but flags "no check against reusing a
   retired P-code." `fetch_hdx_admin_boundaries` only ever detected which
   field *is* the P-code field -- it validated neither uniqueness, nor the
   admin2-pcode-prefix-matches-parent-admin1-pcode hierarchy. Both now
   exist: `agent/pcode_validation.py`'s `check_pcode_uniqueness` (flags
   duplicate non-null P-codes, reports which feature ids collide) and
   `check_pcode_hierarchy` (a pure attribute-level string-prefix check --
   real COD-AB admin2 downloads denormalize the parent admin1 P-code onto
   every child row as a sibling field, e.g. admin2 `YE1201` under admin1
   `YE12`, so this is NOT a spatial containment/join check; that harder,
   separate "semantic topology" check -- does the admin2 polygon actually
   sit inside its claimed admin1 polygon -- remains the untouched part of
   point 4's own scope note). Both checks use the same caller-configurable,
   case-insensitive alias-list field matching as point 5's schema
   contracts (`admin2_pcode`/`adm2_pcode`/`ADM2_PCODE` all match), for the
   same reason: real-world COD-AB/geoBoundaries field naming varies by
   source. Two new registered tools, `check_pcode_uniqueness`/
   `check_pcode_hierarchy` (`agent/tools/pcode_validation_tools.py`).
   Wired into point 2's gate as `pcode_depth` on INGESTED -> STAGED --
   unlike point 5's schema-contract gate, this one is NOT opt-in: it
   auto-detects whether the layer even has P-code-shaped fields at all
   and passes as "not applicable" when it doesn't (or when the layer has
   no `fields()` at all, e.g. a raster), so it can never block a
   non-admin-boundary layer from advancing. 30 new tests (16 for the core
   module, 9 for the tool wrappers, 5 gate-integration tests covering the
   not-applicable/uniqueness-fail/hierarchy-fail/override/both-pass
   paths). Still PARTIAL, deliberately: no temporal-validity concept and
   no check against reusing a retired P-code -- both remain real,
   separate pieces of work (see point 7 for temporal GIS more broadly).
7. **Temporal GIS as a core capability -- REAL GAP.** Zero hits for
   `QgsTemporalController`/`TemporalProperties` anywhere in `src/`.
   `add_incident_point` captures one freeform `date` string field only --
   no `event_start`/`event_end`/`report_date`/`last_verified`/`status`,
   and no date-range filtering tool exists. Not previously discussed in
   `MASTER_TASK_REGISTRY.md` or `BUG_TRACKER.md`. Same note as points 5
   and 6 re: point 2's QA gate once a temporal-validity check exists.
8. **Network impedance model / geometric vs. operational accessibility --
   REAL GAP, but already independently identified.**
   `calculate_service_area`/`travel_time_matrix` pass Processing only a
   flat `DEFAULT_SPEED` (50 km/h) with no speed field, direction field, or
   turn cost; `optimize_delivery_route`'s stop-ordering runs on raw
   straight-line distance. `score_route_incident_risk` only scores
   proximity for a human to read and explicitly does not re-route.
   `docs/ROUTE_OPTIMIZATION_STRATEGY.md` already specifies this exact
   composite-impedance fix as unimplemented follow-up work with a
   prototype script -- so this point restates a gap this project already
   found and queued, it doesn't discover a new one.
9. **Population exposure vs. affected -- REAL GAP, closed 2026-09-04.**
   `estimate_population_exposure` and `population_access_gap` used to return
   plain `total_population`/`gap_population`-style fields with no docstring
   distinguishing "exposed" (estimate) from "affected" (verified) language.
   Fixed: both tools' descriptions now say explicitly that the result is an
   ESTIMATE, not a verified/affected-population figure, and both return
   dicts gained `pop_exposed_est`/`gap_population_est` (explicit alias
   fields, additive -- `total_population`/`gap_population` are unchanged so
   nothing downstream breaks), `pop_source`/`pop_reference_year` (parsed
   honestly from `fetch_worldpop_population`'s own
   `<ISO3>_population_<year>` layer-naming convention when it matches --
   falling back to the raw layer name rather than guessing a provider for a
   manually-loaded or renamed raster), `analysis_resolution` (the raster's
   real pixel size/CRS via `rasterUnitsPerPixelX/Y()`, not estimated), and a
   `confidence` string. 6 new tests (`tests/test_raster_tools.py`,
   `tests/test_logistics_tools.py`), full suite 764/1/6/14, same known
   baseline, 0 new failures. Does not add `hazard_date`/`hazard_threshold`
   -- those are hazard-specific fields neither tool has a hazard layer in
   scope to populate honestly; left for whichever hazard-specific tool
   would actually carry that data.
10. **SAR/EO flood extraction -- REAL GAP, nothing exists at any level of
    sophistication.** No Sentinel-1/SAR/dB/speckle/orbit-correction code
    anywhere. What exists is `calculate_ndwi` (optical NDWI on Green/NIR
    bands) plus generic change detection -- a different technique
    entirely, so even the proposal's baseline ">3 dB threshold" to
    critique doesn't currently exist to be improved.
11. **QGIS Processing Models (.model3) -- REAL GAP.** Zero `.model3`
    files and zero code/doc references to the concept anywhere in the
    repo.
12. **Style-library reuse (.qml files) -- CLOSED 2026-09-05.** Was a REAL
    GAP, already flagged as an open question: no `.qml` files existed and
    no code loaded a named style; `apply_categorized_style`/
    `apply_graduated_style` built symbology programmatically every call.
    `HUMANITARIAN_CARTOGRAPHY_STANDARDS.md` §VI already flagged this exact
    open question ("not yet confirmed... authoritative symbol library").
    Now: two new registered tools in `agent/tools/styling_tools.py`,
    `save_layer_style` (real `QgsMapLayer.saveNamedStyle()`) and
    `load_layer_style` (real `QgsMapLayer.loadNamedStyle()`), plus a
    `_derive_style_path` helper that sits the `.qml` beside the layer's
    own on-disk source when one resolves, falling back to Desktop for a
    scratch/memory layer -- the identical convention point 17's provenance
    sidecar already established, reused rather than reinvented. Scope
    deliberately kept to the literal gap named in this point (`.qml`
    file save/load) -- the orphaned `symbology-style.db` at the repo root
    (confirmed this session: a real, populated `QgsStyle`-format database,
    116 symbols + 35 color ramps, not an empty template) would let the
    agent browse/apply *named symbols from a library* rather than only
    round-tripping one layer's own full style, which is a related but
    separate capability, left unbuilt. 13 new tests
    (`tests/test_styling_tools.py`). **Live-verified**, not just unit-
    tested: a real headless PyQGIS session against QGIS 4.2.2 applied a
    real 5-class graduated style, saved it to a real `.qml` file,
    loaded it onto a fresh layer, and confirmed the renderer type and
    class structure round-tripped correctly -- see
    `docs/MASTER_TASK_REGISTRY.md` for the commit record. Full suite
    1038 tests, same known baseline, 0 new failures.
13. **Data-driven classification (no universal Jenks default) --
    PARTIAL, manual/defined-breaks closed 2026-09-04.** `_classify_values`
    (`styling_tools.py:85-116`) already picks between jenks/equal_interval/
    quantile based on skewness and cardinality -- not a blind default. It
    was still a 3-method set with no manual/defined-breaks option, so fixed
    operational-threshold classification (a real humanitarian need) wasn't
    supported at all. Fixed: `apply_graduated_style` gained an optional
    `breaks` parameter that bypasses auto-classification entirely and
    builds `QgsRendererRange` objects directly from caller-supplied
    boundaries (data's actual min/max become the outer bounds), overriding
    `mode` when given. 3 new tests, full suite unaffected. Does **not**
    add a standard-deviation mode -- that needs QGIS's newer
    `QgsClassificationMethod` subclass API, which this dev environment (no
    real QGIS install) can't verify live, so it was left alone rather than
    guessed at; still open if wanted. No documented policy anywhere
    mandates Jenks -- it's an implementation default only.
14. **QGIS Expression Engine underused -- REAL GAP.** Zero
    `QgsExpression`/`setDataDefinedProperty` usage in `layout_tools.py`/
    `styling_tools.py`. Titles and filenames are built with plain Python
    string formatting (`f"Layout_{title.replace(' ', '_')}"`); no
    `QgsPalLayerSettings`-based expression labeling exists.
15. **Atlas as a publication engine -- REAL GAP.** Zero `QgsLayoutAtlas`
    references anywhere. `create_print_layout` builds one fixed layout
    per call with no `.setId()` calls on any item -- no stable
    MAP_MAIN/TITLE/LEGEND-style identifiers exist for the agent to
    address individually.
16. **Map Themes (`QgsMapThemeCollection`) -- CLOSED 2026-09-05.** Was a
    REAL GAP: zero references anywhere (checked separately from the
    unrelated UI dark/light "theme" code in `ui/theme.py`, which is not
    this); no layer-visibility-preset mechanism existed for multi-product
    output from one project. Now: three new registered tools in
    `agent/tools/project_tools.py` -- `create_map_theme` (saves current
    layer visibility/style as a named theme via
    `QgsMapThemeCollection.createThemeFromCurrentState`), `apply_map_theme`
    (restores one via `.applyTheme`), and `list_map_themes`. **A real bug
    was found and avoided before it shipped**, not just tested around: the
    real QGIS API for both `createThemeFromCurrentState`/`applyTheme`
    types their `model` parameter as `QgsLayerTreeModel|None`, but passing
    `None` **segfaults the process outright** on a real QGIS 4.2.2 install
    -- a hard exit, not a catchable Python exception, confirmed via direct
    reproduction in a live headless PyQGIS session before any tool code
    was written. Fixed by always constructing a real `QgsLayerTreeModel`
    (`_new_layer_tree_model` helper) rather than passing `None`, with a
    comment explaining why. 12 new tests. **Live-verified**: created two
    themes with different real layer-visibility states, applied one, and
    confirmed the target layer's real visibility flag flipped correctly;
    confirmed the missing-theme error path too. Full suite 1049 tests,
    same known baseline, 0 new failures.
17. **Deterministic provenance sidecar -- CLOSED 2026-09-04.** Was a REAL
    GAP: no JSON provenance/processing-log writer existed. The closest
    thing, `export_tools.py`'s `_layer_provenance_entries`, only ever
    appends a human-readable *text* section to Word/Markdown reports --
    not a machine-readable sidecar with QGIS version, algorithm chain, or
    QA results. Now: `agent/provenance.py`'s `build_provenance_record`
    assembles exactly that -- QGIS version, tool-execution lineage, and
    QA-gate status/history/checks -- as pure computation, no file I/O.
    True to this entry's own suggestion, it reads both halves off records
    that already exist rather than tracking either a second time: the
    algorithm-chain half comes straight from `lineage.py`'s
    `get_layer_lineage`, and the QA-results half straight from point 2's
    `dataset_status.py`'s `get_dataset_status` (status + history +
    checks, already JSON, already per-layer). Two new registered tools in
    `agent/tools/provenance_tools.py`: `get_provenance_record` (read-only,
    no disk write) and `write_provenance_sidecar`, which actually writes
    the record as a real `<source_file>.provenance.json` file beside the
    layer's own on-disk source when one resolves (a QGIS URI suffix like
    `|layername=...` is stripped first), falling back to a Desktop file
    named after the layer -- with an explicit `warning` in the result,
    not a silent substitution -- for a layer with no real on-disk source
    (a scratch/memory layer), the same fallback convention
    `export_tools.py`'s `generate_report` already uses. Not wired into
    point 2's `_AUTOMATED_CHECK_TRANSITIONS` -- a provenance sidecar is a
    generated artifact a caller asks for, not a gate a layer must pass to
    advance, so there is no transition for it to block. 17 new tests
    across `tests/test_provenance.py` (plain fake layer, patching
    `lineage.py`'s own module-level `QGIS_AVAILABLE` to exercise real
    tracked lineage data through it) and `tests/test_provenance_tools.py`
    (the registered-tool wrappers, including real on-disk JSON writes
    cleaned up afterward, the same convention `tests/test_export_tools.py`
    already uses for `generate_report`'s real Desktop `.docx` writes).
18. **AI architecture redesign (Intent Interpreter → Project Inspector →
    Spatial Planner → ... ) -- PARTIAL, mostly aspirational.** The actual
    `agent.py` `run()` loop is: build system prompt → LLM call with
    router-filtered tools → dispatch tool calls → loop. No standalone
    parameter-validator or risk-classifier stage exists; each tool
    validates its own args inline. No automatic project-snapshot/inspector
    step runs before planning. `task_manager.py`'s PREVIEW_READY/CONFIRMED
    fields are bookkeeping on a task object with no code that reads task
    status to block execution -- the real execution gate is the separate,
    unrelated per-tool `confirmed: bool` pattern (see point 20).
19. **AST-based sandboxing as the security boundary is insufficient; use
    a 4-tier model instead -- RE-REVIEWED 2026-09-04, proposal's underlying
    concern CONFIRMED LIVE; the audit's narrower conclusion still holds on
    its own terms.** `docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md` Section 4
    settled a narrower question than this point actually raises: it compared
    a confirmation dialog against the sandbox for `execute_pyqgis_script`
    and correctly preferred the sandbox (a dialog just trains users to click
    through unread generated code). It did not re-examine whether the
    denylist itself is complete. Re-reviewing that specifically: reproduced,
    against an extracted copy of `_validate_script_safety` +
    `_SAFE_BUILTINS` run through the exact same `exec()` pattern
    `execute_pyqgis_script` uses, that `pathlib.Path(...).write_text()`/
    `.read_text()`, `dbm.open(path, 'c')`, `logging.FileHandler(path)`, and
    `zipfile.ZipFile(path, 'w')` all pass `_validate_script_safety`
    completely unblocked and then actually write a real file to disk --
    none of the four modules were in `_BLOCKED_MODULES`, and none of their
    file-writing calls is the `open` builtin name already on the blocklist.
    This is a concrete, live instance of exactly the failure mode the
    proposal describes in the abstract ("Python is far too dynamic for a
    simple AST denylist to constitute a robust sandbox") -- not a
    disagreement about philosophy, a verified gap in the specific
    implementation the 2026-08-21 audit approved. **Fixed same-day**: the
    four confirmed-bypass modules were added to `_BLOCKED_MODULES`
    (`system_tools.py`), with a regression test
    (`test_script_safety_blocks_filesystem_modules_that_bypass_open`,
    `tests/test_new_tools.py`) and `SECURITY.md` updated to match; full
    suite re-verified at 758 tests, same known 1-failure/6-error sandbox
    baseline, 0 new failures. This closes the specific holes found, not the
    general question -- `SECURITY.md` itself already disclaims this
    approach as "defense in depth against known techniques, not a formally
    proven sandbox... a determined attacker with unlimited creativity may
    find another gap," and this re-review is direct evidence that disclaimer
    is accurate, not just cautious hedging. The larger architectural
    question the proposal actually raises -- whether to restructure around
    a tiered allow-list model (declarative tools / allow-listed Processing
    algorithms / approved internal functions / PyQGIS as a rare, isolated
    last resort) instead of a denylist-plus-restricted-builtins sandbox at
    all -- is a real, still-open, multi-week architecture decision, not
    resolved by this session's patch, and remains Baron's call.
20. **Transaction/rollback classification (READ/CREATE/MODIFY/DELETE/
    PUBLISH) -- PARTIAL, and the ad hoc-ness is already acknowledged.**
    Only 5 of 131 tools implement the `confirmed: bool = False`/
    PREVIEW_REQUIRED gate (`load_project`, `remove_layer`,
    `calculate_area`/`calculate_length`/`field_calculator`). No
    READ/CREATE/MODIFY/DELETE/PUBLISH taxonomy exists in code.
    `docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md` §3 already logs this as
    reactive (one bug fixed an inconsistency between two tools sharing a
    mutation primitive) and leaves several similar humanitarian tools
    *deliberately* ungated pending an open, already-logged policy
    decision with three named options -- so this is a known open question,
    not an unnoticed gap. No snapshot/rollback mechanism exists for
    partial multi-step failure.
21. **QGIS project inspector -- PARTIAL, layer/layout inspection closed
    2026-09-04.** `get_layers` used to return only `{name, type, id}` --
    no CRS, feature_count, or fields in one call (fields needed a separate
    `get_attributes` call per layer), and no tool listed layouts or map
    themes at all. Fixed: `get_layers` now also returns `crs` for every
    layer, plus `fields`/`feature_count` for layer types that actually
    have them (a raster gets neither, rather than a false empty/zero); a
    new `list_layouts` tool lists existing print-layout names. 5 new
    tests, full suite unaffected. Map Themes are **not** addressed --
    that's point 16, a separate not-yet-implemented QGIS concept, not an
    inspection gap on top of an existing one.
22. **Verification/observe-validate loop -- PARTIAL, the flagship example
    closed 2026-09-05, the systemic version remains a real gap.** No
    PLAN→EXECUTE→OBSERVE→VALIDATE→REPAIR loop exists in `agent.py`. Was:
    the shared vector-tools helper (`_run_and_add`) used by
    `intersect_layers`/`union_layers`/`spatial_join` and ~15 other tools
    (buffer, dissolve, clip, difference, etc.) returned only
    `{"success": True, "layer_name": ...}` with no feature-count or
    zero-result check -- the proposal's flagship "zero-result
    intersection" example was specifically unhandled. Now: fixed once in
    the shared helper itself (the same "extend the shared function, every
    caller picks it up automatically" shape point 4's `diagnose_topology`
    extension already used) -- `_run_and_add` now reports `feature_count`
    on any output that has one, and an explicit `warning` when it's zero,
    telling the caller not to report an empty result as success without
    checking the inputs. Purely additive (no existing key changed), so no
    caller needed updating. 4 new tests (`_run_and_add` had zero direct
    test coverage before this, same gap point 4 found in
    `diagnose_topology`). **Live-verified**, not just mocked: a real
    headless PyQGIS session against QGIS 4.2.2 intersected two genuinely
    non-overlapping polygons (real 0-feature result, warning fired) and
    two genuinely overlapping ones (real 1-feature result, no false-
    positive warning). Full suite 1042 tests, same known baseline, 0 new
    failures. Scattered per-tool self-validation also still exists
    (`logistics_tools.py` checks `featureCount() == 0` in two places;
    `join_by_attribute` warns on non-unique join fields) -- and the
    systemic PLAN→EXECUTE→OBSERVE→VALIDATE→REPAIR agent-level loop this
    point also describes remains unbuilt, a genuinely separate,
    architecture-level piece of work (see point 18).
23. **Confidence/uncertainty reporting (OBSERVED/DERIVED/MODELED/...) --
    REAL GAP.** No such taxonomy or "DATA CONFIDENCE" layout summary
    exists. What exists is narrow and tool-specific: `forecast_trend`'s
    `fit_confidence` (strong/moderate/weak, tied only to R²) and
    `imagery_extraction.py`'s raw 0-1 detection-confidence score --
    isolated scalars, not a project-wide epistemic-status system.
24. **Sensitivity/disclosure classification -- REAL GAP, and narrower
    than assumed.** No PUBLIC/INTERNAL/RESTRICTED/SENSITIVE layer tagging
    or pre-export gate exists anywhere. `export_layer` exports any named
    layer unconditionally with no sensitivity check. The only related
    tool, `obfuscate_sensitive_points`, is explicit opt-in/advisory, never
    automatic. The one logged GDPR finding (F1, now closed in both repos
    as of today) was about the plugin's own stored notes/preferences
    lacking bulk erasure -- unrelated to map-layer/geodata sensitivity
    classification.
25. **"Safe route" terminology -- ALREADY TRUE, already appropriately
    hedged.** `score_route_incident_risk`'s actual docstring never claims
    a route is "safe" -- it says explicitly it "does NOT re-route or
    exclude anything automatically -- this scores a route for a human to
    act on." The literal phrase "safe route" appears only in
    `tool_router.py`'s curated user-query alias list (how people phrase
    requests, mapped to the right tool) and is explicitly excluded from
    what's sent to the model. No tool name, description, or prompt rule
    asserts route safety. This is the one point of the 28 where the
    proposal's concern doesn't apply to this codebase as it stands.
26. **Automated per-map-product QA checklist -- REAL GAP, confirmed
    distinct from `docs/RELEASE_SMOKE_TEST.md`.** That document verifies
    the *plugin's tools* work in a real QGIS session before a release --
    it is not per-product and has no data/cartography/disclosure/export
    categories tied to an individual map output. No automated
    QA-checklist generator for individual products exists.
27. **Deterministic agent command model (plan-then-validate-then-execute)
    -- REAL GAP, current model is ReAct-style.**
    `AgentTaskManager.create_plan` takes freeform human-readable task
    description strings, not a typed step schema, and is just another
    optional tool the LLM may call for UI progress display -- not a
    pre-execution gate. `auto_advance_if_unambiguous` exists specifically
    because the model creates a plan and then calls tools independently
    of it. There is no upfront structured-plan-then-validate pipeline
    anywhere.
28. **Standard project folder architecture (data/00_raw, 10_staging, ...
    with immutable raw data) -- REAL GAP.** The plugin imposes zero
    folder-layout opinion -- it operates entirely on whatever
    `QgsProject.instance()` has open. No raw/staging/processed separation
    or immutability enforcement exists anywhere.

## C. Maintenance note

**Point 19 has been re-reviewed (2026-09-04) -- see that entry above for
the full account.** Short version: the proposal's underlying concern was
confirmed live (four real, working sandbox bypasses found and fixed the
same session), but that closes the specific holes found, not the larger
architectural question of whether to move to a tiered allow-list model
instead of a denylist-based sandbox at all -- that remains a real,
open, multi-week decision, still Baron's call, not resolved by patching
the four bypasses. Point 20 has a similar shape one level down: the ad hoc
confirm-gate coverage is a logged, open policy question with three
already-named options in the same audit doc, not an unnoticed
inconsistency -- unlike point 19, nothing there was re-tested or changed
this session.

**Point 9 has been closed (2026-09-04, same session as the point-19
re-review, picked as the next item to act on from this document's own
queue).** `estimate_population_exposure`/`population_access_gap` now
return explicit `pop_exposed_est`/`gap_population_est`,
`pop_source`/`pop_reference_year`, `analysis_resolution`, and a
`confidence` string instead of a bare number a report could quote as a
confirmed affected-population figure. This was a self-contained,
single-session fix (two functions, additive fields, no architectural
dependency on the still-open items) -- unlike most of the remaining
items, which either need the QA-gate/dataset-status concept points
2/4/5/6/7/17 share, or are themselves multi-week platform changes
(point 18).

**Points 21 and 13 were closed the same session, immediately after, on
Baron's "complete the remaining tools":** both were picked for the same
reason as point 9 -- self-contained, additive, no dependency on the
QA-gate/dataset-status work. Point 21 (`get_layers` gained
crs/fields/feature_count; new `list_layouts` tool) and point 13
(`apply_graduated_style` gained a `breaks` parameter for manual/defined-
threshold classification) are each narrower than their full point --
point 21 doesn't touch Map Themes (point 16, a separate unbuilt concept),
and point 13 doesn't add a standard-deviation classification mode
(deliberately skipped: it would need QGIS's newer `QgsClassificationMethod`
subclass API, which this no-real-QGIS-install dev environment can't
verify live -- left alone rather than guessed at, per this project's own
verify-by-execution standard). Both closures are additive, non-breaking,
and covered by new tests; see each point's own entry above for detail.

**Point 2 has had its first pass built (2026-09-04, same session,
on Baron's explicit "start the shared infrastructure" instruction) --
the ordered lifecycle, the sequential gate, and one real automated check
(geometry validity, reusing `diagnose_topology` rather than
reimplementing it) gating STAGED -> VALIDATED.** This was deliberately
scoped as infrastructure, not a full build-out of points 4/5/6/7/17:
each of those still needs its own real work (overlap/gap/duplicate
geometry checks, schema contracts, P-code hierarchy/uniqueness,
temporal-validity fields, a provenance sidecar writer), and this session
did not invent placeholder checks for any of them just to make the gate
look more complete than it is -- an unchecked forward transition
requires an explicit note justifying the manual advance instead. Each of
those five points can now register its own check in
`_AUTOMATED_CHECK_TRANSITIONS` (`agent/dataset_status.py`) once built,
rather than needing its own state-tracking mechanism -- see each point's
own entry above for the specific hook. Covered by 29 new tests across
`tests/test_dataset_status.py` (core state machine, using a plain fake
layer object rather than a QGIS mock) and
`tests/test_dataset_status_tools.py` (the registered-tool wrappers);
full suite re-run afterward at 801 tests with the same pre-existing
baseline (1 DNS-sandbox failure, 6 file-permission errors in
`test_reporting_tools.py`, 14 skipped) and zero new failures.

**Point 4 had its overlaps/duplicates/min-area follow-on built the same
session, immediately after, on Baron's explicit "pick one dependent
point to build next" -> point 4's fuller geometry QA.** `diagnose_topology`
gained `duplicate_geometries` and (polygon layers only)
`overlapping_feature_pairs` plus an optional `min_area` threshold; point
2's gate was updated in the same slice to actually check the two new
fields, not just `invalid_geometries` -- proving out the "extend the
check function, the gate picks it up automatically" design point 2's
own entry predicted, rather than leaving that claim untested. Gap
detection and the semantic admin1/admin2 topology check remain
deliberately unbuilt -- see point 4's updated entry for why gap
detection specifically was left alone rather than guessed at. 12 new
tests (8 for `diagnose_topology` itself -- its first test coverage of
any kind -- plus 4 for the strengthened gate); full suite 813 tests,
same known baseline, 0 new failures.

**Point 5 had its first two schema contracts built the same session,
immediately after, on Baron's "not yet, keep building" -- picked as the
next dependent point without asking again, since it was already named
as an option alongside point 4.** New `agent/schema_contracts.py` +
`agent/contracts/health_facilities.json`/`admin2.json` (real JSON
files, not inline Python dicts, as the review's own wording asked for).
Fields are matched by an alias list, case-insensitively, rather than one
fixed name -- deliberately, to match this codebase's own existing
treatment of admin/pcode field names as caller-supplied parameters
(`calculate_severity_index`'s `unit_name_field`, etc.) rather than fixed
strings, since real COD-AB/geoBoundaries downloads vary
(`ADM2_PCODE` vs. `admin2_pcode` vs. `adm2_pcode`). Wired into point
2's gate as an OPT-IN check on VALIDATED -> ANALYSIS_READY -- runs only
when the caller supplies `contract_name`; omitted, the transition falls
through to the ordinary note-required path instead of failing a check
with no contract to check against, since only two datasets have
contracts so far. 22 new tests across `tests/test_schema_contracts.py`
(plain fake field/feature/layer objects, real contract JSON files read
from disk rather than mocked), `tests/test_schema_contract_tools.py`,
and 4 gate-integration tests in `tests/test_dataset_status.py`. Full
suite 835 tests, same known baseline, 0 new failures. Still PARTIAL:
only 2 contracts exist, and no cross-dataset `foreign_key` concept was
built. Point 6's P-code hierarchy check has since closed against exactly
the `admin2` contract's `admin1_pcode` field -- see point 5's updated
entry.

**Point 6 had its uniqueness + hierarchy checks built the same session,
immediately after, on Baron's explicit "Point 6: P-code depth" answer to
"keep going toward point 6 or point 17."** New `agent/pcode_validation.py`
(`check_pcode_uniqueness`, `check_pcode_hierarchy`) + `agent/tools/
pcode_validation_tools.py`, using the same case-insensitive alias-list
field matching as point 5's schema contracts, for the same reason
(real-world COD-AB/geoBoundaries field naming varies by source). The
hierarchy check is a pure attribute-level string-prefix check, not a
spatial one -- real COD-AB admin2 downloads denormalize the parent
admin1 P-code onto every child row as a sibling field, so no spatial
join or containment logic was needed; that harder, separate "does the
admin2 polygon actually sit inside its claimed admin1 polygon" check
remains point 4's own untouched semantic-topology item, not this one.
Wired into point 2's gate as `pcode_depth` on INGESTED -> STAGED --
unlike point 5's OPT-IN schema-contract check, this one auto-detects
whether a layer even has P-code-shaped fields and passes as "not
applicable" when it doesn't, so it can never block a non-admin-boundary
layer from advancing (a design correction made mid-build, after a real
regression surfaced: a fields()-less fake layer was initially treated as
a hard failure rather than "not applicable," which would have wrongly
blocked every non-P-code layer's INGESTED -> STAGED advance). 30 new
tests across `tests/test_pcode_validation.py`, `tests/
test_pcode_validation_tools.py`, and 5 gate-integration tests in
`tests/test_dataset_status.py`. Full suite 865 tests, same known
baseline, 0 new failures. Still PARTIAL: no temporal-validity concept
and no check against reusing a retired P-code -- both remain real,
separate pieces of work.

**Point 17 was closed the same session, immediately after, on Baron's
"Not yet, keep building" answer declining to commit point 6 yet --
continued to point 17 since it was already named as the alternative
option in the same question ("keep going toward point 6 or point 17").**
New `agent/provenance.py`'s `build_provenance_record` assembles a
machine-readable provenance record (QGIS version, tool-execution
lineage, QA-gate status/history/checks) as pure computation with no file
I/O, reading both halves off records that already exist -- `lineage.py`'s
tracked history and point 2's `dataset_status.py` record -- rather than
tracking either a second time, exactly as this entry's own earlier note
suggested. Two new tools in `agent/tools/provenance_tools.py`:
`get_provenance_record` (read-only) and `write_provenance_sidecar`,
which writes the record to a real `<source_file>.provenance.json` file
beside the layer's own on-disk source when one resolves, falling back
to a named Desktop file (with an explicit warning, not a silent
substitution) for a scratch/memory layer with no real source -- the
same fallback convention `export_tools.py`'s `generate_report` already
uses. Deliberately NOT wired into point 2's `_AUTOMATED_CHECK_TRANSITIONS`
-- a provenance sidecar is a generated artifact a caller asks for, not a
gate a layer must pass to advance. 17 new tests across `tests/
test_provenance.py` and `tests/test_provenance_tools.py` (the latter
including real on-disk JSON writes, cleaned up afterward, matching
`tests/test_export_tools.py`'s existing convention for `generate_report`'s
real Desktop writes). Full suite 882 tests, same known baseline, 0 new
failures. Points 4 and 5 were already committed earlier this session (as
`250f04a`); points 6 and 17 are now committed too, as `e3bc00c`, on
Baron's "Yes, commit all four now."

Three points (8, 12, and the P-code half of 6) restate gaps this project
had *already independently found and, in 8's case, already scoped a fix
for* (`docs/ROUTE_OPTIMIZATION_STRATEGY.md`) -- useful confirmation that
the proposal's read of the codebase is accurate, not new information.
Point 25 is the one place the proposal's own concern turns out not to
apply here -- worth knowing before spending effort "fixing" something
that's already correctly hedged.

The other ~21 points are real, previously-undiscussed gaps of genuinely
different sizes -- from a one-file addition (point 5's schema contracts
could start with just `health_facilities` and `admin2`) to a multi-week
platform change (point 18's full agent-architecture redesign, or point 2's
QA-gate state machine, which point 4/5/6/7/17 all effectively feed into
and depend on for a shared "dataset status" concept to hang off of).

This document does not recommend a sequencing or make any implementation
decisions -- per this project's own governance rule (`docs/
MASTER_TASK_REGISTRY.md`'s Hermes Charter), which of these ~24 real,
independent gaps to act on, in what order, and how much of the six-layer
target architecture to actually build is Baron's call, not an engineering
default. See the corresponding queue item in `docs/MASTER_TASK_REGISTRY.md`
for tracking.
