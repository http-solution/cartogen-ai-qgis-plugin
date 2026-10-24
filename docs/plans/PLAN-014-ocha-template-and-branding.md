# PLAN-014: OCHA-style map products: credits, no-data, render checks, page sizes, profiles and branding

Status: planned

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
