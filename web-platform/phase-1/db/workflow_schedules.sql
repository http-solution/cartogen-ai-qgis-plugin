-- Persisted read-only workflow scheduling schema and migration.
CREATE TABLE IF NOT EXISTS workflow_schedules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id text NOT NULL,
  project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name text NOT NULL,
  workflow jsonb NOT NULL,
  interval_seconds integer NOT NULL CHECK (interval_seconds >= 60),
  next_run timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled')),
  last_run_id uuid,
  last_run_at timestamptz,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id text NOT NULL,
  project_id text NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  schedule_id uuid NOT NULL REFERENCES workflow_schedules(id) ON DELETE CASCADE,
  analysis_job_id uuid REFERENCES analysis_jobs(id) ON DELETE SET NULL,
  operation text NOT NULL,
  workflow jsonb NOT NULL,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed')),
  output jsonb NOT NULL DEFAULT '{}'::jsonb,
  error text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE workflow_schedules
  DROP CONSTRAINT IF EXISTS workflow_schedules_last_run_fk;
ALTER TABLE workflow_schedules
  ADD CONSTRAINT workflow_schedules_last_run_fk FOREIGN KEY (last_run_id)
  REFERENCES workflow_runs(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS workflow_schedules_scope_idx
  ON workflow_schedules(organization_id, project_id, status, next_run);
CREATE INDEX IF NOT EXISTS workflow_runs_schedule_idx
  ON workflow_runs(schedule_id, created_at DESC);
CREATE INDEX IF NOT EXISTS workflow_runs_scope_idx
  ON workflow_runs(organization_id, project_id, created_at DESC);
