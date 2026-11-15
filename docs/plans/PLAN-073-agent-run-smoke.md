# PLAN-073: Agent-run smoke package (the program writes the evidence)

Status: in progress

## Goal
On 2026-11-13/14 the owner handed the full live smoke test to a small chat agent (Haiku, Cowork, driving QGIS through the screen). The agent was told many times to collect evidence per row, stopped after two rows (A2, A3), said the job was too large, and pasted stale clipboard text into the chat for row B1, which made that run invalid. About 58 screenshots across 38 rows were still owed. Cost to that point: about $29 across the session. The cause on our side: the package is a long hand walkthrough that makes saving evidence depend on a person or agent clicking, typing into the QGIS console and screenshotting, and it was handed to something that cannot do that reliably.

## Scope
- `tools/run_smoke_headless.py`: runs rows of `docs/AGENT_RUN_ROWS.json` in a headless QGIS. A step loads a shipped input, tags a layer's sensitivity, or calls a plugin tool through the real registry with real arguments. No model, no network, no screenshot, no clipboard.
- `tools/smoke_core.py` (pure): evaluates checks, decides the verdict, writes `evidence/<row>/{row.json, checks.txt, verdict.json}`, `RESULTS.csv`, `SUMMARY.md`, and verifies the evidence folder is complete. A row is PASS only if at least one check ran and all held; an unevaluable check is a failure; a crash is ERROR; a row marked `needs_eyes` is never PASS.
- Rows (first four): H1 crude health rates, H2 Moran's I of a checkerboard, H3 Gi* on a one-high grid, H4 geocoding refused on a SENSITIVE layer. Each repeats the numbers of the matching hand row (C24, C21, C22, C27).
- `tools/build_agent_run.py` builds `cartogen_ai_agent_run_<version>.zip` (plugin source, runner, rows, README with the stop rules for an agent, `RUN.bat` with a `dry` mode that runs one row).
- Out of scope: any row needing a model reply, the internet or a person looking at a map; those stay in the hand packages.

## Not done, said plainly
- Never run on a real Windows QGIS yet. The QGIS half is exercised only by `tests/test_run_smoke_headless_live.py` in the QGIS CI job (written without a QGIS install; CI's first run is its first execution).
- It produces no screenshots, so it replaces the numbers-and-refusals part of the hand rows, not the looks.
- I have not read the failed session's transcript (no tool for it): the diagnosis above comes from the session record, the owner's pasted text and the package's design.

## Acceptance
`tests/test_smoke_core.py` (offline) and `tests/test_run_smoke_headless_live.py` (QGIS CI) pass; ruff, ledger guard, master-list check pass. By hand: `RUN.bat dry` on the owner's machine writes `results\evidence\H1-rates-crude\` with the three files and prints PASS, before any larger run.

## Guard tests
`tests/test_smoke_core.py`, `tests/test_run_smoke_headless_live.py`; ledger entry `agent-run-smoke`.

## Rollback
Delete the four new files, the rows file and the builder; nothing else depends on them.

## Status log
- 2026-11-15: written; offline tests pass; package built and its layout checked by unzipping (plugin folder found, rows file found). Not run in QGIS.
