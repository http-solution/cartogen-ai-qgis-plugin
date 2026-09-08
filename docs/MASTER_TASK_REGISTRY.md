# Cartogen AI — Master Task Registry

Single-source-of-truth control tower for the Cartogen AI QGIS plugin (this repo:
`cartogenai-glitch/CARTOGEN-AI`, commercial/private channel). Created 2026-09-02 at
Baron's request to replace scattered chat-based status updates with one structured,
git-versioned registry, organized into exactly three levels:

1. **Release Management** — what version we're on, what's shipped, what's blocked.
2. **Active Queue** — the one thing being worked on right now, plus an ordered list of
   what's next. **This queue must never be empty.** If every real item is done, it gets
   a standing maintenance item (see the last line of the queue) rather than being left
   blank — an empty queue means this document stopped being maintained, not that there's
   nothing left to do.
3. **Full Log** — the complete historical record: every bug found, every feature shipped,
   every version-control milestone, cross-referenced to the underlying files that hold
   the raw detail (`CHANGELOG.md`, `docs/BUG_TRACKER.md`, `docs/OPERATIONS_LOG.md`, git
   history). This document does not duplicate those files' full text — it indexes them
   so "where are we, and how did we get here" has one starting point.

**Maintenance rule (Hermes Charter Rule 5):** update this file after every work slice —
move the finished Current Task into the Full Log, promote the next queue item, and add
anything new discovered. Never git-commit changes to this file (or anything else) without
Baron's explicit instruction — see Release Management's governance note.

---

## LEVEL 1 — RELEASE MANAGEMENT

### Current state (as of 2026-09-05)

| | |
|---|---|
| Source tree version (`metadata.txt`/`pyproject.toml`) | **1.6.0** |
| Last built release ZIP | `dist/cartogen_ai_v1.6.0.zip` (913,855 bytes, SHA-256 `378897b1829f136a2254c8240db49b241dccd14806e165ab677962db8118a8f4`) |
| Last local commit | `e042eeb` — "chore(release): cut v1.6.0" |
| Last tag | `commercial-plugin-v1.6.0` (annotated, on `e042eeb`) |
| Pushed to GitHub? | **Yes** — working GitHub auth was available this session (unlike every prior session's documented credential blocker); `main` and the tag both pushed clean. |
| GitHub Release object created? | **Yes** — [commercial-plugin-v1.6.0](https://github.com/cartogenai-glitch/CARTOGEN-AI/releases/tag/commercial-plugin-v1.6.0), zip attached, created via a portably-downloaded `gh` CLI authenticated through git's own existing credential (no admin rights needed/used, no token ever displayed). |
| Working tree clean otherwise? | Yes. |

### Prior state (2026-09-02, superseded above — kept per this file's no-silent-rewrite convention)

| | |
|---|---|
| Source tree version | 1.5.0 |
| Last built release ZIP | `dist/cartogen_ai_v1.5.0.zip` (693,475 bytes, SHA-256 `de087c39d817f0d7ab8fb146cf8dcd7cb3ca9ed3a33bf63a0508d8ec8db6cdd9`) — delivered to Baron in-session |
| Last local commit | `eee84eb` on top of `2624313` on top of the `cd7d06a` v1.5.0 release commit |
| Last local tag | `commercial-plugin-v1.5.0` (on `cd7d06a`) |
| Pushed to GitHub? | No — blocked, no GitHub credentials configured in that session, no `gh` CLI installed. |
| GitHub Release object created? | No — same blocker. |
| Working tree clean otherwise? | No — pre-existing uncommitted "account" feature work (since reconciled and shipped — see the 2026-09-05 update above and in Level 2). |

### Release channels (per `docs/RELEASE_GOVERNANCE.md`)

- **Commercial/private** — `cartogenai-glitch/CARTOGEN-AI` (**this repo**). Confirmed private via the GitHub API (unauthenticated lookup → HTTP 404). May contain managed-gateway, org, deployment, support, and commercial-operations code.
- **Community/public** — `cartogenai-glitch/cartogen_ai_community`. Confirmed public via the GitHub API (`private: false`). Community-safe core only — never a copy of private code. Not touched this session (no clone, no explicit instruction).

### Governing process

Full rules live in `docs/RELEASE_GOVERNANCE.md` (semantic versioning, the 4-file version-sync
requirement, the 9 required gates, public/private sync rules, business-model guardrails).
This registry doesn't restate them — it tracks *compliance* with them for the current cycle:

| Gate (`RELEASE_GOVERNANCE.md`) | v1.5.0 status |
|---|---|
| 1. Identify affected channel | Done — Commercial only |
| 2-3. Tests added/updated, suite run | Done — 17 new tests (`tests/test_learning.py`), full suite re-verified (718 tests, 1 known sandbox failure, 0 new failures) |
| 4. Compilation/packaging checks | Done — `py_compile` clean, ZIP rebuilt and hashed |
| 5. Security notes | N/A this cycle — no trust-boundary/credential change |
| 6. Update changelog | Done — `CHANGELOG.md` `[1.5.0]` entry |
| 7. Build and audit release artifact | Done — see ZIP above |
| 8. Tag + GitHub release | **Blocked** — tag created locally, not pushed; no GitHub Release object yet |
| 9. Record in `docs/OPERATIONS_LOG.md` | Done — "Adaptive self-learning system (v1.5.0)" entry, including an explicit scope/exclusion note |

**Governance note:** every commit and tag above was made only after Baron's explicit
"update the documentation, githubsite, and follow the version control for the releases"
instruction (Hermes Charter Rule 8 — never commit without explicit instruction). That
authorization is consumed for that specific batch; anything new (e.g. a fabrication-safety
fix, see Level 2) needs a fresh explicit go-ahead before it's committed, even though it can
be implemented and tested in the working tree first.

### Full version history

Full text for every entry below lives in `CHANGELOG.md` (this table is the index, not a
replacement). Versions above the line are this repo's plugin releases; versions across the
`v0.2.x`/`v0.3.x` gap in dates were commercial-service-side work tracked in the same file.

| Version | Date | Highlight |
|---|---|---|
| **1.6.0** | 2026-09-05 | QA-gate/dataset-status infrastructure, GDPR remediation, task-register end-to-end wiring, generalized Qt6 enum compat; live-verified against real QGIS 4.2.2 for the first time (critical `raster_tools.py` import-crash fix, confirmed print-layout disclaimer footer). Pushed to GitHub + Release created. |
| 1.5.0 | 2026-09-02 | Adaptive self-learning system (4 mechanisms) + retroactively documents the QGIS 4.2/Qt6 fixes shipped under 1.4.4 without a version bump |
| 1.4.4 | 2026-09-02 | Sector-guided mapping experience (source tree bump; carries the live-discovered Qt6 enum fixes, dark-theme chat fix, rules 40/41 — see Bug Log) |
| 1.4.3 | 2026-08-22 | UI terminology and navigation polish |
| 1.4.2 | 2026-08-22 | `dock_widget.py` class split into per-tab widgets |
| 1.4.1 | 2026-08-21 | Namespace-package restructure (fixed the `cartogen_ai.py`/`cartogen_ai.core` collision — BUG-2026-08-21-6/-7) |
| 1.4.0 | 2026-08-21 | Breaking change: QSettings key prefix migration |
| 1.3.0 | 2026-08-21 | (see CHANGELOG for detail) |
| 1.2.34 | 2026-08-21 | Docs-only bump (`BUG_TRACKER.md`/`IMPLEMENTATION_TRACKER.md` created) — never repackaged into its own ZIP |
| 1.2.33 | 2026-08-21 | `route_optimization_prototype.py` bbox-order + missing-dependency fixes (BUG-2026-08-21-1/-2) |
| 1.2.32 | 2026-08-21 | Humanitarian Data example-prompt fix |
| 1.2.31 | 2026-08-21 | Extracted `_read_attached_file()` (PDF/DOCX/CSV/XLSX/image ingestion) |
| 1.2.30 | 2026-08-21 | Never fabricate token usage as zero when a provider omits it |
| 1.2.29 | 2026-08-21 | `calculate_area`/`calculate_length` confirm-gate consistency fix (BUG-2026-08-21-3) |
| 1.2.28 | 2026-08-21 | Gemini header-auth fix (BUG-2026-08-21-4) |
| 1.2.27 | 2026-08-20 | Ollama retry-gap fix |
| 1.2.26 | 2026-08-20 | (see CHANGELOG) |
| 1.2.25 | 2026-08-20 | `apply_raster_stretch` added |
| 1.2.24 | 2026-08-20 | Licensing-note addition to tier-restructure proposal |
| 1.2.23 | 2026-08-20 | Enterprise tier confirmed (business/planning, no code) |
| 1.2.22 | 2026-08-20 | Planning/business round, no agent/ui/tests changes |
| 1.2.21 | 2026-08-20 | (see CHANGELOG) |
| 1.2.20 | 2026-08-20 | Rule 38 correction (`calculate_presence_gap`) |
| 1.2.19 | 2026-08-20 | `score_route_incident_risk` buffer-layer styling |
| 1.2.18 | 2026-08-20 | JIAF multisector composite spec |
| 1.2.17 | 2026-08-20 | `analyze_incident_trend` built |
| 1.2.16 | 2026-08-20 | `analyze_incident_trend` proposed |
| 1.2.15 | 2026-08-20 | Route-analysis strategy doc |
| 1.2.14 | 2026-08-17 | (see CHANGELOG) |
| 1.2.13 | 2026-08-17 | (see CHANGELOG) |
| 1.2.12 | 2026-08-17 | `agent/tools/imagery_extraction.py` added |
| 1.2.11 | 2026-08-17 | (see CHANGELOG) |
| 1.2.10 | 2026-08-17 | (see CHANGELOG) |
| 1.2.9 | 2026-08-17 | (see CHANGELOG) |
| 1.2.8 | 2026-08-17 | (see CHANGELOG) |
| 1.2.7 | 2026-08-17 | (see CHANGELOG) |
| 1.2.6 | 2026-08-17 | `agent/scheduler.py` `WorkflowScheduler.start()` fix |
| 1.2.5 | 2026-08-16 | Rules 12/20/23/32 anti-fabrication consolidation |
| 1.2.4 | 2026-08-16 | (see CHANGELOG) |
| 1.2.3 | 2026-08-16 | (see CHANGELOG) |
| 1.2.2 | 2026-08-16 | `WorkflowScheduler` singleton added |
| 1.2.1 | 2026-08-16 | `agent/prompt_refiner.py` added |
| 1.2.0 | 2026-08-14 | (see CHANGELOG — large entry) |
| 1.1.0 | 2026-08-13 | SSRF guard re-validates every redirect hop |
| 1.0.1 | 2026-08-13 | Excel lat/lon mapping fix (`load_tabular_data_as_layer`) |
| 1.0.0-beta | 2026-08-11 | `execute_pyqgis_script` sandbox hardened against adversarial input |
| 0.3.1 | 2026-08-10 | (see CHANGELOG) |
| 0.3.0 / 0.2.0 / 0.1.2 | pre-2026-08-10 | Early prototype phase — see `CHANGELOG.md` for detail |

**Tag history (`git tag`):** `commercial-plugin-v1.5.0` (2026-09-02, local only — see push
blocker above), `commercial-plugin-v1.4.4`, `commercial-plugin-v1.4.3` (both 2026-08-23,
pushed with real GitHub Release objects — see `docs/OPERATIONS_LOG.md`), `commercial-v0.2.0`
through `commercial-v0.2.8` (2026-08-23, commercial-service-side tags, same repo history).

---

## LEVEL 2 — ACTIVE QUEUE

**Rule: this section is never empty.** The current task is always exactly one item. The
next-steps queue always has at least one item — if everything concrete is done, item
"Z — standing maintenance" below stays in as the permanent last slot.

### Current task

> **2026-09-04, Obsidian-memory session.** Baron confirmed this repo (`cartogen-ai`) as the
> canonical QGIS plugin checkout — the parallel `cartogen-ai-community`/
> `cartogen-ai-community-limited` checkouts and the web platform are explicitly out of scope
> going forward. Ran a full incomplete/mockup-code audit against the live source tree (not
> against this registry's own prior claims) at Baron's request; result: very little is actual
> mockup, most incompleteness is already honestly disclosed in code comments. One genuinely new
> finding surfaced — see queue item 6 below, promoted from being buried inside
> BUG-2026-09-02-3's text into its own explicit decision point. Full audit record lives in the
> paired Obsidian vault (`CARTOGEN AI QGIS Plugin/02_BUGS/INCOMPLETE_AND_MOCKUP_CODE_AUDIT.md`),
> not duplicated here in full — this registry stays the code-side index, Obsidian holds the
> narrative.
>
> Superseded, not deleted (Charter's no-silent-rewrite convention): the two open issues from the
> 2026-09-02 "bullshit not real" report (BUG-2026-09-02-6, -7) are still fixed-in-working-tree,
> still uncommitted, still queue item 1 below — unchanged by this update.
>
> **Update, same day, later:** implemented both queue items 2 and 3 (road-snapped route
> upgrade, dual ACLED/IMSMA-style incident coding) — see Level 3b. Full suite 748/0/0/1.
> Neither is committed yet; both need Baron's explicit go-ahead like everything else in this
> registry.
>
> **Update, same day, further later — Baron: "work on task 8":** resolved queue item 7 (the
> ~15-site unscoped-QGIS-enum risk, TASK-0008 in the Obsidian board's numbering) with a
> runtime dual-form resolver rather than picking between the two originally-offered options —
> see BUG-2026-09-04-1 and Level 3b. Full suite 753/0/0/1. Also uncommitted.
>
> **Update, same day, later still — cross-session (Obsidian-vault cross-check + GDPR fix):** re-verified the two `fixed-unverified-pending-retest` QGIS 4.2 crashes (BUG-2026-09-02-2/-3) live: dock-panel-open (`Qt.RightDockWidgetArea`) confirmed fixed in a real QGIS 4.2.2 install (v1.5.0 zip, dock rendered with all 3 tabs, no crash); `QScrollArea.NoFrame` still unverified, pending Baron being back at the machine. Separately, closed GDPR review finding F1 (global memory had no bulk erasure path) directly in this repo: added `MemoryManager.clear_global_notes()` + a "Clear Global Memory" UI control + 4 tests — see BUG-2026-09-04-2 and Level 3b. Committed as `eee84eb` on Baron's explicit "go ahead and commit it," scoped to exactly those 3 files. Note: F1's review document lives in `cartogen-ai-community`, not this repo — the finding and its fix are still in two diverged repos; reconciling that is a new, still-open item (see queue below).
>
> **Update, same day, further later — architecture review:** Baron supplied a 27-point "QGIS-first production standard" critique (Processing-first execution as the default over arbitrary PyQGIS, project folder architecture, QA-gate state machine, schema contracts, P-code/temporal/CRS depth, provenance sidecars, a full agent-decision-loop redesign, and more). Per Baron's own choice of next step, this was captured verbatim and gap-checked point-by-point against the live source tree (four parallel research passes, not assumed) rather than acted on directly — see `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`. Headline: of 28 items checked, 1 is already true (point 25, route-safety terminology is already correctly hedged), 4 are partial, 21 are real undiscussed gaps, and **1 (point 19, replacing the AST-sandbox security boundary with a 4-tier allow-list model) directly conflicts with a decision already made and documented in `docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md` §4** — flagged for Baron's explicit re-review rather than silently implemented over it. No code changed this slice; see queue item 10 below for what happens next.

> **Update, same day, further later — Baron: "pick the next item from the 27-point review to tackle":** picked point 9 (population exposure vs. affected) — a self-contained, single-session, humanitarian-accuracy fix with no dependency on the still-open QA-gate/dataset-status work most of the remaining items need. `estimate_population_exposure`/`population_access_gap` now return explicit `pop_exposed_est`/`gap_population_est`, `pop_source`/`pop_reference_year` (parsed honestly from `fetch_worldpop_population`'s own layer-naming convention, never guessed for other rasters), `analysis_resolution` (real pixel size/CRS), and a `confidence` string, plus both tools' descriptions now say explicitly the result is an estimate, not a verified/affected-population figure. 6 new tests, full suite 764/1/6/14, same known baseline, 0 new failures. Found in the process: this repo's working tree already carries substantial unrelated uncommitted work from outside this session (new `agent/account.py`/`ui/account_dialog.py`, `_qgis_enum_compat.py`, road-snapped routing, incident-coding fields, and more) — all of it pre-existing per Level 2 queue item 5/Level 3c below, left untouched; this slice's diff is isolated to exactly `raster_tools.py`, `logistics_tools.py`, their two test files, and this review document/registry. Not yet committed — awaiting Baron's go-ahead like everything else in this registry. **[Corrected, 2026-09-08]:** now committed as `0f2f796` (2026-09-04).

> **Update, same day, further later still — Baron: "Complete the remaining tools":** continued past point 9 without stopping for the commit decision (that stayed staged, unanswered) and picked two more self-contained, additive items from the same review, same selection logic as point 9 (no dependency on the QA-gate/dataset-status work, no new policy/format decision needed). **Point 21** (project inspector): `get_layers` now returns `crs` for every layer plus `fields`/`feature_count` for layer types that actually have them (omitted, not falsely empty, for e.g. a raster), and a new `list_layouts` tool lists existing print-layout names — Map Themes (point 16) untouched, a separate unbuilt concept. 5 new tests. **Point 13** (classification): `apply_graduated_style` gained an optional `breaks` parameter that builds `QgsRendererRange` objects directly from caller-supplied boundaries instead of auto-selected Jenks/equal-interval/quantile, for humanitarian operational-threshold maps — found and fixed a real bug during this work (a `NameError` on the cluster-color-without-breaks path, from `classification` only being computed in one of three branches) before it ever reached a test. Deliberately did **not** add a standard-deviation classification mode — that needs QGIS's newer `QgsClassificationMethod` subclass API, unverifiable in this no-real-QGIS-install dev environment, so left alone rather than guessed at. 3 new tests. Full suite 772/1/6/14, same known baseline, 0 new failures across all three items combined. All three items' diffs remain isolated from each other and from the pre-existing unrelated uncommitted work (item 5 below) via per-file blob staging where a file was shared with that unrelated work (`layout_tools.py`, `styling_tools.py`) rather than a plain `git add`.
>
> **Update, same day, further later still — Baron answered both pending questions: "Yes, commit it" (points 9/21/13) and "Start the shared infrastructure" (how far to keep going):** committed points 9, 21, and 13 as `0f2f796` — 12 files, 562 insertions(+), 49 deletions(-), the pre-existing unrelated uncommitted work (item 5 below) untouched and still uncommitted exactly as before. Then began the QA-gate/dataset-status concept points 2/4/5/6/7/17 all depend on (Baron's explicit choice from the framing "bigger, multi-file, and it commits you to a design direction for those six points") — see queue item 12 below for what got built.
>
> **Update, same day, further later still — Baron: "Yes, commit it" (point 2 first pass), then "pick one dependent point to build next":** committed point 2's first pass as `3135ff6` — 7 files, 774 insertions(+), 18 deletions(-), again leaving the pre-existing unrelated work (item 5 below) untouched. Picked point 4 (geometry QA overlaps/gaps/duplicates) as the dependent point to build, per the option framed as "e.g. start point 4's fuller geometry QA (overlaps/gaps/duplicates) now that it has a gate to plug into." `diagnose_topology` gained `duplicate_geometries` and, for polygon layers, `overlapping_feature_pairs` (real `QgsGeometry.overlaps`, bbox-prefiltered via the same `QgsSpatialIndex` pattern already used by `obfuscate_sensitive_points`), plus an optional `min_area` small-polygon threshold — and point 2's gate was updated in the same slice to actually check the two new fields, proving out rather than just asserting the "extend the check, the gate picks it up automatically" design. Gap detection and the semantic admin1/admin2 P-code topology check were deliberately left unbuilt (no reference boundary to diff gaps against; a dissolve-and-find-holes heuristic would misfire on real coastlines/voids in almost every humanitarian admin-boundary layer). 12 new tests — 8 for `diagnose_topology` itself, which had zero prior test coverage of any kind despite already being load-bearing for point 2's gate, plus 4 for the strengthened gate. Full suite 813 tests, same known baseline, 0 new failures. See queue item 12 and point 4's updated entry in `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md` for full detail.
>
> **Update, same day, further later still — Baron: "Not yet, keep building" (declined to commit point 4 yet):** continued straight to point 5 (schema contracts) without stopping — it was already named as an option alongside point 4 in the same framing, so no new question was needed to pick it. New `agent/schema_contracts.py` + two real JSON contract files, `agent/contracts/health_facilities.json`/`admin2.json` — exactly the minimal-start scope this review document's own point-5 entry had already suggested. Fields match by a case-insensitive ALIAS LIST (`admin2_pcode`/`adm2_pcode`/`ADM2_PCODE` all satisfy one slot) rather than one fixed name, deliberately mirroring this codebase's own existing treatment of admin/pcode field names as caller-supplied parameters (`calculate_severity_index`'s `unit_name_field`, etc.), not fixed strings — real COD-AB/geoBoundaries downloads vary. Field types check against the same `QVariant.<name>` vocabulary `_qvariant_type_for_dtype` already uses elsewhere in this codebase; `allowed_values` gives a real controlled-vocabulary check. Two new tools, `list_schema_contracts`/`validate_schema`. Wired into point 2's gate as an OPT-IN check on VALIDATED -> ANALYSIS_READY — only runs when `contract_name` is supplied, since only 2 datasets have contracts so far; omitted, the transition falls through to the ordinary note-required path instead of failing a check with nothing to check against. 22 new tests. Full suite 835 tests, same known baseline, 0 new failures. See queue item 14 and point 5's updated entry in `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.

> **Update, same day, further later still — a tool disconnect/reconnect intervened, then Baron answered "Keep going toward point 6 (P-code depth) or point 17 (provenance sidecar), or stop here for now?" with "Point 6: P-code depth":** New `agent/pcode_validation.py` (`check_pcode_uniqueness`, `check_pcode_hierarchy`) + `agent/tools/pcode_validation_tools.py`, matching field names via the same case-insensitive alias list as point 5's schema contracts, for the same reason. The hierarchy check is a pure attribute-level string-prefix check, not a spatial one — real COD-AB admin2 downloads denormalize the parent admin1 P-code onto every child row as a sibling field (e.g. admin2 `YE1201` under admin1 `YE12`), so no spatial join/containment logic was needed; that harder, separate check (does the admin2 polygon actually sit inside its claimed admin1 polygon) remains point 4's own untouched semantic-topology item. Wired into point 2's gate as `pcode_depth` on INGESTED -> STAGED — unlike point 5's opt-in schema-contract check, this one auto-detects whether a layer even has P-code-shaped fields and passes as "not applicable" when it doesn't, so it can never block a non-admin-boundary layer from advancing. A real regression surfaced and was fixed mid-build: adding `pcode_depth` to the gate initially made a fields()-less fake layer (used by an existing, unrelated test) hit a hard failure instead of "not applicable," which would have wrongly blocked every non-P-code layer's INGESTED -> STAGED advance — corrected before writing any new tests, then a second, older test whose whole premise ("INGESTED -> STAGED has no automated check") the new check now falsifies was updated to exercise a transition that still has none (ANALYSIS_READY -> CARTOGRAPHY_READY) instead. 30 new tests: 16 for the core module (`tests/test_pcode_validation.py`), 9 for the tool wrappers (`tests/test_pcode_validation_tools.py`), 5 gate-integration tests in `tests/test_dataset_status.py`. Full suite 865 tests, same known baseline, 0 new failures. See queue item 15 and point 6's updated entry in `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.

> **Update, same day, further later still — Baron declined to commit point 6 ("Not yet, keep building") and continued to point 17 (provenance sidecar), already named as the alternative option in the same question:** New `agent/provenance.py`'s `build_provenance_record` assembles a machine-readable provenance record (QGIS version, tool-execution lineage, QA-gate status/history/checks) as pure computation, reading both halves off records that already exist — `lineage.py`'s tracked history and point 2's `dataset_status.py` record — rather than tracking either a second time. Two new tools in `agent/tools/provenance_tools.py`: `get_provenance_record` (read-only) and `write_provenance_sidecar`, which writes a real `<source_file>.provenance.json` file beside the layer's own on-disk source when one resolves, falling back to a named Desktop file (with an explicit warning) for a scratch/memory layer with no real source — the same fallback convention `export_tools.py`'s `generate_report` already uses. Deliberately not wired into point 2's gate — a provenance sidecar is a generated artifact a caller asks for, not a transition a layer must pass. 17 new tests, including real on-disk JSON writes cleaned up afterward, matching `tests/test_export_tools.py`'s existing convention. Full suite 882 tests, same known baseline, 0 new failures. See queue item 16 and point 17's updated entry in `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`. (Note: points 4 and 5, above, were already committed earlier this session as `250f04a` -- the "not yet committed" language on their own paragraphs and on queue items 13/14 below was never updated after that commit landed; corrected here and there rather than left stale.)

> **Update, same day, further later still — Baron: "Yes, commit all four now" (points 4, 5, 6, 17):** checking git history before committing found points 4 and 5 already committed as `250f04a` earlier this session -- the two prior "commit 4/5/6?" questions to Baron had mischaracterized them as still uncommitted, going off stale registry language that was never corrected after that commit landed (now fixed, above and in queue items 13/14). Only points 6 and 17 actually needed committing. Committed as `e3bc00c` -- 15 files, 1371 insertions(+), 62 deletions(-), scoped to exactly `agent/pcode_validation.py`, `agent/provenance.py`, their two tools/ wrappers, four new test files, `agent/dataset_status.py`/`agent/tools/dataset_status_tools.py`/`agent/tools/__init__.py` and their two existing test files, plus this registry and the review document -- the pre-existing unrelated uncommitted work (item 5 below) untouched. Full suite re-verified clean post-commit: 882 tests, same known baseline, 0 new failures.

> **Update, later, cross-session (Baron back at his machine, screenshots of a live QGIS 4.2 session):** hit `authManager().isDisabled()` for real -- exactly the environment condition `auth.py`'s existing plaintext-fallback path was already built to handle gracefully, but the resulting warning gave no reason or fix. Asked to consider "adding needed dependencies during installation" -- researched (not assumed) and found this can't literally be done that way: QGIS's native Qt/QCA libraries aren't something a plugin's own `qpip`/`requirements.txt` mechanism can install. Built the next-best thing instead: `CredentialManager.auth_system_status()`/`get_auth_system_diagnostic_message()` surface the two real, documented causes (a QGIS 3.40.4+ proxy-authcfg regression, or a missing QCA-OpenSSL backend) and their fixes directly in the existing warning dialog. A separate Gemini API 403 on the same session is unrelated -- a Google-account-side issue, not a QGIS or plugin defect. 5 new tests, full suite 887 tests, same known baseline, 0 new failures. See queue item 17 and Level 3b for full detail. Also corrected: two "not yet committed" claims for points 6/17 that had gone stale the moment `e3bc00c` actually landed (queue items 15/16, above).

> **Update, cross-session, 2026-09-05 — repo sync + first live-QGIS smoke test:** this local checkout was found 20 commits behind `origin/main` (a `764afce` merge reconciling this repo's line with `cartogen-ai-community`'s had landed on origin without a corresponding registry update). Stashed the held uncommitted work, fast-forward pulled, resolved 4 real conflicts, reapplied `account_dialog.py`'s Qt6 fix through `qgis_compat.enum_member()` instead of a hardcoded form, and found/fixed 3 real merge-induced defects along the way (duplicate `class ConnectionType` in `agent.py`'s no-QGIS stub, duplicate `clear_global_notes()` in `memory.py`, two silently-shadowed duplicate test methods in `test_memory_and_tasks.py`) plus ~15 dead imports — committed as `d8113b8`. Then ran `docs/RELEASE_SMOKE_TEST.md`'s checklist for the first time in this environment: the GUI proved undriveable (QGIS launches and stays responsive, confirmed via process state, but its window never composited to anything screen-capture/input-injection could reach — a recurring stray "Windows Input Experience" process kept stealing focus too). Pivoted to a real headless PyQGIS session instead (QGIS 4.2.2's own `python-qgis.bat`, offscreen) and found a genuine live-only bug on the first pass — see BUG-2026-09-05-1 (`QgsColorRampShaderItem` import crash silently degrading all 11 raster tools). Fixed, re-verified live (14/14 checklist categories passing, incl. 2 real network calls), swept all 38 agent/tools modules for the same failure class (clean), committed as `a424b36`. Sandboxed suite: 1025 tests, 0 failures, 7 skipped throughout. **Not done:** the GUI-driven half of the checklist (chat UI, LLM dispatch, canvas, Tasks tab) remains unverified — see queue item 6.

> **Update, same day, later — the GUI half got done after all, cooperatively:** this environment's screen-capture/input-injection pipeline genuinely cannot render or reliably interact with QGIS's window (confirmed rigorously: process responsive, window correctly positioned/visible per Win32, no hidden modal dialog per a full window enumeration, software-OpenGL forced — screenshots stayed solid black regardless). Rather than keep guessing blind, Baron drove the live session directly and shared screenshots for verification. Real evidence obtained: (1) a real Google Gemini (Hosted) chat response loaded `test_points_export.csv` (from the BUG-2026-09-05-1 headless session) into the live project as a real "Health Facilities" layer with real WKT-parsed geometry and a real 5-class graduated Viridis style by `severity` — confirms chat UI + LLM dispatch + real tool execution all work end-to-end; (2) the Tasks_Notes tab renders correctly and honestly shows "No active plan yet" for a single-tool request (not a bug — task_manager's plan view is for genuinely multi-step requests); (3) a real `create_print_layout` call produced an actual layout in QGIS's Layout Manager with a real map, graduated legend, scale bar, north arrow, and — confirmed via direct screenshot of the Layout Designer — the BUG-2026-09-02-6 standing disclaimer footer, fully legible and correctly positioned in landscape orientation (portrait still unconfirmed); (4) the chat's "prompt that will be sent" preview card showed real task-register matching (task 28.15, confidence 0.17) and real tool-ordering reasoning, confirming that pipeline runs live too. Updated BUG-2026-09-02-6's status accordingly (see Level 3a and `docs/BUG_TRACKER.md`). Remaining gap: portrait-orientation layout fit, and the deeper `docs/RELEASE_SMOKE_TEST.md` checklist rows not touched this pass (destructive-action confirm gate live, scheduled-workflow live, etc.).

> **Update, cross-session, 2026-09-07 — new feature request, not from the 27-point review, direct from Baron:** "the new idea/featur is animated dashboard from several views from the map like the status of fighting groups from 2016-2026 in Syria and the controls areas." Scoped via three questions (data source: capability now, real data later; output: both HTML and QGIS-native; scope: reusable tool, not Syria-specific) and built as `generate_temporal_dashboard`/`export_temporal_animation_frames` in `agent/tools/export_tools.py` — full detail in Level 3b's 2026-09-07 entry. 35 new tests, full suite 1196 tests, same known baseline, 0 new failures. Not yet committed — awaiting Baron's go-ahead, same as everything else in this registry. **[Corrected, 2026-09-08]:** now committed as `609ee10` (2026-09-08, covers both phases).

> **Update, same day, later — Baron asked to see it run, then shared a screenshot of a real, live Microsoft Power BI Syria-conflict dashboard ("is something like this"):** the reference showed four concrete gaps against the phase-1 build: a synced trend chart below the map, a location filter panel, point markers colored by category (phase 1 rendered points as plain default icons, not colored), and a two-handle date-range filter in addition to the existing play/pause animation. Asked which to add and why (UX-reference-only vs. eventual real-data target) — Baron: all four, and "eventually load real data like this" (real-data intent noted, but the standing capability-now/no-fabricated-Syria-data scoping from earlier the same day is unchanged — still placeholder-only). Built all four into `_build_temporal_dashboard_html`: point-geometry temporal layers now render as real `folium.CircleMarker`s (confirmed via live inspection that folium's generated `pointToLayer` merges `style_function`'s output into the marker via `Object.assign`, so the existing per-feature color logic just works, unifying the toggle code path with polygons' `.setStyle()`); a location-filter checkbox panel (built from a new `location_field` per-layer option); a Chart.js v4 (CDN, `4.5.1`) stacked-bar trend chart aggregating feature counts by month/category, synced to the current date-range and location-filter selection; and a date-range filter as two plain `<input type=range>` sliders (deliberately, over a fancier dual-handle widget, to avoid a new JS dependency) that clamp the existing play-slider's bounds and wrap the play-loop within the selected range. Found and fixed a real security gap while adding the chart: the chart's caller-controlled data (location/category names) was being embedded via plain `json.dumps()`, which doesn't escape a literal `</script>` sequence and could break out of its own `<script>` tag — added `_json_for_inline_script()` (escapes `</` to `<\/`) and applied it to both new inline-JS data embeddings; `json.dumps`'s own `ensure_ascii=True` default was verified (live) to already handle the separate U+2028/U+2029 JS-line-terminator issue, so no extra handling was needed there. Also found and fixed a latent bug the new `marker_radius` schema field exposed: `layer.get("marker_radius", 6)` silently returns `None`, not `6`, whenever the tool wrapper's prepared-layer dict carries an explicit `"marker_radius": None` (which it always does when a caller omits the field) — changed to `layer.get("marker_radius") or 6`. 21 new tests (`TestMonthBucketLabel`, `TestResolveFeatureLocations`, `TestResolveTemporalColorsSortedOrder`, `TestBuildTrendChartData`, `TestBuildTemporalDashboardHtmlNewFeatures` incl. the script-breakout regression test), full suite re-verified after the marker_radius fix: `tests.test_temporal_dashboard` 56/56 passing, full suite 1217 tests, same known baseline (1 DNS-dependent failure, 6 FUSE `PermissionError` cleanup errors), 0 new failures; pyflakes clean (same 2 pre-existing/accepted `style_function` redefinition warnings, no new ones). `docs/TOOLS_REFERENCE.md` regenerated (158 tools, updated description/schema for `generate_temporal_dashboard`). Still not committed — this is materially different code from phase 1's own not-yet-approved commit, so it needs its own fresh go-ahead from Baron, not a carry-over of any earlier approval.

### Next steps queue (ordered — work the top item first, unless Baron redirects)

1. ~~Get Baron's explicit go-ahead to commit the two fixes above~~ — **done, 2026-09-04.**
   Baron: "Yes, commit both now." Committed as `2624313` "fix: chat-history restore timestamps
   + fabrication-safety mitigation" (8 files, 384 insertions/38 deletions — exactly the
   BUG-2026-09-02-6/-7 fileset, nothing from the still-held account feature). Full suite
   re-verified clean post-commit: 727 tests, 0 new failures. Live-QGIS verification for the
   UI/layout halves is still outstanding (see queue item 5, now renumbered — was item 5).
2. ~~Route rendering — decided, 2026-09-04: upgrade, don't just block.~~ — **implemented,
   2026-09-04, uncommitted.** `optimize_delivery_route` now builds a real road-snapped route
   via `native:shortestpathpointtopoint` when given `road_network_layer`; without it, returns
   an explicit warning instead of a silently-drawable straight line. See Level 3b.
3. ~~Incident coding vocabulary — decided, 2026-09-04: support both.~~ — **implemented,
   2026-09-04, uncommitted.** `add_incident_point`/`add_point_layer` gained optional
   ACLED-style and IMSMA/IMAS-style controlled fields alongside the existing freeform ones. See
   Level 3b.
4. ~~Push to GitHub and create the GitHub Release object~~ — **done, 2026-09-05.** Working
   GitHub auth was available this session (unlike every prior session's documented
   credential blocker) — `main` and `commercial-plugin-v1.6.0` both pushed, and the
   [GitHub Release](https://github.com/cartogenai-glitch/CARTOGEN-AI/releases/tag/commercial-plugin-v1.6.0)
   was created directly (portable `gh` CLI, authenticated through git's own existing
   credential — no admin rights needed, no token ever displayed). Supersedes the v1.5.0
   push, which shipped as part of v1.6.0 instead.
5. **Hosted Cartogen AI account feature — decided, 2026-09-04: hold.** Baron: "Hold it — keep
   uncommitted for now." Left exactly as-is (`agent/account.py`, `ui/account_dialog.py`, and
   the account hunks in `settings_dialog.py`/`USER_GUIDE.md`/`README.md`/`plugin_upload.py`,
   plus `tests/test_account_client.py`/`test_account_ui.py`) — not committed, not removed,
   revisit when Baron is ready to decide scope/UX.
6. **Run `docs/RELEASE_SMOKE_TEST.md`'s manual checklist in a real, live QGIS 4.2 session**
   once one is available to this engagement — several fixes this session (Qt6 enum scoping,
   dark-theme colors, the self-learning UI wiring, and now the chat-timestamp fix and the
   print-layout disclaimer footer's on-page fit) are `fixed-unverified`/
   `fixed-unverified-pending-live-session` specifically because this sandbox cannot import
   `qgis.PyQt`/run a real QGIS process. Portrait-orientation print layouts specifically need
   a look — the disclaimer footer's fit there is tight and unconfirmed (see BUG-2026-09-02-6).
   Land the Section VIII metadata-block work from
   `docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md` (map subject/period, sources/versioning,
   projection/CRS, sensitivity disclaimer) alongside this smoke test rather than ahead of it —
   stacking another mandatory layout element on the already-tight, already-unverified portrait
   geometry blind risks compounding one unconfirmed fit into two.
7. ~~Decide how to close the ~15 unscoped-enum risk on QGIS's own native classes~~ —
   **resolved differently than either offered option, 2026-09-04, uncommitted.** Rather than
   guessing which literal form to blanket-rewrite to (option b) or needing a live QGIS 4.2
   session to verify each one first (option a), added a runtime dual-resolution helper
   (`agent/tools/_qgis_enum_compat.py`'s `resolve_qgis_enum`) that tries the QGIS 4.x/Qt6
   scoped form first and falls back to the QGIS 3.x/Qt5 flat form — no guess needed, works on
   either QGIS major version, and generalizes the identical hand-rolled `getattr` pattern
   already found in use for `QgsZonalStatistics.Mean`/`.Sum`. Applied at all 9 flagged classes
   across `agent/tools/{styling,raster,export,layout,humanitarian}_tools.py` and
   `agent/task_runner.py`. See BUG-2026-09-04-1 and Level 3b for the full site list. This
   doesn't require re-litigating (a) vs (b) — the mechanism works regardless of which form a
   given QGIS install exposes, though the actual resolved *values* remain unverified against a
   live QGIS 4.2 session same as everything else pending queue item 6.
8. ~~Circle back on the `web-platform`/`apps/web` migration~~ — **resolved 2026-09-04, moot.**
   Baron explicitly scoped this engagement to the QGIS plugin only ("the web platform is not my
   focus here"). The Obsidian-sync question this item asked is answered: no, don't keep
   web-platform notes in sync as part of this repo's work. Left struck-through rather than
   deleted per this registry's own no-silent-rewrite convention.
9. ~~Reconcile GDPR review finding F1 across repos~~ — **done, 2026-09-04.** Baron: "port the fix into cartogen-ai-community too." Ported `clear_global_notes()` + the "Clear Global Memory" UI control + 2 tests into `cartogen-ai-community`, adapted to that repo's actual code (it predates this repo's self-learning system, so no `delete_global_note()`/`pref:`/`rule:`/`usage:` scheme to reconcile there — a plain bulk-clear addition instead). Committed there as `99079e3`; full suite 837/1/6/20, same known baseline, 0 new failures. Also logged in that repo's own `docs/BUG_TRACKER.md` (BUG-2026-09-04-1) and `docs/IMPLEMENTATION_TRACKER.md` (dated update appended, original 2026-09-01 entry left untouched per that repo's no-silent-rewrite convention). F1 is now closed in both repos.
10. ~~Re-review point 19 (AST sandbox vs. a 4-tier allow-list model) against the 2026-08-21 audit~~ — **done, 2026-09-04.** The audit's narrow conclusion (sandbox beats a confirm-dialog for this tool shape) holds — but re-testing the denylist's actual completeness (not what the audit checked) found and fixed 4 live, working bypasses: `pathlib`/`dbm`/`logging`/`zipfile` all wrote real files to disk without tripping `_validate_script_safety`, none using the already-blocked `open` name. Added to `_BLOCKED_MODULES`, 1 new regression test, `SECURITY.md` updated; full suite 758 tests, same known baseline, 0 new failures. **Still open, Baron's call:** the larger question of moving to a tiered allow-list architecture instead of a denylist sandbox at all — patching 4 found bypasses doesn't resolve that, it just closes what was actually found this session. Full account in `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`'s updated point 19.
11. ~~Close points 9, 21, and 13 (population exposure, project inspector, classification) from the 27-point review~~ — **done, 2026-09-04.** Baron: "pick the next item from the 27-point review to tackle," then "Complete the remaining tools." Point 9: `estimate_population_exposure`/`population_access_gap` gained `pop_exposed_est`/`gap_population_est`, `pop_source`/`pop_reference_year`, `analysis_resolution`, and `confidence` fields. Point 21: `get_layers` gained `crs`/`fields`/`feature_count`; new `list_layouts` tool. Point 13: `apply_graduated_style` gained a `breaks` parameter for manual/defined-threshold classification (a real NameError bug found and fixed mid-implementation, before it reached a test). 14 new tests total, full suite 772/1/6/14, same known baseline, 0 new failures. See each point's updated entry in `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`. Committed as `0f2f796` on Baron's explicit "Yes, commit it" — 12 files, 562 insertions(+), 49 deletions(-), the pre-existing unrelated uncommitted work (item 5 below) untouched.
12. ~~Build the shared QA-gate/dataset-status infrastructure (point 2) that points 4/5/6/7/17 depend on~~ — **first pass done, 2026-09-04**, on Baron's explicit "Start the shared infrastructure." New `agent/dataset_status.py`: the six-state ordered lifecycle (INGESTED→STAGED→VALIDATED→ANALYSIS_READY→CARTOGRAPHY_READY→PUBLICATION_READY) as a JSON custom property on the layer, same durable-storage pattern `lineage.py` already proved (survives project save/reload for free); a real sequential gate (no skipping states, no silent unchecked advance -- an unchecked forward move or any backward move requires a `note`); one real automated check wired in, `geometry_validity` gating STAGED -> VALIDATED, reusing the existing `diagnose_topology` (point 4) rather than reimplementing it, with `override=True` + a mandatory note to bypass a failed check, recorded in history. New `agent/tools/dataset_status_tools.py` exposes it as three registered tools: `get_dataset_status`, `set_dataset_status`, `advance_dataset_status`. Deliberately does **not** yet build points 5 (schema contracts), 6 (P-code depth), 7 (temporal GIS), or 17 (provenance sidecar) -- each can register its own check in `_AUTOMATED_CHECK_TRANSITIONS` once built, rather than needing its own state-tracking; see each point's updated entry in `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md` for the specific hook. 29 new tests (`tests/test_dataset_status.py`, `tests/test_dataset_status_tools.py`), full suite 801/1/6/14, same known baseline, 0 new failures. Committed as `3135ff6` on Baron's explicit "Yes, commit it" — 7 files, 774 insertions(+), 18 deletions(-).
13. ~~Extend point 4's geometry QA with overlaps/duplicates/min-area, wire into point 2's gate~~ — **done, 2026-09-04**, on Baron's "pick one dependent point to build next" after committing item 12. `diagnose_topology` gained `duplicate_geometries` and (polygon layers) `overlapping_feature_pairs` via `QgsGeometry.overlaps` + the existing `QgsSpatialIndex` bbox-prefilter pattern, plus an optional `min_area` small-polygon threshold; point 2's gate now checks both new fields too, not just `invalid_geometries`. Gap detection and the semantic admin1/admin2 P-code topology check deliberately left unbuilt — see point 4's updated review-doc entry for why. 12 new tests (8 for `diagnose_topology`, its first coverage of any kind; 4 for the strengthened gate). Full suite 813/1/6/14, same known baseline, 0 new failures. Committed as `250f04a` alongside item 14.
14. ~~Build point 5's first schema contracts (health_facilities, admin2), wire into point 2's gate~~ — **done, 2026-09-04**, on Baron's "not yet, keep building" after declining to commit item 13. New `agent/schema_contracts.py` + `agent/contracts/health_facilities.json`/`admin2.json` (real JSON files). Fields matched by a case-insensitive alias list, not one fixed name, matching this codebase's own existing pattern of treating admin/pcode field names as caller-supplied parameters. Field types checked against the same `QVariant` vocabulary `_qvariant_type_for_dtype` already uses; `allowed_values` gives a controlled-vocabulary check. New `list_schema_contracts`/`validate_schema` tools. Wired into point 2's gate as an opt-in check on VALIDATED -> ANALYSIS_READY (only runs when `contract_name` is supplied). 22 new tests. Full suite 835/1/6/14, same known baseline, 0 new failures. Committed as `250f04a` alongside item 13.
15. ~~Build point 6's P-code depth checks (uniqueness, hierarchy), wire into point 2's gate~~ — **done, 2026-09-04**, on Baron's "Point 6: P-code depth" after a tool disconnect/reconnect and the "keep going toward point 6 or point 17" question. New `agent/pcode_validation.py` (`check_pcode_uniqueness`, `check_pcode_hierarchy`) + `agent/tools/pcode_validation_tools.py`, using the same case-insensitive alias-list field matching as point 5. The hierarchy check is a pure attribute-level string-prefix check (real COD-AB data denormalizes the parent P-code onto every child row), not a spatial containment check — that remains point 4's untouched semantic-topology item. Wired into point 2's gate as `pcode_depth` on INGESTED -> STAGED, auto-passing "not applicable" when a layer has no P-code-shaped fields so it never blocks a non-admin-boundary layer. Fixed a real regression mid-build (a fields()-less fake layer was initially treated as a hard failure instead of "not applicable") and updated one older test whose "no automated check on this transition" premise the new check superseded. 30 new tests. Full suite 865/1/6/14, same known baseline, 0 new failures. Committed as `e3bc00c` alongside item 16.
16. ~~Build point 17's provenance sidecar (QGIS version + lineage + QA-status assembled into one JSON record, written to a real file)~~ — **done, 2026-09-04**, on Baron's "Not yet, keep building" after declining to commit item 15 — continued to point 17 since it was already named as the alternative option in the same question. New `agent/provenance.py`'s `build_provenance_record` (pure computation, reads `lineage.py`'s tracked history + point 2's `dataset_status.py` record rather than tracking either twice) + `agent/tools/provenance_tools.py`'s `get_provenance_record`/`write_provenance_sidecar`. The sidecar writer sits the JSON file beside the layer's own on-disk source when one resolves, falling back to a named Desktop file (with an explicit warning) for a scratch/memory layer — the same fallback convention `generate_report` already uses. Deliberately not wired into point 2's gate — a generated artifact, not a transition a layer must pass. 17 new tests. Full suite 882/1/6/14, same known baseline, 0 new failures. Committed as `e3bc00c` alongside item 15.
17. ~~Diagnose and improve the "QGIS auth system disabled" bottleneck Baron hit live on QGIS 4.2~~ — **done, 2026-09-04**, from Baron's own screenshots plus "consider adding any needed dependencies during the installation of the package." Confirmed via WebSearch that neither documented root cause (a QGIS 3.40.4+ proxy-authcfg regression, or a missing QCA-OpenSSL backend) can be fixed from inside this plugin's own package -- `qpip`/`requirements.txt` only installs Python packages, never QGIS's native Qt/QCA libraries or its settings. Built `agent/auth.py`'s `auth_system_status()`/`get_auth_system_diagnostic_message()` instead, wired into `ui/settings_dialog.py`'s existing plaintext-fallback warning so it names the real cause+fix instead of a generic "wasn't available" message. 5 new tests, full suite 887/1/6/14, same known baseline, 0 new failures. `auth.py`/`settings_dialog.py` both already carry the held account-feature diff (item 5) -- committing this will need per-file blob-staging, not a plain `git add`. Not yet committed — awaiting Baron's go-ahead. See Level 3b for full detail. **[Corrected, 2026-09-08]:** now committed as `c9a7a82` (2026-09-04).
18. **Decide what to do with the rest of the 27-point QGIS production-architecture review.** `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md` has the full verbatim proposal plus a code-grounded gap analysis — points 1 (both halves), 2 (first pass), 3 (buffer_analysis's warning), 4 (overlaps/duplicates/min-area), 5 (first 2 contracts), 6 (uniqueness/hierarchy), 7 (the record-level half — event_start/event_end/last_verified), 8 (the strategy doc's own already-scoped §2 item 1 — SPEED_FIELD/DIRECTION_FIELD), 9, 12 (style-library reuse), 13, 15 (both the item-addressability half and the full QgsLayoutAtlas per-feature half), 16 (map themes), 17 (provenance sidecar), 19 (both the first-pass fix and a second, broader denylist sweep), 20 (corrected 2026-09-05, taxonomy+narrowed-rollback built 2026-09-07 — see item 34), 21, 22 (zero-result warning, flagship example only), 24 (sensitivity/disclosure tagging, advisory not blocking), and 26 (per-product QA checklist) are now closed, partially closed, or corrected (see items 10-16, 20-33); the rest keep their original verdicts (1 already true, the remainder real gaps or partial, several of which — 18, 19's larger question, 27 — are explicitly architecture/policy decisions, not mechanical gap-fills, and deliberately left flagged rather than silently changed). Baron: "continue the full list" (2026-09-05), then explicitly asked to also process the flagged architecture/policy items — working through them individually, still declining to build the ones needing live-LLM validation this environment can't do (18, 27) or that impose a real workflow-affecting product opinion (28) unilaterally.
19. ~~Close point 12 (style-library reuse) from the 27-point review~~ — **done, 2026-09-05.**
   Baron: "proceed with no 2" (item 18's review-followthrough), picked per this project's own
   established selection logic (self-contained, no dependency on undecided design questions,
   one session). New `save_layer_style`/`load_layer_style` tools in `styling_tools.py`, real
   `QgsMapLayer.saveNamedStyle()`/`loadNamedStyle()`, `.qml` files. Live-verified against QGIS
   4.2.2 (headless PyQGIS): applied a real graduated style, round-tripped it through a real
   `.qml` file onto a fresh layer, confirmed the renderer type and class structure survived.
   13 new tests, full suite 1038/0/7 skipped. See point 12's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`. Committed as `cddfe0e`, pushed.
20. ~~Close point 22 (zero-result warning, flagship example) from the 27-point review~~ —
   **done, 2026-09-05.** Baron: "continue the full list." Fixed once in the shared
   `_run_and_add` helper (~18 vector-tool call sites) rather than per-caller: reports
   `feature_count` on any output that has one, and an explicit `warning` when it's zero —
   purely additive, no caller needed updating. 4 new tests (zero prior direct coverage of
   this function). Live-verified against QGIS 4.2.2: a real non-overlapping-polygon
   intersection produced the warning, a real overlapping one didn't false-positive. Full
   suite 1042/0/7 skipped. The systemic PLAN→EXECUTE→OBSERVE→VALIDATE→REPAIR agent-level loop
   this point also names remains unbuilt — a genuinely separate, architecture-level item (see
   point 18). See point 22's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
21. ~~Close point 16 (Map Themes) from the 27-point review~~ — **done, 2026-09-05.** New
   `create_map_theme`/`apply_map_theme`/`list_map_themes` tools in `project_tools.py`
   (`QgsMapThemeCollection`). **A real bug caught before shipping, not just tested around:**
   both `createThemeFromCurrentState`/`applyTheme`'s `model` parameter is typed
   `QgsLayerTreeModel|None`, but passing `None` segfaults the process outright on real QGIS
   4.2.2 (a hard exit, not a catchable exception) — reproduced live before writing any tool
   code, fixed by always building a real `QgsLayerTreeModel`. 12 new tests. Live-verified:
   created two themes with different real layer-visibility states, applied one, confirmed the
   target layer's real visibility flag flipped. Full suite 1049/0/7 skipped.
   `docs/TOOLS_REFERENCE.md` regenerated (146 tools). See point 16's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
22. ~~Close point 1 (Processing-first execution model) from the 27-point review~~ — **done,
   the mechanical half, 2026-09-05.** `execute_pyqgis_script`'s own description now opens
   "LAST RESORT ONLY," matching what other tools' descriptions already say to steer the model
   away from it. **Deliberately not changed:** whether to remove it from
   `tool_router.py`'s `always_include` set (guaranteed visible on every query regardless of
   relevance) — that's a routing-visibility change to a security-relevant tool, flagged as
   Baron's call (Hermes Charter Rule 9) rather than silently flipped, same shape as point 19's
   still-open larger question. `docs/TOOLS_REFERENCE.md` regenerated. Full suite 1049/0/7
   skipped (pure description text, no new branch to test). See point 1's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
24. ~~Close point 3 (CRS-operation-aware handling) from the 27-point review~~ — **done, the
   buffer_analysis half, 2026-09-05.** **Verified live before assuming a bug existed:** checked
   whether `calculate_area`/`calculate_length` (`$area`/`$length`) needed a similar fix first —
   they didn't, both are already ellipsoidal-aware regardless of CRS, confirmed against a real
   ~1km² polygon in EPSG:4326. `buffer_analysis` is the real bug: `native:buffer`'s `DISTANCE`
   is applied in the layer's own CRS units with no conversion — confirmed live, buffering an
   EPSG:4326 point by 500 (meaning meters) produced a buffer 1000 degrees wide, not ~1km.
   Fixed with an honest `warning` (CRS named, told to reproject first) plus a strengthened
   description, not a guessed auto-reprojection to a computed UTM zone — that's a real, bigger
   design decision left flagged, not built. 4 new tests. Live-verified both branches (geographic
   warns, projected doesn't). Full suite 1053/0/7 skipped. `docs/TOOLS_REFERENCE.md`
   regenerated. See point 3's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
25. ~~Close point 15 (Atlas item addressability) from the 27-point review~~ — **done, the
   addressability half, 2026-09-05.** Every item `create_print_layout` builds now gets a
   stable `.setId()` (`MAP_MAIN`/`TITLE`/`LEGEND`/`SCALEBAR`/`NORTH_ARROW`/`BODY_TEXT`/
   `FOOTER`). Two new tools use it: `list_layout_items` (id/type/text per item, filters out
   QGIS's own internal page/frame plumbing which has no real id) and `update_layout_item_text`
   (edit one item's text by id without rebuilding the whole layout). Deliberately does **not**
   build full `QgsLayoutAtlas` per-feature pagination — a separate, larger feature, a real
   scope decision left flagged. 12 new tests. Live-verified: built a real layout, all 7 items
   resolved correctly, updated `TITLE` and confirmed it persisted, confirmed `MAP_MAIN`
   (no settable text) and a bad id both error correctly. Full suite 1061/0/7 skipped.
   `docs/TOOLS_REFERENCE.md` regenerated (148 tools). Also fixed `list_layouts`' own
   description, which had gone stale about point 16 the moment that point closed the same
   session. See point 15's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
26. ~~Close point 26 (per-product QA checklist) from the 27-point review~~ — **done,
   2026-09-05.** New `agent/tools/qa_checklist_tools.py`'s `generate_map_product_qa_checklist`
   assembles Data (reads point 2's `dataset_status`), Cartography (reads point 15's
   `list_layout_items` for the 5 mandatory elements, when a layout is given), Export/Provenance
   (reads point 17's `get_provenance_record`), and Disclosure (honest static note — point 24
   isn't built, so this isn't a guessed pass/fail). Pure assembly, no new tracked state. 7 new
   tests. Live-verified end to end: ran against a real untracked layer, then against the same
   layer after a real `set_dataset_status` + `buffer_analysis` + `create_print_layout` — the
   checklist correctly picked up the real status, all 5 real layout elements, and the real QGIS
   version. Full suite 1068/0/7 skipped. `docs/TOOLS_REFERENCE.md` regenerated (149 tools, 21
   groups). See point 26's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
27. ~~Close point 20 (transaction taxonomy) from the 27-point review~~ — **corrected, not a
   new decision, 2026-09-05.** Baron asked to process the flagged architecture/policy items too.
   Turned out this one didn't need a policy call at all: point 20's framing ("an open,
   already-logged policy decision with three named options") was stale the moment the review
   was written on 2026-09-04 — `docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md` §3's three
   options were actually resolved **2026-08-22**, documented in `SECURITY.md` §5 and
   `docs/IMPLEMENTATION_TRACKER.md` §1.1/§4 (Option 1 adopted: leave the 4 humanitarian tools
   ungated). The review's own author hadn't cross-checked `IMPLEMENTATION_TRACKER.md`. No code
   change — corrected the review doc's entry to point at the real resolution. The
   READ/CREATE/MODIFY/DELETE/PUBLISH taxonomy and multi-step rollback halves of this point
   remain real, unaddressed gaps. See point 20's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
28. ~~Close point 1's routing half (execute_pyqgis_script's `always_include` slot) from the
   27-point review~~ — **done, 2026-09-05, on Baron's explicit go-ahead to process the flagged
   items too.** Implemented the bounded middle ground the original entry proposed rather than a
   binary remove/keep: `execute_pyqgis_script` now scores normally like every other tool and
   only gets a guaranteed slot as a true last resort, when nothing else in the candidate set
   scored any real relevance. **A real bug caught by the new tests themselves before this
   shipped**, not live: the first implementation's "did anything else match" check included the
   *other* `always_include` core tools' synthetic 1000-scores, which are unrelated to the
   query's content — so the check was true on literally every query, silently keeping the
   fallback broken for genuinely nothing-matches queries too. Fixed to exclude all of
   `always_include`, not just the one tool. 2 new tests, stability-checked across 15 repeated
   runs (shuffled tie-break scoring). Full suite 1070/0/7 skipped. `docs/TOOLS_REFERENCE.md`
   regenerated. See point 1's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
29. ~~Close point 24 (sensitivity/disclosure classification) from the 27-point review~~ —
   **done, 2026-09-05, on Baron's explicit go-ahead to process the flagged items too.** New
   `agent/sensitivity.py` (pure logic) + `agent/tools/sensitivity_tools.py`'s registered
   `set_layer_sensitivity`/`get_layer_sensitivity` tag a layer PUBLIC/INTERNAL/RESTRICTED/
   SENSITIVE with an optional reason, stored as a `customProperty` (durable across project
   save/reload, same mechanism QGIS itself uses). `export_layer`/`export_to_csv`'s shared
   `_write_vector` helper now adds an advisory `warning` naming the level and reason on a
   RESTRICTED/SENSITIVE layer's export — explicit that the export already completed and
   nothing was blocked. **Deliberately advisory, not a hard export-blocking gate**: no
   automated classifier exists, only explicit tags are tracked, and this codebase has zero
   currently-tagged layers — hard-blocking every unclassified export would brick every
   existing workflow for a check nobody has populated yet. Same warn-don't-block restraint as
   items 20 and (this list's) point 22's zero-result warning. If usage later shows people tag
   and then export past the warning by habit, a blocking mode is a real follow-on decision —
   left flagged, not built unasked. 11 new tests. Live-verified against real QGIS 4.2.2: a
   real point layer exported untagged with no warning, tagged SENSITIVE with a real reason
   exported again with the real warning text (both level and reason present) while the CSV was
   genuinely written to disk, and the tag survived a real project save to `.qgz` and reload
   into a fresh `QgsProject` unchanged. Full suite 1080/0/7 skipped. `docs/TOOLS_REFERENCE.md`
   regenerated (151 tools). See point 24's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
30. ~~Second denylist-completeness sweep for point 19 (AST sandbox) from the 27-point
   review~~ — **done, 2026-09-05, on Baron's explicit go-ahead to process the flagged
   items too.** Bounded to the denylist-completeness question the 2026-09-04 first pass
   already established the technique for, not the larger tiered-allow-list rewrite,
   which remains the same open architecture call it was. Re-ran the identical live-
   reproduction harness (`_validate_script_safety` + `_SAFE_BUILTINS` through the real
   `exec()` path) against a broader candidate list and found 20 more confirmed-live
   bypasses: `io.open` (the same function object as the builtin `open`, reached by
   attribute instead of bare name); `tarfile`/`gzip`/`bz2`/`lzma` (the same archive/
   compression-writer file-write shape as the already-fixed `zipfile`); `winreg` (a
   real registry key write); `linecache`/`filecmp` (real arbitrary file read, not just
   write); `socketserver`/`poplib`/`imaplib`/`nntplib`/`xmlrpc` (the same network-client
   category as the already-blocked `ftplib`/`smtplib`); `webbrowser`/`pydoc` (external-
   program launch, same risk as the already-blocked `QDesktopServices`); `zipimport`
   (dynamic code loading, same risk as `importlib`/`runpy`); `venv`/`mmap` (no
   legitimate PyQGIS use, blocked for the same defense-in-depth reasoning as the rest
   of the list). All 20 added to `_BLOCKED_MODULES`. 1 new regression test covering all
   20 in one pass. Full suite 1081/0/7 skipped. `SECURITY.md` updated to match. As
   before: closes what this sweep found, not a claim of completeness. See point 19's
   updated entry in `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
31. ~~Close point 15's full-atlas half (real QgsLayoutAtlas per-feature export)
   from the 27-point review~~ — **done, 2026-09-05, on Baron's explicit go-ahead
   to process the flagged items too.** New `export_layout_atlas` (`layout_tools.py`):
   one output file per feature of a coverage layer, named from a caller-chosen
   field (sanitized), driving the same `MAP_MAIN` id `create_print_layout`
   already assigns — only works on a `create_print_layout`-built layout. **Two
   real API gaps found live before writing the tool**: the static atlas-aware
   `exportToPdf(atlas, ...)` produces one combined multi-page PDF, not one file
   per feature (`exportToPdfs`, plural, is the real per-file entry point); and
   there is no atlas-aware `exportToImage` overload at all (confirmed live —
   `TypeError`, no matching overload). Both worked around uniformly with manual
   `atlas.beginRender()/.first()/.next()/.endRender()` iteration over the
   ordinary per-page export call, confirmed live to work identically for both
   formats. 10 new tests. Full suite 1091/0/7 skipped. **Live-verified**: a
   real 3-feature layer exported 3 real PDF files named from a unique P-code
   field, a real PNG export with a `/` in the field value was correctly
   sanitized to `_` instead of writing outside the output directory or
   crashing, and `list_layout_items` after the atlas export confirmed the
   layout's own item addressability (point 15's first half) wasn't broken by
   atlas-driving `MAP_MAIN`. `docs/TOOLS_REFERENCE.md` regenerated (152 tools).
   See point 15's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
32. ~~Close point 7's record-level half (optional temporal fields on incident
   tools) from the 27-point review~~ — **done, 2026-09-05, on Baron's explicit
   go-ahead to process the flagged items too.** `add_incident_point`/
   `add_point_layer` gain optional `event_start`/`event_end`/`last_verified`
   fields, additive alongside the pre-existing freeform `date` -- matching
   the same optional-controlled-field pattern already used for ACLED/IMSMA
   coding. New `_validate_incident_temporal` warns (never blocks) when
   `event_end` is before `event_start` and both parse as ISO 8601; an
   unparsable freeform date pair is silently skipped, not flagged.
   Deliberately not built: `report_date`/`status` fields, `QgsTemporalController`
   map animation/playback, or a date-range filtering tool -- real, separate,
   larger pieces of work left as open gaps. 15 new tests. Full suite
   1103/0/7 skipped. **Live-verified against real QGIS 4.2.2**: baseline
   (no temporal fields) unchanged behavior, a valid period added cleanly, an
   inverted period added with a real warning, an unparsable freeform pair
   added cleanly with no false positive, the real stored attributes read
   back matched what was passed in, and a mixed `add_point_layer` batch
   warned on only the genuinely-inverted point. `docs/TOOLS_REFERENCE.md`
   regenerated (152 tools). See point 7's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
33. ~~Close point 8's already-scoped fix (SPEED_FIELD/DIRECTION_FIELD wiring)
   from the 27-point review~~ — **done, 2026-09-05, on Baron's explicit
   go-ahead to process the flagged items too.** Re-read the frozen
   `docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md` instead of guessing point 8's
   scope from scratch -- its own §2 item 1 had already scoped exactly this as
   "the highest-value, lowest-risk change available... a small, independent
   follow-up," distinct from the larger composite-impedance/VRP items in the
   same section. `calculate_service_area`/`travel_time_matrix` both gain
   optional `speed_field`/`direction_field` (+ OSM-convention-defaulted
   `value_forward`/`value_backward`/`value_both`) via a new shared
   `_network_direction_speed_params` helper; `travel_time_matrix` also gains
   the `strategy`/`default_speed` params `calculate_service_area` already had
   (previously hardcoded to shortest-path only). 17 new tests. Full suite
   1117/0/7 skipped. **Live-verified against real QGIS 4.2.2** (correcting
   this module's own docstring, which had claimed it was never run against a
   real session): a real one-way road correctly blocked the reverse route
   via `direction_field`; a real differential-speed test produced two
   individually-correct travel times (0.01h flat vs. 0.05h real) matching
   hand-computed expected values exactly. Found and logged, not fixed (out
   of scope for a small parameter addition): `calculate_service_area` fails
   on a degenerate 1-2 segment synthetic network but works cleanly on a
   realistic one — see BUG-2026-09-05-2. `docs/TOOLS_REFERENCE.md`
   regenerated (152 tools). See point 8's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`.
34. ~~Close the taxonomy half, narrow the rollback half, of point 20 (transaction/rollback
   classification) from the 27-point review~~ — **done, 2026-09-07, on Baron's "Point 20:
   transaction taxonomy + rollback" after being asked what's left following the 2026-09-05
   reconciliation.** New `agent/tool_operations.py` hand-classifies all 156 registered tools
   into READ/CREATE/MODIFY/DELETE/PUBLISH, verified against actual source (not guessed from
   names) -- e.g. `execute_read_only_sql` is CREATE (adds the query result as a layer despite
   its "read-only" name), `run_query` is MODIFY (`setSubsetString` persists a filter),
   `execute_pyqgis_script` is DELETE as the ceiling of what arbitrary code could do. New
   `agent/transactions.py`'s `TurnTransactionLog` records every call in one `agent.run()` turn
   and offers undo for the one case it can do safely and generically: a call that added a
   genuinely new layer, detected by diffing the project's actual layer-id set before/after
   the call (not by trusting the static CREATE label) -- correctly handles
   `add_point_layer`/`add_incident_point`'s documented create-or-append ambiguity for free.
   `get_tool_operation_type`/`list_tools_by_operation_type`/`get_turn_transaction_log`/
   `undo_last_operation` expose both; the last is gated by the same `confirmed: bool = False`
   -> `PREVIEW_REQUIRED` pattern `remove_layer` already uses. **Deliberately not built, a real
   remaining gap, not silently closed:** rollback for any in-place MODIFY or for a DELETE call
   itself -- both need a real before/after snapshot taken *before* the mutating call, a larger
   piece of engineering than this session's scope, left flagged the same way as point 18's
   PLAN->EXECUTE->OBSERVE->VALIDATE->REPAIR loop or point 19's tiered allow-list question.
   48 new tests (`tests/test_tool_operations.py`, `tests/test_transactions.py`,
   `tests/test_tool_operations_tools.py`, `tests/test_transaction_tools.py`, plus 3 in
   `tests/test_agent_runner.py` covering `_execute_tool`'s new before/after wrapper). Full
   suite 1161 tests, same known baseline (the DNS-dependent
   `test_is_safe_url_accepts_public_host` and 6 FUSE-mount `PermissionError` cleanup errors in
   `test_reporting_tools.py`), 0 new failures. `docs/TOOLS_REFERENCE.md` regenerated (156
   tools). See point 20's updated entry in
   `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`. Not yet committed — awaiting
   Baron's go-ahead. **[Corrected, 2026-09-08]:** now committed as `3d5491b` (2026-09-07).
35. **Z — standing maintenance (permanent, never removed):** after every future work slice,

   update this registry — close out the finished Current Task into Level 3's log, promote
   the next queue item into Current Task, and log any new bug/finding. This item exists so
   the queue is structurally incapable of hitting zero.


---

## LEVEL 3 — FULL LOG

### 3a. Bug & troubleshooting log

Full write-ups for every ID below live in `docs/BUG_TRACKER.md` (this is the index).

| ID | Found | Fixed in | Severity | Status | One-line summary |
|---|---|---|---|---|---|
| BUG-2026-08-21-1 | 2026-08-21 | v1.2.33 | medium | fixed-verified | `osmnx` bbox element order wrong for installed version |
| BUG-2026-08-21-2 | 2026-08-21 | v1.2.33 | low | fixed-verified | Missing `scikit-learn` dependency undocumented |
| BUG-2026-08-21-3 | 2026-08-21 | v1.2.29 | medium | fixed-verified | `calculate_area`/`calculate_length` bypassed the destructive-action confirm gate |
| BUG-2026-08-21-4 | 2026-08-21 | v1.2.28 | medium | fixed-verified | Gemini API key sent as query param instead of `x-goog-api-key` header |
| BUG-2026-08-21-5 | 2026-08-21 | v1.2.34 | medium | fixed-verified | Release ZIP silently shipped 7 stray scratch/test files |
| BUG-2026-08-21-6 | 2026-08-21 | v1.4.1 | high | fixed-verified | `cartogen_ai.py` filename collided with the `cartogen_ai.core` namespace package, breaking 31 tests |
| BUG-2026-08-21-7 | 2026-08-21 | v1.4.1 | high | fixed-verified | Function-local legacy imports survived the namespace rewrite; `unittest discover` needed explicit `-t .` |
| BUG-2026-09-02-1 | 2026-09-02 | unreleased | high | fixed-unverified (2 files) / fixed-verified (rest) | 5 unscoped Qt6 enum accesses (`Qt.UserRole`, `QMessageBox.Yes/No`, `QgsMapLayer.RasterLayer`, `QgsWkbTypes.*`, `.exec_()`) found via QGIS's own migration wiki |
| BUG-2026-09-02-2 | 2026-09-02 | unreleased | critical | fixed-unverified-pending-retest | Live QGIS 4.2 crash on dock-panel open (`Qt.RightDockWidgetArea`) — sweep #1 wasn't exhaustive; 5 more flat `Qt.*` accesses found and fixed |
| BUG-2026-09-02-3 | 2026-09-02 | unreleased | critical | fixed-unverified-pending-retest | Second live crash (`QScrollArea.NoFrame`) — widened sweep to all `Q<Class>.<Attr>` patterns; 5 more fixed (incl. theme-palette extraction used by every dock/dialog) |
| BUG-2026-09-02-4 | 2026-09-02 | unreleased | high | fixed-verified (color fix) / prompt-rule-only (behavior) | Dark-theme chat text/table illegibility (`render_markdown` disconnected from theme colors); + rules 40/41 for map-visualization-default and no-guessed-year behavior |
| BUG-2026-09-02-5 | 2026-09-02 | unreleased (feature) | - | fixed-verified (logic) / fixed-unverified-pending-live-session (UI/wiring) | Adaptive self-learning system — see Level 3b, shipped as v1.5.0 |
| BUG-2026-09-02-6 | 2026-09-02 | unreleased | high | fixed-verified (landscape footer fit, live 2026-09-05) / fixed-unverified (portrait fit) / mitigation-not-guarantee (model behavior) | Fabricated Beirut security-incident briefing. Fixed with 3 layers: new rule 42, strengthened `add_point_layer`/`create_print_layout` descriptions, and a standing disclaimer footer `create_print_layout` now always adds. Landscape footer fit confirmed live via a real chat-driven print layout (screenshot evidence, real Gemini session); portrait still unconfirmed. |
| BUG-2026-09-02-7 | 2026-09-02 | unreleased | medium | fixed-verified (chat_persistence.py logic) / fixed-unverified-pending-live-session (UI) | Ollama-error bubble looked like it just happened next to a fresh Gemini reply. Root cause: restored chat history always rendered with a "now" timestamp. Fixed: `chat_persistence.py` now persists and restores each message's real timestamp. 9 new tests, all passing. |
| BUG-2026-09-04-2 | 2026-09-04 | `eee84eb` | critical | fixed-verified (both repos, 2026-09-04) | GDPR review finding F1 (`docs/GDPR_COMPLIANCE_REVIEW.docx`, written against `cartogen-ai-community`): global memory had no bulk erasure path. Added `MemoryManager.clear_global_notes()` + a "Clear Global Memory" UI button + 4 tests here; ported to `cartogen-ai-community` as that repo's `99079e3` (its own BUG-2026-09-04-1). Both repos closed. |
| BUG-2026-09-05-1 | 2026-09-05 | `a424b36` | critical | fixed-verified (the rare entry where the live-QGIS half IS verified) | Found live: `raster_tools.py`'s top-level `QgsColorRampShaderItem` import raises `ImportError` on real QGIS 4.2.2 (moved to `QgsColorRampShader.ColorRampItem`), silently setting `QGIS_AVAILABLE=False` for the whole file — all 11 raster tools degraded, invisible to the sandboxed suite. Caught by an actual live headless PyQGIS smoke-test run (`python-qgis.bat`, offscreen) after the GUI checklist proved undriveable in this environment. Resolved via the same `_qgis_enum_compat.py`-style dual-form pattern as BUG-2026-09-04-1. Re-verified live post-fix: 14/14 smoke-test categories pass, incl. 2 real network calls (HDX, STAC). Swept all 38 `agent/`/`agent/tools/` modules' `QGIS_AVAILABLE` flags live post-fix — clean, this was the only module hit. Sandboxed suite: 1025/0/7 skipped. |

**Known non-bugs — do not re-file (full detail in `docs/BUG_TRACKER.md`):**
- `test_is_safe_url_accepts_public_host` — fails in this sandbox only, DNS/network-egress limitation, not a code defect. Present in every test run this entire engagement.
- 6 `PermissionError` cleanup errors in `tests/test_reporting_tools.py` on the old FUSE-mounted tree — environment-specific, not reproduced on a native Windows filesystem run (2026-08-22: 691 tests, 0 failures, 0 errors there).
- This mount cannot `unlink` (delete) files outright, though same-filesystem rename works — see `docs/BUG_TRACKER.md` for the exact recovery sequence if a `git commit` is ever interrupted by this.

### 3b. Feature-completion log (by version)

- **unreleased (uncommitted, 2026-09-07)** — New feature, from Baron directly (not a
  27-point-review item): "animated dashboard from several views ... like the status of
  fighting groups from 2016-2026 in Syria and the control areas". Built as a generic,
  reusable "animate a multi-period status/control dataset" capability per Baron's own three
  scoping answers -- (1) capability now, placeholder/synthetic data only, no fabricated
  Syria-conflict dataset (2) both an HTML output and a QGIS-native output (3) reusable tool,
  not hardcoded to Syria. Two new tools in `agent/tools/export_tools.py`:
  `generate_temporal_dashboard` (Leaflet/Folium HTML with a hand-rolled play/pause + date
  slider that shows/hides each feature per its own `start_field`/`end_field` window --
  deliberately per-feature, not per-layer, since `folium.plugins.TimestampedGeoJson`'s
  `duration` is one global value for the whole layer and can't give two factions' areas in
  the same layer their own independent periods) and `export_temporal_animation_frames`
  (QGIS-native: loops `layer.setSubsetString()` + `canvas.saveAsImage()` per computed frame
  date, restores the original filter afterward, canvas extent left untouched between frames
  so the animation doesn't jump; returns individual PNGs plus an honest note that QGIS itself
  doesn't encode video -- an `ffmpeg` command is suggested as a follow-up). Shared pure
  helpers (`_categorical_color_map`, `_date_to_epoch_ms`, `_resolve_temporal_colors`,
  `_resolve_temporal_bounds`, `_compute_animation_frame_epochs`,
  `_temporal_subset_expression`) plus a `_resolve_popup_kwargs` extraction refactored out of
  the existing `_build_dashboard_html` so both dashboard builders share one popup-field
  implementation instead of duplicating it. Per-feature color/window baked into each
  feature's own GeoJSON properties (`__cartogen_start_ms`/`__cartogen_end_ms`/
  `__cartogen_color`) so the client-side slider JS never has to recompute a ColorBrewer/
  branca scale in JavaScript -- verified end-to-end with a real folium render: confirmed via
  `node --check` that the generated `<script>` blocks are syntactically valid, and by direct
  inspection of the rendered HTML that the injected slider script (which references the
  Leaflet `L.geoJson(...)` layer variables folium generates) sits *before* those variables'
  own `<script>` block in document order -- correctly handled by deferring the first frame
  update to `DOMContentLoaded` rather than running it inline, so it never references a
  not-yet-defined variable. Both tools classified `PUBLISH` in `agent/tool_operations.py`
  (point 20's taxonomy). 35 new tests in `tests/test_temporal_dashboard.py` (pure-logic
  helpers need no QGIS/folium mock; `_build_temporal_dashboard_html` skips if folium isn't
  installed like the existing dashboard tests; the two registered tools' QGIS-touching
  wrappers use the same `@patch(...QGIS_AVAILABLE, True)` mocking convention already
  established by `test_export_tools.py`). Full suite 1196 tests, same known baseline (1
  DNS-dependent failure, 6 FUSE `PermissionError` cleanup errors), 0 new failures.
  `docs/TOOLS_REFERENCE.md` regenerated (158 tools). Real data was never fabricated anywhere
  in this feature or its tests -- all Syria-flavored fixtures use generic placeholder names
  ("Faction A/B/C") and made-up dates, consistent with rule 42/BUG-2026-09-02-6's standing
  anti-fabrication principle; real control-area data, if/when Baron supplies or points the
  agent at it, flows into these same tools unchanged. Not yet committed — awaiting Baron's
  go-ahead. **[Corrected, 2026-09-08]:** now committed as `609ee10` (2026-09-08, covers both phases).
- **unreleased (uncommitted, 2026-09-07, phase 2)** — Same feature, extended same day after
  Baron shared a screenshot of a real, live Microsoft Power BI Syria-conflict dashboard as a
  reference ("is something like this") and asked (via two follow-up questions) for all four
  of: point markers colored by category, a location filter panel, a synced Chart.js trend
  chart, and a date-range filter alongside the existing play/pause animation --
  `_build_temporal_dashboard_html` gained `location_field`/`marker_radius` per-layer options,
  a `folium.CircleMarker`-based point renderer (verified live that folium's generated
  `pointToLayer` correctly merges `style_function` output into marker options via
  `Object.assign`, so per-feature coloring already in place for polygons just works for
  points too), an HTML checkbox location-filter panel, a Chart.js v4 (`4.5.1` via CDN)
  stacked-bar trend chart (`_build_trend_chart_data` buckets each feature into the calendar
  month its `start_field` falls in, per-category, optionally split `by_location`; category
  colors assigned in *sorted*, not first-seen, order so map and chart legends match for the
  common single-layer case), and two plain range-input sliders for the date-range filter
  (chosen over a dual-handle widget to avoid a new JS dependency; the play-slider's own
  bounds stay fixed but its playhead clamps into the selected range, and the play-loop wraps
  within it once a range is set). Security fix found and applied during this work: added
  `_json_for_inline_script()` (escapes literal `</` to `<\/`) and used it for both new
  inline-JS data embeddings (`__cartogenChartData`/`__cartogenCategoryColors`), closing a
  real script-tag-breakout gap that plain `json.dumps()` of caller-controlled location/
  category names would otherwise have left open; `json.dumps`'s `ensure_ascii=True` default
  was confirmed (live) to already escape U+2028/U+2029 separately, so nothing extra was
  needed there. Bug fix found and applied: `layer.get("marker_radius", 6)` silently returned
  `None` instead of the intended default whenever the wrapper's prepared dict held an
  explicit `"marker_radius": None` (always true when a caller omits the field) -- changed to
  `layer.get("marker_radius") or 6`. 21 new tests in `tests/test_temporal_dashboard.py`
  (56 total in that file). Full suite re-verified after all phase-2 changes: 1217 tests,
  same known baseline (1 DNS-dependent failure, 6 FUSE `PermissionError` cleanup errors), 0
  new failures; pyflakes clean (same 2 pre-existing/accepted warnings). `generate_temporal_
  dashboard`'s registered description/schema updated to document all four additions;
  `docs/TOOLS_REFERENCE.md` regenerated. Still placeholder-data-only, per the standing
  anti-fabrication principle and Baron's own "capability now, data later" scoping from
  earlier the same day -- his "eventually load real data like this" answer was about future
  intent, not a change to that scope. Not yet committed -- this is materially different code
  from phase 1's own not-yet-approved commit and needs its own fresh go-ahead. **[Corrected, 2026-09-08]:** now committed as `609ee10` (2026-09-08, covers both phases).
- **unreleased (uncommitted, 2026-09-05)** — Point 12 of the 27-point review, style-library
  reuse: new `save_layer_style`/`load_layer_style` tools in `agent/tools/styling_tools.py`,
  using real `QgsMapLayer.saveNamedStyle()`/`loadNamedStyle()` against a real `.qml` file, plus
  a `_derive_style_path` helper reusing point 17's provenance-sidecar path convention (beside
  the layer's own source when one resolves, Desktop fallback otherwise). Scope kept to the
  literal named gap (`.qml` save/load) — the orphaned `symbology-style.db` at the repo root
  (confirmed this session: a real, populated `QgsStyle` database, 116 symbols + 35 color
  ramps) would let the agent browse/apply named symbols from a library, a related but separate
  capability, left unbuilt. 13 new tests. **Live-verified**, not just unit-tested with mocks: a
  real headless PyQGIS session against QGIS 4.2.2 applied a real 5-class graduated style to a
  real layer, saved it to a real `.qml` file via `save_layer_style`, loaded it onto a fresh
  layer via `load_layer_style`, and confirmed the renderer type and class structure
  round-tripped correctly — the same headless-session technique BUG-2026-09-05-1 used. Full
  suite 1038 tests, same known baseline, 0 new failures. `docs/TOOLS_REFERENCE.md` regenerated
  (143 tools). Not yet committed. **[Corrected, 2026-09-08]:** now committed as `cddfe0e` (2026-09-05).
- **unreleased (uncommitted, 2026-09-04)** — Auth-system diagnostic, from a live bug report:
  Baron hit `authManager().isDisabled()` on a real QGIS 4.2 session (screenshots: the "Key
  stored without encryption" fallback warning firing, and Options -> Authentication showing
  "Authentication system is DISABLED"), plus a separate, unrelated Gemini API 403
  `PERMISSION_DENIED` ("Your project has been denied access") on that same session -- the
  latter is a Google-account/API-key-side issue (billing/API-enablement/project suspension on
  Baron's own Google Cloud project), not a QGIS or plugin defect, and needs checking on
  Google's side, not a code fix. For the auth-disabled half: confirmed via WebSearch (not
  assumed) two real, documented root causes -- a QGIS 3.40.4+ regression where a network
  proxy's `authcfg` reference disables the whole auth system at startup
  (github.com/qgis/QGIS/issues/61043), and the long-standing missing/broken QCA OpenSSL
  backend (`qca-ossl`/`qca-qt6-ossl`, e.g. Red Hat bug 1396818). Neither is fixable from
  inside this plugin's own package -- `plugin_dependencies=qpip` (metadata.txt) only installs
  Python packages from `requirements.txt`, with no mechanism to touch QGIS's native Qt/QCA
  libraries or its proxy settings, so "add the dependency during plugin installation" isn't
  literally possible here; both fixes happen in QGIS itself. New `CredentialManager.
  auth_system_status()`/`get_auth_system_diagnostic_message()` (`agent/auth.py`) report the
  disabled state and both documented causes+fixes with a machine-readable status dict for
  automated testing; `ui/settings_dialog.py`'s existing plaintext-fallback warning now appends
  that diagnostic instead of leaving the fallback as a generic, unexplained "wasn't available"
  message. QGIS exposes no machine-readable reason for `isDisabled()`, so this reports THAT
  it's disabled and lists the known causes, not which one applies on a given machine -- an
  honest scope limit, not a guess dressed up as a diagnosis. 5 new tests in
  `tests/test_auth_and_deps.py`. Full suite 887 tests, same known baseline, 0 new failures.
  `agent/auth.py` and `ui/settings_dialog.py` both already carry the held, unrelated account-
  feature diff (Level 2 queue item 5) -- this change lands on top of that in both files, so
  committing it separately (as intended, since the account feature stays held) will need the
  same per-file blob-staging this project has used before for exactly this situation, not a
  plain `git add`. Not yet committed — awaiting Baron's go-ahead. **[Corrected, 2026-09-08]:** now committed as `c9a7a82` (2026-09-04).
- **committed, 2026-09-04 (`eee84eb`)** — Closed GDPR compliance review finding F1 (global memory had no bulk erasure path). Added `MemoryManager.clear_global_notes()` (symmetric with `clear_project_notes()`) and a "Clear Global Memory" confirm-gated button in `ui/tasks_tab_widget.py`, next to the existing per-project control. 4 new tests in `tests/test_memory_and_tasks.py`, all 16 tests in that file passing. Full writeup: BUG-2026-09-04-2. Committed on Baron's explicit go-ahead, scoped to exactly the 3 files touched — no other uncommitted work included. Cross-repo reconciliation with the review document (`cartogen-ai-community`) is still open.
- **unreleased (uncommitted, 2026-09-04)** — TASK-0008 (Level 2 queue item 7): closed the
  ~15-site unscoped-native-QGIS-enum risk via a runtime dual-form resolver instead of a guessed
  blanket rewrite. New `agent/tools/_qgis_enum_compat.py`'s `resolve_qgis_enum(cls,
  nested_enum_name, member_name)` tries the QGIS 4.x/Qt6 scoped form (e.g. `cls.Mode.Jenks`),
  falls back to the QGIS 3.x/Qt5 flat form (`cls.Jenks`), returns `None` if neither resolves.
  Applied at all 9 originally-flagged classes: `QgsGraduatedSymbolRenderer` (`styling_tools.py`,
  `Mode`), `QgsColorRampShader` (`raster_tools.py`, `Type`), `QgsContrastEnhancement`
  (`raster_tools.py`, `ContrastEnhancementAlgorithm`), `QgsRasterBandStats` (`raster_tools.py`,
  `Stat`), `QgsTask` (`agent/task_runner.py`, `Flag`), `QgsUnitTypes` (`layout_tools.py`, `
  LayoutUnit`/`DistanceUnit`, 18 call sites collapsed to 2 module-level constants),
  `QgsVectorFileWriter` (`export_tools.py`, `WriterError`), `QgsTextBackgroundSettings`
  (`humanitarian_tools.py`, `ShapeType`); `QgsZonalStatistics` was found already using an
  identical hand-rolled version of this pattern from an earlier round. 5 new tests
  (`tests/test_qgis_enum_compat.py`), full suite 753/0/0/1. Full writeup: BUG-2026-09-04-1.
  **Not yet committed.** **[Corrected, 2026-09-08]:** now committed (part of `d8113b8`, 2026-09-05).
- **unreleased (uncommitted, 2026-09-04)** — Both Section IV/V gaps from the 2026-09-03
  humanitarian-standards analysis (below) implemented, per Baron's same-day decisions.
  `optimize_delivery_route` (`agent/tools/logistics_tools.py`) now takes an optional
  `road_network_layer` and, when given, chains `native:shortestpathpointtopoint` across the
  computed stop order and merges the segments into a real road-snapped route line added to the
  project (`_build_road_snapped_route`); without it, the result now carries an explicit
  `warning` telling the caller not to render the stop order as a route. `add_incident_point`/
  `add_point_layer` (`agent/tools/humanitarian_tools.py`) gained optional ACLED-style
  `event_type`/`sub_event_type` and IMSMA/IMAS-style `hazard_type`/`contamination_status`
  fields, layered on top of the existing freeform `severity`/`category`, validated (advisory,
  not blocking — an unrecognized value comes back as `coding_warnings`, not a rejected point)
  via the new `_validate_incident_coding`. 51 new tests across
  `tests/test_logistics_tools.py` (extended) and `tests/test_humanitarian_incident_coding.py`
  (new, 15 tests) — full suite 748/0/0/1, unchanged baseline plus these additions.
  `docs/TOOLS_REFERENCE.md` regenerated. Gap closure recorded inline in
  `docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md` Sections IV/V. **Not yet committed** — awaiting
  Baron's explicit go-ahead per this registry's own governance rule. **[Corrected, 2026-09-08]:** now committed (part of `d8113b8`, 2026-09-05).
- **unreleased (uncommitted, 2026-09-03)** — `docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md`:
  captured the humanitarian-mapping compliance framework Baron supplied that day verbatim,
  plus a section-by-section gap analysis checked directly against the live tool code (not
  memory). Net finding: P-codes/CODs, severity-index/choropleth mapping, and the mandatory
  title/north-arrow/scale-bar/legend layout elements are already substantially met; a
  structured metadata block (map period, sources/versioning, projection/CRS, sensitivity
  disclaimer) is the clearest gap and is queued alongside the live QGIS smoke test rather
  than built blind on top of the already-tight, unverified portrait print-layout geometry;
  two further gaps (non-road-snapped route rendering risk in `optimize_delivery_route`, and
  no controlled reporting-code vocabulary for incident `category`/`severity`) are queued
  behind a design decision from Baron rather than guessed at. See Level 2 queue items 2 and 5.
- **v1.5.0** — Adaptive self-learning system: passive provider-preference detection,
  correction-rule learning from user feedback phrasing, usage-pattern counters, and a
  visible/editable "Learned Preferences & Rules" panel. 17 new tests
  (`tests/test_learning.py`). Full design rationale and scoping decisions in
  `docs/BUG_TRACKER.md` BUG-2026-09-02-5.
- **v1.4.4 (source tree, same-day as v1.5.0's cut)** — QGIS 4.2/Qt6 enum-scoping fixes
  across three live-crash rounds (dock panel open, scroll-area frames, dialog buttons,
  password fields, theme-palette extraction); dark-theme chat/table color fix; system-prompt
  rules 40 (default to a real map layer for mappable results) and 41 (never guess a
  year/date parameter).
- **v1.4.3** — UI terminology and navigation polish.
- **v1.4.2** — `dock_widget.py` split into per-tab widgets (chat/tasks/help), per
  `docs/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md`.
- **v1.4.1** — Namespace-package architecture (`cartogen_ai.core`) established; fixed the
  module-collision bug that had been silently breaking 31 tests.
- **v1.0.0 to v1.3.0** — Core agent build-out: 130+ PyQGIS tools across vector/raster/
  humanitarian/logistics/styling/monitoring/reporting domains, provider abstraction
  (OpenRouter/Gemini/Ollama/OpenAI/Claude/Cartogen-gateway), task planning, spatial memory,
  prompt refinement, workflow scheduling, SSRF-guarded web tools. Full per-version detail in
  `CHANGELOG.md`.
- **Pre-1.0** — Early prototype phase (v0.1.2-v0.3.1).

*(The `web-platform`/Phase 1 feature history — Directus auth, PostGIS analysis jobs, PDF
export, billing — was tracked in this same `docs/OPERATIONS_LOG.md` before the 2026-08-27
extraction to a standalone repo. It's a separate workstream from this plugin from that point
forward; see the `cartogen web` Claude Project for its own audit docs.)*

### 3c. Version-control log

- **136 commits total** on `main`, 2026-08-17 to 2026-09-02 (`git log --reverse` for the full
  list — not duplicated here). The middle third of that range (2026-08-24 to 2026-08-26,
  `feat(phase-1): ...`/`fix(phase-1): ...` commits) is the web platform's history, extracted
  out at `ced7fc9` ("chore: extract web-platform to a standalone top-level repo",
  2026-08-27) — still present in this repo's history for provenance, not in its current tree.
- **12 tags**, oldest to newest: `commercial-v0.2.0` ... `commercial-v0.2.8` (2026-08-23,
  commercial-service-side), `commercial-plugin-v1.4.3`, `commercial-plugin-v1.4.4`
  (2026-08-23, both pushed with real GitHub Release objects), `commercial-plugin-v1.5.0`
  (2026-09-02, **local only** — see Level 1's push blocker).
- **Latest commit:** `cd7d06a6e894bcd26c0f43913ac4f2dfaa035147`, 2026-09-02, "feat(agent): add
  adaptive self-learning system; cut v1.5.0 release" — 11 files changed, 667 insertions(+),
  7 deletions(-).
- **Working-tree state beyond `cd7d06a`:** pre-existing, unrelated, uncommitted changes for
  the in-progress "account" feature (see Level 2 queue item 4) plus routine scratch-file
  deletions and an untracked `docs/HUMANITARIAN_MAPPING_TASK_REFERENCE.md` — none authored
  by this engagement, all deliberately left alone.

### 3d. Canonical source-of-truth map

| Category | Full detail lives in |
|---|---|
| Every bug ever found/fixed, pre-2026-08-21 | `CHANGELOG.md` (per-version entries) |
| Every bug found/fixed, 2026-08-21 onward | `docs/BUG_TRACKER.md` |
| Every feature/release decision + rationale | `docs/OPERATIONS_LOG.md` |
| Every version's full changelog text | `CHANGELOG.md` |
| Release process rules | `docs/RELEASE_GOVERNANCE.md` |
| Manual QGIS smoke-test checklist | `docs/RELEASE_SMOKE_TEST.md` |
| Commit-by-commit history | `git log` (this repo) |
| This registry | `docs/MASTER_TASK_REGISTRY.md` (this file) — the index over all of the above |
