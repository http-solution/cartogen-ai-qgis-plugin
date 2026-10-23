# PLAN-006: PLAN-005 wave E2 (information reports, plots, exports)

Status: planned

## Goal
Finish the file-writing part of the QGIS algorithm coverage that wave E1 left: a user can ask in plain words for a file information report ("what projection and extent does this file have"), a chart of their data ("a histogram of the dem", "scatter plot of population against distance") and a DXF or spreadsheet export, and get the result, with the model never choosing a file path. Parent plan: PLAN-005 (rules R1 to R6 apply unchanged). Closes the coverage row "Import / export DXF" and adds the first plots. No GitHub issue yet; the coverage list is the source (`docs/qgis_coverage/`).

## Scope
The 30 E2 ids in `docs/plans/PLAN-005-dispositions.csv`, in three packages. Each package is its own pull request and is built only after the previous one is green in the QGIS 4.2.2 live test. Nothing here is built by this plan; it only fixes the order, the method and the pass criteria. **Order (owner agreed 2026-10-23, by what users ask for): E2c first, then the plot probe and E2b only if the probe passes, E2a last and only if hand testing shows a gap. No further algorithm is added until the E1 and E2c rows are hand-tested.**

| Package | Ids | Method | Decision |
|---|---|---|---|
| **E2c EXPORT** | 17 ids, see below | Only where no dedicated tool exists, and only through the existing export anchoring, overwrite preview and `confirmed` argument (`export_tools.overwrite_preview`). | Build first. Route 5 (alias plus golden row, no new surface), add DXF and spreadsheet. The other 10 stay **not planned** (E3), except `pointstopath` (GPS and field points to tracks) and `relief` (cheap), which get a short decision note each before any code. |
| **E2b PLOT** | qgis:barplot, boxplot, meanandstandarddeviationplot, polarplot, rasterlayerhistogram, scatter3dplot, vectorlayerhistogram, vectorlayerscatterplot, native:generateelevationprofileimage (9) | Temporary HTML (PNG for the profile image); the reply gives the path and opens nothing automatically. | **Probe first**: a one-test PR that only checks, inside the QGIS 4.2.2 image, whether the plot modules (plotly) import and one plot writes a file. If the probe fails, E2b is abandoned with the reason recorded and no ids are added. Per id, a plot that fails its first live run is dropped (as `FILE_OUTPUT_REJECTED` does for E1). |
| **E2a INFO** | gdal:gdalinfo, ogrinfo, ogrinfojson, dataset_identify (4) | Run to a temporary text file; the model gets a bounded read (first 4,000 characters) of our own file only. | Build last, only if hand testing shows a gap: users rarely ask for it and layer and project tools probably cover "what CRS and extent is this" (not yet checked). The input must be a project layer (its source path is read by us, never typed by the model). |

E2c in detail (checked against the code: `export_layer` writes shapefile, GeoJSON, GPKG, KML and GeoTIFF only; no DXF or spreadsheet writer exists):
- **Add (new capability, confirm card):** native:dxfexport (DXF), native:exporttospreadsheet (xlsx/ods).
- **Route, do not add (dedicated tool exists):** native:package (package_layers_offline), native:savefeatures (export_layer, save_layer_as), native:printlayouttopdf and printlayouttoimage (export_layout), native:atlaslayouttopdf (export_layout_atlas). The work is a router alias and a golden row each, so a plain request reaches the existing tool.
- **Default not planned (owner agreed), exceptions pointstopath and relief:** exportlayermetadata, convertgpsdata, convertgpxfeaturetype, gdal:convertformat (export_layer covers the common formats), splitvectorlayer (writes many files), extractbinary, pointstopath, hypsometriccurves, relief, tinmeshcreation. Each moves to a wave in the disposition table with a one-line reason; `pointstopath` and `relief` are the likeliest to be worth building (they produce a layer or raster a user asks for), the rest are expected to go to E3-NOT-PLANNED.

Out: any algorithm whose output path the model chooses; extra GDAL twins of tools that exist; E3.

## Acceptance
1. E2a: each of the 4 ids runs in a new live test and the report text is read back from the real output file; a plain request ("show me the file information for the dem layer") is offered the Processing tools (golden row); topic index finds each; coverage rows updated with `ALGS:` evidence. CI-live, then one hand-test row.
2. E2b probe: a live test records import and one written file; the result (pass or fail) is written in this plan's status log before anything else is built.
3. E2b build (only if the probe passes): each plot id has a live test that the temporary file exists and is non-empty; results flag the file as temporary and give the path; a layer name marked sensitive is stopped by the cloud-data gate (test, as for E1).
4. E2c: DXF and spreadsheet exports ask for confirmation when the target exists (offline test on the preview), write only inside the anchored export folder (offline test that a model-supplied absolute path outside it is refused), and read back (DXF file exists and contains the layer name; spreadsheet re-opens as a layer). The 5 routed ids have golden rows proving the dedicated tool is chosen and the algorithm id is NOT added to the allow-list (disposition test).
5. Every package updates `docs/plans/PLAN-005-dispositions.csv` and the plan counts in the same pull request; hand-verified status stays "CI only" until a bundle row passes.

## Guard tests
To be written with each package and added to the ledger (`file-output-wave-e2a`, `-e2b`, `-e2c`); existing guards that must keep passing: `tests/test_plan005_dispositions.py`, `tests/test_processing_file_outputs.py`, `tests/test_processing_file_output_family_live.py`, `tests/test_algorithm_topics.py`, the qgis-coverage ratchet.

## Rollback
One pull request per package: revert it, or remove an id from the allow-list. No existing behaviour changes. The probe PR adds only a test.

## Status log
- 2026-10-23: plan drafted (this pull request). Nothing built.
- 2026-10-23: owner agreed the reorder (E2c, probe, E2b, E2a last) and "not planned" as the default for the 10 undecided exports; plan updated. Next: route the 5 and add DXF and spreadsheet, then cut rc48 with wave E1 so one hand-test pass covers both.
