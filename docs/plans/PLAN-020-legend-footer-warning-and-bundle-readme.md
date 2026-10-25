# PLAN-020: legend cut off in exports, footer "may not fit" warning, precise bundle README

Status: planned

## Goal
Three findings from the owner's hand run of the 1.18.0 precise test (2026-10-25, `4_RESULTS.csv` plus the three exported PDFs): (1) the legend frame cuts its entries off at the bottom in every exported layout; (2) `create_print_layout` warns that the footer text "may not fit" on layouts whose exported PDF shows the full text; (3) the precise hand-test bundle has no "Updating an existing install" section and its OI-224 row expects version 1.16.1. After this: an exported legend is never cut mid-entry (or says plainly that it dropped entries), the footer warning appears only when the text really does not fit, and the bundle's instructions match the bundle.

## Scope
In:
- Finding 1: find why the legend frame clips (fixed `legend_h` in `layout_tools.py`, 35 mm portrait and 88 mm landscape, against a legend that has more entries than fit; whether `resizeToContents` is switched off by the later `attemptResize`), then make the legend either fit (shrink the symbol and text size in steps, or give the legend the free space) or keep only the entries that fit and add a one-line note naming how many were left out.
- Finding 2: find why `_style_footer` still ends with `fits == False` on A4 landscape (candidates, all unverified: the measured height in the owner's Windows font is larger than the PDF shows; `_clearance_above` counts the scale bar or north arrow as in the way; the bottom gap of 0.5 mm leaves the last line about 3 mm from the page edge). Fix the cause, or make the warning say which of the two limits was hit.
- Finding 3: in `tools/build_lean_bundle.py`, add the update-in-place steps to the bundle README (taken from `docs/LIVE_TEST_rc37_README.txt`, which is the text the OI-224 row names) and make the OI-224 row expect the bundle's own version, read from `metadata.txt` instead of a typed number.
Out: the duplicate CartogenAI log tab, the A5 contour failure note and the `Layout_` name prefix (separate findings, not planned here); any change to the footer disclaimer wording; a new release (the owner decides when).

## Facts found before building
- All three exports (`Footer_Fit_Rev.pdf`, `Layout_Disclaimer_Test.pdf`, `Profile_Test_Signed.pdf`) show the legend frame ending in the middle of an entry (`dem_classes ... 1`, `Bed Elevation`, `dem`). The test project holds many raster layers, so the cut may be worse than in a normal project; that has not been checked, and no exported layout of a small project has been looked at for this.
- The same three PDFs show the footer text complete and unclipped; on A4 landscape its last line sits about 3 mm above the page edge. The warning text is `footer: the sources and disclaimer text may not fit in the space available` (`layout_style.py`, `_style_footer`), raised only when `plan_footer_growth` still reports no fit after `_reclaim_from_map`.
- The precise bundle's README (`build_lean_bundle.py`) lists the folders and the cost note only. `docs/LIVE_TEST_rc37_README.txt` holds the "UPDATING AN EXISTING INSTALL, A) UPDATE IN PLACE" text the OI-224 row points to.
- None of this can be reproduced here: the layout code needs a real QGIS. The CI live job (QGIS 4.2.2) can build a layout and measure it.

## Acceptance
1. Offline test: a pure function that decides how many legend entries fit a given height, and that the note names the number left out; plus a test that the bundle README contains the update steps and the OI-224 row names `metadata.txt`'s version. CI-only.
2. CI live test (QGIS 4.2.2): a layout for a project with more legend entries than the frame holds has either a frame tall enough for every entry or a legend with a note, never an entry cut in half (checked by comparing the legend's measured content height with its frame height).
3. CI live test: A4 landscape and A3 portrait layouts with the default disclaimer, three profile footer lines and the sign-off line return no footer warning, and the footer label's bottom edge is inside the page.
4. Hand test (owner): re-export the three PDFs from the 1.18.0 hand-test project with the next build and look at the legend and footer. Not done until the owner has looked.

## Guard tests
To be named when written (a new class in `tests/test_layout_legend_live.py` and `tests/test_layout_footer_text.py`, and a bundle test in `tests/test_test_bundle.py`); the ledger entry is added with the first code change.

## Rollback
Revert the pull request. The legend and footer geometry are computed at layout creation only; existing layouts in saved projects are not changed.

## Status log
- 2026-10-25: plan written after the owner's 1.18.0 precise hand run. No code changed. Findings 1 and 2 need a diagnostic live test first (measure the legend content height against its frame; print the footer's needed and available height) so the cause is read from CI output, not guessed.
