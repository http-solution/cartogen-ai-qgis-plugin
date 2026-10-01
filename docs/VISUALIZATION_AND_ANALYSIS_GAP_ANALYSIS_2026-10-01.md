# Visualization, styling and analysis gap analysis (2026-10-01)

Dated snapshot. Method: read the registry and the tool code (not the docs), counted what could be counted, and for each gap
say whether it is closed in PR (this branch, `claude/viz-gap-analysis`), how it was checked, and what is still open. Anything
"verified" means a test that runs in CI on real QGIS 4.2.2; nothing here has been looked at on a real canvas by a person yet.

## 1. What exists today

- **180 registered tools** in 31 files. Largest groups: vector (43), raster (21), styling (14), humanitarian data (10),
  logistics (9), export (8).
- **Styling toolkit (14 tools + 4 representation tools):** categorized, graduated, graduated-symbol, rule-based, heatmap, point
  cluster, colour, transparency, layer order, save/load QML, SLD export; plus `recommend_visualization_method`,
  `analyze_layer_for_visualization`, `recommend_map_representation`, `apply_recommended_representation`,
  `explain_current_representation`. This is a capable set. The weakness was never "no styling tools", it was that
  **most tools that create layers never call them**: styling depended on the model remembering to ask.
- **Automatic style profiles** (`map_intelligence.STYLE_PROFILES`): five polygon profiles and one line profile (route casing).
  Only some tools call `process_map_output`.
- **Print layout:** one tool, `create_print_layout`, with map, title, legend, scale bar, north arrow, CRS/scale row, graticule,
  inset map, body text and a fixed disclaimer footer; plus atlas export and item-text editing.
- **Processing allowlist:** 37 algorithms, all derived from algorithms the codebase already called.

## 2. Gaps found (with evidence from the code)

### Visualization / styling
| # | Gap | Evidence | Status |
|---|---|---|---|
| V1 | **WorldPop population raster drawn in QGIS's default grey** | `add_worldpop_population_layer_main_thread_phase` adds the layer with no renderer call | **Closed**: pseudocolour ramp, zero cells transparent, stops crowded toward the low end for heavy-tailed data. Live-tested (transparent first stop, opaque last stop at the true maximum). |
| V2 | **Density surface (`hotspot_analysis`) and interpolated surface (`interpolate_surface`) in default grey** | both add a `QgsRasterLayer` and return, no styling | **Closed** (density ramp / opaque ordered surface ramp). Live-tested for the ramp builder; the two tools' own wiring is offline-only. |
| V3 | **Processing results unstyled** | `run_allowlisted_processing_algorithm` styled nothing it created | **Closed**: buffer/hull/Voronoi get the proximity profile, clip/intersection/difference/union/dissolve the selection overlay, path/service-area the route line, points one consistent look, slope/aspect/IDW/TIN/reclass/cell-statistics a surface ramp, kernel density the density ramp. Live-tested for buffer and slope. |
| V4 | **Tabular points in a random colour** | `load_tabular_data_as_layer` adds the layer unstyled | **Closed** (one consistent point look; live-tested). `add_layer_from_path` deliberately left alone: it may load a layer that carries its own `.qml` style. |
| V5 | **Legend lists layers that are not on the map** | `QgsLayoutItemLegend` left in auto-update mode: every project layer appears, including hidden helper layers and the basemap | **Closed**: explicit legend model of the visible thematic layers only, filtered to the map extent. Live-tested (hidden scratch layer and a `_lines_` helper excluded). |
| V6 | **Print layout typography and panels** | no `QgsTextFormat`, no frames, no backgrounds anywhere in `layout_tools.py`; the title was a default-font label | **Closed**: 20 pt masthead title (light on dark slate), panel text 9 pt, info 8 pt, legend title/item sizes, footer 7 pt italic, thin frames and a light background on the legend and body panels, a frame on the map and inset. Live-tested (size, background, frames). **Not looked at on a rendered page by a person.** |
| V7 | **No preparation date or classification on a layout** | none in the code | **Closed**: "Prepared YYYY-MM-DD" in the info row; footer gets `CLASSIFICATION: SENSITIVE/RESTRICTED -- ` when any visible layer carries that tag. Live-tested. |
| V8 | Routing/reach results in defaults | see PR #109 | Closed there (cost-graded roads, grouped reach polygons, red unreachable facilities). |
| V9 | Raster legends are bare numbers | ramps carried numeric labels only | **Closed (live test written, first run pending)**: the colour-ramp legend is continuous and its title carries the unit ("People per cell", "Slope (degrees)", ...) via `QgsColorRampLegendNodeSettings`. |
| V10 | Labels (facility names, admin names) are not applied automatically | `apply_labels` exists, no tool calls it | **Closed (first CI run pending)**: layers of at most 60 features with a readable name field (`name`, `name_en`, `admin1Name_en`, ...) are labelled with `apply_labels`' halo style: loaded facility tables, admin boundaries, access-classified facilities, point results. Larger layers stay unlabelled. The 60 is my choice (`AUTO_LABEL_MAX_FEATURES`). |
| V11 | No access-map layout | the layout shows whatever the canvas shows | **Closed (first CI run pending)**: `create_print_layout(template="access_map")` fits the map to the reach layer when no zoom layer is given, lists reach polygon, access points and cost-graded roads first in the legend, and adds a "how to read this map" body text for the layers present when none is given. |
| V12 | The graded roads are straight segments between road vertices | `_cost_graded_roads` | Matches the road geometry (edges are consecutive vertices); only a rendering choice if smoothing is wanted. Not planned. |

### Analysis (what QGIS offers that the tools did not expose)
The registry had no wrapper and the allowlist had no entry for several basic humanitarian-analysis algorithms. Added to the
allowlist, **each checked against the real QGIS 4.2.2 registry in CI** (a wrong id fails the test):

| Algorithm | Use in this project |
|---|---|
| `native:countpointsinpolygon` | facilities / incidents per admin area (the coverage-gap table); **run end-to-end in CI** |
| `native:creategrid` | rectangle/hex grids for density and exposure aggregation |
| `native:extractbylocation` | facilities inside a catchment or admin area as a new layer |
| `qgis:statisticsbycategories` | count/sum/mean per category |
| `native:dbscanclustering`, `native:kmeansclustering` | clusters of incidents / facilities |
| `native:rastersampling` | population at facility points |
| `native:zonalstatisticsfb` | zonal statistics (current form of the old `qgis:zonalstatistics`) |
| `native:reclassifybytable`, `native:cellstatistics` | suitability classes, multi-raster statistics |

**Owner decision (2026-10-01): the ten additions stay.** **Deliberately not added:** `extractbyexpression`, `aggregate`, `refactorfields`, `fieldcalculator`. They take QGIS expressions;
the tool's safety argument is that it never evaluates code. This is a trust-boundary change and is **flagged in the PR for the
owner**.

**A bug found while auditing this** (not a styling gap): `run_allowlisted_processing_algorithm` forced `"memory:"` as every
output and expected a layer back. A raster algorithm cannot write to `"memory:"` and returns a *file path*, so every raster
algorithm on the list (slope, aspect, hillshade, raster calculator, IDW, TIN, kernel density, ...) either failed or ran and
reported "no new layer output". Fixed: raster algorithms get `TEMPORARY_OUTPUT`, the returned file is loaded as a layer, then
styled. Live-tested with `native:slope` on a synthetic DEM (the layer is present, valid and styled).

Not wired and worth considering next: `native:serviceareafromlayer` (all facilities in one call, instead of one run each),
`native:joinbynearest` is on the list but not described to the model, `gdal:contour`, `native:rasterize`/`gdal:polygonize`
for moving between raster and vector results, `native:nearestneighbouranalysis` (HTML output, needs a different result path).

## 3. What a smoke test should look for (the visible improvement)
1. Fetch population for an area: the raster should be a warm ramp with empty land transparent, not grey.
2. Run a service area: roads in cost bands (PR #109), reach polygons in one group with the headline on top.
3. `create_print_layout` after that: dark masthead title, framed legend that lists **only** what is visible on the map,
   "Prepared <date>" in the info row, a classification prefix if a SENSITIVE layer is visible.
4. `run_allowlisted_processing_algorithm` with `native:slope` / `native:countpointsinpolygon`: the result loads and looks styled.

## 4. Still open (honest list)
- No rendered inspection: everything above is verified by property tests (renderer type, ramp stops, text size, frames, legend
  contents), not by looking at the exported page. The PNG export is only checked to exist and be non-trivial in size.
- The palette is mine (slate masthead, YlOrRd-style population ramp, viridis-style surface); it should be judged on your basemap. I cannot render a page here, so what changed is that the masthead colour is now a setting (Settings > Limits > "Print layout title colour", `#rrggbb`, light colours get dark text); the raster/reach colours are still code constants.
- The processing-allowlist extension needs your decision (section 2).
