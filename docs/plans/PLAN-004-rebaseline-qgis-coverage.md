# PLAN-004: re-baseline the QGIS coverage list against what the plugin really does

Status: done

## Goal
Answer "how much of QGIS can be driven from the chat" with a number that is true today. The 164-row action list (`tools/qgis_coverage_actions.py`) still marks as missing several actions that rc44 and rc46 made possible through approved Processing algorithms (raster warp/reproject, proximity, fill no-data, sieve, viewshed, extract vertices, densify, polygons to lines, bounding boxes, smoothing, random points ...), and still says "42 of 772 algorithms are allowed" when the code allows 427. Several of those algorithms passed the rc46 hand test (21 of 21 priority algorithms).

## Scope
In: rows whose truth changed; a new `ALGS:` marker in a row's note that names the approved algorithm ids behind it, checked against the allow-list by the builder; an `evidence` column (hand-tested rc46 / CI only); a generated `docs/qgis_coverage/SUMMARY.md` that a test keeps equal to the CSV; the ratchet baseline raised.
Out: building new tools (the next plans take the real gaps: the 60 file-writing algorithms, editing of vertices and parts); changing any plugin behaviour; touching rows whose status did not change.

## Acceptance
1. Every row that names algorithms lists only ids that are in `ALLOWED_ALGORITHM_IDS` (builder and test fail otherwise) and the router offers the Processing tools for its phrase.
2. A row is only raised when its algorithms exist in the allow-list; a row says "hand-tested rc46" only for the ids in the rc46 Part 5 priority list.
3. `docs/qgis_coverage/SUMMARY.md` equals what `tools/build_qgis_coverage.py` generates (test), and `tests/test_qgis_coverage_ratchet.py` passes against the new baseline.

## Guard tests
`tests/test_qgis_coverage_evidence.py`, `tests/test_qgis_coverage_ratchet.py`; ledger entry `qgis-coverage-evidence`.

## Rollback
Docs and a test file only; revert the pull request. No plugin behaviour changes.

## Status log
- 2026-10-23: plan created with the first rows (this pull request). Nothing here is hand-verified beyond the rc46 results it cites.
- 2026-10-23: 11 rows updated, builder checks `ALGS:` ids and writes `algorithms`, `evidence` and `SUMMARY.md`; baseline raised. Result: 164 actions, COVERED 107 to 111, PARTIAL 28 to 33, MISSING 27 to 18, BLOCKED 2. Offline suite, ruff, mypy pass. Acceptance 1 to 3 met; hand-tested claims limited to the 21 rc46 algorithms.
