# Cartogen AI Commercial Service Changelog

## 0.2.8 — Community sustainability and funding plan

- Added private-only `docs/COMMUNITY_SUSTAINABILITY_AND_FUNDING_PLAN.md`.
- Defined sustainable Community monetization through sponsorship, grants, training,
  implementation, support, research partnerships, managed service conversion, and emergency
  mapping retainers.
- Added funding funnel, revenue experiments, impact evidence, guardrails, and 30-day actions.
- Explicitly preserved GPL rights and the usefulness of the free Community edition.

## 0.2.7 — enterprise commercial growth plan

- Added `docs/ENTERPRISE_GROWTH_PLAN.md` with the commercial business-gap assessment,
  revised packaging model, enterprise task backlog, sector sequence, 90-day plan, and
  enterprise-readiness definition.
- Humanitarian aid mapping is the recommended commercial beachhead, followed by engineering,
  urban planning, and logistics.
- Added explicit workstreams for product, design partners, pricing, billing, identity,
  security, reliability, customer success, sales, and measurement.

## 0.2.6 — security assessment and hardening

- Bound Docker host ports to loopback by default.
- Made Directus public registration opt-in rather than enabled by default.
- Pinned verified Postgres, Directus, and LiteLLM image digests.
- Added Helmet security headers and auth/checkout rate limiting.
- Made malformed development webhooks return HTTP 400 without terminating Node.
- Added `SECURITY_ASSESSMENT_2026-08-23.md` with findings, evidence, remediation, and residual production gates.
- `npm audit --omit=dev`: 0 vulnerabilities; secret-pattern scan: 0 files.
- Python dependency audit remains a VPS/CI gate because `pip-audit` is not installed locally.

## 0.2.5 — billing activation test and configuration consistency

- Added `scripts/local_saas_smoke.sh` covering registration, session, simulated webhook,
  LiteLLM key retrieval/replay protection, subscription activation, API authorization, and
  Pro-client entitlement checks.
- Fixed Compose configuration drift by explicitly passing the interpolated LiteLLM master
  key into the website container.
- Directus registration/session and LiteLLM virtual-key activation now pass locally.
- Stripe checkout remains a configuration gate when Stripe credentials are absent.
- Pro-client download/entitlement remains a deliberately visible missing gate until the
  commercial client artifact and route are built.

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
