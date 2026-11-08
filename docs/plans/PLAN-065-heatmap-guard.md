# PLAN-065: Guard the native kernel-density heatmap like hotspot_analysis (DEF-34)

Status: in progress

## Goal
Round-3 smoke rows D2 and E5: `hotspot_analysis` correctly refused a 1-degree radius, and the model then ran `native:heatmapkerneldensityestimation` through the allowlist with RADIUS 1 in degrees (D2); the same algorithm also ran on a polygon layer (E5). The dedicated tool's guards must hold whichever route the model takes.

## Scope
`src/cartogen_ai/core/agent/tools/processing_allowlist_tools.py`: new pure `heatmap_violation`, called from the shared pre-run gate `_check_raster_lists`. Point layers only; radius and cell size checked with the existing `degrees_value_problem`. Other algorithms are unchanged (the earlier all-algorithms CI probe showed a blanket geometry check breaks algorithms that convert).

## Acceptance
`tests/test_heatmap_guard.py` passes; `tests/test_processing_allowlist_tools.py` unchanged and passing; ruff and ledger guard pass. Live: rerun row D2 step 4 and row E5 step 3; both must be refused with nothing run.

## Guard tests
`tests/test_heatmap_guard.py`; ledger feature `processing-run-guards-rc48`.

## Rollback
Revert the commit; the heatmap algorithm is unguarded again.

## Status log
- 2026-11-08: built and tested offline with stand-in layers (CI only, not seen live). The refusal arrives as "'native:heatmapkerneldensityestimation' failed: <message>" through the existing wrapper. Not covered: other native density algorithms with a radius in degrees (none seen failing).
