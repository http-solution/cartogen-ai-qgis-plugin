const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { parseEnvFile, validate } = require('../scripts/validate_env');

const REQUIRED_FIELDS = {
  POSTGRES_PASSWORD: 'a1b2c3d4e5f6',
  DIRECTUS_KEY: 'key',
  DIRECTUS_SECRET: 'secret',
  DIRECTUS_ADMIN_EMAIL: 'admin@example.com',
  DIRECTUS_ADMIN_PASSWORD: 'password',
  LITELLM_MASTER_KEY: 'master-key',
};

test('validate() accepts a fully-populated, URL-safe .env', () => {
  assert.deepEqual(validate({ ...REQUIRED_FIELDS }), []);
});

test('validate() rejects a POSTGRES_PASSWORD containing URI-reserved characters', () => {
  const problems = validate({ ...REQUIRED_FIELDS, POSTGRES_PASSWORD: 'p@ss:word/with#chars' });
  assert.equal(problems.length, 1);
  assert.match(problems[0], /URI-reserved character/);
});

test('validate() rejects each URI-reserved character individually', () => {
  for (const char of ['@', ':', '/', '?', '#']) {
    const problems = validate({ ...REQUIRED_FIELDS, POSTGRES_PASSWORD: `safe${char}password` });
    assert.equal(problems.length, 1, `expected exactly one problem for character "${char}"`);
  }
});

test('validate() rejects unfilled .env.example placeholders', () => {
  const problems = validate({ ...REQUIRED_FIELDS, POSTGRES_PASSWORD: 'CHANGE_ME_LONG_RANDOM_DATABASE_PASSWORD' });
  assert.equal(problems.length, 1);
  assert.match(problems[0], /placeholder/);
});

test('validate() flags every missing required field', () => {
  const problems = validate({});
  // POSTGRES_PASSWORD unset, plus the 5 DIRECTUS_*/LITELLM_MASTER_KEY fields.
  assert.equal(problems.length, 6);
});

test('validate() flags an enabled legacy fallback with no target organization', () => {
  const problems = validate({ ...REQUIRED_FIELDS, PHASE1_IDENTITY_MODE: 'directus', PHASE1_ALLOW_LEGACY_ORG_FALLBACK: 'true' });
  assert.ok(problems.some(problem => /nothing to fall back to/.test(problem)));
});

test('parseEnvFile() reads KEY=VALUE lines, skips comments/blanks, and strips quotes', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'validate-env-test-'));
  const envPath = path.join(dir, '.env');
  fs.writeFileSync(
    envPath,
    [
      '# a comment',
      '',
      'POSTGRES_PASSWORD=unquoted-value',
      'DIRECTUS_KEY="quoted value"',
      "DIRECTUS_SECRET='single-quoted'",
      'PHASE1_ALLOW_LEGACY_ORG_FALLBACK=true',
    ].join('\n'),
  );
  try {
    const values = parseEnvFile(envPath);
    assert.equal(values.POSTGRES_PASSWORD, 'unquoted-value');
    assert.equal(values.DIRECTUS_KEY, 'quoted value');
    assert.equal(values.DIRECTUS_SECRET, 'single-quoted');
    assert.equal(values.PHASE1_ALLOW_LEGACY_ORG_FALLBACK, 'true');
    assert.equal('# a comment' in values, false);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
