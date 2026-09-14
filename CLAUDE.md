# CLAUDE.md

> **THIS IS THE CANONICAL QGIS PLUGIN REPO (confirmed 2026-09-08).** A sibling checkout, `C:\Cartogen-AI-Core\cartogen-ai-community`, exists but is now stale -- its full commit history is an ancestor of this repo's (confirmed via `git merge-base --is-ancestor`). The two were merged into this repo's `main` on 2026-09-05 (`764afce`), and this repo has since pulled well ahead: a 15-commit "27-point QGIS architecture review" plus a two-phase animated temporal-dashboard feature (`609ee10`, 2026-09-08). Do all QGIS-plugin development work here, not in `cartogen-ai-community`. Some older Obsidian notes and this repo's own docs may still say otherwise from before this date -- treat this note and a fresh `git log`/`git merge-base` check as the source of truth over anything older.

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
  process — CI has no QGIS and cannot run or visually verify it. This interactive session's
  sandbox CAN, when a real QGIS install is available: construct the real widget headlessly via
  `"C:\Program Files\QGIS <ver>\bin\python-qgis.bat"` with `QgsApplication([], True)` (GUI mode,
  not `False`), force a complete `QPalette` (the offscreen platform's default one is missing
  roles like `AlternateBase` — force a realistic one rather than trusting the default), call
  `widget.grab().save(path)`, then actually look at the saved PNG (the Read tool renders
  images) — used throughout the UI/chat redesign workstream (2026-09-12) to verify icon/color
  changes for real rather than only checking "imports without error." `ui/chat_formatting.py`
  and `ui/icons.py`'s pure string-generation half are deliberately Qt-free so they stay
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

CI (`.github/workflows/tests.yml`) runs the test suite and a `py_compile` check on every push/PR.
There is no QGIS in CI — anything that only breaks inside a real QGIS session (Qt widget wiring,
layer rendering, print layouts) needs manual verification; see `docs/RELEASE_SMOKE_TEST.md`.

## Editions

> **CORRECTION (2026-09-14, verified via `git remote -v` + authenticated `gh repo view`,
> resolving a real conflict an external audit flagged between this section and
> `docs/MASTER_TASK_REGISTRY.md`):** the GitHub remote this checkout's `origin` actually points
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

Community, Pro, and Enterprise (`docs/PRODUCT_TIERS.md`) are three editions, but **not** three
variants of this one codebase — this repo's *content* is designed to stay the single Community
codebase, carrying no tier-check/licensing-gate logic (verified, still true) — see the
correction note above for what "public" does and doesn't mean here today.
Pro/Enterprise are planned to be built in a *separate private repo* that consumes this one as an
upstream core (one-way sync, decided but not yet built — see `docs/archive/OPEN_CORE_REPO_STRATEGY.md`;
confirmed 2026-09-14 that `cartogen-ai-enterprise`/`cartogen-ai-pro` locally are empty
placeholder directories with no git repo at all, consistent with "not yet built").
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
