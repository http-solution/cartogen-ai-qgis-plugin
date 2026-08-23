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

CREATE TABLE IF NOT EXISTS workspace_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  organization_id text NOT NULL,
  title text NOT NULL,
  description text NOT NULL,
  status text NOT NULL DEFAULT 'proposed',
  plan jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analysis_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  organization_id text NOT NULL,
  task_id uuid REFERENCES workspace_tasks(id) ON DELETE SET NULL,
  operation text NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  input jsonb NOT NULL DEFAULT '{}'::jsonb,
  output jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS workspace_tasks_project_idx ON workspace_tasks(project_id);
CREATE INDEX IF NOT EXISTS analysis_jobs_project_idx ON analysis_jobs(project_id);

CREATE TABLE IF NOT EXISTS export_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  organization_id text NOT NULL,
  format text NOT NULL DEFAULT 'html',
  status text NOT NULL DEFAULT 'queued',
  layout jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS export_jobs_project_idx ON export_jobs(project_id);

INSERT INTO projects (id, organization_id, name, sector, crs, status, metadata)
VALUES ('pakistan-humanitarian-screening', 'demo-humanitarian-lab', 'Pakistan Humanitarian Service Coverage', 'humanitarian', 'EPSG:4326', 'draft', '{"phase":"1","source":"public-data-demo"}')
ON CONFLICT (id) DO NOTHING;
