const test = require('node:test');
const assert = require('node:assert/strict');
const { app } = require('../server');

const SERVER_PATH = require.resolve('../server');

// Same fresh-require pattern used in organizations-billing.test.js -- needed
// here so rate-limit tests can use a low, fast-to-hit AUTH_RATE_LIMIT_MAX
// without affecting the shared rate limiter every other test in this suite
// runs against via the top-level `app`.
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

async function withApp(appInstance, fn) {
  const server = appInstance.listen(0);
  try {
    await new Promise(resolve => server.once('listening', resolve));
    return await fn(`http://127.0.0.1:${server.address().port}`);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

test('Helmet security headers are present on every response', async () => {
  await withApp(app, async baseUrl => {
    const response = await fetch(`${baseUrl}/api/auth/status`);
    assert.ok(response.headers.get('content-security-policy'), 'expected a Content-Security-Policy header');
    assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
    assert.equal(response.headers.get('x-powered-by'), null, 'x-powered-by should stay disabled (app.disable already did this; helmet must not reintroduce it)');
  });
});

test('CSP allows the exact basemap tile hosts index.html actually loads from', async () => {
  await withApp(app, async baseUrl => {
    const response = await fetch(`${baseUrl}/api/auth/status`);
    const csp = response.headers.get('content-security-policy');
    for (const host of ['*.tile.openstreetmap.org', '*.tile.openstreetmap.fr', '*.basemaps.cartocdn.com', 'server.arcgisonline.com', 'unpkg.com']) {
      assert.ok(csp.includes(host), `expected CSP to mention ${host}, got: ${csp}`);
    }
  });
});

test('CORS: an unlisted Origin does not get Access-Control-Allow-Origin reflected', async () => {
  await withApp(app, async baseUrl => {
    const response = await fetch(`${baseUrl}/api/auth/status`, { headers: { origin: 'https://evil.example.com' } });
    assert.equal(response.headers.get('access-control-allow-origin'), null);
  });
});

test('CORS: an explicitly allowed Origin (via CORS_ALLOWED_ORIGINS) is reflected', async () => {
  const fresh = freshServerWithEnv({ CORS_ALLOWED_ORIGINS: 'https://trusted.example.com' });
  try {
    await withApp(fresh.app, async baseUrl => {
      const response = await fetch(`${baseUrl}/api/auth/status`, { headers: { origin: 'https://trusted.example.com' } });
      assert.equal(response.headers.get('access-control-allow-origin'), 'https://trusted.example.com');
      assert.equal(response.headers.get('access-control-allow-credentials'), 'true');
    });
  } finally {
    fresh.restore();
  }
});

test('CSRF: a cookie-authenticated POST with no Origin/Referer is rejected', async () => {
  await withApp(app, async baseUrl => {
    const response = await fetch(`${baseUrl}/api/projects`, {
      method: 'POST',
      headers: { cookie: 'cartogen_session=tok', 'content-type': 'application/json' },
      body: '{}',
    });
    assert.equal(response.status, 403);
    const body = await response.json();
    assert.match(body.error, /Origin\/Referer/);
  });
});

test('CSRF: a cookie-authenticated POST from a cross-site Origin is rejected', async () => {
  await withApp(app, async baseUrl => {
    const response = await fetch(`${baseUrl}/api/projects`, {
      method: 'POST',
      headers: { cookie: 'cartogen_session=tok', 'content-type': 'application/json', origin: 'https://evil.example.com' },
      body: '{}',
    });
    assert.equal(response.status, 403);
    const body = await response.json();
    assert.match(body.error, /Cross-origin/);
  });
});

test('CSRF: a cookie-authenticated POST from the app\'s own origin is not blocked by CSRF (falls through to normal auth)', async () => {
  await withApp(app, async baseUrl => {
    const response = await fetch(`${baseUrl}/api/projects`, {
      method: 'POST',
      headers: { cookie: 'cartogen_session=tok', 'content-type': 'application/json', origin: baseUrl },
      body: '{}',
    });
    // Demo-mode server: a directus-style session cookie means nothing here,
    // so this reaches normal identity resolution and gets rejected for a
    // reason that has nothing to do with CSRF -- the point is it's NOT 403
    // with the CSRF error, proving the same-origin request passed the check.
    assert.notEqual(response.status, 403);
  });
});

test('CSRF: a request with no session cookie at all is never blocked by CSRF (nothing to forge)', async () => {
  await withApp(app, async baseUrl => {
    const response = await fetch(`${baseUrl}/api/projects`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-demo-organization': 'demo-humanitarian-lab' },
      body: '{}',
    });
    assert.notEqual(response.status, 403);
  });
});

test('CSRF: GET requests are never subject to the check, even cookie-authenticated ones', async () => {
  await withApp(app, async baseUrl => {
    const response = await fetch(`${baseUrl}/api/auth/status`, { headers: { cookie: 'cartogen_session=tok' } });
    assert.notEqual(response.status, 403);
  });
});

test('rate limiting: /api/auth/login returns 429 after the configured max within the window', async () => {
  const fresh = freshServerWithEnv({ PHASE1_IDENTITY_MODE: 'directus', AUTH_RATE_LIMIT_MAX: '2', AUTH_RATE_LIMIT_WINDOW_MS: '60000' });
  try {
    await withApp(fresh.app, async baseUrl => {
      const attempt = () => fetch(`${baseUrl}/api/auth/login`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email: 'a@example.com', password: 'wrong-password' }),
      });
      const first = await attempt();
      const second = await attempt();
      const third = await attempt();
      // The first two count against the limit regardless of outcome (they'll
      // fail login against a non-existent Directus at 127.0.0.1:8055, but the
      // limiter runs before that handler logic and counts the attempt either way).
      assert.notEqual(first.status, 429);
      assert.notEqual(second.status, 429);
      assert.equal(third.status, 429, 'a third attempt within the window should be rate-limited');
    });
  } finally {
    fresh.restore();
  }
});

test('rate limiting: /api/datasets/search returns 429 after the configured max within the window', async () => {
  const fresh = freshServerWithEnv({ HDX_RATE_LIMIT_MAX: '1', HDX_RATE_LIMIT_WINDOW_MS: '60000' });
  const originalFetch = global.fetch;
  global.fetch = async (url, opts) => {
    if (String(url).includes('humdata.org')) return { ok: true, json: async () => ({ result: { results: [] } }) };
    return originalFetch(url, opts);
  };
  try {
    await withApp(fresh.app, async baseUrl => {
      const attempt = () => fetch(`${baseUrl}/api/datasets/search?q=health`, { headers: { 'x-demo-organization': 'demo-humanitarian-lab' } });
      const first = await attempt();
      const second = await attempt();
      assert.notEqual(first.status, 429);
      assert.equal(second.status, 429, 'a second search within the window should be rate-limited');
    });
  } finally {
    global.fetch = originalFetch;
    fresh.restore();
  }
});
