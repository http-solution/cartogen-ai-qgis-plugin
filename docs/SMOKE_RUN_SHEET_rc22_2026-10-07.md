# rc22 live smoke test sheet (prepared 2026-10-07)

A blank sheet, not a result. rc22 carries the fixes from the rc20 architectural audit (see the `v1.16.0-rc22` block in `metadata.txt`). **The rc21 sheet (`docs/SMOKE_RUN_SHEET_rc21_2026-10-07.md`) stays the master for rows F1-F7, the rc20 sheet for D1-D14, the rc19 sheet for A1-A12, and the rc18 sheet for rows V, T, J, P and the fixtures.** Install and gate steps are the same as rc18 section 0. Nothing in rc22 has been hand-tested. If a prerequisite is missing write "not run: <reason>", never an inferred pass.

## H. New in rc22 (audit fixes)
| Id | Prompt / action | Expected | Result |
|---|---|---|---|
| H1 | Make your own layer named like a plugin result (e.g. rename a layer to `smoke_service_area`), then ask the agent to run the same service-area analysis again | Your layer is kept (renamed, not deleted) and the reply says it was set aside; the new result has the expected name (A02) | |
| H2 | Ask the agent to run an analysis, press Stop, then ask something else | The stopped turn delivers nothing late; the next answer is about the new request (A04) | |
| H3 | Equalise a small single-band raster whose lowest values are valid data (e.g. `histogram_equalization` on a DEM with a few low cells) | The lowest valid cells are not transparent / NoData; only genuinely empty cells are (A09) | |
| H4 | Slope on a DEM in a US-foot projected CRS (e.g. EPSG:2263) vs the same DEM in metres | Slope values agree within rounding (A11) | |
| H5 | Export a layer in a projected CRS to GeoJSON, open it in a web viewer or QGIS | It lands in the right place; the file has WGS84 coordinates and no `crs` member (A12) | |
| H6 | Ask the agent to zoom to a layer after setting a layer CRS the project cannot transform from | An error, not a silent zoom to the wrong place (A13) | |
| H7 | Ask the agent to run `execute_pyqgis_script` that deletes all features of a GeoPackage layer | The GeoPackage on disk is unchanged (A06); a database-backed layer is NOT protected, do not test destructively | |
| H8 | Zonal statistics of a raster over 200+ polygons; watch QGIS while it runs; press Stop once | QGIS stays responsive, Stop works, finished run adds `zs_mean`, `zs_median`, `zs_stdev` (A14) | |
| H9 | Extract features from a small satellite image (needs the FastSAM model) | Only the object is outlined, not the background; the window stays responsive during the model step (A01, A14) | |
| H10 | Run `unsupervised_classification` on a raster with 8 bands over about 10M cells | A clear "clip it or use fewer bands" error, not a crash (A15) | |

## G. Carry-over
Run F1-F7 (rc21 sheet), D1-D14 (rc20), A1-A12 (rc19) and V, T, J, P (rc18) on rc22; run the gates (fresh-profile install, upgrade from the previous zip, restart twice, uninstall and reinstall).

Known open, do not expect a pass: other expensive tools still block the GUI (#221), database and web-service layers are still writable by a script (#220), model-added plans and arrange steps (N3/N9), geography suggested from project memory in prose (N1), PostGIS connections that authenticate through a QGIS auth configuration, the legend-by-role and attribution items listed in #165.
