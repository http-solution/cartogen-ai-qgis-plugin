# Cartogen AI Commercial Service — Local and VPS Runbook

Private operational runbook. Do not publish this file in the Community repository.

## 1. Local prerequisites

- Docker Desktop with Compose v2;
- Node.js 22+ for website development outside Docker;
- Git;
- a copy of this private repository;
- test-mode Stripe account for checkout testing;
- Directus CMS/auth configuration;
- provider credentials only when testing real LLM calls.

No production secrets belong in Git, `.env.example`, browser JavaScript, or Docker images.

## 2. Local configuration

From the commercial service directory:

```bash
cd C:/Cartogen-AI-Core/cartogen-ai/service
cp .env.example .env
```

Edit `.env` and replace every `CHANGE_ME_*` value. At minimum configure:

- `POSTGRES_PASSWORD`
- `DIRECTUS_KEY`
- `DIRECTUS_SECRET`
- `DIRECTUS_ADMIN_EMAIL`
- `DIRECTUS_ADMIN_PASSWORD`
- `LITELLM_MASTER_KEY`
- `STRIPE_SECRET_KEY` for checkout
- `STRIPE_WEBHOOK_SECRET` for signed webhook testing
- `STRIPE_PRICE_ID` for the subscription price

The checked-in `.env.example` uses alternate local host ports because this workstation
already has services on ports 3000 and 4000:

| Service | Local URL / mapping | Container port |
|---|---|---:|
| Website | http://localhost:3001 | 3000 |
| Directus CMS | http://localhost:8055 | 8055 |
| LiteLLM | http://localhost:4001 | 4000 |
| Postgres | Docker network only | 5432 |

On a clean machine, you may use 3000 and 4000 if they are free. The VPS reverse proxy
should expose the website and, where appropriate, the Directus admin hostname; Postgres
and LiteLLM should remain private network services.

## 3. Start the local stack

Validate Compose interpolation first:

```bash
docker compose --env-file .env.example config
```

Start the stack:

```bash
docker compose --env-file .env.example up -d
```

Check status:

```bash
docker compose --env-file .env.example ps
```

Follow service logs:

```bash
docker compose --env-file .env.example logs -f website directus litellm
```

Stop the stack without deleting volumes:

```bash
docker compose --env-file .env.example down
```

Do not use `down -v` unless you deliberately want to delete the local databases and
Directus uploads.

## 4. Local access links

### Website

- Marketing page: http://localhost:3001/
- Register: http://localhost:3001/register.html
- Sign in: http://localhost:3001/login.html
- Client portal: http://localhost:3001/portal.html
- Website health: http://localhost:3001/healthz

Expected health response:

```json
{"ok":true,"service":"cartogen-website"}
```

### Directus CMS and authentication

- Admin/CMS: http://localhost:8055/admin
- Directus health: http://localhost:8055/server/health
- Directus API: http://localhost:8055/

The initial administrator is created from:

- `DIRECTUS_ADMIN_EMAIL`
- `DIRECTUS_ADMIN_PASSWORD`

Use the values in the local `.env`, never values pasted into chat or committed to a file.

### LiteLLM

- Local host mapping: http://localhost:4001
- Docker-internal website/gateway URL: `http://litellm:4000`
- Do not expose the LiteLLM master-key API directly to the public internet.

### Postgres

Postgres is intentionally not published to the host by default. The databases are:

- `cartogen` — website subscription records;
- `directus` — CMS/auth data;
- `litellm` — virtual keys, budgets, and gateway state.

## 5. First-run Directus setup

1. Open http://localhost:8055/admin.
2. Sign in with the configured Directus admin credentials.
3. Confirm the admin account is protected by a strong local password.
4. Create a non-admin customer role.
5. Configure the public registration policy to permit only the fields required for registration:
   - email;
   - password;
   - first name;
   - last name.
6. Do not grant public access to billing records, provider keys, Directus settings, files,
   roles, permissions, or administrative collections.
7. Configure SMTP before enabling production email verification and password reset.
8. Put the customer-role UUID into `DIRECTUS_REGISTER_ROLE` in the deployment `.env`.

The local stack now has Directus registration enabled for the customer role and the website registration/session flow has been verified. The customer self-read policy for optional profile fields should still be reviewed in the Directus admin UI before production; the portal safely falls back to the user ID when those fields are not readable.

## 6. Website/auth smoke test

Run the repeatable local smoke test:

```bash
bash scripts/local_saas_smoke.sh
```

It exits non-zero when Stripe or the Pro-client entitlement gate is not configured.

Check the unauthenticated boundary:

```bash
curl -i -X POST http://localhost:3001/create-checkout-session
```

Expected: `401 authentication required`.

After the Directus customer registration permission is configured:

1. Register at http://localhost:3001/register.html.
2. Confirm the browser receives an HTTP-only session cookie.
3. Confirm http://localhost:3001/portal.html loads the current user.
4. Confirm `/api/me` returns the sanitized user record and never an admin token.
5. Sign out and confirm `/api/me` returns 401.
6. Configure Stripe test mode and `STRIPE_PRICE_ID`.
7. Start Stripe CLI webhook forwarding or configure a test webhook endpoint.
8. Start checkout from the portal.
9. Confirm the webhook creates one pending/active subscription row and one LiteLLM virtual key.
10. Confirm the retrieval token returns the key once only.
11. Confirm subscription cancellation blocks the key and reactivation unblocks it.

## 7. VPS deployment sequence

### Prepare the VPS

1. Provision a supported Linux VPS with Docker Engine and Compose v2.
2. Configure a non-root deployment user.
3. Configure a firewall allowing only SSH and HTTPS; keep Postgres, Directus internal,
   and LiteLLM internal unless a deliberate access policy says otherwise.
4. Clone the private repository using an authenticated deployment method.
5. Copy `service/.env.example` to `service/.env` and generate unique production values.
6. Configure DNS:
   - `cartogen.ai` → reverse proxy / website;
   - `admin.cartogen.ai` → Directus admin behind access controls;
   - optional `api.cartogen.ai` → only if a separately reviewed API surface is ready.
7. Put Caddy or Nginx in front for TLS and security headers.
8. Set `PUBLIC_BASE_URL` to the HTTPS website URL.
9. Set `DIRECTUS_PUBLIC_URL` to the HTTPS CMS URL.
10. Configure Directus SMTP and customer role/registration policy.
11. Configure Stripe live/test mode deliberately; never mix environments.
12. Configure provider keys in the VPS secret store or protected `.env`, never Git.
13. Run `docker compose config` and inspect the rendered configuration for accidental
    secrets, host exposure, or wrong URLs.
14. Start with `docker compose up -d`.
15. Check all health endpoints and logs.
16. Configure Stripe webhook signing and verify a test event.
17. Test registration, login, portal, checkout, webhook, key retrieval, cancellation,
    and reactivation.
18. Configure encrypted off-host Postgres backups and perform a restore test.
19. Configure log rotation, monitoring, alerting, and restart policies.

### VPS health checks

```bash
docker compose ps
curl -fsS https://cartogen.ai/healthz
curl -fsS https://admin.cartogen.ai/server/health
docker compose logs --tail=100 website directus litellm
```

## 8. Common local problems

### Port 4000 already allocated

An existing LiteLLM or other service owns the port. Keep the Docker-internal port at 4000
and change only `LITELLM_PORT`, for example:

```dotenv
LITELLM_PORT=4001
```

### Port 3000 already allocated

Change only the host mapping:

```dotenv
WEBSITE_PORT=3001
PUBLIC_BASE_URL=http://localhost:3001
```

### Directus health is temporarily empty

The first Directus start applies migrations and creates the admin role. Wait for:

```text
Server started at http://0.0.0.0:8055
```

Then retry `/server/health`.

### Website cannot reach Directus

Inside Compose, the website must use `DIRECTUS_URL=http://directus:8055`, not
`localhost:8055`. `localhost` inside the website container means the website container.

### Stripe checkout reports not configured

Set `STRIPE_SECRET_KEY` and `STRIPE_PRICE_ID` in `.env`, restart the website, and use
Stripe test mode until the complete flow has been verified.

## 9. Version and release record

The commercial service is versioned independently from the public QGIS plugin.

- `commercial-v0.2.0` — CMS/auth/portal/Compose foundation;
- `commercial-v0.2.1` — clean website container build and local port configuration.

Every meaningful service change must update `service/CHANGELOG.md`, pass the local checks,
and receive a private Git tag/release when the change is ready to hand off.
