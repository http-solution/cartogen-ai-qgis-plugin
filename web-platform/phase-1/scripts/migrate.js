#!/usr/bin/env node
// Applies db/migrations/*.sql in order, tracking what's been applied in a
// schema_migrations table. Idempotent: safe to run against a fresh database
// (docker-entrypoint-initdb.d's db/init.sql already marks every current
// migration as applied, so this becomes a no-op there) or an existing
// database that predates some migrations (the real use case this exists
// for -- see db/MIGRATIONS.md for the full upgrade/rollback procedure).
//
// Usage:
//   node scripts/migrate.js              apply every pending migration
//   node scripts/migrate.js --dry-run    list what would be applied, change nothing
//   node scripts/migrate.js --status     list applied vs. pending, change nothing

const fs = require('node:fs');
const path = require('node:path');
const { Pool } = require('pg');

const MIGRATIONS_DIR = path.join(__dirname, '..', 'db', 'migrations');
const MIGRATION_NAME_PATTERN = /^\d{4}_[a-z0-9_]+\.sql$/;

// Same discrete-PG*-vars-preferred-over-DATABASE_URL logic as server.js
// (kept as a small standalone copy here rather than importing server.js, so
// this script has no dependency on Express/Stripe/etc. and can run before
// or independently of the API process).
function buildPoolConfig(env = process.env) {
  const discreteKeys = ['PGHOST', 'PGPORT', 'PGUSER', 'PGPASSWORD', 'PGDATABASE'];
  if (discreteKeys.some(key => env[key])) {
    return {
      host: env.PGHOST || '127.0.0.1',
      port: Number(env.PGPORT || 5432),
      user: env.PGUSER || 'cartogen',
      password: env.PGPASSWORD || '',
      database: env.PGDATABASE || 'cartogen_phase1',
    };
  }
  return { connectionString: env.DATABASE_URL || 'postgresql://cartogen:phase1_local_only_change_me@127.0.0.1:55432/cartogen_phase1' };
}

function listMigrationFiles(dir = MIGRATIONS_DIR) {
  return fs.readdirSync(dir)
    .filter(name => MIGRATION_NAME_PATTERN.test(name))
    .sort();
}

// Pure function, no I/O -- the part of "what should run next" that's worth
// unit testing without a real database.
function computePending(files, appliedVersions) {
  const applied = new Set(appliedVersions);
  return files.filter(name => !applied.has(name));
}

// Static idempotency check for a migration file's SQL text. Catches the
// exact class of bug this migration system exists to prevent: a bare `ADD
// CONSTRAINT` or `CREATE TABLE`/`CREATE INDEX` without an existence guard,
// which fails outright if the migration (or the equivalent schema) has
// already been applied. Deliberately conservative -- it flags patterns, not
// a full SQL parse, so a false negative is possible on unusual formatting,
// but every migration in db/migrations/ passes this today (see
// test/validate-migrations.test.js).
function lintMigrationSql(sql) {
  const problems = [];
  const withoutComments = sql.replace(/--[^\n]*/g, '');

  for (const match of withoutComments.matchAll(/CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS)(\S+)/gi)) {
    problems.push(`CREATE TABLE ${match[1]} is missing IF NOT EXISTS`);
  }
  for (const match of withoutComments.matchAll(/CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!IF\s+NOT\s+EXISTS)(\S+)/gi)) {
    problems.push(`CREATE INDEX ${match[1]} is missing IF NOT EXISTS`);
  }
  for (const match of withoutComments.matchAll(/ALTER\s+TABLE\s+(\S+)\s+ADD\s+COLUMN\s+(?!IF\s+NOT\s+EXISTS)(\S+)/gi)) {
    problems.push(`ALTER TABLE ${match[1]} ADD COLUMN ${match[2]} is missing IF NOT EXISTS`);
  }
  // A bare ADD CONSTRAINT is only safe if the same file also DROPs that
  // exact constraint name first (the idempotent DROP-then-ADD pattern used
  // throughout db/migrations/). Flag any ADD CONSTRAINT whose name doesn't
  // also appear in a DROP CONSTRAINT IF EXISTS earlier in the same file.
  const droppedConstraints = new Set([...withoutComments.matchAll(/DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+(\S+)/gi)].map(match => match[1].replace(/;$/, '')));
  for (const match of withoutComments.matchAll(/ADD\s+CONSTRAINT\s+(\S+)/gi)) {
    const name = match[1];
    if (!droppedConstraints.has(name)) problems.push(`ADD CONSTRAINT ${name} has no matching DROP CONSTRAINT IF EXISTS earlier in the file`);
  }

  return problems;
}

async function ensureMigrationsTable(client) {
  await client.query(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version text PRIMARY KEY,
      applied_at timestamptz NOT NULL DEFAULT now()
    )
  `);
}

async function appliedVersions(client) {
  const result = await client.query('SELECT version FROM schema_migrations ORDER BY version');
  return result.rows.map(row => row.version);
}

// `pool` accepts an injected Pool-like object ({ connect(): Promise<client> })
// so tests can exercise the applied/pending/apply logic against a mocked
// client without a live database -- see test/validate-migrations.test.js.
// When omitted (the normal CLI path), a real pg.Pool is built from
// poolConfig and closed again before returning; an injected pool is left
// open for the caller to manage, since it's presumably shared/reused.
async function run({ dryRun = false, statusOnly = false, migrationsDir = MIGRATIONS_DIR, poolConfig = buildPoolConfig(), pool: injectedPool } = {}) {
  const pool = injectedPool || new Pool(poolConfig);
  const client = await pool.connect();
  try {
    await ensureMigrationsTable(client);
    const applied = await appliedVersions(client);
    const files = listMigrationFiles(migrationsDir);
    const pending = computePending(files, applied);

    if (statusOnly) {
      console.log(`Applied (${applied.length}): ${applied.join(', ') || '(none)'}`);
      console.log(`Pending (${pending.length}): ${pending.join(', ') || '(none)'}`);
      return { applied, pending };
    }

    if (!pending.length) {
      console.log('No pending migrations -- schema is up to date.');
      return { appliedNow: [] };
    }

    const appliedNow = [];
    for (const name of pending) {
      const sql = fs.readFileSync(path.join(migrationsDir, name), 'utf8');
      const lintProblems = lintMigrationSql(sql);
      if (lintProblems.length) {
        throw new Error(`Refusing to apply ${name}: not idempotent -- ${lintProblems.join('; ')}`);
      }
      if (dryRun) {
        console.log(`[dry run] would apply ${name}`);
        continue;
      }
      console.log(`Applying ${name}...`);
      await client.query('BEGIN');
      try {
        await client.query(sql);
        await client.query('INSERT INTO schema_migrations (version) VALUES ($1)', [name]);
        await client.query('COMMIT');
        appliedNow.push(name);
      } catch (error) {
        await client.query('ROLLBACK');
        throw new Error(`Migration ${name} failed: ${error.message}`);
      }
    }
    if (!dryRun) console.log(`Applied ${appliedNow.length} migration(s).`);
    return { appliedNow };
  } finally {
    client.release();
    if (!injectedPool) await pool.end();
  }
}

if (require.main === module) {
  const dryRun = process.argv.includes('--dry-run');
  const statusOnly = process.argv.includes('--status');
  run({ dryRun, statusOnly }).catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}

module.exports = { run, listMigrationFiles, computePending, lintMigrationSql, buildPoolConfig, MIGRATIONS_DIR, MIGRATION_NAME_PATTERN };
