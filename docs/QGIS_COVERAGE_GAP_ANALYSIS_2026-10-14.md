# QGIS coverage gap analysis (2026-10-14)

Owner request: read the QGIS and plugin-developer documentation, list every function, vocabulary item, action, Processing tool, QGIS feature, layer type, shape and JSON format, and say what the plugin is missing. This is that list, with the method, the numbers, and a build order that cannot break what works.

## 0. What was read, and what was not

| Source | How it was read | Result |
|---|---|---|
| QGIS documentation, branch `release_4.2`, commit `12332b8` (`qgis/QGIS-Documentation`, shallow sparse clone) | `docs/user_manual` (vector and raster properties, attribute table, editing, layouts, map views, data sources, processing_algs, expressions, projections, GPS, mesh, point clouds, vector tiles, 3D) and `docs/pyqgis_developer_cookbook` (22 chapters including `plugins/`) | 454 algorithm pages parsed (native 336, gdal 59, qgis 34, pdal 24, 3d 1), 448 expression functions in 24 groups, every section heading of the chapters above |
| The real Processing registry of QGIS 4.2.2 (the CI image) | a new live test dumps every algorithm with its parameter types, outputs and flags (`tests/test_processing_registry_dump_live.py`) | **772** algorithms: native 350, GRASS 307 (an optional provider), gdal 59, qgis 31, pdal 24, 3d 1. **465 core** |
| The plugin | the tool registry (212 tools), tool descriptions and signatures, `add_layer_from_path`, `export_layer`, the Processing allow-list, the script worker, and `grep` for every layer class and geometry method | facts quoted below come from the code, not from memory |
| What was **not** done | the PyQGIS API reference (qgis.org) is not reachable from the sandbox, so classes and methods beyond the cookbook are not enumerated; nothing was run in a QGIS desktop session; the 163 action rows are the documentation's own sections, grouped by me, not an exhaustive method list | stated so the gaps in this analysis are visible |

Machine-readable results, rebuilt by `python tools/build_qgis_coverage.py --registry LOG --write-baseline`:
`docs/qgis_coverage/actions_matrix.csv` (163 actions, status computed by asking the real tool router),
`docs/qgis_coverage/processing_matrix.csv` (772 algorithms, disposition and proposed wave),
`docs/qgis_coverage/baseline.json` (the floor the new ratchet test enforces).

## 1. The result in one table

| Area | Rows | Covered | Partial | Missing | Blocked on purpose |
|---|---|---|---|---|---|
| data sources | 24 | 3 | 4 | 17 | 0 |
| project and canvas | 24 | 9 | 2 | 13 | 0 |
| attributes | 23 | 8 | 4 | 11 | 0 |
| editing | 12 | 2 | 4 | 6 | 0 |
| symbology | 17 | 10 | 2 | 5 | 0 |
| layouts | 11 | 5 | 1 | 5 | 0 |
| raster | 20 | 11 | 1 | 8 | 0 |
| vector analysis | 16 | 12 | 1 | 3 | 0 |
| processing framework | 8 | 2 | 3 | 2 | 1 |
| expressions | 3 | 2 | 1 | 0 | 0 |
| specialised | 5 | 1 | 1 | 2 | 1 |
| **All** | **163** | **65** | **24** | **72** | **2** |

Processing: the plugin's code names **44 of the 465 core algorithms (9.5 percent)**; 41 are reachable through the generic tool.

| Core Processing disposition | Algorithms | Meaning |
|---|---|---|
| Already allow-listed | 41 | offered through `run_allowlisted_processing_algorithm` |
| Plain candidates | 283 | only layers, numbers, fields, enums, CRS, extents and sinks (decided from the real parameter definitions, not by name) |
| Candidates that take a QGIS expression | 16 | field calculator, extract by expression, raster calculator ...: need expression screening first |
| Write a file or folder | 60 | need an export-style tool with a confirmed output path |
| Need a layer type the plugin cannot load | 34 | point cloud, mesh, 3D tiles |
| Read a file, folder, connection or layout given as text | 17 | per-algorithm review |
| Stay off | 14 | SQL execution, Python, raw formulas, HTTP requests, file uploads and downloads |
| GRASS (optional) | 307 | present in the CI image, not on every install |

## 2. What this analysis found that was not known before

1. **The foundation tools had no routing aliases at all.** `add_layer_from_path`, `remove_layer`, `zoom_to_layer`, `export_layer`, `reproject_layer`, `clip_layer`, `select_by_attribute`, `highlight_features`, `field_calculator` and 30 others were found only by accidental word overlap with their names. That is exactly what broke in rc23. Plain-phrase aliases for 38 of them are added on this branch, and the new coverage ratchet fails the build if any covered action stops being routed.
2. **"Select the districts where population is over 1000" was offered neither selection tool.** Fixed with aliases (found by the matrix, not by a user).
3. **My earlier statement that the raster calculator must stay off was incomplete.** The 4.2.2 registry has `native:rastercalc` and `native:virtualrastercalc`, which use QGIS's own raster-calculator grammar (`QgsRasterCalculator`), not Python. `gdal:rastercalculator` (Python `eval`, audit #137) stays off. The native one is a candidate; no new tool is needed.
4. **Only two of the nine QGIS layer types are supported** (vector and raster). There is no mesh, point cloud, vector tile, annotation, group or 3D-tiles layer anywhere in the code.
5. **`add_layer_from_path` opens the first layer only** (no `layername=`), and treats only nine file extensions as rasters; NetCDF, VRT, HGT, BIL, ECW, SID, GRIB and Arc grids go to the vector reader and fail.
6. **No Z, M or curved-geometry handling exists** (`hasZ`, `hasM`, `CircularString`, `CompoundCurve`, `CurvePolygon` appear nowhere in `src`).
7. **The expression engine is unscreened.** A model-written expression passed to `field_calculator`, `highlight_features` or `apply_labels` can call any of the 448 functions, including `env()` and the file-name functions. No allow or deny list exists. Listed as a security review item, not as an exploit.
8. **The script worker cannot run Processing at all** (it hands the script 9 names and never initialises the Processing framework), so every algorithm outside the allow-list is unreachable from chat today.
9. **34 of the 42 allow-listed algorithms are never run by id in any live test.**
10. **`saga:` supervised classification cannot work on 4.2.2** (no SAGA provider; the code already reports it unavailable).

## 3. Layer types

| QGIS layer type (QgsMapLayerType) | Plugin |
|---|---|
| Vector | supported (OGR files, memory layers, delimited text, Excel) |
| Raster | supported for 9 extensions; other GDAL rasters fail |
| Mesh | **missing** (also 10 mesh algorithms) |
| Point cloud | **missing** (also 24 PDAL algorithms) |
| Vector tile | **missing** (MVT, MBTiles, PMTiles; 3 algorithms) |
| Annotation | **missing** |
| Group layer | **missing** (also layer-tree groups) |
| Tiled scene / 3D tiles | **missing** (2 algorithms) |
| Plugin layer | not applicable |
| Web services (WMS, WMTS, WFS, WCS, XYZ, ArcGIS REST) | **missing**; the HTML dashboard has a basemap, the QGIS project cannot |
| Databases (PostGIS, SpatiaLite, Oracle, MSSQL, SAP HANA) | PostGIS read-only SQL returns rows; no database layer |
| Virtual / SQL query layers | **missing** |

## 4. Geometry types and shapes

| Item | Plugin |
|---|---|
| Point, LineString, Polygon and their Multi* forms | handled through `geometryType()` (point, line, polygon, none) in 11 files |
| GeometryCollection | mentioned in 4 files (export and corridor code) |
| Z, M, ZM, 25D coordinates | **not handled**; no tool reads or writes them (QGIS has 'Drop M/Z', 'Force RHR' and 'Z/M' algorithms) |
| Curved types (CircularString, CompoundCurve, CurvePolygon, MultiCurve, MultiSurface) | **not handled**; QGIS has 'Convert to curved/straight' algorithms |
| TIN, PolyhedralSurface, Triangle | **not handled** |
| Create shapes: circle, ellipse, rectangle, regular polygon, circular string by radius | **missing** (digitizing shapes; also layout shapes and arrows) |
| Create a polygon or line from coordinates or WKT | **missing** (only `add_point_layer` and `add_incident_point` create geometry) |

## 5. Data formats and JSON

| Format | Read | Write |
|---|---|---|
| Shapefile, GeoPackage, GeoJSON, KML | yes (first layer only for multi-layer files) | yes (`export_layer`) |
| CSV / Excel with X,Y or WKT | yes | CSV only (`export_to_csv`) |
| GPX | first layer only | no |
| GeoJSON from a URL, with a clear error for HTML, zip, XML | yes | - |
| GeoJSON-seq, TopoJSON, ESRI JSON, JSON-FG | through OGR if the extension reaches it; not tested, and the download checker calls any non-GeoJSON JSON an error | no |
| GeoTIFF | yes | yes (rasters export only as GeoTIFF) |
| COG, NetCDF, VRT, HGT, BIL, ECW, SID, GRIB, HDF, PNG/JPG world-file rasters | **partly** (PNG, JPG, JP2, IMG, ASC listed; the rest fail) | no |
| FlatGeobuf, Parquet, SpatiaLite, SQLite, MBTiles, DXF/DWG, GML, MapInfo, FileGDB | **missing** | **missing** |
| QML style | yes (save and load) | yes |
| SLD | no | yes |
| QLR layer definition, QPT layout template, `.model3` Processing model | **missing** | **missing** |
| STAC JSON | yes (`search_stac_satellite_imagery`) | - |
| Overpass JSON | yes (`fetch_osm_features`) | - |
| QGIS JSON field type, `json_to_map`, `map_to_json` and the other JSON expression functions | available through the expression engine, no tool edits a JSON field | - |
| Mapbox GL / vector-tile style JSON | **missing** | **missing** |
| OGC API Features (JSON) | **missing** | - |
| The plugin's own JSON (workflow presets, evidence folders, API traces) | yes | yes |

## 6. Expression vocabulary

448 functions in 24 groups (documentation `expression_help`): Aggregates 23, Arrays 36, Color 24, Conditionals 6, Conversions 24, CRS 2, Date and Time 26, Fields and Values 1, Files and Paths 9, Form 2, Fuzzy Matching 4, General 7, Geometry 151, Layout 2, Magnetic Models 4, Map Layers 3, Maps 16, Math 28, Meshes (0 listed), Operators 26, Processing 1, Rasters 3, Record and Attributes 15, Sensors 1, String 34. The engine is used as is, so every function is available wherever an expression is accepted (`field_calculator`, `highlight_features`, `run_query`, `apply_labels`). Gaps: no tool tells the model which functions exist; nothing screens `env()`, the file functions or `eval_template`; `select_by_attribute` is equality only.

## 7. Actions that are partly covered (24)

| P | Area | Action | What the code shows |
|---|---|---|---|
| 1 | data sources | Open a vector file (Shapefile, GeoJSON, GeoPackage, KML, GPX) | PARTIAL: opens the FIRST layer only; there is no layername= support, so one table of a multi-layer GeoPackage, FileGDB, KML or GPX cannot be chosen |
| 1 | data sources | Open a raster file | PARTIAL: only .tif .tiff .geotiff .img .asc .jp2 .png .jpg .jpeg are treated as rasters; NetCDF, VRT, HGT, BIL, ECW, SID, GRIB, HDF and Arc/Info grids are sent to the vector reader and fail |
| 1 | data sources | Save a layer with another CRS, extent, field subset or format (Save As) | PARTIAL: formats shp/geojson/gpkg/kml (any OGR driver name is passed through); raster only as GeoTIFF; no CRS, extent or field-subset options |
| 1 | attributes | Select features by a value (equality only) | PARTIAL: select_by_attribute(layer, field, value) is equality only |
| 1 | attributes | Group by a field and aggregate (summary per category) | PARTIAL: aggregate_data works on rows you already have; layer-level goes through the Processing tool |
| 1 | attributes | Join a table to a layer by a key field | PARTIAL: makes a new joined layer; no live (virtual) join and no relations |
| 1 | editing | Add a feature from coordinates or WKT | PARTIAL: points only |
| 1 | editing | Undo / redo edits | PARTIAL: undoes the assistant's own operations, not manual edits |
| 1 | symbology | Single symbol: colour, opacity | PARTIAL: fill/line colour and opacity only; no outline colour, stroke width, marker shape or size, line pattern, fill pattern |
| 1 | symbology | Labels from a field or expression | PARTIAL: field/expression, font size, priority; no rule-based labels, placement, halo/buffer, callouts, masks, data-defined overrides |
| 1 | layouts | Export a layout to PDF / PNG / JPG | PARTIAL: PDF and image; no SVG, no world file, no GeoPDF |
| 1 | processing framework | Run any one Processing algorithm by id | PARTIAL: 42 algorithms of the 772 in the 4.2.2 registry are allowed |
| 1 | expressions | Expression functions that reach the system (env, file functions, eval_template) | PARTIAL: UNSCREENED. A model-written expression can call env() and the file-name functions; no function allow/deny list exists in field_calculator, highlight_features or apply_labels. Security review item |
| 2 | data sources | Run a read-only SQL query on a database or the project layers | PARTIAL: result is a table, not a SQL query layer or virtual layer |
| 2 | project and canvas | Elevation profile of a line over a DEM | PARTIAL: returns arrays for a chart, not the QGIS elevation profile panel |
| 2 | attributes | Zoom / pan to the selection | PARTIAL: one feature by id or expression, not 'the current selection' |
| 2 | editing | Split features by a line / split parts / merge selected features | PARTIAL: splits LINES by zone polygons only |
| 2 | editing | Geometry and topology checks, gap/overlap/duplicate checks | PARTIAL: one diagnostic tool; the 20 geometry-check algorithms are not individually reachable |
| 2 | raster | Image classification (unsupervised, supervised), pan-sharpening | PARTIAL: supervised classification needs the SAGA provider, which QGIS 4.2.2 does not ship (#162) |
| 2 | vector analysis | Random points / regular points / create grid | PARTIAL: create grid is allow-listed; random and regular points are not |
| 2 | processing framework | Search the toolbox for an algorithm by name | PARTIAL: finds this plugin's tools, not the QGIS toolbox |
| 3 | project and canvas | Temporal controller / animation of a time layer | PARTIAL: produces an HTML dashboard and frames, does not configure the QGIS temporal controller |
| 3 | processing framework | Processing history and results viewer | PARTIAL: plugin's own log only |
| 3 | specialised | GPS: GPX layers, GPS tracking, live position | PARTIAL: a GPX file opens as its first layer; no GPS panel / tracking |

## 8. Actions with no tool: priority 1 (17)

| P | Area | Action | What the code shows |
|---|---|---|---|
| 1 | data sources | Choose one layer inside a multi-layer container | no sublayer selection anywhere in add_layer_from_path |
| 1 | data sources | Add a WMS / WMTS web map layer | no web-service layer provider is used anywhere (no QgsRasterLayer with wms) |
| 1 | data sources | Add an XYZ tile basemap (OpenStreetMap, satellite) | the HTML dashboard has a basemap; the QGIS project cannot get one |
| 1 | data sources | Create an empty scratch (memory) layer with chosen geometry type and fields | only add_point_layer / add_incident_point create layers from scratch, points only |
| 1 | data sources | Create a new GeoPackage / Shapefile / SpatiaLite / GPX layer | export_layer writes existing layers; no empty-layer creation |
| 1 | project and canvas | Create, rename, collapse a layer GROUP and move layers into it | no group creation anywhere (QgsLayerTreeGroup appears only inside routing_style.py) |
| 1 | project and canvas | Zoom to a scale, to an extent, pan, rotate the map, zoom last/next | no scale, extent, pan or rotation control (setScale / zoomScale not used anywhere) |
| 1 | project and canvas | Set the project CRS | get_crs reads; setCrs appears only in layout and isolation code |
| 1 | project and canvas | Measure distance, area, bearing between points | QgsDistanceArea is used inside analysis tools, there is no measure tool |
| 1 | attributes | Clear selection / select all / deselect | no tool; removeSelection not used anywhere |
| 1 | attributes | Delete, rename, or change the type of a field | no field management (field_calculator adds/updates only) |
| 1 | attributes | Edit a single attribute value of one feature | only expression-based field_calculator writes values |
| 1 | attributes | Delete features (selected or by expression) | deleteFeatures is used only in hazard_monitoring_tools.py for its own layers |
| 1 | attributes | Filter a layer (definition query) so only matching features are shown | run_query returns matches but does not set a layer filter (setSubsetString is not used by any tool) |
| 1 | editing | Start / stop editing, save or discard edits | edit sessions are internal to each tool; no user-facing toggle |
| 1 | raster | Reproject / warp a raster | reproject_layer is vector only |
| 1 | raster | Raster calculator (map algebra) | gdal:rastercalculator stays off (its FORMULA is evaluated as Python, audit #137) and a script cannot run Processing. BUT the 4.2.2 registry has native:rastercalc / native:virtualrastercalc, which use QGIS's own raster-calculator grammar (QgsRasterCalculator, not Python eval): the safe route, needs an expression check and a live test |

## 9. Actions with no tool: priority 2 (28)

| P | Area | Action | What the code shows |
|---|---|---|---|
| 2 | data sources | Open a zipped shapefile or .kmz (vsizip) | a downloaded zip is refused with an explanation |
| 2 | data sources | Open a PostGIS / database table as a layer | execute_read_only_sql reads a PostGIS connection but returns rows, it does not add a layer |
| 2 | data sources | Create a virtual layer from a SQL query over layers | - |
| 2 | data sources | Add a WFS / WCS / ArcGIS REST feature service | - |
| 2 | data sources | Load / save a QLR layer definition file | load_layer_style reads QML only |
| 2 | data sources | Repair broken layer paths (resolve bad layers) | tidy_project_layers handles duplicates, ramps and scratch layers, not missing sources |
| 2 | data sources | Package layers for offline use | - |
| 2 | project and canvas | Layer groups: set mutually exclusive, check/uncheck whole group | - |
| 2 | project and canvas | Set a layer's CRS without reprojecting (Assign projection) | - |
| 2 | project and canvas | Bookmarks: create, list, go to | no bookmark code |
| 2 | project and canvas | Project properties: title, metadata, variables, relations, snapping, default styles, relative paths | - |
| 2 | project and canvas | Layer metadata (title, abstract, license, contacts) | provenance sidecar files exist, QgsLayerMetadata is not written |
| 2 | attributes | Copy / paste selected features between layers | - |
| 2 | attributes | Identify a feature on the map | needs a map click; no query by coordinate |
| 2 | editing | Move, rotate, scale a feature | - |
| 2 | symbology | Symbol layers, SVG / font markers, hatch fills, draw effects, blend modes, symbol levels | - |
| 2 | symbology | Raster: paletted / unique values, hillshade renderer, contours renderer, resampling, transparency, no-data | classification tools style their own output; no general control |
| 2 | layouts | Add picture, shape, arrow, HTML frame, attribute table, fixed table, chart, 3D map, elevation profile items | create_print_layout builds a fixed composition; no add-item tool |
| 2 | layouts | Set the map item extent, scale, rotation, locked layers, overview map | PARTIAL: zoom_to_layer flag only |
| 2 | layouts | Page size, several pages, guides, grid, resize to content | orientation only |
| 2 | layouts | Save / load a layout template (.qpt) | - |
| 2 | raster | Resample, change resolution, translate / convert format | - |
| 2 | raster | Raster to points / polygons (pixels to points, polygonize), rasterize vector | GDAL file-output algorithms need code changes in _resolve_params/harvest_outputs |
| 2 | raster | Proximity (distance) raster, fill nodata, sieve, align rasters | - |
| 2 | raster | Raster histogram and band statistics | histogram_equalization changes an image, it does not report |
| 2 | vector analysis | Extract vertices / densify / polygons to lines / lines to polygons / bounding geometry / boundary | no tool and not on the allow-list; script fallback only |
| 2 | vector analysis | Delete duplicate geometries / split by attribute / extract by attribute / extract by expression / refactor fields | expression-taking algorithms are left off the allow-list on purpose |
| 2 | processing framework | Run a Processing model (graphical modeler) / batch process / run a Processing script | - |

## 10. Actions with no tool: priority 3 (27)

| P | Area | Action | What the code shows |
|---|---|---|---|
| 3 | data sources | Add a vector tile layer (MVT, MBTiles, PMTiles) | no QgsVectorTileLayer anywhere |
| 3 | data sources | Add a 3D tiles / tiled scene layer | - |
| 3 | data sources | Open a mesh layer (UGRID, NetCDF, GRIB, 2DM) | no QgsMeshLayer anywhere |
| 3 | data sources | Open a point cloud (LAS, LAZ, COPC, EPT) | no QgsPointCloudLayer anywhere; 24 PDAL algorithms exist in QGIS |
| 3 | data sources | Import / export DXF | native:dxfexport exists in QGIS |
| 3 | project and canvas | Datum transformations, custom CRS, ellipsoid, measurement units | - |
| 3 | project and canvas | Map decorations: grid, title, copyright, north arrow, scale bar on the canvas | decorations exist only inside print layouts |
| 3 | project and canvas | Annotations on the canvas | - |
| 3 | project and canvas | 3D map view | - |
| 3 | attributes | Virtual fields, conditional formatting, forms, widgets, constraints, default values | - |
| 3 | attributes | Define 1-N / N-M relations between layers | - |
| 3 | attributes | Layer actions and map tips | - |
| 3 | attributes | Auxiliary storage (stored label positions and styles) | - |
| 3 | editing | Vertex edit: add, move, delete vertices | - |
| 3 | editing | Add part / ring, fill ring, delete ring/part | - |
| 3 | editing | Reshape, offset curve, chamfer/fillet, reverse line, trim/extend | - |
| 3 | editing | Snapping and topological editing settings | - |
| 3 | symbology | Merged features, inverted polygon, 2.5D, embedded and no-symbol renderers | - |
| 3 | symbology | Diagrams (pie, bar, histogram) | - |
| 3 | symbology | Style manager: reusable symbols, colour ramps, text formats | - |
| 3 | layouts | Reports (layout report with sections) | - |
| 3 | raster | Viewshed, watershed, flow accumulation, terrain ruggedness | no core algorithm in 4.2; a tool would need a plugin or own code |
| 3 | raster | Build pyramids / overviews, raster attribute tables, identify a cell value | - |
| 3 | vector analysis | Spatial index, snap geometries, topological coverage, line / polygon tools (smooth, subdivide, split with lines, offset, clean) | - |
| 3 | processing framework | In-place layer modification (edit selected features with an algorithm) | - |
| 3 | specialised | Publish the project through QGIS Server (WMS/WFS properties) | out of scope for the assistant; named for completeness |
| 3 | specialised | Authentication: store credentials for a layer or service | the plugin keeps its own provider keys in the Auth Manager, but offers no layer authentication |

## 11. Plugin-developer documentation (`pyqgis_developer_cookbook/plugins`, `releasing.rst`, other chapters)

| Cookbook chapter | What it asks of a plugin | Status |
|---|---|---|
| `plugins/plugins.rst` and `releasing.rst` | metadata.txt keys, `classFactory`, `initGui`/`unload`, no hidden files, unique version, validation on upload | followed and tested (`tests/test_metadata_parses.py`, `plugin_upload.py`, CONTRIBUTING section 9) |
| `communicating.rst` | `QgsMessageBar`, progress, `QgsMessageLog` | used |
| `tasks.rst` | `QgsTask`, task from a Processing algorithm | used for long Processing runs where safe |
| `settings.rst`, `authentication.rst` | `QgsSettings`, Auth Manager, no plaintext secrets | followed for the plugin's own keys; no layer authentication offered to the user |
| `processing.rst` | Processing provider and algorithms | provider exists (hub siting, service area); 2 algorithms |
| `loadproject.rst` | resolve bad paths, project flags | **not offered** to the user |
| `legend.rst` | layer tree, groups | groups **missing** |
| `canvas.rst` | map tools, rubber bands, identify | no identify, no map tools |
| `composer.rst` | layouts, atlas | layout creation, atlas, text editing; no add-item tool |
| `expressions.rst` | parse, evaluate, filter a layer | evaluate and select; no filter (`setSubsetString`) |
| `crs.rst`, `geometry.rst`, `raster.rst`, `vector.rst` | CRS transform, geometry ops, raster renderers, edit buffer | partial, see sections 7 to 10 |
| `network_analysis.rst` | graph, shortest path, areas | covered by the logistics tools |
| `server.rst`, `pluginlayer.rst` | QGIS Server plugins, custom plugin layers | out of scope |
| `plugins/snippets.rst` | key shortcuts, icons, options page, layer-tree widgets | not used |

## 12. Build order (waves), with the proof each wave needs

Rules that apply to every wave (they are what stops regressions):

1. **No optimisation without a before and after.** A change to the router, prompt, guards, token budget or tool schemas pastes the result of `tools/replay_router_across_releases.py` and the golden-suite counts into the PR.
2. **The ratchet.** `tests/test_qgis_coverage_ratchet.py` fails if any of the 163 actions gets worse or a row is deleted. A wave raises rows by building the tool and re-writing `baseline.json` in the same reviewed PR.
3. **Golden suites only grow** (`GOLDEN`, `GOLDEN_LONG`, `VOCAB`, the 42-algorithm table); a test pins their sizes.
4. **Every new tool or algorithm ships with**: a unit test, a live test in the QGIS 4.2.2 image, a golden phrase, a row in the matrix, and a line in the hand-test pack.
5. **Release gate**: the workflow runs the golden suites and the ratchet; a stable number additionally needs the START HERE rows run by a person on the release candidate, results attached.

| Wave | Scope | Size | Exit criteria |
|---|---|---|---|
| **0 Safety net** | schema snapshot test; size pins for the golden suites; release gate in `release.yml`; PR template with the before and after table; a live test that runs all 42 allow-listed algorithms by id | M | the 34 untested algorithms each pass a live run; deleting a tool, a row or an alias fails CI |
| **1 Foundation** | `add_layer_from_path` v2 (sublayer choice, GDAL probing for any raster, `/vsizip/`, KMZ, GPX layers), `export_layer` v2 (CRS, extent, field subset, more drivers, raster formats), `get_layers` reports layer type, geometry type including Z/M/curved, CRS and feature count; layer groups; project CRS; zoom to scale and extent; bookmarks | L | rows in sections 8 (data sources, project) move to COVERED |
| **2A Vector geometry** (88 algorithms) | e.g. native:affinetransform, native:antimeridiansplit, native:approximatemedialaxis, native:boundary, native:boundingboxes, native:bufferbym, native:checkvalidity, native:collect, native:concavehull, native:concavehullbyfeature, native:convertgeometrytype, native:converttocurves, native:coveragesimplify, native:coverageunion ... (+74) | M | each through the generic tool with a parameter-rule table row and a live run |
| **2B Table and selection** (36) | native:addfieldtoattributestable, native:adduniquevalueindexfield, native:addxyfields, native:assignprojection, native:batchnominatimgeocoder, native:bookmarkstolayer, native:createattributeindex, native:createspatialindex, native:definecurrentprojection, native:deletecolumn, native:deleteduplicategeometries, native:detectvectorchanges, native:dropgeometries, native:explodehstorefield ... (+22) | M | add/delete/rename fields, extract by attribute, random selection, spatial indexes |
| **2C Analysis and creation** (36) | native:angletonearest, native:arrayoffsetlines, native:arraytranslatedfeatures, native:calculatevectoroverlaps, native:climbalongline, native:createpointslayerfromtable, native:distancematrix, native:distancetonearesthub, native:extenttolayer, native:extractlabels, native:extractnetworkendpoints, native:generatepointspixelcentroidsinsidepolygons, native:heatmapkerneldensityestimation, native:hublines ... (+22) | M | random points, regular points, grids, distance matrix, hub lines, mean coordinates |
| **2D Raster** (73) | gdal:aspect, gdal:assignprojection, gdal:buildvirtualraster, gdal:cliprasterbyextent, gdal:extractprojection, gdal:fillnodata, gdal:gridaverage, gdal:griddatametrics, gdal:gridinversedistance, gdal:gridinversedistancenearestneighbor, gdal:gridlinear, gdal:gridnearestneighbor, gdal:hillshade, gdal:nearblack ... (+59) | L | terrain indices, cell statistics, raster creation, align, fill nodata, rasterize, warp |
| **2E Geometry quality** (31) | native:checkgeometryangle, native:checkgeometryarea, native:checkgeometrycontained, native:checkgeometrydangle, native:checkgeometrydegeneratepolygon, native:checkgeometryduplicate, native:checkgeometryduplicatenodes, native:checkgeometryfollowboundaries, native:checkgeometrygap, native:checkgeometryhole, native:checkgeometrylineintersection, native:checkgeometrylinelayerintersection, native:checkgeometrymissingvertex, native:checkgeometrymultipart ... (+17) | M | the 21 checks and 10 fixes as one family with one report |
| **2F Other** (19) | gdal:importvectorintopostgisdatabasenewconnection, gdal:rasterize, gdal:rasterize_over, gdal:rasterize_over_fixed_value, native:addhistorymetadata, native:calculateexpression, native:condition, native:copylayermetadata, native:createdirectory, native:exportlayersinformation, native:filter, native:importintospatialite, native:loadlayer, native:polygonfromlayerextent ... (+5) | S | metadata and layer tools |
| **3 Expressions** (16) | an expression screen (deny `env`, file and system functions, bound the length), then `native:rastercalc`, `native:virtualrastercalc`, `native:extractbyexpression`, `native:fieldcalculator`, `native:selectbyexpression`, `native:aggregate`, `native:refactorfields` | M | the screen has its own test list; the raster calculator passes a live run; `field_calculator` and `highlight_features` use the same screen |
| **4 File outputs and path inputs** (77) | an export-style tool with a confirmed output path: `native:package`, DXF export, split vector layer, atlas to PDF, import into SpatiaLite and PostGIS | M | every output path is shown and confirmed, never model-chosen silently |
| **5 New layer types** (34) | mesh, point cloud, vector tile, 3D tiles, annotation layers; web services (WMS, WMTS, WFS, XYZ, ArcGIS REST) with a vetted basemap list | L | each layer type loads, is listed by `get_layers`, and its algorithms are reachable |
| **6 GUI-level actions** | feature editing through the checked edit session (change values, delete with the confirmation gate, add geometry from WKT, move), layer filter, selection (clear, export), measure, identify by coordinate, symbology depth (outline, width, marker, line pattern, rule-based labels, diagrams), layout items (picture, shapes, tables), reports | L, one PR per row | rows in sections 8 and 9 move to COVERED |
| **7 Optional providers** (307) | GRASS, only when the provider is present | S | offered only if `providerById('grass')` exists |
| Never | gdal:executesql, gdal:gdal2tiles, gdal:rastercalculator, native:downloadgpsdata, native:downloadvectortiles, native:filedownloader, native:fileuploader, native:httprequest, native:openurl, native:postgisexecuteandloadsql, native:postgisexecutesql, native:spatialiteexecutesql, native:spatialiteexecutesqlregistered, qgis:advancedpythonfieldcalculator | - | stay excluded; the matrix records why |

Each wave is a separate PR with its own CI run and a short hand-test section. Nothing in a wave is released until the previous wave's ratchet and golden suites are green on the release commit.

## 13. Decisions needed from the owner

1. Approve wave 0 (nothing user-visible changes; it is what stops the regressions).
2. Approve the mechanical rule for the Processing allow-list: an algorithm is added only if the registry dump shows plain parameter types, it has a live test, and it has a parameter-rule row. The `proposed_wave` column is the queue.
3. Approve `native:rastercalc` as the raster calculator (instead of a new parsed-formula tool) once the expression screen exists.
4. Approve an expression screen that denies `env()` and the file and system functions in every model-written expression (a behaviour change for anyone relying on them).
5. Order of waves 1, 5 and 6 (my order is by how often a GIS user needs the action).
