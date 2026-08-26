const test = require('node:test');
const assert = require('node:assert/strict');
const { app, pool, normalizeSlug, normalizeOrganizationCreateRequest, normalizeProjectCreateRequest, directusUser } = require('../server');

const SERVER_PATH = require.resolve('../server');

// Re-requires server.js with a temporary env override, for exercising code
// paths gated on module-load-time constants (PHASE1_IDENTITY_MODE,
// PHASE1_ALLOW_LEGACY_ORG_FALLBACK, LITELLM_MASTER_KEY, ...) that the
// top-of-file `require('../server')` above already froze into its own
// `app`/`pool` bindings. The fresh instance is independent of the module
// used by every other test in this file -- restore() puts process.env back
// and busts the cache again so later `require('../server')` calls (in this
// process or, if node:test ever runs files in-process, elsewhere) get a
// clean module rather than one left mutated by a previous test's overrides.
function freshServerWithEnv(overrides) {
  const previous = {};
  for (const [key, value] of Object.entries(overrides)) {
    previous[key] = process.env[key];
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  delete require.cache[SERVER_PATH];
  const fresh = require(SERVER_PATH);
  return {
    ...fresh,
    restore() {
      for (const [key, value] of Object.entries(previous)) {
        if (value === undefined) delete process.env[key];
        else process.env[key] = value;
      }
      delete require.cache[SERVER_PATH];
    },
  };
}

async function withServer(fn) {
  const server = app.listen(0);
  try {
    await new Promise(resolve => server.once('listening', resolve));
    return await fn(`http://127.0.0.1:${server.address().port}`);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

test('normalizeSlug derives a URL-safe, bounded slug', () => {
  assert.equal(normalizeSlug('Regional Response Unit!!'), 'regional-response-unit');
  assert.equal(normalizeSlug('  Already-slug_ish  '), 'already-slug-ish');
  assert.equal(normalizeSlug(''), '');
  assert.equal(normalizeSlug('x'.repeat(100)).length, 64);
});

test('normalizeOrganizationCreateRequest requires a name and derives a slug', () => {
  assert.deepEqual(normalizeOrganizationCreateRequest({ name: 'Regional Response Unit' }), { name: 'Regional Response Unit', slug: 'regional-response-unit' });
  assert.throws(() => normalizeOrganizationCreateRequest({ name: '' }), /name is required/);
  assert.throws(() => normalizeOrganizationCreateRequest({ name: '!!!' }), /slug/);
});

test('normalizeProjectCreateRequest derives an id from name and defaults sector/crs', () => {
  const result = normalizeProjectCreateRequest({ name: 'Coastal Flood Screening' });
  assert.equal(result.id, 'coastal-flood-screening');
  assert.equal(result.name, 'Coastal Flood Screening');
  assert.equal(result.sector, 'general');
  assert.equal(result.crs, 'EPSG:4326');
  assert.throws(() => normalizeProjectCreateRequest({}), /id/);
});

test('GET /api/organizations in demo mode returns the resolved demo organization', async () => {
  const originalQuery = pool.query;
  let queryText = '';
  let queryParams;
  pool.query = async (text, params) => {
    queryText = text;
    queryParams = params;
    return { rows: [{ id: 'demo-humanitarian-lab', name: 'Demo Humanitarian Lab', slug: 'demo-humanitarian-lab' }], rowCount: 1 };
  };
  try {
    await withServer(async baseUrl => {
      const response = await fetch(`${baseUrl}/api/organizations`, { headers: { 'x-demo-organization': 'demo-humanitarian-lab' } });
      assert.equal(response.status, 200);
      const body = await response.json();
      assert.deepEqual(body, { organizations: [{ id: 'demo-humanitarian-lab', name: 'Demo Humanitarian Lab', slug: 'demo-humanitarian-lab', role: 'owner' }] });
    });
  } finally {
    pool.query = originalQuery;
  }
  assert.deepEqual(queryParams, ['demo-humanitarian-lab']);
  assert.match(queryText, /FROM organizations WHERE id = \$1/);
});

test('POST /api/projects is organization-scoped and rejects a missing name', async () => {
  const originalQuery = pool.query;
  const queries = [];
  pool.query = async (text, params) => {
    queries.push({ text, params });
    return { rows: [{ id: 'coastal-flood-screening', name: 'Coastal Flood Screening', sector: 'general', crs: 'EPSG:4326', status: 'draft', metadata: {}, created_at: '2026-08-25T00:00:00Z', updated_at: '2026-08-25T00:00:00Z' }], rowCount: 1 };
  };
  try {
    await withServer(async baseUrl => {
      const created = await fetch(`${baseUrl}/api/projects`, {
        method: 'POST',
        headers: { 'x-demo-organization': 'demo-humanitarian-lab', 'content-type': 'application/json' },
        body: JSON.stringify({ name: 'Coastal Flood Screening' }),
      });
      assert.equal(created.status, 201);

      const rejected = await fetch(`${baseUrl}/api/projects`, {
        method: 'POST',
        headers: { 'x-demo-organization': 'demo-humanitarian-lab', 'content-type': 'application/json' },
        body: JSON.stringify({}),
      });
      assert.equal(rejected.status, 400);
    });
  } finally {
    pool.query = originalQuery;
  }
  assert.equal(queries.length, 1);
  assert.equal(queries[0].params[1], 'demo-humanitarian-lab');
  assert.match(queries[0].text, /INSERT INTO projects/);
});

test('billing routes require organization membership and report unconfigured Stripe cleanly', async () => {
  const originalQuery = pool.query;
  pool.query = async () => ({ rows: [{ stripe_subscription_status: 'none', litellm_virtual_key: null }], rowCount: 1 });
  try {
    await withServer(async baseUrl => {
      const wrongOrg = await fetch(`${baseUrl}/api/organizations/some-other-org/billing`, { headers: { 'x-demo-organization': 'demo-humanitarian-lab' } });
      assert.equal(wrongOrg.status, 404);

      const summary = await fetch(`${baseUrl}/api/organizations/demo-humanitarian-lab/billing`, { headers: { 'x-demo-organization': 'demo-humanitarian-lab' } });
      assert.equal(summary.status, 200);
      const body = await summary.json();
      assert.equal(body.plan.status, 'none');
      assert.equal(body.plan.configured, false);

      const checkout = await fetch(`${baseUrl}/api/organizations/demo-humanitarian-lab/billing/checkout`, { method: 'POST', headers: { 'x-demo-organization': 'demo-humanitarian-lab', 'content-type': 'application/json' }, body: '{}' });
      assert.equal(checkout.status, 503);
    });
  } finally {
    pool.query = originalQuery;
  }
});

// ---------------------------------------------------------------------------
// Regression coverage for the code-review findings fixed on 2026-08-25:
// bearer-token exposure, the organization-membership-bypass fallback,
// missing role check on the billing portal, and Stripe webhook
// idempotency/error-acknowledgment. See server.js comments at each fix site
// for the full rationale.
// ---------------------------------------------------------------------------

test('directusUser() never includes the Directus access token in the object it returns', async () => {
  const originalFetch = global.fetch;
  const secretToken = 'super-secret-directus-access-token';
  global.fetch = async () => ({ ok: true, json: async () => ({ data: { id: 'user-1', email: 'a@example.com' } }) });
  try {
    const user = await directusUser({ headers: { cookie: `cartogen_session=${secretToken}` } });
    assert.equal('accessToken' in user, false);
    assert.doesNotMatch(JSON.stringify(user), new RegExp(secretToken));
  } finally {
    global.fetch = originalFetch;
  }
});

test('GET /api/me never leaks the Directus access token to the browser', async () => {
  const originalFetch = global.fetch;
  const secretToken = 'super-secret-directus-access-token';
  // Only intercept the outbound call to Directus's /users/me -- everything
  // else (the test's own request to the local Express server below) must
  // fall through to the real fetch, or that request never reaches the app.
  global.fetch = async (url, opts) => {
    if (String(url).includes('/users/me')) return { ok: true, json: async () => ({ data: { id: 'user-1', email: 'a@example.com' } }) };
    return originalFetch(url, opts);
  };
  const fresh = freshServerWithEnv({ PHASE1_IDENTITY_MODE: 'directus' });
  try {
    const server = fresh.app.listen(0);
    await new Promise(resolve => server.once('listening', resolve));
    try {
      const baseUrl = `http://127.0.0.1:${server.address().port}`;
      const response = await fetch(`${baseUrl}/api/me`, { headers: { cookie: `cartogen_session=${secretToken}` } });
      assert.equal(response.status, 200);
      const raw = await response.text();
      assert.doesNotMatch(raw, new RegExp(secretToken));
      assert.doesNotMatch(raw, /accessToken/);
    } finally {
      await new Promise(resolve => server.close(resolve));
    }
  } finally {
    global.fetch = originalFetch;
    fresh.restore();
  }
});

test('an authenticated Directus user with no membership row gets no organization access when the legacy fallback is off (the default)', async () => {
  const originalFetch = global.fetch;
  global.fetch = async (url, opts) => {
    if (String(url).includes('/users/me')) return { ok: true, json: async () => ({ data: { id: 'user-no-membership', email: 'a@example.com' } }) };
    return originalFetch(url, opts);
  };
  const fresh = freshServerWithEnv({
    PHASE1_IDENTITY_MODE: 'directus',
    PHASE1_DIRECTUS_ORGANIZATION_ID: 'fallback-org',
    PHASE1_ALLOW_LEGACY_ORG_FALLBACK: undefined, // explicitly unset -- the default
  });
  const originalQuery = fresh.pool.query;
  fresh.pool.query = async () => ({ rows: [], rowCount: 0 }); // no organization_members row
  try {
    const server = fresh.app.listen(0);
    await new Promise(resolve => server.once('listening', resolve));
    try {
      const baseUrl = `http://127.0.0.1:${server.address().port}`;
      const status = await fetch(`${baseUrl}/api/auth/status`, { headers: { cookie: 'cartogen_session=tok' } });
      const body = await status.json();
      assert.equal(body.authenticated, false, 'a user with no membership row and no legacy fallback must not be treated as authenticated into any organization');

      const created = await fetch(`${baseUrl}/api/projects`, {
        method: 'POST',
        headers: { cookie: 'cartogen_session=tok', 'content-type': 'application/json', origin: baseUrl },
        body: JSON.stringify({ name: 'Should Be Rejected' }),
      });
      assert.equal(created.status, 401);
    } finally {
      await new Promise(resolve => server.close(resolve));
    }
  } finally {
    global.fetch = originalFetch;
    fresh.pool.query = originalQuery;
    fresh.restore();
  }
});

test('the legacy organization fallback, once explicitly enabled, grants access but never the owner role', async () => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({ ok: true, json: async () => ({ data: { id: 'user-no-membership', email: 'a@example.com' } }) });
  const fresh = freshServerWithEnv({
    PHASE1_IDENTITY_MODE: 'directus',
    PHASE1_DIRECTUS_ORGANIZATION_ID: 'fallback-org',
    PHASE1_ALLOW_LEGACY_ORG_FALLBACK: 'true',
  });
  const originalQuery = fresh.pool.query;
  fresh.pool.query = async () => ({ rows: [], rowCount: 0 }); // still no organization_members row
  try {
    const resolved = await fresh.resolveIdentity({ headers: { cookie: 'cartogen_session=tok' }, header: () => null });
    assert.ok(resolved, 'the explicitly-enabled fallback should still resolve an identity');
    assert.equal(resolved.organizationId, 'fallback-org');
    assert.equal(resolved.role, 'member', 'the fallback must never grant owner -- there is no real membership row backing this access');
  } finally {
    global.fetch = originalFetch;
    fresh.pool.query = originalQuery;
    fresh.restore();
  }
});

test('billing portal requires an owner/admin role, not just membership', async () => {
  const originalFetch = global.fetch;
  global.fetch = async (url, opts) => {
    if (String(url).includes('/users/me')) return { ok: true, json: async () => ({ data: { id: 'member-user', email: 'member@example.com' } }) };
    return originalFetch(url, opts);
  };
  // A real (test-mode) Stripe secret key so the route gets past its
  // !stripeClient 503 short-circuit and actually reaches the role check
  // this test targets.
  const fresh = freshServerWithEnv({ PHASE1_IDENTITY_MODE: 'directus', STRIPE_SECRET_KEY: 'sk_test_deadbeef' });
  const originalQuery = fresh.pool.query;
  fresh.pool.query = async () => ({ rows: [{ organization_id: 'org-1', role: 'member' }], rowCount: 1 });
  try {
    const server = fresh.app.listen(0);
    await new Promise(resolve => server.once('listening', resolve));
    try {
      const baseUrl = `http://127.0.0.1:${server.address().port}`;
      const portal = await fetch(`${baseUrl}/api/organizations/org-1/billing/portal`, {
        method: 'POST',
        headers: { cookie: 'cartogen_session=tok', 'content-type': 'application/json', origin: baseUrl },
        body: '{}',
      });
      assert.equal(portal.status, 403);
      const portalBody = await portal.json();
      assert.match(portalBody.error, /owner or admin/, 'must be rejected by the role check, not by an unrelated CSRF/origin failure');
    } finally {
      await new Promise(resolve => server.close(resolve));
    }
  } finally {
    global.fetch = originalFetch;
    fresh.pool.query = originalQuery;
    fresh.restore();
  }
});

test('Stripe webhook: a retried checkout.session.completed does not re-provision a LiteLLM key', async () => {
  const originalFetch = global.fetch;
  const fresh = freshServerWithEnv({ LITELLM_MASTER_KEY: 'test-master-key', ALLOW_UNSIGNED_STRIPE_WEBHOOKS: 'true' });
  const originalQuery = fresh.pool.query;

  let liteLlmGenerateCalls = 0;
  global.fetch = async (url, opts) => {
    if (String(url).includes('/key/generate')) {
      liteLlmGenerateCalls += 1;
      return { ok: true, json: async () => ({ key: 'sk-test-key', token: 'tok-1' }) };
    }
    return originalFetch(url, opts);
  };

  const webhookEvents = new Set();
  fresh.pool.query = async (text) => {
    if (/INSERT INTO stripe_webhook_events/.test(text)) {
      if (webhookEvents.has('evt_test_1')) return { rows: [], rowCount: 0 };
      webhookEvents.add('evt_test_1');
      return { rows: [{ event_id: 'evt_test_1' }], rowCount: 1 };
    }
    if (/SELECT name FROM organizations/.test(text)) return { rows: [{ name: 'Test Org' }], rowCount: 1 };
    if (/INSERT INTO organization_billing/.test(text)) return { rows: [], rowCount: 1 };
    return { rows: [], rowCount: 0 };
  };

  const fakeEvent = {
    id: 'evt_test_1',
    type: 'checkout.session.completed',
    data: { object: { id: 'cs_test_1', payment_status: 'paid', metadata: { organization_id: 'org-1' }, customer: 'cus_1', subscription: { id: 'sub_1', status: 'active' } } },
  };

  try {
    const server = fresh.app.listen(0);
    await new Promise(resolve => server.once('listening', resolve));
    try {
      const baseUrl = `http://127.0.0.1:${server.address().port}`;
      const first = await fetch(`${baseUrl}/api/billing/webhook`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(fakeEvent) });
      assert.equal(first.status, 200);
      const firstBody = await first.json();
      assert.equal(firstBody.duplicate, undefined);
      assert.equal(liteLlmGenerateCalls, 1);

      // Stripe retries the same delivery (same event id) after ack timeout.
      const second = await fetch(`${baseUrl}/api/billing/webhook`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(fakeEvent) });
      assert.equal(second.status, 200);
      const secondBody = await second.json();
      assert.equal(secondBody.duplicate, true);
      assert.equal(liteLlmGenerateCalls, 1, 'a retried delivery of an already-processed event must not mint a second LiteLLM key');
    } finally {
      await new Promise(resolve => server.close(resolve));
    }
  } finally {
    global.fetch = originalFetch;
    fresh.pool.query = originalQuery;
    fresh.restore();
  }
});

test('Stripe webhook: a processing failure returns a non-2xx status instead of a false-positive ack', async () => {
  const fresh = freshServerWithEnv({ LITELLM_MASTER_KEY: 'test-master-key', ALLOW_UNSIGNED_STRIPE_WEBHOOKS: 'true' });
  const originalQuery = fresh.pool.query;

  const queries = [];
  fresh.pool.query = async (text) => {
    queries.push(text);
    if (/INSERT INTO stripe_webhook_events/.test(text)) return { rows: [{ event_id: 'evt_test_fail' }], rowCount: 1 };
    if (/SELECT name FROM organizations/.test(text)) throw new Error('simulated database outage');
    return { rows: [], rowCount: 0 };
  };

  const fakeEvent = {
    id: 'evt_test_fail',
    type: 'checkout.session.completed',
    data: { object: { id: 'cs_test_fail', payment_status: 'paid', metadata: { organization_id: 'org-1' }, subscription: { id: 'sub_fail', status: 'active' } } },
  };

  try {
    const server = fresh.app.listen(0);
    await new Promise(resolve => server.once('listening', resolve));
    try {
      const baseUrl = `http://127.0.0.1:${server.address().port}`;
      const response = await fetch(`${baseUrl}/api/billing/webhook`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(fakeEvent) });
      assert.notEqual(response.status, 200, 'a webhook processing failure must not be acknowledged with 200, or Stripe will never retry it');
      assert.ok(queries.some(text => /DELETE FROM stripe_webhook_events/.test(text)), 'the event claim must be released so a genuine retry can reprocess it');
    } finally {
      await new Promise(resolve => server.close(resolve));
    }
  } finally {
    fresh.pool.query = originalQuery;
    fresh.restore();
  }
});
