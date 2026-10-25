"""Single source for the release-facing text that must change on EVERY version bump: the in-plugin Help ("What's new" and the
humanitarian tool list) and the README's "What's new" section and humanitarian table. Qt-free so tests can read it.

When you bump `version=` in metadata.txt, update this file in the same change (tests/test_release_docs_in_sync.py fails until the
metadata changelog, CHANGELOG.md, README and this module agree). Checklist: CONTRIBUTING.md, "Releasing".

`new_in` marks the version that introduced a tool; the README shows "(**new**)" for tools introduced in the two most recent
releases listed in NEW_MARK_VERSIONS.
"""

WHATS_NEW_VERSION = "1.18.1"
NEW_MARK_VERSIONS = ("1.18.0", "1.18.1")

# Headline items of the current version (the full list is the metadata.txt changelog block and CHANGELOG.md).
WHATS_NEW_ITEMS = [
    ('Legend and footer on print layouts', "The legend no longer has an entry cut in half: its text and symbols shrink in steps, then the layers drawn underneath are left out and the legend title says how many. The footer check accepts a shortfall no bigger than its own padding, which removed a 'may not fit' warning on a footer that fit, and the result now reports the footer's needed and available height so a wrong warning on your fonts can be read from the evidence folder. A layout keeps the name you ask for (Big Map stays Big Map; the old Layout_ spelling still finds it)."),
    ('Charts and profiles say whether they drew', 'Adding a chart or an elevation profile to a layout now renders that item once and tells you whether it drew data or only axes, and what to check when it drew nothing. A test renders the profile five times in CI to catch a flaky render; it has not shown one.'),
    ('One Log Messages tab', 'The plugin logged under about 27 tags, so QGIS opened about 27 tabs, one of them spelled CartogenAi beside CartogenAI, and the model_call lines the cost table needs were not in the tab the README tells you to save. Everything is now in the single CartogenAI tab, with the component name at the start of the line.'),
    ('Fewer wrong plans', "A plain operation request is not answered with a mapping task plan any more (a replay of 385 plain prompts: 34 wrong before the first fix, 7 after it, 2 now, both right). 'Draw contour lines of the dem every 100' no longer starts a DEM download and a workflow plan when a DEM layer is already loaded. A listing tool that repeats now stops with a message naming the next tool."),
    ('Undo of a new field', 'Undoing add_field removes the new field while it is empty; once it holds values, undo refuses, says so and changes nothing. Deleting a filled field stays a deliberate step that asks.'),
    ('Point layers are kept or called temporary', "A point layer the assistant adds is kept in the project's results GeoPackage when the project is saved, so it is there after reopen; in an unsaved project the reply says it is temporary and why. Other tools that write temporary layers (incident, hazard and event layers) are not changed."),
    ('A hand test that costs no API money', 'The hand-test bundle now has a script that you run once in the QGIS Python console: it builds its own project, makes about a dozen layouts, measures the legend, footer, names, presets, profile, logo and sign-off, and exports the pages. A checker reads what you send back. The remaining rows need a person and a model and each starts from its own stated state.'),
    ('Known and open', 'Issues #362 and #380 stay open for their hand rows (animate, elevation profile, linked charts, merge, raster conversion), because they depend on what the model answers. Not changed: undo of rename_field and delete_field, and temporary layers from tools other than add_point_layer. A clean-profile install and an in-place upgrade have not been run on this line since rc6.'),
    ('Not hand-tested', 'Everything above is checked by the offline suite and, for the QGIS parts, by CI on QGIS 4.2.2; none of it has been hand-tested in desktop QGIS. How the legend and footer look on your own fonts is exactly what the new layout script measures on your machine.')
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
