-- Foundational schema: PostGIS/pgcrypto extensions and the core
-- project/layer/feature tables everything else in this app references.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS projects (
  id text PRIMARY KEY,
  organization_id text NOT NULL,
  name text NOT NULL,
  sector text NOT NULL,
  crs text NOT NULL DEFAULT 'EPSG:4326',
  status text NOT NULL DEFAULT 'draft',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_layers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  organization_id text NOT NULL,
  name text NOT NULL,
  source_url text,
  source_resource text,
  source_modified_at timestamptz,
  source_retrieved_at timestamptz NOT NULL DEFAULT now(),
  licence text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_layer_features (
  id bigserial PRIMARY KEY,
  layer_id uuid NOT NULL REFERENCES project_layers(id) ON DELETE CASCADE,
  project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  organization_id text NOT NULL,
  geometry geometry(Geometry, 4326) NOT NULL,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS project_layers_project_idx ON project_layers(project_id);
CREATE INDEX IF NOT EXISTS project_layer_features_layer_idx ON project_layer_features(layer_id);
CREATE INDEX IF NOT EXISTS project_layer_features_geometry_idx ON project_layer_features USING gist(geometry);
