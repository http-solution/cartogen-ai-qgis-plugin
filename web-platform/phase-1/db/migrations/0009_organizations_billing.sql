-- Organizations, Directus-user membership, and per-organization billing
-- state. Deliberately NOT modeled as Directus collections -- Directus stays
-- scoped to what it already does (directus_users authentication) and
-- nothing here requires configuring Directus's own permission/role system.
-- `directus_user_id` columns just store the `id` field Directus's own
-- /users/me returns -- a plain string, no foreign key into Directus's own
-- database (a separate Postgres database in the merged compose stack;
-- cross-database foreign keys aren't possible in Postgres anyway).
--
-- `organizations.id` is `text`, not `uuid`, to match the loose `text
-- organization_id` convention already used on every other table in this
-- schema (see 0001_core_schema.sql onward).
CREATE TABLE IF NOT EXISTS organizations (
  id text PRIMARY KEY,
  name text NOT NULL,
  slug text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS organization_members (
  organization_id text NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  directus_user_id text NOT NULL,
  role text NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, directus_user_id)
);
CREATE INDEX IF NOT EXISTS organization_members_user_idx ON organization_members (directus_user_id);

-- One row per organization. Stripe/LiteLLM identifiers and the raw LiteLLM
-- virtual key live here -- server-side only -- and are never modeled in
-- Directus, which has a broader admin/API surface than this table needs to
-- be exposed to.
CREATE TABLE IF NOT EXISTS organization_billing (
  organization_id text PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
  stripe_customer_id text,
  stripe_subscription_id text,
  stripe_subscription_status text NOT NULL DEFAULT 'none'
    CHECK (stripe_subscription_status IN ('none', 'incomplete', 'active', 'trialing', 'past_due', 'canceled', 'unpaid')),
  stripe_price_id text,
  litellm_key_id text,
  litellm_virtual_key text,
  litellm_max_budget_usd numeric(10,2),
  pending_checkout_org_id text,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS organization_billing_subscription_idx ON organization_billing (stripe_subscription_id);

-- Idempotency ledger for the Stripe webhook: a row is claimed before an
-- event's side effects (LiteLLM key issuance, billing state writes) run, and
-- removed again if those side effects throw -- see server.js's
-- handleStripeWebhook for the full rationale.
CREATE TABLE IF NOT EXISTS stripe_webhook_events (
  event_id text PRIMARY KEY,
  event_type text NOT NULL,
  processed_at timestamptz NOT NULL DEFAULT now()
);
