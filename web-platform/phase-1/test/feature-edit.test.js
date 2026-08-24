const test = require('node:test');
const assert = require('node:assert/strict');
const {
  normalizeFeatureEditRequest,
  canonicalFeatureState,
  hashFeatureState,
  createEditPreviewToken,
  verifyEditPreviewToken,
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
