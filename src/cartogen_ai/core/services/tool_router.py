"""
Semantic Tool Router & Retrieval Engine for Cartogen AI.
Filters top-k relevant tool schemas based on user query keywords and intent matching
to prevent LLM system prompt context overload.
"""

import contextlib
import difflib
import re


# Curated phrase synonyms for tools whose real-world paraphrases don't share
# vocabulary with their name/description -- e.g. "rank the districts by how
# bad the situation is" shares no words with calculate_severity_index's name,
# and only a weak substring hit ("rank"/"ranked") with its description, so it
# scored too low to make the top_k candidate set in measured testing against
# realistic (not the tool's own vocabulary) query phrasing. Kept out of the
# tool descriptions themselves (which are sent to the model on every call
# where the tool is selected) since these are routing-only signals, not
# information the model needs once the tool is actually a candidate.
_TOOL_ALIASES = {
    # M1 (2026-10-14). inspect_canvas_visually is here because the new basemap/web-layer tools mention "map" and pushed it out of the
    # top 40 for "look at the map" (caught by tests/test_qgis_coverage_ratchet.py): a tool that only matched on a description word
    # loses to any newcomer that uses the same word, so the phrases users actually say are pinned.
    "find_processing_algorithm": [
        "which processing algorithm", "processing algorithm", "processing tool for", "is there a tool for", "is there an algorithm",
        "list the processing", "what algorithms", "which algorithm", "available algorithms", "qgis algorithm",
    ],
    "inspect_canvas_visually": [
        "look at the map", "look at the canvas", "see the map", "screenshot of the map", "what does the map look like",
        "inspect the canvas", "check how the map looks", "view the canvas",
    ],
    "create_empty_layer": [
        "empty layer", "new empty layer", "blank layer", "new layer with fields", "create a new layer", "create a scratch layer",
        "scratch layer", "temporary layer", "new geopackage layer", "new shapefile", "layer to digitize", "layer to digitise",
        "empty polygon layer", "empty point layer", "empty line layer", "new table",
    ],
    "create_layer_group": [
        "create a group", "new group", "make a group", "create a layer group", "group the layers", "put the layers in a group",
        "put these layers in a group", "layer group",
    ],
    "move_layers_to_group": ["move the layer into the group", "move layers into the group", "add the layer to the group", "move to the group"],
    "set_group_options": [
        "hide the group", "show the group", "collapse the group", "expand the group", "turn off the group", "turn on the group",
        "mutually exclusive", "check the whole group", "uncheck the group",
    ],
    "set_map_view": [
        "zoom to scale", "set the scale", "scale of 1:", "zoom to 1:", "to 1:", "rotate the map", "map rotation", "pan to", "pan the map",
        "centre the map", "center the map", "zoom to the extent", "zoom to coordinates", "zoom to this extent",
    ],
    "set_project_crs": [
        "set the project crs", "project crs", "change the project crs", "set the map crs", "change the map projection", "project projection",
        "set the project projection",
    ],
    "assign_layer_crs": [
        "assign projection", "assign the crs", "assign crs", "layer has no crs", "wrong crs on the layer", "set the layer crs",
        "set the crs of the layer", "define the crs",
    ],
    "create_bookmark": ["create a bookmark", "add a bookmark", "save a bookmark", "bookmark this", "bookmark the view", "new bookmark", "save this view"],
    "list_bookmarks": ["list the bookmarks", "list bookmarks", "show the bookmarks", "my bookmarks", "what bookmarks"],
    "go_to_bookmark": ["go to the bookmark", "go to bookmark", "zoom to the bookmark", "jump to the bookmark", "open the bookmark"],
    "set_project_properties": [
        "project title", "set the project title", "rename the project", "project variable", "set a project variable", "project properties",
    ],
    "measure_distance": [
        "measure the distance", "measure distance", "how far is", "distance between", "measure the length", "measure the area",
        "bearing between", "measure between", "what is the distance",
    ],
    "select_by_expression": [
        "select by expression", "select with an expression", "select where", "select all features where", "select the features where",
        "add to the selection", "remove from the selection", "narrow the selection", "select features with",
    ],
    "select_all_features": ["select all features", "select everything", "select all the features", "select all records"],
    "clear_selection": [
        "clear the selection", "clear selection", "deselect", "unselect", "remove the selection", "clear all selections", "select nothing",
    ],
    "delete_features": [
        "delete the selected", "delete features", "delete the features", "delete the selected features", "remove the selected features",
        "delete all features where", "delete the records", "delete the rows", "delete the polygons where", "delete the points where",
    ],
    "set_attribute_value": [
        "change the value", "set the value", "edit the value", "update the value", "set the field", "change the attribute",
        "edit the attribute", "change the population of", "set its", "update the attribute", "fill the field",
    ],
    "add_field": ["add a field", "add a column", "add a new field", "new column", "add an attribute field", "add a new column", "add field"],
    "rename_field": ["rename the field", "rename the column", "rename field", "rename column", "rename the attribute"],
    "delete_field": [
        "delete the field", "delete the column", "drop the field", "drop the column", "remove the field", "remove the column", "delete field",
        "delete column",
    ],
    "add_feature_from_wkt": [
        "add a feature", "add a new feature", "add this wkt", "from wkt", "add the geometry", "add a polygon to", "add a line to",
        "add a point to the layer", "wkt",
    ],
    "set_layer_filter": [
        "definition query", "set a filter on", "set the filter on", "layer filter", "set the layer filter", "clear the filter",
        "remove the filter", "clear the layer filter", "provider filter", "subset string",
    ],
    "transform_features": [
        "move the features", "move the selected features", "shift the features", "rotate the selected", "rotate the features by",
        "scale the features", "scale the selected", "enlarge the features", "shrink the features", "nudge the features",
    ],
    "merge_features": [
        "merge the selected features", "merge the features", "merge these features", "union the selected", "combine the selected features",
        "merge features into one", "merge the two features", "merge the selected polygons",
    ],
    "split_features_by_line": [
        "split the polygon", "split the feature", "split the features", "split the selected", "cut the polygon", "cut the feature",
        "split features by a line", "split along a line", "split the parcel",
    ],
    "undo_manual_edit": ["undo my edit", "undo the last edit", "undo my last edit", "undo the manual edit", "undo edit"],
    "redo_manual_edit": ["redo the edit", "redo my edit", "redo the last edit", "redo the manual edit", "redo edit"],
    "change_field_type": [
        "change the field type", "change the type of the field", "change the data type", "convert the field to", "convert the column to",
        "change the column type", "make the field an integer", "make the field a number", "make the field a text",
    ],
    "set_layer_editing": [
        "start editing", "toggle editing", "stop editing", "save the edits", "save my edits", "save layer edits", "discard the edits",
        "discard my edits", "discard the changes", "enter edit mode", "leave edit mode",
    ],
    "find_broken_layers": [
        "broken layer", "broken layers", "broken path", "broken paths", "missing layer", "layer not found", "layers with a red",
        "unavailable layer", "fix the paths", "data source is missing", "lost layer", "moved the file",
    ],
    "repair_layer_source": [
        "repair the layer", "repair layer", "fix the broken", "relink", "re-link", "point the layer to", "change the data source",
        "change the source", "set data source", "resolve the missing", "find the moved",
    ],
    "save_layer_as": [
        "save as", "save the layer as", "save layer as", "save it in epsg", "save with only", "save only the selected",
        "export in another crs", "export with only the fields", "save in a different crs", "export to a different projection",
        "keep only the fields", "export only the fields",
    ],
    "add_basemap": [
        "basemap", "base map", "background map", "add openstreetmap", "add osm", "satellite imagery background",
        "satellite basemap", "add a satellite", "open street map", "topographic background", "carto light", "carto dark",
    ],
    "add_web_layer": [
        "wms", "wmts", "wfs", "xyz tile", "tile layer", "web service", "web map service", "arcgis rest", "arcgis feature",
        "featureserver", "mapserver", "add a service", "tile url", "getcapabilities",
    ],
    "calculate_severity_index": [
        "worst", "priority", "rank the districts", "how bad", "most affected",
        "needs index", "prioritize",
    ],
    "calculate_presence_gap": [
        "underserved", "understaffed", "under-resourced", "who's helping",
        "who is helping", "operational gap", "coverage gap",
    ],
    "load_3w_data": [
        "who else is working", "who is working", "3w", "4w",
        "operational presence", "who's active", "who's responding",
        "who is active", "who is responding", "which organizations are present",
        "which organisations are present",
    ],
    "generate_html_dashboard": [
        "interactive map", "send to donors", "share with", "web map",
        "donor briefing", "for stakeholders",
    ],
    "analyze_incident_trend": [
        "getting worse", "getting more dangerous", "more dangerous", "worsening",
        "improving", "increasing risk", "escalating", "on the rise",
    ],
    "score_route_incident_risk": [
        "risky", "dangerous route", "safe route", "route safety", "safe to travel",
        "safe to drive",
    ],
    "calculate_ndvi": [
        "vegetation", "vegetation health", "how green", "greenness", "crop health",
        "plant health", "vegetation index",
    ],
    "calculate_ndwi": [
        "surface water", "how much water", "water extent", "is there flooding",
        "flood mapping", "water index",
    ],
    "calculate_ndre": [
        "chlorophyll", "nitrogen stress", "crop nitrogen", "precision agriculture",
        "precision ag",
    ],
    "calculate_raster_change_detection": [
        "before and after", "compare images", "what changed", "how much damage",
        "damage from before to after", "satellite comparison",
    ],
    # Real live report, 2026-09-16: a "Health facilities beyond one hour's travel <coords>"
    # request -- no place names in the query, no facility layer already in the project --
    # spent its whole tool-call budget on execute_pyqgis_script hunting for a local data file
    # on disk and probing the plugin's own internals, never once calling geocode_and_enrich/
    # geocode_batch, even though an earlier turn with the same underlying task DID use them
    # successfully. Root cause not fully instrumented (which tools were actually in that turn's
    # active_tools isn't logged), but is strongly implicated by the scoring itself: neither
    # tool's own description ("Geocode a SINGLE address/place name into lat/lon...") shares any
    # vocabulary with "health facilities beyond one hour's travel", so with no query text to
    # match on, both tools score at or near 0 against a name query -- an easy loss against ~175
    # other registered tools within a top_k=40 cutoff, especially since "health"/"facilit*" /
    # "travel"/"hour" naturally score highly for several OTHER, unrelated tools instead. These
    # aliases give both geocode tools a fighting chance of being visible on exactly the kind of
    # query that most needs them: naming real-world facilities (hospitals, clinics) with no
    # existing coordinate data to start from.
    # rc40 hand test OI-80: "which facilities are beyond N hours by road" ran travel_time_matrix and never produced the green/red
    # access layer, because nothing in the request pointed at classify_facilities_by_access. Phrases only; no bare "beyond"/"within".
    "classify_facilities_by_access": [
        "beyond one hour", "beyond an hour", "beyond 1 hour", "beyond 30 minutes", "by road", "outside the service area",
        "within reach of", "out of reach", "cannot be reached within", "not reachable within",
    ],
    # rc41 hand test: "create layer for Jordan ADM1" selected neither boundary tool (no shared words), so the model said no boundary fetcher was
    # "active in this tool configuration" without trying. ADM codes and the usual names for the levels are the way people ask for these.
    "fetch_geoboundaries": [
        "adm0", "adm1", "adm2", "adm3", "adm4", "adm5", "admin boundar", "administrative boundar", "admin level",
        "governorate", "province boundar", "district boundar", "region boundar", "country boundar", "state boundar",
    ],
    "fetch_hdx_admin_boundaries": [
        "adm0", "adm1", "adm2", "adm3", "adm4", "adm5", "admin boundar", "administrative boundar", "admin level",
        "governorate", "province boundar", "district boundar", "p-code", "pcode", "cod-ab",
    ],
    # QGIS vocabulary audit 2026-10-14 (91 plain menu-style phrases): these were not offered. The Processing tool covers the algorithms in
    # _processing_allowlist.py; phrases are the names users know from the Processing toolbox and the Vector/Raster menus.
    "run_allowlisted_processing_algorithm": [
        # M6a geometry family: the algorithm's own name, so a plain request reaches the generic tool (tests/test_processing_allowlist_routing.py)
        'add geometry attributes', 'affine transform', 'approximate medial axis', 'bounding box of each', 'bounding boxes', 'check validity', 'collect geometries', 'concave hull', 'convert geometry type', 'convert to curved geometries', 'convert to multipart', 'create wedge buffers', 'delete holes', 'delete the holes', 'densify', 'densify by count', 'densify by interval', 'dissolve coverage', 'drop m z values', 'explode lines', 'explode the lines', 'extend lines', 'extract clip by extent', 'extract vertices', 'extrude', 'fill gaps between polygons', 'fill the holes', 'filter vertices by m value', 'filter vertices by z value', 'force polygons', 'force polygons clockwise', 'force polygons counter clockwise', 'force right hand rule', 'geodesic line split at antimeridian', 'interpolate point on line', 'keep n biggest parts', 'line substring', 'lines to polygons', 'merge lines', 'minimum bounding', 'minimum bounding geometry', 'minimum enclosing circles', 'multi ring buffer', 'offset lines', 'offset the lines', 'oriented bounding box', 'oriented minimum bounding box', 'orthogonalize', 'point on surface', 'points along', 'points along geometry', 'points displacement', 'pole of inaccessibility', 'polygonize', 'polygons to lines', 'project points', 'promote to multi', 'promote to multipart', 'rectangles ovals diamonds', 'remove duplicate vertices', 'remove null geometries', 'remove parts by area', 'remove parts by length', 'reverse line', 'reverse line direction', 'reverse the line', 'right hand rule', 'rotate the features', 'roundness', 'segmentize', 'segmentize by maximum angle', 'segmentize by maximum distance', 'set m value', 'set z value', 'simplify coverage', 'single sided buffer', 'smooth the geometr', 'smooth the line', 'smooth the polygon', 'snap geometries to layer', 'snap points to grid', 'snap the points to', 'split lines by maximum length', 'split with lines', 'subdivide the', 'swap x and y', 'swap x and y coordinates', 'tapered buffer', 'tapered buffers', 'boundary of the polygon', 'boundary of each polygon', 'outline of the polygons as lines', 'translate the', 'validate coverage', 'variable width buffer', 'wedge buffer',
        'delete duplicate geometries', 'drop geometries', 'drop the geometries', 'extract within distance', 'filter by geometry type', 'drop field', 'drop the field', 'retain fields', 'delete duplicates by attribute', 'random extract', 'random extract within subsets', 'join attributes by location summary', 'detect dataset changes', 'detect vector changes',
        'array of translated features', 'array of offset', 'check geometry', 'check the geometry', 'geometry check', 'small angles', 'small polygons', 'dangle end', 'degenerate polygons', 'duplicated geometries', 'duplicated vertices', 'polygons exceeding boundaries', 'lines intersecting', 'missing vertices along borders', 'strictly multipart', 'sliver polygons', 'small segments', 'self contacts', 'self intersections', 'climb along line', 'distance matrix', 'distance to nearest hub', 'create layer from extent', 'create layer from point', 'join by lines', 'hub lines', 'mean coordinate', 'shortest line between features', 'text to float', 'topological coloring', 'random points in polygons', 'random points on lines', 'random points along line', 'random points in layer bounds',
        'extract by expression', 'geometry by expression', 'order by expression', 'add autoincremental field', 'random points inside polygons', 'autoincrement',
        "symmetrical difference", "symmetric difference", "k-means", "kmeans", "k means cluster", "dbscan", "reclassify", "reclassification",
        "sample raster", "raster sampling", "raster values at", "join by nearest", "join attributes by location", "count points in polygon", "count points in each", "points per polygon", "points in each polygon",
        "cell statistics", "tin interpolation", "idw", "statistics by categories", "pansharp", "shortest path", "extract by location",
        "create grid", "create a grid", "make a grid", "fishnet", "regular grid", "native:", "gdal:", "qgis:", "processing algorithm", "processing toolbox",
    ],
    "hotspot_analysis": ["dbscan", "density clusters", "clusters of incidents", "hot spots"],
    "get_feature_count": ["how many features", "feature count", "count the features", "number of features", "how many records", "how many rows"],
    # QGIS-vocabulary audit 2026-10-14 (docs/QGIS_COVERAGE_GAP_ANALYSIS_2026-10-14.md): the foundation tools had NO alias at all and were found
    # only through accidental word overlap with their names and descriptions, which is what broke in rc23. Plain phrases, as people say them.
    'add_layer_from_path': [
        'add the shapefile', 'add a shapefile', 'add the geopackage', 'import the gpx', 'import the kml', 'import the geojson', 'import the file', 'import the shapefile', 'open the file', 'load the file', 'open the shapefile', 'load the shapefile', 'add the raster', 'load the raster', 'add the dem', 'open the geotiff', 'load the geojson', 'add the geojson', 'add the gpx', 'add the kml', 'add this file', 'load this file', '.shp', '.gpkg', '.geojson', '.tif', '.kml', '.gpx', 'from this url', 'from the url', 'download link', 'create layer for', 'add a layer', 'add layer', 'load a layer', 'load layer', 'open a layer', 'zipped shapefile', 'zip file', 'zipped file', 'open the zip', 'load the zip', '.zip', '.kmz', 'kmz file', 'table from the geopackage', 'table of the geopackage', 'layer from the geopackage', 'layer inside the geopackage', 'one layer of the file',
    ],
    'select_by_attribute': [
        'select the features named', 'select features named', 'select the district named', 'select by name', 'select by attribute', 'select the feature with', 'select the districts named',
    ],
    'highlight_features': [
        'select by expression', 'select features where', 'select the features where', 'select all features where', 'select where', 'districts where', 'points where', 'roads where', 'features where', 'records where', ' is over ', ' is greater than ', ' is less than ', ' is more than ', ' is above ', ' is below ', 'highlight the features', 'highlight features',
    ],
    'run_query': [
        'filter the layer', 'filter layer', 'filter by expression', 'show only the features', 'show only features', 'only the features where', 'subset of the layer',
    ],
    'field_calculator': [
        'calculate a field', 'calculate the field', 'add a field', 'new field', 'field calculator', 'update the field', 'fill the field', 'set the field', 'calculate a new field', 'with an expression', 'using an expression', 'from an expression', 'compute a field', 'add a column', 'new column',
    ],
    'field_statistics': [
        'statistics of the', 'statistics for the', 'summary statistics', 'basic statistics', 'mean of the', 'average of the', 'sum of the', 'minimum of', 'maximum of', 'unique values', 'how many unique', 'min and max',
    ],
    'get_attributes': [
        'list the fields', 'what fields', 'show the fields', 'field names', 'column names', 'list the columns', 'which columns', 'what attributes', 'list the attributes',
    ],
    'open_attribute_table': [
        'open the attribute table', 'show the attribute table', 'attribute table of', 'open the table',
    ],
    'zoom_to_layer': [
        'zoom to the layer', 'zoom to layer', 'zoom to the extent of', 'zoom in on the layer', 'show me the layer', 'center the map on the layer', 'fit the map to', 'zoom to all',
    ],
    'zoom_to_feature': [
        'zoom to the feature', 'zoom to feature', 'zoom to the district', 'zoom to the selected', 'zoom to selection', 'zoom to the selection', 'zoom to where', 'zoom to the city of',
    ],
    'remove_layer': [
        'remove the layer', 'delete the layer', 'remove layer', 'delete layer', 'drop the layer', 'get rid of the layer', 'take the layer off', 'close the layer',
    ],
    'rename_layer': [
        'rename the layer', 'rename layer', 'change the name of the layer', 'call the layer', 'name the layer',
    ],
    'toggle_visibility': [
        'hide the layer', 'show the layer', 'turn off the layer', 'turn on the layer', 'make the layer visible', 'make the layer invisible', 'switch off the layer', 'switch on the layer', 'untick the layer', 'tick the layer', 'hide it', 'unhide',
    ],
    'set_layer_order': [
        'move the layer to the top', 'move the layer to the bottom', 'bring the layer to the front', 'send the layer to the back', 'layer order', 'draw order', 'put the layer above', 'put the layer below', 'move the layer', 'move layer', 'put the layer', 'move the layer above', 'move the layer below', 'reorder the layers', 'stacking order',
    ],
    'export_layer': [
        'export the layer', 'export layer', 'save the layer as', 'save layer as', 'save as shapefile', 'save as geojson', 'save as geopackage', 'export to shapefile', 'export to geojson', 'export to geopackage', 'export to gpkg', 'export to kml', 'export the selected', 'export only the selected', 'write the layer to a file',
    ],
    'export_to_csv': [
        'export to csv', 'export the table', 'save as csv', 'save to csv', 'export the attribute table', 'write a csv', 'as a csv file',
    ],
    'reproject_layer': [
        'reproject', 're-project', 'change the projection', 'transform the layer to', 'convert the layer to epsg', 'to utm', 'to epsg', 'change the crs of the layer to', 'convert to utm',
    ],
    'clip_layer': [
        'clip the', 'clip layer', 'cut the layer to', 'crop the layer', 'clip to the boundary', 'clip by the boundary',
    ],
    'merge_layers': [
        'merge the', 'merge layers', 'merge these layers', 'combine the layers', 'combine layers', 'append the layers', 'put the layers together',
    ],
    'dissolve_layer': [
        'dissolve', 'merge the polygons by', 'aggregate the polygons', 'combine the polygons by',
    ],
    'union_layers': [
        'union of', 'union the', 'overlay union',
    ],
    'intersect_layers': [
        'intersect the', 'intersection of', 'where the two layers overlap', 'overlap of the', 'common area of',
    ],
    'difference_layers': [
        'difference of', 'difference between the layers', 'erase the', 'cut out the', 'subtract the', 'everything outside',
    ],
    'buffer_analysis': [
        'buffer', 'buffers', 'distance around', 'within a distance of', 'area around', 'zone around', 'radius around', 'ring around',
    ],
    'centroid': [
        'centroid', 'centroids', 'center point of', 'centre point of', 'middle point of',
    ],
    'convex_hull': [
        'convex hull', 'smallest polygon around', 'outline around the points', 'hull of the',
    ],
    'simplify_geometry': [
        'simplify', 'generalize', 'generalise', 'reduce the vertices', 'reduce the number of vertices', 'reduce detail',
    ],
    'fix_geometries': [
        'fix geometries', 'fix invalid', 'repair the geometries', 'repair invalid', 'invalid geometries', 'make the geometries valid', 'fix the geometry errors',
    ],
    'join_by_attribute': [
        'join the table', 'join a table', 'join the csv', 'join by field', 'join by attribute', 'attribute join', 'join on the', 'join the spreadsheet', 'add the columns from', 'table join',
    ],
    'spatial_join': [
        'spatial join', 'join by location', 'join based on location', 'join the attributes by location', 'which polygon each point', 'assign the district to each', 'tag each point with',
    ],
    'select_by_location': [
        'select by location', 'select the points inside', 'select points inside', 'select features inside', 'select features within', 'select the features within', 'select the features that intersect', 'select features that intersect', 'select the ones inside', 'intersecting the',
    ],
    'invert_selection': [
        'invert the selection', 'invert selection', 'reverse the selection', 'select the opposite', 'select everything else', 'select the rest',
    ],
    'save_project': [
        'save the project', 'save project', 'save my work', 'save the map project',
    ],
    'load_project': [
        'open the project', 'load the project', 'open project', 'open a project', 'open the qgz', 'open the qgs', 'load the qgz',
    ],
    'get_crs': [
        'what crs', 'which crs', 'what is the crs', 'what projection', 'which projection', 'what coordinate system', 'which coordinate system', 'crs of the layer',
    ],
    'find_tools': [
        'which tool', 'what tool', 'is there a tool', 'is there a way to', 'what can you do', 'list the tools', 'what tools',
    ],
    'get_turn_transaction_log': [
        'what did you change', 'what have you changed', 'what did you do', 'what have you done', 'show the history', 'processing history', 'show the log of changes', 'list the changes you made', 'history of changes',
    ],
    'undo_last_operation': [
        'undo', 'undo the last', 'revert the last', 'take that back', 'roll back', 'go back to before', 'undo that', 'undo what you just did',
    ],
    "geocode_and_enrich": [
        "hospital", "hospitals", "clinic", "clinics", "health facilit",
        "geocode", "find the location of", "where is",
    ],
    "geocode_batch": [
        "hospital", "hospitals", "clinic", "clinics", "health facilit",
        "geocode", "list of locations", "multiple locations",
    ],
    "ingest_osm_features": [
        "hospital", "hospitals", "clinic", "clinics", "health facilit",
        "health facilities", "doctors", "pharmacy", "osm data",
        "download facilities", "fetch facilities", "osm features",
        "infrastructure", "schools", "road network", "highways",
        "osm", "amenities", "amenity",
    ],
    # Hydrology (see tools/engineering_tools.py). "steam length" is the typo in the request that motivated these tools. No bare
    # "tc" alias: aliases match as substrings of the query, so it would boost these tools on "match", "batch" or "catchment".
    "parse_dms_location": [
        "degrees minutes seconds", "dms coordinate", "watershed outlet",
        "watershed area", "stream length", "steam length", "peak flow",
    ],
    "assess_watershed_hydrology_request": [
        "watershed", "catchment", "drainage basin", "stream length", "steam length",
        "return period", "rainfall intensity", "time of concentration", "peak flow",
    ],
    "calculate_rational_watershed_peak_flow": [
        "watershed", "catchment", "rational method", "return period",
        "rainfall intensity", "time of concentration", "peak flow", "kirpich",
    ],
    # Road barriers (see tools/barrier_tools.py). No bare "bridge" or "closed": they would boost this tool on unrelated queries.
    "apply_network_barriers": [
        "destroyed bridge", "damaged bridge", "blocked road", "road closure", "closed road", "flooded road",
        "checkpoint", "barrier", "impassable", "avoid the", "cut off road",
    ],
    # Anticipatory action (see tools/trigger_tools.py). No bare "forecast" or "trigger": forecast_trend and unrelated queries use them.
    "evaluate_forecast_trigger": [
        "anticipatory action", "forecast-based financing", "forecast based financing", "trigger threshold", "trigger model",
        "trigger protocol", "activation threshold", "lead time", "early action", "pre-arranged financing",
    ],
    # Remote mapping tasks (see tools/task_grid_tools.py). No bare "grid" or "tasks": they appear in unrelated requests.
    "generate_mapping_task_grid": [
        "tasking manager", "mapping task", "task grid", "mapswipe", "remote mapping", "crowd mapping", "mapathon",
        "split the area into", "divide the area into",
    ],
    # Survey sampling (see tools/sampling_tools.py). No bare "sample" or "survey": they appear in unrelated requests.
    "design_sampling_frame": [
        "sampling frame", "sample size", "stratified sample", "sampling design", "household survey", "needs assessment",
        "msna", "enumerator", "margin of error", "cluster sampling", "random sample of households",
    ],
    # Multi-criteria ranking and survey aggregation (see tools/mcda_tools.py, tools/survey_tools.py). No bare "rank", "weights" or "survey".
    "calculate_mcda_ranking": [
        "multi-criteria", "multicriteria", "mcda", "weighted ranking", "rank the districts", "rank districts", "prioritise areas",
        "prioritize areas", "prioritisation", "prioritization", "weight sensitivity", "rank stability",
    ],
    "calculate_allocation_envelope": [
        "allocation envelope", "split the budget", "allocate the budget", "divide the budget", "distribute the budget", "budget across districts",
        "budget by severity", "funding envelope", "share the funding", "allocate funding",
    ],
    "import_jiaf_inputs": [
        "jiaf input", "jiaf inputs", "import jiaf", "load the jiaf", "sector pin file", "sectoral pin", "jiaf worksheet", "hno dataset",
        "people in need by sector", "sector inputs",
    ],
    "compute_jiaf_preliminary": [
        "preliminary joint pin", "preliminary pin", "mosaic method", "joint overall pin", "preliminary intersectoral severity", "jiaf flags",
        "pin flags", "highest sectoral pin", "compute the jiaf", "jiaf preliminary",
    ],
    "record_jiaf_decisions": ["record the jiaf decision", "jiaf decisions", "final pin decision", "agreed severity", "flagged unit decision", "which sector pin"],
    "get_jiaf_decisions": ["show the jiaf decisions", "stored jiaf decisions"],
    "finalize_jiaf_results": ["final pin", "final joint overall pin", "finalize the jiaf", "finalise the jiaf", "jiaf final results", "pending flagged units"],
    "compute_jiaf_patterns": ["jiaf patterns", "intersectoral patterns", "workspace 3c", "pin correlation between sectors", "sectors driving the needs",
                              "needs patterns and linkages"],
    "record_jiaf_setup": ["jiaf set-up", "jiaf setup", "record the jiaf", "sector alignment", "jiaf scope", "manual edition"],
    "get_jiaf_setup": ["show the jiaf set-up", "jiaf setup record", "what jiaf scope"],
    "analyze_critical_links": [
        "critical link", "critical links", "bottleneck", "bottlenecks", "single point of failure", "which roads matter most",
        "which road is most important", "roads the routes depend on", "route dependence",
    ],
    "import_humanitarian_table": [
        "import ipc", "ipc table", "ipc phase file", "ipc classification file", "import inform", "inform risk table", "inform risk file",
        "unosat damage", "unosat points", "import the damage points", "load the ipc", "load the inform",
    ],
    "apply_humanitarian_look": [
        "show the severity on the map", "map the severity", "style the severity", "colour by severity", "color by severity",
        "map the people in need", "show people in need on the map", "map the gap", "style the presence gap", "map the ranking",
        "style the ranking", "show the rank on the map",
        "show the jiaf severity", "map the jiaf", "jiaf on the map", "map the severity phases", "which districts still need a decision",
        "which units are pending", "where the group still has to decide", "map the pending", "colour the phases", "color the phases",
        "highlight the worst", "show the worst", "areas that need help most", "where help is needed most", "most in need on the map",
    ],
    "aggregate_survey_indicator": [
        "survey results by", "survey indicator", "weighted survey", "survey weights", "household survey results", "proportion of households",
        "share of households", "percentage of households",
    ],
    "population_access_gap": [
        "cash assistance", "voucher assistance", "cash and voucher", "cva feasib",
        "cva viable",
    ],
    "raster_calculator": [
        "raster calculator", "raster calc", "map algebra", "band math", "raster expression", "raster minus", "minus raster",
        "subtract the raster", "subtract raster", "add the rasters", "multiply the raster", "divide the raster", "raster where",
        "cells above", "cells below", "cells where", "pixels above", "pixels below", "mask of cells", "threshold the raster",
        "raster threshold", "combine the rasters", "raster a minus", "difference between the two rasters",
    ],
    "add_layout_item": [
        "add a picture to the layout", "add a logo to the layout", "add an image to the layout", "add a logo to the map", "add a text box",
        "add a label to the layout", "add a shape to the layout", "add a rectangle to the layout", "add an arrow", "add a table to the layout",
        "add an attribute table", "put a logo", "insert a picture", "insert a logo", "layout item",
    ],
    "edit_layout_item": [
        "move the legend", "move the scale bar", "move the north arrow", "move the title", "resize the legend", "resize the map",
        "make the map bigger", "make the map smaller", "rotate the item", "remove the item from the layout", "delete the item from the layout",
        "remove the legend", "remove the north arrow", "remove the scale bar",
    ],
    "set_layout_map": [
        "set the map scale", "scale of the layout map", "layout map scale", "zoom the layout map", "layout extent", "change the map extent in the layout",
        "rotate the layout map", "lock the layers", "freeze the layers", "map in the layout to", "layout to 1:",
    ],
    "set_layout_page": [
        "page size", "change the page size", "paper size", "a3 page", "a4 page", "a5 page", "a2 page", "a1 page", "a0 page", "letter page",
        "portrait layout", "landscape layout", "add a page", "second page", "two pages", "several pages", "multi-page",
    ],
    "save_layout_template": [
        "save the layout as a template", "save layout template", "layout template", "save as a template", "export the template", ".qpt",
    ],
    "load_layout_template": [
        "load a layout template", "load the template", "new layout from a template", "open the template", "layout from a template", "use the template",
    ],
    "export_layout": [
        "export the layout", "export layout", "export the layout as svg", "layout to svg", "save the layout as pdf", "save the layout as png",
        "export the existing layout", "export layout to",
    ],
    "set_layer_symbol": [
        "outline color", "outline colour", "outline width", "outline thickness", "thicker outline", "thinner outline", "thin outline",
        "thick outline", "dashed outline", "dashed line", "dotted line", "dotted outline", "line pattern", "line style", "stroke width",
        "stroke colour", "stroke color", "marker shape", "marker size", "symbol size", "bigger symbols", "smaller symbols", "star marker",
        "square marker", "triangle marker", "diamond marker", "hatch", "hatched", "hatching", "fill pattern", "no fill", "hollow polygons",
        "outline only", "symbol outline",
    ],
    "set_label_style": [
        "label color", "label colour", "label size", "bigger labels", "smaller labels", "bold labels", "italic labels", "label halo",
        "halo around", "label buffer", "label placement", "labels only when zoomed", "hide the labels", "show the labels", "turn off labels",
        "turn on labels", "label font", "labels in bold",
    ],
    "set_raster_style": [
        "unique values", "one color per value", "one colour per value", "class colors", "class colours", "paletted", "categorical raster",
        "land cover colors", "land cover colours", "nodata", "no data", "no-data", "make zeros transparent", "resampling", "smooth the raster",
        "blocky cells", "pixelated", "bilinear", "raster opacity", "raster transparency",
    ],
    "apply_raster_stretch": [
        "raster looks washed out", "raster looks flat", "fix the raster colors",
        "raster color ramp", "raster contrast", "stretch the raster",
        "raster looks grey", "raster looks gray", "colorize the raster",
        # Long-request audit 2026-10-14: "style the result with a green to red colour ramp" offered only the vector style tools.
        "colour ramp", "color ramp", "colour scheme", "color scheme", "green to red", "red to green", "blue to red", "style the raster",
        "style the dem", "style the slope", "style the result with", "pseudocolor", "contrast stretch", "raster colours", "raster colors",
        "population ramp",
    ],
    # Added 2026-09-13, live user report: "show live incedent in jordan... natural, crime,
    # haszard" -- fetch_gdacs_disaster_alerts scored zero relevance for this phrasing (its
    # description names specific hazard TYPES -- earthquakes, floods, wildfires -- but never
    # the generic words "disaster"/"hazard"/"incident" a real user reaches for first). The
    # single-word "hazard"/"disaster"/"incident"/"wildfire" entries below exist specifically so
    # _expand_query_with_fuzzy_corrections() (see its docstring) has something to land a
    # corrected "haszard"->"hazard" or "incedent"->"incident" on -- bare-substring matching
    # alone still can't see a misspelled word, but the fuzzy-correction pass runs before this
    # check and appends the corrected form to the string these aliases are matched against.
    # rule 48 (prompts.py) is the complementary fix for when the tool IS already a candidate
    # but the model doesn't know to reach for it.
    "fetch_gdacs_disaster_alerts": [
        "disaster alert", "current disaster", "live disaster", "ongoing disaster",
        "disaster incident", "hazard alert", "what disasters", "natural disaster",
        "hazard", "disaster", "emergency",
    ],
    "fetch_nasa_eonet_events": [
        "natural event", "live event", "current event", "live hazard",
        "current hazard", "natural incident", "live incident", "ongoing hazard",
        "what hazards", "hazard incident", "hazard", "incident",
    ],
    "fetch_usgs_earthquakes": [
        "earthquake", "quake", "seismic", "magnitude", "tremor", "aftershock", "usgs",
    ],
    "find_incident_reports": [
        "incident", "incidents", "incident report", "what happened", "security situation", "recent events", "reliable source",
        "check the internet", "latest news", "disaster and conflict", "hazards and conflict", "situation in",
        "incidents from the news", "from the news", "news incidents", "major incidents", "incidents in the news", "news reports", "reported in the news",
        "list the incidents", "incidents on the map", "put the incidents on the map",
    ],
    "fetch_dem": [
        "dem", "elevation data", "download elevation", "download the dem", "terrain data", "get the dem", "watershed", "catchment", "peak flow",
        "stream length", "time of concentration",
    ],
    "delineate_watershed": [
        "watershed", "catchment", "drainage basin", "basin area", "delineate the basin", "flow path", "stream length", "time of concentration", "peak flow",
        "peak discharge", "tc ", "rational method", "return period", "pour point", "upstream area", "contributing area",
    ],
    "web_research": [
        "from the internet", "search the internet", "search the web", "search online", "look up online", "look it up", "find information about",
        "find the information", "give me the source", "provide the source", "provide me with the source", "cite the source", "with sources",
        "with the source", "source of the information", "what are the latest news", "latest news about", "news about", "search the news",
        "check the internet", "on the internet", "online sources", "google",
    ],
    "search_fact_checks": [
        "fact check", "fact-check", "fact checked", "debunk", "debunked", "is this true", "is it true", "really from", "old video", "old footage",
        "fake news", "misinformation", "disinformation", "hoax", "rumour", "rumor", "verify this", "verify the video", "verify the claim",
        "فتبينوا", "تحقق من",
    ],
    "fetch_ucdp_conflict_events": [
        "conflict event", "armed conflict", "political violence", "organised violence", "organized violence", "ucdp",
        "fatalities", "battle", "killed in", "violence against civilians", "conflict", "war",
    ],
    "fetch_nasa_active_fires": [
        "active fire", "live fire", "fire detection", "current wildfire",
        "wildfire location", "fire alert", "wildfire",
    ],
    # Plain-language styling requests share no words with the style tools' names ("make the clinics stand out",
    # "colour the districts by how many people live there"); measured before this entry: several got no style tool at all.
    "get_layer_extent": [
        "extent", "bounding box", "bbox", "wgs84", "in degrees", "lat/lon", "search_stac_satellite_imagery", "fetch_building_footprints",
        "fetch_osm_features", "fetch_worldpop_population", "sentinel", "satellite scenes", "building footprints", "inside it",
    ],
    "apply_graduated_style": [
        "colour the districts by", "color the districts by", "shade the districts", "darker where", "darker the more",
        "colour by how many", "color by how many", "from light to dark", "light to dark", "darker for higher",
        "show how much", "show how many",
    ],
    "apply_graduated_symbol_style": [
        "bigger dots", "bigger circles", "larger dots", "larger circles", "bigger the more", "size by", "scale the dots",
        "scale the circles", "dot size", "bigger symbols",
    ],
    "apply_heatmap_style": [
        "crowded", "crowding", "where people are concentrated", "where most", "concentrated", "density map", "hot spots",
        "hotspots", "busy areas", "clusters of",
    ],
    "apply_categorized_style": [
        "different colour for each", "different color for each", "each type in its own colour", "each type in its own color",
        "colour by type", "color by type", "colour each", "color each", "separate colours", "separate colors",
        "categorize the layer", "categorise the layer", "categorized style", "categorised style", "unique values",
    ],
    "change_layer_color": [
        "make it red", "make them red", "in red", "in blue", "in green", "in dark", "in light", "in pale", "make it stand out",
        "make them stand out", "stand out", "change the colour", "change the color", "recolour", "recolor",
    ],
    "apply_labels": [
        "put the names", "show the names", "names on the map", "write the names", "name next to", "label each",
        "show the name of each",
    ],
    "set_layer_transparency": [
        "see-through", "see through", "less solid", "so i can see underneath", "so i can see what is below",
        "fade the", "more transparent",
    ],
    "auto_arrange_layer_order": [
        "easier to read", "tidy the map", "clean up the map", "declutter", "map is cluttered", "looks messy", "hide the clutter",
    ],
}
# A live user report typo'd BOTH "hazard" -> "haszard" and "incident" -> "incedent" in the
# same query (2026-09-13) -- the alias entries above are exact-substring, so a misspelled
# word matches nothing at all, no matter how close. Scoped narrowly to avoid the false-positive
# risk of fuzzy-matching against the full ~169-tool vocabulary: only checked against this small,
# curated set of words that actually gate real capability (hazard/disaster reporting), only for
# query words of 5+ characters (short words have too many close neighbors to be a safe fuzzy
# target), and only ever ADDS a corrected word alongside the original -- never replaces or
# removes a query word, so a query that was already scoring correctly is unaffected.
_FUZZY_TYPO_VOCAB = {
    "hazard", "hazards", "disaster", "disasters", "incident", "incidents",
    "wildfire", "wildfires", "earthquake", "earthquakes", "flood", "floods",
    "drought", "droughts", "volcano", "volcanoes", "cyclone", "cyclones",
    "emergency", "emergencies",
}
_FUZZY_TYPO_MIN_WORD_LEN = 5
_FUZZY_TYPO_CUTOFF = 0.8


def _expand_query_with_fuzzy_corrections(query_words: set, query_lower: str) -> str:
    """Returns query_lower with a space-joined tail of any fuzzy-corrected words appended,
    for use as the alias-matching string. Does not mutate query_words (name/description
    scoring is unaffected -- see _FUZZY_TYPO_VOCAB's docstring above for why this stays
    narrowly scoped to the alias-matching path only)."""
    corrections = []
    for word in query_words:
        if len(word) < _FUZZY_TYPO_MIN_WORD_LEN or word in _FUZZY_TYPO_VOCAB:
            continue
        match = difflib.get_close_matches(
            word, _FUZZY_TYPO_VOCAB, n=1, cutoff=_FUZZY_TYPO_CUTOFF
        )
        if match:
            corrections.append(match[0])
    if not corrections:
        return query_lower
    return query_lower + " " + " ".join(corrections)
# Score contribution for an alias phrase match -- comparable to a name match
# (10), since these are curated synonyms for a specific known gap rather than
# an incidental substring hit, but not higher (a real name/description match
# should still win a tie against an alias match).
# Verbs and nouns that appear in dozens of tool names ("generate_*", "calculate_*", "*_layer"). A request that says "generate a buffer"
# must not get +10 for generate_html_dashboard, generate_report and generate_mapping_task_grid; the distinctive word (buffer,
# dashboard, report) still scores. Found by measurement on a long request: these verbs alone filled the tool list with unrelated tools.
_GENERIC_NAME_WORDS = frozenset({"generate", "calculate", "create", "apply", "get", "set", "add", "fetch", "run", "export", "extract",
                                 "analyze", "analyse", "layer", "layers", "map", "data", "style", "report", "analysis", "tool"})
_LONG_QUERY_WORDS = 25
_LONG_QUERY_MIN_SCORE = 6
_DESCRIPTION_HIT_CAP = 4        # at most +8 from description words, however long the request
# Was 10, the same as ONE generic name-word match. As the registry grew past 230 tools, more than 40 of them had "layer", "create" or "add" in
# their name, and for a short request ("create layer for Jordan ADM1") the curated alias tool tied with all of them and lost its slot to
# the alphabetical tie-break: adding the M2 tools made fetch_geoboundaries drop out. A curated phrase is the strongest signal the router
# has, so it now outranks a name-word match (10) plus a full set of description hits (+8). Guarded by tests/test_tool_router_basics.py.
_ALIAS_MATCH_SCORE = 25

# Common English function/filler words, excluded from name/description scoring -- 2026-09-12,
# a follow-up to the word-boundary fix above: switching to word-boundary matching correctly
# stopped "hi" from matching inside "histogram_equalization", but a query like "hello there"
# still pulled in the full top_k candidate set, because "there" genuinely appears as a real
# standalone word in several tool descriptions' ordinary English prose ("is there flooding
# here", "there is no addressable map item") -- a true word-boundary match, not a bug, just an
# extremely common word carrying no real intent signal. Deliberately small and conservative --
# only words with essentially zero chance of ever being the actual point of a GIS request, never
# a real (if short) content word like "map" or "fix". Doesn't touch the curated alias list
# (_TOOL_ALIASES) or the always_include/fallback logic below, only the two generic scoring loops.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "am",
    "this", "that", "these", "those", "there", "here", "it", "its",
    "and", "or", "but", "to", "of", "in", "on", "at", "for", "with",
    "as", "by", "from", "so", "if", "than", "then",
    "i", "you", "he", "she", "we", "they", "my", "your", "me",
    "hi", "hey", "hello", "thanks", "thank", "please", "ok", "okay", "yes", "no",
}


class ToolRouter:
    """Keyword & intent-based tool schema selector."""

    def __init__(self, full_schema_list: list[dict]):
        self.full_schema_list = full_schema_list

    def filter_relevant_tools(self, user_query: str, top_k: int = 40, carry_over_tools=None) -> list[dict]:
        """Returns top_k relevant tool schemas matching user query terms.

        `carry_over_tools`: names of tools the PREVIOUS turn used. A short follow-up ("EPSG:3857", "yes, the second one") shares no
        vocabulary with any tool, so scoring on the new message alone dropped the tool the conversation was in the middle of: in the
        rc17 hand test (2026-10-06) the model answered the CRS question with "add_point_layer is unavailable" because it was not in
        the turn's tool list, and the rc16 hint telling it to call add_point_layer again could not help. Names that are not
        registered tools are ignored."""
        if len(self.full_schema_list) <= top_k:
            return self.full_schema_list

        query_lower = user_query.lower()
        long_query = len(user_query.split()) > _LONG_QUERY_WORDS
        # _STOPWORDS removed here only -- query_lower (used by the separate curated-alias
        # check below) keeps every word, since a multi-word alias phrase like "rank the
        # districts" is matched as a whole substring, not word-by-word.
        query_tokens = set(re.findall(r'\w+', query_lower))
        query_words = set()
        for token in query_tokens:
            if token not in _STOPWORDS:
                query_words.add(token)
            if "_" in token:
                query_words.update(w for w in token.split("_") if w not in _STOPWORDS)

        # Alias matching only -- see _FUZZY_TYPO_VOCAB's docstring. Never touches query_words
        # itself, so name/description scoring (and every existing test asserting on it) is
        # unaffected; only the alias substring check below sees the corrected words.
        alias_query_lower = _expand_query_with_fuzzy_corrections(query_words, query_lower)

        # Tools explicitly requested by exact name in user_query/follow-up prompt get guaranteed inclusion
        explicit_tool_names = {
            t.get("function", {}).get("name", "")
            for t in self.full_schema_list
            if t.get("function", {}).get("name", "").lower() in query_lower
            and len(t.get("function", {}).get("name", "")) >= 4
        }

        # Always include core agent/task/memory tools. execute_pyqgis_script is
        # handled separately below (point 1 of
        # docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md): unlike these
        # genuinely-always-relevant bookkeeping tools, it's an arbitrary-code
        # last resort that was previously guaranteed a slot on every single
        # query regardless of relevance, undermining its own "rare, clearly-
        # fenced fallback" framing.
        always_include = {
            "get_layers", "get_attributes", "create_plan", "update_task",
            "set_task_preview", "store_project_memory", "store_global_memory",
            "generate_spatial_report"
        } | explicit_tool_names
        known_names = {t.get("function", {}).get("name", "") for t in self.full_schema_list}
        # Tools the request's DATA SOURCES and ACTIONS require (core/agent/capabilities.py), claimed before any description-word
        # scoring: a long request used to fill the slots with weak description matches (a dashboard, PDF-table and NDWI tool for a
        # water-service request) and leave out the tools the steps actually needed. Bounded, and only registered names count.
        with contextlib.suppress(Exception):
            from ..agent.capabilities import required_tools
            always_include |= {n for n in required_tools(user_query) if n in known_names}
            from ..agent.capabilities import is_multi_step, uncovered_capabilities
            if (uncovered_capabilities(user_query) or is_multi_step(user_query)) and "find_tools" in known_names:
                always_include.add("find_tools")      # a step with no dedicated tool, or a workflow: let the model look tools up
            if is_multi_step(user_query) and "run_steps" in known_names:
                always_include.add("run_steps")       # a workflow: let the model send a whole known chain in one round trip
                from ..agent.capabilities import needed_capabilities
                from ..agent.chains import chains_for
                for chain in chains_for([c for c, _t, _v in needed_capabilities(user_query)]):
                    # run_steps only accepts tools that were offered, so offer the chain's own
                    always_include |= {st["tool"] for st in chain["steps"] if st["tool"] in known_names}
        # At most six carried tools, so a long previous turn cannot crowd the relevant ones out of top_k.
        always_include |= {n for n in tuple(carry_over_tools or ())[:6] if n in known_names and n != "execute_pyqgis_script"}
        fallback_tool = "execute_pyqgis_script"

        # Sort deterministically by tool name instead of randomizing -- 2026-09-19, live-
        # verified follow-up to the "hi" fix above. random.shuffle() reordered the whole tool
        # list on every single call, which meant the serialized `tools` array in the request
        # body was almost never byte-identical between two calls even when they carried the
        # exact same tool SET, defeating prefix-based caching for that segment of the request
        # (Gemini's implicit caching -- automatic on 2.5+ models, no config needed -- discounts
        # a repeated prefix by 90%, confirmed against ai.google.dev/gemini-api/docs/caching and
        # ai.google.dev/gemini-api/docs/pricing, not assumed). Live-measured via a real 12-turn
        # Gemini session after this change: 6 of 23 calls reported real cached_tokens in the
        # response, a mechanism no run before this fix ever showed evidence of. Ties (0-score
        # filler tools) now break alphabetically, replacing the deliberate per-call randomness
        # the removed comment above described -- a real trade-off, not a pure improvement: that
        # randomness existed specifically so the same handful of filler tools didn't get a
        # permanent, arbitrary advantage every time nothing else matched (see the git history of
        # this line). Deterministic tie-breaking reintroduces that specific bias in exchange for
        # the caching win -- acceptable since filler tools are, by definition, not a real match
        # for the query either way, but worth knowing if that older bias ever matters again.
        shuffled = sorted(self.full_schema_list, key=lambda x: x.get("function", {}).get("name", ""))

        scored_tools = []
        for tool_obj in shuffled:
            fn = tool_obj.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "").lower()

            if name in always_include:
                scored_tools.append((1000, tool_obj))
                continue

            # Word-boundary matching, not substring containment -- 2026-09-12, from a live
            # token-usage report: a plain "hi" was costing ~8K tokens in wholly irrelevant tool
            # schemas because `"hi" in "histogram_equalization"` (and highlight_features,
            # hillshade) is True as a raw substring check, even though "hi" never appears there
            # as an actual word. Same bug hit longer words too, just less obviously: "there" (5
            # chars, already past the old length guard) still substring-matched inside "whereby"
            # and 6 other tool descriptions. Splitting the tool name on "_" and tokenizing the
            # description with the same \w+ regex used for query_words turns both checks into
            # real word-boundary membership tests instead of "is this text contained anywhere in
            # that text" -- the length guards below are now a secondary noise filter (e.g. "to"),
            # not the only thing standing between a short query word and a false match.
            # Generic words are discounted only for a LONG request, which is where the measurement that justified it was made. For a
            # short one ("zoom to the layer", "create layer for Jordan ADM1", "remove the layer X") "layer", "add", "export", "create" ARE the
            # signal: from rc23 on the discount applied to every request, add_layer_from_path, remove_layer, zoom_to_layer, export_layer and
            # the other layer tools stopped being offered, and ties were then broken alphabetically (apply_*, calculate_*). Found by replaying
            # 40 plain requests against every release (tests/test_tool_router_basics.py is the permanent guard).
            name_words = set(name.lower().split("_"))
            if long_query:
                name_words -= _GENERIC_NAME_WORDS
            desc_words = set(re.findall(r"\w+", desc))

            score = 0
            # Name match score
            if query_words & {w for w in name_words if len(w) > 2}:
                score += 10

            # Description match score -- capped: in a 70-100 word request nearly every tool description shares a few ordinary words
            # ("all", "points", "layer"), so uncapped +2 per word let description noise outrank real name and alias matches.
            description_hits = sum(1 for word in query_words if len(word) > 2 and word in desc_words)
            score += 2 * (min(description_hits, _DESCRIPTION_HIT_CAP) if long_query else description_hits)

            # Curated alias/synonym match score
            for alias in _TOOL_ALIASES.get(name, []):
                if alias in alias_query_lower:
                    score += _ALIAS_MATCH_SCORE

            scored_tools.append((score, tool_obj))

        # execute_pyqgis_script scored normally above, like every other
        # non-core tool -- it only gets a guaranteed slot here as a true
        # last resort, when nothing else in the whole candidate set scored
        # any real relevance at all (a query sharing no vocabulary with any
        # registered tool). On a query that matched something real, it
        # competes on its own natural score instead of an unconditional
        # synthetic boost, so genuinely-relevant tools aren't crowded out
        # and the model isn't nudged toward arbitrary code execution by
        # default. Confirmed live-code-execution capability doesn't
        # silently vanish either way: on a real match, several other
        # tools' own descriptions already steer the model back to
        # execute_pyqgis_script if truly needed (see e.g. layout_tools.py/
        # styling_tools.py's "don't hand-write X via execute_pyqgis_script"
        # framing) -- this only changes whether it's guaranteed *visible*,
        # not whether the model can still ask for it by name if it somehow
        # already knows to.
        # Excludes always_include too, not just the fallback tool itself --
        # those are synthetic 1000-scores unrelated to whether this
        # specific query matched anything real, and would otherwise make
        # "nothing else matched" false on every single query (confirmed by
        # this exact bug shipping to a failing test before this fix: a
        # nonsense query with zero real relevance still had get_layers/
        # create_plan/etc.'s synthetic 1000 in `other_scores`).
        other_scores = [
            score for score, tool in scored_tools
            if tool.get("function", {}).get("name") not in always_include | {fallback_tool}
        ]
        nothing_else_matched = not other_scores or max(other_scores) <= 0
        if nothing_else_matched:
            scored_tools = [
                (1000, tool) if tool.get("function", {}).get("name") == fallback_tool else (score, tool)
                for score, tool in scored_tools
            ]

        # Sort by score descending and take top_k
        scored_tools.sort(key=lambda x: x[0], reverse=True)
        # Drop zero-score filler tools even on a partial-signal query, not just the
        # nothing_else_matched case -- 2026-09-19 follow-up to the "hi" fix above. A query
        # that scores real relevance against 12 tools was still padding the returned set out
        # to the full top_k=40 with 0-score tools purely because they happened to sort within
        # the slice, which is the same wasted-token problem as the all-zero case, just
        # partially masked by the real matches sitting alongside it. Since scored_tools is
        # sorted descending, every positive-score tool already sorts before every 0-score
        # tool, so slicing to top_k first and then dropping 0-scores is equivalent to (not a
        # behavior change from) filtering positives first and slicing second -- this is a
        # strict simplification/extension of the prior nothing_else_matched-only logic, not a
        # separate code path, and unconditionally applies to every query now.
        # A long request shares an ordinary word or two with most tool descriptions; those one-word overlaps are noise, not relevance.
        # For a request of more than _LONG_QUERY_WORDS words a tool must score at least _LONG_QUERY_MIN_SCORE (a name or alias match,
        # three description words, or a capability the request names) to take a slot. Short requests keep the old rule (score > 0).
        floor = _LONG_QUERY_MIN_SCORE if len(user_query.split()) > _LONG_QUERY_WORDS else 1
        return [tool for score, tool in scored_tools[:top_k] if score >= floor]
