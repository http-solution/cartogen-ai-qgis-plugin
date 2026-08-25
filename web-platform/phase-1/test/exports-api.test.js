const test = require('node:test');
const assert = require('node:assert/strict');
const { app, pool } = require('../server');

async function withServer(fn) {
  const server = app.listen(0);
  try {
    await new Promise(resolve => server.once('listening', resolve));
    return await fn(`http://127.0.0.1:${server.address().port}`);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

test('export history is returned only for the requested organization project', async () => {
  const originalQuery = pool.query;
  let queryText = '';
  let queryParams;
  pool.query = async (text, params) => {
    queryText = text;
    queryParams = params;
    return { rows: [{ id: 'export-1', format: 'html', status: 'completed', title: 'Coverage', report_type: 'situation_report', report_version: 'v1', created_at: '2026-08-25T00:00:00Z', completed_at: '2026-08-25T00:01:00Z' }], rowCount: 1 };
  };
  try {
    await withServer(async baseUrl => {
      const response = await fetch(`${baseUrl}/api/projects/project-1/exports`, { headers: { 'x-demo-organization': 'org-a' } });
      assert.equal(response.status, 200);
      assert.deepEqual(await response.json(), { exports: [{ id: 'export-1', format: 'html', status: 'completed', title: 'Coverage', report_type: 'situation_report', report_version: 'v1', created_at: '2026-08-25T00:00:00Z', completed_at: '2026-08-25T00:01:00Z' }] });
    });
  } finally {
    pool.query = originalQuery;
  }
  assert.deepEqual(queryParams, ['project-1', 'org-a']);
  assert.match(queryText, /JOIN projects p ON p\.id = e\.project_id/);
  assert.match(queryText, /e\.organization_id = \$2 AND p\.organization_id = \$2/);
});

test('HTML and PDF export reads are organization-scoped', async () => {
  const originalQuery = pool.query;
  const queries = [];
  pool.query = async (text, params) => {
    queries.push({ text, params });
    return { rows: [], rowCount: 0 };
  };
  try {
    await withServer(async baseUrl => {
      for (const format of ['html', 'pdf']) {
        const response = await fetch(`${baseUrl}/api/exports/export-foreign/${format}`, { headers: { 'x-demo-organization': 'org-a' } });
        assert.equal(response.status, 404);
        assert.equal(await response.text(), 'Export not found');
      }
    });
  } finally {
    pool.query = originalQuery;
  }
  assert.equal(queries.length, 2);
  for (const query of queries) {
    assert.deepEqual(query.params, ['export-foreign', 'org-a']);
    assert.match(query.text, /e\.organization_id = \$2 AND p\.organization_id = \$2/);
  }
});
