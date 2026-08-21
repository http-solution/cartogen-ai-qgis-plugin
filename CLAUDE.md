# CLAUDE.md

Orientation for Claude Code (or any AI coding agent) working in this repo. Read this before
making changes — it points at the conventions this project actually enforces, not generic advice.

## What this is

Cartogen AI is a QGIS plugin: a spatial AI agent that plans, executes, and shows its work against
a user's open QGIS project. Single Python package, installed as a QGIS plugin folder. No build
step, no compiled artifacts beyond the release zip.

## Structure

- `agent/` — the agent core. `agent/agent.py` is the tool-calling loop and dispatcher;
  `agent/providers/` are the 5 LLM provider clients (OpenRouter, Gemini, OpenAI, Claude, Ollama)
  plus a `cartogen.py` stub for a planned hosted gateway; `agent/tools/` is every tool the model
  can call, one file per domain (vector, raster, styling, humanitarian, etc.), registered via
  `agent/tools/registry.py`'s `@register_tool` decorator.
- `ui/` — the QGIS dock widget, settings dialog, canvas highlighting. Everything here that
  imports `qgis.PyQt`/`qgis.core` unconditionally can only be exercised inside a real QGIS
  process — this sandbox (and CI) cannot run or visually verify it. `ui/chat_formatting.py` is
  deliberately Qt-free so it stays unit-testable; follow that pattern for new pure logic.
- `tests/` — unit tests, runnable without a QGIS installation. Every module that touches
  `qgis.core` degrades gracefully via its own `QGIS_AVAILABLE` guard specifically so this works.
- `docs/` — see the table in `README.md`. `docs/USER_GUIDE.md` and `docs/TOOLS_REFERENCE.md` are
  living references; `docs/IMPLEMENTATION_TRACKER.md` and `docs/BUG_TRACKER.md` are living
  trackers you should update when you close or find something; dated docs
  (`docs/STATUS_REVIEW_2026-08-20.md` and similar) are frozen snapshots — see below.
- `service/` — a standalone hosted-gateway/monetization prototype for the planned Pro tier. Not
  part of the QGIS plugin; not built or tested by the CI workflow.
- `metadata.txt` — QGIS plugin manifest, including an embedded `changelog=` field. Its historical
  entries are frozen (see below) — only ever prepend a new entry, never edit an old one.

## Before you touch anything: read CONTRIBUTING.md

It's short and specific to this codebase, not a generic PR-process doc. The two rules that matter
most for an AI agent working here:

1. **Comments explain *why*, not *what*.** If you fix a real bug, write the comment the way the
   existing ones are written: what broke, how you know (a stack trace, a failing test, a live
   report), and why the fix works. Don't write comments that just restate the next line.
2. **State what's shipped, roadmap, or unverified — honestly, in the code itself, not just in a
   doc.** If something can't be verified in this sandbox (most things touching live QGIS or a
   real LLM API response), say so explicitly rather than implying it works.

Also: **frozen historical docs are never edited after the fact.** `CARTOGEN_AI_FEATURE_LIST.md`,
`CARTOGEN_AI_PRD.md`, `IMPLEMENTATION_TASK_LIST.md`, `CHANGELOG.md`'s past entries, and any
dated review/spec doc are accurate to when they were written — including old identifier names
after a rebrand. If something in one is now wrong, add a new entry/doc that supersedes it; don't
rewrite history.

## Running things

```bash
# Full test suite -- no QGIS needed
python -m unittest discover -s tests -p "test_*.py" -v

# Regenerate docs/TOOLS_REFERENCE.md after adding/changing a tool
python docs/generate_tools_reference.py

# Build the release zip (reads version from metadata.txt)
python plugin_upload.py
```

CI (`.github/workflows/tests.yml`) runs the test suite and a `py_compile` check on every push/PR.
There is no QGIS in CI — anything that only breaks inside a real QGIS session (Qt widget wiring,
layer rendering, print layouts) needs manual verification; see `docs/RELEASE_SMOKE_TEST.md`.

## Editions

Community, Pro, and Enterprise (`docs/PRODUCT_TIERS.md`) are three editions, but **not** three
variants of this one codebase — this repo is, and stays, the single public Community codebase.
Pro/Enterprise are planned to be built in a *separate private repo* that consumes this one as an
upstream core (one-way sync, decided but not yet built — see `docs/OPEN_CORE_REPO_STRATEGY.md`).
**Don't add tier-check/licensing-gate logic to this repo** — that kind of logic belongs in the
private repo once it exists, not here. If you're ever asked to add tier-gating directly to this
codebase, that's a sign the request conflicts with the decided architecture — flag it rather than
implementing it.

## When you're not sure whether to just fix something

Mechanical, low-risk fixes (wrong error message, missing retry, an obviously dead branch) — fix
directly. Anything that changes behavior a user might depend on, or that you can't verify in this
environment, or that involves a real product/design tradeoff — flag it with a clear recommendation
instead of applying it silently. `docs/IMPLEMENTATION_TRACKER.md` §1 is where open items needing a
human decision live; add to it rather than deciding unilaterally.

## History

This repo was consolidated from an earlier dual-tree setup (`qgis_ai_assistant` at
`C:\qgis_ai_assistant`, which maintained a second synced copy under a different internal
identity). See `CHANGELOG.md`'s `[1.4.0]` entry for what changed. Full commit history predating
this repo lives in the old location, not here — this repo started from a fresh `git init`.
