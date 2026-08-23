# Cartogen AI Commercial Service Changelog

## 0.2.4 — portal/session polish

- Portal greeting now falls back safely to the authenticated user ID when optional profile fields are not readable.
- Verified local Directus registration returns 201, session `/api/me` returns 200, and logout returns 200.


## 0.2.3 — release metadata synchronization

- Synchronized the commercial service package version and changelog after the protected 0.2.2 tag.

## 0.2.2 — local/VPS runbook and deployment polish

- Added the complete `LOCAL_VPS_RUNBOOK.md` with local access links, startup/shutdown commands,
  health checks, Directus setup, Stripe/LiteLLM flow checks, VPS DNS/TLS/backup steps, and
  production acceptance gates.
- Documented the local workstation port mappings: website 3001, Directus 8055, LiteLLM 4001.
- Added Docker build-context exclusions and synchronized the website package version.

## 0.2.1 — container build patch

- Cleaned the website container build with an explicit Node build argument and Docker build context exclusions.

## 0.2.0 — local SaaS foundation

- Added Docker Compose orchestration for Postgres, Directus CMS/auth, LiteLLM, and the website.
- Added Directus-backed account registration, login, logout, HTTP-only sessions, and `/api/me`.
- Added authenticated client portal with account and checkout entry points.
- Added authenticated Stripe checkout metadata linking a Directus user to a subscription.
- Added `directus_user_id` persistence to the subscription table with a safe additive schema update.
- Added website `/healthz` endpoint.
- Added VPS-oriented `.env.example`, Dockerfile, Postgres database initialization, and SaaS architecture documentation.
- Kept Stripe raw-body signature verification and single-use retrieval-token behavior.
- Verified Node syntax, `npm ci` with zero reported vulnerabilities, and Docker Compose configuration parsing.

### Not yet represented as production-ready

- Stripe live credentials, webhook delivery, customer portal configuration, and plan IDs.
- Directus SMTP, email verification, password reset, production registration policy, and admin hardening.
- VPS domain/TLS, backups, monitoring, alerting, provider spend limits, and disaster recovery.
- Live end-to-end checkout/webhook/key lifecycle against real VPS services.
