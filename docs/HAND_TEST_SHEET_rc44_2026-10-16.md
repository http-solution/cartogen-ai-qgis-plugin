# Hand-test sheet for everything new in 1.17.0 (rc42 to rc44; run on the rc46 build) -- 2026-10-16

**Goal:** check by hand, in desktop QGIS with a real model, the functionality added since the last stable build (1.16.3) that no person has tried yet.
It goes straight to the new tools and algorithms: no installation, update check or API-key steps. Everything here passed the offline suite and CI on QGIS
4.2.2 on small synthetic data; **none of it has been hand-tested**, and no real model has been observed choosing these tools.

**Scope:** 82 new tools (30 from rc42, 34 from rc43, 18 from rc44) and 385 new Processing algorithms (rc42: 124, rc43: 101, rc44: 160, of which 154 GRASS and 6 mesh).
Companion files (open in a spreadsheet, fill the Result column): `docs/HAND_TEST_rc44_tools.csv` (all 83 tool rows below) and
`docs/HAND_TEST_rc44_algorithms.csv` (all 385 algorithm rows, with a ready-to-paste prompt each).

## Run this on rc46; what changed since rc45
The rc45 run of this sheet found problems that rc46 changes. Retest these first (the four rc45 fixes below passed in that run):
1. **Undo across messages.** Make a change (a filter, a diagram, rule labels, a deleted feature), send the NEXT message "undo the last operation", confirm. The change must be reversed, and a deleted feature must come back.
2. **Remove labels.** "Take the rule labels off the towns" must work without an error.
3. **A layer of the wrong kind.** Ask for a reclassification using a raster as the table; the chat must refuse before running, not hang.
4. **Time limit.** A native algorithm that runs more than 5 minutes now stops itself with a message; note if you see it. GRASS runs keep the window painting but cannot be stopped.
5. **Layout names, snapping, overview map.** "Test Layout" finds `Layout_Test_Layout`; snapping to vertices and segments sets both; the overview map is the size asked for (50 by 40 mm).
6. **Plain-language algorithm test.** See `7_PLAIN_LANGUAGE_SHEET.md` in the bundle: the same 385 algorithms asked without naming them.

## The four rc45 fixes (passed in the rc45 run)
Use the rc45 plugin zip: rc44 has four calls to QGIS methods that do not exist, fixed in rc45. These four should now work; mark each row Pass only if it does, and note it on the row:
1. `zoom_history` (row 25): zoom twice, ask for the previous extent, then the next; at the start of the history it must say there is no earlier extent, not report success.
2. `diagnose_topology`: run it on a layer with a self-crossing (bow-tie) polygon; it must count that polygon as invalid.
3. Point-displacement representation: ask for a point-displacement map of `towns`; it must apply without an error.
4. Proxy: with a proxy set in QGIS network settings, any web tool (for example a fetch) must still run; with none set, nothing changes.

## How to score
Type each prompt into the chat as written (replace `<...>`). Result: **Pass** = did what the Expect column says; **Partial** = worked but something
is wrong or ugly (say what); **Fail** = error, wrong result, or the model picked the wrong tool; **Skip** = you lack the data/module (say which).
For every Fail/Partial, copy the exact prompt, the tool the chat showed it called, and the message. Two questions matter beyond Pass/Fail and are worth a note on
every row: **(1) did the model choose the right tool without being told its name? (2) does the result LOOK right?** Those two are exactly what CI cannot check.

## 0. Fixtures (10 minutes, once)
Paste this into the QGIS Python console (Plugins > Python Console > Show Editor). **It was written without being run**: if it errors, create layers with the same
names and fields by hand; the sheet only needs the names. It builds in-project layers named `towns`, `roads`, `districts`, rasters `dem` and `dem2`, and a mesh `mesh1`,
and prints the temporary folder where the files live.
```python
import os, tempfile
import numpy as np
from osgeo import gdal, osr
from qgis.core import (QgsProject, QgsVectorLayer, QgsRasterLayer, QgsMeshLayer, QgsFeature, QgsGeometry, QgsCoordinateReferenceSystem)
folder = tempfile.mkdtemp(prefix="rc44_")

def mem(kind, name, fields, rows):
    lyr = QgsVectorLayer(f"{kind}?crs=EPSG:4326&" + "&".join(f"field={f}" for f in fields), name, "memory")
    feats = []
    for wkt, attrs in rows:
        f = QgsFeature(lyr.fields()); f.setGeometry(QgsGeometry.fromWkt(wkt)); f.setAttributes(attrs); feats.append(f)
    lyr.dataProvider().addFeatures(feats); lyr.updateExtents(); QgsProject.instance().addMapLayer(lyr)
    return lyr

sq = lambda x, y: f"POLYGON(({x} {y},{x+2} {y},{x+2} {y+2},{x} {y+2},{x} {y}))"
mem("Polygon", "districts", ["name:string", "pop:integer", "area_km2:double"],
    [(sq(0, 0), ["A", 1200, 40.0]), (sq(2, 0), ["B", 800, 35.5]), (sq(0, 2), ["C", 1500, 52.1]), (sq(2, 2), ["D", 300, 20.0])])
mem("Point", "towns", ["name:string", "pop:integer", "seen:date"],
    [(f"POINT({0.5 + i * 0.45} {0.4 + (i * 0.7) % 3.4})", [n, p, f"2026-0{1 + i % 6}-1{i}"])
     for i, (n, p) in enumerate(zip("abcdefgh", (5, 50, 500, 20, 150, 90, 700, 10)))])
mem("LineString", "roads", ["name:string", "type:string"],
    [("LINESTRING(0 0,1 1,2 1.5,4 4)", ["r1", "primary"]), ("LINESTRING(0 4,2 2,4 0)", ["r2", "secondary"]), ("LINESTRING(0 2,4 2)", ["r3", "primary"])])

def raster(name, holes):
    path = os.path.join(folder, name + ".tif")
    ds = gdal.GetDriverByName("GTiff").Create(path, 80, 80, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((0.0, 0.05, 0.0, 4.0, 0.0, -0.05))
    srs = osr.SpatialReference(); srs.ImportFromEPSG(4326); ds.SetProjection(srs.ExportToWkt())
    y, x = np.mgrid[0:80, 0:80]
    z = 100 + 40 * np.sin(x / 12.0) + 30 * np.cos(y / 15.0) + 60 * np.exp(-(((x - 40) / 12.0) ** 2 + ((y - 40) / 12.0) ** 2))
    if holes: z[10:16, 10:20] = -9999
    b = ds.GetRasterBand(1); b.SetNoDataValue(-9999); b.WriteArray(z.astype("float32")); ds.FlushCache(); ds = None
    QgsProject.instance().addMapLayer(QgsRasterLayer(path, name))
raster("dem", False); raster("dem2", True)

mesh_path = os.path.join(folder, "m.2dm")
tri = [(1, 2, 4), (2, 5, 4), (2, 3, 5), (3, 6, 5), (4, 5, 7), (5, 8, 7), (5, 6, 8), (6, 9, 8)]
open(mesh_path, "w").write("MESH2D\n" + "".join(f"E3T {i} {a} {b} {c} 1\n" for i, (a, b, c) in enumerate(tri, 1)) +
                           "".join(f"ND {n} {((n - 1) % 3) * 2} {((n - 1) // 3) * 2} {float(n * 10)}\n" for n in range(1, 10)))
m = QgsMeshLayer(mesh_path, "mesh1", "mdal"); m.setCrs(QgsCoordinateReferenceSystem("EPSG:4326")); QgsProject.instance().addMapLayer(m)
print("fixtures in", folder)
```
Also once: ask the chat **"create a print layout of the map called Test Layout"**. Optional extras for rows that say SKIP-if-missing: an `.svg` icon, a `.qlr` file,
a PostGIS connection, a `.copc.laz` or `ept.json` point cloud, a vector-tile or 3D-tiles source, and QGIS with the GRASS provider (Processing Toolbox shows a GRASS group).

## Recommended order (about 3 to 4 hours for everything; 90 minutes for parts 1, 2 and 4)
1. Part 1 rc44 tools (18 rows) 2. Part 4 integration checks 3. Part 2 rc43 tools (34) 4. Part 3 rc42 tools (30) 5. Part 5 Processing: the priority list, then the CSV as time allows.

## Part 1. New in rc44 (symbology, layouts, new layer types, elevation)

| # | Tool | Prompt to type | Expect | Result | Notes |
|---|---|---|---|---|---|
| 1 | `set_rule_based_labels` | Label towns with rules: bold dark labels for towns with population above 100, small grey labels for the others. | Two label looks on the map; Layer Styling > Labels shows Rule-based with two rules. Then 'undo the last operation' returns to the previous labels. | | |
| 2 | `set_label_callout` | First: label towns by name. Then: add callout lines to the town labels, a red 0.4 mm line with a manhattan style, and a white mask around the label text. | Needs simple labels first (a layer without labels is refused with a hint). Callout lines show once a label sits away from its point (move one with the Label toolbar); mask halo visible. Undo restores. | | |
| 3 | `set_layer_diagram` | Show a pie chart diagram of pop and area_km2 on districts, 12 mm. | A pie per district; Layer Styling > Diagrams is active. 'remove the diagram from districts' clears it. Undo works. | | |
| 4 | `set_point_marker` | Make the town markers a star from the font Arial, 5 mm, orange. Then use the SVG file <path to any .svg> as the marker. | Markers change to a font character, then to the SVG. A polygon layer is refused with a clear message. | | |
| 5 | `set_raster_relief` | Style dem as a hillshade with azimuth 315 and altitude 45. Then show contour lines every 20 with an index line every 100. | Hillshade renderer, then a contour renderer, on the dem. Undo restores the previous style. | | |
| 6 | `save_symbol_to_library` | Save the symbol of the layer towns to my library as 'town-star'. | Success message with the name; saving the same name again asks before overwriting. | | |
| 7 | `list_saved_symbols` | What symbols do I have in my library? | Lists 'town-star' (and any others) with tags. | | |
| 8 | `apply_saved_symbol` | Save the style of the layer roads as a symbol called road-test, then apply the saved symbol road-test to the layer roads. | Asks for confirmation (symbol type must fit); after confirming the symbol changes; undo restores. | | |
| 9 | `add_overview_map` | In Test Layout add an overview map in the top-right corner, 50 by 40 mm, with a red frame. | An inset map appears with a red rectangle showing the main map's extent; moving the main map moves the frame. | | |
| 10 | `set_layout_guides_grid` | In Test Layout add a vertical guide at 20 mm and a horizontal guide at 15 mm, and set the snapping grid to 5 mm. | Guides show in the layout designer; the grid spacing is 5 mm; items snap to it. | | |
| 11 | `set_layout_atlas` | In Test Layout set up an atlas with one page per district, named by the name field, sorted by name. | Atlas panel shows the coverage layer districts and 4 pages; atlas preview steps through districts. | | |
| 12 | `add_layout_chart` | In Test Layout add a bar chart of pop by name for the layer towns, 120 by 80 mm. Then a pie chart, then a line chart. | A chart item appears each time; check bars/pie/line show the right values (this has only been checked for existence so far - note how it LOOKS). Try with a layer tagged RESTRICTED: a warning appears. | | |
| 13 | `add_layout_elevation_profile` | Turn on elevation for dem, then in Test Layout add an elevation profile for dem along the line from 0.2,0.2 to 3.8,3.8. | Without elevation on, the tool says so. With it on, a profile item appears; check the profile curve follows the dem along the line. | | |
| 14 | `export_layout` | Export Test Layout to a PNG with a world file, and to a GeoPDF. | PNG plus a .wld file next to it; a GeoPDF opens in a viewer (georeferenced if the viewer supports it). Overwrite asks first. | | |
| 15 | `add_point_cloud_layer` | Open the point cloud <path to a .copc.laz or an ept.json> as a layer. Then try a plain .las or .laz. | COPC/EPT opens and draws. A plain .las/.laz opens only if QGIS has the PDAL provider; otherwise a clear message says so. SKIP if you have no point cloud. | | |
| 16 | `add_vector_tile_layer` | Add the vector tile layer https://basemaps.cartocdn.com/vectortiles/carto.streets/v1/{z}/{x}/{y}.mvt (zoom 0 to 14). Then try a local .mbtiles file. | Tiles draw (example URL; use any vector tile service you can reach). http:// URLs and URLs without {z}/{x}/{y} are refused. | | |
| 17 | `add_3d_tiles_layer` | Add the 3D tiles tileset <URL or path of a tileset.json>. | The tiled scene layer is added (it draws in 3D views; in 2D it may look empty). SKIP if you have no tileset. | | |
| 18 | `set_layer_elevation` | Turn on elevation for dem as a surface, band 1, offset 5 m. For towns set clamping to relative with extrusion 12 m. | Layer Properties > Elevation shows the settings. Asking to 'enable' a vector layer is refused (vectors have no switch). Undo restores. | | |
| 19 | `set_project_terrain` | Use dem as the project terrain with scale 1.5. Then set the terrain to flat with offset 0. | Project Properties > Elevation shows the DEM terrain, then flat. A 3D view (View > 3D Map Views) uses it. | | |

**rc44 things to look at on every row:** the new colours/ramps on raster and mesh results, and whether 'undo the last operation' reverses the styling rows (labels, callout, diagram, marker, relief, saved symbol, elevation) - undo is wired for those and CI-tested on small layers only.

## Part 2. New in rc43 (editing, data sources, styling, layouts, project settings)

| # | Tool | Prompt to type | Expect | Result | Notes |
|---|---|---|---|---|---|
| 1 | `set_layer_filter` | Filter districts to only those with pop above 1000. Then clear the filter. | Only matching features draw; Layer Properties > Source > Query Builder shows the filter; clearing restores all. Text with ; or comments is refused. Undo restores. | | |
| 2 | `transform_features` | Move the towns with pop above 100 by 0.5 degrees east, rotate them 30 degrees, scale them 1.2. | Shows a preview with the exact count first; after you confirm the geometries change (rotation and scale are about each feature's centre, so single points only move). Reversible with undo_manual_edit while the layer is in edit mode. | | |
| 3 | `merge_features` | Select the districts named A and B, then merge the selected districts into one feature. | Preview with counts, then one merged feature: the first feature keeps its attributes and the others are deleted, so confirm only on a copy. Needs at least two features. | | |
| 4 | `split_features_by_line` | Split districts with the line LINESTRING(1 -1, 1 5). | Preview, then districts crossing x=2 are split; a line that misses everything is reported. | | |
| 5 | `undo_manual_edit` | Start editing towns, change one value by hand, then say: undo my last edit on towns. | The hand edit is reversed (works only while the layer is in edit mode; for assistant operations on a layer not in edit mode the model should use undo_last_operation instead). | | |
| 6 | `redo_manual_edit` | Redo the edit on towns. | The undone edit returns. | | |
| 7 | `change_field_type` | Change the field pop on towns to text. | Preview says how many values cannot be converted (they become NULL); after confirming the type changes and the field moves to the end of the table. | | |
| 8 | `set_layer_editing` | Start editing towns. Then save the edits. Start again and discard the changes. | Toggle edit mode, save, and discard work; discard asks for confirmation. | | |
| 9 | `add_postgis_layer` | Add the PostGIS table public.<table> from the connection <your saved connection>. | Layer is added without asking for a password in chat (credentials come from the saved connection). SKIP if you have no PostGIS. | | |
| 10 | `create_virtual_layer` | Create a virtual layer called big_towns with SQL: SELECT name, pop, geometry FROM towns WHERE pop > 10. | A live virtual layer appears. A query that writes (INSERT/ATTACH) or names a file path is refused. | | |
| 11 | `load_layer_definition` | Load the QLR file <path>. | Layers from the .qlr appear with their styles. | | |
| 12 | `save_layer_definition` | Save towns and districts as a QLR file at <path>. | A .qlr is written; overwriting asks first; reload it with load_layer_definition. | | |
| 13 | `package_layers_offline` | Package towns, roads and districts into one GeoPackage at <path>. | One .gpkg with the three layers and their styles. With a RESTRICTED layer a warning appears. Overwriting asks first. | | |
| 14 | `add_layer_from_path (new formats)` | Add the NetCDF file <path.nc> / mesh file <path.2dm>. | Raster or mesh layer opens as the file type says (ECW/MrSID only if your QGIS has the driver). SKIP files you do not have. | | |
| 15 | `set_layer_symbol` | Make districts fill light yellow with a grey 0.3 mm outline at 60 percent opacity. | The symbol changes accordingly (check colours and opacity by eye). | | |
| 16 | `set_label_style` | Give the town labels a white halo 1 mm, size 10, bold, placed around the point. | Labels get the halo and style. | | |
| 17 | `set_raster_style` | For dem use cubic resampling and 70 percent opacity, and treat values below 0 as no data. | Raster renders accordingly (resampling, opacity, no-data). | | |
| 18 | `add_layout_item` | In Test Layout add a label 'Hello' at 10,10; a picture <path>; a rectangle; an arrow; an attribute table of towns (name, pop). | Each item appears; the table shows the chosen fields. HTML frames are refused on purpose. | | |
| 19 | `edit_layout_item` | Move the label to 60,10, rotate it 15 degrees, then remove the arrow. | Item moves/rotates; removal works; wrong ids are reported. | | |
| 20 | `set_layout_map` | Set the map in Test Layout to scale 1:5000000, rotation 10, and fit it to the layer districts. | Map scale/rotation/extent update. | | |
| 21 | `set_layout_page` | Set the Test Layout page to A3 landscape. | Page size changes. | | |
| 22 | `save_layout_template` | Save Test Layout as a template at <path>. | A .qpt file is written (overwrite asks). | | |
| 23 | `load_layout_template` | Load the template <path> as a new layout called From Template. | New layout appears with the template's items. | | |
| 24 | `rename_layer_group` | Put the layers towns and roads in a group called Test group, then rename the group Test group to Base data. | Group renamed in the layer tree. | | |
| 25 | `zoom_history` | Zoom to the previous extent, then to the next one. | Map returns to earlier extents (needs the real canvas). | | |
| 26 | `get_layer_metadata` | Show the metadata of towns. | Title, abstract, keywords, etc. shown. | | |
| 27 | `set_layer_metadata` | Set the title of towns to 'Test towns', abstract 'Hand test', keywords test, rc44. | Layer Properties > Metadata shows the values. | | |
| 28 | `set_snapping_options` | Turn on snapping to vertices and segments with 12 pixels tolerance and topological editing. | Project > Snapping Options reflects it. | | |
| 29 | `create_relation` | Create a relation called district_towns: parent districts.name, child towns.name. | Project Properties > Relations lists it (use fields that make sense in your data). | | |
| 30 | `list_relations` | List the relations. | Shows district_towns. | | |
| 31 | `set_layer_temporal` | Make towns time-aware using the field seen. | Layer Properties > Temporal is on with seen as start field; undo restores. | | |
| 32 | `set_project_time_range` | Set the project time range from 2026-01-01 to 2026-12-31. | Project Properties > Temporal shows the range. | | |
| 33 | `add_text_annotation` | Add the text 'Check this area' at 1.5, 1.5 on the map. | Annotation appears on the canvas. | | |
| 34 | `remove_annotations` | Remove all annotations. | Asks first, then removes them. | | |

## Part 3. New in rc42 (layers, selection and attributes, groups, map view, analysis)

| # | Tool | Prompt to type | Expect | Result | Notes |
|---|---|---|---|---|---|
| 1 | `create_empty_layer` | Create an empty polygon layer called study_area with fields name text and ha number. | Empty scratch layer with those fields; with a .gpkg path it is saved there. | | |
| 2 | `add_basemap` | Add an OpenStreetMap basemap. | Basemap at the bottom of the tree; asking again reuses it. | | |
| 3 | `add_web_layer` | Add the WMS layer <https URL> layer <name>. | Layer added; http:// URLs and localhost are refused. SKIP without a service. | | |
| 4 | `find_broken_layers` | Which layers in the project are broken? | Lists layers with missing files (move a file first to see one). | | |
| 5 | `repair_layer_source` | Repair the broken layer <name> by looking in <folder>. | Layer source repointed and the layer draws. | | |
| 6 | `save_layer_as` | Save districts as a GeoPackage at <path> in EPSG:3857 with only name and pop. | New file written; overwrite asks first; the layer is added if asked. | | |
| 7 | `select_by_expression` | Select the towns where pop > 100. | Matching points highlighted; a dangerous expression (file functions) is refused. | | |
| 8 | `select_all_features` | Select all districts. | All selected. | | |
| 9 | `clear_selection` | Clear the selection. | Selection cleared. | | |
| 10 | `delete_features` | Select the towns with pop below 50, then delete the selected towns. | Preview with count; deleted only after confirmation; undo_manual_edit reverses. | | |
| 11 | `set_attribute_value` | Set pop to 0 for the town named a. | Preview with counts, then the value changes. | | |
| 12 | `add_field` | Add a text field note to towns. | Field appears. | | |
| 13 | `rename_field` | Rename the field note to remark. | Field renamed. | | |
| 14 | `delete_field` | Delete the field remark from towns. | Asks first; field removed. | | |
| 15 | `add_feature_from_wkt` | Add a point POINT(1 1) to towns with name z and pop 7. | New feature appears. | | |
| 16 | `create_layer_group` | Create a group Hand test containing towns and roads. | Group in the tree with the layers. | | |
| 17 | `move_layers_to_group` | Move districts into the group Hand test. | Layer moves. | | |
| 18 | `set_group_options` | Hide the group Hand test and collapse it. | Visibility/expansion change. | | |
| 19 | `set_map_view` | Zoom the map to scale 1:2000000 centred on 2,2. | Map view changes (needs the canvas). | | |
| 20 | `set_project_crs` | Set the project CRS to EPSG:3857. | Project CRS changes. | | |
| 21 | `assign_layer_crs` | Assign EPSG:4326 to the layer towns. | Asks first (it does not reproject); CRS assigned. | | |
| 22 | `create_bookmark` | Create a bookmark Test area for the extent of districts. | Bookmark in the Spatial Bookmarks panel. | | |
| 23 | `list_bookmarks` | List my bookmarks. | Shows Test area. | | |
| 24 | `go_to_bookmark` | Go to the bookmark Test area. | Map zooms there (needs the canvas). | | |
| 25 | `set_project_properties` | Set the project title to rc44 hand test and a variable team = qa. | Title and variable visible in Project Properties. | | |
| 26 | `measure_distance` | Measure the distance from 0,0 to 3,4 (EPSG:4326). | Ellipsoidal length in metres and kilometres plus the bearing in degrees. Ask for a closed polygon of 3 points to also get area in square metres and hectares. | | |
| 27 | `find_processing_algorithm` | Is there a processing algorithm for densifying lines? | Lists matching approved algorithms with their parameter names. | | |
| 28 | `raster_calculator` | Calculate dem@1 > 100 as a new layer called high_ground. | New raster with 0/1 values; an unsafe expression (python) is refused. | | |
| 29 | `delineate_watershed` | Delineate the watershed upstream of 2.0, 2.0 using dem. | Basin, longest flow path and outlet layers plus area, stream length, relief figures (needs a real DEM to be meaningful). | | |
| 30 | `web_research` | Search the web for recent reports about flooding in Yemen and give me sources. | A sourced list of results; sources are named, no invented links (network dependent). | | |

## Part 4. Integration checks (do the new and old parts work together?)
These come from the 2026-10-16 integration audit (`docs/INTEGRATION_AUDIT_2026-10-16.md`). They test the seams, not single tools.

| # | Check | Steps | Expect | Result | Notes |
|---|---|---|---|---|---|
| I1 | Undo covers the new MODIFY tools | Run set_layer_filter, set_layer_diagram, set_rule_based_labels, set_layer_elevation, set_layer_temporal one by one, each followed by 'undo the last operation' | Each change is reversed (filter gone, diagram gone, labels back, elevation off, temporal off) | | |
| I2 | Privacy gate sees layers inside SQL | Tag `districts` RESTRICTED (set_layer_sensitivity), turn on the egress gate in Settings, use a cloud provider, then 'create a virtual layer r with SQL SELECT * FROM districts' | The call is blocked or asks to confirm sending protected data; the resulting virtual layer is itself treated as protected | | |
| I3 | Advisory for protected layers | With `towns` tagged RESTRICTED: add a chart from towns to Test Layout; set an atlas on towns; package towns offline | Each result carries a warning naming the layer and level; nothing is blocked | | |
| I4 | Routing of ambiguous wording | Type: 'animate the layer over time' / 'undo the last operation' / 'make a chart of population by district' / 'add an inset locator map to the layout' | Right tool each time (export_temporal_animation_frames / undo_last_operation / generate_chart / create_print_layout or add_overview_map); the chat shows the tool it called | | |
| I5 | Compound request in one message | 'Set up an atlas with one page per district in Test Layout, add a bar chart of the population by district, and export the atlas as a PDF' | The model plans several steps and uses set_layout_atlas, add_layout_chart, export_layout_atlas; ask for confirmation where the tool asks | | |
| I6 | Elevation chain | 'Turn on elevation for the dem, then draw an elevation profile along the road in Test Layout' | set_layer_elevation then add_layout_elevation_profile, no manual fix-ups | | |
| I7 | Look of Processing results | Run grass:r.slope.aspect, gdal:proximity, native:meshrasterize, then grass:r.clump and native:hillshade | The first three open with a colour ramp; r.clump and hillshade stay grey (by design) | | |
| I8 | GRASS freeze behaviour | Run grass:r.sun.incidout or any slow GRASS algorithm on the dem | Result arrives; note how long QGIS is unresponsive (GRASS runs on the GUI thread) | | |
| I9 | Task library | Ask 'Create a map book with an atlas of districts' and 'Produce charts linked to maps' | The planner's suggested steps include the new atlas / chart tools | | |
| I10 | Old tools unaffected | Repeat three things that worked in 1.16.3: 'create layer for Jordan ADM1', 'zoom to the layer districts', 'export towns to CSV' | Same behaviour as before (these are the regression guards) | | |

## Part 5. Processing algorithms (385 new)
Prompts are in `docs/HAND_TEST_rc44_algorithms.csv`, one per algorithm, generated from each algorithm's real inputs. The model should find the algorithm with
`find_processing_algorithm` and run it with `run_allowlisted_processing_algorithm`; a result is a NEW temporary layer, never a file. Do the **priority list** first
(each row is a full test of its family), then work through the CSV; **Skip** whole families you cannot run.

| Family (release) | Rows | What the expected result is |
|---|---|---|
| Geometry (rc42) | 73 | Geometry/feature count changes as named; input unchanged |
| Table (rc42) | 11 | Attributes changed as named; input not edited |
| Analysis (rc42) | 35 | Plausible new layer for the name |
| Expression (rc42) | 5 | Works with a simple expression; file/system functions refused |
| Raster (rc43) | 66 | Temporary raster/table; continuous results get a colour ramp |
| Mixed (rc43) | 35 | New temporary layer from the name |
| GRASS (rc44) | 154 | GRASS session result; SKIP if no GRASS |
| Mesh (rc44) | 6 | Layer/raster from `mesh1` |

**Priority list (about 45 minutes)** - type 'Run <name> (<id>) on <fixture>':

1. [ ] native:densifygeometries (Densify by count) on roads - result: ______ notes: ______
2. [ ] native:smoothgeometry (Smooth) on roads - result: ______ notes: ______
3. [ ] native:polygonstolines on districts - result: ______ notes: ______
4. [ ] native:extractvertices on districts - result: ______ notes: ______
5. [ ] native:deleteduplicategeometries on towns - result: ______ notes: ______
6. [ ] native:retainfields on towns keeping name - result: ______ notes: ______
7. [ ] native:randomextract on towns, 3 features - result: ______ notes: ______
8. [ ] native:extractbyexpression on towns, expression "pop" > 100 - result: ______ notes: ______
9. [ ] native:checkgeometryoverlap on districts - result: ______ notes: ______
10. [ ] gdal:slope on dem - result: ______ notes: ______
11. [ ] gdal:roughness on dem - result: ______ notes: ______
12. [ ] gdal:proximity on dem - result: ______ notes: ______
13. [ ] gdal:fillnodata on dem2 - result: ______ notes: ______
14. [ ] gdal:warpreproject on dem to EPSG:3857 - result: ______ notes: ______
15. [ ] gdal:sieve on dem - result: ______ notes: ______
16. [ ] native:fuzzifyrastergaussianmembership on dem - result: ______ notes: ______
17. [ ] gdal:viewshed on dem from 2,2 - result: ______ notes: ______
18. [ ] native:rescaleraster on dem 0 to 1 - result: ______ notes: ______
19. [ ] native:pixelstopoints on dem - result: ______ notes: ______
20. [ ] native:heatmapkerneldensityestimation on towns - result: ______ notes: ______
21. [ ] native:randompointsinextent over the extent of districts - result: ______ notes: ______
22. [ ] gdal:rasterize on districts field pop - result: ______ notes: ______
23. [ ] grass:r.slope.aspect on dem - result: ______ notes: ______
24. [ ] grass:r.cost on dem with a start point 2,2 - result: ______ notes: ______
25. [ ] grass:r.watershed on dem - result: ______ notes: ______
26. [ ] grass:r.viewshed on dem from 2,2 - result: ______ notes: ______
27. [ ] grass:r.fillnulls on dem2 - result: ______ notes: ______
28. [ ] grass:r.clump on dem - result: ______ notes: ______
29. [ ] grass:r.surf.idw on towns field pop - result: ______ notes: ______
30. [ ] grass:r.sun.incidout on dem - result: ______ notes: ______
31. [ ] grass:r.geomorphon on dem - result: ______ notes: ______
32. [ ] grass:v.buffer on roads 0.2 degrees - result: ______ notes: ______
33. [ ] grass:v.overlay on districts and districts (and operator) - result: ______ notes: ______
34. [ ] grass:v.voronoi on towns - result: ______ notes: ______
35. [ ] grass:v.net.iso on roads with one start point - result: ______ notes: ______
36. [ ] native:exportmeshvertices on mesh1 - result: ______ notes: ______
37. [ ] native:exportmeshedges on mesh1 - result: ______ notes: ______
38. [ ] native:exportmeshfaces on mesh1 - result: ______ notes: ______
39. [ ] native:exportmeshongrid on mesh1 - result: ______ notes: ______
40. [ ] native:meshrasterize on mesh1 - result: ______ notes: ______
41. [ ] native:surfacetopolygon on mesh1 - result: ______ notes: ______

**Known not offered (do not expect these to work):** 12 GRASS algorithms and `native:meshcontours` failed their live run and are not on the list (see the CSV
for what is offered); GRASS algorithms that read/write files, take SQL or expressions, or install extensions were left out on purpose; the 24 PDAL point-cloud algorithms are not offered
(this QGIS build has no PDAL); GPS tools and a 3D map layout item do not exist.

## Part 6. What to send back
1. The filled CSVs (tools + algorithms). 2. For each Fail/Partial: exact prompt, the tool the chat called, the full message, and a screenshot if it is a LOOK problem.
3. A short list of rows where the model picked the wrong tool even though the right one exists (these are routing/description problems, the one thing CI cannot see).
4. QGIS version, OS, which provider/model you used, and whether GRASS/PDAL are installed.
