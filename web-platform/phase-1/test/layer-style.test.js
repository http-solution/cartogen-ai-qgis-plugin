const test = require('node:test');
const assert = require('node:assert/strict');
const { app, pool, normalizeLayerStyle, buildServerExportHtml } = require('../server');

async function withServer(fn) {
  const server = app.listen(0);
  try { await new Promise(resolve => server.once('listening', resolve)); return await fn(`http://127.0.0.1:${server.address().port}`); }
  finally { await new Promise(resolve => server.close(resolve)); }
}

test('normalizeLayerStyle validates and normalizes persisted layer style fields', () => {
  assert.deepEqual(normalizeLayerStyle({ preset: 'risk', color: '#12AbEf', fill_opacity: 42, line_weight: 3, classification: 'INTERNAL', legend_label: 'Priority' }), {
    preset: 'risk', color: '#12abef', fill_opacity: 42, line_weight: 3, classification: 'INTERNAL', legend_label: 'Priority',
  });
  assert.throws(() => normalizeLayerStyle({ color: 'red' }), /color/);
  assert.throws(() => normalizeLayerStyle({ fill_opacity: 101 }), /fill_opacity/);
  assert.throws(() => normalizeLayerStyle({ line_weight: 0 }), /line_weight/);
});

test('layer style GET and PUT are organization/project scoped', async () => {
  const originalQuery = pool.query;
  const calls = [];
  pool.query = async (text, params) => {
    calls.push({ text, params });
    if (/SELECT l\.id, l\.project_id, l\.style_preset/.test(text)) return { rowCount: 1, rows: [{ id: 'layer-1', project_id: 'project-1', style_preset: 'coverage', style_color: '#d96a54', style_fill_opacity: 55, style_line_weight: 2, style_classification: 'DRAFT', style_legend_label: 'Coverage' }] };
    if (/UPDATE project_layers/.test(text)) return { rowCount: 1, rows: [{ id: 'layer-1', project_id: 'project-1', style_preset: 'risk', style_color: '#123456', style_fill_opacity: 40, style_line_weight: 4, style_classification: 'INTERNAL', style_legend_label: 'Risk' }] };
    throw new Error(`unexpected query: ${text}`);
  };
  try { await withServer(async base => {
    const get = await fetch(`${base}/api/projects/project-1/layers/layer-1/style`, { headers: { 'x-demo-organization': 'org-a' } });
    assert.equal(get.status, 200); assert.equal((await get.json()).style.legend_label, 'Coverage');
    const put = await fetch(`${base}/api/projects/project-1/layers/layer-1/style`, { method: 'PUT', headers: { 'content-type': 'application/json', 'x-demo-organization': 'org-a' }, body: JSON.stringify({ preset: 'risk', color: '#123456', fill_opacity: 40, line_weight: 4, classification: 'INTERNAL', legend_label: 'Risk' }) });
    assert.equal(put.status, 200); assert.equal((await put.json()).style.preset, 'risk');
  }); } finally { pool.query = originalQuery; }
  assert.deepEqual(calls[0].params, ['layer-1', 'project-1', 'org-a']);
  assert.deepEqual(calls[1].params, ['risk', '#123456', 40, 4, 'INTERNAL', 'Risk', 'layer-1', 'project-1', 'org-a']);
});

test('export HTML uses persisted layer labels and colors', () => {
  const html = buildServerExportHtml({ name: 'P', sector: 'S', crs: 'EPSG:4326' }, [{ name: 'Hospitals', source_resource: 'x', feature_count: 1, style_preset: 'risk', style_color: '#123456', style_fill_opacity: 35, style_line_weight: 4, style_classification: 'INTERNAL', style_legend_label: 'Priority hospitals' }], {}, [{ layer_id: 'layer-1', geometry: { type: 'Point', coordinates: [1, 2] } }]);
  assert.match(html, /Priority hospitals/); assert.match(html, /#123456/); assert.match(html, /INTERNAL/);
});
