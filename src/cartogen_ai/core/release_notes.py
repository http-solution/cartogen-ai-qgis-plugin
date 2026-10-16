"""Single source for the release-facing text that must change on EVERY version bump: the in-plugin Help ("What's new" and the
humanitarian tool list) and the README's "What's new" section and humanitarian table. Qt-free so tests can read it.

When you bump `version=` in metadata.txt, update this file in the same change (tests/test_release_docs_in_sync.py fails until the
metadata changelog, CHANGELOG.md, README and this module agree). Checklist: CONTRIBUTING.md, "Releasing".

`new_in` marks the version that introduced a tool; the README shows "(**new**)" for tools introduced in the two most recent
releases listed in NEW_MARK_VERSIONS.
"""

WHATS_NEW_VERSION = "1.17.0-rc43"
NEW_MARK_VERSIONS = ("1.17.0-rc42", "1.17.0-rc43")

# Headline items of the current version (the full list is the metadata.txt changelog block and CHANGELOG.md).
WHATS_NEW_ITEMS = [
    ('More QGIS actions by plain request', 'The approved Processing list grew from 166 to 267 algorithms: 66 raster algorithms (terrain indices, proximity, sieve, fill no-data, warp, translate, grid interpolation, cell-stack and fuzzify tools, zonal tables, constant and random rasters) and 35 more table, analysis and geometry algorithms (X/Y fields, extract by attribute, kernel density heatmap, raster pixels to points or polygons, multi-layer union, intersection and difference, drape lines on a DEM, rasterize, service area from a layer and others). Each was run once in real QGIS 4.2.2 in CI; any that failed there was left off (find projection hangs, line density could not create its raster, shortest path from a layer needs a purpose-built network). A layer list given to a raster-stack algorithm must hold rasters: vector layers there crashed QGIS in a test, so they are now refused before the algorithm runs.'),
    ('Edit features, not just values', "New tools: set a layer filter, move, rotate and scale features, merge features, split features by a line, undo and redo manual edits on a layer in edit mode, change a field's type, and start, save or discard editing. Anything that changes or removes data shows a preview with exact counts first."),
    ('Open more kinds of data', "New tools: add a PostGIS table through a connection saved in QGIS, create a virtual layer (SQL over the project's layers; a single SELECT only), load and save .qlr layer files, and package layers into one GeoPackage for offline use. NetCDF, GRIB, HDF, ECW, MrSID and mesh files (.nc .grb .2dm .slf) are opened when your QGIS build supports them."),
    ('Styling and print layouts', "New tools: set a layer's fill, outline, marker and opacity, label style (halo, buffer, placement) and raster style (resampling, brightness and contrast). Layouts: add label, picture, shape, arrow and attribute-table items, edit, move, rotate or remove them, set the map's scale, extent and rotation, change the page size, save and load layout templates, and export to PDF, image or SVG. HTML frames and pictures given as a URL are refused on purpose."),
    ('Project settings', 'New tools: rename a layer group, zoom to the previous or next extent, read and set layer metadata, snapping options, 1-N relations between layers, time-aware layers and the project time range, and text annotations on the map.'),
    ('Showcase services measured', 'A CI job now records which outside services answer from the build machine. The Copernicus DEM tile and Google News were reached; GDELT answered with a rate limit (HTTP 429) and DuckDuckGo returned no result list. The plugin falls back from GDELT to Google News and says when a service cannot be used.'),
    ('Not hand-tested', "Everything above is checked by the offline suite and, for the QGIS parts, by CI on QGIS 4.2.2 (each new tool is read back from real QGIS objects and each Processing algorithm was run once). None of it has been hand-tested in desktop QGIS. set_map_view, go_to_bookmark and zoom_history need the real map canvas, which CI does not have. PostGIS was tested against a throwaway server only. ECW and MrSID depend on your QGIS build's drivers and were not tested."),
]

HUMANITARIAN_WORKFLOWS = [('1. Rapid crisis and base mapping',
  ['search_hdx_datasets',
   'fetch_hdx_admin_boundaries',
   'fetch_geoboundaries',
   'fetch_osm_features',
   'ingest_osm_features',
   'fetch_building_footprints',
   'search_stac_satellite_imagery',
   'calculate_raster_change_detection',
   'calculate_damage_exposure_severity',
   'extract_features_from_imagery',
   'add_incident_point',
   'add_point_layer',
   'generate_mapping_task_grid',
   'import_humanitarian_table']),
 ('2. MSNA and field data',
  ['design_sampling_frame',
   'fetch_worldpop_population',
   'estimate_population_exposure',
   'load_tabular_data_as_layer',
   'extract_pdf_tables',
   'extract_word_tables',
   'aggregate_data',
   'aggregate_survey_indicator']),
 ('3. Logistics, routes and catchments',
  ['estimate_road_speeds',
   'build_composite_impedance_field',
   'apply_network_barriers',
   'calculate_service_area',
   'classify_facilities_by_access',
   'travel_time_matrix',
   'population_access_gap',
   'optimal_hub_siting',
   'location_allocation',
   'optimize_delivery_route',
   'score_route_incident_risk',
   'analyze_critical_links']),
 ('4. Severity mapping (JIAF-style)',
  ['calculate_severity_index',
   'calculate_presence_gap',
   'load_3w_data',
   'calculate_population_in_need',
   'hotspot_analysis',
   'analyze_incident_trend',
   'forecast_trend',
   'import_jiaf_inputs',
   'record_jiaf_setup',
   'get_jiaf_setup',
   'compute_jiaf_preliminary',
   'record_jiaf_decisions',
   'get_jiaf_decisions',
   'finalize_jiaf_results',
   'compute_jiaf_patterns']),
 ('5. Allocation and prioritisation',
  ['calculate_mcda_ranking',
   'fetch_fts_funding_data',
   'generate_sector_coverage_report',
   'weighted_overlay_analysis',
   'calculate_allocation_envelope']),
 ('6. Anticipatory action',
  ['evaluate_forecast_trigger',
   'fetch_gdacs_disaster_alerts',
   'fetch_nasa_eonet_events',
   'fetch_usgs_earthquakes',
   'fetch_ucdp_conflict_events',
   'find_incident_reports',
   'search_fact_checks',
   'fetch_nasa_active_fires',
   'generate_situation_dashboard',
   'run_monitoring_workflow',
   'schedule_recurring_workflow',
   'stop_recurring_workflow',
   'list_scheduled_workflows']),
 ('Data quality and governance',
  ['check_pcode_uniqueness',
   'check_pcode_hierarchy',
   'validate_schema',
   'list_schema_contracts',
   'get_dataset_status',
   'set_dataset_status',
   'advance_dataset_status',
   'get_provenance_record',
   'write_provenance_sidecar',
   'set_layer_sensitivity',
   'get_layer_sensitivity',
   'generate_map_product_qa_checklist']),
 ('Reporting and products',
  ['generate_chart',
   'generate_html_dashboard',
   'generate_temporal_dashboard',
   'generate_spatial_report',
   'generate_report',
   'apply_humanitarian_look']),
 ('Engineering hydrology',
  ['parse_dms_location', 'assess_watershed_hydrology_request', 'calculate_rational_watershed_peak_flow'])]

TOOL_NEW_IN = {'aggregate_survey_indicator': '1.16.0-rc12',
 'analyze_critical_links': '1.16.0-rc13',
 'apply_humanitarian_look': '1.16.0-rc13',
 'apply_network_barriers': '1.16.0-rc12',
 'assess_watershed_hydrology_request': '1.16.0-rc12',
 'calculate_allocation_envelope': '1.16.0-rc13',
 'calculate_mcda_ranking': '1.16.0-rc12',
 'calculate_rational_watershed_peak_flow': '1.16.0-rc12',
 'design_sampling_frame': '1.16.0-rc12',
 'evaluate_forecast_trigger': '1.16.0-rc12',
 'generate_mapping_task_grid': '1.16.0-rc12',
 'import_humanitarian_table': '1.16.0-rc13',
 'parse_dms_location': '1.16.0-rc12',
 'import_jiaf_inputs': '1.16.0-rc14',
 'record_jiaf_setup': '1.16.0-rc14',
 'get_jiaf_setup': '1.16.0-rc14',
 'compute_jiaf_preliminary': '1.16.0-rc14',
 'record_jiaf_decisions': '1.16.0-rc14',
 'get_jiaf_decisions': '1.16.0-rc14',
 'finalize_jiaf_results': '1.16.0-rc14',
 'compute_jiaf_patterns': '1.16.0-rc14',
 'fetch_usgs_earthquakes': '1.16.0-rc35',
 'fetch_ucdp_conflict_events': '1.16.0-rc35',
 'find_incident_reports': '1.16.0-rc37',
 'search_fact_checks': '1.16.0-rc40'}


def tool_is_new(name):
    return TOOL_NEW_IN.get(name) in NEW_MARK_VERSIONS


def render_readme_table():
    """The README's humanitarian table rows, exactly as they must appear (tests compare)."""
    rows = []
    for title, tools in HUMANITARIAN_WORKFLOWS:
        cells = ", ".join(f"`{t}`" + (" (**new**)" if tool_is_new(t) else "") for t in tools)
        rows.append(f"| **{title}** | {cells} |")
    return rows
