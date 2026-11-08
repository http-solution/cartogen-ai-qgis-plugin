# PLAN-066: Say plainly when an algorithm made no layer (DEF-30)

Status: in progress

## Goal
Round-3 smoke row B6: `native:meshrasterize` with PIXEL_SIZE 5 on a tiny mesh in EPSG:4326 answered "ran successfully with no new layer output", then two more calls failed with "writeBlock() called on read-only provider"; a request with pixel size 0.001 made the raster. The success wording let the assistant carry on as if a raster existed, and nothing named the cell size.

## Scope
`src/cartogen_ai/core/agent/tools/processing_allowlist_tools.py`: new pure `no_layer_result`, used by the no-layers branch of `run_allowlisted_processing_algorithm`. When the algorithm declares an output layer destination (not a report file) and none appeared, the result has `layer_created: false` and a message saying NO layer was made; for a raster with a cell-size parameter it names the usual cause (cell size larger than the extent, in layer units). Algorithms with no layer destination keep the old wording. The "writeBlock() read-only provider" failures on later calls are unchanged.

## Acceptance
`tests/test_no_layer_result.py` passes; the existing allowlist tests pass; ruff and ledger guard pass. Live: rerun row B6 with a deliberately large pixel size; the reply must not claim a raster.

## Guard tests
`tests/test_no_layer_result.py`; ledger feature `processing-run-guards-rc48`.

## Rollback
Revert the commit.

## Status log
- 2026-11-08: built and tested offline with plain names (CI only, not seen live). Not done: a pre-run check that refuses a cell size larger than the input's extent, which would stop the failure earlier but needs the mesh extent in the layer's CRS and a live look; left as a possible follow-up.
