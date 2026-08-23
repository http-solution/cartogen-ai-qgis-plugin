// Postgres-backed replacement for the local data/subscriptions.json prototype.
// Reuses the same DATABASE_URL Postgres instance LiteLLM's own virtual-key store
// already requires (service/README.md's documented setup) -- one DB to run, a
// separate table here so nothing collides with LiteLLM's own Prisma-managed schema.
//
// Untested against a live Postgres instance from this sandbox (no DB server
// reachable here) -- schema and queries are written directly against the `pg`
// driver's documented API, same "correct per the code, not yet run live" caveat
// every other never-deployed piece of service/ already carries (see
// providers/cartogen.py's docstring on the plugin side for the same pattern).

const { Pool } = require('pg');

const { DATABASE_URL } = process.env;

let pool = null;

function getPool() {
  if (!DATABASE_URL) {
    throw new Error('DATABASE_URL not set -- required for the subscriptions table (same Postgres LiteLLM uses)');
  }
  if (!pool) {
    pool = new Pool({ connectionString: DATABASE_URL });
  }
  return pool;
}

// Called once at server startup. IF NOT EXISTS makes this safe to run on every
// boot rather than needing a separate migration step -- there's no migration
// tooling in this small Express app, and the schema is simple enough that a
// hand-rolled migration tool would be more machinery than the problem needs.
async function initSchema() {
  await getPool().query(`
    CREATE TABLE IF NOT EXISTS cartogen_subscriptions (
      stripe_session_id TEXT PRIMARY KEY,
      retrieval_token TEXT UNIQUE NOT NULL,
      token_used_at TIMESTAMPTZ,
      email TEXT,
      api_key TEXT,
      stripe_customer_id TEXT,
      stripe_subscription_id TEXT,
      directus_user_id TEXT,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    ALTER TABLE cartogen_subscriptions ADD COLUMN IF NOT EXISTS directus_user_id TEXT;
    CREATE INDEX IF NOT EXISTS idx_cartogen_subscriptions_stripe_subscription_id
      ON cartogen_subscriptions (stripe_subscription_id);
  `);
}

// Row created at /create-checkout-session time, before the customer ever reaches
// Stripe -- status starts 'pending' since payment hasn't completed yet. Stores
// retrieval_token here (not just in Stripe's session metadata) so /key-for-session
// can look it up without an extra Stripe API round-trip on every poll.
async function createPendingCheckout({ sessionId, retrievalToken }) {
  await getPool().query(
    `INSERT INTO cartogen_subscriptions (stripe_session_id, retrieval_token, status)
     VALUES ($1, $2, 'pending')`,
    [sessionId, retrievalToken]
  );
}

// Called from the checkout.session.completed webhook once the virtual key is minted.
async function activateSubscription({ sessionId, apiKey, email, customerId, subscriptionId, directusUserId }) {
  await getPool().query(
    `UPDATE cartogen_subscriptions
     SET api_key = $2, email = $3, stripe_customer_id = $4, stripe_subscription_id = $5,
         directus_user_id = $6, status = 'active', updated_at = now()
     WHERE stripe_session_id = $1`,
    [sessionId, apiKey, email, customerId, subscriptionId, directusUserId || null]
  );
}

// The one-time-read path: returns the api_key only if the token exists, the
// subscription is active, and it hasn't been read before -- then immediately
// marks it read in the same call so a second request (leaked/logged URL,
// browser back-button, a retry racing the first request) gets nothing instead
// of the same key again. `token_used_at IS NULL` in the WHERE clause (not a
// separate read-then-write) is what makes two concurrent requests for the same
// token not both succeed -- Postgres serializes the UPDATE, only one row match wins.
async function consumeRetrievalToken(token) {
  const { rows } = await getPool().query(
    `UPDATE cartogen_subscriptions
     SET token_used_at = now()
     WHERE retrieval_token = $1 AND status = 'active' AND token_used_at IS NULL
     RETURNING api_key`,
    [token]
  );
  return rows[0]?.api_key || null;
}

// Subscription lifecycle -- looked up by Stripe subscription id, which
// customer.subscription.updated/.deleted events carry (session id isn't
// present on these events, only on the original checkout.session.completed).
async function getBySubscriptionId(subscriptionId) {
  const { rows } = await getPool().query(
    `SELECT * FROM cartogen_subscriptions WHERE stripe_subscription_id = $1`,
    [subscriptionId]
  );
  return rows[0] || null;
}

async function setStatus(subscriptionId, status) {
  await getPool().query(
    `UPDATE cartogen_subscriptions SET status = $2, updated_at = now()
     WHERE stripe_subscription_id = $1`,
    [subscriptionId, status]
  );
}

module.exports = {
  initSchema,
  createPendingCheckout,
  activateSubscription,
  consumeRetrievalToken,
  getBySubscriptionId,
  setStatus,
};
