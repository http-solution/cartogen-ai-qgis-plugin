# Contributing to Cartogen AI

This is a short document about *how* this codebase is written, not a generic PR-process guide. It
exists because `docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md` §4 named two habits as this
project's single strongest asset — stronger than any individual feature — and flagged them as
fragile precisely because they're emergent conventions, not enforced rules. Writing them down is
the cheapest possible insurance against losing them as more people touch this code.

## 1. Comments explain *why*, not *what*

A comment that restates the code adds nothing. A comment that explains the failure mode the code is
defending against is worth its weight — it's the difference between a future contributor "fixing" a
workaround back into the bug it was written to avoid, and that contributor understanding why the
workaround exists before touching it.

Concrete examples already in this codebase, worth reading before writing your own:

- `ui/canvas_highlight.py`: *"QgsHighlight has no overload that accepts a raw QgsRectangle — only
  QgsGeometry or QgsFeature. Passing the rectangle directly raised 'arguments did not match any
  overloaded call' on every single highlight attempt (confirmed live)."*
- `agent/providers/gemini.py`: *"a live user hit a 404 'no longer available to new users' on
  gemini-2.5-pro even though Google's own docs still listed it as stable at the time."*
- `ui/dock_widget.py`: *"QTabWidget/QStackedWidget sizes the WHOLE dock to its tallest tab's natural
  size hint, not just the currently visible tab... forcing the entire QGIS window taller than the
  screen."*

Each of these cites a real, specific, previously-hit failure — not a hypothetical, not "just in
case." When you fix a real bug, write the comment the way these are written: what broke, how you
know it broke (a stack trace, a live user report, a test that failed), and why the fix works. When
you're tempted to write a comment that just describes what the next line does, skip it — the code
already says that.

## 2. State what's shipped, roadmap, and unverified — honestly, in the code itself

This project's docs are full of sentences like "not yet built," "roadmap only," "unverified against
a live response in this environment." That's not hedging — it's the reason `docs/archive/STATUS_REVIEW_2026-08-20.md`
can be trusted as an accurate picture of the product instead of aspirational marketing that quietly
drifted away from the real codebase.

This discipline belongs in code, not just docs. `agent/providers/cartogen.py`'s module docstring is
the clearest recent example — it states plainly that it's a stub, lists exactly what it is *not*
wired into, and says explicitly not to extend it until specific preconditions are met. That's a
higher bar than most projects hold internal comments to, and it's the right bar here: a comment or
docstring that overstates what a piece of code does is actively worse than no comment at all, because
it's the thing a future contributor (or a future AI-assisted session) will trust without re-checking.

**In practice:**
- If something is a stub, a prototype, or unverified against a live/real environment, say so in the
  code that implements it, not only in a separate doc someone might not read.
- If you're not sure something works — because it can't be tested in this sandbox, or you haven't
  run it against a real API/QGIS session — say that too, specifically (see
  `docs/RELEASE_SMOKE_TEST.md` for the live-verification gap this can't close alone).
- Don't let a docs file's status label go stale. When you ship something a doc previously called
  "not yet built," update that doc in the same change — this project's own review rounds have
  repeatedly found stale status labels as real, fixable gaps precisely because this step gets
  skipped under time pressure.

## 3. When you find a gap, flag it — don't silently fix it if it's a judgment call

Several review rounds in this project's history found real issues and *did not* fix them
unilaterally — redundant tool registrations, a missing raster styling tool, an inconsistent auth
mechanism in a provider client — because the fix involved a product or design tradeoff, not just a
mechanical correction. Mechanical, low-risk fixes (a wrong error message, a missing retry) get fixed
directly. Anything that changes behavior a user or integration might depend on, or that this
environment can't verify live, gets flagged with a clear recommendation instead of applied silently.
If you're not sure which category something falls into, treat it as the second one.

## 4. Testing conventions

- Every module that touches `qgis.core`/PyQGIS degrades gracefully outside a real QGIS process via
  its own `QGIS_AVAILABLE` guard, so the test suite runs without a QGIS installation
  (`python -m unittest discover -s tests -t . -p "test_*.py"` — the `-t .` matters, see
  `CLAUDE.md`'s "Running things" section). New tool modules should follow the same pattern — see
  any file in `src/cartogen_ai/core/agent/tools/` for the shape.
- Pure-Python logic (chat formatting, color derivation, tool routing) is deliberately kept free of
  Qt/QGIS imports specifically so it's directly unit-testable — see
  `src/cartogen_ai/core/ui/chat_formatting.py`'s own docstring for why it's structured that way
  relative to `src/cartogen_ai/core/ui/dock_widget.py`.
- A structural bug this project actually shipped and caught (a duplicate dict key silently
  discarding `ToolRouter` aliases, with no error at parse or runtime) is now guarded against by an
  `ast`-based static test (`tests/test_tool_router.py`'s `TestToolAliasesNoDuplicateKeys`). If you
  add a similarly "the interpreter won't warn you" class of footgun, consider whether a structural
  test like this one is warranted, not just a behavioral one.

## 5. Single tree, one public codebase

This repo is a single source tree — there's no second copy to keep in sync (an earlier version of
this project maintained a dual-tree setup; see `CHANGELOG.md`'s `[1.4.0]` entry). It's a single,
open-source GPL v2 codebase. **Do not add tier-check or license-gating logic here** — that's out
of scope for this repo by design.

## 6. Release tag naming: `cartogen-ai-v<version>`, not `commercial-plugin-v<version>`

Every release tag through `commercial-plugin-v1.16.0-rc6` used the `commercial-plugin-` prefix.
That name described the intended *distribution channel* (services-based monetization — support,
hosting, custom integration — rather than code licensing; see `CHANGELOG_ARCHIVE.md`'s
`[1.0.0-beta]` entry, 2026-08-11), not the license: this codebase has been GPL v2 since that first
tag. Read on a repo whose own `LICENSE` says GPL v2, a tag literally named `commercial-plugin-`
reads as a proprietary-licensing signal it was never meant to send.

**Decided 2026-09-27 by Alaa: new tags use `cartogen-ai-v<version>` going forward** (e.g.
`cartogen-ai-v1.17.0`, matching `metadata.txt`'s `version=` value). Existing `commercial-plugin-v*`
tags are untouched — they're referenced by already-published GitHub Releases and by this repo's own
historical record (`CHANGELOG.md`'s past entries, `docs/IMPLEMENTATION_TRACKER.md`'s dated journal
entries); per §7 below, that history isn't rewritten. Don't retag or rename old releases to match;
just use the new prefix for the next one.

## 7. Frozen historical docs

`docs/archive/CARTOGEN_AI_FEATURE_LIST.md`, `docs/archive/CARTOGEN_AI_PRD.md`,
`docs/archive/IMPLEMENTATION_TASK_LIST.md`, `CHANGELOG.md`'s past entries, and dated review/
audit/spec docs (filenames ending in a date, e.g. `docs/archive/STATUS_REVIEW_2026-08-20.md`)
are deliberately left untouched after the fact — they're a
historical record, not living documentation. If something in one of them is now wrong or
superseded, add a new dated doc or a `docs/IMPLEMENTATION_TRACKER.md` entry that supersedes it;
don't edit the old one to match current reality. This includes not "fixing" old identifier names
in them (e.g. `QgisAiAgent`) even after a rebrand — they're accurate to what was true when written.

## 8. Releasing: every version bump updates the user-facing text

When you change `version=` in `metadata.txt`, update ALL of these in the same change -- `tests/test_release_docs_in_sync.py` fails until they agree:

1. `metadata.txt`: prepend a `changelog=` block for the new version (never edit older blocks). **Never write the `%` symbol anywhere in this file; write "percent"** -- plugins.qgis.org parses it with Python's ConfigParser and rejects the upload (`tests/test_metadata_parses.py` and `plugin_upload.py` both check; 2026-10-10 the directory refused rc24 because of a "25% keyword coverage" in an old block, which was reworded to "25 percent" -- the one exception to "never edit older blocks").
2. `CHANGELOG.md`: a new row in the "Recent releases" table and a new `## [version]` section with its `<a id="v...">` anchor.
3. `src/cartogen_ai/core/release_notes.py`: `WHATS_NEW_VERSION`, `NEW_MARK_VERSIONS`, `WHATS_NEW_ITEMS` (shown in the plugin's Help dialog), any new tool in `HUMANITARIAN_WORKFLOWS` with its `TOOL_NEW_IN` entry.
4. `README.md`: the version line, the status line, a new "What's new in <version>" section (keep the previous one below it), and the humanitarian table -- regenerate it from `release_notes.render_readme_table()`.
5. Counts: tool count (README, `docs/TOOLS_REFERENCE.md` via `python docs/generate_tools_reference.py`) and task/section counts (`docs/USER_GUIDE.md`); the Help dialog reads them live.
6. Say plainly what was and was not verified (hand-tested vs CI only), then build the zip with `python plugin_upload.py`.


## 9. QGIS / PyQGIS development rules

These follow the PyQGIS Developer Cookbook (docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/) and the plugins.qgis.org requirements, checked against what this repo already does. **Unverified against the page itself:** the 2026-10-11 session that wrote this section could not reach docs.qgis.org (blocked by the sandbox's network policy), so the rules come from the cookbook as known, not from a fresh read. Re-read the cookbook chapters named below when you work in that area. The cookbook page above is the 3.44 (LTR) line; this plugin targets **QGIS 4.2.x / Qt6 only**, so where 3.44 and 4.x differ (flat enums, `QVariant` types, `QRegExp`, `exec_`), follow 4.x and the QGIS 4 migration notes, not the 3.44 text.

1. **Threads (cookbook: Using Tasks / Threading).** `QgsProject`, map layers, the canvas, `iface` and every widget are GUI-thread only. Work that can take more than about a second goes in a `QgsTask` (or `QgsProcessingAlgRunnerTask`), never a bare `threading.Thread` touching layers; a task's `run()` must not touch the project or the GUI, and results are applied in `finished()`. Honour `isCanceled()` and give the user a Stop (see `tools/_background_processing.py`, `cancel_signal.py`).
2. **Network (cookbook: Network).** Use `core/net.py` (`QgsNetworkAccessManager`/`QgsBlockingNetworkRequest`) so QGIS proxy, SSL and authentication settings apply. New code does not call `requests`/`urllib` directly; the two kept deliberately (SSRF-guarded opener, Ollama) are listed in `SECURITY.md` §4a. Always set a timeout and a size cap.
3. **Credentials and settings (cookbook: Settings, Authentication infrastructure).** Secrets go in the QGIS Auth Manager or session memory only (`infrastructure/auth.py`), never in `QgsSettings`, the project file, logs or the repo. Non-secret options use `QgsSettings` under the `cartogen_ai/` prefix via `settings_keys.py`.
4. **Layers and data (cookbook: Loading Projects, Vector/Raster layers, Geometry, CRS).** Check `layer.isValid()` after every load; check a CRS is valid before reprojecting and use `QgsCoordinateTransform` with the project's `transformContext()`; use `QgsDistanceArea` with the project ellipsoid for measurements; edit through `startEditing`/`commitChanges` (check the return value, call `rollBack` on failure) or `dataProvider().addFeatures`; never mutate a layer a task is reading. Prefer `processing.run("native:...")` over hand-written geometry loops.
5. **Logging and messages (cookbook: Python Console / Message log).** Use `core/logger.py` `log_event` (it feeds `QgsMessageLog`), metadata only; user-facing notices use `iface.messageBar()` from the GUI thread. No `print()` (ruff T20 enforces it).
6. **Enums and Qt6.** Use scoped enums (`Qt.AlignmentFlag.AlignLeft`, `QgsWkbTypes.GeometryType.Point`), import Qt through `qgis.PyQt`, never `PyQt5`/`PyQt6` directly, no `exec_`. Code that must run on a class or member that moved between versions goes through `resolve_qgis_enum` (`tools/_qgis_enum_compat.py`).
7. **Plugin lifecycle (cookbook: Developing Python Plugins).** `initGui` adds, `unload` removes everything it added (menu, toolbar, dock, processing provider, signal connections, timers, background tasks); `classFactory` stays in the root `__init__.py`. Load, unload and reload must work without restarting QGIS (the CI smoke test checks it).
8. **Processing (cookbook: Writing new Processing algorithms).** Algorithms live in `processing/` as `QgsProcessingAlgorithm` subclasses registered in the provider, with parameters declared in `initAlgorithm`, `feedback` used for progress and cancel, and no GUI calls inside `processAlgorithm`.
9. **Packaging and metadata (plugins.qgis.org).** Follow §8 and `tests/test_directory_validator.py`: `metadata.txt` has name, description, version, `qgisMinimumVersion`, author, email, about, tracker and repository; no `%` anywhere in it; a `LICENSE` at the package root; a lower-case snake_case top folder; no `.pyc`, `__pycache__`, hidden files or `..` paths; zip at most 25 MB.
10. **Dynamic code.** No `eval`/`exec` of model- or user-supplied text in the plugin process. The one script tool runs in the isolated process described in `SECURITY.md` §1 and fails closed when isolation is unavailable; do not widen it.
11. **Verification.** Anything that touches QGIS objects needs a live-test in `tests/test_*_live.py` (runs in the pinned QGIS 4.2.2 image), not only the offline suite; say in the commit and release notes whether a change was live-tested, CI-only, or hand-tested (§2).
