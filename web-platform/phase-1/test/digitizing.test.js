const test = require('node:test');
const assert = require('node:assert/strict');
const { app, pool, normalizeDigitizingFeature } = require('../server');

const validLineString = {
  type: 'LineString',
  coordinates: [[30, -1], [31, 0]],
};
const validPolygon = {
  type: 'Polygon',
  coordinates: [[[30, -1], [31, -1], [31, 0], [30, -1]]],
};

function request(server, body, headers = {}) {
  return fetch(`http://127.0.0.1:${server.address().port}/api/projects/project-1/layers/layer-1/features`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-demo-organization': 'org-1', ...headers },
    body: JSON.stringify(body),
  });
}

test('normalizes only valid LineString and Polygon digitizing features', () => {
  assert.deepEqual(normalizeDigitizingFeature({ geometry: validLineString, properties: { name: 'road' } }), {
    geometry: validLineString,
    properties: { name: 'road' },
  });
  assert.deepEqual(normalizeDigitizingFeature({ geometry: validPolygon, properties: {} }), {
    geometry: validPolygon,
    properties: {},
  });
});

test('normalizes a valid Point digitizing feature', () => {
  assert.deepEqual(normalizeDigitizingFeature({ geometry: { type: 'Point', coordinates: [30, -1] }, properties: { name: 'clinic' } }), {
    geometry: { type: 'Point', coordinates: [30, -1] },
    properties: { name: 'clinic' },
  });
});

test('rejects unsupported geometry, invalid coordinates, short lines, open polygons, and non-object properties', () => {
  assert.throws(() => normalizeDigitizingFeature({ geometry: { type: 'Point', coordinates: [181, -1] }, properties: {} }), /invalid coordinates/);
  assert.throws(() => normalizeDigitizingFeature({ geometry: { type: 'LineString', coordinates: [[30, -1]] }, properties: {} }), /at least 2/);
  assert.throws(() => normalizeDigitizingFeature({ geometry: validLineString, properties: [] }), /properties must be an object/);
  assert.throws(() => normalizeDigitizingFeature({ geometry: { type: 'LineString', coordinates: [[181, 0], [30, 0]] }, properties: {} }), /invalid coordinates/);
  assert.throws(() => normalizeDigitizingFeature({ geometry: { type: 'Polygon', coordinates: [[[30, -1], [31, -1], [31, 0], [30, 0]]] }, properties: {} }), /closed ring/);
  assert.throws(() => normalizeDigitizingFeature({ geometry: { type: 'Polygon', coordinates: [[[30, -1], [31, -1], [30, -1]]] }, properties: {} }), /at least 4/);
});

test('POST creates a scoped feature and creation lineage event transactionally', async () => {
  const originalQuery = pool.query;
  const originalConnect = pool.connect;
  const calls = [];
  pool.query = async (sql, params) => {
    calls.push({ sql, params });
    assert.match(sql, /FROM project_layers l JOIN projects p/);
    return { rowCount: 1, rows: [{ id: 'layer-1' }] };
  };
  const client = {
    query: async (sql, params) => {
      calls.push({ sql, params });
      if (sql.includes('INSERT INTO project_layer_features')) {
        return { rowCount: 1, rows: [{ id: 42, geometry: validLineString, properties: { name: 'road' } }] };
      }
      return { rowCount: 1, rows: [] };
    },
    release() {},
  };
  pool.connect = async () => client;
  const server = app.listen(0);
  try {
    const response = await request(server, { geometry: validLineString, properties: { name: 'road' } });
    assert.equal(response.status, 201);
    const body = await response.json();
    assert.deepEqual(body.feature, { id: 42, geometry: validLineString, properties: { name: 'road' } });
    assert.equal(calls.filter(call => call.sql === 'BEGIN').length, 1);
    assert.equal(calls.filter(call => call.sql === 'COMMIT').length, 1);
    const lineage = calls.find(call => call.sql.includes('INSERT INTO feature_lineage_events'));
    assert.ok(lineage);
    assert.match(lineage.sql, /VALUES \(\$1,\$2,\$3,\$4,'feature_create'/);
    assert.match(lineage.params[5], /^[a-f0-9]{64}$/);
    assert.match(lineage.params[6], /^[a-f0-9]{64}$/);
  } finally {
    await new Promise(resolve => server.close(resolve));
    pool.query = originalQuery;
    pool.connect = originalConnect;
  }
});

test('POST creates a Point and GET reads it back as GeoJSON', async () => {
  const originalQuery = pool.query;
  const originalConnect = pool.connect;
  const point = { type: 'Point', coordinates: [30, -1] };
  pool.query = async sql => {
    if (sql.includes('FROM project_layers l JOIN projects p')) return { rowCount: 1, rows: [{ id: 'layer-1' }] };
    if (sql.includes('ST_AsGeoJSON(f.geometry)')) return { rowCount: 1, rows: [{ id: 43, layer_id: 'layer-1', project_id: 'project-1', organization_id: 'org-1', geometry: point, properties: { name: 'clinic' } }] };
    return { rowCount: 0, rows: [] };
  };
  pool.connect = async () => ({
    query: async sql => sql.includes('INSERT INTO project_layer_features')
      ? { rowCount: 1, rows: [{ id: 43, geometry: point, properties: { name: 'clinic' } }] }
      : { rowCount: 1, rows: [] },
    release() {},
  });
  const server = app.listen(0);
  try {
    const created = await request(server, { geometry: point, properties: { name: 'clinic' } });
    assert.equal(created.status, 201);
    const read = await fetch(`http://127.0.0.1:${server.address().port}/api/layers/layer-1/features/43`, { headers: { 'x-demo-organization': 'org-1' } });
    assert.equal(read.status, 200);
    assert.deepEqual((await read.json()).feature.geometry, point);
  } finally {
    await new Promise(resolve => server.close(resolve));
    pool.query = originalQuery;
    pool.connect = originalConnect;
  }
});

test('POST enforces project/layer scope before opening a transaction', async () => {
  const originalQuery = pool.query;
  const originalConnect = pool.connect;
  let connected = false;
  pool.query = async () => ({ rowCount: 0, rows: [] });
  pool.connect = async () => { connected = true; throw new Error('must not connect'); };
  const server = app.listen(0);
  try {
    const response = await request(server, { geometry: validLineString, properties: {} });
    assert.equal(response.status, 404);
    assert.deepEqual(await response.json(), { error: 'Layer not found' });
    assert.equal(connected, false);
  } finally {
    await new Promise(resolve => server.close(resolve));
    pool.query = originalQuery;
    pool.connect = originalConnect;
  }
});
