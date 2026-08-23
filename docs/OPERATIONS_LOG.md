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
- Public Community release: [v1.4.4](https://github.com/cartogenai-glitch/cartogen_ai_community/releases/tag/v1.4.4), commit `d2f1f64`, ZIP SHA-256 `5bd95da86fec598045c3336311699de50cf49df8ec0557b2f4df91795602100c`.
- Private commercial-plugin release: [commercial-plugin-v1.4.4](https://github.com/cartogenai-glitch/CARTOGEN-AI/releases/tag/commercial-plugin-v1.4.4), commit `720fb79`.
