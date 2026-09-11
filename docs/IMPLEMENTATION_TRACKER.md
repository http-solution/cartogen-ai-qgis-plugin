# Cartogen AI — Implementation Tracker

**Last updated:** 2026-08-31, against v1.4.4 (131 tools, 814 tests — see `docs/BUG_TRACKER.md`
for the known-baseline breakdown). Previously stamped v1.4.1, which predated the task-register
integration ([1.4.2]-[1.4.4]) and the 2026-08-31 UX/documentation audit fixes below — re-synced
here, since a tracker that lags the code defeats its own stated purpose.

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

### 1.4 GDPR / data-protection alignment

**Added 2026-08-31**, full review completed 2026-09-01: `docs/GDPR_COMPLIANCE_REVIEW.docx` --
13 findings against GDPR's articles, each with file:line evidence. Summary of legal framing: the
deploying organization is the controller; each cloud provider (OpenRouter, Gemini, OpenAI,
Claude) is a sub-processor via the org's own direct account, not via Cartogen AI -- confirmed by
reading every provider client, all of which call that provider's own official API directly, with
no Cartogen-operated intermediary live today (the "Cartogen AI (Hosted)" option in Settings is a
stub pointed at an undeployed placeholder domain).

**1 CRITICAL finding:** global memory notes (`agent/memory.py`) have no deletion path anywhere
in the code -- always-on, machine-wide, indefinite retention, no `clear_global_notes()` method
exists. See `SECURITY.md`'s Data Protection section for detail.

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

## 2. Open items blocked on this sandbox's environment (not a decision, not a bug)

- **Live-QGIS verification pass — partially closed 2026-08-22.** The plugin now loads and the
  dock widget works in a real QGIS session (see §1.2) — the "does it even load" half of this
  gap, the largest single piece, is closed. What's not yet done: `docs/RELEASE_SMOKE_TEST.md`'s
  full 16-category checklist (one representative tool per category) hasn't been run row by row,
  so most of the 131-tool registry is still "correct per the code and test suite" only. Worth
  running before a public release, not before further local dev.
- **`generate_html_dashboard` connectivity requirement** — carried forward unchanged from prior
  review rounds; no new information available from this sandbox.
- **No git remote on this repo.** `main` has 5 local commits and no remote configured — nothing
  is on GitHub yet. Blocks the sync workflow, public Releases, plugins.qgis.org submission, and
  anything that references a public repo URL. External action, not a code change.
- **Test baseline is 2 failures, not the documented 1 — specific to the FUSE sandbox.** A full
  run on 2026-08-21 in that sandbox gives 691 tests, **2 failures + 6 errors + 13 skipped**. The
  extra one is `tests/test_export_tools.py::TestGenerateHtmlDashboardConnectivityNote` — it fails
  when `folium` (an optional dependency) is absent, because the test patches `QGIS_AVAILABLE` but
  has no corresponding optional-dependency guard, so it fails where the rest of the suite skips.
  Environmental, not a code defect — the tool returned its documented graceful-degradation error
  correctly. Recommended fix and the reasoning for flagging rather than applying it:
  `docs/archive/PRO_TIER_BUILD_PLAN_2026-08-21.md` §9.1. **2026-08-22, on a normal (non-FUSE) local
  machine with `folium` installed:** 691 tests, 0 failures, 0 errors, 1 skipped — see
  `docs/BUG_TRACKER.md`'s 2026-08-22 baseline entry. The FUSE-specific failures don't reproduce
  outside that sandbox, and the optional-dependency guard has since been added (see
  `CHANGELOG.md`), so the test now skips cleanly on any machine without `folium` instead of
  failing. Current baseline: **691 tests, 0 failures, 0 errors, 14 skipped.**
- ~~`cartogen-ai-pro/` and `cartogen-ai-enterprise/` exist as empty directories~~ **Resolved
  2026-08-22** — both now hold a placeholder `README.md` pointing at
  `docs/archive/OPEN_CORE_REPO_STRATEGY.md` and (for Enterprise) the §1.3 licensing blocker, so an empty
  directory no longer misreads as "the private repo exists."
- **Repo rename / GitHub collaborator items** — external GitHub actions, not verifiable or
  actionable from this sandbox. Source: `docs/archive/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md`.

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
| `BUG_TRACKER.md` | **Living tracker**, not frozen — update as bugs are found/fixed. |
| `CHANGELOG.md` | **Living log**, not frozen — the authoritative fix/feature history. |

---

## How to keep this current

When you close an item above: move it to §4 with a one-line summary and the version it shipped
in, and update the "Last updated" line at the top. When you find something newly open: add it to
the right section above with a source reference — don't let it live only in a chat response or a
session summary that won't survive past this session.
