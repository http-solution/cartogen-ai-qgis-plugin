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

CREATE TABLE IF NOT EXISTS feature_lineage_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  feature_id bigint NOT NULL,
  layer_id uuid NOT NULL REFERENCES project_layers(id) ON DELETE CASCADE,
  project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  organization_id text NOT NULL,
  event_type text NOT NULL,
  actor_id text,
  before_hash text NOT NULL,
  after_hash text NOT NULL,
  before_state jsonb NOT NULL,
  after_state jsonb NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS feature_lineage_events_feature_idx ON feature_lineage_events(feature_id, created_at DESC);
CREATE INDEX IF NOT EXISTS feature_lineage_events_scope_idx ON feature_lineage_events(organization_id, project_id, created_at DESC);

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

CREATE TABLE IF NOT EXISTS project_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  organization_id text NOT NULL,
  name text NOT NULL,
  mime_type text NOT NULL,
  text_content text NOT NULL,
  source_url text,
  sha256 text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS project_documents_project_idx ON project_documents(project_id, created_at DESC);

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

CREATE TABLE IF NOT EXISTS agent_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id text NOT NULL,
  project_id text REFERENCES projects(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','failed','cancelled')),
  prompt text NOT NULL, context jsonb NOT NULL DEFAULT '{}'::jsonb, provider text NOT NULL, model text NOT NULL,
  plan jsonb NOT NULL DEFAULT '{}'::jsonb, rationale text, created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, completed_at timestamptz, error text
);
CREATE TABLE IF NOT EXISTS agent_steps (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  organization_id text NOT NULL, project_id text REFERENCES projects(id) ON DELETE CASCADE,
  step_index integer NOT NULL CHECK (step_index > 0), status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','running','completed','failed','skipped','cancelled')),
  title text NOT NULL, tool text NOT NULL, prompt text, context jsonb NOT NULL DEFAULT '{}'::jsonb,
  provider text NOT NULL, model text NOT NULL, plan jsonb NOT NULL DEFAULT '{}'::jsonb, rationale text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz, completed_at timestamptz, error text, UNIQUE (run_id, step_index)
);
CREATE INDEX IF NOT EXISTS agent_runs_organization_created_idx ON agent_runs(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_runs_project_created_idx ON agent_runs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_steps_run_order_idx ON agent_steps(run_id, step_index);
CREATE INDEX IF NOT EXISTS agent_steps_organization_idx ON agent_steps(organization_id, created_at DESC);

CREATE TABLE IF NOT EXISTS workflow_schedules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id text NOT NULL,
  project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE, name text NOT NULL,
  workflow jsonb NOT NULL, interval_seconds integer NOT NULL CHECK (interval_seconds >= 60),
  next_run timestamptz NOT NULL, status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','cancelled')),
  last_run_id uuid, last_run_at timestamptz, last_error text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS workflow_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), organization_id text NOT NULL,
  project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  schedule_id uuid NOT NULL REFERENCES workflow_schedules(id) ON DELETE CASCADE,
  analysis_job_id uuid REFERENCES analysis_jobs(id) ON DELETE SET NULL, operation text NOT NULL,
  workflow jsonb NOT NULL, status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','failed')),
  output jsonb NOT NULL DEFAULT '{}'::jsonb, error text, started_at timestamptz,
  completed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE workflow_schedules ADD CONSTRAINT workflow_schedules_last_run_fk FOREIGN KEY (last_run_id) REFERENCES workflow_runs(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS workflow_schedules_scope_idx ON workflow_schedules(organization_id, project_id, status, next_run);
CREATE INDEX IF NOT EXISTS workflow_runs_schedule_idx ON workflow_runs(schedule_id, created_at DESC);
CREATE INDEX IF NOT EXISTS workflow_runs_scope_idx ON workflow_runs(organization_id, project_id, created_at DESC);

INSERT INTO projects (id, organization_id, name, sector, crs, status, metadata)
VALUES ('pakistan-humanitarian-screening', 'demo-humanitarian-lab', 'Pakistan Humanitarian Service Coverage', 'humanitarian', 'EPSG:4326', 'draft', '{"phase":"1","source":"public-data-demo"}')
ON CONFLICT (id) DO NOTHING;
