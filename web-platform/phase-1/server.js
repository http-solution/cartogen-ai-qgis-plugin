const path = require('node:path');
const express = require('express');
const { Pool } = require('pg');

const PORT = Number(process.env.PORT || 4179);
const DATABASE_URL = process.env.DATABASE_URL || 'postgresql://cartogen:phase1_local_only_change_me@127.0.0.1:55432/cartogen_phase1';
const NODE_ENV = process.env.NODE_ENV || 'development';
const app = express();
const pool = new Pool({ connectionString: DATABASE_URL, max: 5 });

app.disable('x-powered-by');
app.use(express.json({ limit: '2mb' }));
app.use(express.static(__dirname));

function identity(req) {
  return req.header('x-demo-organization') || (NODE_ENV === 'development' ? 'demo-humanitarian-lab' : null);
}

function requireIdentity(req, res, next) {
  const organizationId = identity(req);
  if (!organizationId) return res.status(401).json({ error: 'Authentication required' });
  req.organizationId = organizationId;
  next();
}

function buildTaskPlan({ prompt = '', documentText = '', sourceNames = [] }) {
  const text = `${prompt}\n${documentText}`.trim();
  if (!text) throw new Error('A narrative, document text, or data context is required');
  const lower = text.toLowerCase();
  const sector = lower.includes('wash') || lower.includes('humanitarian') || lower.includes('3w') ? 'humanitarian' : 'general';
  const steps = [
    { id: 1, tool: 'validate_sources', title: 'Validate sources and assumptions', requires_confirmation: false },
  ];
  if (lower.includes('document') || documentText) steps.push({ id: steps.length + 1, tool: 'extract_document_context', title: 'Extract locations, dates, indicators, and data limitations', requires_confirmation: false });
  if (lower.includes('coverage') || lower.includes('gap') || lower.includes('presence') || lower.includes('access')) steps.push({ id: steps.length + 1, tool: 'screen_service_coverage', title: 'Compare reported presence with service/access context', requires_confirmation: true });
  else steps.push({ id: steps.length + 1, tool: 'inspect_project_layers', title: 'Inspect relevant project layers and attributes', requires_confirmation: false });
  steps.push({ id: steps.length + 1, tool: 'create_review_output', title: 'Create a review layer, table, and provenance summary', requires_confirmation: true });
  return {
    planner: 'cartogen-local-planner-v1',
    mode: 'deterministic-planning-adapter',
    sector,
    objective: prompt || 'Analyze the supplied document and project data',
    source_names: sourceNames,
    steps,
    warnings: [
      'This is a reviewable plan, not an operational decision.',
      'Source freshness, compatibility, and humanitarian data-responsibility checks are required before publication.',
    ],
    expected_outputs: ['review map/layer', 'summary table', 'provenance and limitations'],
  };
}

function parsePlannerResponse(payload) {
  const content = payload?.choices?.[0]?.message?.content;
  if (typeof content !== 'string') throw new Error('Gateway response did not include assistant content');
  const cleaned = content.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '').trim();
  const plan = JSON.parse(cleaned);
  if (!plan || !Array.isArray(plan.steps) || !plan.objective) throw new Error('Gateway plan did not match the required schema');
  return { ...plan, planner: 'cartogen-gateway', mode: 'live-gateway' };
}

async function buildLiveGatewayPlan(context) {
  const gatewayUrl = process.env.CARTOGEN_AI_GATEWAY_URL || 'http://127.0.0.1:4001/v1/chat/completions';
  const gatewayKey = process.env.CARTOGEN_AI_GATEWAY_KEY;
  const model = process.env.CARTOGEN_AI_PLANNER_MODEL || 'gpt-default';
  if (!gatewayKey) throw new Error('CARTOGEN_AI_GATEWAY_KEY is not configured');
  const instruction = [
    'You are Cartogen AI, a humanitarian GIS planning assistant.',
    'Return JSON only with keys: objective, sector, steps, warnings, expected_outputs.',
    'Each step must contain id, tool, title, and requires_confirmation.',
    'Do not claim that an analysis was executed. Create a reviewable plan only.',
    `User request: ${context.prompt || ''}`,
    `Document text: ${context.documentText || ''}`,
    `Source names: ${(context.sourceNames || []).join(', ')}`,
  ].join('\n');
  const response = await fetch(gatewayUrl, {
    method: 'POST',
    headers: { Authorization: `Bearer ${gatewayKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, messages: [{ role: 'user', content: instruction }], temperature: 0, max_tokens: 1200 }),
  });
  if (!response.ok) throw new Error(`Gateway planning failed with HTTP ${response.status}`);
  return parsePlannerResponse(await response.json());
}

async function createTaskPlan(context) {
  if ((process.env.CARTOGEN_AI_PLANNER_MODE || 'deterministic') === 'live') {
    try { return await buildLiveGatewayPlan(context); }
    catch (error) { return { ...buildTaskPlan(context), gateway_fallback: error.message }; }
  }
  return buildTaskPlan(context);
}

function normalizeFeatureCollection(payload) {
  if (!payload || payload.type !== 'FeatureCollection' || !Array.isArray(payload.features)) {
    throw new Error('Expected a GeoJSON FeatureCollection');
  }
  if (payload.features.length > 1000) throw new Error('FeatureCollection exceeds the Phase 1 limit of 1000 features');
  return payload.features.map((feature, index) => {
    if (!feature || feature.type !== 'Feature' || !feature.geometry) throw new Error(`Feature ${index + 1} has no valid geometry`);
    return { geometry: feature.geometry, properties: feature.properties || {} };
  });
}

app.post('/api/ai/plan', requireIdentity, async (req, res) => {
  try {
    const plan = await createTaskPlan({ prompt: req.body.prompt, documentText: req.body.document_text, sourceNames: req.body.source_names || [] });
    res.json({ plan });
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

app.get('/api/projects/:projectId/tasks', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT id, title, description, status, plan, provenance, created_at, updated_at
       FROM workspace_tasks WHERE project_id = $1 AND organization_id = $2 ORDER BY created_at DESC`,
    [req.params.projectId, req.organizationId],
  );
  res.json({ tasks: result.rows });
});

app.post('/api/projects/:projectId/tasks', requireIdentity, async (req, res) => {
  const project = await pool.query('SELECT id FROM projects WHERE id = $1 AND organization_id = $2', [req.params.projectId, req.organizationId]);
  if (!project.rowCount) return res.status(404).json({ error: 'Project not found' });
  let plan;
  try { plan = req.body.plan || await createTaskPlan({ prompt: req.body.prompt, documentText: req.body.document_text, sourceNames: req.body.source_names || [] }); }
  catch (error) { return res.status(400).json({ error: error.message }); }
  const approved = req.body.approved === true;
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const task = await client.query(
      `INSERT INTO workspace_tasks (project_id, organization_id, title, description, status, plan, provenance)
       VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id, title, status, plan, created_at`,
      [req.params.projectId, req.organizationId, req.body.title || 'Cartogen AI humanitarian analysis', plan.objective || 'Reviewable analysis task', approved ? 'approved' : 'proposed', plan, { planner: plan.planner, mode: plan.mode }],
    );
    let job = null;
    if (approved) {
      const created = await client.query(
        `INSERT INTO analysis_jobs (project_id, organization_id, task_id, operation, status, input, provenance)
         VALUES ($1,$2,$3,$4,'queued',$5,$6) RETURNING id, operation, status, created_at`,
        [req.params.projectId, req.organizationId, task.rows[0].id, plan.steps.at(-1)?.tool || 'review_output', { plan }, { planner: plan.planner, mode: plan.mode }],
      );
      job = created.rows[0];
    }
    await client.query('COMMIT');
    res.status(201).json({ task: task.rows[0], job });
  } catch (error) {
    await client.query('ROLLBACK');
    res.status(400).json({ error: 'Task creation failed', detail: error.message });
  } finally { client.release(); }
});

async function executeReviewOutputJob(jobId, organizationId) {
  const jobResult = await pool.query(
    `SELECT id, project_id, task_id, operation, status, input, provenance
       FROM analysis_jobs WHERE id = $1 AND organization_id = $2`,
    [jobId, organizationId],
  );
  if (!jobResult.rowCount) throw new Error('Analysis job not found');
  const job = jobResult.rows[0];
  if (job.status !== 'queued') throw new Error(`Analysis job is already ${job.status}`);
  const layers = await pool.query(
    `SELECT l.id, l.name, l.source_resource, l.source_modified_at, l.licence,
            COUNT(f.id)::int AS feature_count, ST_AsGeoJSON(ST_Extent(f.geometry)) AS extent
       FROM project_layers l LEFT JOIN project_layer_features f ON f.layer_id = l.id
      WHERE l.project_id = $1 AND l.organization_id = $2 GROUP BY l.id ORDER BY l.created_at`,
    [job.project_id, organizationId],
  );
  const output = {
    type: 'humanitarian_review_summary',
    feature_layers: layers.rows,
    totals: { layers: layers.rowCount, features: layers.rows.reduce((sum, layer) => sum + layer.feature_count, 0) },
    limitations: [
      'This Phase 1 result summarizes stored project data; it is not a needs assessment.',
      'Source freshness and administrative compatibility must be reviewed before publication.',
    ],
  };
  const updated = await pool.query(
    `UPDATE analysis_jobs SET status = 'completed', output = $1, completed_at = now()
      WHERE id = $2 AND organization_id = $3
      RETURNING id, operation, status, output, completed_at`,
    [output, jobId, organizationId],
  );
  return updated.rows[0];
}

app.get('/api/analysis-jobs/:jobId', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT id, project_id, task_id, operation, status, input, output, provenance, created_at, completed_at
       FROM analysis_jobs WHERE id = $1 AND organization_id = $2`,
    [req.params.jobId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Analysis job not found' });
  res.json({ job: result.rows[0] });
});

app.post('/api/analysis-jobs/:jobId/run', requireIdentity, async (req, res) => {
  try {
    const operation = await pool.query('SELECT operation FROM analysis_jobs WHERE id = $1 AND organization_id = $2', [req.params.jobId, req.organizationId]);
    if (!operation.rowCount) return res.status(404).json({ error: 'Analysis job not found' });
    const job = operation.rows[0].operation === 'buffer_layer'
      ? await executeBufferJob(req.params.jobId, req.organizationId)
      : await executeReviewOutputJob(req.params.jobId, req.organizationId);
    res.json({ job });
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

async function executeBufferJob(jobId, organizationId) {
  const jobResult = await pool.query(
    `SELECT id, project_id, input, status FROM analysis_jobs WHERE id = $1 AND organization_id = $2`,
    [jobId, organizationId],
  );
  if (!jobResult.rowCount) throw new Error('Analysis job not found');
  const job = jobResult.rows[0];
  if (job.status !== 'queued') throw new Error(`Analysis job is already ${job.status}`);
  const sourceLayerId = job.input?.source_layer_id;
  const distanceMeters = Number(job.input?.distance_meters);
  if (!sourceLayerId) throw new Error('source_layer_id is required');
  if (!Number.isFinite(distanceMeters) || distanceMeters <= 0 || distanceMeters > 100000) throw new Error('distance_meters must be between 0 and 100000');
  const source = await pool.query(
    `SELECT id, project_id, name, source_resource, licence FROM project_layers
      WHERE id = $1 AND project_id = $2 AND organization_id = $3`,
    [sourceLayerId, job.project_id, organizationId],
  );
  if (!source.rowCount) throw new Error('Source layer not found');
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const resultLayer = await client.query(
      `INSERT INTO project_layers (project_id, organization_id, name, source_resource, licence, metadata)
       VALUES ($1,$2,$3,$4,$5,$6) RETURNING id, name, created_at`,
      [job.project_id, organizationId, `${source.rows[0].name} — ${distanceMeters}m buffer`, `derived:buffer:${sourceLayerId}`, source.rows[0].licence, { operation: 'buffer_layer', source_layer_id: sourceLayerId, distance_meters: distanceMeters }],
    );
    const inserted = await client.query(
      `INSERT INTO project_layer_features (layer_id, project_id, organization_id, geometry, properties)
       SELECT $1, project_id, organization_id, ST_Buffer(geometry::geography, $2)::geometry, properties
         FROM project_layer_features
        WHERE layer_id = $3 AND organization_id = $4
       RETURNING id`,
      [resultLayer.rows[0].id, distanceMeters, sourceLayerId, organizationId],
    );
    const output = { type: 'derived_geometry_layer', operation: 'buffer_layer', result_layer_id: resultLayer.rows[0].id, source_layer_id: sourceLayerId, distance_meters: distanceMeters, feature_count: inserted.rowCount, limitations: ['Buffer distance is calculated in metres using a WGS84 geography cast.', 'Derived output requires human review before operational use.'] };
    const updated = await client.query(
      `UPDATE analysis_jobs SET status = 'completed', output = $1, completed_at = now() WHERE id = $2 AND organization_id = $3 RETURNING id, operation, status, output, completed_at`,
      [output, jobId, organizationId],
    );
    await client.query('COMMIT');
    return updated.rows[0];
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally { client.release(); }
}

app.post('/api/projects/:projectId/analysis-jobs', requireIdentity, async (req, res) => {
  const project = await pool.query('SELECT id FROM projects WHERE id = $1 AND organization_id = $2', [req.params.projectId, req.organizationId]);
  if (!project.rowCount) return res.status(404).json({ error: 'Project not found' });
  if (req.body.operation !== 'buffer_layer') return res.status(400).json({ error: 'Unsupported operation' });
  try {
    const distance = Number(req.body.distance_meters);
    if (!req.body.source_layer_id || !Number.isFinite(distance) || distance <= 0 || distance > 100000) throw new Error('source_layer_id and distance_meters (1–100000) are required');
    const result = await pool.query(
      `INSERT INTO analysis_jobs (project_id, organization_id, operation, status, input, provenance)
       VALUES ($1,$2,$3,'queued',$4,$5) RETURNING id, operation, status, input, created_at`,
      [req.params.projectId, req.organizationId, 'buffer_layer', { source_layer_id: req.body.source_layer_id, distance_meters: distance }, { source: 'user-request', phase: '1' }],
    );
    res.status(201).json({ job: result.rows[0] });
  } catch (error) { res.status(400).json({ error: error.message }); }
});

app.get('/api/health', async (_req, res) => {
  try {
    const result = await pool.query('SELECT PostGIS_Version() AS postgis_version');
    res.json({ ok: true, service: 'cartogen-phase1-api', postgis: result.rows[0].postgis_version });
  } catch (error) {
    res.status(503).json({ ok: false, error: 'Database unavailable' });
  }
});

app.get('/api/projects', requireIdentity, async (req, res) => {
  const result = await pool.query(
    'SELECT id, name, sector, crs, status, metadata, created_at, updated_at FROM projects WHERE organization_id = $1 ORDER BY updated_at DESC',
    [req.organizationId],
  );
  res.json({ projects: result.rows });
});

app.get('/api/projects/:projectId', requireIdentity, async (req, res) => {
  const result = await pool.query(
    'SELECT id, name, sector, crs, status, metadata, created_at, updated_at FROM projects WHERE id = $1 AND organization_id = $2',
    [req.params.projectId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Project not found' });
  res.json({ project: result.rows[0] });
});

app.get('/api/projects/:projectId/layers', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT l.id, l.name, l.source_url, l.source_resource, l.source_modified_at, l.source_retrieved_at,
            l.licence, l.metadata, COUNT(f.id)::int AS feature_count,
            ST_AsGeoJSON(ST_Extent(f.geometry)) AS extent
       FROM project_layers l
       LEFT JOIN project_layer_features f ON f.layer_id = l.id
      WHERE l.project_id = $1 AND l.organization_id = $2
      GROUP BY l.id
      ORDER BY l.created_at`,
    [req.params.projectId, req.organizationId],
  );
  res.json({ layers: result.rows });
});

app.get('/api/layers/:layerId/geojson', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT ST_AsGeoJSON(f.geometry)::json AS geometry, f.properties
       FROM project_layer_features f
       JOIN project_layers l ON l.id = f.layer_id
      WHERE f.layer_id = $1 AND f.organization_id = $2 AND l.organization_id = $2
      ORDER BY f.id`,
    [req.params.layerId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Layer not found or empty' });
  res.json({ type: 'FeatureCollection', features: result.rows.map(row => ({ type: 'Feature', geometry: row.geometry, properties: row.properties })) });
});

app.post('/api/projects/:projectId/layers', requireIdentity, async (req, res) => {
  let features;
  try {
    features = normalizeFeatureCollection(req.body.geojson);
  } catch (error) {
    return res.status(400).json({ error: error.message });
  }
  const project = await pool.query('SELECT id FROM projects WHERE id = $1 AND organization_id = $2', [req.params.projectId, req.organizationId]);
  if (!project.rowCount) return res.status(404).json({ error: 'Project not found' });
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const layer = await client.query(
      `INSERT INTO project_layers
        (project_id, organization_id, name, source_url, source_resource, source_modified_at, licence, metadata)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
       RETURNING id, name, source_resource, source_retrieved_at`,
      [req.params.projectId, req.organizationId, req.body.name || 'Uploaded layer', req.body.source_url || null,
        req.body.source_resource || null, req.body.source_modified_at || null, req.body.licence || null, req.body.metadata || {}],
    );
    const layerId = layer.rows[0].id;
    for (const feature of features) {
      await client.query(
        `INSERT INTO project_layer_features (layer_id, project_id, organization_id, geometry, properties)
         VALUES ($1,$2,$3,ST_SetSRID(ST_GeomFromGeoJSON($4),4326),$5)`,
        [layerId, req.params.projectId, req.organizationId, JSON.stringify(feature.geometry), feature.properties],
      );
    }
    await client.query('COMMIT');
    res.status(201).json({ layer: layer.rows[0], feature_count: features.length });
  } catch (error) {
    await client.query('ROLLBACK');
    res.status(400).json({ error: 'Layer ingestion failed', detail: error.message });
  } finally {
    client.release();
  }
});

app.use((_req, res) => res.sendFile(path.join(__dirname, 'index.html')));

if (require.main === module) {
  app.listen(PORT, () => console.log(`Cartogen Phase 1 API listening on http://127.0.0.1:${PORT}`));
}

module.exports = { app, pool, normalizeFeatureCollection, buildTaskPlan, parsePlannerResponse, createTaskPlan, executeReviewOutputJob, executeBufferJob };
