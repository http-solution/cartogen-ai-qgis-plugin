-- Seed data for PHASE1_IDENTITY_MODE=demo (local dev / evaluation). Kept as
-- its own migration, separate from the schema-defining migrations above, so
-- it's obvious this one is data, not structure, and can be skipped or
-- re-run independently -- see db/MIGRATIONS.md. ON CONFLICT DO NOTHING makes
-- it idempotent the same way every schema migration here is.
INSERT INTO organizations (id, name, slug)
VALUES ('demo-humanitarian-lab', 'Demo Humanitarian Lab', 'demo-humanitarian-lab')
ON CONFLICT (id) DO NOTHING;

INSERT INTO organization_billing (organization_id, stripe_subscription_status)
VALUES ('demo-humanitarian-lab', 'none')
ON CONFLICT (organization_id) DO NOTHING;

INSERT INTO projects (id, organization_id, name, sector, crs, status, metadata)
VALUES ('pakistan-humanitarian-screening', 'demo-humanitarian-lab', 'Pakistan Humanitarian Service Coverage', 'humanitarian', 'EPSG:4326', 'draft', '{"phase":"1","source":"public-data-demo"}')
ON CONFLICT (id) DO NOTHING;
