# UX & Documentation Audit — 2026-08-31

Scope: the shipped Cartogen AI Community plugin (v1.4.4) as it actually behaves and reads
today — not the roadmap. Every finding below was verified by reading the real source or
running a grep against it; line numbers are approximate and will drift as the file changes,
but the described behavior was confirmed, not inferred from names or comments alone.

Severity key: **P0** — silent wrong behavior or a broken first-run path; **P1** —
discoverability/onboarding gap a real user will hit; **P2** — documentation accuracy/staleness;
**P3** — UI polish/consistency/accessibility; **P4** — housekeeping.

---

## P0 — Silent failures

### 1. The preview panel's "Send this" button can silently send stale text
`chat_tab_widget.py`: `input_edit` (the message box, lines ~221–224) is never disabled or
read-only while `preview_panel` is visible. `preview_send_btn` → `_send_previewed_prompt()`
(lines 459–464) sends `self._pending_analysis_text`, not `self.input_edit.toPlainText()`. So:
type a request, the preview panel opens, you notice a wording issue and edit the box
underneath the panel, then click **Send this** — your edit is discarded and the *original*
text is sent, with no warning. (One path is safe: pressing Enter or clicking the main **➤**
button re-runs `send_message()`, which correctly cancels the stale preview and re-analyzes the
new text — lines 360–365. The bug is specifically the preview panel's own **Send this**/**Send
my wording only** buttons, which never look at the input box again.) This is structurally the
same class of defect as the "Send my wording only" enrichment bug fixed this session — an
escape hatch that looks like it did what the user asked and quietly didn't.
**Fix:** disable/gray `input_edit` while any gate panel (`preview_panel`, `requirement_panel`,
`refinement_panel`) is visible, or make each panel re-derive its text from the live box instead
of a snapshot.

### 2. A brand-new user's first message throws a raw HTTP error, not the documented friendly message
`_dispatch_message` (`chat_tab_widget.py`, ~line 569) never checks whether the active
provider actually has a key before scheduling the request. With no key configured, the
provider client sends `Authorization: Bearer None`, gets a 401, and `task_runner.py`
(`run()`/`finished()`, lines 56–77) catches it generically and surfaces `str(self.error)`
verbatim — so the very first thing a new user who hasn't opened Settings yet sees is something
like `**Error:** 401 Client Error: Unauthorized for url: ...`, with no mention of Settings.
`docs/USER_GUIDE.md` (line ~240) already documents the intended behavior — *"No API key
configured" — open Settings and add a key* — and that exact friendly string already exists in
the codebase (`chat_tab_widget.py:839`), but only on the file-attachment analysis path, not the
main chat send path. The guide describes behavior the main path doesn't have.
**Fix:** add the same no-key guard to `_dispatch_message` before scheduling the task.

### 3. All provider/network errors reach the user as raw exception text
`on_complete` (`chat_tab_widget.py:642`): `f"**Error:** {err}"`, where `err` is `str(exception)`
from `task_runner.py`. No classification for bad key vs. rate limit vs. network timeout vs.
retired model, and no suggested next step. With five interchangeable providers and routine
key/quota issues, this is probably the single most common real-world confusion point.
**Fix:** classify the common cases (401/403 → check your key in Settings; 429 → rate-limited,
try again shortly; connection error → check your network or Ollama's local server) and only
fall back to the raw string for the unclassified remainder.

---

## P1 — Onboarding & discoverability

### 4. The welcome message never tells a new user to configure a provider first
`chat_tab_widget.py` (~lines 268–274) — the first-run greeting is pure feature marketing
("I plan multi-step spatial tasks...") and never mentions Settings or an API key, so a new user
is invited to type a request that (per #2) will fail confusingly.
**Fix:** one added line — *"First time? Click ⚙ Settings to pick a provider and add an API
key."* — or better, detect the no-key state and lead with that instead of the feature pitch.

### 5. Two of the three gate panels have no title identifying what they are
`refinement_panel = QGroupBox()` (line 120) and `requirement_panel = QGroupBox()` (line 168)
are built with no title string — they appear as a bare bordered box with body text only. Only
`preview_panel = QGroupBox("Prompt that will be sent")` (line 189) is labeled. A first-time
user has no heading telling them what kind of interruption just appeared or why.
**Fix:** give each a title — e.g. "This needs one more detail" for the requirement panel,
"Suggested rewordings" for the refinement panel.

### 6. Settings gives no guidance on what an API key is or where to get one
`settings_dialog.py` (~181–188): the key-entry field has no placeholder text, tooltip, or
"Get a key →" link, for any of the five providers. A humanitarian GIS analyst who has never
used an LLM API has no in-app way to learn what to paste there or where it comes from.
**Fix:** per-provider placeholder text and a link (openrouter.ai/keys, Google AI Studio,
platform.openai.com, console.anthropic.com; Ollama's local-endpoint format instead of a key).

### 7. The in-app Help tab doesn't mention the newest — and most safety-relevant — features
`help_tab_widget.py` (60 lines, static HTML) has zero mention of the prompt preview panel, the
"Send my wording only" escape hatch, the requirement/slot gate, output-contract enforcement, or
attachment-to-tool routing — all shipped in 1.4.3/1.4.4. `docs/USER_GUIDE.md` (lines ~10–11)
explicitly claims the Help tab is *"built from the same data as this guide so it can't drift
out of sync"* — true for the provider list and example prompts (both pull from
`dock_constants.py`), false for everything else. A user working inside QGIS, not GitHub, has no
way to learn why some requests stop to ask a question or show a preview.
**Fix:** either genuinely generate the relevant Help sections from the same source the guide
describes, or add the missing sections by hand and drop the "can't drift" claim for the rest.

### 8. No troubleshooting content is reachable from inside the app
`docs/USER_GUIDE.md` (lines ~238–263) has a solid troubleshooting section — bad key, provider
failure, tool-call limit, wrong-looking output, CSV coordinate issues — but the Help tab has no
troubleshooting section and no link to the guide at all. A user hitting an error mid-session has
no in-app path to an answer.
**Fix:** add a short troubleshooting section to the Help tab, or at minimum a clickable link to
`docs/USER_GUIDE.md`.

### 9. No humanitarian-sector orientation anywhere in the app
The plugin's task register is explicitly sector-guided for humanitarian aid (DG ECHO is the
stated primary use case), but `grep -i "humanitarian|ECHO|sector"` across every UI file returns
only one code comment and one Settings tooltip fragment. All sector framing lives in
`docs/HUMANITARIAN_GIS_FEATURE_REVIEW.md` and `CHANGELOG.md`, invisible from inside the app. A
first-time humanitarian analyst gets no signal that this is more than a generic GIS chatbot.
**Fix:** lower priority than 4–8, but worth a line in the welcome message or Help tab pointing
at the sector-specific task register.

---

## P2 — Documentation accuracy & staleness

### 10. README.md is two versions behind and silent on the newest major feature
`README.md:22` says *"Version 1.4.2"*; `metadata.txt` says `1.4.4`. The "What it does" section
never mentions the prompt preview, requirement gate, output-contract enforcement, or attachment
routing shipped in 1.4.3/1.4.4 — the most significant recent change to how the plugin actually
behaves.

### 11. DOCUMENTATION.md — the "consolidated reference" — is stamped v1.4.1 and doesn't mention any of it either
77KB, billed as the single consolidated reference for the whole project; header says *"Version:
1.4.1"*, and a grep for `prompt preview|slot gat|output contract|task register` returns zero
hits. `docs/USER_GUIDE.md` (mtime newer than the rest) is the one doc that *does* correctly and
fully describe this feature set — so the fix is bringing README/DOCUMENTATION.md in line with
USER_GUIDE.md, not writing new content from scratch.

### 12. The doc README calls "start here for what's open right now" is itself stale
`docs/IMPLEMENTATION_TRACKER.md:3` — *"Last updated: 2026-08-21, against v1.4.1"* — predates
both the 1.4.3 and 1.4.4 releases and doesn't mention either. This undercuts the tracker's own
stated purpose and its own stated rule that a lagging tracker defeats the point of having one.

### 13. Three different tool counts float around the repo at once
125 (`docs/PRODUCT_TIERS.md`, stamped 2026-08-15), 131 (current — matches
`docs/TOOLS_REFERENCE.md`'s auto-generated count), 134 (`docs/TIER_RESTRUCTURE_PROPOSAL...md`,
already self-acknowledged stale elsewhere). A reader who lands on the wrong file first has no
way to know which number is current.

### 14. No per-provider "where do I get a key" links in any doc
Neither README.md nor `docs/USER_GUIDE.md` links to openrouter.ai/keys, Google AI Studio,
platform.openai.com, or console.anthropic.com — matches finding #6's in-app gap; this is the
same gap in the written docs.

### 15. CHANGELOG.md is one undifferentiated 166KB file
No per-release notes a user upgrading from, say, 1.4.2 could skim — they have to search a
single giant file for what changed.

---

## P3 — UI polish, consistency, accessibility

### 16. Send isn't blocked while the (optional) prompt-refinement network call is in flight
`_start_refinement` (`chat_tab_widget.py:490–509`) fires a background thread and returns
without disabling `send_btn` (only `_dispatch_message`, further downstream, does that). A
second Enter/click during that window can start a second `refine()` call; whichever response
lands last silently overwrites `_pending_refinement_text` and can show cards for the wrong
prompt. `stop_btn` also isn't enabled during this window, so there's no way to cancel a hung
refinement call.

### 17. Two of three primary input-row buttons have no tooltip
`attach_btn` ("📎") and `send_btn` ("➤") have no `setToolTip`; `stop_btn` does ("Stop the
current request", line 234). A keyboard/screen-reader user gets no accessible label for
attach or send.

### 18. The disabled "Proceed with stated defaults" button gives no reason it's disabled
`requirement_continue_btn.setEnabled(not analysis.get("blocking"))` (line 419) has no
accompanying tooltip — a user sees a grayed button with no stated explanation, even though the
surrounding code comment (416–418) has the explanation right there in the source.

### 19. Inconsistent accept/edit/cancel vocabulary across the three gate panels, and a reused "success" color across two different meanings
Preview: "Send this" / "Send my wording only" / "Cancel". Requirement: "Proceed with stated
defaults" / "Edit request". Refinement: "Use this" / "Edit first" / "Send as typed instead" —
three different verb sets for the same underlying accept/edit/decline choice. Separately,
`preview_send_btn` uses the `successButton` style (green, line 202) — the same styling
`tasks_tab_widget.py` uses for the destructive-action gate "✅ Confirm & Apply Edit" (lines
~112–115) — so the same color now means both "send a low-stakes composed prompt" and "apply an
edit/delete," which weakens a color the rest of the design otherwise reserves for destructive
confirmation.

---

## P4 — Housekeeping

### 20. docs/ sprawl
~20 dated one-off review/spec/proposal docs (`ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md`,
`STATUS_REVIEW_2026-08-20.md`, `TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`,
`SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md`, `PROMPT_REFINEMENT_LAYER_SPEC.md`, and others) sit
flat alongside living docs (`IMPLEMENTATION_TRACKER.md`, `BUG_TRACKER.md`, `USER_GUIDE.md`,
`TOOLS_REFERENCE.md`). README's own doc table labels each one, which helps a reader who starts
at README — but anyone browsing `docs/` directly on GitHub gets no such signal.
**Fix:** a `docs/archive/` or `docs/proposals/` subfolder for the dated/roadmap docs, living
docs staying at the top level. (This audit's own file is a candidate for that same treatment
once it's been acted on.)

### 21. Two near-empty orphaned root files
`QGIS_AI_Agent_Feature_List.md` (337B) and `QGIS_AI_Agent_PRD.md` (328B) are self-described
"moved" stubs, not git-tracked, explicitly noted as safe to delete — still sitting in the
working tree.

### 22. Minor doc/code name mismatch
`docs/USER_GUIDE.md:9` calls the second tab "Tasks & Memory"; the actual tab title
(`dock_widget.py:116`) is "📋 Tasks & Notes".

---

## Suggested order of attack

1. **P0 items 1–3** — these are the ones that make the plugin behave differently from what it
   claims to do, for the most common real scenarios (first message with no key; any provider
   error; editing a previewed prompt). Fix before the next release.
2. **P1 items 4, 6, 7** — onboarding and Help-tab parity are the cheapest, highest-leverage
   documentation-adjacent fixes: a few lines of copy and two `setToolTip`/placeholder calls
   close most of the first-run confusion.
3. **P2 items 10–12** — a version-number and feature-list pass across README/DOCUMENTATION.md/
   IMPLEMENTATION_TRACKER.md. Mechanical, but currently actively misleading for anyone who reads
   those three files instead of USER_GUIDE.md.
4. **P3/P4** — polish once the above is settled; none of these are silent-failure or first-run
   risks, just consistency and housekeeping debt.
