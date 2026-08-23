# Cartogen AI Workspace — Phase 0 Architecture Spike

**Status:** Decision record for validation, not production implementation

## Candidate rendering approaches

### Option A — MapLibre-first

- Strengths: WebGL vector-tile rendering, modern browser performance, original Cartogen UI freedom, good fit for vector-tile workspaces.
- Risks: more work for OGC/raster/editing edge cases; requires a deliberate tile/data pipeline.
- Fit: recommended for the primary map canvas.

### Option B — OpenLayers-first

- Strengths: mature GIS/browser abstractions, strong OGC and raster capabilities, broad projection/source support.
- Risks: more framework surface and a less opinionated UX; may require additional performance tuning for very large vector scenes.
- Fit: strong candidate for OGC-heavy and editing modules.

### Option C — Hybrid MapLibre/OpenLayers

- Strengths: choose the best renderer/source per layer type; supports vector-tile performance and OGC/raster interoperability.
- Risks: two rendering models, more testing, possible interaction/style differences.
- Fit: likely long-term architecture, but validate through a small spike before committing.

**Initial recommendation:** build a time-boxed MapLibre-first spike with one OGC/OpenLayers comparison path. Do not commit to a hybrid until a concrete data case requires it.

## Data architecture candidates

### Managed spatial data

- PostGIS for vector features, project metadata, permissions, and spatial indexes;
- object storage for original uploads, rasters, exports, and attachments;
- vector tile generation/caching for display;
- OGC API Features/Tiles for interoperable APIs;
- Cloud Optimized GeoTIFF strategy for large rasters.

### External sources

- GeoJSON/CSV uploads;
- WMS/WMTS;
- OGC API Features;
- approved PostGIS connectors;
- managed SharePoint/OneDrive connectors after core tenancy is secure.

## Processing architecture

- browser: parsing, previews, lightweight operations, UI state;
- API: validation, authorization, job creation, metadata;
- workers: buffers, joins, intersections, routing, raster jobs, exports;
- job queue: progress, cancellation, retries, resource quotas;
- provenance store: source IDs, parameters, software versions, result IDs.

Do not run arbitrary user Python or unrestricted SQL in the web platform.

## AI architecture

1. User asks a project-aware question.
2. Cartogen AI identifies relevant layers and missing context.
3. AI returns a visible plan with tools, inputs, assumptions, and expected outputs.
4. User reviews and confirms.
5. Server executes approved tools through a policy-controlled registry.
6. Results, logs, provenance, and warnings are shown in the activity panel.

Sensitive or destructive operations must require explicit review.

## Tenancy model

Every organization-owned object must carry a tenant boundary:

- organization;
- workspace/project;
- layer/source;
- job/result;
- report/export;
- activity/audit event.

Authorization must be enforced server-side. Client-side hiding is not security.

## Spike experiments

Time-box each experiment to 1–3 days:

1. render a vector-tile humanitarian sample in MapLibre;
2. render the same source through OpenLayers;
3. upload GeoJSON and produce a preview;
4. query PostGIS with tenant-aware project scope;
5. run one asynchronous buffer/intersection job;
6. stream job progress to the browser;
7. generate a signed result download;
8. record provenance metadata;
9. measure first render, layer toggle, select, and job-completion times;
10. verify keyboard navigation and responsive layout.

## Initial performance targets

These are targets for validation, not guarantees:

- workspace shell visible within 2 seconds on a normal broadband connection;
- first map view usable within 4 seconds for the pilot dataset;
- layer toggle response under 250 ms after data is loaded;
- feature identify response under 500 ms for indexed vector data;
- job status visible within 1 second of state change;
- exports never block the browser main thread.

## Architecture decision gate

Choose the production stack only after the spike records:

- rendering performance;
- OGC compatibility;
- editing behavior;
- accessibility;
- data-size limits;
- operational complexity;
- licence compatibility;
- hosting/provider cost;
- developer productivity.

## Not selected yet

The following decisions remain open until Phase 0 evidence exists:

- Next.js versus another React application shell;
- MapLibre-only versus hybrid rendering;
- tile service implementation;
- queue technology;
- object-storage provider;
- managed versus self-hosted PostGIS;
- multi-tenant versus single-tenant default deployment;
- offline sync approach;
- commercial usage-metering design.
