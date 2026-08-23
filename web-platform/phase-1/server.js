const path = require('node:path');
const express = require('express');
const { Pool } = require('pg');

const PORT = Number(process.env.PORT || 4180);
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

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}

function buildExportSvg(features) {
  const coordinates = [];
  const collect = geometry => {
    if (!geometry) return;
    if (geometry.type === 'Point') coordinates.push(geometry.coordinates);
    else if (geometry.coordinates) geometry.coordinates.forEach(item => Array.isArray(item[0]) ? collect({ type: geometry.type, coordinates: item }) : coordinates.push(item));
  };
  features.forEach(feature => collect(feature.geometry));
  if (!coordinates.length) return '<svg viewBox="0 0 100 100" aria-label="No geometry available"><text x="50" y="50" text-anchor="middle" fill="#557174">No geometry available</text></svg>';
  const xs = coordinates.map(c => c[0]); const ys = coordinates.map(c => c[1]);
  const minX = Math.min(...xs); const maxX = Math.max(...xs); const minY = Math.min(...ys); const maxY = Math.max(...ys);
  const dx = maxX - minX || 1; const dy = maxY - minY || 1;
  const point = coordinate => [((coordinate[0] - minX) / dx) * 88 + 6, 100 - (((coordinate[1] - minY) / dy) * 88 + 6)];
  const shapes = [];
  const draw = geometry => {
    if (geometry.type === 'Point') { const [x, y] = point(geometry.coordinates); shapes.push(`<circle cx="${x}" cy="${y}" r="1.4"/>`); }
    else if (geometry.type === 'LineString') shapes.push(`<polyline points="${geometry.coordinates.map(c => point(c).join(',')).join(' ')}"/>`);
    else if (geometry.type === 'Polygon') geometry.coordinates.forEach(ring => shapes.push(`<path d="M ${ring.map(c => point(c).join(' L '))} Z"/>`));
    else if (geometry.coordinates) geometry.coordinates.forEach(item => draw({ type: geometry.type.replace('Multi', ''), coordinates: item }));
  };
  features.forEach(feature => draw(feature.geometry));
  return `<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Project geometry">${shapes.join('')}</svg>`;
}

function buildSituationReportHtml(project, layers, layout, features) {
  const title = layout.title || project.name;
  const author = layout.author || 'Cartogen AI Humanitarian Mapping';
  const reportVersion = layout.report_version || 'Phase 1 draft';
  const date = new Date().toISOString().slice(0, 10);
  const totalFeatures = features.length;
  const sourceRows = layers.map((layer, index) => `<tr><td>${index + 1}</td><td>${escapeHtml(layer.name)}</td><td>${escapeHtml(layer.source_resource || 'project layer')}</td><td>${layer.feature_count}</td></tr>`).join('');
  const provenanceRows = layers.map(layer => `<li>${escapeHtml(layer.name)}: ${layer.feature_count} stored features; source ${escapeHtml(layer.source_resource || 'not specified')}.</li>`).join('');
  const pages = [
    `<article class="page cover"><div class="brand">Cartogen AI · Humanitarian Mapping</div><div class="classification">DRAFT · REVIEW REQUIRED</div><h1>${escapeHtml(title)}</h1><p class="lead">Humanitarian service-coverage screening situation report</p><div class="hero-rule"></div><dl><dt>Prepared by</dt><dd>${escapeHtml(author)}</dd><dt>Project</dt><dd>${escapeHtml(project.name)}</dd><dt>Reference system</dt><dd>${escapeHtml(project.crs)}</dd><dt>Report version</dt><dd>${escapeHtml(reportVersion)}</dd><dt>Prepared</dt><dd>${date}</dd></dl><div class="warning">This report supports structured humanitarian review. It is not a needs assessment, targeting decision, or live security product.</div></article>`,
    `<article class="page"><h2>1. Executive summary</h2><p>This report presents a reviewable, public-data screening slice for humanitarian service coverage in ${escapeHtml(project.name)}. The result combines project layers stored in PostGIS with documented source and compatibility limitations.</p><div class="stat-grid"><div><b>${layers.length}</b><small>project layers</small></div><div><b>${totalFeatures}</b><small>features in export</small></div><div><b>${escapeHtml(project.crs)}</b><small>coordinate reference</small></div></div><h3>Review findings</h3><ul><li>Stored project geometry is available for visual and attribute review.</li><li>Derived layers are retained separately from source layers.</li><li>Source age and administrative compatibility require analyst confirmation.</li><li>Any operational use requires provenance and limitations to remain attached.</li></ul><h3>Recommended next action</h3><p>Confirm source vintages and administrative crosswalks with the responsible information-management team before using the screening output for prioritisation.</p></article>`,
    `<article class="page"><h2>2. Map and layer register</h2><div class="map-report">${buildExportSvg(features)}</div><h3>Layer register</h3><table><thead><tr><th>#</th><th>Layer</th><th>Source</th><th>Features</th></tr></thead><tbody>${sourceRows}</tbody></table></article>`,
    `<article class="page"><h2>3. Limitations and provenance appendix</h2><h3>Known limitations</h3><ul><li>Population reference year 2017 is not directly compatible with newer administrative boundaries without a validated crosswalk.</li><li>3W presence does not prove service quality, capacity, funding, outcomes, or absence of need.</li><li>Modelled accessibility is not live road-status or security information.</li><li>Public-data demonstration layers are not a substitute for controlled humanitarian datasets.</li></ul><h3>Provenance register</h3><ul>${provenanceRows}</ul><div class="warning">Retain source URL, resource date, retrieval date, licence, assumptions, and limitations with every distributed copy.</div></article>`
  ];
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(title)} — Situation Report</title><style>@page{size:${escapeHtml(layout.paper || 'A4')} ${escapeHtml(layout.orientation || 'portrait')};margin:12mm}*{box-sizing:border-box}body{font-family:Arial,sans-serif;color:#10232b;margin:0;background:#eef4f2}.page{background:#fff;min-height:calc(297mm - 24mm);padding:12mm;page-break-after:always;position:relative}.page:last-child{page-break-after:auto}.brand{color:#087f7a;font-weight:800;font-size:17px}.classification{float:right;color:#9d402f;font-size:9px;font-weight:800;border:1px solid #e5b7ac;padding:2mm;border-radius:4px}.cover{display:flex;flex-direction:column;justify-content:center}.cover h1{font-size:30px;max-width:170mm;margin:24mm 0 5mm;color:#102b33}.lead{font-size:16px;color:#627276}.hero-rule{height:4px;background:#087f7a;width:55mm;margin:12mm 0}.page h2{font-size:22px;color:#087f7a;border-bottom:2px solid #dce5e6;padding-bottom:4mm}.page h3{font-size:14px;color:#087f7a;margin-top:9mm}.page p,.page li{font-size:11px;line-height:1.55}.page dl{display:grid;grid-template-columns:42mm 1fr;gap:3mm;font-size:11px}.page dt{font-weight:800;color:#627276}.page dd{margin:0}.warning{background:#fff8e7;border:1px solid #e5c978;padding:4mm;margin-top:8mm;font-size:10px;line-height:1.45}.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:5mm;margin:8mm 0}.stat-grid div{border:1px solid #cddbd9;padding:6mm;text-align:center}.stat-grid b{display:block;font-size:22px;color:#087f7a}.stat-grid small{color:#627276}.map-report{height:120mm;border:1px solid #9db4b1;background:#e4eeea;position:relative;margin:7mm 0}.map-report:after{content:'N ↑';position:absolute;right:6mm;top:6mm;background:#fff;border:1px solid #c6d6d3;padding:2mm;font-weight:800}.map-report:before{content:'0 ─── 5 ─── 10 km';position:absolute;right:6mm;bottom:6mm;background:#ffffffe8;border:1px solid #c6d6d3;padding:2mm;font-size:8px}.map-report svg{width:100%;height:100%;display:block}.map-report circle{fill:#087f7a;stroke:#fff;stroke-width:.7}.map-report path{fill:#d96a5466;stroke:#b04c3b;stroke-width:.6}.map-report polyline{fill:none;stroke:#087f7a;stroke-width:.6}table{width:100%;border-collapse:collapse;font-size:10px}th,td{text-align:left;border-bottom:1px solid #dce5e6;padding:3mm}th{color:#627276;font-size:9px;text-transform:uppercase}.page:after{content:'Cartogen AI · '+counter(page);position:absolute;bottom:6mm;right:12mm;color:#879699;font-size:8px}</style></head><body>${pages.join('')}</body></html>`;
}

function buildServerExportHtml(project, layers, layout, features = []) {
  if (layout.report_type === 'situation_report') return buildSituationReportHtml(project, layers, layout, features);
  const title = layout.title || project.name;
  const paper = layout.paper || 'A4';
  const orientation = layout.orientation || 'landscape';
  const author = layout.author || 'Cartogen AI Humanitarian Mapping';
  const warnings = layout.include_warnings !== false;
  const sourceItems = layers.map(layer => `<li><b>${escapeHtml(layer.name)}</b> — ${escapeHtml(layer.source_resource || 'project layer')} — ${layer.feature_count} features</li>`).join('');
  const legendItems = layers.map((layer, index) => `<div><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${index % 2 ? '#dfa43b' : '#087f7a'}"></span> ${escapeHtml(layer.name)} <small>(${layer.feature_count})</small></div>`).join('');
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(title)} — Cartogen AI</title><style>@page{size:${escapeHtml(paper)} ${escapeHtml(orientation)};margin:12mm}body{font-family:Arial,sans-serif;color:#10232b;margin:0}.sheet{min-height:180mm;display:grid;grid-template-rows:auto 1fr auto;gap:7mm}.header{border-bottom:3px solid #087f7a;padding-bottom:4mm;display:flex;justify-content:space-between}.brand{font-weight:800;color:#087f7a;font-size:18px}.title{font-size:23px;font-weight:800;margin-top:2mm}.meta,.footer{font-size:9px;color:#627276}.body{display:grid;grid-template-columns:1fr 65mm;gap:6mm}.map{border:1px solid #9db4b1;background:#e4eeea;min-height:105mm;display:grid;place-items:center;color:#557174;position:relative}.map:after{content:'N ↑';position:absolute;right:7mm;top:7mm;background:#fff;border:1px solid #c6d6d3;border-radius:5px;padding:2mm;font-weight:800}.map:before{content:'0 ─── 5 ─── 10 km';position:absolute;right:7mm;bottom:7mm;background:#ffffffe8;border:1px solid #c6d6d3;border-radius:4px;padding:2mm;font-size:8px}.map svg{width:100%;height:100%;display:block}.map circle{fill:#087f7a;stroke:#fff;stroke-width:.7}.map path{fill:#d96a5466;stroke:#b04c3b;stroke-width:.6}.map polyline{fill:none;stroke:#087f7a;stroke-width:.6}.side{border:1px solid #cddbd9;padding:4mm;font-size:9px}.side h3{font-size:11px;color:#087f7a;margin:0 0 2mm}.side ul{padding-left:4mm}.warning{background:#fff8e7;border:1px solid #e5c978;padding:2mm;margin-top:3mm}.footer{border-top:1px solid #cddbd9;padding-top:3mm;display:flex;justify-content:space-between}</style></head><body><main class="sheet"><header class="header"><div><div class="brand">Cartogen AI · Humanitarian Mapping</div><div class="title">${escapeHtml(title)}</div><div class="meta">Prepared by ${escapeHtml(author)} · ${new Date().toISOString().slice(0,10)} · CRS ${escapeHtml(project.crs)}</div></div><div class="meta">${escapeHtml(project.sector)}<br>Phase 1 review export</div></header><div class="body"><section class="map">${buildExportSvg(features)}</section><aside class="side"><h3>Legend</h3>${legendItems}<h3>Layers and sources</h3><ul>${sourceItems}</ul>${warnings?'<h3>Data quality</h3><div class="warning">Review source freshness, administrative compatibility, and humanitarian limitations before publication.</div><div class="warning">This is a screening result, not a needs assessment or operational targeting decision.</div>':''}</aside></div><footer class="footer"><span>Source dates, licences, assumptions, and limitations accompany this output.</span><span>${escapeHtml(author)} · Cartogen AI</span></footer></main></body></html>`;
}

app.post('/api/projects/:projectId/exports', requireIdentity, async (req, res) => {
  const project = await pool.query('SELECT id, name, sector, crs FROM projects WHERE id = $1 AND organization_id = $2', [req.params.projectId, req.organizationId]);
  if (!project.rowCount) return res.status(404).json({ error: 'Project not found' });
  const layout = req.body.layout || {};
  const layers = await pool.query(
    `SELECT l.id, l.name, l.source_resource, COUNT(f.id)::int AS feature_count
       FROM project_layers l LEFT JOIN project_layer_features f ON f.layer_id = l.id
      WHERE l.project_id = $1 AND l.organization_id = $2 GROUP BY l.id ORDER BY l.created_at`,
    [req.params.projectId, req.organizationId],
  );
  const provenance = { created_by: req.organizationId, source_layer_count: layers.rowCount, generated_at: new Date().toISOString() };
  const result = await pool.query(
    `INSERT INTO export_jobs (project_id, organization_id, format, status, layout, provenance, completed_at)
     VALUES ($1,$2,'html','completed',$3,$4,now()) RETURNING id, format, status, created_at, completed_at`,
    [req.params.projectId, req.organizationId, layout, provenance],
  );
  res.status(201).json({ export: result.rows[0], download_url: `/api/exports/${result.rows[0].id}/html` });
});

app.get('/api/exports/:exportId/html', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT e.id, e.layout, p.id AS project_id, p.name, p.sector, p.crs
       FROM export_jobs e JOIN projects p ON p.id = e.project_id
      WHERE e.id = $1 AND e.organization_id = $2`,
    [req.params.exportId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).send('Export not found');
  const layers = await pool.query(
    `SELECT l.name, l.source_resource, COUNT(f.id)::int AS feature_count
       FROM project_layers l LEFT JOIN project_layer_features f ON f.layer_id = l.id
      WHERE l.project_id = $1 AND l.organization_id = $2 GROUP BY l.id ORDER BY l.created_at`,
    [result.rows[0].project_id, req.organizationId],
  );
  const features = await pool.query(
    `SELECT ST_AsGeoJSON(f.geometry)::json AS geometry, f.properties
       FROM project_layer_features f
      WHERE f.project_id = $1 AND f.organization_id = $2
      ORDER BY f.id LIMIT 2000`,
    [result.rows[0].project_id, req.organizationId],
  );
  res.type('html').send(buildServerExportHtml(result.rows[0], layers.rows, result.rows[0].layout, features.rows));
});

app.get('/api/exports/:exportId/pdf', requireIdentity, async (req, res) => {
  try {
    const playwright = require('playwright');
    const result = await pool.query(
      `SELECT e.id, e.layout, p.id AS project_id, p.name, p.sector, p.crs
         FROM export_jobs e JOIN projects p ON p.id = e.project_id
        WHERE e.id = $1 AND e.organization_id = $2`,
      [req.params.exportId, req.organizationId],
    );
    if (!result.rowCount) return res.status(404).send('Export not found');
    const layers = await pool.query(
      `SELECT l.name, l.source_resource, COUNT(f.id)::int AS feature_count
         FROM project_layers l LEFT JOIN project_layer_features f ON f.layer_id = l.id
        WHERE l.project_id = $1 AND l.organization_id = $2 GROUP BY l.id ORDER BY l.created_at`,
      [result.rows[0].project_id, req.organizationId],
    );
    const features = await pool.query(
      `SELECT ST_AsGeoJSON(f.geometry)::json AS geometry, f.properties
         FROM project_layer_features f WHERE f.project_id = $1 AND f.organization_id = $2 ORDER BY f.id LIMIT 2000`,
      [result.rows[0].project_id, req.organizationId],
    );
    const html = buildServerExportHtml(result.rows[0], layers.rows, result.rows[0].layout, features.rows);
    const browser = await playwright.chromium.launch({ executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: 'load' });
    const pdf = await page.pdf({ format: result.rows[0].layout.paper || 'A4', landscape: (result.rows[0].layout.orientation || 'landscape') === 'landscape', printBackground: true, margin: { top: '12mm', right: '12mm', bottom: '12mm', left: '12mm' } });
    await browser.close();
    res.type('application/pdf').set('Content-Disposition', `attachment; filename="cartogen-${result.rows[0].id}.pdf"`).send(pdf);
  } catch (error) {
    res.status(503).json({ error: 'PDF renderer unavailable', detail: error.message });
  }
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
