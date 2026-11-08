# PLAN-062: Round 3 of the live smoke test: every pending feature on the current build

Status: in progress

## Goal
The owner decided on 2026-11-07 that old versions are not tested; every pending check must be seen on the current build (QGIS 4.2.3). Pending means two things: features never seen live (52 on `main` at 58d69b4) and features seen live only on an older build whose code has changed since (52, the regression gate's list). One package should cover both.

## Scope
- `docs/ROUND3_ROWS.json`: 39 of the 45 rows, each with the reason it is there (computed from `docs/LIVE_RESULTS.json`, the gate and the rows' `covers`). The six left out: D5-task-grid, V2-stop, V7-merge, V8-raster, W5-hdx-ranked, W12-guide.
- `tools/build_full_smoke.py`: the subset README named every subset "ROUND 2"; it now names the round from `--label`.
- Build: `python tools/build_full_smoke.py --plugin-zip dist/cartogen_ai_v<version>.zip --only @docs/ROUND3_ROWS.json --label round3`, from `main` after this merges so `BUILD.txt` names a `main` commit.
- Out of scope: running any row; changing plugin behaviour; rows for the old-version cases A5, A7, C5, D6, S5 (not in the current package; DEF-2, DEF-3, DEF-4 stay Blocked).

## Acceptance
`tests/test_smoke_round3.py` (offline, hermetic): every listed row exists and says why; the nine rows round 2 did not run are in; every feature never seen live that any row covers is covered by a listed row; the six rows left out are named in the file's text; a round-3 README does not say ROUND 2. After a real run: `docs/LIVE_RESULTS.json` updated from the returned evidence, `rechecked_at` stamped only on features whose rows passed on the release candidate.

## Guard tests
`tests/test_smoke_round3.py`, `tests/test_smoke_round2.py`, `tests/test_full_smoke_package.py`; ledger entry `full-smoke-package`.

## Rollback
Delete `docs/ROUND3_ROWS.json` and the label handling in `readme()`; round 2 and the full package are built as before.

## Status log
- 2026-11-07: built; offline tests pass; a trial build gives 39 rows and 131 ledger entries covered. Three ledger entries have no row (docs-published-to-wiki, processing-layer-kind, undo-across-messages): their hand-verified text says a person already tested them, so they are not in the pending sets. Rows that need more than the agent route: A3-cli-bridge (a signed-in Claude Code or Codex, else Skip), V1-update and W7-mcp-dialog (a person), F1-mcp-size (a person and an MCP client, or `mcp_probe.py`); F3-check-evidence needs a terminal only and W6-mcp-probe a script. Nothing in the package has been run.
- 2026-11-07: package audit on the unzipped round-3 zip (the owner reported that instructions and input files had not worked or were missing last time). **Input files:** 33 of 33 present and unchanged (`verify_inputs.py`); every file opens or parses (smoke_start.qgz and its 7 data sources all beside it, both GeoPackages with their layers and row counts, both rasters, the before and after grids on one grid, 8 CSVs, 8 JSON and GeoJSON files, the mesh, the DOCX and PDF); every `smoke_*` name a row uses is a file, a layer, or a layer the row itself makes. **Instruction faults found and fixed:** rows W6, W7, F1, W8 and W10 told the tester to run `python mcp_probe.py` and `python check_workflow_file.py` (the scripts are in `6_tools/`); W6 said `python tools/check_evidence.py` (the package has `5_check_evidence.py` and no `tools/` folder); W3, W4, W6, W7, W8 and W10 said to save into `results\outputs\W6` and so on, folders that do not exist (they are named by the full row id; round 2 ended with both `W8` and `W8-export`, `W10` and `W10-import-bad`); V4 and V5 said `<row id>` for the tester to fill in. The builder now rewrites these for the package layout (`localize_text`); `5_check_evidence.py` no longer points at `tools/layout_check_script.py`. Tests: every command in any row names a script that is in the package, and every results folder named is a row folder. **Run on the rebuilt package:** `verify_inputs.py`, `check_workflow_file.py` (valid file accepted; six bad files refused with the expected sentences, JSON written into the row folder), `5_check_evidence.py results`, and a compile of every script all exit cleanly. **Not verified here (no QGIS):** the plugin install, the console snippets (`begin`, `snap`, `shot`; they worked in round 2), `mcp_probe.py` against a live server, the CLI row.
