# PLAN-067: Shrink a chart or profile into the free space instead of placing it on top of the map (DEF-37)

Status: in progress

## Goal
Round-3 smoke row E3 (tester): a bar chart and an elevation profile added to a layout without a position overlapped the header band and the map. Free placement has existed since rc49 (`layout-items-free-placement`), but on a crowded page (header band plus a map filling most of it) no spot fits a 120 x 80 mm chart or a 180 mm profile, and the code fell back to (10, 10), which is on top of them. A smaller item in the free strip is better than a full-size one on the map.

## Scope
`gap_options.py`: new pure `fit_free_box` (asked size first, then the same shape at 85, 70, 55 and 45 percent, never below 50 x 35 mm). `layout_chart_profile_tools.py`: `_auto_box` uses it and returns the size too; both `add_layout_chart` and `add_layout_elevation_profile` apply the smaller size and report `placement_note` ("made X x Y mm to fit"). When even the smallest size fits nowhere the item still goes to (10, 10), now with a note that it OVERLAPS and what to tell the user. Not done: the second E3 finding (the main map frame after Zoom Full shows the whole DEM extent instead of following the vector layers), which needs the tester's layout screenshot.

## Acceptance
`tests/test_layout_free_box.py::TestFitFreeBox` passes; the live test `tests/test_layout_items_render_live.py::test_a_crowded_page_gets_smaller_items_not_overlapping_ones` passes in CI; the existing three-charts test still passes; ruff and the ledger guard pass. Live: rerun row E3 step 1 on a layout made by create_print_layout.

## Guard tests
`tests/test_layout_free_box.py`, `tests/test_layout_items_render_live.py`; ledger feature `layout-items-free-placement`.

## Rollback
Revert the commit; items go to (10, 10) when no spot of the asked size exists.

## Status log
- 2026-11-08: built; offline tests pass, the live crowded-page test is new and runs only in CI (first execution). The cause (no spot of the asked size on the E3 layout) is inferred from the layout's structure and the code path, not seen: the tester's layout was not available here.
