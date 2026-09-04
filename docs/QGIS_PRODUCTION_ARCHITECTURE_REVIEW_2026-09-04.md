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
1 is already true, 4 are partial, 21 are real gaps, and **1 (point 19)
directly conflicts with a decision this project already made and
documented** -- that one is worth reading first since implementing it as
proposed would silently reverse a deliberate choice, not close a gap.

1. **Processing-first execution model -- PARTIAL.** Processing algorithms
   already are the dominant path for core vector/raster ops: most
   spatial-operation tools (`buffer_analysis`, `intersect_layers`,
   `union_layers`, `spatial_join`, etc.) route through a shared
   `_run_and_add` helper (`vector_tools.py:36-44`) that calls
   `processing.run(...)`. But `execute_pyqgis_script`
   (`system_tools.py:346`) is not a rare, clearly-fenced fallback --
   `tool_router.py:96-100`'s `always_include` set hard-codes it into every
   filtered tool list the model sees, regardless of query relevance, and
   its own description is a bare "execute arbitrary PyQGIS script" with no
   fallback framing. Several other tools' descriptions tell the model to
   prefer themselves over it (a prompt-level nudge, not an architectural
   gate).
2. **Explicit QA-gate state machine (INGESTED→...→PUBLICATION_READY) --
   REAL GAP.** No dataset-lifecycle state concept exists anywhere -- no
   status field, no `@dataclass` for it, nothing preventing a tool from
   running on data that "failed" an earlier check, because there is no
   earlier-check result to consult. Validation today is scattered,
   per-tool, stateless.
3. **CRS handling should be operation-aware, not a blanket rule -- REAL
   GAP, but not the conflict form described.** No hardcoded
   `32636`/`32637` exists anywhere in `agent/tools/*.py` -- so there's no
   "hardcoded Levant UTM" to correct -- but there's also no computed-UTM-
   from-AOI logic at all (`grep -rn "utm"` returns only 2 unrelated
   comment mentions). `buffer_analysis` runs `native:buffer` in whatever
   CRS the layer already has, with no CRS-suitability check or warning.
   `obfuscate_sensitive_points`'s docstring is the only place that even
   discusses CRS-for-operation, as unenforced prose advice.
4. **Geometry QA beyond fixgeometries -- PARTIAL.** `diagnose_topology`
   (`vector_tools.py:1605-1633`) exists and checks single-geometry
   validity and zero-area polygons, feeding `fix_geometries` →
   `native:fixgeometries`. It does not check overlaps, gaps, duplicates,
   ring problems, or minimum-area thresholds across features. No semantic
   topology check exists -- nothing validates that an admin2 polygon
   spatially sits inside its claimed admin1 parent (`admin1_pcode`/
   `admin2_pcode` cross-check returns zero hits in `humanitarian_tools.py`).
5. **Machine-readable schema contracts -- REAL GAP.** No YAML/JSON schema
   files, no `foreign_key`/`required_fields`/`validate_schema` symbol
   anywhere in `src/`. The only "schema" hits are the LLM function-calling
   JSON schema and runtime `QgsFields` objects -- column meaning is
   inferred by the model at call time, not pre-validated against a
   contract.
6. **P-Code handling depth (uniqueness, hierarchy, temporal validity) --
   REAL GAP, extends an already-partially-logged item.**
   `HUMANITARIAN_CARTOGRAPHY_STANDARDS.md` §I already logs basic P-code
   *usage* as substantially met but flags "no check against reusing a
   retired P-code." Going further: `fetch_hdx_admin_boundaries` only
   detects which field *is* the P-code field -- it validates neither
   uniqueness, nor the admin2-pcode-prefix-matches-parent-admin1-pcode
   hierarchy, nor any temporal-validity concept.
7. **Temporal GIS as a core capability -- REAL GAP.** Zero hits for
   `QgsTemporalController`/`TemporalProperties` anywhere in `src/`.
   `add_incident_point` captures one freeform `date` string field only --
   no `event_start`/`event_end`/`report_date`/`last_verified`/`status`,
   and no date-range filtering tool exists. Not previously discussed in
   `MASTER_TASK_REGISTRY.md` or `BUG_TRACKER.md`.
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
9. **Population exposure vs. affected -- REAL GAP.**
   `estimate_population_exposure` and `population_access_gap` return
   plain `total_population`/`gap_population`-style fields -- none named
   `pop_exposed_est`/`pop_source`/`pop_reference_year`/`confidence`, and
   no docstring distinguishes "exposed" (estimate) from "affected"
   (verified) language.
10. **SAR/EO flood extraction -- REAL GAP, nothing exists at any level of
    sophistication.** No Sentinel-1/SAR/dB/speckle/orbit-correction code
    anywhere. What exists is `calculate_ndwi` (optical NDWI on Green/NIR
    bands) plus generic change detection -- a different technique
    entirely, so even the proposal's baseline ">3 dB threshold" to
    critique doesn't currently exist to be improved.
11. **QGIS Processing Models (.model3) -- REAL GAP.** Zero `.model3`
    files and zero code/doc references to the concept anywhere in the
    repo.
12. **Style-library reuse (.qml files) -- REAL GAP, already flagged as an
    open question.** No `.qml` files exist and no code loads a named
    style. `apply_categorized_style`/`apply_graduated_style` build
    symbology programmatically every call.
    `HUMANITARIAN_CARTOGRAPHY_STANDARDS.md` §VI already flagged this exact
    open question ("not yet confirmed... authoritative symbol library").
    An orphaned `symbology-style.db` sits at the repo root, referenced by
    no code.
13. **Data-driven classification (no universal Jenks default) --
    PARTIAL.** `_classify_values` (`styling_tools.py:85-116`) already
    picks between jenks/equal_interval/quantile based on skewness and
    cardinality -- not a blind default. But it's still a 3-method set with
    no standard-deviation or manual/defined-breaks option, so fixed
    operational-threshold classification (a real humanitarian need) isn't
    supported at all. No documented policy anywhere mandates Jenks --
    it's an implementation default only.
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
16. **Map Themes (`QgsMapThemeCollection`) -- REAL GAP.** Zero references
    anywhere (checked separately from the unrelated UI dark/light "theme"
    code in `ui/theme.py`, which is not this). No layer-visibility-preset
    mechanism exists for multi-product output from one project.
17. **Deterministic provenance sidecar -- REAL GAP.** No JSON
    provenance/processing-log writer exists. The closest thing is
    `export_tools.py`'s `_layer_provenance_entries`, which appends a
    human-readable *text* section to Word/Markdown reports -- not a
    machine-readable sidecar with QGIS version, algorithm chain, or QA
    results.
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
    a 4-tier model instead -- CONFLICTS WITH A LOGGED DECISION.**
    `docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md` §4 already reviewed this
    exact question and closed it: *"`execute_pyqgis_script` has no
    confirmation gate -- reviewed, not a gap... already a disclosed,
    deliberate design choice."* The project's documented position is that
    the extensively-hardened AST denylist (`system_tools.py:14-160`,
    written specifically against confirmed live bypass attempts) is the
    right mitigation for this tool's shape, and that a confirm-dialog
    would be weaker in practice since users click through unread generated
    code. There is no allow-listed-algorithm tier or approved-
    internal-function tier today -- `execute_pyqgis_script` is one
    general-purpose tool among 131, not gated behind another tier -- but
    adding one is a re-opening of an already-decided question, not an
    unnoticed gap. Worth Baron's explicit re-review given how forcefully
    the proposal argues this point, but not something to silently
    implement over the top of the existing decision.
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
21. **QGIS project inspector -- PARTIAL.** `get_layers` exists but returns
    only `{name, type, id}` -- no CRS, feature_count, or fields in one
    call (fields need a separate `get_attributes` call per layer). No
    tool lists layouts or map themes for inspection at all.
22. **Verification/observe-validate loop -- PARTIAL, the systemic version
    is a real gap.** No PLAN→EXECUTE→OBSERVE→VALIDATE→REPAIR loop exists
    in `agent.py`. The shared vector-tools helper used by
    `intersect_layers`/`union_layers`/`spatial_join` returns only
    `{"success": True, "layer_name": ...}` with no feature-count or
    zero-result check -- the proposal's flagship "zero-result
    intersection" example is specifically unhandled. That said, scattered
    per-tool self-validation does exist (`logistics_tools.py` checks
    `featureCount() == 0` in two places; `join_by_attribute` warns on
    non-unique join fields) -- so result-sanity checking exists piecemeal,
    just not as a systemic agent-level mechanism.
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

**Read point 19 before acting on any of this.** It's the one place this
proposal argues directly against a decision Baron's own project already
made and documented (`docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md` §4) --
worth a deliberate second look given how forcefully the proposal states
it, but implementing the 4-tier model as a drop-in replacement for the
current AST-sandbox-as-boundary design would silently reverse that
decision rather than close a gap nobody had considered. Point 20 has the
same shape one level down: the ad hoc confirm-gate coverage is a logged,
open policy question with three already-named options in the same audit
doc, not an unnoticed inconsistency.

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
