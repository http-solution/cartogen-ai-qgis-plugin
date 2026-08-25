# Schema migrations

This directory (`db/migrations/`) holds every schema change as a numbered,
idempotent SQL file, applied and tracked by `scripts/migrate.js`. There are
two ways the schema ever gets onto a database, and they're kept
consistent with each other:

- **Fresh install**: `db/init.sql` runs once, automatically, via Postgres's
  `docker-entrypoint-initdb.d` mechanism when the `postgres` container's data
  volume is first created. It builds the full current schema directly (not
  by running the migration files) and then inserts all ten migration
  filenames into `schema_migrations` itself, so the ledger is accurate from
  the start and `scripts/migrate.js` sees nothing pending on a brand-new
  database.
- **Existing database / upgrade**: `docker-entrypoint-initdb.d` only ever
  runs against an empty data volume, so any database that already existed
  before a given migration was added won't pick it up automatically. Run
  `scripts/migrate.js` (or `npm run migrate`) against it instead.

Both paths converge on the same `schema_migrations` table (`version text
PRIMARY KEY`, one row per applied migration filename), so at any point you
can tell exactly what state a database is in.

## Applying pending migrations

Against a running `phase1-api` container (recommended — it already has the
right network access and `PG*`/`DATABASE_URL` env vars configured; see
`docker-compose.yml`):

```
docker compose exec phase1-api npm run migrate
```

Or from a checkout with local network access to the database, using the
same `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`/`PGDATABASE` (preferred) or
`DATABASE_URL` env vars `server.js` itself uses:

```
node scripts/migrate.js
```

Useful flags:

```
node scripts/migrate.js --status     # list applied vs. pending, change nothing
node scripts/migrate.js --dry-run    # list what WOULD be applied, change nothing
```

`schema_migrations` is created automatically (`CREATE TABLE IF NOT EXISTS`)
if it doesn't exist yet, so this is also safe to run against a database that
predates the migrations system entirely — every migration will show as
pending and get applied in order.

## Safety properties

- **Idempotent by construction.** Every migration uses `CREATE TABLE IF NOT
  EXISTS`, `CREATE INDEX IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, and a
  `DROP CONSTRAINT IF EXISTS` immediately before any `ADD CONSTRAINT`. Before
  applying a migration, the runner statically lints its SQL
  (`lintMigrationSql` in `scripts/migrate.js`) and refuses to run anything
  that doesn't follow this pattern — see `test/validate-migrations.test.js`,
  which runs the linter against every real file in this directory.
- **Transactional per-file.** Each migration runs inside its own `BEGIN` /
  `COMMIT`, with `ROLLBACK` on any failure, and its filename is only
  inserted into `schema_migrations` after that file's statements succeed.
  A failure partway through file N leaves migrations before N applied and
  recorded, N itself un-recorded (safe to fix and re-run), and everything
  after N untouched.
- **Ordered, not parallel.** Files apply strictly in filename order
  (`0001_...`, `0002_...`, ...), one at a time.

## Adding a new migration

1. Create `db/migrations/00NN_short_description.sql` with the next number.
2. Write it so it's safe to run twice: `IF NOT EXISTS` on every `CREATE
   TABLE`/`CREATE INDEX`/`ADD COLUMN`, and `DROP CONSTRAINT IF EXISTS
   <name>;` immediately before any `ADD CONSTRAINT <name>`.
3. Add the same change to `db/init.sql` (so fresh installs still get it
   without needing to run the migration afterward), and add the new
   filename to the `INSERT INTO schema_migrations (version) VALUES (...)`
   block near the end of `db/init.sql` so fresh installs and upgraded
   databases agree on what's "applied".
4. Add the new filename to the expected-files list in
   `test/validate-migrations.test.js`.
5. Run `npm test` — the idempotency lint runs automatically against every
   file in `db/migrations/`, including the new one.

## Rollback

There is no automated down-migration / rollback tooling. This is a
deliberate scope decision, not an oversight: hand-written down-migrations
for schema changes involving `DROP COLUMN`/`DROP TABLE` are themselves a
common source of data loss, and this project doesn't yet have the
production traffic where automated rollback pays for the risk it adds.
Recovery from a bad migration is one of:

- **Restore from backup** taken before the migration ran (see the backups
  section of the deployment docs) — the safest option when the migration
  changed or removed data, not just structure.
- **Write a new forward migration** (`00NN+1_...`) that reverses the
  change — e.g. an `ALTER TABLE ... DROP COLUMN IF EXISTS ...` migration to
  undo a bad `ADD COLUMN`. This keeps `schema_migrations` monotonic and
  avoids ever un-applying a recorded migration.

Because every migration is transactional, the most common failure mode — a
migration that fails partway through — never leaves the schema in a broken
half-applied state for that one file; there's nothing to roll back in that
case beyond fixing the SQL and re-running `scripts/migrate.js`.
