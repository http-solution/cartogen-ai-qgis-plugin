// Glue layer: pricing page -> Stripe Checkout -> webhook -> LiteLLM virtual key.
//
// This is the one genuinely custom piece in the "website / billing / gateway" stack.
// Billing logic itself stays in Stripe; key/budget logic stays in LiteLLM. This file
// just translates events between them.

const path = require('path');
// service/README.md's documented setup creates .env in service/ (this file's parent
// directory), then `cd website && npm start` -- dotenv's default config() only looks in
// process.cwd(), which is service/website/ at that point, so it silently never found the
// file (confirmed empirically: dotenv does not search parent directories). Pointing this
// at an explicit, __dirname-relative path makes it work regardless of which directory
// `node server.js`/`npm start` is actually invoked from.
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });
const crypto = require('crypto');
const express = require('express');
const db = require('./db');
const auth = require('./auth');

const {
  PORT = 3000,
  NODE_ENV = 'development',
  STRIPE_SECRET_KEY,
  STRIPE_WEBHOOK_SECRET,
  STRIPE_PRICE_ID,
  LITELLM_BASE_URL = 'http://localhost:4000',
  LITELLM_MASTER_KEY,
  PUBLIC_BASE_URL,
} = process.env;

const stripe = STRIPE_SECRET_KEY ? require('stripe')(STRIPE_SECRET_KEY) : null;

// Statuses a Stripe Subscription object can carry that mean "stop letting this
// key work" vs. statuses that mean "this key should work." Anything not in
// either list (e.g. a status Stripe adds later) is deliberately left alone
// rather than guessed at -- see the webhook handler below.
const REVOKED_SUBSCRIPTION_STATUSES = new Set(['canceled', 'unpaid', 'incomplete_expired', 'past_due']);
const ACTIVE_SUBSCRIPTION_STATUSES = new Set(['active', 'trialing']);

// Mint a LiteLLM virtual key for one customer. This is the "one plan" version —
// see README for what's still needed to map Stripe price -> budget/rate-limit per tier.
async function issueVirtualKey({ customerEmail, sessionId }) {
  if (!LITELLM_MASTER_KEY) {
    throw new Error('LITELLM_MASTER_KEY not set — cannot mint a virtual key');
  }
  const res = await fetch(`${LITELLM_BASE_URL}/key/generate`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${LITELLM_MASTER_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      max_budget: 5, // dollars/month of underlying LLM spend allowed on this plan
      budget_duration: '30d',
      metadata: { customer_email: customerEmail, stripe_session_id: sessionId },
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`LiteLLM /key/generate failed (${res.status}): ${text}`);
  }
  const data = await res.json();
  return data.key; // the virtual API key, e.g. "sk-..."
}

// Revoke/restore access without deleting the key outright -- reversible, so a
// subscription that lapses and later gets fixed (a retried payment, a plan
// change) can be unblocked instead of the customer needing a whole new key.
// Endpoint shapes confirmed against LiteLLM's documented Virtual Key Management
// API (POST /key/block, /key/unblock, body: {"key": "..."}); untested against a
// live gateway, like everything else in service/ that has no deployment yet.
async function setKeyBlocked(apiKey, blocked) {
  if (!LITELLM_MASTER_KEY || !apiKey) return;
  const path = blocked ? '/key/block' : '/key/unblock';
  const res = await fetch(`${LITELLM_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${LITELLM_MASTER_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ key: apiKey }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`LiteLLM ${path} failed (${res.status}): ${text}`);
  }
}

const app = express();
app.use(express.static(path.join(__dirname, 'public')));

// Stripe requires the RAW body for webhook signature verification, so this route
// must come before any express.json() body parser is applied globally.
app.post('/webhook', express.raw({ type: 'application/json' }), async (req, res) => {
  let event;

  if (STRIPE_WEBHOOK_SECRET && stripe) {
    const sig = req.headers['stripe-signature'];
    try {
      event = stripe.webhooks.constructEvent(req.body, sig, STRIPE_WEBHOOK_SECRET);
    } catch (err) {
      console.error('Webhook signature verification failed:', err.message);
      return res.status(400).send(`Webhook Error: ${err.message}`);
    }
  } else if (NODE_ENV === 'development') {
    // Dev-mode escape hatch: no real Stripe webhook secret configured yet, so trust
    // the raw JSON body as-is. Lets you test the full flow with `curl` before you've
    // set up a real Stripe account. See README "Testing the flow without real Stripe keys".
    console.warn('[dev] Skipping webhook signature verification (no STRIPE_WEBHOOK_SECRET)');
    event = JSON.parse(req.body.toString('utf8'));
  } else {
    return res.status(400).send('Missing STRIPE_WEBHOOK_SECRET in production');
  }

  try {
    if (event.type === 'checkout.session.completed') {
      const session = event.data.object;
      const retrievalToken = session.metadata?.retrieval_token;
      if (!retrievalToken) {
        // Only real cause: a checkout session created before this
        // metadata-based flow existed, or created by hand outside
        // /create-checkout-session. Nothing to activate against.
        console.error(`checkout.session.completed with no retrieval_token in metadata (session ${session.id})`);
      } else {
        try {
          const apiKey = await issueVirtualKey({
            customerEmail: session.customer_details?.email || session.customer_email || 'unknown',
            sessionId: session.id,
          });
          await db.activateSubscription({
            sessionId: session.id,
            apiKey,
            email: session.customer_details?.email || session.customer_email || null,
            customerId: session.customer || null,
            subscriptionId: session.subscription || null,
            directusUserId: session.metadata?.directus_user_id || session.client_reference_id || null,
          });
          console.log(`Issued virtual key for session ${session.id}`);
        } catch (err) {
          console.error('Failed to issue virtual key:', err.message);
          // In production: retry / alert. For now the client's success page will just
          // keep polling and never find a key, which is at least visible, not silent.
        }
      }
    } else if (event.type === 'customer.subscription.updated') {
      const subscription = event.data.object;
      const record = await db.getBySubscriptionId(subscription.id);
      if (record && record.api_key) {
        if (REVOKED_SUBSCRIPTION_STATUSES.has(subscription.status) && record.status !== 'revoked') {
          await setKeyBlocked(record.api_key, true);
          await db.setStatus(subscription.id, 'revoked');
          console.log(`Blocked key for subscription ${subscription.id} (status -> ${subscription.status})`);
        } else if (ACTIVE_SUBSCRIPTION_STATUSES.has(subscription.status) && record.status === 'revoked') {
          await setKeyBlocked(record.api_key, false);
          await db.setStatus(subscription.id, 'active');
          console.log(`Unblocked key for subscription ${subscription.id} (status -> ${subscription.status})`);
        }
      }
    } else if (event.type === 'customer.subscription.deleted') {
      const subscription = event.data.object;
      const record = await db.getBySubscriptionId(subscription.id);
      if (record && record.api_key) {
        await setKeyBlocked(record.api_key, true);
        await db.setStatus(subscription.id, 'revoked');
        console.log(`Blocked key for cancelled subscription ${subscription.id}`);
      }
    }
  } catch (err) {
    // A DB/LiteLLM error handling a lifecycle event shouldn't surface to Stripe as
    // a webhook failure (Stripe would just retry the same event) -- log it and
    // still 200, same as the pre-existing checkout.session.completed error handling.
    console.error(`Error handling webhook event ${event.type}:`, err.message);
  }

  res.json({ received: true });
});

app.use(express.json());

app.get('/healthz', (req, res) => res.json({ ok: true, service: 'cartogen-website' }));

app.post('/auth/login', async (req, res) => {
  const { email, password } = req.body || {};
  if (typeof email !== 'string' || typeof password !== 'string' || !email || !password) {
    return res.status(400).json({ error: 'email and password are required' });
  }
  try {
    const result = await auth.login(email.trim(), password);
    auth.setSession(res, result.data.access_token);
    return res.json({ ok: true });
  } catch (err) {
    return res.status(err.status === 401 ? 401 : 400).json({ error: err.message });
  }
});

app.post('/auth/register', async (req, res) => {
  const { email, password, first_name = '', last_name = '' } = req.body || {};
  if (typeof email !== 'string' || typeof password !== 'string' || password.length < 12) {
    return res.status(400).json({ error: 'email and a password of at least 12 characters are required' });
  }
  try {
    await auth.register({ email: email.trim(), password, first_name, last_name });
    const result = await auth.login(email.trim(), password);
    auth.setSession(res, result.data.access_token);
    return res.status(201).json({ ok: true });
  } catch (err) {
    return res.status(err.status === 401 ? 401 : 400).json({ error: err.message });
  }
});

app.post('/auth/logout', (req, res) => {
  auth.clearSession(res);
  res.json({ ok: true });
});

app.get('/api/me', auth.requireUser, (req, res) => {
  const { accessToken, ...user } = req.user;
  res.json({ user });
});

app.post('/create-checkout-session', auth.requireUser, async (req, res) => {
  if (!stripe || !STRIPE_PRICE_ID) {
    return res.status(500).json({
      error: 'Stripe not configured yet — set STRIPE_SECRET_KEY and STRIPE_PRICE_ID in .env',
    });
  }
  try {
    // Minted before the Stripe session so it can be embedded in both the
    // session's own metadata (read back by the webhook) and success_url (read
    // by the browser) -- the browser never sees the raw Stripe session id at
    // all, only this single-use token. See db.js's consumeRetrievalToken for
    // the one-time-read enforcement.
    const retrievalToken = crypto.randomBytes(32).toString('hex');
    const baseUrl = PUBLIC_BASE_URL || `${req.protocol}://${req.get('host')}`;

    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      line_items: [{ price: STRIPE_PRICE_ID, quantity: 1 }],
      client_reference_id: req.user.id,
      customer_email: req.user.email,
      metadata: { retrieval_token: retrievalToken, directus_user_id: req.user.id },
      success_url: `${baseUrl}/success.html?token=${retrievalToken}`,
      cancel_url: `${baseUrl}/`,
    });

    await db.createPendingCheckout({ sessionId: session.id, retrievalToken });

    res.json({ url: session.url });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

app.get('/key-for-session', async (req, res) => {
  const token = req.query.token;
  if (!token) return res.json({});
  try {
    const apiKey = await db.consumeRetrievalToken(token);
    res.json(apiKey ? { apiKey } : {});
  } catch (err) {
    console.error('Failed to read retrieval token:', err.message);
    res.status(500).json({ error: 'internal error' });
  }
});

db.initSchema()
  .then(() => {
    app.listen(PORT, () => {
      console.log(`Website running at http://localhost:${PORT}`);
      if (!stripe) console.warn('Stripe not configured — /create-checkout-session will error until STRIPE_SECRET_KEY is set.');
    });
  })
  .catch((err) => {
    console.error('Failed to initialize the subscriptions table (is DATABASE_URL set and Postgres reachable?):', err.message);
    process.exit(1);
  });

/*
Test the payment -> key flow locally without a real Stripe account:
(with NODE_ENV=development and no STRIPE_WEBHOOK_SECRET set)

  # 1. Create a checkout session the normal way (or just fabricate a token/session
  #    id pair below) -- then POST the completed event with matching metadata:
  curl -X POST http://localhost:3000/webhook \
    -H "Content-Type: application/json" \
    -d '{
      "type": "checkout.session.completed",
      "data": { "object": {
        "id": "cs_test_fake123",
        "customer_details": { "email": "test@example.com" },
        "metadata": { "retrieval_token": "your-test-token-here" }
      }}
    }'

  # Requires a matching pending row already inserted via /create-checkout-session,
  # or insert one by hand: INSERT INTO cartogen_subscriptions
  # (stripe_session_id, retrieval_token) VALUES ('cs_test_fake123', 'your-test-token-here');

Then:
  curl "http://localhost:3000/key-for-session?token=your-test-token-here"
  # Second call to the same URL should now return {} -- single-use.
*/
