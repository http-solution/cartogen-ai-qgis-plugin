# PLAN-020: legend cut off in exports, footer "may not fit" warning, precise bundle README

Status: abandoned

## Goal
Three findings from the owner's hand run of the 1.18.0 precise test (2026-10-25, `4_RESULTS.csv` plus the three exported PDFs): (1) the legend frame cuts its entries off at the bottom in every exported layout; (2) `create_print_layout` warns that the footer text "may not fit" on layouts whose exported PDF shows the full text; (3) the precise hand-test bundle has no "Updating an existing install" section and its OI-224 row expects version 1.16.1. After this: an exported legend is never cut mid-entry (or says plainly that it dropped entries), the footer warning appears only when the text really does not fit, and the bundle's instructions match the bundle.

## Scope
In (one pull request, one build, no release candidate per fix):
- Finding 1 (legend): the cause is known from the owner's own layout (below). Fix: the legend frame keeps its place but its entries are fitted to it, in steps (smaller symbols and text, then only the entries that fit with a one-line note naming how many were left out). Never an entry cut in half.
- Finding 2 (footer warning): measure the footer with QGIS's own `QgsLayoutItemLabel.sizeForText()` (the size the renderer will use) instead of the Qt metrics estimate, keeping the estimate as the fallback; warn only when that real size does not fit. The tool result and the evidence folder also record the needed and available height in mm, so a wrong warning on the owner's machine can be diagnosed from files the plugin already writes, with no further test.
- Finding 3 (bundle): the bundle README gets the update-in-place steps (from `docs/LIVE_TEST_rc37_README.txt`); the OI-224 row reads the version from `metadata.txt`.
- A hand-test file with no model calls (see Acceptance 4).
Out: the duplicate CartogenAI log tab, the A5 contour failure note and the `Layout_` name prefix (separate small plan after this one); footer disclaimer wording; a release (the owner decides when).

## Facts found before building
- Read from the owner's returned `A15_logo.qgz` (2026-10-25), not guessed: the legend of `Layout_Footer_Fit_Rev` (A3 portrait) is 254.5 x 49.5 mm with `resizeToContents="0"` and lists seven layers (`dem_classes, mesh1, dem2, dem, roads, towns, districts`); 49.5 mm is exactly the fixed 35 mm legend of the portrait template scaled for A3. The A4 landscape `Layout_Disclaimer_Test` legend is the fixed 95 x 88 mm. So the cut-off is the fixed frame with automatic resizing off, and it appears whenever the entries need more height than the template gives. It is not caused by the test project alone.
- Same file, finding 2: the A4 landscape footer is 275 x 17.1 mm, its bottom edge at 209.5 mm on a 210 mm page, and its top edge touches the scale bar (about 0 mm clearance). It sits in the only space left, so any excess in the estimate raises the warning even when the exported text fits (the PDF shows the full text). Whether the estimate is high on the owner's Windows font is not established; a Linux CI font will not match, which is why the plan records the numbers on the owner's machine instead of relying on CI alone.
- The three exported PDFs show every footer line, the logo, the masthead and the sign-off complete and unclipped.
- The precise bundle's README lists folders and the cost note only; the OI-224 row names an "UPDATING AN EXISTING INSTALL" section that is not in it and expects 1.16.1.
- The layout code needs real QGIS; the CI live job (QGIS 4.2.2) can build and measure layouts.

## Acceptance
1. Offline (CI): a pure function that decides how many legend entries fit a height and builds the "N more not shown" note; the bundle README contains the update steps; the OI-224 row names the version from `metadata.txt`.
2. CI live (QGIS 4.2.2): a layout built from a project with seven layers including rasters, in A4 landscape and A3 portrait, has a legend whose content height is not larger than its frame (or which carries the note); never a cut entry. The test builds the same seven-layer shape as the owner's file.
3. CI live: A4 landscape and A3 portrait layouts with the default disclaimer, three profile footer lines and the sign-off line return no footer warning, the footer's bottom edge is inside the page, and the recorded needed height is not larger than the box.
4. Hand test, kept as small as possible: one PyQGIS console script in the next bundle that calls the plugin's own layout function on the owner's open project and exports the PDFs, with no model calls (so no API cost), plus the needed/available footer heights printed on screen. The owner runs it once and returns the folder. Nothing else is asked of the owner for these three findings.

## Guard tests
Named when written: a new class in `tests/test_layout_legend_live.py`, one in `tests/test_layout_footer_text.py`, and a bundle test in `tests/test_test_bundle.py`; the ledger entry is added with the first code change.

## Rollback
Revert the pull request. Geometry is computed when a layout is created; layouts already saved in projects are not changed.

## Status log
- 2026-10-25: plan written after the owner's 1.18.0 precise hand run. No code changed. Findings 1 and 2 need a diagnostic live test first (measure the legend content height against its frame; print the footer's needed and available height) so the cause is read from CI output, not guessed.
- 2026-10-25: plan revised the same day after the owner objected that each hand test costs time and money. The legend cause was read from the owner's returned layout file (fixed frame, automatic resizing off); the first version of this plan asked for a diagnostic CI test and a hand re-run. Now: one pull request, one build, the footer numbers recorded by the plugin itself, and a model-free script for the one remaining hand check.
- 2026-10-25: folded into PLAN-021 work package B (legend, footer, names) and G (bundle README and the model-free check). This plan stays as the record of how the causes were found; the work is tracked in PLAN-021.
- 2026-10-28: status set to abandoned from this plan's own log and the GitHub release list (master list HY-1): folded into PLAN-021 work packages B and G as its own last log line says; kept as the record of how the legend and footer causes were found.
