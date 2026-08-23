const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeFeatureCollection } = require('../server');

test('normalizes a valid GeoJSON FeatureCollection', () => {
  const result = normalizeFeatureCollection({
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [67.01, 24.86] },
      properties: { name: 'Facility' },
    }],
  });
  assert.equal(result.length, 1);
  assert.deepEqual(result[0].properties, { name: 'Facility' });
});

test('rejects non-FeatureCollection input', () => {
  assert.throws(() => normalizeFeatureCollection({ type: 'Feature', geometry: null }), /FeatureCollection/);
});

test('rejects features without geometry', () => {
  assert.throws(() => normalizeFeatureCollection({
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: {} }],
  }), /no valid geometry/);
});

test('rejects more than 1000 features', () => {
  const features = Array.from({ length: 1001 }, () => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [0, 0] },
    properties: {},
  }));
  assert.throws(() => normalizeFeatureCollection({ type: 'FeatureCollection', features }), /1000/);
});
