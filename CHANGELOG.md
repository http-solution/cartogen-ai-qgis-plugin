# Changelog

**[1.3.0] and earlier moved to `CHANGELOG_ARCHIVE.md`** in the 2026-08-31 documentation pass -- this file had grown to 2,146 lines covering every version since `[0.1.2]`, most of it from the very early, rapid `[1.2.x]` patch cycle. The split point is `[1.4.0]`, this project's own documented milestone (the dual-tree-to-single-tree consolidation --
see the `[1.4.0]` entry below and `CONTRIBUTING.md`). Entries were relocated verbatim, not rewritten, per this project's convention that past changelog entries are a historical record (`CONTRIBUTING.md` §2) -- only the file they live in changed.


## [1.7.0] — Security & Logistics: GDPR export, undo/rollback, sandbox Tier 2, network-aware routing

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

