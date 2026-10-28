# PLAN-029: side effects found in the 1.18.4 smoke run

Status: in progress

## Goal
Three unrequested side effects the 1.18.4 run showed (master list DEF-5 and DEF-19), fixed without touching a release: no version change, 1.18.6 stays unreleased until the 1.18.5 hand rows (Section P) have been run.

## Scope
In:
1. DEF-5: `calculate_damage_exposure_severity` left its working columns (`chg_mean`, `chg2_mean`, `hzd_mean`) on the user's admin layer, a new set every run, and in the file on a file-based layer. It now deletes exactly the columns that run created, once their values are read, and says so (`temporary_fields_removed`). A column the user already had under the same name is never touched; a layer being edited, or a format that cannot delete fields, keeps the columns and the reply says so (`temporary_fields_kept`).
2. DEF-19: a fetch that matches nothing (UCDP, USGS, EONET, GDACS) no longer adds an empty layer when none of that name exists (`empty_fetch_result`); the reply says no layer was added. A layer that already exists is still replaced as before.
3. DEF-19: a literal `&nbsp;` in a model reply is shown as a space.
Out: A12's hidden `buffer_output` and `deletecolumn_output` layers (they come from a Processing step the model chose; no code path found without the evidence), A7/A9 worldwide layers (GDACS fixed in 1.18.5; USGS has no country filter, the model has to give an area, which the geocode bounding box now makes possible).

## Acceptance
1. Offline suite, ruff, ledger guard pass; CI live passes `tests/test_damage_direction_live.py` (two new tests) and `tests/test_empty_fetch_live.py` (written without a local QGIS: CI's first run is their first execution).
2. Hand (owner): after the damage score on a loaded layer, the layer's field list holds no `chg_mean`; a UCDP request for a year with no events adds no layer.

## Guard tests
tests/test_damage_direction_live.py::TestDamageDirection::test_a_first_run_leaves_no_zonal_columns_behind
tests/test_damage_direction_live.py::TestDamageDirection::test_the_working_zonal_columns_are_removed_but_the_users_own_column_is_kept
tests/test_empty_fetch_live.py::TestEmptyFetchResult::test_says_no_layer_was_added_and_why_the_model_should_stop
tests/test_chat_formatting.py::TestModelBreaksAndComparisonSpans::test_a_model_written_nbsp_is_a_space_not_literal_text

## Rollback
Each item is its own hunk; revert the commit.

## Status log
- 2026-10-28: plan written; items 1 to 3 built with tests. Offline half passes. Not hand-verified.
