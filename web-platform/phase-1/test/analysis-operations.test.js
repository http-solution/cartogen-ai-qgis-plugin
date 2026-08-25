const test = require('node:test');
const assert = require('node:assert/strict');
const { app, OPERATION_REGISTRY, normalizeAnalysisOperationInput } = require('../server');

test('exposes stable typed spatial operation metadata', () => {
  assert.deepEqual(Object.keys(OPERATION_REGISTRY), ['create_review_output', 'buffer_layer', 'intersect_layers']);
  assert.deepEqual(OPERATION_REGISTRY.buffer_layer, {
    display_name: 'Buffer layer',
    parameter_types: { source_layer_id: 'string', distance_meters: 'number' },
    required_fields: ['source_layer_id', 'distance_meters'],
    read_only: false,
    schedulable: false,
    executor_id: 'buffer_layer',
  });
  assert.equal(OPERATION_REGISTRY.create_review_output.read_only, true);
  assert.equal(OPERATION_REGISTRY.create_review_output.schedulable, true);
});

test('normalizes and type-checks operation inputs', () => {
  assert.deepEqual(normalizeAnalysisOperationInput('buffer_layer', { source_layer_id: 'layer-1', distance_meters: '1250' }), {
    source_layer_id: 'layer-1', distance_meters: 1250,
  });
  assert.deepEqual(normalizeAnalysisOperationInput('intersect_layers', { source_layer_id: 'a', overlay_layer_id: 'b' }), {
    source_layer_id: 'a', overlay_layer_id: 'b',
  });
  assert.deepEqual(normalizeAnalysisOperationInput('create_review_output', { include_layers: true }), { include_layers: true });
  assert.throws(() => normalizeAnalysisOperationInput('unknown_operation', {}), /Unsupported analysis operation/);
  assert.throws(() => normalizeAnalysisOperationInput('buffer_layer', { source_layer_id: 'layer-1', distance_meters: 'not-a-number' }), /distance_meters/);
  assert.throws(() => normalizeAnalysisOperationInput('buffer_layer', { source_layer_id: 'layer-1' }), /required/);
  assert.throws(() => normalizeAnalysisOperationInput('create_review_output', { include_layers: 'yes' }), /include_layers/);
});

test('GET /api/analysis/operations returns organization-independent metadata', async () => {
  const server = app.listen(0);
  try {
    const response = await fetch(`http://127.0.0.1:${server.address().port}/api/analysis/operations`);
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.deepEqual(body.operations.map(item => item.operation), Object.keys(OPERATION_REGISTRY));
    assert.equal(body.operations[1].executor_id, 'buffer_layer');
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});
