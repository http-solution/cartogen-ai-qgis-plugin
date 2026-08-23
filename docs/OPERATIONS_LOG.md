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
