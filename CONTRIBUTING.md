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
