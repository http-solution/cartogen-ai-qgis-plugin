#!/usr/bin/env node
// Preflight check for web-platform/phase-1/.env, run before `docker compose up`.
//
// Exists specifically to close a gap that can't be fixed inside the compose
// file itself: LiteLLM's own DATABASE_URL is assembled by docker-compose's
// ${VAR} substitution, which does no URL-encoding. A POSTGRES_PASSWORD
// containing @ : / ? # would silently corrupt that URL rather than failing
// loudly -- LiteLLM would just fail to reach its database with a confusing
// error, or worse, connect to the wrong thing if the corrupted string still
// happens to parse. phase1-api and phase1-worker aren't at risk (server.js
// prefers discrete PGHOST/PGUSER/PGPASSWORD/PGDATABASE over a URL), but
// LiteLLM's Prisma-based storage layer requires a single connection URL, so
// there's no equivalent fix on that side -- the password itself has to be
// URL-safe. This script makes that a loud, actionable failure instead of a
// silent one.
//
// Usage: node scripts/validate_env.js [path-to-.env]
// Exit code 0 = safe to `docker compose up`. Non-zero = fix the listed
// problems first.

const fs = require('node:fs');
const path = require('node:path');

const URI_RESERVED_CHARS = /[@:/?#]/;
const PLACEHOLDER_PATTERN = /CHANGE_ME/i;

function parseEnvFile(filePath) {
  const raw = fs.readFileSync(filePath, 'utf8');
  const values = {};
  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq < 0) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values[key] = value;
  }
  return values;
}

function validate(values) {
  const problems = [];

  const password = values.POSTGRES_PASSWORD || '';
  if (!password) {
    problems.push('POSTGRES_PASSWORD is not set.');
  } else if (PLACEHOLDER_PATTERN.test(password)) {
    problems.push('POSTGRES_PASSWORD still looks like the .env.example placeholder -- generate a real one.');
  } else if (URI_RESERVED_CHARS.test(password)) {
    problems.push(
      'POSTGRES_PASSWORD contains a URI-reserved character (one of @ : / ? #). ' +
      "LiteLLM's DATABASE_URL is built by docker-compose string interpolation with no URL-encoding step, " +
      'so this password would silently corrupt that connection string. ' +
      'Regenerate it with something URL-safe only, e.g.: openssl rand -hex 32',
    );
  }

  for (const key of ['DIRECTUS_KEY', 'DIRECTUS_SECRET', 'DIRECTUS_ADMIN_EMAIL', 'DIRECTUS_ADMIN_PASSWORD', 'LITELLM_MASTER_KEY']) {
    const value = values[key] || '';
    if (!value) problems.push(`${key} is not set.`);
    else if (PLACEHOLDER_PATTERN.test(value)) problems.push(`${key} still looks like the .env.example placeholder -- set a real value.`);
  }

  if (values.PHASE1_IDENTITY_MODE === 'directus' && values.PHASE1_ALLOW_LEGACY_ORG_FALLBACK === 'true' && !values.PHASE1_DIRECTUS_ORGANIZATION_ID) {
    problems.push('PHASE1_ALLOW_LEGACY_ORG_FALLBACK=true but PHASE1_DIRECTUS_ORGANIZATION_ID is unset -- the fallback has nothing to fall back to.');
  }

  return problems;
}

function main(argv) {
  const envPath = argv[2] || path.join(__dirname, '..', '.env');
  if (!fs.existsSync(envPath)) {
    console.error(`No .env file found at ${envPath}. Copy .env.example to .env and fill in every CHANGE_ME value first.`);
    process.exitCode = 1;
    return;
  }
  const values = parseEnvFile(envPath);
  const problems = validate(values);
  if (problems.length) {
    console.error(`${envPath} is not ready for docker compose up:\n`);
    for (const problem of problems) console.error(`  - ${problem}`);
    console.error('');
    process.exitCode = 1;
    return;
  }
  console.log(`${envPath} looks safe to use with docker compose up.`);
}

if (require.main === module) main(process.argv);

module.exports = { parseEnvFile, validate };
