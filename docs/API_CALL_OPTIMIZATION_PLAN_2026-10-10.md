# API call optimisation plan -- 2026-10-10

Status: **plan, nothing in section 4 is built yet.** Section 2 is measured on `main` (`63ceace`+) with the repo's own prompt builder and tool router; section 1 is the owner's observation. Token figures are characters / 4, an estimate, not a provider count. The provider-reported counts come from the `model_call` log lines the rc23 cost work added; compare the two before trusting any saving below. Builds on `docs/COST_AND_ROUTING_PLAN_2026-10-09.md` (measurement, `run_steps`, chains, loop guard, token budget), which this plan does not repeat.

## 1. The problem

The principle: **a model call should happen only for what code cannot answer or decide**: interpreting an ambiguous request, choosing among real options, acquiring data, writing narrative. Everything else (reading the project, running a fully specified tool, formatting a result) should run locally. Today it does not:

- A plain "List the layers" took **13 API calls** in the rc24 hand test (cause not yet found; needs the `Agent` log lines for that turn).
- One call is about **20,000 tokens** before the conversation is even added (section 2).
- The model is asked to do bookkeeping that code could do (section 3.3).

## 2. Measured baseline (per model call, before history)

| Part | Size | Notes |
|---|---|---|
| System prompt (56 rules + map context) | **~9,900 tokens** | Humanitarian, security, cartography, hydrology and scheduling rules are sent on every call, including "List the layers". Largest single rule ~1,600 chars |
| Tool schemas, 40 offered tools | **~12,900 to 19,100 tokens** | `ToolRouter.filter_relevant_tools(top_k=40)` always returns 40 for a real request; 9 for a greeting. The biggest tools alone are 3,400 to 5,400 chars each (`generate_temporal_dashboard`, `compute_jiaf_preliminary`, `add_point_layer`, `create_print_layout`) |
| **Total** | **~22,900 (list layers) to ~29,000 (severity index)** | Resent in full on every round trip |
| All 208 tool schemas | ~60,500 tokens | For scale only; never sent at once |

Experiment (same 40 tools, descriptions cut to their first sentence and parameter descriptions removed): schemas fall from 15,600 to **4,700** tokens for a buffer-and-clip request and from 19,100 to **5,900** for a severity-index request (about -70%). The 12 best-ranked tools alone, compacted, are about 1,000 to 1,300 tokens.

Other facts from the code and the owner's sample request:
- Prompt caching is wired for Claude (and OpenRouter Claude routes) via `cache_control`. For **Gemini**, the owner's usual provider (40 of 41 recent sessions), no explicit caching is configured; whether Gemini's implicit caching hits is **unknown** until cached-token counts are read from real runs. The tool list changes per request, which is hostile to any prefix cache.
- `update_task` was the second most used tool (68 calls) in the owner's usage pattern: the prompt's rule 2 makes the model call it after each plan step.
- `MAX_ITERATIONS = 20`; the loop guard and token budget (rc23) cap a runaway but do not lower the normal cost.

## 3. Where the calls and tokens go

1. **Requests the code could answer or execute without a model.** The plugin already shows this works: confirmations, `how-to` questions, the preview/queue logic and (PR #254) "List the layers" are handled locally. Most read-only questions are the same shape.
2. **Fixed overhead per call.** ~10K prompt + 13-19K schemas, multiplied by every round trip. Two round trips (call a tool, then write the answer) already cost ~45K tokens for a one-tool request.
3. **Model-driven bookkeeping.** `create_plan` / `update_task` calls, `get_layers` / `get_attributes` calls for facts already in the map context, and a final model call that mostly repeats the tool result.
4. **Extra rounds injected by the app.** Nudges (sandbox flailing, tool-name drift, look follow-up, missing file) append a user message and cost another round. Each is justified alone; together they are unmeasured.
5. **Unknown:** why "List the layers" took 13 calls. Candidates: repeated `get_layers` (exempt from the duplicate-call guard), plan creation and updates, provider retries after 429/404, nudges.

## 4. Plan

### Track A -- Local-first execution (largest saving: zero calls)

Add a deterministic **local dispatcher** ahead of the agent: parse the request with code, resolve layer and field names against the open project, run the tool, format the answer from the tool result, and call a model only when parsing fails or confidence is low.

- **A1. Project reads, no tool needed (done for one):** list layers (PR #254); then layer details (fields, CRS, feature count, extent, geometry type), project CRS, active layer, selected-feature count, unique values of a field, min/max/mean/sum of a numeric field, total area / length.
- **A2. Fully specified single-tool commands:** "buffer X by N m", "clip A with B", "reproject X to EPSG:n", "zoom to X", "select by expression", "export X to CSV/GeoPackage", "show X on the map" (the existing look hints). The slot filling, validation and preflight already exist in `discovery.py` / `step_runner.py` / `chains.py`; reuse them.
- **A3. Template answers from tool results:** each tool gets a result formatter so a successful run needs no summarising model call. The destructive-action confirmation, egress gate and PREVIEW_REQUIRED flow stay exactly as they are.
- **A4. Fallback is the model**, with the dispatcher's findings (what it resolved, what is missing) passed as context so the model starts further along.
- Safety: nothing here may bypass the confirmation gate, the egress gate or the "no invented facts" guards; the local path produces its answer only from tool results.

### Track B -- Smaller calls when a model is needed

- **B1. Compact tool schemas (~-70% of 13-19K).** Send each offered tool as name + one-sentence description + parameter names/types; expand to the full schema only for the tool the model selects (a second, small lookup inside the loop) or for tools in the top 3 by rank. `find_tools` / `run_steps` already show the model can discover tools.
- **B2. Fewer tools per call.** Offer 8-12, not 40, with the router's confidence deciding; `find_tools` covers misses.
- **B3. Rule packs for the system prompt (~10K to ~3K).** Keep a small core (identity, environment, safety, honesty rules). Attach domain packs (humanitarian logistics, security briefings, cartography/styling, hydrology, scheduling, JIAF) only when the matched capability or offered tools need them. `capabilities.py` already carries the capability → tool mapping.
- **B4. Stable prefix for caching.** Order: static core, static packs for the session, then per-request tools and context. Enable provider caching where supported (Gemini explicit cached content for the core + packs; Claude already). Report cached-token counts and treat "cache hit rate" as a metric.
- **B5. Trim what is resent.** Cap tool-result size sent back (table rows, attribute dumps), keep the existing history compaction, drop the "ACTIVE TASK PLAN" tool-result text from the prompt (it also leaks attribute values to the provider).

### Track C -- Fewer round trips

- **C1. Code-driven plan tracking.** The app marks plan steps done from tool results; remove the rule that makes the model call `update_task` after each step. No `create_plan` for requests that resolve to one or two tool calls.
- **C2. Answer from the map context first.** Do not let the model call `get_layers` / `get_attributes` for facts already in the context (count `get_layers` calls per turn in the guard; it is currently exempt from duplicate detection).
- **C3. Find the 13-call cause** from the owner's log, then add a regression test (scripted client, call budget per scenario).
- **C4. One nudge per turn in total**, not one per kind, and measure how many rounds nudges add.
- **C5. Model tiering:** a small/fast model for routing and simple answers, the large model only for planning and interpretation (the auto-select hook exists).

### Track D -- Measure and show it (needed for the showcase and for integration)

- **D1. Benchmark suite:** 20 to 30 scripted requests (reads, single tools, multi-step, ambiguous, data acquisition) with a recorded call count and token total per request, run against a scripted client in CI (no network) and against a real provider by hand.
- **D2. Budgets enforced in CI:** fail the build if the core system prompt, the compacted schema set for a request, or a scenario's call count exceeds its budget (a regression test, like the docs-in-sync test).
- **D3. In-product metrics:** per request and per session: model calls, input / cached / output tokens, share of requests answered locally, cost estimate. The rc23 footer already shows tokens; add the local-answer share.
- **D4. A one-page metrics report** generated from D1/D3 for demos and integration partners.

## 5. Targets (to be confirmed against D1 after each phase)

| Request type | Today (estimate) | Target |
|---|---|---|
| Project read ("list layers", "how many features") | 2+ calls, ~45K tokens (13 calls observed once) | **0 calls** |
| Fully specified single tool | 2 calls, ~50K tokens | **0 to 1 call**, <=8K tokens each |
| Typical multi-step analysis | 5-8 calls, 120-200K tokens | <=4 calls, <=10K tokens each |
| Per-call fixed overhead | ~23-29K tokens | <=8K tokens |

These are goals set from the measurements above, not results.

## 6. Order of work

1. **Phase 1 (days, low risk):** C3 (find the 13 calls), D1/D2 (baseline + budgets), A1 (project reads), C2, C1, B5.
2. **Phase 2 (about a week):** B1 + B2 (compact schemas, fewer tools), B3 (rule packs), D3.
3. **Phase 3:** A2 + A3 (local single-tool commands and result formatters), B4 (caching), C4/C5, D4.

Each phase ends with a measured before/after from D1 on the same scripted scenarios and a hand-test row, and ships in a release candidate with its limits stated.

## 7. Risks and what this does not claim

- Compacting schemas or offering fewer tools can make the model pick the wrong tool or wrong arguments; the benchmark must include arguments-correctness, not only call counts, and `find_tools` must stay available.
- Rule packs can drop a safety rule the request turns out to need; the safety and honesty rules stay in the core, and packs are chosen conservatively (include when in doubt).
- A local parser can misread a request and act; it handles only patterns it matches exactly, resolves names against the project, and defers to the model otherwise. Destructive and outward-facing actions keep their confirmation cards.
- Token numbers here are estimates; a provider's tokenizer and caching change them. Nothing in this plan has been run against a real model.

## 8. Gemini-specific notes (from the owner's optimisation guide, checked against this code)

The owner supplied a "Gemini API deep optimisation" guide on 2026-10-10. Its architecture matches this plan (code-driven state and plan tracking, deterministic reads, compact one-sentence tool descriptions, 8-12 tools per call, rule packs, context first and the query last). What the guide leaves out or states more firmly than I can confirm:

1. **The chat client uses Google's OpenAI-compatible endpoint** (`/v1beta/openai/chat/completions`, `providers/gemini.py`), not native `generateContent` (which is used only for grounded search and model listing). Native features the guide recommends (`tool_config` with `allowed_function_names`, `cachedContent`, a `response_schema`) are not reachable through the chat path as written. Before relying on any of them: check what the compatibility layer accepts (`tool_choice`, extra body fields) or move the chat path to the native API. This is a prerequisite task, not a detail.
2. **Dynamic tool selection and implicit caching pull against each other.** Implicit caching is on by default for Gemini 2.5 and newer and reuses a request's matching prefix; Google's advice is to put large common content at the start and send similar prefixes close together in time. The tool list is part of that prefix, and the router changes it on every request, so everything after the first difference misses. Options to test: a small number of fixed domain tool bundles (so a prefix repeats), or a stable compact catalogue of all tools plus `allowed_function_names` to narrow the choice without changing the prefix. Measure the cached-token count the provider reports before choosing.
3. **Cache minimums are not stable.** A search of Google's docs returned 2,048 (2.5) and 4,096 (3.x) in the latest snapshot, but older revisions list 1,024 and other numbers. The guide's figures match the latest one. Treat them as unverified; read the live caching page (not reachable from this build sandbox) before designing around a threshold. If the optimised prefix ends below the minimum there is no cache discount, but a ~3-8K token prompt is already far cheaper than today's ~25K, so smaller beats cached.
4. **Explicit caching is not needed** at the planned prefix size (the guide agrees): it adds a cache object, a TTL and a storage cost for a prefix of a few thousand tokens.
5. **Structured output together with function calling** (`response_schema` plus tools) is not confirmed here for every model. Do not plan on it until tested; the existing tool-result validation and the reply guards stay the control.
6. **`tool_config` modes** (force a tool, allow none) are a useful way to stop the loop: a final turn with tools disabled must produce text, which removes the "one more tool call" rounds. Needs item 1 first.
7. **Model names and prices in the guide** (Gemini 3.1 Pro, 3.5 Flash, the 90% discount) are not checked here. The plugin lets the user pick the model; nothing in this plan should hard-code one.
8. **Prompt delimiters:** the plugin's system prompt is Markdown with numbered rules. Moving the new rule packs to tagged blocks (`<rules>`, `<project_data>`) is cheap and worth doing while the packs are built, but it is a style change, not a saving, and needs the benchmark to confirm no regression.

Added to the order of work: **Phase 0 (before Phase 1):** check the Gemini compatibility endpoint's supported fields and measure the cached-token count on a real run, so Track B4 is designed on evidence.
