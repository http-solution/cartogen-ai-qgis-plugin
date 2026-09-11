# -*- coding: utf-8 -*-
"""
Operation-type taxonomy for every registered Cartogen AI tool.

Closes half of point 20's real gap in
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: "No READ/CREATE/
MODIFY/DELETE/PUBLISH taxonomy exists in code -- that part is a genuine
real gap, unchanged." (The other half -- a snapshot/rollback mechanism
for partial multi-step failure -- is agent/transactions.py; see that
module's docstring for what it does and does not cover.)

Five categories, defined by their effect on project/external state, not
by how "risky" a tool sounds:

READ    Inspects or queries live project state or an external source.
        Never persists anything new. Feature *selection* and canvas
        zoom/pan are treated as READ here even though they are technically
        QGIS API calls that change object state -- QGIS does not persist
        either one into a saved project, so there is nothing for a
        rollback mechanism to ever need to undo.

CREATE  Adds something QGIS did not have before: a new layer, print
        layout, map theme, workflow preset, saved style file, agent plan,
        or memory note. The reverse of a CREATE is always "remove the
        thing that was just added" -- never a data-loss risk to anything
        that existed before the call. See transactions.py for the one
        sub-case (a newly added layer) this codebase can undo generically
        right now.

MODIFY  Changes a property of something that already existed: an existing
        layer's fields, geometry, renderer/style, name, visibility, draw
        order, subset filter, labeling, or tracked QA-gate/sensitivity
        metadata; an existing task or print-layout item's state. Only
        reversible if the prior value was captured before the call --
        this codebase does not yet do that generically (see
        transactions.py's docstring for why that is a real, separate,
        unbuilt piece of work, not a small addition).

DELETE  Removes or unconditionally replaces project state in a way this
        taxonomy cannot recover: removing a layer outright, or replacing
        the whole project with a different one (explicitly documented as
        "Destructive: any unsaved changes are lost").
        `execute_pyqgis_script` is also classified here even though most
        invocations of it are harmless -- arbitrary code can perform any
        of the other four categories' effects at once (or things outside
        all four), so this label reflects the ceiling of what it could
        do, not a typical call. The AST sandbox (point 19) is the actual
        control on this tool; this classification is informational only,
        it does not add or replace any gate.

PUBLISH Writes a human-facing artifact to disk: an exported vector/CSV
        file, a printed map image, a chart, a Word/HTML report or
        dashboard, a provenance sidecar, a saved .qml style, or the QGIS
        project file itself. Never mutates layer data in the live
        project, but the artifact can immediately leave the machine
        (email, upload, print) the moment it is written, which is a
        materially different risk shape than CREATE/MODIFY -- hence its
        own category rather than folding it into one of those two.

This module is deliberately hand-reviewed against the actual source of
every tool below (see the 2026-09-07 session notes for the verification
method: static analysis for addMapLayer/removeMapLayer/addAttribute/
setCustomProperty/file-write call sites, cross-checked against each
tool's own description, with every ambiguous case read in full), not
inferred at runtime from tool names. A name-based guess is exactly the
kind of unverified shortcut this project's own reconciliation lesson
(see the Obsidian vault's DECISION_LOG.md, 2026-09-05) warned against for
safety-relevant classification.

`tests/test_tool_operations.py` asserts this dict's keys exactly match
`TOOL_REGISTRY`'s keys (both directions) -- a new tool with no entry
here, or a stale entry for a removed tool, fails the suite instead of
silently going unclassified.
"""

READ = "READ"
CREATE = "CREATE"
MODIFY = "MODIFY"
DELETE = "DELETE"
PUBLISH = "PUBLISH"

VALID_OPERATION_TYPES = frozenset({READ, CREATE, MODIFY, DELETE, PUBLISH})

TOOL_OPERATION_TYPES = {
    # -- analysis_tools.py --
    # These four all take an optional output_field: when given, the
    # composite score/classification is written back onto the input
    # layer via QgsVectorDataProvider.addAttributes/changeAttributeValues
    # (see _write_scores_to_layer / _write_presence_gap_status_to_layer /
    # _write_damage_severity_to_layer). Classified MODIFY for the
    # capability, even on a call that omits output_field.
    "calculate_severity_index": MODIFY,
    "calculate_presence_gap": MODIFY,
    "calculate_population_in_need": MODIFY,
    "calculate_damage_exposure_severity": MODIFY,
    "forecast_trend": READ,
    "analyze_incident_trend": READ,

    # -- dataset_status_tools.py --
    "get_dataset_status": READ,
    "set_dataset_status": MODIFY,
    "advance_dataset_status": MODIFY,

    # -- db_and_workflow_tools.py --
    # "read-only" describes the SQL statement guard, not the QGIS project
    # effect: both the PostGIS and virtual-provider branches call
    # QgsProject.instance().addMapLayer() on the query result.
    "execute_read_only_sql": CREATE,
    "save_workflow_preset": CREATE,
    "load_workflow_preset": READ,

    # -- export_tools.py --
    "export_layer": PUBLISH,
    "export_to_csv": PUBLISH,
    "print_map": PUBLISH,
    "generate_report": PUBLISH,
    # Returns a markdown string only -- no file write, no project mutation.
    "generate_spatial_report": READ,
    "generate_html_dashboard": PUBLISH,
    "generate_temporal_dashboard": PUBLISH,
    "export_temporal_animation_frames": PUBLISH,

    # -- humanitarian_tools.py --
    "search_hdx_datasets": READ,
    "fetch_fts_funding_data": READ,
    # Returns a JSON feature summary only; does not add a layer.
    "fetch_osm_features": READ,
    "fetch_hdx_admin_boundaries": CREATE,
    "fetch_building_footprints": CREATE,
    "fetch_geoboundaries": CREATE,
    "fetch_worldpop_population": CREATE,
    # Both may create a brand-new point layer, or append to an
    # already-existing one of the same name (explicit in add_point_layer's
    # own description) -- the static label can't distinguish those two
    # cases, so it's set to the more common/first-use case. transactions.py
    # resolves the ambiguity per-call by diffing the project's actual
    # layer set rather than trusting this label.
    "add_incident_point": CREATE,
    "add_point_layer": CREATE,

    # -- imagery_extraction.py --
    "extract_features_from_imagery": CREATE,

    # -- layout_tools.py --
    # Always adds a new QgsPrintLayout to the project's layout manager;
    # optionally also exports it to a file if output_path is given. The
    # layout-creation half is treated as primary.
    "create_print_layout": CREATE,
    "list_layouts": READ,
    "export_layout_atlas": PUBLISH,
    "list_layout_items": READ,
    "update_layout_item_text": MODIFY,

    # -- logistics_tools.py --
    "optimal_hub_siting": READ,
    "location_allocation": READ,
    "optimize_delivery_route": CREATE,
    "calculate_service_area": CREATE,
    "travel_time_matrix": READ,
    "population_access_gap": CREATE,
    # Calls buffer_analysis() internally to build its risk-corridor layer,
    # then styles that new layer -- so this is a CREATE, not just a style
    # change on an existing layer.
    "score_route_incident_risk": CREATE,

    # -- monitoring_tools.py --
    # Replays an arbitrary saved tool sequence -- its real operation type
    # depends entirely on the preset's own contents. Classified MODIFY as
    # a deliberately conservative default for a composite/meta tool, not
    # a claim that every run only modifies existing state.
    "run_monitoring_workflow": MODIFY,
    "schedule_recurring_workflow": CREATE,
    "stop_recurring_workflow": DELETE,
    "list_scheduled_workflows": READ,

    # -- multimodal_remote_sensing.py --
    "search_stac_satellite_imagery": READ,
    # Saves a temp screenshot for the model's own visual inspection --
    # transient working data, not a human-facing deliverable.
    "inspect_canvas_visually": READ,
    "calculate_raster_change_detection": CREATE,

    # -- pcode_validation_tools.py --
    "check_pcode_uniqueness": READ,
    "check_pcode_hierarchy": READ,

    # -- project_tools.py --
    "save_project": PUBLISH,
    # "Destructive: any unsaved changes are lost" -- replaces the whole
    # project, the highest-risk tier in this taxonomy.
    "load_project": DELETE,
    "create_map_theme": CREATE,
    # Restores a saved theme's layer visibility/style onto the CURRENT
    # project -- changes existing layers' properties, doesn't add new ones.
    "apply_map_theme": MODIFY,
    "list_map_themes": READ,

    # -- provenance_tools.py --
    "get_provenance_record": READ,
    "write_provenance_sidecar": PUBLISH,

    # -- qa_checklist_tools.py --
    "generate_map_product_qa_checklist": READ,

    # -- raster_tools.py --
    "calculate_ndvi": CREATE,
    "calculate_ndwi": CREATE,
    "weighted_overlay_analysis": CREATE,
    "calculate_ndre": CREATE,
    "hillshade": CREATE,
    "slope_analysis": CREATE,
    "aspect_analysis": CREATE,
    "zonal_statistics": READ,
    "raster_clip": CREATE,
    "unsupervised_classification": CREATE,
    "supervised_classification": CREATE,
    "histogram_equalization": CREATE,
    "mosaic_rasters": CREATE,
    "band_composite": CREATE,
    "pan_sharpening": CREATE,
    "interpolate_surface": CREATE,
    "elevation_profile": READ,
    "georeference_image": CREATE,
    "estimate_population_exposure": READ,
    "apply_raster_stretch": MODIFY,

    # -- reporting_tools.py --
    "generate_chart": PUBLISH,
    "extract_pdf_tables": READ,
    "extract_word_tables": READ,
    "load_3w_data": READ,
    "aggregate_data": READ,
    # Calls generate_chart() internally -- writes a PNG the same way.
    "generate_sector_coverage_report": PUBLISH,

    # -- schema_contract_tools.py --
    "list_schema_contracts": READ,
    "validate_schema": READ,

    # -- sensitivity_tools.py --
    "set_layer_sensitivity": MODIFY,
    "get_layer_sensitivity": READ,

    # -- confidence_tools.py --
    "set_layer_confidence": MODIFY,
    "get_layer_confidence": READ,

    # -- data_export_tools.py -- writes a new file to disk, same category as
    # export_layer/export_to_csv above.
    "export_stored_data": PUBLISH,

    # -- styling_tools.py --
    "apply_categorized_style": MODIFY,
    "apply_graduated_style": MODIFY,
    "apply_graduated_symbol_style": MODIFY,
    "apply_heatmap_style": MODIFY,
    "hotspot_analysis": CREATE,
    "change_layer_color": MODIFY,
    "set_layer_transparency": MODIFY,
    "auto_arrange_layer_order": MODIFY,
    "set_layer_order": MODIFY,
    "save_layer_style": PUBLISH,
    "load_layer_style": MODIFY,

    # -- system_tools.py --
    "search_web": READ,
    "gemini_grounded_search": READ,
    "openai_grounded_search": READ,
    "geocode_and_enrich": READ,
    "geocode_batch": READ,
    "execute_pyqgis_script": DELETE,

    # -- task_tools.py --
    "create_plan": CREATE,
    "set_task_preview": MODIFY,
    "update_task": MODIFY,
    "store_project_memory": CREATE,
    "store_global_memory": CREATE,

    # -- vector_tools.py --
    "get_layers": READ,
    "get_attributes": READ,
    # setSubsetString persists a query filter on the layer.
    "run_query": MODIFY,
    "buffer_analysis": CREATE,
    "highlight_features": READ,
    "remove_layer": DELETE,
    "rename_layer": MODIFY,
    "zoom_to_layer": READ,
    "toggle_visibility": MODIFY,
    "add_layer_from_path": CREATE,
    "load_tabular_data_as_layer": CREATE,
    "apply_labels": MODIFY,
    "clip_layer": CREATE,
    "intersect_layers": CREATE,
    "union_layers": CREATE,
    "difference_layers": CREATE,
    "convex_hull": CREATE,
    "voronoi_polygons": CREATE,
    "delaunay_triangulation": CREATE,
    "find_nearest_features": CREATE,
    "convert_to_singlepart": CREATE,
    "simplify_geometry": CREATE,
    "field_statistics": READ,
    "select_by_location": READ,
    "invert_selection": READ,
    "dissolve_layer": CREATE,
    "merge_layers": CREATE,
    "spatial_join": CREATE,
    "join_by_attribute": CREATE,
    "calculate_area": MODIFY,
    "calculate_length": MODIFY,
    "centroid": CREATE,
    "reproject_layer": CREATE,
    "fix_geometries": CREATE,
    "select_by_attribute": READ,
    "field_calculator": MODIFY,
    "get_feature_count": READ,
    "open_attribute_table": READ,
    "zoom_to_feature": READ,
    "get_crs": READ,
    "diagnose_topology": READ,
    "verify_crs_compatibility": READ,
    "obfuscate_sensitive_points": CREATE,

    # -- tool_operations_tools.py -- pure lookups over this same dict.
    "get_tool_operation_type": READ,
    "list_tools_by_operation_type": READ,

    # -- transaction_tools.py --
    "get_turn_transaction_log": READ,
    # Its only real effect is removing the layer(s) a past call added --
    # same category as remove_layer, and gated by the identical
    # confirmed=False -> PREVIEW_REQUIRED pattern.
    "undo_last_operation": DELETE,
}


def get_tool_operation_type(name):
    """Returns one of READ/CREATE/MODIFY/DELETE/PUBLISH for a registered
    tool name, or None if the name isn't in the taxonomy at all (unknown
    tool name -- not the same as an intentionally-unclassified one, since
    the completeness test guarantees there are no intentionally-unclassified
    entries for anything actually in TOOL_REGISTRY)."""
    return TOOL_OPERATION_TYPES.get(name)


def list_tools_by_operation_type(operation_type):
    """Returns the sorted list of tool names classified under one category.
    Raises ValueError on an unrecognized category rather than silently
    returning an empty list, which would look identical to "no tools in
    this real category"."""
    if operation_type not in VALID_OPERATION_TYPES:
        raise ValueError(
            f"Unknown operation type {operation_type!r}. Valid: {sorted(VALID_OPERATION_TYPES)}"
        )
    return sorted(name for name, op in TOOL_OPERATION_TYPES.items() if op == operation_type)
