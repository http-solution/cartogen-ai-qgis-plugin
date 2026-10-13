"""Single source for the release-facing text that must change on EVERY version bump: the in-plugin Help ("What's new" and the
humanitarian tool list) and the README's "What's new" section and humanitarian table. Qt-free so tests can read it.

When you bump `version=` in metadata.txt, update this file in the same change (tests/test_release_docs_in_sync.py fails until the
metadata changelog, CHANGELOG.md, README and this module agree). Checklist: CONTRIBUTING.md, "Releasing".

`new_in` marks the version that introduced a tool; the README shows "(**new**)" for tools introduced in the two most recent
releases listed in NEW_MARK_VERSIONS.
"""

WHATS_NEW_VERSION = "1.16.0-rc40"
NEW_MARK_VERSIONS = ("1.16.0-rc39", "1.16.0-rc40")

# Headline items of the current version (the full list is the metadata.txt changelog block and CHANGELOG.md).
WHATS_NEW_ITEMS = [
    ('New tool: search_fact_checks', "Answers 'has this claim, video or photo been fact-checked?' from the published feeds of Snopes, PolitiFact, FactCheck.org, Full Fact, Lead Stories and the Arabic-language Fatabyyano (searchable in Arabic). Every reply names the outlets that answered or failed and says that only each outlet's newest 10 to 25 entries are searched, so no match is never evidence that a claim is true, false or unchecked. Reuters, AFP, Africa Check and AP refuse automated requests and cannot be asked. The six feeds were queried live from a development session; not hand-tested in QGIS."),
    ('Point positions the model typed are flagged', "Coordinates passed to add_point_layer, add_incident_point or execute_pyqgis_script that appear in neither your message nor an earlier tool result are flagged in the tool result and in the final reply ('Unverified point positions'). This closes the gap noted in rc39. It never blocks, and it cannot see coordinates computed or read from a file inside a script."),
    ('Routes from a depot in another layer', 'optimize_delivery_route takes additional_stops_layers, so a depot or hub in one layer and the stops in another no longer need scripts to merge them first (rc37 row F3 took 9 calls for 5 stops). Whether the assistant now does it in one call is not yet checked.'),
    ('Analysis fields are written through the edit session', 'Severity score, presence-gap status, population-in-need and damage-severity fields were added straight to the data provider, bypassing the edit buffer, so a failure half-way could not be undone and a layer you were already editing was ignored (issue 293). They now go through the same checked, undoable edit as the other field-writing tools.'),
    ('Downloads behind a proxy', "A download that follows a redirect (geoBoundaries boundary files do) used urllib for the redirected hop, which does not know a PAC or authenticated proxy that QGIS does. A hop urllib cannot connect to is now retried through QGIS's own network stack. geoBoundaries failures now say whether the lookup or the file download failed, and from which host. The tester's failure on 2026-10-13 is still unconfirmed; this fixes the best-supported explanation."),
    ('Security alerts and documentation site', "Fixes for the CodeQL alerts on the website prototype (content security policy, a reflected error message, a log format string), a test server that copied the Host header into a redirect, workflow permissions, and the documentation site's search. The documentation site is live at https://http-solution.github.io/cartogen-ai-qgis-plugin/."),
    ('Not hand-tested', 'Everything above is checked by the offline suite and CI (including the live checks in QGIS 4.2.2) only. The proxy fix was not tried behind a real proxy, the point-flagging and the depot merge were not tried with a real model, and the rc39 hand-test rows (no invented layer, follow-up, Stop on a long job) are still to run.'),
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
