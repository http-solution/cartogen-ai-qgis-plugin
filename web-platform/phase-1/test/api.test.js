const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeFeatureCollection, normalizeDocumentContext, normalizeIntersectionInput, isSupportedAnalysisOperation, normalizeExportStyle, resolvePlannerModel, plannerProviderStatus, buildTaskPlan, parsePlannerResponse } = require('../server');

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

test('normalizes bounded text document context', () => {
  const result = normalizeDocumentContext({ name: 'situation.txt', mime_type: 'text/plain', text: 'Pakistan WASH coverage review' });
  assert.equal(result.name, 'situation.txt');
  assert.equal(result.mime_type, 'text/plain');
  assert.equal(result.text, 'Pakistan WASH coverage review');
});

test('rejects empty or oversized document context', () => {
  assert.throws(() => normalizeDocumentContext({ name: 'empty.txt', mime_type: 'text/plain', text: '   ' }), /text is required/);
  assert.throws(() => normalizeDocumentContext({ name: 'large.txt', mime_type: 'text/plain', text: 'x'.repeat(200001) }), /200000/);
});

test('rejects unsupported document context format', () => {
  assert.throws(() => normalizeDocumentContext({ name: 'photo.png', mime_type: 'image/png', text: 'not an image' }), /Unsupported/);
});

test('validates intersection layer inputs', () => {
  assert.deepEqual(normalizeIntersectionInput({ source_layer_id: 'a', overlay_layer_id: 'b' }), { source_layer_id: 'a', overlay_layer_id: 'b' });
  assert.throws(() => normalizeIntersectionInput({ source_layer_id: 'a', overlay_layer_id: 'a' }), /different/);
  assert.throws(() => normalizeIntersectionInput({ source_layer_id: 'a' }), /overlay_layer_id/);
});

test('validates supported analysis operations', () => {
  assert.equal(isSupportedAnalysisOperation('create_review_output'), true);
  assert.equal(isSupportedAnalysisOperation('buffer_layer'), true);
  assert.equal(isSupportedAnalysisOperation('intersect_layers'), true);
  assert.equal(isSupportedAnalysisOperation('unsupported_operation'), false);
});

test('validates export style presets and opacity', () => {
  assert.deepEqual(normalizeExportStyle({ style_preset: 'facilities', opacity: 72 }), { style_preset: 'facilities', opacity: 72 });
  assert.throws(() => normalizeExportStyle({ style_preset: 'unknown' }), /style_preset/);
  assert.throws(() => normalizeExportStyle({ style_preset: 'coverage', opacity: 101 }), /opacity/);
});

test('resolves central planner provider aliases', () => {
  assert.equal(resolvePlannerModel('gemini'), 'gemini-default');
  assert.equal(resolvePlannerModel('openai'), 'gpt-default');
  assert.equal(resolvePlannerModel('claude'), 'claude-default');
  assert.equal(resolvePlannerModel('openrouter'), 'openrouter-default');
  assert.equal(resolvePlannerModel('local'), 'local-default');
  assert.equal(resolvePlannerModel('unknown'), 'gpt-default');
  assert.equal(resolvePlannerModel('openai', 'custom-model'), 'custom-model');
});

test('reports non-secret provider status', () => {
  const result = plannerProviderStatus();
  assert.equal(result.providers.length, 5);
  assert.deepEqual(result.providers.map(item => item.provider), ['gemini', 'openai', 'claude', 'openrouter', 'local']);
  assert.ok(result.providers.every(item => typeof item.credential_configured === 'boolean'));
  assert.ok(!JSON.stringify(result).match(/sk-[A-Za-z0-9]/));
});

test('builds a humanitarian review plan from narrative and document context', () => {
  const plan = buildTaskPlan({
    prompt: 'Review WASH coverage gaps and partner presence',
    documentText: 'Situation report for Pakistan',
    sourceNames: ['3w.csv', 'hno.xlsx'],
  });
  assert.equal(plan.sector, 'humanitarian');
  assert.equal(plan.mode, 'deterministic-planning-adapter');
  assert.ok(plan.steps.some(step => step.tool === 'extract_document_context'));
  assert.ok(plan.steps.some(step => step.tool === 'screen_service_coverage'));
  assert.deepEqual(plan.source_names, ['3w.csv', 'hno.xlsx']);
});

test('requires content before creating a plan', () => {
  assert.throws(() => buildTaskPlan({}), /required/);
});

test('parses a valid gateway JSON plan', () => {
  const content = ['```json', JSON.stringify({ objective: 'Review coverage', steps: [{ id: 1, tool: 'validate_sources', title: 'Validate sources', requires_confirmation: false }] }), '```'].join('\n');
  const plan = parsePlannerResponse({ choices: [{ message: { content } }] });
  assert.equal(plan.mode, 'live-gateway');
  assert.equal(plan.steps[0].tool, 'validate_sources');
});

test('rejects malformed gateway plan responses', () => {
  assert.throws(() => parsePlannerResponse({ choices: [{ message: { content: '{"wrong":true}' } }] }), /schema/);
});
