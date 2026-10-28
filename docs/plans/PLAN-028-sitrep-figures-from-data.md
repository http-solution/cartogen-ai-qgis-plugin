# PLAN-028: sitrep key figures come from the data or are marked

Status: in progress

## Goal
In the 1.18.4 smoke run (row B8) a model read only the field names of `admin_units_fixture`, then typed key figures 120,000 / 85,000 / 45,000 into `create_print_layout`; the layer held 94,000 / 76,000 / 52,000. A number on a map product that is not in the data is the worst failure this tool can have, and the prompt rule "copy figures from a tool result" did not stop it. This makes the tool check, not the model.

## Scope
In:
1. `key_figures_from` on `create_print_layout` (`{layer_name, label_field, value_field, top_n, order}`): the tool reads the figures from the layer, largest first, formatted with thousands separators. They cannot be mistyped.
2. A check on typed `key_figures`: each figure's number must exist in the project's data, as an attribute value of a numeric field, or as that field's total, count, minimum, maximum or mean, at the precision it was written with. A figure that does not is printed with `[not found in the project data]` on the layout and listed in `sitrep_warning` of the reply, with the instruction to use `key_figures_from`. The layout is still made; nothing is refused.
3. Text with no number (for example "rising") is not checked.
Out, with reasons:
- Refusing the layout: figures from a tool result that is not written to a layer (for example the population-gap totals) are real and would be refused wrongly; the marker is honest about what could not be matched and lets the reader decide.
- Figures in `body_text` (the summary paragraph): free text, not checked. Open.
- Raster statistics as a source of figures: not in the pool. A figure taken from a raster is marked until it is written to a field.

## Acceptance
1. Offline suite, ruff and ledger guard pass; CI live passes the three live tests in `tests/test_layout_figures_guard.py` (written without a local QGIS: CI's first run is their first execution).
2. Hand (owner): rerun B8 with the 1.18.5 package. Either the layout shows the three highest `people_in_need` values from the layer, or a typed wrong figure carries the marker and the reply names it.

## Guard tests
tests/test_layout_figures_guard.py::TestFigureGrounding::test_the_b8_figures_are_flagged_and_the_layer_figures_are_not
tests/test_layout_figures_guard.py::TestSitrepLayoutMarksUnverifiedFigures::test_typed_figures_that_are_not_in_the_layer_are_marked_and_reported

## Rollback
Revert the commit; `key_figures` behaves as before (no check, no marker).

## Status log
- 2026-10-28: plan written from the B8 evidence (`create_print_layout` arguments in the plugin evidence folder). Code and tests written; offline half passes. Not hand-verified.
