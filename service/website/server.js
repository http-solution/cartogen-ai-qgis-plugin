// Glue layer: pricing page -> Stripe Checkout -> webhook -> LiteLLM virtual key.
//
// This is the one genuinely custom piece in the "website / billing / gateway" stack.
// Billing logic itself stays in Stripe; key/budget logic stays in LiteLLM. This file
// just translates events between them.

require('dotenv').config();
const fs = require('fs');
const path = require('path');
const express = require('express');

const {
  PORT = 3000,
  NODE_ENV = 'development',
  STRIPE_SECRET_KEY,
  STRIPE_WEBHOOK_SECRET,
  STRIPE_PRICE_ID,
  LITELLM_BASE_URL = 'http://localhost:4000',
  LITELLM_MASTER_KEY,
} = process.env;

const stripe = STRIPE_SECRET_KEY ? require('stripe')(STRIPE_SECRET_KEY) : null;

const DB_PATH = path.join(__dirname, '..', 'data', 'subscriptions.json');

function readDb() {
  try {
    return JSON.parse(fs.readFileSync(DB_PATH, 'utf8'));
  } catch {
    return {};
  }
}

function writeDb(db) {
  fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });
  fs.writeFileSync(DB_PATH, JSON.stringify(db, null, 2));
}

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

  if (event.type === 'checkout.session.completed') {
    const session = event.data.object;
    try {
      const apiKey = await issueVirtualKey({
        customerEmail: session.customer_details?.email || session.customer_email || 'unknown',
        sessionId: session.id,
      });
      const db = readDb();
      db[session.id] = {
        apiKey,
        email: session.customer_details?.email || session.customer_email || null,
        createdAt: new Date().toISOString(),
      };
      writeDb(db);
      console.log(`Issued virtual key for session ${session.id}`);
    } catch (err) {
      console.error('Failed to issue virtual key:', err.message);
      // In production: retry / alert. For now the client's success page will just
      // keep polling and never find a key, which is at least visible, not silent.
    }
  }

  res.json({ received: true });
});

app.use(express.json());

app.post('/create-checkout-session', async (req, res) => {
  if (!stripe || !STRIPE_PRICE_ID) {
    return res.status(500).json({
      error: 'Stripe not configured yet — set STRIPE_SECRET_KEY and STRIPE_PRICE_ID in .env',
    });
  }
  try {
    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      line_items: [{ price: STRIPE_PRICE_ID, quantity: 1 }],
      success_url: `${req.protocol}://${req.get('host')}/success.html?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${req.protocol}://${req.get('host')}/`,
    });
    res.json({ url: session.url });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

app.get('/key-for-session', (req, res) => {
  const db = readDb();
  const record = db[req.query.session_id];
  res.json(record ? { apiKey: record.apiKey } : {});
});

app.listen(PORT, () => {
  console.log(`Website running at http://localhost:${PORT}`);
  if (!stripe) console.warn('Stripe not configured — /create-checkout-session will error until STRIPE_SECRET_KEY is set.');
});

/*
Test the payment -> key flow locally without a real Stripe account:
(with NODE_ENV=development and no STRIPE_WEBHOOK_SECRET set)

  curl -X POST http://localhost:3000/webhook \
    -H "Content-Type: application/json" \
    -d '{
      "type": "checkout.session.completed",
      "data": { "object": {
        "id": "cs_test_fake123",
        "customer_details": { "email": "test@example.com" }
      }}
    }'

Then:
  curl "http://localhost:3000/key-for-session?session_id=cs_test_fake123"
*/
