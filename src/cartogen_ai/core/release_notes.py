"""Single source for the release-facing text that must change on EVERY version bump: the in-plugin Help ("What's new" and the
humanitarian tool list) and the README's "What's new" section and humanitarian table. Qt-free so tests can read it.

When you bump `version=` in metadata.txt, update this file in the same change (tests/test_release_docs_in_sync.py fails until the
metadata changelog, CHANGELOG.md, README and this module agree). Checklist: CONTRIBUTING.md, "Releasing".

`new_in` marks the version that introduced a tool; the README shows "(**new**)" for tools introduced in the two most recent
releases listed in NEW_MARK_VERSIONS.
"""

WHATS_NEW_VERSION = "1.16.0-rc36"
NEW_MARK_VERSIONS = ("1.16.0-rc35", "1.16.0-rc36")

# Headline items of the current version (the full list is the metadata.txt changelog block and CHANGELOG.md).
WHATS_NEW_ITEMS = [
    ('QGIS stays responsive during long analyses', "Loops over features, pairs and pixels used to run in one unbroken stretch on QGIS's main thread, so QGIS showed Not Responding and ignored Stop. About 90 such loops in the analysis, validation, styling, export and import tools now work in slices of about 50 ms: the window repaints, Stop is heard, and progress is reported every few seconds. A Stop inside an edit rolls the edit back."),
    ('Hub siting, allocation and delivery routes', 'The distance matrix is built in slices and the ranking, facility selection and route ordering run off the main thread. Route ordering now finds tours about 14 percent shorter on a 200-stop test and runs faster (it used to stop after 2000 trial moves). The route-risk tool merges geometry in one pass and tests incidents against a prepared buffer.'),
    ('Large raster classification', 'unsupervised_classification reads and classifies the raster in blocks, so memory no longer limits its size; a raster over 400 million cells is refused with a clip-it-first message (it used to refuse over 25 million cells).'),
    ('Fewer freezes elsewhere', 'geocode_batch (up to 25 lookups with pauses) no longer runs on the main thread and stops when you press Stop. Scheduled recurring workflows now skip a tick while another one or a chat request is running instead of starting a second analysis on top. The chat window removes the oldest messages once it holds more than 300 items, keeping the newest 200 (the saved conversation is untouched).'),
    ('Not hand-tested', 'CI is green, including the live checks in QGIS 4.2.2, but none of this has been tried on a large real project or hand-tested in desktop QGIS. The size of the speed-up on real data has not been measured, and 300 and 200 for the chat window are estimates.'),
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
 'find_incident_reports': '1.16.0-rc37'}


def tool_is_new(name):
    return TOOL_NEW_IN.get(name) in NEW_MARK_VERSIONS


def render_readme_table():
    """The README's humanitarian table rows, exactly as they must appear (tests compare)."""
    rows = []
    for title, tools in HUMANITARIAN_WORKFLOWS:
        cells = ", ".join(f"`{t}`" + (" (**new**)" if tool_is_new(t) else "") for t in tools)
        rows.append(f"| **{title}** | {cells} |")
    return rows
