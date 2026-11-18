# PLAN-074: Computer-use smoke package (Haiku 5 on QGIS 4.2.3)

Status: in progress

## Goal
Owner request 2026-11-15: a full live smoke package that a Haiku 5 computer-use agent runs on QGIS 4.2.3, with the output collected and analysed, covering all needed tests and the missing features. PLAN-073 explains why the earlier hand package failed with a small agent: it had to follow a long sheet and remember to save evidence.

## Scope (one rule: the agent never saves evidence)
- **Cards.** `tools/smoke_cards.py` turns the 72 rows of the full smoke package into one short card each, with every console-command sentence removed (the dock does that). Rows that need a second program or a fluent reader (A3, B3, C21, C22, C24, F1 by their Needs text) are marked human rows, so 66 are for the agent.
- **Dock.** `tools/smoke_dock.py` docks one card in QGIS. Start, then Pass / Partial / Fail / Skip with a one-line note. The result click calls the existing `collect_evidence.snap` (window and canvas screenshots, layer table, project state, CartogenAI log, the plugin's own per-request evidence folder), and only then writes `RESULTS_GUI.csv`. A result for a row that was never started is refused; an evidence failure is recorded on the line. The start script sets the plugin's evidence setting itself.
- **Programme-checked rows.** `docs/AGENT_RUN_ROWS.json` now has fifteen rows (H1 to H15) that check, with no agent, the numbers CI already proved for rows C20 to C25 and C27: rates and their variants, Moran's I (checkerboard and districts) and its refusals, Gi* (with and without false-discovery correction), the Kulldorff scan, the four public-health looks, the land-cover and change-class looks, the task-grid refusal and the geocoding refusal.
- **Analysis.** `tools/analyze_smoke_run.py` writes `REPORT.md`: per row the claim, the trust level (VERIFIED, UNSUPPORTED, CLAIMED, NO RESULT, HUMAN ROW), seconds, tools actually called; an agent PASS without a window screenshot, a layer table (and, for model rows, a plugin tool-call record) is UNSUPPORTED. Exit code is non-zero when anything is UNSUPPORTED, unrun, or a program row failed.
- **Package.** `tools/build_computer_use.py`: the full smoke package's test files and SHA-256 list, the plugin zip, cards, dock, runner, three .bat files, a 25-line prompt for the agent, a README with the owner-only steps (the model key is entered by the owner, never by the agent).

## Not done, said plainly
- The dock, `START_QGIS.bat` (profile path of QGIS 4, `qgis-bin.exe --code`), the plugin auto-start (`cartogen_ai_plugin`) and window screenshots have never run on a desktop QGIS 4.2.3; the dock is only clicked through in the CI job. Nothing has run with Haiku 5.
- Rows whose result depends on how a map or page looks still rely on the agent's reading of the screen; the report can show it saw evidence, not that its judgement was right. Look rows (C20 colours, C25 bulletin page) should be checked by a person from the saved window.png.
- "Missing features" here means the ledger entries no person has verified: the 72 rows cover all 199 ledger entries (coverage is checked by the existing builder).

## Acceptance
`tests/test_smoke_cards.py`, `tests/test_smoke_core.py` offline; `tests/test_smoke_dock_live.py` and `tests/test_run_smoke_headless_live.py` (now ten rows) in the QGIS CI job; ruff, ledger guard and master-list check. By hand: the dry run, then three cards with a person watching.

## Guard tests
Ledger entry `computer-use-smoke` and `agent-run-smoke`.

## Rollback
Delete the new tools, tests and the plan; the full smoke package is untouched (the builder only reads it).

## Status log
- 2026-11-15: written and built offline (72 cards, 66 for the agent); not run in QGIS.
- 2026-11-15: merged (PR 640). Five more program rows added (H11 task-grid refusal, H12 statistics refusals, H13 cluster and hotspot looks, H14 change-class looks, H15 rates variants); the checks use only keys and messages read from the tool code, and the QGIS CI job is their first run.
- 2026-11-18 (first real Haiku run on Windows 11, results sent by the owner): the dock worked for A1, A2, A3, V1 and W13 (window screenshot, layer table, project state, log all written), but QGIS CRASHED when a result button was pressed on B1 (twice) and B2 (`qgiscrashhandler.exe`), the verdicts were lost, and Haiku wrote notes by hand instead. B4 showed tools that block QGIS for minutes (`ingest_osm_features` 164 s, a processing algorithm 320 s), which look like a freeze to an agent. A1 and V1 could not be done from their cards. Changes: the result line is written BEFORE any evidence is taken and rewritten afterwards (a crash leaves a 'pending' line, which the report reads as unsupported); the screenshot is taken from outside QGIS (PowerShell) and `snap(..., screenshots=False)` no longer calls `grab()`/`saveAsImage()` inside QGIS (suspect cause: the A2 evidence has `canvas.pgw` but no `canvas.png`; NOT proven); a row left open by a crash is recorded as FAIL 'interrupted' at the next start; A1, V1, F3, W6 to W10 are human rows (they need scripts or a terminal); slow rows carry a "wait, do not click" notice; the agent prompt is rewritten for the Claude desktop app with Haiku on Windows 11 (no restarts, no other programs, at most 6 rows per session). Not verified: that the crash is gone.
- 2026-11-18 (owner: "i want haiku computer use to do everything: recover the failure, launch the tools, do what is needed to complete the process"): the "stop and report" rules are replaced by full authority with a short STOP list (no keys, nothing outside the package folder and QGIS, no pasting). New: `RUN_EVERYTHING.bat` + `tools/supervisor.ps1` (runs the program-checked rows, opens QGIS with the dock, reopens it after a crash up to 8 times and closes the crash window, writes the report); `RECORD.bat` / `tools/record_result.py` records a verdict from the command line when the dock cannot be used, so nothing is kept in a hand-written note; `PY.bat` runs QGIS's own Python for the card commands; `6_tools/` and `2_layout_check/` ship the scripts the script rows use, so A1 and W6 to W10 are the agent's rows again (only V1, F3 and the rows needing a second program or a signed-in CLI stay human; the dock records those as SKIP by itself); the dock opens at the first row with no result, so a new Haiku session or a restarted QGIS carries on. Not verified: `supervisor.ps1` and the bat files have never run (no Windows here); the Python parts are tested offline.

