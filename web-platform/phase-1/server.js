const path = require('node:path');
const crypto = require('node:crypto');
const express = require('express');
const { Pool } = require('pg');

const PORT = Number(process.env.PORT || 4180);
const DATABASE_URL = process.env.DATABASE_URL || 'postgresql://cartogen:phase1_local_only_change_me@127.0.0.1:55432/cartogen_phase1';
const NODE_ENV = process.env.NODE_ENV || 'development';
const PHASE1_IDENTITY_MODE = process.env.PHASE1_IDENTITY_MODE || 'demo';
const DIRECTUS_URL = process.env.DIRECTUS_URL || 'http://127.0.0.1:8055';
const DIRECTUS_COOKIE = 'cartogen_session';
const DIRECTUS_ORGANIZATION_ID = process.env.PHASE1_DIRECTUS_ORGANIZATION_ID || null;
const app = express();
const pool = new Pool({ connectionString: DATABASE_URL, max: 5 });

app.disable('x-powered-by');
app.use(express.json({ limit: '2mb' }));
app.use(express.static(__dirname));

function parseCookies(header = '') {
  return Object.fromEntries(header.split(';').map(part => { const index = part.indexOf('='); return index < 0 ? ['', ''] : [part.slice(0, index).trim(), decodeURIComponent(part.slice(index + 1).trim())]; }).filter(([key]) => key));
}

async function directusUser(req) {
  const token = parseCookies(req.headers.cookie)[DIRECTUS_COOKIE];
  if (!token) return null;
  const response = await fetch(`${DIRECTUS_URL}/users/me?fields=id`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) return null;
  const body = await response.json();
  if (!body?.data?.id) return null;
  return body.data;
}

async function resolveIdentity(req) {
  if (PHASE1_IDENTITY_MODE === 'directus') {
    if (!DIRECTUS_ORGANIZATION_ID) return null;
    const user = await directusUser(req);
    return user ? { organizationId: DIRECTUS_ORGANIZATION_ID, user } : null;
  }
  const organizationId = req.header('x-demo-organization') || (NODE_ENV === 'development' ? 'demo-humanitarian-lab' : null);
  return organizationId ? { organizationId, user: null } : null;
}

async function requireIdentity(req, res, next) {
  try {
    const resolved = await resolveIdentity(req);
    if (!resolved) return res.status(401).json({ error: 'Authentication required' });
    req.organizationId = resolved.organizationId;
    req.user = resolved.user;
    next();
  } catch (error) {
    res.status(401).json({ error: 'Authentication required' });
  }
}

const PLANNER_PROVIDER_MODELS = Object.freeze({
  gemini: 'gemini-default',
  google: 'gemini-default',
  openai: 'gpt-default',
  claude: 'claude-default',
  anthropic: 'claude-default',
  openrouter: 'openrouter-default',
  local: 'local-default',
  ollama: 'local-default',
});

function resolvePlannerModel(provider = process.env.CARTOGEN_AI_PROVIDER || 'gemini', explicitModel = process.env.CARTOGEN_AI_PLANNER_MODEL) {
  if (explicitModel) return explicitModel;
  const normalized = String(provider || 'gemini').trim().toLowerCase();
  return PLANNER_PROVIDER_MODELS[normalized] || PLANNER_PROVIDER_MODELS.gemini;
}

function plannerProviderStatus() {
  const selectedProvider = String(process.env.CARTOGEN_AI_PROVIDER || 'gemini').trim().toLowerCase();
  const credentials = {
    gemini: Boolean(process.env.GEMINI_API_KEY),
    google: Boolean(process.env.GEMINI_API_KEY),
    openai: Boolean(process.env.OPENAI_API_KEY),
    claude: Boolean(process.env.ANTHROPIC_API_KEY),
    anthropic: Boolean(process.env.ANTHROPIC_API_KEY),
    openrouter: Boolean(process.env.OPENROUTER_API_KEY),
    local: Boolean(process.env.OLLAMA_BASE_URL),
    ollama: Boolean(process.env.OLLAMA_BASE_URL),
  };
  const providers = [...new Set(Object.keys(PLANNER_PROVIDER_MODELS).map(name => name === 'google' ? 'gemini' : name === 'anthropic' ? 'claude' : name === 'ollama' ? 'local' : name))]
    .map(provider => ({ provider, model: PLANNER_PROVIDER_MODELS[provider], credential_configured: credentials[provider] || false }));
  return { selected_provider: selectedProvider, selected_model: resolvePlannerModel(), providers };
}

app.get('/api/ai/providers', (req, res) => {
  res.json(plannerProviderStatus());
});

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

const GATEWAY_SYSTEM_PROMPT = [
  'You are Cartogen AI, a humanitarian GIS planning assistant.',
  'Return JSON only with keys: objective, sector, steps, warnings, expected_outputs.',
  'Each step must contain id, tool, title, and requires_confirmation.',
  'Do not claim that an analysis was executed. Create a reviewable plan only.',
].join(' ');

function buildGatewayMessages(context) {
  const instruction = [
    `User request: ${context.prompt || ''}`,
    `Document text: ${context.documentText || ''}`,
    `Source names: ${(context.sourceNames || []).join(', ')}`,
  ].join('\\n');
  return [{ role: 'system', content: GATEWAY_SYSTEM_PROMPT }, { role: 'user', content: instruction }];
}

async function buildLiveGatewayPlan(context) {
  const gatewayUrl = process.env.CARTOGEN_AI_GATEWAY_URL || 'http://127.0.0.1:4001/v1/chat/completions';
  const gatewayKey = process.env.CARTOGEN_AI_GATEWAY_KEY;
  const model = resolvePlannerModel();
  if (!gatewayKey) throw new Error('CARTOGEN_AI_GATEWAY_KEY is not configured');
  const messages = buildGatewayMessages(context);
  const response = await fetch(gatewayUrl, {
    method: 'POST',
    headers: { Authorization: `Bearer ${gatewayKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, messages, temperature: 0, max_tokens: 1200 }),
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

function normalizeDatasetSearchInput({ q = '', limit = 20 } = {}) {
  const query = String(q || '').trim();
  const boundedLimit = Number(limit);
  if (!query) throw new Error('q is required');
  if (query.length > 200) throw new Error('q must not exceed 200 characters');
  if (!Number.isInteger(boundedLimit) || boundedLimit < 1 || boundedLimit > 100) throw new Error('limit must be between 1 and 100');
  return { query, limit: boundedLimit };
}

const HDX_IMPORT_MAX_BYTES = 5 * 1024 * 1024;
const HDX_IMPORT_MAX_FEATURES = 1000;
const HDX_ALLOWED_HOSTS = new Set(['data.humdata.org', 'www.humdata.org', 'hdx.humdata.org']);
const HDX_FETCH_HOSTS = new Set([...HDX_ALLOWED_HOSTS, 'production-raw-data-api.s3.amazonaws.com', 's3.amazonaws.com', 's3.us-east-1.amazonaws.com']);

function normalizeHdxImportRequest(body = {}) {
  const projectId = String(body.project_id || '').trim();
  const resourceUrl = String(body.resource_url || '').trim();
  if (!projectId) throw new Error('project_id is required');
  if (body.approved !== true) throw new Error('approved must be true before importing an HDX resource');
  let parsed;
  try { parsed = new URL(resourceUrl); } catch { throw new Error('resource_url must be a valid HTTPS HDX URL'); }
  if (parsed.protocol !== 'https:' || !HDX_FETCH_HOSTS.has(parsed.hostname.toLowerCase())) throw new Error('resource_url must point to an HTTPS HDX resource');
  const resourceFormat = String(body.resource_format || (parsed.pathname.toLowerCase().match(/\.(geojson|json|csv)$/)?.[1] || '')).trim().toLowerCase();
  if (!['geojson', 'json', 'csv'].includes(resourceFormat)) throw new Error('resource_format must be GeoJSON, JSON, or CSV');
  const isoDate = value => value == null || value === '' ? null : (Number.isNaN(Date.parse(String(value))) ? (() => { throw new Error('metadata dates must be valid ISO dates'); })() : new Date(String(value)).toISOString());
  return {
    project_id: projectId,
    resource_url: parsed.toString(),
    resource_format: resourceFormat,
    dataset_id: body.dataset_id ? String(body.dataset_id).slice(0, 255) : null,
    resource_id: body.resource_id ? String(body.resource_id).slice(0, 255) : null,
    provider: String(body.provider || 'HDX').trim().slice(0, 255) || 'HDX',
    licence: body.licence == null ? null : String(body.licence).slice(0, 255),
    metadata_created: isoDate(body.metadata_created),
    metadata_modified: isoDate(body.metadata_modified),
    name: String(body.name || body.resource_name || 'HDX imported layer').trim().slice(0, 255) || 'HDX imported layer',
    approved: true,
  };
}

function parseCsvRows(text) {
  const rows = [];
  let row = [], cell = '', quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (char === '"' && quoted && text[i + 1] === '"') { cell += '"'; i += 1; }
    else if (char === '"') quoted = !quoted;
    else if (char === ',' && !quoted) { row.push(cell); cell = ''; }
    else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && text[i + 1] === '\n') i += 1;
      row.push(cell); cell = ''; if (row.some(value => value.trim())) rows.push(row); row = [];
    } else cell += char;
  }
  if (quoted) throw new Error('Invalid CSV: unterminated quoted field');
  if (cell || row.length) { row.push(cell); if (row.some(value => value.trim())) rows.push(row); }
  return rows;
}

function normalizeCsvResource(text, filename = 'resource.csv') {
  if (typeof text !== 'string' || !text.trim()) throw new Error('CSV resource is empty');
  const rows = parseCsvRows(text);
  if (rows.length < 2) throw new Error('CSV resource must contain a header and at least one row');
  const headers = rows[0].map(value => value.trim());
  const findHeader = names => headers.findIndex(header => names.includes(header.toLowerCase().replace(/[^a-z0-9]/g, '')));
  const latIndex = findHeader(['lat', 'latitude', 'y']);
  const lonIndex = findHeader(['lon', 'lng', 'long', 'longitude', 'x']);
  if (latIndex < 0 || lonIndex < 0) throw new Error('CSV requires latitude and longitude columns');
  if (rows.length - 1 > HDX_IMPORT_MAX_FEATURES) throw new Error(`CSV exceeds the Phase 1 limit of ${HDX_IMPORT_MAX_FEATURES} features`);
  const features = rows.slice(1).map((values, rowIndex) => {
    const latitude = Number(values[latIndex]); const longitude = Number(values[lonIndex]);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) throw new Error(`CSV row ${rowIndex + 2} has invalid latitude/longitude`);
    const properties = Object.fromEntries(headers.map((header, index) => [header || `column_${index + 1}`, values[index] ?? '']).filter(([, value], index) => index !== latIndex && index !== lonIndex));
    return { geometry: { type: 'Point', coordinates: [longitude, latitude] }, properties };
  });
  return normalizeFeatureCollection({ type: 'FeatureCollection', features: features.map(feature => ({ type: 'Feature', ...feature })) });
}

async function downloadHdxResource(resourceUrl) {
  let url = new URL(resourceUrl);
  const originalUrl = url.toString();
  for (let redirect = 0; redirect <= 3; redirect += 1) {
    if (url.protocol !== 'https:' || !HDX_FETCH_HOSTS.has(url.hostname.toLowerCase())) throw new Error('HDX resource redirected outside an allowed HDX host');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    let response;
    try { response = await fetch(url, { redirect: 'manual', signal: controller.signal, headers: { Accept: 'application/geo+json, application/json, text/csv, */*' } }); }
    catch (error) { throw new Error(error.name === 'AbortError' ? 'HDX resource download timed out' : 'HDX resource download failed'); }
    finally { clearTimeout(timeout); }
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      const location = response.headers.get('location');
      if (!location || redirect === 3) throw new Error('HDX resource has too many redirects');
      url = new URL(location, url);
      continue;
    }
    if (!response.ok) throw new Error(`HDX resource download failed with HTTP ${response.status}`);
    const declaredLength = Number(response.headers.get('content-length'));
    if (Number.isFinite(declaredLength) && declaredLength > HDX_IMPORT_MAX_BYTES) throw new Error(`HDX resource exceeds the ${HDX_IMPORT_MAX_BYTES} byte limit`);
    const chunks = []; let total = 0;
    for await (const chunk of response.body) {
      total += chunk.length;
      if (total > HDX_IMPORT_MAX_BYTES) throw new Error(`HDX resource exceeds the ${HDX_IMPORT_MAX_BYTES} byte limit`);
      chunks.push(chunk);
    }
    return { buffer: Buffer.concat(chunks), text: Buffer.concat(chunks).toString('utf8'), url: url.toString(), original_url: originalUrl, contentType: response.headers.get('content-type') || '' };
  }
  throw new Error('HDX resource redirect failed');
}

function extractGeoJsonFromZip(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.readUInt32LE(0) !== 0x04034b50) throw new Error('HDX ZIP resource is invalid');
  let offset = 0;
  while (offset + 30 <= buffer.length && buffer.readUInt32LE(offset) === 0x04034b50) {
    const method = buffer.readUInt16LE(offset + 8);
    const compressedSize = buffer.readUInt32LE(offset + 18);
    const uncompressedSize = buffer.readUInt32LE(offset + 22);
    const nameLength = buffer.readUInt16LE(offset + 26);
    const extraLength = buffer.readUInt16LE(offset + 28);
    const name = buffer.subarray(offset + 30, offset + 30 + nameLength).toString('utf8');
    const dataStart = offset + 30 + nameLength + extraLength;
    const dataEnd = dataStart + compressedSize;
    if (dataEnd > buffer.length || uncompressedSize > HDX_IMPORT_MAX_BYTES) throw new Error('HDX ZIP entry exceeds the import limit');
    if (/\.geojson$|\.json$/i.test(name)) {
      let content;
      if (method === 0) content = buffer.subarray(dataStart, dataEnd);
      else if (method === 8) content = require('node:zlib').inflateRawSync(buffer.subarray(dataStart, dataEnd));
      else throw new Error(`Unsupported HDX ZIP compression method: ${method}`);
      return content.toString('utf8');
    }
    offset = dataEnd;
  }
  throw new Error('HDX ZIP did not contain a GeoJSON or JSON entry');
}

function parseDownloadedHdxResource(download, resourceFormat = '') {
  const isZip = download.contentType.toLowerCase().includes('zip') || download.buffer?.subarray(0, 4).equals(Buffer.from([0x50, 0x4b, 0x03, 0x04]));
  const sourceText = isZip ? extractGeoJsonFromZip(download.buffer) : download.text;
  const format = resourceFormat || (new URL(download.original_url || download.url).pathname.toLowerCase().endsWith('.csv') ? 'csv' : 'geojson');
  if (format === 'csv') return normalizeCsvResource(sourceText);
  let payload;
  try { payload = JSON.parse(sourceText); } catch { throw new Error('Invalid GeoJSON resource: response is not valid JSON'); }
  return normalizeFeatureCollection(payload);
}
function normalizeHdxSearchResponse(payload, { query, retrievedAt = new Date().toISOString() }) {
  const sourceResults = Array.isArray(payload?.result?.results) ? payload.result.results : [];
  const candidates = sourceResults.map(item => ({
    id: item.id || item.name || null,
    name: item.name || null,
    title: item.title || item.name || null,
    notes: typeof item.notes === 'string' ? item.notes.slice(0, 4000) : null,
    organization: item.organization?.name || null,
    metadata_created: item.metadata_created || null,
    metadata_modified: item.metadata_modified || null,
    license: item.license_title || item.license_id || null,
    tags: Array.isArray(item.tags) ? item.tags.map(tag => tag.display_name || tag.name).filter(Boolean).slice(0, 50) : [],
    resources: Array.isArray(item.resources) ? item.resources.slice(0, 100).map(resource => ({
      id: resource.id || null,
      name: resource.name || null,
      description: typeof resource.description === 'string' ? resource.description.slice(0, 2000) : null,
      format: resource.format || null,
      url: resource.url || null,
      last_modified: resource.last_modified || null,
      size: resource.size || null,
    })) : [],
  }));
  return {
    count: Number(payload?.result?.count || candidates.length),
    candidates,
    provenance: { source: 'HDX / data.humdata.org', query, retrieved_at: retrievedAt, api: 'CKAN package_search', import_performed: false },
  };
}

function validateApprovalPlan(plan) {
  if (!plan || typeof plan !== 'object' || Array.isArray(plan) || !String(plan.objective || '').trim() || !Array.isArray(plan.steps) || plan.steps.length === 0) {
    throw new Error('Agent run has no usable plan');
  }
  return plan;
}

async function approveAgentRun({ runId, organizationId }) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const runResult = await client.query(
      `SELECT id, organization_id, project_id, status, prompt, context, provider, model, plan, rationale,
              created_at, updated_at, started_at, completed_at, error
         FROM agent_runs
        WHERE id = $1 AND organization_id = $2
        FOR UPDATE`,
      [runId, organizationId],
    );
    if (!runResult.rowCount) {
      const error = new Error('Agent run not found');
      error.statusCode = 404;
      throw error;
    }
    const run = runResult.rows[0];
    if (!run.project_id) {
      const error = new Error('Agent run is not associated with a project');
      error.statusCode = 404;
      throw error;
    }
    const project = await client.query(
      'SELECT id FROM projects WHERE id = $1 AND organization_id = $2',
      [run.project_id, organizationId],
    );
    if (!project.rowCount) {
      const error = new Error('Project not found');
      error.statusCode = 404;
      throw error;
    }
    if (run.status !== 'completed') {
      const error = new Error(`Only completed agent runs can be approved; current status is ${run.status}`);
      error.statusCode = 409;
      throw error;
    }
    const plan = validateApprovalPlan(run.plan);
    const existing = await client.query(
      `SELECT id FROM workspace_tasks
        WHERE organization_id = $1 AND project_id = $2 AND provenance->>'run_id' = $3
        LIMIT 1`,
      [organizationId, run.project_id, String(run.id)],
    );
    if (existing.rowCount) {
      const error = new Error('Agent run has already been approved');
      error.statusCode = 409;
      throw error;
    }

    const taskResult = await client.query(
      `INSERT INTO workspace_tasks (project_id, organization_id, title, description, status, plan, provenance)
       VALUES ($1,$2,$3,$4,'approved',$5,$6)
       RETURNING id, project_id, organization_id, title, description, status, plan, provenance, created_at, updated_at`,
      [
        run.project_id,
        organizationId,
        String(plan.objective).slice(0, 500),
        String(plan.objective),
        plan,
        { source: 'ai-run-approval', run_id: String(run.id), planner: plan.planner || null, mode: plan.mode || null },
      ],
    );
    const task = taskResult.rows[0];
    const operation = String(plan.steps.at(-1)?.tool || 'create_review_output');
    const jobResult = await client.query(
      `INSERT INTO analysis_jobs (project_id, organization_id, task_id, operation, status, input, provenance)
       VALUES ($1,$2,$3,$4,'queued',$5,$6)
       RETURNING id, project_id, organization_id, task_id, operation, status, input, output, provenance, created_at, completed_at`,
      [run.project_id, organizationId, task.id, operation, { plan, run_id: String(run.id) }, { source: 'ai-run-approval', run_id: String(run.id), task_id: String(task.id) }],
    );
    const job = jobResult.rows[0];
    await client.query(
      `UPDATE agent_steps
          SET status = CASE WHEN status IN ('pending','running') THEN 'queued' ELSE status END,
              rationale = CASE WHEN (plan->>'requires_confirmation')::boolean IS TRUE
                THEN 'Human confirmation recorded; step is queued for execution.'
                ELSE rationale END,
              updated_at = now(), completed_at = NULL
        WHERE run_id = $1 AND organization_id = $2
          AND COALESCE((plan->>'requires_confirmation')::boolean, false) IS TRUE`,
      [run.id, organizationId],
    );
    await client.query('COMMIT');
    return { run, task, job };
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

async function persistAgentRun({ organizationId, projectId = null, context, plan }) {
  const provider = String(process.env.CARTOGEN_AI_PROVIDER || 'gemini').trim().toLowerCase();
  const model = resolvePlannerModel(provider);
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const run = await client.query(
      `INSERT INTO agent_runs (organization_id, project_id, status, prompt, context, provider, model, plan, rationale, started_at, completed_at)
       VALUES ($1,$2,'completed',$3,$4,$5,$6,$7,$8,now(),now())
       RETURNING id, organization_id, project_id, status, prompt, context, provider, model, plan, rationale, created_at, updated_at, started_at, completed_at, error`,
      [organizationId, projectId, String(context.prompt || '').slice(0, 20000), context, provider, model, plan, Array.isArray(plan.warnings) ? plan.warnings.join(' ') : null],
    );
    const steps = [];
    for (let index = 0; index < plan.steps.length; index += 1) {
      const source = plan.steps[index] || {};
      const result = await client.query(
        `INSERT INTO agent_steps (run_id, organization_id, project_id, step_index, status, title, tool, prompt, context, provider, model, plan, rationale, started_at, completed_at)
         VALUES ($1,$2,$3,$4,'pending',$5,$6,$7,$8,$9,$10,$11,$12,NULL,NULL)
         RETURNING id, run_id, project_id, step_index, status, title, tool, prompt, context, provider, model, plan, rationale, created_at, updated_at, started_at, completed_at, error`,
        [run.rows[0].id, organizationId, projectId, index + 1, String(source.title || `Step ${index + 1}`).slice(0, 500), String(source.tool || 'review').slice(0, 200), context.prompt || null, { ...context, step: source }, provider, model, source, source.requires_confirmation ? 'Human confirmation required before execution.' : 'Reviewable planning step.'],
      );
      steps.push(result.rows[0]);
    }
    await client.query('COMMIT');
    return { run: run.rows[0], steps };
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally { client.release(); }
}

function normalizeFeatureCollection(payload) {
  if (!payload || payload.type !== 'FeatureCollection' || !Array.isArray(payload.features)) {
    throw new Error('Expected a GeoJSON FeatureCollection');
  }
  if (payload.features.length > HDX_IMPORT_MAX_FEATURES) throw new Error(`FeatureCollection exceeds the Phase 1 limit of ${HDX_IMPORT_MAX_FEATURES} features`);
  const allowedGeometryTypes = new Set(['Point', 'MultiPoint', 'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon']);
  const validateCoordinates = coordinates => {
    if (!Array.isArray(coordinates) || coordinates.length === 0) throw new Error('Geometry has invalid coordinates');
    if (typeof coordinates[0] === 'number') {
      if (coordinates.length < 2 || !coordinates.slice(0, 2).every(Number.isFinite) || coordinates[0] < -180 || coordinates[0] > 180 || coordinates[1] < -90 || coordinates[1] > 90) throw new Error('Geometry has invalid coordinates');
      return;
    }
    coordinates.forEach(validateCoordinates);
  };
  return payload.features.map((feature, index) => {
    if (!feature || feature.type !== 'Feature' || !feature.geometry || !allowedGeometryTypes.has(feature.geometry.type)) throw new Error(`Feature ${index + 1} has no valid geometry`);
    validateCoordinates(feature.geometry.coordinates);
    if (feature.properties != null && (typeof feature.properties !== 'object' || Array.isArray(feature.properties))) throw new Error(`Feature ${index + 1} has invalid properties`);
    return { geometry: feature.geometry, properties: feature.properties || {} };
  });
}

const EDIT_PREVIEW_SECRET = process.env.CARTOGEN_EDIT_PREVIEW_SECRET || crypto.randomBytes(32);
const EDIT_PREVIEW_TTL_SECONDS = 15 * 60;

function stableJson(value) {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableJson(value[key])}`).join(',')}}`;
  return JSON.stringify(value);
}

function canonicalFeatureState({ geometry, properties }) {
  return stableJson({ geometry, properties: properties || {} });
}

function hashFeatureState(state) {
  return crypto.createHash('sha256').update(canonicalFeatureState(state), 'utf8').digest('hex');
}

function normalizeFeatureEditRequest(body = {}) {
  const mode = String(body.mode || 'preview').trim().toLowerCase();
  if (!['preview', 'apply'].includes(mode)) throw new Error('mode must be preview or apply');
  const hasProperties = Object.prototype.hasOwnProperty.call(body, 'properties');
  const hasGeometry = Object.prototype.hasOwnProperty.call(body, 'geometry');
  if (!hasProperties && !hasGeometry) throw new Error('properties or geometry is required');
  let properties;
  if (hasProperties) {
    if (!body.properties || typeof body.properties !== 'object' || Array.isArray(body.properties)) throw new Error('properties must be an object');
    try { if (JSON.stringify(body.properties).length > 200000) throw new Error('properties exceed the 200000 byte limit'); } catch (error) { throw new Error(error.message || 'properties must be valid JSON'); }
    properties = body.properties;
  }
  let geometry;
  if (hasGeometry) {
    try { geometry = normalizeFeatureCollection({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: body.geometry, properties: {} }] })[0].geometry; }
    catch (error) { throw new Error(`geometry is invalid: ${error.message}`); }
  }
  if (mode === 'apply' && body.approved !== true) throw new Error('approved must be true before applying a feature edit');
  const beforeHash = body.before_hash == null ? null : String(body.before_hash).trim();
  if (beforeHash && !/^[a-f0-9]{64}$/i.test(beforeHash)) throw new Error('before_hash must be a SHA-256 hash');
  return { mode, approved: body.approved === true, properties, geometry, before_hash: beforeHash, preview_token: body.preview_token ? String(body.preview_token) : null };
}

function createEditPreviewToken({ layerId, featureId, beforeHash, afterHash }) {
  const payload = Buffer.from(JSON.stringify({ layerId: String(layerId), featureId: String(featureId), beforeHash, afterHash, exp: Math.floor(Date.now() / 1000) + EDIT_PREVIEW_TTL_SECONDS })).toString('base64url');
  const signature = crypto.createHmac('sha256', EDIT_PREVIEW_SECRET).update(payload).digest('base64url');
  return `${payload}.${signature}`;
}

function verifyEditPreviewToken(token) {
  if (typeof token !== 'string') return null;
  const parts = token.split('.');
  if (parts.length !== 2) return null;
  const expected = crypto.createHmac('sha256', EDIT_PREVIEW_SECRET).update(parts[0]).digest();
  let actual;
  try { actual = Buffer.from(parts[1], 'base64url'); } catch { return null; }
  if (actual.length !== expected.length || !crypto.timingSafeEqual(actual, expected)) return null;
  try {
    const payload = JSON.parse(Buffer.from(parts[0], 'base64url').toString('utf8'));
    if (!payload || payload.exp < Math.floor(Date.now() / 1000)) return null;
    return { layerId: String(payload.layerId), featureId: String(payload.featureId), beforeHash: payload.beforeHash, afterHash: payload.afterHash };
  } catch { return null; }
}

function mergeFeatureState(before, edit) {
  return { geometry: edit.geometry === undefined ? before.geometry : edit.geometry, properties: edit.properties === undefined ? before.properties : edit.properties };
}

function featureStateDiff(before, after) {
  const diff = {};
  if (stableJson(before.geometry) !== stableJson(after.geometry)) diff.geometry = { before: before.geometry, after: after.geometry };
  if (stableJson(before.properties) !== stableJson(after.properties)) diff.properties = { before: before.properties, after: after.properties };
  return diff;
}

function normalizeDocumentContext({ name = '', mime_type = 'text/plain', text = '', source_url = null, metadata = {} }) {
  const allowed = new Set(['text/plain', 'text/markdown', 'text/csv', 'application/json']);
  if (!allowed.has(mime_type)) throw new Error(`Unsupported document format: ${mime_type}`);
  if (typeof text !== 'string' || !text.trim()) throw new Error('Document text is required');
  if (text.length > 200000) throw new Error('Document text exceeds the Phase 1 limit of 200000 characters');
  const cleanName = String(name || 'context.txt').trim().slice(0, 255);
  return { name: cleanName || 'context.txt', mime_type, text: text.trim(), source_url: source_url ? String(source_url).slice(0, 2000) : null, metadata: metadata && typeof metadata === 'object' ? metadata : {} };
}

function normalizeIntersectionInput({ source_layer_id = '', overlay_layer_id = '' }) {
  if (!source_layer_id || !overlay_layer_id) throw new Error('source_layer_id and overlay_layer_id are required');
  if (String(source_layer_id) === String(overlay_layer_id)) throw new Error('source and overlay layers must be different');
  return { source_layer_id: String(source_layer_id), overlay_layer_id: String(overlay_layer_id) };
}

function isSupportedAnalysisOperation(operation) {
  return ['create_review_output', 'buffer_layer', 'intersect_layers'].includes(operation);
}

const SCHEDULE_MIN_INTERVAL_SECONDS = 60;
const ALLOWED_SCHEDULED_OPERATIONS = new Set(['create_review_output']);

function isAllowedScheduledOperation(operation) {
  return ALLOWED_SCHEDULED_OPERATIONS.has(String(operation || '').trim());
}

function normalizeWorkflowScheduleRequest(body = {}) {
  const workflow = body.workflow && typeof body.workflow === 'object' && !Array.isArray(body.workflow) ? body.workflow : body;
  const operation = String(workflow.operation || '').trim();
  if (!isAllowedScheduledOperation(operation)) throw new Error('Only read-only create_review_output workflows may be scheduled');
  const intervalSeconds = Number(body.interval_seconds ?? workflow.interval_seconds);
  if (!Number.isInteger(intervalSeconds) || intervalSeconds < SCHEDULE_MIN_INTERVAL_SECONDS || intervalSeconds > 31536000) {
    throw new Error(`interval_seconds must be at least ${SCHEDULE_MIN_INTERVAL_SECONDS} and at most 31536000`);
  }
  const rawNextRun = body.next_run ?? workflow.next_run;
  const nextRun = rawNextRun == null ? new Date(Date.now() + intervalSeconds * 1000) : new Date(rawNextRun);
  if (Number.isNaN(nextRun.getTime())) throw new Error('next_run must be a valid timestamp');
  const name = String(body.name || workflow.name || 'Scheduled read-only workflow').trim().slice(0, 255);
  if (!name) throw new Error('name is required');
  const cleanWorkflow = { ...workflow, operation };
  delete cleanWorkflow.interval_seconds;
  delete cleanWorkflow.next_run;
  delete cleanWorkflow.name;
  return { name, interval_seconds: intervalSeconds, next_run: nextRun, workflow: cleanWorkflow };
}

function normalizeExportStyle({ style_preset = 'coverage', opacity = 85 } = {}) {
  const presets = new Set(['coverage', 'facilities', 'accessibility', 'risk']);
  const value = Number(opacity);
  if (!presets.has(style_preset)) throw new Error('style_preset must be coverage, facilities, accessibility, or risk');
  if (!Number.isFinite(value) || value < 20 || value > 100) throw new Error('opacity must be between 20 and 100');
  return { style_preset, opacity: value };
}

app.get('/api/auth/status', async (req, res) => {
  const resolved = await resolveIdentity(req).catch(() => null);
  res.json({ authenticated: Boolean(resolved), mode: PHASE1_IDENTITY_MODE, organization_configured: Boolean(DIRECTUS_ORGANIZATION_ID), providers: plannerProviderStatus() });
});

app.get('/api/projects/:projectId/documents', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT id, name, mime_type, length(text_content)::int AS character_count, source_url, sha256, metadata, created_at
       FROM project_documents WHERE project_id = $1 AND organization_id = $2 ORDER BY created_at DESC`,
    [req.params.projectId, req.organizationId],
  );
  res.json({ documents: result.rows });
});

app.post('/api/projects/:projectId/documents', requireIdentity, async (req, res) => {
  let document;
  try { document = normalizeDocumentContext(req.body || {}); }
  catch (error) { return res.status(400).json({ error: error.message }); }
  const project = await pool.query('SELECT id FROM projects WHERE id = $1 AND organization_id = $2', [req.params.projectId, req.organizationId]);
  if (!project.rowCount) return res.status(404).json({ error: 'Project not found' });
  const sha256 = crypto.createHash('sha256').update(document.text, 'utf8').digest('hex');
  const result = await pool.query(
    `INSERT INTO project_documents (project_id, organization_id, name, mime_type, text_content, source_url, sha256, metadata)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
     RETURNING id, name, mime_type, length(text_content)::int AS character_count, source_url, sha256, metadata, created_at`,
    [req.params.projectId, req.organizationId, document.name, document.mime_type, document.text, document.source_url, sha256, document.metadata],
  );
  res.status(201).json({ document: result.rows[0] });
});

app.get('/api/projects/:projectId/documents/:documentId', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT id, name, mime_type, text_content, source_url, sha256, metadata, created_at
       FROM project_documents WHERE id = $1 AND project_id = $2 AND organization_id = $3`,
    [req.params.documentId, req.params.projectId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Document not found' });
  res.json({ document: result.rows[0] });
});

app.post('/api/ai/plan', requireIdentity, async (req, res) => {
  try {
    const context = { prompt: req.body.prompt, documentText: req.body.document_text, sourceNames: req.body.source_names || [] };
    const projectId = req.body.project_id ? String(req.body.project_id) : null;
    if (projectId) {
      const project = await pool.query('SELECT id FROM projects WHERE id = $1 AND organization_id = $2', [projectId, req.organizationId]);
      if (!project.rowCount) return res.status(404).json({ error: 'Project not found' });
    }
    const plan = await createTaskPlan(context);
    const persisted = await persistAgentRun({ organizationId: req.organizationId, projectId, context, plan });
    res.json({ plan, run_id: persisted.run.id, steps: persisted.steps });
  } catch (error) {
    res.status(error.message.includes('Gateway') || error.message.includes('database') ? 503 : 400).json({ error: error.message });
  }
});

app.get('/api/ai/runs/:runId', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT id, organization_id, project_id, status, prompt, context, provider, model, plan, rationale, created_at, updated_at, started_at, completed_at, error
       FROM agent_runs WHERE id = $1 AND organization_id = $2`,
    [req.params.runId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Agent run not found' });
  const steps = await pool.query(
    `SELECT id, run_id, project_id, step_index, status, title, tool, prompt, context, provider, model, plan, rationale, created_at, updated_at, started_at, completed_at, error
       FROM agent_steps WHERE run_id = $1 AND organization_id = $2 ORDER BY step_index`,
    [req.params.runId, req.organizationId],
  );
  res.json({ run: result.rows[0], steps: steps.rows });
});

app.post('/api/ai/runs/:runId/approve', requireIdentity, async (req, res) => {
  try {
    const result = await approveAgentRun({ runId: req.params.runId, organizationId: req.organizationId });
    res.status(201).json(result);
  } catch (error) {
    res.status(error.statusCode || 400).json({ error: error.message });
  }
});

app.get('/api/datasets/search', requireIdentity, async (req, res) => {
  let input;
  try { input = normalizeDatasetSearchInput(req.query); }
  catch (error) { return res.status(400).json({ error: error.message }); }
  if (req.query.project_id) {
    const project = await pool.query('SELECT id FROM projects WHERE id = $1 AND organization_id = $2', [String(req.query.project_id), req.organizationId]);
    if (!project.rowCount) return res.status(404).json({ error: 'Project not found' });
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const url = new URL('https://data.humdata.org/api/3/action/package_search');
    url.searchParams.set('q', input.query);
    url.searchParams.set('rows', String(input.limit));
    const response = await fetch(url, { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!response.ok) return res.status(502).json({ error: `HDX search failed with HTTP ${response.status}` });
    res.json(normalizeHdxSearchResponse(await response.json(), { query: input.query }));
  } catch (error) {
    res.status(502).json({ error: error.name === 'AbortError' ? 'HDX search timed out' : 'HDX search unavailable' });
  } finally { clearTimeout(timeout); }
});

app.post('/api/datasets/import', requireIdentity, async (req, res) => {
  let input;
  try { input = normalizeHdxImportRequest(req.body || {}); }
  catch (error) { return res.status(400).json({ error: error.message }); }
  if (input.project_id !== String(req.body.project_id)) return res.status(400).json({ error: 'project_id is required' });
  const project = await pool.query('SELECT id FROM projects WHERE id = $1 AND organization_id = $2', [input.project_id, req.organizationId]);
  if (!project.rowCount) return res.status(404).json({ error: 'Project not found' });
  let features; let downloaded;
  try {
    downloaded = await downloadHdxResource(input.resource_url);
    features = parseDownloadedHdxResource(downloaded, input.resource_format);
  } catch (error) {
    const status = /HTTP 4|timed out|exceeds|Unsupported|Invalid|requires|unterminated|outside/.test(error.message) ? 400 : 502;
    return res.status(status).json({ error: error.message });
  }
  const retrievedAt = new Date().toISOString();
  const metadata = {
    provider: input.provider,
    dataset_id: input.dataset_id,
    resource_id: input.resource_id,
    metadata_created: input.metadata_created,
    metadata_modified: input.metadata_modified,
    retrieved_at: retrievedAt,
    source: 'HDX / data.humdata.org',
    import_approved: true,
  };
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const layer = await client.query(
      `INSERT INTO project_layers (project_id, organization_id, name, source_url, source_resource, source_modified_at, licence, metadata)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
       RETURNING id, project_id, organization_id, name, source_url, source_resource, source_modified_at, source_retrieved_at, licence, metadata, created_at`,
      [input.project_id, req.organizationId, input.name, input.resource_url, input.resource_id || input.dataset_id, input.metadata_modified, input.licence, metadata],
    );
    for (const feature of features) {
      await client.query(
        `INSERT INTO project_layer_features (layer_id, project_id, organization_id, geometry, properties)
         VALUES ($1,$2,$3,ST_SetSRID(ST_GeomFromGeoJSON($4),4326),$5)`,
        [layer.rows[0].id, input.project_id, req.organizationId, JSON.stringify(feature.geometry), feature.properties],
      );
    }
    await client.query('COMMIT');
    res.status(201).json({ layer: layer.rows[0], feature_count: features.length });
  } catch (error) {
    await client.query('ROLLBACK');
    res.status(400).json({ error: 'HDX layer import failed', detail: error.message });
  } finally { client.release(); }
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

async function executeIntersectionJob(jobId, organizationId) {
  const jobResult = await pool.query('SELECT id, project_id, input, status FROM analysis_jobs WHERE id = $1 AND organization_id = $2', [jobId, organizationId]);
  if (!jobResult.rowCount) throw new Error('Analysis job not found');
  const job = jobResult.rows[0];
  if (job.status !== 'queued') throw new Error(`Analysis job is already ${job.status}`);
  const input = normalizeIntersectionInput(job.input || {});
  const sources = await pool.query(
    `SELECT id, name, licence FROM project_layers WHERE id = ANY($1::uuid[]) AND project_id = $2 AND organization_id = $3`,
    [[input.source_layer_id, input.overlay_layer_id], job.project_id, organizationId],
  );
  if (sources.rowCount !== 2) throw new Error('Source or overlay layer not found');
  const source = sources.rows.find(layer => layer.id === input.source_layer_id);
  const overlay = sources.rows.find(layer => layer.id === input.overlay_layer_id);
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const resultLayer = await client.query(
      `INSERT INTO project_layers (project_id, organization_id, name, source_resource, licence, metadata)
       VALUES ($1,$2,$3,$4,$5,$6) RETURNING id, name, created_at`,
      [job.project_id, organizationId, `${source.name} ∩ ${overlay.name}`, `derived:intersection:${source.id}:${overlay.id}`, source.licence || overlay.licence, { operation: 'intersect_layers', source_layer_id: source.id, overlay_layer_id: overlay.id }],
    );
    const inserted = await client.query(
      `INSERT INTO project_layer_features (layer_id, project_id, organization_id, geometry, properties)
       SELECT $1, $2, $3, ST_CollectionExtract(ST_Intersection(a.geometry, b.geometry), 3),
              jsonb_build_object('source_properties', a.properties, 'overlay_properties', b.properties)
         FROM project_layer_features a JOIN project_layer_features b ON ST_Intersects(a.geometry, b.geometry)
        WHERE a.layer_id = $4 AND b.layer_id = $5 AND a.organization_id = $3 AND b.organization_id = $3
          AND NOT ST_IsEmpty(ST_Intersection(a.geometry, b.geometry))
          AND ST_GeometryType(ST_CollectionExtract(ST_Intersection(a.geometry, b.geometry), 3)) = 'ST_Polygon'
       RETURNING id`,
      [resultLayer.rows[0].id, job.project_id, organizationId, input.source_layer_id, input.overlay_layer_id],
    );
    const output = { type: 'derived_geometry_layer', operation: 'intersect_layers', result_layer_id: resultLayer.rows[0].id, source_layer_id: source.id, overlay_layer_id: overlay.id, feature_count: inserted.rowCount, limitations: ['Only polygon intersections are retained in this Phase 1 operation.', 'Derived output requires human review before operational use.'] };
    const updated = await client.query(`UPDATE analysis_jobs SET status = 'completed', output = $1, completed_at = now() WHERE id = $2 AND organization_id = $3 RETURNING id, operation, status, output, completed_at`, [output, jobId, organizationId]);
    await client.query('COMMIT');
    return updated.rows[0];
  } catch (error) { await client.query('ROLLBACK'); throw error; } finally { client.release(); }
}

app.get('/api/projects/:projectId/analysis-jobs', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT id, operation, status, input, output, provenance, created_at, completed_at
       FROM analysis_jobs WHERE project_id = $1 AND organization_id = $2 ORDER BY created_at DESC LIMIT 100`,
    [req.params.projectId, req.organizationId],
  );
  res.json({ jobs: result.rows });
});

app.get('/api/analysis-jobs/:jobId', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT id, project_id, task_id, operation, status, input, output, provenance, created_at, completed_at
       FROM analysis_jobs WHERE id = $1 AND organization_id = $2`,
    [req.params.jobId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Analysis job not found' });
  res.json({ job: result.rows[0] });
});

app.post('/api/analysis-jobs/:jobId/retry', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `UPDATE analysis_jobs
        SET status = 'queued', output = jsonb_build_object('retry_requested', true), completed_at = NULL,
            provenance = provenance || jsonb_build_object('retry_requested_at', now(), 'retry_requested_by', $2)
      WHERE id = $1 AND organization_id = $2 AND status = 'failed'
      RETURNING id, operation, status, input, provenance, created_at`,
    [req.params.jobId, req.organizationId],
  );
  if (!result.rowCount) return res.status(409).json({ error: 'Only failed jobs can be retried' });
  res.status(202).json({ job: result.rows[0] });
});

app.post('/api/analysis-jobs/:jobId/run', requireIdentity, async (req, res) => {
  try {
    const operation = await pool.query('SELECT operation FROM analysis_jobs WHERE id = $1 AND organization_id = $2', [req.params.jobId, req.organizationId]);
    if (!operation.rowCount) return res.status(404).json({ error: 'Analysis job not found' });
    if (!isSupportedAnalysisOperation(operation.rows[0].operation)) throw new Error(`Unsupported analysis operation: ${operation.rows[0].operation}`);
    const job = operation.rows[0].operation === 'buffer_layer'
      ? await executeBufferJob(req.params.jobId, req.organizationId)
      : operation.rows[0].operation === 'intersect_layers'
        ? await executeIntersectionJob(req.params.jobId, req.organizationId)
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

app.post('/api/projects/:projectId/workflow-schedules', requireIdentity, async (req, res) => {
  let input;
  try { input = normalizeWorkflowScheduleRequest(req.body || {}); }
  catch (error) { return res.status(400).json({ error: error.message }); }
  const project = await pool.query('SELECT id FROM projects WHERE id = $1 AND organization_id = $2', [req.params.projectId, req.organizationId]);
  if (!project.rowCount) return res.status(404).json({ error: 'Project not found' });
  try {
    const result = await pool.query(
      `INSERT INTO workflow_schedules (organization_id, project_id, name, workflow, interval_seconds, next_run)
       VALUES ($1,$2,$3,$4,$5,$6)
       RETURNING id, organization_id, project_id, name, workflow, interval_seconds, next_run, status, last_run_id, last_run_at, last_error, created_at, updated_at`,
      [req.organizationId, req.params.projectId, input.name, input.workflow, input.interval_seconds, input.next_run],
    );
    res.status(201).json({ schedule: result.rows[0] });
  } catch (error) { res.status(400).json({ error: 'Workflow schedule creation failed', detail: error.message }); }
});

app.get('/api/projects/:projectId/workflow-schedules', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT id, organization_id, project_id, name, workflow, interval_seconds, next_run, status,
            last_run_id, last_run_at, last_error, created_at, updated_at
       FROM workflow_schedules WHERE project_id = $1 AND organization_id = $2 ORDER BY created_at DESC`,
    [req.params.projectId, req.organizationId],
  );
  res.json({ schedules: result.rows });
});

app.post('/api/workflow-schedules/:scheduleId/cancel', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `UPDATE workflow_schedules SET status = 'cancelled', updated_at = now()
      WHERE id = $1 AND organization_id = $2 RETURNING id, organization_id, project_id, name, workflow, interval_seconds, next_run, status, last_run_id, last_run_at, last_error, created_at, updated_at`,
    [req.params.scheduleId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Workflow schedule not found' });
  res.json({ schedule: result.rows[0] });
});

async function listWorkflowRuns(req, res) {
  const result = await pool.query(
    `SELECT id, organization_id, project_id, schedule_id, analysis_job_id, operation, workflow, status,
            output, error, started_at, completed_at, created_at, updated_at
       FROM workflow_runs WHERE schedule_id = $1 AND organization_id = $2 ORDER BY created_at DESC LIMIT 100`,
    [req.params.scheduleId, req.organizationId],
  );
  res.json({ runs: result.rows });
}
app.get('/api/workflow-schedules/:scheduleId/runs', requireIdentity, listWorkflowRuns);
app.get('/api/projects/:projectId/workflow-schedules/:scheduleId/runs', requireIdentity, async (req, res) => {
  const schedule = await pool.query('SELECT id FROM workflow_schedules WHERE id = $1 AND project_id = $2 AND organization_id = $3', [req.params.scheduleId, req.params.projectId, req.organizationId]);
  if (!schedule.rowCount) return res.status(404).json({ error: 'Workflow schedule not found' });
  return listWorkflowRuns(req, res);
});

app.post('/api/workflow-schedules/:scheduleId/run', requireIdentity, async (req, res) => {
  const scheduleResult = await pool.query(
    `SELECT id, project_id, organization_id, workflow, status FROM workflow_schedules WHERE id = $1 AND organization_id = $2`,
    [req.params.scheduleId, req.organizationId],
  );
  if (!scheduleResult.rowCount) return res.status(404).json({ error: 'Workflow schedule not found' });
  const schedule = scheduleResult.rows[0];
  if (schedule.status !== 'active') return res.status(409).json({ error: 'Workflow schedule is cancelled' });
  if (!isAllowedScheduledOperation(schedule.workflow?.operation)) return res.status(400).json({ error: 'Scheduled workflow is not an allowed read-only operation' });
  const client = await pool.connect();
  let clientReleased = false;
  let run;
  let job;
  try {
    await client.query('BEGIN');
    const jobResult = await client.query(
      `INSERT INTO analysis_jobs (project_id, organization_id, operation, status, input, provenance)
       VALUES ($1,$2,$3,'queued',$4,$5) RETURNING id, project_id, organization_id, operation, status, input, provenance, created_at`,
      [schedule.project_id, req.organizationId, schedule.workflow.operation, schedule.workflow.input || {}, { source: 'workflow-schedule', schedule_id: schedule.id }],
    );
    job = jobResult.rows[0];
    const runResult = await client.query(
      `INSERT INTO workflow_runs (organization_id, project_id, schedule_id, analysis_job_id, operation, workflow, status, started_at)
       VALUES ($1,$2,$3,$4,$5,$6,'running',now())
       RETURNING id, organization_id, project_id, schedule_id, analysis_job_id, operation, workflow, status, output, error, started_at, completed_at, created_at, updated_at`,
      [req.organizationId, schedule.project_id, schedule.id, job.id, schedule.workflow.operation, schedule.workflow],
    );
    run = runResult.rows[0];
    await client.query('COMMIT');
  } catch (error) {
    await client.query('ROLLBACK');
    client.release();
    clientReleased = true;
    return res.status(400).json({ error: 'Workflow run creation failed', detail: error.message });
  } finally { if (!clientReleased) client.release(); }
  try {
    const completedJob = await executeReviewOutputJob(job.id, req.organizationId);
    const completed = await pool.query(
      `UPDATE workflow_runs SET status = 'completed', output = $1, completed_at = now(), updated_at = now()
        WHERE id = $2 AND organization_id = $3
        RETURNING id, organization_id, project_id, schedule_id, analysis_job_id, operation, workflow, status, output, error, started_at, completed_at, created_at, updated_at`,
      [completedJob.output, run.id, req.organizationId],
    );
    const scheduleUpdate = await pool.query(
      `UPDATE workflow_schedules SET last_run_id = $1, last_run_at = now(), last_error = NULL,
              next_run = now() + (interval_seconds * interval '1 second'), updated_at = now()
        WHERE id = $2 AND organization_id = $3
        RETURNING id, organization_id, project_id, name, workflow, interval_seconds, next_run, status, last_run_id, last_run_at, last_error, created_at, updated_at`,
      [run.id, schedule.id, req.organizationId],
    );
    return res.json({ run: completed.rows[0], job: completedJob, schedule: scheduleUpdate.rows[0] });
  } catch (error) {
    await pool.query(`UPDATE analysis_jobs SET status = 'failed', output = $1, completed_at = now() WHERE id = $2 AND organization_id = $3`, [{ error: error.message }, job.id, req.organizationId]);
    const failed = await pool.query(`UPDATE workflow_runs SET status = 'failed', error = $1, completed_at = now(), updated_at = now() WHERE id = $2 AND organization_id = $3 RETURNING id, status, error, started_at, completed_at, created_at, updated_at`, [error.message, run.id, req.organizationId]);
    await pool.query(`UPDATE workflow_schedules SET last_run_id = $1, last_run_at = now(), last_error = $2, next_run = now() + (interval_seconds * interval '1 second'), updated_at = now() WHERE id = $3 AND organization_id = $4`, [run.id, error.message, schedule.id, req.organizationId]);
    return res.status(400).json({ error: 'Workflow run failed', run: failed.rows[0] });
  }
});

app.post('/api/projects/:projectId/workflow-schedules/:scheduleId/run', requireIdentity, async (req, res) => {
  const schedule = await pool.query('SELECT id FROM workflow_schedules WHERE id = $1 AND project_id = $2 AND organization_id = $3', [req.params.scheduleId, req.params.projectId, req.organizationId]);
  if (!schedule.rowCount) return res.status(404).json({ error: 'Workflow schedule not found' });
  req.url = `/api/workflow-schedules/${schedule.rows[0].id}/run`;
  return app.handle(req, res);
});

app.post('/api/projects/:projectId/analysis-jobs', requireIdentity, async (req, res) => {
  const project = await pool.query('SELECT id FROM projects WHERE id = $1 AND organization_id = $2', [req.params.projectId, req.organizationId]);
  if (!project.rowCount) return res.status(404).json({ error: 'Project not found' });
  if (!['buffer_layer', 'intersect_layers'].includes(req.body.operation)) return res.status(400).json({ error: 'Unsupported operation' });
  try {
    const input = req.body.operation === 'buffer_layer'
      ? (() => { const distance = Number(req.body.distance_meters); if (!req.body.source_layer_id || !Number.isFinite(distance) || distance <= 0 || distance > 100000) throw new Error('source_layer_id and distance_meters (1–100000) are required'); return { source_layer_id: req.body.source_layer_id, distance_meters: distance }; })()
      : normalizeIntersectionInput(req.body);
    const result = await pool.query(
      `INSERT INTO analysis_jobs (project_id, organization_id, operation, status, input, provenance)
       VALUES ($1,$2,$3,'queued',$4,$5) RETURNING id, operation, status, input, created_at`,
      [req.params.projectId, req.organizationId, req.body.operation, input, { source: 'user-request', phase: '1' }],
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
  const classification = layout.classification || 'DRAFT · REVIEW REQUIRED';
  const style = normalizeExportStyle(layout);
  const styleMap = { coverage: ['#d96a54', '#d96a5466'], facilities: ['#dfa43b', '#dfa43b66'], accessibility: ['#087f7a', '#087f7a55'], risk: ['#a952c4', '#a952c466'] };
  const [styleStroke, styleFill] = styleMap[style.style_preset];
  const date = new Date().toISOString().slice(0, 10);
  const totalFeatures = features.length;
  const sourceRows = layers.map((layer, index) => `<tr><td>${index + 1}</td><td>${escapeHtml(layer.name)}</td><td>${escapeHtml(layer.source_resource || 'project layer')}</td><td>${layer.feature_count}</td></tr>`).join('');
  const provenanceRows = layers.map(layer => `<li>${escapeHtml(layer.name)}: ${layer.feature_count} stored features; source ${escapeHtml(layer.source_resource || 'not specified')}.</li>`).join('');
  const pages = [
    `<article class="page cover"><div class="brand">Cartogen AI · Humanitarian Mapping</div><div class="classification">${escapeHtml(classification)}</div><h1>${escapeHtml(title)}</h1><p class="lead">Humanitarian service-coverage screening situation report</p><div class="hero-rule"></div><dl><dt>Prepared by</dt><dd>${escapeHtml(author)}</dd><dt>Project</dt><dd>${escapeHtml(project.name)}</dd><dt>Reference system</dt><dd>${escapeHtml(project.crs)}</dd><dt>Report version</dt><dd>${escapeHtml(reportVersion)}</dd><dt>Prepared</dt><dd>${date}</dd></dl><div class="warning">This report supports structured humanitarian review. It is not a needs assessment, targeting decision, or live security product.</div></article>`,
    `<article class="page"><h2>1. Executive summary</h2><p>This report presents a reviewable, public-data screening slice for humanitarian service coverage in ${escapeHtml(project.name)}. The result combines project layers stored in PostGIS with documented source and compatibility limitations.</p><div class="stat-grid"><div><b>${layers.length}</b><small>project layers</small></div><div><b>${totalFeatures}</b><small>features in export</small></div><div><b>${escapeHtml(project.crs)}</b><small>coordinate reference</small></div></div><h3>Review findings</h3><ul><li>Stored project geometry is available for visual and attribute review.</li><li>Derived layers are retained separately from source layers.</li><li>Source age and administrative compatibility require analyst confirmation.</li><li>Any operational use requires provenance and limitations to remain attached.</li></ul><h3>Recommended next action</h3><p>Confirm source vintages and administrative crosswalks with the responsible information-management team before using the screening output for prioritisation.</p></article>`,
    `<article class="page"><h2>2. Map and layer register</h2><div class="map-report">${buildExportSvg(features)}</div><h3>Layer register</h3><table><thead><tr><th>#</th><th>Layer</th><th>Source</th><th>Features</th></tr></thead><tbody>${sourceRows}</tbody></table></article>`,
    `<article class="page"><h2>3. Limitations and provenance appendix</h2><h3>Known limitations</h3><ul><li>Population reference year 2017 is not directly compatible with newer administrative boundaries without a validated crosswalk.</li><li>3W presence does not prove service quality, capacity, funding, outcomes, or absence of need.</li><li>Modelled accessibility is not live road-status or security information.</li><li>Public-data demonstration layers are not a substitute for controlled humanitarian datasets.</li></ul><h3>Provenance register</h3><ul>${provenanceRows}</ul><div class="warning">Retain source URL, resource date, retrieval date, licence, assumptions, and limitations with every distributed copy.</div></article>`
  ];
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(title)} — Situation Report</title><style>@page{size:${escapeHtml(layout.paper || 'A4')} ${escapeHtml(layout.orientation || 'portrait')};margin:12mm}*{box-sizing:border-box}body{font-family:Arial,sans-serif;color:#10232b;margin:0;background:#eef4f2}.page{background:#fff;min-height:calc(297mm - 24mm);padding:12mm;page-break-after:always;position:relative}.page:last-child{page-break-after:auto}.brand{color:#087f7a;font-weight:800;font-size:17px}.classification{float:right;color:#9d402f;font-size:9px;font-weight:800;border:1px solid #e5b7ac;padding:2mm;border-radius:4px}.cover{display:flex;flex-direction:column;justify-content:center}.cover h1{font-size:30px;max-width:170mm;margin:24mm 0 5mm;color:#102b33}.lead{font-size:16px;color:#627276}.hero-rule{height:4px;background:#087f7a;width:55mm;margin:12mm 0}.page h2{font-size:22px;color:#087f7a;border-bottom:2px solid #dce5e6;padding-bottom:4mm}.page h3{font-size:14px;color:#087f7a;margin-top:9mm}.page p,.page li{font-size:11px;line-height:1.55}.page dl{display:grid;grid-template-columns:42mm 1fr;gap:3mm;font-size:11px}.page dt{font-weight:800;color:#627276}.page dd{margin:0}.warning{background:#fff8e7;border:1px solid #e5c978;padding:4mm;margin-top:8mm;font-size:10px;line-height:1.45}.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:5mm;margin:8mm 0}.stat-grid div{border:1px solid #cddbd9;padding:6mm;text-align:center}.stat-grid b{display:block;font-size:22px;color:#087f7a}.stat-grid small{color:#627276}.map-report{height:120mm;border:1px solid #9db4b1;background:#e4eeea;position:relative;margin:7mm 0}.map-report:after{content:'N ↑';position:absolute;right:6mm;top:6mm;background:#fff;border:1px solid #c6d6d3;padding:2mm;font-weight:800}.map-report:before{content:'0 ─── 5 ─── 10 km';position:absolute;right:6mm;bottom:6mm;background:#ffffffe8;border:1px solid #c6d6d3;padding:2mm;font-size:8px}.map-report svg{width:100%;height:100%;display:block;opacity:${style.opacity / 100}}.map-report circle{fill:${styleStroke};stroke:#fff;stroke-width:.7}.map-report path{fill:${styleFill};stroke:${styleStroke};stroke-width:.6}.map-report polyline{fill:none;stroke:${styleStroke};stroke-width:.6}table{width:100%;border-collapse:collapse;font-size:10px}th,td{text-align:left;border-bottom:1px solid #dce5e6;padding:3mm}th{color:#627276;font-size:9px;text-transform:uppercase}.page-number{position:absolute;bottom:6mm;right:12mm;color:#879699;font-size:8px}</style></head><body>${pages.map((page, index) => page.replace('</article>', `<div class="page-number">Page ${index + 1} of ${pages.length} · Cartogen AI</div></article>`)).join('')}</body></html>`;
}

function buildServerExportHtml(project, layers, layout, features = []) {
  if (layout.report_type === 'situation_report') return buildSituationReportHtml(project, layers, layout, features);
  const title = layout.title || project.name;
  const paper = layout.paper || 'A4';
  const orientation = layout.orientation || 'landscape';
  const author = layout.author || 'Cartogen AI Humanitarian Mapping';
  const warnings = layout.include_warnings !== false;
  const style = normalizeExportStyle(layout);
  const styleMap = { coverage: ['#d96a54', '#d96a5466'], facilities: ['#dfa43b', '#dfa43b66'], accessibility: ['#087f7a', '#087f7a55'], risk: ['#a952c4', '#a952c466'] };
  const [styleStroke, styleFill] = styleMap[style.style_preset];
  const sourceItems = layers.map(layer => `<li><b>${escapeHtml(layer.name)}</b> — ${escapeHtml(layer.source_resource || 'project layer')} — ${layer.feature_count} features</li>`).join('');
  const legendItems = layers.map(layer => `<div><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${styleStroke}"></span> ${escapeHtml(layer.name)} <small>(${layer.feature_count})</small></div>`).join('');
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(title)} — Cartogen AI</title><style>@page{size:${escapeHtml(paper)} ${escapeHtml(orientation)};margin:12mm}body{font-family:Arial,sans-serif;color:#10232b;margin:0}.sheet{min-height:180mm;display:grid;grid-template-rows:auto 1fr auto;gap:7mm}.header{border-bottom:3px solid #087f7a;padding-bottom:4mm;display:flex;justify-content:space-between}.brand{font-weight:800;color:#087f7a;font-size:18px}.title{font-size:23px;font-weight:800;margin-top:2mm}.meta,.footer{font-size:9px;color:#627276}.body{display:grid;grid-template-columns:1fr 65mm;gap:6mm}.map{border:1px solid #9db4b1;background:#e4eeea;min-height:105mm;display:grid;place-items:center;color:#557174;position:relative}.map:after{content:'N ↑';position:absolute;right:7mm;top:7mm;background:#fff;border:1px solid #c6d6d3;border-radius:5px;padding:2mm;font-weight:800}.map:before{content:'0 ─── 5 ─── 10 km';position:absolute;right:7mm;bottom:7mm;background:#ffffffe8;border:1px solid #c6d6d3;border-radius:4px;padding:2mm;font-size:8px}.map svg{width:100%;height:100%;display:block;opacity:${style.opacity / 100}}.map circle{fill:${styleStroke};stroke:#fff;stroke-width:.7}.map path{fill:${styleFill};stroke:${styleStroke};stroke-width:.6}.map polyline{fill:none;stroke:${styleStroke};stroke-width:.6}.side{border:1px solid #cddbd9;padding:4mm;font-size:9px}.side h3{font-size:11px;color:#087f7a;margin:0 0 2mm}.side ul{padding-left:4mm}.warning{background:#fff8e7;border:1px solid #e5c978;padding:2mm;margin-top:3mm}.footer{border-top:1px solid #cddbd9;padding-top:3mm;display:flex;justify-content:space-between}</style></head><body><main class="sheet"><header class="header"><div><div class="brand">Cartogen AI · Humanitarian Mapping</div><div class="title">${escapeHtml(title)}</div><div class="meta">Prepared by ${escapeHtml(author)} · ${new Date().toISOString().slice(0,10)} · CRS ${escapeHtml(project.crs)}</div></div><div class="meta">${escapeHtml(project.sector)}<br>Phase 1 review export</div></header><div class="body"><section class="map">${buildExportSvg(features)}</section><aside class="side"><h3>Legend</h3>${legendItems}<h3>Layers and sources</h3><ul>${sourceItems}</ul>${warnings?'<h3>Data quality</h3><div class="warning">Review source freshness, administrative compatibility, and humanitarian limitations before publication.</div><div class="warning">This is a screening result, not a needs assessment or operational targeting decision.</div>':''}</aside></div><footer class="footer"><span>Source dates, licences, assumptions, and limitations accompany this output.</span><span>${escapeHtml(author)} · Cartogen AI</span></footer></main></body></html>`;
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

app.get('/api/projects/:projectId/exports', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT id, format, status, layout->>'title' AS title, layout->>'report_type' AS report_type,
            layout->>'report_version' AS report_version, created_at, completed_at
       FROM export_jobs WHERE project_id = $1 AND organization_id = $2 ORDER BY created_at DESC LIMIT 50`,
    [req.params.projectId, req.organizationId],
  );
  res.json({ exports: result.rows });
});

app.get('/api/projects/:projectId/exports/:exportId', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT id, format, status, layout, provenance, created_at, completed_at
       FROM export_jobs WHERE id = $1 AND project_id = $2 AND organization_id = $3`,
    [req.params.exportId, req.params.projectId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Export not found' });
  res.json({ export: result.rows[0] });
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

app.get('/api/layers/:layerId/features/:featureId', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT f.id, f.layer_id, f.project_id, f.organization_id, ST_AsGeoJSON(f.geometry)::json AS geometry, f.properties
       FROM project_layer_features f JOIN project_layers l ON l.id = f.layer_id
      WHERE f.id = $1 AND f.layer_id = $2 AND f.organization_id = $3 AND l.organization_id = $3 AND f.project_id = l.project_id`,
    [req.params.featureId, req.params.layerId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Feature not found' });
  const row = result.rows[0];
  const state = { geometry: row.geometry, properties: row.properties || {} };
  res.json({ feature: { type: 'Feature', id: String(row.id), geometry: row.geometry, properties: row.properties || {} }, before_hash: hashFeatureState(state) });
});

app.post('/api/layers/:layerId/features/:featureId/edit', requireIdentity, async (req, res) => {
  let edit;
  try { edit = normalizeFeatureEditRequest(req.body || {}); }
  catch (error) { return res.status(400).json({ error: error.message }); }
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await client.query(
      `SELECT f.id, f.layer_id, f.project_id, f.organization_id, ST_AsGeoJSON(f.geometry)::json AS geometry, f.properties
         FROM project_layer_features f JOIN project_layers l ON l.id = f.layer_id
        WHERE f.id = $1 AND f.layer_id = $2 AND f.organization_id = $3 AND l.organization_id = $3 AND f.project_id = l.project_id
        FOR UPDATE`,
      [req.params.featureId, req.params.layerId, req.organizationId],
    );
    if (!result.rowCount) { await client.query('ROLLBACK'); return res.status(404).json({ error: 'Feature not found' }); }
    const row = result.rows[0];
    const before = { geometry: row.geometry, properties: row.properties || {} };
    const beforeHash = hashFeatureState(before);
    const after = mergeFeatureState(before, edit);
    const afterHash = hashFeatureState(after);
    const tokenPayload = edit.preview_token ? verifyEditPreviewToken(edit.preview_token) : null;
    if (edit.before_hash && edit.before_hash !== beforeHash) { await client.query('ROLLBACK'); return res.status(409).json({ error: 'Feature has changed since the supplied before_hash', before_hash: beforeHash }); }
    if (edit.mode === 'apply') {
      const tokenMatches = tokenPayload && tokenPayload.layerId === String(req.params.layerId) && tokenPayload.featureId === String(req.params.featureId) && tokenPayload.beforeHash === beforeHash && tokenPayload.afterHash === afterHash;
      if (!tokenMatches && !edit.before_hash) { await client.query('ROLLBACK'); return res.status(409).json({ error: 'A valid preview_token or matching before_hash is required' }); }
      if (tokenPayload && (!tokenMatches || tokenPayload.beforeHash !== beforeHash)) { await client.query('ROLLBACK'); return res.status(409).json({ error: 'Preview token is stale or does not match this feature' }); }
      const updated = await client.query(
        `UPDATE project_layer_features
            SET properties = $1::jsonb, geometry = CASE WHEN $2::text IS NULL THEN geometry ELSE ST_SetSRID(ST_GeomFromGeoJSON($2),4326) END
          WHERE id = $3 AND layer_id = $4 AND project_id = $5 AND organization_id = $6
          RETURNING id, ST_AsGeoJSON(geometry)::json AS geometry, properties`,
        [after.properties, edit.geometry === undefined ? null : JSON.stringify(after.geometry), req.params.featureId, req.params.layerId, row.project_id, req.organizationId],
      );
      if (!updated.rowCount) throw new Error('Feature update failed');
      await client.query(
        `INSERT INTO feature_lineage_events (feature_id, layer_id, project_id, organization_id, event_type, actor_id, before_hash, after_hash, before_state, after_state, metadata)
         VALUES ($1,$2,$3,$4,'feature_edit',$5,$6,$7,$8,$9,$10)`,
        [row.id, row.layer_id, row.project_id, req.organizationId, req.user?.id || null, beforeHash, afterHash, before, after, { approved: true, via_preview_token: Boolean(tokenMatches) }],
      );
      await client.query('COMMIT');
      return res.json({ mode: 'apply', applied: true, before, after, diff: featureStateDiff(before, after), before_hash: beforeHash, after_hash: afterHash });
    }
    const previewToken = createEditPreviewToken({ layerId: req.params.layerId, featureId: req.params.featureId, beforeHash, afterHash });
    await client.query('ROLLBACK');
    return res.json({ mode: 'preview', applied: false, before, after, diff: featureStateDiff(before, after), before_hash: beforeHash, after_hash: afterHash, preview_token: previewToken });
  } catch (error) {
    try { await client.query('ROLLBACK'); } catch {}
    res.status(400).json({ error: 'Feature edit failed', detail: error.message });
  } finally { client.release(); }
});

app.get('/api/layers/:layerId/geojson', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT f.id, ST_AsGeoJSON(f.geometry)::json AS geometry, f.properties
       FROM project_layer_features f
       JOIN project_layers l ON l.id = f.layer_id
      WHERE f.layer_id = $1 AND f.organization_id = $2 AND l.organization_id = $2
      ORDER BY f.id`,
    [req.params.layerId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Layer not found or empty' });
  res.json({ type: 'FeatureCollection', features: result.rows.map(row => ({ id: String(row.id), type: 'Feature', geometry: row.geometry, properties: row.properties })) });
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

module.exports = { app, pool, PLANNER_PROVIDER_MODELS, resolvePlannerModel, plannerProviderStatus, GATEWAY_SYSTEM_PROMPT, buildGatewayMessages, normalizeFeatureCollection, normalizeDocumentContext, normalizeIntersectionInput, isSupportedAnalysisOperation, isAllowedScheduledOperation, normalizeWorkflowScheduleRequest, normalizeExportStyle, buildTaskPlan, parsePlannerResponse, createTaskPlan, persistAgentRun, approveAgentRun, validateApprovalPlan, normalizeDatasetSearchInput, normalizeHdxSearchResponse, normalizeHdxImportRequest, normalizeCsvResource, downloadHdxResource, parseDownloadedHdxResource, executeReviewOutputJob, executeBufferJob, executeIntersectionJob, normalizeFeatureEditRequest, canonicalFeatureState, hashFeatureState, createEditPreviewToken, verifyEditPreviewToken, mergeFeatureState, featureStateDiff };
