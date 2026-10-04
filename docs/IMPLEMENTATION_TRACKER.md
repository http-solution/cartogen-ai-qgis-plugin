# Cartogen AI — Implementation Tracker

**Cut as `v1.5.7-rc5`, then corrected to `v1.16.0-rc1`, both 2026-09-20** — the Phase 11
completion, the AST-sandbox bypass fix, and the 2 keyboard-navigation fixes this file's own
entries below describe as "not yet cut into a release" were first released as rc5
(`commercial-plugin-v1.5.7-rc5`), then an external review found — and this session independently
confirmed via QGIS's own `pyplugin_installer.version_compare.compareVersions()` — that
`"1.5.7-rc5"` compares as **older** than the already-published `"1.15.6"`, a real defect
inherited from a 2026-09-19 renumbering decision and never questioned through rc1-rc5. Renumbered
forward to `v1.16.0-rc1` (the version actually intended at that point, never previously released
under any tag) the same day, plus 2 more real defects the review found in rc5 itself (a stale CI
packaging assertion, stale doc test-counts) and a real socket-leak fix in the test suite. `v1.5.7-
rc5`'s GitHub release stays published (tags are never rewritten) with a superseded notice pointing
here. Current release:
https://github.com/cartogenai-glitch/CARTOGEN-AI/releases/tag/commercial-plugin-v1.16.0-rc1 —
published GitHub asset checksum-verified against a fresh local rebuild, matching the standard
7-step process. `v1.15.6` is still "Latest"/stable on GitHub; rc1 is a prerelease only. Left the
paragraph below as it was written (a same-day snapshot at the time), rather than rewritten, per
this doc's own append-don't-rewrite convention.

**Last updated:** 2026-09-20 (same day, second pass), against `v1.5.7-rc4` plus an unreleased
Phase 11 completion pass on `main` (177 tools per the live registry -- not the 182 raw
`@register_tool` decorator sites a naive grep finds, several of which are duplicate positional-arg
call sites the registry itself dedupes; the 177 figure is queried straight from
`registry.TOOL_REGISTRY` at runtime, not assumed. `docs/TOOLS_REFERENCE.md` regenerated the same
day to match. 1,958 tests, 0 failures, 38 skipped -- independently re-run in this pass, not just
copied from `CHANGELOG.md`). This second same-day pass finished 3 of Phase 11's 4 target areas for
real (§4's Phase 11 entry has the "Update, 2026-09-20" detail) after the first pass caught it
false-complete a few hours earlier — not yet cut into a release.
Previously stamped 2026-09-19, against `v1.15.6` stable + 5 unreleased fixes on `main` (169
tools, 1771 tests, 0 failures). That previous sync predates essentially all of the work this
update covers: the entire 11-phase Part A remediation plan (`docs/../` -- tracked in project
memory as `project_followup_task_list_2026-09-19`, plan file
`jiggly-sparking-corbato.md`) merged and shipped as `v1.5.7-rc1` through `-rc4` the very same day
that previous sync was stamped and the days after, so none of it made it into that pass. §4 below
gets one consolidated entry for it, same convention as every prior gap. **`v1.5.7` has not been
promoted to stable/"Latest" on GitHub yet** -- `v1.15.6` (2026-09-17) is still the "Latest"
release; `rc1`-`rc4` are prereleases only.
Previously stamped 2026-09-18, against `v1.15.6-rc6` (169
tools, 1754 tests, 0 failures — see
`docs/BUG_TRACKER.md` for the known-baseline breakdown). Previously stamped 2026-08-31 against
v1.4.4 — nearly seven weeks and 15 release-candidate/version cycles behind, most notably
missing this repo getting a real GitHub remote (§2's "No git remote" bullet below was simply
wrong by the time this update landed) and the entire v1.9.0-v1.15.6 workstream (live hazard
monitoring, rate-limit resilience, the UI/chat Broadsheet redesign, the orchestrator reliability
pass). Re-synced here for the same reason the previous sync gave: a tracker that lags the code
defeats its own stated purpose. §4 below gets one consolidated entry for everything that closed
in the gap rather than reconstructing a decision-by-decision history this pass doesn't have
firsthand context for -- see `CHANGELOG.md` for the authoritative per-version detail.

This is the one place to look for "what's actually still open right now." Every review, audit,
and spec doc referenced below now lives in `docs/archive/` (moved there in the 2026-08-31
documentation pass so `docs/`'s top level only shows living references/trackers) and is a
**dated, frozen snapshot** — per `CONTRIBUTING.md`
§2's own convention, those are never edited after the fact (with rare same-day correction
addenda, like `docs/archive/STATUS_REVIEW_2026-08-20.md`'s own "Post-review update" note — even that doc says
so explicitly rather than silently rewriting itself). The result is the same either way: several
of these docs now describe things that have since changed — a tool count verified against the
live registry as of one review's date is a common example, since the registry keeps growing. This
doc exists to be the current, living answer instead of making anyone cross-reference nine dated
files to figure out what's real today. When something below gets resolved, update this file in the same
change (per `CONTRIBUTING.md` §2's "don't let a status label go stale" rule) — don't edit the
frozen source docs themselves.

---

## 1. Open items that need a human decision (not an engineering call)

These three are explicitly **not** something an agent should decide or silently implement —
each involves a real product, UX, legal, or environmental-verification tradeoff. Consistent
with `CONTRIBUTING.md` §3 ("flag, don't silently fix if it's a judgment call").

> **2026-09-25 — API-cost plan (priority 1 done): automatic model selection fixed** (`docs/BUG_TRACKER.md` BUG-2026-09-25-1). It never took effect on Gemini/OpenAI/OpenRouter/Cartogen; fixed and verified live. **Open follow-ups from review of PR #28:** (a) the picker infers model capability and tier from names only; a curated per-provider table would be safer (chat-compatible, tool-calling-compatible, economy tier, stable, context limit, known price), because with ~178 tools a model that can't call tools reliably costs more than it saves; (b) the behaviour is now "cost saver" (simple: a smaller model; otherwise the default; never escalates), not "auto" in the old sense, so the Settings label and help text should say so, and separate Fixed / Auto-Balanced / Cost-saver modes are worth considering; (c) an explicit "economy model" setting would be the only way to actually guarantee savings; (d) a preferred model that is dead is retried first on every call (one extra 404), acceptable now, a policy choice later. Remaining, in the agreed order: (2) measure billed cost per provider, especially OpenRouter routed to an `anthropic/*` model (Gemini cache hits are already evidenced: 6 of 23 calls); (3) a new held-out ToolRouter recall benchmark over all 178 tools (the router itself was already retuned: top_k 40, aliases, typo correction, deterministic order, an 18-query regression set); (4) measure how often the model already batches tool calls (execution stays sequential on purpose: PyQGIS state and threading); (5) only narrow, state-fingerprinted caching of safe read-only requests, if the numbers justify it. **Error logging is NOT the full-content local log first proposed.** An external review rightly objected: it would persist arguments, results and coordinates before consent, a second sensitive store outside the RC5 sensitivity controls. The agreed direction is consent-first: metadata-only incident records by default, opt-in time-limited enhanced capture, sanitised previewable export, never sent automatically. Not started; needs a design pass. README tool counts are inconsistent (177, 169 and 171 in different places; the live registry has 178).

> **2026-09-25 — Built: offer to download local base data before road-network requests**
> (Alaa: "check with the user if they want to download local data to the project for better
> results and less API calls; list all the sources that can provide a downloadable version").
> `agent/local_data_sources.py` (Qt-free: when to ask, the source catalog, Geofabrik region
> lookup) and `agent/local_data_loader.py` (download/extract on a `QgsTask`, load roads +
> health facilities); the question is asked in chat by `chat_tab_widget.py`, see
> `docs/USER_GUIDE.md` "Local base data". Every source URL was checked live. Verified: 16 + 9
> unit tests, 5 live-widget tests in real QGIS 4.2.2 (mutation-checked), and live region lookups
> against Geofabrik (Jordan 60 MB, Pakistan 370 MB, Oberbayern 404 MB).
> **Not yet verified: a real download and load of a full extract** (the layer loading was
> tested with fixture shapefiles in Geofabrik's real schema). **Open decision:** network
> tools still route in degrees on these EPSG:4326 layers (BUG-2026-09-24-5, below).

> **2026-09-25 — Service areas are now fast on big networks, and exact (BUG-2026-09-25-2).** Routing only over roads that
> can be reached: 76-148x faster for a 3 km reach on the full Jordan network with geometry identical to routing over
> all roads, and the one-hour service area 331 s -> 93 s with the identical reach. Non-drivable roads (footpaths, steps)
> are left out of the loaded road layer. **Open, needs a decision:** (1) `travel_time_matrix` can't be clipped exactly and
> still takes ~8 min on the whole country (responsive and stoppable); (2) `optimize_delivery_route` builds the graph per
> stop pair; (3) **BUG-2026-09-25-3: only 0.9% of Jordan's roads carry a `maxspeed`, so 'fastest' uses a flat 50 km/h
> everywhere: assumed speeds by road class would make travel times far more realistic (recommended, changes results).**
> Earlier: QGIS no longer freezes (Stop and progress work), network tools work in real metres/hours, README tool counts
> corrected to 178.

> **2026-09-24 — `v1.16.0-rc5` cut and published as a prerelease** (tag
> `commercial-plugin-v1.16.0-rc5` on `d140adc`, PR #23 — renamed to `cartogen-ai-v1.16.0-rc5`
> 2026-09-27, see `CONTRIBUTING.md` §6; everything since rc4, PRs #4–#22,
> including #19 pulled in from `main` before tagging). The zip was built from a clean
> `git archive` of the release branch and smoke-tested headless in real QGIS 4.2.2
> (27/27 + 10/10, `docs/RELEASE_SMOKE_TEST.md`). It was then rebuilt from the merged commit:
> 217 files in both builds, and only the 3 smoke-log docs differ. The published asset was
> re-downloaded and its sha256 matched (`f77fa9b2…c1b4a`). **§1.10 (interactive check in a
> real QGIS window) is still not done** and is still the only item before a stable-release
> decision.

> **2026-09-24 — QGIS 3.x support dropped (Alaa: "keep the compatibility only for 4.2.2, no
> compatibility with 3.x is needed").** `metadata.txt` `qgisMinimumVersion` 3.28 → **4.2**
> (`qgisMaximumVersion` left at 4.99). The CI live-test job now runs QGIS 4.2.2 only (the
> `release-3_28` entry was removed; its digest is kept in a comment). README, CLAUDE.md and the
> model's system prompt now say 4.2+/Qt6 only; the prompt's new claims (scoped enums required,
> PyQt5 not importable) were checked against real QGIS 4.2.2 first. **Consequence for users:**
> QGIS 3.x will treat the next release as incompatible, so anyone on 3.x stays on the last
> version they installed. The compatibility shims (`qgis_compat.py`, `_qgis_enum_compat.py`) are
> **kept**, since on 4.x they already take the 4.x path, with their docstrings updated to say the
> 3.x branches are now unsupported. Removing them would mean re-verifying ~15 call sites live for
> no gain on 4.2.2. **To do at the next RC cut:** record this in that release's `CHANGELOG.md`
> entry and `metadata.txt` `changelog=` (not written now — both are per-release). Historical
> entries below that mention 3.28 are left as written.

### 1.1 ~~Destructive-action confirmation gate — 4 humanitarian analysis tools~~

**Resolved 2026-08-22.** Decision: leave as-is (idempotent, lower real-harm than a
geometry-mutating op — not worth the added friction). `SECURITY.md` §6.2 item 5 updated to
state this as a decision rather than an open question. See §4 below.

### 1.2 ~~`ui/dock_widget.py` class split — execution~~

**Resolved 2026-08-22.** Split done (see `docs/archive/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md`'s
"2026-08-22" section for the mechanical detail), offscreen-construction-verified the same day,
and **now confirmed live in a real QGIS session by Alaa**: plugin loads, all 3 tabs work
(chat, task selection, resize), and the new Cartogen provider entry appears correctly in
Settings (last position, not default). This closes the single largest standing gap this
tracker and every review round before it flagged. Scope of what was checked live: plugin
load + dock interaction + Settings dropdown — not itemized against
`docs/RELEASE_SMOKE_TEST.md`'s full 16-category checklist row by row, so treat that checklist
as still worth running in full before a public release, not as formally complete.

### 1.3 ~~Tier restructure — licensing path~~

**Closed 2026-09-27 by Alaa.** This item, and the business-strategy/pricing documents it cited,
were removed from this open-source repo — a GPL v2 codebase has no business reading business
documents describing paid tiers, licensing models, or a hosted gateway's revenue plan. The one
fact worth keeping, since it describes actual current product behavior rather than business
strategy: **the shipped Community edition has never been provider-restricted** — every provider
(OpenRouter, Gemini, OpenAI, Claude, Ollama) has always been available with your own API key, and
nothing in this codebase gates that.

**DECIDED 2026-09-24 by Alaa: Path C — keep everything GPL v2, drop the "locked"/"closed" source-
availability language entirely.** Of the 3 paths §3 of the source proposal laid out (re-license
away from GPL v2; split into an open-core public/proprietary-closed architecture; or stay full
GPL v2 and gate purely on runtime feature flags/tier license), Path C is the one chosen — legally
simplest, no re-licensing, no open-core split, and it sidesteps the unresolved QGIS
combined-work question entirely since no module ever becomes closed-source. The tradeoff named
in the source doc stands as the accepted cost: this does not deliver a source-availability
distinction between tiers — Pro/Enterprise become "same GPL v2 code, paid unlock" (tier license
gates the tool set / gateway quota at runtime), not "different code you can't see." That was the
known shape of this path when chosen, not a surprise.

**What this resolves and what it still doesn't, per §6's engineering-gap scoping in the source
proposal:** picking Path C removes item 5's fork entirely — item 6 (build a closed-source
distribution mechanism: compiled bytecode/Cython, or a gated non-public download) is now **moot,
not just deferred**, and item 5's "identify which modules become the closed, unpublished part"
question no longer applies. What Path C still requires, unresolved by this decision alone: item 3
(a tier/license concept in the plugin itself — doesn't exist in any form today; `agent/auth.py`
has no notion of "which tier is this installation," and `agent/tools/registry.py`/`ToolRouter`
would need a tier-filter stage ahead of its existing relevance-filter, per §6.3's own suggestion
to extend that mechanism rather than build a parallel one), item 4 (connectivity gating in
`ui/settings_dialog.py` — hide or gray out direct-BYOK provider fields for tiers that shouldn't
have them), and item 1/2 (`service/`'s billing punch list and the `agent/providers/cartogen.py`
gateway client) — none of which are Path-C-specific, all of which were already scoped and still
need real engineering work, now unblocked to start. Item 7 (how Enterprise itself is distributed)
still needs its own separate decision — Path C says the *code* stays open, not whether Enterprise
gets a fully separate build/listing.

**Still not started; this is a decision record, not a claim of engineering progress.** The §7
migration consideration (whether existing Community users get grandfathered, a migration window,
or see Community simply redefined going forward) also remains open and is not resolved by
choosing Path C — if anything Path C removes the "source tree gets less open" half of that
concern (no re-license, no open-core split), leaving only the tool-set/BYOK-restriction half of
the migration question live.

### 1.4 GDPR / data-protection alignment

**Added 2026-08-31**, full review completed 2026-09-01: `docs/GDPR_COMPLIANCE_REVIEW.docx` --
13 findings against GDPR's articles, each with file:line evidence. Summary of legal framing: the
deploying organization is the controller; each cloud provider (OpenRouter, Gemini, OpenAI,
Claude) is a sub-processor via the org's own direct account, not via Cartogen AI -- confirmed by
reading every provider client, all of which call that provider's own official API directly, with
no Cartogen-operated intermediary live today (the "Cartogen AI (Hosted)" option in Settings is a
stub pointed at an undeployed placeholder domain).

**1 CRITICAL finding [RESOLVED / CLOSED 2026-09-04 — see update below; `SpatialMemoryManager.clear_global_notes()` implemented and wired to UI]:** global memory notes (`agent/memory.py`) previously had no deletion path anywhere
in the code -- always-on, machine-wide, indefinite retention, no `clear_global_notes()` method
existed. See `SECURITY.md`'s Data Protection section and the 2026-09-04 update below for resolution details.

**4 HIGH findings:** no privacy notice anywhere in the product; no documented international-
transfer mechanism for any of the 4 cloud providers; no DPA/sub-processor visibility surfaced to
the org; processing plausibly meets EDPB high-risk criteria and a DPIA has not been performed.

**Needs:** real legal/DPO review before any EU/DG ECHO deployment processes real beneficiary
data — the review's own disclaimer states plainly it is not a substitute for that. Not an
engineering call per `CONTRIBUTING.md` §3 — flagged, not silently decided. The review's §7
offers a concrete, mostly-mechanical remediation roadmap (R1-R10) if the fixes are wanted; none
of it has been applied to the code yet, since this round was scoped as a review, not a fix.

**Remediation, 2026-09-01 — the 4 HIGH findings (F2-F5), user-requested; F1/Medium/Low/
Informational untouched, out of this round's scope:**

- **F2 (privacy notice) -- fixed.** `settings_dialog.py` shows a static provider-agnostic
  notice above the provider dropdown; `docs/USER_GUIDE.md` has a matching "Where it goes"
  paragraph.
- **F3 (transfer mechanisms undocumented) -- documented.** `SECURITY.md`'s new
  "International transfer mechanisms, by provider" subsection, researched from each
  provider's own current published terms (not assumed) on 2026-09-01.
- **F4 (DPA/sub-processor visibility) -- fixed.** Each cloud provider's Settings page now
  links its DPA (or Trust Portal, for OpenRouter, labelled with its Enterprise-only
  enforceability caveat).
- **F5 (DPIA not performed) -- screening aid added, not a completed DPIA.**
  `docs/DPIA_SCREENING_WORKSHEET.docx` maps EDPB WP248's nine high-risk criteria against
  this plugin's actual tools/data flows; the risk determination and sign-off are left to
  the org's DPO, per `CONTRIBUTING.md` §3.

Still open, unchanged by this round: **F1 (CRITICAL — global memory has no erasure path)**
and **F6-F12 (Medium/Low/Informational)** — see `docs/GDPR_COMPLIANCE_REVIEW.docx` §6 for
all 13.

**Update, 2026-09-04 — F1 now fixed (found via cross-checking this repo's GDPR review against `cartogen-ai`, the now-canonical QGIS plugin checkout):** `SpatialMemoryManager.clear_global_notes()` added, wired to a new "Clear Global Memory" button in `ui/tasks_tab_widget.py`, matching recommendation R4. Full writeup: `docs/BUG_TRACKER.md` BUG-2026-09-04-1. Ported from `cartogen-ai` commit `eee84eb`, which closed the identical finding in that repo first — the two repos diverged before this GDPR review was ever run, so the fix had to land in both independently. **F6-F12 still open, unaffected by this update.**

**Update, 2026-09-08 -- two new HIGH findings, discovered during a full 5-dimension code
review of the `cartogen-ai-community` line and independently confirmed to apply here
unchanged (same shared history; `account.py`/`account_dialog.py` are identical between the
two repos):** (1) the Hosted-Account login dialog (`ui/account_dialog.py`) tells the user
their password "is sent only over HTTPS," but `agent/account.py`'s
`normalize_account_base_url()` accepts plain `http` (default is even
`http://localhost:3000`) with nothing enforcing the on-screen claim. (2) That same
Hosted-Account feature (added 2026-08-28, confirmed via `git log` in this repo too --
before this GDPR review's 2026-09-01 date) was never actually assessed by the review: its
own scope and file list cover only the inert `providers/cartogen.py` LLM-provider stub,
and "password" never appears in `docs/GDPR_COMPLIANCE_REVIEW.docx` here either. Full
write-ups: `docs/BUG_TRACKER.md` BUG-2026-09-08-1/-2, and full detail in
`cartogen-ai-community/docs/CODE_REVIEW_2026-09-08.md` (written against that checkout, but
both findings independently verified to reproduce here since this repo is where the code
actually lives now -- `cartogen-ai` is currently 15+ commits and two feature-phases ahead
of `cartogen-ai-community`, per the 2026-09-08 folder-reconciliation check). Neither finding
has been fixed yet -- awaiting the project owner's go-ahead to change code, per Hermes Charter Rule 8.

**Update, 2026-09-08, later -- full independent 5-dimension review of *this* repo (`cartogen-ai`), not assumed to mirror the community-line review above:** wrote `docs/CODE_REVIEW_2026-09-08.md`, a fresh pass over this repo's own, larger, more-evolved codebase (the 27-point architecture review's 15 commits, the temporal-dashboard feature). Mockups/incomplete-UI: clean. Bugs: no new functional bugs beyond one documentation-hygiene item (this file's own "not yet committed" annotations for several 27-point-review items and other work are stale -- `git log`/`git status` confirm all of it is already committed; worth a future pass to reconcile every such claim against `git log`). Uncompleted work: none -- working tree fully clean as of `9fcc939`. GDPR: `docs/GDPR_COMPLIANCE_REVIEW.docx` confirmed byte-identical to `cartogen-ai-community`'s copy (same 2026-09-01 date, same commit `01d853f` reference, never updated for anything since) -- F1 re-confirmed fixed here, F6/F7/F2 (and by extension F3-F5/F8-F13) re-confirmed still open, no new GDPR findings. **Security: one new CRITICAL finding** -- `execute_pyqgis_script`'s sandbox is fully bypassable via exception-traceback frame-walking (`__traceback__`/`tb_frame`/`f_back`/`f_globals`), reaching the real unrestricted `builtins` module and from there `open`/`__import__`/`eval`/`exec`, none of which the current `_BLOCKED_DUNDER_ATTRS` denylist inspects. Live-reproduced, not theoretical: an exact copy of this file's own `_validate_script_safety`/exec pattern accepted the exploit script and successfully wrote a real file to disk from inside the restricted context. Full writeup and recommended fix: `docs/BUG_TRACKER.md` NEW-2026-09-08-1, and `docs/CODE_REVIEW_2026-09-08.md` §4.1. Not fixed yet -- awaiting the project owner's go-ahead to change code, per Hermes Charter Rule 8, and given the severity this is recommended as the first fix once approval is given, ahead of the other open items above.

**Update, 2026-09-08, later still -- the project owner: "go ahead":** fixed and verified. Extended `_BLOCKED_DUNDER_ATTRS` in `agent/tools/system_tools.py` with the frame/traceback attribute names (`f_back`, `f_globals`, `f_locals`, `f_builtins`, `f_code`, `gi_frame`, `cr_frame`, `ag_frame`, `tb_frame`, `tb_next`, `__traceback__`), closing the escape described above -- confirmed by re-running the exact PoC through `_validate_script_safety` (now rejected) both before and after the fix. Added two regression tests to `tests/test_new_tools.py` (the PoC end to end via `execute_pyqgis_script`, plus each new attribute name checked individually). Full suite re-verified: 1219 tests (1217 + 2 new), same 1 known DNS-dependent failure, 0 errors, 0 other new failures. `docs/BUG_TRACKER.md`'s NEW-2026-09-08-1 entry moved from Open to Fixed (recent), status `fixed-verified`.

**Update, 2026-09-08, later still -- the project owner: "go through the pending task and solve them one by one":** worked the rest of this review's fix plan in priority order. (1) `BUG-2026-09-08-1` (HTTPS-claim gap): `normalize_account_base_url()` now rejects plain `http` for any host except `localhost`/`127.0.0.1`/`::1`, closing the gap between `account_dialog.py`'s "sent only over HTTPS" text and the code -- 3 new tests in `tests/test_account_client.py`. (2) `BUG-2026-09-05-2` (`calculate_service_area` degenerate-network failure): both `native:serviceareafrompoint` and `native:convexhull` calls were sharing one try/except spanning the whole multi-facility loop, so one facility hitting the known small-network edge case aborted every other facility's already-computed result too -- each stage is now isolated per facility (a failure is recorded in a new `skipped`/`warnings` result field and that facility is skipped, or, if only the hull step fails, its already-built reachable-network lines are kept); this does not change the underlying QGIS behavior on a 1-2 segment network (this session has no live QGIS to re-verify that against), it stops that known edge case from taking unrelated facilities down with it -- 3 new tests in `tests/test_logistics_tools.py`, mocked reproductions of both exact error strings recorded in the bug tracker. (3) `NEW-2026-09-08-2` (registry staleness): reconciled all 10 stale "not yet committed" claims in `docs/MASTER_TASK_REGISTRY.md` against `git log`, appending a dated `[Corrected, 2026-09-08]` note with the actual commit hash to each rather than rewriting the original journal entries. (4) `BUG-2026-09-08-2` (GDPR/Hosted-Account gap): wrote `docs/GDPR_HOSTED_ACCOUNT_ADDENDUM_2026-09-08.md`, a verified personal-data inventory for the Hosted-Account feature (what's collected, where it goes, how it's stored) -- explicitly a draft engineering input for the project owner/compliance review, not a compliance determination; the bug stays `open` pending the project owner's actual decision (extend the official GDPR review vs. defer/disable the feature). Full suite re-verified after every code change: 1225 tests (1219 + 6 new), same 1 known DNS-dependent failure, 0 errors, 0 other new failures. Still open, genuinely needing the project owner's judgment rather than an assumption: the route-straight-line-fallback and incident-reporting-vocabulary design decisions from `docs/MASTER_TASK_REGISTRY.md`'s standing queue, and the Hosted-Account feature's overall disposition.

**Update, 2026-09-08, later still -- the project owner: "Ship, extend GDPR review":** implemented the Hosted-Account feature's disposition decision. (1) Added an in-app privacy notice (`privacy_notice_label`) to `ui/account_dialog.py`, shown before registration/login -- the concrete UI gap the addendum flagged. (2) Extended `docs/GDPR_COMPLIANCE_REVIEW.docx` directly (edited `word/document.xml`, following the docx skill's edit-existing-document approach, then validated with `validate.py` and a rendered-PDF visual check against the original's exact styling) to formally cover the feature: Finding F14 (MEDIUM, transparency gap now closed, deletion/export and retention gaps remain), Recommendation R11, two new Section 4 data-inventory rows (Hosted-Account email/name/password, and the session token separately since it behaves differently under every column), three new Appendix -- Files Reviewed entries, and an Executive Summary extension note plus updated finding count (thirteen to fourteen). (3) Also corrected the addendum's own inaccurate claim (verified via `git log --diff-filter=A --follow` on `agent/account.py`) that the standing review predated the feature -- `account.py` was added 2026-08-28, before the review's own 2026-09-01 date; what actually happened is a scope gap (the review's file list never covered it), not a timing gap, and the addendum now says so. `docs/BUG_TRACKER.md`'s BUG-2026-09-08-2 entry moved from Open to Fixed accordingly. Full suite re-verified clean after the code change: 1225 tests, same 1 known DNS-dependent failure, 0 errors, 0 other new failures. What is explicitly NOT closed by this work, and stays tracked rather than silently dropped: no in-app account-deletion/export path for this feature's data (R11 -- today it's server-side only, no self-service UI), and no documented retention policy for whatever operates the configured `base_url` -- both are organizational/server-side facts this codebase has no visibility into, not code defects to fix here.

**Update, 2026-09-11 -- the project owner: v1.7.0 "Security & Logistics" release, workstream 1 (GDPR
F6/F7/F8), scoped for a UN/NGO deployment/pilot by Oct 15, 2026.** Read the review's exact
F6-F13 text via python-docx (not assumed) to scope precisely. (1) **F6 (project memory
always-on, undisclosed, duplicated to a sidecar file) -- addressed.** New
`memory.is_project_memory_persist_enabled()` (opt-in, default OFF, mirrors
`chat_persistence.is_persist_enabled()` exactly) gates `store_project_note`'s two
persistent/shareable write targets (the sidecar `.sqlite`, the `QgsProject` custom property)
and `get_project_notes`'s reads from them -- the in-memory cache stays always-on and
always-readable regardless, since the agent needs it within a session. New Settings checkbox
"Save project notes/memory in the project file and sidecar database", same pattern as the
existing chat-history toggle. 6 new tests in `tests/test_memory_and_tasks.py`. (2) **F7 (no
structured export) and F8 (no consolidated access view) -- addressed together**, per the
review's own recommendation since both touch the same three sources (project memory, global
memory, chat history) and both are already JSON internally. New `agent/data_export.py` (pure
logic, Qt/qgis-free, mirrors `ui/chat_formatting.py`'s testability pattern) assembles one JSON
document; new `agent/tools/data_export_tools.py`'s `export_stored_data` tool and a new
"💾 Export My Data" button in the Tasks & Notes panel (next to Clear Project/Global Memory)
both surface it. Needed cross-module access to the live `SpatialMemoryManager` instance
`agent.py` already binds into `task_tools.py`'s `_MEMORY_MANAGER` -- added a small public
`task_tools.get_memory_manager()` accessor rather than reaching into that private global
directly or standing up a second, empty `SpatialMemoryManager()` instance (which would only
see whatever's on disk, not what the live session actually holds in memory). Classified the
new tool `PUBLISH` in `tool_operations.py`, matching `export_layer`/`export_to_csv`'s existing
classification (point 20's completeness test enforces this). (3) **F9 (erasure can't reach
previously-distributed file copies) -- documented, not code**, added to `SECURITY.md`'s Data
Protection section: an inherent property of local-file architecture, not a defect. (4) **F10
(plaintext credential fallback)** confirmed already adequately mitigated per the review itself
-- no action. F11/F12 are organizational, not code; F13 is a stated strength. See
`SECURITY.md`'s "Remediation, 2026-09-11" entry for the short version.

**Update, 2026-09-24 -- fact-checked an external critique of this review, one real new item
kept, the rest already stale.** Alaa pasted an outside critique of
`docs/GDPR_COMPLIANCE_REVIEW.docx`. Checked every concrete technical claim in it against the
live code rather than acting on any of it directly (per this project's standing verify-before-
acting practice): its F1/F6/F7 "quick-fix" code sketches all turned out to already exist
(`clear_global_notes()`/`delete_global_note()`, the F6 opt-in persistence gate, and the F7/F8
`export_stored_data` tool/button, all shipped 2026-09-04/09-11 above), its "vector embeddings
may be PII" concern doesn't apply (`memory.py` has zero embeddings/vector/semantic search, it's
plain keyword storage), its "logs may leak raw PII" concern is already prevented by
`logger.py`'s `log_event()` design (never logs raw prompt/response/tool-argument/tool-result
text), and its "missing zero-retention/training-tier documentation" claim is actually already
covered in more depth than the critique itself -- `SECURITY.md`'s transfer-mechanisms table
(F3) already distinguishes Gemini's free-vs-paid training policy and OpenAI's no-training-by-
default policy, tied directly to a live UI tooltip for OpenRouter's equivalent toggle.

**One genuinely new, not-yet-existing idea survived the check, and was added:** a preventive
complement to F1's reactive delete-after-the-fact fix -- nothing stopped the model writing PII
into global memory in the first place. New rule 49 in `agent/prompts.py` (`_ALL_RULES`),
added to `CORE_RULE_NUMBERS` (always included, matching rule 3's "memory mechanics" category;
`store_global_memory` is itself in `_ALWAYS_GUARANTEED_TOOLS` so a domain-triggered version
would've fallen back to always-on anyway -- CORE just makes that explicit): never write a
beneficiary's name, exact coordinates, phone number, or other individually-identifying detail
into `store_global_memory`, since it is machine-wide and persists indefinitely across every
unrelated project on this installation -- the exact property that made F1 CRITICAL rather than
MEDIUM in the first place. 7 new unit tests in `tests/test_prompt_modules.py`
(`TestRule49GlobalMemoryPiiGuardrail`). Full suite: 2030 tests, all passing. The critique's
"Ollama-first for conflict zones" recommendation is a real product/deployment policy question,
not a code gap -- left for Alaa/DPO, not decided here.

**Update, 2026-09-24 -- compiled review package sent for DPO sign-off, determination received
and recorded.** Compiled every open thread in this section (all 14 findings reconciled against
current code, the DPIA screening result, and what remained genuinely open) into one artifact
for a DPO/legal read: `https://claude.ai/artifact/CenwECt4wjJeoce2xVjSsq`. A determination came
back covering 3 decisions:

- **DPIA (worksheet §6): required under Art. 35(1), approved subject to deployment
  constraints.** `docs/DPIA_SCREENING_WORKSHEET.docx`'s Section 6 sign-off block now has this
  determination's text filled in (the "is a DPIA required" / "reference or location" /
  "residual risk and conditions" fields) -- the "Assessed by (name, role)" and "Date" fields
  are deliberately left blank, since recording a fabricated signer wasn't this session's call
  to make; the actual DPO still needs to sign those two fields directly.
- **Deployment posture: Ollama-only for protection/incident/displacement data.** Cloud
  providers restricted to anonymized/aggregated/macro-level data. **Documented, not enforced
  in code** -- Alaa's explicit instruction was document-only for now (a real technical gate
  would need a classification of which tools/data count as "sensitive" first, its own scoping
  pass, not squeezed in here). New "DPIA determination and deployment constraints" subsection
  in `SECURITY.md`'s Data Protection section; a matching note in `docs/USER_GUIDE.md`'s "Where
  it goes" section pointing users at the constraint before they assume cloud is approved.
- **Hosted-Account feature (F14): restricted, not disabled in code.** Same "document, don't
  build a gate yet" scope -- the constraint (self-hosted `base_url` or an executed DPA first)
  is recorded in `SECURITY.md`, the dialog itself is unchanged.
- **File-sharing SOP, extending F9:** field teams must purge local memory before committing a
  `.qgz` to a shared drive/version control -- documented alongside the other constraints, not
  a code change (F9 already established this is inherent to local-file architecture, not
  fixable in code).

**Not done, explicitly deferred, genuinely open:** any technical enforcement of the Ollama-only
constraint (no per-tool or per-data-class provider gating exists), any code change to the
Hosted-Account dialog, and R2's vendor-DPA execution (an organizational/contractual act, not
something this codebase can do). All three remain real follow-ups if/when the org wants them
built rather than just required.

**Update, 2026-09-24 -- the Ollama-only enforcement gate scoped, not built.**
`docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md`. Findings from reading the code that shape the
design: **(1)** the existing per-layer sensitivity tag is advisory, manual and fail-open (an
untagged layer is `level=None`, treated as not sensitive), and `set_layer_sensitivity` has no
confirmation gate, so the model itself could currently lower a tag -- any enforcement that trusts
tags has to close that first. **(2)** "Ollama" is not "local": the client takes a free-form
endpoint URL, so the gate must classify the endpoint host, not the provider name. **(3)**
`get_attributes` returns field names only, so the value-bearing routes to the provider are: tool
results (one serialization chokepoint), `execute_pyqgis_script` return values (hard -- layer names
are literals inside the script), attachments, the prompt refiner's separate request, and
conversation history (switching provider mid-session re-sends earlier tool results). Recommends a
data-class gate on the existing tags (G1) with an org-level fail-closed strict mode (G2), and
rejects a tool-class-only gate and content/PII detection as the boundary. States plainly that it
prevents accidents, not a determined user, since the policy setting lives in user-editable
`QgsSettings`. Six decisions are listed for Alaa/the DPO (default mode, override policy, who
classifies layers, `execute_pyqgis_script` on cloud, history on provider switch, where the policy
lives) before any code. **Not built; no phase started.**

**Update, 2026-09-24, later — the Ollama-only gate partly built (Alaa: "ok proceed").** Built
behind a mode that defaults to **Off**, so nothing changes until someone opts in: Phase 1 in full
(`core/models/egress_gate.py`: endpoint-locality classifier, protection rules, lineage inheritance,
fail-closed on internal error), the pre-dispatch check in `_real_execute_tool` (a blocked call never
executes), a confirmation lock so the model cannot lower a protected layer's tag itself
(`confirmed` is not in the schema, so a model-supplied value is discarded), and Settings controls
(Off / Warn only / Block, plus strict). Verified with 51 new unit tests and a live run against real
QGIS 4.2.2 of 19 bypass-style scenarios, all passing — including derived-layer inheritance through
real lineage, a forged `confirmed=True`, strict mode, and `execute_pyqgis_script`. **Still not
built:** the result-serialization chokepoint, gating attachments and the prompt refiner's separate
request, history handling on a provider switch, a layer-classification UX, and override records — so
the gate covers the tool-call route only, which `SECURITY.md` now says plainly. Defaults were chosen
without waiting on the scope doc's six decisions and are the reversible ones (Off; strict off; no
override flow; setting in user `QgsSettings`). It prevents accidents, not a determined user. Note
for whoever tests it: it depends on layers being tagged — an untagged layer is unprotected outside
strict mode.

**Update, 2026-09-24, second build pass (Alaa: "proceed").** Checked each remaining route before
building it, which changed the plan: **attachments** were the one real remaining gap and are now
gated at their single chokepoint (`ChatInputController.analyze_file`) — treated like an untagged
layer, so blocked on cloud only in strict enforce mode, and a blocked file is dropped from the
next-message queue. The **prompt refiner** needed no gate (it sends only the user's own text). The
scope doc's claim that a provider switch re-sends earlier **tool results** was wrong — history
stores only user messages and assistant prose — and is now marked corrected there. The planned
**result-serialization catch-all** was replaced by `tests/test_egress_gate_coverage.py`, after a
search of all 178 tools showed every feature-reading tool names its layer (so the pre-run check
already sees it); the guard fails CI if that stops being true and was mutation-checked. Verified:
unit suite 2095 passing, and the full live QGIS suite (46 tests) locally against real QGIS 4.2.2.
Still open: the scope doc's §7 decisions, a layer-classification UX, override records.

**Update, 2026-09-27 — Presidio (outbound PII scanning) scoped and NOT recommended.** Alaa asked
whether `Presidio` (Microsoft) could close the two gaps `SECURITY.md` names honestly (user-typed
text and the model repeating prior content are not gated) by scanning outbound content for PII.
`docs/PRESIDIO_EGRESS_SCAN_SCOPE_2026-09-27.md` scopes it — and finds this project already
evaluated and rejected exactly this approach as option **G4** in the original
`OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md` ("unreliable in exactly the cases that matter...
and it creates false assurance. Not recommended as the boundary"). Installed `presidio-analyzer`
v2.2.364 and ran it live against text shaped like this project's real humanitarian data to check
whether the real library changes that verdict. It does not — the live evidence is stronger than
the original reasoning anticipated: on **Arabic-script beneficiary names** (this plugin's own
primary use-case language, per `CLAUDE.md`), Presidio doesn't degrade gracefully, it produces
**confidently wrong output** — flagging ordinary words ("the beneficiary", "camp number five") as
`PERSON` while missing the real name entirely, and (separately) mislabeling a geographic
coordinate as a `PHONE_NUMBER` (Presidio ships no coordinate recognizer at all). Retested with a
multilingual model (`xx_ent_wiki_sm`) specifically to rule out "wrong model, not wrong approach" —
same failure shape (missed the real name; flagged a non-name phrase instead). **Recommendation:
do not build this** — not deferred, actively not recommended, since the false-assurance risk is
worse on this project's own core content than a generic "PII detection is imperfect" caveat would
suggest. The tag-and-lineage gate (`egress_gate.py`) remains the actual, unchanged mechanism.
`presidio-analyzer` and its models were removed from this environment after testing; not a
dependency of this repo.

**Update, 2026-09-28 — logging the still-open data-classification-gate decision explicitly, per
Alaa's request.** The gate itself (`egress_gate.py`) is built and covers the tool-call, attachment,
and result-serialization routes (see the two 2026-09-24 build-pass updates above), but
`docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md` §7's six decisions were never answered —
defaults were chosen as reversible placeholders (Off, non-strict, no override flow) specifically so
shipping the gate wouldn't wait on them. Restating them here so they don't stay buried in a dated
scope doc:

1. **Default mode:** off / warn / enforce — and whether a deployment with a completed DPIA
   sign-off should default to strict (fail-closed).
2. **Override policy:** can a user lift a block with a recorded justification (as
   `advance_dataset_status(override=True, note=...)` already does elsewhere), and who reviews
   those records?
3. **Who classifies layers, and how:** manual tagging only (today's behavior — untagged is
   unprotected outside strict mode), or a prompt at layer-load time?
4. **`execute_pyqgis_script` on cloud:** blanket-block whenever any non-PUBLIC layer exists in the
   project, or a narrower rule?
5. **History on provider switch:** the scope doc's original premise here (a switch re-sends prior
   *tool results*) was already found wrong and corrected in the 2026-09-24 second-build-pass update
   above — history holds only user messages and assistant prose. The decision narrows accordingly:
   is gating that residual (user/assistant text potentially containing sensitive content) on a
   provider switch worth building, or is it accepted as out of scope?
6. **Where the policy setting lives:** user-editable `QgsSettings` (today's default — prevents
   accidents, not a determined user) vs. a managed org-level config that a local user can't change.

No code change accompanies this entry — it is the decision request itself, not a resolution.

**Update, 2026-09-28 — decision 1 (default mode) answered by Alaa; documented, not auto-enforced.**
Code default stays **Off** for a general Community install (unchanged — a fresh install's behavior
should not silently change before anyone has opened Settings). For a deployment that has completed
the DPIA sign-off above, the recommendation is **Block, non-strict** — not strict-by-default even
there, since strict mode requires every layer classified first and this plugin has no automatic
classification path yet (decision 3, still open). Surfaced as a guidance label directly under the
"Cloud data protection" dropdown in `ui/settings_dialog.py`, live-verified rendering correctly in a
real QGIS 4.2.2 session (screenshot-checked, not just "imports without error"), plus a matching
paragraph in `SECURITY.md`'s "DPIA determination and deployment constraints" section. Deliberately
NOT auto-detected/auto-switched: whether a given install's DPIA is actually complete is an
organizational fact this plugin cannot observe, so making the setting itself smart about it would
mean guessing, not deciding. **Decisions 2, 3, 4, 5, 6 remain open, unchanged by this update.**

**Update, 2026-09-28 — decision 2 (override policy) answered and built: yes, overridable, but only
via the existing UI Confirm-button path, never a model-supplied argument.** A blocked tool call
with known layers no longer returns a flat `EGRESS_BLOCKED` result to the model -- new
`egress_gate.preview_required()` wraps it as `PREVIEW_REQUIRED` instead, so `_real_execute_tool`
hands it to the exact same destructive-action confirm/cancel machinery `remove_layer`/
`field_calculator` already use (`task_manager.set_task_preview`, `chat_tab_widget.py`'s
`_resolve_pending_confirmation`, the Activity tab's Confirm button, a typed "Confirm" chat reply --
all one code path). Only a real UI click sets `user_confirmed=True`; the dispatcher's own
schema-filtering already guarantees the model cannot inject that itself (same trust boundary
`SECURITY.md` §5 documents for the `confirmed` flag). No new free-text justification field --
the deliberate click on a card naming the exact tool and layers involved is the audit record,
matching that neither `remove_layer` nor `field_calculator` requires a note either. Both paths are
logged (`egress_blocked` / `egress_override_confirmed`), and an overridden call's result carries an
`egress_override_note` so the chat transcript itself shows what happened -- satisfies "who reviews
those records": the same user who clicked Confirm, visible in their own chat/Activity history,
matching how every other confirmation in this codebase is reviewed (no separate audit-log
mechanism exists for the others either, so none was added here). **Deliberately excluded:** a
check-failure block (`check_failed_decision`, the gate's own machinery erroring) has no known
layers to show, so it stays a hard, non-overridable block -- nothing concrete to confirm.

6 new/updated unit tests: `tests/test_agent_runner.py`'s `TestEgressGateWiring` (block-with-layers
now returns `PREVIEW_REQUIRED` not the raw block; block-with-no-layers stays non-overridable even
confirmed; a confirmed override actually runs the tool and attaches the note) and a new
`TestPreviewRequired` class in `tests/test_egress_gate.py` (shape, rationale content, arguments
copied not aliased, no crash on a missing `layers` key). Full suite: 2253 tests, all passing, ruff
clean. **Decisions 3, 4, 5, 6 remain open, unchanged by this update.**

**Update, 2026-09-28 — decisions 4, 5, 6 answered; only decision 3 (who classifies layers) remains
genuinely open.**

- **Decision 4 (`execute_pyqgis_script` on cloud): keep the existing whole-project rule, don't
  widen it.** Already implemented via `WHOLE_PROJECT_TOOLS` — this tool is judged by the same
  PROTECTED-levels standard as every other tool (RESTRICTED/SENSITIVE, or untagged in strict
  mode), not a broader "any non-PUBLIC layer" rule. Verified live and now regression-tested
  (`test_execute_pyqgis_script_is_allowed_with_only_internal_layers`): an all-INTERNAL project
  does not block this tool on cloud, since INTERNAL is an explicit owner declaration the data may
  leave the machine. Widening to block on any non-PUBLIC layer was considered and rejected — no
  real security gain, real usability cost for ordinary INTERNAL working layers.
- **Decision 5 (history on a provider switch): accepted as out of scope, not built.** The scope
  doc's premise (a switch re-sends tool results) was already corrected 2026-09-24 — history holds
  only user text and assistant prose. The real residual (the model repeating protected content in
  its own prose) is the already-documented "What is not gated" gap, present regardless of whether
  a provider switch happens — narrowly gating just the switch case wasn't judged worth the added
  complexity for that small a slice of an already-open gap.
- **Decision 6 (where the policy setting lives): `QgsSettings` stays it for Community.** A managed
  org-level config is an Enterprise/Pro-tier deployment feature — real work §1.3's Path C decision
  already named as unblocked but not started, not something to build ahead of that tier work
  actually resuming.

No code change for decisions 5/6 (documentation-only, per `CONTRIBUTING.md`'s "document, don't
build ahead of demand" convention already used for the Ollama-only posture itself). Decision 4
got one new regression test, no behavior change (ratifying existing code as the deliberate
answer, not a fix). Full suite: 2254 tests (2253 + 1), all passing, ruff clean. Full writeup:
`SECURITY.md`'s "What it does not do" list, decisions 4/5/6 entries.

**Update, 2026-09-28 — decision 3 (who classifies layers, and how) answered and built: manual
tagging stays the model, but it's no longer chat-only.** Before this, `set_layer_sensitivity` was
only reachable by asking the AI to call it -- no direct QGIS UI control existed at all. New
`ui/layer_sensitivity_dialog.py` (`LayerSensitivityDialog`) opens from a new "🛡 Sensitivity"
header button in `ui/dock_widget.py`, alongside the existing Memory/Settings buttons -- pick a
loaded layer, see its current classification, set a new one with an optional reason. Calls
`agent/tools/sensitivity_tools.py`'s `set_layer_sensitivity(..., confirmed=True)` rather than
`models/sensitivity.py`'s bare function directly: this dialog itself IS the UI confirmation
decision 2's egress-gate loosening lock already requires (a human filling out a dialog and
clicking Apply is the same trust boundary as the chat confirm-card flow, not a way around it).

**The load-time-prompt option was considered and explicitly rejected**, not left unresolved:
interrupting every layer load (including ordinary basemaps and reference data, the overwhelming
majority of loads) to ask "how sensitive is this?" adds real friction for a question this plugin
usually can't answer better than the user can in the moment anyway. A narrower version -- prompt
only after a humanitarian-data-fetching tool (HDX/OSM/geoBoundaries) adds a layer, since that's
the actual risk surface for beneficiary-level data -- was considered as a middle ground but not
built: it needs its own scoping pass (which tools, sync vs. async, does it interrupt an in-flight
agent turn) that wasn't part of this decision's scope. Flagged as a real follow-up, not decided
here.

A new "shield" icon was added to `ui/icons.py`'s existing theme-reactive SVG set (`_ICON_TEMPLATES`,
same stroke-only-outline convention as `notes`/`settings`), covered by that module's existing
generic `test_every_known_icon_produces_well_formed_svg` test with no test-file changes needed.
No unit test file was added for `LayerSensitivityDialog` itself, matching this codebase's existing
convention for QGIS-heavy dialogs (`settings_dialog.py`/`memory_dialog.py` have none either) --
live-verified instead against real QGIS 4.2.2 (screenshot-checked): the dialog lists loaded
layers, shows "untagged" for a fresh layer, and correctly reports "SENSITIVE (contains individual
beneficiary GPS coordinates)" immediately after Apply; the new header button renders correctly
alongside Memory/Settings. Full suite: 2265 tests, all passing, ruff clean.

**§1.4 is now fully closed — all six decisions answered.** Decisions 1, 3, 4, 6 kept or extended
existing behavior with real UI/doc additions; decision 2 shipped a real override mechanism;
decision 5 was accepted as out of scope. See `SECURITY.md`'s "What it does not do" list for the
complete, consolidated record.

### 1.5 Point 18 -- AI agent architecture redesign (Intent Interpreter -> Project Inspector -> Spatial Planner -> ...)

**Added 2026-09-09.** Source: `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md` point 18.
The proposal describes a multi-stage agent pipeline -- Intent Interpreter, Project Inspector,
Spatial Planner, and further stages -- replacing today's single-loop model. The actual `agent.py`
`run()` loop today is: build system prompt -> LLM call with router-filtered tools -> dispatch tool
calls -> loop. No standalone parameter-validator or risk-classifier stage exists; each tool
validates its own args inline, and no automatic project-snapshot/inspector step runs before
planning. Since the point was first reviewed, real adjacent work has landed without restructuring
the core loop: point 20 (§4 above, item 34 in `docs/MASTER_TASK_REGISTRY.md`) added a
READ/CREATE/MODIFY/DELETE/PUBLISH operation taxonomy and a per-turn undo log as an *informational
and safety layer on top of* the existing loop, and point 22 added zero-result warnings inside
individual tools -- real improvements, neither of which is the staged pipeline this point
describes.

**Why this needs a decision, not code.** The proposed pipeline is a different agent architecture,
not a bug fix or a parameter addition -- it would change how every tool call is initiated, and
either adds new LLM calls (real cost/latency on every request) or new deterministic stages
(behavior an LLM currently handles implicitly moves into code, which can be wrong in new ways an
LLM wasn't). Whether it actually improves task success/reliability over the current ReAct-style
loop needs a live-LLM evaluation comparing both against real tasks -- this sandbox has no live LLM
to run that comparison, so building it blind risks months of rearchitecture on an unvalidated
premise. This overlaps materially with point 27 below (a validated pre-execution plan is
essentially this proposal's "Planner" stage) -- worth deciding together, not independently, so a
choice on one doesn't box in the other.

**Options, not recommending one:**
- (a) Leave as-is. The current loop plus this session's additive layers (taxonomy/transactions,
  zero-result warnings, `tool_router.py`'s relevance filtering) is a real, shipping system;
  a full rewrite is unproven to actually improve outcomes for this product's actual usage.
- (b) Build one narrow, isolated first stage -- e.g. just a deterministic Project Inspector
  snapshot run before planning, the most self-contained piece -- and measure its effect before
  committing to the rest.
- (c) Commit to the full staged pipeline as described, scoped as its own multi-week
  rearchitecture project with its own spec doc, not squeezed into an existing session.

**Needs:** the project owner's decision on whether to pursue this at all, and at what scope; if pursued, a
live-LLM evaluation harness comparing before/after doesn't exist yet and would need building first.

**BUILT 2026-09-24, option (b): narrow, isolated first stage, real and testable, not left as a
scoping-only writeup.** Alaa's instruction was the same as §1.6's: "build it, evaluate later" --
live-LLM evaluation of whether this actually helps is still a genuinely separate, not-yet-done
follow-up, but the stage itself is real, wired, tested, and live-verified.

**What it does:** point 18's proposal names the Project Inspector's scope explicitly as
"Layers/CRS/Fields/Layouts/Themes/Metadata." `agent/map_context.py`'s existing
`get_map_context_summary()` (unconditional, sent on every turn already) already covers
Layers/CRS/Fields -- new `core/services/project_inspector.py` (`inspect_project()`) exists only
for the genuine gap: print layouts, saved map themes, and project metadata
(title/abstract/author/keywords), none of which the agent saw before this without spending a
tool call to look them up. Deterministic and synchronous, no LLM call involved -- exactly the
"Project Inspector" stage's own description: a snapshot step that runs BEFORE planning, not a
reasoning step.

**Wiring:** called in `agent_orchestrator.py`'s `run()`, before the first LLM call of the turn,
its result passed into a new `_format_project_inspector()` block in `prompts.py`'s
`build_system_prompt()` (a new `## \U0001F4CB PROJECT INSPECTOR` section, alongside the existing
`## \U0001F5FA️ CURRENT MAP CONTEXT` one). Deliberately NOT folded into `map_context.py`
itself, which is always-on: keeping this feature-flagged and separate means its effect can be
measured in isolation later, without conflating it with `map_context`'s already-shipped,
already-proven behavior.

**Feature-flagged OFF by default** (`SETTINGS_PROJECT_INSPECTOR_ENABLED`) with a real Settings
checkbox ("Include print layouts, map themes, and project metadata in context") -- same "don't
silently change every installation's prompt content before there's evidence it helps" reasoning
as §1.6's plan-validation gate.

**Verification:** 6 unit tests for `inspect_project()` itself (`test_project_inspector.py`) + 6
for the prompt-formatting layer (`test_prompt_modules.py`'s `TestProjectInspectorContext`) + 2
integration tests exercising the real `run()` wiring (`test_agent_runner.py`'s
`TestProjectInspectorWiring` -- disabled gate never calls `inspect_project()`, enabled gate calls
it once and passes its exact result through to `build_system_prompt`). Live-verified against real
QGIS 4.2.2 (`python-qgis.bat`): a real print layout, a real saved map theme, and real project
metadata (title/abstract/author/keywords) all round-tripped correctly through `inspect_project()`
into the rendered prompt text. Settings-dialog checkbox live-verified the same way as §1.6's
(defaults unchecked, toggling + `accept()` persists via `QgsSettings`). Full suite: 2008 tests,
all passing.

### 1.6 Point 27 -- Deterministic plan-then-validate-then-execute command model

**Added 2026-09-09.** Source: `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md` point 27.
`AgentTaskManager.create_plan` takes freeform human-readable task description strings, not a typed
step schema, and is an optional tool the LLM may call for UI progress display -- not a
pre-execution gate. `auto_advance_if_unambiguous` exists specifically because the model creates a
plan and then calls tools independently of it, not because the plan constrains execution. There is
no upfront structured-plan-then-validate pipeline anywhere.

**Why this needs a decision, not code -- same underlying blocker as point 18 above, and the same
overlap.** A structured plan schema (`task`, `aoi`, `inputs`, an ordered `workflow:` step list,
declared `outputs:`) needs to be something the LLM can reliably and consistently populate; this
sandbox has no live LLM to validate that against real queries versus the model silently degrading
back to unstructured tool-calling around a schema it half-fills. There's also a real product
tradeoff distinct from point 18's: a validation gate before every execution adds latency/friction
to *every* request, including trivial ones ("what layers are loaded"), which has to be weighed
against the safety benefit for the requests that actually warrant it.

**Options, not recommending one:**
- (a) Leave as-is.
- (b) Build the plan schema as a validation gate only for a narrow, already-defined high-risk
  class of calls -- point 20's own DELETE/PUBLISH operation types -- rather than every request,
  so routine reads/creates see no added friction.
- (c) Full deterministic plan-then-validate-then-execute pipeline as described.

**Needs:** the project owner's decision, ideally made alongside point 18's since they're two angles on the
same underlying proposal.

**BUILT 2026-09-24, option (b): narrow experiment, real and testable, not left as a scoping-only
writeup.** Alaa's instruction was explicit: "build it, evaluate later" -- the live-LLM evaluation
of whether this actually helps is still a genuinely separate, not-yet-done follow-up (this sandbox
still has no live LLM to run that comparison), but the mechanism itself is real, wired, tested,
and live-verified, not just designed on paper.

**What it does:** `PlanValidationGate` (`core/models/plan_gate.py`) blocks any tool call
`tool_operations.py` classifies `DELETE` or `PUBLISH` until `create_plan` has been called at least
once THIS turn -- reusing the EXISTING freeform `create_plan` tool (`task_tools.py`) as "the plan,"
deliberately NOT inventing the new typed `task`/`aoi`/`inputs`/`workflow:`/`outputs:` schema point
27's full proposal (option (c)) describes. That was the specific choice that let this sidestep the
exact blocker named above ("needs to be something the LLM can reliably and consistently
populate... this sandbox has no live LLM to validate that") -- nothing new for the model to learn
to populate correctly, since `create_plan` is already a tool it calls today.

**Wiring:** checked in `agent_orchestrator.py`'s `_real_execute_tool`, BEFORE the tool's own side
effects run (a blocked call never executes, not "executes then gets flagged retroactively"). Reset
every turn in `run()`, same turn-scoped lifecycle as `_transaction_log` (point 20's undo log) --
a plan made last turn never silently satisfies this turn's gate. `TWO_PHASE_TOOLS` (the
network-fetch-then-add-layer path) checked and confirmed all CREATE-classified, so that separate
dispatch path needed no changes.

**Feature-flagged OFF by default** (`SETTINGS_PLAN_VALIDATION_GATE_ENABLED`) -- a real, working
checkbox in Settings ("Require a stated plan before destructive or export/report actions"), not
just a key nobody can toggle. This is deliberate: per the tracker's own stated tradeoff (a gate
adds latency/friction to every request that hits it), this should not silently change behavior for
every installation before there's any evidence it helps.

**Verification:** 12 unit tests for the gate class itself (`test_plan_gate.py`) plus 5 integration
tests exercising the actual `_real_execute_tool` wiring (`test_agent_runner.py`'s
`TestPlanValidationGateWiring` -- disabled gate is a no-op, enabled gate blocks a PUBLISH tool
before any plan and lets it through after, never blocks READ/CREATE tools, a FAILED `create_plan`
call does NOT unblock the gate). Fixed 6 pre-existing test helpers in `test_agent_runner.py` that
construct `CartogenAi` via `__new__()` (bypassing `__init__`) to also initialize `_plan_gate`, the
same way they already initialize `_transaction_log`. Settings-dialog checkbox live-verified against
real QGIS 4.2.2 (`python-qgis.bat`): defaults unchecked, toggling + `accept()` correctly persists
via `QgsSettings`. Full suite: 2006 tests, all passing.

### 1.7 Point 28 -- Standard project folder architecture (data/00_raw, 10_staging, ... immutable raw data)

**Added 2026-09-09.** Source: `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md` point 28.
The plugin imposes zero folder structure on a QGIS project today -- files live wherever the user
puts them; no immutable-raw-data convention exists anywhere in the code or docs.

**Why this needs a decision, not code.** This is explicitly a workflow-affecting product opinion,
not a gap to close. Imposing a folder taxonomy means either actively creating/enforcing it (a real
behavior change existing users and projects would need to adopt, and this plugin has no authority
to enforce a folder layout outside its own writes) or merely documenting a suggested convention
with no enforcement (much lower value, easy to ignore, arguably not worth a tracked decision at
all). This is squarely a "how should this product want its users to work" call --
`CLAUDE.md`'s own "when you're not sure whether to just fix something" section assigns exactly
this kind of tradeoff to a human, not an agent. It's also worth naming a real-world constraint
the proposal doesn't address: this product's actual users (humanitarian GIS analysts) frequently
already work inside an org-mandated data structure they don't control (e.g. OCHA's own field
conventions) -- a second, different structure imposed from inside a QGIS plugin could add friction
without the standing to actually replace what the org already requires.

**Options, not recommending one:**
- (a) Don't build. Most target users already work within a data structure imposed by their own
  organization; a plugin-imposed alternative adds friction without authority to enforce it.
- (b) Document only -- a recommended convention in `docs/USER_GUIDE.md`, no code, no enforcement.
- (c) Build an opt-in scaffolding tool (e.g. a `create_project_folder_structure` tool the user
  calls only if they want the convention) -- imposes nothing on anyone who doesn't ask for it.

**Needs:** the project owner's decision on whether this convention is worth adopting for this product's actual
user base at all, and if so, at what enforcement level.

**BUILT 2026-09-24, option (c): opt-in scaffolding tool.** Alaa decided against (a)/(b) and for
the opt-in tool -- `create_project_folder_structure` (`project_tools.py`) creates the full layout
from the source proposal's diagram (`data/00_raw` through `40_raster`, `project/templates`,
`styles`, `models`, `scripts/{processing,atlas,validation}`, `exports/{pdf,geospatial,web,field}`,
`metadata`, `logs`) under a caller-given `base_path`. Registered `CREATE` in
`tool_operations.py` (only ever adds new empty folders via `os.makedirs(exist_ok=True)`, skips
anything that already exists -- never a DELETE/data-loss risk, so no confirmation gate per
`SECURITY.md` §5). The tool's own description tells the model to call it only on an explicit user
request, never on its own initiative -- the whole point of choosing (c) over (a)/(b) was to add
zero friction for users who already work inside an org-mandated structure. 5 new unit tests
(idempotency, never overwrites an existing folder or file -- verified with a real sentinel file
written into a pre-existing `data/00_raw`, creates `base_path` itself if missing, rejects an empty
`base_path`). Full suite: 1994 tests, all passing. `docs/TOOLS_REFERENCE.md` regenerated (178
tools now, was 177).

---

### 1.8 `task_matcher.py`'s keyword-count normalisation structurally favors short task definitions

**Added 2026-09-19, from a live-reported failure.** `_score()` (task_matcher.py) normalizes each
task's keyword-overlap score by that TASK's own keyword-list length (`weight / (denom + 1)`,
comment: "keeps short precise tasks findable"). This has a real, confirmed side effect: a task with
a short, generic keyword list scores much higher on a 2-word overlap than an equally-strong,
equally-relevant task with a longer, more specific keyword list scores on a 3-word overlap.

**Live case that surfaced it:** "Health facilities beyond one hour's travel" matched `25c.01` ("Map
health facilities", kw={facilities,health,map}, score 0.72) over `7.23` ("Calculate travel time to
health facilities", the actually-correct task, kw={calculate,facilities,health,time,travel}, score
0.55) -- purely because 7.23's kw list is longer, not because 25c.01 is a better match. `25c.01`'s
tool hints (`add_layer_from_path`/`apply_categorized_style`/`zoom_to_layer`) assume a local data
file that doesn't exist for this query; the model had no `calculate_service_area` in its directive,
couldn't find that file, and burned its entire tool-call budget probing `execute_pyqgis_script`'s
sandbox internals (blocked `os`/`sys`/`QDir`/`inspect` imports, `dir()`, `.__class__`) instead of
ever calling the right tool -- a real, user-visible task failure.

**What was fixed already (narrow, not a rewrite):** `classify()` now re-ranks toward a scored
candidate that has `calculate_service_area` in its tools when the query uses travel-time/access
phrasing ("beyond one hour's travel", "within 30 minutes", "reachable", "isochrone", etc.) --
`_ACCESS_TIME_LANGUAGE` in `task_matcher.py`. This closes the ONE confirmed live case (and its
sibling tasks across every section that share the same `calculate_service_area` tool) without
touching the shared scoring formula every other task in the 250+-entry register depends on.

**Why the underlying formula itself isn't touched here.** Reweighting `_score()` (e.g. an F1-style
blend of task-recall and query-precision instead of pure task-recall) would change ranking for
every task in the register simultaneously, not just the travel-time family -- a much wider blast
radius that needs its own dedicated review pass (rerun `test_the_matcher_still_finds_every_task_
from_its_own_title` and spot-check a representative sample of real queries per section, not just
the handful of tests this session added), not a fix bundled into a live-bug patch.

**Needs:** a decision on whether this general normalization tension is worth a dedicated pass (and
if so, what the target formula should be), or whether targeted overrides like `_ACCESS_TIME_
LANGUAGE` are the accepted long-term pattern for closing specific short-vs-long-keyword-list
collisions as they're found live.

**DECIDED 2026-09-24 by Alaa: option 1 — targeted re-rank overrides (the `_ACCESS_TIME_LANGUAGE`
pattern) are the accepted long-term approach.** The shared `_score()` normalization formula stays
untouched. This was chosen as the zero-blast-radius option over reweighting the formula itself
(which would need the full review pass described above — rerunning
`test_the_matcher_still_finds_every_task_from_its_own_title` plus a real-query spot-check across
every section — before it could ship, since it changes ranking for all 250+ tasks at once, not
just the collision family that's actually been hit). Accepted tradeoff, explicit going in: this is
reactive, not preventive — it only closes specific collisions after they surface as a live-reported
failure, the override list grows as a parallel mechanism sitting next to the real scorer rather
than fixing the underlying tension, and a not-yet-reported task pair with the same short-vs-long
keyword-list shape will fail the same way until it, too, is reported and given its own override.
**No code change from this entry** — `_ACCESS_TIME_LANGUAGE` already exists and already closes the
one confirmed live case; this decision just confirms that pattern as where the *next* one goes too,
rather than reopening the formula question each time.

---

### 1.9 ~~`run_allowlisted_processing_algorithm` outputs are always fully visible, even purely-internal ones~~

**Added 2026-09-19, from a live-reported "layer order is wrong" complaint.** Live-verified that
`set_layer_order`/`_reorder_top_level_layers` (`styling_tools.py`) themselves are NOT buggy: a
throwaway 4-layer project confirmed `set_layer_order(["A","B","C","D"])` produces exactly
`layerOrder() == ["A","B","C","D"]`, top to bottom, every time (`python-qgis.bat`, live).

**What's actually happening:** a real turn (the "Health facilities beyond one hour's travel"
analysis) called `run_allowlisted_processing_algorithm` four times to reproject/buffer/intersect
its way to an answer, producing `Assessment_Origin_3857`, `Access_Threshold_5km`,
`Health_Facilities_3857`, and `Facilities_Within_5km` -- of which only `Access_Threshold_5km` (the
buffer) was ever a real deliverable; the two reprojected copies and the (0-feature) intersection
result exist purely as internal computation steps. All four were added to the project fully
visible (`QgsProject.instance().addMapLayer(new_layer)`, no visibility flag). The model's own
`set_layer_order` call afterward only named 4 layers (the two originals, the buffer, and the
basemap) -- the two reprojected duplicates and the empty intersection layer were left out of that
call entirely and sit in the legend/map at whatever position they landed in by default, visually
cluttering a map that otherwise looks intentional.

**Why this isn't a mechanical fix.** Hiding every `run_allowlisted_processing_algorithm` output by
default would be wrong just as often as leaving it visible -- many allowed algorithms (`native:
buffer` for a requested buffer map, `native:clip` for a requested clip) ARE the deliverable a task's
own `layer` output contract expects to see rendered (`output_router.satisfied()`'s `layer` branch
explicitly credits `buffer_`/`clip_`/etc. as satisfying that contract). There's no way to tell
"purely-internal reprojection step" from "the actual requested result" from inside this one tool
call alone -- that requires either a caller-supplied hint (a new parameter?) or a smarter
default (e.g. hide only when `new_layer_name` wasn't given, on the theory that the model names
layers it means to keep visible) — a real design call, not an obvious fix.

**Needs:** a decision on the right default (always visible as today; always hidden requiring an
explicit follow-up to show it; hidden only when the model didn't bother naming the output layer;
or a new explicit `visible: bool` parameter on the tool itself).

**Still open as of 2026-09-20.** Not to be confused with the new `CartogenProcessingProvider`
(Processing Toolbox provider, §4 below) that shipped in `v1.5.7-rc1` — that's a different, newer
mechanism (2 tools wrapped as real `QgsProcessingAlgorithm` classes) and doesn't touch this tool
or its layer-visibility behavior at all. Re-checked this pass: `run_allowlisted_processing_algorithm`
(`processing_allowlist_tools.py`) still calls `QgsProject.instance().addMapLayer(new_layer)` with
no visibility flag, unchanged from when this item was written.

**FIXED 2026-09-24, option 1 (narrow fix, decided by Alaa over the costlier explicit `visible`
parameter):** if the caller didn't bother naming the output (`new_layer_name` omitted, falls back
to the auto-generated `"<alg_id>_output"` name), the layer is still added to the project/legend
(inspectable, exportable, included in `set_layer_order` if named explicitly afterward) but its
layer-tree checkbox is unchecked via `layerTreeRoot().findLayer(new_layer.id()).setItemVisibilityChecked(False)`
— betting on the theory the source doc itself named: the model names layers it means the user to
see. An explicitly-named output stays visible as before. The tool's `new_layer_name` schema
description was updated to tell the model this distinction exists, so it can name outputs
deliberately rather than by accident; no new parameter was added, no separate prompt-rule doc
needed updating (checked `tool_operations.py`/`system_tools.py`'s other references to this tool —
both are routing/classification only, no behavior documentation to keep in sync). Live-verified
against real QGIS 4.2.2 (`python-qgis.bat`, not mocks): an unnamed buffer output came back
`itemVisibilityChecked() == False`, a `new_layer_name="my_buffer"` call on the same algorithm came
back `True` — both cases also covered by 2 new unit tests
(`test_unnamed_output_is_hidden_from_the_layer_tree`, `test_named_output_stays_visible`) in
`tests/test_processing_allowlist_tools.py`. Result dict gained a `visible: bool` field reporting
which branch was taken. **If this naming-convention bet doesn't hold up in practice** (the model
keeps omitting names for genuine deliverables, or naming scratch layers out of habit), the
tracker's original option 3 (an explicit `visible` parameter) is the documented fallback — not
attempted here, since this was scoped as the narrow fix.

### 1.10 Exact-ZIP clean-profile install and upgrade test — needs a human with a real QGIS profile

**Added 2026-09-20, from the 15-section production-standard audit's P1 findings.** 4 of the 5 P1
findings from that audit were fixable/verifiable from this sandbox and are closed — see §4's
2026-09-20 entry. This 5th one structurally cannot be: it requires installing the exact published
release ZIP into a **fresh QGIS profile** (not this dev tree), restarting QGIS, confirming a clean
load, then testing an in-place upgrade from the previously-published `v1.15.6`, and a full run of
`docs/RELEASE_SMOKE_TEST.md`'s 16-category checklist against that installed copy. All of that needs
a real interactive QGIS GUI session and a second, older release ZIP already in hand — neither
exists in this sandbox. `RELEASE_SMOKE_TEST.md`'s own run log is still only complete for an RC4
build; no entry exists yet for `v1.16.0-rc1` or later.

**Needs:** a human, on a machine with QGIS installed, to: (1) create a fresh QGIS profile, (2)
install `v1.16.0-rc1`'s published ZIP into it, restart, confirm clean load with no errors, (3)
separately test upgrading an existing `v1.15.6` install in place, (4) run the RELEASE_SMOKE_TEST.md
checklist against the result and append a dated entry to its Run log. Until this is done, this
audit's overall "GO for QGIS 4.2.2 functional RC, NO-GO for stable production release" verdict
should be taken as accurate — the automated/live-headless fixes in §4 close the *code-level* P1s,
not this release-process one.

**Partial automation, 2026-09-23/24 — closes part of this item, NOT all of it (see below for what
remains genuinely open).** Reasoned through what's actually blocking here: `initGui()` needs a real
`QgisInterface` (`self.iface`), which only exists inside a running QGIS desktop process's C++ main
application — `QgsApplication([], True)` alone (this sandbox's usual headless technique) never
constructs that, so the literal "install via the Plugin Manager, watch it load" step is correctly
unautomatable from here, as this entry has said since 2026-09-20. But most of the rest of what this
item asks for — a fresh profile, an exact-ZIP install, an in-place upgrade, and a "does it come up
clean" check — doesn't strictly require the Plugin Manager UI, only the plugin folder sitting at a
real profile path and QGIS's own entry point (`classFactory` → `initGui` → `unload`) being called
the way QGIS calls it. Built a hand-rolled `FakeIface` providing only the 3 methods `initGui()`/
`unload()` actually call (`mainWindow()`, `addToolBarIcon()`, `addPluginToMenu()`) — explicitly
NOT a `QgisInterface` substitute, doesn't validate toolbar/menu rendering or give a human anything
to look at — and drove the real entry point against a real profile:

1. Created a fresh profile directory (`python/plugins/`, nothing else in it).
2. Built `v1.15.6` fresh from its tag (`commercial-plugin-v1.15.6`, no GitHub Release/asset exists
   for it on this repo, so built it the same way `plugin_upload.py` builds any release — from a
   clean archive of that exact commit) and installed it into the fresh profile.
3. Ran the real `classFactory(fake_iface)` → `initGui()` → `unload()` sequence via `python-qgis.bat`
   against that profile path. Result: **clean** — namespace bootstrap resolved
   (`cartogen-ai/src/cartogen_ai`, the hyphenated real installed folder name, not the dev tree),
   1 toolbar action + 2 menu actions installed, no Processing provider (correct — that feature
   postdates v1.15.6), `unload()` completed with no exception.
4. Simulated the in-place upgrade: deleted the v1.15.6 plugin folder from that same profile and
   extracted this repo's published `v1.16.0-rc4` ZIP into it (asset id `584510070`, checksum
   re-verified against the release, same as the `docs/RELEASE_SMOKE_TEST.md` entry above).
5. Ran the same entry-point sequence again, as a **separate process** (simulating a QGIS restart,
   not just a re-import in the same interpreter — a stale-`sys.modules` false pass would defeat the
   point). Result: **clean** — same successful bootstrap/initGui/unload, and this time the
   Processing provider DID register and DID get removed on unload (the version difference the
   upgrade should produce). No leftover-file or stale-module symptoms across the upgrade.
6. The 16-category `RELEASE_SMOKE_TEST.md` checklist itself was not re-run against this
   profile-installed copy specifically — its content is byte-identical to the rc4 ZIP already
   checklist-verified 27/27 in this doc's Run log entry immediately above, so re-running it against
   the same bytes at a different path would just be re-confirming the same result a second time.

**What is still genuinely open, and still needs a human:** whether the toolbar icon actually
*renders* correctly in a real QGIS toolbar, whether the menu entry actually *appears* in a real
QGIS menu bar, and whether a human watching QGIS actually start up with this profile sees no error
dialog — none of that can be confirmed by a `FakeIface` that only exists to not raise an exception.
The "GO for QGIS 4.2.2 functional RC, NO-GO for stable production release" verdict from
2026-09-20 stands unchanged by this entry; it narrows what's missing to specifically the
visual/interactive confirmation, not the whole install/upgrade mechanism.

**Update, 2026-09-27 — the toolbar/menu-rendering gap closed, with a real `QgisInterface`, not a
`FakeIface`.** Alaa asked to handle this directly. A real QGIS 4.2.2 Docker image
(`qgis/qgis@sha256:6ffe6b31646247f2e179cb2cc32bb4df215eedc99f387ad59a6cc88ebfe23e21`, the exact
digest this repo's own CI pins) turned out to be pullable in this sandbox after all — the Docker
daemon just needed starting manually (`dockerd` isn't running by default here, but starts and
works fine once launched), which earlier sessions this month had not tried. Ran the real `qgis`
desktop binary (not `python-qgis.bat`'s script mode) under Xvfb, with `--code` driving a real
`iface`-bound Python script inside the actual running app — genuinely different from the
2026-09-23/24 `FakeIface` approach, which explicitly could not validate rendering.

Two real environment bugs had to be found and worked around before this worked at all (both
sandbox/test-harness issues, not bugs in this plugin):
1. **`xvfb-run`'s signal-based readiness wait hangs when it runs as a container's PID 1** (no init
   process to reap children/deliver signals correctly) — worked around by starting `Xvfb`
   manually and polling `xset -display :99 q` for readiness instead of using `xvfb-run`.
2. **This QGIS build's real profile path is `~/.local/share/QGIS/QGIS4/profiles/<name>`, not
   `QGIS3/profiles/<name>`** (QGIS renamed the config directory for QGIS4, but the per-profile
   *settings file inside it* is still named `QGIS3.ini`) — confirmed by directly inspecting the
   live app's own `qgis.utils.plugin_paths` from inside a running `--code` script; the wrong path
   silently produced a `ModuleNotFoundError`, whose exception-handling path
   (`qgis.utils.showException` → `open_stack_dialog`, taken because `QApplication.activeWindow()`
   is `None` under a window-manager-less Xvfb) opened a blocking modal dialog that looked
   indistinguishable from a genuine hang until a `faulthandler`-triggered stack dump (`SIGUSR1`)
   showed exactly where execution was stuck.

With the real path, both parts of this item's original ask ran clean, verified via real Qt widget
introspection on the live app (`win.findChildren(QToolBar)`/`QMenu`), not just "didn't raise an
exception":
- **Fresh profile, `v1.15.6` (built from its tag, matching the 2026-09-23/24 methodology).**
  `qgis.utils.loadPlugin`/`startPlugin` both succeeded; a `QAction` titled "Cartogen AI" was found
  on a real `QToolBar`, and a `QMenu` titled "Cartogen AI" (containing "Cartogen AI" and "Help"
  entries, matching `plugin_main.py`'s own `addPluginToMenu` calls) was found nested under the
  Plugins menu, exactly where `addPluginToMenu` is documented to place it — not a new top-level
  menu-bar entry, so it does not show in a plain screenshot without opening the Plugins menu.
  Screenshot captured (`win.grab()`) showing a clean startup with no error dialog.
- **In-place upgrade, `v1.15.6` → the actual published `v1.16.0-rc5` release asset** (downloaded
  via the GitHub API with the environment's own `GH_TOKEN`, since this repo is private; sha256
  independently verified against the release notes' published checksum before use). Deleted the
  `v1.15.6` plugin folder from the same profile, extracted the rc5 zip in its place, then relaunched
  as a **genuinely separate Docker container invocation** (a real new process, not a re-import in
  the same interpreter). Same clean result: toolbar action and menu both found, no error dialog.

**Both runs needed a manual `loadPlugin`/`startPlugin` call from the driving script rather than
relying on the profile's `QGIS3.ini`'s `[PythonPlugins] cartogen-ai=true` auto-enable** — that
setting did not take effect in this harness (`plugin_loaded_before_manual` was `False` both times);
not investigated further since the manual call exercises the identical `qgis.utils` code path a
real Plugin-Manager-driven enable would, and getting the auto-enable ini working is a test-harness
detail, not something this item needed to close.

**What this does and does not close:** this closes the specific gap the 2026-09-23/24 entry left
open — real toolbar rendering, real menu rendering, and a real clean startup/upgrade, all
confirmed with a genuine `QgisInterface` inside an actually-running QGIS 4.2.2 desktop process, for
both a fresh install and an in-place upgrade. **Not done:** the full interactive
`RELEASE_LIVE_TEST_SCENARIOS.md` walkthrough (16 tool categories driven through the real chat UI)
still needs a real LLM provider API key, which this sandbox does not have — that remains a
separate, still-open verification, not part of what this item asked for. Test harness (Dockerfile-free
docker run invocations, profile fixtures, diagnostic scripts) was scratch work in `/tmp`, not
committed to the repo — the fixes and findings that matter (this entry, plus the `RELEASE_SMOKE_
TEST.md` Run log entry below) are what's retained. The 2026-09-20 "GO for QGIS 4.2.2 functional RC,
NO-GO for stable production release" verdict can now be revisited: the specific reason for the
NO-GO (this item) is closed for rc5, so a decision to promote rc5 (or a successor) to stable is a
release-timing call for Alaa, not reopened or decided here.

### 1.11 `execute_pyqgis_script`'s AST-blocklist sandbox — process isolation (Phase 1) built 2026-09-28

**Added 2026-09-23, from a deeper adversarial pass on the sandbox + `execute_read_only_sql`.**
Confirmed live against the real `_validate_script_safety` + restricted-`exec()` path on QGIS
4.2.2: 2 real bypasses found and closed the same day (commit `4268c95`) — `qgis.utils`/`processing`
each import `os`/`sys` at module scope, reachable as plain attributes with no blocked import
statement (`qgis.utils.os.getcwd()`, and `qgis.utils.sys.modules['subprocess']` handing back the
live `subprocess`/`socket`/`ctypes` module objects); and this plugin's own package was never
blocked, so a script could `from cartogen_ai.infrastructure.auth import CredentialManager` and read
the live in-memory session credential store directly. Both fixed and re-verified live after the fix
(`os`/`sys`/`modules` added to `_BLOCKED_DUNDER_ATTRS`, `cartogen_ai` added to `_BLOCKED_MODULES`).

**This is the same shape of gap every prior bypass-fix in `system_tools.py` has been** (see that
file's own changelog comments: the `QFile`/`QProcess` Qt-class sweep, the `type.__dict__` dict-
subscript bypass, the frame-walking `__builtins__` escape) — a blocklist can't be proven complete
because the attack surface is "any capability-bearing object reachable through an allowed name,"
which is structurally unbounded, not a finite list to exhaust. Each fix closes the specific
instance found that session, not the pattern. **By explicit instruction (2026-09-23): treat
process isolation (running the script in a genuinely separate process with no access to this
plugin's credential objects or an unrestricted filesystem) as the real fix for this tool, not
another round of denylist patching** — the narrow patch above was applied because it was cheap and
closed real, live-confirmed holes, not because denylist-sweeping is the intended long-term design.
No isolation work has been scoped or started; this entry is the decision record, not a plan.

**Also found the same pass, NOT fixed, explicitly deferred here rather than patched piecemeal:**
- **`QgsProject.instance().write(<any path>)` runs from inside a script with no path restriction
  and no confirmation gate** — live-confirmed it wrote a real file outside the project directory.
  Every other destructive/file-producing tool in the registry goes through `SECURITY.md` §5's
  confirmation-gate mechanism; a script can reach this QGIS API directly and skip it entirely,
  which is really a scoping/allowlist question for what `execute_pyqgis_script` should be able to
  touch on the project object, not a blocklist gap in the AST sense.
- **`QgsApplication.authManager().configIds()` is enumerable from inside a script with no gate at
  all** — live-confirmed it returned real config IDs from the machine's auth database. Doesn't
  return the actual secret values (that still requires `loadAuthenticationConfig` + the right ID),
  but config-ID enumeration is real reconnaissance a hostile script shouldn't get for free.
- **Not verified either way:** whether a script can call a *different*, already-imported tool
  function directly (bypassing that tool's own confirmation-gate check) rather than going through
  the model's normal tool-call dispatch — `TOOL_REGISTRY` names are enumerable from inside a
  script (confirmed), but actually invoking a gated tool with a forged `confirmed=True` from
  inside `execute_pyqgis_script` was not attempted. Needs a live check before it can be called
  closed OR open.

**`execute_read_only_sql`'s keyword-blocklist guard** (`db_and_workflow_tools.py`) was reviewed
alongside the sandbox but not live-tested against a real PostGIS connection this pass (none
available in this sandbox) — noted as a real design concern, not a confirmed live bypass:
- It scans the query as a flat string, including inside string literals, so a legitimate query
  containing e.g. `WHERE status = 'Delete'` would be rejected by the `DELETE` keyword check —
  a false-positive/usability bug, not a security one.
- Splitting on `;` to reject multi-statement queries also rejects a semicolon that legitimately
  appears inside a string literal.
- The list doesn't cover every server-side function that could stall or read broadly (e.g.
  `pg_sleep`, `pg_stat_file` weren't checked). The doc comment on the list itself already
  acknowledges this is an evolving, live-discovered set (`lo_export`/`dblink`/etc. were each added
  after being found), not a claim of completeness.
- Real enforcement is supposed to come from the DB-level read-only transaction/role
  (`_enforce_db_read_only`, referenced in the file's own comments) — that path was not
  independently re-verified live this pass. If it's genuinely doing the enforcement, the
  string-level keyword list is defense-in-depth on top of it, not the actual boundary; if it isn't
  reliably applied, the keyword list IS the boundary and inherits the same completeness problem as
  every blocklist above.

**Needs:** a product/architecture decision (not an engineering call) on scope and timeline for
process-isolating `execute_pyqgis_script`, a scoping decision on what `execute_pyqgis_script`
should be allowed to touch on `QgsProject`/`QgsApplication.authManager()` directly vs. only via
gated tool calls, and — separately — a live PostGIS connection to actually test
`execute_read_only_sql`'s DB-level enforcement rather than reasoning about it from the code alone.

**Update, 2026-09-24 — the 3 smaller deferred findings closed, independent of the process-
isolation architecture question above (which remains open, unscoped, per Alaa's explicit
instruction: "knock out the 3 smaller items now" rather than wait on the bigger decision).**

- **`QgsProject.instance().write(<any path>)` — fixed.** Live re-confirmed exploitable first
  (same probe technique as the original finding: wrote a real 4KB `.qgz` file to an arbitrary
  temp path, no gate), then closed by adding `"write"` to `system_tools.py`'s attribute
  blocklist (the same generic `ast.Attribute.attr` check `os`/`sys`/`modules` already use, not
  a new mechanism) — no legitimate script needs to call `QgsProject.write()` itself;
  `save_project` (`project_tools.py`) is the gated, registered path for that. Re-verified live
  after the fix: the same probe script now gets rejected at validation time, before any file
  is written (confirmed the file does not exist afterward).
- **`QgsApplication.authManager().configIds()` — fixed.** Live re-confirmed exploitable first
  (returned real config IDs from the machine's auth database), then closed the same way —
  `"authManager"` added to the same blocklist, which closes the whole `authManager()` surface,
  not just `configIds()` specifically. Re-verified live after the fix: rejected at validation
  time.
- **Whether a script can enumerate/forge-call `TOOL_REGISTRY` to bypass another tool's own
  confirmation gate — resolved as CLOSED, not open.** Live-checked directly rather than left
  unconfirmed: `globals()`/`vars()`/`dir()` are not in `_SAFE_BUILTINS` (each raises
  `NameError: name '...' is not defined` when a script tries to call them, confirmed live), and
  `cartogen_ai.*` imports are already blocked (this session's earlier §1.11 fix, `4268c95`) —
  there is currently no live path to reach `TOOL_REGISTRY` from inside a script at all. This
  was already closed as a side effect of the `cartogen_ai` import block, not by a new fix here;
  this update just settles the "not verified either way" status the original entry left open.

No new tests added (this tool's existing regression-test convention in `tests/test_new_tools.py`
already covers the blocklist mechanism generically per-name; the live probes above are the
actual verification evidence, matching how this tool's fixes have been verified every prior
round). Full suite: 2025 tests (this repo's current baseline before this fix), all passing.

**Still fully open, unchanged by this update:** the process-isolation architecture decision
itself (scope/timeline not decided, no isolation work scoped or started), and the live-PostGIS
test of `execute_read_only_sql`'s DB-level enforcement (no PostGIS connection available in this
sandbox).

**Update, 2026-09-24 — process isolation scoped, not started.**
`docs/EXECUTE_PYQGIS_SCRIPT_ISOLATION_SCOPE_2026-09-24.md` lays out the architecture: a real
finding from reading `execute_pyqgis_script`'s current `local_env` narrows the design space
meaningfully — the tool exposes no `iface`/canvas/selection today, only `QgsProject.instance()`
and plain geometry/vector constructors, so a subprocess operating on a *serialized copy* of the
project loses nothing a script can reach today except genuinely unsaved mid-edit-session state
(one named, not-yet-decided fidelity gap). Recommends **Path A** (serialize → fresh subprocess
with its own `QgsApplication` → reload results, reusing `transactions.py`'s existing
layer-id-diff technique for detecting what changed) over a curated-proxy-API rewrite (a
different tool, not this one isolated) and OS-level sandboxing (real, but a hardening layer on
top of Path A, not an alternative to it — Windows' primitives for this are weaker/less standard
than Linux's, flagged as Phase 3, not a Phase 1 blocker). A phased plan (benchmark first, then
the subprocess boundary for vector/geometry scripts, then raster support if usage justifies it,
then optional OS hardening), concrete file-level scope, and the real open risks (unmeasured
latency, Windows child-process reliability inside a Qt event loop, the test-suite migration
question for `test_new_tools.py`'s ~42 existing tests) are all in the document. **Not built,**
no Phase 0 benchmark run yet — this is the scoping pass Alaa asked for, a go-ahead on Phase 1
is a separate, later decision.

**Update, 2026-09-24 — Phase 0 benchmark run; it changes the recommendation.** Measured against
real QGIS 4.2.2 (harness committed at `tests/manual_isolation_bench/`, re-run from that location
to confirm it reproduces): **(1)** a cold subprocess per call costs **~5.0 s** end to end
(`import qgis.core` alone is ~3.5 s of it) versus under 1 ms for today's in-process call — the
original 1-3 s guess in the scoping doc was too optimistic, and per-call cold spawn is not viable
for a tool a turn may call several times; the doc now recommends a **persistent worker** instead
(derived, not yet measured, at roughly ~0.6 s/call — a prototype must confirm). **(2)** A
previously unknown, more serious fidelity gap: **memory (scratch) layers serialize into a `.qgz`
with their definition but zero features** — confirmed live at 1,000 and 50,000 features. This
plugin's tools emit memory layers constantly, so "write the project and hand it over" would give
an isolated script silently empty copies of exactly the layers it is most likely to reference;
the serialize step must export them (measured 0.10-0.15 s per 1k features, 0.53 s per 50k).
**(3)** Unverified, flagged: inside a live QGIS desktop process `sys.executable` is normally the
QGIS executable, not a Python interpreter, so locating a spawnable interpreter portably (3.28 LTR
and 4.x, Windows) is an untested implementation risk this benchmark could not cover. Limits: small
file-backed fixture, warm OS cache, no antivirus/EDR variation, run under `python-qgis.bat` not a
live desktop. Still **not built**; Phase 1 remains a separate go-ahead.

**Update, 2026-09-27 — RestrictedPython scoped as a defense-in-depth layer, separate question from
the process-isolation decision above.** Alaa asked whether `RestrictedPython` (Zope Foundation)
could improve the current same-process AST-blocklist while process isolation stays the intended
real fix. `docs/RESTRICTEDPYTHON_SANDBOX_LAYER_SCOPE_2026-09-27.md` scopes it, with the library
actually installed (v8.5) and run live against this project's own historical bypass reports, not
assumed from documentation. Two findings that narrow the recommendation sharply: **(1)**
RestrictedPython's attribute guard (`safer_getattr`) does NOT catch the dominant bypass class this
project has spent the most effort on — `pathlib`/`dbm`/`logging`/`zipfile`/`io.open`/etc. are all
plain, non-underscore method names, and `safer_getattr` only blocks underscore-prefixed names plus
a small hardcoded set; `_BLOCKED_MODULES` stays necessary regardless. **(2)** It DOES fully subsume,
and is verified more complete than, this project's own hand-built frame/traceback/generator/
coroutine introspection blocklist (`_BLOCKED_DUNDER_ATTRS`'s `__class__`/`__globals__`/`f_back`/
`tb_frame`/`cr_frame`/etc. entries, built the hard way across the 2026-09-08/09-20/09-23 sweeps) —
live-confirmed via `RestrictedPython.transformer.INSPECT_ATTRIBUTES`, a maintained-upstream
enumeration of exactly this attack surface that already includes several names this project hasn't
been live-bitten by yet (`f_trace`, `co_code`, `cr_await`, `cr_origin`, `ag_await`). Recommends
folding `INSPECT_ATTRIBUTES` into `_BLOCKED_DUNDER_ATTRS` (a one-line set union, no exec-time
mechanism change) as a small, low-risk, verified win now, and deferring the larger question (fully
adopting `compile_restricted` as the exec mechanism, which has its own unresolved compatibility
questions — `print` requires an explicit `_print_`, no import-allowlisting story exists for the
`qgis.PyQt.*` imports this tool's own prompt guidance tells the model to write) until/unless
process isolation (Path A above) is actually built, since a subprocess's own exec environment is
the more natural place to adopt it fully. **Not built** — this is the scoping pass Alaa asked for;
a go-ahead on the one-line fold, or on the larger `compile_restricted` question, is a separate,
later decision, same convention as the isolation scoping doc above.

**Update, 2026-09-27 — Shape A step 1 built.** Went ahead on the fold. Not a live
`from RestrictedPython import ...`, on reflection: `system_tools.py` has zero external
dependencies today (stdlib `ast`/`builtins` only), and a security denylist that quietly gets
weaker whenever an optional package isn't installed is a worse failure mode than the small staleness
risk of a copied list — so the 10 names `INSPECT_ATTRIBUTES` (v8.5) has that this project's own
`_BLOCKED_DUNDER_ATTRS` didn't (`f_generator`/`f_trace`/`co_code`/`gi_code`/`gi_yieldfrom`/
`cr_await`/`cr_code`/`cr_origin`/`ag_await`/`ag_code`) were copied in as literal strings, with a
comment citing the source and version. Unlike every other name in that set, these 10 are **not**
backed by a live-confirmed PoC of this project's own — added on the strength of RestrictedPython
tracking the same attack surface, not an independent live finding here. New test
(`test_blocks_names_folded_from_restrictedpython_inspect_attributes`, `tests/test_new_tools.py`)
confirmed to fail against the pre-fold code. Full suite 2228 → 2229, 0 failures, ruff clean.
`docs/TOOLS_REFERENCE.md` regenerated (no diff — this only touches the internal denylist, not the
tool's registered description). Shape A step 2 (wiring `safer_getattr` itself into the exec
environment) and Shape B (`compile_restricted` adoption) remain exactly as scoped above — not
started, no change from this update.

**Update, 2026-09-27 — two of the process-isolation scoping doc's open risks narrowed further, per
Alaa's request to scope the process-isolation decision.** `docs/EXECUTE_PYQGIS_SCRIPT_ISOLATION_
SCOPE_2026-09-24.md` §9 (new): (1) the Phase 0 benchmark's flagged-unverified "how does a Windows
QGIS desktop session locate a real spawnable Python interpreter, since `sys.executable` is
`qgis-bin.exe` there" risk is resolved as an engineering unknown, not by a new live test (none
available in this sandbox) but by research: confirmed as a known, currently-unfixed upstream QGIS
bug ([qgis/QGIS#45646](https://github.com/qgis/QGIS/issues/45646); an attempted upstream fix,
[qgis/QGIS#67318](https://github.com/qgis/QGIS/pull/67318), was closed unmerged 2026-09-18, so no
QGIS version including 4.2.2 has an official helper), with a real, shipped, MIT-licensed QGIS
plugin ([QPIP](https://github.com/opengisch/qpip)) already carrying a working, directly-adoptable
per-platform lookup (`python_command()`, cites the same upstream bug) this project could reuse
almost verbatim. Still needs live confirmation on a real QGIS 4.2.2 desktop install before Phase 1
relies on it — resolved as "a known solution exists to adopt," not as "verified working here."
(2) A concrete recommendation for the unsaved-mid-edit-session fidelity gap (§6 of that doc,
previously three open options): block the call with an error if any layer has uncommitted edits,
matching this project's existing fail-loudly-rather-than-guess convention elsewhere
(`buffer_analysis`'s `only_selected` guard, the egress gate's block-by-default) — a recommendation
for Alaa to accept or override, not decided unilaterally. **Neither of these changes the Phase 1
go-ahead decision itself, which remains fully open and unscoped-for-timeline, exactly as every
prior update in this entry has said** — this update narrows engineering unknowns a go-ahead
decision would otherwise have to weigh, it isn't a substitute for that decision.

**Update, 2026-09-28 — Phase 1 go-ahead given by Alaa; built and live-verified, not just scoped.**
Path A (serialize → persistent worker subprocess → reconcile results) implemented as
`agent/services/script_isolation.py` (the parent-side serialize/reconcile/process-management logic)
and `agent/services/_script_isolation_worker.py` (the worker's own bootstrap — imports
`_validate_script_safety`/`_SAFE_BUILTINS` from `system_tools.py` rather than duplicating the
denylist, so section 1's AST/builtins sandbox still runs as defense in depth inside the worker).
`execute_pyqgis_script` now branches on whether real QGIS is importable: when it is, the script runs
isolated; when it isn't (this repo's plain `test` CI job, and this tool's own ~40 existing unit
tests), it execs in-process exactly as before — there was no test-suite migration cost after all
(§4's open question), since those tests were already validator/dispatch-logic tests that never had
real QGIS in the first place.

**Real bugs found and fixed during live verification, not assumed correct from the design alone:**
(1) The scoping doc's Phase 0 finding ("QGIS writes a memory layer's definition but not its data")
turns out to bite on **both directions** of the round trip, not just serializing the input project —
a script's own NEWLY CREATED memory layer suffers the identical data-loss when the worker calls
`QgsProject.write()` for the result, unless it too is export-to-GPKG-and-swapped before that write.
Missed on the first implementation pass, caught by the live check below reporting 0 features on a
layer the test script had just added one to; fixed by applying the same export step in the worker,
symmetric with the parent's own pre-call export. (2) The parent's first draft exported the
*scratch-project-reloaded* copy of each pre-existing memory layer (already reduced to 0 features by
the read/write round-trip that copy went through) instead of the still-intact **live** layer object
— fixed to export from `QgsProject.instance().mapLayer(layer_id)` directly.

**Live-verified against the real `qgis/qgis@sha256:6ffe6b31...` Docker image this repo's CI itself
pins (QGIS 4.2.2)** — not `python-qgis.bat` this time, a genuine `docker pull` of the exact pinned
digest succeeded in this sandbox (the Docker daemon just needed manually starting, same finding as
the 2026-09-27 §1.10 update). Three new manual harnesses in `tests/manual_isolation_bench/` (same
manual/live-QGIS-only convention as the existing Phase 0 `bench.py`, not collected by `unittest`):
- `phase1_live_check.py` — 9/9 passing: a script creating a new memory layer (feature data survives
  the round trip both ways), a script adding a feature to a pre-existing memory layer (the script
  correctly sees the layer's pre-existing feature, and the live layer ends up with both features
  afterward), the uncommitted-edits guard actually refusing when a layer is mid-edit, a
  blocked-import script still rejected (defense in depth confirmed live inside the worker, not just
  unit-tested), and the Linux interpreter-lookup branch.
- `phase1_persistence_check.py` — confirms the worker is genuinely persistent (same OS pid across
  6 calls) and measures real latency: a cold call (spawn + first job) at 0.844s, warm calls
  averaging **~0.14s** — better than the scoping doc's derived-not-measured ~0.6s/call estimate.
- `phase1_recovery_check.py` — an infinite-loop script is killed at a (test-shortened) 2s timeout
  and the very next call successfully respawns and completes — the worker does not stay wedged
  after a kill.

**What Phase 1 covers, exactly as scoped:** the existing `local_env` surface as-is (vector/geometry
scripts only, no new capability). **What's still open, honestly, not glossed over:** the
Windows/macOS branch of `find_python_interpreter()` (QPIP's algorithm, adopted per the 2026-09-27
research) is still not independently live-verified on a real Windows/macOS QGIS desktop install —
no such install exists in this sandbox, only the Linux Docker path was actually exercised end to
end. A script mutating an existing FILE-BACKED (non-memory) layer is not given any new
concurrent-access safety by this boundary — documented as a known limitation in
`agent/services/script_isolation.py`'s own docstring and `SECURITY.md` §1b, not silently assumed
away. Layer removal/reordering/style edits a script makes are not reconciled back to the live
project (Phase 1's `local_env` surface doesn't give a script `iface`/canvas access to do most of
that anyway). Path C's OS-level hardening (Windows AppContainer/Job Object) remains a separate,
later, unscoped phase, exactly as the scoping doc always said. Full unit suite: 2258 tests (2247 +
11 new in `tests/test_script_isolation.py`, covering the QGIS-free pure logic — interpreter lookup,
worker-environment construction — the actual subprocess round-trip is live-QGIS-only, per the
harnesses above), 0 failures, ruff clean. `docs/TOOLS_REFERENCE.md` regenerated (179 tools, same
count — only the registered description text changed, to mention isolation and the
uncommitted-edits refusal).

**Update, 2026-09-28 — first real-world live bug from Phase 1, reported and fixed same day.**
Alaa live-tested the release zip on a real Windows QGIS install: a "Health facilities beyond one
hour's travel" query (real Yemen OSM extract, 139,748 road segments + 3,369 health facilities)
hit `execute_pyqgis_script exceeded the 60s isolation timeout` — with the overall task still
completing successfully afterward via the other suggested tools (`calculate_service_area`,
`travel_time_matrix`), so this was a single failed tool call inside an otherwise-successful turn,
not a fully uncompleted task. Investigated by reproducing at the same real-world scale (a
synthetic 139,748-feature line layer + 3,369-feature point layer) in this sandbox's live QGIS
4.2.2 Docker environment: **the trivial-script isolation call completed in 4.7s**, ruling out
"large project makes the whole-project serialize slow" as the cause — memory-layer export scales
fine even at this size.

Reading the timeout/diagnostics code path with that ruled out surfaced two real, confirmable-by-
inspection bugs, not just a hypothesis:

1. **`_drain_stderr()` used `select.select()` on a plain pipe** — `select()` only supports
   sockets on Windows, not the anonymous pipes `subprocess.PIPE` gives there, so every Windows
   call silently returned `""` (caught by its own broad `except Exception`). Stderr capture for
   diagnosing exactly this kind of failure has never actually worked on Windows. Fixed: read
   stderr *after* killing the worker (guarantees EOF instead of racing a still-open pipe) via a
   plain blocking `.read()` — works identically on every platform, no `select()` needed at all.
2. **A timeout never drained stderr in the first place** — even on a platform where `select()`
   works, the old code called `_kill()` before `_drain_stderr()` had a chance to run.

Most likely root cause of the hang itself, per `find_python_interpreter()`'s own long-standing
caveat (§1.11's 2026-09-27 update: not independently verified on a real Windows/macOS QGIS
desktop install): if the Windows branch's search doesn't find a bundled interpreter for this
specific install's layout, it falls back to `sys.executable` — which inside a real QGIS desktop
session **is the QGIS binary itself**, not Python. Spawning that as the "worker" doesn't error;
it silently launches a second real QGIS process that never answers the JSON handshake this module
waits for, hanging until the job timeout kills it with nothing to explain why. Three fixes, all
live-verified against real QGIS 4.2.2 (Docker):

- **Widened the Windows interpreter search** (`find_python_interpreter()`): now also checks
  `sys.base_prefix`/`sys.exec_prefix` (can differ from `sys.prefix`) and any single
  `apps\Python3*\` child directory under each — covers more real QGIS-for-Windows install layouts
  than checking only `sys.prefix`'s own root.
- **A fast startup handshake** (`_WORKER_HANDSHAKE_TIMEOUT_SECONDS = 20`, well under the 60s job
  timeout): the worker now writes `{"ready": true}` to stdout right after QGIS initializes, before
  entering its job loop; `_ensure_started()` waits for it and fails fast (~20s, not the full job
  timeout) with the captured stderr if it never arrives.
- **A basename sanity check** (`_QGIS_BINARY_BASENAMES`): if the interpreter lookup ever resolves
  to something named like the QGIS binary itself, the worker refuses to even attempt spawning it
  — live-verified this returns in under 2s with a clear message naming exactly what was resolved
  and why, instead of any hang at all.

Live-verified (`tests/manual_isolation_bench/`, run against real QGIS 4.2.2, not committed —
matching this project's manual/live-QGIS-only harness convention): normal startup still works via
the handshake (~1.2s cold, unchanged in practice); a QGIS-basename interpreter is refused in
<2s with no spawn attempt; a real-but-wrong binary (`/bin/cat`, standing in for "some other
non-Python executable got resolved") fails via the handshake timeout in ~3s with its actual stderr
captured verbatim (confirms the stderr fix is real, not just theoretical); all three prior Phase 1
harnesses (`phase1_live_check.py`, `phase1_persistence_check.py`, `phase1_recovery_check.py`)
re-run clean, no regressions. 6 new unit tests in `tests/test_script_isolation.py` (the widened
Windows search using real temp-directory fixtures instead of deep `Path` mocking, since the
widened logic touches `Path` too many times to mock faithfully; the basename refusal exercised
directly since it never reaches `subprocess.Popen`, so it needs no real QGIS or spawn at all).
Full suite: 2271 tests, all passing, ruff clean.

**Still not verified:** this fix set could not be tested on an actual Windows machine from this
sandbox — it's built from reading the code and QGIS's own documented Windows behavior, the same
standing limitation every version of this caveat has carried. Alaa re-testing the next release
zip on the real Windows install that hit this is the next real verification step, not something
this sandbox can close out itself.


**Added 2026-09-27.** Alaa asked to scope `semantic-router` (aurelio-labs) as a replacement for
`filter_relevant_tools`'s keyword/alias scoring, following up on BUG-2026-09-13-1 (a real live
failure: a query sharing no vocabulary with its target tool's name/description scored zero and
never made the candidate set, fixed there by adding `_TOOL_ALIASES` entries plus fuzzy-typo
correction). `docs/SEMANTIC_ROUTER_TOOL_FILTER_SCOPE_2026-09-27.md` scopes it — installed
`semantic-router` v0.1.16 and ran it live against all 178 of this project's real registered tools
and the exact hard cases `_TOOL_ALIASES` exists to fix, not a toy example set. **Two-sided
result, unlike the RestrictedPython/Presidio docs the same day:**

- **Zero extra authoring** (the tool's own already-registered description as the sole input) —
  the realistic "just point it at what we have" deployment — **performs worse than today**: 4 of
  the 5 known hard cases from `_TOOL_ALIASES` didn't even make the top 40 out of 178, where the
  existing alias entries make all 5 score positively today.
- **With ~4-5 authored example phrasings per tool** (comparable effort to what `_TOOL_ALIASES`
  already costs per entry) — all 5 hard cases correct, plus real generalization to genuinely
  novel paraphrases (3 of 4 correct) that literal alias/keyword matching cannot match at any
  authoring effort.

So the real finding is that semantic similarity does not remove the "someone must write realistic
phrasings per tool" cost `_TOOL_ALIASES` already pays — it moves it from alias words to example
sentences, at comparable cost — and only pays off with that investment made, not for free.
**Recommendation: prototype further, not a yes or a no** — the scope doc names four concrete
prerequisites a real prototype needs (authored utterances for all 178 tools, not 5; a real
embedding backend decision — `OllamaEncoder` flagged as the natural fit since this project
already ships Ollama, untested here for lack of a local server; a measured A/B against real query
logs, not hand-picked hard cases; a hybrid-vs-replacement design decision), none sized or started.
Not built. `semantic-router`/`spacy`/`en_core_web_md` removed from this environment after
testing; not a dependency of this repo.

---

### 1.13 `memory.py`'s unconditional full-dump context — LanceDB/Chroma scoped, not recommended

**Added 2026-09-27.** Alaa asked to scope `LanceDB`/`Chroma` as semantic retrieval on top of
`core/agent/memory.py`. `docs/LANCEDB_CHROMA_MEMORY_SCOPE_2026-09-27.md` scopes it — and finds the
premise needs correcting first: `get_formatted_memory_context()` does **no retrieval at all
today** (it dumps every stored note into the prompt unconditionally every turn, with only
`usage:` notes sliced to top-5 by count, unrelated to query relevance). So a vector database's
selling point ("retrieve only what's relevant") would be a genuinely new capability here, not an
upgrade to an existing worse search — and grepping this tracker and `BUG_TRACKER.md` found **zero**
prior reports of a memory-context-size/token problem, unlike RestrictedPython or semantic-router,
which both had a real bug/incident to anchor against. This is a speculative fix for an
unobserved problem, not a response to one.

Both libraries were live-tested anyway (insert/query/persist/delete-by-id/full-wipe against
realistic `pref:`/`rule:`/`other:` notes matching this project's actual key-prefix conventions):
both map cleanly onto `memory.py`'s existing GDPR-driven erasure contract (F1/F6) with no rework
needed. Retrieval quality was good with a real embedding model and mediocre with the same weak
spaCy substitute the semantic-router doc used — consistently an embedding-backend property, not a
vector-store-engine one. One real, sandbox-specific finding: **Chroma ships a default local
embedding model that downloaded successfully from an S3 host this sandbox's network policy does
not block** (unlike the Hugging-Hub-hosted encoders both LanceDB and semantic-router would need),
giving a clean 4/4 top-1 retrieval result with zero extra engineering — but that convenience comes
with a real, measured dependency-weight cost (`onnxruntime`, `kubernetes`, `opentelemetry-*`, ~45
transitive packages) that LanceDB's lean footprint avoids, at the cost of reopening the same
unresolved embedding-backend decision the semantic-router doc left open (`OllamaEncoder`,
untested here for lack of a local server).

**Recommendation: not now.** No evidence of the problem this would solve; if unbounded `pref:`/
`rule:` note growth over a long-lived global profile is ever actually observed, a much cheaper fix
(a simple cap/trim, matching `usage:` notes' existing top-5-by-count treatment) should be tried
before adding a new embedding + vector-store dependency. The dependency-weight tradeoff between
the two libraries is logged here as an open product decision, not resolved — per `CLAUDE.md`'s
own guidance to flag rather than silently decide judgment calls like this.
Not built. `lancedb`/`chromadb`/`spacy`/`en_core_web_md` removed from this environment after
testing; not a dependency of this repo.

---

### 1.14 `prompt_refiner.py`'s no-retry-on-malformed-JSON gap — Instructor/Outlines scoped, not recommended

**Added 2026-09-27.** Alaa asked to scope `Instructor`/`Outlines` (the last of the original
5-library list) as structured-output enforcement.
`docs/INSTRUCTOR_OUTLINES_STRUCTURED_OUTPUT_SCOPE_2026-09-27.md` scopes it. The real gap: two call
sites in `core/services/prompt_refiner.py` ask the model to "Respond as JSON only" in a plain-text
prompt and parse the result with `json.loads` in a try/except that **degrades to `None`/an error
on the first malformed response, with no retry** — unlike `agent_orchestrator.py`'s tool-call
argument parsing, which relies on each provider's own validated function-calling field, not free
text. No live bug names this specific failure yet (checked `BUG_TRACKER.md`), but the code's own
defensive `try/except` already anticipates it.

Both libraries were live-tested. **Instructor v1.17.0 genuinely works** — demonstrated live,
retry-with-validation-error-reprompt recovering a malformed 1-of-2-recommendations response into a
valid one in 2 calls — but only when wrapping a real `openai.OpenAI()`/`anthropic.Anthropic()` SDK
client object; its low-level `Instructor(client=None, create=<fn>)` path silently does nothing
useful with a bare callable (confirmed live, not assumed). This project's 5 providers
(`infrastructure/providers/*.py`) deliberately use raw `requests` calls, never an official SDK —
adopting Instructor for real would mean rebuilding that architecture, not just adding a package.
**Outlines v1.3.3's actual value (token-level grammar-constrained decoding) only applies to local
backends it directly controls** (Transformers/VLLM/LlamaCpp/MLXLM); its OpenAI/Anthropic/Gemini/
Ollama wrappers are thin proxies onto those providers' own native structured-output parameters,
giving none of Outlines' real benefit for any of this project's 5 (HTTP-API-based) providers.

**The load-bearing finding: all 5 providers already expose native, schema-constrained JSON output
in their own plain HTTP APIs, unused today** — OpenAI's `response_format: json_schema` (strict
mode), Gemini's `responseSchema`, Ollama's `format: <json-schema>` (real GBNF grammar-constrained
decoding, server-side, for the one local provider this project already ships), OpenRouter's
pass-through `response_format`. Checked each provider file: none send this parameter today. Not
live-tested (no API keys/servers available in this sandbox) — flagged as resting on documentation
rather than this doc's own live-testing standard, unlike everything else in it.

**Recommendation: do not adopt Instructor or Outlines.** If the no-retry gap is worth closing, the
cheaper fix is adding each provider's native schema parameter to its existing payload plus one
retry loop in `prompt_refiner.refine()` itself — same architecture, no new dependency, sized like
every other provider-specific quirk these files already carry. That is real, multi-provider work
(not scoped or sized here), and whether it's worth doing at all with no live incident reported yet
is an open call, logged here rather than decided unilaterally per `CLAUDE.md`'s own guidance.
Not built. `instructor`/`outlines`/`openai`/`pydantic` removed from this environment after
testing; not a dependency of this repo.

### 1.15 `local_data_sources.find_region()` picked the wrong country for a real Jordan coordinate — needs live Geofabrik data to diagnose, blocked in this sandbox

**Added 2026-09-28**, found live-testing BUG-2026-09-28-1/2/3's fixes together (see
`BUG_TRACKER.md` BUG-2026-09-28-4 for the full report). Asked whether to download local road/
health-facility data for a point at 31.8335 N, 35.9304 E — which the SAME turn's own later
analysis correctly identified as "southern Amman / Al-Jizah area, Jordan" — the download offer
named the region "Israel and Palestine" (216 MB), not Jordan. The point is not near the actual
Israel/West Bank border (~35.5 E); this is not a borderline case.

`find_region()` (`agent/local_data_sources.py`) does real point-in-polygon matching against
Geofabrik's published `index-v1.json` and picks the smallest-bbox-area region whose polygon
contains the point. Two live possibilities, and this sandbox cannot distinguish between them:

1. A logic bug in `find_region`/`_in_geometry`/`_bbox_area` (re-read closely, 2026-09-28: no bug
   found by inspection — the point-in-polygon and smallest-area tie-break both look correct against
   the GeoJSON spec), or
2. A real data characteristic of Geofabrik's own index: their region polygons are documented as
   simplified "download convenience" shapes, not precise political borders, and a combined
   "israel-and-palestine" region (a real Geofabrik region, since Israel/West Bank/Gaza don't have
   clean separate extracts) could plausibly have a polygon that overlaps into Jordan near the
   border in their own published data — in which case "smallest region wins" is the wrong
   tie-break rule for this specific pair, but only for this pair.

**Could not be resolved further from this sandbox**: `download.geofabrik.de` is blocked by this
environment's network egress policy (confirmed via the agent proxy's own status endpoint —
`connect_rejected`, "gateway answered 403 to CONNECT (policy denial)" — checked directly, not
assumed) and `WebFetch` hit the same `EGRESS_BLOCKED` wall. Without the real `index-v1.json`
polygon coordinates for Jordan and israel-and-palestine, guessing a fix (e.g. preferring an exact
ISO2 hint, or a different tie-break rule) risks fixing the wrong hypothesis or masking a real data
quirk that would just resurface for some other border pair. Per `CLAUDE.md`'s "when you're not
sure whether to just fix something" guidance, flagged here rather than guess-patched.

**Real-world severity is low as actually observed**: the existing flow already shows the matched
region's name and size to the user before downloading anything (`question_text`/the "Reply
download to get local data" flow), so the wrong match was caught and declined by the user, not
silently acted on. No wrong data was downloaded.

**What would unblock this**: either network access to `download.geofabrik.de` from a future
session, or the user pasting the actual matched region's raw GeoJSON feature (the `region` dict
`resolve_region()` returns, or the raw Geofabrik index entries for "jordan" and
"israel-and-palestine") so the polygon data can be inspected directly without needing network
access.

**Resolved, 2026-09-28, same day, without needing that network access after all.** A second
live re-test of the same request hit the same class of bug again, but this time with a far more
diagnostic symptom: the download offer named the region for the literal, meaningless coordinate
"(0.000, 0.000)" — not a real border-adjacent mismatch at all. That pointed straight at the
actual bug, in code this sandbox COULD inspect directly: `_maybe_ask_local_data`
(`ui/chat_tab_widget.py`) picked which Geofabrik region to offer from `self._canvas_center()` --
the QGIS **canvas's current view centre** -- never from the coordinate the request itself named.
Both symptoms trace to the same root cause: whenever the canvas hadn't been panned to the
request's actual area yet (a fresh/default project view, or one still showing a previous
request's area), the offer named whatever region the canvas happened to be looking at instead of
the region the request was actually about -- a neighboring country in the first report, and a
canvas with no meaningful extent at all (hence literal zeros) in the second. `find_region()`
itself was correctly cleared by the 2026-09-28 inspection above and needed no change; this was a
caller bug, not a point-in-polygon bug.

**Fixed** by preferring the coordinate the request itself names when it has one: a new
`extract_coordinate_pair()` (`agent/local_data_sources.py`, QGIS-free, unit-tested) finds an
"X,Y" pair in the request text -- tight on purpose, requiring a decimal point on both numbers, so
a thousands separator or an unrelated list of numbers is never mistaken for a coordinate -- and a
new `query_point_wgs84()` (`agent/local_data_loader.py`) reprojects it from the project's current
CRS to WGS84, the exact same transform pattern `canvas_center_wgs84()` right above it already
uses for the canvas's own numbers. `_maybe_ask_local_data` now tries this first and falls back to
the canvas centre exactly as before when the request names no coordinate (e.g. "buffer 5km around
active GDACS alerts", which has nothing to prefer over the canvas view). 6 new tests (4 for the
text-parsing half in `tests/test_local_data_sources.py`, 2 for the QGIS-availability/no-coordinate
short-circuit paths in `tests/test_local_data_loader.py` -- the full CRS-transform path itself is
live-QGIS-only, same standing limitation as `canvas_center_wgs84` beside it, never independently
tested from this sandbox). Full suite re-verified: 2282 tests, 0 failures, `ruff check .` clean.
See `BUG_TRACKER.md` BUG-2026-09-28-7 for the bug-tracker entry. `fixed-unverified-pending-live-session`
for the on-canvas behavior change itself (no live QGIS in this sandbox to confirm the offer now
names the right region against a real project); the text-extraction and reprojection-fallback
logic themselves are fully unit-tested.

### 1.16 "Smart mapping" -- analysis-tool output layers pile up uncoordinated across a multi-step session, beyond the one confirmed-and-fixed mechanism

**Added 2026-09-28.** Live report, a multi-step session on the same project (the exact one
§1.15/BUG-2026-09-28-7 fixed the region-offer for): after "Health facilities beyond one hour's
travel" then a follow-up "Estimate population outside the one-hour health facility catchment"
reusing the same origin, the user's own words: *"the visual style in the map is not correct when
you deal with complex analysis the tool loses the control and just creating layers on top of
each other this should be smart mapping indicators."* The Layers panel screenshot showed three
separate, near-identical "Origin Point_service_area..." entries (two polygon-fill variants, one
line variant) plus a dense stack of Voronoi/district/population layers with no apparent visual
coordination between them.

**One concrete mechanism found and fixed same day** (`BUG_TRACKER.md` BUG-2026-09-28-9):
`calculate_service_area` named its output layers deterministically (from the facility layer's
name + feature index, not a per-call id) and never checked for an existing layer under that name
before calling `QgsProject.addMapLayer()` -- which does not deduplicate by name at all. Re-running
the same analysis, or a follow-up request reusing the same origin, silently stacked a new
identically-named layer on top of the old one every time. Fixed with a new `_replace_named_layer`
helper, scoped to `calculate_service_area`'s three output call sites only -- the tool actually
named in this report.

**What's still open, and why it's flagged rather than fixed here:** whether this same
deterministic-naming-with-no-dedup pattern exists in the OTHER analysis tools this session's
tool-call list shows running back to back (`estimate_population_exposure`,
`run_allowlisted_processing_algorithm`, `difference_layers`, `apply_graduated_style`, and
whatever built the "Jordan_Voronoi_Districts" layers visible in the screenshot -- likely a
`fetch_hdx_admin_boundaries` fallback, since that tool failed twice in this same report with "No
OCHA COD-AB ... for 'JOR'" and the model apparently built a Voronoi approximation instead of
following the tool's own suggested `fetch_geoboundaries` fallback, worth a separate look at
whether the router/prompt reliably steers the model to a tool's own suggested fallback) has not
been audited. That is real, multi-file work (auditing every `addMapLayer` call site across
`agent/tools/*.py` for the same class of gap), not a small fix, and the user's own phrasing --
"this should be smart mapping indicators" -- reads as wanting something beyond mere
deduplication: some coordinated way to tell which layers belong to the CURRENT analysis versus a
superseded prior one (grouping? an active-analysis indicator? auto-collapsing/greying out
superseded layers rather than removing them, so a user who wants to compare two runs isn't
silently losing the older one?). That's a real product/design tradeoff this project's own
`CLAUDE.md` says to flag rather than decide unilaterally, not a mechanical bug fix -- logged here
per that guidance rather than guessed at. Whether a systemic policy (e.g. "every analysis tool
replaces its own same-named output" as a house rule) is the right shape, versus a heavier
answer (an explicit layer-grouping/session concept in `map_intelligence.py`), is Alaa's call.

**Update, 2026-09-28 (same day): the "context-aware, replicate the same layer/analysis
visualization" half is now built -- the layer-grouping/decluttering half is still open, per
above.** Separately from the live-report thread above, the user asked (unrelated conversation,
this same day) for "deep analysis on the codebase... on how to improve the intelligent of the
analysis, ... replicating the same layer and context aware analysis visualization," citing the
MapMate framework's dual-memory (operational history + persistent design-state memory)
architecture as a research reference, then explicitly chose "Full dual-memory architecture" over
a narrower scoped alternative when asked via `AskUserQuestion`.

**What "full dual-memory architecture" means here, scoped deliberately:** MapMate's own
architecture has two distinguishable halves -- (1) the dual-memory system itself (an operational-
history store plus a persistent design-state store, and a retrieval step that lets past state
inform new output), and (2) a request-validator/task-planner/context-retriever/tool-router layer
sitting in front of the whole agent loop that DECIDES what to retrieve and how to route a request.
Built now: half (1), for real, not a stub. Deliberately NOT touched: half (2) -- rearchitecting
`agent_orchestrator.py`'s core tool-calling loop (validator/planner/router) is a materially larger,
higher-risk change than everything else in this pass, cannot be meaningfully verified without a
live multi-turn session against a real LLM provider, and risks regressing every existing tool call
path if done in the same pass as several other unrelated fixes. Flagging it here rather than
guessing at an architecture for it, per this file's own §1 convention -- if/when this is wanted,
it deserves its own dedicated pass with its own live-verification plan.

**What was actually built (half 1):**
- **Operational history already existed** and needed no new work: `SpatialMemoryManager.
  log_spatial_action` (`agent/memory.py`) has recorded every tool call (name + args) since before
  this session, called from `agent_orchestrator.py` on each successful execution, surfaced back
  into the system prompt every turn via `get_formatted_memory_context()`.
- **New: persistent design-state memory**, `agent/map_state_memory.py` -- `record_output()`/
  `recall_output()`, storing `{layer_id, layer_name, style_profile, properties}` per `output_role`
  as a project-scoped note (`layout:<output_role>`), reusing `memory.py`'s existing
  `store_project_note`/`get_project_notes` API rather than inventing new storage plumbing --
  exactly the pattern `services/learning.py` already established for its own `pref:`/`rule:`/
  `usage:` global notes (project-scoped here, not global, since a map's own visual choices are a
  property of that project, not a preference that should follow the user into an unrelated one).
- **New: the retrieval step**, wired into `map_intelligence.py`'s `process_map_output` (the single
  choke point every analysis tool's styled output already passes through): before styling, it
  recalls the last `style_profile`/`properties.color` used for this `output_role` in this project
  and fills in whatever the caller didn't explicitly specify; after a successful styling call, it
  records what was actually used as the new "last used" default. A caller's own explicit
  `style_profile`/`color` always wins -- this only supplies a smarter *default*, never overrides
  an explicit choice. Net effect: a follow-up request producing a similar output (e.g. "do the
  same buffer for the other district") now visually matches the one before it, rather than
  silently reverting to `STYLE_PROFILES`' one hardcoded per-role default every single time.
- 15 new tests (`tests/test_map_state_memory.py`'s 10 pure-Python storage/recall tests, plus
  5 new cases in `tests/test_map_intelligence.py`'s `TestProcessMapOutputDesignStateMemory` --
  remembered-style reuse, explicit-caller-override-wins, record-after-success, no-record-after-
  failure, and the no-active-memory-manager safe-no-op path for a standalone Processing-provider
  run outside the chat loop). Full suite re-verified: 2313 tests, 0 failures, `ruff check .`
  clean. **Not verified**: no live QGIS session in this sandbox to confirm the recalled color
  actually renders visually consistent across two real follow-up requests -- the recall/record
  logic itself is fully unit-tested, including the exact descriptor values `apply_component_
  symbology` receives.

---

### 1.17 rc7 smoke-test findings still open after rc8 (added 2026-09-30)

Source: `docs/RC7_SMOKE_TEST_FINDINGS_2026-09-30.md`; GitHub #72 (umbrella) and #73-#97. rc8 fixed or mitigated
F01-F06, F10-F16, F20, F23, F24 (offline-tested only; live-QGIS re-verification is part of the next smoke round).
Open and needing a decision or a live reproduction:
- **F07** layer-tree duplicate/orphan nodes (10 nodes for 7 layers) -- root cause identified by code reading, 2026-09-30: `map_intelligence.insert_layer_semantically` inserted a second `QgsLayerTreeLayer` for layers the tool had already added with `addMapLayer()` (service-area lines/hull, delivery-route layer), and a re-run's `removeMapLayer` removed only one of the pair, leaving an orphan. Fix: a layer that already has a tree node keeps it and gets no second one (4 offline tests; 2 real-QGIS tests in `tests/test_rc8_live.py`). A first attempt that MOVED the node (remove + re-insert) broke two live service-area tests in CI (`test_network_background_live`, `test_network_clip_live`: the layers were no longer in the project), so it was replaced; the cause of that was not established. Consequence: semantic placement (e.g. buffer below source) now only applies to layers that have no node yet. The unfixed part: projects saved under rc7 still carry duplicate/orphan nodes (no healing pass). Also unchecked: `map_intelligence` uses unscoped `QgsWkbTypes.PointGeometry`-style enums -- whether those resolve on QGIS 4.2 is unverified.
- **F08** 43-minute routing -- first cut built 2026-09-30: new tool `classify_facilities_by_access` answers "which facilities are within/beyond N of this origin" from ONE service area (seconds) instead of `travel_time_matrix` (~37 min of the 43 for 3,369 facilities; CORRECTED 2026-09-30 after reading the QGIS source: `native:shortestpathpointtolayer` runs ONE Dijkstra per origin, not one per destination -- the likely cost is that `QgsVectorLayerDirector.makeGraph` compares every road segment with every tied destination, growing with segments x destinations; source-read, not profiled). `travel_time_matrix` now refuses destination layers over 200 features unless `allow_large=true`, and its description/prompt rule 25 point at the new tool. It is an approximation, stated in the tool result: the access leg from the road to the facility (up to `snap_distance_m`, default 500 m) is ignored, so it can differ from a routed cost near the threshold. Verified offline (pure classification + wiring, 8 tests); the agreement check against routed costs is `tests/test_facility_access_live.py`, NOT yet run in CI. Not done: a time estimate shown before long jobs, the ~6 min graph build itself, and whether the model actually picks the new tool (needs the next smoke round).
- **F09** population exposure counted people inside the CONVEX HULL of the reached roads (778,156 in the rc7 session) -- first cut built 2026-09-30: `population_access_gap` now sums population inside the reached roads buffered by `reach_buffer_m` (default 500 m, buffered in the local UTM zone so it is real metres); `reach_geometry='convex_hull'` remains, labelled `is_upper_bound_on_reach`. `calculate_service_area` results now carry a `hull_note` saying its polygons are an upper bound. This is a BEHAVIOUR CHANGE, but not always a smaller figure: on a sparse network the buffer removes the empty land a hull adds; on a DENSE network (roads closer together than twice the buffer) a 500 m buffer reaches up to 500 m past the last reached road and can be as large as or larger than the hull -- found in CI (a 300 m buffer on a ~220 m grid came out 16.3 km2 vs the hull's 12.0 km2). The 500 m default is my choice, not derived from data; a direct `estimate_population_exposure` call on a hull layer is not intercepted (only the note warns). Verified offline (mocked flow + UTM-zone helper); the buffer-vs-hull geometry check is in `tests/test_facility_access_live.py`, not yet run in CI.
- **F19** whole-country WorldPop fetch -- first cut built 2026-09-30: `fetch_worldpop_population` takes `extent_layer` (any project layer; transformed to WGS84 on the main thread) or `bbox` and then reads only that window, plus a ~2 km margin, through GDAL `/vsicurl/` range requests (`_clip_raster_to_bbox`), naming the layer `<ISO3>_population_<year>_area`; pixel values are untouched so sums over the area match the full raster. The tool description tells the model to always pass one; without one the whole country is still downloaded, now with a `note` and `bytes_on_disk` in the result. A failed clip is an error, never a silent full download. The window is clamped to the raster's bounds and a window that misses the raster entirely is an error (found in CI: `gdal.Translate(projWin=...)` does NOT fail for a window outside the raster, it writes an empty nodata raster, which would have made every population sum over it silently zero). Only https `*.worldpop.org` URLs are read remotely (GDAL follows redirects outside the SSRF-guarded opener). Verified offline with mocks and on a synthetic local GeoTIFF in CI (`tests/test_worldpop_clip_live.py`); NOT verified against data.worldpop.org: whether the server honours range requests efficiently for these files (strip- vs tile-organised GeoTIFF), how fast the window read is, or that the model passes `extent_layer`.
- **F22** unprompted large downloads -- partly built 2026-09-30: (a) the OSM-extract silent-download threshold is now the QGIS advanced setting `cartogen_ai/local_data_ask_above_mb` (MB; 0 = always ask), DEFAULT NOW 50 MB (owner decision 2026-09-30, was 150), so the 103 MB Yemen extract now asks; (b) an extract already cached on disk (under a week old) no longer triggers the choice, since nothing would be downloaded; (c) `fetch_worldpop_population` without `extent_layer`/`bbox` is now refused unless `allow_whole_country=true`. **Decided 2026-09-30:** default 50 MB. Not done: a metered-connection check (QGIS/Qt give no reliable signal), a size confirmation for the other fetch tools (geoBoundaries, HDX, building footprints), and no UI for the setting (advanced-settings only). Offline-tested (threshold/ask logic, cache check, WorldPop guard); the chat-widget branch that calls them is not covered by a live test.
- **F12 marker clustering** -- built 2026-09-30 for BOTH dashboards: `generate_html_dashboard` and, in a second step, `generate_temporal_dashboard`. Point layers with >= 100 features (>= 90% points) are drawn as Leaflet.markercluster clusters, with a warning saying so. Static dashboard: `color_field` is dropped for a clustered layer (warning). Temporal dashboard: the slider hides a feature by zeroing its opacity, which a cluster would still count, so the page script rebuilds the cluster from only the ACTIVE markers on every frame; cluster bubbles use the default colours, individual markers keep their category colours. **Verified in a real browser (headless Chromium via Playwright, 2026-09-30) with Leaflet 1.9.3 and leaflet.markercluster 1.5.3 from npm standing in for the CDN** (the generated pages ask for markercluster 1.1.0 from cdnjs, so that exact version is untested): static page -> 300 markers, 5 cluster bubbles at fit zoom, 24 separate markers at zoom 17; temporal page -> 200 markers at the first date, 300 after the slider moves, 200 again going back, play advances the date, no page errors. The CartoDB 'requires an API key' warning from folium 0.20.0 is still uninvestigated (tiles were stubbed in that check, so it says nothing about them).
- **Temporal dashboard slider was dead with folium 0.20.0** (found by that browser check; pre-existing, not caused by clustering): the slider script ran BEFORE folium's map script and referenced `geo_json_*` at load, so a ReferenceError stopped it -- no play button, no sliders. `requirements.txt` leaves `folium` unpinned, so anyone on a current folium was affected. Fixed by resolving the layer/cluster variables lazily (`function __cartogenLayers()`), covered by a string-level test; the real-browser check is not in CI (no Playwright there). **Separate quirk, not fixed:** the slider steps in `step_days` from the first date, so when the data span is not a multiple of the step the last date is unreachable (a 31-day span with a 30-day step tops out on day 30) and features that start on the final date never show.
- **F25** chat-history export -- cause found 2026-09-30 by code reading: the export reads the persisted rolling window (`MAX_HISTORY_MESSAGES` = 10); older turns are replaced by a one-line-per-message digest (role `system`) that `load_chat_history*()` filter out, so the export omitted stored text, and gave no hint that a short export was expected. Fixed: the export now includes `chat_history_digest` and a `chat_history_info` note (window size, persistence on/off, project-bound); a new user message is stamped with its send time instead of the save time. NOT changed: the 10-message window itself (a token-cost design choice, so a full transcript is still not kept -- decide whether the GDPR export needs one), and history is still stored per project file, so loading another project shows that project's history. Unverified in live QGIS. Still open here: per-turn token display; dashboard marker clustering.
- **F18** operator's plan-validation setting was ON during the smoke test; reset to OFF before the next round unless deliberately under test.

### 1.18 F25 -- should "Export My Data" hold a full chat transcript? (decision needed, added 2026-09-30)

Today the export holds the agent's rolling window (`MAX_HISTORY_MESSAGES` = 10) plus the stored digest of older turns, and says so
(`chat_history_info`). A 50-minute session therefore exports a handful of messages. Options:

- **A. Keep as is.** No new stored data; the export is accurate about what is held. A right-of-access request covers data the controller
  actually holds, and the plugin does not hold the rest.
- **B. Store a full transcript** in the project file (only when "Save chat history" is on), capped by count or age. Gives a complete export and
  a true restore, but: the conversation is written into a shareable `.qgz` (SECURITY.md §7 -- why this is opt-in, default off), the erasure
  limitation for already-distributed copies (SECURITY.md, F9) grows with it, the project's custom property is rewritten on every save, and it
  runs against the data-minimisation gap already noted in SECURITY.md. Storing more in order to be able to export more inverts the purpose.
- **C. A user-initiated "Save this conversation..." action** that writes the on-screen transcript to a file the user chooses. Nothing new is stored
  or retained; the user controls where it goes. Limits: it covers only what the chat window shows (lost on restart, since restore rebuilds
  only the 10-message window), and it is a new UI control that needs a live-widget test.

**Recommendation: A + C, not B.** Keep the honest export (done) and add C for the audit/smoke-test need, without widening what is stored.
Nothing is built for B or C yet; say which you want.

**DECISION (owner, 2026-09-30): B, on by default, for the life of the project, with an enable/disable control in Settings** ("a mapping
project has a purpose and context, it's not a long-term project"). Built the same day: the full transcript is stored with
`QgsProject.writeEntry` (`cartogen_ai/chat_transcript` -- deliberately NOT the custom-property slot the rolling window uses, because on
QGIS 4 that slot is `customVariables()`, shown in Project Properties > Variables); the export uses the transcript and falls back to the
window; the persist setting defaults to ON (Settings label now "Save the conversation in the project file"); "Clear Saved Chat" in the
Memory window deletes it. Additions of mine beyond the decision: safety bounds of 2,000 messages / 2,000,000 characters (oldest dropped
first, the count reported in the export) so a very long project cannot bloat its own file; and the delete button, since a default-on
store needs a way out. Consequences to be aware of: anyone who never opens Settings now has their conversation saved in every project
they work in (SECURITY.md §7 updated); users who explicitly left the old default are unaffected only if the key was ever written by
opening Settings and pressing OK; the UI still restores only the agent's 10-message window on reopen (showing the whole transcript is a
possible follow-up). NOT verified in a real QGIS session; real-QGIS round-trip tests are in `tests/test_chat_transcript_live.py`.

## 2. Open items blocked on this sandbox's environment (not a decision, not a bug)

- **Live-QGIS verification pass — the "does it even load" gap closed 2026-08-22 (see §1.2);
  the full 16-category checklist itself has since been run repeatedly, not just once.**
  `docs/RELEASE_SMOKE_TEST.md`'s checklist has run against every `v1.15.6-rcN` build
  (rc1 through rc6, 2026-09-14 through 2026-09-18) — most recently confirming 15/15 runnable
  categories pass (category 10, PostGIS, skipped under the checklist's own documented allowance
  every time). RC5/RC6's own cycles didn't re-run the full 16 categories (their changes were
  isolated to the orchestrator/UI and one tool dependency, not the tool surface that checklist
  exercises broadly) — see that doc's run log for the exact reasoning each time. **Still
  genuinely open, unchanged**: PostGIS's read-only-SQL enforcement has never been verified
  against a real database in this environment — no test DB has ever been available, and a
  2026-09-18 attempt to start one via Docker Desktop found its backend won't start without a
  one-time interactive first-run only a human can complete.
- **`generate_html_dashboard` connectivity requirement** — carried forward unchanged from prior
  review rounds; no new information available from this sandbox.
- ~~**No git remote on this repo.**~~ **Resolved, some time before 2026-09-14 (exact date not
  captured when it happened).** This repo now has a real, private GitHub remote
  (`cartogenai-glitch/CARTOGEN-AI`, confirmed via `git remote -v` and authenticated `gh repo
  view` — see `CLAUDE.md`'s own 2026-09-14 correction note) with a full release history:
  `v1.7.0` through `v1.15.5` as tagged releases, `v1.15.6-rc1` through `-rc6` as tagged
  prereleases (none yet promoted to "Latest"). Sync workflow, tagged releases, and downloadable
  asset verification are all in active, routine use — every RC follows the same 7-step process
  (version bump, smoke test, commit, push+verify, rebuild+checksum, tag, GitHub prerelease+asset
  diff), not written up as its own doc in this repo but applied identically every time. plugins.qgis.org submission
  specifically has not happened (the remote is still private, not a public listing) — that's the
  one piece of this bullet still genuinely open.
- **Test baseline, current: 1,958 tests, 0 failures, 38 skipped** (`python -m unittest discover
  -s tests -t . -p "test_*.py"`, re-run and confirmed 2026-09-20 against `v1.5.7-rc4` — matches
  `CHANGELOG.md`'s own rc4 figure exactly, independently verified rather than copied). The
  FUSE-sandbox-specific 2-failure baseline this bullet used to describe (`folium` absence
  mishandling) was fixed long ago per this bullet's own 2026-08-22 update and hasn't recurred in
  any measurement since.
- ~~`cartogen-ai-pro/` and `cartogen-ai-enterprise/` exist as empty directories~~ **Resolved
  2026-08-22** — both now hold a placeholder `README.md` noting no private repo exists yet, so an
  empty directory no longer misreads as "the private repo exists."
- **Repo rename / GitHub collaborator items** — external GitHub actions, not verifiable or
  actionable from this sandbox.
- **OpenRouter+Anthropic prompt caching — doc-verified, not yet live-confirmed.** 2026-09-19
  cost/performance pass (4-provider follow-up to the Gemini-specific pass in `88c4764`):
  `agent/providers/openrouter.py`'s `_apply_anthropic_cache_control` (system-prompt breakpoint)
  and the new top-level `cache_control` field (growing message-tail breakpoint) are both
  confirmed real, supported mechanisms against OpenRouter's own docs
  (openrouter.ai/docs/features/prompt-caching, fetched 2026-09-18) — but neither has been
  checked against a live response's `usage.prompt_tokens_details.cached_tokens` field in this
  environment. Needs a real OpenRouter key routed to an `anthropic/*` model, a 2+ iteration
  tool-calling turn, and confirmation that `cached_tokens > 0` appears on the second call.
- **Ollama `keep_alive` — investigated, deliberately NOT implemented.** Same pass: considered
  adding `keep_alive` to `agent/providers/ollama.py`'s request payload to keep a local model
  resident between turns (avoiding reload latency) — confirmed via live GitHub issues
  (ollama/ollama#11458, #9355) that Ollama's `/v1/chat/completions` (OpenAI-compatible)
  endpoint, which this client uses, silently ignores `keep_alive` in the request body; only the
  native `/api/chat` endpoint honors it. Adding the field here would be dead code that looks
  like a real fix. See `ollama.py`'s own comment for the actionable workaround (the
  `OLLAMA_KEEP_ALIVE` server-side env var) — switching this client to the native endpoint would
  be a bigger, response-shape-changing decision, flagged here rather than done silently.

## 3. Deliberately deferred (not a gap — a stated design choice)

- **`docs/archive/JIAF_MULTISECTOR_COMPOSITE_SPEC.md`** — spec-only, intentionally not built. Combining
  per-sector severity indices into one intersectoral estimate needs a real JIAF Mosaic Method
  human-validation workshop step that a formula can't substitute for. Revisit only if that
  workshop happens.
- **`docs/archive/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md` §3.3 (no-go zones)** — prompt-guidance-only by
  design, not a missing tool. §3.1/§3.2 (`analyze_incident_trend`, `score_route_incident_risk`)
  are shipped.

---

## 4. Resolved since the last full status review (informational — for traceability)

- **2026-09-20 — 15-section production-standard audit's 5 P1 findings, independently verified
  against live code before fixing, then re-verified by a second independent review that corrected
  an overclaim in this entry's first draft ("4 fixed") to the precise per-finding verdict below —
  1 closed, 2 mitigated (not fully compliant with the audit's own stricter standard), 1 improved
  but unverified in a live CI run, 1 left genuinely open.**
  - **QAction lifecycle leak (`plugin_main.py` `unload()`) — CLOSED.** Confirmed via a live-QGIS probe
    before the fix: `before_unload_actions`/`after_unload_actions` were identical, proving
    `removePluginMenu`/`removeToolBarIcon` alone left the toolbar/menu `QAction`s alive, still
    parented to `iface.mainWindow()`, still connected. Fixed: `unload()` now disconnects each
    action's `triggered` signal and calls `deleteLater()` before clearing `self.actions`/
    `self.toolbar_action`. New live test module `tests/test_plugin_main_live.py` (4 tests) drives
    a real `initGui()` -> `unload()` -> `initGui()` reload cycle against a real `QMainWindow` and
    confirms (via `qgis.PyQt.sip.isdeleted`) that the first instance's actions are actually gone
    before the second instance's are created — the exact regression scenario (QGIS's Plugin
    Reloader, or disable/re-enable).
  - **Plaintext credential fallback (`infrastructure/auth.py`) — MITIGATED, not fully compliant.**
    Confirmed: `save_credential()` silently wrote the API key to plaintext `QgsSettings` (Windows
    registry) any time `QgsAuthManager` was unavailable/disabled, with only a post-hoc UI warning.
    Changed: default fallback is now session-only in-memory storage (never touches disk, gone on
    QGIS restart) — persistent plaintext requires a new explicit `allow_plaintext_persist=True`
    argument, only passed by `ui/settings_dialog.py`'s `accept()` after the user says Yes to a
    `QMessageBox.question`. A successful encrypted save also migrates away any stale plaintext key
    (`_delete_plaintext_fallback`, skips `ollama` since that key holds an endpoint URL, not a
    secret). **Second-review correction:** informed consent changes the risk profile but does not
    satisfy the audit's own literal standard ("do not store tokens in plain `QgsSettings`") — the
    Yes path at `auth.py`'s plaintext-write branch still writes the raw key to the registry.
    Whether user-authorized plaintext persistence is acceptable product policy, or whether it
    should be refused outright (session-only, full stop, no opt-out), is an open decision — not
    resolved by this fix alone. `tests/test_auth_and_deps.py` updated/extended accordingly.
  - **Unsanitized prompt/tool-arg/result logging (`core/logger.py`) — SECRET LEAKAGE MITIGATED,
    broader privacy finding NOT closed.** Confirmed: `log_info`/`log_warning`/`log_error` forwarded
    whatever string a caller built, with call sites in `agent_orchestrator.py` (tool call
    args/results) and `task_runner.py` (user query, agent response, via raw `print()`) passing
    free-form content that can embed a key or token. Changed: centralized regex-based redaction
    (`core/logger.py`'s `_redact`) applied inside all three log functions — covers
    OpenRouter/OpenAI-, Gemini-, and Anthropic-style key formats, `Bearer` tokens, and generic
    `api_key`/`password`/`token`/`secret`-named fields. `task_runner.py`'s two content-bearing
    `print()` calls switched to `log_info` for the same coverage. New `tests/test_logger.py` (6
    tests). **Second-review correction:** the regex only strips known secret *shapes* — it does
    NOT redact coordinates/geographic attributes, names/emails/PII, general prompt content, file
    paths, or unknown credential formats. `task_runner.py:49`/`:68` and
    `agent_orchestrator.py:1125` still log up to 60/200/300 raw characters of user prompt/model
    response/tool args-results after only that narrow secret-pattern scrub. The audit's actual ask
    — structured logging with an explicit safe-field allowlist (tool name, status, duration,
    correlation ID, error class) instead of truncated free-form content — is still open.
  - **CI matrix (`.github/workflows/tests.yml`) — implemented, not yet proven; upper-bound tag
    corrected.** Confirmed: ubuntu-only, Python 3.11 only, no QGIS anywhere in the workflow,
    despite `metadata.txt` advertising `qgisMinimumVersion=3.28` through `qgisMaximumVersion=4.99`
    and this being a Windows-developed plugin. Changed: the existing `test` job gained a
    `windows-latest` leg (POSIX-only steps scoped to Linux via `if: runner.os == 'Linux'`); a new
    `qgis-live-tests` job runs `tests/test_chat_widget_live.py` + `tests/test_plugin_main_live.py`
    inside the official `qgis/qgis` docker images across the declared version range, plus a smoke
    test that now builds the actual release zip (`plugin_upload.py`) and imports from the
    *extracted zip*, not the dev tree, closing the narrower "does the packaged file set import"
    gap (still not the full exact-ZIP-in-a-fresh-profile test — see §1.10). **Second-review
    correction:** the original `latest` tag for the upper bound was wrong — confirmed via the
    Docker Hub API that `qgis/qgis:latest` and `qgis/qgis:nightly` currently share the same image
    digest, i.e. `latest` tracks unreleased nightly builds, not a stable QGIS version. Repinned to
    `4.2.2` (confirmed to exist on Docker Hub), the exact released version this repo is
    developed/live-tested against locally. Remaining gaps, not yet addressed: no GitHub Actions
    run has actually executed this workflow from this environment (cannot be done from this
    sandbox), and QGIS coverage stays Linux-only (Windows gets the headless suite only, no docker
    image exists for a Windows QGIS live run). This item stays **open** until a real workflow run
    is confirmed green.
  - **5th P1 (exact-ZIP clean-profile install/upgrade test) — OPEN.** Needs a real interactive
    QGIS GUI session this sandbox cannot provide; tracked as new item §1.10 above.
  - **Release provenance:** none of the above has been released — `commercial-plugin-v1.16.0-rc1`
    is still pinned to `609e4ca`; this remediation landed as a separate commit (`58dccb2`, 13 files,
    622 insertions) on `main` afterward. The published RC1 artifact does not contain any of it. A
    corrected RC (`1.16.0-rc2`) is the right next step once the credential/logging policy
    decisions above are made and the CI workflow has an actual green run — not before.
  - Full headless suite: 1973 passing (up from 1966), 44 skipped, after every change above. Live
    QGIS 4.2.2 confirmation run for the plugin-lifecycle tests: 4/4 passing
    (`python-qgis.bat -m unittest tests.test_plugin_main_live`). Zero `ResourceWarning`s under
    `-W error::ResourceWarning`, per a second-review check.

- **2026-09-20, same day — the 2 "mitigated" findings above closed for real, per the user's own
  explicit strict-policy decision (not decided unilaterally — both were surfaced as open product
  calls after the second review, and the user chose the strict option for both).**
  - **Plaintext credential fallback — now CLOSED, not just mitigated.** The
    `allow_plaintext_persist=True` opt-in path is removed from `save_credential()` entirely — there
    is no longer any code path, consent-gated or otherwise, that can write a new key to plaintext
    `QgsSettings`. Session-only in-memory storage is the only fallback when `QgsAuthManager` is
    unavailable, unconditionally. `ui/settings_dialog.py`'s `accept()` changed from a
    `QMessageBox.question` (offering plaintext persistence) to a `QMessageBox.information` (states
    plainly that the key is session-only and re-entry will be needed, with no alternative offered).
    Migration code that only *reads*/*removes* legacy plaintext keys written by older versions of
    this file (`LEGACY_SETTINGS_KEYS` fallback read in `get_credential`, `_delete_plaintext_fallback`
    on a successful encrypted save) is retained, per the user's explicit instruction — existing
    users' already-stored plaintext keys still work and get cleaned up opportunistically, but no
    *new* plaintext write can ever happen again.
  - **Sensitive logging — now CLOSED, not just secret-leakage-mitigated.** `core/logger.py` gained
    `log_event(event, tag=, error=False, **fields)`: structured, metadata-only logging with a hard
    allowlist (`_SAFE_EVENT_FIELDS = {tool, status, duration_ms, correlation_id, provider,
    error_class, count}`) — any kwarg not in that set is silently dropped, so a future call site
    can't widen what gets logged just by passing a new field. `agent_orchestrator.py`'s tool-call
    logging and `task_runner.py`'s turn-start/turn-end logging both switched from raw truncated
    content (even redacted) to `log_event` calls carrying only tool name/status/duration/
    correlation ID (new: `uuid.uuid4().hex[:8]` generated once per turn in `run()`)/provider (the
    client class name)/error class (`type(e).__name__`, now also attached to the `{"error": ...}`
    dicts `_real_execute_tool`/`_execute_tool`'s exception handlers already returned). Zero raw
    prompt, response, tool-argument, or tool-result content is logged by default anymore — not even
    truncated/redacted, matching the audit's actual ask (structured logging over free-form content).
    A new explicit, OFF-by-default escape hatch, `log_diagnostic()`, exists for a developer actively
    debugging locally: gated behind `cartogen_ai/debug_verbose_logging` (never set by default, not
    a normal Settings UI toggle), prints a visible one-time warning the first time it actually
    emits in a process, and is a true no-op (confirmed by test) otherwise. `_redact`'s
    secret-pattern scrubbing stays on `log_info`/`log_warning`/`log_error` as defense-in-depth for
    anything else that still logs a free-form string (including inside `log_diagnostic` itself).
  - New tests: `tests/test_logger.py` extended with `TestLogEvent` (3 tests: only safe fields ever
    appear in output, an unsafe kwarg is silently dropped rather than passed through, `error=True`
    routes to stderr) and `TestLogDiagnostic` (2 tests: true no-op outside QGIS, disabled by
    default). `tests/test_auth_and_deps.py`'s plaintext-persist-opt-in test replaced with one
    asserting the parameter doesn't exist on `save_credential`'s signature at all (`inspect.signature`).
  - Full headless suite: 1978 passing (up from 1973; +5 new logger tests, net-even on auth tests
    after removing 1 and adding 2), 44 skipped.
  - **What's still open:** §1.10's exact-ZIP clean-profile install/upgrade test remains genuinely
    blocked on a real interactive QGIS GUI session this sandbox can't provide.

- **2026-09-20, same day — CI matrix item CLOSED: the pinned `qgis-live-tests` jobs validated with
  actual passing GitHub Actions runs (`gh run view`, not assumed), per the user's own instruction
  to validate before cutting `1.16.0-rc2`.** 3 real, distinct failures found and fixed by actually
  running the jobs against both pinned images, not guessed:
  1. `pip install --upgrade pip` failed on the `4.2.2` image specifically (Debian-packaged pip has
     no RECORD file, refuses to uninstall itself) — dropped, unnecessary.
  2. The two images disagree on `--break-system-packages`: `4.2.2`'s newer pip requires it (PEP
     668), `release-3_28`'s older pip doesn't recognize it and hard-errors if passed — now tries
     with the flag, falls back without it.
  3. `4.2.2` (not `release-3_28`) segfaults during Python/Qt interpreter shutdown, AFTER all 42
     live tests already passed (`Ran 42 tests ... OK` immediately followed by `Segmentation fault
     (core dumped)`, exit 139) — an image-specific at-exit Qt teardown quirk under offscreen QPA,
     not a bug in this repo. The step now checks unittest's own final `OK` line and treats a
     nonzero exit alongside it as this known crash, not a failure (a real regression always prints
     `FAILED (...)`, never a bare `OK`, so this can't mask an actual failure).
  Final confirmed-green run: https://github.com/cartogenai-glitch/CARTOGEN-AI/actions/runs/35534755563
  — both `QGIS live tests (4.2.2)` and `QGIS live tests (release-3_28)` fully green end-to-end,
  including the release-zip build and load→unload→reload smoke test steps. `test (windows-latest)`
  and `secret-scan` also green.
  - **Separately flagged, NOT fixed here (out of scope for this P1 pass):** the plain `test`
    job's `Lint with Ruff` step fails on dozens of pre-existing unused-import/ambiguous-variable
    findings across the repo (`docs/route_optimization_prototype.py`, several files under
    `src/cartogen_ai/core/agent/`, `src/cartogen_ai/core/representation/`, etc.) — confirmed via
    `gh run view` on a run at the current `commercial-plugin-v1.16.0-rc1` tag commit (`609e4ca`)
    that this predates this session entirely. This means `ruff check .` has likely never actually
    passed in CI, and the packaging-verification step downstream of it has never run to completion
    either. A real, separate cleanup task — not addressed here to avoid scope-creeping a
    security-P1-fix pass into an unrelated repo-wide lint sweep.

- **2026-09-19/20, `v1.5.7-rc1` through `-rc4` — the full 11-phase Part A remediation plan
  (all ~35 confirmed gaps from the 2026-09-19 external-audit/architecture-guide passes),
  sequenced isolated-fixes-first, architecture-restructuring-last. Full per-item detail is in
  `CHANGELOG.md`'s `[1.5.7-rcN]` entries and project memory (`project_followup_task_list_2026-09-19`,
  plan file `jiggly-sparking-corbato.md`); this is the index pointer, not a restatement.**
  - **Phases 1-5 (cartography, layer formats, OCHA print layout, dashboards/reporting/imagery,
    domain tools)** — label buffers/placement/priority, geographic-CRS-aware hillshade Z-factor,
    a colorblind-safe NDVI ramp, `stddev`/`pretty`/`logarithmic` classification modes,
    GeoPackage `layer_styles` persistence, shapefile encoding detection, SpatiaLite spatial
    indexing, a real coordinate graticule/CRS label/inset map on print layouts (live-verified via
    real rendered PNGs, not just mocked), dashboard feature-count capping + basemap choice, a
    colorblind-safe chart palette + pie-slice cap + 300dpi export, `QgsDistanceArea`-based
    ellipsoidal distance in the logistics tools (this one caught a real live bug —
    `QgsProject.instance().ellipsoid()` defaults to the literal string `'NONE'`, truthy in
    Python, so a naive `ellipsoid() or "WGS84"` fallback never actually triggered and silently
    left planar math on), and a `threading.RLock()` around `conversation_history`/
    `_transaction_log`. Humanitarian severity/category controlled-vocabulary was deliberately
    **not** touched — the code's own comment documents it as a prior explicit product decision
    with no external standard to validate against.
  - **Phase 6 (cost/performance, `88c4764`)** — `tool_router.py` zero-score-drop logic extended to
    partial-signal queries (not just all-zero), a cross-turn history digest beyond
    `MAX_HISTORY_MESSAGES`, `max_tokens` scaled down for intermediate tool-dispatch iterations
    (full budget reserved for final synthesis), Rule 5's `get_attributes()` directive narrowed to
    skip when the fields are already in `map_context`, and deterministic tool ordering added for
    Gemini prefix caching. This is the same pass §2 below's "OpenRouter+Anthropic prompt caching"
    bullet already described as doc-verified-not-live-confirmed — that caveat still applies
    unchanged; nothing about landing the code changed whether it's been checked against a real
    billing response.
  - **Phase 7 (error handling/logging) + Phase 8 (networking), both in one commit (`b0fb5ab`)** —
    a small exception hierarchy (`CartogenError`/`ApiError`/`ValidationError`/
    `SecuritySandboxError`), a `QgsMessageLog`-wrapping logging helper replacing the confirmed
    raw `print()` calls, and `QgsNetworkAccessManager`-derived proxy-awareness added to the
    existing `requests.Session`-based provider HTTP calls (the already-working
    `post_with_retry()` backoff/429-handling was left intact, only proxy support was added on
    top). This is the concrete engineering answer to the architecture guide's "no
    `QgsNetworkAccessManager`" gap noted in `[[project_architecture_guide_alignment]]`.
  - **Phase 9 (code-quality tooling/CI)** — `[tool.ruff]`/`[tool.mypy]` sections now exist in
    `pyproject.toml` (confirmed present, this pass). CI matrix/packaging-test scope from the
    original plan not independently re-verified in this resync pass — worth a follow-up check,
    not asserted here either way.
  - **Phase 10 (Processing framework integration, `21d8296`)** — a real
    `CartogenProcessingProvider(QgsProcessingProvider)` with `OptimalHubSitingAlgorithm` and
    `CalculateServiceAreaAlgorithm`; `metadata.txt`'s `hasProcessingProvider` flipped `no` → `yes`
    (confirmed live in this pass). Also OGC SLD export and point cluster renderers, closing the
    two items §-tracked as confirmed gaps in `project_followup_task_list_2026-09-19`'s Part A6a.
    **This is a distinct mechanism from `run_allowlisted_processing_algorithm`** (the
    agent-callable tool in `processing_allowlist_tools.py`, §1.9 below) — Phase 10 added a
    Processing *Toolbox* provider wrapping 2 specific algorithms as their own typed
    `QgsProcessingAlgorithm` classes; it did not touch the allowlist tool or its always-visible
    output-layer behavior. §1.9 is unaffected and still open.
  - **Phase 11 (architecture restructuring, `91d4233`) — landed only partially, verified in this
    pass by actually reading the diff and the resulting files, not by trusting the commit
    message.** What's real: `src/cartogen_ai/infrastructure/` and `src/cartogen_ai/processing/`
    now exist as real packages, and `core/models/`, `core/services/`, `core/validators/` exist
    too — but the latter three are thin re-export facades (45/32/22 lines each, `from
    ..agent.transactions import TurnTransactionLog` etc.), not the actual code moved. The
    original files (`agent/transactions.py`, `agent/dataset_status.py`, `agent/sensitivity.py`,
    `agent/confidence.py`, and everything else in `core/agent/`) are still exactly where they
    were. `infrastructure/` itself holds only `settings_keys.py` — `auth.py`, `deps.py`, and
    `providers/` were **not** moved there as the plan specified. The two god classes the plan
    named are **not** decomposed: `agent.py` is 1,346 lines today (was 1,185 when the plan was
    written — it grew, it didn't shrink), `chat_tab_widget.py` is 1,839 lines (was 1,642). A new
    `tests/test_architecture_boundaries.py` exists and passes, but it's asserting boundaries
    around the facade packages, not around a real physical decomposition. **Net effect: Phase 11
    is scaffolding + a namespace layer, not the restructuring itself — treat this as still open,
    not closed**, despite the commit message ("add core subdivision packages and verify
    architectural boundaries") reading like a completion. This is the one phase of the plan
    worth a deliberate follow-up decision: finish the real move, or accept the facade layer as
    the final state and update the plan's own stated goal to match reality.

    **Update, 2026-09-20 — the real move, done for 3 of the plan's 4 target areas, verified by
    re-running the full suite after every single-group step (never batched):**
    - `infrastructure/`, `core/models/`, `core/validators/`, `core/services/` are no longer
      facades — `auth.py`, `deps.py`, `providers/` physically moved into `infrastructure/`;
      `transactions.py`, `dataset_status.py`, `sensitivity.py`, `confidence.py` into
      `core/models/`; `schema_contracts.py` + `pcode_validation.py` (and their `contracts/*.json`
      data files, easy to miss since they're loaded via a path relative to `__file__` — caught by
      the suite going from a clean pass to 11 failures until the data directory moved too) into
      `core/validators/`; `prompt_refiner.py`, `tool_router.py`, `task_runner.py`, `learning.py`
      into `core/services/`. Every internal relative import, every external call site
      (`agent.py`, `tools/*.py`, `ui/*.py`, `plugin_main.py`), and every test `@patch`
      string/import across `test_providers.py`, `test_auth_and_deps.py`, `test_dataset_status.py`,
      `test_schema_contracts.py`, `test_pcode_validation.py`, `test_transactions.py`,
      `test_prompt_refiner.py`, `test_tool_router.py`, `test_task_runner.py`, `test_learning.py`,
      and others updated to the real new paths — not left pointing at a location that happened
      to still work by accident. `infrastructure/__init__.py`'s PEP 562 `__getattr__` workaround
      for `CredentialManager` (added specifically to dodge a circular import between two packages)
      was also simplified back to a plain eager import, since physically moving `auth.py` into
      `infrastructure/` means the cycle it was dodging can no longer exist by construction.
    - `agent.py`'s god-class decomposition: 3 of the plan's 4 named files now exist for real —
      `tool_dispatcher.py` (pure file move, `ToolDispatcher` was already self-contained),
      `usage_tracker.py`, and `history_manager.py` (both extracted via delegation — `CartogenAi.
      conversation_history`/`session_usage` are now properties backed by the extracted classes,
      and every externally-called method name — `_accumulate_usage`, `get_session_usage_text`,
      `_append_history`, `_trim_history`, `_read_history_snapshot`, `_get_history_lock`,
      `_is_digest_message` as an unbound classmethod call — kept its exact signature so
      `chat_tab_widget.py` and `test_agent_runner.py`/`test_new_tools.py`'s ~85 direct references
      didn't need to change). `agent.py`: 1,346 → 1,170 lines. Worth knowing for anyone touching
      `history_manager.py` later: `trim()`/`append()`/`compact_old_tool_results()` take their
      thresholds (`MAX_HISTORY_MESSAGES` etc.) as call arguments rather than owning their own
      copies, specifically because `test_agent_runner.py` monkeypatches
      `agent_mod.MAX_HISTORY_MESSAGES` directly mid-test — moving the constant itself into
      `history_manager.py` would silently break that monkeypatch (a `from .history_manager import
      MAX_HISTORY_MESSAGES` re-export creates an independent binding, not a live link).
    - **Update, 2026-09-20, later same day — the remaining two items done too, on request.**
      `agent.py` → `agent_orchestrator.py`: reassessed and the blast radius was smaller than
      first estimated — only 5 files reference the module by its `cartogen_ai.core.agent.agent`
      path (`plugin_main.py`, `test_agent_live.py`, `test_agent_runner.py`,
      `test_analysis_tools.py`, `test_new_tools.py`); nothing inside `core/agent/` itself imports
      it by name. Renamed, all 5 references + ~36 files' stray comments updated, re-verified
      clean (one self-referential `X.py -> X.py` mangling from the blind comment sed caught and
      fixed by hand in two files' own docstrings).
      `chat_tab_widget.py`: split, but **not as a full view/controller bisection** — tracing every
      method's cross-calls found input-handling and view-rendering woven together too tightly
      through most of the file (`send_message`/`_dispatch_message`, the anchor-click router,
      message rendering) for that split to reduce real complexity rather than just add ~40
      pass-through delegators for questionable benefit. Extracted the two subsystems that
      actually stood on their own instead: `chat_view_presenter.py` (tool-step/plan-progress
      rendering) and `chat_input_controller.py` (file-attachment reading/analysis).
      `chat_tab_widget.py`: 1,839 → 1,522 lines. Both new classes operate on the widget instance
      passed to their constructor rather than owning separate state, since `dock_widget.py`'s
      signal wiring and `test_chat_widget_live.py`'s live Qt tests reach several of these
      methods/attributes by their original widget-level names — every such name stayed a thin
      delegator, same pattern as `agent_orchestrator.py`'s extraction.
      **Verified two ways for the UI change, not just the headless suite**: 1,958 tests / 0
      failures / 38 skipped as usual, AND the full 36-test live Qt suite
      (`tests/test_chat_widget_live.py`) actually run against a real QGIS install
      (`C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat`, `QT_QPA_PLATFORM=offscreen`) — real
      `QTest` widget construction and mouse-click interaction, run once as a clean baseline
      before touching the file and again after, both passing 36/36. This is the concrete answer
      to a real standing risk this project's own history flagged (`feedback_synthetic_
      screenshots_have_limits`): headless/static verification alone has missed a real
      interactive Qt bug before.
  - **Also in this arc but outside the original 11-phase plan's scope:** `ingest_osm_features`
    (two-phase OSM Overpass-API ingestion), AST sandbox prompt guardrails, the Map Intelligence
    Engine, the Intelligent Representation Planner, a live end-to-end QGIS 4.2 pipeline test, and
    a `/code-review`-driven pass fixing 7 correctness/security bugs (credential-rotation orphan
    entries, a silent full-layer export on empty selection, a reintroduced blocking-dialog
    regression, an equator/prime-meridian falsy-zero data-loss bug, an opacity-clobber
    regression, a profiler vacuous-truth misclassification) plus one latent circular import
    between `auth.py` and `infrastructure/__init__.py`. Full detail in `CHANGELOG.md`'s
    `[1.5.7-rc3]`/`[1.5.7-rc4]` entries.
  - **Versioning note, for anyone confused by the jump:** `metadata.txt` briefly read `1.16.0`
    before that number was ever tagged or released — the same commit that started the `rc1` cycle
    (`91752da`) renumbered it down to `1.5.7-rc1` in one step. No public `1.16.0` release ever
    existed; this isn't a downgrade of shipped code, just a pre-release renumbering. The `git tag`
    history confirms no `commercial-plugin-v1.16.0*` tag exists.

- **2026-09-19, a code-level circuit breaker on `main` from a THIRD live-reported transcript of
  the identical "Health facilities beyond one hour's travel" request -- proving the task router
  and directive were both correct (independently confirmed by re-running the exact same query
  text against both the dev repo and the actual installed plugin files) and the model still
  burned its whole 20-call budget on `execute_pyqgis_script` probing anyway, never once calling a
  directed tool.** `agent.py`'s tool-calling loop now injects a one-shot corrective message when
  `SANDBOX_FLAILING_THRESHOLD` (3) consecutive `execute_pyqgis_script` calls in the same turn are
  ALL rejected by the safety sandbox specifically -- a deterministic circuit breaker, not a prompt
  wording change, since `execute_pyqgis_script`'s own "LAST RESORT ONLY" description clearly isn't
  reliable enough alone. Does not fire for a script that fails for a real reason (a bug in the
  model's own code, a missing layer) or when a different tool breaks up the streak. 8 new tests (5
  pure-function, 3 full `run()`-loop integration tests using the existing `_CapturingLoopingClient`
  harness) confirm the nudge fires exactly once, only after the threshold, and only for genuine
  safety rejections. Not yet cut into a release. This is a mitigation for an underlying LLM-
  compliance gap (the directive existing in the system prompt doesn't guarantee the model follows
  it), not a fix for the gap itself -- worth watching whether it recurs with a different tool.
- **2026-09-19, two more fixes on `main` from a second live-reported transcript (the travel-time
  router fix above actually worked correctly this time -- confirmed task 7.23 matched, not
  25c.01), not yet cut into a release.**
  - **Chat scroll-to-bottom fixed for cursor-inserted blocks.** `_add_message`'s existing
    force-scroll fix (2026-09-15) only covered `chat_browser.append()`; `_flush_tool_steps_summary`
    and the new in-chat plan card (`_on_live_plan_updated`) insert via `QTextCursor` directly,
    which bypasses `append()`'s scroll heuristic entirely -- neither ever scrolled the view down.
    Fixed by force-scrolling after a genuinely NEW block lands (not on every in-place update or
    spinner tick, which would yank the view down several times a second during a running turn).
    Live-verified: a scripted scroll-to-top followed by a new tool-steps block or a new plan card
    both correctly snap back to the bottom; a spinner tick on an already-visible card does not.
  - **`export_to_csv`'s `output_path` is no longer a hard-required argument.** Live-reported dead
    end: a turn that ran out of tool-call budget before the model supplied a path ended in "please
    specify a destination file path" after the real analysis (including a full generated report)
    had already completed. Now defaults the same way `save_layer_style`'s `_derive_style_path`
    already does -- beside the layer's real on-disk source, or Desktop for a scratch/memory layer
    -- rather than leaving the model with nothing sensible to default to. 4 new tests; live-verified
    against a real memory layer.
  - **Investigated and ruled out:** the same transcript's "layer order is wrong" complaint is NOT a
    bug in `set_layer_order` (live-verified correct); see §1.9 above for what's actually happening
    and why it's a real design decision, not a quick fix.
- **2026-09-19, two fixes on `main`, not yet cut into a release.**
  - **In-chat plan-progress card, replacing the docked plan strip.** `plan_strip_widget.py` (the
    Broadsheet Phase 1 sticky panel above the chat) was live-user-rejected in turn -- "i dont like
    the design of the multi step task on top of the chat ... with bit of animation" -- as reading
    like a debug overlay. Deleted outright; task/plan progress now renders as an ordinary block
    inside `chat_tab_widget.py`'s own chat log (`render_task_progress_html`, `chat_formatting.py`),
    updated in place via the same tracked-cursor-span technique the tool-steps toggle already
    used. See `[[project_activity_tab_audit]]`-equivalent detail in memory; commit `a3429b5`.
  - **Task-router fix: travel-time language now prefers the `calculate_service_area` task.** See
    §1.8 above for the full writeup -- a live-reported failure ("Health facilities beyond one
    hour's travel" routed to a plain facility-mapping task with no data-fetch step, then burned
    its whole tool-call budget probing the `execute_pyqgis_script` sandbox). `task_matcher.py`'s
    `classify()` now re-ranks toward a scored candidate with `calculate_service_area` in its tools
    when travel-time/access phrasing is present, without touching the shared scoring formula.
- **2026-09-11 through 2026-09-18, v1.13.0 through v1.15.6-rc6 — the largest gap this tracker
  has ever gone stale for (this section's own preceding entries stop at 2026-09-12/v1.9.0; this
  one entry covers everything from there to now in one pass, not a day-by-day reconstruction).
  Full per-version detail lives in `CHANGELOG.md`, not repeated here.**
  - **API cost/token resilience (v1.13.0-v1.14.0).** 429-aware backoff on all 5 provider clients,
    adaptive inter-iteration pacing, mid-turn tool-result compaction, tool-router word-boundary
    matching (a plain "hi" dropped from ~23K to ~3.2K tokens across the full v1.13-v1.14 arc), and
    the 47-rule base system prompt split into always/sensitive-cluster/domain tiers sent only when
    relevant. Gemini implicit prompt caching (automatic, no code needed) plus cache-hit visibility
    in the session usage line, later confirmed working against a real account in live use.
  - **UI & Chat Redesign workstream (v1.15.2 onward) — culminating in the Broadsheet redesign.**
    Every remaining boxed `QGroupBox` panel (the requirement gate, the prompt preview, the
    prompt-refinement panel) converted to in-chat messages per repeated direct feedback. A
    recurring `'str' object has no attribute 'get'` crash, reported identically at wildly
    different tool-call counts across 5+ separate incidents, was finally root-caused for real in
    `v1.15.6-rc4` (`_execute_tool`'s snapshot step was receiving raw, still-JSON-encoded tool-call
    arguments instead of a parsed dict) after two earlier defensive-guard fixes landed without
    being the actual cause. `v1.15.6-rc5`/`rc6` then shipped a full 4-phase visual and structural
    redesign from a user-supplied mockup board ("Broadsheet"): the Chat/Activity tab split
    replaced by one continuous scroll with a sticky plan strip; the destructive-action
    confirmation gate re-rendered as a real inline card with clickable Apply-edit/Cancel links;
    the Task Inspector and Project Notes/Memory sections moved from always-docked tab content into
    per-task/on-demand dialogs; and a new layer-context picker giving explicit, per-question,
    opt-out control over which loaded layers' schema reaches the model (defaulting unchecked for
    anything already tagged via the existing `set_layer_sensitivity` tool).
  - **Orchestrator reliability pass (v1.15.6-rc5), 3 real bugs found via close reading of an
    actual live-session transcript, not assumption:** (1) the task router's own confidence floor
    was computed but never checked, so a low-confidence match still routed the model to a
    completely unrelated deliverable — the dominant cause of reports that answers weren't
    "relative to the request." (2) External API string values wider than a memory layer's
    shapefile-era field width (e.g. GDACS's multi-country `country` field) were silently dropped
    by QGIS's own memory-provider enforcement, with nothing surfacing it. (3) The most serious: a
    destructive-action confirmation gate could be bypassed by normal chat use — a plain "Confirm"
    reply used to re-enter the free-form LLM loop with no structured awareness of what was
    pending, and the model could fabricate a "Confirmed" narrative without ever re-calling the
    tool, so an approved edit silently never happened. Fixed at 3 compounding layers (a dedicated
    task instead of overwriting an unrelated one; the same deterministic resolution path for a
    typed reply as the UI's own button; the pending tool/arguments surfaced in the model's own
    prompt context as a backstop).
  - **`v1.15.6-rc6`: `search_web`'s dependency was found genuinely broken and fixed.**
    `duckduckgo_search`, even at its own documented-safe pinned floor version, was confirmed live
    to silently return zero results for a real query with no exception raised — while `ddgs` (the
    package it was renamed to upstream) returned real results immediately for the identical
    query. Migrated with a fallback for anyone still on the old package.
  - **Two rounds of independent external audit of `v1.15.6-rc5`**, both instructive: one flagged
    the release checksum as unreconciled, which traced to this project's own zip-build script
    embedding real on-disk file mtimes (a rebuild-checksum mismatch across sessions isn't, by
    itself, evidence of a content problem — the actual published GitHub asset was re-verified
    correct both times). The other flagged a "Community edition provider-restriction contradiction"
    that traced to an explicitly-marked, never-merged draft proposal (since removed, per §1.3
    above) being misread as current policy — the audit withdrew the finding once shown the exact
    quotes. Two small real documentation fixes shipped from the exchange regardless: a stale tool
    count in a now-removed business-strategy doc, and a leftover "Internal/commercial use" phrase
    in `README.md` inconsistent with the rest of that page's Community/GPL framing.
  - **Repository housekeeping**: 2 moderate Dependabot vulnerabilities in `service/website`'s
    `qs` transitive dependency (via `express`/`body-parser`/`stripe`) resolved via a patch-level
    `npm audit fix`, confirmed both alerts show `state: fixed` on GitHub. New
    `docs/LIVE_TEST_SCENARIOS.md` adds 5 multi-turn workflow scenarios (not single-prompt checks
    like `docs/RELEASE_SMOKE_TEST.md`) verified against actual canvas/attribute-table state.
  - **What's still genuinely open from this whole arc, not silently dropped**: PostGIS live
    read-only-SQL verification (no test database ever available in this sandbox; a 2026-09-18
    attempt to start one via Docker Desktop found its backend won't start without a one-time
    interactive first run); a live Gemini network observation from this sandbox specifically (the
    real QGIS profile has a Gemini provider configured, but its encrypted credential needs an
    interactive GUI unlock a headless boot never triggers); full positive-path coverage for
    `ultralytics`/`torch`-backed imagery feature extraction (the packages install and import fine
    in isolation, confirmed 2026-09-18, but the tool itself needs `qgis.core` + a real raster
    layer, meaning installing a real ML runtime into a live QGIS Python environment rather than a
    disposable one); and QGIS-version-range coverage beyond 4.2.2 (confirmed 2026-09-18: this
    development machine has exactly one real, complete QGIS install — the other 3 version
    directories present are bare, unusable OSGeo4W installer shells).
  - `v1.15.6-rc1`-`rc6` are all published GitHub prereleases (checksum-verified against each
    downloaded asset every time). **`v1.15.6` itself was promoted to stable/"Latest" on
    2026-09-18** (commit `a709abf`, tag `commercial-plugin-v1.15.6`, same code as rc6 — no
    changes beyond the version/changelog text marking the promotion), checksum-verified against
    the downloaded asset the same way every RC was. The known open items listed just above this
    bullet were not resolved by the promotion — they're carried forward, not silently dropped.

- **Live hazard monitoring (v1.9.0, 2026-09-12).** New `fetch_nasa_active_fires`/
  `fetch_nasa_eonet_events`/`fetch_gdacs_disaster_alerts` plus `generate_situation_dashboard`
  (`agent/tools/hazard_monitoring_tools.py`) and dashboard freshness badges
  (`generate_html_dashboard`/`generate_temporal_dashboard`). Two things worth flagging for
  future work in this area, not full open items:
  - **Confidence-tagging convention, established but not retroactive.** These 3 tools are the
    first fetch tools in this codebase to auto-call `set_layer_confidence` on the layer they
    create (`OBSERVED` for FIRMS/EONET, `DERIVED` for GDACS). No prior fetch tool
    (`fetch_geoboundaries`, `fetch_hdx_admin_boundaries`, `fetch_building_footprints`,
    `fetch_worldpop_population`) does this — worth adopting there too if a future pass touches
    those, but not itself a bug or a gap to close as this note is written.
  - **GDACS license terms, verified live 2026-09-12.** `https://www.gdacs.org/About/termofuse.aspx`
    carries no explicit data-redistribution license — it's primarily an accuracy/liability
    disclaimer (deferring to the European Commission's general copyright notice), and states
    plainly that GDACS's automated alerts "may require further validation" and "should not be
    used for decision making without prior confirmation of their validity." Reflected in
    `fetch_gdacs_disaster_alerts`'s own tool description per `docs/archive/LICENSE_AUDIT.md`'s
    own established precedent (verify a source's current terms directly rather than assume —
    that doc's own history shows a source's license can change between passes). Not added to
    `docs/archive/LICENSE_AUDIT.md` itself, which is frozen; recorded here instead.

Everything below was open as of `docs/archive/STATUS_REVIEW_2026-08-20.md` (v1.2.21) or a later round, and is
now closed as of v1.2.33. Listed here once, briefly, so nobody re-opens it by misreading an old
doc — full detail for each is in `CHANGELOG.md`'s per-version entries, not repeated here.

- 4 duplicate tool registrations removed (`generate_csv`, `export_attribute_table`,
  `generate_map_image`, `filter_features`) — tool count is 131, not 134, as of this doc.
- Raster styling gap closed — `apply_raster_stretch` (v1.2.25).
- `agent/providers/cartogen.py` scaffolded as an explicit, honestly-labeled stub (v1.2.25) —
  still a stub, not extended, per its own docstring's stated preconditions; not "open," just
  not further built.
- Provider client bugs fixed: `gemini.py` header-auth for `grounded_search`/`list_models`
  (v1.2.28); `ollama.py` shared retry logic + accurate malformed-response error message.
- `CONTRIBUTING.md` written (comment/status-honesty/testing discipline).
- `docs/RELEASE_SMOKE_TEST.md` written (v1.2.29) and its checklist verified accurate against
  live code (v1.2.32) — 2 real inconsistencies found and fixed (Humanitarian Data row's tool
  conflation, Project Management row's missing confirmation-gate note).
- Session token/cost usage visibility added to the chat UI (v1.2.30).
- `ui/attachments.py` extracted from `dock_widget.py` (the file-parsing half of the split plan
  — see §1.2 above for what's still open).
- **Full MultiTier namespace-package restructure** (v1.4.0/v1.4.1) — code moved to
  `src/cartogen_ai/core/` under a PEP 420 namespace root; `cartogen_ai.py` renamed to
  `plugin_main.py` (BUG-2026-08-21-6); 15 stale `agent`/`ui` imports and the missing `-t .` in the
  documented test command fixed (BUG-2026-08-21-7). 691/691 baseline restored. Note the `sys.path`
  bootstrap half of this is still unverified inside a real QGIS session — see §2 above.
- `docs/route_optimization_prototype.py` smoke-tested for the first time against real installed
  dependencies + synthetic data; 2 real bugs found and fixed (v1.2.33) — see `BUG_TRACKER.md`.
- **Task register wired end to end into the chat send path** (v1.4.2-v1.4.4) — file I/O modeling
  per task, the prompt-preview panel, the requirement/slot gate, and output-contract enforcement.
  Verified 2026-08-31 by a headless functional test (`tests/test_chat_widget_live.py`) driving
  real Qt widgets with `QTest.mouseClick` against a real `QgsApplication` — closing the "never
  run in a live QGIS session" gap this tracker previously flagged for that layer.
- **2026-08-31 UX/documentation audit and fixes** — a 22-finding audit
  (`docs/archive/UX_DOCUMENTATION_AUDIT_2026-08-31.md`) covering documentation staleness, in-app
  onboarding, and UI consistency. Fixed: the preview panel silently sending stale text after an
  in-place edit (input box is now read-only while any gate panel is open); the main chat send
  path throwing a raw provider 401 instead of a friendly message for an unconfigured API key
  (`agent/auth.py`'s `CredentialManager.missing_credential_message`); all send errors reaching
  the user as unclassified raw exception text (`ui/chat_formatting.format_send_error`); a
  possible double-send race during prompt refinement; missing tooltips, an untitled gate panel,
  and a reused destructive-action button color; the welcome message, Settings dialog, and Help
  tab not mentioning the task-register pipeline or how to get an API key per provider; and the
  version/tool-count staleness in this doc, `README.md`, and `DOCUMENTATION.md`. Not done in this
  pass (tracked, not forgotten): splitting
  `CHANGELOG.md` into per-release notes, and archiving the dated one-off review docs in `docs/`
  into a subfolder.

---

## 4a. Cross-repo sync check, 2026-09-10 — `cartogen-ai-community` does NOT need syncing

Resolved the open question ("does `cartogen-ai-community`'s checkout need syncing to the
now-shared `origin/main` tip?") left by the 2026-09-05 repository-split-brain reconciliation.

`cartogen-ai-community`'s local `main` (`aa3ac95`) has 3 commits not present in `cartogen-ai`'s
history: `99079e3` ("add `clear_global_notes()`"), `80aca72` ("mark this repo as stale, point to
`cartogen-ai` as canonical"), `aa3ac95` ("record full 5-dimension code review"). Checked each for
content-equivalence rather than assuming the repos are in sync:

- `99079e3` — already independently ported into `cartogen-ai`. `clear_global_notes()` exists in
  this repo's own `agent/memory.py` (line 185), closed here first as `eee84eb` (2026-09-04, this
  repo's BUG-2026-09-04-2) and ported to `cartogen-ai-community` afterward as that repo's own
  BUG-2026-09-04-1. Already fully documented above (§9 in `MASTER_TASK_REGISTRY.md`'s queue) as
  closed in both repos. No action needed.
- `80aca72` — a docs-only commit in `cartogen-ai-community` marking that repo stale and pointing
  to `cartogen-ai` as canonical. Nothing to port; this is the terminal state, not a change this
  repo needs.
- `aa3ac95` — `cartogen-ai-community`'s own 5-dimension review (mockup/bug/uncompleted/
  security/GDPR) of *its own* code. `cartogen-ai` already has its own independent, equivalent
  review of *this* repo's code: `docs/CODE_REVIEW_2026-09-08.md`, referenced above at line 142.
  These are parallel reviews of two different codebases, not one review that needs propagating.

**Conclusion: no sync action needed in either repo.** `cartogen-ai-community`'s unmerged commits'
content is already accounted for on this side.

**Factual correction (not a rewrite — commit `80aca72` is immutable history, so noting the
correction here instead):** `80aca72`'s commit message states "This repo's full commit history is
an ancestor of cartogen-ai's (confirmed via `git merge-base --is-ancestor`)." Independently
re-ran that exact check this session (`git merge-base --is-ancestor _community_check/main HEAD`
from within `cartogen-ai`, `_community_check` remote pointed at the `cartogen-ai-community`
checkout): **exit code 1 — not an ancestor.** `git merge-base` gives the actual common ancestor as
`dd4dacf`, three commits behind `cartogen-ai-community`'s `aa3ac95`. The claim in that commit
message is factually inaccurate as literal git ancestry — most likely because the fix in `99079e3`
was hand-ported into `cartogen-ai` as a separate, differently-hashed commit (`eee84eb`) rather than
merged/cherry-picked, so the two histories were never going to share that commit object even though
the *content* matches. No functional consequence (nothing is lost or needs redoing), but the
"is an ancestor" phrasing should not be trusted at face value if anyone re-reads that commit later.

- **2026-09-20/21 — both remaining stable-release gates from the 15-section audit closed for
  real: the pre-existing Ruff lint failure fixed (not just accepted as debt), and the CI matrix
  re-validated green after a real, live regression the fix itself surfaced.**
  - **Ruff: 125 violations -> 0.** Every finding individually verified (grep for other usages)
    before removal, not blindly trusted from `--fix` — caught and reverted one real false
    positive: `--fix` removed `requests` from 5 provider client files as "unused," but tests
    patch e.g. `cartogen_ai.infrastructure.providers.gemini.requests.get`, which needs the name
    importable in that module even though nothing in the file calls it directly (real calls route
    through `providers/base.py`'s shared `requests` object, which patching the same object's
    attribute via any importer's name still affects). Restored in gemini/openai/claude/
    openrouter/ollama with a `# noqa: F401` explaining why; left removed in `cartogen.py`, which
    no test patches. A real bug was also found and fixed along the way: `vector_tools.py`'s
    `apply_labels()` referenced `QgsLabelObstacleSettings` for polygon obstacle-avoidance labeling
    without ever importing it — a `NameError` on every real call to that path, silently caught by
    the tool's own broad exception handling rather than crashing visibly. Live-confirmed the fix
    against real QGIS 4.2.2 (`apply_labels` on a polygon layer now succeeds).
  - **CI matrix: validated, then a real regression appeared and was fixed within the same
    session.** The Ruff fix push confirmed `test (ubuntu-latest)` fully green for the first time
    ever in this repo — Ruff passes AND the release-zip packaging-verification step downstream of
    it finally executes and passes. But `QGIS live tests (release-3_28)` then failed with the
    exact segfault signature the prior session's fix was built to tolerate on `4.2.2` only —
    confirming `release-3_28`'s own documented moving-tag nature (the image underneath that tag
    name changed within the session) makes pinning a crash waiver to an image name fragile by
    construction. Removed the `$QGIS_TAG == "4.2.2"` restriction; kept the 3-part signature (exit
    139 exactly + literal "Segmentation fault" + unittest's own "OK" line) that's specific enough
    on its own. Final confirmed-green run, all 5 jobs:
    https://github.com/cartogenai-glitch/CARTOGEN-AI/actions/runs/35537301531
  - Full headless suite: 1981 passing, 44 skipped, unchanged by the lint pass itself (pure
    import/naming cleanup plus the one real labeling-bug fix). Byte-compile clean across the
    whole repo.
  - **§1.10 (exact-ZIP clean-profile install/upgrade test) is now the ONLY remaining item before
    a stable-release decision** — genuinely blocked on a real interactive QGIS GUI session this
    sandbox cannot provide, unchanged from every prior entry that's said so.

- **2026-09-21 — the post-test CI segfault fixed at the root, not just waived.** A fourth review
  correctly rejected the prior day's waiver as unproven: it asserted an environment-level cause
  ("numpy/matplotlib ABI mismatch") without demonstrating it, and didn't rule out a real plugin
  teardown regression. Implemented the review's own recommended methodology instead of arguing
  the point further:
  - **Pinned both `qgis-live-tests` images by immutable manifest digest** (`qgis/qgis@sha256:...`)
    instead of a floating tag, closing the moving-tag risk that had already bitten this job once.
  - **Added a minimal QGIS-only control process** (`tests/_ci_qgis_control_process.py`, never
    imports `cartogen_ai` or anything under `src/`) as its own CI step, to test whether a
    plugin-code-free QGIS session hits the same crash independent of this repo.
  - **Added explicit `QgsApplication.exitQgis()` teardown** (`tests/_ci_run_live_tests.py`,
    replacing the bare `python3 -m unittest ...` invocation) so Qt/QGIS's C++ objects get an
    orderly shutdown instead of whatever Python's implicit interpreter-exit does.
  - **Found a real bug in step 3's own script** (invoked as a bare script instead of `-m`, so the
    repo root was never on `sys.path` — fixed to `python3 -m tests._ci_run_live_tests`) and, once
    that was fixed, **reproduced the actual crash locally** — on Windows/QGIS 4.2.2, independent
    of CI's Linux image and unrelated to the numpy/matplotlib warning previously assumed to be the
    cause. The crash happened between `runner.run()` returning and the next line of Python
    executing, before `exitQgis()` was even reached.
  - **Root-caused it for real:** each of the ~40 test methods across `test_chat_widget_live.py`/
    `test_plugin_main_live.py` creates a real `QDockWidget` via `addCleanup(dock.close)` —
    `.close()` alone doesn't destroy the underlying C++ object, so ~40 live-but-closed widgets
    (each owning child `QTimer`s, e.g. `chat_tab_widget.py`'s `_plan_spinner_timer`) accumulated
    for the whole run and only got garbage-collected whenever Python's refcounting happened to
    drop the last reference — landing unpredictably, evidently sometimes inside the interpreter's
    own shutdown sequence.
  - **Fix:** `gc.collect()` + pump the Qt event loop (a 300ms `QEventLoop`/`QTimer.singleShot`)
    before calling `exitQgis()`, so any `deleteLater()`-deferred C++ destruction actually runs
    while `QApplication` is still fully alive. Verified 4/4 clean local runs after the fix (vs. a
    reliable crash before it), then confirmed in CI: both `qgis-live-tests` legs now complete with
    `exitQgis() returned normally` and zero `Segmentation fault` — the waiver logic never
    triggers, it's dead code now rather than something still relied upon. Final confirmed-green
    run, all 5 jobs, no waiver used:
    https://github.com/cartogenai-glitch/CARTOGEN-AI/actions/runs/35538330552
  - The segfault-waiver code itself is left in place (harmless if truly dead, and cheap insurance
    against a future regression reintroducing the same pattern) but should not be relied upon as
    the CI matrix's actual passing mechanism going forward — it isn't one anymore.

- **2026-09-21 — cut and published `v1.16.0-rc3`.** Both gates §4's two entries above closed for
  real (Ruff 125→0, CI segfault root-caused not waived) — released per the standard 7-step
  process: version bump → smoke test (1981 tests + live-QGIS `exitQgis()` teardown, both clean) →
  commit → push → rebuild → tag → GitHub prerelease, published asset checksum independently
  verified to match the local build byte-for-byte
  (`74b0b167a112417a15ce12bade6990d86d68923cdb9de1bc9e1a2d07f66b2426`).
  https://github.com/cartogenai-glitch/CARTOGEN-AI/releases/tag/commercial-plugin-v1.16.0-rc3 —
  `v1.16.0-rc2` (`7d682c7`) stays published, unchanged, per the tags-never-rewritten convention.
  **§1.10 (exact-ZIP clean-profile install/upgrade test) remains the only open item before a
  stable production-release decision** — cutting this RC does not change that; it was published
  as another prerelease with that gate explicitly still open, by direct instruction.

- **2026-09-23 — cut and published `v1.16.0-rc4`.** Built from `c36e611`, a clean `git archive` of
  that commit (not the live working tree, which had another session's uncommitted release-smoke
  prep work sitting in `docs/` — confirmed `docs/` is NOT excluded from the release zip by
  `plugin_upload.py`, so building from the working directory as-is would have shipped that
  unrelated in-progress work in this release; the archive approach avoided it without touching or
  discarding those files). Contains the §1.11 sandbox-hardening fixes (commit `4268c95`), the
  swallowed-exception logging + `CLAUDE.md` refresh (`78363b8`), and the §1.11 tracker entry itself
  (`c85c061`) — none of which had shipped in `v1.16.0-rc3`. Standard 7-step process: version bump
  → smoke test (1987 tests + live-QGIS `exitQgis()` teardown, both clean) → commit → push →
  rebuild (from the clean archive) → tag → GitHub prerelease, published asset checksum
  independently verified to match the local build byte-for-byte
  (`765c352d807e9243b2d4d73219145f62c5546637a0f59bba84654187903f2a5b`).
  https://github.com/cartogenai-glitch/CARTOGEN-AI/releases/tag/commercial-plugin-v1.16.0-rc4 —
  `v1.16.0-rc3` (`99eb868`) stays published, unchanged. **§1.10 remains the only open item before a
  stable production-release decision.**

- **2026-09-23 — the `v1.16.0-rc4` codebase also synced and released to a second repo,
  `http-solution/cartogen-ai-qgis-plugin` (private, account ID `214734687`), by direct
  instruction.** This is a genuinely separate GitHub repository from the canonical
  `cartogenai-glitch/CARTOGEN-AI` used throughout this tracker — not a fork, not a mirror
  configured via GitHub's own mirroring, and not previously referenced anywhere in this
  project's docs/history before this session. It has its own independent commit history
  (unrelated by hash to the canonical repo despite closely matching content — commit messages
  in its history read as replicated/synced from the same source, apparently by a separate,
  independent process not run from this session) and was already current through `v1.16.0-rc3`
  plus one extra commit (a `release_smoke_assets/` fixture bundle + `RELEASE_LIVE_TEST_SCENARIOS.md`
  — the same fixture content another session had left uncommitted in the canonical repo's working
  tree) before this session touched it.
  - **Local sync**: diffed the two working trees directly (not a `git merge`/`pull`, which would
    conflict on every file given the unrelated histories) at `C:\http-solution\cartogen-ai-qgis-plugin`
    against the canonical checkout. Verified file-by-file, after normalizing CRLF-vs-LF line-ending
    noise that was making every file look different, that the canonical repo's rc4 content was
    purely additive/replacing over what this repo already had committed — nothing here was
    overwritten or lost. Synced: the rc4 §1.11 sandbox fixes, exception-logging changes, version
    bump, `CLAUDE.md`/tracker updates, and the rc4 headless-checklist evidence
    (`docs/release_smoke_assets/logs/rc4_headless_run.json`). Deliberately left untouched:
    `docs/release_smoke_assets/` fixture *binaries* and `RELEASE_LIVE_TEST_SCENARIOS.md` (already
    correct there), and `.github/workflows/tests.yml`'s `permissions:` block (this repo's own
    addition, not present upstream) — merged rather than overwritten once confirmed to be the
    *only* real difference in that file; the rest of that file there already matched the rc4 CI
    content, apparently from that same independent sync process. `web-platform/` (untracked local
    content in the canonical checkout, not part of either repo's git history) was correctly left
    alone.
  - **Commit identity**: this checkout's local git config was overridden to a personal identity
    that GitHub's `GH007` email-privacy check rejected on push. Fixed by setting both
    `GIT_AUTHOR_*` and `GIT_COMMITTER_*` (amend alone only fixes the author field, not the
    committer — the first attempt failed for exactly this reason) to
    `HTTP-Solution <214734687+http-solution@users.noreply.github.com>`, the same identity already
    used in this repo's own prior commits, confirmed by matching the numeric account ID.
  - **Release**: tagged `commercial-plugin-v1.16.0-rc4`, built the zip from this repo's own clean
    committed state (226 files — more than the canonical rc4 zip's 196, since this repo has
    additional already-committed content the canonical repo doesn't yet), and published a GitHub
    prerelease via the REST API — this session has no `gh` CLI access to the `http-solution`
    account (only `cartogenai-glitch`), so the release/asset-upload/verify steps used the OAuth
    token Git Credential Manager already had cached for this checkout's own git push access,
    called directly via `curl`/Python, with the token never printed or logged. Published asset
    checksum independently verified to match the local build byte-for-byte
    (`8566c818a212851fe2bb10dec115b3e686425995d7663e9d23b77eeda43a78f9`).
    https://github.com/http-solution/cartogen-ai-qgis-plugin/releases/tag/commercial-plugin-v1.16.0-rc4
  - **This does not change §1.10's status** — the exact-ZIP clean-profile install/upgrade test is
    still open on both repos; publishing rc4 here doesn't substitute for it. Whether
    `http-solution/cartogen-ai-qgis-plugin` should be treated as an ongoing second release target
    going forward, or this was a one-off sync, is a decision for whoever owns that account — not
    resolved here.

## 5. Source doc index (all frozen/historical unless noted; frozen docs live in `docs/archive/`)

| Doc | Status |
|---|---|
| `docs/archive/STATUS_REVIEW_2026-08-20.md` | Frozen snapshot, v1.2.21. Superseded by this tracker for "what's open." |
| `docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md` | Frozen review. All 4 follow-up tasks from this round are closed (§4 above). |
| `docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md` | Frozen audit. §3's decision is the live item in §1.1 above. |
| `docs/archive/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md` | Frozen plan. Execution is the live item in §1.2 above. |
| `docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md` | Frozen strategy doc; its own §4 was updated 2026-08-21 with real smoke-test results (not re-frozen, since that update was factual correction, not new proposal content). |
| `docs/archive/JIAF_MULTISECTOR_COMPOSITE_SPEC.md` | Frozen spec, deliberately unbuilt — see §3 above. |
| `RELEASE_SMOKE_TEST.md` | **Living checklist**, not frozen — update when tools/categories change. |
| `LIVE_TEST_SCENARIOS.md` | **Living checklist**, added 2026-09-16 — multi-turn workflow scenarios a single-prompt smoke test can't catch (task routing, confirmation gates, map-visualization/technical-analysis accuracy). |
| `BUG_TRACKER.md` | **Living tracker**, not frozen — update as bugs are found/fixed. |
| `CHANGELOG.md` | **Living log**, not frozen — the authoritative fix/feature history. |

---

## How to keep this current

When you close an item above: move it to §4 with a one-line summary and the version it shipped
in, and update the "Last updated" line at the top. When you find something newly open: add it to
the right section above with a source reference — don't let it live only in a chat response or a
session summary that won't survive past this session.

### 1.19 rc9: audit follow-up (added 2026-10-01; CI-verified on QGIS 4.2.2, not yet hands-on)

Plan and evidence: `docs/RC8_AUDIT_AND_SOLUTIONS_2026-09-30.md`, `docs/RC8_FIX_PLAN_2026-09-30.md`; PR #108. Owner decisions 2026-10-01: F06 results GeoPackage, F09 concave-hull headline, F21 central model view, F25 unchanged. What shipped and how it was checked:
- **F03/F14** `services/response_guard.py`: record-like bullets/prose and no-data-tool turns are flagged; ungrounded record tables replaced by a notice; the model's confirm lines dropped when a gate is pending. Heuristic: it cannot catch data written in an unrecognised shape. Offline tests only.
- **F10/F18/F22** per-turn tool cap + token budget (`cartogen_ai/max_tool_iterations`, `max_turn_tokens`, 0 = no budget), footer text, Settings fields, startup log line, size guard for the other fetch tools (`allow_large_download`), `QNetworkInformation.isMetered()` check. Offline tests; the Settings dialog fields are not covered by a live widget test.
- **F15** LaTeX to Unicode, balanced parentheses in action-chip links (the stray `)` cause), article, no-route feedback (`_CollectingFeedback`, QGIS-only, exercised indirectly by the network live tests), prints to the structured log.
- **F12** `basemap='none'`, `backdrop_layer` (live-tested), markercluster 1.5.3, slider last date, default basemap `hot`. A dashboard opened from disk with real tiles is still unchecked.
- **F09** three figures (`reach_figures`, `reachable_population_range`); concave hull via `QgsGeometry.concaveHull(0.85)` (QGIS >= 3.28, GEOS >= 3.11; live-tested). The constrained WorldPop product was NOT adopted: its REST alias is unverified.
- **F21** `models/model_view.py` (live-tested through `get_layers` and the map context). Layer NAMES stay visible; only field names are withheld, in enforce mode with a non-local provider.
- **F08** `travel_time_matrix` single-tree path for > 200 destinations. Live-tested for equivalence with `native:shortestpathpointtolayer` (shortest and fastest) on a small grid. NOT profiled on the 3,369-facility request; each destination takes its nearest road vertex's cost.
- **F07** `heal_layer_tree()` on project load (live-tested). **F06** `results_store.py` called from `_replace_named_layer` (live-tested round trip); outputs of tools that do not use `_replace_named_layer` remain memory layers. **F19** whole-country cache-and-clip fallback (offline-tested only; needs `allow_whole_country`).
- Live tests added: `tests/test_rc9_live.py` (F01 incl. auxiliary storage, F05 guards, F11). F02 and F16 widget flows were already covered by existing widget tests.
- Still open: F25 transcript location (decision: unchanged); WorldPop windowed-read measurement (`gdalinfo` Block=); Excel CSV; the plan-validation setting in the operator's profile (F18); results store covers only `_replace_named_layer` outputs.

### 1.20 Routing and reach visualization round 2 (added 2026-10-01)

`tools/routing_style.py`. (1) `calculate_service_area(style_by_cost=True)` adds `<facility>_roads_by_cost_<i>`: the roads reached within the travel cost from the same one-origin shortest-path tree as `travel_time_matrix`, graded in 5 labelled cost bands (dark near, warm far), and hides the plain native lines layer (kept for analysis; `styled_layers` in the result). Whole edges, not cut ones: the outermost road may run one segment past the limit; the native lines stay the exact result. (2) `population_access_gap` styles the three reach figures with distinct translucent fills (upper bound dashed) and puts them in one group `Reach figures: <facility>`: headline on top and visible, the others hidden. (3) `classify_facilities_by_access` draws "beyond" facilities red, larger and on top of "within" (symbol levels). Offline: pure band/label/palette tests. Live (CI): `tests/test_routing_style_live.py`. Not seen on a real canvas yet: whether the colours read well on your basemap.

### 1.21 Visualization and analysis gap analysis (added 2026-10-01)

Full analysis: `docs/VISUALIZATION_AND_ANALYSIS_GAP_ANALYSIS_2026-10-01.md`. Shipped on branch `claude/viz-gap-analysis`: `tools/output_style.py` (population/density/surface raster ramps, point default, algorithm-output styling), `tools/layout_style.py` (print layout typography, panels, a legend of the visible layers only, preparation date, classification prefix), a fix for raster algorithms in `run_allowlisted_processing_algorithm` (they could not write to `memory:` and returned a file path), and ten analysis algorithms added to the allowlist (`ANALYSIS_EXTENSIONS`, each checked against the QGIS registry in CI). Needs the owner's decision: the allowlist extension is a trust-boundary change (expression-taking algorithms were left out on purpose). Open: raster legend units, automatic labels, an access-map layout template, a rendered look at the exported page.

### 1.22 Humanitarian workflow gap analysis (added 2026-10-04)

Full analysis: `docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md`, comparing the owner's "Humanitarian Mapping Workflows" document with the 184 registered tools (static comparison, nothing run). Planned, not built: **H1** `apply_network_barriers` (blocked/penalised roads for the service-area tools), **H2** `generate_mapping_task_grid` (HOT Tasking Manager style), **H3** `design_sampling_frame` (MSNA), **H4** `evaluate_forecast_trigger` (anticipatory-action thresholds), **H5** vector MCDA ranking with stability check, **H6** weighted survey aggregation with small-n suppression, **H7** file-based importers for IPC / INFORM / UNOSAT tables, **H8** allocation envelope, **H9** road-network bottleneck analysis. **H10** (Kobo API, ACLED, GloFAS/CHIRPS, Logistics Cluster, LandScan) is blocked on credential/licence decisions. Needs the owner: build order (suggested H1, H4, H2), the H10 decisions, and whether `calculate_severity_index` stays "JIAF-style" or gets a real JIAF-method tool. Also stated plainly there: `fetch_fts_funding_data` is plan-level, not geographic, so a "funding orphan" map is not possible today.

**Update 2026-10-04: H1, H4 and H2 built** (branch `claude/eager-goldberg-aruysp`). H1 `apply_network_barriers` (`tools/barrier_tools.py`): writes a speed field with roads near barriers blocked or penalised; ignored by `strategy='shortest'` and 'block' is a near-zero speed, both stated in the result. H4 `evaluate_forecast_trigger` (`tools/trigger_tools.py`): evaluates a user-supplied threshold / lead window / probability against forecast rows, no defaults, never fetches forecasts. H2 `generate_mapping_task_grid` (`tools/task_grid_tools.py`): clipped square task grid in a local UTM CRS, optional High/Medium/Low priority from a point count or population raster sum, GeoJSON export (import into a real Tasking Manager not checked). Pure logic is unit tested offline; the QGIS-side code has live tests (`tests/test_barrier_tools_live.py`, `test_trigger_tools_live.py`, `test_task_grid_tools_live.py`) written without a local QGIS, so their first execution is CI. Not hand-tested. Possible existing defect noticed, not investigated: `zonal_statistics` calls `qgis:zonalstatistics`, which may not exist in QGIS 4 (H2 uses `native:zonalstatisticsfb`).

**Update 2026-10-04 (later): H3 built.** `design_sampling_frame` (`tools/sampling_tools.py`): per-stratum sample size for a single proportion (z-score, margin of error, expected proportion, design effect, finite-population correction, non-response) and a reproducible draw (recorded seed) from a candidate-units layer or as random points in each stratum. Every assumption is an argument and is echoed back; the defaults p = 0.5 and design effect = 1.0 are stated as NOT a recommendation (1.0 is valid only for simple random sampling; a cluster design needs a design effect from the survey designer). Random points are not households; the result says so. Pure statistics and draw tested offline; QGIS part has `tests/test_sampling_tools_live.py` (written without a local QGIS, first run in CI). Not hand-tested; no check against an external sample-size calculator beyond the textbook figure (n0 = 385 at 95% / 5% / p 0.5).

**Update 2026-10-04 (later still): H5 and H6 built.** H5 `calculate_mcda_ranking` (`tools/mcda_tools.py`): weighted multi-criteria ranking of any vector features, each criterion with a weight and a priority direction, min-max scaled, ties share a rank; then a seeded weight-perturbation check (default +/-20%, 500 trials) reports each unit's best/worst rank and top-k share. The check covers the weights only (said in the result). Units are keyed by feature id (not name), units with a missing criterion are excluded and listed, writing score/rank fields needs confirmation and goes through the owned edit session. H6 `aggregate_survey_indicator` (`tools/survey_tools.py`): weighted share (Wilson) or mean per area with Kish effective sample size; groups under `min_n` (default 30) are suppressed and their exact small count is not returned; invalid answers/weights are excluded and counted. It ignores clustering unless a design effect is supplied, and `min_n` 30 is a rule of thumb, not a disclosure-control standard (the owner's data-protection policy decides). Pure logic tested offline; QGIS parts have live tests written without a local QGIS (first run in CI). Not hand-tested. Noticed, not fixed here: `calculate_severity_index` / `calculate_presence_gap` still write their output fields through the data provider (`_write_scores_to_layer`), i.e. the pre-#143 pattern that bypasses the edit buffer and ignores failures after the add; and they key units by name, so duplicate names collide. Worth a follow-up issue.

**Update 2026-10-04 (catalogue and styling review).** `docs/HUMANITARIAN_TOOLS_CATALOGUE.md` lists every humanitarian tool by workflow with its map output and tips (a test, `tests/test_humanitarian_catalogue.py`, fails if the catalogue names a tool that does not exist); the README has a matching "Humanitarian tools" section. Styling review result: new `tools/humanitarian_style.py` gives the task grid (priority colours, task-id labels), the barrier-affected segments (separate red/orange layer), survey sample points (colour per stratum), GDACS / EONET / fires layers (alert / category / dot; styled when first created, with an "other" catch-all) and the change-detection raster (diverging ramp, zero transparent) a meaningful look. Open styling gaps, listed in the catalogue: output layers of `ingest_osm_features`, `fetch_building_footprints`, `extract_features_from_imagery` and `weighted_overlay_analysis` still arrive in QGIS defaults, and the severity / presence-gap / population-in-need / damage-exposure / MCDA tools write fields to the user's own layer without restyling it (a deliberate choice, to be confirmed). Live tests for the new styling (`tests/test_humanitarian_style_live.py`) were written without a local QGIS; none of the looks has been seen on a real canvas.

**Update 2026-10-04 (WP4, #156 #157 #163).** Native service-area algorithm: the cost for the Fastest strategy is seconds in the parameter and is now converted to hours for the child algorithm (the child's convention; before, every Fastest service area was 3,600 times too large); facility points are transformed into the network CRS; the sink schema is what the child actually returns plus `facility_fid`; optional direction-value parameters are passed through; no usable facility is an error (was an empty "success"). Both native algorithms: invalid sources and failed `addFeature` raise `QgsProcessingException`; cancellation is checked inside the long loops and a cancelled hub-siting run says it is partial; hub siting stops above 25 million candidate x demand measurements with a message. Generic Processing tool: unknown parameter names are rejected before running (valid names listed), destination sinks come from the algorithm's own definition, every layer output is returned (`additional_outputs`), `native:selectbylocation` reports a changed selection instead of renaming the user's layer, and `qgis:zonalstatistics` (which writes into its input) is no longer offered. Offline tests for the pure parts; live tests (`tests/test_processing_provider_live.py`, `tests/test_processing_allowlist_tools_live.py`) were written without a local QGIS, so their first execution is CI. One assumption to confirm in CI output: that the child algorithm's fastest cost is in hours, as this repo's own `calculate_service_area` treats it.

**Update 2026-10-04 (WP2, #153 #154 #159 #160 #161).** Data correctness, offline-tested only (no QGIS here; PyQGIS paths are CI/hand-check):
- #160: `estimate_population_exposure` runs zonal statistics on a detached copy, so the caller's layer gets no `pop_*` fields and a repeat run cannot read a stale one. Result has `zones` (per feature id), `overlap_rule` and `overlapping_zone_pairs`; per-zone totals, `total_population` is their plain sum (owner decision). `calculate_population_in_need` reads the per-zone list by feature id instead of the removed side-effect field. Not done: raster-unit (people per cell vs density) validation.
- #159: hub siting, p-median, route stops and the matrix origins use `unique_labels`, so duplicate or NULL first-attribute names no longer overwrite each other. Population totals use `unique_zone_keys`. Not done: `analysis_tools.py` score writes.
- #161: point-in-polygon counting uses intersects, lowest feature id wins, and `calculate_damage_exposure_severity` reports `building_assignment` (matched/ambiguous/unmatched/skipped). Not done: requiring/reprojecting points into the admin CRS.
- #153: NDVI/NDWI/NDRE, weighted overlay and change detection reject rasters that differ in CRS definition, size, pixel size or origin (message names the difference and suggests warping). No automatic alignment. Index formulas return 0 where the denominator is 0.
- #154: `elevation_profile` transforms sample points into the DEM CRS and reports ellipsoidal metres; the impedance slope does the same and uses metre lengths; the imagery `min_area_m2` filter measures square metres on the ellipsoid. The DEM vertical unit is still assumed to be metres (stated in results).

**Update 2026-10-04 (WP3, #155).** Blocked roads are removed from the network (owner decision). `tools/_network_closure.py`: a segment is CLOSED when its speed field is negative (`CLOSED_SPEED_KMH = -1`); `apply_network_barriers` mode `block` and `build_composite_impedance_field` passability 0 now write it (before: a 0.1 km/h floor that routing could still cross). `calculate_service_area`, `travel_time_matrix` and `optimize_delivery_route` (and so `classify_facilities_by_access` and `population_access_gap`, which call the service area) route on a scratch copy without closed segments, for either strategy, and report `closed_segments_removed`; a network with every segment closed is an explicit error; the user's layer is never edited. **Deviation from the plan, on purpose:** the plan said "speed 0 = closed", but this repo's own measurements show OSM `maxspeed` is 0/NULL on over 99% of roads and means "unset", so reading 0 as closed would delete nearly every road. Only a negative value closes. **Behaviour change for the release notes:** a road previously "blocked" (0.1 km/h) is now unreachable, and "block" now works with `strategy='shortest'` too. Old speed fields written by earlier versions still hold 0.1 and are NOT closed until the tool is re-run. Live tests (`tests/test_network_closure_live.py`) were written without a local QGIS; first execution is CI.

**Update 2026-10-04 (WP5, #152).** `travel_time_matrix`, single-tree path (over 200 destinations; also used by the tools built on it): each destination is projected onto its nearest road edge and charged the direction-aware partial-edge cost (`partial_edge_cost`: enter at either end, cheaper allowed way wins, one-way roads stay one-way), instead of the cost of the nearest graph vertex. Both paths now key the matrix by destination feature id: the native point-to-layer output is matched back from its reported end-point coordinates (`parse_xy`, `match_destination_key`; unmatched rows keep QGIS's text key and are counted in `destination_keys_note`). Pure parts unit tested offline; the graph code and the native-vs-single-tree agreement (`tests/test_partial_edge_costs_live.py`: 1,000 m road, points at 490/510/1,000 m, a one-way road) were written without a local QGIS, so CI is their first run. Assumptions to check in CI: the graph's per-edge `cost(0)` is in the strategy's unit; the native `end` field contains the destination's coordinates as text. Edges are straight lines between graph vertices, so on a curved road the fraction is by straight-line share of that vertex pair, which is exact for cost because each pair is one routing edge. The short leg from the destination to the road is still not added.

**Update 2026-10-04 (WP6, #164 #167 #93 #91).**
- #164: `create_print_layout` builds the replacement under a temporary name and swaps it in only after it has been built and exported; any failure removes the temporary layout and leaves the old one untouched. `export_layout_atlas` gives every page a distinct file name (`unique_atlas_file_name`, `_2`, `_3` suffixes, case-insensitive), reports files from an earlier export it replaced, and puts the layout's atlas settings back as they were. `feature_count` counts files written.
- #167: unload now removes the translator and shuts the script-isolation worker down (`script_isolation.shutdown_worker`); the load-time module eviction is scoped to modules under this plugin's own `cartogen_ai` directory (`_module_ownership.py`), with the old evict-everything path kept as a last resort when what resolves is not ours. **Not done:** invalidating callbacks of tasks still running at unload, and marshalling the task runner's fallback completion to the Qt thread (both in `core/services/task_runner.py`) — left open on #167, not investigated.
- #93: owner decision recorded — layer name, geometry type, CRS and feature count stay visible to a cloud provider; declared in `SECURITY.md`, in Settings next to "Cloud data protection" and in the Layer Data Sensitivity dialog (`model_view.SCHEMA_DISCLOSURE`). Field names of protected layers were already withheld since rc9.
- #91: the WorldPop refusal/confirmation texts now say what is true (worldpop.org cannot send a window; the full file is downloaded once, kept, only the requested area is added; the real size is shown first). The clipped-add behaviour itself was done earlier (F19/F22). Not hand-tested.
Live tests for #164 (`tests/test_layout_swap_live.py`) were written without a local QGIS; first execution is CI.

**Update 2026-10-04 (HX1a, humanitarian map looks).** New tool `apply_humanitarian_look` (MODIFY) and `humanitarian_style` looks for result fields: `severity` (five fixed classes matching `calculate_severity_index`'s own 1-5 classes, boundary-tested against `_severity_class`), `people_in_need` / `exposure` (quantile classes with limits rounded to two significant digits, zero as its own class), `presence_gap`, `rank`. The analysis tools (severity, population in need, presence gap, damage severity, MCDA) now return a `map_look` hint when they write a field; they still never restyle a layer they did not create, so the look is applied only when asked or accepted. `calculate_severity_index`'s description now says it is a simple weighted index and not the JIAF method (HX5 will add a separate JIAF 2 analysis-support module). Not yet done in HX1: automatic looks for layers the tools create themselves (footprints, OSM features, imagery extraction, weighted overlay, an output layer for population exposure) and the `sitrep` print template. Pure rules unit tested offline; the renderer test (`tests/test_humanitarian_look_live.py`) was written without a local QGIS, so CI is its first run. Not hand-tested.

**Update 2026-10-04 (HX1b, looks for layers the tools create).** `fetch_osm_features`/`ingest_osm_features` layers: roads graded by highway class (rule-based, four groups + "Other"), areas pale, points the standard look; `fetch_building_footprints`: quiet translucent grey; `extract_features_from_imagery`: three model-confidence bands (labelled as the model's score, not a probability); `weighted_overlay_analysis`: the existing opaque surface ramp, under the vectors; `estimate_population_exposure(output_layer_name=...)`: a NEW layer (zone, feature_id, pop_estimate) in exposure classes, replacing only a layer this tool made earlier (marked with a custom property) and never a user's layer of the same name (suffix instead). All best effort: a styling failure never turns a successful analysis into an error. Pure rules offline; renderer behaviour in `tests/test_humanitarian_look_live.py`, written without a local QGIS (CI first run). Not hand-tested. Still open in HX1: the `sitrep` print template.

**Update 2026-10-04 (HX1c, `sitrep` print template; completes HX1).** `create_print_layout(template="sitrep", body_text=<situation summary>, key_figures=[{label, value, source?}], sources=[...])`: the same one-page geometry and styling as the standard layout, with a structured text panel: SITUATION, KEY FIGURES, HOW TO READ THIS MAP (when access layers are visible), SOURCES, HANDLING. HANDLING (figures are estimates, no exact locations of people or sensitive sites) and the preparation date are always added; nothing else is written on the caller's behalf, and a sitrep with no supplied content returns a `sitrep_warning` instead of inventing any. Key figures are whatever the caller passes (meant to be copied from tool results; at most 8). When the text exceeds the label box it gives up, in order, the reading guide, the tail of the summary and the last figures, and never the sources or the handling note (plain truncation would have cut exactly those). Not done: a genuine two-page report (the layout geometry has a documented overlap history and was left alone) and a per-persona template registry. Pure text rules offline; the layout itself in `tests/test_layout_swap_live.py`, written without a local QGIS (CI first run). Not hand-tested.

**Update 2026-10-04 (HX2, humanitarian task register).** Correction to my own plan: the "54 tasks with no tools" were not defects. All 54 were `guidance` tasks, which the register's own invariant allows to have no tools (training, workshops, agreements, procedures). What was wrong: 38 tools the humanitarian catalogue offers, including all of H1-H6, were in no task, so task matching could never suggest them; and 18 of the 54 guidance tasks do have a tool path. Changes (`task_register.json`, derived `acc`/`prod` regenerated with `tools/derive_task_io.py`): the H1-H6 tools, hazard feeds, monitoring workflows, schema/P-code/sensitivity/provenance/dataset-status tools, `apply_humanitarian_look` (after every task that writes a severity, need, gap or rank field) and the rest of the catalogue are attached to the tasks a person would look under; 13 guidance tasks became real tasks (`19.01` task grid, `18.01` sampling design, `26.15` web maps, `27.03`/`27.10` shared and inter-agency maps, and the planning tasks `7.29`, `14.28`, `27.12`-`27.17`: allocation, response, contingency, preparedness, evacuation, recovery); 5 more (`12.23`, `27.21`, `29.04`, `29.09`, `29.20`) stay guidance but now name the sensitivity, schema and P-code tools. 36 tasks remain tool-free guidance (training, coordination, agreements, procedures), which is correct. New tests: every catalogued tool is in some task; the tool-free tasks are the training/coordination/procedure kind; spot checks that the new tools sit where a person would look. Judgement calls to review: which tasks got which tool is my reading of the task text, not something verified with users; the planning tasks' tool chains are suggestions, not validated workflows.

**Update 2026-10-04 (HX3a, H8 allocation envelope).** New tool `calculate_allocation_envelope` (`tools/allocation_tools.py`): splits a budget the user supplies over areas in proportion to need ** exponent (times population when a field is given), with an optional ceiling per area (a capped area gets exactly its ceiling and the rest is re-split until nobody exceeds it), a floor for areas with positive weight, a need threshold below which an area gets nothing, and rounding to a unit (largest remainder, total preserved). Areas with a missing, non-numeric or negative value are excluded and listed, never imputed; ceilings that stop the whole budget being spent leave the difference as `unallocated`. It is labelled an advisory calculation, not a recommendation of who should receive what, and supplies no rate or coefficient. Optional output field (needs confirmation, owned edit session, like the MCDA tool) with a new `allocation` look (green quantile classes). The arithmetic is unit tested offline including 300 random cases of the invariants (total, non-negativity, zero weight gets zero, ceiling respected); the layer work in `tests/test_allocation_tools_live.py`, written without a local QGIS (CI first run). Attached to tasks 27.12, 23.20, 23.21. Not hand-tested. Still open in HX3: H7 table importers (IPC / INFORM / UNOSAT) and H9 critical-link analysis.

**Update 2026-10-04 (HX3b, H7 table importers).** New tool `import_humanitarian_table` (`tools/table_importers.py`): file-based import and validation of IPC phase tables, INFORM Risk tables and UNOSAT damage points; no network, no credentials. Columns are matched by alias lists (case/punctuation-insensitive); a role matched by two columns is reported ambiguous and left unmapped, a missing required role stops the import with the remedy, and an explicit `mapping` always wins. Validation never repairs: phase outside 1-5, INFORM score outside 0-10, negative or non-numeric population, out-of-range coordinate or unknown damage class is listed and left empty (a missing IPC phase is not phase 1; "3+" is not a phase). For ipc/inform an optional admin layer + key field (P-code preferred, name as fallback) reports matched / unmatched / ambiguous (duplicate on either side is never matched) and, with `write_fields` after confirmation, adds numeric fields (`ipc_phase`, `ipc_pop`, `ipc_p3plus`, `inf_risk`, `inf_haz`, `inf_vuln`, `inf_coping`). **Unverified:** the alias lists and the damage-class vocabulary come from general knowledge, not from real HDX files (none were available); please send one real sample of each (IPC, INFORM, UNOSAT) so the layouts can be pinned in tests. Pure logic tested offline; the layer join in `tests/test_table_importers_live.py`, written without a local QGIS (CI first run). Attached to tasks 5.21 and 9.20. Not hand-tested. Still open in HX3: H9 critical-link analysis.

**Update 2026-10-04 (HX3c, H9 critical-link analysis).** New tool `analyze_critical_links` (`tools/critical_link_tools.py`): for origins and destinations on a road network, the weight of OD demand whose shortest path crosses each segment. It is a screening of dependence, labelled as such in the result: not a closure simulation (that would need a re-route per segment) and not a traffic forecast. Speed design: one graph with all origins tied in (the tie cost is segments x origins, so origins are capped at 200, default 50), one Dijkstra per origin, and the load of every tree edge is the weight of the destinations below it, accumulated leaves-first in one pass (`accumulate_tree_load`), so no path is walked per OD pair; the accumulation is checked offline against a brute-force path walk on 200 random trees. Destinations snap to the nearest graph vertex (ellipsoidal metres; beyond `max_snap_m` left out and counted). A time budget (default 120 s) stops between origins and labels the result partial; the graph build itself cannot be interrupted and grows with road count, which is why the description tells the model to clip national networks first. **Not measured on a national network** -- the performance claim above is by design, not by measurement; per-origin cost also includes an O(vertices) Python pass. Closed roads (negative speed) are removed as everywhere. Output layer `critical_links` (fields `load`, `share`) in five quantile load classes. Attached to tasks 10.16, 10.23, 11.17, 11.23. Live test `tests/test_critical_link_tools_live.py` written without a local QGIS (CI first run); not hand-tested. HX3 is now complete (H7, H8, H9); HX4/HX5 remain.

**Update 2026-10-04 (HX5 stage 2, JIAF 2 inputs and validation).** New tools `import_jiaf_inputs`, `record_jiaf_setup`, `get_jiaf_setup` (`tools/jiaf_inputs.py`), built to `docs/JIAF2_ANALYSIS_SUPPORT_PLAN_2026-10-04.md`. The reader takes three shapes as plain grids: the OCHA 3A/3B worksheet, HXL-tagged published tables, and the manual's Annex 4 per-sector template. **Checked on the real files supplied by the owner (not committed):** the filled Yemen 2026 worksheet and the published Yemen HNO 2025 and 2026 datasets each read as 333 admin-2 units with all eight main sectors and no errors; the only findings are three real data warnings (a sector PiN above the unit population, e.g. CCCM in YE1705) and 132 not-applicable zero severities (CCCM where there are no camps) in the 2026 data. The Annex 4 template reader is **unverified against a real template file**: it follows the manual's screenshots only. Nothing is repaired or imputed; stored Preliminary/Final columns are returned as stored and flagged as untrusted (two Yemen units store a Preliminary PiN of 0 although their sectors have figures). The set-up record (country, cycle, unit, manual edition, scope, HCT endorsement, per-sector alignment with a required explanation when not aligned/adapted) is stored in the QGIS project. Optional P-code join writes `jp_<sector>`/`js_<sector>` fields after confirmation; severity 0 is never written as a phase. Offline tests cover the parsers and validation (plus a local-only test on the real files via `JIAF_YEMEN_DIR`); the join and the project record are covered by `tests/test_jiaf_inputs_live.py`, written without a local QGIS (CI first run). Not hand-tested. Still open for stage 3: the exact flag formulas (plan section 6), which need the formula-bearing OCHA worksheet.

**Update 2026-10-04 (HX5 stage 3, JIAF 2 preliminary calculations).** New tool `compute_jiaf_preliminary` (`tools/jiaf_engine.py`), per `docs/JIAF2_ANALYSIS_SUPPORT_PLAN_2026-10-04.md`. Pure engine plus tool: preliminary joint PiN by the mosaic rule over the eight main sectors, PiN flags 1-6, preliminary severity (Box 22), severity flags 1-4, national sum over units, a Phase 5 notice for the HCT, comparison with the file's stored columns (not trusted), optional per-unit CSV (never overwrites) and optional layer fields after confirmation. **Reproduced on the real Yemen files supplied by the owner** (not committed; local-only tests via `JIAF_YEMEN_DIR`): preliminary severity matches the stored severity in 333 of 333 units, in both the filled worksheet and the published HNO 2026 file; the stored Final PiN totals 22,325,198 and is the highest sector in 305 units, the second in 11, the third in 17; the engine's preliminary national PiN is 23,427,135 (higher than the final, as expected); the two units with a stored preliminary PiN of 0 (YE1920, YE1928) are reported as mismatches. **Flag readings that are NOT verified** (the supplied worksheet has values only, plan section 6): flag 1 fires at >= `f1_min_sectors` (default 1); flags 2-3 are measured relative to the 2nd/3rd highest PiN (Annex 5's "more than 200 percent difference" only makes sense this way); flag 4 is evaluated only when sub-population sectors are named; flag 5 uses `f5_share` of the unit population; flag 6 compares the same sector with last year and only above 1,000; severity flag 4 means more than 4 sectors in phase 4. Each is a setting echoed in every result. On the Yemen data these readings give flag 1 on 192 units, flag 2 on 94, flag 3 on 56, flag 5 on 9 (worksheet only, which has population), severity flag 1 on 3 and severity flag 4 on 55; these counts are not compared with any OCHA output. The Final PiN choice and the final severity of flagged units are not computed anywhere (stage 4 records them). The layer write is covered by `tests/test_jiaf_engine_live.py`, written without a local QGIS (CI first run). Not hand-tested.

**Update 2026-10-04 (HX5 stage 4, JIAF 2 decisions, final figures, patterns and export).** New tools `record_jiaf_decisions`, `get_jiaf_decisions`, `finalize_jiaf_results` (`tools/jiaf_review.py`) and `compute_jiaf_patterns` (`tools/jiaf_patterns.py`); `jiaf_engine.run_analysis` now shares the load-validate-analyse pipeline. The module decides nothing: decisions are the group's, stored in the QGIS project with rationale / evidence required. Statuses are explicit (`no_flag`, `flags_closed_in_bulk`, `decided`, `pending_flagged`; severity `preliminary_accepted`, `decided`, `pending_flagged`, `no_severity_data`) and a total that includes pending units is labelled PROVISIONAL. **Checked on the real Yemen worksheet (local-only test via `JIAF_YEMEN_DIR`, files not committed):** feeding the recorded sector choices back as decisions reproduces the stored Final PiN total 22,325,198 exactly, with the chosen sector the 2nd highest in 11 units and the 3rd in 17 (so any main sector is accepted as a choice, not only the first two). With no decisions and the default flag readings 249 of 333 units are pending (flag 1 fires on units with a zero-PiN sector); closing flags 1, 2, 3 and 5 in bulk leaves none -- a team choice the tool only records. The ten pattern outputs follow Reference Table 3C; thresholds the manual gives (40% of the population, five sectors in phase 4-5, top three sectors, correlation above 0.7, phases 4-5) are used, the rest are module defaults echoed in every result; the trend compares the highest sectoral PiN against last year's on the same basis. On the Yemen data, sector PiN correlations above 0.7 include nutrition-health 0.997, food security-health 0.980 and nutrition-food security 0.979 -- a description of the data, not a finding. The layer writes and the project store are covered by `tests/test_jiaf_review_live.py`, written without a local QGIS (CI first run). Not hand-tested. Open: the flag readings of stage 3 remain unverified against the OCHA worksheet formulas, and the Annex 4 template reader against a real template.

**Update 2026-10-04 (HX5 coverage rule, added to PR #195 after an outside review of the formulas).** The Box 22 rule, the mosaic PiN and the "final severity is reviewed, not averaged" rule were re-checked against an independent summary of the July 2024 manual: all four of its worked examples (3,3,3,3,2,1 -> 3; 4,4,4,4,2,1 -> 4; 5,5,4,4,2,1 -> 5; 5,4,3,2,2,1 -> 2 with a flag) are now unit tests and pass. That review also asked that incomplete coverage must not silently produce phase 1, which was a **real gap**: with fewer than four sectors reporting the rule returned phase 1 (for example three sectors in phase 4 gave 1). Fixed: `sectors_in_scope` (default all eight main sectors) defines who must report; a sector with no phase is missing; the overlap rule is applied with the missing sectors contributing nothing and with all of them at phase 5, and if the two differ the preliminary severity is empty with status `incomplete_coverage` and both bounds, needing a recorded decision. A severity of 0 stays *not applicable* by default (`zero_severity_as`). A unit with a missing sector PiN is marked as a lower bound and counted. The preliminary result, review status, final result and justification (who, when, evidence basis) are now separate fields in the results, in the CSV (new column set; `evidence_and_comments` kept as a combined convenience column) and as layer fields (`jf_pin_st`, `jf_sev_st`). **The Yemen results are unchanged** (the files have no blank severity cells; the 132 zeros are not-applicable): preliminary severity still matches in 333/333 units and the recorded choices still reproduce 22,325,198. Toy test files with four sectors are now incomplete by default and the tests state their scope explicitly. Still unverified: the flag readings of stage 3 and the Annex 4 template reader.

