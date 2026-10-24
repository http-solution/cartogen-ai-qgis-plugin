# PLAN-014: OCHA-style map products: credits, no-data, render checks, page sizes, profiles and branding

Status: in progress

## Goal
Take the second half of the external audit (the OCHA / cartographic compliance list) and turn only what the code supports into phased work. Each item was checked against the source on 2026-10-24; nothing was run (no QGIS in this sandbox), so every statement about rendering is marked as needing a CI render.

Two limits shape the whole plan, and the owner should confirm them:
1. **I do not have OCHA's template specification, logo files, colour values or font rules.** Anything that reproduces them from memory would be a guess presented as a standard. So the plan builds a **profile mechanism** (a file that holds page size, colours, fonts, logo path, footer wording, required elements, credit text, file-name pattern and DPI preset) and ships **no OCHA or UN marks**. The organisation supplies its own profile file and logo, the same way it already supplies its own disclaimer wording (PLAN-011).
2. The existing standards document (`docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md`, section VIII) records a metadata gap; PLAN-011 closed part of it (sources, disclaimer, prepared date). What remains is below.

## Scope
**Checked against the code (2026-10-24):**

| Audit item | Finding | In this plan |
|---|---|---|
| Basemap and data credits | No credit text anywhere on a layout. The legend deliberately excludes basemaps, and nothing replaces them, so a map with an OpenStreetMap basemap carries no "OpenStreetMap contributors" credit (the ODbL asks for one). Layer metadata is read only for the Sources line, not for web basemaps. | Phase 1 |
| Missing-data symbology | `apply_categorized_style` adds an "Unknown / No data" rule; `apply_graduated_style` was not found to do the same. QGIS draws a NULL value in a graduated field with no symbol, so those features vanish and the legend does not say so. Not yet shown by a render. | Phase 1 (CI render first) |
| Render-based QA | The QA checklist reads item ids, not pixels. A label that overflows its box, or two items that overlap, is not detected. `_fit_text_to_box` and a geometry overlap test exist for specific cases only. | Phase 1 |
| Export DPI presets and file names | `export_layout` defaults to 150 dpi, `create_print_layout` to 300; the model chooses. No naming convention for exported maps (only atlas pages are sanitised). | Phase 1: named presets (`draft`, `print`, `web`) and a file-name pattern in the profile |
| Page sizes | `set_layout_page` knows named sizes, but `create_print_layout` hard-codes A4 and positions every item for A4, so changing the page afterwards leaves items misplaced. | Phase 2 |
| Product profiles | None. | Phase 2 (mechanism), Phase 3 (branding fields) |
| Branding (logo, colours, fonts) | One setting exists: the title-bar colour. No logo item, no font choice. | Phase 3 |
| Reviewer sign-off | Not present. | Phase 3, as a footer block (prepared by, reviewed by, status, date) filled from the profile or the request; no approval workflow engine |
| COD profile | The P-code validators exist (`pcode_validation_tools.py`, the VALIDATED gate). Nothing ties a map to "uses COD boundaries". | Phase 3, as a profile flag that adds the COD credit and runs the existing P-code check |
| Locator map, graticule, north arrow, pie charts | Already built (`include_inset_map`, `_add_graticule`, `_add_north_arrow`, `add_layout_chart` accepts `pie`). | Nothing to build |

**Needs evidence before any work (no defect shown, so no code is planned):**
- *Accessibility* (colour-blind-safe palettes, alt text, tagged/accessible PDF): the PDF export uses default `PdfExportSettings` only; whether QGIS 4.2 can write a tagged PDF through the API is not known to me. A CI diagnostic that lists the available export settings comes first.
- *Multilingual and right-to-left typography* (Arabic place names are routine in this work): no handling exists in the plugin, and Qt text shaping may already be correct. A CI render of Arabic and Latin text in a layout, looked at by the owner, decides.
- *Canvas-derived map state, coverage aggregation grain, classification contracts, chart metadata, legend semantics:* the audit named them without a failing case. Each stays on this list until a concrete wrong output is shown.

**Phases (each its own pull request, stop after any):**
1. **Credits, no-data, render checks, presets** (no template needed). A credit line for web basemaps and layers with a known licence (taken from the layer's own metadata or the provider's attribution string; "credit not recorded" otherwise, never invented); a "No data" class and legend entry for graduated styles, after a CI render shows the problem; `check_layout_render` (text overflow and item overlap, from the layout's own geometry plus one rendered image); export presets and a file-name pattern.
2. **Page sizes and the profile mechanism.** `create_print_layout` gets a `page_size` (A4 default, A3, A2, A1 by owner decision; US Letter and Tabloid are not needed) by scaling its A4 geometry, with a render test per size and orientation, because the A4 geometry carries a history of overlap bugs (BUG-2026-09-11-1). A profile file (JSON, validated, loaded from the project folder or the QGIS profile folder) sets page size, orientation, required elements and DPI preset.
3. **Branding and sign-off.** Profile fields for logo path, colours, font, footer lines, reviewer block and the COD flag. The logo is a picture item from a local file the organisation supplies (URLs stay refused, as in `layout_options.py`). One example profile ships with placeholder text and an empty logo box, clearly not OCHA's.

## Phase 3 detail (written 2026-10-24, after reading map_profiles.py, layout_style.py, layout_item_tools.py and layout_export_checks.py; nothing run)
Split into three pull requests so each can be reverted alone. All new profile fields are optional; an older plugin still refuses them by name.

**3a. Logo, colours, font.**
- `logo_path` (a local file, resolved relative to the profile's own folder; URLs, UNC paths and `..` refused) and `logo_position` (`left` or `right` of the masthead). The picture item `LOGO` is added by `_style_title` before `scale_layout`, so it scales with the page; the TITLE label is narrowed by the logo width so the two never overlap (the existing overlap check proves it). Missing or unreadable file: the layout is still built, with a warning naming the path, never a silent skip.
- `masthead_colour`, `masthead_text_colour` (hex). Order of precedence: request, profile, existing Settings colour, default palette. Contrast is checked by the existing `resolve_masthead` rule (an unreadable pair is replaced and a warning says so).
- `font_family`. Checked against the fonts installed on the machine; if absent the default font is used and a warning names the missing font (a map must not silently change typeface). Applied through `text_format`, so every label, the legend and the scale bar follow. Risk: the height estimates assume an average glyph width, so a wide font can overflow a box; the geometry check reports it, and the live test renders one wide and one narrow font.
- Not planned: per-element fonts, gradients, images other than the logo.

**3b. Footer lines and reviewer sign-off.**
- `footer_lines` (up to 3 lines of 120 characters, inserted after the classification note).
- `sign_off`: `prepared_by`, `reviewed_by`, `review_date`, `status` (`Draft`, `Reviewed`, `Approved`). Rendered as one footer line. Rules that keep it honest: with no `reviewed_by` the status is forced to "Draft - not reviewed"; `Reviewed` or `Approved` without a reviewer name and a date is refused at validation. `require_sign_off: true` makes a missing reviewer a publication-gate problem (same mechanism as a missing required element, with the same reason override). No workflow engine and no stored approvals: the profile or the request supplies the text, a person supplies the truth.

**3c. COD flag.**
- `cod_boundaries: true` plus `cod_credit` (the organisation's credit wording, REQUIRED when the flag is on: I will not invent the wording of a data licence). The text joins the credits line. On a publication export the report also lists the result of the existing P-code checks for visible layers with an admin P-code field; duplicates are a warning, not a block, because a P-code field's name is not standardised.

**Tests (each fails without its feature).** Offline: validation of every new field (bad hex, path traversal, URL, sign-off status without reviewer, `cod_boundaries` without wording), the sign-off line text, precedence of colour sources. Live (CI, QGIS 4.2.2): the logo item exists with the path and a nonzero rendered area, A4 and A3 in both orientations report no geometry problem with a logo, the masthead colour is on the TITLE item, a missing font warns and a present font is on the labels, the footer shows the sign-off line, a publication export with `require_sign_off` and no reviewer is blocked then passes with one. Nothing here is hand-verified until the owner has looked at an exported map with their own logo.

**Rollback.** Revert the phase; layouts built without a profile are untouched (the new code only runs when a profile has these fields).

**Ships.** An example profile with placeholder text and no logo path (a test checks that no organisation name or mark is in it), `docs/MAP_PROFILES.md` rows, ledger entries, and the release texts at the next version bump.

## Acceptance
1. Phase 1: a layout with an OpenStreetMap basemap carries a credit; a graduated layer with NULL values shows a "No data" class in the map and the legend (after the CI render has first shown the problem); `check_layout_render` flags a deliberately overflowing label; presets and the name pattern are applied by `export_layout`.
2. Phase 2: a layout at A3 and A2, landscape and portrait, passes the overlap and on-page checks in CI; a profile file with a bad field is refused with a clear message.
3. Phase 3: a profile with a logo and colours produces a layout that shows them; the example profile contains no OCHA or UN mark.
4. Each item has a ledger entry and a test that fails without it; nothing is called hand-verified until the owner has looked at an exported map.

## Guard tests
To be listed per phase. Existing ones that must keep passing: `tests/test_layout_export_checks_live.py`, `tests/test_output_style_live.py`, `tests/test_layout_items_render_live.py`.

## Rollback
One pull request per phase; revert the phase. Profiles are opt-in files, so a revert removes the loader and leaves every existing layout unchanged.

## Status log
- 2026-10-24: plan written after reading `layout_tools.py`, `layout_options.py`, `layout_style.py`, the chart and styling tools and the standards document. No code changed. Waiting for the owner's answers on the profile approach, the page sizes needed and the order.
- 2026-10-24: owner decisions: (1) profile file mechanism, the organisation supplies its own branding and logo, nothing OCHA or UN ships; (2) Phase 1 first; (3) page sizes A4, A3, A2 and A1. Phase 1 is built on the owner's go.
- 2026-10-24: Phase 1 built (PR 404). CI results before the No data fix: both standard layouts (landscape and portrait) report no geometry problem, the deliberately bad layout is flagged for overlap, off-page and overflow, the OpenStreetMap basemap is credited in the footer, and the NULL diagnostic FAILED as predicted (control feature painted 48 pixels, the feature with no value 0), so the fix was built: a graduated style on a layer with empty values becomes rules plus a grey 'No data' rule. Deviations from the plan: the geometry checks live in the export report (`layout_problems`) instead of a new `check_layout_render` tool (no new tool to wire through the router and counts), and the blank-map image check is not built. The file-name pattern is fixed to `<title>_<date>`; a custom pattern waits for the profile file of Phase 2. Not hand-tested.
- 2026-10-24: Phase 1 merged (#404): No data class reproduced then fixed in CI, credits line (a vetted basemap credit is not repeated by QGIS's own long rights text), layout geometry checks (standard layouts report none), presets and folder names. Phase 2a built (PR 405): page sizes A4, A3, A2, A1 by scaling the finished A4 layout (`layout_page_scale.py`), not by re-deriving the geometry, so A4 is untouched (factor 1, nothing runs). The map keeps its extent. Live tests check page size, same map area, text scaled by the factor and no geometry problem for every size in both orientations. Not covered: symbol sizes of the data layers (map content is not scaled), and nobody has looked at an A2 or A1 page. Phase 2b (the profile file) is next.
- 2026-10-24: found by the Phase 2b CI run: every LANDSCAPE layout returned the warning "footer: the sources and disclaimer text may not fit" (A3, A2, A1 and A4 alike, portrait none). Cause: the footer used the generous body-panel height estimate (12 mm for three lines where about 10 fit) and kept a 1.5 mm gap above itself. Fix: a footer-specific estimate (`footer_height_mm`, line pitch 1.25) and a 0.5 mm gap; a live assertion now requires no style warning on a landscape layout with a credits line. Also seen in the same run, NOT fixed here: the elevation-profile curve is drawn with a varying amount of colour from run to run (0.013, 0.011, 0.009 on three green runs, 0.000 on one failing run, while bar, pie and line are identical every run), which points to the profile plot rendering asynchronously; a hand-made layout in `tests/test_layout_items_render_live.py` failed once on it. Recorded as an open finding.
- 2026-10-24: Phase 2a merged (#405): page sizes A4, A3, A2, A1; live tests passed for every size in both orientations. Phase 2b built (PR 406): map profiles (`map_profiles.py`, `docs/MAP_PROFILES.md`, `docs/examples/map_profile_example.json`). Fields in this phase: page_size, orientation, export_preset, file_name_pattern, required_elements; logo, colours, font and sign-off are Phase 3 and an unknown field is refused by name so a later-version file cannot look as if it worked. No organisation's name or mark ships (a test checks the example). The profile is stored on the layout so a later export uses its pattern, preset and required elements; the QA checklist and the publication check use its required elements. Not hand-tested.
- 2026-10-24: Phase 3 detailed plan written (3a logo, colours, font; 3b footer lines and sign-off; 3c COD flag). No code changed. Waiting for the owner's answers on logo formats, sign-off strictness and COD wording.
- 2026-10-24: owner decisions for Phase 3: PNG and JPG logos only; sign-off is text, blockable with require_sign_off; COD wording comes from the profile; order 3a, 3b, 3c. Phase 3a built (logo_path, logo_position, masthead_colour, masthead_text_colour, font_family; `masthead_split`, `resolve_masthead_colours`, `installed_font` in layout_style.py). Not run in QGIS; CI live is the first execution. Not covered: legend and scale bar fonts follow the profile font only if QGIS keeps the family on the text format (checked only on the title).
