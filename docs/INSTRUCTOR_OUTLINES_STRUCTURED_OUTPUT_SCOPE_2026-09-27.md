# Structured LLM output (Instructor/Outlines) — not recommended; a cheaper native fix exists

**Status: scoping document, not a build plan.** Alaa asked to scope `Instructor`/`Outlines` as
structured-output enforcement, the last of the original 5-library list, following the same method
as the four prior 2026-09-27 scoping docs: find the real gap first, install the real libraries,
test them against this project's actual code and data, report what actually happened.

**The short version: there is a real gap (two call sites ask the model to "respond as JSON only"
in prose and parse defensively, with no retry on failure), but both candidate libraries require an
architectural change this project has deliberately avoided — wrapping the official provider SDKs
— to get their real benefit. All 5 of this project's providers already expose a cheaper, native fix
for the same gap (schema-constrained output built into their own plain HTTP APIs) that needs no
new dependency at all.**

## 1. The real gap, found by reading the code first

`core/services/prompt_refiner.py` has two call sites that ask the model to produce JSON inside a
plain-text system prompt instruction ("Respond as JSON only, no other text: ...") and parse the
result defensively:

- `build_refinement_messages`/`parse_refinement_response` (the request-refinement feature: two
  rewritten prompt suggestions).
- `build_disambiguation_messages`/`parse_disambiguation_response` (line ~360/370: task-register
  disambiguation, currently defined but not wired into any live call path).

Both follow the same pattern, explicitly documented in `parse_refinement_response`'s own
docstring: `json.loads` wrapped in try/except, **degrading to `None`/an error on any malformed
shape, with no retry.** This is a real, narrow gap — the two things `agent_orchestrator.py`'s
`json.loads` call sites (also checked) do NOT share this shape with: those parse the model's
native **tool-call arguments**, which every provider here sends back as a distinct structured
field already validated by the provider's own function-calling machinery, not free text embedded
in prose. The prompt-refiner gap is the one place this project asks a model to freehand JSON in a
chat message and hopes it's well-formed.

No live bug report names this specific failure (grepped `docs/BUG_TRACKER.md` for "malformed
refinement", "invalid JSON response" — no hits), but the code's own comments already anticipate it
happening (hence the defensive `try/except`), and two related, confirmed live bugs
(`BUG-2026-09-13-2`, `BUG-2026-09-13-4`) show this codebase does get bitten by malformed external
JSON in practice, just from network APIs, not yet from a model's own free-text JSON.

## 2. What was actually tested

### 2a. Instructor v1.17.0 — works, but only via the same SDK-client wrapping this project doesn't use

Built a live test with `instructor.Instructor(client=None, create=<fn>, mode=Mode.JSON)`,
wrapping a fake completion function, using a Pydantic model mirroring `prompt_refiner.py`'s real
refinement schema (`detected_profile` + exactly 2 `recommendations`). **First attempt: silently
did nothing** — the low-level `Instructor(create=...)` constructor accepted a raw callable but
passed `response_model` straight through to it instead of validating the result; the returned
object was the unvalidated fake completion. Root-caused by inspecting `instructor/v2/providers/*/handlers.py`:
response parsing is hard-coded per provider to each provider's own SDK response object shape
(`.choices[0].message.content`, attribute access, not dict access) — the officially working path
requires `instructor.from_openai()`/`from_anthropic()`/etc. wrapping a **real `openai.OpenAI()` or
`anthropic.Anthropic()` SDK client instance**, not a bare function.

**Second attempt, done the way Instructor's docs actually intend:** constructed a real
`openai.OpenAI()` client object, monkeypatched its `.chat.completions.create` to a fake function
that returns a malformed response (1 recommendation instead of 2) on the first call and a valid
one on the second, wrapped it with `instructor.from_openai(...)`. **This worked exactly as
advertised:** the first, invalid response was rejected by Pydantic validation, Instructor
automatically reprompted with the validation error, and the second call produced a fully validated
`RefinementResponse` object — 2 calls total, 0 manual retry code. This is the real, demonstrated
value: automatic retry-with-validation-feedback, which is strictly better than today's
`parse_refinement_response` returning `None` on the first failure with no second attempt.

**The catch:** getting that real behavior requires an actual `openai.OpenAI()` (or
`anthropic.Anthropic()`) SDK client object as the thing being wrapped — `pip install instructor`
pulls in the full `openai` SDK (3.3.0) as a hard dependency even to use `Mode.JSON` against a
non-OpenAI backend. This project's 5 providers (`infrastructure/providers/*.py`) deliberately do
**not** use any official SDK — every one of them is a bespoke `requests`-based HTTP client
returning a plain dict (confirmed reading `openai.py`, `ollama.py`: `payload = {...}`,
`requests.post(url, json=payload)`, `result.get("message")`), a real, load-bearing architectural
choice this project has kept consistently across all 5 providers, all the way down to raw-dict
provider responses with no schema layer anywhere in `core/models/`. Getting Instructor's real
value would mean rebuilding at least one provider on top of the actual SDK client object it needs
to wrap, not just adding a package.

### 2b. Outlines v1.3.3 — its API-provider wrappers do not do what the name implies

Outlines' actual value proposition — token-level grammar-constrained decoding, guaranteeing
schema-valid output structurally rather than by retrying — only applies to backends it directly
controls generation for: `Transformers`, `VLLM`, `LlamaCpp`, `MLXLM` (local model weights loaded
into the same process). Its `OpenAI`/`Anthropic`/`Gemini`/`Ollama` model wrappers
(`outlines.models.from_openai`, etc., confirmed present in v1.3.3's `outlines.models` namespace)
are thin proxies onto those providers' own native structured-output parameters — they do not, and
by the nature of a remote HTTP API cannot, give Outlines any real control over token generation on
a provider this project doesn't host itself. For every one of this project's 5 providers, using
Outlines here would mean paying its dependency cost for no capability beyond what's covered in §3
for free.

The one place real constrained decoding could theoretically apply is Ollama, since it's the one
provider running a local model this project could plausibly influence more directly — but that
would mean loading a model via `Transformers`/`LlamaCpp` directly inside the plugin process
(a fundamentally different, heavier integration than talking to Ollama's existing HTTP server the
way `ollama.py` does today), not just calling `outlines.models.Ollama`, which is the same
thin-proxy-over-HTTP shape as the cloud wrappers. Not evaluated further — a materially different
proposal than "add Outlines," out of scope here.

## 3. The cheaper fix both libraries are trying to work around

Every one of this project's 5 providers already exposes native, schema-constrained structured
output through its own plain HTTP API, unused today:

| Provider | Native mechanism | Used by this project today? |
|---|---|---|
| OpenAI | `response_format: {"type": "json_schema", "json_schema": {..., "strict": true}}` in the Chat Completions payload | No — `openai.py`'s payload has no `response_format` key |
| Gemini | `generationConfig.responseSchema` / `responseMimeType: "application/json"` | No — checked `gemini.py`, not present |
| Claude | Tool-use forced to a single schema (`tool_choice: {"type": "tool", "name": "..."}`) — no separate free-text JSON mode, but the same tool-calling machinery `agent_orchestrator.py` already drives for real tools | Not for prompt_refiner's calls (`tools=None` is passed deliberately there, per `refine()`'s own docstring) |
| Ollama | `format: <json-schema-object>` in the `/api/chat` or `/api/generate` payload, backed by real GBNF grammar-constrained decoding server-side (the same real guarantee Outlines' local backends offer, already running for the one local provider this project ships) | No — checked `ollama.py`'s payload construction, not present |
| OpenRouter | Passes through `response_format` to the underlying model, OpenAI-compatible | No — checked `openrouter.py`, not present |

This is not tested live here (no live API keys/servers available in this sandbox for any of the
5), but it is each provider's own documented, stable API surface — not a claim requiring library
testing the way Instructor's/Outlines' actual behavior did. **If the `prompt_refiner.py` gap (§1)
is worth closing, adding a `response_format`/`format` field to the existing raw-dict payloads in
each provider's `complete()` is a same-shape, same-architecture change** — no new dependency, no
SDK-client rewrite, consistent with every other provider-specific quirk these 5 files already
handle individually (auth header shape, usage-field extraction, model-listing endpoint).

## 4. Recommendation

**Do not adopt Instructor or Outlines.** Not because the gap they're aimed at isn't real (§1 is a
real, if narrow and not-yet-live-reported, gap), but because both libraries' actual value is gated
behind an SDK-client architecture this project has deliberately not built, and — for Outlines
specifically — its remote-provider wrappers don't provide the library's real benefit at all (§2b).

**If `prompt_refiner.py`'s no-retry-on-malformed-JSON gap is worth closing, the smaller fix is:**
add each provider's native `response_format`/`format` schema parameter (§3) to their existing
`complete()` payloads, and add one retry loop in `prompt_refiner.refine()` itself (call again with
the validation failure appended to the messages, matching the pattern Instructor demonstrated in
§2a working correctly, just implemented directly rather than through a library) — a same-shape,
same-dependency-footprint change consistent with how every other provider quirk in this codebase
is already handled. This is a real, sizeable follow-up (5 providers' worth of payload changes plus
a retry loop plus tests), not a one-liner, and — per this repo's own `CLAUDE.md` guidance to flag
judgment calls rather than decide them unilaterally — whether it's worth building at all given no
live incident has reported this gap yet is logged as an open item in
`docs/IMPLEMENTATION_TRACKER.md` §1.14, not decided here.

Not built. `instructor`, `outlines`, `openai`, and `pydantic` were removed from this environment
after testing; none of this is a new dependency of this repo.

## 5. What was and wasn't verified

- Verified live: Instructor's actual retry-with-validation-error behavior, using a real
  `openai.OpenAI()` SDK client object with its `create` method monkeypatched to a fake completion
  function — a genuinely working reproduction of Instructor's core claim, not taken from its
  documentation.
- Verified live: Instructor's low-level `Instructor(client=None, create=<fn>)` constructor does
  **not** validate/retry when given a bare callable instead of a real SDK client object — confirmed
  by direct testing, not assumed from reading the source.
- Verified by direct source inspection, not live API calls (no live API keys/servers available in
  this sandbox for any of this project's 5 providers): Outlines v1.3.3's `outlines.models`
  namespace contains `OpenAI`/`Anthropic`/`Gemini`/`Ollama` wrappers, and this project's own
  `infrastructure/providers/*.py` files currently send no `response_format`/`format`/schema
  parameter to any of the 5 providers.
- Not verified live: that OpenAI/Gemini/Ollama/OpenRouter's native `response_format`/`format`
  parameters (§3) actually produce schema-conformant output against a real API call — this is
  each provider's own documented, stable feature, not something this scoping pass could test
  without live credentials, and is flagged as the one part of this document's recommendation that
  rests on documentation rather than this project's own live-testing methodology.
- Not verified: Claude's tool-forcing route (`tool_choice: {"type": "tool", ...}`) as a structured
  output mechanism for `prompt_refiner.py` specifically — `refine()` deliberately passes
  `tools=None` for reasons stated in its own docstring (keeping this call out of
  `ToolRouter`/`TOOLS_SCHEMA` territory), so using Claude's tool-forcing here would need its own
  smaller, separate design decision, not evaluated further.
