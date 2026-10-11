"""Single source for the release-facing text that must change on EVERY version bump: the in-plugin Help ("What's new" and the
humanitarian tool list) and the README's "What's new" section and humanitarian table. Qt-free so tests can read it.

When you bump `version=` in metadata.txt, update this file in the same change (tests/test_release_docs_in_sync.py fails until the
metadata changelog, CHANGELOG.md, README and this module agree). Checklist: CONTRIBUTING.md, "Releasing".

`new_in` marks the version that introduced a tool; the README shows "(**new**)" for tools introduced in the two most recent
releases listed in NEW_MARK_VERSIONS.
"""

WHATS_NEW_VERSION = "1.16.0-rc32"
NEW_MARK_VERSIONS = ("1.16.0-rc31", "1.16.0-rc32")

# Headline items of the current version (the full list is the metadata.txt changelog block and CHANGELOG.md).
WHATS_NEW_ITEMS = [
    ('A refused AI request now says why', "When Google, OpenAI or another provider answers 401 or 403, the chat message now includes the provider's own short reason code (for example PERMISSION_DENIED, API_KEY_INVALID or SERVICE_DISABLED). The rest of the response is still hidden, because some providers echo part of the key back, and only values that look like a plain code name are shown."),
    ('Switch back to the previous request sender', "A Gemini key that worked in a test outside QGIS was refused with 403 when the plugin sent the same kind of request through QGIS's network stack. The cause has not been found. Setting cartogen_ai/hosted_requests_via_qgis to false in QGIS's advanced settings sends hosted AI requests (Gemini, OpenAI, Claude, OpenRouter) the way versions before rc28 did. It is on by default."),
    ('Refusals are logged without secrets', 'A 401 or 403 on the QGIS path now writes a log line with the host and whether a QGIS proxy is set, never the key, the headers or the response body.'),
    ('Not hand-tested', 'CI is green, including the live checks in QGIS 4.2.2, but none of this has been hand-tested in desktop QGIS, and it has not been confirmed that the switch fixes the Gemini 403.'),
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
 'compute_jiaf_patterns': '1.16.0-rc14'}


def tool_is_new(name):
    return TOOL_NEW_IN.get(name) in NEW_MARK_VERSIONS


def render_readme_table():
    """The README's humanitarian table rows, exactly as they must appear (tests compare)."""
    rows = []
    for title, tools in HUMANITARIAN_WORKFLOWS:
        cells = ", ".join(f"`{t}`" + (" (**new**)" if tool_is_new(t) else "") for t in tools)
        rows.append(f"| **{title}** | {cells} |")
    return rows
