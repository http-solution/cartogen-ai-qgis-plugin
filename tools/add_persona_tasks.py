"""Add the persona tasks and the `persona` field to the task register (PLAN-023 R1-5). Idempotent: rerunning rewrites the same result.

Run:  python tools/add_persona_tasks.py            # rewrite register + persona task_ids
      python tools/add_persona_tasks.py --check    # exit 1 if it would change anything

What it does
  * every existing task gets `persona`: ["engineering"] for section 36 (engineering hydrology) and ["humanitarian"] for the rest, because the register was written as the humanitarian mapping register (docs/PERSONA_TOOLS_STYLING_PLAN_2026-10-04.md section 1, point 3);
  * sections 38 to 50 are added, one per persona except `general` and `defense_intel` (persona numbers 2 to 14), 4 tasks each (52), and R3-6 adds 1 to agriculture and 2 to environment (55 in all); section 37 stays empty on purpose (the plan numbers the persona sections 38 to 50);
  * each persona file's `task_ids` is set to its own tasks.
Every new task uses only tools that exist in the registry TODAY (a test checks it); a capability that is `not built` in the persona's readiness list has no task. `acc` and `prod` are filled in by tools/derive_task_io.py's own derive(), so one run of this script is enough."""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from cartogen_ai.core.agent import task_matcher  # noqa: E402
sys.path.insert(0, HERE)
import derive_task_io  # noqa: E402

REGISTER = os.path.join(ROOT, "src", "cartogen_ai", "core", "agent", "task_register.json")
PERSONA_DIR = os.path.join(ROOT, "src", "cartogen_ai", "core", "personas")

# (section, persona id, section name, [(text, output, slots, tools)])
SECTIONS = [
    ("38", "humanitarian", "Humanitarian response: overview, access and needs", [
        ("Build a situation overview for a crisis area", "dashboard", ["aoi"], ["fetch_hdx_admin_boundaries", "fetch_worldpop_population", "fetch_gdacs_disaster_alerts", "generate_situation_dashboard"]),
        ("Find who cannot reach services within a travel time", "analysis", ["facility_type", "threshold"], ["calculate_service_area", "classify_facilities_by_access", "population_access_gap"]),
        ("Estimate people in need and a preliminary JIAF severity", "analysis", [], ["aggregate_survey_indicator", "calculate_severity_index", "compute_jiaf_preliminary", "calculate_population_in_need"]),
        ("Divide a response area into a mapping task grid", "layer", ["aoi"], ["fetch_hdx_admin_boundaries", "generate_mapping_task_grid"]),
    ]),
    ("39", "engineering", "Engineering: terrain, corridors and plans", [
        ("Produce terrain products for a site", "layer", ["aoi"], ["fetch_dem", "hillshade", "slope_analysis", "generate_contours"]),
        ("Draw a terrain cross-section along a line", "analysis", [], ["fetch_dem", "elevation_profile"]),
        ("Rank candidate corridors by slope and constraints", "layer", ["aoi"], ["fetch_dem", "slope_analysis", "weighted_overlay_analysis"]),
        ("Georeference a scanned site plan", "layer", [], ["georeference_image", "parse_dms_location"]),
    ]),
    ("40", "urban_planning", "Urban planning: zoning, catchments and parcels", [
        ("Check proposed parcels against zoning overlays", "analysis", [], ["intersect_layers", "spatial_join", "generate_report"]),
        ("Show who a planned public facility would serve", "analysis", ["threshold", "population_src"], ["calculate_service_area", "estimate_population_exposure", "population_access_gap"]),
        ("Rank candidate sites for a new public facility", "layer", ["aoi", "facility_type"], ["fetch_osm_features", "calculate_mcda_ranking"]),
        ("Split a parcel along a proposed boundary line", "layer", [], ["add_layer_from_path", "split_features_by_line"]),
    ]),
    ("41", "logistics", "Logistics: hubs, routes and delivery risk", [
        ("Choose hub locations and the demand each one serves", "layer", [], ["add_layer_from_path", "optimal_hub_siting", "location_allocation", "calculate_allocation_envelope"]),
        ("Compare depots by travel time to the delivery points they serve", "analysis", [], ["classify_facilities_by_access", "travel_time_matrix"]),
        ("Plan a single-vehicle delivery tour", "layer", [], ["add_layer_from_path", "optimize_delivery_route"]),
        ("Score route risk from incidents and apply road barriers", "analysis", [], ["apply_network_barriers", "score_route_incident_risk"]),
    ]),
    ("42", "agriculture", "Agriculture: crop indices, seasons and zones", [
        ("Compute vegetation indices for a field from satellite imagery", "layer", ["aoi", "time_range"], ["search_stac_satellite_imagery", "load_stac_assets", "calculate_spectral_index"]),
        ("Compare crop condition between two seasons", "analysis", ["time_range"], ["raster_time_series_stats", "calculate_change_matrix"]),
        ("Delineate management zones inside a field", "layer", [], ["add_layer_from_path", "create_zoning_map", "zonal_statistics"]),
        ("Check crop water stress with NDWI and NDRE", "layer", ["aoi", "time_range"], ["search_stac_satellite_imagery", "calculate_ndwi", "calculate_ndre"]),
        ("Lay out a report for one field", "layout", [], ["add_layer_from_path", "create_print_layout", "print_map"]),
    ]),
    ("43", "environment", "Environment: land cover, change and suitability", [
        ("Detect land cover change between two dates", "layer", [], ["add_layer_from_path", "calculate_raster_change_detection"]),
        ("Tabulate land cover from-to transitions", "analysis", [], ["calculate_change_matrix"]),
        ("Classify land cover from training samples", "layer", [], ["add_layer_from_path", "supervised_classification"]),
        ("Rank sites for habitat or restoration suitability", "analysis", [], ["weighted_overlay_analysis", "buffer_analysis"]),
        ("Colour a classified layer with the official ESA WorldCover legend", "layer", [], ["add_layer_from_path", "apply_land_cover_look"]),
        ("Lay out a report on land cover change", "layout", [], ["add_layer_from_path", "apply_land_cover_look", "create_print_layout", "print_map"]),
    ]),
    ("44", "public_health", "Public health: access, cases and indicators", [
        ("Map health facility access and the population left out", "analysis", ["aoi", "facility_type", "threshold"], ["fetch_worldpop_population", "calculate_service_area", "classify_facilities_by_access", "population_access_gap"]),
        ("Geocode case addresses and chart the trend over time", "layer", ["time_range"], ["geocode_batch", "analyze_incident_trend", "generate_chart"]),
        ("Show where cases cluster with a density surface", "layer", [], ["add_layer_from_path", "hotspot_analysis", "obfuscate_sensitive_points"]),
        ("Summarise a survey indicator with small-number suppression", "analysis", [], ["aggregate_survey_indicator", "generate_chart"]),
    ]),
    ("45", "disaster_risk", "Disaster risk: hazards, exposure and triggers", [
        ("Check current hazard alerts for an area", "layer", ["aoi"], ["fetch_gdacs_disaster_alerts", "fetch_nasa_eonet_events", "fetch_usgs_earthquakes"]),
        ("Estimate the people and assets exposed to a hazard", "analysis", ["population_src"], ["estimate_population_exposure", "calculate_damage_exposure_severity"]),
        ("Set a forecast trigger and schedule its monitoring", "analysis", [], ["evaluate_forecast_trigger", "schedule_recurring_workflow"]),
        ("Score hazard susceptibility with a documented weighted overlay", "layer", ["aoi"], ["fetch_dem", "weighted_overlay_analysis"]),
    ]),
    ("46", "utilities", "Utilities: network checks, faults and CAD", [
        ("Check a utility network for topology problems", "analysis", [], ["diagnose_topology"]),
        ("Find the nearest assets to a reported fault", "analysis", [], ["find_nearest_features"]),
        ("Find critical links whose loss would split the network", "analysis", [], ["analyze_critical_links", "apply_network_barriers"]),
        ("Export network layers to DXF for CAD", "dataset", [], ["export_layers_to_dxf"]),
    ]),
    ("47", "transport", "Transport: accessibility, speeds and weak links", [
        ("Map multi-band travel time around a stop or facility", "layer", ["aoi", "threshold"], ["fetch_osm_features", "calculate_service_area"]),
        ("Estimate road speeds and travel times on a road network", "analysis", ["aoi"], ["fetch_osm_features", "estimate_road_speeds", "calculate_service_area"]),
        ("Find the weak links in a road network", "analysis", [], ["analyze_critical_links", "build_composite_impedance_field"]),
        ("Classify facilities by how reachable they are", "analysis", ["facility_type", "threshold"], ["classify_facilities_by_access", "population_access_gap"]),
    ]),
    ("48", "public_safety", "Public safety: incidents, coverage and route safety", [
        ("Map incident density and its trend", "layer", [], ["add_layer_from_path", "hotspot_analysis", "apply_heatmap_style", "analyze_incident_trend"]),
        ("Blur exact incident points to protect people", "dataset", [], ["obfuscate_sensitive_points", "set_layer_sensitivity"]),
        ("Rate route safety from past incidents", "analysis", [], ["score_route_incident_risk", "apply_network_barriers"]),
        ("Show response coverage within a response time", "layer", ["aoi", "threshold"], ["fetch_osm_features", "calculate_service_area"]),
    ]),
    ("49", "research", "Research: provenance, workflows and metadata", [
        ("Record how a result was produced", "report", [], ["write_provenance_sidecar", "get_provenance_record"]),
        ("Save an analysis as a reusable workflow", "dataset", [], ["save_workflow_preset", "export_workflow_file"]),
        ("Write a workflow report for a methods section", "report", [], ["write_workflow_report", "generate_spatial_report"]),
        ("Describe a dataset with title, abstract and licence", "dataset", [], ["get_layer_metadata", "set_layer_metadata"]),
    ]),
    ("50", "real_estate", "Real estate: site comparison and context", [
        ("Compare candidate sites by catchment population", "analysis", ["threshold", "population_src"], ["buffer_analysis", "calculate_service_area", "estimate_population_exposure"]),
        ("Rank candidate sites with weighted criteria", "analysis", [], ["calculate_mcda_ranking", "weighted_overlay_analysis"]),
        ("Map the amenities around a candidate site", "layer", ["aoi", "facility_type"], ["fetch_osm_features", "find_nearest_features"]),
        ("Build a neighbourhood dashboard for a site", "dashboard", ["aoi"], ["geocode_batch", "fetch_osm_features", "generate_html_dashboard"]),
    ]),
]


def build():
    """(register list, {persona id: [task ids]}) as they should be on disk."""
    with open(REGISTER, encoding="utf-8") as fh:
        old = json.load(fh)
    keep = [e for e in old if int(e["cat"].rstrip("abcdefghijklmnopqrstuvwxyz") or 0) < 38]
    for e in keep:
        e["persona"] = ["engineering"] if e["cat"] == "36" else ["humanitarian"]
    ids = {}
    for number, persona, cname, tasks in SECTIONS:
        for position, (text, out, slots, tools) in enumerate(tasks, 1):
            task_id = f"{number}.{position:02d}"
            keep.append({"id": task_id, "cat": number, "cname": cname, "text": text, "out": out, "slots": slots, "tools": tools,
                         "kw": sorted(task_matcher._tokens(text)), "persona": [persona]})
            ids.setdefault(persona, []).append(task_id)
    ids["engineering"] = ["36.01"] + ids["engineering"]
    return derive_task_io.derive(keep), ids


def _dump(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    register, ids = build()
    changed = []
    with open(REGISTER, encoding="utf-8") as fh:
        before = fh.read()
    after = _dump(register)
    if before != after:
        changed.append(REGISTER)
    for persona, task_ids in ids.items():
        path = os.path.join(PERSONA_DIR, persona + ".json")
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        data = json.loads(raw)
        if data["task_ids"] != task_ids:
            data["task_ids"] = task_ids
            new_raw = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
            changed.append(path)
            if not args.check:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(new_raw)
    if changed and not args.check:
        with open(REGISTER, "w", encoding="utf-8") as fh:
            fh.write(after)
    print("would change:" if args.check else "changed:", [os.path.relpath(c, ROOT) for c in changed] or "nothing")
    return 1 if (args.check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
