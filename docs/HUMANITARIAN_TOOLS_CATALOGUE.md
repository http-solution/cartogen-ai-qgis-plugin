# Humanitarian tools catalogue

Every tool Cartogen AI offers for humanitarian work, organised by the six workflows in the "Humanitarian Mapping Workflows" document (field operations first, then strategic orchestration), with what each tool produces on the map and how to get better results from it. Companion to the generated parameter reference [`TOOLS_REFERENCE.md`](TOOLS_REFERENCE.md) (exact arguments) and the gap analysis [`HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md`](HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md) (what is still missing).

**Honesty notes.** This is a static description written from the code and tool descriptions, dated 2026-10-04. "Map output" says what the tool draws; a tool marked *no automatic style* leaves QGIS's default look and you can ask for `apply_graduated_style` / `apply_categorized_style` afterwards. Nothing here was hand-tested in a live QGIS session; the QGIS-side behaviour is covered by CI tests on QGIS 4.2.2 where the tool's entry says so. Tools that produce estimates say so, and you should repeat that wording in reports. The tools do not choose thresholds, weights or survey designs for you: where a number is a judgement (trigger threshold, criteria weights, design effect, minimum cell size) the tool asks for it.

**How to prompt well, in general.** Name the layers exactly as they appear in the project. Say the unit you mean (minutes or hours of travel, metres, people or households). Give weights, thresholds and dates yourself rather than asking for "reasonable" ones. Say which end of a scale is worse. Ask for the assumptions to be listed in the answer. For anything that is a count of people, ask for the wording "estimated".

---

## Phase I -- Operational and field mapping

### Workflow 1. Rapid crisis and base mapping

**The workflow.** Build or refresh the base geography of an affected area (boundaries, roads, buildings, facilities), assess damage, and organise remote mappers.
**Outputs.** Base map layers, damage and change layers, a mapping-task grid.
**Supporting data sources.** HDX / OCHA COD-AB, geoBoundaries, OpenStreetMap (Overpass, Geofabrik extracts), Microsoft building footprints, Sentinel-2 via STAC.

### `search_hdx_datasets`
Search the Humanitarian Data Exchange by keyword. **Map output:** none (a list of datasets). **Better results:** search with the place and the theme ("Yemen health facilities", "Sudan flood extent"), then ask for the specific dataset to be downloaded or loaded; check the dataset's date and licence yourself.

### `fetch_hdx_admin_boundaries`
Downloads OCHA COD-AB administrative boundaries with real P-codes. **Map output:** pale-fill backdrop with a grey outline, name labels when there are few enough areas, ordered under points and lines. **Better results:** use this rather than `fetch_geoboundaries` whenever you will join data by P-code; pass the reported `pcode_field` to the severity and presence-gap tools. A large file asks for confirmation before download.

### `fetch_geoboundaries`
Administrative boundaries from geoBoundaries (broader coverage, no P-codes). **Map output:** same backdrop styling as above. **Better results:** use as a fallback when COD-AB does not exist for the country; join by name only with care (spelling variants break joins).

### `fetch_osm_features` / `ingest_osm_features`
Overpass queries for OSM features (`key`, `value`, bounding box or centre and radius); `ingest_osm_features` adds the result as a layer. **Map output:** *no automatic style* for most results (QGIS default colour). **Better results:** give a tight bounding box; combine values with `|` (`hospital|clinic|doctors`); ask for roads separately from facilities; for a road network to route on, request highways and then run `estimate_road_speeds`.

### `fetch_building_footprints`
Microsoft Global ML Building Footprints for an area. **Map output:** *no automatic style*. **Better results:** use a small bounding box; remember the dataset can lag real conditions by months, so it is a baseline, not a damage assessment.

### `search_stac_satellite_imagery`
Finds Sentinel-2 scenes (Earth Search STAC) by bounding box and dates. **Map output:** none (scene list). **Better results:** give a before and an after date range and a low-cloud requirement; the tool lists scenes, it does not judge usability.

### `calculate_raster_change_detection`
Pixel-wise after-minus-before difference of two rasters. **Map output:** a diverging ramp symmetric about zero -- blue = decrease, red = increase, no change transparent -- drawn under the vector layers. **Better results:** use two rasters of the same sensor, band, resolution and CRS; co-registration and clouds are your responsibility.

### `calculate_damage_exposure_severity`
Per-admin-unit damage score combining the change raster, building counts and an optional hazard-intensity raster; reports buildings in the high-severity units. **Map output:** values on the admin layer (`output_field`); *no automatic style* -- follow with `apply_graduated_style`. **Better results:** supply the before/after pair, the footprints layer and the admin layer with a P-code or name field; state it is a rapid indicative assessment, not a field-verified count.

### `extract_features_from_imagery`
Segments object outlines from a raster you loaded (FastSAM, local, offline once the model is downloaded). **Map output:** polygons, *no automatic style*. **Better results:** use a clear, high-resolution image; the tool finds outlines, never identities -- do not call a polygon "a building" unless you know it is.

### `add_incident_point` / `add_point_layer`
Plot one incident, or a list of named points, from real verified coordinates. **Map output:** incidents: red marker with a red label on a shared Incidents layer; named point layers: consistent point look with labels. **Better results:** give coordinates and dates you have verified; set `severity` / `event_type` (ACLED-style) so a later categorized style can tell incidents apart; use `add_point_layer` for more than one point.

### `generate_mapping_task_grid` -- new (H2)
Splits an area into square mapping tasks for remote or crowd mapping, clipped to the area, optionally ranked High / Medium / Low by a point count (damage reports, buildings) or a population raster; can write GeoJSON. **Map output:** task polygons coloured by priority (dark red High, orange Medium, pale Low, grey for unranked) with task ids as labels on small grids; an unranked grid is a neutral outline. **Better results:** choose a cell size that one mapper can finish (500-2000 m for dense areas); pass a damage or building layer as the priority basis so the worst-hit cells are mapped first; check the GeoJSON against your Tasking Manager's import rules (not verified here).

---

### Workflow 2. Multi-sectoral needs assessment (MSNA) and field data collection

**The workflow.** Design a statistically defensible sample, collect household data, and turn it into figures per area.
**Outputs.** Sample sizes and draws, population baselines, weighted indicators per area.
**Supporting data sources.** KoboToolbox / ODK exports (as CSV/XLSX), WorldPop, REACH/IMPACT datasets via HDX.

### `design_sampling_frame` -- new (H3)
Per-stratum sample sizes for a single proportion (confidence, margin of error, expected proportion, design effect, finite-population correction, non-response) and a reproducible draw from a candidate-units layer or as random points per stratum. **Map output:** sample points, one colour per stratum. **Better results:** give the survey designer's design effect for cluster samples (the default of 1 is only valid for simple random sampling); supply a layer of dwellings or settlements so points are real units, not random locations; keep the returned seed with your methodology note; use `plan_only` first to see the sample sizes.

### `fetch_worldpop_population`
WorldPop gridded population (about 100 m) clipped to your area. **Map output:** a heavy-tailed warm ramp with zero cells transparent, placed under the vector layers. **Better results:** always pass an `extent_layer` or `bbox`; whole-country downloads are refused unless you confirm; the figures are modelled estimates -- say "estimated".

### `estimate_population_exposure`
Sums a population raster inside each polygon (one total per zone, on a detached copy: the polygon layer is not modified; overlapping zones are summed separately and the overlap is reported). **Map output:** values on the polygon layer; *no automatic style*. **Better results:** build the exposure polygon first (buffer, flood extent, service area) and say "estimated population within".

### `load_tabular_data_as_layer`
Loads a CSV/XLSX in full as a layer, with coordinate or WKT columns where present. **Map output:** points get one consistent look and name labels on small layers. **Better results:** name the X/Y columns if the file's headings are unusual; check the reported CRS.

### `extract_pdf_tables` / `extract_word_tables` / `aggregate_data`
Pull tables out of reports and group-summarise rows. **Map output:** none. **Better results:** give the page for PDFs; check the extracted columns before aggregating.

### `aggregate_survey_indicator` -- new (H6)
Weighted share of "yes" answers or weighted mean per area, with confidence intervals; groups below a minimum number of respondents are suppressed. **Map output:** a results table (optional); join it to admin polygons with `join_by_attribute` to map it. **Better results:** pass the survey's own weight field; say which answers count as "yes" (`positive_values`); supply the design effect for cluster surveys (intervals otherwise ignore clustering); set `min_n` from your data-protection policy (30 is only a rule of thumb); never infer a suppressed group from totals.

---

### Workflow 3. Logistics, route planning and catchment analysis

**The workflow.** Put the physical constraints into a road network and measure who can reach what.
**Outputs.** Reach polygons, travel-time layers, access classes, route layers, siting rankings.
**Supporting data sources.** OSM roads, HDX road status layers, Logistics Cluster layers (not fetched automatically).

### `estimate_road_speeds`
Writes an assumed speed per road class. **Map output:** a field, no style. **Better results:** use only when the network has little real speed data; state that it is an assumption.

### `build_composite_impedance_field`
Blends road class, surface, optional passability and optional slope into one km/h field. **Map output:** a field. **Better results:** run it before routing and pass its output as `speed_field` with `strategy='fastest'`; supply a 0-1 damage/passability field if you have a road assessment.

### `apply_network_barriers` -- new (H1)
Blocks or slows road segments near destroyed bridges, checkpoints or flood extents (points, lines or polygons) and writes a speed field. **Map output:** the affected segments are drawn as a separate layer `<roads>_barrier_affected`, thick red when blocked, orange when slowed; your road layer is not restyled. **Better results:** pass `speed_field` from `build_composite_impedance_field` so unaffected roads keep realistic speeds; remember `strategy='shortest'` ignores the field and "block" is a near-zero speed, not a closure; pick `buffer_m` to match the barrier's real footprint.

### `calculate_service_area`
Reachable road network and approximate coverage polygon within a distance or time. **Map output:** roads graded in five cost bands (dark near, warm far) and a reach polygon, with the plain network hidden. **Better results:** use a real line layer with a speed field; ask for `strategy='fastest'` for time; read the polygon as an approximation (a hull around the reached roads).

### `classify_facilities_by_access`
Labels each facility within or beyond a travel cost of an origin, using one service area (fast). **Map output:** points coloured within/beyond, "beyond" drawn larger and on top, labelled when the layer is small. **Better results:** use it instead of `travel_time_matrix` for any "within / beyond N hours" question over many facilities; state its snapping approximation.

### `travel_time_matrix`
Road distance or time from each origin to each destination. **Map output:** none (a matrix). **Better results:** keep origins and destinations few; large sets are slow.

### `population_access_gap`
People and percentage beyond a travel distance or time of the nearest facility. **Map output:** three reach figures with distinct translucent fills in one group; the headline figure visible, the others hidden. **Better results:** supply an area layer, a population raster and a speed field; quote the figure as an estimate and say which reach figure it used.

### `optimal_hub_siting` / `location_allocation`
Rank candidate hubs, or choose the best combination of N sites, by distance to demand points (ellipsoidal distances). **Map output:** rankings in the result; *no automatic style*. **Better results:** give demand weights (`weight_field`) such as population; remember these are straight-line distances -- use the service-area tools for road reach.

### `optimize_delivery_route`
Visiting order for stops, and a road-snapped route line when a network is given. **Map output:** route line in the route-line style. **Better results:** always pass the road network; do not present a straight line as a route.

### `score_route_incident_risk`
Counts and distances of incidents near a route, optionally recent or severity-weighted. **Map output:** a translucent orange risk corridor. **Better results:** pass dates and a recency window; weight by severity if you have it; it counts nearby incidents, it does not predict risk.

---

## Phase II -- Strategic decision-making and donor orchestration

### Workflow 4. Intersectoral severity mapping (JIAF-style)

**The workflow.** Overlay vulnerabilities per admin unit into a composite severity score and class.
**Outputs.** A severity layer, hotspot surfaces, coverage-gap lists.
**Supporting data sources.** IPC, ACLED and 3W/4W tables (loaded as files; no automatic IPC or ACLED download).

### `calculate_severity_index`
Min-max normalised, weighted composite score and a 1-5 class per unit. **Map output:** an optional score field; *no automatic style* -- follow with `apply_graduated_style` on the score. **Better results:** state the weights and which indicators are "higher is better" (`invert_indicators`); report excluded units. It is JIAF/INFORM-**style**, not the JIAF method.

### `calculate_presence_gap` / `load_3w_data`
Cross-reference high-severity units with 3W/4W presence. **Map output:** an optional status field (gap / covered / unmatched); *no automatic style* -- follow with `apply_categorized_style`. **Better results:** join by P-code, not name; look at the "unmatched" list before concluding a gap.

### `calculate_population_in_need`
Population in the high-severity classes using a population raster. **Map output:** an optional field; *no automatic style*. **Better results:** quote as an estimate and give the severity classes counted.

### `hotspot_analysis`
Kernel density surface of a point layer. **Map output:** warm density ramp, transparent where empty. **Better results:** choose the radius to match the question; weight by severity if relevant.

### `analyze_incident_trend` / `forecast_trend`
Is incident density rising or falling per zone; linear projection of a numeric field. **Map output:** none. **Better results:** supply at least three periods; present results as projections with the stated fit.

---

### Workflow 5. Donor resource allocation and prioritisation

**The workflow.** Combine severity with funding and access to find where need is critical and support is thin.
**Outputs.** Ranked priorities, coverage tables, funding snapshots.
**Supporting data sources.** FTS, INFORM (as files).

### `calculate_mcda_ranking` -- new (H5)
Weighted multi-criteria ranking of areas, each criterion with a weight and a priority direction, plus a test of how much the ranking depends on the weights. **Map output:** optional `<prefix>_score`, `_rank`, `_rank_min`, `_rank_max` fields; *no automatic style* -- follow with `apply_graduated_style` on the score or rank. **Better results:** give the weights yourself; say for each criterion whether a high or low value gets priority; use `top_k` to see which areas stay in the top group; treat areas whose best and worst rank differ widely as weight-dependent, not firm.

### `fetch_fts_funding_data`
Plan-level requirements, funding received and gap from FTS. **Map output:** none; it is not geographic. **Better results:** name the plan year; quote it as a snapshot.

### `generate_sector_coverage_report`
"Reached versus target" table and bar chart by sector or admin unit. **Map output:** a chart image. **Better results:** include a target column; missing targets sort with the worst performers deliberately.

### `weighted_overlay_analysis`
Weighted sum of already-normalised rasters (suitability or risk surface). **Map output:** *no automatic style*. **Better results:** normalise inputs to a common scale first; share CRS and extent.

---

### Workflow 6. Anticipatory action and forecast-based financing

**The workflow.** Compare forecasts with pre-agreed triggers and watch live hazards.
**Outputs.** Which areas meet a trigger, hazard layers, dashboards, scheduled change summaries.
**Supporting data sources.** GDACS, NASA EONET, NASA FIRMS (needs a free key), your own forecast tables (GloFAS and rainfall are not fetched automatically).

### `evaluate_forecast_trigger` -- new (H4)
Applies your threshold, lead window and probability cut-off to forecast rows already in a layer or table and reports activated areas. **Map output:** none (a table and the rule in words). **Better results:** give the threshold, comparison, lead days and probability from your trigger protocol -- the tool has no defaults; include a date and a unit field; check `rows_skipped`.

### `fetch_gdacs_disaster_alerts` / `fetch_nasa_eonet_events` / `fetch_nasa_active_fires`
Live hazard layers. **Map output:** GDACS points coloured Red / Orange / Green (with a grey "other"); EONET points coloured by event category; fires as small orange dots. Styled when the layer is first created, so a refresh keeps any restyling you did. **Better results:** pass a bounding box as `[min_lon, min_lat, max_lon, max_lat]`; GDACS alerts "may require further validation" -- do not act on one without confirmation.

### `generate_situation_dashboard`
Fetches the three hazard feeds for a box and writes one HTML dashboard. **Map output:** an interactive web map (needs internet to view). **Better results:** give a tight box and a title.

### `run_monitoring_workflow` / `schedule_recurring_workflow` / `stop_recurring_workflow` / `list_scheduled_workflows`
Re-run a saved set of read-only analyses and report what changed; schedule it while QGIS is open. **Map output:** change summaries in chat. **Better results:** save the preset first; remember schedules stop when QGIS closes.

---

## Cross-cutting tools

### Data quality and governance
`check_pcode_uniqueness`, `check_pcode_hierarchy`, `validate_schema` / `list_schema_contracts`, `get_dataset_status` / `set_dataset_status` / `advance_dataset_status`, `get_provenance_record` / `write_provenance_sidecar`, `set_layer_sensitivity` / `get_layer_sensitivity`, `generate_map_product_qa_checklist`. **Map output:** none. **Better results:** run the P-code checks before any join; advance a layer's status only after the checks pass; tag sensitive layers before exporting or using a cloud model.

### Reporting and products
`generate_chart`, `generate_html_dashboard`, `generate_temporal_dashboard`, `generate_spatial_report`, `generate_report`. **Map output:** charts, interactive HTML maps, Word and Markdown reports. **Better results:** use the HTML dashboard for non-GIS audiences; pass `source_layers` to reports so provenance is included.

### Engineering hydrology
`parse_dms_location`, `assess_watershed_hydrology_request`, `calculate_rational_watershed_peak_flow`. **Map output:** none. **Better results:** supply measured basin area, flow length, elevations and a cited local rainfall intensity; the tools refuse to invent them.

---

## Map styling review

What each tool's map output looked like before this review, and now. "Default" means QGIS's raw random single-colour or unstretched look.

| Tool | Layer it creates | Before the review | Now |
|---|---|---|---|
| `generate_mapping_task_grid` | task polygons | default colour | priority colours, task-id labels |
| `apply_network_barriers` | speed field only | nothing visible | separate red / orange layer of affected segments |
| `design_sampling_frame` | sample points | default colour | one colour per stratum |
| `fetch_gdacs_disaster_alerts` | alert points | default colour | Red / Orange / Green plus "other" |
| `fetch_nasa_eonet_events` | event points | default colour | colour per category plus "other" |
| `fetch_nasa_active_fires` | fire points | default colour | small orange dots |
| `calculate_raster_change_detection` | difference raster | unstretched grey | diverging blue-white-red, zero transparent |
| `calculate_service_area`, `classify_facilities_by_access`, `population_access_gap`, `score_route_incident_risk`, `optimize_delivery_route` | routing layers | already styled (cost bands, within/beyond, reach figures, risk corridor, route line) | unchanged |
| `fetch_worldpop_population`, `hotspot_analysis` | rasters | already styled | unchanged |
| `fetch_hdx_admin_boundaries`, `fetch_geoboundaries` | boundaries | already a pale backdrop with labels | unchanged |
| `add_incident_point`, `add_point_layer`, `load_tabular_data_as_layer` | points | already styled | unchanged |

**Still not automatically styled (a deliberate or open gap).**
- `calculate_severity_index`, `calculate_presence_gap`, `calculate_population_in_need`, `calculate_damage_exposure_severity`, `calculate_mcda_ranking` write fields onto *your* layer; they do not restyle it, because that layer is yours. Ask for `apply_graduated_style` (scores, ranks) or `apply_categorized_style` (gap status) as the next step.
- `fetch_osm_features` / `ingest_osm_features`, `fetch_building_footprints`, `extract_features_from_imagery`, `weighted_overlay_analysis`: default look; open gap, listed in the implementation tracker.
- `evaluate_forecast_trigger` and `aggregate_survey_indicator` produce tables, not map layers; join their results to admin polygons to map them.

**Verification.** The pure parts (palettes, ordering) are unit tested offline. The QGIS styling code has live tests (`tests/test_humanitarian_style_live.py`) that were written without a local QGIS; their first execution is CI, and none of the looks has been seen on a real canvas.
