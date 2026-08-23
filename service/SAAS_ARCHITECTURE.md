# Cartogen AI SaaS Architecture

This service is the private commercial backend for HTTP-Solution. It is designed for a VPS deployment with a managed client portal, CMS-backed authentication, subscription billing, and a self-hosted LLM gateway.

## Components

```text
Browser
  ├── Marketing site / client portal (Express static UI)
  ├── Directus authentication and CMS admin (port 8055 internally)
  └── Stripe Checkout / Customer Portal

Website API (port 3000)
  ├── Directus session bridge: register, login, logout, current user
  ├── Authenticated checkout creation
  ├── Stripe raw-body webhook verification
  ├── Subscription/key lifecycle orchestration
  └── Health endpoint

LiteLLM gateway (port 4000 internally)
  ├── Provider routing
  ├── Virtual keys, budgets, and rate limits
  └── PostgreSQL persistence

PostgreSQL
  ├── Directus CMS/auth database
  ├── LiteLLM key/budget database
  └── Cartogen website subscription database
```

## Authentication model

Directus is the CMS and identity authority. The website does not store passwords.

- Registration is handled by Directus's user-registration endpoint.
- Login is handled by Directus and the access token is stored in an HTTP-only session cookie.
- The website calls Directus `/users/me` to validate the session before portal or checkout actions.
- The browser never receives a Directus admin token or LiteLLM master key.
- The client portal is the place for account state, subscription actions, documentation links, and future usage summaries.

For production, configure Directus registration policy, email verification, password reset, SMTP, rate limits, and a non-admin registration role before opening registration publicly.

## Billing model

Stripe owns payment state. The website is an orchestration layer, not a billing ledger.

1. Authenticated user requests checkout.
2. Website creates a random single-use retrieval token and a pending database row.
3. Website creates a Stripe subscription checkout session with the Directus user ID in metadata.
4. Stripe calls the raw-body webhook.
5. The webhook verifies the signature, issues a LiteLLM virtual key, and records the subscription/user mapping.
6. The success page retrieves the virtual key once through the single-use token.
7. Subscription updates or cancellation block/unblock the LiteLLM key.

Before live launch, add Stripe Customer Portal configuration, idempotent webhook-event storage, retry/alert handling, plan-to-budget mapping, and an admin reconciliation command.

## VPS deployment shape

Use one VPS with Docker Compose initially:

- Caddy or Nginx at the edge for TLS and routing;
- website exposed publicly;
- Directus exposed only through an admin subdomain or VPN/allowlist;
- LiteLLM exposed only to the private Docker network;
- PostgreSQL exposed only to the private Docker network;
- named volumes for Postgres, Directus uploads, and Directus extensions;
- encrypted off-host database backups;
- Docker health checks and restart policies;
- logs shipped or rotated outside the container filesystem.

Recommended hostnames:

- `cartogen.ai` — marketing and portal;
- `admin.cartogen.ai` — Directus administration, restricted by identity/network policy;
- `api.cartogen.ai` — optional future public API endpoint; do not expose LiteLLM directly until its policy is complete.

Do not put secrets in the repository, Docker image, browser bundle, or release ZIP.

## Required production configuration

- `POSTGRES_PASSWORD`
- `DIRECTUS_KEY`
- `DIRECTUS_SECRET`
- `DIRECTUS_ADMIN_EMAIL`
- `DIRECTUS_ADMIN_PASSWORD`
- `LITELLM_MASTER_KEY`
- provider API keys used by the gateway
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_ID`
- `PUBLIC_BASE_URL`
- SMTP settings for Directus email verification and password reset

Generate random values; never reuse development values. Set `NODE_ENV=production`.

## Pre-VPS acceptance gates

- `docker compose config` succeeds with a real `.env`.
- Postgres health check passes.
- Directus admin login works and registration policy is deliberate.
- Website `/healthz` returns JSON health.
- Registration and login create/use an HTTP-only session.
- Unauthenticated checkout returns 401.
- Authenticated checkout reaches Stripe test mode.
- Stripe webhook rejects an invalid signature.
- Stripe test webhook activates exactly one subscription/key.
- Retrieval token succeeds once and fails on replay.
- Subscription cancellation blocks the LiteLLM key.
- Reactivation unblocks the same key.
- Gateway budget/rate-limit behavior is verified.
- Portal shows account/subscription state without exposing admin secrets.
- Backup and restore are tested before accepting customer data.

## Known current status

The local stack now has the Compose/CMS/auth/portal wiring foundation. Stripe test credentials,
Directus SMTP, production domain/TLS, provider keys, real VPS backups, live webhook delivery,
and a complete entitlement/admin reconciliation surface still require environment-specific
configuration and verification. They must not be represented as complete until exercised against
the real services.
