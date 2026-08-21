# Cartogen AI — Engineering, Product & UX Review (2026-08-20)

Requested directly by the user: a specialist read of the codebase — product engineering, software
engineering, and UI/UX — with concrete recommendations and best practices for continuing to build
this specific product, not generic QGIS-plugin advice detached from the actual code. Grounded in a
direct read of `agent/providers/` (all 6 clients + `base.py`) and `ui/` (all 4 files) this round,
on top of the architecture/tool-registry/security/docs context already established in
`docs/STATUS_REVIEW_2026-08-20.md`. Current as of **v1.2.25** (131 tools).

## 1. Overall assessment

This is an unusually mature codebase for a QGIS plugin at this stage. Three things stand out
immediately, and they're the foundation everything below builds on:

- **The comments explain *why*, not *what*.** Nearly every non-obvious line has a comment citing a
  real, previously-hit failure mode (a live 404 on a Gemini model Google's own docs still called
  stable, a `QgsHighlight` overload that only accepts `QgsGeometry` not `QgsRectangle`, a
  `QTabWidget` sizing the whole dock to its tallest tab). That's the signature of a codebase that
  learns from production incidents instead of re-deriving the same bugs.
- **Honest status-tracking is a real, load-bearing habit, not decoration.** "Not yet built,"
  "unverified against a live response," "this is a stub" appear throughout — including inside the
  code itself (`cartogen.py`'s docstring), not just in docs. That discipline is rarer than it
  sounds and is worth explicitly protecting as the team grows.
- **The main-thread/background-thread split is correctly enforced everywhere it matters.** Every
  network call in `ui/` and `agent/providers/` that could block goes through a background
  `threading.Thread` with a Qt signal back to the main thread — settings dialog model fetching,
  prompt refinement, the agent loop itself. This is the single easiest thing for a QGIS plugin to
  get wrong (a frozen UI *is* a frozen QGIS), and it's handled consistently.

## 2. Software engineering findings

### 2.1 Real, fixable bug: `OllamaClient` skips the shared retry helper

`agent/providers/base.py` defines `post_with_retry()` specifically so a transient network hiccup or
429/5xx doesn't kill an entire agent turn — its own comment says this benefit is meant for every
provider "except OpenRouter/Gemini, which already have their own multi-model fallback loop as an
outer layer." Every other client (`openai.py`, `claude.py`, `gemini.py`, `cartogen.py`) correctly
calls `post_with_retry(...)`. **`ollama.py`'s `complete()` calls `requests.post(...)` directly**,
bypassing it entirely — the one provider client most likely to hit a transient failure in practice
(a local Ollama server that's still loading a model, or briefly saturated) is the one with no
retry. Recommend swapping the bare `requests.post` call for `post_with_retry`, matching every other
client's pattern.

### 2.2 Minor bug: misleading error message on malformed Ollama responses

`ollama.py`'s `complete()` wraps the whole request+parse in one `try/except Exception as e: return
{"error": f"Ollama connection failed: {e}"}`. A `KeyError` from an unexpected response shape (not a
connection problem at all) gets reported to the user as "Ollama connection failed: 'choices'" —
actively misleading for debugging. `openrouter.py` handles this correctly: it catches
`(KeyError, IndexError, ValueError)` separately and reports "Unexpected response format." Recommend
the same split in `ollama.py` (and, lower priority, in `gemini.py`/`openai.py`/`cartogen.py`, whose
generic messages are less actively wrong but still don't distinguish "couldn't reach the server"
from "reached it, got something we didn't expect").

### 2.3 Worth a look, not urgent: Gemini's auth is inconsistent within its own file

`gemini.py`'s main chat path (`complete()`/`_post()`) correctly authenticates via an
`Authorization: Bearer` header. Its two legacy-endpoint functions — `list_models()` and
`grounded_search()` — authenticate via a `?key=` **URL query parameter** instead. Query-string
credentials are more likely to end up in server access logs, proxy logs, or browser history than a
header ever would. Google's Generative Language API does support header-based auth
(`x-goog-api-key`) for these same endpoints, so this is fixable — but flagging rather than applying:
this sandbox has no live network access to verify the header actually works against Google's real
API, and an unverified change to a network code path this codebase can't test here is exactly the
kind of thing this project's own conventions say to flag, not silently patch.

### 2.4 What NOT to change — deliberate, already-correct design

Two things that look inconsistent at first glance but are documented, intentional decisions, worth
naming so a future pass doesn't "fix" them: `claude.py` defines its own local `DEFAULT_MAX_TOKENS`
instead of importing `base.py`'s identical constant — `base.py`'s own comment explains this was left
as-is "for no functional reason" when the shared constant was introduced, i.e., already a known,
accepted duplication. And `ollama.py`'s 180-second timeout (vs. 60s everywhere else) is intentional
— local models can be slower than a cloud API, correctly commented as such.

### 2.5 Provider-layer best practice already in place, worth protecting

The `PROVIDERS` list in `settings_dialog.py` (single source of truth for every provider's UI row)
and the consistent `{"message": ..., "model": ...}` / `{"error": ...}` return contract every
`complete()` implementation honors are exactly the right pattern for a growing multi-provider
system: adding provider #7 means one list entry plus one client file, not touching UI logic. Keep
enforcing this contract explicitly (a shared test asserting every provider module's `complete()`
returns one of exactly those two shapes would catch a future provider breaking the contract before
it reaches `agent.py`'s tool-calling loop).

## 3. UI/UX findings

### 3.1 Strengths worth keeping as house style

- **Theme-adaptive rendering, done right.** `_extract_theme_palette()` reads the live QGIS
  `QApplication` palette; `chat_formatting.derive_bubble_colors()` and `build_dock_stylesheet()`
  derive every color from it. This means dark-theme QGIS installs (increasingly common) get a UI
  that actually matches, instead of a plugin that looks visibly bolted-on. The palette-reading code
  is deliberately thin and the color-derivation logic is pulled into a pure-Python, unit-tested
  function — a genuinely good split between "QGIS-dependent glue" and "testable logic," and a
  pattern worth repeating anywhere else UI logic grows.
- **Explicit, opt-in defaults for anything privacy- or cost-sensitive.** Chat history persistence to
  the `.qgz` project file defaults OFF with a tooltip explaining exactly why (a project file is a
  shareable artifact). Prompt refinement defaults OFF with the per-call cost named in the tooltip.
  Neither silently changes behavior or cost profile — this is the right default posture for a tool
  that talks to paid external APIs and may handle sensitive humanitarian data, and it should stay
  the default posture for any new opt-in feature.
- **The preview/confirm gate for destructive actions has a real visual affordance, not just text.**
  `_flash_preview_layer()` highlights the actual layer a pending edit would touch on the map canvas
  before the user clicks Confirm — closing the gap between "the AI says it will edit X" and "I can
  see X" without needing a full before/after geometry diff.
- **XSS-equivalent discipline in the chat renderer.** `render_markdown()` escapes HTML-sensitive
  characters *before* applying any markdown transformation, and `escape_plain_text()` was added
  specifically because user-typed input used to go into the bubble HTML unescaped. This matters more
  than it might look like for a desktop app: `QTextBrowser` renders real HTML, and tool results or
  file attachment content can contain arbitrary user- or model-supplied text.

### 3.2 Recommendations

- **`dock_widget.py` at 1,365 lines is carrying too much.** It currently owns the chat tab, the
  tasks/memory tab, file-attachment reading, the refinement panel, and the settings/provider-switch
  glue, all in one class. This hasn't caused a bug yet — the file is well-organized internally — but
  it's the single largest maintenance-risk surface in the UI layer, and it's still growing (the
  refinement panel and tasks-tab scroll-area fix are both recent additions to this same file).
  Recommend splitting along the tab boundary at minimum (`ChatTabWidget`, `TasksTabWidget` as
  separate `QWidget` subclasses composed into the dock), before the next major feature addition
  makes the split more expensive to do. `_read_attached_file()` is already a free-standing function
  at module level — a natural first extraction into its own `attachments.py`.
- **Surface the new raster styling tool in the UI, not just the tool registry.** `apply_raster_stretch`
  (built this session) closes a real, previously-flagged gap, but nothing in `QUICK_SUGGESTION_CHIPS`
  or the Help tab mentions it — a user has no UI-level cue that raster styling now exists unless they
  happen to ask for it in exactly the right words. A quick-suggestion chip (mirroring the existing
  "💡 Style by attribute" one) would close the loop between "the capability exists" and "a user
  discovers it," which is otherwise entirely dependent on `ToolRouter`'s alias matching.
- **No cost/usage visibility in the UI despite real, documented cost-engineering work.**
  `docs/API_COST_OPTIMIZATION_REVIEW.md` and this session's prompt-caching comments (Anthropic cache
  breakpoints in both `claude.py` and `openrouter.py`) show real attention to token cost — but
  nothing in `dock_widget.py` surfaces token usage, estimated cost, or even which model actually
  served a given response beyond the small status line. For a tool that can silently rack up API
  spend across five paid providers, even a lightweight "~N tokens this turn" or a running session
  total would close a real gap between the cost-awareness already built into the backend and what
  the user actually sees.
- **Audit which destructive tools get the preview/confirm gate and which don't, as the tool count
  grows.** The gate exists and works well (§3.1), but with 131 tools and growing, it's worth a
  periodic check that every tool capable of a real, hard-to-reverse project change (not just the
  ones that had it from the start) is actually routed through `PREVIEW_READY`/`TASK_MANAGEMENT_TOOLS`
  rather than executing immediately — this is a policy that needs re-verifying as new tools are
  added, not a one-time fact once true, always true.

## 4. Product engineering findings

- **Scope discipline is the strongest product asset here, not a specific feature.** The willingness
  to write "not yet built," "roadmap only," "unverified" directly into shipped docs and code
  comments — rather than letting marketing framing drift ahead of what's real — is unusual and
  valuable. It's also fragile: it only holds if every future contributor keeps doing it. Worth
  making explicit as a stated engineering value (e.g., in a CONTRIBUTING doc) rather than leaving it
  as an emergent pattern that depends on continuity of the people currently doing it.
- **The licensing decision in `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` §3 is the single
  biggest open product risk right now**, and it's upstream of most of the other open engineering
  items (tier gating, closed-source packaging, the Cartogen gateway provider going live). Nothing
  in this review changes that assessment — repeating it here because a product/engineering/UX
  review that didn't surface it would be incomplete.
- **"Live-QGIS verification" keeps recurring as the top item in every review round's recommended
  next steps, because this sandbox structurally cannot do it.** That's not a gap that a better code
  review closes. Recommend turning it into a concrete, reusable artifact instead of a repeated
  to-do: a short manual smoke-test checklist (e.g. `docs/RELEASE_SMOKE_TEST.md`) — one representative
  tool call per category, run inside a real QGIS session before each release — so "verify live" stops
  being an unowned, perpetually-deferred line item and becomes a 15-minute checklist a human actually
  runs. This is the kind of gap a process artifact closes better than more code review can.

## 5. Prioritized best-practices checklist going forward

1. Keep the "why, not what" comment discipline and the honest shipped/roadmap labeling — these are
   the two habits most responsible for this codebase's above-average maintainability, and the
   easiest to lose gradually without anyone deciding to drop them.
2. Fix `ollama.py`'s retry gap and error-message specificity (§2.1/§2.2) — small, low-risk, closes a
   real reliability inconsistency.
3. Split `dock_widget.py` along its tab boundary before the next major UI feature (§3.2) — cheapest
   to do now, more expensive every feature added after this point.
4. Resolve the GPL v2 licensing question (§4, `TIER_RESTRUCTURE_PROPOSAL` §3) before more
   tier-engineering work — it blocks more downstream work than any single code issue in this review.
5. Turn "live QGIS verification" from a recurring recommendation into a standing checklist artifact
   a human can actually execute — closes a gap no amount of further sandbox code review can.
