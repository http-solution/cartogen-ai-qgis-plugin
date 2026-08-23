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
