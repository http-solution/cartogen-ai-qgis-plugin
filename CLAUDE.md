# CLAUDE.md

> **THIS IS THE CANONICAL QGIS PLUGIN REPO (confirmed 2026-09-08).** A sibling checkout, `C:\Cartogen-AI-Core\cartogen-ai-community`, exists but is now stale -- its full commit history is an ancestor of this repo's (confirmed via `git merge-base --is-ancestor`). The two were merged into this repo's `main` on 2026-09-05 (`764afce`), and this repo has since pulled well ahead: a 15-commit "27-point QGIS architecture review" plus a two-phase animated temporal-dashboard feature (`609ee10`, 2026-09-08). Do all QGIS-plugin development work here, not in `cartogen-ai-community`. Some older Obsidian notes and this repo's own docs may still say otherwise from before this date -- treat this note and a fresh `git log`/`git merge-base` check as the source of truth over anything older.

Orientation for Claude Code (or any AI coding agent) working in this repo. Read this before
making changes — it points at the conventions this project actually enforces, not generic advice.

## What this is

Cartogen AI is a QGIS plugin: a spatial AI agent that plans, executes, and shows its work against
a user's open QGIS project. Single Python package, installed as a QGIS plugin folder. No build
step, no compiled artifacts beyond the release zip.

## Structure

- Everything lives under `src/cartogen_ai/` (layout restructured in Phase 11, 2026-09-20):
  - `core/agent/` — the agent core. `agent_orchestrator.py` (`CartogenAi`) is the tool-calling
    loop; it composes `tool_dispatcher.py`, `usage_tracker.py` and `history_manager.py`.
    `core/agent/tools/` is every tool the model can call, one file per domain (vector, raster,
    styling, humanitarian, etc.), registered via `tools/registry.py`'s `@register_tool`.
  - `core/services/`, `core/models/`, `core/validators/`, `core/representation/` — prompt
    refiner/router/task runner, transaction/confidence models, schema/P-code validation, and the
    map-representation planner.
  - `core/logger.py` — structured, metadata-only logging (`log_event`); never log raw prompts,
    responses, tool arguments/results, or coordinates. `core/exceptions.py` — exception hierarchy.
  - `infrastructure/` — `auth.py` (credentials: QGIS Auth Manager or session memory ONLY, never
    plaintext `QgsSettings`), `deps.py`, `settings_keys.py`, and `providers/` (the 5 LLM clients:
    OpenRouter, Gemini, OpenAI, Claude, Ollama, plus a `cartogen.py` stub for a planned hosted
    gateway).
  - `processing/` — the QGIS Processing provider (hub siting, service area algorithms).
  - The plugin entry points (`__init__.py`, `plugin_main.py`) stay at the repo root.
- `core/ui/` — the QGIS dock widget, settings dialog, canvas highlighting. Everything here that
  imports `qgis.PyQt`/`qgis.core` unconditionally can only be exercised inside a real QGIS
  process — the plain `test` CI job has no QGIS (the separate `qgis-live-tests` job does; see below). This interactive session's
  sandbox CAN, when a real QGIS install is available: construct the real widget headlessly via
  `"C:\Program Files\QGIS <ver>\bin\python-qgis.bat"` with `QgsApplication([], True)` (GUI mode,
  not `False`), force a complete `QPalette` (the offscreen platform's default one is missing
  roles like `AlternateBase` — force a realistic one rather than trusting the default), call
  `widget.grab().save(path)`, then actually look at the saved PNG (the Read tool renders
  images) — used throughout the UI/chat redesign workstream (2026-09-12) to verify icon/color
  changes for real rather than only checking "imports without error." `core/ui/chat_formatting.py`
  and `core/ui/icons.py`'s pure string-generation half are deliberately Qt-free so they stay
  unit-testable without any of this; follow that pattern for new pure logic.
- `tests/` — unit tests, runnable without a QGIS installation. Every module that touches
  `qgis.core` degrades gracefully via its own `QGIS_AVAILABLE` guard specifically so this works.
- `docs/` — see the table in `README.md`. `docs/USER_GUIDE.md` and `docs/TOOLS_REFERENCE.md` are
  living references; `docs/IMPLEMENTATION_TRACKER.md` and `docs/BUG_TRACKER.md` are living
  trackers you should update when you close or find something; dated docs
  (`docs/archive/STATUS_REVIEW_2026-08-20.md` and similar) are frozen snapshots — see below.
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

Also: **frozen historical docs are never edited after the fact.** `docs/archive/CARTOGEN_AI_FEATURE_LIST.md`,
`docs/archive/CARTOGEN_AI_PRD.md`, `docs/archive/IMPLEMENTATION_TASK_LIST.md`, `CHANGELOG.md`'s
past entries, and any dated review/spec doc in `docs/archive/` are accurate to when they were
written — including old identifier names after a rebrand. If something in one is now wrong, add
a new entry/doc that supersedes it; don't rewrite history. (These 3 files, plus
`docs/archive/DOCUMENTATION.md` and `docs/archive/LICENSE_AUDIT.md`, moved from the repo root
into `docs/archive/` in a 2026-09-12 repo-organization pass — content unchanged, only location.)

## Running things

```bash
# Full test suite -- no QGIS needed. -t . matters: without it, discover()
# treats tests/ as its own top-level dir and never runs tests/__init__.py's
# src/-on-sys.path bootstrap, so every cartogen_ai.core.* import fails --
# see docs/BUG_TRACKER.md BUG-2026-08-21-7.
python -m unittest discover -s tests -t . -p "test_*.py" -v

# Regenerate docs/TOOLS_REFERENCE.md after adding/changing a tool
python docs/generate_tools_reference.py

# Build the release zip (reads version from metadata.txt)
python plugin_upload.py
```

CI (`.github/workflows/tests.yml`) runs the test suite, `py_compile`, `ruff check .` (must stay at zero violations) and a release-zip packaging check on every push/PR.
The `test` job (Ubuntu + Windows) has no QGIS, but the `qgis-live-tests` job runs `tests/test_chat_widget_live.py` + `tests/test_plugin_main_live.py` inside pinned official QGIS docker images (4.2.2 only -- QGIS 3.x support, and the 3.28 LTR job with it, was dropped 2026-09-24) via `tests/_ci_run_live_tests.py`, which force-collects and pumps the Qt event loop before `exitQgis()` (see the docstring there for the crash this prevents). Anything that only breaks inside a real QGIS session (Qt widget wiring,
layer rendering, print layouts) needs manual verification; see `docs/RELEASE_SMOKE_TEST.md`.

## Editions

> **UPDATE (2026-10-09, verified via the GitHub API: `visibility: public`, GPL-2.0):** this repository is
> now PUBLIC at `http-solution/cartogen-ai-qgis-plugin`. That supersedes the 2026-09-14 note below, which
> described the older `cartogenai-glitch/CARTOGEN-AI` remote (then private) and is kept only as history.
> Because the repo and its full history are public: never commit credentials, API keys, personal email
> addresses or personal data (the secret and PII scan on 2026-10-09 found none in the tree or history);
> the earlier "no public repo exists" statements in older docs are out of date. GitHub Actions minutes
> are free on a public repo; the `tests` workflow runs on every push and pull request.
>
> *Superseded -- historical note, 2026-09-14:* (2026-09-14, verified via `git remote -v` + authenticated `gh repo view`,
> resolving a real conflict an external audit flagged between this section and
> `docs/MASTER_TASK_REGISTRY.md`) the GitHub remote this checkout's `origin` actually points
> to (`cartogenai-glitch/CARTOGEN-AI`) is **PRIVATE**, not public — confirmed with an
> authenticated API call, not guessed. The separate repo `docs/MASTER_TASK_REGISTRY.md` names
> as the intended public Community-facing repo (`cartogenai-glitch/cartogen_ai_community`) is
> **also PRIVATE** as of this check, contradicting that doc's own 2026-09-05 claim of having
> confirmed it public — it was either made private since, or that claim was wrong when made.
> `gh repo list cartogenai-glitch` shows exactly these 2 repos and no others: **there is
> currently no public GitHub repo for this project under this account at all.** The paragraph
> below is still accurate about *codebase content/architecture* (this codebase carries no
> tier-gating logic, verified separately in the 2026-09-13/14 audit) — read "public Community
> codebase" as a statement of intended licensing/content, not of current GitHub visibility.
> Whether/when to actually publish a public repo, and under what name, is a release decision
> for Alaa — not resolved here.

This repo is a single, GPL v2 open-source codebase — it carries no tier-check or licensing-gate
logic (verified, still true), and it isn't a variant of anything else. **Don't add tier-check/
licensing-gate logic to this repo.** If you're ever asked to add tier-gating directly to this
codebase, flag it rather than implementing it.

## Version bumps

A bump of `version=` in `metadata.txt` must also update the in-plugin Help and the README "What's new" and humanitarian table (`src/cartogen_ai/core/release_notes.py`), the CHANGELOG and the counts; see CONTRIBUTING.md §8. `tests/test_release_docs_in_sync.py` enforces it.

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

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
