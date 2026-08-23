# Cartogen AI — commercial service (local dev)

This is the **separate** backend that lets you sell managed API access to Cartogen AI
users who don't want to bring their own LLM key. It is not part of the GPLv2-licensed
QGIS plugin and should stay in its own directory / eventually its own deploy target.

Three pieces:

- `gateway/` — [LiteLLM Proxy](https://github.com/BerriAI/litellm) (MIT licensed). Sits in
  front of your real provider keys (OpenAI/Anthropic/Gemini/OpenRouter) and issues a
  **virtual API key per client**, each with its own budget and rate limit. This is what
  the QGIS plugin will eventually point at instead of (or in addition to) "bring your own key."
- `website/` — a small Express app: a pricing page, Stripe Checkout, a webhook that turns
  a completed payment into a LiteLLM virtual key, and a page that hands the key to the client.
- `data/` — local JSON file standing in for a database during dev (customer → virtual key
  mapping). Replace with a real DB before going live.

## Why these choices for v1

- **Stripe directly**, not a self-hosted billing engine (Lago etc.) — fewer moving parts,
  hosted customer portal for free, nothing to run ourselves. Revisit only if fees or
  pricing-logic limits become a real constraint.
- **LiteLLM**, MIT licensed — self-hosted, no licensing conditions on how you use it
  commercially.

## Prerequisites

- Docker (recommended — see below), or Python 3.10+/`pip` if running the gateway bare-metal
- Node.js 18+
- A Stripe account in **test mode** (free) — get your test secret key and set up a
  webhook signing secret. Not required to get the gateway itself running.

## Run it — Docker path (recommended)

LiteLLM's virtual-key store needs Postgres, and its official Docker image ships with
the Prisma client already generated, which sidesteps a handful of local dependency
issues (see "Bare-metal path" below if you hit them). This is the easiest way to run
it on a normal dev machine with Docker installed:

```bash
cp .env.example .env   # fill in LITELLM_MASTER_KEY, provider keys, Stripe keys

docker run -d --name cartogen-litellm-db \
  -e POSTGRES_DB=litellm -e POSTGRES_USER=litellm -e POSTGRES_PASSWORD=litellm \
  -p 5432:5432 postgres:16

docker run -d --name cartogen-litellm-gateway -p 4000:4000 \
  -e LITELLM_MASTER_KEY=sk-local-dev-master-key-change-me \
  -e DATABASE_URL=postgresql://litellm:litellm@host.docker.internal:5432/litellm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -v "$(pwd)/gateway/litellm_config.yaml:/app/config.yaml" \
  ghcr.io/berriai/litellm:main-latest --config /app/config.yaml

cd website
npm install
npm start   # listens on :3000
```

Visit `http://localhost:3000` for the pricing page. On Linux, `host.docker.internal`
may need `--add-host=host.docker.internal:host-gateway` on the `docker run` for the
gateway container.

## Run it — bare-metal path (no Docker)

Works, but expect to hit a few dependency snags that the Docker image avoids. These
are the fixes, discovered while getting this running here:

```bash
# 1. Postgres — any local Postgres 14+ works. Example with apt:
sudo apt-get install -y postgresql
sudo -u postgres psql -c "CREATE DATABASE litellm; CREATE USER litellm WITH PASSWORD 'litellm'; GRANT ALL PRIVILEGES ON DATABASE litellm TO litellm;"

# 2. Gateway deps
cd gateway
pip install -r requirements.txt

# LiteLLM's proxy extra pulls in a fastapi version that breaks its own imports
# (ImportError: get_flat_dependant). Pin a known-good version:
pip install "fastapi==0.136.3"

# If your machine routes traffic through a SOCKS proxy, LiteLLM's license-check
# HTTP client will fail on boot unless this is installed:
pip install "httpx[socks]"

# The virtual-key store talks to Postgres through Prisma's Python client, which
# needs its CLI + generated client (the Docker image has this pre-built; bare
# metal does not):
pip install prisma
DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm \
  prisma generate --schema "$(python3 -c 'import litellm, os; print(os.path.join(os.path.dirname(litellm.__file__), "proxy", "schema.prisma"))')"

# 3. Run it
export LITELLM_MASTER_KEY=sk-local-dev-master-key-change-me
export DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm
export ANTHROPIC_API_KEY=...   # your real key
litellm --config litellm_config.yaml --port 4000

# 4. website (separate terminal)
cd ../website
npm install
npm start   # listens on :3000
```

## Testing the flow without real Stripe keys yet

`website/server.js` skips webhook signature verification when `STRIPE_WEBHOOK_SECRET`
is unset **and** `NODE_ENV=development`, so you can POST a fake `checkout.session.completed`
event straight to `/webhook` to exercise the whole "payment → virtual key" path before
you've wired up a real Stripe account. See the `curl` example at the bottom of `server.js`.

## SaaS architecture and VPS preparation

The local stack now includes Directus CMS/authentication, a client portal foundation, Docker Compose orchestration, and a Postgres-backed billing/key lifecycle. See [`SAAS_ARCHITECTURE.md`](SAAS_ARCHITECTURE.md), [`LOCAL_VPS_RUNBOOK.md`](LOCAL_VPS_RUNBOOK.md), [`SECURITY_ASSESSMENT_2026-08-23.md`](SECURITY_ASSESSMENT_2026-08-23.md), [`CHANGELOG.md`](CHANGELOG.md), and `.env.example`.

The service is versioned independently from the public QGIS plugin. The current commercial service foundation is **0.2.6** and is not production-ready until the documented VPS acceptance gates pass against real configured services.

- Emailing the API key instead of showing it on a success page
- Mapping Stripe price IDs to specific LiteLLM budgets/rate limits (currently one flat plan)
- An actual deployment: a domain, a reachable gateway, real Stripe live-mode keys, and
  `NODE_ENV=production` with a real `STRIPE_WEBHOOK_SECRET` set

**Done, 2026-08-22** (see `db.js`/`server.js` — verified against a live Postgres and a live
HTTP server, not just written):
- Customer↔key mapping now lives in Postgres (`cartogen_subscriptions` table, `db.js`),
  reusing the same `DATABASE_URL` LiteLLM's own virtual-key store already requires — no more
  `data/subscriptions.json`.
- `customer.subscription.updated`/`.deleted` are handled: a cancelled or unpaid subscription
  gets its LiteLLM key blocked (`POST /key/block`); a reactivated one gets unblocked
  (`POST /key/unblock`) rather than needing a whole new key.
- `/key-for-session` no longer trusts the raw Stripe session id. `/create-checkout-session`
  now mints a random single-use `retrieval_token`, embedded in the Stripe session's
  `metadata` and in `success_url` — the browser never sees the Stripe session id at all.
  The token is consumed atomically on first successful read (`token_used_at IS NULL` in the
  `UPDATE ... WHERE` clause, not a separate read-then-write), so a leaked/logged/replayed
  URL returns nothing on a second request — confirmed under 10 concurrent requests for the
  same token, exactly one wins.
- Pointing the actual QGIS plugin at this gateway as a provider option — done on the plugin
  side (`CartogenClient` registered, selectable in Settings, not yet default); still needs a
  real deployed gateway to actually talk to.
- **Bug fix:** `website/server.js` was silently never loading `service/.env` — `dotenv`'s
  default `config()` only looks in `process.cwd()`, which is `website/` once you `cd website
  && npm start` per this doc's own setup steps above, not `service/` where `.env` actually
  gets created. Confirmed empirically (a probe var in a parent-directory `.env` came back
  `undefined`). Fixed with an explicit `__dirname`-relative path, verified against a live
  Postgres by running the exact documented setup sequence end to end.

All of the above verified live: a throwaway Postgres container, `npm start` run exactly per
this doc's documented sequence, real HTTP requests through `/key-for-session` and the webhook
route, including a 10-concurrent-request race against the same retrieval token (exactly one
request won).
