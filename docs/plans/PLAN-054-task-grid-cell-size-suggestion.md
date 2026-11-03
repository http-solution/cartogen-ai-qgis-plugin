# PLAN-054: A refused task grid says which cell size would work (master list DEF-6)

Status: in progress

## Goal
`generate_mapping_task_grid` refuses a grid above 5,000 tasks (`MAX_TASKS`). On a whole country at 5 km the refusal said only "Use a larger cell_size_m", so the user had to guess a size and try again. The owner decided on 2026-11-03: suggest a cell size, do not raise the limit and do not switch it off.

## Scope
- Both refusals (the bounding box alone needs more than four times the limit, and the grid after cutting to the outline has more than the limit) now say that no grid was made, name the smallest round cell size that fits with about how many tasks it gives, and offer making the grid for part of the area at a time with `aoi_where`. The result also carries `suggested_cell_size_m` and `suggested_cells` as numbers.
- Round sizes come from a ladder (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8 times a power of ten, from 100 m), never a smaller size than the one asked for.
- For the bounding-box refusal the count is an upper bound (the box, not the outline). For the after-clipping refusal the size is scaled from the real count (tasks go with one over the size squared) and is stated as "about".
- Out of scope: any automatic change of the size or the limit; the cell size is an operational choice (what a field team can cover), so the tool only suggests and the user decides.

## Acceptance
- Offline: `tests/test_task_grid_cell_size.py` (14 tests): the ladder, the smallest fitting size, never below the size asked for, the reported count equals the real estimate, the wording of both refusals, nothing suggestible keeps the old advice.
- CI live: `tests/test_task_grid_tools_live.py` refuses a 5 by 3 degree box at 1 km, leaves no layer behind, and the suggested size then produces a grid within the limit.
- By hand: ask for a 1 km task grid over a whole country; expect a refusal naming a size, then ask for that size.

## Guard tests
`tests/test_task_grid_cell_size.py`, `tests/test_task_grid_tools_live.py`; ledger entry `task-grid-cell-size-suggestion`.

## Rollback
Revert the change: the refusals return to the old text and nothing else depends on the new functions.

## Status log
- 2026-11-03: owner chose "suggest a cell size". Built tests first; offline tests and ruff and mypy pass. The live test was written without a QGIS install. Not hand-run.
