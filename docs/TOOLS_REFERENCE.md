# Tool Reference

Auto-generated from the live tool registry (180 tools) by `docs/generate_tools_reference.py` -- do not hand-edit, regenerate instead so this can never drift from the actual code.

Flags: **network-only** tools bypass the main-thread QGIS dispatcher entirely (pure HTTP, safe from any background thread); **two-phase** tools split a network fetch (background thread) from the QGIS-touching part (main thread); **task-management** tools are excluded from auto-advance in the Task Manager.

## AI Imagery Feature Extraction

### `extract_features_from_imagery`

Extract object boundary polygons from a loaded raster using a class-agnostic segmentation model (FastSAM) -- for a specific image the user actually has (a fresh drone/satellite photo, a scanned map), NOT for pre-vetted baseline data (use fetch_building_footprints for that instead, which is faster and free but can lag real conditions by months). Runs entirely locally/offline once the model is downloaded -- no cloud vision API call, matching this plugin's offline-first posture. IMPORTANT: this tool is class-agnostic -- it finds object BOUNDARIES, never object IDENTITIES. Never describe a result polygon as a specific class ('this is a building') unless the user's own request already established that framing for the whole image; state plainly that these are detected boundaries with a confidence score, not classified objects. Requires the raster's pixel dimensions to be at most max_pixel_dimension -- clip to a smaller area of interest first for a large image rather than expecting this tool to silently downsample it for you. Requires the optional `ultralytics` package (installs a real ML runtime plus a ~150MB+ model checkpoint on first use) -- install via qpip if prompted, or manually in the OSGeo4W Shell.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `raster_layer` | string | yes | An already-loaded raster layer to extract features from. |
| `output_layer_name` | string | no | Name for the resulting polygon layer. Defaults to '{raster_layer}_extracted_features'. |
| `min_area_m2` | number | no | Optional: drop detected features smaller than this real-world area (square meters) -- SAM-family 'segment everything' mode reliably produces noise-scale false positives worth filtering out. |
| `confidence_threshold` | number | no | Minimum model confidence (0-1) to keep a detected feature. Defaults to 0.4. |
| `max_pixel_dimension` | integer | no | Hard cap on the raster's width/height in pixels. Defaults to 2048 -- larger rasters are rejected with an error asking you to clip first, rather than silently downsampled. |

## Data Analysis & Prediction

### `analyze_incident_trend`

Is incident density in each zone rising or falling over time -- e.g. security incidents by district over the last few months. hotspot_analysis answers 'where is density high right now' (a single snapshot); this answers 'is it getting worse here.' A thin composite, not a new statistic: buckets point_layer's incidents into period_days-sized time periods per zone_layer feature, then feeds each zone's (period, count) series into the same _forecast_series/_linear_regression math forecast_trend already uses -- so results carry the same fit_confidence/trend_direction framing, and the same 'present as a projection, not a certain fact' rule applies. Needs at least 3 time periods of data to fit a trend (i.e. the date range in point_layer must span at least 3x period_days) -- returns a clear error naming how much data is actually available if not. A zone with zero incidents in every period is a valid, confidently-flat result, not an error.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `point_layer` | string | yes | Point layer of incidents, e.g. the shared 'Incidents' layer from add_incident_point. |
| `date_field` | string | yes | Date field on point_layer. |
| `zone_layer` | string | yes | Polygon layer of zones to analyze per-zone trend within (e.g. districts, or a hand-drawn area of interest). |
| `zone_name_field` | string | yes | Field on zone_layer holding each zone's name. |
| `period_days` | integer | no | Size of each time bucket in days. Defaults to 30. |
| `periods_ahead` | integer | no | How many future periods to project per zone. Defaults to 1. |

### `calculate_damage_exposure_severity`

Composite post-crisis damage-and-exposure assessment, in the same thin-composite pattern as calculate_population_in_need: combines calculate_raster_change_detection's before/after pixel diff with fetch_building_footprints' building counts (and, optionally, a user-supplied hazard-intensity raster -- e.g. a shake-intensity or flood-depth layer) into one severity score per admin unit, plus a total building count in the high-severity units. Inspired by UNDP RAPIDA's rapid post-crisis assessment approach, deliberately scoped down to what's actually available here -- no seismic/hazard modeling, no social-media/night-light signal ingestion (see docs/archive/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md B.3 for that gap; this tool doesn't close it, just narrows it). Change magnitude is the MEAN absolute pixel difference within each unit, not the raw sum, which would just scale with unit area/pixel count. Building exposure counts footprint centroids falling within each unit -- units the change-detection raster doesn't cover are excluded from the severity index (never imputed as zero), matching calculate_severity_index's own rule; units with genuinely zero buildings still get a real 0, since that's an actual count, not missing data. Pass output_field to write each unit's severity score back to the layer for apply_graduated_style. Never hand-write this composition via execute_pyqgis_script -- use this tool.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `admin_layer` | string | yes | Polygon layer of admin units. |
| `unit_name_field` | string | yes | Field holding each unit's name/P-code. |
| `raster_before` | string | yes | Pre-event raster layer (see calculate_raster_change_detection). |
| `raster_after` | string | yes | Post-event raster layer. |
| `building_footprints_layer` | string | yes | Building footprint polygon layer, e.g. from fetch_building_footprints. |
| `hazard_intensity_raster` | string | no | Optional hazard-intensity raster (shake intensity, flood depth, etc.) to weight the severity score alongside raw change magnitude. |
| `high_severity_classes` | array[integer] | no | Severity classes (1-5) counted toward the exposed-building total. Defaults to [4, 5]. |
| `output_field` | string | no | Optional: write each unit's severity score back to the layer under this field name. |

### `calculate_population_in_need`

Combines calculate_severity_index's classification with population-per-pixel data to answer the number every HRP, donor brief, and allocation committee actually quotes -- 'X people in need in District Y', not just 'District Y is severity class 5'. Computes the severity index internally (same method and indicator handling as calculate_severity_index) from indicator fields already on a polygon layer, sums population within each admin unit via zonal statistics against an already-loaded population raster (same mechanism as estimate_population_exposure, which this calls internally -- e.g. a layer from fetch_worldpop_population), and reports a population_in_need total for the high-severity classes plus a population breakdown per severity class. Closes a gap where getting this number previously required manually chaining calculate_severity_index and estimate_population_exposure and matching the two up by hand -- easy to get subtly wrong (double-counting, or forgetting to exclude units calculate_severity_index itself flagged as missing data). Units excluded from severity scoring (missing indicator data) are excluded from the total, not silently counted as needy or safe -- same for units the population raster doesn't cover (no pop_sum value), listed separately rather than treated as zero population. Pass output_field to write each unit's population figure back to the layer, then style it directly with apply_graduated_style. Results are capped to 50 units (see unit_results_total/truncated) -- output_field still writes every unit's figure to the layer regardless of the cap.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Polygon layer of admin units with severity indicator fields. |
| `indicator_fields` | array[string] | yes | Numeric indicator fields to combine into the severity score. |
| `unit_name_field` | string | yes | Field on the polygon layer holding each unit's name/P-code. |
| `population_raster_layer` | string | yes | A population-per-pixel raster layer already loaded (e.g. from fetch_worldpop_population). |
| `weights` | object | no | Optional {indicator_field: weight} for the severity score. Defaults to equal. |
| `invert_indicators` | array[string] | no | Indicator fields where a HIGHER raw value means a BETTER situation. |
| `high_severity_classes` | array[integer] | no | Severity classes (1-5) counted toward the population_in_need total. Defaults to [4, 5]. |
| `output_field` | string | no | Optional: write each unit's population figure back to the layer under this field name. |

### `calculate_presence_gap`

Cross-reference a computed severity/needs index (see calculate_severity_index) against 3W/4W ('who does what where') operational-presence data to find admin units with HIGH severity but LOW or NO organizational presence -- the classic humanitarian coverage-gap question for targeting where a response is most under-resourced relative to need. Computes the severity index internally (same method and indicator handling as calculate_severity_index) from indicator fields already on a polygon layer, reads the 3W/4W file, and joins the two by admin unit name (case/whitespace-insensitive match). High-severity units with no match at all in the 3W data are reported separately as unmatched, since that could mean genuinely zero presence or just a name mismatch between the two datasets -- don't treat it the same as a confirmed zero. Pass output_field to write each high-severity unit's status ('gap'/'covered'/'unmatched') back to the layer, then style it directly with apply_categorized_style or place it on generate_html_dashboard -- do NOT hand-write PyQGIS renderer code for this via execute_pyqgis_script, use output_field plus the existing styling tools instead. Each of the three result lists is capped to 50 entries (see the matching _total fields and truncated) -- output_field still writes every classified unit's status to the layer regardless of the cap.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Polygon layer of admin units with severity indicator fields. |
| `indicator_fields` | array[string] | yes | Numeric indicator fields to combine into the severity score. |
| `unit_name_field` | string | yes | Field on the polygon layer holding each unit's name/P-code. |
| `presence_file_path` | string | yes | Absolute path to the 3W/4W .csv/.xlsx/.xls file. |
| `presence_admin_field` | string | yes | Column in the 3W/4W file holding the admin unit name/P-code. |
| `presence_org_field` | string | yes | Column in the 3W/4W file holding the organization name. |
| `weights` | object | no | Optional {indicator_field: weight} for the severity score. Defaults to equal. |
| `invert_indicators` | array[string] | no | Indicator fields where a HIGHER raw value means a BETTER situation. |
| `high_severity_classes` | array[integer] | no | Severity classes (1-5) counted as 'high need'. Defaults to [4, 5]. |
| `low_presence_threshold` | integer | no | Organization count strictly below this counts as a presence gap. Defaults to 1 (i.e. zero organizations). |
| `sheet_name` | string | no | Sheet name if presence_file_path is a multi-sheet Excel file. |
| `delimiter` | string | no | CSV delimiter for presence_file_path. Defaults to ','. |
| `output_field` | string | no | Optional: write each high-severity unit's presence-gap status ('gap'/'covered'/'unmatched') back to the layer under this field name. |

### `calculate_severity_index`

Build a composite multi-indicator severity/needs index across admin units (JIAF/INFORM-style), the standard basis for prioritizing which areas receive funding. Takes several numeric indicator fields already on a polygon layer's attribute table (e.g. food insecurity %, displacement %, protection incidents, WASH coverage), min-max normalizes each so higher always means worse, applies relative weights, and returns a 0-1 composite score plus a 1-5 severity class per unit, ranked worst-first. Use invert_indicators for fields where a HIGHER value means a BETTER situation (e.g. % with water access) -- otherwise well-served areas score as high-severity. Units missing any indicator are excluded and listed, never imputed. Always report the weights and any excluded units alongside the ranking, since both change how it should be read. Results are capped to the worst 50 units (see truncated/scored_units) -- output_field still writes the score for every unit to the layer regardless of the cap, so styling/mapping the full set is unaffected; only the returned JSON is capped.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Polygon layer of admin units. |
| `indicator_fields` | array[string] | yes | Numeric indicator fields to combine. |
| `unit_name_field` | string | yes | Field holding each unit's name/P-code, used to label results. |
| `weights` | object | no | Optional {field: weight}; defaults to equal. Normalized to sum to 1, so these are relative. |
| `invert_indicators` | array[string] | no | Indicator fields where a HIGHER raw value means a BETTER situation. |
| `output_field` | string | no | Optional: write the composite score back to the layer under this field name. |

### `forecast_trend`

Project a simple linear trend forward from historical numeric data already in a layer's attribute table (e.g. case counts, incident counts, or any numeric field over time). Returns a mathematical trend projection with a stated fit confidence -- NOT a certain prediction; always present it as a projection, not a fact. Optionally group by a categorical field to get one forecast per group (e.g. one per district) instead of a single overall forecast.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `date_field` | string | yes | Field holding the date/time of each observation. |
| `value_field` | string | yes | Numeric field to forecast. |
| `periods_ahead` | integer | no | How many future points to project. Defaults to 3. |
| `group_by_field` | string | no | Optional categorical field -- returns one forecast per distinct value instead of one overall forecast. |

## Database & Workflows

### `execute_read_only_sql`

Execute a read-only SQL query against a named PostGIS connection or active project layers.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `connection_name` | string | no |  |
| `sql_query` | string | yes |  |

### `load_workflow_preset`

Load a saved workflow preset JSON by name.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `preset_name` | string | yes |  |

### `save_workflow_preset`

Save an agent plan as a re-usable JSON workflow preset. To build a recurring monitoring workflow (see run_monitoring_workflow/schedule_recurring_workflow), save workflow_json in the shape '{"steps": [{"tool": "calculate_severity_index", "args": {...}}, ...]}' -- an ordered list of read-only analysis tool calls to re-run and diff over time.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `preset_name` | string | yes |  |
| `workflow_json` | string | yes |  |

## Export & Reporting

### `export_layer`

Export vector layer to file format (ESRI Shapefile, GeoJSON, GPKG, KML).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `format` | string | yes |  |
| `output_path` | string | no |  |
| `only_selected` | boolean | no |  |

### `export_temporal_animation_frames`

Render one PNG frame per time step from a layer with start/end period fields already in the project -- e.g. control-area polygons over 2016-2026 -- by filtering the layer to each frame's date and exporting the current map canvas view, so the frames can be assembled into a GIF/video outside QGIS (e.g. with ffmpeg) for a native, non-HTML animation. This is the QGIS-native sibling of generate_temporal_dashboard's HTML output -- use this one when a video/GIF file is wanted instead of (or in addition to) a shareable web page. The canvas view/extent is NOT changed between frames (so the animation doesn't visually jump) -- pan/zoom to the desired extent yourself before calling this. Optionally applies a categorized style once via category_field before rendering frames. The layer's filter is restored to what it was before the call once done, even on failure.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `start_field` | string | yes | Date/text field holding when each feature's period began. |
| `end_field` | string | no | Optional date/text field holding when the period ended. A feature with no value here stays visible from its start onward. |
| `category_field` | string | no | Optional field to categorize/color the layer by (e.g. controlling faction) before rendering frames -- applied once via apply_categorized_style. |
| `output_dir` | string | no | Directory to write frame_0001.png, frame_0002.png, etc. Defaults to a new temp directory. |
| `step_days` | integer | no | Days between frames. Defaults to 30. |

### `export_to_csv`

Export layer attribute table to CSV file. output_path is optional -- omit it to save under the project's data/20_processed folder (or the QGIS profile folder if the project isn't saved yet), under a clean, sanitized file name derived from the layer's own name. Never prompts interactively. If features are selected on the layer, only selected features are exported by default. Point layers get X and Y columns (in the layer's CRS) instead of a WKT column unless wkt_geometry is true; the file is UTF-8 with a BOM so Excel shows non-ASCII names correctly.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `output_path` | string | no |  |
| `only_selected` | boolean | no |  |
| `wkt_geometry` | boolean | no | Point layers only: write a WKT geometry column instead of X/Y columns. |

### `generate_html_dashboard`

Generate an interactive HTML situation dashboard (Leaflet/Folium map with layer toggles and popups) from one or more vector layers already in the project -- e.g. a severity-index layer plus facility points plus admin boundaries, click-to-inspect the indicator values behind a severity score. This is the highest-visibility deliverable for a non-QGIS audience (fund-allocation committees, donors) -- prefer it over a static print layout/report when the audience will interact with the map themselves. The viewer needs internet access at view time (see the result's connectivity_note for the exact wording to relay). Each layer is reprojected to WGS84 automatically. Vector layers only -- not for raster layers. Optionally pass color_field per layer (e.g. a severity score field) to choropleth-color it. IMPORTANT: always pass popup_labels for any field whose raw name isn't already plain language (e.g. abbreviated or coded field names like 'food_insec_pct', 'wash_depriv_pct') -- give each one a real human-readable label (e.g. 'Food Insecurity (IPC 3+) %', 'WASH Service Deprivation %') using your own knowledge of what the field means. Fields left unlabeled fall back to a purely mechanical Title Case of the raw name (e.g. 'food_insec_pct' -> 'Food Insec Pct'), which is not real language and should not be relied on for a field whose meaning you actually know.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layers` | array[object] | yes | One or more layers to include, each rendered as its own toggleable overlay. |
| `title` | string | no | Optional dashboard title, shown as a heading overlay on the map. |
| `output_path` | string | no | Where to save the HTML file. Defaults to a readable, timestamped file under the project's data/20_processed/dashboards folder. Tell the user the full path. |
| `basemap` | string | no | 'hot' (default, Humanitarian OSM Team style), 'satellite' (Esri World Imagery), or 'none' (no tiles: works offline, pair with backdrop_layer), or 'positron' / 'dark_matter' (Carto; these now need a Carto API key and may show no tiles). |
| `backdrop_layer` | string | no | Optional name of a polygon layer in the project (e.g. an administrative boundary) drawn under the data as a tile-free backdrop. Best with basemap='none'. |

### `generate_report`

Generate a Word (.docx) report document saved on Desktop. Optionally pass source_layers to append a 'Data Sources & Provenance' section -- what tool created/modified each layer, with what parameters and source layers, and when -- pulled from tracked lineage. Gives a report's audience (often not QGIS users, e.g. a fund-allocation committee) something to check a spatial claim against instead of just asserting it.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `title` | string | yes |  |
| `content` | string | yes |  |
| `source_layers` | array[string] | no | Optional layer names to append a provenance/lineage section for. |

### `generate_spatial_report`

Generate a markdown report to present insights in chat. Optionally pass source_layers to append a 'Data Sources & Provenance' section -- what tool created/modified each layer, with what parameters and source layers, and when -- pulled from tracked lineage. Gives a report's audience (often not QGIS users, e.g. a fund-allocation committee) something to check a spatial claim against instead of just asserting it.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `title` | string | yes |  |
| `insights` | string | yes |  |
| `source_layers` | array[string] | no | Optional layer names to append a provenance/lineage section for. |

### `generate_temporal_dashboard`

Generate an animated, time-sliding HTML dashboard (Leaflet/Folium) from one or more vector layers already in the project -- e.g. control-area polygons or incident points for several armed groups/factions over a multi-year period, each with its own period/date, plus a play/pause + date slider the viewer drags or plays through to watch status/control change over time. This is the temporal, reusable-for-any-multi-period-status-dataset sibling of generate_html_dashboard -- use THIS tool (not that one) whenever the data has a time dimension a viewer should be able to scrub through (e.g. 'from 2016 to 2026'), and generate_html_dashboard for a plain, non-animated situation map. At least one layer must set start_field. Give every temporal layer a category_field (e.g. the controlling faction/group name) so features are colored by category -- without it every feature in that layer gets the same color, which defeats the point of an animated status map. A layer with no start_field is rendered as an always-visible reference layer alongside the animated ones (e.g. a fixed country outline). Point-geometry layers (e.g. incidents) render as colored circle markers, not plain icons. Beyond the single-point-in-time slider, the dashboard also gets: a separate from/to date-range control that narrows what the slider ever shows and what the play button loops through; an automatic checkbox filter panel listing every distinct value of any layer's location_field (e.g. governorate/admin1 name), letting the viewer hide specific locations regardless of date; and, when any layer sets category_field, an automatic stacked bar chart (via Chart.js, from a CDN) showing how many status/control changes started in each calendar month, broken down by category and kept in sync with the location filter and date range -- modeled on a real reference dashboard the project owner shared (a Power BI conflict-monitoring report with a map, location filters, a date range, and a synced trend chart). Each layer is reprojected to WGS84 automatically. Vector layers only. The viewer needs internet access at view time (see the result's connectivity_note -- this is now true even for a dashboard with no chart, since Chart.js is always loaded). IMPORTANT: use your own knowledge of the data's field names to pass human-readable popup_labels for any coded/abbreviated field, exactly as for generate_html_dashboard. This tool never invents data of its own -- it only animates/charts whatever start_field/end_field/category_field/location_field values are actually present on the layer(s) you point it at.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layers` | array[object] | yes | One or more layers. At least one must set start_field. |
| `title` | string | no | Optional dashboard title, shown as a heading overlay on the map. |
| `output_path` | string | no | Where to save the HTML file. Defaults to a readable, timestamped file under the project's data/20_processed/dashboards folder. Tell the user the full path. |
| `step_days` | integer | no | Slider step size / play-button advance, in days. Defaults to 30. |
| `basemap` | string | no | 'hot' (default, Humanitarian OSM Team style), 'satellite' (Esri World Imagery), or 'none' (no tiles: works offline, pair with backdrop_layer), or 'positron' / 'dark_matter' (Carto; these now need a Carto API key and may show no tiles). |
| `backdrop_layer` | string | no | Optional name of a polygon layer in the project (e.g. an administrative boundary) drawn under the data as a tile-free backdrop. Best with basemap='none'. |

### `print_map`

Export current QGIS map canvas view to a PDF document or PNG/JPG image. output_path is optional -- if omitted, saves a PNG to Desktop without prompting.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `output_path` | string | no | Optional file path with .pdf, .png, or .jpg extension. If omitted, saves a PNG to Desktop. |

## Humanitarian Data (HDX / OSM / geoBoundaries)

### `add_incident_point`

Plot a single real-world incident/event as a labeled point on the map, using consistent professional styling (red marker, white-background/red-text label). Adds to a shared 'Incidents' layer, creating it on first use. Only ever call this with real, verified data -- if the coordinates or date aren't already known, use search_web/geocode_and_enrich to find them first; never invent placeholder values. Set severity when it's known (e.g. security incident classification) so apply_categorized_style/apply_graduated_symbol_style can later distinguish incident types on the map instead of every point looking identical. For conflict/security incidents, also set event_type (+ sub_event_type) using ACLED's controlled taxonomy when the source classification maps to it; for explosive-hazard incidents, set hazard_type (+ contamination_status) using the IMSMA/IMAS-style vocabulary. Both are optional and validated -- an unrecognized value comes back as a warning, not a rejected point. If the incident spans a period rather than one instant (e.g. a hazard active over days, a multi-day event), also set event_start/event_end alongside the existing date field -- additive, not a replacement, so date stays freeform for single-date sources. last_verified records when the data was last confirmed, separate from when the incident itself occurred.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `lat` | number | yes | Latitude in decimal degrees (WGS84). |
| `lon` | number | yes | Longitude in decimal degrees (WGS84). |
| `date` | string | yes | Real, verified date of the incident (e.g. '2026-03-14'). |
| `description` | string | yes | Short, factual description of the incident. |
| `severity` | string | no | Optional severity/category label, e.g. 'High', 'Security', 'Flood'. Free text -- use whatever classification the source data uses. |
| `event_type` | string | no | Optional ACLED-style controlled event type: one of ['Battles', 'Protests', 'Riots', 'Explosions/Remote violence', 'Violence against civilians', 'Strategic developments']. |
| `sub_event_type` | string | no | Optional ACLED-style sub-event type, valid within the chosen event_type. |
| `hazard_type` | string | no | Optional IMSMA/IMAS-style explosive-hazard type: one of ['Landmine - Anti-Personnel', 'Landmine - Anti-Vehicle', 'Unexploded Ordnance (UXO)', 'Abandoned Ordnance (AXO)', 'Improvised Explosive Device (IED)', 'Cluster Munition Remnant', 'Booby Trap']. |
| `contamination_status` | string | no | Optional IMSMA/IMAS-style contamination status: one of ['Confirmed Hazardous Area', 'Suspected Hazardous Area', 'Cleared']. |
| `event_start` | string | no | Optional ISO date (YYYY-MM-DD) the incident/hazard started, when it spans a period rather than one day. |
| `event_end` | string | no | Optional ISO date (YYYY-MM-DD) the incident/hazard ended, when it spans a period rather than one day. |
| `last_verified` | string | no | Optional ISO date (YYYY-MM-DD) this data was last confirmed accurate -- distinct from when the incident occurred. |

### `add_point_layer`

Create a new point layer (or append to an existing one with the same name) from a LIST of real, verified locations in a SINGLE call -- e.g. embassies, offices, facilities, or any set of named points of interest. Always prefer this over calling add_incident_point repeatedly when plotting more than one location -- one call per point will exhaust the agent's step limit on anything but a short list. Gather every location first (search_web/gemini_grounded_search/geocode_and_enrich), then call this once with the full list. Only ever use real, verified coordinates -- never invent placeholder values. Set category per point when it's known (e.g. incident severity/type) so apply_categorized_style can later distinguish them on the map. For conflict/security points, also set event_type (+ sub_event_type) using ACLED's controlled taxonomy when the source classification maps to it; for explosive-hazard points, set hazard_type (+ contamination_status) using the IMSMA/IMAS-style vocabulary. Both are optional and validated -- an unrecognized value comes back as a per-point warning, not a rejected point. If a point spans a period rather than one instant, also set event_start/event_end (additive alongside any date-like field in description); last_verified records when the data was last confirmed. If you're plotting incidents, threats, or other security-related points and haven't actually gathered them from a real source in this conversation (search_web/gemini_grounded_search/geocode_and_enrich/geocode_batch, or data the user supplied directly), do not call this tool with invented data -- say plainly in your chat response that you don't have verified locations for that, instead of fabricating a plausible-looking dataset. A point layer feeds directly into exported maps and reports, where fabricated content is far more likely to be trusted and acted on than the same claim in chat.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Name for the layer, e.g. 'Foreign Embassies'. |
| `points` | array[object] | yes | List of points to add, e.g. [{"lat": 31.95, "lon": 35.93, "name": "Embassy of France", "description": "Amman", "category": "High"}]. |
| `crs` | string | no | CRS the point coordinates are in, e.g. "EPSG:3857" or "EPSG:32636". Omit ONLY when the coordinates are already lon/lat degrees. If the user gave projected coordinates (large numbers such as 4902068, 1799912), pass them UNCHANGED with their CRS (the project CRS unless the user says otherwise) -- the code converts them exactly. NEVER convert coordinates yourself. |

### `fetch_building_footprints` _(two-phase)_

Download building footprint polygons for an area of interest from Microsoft's Global ML Building Footprints dataset (1B+ buildings, 225 countries/regions, CDLA Permissive 2.0 license) -- for baseline digitization where no local building-footprint data exists (e.g. in-limit boundary work), NOT for damage assessment against a specific fresh image (use calculate_raster_change_detection for that instead; see the result's baseline_caveat for the exact wording on how current this dataset is). country_name is free text matched against the dataset's own location list (NOT an ISO3 code -- this dataset isn't indexed that way); an ambiguous or unmatched name returns candidate matches instead of guessing.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `country_name` | string | yes | Country name, e.g. 'Yemen'. Matched against the dataset's own location names, not an ISO3 code. |
| `bbox` | array[number] | yes | [south, west, north, east] in WGS84 degrees -- footprints are cropped to this area, not the whole country. |
| `max_features` | integer | no | Safety cap on returned features. Defaults to 5000; if exceeded, results are truncated (not silently dropped) and truncated=true is reported. |
| `allow_large_download` | boolean | no | Set true ONLY after the user agreed to a download above their size threshold. |

### `fetch_fts_funding_data` _(network-only)_

Fetch humanitarian funding data from OCHA's Financial Tracking Service (FTS) for a country's response plan -- requirements, funding received, coverage percentage, and the funding gap. If year/plan_id are omitted, auto-selects the most recent plan and reports that it did so; if more than one plan matches (a country can run several concurrent plans in the same year, e.g. a regional migrant response alongside the main response plan), returns the candidate list instead of guessing which one you meant -- call again with plan_id set to one of those. Funding figures are a live snapshot from FTS, not a final/certain total -- state that when presenting them, the same way you would any other point-in-time data.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `country_iso3` | string | yes | 3-letter ISO country code, e.g. 'YEM'. |
| `year` | integer | no | Response plan year, e.g. 2024. Omit to auto-select the most recent. |
| `plan_id` | integer | no | A specific FTS plan ID (from a prior call's plan list) to fetch directly. |

### `fetch_geoboundaries` _(two-phase)_

Download administrative boundaries from geoBoundaries API. A file larger than the user's download-size setting is not fetched until the user agrees: then call again with allow_large_download=true.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `iso3` | string | yes |  |
| `admin_level` | string | yes |  |
| `allow_large_download` | boolean | no | Set true ONLY after the user agreed to a download above their size threshold. |

### `fetch_hdx_admin_boundaries` _(two-phase)_

Download OCHA's Common Operational Dataset - Administrative Boundaries (COD-AB) for a country from HDX -- the authoritative humanitarian source for admin boundaries, carrying real P-codes (the OCHA/HDX standard admin-unit code, e.g. 'YE12') as an attribute, unlike fetch_geoboundaries which doesn't publish P-codes at all. Reports which attribute field holds the P-code (pcode_field in the result) so it can be passed straight to unit_name_field/presence_admin_field for a reliable join in calculate_severity_index/calculate_presence_gap instead of fragile name-string matching. COD-AB coverage isn't universal -- if no dataset exists for a country, fall back to fetch_geoboundaries (broader coverage, but no P-codes).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `iso3` | string | yes | 3-letter ISO country code, e.g. 'YEM'. |
| `admin_level` | string | no | Admin level, e.g. 'ADM1', 'ADM2'. Defaults to 'ADM1'. |
| `allow_large_download` | boolean | no | Set true ONLY after the user agreed to a download above their size threshold. |

### `fetch_osm_features` _(network-only)_

Fetch OpenStreetMap vector features via Overpass API for a bounding box.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `key` | string | yes |  |
| `value` | string | yes |  |
| `bbox` | array[number] | yes |  |

### `fetch_worldpop_population` _(two-phase)_

Fetch a country's gridded population raster from WorldPop (open, free population data at ~100m resolution) and load it as a layer -- an open-data approximation of what ArcGIS's Business Analyst extension provides with proprietary demographic data. ALWAYS pass extent_layer (a layer covering the area of interest, e.g. the catchment or admin boundary) or bbox: without either the call is refused, because the WHOLE country would be downloaded (100MB-1GB+, minutes) -- allow_whole_country=true overrides that, only after the user agreed. With one, only that area plus a ~2 km margin is fetched and the layer is named <ISO3>_population_<year>_area. After loading, use estimate_population_exposure to sum population within a specific area.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `iso3` | string | yes | 3-letter ISO country code, e.g. 'YEM'. |
| `year` | string | no | Population year, e.g. '2020'. Omit to use the most recent available. |
| `extent_layer` | string | no | Name of a project layer whose extent is the area to fetch (preferred -- handles any CRS). |
| `bbox` | array[number] | no | Alternative to extent_layer: [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees. |
| `allow_whole_country` | boolean | no | Set true ONLY after the user agreed to download the whole country (100 MB to over 1 GB). Without extent_layer/bbox and without this, the tool refuses. |

### `ingest_osm_features` _(two-phase)_

Download OpenStreetMap vector features via Overpass API (e.g. key='amenity', value='hospital', or value='hospital|clinic|doctors', or key='highway', value='primary|secondary') for a bounding box or around a center coordinate and directly add them as a new vector layer to the active QGIS project. Use this whenever you need to ingest facilities, infrastructure, or road networks into an empty or new project.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `key` | string | yes | OSM tag key, e.g. 'amenity', 'highway', 'building' |
| `value` | string | yes | OSM tag value or regex pipe-separated values, e.g. 'hospital', 'hospital|clinic|doctors' |
| `bbox` | array[number] | no | Optional bounding box [south, west, north, east] |
| `center_lat` | number | no | Optional center latitude for radius search |
| `center_lon` | number | no | Optional center longitude for radius search |
| `radius_km` | number | no | Optional search radius in km around center (default: 10 km) |
| `layer_name` | string | no | Optional name for the created QGIS vector layer |

### `search_hdx_datasets` _(network-only)_

Search Humanitarian Data Exchange (HDX) for datasets by query.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes |  |
| `limit` | integer | no |  |

## Humanitarian Logistics

### `calculate_service_area`

Calculate the reachable road-network area around one or more facilities (warehouse, clinic, distribution point) within a given travel distance or time -- e.g. 'what area can this warehouse serve within 30km by road'. Produces, per facility, both the reachable road network and an approximate coverage polygon (convex hull around it). Requires a real line layer representing the road network -- for simple straight-line/as-the-crow-flies coverage, use buffer_analysis instead. Without speed_field, every road segment is treated as one flat default_speed regardless of surface or condition, which overstates reachability on unpaved/damaged roads -- when the network layer has a per-segment speed or condition field (e.g. from OSM highway/surface tags), pass it as speed_field with strategy='fastest' for a more realistic area. direction_field makes one-way roads one-way instead of assuming every segment is traversable both directions. Pass travel_cost as a LIST (e.g. [15, 30, 60]) instead of a single number for a real isochrone/access-band map: builds one combined polygon layer per facility with a travel_cost_band field, one ring per value, auto-styled with a graduated renderer -- a single call instead of one per band plus manual styling.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `facility_layer` | string | yes | Point layer with the facility/facilities to calculate service areas for. |
| `road_network_layer` | string | yes | Line layer representing the road/path network. |
| `travel_cost` | any | yes | Maximum travel distance in METRES (real-world, measured on the ellipsoid whatever the layers' CRS is) or time in HOURS if strategy='fastest'. Pass a single number for one service area, or a list of ascending values (e.g. [15, 30, 60]) for a multi-band isochrone/access map -- one combined, auto-styled polygon layer per facility instead of separate calls. |
| `strategy` | string | no | 'shortest' (distance-based, default) or 'fastest' (time-based). |
| `default_speed` | number | no | Default travel speed in km/h for any segment with no speed_field value, used only when strategy='fastest'. Defaults to 50. |
| `speed_field` | string | no | Optional numeric field on road_network_layer giving per-segment speed in km/h (e.g. derived from OSM highway/surface tags). Only affects routing when strategy='fastest'. |
| `direction_field` | string | no | Optional field on road_network_layer marking one-way segments (e.g. OSM's 'oneway' tag). Segments with no matching value still route both ways. |
| `style_by_cost` | boolean | no | Default true: also add a road layer graded by travel cost (near = dark, far = warm, labelled bands) and hide the plain reached-roads line layer, which stays in the project for analysis. Set false to keep only the plain lines. |
| `value_forward` | string | no | direction_field value meaning forward-only travel. Defaults to 'yes' (OSM convention). |
| `value_backward` | string | no | direction_field value meaning backward-only travel. Defaults to '-1' (OSM convention). |
| `value_both` | string | no | direction_field value meaning both directions. Defaults to 'no' (OSM convention). |

### `classify_facilities_by_access`

Answer 'which facilities are within / beyond N hours (or N metres) of this origin' FAST. Runs ONE service area from origin_layer (seconds, the same engine as calculate_service_area) and labels every facility in facility_layer 'within' when it lies on or within snap_distance_m of a road reached inside travel_cost, else 'beyond'. Use THIS instead of travel_time_matrix for any 'beyond/within X of the origin' question over many facilities: travel_time_matrix ties every destination into the road graph and took ~44 minutes for 3,369 facilities. Adds a copy of the facility layer with access_class and dist_to_reach_m fields, plus the service-area layers. APPROXIMATION to state in the answer: it ignores the access leg from the road to the facility (up to snap_distance_m) and is not a per-facility routed cost; use travel_time_matrix (small destination sets only) when exact per-facility costs are needed.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `origin_layer` | string | yes | Point layer holding the origin(s) the travel cost is measured from. |
| `facility_layer` | string | yes | Point layer of the facilities to classify. |
| `road_network_layer` | string | yes | Line layer of the road/path network. |
| `travel_cost` | number | yes | Max travel distance in METRES (strategy='shortest') or time in HOURS (strategy='fastest'). |
| `strategy` | string | no | 'shortest' (distance, default) or 'fastest' (time). |
| `default_speed` | number | no | Default speed in km/h, used only when strategy='fastest'. Defaults to 50. |
| `speed_field` | string | no | Optional per-segment speed field (km/h); ignored with a note if mostly empty. |
| `direction_field` | string | no | Optional one-way field on the road layer. |
| `snap_distance_m` | number | no | A facility counts as reached when it is within this many metres of a reached road. Defaults to 500. |

### `estimate_road_speeds`

Write an 'assumed_speed_kmh' field onto a road network layer's features, filled in from a fixed table of typical speeds per road class (motorway/primary/residential/track/etc, common routing-profile values -- see ASSUMED_SPEED_BY_ROAD_CLASS_KMH), read from the layer's 'fclass' (Geofabrik OSM extracts) or 'highway' (OSM/Overpass ingests) field. Use this when a road network has little or no real maxspeed data (very common: a real Jordan extract had maxspeed on only 0.9% of roads) and calculate_service_area/travel_time_matrix/optimize_delivery_route with strategy='fastest' would otherwise fall back to one flat default speed for nearly every road. IMPORTANT: this is an ASSUMPTION, not measured data for this specific road network -- tell the user the travel times that follow from it are estimates based on typical road-class speeds, not this network's real posted limits, especially if they ask for a precise duration. Never call this automatically as part of another tool's workflow; only when the user has actual maxspeed data will speed_field give a materially better answer. Pass country (an ISO 3166-1 alpha-2 code, e.g. 'JO', 'DE', 'US') to scale the table to that country's real legal urban/rural/motorway speed limits (see COUNTRY_SPEED_TIERS_KMH) instead of the generic global defaults -- covers a curated set of countries; falls back to the generic table for any other code or when omitted. Destructive action requiring UI confirmation -- in-place attribute mutation on the live layer, same class of operation as calculate_area/field_calculator.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `road_network_layer` | string | yes | Line layer of the road network, with an 'fclass' or 'highway' field. |
| `default_speed_kmh` | number | no | Speed assumed for a road class not in the table (default 30). |
| `overwrite` | boolean | no | If assumed_speed_kmh already exists, overwrite it. Default false: existing values are left alone, only missing/null ones are filled in. |
| `country` | string | no | Optional ISO 3166-1 alpha-2 country code (e.g. 'JO', 'DE', 'US') to scale the speed table to that country's real legal urban/rural/motorway limits instead of generic global defaults. Unrecognized or omitted falls back to the generic table. |

### `location_allocation`

Choose the best COMBINATION of num_facilities locations (out of a larger candidate list) to collectively minimize distance to all demand points -- e.g. 'which 3 of these 10 possible warehouse sites should we actually build, together, to best cover all these villages'. Different from optimal_hub_siting, which ranks candidates independently and doesn't account for overlap between them (two candidates both close to the same villages don't both get credit for covering them here). Uses a standard greedy approximation, not a guaranteed globally-optimal solution -- exact optimization is computationally infeasible beyond a handful of candidates anyway.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `candidate_layer` | string | yes | Point layer of possible facility locations. |
| `demand_layer` | string | yes | Point layer of locations needing service. |
| `num_facilities` | integer | yes | How many facilities to select. |
| `weight_field` | string | no | Optional numeric field on demand_layer to weight points by (e.g. population). Defaults to equal weight. |

### `optimal_hub_siting`

Rank candidate hub/warehouse/facility locations by how well they serve a set of demand points (e.g. villages, distribution sites) -- for each candidate, computes the average straight-line distance to all demand points and (if max_distance is given) how many fall within it. Returns candidates ranked best (lowest average distance) first. Use this instead of eyeballing a map when choosing between several possible hub locations. Uses straight-line distance, not road network distance -- for network-based reachability use calculate_service_area instead.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `candidate_layer` | string | yes | Point layer of possible hub/facility locations to evaluate. |
| `demand_layer` | string | yes | Point layer of locations needing service (villages, distribution sites). |
| `max_distance` | number | no | Distance (in the layers' CRS units, usually meters) within which a demand point counts as 'served'. Omit to rank on average distance alone. |

### `optimize_delivery_route`

Find a good visiting order for a set of delivery/distribution stops -- e.g. 'what order should the truck visit these 8 distribution points'. Uses a standard nearest-neighbor + 2-opt heuristic to pick the *order* (not a guaranteed globally-optimal order). Without road_network_layer, ordering uses straight-line distance and the result is a stop order only -- do NOT draw a straight line between the stops and present it as a route on an operational map; it is not a routable path. Pass road_network_layer to make the ordering itself road-network-aware (real road distance between every pair of stops, not straight-line) and to build an actual road-snapped route line, added to the project and safe to render as a real route. speed_field/direction_field (same meaning as calculate_service_area's) only affect ordering when road_network_layer is given. Not a substitute for a full commercial VRP solver with vehicle capacity/time-window constraints.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `stops_layer` | string | yes | Point layer of stops to visit. |
| `start_stop_name` | string | no | Optional name (from the layer's first attribute field) of the stop to start from. Defaults to the first feature. |
| `road_network_layer` | string | no | Optional line layer representing the road/path network. When given, visiting order uses real road-network distance (not straight-line) and a road-snapped route line is built and added to the project -- required before the output may be rendered as a route on a map. |
| `speed_field` | string | no | Optional numeric field on road_network_layer giving per-segment speed in km/h. Only affects ordering when road_network_layer is given. |
| `direction_field` | string | no | Optional field on road_network_layer marking one-way segments (e.g. OSM's 'oneway' tag). Only affects ordering when road_network_layer is given. |
| `value_forward` | string | no | direction_field value meaning forward-only travel. Defaults to 'yes' (OSM convention). |
| `value_backward` | string | no | direction_field value meaning backward-only travel. Defaults to '-1' (OSM convention). |
| `value_both` | string | no | direction_field value meaning both directions. Defaults to 'no' (OSM convention). |

### `population_access_gap`

Compute how many people, and what percentage of a population base, are BEYOND a given travel distance/time from the nearest facility -- e.g. 'X people / Y% of the population are more than 30 minutes from a functioning health facility', the standard access-to-services statistic in humanitarian gap analysis and cluster reporting. A thin composite over calculate_service_area (network-based reach per facility) and estimate_population_exposure (population sum within a polygon) rather than reimplementing either -- area_layer defines the population base to check coverage for (e.g. an admin-boundary or catchment polygon) and must already have a population raster available (see fetch_worldpop_population). As a side effect of calling calculate_service_area internally, per-facility service-area polygons are also added to the project, plus the combined reachable-area layers this tool builds from them. It reports THREE labelled figures (reach_figures): a concave hull of the reached roads (the headline, the method used in published hospital-access work), the reached roads buffered by reach_buffer_m (a tight lower figure) and the convex hull (an UPPER BOUND that fills the land between roads). Always give the user the range (reachable_population_range), not only the headline. Returns a MODELED estimate -- network-based reachability against a gridded population raster, not a verified count of people confirmed to lack access -- report it as 'an estimated N people/percent are beyond X', not as a confirmed access-gap figure.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `facility_layer` | string | yes | Point layer of facilities (health centers, warehouses, etc.). |
| `road_network_layer` | string | yes | Line layer of the road/path network. |
| `population_raster_layer` | string | yes | Population-per-pixel raster (e.g. from fetch_worldpop_population). |
| `area_layer` | string | yes | Polygon layer defining the population base to check coverage for. |
| `travel_cost` | number | yes | Max travel distance in METRES (real-world, whatever the layers' CRS is) or time in HOURS if strategy='fastest'. |
| `strategy` | string | no | 'shortest' (distance-based, default) or 'fastest' (time-based). |
| `default_speed` | number | no | Default travel speed in km/h, used only when strategy='fastest'. Defaults to 50. |
| `reach_geometry` | string | no | Which figure is the headline: 'concave_hull' (default), 'road_buffer' (people within reach_buffer_m of a reached road) or 'convex_hull' (an UPPER BOUND). All three are always reported in reach_figures. |
| `reach_buffer_m` | number | no | Buffer distance in metres around the reached roads for the road-buffer figure. Defaults to 500. |

### `score_route_incident_risk`

Score a planned route (or any line layer) against how close it passes to recent security/safety incidents -- 'does this route go near any recent incidents'. Reuses buffer_analysis's exact processing call to build a buffer around the route, then counts/lists incident_layer points falling within it, each with its own distance to the route. Optionally restrict to recent incidents only (date_field + days_back) and/or weight by a numeric field (e.g. a severity score) for a weighted risk total instead of a flat count. The buffer layer it creates is auto-styled as a translucent orange risk corridor (not QGIS's default random single-symbol color) so it reads as risk on the map without a separate styling call. Does NOT re-route or exclude anything automatically -- this scores a route for a human to act on; for a genuine hard-exclude of a security-restricted area from routing itself, use difference_layers to remove that area from the road network layer before calling calculate_service_area/travel_time_matrix, see docs/archive/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `route_layer` | string | yes | Line layer of the planned route (any line layer -- a hand-drawn route, a road-network subset, etc.). |
| `incident_layer` | string | yes | Point layer of incidents to check proximity against, e.g. the shared 'Incidents' layer from add_incident_point. |
| `buffer_distance` | number | yes | How close counts as 'near' the route, in the layers' CRS units (usually meters). |
| `date_field` | string | no | Optional date field on incident_layer, required if days_back is set. |
| `days_back` | integer | no | Optional: only count incidents from the last N days. Requires date_field. |
| `weight_field` | string | no | Optional numeric field on incident_layer (e.g. a severity score) to compute a weighted risk total instead of a flat count. |

### `travel_time_matrix`

Calculate road-network distance or travel time from each origin point to each destination point -- e.g. delivery distance from each warehouse to each distribution site. Returns a matrix of costs (metres for strategy='shortest' -- real-world distance whatever the layers' CRS is -- or hours for strategy='fastest') keyed by origin then destination. Requires a line layer representing the road network, not straight-line distance. Without speed_field, every segment is treated as one flat default_speed regardless of surface or condition -- when the network layer has a per-segment speed or condition field, pass it as speed_field with strategy='fastest' for a more realistic matrix. direction_field makes one-way roads one-way instead of assuming every segment is traversable both directions. SLOW for many destinations (every destination is tied into the road graph, which QGIS does by brute force; ~44 minutes for 3,369): for 'which facilities are within/beyond N of this origin' use classify_facilities_by_access instead; destination layers over 200 features use a single shortest-path tree per origin (fast; costs placed at the nearest road vertex) when the QGIS network classes are available.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `origins_layer` | string | yes | Point layer of origin locations (e.g. warehouses). |
| `destinations_layer` | string | yes | Point layer of destination locations (e.g. distribution sites). |
| `road_network_layer` | string | yes | Line layer representing the road/path network. |
| `strategy` | string | no | 'shortest' (distance-based, default) or 'fastest' (time-based). |
| `default_speed` | number | no | Default travel speed in km/h for any segment with no speed_field value, used only when strategy='fastest'. Defaults to 50. |
| `speed_field` | string | no | Optional numeric field on road_network_layer giving per-segment speed in km/h. Only affects the matrix when strategy='fastest'. |
| `direction_field` | string | no | Optional field on road_network_layer marking one-way segments (e.g. OSM's 'oneway' tag). Segments with no matching value still route both ways. |
| `value_forward` | string | no | direction_field value meaning forward-only travel. Defaults to 'yes' (OSM convention). |
| `value_backward` | string | no | direction_field value meaning backward-only travel. Defaults to '-1' (OSM convention). |
| `value_both` | string | no | direction_field value meaning both directions. Defaults to 'no' (OSM convention). |
| `allow_large` | boolean | no | Only needed if the fast single-tree method is unavailable: set true to run a matrix over more than 200 destinations the slow way. |

## Monitoring & Scheduling

### `list_scheduled_workflows`

List currently active recurring workflow schedules (session-scoped -- cleared when QGIS closes).

_No parameters._

### `run_monitoring_workflow`

Re-run a saved sequence of analysis tools (a 'monitoring workflow', see save_workflow_preset) in one shot and diff each step's per-unit results against the last time this preset was run -- e.g. re-running calculate_severity_index weekly and seeing which admin units moved into a worse severity class. Only read-only analysis tools are allowed as steps (calculate_severity_index, calculate_presence_gap, calculate_population_in_need, forecast_trend, field_statistics, population_access_gap, estimate_population_exposure) -- never geometry edits, file writes, or network-fetch tools, so an unattended recurring run can't silently repeat a destructive action or freeze the QGIS interface on a slow network call. For live hazard data (fire detections, GDACS alerts), call fetch_nasa_active_fires/fetch_nasa_eonet_events/fetch_gdacs_disaster_alerts directly instead -- they are not usable as a workflow step. The preset must be saved first via save_workflow_preset as '{"steps": [{"tool": "calculate_severity_index", "args": {...}}, ...]}'. The first run has nothing to compare against (previous_run_at is null); later runs report units_appeared/units_disappeared/units_changed per step, wherever that step's result contains a list of per-unit entries.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `preset_name` | string | yes | Name of a workflow preset already saved via save_workflow_preset. |

### `schedule_recurring_workflow`

Start re-running a saved monitoring workflow (see run_monitoring_workflow) automatically every interval_minutes, for as long as QGIS stays open with this plugin loaded. This is session-scoped, NOT a headless/background-service schedule -- it stops when QGIS closes or the plugin is unloaded, nothing runs while QGIS is closed. Each tick posts a short change summary into chat ('no changes since the last run', or a count of changed/new/dropped units) without an extra API call -- ask a follow-up question if you want the model to explain what changed. Starting a schedule for a preset_name that's already scheduled replaces the old schedule. Use stop_recurring_workflow to cancel, list_scheduled_workflows to see what's active. interval_minutes must be at least 1 (a shorter interval would hammer the QGIS UI thread with repeated geoprocessing), and at most 5 schedules can be active at once -- stop one first if already at that limit.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `preset_name` | string | yes | Name of a workflow preset already saved via save_workflow_preset. |
| `interval_minutes` | number | yes | Minutes between runs. Must be at least 1. |
| `max_runs` | integer | no | Optional: stop automatically after this many runs. Otherwise runs until QGIS closes or stop_recurring_workflow is called. |

### `stop_recurring_workflow`

Cancel a recurring workflow schedule started with schedule_recurring_workflow.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `preset_name` | string | yes |  |

## Print Layouts

### `create_print_layout`

Create a map print layout composition with title, legend, scalebar, north arrow, and an optional summary text panel -- then optionally export it. Exports at output_path if given: '.pdf' for a vector PDF, '.png'/'.jpg'/'.jpeg' for a raster image at the given dpi (default 300, print quality). ALWAYS use this instead of hand-writing QgsPrintLayout/QgsLayoutItemMap/QgsLayoutExporter code via execute_pyqgis_script, even for a richer composition than this tool's parameters look like they cover -- body_text accepts multi-line text (use \n between bullets/findings for a summary panel), and the legend/scale bar/north arrow are already included, so accepting this tool's defaults for those is strongly preferred over reimplementing the object-graph by hand. Hand-written layout code has repeatedly produced silently broken exports in live testing (a blank map area with no visible error, and real PyQGIS/Qt API mistakes, e.g. QFont.Italic and QgsLegendStyle.Item are not real attributes) that this tool doesn't have. The map area captures whatever extent is currently on screen -- pass zoom_to_layer to fit a specific layer's full extent first (e.g. the national boundary layer for a country-wide sitrep map); otherwise a stale or zoomed-in canvas view produces a cropped map missing large parts of the area of interest. `title` and `body_text` must only describe real, verified findings -- never invent incidents, casualties, threat assessments, severity ratings, or other real-world claims to make a report look complete. If you don't have verified data for what's being asked, say so in your chat response instead of writing placeholder or invented content into this layout -- a printed/exported layout reads as an authoritative finished document, not a draft, so anything fabricated here is far more likely to be trusted and acted on than the same claim in chat. Every export from this tool carries a standing disclaimer footer for exactly this reason, but that does not excuse writing fabricated content in the first place. Also includes a coordinate graticule, a CRS/datum + representative-fraction scale label ('1:N', alongside the graphical scale bar), and -- when include_inset_map is true -- a small locator/inset map showing where the main map sits within a wider surrounding area.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `title` | string | yes |  |
| `page_orientation` | string | no | 'Landscape' (default) or 'Portrait'. |
| `output_path` | string | no | Where to export -- '.pdf' for a vector PDF, '.png'/'.jpg'/'.jpeg' for a raster image. Omit to create the layout in the project without exporting. |
| `dpi` | integer | no | Export resolution in DPI, for both PDF and image export. Defaults to 300 (print quality). |
| `body_text` | string | no | Optional summary/sitrep text shown in a panel on the layout (e.g. priority findings, data sources). |
| `zoom_to_layer` | string | no | Name of a layer to fit the map to its full extent before capturing it, e.g. the national boundary layer for a full-country sitrep map. Omit to use whatever extent the canvas currently shows. |
| `template` | string | no | 'standard' (default) or 'access_map': for the result of a service-area / facility-access analysis. Fits the map to the reach layer when zoom_to_layer is omitted, lists the reach polygon, access points and cost-graded roads first in the legend, and (when body_text is empty) adds a short 'how to read this map' guide for the layers present. |
| `include_inset_map` | boolean | no | Add a small locator/inset map (zoomed out ~6x from the main map, same center) showing the main map's location within its wider region. Defaults to true. |

### `export_layout_atlas`

Exports one file PER FEATURE of a coverage layer from an existing print layout -- e.g. one PDF per district, one PNG per health facility catchment -- using QgsLayoutAtlas. This is the full-atlas half of point 15 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md; list_layout_items/update_layout_item_text (the other half) address items within ONE layout, this generates MANY layouts (one per feature). Only works on a layout built by create_print_layout, since it re-points that layout's MAP_MAIN item to follow the atlas -- there is no addressable map item on a hand-built layout to atlas-drive. Each output file is named from filename_field's value on that feature (e.g. a district-name field), sanitized for use as a filename; a non-unique or empty field value across features will silently overwrite an earlier output with the same name, so pick a field that's actually unique per feature (a P-code, not a display name that repeats).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes | An existing layout built by create_print_layout. |
| `coverage_layer_name` | string | yes | The layer whose features drive one output page each, e.g. an admin-boundary layer. |
| `output_directory` | string | yes | Directory to write the per-feature files into. Created if it doesn't exist. |
| `filename_field` | string | yes | Field on coverage_layer_name whose value names each output file. Should be unique per feature. |
| `output_format` | string | no | 'pdf' (default), 'png', 'jpg', or 'jpeg'. |
| `dpi` | integer | no | Export resolution in DPI. Defaults to 300 (print quality). |

### `list_layout_items`

Lists the addressable items in a print layout -- id, type, and current text (for text items) -- so the agent can check what's actually in a layout before editing it with update_layout_item_text, instead of guessing. create_print_layout gives every item it builds a stable id (MAP_MAIN, TITLE, LEGEND, SCALEBAR, NORTH_ARROW, BODY_TEXT, FOOTER -- NORTH_ARROW/BODY_TEXT only appear when that item was actually built). Point 15 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md (stable item addressability -- full QgsLayoutAtlas per-feature pagination is a separate capability, export_layout_atlas).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |

### `list_layouts`

List the print layouts already in the current QGIS project by name -- lets the agent check what layouts exist (e.g. before deciding whether to build a new one with create_print_layout or address an existing one) instead of guessing layout names. Point 21 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md (a project inspector) -- covers layouts only; QGIS Map Themes are a separate concept, listed by list_map_themes instead (point 16 of the same review, project_tools.py).

_No parameters._

### `update_layout_item_text`

Updates the text of one existing item in a print layout (e.g. a stale title or summary panel) by its stable id -- without rebuilding the whole layout with create_print_layout. Use list_layout_items first to see what ids exist. Only works on text items (TITLE, BODY_TEXT, FOOTER); MAP_MAIN/LEGEND/SCALEBAR/NORTH_ARROW have no settable text. Point 15 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `item_id` | string | yes | Stable id from list_layout_items, e.g. 'TITLE'. |
| `text` | string | yes |  |

## Project Management

### `apply_map_theme`

Restores a previously saved map theme (layer visibility and style), created with create_map_theme -- switches the project's current view between different named map product states.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `theme_name` | string | yes |  |

### `create_map_theme`

Saves the current layer visibility/style state as a named map theme, so it can be restored later with apply_map_theme -- for producing several different map products (e.g. 'overview', 'health facilities only', 'roads and admin boundaries') from one project without manually toggling layer visibility every time. Point 16 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `theme_name` | string | yes | Name for the saved theme. |

### `create_project_folder_structure`

Creates the recommended humanitarian-GIS project folder layout (data/00_raw for immutable source data, 10_staging/20_processed for derived work, plus styles/models/scripts/exports/metadata/logs) under a base directory. Opt-in only -- call this ONLY when the user explicitly asks for a standard project structure; never on your own initiative, since many users already work inside an org-mandated data structure this would duplicate. Never overwrites or deletes anything -- only creates folders that don't already exist.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `base_path` | string | yes | Absolute path to the project root the folder structure should be created under, e.g. 'C:/projects/flood_response'. Created if it doesn't exist. |

### `list_map_themes`

Lists the names of every map theme saved in the current project via create_map_theme.

_No parameters._

### `load_project`

Open a different QGIS project file, replacing everything currently loaded. Destructive: any unsaved changes in the current project are lost -- save_project first if they matter.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes | Absolute path to a .qgz/.qgs project file. |

### `save_project`

Save the current QGIS project (all layers, styles, and layout) to a .qgz/.qgs file. Use this as a checkpoint before a risky multi-step operation, or at the end of a task so the user's work is persisted.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `output_path` | string | no | Absolute path to save to, e.g. 'C:/maps/analysis.qgz'. Omit to save to the project's current file path (if it has one). |

## Raster

### `apply_raster_stretch`

Apply a min/max contrast stretch or pseudocolor ramp to a single-band raster layer -- every raster-producing tool in this plugin (calculate_ndvi/calculate_ndwi/calculate_ndre, calculate_raster_change_detection, hillshade/slope_analysis/aspect_analysis, interpolate_surface, hotspot_analysis, weighted_overlay_analysis, etc.) lands on the canvas with QGIS's raw, unstretched single-band default rendering, which usually looks flat grey and unreadable until this is applied -- this plugin's vector styling toolkit (apply_graduated_style, apply_categorized_style, apply_heatmap_style) has no raster equivalent, this tool is it. Two modes: 'color_ramp' applies a QgsSingleBandPseudoColorRenderer with a named QGIS color ramp (e.g. a diverging ramp centered on 0 for a -1..1 vegetation/water index); 'stretch' applies a grayscale linear min/max contrast stretch via QgsSingleBandGrayRenderer, the usual fix for a flat-looking DEM/hillshade/panchromatic band. 'auto' (default) picks 'color_ramp' with a sensible diverging ramp for layers whose name contains 'ndvi'/'ndwi'/'ndre', 'stretch' otherwise. Min/max values default to the band's actual computed data min/max unless overridden.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `mode` | string | no | 'auto' (default), 'stretch' (grayscale contrast stretch), or 'color_ramp' (pseudocolor). 'auto' picks 'color_ramp' for layers named like NDVI/NDWI/NDRE, 'stretch' otherwise. |
| `color_ramp` | string | no | QGIS color ramp name (e.g. 'Viridis', 'RdYlGn', 'RdBu', 'Spectral'). Only used in 'color_ramp' mode. Defaults to a diverging ramp for known vegetation/water indices, or 'Viridis' otherwise. |
| `band` | integer | no | Raster band number to style. Defaults to 1. |
| `min_value` | number | no | Optional. Overrides the auto-computed stretch/ramp minimum. |
| `max_value` | number | no | Optional. Overrides the auto-computed stretch/ramp maximum. |
| `keep_population_ramp` | boolean | no | Default true: a WorldPop population layer keeps the plugin's own ramp (empty cells transparent, unit on the legend) because a generic stretch over a whole country is unreadable. Pass false only if the user explicitly asked for a different look. |

### `aspect_analysis`

Calculate aspect map from DEM layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `dem_layer` | string | yes |  |

### `band_composite`

Create RGB band composite from single band rasters.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `red_band` | string | yes |  |
| `green_band` | string | yes |  |
| `blue_band` | string | yes |  |

### `calculate_ndre`

Calculate NDRE (Normalized Difference Red Edge index) from Red Edge and Near-Infrared raster bands -- a precision-agriculture vegetation index more sensitive than NDVI to chlorophyll/nitrogen status in mid-to-late-season crops: 'crop nitrogen stress', 'plant chlorophyll health', 'precision agriculture crop monitoring'. Needs a Red Edge band (not standard on every sensor -- confirm the imagery actually has one before calling this over calculate_ndvi, which only needs Red/NIR and works with far more common sensors). Produces a new single-band raster layer named 'NDRE' with QGIS's default (unstretched) rendering -- follow up with apply_raster_stretch(layer_name='NDRE') to apply a readable diverging color ramp (auto-selected for NDRE-named layers) instead of leaving it flat/unstretched.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `red_edge_layer` | string | yes |  |
| `nir_layer` | string | yes |  |

### `calculate_ndvi`

Calculate NDVI (Normalized Difference Vegetation Index) from Red and Near-Infrared raster bands -- the standard remote-sensing measure of vegetation health/greenness/density: 'how green is this area', 'is this crop/vegetation healthy', 'vegetation health check'. Output ranges roughly -1 to 1: values near 1 indicate dense healthy vegetation, near 0 bare soil or built-up areas, negative values open water. Produces a new single-band raster layer named 'NDVI' added to the project with QGIS's default (unstretched, low-contrast) rendering -- follow up with apply_raster_stretch(layer_name='NDVI') to apply a readable diverging color ramp (auto-selected for NDVI-named layers) instead of leaving it flat/unstretched.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `red_layer` | string | yes |  |
| `nir_layer` | string | yes |  |

### `calculate_ndwi`

Calculate NDWI (Normalized Difference Water Index) from Green and Near-Infrared raster bands -- the standard remote-sensing measure of surface water/moisture: 'how much water is in this area', 'map surface water extent', 'is there flooding here'. Output ranges roughly -1 to 1: values above ~0 typically indicate open water, below ~0 vegetation/dry land. For a flood-specific before/after comparison rather than a single-image water map, use calculate_raster_change_detection instead. Produces a new single-band raster layer named 'NDWI' with QGIS's default (unstretched) rendering -- follow up with apply_raster_stretch(layer_name='NDWI') to apply a readable diverging color ramp (auto-selected for NDWI-named layers) instead of leaving it flat/unstretched.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `green_layer` | string | yes |  |
| `nir_layer` | string | yes |  |

### `create_shaded_relief`

Generate a publication-grade shaded relief composite from a DEM layer combining hypsometric elevation tinting with hillshade using Multiply blending (QPainter.CompositionMode_Multiply). First styles the DEM with a pseudocolor elevation color ramp (e.g. 'BrBG', 'Spectral', or 'Terrain'), generates or links the hillshade layer, and applies the Multiply blend mode so the topography modulates the elevation colors cleanly without flattening.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `dem_layer` | string | yes | Name of the DEM/elevation raster layer. |
| `color_ramp` | string | no | Color ramp name for hypsometric tinting. Defaults to 'BrBG' (CVD-safe diverging ramp). |
| `azimuth` | number | no | Sun azimuth angle in degrees (default 315). |
| `altitude` | number | no | Sun altitude angle in degrees (default 45). |
| `opacity` | number | no | Hillshade layer opacity between 0.0 and 1.0 (default 1.0). |

### `elevation_profile`

Sample a DEM raster along a line to produce a distance/elevation profile -- e.g. terrain along a proposed route, or a valley cross-section. Returns distance-along-line and elevation arrays of equal length; feed them into generate_chart (chart_type='line') for a real elevation-profile chart.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `line_layer` | string | yes | Line layer to sample along. Uses the first feature if it has more than one. |
| `dem_layer` | string | yes | Raster (DEM) layer to sample elevation from. |
| `num_samples` | integer | no | Number of sample points along the line. Defaults to 100. |

### `estimate_population_exposure`

Sum population within each polygon of a vector layer, using an already-loaded population raster (e.g. from fetch_worldpop_population) -- e.g. 'how many people live within 5km of this facility' (combine with buffer_analysis first to build the area), or 'population per district' (pass admin boundaries directly). Adds a 'pop_sum' field to the vector layer. Returns an ESTIMATE derived from a gridded population raster, not a verified count of people actually present -- report results as 'estimated population within <area>', never as a confirmed or affected-population figure, unless field data corroborates it.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `population_raster_layer` | string | yes | A population-per-pixel raster layer (e.g. from fetch_worldpop_population). |
| `area_layer` | string | yes | Polygon layer to sum population within, one total per feature. |

### `georeference_image`

Georeference a scanned map or unreferenced image using control points (pixel coordinates matched to real-world coordinates) -- e.g. aligning a scanned paper map to its true location and scale on the map. Needs at least 3 non-collinear control points; more (well-distributed across the image) generally gives a more accurate result than the minimum. Produces a real, spatially-referenced raster, loads it into the project, and reports the fit's RMSE (in the target CRS's units) so alignment quality can be judged -- QGIS Georeferencer shows the same number for the same reason.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `image_path` | string | yes | Absolute path to the source image (e.g. a scanned map). |
| `control_points` | array[object] | yes | At least 3 points, e.g. [{"pixel_x": 120, "pixel_y": 340, "lon": 35.93, "lat": 31.95}]. |
| `output_path` | string | yes | Where to save the georeferenced raster (.tif). |
| `target_crs` | string | no | CRS of the lon/lat control point coordinates. Defaults to EPSG:4326. |
| `transform_type` | string | no | 'tps' (default): thin-plate-spline rubber-sheeting -- best when the source image itself is locally distorted (an uneven scan, a hand-drawn sketch map) since it bends to fit every control point exactly. 'linear': a single 6-parameter affine (independent x/y scale, shear, rotation) fit by least squares -- QGIS Georeferencer's 'Linear'. 'helmert': a single 4-parameter similarity (one uniform scale, one rotation, no shear) fit by least squares -- QGIS Georeferencer's 'Helmert', the right choice for a clean scan of a rigid printed map where the true transform can't have shear. |

### `hillshade`

Generate hillshade surface from DEM layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `dem_layer` | string | yes |  |

### `histogram_equalization`

Enhance raster image contrast using histogram equalization.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `raster_layer` | string | yes |  |

### `interpolate_surface`

Create a continuous raster surface from scattered point values using spatial interpolation -- e.g. estimating rainfall/elevation/population density between sample points. 'idw' (inverse distance weighting, default) is simple and fast; 'tin' (triangulated irregular network) preserves exact sample values but can look faceted at the triangle edges. Neither is a true geostatistical kriging model -- use this for a reasonable estimate, not a statistically rigorous prediction with confidence bounds.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `point_layer` | string | yes |  |
| `field` | string | yes | Numeric field to interpolate. |
| `method` | string | no | 'idw' (default) or 'tin'. |
| `cell_size` | number | no | Output raster cell size in the layer's CRS units. Defaults to a size producing roughly a 250x250 grid. |

### `mosaic_rasters`

Merge/mosaic multiple raster layers together.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `raster_layers_list` | array[string] | yes |  |

### `pan_sharpening`

Pan-sharpen multispectral raster using panchromatic band.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `ms_layer` | string | yes |  |
| `pan_layer` | string | yes |  |

### `raster_clip`

Clip raster layer by vector mask layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `raster_layer` | string | yes |  |
| `mask_layer` | string | yes |  |

### `slope_analysis`

Calculate slope map from DEM layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `dem_layer` | string | yes |  |

### `supervised_classification`

Supervised classification using training polygons.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `training_layer` | string | yes |  |

### `unsupervised_classification`

Unsupervised K-Means raster classification.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `num_classes` | integer | yes |  |

### `weighted_overlay_analysis`

Combine multiple rasters into a single weighted suitability/risk surface -- e.g. 'best sites for a new clinic' combining slope, distance-to-road, and population density rasters with different weights. Each input raster should already be normalized to a comparable scale (e.g. 0-1 or 0-100) before combining -- this tool weights and sums them, it doesn't rescale them. All rasters must share the same CRS and cover roughly the same extent/resolution, or the result is meaningless; mismatched CRS is rejected outright rather than silently misaligned.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `raster_layers` | array[string] | yes | 2 to 6 raster layer names to combine. |
| `weights` | array[number] | yes | One weight per raster, same order as raster_layers. Don't need to sum to 1 -- normalized automatically. |

### `zonal_statistics`

Compute zonal statistics of raster over vector polygons.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `raster_layer` | string | yes |  |
| `vector_layer` | string | yes |  |

## Reporting & Document Analysis

### `aggregate_data` _(network-only)_

Group rows of data by a field and compute sum/count/mean/min/max of another field per group -- e.g. 'total incidents by district' or 'average funding by cluster'. Takes structured rows such as the output of extract_pdf_tables/extract_word_tables (their 'rows' list), or any other list of flat {field: value} objects you've already gathered.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `rows` | array[object] | yes | List of flat row objects to aggregate. |
| `group_by_field` | string | yes |  |
| `value_field` | string | no | Numeric field to aggregate. Not needed when agg is 'count'. |
| `agg` | string | no | 'sum' (default), 'count', 'mean', 'min', or 'max'. |

### `extract_pdf_tables` _(network-only)_

Extract structured tables from a PDF file -- e.g. a situation report's 'IDPs by district' table -- as rows of column values, not just plain text. Use this instead of reading PDF text when the data you need is in a table (funding breakdowns, incident lists, needs-assessment figures). Returns one entry per detected table, each with its own columns/rows.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes | Absolute path to the PDF file. |
| `page` | integer | no | 1-based page number to limit extraction to. Omit to scan every page. |

### `extract_word_tables` _(network-only)_

Extract structured tables from a Word (.docx) document as rows of column values, instead of flattened text. Use this when the data you need is in a table (e.g. a needs-assessment matrix) rather than prose.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes | Absolute path to the .docx file. |

### `generate_chart` _(network-only)_

Generate a bar, pie, or line chart image from labeled numeric data -- for statistical comparisons a map can't show (funding by cluster, incidents over time, casualties by district). Not for spatial/geographic visualization -- use the styling tools (apply_categorized_style, apply_graduated_style, etc.) for that. Returns the PNG file path.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `chart_type` | string | yes | 'bar', 'pie', or 'line'. |
| `title` | string | yes |  |
| `labels` | array[string] | yes | Category names (bar/pie) or x-axis points (line). |
| `values` | array[number] | yes | One numeric value per label. |
| `x_label` | string | no | X-axis label. Ignored for pie charts. |
| `y_label` | string | no | Y-axis label. Ignored for pie charts. |
| `output_path` | string | no | Where to save the PNG. Defaults to a temp file. |
| `color_palette` | array[string] | no | Optional list of hex colors (e.g. ['#0072B2', '#E69F00']) to use instead of the default colorblind-safe palette -- cycled if there are more categories than colors. |
| `dpi` | integer | no | Export resolution in DPI. Defaults to 300 (print quality). |

### `generate_sector_coverage_report`

Generate the standard humanitarian 'beneficiaries reached vs. target' coverage table and bar chart in one call, grouped by sector/cluster (or any other categorical field, e.g. admin unit) -- instead of chaining aggregate_data + generate_chart by hand. Sums reached_field (and target_field, if given) per group_by_field value, computes a coverage percentage per group when a target is given, and renders a bar chart. Returns the underlying table alongside the chart path so both the numbers and the visual are available. When a target is given, the table is sorted worst-coverage-first (groups with no target on record sort alongside the worst performers, not silently last, since missing target data is itself worth flagging in a gap analysis) -- otherwise sorted by reached, highest first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `rows` | array[object] | yes | List of flat row objects, e.g. one per activity/beneficiary record. |
| `group_by_field` | string | yes | Field to group by -- typically sector/cluster, but any categorical field works (e.g. admin unit). |
| `reached_field` | string | yes | Numeric field holding beneficiaries reached per row. |
| `target_field` | string | no | Optional numeric field holding the target per row -- enables a coverage percentage. |
| `title` | string | no | Chart title. Defaults to 'Coverage by {group_by_field}'. |
| `output_path` | string | no | Where to save the chart PNG. Defaults to a temp file. |

### `load_3w_data`

Read a 3W/4W ('who does what where/when') CSV or Excel file -- the standard humanitarian operational-presence dataset, one row per activity with an organization, admin unit, and usually a sector/cluster -- and aggregate it into organizational presence per admin unit: how many distinct organizations are active there, which ones, and (if a sector field is given) which sectors are covered. Use this for 'which organizations work in X' / 'how many actors cover district Y' questions. This is a plain tabular read, not a QGIS layer load -- pair with calculate_presence_gap to cross-reference presence against a severity/needs index.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes | Absolute path to the .csv/.xlsx/.xls 3W/4W file. |
| `admin_field` | string | yes | Column holding the admin unit name/P-code each activity row belongs to. |
| `org_field` | string | yes | Column holding the organization name/acronym running each activity. |
| `sector_field` | string | no | Optional column holding the sector/cluster (e.g. WASH, Health) -- adds sector coverage per unit. |
| `sheet_name` | string | no | Sheet name for Excel files with multiple sheets. Defaults to the first sheet. |
| `delimiter` | string | no | CSV field delimiter. Defaults to ','. |

## Satellite Imagery & Vision

### `calculate_raster_change_detection`

Compute pixel-wise differential change between two temporal rasters (after minus before) -- 'what changed between these two satellite images', 'compare before and after images for damage', 'show me the damage from before to after'. The core building block calculate_damage_exposure_severity composes into a full damage assessment (zonal stats per admin unit, building exposure counts, severity classing) -- use this tool directly only for the raw pixel-difference layer itself, calculate_damage_exposure_severity for a per-district severity score. Produces a new raster layer named 'change_detection_<after>_vs_<before>' added to the project with QGIS's default (unstretched) rendering -- this plugin has no dedicated raster styling tool, so a diverging color ramp needs to be applied manually in QGIS's own layer properties to make the change pattern visible.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `raster_before` | string | yes |  |
| `raster_after` | string | yes |  |

### `inspect_canvas_visually`

Capture current map canvas view and return visual inspection context.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `prompt_guidance` | string | no |  |

### `search_stac_satellite_imagery` _(network-only)_

Search STAC API (Earth Search / Sentinel-2) for satellite scenes by bounding box and date range.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `bbox` | array[number] | yes |  |
| `start_date` | string | yes |  |
| `end_date` | string | yes |  |
| `limit` | integer | no |  |

## Styling & Labeling

### `apply_categorized_style`

Apply categorized style renderer based on field values. Pass palette='humanitarian_cluster' to color categories that match a known IASC global cluster name (Health, WASH, Food Security, Protection, Emergency Shelter, Nutrition, Education, Logistics, CCCM, Early Recovery, Emergency Telecommunications, plus common aliases like 'FSL' or 'Shelter') using commonly recognized humanitarian cluster colors -- the map a field coordinator recognizes instantly instead of one they have to re-read the legend for. Categories that don't match a known cluster name keep the default qualitative color assignment.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field` | string | yes |  |
| `opacity` | number | no | 0-100. Defaults to 75 for polygon layers (so overlapping layers/basemap underneath stay visible) and 100 for points/lines. |
| `palette` | string | no | Optional. 'humanitarian_cluster' (or 'ocha') colors categories matching a known IASC cluster name/alias; unmatched categories keep the default palette. |

### `apply_graduated_style`

Apply smart graduated choropleth style analyzing field distribution for optimal breaks. Pass cluster (e.g. 'WASH', 'Health', 'Food Security') to tint the ramp toward that IASC cluster's commonly recognized color instead of the auto-selected Viridis/Cividis ramp -- e.g. a WASH coverage % choropleth rendered in WASH's color, for the map a field coordinator recognizes instantly. Unrecognized cluster names fall back to the default ramp. Pass explicit breaks (e.g. [10000, 25000, 50000, 100000]) for a fixed, mode-independent set of class boundaries -- for humanitarian decision maps, an operational threshold (e.g. response-capacity bands) often matters more than a statistically 'optimal' Jenks/quantile break, and breaks overrides mode entirely when given (point 13 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field` | string | yes |  |
| `mode` | string | no | 'auto' (default), 'equal', 'quantile', 'stddev' (classes centered on the mean +/- N standard deviations), 'pretty' (rounded, human-friendly breaks for a public-facing map), or 'logarithmic' (log-spaced classes for heavily right-skewed data spanning orders of magnitude, e.g. population or income -- needs all-positive, non-identical values). Ignored if breaks is given. |
| `num_classes` | integer | no | Number of classes to split the data into. Defaults to 5. Ignored if breaks is given. |
| `opacity` | number | no | 0-100. Defaults to 75 for polygon layers (so overlapping layers/basemap underneath stay visible) and 100 for points/lines. |
| `cluster` | string | no | Optional IASC cluster name/alias (e.g. 'WASH', 'Health') to tint the ramp toward that cluster's color instead of the auto-selected one. |
| `breaks` | array[number] | no | Optional explicit class-boundary values (e.g. operational response thresholds), sorted ascending -- when given, these define the classes directly instead of an auto-selected classification method, overriding 'mode'. Data's actual min/max become the outer class bounds. |

### `apply_graduated_symbol_style`

Apply a graduated (proportional) SYMBOL SIZE style to a point layer -- circles scaled from a minimum to a maximum size based on a numeric field, analyzing the field's distribution for optimal class breaks the same way apply_graduated_style does for choropleth fill color. Use this for point data (e.g. 'graduated symbol map', 'proportional circles') instead of hand-writing QgsGraduatedSymbolRenderer/QgsRendererRange code via execute_pyqgis_script.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field` | string | yes |  |
| `min_size` | number | no | Smallest symbol size in mm. Defaults to 4. |
| `max_size` | number | no | Largest symbol size in mm. Defaults to 24. |
| `mode` | string | no | 'auto' (default), 'equal', 'quantile', 'stddev', or 'pretty'. |
| `num_classes` | integer | no | Target number of size classes. Defaults to 5, capped down to the field's actual number of distinct values if fewer. |
| `color` | string | no | Hex color (e.g. '#3182bd') for every symbol -- size carries the meaning here, not color. Defaults to a semi-transparent blue. |

### `apply_heatmap_style`

Apply heatmap renderer to point layer with transparent zero-density baseline so basemaps remain visible.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field` | string | no |  |

### `apply_point_cluster_style`

Applies a point cluster or point displacement renderer to a point layer so overlapping or densely clustered points are cleanly grouped on the map rather than drawing on top of each other. Mode 'cluster' (default) aggregates nearby points within a distance threshold into numeric cluster badges; mode 'displacement' displays co-located or overlapping points arranged in a clean ring/spiral circle around the central coordinate.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Point layer to apply clustering/displacement to. |
| `mode` | string | no | 'cluster' (default) for aggregate numeric count badges, 'displacement' for circle/ring offset around overlaps. |
| `tolerance` | number | no | Cluster distance tolerance in millimeters (default 15.0 mm). |

### `apply_rule_based_style`

Apply a rule-based renderer keyed to a controlled vocabulary of field values -- e.g. route/facility status (open/constrained/closed) -- with a FIXED color per value, rather than an auto-assigned qualitative palette (apply_categorized_style) or an auto-classified continuous gradient (apply_graduated_style). Use this when the categories carry a specific operational meaning that needs a caller-chosen color per value, not an auto-picked one. Any field value not matching one of the given rules automatically renders in a neutral gray 'Unknown / No data' class -- do not add your own catch-all rule, and never let an unassessed/missing status look the same as a real class.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field` | string | yes |  |
| `rules` | array[object] | yes | One entry per controlled-vocabulary value, e.g. [{"value": "open", "label": "Open", "color_hex": "#2E7D32"}, {"value": "closed", "label": "Closed", "color_hex": "#B3261E"}]. |

### `auto_arrange_layer_order`

Reorders every top-level layer in the project by geometry type so small features stay visible: points on top, then lines, then polygons, then rasters at the bottom. Call this after adding or styling multiple overlapping layers -- e.g. point markers plus an area/boundary polygon -- so the polygon's fill doesn't bury the points underneath it. This is the usual fix when a map with several layers looks 'messy' or a small icon layer has disappeared under a larger area layer.

_No parameters._

### `change_layer_color`

Change layer symbol fill/line color using hex string.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `color_hex` | string | yes |  |
| `opacity` | number | no | Optional, 0-100. Leaves current opacity unchanged if omitted. |

### `export_layer_sld`

Exports a vector layer's symbology to an OGC SLD (Styled Layer Descriptor 1.1.0/1.0.0) file on disk. Use this when publishing styles to GeoServer/MapServer or sharing interoperable OGC styling with external GIS portals. Without output_path, saves beside the source file as '<source>.sld' (or to Desktop for scratch/memory layers).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Vector layer to export styling from. |
| `output_path` | string | no | Optional explicit .sld file path. Defaults to beside the layer's source file. |

### `hotspot_analysis`

Compute a kernel density estimation surface from a point layer -- a real statistical density raster (higher values = more points/higher intensity nearby), not just a visual-only renderer. apply_heatmap_style changes how a layer LOOKS on screen but produces no reusable data; this tool produces an actual raster you can run zonal_statistics against (e.g. rank districts by incident density) or feed into weighted_overlay_analysis for risk-surface analysis. Use this for real hotspot/risk-concentration analysis, apply_heatmap_style for a quick visual only.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `point_layer` | string | yes |  |
| `radius` | number | yes | Kernel search radius in the layer's map units. Larger = smoother, less localized. |
| `pixel_size` | number | no | Output raster cell size in map units. Defaults to radius/10. |
| `weight_field` | string | no | Optional numeric field to weight points by (e.g. severity) instead of treating every point equally. |

### `load_layer_style`

Loads a previously saved .qml style file (from save_layer_style, or exported manually via QGIS's own Layer Properties -> Symbology -> Style -> Save Style) onto a layer, replacing its current symbology -- for reusing a standard humanitarian color scheme/classification across layers or maps instead of rebuilding it from scratch each time.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `style_path` | string | yes | Path to the .qml style file to load. |

### `save_layer_style`

Saves a layer's current symbology (renderer, colors, classification, labeling) to a real .qml style file on disk, so it can be reapplied later to this or another layer with load_layer_style -- for reusing a standard color scheme/classification across multiple layers or maps instead of rebuilding it with apply_categorized_style/apply_graduated_style every time. Without output_path, the file is saved beside the layer's own on-disk source (as '<source>.qml'); for a scratch/memory layer with no real source, it falls back to Desktop instead. For a GeoPackage-backed layer, the style is ALSO written into the GeoPackage's own layer_styles table (OGC 12-128r17) so it travels with the .gpkg file itself -- e.g. opening it in another QGIS install or a different GIS package that reads that table -- not just as an external sidecar that can be misplaced or left behind.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `output_path` | string | no | Optional explicit .qml file path. Defaults to beside the layer's own source file. |

### `set_layer_order`

Explicitly sets the draw order of the given layers, top to bottom (the first name in the list renders on top of the rest, on top of everything else in the project). Use this when auto_arrange_layer_order's point > line > polygon > raster default isn't what's needed -- e.g. two polygon layers that need a specific stacking order relative to each other.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_names` | array[string] | yes | Layer names in the desired draw order, first = topmost. |

### `set_layer_transparency`

Set a layer's overall opacity (0-100). Use this to make an area/polygon layer semi-transparent so layers or features underneath it (e.g. point markers) stay visible instead of being fully covered by a solid fill.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `opacity_percent` | number | yes | 0 (fully transparent) to 100 (fully opaque). |

## System, Search & Scripting

### `execute_pyqgis_script`

LAST RESORT ONLY -- run this only when no other registered tool covers the task; check the rest of the tool list first, including run_allowlisted_processing_algorithm if the task is achievable via a single Processing algorithm -- that tool never executes Python code at all, so it's meaningfully safer than this one whenever it applies. Runs in a separate, isolated process (a snapshot of the project, not the live one) with its own denylist-based safety sandbox on top (blocked modules/builtins; see SECURITY.md) -- not a formally proven sandbox, so it is not a safe default path just because it's available. Fails with an error, without running, if any layer has uncommitted edits -- commit or discard them first. Execute arbitrary PyQGIS script; must define a run() function returning the result.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `script` | string | yes |  |

### `gemini_grounded_search` _(two-phase)_

Search the live web using Gemini's native Google Search grounding for real-time, source-cited facts. Only works when the active provider is Gemini with a configured API key -- prefer this over search_web when the active provider is Gemini.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes |  |

### `geocode_and_enrich` _(network-only)_

Geocode a SINGLE address/place name into lat/lon via Nominatim API. For multiple locations in one request, use geocode_batch instead -- one call per place will run out of tool-call steps before finishing a long list.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `location_name` | string | yes |  |

### `geocode_batch`

Geocode MULTIPLE address/place names into lat/lon in a single call. Use this instead of calling geocode_and_enrich in a loop whenever more than one location needs coordinates.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `location_names` | array[string] | yes |  |

### `openai_grounded_search` _(two-phase)_

Search the live web using OpenAI's dedicated web-search model for real-time, source-cited facts. Only works when the active provider is OpenAI with a configured API key -- prefer this over search_web when the active provider is OpenAI.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes |  |

### `search_web` _(network-only)_

Search internet for real-time information or facts.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes |  |
| `max_results` | integer | no |  |

## Task & Memory Management

### `create_plan` _(task-management)_

Create a multi-step execution plan for complex spatial tasks.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `title` | string | yes |  |
| `task_descriptions` | array[string] | yes |  |

### `set_task_preview` _(task-management)_

Set a task to PREVIEW_READY state before applying destructive spatial edits.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `task_id` | string | yes |  |
| `code_snippet` | string | yes |  |
| `rationale` | string | no |  |
| `is_destructive` | boolean | no |  |

### `store_global_memory` _(task-management)_

Store persistent global preference/note across sessions.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `key` | string | yes |  |
| `value` | string | yes |  |

### `store_project_memory` _(task-management)_

Store persistent key-value note for current project. Only when the user asked you to remember something; never store coordinates or data values.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `key` | string | yes |  |
| `value` | string | yes |  |

### `update_task` _(task-management)_

Update status of a task in current plan (TODO, IN_PROGRESS, PREVIEW_READY, CONFIRMED, DONE, FAILED).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `task_id` | string | yes |  |
| `status` | string | yes |  |
| `result` | string | no |  |
| `rationale` | string | no |  |
| `code_snippet` | string | no |  |

## Vector & Geoprocessing

### `add_layer_from_path` _(two-phase)_

Load vector or raster file from a local path or remote URL (e.g. a GeoJSON download link).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes |  |
| `layer_name` | string | no |  |

### `apply_labels`

Apply text labels to a vector layer, either from a single field (target_field) or a QGIS expression combining multiple fields/literals (expression) -- e.g. a governorate name, P-code, and a count combined into one label like "Sa'dah [YE22 | 4 Orgs]" via "adm1_name || ' [' || adm1_pcode || ' | ' || org_count || ' Orgs]'" -- instead of hand-writing QgsPalLayerSettings code via execute_pyqgis_script for a combined label. Pass exactly one of target_field/expression. Applies a white text halo/buffer by default so labels stay legible over dense polygons or dark rasters, and -- for point layers -- an 8-position ordered placement with collision avoidance instead of an arbitrary single position.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `target_field` | string | no | A single field to label from. Omit if using expression instead. |
| `expression` | string | no | A QGIS expression combining multiple fields/literals into one label. Omit if using target_field instead. |
| `font_size` | number | no | Label text point size. Defaults to 10 -- pass a larger value for higher-hierarchy features (e.g. a capital vs. a village) and a smaller one for dense point layers. |
| `priority` | number | no | PAL anti-collision priority, 0 (lowest) to 10 (highest). Defaults to 5. Higher-priority labels win when two labels would otherwise overlap. |

### `buffer_analysis`

Create a buffer polygon layer around features. `distance` is interpreted in the layer's OWN CRS units, not automatically converted -- meters for a typical projected/UTM CRS, but DEGREES for a geographic CRS (e.g. EPSG:4326/WGS84). Buffering a WGS84 layer by 500 expecting 500 meters actually buffers by 500 degrees (most of the way around the globe), not a small error but a silently nonsensical result. If the target layer's CRS is geographic, reproject it to an appropriate projected/UTM CRS first (or check get_layers()'s crs field before calling this). To buffer only SPECIFIC features (e.g. 'buffer around alerts X and Y', not the whole layer), first select them -- select_by_attribute for one value, or highlight_features with an expression like "event_id IN ('X','Y')" for several -- then call this with only_selected=True. Without only_selected=True, this always buffers every feature in the layer, regardless of any current selection.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `distance` | number | yes | Buffer distance in the layer's own CRS units (meters for a projected CRS, degrees for a geographic one -- see this tool's own description). |
| `only_selected` | boolean | no | If true, buffer only the layer's currently-selected features instead of the whole layer. Errors if nothing is selected, rather than silently falling back to the full layer. |

### `calculate_area`

Calculate polygon area in square meters and write it into a new 'area_sqm' field on the layer. Destructive action requiring UI confirmation -- same underlying operation as field_calculator (in-place attribute mutation on the live layer).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `calculate_length`

Calculate line length in meters and write it into a new 'length_m' field on the layer. Destructive action requiring UI confirmation -- same underlying operation as field_calculator (in-place attribute mutation on the live layer).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `centroid`

Generate centroid points for polygon layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `clip_layer`

Clip vector layer by mask layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `input_layer` | string | yes |  |
| `mask_layer` | string | yes |  |

### `convert_to_singlepart`

Split multipart geometries (e.g. a MultiPolygon feature representing several separate islands) into one single-part feature per part. Useful cleanup before per-feature analysis like calculate_area or centroid, which otherwise treat all parts as one feature.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `convex_hull`

Generate the convex hull polygon(s) enclosing a layer's features -- the smallest convex polygon containing all of them. Useful for catchment/coverage-area style analysis (e.g. the outer boundary of a set of service points).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `delaunay_triangulation`

Generate a Delaunay triangulation from a point layer -- a mesh of non-overlapping triangles connecting the points, useful as a basis for terrain interpolation or network-like proximity analysis.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `diagnose_topology`

Diagnose self-intersections, slivers, exact-duplicate geometries, and (for polygon layers) overlapping features in a vector layer. Pass min_area to also flag polygons smaller than a given threshold (in the layer's CRS units squared) as small_polygons, distinct from exact zero-area slivers. Does NOT check for gaps between polygons meant to tile an area (e.g. missing coverage inside an admin boundary) -- that needs a reference boundary to diff against that this tool has no way to infer, and a heuristic based on dissolving the layer and looking for interior holes would misfire as a false gap on almost any real humanitarian admin-boundary layer (a coastline, an unmapped buffer zone, a deliberately excluded area are all real holes, not QA failures) -- that remains open, see point 4 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `min_area` | number | no | Optional. Flags polygons with 0 < area < min_area (in the layer's CRS units squared) as small_polygons, separate from exact zero-area slivers. |

### `difference_layers`

Subtract one vector layer from another (A minus B) -- e.g. 'everything outside the flood zone'. Set symmetric=true for a symmetric difference (everything in A or B but not in both) instead.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `input_layer` | string | yes | Layer to subtract from (A). |
| `overlay_layer` | string | yes | Layer to subtract (B). |
| `symmetric` | boolean | no | True for symmetric difference. Defaults to false. |

### `dissolve_layer`

Dissolve vector features optionally grouped by field.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field` | string | no |  |

### `field_calculator`

Calculate or add field using QGIS expression. Destructive action requiring UI confirmation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `new_field` | string | yes |  |
| `expression` | string | yes |  |

### `field_statistics`

Compute summary statistics (count, sum, mean, median, min, max, stdev, range) for a numeric field across every feature in a layer -- a flat project-wide summary, not per-zone (use zonal_statistics for that).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field` | string | yes |  |

### `find_nearest_features`

For each feature in input_layer, find the nearest feature(s) in near_layer and join it (distance in meters, plus the nearest feature's attributes) -- e.g. 'nearest hospital to each village'. Creates a new layer; input_layer and near_layer are unchanged.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `input_layer` | string | yes | Layer whose features get a nearest-match added, e.g. villages. |
| `near_layer` | string | yes | Layer to search for the nearest feature in, e.g. hospitals. |
| `neighbors` | integer | no | How many nearest matches per feature. Defaults to 1. |

### `fix_geometries`

Fix invalid geometries in vector layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `get_attributes`

Get list of field/attribute names for a layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `get_crs`

Get CRS authid, description, and units for layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `get_feature_count`

Get total feature count in a layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `get_layers`

Get all layers in current QGIS project with name, type, ID, CRS, feature count, and field names in one call -- covers most basic inspection needs (a vector layer's field names, a rough size check via feature_count) without a separate get_attributes round trip per layer. Point 21 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md. feature_count/fields are omitted for layers that don't have them (e.g. a raster has no attribute table).

_No parameters._

### `highlight_features`

Select features in a layer matching expression.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `expression` | string | yes |  |

### `intersect_layers`

Intersection of two vector layers.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer1` | string | yes |  |
| `layer2` | string | yes |  |

### `invert_selection`

Invert the current feature selection on a layer -- previously unselected features become selected and vice versa.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `join_by_attribute`

Join attributes from one layer to another by a shared field value (not location -- use spatial_join for that). If target_field/join_field are omitted, suggests fuzzy-matched candidate field pairs instead of running the join -- call again with the fields once you've picked one. Warns if the join field isn't unique on the join layer, since that duplicates features on the target side (1-to-many) rather than a clean 1-to-1 join.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `target_layer` | string | yes |  |
| `join_layer` | string | yes |  |
| `target_field` | string | no | Field on target_layer to join on. Omit to get fuzzy-matched suggestions. |
| `join_field` | string | no | Field on join_layer to join on. Omit to get fuzzy-matched suggestions. |

### `load_tabular_data_as_layer`

Load the FULL contents of a CSV or Excel (.xlsx/.xls) file as a real QGIS layer -- not a preview or a summary. Use this whenever the user has attached, downloaded, or referenced a spreadsheet/CSV file and wants the actual data in the project, not just a description of it. If the file has coordinate columns (e.g. latitude/longitude) or a WKT geometry column, pass x_field/y_field or wkt_field to create a real point/geometry layer; if omitted, this tool tries to auto-detect common column names on its own (for both CSV and Excel) and reports what it used -- if it can't confidently guess, it returns FIELD_SUGGESTION with the real column names instead of guessing wrong. Omit all three (or call again after a FIELD_SUGGESTION with none set) to load it as a plain non-spatial attribute table.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes | Absolute path to the .csv/.xlsx/.xls file. |
| `layer_name` | string | no |  |
| `x_field` | string | no | Longitude/X column name. |
| `y_field` | string | no | Latitude/Y column name. |
| `wkt_field` | string | no | Column containing WKT geometry strings. |
| `sheet_name` | string | no | Sheet name for Excel files with multiple sheets. Defaults to the first sheet. |
| `crs` | string | no | CRS of x_field/y_field coordinates. Defaults to EPSG:4326. |
| `delimiter` | string | no | CSV field delimiter. Defaults to ','. |

### `merge_layers`

Merge multiple vector layers into one.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_names_list` | array[string] | yes |  |

### `obfuscate_sensitive_points`

Displace or aggregate sensitive point locations (e.g. GBV survivors, individual IDP households, protection incidents) before they're mapped, exported, or included in any report -- a Do No Harm safeguard, and increasingly an explicit donor/ECHO compliance requirement. Recommend this as a step before add_incident_point/add_point_layer output or export_layer involving protection-flagged data goes anywhere -- never apply it silently or automatically without the user choosing to. Three methods: 'jitter' (random displacement within radius; radius is in the LAYER'S OWN CRS UNITS, not meters -- for a geographic CRS like EPSG:4326 a radius intended as '500 meters' would actually mean 500 DEGREES and scatter points across the globe, so reproject to a projected CRS first if a specific real-world distance matters), 'grid_snap' (collapses every point sharing a grid cell to that cell's centroid -- the strongest protection of the three, since it destroys individual-point identity rather than just displacing it; cell_size is also in the layer's own CRS units), or 'admin_unit_snap' (moves each point to the centroid of the admin-boundary polygon it falls within, from a separate polygon layer). The method and its parameter are always included in the output so they're disclosable in any report alongside the map.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Point layer with sensitive locations. |
| `method` | string | yes | One of: 'jitter', 'grid_snap', 'admin_unit_snap'. |
| `radius` | number | no | Required for 'jitter': max displacement, in the layer's own CRS units. |
| `cell_size` | number | no | Required for 'grid_snap': grid cell size, in the layer's own CRS units. |
| `admin_layer_name` | string | no | Required for 'admin_unit_snap': polygon layer of admin units to snap to. |
| `output_layer_name` | string | no | Optional name for the new layer; defaults to '{layer_name}_obfuscated'. |
| `seed` | integer | no | Optional random seed for 'jitter', for reproducible output. |

### `open_attribute_table`

Open attribute table GUI for layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `remove_layer`

Remove layer from QGIS project. Destructive action requiring UI confirmation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `rename_layer`

Rename layer in QGIS project.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `old_name` | string | yes |  |
| `new_name` | string | yes |  |

### `reproject_layer`

Reproject layer to target CRS code (e.g. 'EPSG:4326').

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `crs_code` | string | yes |  |

### `run_query`

Filter layer features using a QGIS expression.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `expression` | string | yes |  |

### `select_by_attribute`

Select features matching specific field value.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field` | string | yes |  |
| `value` | string | yes |  |

### `select_by_location`

Select features in target_layer based on their spatial relationship to reference_layer (e.g. select all points within a polygon boundary). Use method to combine with an existing selection instead of replacing it (e.g. 'add' after a select_by_attribute call to build up a combined selection, or 'intersect' to narrow one down).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `target_layer` | string | yes | Layer whose features get selected. |
| `reference_layer` | string | yes | Layer to test spatial relationship against. |
| `predicate` | string | no | Spatial relationship: 'intersects' (default), 'contains', 'within', 'touches', 'overlaps', 'crosses', 'equals'. |
| `method` | string | no | 'new' (default, replaces current selection), 'add', 'remove', or 'intersect' with the current selection. |

### `simplify_geometry`

Simplify (generalize) a layer's geometries by removing vertices within tolerance of a straight line -- reduces file size/complexity for display at smaller scales or for web export. Larger tolerance means more simplification.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `tolerance` | number | yes | Simplification tolerance in the layer's map units. |

### `spatial_join`

Join attributes from one layer to another by spatial location.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `target_layer` | string | yes |  |
| `join_layer` | string | yes |  |

### `toggle_visibility`

Show or hide a layer in layer tree.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `visible` | boolean | no |  |

### `union_layers`

Geometric union of two vector layers.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer1` | string | yes |  |
| `layer2` | string | yes |  |

### `verify_crs_compatibility`

Check if two layers share compatible Coordinate Reference Systems.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer1` | string | yes |  |
| `layer2` | string | yes |  |

### `voronoi_polygons`

Generate Voronoi polygons (Thiessen polygons) from a point layer -- each polygon covers the area closest to its point. Common for coverage/catchment analysis (e.g. 'which points are closest to each facility').

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `buffer_percent` | number | no | Extends the diagram past the point extent by this percentage, to avoid clipped edge polygons. Defaults to 0. |

### `zoom_to_feature`

Zoom map canvas to a single feature, identified either by feature_id or by an attribute expression (e.g. "governorate_name = 'Ma\'rib'"). Use expression when the feature_id isn't already known -- this looks it up and zooms in one call, instead of hand-writing PyQGIS to query for it first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `feature_id` | integer | no | Feature ID to zoom to. Provide this or expression, not both. |
| `expression` | string | no | QGIS expression selecting exactly one feature by attribute, e.g. "name = 'Ma\'rib'". Provide this or feature_id, not both. |

### `zoom_to_layer`

Zoom canvas to extent of layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

## cartographic_advisory_tools

### `recommend_visualization_method`

Recommends which styling tool fits a layer/field's actual data semantics -- geometry type, field type, cardinality, and distribution -- before you style it, instead of guessing the renderer or defaulting to whichever tool was used last. ADVISORY ONLY: returns a recommendation and rationale, never applies any styling itself -- you still call the recommended tool (or a different one, if you have good reason) yourself. Use this before any apply_*_style call on a field you haven't already styled by in this conversation, especially before a choropleth on a polygon layer, since the single most common real-world misuse is coloring raw counts instead of a rate/density.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field` | string | no | Optional. Omit for a reference/location-only map with no field to style by. |
| `intended_message` | string | no | Optional free-text hint, e.g. 'show which districts have the worst access gap' or 'show route status'. Used only to explain a recommendation more specifically -- never to override what the data itself actually supports. |

## confidence_tools

### `get_layer_confidence`

Reads a layer's current confidence/epistemic-status classification, if any was set via set_layer_confidence. Returns level=null if never tagged -- not the same as UNKNOWN, just unclassified.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `set_layer_confidence`

Tags a layer with its epistemic-status/confidence level -- OBSERVED (directly recorded, e.g. a surveyed facility location), DERIVED (computed from observed data with no modeling assumptions, e.g. a buffer or spatial join), MODELED (built from a model with real assumptions, e.g. a service area or population-exposure estimate), INFERRED (a conclusion drawn beyond what the data directly shows), or UNKNOWN (provenance genuinely unclear). Use this on any layer whose confidence level matters for how a reader should trust it -- especially anything that will be exported or printed. No automated classification exists -- only what's explicitly set here is tracked.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `level` | string | yes | OBSERVED, DERIVED, MODELED, INFERRED, or UNKNOWN. |
| `reason` | string | no | Optional short reason, e.g. 'buffer output, no field verification' or 'population estimate, WorldPop 2025 raster'. |

## data_export_tools

### `export_stored_data`

Exports everything Cartogen AI has stored for this project and this machine -- project memory notes, global memory notes/preferences, and chat history (if chat history saving is enabled in Settings) -- into one structured JSON file. Use this when the user asks what data the plugin has stored, wants a copy of their conversation/notes, or needs a data-portability export. Chat history is included only if the user has opted into 'Save chat history in the project file' -- this tool does not change that setting or read history that was never saved. The chat history it exports is only a rolling window of the most recent messages plus a short digest of older ones (see chat_history_info in the file), never a full transcript; say so when reporting it.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `output_path` | string | yes | Full file path to write the JSON export to, e.g. 'C:/Users/me/Desktop/cartogen_data_export.json'. |

## dataset_status_tools

### `advance_dataset_status`

Move a layer's QA-gate lifecycle status forward one step (e.g. STAGED -> VALIDATED), backward (to mark a regression), or re-state it -- never skipping a state. The INGESTED -> STAGED step automatically runs a P-code depth check (uniqueness + parent/child hierarchy prefix-match) when the layer has P-code-shaped fields, and auto-passes as not-applicable otherwise -- so it never blocks a non-admin-boundary layer. The STAGED -> VALIDATED step automatically runs the existing geometry-validity check (diagnose_topology) and refuses to advance if it fails, unless override=True is passed with a note justifying the bypass. The VALIDATED -> ANALYSIS_READY step runs a schema-contract check (validate_schema) instead, but ONLY when contract_name is supplied -- omit it and this transition behaves like any other unchecked one (a note is required). The CARTOGRAPHY_READY -> PUBLICATION_READY step runs a map-QA check (generate_map_product_qa_checklist) when layout_name is supplied -- refuses to advance if the layout is missing a mandatory element (map/title/legend/scale bar/north arrow) or the layer is tagged RESTRICTED/SENSITIVE, unless override=True is passed with a note justifying the bypass. Omit layout_name and this transition behaves like any other unchecked one. Every other transition has no automated check yet and requires a note explaining the manual advance. Moving backward always requires a note. Call get_dataset_status first if unsure of the layer's current status, set_dataset_status first if it isn't tracked yet, and list_schema_contracts to see available contract_name values.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `target_status` | string | yes | One of INGESTED, STAGED, VALIDATED, ANALYSIS_READY, CARTOGRAPHY_READY, PUBLICATION_READY. |
| `note` | string | no | Required for transitions with no automated check, for any backward move, and for an override. |
| `override` | boolean | no | Bypass a failed automated check. Requires note. Defaults to false. |
| `contract_name` | string | no | Only used for VALIDATED -> ANALYSIS_READY, e.g. 'health_facilities' or 'admin2'. See list_schema_contracts. |
| `layout_name` | string | no | Only used for CARTOGRAPHY_READY -> PUBLICATION_READY -- the print layout built for this map product (from create_print_layout). |

### `get_dataset_status`

Read a layer's tracked QA-gate lifecycle status (one of INGESTED, STAGED, VALIDATED, ANALYSIS_READY, CARTOGRAPHY_READY, PUBLICATION_READY), its full status-change history, and any automated check results recorded against it. Returns status=null for a layer that has never been tagged -- call set_dataset_status first to start tracking it.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `set_dataset_status`

Start QA-gate lifecycle tracking on a layer that isn't tracked yet, tagging it with a starting status (defaults to INGESTED). Refuses to run on a layer that already has a tracked status -- use advance_dataset_status to move an already-tracked layer forward or back instead, so this can't accidentally erase real QA history.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `status` | string | no | Starting status. One of INGESTED, STAGED, VALIDATED, ANALYSIS_READY, CARTOGRAPHY_READY, PUBLICATION_READY. Defaults to INGESTED. |
| `note` | string | no | Optional note explaining why tracking starts at this status. |

## hazard_monitoring_tools

### `fetch_gdacs_disaster_alerts` _(two-phase)_

Fetch current UN-coordinated disaster alerts from GDACS (Global Disaster Alert and Coordination System) -- earthquakes, floods, tropical cyclones, volcanoes, wildfires, droughts -- each with a human-assigned Green/Orange/Red severity, and load them as a point layer. GDACS's own terms of use (verified 2026-09-12) state that its automated alerts and impact estimations 'may require further validation' and 'should not be used for decision making without prior confirmation of their validity' -- pass this caveat along if a user asks about acting on a specific alert. Free, no API key. Defaults to Orange and above (excludes minor/localized Green advisories) -- pass min_alert_level='Green' to include everything. IMPORTANT: bbox (when given) is [min_lon, min_lat, max_lon, max_lat], same convention as fetch_nasa_active_fires and fetch_nasa_eonet_events. IMPORTANT: if the user names a specific place ('the latest GDACS alerts for Yemen') rather than giving coordinates, pass country (e.g. country='Yemen') -- omitting BOTH bbox and country returns every alert worldwide, which is very rarely what a place-scoped request actually wants. Re-running this tool REPLACES the layer's features with the latest fetch, so it's safe to schedule on a recurring interval. Each returned alert's 'unit' value is also stored on the layer as an 'event_id' field -- to act on SPECIFIC named alerts (e.g. 'buffer around alerts 123,456'), select by that field (select_by_attribute for one, or highlight_features with "event_id IN ('123','456')" for several) rather than operating on the whole layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `bbox` | array[number] | no | Optional [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees. Omit for global coverage. |
| `min_alert_level` | string | no | Minimum alert level to include: 'Green', 'Orange' (default), or 'Red'. |
| `country` | string | no | Optional country name to scope results to (case-insensitive substring match against GDACS's own per-alert country field, e.g. 'Yemen'). Use this or bbox (or both) whenever the user named a specific place -- don't leave both empty for a place-scoped request. |
| `layer_name` | string | no | Name for the layer. Defaults to 'GDACS Disaster Alerts'. Re-fetching with the same name replaces its features rather than duplicating them. |

### `fetch_nasa_active_fires` _(two-phase)_

Fetch near-real-time active fire/thermal-anomaly detections from NASA FIRMS (VIIRS satellite instrument) for a bounding box, and load them as a point layer. Needs a free NASA FIRMS API key configured in Settings -- if missing, this returns a clear error with a link to get one. IMPORTANT: bbox is [min_lon, min_lat, max_lon, max_lat] (matches search_stac_satellite_imagery's convention) -- NOT the [south, west, north, east] order fetch_building_footprints uses. Re-running this tool (e.g. via schedule_recurring_workflow) REPLACES the layer's features with the latest fetch rather than accumulating duplicates, so it's safe to schedule on a recurring interval to watch for new fire activity -- run_monitoring_workflow will then report new/disappeared detections automatically.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `bbox` | array[number] | yes | [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees. |
| `days` | integer | no | How many days back to look, 1-10. Defaults to 1. |
| `min_confidence` | string | no | Minimum detection confidence to include: 'low', 'nominal' (default), or 'high'. |
| `layer_name` | string | no | Name for the layer. Defaults to 'NASA Active Fires'. Re-fetching with the same name replaces its features rather than duplicating them. |

### `fetch_nasa_eonet_events` _(two-phase)_

Fetch open (or closed/all) natural events from NASA EONET -- wildfires, severe storms, volcanoes, floods, sea/lake ice, drought, dust/haze, and more -- for an optional bounding box, and load them as a point layer (each event's most recent known position). Free, no API key. IMPORTANT: bbox is [min_lon, min_lat, max_lon, max_lat], same convention as fetch_nasa_active_fires and search_stac_satellite_imagery. Re-running this tool REPLACES the layer's features with the latest fetch, so it's safe to schedule on a recurring interval. Each returned event's 'unit' value is also stored on the layer as an 'event_id' field -- to act on a SPECIFIC named event, select by that field (select_by_attribute, or highlight_features for several) rather than operating on the whole layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `bbox` | array[number] | no | Optional [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees. Omit for global coverage. |
| `category` | string | no | Optional EONET category id to filter to, e.g. 'wildfires', 'severeStorms', 'volcanoes', 'floods', 'drought'. |
| `days` | integer | no | How many days back to look. Defaults to 20. |
| `status` | string | no | 'open' (default), 'closed', or 'all'. |
| `layer_name` | string | no | Name for the layer. Defaults to 'NASA EONET Events'. Re-fetching with the same name replaces its features rather than duplicating them. |

### `generate_situation_dashboard`

Fetch live hazard data (NASA active fires, NASA EONET natural events, GDACS disaster alerts) for a bounding box and export it all as one interactive HTML situation dashboard in a single call -- the fastest way to answer 'what hazards are happening in this area right now'. Internally calls fetch_nasa_active_fires/fetch_nasa_eonet_events/fetch_gdacs_disaster_alerts (each skipped gracefully, not fatally, if its source errors -- e.g. no FIRMS API key configured) then generate_html_dashboard. IMPORTANT: bbox is [min_lon, min_lat, max_lon, max_lat], same convention as the 3 fetch tools it calls.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `bbox` | array[number] | yes | [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees. |
| `output_path` | string | no | Optional output HTML file path. |
| `title` | string | no | Optional dashboard title. |
| `include_fires` | boolean | no | Include NASA FIRMS active fires. Defaults to true. |
| `include_eonet` | boolean | no | Include NASA EONET natural events. Defaults to true. |
| `include_disasters` | boolean | no | Include GDACS disaster alerts. Defaults to true. |

## impedance_tools

### `build_composite_impedance_field`

Builds a single blended per-segment speed field on a road network layer -- combining OSM highway-class baseline speed, OSM surface-condition penalty, an optional damage/passability field, and an optional DEM-derived slope penalty into one number in km/h. Feeds directly into calculate_service_area/travel_time_matrix/optimize_delivery_route's existing speed_field parameter -- run this first, then pass output_field's name as speed_field to those tools with strategy='fastest' for realistic routing that avoids unpaved/damaged/steep roads instead of treating every segment as equally fast. Requires highway_field/surface_field to already exist on the layer (e.g. from fetch_osm_features) -- a layer without them still gets a flat default speed with no penalties, not an error.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `road_network_layer` | string | yes | Line layer representing the road/path network. |
| `highway_field` | string | no | Field holding the OSM highway=* class (e.g. 'primary', 'track'). Defaults to 'highway'. |
| `surface_field` | string | no | Field holding the OSM surface=* value (e.g. 'paved', 'gravel'). Defaults to 'surface'. |
| `damage_field` | string | no | Optional numeric field, 0.0-1.0, giving each segment's passability (1.0=fully passable, 0.0=impassable, e.g. from a road-status assessment). Non-numeric values default to 1.0 (unknown = assumed passable). |
| `dem_layer` | string | no | Optional DEM raster layer. When given, each segment's endpoints are sampled for elevation and a slope penalty applied -- steeper segments get a lower effective speed. |
| `output_field` | string | no | Name of the new field to write the blended speed (km/h) into. Defaults to 'impedance_cost'. |

## pcode_validation_tools

### `check_pcode_hierarchy`

Check that each feature's child P-code (e.g. admin2_pcode) is prefixed by its own parent P-code (e.g. admin1_pcode) on the same row -- the real OCHA/HDX COD-AB convention (admin2 'YE1201' under admin1 'YE12'). This is a string-prefix check on two sibling attributes, NOT a spatial containment check -- it does not verify the admin2 polygon actually sits inside the admin1 polygon's geometry, only that the codes are structurally consistent. Auto-detects both fields from common P-code field names if not given.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `child_pcode_field` | string | no | Optional. Defaults to an admin2 P-code alias. |
| `parent_pcode_field` | string | no | Optional. Defaults to an admin1 P-code alias. |

### `check_pcode_uniqueness`

Check that every P-code value in a layer is unique across its features -- flags duplicate admin-unit codes that would silently corrupt a P-code join in calculate_severity_index or calculate_presence_gap. Tries the admin2 P-code field aliases (admin2_pcode/adm2_pcode/ADM2_PCODE) automatically if pcode_field isn't given.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `pcode_field` | string | no | Optional. Field to check; auto-detected from common P-code field names if omitted. |

## processing_allowlist_tools

### `run_allowlisted_processing_algorithm`

Runs one QGIS Processing algorithm from a fixed, pre-approved list -- prefer this over execute_pyqgis_script when the task is achievable via a single Processing algorithm that isn't already covered by a dedicated tool. Safer than execute_pyqgis_script: this never runs Python code at all, only calls the named algorithm with the given parameters, so there is no code-execution surface to sandbox. Only algorithms already used elsewhere in this codebase are allowed -- an unlisted algorithm id is rejected outright, not run. Output is always kept in-memory as a new project layer (auto-named), never written to a file path -- use a dedicated export tool (export_layer, export_to_csv) afterward if a file is actually needed. Don't specify an OUTPUT/OUTPUT_LINES parameter yourself -- it's set automatically and any value you give is ignored. Any string parameter value matching a currently-loaded layer's name is automatically resolved to that layer; every other value is passed through as-is.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `alg_id` | string | yes | Processing algorithm id, e.g. 'native:buffer'. Must be one of: ['gdal:cliprasterbymasklayer', 'gdal:contraststretch', 'gdal:merge', 'gdal:pansharpening', 'gdal:rastercalculator', 'native:aspect', 'native:buffer', 'native:cellstatistics', 'native:centroids', 'native:clip', 'native:convexhull', 'native:countpointsinpolygon', 'native:creategrid', 'native:dbscanclustering', 'native:delaunaytriangulation', 'native:difference', 'native:dissolve', 'native:extractbylocation', 'native:fixgeometries', 'native:hillshade', 'native:intersection', 'native:joinattributesbylocation', 'native:joinattributestable', 'native:joinbynearest', 'native:kmeansclustering', 'native:mergevectorlayers', 'native:multiparttosingleparts', 'native:rastersampling', 'native:reclassifybytable', 'native:reprojectlayer', 'native:selectbylocation', 'native:serviceareafrompoint', 'native:shortestpathpointtolayer', 'native:shortestpathpointtopoint', 'native:simplifygeometries', 'native:slope', 'native:symmetricaldifference', 'native:union', 'native:voronoipolygons', 'native:zonalstatisticsfb', 'qgis:heatmapkerneldensityestimation', 'qgis:idwinterpolation', 'qgis:statisticsbycategories', 'qgis:tininterpolation', 'qgis:zonalstatistics', 'saga:kmeansclassificationforgrid', 'saga:supervisedclassificationforgrids'] |
| `params` | object | yes | Flat dict of algorithm parameters, e.g. {"INPUT": "my_layer", "DISTANCE": 500}. String values matching a loaded layer's name are resolved to that layer automatically. |
| `new_layer_name` | string | no | Name to give the algorithm's output layer once added to the project. Defaults to '<alg_id>_output' if omitted -- and an omitted name is treated as a signal that this output is an internal/scratch step (e.g. a reprojection before a buffer), so it's added to the project hidden (unchecked in the layer tree) rather than cluttering the visible map. Give this an explicit name whenever the output IS the deliverable you want the user to see. |

## provenance_tools

### `get_provenance_record`

Read a layer's machine-readable provenance record without writing anything to disk: the QGIS version, its full tool-execution lineage (what tool chain produced/modified it, see get_layer_lineage-tracked history), and its QA-gate lifecycle status/history/checks (see get_dataset_status). Use this to inspect provenance in-conversation; use write_provenance_sidecar instead to save it as a real JSON file.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `write_provenance_sidecar`

Write a layer's machine-readable provenance record (QGIS version, tool-execution lineage, QA-gate status/history/checks) to a real JSON sidecar file -- named '<source_file>.provenance.json' beside the layer's own on-disk source when one can be resolved, or an explicit output_path when supplied. Falls back to a Desktop file named after the layer (with a warning in the result) for a layer with no real on-disk source, e.g. a scratch/memory layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `output_path` | string | no | Optional explicit file path for the sidecar. Omit to derive one from the layer's own source, or fall back to Desktop. |

## qa_checklist_tools

### `generate_map_product_qa_checklist`

Assembles a QA checklist for one map product -- a layer, optionally paired with a print layout -- covering data readiness, cartographic completeness, disclosure/sensitivity, and export/provenance. Reads from what's already tracked (dataset_status, layout item ids, provenance) rather than re-deriving or guessing any of it. Point 26 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md -- distinct from this plugin's own docs/RELEASE_SMOKE_TEST.md, which verifies the plugin's tools work in a live QGIS session, not an individual map product's readiness.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `layout_name` | string | no | Optional print layout built for this product (from create_print_layout) -- checked for the mandatory MAP_MAIN/TITLE/LEGEND/SCALEBAR/NORTH_ARROW elements. Omit to skip the cartography section. |
| `output_path` | string | no | Optional exported file path (e.g. create_print_layout's own output_path) to verify it actually exists on disk with real content. Omit to skip the export-integrity section. |

## representation_tools

### `analyze_layer_for_visualization`

Analyze a layer's geometry, feature count, spatial density, overlap ratio, and attribute semantics (rates vs raw counts, nominals, temporal) to inform cartographic representation decisions.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Name of the layer in the QGIS project to analyze. |

### `apply_recommended_representation`

Apply a recommended representation candidate (e.g. 'point_cluster', 'point_displacement', 'point_heatmap', 'polygon_choropleth_rate', 'polygon_proportional_centroid') to a layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `representation_id` | string | yes | Candidate representation id to apply, e.g. 'point_cluster', 'point_heatmap', 'polygon_choropleth_rate'. |
| `target_field` | string | no | Optional attribute field if the representation requires one. |

### `explain_current_representation`

Inspect a layer's active renderer and explain whether it fits the data distribution and geometry, flagging potential cartographic issues (such as raw count choropleth distortion or dense point crowding).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `recommend_map_representation`

Evaluate candidate map representations for a layer based on spatial density, geometry, and analytical question (e.g. 'Where are they concentrated', 'Which are largest', 'What category'). Returns scored candidates and interactive action options.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Name of the layer to evaluate. |
| `user_intent` | string | no | The analytical question or intent, e.g. 'show density', 'compare size', 'show status category'. |
| `target_field` | string | no | Optional attribute field to style or symbolize by. |

## schema_contract_tools

### `list_schema_contracts`

List the machine-readable dataset schema contracts available to validate_schema (currently health_facilities and admin2 -- see validators/contracts/*.json). Each contract declares required fields (by acceptable name aliases, since real-world admin/pcode field names vary by source), expected field types, and optional controlled-vocabulary domains.

_No parameters._

### `validate_schema`

Check a vector layer's fields -- presence, type, and any controlled-vocabulary values -- against a named schema contract (see list_schema_contracts for available names). Field matching is case-insensitive and checks a contract's full alias list, not one fixed name, so e.g. 'ADM2_PCODE' from a COD-AB download and 'admin2_pcode' from a hand-built layer both satisfy the same required field. Returns missing_fields/type_mismatches/value_violations and an overall passed flag -- never blocks anything by itself, but feeds advance_dataset_status's VALIDATED -> ANALYSIS_READY gate when a contract_name is supplied there.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `contract_name` | string | yes | e.g. 'health_facilities' or 'admin2'. See list_schema_contracts. |

## sensitivity_tools

### `get_layer_sensitivity`

Reads a layer's current sensitivity/disclosure classification, if any was set via set_layer_sensitivity. Returns level=null if never tagged -- not the same as PUBLIC, just unclassified.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `set_layer_sensitivity`

Tags a layer with a sensitivity/disclosure classification -- PUBLIC, INTERNAL, RESTRICTED, or SENSITIVE. Use for a layer containing individual beneficiary locations, protection incident details, or anything else that shouldn't be shared broadly. export_layer/export_to_csv check this and add an advisory warning (not a block -- the export still completes) when exporting a RESTRICTED/SENSITIVE layer. No automated classification exists -- only what's explicitly set here is tracked. When the cloud-provider data-protection gate is on, moving a RESTRICTED/SENSITIVE layer to PUBLIC/INTERNAL needs the user's confirmation in the UI -- do not try to work around that by re-tagging.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `level` | string | yes | PUBLIC, INTERNAL, RESTRICTED, or SENSITIVE. |
| `reason` | string | no | Optional short reason shown in the export warning, e.g. 'contains individual beneficiary GPS coordinates'. |

## tool_operations_tools

### `get_tool_operation_type`

Look up which operation-type category (READ, CREATE, MODIFY, DELETE, or PUBLISH) a registered Cartogen AI tool falls into -- e.g. before deciding whether a planned call is safe to make without asking first. Returns an error if the name isn't a registered tool.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tool_name` | string | yes | Exact registered tool name, e.g. 'remove_layer'. |

### `list_tools_by_operation_type`

List every registered tool classified under one operation-type category (READ, CREATE, MODIFY, DELETE, or PUBLISH). Use this to see, for example, every tool that can write an external file (PUBLISH) or remove/replace project state (DELETE).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `operation_type` | string | yes | One of READ, CREATE, MODIFY, DELETE, PUBLISH. |

## transaction_tools

### `get_turn_transaction_log`

List every tool call made so far during THIS turn (this one user request), each tagged with its operation type and, when it added a new layer, whether it can be undone with undo_last_operation. Use this before undo_last_operation to see what's actually available to undo -- it does not reach back into earlier turns/messages, only the current one.

_No parameters._

### `undo_last_operation`

Reverse the most recent undoable tool call made THIS turn (see get_turn_transaction_log to check what qualifies first). Covers: a call that added a new layer (removes it); remove_layer (restores the removed layer and its data); field_calculator/calculate_area/calculate_length (restores the field's prior values, or deletes it if it didn't exist before); apply_categorized_style/apply_graduated_style/apply_graduated_symbol_style (restores the prior style); set_dataset_status/set_layer_sensitivity/set_layer_confidence/run_query (restores the prior value). It cannot undo load_project or any other in-place edit not in that list -- a real, separate, still-open gap, not something this tool silently skips without saying so. Destructive action requiring UI confirmation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `confirmed` | boolean | no | Set true only after the user has confirmed the undo. |
