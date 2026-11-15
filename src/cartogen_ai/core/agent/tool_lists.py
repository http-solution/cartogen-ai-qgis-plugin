"""The reviewed lists of tools that may be handed to something outside the chat (PLAN-034 MCP, PLAN-048 shared workflow files). One place, so the two
doors cannot drift apart: a tool added here is available to both, a tool removed here leaves both. Pure: names only, no imports.

READ_TOOLS   run at once; they show field names, counts, statistics, extents, metadata and QA status of the open project, never feature values.
WRITE_TOOLS  make a NEW layer from existing ones, or change presentation only. Over MCP each call waits for a person's yes; in a workflow file the
             person has seen every step before the run and each step still goes through the normal gates.
Left out on purpose, and pinned by tests: tools that edit existing data, delete, write to a path the caller names, run code, store memory or change
sensitivity, take a free URL, or have their own `confirmed` step (that confirmation belongs to the plugin chat)."""

READ_TOOLS = frozenset({
    "get_layers", "get_attributes", "get_crs", "get_feature_count", "get_layer_extent", "get_layer_metadata", "get_layer_sensitivity",
    "get_layer_confidence", "get_dataset_status", "get_provenance_record", "field_statistics", "list_layouts", "list_layout_items",
    "list_map_themes", "list_bookmarks", "list_relations", "verify_crs_compatibility", "find_broken_layers", "check_pcode_uniqueness",
    "check_pcode_hierarchy", "validate_schema", "list_schema_contracts", "measure_distance", "find_tools",
})

WRITE_TOOLS = frozenset({
    # analysis: each makes a NEW layer from existing ones
    "buffer_analysis", "clip_layer", "centroid", "convex_hull", "dissolve_layer", "difference_layers", "intersect_layers", "union_layers",
    "merge_layers", "spatial_join", "join_by_attribute", "convert_to_singlepart", "simplify_geometry", "fix_geometries", "reproject_layer",
    "voronoi_polygons", "delaunay_triangulation", "find_nearest_features", "calculate_service_area",
    # presentation only
    "apply_graduated_style", "apply_categorized_style", "change_layer_color", "apply_labels", "set_layer_transparency", "toggle_visibility", "rename_layer",
})


# Fixed-service fetch tools (each talks to one named provider, takes no URL). Allowed as steps in a shared workflow file (PLAN-048), NOT over MCP.
# A test pins that this equals source_record.SOURCES, so a fetch tool that gets a source record is a deliberate decision about files too.
FETCH_TOOLS = frozenset({
    "fetch_geoboundaries", "fetch_hdx_admin_boundaries", "fetch_building_footprints", "fetch_worldpop_population", "ingest_osm_features",
    "fetch_osm_features", "fetch_fts_funding_data", "fetch_nasa_active_fires", "fetch_nasa_eonet_events", "fetch_gdacs_disaster_alerts",
    "fetch_usgs_earthquakes", "fetch_ucdp_conflict_events",
})

FILE_TOOLS = READ_TOOLS | WRITE_TOOLS | FETCH_TOOLS      # what a step in a shared workflow file may call
