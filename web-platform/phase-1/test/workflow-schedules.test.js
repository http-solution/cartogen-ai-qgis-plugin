const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeWorkflowScheduleRequest, isAllowedScheduledOperation } = require('../server');

test('normalizes a persisted read-only workflow schedule', () => {
  const result = normalizeWorkflowScheduleRequest({
    name: 'Nightly layer review',
    interval_seconds: 3600,
    workflow: { operation: 'create_review_output', input: { include_layers: true } },
  });
  assert.equal(result.name, 'Nightly layer review');
  assert.equal(result.interval_seconds, 3600);
  assert.equal(result.workflow.operation, 'create_review_output');
  assert.ok(result.next_run instanceof Date);
});

test('accepts only the worker-compatible read-only operation', () => {
  assert.equal(isAllowedScheduledOperation('create_review_output'), true);
  for (const operation of ['buffer_layer', 'intersect_layers', 'edit_feature', 'import_dataset', 'delete_layer']) {
    assert.equal(isAllowedScheduledOperation(operation), false, operation);
  }
});

test('rejects unsafe, malformed, or too-fast schedules', () => {
  assert.throws(() => normalizeWorkflowScheduleRequest({ interval_seconds: 30, workflow: { operation: 'buffer_layer' } }), /read-only/);
  assert.throws(() => normalizeWorkflowScheduleRequest({ interval_seconds: 60, workflow: { operation: 'edit_feature' } }), /read-only/);
  assert.throws(() => normalizeWorkflowScheduleRequest({ interval_seconds: 60, workflow: { operation: 'import_dataset' } }), /read-only/);
  assert.throws(() => normalizeWorkflowScheduleRequest({ interval_seconds: 30, workflow: { operation: 'create_review_output' } }), /at least/);
});
