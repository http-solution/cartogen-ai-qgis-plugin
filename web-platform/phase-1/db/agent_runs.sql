CREATE TABLE IF NOT EXISTS agent_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id text NOT NULL,
  project_id text REFERENCES projects(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
  prompt text NOT NULL,
  context jsonb NOT NULL DEFAULT '{}'::jsonb,
  provider text NOT NULL,
  model text NOT NULL,
  plan jsonb NOT NULL DEFAULT '{}'::jsonb,
  rationale text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  error text
);

CREATE TABLE IF NOT EXISTS agent_steps (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  organization_id text NOT NULL,
  project_id text REFERENCES projects(id) ON DELETE CASCADE,
  step_index integer NOT NULL CHECK (step_index > 0),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped', 'cancelled')),
  title text NOT NULL,
  tool text NOT NULL,
  prompt text,
  context jsonb NOT NULL DEFAULT '{}'::jsonb,
  provider text NOT NULL,
  model text NOT NULL,
  plan jsonb NOT NULL DEFAULT '{}'::jsonb,
  rationale text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  error text,
  UNIQUE (run_id, step_index)
);

CREATE INDEX IF NOT EXISTS agent_runs_organization_created_idx ON agent_runs(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_runs_project_created_idx ON agent_runs(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_steps_run_order_idx ON agent_steps(run_id, step_index);
CREATE INDEX IF NOT EXISTS agent_steps_organization_idx ON agent_steps(organization_id, created_at DESC);
