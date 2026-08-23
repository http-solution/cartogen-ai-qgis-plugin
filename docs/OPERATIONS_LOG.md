# HTTP-Solution / Cartogen AI Operations Log

This private log records public-repository operations, release preparation, security documentation, and repository-boundary decisions. Do not copy this file into the public Community repository.

## 2026-08-23 — Community/private repository split and public documentation pass

### Repository boundary

- Full internal repository: `cartogenai-glitch/CARTOGEN-AI`
  - Visibility: private
  - Local source: `C:\Cartogen-AI-Core\cartogen-ai`
  - `main`: full internal tree
  - `internal-full-backup`: preserved full-tree backup
- Public Community repository: `cartogenai-glitch/cartogen_ai_community`
  - Visibility: public
  - Local source: `C:\Cartogen-AI-Core\cartogen-ai-community-limited`
  - `main`: limited Community distribution

### Public provider policy

The public Community build exposes exactly two provider choices:

1. Ollama local endpoint — no API key.
2. Cartogen AI hosted endpoint — Cartogen AI key only.

Removed from the public distribution:

- OpenRouter, Gemini, OpenAI, and Claude provider modules;
- provider-specific API-key fields and runtime selection;
- Gemini/OpenAI grounded-search tools;
- hosted billing, pricing, service, tier, and private-deployment material;
- internal product reviews, commercial roadmap documents, and private architecture notes.

The full provider and service implementation remains in this private repository.

### Public documentation published

- README branding, provider scope, installation, testing, security, and release links;
- `SECURITY.md` with implemented protections, adversarial verification, limitations,
  credential handling, and responsible disclosure guidance;
- `docs/TESTING_AND_RELEASE.md` with test commands, CI behavior, QGIS smoke-test gates,
  and release checklist;
- clean Community `CHANGELOG.md` and `metadata.txt` without commercial history;
- corrected issue templates and user guide for the two-provider public surface.

### Verification evidence

- Public limited build: 620 tests passed, 0 failures, 34 optional dependency skips.
- Python compilation passed.
- Markdown local-link scan passed with 0 broken links.
- Public provider directory contains only `ollama.py` and `cartogen.py` plus shared base/export files.
- Public tree contains no `service/`, `DOCUMENTATION.md`, tier/pricing files, or private gateway paths.
- Public `main` final commit: `fef731ab842ce3ba7070ad5905854c4cd2183971`.
- Full private `CARTOGEN-AI/main`: `5e4bb6f`.

### Release/security status

- Automated checks are green for the public limited build.
- Interactive QGIS smoke testing remains a release gate and must be completed in a real
  QGIS session before claiming a fully smoke-tested release.
- Public GitHub tag: `v1.4.2` at commit `fef731ab842ce3ba7070ad5905854c4cd2183971`.
- GitHub release: [Cartogen AI Community v1.4.2](https://github.com/cartogenai-glitch/cartogen_ai_community/releases/tag/v1.4.2).
- Release state: published pre-release, pending the interactive QGIS smoke-test gate.
- Release asset: `cartogen_ai_v1.4.2.zip` (325,443 bytes).
- Release asset URL: https://github.com/cartogenai-glitch/cartogen_ai_community/releases/download/v1.4.2/cartogen_ai_v1.4.2.zip
- Release asset SHA-256: `f159fffc297dc5a1fa52ed69be2c4eb63ff0620cf4982497e1a7d79993b6f999`.
- No credentials, tokens, or private infrastructure values were recorded in this log.

## Product governance baseline — 2026-08-23

- Significant changes receive a version, changelog entry, test evidence, release decision,
  and GitHub release record when the release gate is complete.
- Community/public scope is documented in `cartogen-ai-community-limited/docs/COMMUNITY_SCOPE.md`.
- Private release governance is documented in `docs/RELEASE_GOVERNANCE.md`.
- Private commercial strategy is documented in `docs/COMMERCIAL_PRODUCT_STRATEGY.md`.
- Commercial differentiation is based on managed operations, governance, deployment, integrations,
  onboarding, support, and service commitments — not artificial removal of core GIS capability.
- Public and private feature-placement decisions must be recorded before a significant feature ships.

## Commercial Service v0.2.0 — local SaaS foundation

- Added Directus CMS/authentication integration foundation and HTTP-only website sessions.
- Added local client portal pages for registration, login, account state, and checkout entry.
- Added Docker Compose services for Postgres, Directus, LiteLLM, and the website.
- Added Postgres initialization for separate Directus, LiteLLM, and website databases.
- Added VPS-oriented `.env.example`, website Dockerfile, health endpoint, and SaaS architecture guide.
- Added Directus user identity to Stripe checkout metadata and subscription records.
- Verified `node --check`, `npm install --package-lock-only` with zero reported vulnerabilities,
  and `docker compose --env-file .env.example config`.
- Not production-ready yet: live Stripe, SMTP, domain/TLS, provider credentials, backups,
  monitoring, and real end-to-end VPS checkout/webhook/key lifecycle remain acceptance gates.

## Commercial Service v0.2.1 — container and local-runbook patch

- Added clean Docker build argument handling and website `.dockerignore`.
- Documented local ports, CMS/portal/health URLs, Directus role setup, VPS deployment,
  troubleshooting, backup, and acceptance steps in `service/LOCAL_VPS_RUNBOOK.md`.
- Local stack verified with Postgres healthy, Directus `/server/health` returning 200,
  LiteLLM running on internal port 4000/local host mapping 4001, and website `/healthz`
  returning 200 on local host mapping 3001.
- Local website image built successfully with npm audit reporting zero vulnerabilities.
- Directus public registration remains intentionally blocked until the minimal customer-role
  permission is configured and verified; no broad anonymous permission was granted.

## Commercial Service v0.2.3 — release metadata synchronization

- Synchronized the website package version and service changelog after the protected
  `commercial-v0.2.2` tag.
- Published private pre-release: https://github.com/cartogenai-glitch/CARTOGEN-AI/releases/tag/commercial-v0.2.3
- Final private service commit: `981333d`.

## Commercial Service v0.2.4 — portal/session polish

- Portal greeting now falls back safely to the authenticated Directus user ID when optional
  profile fields are not readable by the customer policy.
- Local Directus registration/session smoke test verified: registration 201, `/api/me` 200,
  logout 200.

## Commercial Service v0.2.5 — billing activation test and config consistency

- Added `service/scripts/local_saas_smoke.sh` for repeatable registration-to-API activation testing.
- Local smoke results: registration/session PASS; simulated webhook PASS; single-use key retrieval
  PASS; replay rejection PASS; subscription activation/linkage PASS; LiteLLM `/v1/models` authorization PASS.
- Stripe checkout is BLOCKED locally until real/test Stripe credentials and `STRIPE_PRICE_ID` are configured.
- Pro-client download/entitlement is BLOCKED because no Pro artifact or download route exists yet.
- Fixed website/LiteLLM master-key drift in Compose by explicitly passing the interpolated key.

## Commercial Service v0.2.6 — security assessment and hardening

- Security assessment completed across dependencies, secrets, Docker exposure, authentication,
  webhooks, rate limiting, headers, and configuration boundaries.
- Remediated all confirmed local configuration/application findings: loopback bindings,
  opt-in registration, digest-pinned images, Helmet headers, rate limits, malformed-webhook safety,
  and website/LiteLLM master-key consistency.
- Evidence: npm audit 0 vulnerabilities, secret-pattern scan 0 files, Compose config valid,
  malformed webhook 400 with process health preserved, and all local services healthy.
- Residual gates: pip-audit in CI/VPS, SMTP/password reset, backups, monitoring, live Stripe,
  Pro entitlement/download, and production TLS/firewall review.

## Plugin UI v1.4.3 — cross-edition interface terminology

- Audited public Community and private commercial QGIS UI source side by side.
- Standardized tabs to `Chat`, `Tasks & Notes`, and `Help & Guide`.
- Standardized memory panel wording to `Project Notes & Memory`.
- Normalized commercial provider labels to Hosted/Local terminology and clarified Settings as `Connection`.
- Updated help copy and public/private changelogs.
- Verification: Community suite 620 passed; private suite 691 passed; both Python compile checks passed.
- Public Community release: [v1.4.3](https://github.com/cartogenai-glitch/cartogen_ai_community/releases/tag/v1.4.3), commit `d5a980b`, ZIP SHA-256 `c5519c0b7e4b8e9e8faf299531f0812a498448e15420954cea5332acbc304a2a`.
- Private commercial-plugin release: [commercial-plugin-v1.4.3](https://github.com/cartogenai-glitch/CARTOGEN-AI/releases/tag/commercial-plugin-v1.4.3), commit `cb54e32`.

## Plugin sector experience v1.4.4

- Added sector-aware prompt guidance across both editions.
- Priority sequence: humanitarian aid, engineering, urban planning, then logistics.
- Additional profiles: agriculture, environment, public health, disaster risk, utilities,
  transport, public safety, research, real estate, and defense/intelligence.
- Public guide: `docs/SECTOR_WORKFLOWS.md`.
- Private strategy: `docs/SECTOR_PRODUCT_STRATEGY.md`.
- Enterprise business-gap assessment and prioritized delivery backlog: `docs/ENTERPRISE_GROWTH_PLAN.md`.
- Current recommendation: treat humanitarian aid mapping as the commercial beachhead and
  validate a paid Starter package before broad enterprise platform expansion.

## Private Community sustainability and funding plan

- Added `docs/COMMUNITY_SUSTAINABILITY_AND_FUNDING_PLAN.md`.
- This plan is private-only and must not be copied into `cartogen_ai_community` without an
  explicit publication decision.
- Recommended revenue/funding mix: sponsorship, grants, training, implementation, support,
  research partnerships, managed service conversion, and emergency mapping retainers.
- Guardrail: preserve a useful GPL Community edition and monetize operational value rather than
  charging for GPL rights or manufacturing artificial feature deprivation.

## Cartogen AI Web Mapping Platform proposal

- Added private-only `docs/WEB_CARTOGEN_PRODUCT_PLAN.md`.
- Proposed a new browser-native collaborative mapping workspace inspired by QGIS workflows,
  not a browser port or source-code reuse of QGIS.
- MVP focus: humanitarian operational mapping with project/data/layer management, core vector
  analysis, safe AI plans, collaboration, provenance, reports, permissions, and exports.
- Explicitly excluded from MVP: full QGIS parity, arbitrary Python/plugin execution, unrestricted
  Processing provider support, full raster science, and offline parity.
- Research references include QGIS GPL-2.0, QGIS Server/OGC services, PostGIS, OGC APIs, MapLibre,
  and OpenLayers.
- No implementation started; approval gates are required before the build begins.

## Humanitarian Phase 0 exit-gate build

- Added private local Validation Hub: `web-platform/phase-0/validation-hub/index.html`.
- Added candidate pipeline, stage filtering, workflow/data/pilot/funding signals, prototype score,
  JSON export, and five-gate readiness dashboard.
- Added `HUMANITARIAN_PILOT_CHARTER.md` and `HUMANITARIAN_CANDIDATE_SCORING.md`.
- Validation Hub and original prototype both served successfully with HTTP 200.
- Candidate data is browser-local only; users must not enter sensitive beneficiary or operational data.
- Public repository remains unchanged.

## OCHA/HDX public 3W structured analysis

- Analyzed the public OCHA Global Humanitarian Operational Presence 3W resource `global-3w-2023-06-08.xlsx`.
- Dataset metadata modified: 2026-07-22; operational resource created/modified: 2023-06-08.
- Extracted 11,306 rows, 55 countries, 31 sectors, 4,885 organization strings, and 161 exact duplicate rows.
- Normalized mixed-format `3w date` values to an operational range of 2019-06-01 through 2023-05-01.
- Key caveat: current catalogue metadata does not mean the operational resource is current; use it as historical baseline unless newer country-level data is found.
- Report: `web-platform/phase-0/OCHA_3W_STRUCTURED_ANALYSIS_2026-08-23.md`.

## Pakistan Phase 0 public humanitarian data bundle

- Added reproducible downloader: `web-platform/phase-0/scripts/build_pakistan_bundle.py`.
- Added Pakistan-only 3W extractor: `web-platform/phase-0/scripts/extract_3w_pakistan.py`.
- Bundle sources: OCHA 3W, COD administrative boundaries, COD population, Healthsites,
  HOT/OSM roads, Pakistan HNO, and WFP ADAM flood-event data.
- Downloaded and validated locally: 7 source resources; archives test clean; population CSV 131 rows;
  Healthsites CSV 4,849 rows; derived Pakistan 3W CSV 714 rows.
- Raw downloaded files are ignored from Git; manifest and reproducible scripts are retained.
- Important caveat: the 2017 population source is not directly compatible with newer boundaries
  without a crosswalk; HNO is a 2021 snapshot; the 3W operational resource is historical to 2023;
  the flood layer is event-specific.

## Operational extensions catalogue and local validation

- Added `web-platform/phase-0/data/HUMANITARIAN_OPERATIONAL_EXTENSIONS_CATALOG.md`.
- Added reproducible downloader `web-platform/phase-0/scripts/build_operational_extensions.py`.
- Downloaded and validated eight extension resources: ACLED aggregated security workbook,
  World Bank infrastructure indicators, three HOT accessibility CSVs, Pakistan airports,
  and Afghanistan 2026 operational presence/capacity CSVs.
- Local validation counts: infrastructure 1,488 rows; education access 2,426; hospitals 7,716;
  primary healthcare 6,846; airports 195; Afghanistan presence 10,098; Afghanistan capacity 7,094.
- ACLED detailed event access remains subject to provider access/licence controls.
- No verified open Pakistan telecom tower/coverage layer was found; World Bank indicators are
  country-level context, not a local coverage map.

## Phase 0 provisional exit

- Phase 0 research/design work is provisionally closed and parked.
- Phase 1 preparation is authorized using the Pakistan humanitarian screening workflow.
- Customer-validation gates remain open and are explicitly not marked as passed.
- Exit record: `web-platform/phase-0/PHASE_0_EXIT_RECORD.md`.
- Phase 1 starting scope: project/data catalogue, 3W ingestion, boundaries, population/facilities/
  accessibility layers, freshness warnings, coverage screening, AI review flow, and map export.

## Phase 1 humanitarian workspace vertical slice

- Added private Phase 1 workspace: `web-platform/phase-1/index.html`.
- Added generated demo summary: `web-platform/phase-1/demo-data.json`.
- Added reproducible summary builder: `web-platform/phase-1/scripts/build_demo_data.py`.
- Local verification: Phase 1 HTML and data served HTTP 200; 714 Pakistan 3W records and 4,849
  health facilities loaded from the downloaded public bundle; source catalogue and compatibility warnings visible.
- Current slice is an interface/data-backed vertical slice. PostGIS/API persistence, real geometry
  rendering, asynchronous processing, authentication, and PDF generation remain next implementation gates.

## Phase 1 PostGIS/API foundation

- Added `web-platform/phase-1/docker-compose.yml` with local PostGIS.
- Added projects/layers/features schema with PostGIS geometry and GiST indexes.
- Added `web-platform/phase-1/server.js` API for health, project listing, layer listing, and GeoJSON ingestion.
- Added organization boundary via request identity; production auth remains a later Directus integration gate.
- Verified against live PostGIS: health 200, project list 200, GeoJSON ingestion 201, spatial extent read-back,
  invalid GeoJSON 400.
- Added Node tests: 4 passed; Phase 1 npm audit: 0 vulnerabilities; Node syntax passed.
- Corrected Express 5 catch-all compatibility before verification.

## Phase 1 browser-to-PostGIS layer flow

- Added browser GeoJSON upload control to `web-platform/phase-1/index.html`.
- Added `GET /api/layers/:layerId/geojson` for server-side geometry read-back.
- Verified on the corrected API listener: health 200, upload 201, GeoJSON FeatureCollection read-back 200 with geometry coordinates preserved.
- Development port is documented as 4180 because earlier orphaned listeners occupied 4176–4179; no forced process termination was performed.

## Phase 1 geometry rendering

- Added SVG geometry overlay to the workspace map surface.
- Added browser-side rendering for Point, LineString, Polygon, and multi-geometries.
- Added automatic extent fitting from PostGIS GeoJSON read-back.
- Workspace now loads the latest project layer geometry from the API on startup.
- Verification: SVG overlay/static checks passed; API health and workspace HTTP 200; four Node tests passed.

## Product requirement confirmation — embedded Cartogen AI analyst

- Confirmed as a core web-platform requirement: users can provide narrative, documents, tabular data,
  geospatial sources, and selected project layers to the AI assistant.
- The assistant must create an inspectable plan, identify missing information and risks, request confirmation,
  execute approved tools, create layers/reports/tasks, and preserve provenance and limitations.
- Current Phase 1 UI has the reviewable-plan state; document ingestion, real tool execution, and task creation
  remain implementation slices rather than completed capabilities.

## Phase 1 narrative-to-task planning slice

- Added deterministic planning adapter `POST /api/ai/plan` for narrative/document/source context.
- Added `workspace_tasks` and `analysis_jobs` PostGIS database tables.
- Added task creation with proposed/approved states and queued analysis jobs.
- Verified live: plan 200 with humanitarian sector and document/coverage steps; approved task 201;
  queued analysis job created; task listing 200.
- This is an explicit provider-independent planning contract, not a claim of live LLM inference.
  Real Cartogen model-gateway execution remains the next adapter integration.

## Phase 1 Cartogen gateway adapter

- Added OpenAI-compatible gateway adapter behind `CARTOGEN_AI_PLANNER_MODE=live`.
- Added structured JSON response validation and fenced-JSON handling.
- Added safe deterministic fallback when the live gateway key/configuration is unavailable.
- Added unit coverage for valid and malformed gateway plan responses.
- Gateway `/v1/models` is reachable locally with the active Compose credential context; live chat
  completion is not yet certified because host/example key configuration differs from the active gateway context.

## Phase 1 approved-task executor

- Added `POST /api/analysis-jobs/:jobId/run` and `GET /api/analysis-jobs/:jobId`.
- Implemented the first safe executor: `create_review_output` reads stored PostGIS layers,
  feature counts, extents, source metadata, and limitations into a persisted humanitarian review summary.
- Verified live: plan 200, task approval 201, job execution 200/completed, job read-back 200.

## Phase 1 PostGIS buffer executor

- Added `POST /api/projects/:projectId/analysis-jobs` for `buffer_layer` jobs.
- Added a safe PostGIS executor using metre-based geography buffering.
- Derived layers preserve source layer, distance, licence, and operation metadata.
- Verified live: buffer job created 201, completed 200, result GeoJSON 200, two Polygon features returned.

## Phase 1 visible spatial operations UI

- Added a visible Spatial Operations panel to the workspace Analysis screen.
- Added source-layer selection, metre distance input, execution button, completion notice, and map refresh.
- Static/UI checks passed; eight Node tests and npm audit remain green.

## Phase 1 visible derived-layer manager

- Added Project result layers panel with Source/Derived badges, feature counts, operation/source metadata,
  Show and Hide controls, and automatic refresh after buffer execution.
- This makes PostGIS-derived outputs visible and manageable in the workspace UI.

## Phase 1 feature inspector

- Map geometry interaction is enabled for the SVG overlay.
- Clicking a rendered geometry now opens the Feature inspector with geometry type, properties,
  provenance-review status, and a safe text-rendered properties block.
- Uploaded properties are escaped before display to prevent HTML injection.

## Phase 1 attribute table and filtered export

- Added feature table for the active rendered layer.
- Added case-insensitive property filtering.
- Added row-to-feature selection and shared inspector behavior.
- Added filtered GeoJSON export from the browser.
- Verification: attribute-table/static checks passed; eight Node tests and npm audit remain green.

## Phase 1 selection synchronization

- Added map/table shared feature selection state.
- Clicking a rendered geometry now selects the corresponding feature record.
- Selecting a table row highlights the corresponding geometry.
- Selected geometry receives a visible high-contrast stroke for review.

## Phase 1 thematic symbology

- Added Style and Legend controls for Coverage screening, Facilities and services,
  Accessibility context, and Risk/exposure review.
- Added layer opacity control and synchronized legend heading.
- Verification: style-panel/static checks passed; eight Node tests and npm audit remain green.

## Phase 1 professional print/export layout

- Added A4 landscape print preview generation.
- Added downloadable HTML report output.
- Report includes title, subtitle/date, CRS, map frame, legend, source/resource dates,
  data-quality warnings, limitations, and humanitarian screening disclaimer.
- Embedded script token diagnostic passes; eight Node tests and npm audit remain green.

## Phase 1 configurable print-layout designer

- Added report controls for A4/A3/A2/A1/A0, portrait/landscape, title, author/team,
  and warning/limitation visibility.
- Print preview and downloaded HTML now consume the selected report configuration.
- Verification: report-control/static checks passed; eight Node tests and npm audit remain green.

## Phase 1 server-backed export job

- Added `export_jobs` persistence and server-side HTML export generation.
- Added `POST /api/projects/:projectId/exports` and `GET /api/exports/:exportId/html`.
- UI Download HTML now persists the selected layout configuration before serving the artifact.
- Verified live: export creation 201/completed, HTML read-back 200, custom title/source/warning content preserved.

## Phase 1 geometry-backed server export

- Server export now queries stored PostGIS feature geometries and embeds an SVG map frame.
- Export verification: SVG present, Polygon geometry present, placeholder map removed.

## Phase 1 PDF renderer

- Added Playwright using the installed Chrome binary for server-side PDF generation.
- Added `GET /api/exports/:exportId/pdf`.
- PDF honours stored paper size and orientation and includes the geometry-backed report layout.
- Live verification: HTTP 200, `application/pdf`, valid `%PDF-` signature, 59,456-byte output.

## Phase 1 visible PDF export

- Added `Download PDF` to the Reports & exports interface.
- The button creates a persisted export configuration and opens the server PDF endpoint.
- The browser workflow now exposes print preview, HTML download, and PDF download separately.

## Phase 1 dynamic map composition

- Added visible north arrow and scale bar to the interactive map surface.
- Server-backed exports retain the geometry-backed map frame and report furniture.
- Verification: composition/static checks passed; eight Node tests and npm audit remain green.
- Public Community release: [v1.4.4](https://github.com/cartogenai-glitch/cartogen_ai_community/releases/tag/v1.4.4), commit `d2f1f64`, ZIP SHA-256 `5bd95da86fec598045c3336311699de50cf49df8ec0557b2f4df91795602100c`.
- Private commercial-plugin release: [commercial-plugin-v1.4.4](https://github.com/cartogenai-glitch/CARTOGEN-AI/releases/tag/commercial-plugin-v1.4.4), commit `720fb79`.
