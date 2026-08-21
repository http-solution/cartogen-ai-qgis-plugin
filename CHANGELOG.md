# Changelog

All notable changes to Cartogen AI are documented here, newest first. Format
loosely follows [Keep a Changelog](https://keepachangelog.com/).

> **Repo note:** this file's history up through v1.3.0 was carried over verbatim
> from the old `qgis_ai_assistant` repo as part of a from-scratch copy/restructure
> into this new `cartogen-ai` repo — it is **not** a git history migration. Full
> commit history back to v0.2.0 remains available in the old repo
> (`C:\qgis_ai_assistant`) if ever needed.

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

## [1.3.0] — 2026-08-21

**Full internal rebrand** of this root source tree, requested directly by the user: every
"QGIS AI Assistant"/`QgisAiAgent`/`qgis_ai_agent` identifier renamed to "Cartogen AI"/
`CartogenAiCore`/`cartogen_ai_core`. The second, separately distributed `Cartogen AI/cartogen_ai/`
copy tree already carried the "Cartogen AI"/`CartogenAi`/`cartogen_ai` branding and keeps its own
identity unchanged — the two trees now use distinct identifier schemes specifically so they can
still be installed side by side without colliding on install-folder name or settings-key prefix.

**Deliberately a breaking change** for existing installs of this root plugin: the QSettings key
prefix moved from `qgis_ai_agent/...` to `cartogen_ai_core/...`, so anyone upgrading in place loses
their saved API keys and provider selection and has to re-enter them once. Confirmed with the
project owner and accepted as the cost of a clean rebrand, not an oversight.

Renamed:
- Plugin entry class: `QgisAiAgent` → `CartogenAiCore` (plus `QgisAiAgentDockWidget` →
  `CartogenAiCoreDockWidget`, `QgisAiAgentSettingsDialog` → `CartogenAiCoreSettingsDialog`)
- Plugin module file: `qgis_ai_agent.py` → `cartogen_ai_core.py`
- Packaging identity: `plugin_upload.py`'s `PLUGIN_NAME` (`qgis_ai_assistant` → `cartogen_ai_core`)
- Every internal identifier across `agent/`, `ui/`, `tests/`, and the doc set — 42 files total

Left untouched, per `CONTRIBUTING.md`'s existing "frozen historical doc" convention:
`QGIS_AI_Agent_Feature_List.md`, `QGIS_AI_Agent_PRD.md`, `IMPLEMENTATION_TASK_LIST.md`, this
file's own past entries below, and the dated `STATUS_REVIEW_2026-08-20.md`/
`SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md`/`DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md`/
`PROMPT_REFINEMENT_LAYER_SPEC.md`.

A post-hoc audit of the mechanical find-and-replace (42 files, ordered string substitution) caught
and fixed two real corruptions it introduced: `metadata.txt`'s own embedded historical changelog
and `docs/BUG_TRACKER.md`'s version-numbering note both had a currently-real, currently-shipped
filename (`qgis_ai_assistant_v1.2.33.zip`, still the actual name of the last built zip in `dist/`)
accidentally rewritten to a name that doesn't exist on disk — restored by hand. Also found (not
caused by data corruption, but a logic bug): `build_cartogen_ai.py`'s own `PY_ONLY_RULES`
translation table had its search-pattern strings rewritten by the same blind replace, silently
turning both its rules into no-ops. Fixed, and while auditing that script further: hardened it with
the same scratch-file/`.git_commit_msg*` exclude-pattern guard `plugin_upload.py` already had
(`BUG-2026-08-21-5`), and added `CHANGELOG.md`/`BUG_TRACKER.md` to its own `UNTRANSLATED_DOCS` so
neither can be retroactively mistranslated by a future sync run. `.gitignore` updated for the new
`cartogen_ai_core.zip` build output alongside the old `qgis_ai_assistant.zip` entry.

691 tests, same known baseline (1 DNS-dependent failure + 6 sandbox-artifact-cleanup errors),
verified independently in both trees after the rebrand — no regressions. The copy tree itself was
**not** regenerated from source this round and keeps its existing branding/identity, per an
explicit decision to keep both trees stable and installable side by side; three dated docs
(`DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md`, `PROMPT_REFINEMENT_LAYER_SPEC.md`,
`STATUS_REVIEW_2026-08-20.md`) will stop getting their identifiers auto-translated into copy-tree
branding the next time someone *does* run a real sync, since the translation table no longer
recognizes the old identifier scheme they still use — flagged as an open design question, not
resolved here. Also noted, unrelated to this rebrand: a small, empty, unrelated `git init` scaffold
(`Cartogen AI/cartogen_ai/cartogen_ai/`, just a placeholder README and one commit, no remote) was
found sitting inside the copy tree during this audit — left untouched pending confirmation of what
it is.

## [1.2.34] — 2026-08-21

**Set up ongoing implementation/bug tracking**, requested directly by the user acting in a CTO
capacity for this project — two new living docs, `docs/BUG_TRACKER.md` and
`docs/IMPLEMENTATION_TRACKER.md`, plus README.md doc-index entries for both:

- `BUG_TRACKER.md`: currently zero known open real bugs; explicitly documents the known
  sandbox-artifact test baseline (1 DNS-dependent failure + 6 scratch-file-permission errors)
  so it's never mistaken for a new regression, and a short "fixed (recent)" log seeded from
  this session's real fixes (the two `route_optimization_prototype.py` bugs, the gemini.py
  header-auth fix).
- `IMPLEMENTATION_TRACKER.md`: consolidates every genuinely still-open item across the
  project's dated review/audit/spec docs (`STATUS_REVIEW_2026-08-20.md`,
  `TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`, `DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md`,
  `DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md`, and others) into one current doc, explicitly
  separating 3 items that need a human/product/legal decision (destructive-gate scope for 4
  humanitarian tools, the dock_widget class-split execution, and the tier-restructure licensing
  question) from items only blocked on this sandbox's lack of live QGIS access, from items
  deliberately deferred by design (JIAF composite spec). The dated source docs are left
  untouched, per `CONTRIBUTING.md` §2's existing "frozen snapshot" convention — this tracker is
  the living index on top of them, not a replacement.

No code changed. Full suite re-run as a sanity check: 691 tests, same known baseline.

## [1.2.33] — 2026-08-21

**Smoke-tested `docs/route_optimization_prototype.py`** (task #67, the last remaining item from the
routing-strategy work) — installed `osmnx`/`networkx`/`geopandas`/`rasterio`/`shapely` and actually
ran the script's cost function and routing logic for the first time, against a small hand-built
synthetic road graph + synthetic GeoTIFF DEM standing in for a live OSM/Overpass fetch (no outbound
access to Overpass or a real DEM source in this environment). Found and fixed 2 real bugs:

- `build_constrained_graph()` called `ox.graph_from_bbox(bbox=(north, south, east, west), ...)`, but
  the installed osmnx version (2.0.7) actually requires `(west, south, east, north)` — exactly the
  version-order risk the script's own comment had flagged without ever verifying it against a real
  install. Fixed and reworded the comment to state what was actually confirmed, not just what's
  theoretically possible.
- `find_constrained_route()`'s `ox.distance.nearest_nodes()` call raised `ImportError: scikit-learn
  must be installed` on the unprojected lon/lat graph this script uses — `scikit-learn` wasn't in the
  script's documented `pip install` line. Added it.
- Also confirmed (no changes needed): all 4 vehicle profiles construct without error, an unknown
  profile raises `ValueError` rather than proceeding silently, a disconnected graph returns the
  documented `{"success": False, "error": ...}` shape rather than raising, and — the actual point of
  the exercise — a synthetic route with a shorter unpaved+steep alternative correctly resolves to the
  longer paved route once the surface/slope penalties are applied (confirmed with both penalties
  together, and with each in isolation).
- Updated the script's own docstring and `docs/ROUTE_OPTIMIZATION_STRATEGY.md` §4 to state plainly
  what's now verified (cost function + routing logic, against synthetic data) versus what still isn't
  (a real downloaded road network, a real DEM, or performance at real-graph scale) — no code outside
  this standalone prototype changed, so the 691-test suite baseline is unaffected.

## [1.2.32] — 2026-08-21

**Accuracy pass on `docs/RELEASE_SMOKE_TEST.md`**, prompted by re-reading the checklist against the
current tool registry rather than assuming it was still correct since v1.2.29. Cross-checked all 16
rows against `docs/TOOLS_REFERENCE.md`, `agent/agent.py`'s `NETWORK_ONLY_TOOLS`/`TWO_PHASE_TOOLS`
sets, `agent/prompts.py`, `task_manager.py`'s status strings, and `SECURITY.md`'s section numbers.
14 of 16 rows checked out exactly as written; 2 needed a fix:

- **Humanitarian Data row**: the example prompt asked to fetch "OpenStreetMap building footprints,"
  but that conflated two different real tools — `fetch_osm_features` (genuinely OpenStreetMap/
  Overpass-sourced, `NETWORK_ONLY_TOOLS`, but has no "building footprints" framing at all) and
  `fetch_building_footprints` (the tool that actually returns building footprint geometries, but
  from Microsoft's Global ML Building Footprints dataset, not OpenStreetMap, and classified as
  `TWO_PHASE_TOOLS` not network-only). The row's own "what to verify" text ("real building
  footprint geometries") clearly meant to exercise `fetch_building_footprints`, so retargeted the
  prompt and corrected both the data-source attribution and the threading-model claim.
- **Project Management row**: "what to verify" didn't mention that `load_project` requires a
  confirmation-preview click before it replaces the open project — it's one of the destructive-
  action-gated tools (`SECURITY.md` §5). Added a note so a tester isn't confused when the load
  doesn't happen immediately.

No code changed — this is a docs-only correction to a manual checklist with no automated test, so
"verification" here means the cross-referencing above plus a final read-through, not a test run
against this file specifically. Full suite re-run as a sanity check regardless: still 691 tests,
same pre-known sandbox baseline (1 failure + 6 errors, both documented since before this file
existed, neither a real code defect).

## [1.2.31] — 2026-08-21

**Round 2 of the ENGINEERING_PRODUCT_UX_REVIEW findings, final item** — the `dock_widget.py`-split
recommendation (REVIEW §3.2), partially done and the rest deliberately deferred with a written
plan. See `docs/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md` for the full reasoning. This closes out all
four tasks from the round-2 follow-up work.

- **Done**: extracted `_read_attached_file()` (PDF/DOCX/CSV/XLSX/image/plain-text attachment
  parsing) into a new `ui/attachments.py`. This function had zero Qt/QGIS dependencies despite
  living inside `dock_widget.py`, which imports `qgis.PyQt`/`qgis.core` unconditionally with no
  `QGIS_AVAILABLE` fallback and so cannot be imported or tested outside a real QGIS process at
  all. Moving it out gives it real test coverage for the first time — 10 new tests in
  `tests/test_attachments.py`, including a real generated PDF and DOCX.
- **Not done**: splitting `QgisAiAgentDockWidget` itself into `ChatTabWidget`/`TasksTabWidget`
  classes. This sandbox cannot import, run, or visually verify a refactor of a live stateful Qt
  widget with cross-tab signal wiring and no existing tests — a blind split risks shipping a
  broken dock panel behind a fully green (but non-representative) test suite. Documented the real
  coupling points found while reading the current structure (three tabs, not two; shared
  `statusSignal`/`usageSignal`/`receiveMessageSignal`/`toolStepSignal`; one shared
  `agent`/`task_manager` reference) and a concrete plan for doing this in a real QGIS session
  instead.
- 691 tests total (was 681), same pre-known sandbox baseline as always.

## [1.2.30] — 2026-08-21

**Round 2 of the ENGINEERING_PRODUCT_UX_REVIEW findings, continued** — added session token-usage
visibility to the chat UI (REVIEW §3.2: "no cost/usage visibility in the UI despite real,
documented cost-engineering work").

- Every provider client's `complete()` now extracts a normalized `{input_tokens, output_tokens}`
  `usage` dict from the raw API response when the provider actually reported one. OpenRouter,
  OpenAI, Gemini, and the Cartogen gateway stub share `base.py`'s new
  `extract_openai_style_usage()` helper (all four go through an OpenAI-Chat-Completions-shaped
  endpoint); Claude's native `input_tokens`/`output_tokens` field names already match and are
  pulled through directly; Ollama reports under its own `eval_count`/`prompt_eval_count` field
  names, extracted separately.
- **Never fabricated as zero** when a provider/model omits usage — the `usage` key is simply
  absent from `complete()`'s return in that case, and `QgisAiAgent.get_session_usage_text()`
  returns `None` (not "0 tokens") until at least one real call has reported it, caveating the
  total explicitly when some calls did and others didn't.
- New `QgisAiAgent.session_usage`/`_accumulate_usage()`/`get_session_usage_text()` track a running
  session total — `agent.run()`'s tool-calling loop and the image-attachment direct-`complete()`
  path both feed it.
- `ui/dock_widget.py` gets a new `usage_label` below the existing status line, updated via a new
  thread-safe `usageSignal` after every turn (success or error) and after file/image attachment
  analysis.
- Deliberately **no dollar-cost estimate** — accurate per-model pricing across 5 providers needs a
  table that's guaranteed to go stale and mislead; token counts alone were the review's own
  suggested minimum bar.
- `TestProviderReturnContract`'s strict shape check extended to allow the new optional `usage` key
  without loosening what counts as a valid response shape otherwise.
- 10 new tests (usage extraction per provider, the honesty-preserving "omitted not zero" case, and
  agent-level accumulation/caveating). 681 tests total (was 671), same pre-known sandbox baseline
  as always.

## [1.2.29] — 2026-08-21

**Round 2 of the ENGINEERING_PRODUCT_UX_REVIEW findings, continued** — audited every destructive
tool for preview/confirm safety-gate coverage (REVIEW §3.2). Full method and findings in
`docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md`.

- **Fixed a real inconsistency**: `calculate_area`/`calculate_length` (`vector_tools.py`) called
  the exact same `_add_calculated_field` primitive as `field_calculator` — an in-place edit of the
  live layer's attribute table via `startEditing()`/`commitChanges()` — but weren't gated behind
  the `confirmed=True` flow `field_calculator` already requires for that same operation. Both now
  follow `field_calculator`'s exact `PREVIEW_REQUIRED` pattern.
- **Corrected doc drift**: `load_project` was already gated, but `SECURITY.md` §5's prose only
  named 2 of the then-3 gated tools. Fixed; now names all 5.
- **Flagged, deliberately not fixed** pending a product decision: 4 core humanitarian analysis
  tools (`calculate_severity_index`, `calculate_presence_gap`, `calculate_population_in_need`,
  `calculate_damage_exposure_severity`) perform the identical class of in-place mutation via a
  parallel `_write_*_to_layer` helper family in `analysis_tools.py`. Gating them trades
  consistency against inserting a confirmation click into the app's primary analytical workflow —
  see the audit doc §3 for three options and why none was applied unilaterally.
- **Reviewed and confirmed not gaps**: `execute_pyqgis_script` (protected by its AST sandbox, a
  different and already-disclosed mitigation, not a silent omission), `save_project` (normal save
  semantics), `save_workflow_preset` (low-stakes settings overwrite), and the ~120 other tools
  that create new output layers rather than mutating existing ones.
- **Regenerated `docs/TOOLS_REFERENCE.md`**, discovered stale since before v1.2.25 — it still
  listed 4 tools removed in that release (`export_attribute_table`, `generate_csv`,
  `generate_map_image`, `filter_features`) and was missing the AI Imagery Feature Extraction and
  Monitoring & Scheduling sections entirely. Both trees now regenerate identically (131 tools).
- `prompts.py` rule 9 updated to name all 5 now-gated tools. 2 new tests
  (`test_destructive_calculate_area_gate`, `test_destructive_calculate_length_gate`). 671 tests
  total (was 669), same pre-known sandbox baseline as always.

## [1.2.28] — 2026-08-21

**Implementing the ENGINEERING_PRODUCT_UX_REVIEW findings, round 2** — the user authorized
proceeding with all four remaining review-finding tasks (REVIEW §2.3, §3.2 x2, §4) that round 1
left pending. This entry covers the first of them.

- **Fixed `gemini.py`'s auth-header inconsistency (REVIEW §2.3)**: `list_models()` and
  `grounded_search()` both sent the API key via a `?key=` query parameter, while
  `GeminiClient.complete()`'s main chat path already used the `x-goog-api-key` header.
  Query-string credentials are more likely to end up in server access logs, proxy logs, or
  browser history than a header. Round 1 deliberately left this unfixed pending live-network
  verification this sandbox can't do directly — this round, before changing behavior, confirmed
  via `WebSearch` against Google's own current API docs (ai.google.dev/api) that `x-goog-api-key`
  is a real, documented, supported header for both the ListModels and `generateContent` REST
  endpoints this file calls, rather than assumed or applied blind. Both functions now use the
  header consistently; neither passes `params={"key": ...}` anymore.
- **Added 2 tests** (`test_gemini_list_models_uses_header_auth_not_query_param`,
  `test_gemini_grounded_search_uses_header_auth_not_query_param`) asserting the header is sent
  and the query param is absent, so a regression back to query-param auth would be caught by the
  suite rather than only by manual inspection.
- Still not independently confirmed against the live API from inside this sandbox (no network
  access) — worth exercising via `docs/RELEASE_SMOKE_TEST.md`'s Gemini provider row before the
  next release.
- 669 tests total (was 667), same pre-known sandbox baseline as always (1 DNS-lookup failure in
  `test_is_safe_url_accepts_public_host` + 6 scratch-file-permission errors in
  `test_reporting_tools.py`, neither a real code defect).

## [1.2.27] — 2026-08-20

**Implementing the ENGINEERING_PRODUCT_UX_REVIEW findings, round 1** — the user asked for the
v1.2.26 review's findings to go onto the task list, be analyzed, and planned/implemented. This
round covers the mechanical, low-risk items; the larger design items (dock_widget.py split, cost/
usage UI, destructive-tool audit) are tracked but deliberately not rushed — see below.

- **Fixed `ollama.py`'s retry gap (REVIEW §2.1)**: `complete()` now goes through `base.py`'s shared
  `post_with_retry` instead of a bare `requests.post`, matching every other provider client. The
  local-server client most likely to hit a transient failure in practice was the one with no retry.
- **Fixed `ollama.py`'s misleading error message (REVIEW §2.2)**: a malformed-response `KeyError`
  no longer gets reported as "Ollama connection failed" — split into a distinct "Unexpected response
  format" path, matching `openrouter.py`'s existing handling.
- **Added `TestOllamaRetryAndErrorHandling`** (3 tests) covering both fixes, and updated 2 existing
  tests (`test_ollama_sends_max_tokens`, `test_ollama_honors_max_tokens_override`) that mocked
  `requests.post` directly and would otherwise have silently stopped testing anything after the
  `post_with_retry` swap.
- **Added `TestProviderReturnContract`** (9 tests, REVIEW §2.5): asserts every provider client's
  `complete()` — all 6, including the unwired `cartogen.py` stub — returns exactly
  `{"message", "model"}` on success or `{"error"}` on failure, nothing else. Catches a future
  provider (or a change to an existing one) silently breaking the shape `agent.py`'s tool-calling
  loop depends on.
- **Added a quick-suggestion chip for `apply_raster_stretch`** (REVIEW §3.2): the raster styling
  tool built in v1.2.25 had no UI-level discovery path. Verified the chosen prompt phrasing actually
  routes to the tool via `ToolRouter.filter_relevant_tools` before adding it, not just assumed.
- **Added `docs/RELEASE_SMOKE_TEST.md`** (REVIEW §4): a ~15-minute, one-tool-call-per-category
  checklist for a human to run in a real QGIS session before each release — turns "live QGIS
  verification" from a recurring, unowned recommendation into something concrete and runnable.
- **Added `CONTRIBUTING.md`** (REVIEW §4): states the "why not what" comment discipline and honest
  shipped/roadmap labeling explicitly, with real examples pulled from this codebase, so it survives
  contributor turnover instead of depending on continuity of whoever's doing it today.
- **Deliberately not done this round**, tracked as separate tasks instead of rushed: the
  `gemini.py` auth-header inconsistency (REVIEW §2.3 — flagged as needing live-network verification
  this sandbox can't do, not something to patch blind); splitting `dock_widget.py` along its tab
  boundary (REVIEW §3.2 — the largest, riskiest single change in the whole findings list, and this
  environment can't visually verify a Qt UI refactor); a destructive-tool preview-gate coverage
  audit (REVIEW §3.2 — an investigation task in its own right, not a quick fix); and a token/cost
  usage indicator in the chat UI (REVIEW §3.2 — a real design task, not a mechanical addition).
- Propagated every change to both trees, verified via `diff` (one real mistake caught and fixed in
  the process: an over-eager `sed` identity-translation turned a literal folder-name reference —
  "the root tree is named `qgis_ai_assistant`" — into the wrong string in the copy tree's own
  `CONTRIBUTING.md`; corrected by hand). 655 tests at the start of this round, 667 after this
  round's 12 new provider tests — same known-bad baseline throughout (1 DNS-lookup failure, 6
  scratch-file-permission errors), reconfirmed via a real test run before writing this number down
  rather than estimated.

## [1.2.26] — 2026-08-20

**Specialist product/software-engineering/UI-UX review — docs only, no code changes applied.**
Requested directly by the user: a grounded read of `agent/providers/` (all 6 clients + `base.py`)
and `ui/` (all 4 files, neither of which had a dedicated deep-review pass before this round) with
concrete recommendations, not generic QGIS-plugin advice.

- Added `docs/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md`. Findings include: a real bug
  (`ollama.py`'s `complete()` bypasses `base.py`'s shared `post_with_retry` helper that every other
  provider client uses, so the one provider most likely to hit a transient local-server failure has
  no retry), a minor bug (Ollama's generic exception handler mislabels a malformed-response
  `KeyError` as "connection failed"), and a flagged-not-applied inconsistency (`gemini.py` uses
  header auth for its main chat path but URL query-param auth for its two legacy endpoints —
  fixable, but not changed here since this sandbox has no live network access to verify the header
  form actually works against Google's real API). None of these were fixed this round — the ask was
  recommendations, not implementation; §5's checklist lists them as next steps.
- UI findings are mostly positive: theme-adaptive styling read from the live QGIS palette, correct
  main-thread/background-thread separation on every network call, deliberate opt-in defaults for
  privacy/cost-sensitive features, and HTML-escaping discipline in the chat renderer are all called
  out as patterns to keep. Two concrete recommendations: `dock_widget.py` (1,365 lines, doing chat +
  tasks + attachments + refinement-panel + settings glue in one class) should split along its tab
  boundary before the next major feature makes that more expensive; and the new `apply_raster_stretch`
  tool (v1.2.25) has no UI-level discovery surface (no quick-suggestion chip) despite closing a
  real, previously-flagged gap.
- Product-level: reiterates that the GPL v2 licensing question from
  `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md` §3 is the largest open product risk, and proposes
  turning "live QGIS verification" from a recurring, never-owned recommendation into a concrete
  `docs/RELEASE_SMOKE_TEST.md` checklist artifact a human can actually run before each release.
- Propagated to both trees (`Cartogen AI/cartogen_ai/docs/` copy is byte-identical — the doc's own
  content never mentions the old "QGIS AI Assistant" name, so no re-branding substitution was
  needed). Added a row to both `README.md` documentation tables.

## [1.2.25] — 2026-08-20

**Scheduled task run: actioned 2 of `docs/STATUS_REVIEW_2026-08-20.md`'s open engineering items plus
one scaffold-only item from `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`.** Explicitly excluded
everything tied to the unresolved GPL v2 licensing decision those documents flag (see bottom).

- **Built `apply_raster_stretch`** (`agent/tools/raster_tools.py`) — closes STATUS_REVIEW §7.2/§8.3's
  flagged gap. Every raster-producing tool (`calculate_ndvi`/`calculate_ndwi`/`calculate_ndre`,
  `calculate_raster_change_detection`, `hillshade`/`slope_analysis`/`aspect_analysis`,
  `interpolate_surface`, `hotspot_analysis`, `weighted_overlay_analysis`, etc.) landed on the canvas
  with QGIS's raw, unstretched single-band default rendering — there was a rich vector styling
  toolkit (`apply_graduated_style`/`apply_categorized_style`/`apply_heatmap_style`/
  `apply_graduated_symbol_style`) but no raster equivalent at all. New tool applies either a
  `QgsSingleBandPseudoColorRenderer` color ramp or a `QgsSingleBandGrayRenderer` grayscale min/max
  contrast stretch, auto-selected by layer name (`mode="auto"`, the default): a diverging ramp
  centered on 0 for layers named like NDVI/NDWI/NDRE, grayscale stretch otherwise. Added a
  `ToolRouter` alias entry, prompts.py rule 39 (mirrors rule 38's "guess a sensible default, then
  state it" automatic-styling-follow-up pattern), and updated `calculate_ndvi`/`ndwi`/`ndre`'s own
  docstrings, which previously stated flatly "this plugin has no dedicated raster styling tool" — no
  longer true. 16 new tests: 8 pure-Python `_auto_raster_style` cases, plus QGIS-degrade/validation
  tests following this file's existing `TestXDegradesOutsideQgis` convention. `docs/TOOLS_REFERENCE.md`
  regenerated. Tool count: 134 → 135.

- **Removed 4 redundant duplicate tool registrations** (STATUS_REVIEW §3/§7.1 — flagged in v1.2.20,
  left unresolved pending a decision, now actioned): `generate_csv` and `export_attribute_table`
  (both literal `return export_to_csv(...)` pass-throughs), `generate_map_image`
  (`return print_map(...)`), and `filter_features` (`return run_query(...)`).
  **This is a breaking change**: any saved workflow preset, external script, or integration that
  calls one of these 4 tool names directly will now fail — no backward-compatible alias was kept, on
  the reasoning that the canonical names (`export_to_csv`/`print_map`/`run_query`) are the ones with
  real logic attached and every internal reference has been moved to them. Grepped the full repo (not
  just `agent/`) for all 4 names before removing: found and updated the one place this codebase itself
  called `filter_features` by name — prompts.py rule 37 and `docs/CVA_MARKET_ACCESS_RECIPE.md`'s
  worked example now both call `run_query` instead (identical behavior; `filter_features` was always
  just a pass-through to it). No saved JSON workflow presets or tests referenced any of the 4 removed
  names. Tool count: 135 → 131. Updated `README.md`, `docs/PRODUCT_TIERS.md`, and
  `docs/STATUS_REVIEW_2026-08-20.md`'s own now-stale "134 tools" restatements — added a dated
  post-review note to the latter rather than rewriting its original findings/recommendations, since
  the review's own text is a historical record of what that pass found, not a living document.

- **Scaffolded `agent/providers/cartogen.py`** (TIER_RESTRUCTURE_PROPOSAL §6 item 2) — a stub
  `BaseAiProvider` client for the not-yet-deployed Cartogen API gateway (`service/gateway/`'s LiteLLM
  proxy config), modeled on `openai.py`'s raw-`requests` + per-model 404-fallback shape, since LiteLLM
  proxy exposes an OpenAI-Chat-Completions-compatible endpoint. Explicitly **not** imported by
  `agent/providers/__init__.py` or referenced anywhere in `ui/settings_dialog.py` — confirmed via
  grep, and stated plainly in the module's own docstring — since the backend it would talk to doesn't
  exist yet either: `service/README.md`'s own punch list still lists "pointing the actual QGIS plugin
  at this gateway as a provider option" as not done, several items after a real customer/key database,
  per-tier Stripe-to-budget mapping, and subscription-lifecycle handling that also don't exist yet.
  `GATEWAY_BASE_URL` is a placeholder domain, not a live endpoint. No tests added — none of the other
  5 provider clients (`openrouter.py`/`gemini.py`/`openai.py`/`claude.py`/`ollama.py`) have dedicated
  tests either, so this doesn't introduce an inconsistent gap.

- **Explicitly out of scope this round**, per the task's own exclusion list — all tied to the
  unresolved GPL v2 licensing decision TIER_RESTRUCTURE_PROPOSAL §3/§6 flags as the actual blocker,
  not something to improvise around: no changes to `LICENSE` or any licensing statement in
  `README.md`/`metadata.txt`; no closed-source packaging/compilation/obfuscation mechanism; no tier or
  license-gating concept added to the plugin itself or to `ui/settings_dialog.py`; no changes to
  `service/website/`'s Stripe/billing code or `service/gateway/`'s per-tier budget mapping;
  `SECURITY.md`'s documented protections untouched.

- Both trees (`qgis_ai_assistant` root and `Cartogen AI/cartogen_ai/`) verified in sync via `diff`
  after every change (only expected "QGIS AI Assistant" → "Cartogen AI" re-branding text differs).
  655 tests total (was 639 at the start of this round) — same 2 pre-known sandbox-specific
  failures (a DNS-lookup test that can't resolve a public host in this sandbox, plus a
  `test_result_includes_connectivity_note` failure newly observed this round because the optional
  `folium` package isn't installed in this particular sandbox — same "missing optional dependency"
  category as the DNS issue, not a code defect) and the same 6 pre-known scratch-file-permission
  errors, all unrelated to this round's changes.

## [1.2.24] — 2026-08-20

**Tier restructure proposal, round 3 — docs only, no code or behavior change.** The user gave a
significantly more specific instruction than the previous round: a 3-way split (Community/Pro/
Enterprise) with a new axis this document had never addressed before — source-code availability,
not just connectivity/tool-count. Community is "open source but the source is locked"; Pro is
"closed code, full features"; Enterprise is "full features, full connectivity."

- **Added a licensing-note section to §3** of `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`
  flagging, factually (not as legal advice), that this repository is distributed under GPL v2
  today (`LICENSE`, `metadata.txt`), that GPL v2 is copyleft and requires source availability plus
  modification/redistribution rights for recipients, and that "locked"/"closed" source as
  described is not achievable by adding a feature flag to the current codebase — it requires a
  real licensing decision (re-license, split into an open-core + closed-modules structure, or keep
  everything GPL v2 and drop the locked/closed framing). Flagged a QGIS-specific wrinkle too:
  QGIS's own GPL v2+ license and the plugin ecosystem's GPL-compatibility norm for anything linking
  `qgis.core`/PyQGIS. Recommended getting real counsel before proceeding — explicitly out of scope
  for this document to resolve.
- **Rebalanced the Community/Pro tool split** around a different design goal this round: not "how
  much can Community keep without feeling crippled" but "balance features to create real upgrade
  pressure." Moved `generate_chart` (Community's only insight-generating tool) and `geocode_batch`
  (bulk geocoding, vs. free single-address `geocode_and_enrich`) to Pro as deliberate upgrade
  triggers. New split: **77 Community / 57 Pro** (was 79/55), re-verified by script against
  `docs/TOOLS_REFERENCE.md`'s live 134-tool registry — not hand-counted.
- **Caught and fixed two of my own labeling errors from the previous draft** while re-verifying:
  "Professional deliverables" and "Advanced Raster"/"Advanced scripting/search" were subcategory
  names this document invented, not real categories in `TOOLS_REFERENCE.md` — those tools actually
  belong to the real `Export & Reporting`, `Raster`, and `System, Search & Scripting` categories.
  Relabeled to match the live registry exactly so the split stays traceable. (Caught via a
  from-scratch script re-derivation of the category→tool mapping, prompted by a manual arithmetic
  reconstruction that didn't sum correctly — the reconstruction error was mine, not the document's,
  but it's what triggered re-verifying against ground truth instead of trusting the prior claim.)
- Added new engineering-gap items to §6 covering the actual closed-source distribution mechanism
  (compiled/obfuscated artifacts or gated download, not just a runtime tier flag — materially
  different from what `build_cartogen_ai.py` does today) and sequencing (the licensing decision
  blocks the tier-filter and packaging work).
- Updated §7's migration section to note the source-openness reduction is a second axis of change
  for existing users, on top of the feature/connectivity changes already flagged.
- Updated the `docs/PRODUCT_TIERS.md` cross-reference note (both trees) to summarize the new
  licensing tension and the 77/57 split.
- **Nothing in `agent/`, `ui/`, or `tests/` changed this round** — same reasoning as the last two
  rounds: this is a planning document, not an implementation.

## [1.2.23] — 2026-08-20

**Tier restructure proposal revised — docs only, no code or behavior change.** The user directly
resolved the one open question flagged in v1.2.22's `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`
(§0): where does today's direct BYOK to OpenRouter/Gemini/Claude/OpenAI live under the new
Community/Pro connectivity cap?

- **Confirmed: a third tier, named Enterprise**, with all features (full 134-tool registry, same
  as Pro) plus all connectivity options — Local LLM, Cartogen API gateway, and direct BYOK.
- Updated the proposal doc in both trees: retired the placeholder "Full / Direct-Connect" name from
  the first draft, renamed §3's tier-structure table's third column to Enterprise, and added a new
  explanatory paragraph reconciling this connectivity-based Enterprise definition with
  `PRODUCT_TIERS.md`'s existing (2026-08-15) Enterprise section, which is built around RBAC/SSO/
  private-enclaves/M365 push — a separate, additive, still entirely unbuilt axis, not a conflict.
  Updated §6's engineering-gap items 4-5 to reference Enterprise instead of the retired name.
- Updated the `docs/PRODUCT_TIERS.md` cross-reference note (both trees) to match.
- **Nothing in `agent/`, `ui/`, or `tests/` changed this round** — same reasoning as v1.2.22: this
  is a planning document, and the Cartogen API gateway it depends on still doesn't exist.

## [1.2.22] — 2026-08-20

**Tier restructure proposal — docs only, no code or behavior change.** Requested directly by the
user: design a proposal replacing the (also-unbuilt) Professional/Enterprise framing in
`docs/PRODUCT_TIERS.md` with a Community/Pro split gated on tool count *and* connectivity (both
capped to Local LLM + the not-yet-finished Cartogen API gateway, no direct BYOK), plus a third tier
to hold the existing direct-BYOK capability.

- Added `docs/TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md`: proposes **Community** (79 of 134 tools,
  script-verified against the live registry, Local LLM + Cartogen API gateway only),
  **Pro** (full 134-tool registry, same connectivity cap), and a proposed third **Full /
  Direct-Connect** tier retaining today's direct BYOK to OpenRouter/Gemini/Claude/OpenAI. Grounded
  in `service/`'s already-partially-built LiteLLM/Stripe gateway prototype (read in full this
  round — not previously examined in this conversation) rather than treating the gateway as pure
  abstraction; lists the concrete engineering gap (no `agent/providers/cartogen.py`, no tier
  concept anywhere in the plugin, no connectivity gating in `ui/settings_dialog.py`) and flags one
  explicit assumption for the user to confirm or correct (where direct multi-provider BYOK lives
  under the new structure).
- Cross-referenced the new proposal from `docs/PRODUCT_TIERS.md` (dated note, since that file's own
  job is to track shipped reality, not proposals) and from both `README.md` documentation tables.
- **Nothing in `agent/`, `ui/`, or `tests/` changed this round** — this is a planning/business
  document, consistent with the fact that the Cartogen API gateway it depends on doesn't exist yet
  and no gating code could be meaningfully tested against it today.

## [1.2.21] — 2026-08-20

**Full-codebase status review**, requested by the user directly (not a continuation of the v1.2.20
gap audit — a fresh top-to-bottom pass across architecture, tool registry, security, and docs).
Found and fixed 3 small real gaps while establishing the baseline, then wrote
`docs/STATUS_REVIEW_2026-08-20.md` as the consolidated deliverable.

- `docs/TOOLS_REFERENCE.md`'s auto-generated category grouping fell back to raw Python module
  names ("imagery_extraction", "monitoring_tools") for 2 of its 16 categories instead of a
  readable label, because `docs/generate_tools_reference.py`'s `_group_key` label map simply never
  had entries for those two modules. Fixed: `"imagery_extraction": "AI Imagery Feature Extraction"`,
  `"monitoring_tools": "Monitoring & Scheduling"`. Regenerated in both trees.
- `docs/PRODUCT_TIERS.md` still said "all 125 tools" -- stale since the registry grew to 134
  (README.md already had the correct count; this doc was missed in that pass). Fixed.
- `SECURITY.md`'s "Known limitations" section never mentioned that
  `extract_features_from_imagery`'s FastSAM weights download (`FastSAM("FastSAM-s.pt")`) is
  entirely delegated to the `ultralytics` package's own first-use download logic, with no hash
  pinning or verification by this plugin's own code. Added as a new bullet matching the section's
  existing honest-disclosure pattern, scoped the same way as the § 3 SSRF guard (only URLs this
  plugin's own code fetches directly are in scope; a dependency's own download mechanism isn't).

## [1.2.20] — 2026-08-20

**Self-audit: "find the gaps that weren't triggered" in v1.2.19's own work.** The user explicitly
asked for a follow-up review of the previous round's rendering/router/prompt fixes to find what
was missed. This surfaced real bugs in that round's own work, not just new unrelated findings --
worth being direct about rather than folding into a generic "more improvements" entry.

- **Rule 38 (v1.2.19) was itself wrong for one of its three named tools.** `calculate_presence_gap`
  writes a CATEGORICAL string field (`'gap'/'covered'/'unmatched'`), not a continuous score, but
  rule 38 told the model to follow up with `apply_graduated_style` for all three tools uniformly --
  `apply_graduated_style` requires a numeric field and would produce nothing meaningful on this
  one. Also completely missing from rule 38: `calculate_population_in_need`, which writes a
  continuous population figure via `output_field` and whose own tool description already says
  "then style it directly with apply_graduated_style" -- rule 38 just never named it. Rule 38
  rewritten to split graduated (severity/damage/population, all continuous) from categorized
  (presence-gap status, categorical) styling guidance.
- **4 more tools had the same near-zero router recall problem as v1.2.19's own
  analyze_incident_trend/score_route_incident_risk fix, just not checked at the time:**
  `calculate_ndvi`, `calculate_ndwi`, `calculate_ndre`, `calculate_raster_change_detection`. Root
  cause: these four had the thinnest descriptions in the entire 134-tool registry (as short as 7
  words, e.g. "Calculate NDVI from Red and NIR raster layers") -- zero vocabulary overlap with how
  a real user actually asks ("how green is this area", "is there flooding here", "crop nitrogen
  stress", "compare before and after images for damage"). All 4 confirmed missing from the top-40
  candidate set on repeated trials before the fix, confirmed present after. Fixed both ways:
  expanded each description with real vocabulary and interpretation guidance (matching this
  codebase's established descriptive style, which these four had drifted from), plus added
  `ToolRouter` alias entries as a second layer of defense. Also documented, in the same pass, that
  this plugin has no dedicated raster styling tool at all -- every raster output (NDVI/NDWI/NDRE,
  change detection, interpolation, hillshade, etc.) lands with QGIS's raw unstretched default
  rendering, unlike the rich vector styling toolkit in `styling_tools.py`. Not fixed this round
  (a new tool, not a description/alias fix) -- flagged for a decision.
- **Introduced and caught a real regression in the process of fixing the above.** Added a second
  `"load_3w_data": [...]` entry to `_TOOL_ALIASES` instead of merging into the existing one --
  Python dict literals silently keep only the last duplicate key, discarding the original 5-phrase
  alias list for the narrower 4-phrase replacement with no error or warning. Not caught by reading
  the diff; caught by re-running the full test suite and seeing `test_who_else_is_working_finds_3w_data`
  fail. Fixed by merging into one entry, and added
  `TestToolAliasesNoDuplicateKeys.test_no_duplicate_keys_in_tool_aliases_dict` (parses
  `tool_router.py` via `ast` and asserts no repeated dict key) so this exact silent-failure mode
  can't ship again undetected -- a runtime dict can't tell you it had a duplicate key, so this had
  to be a static check, not a behavioral one.
- **`calculate_ndvi`/`calculate_ndwi`/`calculate_ndre`/`calculate_raster_change_detection` had zero
  test coverage** -- not even the baseline "returns a QGIS-not-available error outside QGIS" check
  every other tool in this suite has. Added the missing degrade tests (4 new), on top of 6 new
  router-recall regression tests and the duplicate-key guard test -- 639 tests total (was 628 at
  the start of v1.2.19), same pre-known sandbox artifacts (1 failure + 6 errors) as every prior run
  in this environment.
- **Flagged, not fixed pending a decision:** `generate_csv` and `export_attribute_table` are
  literal one-line pass-through wrappers around `export_to_csv` (`return export_to_csv(...)`, no
  other logic), and `generate_map_image`/`filter_features` duplicate `print_map`/`run_query` the
  same way -- 4 of the 134 registered tools are fully redundant aliases with no functional
  difference, adding router-candidate and prompt-token noise for zero capability. Left in place
  rather than removed unilaterally, since deleting a registered tool name is a bigger, more
  consequential change than a description/alias fix (could affect saved workflow presets or
  scripts referencing the name) -- worth a decision, not a silent removal.

## [1.2.19] — 2026-08-20

**Rendering + prompt/router audit of the v1.2.17 tools** (2026-08-20): the user asked me to check
layer rendering and prompt coverage for all currently-shipped tools, specifically the newest ones.
Found and fixed three real, verified gaps -- not a routine pass, each was confirmed against actual
code before being changed.

- **`score_route_incident_risk`'s buffer layer had no deliberate styling.** It's built via
  `buffer_analysis`, which calls `QgsProject.instance().addMapLayer()` with no renderer set --
  every caller gets QGIS's default random single-symbol color, fine for a generic buffer but wrong
  for a risk-corridor visualization a user would actually read as risk. Fixed with a new
  `_style_risk_buffer_layer()` helper in `agent/tools/logistics_tools.py` (translucent orange,
  no border, ~35% opacity so the route line and basemap stay visible underneath) -- same
  hardcoded-in-plugin-code philosophy as `humanitarian_tools._style_incident_layer`, for the same
  reason: a guaranteed consistent look regardless of what the model would otherwise generate.
  Confirmed via grep that no other caller of `buffer_analysis` shares this code path, so the fix is
  scoped to this one tool, not a behavior change for every buffer call in the plugin.
- **`ToolRouter._TOOL_ALIASES` had no entries for either tool added in v1.2.17.** Checked the exact
  scoring math in `agent/tool_router.py`: `analyze_incident_trend`'s name/description share no
  vocabulary with realistic paraphrases like "is this area getting more dangerous" (the same
  phrasing prompts.py's own rule 35 uses to describe this tool's intent) -- only a weak single-word
  hit ("getting"), the same failure category that motivated the four existing alias entries per
  `docs/API_COST_OPTIMIZATION_REVIEW.md` section 1.1. Added alias phrases for both tools. Verified
  with 2 new regression tests in `tests/test_tool_router.py` (added to both the dedicated alias-
  coverage test class and the table-driven recall-regression test) -- all pass.
- **No prompt rule told the model to visualize a severity score after computing it.**
  `calculate_severity_index`/`calculate_presence_gap`/`calculate_damage_exposure_severity` write a
  score to `output_field` on request, but none of them touch the layer's renderer -- confirmed via
  reading all three `_write_*_to_layer` helpers in `agent/tools/analysis_tools.py`. Without a
  prompt rule connecting this to `apply_graduated_style`, a computed severity score could sit
  correctly in the attribute table while the agent presents the result as a finished map. Added
  rule 38 to `agent/prompts.py`.
- `docs/TOOLS_REFERENCE.md` regenerated via `docs/generate_tools_reference.py` -- 134 tools,
  unchanged count, only `score_route_incident_risk`'s description text updated to mention the new
  auto-styling. All five changed files (`agent/prompts.py`, `agent/tool_router.py`,
  `agent/tools/logistics_tools.py`, `docs/TOOLS_REFERENCE.md`, `tests/test_tool_router.py`)
  propagated to `Cartogen AI/cartogen_ai/` and verified (grep for the new content landing, and for
  no stale `qgis_ai_agent`/`QgisAiAgent` identifiers introduced). Full `build_cartogen_ai.py` run
  was skipped this round because unrelated leftover scratch test files in the sandbox root
  (`scratch_test_*.csv/.docx/.pdf`, pre-existing, not removable in this environment due to a
  permissions error) would have been swept into the target tree by its whole-repo walk -- propagated
  these five files by hand instead, the same fallback this project has used before when the
  automated build wasn't safe to run as-is. 629 tests (628 + 1 new test method; the second new
  assertion extends an existing table-driven test rather than adding a new one), 1 failure + 6
  errors (same pre-known sandbox artifacts as every prior run in this environment -- confirmed
  unchanged, not new).

## [1.2.18] — 2026-08-20

**Three program-area gap responses (2026-08-20)**: closes out the "Program / Security / Logistics"
gap-analysis review with a JIAF multi-sector composite spec, and two zero-code recipes -- researched
via WebSearch/WebFetch against real sources before writing anything down, not assumed from the
original review's own framing.

- **`docs/JIAF_MULTISECTOR_COMPOSITE_SPEC.md`** (spec, no code): grounded in JIAF 2.0's actual,
  named **Mosaic Method** (maximum sectoral PiN per geographic unit, not sum -- fetched and quoted
  from a Global Health Cluster technical brief) and the 2026 HPC cycle's PiN-scope update (only
  areas at intersectoral severity Phase 3+ count toward the total). The load-bearing finding: real
  JIAF cross-sectoral severity is finalized through human "Convergence of Evidence"/validation
  workshops, not a pure formula -- so the proposed `calculate_intersectoral_severity` tool is
  explicitly scoped to output a **preliminary, Mosaic-Method-based estimate**, never presented as an
  official JIAF figure. Where the real methodology's "compounding" rule for simultaneously-severe
  sectors wasn't found in any reachable source, the spec says so and scopes it out, rather than
  inventing a plausible-sounding formula -- the same anti-fabrication discipline `agent/prompts.py`
  rule 12 already applies to LLM text and (rule 34) tool output, now applied to methodology research
  itself.
- **`docs/AUTO_REPORTING_RECIPE.md`** (zero new code): corrects the original "free recipe" claim --
  `generate_html_dashboard`/`generate_sector_coverage_report` aren't in
  `_ALLOWED_WORKFLOW_TOOLS`, so scheduling them directly fails. The recipe that's actually free:
  schedule the read-only analysis, generate reports on demand when a tick shows something worth
  reporting.
- **`docs/CVA_MARKET_ACCESS_RECIPE.md`** (zero new code): `population_access_gap` already computes
  the GIS-computable piece of CVA feasibility (population beyond reasonable market/FSP distance);
  `filter_features` optionally restricts to already-assessed functioning markets in place, no
  extract-to-new-layer step needed. Explicitly states CALP's other three feasibility pre-conditions
  (market functionality, FSP capacity, security, community acceptance) aren't GIS-computable and
  shouldn't be implied by a distance-gap result -- and that no universal market-access distance
  threshold exists (sourced research found context-specific values from ~2km to ~17km).
- **`agent/prompts.py` rules 36-37**: intent recognition for both recipes, including steering away
  from the now-corrected auto-reporting approach and an explicit ban on inventing a market-access
  distance threshold.
- **`README.md`**: all three added to the documentation table.

## [1.2.17] — 2026-08-20

**Implemented `analyze_incident_trend` + `score_route_incident_risk` (2026-08-20)**: builds
`docs/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md`'s §3.1 and §3.2 end to end. §3.3 (no-go zones) ships as
prompt guidance (rule 35) pointing at the existing `difference_layers` + routing-tool composition,
exactly as scoped -- not a new tool.

- **`analyze_incident_trend`** (`agent/tools/analysis_tools.py`): buckets a point layer's incidents
  into `period_days`-sized time periods per zone, then feeds each zone's (period, count) series into
  the same `_forecast_series`/`_linear_regression` math `forecast_trend` already uses -- no new
  statistic invented. The date-bucketing math is factored into a new `_bucket_dates_by_period` helper
  specifically so it's unit-testable without QGIS, mirroring the existing `_forecast_series`/
  `forecast_trend` split. Requires at least 3 time periods to fit a trend; returns a clear error
  naming how much data is actually available otherwise.
- **`score_route_incident_risk`** (`agent/tools/logistics_tools.py`): reuses `buffer_analysis`'s
  exact processing call to buffer a route, then counts/lists incidents within it with optional
  date-window and severity-weight filtering, each with its own distance-to-route.
- **`agent/prompts.py` rule 35**: recognizes field/operational-security and route-safety intent
  without the tool being named (extends rule 25's pattern) -- including steering "avoid this area"
  requests toward the `difference_layers` + routing composition instead of either
  `score_route_incident_risk` (which only scores, never excludes) or a hand-rolled
  `execute_pyqgis_script` network edit.
- **Tests**: `_bucket_dates_by_period` covered directly (single-period, multi-period, unsorted input,
  single-date, and period-boundary edge cases), plus graceful degradation outside QGIS for both new
  tools. 628 tests total.
- **Not verified**: real behavior against a live QGIS session with real incident/route/zone data --
  neither tool has been run against a real project. `docs/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md`'s own
  §6 "cannot verify without live QGIS" list, including whether `native:difference`'s output stays
  cleanly routable after removing restricted-zone segments, is unchanged by shipping this code.
- **`README.md`**: tool count updated (132 -> 134) and `TOOLS_REFERENCE.md` regenerated.

## [1.2.16] — 2026-08-20

**Wrote the route risk-scoring & no-go zones spec (2026-08-20)**: `docs/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md`
-- the Security x Logistics intersection item from a gap-analysis review, chosen over the other
options because it composes already-shipped tools rather than starting a new area cold. Same
spec-before-build discipline as the Prompt Refinement Layer and SAM imagery extraction specs.

Closes three verified gaps: `hotspot_analysis` (`styling_tools.py`) has no time/date parameter at
all, confirmed by reading its full schema -- it's a single density snapshot, not a trend; nothing
composes `buffer_analysis` with an incident layer to score a planned route's proximity to recent
incidents; and no-go/security-restricted zones aren't modeled anywhere, despite
`ROUTE_OPTIMIZATION_STRATEGY.md` already recommending the identical hard-exclude treatment for
physically damaged roads.

- **`analyze_incident_trend`** (proposed): reuses `analysis_tools.py`'s existing `_forecast_series`/
  `_linear_regression` (the same functions `forecast_trend` already uses and this codebase already
  tests) over per-zone incident-count series, instead of inventing new trend statistics.
- **`score_route_incident_risk`** (proposed): reuses `buffer_analysis`'s exact processing call to
  buffer a route, then counts/lists nearby incidents with optional date and severity-weight
  filtering.
- **No-go zones**: not a fourth tool -- a documented usage pattern (`difference_layers` to remove
  restricted-zone-intersecting road segments, then route on the result unchanged), after concluding
  a new parameter on the existing routing tools would just re-derive logic `difference_layers`
  already does correctly.
- **Honestly flagged as unverified**: whether `native:difference`'s output stays cleanly routable
  for `native:shortestpathpointtolayer`'s graph builder after segment removal -- the one real
  assumption in this spec, not just an untested pass-through, called out explicitly in §6 rather
  than glossed over.
- **No code changes** -- spec only. `README.md`'s documentation table updated.

## [1.2.15] — 2026-08-20

**Wrote a route optimization strategy + OSMnx/NetworkX prototype (2026-08-20)**: implements a
requested humanitarian-logistics review of `agent/tools/logistics_tools.py`'s routing accuracy.
Every "current behavior" claim in `docs/ROUTE_OPTIMIZATION_STRATEGY.md` is checked against the real
code (file:line verified before shipping) -- the concrete, fixable root cause behind reported
routing-accuracy problems: `calculate_service_area` and `travel_time_matrix`
(`logistics_tools.py` lines 399-407, 480-488) already call QGIS's own real Dijkstra-based network
algorithms (`native:serviceareafrompoint`, `native:shortestpathpointtolayer`), but only ever pass a
flat 50 km/h `DEFAULT_SPEED` -- neither call sets `SPEED_FIELD` or `DIRECTION_FIELD`, both of which
that same algorithm already supports. No new algorithm needed, just wiring up existing parameters.
Also documents a real gap: `optimal_hub_siting`/`location_allocation`/`optimize_delivery_route`
explicitly use straight-line distance, and no tool today combines multi-stop ordering with real
road-network distance.

- **Strategy doc** covers data enhancements (per-segment speed/surface/damage fields, a local DEM
  for grade penalty, explicitly recommending against live traffic/weather APIs given post-disaster
  connectivity reality), algorithmic adjustments (the `SPEED_FIELD` wiring as the highest-value
  lowest-risk change, a composite-impedance preprocessing approach, OR-Tools flagged honestly as a
  materially bigger separate effort for true vehicle-routing-problem constraints, and why Dijkstra
  stays the right algorithm family over A*), a GPS-trace-based validation strategy (map-matched
  per-segment speed calibration plus a held-out accuracy test with a real before/after error number),
  and why the prototype script below intentionally uses a different stack than the plugin's shipped
  tools.
- **`docs/route_optimization_prototype.py`**: the requested standalone OSMnx/NetworkX/GeoPandas
  script, computing a route that penalizes both unpaved surface (OSM tags) and steep grade (a local
  DEM raster, not a cloud elevation API -- stays offline-first). Explicitly flagged, not glossed
  over: never executed in this session (no network/QGIS access), and a known OSMnx
  version-sensitivity risk in the `graph_from_bbox` call is called out inline rather than left as a
  silent trap.
- **No changes to `agent/tools/logistics_tools.py`** -- strategy and prototype only, same
  spec-before-build discipline as the Prompt Refinement Layer and SAM imagery extraction specs.
- **`README.md`**: added to the documentation table; also fixed a stale "125 tools" count in two
  places (real count is 132, per the last `TOOLS_REFERENCE.md` regeneration) -- found while
  verifying this entry, unrelated to it, fixed while already in the file.

## [1.2.14] — 2026-08-17

**Clearer guidance for a live-confirmed install failure (2026-08-17)**: a real install of the
`extract_features_from_imagery` dependency group failed with `PermissionError: [WinError 5] Access is
denied` on a locked `markupsafe` `.pyd` file -- pip's `--target` install (the mechanism `qpip` uses)
couldn't replace a module QGIS already had loaded, because `folium` (an existing base dependency)
shares the `jinja2`/`markupsafe` chain with `ultralytics`. This is a Windows OS-level file-lock
constraint on a module the running QGIS process already has open -- no code executing inside that same
locked process can delete or overwrite it, so this is not something any code change in this plugin can
make impossible. What's fixable, and now fixed: the raw traceback gave no indication of what went
wrong or how to recover. Added an explicit "close QGIS completely before installing" warning naming
the exact error and the exact fix in three places: the tool's own `ImportError` message
(`agent/tools/imagery_extraction.py`), the dependency group's comment in `requirements.txt`, and
`README.md`'s Optional dependencies section. Also recorded as a "Confirmed live" finding in
`docs/SAM_IMAGERY_EXTRACTION_SPEC.md`, matching `SECURITY.md`'s own convention for live-confirmed
issues rather than hypothetical ones. Not done: a proper install-time confirmation dialog (§10 item 3
of the spec already flagged this as worth building, still open, not claimed as resolved by this
message-only fix).

## [1.2.13] — 2026-08-17

**Declined: MCP server exposure (2026-08-17)**: `docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md`
Tier 1 item 4 (exposing the tool registry as an MCP server -- the review's single most consequential
competitive finding) is explicitly **declined**, not deferred. The product owner does not want this
surface added. No code was ever written toward it -- confirmed no `mcp_server.py`, no MCP references
anywhere in `agent/` or `ui/` beyond the review's own recommendation text and this changelog entry --
so there's nothing to remove. Left in the review doc struck through with a "Declined" marker rather
than deleted, so there's a record it was considered and explicitly rejected, matching this project's
existing convention for other declined/deferred items (e.g. the SSRF DNS-rebinding limitation in
`SECURITY.md`, accepted rather than fixed, stated rather than silently dropped). Do not re-propose
without a new explicit request.

The repo-rename item (§A.3) is untouched by this change -- still open, still needs the private-repo
visibility question resolved before any public submission.

## [1.2.12] — 2026-08-17

**Implemented `extract_features_from_imagery` (2026-08-17)**: builds `docs/SAM_IMAGERY_EXTRACTION_SPEC.md`
end to end, using the spec's own recommended defaults for all 4 open decisions -- FastSAM only (no
full-SAM/MobileSAM choice for v1), hard-reject rasters over `max_pixel_dimension` (default 2048px,
never silently downsampled), no separate install-confirmation UI beyond the existing qpip flow, and
the `ultralytics` library's own default checkpoint cache location.

- **`agent/tools/imagery_extraction.py`** (new): isolated in its own module on purpose -- the first
  tool needing a real ML runtime (`torch`, via `ultralytics`) rather than an API-key-only provider
  integration. `ultralytics` is imported lazily inside the tool function, the same guard pattern
  `generate_chart` already uses for `matplotlib`, so a missing dependency here can't break plugin
  startup or any other tool. Pipeline: load the raster via GDAL, export to an 8-bit PNG (`gdal.Translate`
  handles band-count/bit-depth conversion), run FastSAM in "segment everything" mode (CPU by
  default, CUDA automatically if available), convert each surviving mask to a georeferenced polygon
  via `gdal.Polygonize` against a per-mask in-memory raster carrying its own scaled geotransform (a
  FastSAM mask's resolution isn't guaranteed identical to the source raster's), and add the result
  as a new vector layer with a `confidence` field. Class-agnostic throughout -- never labels a
  result "building" or any other object class, only a boundary and a confidence score (see rule 34).
- **Caught before shipping**: `_mask_pixel_count`'s plain-Python fallback path (for testability
  without requiring numpy) caught `AttributeError` only, but a plain nested list raises `TypeError`
  on the numpy-style comparison first -- fixed to catch both, verified with a direct test before
  moving on.
- **`agent/prompts.py` rule 34**: extends rule 12's anti-fabrication principle to this codebase's
  own tool output, not just LLM-generated text -- never describe extracted polygons as a specific
  object class unless the user's own request already established that framing.
- **`requirements.txt`**: `ultralytics` added as a clearly-separated single-feature dependency, not
  mixed into the existing lightweight document/chart optional-dependency list -- deliberately kept
  out of `agent/deps.py`'s `REQUIRED_PACKAGES` (and its always-shown startup warning banner) since
  most users never touch imagery extraction; the tool's own inline error message is the only place
  this dependency is surfaced, at the moment it's actually needed.
- **Tests**: `tests/test_imagery_extraction.py` covers every piece the spec's §9 already flagged as
  verifiable without a live pass -- the pixel-to-map coordinate transform, mask pixel counting
  (both numpy and plain-Python paths), and graceful degradation outside QGIS. 618 tests total.
- **Explicitly NOT verified by this commit**: real segmentation quality, real CPU inference timing,
  real memory behavior under `torch` + a loaded model, and whether `gdal.Polygonize`'s actual output
  matches what the implementation expects without adjustment. This needs a live QGIS session with a
  real downloaded FastSAM checkpoint -- writing the code does not substitute for that pass, and this
  entry does not claim otherwise.

## [1.2.11] — 2026-08-17

**Wrote the SAM-family imagery extraction spec (2026-08-17)**: `docs/SAM_IMAGERY_EXTRACTION_SPEC.md`
implements Tier 2 item 7 from `docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md` -- a design spec, not
code, following the same spec-before-build discipline used for the Prompt Refinement Layer. Covers
model choice (FastSAM recommended over full SAM -- offline/CPU-first positioning rules out a
2.4GB-checkpoint model), the proposed `extract_features_from_imagery` tool pipeline, why this breaks
this codebase's "pure Python, no numpy" convention deliberately (real tensor inference needs
`torch`), failure modes, and 4 open decisions that need a call before implementation starts. Flags
explicitly that this feature's unverifiable-without-a-live-pass surface (real model inference
quality, real timing, real memory behavior) is larger than any other feature shipped this session --
stated plainly in the spec's §9 rather than glossed over.

No code changes. `agent/tools/analysis_tools.py`'s "pure-Python, no numpy" docstring convention is
unaffected -- this spec explicitly scopes the numpy/torch dependency to a new module, not a
retroactive change to existing tools.

## [1.2.10] — 2026-08-17

**Added Transparency Cards (2026-08-17)**: implements Tier 2 item 5 from
`docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md` -- `docs/TRANSPARENCY_CARDS.md`, three
procurement/compliance-facing one-pagers (running model-generated Python, running model-generated
SQL, deleting/mutating existing data) mirroring the "what it does / what it can't do / what's
confirmed by testing" structure the review described from Esri's ArcGIS Trust Centre. Every claim
is grounded in an existing `SECURITY.md` file:line reference -- no new claims introduced, matching
this session's standing anti-fabrication discipline applied to documentation, not just prompts.
Pure documentation, no code changes.

## [1.2.9] — 2026-08-17

**Added `calculate_damage_exposure_severity` (2026-08-17)**: implements Tier 2 item 6 from
`docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md` -- a RAPIDA-inspired damage-and-exposure composite,
in the same thin-composite pattern as `calculate_population_in_need`. Combines
`calculate_raster_change_detection`'s before/after pixel diff with `fetch_building_footprints`'
building counts (and, optionally, a user-supplied hazard-intensity raster) via `_compute_severity_index`
into a per-unit severity score plus a total building count in the high-severity units.

- Change magnitude is the zonal **mean** absolute pixel difference per admin unit, not the raw sum --
  summing would just scale with unit area/pixel count rather than reflecting actual damage intensity.
- Building exposure counts footprint **centroids** falling within each unit, not full-polygon
  containment -- caught in review before shipping: an earlier draft tested whether the entire
  building footprint polygon was contained in the admin polygon, which would silently undercount (or
  double-exclude) buildings straddling an admin boundary. Fixed via `QgsGeometry.centroid()` before
  the point-in-polygon test, mirroring `obfuscate_sensitive_points`' existing spatial-index pattern.
- Units the change-detection raster doesn't cover are excluded from the severity index (never
  imputed as zero), matching `calculate_severity_index`'s own rule; units with genuinely zero
  buildings still get a real 0, since that's an actual count, not missing data.
- Deliberately scoped down from what RAPIDA actually does -- no seismic/hazard modeling, no
  social-media/night-light signal ingestion (flagged as Tier 3/aspirational in the same review). This
  narrows that gap, it doesn't close it.
- Tests: 3 new graceful-degradation cases in `tests/test_analysis_tools.py`.

## [1.2.8] — 2026-08-17

**Corrected the repo URL to the actual repo (2026-08-17)**: the previous commit pointed
`metadata.txt` at `cartogenai-glitch/cartogen_ai`, based on the name confirmed at the time --
corrected to the actual repo, `cartogenai-glitch/QGIS-CARTOGEN-AI`, confirmed to already exist
(private). **Flagging, not resolving:** a private repo is the exact same blocker
`IMPLEMENTATION_TASK_LIST.md` and `QGIS_AI_Agent_Feature_List.md` already documented for the old
repo -- the QGIS Plugin Repository submission checklist requires metadata links to be publicly
accessible. This commit only fixes which repo the metadata points at, not that visibility
requirement; the repo will need to be made public (or metadata pointed at a public mirror) before
any QGIS Plugin Repository submission. This session's `gh` still isn't authenticated as
`cartogenai-glitch`, so the actual git remote this codebase pushes to remains unchanged.

## [1.2.7] — 2026-08-17

**Repointed `metadata.txt` to the canonical Cartogen AI repo (2026-08-17)**: resolves
`docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md` §A.3 -- `repository`/`tracker`/`homepage` (both
trees) pointed at `github.com/baron-dev07/qgis_ai_assistant`, the project's pre-rebrand name and,
separately, an already-live unrelated listing's slug on the QGIS Plugin Repository. Now point at
`github.com/cartogenai-glitch/cartogen_ai`. That repo doesn't exist yet and this session's `gh` CLI
isn't authenticated as that account, so the actual git remote this codebase pushes to is
unchanged for now -- only the metadata fields moved. Two historical docs (`IMPLEMENTATION_TASK_LIST.md`,
`QGIS_AI_Agent_Feature_List.md`) still cite the old URL and were deliberately left alone -- they're
dated point-in-time status records, not live references, and rewriting them would misrepresent what
was actually true when they were written.

## [1.2.6] — 2026-08-17

**Hardened the recurring monitoring scheduler + SECURITY.md update (2026-08-17)**: acted on
`docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md`, a security and competitive review whose Part A
(security) claims were verified against real code line-by-line before acting on them -- every
file:line citation checked out exactly (`scheduler.py:48`, `monitoring_tools.py:65`,
`analysis_tools.py:450`, and the `metadata.txt` naming-collision claim).

- **`agent/scheduler.py`**: `WorkflowScheduler.start()` previously only rejected
  `interval_minutes <= 0` -- `0.001` became a ~60ms `QTimer` re-running full geoprocessing on the
  main Qt thread on every fire, a self-inflicted denial-of-service from a single miscalibrated or
  prompt-injected call. Now enforces a 1-minute floor. Also adds a 5-schedule concurrent cap (a new
  `preset_name` past the limit is rejected; replacing an already-active schedule under the same name
  is exempt) -- previously nothing bounded how many independent `QTimer`s could accumulate.
  Validation runs before the QGIS-availability check specifically so both guards are unit-testable
  without a real QGIS environment.
- **`agent/tools/monitoring_tools.py`**: `schedule_recurring_workflow`'s description and
  `interval_minutes` schema now state both limits up front.
- **`SECURITY.md`**: new `### 8. Recurring monitoring scheduler` and
  `### 9. Prompt Refinement Layer` sections -- neither feature (both shipped since the last
  substantive `SECURITY.md` update) was documented at all, which the review flagged as the most
  important finding: a completeness gap in the one document whose job is completeness. Also folds
  `calculate_presence_gap`'s `presence_file_path` into the existing "Local file access is
  intentionally broad" accepted-risk bullet (it was missing from that list independent of the
  scheduler) and notes the scheduler's unattended, recurring re-read of that same path as an
  escalation of that accepted risk, not a new vulnerability class.
- **Tests**: 4 new cases in `tests/test_monitoring_tools.py` covering the interval floor, the
  concurrency cap, and the same-name-replacement exemption.
- **Not done, flagged for a decision**: the review's other two findings --renaming the public repo
  away from the `qgis_ai_assistant` slug (already claimed by a live, unrelated listing on the QGIS
  Plugin Repository) before any public submission, and scoping an MCP server to expose the tool
  registry to external MCP clients (the review's single biggest competitive-gap finding: a
  `QGIS MCP` plugin already does this today, and Esri is adding MCP support to ArcGIS) -- both are
  real, external, and not something to act on unilaterally.

## [1.2.5] — 2026-08-16

**Consolidated redundant anti-fabrication rules + prompt-rule eval starter (2026-08-16)**: acted
on live review feedback grounded in the actual current state of `agent/prompts.py` (18,281
characters at review time, close to the review's own ~16.6K estimate) and `agent/prompt_refiner.py`
-- verified against the code before acting, not taken at face value. Two corrections surfaced
during that verification: the review's persona claim was more pessimistic than reality warranted
(personas are one shared template with a swapped label, not four separately hand-written system
messages, which is actually a thinner gap worth knowing about before any QA pass), and the exact
character-count citation was already stale.

- **Rules 12/20/23/32 consolidated**: all four independently re-derived the same principle --
  don't present invented/uncertain/time-sensitive content as settled fact -- for real-world facts,
  forecasts, live funding data, and illustrative JSON respectively, each added reactively after a
  real bug. Rule 12 is now the general principle; rules 20/23/32 are one-line pointers back to it
  with only their tool-specific guidance kept (rule 23 keeps its unrelated `PLAN_SUGGESTION`/
  `generate_chart` guidance intact, since that isn't part of the redundancy). Saved ~590 characters
  (~25%) off the four rules combined.
- **New rule 33 (ask vs. guess decision hierarchy)**: resolves the tension between rule 19 (guess
  style/format defaults, state the choice) and rules 26/31 (ask first on data-sensitivity judgment
  calls and irreversible/standing actions) for requests that touch more than one -- e.g. style a
  layer of protection-sensitive points: ask about the obfuscation method, guess-and-state the
  styling. This is new content addressing a real gap, not reclaimed redundancy, so it brings net
  prompt size back to roughly even with before the consolidation -- the win is that each rule now
  does one clear job, not a straight character-count reduction once rule 33 is included.
- **`agent/prompt_refiner.py`**: fixed the hardcoded, already-stale "~16,591 characters" citation
  in `build_refinement_messages`'s docstring -- points to `len(BASE_SYSTEM_PROMPT)` directly now
  instead of a number that drifts with every future rule change.
- **`tests/manual_prompt_rule_evals.py`** (new): 12 golden prompts, each tagged with the rule(s) it
  exercises and a checklist of what the response should/shouldn't do -- covers every rule this
  session's live QA has actually caught a violation of (fabrication, forecast confidence, funding
  snapshots, placeholder JSON, actual-result reporting, style defaults, logistics-intent
  recognition, sensitive-point handling, export paths, premature scheduling, hand-written print
  layouts). Deliberately named so the automated suite's `test_*.py` glob never picks it up --
  grading is manual/qualitative on purpose, since a brittle string-match on natural-language output
  would fail on rephrasing while a real violation slips through. Meant to be re-run before a
  `agent/prompts.py` change ships, not just when a new rule is added -- a rewrite can silently
  weaken a rule's effect even though the file still "has" it.
- **Not done**: a live QA pass comparing the 4 prompt-refiner personas' actual rewrite quality
  against each other -- flagged as needing a human judgment call across real queries, same as this
  session's other live-QGIS-only verifications, not something to guess at from the code alone.

## [1.2.4] — 2026-08-16

**Clarified illustrative workflow-preset examples (2026-08-16)**: caught in the same live Yemen
monitoring session as the v1.2.3 fix, on the very next turn after it -- the sequencing fix worked
(no premature `schedule_recurring_workflow` call), but the response's "Workflow Preset Structure"
preview showed a concrete JSON block with plausible-but-unconfirmed indicator field names
(`food_insec_pct`, `wash_deficit_pct`, `health_gap_pct`) sitting directly next to the real,
just-fetched `YEM_ADM1_boundary_hdx` layer name. HDX COD-AB admin boundaries only carry P-codes/
names/area metadata, never humanitarian indicators, so those fields don't exist on that layer --
the surrounding "once configured" phrasing hedged it, but a concrete JSON block next to real data
still reads as a claim about that data. Added prompt rule 32: any illustrative `workflow_json`/
tool-call JSON example with unconfirmed field names, paths, or values must be labeled explicitly as
a placeholder template, not presented as a ready structure -- extends rule 12's ban on inventing
real-world facts to illustrative examples specifically.

## [1.2.3] — 2026-08-16

**Fixed premature `schedule_recurring_workflow` calls (2026-08-16)**: caught live on the very first
real-world use of the recurring-monitoring feature (a Yemen severity/presence-gap/PiN monitoring
request) -- the model called `schedule_recurring_workflow` directly, before ever calling
`save_workflow_preset`, so it failed with "Workflow preset ... not found" (correct behavior; the
tool itself did the right thing). The response text that followed then explained what was still
needed without clearly restating that the tool call itself had failed, which the existing
false-success-narrative backstop (see the v1.0.1 entry below) correctly flagged as a mismatch to
the user. Two fixes: (1) a new prompt rule 31 in `agent/prompts.py` telling the model to gather and
confirm every step's concrete layer/field/file inputs, save the preset, and only then schedule --
never call `schedule_recurring_workflow` speculatively before the preset exists; (2)
`monitoring_tools.py`'s `_load_steps` "preset not found" error now includes a ready-to-use
`save_workflow_preset(...)` example with the preset name already filled in, so even without
re-reading `save_workflow_preset`'s own description, the fix is inline in the error itself.

## [1.2.2] — 2026-08-16

**Added recurring monitoring workflows (2026-08-16)**: closes `QGIS_AI_Agent_PRD.md` §5.3's
"scheduled/recurring workflow object" gap (pulled forward from Phase 4 vision into Phase 2 scope,
per the Atlas competitive review) -- re-running an analysis periodically and diffing results, e.g.
"which admin units moved into a worse severity class since last week." Deliberately scoped to
**in-session recurring only**: a schedule runs for as long as QGIS stays open with the plugin
loaded, driven by `QTimer` on the main Qt thread. Nothing runs while QGIS is closed, and nothing
here touches the OS scheduler (cron/Windows Task Scheduler) -- a true headless `qgis_process`
trigger was explicitly scoped out after a design check-in, since registering an OS-level scheduled
task is a system-settings change this plugin shouldn't make unilaterally.

- **`agent/scheduler.py`** (new): `WorkflowScheduler`, a `QObject` singleton holding one `QTimer`
  per active preset name, with a `workflow_tick_completed(preset_name, summary_text)` signal.
  Starting a schedule for an already-scheduled preset replaces it; `stop_all()` is called from
  `qgis_ai_agent.py`'s `unload()` so no timer outlives the dock widget.
- **`agent/tools/monitoring_tools.py`** (new): `run_monitoring_workflow` (one-shot re-run + diff),
  `schedule_recurring_workflow`, `stop_recurring_workflow`, `list_scheduled_workflows`. A monitoring
  workflow is a saved `save_workflow_preset` JSON blob shaped
  `{"steps": [{"tool": ..., "args": {...}}, ...]}`; steps are restricted to a fixed allowlist of
  read-only analysis tools (`calculate_severity_index`, `calculate_presence_gap`,
  `calculate_population_in_need`, `forecast_trend`, `field_statistics`, `population_access_gap`,
  `estimate_population_exposure`) -- never geometry edits or file writes, so an unattended
  recurring run can't silently repeat a destructive action. Each run's per-unit results (matched by
  the "unit" key convention `calculate_severity_index`/`calculate_presence_gap`/
  `calculate_population_in_need` already share) are diffed against the previous run and stored back
  under a `QgsSettings` key for next time.
- **Cost-conscious by design**: a scheduled tick computes a structural diff and posts a short
  summary into chat directly -- it does NOT spend an API call narrating the change every tick.
  Asking a follow-up question ("what changed?") is what triggers a real model turn, matching this
  session's broader API-cost-efficiency work.
- **UI (`ui/dock_widget.py`)**: connects `workflow_tick_completed` to a new
  `_on_scheduled_workflow_tick` slot that posts the summary as an assistant-role chat message, the
  same visual path a normal response uses, without spending a turn on it.

## [1.2.1] — 2026-08-16

**Added `calculate_population_in_need` (2026-08-16)**: closes section A of
`docs/HUMANITARIAN_GIS_FEATURE_REVIEW.md` -- `calculate_severity_index` ranks admin units 1-5 but
doesn't answer the number every HRP, donor brief, and allocation committee actually quotes: how
many people that severity translates to. The new tool composes `_compute_severity_index`'s
existing scoring with `estimate_population_exposure`'s existing zonal-statistics path (calls it
directly for its `pop_sum` side effect, reading the result back per-feature by fid rather than
trusting its `totals` dict, which is keyed by the layer's first field and not reliably
`unit_name_field`) to return a `population_in_need` total for the high-severity classes (default
4-5) plus a population breakdown per class. Units excluded from severity scoring (missing
indicator data) and units the population raster doesn't cover are both excluded from the total
rather than imputed as zero, matching `calculate_severity_index`'s own "exclude, never impute"
rule for exactly the same reason: silently zero-filling would understate an allocation input.
`output_field` writes each unit's population figure back to the layer for `apply_graduated_style`,
mirroring `_write_scores_to_layer`. Same thin-composite pattern as `calculate_presence_gap` and
`population_access_gap`.

**Implemented the Prompt Refinement Layer (2026-08-15)**: built out
`docs/PROMPT_REFINEMENT_LAYER_SPEC.md` end to end -- an optional, opt-in step that rewrites a longer or
ambiguous chat message into two better-specified candidates before it reaches `agent.run()`, addressing
two measured problems: ambiguous requests burning a full agentic turn to discover they're ambiguous,
and `ToolRouter`'s keyword/substring matching missing tools on vaguely-phrased queries (the 33%
recall-miss finding from `docs/API_COST_OPTIMIZATION_REVIEW.md`).

- **`agent/prompt_refiner.py`** (new): `should_refine()` skips messages under 6 words or when the
  feature is disabled; `refine()` calls the already-configured provider client with `tools=None` (so it
  can never enter `ToolRouter`/`TOOLS_SCHEMA` territory or trigger a tool call) and a short, dedicated
  system message per persona (general/humanitarian/urban_planning/defense_intel, reusing
  `docs/PRODUCT_TIERS.md` §4's taxonomy); `parse_refinement_response()` defensively validates the JSON
  output contract, matching `agent.py`'s existing `_real_execute_tool` parsing pattern -- never raises,
  degrades to `None` on anything malformed.
- **`max_tokens` threading** (prerequisite): added an optional `max_tokens` param to all 5 provider
  clients' `complete()` (previously only settable via the shared `DEFAULT_MAX_TOKENS`), so the
  refinement call's ~400-token output isn't billed/capped at the full 8096-token default.
- **Settings**: `qgis_ai_agent/prompt_refinement_enabled` (default **off** -- this adds a real small
  extra API call per refined message, shouldn't silently change every user's cost profile),
  `qgis_ai_agent/user_profile` (default `general`), and a reserved
  `qgis_ai_agent/prompt_refinement_model` key for a future advanced override. Both active keys are
  owned by `agent/prompt_refiner.py` and read via `is_refinement_enabled()`/`get_user_profile()`,
  matching `agent/chat_persistence.py`'s existing `PERSIST_SETTING_KEY` ownership precedent rather than
  being defined in the UI file. New checkbox + persona dropdown in Settings.
- **UI (`ui/dock_widget.py`)**: a separate panel above `ChatInputEdit` (decided over inline chat
  bubbles specifically so these cards never touch `conversation_history`/`chat_persistence.py` at all --
  they're not chat messages), modeled on the existing `confirm_btn`/`PREVIEW_READY` gate's
  explicit-button, nothing-auto-proceeds interaction language. Each of the two cards has "Use this" and
  "Edit first" (pre-fills `ChatInputEdit`, never auto-sends, mirroring the existing Edit & Resend
  pattern) buttons, plus a persistent "Send as typed instead" bypass. The refinement API call runs on a
  background thread (`refinementFetchedSignal`, mirroring `settings_dialog.py`'s
  `modelsFetchedSignal`/`_fetch_models` pattern) so it can never freeze the QGIS UI thread. `send_message()`
  was split into a thin fork plus `_dispatch_message()` (the original, unmodified send path) -- every
  failure mode (disabled, too-short message, API error, malformed response, a fresh send abandoning a
  stale open panel) falls straight through to `_dispatch_message(original_text)`, and only the final
  chosen text is ever logged to `conversation_history`, per the spec's "exit is always plain text, no
  trace left downstream" design goal.

29 new tests (579 total, was 550: 24 in `tests/test_prompt_refiner.py`, 5 `max_tokens` override tests
in `tests/test_providers.py`). No tool-count change (125) -- this feature adds no new agent tools, only
a pre-processing UI step.

**Live-verified (2026-08-15)**: manual QA of the two-card flow against all 5 providers, including
Ollama's structured-JSON reliability on a small local model, confirmed working; the feature is also
confirmed a true no-op end to end when the Settings checkbox is off (the default).

**API cost review, Tier 3 (2026-08-15)**: implemented `docs/API_COST_OPTIMIZATION_REVIEW.md` §3, the
lower-urgency items.

- **`max_tokens` cap standardized across all 5 providers**: only Claude's client capped output size
  before this (its own local `DEFAULT_MAX_TOKENS`). Added a shared `DEFAULT_MAX_TOKENS = 8096` to
  `agent/providers/base.py` and wired it into OpenAI/Gemini/OpenRouter/Ollama's request payloads --
  rarely an issue in practice (tool-calling responses are typically short), but a real, if uncommon,
  runaway-output cost risk with nothing standardizing it before now.
- **`pick_model_for_complexity`'s fragile fallback tightened**: when no naming-convention keyword
  matches either tier, "simple" used to fall back to the shortest model *name string* as a proxy for
  "smaller/base variant" -- but string length isn't a reliable signal of model size or cost (a real
  `-mini`/`-nano` suffix would already have scored via the existing keyword list; a model with truly no
  naming signal at all gives no honest basis to guess "smaller" from a shorter string). Both tiers now
  fall back to the same predictable choice, the first entry in the list, rather than "simple" pretending
  to a precision it didn't have.
- **Routing-recall regression test**: added a table-driven test covering all 9 queries from the
  original §0 measurement (not just the 3 that were failing), so a future change to `ToolRouter` or a
  tool's description can't silently regress recall on a query that happened to already be passing.

5 new tests (550 total, was 545). No tool-count change (125).

**API cost review, Tier 2 (2026-08-15)**: implemented `docs/API_COST_OPTIMIZATION_REVIEW.md` §2.1-2.3.

- **Prompt caching beyond Claude**: OpenRouter (the default provider) now marks the system prompt with
  an Anthropic `cache_control` breakpoint when the active model is `anthropic/*`, the same mechanism
  the native Claude client already uses -- OpenRouter documents passing this field through unmodified
  to the underlying Anthropic API for those models. No-op for every other model, including the default
  free-tier `FALLBACK_MODELS` chain (none of which are `anthropic/*`). **Unverified against a live
  response's cache-hit fields** -- no network access in this environment to test -- flagged clearly in
  the function's own docstring; needs confirming against real usage before being trusted as working.
  OpenAI/Gemini's own caching (documented as automatic/implicit, no code required) needs the same live
  verification, not a code change -- nothing to implement there.
- **Cached `gemini_grounded_search`/`openai_grounded_search`**: both are real, billed LLM API calls that
  had no caching at all, unlike every "fetch external thing" tool in `agent/tools/` (which all share
  `_LOOKUP_CACHE`'s TTL-cache pattern). Added a 30-minute TTL cache (by query + model) directly in
  `agent/providers/gemini.py`/`openai.py`'s `grounded_search()` -- the actual call site for both, since
  `agent.py`'s two-phase dispatch calls `grounded_search()` directly and bypasses the registered tool
  functions entirely. A new small standalone `TTLCache` duplicate lives in
  `agent/providers/_search_cache.py` rather than importing `agent.tools._cache_utils`'s existing one:
  nothing in this codebase currently imports across the providers/tools package boundary in either
  direction, and `agent/tools/__init__.py` eagerly imports all 14 tool modules to populate the tool
  registry, so doing so risks a circular import for any code path that loads a provider module before
  `agent.tools` has already been loaded. Error responses are never cached.
- **Moved presentation-only caveats from tool descriptions into tool results**: `generate_html_dashboard`
  (the CDN/offline caveat) and `fetch_building_footprints` (the baseline-not-live caveat) both carried
  verbose "how to present this to the user" guidance in their tool *description*, paid on every call
  where `ToolRouter` merely selects the tool as a routing candidate, whether or not it's actually
  invoked -- both caveats are also already covered by existing `BASE_SYSTEM_PROMPT` rules (27 and 28),
  making the description text pure duplication. Trimmed both descriptions and added the same wording as
  a `connectivity_note`/`baseline_caveat` field in the result instead, so it's paid only when the tool
  actually runs and stays machine-locatable in the tool's own output rather than relying on the prompt
  rule alone.

11 new tests (545 total, was 534). No tool-count change (125).

**API cost review, Tier 1 (2026-08-15)**: implemented the highest-leverage findings from
`docs/API_COST_OPTIMIZATION_REVIEW.md` (§1.1-1.3), a code-grounded review of where LLM token spend and
external API calls were being wasted across the agent loop, prompt design, and tool routing.

- **`ToolRouter` recall**: a test against 9 realistic paraphrased queries found 3 of 9 (33%) never made
  it into the candidate tool set the model was allowed to choose from at all -- a missed tool either
  fails the turn outright or forces a heavier `execute_pyqgis_script` fallback, each a real cost, not
  just a quality issue. Fixed three ways: (1) the ranking's tie-break bug -- Python's stable sort meant
  the many tools scoring 0 always filled remaining `top_k` slots in fixed file-registration order, a
  silent, consistent bias toward whichever tools happened to be defined earliest, not a relevance
  signal; candidates are now shuffled before scoring so ties break differently each call. (2) A small
  curated alias list (`_TOOL_ALIASES` in `tool_router.py`, routing-only, not sent to the model) for the
  4 tools with measured paraphrase gaps -- `calculate_severity_index`, `calculate_presence_gap`,
  `load_3w_data`, `generate_html_dashboard` -- directly closing the 3 measured misses. (3) Raised
  `top_k` from 30 to 40 now that the registry has grown to 125 tools (was 61 when the router was
  originally tuned).
- **`calculate_severity_index`/`calculate_presence_gap` unbounded results**: both returned one full
  entry per admin unit with no cap -- for an ADM3-level layer (routinely hundreds of units) an
  uncapped, worst-first-sorted JSON blob that gets resent on every remaining iteration of the turn and
  lingers in `conversation_history` for several turns afterward. Capped each returned list to the worst
  50 entries (`_cap_entries` in `analysis_tools.py`) with a `truncated`/total-count field so the model
  can ask for a specific unit or class if it needs more. `output_field` layer write-back still uses the
  full, untruncated list -- only the JSON returned to the model is capped, styling/mapping the complete
  dataset is unaffected.
- **`model_selector.classify_complexity`**: `history_len > 6` alone forced the expensive "complex"
  model tier, with no other signal needed. Since `conversation_history` grows by 2 messages per turn,
  this tripped after only 3-4 exchanges and then stayed tripped for the rest of the session regardless
  of what was actually being asked -- "zoom to that layer" got routed identically to a genuine
  multi-step analysis. Dropped entirely; the existing content signals (multi-step phrasing, quantity
  words, 2+ distinct GIS operations) are already meaningful on their own and don't need a
  session-length proxy stacked on top.

9 new tests (534 total, was 525). No tool-count change (125) -- no new tools, only routing/result-shape
changes to existing ones.

**Fixed `create_print_layout` exporting a blank map area (2026-08-15)**: the previous PNG/DPI export
fix (below) closed the tool-coverage gap but the exported PDF/PNG still came back with the map frame
rendered as a solid ocean-blue rectangle -- the real map layers never appeared. Root cause:
`QgsLayoutItemMap` was constructed and had `setExtent()` called on it while still at its default
zero-size rect. Per the documented PyQGIS layout pattern, a map item needs a nonzero placeholder rect
(`setRect(...)`) *before* `setExtent()` -- setting an extent against a zero-size frame produces a
degenerate scale, and QGIS falls back to a hugely zoomed-out view that, on an OSM basemap, renders as
flat ocean color. Fixed by calling `map_item.setRect(20, 20, 20, 20)` immediately after construction,
before `setExtent(canvas.extent())`. No new tests added -- this is inside the same deep QGIS
object-graph construction covered by `create_print_layout`'s existing degrade-only test convention;
needs live-QGIS confirmation.

**Reworked `create_print_layout`'s layout geometry for a full-country map (2026-08-15)**: the previous
`zoom_to_layer` fix got a full, uncropped Yemen map rendering correctly, but the surrounding layout
elements were still tuned for a small/zoomed-in map and broke visibly once real content reached the
page edges: the legend's category text ran off the page (its `resizeToContents` default of `True`
always expands it to its full natural content width regardless of any `attemptResize()` call, so it
was never actually constrained by the box position chosen for it), the legend/summary column started
15mm inside the map item's own right edge (invisible against a cropped view, a real overlap against the
full country -- Socotra/Al Maharah's labels visibly collided with the summary panel text), and the
scale bar's hand-tuned 1000m/segment setting produced overlapping, garbled numbers at a country-wide
scale it was never tuned for. Fixed: `legend.setResizeToContents(False)` before an explicit resize, so
long category labels wrap within a fixed column width instead of overflowing past the page; recomputed
map/legend/scalebar/body geometry so the right-hand column sits fully clear of the map's own right edge
and inside the page's margins; and `scalebar.applyDefaultSize(QgsUnitTypes.DistanceKilometers)` instead
of a fixed segment/unit count, which picks a sensible scale-bar size for whatever the map's actual
current scale is rather than a value hand-tuned for one specific prior zoom level. The title label now
spans the full page width as a masthead instead of only the map column. `setResizeToContents` and
`applyDefaultSize` are real, documented `QgsLayoutItemLegend`/`QgsLayoutItemScaleBar` methods, but --
same caveat as every `create_print_layout` fix this round -- this is inside the deep QGIS object-graph
construction this file can't unit-test outside real QGIS; needs live confirmation. 525/525 tests still
passing (no new tests -- pure geometry/method changes inside the untestable construction path). No
tool-count change (125).

**Added `zoom_to_layer` to `create_print_layout` (2026-08-15)**: after the previous fix (steering the
model back to using this tool instead of hand-writing code), a live retest correctly invoked
`create_print_layout` and the map finally rendered real content -- but cropped, missing large parts of
Yemen (southern governorates cut off, legend/labels clipped at the page edge). Root cause:
`create_print_layout`'s map area captures whatever extent `canvas.extent()` currently is, and nothing
guaranteed that was the full national extent rather than a leftover zoomed-in view from an earlier tool
call in the same conversation (e.g. a prior `zoom_to_feature`). Rather than relying on the model to
reliably chain a separate `zoom_to_layer` call before `create_print_layout` -- prompt-only steering had
already proven unreliable once this session, for the hand-written-code issue above -- added an optional
`zoom_to_layer` parameter directly to `create_print_layout` that fits the canvas (and the map item) to
a named layer's full extent, through the same CRS-safe `_extent_to_canvas_crs` transform used by
`zoom_to_layer`/`zoom_to_feature`, before capturing the map. New prompt guidance tells the model to pass
this parameter (with the boundary/AOI layer's name) for country/region-wide sitrep maps rather than a
separate preceding tool call. 3 new tests (525 total, was 522). No tool-count change (125) -- an
existing tool gaining an optional parameter.

**Strengthened steering away from hand-written print-layout code (2026-08-15)**: the two
`create_print_layout` fixes above (blank-map extent bug, `ModeRaster` crash) turned out not to be
what was actually breaking the user's live sitrep export -- the tool-call transcript for the failing
request showed `create_print_layout` was never even called. The model hand-wrote the entire layout
composition via `execute_pyqgis_script` again, bypassing both fixes entirely, almost certainly because
the request wanted a richer composition (a bulleted findings panel, a specific layout name, a custom
scale bar segmentation) than the tool's existing description made clear it already supports. Added new
prompt rule 30, an explicit, unconditional instruction to never hand-write
QgsPrintLayout/QgsLayoutItemMap/QgsLayoutExporter code via `execute_pyqgis_script` for any reason --
including wanting more composition control -- and to accept `create_print_layout`'s defaults (its
`body_text` already accepts multi-line text for bulleted panels via `\n`) rather than reimplementing
the object-graph by hand. Also strengthened the tool's own description to state the same thing more
forcefully and spell out the multi-line `body_text` support explicitly. This is steering guidance, not
a code fix -- the two underlying `create_print_layout` bugs fixed above are still real and still worth
having fixed for whenever the tool is actually invoked, but the model choosing not to call it at all
was the actual live-reproduced failure this time.

**Added `expression` support to `zoom_to_feature` (2026-08-15)**: caught live -- a request to "zoom
to the layer, then zoom to the feature for Ma'rib" correctly used the dedicated `zoom_to_layer` tool
for the first half, but `zoom_to_feature` only ever accepted a numeric `feature_id`, and the model
didn't have Ma'rib's id in advance. It fell back to hand-writing a lookup-and-zoom
`execute_pyqgis_script`, which bypassed the CRS-transform fix below entirely (that fix only lives
inside the dedicated tool functions) and reproduced the exact same "canvas lands near the coordinate
origin" bug on an ostensibly already-fixed code path -- confirmed live by the canvas showing a
degenerate 1:24 scale and a flat blue no-data view. `zoom_to_feature` now accepts an optional
`expression` alongside `feature_id` (e.g. `"name = 'Ma\'rib'"`), validated the same way as
`apply_labels`' expression parameter, requiring the expression to match exactly one feature. 6 new
tests. No tool-count change (125) -- an existing tool gaining an optional parameter.

**Fixed `create_print_layout` failing outright with `QgsLayoutItemPicture has no attribute
'ModeRaster'` (2026-08-15)**: caught in the same live retest as the blank-map fix above -- the north
arrow item construction called `north_arrow.setMode(QgsLayoutItemPicture.ModeRaster)`, and neither the
`setMode()` method nor the `ModeRaster` attribute exist on `QgsLayoutItemPicture`; this was a
fabricated API call that made the whole tool call fail before any export could happen. Fixed by
removing the erroneous call -- `setPicturePath()`'s `format` argument already defaults to
`FormatUnknown`, which auto-detects SVG vs. raster from the file extension, so no explicit mode-setting
call is needed at all for the bundled north-arrow SVG. Same untestable-outside-QGIS caveat as the fix
above.

## [1.2.0] — 2026-08-14

Humanitarian crisis-management and fund-allocation feature pass, from a field-analyst-
perspective review of what already served that workflow and what genuinely didn't. Every
tool below was checked against real code/live data before being built, not assumed from the
review's own framing -- two items (P-code capture, imagery-based feature extraction) turned
out to need a different underlying approach than what was originally asked for, and both were
corrected rather than built as literally scoped. Tool count: 116 -> 125.

**`apply_labels` expression support + `create_print_layout` PNG/DPI export and summary panel +
export-location prompt guidance (2026-08-15)**, all from the same live session: a sitrep map export
came back with a blank map area, and the transcript showed why -- `create_print_layout` only ever
supported PDF export (no PNG/image export, no DPI control, no summary-text panel), and `apply_labels`
only supported a single raw field (no expression support for combined labels like governorate name
+ P-code + org count) -- so the model had no choice but to hand-write raw PyQGIS layout/labeling
code via `execute_pyqgis_script` for a genuinely standard sitrep composition. That hand-written code
is exactly where two real API mistakes came from (`QgsLegendStyle` has no `Item` attribute; `QFont`
has no `Italic` attribute -- confirmed neither exists on those classes), and almost certainly where
the blank-map bug itself originated, in code that was never saved and can't be inspected after the
fact.

Closed the actual tool-coverage gaps instead of trying to patch ephemeral generated code:
- `create_print_layout` now exports to `.png`/`.jpg`/`.jpeg` (via `QgsLayoutExporter.exportToImage`)
  in addition to `.pdf`, with a new `dpi` parameter (default 300) applied to both export paths, and
  an optional `body_text` parameter for a summary/sitrep panel. Also fixes a real pre-existing silent
  bug along the way: previously, passing any `output_path` not ending in `.pdf` did nothing at all,
  no error, no export -- now an unsupported extension returns a clear error instead of silently
  no-opping. Export result codes are also checked now (`QgsLayoutExporter.Success`), where the old
  code ignored `exportToPdf`'s return value entirely.
- `apply_labels` gains an optional `expression` parameter (alongside the existing `target_field`) --
  a QGIS expression combining multiple fields/literals into one label (e.g.
  `adm1_name || ' [' || adm1_pcode || ' | ' || org_count || ' Orgs]'`), validated via the same
  `QgsExpression().hasParserError()` pattern already used elsewhere in this file, so a bad expression
  fails cleanly instead of producing a blank/wrong label.
- New prompt rule (29): before running a tool that produces a real deliverable file, ask where to
  save it if the request didn't say -- don't silently pick a system temp path and only surface it
  buried in a results table. Direct response to the user's own explicit feedback after the exported
  PDF/PNG landed in `AppData\Local\Temp` with no path mentioned until asked for.

14 new tests (516 total, was 508) across `apply_labels` (input validation, expression-parse-error
handling, and confirming `isExpression`/`fieldName` are actually set correctly) and
`create_print_layout` (degrade coverage -- no live-object-graph test, matching this suite's own
established convention for similarly deep QGIS-object-graph functions with no pre-QGIS-touch
validation, e.g. `calculate_service_area`/`_write_scores_to_layer`). No tool-count change -- both
are existing tools gaining optional parameters.

**Fixed `zoom_to_layer`/`zoom_to_feature` zooming to the wrong location when the layer's CRS differs
from the project's (2026-08-15)**, caught live: a user reported the canvas "shifting and losing
focus" right after zooming to a freshly fetched Yemen boundary layer. Root cause: both tools passed
`layer.extent()`/`feature.geometry().boundingBox()` straight into `canvas.setExtent()`, which
expects the extent already in the *canvas's* CRS -- but that extent is in the *layer's* CRS. Most
projects using an OSM basemap run in Web Mercator (EPSG:3857, meters), while every layer this
plugin fetches (`fetch_hdx_admin_boundaries`, `fetch_geoboundaries`, `fetch_building_footprints`) is
WGS84 (EPSG:4326, degrees) -- passing degree-magnitude numbers into a meters-based canvas silently
lands the view near the map's coordinate origin, nowhere near the actual layer, exactly matching
the reported symptom. New `_extent_to_canvas_crs` helper transforms the extent via
`QgsCoordinateTransform` before it reaches `setExtent()`, short-circuiting when the CRSes already
match and falling back to the untransformed extent (rather than crashing the tool call) if the
transform itself fails. Swept the rest of the codebase for the same pattern -- no other instance
found (`layout_tools.py`'s one other `setExtent()` call takes FROM the canvas's own extent, already
in the right CRS, no bug there). 8 new tests, including two that assert both tools actually route
through the new transform rather than calling `setExtent()` directly (the exact regression this
fix prevents). No tool-count change -- both are existing tools, internal fix only.

**`output_field` on `calculate_presence_gap` (2026-08-15)**, the second follow-on item flagged in
the humanitarian review's revised assessment, built after live evidence made the case directly:
a real session hit `QgsSimpleFillSymbolLayer(): argument 2 has unexpected type 'QColor'` --
`execute_pyqgis_script` hand-rolling a renderer to color-code presence-gap status by hand, because
`calculate_presence_gap` had no field on the layer for `apply_categorized_style` to use, unlike
`calculate_severity_index`. New `output_field` parameter writes each high-severity unit's status
(`'gap'`/`'covered'`/`'unmatched'`) back to the layer via a new `_write_presence_gap_status_to_layer`
(mirrors `_write_scores_to_layer`'s existing pattern exactly); units outside the high-severity
classes are left unset, not given a fabricated "fine" status, since they were never classified by
this analysis at all. The tool description now explicitly tells the agent to use `output_field`
plus the existing styling tools instead of hand-writing PyQGIS renderer code for this. No
dedicated unit test for the QGIS write path itself -- matches this codebase's own established
precedent (`_write_scores_to_layer` has none either) -- covered by a degrade test with
`output_field` set. No tool-count change -- existing tool gaining an optional parameter.

**Human-readable popup labels in `generate_html_dashboard` (2026-08-15)**, a real gap caught in
live use of the v1.2.0 dashboard: popups showed raw field names verbatim (`food_insec_pct`,
`wash_depriv_pct`) instead of anything a non-technical viewer would read as language. Confirmed
`folium.GeoJsonPopup` supports an `aliases` parameter before using it -- each layer entry now takes
an optional `popup_labels` ({field: display label}) dict; a field left unlabeled falls back to a
purely mechanical Title Case of its raw name (`food_insec_pct` -> `Food Insec Pct`) rather than the
literal snake_case, but that fallback is explicitly not a substitute for a real label -- the tool
description now tells the agent to always supply `popup_labels` for any field whose meaning it
actually knows, since only the agent (not this tool) can tell "food_insec_pct" means "Food
Insecurity (IPC 3+) %". Verified against the real originating case: rebuilt the actual Yemen
severity-index dashboard's popup with explicit labels for four of five fields and confirmed live in
a browser that both the explicit labels and the one deliberately-unlabeled fallback rendered
correctly. 7 new tests. No tool-count change -- existing tool gaining an optional parameter.

**`fetch_building_footprints` (2026-08-14)**, a reframed version of PRD Tier-3 item #11 ("semi-
automated feature extraction from imagery"), which the humanitarian review's Tier 3 correctly said
not to build in this pass -- deferred, large-scope, "via vision models." Investigated instead of
taking the deferral at face value: checked what was actually still missing against real code (not
the PRD's own claims) and found the item decomposes into three pieces, two of which are already
done -- roads via the existing `fetch_osm_features` (`key='highway'`), damage/change detection via
the existing `calculate_raster_change_detection` -- leaving only building footprints as a genuine
gap. And "via vision models" turned out to be the wrong approach for that gap: asking a
general-purpose vision LLM to output precise polygon vertex coordinates is a well-known unreliable
pattern, a real risk for humanitarian digitization/damage work where geometric accuracy has
consequences. Found and verified live instead: Microsoft's Global ML Building Footprints dataset
(1B+ buildings, 225 countries/regions, CDLA Permissive 2.0, actively maintained -- updated
2026-08-13, one day before this was written) -- pre-computed, already-vetted polygons, no local ML
inference needed. This made the "large-scope, deferred" item into a small, well-scoped addition:
one new tool, `fetch_building_footprints(country_name, bbox, max_features=5000)`, following the
same two-phase network/main-thread pattern as `fetch_geoboundaries`/`fetch_hdx_admin_boundaries`.

Verified thoroughly before writing tests: hand-rolled the Bing Maps quadkey tile math (bbox ->
covering tiles at the dataset's zoom level) rather than adding a new dependency for it, but cross-
checked it against the real `mercantile` library (the one Microsoft's own example notebook for this
dataset uses) across five points including the equator, near-antimeridian, and near-max-latitude
edges -- all matched exactly -- before hardcoding any of it. Ran the full live pipeline end-to-end
against real data for a small area in Aden, Yemen: real network fetch, real building polygons,
confirmed zero features fell outside the requested bbox after cropping. `country_name` is free text
(Microsoft's dataset isn't ISO3-indexed) matched against the dataset's own 225 location names;
ambiguous or unmatched input returns candidates instead of guessing. Stated honestly in the tool
description, prompt rule 28, and USER_GUIDE: this is Microsoft's periodic baseline dataset, not
live extraction from a specific image, and can lag real conditions by months -- never to be
presented as current/post-event structure status; damage assessment against a specific image pair
should use `calculate_raster_change_detection` instead.

16 new tests (492 total, was 476). Full suite: 492/492 passing. Tool count: 124 -> 125.

**OCHA cluster color presets (2026-08-14)**, Tier-2 item #8 from the humanitarian-analyst review --
`apply_categorized_style` gains an optional `palette='humanitarian_cluster'` (alias `'ocha'`) that
colors categories matching a known IASC global cluster name (Health, WASH, Food Security,
Protection, Emergency Shelter, Nutrition, Education, Logistics, CCCM, Early Recovery, Emergency
Telecommunications, plus common aliases like 'FSL'/'Shelter') using commonly recognized humanitarian
cluster colors; categories that don't match keep the existing qualitative palette, so a mixed field
(some cluster names, some not) still renders sensibly. `apply_graduated_style` gains an optional
`cluster` parameter that tints a graduated choropleth's ramp toward that cluster's color (a
near-white-to-cluster-color sequential ramp via `QgsGradientColorRamp`, the correct ramp family for
ordered/graduated data) instead of the auto-selected Viridis/Cividis -- e.g. a WASH coverage %
choropleth rendered in WASH's color.

Checked before hardcoding any hex values, not assumed: searched for an official OCHA cluster color
specification (OCHA's graphics stylebook, brand.unocha.org) and found no publicly documented
per-cluster hex-code standard exists -- so this is stated honestly in the tool description and here
as a commonly recognized color association (as seen across ReliefWeb/Shelter Cluster/humanitarian
mapping products), not a verified official spec. The 11 cluster names themselves are the real,
well-defined IASC global cluster list. Unrecognized `palette`/`cluster` values degrade to the
existing default behavior with a `palette_warning`/`cluster_warning` in the result, never a hard
error. 7 new tests. No tool-count change -- both are existing tools gaining optional parameters,
not new registrations.

**`generate_html_dashboard` (2026-08-14)**, Tier-2 item #6 from the humanitarian-analyst review --
an interactive HTML situation dashboard (Leaflet/Folium map with layer toggles and popups) from one
or more vector layers already in the project, closing the review's §2G gap ("no non-GIS-user-facing
output"). New optional dependency: `folium` (pulls in `branca` for choropleth coloring), added to
`requirements.txt` and `agent/deps.py`'s `REQUIRED_PACKAGES` -- same qpip-or-manual install pattern
as matplotlib/pdfplumber.

The review called this "self-contained... no server dependency." Verified against real generated
output before building anything: Folium's default HTML embeds Leaflet/Bootstrap/jQuery and
OpenStreetMap basemap tiles from public CDNs, fetched only when the file is *opened*, not when it's
generated. So the accurate framing -- and what the tool description now says -- is "single file,
no backend server needed to view," not "works fully offline"; corrected rather than carried the
review's overstatement forward. Split into a pure `_build_dashboard_html(layers, title)` core
(already-extracted GeoJSON in, HTML string out -- no QGIS needed, same split as
`_compute_severity_index`) and a thin QGIS-dependent wrapper that reprojects each layer to WGS84
(Leaflet needs lon/lat; a layer in any other CRS, e.g. UTM, would otherwise render at nonsensical
coordinates) via a new `_write_layer_geojson_wgs84`, kept separate from the existing `_write_vector`
so `export_layer`/`export_to_csv`'s native-CRS behavior is untouched.

Verified more thoroughly than most tools in this pass: rendered real generated dashboards in an
actual browser (not just inspected the HTML string) -- confirmed live OSM tiles, choropleth
coloring by a severity_score field, layer-toggle control, and click-to-inspect popups showing the
indicator values behind the score, end-to-end through the exact shipped code path. Also measured
real output size (~95KB for 60 polygons with 5 attributes each) to set expectations for larger
admin-boundary layers -- the tool description points at the existing `simplify_geometry` tool for
large/complex layers rather than adding new simplification logic. Raster layers are explicitly out
of scope (vector only) -- correctly georeferencing a raster overlay is materially more complex and
wasn't what the review's own example (severity-score polygons) needed. 16 new tests. Tool count:
123 -> 124.

**`generate_sector_coverage_report` (2026-08-14)**, Tier-2 item #9 from the humanitarian-analyst
review: the standard "beneficiaries reached vs. target, by sector" (or by admin unit, or any other
categorical field) report table and bar chart in one call, instead of chaining `aggregate_data` +
`generate_chart` by hand -- the same "package existing primitives into one call" pattern already
used for `add_incident_point`'s hardcoded styling. Sums `reached_field` (and `target_field`, if
given) per `group_by_field` value via the existing, already-tested `aggregate_data`, computes a
coverage percentage per group, and renders a bar chart via the existing `generate_chart`. When a
target is given, the table sorts worst-coverage-first, with groups that had an unusable/missing
target value sorted alongside the worst performers rather than silently last -- confirmed by hand
(WASH 800/2000=40%, Shelter 200/500=40%, Health 900/1000=90%, and a group with a non-numeric target
value sorting first with `coverage_percent: null`) before writing tests. Tool count: 122 -> 123.

**`fetch_hdx_admin_boundaries` (2026-08-14)**, Tier-2 item #5 from the humanitarian-analyst review,
rebuilt on a different premise than the review originally proposed. The review asked for P-code
capture on `fetch_geoboundaries`; live verification (already logged above) found geoBoundaries'
`gbOpen` release publishes no P-codes at all, so there was no existing field to carry through. The
actual fix is a different data source: OCHA's own Common Operational Dataset - Administrative
Boundaries (COD-AB), published per-country on HDX under the consistent naming `cod-ab-{iso3}` --
confirmed live against Syria, Yemen, DR Congo, and Somalia, all published by OCHA FISS with the
same schema. Unlike geoBoundaries, COD-AB genuinely carries P-codes as `adm{N}_pcode` attributes
(e.g. `adm1_pcode` = `YE12` for Yemen) -- verified by downloading and unzipping real HDX resources,
not assumed from the dataset description. `fetch_hdx_admin_boundaries(iso3, admin_level)` follows
`fetch_geoboundaries`'s existing two-phase network/main-thread pattern: looks up the country's
COD-AB package, downloads its boundaries zip, extracts just the requested admin-level GeoJSON, adds
it as a layer, and reports which field holds the P-code (`pcode_field`) so it can be passed
straight to `calculate_severity_index`'s `unit_name_field` or `calculate_presence_gap`'s
`presence_admin_field` for a reliable join instead of fragile name-string matching. A 404 (no
COD-AB dataset for that country -- coverage isn't universal) is reported as exactly that, with an
explicit pointer to fall back to `fetch_geoboundaries` for broader coverage without P-codes. 6 new
tests, including a full pipeline test (package lookup -> zip download -> member extraction ->
pcode-field detection -> temp file write) against a real in-memory zip, with only the two network
calls mocked. Tool count: 121 -> 122.

**Provenance footer on `generate_report`/`generate_spatial_report` (2026-08-14)**, Tier-2 item #7
from the humanitarian-analyst review: both report tools now take an optional `source_layers` list
and, when given one, append a "Data Sources & Provenance" section built from what
`agent/lineage.py` already tracks per layer (tool, parameters, source layers, timestamp) --
`agent.py` has tagged every successful layer-producing tool call with this since lineage tracking
was first added, it just wasn't surfaced in generated documents until now. A layer that's missing
from the project, or was loaded directly rather than created/modified by an agent tool, is reported
as such rather than silently dropped from the section -- a report implying full provenance when a
layer's actual origin is unknown would be worse than no provenance section at all, especially for
this tool's stated audience (fund-allocation committees and donors, rarely QGIS users themselves,
per the review's own framing). No new tool count change -- both are existing tools gaining an
optional parameter, not new registrations.

**`load_3w_data` + `calculate_presence_gap` (2026-08-14)**, the last open Tier-1 item from the
humanitarian-analyst review: a 3W/4W ("who does what where") CSV/Excel loader, plus a
severity-vs-presence overlay for finding admin units where need is high but organizational
response is thin or absent -- the standard coverage-gap question behind response-planning and
fund-allocation targeting. `load_3w_data` reads a 3W/4W activity file and aggregates it into
per-admin-unit organizational presence (distinct org count/list, optional sector coverage,
activity-row count) -- deliberately counts distinct organizations, not activity rows, since "12
activities" and "3 organizations" answer different questions and conflating them overstates
presence. `calculate_presence_gap` composes this with the existing severity-index math
(`_compute_severity_index`, unchanged, same method as `calculate_severity_index`): computes
severity from indicator fields on a polygon layer, loads the 3W/4W file, and joins the two by
admin-unit name (case/whitespace-insensitive). High-severity units with no match at all in the 3W
data are reported as a separate `unmatched` bucket rather than folded into confirmed
zero-presence gaps, since an unmatched name could just as easily mean a spelling/P-code mismatch
between the two datasets as genuine absence -- collapsing the two would risk misdirecting funding
based on a data-entry artifact. Both tools are pure Python (no QGIS needed for the 3W/4W read
itself); `calculate_presence_gap`'s layer-reading half inherits `calculate_severity_index`'s
existing unverified-live-QGIS caveat. Verified via hand-traced join scenarios (unmatched vs.
confirmed-gap vs. covered, across severity-class and presence-threshold boundaries) in addition to
unit tests. Tool count: 119 -> 121.

**`population_access_gap` (2026-08-15)**, the second Tier-1 item from the humanitarian-analyst
review: how many people, and what % of a population base, are beyond a given travel distance/time
from the nearest facility ("X people are more than 30 minutes from a functioning health facility")
-- the standard access-to-services statistic in gap analysis and cluster reporting, and the review's
own example of two already-working tools (`calculate_service_area`, `estimate_population_exposure`)
never being chained together. Genuinely thin: builds each facility's reach polygon via
`calculate_service_area`, merges and dissolves them (`native:mergevectorlayers` +
`native:dissolve`) so overlapping coverage isn't double-counted, intersects with the population
base (`native:intersection`), then runs `estimate_population_exposure` on both the full base and
the reachable slice to get `gap_population`/`gap_percent`. A zero-overlap intersection (facility
reach doesn't touch the population base at all) is handled explicitly as 0 reachable population,
rather than trusting `estimate_population_exposure`'s behavior against an empty layer, which isn't
a path this codebase has verified live. Inherits `calculate_service_area`'s existing "best-effort,
unverified without a live QGIS session" caveat, plus its own for the merge/dissolve/intersect
chain. Tool count: 118 -> 119.

**`obfuscate_sensitive_points` (2026-08-15)**, the geoprivacy/Do No Harm safeguard the humanitarian
review flagged as operational risk rather than just a missing feature -- `add_incident_point`/
`add_point_layer` already made it trivial to plot exact coordinates of protection-sensitive
individuals (GBV survivors, individually-identified IDP households) with no obfuscation step in
between. Three methods, all in the layer's own CRS units (documented explicitly, since a "500m"
radius on a geographic CRS would actually mean 500 degrees): `jitter` (random displacement within
a radius, using a uniform-AREA disk sample -- verified with a 20,000-sample Monte Carlo check that
P(r < R/2) lands at ~0.25 as area scaling predicts, not the ~0.50 a naive uniform-radius draw would
give, which would silently under-protect points near their true location); `grid_snap` (collapses
every point sharing a square grid cell to that cell's centroid -- the strongest of the three, since
it destroys individual-point identity rather than displacing it; square rather than hexagonal,
since this codebase has no geometry library to verify hex-coordinate math against); and
`admin_unit_snap` (moves each point to the centroid of the admin-boundary polygon it falls within).
The method and its parameter are always included in the tool's output so they're disclosable
alongside any map or report. New prompt rule (26) recommends this step for protection-sensitive
point layers specifically -- never applied silently or automatically, since whether a given point
layer needs it is a judgment call about the data, not something to guess at.

**`calculate_severity_index` (2026-08-15)**, following the same humanitarian-analyst-perspective
review of crisis-management/fund-allocation coverage: a composite multi-indicator severity/needs index
(JIAF/INFORM-style) over admin-unit polygons -- min-max normalizes N numeric indicator fields
(with `invert_indicators` for fields where higher raw value means a better situation), applies
relative weights, and returns a 0-1 composite score plus a 1-5 equal-interval severity class per
unit, ranked worst-first. Identified as the load-bearing gap: `weighted_overlay_analysis` already
combines rasters, but fund-allocation decisions are built from tabular indicators joined to admin
units, which nothing in the existing tool set did. Units missing any indicator are excluded and
listed, never imputed; indicators with no variation across units are flagged, since they silently
contribute nothing to the ranking. Hand-verified against a worked 3-unit/2-indicator example
before trusting it, including confirming that omitting `invert_indicators` on an anti-correlated
indicator pair makes every unit collapse to an identical, useless score.

Tool count: 116 -> 118 (`obfuscate_sensitive_points`, `calculate_severity_index`).

Also corrected `QGIS_AI_Agent_Feature_List.md`, which still claimed no shortest-path/routing tool
existed anywhere in the codebase -- true when that row was last written (2026-08-10), stale since
`agent/tools/logistics_tools.py` was added in the ArcGIS-parity round (present since v1.0.1).

Three further findings from that review -- a geoprivacy/obfuscation tool (jitter/hexbin/admin-unit
snapping before plotting sensitive points), P-codes in `fetch_geoboundaries` output (confirmed
live against the real API: geoBoundaries' `gbOpen` release doesn't provide P-codes at all, so this
isn't fixable by capturing an existing field -- only by joining a separate P-code crosswalk after
the fact), and a 3W/4W operational-presence loader -- are logged as follow-up, not built in this
pass.

## [1.1.0] — 2026-08-13

Interface modernization and provider consolidation pass, driven directly by user/colleague
feedback on the chat experience.

**Security/reliability/infrastructure pass (2026-08-14)**, following a full code review of the
v1.1.0 changes (agent loop, task runner, SSRF guard, and the second plugin tree's maintenance
process). Each item below was confirmed live -- exploited or reproduced before being fixed, not
assumed -- before being fixed.

### Security
- **SSRF guard now re-validates every HTTP redirect, not just the initial URL.** Confirmed live
  with a local test server that a URL passing `_is_safe_url` could `302` to an unvalidated
  address (e.g. the cloud metadata endpoint) and the old code fetched it anyway, since the check
  only ran once, before the request. `_prefetch_url_to_temp` now uses a custom redirect handler
  that re-checks every hop; the response body is also streamed and capped at 200MB instead of
  read in one unbounded call. See `SECURITY.md` for the full writeup.
- **Chat history persistence is now opt-in, default off.** Previously always written into the
  active project's `.qgz` file with no way to turn it off -- a project file is shared/emailed/
  committed, so this risked carrying sensitive conversation content (humanitarian incident/
  security details) along with the map silently. New "Save chat history in the project file"
  checkbox in Settings.
- `SECURITY.md` now documents `execute_pyqgis_script`'s residual file-I/O capability (the
  objects it's allowed to use -- `QgsProject`, `QgsVectorLayer`, etc. -- can themselves read/
  write files) as an accepted, explicit limitation rather than leaving the sandbox description
  implying total containment.

### Fixed
- **The false-success narrative backstop only checked the LAST tool call in a turn.** Verified
  live that this missed the actual common shape of the bug: an earlier call fails, the model
  recovers with a different tool, and the final answer never mentions the earlier failure at
  all. Now scans every call in the turn; a failure is only treated as resolved if a *later* call
  to that same tool name succeeded, so a plain retry-then-success still doesn't produce a
  spurious warning.
- `EMPTY_RESPONSE_FALLBACK` no longer claims `"Task completed successfully!"` when the model
  returns nothing -- that asserted success with zero evidence. Now a neutral statement of fact.
- **Stop button was a silent no-op outside a real QGIS process** (the non-QgsTask fallback
  thread path): `run_agent_task` returned a bare `threading.Thread`, which has no `.cancel()`,
  so clicking Stop did nothing there (caught by the UI's own try/except, not a crash, but real
  missing functionality). The fallback path now returns a handle with a working
  `.cancel()`/`isCanceled()` pair, threaded through to `agent.run()`'s `should_stop`.
- `AgentQgsTask.run()` could leave a status callback bound to a (possibly about-to-be-discarded)
  task object if `agent.run()` raised -- the reset ran only on the success path, inside the
  `try`. Moved to a `finally` so it always runs.
- Four `urllib.request.urlopen()` calls (HDX/Overpass search in `humanitarian_tools.py`, STAC
  search in `multimodal_remote_sensing.py`, Nominatim geocoding in `system_tools.py`) had no
  timeout, unlike every `requests.get`/`post` call in the provider modules, which all set one.
  These hit fixed domains rather than attacker-controlled URLs and run on a background thread,
  so it was a reliability/hang risk rather than a security hole -- fixed with `timeout=15`
  (`timeout=30` for the Overpass call, since its own query already requests a 25s server-side
  budget via `[timeout:25]`, and a shorter client timeout would abort legitimate slow-but-valid
  queries before the server's own deadline).
- `ui/dock_widget.py`: two bare/broad `except: pass` blocks around refreshing the agent after a
  provider switch or a Settings save silently swallowed real failures (e.g. a bad provider
  config right after save) with no way to tell from the UI. Now logged with the same
  `[DockWidget] ... failed: {e}` prefix used by every other error path in this file.

### Infrastructure
- **New `build_cartogen_ai.py`**: regenerates the `Cartogen AI/cartogen_ai/` copy from this
  tree's own source as a deterministic build step, replacing the ad-hoc, hand-written mirror
  script written fresh each round this project used before. That manual process already
  produced a real bug earlier in this same project's history (a newly added test referencing the
  root tree's class name got copied verbatim into the second tree instead of translated, since
  that round's one-off script's file lists didn't route it through translation). Verified with a
  `--check` dry-run and line-by-line diff review before applying -- also surfaced and fixed two
  pre-existing, independent inconsistencies between the trees (a stale "QGIS AI Agent" product
  name in three root files the copy had already fixed ahead of root; a broken absolute-path
  license link in the copy). Run it before `python plugin_upload.py` whenever the root tree
  changes.
- **Stopped tracking the built release zips in git** (`qgis_ai_assistant.zip`,
  `Cartogen AI/cartogen_ai/cartogen_ai.zip`) -- both are fully regenerable from already-tracked
  source via `plugin_upload.py`, so committing them just added binary diffs to `.git` on every
  rebuild. Kept on disk, just untracked; attach release builds to GitHub Releases instead.

### Added
- **Live per-tool-call step indicators in chat**: previously a multi-tool-call turn showed
  nothing in the chat panel until the final answer landed -- the Task Manager tab only updates
  for formal multi-step plans (`create_plan`/`update_task`), so a simple one-shot request (e.g.
  "buffer this layer by 500m") gave zero visible progress while the agent worked. `agent.run()`
  now accepts a `tool_step_callback` invoked around every tool execution (`running` -> `done`/
  `failed`), threaded through `AgentQgsTask`/`run_agent_task` across the QgsTask and fallback-
  thread paths, and rendered as small inline "Using X" / "Used X" / "Failed: X" lines in the chat
  browser -- the "steps of processing" visibility modern AI chat apps show while working.
- **Theme-adaptive QSS styling across the whole UI** (`build_dock_stylesheet`, pure-Python and
  unit-tested): buttons, tabs, inputs, combo boxes, progress bars, group boxes, and list widgets
  in the main dock now share one QSS sheet built from QGIS's live `QApplication` palette (base,
  window, highlight, text) instead of a mix of default Qt chrome and scattered inline
  `setStyleSheet()` calls -- adapts automatically to light/dark QGIS themes, same principle
  already used for chat bubble colors. Button variants (secondary/danger/success/chip/icon) added
  via `objectName` selectors so buttons read at a glance (Clear = danger, Confirm = success)
  without duplicating the whole stylesheet per variant.
- **Settings dialog redesign**: replaced the old layout -- every provider's API key and model
  fields always present in one long form, just greyed out for the unselected providers -- with a
  `QStackedWidget` showing only the selected provider's fields, one focused page instead of a
  wall of disabled rows. Same theme-adaptive QSS applied. All existing behavior (model-list
  fetching, cached model lists, credential save/load, plaintext-fallback warning) is unchanged.

### Removed
- **Dropped Groq, Cerebras, and DeepSeek provider support.** These were free/low-value API tiers
  not viable to build a resellable service around; OpenRouter (which already re-exposes many of
  the same underlying models through one paid-or-free gateway), Gemini, OpenAI, Claude, and local
  Ollama remain the five supported providers. Removed the three provider client modules, their
  entries in `PROVIDERS`/`PROVIDER_CHOICES`/`LEGACY_SETTINGS_KEYS`, their `elif` branches in
  `agent.py`'s provider dispatch, and their tests. Existing installs with a saved Groq/Cerebras/
  DeepSeek key simply fall back to the provider picker's default on next open; no migration
  needed since those keys were never a paid/durable commitment.

---

Humanitarian-operations improvement pass, from a gap audit against four areas: Excel/Word/CSV/PDF
analysis & visualization, humanitarian aid fund gaps, humanitarian logistics, and humanitarian
security; followed by an ArcGIS/Esri feature-parity pass. Tool count: 100 -> 116.

### Added
- **Statistical charting** (`generate_chart`): bar/pie/line charts from labeled data via
  matplotlib -- previously the plugin could only produce map images, with no way to express
  non-spatial comparisons (funding by cluster, incidents over time). The single highest-leverage
  gap identified in the audit, since it benefits the other three areas below too.
- **Real PDF/Word table extraction** (`extract_pdf_tables` via pdfplumber, `extract_word_tables`):
  the existing chat-attachment preview only ever did plain-text extraction for PDFs and flattened
  Word tables into a text blob -- neither was usable for real analysis. These return actual
  structured rows/columns, verified against real generated PDF/Word files with tables, not just
  unit-tested against mocks.
- **`aggregate_data`**: pure-Python groupby (sum/count/mean/min/max) over structured rows, e.g.
  "total incidents by district" or "average funding by cluster" -- feeds directly from
  extract_pdf_tables/extract_word_tables output, verified end-to-end as a real extract-then-
  aggregate pipeline.
- **`fetch_fts_funding_data`**: OCHA Financial Tracking Service integration -- requirements,
  funding received, coverage %, and the funding gap for a country's response plan. Auto-selects
  the most recent plan (and says so) when year/plan_id are omitted; returns a candidate list
  instead of guessing when multiple plans match (a country can run several concurrent plans in
  one year, e.g. a regional migrant response alongside the main HRP). The exact API response
  shape was verified live against the real FTS API for two different plans -- the field originally
  assumed to hold the funding total was missing for a very recent plan, and a simpler, more
  reliable field (`incoming.fundingTotal`) was used instead after cross-checking both.
- **Humanitarian logistics tools** (`agent/tools/logistics_tools.py`, new module):
  `optimal_hub_siting` ranks candidate warehouse/facility locations by average distance to demand
  points; `calculate_service_area` computes road-network-based reachable area around a facility
  within a travel distance/time; `travel_time_matrix` computes road-network shortest-path
  distances between origin and destination points. The latter two rely on QGIS's native Network
  Analysis processing algorithms, which -- unlike the rest of this codebase's `processing.run()`
  calls -- could not be verified live (no real QGIS install in this dev environment); treat their
  exact parameters as best-effort pending confirmation in a real QGIS session.
- **Security/incident classification**: `add_incident_point`/`add_point_layer` now accept an
  optional `severity`/`category` field (free text) so `apply_categorized_style` can later
  distinguish incident types on the map instead of every point looking identical.
- **`hotspot_analysis`**: real kernel density estimation (a statistical raster you can run
  `zonal_statistics` against or feed into `weighted_overlay_analysis`), distinct from the existing
  `apply_heatmap_style`, which only changes how a layer looks on screen and produces no reusable
  data.
- New prompt rules: funding data from FTS is a live snapshot, not a settled fact (state it as
  such); prefer `generate_chart`/`aggregate_data` over manual prose tallying for document-derived
  comparisons; a plain-language map from common logistics/security phrasing ("what area can this
  warehouse reach", "best hub location", "nearest threat to each site") to the specific tool that
  already covers it, since several of these requests were previously only reachable if the model
  happened to think of the right existing tool.

**ArcGIS/Esri feature-parity pass** (tool count: 109 -> 116), from a gap audit comparing this
plugin (bounded by QGIS's own capabilities) against ArcGIS/Esri, split into what's directly
buildable on QGIS vs. what needs open-data equivalents of Esri's proprietary offerings:
- **`interpolate_surface`**: IDW/TIN spatial interpolation from scattered point values (e.g.
  rainfall/elevation between sample points) -- an approximation of ArcGIS's Geostatistical
  Analyst extension, not a true kriging model with confidence bounds.
- **`elevation_profile`**: samples a DEM along a line for a distance/elevation profile (ArcGIS 3D
  Analyst's profile tool) -- feeds directly into `generate_chart` for a real profile chart. Uses
  only core `QgsGeometry`/raster-sampling APIs, no processing algorithm needed, lowest-risk tool
  in this pass.
- **`georeference_image`**: georeferences a scanned map/image from control points (ArcGIS's
  Georeferencer), via GDAL's GCP + Warp API directly rather than guessing `processing.run()`
  parameter names -- more reliable than the network-analysis tools below, but still unverified
  live (this dev environment has no C++ toolchain to build GDAL's Python bindings for testing).
- **`location_allocation`**: chooses the best COMBINATION of *k* facility locations to minimize
  total distance to demand points (ArcGIS Network Analyst's location-allocation solver), via a
  standard greedy p-median heuristic. A genuine capability upgrade over `optimal_hub_siting` (which
  ranks candidates independently and double-counts overlapping coverage) -- verified by hand
  against a symmetric 4-corner scenario with provably tied-optimal candidate pairs.
- **`optimize_delivery_route`**: finds a good visiting order for delivery/distribution stops
  (a simplified ArcGIS VRP solver) via nearest-neighbor construction + 2-opt refinement --
  verified by hand: correctly untangles a deliberately crossed 4-point square into the true
  optimal 3-side tour.
- **`fetch_worldpop_population`** + **`estimate_population_exposure`**: downloads a country's open
  WorldPop population raster and sums population within polygons (`QgsZonalStatistics` with the
  `Sum` statistic) -- an open-data approximation of ArcGIS Business Analyst's core "how many
  people live here" use case. WorldPop rasters are large (100MB-1GB+, confirmed live against the
  real API) so this follows the existing two-phase pattern (network download off the main thread)
  -- but unlike `fetch_geoboundaries`, the downloaded file is deliberately never deleted after
  loading, since a raster layer reads its backing file lazily/on demand rather than fully into
  memory; deleting it would have silently broken the layer the next time something sampled it.

## [1.0.1] — 2026-08-13

### Fixed
- Chat-attachment CSV preview crashed on non-UTF-8 files (`'utf-8' codec can't decode
  byte 0x92...`), a common failure on Excel-exported CSVs that use cp1252 smart quotes/
  em dashes. Now tries `utf-8-sig` -> `cp1252` -> `latin-1` in order instead of failing
  outright. Only affected the chat preview text; `load_tabular_data_as_layer` (the real
  full-file load) goes through QGIS's own OGR/GDAL CSV driver and was unaffected.
- Overlapping layers (e.g. point markers under a boundary/area polygon) rendered as a
  "messy" solid stack that didn't match what the legend implied, because every styling
  tool used fully-opaque default symbols and newly added layers always land on top of
  the layer stack -- a polygon added after point markers would completely bury them.
  `apply_categorized_style`/`apply_graduated_style` now default polygon fills to 75%
  opacity (configurable via a new `opacity` parameter); three new tools give direct
  control: `set_layer_transparency` (per-layer opacity), `auto_arrange_layer_order`
  (reorders layers by geometry type so points/lines stay on top of polygons/rasters),
  and `set_layer_order` (explicit stacking order). New prompt rule instructs the model
  to consider layer composition as a whole -- not style each layer in isolation -- when
  a task involves more than one overlapping layer. Tool count: 84 -> 87.

### Added
- QGIS feature-coverage pass, from a gap audit against QGIS's own processing toolbox
  (see the audit for full reasoning): `difference_layers` (A minus B / symmetric
  difference -- intersect and union existed, difference didn't), `convex_hull`,
  `voronoi_polygons`, `delaunay_triangulation`, `find_nearest_features` (nearest-
  feature join with distance, e.g. "nearest hospital to each village"),
  `convert_to_singlepart`, `simplify_geometry`, `field_statistics` (project-wide
  count/sum/mean/median/min/max/stdev/range for a numeric field -- zonal_statistics
  only covered the per-zone case), `select_by_location` (with new/add/remove/
  intersect selection-set combination) and `invert_selection`, `weighted_overlay_analysis`
  (combine multiple normalized rasters into one weighted suitability/risk surface, e.g.
  "best sites for a new clinic"), and `save_project`/`load_project` (the agent could
  previously only ever touch the currently open project, with no way to checkpoint or
  switch). All follow the same `native:`/`gdal:` processing-algorithm pattern already
  used by the existing overlay tools, or the same PREVIEW_REQUIRED destructive-
  confirmation gate as `remove_layer` where relevant (`load_project`). Tool count:
  87 -> 100.

### Fixed (2026-08-12, second pass)
- **`load_tabular_data_as_layer` silently failed to map Excel spreadsheets with lat/lon
  columns**, root-caused from a live user report ("excel sheet was not analyzed
  correctly, visualization on the map was completely wrong"). Two compounding bugs:
  geometry-column auto-detection was gated to `ext == ".csv"` only, so an .xlsx/.xls
  file was never even checked for coordinate columns; and when `x_field`/`y_field` were
  passed explicitly for an Excel file anyway, the code unconditionally routed through
  QGIS's `delimitedtext` (plain-text CSV) provider, which cannot correctly parse an
  Excel binary file. Net effect: Excel geometry data always loaded as a non-spatial
  table (or failed outright), contradicting the tool's own docstring, which likely led
  the agent to improvise -- e.g. hand-transcribing points from the chat's 5-row preview
  instead of a real spatial load, matching the reported "completely wrong" map. Fixed by
  extending auto-detection to Excel (`_sniff_excel_header`) and adding a real Excel
  geometry path (`_load_excel_as_geometry_layer`) that reads the sheet via pandas and
  builds an in-memory point/WKT layer directly, instead of forcing Excel through a
  CSV-only provider.
- Added a coordinate-range sanity check (`_validate_wgs84_coordinates`) that samples
  x_field/y_field values before building any layer (CSV or Excel) and rejects the call
  with a clear error if most sampled values fall outside valid WGS84 lon/lat ranges --
  catches swapped lat/lon columns or a wrong-field pick (e.g. projected UTM meters
  mistaken for degrees) that would otherwise silently produce a layer with no error and
  every point in the wrong place. Confirmed live against a synthetic UTM-as-WGS84 case.
- Found and fixed a second, unrelated bug while testing the fix above:
  `_qvariant_type_for_dtype`'s attribute-type inference used raw `np.issubdtype()`,
  which raises `TypeError` on pandas' newer extension dtypes (e.g. the Arrow-backed
  nullable string dtype) since they aren't plain numpy dtypes. Switched to pandas' own
  `pd.api.types.is_*_dtype` predicates, which handle both correctly.

## [1.0.0-beta] — 2026-08-11

First internal/commercial release candidate. GNU GPL v2 (see [LICENSE](LICENSE)) —
not distributed via the public QGIS plugin repository; monetization plans are
services-based (support, hosting, custom integration) rather than code licensing.

### Chat UX, response quality, prediction, and visualization (user feedback round)
- Chat bubbles now derive their colors from QGIS's actual live theme (`ui/chat_formatting.py`,
  new module) instead of hardcoded light-theme colors that looked wrong in dark mode; added
  role badges, per-message timestamps, and a real markdown renderer upgrade (GFM tables,
  blockquotes, strikethrough, nested lists) so structured answers actually render as such.
- New system prompt rules: structure final answers with headers/lists/tables instead of a wall
  of prose; fill unstated cartographic/analytical parameters with sensible defaults and say so,
  instead of failing or demanding every detail up front; self-check any styling result against
  basic cartographic conventions before presenting it as finished.
- New `forecast_trend` tool (`agent/tools/analysis_tools.py`): pure-Python linear-regression
  trend projection over historical numeric attribute data, with a stated fit confidence and an
  explicit prompt rule that it must always be presented as a projection, never a certain fact
  (extends rule 12's "never invent real-world facts" to predictions specifically). Spatial
  risk/hotspot scoring is a deferred second phase, not built in this pass.
- New `apply_graduated_symbol_style` tool: distribution-aware proportional-circle sizing for
  point layers, reusing the same skewness-based classification logic as the existing choropleth
  tool (factored into a shared `_classify_values` helper) — closes the gap where the model was
  hand-writing ~40 lines of `QgsGraduatedSymbolRenderer` code from scratch for exactly this map
  type, confirmed directly in this session's own live QGIS logs. Also fixed
  `apply_categorized_style` using a diverging ramp ("Spectral") on unordered/nominal categories,
  where a diverging ramp is the wrong tool — switched to a qualitative ColorBrewer ramp.

### Security
- **Critical**: hardened the `execute_pyqgis_script` sandbox after an adversarial
  testing pass found four confirmed, live-exploitable bypasses — `import builtins`
  gave a direct reference to the real (unrestricted) builtins module bypassing the
  restricted execution environment entirely (verified with a real arbitrary file
  read); `"{0.__class__}".format(x)`-style attribute traversal reached dunder
  attributes invisibly to AST-based checks; `gc.get_objects()` and `inspect`
  frame-walking could locate already-imported dangerous modules without importing
  them directly. All four fixed; see [SECURITY.md](SECURITY.md) for the full
  before/after testing table.
- **Critical, found in live production use** (not synthetic testing): a real agent
  session used `QDirIterator` from `qgis.PyQt.QtCore` to browse the filesystem well
  outside the QGIS install. Qt's own file/process/network classes (`QFile`, `QDir`,
  `QProcess`, `QNetworkAccessManager`, `QSettings`, `QLibrary`, `QPluginLoader`,
  `QDesktopServices`, and others) completely bypassed the Python-module-based
  blocklist, since the module they live in (`qgis.PyQt.QtCore`/`QtNetwork`) must stay
  importable for normal PyQGIS work. Fixed by blocking these specific classes by name
  regardless of which allowed Qt submodule they're imported from, checked at the
  import statement itself so `from qgis.PyQt.QtCore import QFile as F` can't dodge it
  by aliasing.
- Expanded the `execute_pyqgis_script` blocked-module list (urllib, requests,
  pickle, base64, sqlite3, and more), closed the `x = eval; x(...)` aliasing bypass
  and the `().__class__.__bases__[0].__subclasses__()` dunder-escape chain, and
  added a restricted-builtins allowlist as defense in depth for `exec()`.
- `execute_read_only_sql` now fails **closed** (refuses the query) instead of open
  if database-level read-only enforcement can't be confirmed; blocks stacked
  (`;`-separated) statements; and blocks `lo_export`/`pg_read_file`/`dblink` and
  related PostgreSQL functions that can read server-side files or run SQL against a
  different server from a plain `SELECT` — none of which the DML/DDL keyword
  blocklist or the read-only-transaction setting caught on their own.
- Added an SSRF guard rejecting loopback/private/link-local/metadata-endpoint
  addresses before fetching any model-supplied URL.
- Credential save now warns the user in Settings if it silently fell back to
  unencrypted storage, instead of that happening invisibly.
- Added prompt-level guidance instructing the model to treat fetched web/OSM/HDX
  content as untrusted data, never as instructions.
- Considered switching from GPL v2 to a proprietary license for commercial
  distribution, then deliberately kept GPL v2 instead — importing GPL v2 PyQGIS at
  runtime made the legal compatibility of a proprietary license a genuine open
  question not worth betting a commercial license on. Monetization is
  services-based (support, hosting, custom integration) rather than code
  licensing.

### Reliability
- **Critical**: fixed a cross-thread signal bug where every dispatcher-routed tool
  call could silently fail with "Execution failed unexpectedly" even though the
  underlying operation had actually succeeded (also explains task plans getting
  stuck mid-progress) — a `list`-typed PyQt signal parameter was being reconstructed
  as a new object across the queued connection, so a result written into it by the
  slot was invisible to the waiting caller. Fixed by switching to an `object`-typed
  parameter, which PyQt passes by reference.
- Fixed the dock panel needing two clicks to open after a fresh install — creating
  the dock already makes it visible, so the old code's visible→hide toggle check
  was closing it again immediately on first creation.
- Added a Stop button to cancel an in-progress request (cooperative — stops before
  the next tool-call iteration, not mid-flight).
- Added a code-level check that catches the agent claiming success in its final
  answer when the last tool call in that turn actually failed, instead of relying
  purely on prompt instructions.

### Added
- `load_tabular_data_as_layer`: loads the *full* contents of a CSV/Excel file as a
  real QGIS layer (not a preview), with automatic point-geometry detection for
  coordinate columns and FIELD_SUGGESTION-style fallback when detection isn't
  confident. File attachments now pass the real file path to the agent so it can
  actually act on the full data, not just a 5-row preview.
- Native web-search grounding for both Gemini (`gemini_grounded_search`) and OpenAI
  (`openai_grounded_search`), plus automatic model-fallback chains for both
  providers when a configured model is retired/renamed.
- Retry-with-backoff on every cloud provider's HTTP calls.
- Claude prompt caching (system prompt + tool schemas marked as cache breakpoints).
- Batched geocoding (`geocode_batch`) and a shared TTL cache for repeated
  geocode/OSM/HDX/geoBoundaries lookups.
- New installs now default to complexity-based automatic model selection instead of
  always using the most expensive configured model (existing explicit model choices
  are unaffected).

### Documentation
- Added this changelog, `README.md`, `SECURITY.md`, `docs/USER_GUIDE.md`, and an
  auto-generated `docs/TOOLS_REFERENCE.md` (regenerable via
  `python docs/generate_tools_reference.py`).

### Removed
- Dead `resources.qrc`/`resources/` files (unused Plugin Builder scaffolding).
- Temporary `[Agent][DIAG]` diagnostic logging added during the v0.3.1 dispatch-bug
  investigation, now that the fix is confirmed working.

## [0.3.1] — 2026-08-10

- Fixed the "Execution failed unexpectedly" dispatch bug (see 1.0.0-beta above for
  the full root-cause writeup — this is when the fix first landed).
- QGIS 4.0 (Qt6) compatibility fixes: `QgsProject.customProperty` fallback,
  `QgsAuthManager` method-name fallback, `QgsHighlight` geometry-argument fix,
  alongside continued QGIS 3.x support.
- Task Manager panel revamp: progress bar, plan history browsing, retry failed
  steps, edit-and-resend, tool badges, timestamps, copy-snippet, memory
  search/filter and clear.
- A safety net that keeps the task plan from freezing on TODO when steps complete
  without an explicit status update.
- In-app Help tab.
- STAC satellite imagery query caching and a per-session quota guard.
- Database-level (not just keyword-blocklist) read-only SQL enforcement.
- Multi-layer attribute join assistant with fuzzy field matching and cardinality
  warnings.
- Bulk point-layer creation and single incident-point plotting tools with
  consistent professional styling.
- Fixed the dock panel's tab sizing forcing the QGIS window taller than the screen.

## [0.3.0]

- QGIS 4.0 compatibility groundwork.

## [0.2.0]

- Multi-provider support (OpenRouter, Gemini, OpenAI, Claude, DeepSeek, Groq,
  Cerebras, Ollama) with dynamic async model fetching and complexity-based
  auto-routing.
- Proactive map context injection, persistent project-bound chat history, canvas
  layer highlighting, quick suggestion chips.
- AST safety sandbox for PyQGIS script execution (first version — see 1.0.0-beta
  above for the hardening pass that closed several bypasses found in it).
- Network-tool UI thread bypass, qpip dependency management.

## [0.1.2]

- First published release (single-provider, smaller tool set).
