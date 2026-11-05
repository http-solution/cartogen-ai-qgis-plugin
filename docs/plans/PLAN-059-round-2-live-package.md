# PLAN-059: Round 2 of the live smoke test: the rows to rerun after the 2026-11-04 fixes

Status: in progress

## Goal
After PR 573, the regression gate lists 40 features seen working live that changed code since, and four fixes (V9 undo card, V4 animation tool, A1 empty legend, B5 export count) have never been seen working. The full package is 45 rows; this plan builds a package of just the rows that settle those questions (30 rows, each with its reason), plus the one case of issue 380 that no row ever tested (B41, the mesh), so one agent run on the owner's Windows machine can turn "CI green" into "seen working" or "seen failing".

## Scope
- `tools/build_full_smoke.py --only ID,ID,... | @docs/ROUND2_ROWS.json [--label round2]`: builds a subset package; coverage of the full set is still checked first; an unknown row id stops the build; the subset's COVERAGE.md lists only what its rows cover; the README says it is round 2.
- `docs/ROUND2_ROWS.json`: the 30 rows and why each is there (from `python tools/live_results.py --gate`, the features seen only partly, and the Track 2 fixes).
- New row `B6-mesh-to-raster` in `docs/FULL_SMOKE_ROWS.json`: case B41 of issue 380, with the issue's own wording and `smoke_mesh.2dm`.
- `1_plugin/BUILD.txt` in every package: the commit and SHA-256 of the plugin zip, and a plain instruction to install it over any earlier 1.18.5 (the version number is unchanged while 1.18.6 is held, so an old install would look identical).
- Out of scope: running any row; changing plugin behaviour.

## Acceptance
`tests/test_smoke_round2.py` (offline): the row selection keeps running order and names unknown ids; every listed row exists and has a reason; the four Track 2 rows and B6 are in the list; B6 uses the issue's wording, ships the mesh and covers the routing entry; a really built subset package holds exactly the chosen rows, a result line and checklist for each, only their coverage, all their files with checksums, a BUILD.txt whose checksum matches the plugin zip, and a README that says round 2. The full package's coverage test is unchanged. By a person or agent: the rows are run and `5_check_evidence.py` reads the folder.

## Guard tests
`tests/test_smoke_round2.py`, `tests/test_full_smoke_package.py`; ledger entry `full-smoke-package`.

## Rollback
Delete `docs/ROUND2_ROWS.json` and the `--only` branch of the builder; the full package is built as before (the BUILD.txt addition is harmless to it).

## Status log
- 2026-11-04: built; offline tests pass. Nothing in it has been run. The row set is the gate's list on `main` at `faeacee` (40 features) plus the partly-seen features' rows; B4 (the most expensive row) stays in with a note to run it last and only with quota. Rows that need a person the agent cannot be (B3 needs two fluent readers; a person must look at the A1 pages) are left in and are marked Skip by the agent with what a human must do.
