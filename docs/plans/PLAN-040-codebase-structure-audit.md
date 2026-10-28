# PLAN-040: whole-code-base structure audit and staged reorganisation (master list AR-6)

Status: in progress

## Goal
Reorganise the code so it is easier to change safely, without breaking finished work. The owner asked on 2026-10-28 for "reorganizing everything again" with a self audit of the whole code base. This page is the audit and a staged proposal. Every number below is reproducible with `python tools/structure_audit.py` (stdlib only, read-only; it reads `src/` and cannot see dynamic imports or imports made from the plugin root, so `plugin_main.py` imports are not counted).

## What the audit measured (2026-10-28, main at 75e719c)

| Measure | Result |
|---|---|
| Size | 229 source files, 72,748 lines. `core/agent/tools/` is 108 files and 42,810 lines, 59% of the code |
| Largest files | logistics_tools 3,558; export_tools 2,656; vector_tools 2,514; humanitarian_tools 2,264; agent_orchestrator 2,078; chat_tab_widget 2,072; raster_tools 1,940 |
| Import edges | 541 at import time, 256 inside functions (deferred) |
| Import cycles at import time | **none**. (The first version of this audit reported a 30-module cycle; that was a counting error in `tools/structure_audit.py`, which treated `from . import some_module` as a dependency on the package, and the package imports every tool. Corrected 2026-10-28.) |
| Cycles counting deferred imports | three small groups: **13 modules** (the styling cluster: `vector_tools`, `raster_tools`, `styling_tools`, `humanitarian_style`, `output_style`, `logistics_tools`, `export_tools`, `layout_style` and five more), **5** (`provenance`, `dataset_status` and the provenance, QA and dataset-status tools) and **4** (`agent_orchestrator`, `prompts`, `tools`, `data_export_tools`) |
| Deferred imports that close those groups | 27 (24 in the 13-module styling cluster, 2 in the provenance group, 1 in the orchestrator group); the most-imported targets are `humanitarian_style`, `raster_tools`, `output_style`, `vector_tools` |
| Layering as drawn in `CLAUDE.md` | not enforced. `tests/test_architecture_boundaries.py` only checks that names are exported, not which way imports point. Measured inversions: 17 edges in all: providers import `core.agent.model_selector` and `cancel_signal` (8, with `core/net.py`); `core/models` import `settings_keys` (4), `tool_operations` (1) and, through deferred imports, tool modules (2); `core/validators` import `tools._chunked` (2) |
| Duplicated helpers | 30 private helpers are defined in two or more modules. `_find_layer_by_name` is defined **20 times with 3 distinct bodies** (16 identical copies, 3 in corridor, impedance and processing_allowlist tools, 1 in `representation/applier.py`); `_layer` 14 times (4 bodies); `_sanitize_filename` 3 identical; `_redact` 3 (2 bodies) |
| Dead code | `vulture` at 80% confidence finds two unused variables. At 60% it lists about 400 items, almost all tools registered by decorator or Qt slots (false positives). One real finding: `core/exceptions.py` defines `CartogenError`, `ApiError`, `SpatialValidationError`, `SecuritySandboxError`, `TaskExecutionError`, which production code never raises or catches (one test imports it), while `CLAUDE.md` lists it as the exception hierarchy |
| Modules no test names | 9: `providers/_search_cache`, `ui/chat_view_presenter`, `ui/onboarding_dialog`, `ui/chat_input_controller`, `ui/help_tab_widget`, `agent/history_manager`, `agent/tool_dispatcher`, `tools/_sensitivity_notes`, `tools/map_tools` (a name match, not a coverage measure) |
| Broad `except Exception` | 526 in `src/` (the tracked baseline is in master list DEF-8) |
| Docs | 87 top-level `.md` files, 59 of them dated snapshots, plus 40 plans and 23 archived; `IMPLEMENTATION_TRACKER.md` is 2,746 lines |
| Cost of moving a tool file | 224 test files name tool module paths, 2,053 path references in tests (1,417 of them `patch()` targets), 134 ledger source paths, 5 docs |

The tools package is also flat on purpose-by-name rather than by folder: 108 files with 69 different first words (`layout_*` 12, `jiaf_*` 5, `data_*`, `project_*`, `raster_*`, `symbology_*` 4 each).

## What is fine
- The `agent` core is already split into orchestrator, dispatcher, usage tracker and history manager.
- `ui/chat_formatting.py` and `ui/icons.py` keep their Qt-free halves, which is what makes them testable.
- There are no `print` debris or large tracked binaries; `cartogen_ai.zip` and `dist/` at the repo root are untracked build output.
- Only 15 TODO/FIXME markers in `src/`.

## Scope
This plan covers the audit (done) and the stages below, each its own PR, behaviour-neutral, full CI, mergeable alone. No code has been moved yet; the owner chooses the stages (open questions).

| Stage | Change | Risk | Why it earns its place |
|---|---|---|---|
| 0 | Write the **intended** import direction into a test: a layer rule set plus an allowlist of today's violations that may only shrink | none (test only) | Without it every later stage can be undone by the next change. Needs the owner to confirm the intended direction (see questions) |
| 1 | **Evaluated and rejected (2026-10-28).** The 19 tool-module copies of `_find_layer_by_name` are the same 7 lines, but 583 tests patch `QGIS_AVAILABLE` or `QgsProject` on individual tool modules; a shared helper would read its own module's globals and silently bypass those patches. The copies are a test seam. A one-line wrapper per module would save about 5 lines each for a real chance of breaking patches | n/a | the benefit is cosmetic; the risk is not |
| 2 | Break the 13-module styling cluster: move what `humanitarian_style`, `raster_tools`, `output_style` and `vector_tools` export to many callers into leaf helper modules, then delete the 27 deferred imports that exist only for the cycles | medium | import order stops mattering; the cycles can no longer grow |
| 3 | Fix the inversions: providers stop importing `core.agent` (move `model_selector` and `cancel_signal` to a shared lower module); `core/representation` and `core/services` stop importing tool modules | medium | gives `infrastructure` a real "no upward imports" rule |
| 4 | Remove or use `core/exceptions.py`: either delete the unused hierarchy and fix `CLAUDE.md`, or adopt it at the few places that raise plain `Exception` today | low | the documentation and the code agree |
| 5 | Split the four largest tool files and the two largest UI/agent files along the seams the code already has (comment-headed sections), keeping the public names importable from the old module | medium | 3,558-line files are where mistakes hide |
| 6 | Docs: move the 59 dated snapshots into `docs/archive/` with an index, prune `IMPLEMENTATION_TRACKER.md` to open items | none | the working agreement says plans and ledger are the record; the rest is noise |

## Not recommended: moving tool files into domain subpackages
This is what "reorganise everything" would most naturally mean, and it is the most expensive change on the table: 224 test files, 2,053 path references, 1,417 `patch()` targets, 134 ledger paths and the registry import order all change, for a benefit (folders by topic) that a one-page index of the 108 tools gives for almost nothing. If the owner wants it anyway, do it last, as a mechanical rename that keeps old import paths working through thin re-export modules, one domain at a time, with the tools-reference generator and ledger guard as the checks.

## Open questions (owner)
1. **Intended import direction.** Proposed rule: `ui` may import `agent`; `agent` may import `tools`; `tools` may import `core-support` and `infrastructure`; `core-support` and `infrastructure` may not import `agent`, `tools` or `ui`. Today's `representation.applier -> tools` would break the rule: is that package meant to sit above the tools (then it belongs under `agent`) or below them? Confirm or change before Stage 0.
2. Which stages to run, and in what order. Recommended: 0, 1, 4, 6 first (no or low risk), then 2 and 3, then 5.
3. Whether subpackage moves (above) are wanted at all.

## Acceptance
- `python tools/structure_audit.py` reports fewer cycles, fewer duplicated helpers and no layer inversions than the table above, stage by stage.
- Offline suite, live CI, ruff, ledger guard and master list stay green on every stage; no tool name, argument or reply changes (the tool-schema snapshot test is the proof).
- Nothing is verified by a person: a reorganisation proves nothing about behaviour in a real QGIS session, so the hand rows stay as they are.

## Guard tests
`tests/test_architecture_boundaries.py` (names exported, today); the import-direction test of Stage 0; `tools/snapshot_tool_schema.py` for "no tool changed".

## Rollback
Each stage is one squash-merged PR; revert it. No stored data format changes.

## Status log
- 2026-10-28: audit done and this plan written (status stays planned: no code moved, waiting on the owner to choose stages) at the owner's request; `tools/structure_audit.py` added so the numbers can be re-run. No code moved. Waiting on the owner's answers above.
- 2026-10-28: correction. The first version of the findings reported an import-time cycle of 30 modules and a 90-module group. Both came from `tools/structure_audit.py` counting `from . import some_module` as an edge to the package. Fixed in the script; the findings and Stage 2 above now show the corrected numbers (no import-time cycles; groups of 13, 5 and 4 through deferred imports). Stage 1 was evaluated and rejected (see its row).
- 2026-10-28: stages 0 and 3 (first part) built. `tests/test_import_architecture.py` is the ratchet: no import-time cycles, a snapshot of the 22 modules that take part in cycles only through lazy imports (no module may join, none may stay listed after leaving), and layer rules with 4 listed exceptions that may only shrink. `cancel_signal`, `model_selector` and `tool_operations` (stdlib-only leaves) moved from `core/agent/` to `core/`; the old paths stay as `sys.modules` aliases to the same module objects (a test proves they are the same objects, so state and patches behave as before). Violations went from 17 edges to 4. A mutation check showed the guard failing on a wrong-direction import and on a new cycle. Offline only; not tried in QGIS, though CI runs the live suite on this change. Left: the 4 listed edges (models -> tool modules through lazy imports; validators -> `tools._chunked`), stage 2 (the 13-module styling cluster), stages 4 to 6.
- 2026-10-28: audit-fixes PR: plugin_main no longer keeps the raw API key as its agent-change marker (SHA-256 fingerprint via auth.credential_fingerprint); dead core/exceptions.py (no production importer) removed. CI-only.
- 2026-10-28: stage 3 finished. `_background_processing` and `_chunked` moved to core/ (old paths are aliases); `models.dataset_status` no longer imports tools: the tools register their check runners (`register_check_runner`). `KNOWN_VIOLATIONS` is empty; 3 more modules left the lazy-cycle set. CI-only.
