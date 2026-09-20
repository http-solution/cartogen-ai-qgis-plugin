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
of these docs now describe things that have since changed. For example,
`docs/archive/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` still references "134 tools" throughout (its own
proposed Community/Pro split, and its "verified against the live 134-tool registry" claim) —
true when it was written, now stale, since the registry is 131 as of this doc. This doc exists
to be the current, living answer instead of making anyone cross-reference nine dated files to
figure out what's real today. When something below gets resolved, update this file in the same
change (per `CONTRIBUTING.md` §2's "don't let a status label go stale" rule) — don't edit the
frozen source docs themselves.

---

## 1. Open items that need a human decision (not an engineering call)

These three are explicitly **not** something an agent should decide or silently implement —
each involves a real product, UX, legal, or environmental-verification tradeoff. Consistent
with `CONTRIBUTING.md` §3 ("flag, don't silently fix if it's a judgment call").

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

### 1.3 Tier restructure — licensing path

**Source:** `docs/archive/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` §3.
The proposed Community ("open source but locked")/Pro (closed code)/Enterprise structure is not
achievable as a simple feature flag on the current GPL v2 codebase — the source doc lays out
three real paths (re-license entirely, split into an open-core + closed-module architecture, or
stay full GPL v2 and drop the "locked"/"closed" framing) and states plainly this isn't an
engineering decision. Everything in that proposal's §6 engineering build-out (the Cartogen API
gateway, tier gating mechanism, closed-source packaging) is blocked on this being resolved first.

**Needs:** real legal counsel, then a business decision from Alaa. Not something to build
toward until it's resolved — starting the engineering work first would mean building against
an unknown target.

**Narrowed 2026-08-21** by `docs/archive/PRO_TIER_BUILD_PLAN_2026-08-21.md` §4. This item blocks
*Enterprise* (RBAC/SSO/M365, closed-source packaging, license-key validation) and it blocks the
restrictive tier model in `docs/archive/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`. It does **not** block the
Professional tier under the already-decided open-core model: a hosted gateway sells access to a
service, distributes no code, and needs no license key (the virtual key authenticates
server-side), so GPL v2 is not implicated. Pro can be built now; Enterprise still cannot.

**Confirmed 2026-08-22 by Alaa:** Model A (gateway as convenience — `docs/PRODUCT_TIERS.md`/
`docs/archive/OPEN_CORE_REPO_STRATEGY.md`) over Model B (gateway as gate —
`docs/archive/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`). Everything built toward the Professional tier
so far (the plugin-side provider wiring, the `service/website/` billing hardening in
§4 below) assumes Model A. Model B remains frozen/unresolved and isn't being built toward.

**Re-confirmed still accurate, 2026-09-18**, prompted by an external audit that initially (and
incorrectly) read `docs/archive/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`'s 3-provider Community
restriction language as if it were a settled, active policy contradicting the shipped 5/6-provider
product. It isn't — the audit withdrew that finding once shown this section and
`docs/PRODUCT_TIERS.md`'s own "draft for a decision, not yet a settled fact" framing. Restated
plainly since an outside reader keeps tripping on it: **today's shipped Community edition has
never been provider-restricted, is not blocked on this item resolving, and nothing about §1.3
being open threatens that.** This item blocks *future* Enterprise/restrictive-tier work only, per
the narrowing two paragraphs above — it does not describe current product behavior.

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
has been fixed yet -- awaiting Baron's go-ahead to change code, per Hermes Charter Rule 8.

**Update, 2026-09-08, later -- full independent 5-dimension review of *this* repo (`cartogen-ai`), not assumed to mirror the community-line review above:** wrote `docs/CODE_REVIEW_2026-09-08.md`, a fresh pass over this repo's own, larger, more-evolved codebase (the 27-point architecture review's 15 commits, the temporal-dashboard feature). Mockups/incomplete-UI: clean. Bugs: no new functional bugs beyond one documentation-hygiene item (this file's own "not yet committed" annotations for several 27-point-review items and other work are stale -- `git log`/`git status` confirm all of it is already committed; worth a future pass to reconcile every such claim against `git log`). Uncompleted work: none -- working tree fully clean as of `9fcc939`. GDPR: `docs/GDPR_COMPLIANCE_REVIEW.docx` confirmed byte-identical to `cartogen-ai-community`'s copy (same 2026-09-01 date, same commit `01d853f` reference, never updated for anything since) -- F1 re-confirmed fixed here, F6/F7/F2 (and by extension F3-F5/F8-F13) re-confirmed still open, no new GDPR findings. **Security: one new CRITICAL finding** -- `execute_pyqgis_script`'s sandbox is fully bypassable via exception-traceback frame-walking (`__traceback__`/`tb_frame`/`f_back`/`f_globals`), reaching the real unrestricted `builtins` module and from there `open`/`__import__`/`eval`/`exec`, none of which the current `_BLOCKED_DUNDER_ATTRS` denylist inspects. Live-reproduced, not theoretical: an exact copy of this file's own `_validate_script_safety`/exec pattern accepted the exploit script and successfully wrote a real file to disk from inside the restricted context. Full writeup and recommended fix: `docs/BUG_TRACKER.md` NEW-2026-09-08-1, and `docs/CODE_REVIEW_2026-09-08.md` §4.1. Not fixed yet -- awaiting Baron's go-ahead to change code, per Hermes Charter Rule 8, and given the severity this is recommended as the first fix once approval is given, ahead of the other open items above.

**Update, 2026-09-08, later still -- Baron: "go ahead":** fixed and verified. Extended `_BLOCKED_DUNDER_ATTRS` in `agent/tools/system_tools.py` with the frame/traceback attribute names (`f_back`, `f_globals`, `f_locals`, `f_builtins`, `f_code`, `gi_frame`, `cr_frame`, `ag_frame`, `tb_frame`, `tb_next`, `__traceback__`), closing the escape described above -- confirmed by re-running the exact PoC through `_validate_script_safety` (now rejected) both before and after the fix. Added two regression tests to `tests/test_new_tools.py` (the PoC end to end via `execute_pyqgis_script`, plus each new attribute name checked individually). Full suite re-verified: 1219 tests (1217 + 2 new), same 1 known DNS-dependent failure, 0 errors, 0 other new failures. `docs/BUG_TRACKER.md`'s NEW-2026-09-08-1 entry moved from Open to Fixed (recent), status `fixed-verified`.

**Update, 2026-09-08, later still -- Baron: "go through the pending task and solve them one by one":** worked the rest of this review's fix plan in priority order. (1) `BUG-2026-09-08-1` (HTTPS-claim gap): `normalize_account_base_url()` now rejects plain `http` for any host except `localhost`/`127.0.0.1`/`::1`, closing the gap between `account_dialog.py`'s "sent only over HTTPS" text and the code -- 3 new tests in `tests/test_account_client.py`. (2) `BUG-2026-09-05-2` (`calculate_service_area` degenerate-network failure): both `native:serviceareafrompoint` and `native:convexhull` calls were sharing one try/except spanning the whole multi-facility loop, so one facility hitting the known small-network edge case aborted every other facility's already-computed result too -- each stage is now isolated per facility (a failure is recorded in a new `skipped`/`warnings` result field and that facility is skipped, or, if only the hull step fails, its already-built reachable-network lines are kept); this does not change the underlying QGIS behavior on a 1-2 segment network (this session has no live QGIS to re-verify that against), it stops that known edge case from taking unrelated facilities down with it -- 3 new tests in `tests/test_logistics_tools.py`, mocked reproductions of both exact error strings recorded in the bug tracker. (3) `NEW-2026-09-08-2` (registry staleness): reconciled all 10 stale "not yet committed" claims in `docs/MASTER_TASK_REGISTRY.md` against `git log`, appending a dated `[Corrected, 2026-09-08]` note with the actual commit hash to each rather than rewriting the original journal entries. (4) `BUG-2026-09-08-2` (GDPR/Hosted-Account gap): wrote `docs/GDPR_HOSTED_ACCOUNT_ADDENDUM_2026-09-08.md`, a verified personal-data inventory for the Hosted-Account feature (what's collected, where it goes, how it's stored) -- explicitly a draft engineering input for Baron/compliance review, not a compliance determination; the bug stays `open` pending Baron's actual decision (extend the official GDPR review vs. defer/disable the feature). Full suite re-verified after every code change: 1225 tests (1219 + 6 new), same 1 known DNS-dependent failure, 0 errors, 0 other new failures. Still open, genuinely needing Baron's judgment rather than an assumption: the route-straight-line-fallback and incident-reporting-vocabulary design decisions from `docs/MASTER_TASK_REGISTRY.md`'s standing queue, and the Hosted-Account feature's overall disposition.

**Update, 2026-09-08, later still -- Baron: "Ship, extend GDPR review":** implemented the Hosted-Account feature's disposition decision. (1) Added an in-app privacy notice (`privacy_notice_label`) to `ui/account_dialog.py`, shown before registration/login -- the concrete UI gap the addendum flagged. (2) Extended `docs/GDPR_COMPLIANCE_REVIEW.docx` directly (edited `word/document.xml`, following the docx skill's edit-existing-document approach, then validated with `validate.py` and a rendered-PDF visual check against the original's exact styling) to formally cover the feature: Finding F14 (MEDIUM, transparency gap now closed, deletion/export and retention gaps remain), Recommendation R11, two new Section 4 data-inventory rows (Hosted-Account email/name/password, and the session token separately since it behaves differently under every column), three new Appendix -- Files Reviewed entries, and an Executive Summary extension note plus updated finding count (thirteen to fourteen). (3) Also corrected the addendum's own inaccurate claim (verified via `git log --diff-filter=A --follow` on `agent/account.py`) that the standing review predated the feature -- `account.py` was added 2026-08-28, before the review's own 2026-09-01 date; what actually happened is a scope gap (the review's file list never covered it), not a timing gap, and the addendum now says so. `docs/BUG_TRACKER.md`'s BUG-2026-09-08-2 entry moved from Open to Fixed accordingly. Full suite re-verified clean after the code change: 1225 tests, same 1 known DNS-dependent failure, 0 errors, 0 other new failures. What is explicitly NOT closed by this work, and stays tracked rather than silently dropped: no in-app account-deletion/export path for this feature's data (R11 -- today it's server-side only, no self-service UI), and no documented retention policy for whatever operates the configured `base_url` -- both are organizational/server-side facts this codebase has no visibility into, not code defects to fix here.

**Update, 2026-09-11 -- Baron: v1.7.0 "Security & Logistics" release, workstream 1 (GDPR
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

**Needs:** Baron's decision on whether to pursue this at all, and at what scope; if pursued, a
live-LLM evaluation harness comparing before/after doesn't exist yet and would need building first.

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

**Needs:** Baron's decision, ideally made alongside point 18's since they're two angles on the
same underlying proposal.

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

**Needs:** Baron's decision on whether this convention is worth adopting for this product's actual
user base at all, and if so, at what enforcement level.

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

---

### 1.9 `run_allowlisted_processing_algorithm` outputs are always fully visible, even purely-internal ones

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

---

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
  2026-08-22** — both now hold a placeholder `README.md` pointing at
  `docs/archive/OPEN_CORE_REPO_STRATEGY.md` and (for Enterprise) the §1.3 licensing blocker, so an empty
  directory no longer misreads as "the private repo exists."
- **Repo rename / GitHub collaborator items** — external GitHub actions, not verifiable or
  actionable from this sandbox. Source: `docs/archive/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md`.
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
  - **What's still open:** the CI-matrix item stays open until an actual GitHub Actions run is
    confirmed green (per the user's own instruction, this is the next step — validate the pinned
    QGIS CI jobs before cutting `1.16.0-rc2`), and §1.10's exact-ZIP clean-profile install/upgrade
    test remains genuinely blocked on a real interactive QGIS GUI session this sandbox can't
    provide.

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
    that traced to an explicitly-marked, never-merged draft proposal (`docs/archive/
    TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`, §1.3 above) being misread as current policy — the
    audit withdrew the finding once shown the exact quotes. Two small real documentation fixes
    shipped from the exchange regardless: a stale tool count in `docs/PRODUCT_TIERS.md`, and a
    leftover "Internal/commercial use" phrase in `README.md` inconsistent with the rest of that
    page's Community/GPL framing.
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
  version/tool-count staleness in this doc, `README.md`, `DOCUMENTATION.md`, and
  `docs/PRODUCT_TIERS.md`. Not done in this pass (tracked, not forgotten): splitting
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

## 5. Source doc index (all frozen/historical unless noted; frozen docs live in `docs/archive/`)

| Doc | Status |
|---|---|
| `docs/archive/STATUS_REVIEW_2026-08-20.md` | Frozen snapshot, v1.2.21. Superseded by this tracker for "what's open." |
| `docs/archive/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` | Frozen proposal, not built. §3 licensing question is the live blocker — see §1.3 above. Its own 2026-08-31 correction addendum flags the now-stale "134 tools" figure (not re-frozen, since that's a factual pointer to the current number, not new proposal content). |
| `docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md` | Frozen review. All 4 follow-up tasks from this round are closed (§4 above). |
| `docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md` | Frozen audit. §3's decision is the live item in §1.1 above. |
| `docs/archive/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md` | Frozen plan. Execution is the live item in §1.2 above. |
| `docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md` | Frozen strategy doc; its own §4 was updated 2026-08-21 with real smoke-test results (not re-frozen, since that update was factual correction, not new proposal content). |
| `docs/archive/JIAF_MULTISECTOR_COMPOSITE_SPEC.md` | Frozen spec, deliberately unbuilt — see §3 above. |
| `docs/archive/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md` | Frozen review — repo-rename item still open, §2 above. |
| `docs/archive/PRO_TIER_BUILD_PLAN_2026-08-21.md` | Frozen plan, 2026-08-21. Phased Professional-tier build plan; §4 narrows §1.3 above, §9 records findings folded into §2. |
| `RELEASE_SMOKE_TEST.md` | **Living checklist**, not frozen — update when tools/categories change. |
| `LIVE_TEST_SCENARIOS.md` | **Living checklist**, added 2026-09-16 — multi-turn workflow scenarios a single-prompt smoke test can't catch (task routing, confirmation gates, map-visualization/technical-analysis accuracy). |
| `PRODUCT_TIERS.md` | **Living positioning doc**, not frozen — §1.3 above is its live open question. |
| `BUG_TRACKER.md` | **Living tracker**, not frozen — update as bugs are found/fixed. |
| `CHANGELOG.md` | **Living log**, not frozen — the authoritative fix/feature history. |

---

## How to keep this current

When you close an item above: move it to §4 with a one-line summary and the version it shipped
in, and update the "Last updated" line at the top. When you find something newly open: add it to
the right section above with a source reference — don't let it live only in a chat response or a
session summary that won't survive past this session.
