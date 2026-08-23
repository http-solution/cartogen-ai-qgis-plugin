# Cartogen AI Workspace — Phase 1 Vertical Slice

**Status:** Started
**Scope:** Pakistan humanitarian service-coverage screening
**Repository:** Private `CARTOGEN-AI`

## Run locally

Start PostGIS:

```bash
docker compose up -d postgis
```

Start the API-backed workspace:

```bash
npm install
npm start
```

Open:

```text
http://127.0.0.1:4180/index.html
```

API health:

```text
http://127.0.0.1:4180/api/health
```

The earlier static-only preview remains available on port 4175 if needed, but Phase 1 development should use the API-backed server.

## Included in this slice

- Cartogen AI Workspace shell;
- project/layer workspace;
- source catalogue;
- real Pakistan public-data summary loaded from `demo-data.json`;
- 714 Pakistan 3W presence records;
- 4,849 health facilities;
- accessibility source summaries;
- logistics/security/IT source metadata;
- source freshness labels;
- population/boundary compatibility warning;
- humanitarian coverage-screening question;
- AI plan preview and safe-run state;
- provenance/limitation export;
- humanitarian map/legend/status presentation.

## Rebuild demo data

```bash
python web-platform/phase-1/scripts/build_demo_data.py
```

The script reads the locally downloaded Phase 0 bundle and creates the non-sensitive summary consumed by the browser slice.

## Phase 1 acceptance checks

- [x] Project workspace loads.
- [x] Source catalogue loads.
- [x] Pakistan 3W count is data-backed.
- [x] Healthsites count is data-backed.
- [x] Freshness warnings are visible.
- [x] Compatibility warning is visible.
- [x] AI plan is reviewable before execution.
- [x] Safe-run state confirms source data is not modified.
- [x] Structured provenance report can be exported.
- [x] Real PostGIS/API persistence for projects and layers.
- [x] GeoJSON FeatureCollection ingestion into PostGIS.
- [x] Tenant/organization boundary on project and layer queries.
- [x] Spatial extent read-back from PostGIS.
- [x] Browser GeoJSON upload to the API.
- [x] Geometry read-back and SVG rendering for the workspace map.
- [x] Narrative/document/source context creates a structured reviewable plan.
- [x] Approved plan creates a persisted workspace task and queued analysis job.
- [x] Approved queued job executes a persisted humanitarian review summary.
- [x] PostGIS buffer job creates a derived result layer and preserves provenance.
- [x] Spatial Operations panel exposes source-layer selection, distance, execution, and result status.
- [x] Feature inspector displays selected geometry type, properties, and provenance-review status.
- [x] Attribute table filters rendered feature properties and exports filtered GeoJSON.
- [x] Style and Legend panel applies thematic presets and opacity to rendered geometry.
- [x] A4 print preview and downloadable HTML humanitarian report layout.
- [x] Configurable paper size, orientation, title, author, and warning visibility.
- [x] Server-backed export job persists layout and serves reproducible HTML output.
- [x] Server export embeds stored PostGIS geometry as SVG in the report map frame.
- [x] Server-backed PDF rendering with configured paper size and orientation.
- [x] Reports UI exposes Download PDF and uses the persisted export job.
- [x] Dynamic north arrow and scale bar displayed in the workspace map.
- [x] Dynamic legend generated from the stored project layer list and synchronized to exports.
- [x] Multi-page situation report with summary, map/register, limitations, provenance appendix, and version metadata.
- [x] Export History panel lists persisted HTML/PDF reports with title, type, version, status, and timestamps.
- [x] Situation-report page numbering is deterministic and embedded as Page N of 4.
- [x] OpenAI-compatible Cartogen gateway adapter with structured-plan validation and fallback.
- [ ] Live gateway chat completion certified with aligned runtime credentials.
- [ ] Real asynchronous spatial processing.
- [ ] Real authentication and organization permissions.
- [ ] Real PDF/print export engine.

The unchecked items are the next implementation slices; this artifact is intentionally a data-backed interface vertical slice, not production SaaS infrastructure.
