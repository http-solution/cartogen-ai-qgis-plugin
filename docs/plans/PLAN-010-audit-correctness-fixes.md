# PLAN-010: correctness fixes from the external architecture and cartography audit

Status: in progress

## Goal
Fix the audit findings that were checked against the code and shown to produce silently wrong output. Nothing else from the audit is in this plan.

## Scope
In (each verified in the code on 2026-10-24):
1. `obfuscate_sensitive_points`, method `admin_unit_snap`: the admin polygons were indexed and matched in their own CRS, but the point was tested untransformed and the centroid was written into the point layer's CRS untransformed. With two different CRSs the point was matched to nothing or to the wrong place, and the tool still said success. Now the point is moved into the admin CRS for matching and the centroid is moved back.
2. `generate_sector_coverage_report`: a group with no usable target (missing, unparseable or zero) has `coverage_percent = None` in the table but was charted as 0. Now it is left out of the chart, stays in the table, and is named in `no_target_groups` and a `chart_note`.
3. `generate_map_product_qa_checklist`: an exception while reading features set "no numeric field", so the classification check said "No concern found". Now it reports `status: unknown` ("could not be completed, not a pass") and logs the exception type.
4. `_replace_named_layer`: the earlier result was removed before the replacement was added, so a failing `addMapLayer` left neither. Now the replacement is added first; if removing the old one then fails, the new one is taken out again.
5. `_replace_named_layer`: a failed attempt to keep the result in the results GeoPackage was dropped silently. Now it adds a note to the reply (expected non-persistence such as "project not saved yet" stays silent).

Out (audit findings withdrawn or deferred, by owner decision): repository-wide exception-handling refactor (withdrawn: most catches are deliberate), cross-layer transactions (withdrawn: no failing case), export and publication gates, reliability work on threads and Processing, structural refactors, and the OCHA template feature set. These need their own plans.

## Acceptance
1. Each fix has a test that fails without it: offline in `tests/test_plan010_correctness.py`, live in `tests/test_plan010_live.py` (CI only; written without a QGIS install).
2. `ruff check .` clean; the full unit suite and the ledger guard pass.
3. Nothing is called hand-verified.

## Guard tests
`tests/test_plan010_correctness.py`, `tests/test_plan010_live.py`.

## Rollback
One pull request; revert it.

## Status log
- 2026-10-24: audit claims 1 and 2 read in the code and confirmed; the exception-handling and replacement-order cases came from the owner's corrected audit and were read in the code before fixing. Fixes and tests built; CI result to be recorded here.
