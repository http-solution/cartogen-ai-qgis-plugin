# Cartogen AI — API Cost & Integration Efficiency Review

**Reviewer role:** Software engineer / Python specialist / prompt engineer (LLM integration and API cost)
**Scope:** Where API cost (LLM token spend and external service calls) is being wasted across the agent loop, prompt design, tool routing, and provider integrations — and what to fix, in priority order.
**Method:** Every finding below is measured or reproduced against the actual code (125-tool registry, current `agent/`), not estimated from general LLM-cost folklore. Where a number is an estimate (token counts), it's labeled as such and the method is stated so it can be recomputed.

**Status (2026-08-15):** Tier 1 (§1.1-1.3), Tier 2 (§2.1-2.3), and Tier 3 (§3, all 3 items) implemented -- see the three CHANGELOG entries dated 2026-08-15 for details. §2.1's OpenRouter/Anthropic cache_control addition is unverified against a live response (no network access in this environment to test) -- needs confirming against real usage before being trusted as working. The measurements and analysis below are left as originally written, as the record of what was found; they are not re-verified against the post-fix code.

---

## 0. What was actually measured

- **System prompt size**: `BASE_SYSTEM_PROMPT` in `agent/prompts.py` is 16,591 characters / 2,463 words ≈ **3,300–4,100 tokens** (char/4 and word×1.33 estimates; no network access in this environment to run a real tokenizer, so both methods are given as a cross-check). This is resent as `messages[0]` on **every** iteration of the tool-calling loop in `agent.py`, not just once per user turn.
- **Tool schema size**: parsed all 124 `register_tool(...)` calls via `ast` (one raster-tools entry uses an f-string and wasn't literal-evaluable, so true count is 125). Full registry as JSON-over-the-wire ≈ 78,000 chars ≈ **~19,500 tokens** if every tool were sent; `ToolRouter.filter_relevant_tools(..., top_k=30)` caps what's actually sent to **≈4,700 tokens on average** per call. Combined with the system prompt, a typical turn's *fixed* per-call overhead is **~8,000–9,000 tokens before any user query, chat history, or tool result is counted.**
- **Tool-description size is uneven and growing**: average full schema is 629 chars/tool, but the four newest humanitarian tools run 2,000–3,200 chars each — `calculate_presence_gap` (3,181), `generate_html_dashboard` (2,685), `obfuscate_sensitive_points` (2,291), `population_access_gap` (2,011). These are paid in full on every call where `ToolRouter` selects them, whether or not the model ends up invoking them.
- **`ToolRouter` recall, tested against 9 realistic paraphrased humanitarian queries** (the kind of phrasing a real user types, not the tool's own vocabulary):

  | Query | Expected tool | In top-30? |
  |---|---|---|
  | "which districts are underserved and need more funding" | `calculate_presence_gap` | ✅ (rank 20) |
  | "rank the districts by how bad the situation is" | `calculate_severity_index` | ❌ **missed** |
  | "how many people cannot reach a hospital within an hour" | `population_access_gap` | ✅ (rank 10) |
  | "hide the exact location of these GBV survivors before I share this map" | `obfuscate_sensitive_points` | ✅ (rank 11) |
  | "who else is working in this area" | `load_3w_data` | ❌ **missed** |
  | "get me official admin boundaries with proper codes" | `fetch_hdx_admin_boundaries` | ✅ (rank 10) |
  | "make an interactive map I can send to the donors" | `generate_html_dashboard` | ❌ **missed** |
  | "show reached vs target by cluster" | `generate_sector_coverage_report` | ✅ (rank 13) |
  | "get building outlines for this town" | `fetch_building_footprints` | ✅ (rank 10) |

  **3 of 9 (33%) never made it into the candidate set the model was even allowed to choose from.** A missed tool doesn't just degrade quality — it directly costs money: the turn either fails outright, the model falls back to a heavier `execute_pyqgis_script` workaround, or it burns iterations (each a full API call with the same ~8,000-token fixed overhead) trying something else within `MAX_ITERATIONS`.
- **Prompt caching**: only `ClaudeClient` (`agent/providers/claude.py`) sets `cache_control` on the system prompt and tool schemas. `OpenAIClient`, `GeminiClient`, `OpenRouterClient`, and `OllamaClient` send no caching directives at all — confirmed by grep, zero matches for `cache` across all four files.
- **`model_selector.classify_complexity`**: `history_len > 6` alone forces the "complex" (expensive) tier, with no other signal needed. `history_len` is `len(self.conversation_history)`, which grows by 2 per turn — so **after 3–4 exchanges, every subsequent request in that session is classified complex regardless of content**, permanently defeating auto-routing for any sustained conversation.
- **External-API caching coverage**: `humanitarian_tools.py`'s `_LOOKUP_CACHE` (30-min TTL) covers HDX search, FTS funding, OSM Overpass, geoBoundaries, HDX COD-AB, and the building-footprints tile index — good, consistent coverage. `system_tools.py`'s `_GEOCODE_CACHE` covers geocoding. **`gemini_grounded_search` and `openai_grounded_search` have no caching at all**, despite being real, billed LLM API calls (unlike `search_web`, which is free DuckDuckGo).
- **Unbounded tool-result size**: `calculate_severity_index` and `calculate_presence_gap` return one full entry per admin unit with no cap — confirmed by reading `_compute_severity_index`; no `MAX_`/truncation logic anywhere in `analysis_tools.py`'s severity/presence code. For an ADM3-level layer (routinely hundreds of units), this is a large, uncapped JSON blob that becomes part of the model's context for the rest of the turn *and* persists in `conversation_history` for several more turns after that (`MAX_HISTORY_MESSAGES = 20`). `get_layers` has the same unbounded pattern, lower severity (project layer counts are usually small).

---

## 1. Tier 1 — highest leverage, fix first

### 1.1 Fix `ToolRouter` recall (the 33% miss rate above) — ✅ Done (2026-08-15)

This is the single highest-leverage item: every other optimization in this document only matters if the model can actually see the tool it needs. Layered fixes, cheapest first:

- **Fix the tie-break bug.** `scored_tools.sort(key=lambda x: x[0], reverse=True)` on a list where most tools score 0 relies on Python's *stable* sort, which means 0-score tools fill the remaining `top_k` slots in **fixed file-registration order**, not by any relevance signal. This silently and consistently favors whichever tools happen to be defined earliest across `agent/tools/*.py`, for every query that doesn't score enough real matches. Cheap fix: track a small "recently useful" or "recently mentioned" signal, or at minimum accept this is arbitrary and stop relying on it as if it were a ranking.
- **Add a short alias/synonym list per tool** targeting the paraphrasing gap actually observed above — e.g. `severity`/`needs index` tool should also match "worst", "priority", "rank the districts"; the presence-gap tool should also match "underserved", "understaffed", "who's helping"; the dashboard tool should also match "interactive", "send to donors", "share with". A handful of words per tool, no new dependency, directly closes the measured misses.
- **Raise `top_k` from 30 to ~40.** The registry has grown from 61 (when this router was tuned) to 125 tools without `top_k` being revisited. ~1,500–2,000 extra tokens per call is cheap insurance against a full turn failing and needing to be retried from scratch, which costs far more.
- **Longer-term, only if the above isn't enough**: real embedding-based retrieval. The plugin's own docs already flag keyword/substring matching as a known limitation "worth revisiting if tool count grows much further" — it has. Only worth the added dependency/complexity if (b)/(c) don't close the gap in practice.

### 1.2 Cap tool-result size before it enters the conversation — ✅ Done (2026-08-15)

`calculate_severity_index`/`calculate_presence_gap`'s `results` list has no limit. Since both already sort worst-first, the fix is mechanical and matches a pattern this codebase already uses well elsewhere (`fetch_building_footprints`'s `max_features`/`truncated`, dashboard's `_MAX_DASHBOARD_POPUP_FIELDS`): cap at, say, the top 50–100 entries, add `"total_units": N` and `"showing_top_N": True`, and let the model ask for a specific subset (a district name, a severity-class filter) if it needs more. This isn't just a one-time saving — an oversized result gets resent on every remaining iteration of the same turn *and* lingers in `conversation_history` for several turns afterward, so the cost compounds.

### 1.3 Fix `history_len > 6` in `model_selector.classify_complexity` — ✅ Done (2026-08-15)

As measured above, this makes auto-routing correctly weigh query complexity for roughly the first 3 exchanges of a session and then stop mattering at all — every later request gets the expensive-tier model regardless of whether it's "zoom to that layer" or a genuine multi-step analysis. Fix: either drop message-count as a signal entirely (the query-content signals already present — multi-step phrasing, quantity words, distinct operations — are more meaningful on their own), or scope it to *recent* history only (e.g. tool calls in just the last exchange) so a long-but-otherwise-simple session doesn't get permanently pinned to the capable tier.

---

## 2. Tier 2 — real savings, moderate effort

### 2.1 Extend prompt caching beyond Claude — ✅ Done for OpenRouter (2026-08-15), unverified live; OpenAI/Gemini need live verification only, no code change

Claude's client does this correctly. The other four providers don't opt in anywhere:

- **OpenAI**: automatically caches identical prefixes ≥1024 tokens with no code changes required — but this needs to be *confirmed*, not assumed, since payload composition (which tools got routed, chat history growth) varies turn to turn and could be breaking prefix stability without anyone noticing. Check `usage`-equivalent fields in real responses for cache-hit evidence before crediting this as "already free."
- **Gemini**: implicit caching on 2.5+/3.x models should apply via the OpenAI-compat endpoint this client uses — same "verify, don't assume" caveat.
- **OpenRouter** (the **default provider** new installs land on): passes through to whatever backend it routes to. For Anthropic-backed models specifically, it needs the same explicit `cache_control` block the native Claude client already sends, which isn't happening today. The free-tier fallback chain (`FALLBACK_MODELS`) also means requests may hit a *different* backend turn to turn, which undermines the prefix-stability caching depends on regardless of provider — worth knowing, not necessarily worth "fixing" given the fallback chain's own reliability purpose.

Given the fixed per-call overhead measured in §0 (~8,000–9,000 tokens, repeated on every iteration of every multi-step turn), this is the single largest lever in the document if it isn't already landing on the default provider.

### 2.2 Cache `gemini_grounded_search`/`openai_grounded_search` — ✅ Done (2026-08-15)

Both are real, billed API calls with zero caching, inconsistent with every other "fetch external thing" tool in the codebase. A short TTL cache on the query string (the exact `_LOOKUP_CACHE` pattern already proven in `humanitarian_tools.py`) would catch the common case of the model re-issuing the same or a near-identical search within one turn or a quick follow-up.

### 2.3 Move exhaustive caveats from tool *descriptions* into tool *results* — ✅ Done for the 2 named examples (2026-08-15)

The newest tools' descriptions are 3–5x the registry average specifically because they carry detailed "how to present this to the user" guidance (the CDN/offline caveat on `generate_html_dashboard`, the baseline-not-live caveat on `fetch_building_footprints`, etc.). That guidance is only actually needed on the call where the tool gets invoked — but it's currently paid on **every** call where `ToolRouter` merely selects the tool as a candidate, invoked or not. Several tools already return a `warnings`-style field in their result; extending that pattern to carry the presentation guidance there instead of in the schema description keeps the model well-informed exactly when it matters, while cutting the fixed cost of every candidate turn that doesn't end up calling that tool.

---

## 3. Tier 3 — lower urgency, worth doing, not urgent

- **No `max_tokens` cap on OpenAI/Gemini/OpenRouter/Ollama requests.** Only Claude's client sets `DEFAULT_MAX_TOKENS`. Rarely an issue in practice (tool-calling responses are typically short), but a real, if uncommon, runaway-output cost risk — cheap to standardize. — ✅ Done (2026-08-15)
- **`pick_model_for_complexity`'s "shortest model name = simple tier" fallback is fragile** (string length isn't a reliable proxy for model size/cost) but only engages when no keyword match exists at all, which `_CHEAP_KEYWORDS`'s current coverage makes rare. Worth tightening opportunistically, not urgent. — ✅ Done (2026-08-15)
- **Add a small routing-recall regression test.** The 33% miss rate in §0 is a direct symptom of the tool registry roughly doubling (61→125) without `ToolRouter` or description conventions being revisited. A fixed set of representative queries → expected tool, checked in the test suite the same way this codebase already protects its security invariants, would catch future recall regressions before they ship rather than after a user notices a missing tool. — ✅ Done (2026-08-15)

---

## 4. Deliberately not recommending

- **Don't reduce `MAX_ITERATIONS` (20) or the retry/backoff logic in `base.py`/`openrouter.py`.** Both exist because of specific, previously-reproduced failure modes (documented in this codebase's own commit history: two real UI-freeze bugs, a rate-limit death spiral, a too-tight iteration cap that broke legitimate multi-step requests). Cutting either trades a real cost saving for a worse failure mode — a user manually retrying a failed turn costs more (in tokens and trust) than letting the current one finish.
- **Don't shrink `map_context`'s existing caps.** `MAX_LAYERS = 15` and per-layer field truncation are already sensible bounds; no evidence of waste there.
- **Don't cut system-prompt rules to save tokens.** Each of the 29 rules in `BASE_SYSTEM_PROMPT` reads as tied to a specific, previously-observed failure mode (per this codebase's own comments and CHANGELOG discipline) — removing one to save ~50–100 tokens risks reintroducing the bug it was written to prevent, which costs far more in wasted turns than the prompt line itself.

---

## 5. Suggested order of work

1. §1.1 (ToolRouter recall) — highest leverage, no dependency on anything else, and every other fix's value is capped by whether the model can see the right tool in the first place.
2. §1.2 (result-size cap) and §1.3 (`history_len` fix) — both small, independent, mechanical changes.
3. §2.1 (verify/extend caching) — start by *measuring* actual cache-hit behavior on the default provider (OpenRouter) before writing any code; this could turn out to already be partially working, or could be the biggest single win in the document.
4. §2.2 and §2.3 — small, low-risk, can be done opportunistically alongside other tool-file edits.
5. §3 items — fold into other work touching the same files rather than a dedicated pass.
