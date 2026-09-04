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

### Current state (as of 2026-09-02)

| | |
|---|---|
| Source tree version (`metadata.txt`/`pyproject.toml`) | **1.5.0** |
| Last built release ZIP | `dist/cartogen_ai_v1.5.0.zip` (693,475 bytes, SHA-256 `de087c39d817f0d7ab8fb146cf8dcd7cb3ca9ed3a33bf63a0508d8ec8db6cdd9`) — delivered to Baron in-session |
| Last local commit | `eee84eb` — "fix: add clear_global_notes() to close GDPR review finding F1" (on top of `2624313` "fix: chat-history restore timestamps + fabrication-safety mitigation", on top of the `cd7d06a` v1.5.0 release commit) |
| Last local tag | `commercial-plugin-v1.5.0` (on `cd7d06a`) |
| Pushed to GitHub? | **No** — blocked. This session's device-bridge shell has no GitHub credentials configured (`git push` fails with `could not read Password for 'https://cartogenai-glitch@github.com'`) and no `gh` CLI is installed. Pushing `main` and the tag is Baron's own action. |
| GitHub Release object created? | **No** — same blocker; also Baron's own action (via `gh` or the GitHub web UI) once the tag is pushed. |
| Working tree clean otherwise? | No — several **pre-existing, unrelated, deliberately untouched** changes sit uncommitted (see Level 2, queue item on the "account" feature). None of them are part of the v1.5.0 release. |

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
| **1.5.0** | 2026-09-02 | Adaptive self-learning system (4 mechanisms) + retroactively documents the QGIS 4.2/Qt6 fixes shipped under 1.4.4 without a version bump |
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
4. **Push `cd7d06a`/`2624313` + tag `commercial-plugin-v1.5.0` to GitHub, and create the
   GitHub Release object.** Blocked on Baron's own authenticated push — this session's
   device-bridge has no GitHub credentials or `gh` CLI, and credential handling is off-limits
   to Hermes regardless. Exact commands are on file from the original release-cut turn.
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
10. **Z — standing maintenance (permanent, never removed):** after every future work slice,
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
| BUG-2026-09-02-6 | 2026-09-02 | unreleased | high | fixed-unverified-pending-live-session (layout fit / model behavior) / fixed-verified (description text present) | Fabricated Beirut security-incident briefing. Fixed with 3 layers: new rule 42, strengthened `add_point_layer`/`create_print_layout` descriptions, and a standing disclaimer footer `create_print_layout` now always adds. Mitigation, not a guarantee. |
| BUG-2026-09-02-7 | 2026-09-02 | unreleased | medium | fixed-verified (chat_persistence.py logic) / fixed-unverified-pending-live-session (UI) | Ollama-error bubble looked like it just happened next to a fresh Gemini reply. Root cause: restored chat history always rendered with a "now" timestamp. Fixed: `chat_persistence.py` now persists and restores each message's real timestamp. 9 new tests, all passing. |
| BUG-2026-09-04-2 | 2026-09-04 | `eee84eb` | critical | fixed-verified (both repos, 2026-09-04) | GDPR review finding F1 (`docs/GDPR_COMPLIANCE_REVIEW.docx`, written against `cartogen-ai-community`): global memory had no bulk erasure path. Added `MemoryManager.clear_global_notes()` + a "Clear Global Memory" UI button + 4 tests here; ported to `cartogen-ai-community` as that repo's `99079e3` (its own BUG-2026-09-04-1). Both repos closed. |

**Known non-bugs — do not re-file (full detail in `docs/BUG_TRACKER.md`):**
- `test_is_safe_url_accepts_public_host` — fails in this sandbox only, DNS/network-egress limitation, not a code defect. Present in every test run this entire engagement.
- 6 `PermissionError` cleanup errors in `tests/test_reporting_tools.py` on the old FUSE-mounted tree — environment-specific, not reproduced on a native Windows filesystem run (2026-08-22: 691 tests, 0 failures, 0 errors there).
- This mount cannot `unlink` (delete) files outright, though same-filesystem rename works — see `docs/BUG_TRACKER.md` for the exact recovery sequence if a `git commit` is ever interrupted by this.

### 3b. Feature-completion log (by version)

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
  **Not yet committed.**
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
  Baron's explicit go-ahead per this registry's own governance rule.
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
