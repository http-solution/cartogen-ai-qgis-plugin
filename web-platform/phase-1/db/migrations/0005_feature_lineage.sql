-- feature_lineage_events: before/after hash + full state for every feature
-- edit, the audit trail behind POST /api/layers/:layerId/features/:featureId/edit.
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
