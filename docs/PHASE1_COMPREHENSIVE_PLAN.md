# Cartogen AI Phase 1 — Comprehensive Delivery Plan

**Role:** Technical project manager / release owner  
**Repository:** Private `CARTOGEN-AI`  
**Primary reference:** Existing Cartogen QGIS plugin plus `C:\Cartogen-AI-Core\Ref\QGIS-master`  
**Active AI provider:** Gemini API only for this phase  
**Execution model:** Two concurrent engineering workstreams maximum; main session owns integration, verification, and release decisions.

## 1. Phase 1 objective

Deliver a professional, browser-native humanitarian mapping application in which the user can ask Cartogen AI a question, discover or supply data, review a typed plan, approve safe operations, inspect the resulting map/layers/table, edit data with an explicit diff, and queue or schedule read-only analysis.

The web application must be a working system, not a visual mockup.

## 2. Product principles

- **AI-first:** chat is the primary command surface; tools are generated from the objective and current project context.
- **GIS-grade underneath:** real PostGIS state, real GeoJSON read-back, real map layers, real operations, real lineage.
- **QGIS-informed:** reproduce the useful behavior of `QgsMapCanvas`, `QgsLayerTree`, `QgsTaskManager`, `QgsProcessingAlgorithm`, and the existing Cartogen QGIS agent—not the QGIS visual design or source code.
- **No fabricated state:** no fake basemaps, pins, counts, source records, project metrics, or completed-job claims.
- **Human approval:** destructive edits require preview, diff, confirmation, and transaction read-back.
- **Provenance:** every imported source, AI step, operation, output layer, and scheduled run has lineage.
- **Provider boundary:** Gemini is the only active provider; provider keys remain backend-only.
- **Release discipline:** every gate needs automated/API/browser evidence and exact status reporting.

## 3. Reference findings incorporated

### Cartogen QGIS plugin patterns to port

- Chat history bound to the active project;
- file attachments and context ingestion;
- prompt refinement as an explicit user choice;
- `QgsTask` background execution, cancellation, progress, and completion callbacks;
- task states: queued, running, preview-ready, confirmation-required, complete, failed, cancelled;
- task inspector showing rationale, parameters, and generated operation;
- retry and edit/resend workflow;
- HDX, OSM Overpass, geoBoundaries, STAC, and humanitarian data fetchers;
- tool routing/aliases to avoid sending the entire registry on every request;
- CRS compatibility and topology diagnosis;
- smart symbology and colorblind-safe styling;
- layer lineage and spatial memory;
- read-only recurring workflows;
- explicit destructive-operation confirmation.

### QGIS reference patterns to port

- Map canvas owns view, extent, CRS, selections, overlays, and rendered layer state;
- layer tree owns layer order, visibility, groups, and active layer;
- processing algorithms have stable IDs, typed parameters, outputs, feedback, and descriptions;
- task manager owns queued/running/completed/terminated state and cancellation.

## 4. Target web architecture

```text
Browser
  ├─ Chat / agent transcript
  ├─ Map canvas / basemap / layer tree
  ├─ Inspector / edit diff / tool controls
  └─ Jobs / schedules / provenance
        ↓
Node API
  ├─ project and layer state
  ├─ dataset discovery/import
  ├─ agent runs and typed steps
  ├─ edit transactions and lineage
  ├─ jobs, worker, schedules
  └─ Gemini gateway adapter
        ↓
PostgreSQL/PostGIS + object/source metadata + worker
```

## 5. Work packages and acceptance criteria

### WP-01 — Professional map and layer model

- Leaflet/MapLibre map surface with OSM default and selectable standard basemaps;
- attribution, CRS, scale, zoom, fit-to-layer, selection, and empty states;
- server-backed layer tree: order, visibility, active layer, source, style;
- real GeoJSON read-back only;
- no decorative geometry or hard-coded project metrics;
- map selection synchronizes with attribute table and inspector.

**Gate:** upload a real GeoJSON layer, read it from PostGIS, render it, toggle it, fit it, select a feature, and read its properties back.

### WP-02 — AI agent run and step model

- persist `agent_runs` and `agent_steps`;
- store prompt, system/model/provider metadata, context snapshot, plan, warnings, rationale, status, and timestamps;
- separate system/user messages;
- Gemini-only provider selection;
- plan preview and explicit approval;
- tool execution never writes directly from model output;
- step-level retry/edit and error details.

**Gate:** chat objective produces a persisted Gemini plan, read-back shows steps, approval creates an auditable job, and the final assistant response matches the job result.

### WP-03 — Dataset discovery and import

- HDX search;
- OSM Overpass search/fetch;
- geoBoundaries fetch;
- STAC discovery where relevant;
- candidate dataset cards with URL, provider, licence, date, CRS, schema, limitations;
- explicit import approval;
- import transaction to PostGIS;
- raw source/provenance record;
- no silent external-data import.

**Gate:** ask for a dataset, receive real candidates, approve one, import it, read it back, and show it as a real layer.

### WP-04 — Typed spatial operations

- stable operation registry inspired by `QgsProcessingAlgorithm`;
- typed parameters and validation;
- CRS mismatch checks;
- topology diagnosis;
- buffer, intersection, clip, join, selection, summary, and humanitarian presets;
- feedback/progress;
- worker execution and persisted outputs;
- operation rationale and lineage.

**Gate:** AI chooses a typed operation, the UI shows parameters, approval queues it, worker completes it, output layer is read back and displayed.

### WP-05 — Editing and safety

- feature/property selection;
- edit form with validation;
- before/after diff;
- preview transaction;
- explicit confirm/apply;
- optimistic locking/version check;
- lineage event and audit log;
- undo/revert path.

**Gate:** edit one feature, reject invalid input, preview diff, confirm transaction, read back changed feature, and verify lineage.

### WP-06 — Jobs and scheduling

- durable queued/running/complete/failed/cancelled state;
- cancellation and retry;
- worker claim lock;
- saved read-only workflow definition;
- schedule interval, next run, last run, and run history;
- diff summaries between recurring runs;
- destructive tools prohibited from unattended schedules.

**Gate:** save a read-only workflow, run immediately, schedule it, verify a worker run and persisted history, then cancel/retry safely.

### WP-07 — Identity and tenancy

- strict Directus cookie validation;
- project list scoped to organization;
- layer/document/job/edit queries scoped server-side;
- no browser demo tenant header;
- permission matrix tests;
- account login and protected journey acceptance.

**Gate:** two organizations cannot read or mutate each other’s projects, layers, documents, jobs, or exports.

### WP-08 — Professional UI and browser verification

- left chat, centre map, right layer/tools/job inspector;
- no fake cards or placeholder claims;
- accessible keyboard flows;
- clear empty/loading/error/progress states;
- responsive layout;
- browser smoke automation using a real browser;
- screenshot/evidence captured by the release owner, not delegated to the user.

**Gate:** browser executes chat → plan → approval → job → layer/map/result without manual debugging.

## 6. Subagent execution model

Concurrency limit: **2 child instances**.

### Workstream A — Map/layer foundation

Own WP-01, map state, layer tree, basemap/source attribution, selection, inspector, and browser-visible UI. Do not modify agent-run schema or worker files except through a documented interface contract.

### Workstream B — Agent/data/job foundation

Own WP-02, WP-03, WP-04, and worker-facing contracts. Add typed run/step persistence, Gemini system/user message handling, discovery candidates, import approval, and operation registry. Do not rewrite the map UI.

Main session responsibilities:

- create and enforce interface contracts;
- review child diffs and self-reported claims;
- resolve conflicts;
- run live integration tests;
- reject mockup or unverified work;
- own commits/push/release report.

## 7. Definition of done for Phase 1

Phase 1 is not complete until this exact journey passes against the live stack:

```text
Open empty project
→ ask Cartogen AI for a humanitarian mapping objective
→ discover real candidate data
→ approve an import
→ imported layer appears in layer tree/map
→ ask a spatial question
→ review typed operation and assumptions
→ approve operation
→ worker runs with progress
→ result layer appears on map
→ select/inspect feature
→ edit with before/after diff
→ confirm transaction
→ save a read-only workflow
→ run/schedule it
→ read back run history and lineage
→ export a provenance-aware report
```

Open gates must be reported explicitly; no synthetic substitute is acceptable.

## 8. Current truth before execution

Already proven: Gemini live planning, PostGIS persistence, GeoJSON upload/read-back, Leaflet basemap, buffer/intersection workers, export generation, and AI-first three-column shell.

Not yet proven: real dataset discovery/import, typed agent-run persistence, editing/diff transactions, persisted schedules, production organization permissions, and a full browser journey.
