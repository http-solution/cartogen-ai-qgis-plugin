# Cartogen AI Web Mapping Platform — Product and Design Proposal

**Status:** Proposal for approval — no implementation started
**Classification:** Private HTTP-Solution strategy
**Proposed product name:** Cartogen AI Workspace
**Positioning:** A browser-native spatial workspace for collaborative mapping, analysis, reporting, and sector workflows.

## 1. Executive recommendation

Build a new web-native geospatial product inspired by the workflows users value in QGIS, but do not attempt to reproduce the QGIS desktop application one-to-one.

The first product should be a focused, collaborative mapping workspace that lets a user:

1. create or open a project;
2. add data from files, URLs, or managed sources;
3. style and inspect layers;
4. run safe spatial analysis;
5. ask Cartogen AI to explain, plan, and execute visible workflows;
6. collaborate with a team;
7. produce a map, report, or export;
8. preserve provenance, permissions, and audit history.

The browser product should be excellent at collaborative operational mapping. It should not initially promise every desktop capability in QGIS such as arbitrary Python plugins, unrestricted processing providers, advanced desktop layout automation, or offline parity.

## 2. Legal and licensing position

Research baseline:

- QGIS is GPL-2.0 licensed: https://github.com/qgis/QGIS
- QGIS Server provides established OGC services including WMS, WFS, WCS, WMTS, and OGC API Features: https://docs.qgis.org/3.44/en/docs/server_manual/services.html
- PostGIS is an open-source PostgreSQL spatial extension: https://postgis.net/
- OGC API standards provide modern interoperable interfaces for Features, Tiles, and Processes: https://ogcapi.ogc.org/
- MapLibre GL JS is an open-source WebGL vector-tile renderer: https://maplibre.org/maplibre-gl-js/docs/
- OpenLayers provides browser mapping and WebGL rendering capabilities: https://openlayers.org/

The implementation principle is:

- learn from public QGIS concepts and established GIS standards;
- implement original Cartogen code and original Cartogen UX;
- do not copy QGIS source code, assets, UI text, icons, or proprietary-looking implementation fragments without a formal licence review;
- maintain a written provenance record for architecture, dependencies, and copied/adapted code;
- obtain qualified legal advice before using QGIS branding, QGIS source components, or any GPL-linked server/client component in a commercial distribution.

This proposal is product planning, not a legal opinion.

## 3. Product identity

### Product promise

**Turn spatial data into confident operational decisions — together.**

### Brand role

Cartogen AI Workspace should feel:

- professional enough for enterprise GIS teams;
- fast and approachable for non-specialist programme staff;
- transparent enough for humanitarian and public-sector work;
- powerful without exposing unnecessary GIS complexity;
- calm, evidence-oriented, and trustworthy.

### Design principles

1. **Map first:** the map is the primary working surface.
2. **Evidence visible:** every AI suggestion shows inputs, assumptions, tools, and outputs.
3. **Progressive complexity:** simple actions first; advanced controls available when needed.
4. **Safe by default:** destructive edits, sensitive exports, and external data access require explicit review.
5. **Operational clarity:** status, freshness, ownership, and provenance are always visible.
6. **Collaborative by design:** comments, review, version history, and shared projects are core features.
7. **Sector-aware:** humanitarian, engineering, planning, and logistics workflows are first-class experiences.
8. **Accessible and resilient:** responsive interface, keyboard support, strong contrast, low-bandwidth modes, and graceful degradation.

## 4. Target users and jobs-to-be-done

### Humanitarian GIS analyst

Needs to combine population, admin boundaries, facilities, partner presence, needs, and access constraints into decision-ready maps and reports.

### Programme/operations manager

Needs a readable answer without mastering every GIS tool: where are gaps, who is responding, what changed, and what needs attention.

### Engineering/project team

Needs controlled survey, asset, CRS, measurement, QA, and construction-progress workflows.

### Urban planner/local authority

Needs parcels, zoning, land use, accessibility, catchments, scenarios, and stakeholder-readable outputs.

### Logistics planner

Needs network, hubs, routes, travel cost, risk, service levels, and scenario comparison.

### GIS manager/administrator

Needs workspace governance, permissions, data policies, audit visibility, templates, and user management.

## 5. Proposed information architecture

### Global shell

- Cartogen AI logo and workspace switcher;
- project search;
- notifications and review tasks;
- help and documentation;
- account and organization menu;
- connection/status indicator.

### Primary workspace navigation

1. **Projects** — project list, templates, recent work, shared projects.
2. **Map** — main interactive mapping workspace.
3. **Data** — uploads, sources, tables, connections, metadata.
4. **Analysis** — tools, saved workflows, jobs, results.
5. **Reports** — map layouts, dashboards, exports, generated reports.
6. **Activity** — comments, review, versions, audit history.
7. **Admin** — organization, users, roles, budgets, policies; permission-gated.

### Map workspace layout

- **Left rail:** project/layer tree and search.
- **Centre:** map canvas.
- **Right rail:** selected feature, styling, analysis, AI and review panels.
- **Bottom tray:** processing jobs, messages, data warnings, task progress.
- **Top bar:** project title, save/version state, share/review, basemap, scale/coordinate readout.

Avoid copying QGIS desktop menus and panels directly. Use a web-native three-zone workspace with task-oriented panels.

## 6. Core feature list

### A. Account and organization

#### MVP

- email/password authentication through the commercial CMS;
- organization/workspace membership;
- invitations;
- basic roles: Owner, Admin, Editor, Analyst, Viewer;
- account/session management;
- organization usage summary.

#### Enterprise

- OIDC/SAML SSO;
- SCIM provisioning;
- domain verification;
- group-based permissions;
- audit exports;
- customer-managed retention policies.

### B. Project management

#### MVP

- create project from blank or sector template;
- project metadata: title, description, area, sector, owner, sensitivity, CRS;
- project list and search;
- recent projects;
- project duplication;
- project archive and restore;
- autosave and version checkpoints.

#### Enterprise

- project lifecycle states;
- approval workflows;
- project-level retention;
- controlled sharing;
- organization templates;
- cross-project catalog.

### C. Data ingestion and management

#### MVP

- GeoJSON upload;
- CSV with coordinates;
- GeoPackage upload where browser/server processing supports it;
- GeoTIFF upload with asynchronous processing;
- drag-and-drop upload;
- URL-based GeoJSON/OGC source;
- layer metadata and source citation;
- field/type preview;
- upload progress and validation errors;
- size and type limits.

#### Phase 2

- Shapefile ZIP import;
- KML/KMZ;
- WMS/WMTS/OGC API Features connections;
- PostGIS connection through managed connectors;
- SharePoint/OneDrive/ArcGIS service connectors where justified;
- object-storage integration;
- scheduled source refresh.

#### Enterprise

- private data connectors;
- data catalog;
- lineage;
- sensitivity labels;
- data residency options;
- approval for external sources.

### D. Map rendering and layer experience

#### MVP

- vector and raster layers;
- layer visibility and ordering;
- opacity;
- basemap selection;
- pan/zoom/fit;
- feature selection;
- identify popup;
- coordinate readout;
- legend;
- layer search;
- simple point/line/polygon styling;
- categorized and graduated styling;
- label controls;
- map screenshots and shareable views.

#### Phase 2

- expression-based styling;
- heatmaps;
- raster colour ramps;
- temporal slider;
- comparison/swipe view;
- 3D terrain or scene view;
- annotation layer;
- print-oriented map composition.

#### Enterprise

- organization style library;
- approved basemaps;
- cartographic standards;
- branded templates;
- cached/tiled delivery policy.

### E. Editing and field operations

#### MVP

- create point, line, and polygon;
- edit geometry with undo/redo;
- edit attributes;
- validation messages;
- draft versus published state;
- explicit save/commit;
- conflict warning when a shared layer changed.

#### Phase 2

- snapping;
- geometry validity checks;
- forms and conditional fields;
- photo/file attachments;
- offline draft capture with later sync;
- mobile-responsive editing.

#### Enterprise

- approval workflows;
- edit locks;
- field team roles;
- immutable audit history;
- supervisor review.

### F. Spatial analysis

#### MVP

- buffer;
- intersect/clip;
- dissolve;
- spatial join;
- select by location;
- distance/area/length measurement;
- point-in-polygon summary;
- proximity analysis;
- simple statistics;
- export result as a new layer;
- asynchronous job progress;
- reproducible parameters and output metadata.

#### Phase 2

- network routing;
- service areas;
- raster statistics;
- zonal statistics;
- terrain/elevation profile;
- change detection;
- suitability analysis;
- model/workflow chaining.

#### Enterprise

- organization-approved tools;
- resource quotas;
- private processing workers;
- scheduled analyses;
- job history and cost visibility.

### G. Cartogen AI experience

#### MVP

- contextual AI chat inside the project;
- project/layer-aware questions;
- tool-plan preview;
- visible task execution;
- confirmation before edits or exports;
- explanation of assumptions;
- cited data sources where available;
- sector profiles: humanitarian, engineering, urban planning, logistics;
- local/hosted provider policy appropriate to account plan;
- retry, cancel, and inspect job state.

#### Phase 2

- AI-generated workflow presets;
- report drafting;
- map narrative and executive summary;
- anomaly/quality suggestions;
- natural-language layer search;
- multimodal image/document context;
- saved organization prompts.

#### Enterprise

- policy-controlled tools;
- prompt/output retention settings;
- approved model catalogue;
- provider routing policies;
- AI usage audit;
- human review checkpoints;
- organization-level AI budgets.

### H. Reports and sharing

#### MVP

- export GeoJSON/CSV/GeoPackage where supported;
- map image export;
- project share link with permission check;
- generated analysis summary;
- downloadable result package;
- provenance and processing metadata.

#### Phase 2

- PDF map layouts;
- HTML situation reports;
- dashboard views;
- scheduled report generation;
- comments and review pins;
- public/private share modes.

#### Enterprise

- branded report templates;
- approval and publishing workflow;
- external stakeholder portal;
- expiring links;
- watermark and classification labels;
- export audit trail.

### I. Collaboration and governance

#### MVP

- project members;
- comments;
- activity feed;
- version checkpoints;
- viewer/editor permissions;
- share/revoke access;
- basic audit events.

#### Enterprise

- RBAC and SSO;
- review/approval states;
- immutable audit records;
- legal hold/export;
- organization policy engine;
- administrator activity reports.

### J. Sector workspaces

#### Humanitarian aid — first package

- 3W/4W templates;
- admin-level coverage gap analysis;
- affected population and needs layers;
- facility and service catchments;
- access/route-risk layers;
- severity/vulnerability analysis;
- situation-map template;
- data sensitivity warnings;
- do-no-harm review checklist.

#### Engineering

- survey/CRS QA;
- asset inventory;
- condition/status styling;
- construction progress;
- measurements and buffers;
- inspection forms;
- engineering map/report template.

#### Urban planning

- parcels/zoning/land-use template;
- accessibility and catchments;
- service equity analysis;
- development scenario comparison;
- stakeholder map template.

#### Logistics

- hubs and depots;
- origin/destination tables;
- route and travel-cost analysis;
- service-level coverage;
- hazard-aware route comparison;
- logistics dashboard/report.

## 7. Technical architecture proposal

### Frontend

- TypeScript;
- React/Next.js or a comparable component framework;
- MapLibre GL JS for vector-tile/WebGL rendering;
- OpenLayers where OGC/raster/editing capabilities are more suitable;
- accessible design system with Cartogen tokens;
- web workers for client-side parsing and lightweight geometry operations;
- resumable uploads and progressive loading.

### API and services

- REST/OpenAPI for public service contracts;
- WebSocket or Server-Sent Events for job progress and collaboration events;
- separate authentication, project, data, analysis, report, and AI service boundaries;
- background job queue for imports, raster processing, exports, and AI workflows;
- signed download URLs;
- tenant-aware authorization at every data access boundary.

### Spatial data layer

- PostgreSQL/PostGIS for managed vector data and project metadata;
- object storage for originals, rasters, exports, and attachments;
- vector tiles for high-performance display;
- OGC API Features/Tiles for interoperable access;
- optional QGIS Server integration for selected standards-compatible services;
- raster tiling/COG strategy for large imagery.

### Processing layer

- safe server-side spatial workers;
- isolated execution for expensive or untrusted operations;
- explicit tool registry;
- resource quotas and cancellation;
- provenance for inputs, parameters, versions, and outputs;
- no arbitrary browser-submitted SQL or Python.

### AI layer

- Cartogen AI orchestration API;
- tool-plan preview and confirmation;
- sector profiles;
- provider routing and budgets;
- tenant-level policy checks;
- redacted logs and configurable retention;
- human review for sensitive or destructive operations.

### Deployment

#### MVP

- Docker Compose for local and single-tenant managed deployment;
- reverse proxy/TLS;
- Postgres/PostGIS;
- object storage;
- background worker;
- monitoring and backups.

#### Enterprise

- Kubernetes only when customer demand justifies it;
- private networking;
- managed database option;
- separate worker pools;
- SSO and secrets manager;
- data residency and customer-managed keys where required.

## 8. Data and security model

- tenant ID on every organization-owned record;
- deny-by-default authorization;
- project and layer permission checks server-side;
- signed, expiring export/download URLs;
- file-type validation and malware scanning for uploads;
- size and resource quotas;
- rate limits;
- audit events for access, edits, exports, AI actions, and administration;
- encryption in transit and at rest;
- configurable retention/deletion;
- sensitive humanitarian data warnings;
- no secrets in browser bundles;
- no arbitrary user-supplied Python execution in the browser platform;
- explicit separation of observation, inference, and AI-generated suggestion.

## 9. MVP definition

The MVP is not “QGIS in a browser.” It is:

> A collaborative humanitarian mapping workspace that ingests common vector data, renders and styles layers, performs core spatial analysis, supports safe AI-assisted workflows, and produces a decision-ready map/report.

### MVP must include

- authentication and organization workspace;
- project creation;
- GeoJSON/CSV upload;
- vector map rendering;
- layer tree and identify;
- basic styling;
- core vector analysis;
- asynchronous jobs;
- AI plan preview and confirmation;
- humanitarian templates;
- permissions and sharing;
- provenance;
- export;
- monitoring, backups, and security baseline.

### Explicit MVP exclusions

- full QGIS Processing provider parity;
- arbitrary desktop plugin execution;
- unrestricted Python console;
- complete print-layout parity;
- full raster science stack;
- offline parity;
- multi-region high availability;
- every OGC service;
- unrestricted public sharing;
- custom enterprise integrations before core tenancy/security is proven.

## 10. Delivery phases

### Phase 0 — discovery and validation

- interview humanitarian, engineering, planning, and logistics users;
- test the proposed workspace information architecture;
- validate data formats and first workflows;
- confirm legal/provenance boundaries;
- select frontend/rendering stack through a short spike;
- produce clickable prototype and threat model.

**Gate:** five design partners confirm the MVP workflows and data assumptions.

### Phase 1 — web mapping foundation

- authentication and workspace;
- project model;
- uploads and validation;
- PostGIS/object storage;
- map rendering;
- layer tree;
- basic style and identify;
- audit/event foundation.

**Gate:** a user can upload data, style it, save a project, and share it safely.

### Phase 2 — analysis and humanitarian workflows

- core analysis jobs;
- job status/cancellation;
- provenance;
- 3W/4W and coverage-gap templates;
- needs/severity/access workflows;
- map/report export;
- AI plan/confirm/execute flow.

**Gate:** a design partner completes one recurring humanitarian workflow without founder intervention.

### Phase 3 — collaboration and commercial controls

- organizations and RBAC;
- billing/entitlements;
- quotas/budgets;
- comments/review;
- versioning;
- customer portal;
- monitoring/support tools.

**Gate:** three pilot organizations can be onboarded, governed, billed, supported, and renewed.

### Phase 4 — sector expansion

- engineering package;
- urban-planning package;
- logistics package;
- reusable templates and sector reports;
- connectors based on validated demand.

### Phase 5 — enterprise deployment

- SSO/SCIM;
- private deployment;
- data-residency options;
- advanced audit and retention;
- procurement/security evidence;
- supported upgrade and SLA model.

## 11. Commercial packaging proposal

### Community Web Preview

- low-friction evaluation;
- limited workspace/storage/resource quota;
- public-good and personal projects;
- no promise of enterprise retention or SLA.

### Professional Workspace

- managed AI access;
- private projects;
- higher quotas;
- exports;
- standard support;
- individual or small-team use.

### Team/Organization Workspace

- RBAC;
- shared projects;
- audit events;
- workflow templates;
- team budgets;
- training and onboarding;
- priority support.

### Enterprise Workspace

- SSO/SCIM;
- private or controlled deployment;
- data policies;
- integrations;
- security/procurement pack;
- RTO/RPO and SLA only when evidenced.

## 12. Success metrics

### Product

- time to first map;
- time to first useful analysis;
- upload success rate;
- analysis success rate;
- AI plan acceptance rate;
- export completion rate;
- repeat weekly workflow rate.

### Commercial

- workspace activation;
- paid conversion;
- expansion;
- churn;
- provider cost per successful workflow;
- gross margin;
- onboarding hours;
- support hours;
- customer acquisition source;
- renewal rate.

### Trust and operations

- incidents;
- failed jobs;
- backup success;
- restore-test success;
- mean time to detect;
- mean time to recover;
- permission violations;
- export/audit completeness.

## 13. Key risks and mitigations

### Scope explosion

**Risk:** attempting to reproduce all of QGIS.

**Mitigation:** humanitarian workflow MVP; strict exclusions; sector gates.

### Performance and cost

**Risk:** large rasters, complex analysis, and AI workflows make browser/service costs unpredictable.

**Mitigation:** quotas, asynchronous jobs, tiling, caching, worker isolation, usage metering.

### Licensing confusion

**Risk:** accidental source/UI/brand reuse or unclear obligations.

**Mitigation:** clean-room implementation record, dependency licence inventory, legal review, original Cartogen design system.

### Data sensitivity

**Risk:** humanitarian data may include vulnerable populations or sensitive facilities.

**Mitigation:** minimization, classification, retention controls, access review, aggregation defaults, audit trails.

### Desktop gap

**Risk:** users expect every QGIS capability immediately.

**Mitigation:** position as a collaborative operational workspace, maintain desktop interoperability, publish capability matrix.

### Founder dependency

**Risk:** delivery, support, and sales rely on Baron.

**Mitigation:** onboarding playbooks, partner delivery, documentation, support severity model, repeatable templates.

## 14. Approval gates before implementation

Do not begin the full build until Baron approves:

1. product name and positioning;
2. MVP scope and exclusions;
3. primary humanitarian workflow;
4. frontend/rendering stack spike;
5. data/storage architecture;
6. licensing/provenance approach;
7. tenancy and security model;
8. commercial packaging assumptions;
9. design-partner validation plan;
10. implementation budget and delivery sequence.

## 15. Research references

- QGIS source repository and GPL-2.0 notice: https://github.com/qgis/QGIS
- QGIS Server services: https://docs.qgis.org/3.44/en/docs/server_manual/services.html
- PostGIS: https://postgis.net/
- OGC API standards: https://ogcapi.ogc.org/
- OGC API Features: https://www.ogc.org/standards/ogcapi-features/
- OGC API Tiles: https://www.ogc.org/standards/ogcapi-tiles/
- MapLibre GL JS: https://maplibre.org/maplibre-gl-js/docs/
- OpenLayers: https://openlayers.org/
