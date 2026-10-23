# PLAN-005: the 60 file-writing Processing algorithms

Status: planned

## Goal
Let a user ask in plain words for the results of the 60 approved-candidate QGIS algorithms that write files (statistics reports, GDAL vector tools, exports, plots) and get the result in the project or in the reply, without the model ever choosing a file path. This closes the coverage rows "Raster histogram and band statistics", "Raster to points / polygons" (gdal:polygonize) and "Import / export DXF", and part of "Spatial index / line / polygon tools". Source: `docs/qgis_coverage/processing_matrix.csv`, disposition NEEDS-OUTPUT-HANDLING (60 ids: 32 native, 20 gdal, 8 qgis).

## Scope
Every one of the 60 has exactly one wave in `docs/plans/PLAN-005-dispositions.csv` (a test checks that none is missing, duplicated or invented):

| Wave | Count | What | How it is built |
|---|---|---|---|
| **E1-REPORT** | 6 | basic statistics, unique values, nearest-neighbour analysis, raster layer statistics, raster unique values report, raster surface volume | The numeric results are returned from the algorithm's own result dictionary (MIN, MAX, MEAN, COUNT ...); the HTML report goes to a temporary file in the export folder and its path is reported. Table outputs become project layers as today. |
| **E1-GDAL-VECTOR** | 10 | gdal buffer, clip by extent, clip by mask, dissolve, offset curve, one-side buffer, points along lines, contour, contour polygons, polygonize | Same route GRASS vector results already use: `TEMPORARY_OUTPUT` file, opened as a layer, styled like other algorithm outputs. `OPTIONS` and `EXTRA` stay refused. |
| **E2-INFO** | 4 | gdalinfo, ogrinfo, ogrinfo JSON, dataset identify | Text report of a file the user names as a layer; temporary text file, a bounded read of our own file. |
| **E2-PLOT** | 9 | bar, box, mean and deviation, polar, histogram and scatter plots; elevation profile image | Temporary HTML or PNG plus its path. First a probe that the plot modules exist in the QGIS image; ids that do not run are dropped with the reason, as for the mesh family. |
| **E2-EXPORT** | 17 | DXF, spreadsheet, package, save features, layout PDF/image/atlas, layer metadata, GPS conversions, convert format, split layer, extract binary, points to path, hypsometric curves, relief, TIN mesh | Writes where the user says: needs the export folder, the existing overwrite check and a confirm card. Where a dedicated tool exists (export_layer, export_layout, export_layout_atlas, package_layers_offline, generate_contours) the request is routed to it and the algorithm is NOT added; only DXF and spreadsheet are new routes. |
| **E3-NOT-PLANNED** | 14 | XYZ and MBTiles tiles, vector tile writers, retile, COG, tile index, virtual vector, gdal2xyz, B3DM to GLTF, style databases, modeler helpers | Large or niche outputs with no chat use. Listed so they are decided, not forgotten. |

Out: any algorithm whose output path the model chooses; changing the 427 already approved; the 63 plain candidates and the 28 waiting on layer types (own plans).

## Safety rules (owner decision requested: these widen the trust boundary)
1. R1. Outputs are always temporary files in the export folder (or in-memory sinks). A destination parameter the caller supplies is ignored, as today.
2. R2. Nothing is overwritten; file names are made unique.
3. R3. The model only sees numbers and short text from the algorithm's result dictionary and bounded reads of the plugin's own temporary files, never an arbitrary file.
4. R4. Wave E2 exports to a user path need a confirm card and the existing overwrite confirmation; duplicates of dedicated tools are not added.
5. R5. Every id needs a live test in the QGIS 4.2.2 image; an id that fails its first run is dropped with the reason written next to it.
6. R6. `OPTIONS`, `EXTRA`, `FORMULA` and any raw argument parameter stay refused for these algorithms.

## Acceptance
1. Wave E1: the 16 ids are approved, each runs in `tests/test_processing_file_output_family_live.py` and its result is read back from real QGIS objects (layer feature count; statistics values), the router offers the Processing tools for a plain request for each (golden rows), the topic index finds each from a description, and the coverage rows move up in `docs/qgis_coverage/` with `ALGS:` evidence.
2. Wave E1 hand test: rows for statistics ("what are the minimum, maximum and mean of the dem") and one GDAL vector tool in the next test bundle; until then every claim says CI only.
3. Wave E2 and E3 are decided in the disposition table; E2 starts only after the owner confirms rules R1 to R6 and the probe results are in.

## Guard tests
`tests/test_plan005_dispositions.py` (every NEEDS-OUTPUT-HANDLING id has one wave; counts match this plan); wave E1 adds the live family test, the golden routing rows and a ledger entry.

## Rollback
Each wave is one pull request that adds ids to the allow-list; revert it, or remove an id, to take algorithms back. No existing behaviour changes.

## Status log
- 2026-10-23: plan and dispositions written (this pull request). No algorithm added yet; waiting for the owner to confirm rules R1 to R6 before wave E1 is built.
