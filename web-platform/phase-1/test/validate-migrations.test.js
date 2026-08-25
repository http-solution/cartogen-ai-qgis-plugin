const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {
  run,
  listMigrationFiles,
  computePending,
  lintMigrationSql,
  buildPoolConfig,
  MIGRATIONS_DIR,
  MIGRATION_NAME_PATTERN,
} = require('../scripts/migrate');

// --- listMigrationFiles: real I/O against the actual db/migrations/ dir ---
// This is the concrete, Docker-free proof that the migration set is
// complete and correctly named/ordered -- no live database required.

test('listMigrationFiles finds all 10 real migrations, correctly named and ordered', () => {
  const files = listMigrationFiles();
  const expected = [
    '0001_core_schema.sql',
    '0002_ai_tasks.sql',
    '0003_exports.sql',
    '0004_documents.sql',
    '0005_feature_lineage.sql',
    '0006_agent_runs.sql',
    '0007_ai_run_approval.sql',
    '0008_workflow_schedules.sql',
    '0009_organizations_billing.sql',
    '0010_seed_demo_data.sql',
  ];
  assert.deepEqual(files, expected);
  // Sorted lexicographically == numeric order, since every name shares the
  // same 4-digit zero-padded prefix width.
  assert.deepEqual(files, [...files].sort());
});

test('listMigrationFiles ignores non-matching files in the directory (e.g. a stray README)', () => {
  const files = listMigrationFiles();
  for (const name of files) {
    assert.match(name, MIGRATION_NAME_PATTERN, `${name} should match MIGRATION_NAME_PATTERN`);
  }
  // Directory itself shouldn't contain anything else that looks like SQL and
  // got left out by accident.
  const allEntries = fs.readdirSync(MIGRATIONS_DIR);
  const strayNonSql = allEntries.filter(name => !MIGRATION_NAME_PATTERN.test(name) && name !== '.gitkeep');
  assert.deepEqual(strayNonSql, [], `unexpected files in db/migrations/: ${strayNonSql.join(', ')}`);
});

// --- lintMigrationSql: run for real against every actual migration file ---
// Directly answers the original reviewer's "make constraint changes
// idempotent" concern: proves every migration in the repo passes the
// idempotency lint, not just that the linter works on synthetic input.

test('every real migration file passes lintMigrationSql with zero problems', () => {
  const files = listMigrationFiles();
  assert.ok(files.length > 0, 'expected at least one migration file to check');
  for (const name of files) {
    const sql = fs.readFileSync(path.join(MIGRATIONS_DIR, name), 'utf8');
    const problems = lintMigrationSql(sql);
    assert.deepEqual(problems, [], `${name} is not idempotent: ${problems.join('; ')}`);
  }
});

test('lintMigrationSql flags a bare CREATE TABLE without IF NOT EXISTS', () => {
  const problems = lintMigrationSql('CREATE TABLE widgets (id uuid PRIMARY KEY);');
  assert.equal(problems.length, 1);
  assert.match(problems[0], /CREATE TABLE widgets is missing IF NOT EXISTS/);
});

test('lintMigrationSql flags a bare CREATE INDEX / CREATE UNIQUE INDEX without IF NOT EXISTS', () => {
  assert.deepEqual(
    lintMigrationSql('CREATE INDEX widgets_name_idx ON widgets(name);'),
    ['CREATE INDEX widgets_name_idx is missing IF NOT EXISTS'],
  );
  assert.deepEqual(
    lintMigrationSql('CREATE UNIQUE INDEX widgets_slug_idx ON widgets(slug);'),
    ['CREATE INDEX widgets_slug_idx is missing IF NOT EXISTS'],
  );
});

test('lintMigrationSql flags a bare ALTER TABLE ADD COLUMN without IF NOT EXISTS', () => {
  const problems = lintMigrationSql('ALTER TABLE widgets ADD COLUMN color text;');
  assert.equal(problems.length, 1);
  assert.match(problems[0], /ALTER TABLE widgets ADD COLUMN color is missing IF NOT EXISTS/);
});

test('lintMigrationSql flags ADD CONSTRAINT with no matching DROP CONSTRAINT IF EXISTS', () => {
  const problems = lintMigrationSql('ALTER TABLE widgets ADD CONSTRAINT widgets_fk FOREIGN KEY (owner_id) REFERENCES owners(id);');
  assert.equal(problems.length, 1);
  assert.match(problems[0], /ADD CONSTRAINT widgets_fk has no matching DROP CONSTRAINT IF EXISTS/);
});

test('lintMigrationSql passes a properly guarded DROP-then-ADD CONSTRAINT pair', () => {
  const sql = `
    ALTER TABLE widgets DROP CONSTRAINT IF EXISTS widgets_fk;
    ALTER TABLE widgets ADD CONSTRAINT widgets_fk FOREIGN KEY (owner_id) REFERENCES owners(id);
  `;
  assert.deepEqual(lintMigrationSql(sql), []);
});

test('lintMigrationSql ignores CREATE TABLE / CONSTRAINT keywords that only appear inside -- comments', () => {
  const sql = `
    -- CREATE TABLE widgets (id uuid); -- this is just an example in a comment
    -- ALTER TABLE widgets ADD CONSTRAINT widgets_fk FOREIGN KEY (x) REFERENCES y(id);
    CREATE TABLE IF NOT EXISTS widgets (id uuid PRIMARY KEY);
  `;
  assert.deepEqual(lintMigrationSql(sql), []);
});

// --- computePending: pure function, no I/O ---

test('computePending returns files not present in appliedVersions', () => {
  const files = ['0001_a.sql', '0002_b.sql', '0003_c.sql'];
  assert.deepEqual(computePending(files, []), files);
  assert.deepEqual(computePending(files, ['0001_a.sql']), ['0002_b.sql', '0003_c.sql']);
  assert.deepEqual(computePending(files, ['0001_a.sql', '0002_b.sql', '0003_c.sql']), []);
});

test('computePending tolerates an applied version not present in files (e.g. a removed migration)', () => {
  const files = ['0002_b.sql'];
  assert.deepEqual(computePending(files, ['0001_a.sql']), ['0002_b.sql']);
});

// --- buildPoolConfig: discrete PG* vars take precedence over DATABASE_URL ---

test('buildPoolConfig prefers discrete PG* vars when present', () => {
  const config = buildPoolConfig({ PGHOST: 'db.internal', PGPORT: '6543', PGUSER: 'u', PGPASSWORD: 'p', PGDATABASE: 'd', DATABASE_URL: 'postgresql://ignored' });
  assert.deepEqual(config, { host: 'db.internal', port: 6543, user: 'u', password: 'p', database: 'd' });
});

test('buildPoolConfig falls back to DATABASE_URL when no discrete PG* vars are set', () => {
  const config = buildPoolConfig({ DATABASE_URL: 'postgresql://custom' });
  assert.deepEqual(config, { connectionString: 'postgresql://custom' });
});

test('buildPoolConfig falls back to the local-dev default connection string when nothing is set', () => {
  const config = buildPoolConfig({});
  assert.match(config.connectionString, /^postgresql:\/\//);
});

// --- run(): applied/pending/apply logic against a mocked pg.Pool/client ---
// No live database available here (Docker-less sandbox), so `run()` is
// exercised via dependency injection (the `pool` option) against an
// in-memory fake that mimics the subset of the pg.Pool/Client API this
// script actually uses: connect(), query(text, params?), release().

function makeFakeClient({ appliedVersions = [], onQuery } = {}) {
  const applied = new Set(appliedVersions);
  const calls = [];
  const client = {
    calls,
    released: false,
    async query(text, params) {
      calls.push({ text, params });
      if (onQuery) {
        const result = await onQuery(text, params, { applied });
        if (result !== undefined) return result;
      }
      if (/CREATE TABLE IF NOT EXISTS schema_migrations/.test(text)) return { rows: [] };
      if (/SELECT version FROM schema_migrations/.test(text)) {
        return { rows: [...applied].sort().map(version => ({ version })) };
      }
      if (/INSERT INTO schema_migrations/.test(text)) {
        applied.add(params[0]);
        return { rows: [] };
      }
      if (text === 'BEGIN' || text === 'COMMIT' || text === 'ROLLBACK') return { rows: [] };
      // Any other statement is a migration file's own SQL body being
      // "executed" -- the fake accepts it without doing anything, since
      // these tests are about the runner's control flow, not real DDL.
      return { rows: [] };
    },
    release() {
      this.released = true;
    },
  };
  return client;
}

function makeFakePool(client) {
  return { async connect() { return client; } };
}

test('run({statusOnly:true}) reports applied vs pending without changing anything, using a temp migrations dir', async () => {
  const tmpDir = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'migrate-test-'));
  try {
    fs.writeFileSync(path.join(tmpDir, '0001_a.sql'), 'CREATE TABLE IF NOT EXISTS a (id int);\n');
    fs.writeFileSync(path.join(tmpDir, '0002_b.sql'), 'CREATE TABLE IF NOT EXISTS b (id int);\n');
    const client = makeFakeClient({ appliedVersions: ['0001_a.sql'] });
    const pool = makeFakePool(client);

    const result = await run({ statusOnly: true, migrationsDir: tmpDir, pool });

    assert.deepEqual(result.applied, ['0001_a.sql']);
    assert.deepEqual(result.pending, ['0002_b.sql']);
    // No INSERT into schema_migrations should have happened in status mode.
    assert.ok(!client.calls.some(call => /INSERT INTO schema_migrations/.test(call.text)));
    assert.ok(client.released, 'client should be released even in status-only mode');
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('run() applies pending migrations in order and records each in schema_migrations', async () => {
  const tmpDir = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'migrate-test-'));
  try {
    fs.writeFileSync(path.join(tmpDir, '0001_a.sql'), 'CREATE TABLE IF NOT EXISTS a (id int);\n');
    fs.writeFileSync(path.join(tmpDir, '0002_b.sql'), 'CREATE TABLE IF NOT EXISTS b (id int);\n');
    const client = makeFakeClient({ appliedVersions: [] });
    const pool = makeFakePool(client);

    const result = await run({ migrationsDir: tmpDir, pool });

    assert.deepEqual(result.appliedNow, ['0001_a.sql', '0002_b.sql']);
    const insertedOrder = client.calls
      .filter(call => /INSERT INTO schema_migrations/.test(call.text))
      .map(call => call.params[0]);
    assert.deepEqual(insertedOrder, ['0001_a.sql', '0002_b.sql']);
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('run() skips migrations already recorded as applied', async () => {
  const tmpDir = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'migrate-test-'));
  try {
    fs.writeFileSync(path.join(tmpDir, '0001_a.sql'), 'CREATE TABLE IF NOT EXISTS a (id int);\n');
    fs.writeFileSync(path.join(tmpDir, '0002_b.sql'), 'CREATE TABLE IF NOT EXISTS b (id int);\n');
    const client = makeFakeClient({ appliedVersions: ['0001_a.sql', '0002_b.sql'] });
    const pool = makeFakePool(client);

    const result = await run({ migrationsDir: tmpDir, pool });

    assert.deepEqual(result.appliedNow, []);
    assert.ok(!client.calls.some(call => /INSERT INTO schema_migrations/.test(call.text)));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('run({dryRun:true}) reports what would apply without executing SQL or recording anything', async () => {
  const tmpDir = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'migrate-test-'));
  try {
    fs.writeFileSync(path.join(tmpDir, '0001_a.sql'), 'CREATE TABLE IF NOT EXISTS a (id int);\n');
    const client = makeFakeClient({ appliedVersions: [] });
    const pool = makeFakePool(client);

    const result = await run({ dryRun: true, migrationsDir: tmpDir, pool });

    assert.deepEqual(result.appliedNow, []);
    assert.ok(!client.calls.some(call => /INSERT INTO schema_migrations/.test(call.text)));
    assert.ok(!client.calls.some(call => call.text === 'BEGIN'));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('run() refuses to apply a non-idempotent migration and leaves earlier migrations committed', async () => {
  const tmpDir = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'migrate-test-'));
  try {
    fs.writeFileSync(path.join(tmpDir, '0001_a.sql'), 'CREATE TABLE IF NOT EXISTS a (id int);\n');
    fs.writeFileSync(path.join(tmpDir, '0002_bad.sql'), 'CREATE TABLE bad (id int);\n'); // missing IF NOT EXISTS
    const client = makeFakeClient({ appliedVersions: [] });
    const pool = makeFakePool(client);

    await assert.rejects(
      run({ migrationsDir: tmpDir, pool }),
      /Refusing to apply 0002_bad\.sql: not idempotent/,
    );

    const insertedOrder = client.calls
      .filter(call => /INSERT INTO schema_migrations/.test(call.text))
      .map(call => call.params[0]);
    assert.deepEqual(insertedOrder, ['0001_a.sql'], '0001 should still have been applied before the lint failure on 0002');
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test('run() rolls back and rethrows when a migration statement itself fails', async () => {
  const tmpDir = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'migrate-test-'));
  try {
    fs.writeFileSync(path.join(tmpDir, '0001_boom.sql'), 'CREATE TABLE IF NOT EXISTS boom (id int);\n');
    const client = makeFakeClient({
      appliedVersions: [],
      onQuery: async (text) => {
        if (text.includes('CREATE TABLE IF NOT EXISTS boom')) throw new Error('relation "boom" already exists (simulated)');
      },
    });
    const pool = makeFakePool(client);

    await assert.rejects(
      run({ migrationsDir: tmpDir, pool }),
      /Migration 0001_boom\.sql failed: relation "boom" already exists \(simulated\)/,
    );

    assert.ok(client.calls.some(call => call.text === 'ROLLBACK'), 'expected a ROLLBACK after the failed statement');
    assert.ok(!client.calls.some(call => /INSERT INTO schema_migrations/.test(call.text)));
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});
