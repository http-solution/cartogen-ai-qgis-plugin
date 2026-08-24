-- Apply to existing Phase 1 databases before using POST /api/ai/runs/:runId/approve.
ALTER TABLE agent_steps
  DROP CONSTRAINT IF EXISTS agent_steps_status_check;
ALTER TABLE agent_steps
  ADD CONSTRAINT agent_steps_status_check
  CHECK (status IN ('pending','queued','running','completed','failed','skipped','cancelled'));
