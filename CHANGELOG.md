# Changelog

**[1.3.0] and earlier moved to `CHANGELOG_ARCHIVE.md`** in the 2026-08-31 documentation pass -- this file had grown to 2,146 lines covering every version since `[0.1.2]`, most of it from the very early, rapid `[1.2.x]` patch cycle. The split point is `[1.4.0]`, this project's own documented milestone (the dual-tree-to-single-tree consolidation --
see the `[1.4.0]` entry below and `CONTRIBUTING.md`). Entries were relocated verbatim, not rewritten, per this project's convention that past changelog entries are a historical record (`CONTRIBUTING.md` §2) -- only the file they live in changed.

**Recent releases at a glance:**

| Version | Date | Summary |
|---|---|---|
| [1.9.0](#v1-9-0) | 2026-09-12 | Live Hazard Monitoring: NASA FIRMS/EONET + GDACS tools, dashboard freshness badges |
| [1.8.3](#v1-8-3) | 2026-09-12 | Patch: release zip was silently missing 4 relocated archive docs |
| [1.8.2](#v1-8-2) | 2026-09-12 | Docs-only: repo reorganization and documentation polish pass |
| [1.8.1](#v1-8-1) | 2026-09-12 | Patch: dashboard OSM-blocked basemap + canvas not following new layers |
| [1.8.0](#v1-8-0) | 2026-09-12 | Cartographic Intelligence: visualization selection, real QA gate, isochrone bands |
| [1.7.1](#v1-7-1) | 2026-09-11 | Patch: portrait print-layout body/footer overlap fixed |
| [1.7.0](#v1-7-0) | 2026-09-11 | Security & Logistics: GDPR export, undo/rollback, sandbox Tier 2, network-aware routing |

The detailed narrative entries below are unchanged -- this table is purely an additive index on
top of them.

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

