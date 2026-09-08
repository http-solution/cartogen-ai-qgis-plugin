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
