# PLAN-016: findings from the first rc50 hand run (profile snapshot, export gate and lineage, contours routing, footer estimate)

Status: planned

## Goal
Turn what the first desktop run of the rc50 bundle (QGIS 4.2.3, 20 of 87 rows, one chat for all rows) showed into small, tested fixes, and settle OI-150 properly. Nothing here is built yet; nothing was run in QGIS by me. Evidence: the owner's `4_RESULTS.csv`, the OI-150 `context.json` (evidence folder t23) and the A22 screenshot; the code facts below were read on 2026-10-24.

Hand-run results that shaped this plan: Pass: OI-S1, OI-S2, OI-128, A14, A15, A17, A19, A24. Partial: A16, A18, A20 to A23, A25 to A28 (most only because the exported page was not opened). Fail as recorded: OI-150 and A29. Not yet re-run: A29 on a layout built after the edit, OI-150 with the merged layer present.

## Scope
**1. Profile snapshot at export (A29).** Cause found by code read: `create_print_layout` stores a copy of the profile on the layout (`cartogen_ai/profile_json`), and `gate_export`, `export_report` and the QA checklist read that copy. A27 built "Profile Test" before `require_sign_off` was added to `handtest.json`, so A29 exported a layout whose copy had no such setting. The rc50 row text also did not say to rebuild the layout.
Design (needs owner confirmation, see Decisions): store the profile NAME beside the copy; at export read the file again by name. Requirements (`require_sign_off`, `required_elements`, `export_preset`, `file_name_pattern`) come from the current file, so a newly added requirement applies. Whether the sign-off is SATISFIED is judged by what is printed on the layout (the stored copy), because the footer text is fixed at build time: a review added to the file later still needs the layout rebuilt so the map itself says "Reviewed". If the file is missing or invalid the stored copy is used and the result says so.

**2. Export gate follows lineage (found while reading OI-150).** `protected_in` in `layout_export_checks.py` reads only a layer's own tag (`get_layer_sensitivity`). The cloud (egress) gate in `agent_orchestrator.py` also follows lineage (`effective_source_names`), so a merged or renamed output of a SENSITIVE layer is gated there but a map drawing it would export with no card. Not yet shown by a run. Design: one shared helper (own tag, else strictest tag among lineage sources, followed through sources that are themselves derived, by id so a rename does not hide it), used by the export gate, the export report, the atlas gate and the QA checklist; the cloud gate is switched to the same helper so the two cannot drift. The Sensitivity dialog shows "Protected through lineage from X (SENSITIVE)" instead of a bare "untagged", which is what misled the first run.

**3. OI-150 itself.** Its row expected "Layer Data Sensitivity shows it protected", which is not what the cloud-gate fix did; the dialog reads the layer's own tag. Row to be reworded to the real check: after the merge and rename, ask the assistant a question about the renamed layer with Cloud data protection on Block; a card means the gate holds. The run could not do this because creating the merged layer meant clicking "Send to cloud once" for the SENSITIVE fixture, which the owner has to do. CI covers the same path (`tests/test_egress_flow_live.py`: merge, rename, rename, read) but CI is not a hand-verified pass. OI-150 stays open until the owner's pass.

**4. "Draw contour lines of the dem" restyled the DEM (A18).** Expected `create_contours`; the router chose a styling tool. Reproduce offline first with the router and the tool-selection tests on that exact prompt (and "contours every 100"), then fix the keyword or tool-description gap and add the prompt to the plain-language regression list.

**5. Footer needs more room than the estimate (A22).** The export reply reported a footer box of about 16 mm with text needing about 18 mm on A4 landscape in desktop QGIS; CI (Linux fonts) never showed it. The estimate assumes an average glyph width of half an em, which Windows UI fonts exceed. Design: when QGIS is available, measure the real wrapped text height with the label's own size calculation (`QgsLayoutItemLabel.sizeForText`) instead of the character estimate, for both the footer growth and the geometry check, so they agree with each other and with the real font. Keep the estimate as the fallback.

**Out of scope:** the 67 skipped rows; redesigning the Sensitivity model; tagging derived layers on disk (lineage is followed instead, so no new stored state).

## Decisions needed from the owner
- Item 1: current file for requirements, printed footer for sign-off satisfaction (recommended), versus snapshot only plus a clearer row text.
- Item 2: follow lineage in the export gate (recommended: no new stored state, matches the cloud gate) versus copy the tag onto every derived layer.
- Item 3: who clicks "Send to cloud once" for the OI-150 fixture re-run.

## Acceptance
1. A29: a layout built before `require_sign_off` was added, exported as a publication after the file changed, is refused; a layout whose footer says Reviewed passes; a deleted or broken file falls back to the stored copy with a note.
2. A layout drawing a layer made by merge or rename from a SENSITIVE layer gets the confirm card on export, in single, atlas and publication exports; a renamed source still counts; an unrelated layer does not. The Sensitivity dialog names the lineage source.
3. "draw contour lines of the dem" reaches `create_contours` in the offline selection test.
4. A4 and A3 landscape layouts with a Sources line, a Credits line, a profile footer line and a sign-off line report no footer overflow in CI, and the geometry check and the footer growth use the same measure.
5. Each fix has a test that fails without it; nothing is called hand-verified until the owner's re-run rows pass.

## Guard tests
Existing and must keep passing: `tests/test_plan014_signoff_live.py`, `tests/test_plan014_profiles_live.py`, `tests/test_layout_export_checks_live.py`, `tests/test_export_confirm_flow_live.py`, `tests/test_egress_flow_live.py`, `tests/test_layout_export_checks.py`, `tests/test_layout_footer_text.py`, `tests/test_plan014_pagesize_live.py`. New ones are listed per item when built.

## Rollback
One pull request per item, in the order 1, 2, 4, 5 (3 is a row and plan text only). Reverting item 1 restores snapshot-only gating; reverting item 2 restores own-tag-only export gating (the cloud gate keeps its current behaviour either way); reverting item 5 restores the character estimate.

## Status log
- 2026-10-24: plan written from the first rc50 hand run and a read of `map_profiles.py`, `layout_export_checks.py`, `agent_orchestrator.py` (egress lineage), `lineage.py` and `layout_style.py`. No code changed. Waiting for the owner's decisions on items 1 to 3 and for the A29 retest on a freshly built layout, which would confirm the cause of A29.
- 2026-10-24: PLAN-016 merged (#412). Owner said go on item 1 (the recommended design). Built: the layout stores its profile name; `current_profile` in layout_export_checks.py re-reads the file for requirements and keeps the printed sign-off; used by the publication gate, the export report, export_layout (preset and file name pattern) and the QA checklist; `profile_note` when the file cannot be re-read. Offline tests and live tests written; not yet run in QGIS. Status stays planned until all items are built.
