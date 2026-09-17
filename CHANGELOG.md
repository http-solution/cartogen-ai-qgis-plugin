# Changelog

**[1.3.0] and earlier moved to `CHANGELOG_ARCHIVE.md`** in the 2026-08-31 documentation pass -- this file had grown to 2,146 lines covering every version since `[0.1.2]`, most of it from the very early, rapid `[1.2.x]` patch cycle. The split point is `[1.4.0]`, this project's own documented milestone (the dual-tree-to-single-tree consolidation --
see the `[1.4.0]` entry below and `CONTRIBUTING.md`). Entries were relocated verbatim, not rewritten, per this project's convention that past changelog entries are a historical record (`CONTRIBUTING.md` §2) -- only the file they live in changed.

**Recent releases at a glance:**

| Version | Date | Summary |
|---|---|---|
| [1.15.6](#v1-15-6) | 2026-09-18 | **Stable.** Promoted from rc6, no code changes -- security/audit remediation, crash root-causes, rate-limit resilience, the orchestrator reliability pass, and the full Broadsheet UI redesign, across 6 release candidates |
| [1.15.6-rc6](#v1-15-6-rc6) | 2026-09-18 | Release candidate: search_web's dead duckduckgo-search dependency migrated to ddgs, found via an independent audit-verification pass of every RC5 open item |
| [1.15.6-rc5](#v1-15-6-rc5) | 2026-09-17 | Release candidate: router-confidence, field-width, and confirmation-gate fixes, plus the full Broadsheet redesign (single-scroll dock, inline safety-gate card, layer context picker) |
| [1.15.6-rc4](#v1-15-6-rc4) | 2026-09-16 | Release candidate: crash root-causes confirmed with real tracebacks, a tool-discovery router gap, a UI freeze reverted, and a Settings/chat/Activity visual redesign |
| [1.15.6-rc3](#v1-15-6-rc3) | 2026-09-15 | Release candidate: 2 more fixes on rc2 -- missing first-message echo, tool-argument shape validation |
| [1.15.6-rc2](#v1-15-6-rc2) | 2026-09-15 | Release candidate: 4 fixes on rc1 -- requests dependency, GDACS country filter, dock screen-clamp timing, prompt-preview-to-in-chat conversion |
| [1.15.6-rc1](#v1-15-6-rc1) | 2026-09-14 | Release candidate: fixes 27 of 32 findings from a full security/QGIS/API/performance/code-quality audit |
| [1.15.5](#v1-15-5) | 2026-09-13 | Patch: fixed another instance of the "'str' object has no attribute 'get'" crash, this one in Gemini usage parsing |
| [1.15.4](#v1-15-4) | 2026-09-13 | Patch: root-caused and fixed the "'str' object has no attribute 'get'" crash |
| [1.15.3](#v1-15-3) | 2026-09-13 | Patch: the user's own reply to a clarifying question wasn't showing up in the chat log |
| [1.15.2](#v1-15-2) | 2026-09-13 | Patch: requirement-gate questions now ask in chat instead of a separate boxed panel |
| [1.15.1](#v1-15-1) | 2026-09-13 | Patch: live-hazard-data requests could get refused despite real matching tools existing |
| [1.15.0](#v1-15-0) | 2026-09-13 | Gemini prompt caching (automatic, implicit) + cache-hit visibility for Gemini and Claude |
| [1.14.1](#v1-14-1) | 2026-09-13 | Patch: floating dock clamped to the screen after a report of the chat input row going missing |
| [1.14.0](#v1-14-0) | 2026-09-13 | Modularized the 47-rule base prompt by relevance; "hi" now ~3.2K tokens, down from ~23K originally |
| [1.13.1](#v1-13-1) | 2026-09-12 | Patch: a plain "hi" cost ~23K tokens from tool-router padding; word-boundary matching + stopwords fix it |
| [1.13.0](#v1-13-0) | 2026-09-12 | Rate-limit/task-size resilience: 429-aware backoff on all providers, adaptive pacing, mid-turn compaction |
| [1.12.0](#v1-12-0) | 2026-09-12 | Onboarding profile, Help auto-show, tidier tool-call summary; fixes a v1.11.0 accent-stripe regression |
| [1.11.0](#v1-11-0) | 2026-09-12 | Real-session UI fixes: bubble double-border, Activity tab rename, Help moved to menu |
| [1.10.0](#v1-10-0) | 2026-09-12 | UI & Chat Redesign: brand-accent blending, theme-reactive SVG icons |
| [1.9.0](#v1-9-0) | 2026-09-12 | Live Hazard Monitoring: NASA FIRMS/EONET + GDACS tools, dashboard freshness badges |
| [1.8.3](#v1-8-3) | 2026-09-12 | Patch: release zip was silently missing 4 relocated archive docs |
| [1.8.2](#v1-8-2) | 2026-09-12 | Docs-only: repo reorganization and documentation polish pass |
| [1.8.1](#v1-8-1) | 2026-09-12 | Patch: dashboard OSM-blocked basemap + canvas not following new layers |
| [1.8.0](#v1-8-0) | 2026-09-12 | Cartographic Intelligence: visualization selection, real QA gate, isochrone bands |
| [1.7.1](#v1-7-1) | 2026-09-11 | Patch: portrait print-layout body/footer overlap fixed |
| [1.7.0](#v1-7-0) | 2026-09-11 | Security & Logistics: GDPR export, undo/rollback, sandbox Tier 2, network-aware routing |

The detailed narrative entries below are unchanged -- this table is purely an additive index on
top of them.

<a id="v1-15-6"></a>
## [1.15.6] — 2026-09-18 — Stable, promoted from rc6

**No code changes from `v1.15.6-rc6`** — this release exists to mark that candidate as the
version actually shipped as "Latest," not to introduce anything new. Six release candidates ran
against this version line over 5 days, each checksum-verified against a real QGIS session before
the next one started:

- **rc1** (2026-09-14): remediated 27 of 32 findings from a full security/QGIS/API/performance/
  code-quality audit.
- **rc2** (2026-09-15): 4 fixes — a missing `requests` dependency declaration, a GDACS country
  filter, dock screen-clamp timing, and the prompt-preview panel's first conversion to in-chat.
- **rc3** (2026-09-15): a missing first-message echo fixed, and tool-call argument shape
  validation added (guards against a double-JSON-encoded arguments string).
- **rc4** (2026-09-16): the recurring `'str' object has no attribute 'get'` crash — reported
  identically at wildly different tool-call counts across 5+ separate incidents — finally
  root-caused for real (`_execute_tool`'s snapshot step was receiving raw, unparsed JSON tool-call
  arguments) after two earlier defensive-guard fixes landed without being the actual cause; a
  custom Qt layout that froze the whole application on first real interactive use, reverted
  outright rather than debugged blind; and a Settings/chat/Activity visual pass.
- **rc5** (2026-09-17): three real orchestrator bugs found from close reading of an actual live
  session transcript — a task-router confidence floor that was computed but never checked
  (routing low-confidence requests to a completely unrelated deliverable, the dominant cause of
  reports that answers weren't "relative to the request"); external API values silently dropped
  by a memory layer's shapefile-era field width; and a destructive-action confirmation gate that
  could be silently bypassed by a plain "Confirm" reply in chat, fixed at 3 compounding layers.
  Plus the full 4-phase Broadsheet UI redesign: a single continuous scroll replacing the Chat/
  Activity tab split, an inline destructive-action confirmation card with clickable Apply-edit/
  Cancel links, the Task Inspector and Project Notes/Memory moved into on-demand dialogs, and a
  new layer-context picker for explicit, opt-out control over what schema reaches the model.
- **rc6** (2026-09-18): `search_web`'s `duckduckgo-search` dependency confirmed genuinely broken
  (silently returns zero results for a real query) and migrated to `ddgs` — found by
  independently verifying every item left open by two rounds of external audit of rc5, rather
  than accepting "reported PASS, not independently rerun" as a final answer. Both audit rounds'
  own headline findings (a release-checksum non-issue caused by this build script's zip entries
  embedding real file mtimes; a licensing-contradiction claim traced to a never-merged draft
  proposal misread as current policy) were resolved without any code change.

**Known, honestly-tracked open items at this promotion, not resolved by it** — see
`docs/IMPLEMENTATION_TRACKER.md` for the current, living list: PostGIS live read-only-SQL
enforcement has never been verified against a real database in this development environment
(Docker's backend won't start there without a one-time interactive first run); a live Gemini
network observation from that same environment is blocked on an interactive credential-store
unlock a headless process never triggers; imagery feature extraction (`ultralytics`/`torch`) is
confirmed installable and importable but not end-to-end tested against a real QGIS raster layer;
and the Community/Professional/Enterprise licensing path (`docs/PRODUCT_TIERS.md`) remains an
open business/legal decision that does not affect this edition's shipped functionality — the
Community edition has never been provider-restricted and ships all 6 provider integrations today.

Full suite: 1754 tests, 0 failures.

<a id="v1-15-6-rc6"></a>
## [1.15.6-rc6] — 2026-09-18 — Release candidate: search_web's dead dependency migrated to ddgs

A real fix found by closing out RC5's remaining open items for real rather than leaving them as
"reported PASS, not independently rerun" — two rounds of external audit on RC5 (see below) had
already confirmed the mechanical release state, but 4 items were still genuinely unverified:
PostGIS live enforcement, a real Gemini network observation, QGIS-version-range coverage beyond
4.2.2, and optional-dependency positive-path coverage. Attempted every one for real.

**`search_web`'s dependency was genuinely broken, and is now fixed.** `duckduckgo_search`, even
at 8.1.1 (the version `requirements.txt` pinned as its documented "thin compat shim" floor),
silently returns zero results for a real live query — no exception raised, nothing for
`search_web`'s own `except ImportError` to catch, so the tool just reported "no results found"
for a completely valid query as though that were a normal, unremarkable answer. The identical
query against `ddgs` (the actual current package this dependency was renamed to upstream)
returned real results immediately, confirmed live, not from reading the deprecation notice alone.
`search_web` now imports `ddgs` first, falling back to `duckduckgo_search` only if `ddgs`
genuinely isn't installed — both expose the same `DDGS` class/`.text()` call shape, so nothing
below the import needed to change. `requirements.txt` and the startup dependency-check banner
(`agent/deps.py`) now track `ddgs` (floored at 9.16.0, the version this fix was tested against)
instead of the dead pin. 3 new tests confirm the preference order and the fallback path.

**The other 3 items got honest, closing answers — not silently declared done:**
- **QGIS version-range coverage**: this machine has exactly ONE real, complete QGIS install
  (4.2.2). The other 3 version directories present (`3.44.12`, `3.44.13`, `4.2.0`) are all bare
  OSGeo4W installer shells with no usable Python environment at all — resolved as "not further
  testable in this environment," a real finding, not a gap left open indefinitely.
- **Optional-dependency positive paths**: `python-docx` and `pdfplumber` both confirmed working
  against real generated test files (a real `.docx` with a table, a real PDF with a table)
  through the plugin's own `read_attached_file`/`extract_pdf_tables` code, in an isolated
  throwaway environment. `ultralytics`/`torch` installed and imported successfully the same way,
  confirming the packages work on this machine — completing that specific tool's own end-to-end
  test needs `qgis.core` plus a real raster layer, meaning installing a real ML runtime into the
  live QGIS Python environment rather than a disposable one; deliberately not done without
  explicit sign-off, given that weight and persistence.
- **PostGIS live verification and a live Gemini network observation remain genuinely blocked** —
  Docker Desktop's backend won't start without a one-time interactive first run only a human can
  complete; the real QGIS profile has a Gemini provider configured, but its encrypted credential
  needs the interactive GUI's master-password unlock, which a headless boot never triggers.

**Two rounds of external audit on RC5**, both instructive: the first flagged the release checksum
as unreconciled, which traced to `plugin_upload.py`'s zip embedding real on-disk file mtimes
(never normalized) — a checksum mismatch across independent rebuilds is not, by itself, evidence
of a content problem with this build script, documented plainly so it stops causing false alarms.
The actual published GitHub asset was re-downloaded and re-hashed fresh, twice, confirming the
real release was never in question. The second flagged a "product identity/licensing
contradiction" between the shipped 5/6-provider Community edition and a supposed "Community
contract" limiting it to 3 — traced to `docs/archive/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`, an
explicitly-marked, never-merged DRAFT being misread as current policy; `README.md`, `CLAUDE.md`,
and `docs/PRODUCT_TIERS.md` are actually mutually consistent, and the audit withdrew the finding
once shown the exact quotes. Two small real documentation fixes came out of that exchange anyway:
a stale "165-tool" count in `docs/PRODUCT_TIERS.md` (live count is 169), and a leftover "Internal/
commercial use" phrase in `README.md`'s Support section, inconsistent with the rest of the page's
Community/GPL framing.

Full suite: 1754 tests, 0 failures (up from rc5's 1751).

Still a release candidate, not final.

<a id="v1-15-6-rc5"></a>
## [1.15.6-rc5] — 2026-09-17 — Release candidate: router/field-width/confirmation-gate fixes, and the Broadsheet redesign

An extended live-testing session on top of `v1.15.6-rc4` surfaced 3 more real, code-grounded bugs
in the orchestrator pipeline, all reproduced and fixed against the real agent — not from a chat
transcript's own summary text, but from the raw QGIS Python Console's `[Agent] Tool call:`/
`succeeded`/`FAILED` lines, since two of the three bugs were exactly the case where the model's
own prose confidently described something that never actually happened. Source commits `ce91b6a`,
`96fd84b`, `ed6c42b`.

**1. The task router's own confidence floor was computed but never checked.**
`task_matcher.classify()` already flags a match `ambiguous` when it scores below
`CONFIDENT_SCORE=0.34`, but `prompt_refiner.analyze_request()` built a full "Recognised task X,
deliver Y, prefer tools Z" system-prompt directive from the low-confidence match anyway. Live
evidence: "apply a color ramp to the raster layer" (score 0.33) got routed to an unrelated HDX/3W
CSV-export task; the model then reported a fabricated GPKG/CSV export instead of touching the
raster at all. Fixed by falling through to the same "nothing matched" path a genuinely unmatched
query already gets, but ONLY for the "below confidence floor" reason — a *tied*-but-above-floor
match (e.g. a 0.38-scoring "dashboard" query merely tied against a much weaker cross-section
match) is left alone, since nulling that out would throw away good matches too, not just bad
ones. This was the dominant root cause behind reports of answers "not relative to the request."

**2. External API values wider than a memory layer's field width were silently dropped.**
GDACS's own `country` property is a comma-joined list for multi-country events (observed at 261
chars); the memory layer's shapefile-era `field=country:string(255)` silently rejects anything
over 255 chars via QGIS's own memory-provider width enforcement — no exception, just a missing
attribute and a Qt log line the tool's own return value never reflected. Fixed with a small
`_clip_to_field_width` helper (one copy per file, matching this codebase's existing per-file-
helper convention) applied at all 3 affected write sites (GDACS/EONET/fires, and the two
humanitarian incident-point writers).

**3. A destructive-action confirmation gate could be bypassed by normal chat use, not misuse —
the most serious finding.** Traced a specific live sequence: a `field_calculator` `PREVIEW_
REQUIRED` gate fired mid-plan, the user replied "Confirm" in the chat box rather than the
Activity tab's own "Confirm and Apply Edit" button, and the actual tool log for that turn showed
`field_calculator` was never called — the model fabricated a full "Confirmation Acknowledged...
Evaluated Numeric Severity: 2" narrative while the field was never written. Three compounding
structural gaps, fixed together: `_real_execute_tool` used to only start a fresh safety-gate plan
when the task list was completely empty, otherwise gluing the pending confirmation onto
`tasks[0]` of whatever plan happened to already be active — silently overwriting an unrelated,
possibly already-`DONE` task; a new `add_task()` on the task manager always appends a dedicated
task instead. The chat send path gained the same deterministic resolution the Activity tab's
button already used (`agent._real_execute_tool(pending_tool, pending_args, user_confirmed=True)`
directly, no LLM turn) for a plain-text confirm/cancel reply — narrow enough that only an exact
yes/no-shaped reply is intercepted, so an unrelated new message can never hijack a stale gate.
`get_formatted_task_context()` now also surfaces the pending tool/arguments as defense-in-depth.

**Broadsheet redesign** — a full visual and structural redesign of the dock, from a user-supplied
15-state mockup board reviewed live and confirmed direction-by-direction:
- **Single continuous scroll, no more Chat/Activity tabs.** A sticky plan strip (progress bar,
  now stating e.g. *"3/4 steps complete — 1 needs you"* directly instead of a bare fraction, plus
  the task list) sits above the chat thread in one view — directly fixes a live audit finding
  that the one task genuinely needing a decision could scroll out of view inside the old tab's
  capped list. The Task Inspector moved to a per-task dialog opened by clicking a plan-strip row;
  Project Notes/Memory and Learned Preferences moved to a new dialog opened from a header button.
- **Inline destructive-action confirmation card.** Replaces the plain-text gate message with a
  real card (layer/field summary, rationale, code snippet, clickable Apply-edit/Cancel links) —
  wired to the exact same safe confirmation path fix 3 above built, not new logic.
- **Layer context picker.** A new composer control gives explicit, per-question, opt-out control
  over which loaded layers' schema reaches the model — a layer already tagged via the existing
  `set_layer_sensitivity` tool defaults unchecked; a user who never opens it sees unchanged
  behavior.
- Theme-aware magenta/"danger" color tokens (nudging the live QGIS palette, never a flat
  hardcoded color, so it still adapts across light/dark themes) reserved specifically for the one
  thing that mutates data — found and fixed a real bug along the way: the Confirm button had no
  `:disabled` QSS rule at all, so it looked identically clickable whether it actually was or not.

New `docs/LIVE_TEST_SCENARIOS.md` adds 5 multi-turn workflow scenarios (not single-prompt checks
like `docs/RELEASE_SMOKE_TEST.md`) — 3 reproduce this cycle's own fixed bugs, 2 are grounded
directly in the plugin's stated core purpose (map-visualization accuracy and technical-analysis
accuracy), every one verified against actual canvas/attribute-table state, never chat prose.
`docs/USER_GUIDE.md` and the in-app Help window updated to match the redesign throughout.

Full suite: 1751 tests, 0 failures (up from rc4's 1695 — new coverage for every fix and every
redesign phase, live-verified with real headless screenshots and real `QTest` clicks/keystrokes
against the actual Qt widgets, not just unit-level assertions). 34/34 live-QGIS tests passing.

Still a release candidate, not final.

<a id="v1-15-6-rc4"></a>
## [1.15.6-rc4] — 2026-09-16 — Release candidate: confirmed crash root-causes, a router gap, a UI freeze reverted, and a visual redesign

A large batch of live-reported fixes on top of `v1.15.6-rc3`, every one reproduced and verified
against the packaged plugin across an extended live-testing session, not just the dev tree.

**Crashes, root-caused with real tracebacks:**

1. **`'str' object has no attribute 'get'` — the actual root cause, finally confirmed.** This
   exact error text was reported repeatedly across the cycle, at wildly different tool-call
   counts (18, then 3, then 1, then 15) with no traceback to pin it down — two earlier defensive
   guards landed without full confirmation (see below). A live report finally came with a real
   traceback: `_execute_tool`'s pre-dispatch "snapshot" step (`_snapshot_registry.py`, used by
   MODIFY/DELETE tools like `apply_categorized_style` to capture undo state) received the
   model's tool-call arguments as the raw, still-JSON-encoded string straight off the tool call —
   never parsed into a dict, unlike the two real dispatch paths a few lines later, which each
   parse it internally. Any tool registered with a snapshot function crashed this way every time
   it was actually called, independent of anything else that ran first — exactly why the
   tool-call count varied while the crash didn't. Fixed by parsing once, before the snapshot
   call; covered by a new test that reproduces the real traceback shape (a raw JSON string in,
   not an already-parsed dict).
2. **`_compact_old_tool_results` guarded against a non-dict message entry.** A separate,
   legitimate defensive fix found while investigating (1) above, before the real root cause was
   confirmed — `m.get("role")` assumed every entry in the turn's message list was a dict;
   reproduced in isolation (`['x'][0].get('role')` raises the identical text) and guarded either
   way, though the exact mechanism that could produce a non-dict entry was never conclusively
   identified.
3. **Oversized tool results are now compacted immediately, not after 8 more tool calls.** A
   Gemini 400 "input token count exceeds the maximum" error after only 5 tool calls —
   `inspect_canvas_visually` embeds a full base64 canvas screenshot in its tool result, easily
   hundreds of thousands of tokens on its own, but the existing mid-turn compaction only trimmed
   a result once 8 *other* tool calls had also happened, a rule that assumes no single result is
   enormous enough to blow the budget alone. A single oversized result now gets trimmed as soon
   as it's no longer the latest one, immediately after the model has seen it once.

**Tool discovery:** `geocode_and_enrich`/`geocode_batch` share no vocabulary with
"health facilities beyond one hour's travel"-style requests, so they lost the competition for a
slot in the ~40 tools shown to the model out of ~170 registered — the model, unable to see they
existed, spent an entire turn's tool budget hunting the filesystem via `execute_pyqgis_script`
for a local data file instead. Fixed with curated router aliases (the same mechanism already
tuned for 8 other tools with this exact gap); confirmed end-to-end against the real `agent.run()`
loop, not just the router in isolation, and covered by a new live regression suite
(`tests/test_agent_live.py`) that scripts a full realistic turn — geocode, create a plan, add a
real QGIS layer, style it, mark every task `DONE` — and confirms a real layer lands on the canvas
and the Activity tab's actual data source gets populated, closing the loop on a live report that
a "successful" turn produced neither.

**A real UI freeze, reverted rather than chased.** A custom Qt `FlowLayout`, added this cycle for
the Settings dialog's provider pills (then reused in the Activity tab), triggered a live-reported
total application freeze on its first real interactive use — a known Qt failure mode (a resize
feedback loop inside a `QScrollArea`) that headless/offscreen screenshot verification cannot
catch, since it never drives real interactive resize/paint behavior. Reverted outright to plain,
long-established Qt layouts (a vertical stack for the pills, a fixed grid for the Activity tab's
buttons) rather than risk the same failure mode chasing a fix blind.

**Visual redesign**, following a design proposal drawn up this cycle and iterated against real
screenshots and real live feedback: numbered sections and a masthead status line in Settings; a
"Keys" summary showing a masked value and Set/Verified state per credential, directly targeting
an earlier live report where a saved key gave no confirmation it had actually taken; a redesigned
welcome message (a real capability index and clickable starter prompts, not plain markdown) and a
matching restyle of the prompt-preview card; the "Suggested rewordings" boxed panel converted to
in-chat cards, the same conversion the requirement gate and prompt preview already went through
earlier; an Activity-tab fix for buttons overflowing off the dock's edge; and a real correctness
fix for the Activity tab's memory panel, which was showing raw, unrendered `##`/`**` markdown
instead of formatted text.

Full suite: 1695 tests, 0 failures, including a new live-QGIS regression module
(`tests/test_agent_live.py`) that exercises real tool execution against a real QGIS project and
a real task-tracking pipeline, not mocks — closing a real gap every other agent test left open
(mocking tool dispatch directly proves the tool-calling loop is correct, but never proves a tool
call actually creates a real layer or populates the Activity tab's data).

Still a release candidate, not final.

<a id="v1-15-6-rc3"></a>
## [1.15.6-rc3] — 2026-09-15 — Release candidate: 2 more fixes on rc2

Two more real, live-reported fixes on top of `v1.15.6-rc2`, both verified against the packaged
plugin. Source commit `156fea4`.

1. **The triggering message for an in-chat gate is now echoed as its own bubble.** Real live
   report: "the first message i sent on the chat was not showing in the chat box." When a
   fresh message triggered either in-chat gate (`_ask_requirement_in_chat` or
   `_ask_preview_in_chat`), the user's own typed text was never shown as its own "You" bubble
   -- it only appeared secondhand, quoted inside the AI's own message. Both gates now echo the
   triggering message immediately, before the AI's question; the preview-confirm path gained an
   `already_echoed` flag so the same text isn't shown a second time once dispatch happens.
2. **Tool-call arguments are now validated to actually be an object.** `json.loads` succeeds on
   any well-formed JSON document, not just objects -- a double-JSON-encoded arguments string (a
   known real-world LLM tool-calling quirk: the model's own arguments field is itself a
   JSON-encoded string) decodes to a plain string, not the intended dict, and previously crashed
   uncaught on the next line. Investigated as a candidate cause for a live-reported
   `'str' object has no attribute 'get'` crash immediately after a real 18-tool-call Gemini turn
   where every individual tool call succeeded -- not confirmed as the exact site (no traceback
   was available to pin it down precisely), but a real, demonstrable gap in the same bug class
   as two earlier-fixed usage-parsing crashes (`extract_openai_style_usage`).

Full suite: 1689 tests, 0 failures. Live-verified against the rebuilt package (`dist/`
`cartogen_ai_v1.15.6.zip`, 173 entries, sha256 `1d1cd5b5...6530f810`): the full 16-category
interactive checklist (15/15 runnable categories, PostGIS skipped -- no test DB; one transient
network timeout on the OSM category, clean on retry) plus 2 targeted checks proving both fixes
work against the packaged code, not just the dev tree -- see `docs/RELEASE_SMOKE_TEST.md`'s
2026-09-15 RC3 run log entry for the full detail.

Still a release candidate, not final: licensing/publication decision, package provenance
confirmation, and stable-promotion gates remain open — see
`docs/audits/QGIS_PLUGIN_AUDIT_FINAL_REPORT.md` §16 for the full gate table.

<a id="v1-15-6-rc2"></a>
## [1.15.6-rc2] — 2026-09-15 — Release candidate: 4 fixes on rc1

Four real, live-reported fixes on top of `v1.15.6-rc1`, all verified against the packaged plugin
(not just the dev tree). Source commit `62fcb69`.

1. **`requests` declared as a required dependency.** Every provider client
   (`agent/providers/*.py`) and `account.py` import it directly for all LLM API calls, but it was
   never listed in `requirements.txt` -- worked in practice only because QGIS's own bundled
   Python typically ships it already, an unstated host-environment assumption rather than a real
   dependency declaration.
2. **GDACS `country` filter.** A place-scoped request with no explicit bbox (e.g. "the latest
   GDACS alerts for Yemen") previously fell through to `fetch_gdacs_disaster_alerts`'s
   global-coverage default, returning every disaster alert on Earth. Added a `country` parameter
   that filters against GDACS's own per-alert country field (already extracted, never filtered
   on before). Live-verified: every returned alert's country field genuinely contains "Yemen",
   and the filtered count never exceeds the unfiltered count.
3. **Floating dock proactively re-clamped on panel toggle.** Showing the prompt-preview/
   refinement panels grows the dock's forced minimum size enough to push it past the available
   screen height -- exactly the failure mode `_clamp_to_screen_if_floating` (added in `v1.14.1`)
   exists to catch, but that guard only ran from `resizeEvent`, leaving a timing gap that could
   leave the chat input row under the Windows taskbar. Now called proactively the moment either
   panel's visibility changes.
4. **Prompt-preview panel converted to an in-chat exchange.** The "Prompt that will be sent"
   boxed panel (Send this / Send as typed instead / Cancel) is replaced by `_ask_preview_in_chat`
   -- the reasoning and composed prompt post as a normal chat message, and a typed reply resolves
   the same 3-way choice (confirm / edit / cancel) via free text. Same conversion already applied
   to the requirement-gate panel in `v1.15.2`; this was the last boxed panel in the chat flow.

Also fixed in passing: a stale doc reference in `help_tab_widget.py` (an "Edit request" button
that had already been removed in the `v1.15.2` conversion) and a dangling reference in
`.github/workflows/sync-to-private.yml` found while preparing an unrelated Community-publication
artifact.

Full suite: 1684 tests, 0 failures. Live-verified against the rebuilt package (`dist/`
`cartogen_ai_v1.15.6.zip`, 173 entries, sha256 `5aee5c99...377a950`): the full 16-category
interactive checklist (15/15 runnable categories, PostGIS skipped -- no test DB) plus 4 targeted
checks (plugin load/unload via the real `classFactory()` entry point, the live GDACS network
call described above, the screen-clamp firing on a real panel-visibility change, and the old
boxed preview panel confirmed absent with the new in-chat mechanism confirmed present) -- see
`docs/RELEASE_SMOKE_TEST.md`'s 2026-09-15 run log entry for the full detail.

Still a release candidate, not final: licensing/publication decision, package provenance
confirmation, and stable-promotion gates remain open — see
`docs/audits/QGIS_PLUGIN_AUDIT_FINAL_REPORT.md` §16 for the full gate table.

<a id="v1-15-6-rc1"></a>
## [1.15.6-rc1] — 2026-09-14 — Release candidate: audit remediation (27 of 32 findings)

Full multi-domain audit (Security, QGIS/PyQGIS Integrity, API/Network Client, Performance, Code
Quality) against `cartogen-ai-audit-charter.md`, executed over 2 days against this repo's actual
current state. Complete findings register, remediation log, and a synthesized final report live
in `docs/audits/` (`QGIS_PLUGIN_FINDINGS.md`, `QGIS_PLUGIN_AUDIT_FINAL_REPORT.md`) -- this entry
is a summary; those files are the source of truth for every individual finding's evidence, test
reference, and reasoning.

**32 real findings, 27 fixed/mitigated/partial, 2 accepted risk, 3 deliberately untouched**
(all three explicitly no-action-recommended by the audit itself -- large-scope, low-value
rewrites with no demonstrated bug). Test suite grew 1531 → 1680, 0 failures throughout,
re-verified independently on GitHub Actions CI after every push.

**Security**: SSRF-hardened 4 second-hop URL fetches that bypassed this plugin's own guard
(`humanitarian_tools.py`); sanitized CSV/spreadsheet formula injection in `export_to_csv`;
corrected a license-metadata mismatch and documented an optional dependency's stricter license;
cleaned up cached fetch results' leftover temp files.

**API/network**: redacted provider error bodies that can echo back partial API keys; added
retry/backoff to `list_models()` and the 3 recurring-schedule hazard fetch tools (12 one-shot
fetch tools intentionally left for a follow-up); fixed a real crash on a malformed JSON response
in 2 providers; gave connection/timeout errors an actionable message instead of raw exception
text; added an inline disclosure at the moment of file attachment naming which AI provider the
content is sent to.

**QGIS/PyQGIS**: guarded task-completion callbacks and now cancel in-flight tasks on plugin
unload; the Stop button now takes effect mid-batch, not just between rounds; fixed a latent
export-writer bug and 5 more unresolved-enum gaps of the same class; propagated and extended
CRS-unit-mismatch warnings across 3 logistics tools (numeric correction itself remains an open
design decision -- these tools warn honestly rather than guess a reprojection); extended the
destructive-action confirmation gate to 4 more attribute-mutating tools; a styling failure can
no longer leave a shared layer permanently unstyled.

**Performance**: excluded the 3 network-fetch hazard tools from scheduled/recurring workflows,
closing a real QGIS-GUI-freeze risk (the underlying off-main-thread dispatch rework remains
open); stopped rebuilding a spatial index once per time bucket instead of once; cached
building-footprint tile downloads; moved attachment parsing off the Qt main thread; capped the
candidate×demand pair count in facility-siting tools against unbounded input size.

**Code quality**: pinned an unofficial-API dependency to a known-working range; synced drifted
version metadata across `pyproject.toml`/`README.md`; added real behavioral tests for all 24
previously-untested tools (9 raster/classification, 15 vector/layer-management) -- 0 of 169
tools now have zero test coverage, down from 24.

**CI**: added a `gitleaks` secret-scanning job (GitHub's native secret scanning isn't available
on this private repo without a paid GHAS license -- confirmed directly via the API) and enabled
Dependabot vulnerability alerts and automated security fixes.

Tagged `commercial-plugin-v1.15.6-rc1` rather than promoted straight to a final release: several
release-readiness gates remain open independent of the code itself -- an interactive QGIS smoke
test, a licensing/publication decision, and package identity/provenance confirmation. See
`docs/audits/QGIS_PLUGIN_AUDIT_FINAL_REPORT.md` §16 for the full gate table.

<a id="v1-15-5"></a>
## [1.15.5] — 2026-09-13 — Patch: fixed a second instance of the "'str' object has no attribute 'get'" crash

Three more live reports came in right after v1.15.4 shipped -- same exact crash text, but with
completely different tool sequences each time (4 tools, then 9 tools, none overlapping with
the hazard/HDX tools v1.15.4 fixed), all on a session configured with **Google Gemini**.

Three separate reproduction attempts (a scripted client, a real-QGIS run with real layers, and
a run through the actual cross-thread dispatcher mechanism a live session uses) all came back
clean against the reported tool sequences -- ruling out every individual tool involved and the
dispatch machinery around them a second time. The common factor across all three reports
wasn't any specific tool; it was the provider.

**Root cause**: `providers/base.py`'s `extract_openai_style_usage` (added in v1.15.0's Gemini-
caching-visibility work, and not covered by v1.15.4's audit since that code didn't exist yet
when this bug class was first found) extracted the cache-hit count with:

```python
cached_tokens = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
```

This only degrades safely when the field is missing or falsy. If a provider's OpenAI-compatible
response ever returns `prompt_tokens_details` as a **truthy non-dict** (a bare string being the
most likely real shape for a compatibility-shim quirk), `x or {}` returns `x` itself -- `or`
short-circuits on the first truthy operand -- and the following `.get()` raises uncaught,
producing exactly the reported error text. Confirmed with a one-line repro:
`("some string" or {}).get("cached_tokens")` raises `AttributeError: 'str' object has no
attribute 'get'`.

**Fixed** with an explicit `isinstance(details, dict)` check instead of relying on truthiness.
This is the shared usage-extraction point for all 4 OpenAI-style providers (Gemini, OpenAI,
OpenRouter, and the hosted-gateway prototype), so the fix protects all of them, not just Gemini.
New regression test confirms the exact malformed-response shape now degrades to "no cache-hit
info available" instead of crashing the whole turn. Full suite 1530 -> 1531, 0 failures.

<a id="v1-15-4"></a>
## [1.15.4] — 2026-09-13 — Patch: root-caused the "'str' object has no attribute 'get'" crash

Following up on `BUG-2026-09-13-2` (see `docs/BUG_TRACKER.md`): a full audit of the tool-
dispatch and `.get()` call surface, prompted directly by the live crash report, found the
real gap.

**Root cause**: `agent.py`'s `_execute_two_phase_tool` (the dispatch path used by
`fetch_worldpop_population` and the 3 hazard-monitoring fetch tools, among others) has no
exception handling of its own -- unlike the regular tool dispatch path, which wraps its
function call in a broad `try/except`. Within that unguarded surface, 3 real network-fetch
functions called `.get()` on a freshly `json.loads()`'d API response OUTSIDE their own
`try/except`'s coverage: `fetch_nasa_eonet_events_network_phase` and
`fetch_gdacs_disaster_alerts_network_phase` (`hazard_monitoring_tools.py`),
`fetch_hdx_admin_boundaries_network_phase` (`humanitarian_tools.py`). If any of these APIs
ever returned valid JSON that wasn't a dict (a bare string/list/null error body -- GDACS's
own docs already warn its data "may require further validation"), that `.get()` call raised
an uncaught `AttributeError` that escaped the entire tool-calling loop, surfacing as a bare
Python exception in the chat instead of a normal error message.

**Fixed in two parts**:
- A general safety net in `agent.py`'s `_execute_tool`: any exception from any tool dispatch
  path now becomes a normal `{"error": ...}` result. This closes the whole class of bug for
  every tool -- present or future -- not just the 3 found.
- Proper `isinstance(data, dict)` guards at the 3 specific sites (plus
  `fetch_building_footprints_network_phase`'s per-line JSON parsing, same pattern, lower
  risk), giving a clear, attributable error message instead of relying on the safety net
  alone.

Also fixed a matching but structurally different gap in `chat_tab_widget.py`'s
`_analyze_image` (already caught by its own surrounding `try/except`, so not this specific
bug, but the same risk class, worth closing while auditing this).

5 new tests covering the exact malformed-response scenarios and the general safety net; full
suite 1525 -> 1530, 0 failures.

<a id="v1-15-3"></a>
## [1.15.3] — 2026-09-13 — Patch: the user's own replies weren't showing up in chat

Direct follow-up report after v1.15.2 shipped: "some of my text i sent in the chat is not
showing." Root cause: when a requirement-gate question (see v1.15.2) was answered, the reply
got folded into the pending request behind the scenes -- it was never emitted as its own chat
message. For a request needing only one missing detail this was subtle (the eventual composed
request still appeared once dispatch/preview happened, so something visible did show up
eventually). For a request needing two unresolvable details in a row (e.g. `facility_type` AND
`sector`, both with no safe default to guess), asking a second time silently replaced the first
question with no trace the first answer was ever received -- exactly matching the report.

**Fixed**: `chat_tab_widget.py`'s `send_message()` now echoes the literal reply into the chat
log immediately, in the same `_awaiting_requirement_reply` branch, before merging it into the
pending request text. Live-verified in real QGIS: a genuine 2-round clarification (facility
type, then sector) now shows both replies as their own messages, in order, exactly as typed.
New `test_multi_round_clarification_shows_every_reply_in_chat` plus a new assertion on the
existing single-round test; full live-widget suite 8/8, full suite 1525 tests, 0 failures.

<a id="v1-15-2"></a>
## [1.15.2] — 2026-09-13 — Patch: requirement-gate questions now ask in chat, not a boxed panel

Direct user feedback, with a real screenshot: "i dont like the style of the feedback from
cartogen AI make it more in the chat and get user response interactive chat." The complaint was
about the task-register requirement gate -- asked when a request is missing a slot with no safe
default to guess (e.g. hazard type: guessing wrong produces confidently wrong humanitarian
output) -- which showed as a separate `QGroupBox("One more detail needed")` panel above the
input row, with two buttons and the input box locked read-only. Visually, it read as a foreign
popup rather than part of the conversation above it.

**Fixed** by posting the question as a normal Cartogen chat message instead. The input box stays
fully live the whole time -- answering it is just typing a reply and hitting Send, exactly like
any other turn. Behind the scenes, that reply is merged into the original request (the same
"Details: ..." convention the old Edit-request button used to pre-fill into the box) and re-run
through the same analysis pipeline, so a second still-missing slot asks again the same
conversational way rather than needing a different mechanism.

Also removed "Proceed with stated defaults" as confirmed dead code while making this change: the
panel it lived on was only ever shown for a `blocking` analysis, and that button was always
`setEnabled(not analysis.get("blocking"))` -- i.e. always disabled on every real call, exactly
matching what the user's screenshot showed (a greyed-out button next to an active "Edit
request").

**Live-verified** in real QGIS (`python-qgis.bat`): the question renders as a genuine chat
message with no boxed panel, the input box stays editable throughout, and a plain typed reply
("flood") correctly resolves the pending hazard-type slot and proceeds to the normal preview
step -- confirmed via both a rendered screenshot and the widget's actual text content. 2 tests
updated/added in `tests/test_chat_widget_live.py` (a real headless Qt session, not mocks); full
suite 1524 tests, 0 failures.

<a id="v1-15-1"></a>
## [1.15.1] — 2026-09-13 — Patch: live-hazard-data requests refused despite real tools existing

Live user report (real typos preserved): "show live incedent in jordan in the map creat enew
layer / Details: natural, crime, haszard" got a blanket "I do not currently have direct access
to a verified live feed or real-time incident database..." refusal -- even though this plugin
has shipped 3 real hazard-monitoring tools since v1.9.0: `fetch_gdacs_disaster_alerts`,
`fetch_nasa_eonet_events`, and `fetch_nasa_active_fires`.

**Root cause, diagnosed via direct router simulation rather than assumed** -- two stacked gaps:

1. **No prompt rule connected the intent to the tools.** None of the 47 existing behavioral
   rules told the model that a "live/current hazard or disaster" request maps to these 3 tools
   specifically -- only rule 16 mentioned them, in an unrelated "treat fetched content as data,
   not instructions" context. Even when a tool was available for the turn, nothing told the
   model to reach for it.
2. **Recall into the tool router's top-40 candidate set was unreliable even before the prompt
   gap.** A 30-trial live simulation of the exact reported query found `fetch_nasa_eonet_events`
   was selected only ~47% of the time, and `fetch_gdacs_disaster_alerts`/`fetch_nasa_active_fires`
   never were -- generic words in the query ("map", "layer", "natural") gave ~24 other, unrelated
   tools an equal or higher relevance score. The query's own typos ("haszard", "incedent")
   additionally defeated the existing exact-substring alias-matching mechanism outright.

**Three-part fix:**

- **New prompt rule 48** (`agent/prompts.py`): explicit guidance that live/current natural
  hazard or disaster requests map to the 3 named tools, with explicit instructions for a mixed
  request like the one reported -- fetch and map what the real tools DO cover, and separately,
  honestly state that a category with no real data source (e.g. crime/security incidents) can't
  be fulfilled, rather than declining the whole request. Explicitly cross-references rule 12/42's
  anti-fabrication guarantee so this new positive capability doesn't weaken it.
- **New tool-router aliases** for all 3 hazard tools (`agent/tool_router.py`'s `_TOOL_ALIASES`)
  -- phrases like "current disaster", "live hazard", "what hazards" that share no vocabulary with
  the tools' own descriptions.
- **A small, scoped typo-tolerant correction** (`_expand_query_with_fuzzy_corrections`, difflib-
  based): only for query words 5+ characters long, checked only against a small curated list of
  hazard-domain words (hazard, disaster, incident, wildfire, earthquake, flood, etc.) -- so a
  misspelled "haszard"/"incedent" still resolves to the right alias, without the false-positive
  risk of fuzzy-matching against the plugin's full ~169-tool vocabulary.

**Live-verified end to end** against the exact reported query text: `fetch_gdacs_disaster_alerts`
and `fetch_nasa_eonet_events` are now selected 30/30 trials through the real router (up from
0/30 and ~14/30 before this fix), and rule 48's guidance text is confirmed present in the
resulting assembled system prompt for that query. 11 new tests across `tests/test_prompt_modules.py`
and `tests/test_tool_router.py`; full suite 1512 -> 1523, 0 failures.

**Honest limitation**: the actual downstream model behavior change (does the LLM now correctly
call these tools instead of refusing) cannot be confirmed from this sandbox -- there is no live
network access to a real LLM API here. This release verifies the router selects the right tools
and the prompt carries the right guidance; the user is the one who can confirm the model
actually acts on it in a live session.

<a id="v1-15-0"></a>
## [1.15.0] — 2026-09-13 — Gemini prompt caching (automatic, implicit) + cache-hit visibility

Direct request — "implement gemini caching, check the documentation" — following a real report
of ~168K tokens for one 6-call print-layout turn. Researched Google's current Gemini API docs
before writing any code, not assumed.

**Implicit caching is automatic and free for Gemini 2.5+/3.x models** — no client code needed to
trigger it, ~90% discount on cache hits, no storage cost. It requires the cached content to sit
as a stable prefix above a per-model minimum (2,048 tokens for 2.5 Flash/Pro, 4,096 for 3.x
Flash/3.1 Pro Preview). Confirmed this plugin's system prompt/tools already meet both: they're
computed once before `agent.py`'s tool-calling loop starts and never rebuilt mid-turn — a
multi-call turn's repeated system prompt is exactly the shape implicit caching targets. There was
nothing to implement here beyond confirming it isn't accidentally defeated.

**What was actually missing was visibility.** The Gemini OpenAI-compatible endpoint reports cache
hits via `usage.prompt_tokens_details.cached_tokens` (a sub-breakdown of `prompt_tokens`, not
subtracted from it), but nothing in this codebase surfaced it — so whether caching was helping
was an unverifiable assumption.

- **Explicit caching** (a separate `CachedContent` resource with its own lifecycle/storage cost)
  was considered and deliberately not built: implicit caching already covers the exact scenario
  driving this report — repeated identical content within one turn's loop — for free, and the
  per-turn module-based system prompt (v1.14.0) limits explicit caching's cross-turn reuse value
  for the added complexity.
- `providers/base.py`'s `extract_openai_style_usage` (shared by Gemini/OpenAI/OpenRouter/Ollama)
  now also extracts `cached_tokens` when present.
- `providers/claude.py`'s `from_anthropic_response` gets the same visibility, for symmetry —
  Claude already sends `cache_control` breakpoints (from earlier this session) but never
  surfaced `cache_read`/`cache_creation` token counts either. Anthropic's own `input_tokens`
  deliberately *excludes* cached tokens (unlike Gemini/OpenAI's convention, which includes them
  in the headline total), so it's reconstructed to the full request size for cross-provider
  consistency.
- Session usage now shows e.g. `"~24,747 tokens this session (3 calls, ~14,400 served from
  cache)"` — omitted entirely (not fabricated as 0) when nothing was reported, same honesty
  policy the usage feature has always had.

No new agent tools — 169 tools, unchanged. 18 new tests, full suite 1506 → 1512, 0 failures.
Live-verified end to end in real QGIS 4.2.2: a realistic Gemini response shape parses correctly,
a 3-turn fake-client session accumulates cache hits and produces the exact expected label text,
and the real `ChatTabWidget` renders it.

**Honest limitation, stated plainly**: this sandbox has no live network access to a real Gemini
API key, so whether the actual API genuinely returns `prompt_tokens_details.cached_tokens`
through this specific OpenAI-compatible endpoint (vs. only the native endpoint) is confirmed
against Google's documentation, not confirmed end-to-end against a real response. The parsing
logic is correct for the documented shape and degrades safely (omits `cached_tokens`, doesn't
crash) if the real field name or nesting ever turns out to differ.

<a id="v1-14-1"></a>
## [1.14.1] — 2026-09-13 — Patch: floating dock clamped to the screen

Direct live report: after a long print-layout response, the chat input row was no longer
visible — the floating panel's window appeared to end right where the response content did, no
input box reachable.

Investigated thoroughly before changing anything: tried to reproduce with a small window plus
long content, a bloated Activity tab (many tasks/memory entries accumulated over a session), and
the exact reported scenario (6 API calls, multiple tool-step summaries, a long final response) —
in every headless test, `chat_tab_widget`'s layout correctly kept the input row visible and
positioned within the window (`QTextBrowser.sizeHint()` stays content-independent, confirmed
live; the Activity tab's `QScrollArea` correctly caps its own outward size hint regardless of
its content's real size). Could not reproduce a layout defect in the sandbox.

A floating window that's grown or drifted past the available screen's height/position is a known
Qt/Windows failure mode that produces exactly this symptom — the input row still exists in the
layout, just rendered below the visible screen area, invisible and unreachable without a manual
resize. Added a defensive `resizeEvent` guard: while floating, clamps the dock's geometry to fit
within `QScreen.availableGeometry()` whenever it would otherwise extend past it. Idempotent (a
window already on-screen computes no change), so safe on every resize with no recursion risk.
Only acts while floating — a docked panel is already bounded by the main QGIS window.

Live-verified: forced the dock to an absurdly tall, partly off-screen geometry and confirmed the
guard clamps it back on-screen, with the input row's own on-screen position confirmed within the
visible screen area afterward. `dock_widget.py` has no automated test coverage (no
`QGIS_AVAILABLE` fallback, by its own module docstring), so this relies on live verification per
this file's established convention, not a new unit test. No new agent tools — 169 tools,
unchanged. Full suite unaffected: 1506 tests, 0 failures.

<a id="v1-14-0"></a>
## [1.14.0] — 2026-09-13 — Modularized the 47-rule base prompt by relevance

Follow-up to v1.13.1 (the tool-router side of the same token-waste problem). Direct request: the
remaining ~8,149-token base system prompt should be trimmed the same way tool schemas already
are. Investigated the actual content first, rather than assuming — `BASE_SYSTEM_PROMPT` contains
**no JSON schemas at all** (those are the separate, already-fixed `TOOLS_SCHEMA` path); it's
100% plain-English prose, **47 numbered behavioral rules** always sent in full regardless of
what the request actually needed.

Read and categorized all 47 rules before designing anything, into three tiers — confirmed with
the user via `AskUserQuestion` on risk tolerance for the safety-critical cluster before
implementing:

- **CORE (16 rules, always included)**: task/memory mechanics, the destructive-action safety
  gate, anti-fabrication, output structure, ask-vs-guess defaults. Applies to every request, no
  relevance heuristic needed or wanted.
- **SENSITIVE cluster (10 rules)**: protection-sensitive data handling, never-fabricate-
  security-incidents (rule 42 exists because of a real, cited past incident — a live user report
  of a fabricated Beirut security briefing exported looking authoritative), operational-briefing
  sourcing standards, sensitivity-check-before-export. Included whenever ANY tool from a
  deliberately **wide, hand-verified** trigger list is selected this turn — every export/
  deliverable tool, incident/sensitivity tool, and humanitarian-logistics/routing tool — not
  narrowly gated to "sounds humanitarian." Hand-verified rather than auto-extracted specifically
  for this cluster: a rule's own prose sometimes names the *wrong* tool for triggering purposes
  (rule 42 names `search_web` as the recommended fix for fabrication, not the risky report/
  export action that should actually trigger the rule).
- **Remaining 21 domain rules** (styling, imagery, workflows, documents, forecasting, web
  search, print layouts, time-series dates): trigger tools extracted **automatically** via a
  one-time regex scan of each rule's own backtick-quoted tool mentions against the real
  `TOOLS_SCHEMA` — no hand-maintained list to drift out of sync as tools/rules change.

**Found and fixed a real bug during live verification, not just unit tests**: router-guaranteed
tools (`execute_pyqgis_script`, the 8 always-include core tools) were polluting the
auto-extraction, since their presence in `active_tools` doesn't mean a rule's actual domain is
relevant — rule 30 (print-layout composition) was firing on a plain `"hi"` purely because
`execute_pyqgis_script` is the router's guaranteed no-signal fallback tool, nothing to do with
print layouts. Fixed by excluding router-guaranteed tool names from the auto-extraction signal;
a rule left with zero real trigger tools after that (rule 8) safely falls back to always-on
rather than silently vanishing.

Every rule keeps its **original number permanently** in every tier — 47 rules cross-reference
each other by number (20 such references, confirmed via grep), so renumbering would silently
break them. Included rules are always assembled in ascending numeric order, so the full/
unfiltered `BASE_SYSTEM_PROMPT` (kept for `tests/manual_prompt_rule_evals.py`) is verified
**byte-identical** to this file's pre-modularization content, not just "close enough."
`agent.py`'s `run()` was reordered so `ToolRouter.filter_relevant_tools()` runs before
`build_system_prompt()`, passing the selected tool names through as a new
`active_tool_names` parameter (default `None` reproduces the exact prior behavior for any
caller that doesn't pass it).

No new agent tools — 169 tools, unchanged. **Measured effect**: a real `agent.run("hi")` call's
full payload (system prompt + tools) dropped from ~9,316 tokens (v1.13.1's number) to **~3,184
tokens — ~84% below the original ~22,959-token report** that started this whole thread. Real
GIS requests save 15-30% depending on domain. Live-verified against real QGIS 4.2.2 for a plain
`"hi"`, an export request, a humanitarian-logistics request, and a print-layout request,
confirming the sensitive cluster and the right domain rules appear/don't appear as designed —
plus a spot check across 7 realistic humanitarian-flavored queries confirming the sensitive
cluster fires on every one. 18 new tests, full suite 1488 → 1506, 0 failures.

<a id="v1-13-1"></a>
## [1.13.1] — 2026-09-12 — Patch: a plain "hi" was costing ~23K tokens from tool-router padding

Patch release, found and fixed the same day v1.13.0 shipped: a direct live report that a single
plain `"hi"` message cost **~22,959 tokens for one API call**. Traced to
`tool_router.py`'s `filter_relevant_tools()` always padding out to the full `top_k=40` tool
schemas even for a query with zero real signal — worsened by two real matching bugs, not just
one padding issue:

- **Substring containment, not word-boundary matching.** Name/description scoring used
  `word in text` — a 2-character query word like `"hi"` spuriously substring-matched inside
  completely unrelated tool names (`histogram_equalization`, `highlight_features`, `hillshade`),
  scoring a real-looking +10. That was enough to make the router's own "nothing else matched"
  check evaluate `False`, triggering full `top_k` padding with ~30 more essentially random tool
  schemas. Fixed by splitting tool names on `_` and tokenizing descriptions with the same `\w+`
  regex already used for the query — both checks are now genuine word-boundary membership tests.
- **No-signal queries still padded to `top_k`.** Even once correctly detected as having zero
  real signal, the router still filled the remaining slots with random 0-score filler instead of
  returning only the genuinely useful always-include + fallback set (9 tools). Fixed: a
  no-signal query now returns only tools that scored above 0.
- **A follow-up gap the word-boundary fix alone didn't close**: `"hello there"` still pulled in
  the full padded set, because `"there"` is a genuine standalone word in several tool
  descriptions' ordinary prose (`"is there flooding here"`) — a true match, just for a word
  carrying zero intent signal. A small, conservative stopword list (articles, pronouns, common
  greetings/acknowledgments) is now filtered out of query words before scoring — the curated
  alias list and the always-include/fallback logic are untouched.

Every real-signal query tested (buffer, calculate severity index, NDVI, all 8 existing
alias-coverage tests) is completely unaffected — still gets the full `top_k=40` candidate pool
exactly as before. Measured effect: `"hi"`'s filtered-tools payload dropped from 40 tools
(~8,133 tokens) to 9 tools (~1,027 tokens); a real `agent.run("hi")` call's full payload (system
prompt + tools) dropped from ~22,959 to ~9,316 tokens in live verification against a real QGIS
4.2.2 session, not just the router in isolation. No new agent tools — 169 tools, unchanged. Full
suite 1484 → 1488 tests, 0 failures.

<a id="v1-13-0"></a>
## [1.13.0] — 2026-09-12 — Rate-limit/task-size resilience: 429-aware backoff, adaptive pacing, mid-turn compaction

Direct request: prevent a large/complex request from failing outright when it hits a provider's
API rate limit, or simply from its own size. Investigated actual current behavior before
designing anything, rather than assuming: `agent.py`'s tool-calling loop could fire up to 20
back-to-back `client.complete()` calls with **zero pacing**, and each iteration re-sent every
prior tool result in full — a large task's per-call payload grows unbounded through the turn.
When the iteration limit was hit, the turn just stopped with a static message asking the *user*
to manually break up their own request — no automatic mitigation. Separately, `post_with_retry`
already retried a transient 429/5xx twice with a short 1.5s/3s backoff, but a genuine *sustained*
per-minute quota breach usually outlasts that. OpenRouter's client turned out to already have
real resilience here (a model-fallback chain plus a 30s-wait/3-cycle loop) — confirmed via grep
that Claude, OpenAI, Gemini, and Ollama had nothing like it, only the shared short-backoff path.

- **429 gets its own, longer retry budget** (`providers/base.py`): `RATE_LIMIT_BACKOFF_SECONDS=10`,
  `RATE_LIMIT_MAX_RETRIES=3` (10s/20s/30s, roughly a minute of patience) — separate from the
  existing generic 5xx/network-blip budget, since a rate limit needs to wait out an actual quota
  window while a transient 5xx usually clears in a second or two. Lifts Claude/OpenAI/Gemini/
  Ollama to roughly OpenRouter's own level of sustained-rate-limit resilience. Also fixed
  `gemini.py`'s `grounded_search()` — the one raw `requests.post()` call a grep sweep found
  bypassing the shared retry helper entirely.
- **Adaptive inter-iteration pacing** (`agent.py`): once a turn's tool-calling loop passes 3
  iterations, each further one adds a short `1.2s` delay before the next `client.complete()` call
  — a normal, small request (1-3 tool-call rounds) pays nothing at all; only a genuinely large
  multi-step task starts spacing its own remaining calls out, in direct proportion to how large
  it's getting, reducing the chance of ever tripping a provider's requests-per-minute limit in
  the first place rather than only reacting after the fact.
- **Mid-turn context compaction** (`agent.py`): once a turn's in-flight message list accumulates
  more than 8 tool-result messages, older **successful** ones get replaced with a short
  placeholder — the most recent 8 stay in full. Any tool result containing an `"error"` key is
  **never** compacted, at any age — failures stay load-bearing, the identical call v1.12.0's chat
  tool-steps redesign already made for the identical reason. This is turn-local: the in-flight
  message list never touches persisted conversation history, so compaction only affects what
  gets sent for the rest of the turn already in flight.

No new agent tools — 169 tools, unchanged. Full suite 1484 tests (up from 1478), 0 failures.
Live-verified against a real `CartogenAi` agent instance and real tool dispatch (`get_layers`
against a real `QgsProject`, not a stub) in real QGIS 4.2.2: a 20-iteration looping turn produced
exactly 17 pacing sleeps (iterations 3-19) and correctly compacted 11 old tool results while
keeping the most recent 8 in full.

<a id="v1-12-0"></a>
## [1.12.0] — 2026-09-12 — Onboarding profile, Help auto-show, tidier tool-call summary

Third round of the same real-session feedback thread as v1.11.0, starting with a genuine
regression in that release's own bubble accent stripe, then a further batch of direct requests
clarified via AskUserQuestion before implementing.

- **The v1.11.0 accent stripe wasn't actually rendering.** It looked correct in code and had
  passed a screenshot "confirmation" — but that check only found the expected accent color
  *somewhere* in a full-widget screenshot, not proven to be the bubble itself. The real bug: Qt's
  rich-text table CSS silently drops `border-left` when a `border` shorthand is already set on
  the same cell — confirmed by rendering an unmistakable magenta `border-left` in isolation and
  finding it never appeared in the output at all. Fixed with a two-cell table instead of a CSS
  trick: a dedicated 3px stripe cell using only `background-color` (no border), beside a content
  cell keeping its border but only on 3 sides. Verified properly this time by isolating just the
  `QTextBrowser` (not the whole parent widget, which has its own accent-colored QSS chrome — the
  exact trap that produced the false-positive the first time) and checking for a narrow,
  spatially-consistent run of the exact accent color.
- **Version menu entry removed.** v1.11.0 added a disabled `"Cartogen AI vX.Y.Z"` Plugins-menu
  entry alongside the version already shown inside Help — direct same-day feedback said that was
  one place too many. Version now shows only inside the Help dialog's own content.
- **Help now auto-shows**: the first time the plugin ever loads, and again once after any version
  update (a new `help_last_shown_version` setting compared against `metadata.txt`'s version on
  every `initGui()`) — previously the user had to know to look for it in the Plugins menu at all.
- **New first-use onboarding profile** (`agent/onboarding_profile.py`, `ui/onboarding_dialog.py`):
  a short dialog — narrative intro, then role/use-case, QGIS experience level, and communication
  style pickers — saved as a real, human-readable `user_profile.md` in the QGIS profile directory,
  not a hidden settings blob, so it can be opened and hand-edited directly. Feeds the base system
  prompt on every request via a new `build_system_prompt(user_profile_ctx=...)` parameter,
  deliberately separate from `prompt_refiner.py`'s pre-existing "user_profile" (the Refinement
  Persona sector dropdown, a different concept that only steers the optional prompt-refinement
  rewrite). Deliberately a static dialog, not an LLM-driven conversation — onboarding has to work
  before any API key is configured, which a live "the agent asks you" exchange wouldn't. Re-editable
  anytime via a new Settings → "Edit My Profile…" button.
- **Chat tool-call display redesigned.** Every tool call previously rendered 2 separate lines
  directly in the conversation scrollback (`Using X` / `Used X`) — real feedback called this too
  much visual space, too much raw detail, and too much visual noise for a multi-tool-call turn.
  "Running" status now updates the existing status label in place instead of adding a scrollback
  line; terminal steps are collected per turn and flushed as **one** compact
  `"N tool calls · name, name"` summary with a "Details" toggle — this chat log's first internal
  clickable anchor (intercepted via `anchorClicked` with `openLinks` disabled; real http(s) links
  in AI responses are unaffected, still handled by `openExternalLinks`). Any failed step's error
  text is always shown regardless of toggle state, never collapsed. The toggle is implemented via
  `QTextCursor` position tracking with explicit shift-adjustment for every later block after an
  edited one — directly live-verified with a 2-turn scenario proving stored positions actually
  shift correctly and a later block's toggle still targets the right span afterward, rather than
  trusting that the logic "looks right" (the same lesson this session's bubble-border fix already
  ran into twice).

No new agent tools — 169 tools, unchanged. Full suite 1478 tests (up from 1457), 0 failures.
Live-verified against real QGIS 4.2.2 throughout: `OnboardingDialog` builds and its Other-role
field toggles correctly; a full save writes a real `.md` file to disk and
`get_formatted_onboarding_context()` reads it back; Settings' Edit My Profile button opens it;
`build_system_prompt()` includes the profile block end to end; Help auto-show/onboarding-trigger
logic exercised through all 3 states (first run, same version, version bump) via a mocked
`iface`; the tool-steps toggle mechanism per above.

<a id="v1-11-0"></a>
## [1.11.0] — 2026-09-12 — Real-session UI fixes: bubble double-border, Activity tab rename, Help moved to menu

The v1.10.0 UI redesign above was verified against this session's own synthetic `widget.grab()`
screenshots. A user then shared real screenshots from their own live QGIS session, and they
caught two genuine bugs the synthetic ones never surfaced, plus several direct layout requests.

- **Chat bubbles, two stacked bugs.** `QTextBrowser` renders message HTML through Qt's own
  rich-text engine — a CSS 2.1-ish subset with **no `border-radius` support at all** — so the
  existing `border-radius:8px` had never actually worked; every bubble has always rendered as a
  sharp rectangle in real QGIS, unlike this same dock's QSS-styled buttons/tabs, which do support
  `border-radius` (a completely different rendering path). Separately, the outer alignment
  `<table>` never set `border="0"`, so Qt's rich-text engine drew its own default border around
  it, stacking visibly with the inner bubble's real border — a genuine double border. Fixed both:
  `border="0"` on the outer table, and the dead `border-radius` replaced with a
  `border-left:3px solid` accent stripe (the same flat-message shape GitHub PR review comments
  and Slack thread replies use) — user messages get the brand accent, agent messages stay
  neutral. `chat_formatting.derive_bubble_colors()` now exposes that accent value directly.
- **A Qt mnemonic-parsing bug.** "Tasks & Notes" rendered as "Tasks _Notes" in the screenshots —
  Qt's plain-text widget-label parser treats a bare `&` immediately followed by a space as an
  accelerator marker it can't resolve. (The QGIS Plugins-submenu title `"&Cartogen AI"` is *not*
  affected — `&` immediately followed by a letter is a normal, working mnemonic.) A full sweep
  found the same `"X & Y"` pattern in 3 more `tasks_tab_widget.py` labels (`QGroupBox`,
  `QPushButton` — the same affected widget types) not visible in the screenshots but very likely
  broken the same way, plus 3 rich-text `QLabel`s that aren't actually affected (HTML content
  bypasses the mnemonic parser) but got the same wording fix for consistency. Renamed the tab
  itself to **Activity** — the user's own choice among the options offered — rather than just
  escaping the ampersand, spelling out "and" everywhere else.
- **Help moved out of the dock entirely**, into the QGIS Plugins menu (`Cartogen AI → Help`) as a
  standalone non-modal dialog reusing the existing `HelpTabWidget`. A new disabled
  `"Cartogen AI vX.Y.Z"` menu entry (read at runtime from `metadata.txt`, mirroring
  `plugin_upload.py`'s own `get_plugin_version()`) makes version info discoverable from the main
  menu, per direct request — also shown a second time at the top of the Help dialog's own content.
- **Quick-suggestion chip row removed** from the bottom of the Chat tab ("irrelevant" — direct
  feedback). `QUICK_SUGGESTION_CHIPS` stays defined in `dock_constants.py`; Help's own
  example-prompts list is its only consumer now.
- **Both scrollbars showing at once on the Activity tab, fixed.** Its `QScrollArea` now forces
  `ScrollBarAlwaysOff` horizontally so content wraps instead of ever triggering horizontal
  scroll; vertical scrolling (needed to stop the dock forcing the whole QGIS window taller than
  the screen) is unchanged.

No new agent tools — 169 tools, unchanged. Full suite 1457 tests (up from 1456), 0 failures.
Live-verified against real QGIS 4.2.2: 2 tabs (Chat, Activity, down from 3), zero chip buttons,
horizontal scrollbar policy confirmed `ScrollBarAlwaysOff`, `HelpTabWidget` builds standalone
with a version string, and `dock-panel.png`/`chat-conversation.png` regenerated to show the
corrected UI.

<a id="v1-10-0"></a>
## [1.10.0] — 2026-09-12 — UI & Chat Redesign: brand-accent blending, theme-reactive SVG icons

A visual polish pass on the dock/chat UI, grounded in real QGIS plugin design research rather
than generic web-design advice — published first as a review Artifact, corrected once (a
research agent had reported 3 already-fixed UX-audit items as still open; re-reading the live
code before planning caught it), then implemented as 4 workstreams. Structure, the markdown
renderer, and the message-bubble mechanism are unchanged — this is polish on a sound base, not a
rebuild.

- **Two-tier theme detection.** `ui/theme.py`'s new `_detect_theme_mode()` checks QGIS's own
  named theme (`QgsApplication.instance().themeName()`, `"Night Mapping"`/`"Blend of Gray"`)
  before falling back to the existing palette-luminance read — QFieldSync's real, shipping
  pattern (`qfieldsync/gui/utils.py`), since a named theme can pick a scheme that doesn't show
  up as a clean luminance difference in every `QPalette` role.
- **Brand-accent color blending.** New `_brand_accent()` in `chat_formatting.py` blends QGIS's
  own live accent color toward the Cartogen brand teal (`#1F7A6C`) at a modest 0.35 ratio,
  reusing the already-tested `_blend_hex()` helper — a blend, never a replacement, so the accent
  still varies across QGIS themes instead of becoming one fixed color. Wired into
  `derive_bubble_colors()` (the user-message bubble tint) and `build_dock_stylesheet()`
  (buttons, selected-tab underline, focus border, chip buttons). The first brand color to reach
  the running UI at all — every color before this was purely QGIS-palette-derived, with zero
  connection to the plugin's own documented brand system.
- **Theme-reactive SVG icons.** New `ui/icons.py`: hand-authored, in-repo SVGs (attach, send,
  stop, settings) — matches the observed QGIS plugin-ecosystem convention (custom SVG icons
  in-repo, e.g. `opengeos/qgis-plugin-template`) rather than an icon font. `themed_icon()`
  renders a template at a given color entirely in memory (no temp file), colored from the live
  palette at construction time — the same pattern TerraLabAI's `QGIS_AI-Segmentation` plugin
  uses for its own dock icons. Replaces the plain Unicode emoji (📎 ➤ ⏹ ⚙) in the chat input
  row and the Settings button. The toolbar/menu action icon also switched from a flat `icon.png`
  to `icon.svg`, a copy of the real brand mark — placed at the plugin root specifically because
  `plugin_upload.py`'s `EXCLUDE_DIRS` excludes the whole `branding/` folder from the release
  zip; pointing directly at `branding/cartogen-mark.svg` would have silently shipped a plugin
  with an empty toolbar icon. Caught by checking the exclusion list before wiring it up, not by
  trial and error.
- **One wording alignment.** The Preview panel's bypass-send button ("Send my wording only") now
  matches the Refinement panel's identical action ("Send as typed instead") exactly — the one
  real inconsistency once the other 3 items a prior UX audit flagged were confirmed already
  fixed in code.

No new agent tools — 169 tools, unchanged. 9 new tests (color-blend determinism/non-collapse
behavior, icon SVG generation). Full suite 1456 tests (up from 1447), 0 failures. Live-verified
against real QGIS 4.2.2 via actual rendered screenshots of the wired-up input row, dock header,
gate-panel wording, and toolbar icon, in both light and forced-dark palettes — not just
import-success checks, since a visual redesign can't be verified any other way.

<a id="v1-9-0"></a>
## [1.9.0] — 2026-09-12 — Live Hazard Monitoring: NASA FIRMS/EONET + GDACS tools, dashboard freshness badges

Inspired by [koala73/worldmonitor](https://github.com/koala73/worldmonitor)'s live-event
dashboards (crisis/disaster alerts, satellite fire detections) — adapts the *techniques*, not
code (a completely different stack), and deliberately kept narrow: hazard data feeding this
plugin's existing humanitarian analysis tools, not a general "crisis/geopolitical intelligence"
product. Positioning checked against this project's own commercial strategy docs before
building — see `docs/archive/COMMERCIAL_PRODUCT_STRATEGY.md`'s feature-placement test and
`docs/archive/ENTERPRISE_GROWTH_PLAN.md`'s explicit warning against broadening Cartogen's
positioning beyond humanitarian-GIS-first.

- **3 new live hazard fetch tools**, `agent/tools/hazard_monitoring_tools.py`:
  - `fetch_nasa_active_fires` — NASA FIRMS VIIRS active-fire/thermal-anomaly detections. First
    Cartogen tool needing its own API key, separate from any LLM provider key — a new optional
    field in Settings ("NASA FIRMS API Key"), stored via the same `CredentialManager` every
    provider key already uses.
  - `fetch_nasa_eonet_events` — NASA EONET natural event tracker (wildfires, storms, volcanoes,
    floods, and more). Free, no key.
  - `fetch_gdacs_disaster_alerts` — GDACS UN-coordinated disaster alerts, each with a
    human-assigned Green/Orange/Red severity. Free, no key. Live-verified GDACS's own bbox query
    parameter doesn't actually filter server-side, so filtering happens client-side after
    fetching, the same pattern `fetch_building_footprints` already uses for its tile crop.
  - All 3 use `[min_lon, min_lat, max_lon, max_lat]` (matching `search_stac_satellite_imagery`),
    deliberately not `fetch_building_footprints`'s `[south, west, north, east]` — a real footgun
    confirmed live during this project's own v1.8.3 release smoke test.
  - Re-running any of the 3 (e.g. on a schedule) **replaces** that layer's features with the
    latest fetch rather than accumulating duplicates. Each auto-tags layer confidence
    (`OBSERVED` for FIRMS/EONET, `DERIVED` for GDACS) and stamps a `cartogen_ai/fetched_at`
    custom property.
- **`generate_situation_dashboard`** — one call fetches all 3 sources for a bbox and exports
  them as a single HTML dashboard.
- **Wired into the existing monitoring scheduler** — all 3 tools added to
  `_ALLOWED_WORKFLOW_TOOLS`, extending its documented safety rationale to a second category
  (idempotent external-data-refresh, never touches user-authored data). `run_monitoring_workflow`
  now reports real "N new fire detections since last check" via its existing
  `_diff_unit_results` mechanism — zero new diffing code, the honest analog of a competitor
  product's persistence tracking built on infrastructure this project already had and had
  already tested.
- **Dashboard freshness badges** — the piece most directly asked for. `generate_html_dashboard`/
  `generate_temporal_dashboard` now render a small color-coded pill per layer that carries a
  `fetched_at` stamp: green "Fresh 2m", amber "Stale 3h", red "Very stale 2d", with a hover
  tooltip showing the exact fetch time. Reproduces the competitor product's exact freshness-pill
  visual pattern in plain inline HTML/CSS — no JS framework, no new dependency. Purely additive:
  a layer never fetched from a live source renders with no badge, and every existing caller
  keeps working unchanged.

41 new tests (25 for the hazard tools, 16 for the freshness badges). Full suite 1447 tests, 0
failures (up from 1406 at the start of this release). 169 tools (up from 165). A real bug
(`generate_situation_dashboard` raising `KeyError` when QGIS is unavailable) was caught by this
release's own test suite and fixed before it shipped. Live-verified against real QGIS 4.2.2 and
the real NASA FIRMS/EONET/GDACS APIs throughout — real layers created, confidence/freshness
stamped correctly, replace-in-place confirmed on a second fetch, client-side GDACS bbox
filtering confirmed to actually narrow results (99 → 3 for a regional bbox), the monitoring
scheduler's diff cycle confirmed against real GDACS data, and the Settings dialog's new FIRMS
key field confirmed to round-trip through the same credential storage every provider key uses.

<a id="v1-8-3"></a>
## [1.8.3] — 2026-09-12 — Patch: release zip was silently missing 4 relocated archive docs

Fixed `BUG-2026-09-12-2`, found and fixed the same day v1.8.2 shipped — caught while verifying
that the v1.8.2 release zip installs cleanly in QGIS, before announcing it.

- **Release zip was missing content.** `plugin_upload.py`'s `EXCLUDE_FILES` matches a file by
  basename regardless of directory. `IMPLEMENTATION_TASK_LIST.md`, `LICENSE_AUDIT.md`,
  `CARTOGEN_AI_PRD.md`, and `CARTOGEN_AI_FEATURE_LIST.md` were correctly excluded there when
  they lived at the repo root (internal dev docs). v1.8.2's repo-organization pass moved all 5
  of those docs (the 4 above, plus `DOCUMENTATION.md`) into `docs/archive/` — a directory that
  is *not* excluded and whose other ~29 files ship normally — but the same 4 stale basenames
  kept matching there too, so `cartogen_ai_v1.8.2.zip` silently shipped without them while their
  sibling `DOCUMENTATION.md` (never in `EXCLUDE_FILES`) shipped fine. Did not affect plugin
  functionality: confirmed via a real QGIS 4.2.2 headless import of the extracted v1.8.2 zip
  that `__init__.py` imports cleanly, `classFactory` is present, and all 165 tools register —
  this was a shipped-content-completeness bug, not a functional one. Fixed by removing those 4
  entries from `EXCLUDE_FILES`; rebuilt the zip and re-verified (fresh `unzip -l` plus another
  real-QGIS import) that all 5 moved docs are now present and non-trivial after extraction.

Full suite unchanged: 1406 tests, 0 failures (packaging-script fix only, no `src/` behavior
touched).

<a id="v1-8-2"></a>
## [1.8.2] — 2026-09-12 — Docs-only: repo reorganization and documentation polish pass

No code, tool, or behavior changes. Prompted by a request to make the repo read as professional
for three audiences at once: external GitHub contributors, a humanitarian-org (UN/NGO)
due-diligence reviewer, and general internal tidiness — while keeping every existing technical
detail, not stripping it down.

- **5 frozen historical docs moved into `docs/archive/`** — `CARTOGEN_AI_FEATURE_LIST.md`,
  `CARTOGEN_AI_PRD.md`, `DOCUMENTATION.md`, `IMPLEMENTATION_TASK_LIST.md`, `LICENSE_AUDIT.md`
  (`git mv`, content unchanged, full history preserved). Every live reference updated; the moved
  `DOCUMENTATION.md`'s own ~27 internal relative links fixed for its new location.
- **Stale tool counts fixed.** "131 tools" → 165 in `README.md`, `docs/PRODUCT_TIERS.md`, and
  `docs/RELEASE_SMOKE_TEST.md` — left untouched wherever a document was explicitly describing a
  dated historical snapshot rather than making a present-tense claim.
- **`README.md`** gained a table of contents and a regrouped, expanded Documentation table
  (Getting started / Security & compliance / Engineering & process / Product & humanitarian
  standards / Roadmap & archive / Project reference) — surfacing 9 previously-untabled files,
  including the GDPR compliance review and DPIA screening worksheet that had no discoverable
  path from the README before. Also gained a dedicated Contributing section.
- **New `docs/README.md`** index, reusing the same category grouping, for anyone browsing the
  `docs/` folder directly on GitHub; notes the two dev scripts' purpose inline so their presence
  reads as intentional.
- **`docs/archive/README.md`** gained a one-line-per-file index of all 33 archived documents.
- **`SECURITY.md`** gained a table of contents over its 19 sections.
- **`CHANGELOG.md`** — the 4 previously-undated `[1.7.0]`–`[1.8.1]` headers now carry real
  dates, plus this "Recent releases at a glance" quick-index.

Full suite unchanged: 1406 tests, 0 failures (comment/doc-only changes touch no `src/` behavior).

<a id="v1-8-1"></a>
## [1.8.1] — 2026-09-12 — Patch: dashboard OSM-blocked basemap + canvas not following new layers

Direct live user report, not from a planned workstream.

- **Dashboard basemap blocked by OpenStreetMap.** `generate_html_dashboard`/
  `generate_temporal_dashboard` (`agent/tools/export_tools.py`) both called bare `folium.Map()`,
  which defaults to raw, unthrottled, uncached `tile.openstreetmap.org` requests with no custom
  User-Agent — exactly the pattern OpenStreetMap's own tile usage policy blocks for bulk/
  embedded-app use. Switched both to `tiles="cartodbpositron"`, folium's standard permissively-
  licensed alternative built for exactly this "embed a basemap in your own generated page" case.
  Confirmed directly that the generated HTML no longer references `tile.openstreetmap.org` at
  all, for either dashboard builder.
- **Canvas doesn't follow new/changed layers.** New `zoom_to_layers()` (`ui/canvas_highlight.py`)
  wired into `ChatTabWidget._after_successful_response` — moves the canvas to the union extent of
  whatever layer(s) a turn's response mentions, once per turn, alongside the existing highlight-
  flash behavior. A real bug caught live before shipping: the first version also skipped any
  layer whose extent was "empty" (zero width/height) alongside a genuinely null extent — live-
  confirmed against real QGIS 4.2.2 that a single-point layer's extent is legitimate but
  registers as empty (a point has no area), so that check silently dropped every single-point
  layer, one of the most common layer types this plugin creates. Corrected to match the existing
  single-layer `zoom_to_layer` tool's own behavior.

8 new tests. Full suite 1406 tests, 0 failures. Live-verified against real QGIS 4.2.2 with a real
`QgsMapCanvas` (not mocked): a single-point layer moved the canvas off a deliberately stale
extent, two layers produced a real union extent, and a cross-CRS layer produced a correctly-
transformed extent.

<a id="v1-8-0"></a>
## [1.8.0] — 2026-09-12 — Cartographic Intelligence: visualization selection, real QA gate, isochrone bands

Adapts an external "QGIS Cartographic Intelligence Standard for AI Agents" document to this
plugin's own architecture, as an integration/gap-closure pass on real existing infrastructure
(`_classify_values`'s skewness-driven classification, `_compute_severity_index`'s composite-index
engine, `dataset_status.py`'s QA-gate state machine, `sensitivity.py`/`confidence.py`'s
classification tags) rather than a from-scratch build. Plan:
`~/.claude/plans/idempotent-popping-haven.md`.

- **Visualization selection.** New `recommend_visualization_method(layer_name, field?,
  intended_message?)` — inspects a layer/field's real geometry type, field type, cardinality,
  and distribution, and returns a recommended styling tool + rationale + warnings. Advisory
  only: never applies styling itself, matching the existing "state the default, don't stop to
  ask" convention. Flags the single most common real-world misuse directly — a raw-count-shaped
  field on a polygon layer gets an explicit warning about choropleth-coloring counts instead of
  a normalized rate. New `apply_rule_based_style` — a real `QgsRuleBasedRenderer` (previously
  unused in this codebase), for fixed-vocabulary fields (e.g. route/facility status) needing a
  caller-chosen color per value plus a mandatory "Unknown / No data" catch-all class.
- **Real sensitivity in the QA checklist.** `generate_map_product_qa_checklist`'s disclosure
  section used to be a static "no automated classification exists yet" stub even after
  `set_layer_sensitivity`/`get_layer_sensitivity` shipped — it simply never read them. Now reads
  the real tag, reason, and export warning. Two new informational categories:
  `classification_sanity` (flags a single-symbol-rendered layer with a numeric field worth a
  second look) and `export_integrity` (confirms an exported file actually exists on disk with
  real content).
- **A real blocking cartographic QA gate.** `dataset_status.py`'s `CARTOGRAPHY_READY →
  PUBLICATION_READY` transition — previously the only transition with zero automated checks of
  any kind — now has a real, opt-in `map_qa` check: blocks the advance if a mandatory print-layout
  element is missing or the layer is tagged RESTRICTED/SENSITIVE, with the same
  `override=True` + mandatory-note bypass every other check in this state machine already uses.
- **Isochrone / access-band styling.** `calculate_service_area`'s `travel_cost` now accepts a
  list (e.g. `[15, 30, 60]`) as well as a single number — builds one combined,
  `travel_cost_band`-tagged polygon layer per facility instead of requiring N separate calls,
  auto-styled with a graduated renderer in the same call. The pre-existing single-value path is
  completely unchanged.
- **New behavioral rules.** Missing/suppressed/not-assessed values must never land in the same
  class as a real zero; establish purpose/audience/sensitivity before a finished cartographic
  deliverable (a conversational MapBrief, not a rigid pre-flight form); a raw-count choropleth
  must be normalized or have its denominator named explicitly; a RESTRICTED/SENSITIVE layer's
  tag must be surfaced in chat before an export touching it, not left only to the QA gate.

Full suite: 1398 tests, 0 failures. Live-verified against real QGIS 4.2.2 throughout, including
real rendered-pixel checks (a rule-based route-status layer, a multi-band isochrone map with
monotonically growing hull area per band) and a real blocking-gate test (a SENSITIVE-tagged
layer correctly blocked, then correctly advanced via override).

Explicitly out of scope this release (named, not dropped): bivariate choropleth, flow/OD maps, a
small-multiples/change-map compositor, uncertainty-*rendering* (confidence tags exist, drawing
them doesn't yet), a standard-deviation classification mode, a rigid structured MapBrief object,
and a minimum-count/k-anonymity suppression method for `sensitivity_tools.py`.

<a id="v1-7-1"></a>
## [1.7.1] — 2026-09-11 — Patch: portrait print-layout body/footer overlap fixed

- **`BUG-2026-09-11-1` fixed, same day it was found.** `create_print_layout`'s portrait
  orientation had a `body_h` sized for roughly one line of text, but `QgsLayoutItemLabel`
  doesn't clip overflowing content — any `body_text` longer than that silently overflowed
  downward into the standing disclaimer footer, exactly the multi-line "bullets/findings"
  usage the tool's own schema description encourages. Found live against real QGIS 4.2.2 via
  a real `QgsLayoutExporter` PNG export, visually inspected.
- Two changes in `agent/tools/layout_tools.py`: the disclaimer footer is now pinned to a fixed
  distance from the page bottom instead of being derived from `body_y+body_h`, so its position
  no longer depends on how much `body_text` overflows; new `_fit_text_to_box()` (pure Python,
  calibrated from a real live render) truncates `body_text` — by whole words, with an ellipsis
  — to what the box can actually hold before it's ever handed to the label. This is the real
  fix: since the label itself never clips, only bounding the text content guarantees no
  overflow regardless of exactly how generous the mm budget turns out to be.
- 6 new tests. Full suite 1339 tests (up from 1333), 0 failures, 7 skipped. Live-verified
  against real QGIS 4.2.2 with the exact repro that found the bug — the exported PNG now shows
  a cleanly truncated body paragraph and a fully legible, unobstructed disclaimer footer.
- Landscape untouched — already live-confirmed clean (2026-09-05); the same truncation guard
  isn't applied there yet, flagged as an optional defense-in-depth follow-up, not a known
  failure.

  **Correction, 2026-09-11, same day (documentation only, no code change — kept per this
  project's frozen-changelog convention rather than edited in place):** the line above is
  wrong. `_fit_text_to_box()`'s call site sits in the shared code path after the
  portrait/landscape `if`/`else` block closes, not inside the portrait-only branch, so it
  already ran for landscape too, using landscape's own `(col_w=95, body_h=78)` values, from the
  moment this release shipped — there was no gap to revisit. Verified live against real QGIS
  4.2.2 with an extreme 2774-character `body_text`: truncated cleanly with an ellipsis, footer
  fully legible and unobstructed. A regression test
  (`test_landscape_dimensions_also_truncate_an_extreme_body_text`) locks this in going forward.

<a id="v1-7-0"></a>
## [1.7.0] — 2026-09-11 — Security & Logistics: GDPR export, undo/rollback, sandbox Tier 2, network-aware routing

Scoped for a humanitarian org (UN/NGO) deployment/pilot with an Oct 15, 2026 target — data
protection and operational safety first, sandbox architecture second, logistics third. All four
workstreams are grounded in gaps this repo's own docs had already found and left open, not
invented from scratch: `docs/GDPR_COMPLIANCE_REVIEW.docx` (F6–F9),
`docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md` (points 8, 19, 20),
`docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md` (§2 items 2–3). Plan:
`~/.claude/plans/idempotent-popping-haven.md`.

- **GDPR F6–F9 closure.** `agent/memory.py`'s persistent project-memory writes (the sidecar
  `<project>_spatial_memory.sqlite` file and the embedded `QgsProject` custom property — both a
  second, easy-to-miss copy that travels with the project) are now gated behind the same
  opt-in, default-off settings-dialog toggle `chat_persistence.py` already uses for chat
  history; the in-memory cache stays always-on since the agent needs it within a session. New
  "My Data" export (`agent/data_export.py`, `export_stored_data` tool, and a button in the
  Notes/Memory panel) assembles project memory + global memory + chat history into one JSON
  document a user can save — closing F7/F8's "no consolidated view of what the agent knows
  about me" gap. F9 (erasure can't reach previously-distributed file copies) documented in
  `SECURITY.md` as an inherent property of local files, not a code defect.
- **Undo/rollback for a priority subset of MODIFY/DELETE tools.** New
  `agent/tools/_snapshot_registry.py` — an explicit, auditable `{tool_name: (snapshot_fn,
  restore_fn)}` registry, snapshotted before dispatch and consumed by `undo_last_operation` —
  covers `remove_layer`; `field_calculator`/`calculate_area`/`calculate_length`; the three
  `apply_*_style` tools; and `set_dataset_status`/`set_layer_sensitivity`/
  `set_layer_confidence`/`run_query`. A real bug caught live before shipping: the original
  design (hold a Python reference to a removed layer) is wrong —
  `QgsProject.removeMapLayer()` destroys the underlying C++ object immediately; fixed via
  `layer.clone()` taken before removal. `load_project` undo and MODIFY tools outside this
  priority subset are explicitly out of scope for this release, not silently dropped.
- **Sandbox Tier 2: a real allow-listed Processing path.** New
  `run_allowlisted_processing_algorithm(alg_id, params)`
  (`agent/tools/processing_allowlist_tools.py`) validates `alg_id` against a hard-coded,
  code-derived 36-id allow-list (grepped from every `processing.run()` call already trusted
  across this codebase) and calls `processing.run()` directly with a constrained params
  contract — never executes arbitrary code, so it adds no new sandbox-bypass surface.
  `execute_pyqgis_script`'s description now names this as the preferred path for "run one
  Processing algorithm" requests. The full tiered-allow-list rewrite (point 19's larger
  question) remains open; this closes one real, valuable slice of it.
- **Logistics: composite impedance + network-aware multi-stop routing.** New
  `build_composite_impedance_field` (`agent/tools/impedance_tools.py`) blends OSM
  `highway`-class baseline speed, `surface` penalty, an optional 0.0–1.0 `damage_field`
  (passability), and an optional DEM-derived endpoint-slope penalty into one `impedance_cost`
  field — feeds directly into `calculate_service_area`/`travel_time_matrix`'s existing
  `speed_field` parameter, no changes needed on either tool. `optimize_delivery_route` now
  builds a real road-network distance matrix (`native:shortestpathpointtopoint`'s `cost`
  output per ordered pair — `travel_time_matrix` was tried first but its destination-side
  matrix keys turned out unmappable back to stop names, confirmed live) before running its
  existing nearest-neighbor + 2-opt heuristic, so stop *order* is now road-network-aware, not
  just the final drawn route line. True VRP via OR-Tools and turn-cost/turn-penalty support
  remain real, deliberately unbuilt gaps (QGIS's native algorithms expose no turn-cost
  parameter at all).

All four workstreams live-verified against real QGIS 4.2.2. Full suite 1333 tests, 0 failures.
`docs/TOOLS_REFERENCE.md` regenerated (163 tools). See
`docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md` and `docs/MASTER_TASK_REGISTRY.md`
items 37–40 for full per-workstream detail.

## [1.6.0] — QA-gate infrastructure, GDPR remediation, live-verified QGIS 4.2 fixes

- **Repo reconciliation.** This checkout and `cartogen-ai-community` had diverged as two
  private clones of the same remote with mutually unpushed commits since a shared ancestor.
  Reconciled: fast-forward pulled the already-merged `origin/main`, resolved the remaining
  local working-tree conflicts (a duplicate `clear_global_notes()`, a duplicate `class
  ConnectionType` stub, two silently-shadowed duplicate test methods — all found and fixed,
  not just merged over), and reapplied the held "hosted account" feature's Qt6 enum fix
  through the project's canonical `qgis_compat.enum_member()` helper.
- **QA-gate / dataset-status infrastructure**, built from a 27-point QGIS-first production
  standard review (`docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`): a real
  `INGESTED → STAGED → VALIDATED → ANALYSIS_READY → CARTOGRAPHY_READY` state machine
  (`agent/dataset_status.py`) that layers/tools now advance through, with automated checks
  wired into the gate rather than left as documentation — geometry QA (duplicate/overlapping
  features, small-polygon threshold), P-code uniqueness/hierarchy validation
  (`agent/pcode_validation.py`, alias-list field matching for real COD-AB naming variance),
  and opt-in schema contracts (`agent/schema_contracts.py` + `agent/contracts/*.json` for
  health facilities and admin2 boundaries) that check field presence, type, and controlled
  vocabularies. A machine-readable provenance sidecar (`agent/provenance.py`,
  `write_provenance_sidecar`) assembles QGIS version, tool-lineage, and QA-gate history into
  a `.provenance.json` written beside the layer's own source file.
- **GDPR compliance remediation.** Closed finding F1 (global memory had no bulk erasure
  path) with `MemoryManager.clear_global_notes()` plus a confirm-gated "Clear Global Memory"
  UI control, and remediated four further HIGH findings (F2–F5) from the same review. The F1
  fix had been made independently on both diverged repo lines; the reconciliation above
  de-duplicated it rather than shipping two competing implementations.
- **Task register wired end to end.** The 791-task/35-section Humanitarian Mapping Task
  Register now drives the chat send path (matching, prompt enrichment, output-contract
  routing) instead of sitting beside it as reference data — see the `[1.4.4]` entry below for
  the register itself; this release is where dispatch actually runs through it.
- **QGIS 4.x/Qt6 enum-compatibility, generalized.** Replaced the ~15 site-by-site hand-rolled
  fixes with a shared runtime resolver (`agent/tools/_qgis_enum_compat.py`'s
  `resolve_qgis_enum`) that tries the QGIS 4.x scoped form first and falls back to the QGIS
  3.x flat form — applied across `styling_tools.py`, `raster_tools.py`, `task_runner.py`,
  `layout_tools.py`, `export_tools.py`, and `humanitarian_tools.py`. A live QGIS 4.2.2 smoke
  test (below) caught one class this pattern hadn't yet reached.
- **Live-verified critical fix: `QgsColorRampShaderItem` import crash.** Found by running a
  real headless PyQGIS session (QGIS 4.2.2's own Python, not the sandboxed no-QGIS suite,
  after the plugin's GUI proved undriveable in this deployment environment) against a
  purpose-built test dataset: `agent/tools/raster_tools.py`'s top-level import of
  `QgsColorRampShaderItem` raises `ImportError` on real QGIS 4.2.2 — the class moved to
  `QgsColorRampShader.ColorRampItem` — silently setting `QGIS_AVAILABLE = False` for the
  whole file and degrading all 11 raster tools (hillshade, slope, aspect, zonal statistics,
  clip, both classification tools, histogram equalization, mosaic, band composite,
  pan-sharpening) in any real live session. Invisible to the sandboxed suite by construction.
  Fixed with the same dual-form resolution pattern; re-verified live afterward, 14/14 smoke
  test categories passing including two real network calls. See `docs/BUG_TRACKER.md`
  BUG-2026-09-05-1.
- **Live-verified GUI: the print-layout disclaimer footer.** `[1.5.0]`'s dark-theme fix and
  BUG-2026-09-02-6's fabrication-safety footer had both shipped `fixed-unverified-pending-
  live-session`. Directly confirmed this cycle via a real chat-driven `create_print_layout`
  call in a live QGIS 4.2.2 session (Google Gemini (Hosted) provider): the standing
  disclaimer footer renders correctly and legibly in landscape orientation, alongside a real
  graduated-severity legend, scale bar, and north arrow. Portrait orientation's tighter fit
  remains unconfirmed.
- **Auth-system diagnostic.** From a live bug report (`authManager().isDisabled()` on a real
  QGIS 4.2 session): `CredentialManager.auth_system_status()`/
  `get_auth_system_diagnostic_message()` now surface the two real, documented root causes (a
  QGIS 3.40.4+ proxy-authcfg regression, or a missing QCA-OpenSSL backend) and their fixes
  directly in the existing plaintext-fallback warning, instead of an unexplained generic
  message.
- **Humanitarian incident coding.** `add_incident_point`/`add_point_layer` gained optional
  ACLED-style (`event_type`/`sub_event_type`) and IMSMA/IMAS-style (`hazard_type`/
  `contamination_status`) controlled-vocabulary fields alongside the existing freeform
  `severity`/`category` — advisory validation only, an unrecognized value returns a warning
  rather than rejecting the point.
- **Road-snapped delivery routes.** `optimize_delivery_route` accepts an optional
  `road_network_layer`; when given, it chains `native:shortestpathpointtopoint` across the
  computed stop order into a real road-snapped route line instead of leaving callers to draw
  a straight line through stops and present it as a route.
- **Sandbox hardening.** Closed 4 live bypasses of the `execute_pyqgis_script` safety sandbox
  found on re-review.
- **Release packaging.** `.bak`/`.orig`/`.rej` backup files no longer ship in the release ZIP;
  the ZIP's top-level folder name is now pinned rather than derived from the build directory
  (a prior build had shipped under a scratch-directory name, causing QGIS to install it
  alongside the real plugin instead of replacing it — see `docs/BUG_TRACKER.md`
  BUG-2026-08-21-6 lineage).

## [1.5.0] — adaptive self-learning + confirmed QGIS 4.2/Qt6 fixes

- **Adaptive self-learning system.** New `agent/learning.py` layers four
  mechanisms on top of the existing `SpatialMemoryManager` global-note store
  (no new storage plumbing): passive preference detection (scoped to
  connection-provider choice for this first pass, requiring 5+ samples and a
  70%+ dominant share before acting), correction learning (a text heuristic
  over the message right after a tool call — "that's wrong", "undo that",
  etc. — stored as a standing rule), usage-pattern counters (tool/provider
  frequency, surfaced to the model as context, never silently changing a UI
  default), and a new **🎓 Learned Preferences & Rules** row in the Tasks &
  Memory tab (dropdown + **🗑 Forget Selected**) so anything inferred is
  visible and removable. `get_formatted_memory_context()` now buckets global
  notes under labeled headings (Learned Preferences / Correction Rules /
  Usage Patterns / User Global Preferences) instead of one flat list. 17 new
  tests in `tests/test_learning.py`; the `agent.py` wiring and UI addition
  are unverified in a live QGIS session (same structural limitation as every
  other UI/agent-lifecycle change — see `docs/BUG_TRACKER.md` BUG-2026-09-02-5).
- **QGIS 4.2/Qt6 enum-scoping fixes**, discovered via three rounds of live
  crash reports during real QGIS 4.2 testing and shipped under the unchanged
  `1.4.4` version number without a release cut — recorded here retroactively.
  Fixed flat-vs-scoped enum access across `Qt`, `QScrollArea`,
  `QDialogButtonBox`, `QLineEdit`, and `QPalette` (dock panel open,
  scroll-area frames, dialog buttons, password fields, live theme palette
  extraction) — see `docs/BUG_TRACKER.md` BUG-2026-09-02-1 through -3 for the
  full per-symbol breakdown and verification status.
- **Dark-theme chat rendering fix.** `chat_formatting.py`'s `render_markdown()`
  was hardcoded to fixed light-theme colors for code blocks, inline code,
  tables, blockquotes, and `<hr>`, disconnected from the already
  theme-aware bubble colors — confirmed via a live screenshot showing
  near-invisible white-on-white table text in QGIS dark theme. Colors now
  thread through from the same theme-derived dict the chat bubbles already
  use. Two new system-prompt rules (40, 41) address related live feedback:
  default to creating a real map layer for mappable results instead of only
  describing them in chat, and never silently guess a year/date a tool
  parameter left unspecified. See BUG-2026-09-02-4.

## [1.4.4] — sector-guided mapping experience

### Humanitarian Mapping Task Register, wired end to end

The register (791 tasks across 35 sections) now drives the chat send path
instead of sitting beside it.

- **Every task declares what it takes in and what it puts out.** New
  `agent/file_io.py` models the media kinds the plugin can actually ingest --
  picture, PDF, TXT, Word, spreadsheet, vector, raster, QGIS project -- each
  with a real registered tool behind it, and the artifact each output contract
  leaves on disk (`.pdf`/`.png` for a layout, `.html` for a dashboard, `.csv`
  for an analysis, `.gpkg` for an export). Both fields are derived for all 791
  tasks by `tools/derive_task_io.py`; `tests/test_file_io.py` re-runs the
  derivation and fails if the committed register has drifted from it.
- **Attachments join the task.** A file attached in chat is classified, routed
  to the tool that can read it (a 3W spreadsheet to `load_3w_data`, a damage
  photo to `extract_features_from_imagery`, a sitrep to `extract_pdf_tables`),
  and carried into the next message rather than analysed as a side errand.
- **The prompt is shown before it is sent.** A new preview panel (on by
  default, Settings ▸ *Show the prompt and reasoning before sending*) displays
  the literal text that will be sent -- the user turn, plus the addendum added
  to the system prompt -- together with the reasoning: which task matched and
  how confidently, what will be delivered, which values were assumed, and what
  each attached file will be read as. No extra API call; it renders text that
  has already been composed locally.
- **Only genuinely unanswerable gaps interrupt.** Slots QGIS can answer (area
  of interest, from the open project) are answered; slots with a safe default
  are filled and stated in the preview; only hazard type, facility type and
  sector -- where a guess produces confidently wrong humanitarian output --
  stop and ask. That is ~10% of tasks rather than ~89%.
- **The answer is checked against the contract.** New `agent/output_router.py`
  compares the tools that actually ran against what the task promised. A
  dashboard task that ended in prose gets exactly one follow-up turn naming
  the missing renderer; the reason is written into the chat, and if it is still
  not produced the chat says so rather than describing an artifact that does
  not exist.
- Fixed five tasks that asked "which facility or service type?" about a
  statistical distribution (*Map population distribution*, *Map age and sex
  distribution*, and three others) because `distribution` also names a
  distribution point. Real distribution-point tasks keep the slot.
- **The click-through itself is now verified, not just the logic behind it.**
  New `tests/test_chat_widget_live.py` boots a real `QgsApplication`, builds
  the real dock and chat widgets, and drives them with `QTest.mouseClick` on
  the actual buttons -- the requirement panel, the prompt preview, and the
  output-contract follow-up, previously proven correct only at the level of
  pure-logic unit tests and static source inspection. It caught a real bug
  doing it: `_dispatch_message` had a stale `analysis is None` fallback that
  silently re-applied the register's enrichment -- and its output contract --
  after clicking "Send my wording only", the escape hatch for when the
  matched task is simply wrong. Fixed; the button now dispatches the user's
  own wording with no contract attached, as intended.

- Added sector-aware prompt guidance for humanitarian aid, engineering, urban planning, logistics, agriculture, environment, public health, disaster risk, utilities, transport, public safety, research, real estate, and defense/intelligence profiles.
- Priority rollout documented: humanitarian aid, engineering, urban planning, then logistics.
- Verified against the Community and private prompt-refiner suites.


## [1.4.3] — UI terminology and navigation polish

- Standardized the main tabs as **Chat**, **Tasks & Notes**, and **Help & Guide** in both plugin editions.
- Normalized commercial provider labels to Hosted/Local terminology.
- Clarified Settings connection naming and project-notes labels.
- Automated UI regression suites remain green: 691 private tests and 620 Community tests.


All notable changes to Cartogen AI are documented here, newest first. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/).

> **Repo note:** this file's history up through v1.3.0 was carried over verbatim
> from the old `qgis_ai_assistant` repo as part of a from-scratch copy/restructure
> into this new `cartogen-ai` repo — it is **not** a git history migration. Full
> commit history back to v0.2.0 remains available in the old repo
> (`C:\qgis_ai_assistant`) if ever needed.

## [1.4.2] — 2026-08-22

- **`ui/dock_widget.py` class split**, per `docs/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md`. The
  1,355-line `CartogenAiDockWidget` is now the outer dock (signals, header, tab wiring) with
  the Chat, Tasks & Memory, and Help tabs each extracted into their own `QWidget` class
  (`ChatTabWidget`, `TasksTabWidget`, `HelpTabWidget`), plus two small shared-code extractions
  (`dock_constants.py`, `theme.py`) needed to avoid a circular import. Code moved verbatim —
  no logic changes. Verified by constructing the dock offscreen against a real QGIS Python
  environment (`python-qgis-ltr.bat`, `QT_QPA_PLATFORM=offscreen`): all modules import
  cleanly, all 3 tabs are present, and every cross-tab signal connection fires correctly.
  **Not yet verified in a real interactive QGIS session** — run
  `docs/RELEASE_SMOKE_TEST.md` before relying on this in production.
- **Cartogen Cloud Connect Gateway wired in as a selectable provider** (not yet functional —
  no gateway is deployed anywhere). `CartogenClient` is now exported from `agent/providers`,
  registered in `agent.py`'s provider selection, and added to `ui/settings_dialog.py`'s
  provider dropdown (deliberately placed last, not default, until a real gateway exists).
  `providers/cartogen.py` gained a `list_models()` function for the Settings dialog's model
  picker. See `docs/PRO_TIER_BUILD_PLAN_2026-08-21.md` for what's still needed (gateway
  deployment, billing lifecycle, key-retrieval auth) before this tier has real value.
- **Fixed:** `tests/test_export_tools.py`'s `TestGenerateHtmlDashboardConnectivityNote` now
  skips when `folium` is absent instead of failing, matching every other optional-dependency
  guard in the suite.
- Added placeholder `README.md`s to the empty `cartogen-ai-pro/`/`cartogen-ai-enterprise/`
  sibling directories so they no longer read as "the private repo exists."

## [1.4.1] — 2026-08-21

Follow-up fixes after the `[1.4.0]` consolidation, from direct feedback that two problems slipped
through:

- **Living docs still named/linked like leftovers.** `QGIS_AI_Agent_Feature_List.md` and
  `QGIS_AI_Agent_PRD.md` renamed to `CARTOGEN_AI_FEATURE_LIST.md`/`CARTOGEN_AI_PRD.md` and fully
  rebranded. Unlike `CHANGELOG.md`'s past entries, these are living reference docs, not
  historical logs — renaming/translating them isn't a rewrite-history concern.
- **44 broken links.** Every `file:///c:/qgis_ai_assistant/...` absolute link (hardcoded to the
  old machine's path) converted to a relative link.
- Updated every live reference to the renamed files: `agent/scheduler.py`,
  `agent/tools/monitoring_tools.py`, `CLAUDE.md`, `CONTRIBUTING.md`, `plugin_upload.py`'s
  `EXCLUDE_FILES`, `docs/PRODUCT_TIERS.md`, `docs/HUMANITARIAN_GIS_FEATURE_REVIEW.md`,
  `docs/SAM_IMAGERY_EXTRACTION_SPEC.md`.
- Left the genuinely dated/historical docs untouched (this file's own past entries,
  `docs/STATUS_REVIEW_2026-08-20.md`, `docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md`) — they
  describe real past states, not leftover branding, per this project's frozen-doc convention.

**Added [docs/OPEN_CORE_REPO_STRATEGY.md](docs/OPEN_CORE_REPO_STRATEGY.md):** this repo stays the
single public Community codebase. Professional and Enterprise are decided (not yet built) to live
in a separate private repo that one-way-syncs from this one via GitHub Actions, distributed from
the project website with license-key gating. This resolves the licensing tension
`docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` flagged but didn't settle — Community stays
genuinely GPL v2/open in this repo; only the unbuilt Pro/Enterprise-only code would be
proprietary, in the other repo. Added `.github/workflows/sync-to-private.yml` as an inactive
scaffold (needs a real target repo before it can run).

## [1.4.0] — 2026-08-21

**Consolidated the dual-tree architecture into this single repo.** Previously,
`C:\qgis_ai_assistant` maintained two parallel plugin trees — a root source tree
(`CartogenAiCore`/`cartogen_ai_core`, renamed in `[1.3.0]` below) and a separately
distributed `Cartogen AI/cartogen_ai/` copy (`CartogenAi`/`cartogen_ai`) kept in
sync by `build_cartogen_ai.py`, so two QGIS plugin listings could exist side by
side. This repo (`C:\cartogen-ai`) is the single, consolidated result of copying
the root tree over and dropping the now-unnecessary `_core` suffix.

- Renamed: `CartogenAiCore` → `CartogenAi`, `cartogen_ai_core` → `cartogen_ai`,
  `CartogenAiCoreDockWidget`/`CartogenAiCoreSettingsDialog` → `CartogenAiDockWidget`/
  `CartogenAiSettingsDialog`, `cartogen_ai_core.py` → `cartogen_ai.py`
- **Another breaking change**, same caveat as `[1.3.0]`: the QSettings key prefix
  moved again, `cartogen_ai_core/...` → `cartogen_ai/...`
- `build_cartogen_ai.py` retired — no second tree left to sync into
- `plugin_upload.py` simplified for single-tree packaging (`PLUGIN_NAME = "cartogen_ai"`)
- Added Claude Code / GitHub scaffolding: `CLAUDE.md`, `.github/workflows/tests.yml`,
  issue templates, PR template
- The 3 planned editions (Community/Pro/Enterprise — see
  [docs/PRODUCT_TIERS.md](docs/PRODUCT_TIERS.md)) are reflected in documentation
  only; nothing in this codebase is tier-gated yet, per the project's existing
  honest-status convention (see `CONTRIBUTING.md`)
- `service/data/pgdata/` (a live Postgres data directory that had been committed
  to git in the old repo) was **not** carried over — it's runtime state, not
  source, and shouldn't have been tracked in the first place
- 691 tests, same known baseline, verified in this new tree post-copy

