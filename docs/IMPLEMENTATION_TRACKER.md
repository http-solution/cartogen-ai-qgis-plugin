# Cartogen AI — Implementation Tracker

**Last updated:** 2026-08-21, against v1.4.1 (131 tools, 691 tests — see `docs/BUG_TRACKER.md`
for the known-baseline breakdown). Previously stamped v1.2.33, which predated the whole
namespace-package restructure ([1.4.0]) and BUG-2026-08-21-6/-7 — re-synced here, since a
tracker that lags the code defeats its own stated purpose.

This is the one place to look for "what's actually still open right now." Every review, audit,
and spec doc in `docs/` up to this point is a **dated, frozen snapshot** — per `CONTRIBUTING.md`
§2's own convention, those are never edited after the fact (with rare same-day correction
addenda, like `STATUS_REVIEW_2026-08-20.md`'s own "Post-review update" note — even that doc says
so explicitly rather than silently rewriting itself). The result is the same either way: several
of these docs now describe things that have since changed. For example,
`TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` still references "134 tools" throughout (its own
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

### 1.1 Destructive-action confirmation gate — 4 humanitarian analysis tools

**Source:** `docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md` §3.
`calculate_severity_index`, `calculate_damage_exposure_severity`, `calculate_population_in_need`,
and `calculate_presence_gap` all write a new field to a layer in place, same category of
mutation as `field_calculator`/`calculate_area`/`calculate_length` (which already require
preview/confirm). These four do not. Three options were laid out, not picked:
1. Leave as-is — these are idempotent (re-running just recomputes the same field) and lower
   real-harm than a geometry-mutating op, so the friction may not be worth it.
2. Add the same preview/confirm gate as the other four mutation tools, for consistency.
3. Narrow `SECURITY.md` §5's stated scope so it's accurate either way, without changing tool
   behavior.

**Needs:** a product/UX call from Alaa — friction vs. consistency tradeoff, not a bug.

### 1.2 `ui/dock_widget.py` class split — execution

**Source:** `docs/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md`.
The recommended split (`ChatTabWidget`/`TasksTabWidget` extracted from the monolithic dock
widget) is fully planned, with the real coupling points identified (3 tabs, shared signals,
shared `agent`/`task_manager` reference). What's NOT done — and can't safely be done from this
sandbox — is the actual refactor: `dock_widget.py` imports `qgis.PyQt`/`qgis.core`
unconditionally with no `QGIS_AVAILABLE` fallback, so it cannot be imported, run, or visually
verified outside a real QGIS process. A blind split here risks shipping a broken dock panel
behind a fully green but non-representative test suite.

**Needs:** a real QGIS session to execute against — this is an environmental blocker, not a
decision Alaa needs to make, but it can't be delegated to any agent working from this sandbox
either. Flagged here so it doesn't get silently attempted by a future session that forgets why
it was deferred.

### 1.3 Tier restructure — licensing path

**Source:** `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` §3.
The proposed Community ("open source but locked")/Pro (closed code)/Enterprise structure is not
achievable as a simple feature flag on the current GPL v2 codebase — the source doc lays out
three real paths (re-license entirely, split into an open-core + closed-module architecture, or
stay full GPL v2 and drop the "locked"/"closed" framing) and states plainly this isn't an
engineering decision. Everything in that proposal's §6 engineering build-out (the Cartogen API
gateway, tier gating mechanism, closed-source packaging) is blocked on this being resolved first.

**Needs:** real legal counsel, then a business decision from Alaa. Not something to build
toward until it's resolved — starting the engineering work first would mean building against
an unknown target.

**Narrowed 2026-08-21** by `docs/PRO_TIER_BUILD_PLAN_2026-08-21.md` §4. This item blocks
*Enterprise* (RBAC/SSO/M365, closed-source packaging, license-key validation) and it blocks the
restrictive tier model in `TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`. It does **not** block the
Professional tier under the already-decided open-core model: a hosted gateway sells access to a
service, distributes no code, and needs no license key (the virtual key authenticates
server-side), so GPL v2 is not implicated. Pro can be built now; Enterprise still cannot.

---

## 2. Open items blocked on this sandbox's environment (not a decision, not a bug)

- **Live-QGIS verification pass.** Every tool in the registry is "correct per the code and test
  suite," not "confirmed working in a real QGIS session" — the single largest standing gap
  across every review round this project has had. `docs/RELEASE_SMOKE_TEST.md` exists
  specifically to make this a bounded, ~15-minute human task instead of an open-ended one — see
  that doc for what's already been checked for accuracy (2026-08-21) vs. actually run live
  (never, in this sandbox).
- **`generate_html_dashboard` connectivity requirement** — carried forward unchanged from prior
  review rounds; no new information available from this sandbox.
- **No git remote on this repo.** `main` has 5 local commits and no remote configured — nothing
  is on GitHub yet. Blocks the sync workflow, public Releases, plugins.qgis.org submission, and
  anything that references a public repo URL. External action, not a code change.
- **Test baseline is 2 failures, not the documented 1.** A full run on 2026-08-21 gives 691 tests,
  **2 failures + 6 errors + 13 skipped**. The extra one is
  `tests/test_export_tools.py::TestGenerateHtmlDashboardConnectivityNote` — it fails when `folium`
  (an optional dependency) is absent, because the test patches `QGIS_AVAILABLE` but has no
  corresponding optional-dependency guard, so it fails where the rest of the suite skips.
  Environmental, not a code defect — the tool returned its documented graceful-degradation error
  correctly. Recommended fix and the reasoning for flagging rather than applying it:
  `docs/PRO_TIER_BUILD_PLAN_2026-08-21.md` §9.1.
- **`cartogen-ai-pro/` and `cartogen-ai-enterprise/` exist as empty directories** beside this repo
  at `C:\Cartogen-AI-Core\`. Harmless, but they read as "the private repo exists." Remove them or
  add a placeholder README pointing at `docs/OPEN_CORE_REPO_STRATEGY.md`.
- **Repo rename / GitHub collaborator items** — external GitHub actions, not verifiable or
  actionable from this sandbox. Source: `docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md`.

## 3. Deliberately deferred (not a gap — a stated design choice)

- **`docs/JIAF_MULTISECTOR_COMPOSITE_SPEC.md`** — spec-only, intentionally not built. Combining
  per-sector severity indices into one intersectoral estimate needs a real JIAF Mosaic Method
  human-validation workshop step that a formula can't substitute for. Revisit only if that
  workshop happens.
- **`docs/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md` §3.3 (no-go zones)** — prompt-guidance-only by
  design, not a missing tool. §3.1/§3.2 (`analyze_incident_trend`, `score_route_incident_risk`)
  are shipped.

---

## 4. Resolved since the last full status review (informational — for traceability)

Everything below was open as of `STATUS_REVIEW_2026-08-20.md` (v1.2.21) or a later round, and is
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

---

## 5. Source doc index (all frozen/historical unless noted)

| Doc | Status |
|---|---|
| `STATUS_REVIEW_2026-08-20.md` | Frozen snapshot, v1.2.21. Superseded by this tracker for "what's open." |
| `TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` | Frozen proposal, not built. §3 licensing question is the live blocker — see §1.3 above. |
| `ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md` | Frozen review. All 4 follow-up tasks from this round are closed (§4 above). |
| `DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md` | Frozen audit. §3's decision is the live item in §1.1 above. |
| `DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md` | Frozen plan. Execution is the live item in §1.2 above. |
| `ROUTE_OPTIMIZATION_STRATEGY.md` | Frozen strategy doc; its own §4 was updated 2026-08-21 with real smoke-test results (not re-frozen, since that update was factual correction, not new proposal content). |
| `JIAF_MULTISECTOR_COMPOSITE_SPEC.md` | Frozen spec, deliberately unbuilt — see §3 above. |
| `SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md` | Frozen review — repo-rename item still open, §2 above. |
| `PRO_TIER_BUILD_PLAN_2026-08-21.md` | Frozen plan, 2026-08-21. Phased Professional-tier build plan; §4 narrows §1.3 above, §9 records findings folded into §2. |
| `RELEASE_SMOKE_TEST.md` | **Living checklist**, not frozen — update when tools/categories change. |
| `BUG_TRACKER.md` | **Living tracker**, not frozen — update as bugs are found/fixed. |
| `CHANGELOG.md` | **Living log**, not frozen — the authoritative fix/feature history. |

---

## How to keep this current

When you close an item above: move it to §4 with a one-line summary and the version it shipped
in, and update the "Last updated" line at the top. When you find something newly open: add it to
the right section above with a source reference — don't let it live only in a chat response or a
session summary that won't survive past this session.
