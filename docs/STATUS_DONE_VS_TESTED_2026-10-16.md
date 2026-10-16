# Roadmap completion: what was done, and how far each piece was tested (2026-10-16, refreshed after rc45)

**State of main:** 294 tools; 427 Processing algorithm ids on the allow-list. Every roadmap package (A to J), the gap-closing package and the integration audit are merged.
Release candidates rc42, rc43, rc44 and rc45 are published as pre-releases on GitHub (rc45 built from `39e72ccb`, zip SHA-256
`149fae0e…84c7`). Nothing has been uploaded to plugins.qgis.org by the assistant; that step belongs to the owner. rc44 carries packages F to I, the
gap-closing tools and the audit fixes. rc45 adds only the four fixes below and an API-name check; it adds no tools.

## rc45 (#352, #353; hand-test sheet and bundle builder #354)
The QGIS 4.2.3 Developer Reference was used to compare every QGIS method name called in the code with the 20,064 names it lists. Four calls named
methods that do not exist; all four were in published rc44 (one since rc43), and rc45 fixes them:
- `zoom_history` (rc43): never worked on a real canvas; now compares the extent before and after and returns an error when there is no earlier or later extent.
- `diagnose_topology`: now uses `isGeosValid()`.
- Proxy detection: now uses `fallbackProxy()` (the wrong name had been hidden by `contextlib.suppress`).
- Point-displacement representation: removed the call to the nonexistent `setCircleRadiusSymbol`.
New guard: `tests/test_pyqgis_call_names.py` fails on any QGIS call name missing from the reference list (61 reviewed Qt names are a fixed baseline).
Evidence: offline suite (4534 tests), ruff, mypy and the QGIS 4.2.2 live job passed on #352 and #353; `tests/test_api_reference_fixes_live.py`
runs the bow-tie polygon, the point-displacement representation and the proxy check against real QGIS objects. `zoom_history` is covered offline with a
spec'd mock only, because CI has no canvas. Limits: the check compares names, not argument lists or return types; there may be more wrong-argument
calls that no test has exercised. Not hand-tested.
Hand testing: `docs/HAND_TEST_SHEET_rc44_2026-10-16.md` (run on rc45; its first section retests these four fixes), the two results CSVs, and
`tools/build_hand_test_bundle.py`, which builds `dist/cartogen_ai_hand_test_1.17.0-rc45.zip` (local file, not committed).

**Reading guide.** Three levels of evidence appear below. Nothing in this document is hand-tested.

- **Offline-tested:** the pure logic (screens, source strings, option checks, routing) has unit tests that pass in the plain suite (no QGIS).
- **CI-live-tested:** a test in `tests/*_live.py` ran the real tool against real QGIS 4.2.2 objects in the pinned docker image of the "QGIS live
  tests" CI job and passed. This proves the tool works on the layers the test builds, not on a user's data or a desktop session.
- **Hand-tested:** a person ran it in a desktop QGIS with the dock widget and a model. **Nothing from this roadmap has reached this level.**

Limits that apply to every row: CI has no canvas, no GPS device, no sample point-cloud or tile data, no model/LLM in the loop for the live tests
(they call the tools directly), and the network from CI is restricted. Whether the model chooses and phrases these tools well is covered only by
router golden-row tests (the request text maps to the expected tool), not by a real conversation. All 38 tools added by packages A to H have a
golden routing row; the four gap-closing tools have one each.

## Package A, editing (PRs #333, #334)
Done: layer filter (definition query) with a screen on the text; move, rotate, scale features (preview first); merge selected; split by a line;
undo/redo of manual edits; change a field's type (preview first); start/stop editing, save/discard.
- Offline-tested: option and expression screens.
- CI-live-tested: transform preview then apply, bad input refused, merge, split, a split line that misses, field-type change and its refusal,
  undo/redo with save/discard, layer filter.
- Not tested: editing on database-backed layers (PostGIS, WFS-T); real attribute rules, joins or constraints; the dock's confirmation flow.

## Package C, data (#335)
Done: PostGIS table as a layer, virtual layers (screened SQL), QLR load/save, offline GeoPackage package, extra raster extensions (NetCDF, GRIB,
HDF, ECW, SID) and mesh files.
- CI-live-tested: virtual layer over a project layer, unsafe SQL refused, QLR round trip and overwrite refusal, bad QLR paths, offline package, a
  2DM mesh opens, a NetCDF raster opens, PostGIS against the CI PostGIS service (table added, credentials not leaked), unknown connection reported.
- Not tested: PostGIS with Auth Manager credentials or SSL; ECW, MrSID (drivers absent in the CI image; they work only where the user's QGIS has
  them); GRIB/HDF files; large or malformed real-world files.

## Package B, project (#336)
Done: zoom last/next, group rename, layer metadata, snapping settings, relations, per-layer temporal range, project time range, annotation items.
- CI-live-tested: group rename, metadata round trip, snapping options, relations, layer temporal settings, project time range, annotations.
- Not tested: zoom last/next and anything needing the map canvas (CI has no canvas); how snapping and temporal settings behave when a user then
  digitises or animates.

## Package D, raster and terrain (#337)
Done: 66 raster-family Processing algorithms on the allow-list, with a guard that refuses vector layers in raster-stack algorithms and raw GDAL
option strings.
- CI-live-tested: each algorithm ran once in its own process on generated test rasters; 63 of 66 ran first time, the rest were fixed or listed in
  the not-yet/rejected rows in `tests/_processing_live_rows.py`.
- Not tested: real DEM-scale rasters (size, runtime, memory); numerical correctness (the smoke checks that the algorithm completes and returns a
  layer, not that the numbers are right); other projections.
- Found and fixed along the way: vector layers into raster cell-stack algorithms crashed QGIS (SIGSEGV) or hung; now refused before running.

## Package E, remaining Processing algorithms (#339)
Done: 35 mixed-family algorithms, file-writing algorithms forced to temporary outputs, geometry-fix algorithms, select by expression, aggregate.
- CI-live-tested: 35 of 38 mixed algorithms ran; the others are listed with their errors.
- Not tested: same limits as package D. The raise-message algorithms are deliberately not added.

## Package J, service reach (#338)
Done: a non-blocking CI job that checks which showcase services answer. Measured twice, from the cloud sandbox and from the CI runner, with the
same result: Copernicus DEM tile reached, Google News reached (100 items), GDELT HTTP 429, DuckDuckGo blocked. See
`docs/SHOWCASE_SERVICES_REACH_2026-10-16.md`. Reach is not the same as the tools working end to end for a user, and two datacentre addresses on one
day say nothing about a user's network.

## Package F, symbology and labels (#341)
Done: rule-based labels, callouts, masks, diagrams, SVG and font markers, hillshade and contour renderers, symbol library save/load.
- CI-live-tested: rule-based labels and their refusals, callout and mask, SVG and font markers, polygon layer refused for markers, diagrams,
  hillshade/contour renderers, symbol library round trip.
- Not tested: how any of it looks. CI checks that settings are applied and read back, not rendered output.
- Found and fixed along the way: a SIGSEGV from handing a QGIS-owned object back to a setter (callout); now mutated in place.

## Package G, layouts (#342) and the gap-closing layout items (#347)
Done: overview map, guides and grid, atlas setup, export with world file and GeoPDF (#342); bar, line and pie chart items and an elevation-profile
item along a straight line (#347).
- CI-live-tested: overview inset shows the main extent, existing map reused and bad ids refused, guides and grid, atlas settings, export with world
  file and GeoPDF options; all three chart types created, the profile item created once elevation is on (and refused when it is off).
- Not tested: a full atlas run and the exported pages; opening the GeoPDF/world file in other software; how charts, profiles and layouts LOOK
  (only that the items exist and hold the settings).
- Not built: the 3D map layout item, because the class is missing in CI's QGIS.

## Capability probe (#343)
Done: a live test that prints what the CI QGIS offers, and `docs/QGIS_CAPABILITY_PROBE_2026-10-16.md`. Measured for the CI image only; a user's
QGIS (version, GDAL, GRASS, PDAL) can differ.

## Package H, new layer types (#344) and elevation settings (#347)
Done: `add_point_cloud_layer`, `add_vector_tile_layer`, `add_3d_tiles_layer` (#344); `set_layer_elevation` and `set_project_terrain` (#347).
- CI-live-tested: refusals for each layer tool; an https XYZ vector-tile source and a minimal local 3D Tiles tileset.json accepted; raster
  elevation settings, flat and DEM project terrain, and vector extrusion round-trip through real objects.
- Not tested: opening any real point cloud, vector-tile service or 3D tiles (no data or provider available). Plain .las/.laz cannot open in the CI
  image (no `pdal` provider); the tool says so and points to COPC or EPT, and that message was checked, not the opening. What the elevation
  settings do to a profile or a 3D view was not checked.
- Known limit: a vector layer has no elevation on/off switch in QGIS, so `set_layer_elevation` refuses `enabled` for vectors.
- Not built: GPS tools (a device is needed, nothing verifiable in CI); PDAL algorithms (24; no PDAL binary or provider in CI).

## Package I, GRASS (#346)
Done: 154 GRASS algorithms on the allow-list behind `run_allowlisted_processing_algorithm` (no new tool). They are the candidates that passed a
selection rule on the 307 the CI image reports (no file/folder parameters, no `*.in.*`/`*.external*`/`g.*`/`v.db.*`, no url/expression/SQL-like
parameters), minus 12 that failed. GRASS vector results are exported to a temporary file and loaded as layers; raw format options and `where` SQL
filters are refused.
- CI-live-tested: all 154 ran in their own process on tiny synthetic rasters or vectors.
- Rejected (in `GRASS_REJECTED`, with the error): i.evapo.mh, i.landsat.acca, r.drain, r.null, r.resamp.filter, r.rescale, r.rescale.eq, v.drape,
  v.extrude, v.net.connectivity, v.net.flow, v.to.3d. All failed with GRASS's generic "Unable to execute algorithm" on default inputs; likely they
  need purpose-built inputs; the cause was not investigated.
- Not tested: results on real data (the smoke proves completion, not correctness); long runs. GRASS algorithms run on the GUI thread, so a long one
  can freeze QGIS until it finishes. On a desktop QGIS without GRASS these ids do not exist.

## Mesh algorithms (#347)
Done: 6 mesh algorithms on the allow-list (export edges, faces, on grid, vertices; rasterize mesh dataset; surface to polygon), run on a 9-node test
mesh. `native:meshcontours` hung for 90 s and is rejected (`MESH_REJECTED`). Two file-destination exports and `3d:tessellate` were never candidates.
Not tested: real meshes (time series, large grids).

## Golden routing rows (#345)
Ten tools that only had alias entries now have golden routing rows; a wrong row fails the build (checked by mutation).

## Integration audit (#349), full detail in `docs/INTEGRATION_AUDIT_2026-10-16.md`
Done: the new tools were compared with the router from before the roadmap and with the older mechanisms they should plug into.
- Measured offline: 0 of 1565 old alias phrases lost their own tool; average tools offered 25.6 -> 26.5; schema text per request -2.9%; seven long
  compound requests mixing old and new capabilities offered every tool they needed.
- Found and fixed: one routing regression ("animate the layer over time"), nine new MODIFY tools that `undo_last_operation` could not reverse, a
  privacy hole (`create_virtual_layer` names layers only inside its SQL, so the egress gate and lineage tagging missed them), missing
  RESTRICTED/SENSITIVE advisories on the package, chart and atlas tools, none of the 42 new tools linked to any of the 792 library tasks, and plain-grey
  output for the raster, GRASS and mesh algorithms.
- CI-live-tested: the five undo round trips (layer filter, diagram, rule-based labels, layer elevation, layer temporal) and the advisories on
  chart, atlas and package. Offline: SQL layer-name scan, alias-owner guard (every alias phrase offers its own tool), styling name mappings.
- Not tested: which tool a real model chooses; how the styled outputs look; undo for the edit-buffer tools (they use `undo_manual_edit`) and for
  project-wide settings (snapping, terrain, time range), which are not covered on purpose.
- Not done: no pre-built `run_steps` chains for the new tools (their argument names would need live testing with real layouts first).

## Not tested at all, across the roadmap
1. Any end-to-end conversation: a real model choosing these tools from a prompt, asking for confirmation, and the user seeing results in the dock.
   The router tests prove which tools are OFFERED for a request, not which one is CHOSEN.
2. Any desktop QGIS session (canvas, layer tree refresh, rendering, print layout appearance).
3. User data: large, messy, non-English, differently projected, or database-backed layers.
4. Numerical correctness of Processing outputs (raster, mixed, GRASS, mesh); the smoke tests prove completion, not accuracy.
5. Windows and macOS QGIS (live tests ran on Linux docker only; the plain suite also runs on Windows).
6. The owner's hand-test rows (smoke 16 to 18), the JIAF validation, the credentialed integrations (HX4), and the open secret-scanning alert.

## Open decisions
- Uploading rc45 to plugins.qgis.org, and whether to promote a later build to stable, are the owner's decisions; nothing is done for them.
- Argument-list and return-type checks against the 4.2.3 reference are not built; they would find a class of bug the name check cannot.
- If any of the "not built" items matters (GPS, PDAL, 3D map item), it needs a different CI image or a hand test on a machine that has the module.
