-- workspace_tasks + analysis_jobs: the AI-plan-to-review-to-execute pipeline.
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
