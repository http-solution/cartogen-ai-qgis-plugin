const test = require('node:test');
const assert = require('node:assert/strict');
const {
  normalizeFeatureEditRequest,
  canonicalFeatureState,
  hashFeatureState,
  createEditPreviewToken,
  verifyEditPreviewToken,
  normalizeGeometryOperation,
  applyGeometryOperation,
} = require('../server');

test('normalizes a safe feature edit and computes stable state hash', () => {
  const before = { geometry: { type: 'Point', coordinates: [67.01, 24.86] }, properties: { name: 'Clinic', count: 2 } };
  const request = normalizeFeatureEditRequest({ mode: 'preview', properties: { count: 3 } });
  assert.equal(request.mode, 'preview');
  assert.deepEqual(request.properties, { count: 3 });
  assert.equal(hashFeatureState(before), hashFeatureState({ properties: { count: 2, name: 'Clinic' }, geometry: before.geometry }));
  assert.match(canonicalFeatureState(before), /"geometry"/);
});

test('rejects unapproved apply, invalid geometry, and invalid properties', () => {
  assert.throws(() => normalizeFeatureEditRequest({ mode: 'apply', properties: {} }), /approved/);
  assert.throws(() => normalizeFeatureEditRequest({ mode: 'preview', geometry: { type: 'Point', coordinates: [999, 1] } }), /coordinates/);
  assert.throws(() => normalizeFeatureEditRequest({ mode: 'preview', properties: [] }), /properties/);
});

test('preview tokens are scoped to the proposed state and cannot be tampered with', () => {
  const token = createEditPreviewToken({ layerId: 'layer-1', featureId: '7', beforeHash: 'before', afterHash: 'after' });
  assert.deepEqual(verifyEditPreviewToken(token), { layerId: 'layer-1', featureId: '7', beforeHash: 'before', afterHash: 'after' });
  assert.equal(verifyEditPreviewToken(`${token}x`), null);
});

test('normalizes and previews move, reverse, and scale geometry operations', () => {
  const line = { type: 'LineString', coordinates: [[1, 2], [3, 4], [5, 2]] };
  assert.deepEqual(normalizeGeometryOperation({ operation: 'move', dx: 2, dy: -1 }), { operation: 'move', dx: 2, dy: -1 });
  assert.deepEqual(applyGeometryOperation(line, normalizeGeometryOperation({ operation: 'move', dx: 2, dy: -1 })), {
    type: 'LineString', coordinates: [[3, 1], [5, 3], [7, 1]],
  });
  assert.deepEqual(applyGeometryOperation(line, normalizeGeometryOperation({ operation: 'reverse' })), {
    type: 'LineString', coordinates: [[5, 2], [3, 4], [1, 2]],
  });
  assert.deepEqual(applyGeometryOperation({ type: 'Point', coordinates: [2, 3] }, normalizeGeometryOperation({ operation: 'scale', factor: 2, origin: [0, 0] })), {
    type: 'Point', coordinates: [4, 6],
  });
});

test('wires a geometry operation through the edit preview contract and rejects unsafe operations', () => {
  const edit = normalizeFeatureEditRequest({ mode: 'preview', geometry_operation: { operation: 'move', dx: 1, dy: 2 } });
  assert.deepEqual(edit.geometry_operation, { operation: 'move', dx: 1, dy: 2 });
  assert.throws(() => normalizeGeometryOperation({ operation: 'trim' }), /requires|unsupported|parameter|integer/i);
  assert.throws(() => normalizeGeometryOperation({ operation: 'move', dx: Infinity, dy: 0 }), /number/i);
});

test('splits lines only at safe interior vertices and explicitly supplied polygon parts', () => {
  const line = { type: 'LineString', coordinates: [[0, 0], [1, 1], [2, 0], [3, 1]] };
  assert.deepEqual(applyGeometryOperation(line, normalizeGeometryOperation({ operation: 'split', index: 2 })), {
    type: 'MultiLineString', coordinates: [[[0, 0], [1, 1], [2, 0]], [[2, 0], [3, 1]]],
  });
  assert.throws(() => applyGeometryOperation(line, normalizeGeometryOperation({ operation: 'split', index: 0 })), /at least 2/);
  const parts = [
    [[0, 0], [2, 0], [2, 2], [0, 0]],
    [[2, 0], [4, 0], [4, 2], [2, 0]],
  ];
  const polygon = { type: 'Polygon', coordinates: [[[0, 0], [4, 0], [4, 2], [0, 0]]] };
  assert.equal(applyGeometryOperation(polygon, normalizeGeometryOperation({ operation: 'split', parts })).type, 'MultiPolygon');
  assert.throws(() => normalizeGeometryOperation({ operation: 'split' }), /requires/);
});

test('adds and deletes polygon rings without allowing an exterior-ring deletion', () => {
  const polygon = { type: 'Polygon', coordinates: [[[0, 0], [5, 0], [5, 5], [0, 0]], [[1, 1], [2, 1], [2, 2], [1, 1]]] };
  const ring = [[3, 3], [4, 3], [4, 4], [3, 3]];
  const added = applyGeometryOperation(polygon, normalizeGeometryOperation({ operation: 'add_ring', ring }));
  assert.equal(added.coordinates.length, 3);
  assert.equal(applyGeometryOperation(added, normalizeGeometryOperation({ operation: 'delete_ring', index: 1 })).coordinates.length, 2);
  assert.throws(() => applyGeometryOperation(polygon, normalizeGeometryOperation({ operation: 'delete_ring', index: 0 })), /interior/);
  assert.throws(() => normalizeGeometryOperation({ operation: 'add_ring', ring: [[0, 0], [1, 1]] }), /closed/);
});

test('simplify honors the requested tolerance via Douglas-Peucker instead of a fixed decimation', () => {
  // (5, 0.01) deviates from the straight (0,0)-(10,0) line by exactly 0.01 degrees.
  const line = { type: 'LineString', coordinates: [[0, 0], [5, 0.01], [10, 0]] };
  const loose = applyGeometryOperation(line, normalizeGeometryOperation({ operation: 'simplify', tolerance: 1 }));
  assert.deepEqual(loose.coordinates, [[0, 0], [10, 0]]);
  const tight = applyGeometryOperation(line, normalizeGeometryOperation({ operation: 'simplify', tolerance: 0.001 }));
  assert.deepEqual(tight.coordinates, [[0, 0], [5, 0.01], [10, 0]]);
  // Endpoints are never moved or dropped, even at a very loose tolerance.
  const zigzag = { type: 'LineString', coordinates: [[0, 0], [1, 5], [2, -5], [3, 5], [4, 0]] };
  const collapsed = applyGeometryOperation(zigzag, normalizeGeometryOperation({ operation: 'simplify', tolerance: 100 }));
  assert.deepEqual(collapsed.coordinates[0], [0, 0]);
  assert.deepEqual(collapsed.coordinates[collapsed.coordinates.length - 1], [4, 0]);
  // MultiLineString simplifies each part independently.
  const multi = { type: 'MultiLineString', coordinates: [[[0, 0], [5, 0.01], [10, 0]], [[0, 0], [5, 0.01], [10, 0]]] };
  const multiResult = applyGeometryOperation(multi, normalizeGeometryOperation({ operation: 'simplify', tolerance: 1 }));
  assert.deepEqual(multiResult.coordinates, [[[0, 0], [10, 0]]].concat([[[0, 0], [10, 0]]]));
  assert.throws(() => applyGeometryOperation({ type: 'Point', coordinates: [0, 0] }, normalizeGeometryOperation({ operation: 'simplify', tolerance: 1 })), /line geometry/);
});

test('supports safe multi-part edits, reshape, and feature arrays', () => {
  const multiLine = { type: 'MultiLineString', coordinates: [[[0, 0], [1, 1]]] };
  const added = applyGeometryOperation(multiLine, normalizeGeometryOperation({ operation: 'add_part', part: [[2, 2], [3, 3]] }));
  assert.equal(added.coordinates.length, 2);
  assert.equal(applyGeometryOperation(added, normalizeGeometryOperation({ operation: 'delete_part', index: 0 })).coordinates.length, 1);
  assert.deepEqual(applyGeometryOperation({ type: 'LineString', coordinates: [[0, 0], [1, 1]] }, normalizeGeometryOperation({ operation: 'reshape', coordinates: [[2, 2], [3, 3], [4, 2]] })).coordinates, [[2, 2], [3, 3], [4, 2]]);
  assert.deepEqual(applyGeometryOperation({ type: 'Point', coordinates: [0, 0] }, normalizeGeometryOperation({ operation: 'feature_array', geometries: [{ type: 'Point', coordinates: [1, 1] }, { type: 'Point', coordinates: [2, 2] }] })), { type: 'MultiPoint', coordinates: [[1, 1], [2, 2]] });
  assert.throws(() => normalizeGeometryOperation({ operation: 'feature_array', geometries: [] }), /non-empty/);
  assert.throws(() => applyGeometryOperation(multiLine, normalizeGeometryOperation({ operation: 'delete_part', index: 0 })), /at least one/);
});
