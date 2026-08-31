# Prompt Refinement Layer — Specification

**Status: SHIPPED (2026-08-15).** Every piece described below is built -- `agent/prompt_refiner.py`,
the `max_tokens` threading across all 5 provider clients, the Settings keys/UI, and the two-card panel
in `ui/dock_widget.py` -- the full test suite (579/579 on both trees) is green, and §10's live QA has
been run and confirmed working against all 5 providers, including the Ollama/local-model case and the
Settings-off true-no-op case. See the CHANGELOG's 2026-08-15 "Implemented the Prompt Refinement Layer"
entry for the full list of what changed and why. The design below is left as originally written, as the
record of what was specified; it is not retroactively edited to describe the implementation's exact
code shape.

---

## 1. Problem

Today, whatever the user types goes straight from `ChatInputEdit` into `agent.run(user_query, ...)`
(`ui/dock_widget.py` → `_send_message`, line ~952). Two consequences of that directness:

- **Ambiguous or underspecified requests burn a full agentic turn to discover they're ambiguous.**
  The model has to ask a clarifying question back, or guess — either way costs a full tool-enabled
  turn (system prompt + up to 40 routed tool schemas, per `docs/API_COST_OPTIMIZATION_REVIEW.md`
  §0) before the user even knows the request landed correctly.
- **`ToolRouter.filter_relevant_tools()` (`agent/tool_router.py`) is keyword/substring matching, not
  semantic.** A vague query ("show me the flood situation") gives it little to match against and can
  miss the right tools (the cost-optimization review's 9-query recall test found 3/9 misses for
  exactly this reason). A query phrased with concrete GIS/visualization vocabulary routes far more
  reliably — but most users don't know which words the router is keying off.

This spec adds a small, optional, interactive step that rewrites the raw input into one or two
better-specified candidates before it ever reaches `agent.run()`, and lets the user pick, edit, or
skip it. It is a prompt-quality feature, not a new agent capability — it never calls a tool and never
touches `QgsProject`.

## 2. Non-goals

- Not a replacement for `classify_complexity()` / `pick_model_for_complexity()` (`model_selector.py`)
  — those still run, unchanged, on whatever text ultimately reaches `agent.run()`.
- Not a new provider integration — reuses whatever `agent.client` is already configured (OpenRouter,
  Gemini, OpenAI, Claude, or Ollama), same credentials, no new key management.
- Not a memory/personalization system that learns silently. The one persistent input it uses (user
  profile, §4) is an explicit setting the user picks, not inferred behind their back — consistent with
  this plugin's existing posture of never taking action the user didn't visibly authorize (see the
  `PREVIEW_REQUIRED` confirm gate in `SECURITY.md` §3 / `dock_widget.py`'s `confirm_btn`).
- Does not attempt to fully solve ToolRouter recall — `docs/API_COST_OPTIMIZATION_REVIEW.md` §1
  already has a dedicated fix for that (tie-break bug, alias list, raise `top_k`). This layer is a
  complementary, independent improvement: better input text helps recall regardless of whether the
  router itself also gets fixed.

## 3. Architecture overview

```
ChatInputEdit.text
      │
      ▼
[NEW] should_refine(text, settings) ──skip──► agent.run(text, ...)   (unchanged path, today's behavior)
      │ yes
      ▼
[NEW] PromptRefiner.refine(text, user_profile, client)
      │  one small, tools=None API call on the already-configured client
      ▼
[NEW] two-card selection UI in dock_widget.py
      │  user picks A, picks B, edits either, or clicks "Send as typed"
      ▼
agent.run(chosen_text, ...)          (existing, unmodified entry point)
```

The important property: **the exit of this layer is always plain text handed to the exact same
`agent.run(user_query, map_context=..., should_stop=..., tool_step_callback=...)` call that exists
today.** Nothing downstream (`ToolRouter`, `classify_complexity`, `build_system_prompt`,
`MAX_ITERATIONS`, the dispatcher) needs to know this layer exists. That's deliberate — it keeps the
blast radius of this feature to two new files and one new UI insertion point, not a rearchitecture.

## 4. User profile setting

**New `QgsSettings` key:** `qgis_ai_agent/user_profile`, following the existing
`qgis_ai_agent/provider`-style naming convention already used throughout `agent/agent.py` and
`ui/settings_dialog.py`.

A dropdown in Settings, default `"general"`:

| Value | Label | Steers refinement toward |
|---|---|---|
| `general` | GIS Generalist | No persona bias — refinement only clarifies ambiguity and adds visualization framing (§5). |
| `humanitarian` | Humanitarian / Crisis Response | JIAF/INFORM severity language, 3W/4W presence, P-codes, Do No Harm phrasing — mirrors `docs/HUMANITARIAN_GIS_FEATURE_REVIEW.md`'s vocabulary and the actual tool names it documents (`calculate_severity_index`, `calculate_presence_gap`, `obfuscate_sensitive_points`). |
| `urban_planning` | Local Government / Urban Planning | Zoning, population exposure, service-area language — `zonal_statistics`, `estimate_population_exposure`, `calculate_service_area`. |
| `defense_intel` | Defense / Intelligence | Offline-first framing, read-only query language — `execute_read_only_sql`, no external-fetch tools implied unless explicitly requested. |

This directly reuses the vertical breakdown already written and verified in
`docs/PRODUCT_TIERS.md` §4 — the same four groupings, same tool names, so the persona list here
isn't a new invention, it's the same accuracy-checked taxonomy applied to a different feature.

**Not in scope for v1:** inferring the profile automatically from conversation history or tool-usage
patterns. `agent/memory.py`'s `SpatialMemoryManager` could plausibly support this later (it already
persists global notes via `store_global_note`), but an explicit setting is the correct v1 choice —
it's auditable, the user can see and change it, and it avoids a second undocumented heuristic (the
project already has one keyword heuristic, `classify_complexity`, whose brittleness is a known,
documented limitation; this spec shouldn't add a second one for something as consequential as "what
persona is the AI adopting").

## 5. The refinement call

**New module: `agent/prompt_refiner.py`**, structured like `model_selector.py` — small pure
functions plus one thin call site, unit-testable without QGIS.

### 5.1 Skip heuristic (`should_refine`)

Not every message should pay the extra round trip. Reuse the existing complexity signal instead of
inventing a new one:

```python
def should_refine(query: str, enabled: bool) -> bool:
    if not enabled or not query or not query.strip():
        return False
    word_count = len(query.split())
    # Short, imperative, single-operation commands ("list layers", "zoom to X",
    # "undo that") are already unambiguous -- refining them adds latency and a
    # cheap-model-call cost for no benefit. Mirrors the word-count/operation-count
    # signals classify_complexity() already uses in model_selector.py, applied to
    # a different decision (whether to refine at all, not which model to use).
    if word_count <= 5:
        return False
    return True
```

This is the same category of "deterministic heuristic, not ML" classify_complexity() already uses
and documents honestly as imperfect — same standard applies here.

### 5.2 The call itself

- Uses `agent.client.complete(messages, tools=None)` — the exact same method every provider client
  already implements (`agent/providers/base.py`'s abstract `complete(self, messages, tools=None)`),
  called with no tools so it never enters TOOLS_SCHEMA/ToolRouter territory and can't trigger a tool
  call.
- A short, dedicated system message (NOT `build_system_prompt()` — that's ~16,591 characters per the
  cost-optimization review and includes the full task/memory/map context this call doesn't need).
  Target: under 500 characters, roughly:

  > "You rewrite a QGIS user's request into two improved versions, without changing what they're
  > asking for. Persona: {profile_label}. Respond as JSON only: {see schema below}."

- **Open engineering question, flagged not glossed over:** none of the five provider clients
  currently accept a per-call `max_tokens` override — `claude.py` line 200 and its siblings all hard-
  code the shared `DEFAULT_MAX_TOKENS = 8096` from `agent/providers/base.py`. This call's output
  (two short strings + labels) needs a few hundred tokens, not 8096. Capping it requires threading an
  optional `max_tokens` parameter through each client's `complete()` — a small, real, cross-cutting
  change across all five provider files, not a detail to hand-wave. Until that lands, the call relies
  on prompt instructions alone ("be concise, JSON only") to keep output short, which is weaker than a
  hard cap and should be treated as a known v1 gap.

### 5.3 Output contract

```json
{
  "detected_profile": "humanitarian",
  "recommendations": [
    {
      "id": "A",
      "label": "Clarified",
      "refined_prompt": "...",
      "rationale": "one short sentence on what was disambiguated"
    },
    {
      "id": "B",
      "label": "Visualization-forward",
      "refined_prompt": "...",
      "rationale": "one short sentence on what output/visualization was made explicit"
    }
  ]
}
```

- **Recommendation A ("Clarified")** — fixes genuine ambiguity (undefined place names, missing
  units, an unstated target layer) while staying as close as possible to the original wording.
- **Recommendation B ("Visualization-forward")** — same intent, but made explicit about the desired
  QGIS output: which layer gets created/styled, what map/report/dashboard comes out the other end.
  This is deliberately biased toward naming concrete tool-shaped actions (style a layer, generate a
  print layout, export a dashboard) because that vocabulary is exactly what `ToolRouter`'s
  keyword/substring matching (§1) responds well to — this candidate is explicitly designed to help
  the *next* known weak point in the pipeline, not just to sound nicer.

**Parsing must be defensive**, matching the existing pattern in `agent.py`'s `_real_execute_tool`
(`json.loads` wrapped in `try/except (TypeError, ValueError)`, degrading to an error dict rather than
raising). If the response isn't valid JSON, isn't a dict, or is missing either recommendation: treat
it as a failed refinement and fall through to sending the original text unmodified (§7) — never block
or error the user's turn because this helper call misbehaved.

## 6. Interactive selection UI

**Insertion point:** `ui/dock_widget.py`, `_send_message` — currently emits the user's message
immediately (line 887) and starts the background task (line 952). This becomes a fork: if
`should_refine()` returns True and the refinement call succeeds, show a selection step first; the
existing emit-and-run code becomes what happens *after* a choice is made (whether that choice is A,
B, an edited version, or the original).

**Precedent to follow:** this plugin already has exactly one other "show the user something and wait
for an explicit choice before proceeding" pattern — the `PREVIEW_REQUIRED` destructive-edit gate
(`confirm_btn`, enabled only when `status == "PREVIEW_READY"`, `dock_widget.py` line ~723). The new
UI should follow that same visual/interaction language (a card in the chat/tasks area, explicit
buttons, nothing auto-proceeds) rather than inventing a new interaction style — users already know
this plugin's confirm-before-acting pattern from that flow.

**Card layout (two cards, side by side or stacked depending on dock width):**

```
┌─ A. Clarified ──────────────────────────────┐  ┌─ B. Visualization-forward ───────────────┐
│ "Calculate flood exposure for admin-2       │  │ "Calculate flood exposure for admin-2    │
│  units in Aleppo governorate."               │  │  units in Aleppo governorate, then style │
│                                               │  │  the result with a graduated color ramp  │
│ Why: named the admin level and area you      │  │  by exposure and export a print layout." │
│ likely meant.                                │  │                                           │
│                                               │  │ Why: made the map output explicit so the │
│ [ Use this ]  [ Edit first ]                 │  │ right styling/export tools get picked up.│
│                                               │  │ [ Use this ]  [ Edit first ]             │
└───────────────────────────────────────────────┘  └───────────────────────────────────────────┘
                    [ Send as typed instead — skip refinement ]
```

- "Edit first" opens the refined text in the existing `ChatInputEdit` for the user to modify before
  sending — never sends a rewritten prompt the user hasn't seen.
- "Send as typed" is always present and always one click away — this must never become a mandatory
  gate. A user who types the same kind of command repeatedly should be able to disable this in
  Settings (§4's `qgis_ai_agent/prompt_refinement_enabled`, default **off** — see §9) entirely.

## 7. Failure modes and fallbacks

Every failure degrades to "send the original text, unmodified, exactly like today" — matching the
silent-fallback posture `_apply_auto_model_selection` already uses in `agent.py` (wrapped in
`try/except`, logs to console, never raises into the caller):

| Failure | Behavior |
|---|---|
| Refinement disabled in settings | Skip entirely, unchanged current behavior. |
| `should_refine()` returns False (short/simple message) | Skip entirely. |
| Refinement API call errors or times out | Log to console (`print(f"[PromptRefiner] ...")`, same style as existing modules), send original text. |
| Response isn't valid/complete JSON | Same as above. |
| User closes the card without choosing | Nothing sent — same as if they hadn't pressed Send yet. No auto-timeout auto-send. |

## 8. Cost impact

One extra small call per refined message, using the numbers already measured in
`docs/API_COST_OPTIMIZATION_REVIEW.md` §0 as a baseline for comparison:

- **Input:** a ~500-character system instruction (~125-150 tokens) + the user's raw query (typically
  10-60 tokens) + **no tool schema** (the main turn's routed schema alone averages ~4,700 tokens per
  that review) — call it 150-250 tokens total input.
- **Output:** two short rewritten prompts + two one-line rationales, realistically 150-400 tokens
  (unenforced until the `max_tokens` gap in §5.2 is closed).
- **Net:** roughly 300-650 tokens per refined message — small next to a single full agentic turn
  (system prompt ~3,300-4,100 tokens plus routed tools ~4,700 tokens before any tool results even
  come back), but not free, and it runs on *every* refined message, not just ones that would have
  gone wrong. The honest case for it is quality/recall, not cost — this feature trades a small,
  bounded cost increase for fewer wasted full turns caused by ambiguity or poor tool-router recall,
  and should be evaluated against that tradeoff, not marketed as a cost optimization.
- This is why §5.1's skip heuristic and §9's default-off setting both exist: the feature should not
  silently change every user's per-message cost profile without them choosing that.

## 9. Settings additions

| Key | Default | Notes |
|---|---|---|
| `qgis_ai_agent/prompt_refinement_enabled` | `false` | Opt-in. Given §8's honest cost tradeoff, this should not default on until real usage data shows the two-recommendation quality is worth the added latency/cost for most users. |
| `qgis_ai_agent/user_profile` | `"general"` | See §4. |
| `qgis_ai_agent/prompt_refinement_model` | unset (falls back to the same cheap-tier pick `pick_model_for_complexity` would choose for a "simple" query) | Advanced/optional override, not required for v1. |

## 10. Testing & acceptance criteria

- Unit tests for `agent/prompt_refiner.py` (no QGIS needed, same pattern as `test_model_selector.py`
  presumably already covers `model_selector.py`): `should_refine()` boundary cases (empty string,
  exactly 5 words, 6 words), JSON parsing success/failure/partial cases, profile-label mapping for
  all four `user_profile` values.
- A fixture test asserting that a malformed response (missing `recommendations`, non-JSON text, one
  recommendation instead of two) degrades to "use original text" without raising.
- Manual QA: run the two-card flow once against each of the five providers (OpenRouter, Gemini,
  OpenAI, Claude, Ollama) — Ollama in particular needs verification that a small local model still
  returns usable structured JSON, since this plugin's offline-first Community-tier story
  (`docs/PRODUCT_TIERS.md` §1) depends on this feature working there too, not just on hosted models.
- Verify the "Send as typed" bypass and the Settings toggle both fully disable this layer with zero
  behavior change versus current `main` — this is the safety net that makes the feature safe to ship
  opt-in.

## 11. Open decisions (need a call before implementation starts)

1. **Where the two-card UI physically renders** — inline in the chat scroll area (like a message) or
   a separate panel above `ChatInputEdit`. Chat-area placement matches existing message rendering
   code more closely; a separate panel avoids cluttering chat history with cards that aren't really
   conversation turns.
2. **Whether a chosen/edited recommendation is logged to `conversation_history`** as if the user had
   typed it directly (simplest, keeps `MAX_HISTORY_MESSAGES` trimming and history-based context
   untouched) or whether the original-plus-choice should both be recorded for transparency. Simplest
   default: log only the final chosen text, exactly as if the user had typed it — the refinement step
   leaves no trace downstream, consistent with §3's "exit is always plain text" design goal.
3. **Default-on vs. default-off** (§9) — this spec recommends off given the unbudgeted cost in §8,
   but that's a product call, not a purely technical one.

## 12. Relationship to other roadmap docs

- Builds on the ToolRouter recall problem documented in `docs/API_COST_OPTIMIZATION_REVIEW.md` §0-1
  — that document's fix (tie-break bug, alias list, `top_k`) and this layer's visualization-forward
  recommendation (§5.3) are independent, complementary mitigations for the same underlying issue.
- Reuses the exact profile taxonomy from `docs/PRODUCT_TIERS.md` §4 (humanitarian / defense-intel /
  urban-planning / general) rather than inventing a new one.
- Like Professional/Enterprise in `docs/PRODUCT_TIERS.md`, this is Community-tier functionality if
  built — it needs no backend, no billing, no account system, just a new module, a settings key, and
  a UI insertion point.
