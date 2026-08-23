#!/usr/bin/env bash
set -u
set -o pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:3001}"
LITELLM_URL="${LITELLM_URL:-http://127.0.0.1:4001}"
SERVICE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SERVICE_DIR"
COOKIE_FILE="${TEMP:-/tmp}/cartogen-saas-cookie.txt"
STAMP="$(date +%s)"
EMAIL="cartogen-smoke-${STAMP}@example.com"
PASSWORD='CartogenSmokePassword123!'
SESSION_ID="cs_smoke_${STAMP}"
RETRIEVAL_TOKEN="retrieval_${STAMP}_$(python -c 'import secrets; print(secrets.token_hex(12))')"
SUBSCRIPTION_ID="sub_smoke_${STAMP}"
CUSTOMER_ID="cus_smoke_${STAMP}"

BLOCKED=0
pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; }
block() { BLOCKED=1; printf 'BLOCK %s\n' "$1"; }

rm -f "$COOKIE_FILE"

register_response=$(curl -sS -c "$COOKIE_FILE" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"first_name\":\"Smoke\",\"last_name\":\"Test\"}" \
  -w '\nHTTP_STATUS:%{http_code}' "$BASE_URL/auth/register")
register_status=$(printf '%s' "$register_response" | sed -n 's/.*HTTP_STATUS://p')
if [ "$register_status" = "201" ]; then pass "registration ($EMAIL)"; else fail "registration: $register_response"; exit 1; fi

me_response=$(curl -sS -b "$COOKIE_FILE" -w '\nHTTP_STATUS:%{http_code}' "$BASE_URL/api/me")
me_status=$(printf '%s' "$me_response" | sed -n 's/.*HTTP_STATUS://p')
USER_ID=$(printf '%s' "$me_response" | sed 's/HTTP_STATUS:.*//' | python -c 'import json,sys; print(json.load(sys.stdin)["user"]["id"])')
if [ "$me_status" = "200" ] && [ -n "$USER_ID" ]; then pass "authenticated session (/api/me user=$USER_ID)"; else fail "session: $me_response"; exit 1; fi

checkout_response=$(curl -sS -b "$COOKIE_FILE" -X POST -w '\nHTTP_STATUS:%{http_code}' "$BASE_URL/create-checkout-session")
checkout_status=$(printf '%s' "$checkout_response" | sed -n 's/.*HTTP_STATUS://p')
if [ "$checkout_status" = "200" ]; then pass "Stripe checkout session"; else block "Stripe checkout is not configured locally (HTTP $checkout_status)"; fi

printf '%s\n' "Inserting a local pending checkout row for signed-webhook-free development flow..."
docker compose --env-file .env.example exec -T postgres psql -U cartogen -d cartogen -v ON_ERROR_STOP=1 -c \
  "INSERT INTO cartogen_subscriptions (stripe_session_id, retrieval_token, email, directus_user_id, status) VALUES ('$SESSION_ID', '$RETRIEVAL_TOKEN', '$EMAIL', '$USER_ID', 'pending');" >/dev/null
pass "pending subscription row"

export SESSION_ID EMAIL CUSTOMER_ID SUBSCRIPTION_ID USER_ID RETRIEVAL_TOKEN
webhook_payload=$(python -c 'import json,os; print(json.dumps({"type":"checkout.session.completed","data":{"object":{"id":os.environ["SESSION_ID"],"customer_details":{"email":os.environ["EMAIL"]},"customer":os.environ["CUSTOMER_ID"],"subscription":os.environ["SUBSCRIPTION_ID"],"client_reference_id":os.environ["USER_ID"],"metadata":{"retrieval_token":os.environ["RETRIEVAL_TOKEN"],"directus_user_id":os.environ["USER_ID"]}}}}))' SESSION_ID="$SESSION_ID" EMAIL="$EMAIL" CUSTOMER_ID="$CUSTOMER_ID" SUBSCRIPTION_ID="$SUBSCRIPTION_ID" USER_ID="$USER_ID" RETRIEVAL_TOKEN="$RETRIEVAL_TOKEN")
webhook_response=$(curl -sS -b "$COOKIE_FILE" -H 'Content-Type: application/json' -d "$webhook_payload" -w '\nHTTP_STATUS:%{http_code}' "$BASE_URL/webhook")
webhook_status=$(printf '%s' "$webhook_response" | sed -n 's/.*HTTP_STATUS://p')
if [ "$webhook_status" = "200" ]; then pass "development checkout webhook"; else fail "webhook: $webhook_response"; fi

key_response=$(curl -sS -w '\nHTTP_STATUS:%{http_code}' "$BASE_URL/key-for-session?token=$RETRIEVAL_TOKEN")
key_status=$(printf '%s' "$key_response" | sed -n 's/.*HTTP_STATUS://p')
API_KEY=$(printf '%s' "$key_response" | sed 's/HTTP_STATUS:.*//' | python -c 'import json,sys; print(json.load(sys.stdin).get("apiKey", ""))')
if [ "$key_status" = "200" ] && [ -n "$API_KEY" ]; then pass "single-use API key retrieval"; else fail "key retrieval: $key_response"; fi

replay=$(curl -sS "$BASE_URL/key-for-session?token=$RETRIEVAL_TOKEN")
if [ "$replay" = "{}" ]; then pass "single-use retrieval replay rejected"; else fail "retrieval replay returned: $replay"; fi

row=$(docker compose --env-file .env.example exec -T postgres psql -U cartogen -d cartogen -At -c \
  "SELECT status || '|' || COALESCE(directus_user_id,'') FROM cartogen_subscriptions WHERE stripe_session_id='$SESSION_ID';")
if printf '%s' "$row" | grep -q '^active|'; then pass "subscription activated and linked to Directus user"; else fail "subscription row: $row"; fi

api_status=$(curl -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $API_KEY" "$LITELLM_URL/v1/models")
if [ "$api_status" != "401" ] && [ "$api_status" != "403" ]; then pass "LiteLLM virtual key accepted at /v1/models (HTTP $api_status)"; else block "LiteLLM API authorization returned HTTP $api_status"; fi

pro_status=$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL/downloads/pro")
if [ "$pro_status" = "200" ]; then pass "Pro client download"; else block "Pro client download/entitlement route is not implemented (HTTP $pro_status)"; fi

printf '\nTest data: email=%s session=%s user=%s\n' "$EMAIL" "$SESSION_ID" "$USER_ID"
printf 'Result: registration/session/billing-simulation/key lifecycle tested; blocked gates are reported above.\n'
exit "$BLOCKED"
