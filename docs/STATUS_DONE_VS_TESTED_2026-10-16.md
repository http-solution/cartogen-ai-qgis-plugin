# Roadmap completion: what was done, and how far each piece was tested (2026-10-16)

**Reading guide.** Three levels of evidence appear below. Nothing in this document is hand-tested.

- **Offline-tested:** the pure logic (screens, source strings, option checks) has unit tests that pass in the plain suite (no QGIS).
- **CI-live-tested:** a test in `tests/*_live.py` ran the real tool against real QGIS 4.2.2 objects in the pinned docker image of the "QGIS live tests" CI job and passed. This proves the tool works on the layers the test builds, not on a user's data or a desktop session.
- **Hand-tested:** a person ran it in a desktop QGIS with the dock widget and a model. **Nothing from this roadmap has reached this level.**

Limits that apply to every row: CI has no canvas, no GPS device, no sample point-cloud or tile data, no model/LLM in the loop for the live tests (they call the tools directly), and the network from CI is restricted. Whether the model chooses and phrases these tools well is covered only by router golden-row tests (the request text maps to the expected tool), not by a real conversation.

## Package A, editing (PRs #333, #334)
Done: layer filter (definition query) with a screen on the text; move, rotate, scale features (preview first); merge selected; split by a line; undo/redo of manual edits; change a field's type (preview first); start/stop editing, save/discard.
- Offline-tested: option and expression screens (`test_edit_options`).
- CI-live-tested: transform preview then apply, bad input refused, merge, split, a split line that misses, field-type change and its refusal, undo/redo with save/discard, layer filter (`test_edit_ops_tools_live`).
- Not tested: editing on database-backed layers (PostGIS, WFS-T); behaviour with a user's real attribute rules, joins or constraints; the dock's confirmation flow with a real model.

## Package C, data (#335)
Done: PostGIS table as a layer, virtual layers (screened SQL), QLR load/save, offline GeoPackage package, extra raster extensions (NetCDF, GRIB, HDF, ECW, SID) and mesh files.
- CI-live-tested: virtual layer over a project layer, unsafe SQL refused, QLR round trip and overwrite refusal, bad QLR paths, offline package, a 2DM mesh opens, a NetCDF raster opens, PostGIS with the CI PostGIS service (table added, credentials not leaked), unknown connection reported.
- Not tested: PostGIS with Auth Manager credentials or SSL; ECW, MrSID (drivers absent in CI image; they work only where the user's QGIS has them); GRIB/HDF files (only NetCDF and 2DM were exercised); large or malformed real-world files.

## Package B, project (#336)
Done: zoom last/next, group rename, layer metadata, snapping settings, relations, per-layer temporal range, project time range, annotation items.
- CI-live-tested: group rename, metadata round trip, snapping options, relations, layer temporal settings, project time range, annotations (`test_project_ops_tools_live`).
- Not tested: zoom last/next and anything needing the map canvas (CI has no canvas; labelled like `set_map_view`); how snapping and temporal settings behave when a user then digitises or animates.

## Package D, raster and terrain (#337)
Done: 66 raster-family Processing algorithms added to the allow-list, with a guard that refuses vector layers in raster-stack algorithms and raw GDAL option strings.
- Offline-tested: list membership, exclusions, parameter refusals, layer-list resolution, the raster-stack guard (`test_processing_raster_family`).
- CI-live-tested: each algorithm ran once in its own process on generated test rasters; 63 of 66 ran first time, the rest were fixed or listed in the not-yet/rejected rows in `tests/_processing_live_rows.py`.
- Not tested: outputs on real DEM-scale rasters (size, runtime, memory); numerical correctness of results (the smoke checks that the algorithm completes and returns a layer, not that the numbers are right); projections other than the test one.
- Found and fixed along the way: feeding vector layers into raster cell-stack algorithms crashed QGIS (SIGSEGV) or hung; now refused before running.

## Package E, remaining Processing algorithms (#339)
Done: 35 mixed-family algorithms, file-writing algorithms forced to temporary outputs, geometry-fix algorithms, select by expression, aggregate.
- CI-live-tested: 35 of 38 mixed algorithms ran; the others are listed with their errors.
- Not tested: same limits as package D (real data, numerical correctness). The raise-message algorithms are deliberately not added.

## Package J, service reach (#338)
Done: a non-blocking CI job that checks which showcase services answer.
- Measured from CI: Copernicus DEM tile reachable, Google News reachable, GDELT answered 429 (rate limited), DuckDuckGo blocked.
- Not done: `docs/SHOWCASE_SERVICES_REACH_2026-10-16.md` still describes the earlier sandbox run; the CI numbers are not folded in. Reach is not the same as the tools working end to end for a user.

## Package F, symbology and labels (#341)
Done: rule-based labels, callouts, masks, diagrams, SVG and font markers, hillshade and contour renderers, symbol library save/load.
- CI-live-tested: rule-based labels and their refusals, callout and mask, SVG and font markers, polygon layer refused for markers, diagrams, hillshade/contour renderers, symbol library round trip.
- Not tested: how any of it looks. CI checks that settings are applied and read back, not rendered output. Hand-viewing of maps (label placement, callout lines, diagram sizes, hillshade quality) has not happened.
- Found and fixed along the way: a SIGSEGV from handing a QGIS-owned object back to a setter (callout); now mutated in place.

## Package G, layouts (#342)
Done: overview map, guides and grid, atlas setup, export with world file and GeoPDF.
- CI-live-tested: overview inset shows the main extent, existing map reused and bad ids refused, guides and grid, atlas settings, export with world file and GeoPDF options.
- Not tested: a full atlas run over many features and the exported pages; opening the exported GeoPDF/world file in other software; how the layouts look.
- Not built: chart and elevation-profile layout items (the classes exist in CI; not done). 3D map layout item cannot be built here (class missing in CI's QGIS).

## Capability probe (#343)
Done: a live test that prints what the CI QGIS offers, and `docs/QGIS_CAPABILITY_PROBE_2026-10-16.md`. This is measured for the CI image only; a user's QGIS (version, GDAL, GRASS, PDAL) can differ.

## Package H, new layer types (#344)
Done: `add_point_cloud_layer`, `add_vector_tile_layer`, `add_3d_tiles_layer`.
- Offline-tested: source-string logic and refusals (`test_new_layer_options`).
- CI-live-tested: refusals for each tool; an https XYZ vector-tile source and a minimal local 3D Tiles tileset.json were accepted by QGIS.
- Not tested: opening any real point cloud, real vector-tile service, or real 3D tiles (no data or provider available). Plain .las/.laz cannot open in the CI image (no `pdal` provider); the tool says so and points to COPC or EPT, and that message was checked, not the opening.
- Not built: elevation controller and GPS tools; the 34 algorithms that wait on these layer types; PDAL algorithms (binary missing in CI).

## Releases
rc42 and rc43 were published from green CI builds. The release workflow's gate is the offline suite; a published zip has not been installed and exercised by hand by me. Packages F, G and H are in no release yet.

## Not started
- Package I, GRASS: nothing written. CI reports the GRASS provider active with 307 algorithms, so it can be built and smoke-tested there.

## Not tested at all, across the roadmap
1. Any end-to-end conversation: a real model choosing these tools from a prompt, asking for confirmation, and the user seeing results in the dock.
2. Any desktop QGIS session (canvas, layer tree refresh, rendering, print layout appearance).
3. User data: large, messy, non-English, differently projected, or database-backed layers.
4. Numerical correctness of Processing outputs; the smoke tests prove completion, not accuracy.
5. Windows and macOS QGIS (live tests ran on Linux docker only; the plain suite also runs on Windows).
6. The owner's hand-test rows (smoke 16 to 18), the JIAF validation, the credentialed integrations (HX4), and the open secret-scanning alert.
