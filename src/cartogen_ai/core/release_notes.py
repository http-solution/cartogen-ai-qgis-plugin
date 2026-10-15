"""Single source for the release-facing text that must change on EVERY version bump: the in-plugin Help ("What's new" and the
humanitarian tool list) and the README's "What's new" section and humanitarian table. Qt-free so tests can read it.

When you bump `version=` in metadata.txt, update this file in the same change (tests/test_release_docs_in_sync.py fails until the
metadata changelog, CHANGELOG.md, README and this module agree). Checklist: CONTRIBUTING.md, "Releasing".

`new_in` marks the version that introduced a tool; the README shows "(**new**)" for tools introduced in the two most recent
releases listed in NEW_MARK_VERSIONS.
"""

WHATS_NEW_VERSION = "1.17.0-rc42"
NEW_MARK_VERSIONS = ("1.16.3", "1.17.0-rc42")

# Headline items of the current version (the full list is the metadata.txt changelog block and CHANGELOG.md).
WHATS_NEW_ITEMS = [
    ('Run QGIS tools by name', "The approved Processing list grew from 42 to 166 algorithms: 73 geometry tools (densify, smooth, extract vertices, polygons to lines, hulls, boundaries and more), 11 table and selection tools (delete duplicates, drop fields, random extract, join by location summary and others), 35 analysis and creation tools (distance matrix, hub lines, random points, mean coordinates, topological colouring, the 16 geometry checks) and 5 expression tools (extract, geometry and order by expression, autoincrement field, random points inside polygons). New tool find_processing_algorithm searches the list by a few words and returns each algorithm's exact parameters. Each algorithm was run once in real QGIS 4.2.2 in CI; any that failed there was left off. Expression tools refuse env(), file functions and eval() in what the model writes. Algorithms that need file output, a path, or a selection change on your own layer are not on the list."),
    ('Raster calculator', 'New tool raster_calculator: map algebra with QGIS\'s own calculator, for example "dem@1" > 100 or ("nir@1" - "red@1") / ("nir@1" + "red@1"). Only numbers, + - * / ^, comparisons, AND, OR, brackets and sqrt sin cos tan asin acos atan ln log10 abs min max are accepted; layers must exist, share a coordinate system and have unique names. The result is a new raster; no input is changed.'),
    ('Layers, groups, map view and project', 'New tools: create an empty layer, add a basemap or a web service layer (WMS, WFS, XYZ), find and repair broken layer paths, assign a layer CRS, save a layer as another format, create layer groups and move layers into them, set the project CRS and properties, set the map view (centre, scale), create and go to bookmarks, and measure a distance.'),
    ('Selections and attribute editing', 'New tools: select all, select by expression, clear selection, set an attribute value, add, rename and delete a field, add a feature from WKT, delete features. Edits go through the edit session so they can be undone. Expressions the model writes are screened: env(), file functions and eval() are refused.'),
    ('Hydrology and research', 'New tool delineate_watershed: from a DEM and an outlet point it derives the basin, longest flow path and outlet, and returns area, stream length, relief, slope and time of concentration, then hands over to the existing peak-flow tool, which still refuses guessed rainfall intensity or runoff coefficient. New tool web_research returns sourced findings; search_web now falls back instead of failing when the search package is missing; find_incident_reports can include news as an opt-in source mapped from place names in headlines.'),
    ('Safety net', 'Every release is now built behind a gate of the offline test suite, a tool-schema snapshot, golden routing requests with size pins, a coverage ratchet over 163 QGIS actions and all 772 registry algorithms, and the replay of 26 recorded sessions. Plain requests that worked before must keep being offered their tools.'),
    ('Not hand-tested', 'Everything above is checked by the offline suite and, for the QGIS parts, by CI on QGIS 4.2.2. None of it has been hand-tested in desktop QGIS. Not verified from the build environment: the Copernicus DEM download behind delineate_watershed, and the live GDELT, Google News and DuckDuckGo responses behind the news source and web_research. set_map_view and go_to_bookmark need the real map canvas, which CI does not have.'),
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
