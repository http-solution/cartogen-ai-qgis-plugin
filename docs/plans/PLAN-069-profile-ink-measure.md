# PLAN-069: Measure "drew data" so a pale layer colour is not read as empty (DEF-38)

Status: in progress

## Goal
`test_the_rendered_items_are_not_empty` failed once on `main` at 59e3b76 (CI run 42558613090) with "profile: coloured 0.000". The run kept its pictures: the profile curve is there, drawn in a muted green `(121, 146, 108)`. The render was not empty; the measure was wrong. QGIS gives each layer a random profile-line colour, and this one fell just under the test's threshold (colour-channel spread 38, needed 40). The tool's own check (`render_check`, saturation above 60) has the same weakness in a worse form: the pale line chart of the same run, `(172, 196, 157)`, has saturation 51 and would be reported as "drew no data", a false warning to a user. The earlier hypothesis (the profile renders asynchronously and a render taken too early is empty) is rejected: QGIS 3.44's exporter renders non-preview items with `generateSynchronously()`, and the saved picture shows the curve.

## Scope
`layout_chart_profile_tools.py`: new pure `is_data_ink` (a pixel counts when its channel spread is at least 20, so neutral white, black and greys never count and any layer colour does); `_render_check` uses it. `tests/test_layout_items_render_live.py` uses the same function in `colour_stats` and in the five-render test, so the test and the tool cannot disagree. No change to the minimum pixel count.

## Acceptance
`tests/test_layout_item_ink.py::TestIsDataInk` (the colours measured from the CI pictures) passes offline; the live render tests pass in CI; ruff, mypy and the ledger guard pass. Live: add a chart and a profile in a real project; `render_check.drew` is true whatever colour the layer drew in.

## Guard tests
`tests/test_layout_item_ink.py`, `tests/test_layout_items_render_live.py`; ledger feature `layout-items-say-whether-they-drew`.

## Rollback
Revert the commit; the old thresholds (spread 40 in the test, saturation 60 in the tool) return.

## Status log
- 2026-11-09: cause found from the failed run's saved pictures (`items_profile.png`, `items_line.png`), measured with a PNG reader: curve `(121, 146, 108)`, spread 38, saturation 66; line `(172, 196, 157)`, spread 39, saturation 51; the five good renders of the same item had `(170, 5, 145)`. Built; offline tests pass; CI only for the live part. Not verified: that 20 never lets a coloured axis, grid or text pixel through on a real layout; the pictures of three runs show neutral axes and text.
