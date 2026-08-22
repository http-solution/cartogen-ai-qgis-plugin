"""
Cartogen API gateway provider client -- STUB, NOT WIRED IN.

This client is not registered in `agent/providers/__init__.py`'s exports (deliberately --
importing it there would invite `ui/settings_dialog.py` or `agent/agent.py` to start
offering it as a real provider option before it's one), not exposed anywhere in
`ui/settings_dialog.py`'s provider dropdown, and not connected to any live backend.

Why this exists now: `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` (a proposal, not a
decision) scopes a Cartogen-operated model gateway as the default connectivity path for
its proposed Community/Pro tiers, and section 6 item 2 of that document calls out that
`agent/providers/cartogen.py` was the one missing piece on the client side -- every other
provider (`openrouter.py`, `gemini.py`, `openai.py`, `claude.py`, `ollama.py`) already has
a client here, this one didn't. `service/README.md`'s own punch list lists "pointing the
actual QGIS plugin at this gateway as a provider option" as the last, not-yet-done item,
after several other gaps (real customer/key database, per-tier Stripe-to-budget mapping,
subscription lifecycle handling, website auth) that are also still open. None of those
backend pieces exist yet, so there is nothing real for this client to talk to -- this file
only gets the client-side interface shape ready ahead of that, matching this codebase's
existing pattern of standing up a client's shape before the backend behind it is real.

What this is NOT, on purpose (do not extend this file to do any of the following without
first confirming the backend and the tier/licensing decision from the proposal doc are
actually resolved):
  - Not imported by `ui/settings_dialog.py` or any provider-selection UI.
  - Not imported by `agent/providers/__init__.py`'s `__all__`.
  - Not connected to any tier/license gating concept (none exists in this codebase yet).
  - Not pointed at a real, deployed gateway -- `GATEWAY_BASE_URL` below is a placeholder
    domain, not a live endpoint. `service/gateway/` only runs locally per its own README,
    with no deployed URL anywhere in this repo.

Protocol shape: LiteLLM Proxy (what `service/gateway/litellm_config.yaml` configures)
exposes an OpenAI-Chat-Completions-compatible `/v1/chat/completions` endpoint in front of
whichever real provider it's proxying, authenticated with a per-client "virtual key" issued
by `service/website/`'s Stripe-checkout flow instead of a raw provider API key. That makes
this client's request/response shape closest to `openai.py`'s `OpenAIClient` (raw
`requests` + `post_with_retry`, same `DEFAULT_MAX_TOKENS` cap, same
`{"message": ..., "model": ...}` / `{"error": ...}` return contract every other
`BaseAiProvider` implementation here uses) rather than a provider-specific SDK.
"""

import json
import requests
from .base import BaseAiProvider, post_with_retry, DEFAULT_MAX_TOKENS, extract_openai_style_usage
from ..model_selector import filter_chat_model_ids

# Placeholder only -- no gateway is deployed at this or any other real domain today.
# service/gateway/ only runs locally (see service/README.md). Now overridable via
# QgsSettings("cartogen_ai/cartogen_gateway_url") -- see agent.py's construction of
# this client -- with this constant as the fallback default, per
# docs/PRO_TIER_BUILD_PLAN_2026-08-21.md item 1.4.
GATEWAY_BASE_URL = "https://gateway.cartogen.ai/v1/chat/completions"


def _models_url(base_url):
    """Derives the OpenAI-compatible /v1/models listing endpoint from the
    chat/completions base_url, so this stays correct if GATEWAY_BASE_URL (or a
    QgsSettings override) ever changes host/path -- same host, sibling path,
    per LiteLLM's OpenAI-compatible proxy surface."""
    base = (base_url or GATEWAY_BASE_URL).rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    return base + "/models"


def list_models(api_key, base_url=None):
    """Fetches the live model list from the gateway's /v1/models endpoint --
    same shape as openai.py's list_models, since LiteLLM's proxy exposes an
    OpenAI-compatible surface. Untested against a real gateway, like the rest
    of this stub (see module docstring) -- no gateway is deployed anywhere
    this repo can reach yet."""
    try:
        response = requests.get(
            _models_url(base_url),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        ids = [m.get("id", "") for m in data.get("data", [])]
        return {"success": True, "models": filter_chat_model_ids(ids)}
    except requests.exceptions.HTTPError as e:
        return {"error": f"Cartogen gateway models list failed ({e.response.status_code}): {e.response.text}"}
    except Exception as e:
        return {
            "error": f"Cartogen gateway models list request failed: {e} (this is a stub client "
            "-- no gateway is deployed yet; see this module's docstring and service/README.md)"
        }

# Matches the `model_name` aliases service/gateway/litellm_config.yaml defines today
# (each mapped to a real underlying model + provider key on the gateway side) -- NOT
# real, callable model IDs against any live endpoint yet. First entry is the default;
# same "user's configured model first, fallbacks after" shape as openai.py's
# FALLBACK_MODELS, kept here for interface-shape consistency even though there's no
# live gateway yet to actually fail over against.
FALLBACK_MODELS = ["claude-default", "gpt-default"]


class CartogenClient(BaseAiProvider):
    """Stub client for the Cartogen-operated model gateway. Implements the same
    `BaseAiProvider` interface every other provider client in this package does
    (`complete`, `set_status_callback`), so it's a drop-in once the gateway is real and
    this is actually wired into provider selection -- neither of which has happened yet.
    """

    def __init__(self, api_key, model=None, base_url=None, status_callback=None):
        # `api_key` here is a LiteLLM *virtual* key (per `service/website/`'s
        # Stripe-webhook-issued keys), not a raw provider API key -- same field name as
        # every other client for interface consistency, different meaning underneath.
        self.api_key = api_key
        primary = model or FALLBACK_MODELS[0]
        self.models = [primary] + [m for m in FALLBACK_MODELS if m != primary]
        self.model = primary
        self.base_url = base_url or GATEWAY_BASE_URL
        self._status_callback = status_callback

    def set_status_callback(self, callback):
        self._status_callback = callback

    def _emit_status(self, text):
        if self._status_callback:
            try:
                self._status_callback(text)
            except Exception:
                pass

    def _post(self, messages, tools, model_id, max_tokens=None):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": model_id, "messages": messages, "max_tokens": max_tokens or DEFAULT_MAX_TOKENS}
        if tools:
            payload["tools"] = tools
        return post_with_retry(self.base_url, headers, json.dumps(payload), timeout=60)

    def complete(self, messages, tools=None, max_tokens=None):
        """Same shape as OpenAIClient.complete() -- including its per-model 404
        fallback loop, since a LiteLLM proxy returns the same 404-on-unknown-model
        behavior an OpenAI-compatible endpoint does. Untested against a real gateway
        (none is deployed anywhere this repo can reach) -- this is the interface shape
        the eventual real client should fit, not a verified-working integration."""
        for idx, model_id in enumerate(self.models):
            self.model = model_id
            self._emit_status(f"Using Cartogen gateway: {model_id}")
            try:
                response = self._post(messages, tools, model_id, max_tokens=max_tokens)
                if response.status_code == 404:
                    next_idx = idx + 1
                    if next_idx < len(self.models):
                        self._emit_status(f"Model unavailable, switching to {self.models[next_idx]}...")
                    continue
                response.raise_for_status()
                data = response.json()
                out = {"message": data["choices"][0]["message"], "model": model_id}
                # LiteLLM's proxy passes through the underlying provider's real
                # OpenAI-shaped usage object unmodified -- same extraction as
                # openai.py. Untested against a real gateway, like the rest of
                # this stub (see module docstring).
                usage = extract_openai_style_usage(data)
                if usage is not None:
                    out["usage"] = usage
                return out
            except requests.exceptions.HTTPError as e:
                return {"error": f"Cartogen gateway API error ({e.response.status_code}): {e.response.text}"}
            except Exception as e:
                return {
                    "error": f"Cartogen gateway request failed: {e} (this is a stub client -- no gateway "
                    "is deployed yet; see this module's docstring and service/README.md)"
                }

        tried = ", ".join(self.models)
        return {
            "error": (
                f"No configured Cartogen gateway model is currently available (all returned 404). "
                f"Models tried: [{tried}]. This is a stub client with no deployed gateway behind it -- "
                "see this module's docstring and service/README.md."
            )
        }
