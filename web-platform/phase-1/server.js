const path = require('node:path');
const crypto = require('node:crypto');
const net = require('node:net');
const express = require('express');
const helmet = require('helmet');
const { rateLimit } = require('express-rate-limit');
const { Pool } = require('pg');

const PORT = Number(process.env.PORT || 4180);
const DATABASE_URL = process.env.DATABASE_URL || 'postgresql://cartogen:phase1_local_only_change_me@127.0.0.1:55432/cartogen_phase1';
const NODE_ENV = process.env.NODE_ENV || 'development';
const PHASE1_IDENTITY_MODE = process.env.PHASE1_IDENTITY_MODE || 'demo';
const DIRECTUS_URL = process.env.DIRECTUS_URL || 'http://127.0.0.1:8055';
const DIRECTUS_COOKIE = 'cartogen_session';
const DIRECTUS_ORGANIZATION_ID = process.env.PHASE1_DIRECTUS_ORGANIZATION_ID || null;
// Off by default. When on, ANY authenticated Directus user with zero
// organization_members rows is treated as a member (never 'owner') of
// PHASE1_DIRECTUS_ORGANIZATION_ID -- a migration aid for the single
// pre-multi-tenant deployment that set PHASE1_DIRECTUS_ORGANIZATION_ID
// before organization_members existed. Never enable in a shared/production
// deployment: it grants org access with no membership record at all.
const ALLOW_LEGACY_ORG_FALLBACK = process.env.PHASE1_ALLOW_LEGACY_ORG_FALLBACK === 'true';
const LITELLM_URL = process.env.LITELLM_URL || 'http://127.0.0.1:4000';
const LITELLM_MASTER_KEY = process.env.LITELLM_MASTER_KEY || null;
const LITELLM_PLAN_MAX_BUDGET_USD = Number(process.env.LITELLM_PLAN_MAX_BUDGET_USD || 5);
const STRIPE_SECRET_KEY = process.env.STRIPE_SECRET_KEY || null;
const STRIPE_WEBHOOK_SECRET = process.env.STRIPE_WEBHOOK_SECRET || null;
const ALLOW_UNSIGNED_STRIPE_WEBHOOKS = process.env.ALLOW_UNSIGNED_STRIPE_WEBHOOKS === 'true';
const STRIPE_PRICE_ID = process.env.STRIPE_PRICE_ID || null;
const STRIPE_PORTAL_CONFIGURATION_ID = process.env.STRIPE_PORTAL_CONFIGURATION_ID || null;
const PUBLIC_BASE_URL = process.env.PUBLIC_BASE_URL || null;
// Origins allowed to make cookie-authenticated cross-origin requests, and the
// same allowlist doubles as the CSRF Origin/Referer check below. PUBLIC_BASE_URL
// is always included when set. Comma-separated; extra origins are only needed
// if the frontend is ever served from a different origin than this API (e.g.
// behind a reverse proxy that splits them) -- the default single-origin
// deployment (this server serves both the HTML and the /api/* routes) needs
// nothing extra here.
const CORS_ALLOWED_ORIGINS = new Set(
  [PUBLIC_BASE_URL, ...(process.env.CORS_ALLOWED_ORIGINS || '').split(',').map(value => value.trim())].filter(Boolean),
);
// Requiring 'stripe' lazily (only when a secret key is configured) means the
// module still boots and every non-billing route still works on a deployment
// that hasn't set up Stripe yet -- billing routes report 'not configured'
// instead of crashing the whole server at require-time.
const stripeClient = STRIPE_SECRET_KEY ? require('stripe')(STRIPE_SECRET_KEY) : null;
const app = express();
// Prefer discrete PG* connection params over a single interpolated
// DATABASE_URL when they're set: docker-compose's ${VAR} substitution has no
// URL-encoding step, so a generated password containing @ : / ? # would
// silently corrupt a `postgresql://user:${PASSWORD}@host/db` string (a
// truncated/misparsed user, host, or path) instead of failing loudly. Passing
// the fields directly to `pg` sidesteps that entirely -- no string to
// mis-parse. DATABASE_URL remains supported for anyone running server.js
// outside the merged compose stack with a password known not to contain
// those characters.
const PG_DISCRETE_ENV_KEYS = ['PGHOST', 'PGPORT', 'PGUSER', 'PGPASSWORD', 'PGDATABASE'];
const hasDiscretePgEnv = PG_DISCRETE_ENV_KEYS.some(key => process.env[key]);
const poolConfig = hasDiscretePgEnv
  ? {
      host: process.env.PGHOST || '127.0.0.1',
      port: Number(process.env.PGPORT || 5432),
      user: process.env.PGUSER || 'cartogen',
      password: process.env.PGPASSWORD || '',
      database: process.env.PGDATABASE || 'cartogen_phase1',
      max: 5,
    }
  : { connectionString: DATABASE_URL, max: 5 };
const pool = new Pool(poolConfig);

app.disable('x-powered-by');

// Stripe requires the RAW request body for webhook signature verification, so
// this route must be registered before the global express.json() parser
// below -- once express.json() consumes a request body, the raw bytes are
// gone. handleStripeWebhook is a hoisted function declaration defined further
// down in this file; referencing it here before its definition is safe.
app.post('/api/billing/webhook', express.raw({ type: 'application/json' }), handleStripeWebhook);

app.use(express.json({ limit: '2mb' }));

// Security headers. CSP allows 'unsafe-inline' for script-src/style-src
// because every page in this app (index.html, login.html, welcome.html) is a
// single file with its logic inline -- a stricter nonce-based CSP would
// require splitting those into external .js files (or per-request nonce
// injection), which is a real follow-up but out of scope here. Even with
// that carve-out, this still blocks remote script/object injection,
// clickjacking (frame-ancestors), and MIME-sniffing, which the app had zero
// protection against before. imgSrc lists the exact basemap tile hosts
// index.html's L.tileLayer() calls use (OSM, HOT, Carto Voyager, Esri) --
// {s}.tile.openstreetmap.org, {s}.tile.openstreetmap.fr, and
// {s}.basemaps.cartocdn.com's {s} subdomain wildcard is why these need
// wildcard-subdomain entries rather than exact hosts.
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'", "'unsafe-inline'", 'https://unpkg.com'],
      styleSrc: ["'self'", "'unsafe-inline'", 'https://unpkg.com'],
      imgSrc: [
        "'self'", 'data:', 'blob:',
        'https://*.tile.openstreetmap.org', 'https://*.tile.openstreetmap.fr',
        'https://*.basemaps.cartocdn.com', 'https://server.arcgisonline.com',
      ],
      connectSrc: ["'self'"],
      fontSrc: ["'self'", 'https://unpkg.com', 'data:'],
      objectSrc: ["'none'"],
      baseUri: ["'self'"],
      frameAncestors: ["'self'"],
    },
  },
  // Third-party tiles/scripts above aren't served with CORP/COEP headers of
  // their own, so a strict cross-origin-embedder-policy would silently block
  // them (Leaflet tiles just not appearing, no console error explaining why).
  crossOriginEmbedderPolicy: false,
}));

// Explicit CORS: this server serves both the frontend HTML and the /api/*
// routes from one origin, so no cross-origin API access is required for the
// app to function -- the correct default is to allow none, explicitly,
// rather than silently inheriting whatever Express's un-configured default
// happens to be. CORS_ALLOWED_ORIGINS exists only for a reverse-proxy setup
// that splits frontend and API onto different origins.
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin && CORS_ALLOWED_ORIGINS.has(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
    res.setHeader('Access-Control-Allow-Credentials', 'true');
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,PATCH,DELETE,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type,x-organization-id,x-demo-organization');
  }
  if (req.method === 'OPTIONS') return res.status(204).end();
  next();
});

// CSRF protection for cookie-authenticated state-changing requests. The
// session cookie is SameSite=Lax + HttpOnly already (see setSessionCookie
// below), which blocks most cross-site POSTs in modern browsers -- this is
// defense in depth on top of that, and the only requests it actually
// constrains are ones that (a) change state (non-GET/HEAD/OPTIONS) and (b)
// carry the session cookie. A request with no session cookie has nothing for
// CSRF to forge, so it's left to the normal requireIdentity/requireUser auth
// checks. The Stripe webhook is naturally exempt: Stripe never sends the
// cartogen_session cookie, and that route is authenticated by signature
// verification instead, not by this cookie at all.
app.use((req, res, next) => {
  if (['GET', 'HEAD', 'OPTIONS'].includes(req.method)) return next();
  const hasSessionCookie = Boolean(parseCookies(req.headers.cookie)[DIRECTUS_COOKIE]);
  if (!hasSessionCookie) return next();
  const originHeader = req.headers.origin || req.headers.referer;
  if (!originHeader) return res.status(403).json({ error: 'Missing Origin/Referer header on a cookie-authenticated request' });
  let requestOrigin;
  try { requestOrigin = new URL(originHeader).origin; } catch { return res.status(403).json({ error: 'Invalid Origin/Referer header' }); }
  const selfOrigin = PUBLIC_BASE_URL ? new URL(PUBLIC_BASE_URL).origin : `${req.protocol}://${req.get('host')}`;
  if (requestOrigin !== selfOrigin && !CORS_ALLOWED_ORIGINS.has(requestOrigin)) {
    return res.status(403).json({ error: 'Cross-origin request rejected' });
  }
  next();
});

// Rate limiting. Auth routes are the classic credential-stuffing/brute-force
// target; HDX import/search fan out to an external host per request and
// (for import) write to Postgres, so both are worth capping independently of
// general traffic. Window/max are deliberately generous for real usage and
// tight enough to blunt automated abuse; tune via env if a deployment needs
// different numbers.
const authRateLimit = rateLimit({
  windowMs: Number(process.env.AUTH_RATE_LIMIT_WINDOW_MS || 15 * 60 * 1000),
  limit: Number(process.env.AUTH_RATE_LIMIT_MAX || 20),
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many attempts, please try again later' },
});
const hdxRateLimit = rateLimit({
  windowMs: Number(process.env.HDX_RATE_LIMIT_WINDOW_MS || 15 * 60 * 1000),
  limit: Number(process.env.HDX_RATE_LIMIT_MAX || 60),
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many dataset requests, please try again later' },
});

app.get(['/', '/index.html'], (req, res) => res.sendFile(path.join(__dirname, 'index.html')));
app.get(['/welcome', '/welcome.html'], (req, res) => res.sendFile(path.join(__dirname, 'welcome.html'), error => { if (error) res.status(404).json({ error: 'Not found' }); }));
app.get(['/login', '/login.html'], (req, res) => res.sendFile(path.join(__dirname, 'login.html'), error => { if (error) res.status(404).json({ error: 'Not found' }); }));

function parseCookies(header = '') {
  return Object.fromEntries(header.split(';').map(part => { const index = part.indexOf('='); return index < 0 ? ['', ''] : [part.slice(0, index).trim(), decodeURIComponent(part.slice(index + 1).trim())]; }).filter(([key]) => key));
}

function isLoopbackAddress(address) {
  const normalized = String(address || '').replace(/^::ffff:/i, '');
  return normalized === '::1' || (net.isIP(normalized) === 4 && normalized.startsWith('127.'));
}

function requestIsLoopback(req) {
  return isLoopbackAddress(req.ip || req.socket?.remoteAddress);
}

async function directusUser(req) {
  const token = parseCookies(req.headers.cookie)[DIRECTUS_COOKIE];
  if (!token) return null;
  const response = await fetch(`${DIRECTUS_URL}/users/me?fields=id,email,first_name,last_name`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) return null;
  const body = await response.json();
  if (!body?.data?.id) return null;
  // Deliberately NOT `{ ...body.data, accessToken: token }`: this object
  // reaches the browser verbatim via GET /api/me and req.user in several
  // JSON responses. The whole point of the HttpOnly session cookie is that
  // client-side JS can never read the Directus access token; echoing it
  // back in a JSON body would defeat that. The cookie itself (read via
  // parseCookies, above) is the only thing that should ever carry it.
  return { ...body.data };
}

// Which organization a Directus-authenticated request is acting as. An
// explicit x-organization-id header (sent once welcome.html's org switcher
// has a selection) is validated against real membership; with no header, the
// user's earliest membership is the default -- the same "pick something
// reasonable" fallback demo mode already uses for x-demo-organization.
async function resolveOrganizationForUser(directusUserId, requestedOrganizationId) {
  if (requestedOrganizationId) {
    const result = await pool.query(
      `SELECT organization_id, role FROM organization_members WHERE directus_user_id = $1 AND organization_id = $2`,
      [directusUserId, requestedOrganizationId],
    );
    return result.rows[0] || null;
  }
  const result = await pool.query(
    `SELECT organization_id, role FROM organization_members WHERE directus_user_id = $1 ORDER BY created_at ASC LIMIT 1`,
    [directusUserId],
  );
  return result.rows[0] || null;
}

async function resolveIdentity(req) {
  if (PHASE1_IDENTITY_MODE === 'directus') {
    const user = await directusUser(req);
    if (!user) return null;
    const membership = await resolveOrganizationForUser(user.id, req.header('x-organization-id') || null);
    if (membership) return { organizationId: membership.organization_id, user, role: membership.role };
    // Legacy fallback: explicit opt-in only (see ALLOW_LEGACY_ORG_FALLBACK
    // above), and never grants 'owner' -- a user with no real membership row
    // gets read/write access to the fallback organization but not billing or
    // membership-management rights (requireOrganizationMembership, used by
    // the billing routes, does not consult this fallback at all -- it
    // requires a real organization_members row unconditionally).
    if (ALLOW_LEGACY_ORG_FALLBACK && DIRECTUS_ORGANIZATION_ID) {
      return { organizationId: DIRECTUS_ORGANIZATION_ID, user, role: 'member' };
    }
    return null;
  }
  const organizationId = requestIsLoopback(req) && (req.header('x-demo-organization') || 'demo-humanitarian-lab');
  return organizationId ? { organizationId, user: null, role: 'owner' } : null;
}

async function requireIdentity(req, res, next) {
  try {
    const resolved = await resolveIdentity(req);
    if (!resolved) return res.status(401).json({ error: 'Authentication required' });
    req.organizationId = resolved.organizationId;
    req.user = resolved.user;
    req.role = resolved.role || 'owner';
    next();
  } catch (error) {
    res.status(401).json({ error: 'Authentication required' });
  }
}

// Session-only middleware: requires a valid identity but NOT organization
// membership -- unlike requireIdentity, a Directus user with zero
// organizations yet still reaches routes guarded by this (list/create
// organization) instead of being 401'd before they can create their first one.
async function requireUser(req, res, next) {
  if (PHASE1_IDENTITY_MODE === 'directus') {
    try {
      const user = await directusUser(req);
      if (!user) return res.status(401).json({ error: 'Authentication required' });
      req.directusUser = user;
      return next();
    } catch (error) {
      return res.status(401).json({ error: 'Authentication required' });
    }
  }
  const organizationId = requestIsLoopback(req) && (req.header('x-demo-organization') || 'demo-humanitarian-lab');
  if (!organizationId) return res.status(401).json({ error: 'Authentication required' });
  req.directusUser = null;
  req.demoOrganizationId = organizationId;
  next();
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
const HDX_IMPORT_MAX_COMPRESSION_RATIO = 100;
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
    if (dataEnd > buffer.length || uncompressedSize > HDX_IMPORT_MAX_BYTES || (compressedSize === 0 ? uncompressedSize > 0 : uncompressedSize / compressedSize > HDX_IMPORT_MAX_COMPRESSION_RATIO)) throw new Error('HDX ZIP entry exceeds the import expansion limit');
    if (/\.geojson$|\.json$/i.test(name)) {
      let content;
      if (method === 0) content = buffer.subarray(dataStart, dataEnd);
      else if (method === 8) content = require('node:zlib').inflateRawSync(buffer.subarray(dataStart, dataEnd), { maxOutputLength: HDX_IMPORT_MAX_BYTES });
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
    const operation = 'create_review_output';
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

function normalizeDigitizingFeature(body = {}) {
  const geometry = body.geometry;
  if (!geometry || !['Point', 'LineString', 'Polygon'].includes(geometry.type)) throw new Error('geometry must be a GeoJSON Point, LineString, or Polygon');
  const isPosition = value => Array.isArray(value) && value.length >= 2 && value.slice(0, 2).every(Number.isFinite)
    && value[0] >= -180 && value[0] <= 180 && value[1] >= -90 && value[1] <= 90;
  if (geometry.type === 'Point') {
    if (!isPosition(geometry.coordinates)) throw new Error('Geometry has invalid coordinates');
  } else if (geometry.type === 'LineString') {
    if (!Array.isArray(geometry.coordinates) || geometry.coordinates.length < 2) throw new Error('LineString must contain at least 2 coordinate positions');
    if (!geometry.coordinates.every(isPosition)) throw new Error('Geometry has invalid coordinates');
  } else {
    if (!Array.isArray(geometry.coordinates) || geometry.coordinates.length === 0) throw new Error('Polygon must contain at least one ring');
    for (const ring of geometry.coordinates) {
      if (!Array.isArray(ring) || ring.length < 4 || !ring.every(isPosition)) throw new Error('Polygon ring must contain at least 4 valid positions');
      const first = ring[0]; const last = ring[ring.length - 1];
      if (first[0] !== last[0] || first[1] !== last[1]) throw new Error('Polygon ring must be a closed ring');
    }
  }
  if (!body.properties || typeof body.properties !== 'object' || Array.isArray(body.properties)) throw new Error('properties must be an object');
  return { geometry, properties: body.properties };
}

function normalizeGeometryOperation(body = {}) {
  const source = body.parameters && typeof body.parameters === 'object' && !Array.isArray(body.parameters)
    ? { ...body.parameters, ...body } : body;
  const operation = String(source.operation || source.type || '').trim().toLowerCase().replace(/[- ]/g, '_');
  const number = (value, field, { integer = false } = {}) => {
    const parsed = typeof value === 'number' ? value : (typeof value === 'string' && value.trim() ? Number(value) : NaN);
    if (!Number.isFinite(parsed) || (integer && !Number.isInteger(parsed))) throw new Error(`${field} must be a finite ${integer ? 'integer' : 'number'}`);
    return parsed;
  };
  const position = value => {
    if (!Array.isArray(value) || value.length < 2 || !value.slice(0, 2).every(Number.isFinite)) throw new Error('origin must be a coordinate position');
    return [Number(value[0]), Number(value[1])];
  };
  const coordinateList = (value, field, { closed = false } = {}) => {
    if (!Array.isArray(value) || value.length < (closed ? 4 : 2) || !value.every(item => Array.isArray(item) && item.length >= 2 && item.slice(0, 2).every(Number.isFinite) && item[0] >= -180 && item[0] <= 180 && item[1] >= -90 && item[1] <= 90)) throw new Error(`${field} must be a valid ${closed ? 'closed ring' : 'coordinate list'}`);
    if (closed && (value[0][0] !== value[value.length - 1][0] || value[0][1] !== value[value.length - 1][1])) throw new Error(`${field} must be closed`);
    return value.map(item => item.slice());
  };
  const geometry = (value, field) => {
    try { return normalizeFeatureCollection({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: value, properties: {} }] })[0].geometry; }
    catch (error) { throw new Error(`${field} is invalid: ${error.message}`); }
  };
  if (!['move', 'rotate', 'scale', 'reverse', 'simplify', 'offset', 'trim', 'extend', 'trim_extend', 'split', 'add_ring', 'delete_ring', 'add_part', 'delete_part', 'reshape', 'feature_array'].includes(operation)) throw new Error(`Unsupported geometry operation: ${operation || 'unknown'}`);
  if (operation === 'reverse') return { operation };
  if (operation === 'move') return { operation, dx: number(source.dx ?? source.delta_x, 'dx'), dy: number(source.dy ?? source.delta_y, 'dy') };
  if (operation === 'rotate') return { operation, angle: number(source.angle ?? source.degrees, 'angle'), origin: position(source.origin || [0, 0]) };
  if (operation === 'scale') {
    const factor = number(source.factor, 'factor');
    if (factor <= 0 || factor > 1000) throw new Error('factor must be greater than 0 and at most 1000');
    return { operation, factor, origin: position(source.origin || [0, 0]) };
  }
  if (operation === 'simplify') {
    const tolerance = number(source.tolerance, 'tolerance');
    if (tolerance <= 0 || tolerance > 180) throw new Error('tolerance must be greater than 0 and at most 180');
    return { operation, tolerance };
  }
  if (operation === 'offset') {
    const distance = number(source.distance ?? source.distance_degrees, 'distance');
    if (distance === 0 || Math.abs(distance) > 180) throw new Error('distance must be non-zero and at most 180 degrees');
    return { operation, distance };
  }
  if (operation === 'trim' || operation === 'extend' || operation === 'trim_extend') {
    const start = number(source.start, 'start', { integer: true });
    const end = number(source.end, 'end', { integer: true });
    if (start < 0 || end <= start) throw new Error('trim/extend requires integer start and end indexes with end greater than start');
    return { operation: operation === 'trim_extend' ? 'trim_extend' : operation, start, end };
  }
  if (operation === 'split') {
    if (source.index == null && source.split_index == null && !source.parts) throw new Error('split requires index for LineString or parts for Polygon');
    if (source.parts !== undefined) {
      if (!Array.isArray(source.parts) || source.parts.length < 2) throw new Error('split parts must contain at least two Polygon parts');
      return { operation, parts: source.parts.map((part, index) => geometry(part && part.type === 'Polygon' ? part : { type: 'Polygon', coordinates: Array.isArray(part) && Array.isArray(part[0]) && Array.isArray(part[0][0]) ? part : [part] }, `parts[${index}]`)) };
    }
    return { operation, index: number(source.index ?? source.split_index, 'index', { integer: true }) };
  }
  if (operation === 'add_ring') {
    if (source.ring === undefined) throw new Error('add_ring requires ring');
    return { operation, ring: coordinateList(source.ring, 'ring', { closed: true }) };
  }
  if (operation === 'delete_ring' || operation === 'delete_part') {
    return { operation, index: number(source.index, 'index', { integer: true }) };
  }
  if (operation === 'add_part') {
    if (source.part === undefined) throw new Error('add_part requires part');
    return { operation, part: source.part };
  }
  if (operation === 'reshape') {
    if (source.coordinates === undefined) throw new Error('reshape requires coordinates');
    return { operation, coordinates: source.coordinates, ring_index: source.ring_index == null ? 0 : number(source.ring_index, 'ring_index', { integer: true }) };
  }
  if (operation === 'feature_array') {
    if (!Array.isArray(source.geometries) || source.geometries.length < 1) throw new Error('feature_array requires a non-empty geometries array');
    return { operation, geometries: source.geometries.map((item, index) => geometry(item, `geometries[${index}]`)) };
  }
}

function perpendicularDistance(point, lineStart, lineEnd) {
  const [x, y] = point; const [x1, y1] = lineStart; const [x2, y2] = lineEnd;
  const dx = x2 - x1; const dy = y2 - y1;
  if (dx === 0 && dy === 0) return Math.hypot(x - x1, y - y1);
  const t = ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy);
  const clamped = Math.max(0, Math.min(1, t));
  return Math.hypot(x - (x1 + clamped * dx), y - (y1 + clamped * dy));
}

// Ramer-Douglas-Peucker line simplification: keeps a point only if it deviates
// from the straight line between its neighbors by more than `tolerance`
// (same raw coordinate-degree units as the rest of applyGeometryOperation).
// Always keeps the first and last point so the line's endpoints never move.
function douglasPeuckerSimplify(points, tolerance) {
  if (points.length <= 2) return points.map(point => point.slice());
  let maxDistance = 0; let splitIndex = 0;
  const first = points[0]; const last = points[points.length - 1];
  for (let i = 1; i < points.length - 1; i++) {
    const distance = perpendicularDistance(points[i], first, last);
    if (distance > maxDistance) { maxDistance = distance; splitIndex = i; }
  }
  if (maxDistance > tolerance) {
    const left = douglasPeuckerSimplify(points.slice(0, splitIndex + 1), tolerance);
    const right = douglasPeuckerSimplify(points.slice(splitIndex), tolerance);
    return left.slice(0, -1).concat(right);
  }
  return [first.slice(), last.slice()];
}

function applyGeometryOperation(geometry, operation) {
  const op = normalizeGeometryOperation(operation);
  const coordinateList = (value, field, { closed = false } = {}) => {
    if (!Array.isArray(value) || value.length < (closed ? 4 : 2) || !value.every(item => Array.isArray(item) && item.length >= 2 && item.slice(0, 2).every(Number.isFinite) && item[0] >= -180 && item[0] <= 180 && item[1] >= -90 && item[1] <= 90)) throw new Error(`${field} must be a valid ${closed ? 'closed ring' : 'coordinate list'}`);
    if (closed && (value[0][0] !== value[value.length - 1][0] || value[0][1] !== value[value.length - 1][1])) throw new Error(`${field} must be closed`);
    return value.map(item => item.slice());
  };
  const mapPositions = transform => {
    const walk = coordinates => Array.isArray(coordinates) && typeof coordinates[0] === 'number' ? transform(coordinates) : coordinates.map(walk);
    return walk(geometry.coordinates);
  };
  const origin = op.origin || [0, 0];
  const transform = position => {
    const x = position[0]; const y = position[1];
    if (op.operation === 'move') return [x + op.dx, y + op.dy, ...position.slice(2)];
    if (op.operation === 'rotate') { const radians = op.angle * Math.PI / 180; return [origin[0] + (x - origin[0]) * Math.cos(radians) - (y - origin[1]) * Math.sin(radians), origin[1] + (x - origin[0]) * Math.sin(radians) + (y - origin[1]) * Math.cos(radians), ...position.slice(2)]; }
    if (op.operation === 'scale') return [origin[0] + (x - origin[0]) * op.factor, origin[1] + (y - origin[1]) * op.factor, ...position.slice(2)];
    if (op.operation === 'offset') return [x + op.distance, y, ...position.slice(2)];
    return position.slice();
  };
  let result = { type: geometry.type, coordinates: geometry.coordinates };
  if (['move', 'rotate', 'scale', 'offset'].includes(op.operation)) result = { ...geometry, coordinates: mapPositions(transform) };
  else if (op.operation === 'reverse') {
    if (geometry.type === 'Point') throw new Error('reverse is not supported for Point geometry');
    const reverse = coordinates => Array.isArray(coordinates) && typeof coordinates[0] === 'number' ? coordinates.slice() : coordinates.slice().reverse().map(reverse);
    result = { ...geometry, coordinates: reverse(geometry.coordinates) };
  } else if (op.operation === 'simplify') {
    if (!['LineString', 'MultiLineString'].includes(geometry.type)) throw new Error('simplify is supported only for line geometry');
    const simplify = points => douglasPeuckerSimplify(points, op.tolerance);
    result = { ...geometry, coordinates: geometry.type === 'LineString' ? simplify(geometry.coordinates) : geometry.coordinates.map(simplify) };
  } else if (['trim', 'extend', 'trim_extend'].includes(op.operation)) {
    if (geometry.type !== 'LineString') throw new Error('trim/extend is supported only for LineString geometry');
    const coordinates = geometry.coordinates.slice(op.start, Math.min(op.end, geometry.coordinates.length));
    if (coordinates.length < 2) throw new Error('trim/extend would produce an invalid LineString');
    result = { ...geometry, coordinates };
  } else if (op.operation === 'split') {
    if (geometry.type === 'LineString') {
      if (op.index < 1 || op.index >= geometry.coordinates.length - 1) throw new Error('split index must leave at least 2 positions in each LineString');
      result = { type: 'MultiLineString', coordinates: [geometry.coordinates.slice(0, op.index + 1), geometry.coordinates.slice(op.index)] };
    } else if (geometry.type === 'Polygon') {
      if (!op.parts) throw new Error('Polygon split requires explicit Polygon parts');
      result = { type: 'MultiPolygon', coordinates: op.parts.map(part => part.coordinates) };
    } else throw new Error('split is supported only for LineString or Polygon geometry');
  } else if (op.operation === 'add_ring') {
    if (geometry.type !== 'Polygon') throw new Error('add_ring is supported only for Polygon geometry');
    result = { ...geometry, coordinates: [...geometry.coordinates, op.ring] };
  } else if (op.operation === 'delete_ring') {
    if (geometry.type !== 'Polygon') throw new Error('delete_ring is supported only for Polygon geometry');
    if (op.index < 1 || op.index >= geometry.coordinates.length) throw new Error('delete_ring index must identify an interior ring');
    result = { ...geometry, coordinates: geometry.coordinates.filter((_ring, index) => index !== op.index) };
  } else if (op.operation === 'add_part') {
    if (geometry.type === 'MultiLineString') result = { ...geometry, coordinates: [...geometry.coordinates, coordinateList(op.part, 'part')] };
    else if (geometry.type === 'MultiPolygon') result = { ...geometry, coordinates: [...geometry.coordinates, (Array.isArray(op.part) && Array.isArray(op.part[0]) && Array.isArray(op.part[0][0]) ? op.part : [op.part])] };
    else throw new Error('add_part is supported only for MultiLineString or MultiPolygon geometry');
  } else if (op.operation === 'delete_part') {
    if (!['MultiLineString', 'MultiPolygon'].includes(geometry.type)) throw new Error('delete_part is supported only for multi-part geometry');
    if (op.index < 0 || op.index >= geometry.coordinates.length || geometry.coordinates.length < 2) throw new Error('delete_part index must identify a part and leave at least one part');
    result = { ...geometry, coordinates: geometry.coordinates.filter((_part, index) => index !== op.index) };
  } else if (op.operation === 'reshape') {
    if (geometry.type === 'LineString') result = { ...geometry, coordinates: coordinateList(op.coordinates, 'coordinates') };
    else if (geometry.type === 'Polygon') {
      const ringIndex = op.ring_index == null ? 0 : op.ring_index;
      if (!Number.isInteger(ringIndex) || ringIndex < 0 || ringIndex >= geometry.coordinates.length) throw new Error('reshape ring_index is invalid');
      const coordinates = geometry.coordinates.map((ring, index) => index === ringIndex ? coordinateList(op.coordinates, 'coordinates', { closed: true }) : ring);
      result = { ...geometry, coordinates };
    } else throw new Error('reshape is supported only for LineString or Polygon geometry');
  } else if (op.operation === 'feature_array') {
    const types = new Set(op.geometries.map(item => item.type));
    if (types.size !== 1) throw new Error('feature_array geometries must all have the same type');
    const type = [...types][0];
    const multiType = { Point: 'MultiPoint', LineString: 'MultiLineString', Polygon: 'MultiPolygon' }[type];
    if (!multiType) throw new Error('feature_array supports only Point, LineString, or Polygon geometries');
    result = { type: multiType, coordinates: op.geometries.map(item => item.coordinates) };
  }
  try { return normalizeFeatureCollection({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: result, properties: {} }] })[0].geometry; }
  catch (error) { throw new Error(`geometry operation produced invalid geometry: ${error.message}`); }
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
  const hasGeometryOperation = Object.prototype.hasOwnProperty.call(body, 'geometry_operation');
  if (!hasProperties && !hasGeometry && !hasGeometryOperation) throw new Error('properties, geometry, or geometry_operation is required');
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
  let geometryOperation;
  if (hasGeometryOperation) {
    try { geometryOperation = normalizeGeometryOperation(body.geometry_operation); }
    catch (error) { throw new Error(`geometry_operation is invalid: ${error.message}`); }
  }
  if (hasGeometry && hasGeometryOperation) throw new Error('geometry and geometry_operation cannot be supplied together');
  if (mode === 'apply' && body.approved !== true) throw new Error('approved must be true before applying a feature edit');
  const beforeHash = body.before_hash == null ? null : String(body.before_hash).trim();
  if (beforeHash && !/^[a-f0-9]{64}$/i.test(beforeHash)) throw new Error('before_hash must be a SHA-256 hash');
  return { mode, approved: body.approved === true, properties, geometry, geometry_operation: geometryOperation, before_hash: beforeHash, preview_token: body.preview_token ? String(body.preview_token) : null };
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
  const geometry = edit.geometry_operation ? applyGeometryOperation(before.geometry, edit.geometry_operation) : (edit.geometry === undefined ? before.geometry : edit.geometry);
  return { geometry, properties: edit.properties === undefined ? before.properties : edit.properties };
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

// The public contract for spatial analysis operations. Keep this registry free of
// organization or user state so it can safely power API discovery and clients.
const OPERATION_REGISTRY = Object.freeze({
  create_review_output: Object.freeze({
    display_name: 'Create review output',
    parameter_types: Object.freeze({ include_layers: 'boolean' }),
    required_fields: Object.freeze([]),
    read_only: true,
    schedulable: true,
    executor_id: 'review_output',
  }),
  buffer_layer: Object.freeze({
    display_name: 'Buffer layer',
    parameter_types: Object.freeze({ source_layer_id: 'string', distance_meters: 'number' }),
    required_fields: Object.freeze(['source_layer_id', 'distance_meters']),
    read_only: false,
    schedulable: false,
    executor_id: 'buffer_layer',
  }),
  intersect_layers: Object.freeze({
    display_name: 'Intersect layers',
    parameter_types: Object.freeze({ source_layer_id: 'string', overlay_layer_id: 'string' }),
    required_fields: Object.freeze(['source_layer_id', 'overlay_layer_id']),
    read_only: false,
    schedulable: false,
    executor_id: 'intersect_layers',
  }),
});

function normalizeAnalysisOperationInput(operation, input = {}) {
  const operationId = String(operation || '').trim();
  const definition = OPERATION_REGISTRY[operationId];
  if (!definition) throw new Error(`Unsupported analysis operation: ${operationId || 'unknown'}`);
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error(`Invalid parameters for operation ${operationId}`);
  for (const field of definition.required_fields) {
    if (input[field] === undefined || input[field] === null || input[field] === '') {
      throw new Error(`Invalid parameters for operation ${operationId}: ${field} is required`);
    }
  }
  const normalized = {};
  for (const [field, type] of Object.entries(definition.parameter_types)) {
    if (input[field] === undefined) continue;
    const value = input[field];
    if (type === 'string') {
      if (typeof value !== 'string' || !value.trim()) throw new Error(`Invalid parameters for operation ${operationId}: ${field} must be a string`);
      normalized[field] = value.trim();
    } else if (type === 'number') {
      const number = typeof value === 'number' ? value : (typeof value === 'string' && value.trim() ? Number(value) : NaN);
      if (!Number.isFinite(number)) throw new Error(`Invalid parameters for operation ${operationId}: ${field} must be a number`);
      normalized[field] = number;
    } else if (type === 'boolean') {
      if (typeof value !== 'boolean') throw new Error(`Invalid parameters for operation ${operationId}: ${field} must be a boolean`);
      normalized[field] = value;
    }
  }
  if (operationId === 'intersect_layers' && normalized.source_layer_id === normalized.overlay_layer_id) {
    throw new Error('Invalid parameters for operation intersect_layers: source and overlay layers must be different');
  }
  if (operationId === 'buffer_layer' && (normalized.distance_meters <= 0 || normalized.distance_meters > 100000)) {
    throw new Error('Invalid parameters for operation buffer_layer: distance_meters must be between 0 and 100000');
  }
  return normalized;
}

function normalizeIntersectionInput(input = {}) {
  return normalizeAnalysisOperationInput('intersect_layers', input);
}

function normalizeLayerCrs(value) {
  if (value === undefined || value === null) return null;
  const crs = String(value).trim().toUpperCase().replace(/\s+/g, '');
  return crs || null;
}

function spatialLayerCrs(layer) {
  return normalizeLayerCrs(layer?.crs || layer?.coordinate_reference_system || layer?.metadata?.crs || layer?.project_crs || 'EPSG:4326');
}

function spatialGeometryTypes(layer) {
  const values = layer?.geometry_types || layer?.geometry_type || [];
  return [...new Set((Array.isArray(values) ? values : [values]).filter(Boolean).map(value => String(value).replace(/^ST_/, '')))].sort();
}

function diagnoseSpatialCompatibility({ source, overlay = null } = {}) {
  const sourceCrs = spatialLayerCrs(source);
  const overlayCrs = overlay ? spatialLayerCrs(overlay) : null;
  const sourceTypes = spatialGeometryTypes(source);
  const overlayTypes = spatialGeometryTypes(overlay);
  const geometryTypes = [...new Set([...sourceTypes, ...overlayTypes])].sort();
  const invalidGeometryCount = Number(source?.invalid_geometry_count || 0) + Number(overlay?.invalid_geometry_count || 0);
  const warnings = [];
  if (invalidGeometryCount > 0) warnings.push(`${invalidGeometryCount} invalid geometr${invalidGeometryCount === 1 ? 'y' : 'ies'} detected; topology operations may fail`);
  if (sourceTypes.length > 1 || overlayTypes.length > 1 || (sourceTypes.length && overlayTypes.length && sourceTypes.join('|') !== overlayTypes.join('|'))) {
    warnings.push(`mixed geometry types detected: ${geometryTypes.join(', ') || 'unknown'}`);
  }
  if (source?.geometry_srid && overlay?.geometry_srid && String(source.geometry_srid) !== String(overlay.geometry_srid)) {
    warnings.push(`geometry SRID differs (${source.geometry_srid} vs ${overlay.geometry_srid})`);
  }
  return {
    compatible: !overlay || sourceCrs === overlayCrs,
    source_crs: sourceCrs,
    overlay_crs: overlayCrs,
    geometry_types: geometryTypes,
    source_geometry_types: sourceTypes,
    overlay_geometry_types: overlayTypes,
    invalid_geometry_count: invalidGeometryCount,
    warnings,
  };
}

function spatialCompatibilityError(code, message, details) {
  const error = new Error(message);
  error.code = code;
  error.statusCode = 400;
  error.safe = true;
  error.details = details;
  return error;
}

function assertSpatialCompatibility(diagnosis) {
  if (diagnosis?.overlay_crs && diagnosis.source_crs !== diagnosis.overlay_crs) {
    throw spatialCompatibilityError('SPATIAL_CRS_MISMATCH', 'Source and overlay layers use incompatible coordinate reference systems', {
      source_crs: diagnosis.source_crs,
      overlay_crs: diagnosis.overlay_crs,
    });
  }
  if (Number(diagnosis?.invalid_geometry_count || 0) > 0) {
    throw spatialCompatibilityError('SPATIAL_INVALID_GEOMETRY', 'Spatial operation requires valid geometries', {
      invalid_geometry_count: diagnosis.invalid_geometry_count,
      warnings: diagnosis.warnings,
    });
  }
  return diagnosis;
}

async function inspectSpatialLayers({ projectId, organizationId, layerIds }) {
  const result = await pool.query(
    `SELECT l.id, l.name, l.metadata, p.crs AS project_crs,
            COALESCE(l.metadata->>'crs', l.metadata->>'coordinate_reference_system', p.crs, 'EPSG:4326') AS crs,
            COALESCE(array_agg(DISTINCT regexp_replace(ST_GeometryType(f.geometry), '^ST_', '')) FILTER (WHERE f.id IS NOT NULL), ARRAY[]::text[]) AS geometry_types,
            COALESCE(array_agg(DISTINCT ST_SRID(f.geometry)) FILTER (WHERE f.id IS NOT NULL), ARRAY[]::int[]) AS geometry_srids,
            COUNT(f.id) FILTER (WHERE f.id IS NOT NULL AND NOT ST_IsValid(f.geometry))::int AS invalid_geometry_count
       FROM project_layers l JOIN projects p ON p.id = l.project_id AND p.organization_id = l.organization_id
       LEFT JOIN project_layer_features f ON f.layer_id = l.id AND f.project_id = l.project_id AND f.organization_id = l.organization_id
      WHERE l.id = ANY($1::uuid[]) AND l.project_id = $2 AND l.organization_id = $3
      GROUP BY l.id, p.crs`,
    [layerIds, projectId, organizationId],
  );
  return result.rows.map(row => ({ ...row, geometry_srid: row.geometry_srids?.length === 1 ? row.geometry_srids[0] : null }));
}

function isSupportedAnalysisOperation(operation) {
  return Object.prototype.hasOwnProperty.call(OPERATION_REGISTRY, String(operation || '').trim());
}

const SCHEDULE_MIN_INTERVAL_SECONDS = 60;

function isAllowedScheduledOperation(operation) {
  const definition = OPERATION_REGISTRY[String(operation || '').trim()];
  return Boolean(definition?.read_only && definition.schedulable);
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

const LAYER_STYLE_DEFAULTS = { preset: 'coverage', color: '#d96a54', fill_opacity: 55, line_weight: 2, classification: 'DRAFT · REVIEW REQUIRED', legend_label: null };
function normalizeLayerStyle(body = {}) {
  const input = body.style && typeof body.style === 'object' && !Array.isArray(body.style) ? body.style : body;
  const preset = String(input.preset ?? input.style_preset ?? LAYER_STYLE_DEFAULTS.preset);
  if (!['coverage', 'facilities', 'accessibility', 'risk'].includes(preset)) throw new Error('preset must be coverage, facilities, accessibility, or risk');
  const color = String(input.color ?? input.style_color ?? LAYER_STYLE_DEFAULTS.color).toLowerCase();
  if (!/^#[0-9a-f]{6}$/.test(color)) throw new Error('color must be a six-digit hexadecimal color');
  const fill_opacity = Number(input.fill_opacity ?? input.style_fill_opacity ?? LAYER_STYLE_DEFAULTS.fill_opacity);
  if (!Number.isFinite(fill_opacity) || fill_opacity < 0 || fill_opacity > 100) throw new Error('fill_opacity must be between 0 and 100');
  const line_weight = Number(input.line_weight ?? input.style_line_weight ?? LAYER_STYLE_DEFAULTS.line_weight);
  if (!Number.isFinite(line_weight) || line_weight <= 0 || line_weight > 20) throw new Error('line_weight must be greater than 0 and at most 20');
  const classification = String(input.classification ?? input.style_classification ?? LAYER_STYLE_DEFAULTS.classification).trim().slice(0, 120);
  const legend_label = input.legend_label == null ? (input.style_legend_label == null ? LAYER_STYLE_DEFAULTS.legend_label : String(input.style_legend_label).trim().slice(0, 255)) : String(input.legend_label).trim().slice(0, 255);
  if (!classification) throw new Error('classification must not be empty');
  if (legend_label === '') throw new Error('legend_label must not be empty');
  return { preset, color, fill_opacity, line_weight, classification, legend_label: legend_label || null };
}

function layerStyleFromRow(row = {}) {
  return normalizeLayerStyle({ preset: row.style_preset, color: row.style_color, fill_opacity: row.style_fill_opacity, line_weight: row.style_line_weight, classification: row.style_classification, legend_label: row.style_legend_label });
}

app.get('/api/auth/status', async (req, res) => {
  const resolved = await resolveIdentity(req).catch(() => null);
  res.json({ authenticated: Boolean(resolved), mode: PHASE1_IDENTITY_MODE, organization_configured: Boolean(DIRECTUS_ORGANIZATION_ID), providers: plannerProviderStatus() });
});

// ---------------------------------------------------------------------------
// Directus session login/registration. The website never sees or stores a
// password itself -- it forwards to Directus's own /auth/login and /users/register,
// then holds only the resulting Directus access token, in an HttpOnly cookie
// the browser's JS can't read. Mirrors service/website/auth.js's contract
// exactly (same cookie name, same field set) so the same Directus instance
// can serve both the QGIS-plugin portal and this workspace.
// ---------------------------------------------------------------------------

async function directusLogin(email, password) {
  const response = await fetch(`${DIRECTUS_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body?.errors?.[0]?.message || 'Login failed');
    error.statusCode = response.status === 401 ? 401 : 400;
    throw error;
  }
  return body.data;
}

async function directusRegister({ email, password, first_name, last_name }) {
  const response = await fetch(`${DIRECTUS_URL}/users/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, first_name, last_name }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body?.errors?.[0]?.message || 'Registration failed');
    error.statusCode = response.status === 401 ? 401 : 400;
    throw error;
  }
  return body.data;
}

function setSessionCookie(res, accessToken) {
  res.cookie(DIRECTUS_COOKIE, accessToken, {
    httpOnly: true,
    sameSite: 'lax',
    secure: NODE_ENV === 'production',
    maxAge: 24 * 60 * 60 * 1000,
    path: '/',
  });
}

function clearSessionCookie(res) {
  res.clearCookie(DIRECTUS_COOKIE, { path: '/' });
}

app.post('/api/auth/login', authRateLimit, async (req, res) => {
  if (PHASE1_IDENTITY_MODE !== 'directus') return res.status(400).json({ error: 'Login is only available in directus identity mode' });
  const email = String(req.body?.email || '').trim();
  const password = String(req.body?.password || '');
  if (!email || !password) return res.status(400).json({ error: 'email and password are required' });
  try {
    const result = await directusLogin(email, password);
    setSessionCookie(res, result.access_token);
    res.json({ ok: true });
  } catch (error) {
    res.status(error.statusCode || 400).json({ error: error.message });
  }
});

app.post('/api/auth/register', authRateLimit, async (req, res) => {
  if (PHASE1_IDENTITY_MODE !== 'directus') return res.status(400).json({ error: 'Registration is only available in directus identity mode' });
  const email = String(req.body?.email || '').trim();
  const password = String(req.body?.password || '');
  const firstName = String(req.body?.first_name || '');
  const lastName = String(req.body?.last_name || '');
  if (!email || password.length < 12) return res.status(400).json({ error: 'email and a password of at least 12 characters are required' });
  try {
    await directusRegister({ email, password, first_name: firstName, last_name: lastName });
    try {
      const result = await directusLogin(email, password);
      setSessionCookie(res, result.access_token);
      res.status(201).json({ ok: true });
    } catch (loginError) {
      if (loginError.statusCode === 401) {
        return res.status(202).json({ ok: true, verification_required: true, message: 'Registration succeeded. Activate the account or wait for approval, then sign in.' });
      }
      throw loginError;
    }
  } catch (error) {
    res.status(error.statusCode || 400).json({ error: error.message });
  }
});

app.post('/api/auth/logout', (req, res) => {
  clearSessionCookie(res);
  res.json({ ok: true });
});

// Directus's own password-reset flow, proxied the same way login/register
// are: the request/reset tokens and the actual password never pass through
// anything this app stores, and Directus itself emails the reset link.
// Always returns ok:true on /request regardless of whether the email exists
// -- an "unknown email" response would let an attacker enumerate registered
// accounts, which the login/register error messages above already avoid by
// only ever surfacing Directus's own generic failure text.
app.post('/api/auth/password/request', authRateLimit, async (req, res) => {
  if (PHASE1_IDENTITY_MODE !== 'directus') return res.status(400).json({ error: 'Password reset is only available in directus identity mode' });
  const email = String(req.body?.email || '').trim();
  if (!email) return res.status(400).json({ error: 'email is required' });
  const resetUrl = PUBLIC_BASE_URL ? `${PUBLIC_BASE_URL}/login.html?reset=1` : undefined;
  try {
    await fetch(`${DIRECTUS_URL}/auth/password/request`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(resetUrl ? { email, reset_url: resetUrl } : { email }),
    });
  } catch (error) {
    console.error('Directus password reset request failed:', error.message);
  }
  res.json({ ok: true });
});

app.post('/api/auth/password/reset', authRateLimit, async (req, res) => {
  if (PHASE1_IDENTITY_MODE !== 'directus') return res.status(400).json({ error: 'Password reset is only available in directus identity mode' });
  const token = String(req.body?.token || '');
  const password = String(req.body?.password || '');
  if (!token || password.length < 12) return res.status(400).json({ error: 'token and a password of at least 12 characters are required' });
  try {
    const response = await fetch(`${DIRECTUS_URL}/auth/password/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      return res.status(400).json({ error: body?.errors?.[0]?.message || 'Password reset failed' });
    }
    res.json({ ok: true });
  } catch (error) {
    console.error('Directus password reset failed:', error.message);
    res.status(502).json({ error: 'Password reset service unavailable' });
  }
});

app.get('/api/me', requireUser, (req, res) => {
  res.json({ user: req.directusUser, mode: PHASE1_IDENTITY_MODE });
});

// ---------------------------------------------------------------------------
// Organizations: list/create. Guarded by requireUser (session only) rather
// than requireIdentity, so a just-registered Directus user with zero
// organizations yet can still reach these and create their first one.
// ---------------------------------------------------------------------------

function normalizeSlug(value) {
  return String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64);
}

function normalizeOrganizationCreateRequest(body = {}) {
  const name = String(body.name || '').trim().slice(0, 255);
  if (!name) throw new Error('name is required');
  const slug = normalizeSlug(body.slug || name);
  if (!slug) throw new Error('A usable slug could not be derived from name');
  return { name, slug };
}

app.get('/api/organizations', requireUser, async (req, res) => {
  if (PHASE1_IDENTITY_MODE === 'directus') {
    const result = await pool.query(
      `SELECT o.id, o.name, o.slug, om.role
         FROM organization_members om JOIN organizations o ON o.id = om.organization_id
        WHERE om.directus_user_id = $1
        ORDER BY om.created_at ASC`,
      [req.directusUser.id],
    );
    return res.json({ organizations: result.rows });
  }
  const result = await pool.query(`SELECT id, name, slug FROM organizations WHERE id = $1`, [req.demoOrganizationId]);
  const organizations = result.rowCount
    ? result.rows.map(row => ({ ...row, role: 'owner' }))
    : [{ id: req.demoOrganizationId, name: req.demoOrganizationId, slug: req.demoOrganizationId, role: 'owner' }];
  res.json({ organizations });
});

app.post('/api/organizations', requireUser, async (req, res) => {
  if (PHASE1_IDENTITY_MODE !== 'directus') return res.status(400).json({ error: 'Organization creation requires directus identity mode' });
  let input;
  try { input = normalizeOrganizationCreateRequest(req.body || {}); }
  catch (error) { return res.status(400).json({ error: error.message }); }
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const org = await client.query(
      `INSERT INTO organizations (id, name, slug) VALUES ($1,$2,$3) RETURNING id, name, slug, created_at`,
      [input.slug, input.name, input.slug],
    );
    await client.query(`INSERT INTO organization_members (organization_id, directus_user_id, role) VALUES ($1,$2,'owner')`, [org.rows[0].id, req.directusUser.id]);
    await client.query(`INSERT INTO organization_billing (organization_id, stripe_subscription_status) VALUES ($1,'none')`, [org.rows[0].id]);
    await client.query('COMMIT');
    res.status(201).json({ organization: { ...org.rows[0], role: 'owner' } });
  } catch (error) {
    await client.query('ROLLBACK');
    const duplicate = error.code === '23505';
    // error.message can carry raw Postgres internals (constraint/column
    // names, sometimes query fragments) -- log it server-side, but the
    // client only ever needs to know whether the slug collided.
    if (!duplicate) console.error('Organization creation failed:', error.message);
    res.status(duplicate ? 409 : 400).json({ error: duplicate ? 'That organization slug is already taken' : 'Organization creation failed' });
  } finally { client.release(); }
});

// ---------------------------------------------------------------------------
// Project creation. GET /api/projects has existed since Phase 1's first cut;
// there was never a POST to match it, so the only way a project ever existed
// was the seed script -- welcome.html's "create a new project" flow needs this.
// ---------------------------------------------------------------------------

function normalizeProjectCreateRequest(body = {}) {
  const id = normalizeSlug(body.id || body.name);
  if (!id) throw new Error('id (or a name a slug can be derived from) is required');
  const name = String(body.name || id).trim().slice(0, 255);
  if (!name) throw new Error('name is required');
  const sector = String(body.sector || 'general').trim().slice(0, 120) || 'general';
  const crs = String(body.crs || 'EPSG:4326').trim().slice(0, 64) || 'EPSG:4326';
  const metadata = body.metadata && typeof body.metadata === 'object' && !Array.isArray(body.metadata) ? body.metadata : {};
  return { id, name, sector, crs, metadata };
}

app.post('/api/projects', requireIdentity, async (req, res) => {
  let input;
  try { input = normalizeProjectCreateRequest(req.body || {}); }
  catch (error) { return res.status(400).json({ error: error.message }); }
  try {
    const result = await pool.query(
      `INSERT INTO projects (id, organization_id, name, sector, crs, status, metadata)
       VALUES ($1,$2,$3,$4,$5,'draft',$6)
       RETURNING id, name, sector, crs, status, metadata, created_at, updated_at`,
      [input.id, req.organizationId, input.name, input.sector, input.crs, input.metadata],
    );
    res.status(201).json({ project: result.rows[0] });
  } catch (error) {
    const duplicate = error.code === '23505';
    if (!duplicate) console.error('Project creation failed:', error.message);
    res.status(duplicate ? 409 : 400).json({ error: duplicate ? 'A project with that id already exists' : 'Project creation failed' });
  }
});

// ---------------------------------------------------------------------------
// Billing: LiteLLM virtual-key credit read, Stripe Checkout, Stripe billing
// portal, and the Stripe webhook (registered earlier, before express.json(),
// for raw-body signature verification). One Stripe subscription and one
// LiteLLM virtual key per organization -- the same "one plan" shape
// service/website/server.js already uses per QGIS-plugin user, rescoped here
// to an organization. Stripe env vars unset simply means these routes report
// 503 "not configured" rather than the server failing to boot.
// ---------------------------------------------------------------------------

async function issueLiteLlmVirtualKey({ organizationId, organizationName }) {
  if (!LITELLM_MASTER_KEY) throw new Error('LITELLM_MASTER_KEY is not configured');
  const response = await fetch(`${LITELLM_URL}/key/generate`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${LITELLM_MASTER_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      max_budget: LITELLM_PLAN_MAX_BUDGET_USD,
      budget_duration: '30d',
      metadata: { organization_id: organizationId, organization_name: organizationName },
    }),
  });
  if (!response.ok) throw new Error(`LiteLLM /key/generate failed (${response.status}): ${await response.text()}`);
  const body = await response.json();
  return { key: body.key, keyId: body.token || body.key_name || null };
}

async function setLiteLlmKeyBlocked(virtualKey, blocked) {
  if (!LITELLM_MASTER_KEY || !virtualKey) return;
  const response = await fetch(`${LITELLM_URL}${blocked ? '/key/block' : '/key/unblock'}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${LITELLM_MASTER_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: virtualKey }),
  });
  if (!response.ok) throw new Error(`LiteLLM key ${blocked ? 'block' : 'unblock'} failed (${response.status}): ${await response.text()}`);
}

async function readLiteLlmKeyInfo(virtualKey) {
  if (!LITELLM_MASTER_KEY || !virtualKey) return null;
  const response = await fetch(`${LITELLM_URL}/key/info?key=${encodeURIComponent(virtualKey)}`, {
    headers: { Authorization: `Bearer ${LITELLM_MASTER_KEY}` },
  });
  if (!response.ok) return null;
  const body = await response.json();
  const info = body.info || body;
  const spend = Number(info.spend || 0);
  const maxBudget = info.max_budget == null ? null : Number(info.max_budget);
  return { spend, max_budget: maxBudget, remaining: maxBudget == null ? null : Math.max(0, maxBudget - spend) };
}

async function requireOrganizationMembership(req, res, next) {
  try {
    if (PHASE1_IDENTITY_MODE === 'directus') {
      const user = await directusUser(req);
      if (!user) return res.status(401).json({ error: 'Authentication required' });
      const membership = await resolveOrganizationForUser(user.id, req.params.organizationId);
      if (!membership) return res.status(404).json({ error: 'Organization not found' });
      req.organizationId = membership.organization_id;
      req.user = user;
      req.role = membership.role;
      return next();
    }
    const organizationId = requestIsLoopback(req) && (req.header('x-demo-organization') || 'demo-humanitarian-lab');
    if (!organizationId || organizationId !== req.params.organizationId) return res.status(404).json({ error: 'Organization not found' });
    req.organizationId = organizationId;
    req.user = null;
    req.role = 'owner';
    next();
  } catch (error) {
    res.status(401).json({ error: 'Authentication required' });
  }
}

app.get('/api/organizations/:organizationId/billing', requireOrganizationMembership, async (req, res) => {
  const result = await pool.query(
    `SELECT organization_id, stripe_subscription_status, stripe_price_id, litellm_virtual_key, litellm_max_budget_usd, updated_at
       FROM organization_billing WHERE organization_id = $1`,
    [req.organizationId],
  );
  const billing = result.rows[0] || { stripe_subscription_status: 'none', litellm_virtual_key: null };
  let credit = null;
  if (billing.litellm_virtual_key) {
    try { credit = await readLiteLlmKeyInfo(billing.litellm_virtual_key); }
    catch (error) { credit = null; }
  }
  res.json({
    plan: {
      status: billing.stripe_subscription_status,
      configured: Boolean(stripeClient && STRIPE_PRICE_ID),
      price_id: billing.stripe_price_id || null,
    },
    credit: credit ? { max_budget_usd: credit.max_budget, spent_usd: credit.spend, remaining_usd: credit.remaining } : null,
    updated_at: billing.updated_at || null,
  });
});

app.post('/api/organizations/:organizationId/billing/checkout', requireOrganizationMembership, async (req, res) => {
  if (!stripeClient || !STRIPE_PRICE_ID) return res.status(503).json({ error: 'Stripe is not configured yet' });
  if (!['owner', 'admin'].includes(req.role)) return res.status(403).json({ error: 'Only an organization owner or admin can manage billing' });
  try {
    const existing = await pool.query(`SELECT stripe_customer_id FROM organization_billing WHERE organization_id = $1`, [req.organizationId]);
    const customerId = existing.rows[0]?.stripe_customer_id || null;
    const baseUrl = PUBLIC_BASE_URL || `${req.protocol}://${req.get('host')}`;
    const session = await stripeClient.checkout.sessions.create({
      mode: 'subscription',
      line_items: [{ price: STRIPE_PRICE_ID, quantity: 1 }],
      ...(customerId ? { customer: customerId } : req.user?.email ? { customer_email: req.user.email } : {}),
      client_reference_id: req.organizationId,
      metadata: { organization_id: req.organizationId },
      success_url: `${baseUrl}/welcome.html?checkout=success`,
      cancel_url: `${baseUrl}/welcome.html?checkout=cancelled`,
    });
    res.json({ url: session.url });
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

app.post('/api/organizations/:organizationId/billing/portal', requireOrganizationMembership, async (req, res) => {
  if (!stripeClient) return res.status(503).json({ error: 'Stripe is not configured yet' });
  // The billing portal lets a visitor change payment methods and cancel the
  // subscription -- membership alone isn't enough, same as /billing/checkout.
  if (!['owner', 'admin'].includes(req.role)) return res.status(403).json({ error: 'Only an organization owner or admin can manage billing' });
  const existing = await pool.query(`SELECT stripe_customer_id FROM organization_billing WHERE organization_id = $1`, [req.organizationId]);
  const customerId = existing.rows[0]?.stripe_customer_id;
  if (!customerId) return res.status(404).json({ error: 'No billing customer on file for this organization yet' });
  try {
    const baseUrl = PUBLIC_BASE_URL || `${req.protocol}://${req.get('host')}`;
    const session = await stripeClient.billingPortal.sessions.create({
      customer: customerId,
      return_url: `${baseUrl}/welcome.html`,
      ...(STRIPE_PORTAL_CONFIGURATION_ID ? { configuration: STRIPE_PORTAL_CONFIGURATION_ID } : {}),
    });
    res.json({ url: session.url });
  } catch (error) {
    res.status(400).json({ error: error.message });
  }
});

const STRIPE_ACTIVE_STATUSES = new Set(['active', 'trialing']);
const STRIPE_REVOKED_STATUSES = new Set(['canceled', 'unpaid', 'incomplete_expired', 'past_due']);

async function validateCheckoutSessionPayment(session) {
  if (session?.payment_status !== 'paid') throw new Error('Checkout payment is not paid');
  const subscription = typeof session.subscription === 'object'
    ? session.subscription
    : await stripeClient?.subscriptions.retrieve(session.subscription);
  if (!subscription || !STRIPE_ACTIVE_STATUSES.has(subscription.status)) throw new Error('Checkout subscription is not active');
  return subscription;
}

// Hoisted function declaration -- referenced by app.post('/api/billing/webhook', ...)
// near the top of the file, before this point is reached in file order. Safe:
// function declarations are hoisted with their full body, and Express only
// invokes this later, at request time, by which point the whole module has
// finished loading regardless.
async function handleStripeWebhook(req, res) {
  let event;
  if (stripeClient && STRIPE_WEBHOOK_SECRET) {
    try {
      event = stripeClient.webhooks.constructEvent(req.body, req.headers['stripe-signature'], STRIPE_WEBHOOK_SECRET);
    } catch (error) {
      return res.status(400).send(`Webhook Error: ${error.message}`);
    }
  } else if (ALLOW_UNSIGNED_STRIPE_WEBHOOKS && requestIsLoopback(req)) {
    try { event = JSON.parse(req.body.toString('utf8')); }
    catch { return res.status(400).send('Invalid JSON webhook body'); }
  } else {
    return res.status(400).send('Missing STRIPE_WEBHOOK_SECRET in production');
  }

  // Idempotency: claim this event id before running any side effects. Stripe
  // retries undelivered-ack'd events, and without this a retried
  // checkout.session.completed would call issueLiteLlmVirtualKey again,
  // minting a second LiteLLM key (only the newest gets persisted, but the
  // first is now an orphaned, still-valid credit grant). If the claim hits a
  // duplicate, this event already succeeded -- ack it and stop. If
  // processing then throws, the claim is released so a genuine retry (after
  // a transient failure) can still reprocess it.
  let claimed = false;
  try {
    const claim = await pool.query(
      `INSERT INTO stripe_webhook_events (event_id, event_type) VALUES ($1,$2) ON CONFLICT (event_id) DO NOTHING RETURNING event_id`,
      [event.id, event.type],
    );
    if (!claim.rowCount) return res.json({ received: true, duplicate: true });
    claimed = true;

    if (event.type === 'checkout.session.completed') {
      const session = event.data.object;
      await validateCheckoutSessionPayment(session);
      const organizationId = session.metadata?.organization_id || session.client_reference_id;
      if (!organizationId) {
        console.error(`checkout.session.completed with no organization_id in metadata (session ${session.id})`);
      } else {
        const org = await pool.query(`SELECT name FROM organizations WHERE id = $1`, [organizationId]);
        if (!org.rowCount) {
          console.error(`checkout.session.completed for unknown organization ${organizationId}`);
        } else {
          const issued = await issueLiteLlmVirtualKey({ organizationId, organizationName: org.rows[0].name });
          await pool.query(
            `INSERT INTO organization_billing (organization_id, stripe_customer_id, stripe_subscription_id, stripe_subscription_status, stripe_price_id, litellm_key_id, litellm_virtual_key, litellm_max_budget_usd, updated_at)
             VALUES ($1,$2,$3,'active',$4,$5,$6,$7,now())
             ON CONFLICT (organization_id) DO UPDATE SET
               stripe_customer_id = EXCLUDED.stripe_customer_id,
               stripe_subscription_id = EXCLUDED.stripe_subscription_id,
               stripe_subscription_status = 'active',
               stripe_price_id = EXCLUDED.stripe_price_id,
               litellm_key_id = COALESCE(EXCLUDED.litellm_key_id, organization_billing.litellm_key_id),
               litellm_virtual_key = COALESCE(EXCLUDED.litellm_virtual_key, organization_billing.litellm_virtual_key),
               litellm_max_budget_usd = COALESCE(EXCLUDED.litellm_max_budget_usd, organization_billing.litellm_max_budget_usd),
               updated_at = now()`,
            [organizationId, session.customer || null, session.subscription || null, STRIPE_PRICE_ID, issued.keyId || null, issued.key || null, LITELLM_PLAN_MAX_BUDGET_USD],
          );
        }
      }
    } else if (event.type === 'customer.subscription.updated' || event.type === 'customer.subscription.deleted') {
      const subscription = event.data.object;
      const record = await pool.query(
        `SELECT organization_id, litellm_virtual_key, stripe_subscription_status FROM organization_billing WHERE stripe_subscription_id = $1`,
        [subscription.id],
      );
      if (record.rowCount) {
        const row = record.rows[0];
        const nextStatus = event.type === 'customer.subscription.deleted' ? 'canceled' : subscription.status;
        const wasActive = STRIPE_ACTIVE_STATUSES.has(row.stripe_subscription_status);
        const shouldBlock = STRIPE_REVOKED_STATUSES.has(nextStatus) || event.type === 'customer.subscription.deleted';
        const shouldUnblock = STRIPE_ACTIVE_STATUSES.has(nextStatus) && !wasActive;
        if (row.litellm_virtual_key && shouldBlock) await setLiteLlmKeyBlocked(row.litellm_virtual_key, true);
        else if (row.litellm_virtual_key && shouldUnblock) await setLiteLlmKeyBlocked(row.litellm_virtual_key, false);
        await pool.query(`UPDATE organization_billing SET stripe_subscription_status = $1, updated_at = now() WHERE organization_id = $2`, [nextStatus, row.organization_id]);
      }
    }
    res.json({ received: true });
  } catch (error) {
    console.error(`Error handling Stripe webhook event ${event.type} (${event.id}):`, error.message);
    if (claimed) await pool.query(`DELETE FROM stripe_webhook_events WHERE event_id = $1`, [event.id]).catch(releaseError => console.error('Failed to release webhook event claim:', releaseError.message));
    // Non-2xx so Stripe treats this delivery as failed and retries -- an
    // earlier version of this handler always returned 200 here, which told
    // Stripe every delivery succeeded even when provisioning or the DB write
    // had just thrown, silently losing the event for good.
    res.status(500).json({ error: 'Webhook processing failed' });
  }
}

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

app.get('/api/datasets/search', hdxRateLimit, requireIdentity, async (req, res) => {
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

app.post('/api/datasets/import', hdxRateLimit, requireIdentity, async (req, res) => {
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
    console.error('HDX layer import failed:', error.message);
    res.status(400).json({ error: 'HDX layer import failed' });
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
        [req.params.projectId, req.organizationId, task.rows[0].id, 'create_review_output', { plan }, { planner: plan.planner, mode: plan.mode }],
      );
      job = created.rows[0];
    }
    await client.query('COMMIT');
    res.status(201).json({ task: task.rows[0], job });
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('Task creation failed:', error.message);
    res.status(400).json({ error: 'Task creation failed' });
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
  const completed = updated.rows[0];
  const runId = job.provenance?.run_id || job.input?.run_id;
  if (runId) {
    await pool.query(`UPDATE agent_runs SET status = 'completed', completed_at = now(), updated_at = now(), error = NULL WHERE id = $1 AND organization_id = $2`, [runId, organizationId]);
    await pool.query(`UPDATE agent_steps SET status = 'completed', completed_at = now(), updated_at = now(), error = NULL WHERE run_id = $1 AND organization_id = $2 AND status IN ('queued','running','pending')`, [runId, organizationId]);
  }
  return completed;
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
  const inspected = await inspectSpatialLayers({ projectId: job.project_id, organizationId, layerIds: [input.source_layer_id, input.overlay_layer_id] });
  const spatialDiagnosis = diagnoseSpatialCompatibility({
    source: inspected.find(layer => layer.id === input.source_layer_id),
    overlay: inspected.find(layer => layer.id === input.overlay_layer_id),
  });
  assertSpatialCompatibility(spatialDiagnosis);
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
    const output = { type: 'derived_geometry_layer', operation: 'intersect_layers', result_layer_id: resultLayer.rows[0].id, source_layer_id: source.id, overlay_layer_id: overlay.id, feature_count: inserted.rowCount, topology_diagnosis: spatialDiagnosis, limitations: ['Only polygon intersections are retained in this Phase 1 operation.', 'Derived output requires human review before operational use.'] };
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
    const operationId = String(operation.rows[0].operation || '').trim();
    const definition = OPERATION_REGISTRY[operationId];
    if (!definition) throw new Error(`Unsupported analysis operation: ${operationId}`);
    const job = definition.executor_id === 'buffer_layer'
      ? await executeBufferJob(req.params.jobId, req.organizationId)
      : definition.executor_id === 'intersect_layers'
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
  const inspected = await inspectSpatialLayers({ projectId: job.project_id, organizationId, layerIds: [sourceLayerId] });
  const spatialDiagnosis = diagnoseSpatialCompatibility({ source: inspected[0] });
  assertSpatialCompatibility(spatialDiagnosis);
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
    const output = { type: 'derived_geometry_layer', operation: 'buffer_layer', result_layer_id: resultLayer.rows[0].id, source_layer_id: sourceLayerId, distance_meters: distanceMeters, feature_count: inserted.rowCount, topology_diagnosis: spatialDiagnosis, limitations: ['Buffer distance is calculated in metres using a WGS84 geography cast.', 'Derived output requires human review before operational use.'] };
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
  } catch (error) {
    console.error('Workflow schedule creation failed:', error.message);
    res.status(400).json({ error: 'Workflow schedule creation failed' });
  }
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
    console.error('Workflow run creation failed:', error.message);
    return res.status(400).json({ error: 'Workflow run creation failed' });
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

app.get('/api/analysis/operations', (req, res) => {
  res.json({ operations: Object.entries(OPERATION_REGISTRY).map(([id, definition]) => ({ operation: id, ...definition })) });
});

app.post('/api/projects/:projectId/analysis-jobs', requireIdentity, async (req, res) => {
  const project = await pool.query('SELECT id FROM projects WHERE id = $1 AND organization_id = $2', [req.params.projectId, req.organizationId]);
  if (!project.rowCount) return res.status(404).json({ error: 'Project not found' });
  const operation = String(req.body?.operation || '').trim();
  try {
    const input = normalizeAnalysisOperationInput(operation, req.body || {});
    let spatialDiagnosis = null;
    if (operation === 'intersect_layers' || operation === 'buffer_layer') {
      const layerIds = operation === 'intersect_layers'
        ? [input.source_layer_id, input.overlay_layer_id]
        : [input.source_layer_id];
      const layers = await inspectSpatialLayers({ projectId: req.params.projectId, organizationId: req.organizationId, layerIds });
      if (layers.length !== layerIds.length) throw new Error('Source or overlay layer not found');
      const source = layers.find(layer => layer.id === input.source_layer_id);
      const overlay = operation === 'intersect_layers' ? layers.find(layer => layer.id === input.overlay_layer_id) : null;
      spatialDiagnosis = diagnoseSpatialCompatibility({ source, overlay });
      assertSpatialCompatibility(spatialDiagnosis);
    }
    const result = await pool.query(
      `INSERT INTO analysis_jobs (project_id, organization_id, operation, status, input, provenance)
       VALUES ($1,$2,$3,'queued',$4,$5) RETURNING id, operation, status, input, created_at`,
      [req.params.projectId, req.organizationId, operation, input, { source: 'user-request', phase: '1', ...(spatialDiagnosis ? { spatial_diagnosis: spatialDiagnosis } : {}) }],
    );
    res.status(201).json({ job: result.rows[0] });
  } catch (error) {
    const body = error.safe ? { error: { code: error.code, message: error.message, details: error.details } } : { error: error.message };
    res.status(error.statusCode || 400).json(body);
  }
});

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}

function buildExportSvg(features, layerStyles = {}) {
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
  const draw = (geometry, style) => {
    const stroke = style?.color || '#087f7a'; const fill = style ? `${stroke}${Math.round(style.fill_opacity * 2.55).toString(16).padStart(2, '0')}` : '#087f7a55'; const weight = style?.line_weight || 0.6;
    if (geometry.type === 'Point') { const [x, y] = point(geometry.coordinates); shapes.push(`<circle cx="${x}" cy="${y}" r="1.4" style="fill:${stroke};stroke:#fff;stroke-width:${weight}"/>`); }
    else if (geometry.type === 'LineString') shapes.push(`<polyline points="${geometry.coordinates.map(c => point(c).join(',')).join(' ')}" style="fill:none;stroke:${stroke};stroke-width:${weight}"/>`);
    else if (geometry.type === 'Polygon') geometry.coordinates.forEach(ring => shapes.push(`<path d="M ${ring.map(c => point(c).join(' L '))} Z" style="fill:${fill};stroke:${stroke};stroke-width:${weight}"/>`));
    else if (geometry.coordinates) geometry.coordinates.forEach(item => draw({ type: geometry.type.replace('Multi', ''), coordinates: item }, style));
  };
  features.forEach(feature => draw(feature.geometry, layerStyles[feature.layer_id]));
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
  const layerStyles = Object.fromEntries(layers.map(layer => [layer.id, layerStyleFromRow(layer)]));
  const date = new Date().toISOString().slice(0, 10);
  const totalFeatures = features.length;
  const sourceRows = layers.map((layer, index) => `<tr><td>${index + 1}</td><td>${escapeHtml(layer.name)}</td><td>${escapeHtml(layer.source_resource || 'project layer')}</td><td>${layer.feature_count}</td></tr>`).join('');
  const provenanceRows = layers.map(layer => `<li>${escapeHtml(layer.name)}: ${layer.feature_count} stored features; source ${escapeHtml(layer.source_resource || 'not specified')}.</li>`).join('');
  const pages = [
    `<article class="page cover"><div class="brand">Cartogen AI · Humanitarian Mapping</div><div class="classification">${escapeHtml(classification)}</div><h1>${escapeHtml(title)}</h1><p class="lead">Humanitarian service-coverage screening situation report</p><div class="hero-rule"></div><dl><dt>Prepared by</dt><dd>${escapeHtml(author)}</dd><dt>Project</dt><dd>${escapeHtml(project.name)}</dd><dt>Reference system</dt><dd>${escapeHtml(project.crs)}</dd><dt>Report version</dt><dd>${escapeHtml(reportVersion)}</dd><dt>Prepared</dt><dd>${date}</dd></dl><div class="warning">This report supports structured humanitarian review. It is not a needs assessment, targeting decision, or live security product.</div></article>`,
    `<article class="page"><h2>1. Executive summary</h2><p>This report presents a reviewable, public-data screening slice for humanitarian service coverage in ${escapeHtml(project.name)}. The result combines project layers stored in PostGIS with documented source and compatibility limitations.</p><div class="stat-grid"><div><b>${layers.length}</b><small>project layers</small></div><div><b>${totalFeatures}</b><small>features in export</small></div><div><b>${escapeHtml(project.crs)}</b><small>coordinate reference</small></div></div><h3>Review findings</h3><ul><li>Stored project geometry is available for visual and attribute review.</li><li>Derived layers are retained separately from source layers.</li><li>Source age and administrative compatibility require analyst confirmation.</li><li>Any operational use requires provenance and limitations to remain attached.</li></ul><h3>Recommended next action</h3><p>Confirm source vintages and administrative crosswalks with the responsible information-management team before using the screening output for prioritisation.</p></article>`,
    `<article class="page"><h2>2. Map and layer register</h2><div class="map-report">${buildExportSvg(features, layerStyles)}</div><h3>Layer register</h3><table><thead><tr><th>#</th><th>Layer</th><th>Source</th><th>Features</th></tr></thead><tbody>${sourceRows}</tbody></table></article>`,
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
  const layerStyles = Object.fromEntries(layers.map(layer => [layer.id, layerStyleFromRow(layer)]));
  const sourceItems = layers.map(layer => `<li><b>${escapeHtml(layer.name)}</b> — ${escapeHtml(layer.source_resource || 'project layer')} — ${layer.feature_count} features</li>`).join('');
  const legendItems = layers.map(layer => { const s = layerStyleFromRow(layer); return `<div><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${s.color};opacity:${s.fill_opacity / 100}"></span> ${escapeHtml(s.legend_label || layer.name)} <small>(${escapeHtml(s.classification)} · ${layer.feature_count})</small></div>`; }).join('');
  return `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(title)} — Cartogen AI</title><style>@page{size:${escapeHtml(paper)} ${escapeHtml(orientation)};margin:12mm}body{font-family:Arial,sans-serif;color:#10232b;margin:0}.sheet{min-height:180mm;display:grid;grid-template-rows:auto 1fr auto;gap:7mm}.header{border-bottom:3px solid #087f7a;padding-bottom:4mm;display:flex;justify-content:space-between}.brand{font-weight:800;color:#087f7a;font-size:18px}.title{font-size:23px;font-weight:800;margin-top:2mm}.meta,.footer{font-size:9px;color:#627276}.body{display:grid;grid-template-columns:1fr 65mm;gap:6mm}.map{border:1px solid #9db4b1;background:#e4eeea;min-height:105mm;display:grid;place-items:center;color:#557174;position:relative}.map:after{content:'N ↑';position:absolute;right:7mm;top:7mm;background:#fff;border:1px solid #c6d6d3;border-radius:5px;padding:2mm;font-weight:800}.map:before{content:'0 ─── 5 ─── 10 km';position:absolute;right:7mm;bottom:7mm;background:#ffffffe8;border:1px solid #c6d6d3;border-radius:4px;padding:2mm;font-size:8px}.map svg{width:100%;height:100%;display:block;opacity:${style.opacity / 100}}.map circle{fill:${styleStroke};stroke:#fff;stroke-width:.7}.map path{fill:${styleFill};stroke:${styleStroke};stroke-width:.6}.map polyline{fill:none;stroke:${styleStroke};stroke-width:.6}.side{border:1px solid #cddbd9;padding:4mm;font-size:9px}.side h3{font-size:11px;color:#087f7a;margin:0 0 2mm}.side ul{padding-left:4mm}.warning{background:#fff8e7;border:1px solid #e5c978;padding:2mm;margin-top:3mm}.footer{border-top:1px solid #cddbd9;padding-top:3mm;display:flex;justify-content:space-between}</style></head><body><main class="sheet"><header class="header"><div><div class="brand">Cartogen AI · Humanitarian Mapping</div><div class="title">${escapeHtml(title)}</div><div class="meta">Prepared by ${escapeHtml(author)} · ${new Date().toISOString().slice(0,10)} · CRS ${escapeHtml(project.crs)}</div></div><div class="meta">${escapeHtml(project.sector)}<br>Phase 1 review export</div></header><div class="body"><section class="map">${buildExportSvg(features, layerStyles)}</section><aside class="side"><h3>Legend</h3>${legendItems}<h3>Layers and sources</h3><ul>${sourceItems}</ul>${warnings?'<h3>Data quality</h3><div class="warning">Review source freshness, administrative compatibility, and humanitarian limitations before publication.</div><div class="warning">This is a screening result, not a needs assessment or operational targeting decision.</div>':''}</aside></div><footer class="footer"><span>Source dates, licences, assumptions, and limitations accompany this output.</span><span>${escapeHtml(author)} · Cartogen AI</span></footer></main></body></html>`;
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
      WHERE e.id = $1 AND e.organization_id = $2 AND p.organization_id = $2`,
    [req.params.exportId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).send('Export not found');
  const layers = await pool.query(
    `SELECT l.id, l.name, l.source_resource, l.style_preset, l.style_color, l.style_fill_opacity, l.style_line_weight, l.style_classification, l.style_legend_label, COUNT(f.id)::int AS feature_count
       FROM project_layers l LEFT JOIN project_layer_features f ON f.layer_id = l.id
      WHERE l.project_id = $1 AND l.organization_id = $2 GROUP BY l.id ORDER BY l.created_at`,
    [result.rows[0].project_id, req.organizationId],
  );
  const features = await pool.query(
    `SELECT f.layer_id, ST_AsGeoJSON(f.geometry)::json AS geometry, f.properties
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
        WHERE e.id = $1 AND e.organization_id = $2 AND p.organization_id = $2`,
      [req.params.exportId, req.organizationId],
    );
    if (!result.rowCount) return res.status(404).send('Export not found');
    const layers = await pool.query(
      `SELECT l.id, l.name, l.source_resource, l.style_preset, l.style_color, l.style_fill_opacity, l.style_line_weight, l.style_classification, l.style_legend_label, COUNT(f.id)::int AS feature_count
         FROM project_layers l LEFT JOIN project_layer_features f ON f.layer_id = l.id
        WHERE l.project_id = $1 AND l.organization_id = $2 GROUP BY l.id ORDER BY l.created_at`,
      [result.rows[0].project_id, req.organizationId],
    );
    const features = await pool.query(
      `SELECT f.layer_id, ST_AsGeoJSON(f.geometry)::json AS geometry, f.properties
         FROM project_layer_features f WHERE f.project_id = $1 AND f.organization_id = $2 ORDER BY f.id LIMIT 2000`,
      [result.rows[0].project_id, req.organizationId],
    );
    const html = buildServerExportHtml(result.rows[0], layers.rows, result.rows[0].layout, features.rows);
    const browser = await playwright.chromium.launch(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH, headless: true } : { headless: true });
    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: 'load' });
    const pdf = await page.pdf({ format: result.rows[0].layout.paper || 'A4', landscape: (result.rows[0].layout.orientation || 'landscape') === 'landscape', printBackground: true, margin: { top: '12mm', right: '12mm', bottom: '12mm', left: '12mm' } });
    await browser.close();
    res.type('application/pdf').set('Content-Disposition', `attachment; filename="cartogen-${result.rows[0].id}.pdf"`).send(pdf);
  } catch (error) {
    console.error('PDF renderer unavailable:', error.message);
    res.status(503).json({ error: 'PDF renderer unavailable' });
  }
});

app.get('/api/projects/:projectId/exports', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT e.id, e.format, e.status, layout->>'title' AS title, layout->>'report_type' AS report_type,
            layout->>'report_version' AS report_version, e.created_at, e.completed_at
       FROM export_jobs e JOIN projects p ON p.id = e.project_id
      WHERE e.project_id = $1 AND e.organization_id = $2 AND p.organization_id = $2
      ORDER BY e.created_at DESC LIMIT 50`,
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

function normalizeFeatureTableQuery({ limit = 50, offset = 0, q = '' } = {}) {
  const boundedLimit = Number(limit);
  const boundedOffset = Number(offset);
  const query = String(q || '').trim();
  if (!Number.isInteger(boundedLimit) || boundedLimit < 1 || boundedLimit > 100) throw new Error('limit must be between 1 and 100');
  if (!Number.isInteger(boundedOffset) || boundedOffset < 0 || boundedOffset > 100000) throw new Error('offset must be between 0 and 100000');
  if (query.length > 200) throw new Error('q must not exceed 200 characters');
  return { limit: boundedLimit, offset: boundedOffset, query };
}

app.get('/api/projects/:projectId/layers/:layerId/features', requireIdentity, async (req, res) => {
  let input;
  try { input = normalizeFeatureTableQuery(req.query); }
  catch (error) { return res.status(400).json({ error: error.message }); }
  const layerScope = await pool.query(
    `SELECT l.id
       FROM project_layers l JOIN projects p ON p.id = l.project_id AND p.organization_id = l.organization_id
      WHERE l.id = $1 AND l.project_id = $2 AND l.organization_id = $3`,
    [req.params.layerId, req.params.projectId, req.organizationId],
  );
  if (!layerScope.rowCount) return res.status(404).json({ error: 'Layer not found' });
  const scope = [req.params.projectId, req.params.layerId, req.organizationId];
  const filter = input.query ? ' AND f.properties::text ILIKE $4' : '';
  const filterParams = input.query ? [`%${input.query}%`] : [];
  const count = await pool.query(
    `SELECT COUNT(*)::int AS total
       FROM project_layer_features f
       JOIN project_layers l ON l.id = f.layer_id AND l.project_id = f.project_id AND l.organization_id = f.organization_id
       JOIN projects p ON p.id = f.project_id AND p.organization_id = f.organization_id
      WHERE f.project_id = $1 AND f.layer_id = $2 AND f.organization_id = $3${filter}`,
    scope.concat(filterParams),
  );
  const result = await pool.query(
    `SELECT f.id, f.properties, regexp_replace(ST_GeometryType(f.geometry), '^ST_', '') AS geometry_type
       FROM project_layer_features f
       JOIN project_layers l ON l.id = f.layer_id AND l.project_id = f.project_id AND l.organization_id = f.organization_id
       JOIN projects p ON p.id = f.project_id AND p.organization_id = f.organization_id
      WHERE f.project_id = $1 AND f.layer_id = $2 AND f.organization_id = $3${filter}
      ORDER BY f.id LIMIT $${4 + (input.query ? 1 : 0)} OFFSET $${5 + (input.query ? 1 : 0)}`,
    scope.concat(filterParams, [input.limit, input.offset]),
  );
  const total = count.rows[0].total;
  res.json({
    features: result.rows,
    pagination: { limit: input.limit, offset: input.offset, total, has_more: input.offset + result.rowCount < total },
  });
});

app.post('/api/projects/:projectId/layers/:layerId/features', requireIdentity, async (req, res) => {
  let feature;
  try { feature = normalizeDigitizingFeature(req.body || {}); }
  catch (error) { return res.status(400).json({ error: error.message }); }
  const layerScope = await pool.query(
    `SELECT l.id
       FROM project_layers l JOIN projects p ON p.id = l.project_id AND p.organization_id = l.organization_id
      WHERE l.id = $1 AND l.project_id = $2 AND l.organization_id = $3`,
    [req.params.layerId, req.params.projectId, req.organizationId],
  );
  if (!layerScope.rowCount) return res.status(404).json({ error: 'Layer not found' });
  const before = { geometry: null, properties: {} };
  const beforeHash = hashFeatureState(before);
  const afterHash = hashFeatureState(feature);
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const inserted = await client.query(
      `INSERT INTO project_layer_features (layer_id, project_id, organization_id, geometry, properties)
       VALUES ($1,$2,$3,ST_SetSRID(ST_GeomFromGeoJSON($4),4326),$5)
       RETURNING id, ST_AsGeoJSON(geometry)::json AS geometry, properties`,
      [req.params.layerId, req.params.projectId, req.organizationId, JSON.stringify(feature.geometry), feature.properties],
    );
    const created = inserted.rows[0];
    await client.query(
      `INSERT INTO feature_lineage_events (feature_id, layer_id, project_id, organization_id, event_type, actor_id, before_hash, after_hash, before_state, after_state, metadata)
       VALUES ($1,$2,$3,$4,'feature_create',$5,$6,$7,$8,$9,$10)`,
      [created.id, req.params.layerId, req.params.projectId, req.organizationId, req.user?.id || null, beforeHash, afterHash, before, feature, { source: 'digitizing' }],
    );
    await client.query('COMMIT');
    return res.status(201).json({ feature: created });
  } catch (error) {
    try { await client.query('ROLLBACK'); } catch {}
    console.error('Feature creation failed:', error.message);
    return res.status(400).json({ error: 'Feature creation failed' });
  } finally { client.release(); }
});

app.get('/api/projects/:projectId/features/:featureId/lineage', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT e.id, e.feature_id, e.layer_id, e.project_id, e.event_type, e.actor_id,
            e.before_hash, e.after_hash, e.before_state, e.after_state, e.metadata, e.created_at
       FROM feature_lineage_events e
       JOIN project_layers l ON l.id = e.layer_id AND l.project_id = e.project_id AND l.organization_id = e.organization_id
       JOIN projects p ON p.id = e.project_id AND p.organization_id = e.organization_id
      WHERE e.project_id = $1 AND e.feature_id = $2 AND e.organization_id = $3
      ORDER BY e.created_at ASC, e.id ASC`,
    [req.params.projectId, req.params.featureId, req.organizationId],
  );
  res.json({ lineage: result.rows });
});

app.get('/api/projects/:projectId/layers/:layerId/style', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT l.id, l.project_id, l.style_preset, l.style_color, l.style_fill_opacity, l.style_line_weight, l.style_classification, l.style_legend_label
       FROM project_layers l JOIN projects p ON p.id = l.project_id AND p.organization_id = l.organization_id
      WHERE l.id = $1 AND l.project_id = $2 AND l.organization_id = $3`,
    [req.params.layerId, req.params.projectId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Layer not found' });
  res.json({ style: layerStyleFromRow(result.rows[0]), layer_id: result.rows[0].id });
});

app.put('/api/projects/:projectId/layers/:layerId/style', requireIdentity, async (req, res) => {
  let style;
  try { style = normalizeLayerStyle(req.body || {}); } catch (error) { return res.status(400).json({ error: error.message }); }
  const result = await pool.query(
    `UPDATE project_layers l SET style_preset = $1, style_color = $2, style_fill_opacity = $3, style_line_weight = $4, style_classification = $5, style_legend_label = $6
       FROM projects p WHERE l.id = $7 AND l.project_id = $8 AND l.organization_id = $9 AND p.id = l.project_id AND p.organization_id = l.organization_id
       RETURNING l.id, l.project_id, l.style_preset, l.style_color, l.style_fill_opacity, l.style_line_weight, l.style_classification, l.style_legend_label`,
    [style.preset, style.color, style.fill_opacity, style.line_weight, style.classification, style.legend_label, req.params.layerId, req.params.projectId, req.organizationId],
  );
  if (!result.rowCount) return res.status(404).json({ error: 'Layer not found' });
  res.json({ style: layerStyleFromRow(result.rows[0]), layer_id: result.rows[0].id });
});

app.get('/api/projects/:projectId/layers', requireIdentity, async (req, res) => {
  const result = await pool.query(
    `SELECT l.id, l.name, l.source_url, l.source_resource, l.source_modified_at, l.source_retrieved_at,
            l.licence, l.metadata, l.style_preset, l.style_color, l.style_fill_opacity, l.style_line_weight,
            l.style_classification, l.style_legend_label, COUNT(f.id)::int AS feature_count,
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
        [after.properties, edit.geometry === undefined && !edit.geometry_operation ? null : JSON.stringify(after.geometry), req.params.featureId, req.params.layerId, row.project_id, req.organizationId],
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
    console.error('Feature edit failed:', error.message);
    res.status(400).json({ error: 'Feature edit failed' });
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
    console.error('Layer ingestion failed:', error.message);
    res.status(400).json({ error: 'Layer ingestion failed' });
  } finally {
    client.release();
  }
});

app.use((_req, res) => res.status(404).json({ error: 'Not found' }));

function assertProductionPreflight() {
  if (NODE_ENV === 'production' && PHASE1_IDENTITY_MODE !== 'directus') {
    throw new Error('Production startup requires PHASE1_IDENTITY_MODE=directus');
  }
  if (NODE_ENV === 'production' && ALLOW_UNSIGNED_STRIPE_WEBHOOKS) {
    throw new Error('Unsigned Stripe webhooks are forbidden in production');
  }
}

if (require.main === module) {
  assertProductionPreflight();
  app.listen(PORT, () => console.log(`Cartogen Phase 1 API listening on http://127.0.0.1:${PORT}`));
}

module.exports = { app, pool, OPERATION_REGISTRY, normalizeAnalysisOperationInput, normalizeLayerCrs, diagnoseSpatialCompatibility, assertSpatialCompatibility, inspectSpatialLayers, PLANNER_PROVIDER_MODELS, resolvePlannerModel, plannerProviderStatus, GATEWAY_SYSTEM_PROMPT, buildGatewayMessages, normalizeFeatureCollection, normalizeDigitizingFeature, normalizeGeometryOperation, applyGeometryOperation, normalizeDocumentContext, normalizeIntersectionInput, isSupportedAnalysisOperation, isAllowedScheduledOperation, normalizeWorkflowScheduleRequest, normalizeExportStyle, normalizeLayerStyle, buildServerExportHtml, buildExportSvg, buildTaskPlan, parsePlannerResponse, createTaskPlan, persistAgentRun, approveAgentRun, validateApprovalPlan, normalizeDatasetSearchInput, normalizeFeatureTableQuery, normalizeHdxSearchResponse, normalizeHdxImportRequest, normalizeCsvResource, downloadHdxResource, extractGeoJsonFromZip, parseDownloadedHdxResource, executeReviewOutputJob, executeBufferJob, executeIntersectionJob, normalizeFeatureEditRequest, canonicalFeatureState, hashFeatureState, createEditPreviewToken, verifyEditPreviewToken, mergeFeatureState, featureStateDiff, normalizeSlug, normalizeOrganizationCreateRequest, normalizeProjectCreateRequest, resolveOrganizationForUser, issueLiteLlmVirtualKey, setLiteLlmKeyBlocked, readLiteLlmKeyInfo, directusUser, resolveIdentity, isLoopbackAddress, validateCheckoutSessionPayment, assertProductionPreflight };
