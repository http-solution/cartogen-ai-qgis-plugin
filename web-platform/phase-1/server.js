const path = require('node:path');
const express = require('express');
const { Pool } = require('pg');

const PORT = Number(process.env.PORT || 4177);
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

module.exports = { app, pool, normalizeFeatureCollection };
