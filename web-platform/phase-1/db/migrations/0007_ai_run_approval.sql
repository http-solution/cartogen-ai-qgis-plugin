-- Re-asserts agent_steps' status constraint via the DROP-then-ADD pattern
-- required for POST /api/ai/runs/:runId/approve. Against the constraint
-- 0006_agent_runs.sql already creates, this is a no-op (both define the same
-- 7-value set) -- it's kept as its own migration to preserve the real
-- history (this constraint was widened after agent_steps first shipped) and
-- as a template for the idempotent way to change a CHECK constraint: DROP
-- CONSTRAINT IF EXISTS before ADD CONSTRAINT, never a bare ADD CONSTRAINT,
-- which fails on any database where a same-named constraint already exists.
ALTER TABLE agent_steps
  DROP CONSTRAINT IF EXISTS agent_steps_status_check;
ALTER TABLE agent_steps
  ADD CONSTRAINT agent_steps_status_check
  CHECK (status IN ('pending','queued','running','completed','failed','skipped','cancelled'));
