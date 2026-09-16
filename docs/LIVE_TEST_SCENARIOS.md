# Cartogen AI — Live Test Scenarios

**Purpose.** `docs/RELEASE_SMOKE_TEST.md` checks ~16 tools in isolation, one prompt each, before a
release. This document is different: it strings prompts together into the same **multi-turn
workflows** that have actually broken live (2026-09-16 RC4 session) and checks the two things the
plugin exists to do — **visualize data correctly on the map canvas, and produce technically
accurate analysis text** — not just "the tool call didn't error."

**When to run this.** After any change to `agent/task_matcher.py`, `agent/prompt_refiner.py`,
`agent/output_router.py`, `agent/task_manager.py`, or `agent/agent.py`'s tool-calling loop —
the layer this document exercises, not individual tool implementations. Also worth a full run
before promoting any RC to a final release.

**Setup (once).** Same as `RELEASE_SMOKE_TEST.md`'s setup: a QGIS project with a live internet
connection (GDACS/EONET/geocoding are real network calls) and at least one configured provider.
Each scenario below is self-contained — run them in any order, in a fresh chat session or plan.

---

## How to read each scenario

- **Question(s)** — type these into the chat verbatim, in order. A scenario with more than one
  question is testing that state (a plan, a layer, a pending confirmation) carries correctly from
  one turn to the next — the class of bug that a single-prompt smoke test can't see at all.
- **Watch for** — the specific failure mode this scenario exists to catch, named so you know what
  you're looking for before you start.
- **Verify** — check these against what's ACTUALLY on the canvas / in the Activity tab / in the
  raw QGIS Python Console `[Agent] Tool call:` / `[Agent] Tool ... succeeded/FAILED:` lines — never
  against the chat bubble's own prose alone. Every bug this document exists to catch is exactly
  the case where the chat text says one thing and the project state says another.
- **Expected result** — the concrete pass/fail line.

---

## Scenario 1 — Task routing doesn't hijack an off-register phrasing

**Watch for:** the task-matcher (`task_matcher.py`, `CONFIDENT_SCORE=0.34`) silently routing a
plainly-worded request to an unrelated task, injecting the wrong deliverable/tool-order into the
system prompt. Fixed 2026-09-16 (`ce91b6a`) for the below-floor case — this scenario is the live
regression check for that fix.

**Question(s):**
1. `Apply a color ramp to the raster layer.` (with at least one raster layer already on the
   canvas)
2. `Only create the layer, do not add styling yet.` (as a follow-up in the same conversation,
   after asking for something that creates a layer)

**Verify:**
- If prompt-preview is enabled, the "Why this prompt" card (if one appears at all) names a task
  that's actually about raster styling / layer creation — not CSV export, not HDX/3W data, not
  print layouts.
- The raster layer's renderer actually changes (visibly, in the Layers panel's symbol preview) —
  not a chat claim of an unrelated GPKG/CSV export.
- No `⚠️ Note: a tool call... actually returned an error that isn't reflected above` line UNLESS a
  real tool call in that same turn actually failed.

**Expected result:** Both turns produce a response that is topically about what was actually
asked. Any response describing an export, a different layer, or a different deliverable than the
one requested is a FAIL — quote the exact wording used and the response received.

---

## Scenario 2 — A destructive-action confirmation is never silently skipped

**Watch for:** the exact live bug from 2026-09-16 — a user confirms a destructive edit in chat,
and the model narrates success without ever re-calling the tool. Fixed the same day (`ed6c42b`).

**Question(s):**
1. `Calculate a severity index for the point layer using its numeric severity field.` (against a
   layer that does NOT already have a numeric severity field — e.g. a freshly fetched GDACS
   layer, which only has `alert_level` as text)
2. Once the chat shows a `⚠️ Destructive Action Safety Gate` message proposing a
   `field_calculator` expression: reply exactly `Confirm`.

**Verify:**
- **Before** replying "Confirm": open the Activity tab, confirm a task is `PREVIEW_READY` with a
  real rationale and code snippet — not silently attached to an unrelated already-`DONE` task.
- **After** replying "Confirm": open the layer's attribute table and confirm the new field
  actually exists with real computed values — do not trust the chat's own "Confirmed & Executed"
  text alone.
- The QGIS Python Console should show **zero** `[Agent] Calling agent.run()` lines between your
  "Confirm" message and the result — a chat-typed confirm must resolve directly, not through a
  new LLM turn (see `chat_tab_widget.py`'s `_resolve_pending_confirmation`).
- Repeat once more, but reply `cancel` instead — verify the field is NOT added, and the task shows
  `FAILED` / "Cancelled by User" in the Activity tab.

**Expected result:** The attribute table's actual contents match what the chat claims, every
time, for both the confirm and the cancel path. A mismatch (chat says done, field doesn't exist)
is a FAIL and is the single highest-severity failure mode this document checks for.

---

## Scenario 3 — Map visualization is the actual deliverable, not a description of one

**Watch for:** the model describing styled layers in prose without the styling tool actually
having run — the general shape of the output-contract gap `output_router.py` exists to close.

**Question(s):**
1. `Health facilities beyond one hour's travel [pick real coordinates in your project's region].`
2. `Buffer the point layer by 500 meters.`
3. `Style the buffer layer with 50% transparency and put it under the point layer.`

**Verify:**
- After turn 1: a new point layer exists on the canvas with **visibly distinct symbols** for
  "within" vs "beyond" the threshold (not one uniform default marker) — check the Layers panel's
  legend, not just the chat's "categorized styling applied" claim.
- After turn 2: a new polygon buffer layer exists with the correct radius — right-click →
  Properties → check the actual geometry, or eyeball the buffer distance against the map scale
  bar.
- After turn 3: the buffer layer's actual rendered opacity is visibly ~50% on the canvas, and its
  position in the Layers panel is below the point layer, not above it.

**Expected result:** Every claim made in the chat text about the map's visual state is checkable
and true against the actual canvas. Any layer described as styled/positioned a certain way that
isn't is a FAIL.

---

## Scenario 4 — External API data doesn't silently vanish into a field-width limit

**Watch for:** the 2026-09-16 GDACS `country` field-length bug (`96fd84b`) — any external-API
string attribute wider than a memory layer's declared field width used to be silently dropped,
not stored, with no error surfaced anywhere.

**Question(s):**
1. `Fetch current disaster alerts worldwide and add them to the map.` (deliberately global, not
   scoped to one country — regional GDACS events with multi-country `country` strings are more
   likely to appear in a worldwide fetch)

**Verify:**
- Open the new layer's attribute table, sort by the `country` column, and check for any row
  where `country` is empty/`NULL` despite the event clearly being real (cross-check a couple of
  event names against gdacs.org directly).
- No Qt "Could not store attribute" message appears in the QGIS message bar or Python Console.

**Expected result:** Every fetched alert's `country` field is populated (possibly truncated at a
generous width, never silently blank). A blank `country` on an otherwise-valid alert is a FAIL.

---

## Scenario 5 — Technical analysis text is accurate, not just fluent

**Watch for:** confident, well-formatted prose that states numbers/units/CRS that don't match
what the tools actually returned — the fabrication class `_reconcile_final_text_with_tool_log`
only partially covers (unacknowledged tool errors, not invented-but-plausible numbers).

**Question(s):**
1. `Calculate the total area of the buffer layer and summarize it in square kilometers.`

**Verify:**
- Cross-check the stated area against QGIS's own Field Calculator (`$area` on the buffer layer,
  converted to km²) or the Vector → Geometry Tools → "Add Geometry Attributes" result — a
  from-scratch, independent number.
- Confirm the CRS named in the response (e.g. "EPSG:32638 (UTM 38N)") matches the buffer layer's
  ACTUAL CRS shown in the Layers panel, not just an assumed/typical one for the region.

**Expected result:** The stated area is within reasonable rounding of the independently computed
one, and every technical detail (CRS, units, feature count) matches project reality. A
confidently-stated wrong number is a FAIL, more serious than a hedge/refusal would have been.

---

## After running this

Log results the same way `RELEASE_SMOKE_TEST.md` does: append a dated entry to that file's
**Run log** section noting which of these 5 scenarios passed/failed and against which build —
don't duplicate a second run-log here. If a scenario fails, capture the exact chat transcript AND
the actual QGIS Python Console `[Agent] Tool call:`/`succeeded`/`FAILED` lines for that turn —
every real bug fixed on 2026-09-16 was found from that raw log, not from the chat UI's own
summary text.
