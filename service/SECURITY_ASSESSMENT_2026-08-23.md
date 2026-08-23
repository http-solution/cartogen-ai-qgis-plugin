# Commercial Service Security Assessment — 2026-08-23

## Scope

Assessed the private commercial service under `service/`, including the Express website,
Directus/CMS integration, Stripe webhook boundary, LiteLLM gateway orchestration, Docker
Compose exposure, dependency state, and local configuration handling.

## Findings and remediation

### SEC-001 — host service ports bound to all interfaces

**Risk:** Directus and LiteLLM admin/API ports could be exposed directly on a VPS if the
reverse proxy/firewall were misconfigured.

**Remediation:** Compose now binds website, Directus, and LiteLLM mappings to `127.0.0.1`
by default. The VPS runbook requires the reverse proxy to be the public edge and Postgres/
LiteLLM to remain private network services.

**Evidence:** `docker compose ps` shows `127.0.0.1:8055`, `127.0.0.1:4001`, and
`127.0.0.1:3001` locally.

### SEC-002 — Directus registration enabled by default

**Risk:** A fresh deployment could accidentally expose account registration before the
customer role, SMTP, email verification, and abuse controls were configured.

**Remediation:** Compose and `.env.example` default `DIRECTUS_USER_REGISTRATION=false`.
Registration is an explicit deployment decision documented in `LOCAL_VPS_RUNBOOK.md`.
The local smoke environment enabled it only after a customer role and minimal permission
were configured.

### SEC-003 — floating container image tags

**Risk:** A future image pull could silently change the runtime supply chain.

**Remediation:** The verified local Postgres, Directus, and LiteLLM images are pinned by
content digest in Compose and `.env.example`. Image digests must be deliberately updated
and reviewed.

### SEC-004 — missing website security headers and request throttling

**Risk:** The website lacked standard browser security headers and unauthenticated auth/
checkout endpoints had no application-level rate limit.

**Remediation:** Added Helmet security headers, disabled the Express powered-by disclosure,
and added rate limits to `/auth/*` and `/create-checkout-session`.

**Evidence:** HTTP response contains `Strict-Transport-Security`, `X-Content-Type-Options`,
`X-Frame-Options`, and `Referrer-Policy`.

### SEC-005 — malformed development webhook could terminate Node

**Risk:** The development webhook bypass intentionally accepts unsigned JSON, but malformed
JSON previously escaped `JSON.parse()` and crashed the website process.

**Remediation:** Malformed development webhook bodies now return `400 Invalid JSON webhook body`
and the process remains healthy.

### SEC-006 — website/LiteLLM master-key configuration drift

**Risk:** The website and gateway could receive different master keys because the website
loaded `.env` through `env_file` while LiteLLM used Compose interpolation. Billing activation
then failed with a misleading invalid-proxy-token error.

**Remediation:** Compose explicitly injects the interpolated `LITELLM_MASTER_KEY` into the
website container. The local smoke test now verifies the key lifecycle and LiteLLM `/v1/models`
authorization.

### SEC-007 — dependency audit coverage

**Evidence:** `npm audit --omit=dev` reports 0 vulnerabilities for the website dependency set.
A static scan found no private-key, AWS-key, Stripe-key, GitHub-token, or `sk-...` secret-pattern
files in the repositories. `pip-audit` is not installed in this environment, so the Python/
LiteLLM dependency audit remains an explicit VPS/CI gate.

## Local verification

- Website Node syntax: passed.
- Auth module syntax: passed.
- Docker Compose config: passed.
- Website image build: passed.
- Directus health: HTTP 200.
- Website health: HTTP 200.
- Malformed webhook: HTTP 400; process remained healthy.
- Registration/session smoke test: registration 201, `/api/me` 200, logout 200.
- Simulated billing webhook: passed.
- Single-use key retrieval and replay rejection: passed.
- Subscription activation/linkage: passed.
- LiteLLM virtual-key authorization at `/v1/models`: passed.
- Stripe checkout with real credentials: not configured locally.
- Pro-client entitlement/download: not implemented yet.

## Residual production risks

- Configure Stripe signatures and idempotent webhook-event storage before live billing.
- Configure Directus SMTP, password reset, email verification, customer self-read policy,
  and registration abuse controls.
- Add off-host encrypted backups and restore testing.
- Add centralized logs, alerting, and uptime monitoring.
- Run `pip-audit` against the gateway requirements in CI/VPS preparation.
- Pin and review all future image digest updates.
- Put Caddy/Nginx in front with TLS, admin access policy, and a strict firewall.
- Complete and test the Pro-client artifact/entitlement/download flow before offering it.
