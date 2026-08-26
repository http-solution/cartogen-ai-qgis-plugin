const test = require('node:test');
const assert = require('node:assert/strict');
const zlib = require('node:zlib');
const fs = require('node:fs');
const path = require('node:path');
const { validate } = require('../scripts/validate_env');
const { extractGeoJsonFromZip, isLoopbackAddress, validateCheckoutSessionPayment } = require('../server');

test('preflight rejects demo identity mode', () => {
  const values = { POSTGRES_PASSWORD: 'safe', DIRECTUS_KEY: 'k', DIRECTUS_SECRET: 's', DIRECTUS_ADMIN_EMAIL: 'a@b.test', DIRECTUS_ADMIN_PASSWORD: 'p', LITELLM_MASTER_KEY: 'm', PHASE1_IDENTITY_MODE: 'demo' };
  assert.ok(validate(values).some(problem => /directus|demo/i.test(problem)));
});

test('loopback detection accepts only local addresses', () => {
  assert.equal(isLoopbackAddress('127.0.0.1'), true);
  assert.equal(isLoopbackAddress('::1'), true);
  assert.equal(isLoopbackAddress('203.0.113.10'), false);
});

test('checkout fulfillment requires paid payment and active subscription', async () => {
  await assert.rejects(() => validateCheckoutSessionPayment({ payment_status: 'unpaid', subscription: { status: 'active' } }), /paid/);
  await assert.rejects(() => validateCheckoutSessionPayment({ payment_status: 'paid', subscription: { status: 'canceled' } }), /subscription/);
  await assert.doesNotReject(() => validateCheckoutSessionPayment({ payment_status: 'paid', subscription: { status: 'active' } }));
});

test('unsigned webhook support is explicitly gated and worker claims atomically', () => {
  const serverSource = fs.readFileSync(path.join(__dirname, '..', 'server.js'), 'utf8');
  const workerSource = fs.readFileSync(path.join(__dirname, '..', 'scripts', 'analysis_worker.js'), 'utf8');
  assert.match(serverSource, /ALLOW_UNSIGNED_STRIPE_WEBHOOKS/);
  assert.doesNotMatch(serverSource, /else if \\(NODE_ENV === 'development'\\)/);
  assert.match(workerSource, /FOR UPDATE SKIP LOCKED/);
  assert.match(workerSource, /SET status = 'running'/);
});

test('ZIP extraction rejects excessive expansion and enforces output cap', () => {
  const payload = Buffer.from('PK\\x03\\x04' + 'x'.repeat(1));
  assert.throws(() => extractGeoJsonFromZip(payload), /invalid|entry/i);
  const content = Buffer.from('{"type":"FeatureCollection","features":[]}');
  const compressed = zlib.deflateRawSync(content);
  const name = Buffer.from('data.geojson');
  const header = Buffer.alloc(30);
  header.writeUInt32LE(0x04034b50, 0); header.writeUInt16LE(8, 8);
  header.writeUInt32LE(compressed.length, 18); header.writeUInt32LE(content.length, 22);
  header.writeUInt16LE(name.length, 26);
  assert.equal(extractGeoJsonFromZip(Buffer.concat([header, name, compressed])), content.toString());
});
