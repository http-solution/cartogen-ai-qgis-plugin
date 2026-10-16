# QGIS capability probe, 2026-10-16

Source: the `CAPABILITY ...` lines printed by `tests/test_qgis_capability_probe_live.py` in the
"QGIS live tests (4.2.2)" CI job (pinned official QGIS 4.2.2 docker image, GDAL 3.10.3). CI-measured,
not hand-tested on a desktop install; a user's QGIS may differ (especially GDAL drivers and GRASS).

| Area | Result in CI | Consequence |
|---|---|---|
| Point cloud (`QgsPointCloudLayer`, providers `copc`, `ept`, `vpc`) | available | Package H can add point-cloud layers |
| Vector tiles (`QgsVectorTileLayer`; `xyzvectortiles`, `mbtilesvectortiles`, `vtpkvectortiles`, `arcgisvectortileservice`) | available | Package H |
| Tiled scene / 3D tiles (`QgsTiledSceneLayer`; `cesiumtiles`, `quantizedmesh`, `esrii3s`) | available | Package H |
| Mesh (`QgsMeshLayer`, `mdal`) | available | already covered in package C |
| Annotation layer | available | Package H |
| Elevation profile (`QgsLayoutItemElevationProfile`, `QgsProfileRequest`) | available | Package H layout item |
| Chart layout item (`QgsLayoutItemChart`) | available | Package H layout item |
| 3D map layout item (`QgsLayoutItem3DMap`) | **not available** | Do NOT build a 3D map layout tool |
| GPS (`QgsGpsConnection`) | classes available; no device in CI | Only status/settings, nothing device-dependent can be verified |
| GDAL drivers netCDF, GRIB, HDF5, HDF4, PDF, COG, Zarr, OpenFileGDB | present | Package C extensions already usable |
| GDAL drivers ECW, JP2ECW, MrSID, FileGDB | **absent** | Those formats stay "only when the user's QGIS has the driver" |
| GRASS (`grass` provider, 307 algorithms, `/usr/bin/grass`) | **active in CI** | Package I can be live-tested |
| SAGA, PDAL binary, LAStools | not installed (PDAL provider lists 24 algs, binary missing) | No SAGA/PDAL/LAStools tools |
| Processing providers | 3d:1, gdal:59, grass:307, native:350, pdal:24, qgis:31 | |
