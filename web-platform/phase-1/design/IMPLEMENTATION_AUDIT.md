# Cartogen AI Workspace — structure and implementation audit

**Scope:** `web-platform/phase-0` and `web-platform/phase-1` — architecture, `server.js` (1,443
lines, read in full), the database schema (`db/*.sql`), the test suite, the build/data
scripts, and the deployment story (`docker-compose.yml`, `package.json`).
**Verification:** `npm test` run live — 29/29 pass. Server boot, live HTTP checks, and
`docker compose up` were attempted but this session's connection to the local port kept
getting torn down by the remote shell bridge before curl could complete; findings below
that depend on runtime behavior are marked accordingly and are otherwise based on direct
reading of the code paths involved, which is unambiguous for the cases cited.
**Companion doc:** `UI_UX_AUDIT.md` covers the interface; this one covers what is under it.

---

## 1. The headline: the backend is better than the frontend

The earlier interface review found `index.html` implementing roughly half of what the
README claims. `server.js` is a different story — the route handlers, SQL, and validation
are careful, consistent, and mostly correct: parameterized queries everywhere, geometry
validated (allowlisted types, coordinate range checks) before it ever reaches
`ST_GeomFromGeoJSON`, SSRF protections on the HDX import path (host allowlist re-checked on
every redirect hop, byte ceiling enforced while streaming, request timeout via
`AbortController`), a hand-rolled ZIP reader that never trusts a claimed size without
checking it against the actual buffer, and a feature-edit flow with SHA-256 state hashing,
an HMAC-signed preview token, `timingSafeEqual` comparison, and `SELECT ... FOR UPDATE` row
locking for the approve path. This is not vibe-coded — someone was thinking about tenant
isolation and injection at every call site.

That makes the three defects below more worth fixing, not less: they sit in otherwise
solid code, they are each one line or one missing script away from correct, and they are
the difference between "vertical slice" and "would survive being shown to a design
partner's IT team."

---

## 2. Critical

**A. The API serves its own source code, schema, and default database password to anyone
who asks.**

```js
app.use(express.static(__dirname));
```

This is mounted before every route, with no path restriction. `express.static` will serve
any non-dotfile under `phase-1/` that a client requests by name. Concretely, with the
server reachable at all:

- `GET /server.js` → the entire API implementation
- `GET /docker-compose.yml` → the Postgres superuser password
  (`phase1_local_only_change_me`, sitting in plaintext)
- `GET /db/init.sql` → the full schema, including the seeded organization id
- `GET /package.json`, `GET /test/*.js`, `GET /scripts/*.py` → everything else in the tree

`.env` itself would be excluded (Express's static middleware ignores dotfiles by default),
but nothing else is. On `127.0.0.1` this is invisible. The moment this API is reachable
from anywhere else — a shared dev box, a design-partner demo on a VPN, a cloud deployment —
it hands over the codebase and the DB credential to any visitor. Fix: `express.static` with
an explicit allowlist (`index.html` and a real `public/` or `dist/` directory only), never
the project root.

**B. PDF export is hardcoded to one developer's Windows machine and will not work anywhere
else by default.**

```js
const browser = await playwright.chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
```

`playwright` is a declared dependency specifically so it can manage its own bundled
Chromium — that's the entire point of depending on it instead of shelling out to a system
browser. This line ignores that and points at a literal desktop install path instead. On
Linux, in Docker, in CI, or on any machine where Chrome isn't installed at that exact path
and `CHROME_PATH` isn't set, every PDF export throws and the route returns
`503 PDF renderer unavailable`. This is consistent with the README's own honesty here —
"Real PDF/print export engine" is listed as unchecked — but the fix is small: call
`playwright.chromium.launch({ headless: true })` with no `executablePath` override (or fall
back to it only if `CHROME_PATH` is explicitly set), and the bundled browser Playwright
already downloads will just work.

**C. There is no pipeline that puts the Pakistan data into PostGIS. `demo-data.json` is
dead code.**

`db/init.sql` seeds exactly one row — the `pakistan-humanitarian-screening` project itself.
No layer, no feature. Searching the whole `web-platform` tree, the only code that ever
inserts into `project_layer_features` is `server.js`, and only from two request-triggered
paths: the HDX import endpoint and the generic layer-upload endpoint. Neither runs
automatically. `scripts/build_demo_data.py` reads the ~34 MB Pakistan bundle in
`phase-0/data/` and writes `phase-1/demo-data.json` — a 15 KB summary with 714 3W records,
4,849 facility counts, sector breakdowns — and nothing in `server.js` or `index.html` ever
reads that file back. It's generated, checked in, and orphaned.

Net effect: `docker compose up -d postgis && npm install && npm start` on a clean checkout
gives an empty map. Every count in the README ("714 Pakistan 3W presence records," "4,849
health facilities") is only true after someone manually drives the HDX-import UI flow for
each dataset by hand — a flow that itself doesn't exist yet in `index.html` per the
companion audit. There is no `scripts/seed_postgis.py` or equivalent that takes the bundle
already sitting in the repo and loads it. That script is the highest-leverage piece of
missing plumbing in the whole project: without it, "data-backed vertical slice" is
aspirational on a fresh environment.

---

## 3. High

**D. Zero integration tests. All 29 passing tests are unit tests on exported pure
functions.**

`node --test test/*.test.js` passes cleanly, and that's worth taking at face value — the
validators, normalizers, hashing, and token functions it covers (`normalizeFeatureCollection`,
`normalizeHdxImportRequest`, `createEditPreviewToken`/`verifyEditPreviewToken`,
`normalizeWorkflowScheduleRequest`, etc.) are well chosen and the edge cases are sensible.
But nothing in the suite makes an HTTP request, touches `pool`, or calls `app.listen`. Not
one of the ~30 route handlers is exercised end to end. In particular, the tenant-scoping
pattern used in almost every query —

```sql
WHERE id = $1 AND organization_id = $2
```

— is never tested for the failure mode that matters: does requesting another
organization's project, layer, job, or export actually 404 instead of leaking a row? That's
the single most security-relevant behavior in the app and it has no test coverage at all.
Given `pg`'s test-container ecosystem is mature, a `node:test` + `supertest`-style suite
against a throwaway Postgres/PostGIS instance (even via the existing `docker-compose.yml`)
would close this cheaply.

**E. No migration framework — six hand-written "apply once" patch files with no version
tracking.**

`db/init.sql` is complete and internally consistent for a fresh database. Alongside it sit
`agent_runs.sql`, `ai_run_approval.sql`, `ai_tasks.sql`, `documents.sql`, `exports.sql`,
`feature_edits.sql`, and `workflow_schedules.sql` — each headed with a comment like "Apply
once to an existing Phase 1 database; init.sql includes the same schema for fresh
databases." There's no `schema_migrations` table, no ordering, no way for an operator who
set up their database before a given feature shipped to know which of the six files they're
missing versus which they've already run. `CREATE TABLE IF NOT EXISTS` makes re-running
safe, but an `ALTER TABLE ... ADD CONSTRAINT` (see `ai_run_approval.sql`) is not idempotent
against a database that already has a different version of that constraint. This works
today because the project has one operator who remembers the order changes shipped in; it
will not survive a second contributor or a hosted deployment.

**F. Nothing supervises the app or the worker.** `docker-compose.yml` defines exactly one
service: `postgis`. `server.js` and `scripts/analysis_worker.js` are both meant to be run by
hand (`npm start`, `npm run worker`), with no container, no restart policy, no process
manager. If the worker isn't running — or dies, since `analysis_worker.js`'s `tick()`
catches per-job errors but has no wrapper around the poll loop itself — every `buffer_layer`
and `intersect_layers` job queued through `/api/projects/:id/analysis-jobs` sits in
`queued` forever with nothing to surface that. This is the server-side cause of the "Jobs
never refresh" symptom the interface audit flagged from the browser side.

---

## 4. Medium

**G. Identity is a single client-supplied header, and that's the default mode, not an
opt-in one.** `PHASE1_IDENTITY_MODE` defaults to `'demo'`. In that mode,
`resolveIdentity` trusts `req.header('x-demo-organization')` outright — any caller who sets
that header becomes that organization, no credential involved. This is explicitly called
out as unfinished in the README ("Real authentication and organization permissions" is
unchecked) so it isn't a surprise, but it's worth being precise about how thin it is: it's
not a weak auth scheme, it's the complete absence of one, active by default. Combined with
finding A, anyone who can reach the API can read the source, read the DB password from
`docker-compose.yml`, and then assert any `organization_id` they like against the live
database with the credentials they just downloaded. None of this matters on `localhost`;
all of it matters the moment a design partner is given a URL.

**H. No security middleware beyond disabling `x-powered-by`.** No `helmet` (no CSP, no
`X-Frame-Options`, no HSTS), no rate limiting on any endpoint — including
`/api/datasets/search` and `/api/datasets/import`, which both make outbound requests on the
server's behalf and are exactly the kind of endpoint abused for request amplification. No
CORS policy is declared; harmless today because the SPA and API share an origin, but
undocumented, so the first person who splits the frontend into its own deployment will
discover the gap by trial and error.

**I. Bulk operations insert one row at a time inside a single transaction.** HDX import and
the generic layer-upload endpoint both loop `for (const feature of features) { INSERT... }`
— up to 1,000 round-trips per request, bounded by `HDX_IMPORT_MAX_FEATURES` so not
dangerous, but a multi-row `INSERT ... VALUES` batch or `pg-copy-streams` would turn a
thousand round-trips into one and matters as soon as a real pilot dataset (not the 1,000-cap
demo limit) is in scope.

**J. No CI, no lint/format config, no `.env.example`, no `engines` field.** Nothing in the
repository enforces a Node version, a code style, or runs the test suite automatically on a
change. `.gitignore` excludes `.env` correctly, but there's no template showing what belongs
in it, so a new contributor has to reverse-engineer the required environment variables from
reading `server.js` end to end — which is what this audit had to do.

---

## 5. What's actually solid — don't rebuild these

- **Input validation.** Every `normalize*` function in `server.js` rejects malformed input
  with a specific message before it touches the database — coordinate bounds, geometry
  type allowlists, byte and feature-count ceilings, ISO date parsing, CSV column detection.
  This is the right shape for the job and it's applied consistently.
- **The feature-edit workflow.** Preview → HMAC token → explicit `approved: true` → hash
  comparison against the current stored state → `FOR UPDATE` lock → lineage event write, all
  in one transaction with rollback on any mismatch. This is a genuinely careful design for
  "never silently overwrite a stale edit," and it's implemented correctly.
- **HDX import safety.** Host allowlist checked on the *original* URL and *again* on every
  redirect hop (not just once), streamed byte-limit enforcement rather than trusting
  `Content-Length`, and a hand-rolled ZIP central-directory walk that checks uncompressed
  size against the import ceiling before ever inflating — this defends against exactly the
  zip-bomb and SSRF-via-redirect classes of bug that are easy to miss.
- **Tenant scoping pattern.** Every query, without exception across ~30 handlers, filters on
  `organization_id`. The pattern is right even though it's untested (finding D) — this is a
  "write the test," not a "fix the query," problem.
- **`normalizeFeatureCollection`'s recursive coordinate validator** correctly walks nested
  Multi* geometries instead of assuming a fixed depth — an easy thing to get subtly wrong
  and it isn't wrong here.

---

## 6. Suggested order of work

**Before this is shown to anyone outside localhost**

1. Restrict `express.static` to a real public directory — stop serving the source tree (A)
2. Fix the PDF renderer's `executablePath` to use Playwright's bundled Chromium (B)
3. Write `scripts/seed_postgis.py` (or a `.sql` COPY-based loader) that takes the bundle
   already in `phase-0/data/` and actually populates `project_layers` /
   `project_layer_features` on a fresh database (C)

**Before a second contributor or a hosted environment**

4. Add a real migration tool (even `node-pg-migrate` or numbered `.sql` files run in order
   by a tracked table) and retire the "apply once" convention (E)
5. Add `server` and `worker` as services in `docker-compose.yml` with restart policies (F)
6. Add an HTTP-level test suite against a throwaway Postgres, with explicit
   cross-tenant-isolation tests as the first cases written (D)

**Before scale or a wider audience**

7. Real authentication (already tracked in the README — just noting the current default is
   more permissive than "not done yet" suggests) (G)
8. `helmet`, rate limiting on outbound-fetch endpoints, an explicit CORS policy (H)
9. Batch inserts for bulk ingestion paths (I)
10. CI running `npm test` on push, a lint config, `.env.example`, an `engines` field (J)
