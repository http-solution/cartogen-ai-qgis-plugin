# Tool Reference

Auto-generated from the live tool registry (296 tools) by `docs/generate_tools_reference.py` -- do not hand-edit, regenerate instead so this can never drift from the actual code.

Flags: **network-only** tools bypass the main-thread QGIS dispatcher entirely (pure HTTP, safe from any background thread); **two-phase** tools split a network fetch (background thread) from the QGIS-touching part (main thread); **task-management** tools are excluded from auto-advance in the Task Manager.

## AI Imagery Feature Extraction

### `extract_features_from_imagery` _(two-phase)_

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

Build a composite multi-indicator severity/needs index across admin units (a simple weighted min-max index in the style of INFORM/JIAF -- exploratory analysis only: it is NOT the JIAF method, so never call its result JIAF-compliant or an official severity classification), the standard basis for prioritizing which areas receive funding. Takes several numeric indicator fields already on a polygon layer's attribute table (e.g. food insecurity %, displacement %, protection incidents, WASH coverage), min-max normalizes each so higher always means worse, applies relative weights, and returns a 0-1 composite score plus a 1-5 severity class per unit, ranked worst-first. Use invert_indicators for fields where a HIGHER value means a BETTER situation (e.g. % with water access) -- otherwise well-served areas score as high-severity. Units missing any indicator are excluded and listed, never imputed. Always report the weights and any excluded units alongside the ranking, since both change how it should be read. Results are capped to the worst 50 units (see truncated/scored_units) -- output_field still writes the score for every unit to the layer regardless of the cap, so styling/mapping the full set is unaffected; only the returned JSON is capped.

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
| `geometry_column` | string | no | Name of the geometry column in the query result; omit for a non-spatial result table. |

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

Export a layer to a file: a vector layer to ESRI Shapefile, GeoJSON, GPKG or KML; a raster layer to GeoTIFF (format 'tif'). A relative output_path is anchored to the project folder; the reply's output_path is the real location.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `format` | string | yes |  |
| `output_path` | string | no |  |
| `only_selected` | boolean | no |  |

### `export_layers_to_dxf`

Export one or more vector layers to a single DXF file for CAD software (AutoCAD and similar). A DXF holds geometry and layer names, not attribute tables or QGIS styling: say so if the user expects either. output_path is optional -- omit it to save under the project's data/20_processed folder (or the QGIS profile folder if the project is not saved yet); a relative path is anchored to the project folder and the reply's output_path is the real location. At most 20 layers per file. Replacing an existing file asks the user first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_names` | array[string] | yes |  |
| `output_path` | string | no |  |

### `export_layers_to_spreadsheet`

Export one or more vector layers or tables to a single spreadsheet (Excel .xlsx, or .ods) with one sheet per layer, attributes only (no styling). Use it when the user asks for an Excel or spreadsheet file; export_to_csv is for CSV. output_path is optional -- omit it to save under the project's data/20_processed folder (or the QGIS profile folder if the project is not saved yet); a relative path is anchored to the project folder and the reply's output_path is the real location. At most 20 layers per file. Replacing an existing file asks the user first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_names` | array[string] | yes |  |
| `output_path` | string | no |  |

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
| `crs_stated_by_user` | boolean | no | true ONLY when the user's own message named the CRS of these coordinates (for example 'in EPSG:3857'). When the user gave projected numbers WITHOUT a CRS, pass the project CRS and leave this false: if that CRS is not the project's the tool asks the user instead of placing the point. |

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
| `allow_whole_country` | boolean | no | Set true ONLY after the user agreed to download the whole country file (worldpop.org cannot send just a window; the real size is shown first). Without extent_layer/bbox and without this, the tool refuses. |

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

Answer 'which facilities are within / beyond N hours (or N metres) of this origin' FAST. Runs ONE service area from origin_layer (seconds, the same engine as calculate_service_area) and labels every facility in facility_layer 'within' when it lies on or within snap_distance_m of a road reached inside travel_cost, else 'beyond'. Use THIS instead of travel_time_matrix for any 'beyond/within X of the origin' question over many facilities: travel_time_matrix ties every destination into the road graph and took ~44 minutes for 3,369 facilities. Adds a copy of the facility layer with access_class and dist_to_reach_m fields, plus the service-area layers. For a DISTANCE budget (strategy 'shortest') over up to 200 facilities each facility is routed and 'within' means road distance PLUS the straight leg from the road to the facility is inside the budget; the result says method 'routed' and snap_distance_m is not used. For a time budget, or more facilities, it is an APPROXIMATION to state in the answer: it ignores the access leg from the road to the facility (up to snap_distance_m) and is not a per-facility routed cost; pass a small snap_distance_m (for example 50) so a facility far from the road is not counted as reached.

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

Find a good visiting order for a set of delivery/distribution stops -- e.g. 'what order should the truck visit these 8 distribution points'. Uses a standard nearest-neighbor + 2-opt heuristic to pick the *order* (not a guaranteed globally-optimal order). Without road_network_layer, ordering uses straight-line distance and the result is a stop order only -- do NOT draw a straight line between the stops and present it as a route on an operational map; it is not a routable path. Pass road_network_layer to make the ordering itself road-network-aware (real road distance between every pair of stops, not straight-line) and to build an actual road-snapped route line, added to the project and safe to render as a real route. speed_field/direction_field (same meaning as calculate_service_area's) only affect ordering when road_network_layer is given. Not a substitute for a full commercial VRP solver with vehicle capacity/time-window constraints. If the start (a hub, depot) and the stops are in DIFFERENT point layers, name the others in additional_stops_layers -- do not write a script to merge them first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `stops_layer` | string | yes | Point layer of stops to visit. |
| `additional_stops_layers` | array[string] | no | Optional other point layers whose features are added to the stops (for example the depot layer when the stops are in another one). They are reprojected into stops_layer's CRS, and start_stop_name can name a stop from any of them. |
| `start_stop_name` | string | no | Optional name (from the layer's first attribute field) of the stop to start from. Defaults to the first feature. |
| `road_network_layer` | string | no | Optional line layer representing the road/path network. When given, visiting order uses real road-network distance (not straight-line) and a road-snapped route line is built and added to the project -- required before the output may be rendered as a route on a map. |
| `speed_field` | string | no | Optional numeric field on road_network_layer giving per-segment speed in km/h. Only affects ordering when road_network_layer is given. |
| `direction_field` | string | no | Optional field on road_network_layer marking one-way segments (e.g. OSM's 'oneway' tag). Only affects ordering when road_network_layer is given. |
| `value_forward` | string | no | direction_field value meaning forward-only travel. Defaults to 'yes' (OSM convention). |
| `value_backward` | string | no | direction_field value meaning backward-only travel. Defaults to '-1' (OSM convention). |
| `value_both` | string | no | direction_field value meaning both directions. Defaults to 'no' (OSM convention). |
| `strategy` | string | no | 'shortest' (distance-based, default) or 'fastest' (travel time). Use 'fastest' when the user asks for the fastest route or a travel time; it needs road_network_layer. The time is an ESTIMATE from speed_field (km/h per segment) or default_speed, not measured traffic. |
| `default_speed` | number | no | Speed in km/h for road segments with no speed_field value. Only used with strategy='fastest'. Defaults to 50. |

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
| `speed_field` | string | no | Optional numeric field on road_network_layer giving per-segment speed in km/h, same meaning as in calculate_service_area. Pass it when the request names one (for example the speed_blocked field written by apply_network_barriers): without it, blocked or slowed roads are ignored and the people-beyond figure is wrong. Only affects routing when strategy='fastest'. |
| `direction_field` | string | no | Optional one-way field on road_network_layer, same meaning as in calculate_service_area. |

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

Calculate road-network distance or travel time from each origin point to each destination point -- e.g. delivery distance from each warehouse to each distribution site. Returns a matrix of costs (metres for strategy='shortest' -- real-world distance whatever the layers' CRS is -- or hours for strategy='fastest') keyed by origin then destination. Requires a line layer representing the road network, not straight-line distance. Without speed_field, every segment is treated as one flat default_speed regardless of surface or condition -- when the network layer has a per-segment speed or condition field, pass it as speed_field with strategy='fastest' for a more realistic matrix. direction_field makes one-way roads one-way instead of assuming every segment is traversable both directions. The costs are along the road only: the result also gives access_leg_m (straight distance from each destination to its nearest road); ADD it when the question is total travel within a budget. SLOW for many destinations (every destination is tied into the road graph, which QGIS does by brute force; ~44 minutes for 3,369): for 'which facilities are within/beyond N of this origin' use classify_facilities_by_access instead; destination layers over 200 features use a single shortest-path tree per origin (fast; each destination is charged the cost to its projected point on the nearest road segment) when the QGIS network classes are available.

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
| `profile` | string | no | Name of a saved map profile (a JSON file the organisation keeps in the project's cartogen_profiles folder or the QGIS profile folder) that sets page size, orientation, export preset, file name pattern and required elements. Explicit arguments beat the profile. |
| `page_size` | string | no | Page size: 'A4' (default), 'A3', 'A2' or 'A1'. The same layout is scaled up, and the map shows the same area larger. |
| `preset` | string | no | Export purpose instead of a dpi number: 'draft' (96), 'web' (150) or 'print' (300). An explicit dpi wins. |
| `output_format` | string | no | Only when output_path is a FOLDER: 'pdf' (default), 'png' or 'jpg'. The file is then named <title>_<date>.<format>. |
| `body_text` | string | no | Optional summary/sitrep text shown in a panel on the layout (e.g. priority findings, data sources). |
| `zoom_to_layer` | string | no | Name of a layer to fit the map to its full extent before capturing it, e.g. the national boundary layer for a full-country sitrep map. Omit to use whatever extent the canvas currently shows. |
| `template` | string | no | 'standard' (default), 'access_map' or 'sitrep'. 'access_map': for the result of a service-area / facility-access analysis. Fits the map to the reach layer when zoom_to_layer is omitted, lists the reach polygon, access points and cost-graded roads first in the legend, and (when body_text is empty) adds a short 'how to read this map' guide for the layers present. 'sitrep': a one-page situation report; body_text is the situation summary, key_figures and sources fill the KEY FIGURES and SOURCES sections, and a standing handling note (estimates, no exact locations of people or sensitive sites) and the preparation date are always added. |
| `key_figures` | array[object] | no | For template='sitrep': up to 8 headline figures, each copied from a tool result (never estimated or remembered), e.g. {label: 'People within 1 hour of a clinic', value: '412,000 (estimate)', source: 'population_access_gap'}. |
| `key_figures_from` | object | no | For template='sitrep': take the headline figures straight from a layer, e.g. {layer_name: 'admin_units', label_field: 'ADM2_EN', value_field: 'people_in_need', top_n: 3}. The numbers are read from the layer, so they cannot be mistyped; prefer this over typing figures. Any typed key_figures whose number is not found in a project layer (a value, or a total, minimum, maximum, mean or count of a numeric field) is marked 'not found in the project data' on the layout and listed in the reply. |
| `sources` | array[string] | no | For template='sitrep': the data sources behind the figures, e.g. ['OCHA COD-AB 2024', 'WorldPop 2020']. |
| `include_inset_map` | boolean | no | Add a small locator/inset map (zoomed out ~6x from the main map, same center) showing the main map's location within its wider region. Defaults to true. |

### `export_layout_atlas`

Exports one file PER FEATURE of a coverage layer from an existing print layout -- e.g. one PDF per district, one PNG per health facility catchment -- using QgsLayoutAtlas. This is the full-atlas half of point 15 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md; list_layout_items/update_layout_item_text (the other half) address items within ONE layout, this generates MANY layouts (one per feature). Only works on a layout built by create_print_layout, since it re-points that layout's MAP_MAIN item to follow the atlas -- there is no addressable map item on a hand-built layout to atlas-drive. Each output file is named from filename_field's value on that feature (e.g. a district-name field), sanitized for use as a filename; a non-unique or empty field value across features will silently overwrite an earlier output with the same name, so pick a field that's actually unique per feature (a P-code, not a display name that repeats). A map or coverage layer tagged RESTRICTED or SENSITIVE makes the export wait for the user's confirmation.

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

Save the current QGIS project (all layers, styles, and layout) to a .qgz/.qgs file. Use this as a checkpoint before a risky multi-step operation, or at the end of a task so the user's work is persisted. Temporary (memory) layers are NOT saved with their data -- the result lists them and they must be exported to a file separately.

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
| `align_to_first` | boolean | no | If the rasters are not on one pixel grid, warp the others onto the first raster's grid (its CRS, extent and cell size) instead of refusing. The result says which raster was the reference and the resampling used. Default false: refuse. |
| `resampling` | string | no | With align_to_first: 'bilinear' (default, for continuous values such as reflectance), 'nearest' (for classes or counts) or 'cubic'. |

### `calculate_ndvi`

Calculate NDVI (Normalized Difference Vegetation Index) from Red and Near-Infrared raster bands -- the standard remote-sensing measure of vegetation health/greenness/density: 'how green is this area', 'is this crop/vegetation healthy', 'vegetation health check'. Output ranges roughly -1 to 1: values near 1 indicate dense healthy vegetation, near 0 bare soil or built-up areas, negative values open water. Produces a new single-band raster layer named 'NDVI' added to the project with QGIS's default (unstretched, low-contrast) rendering -- follow up with apply_raster_stretch(layer_name='NDVI') to apply a readable diverging color ramp (auto-selected for NDVI-named layers) instead of leaving it flat/unstretched.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `red_layer` | string | yes |  |
| `nir_layer` | string | yes |  |
| `align_to_first` | boolean | no | If the rasters are not on one pixel grid, warp the others onto the first raster's grid (its CRS, extent and cell size) instead of refusing. The result says which raster was the reference and the resampling used. Default false: refuse. |
| `resampling` | string | no | With align_to_first: 'bilinear' (default, for continuous values such as reflectance), 'nearest' (for classes or counts) or 'cubic'. |

### `calculate_ndwi`

Calculate NDWI (Normalized Difference Water Index) from Green and Near-Infrared raster bands -- the standard remote-sensing measure of surface water/moisture: 'how much water is in this area', 'map surface water extent', 'is there flooding here'. Output ranges roughly -1 to 1: values above ~0 typically indicate open water, below ~0 vegetation/dry land. For a flood-specific before/after comparison rather than a single-image water map, use calculate_raster_change_detection instead. Produces a new single-band raster layer named 'NDWI' with QGIS's default (unstretched) rendering -- follow up with apply_raster_stretch(layer_name='NDWI') to apply a readable diverging color ramp (auto-selected for NDWI-named layers) instead of leaving it flat/unstretched.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `green_layer` | string | yes |  |
| `nir_layer` | string | yes |  |
| `align_to_first` | boolean | no | If the rasters are not on one pixel grid, warp the others onto the first raster's grid (its CRS, extent and cell size) instead of refusing. The result says which raster was the reference and the resampling used. Default false: refuse. |
| `resampling` | string | no | With align_to_first: 'bilinear' (default, for continuous values such as reflectance), 'nearest' (for classes or counts) or 'cubic'. |

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
| `dem_vertical_unit` | string | no | Vertical unit of the DEM's elevation values: 'm' (default), 'ft' or 'us_ft'. A raster does not carry its vertical unit, so say so if the DEM is in feet. |

### `estimate_population_exposure`

Sum population within each polygon of a vector layer, using an already-loaded population raster (e.g. from fetch_worldpop_population) -- e.g. 'how many people live within 5km of this facility' (combine with buffer_analysis first to build the area), or 'population per district' (pass admin boundaries directly). Does not modify the vector layer; returns one total per zone (keyed by name, made unique when names repeat) and says whether zones overlap. Returns an ESTIMATE derived from a gridded population raster, not a verified count of people actually present -- report results as 'estimated population within <area>', never as a confirmed or affected-population figure, unless field data corroborates it.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `population_raster_layer` | string | yes | A population-per-pixel raster layer (e.g. from fetch_worldpop_population). |
| `area_layer` | string | yes | Polygon layer to sum population within, one total per feature. |
| `raster_unit` | string | no | 'people_per_cell' (default; counts per cell, e.g. WorldPop ppp) or 'people_per_km2' (a density raster: each cell is multiplied by its area before summing). A raster does not carry its unit; a layer named like a density raster is refused unless this is set. |
| `output_layer_name` | string | no | Optional: also add a NEW polygon layer with this name holding each zone's estimated population (field pop_estimate), styled in exposure classes. The area layer itself is never changed. |

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

Enhance raster image contrast using histogram equalization. Writes a NEW 8-bit raster (0-255) of one band; no-data cells stay no-data. A global equalisation of the band, for display and visual interpretation: the values are no longer the original measurements.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `raster_layer` | string | yes |  |
| `band` | integer | no | Band to equalise, default 1. |

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

Calculate slope map from DEM layer. Elevations are taken as metres unless dem_vertical_unit says 'ft' or 'us_ft'.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `dem_layer` | string | yes |  |
| `dem_vertical_unit` | string | no | Vertical unit of the DEM's elevation values: 'm' (default), 'ft' or 'us_ft'. A raster does not carry its vertical unit, so say so if the DEM is in feet. |

### `supervised_classification`

Supervised classification using training polygons.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `training_layer` | string | yes |  |

### `unsupervised_classification`

Unsupervised K-Means raster classification of up to the first 8 bands into num_classes spectral classes (1..num_classes; 0 = no data). Classes are statistical clusters of pixel values, NOT land-cover categories: label them yourself. Reproducible with a seed; works through the raster in blocks, so memory is not the limit, but a raster over 400 million cells is refused (clip it first).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `num_classes` | integer | yes | Number of clusters, 2 to 50. |
| `seed` | integer | no | Random seed (default 0). |

### `weighted_overlay_analysis`

Combine multiple rasters into a single weighted suitability/risk surface -- e.g. 'best sites for a new clinic' combining slope, distance-to-road, and population density rasters with different weights. Each input raster should already be normalized to a comparable scale (e.g. 0-1 or 0-100) before combining -- this tool weights and sums them, it doesn't rescale them. All rasters must share the same CRS and cover roughly the same extent/resolution, or the result is meaningless; mismatched CRS is rejected outright rather than silently misaligned.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `raster_layers` | array[string] | yes | 2 to 6 raster layer names to combine. |
| `weights` | array[number] | yes | One weight per raster, same order as raster_layers. Don't need to sum to 1 -- normalized automatically. |
| `align_to_first` | boolean | no | If the rasters are not on one pixel grid, warp the others onto the first raster's grid (its CRS, extent and cell size) instead of refusing. The result says which raster was the reference and the resampling used. Default false: refuse. |
| `resampling` | string | no | With align_to_first: 'bilinear' (default, for continuous values such as reflectance), 'nearest' (for classes or counts) or 'cubic'. |

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

Compute pixel-wise differential change between two temporal rasters (after minus before) -- 'what changed between these two satellite images', 'compare before and after images for damage', 'show me the damage from before to after'. The core building block calculate_damage_exposure_severity composes into a full damage assessment (zonal stats per admin unit, building exposure counts, severity classing) -- use this tool directly only for the raw pixel-difference layer itself, calculate_damage_exposure_severity for a per-district severity score. Produces a new raster layer named 'change_detection_<after>_vs_<before>' added to the project with a diverging ramp symmetric about zero (blue = decrease, red = increase, no change transparent) so the change pattern is visible straight away.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `raster_before` | string | yes |  |
| `raster_after` | string | yes |  |
| `align_to_first` | boolean | no | If the two rasters are not on one pixel grid, warp the 'before' raster onto the 'after' raster's grid instead of refusing; the result says what was done. Default false: refuse. |
| `resampling` | string | no | With align_to_first: 'bilinear' (default), 'nearest' (classes/counts) or 'cubic'. |

### `inspect_canvas_visually`

LOOK at the current map: captures the map canvas as a picture you can see (at most 1,280 pixels on the long edge), sent to you right after this result together with the legend and the visible layers as text. Use it for 'what is wrong with this map', 'does it look right', 'what does the map show'. Optional extent_layer: look at that layer's extent instead of the current view (the canvas is not moved). If the model cannot see pictures you get the legend and layer list as text instead.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `prompt_guidance` | string | no |  |
| `extent_layer` | string | no | Optional: name of a layer; the picture shows that layer's extent instead of the current view. |

### `search_stac_satellite_imagery` _(network-only)_

Search STAC API (Earth Search / Sentinel-2) for satellite scenes by bounding box and date range. Pass max_cloud_cover (percent) when the user names a cloud limit: the filter is applied by the service, so every scene returned meets it. The reply lists only scenes the service returned (newest first); never add scenes from memory.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `bbox` | array[number] | yes |  |
| `start_date` | string | yes |  |
| `end_date` | string | yes |  |
| `limit` | integer | no |  |
| `max_cloud_cover` | number | no | Only scenes with eo:cloud_cover below this percent (0-100). |

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
| `color_from` | string | no | Optional start colour of an explicit ramp, as plain words ('pale yellow') or #rrggbb. Use with color_to when the user names the colours. |
| `color_to` | string | no | Optional end colour of an explicit ramp ('dark red' or #rrggbb). Overrides the automatic ramp and cluster tint. |
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

Change layer symbol fill/line color. Pass the colour the user said ("dark red", "pale yellow", "light blue") or a hex code.

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

Geocode a SINGLE address/place name into lat/lon via Nominatim API; the result also carries the place's bounding box (bbox_south_west_north_east and bbox_west_south_east_north) for tools that take an area. For multiple locations in one request, use geocode_batch instead -- one call per place will run out of tool-call steps before finishing a long list.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `location_name` | string | yes |  |

### `geocode_batch` _(network-only)_

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

Search internet for real-time information or facts; every hit has a URL: cite them. For a sourced, structured answer or for news use web_research. NOT for incidents, disasters or conflict events in a place: use find_incident_reports for those (named reliable sources, dates, links).

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
| `sublayer` | string | no | name of ONE layer/table inside a multi-layer file (GeoPackage, FileGDB, KML, GPX, SpatiaLite); omit to open the first and be told what else the file holds |

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
| `output_name` | string | no | Name for the new buffer layer, used exactly as given when the user asked for a specific name. Omit to get '<layer>_buffer_<distance>'. |

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

For each feature in input_layer, find the nearest feature(s) in near_layer and join it (plus the nearest feature's attributes) -- e.g. 'nearest hospital to each village'. The 'distance' field is in the layer's own CRS units; distance_m is added in real metres (ellipsoidal) whenever those units are not metres, so use distance_m when the layers are in latitude/longitude. Creates a new layer; input_layer and near_layer are unchanged.

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

### `get_layer_extent`

Get a layer's extent, in its own CRS and transformed to WGS84 degrees. Use this -- never a remembered or estimated bounding box -- whenever a tool needs a bbox in degrees (fetch_osm_features, fetch_building_footprints, search_stac_satellite_imagery, fetch_worldpop_population). The result gives the box in BOTH orders, named: bbox_south_west_north_east for the OSM and building-footprint tools, bbox_west_south_east_north for the STAC search. Pass layer_name='canvas' for the current map view.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | A layer name, or 'canvas' for the current map view. |

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

Load the FULL contents of a CSV or Excel (.xlsx/.xls) file as a real QGIS layer -- not a preview or a summary. Use this whenever the user has attached, downloaded, or referenced a spreadsheet/CSV file and wants the actual data in the project, not just a description of it. If the file has coordinate columns (e.g. latitude/longitude) or a WKT geometry column, pass x_field/y_field or wkt_field to create a real point/geometry layer; if omitted, this tool tries to auto-detect common column names on its own (for both CSV and Excel) and reports what it used -- if it can't confidently guess, it returns FIELD_SUGGESTION with the real column names instead of guessing wrong. A file with no coordinate columns (a forecast, survey or 3W table) is loaded as a plain non-spatial attribute table by passing as_table=true; omitting the coordinate arguments alone just returns the suggestion again.

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
| `as_table` | boolean | no | true: load as a plain attribute table with no geometry (a forecast, survey or 3W file). Skips coordinate detection. |

### `merge_layers`

Merge multiple vector layers into one.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_names_list` | array[string] | yes |  |

### `obfuscate_sensitive_points`

Displace or aggregate sensitive point locations (e.g. GBV survivors, individual IDP households, protection incidents) before they're mapped, exported, or included in any report -- a Do No Harm safeguard, and increasingly an explicit donor/ECHO compliance requirement. Recommend this as a step before add_incident_point/add_point_layer output or export_layer involving protection-flagged data goes anywhere -- never apply it silently or automatically without the user choosing to. Three methods: 'jitter' (random displacement within radius; radius is in the LAYER'S OWN CRS UNITS, not meters -- for a geographic CRS like EPSG:4326 a radius intended as '500 meters' would actually mean 500 DEGREES and scatter points across the globe, so reproject to a projected CRS first if a specific real-world distance matters), 'grid_snap' (collapses every point sharing a grid cell to that cell's centroid -- the strongest protection of the three, since it destroys individual-point identity rather than just displacing it; cell_size is also in the layer's own CRS units), or 'admin_unit_snap' (moves each point to the centroid of the admin-boundary polygon it falls within, from a separate polygon layer). The method and its parameter are always included in the output so they're disclosable in any report alongside the map. A MultiPoint feature is obfuscated part by part and written as one output point per part, with the same attributes.

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

## allocation_tools

### `calculate_allocation_envelope`

Split a budget the user gives across areas in proportion to need (optionally times population), with optional ceiling and floor per area, optional rounding, and areas below a need threshold left out. This is an ADVISORY CALCULATION of an envelope, not a recommendation of who should receive what: the budget, the need field, the exponent, the ceiling/floor and the exclusion threshold are the user's decisions, so ask for them and state them with the result. Need can be a severity score, a people-in-need count or any non-negative field; population is optional. Areas with a missing or negative value are excluded and listed, never imputed. If ceilings stop the whole budget being spent the rest is reported as unallocated. Optionally writes each area's amount to the layer (needs confirmation). Never invent a budget, a cost per person or a coefficient.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Vector layer with the areas (e.g. admin polygons). |
| `budget` | number | yes | The total to split, in the user's own unit. Must be given by the user. |
| `need_field` | string | yes | Non-negative numeric field that drives the split (e.g. a 0-1 severity score or people in need). |
| `population_field` | string | no | Optional numeric field; when given the weight is need x population. |
| `unit_name_field` | string | no | Optional field used to label areas in the results. |
| `need_exponent` | number | no | Weight = need ** exponent. Default 1 (proportional). Above 1 favours the neediest areas more, below 1 spreads more evenly. |
| `max_share_per_unit` | number | no | Optional ceiling per area as a share of the budget, above 0 and at most 1 (e.g. 0.15). |
| `min_amount_per_unit` | number | no | Optional floor guaranteed to every area with a positive weight. |
| `exclude_need_below` | number | no | Optional: areas with need below this get nothing. |
| `rounding` | number | no | Optional: round amounts to multiples of this (e.g. 100); the total is preserved. |
| `unit_label` | string | no | Optional label for the budget's unit (e.g. 'USD'); echoed in the result. |
| `output_field` | string | no | Optional: write each area's amount to the layer under this field name. |

## attribute_edit_tools

### `add_feature_from_wkt`

Add one feature to an existing layer from WKT geometry (POINT, LINESTRING, POLYGON ...). crs is the CRS of the WKT coordinates (default: the layer's own); it is transformed in code. attributes is {field: value}. The geometry type must match the layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `wkt` | string | yes |  |
| `attributes` | object | no |  |
| `crs` | string | no | e.g. EPSG:4326 |

### `add_field`

Add an empty field to a layer. field_type: string, integer, long, double, date or datetime.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field_name` | string | yes |  |
| `field_type` | string | no |  |

### `clear_selection`

Deselect all features: of one layer, or of every layer in the project when layer_name is omitted.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | no |  |

### `delete_features`

Delete features from a layer: those matching an expression, or the currently selected ones (only_selected). Destructive: a preview with the exact count is shown for confirmation first. Never deletes everything unless the expression says so.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `expression` | string | no |  |
| `only_selected` | boolean | no |  |

### `delete_field`

Delete a field (column) and all its values from a layer. Destructive: a preview is shown for confirmation first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field_name` | string | yes |  |

### `rename_field`

Rename a field of a layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field_name` | string | yes |  |
| `new_name` | string | yes |  |

### `select_all_features`

Select every feature of a layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `select_by_expression`

Select features of a layer with any QGIS expression (for example "population" > 1000 AND "type" = 'school'). mode: replace (default), add, remove or intersect with the current selection.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `expression` | string | yes |  |
| `mode` | string | no | replace, add, remove or intersect |

### `set_attribute_value`

Set one field to a value on specific features: pick them by feature_id or by an expression. Numeric fields need numbers; a typo is refused, not turned into NULL. Use the string null to clear a value. Changes data: a preview with the count is shown first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field` | string | yes |  |
| `value` | string | yes |  |
| `feature_id` | integer | no |  |
| `expression` | string | no |  |

## barrier_tools

### `apply_network_barriers`

Put blocked or degraded places into a road network for routing: destroyed bridges, checkpoints, flooded stretches or any other barrier layer (points, lines or polygons such as a flood extent). Every road segment within buffer_m metres of a barrier is blocked (mode='block') or has its speed multiplied by penalty_factor (mode='penalise'); all other segments keep their speed. Writes the result to a new numeric speed field (km/h) on the road layer, and draws the affected segments as a separate red (blocked) or orange (slowed) layer '<roads>_barrier_affected' so the effect is visible on the map; pass that field as speed_field to calculate_service_area / travel_time_matrix / optimize_delivery_route. Blocked segments are REMOVED from the network by those tools (any strategy), so nothing can cross them; slowed segments only matter with strategy='fastest'. Pass speed_field (e.g. from build_composite_impedance_field) to keep realistic base speeds; without it unaffected segments are 30 km/h.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `road_network_layer` | string | yes | Line layer representing the road network. |
| `barrier_layer` | string | yes | Layer of barriers: points (bridge, checkpoint), lines or polygons (flood extent). |
| `buffer_m` | number | no | Distance in metres around each barrier within which roads are affected. 0 = only roads that touch/cross the barrier. Default 50. |
| `mode` | string | no | 'block' (default) or 'penalise'. |
| `penalty_factor` | number | no | For mode='penalise': speed multiplier between 0 and 1 (e.g. 0.25). Ignored for 'block'. |
| `speed_field` | string | no | Optional existing numeric speed field (km/h) to start from, e.g. from build_composite_impedance_field. |
| `output_field` | string | no | Name of the new speed field. Default 'barrier_speed'. |

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

## corridor_tools

### `generate_contours`

Make contour lines from a DEM raster layer at a fixed elevation interval (in the DEM's own elevation units, normally metres), as a NEW LINE LAYER with an 'ELEV' field -- the usual meaning of 'draw / make / create contour lines of the DEM, every 100'. Use set_raster_relief instead only when the user wants the raster itself shown as contours (render / style) without a new layer. The interval is the vertical spacing between lines, NOT the accuracy of the terrain: the result reports the DEM's pixel size and source so the user can judge what the lines can show. Refuses very large rasters. When the request names a DEM that is already in the project ("the dem", "smoke_dem"), call this directly with that layer: do not fetch a new DEM and do not plan a fetch first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `raster_layer` | string | yes | Name of the DEM raster layer. |
| `interval` | number | no | Elevation step between contour lines, default 10. |
| `band` | integer | no | Band number, default 1. |
| `output_name` | string | no |  |

### `split_lines_by_zones`

Split a line layer (a road, a highway, a pipeline) by a polygon layer of zones (exclusion zones, flood areas, buffers) into compromised pieces (inside any zone) and clear pieces (outside every zone), style them red and green, and report both the total passable length in km and the longest continuous passable segment in km (they are different numbers). Lengths are ellipsoidal. Connected line features are joined first, so a road stored as many OSM segments counts as one continuous road. Creates a new layer; the inputs are not changed.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `line_layer` | string | yes | Name of the line layer. |
| `zone_layer` | string | yes | Name of the polygon layer (for example the checkpoint buffers). |
| `output_name` | string | no | Optional name of the result layer. |

## critical_link_tools

### `analyze_critical_links`

Screen a road network for bottlenecks: how much origin-to-destination demand has its shortest path through each road segment. A segment with a high load is one many routes depend on -- closing it would push all of them onto other roads. This is a SCREENING measure of dependence, not a closure simulation and not a traffic forecast: one shortest path per pair (cost = distance, or time from the speed field), no congestion, convoy size or security, and the load counts OD pairs unless weight fields are given. Origins are capped (default 50, max 200) and a time budget stops the run between origins and labels the result partial; for national road data clip the network to the area first. Closed roads (negative speed) are left out. Draws the roads graded by load in a new layer and returns the heaviest segments.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `road_network_layer` | string | yes | Line layer with the road network. |
| `origins_layer` | string | yes | Point layer of origins (e.g. warehouses, hubs). |
| `destinations_layer` | string | no | Point layer of destinations (e.g. facilities, settlements). Default: the origins layer. |
| `strategy` | string | no | 'shortest' (distance, default) or 'fastest' (time). |
| `default_speed` | number | no | km/h for segments without a speed, used only for 'fastest'. Default 50. |
| `speed_field` | string | no | Optional per-segment speed (km/h). A negative value marks a closed road, which is removed. |
| `direction_field` | string | no | Optional one-way field. |
| `value_forward` | string | no | direction_field value for forward-only. Default 'yes'. |
| `value_backward` | string | no | direction_field value for backward-only. Default '-1'. |
| `value_both` | string | no | direction_field value for both ways. Default 'no'. |
| `origin_weight_field` | string | no | Optional non-negative numeric field weighting each origin. |
| `destination_weight_field` | string | no | Optional non-negative numeric field weighting each destination (e.g. population). |
| `max_origins` | integer | no | Origins to use, at most 200. Default 50; more origins are left out and counted. |
| `max_snap_m` | number | no | A destination further than this from the road graph is left out. Default 2000 m. |
| `time_budget_s` | number | no | Stop between origins after this many seconds. Default 120. |
| `top_n` | integer | no | Heaviest segments to return. Default 10. |
| `output_layer_name` | string | no | Name of the output line layer. Default 'critical_links'. |

## data_export_tools

### `export_stored_data`

Exports everything Cartogen AI has stored for this project and this machine -- project memory notes, global memory notes/preferences, and chat history (if chat history saving is enabled in Settings) -- into one structured JSON file. Use this when the user asks what data the plugin has stored, wants a copy of their conversation/notes, or needs a data-portability export. Chat history is included only if the user has opted into 'Save chat history in the project file' -- this tool does not change that setting or read history that was never saved. The chat history it exports is only a rolling window of the most recent messages plus a short digest of older ones (see chat_history_info in the file), never a full transcript; say so when reporting it.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `output_path` | string | yes | Full file path to write the JSON export to, e.g. 'C:/Users/me/Desktop/cartogen_data_export.json'. |

## data_layer_tools

### `add_postgis_layer`

Add a PostGIS table or view to the project as a layer, using a database connection already saved in QGIS (Browser panel > PostgreSQL). Give the connection name, schema and table; geometry_column and key_column are only needed when the table has several geometry columns or no primary key. Read-only data access: it adds a layer, it changes nothing in the database. Use execute_read_only_sql for a query instead of a whole table.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `connection_name` | string | yes |  |
| `table` | string | yes |  |
| `schema` | string | no |  |
| `geometry_column` | string | no |  |
| `key_column` | string | no |  |
| `layer_name` | string | no |  |

### `create_virtual_layer`

Create a virtual layer: a live SQL (SQLite/SpatiaLite) query over the layers in the project, for example SELECT a.name, count(b.id) AS n FROM districts a JOIN points b ON ST_Contains(a.geometry, b.geometry) GROUP BY a.name. Reference layers by their project layer name. Only a single SELECT is accepted; paths, URLs, comments, ATTACH and other statements are refused. The layer is not saved to disk and follows the source layers.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `sql` | string | yes |  |
| `geometry_column` | string | no | name of the geometry column in the result, if it is not detected |

### `load_layer_definition`

Load a QGIS layer definition file (.qlr) into the project: the layers it holds come with their styles. The layers read their own data sources, so a .qlr is only as safe as the files and services it points to.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes |  |

### `package_layers_offline`

Package vector layers into ONE GeoPackage file for offline use or hand-over, keeping their styles and metadata (QGIS native:package). layer_names is the list of vector layers; file_path ends in .gpkg. only_selected packs just the selected features. An existing file is only replaced after confirmation. Raster layers are not packaged.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_names` | array[string] | yes |  |
| `file_path` | string | yes |  |
| `only_selected` | boolean | no |  |

### `save_layer_definition`

Save chosen layers of the project, with their styles, to a QGIS layer definition file (.qlr) that can be loaded into other projects. layer_names is the list of layers. An existing file is only replaced after confirmation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_names` | array[string] | yes |  |
| `file_path` | string | yes |  |

## data_source_tools

### `add_basemap`

Add a background map to the QGIS project from a fixed list: openstreetmap, opentopomap, satellite (Esri imagery), esri streets, carto light, carto dark. The layer is placed at the bottom of the layer tree. Tiles are loaded by QGIS directly from the provider.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `basemap` | string | yes | openstreetmap, topo, satellite, esri streets, carto light, carto dark |

### `add_web_layer`

Add a web map or feature service to the project. service_type: xyz (tile URL with {z}/{x}/{y}), wms, wmts, wfs or arcgis_feature. Only https URLs are accepted. wms/wmts need layer (the service layer name), wmts also tile_matrix_set, wfs needs layer (typename).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `service_type` | string | yes |  |
| `url` | string | yes |  |
| `layer_name` | string | no |  |
| `layer` | string | no | service layer / typename |
| `crs` | string | no |  |
| `image_format` | string | no |  |
| `tile_matrix_set` | string | no |  |
| `style` | string | no |  |

### `create_empty_layer`

Create a new EMPTY vector layer (or a table with no geometry) with the fields you choose, ready for digitising. geometry_type: point, line, polygon, multipoint, multiline, multipolygon or none. fields: list of {name, type} with type string, integer, long, double, date or datetime. By default a scratch (in-memory) layer is added; give file_path ending .gpkg, .shp or .geojson to create a file.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `geometry_type` | string | yes |  |
| `fields` | array[object] | no |  |
| `crs` | string | no | e.g. EPSG:4326 (default) |
| `file_path` | string | no | optional .gpkg/.shp/.geojson to create on disk |

### `find_broken_layers`

List the project layers whose data source cannot be read (moved or deleted file, lost drive) with the path they point to. Read-only.

_No parameters._

### `repair_layer_source`

Point a broken layer at its data again. Give new_path if you know where the file is; otherwise the project folder (and search_folder, if given) is searched for a file with the same name. One match is applied; several are listed so you can choose one.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `new_path` | string | no |  |
| `search_folder` | string | no |  |

### `save_layer_as`

Save a vector layer to a file in another CRS and/or with only some fields and/or only the selected features (the QGIS 'Save As' options). format: gpkg, shp, geojson or kml. The original layer is not changed and the new file is NOT added to the project unless add_to_project is true.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `output_path` | string | yes |  |
| `format` | string | yes |  |
| `crs` | string | no | target CRS, e.g. EPSG:4326; omit to keep the layer's CRS |
| `fields` | array[string] | no | field names to keep; omit for all |
| `only_selected` | boolean | no |  |
| `add_to_project` | boolean | no |  |

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

## dem_tools

### `fetch_dem`

Download elevation (a DEM raster) for an area from the Copernicus DEM GLO-30 open dataset (about 30 m, no account or key needed) and add it to the project. Give the area as a layer name (its extent), as a bounding box in degrees (west, south, east, north), or as a centre point (lat, lon) with radius_km. The result is a surface model (includes buildings/trees), not bare earth, about 30 m resolution; the reply records source, tiles used, retrieval date, vertical datum and the required attribution. Refuses very large areas. Use generate_contours or slope_analysis on the result. ONLY for an area with no DEM in the project yet: when the request names a DEM layer that is already loaded ("the dem", "smoke_dem"), use that layer and do not call this.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | no | Name of a layer whose extent defines the area. |
| `west` | number | no |  |
| `south` | number | no |  |
| `east` | number | no |  |
| `north` | number | no |  |
| `lat` | number | no | Centre latitude (with lon and radius_km). |
| `lon` | number | no | Centre longitude. |
| `radius_km` | number | no | Half-width of the square around the centre, km. |
| `output_path` | string | no | Optional GeoTIFF path; relative paths are anchored to the project folder. |
| `output_name` | string | no | Optional layer name. |

## edit_ops_tools

### `change_field_type`

Change the data type of a field to string, integer, long or double, converting the values. Values that cannot be converted become NULL and numbers lose their fraction when going to integer: the preview says how many. The field moves to the end of the table.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `field` | string | yes |  |
| `new_type` | string | yes |  |

### `merge_features`

Merge (union) several features of a layer into one: those matching an expression or the selected ones. The first feature keeps its attributes and gets the combined geometry; the others are deleted. Needs at least two features. Destructive: a preview is shown first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `expression` | string | no | QGIS expression choosing the features |
| `only_selected` | boolean | no | use the currently selected features instead |

### `redo_manual_edit`

Redo the last undone edit step on a layer that is in edit mode.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `set_layer_editing`

Start editing a layer, save its edits, or discard them (action: start, save or discard). Discarding unsaved edits is destructive and needs confirmation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `action` | string | yes | start, save or discard |

### `set_layer_filter`

Set or clear a layer's filter (definition query): only features matching the filter are shown and used. The filter is a plain condition in the data source's own syntax, such as "population" > 1000. Statements, comments and semicolons are refused. clear=true removes the filter. The data is not changed.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `filter` | string | no |  |
| `clear` | boolean | no |  |

### `split_features_by_line`

Cut features of a polygon or line layer along a line given as WKT (LINESTRING(x1 y1, x2 y2, ...)) in the layer's CRS or in the CRS given. Splits the features matching an expression or the selected ones that the line crosses. Changes data: a preview is shown first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `expression` | string | no | QGIS expression choosing the features |
| `only_selected` | boolean | no | use the currently selected features instead |
| `line_wkt` | string | yes |  |
| `crs` | string | no | e.g. EPSG:4326 |

### `transform_features`

Move, rotate and/or scale features of a layer: those matching an expression, or the selected ones (only_selected). move_x and move_y are in the layer's units, rotate_degrees is clockwise about each feature's centre, scale_factor scales about each feature's centre. Changes geometry: a preview with the exact count is shown for confirmation first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `expression` | string | no | QGIS expression choosing the features |
| `only_selected` | boolean | no | use the currently selected features instead |
| `move_x` | number | no |  |
| `move_y` | number | no |  |
| `rotate_degrees` | number | no |  |
| `scale_factor` | number | no |  |

### `undo_manual_edit`

Undo the last edit step on a layer that is in edit mode (the layer's own undo history, including edits made by hand). Use undo_last_operation for assistant operations on a layer not in edit mode.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

## elevation_tools

### `set_layer_elevation`

Change a layer's elevation settings (used by elevation profiles and 3D views). Raster: enabled, mode 'surface' (the cells are heights) or 'fixed_range', band, z_offset, z_scale. Vector (no on/off switch): clamping 'absolute', 'relative' or 'terrain', z_offset, z_scale, extrusion (metres). Only the values you give are changed; the result lists the settings read back.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `enabled` | boolean | no |  |
| `mode` | string | no |  |
| `band` | integer | no |  |
| `z_offset` | number | no |  |
| `z_scale` | number | no |  |
| `clamping` | string | no |  |
| `extrusion` | number | no |  |

### `set_project_terrain`

Set the project's terrain used by elevation profiles and 3D views: source 'flat' (optional offset) or 'dem' (a raster layer, optional offset and scale). Stored in the project; nothing is written to the data.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `source` | string | yes |  |
| `layer_name` | string | no |  |
| `offset` | number | no |  |
| `scale` | number | no |  |

## engineering_tools

### `assess_watershed_hydrology_request`

Preflight a watershed/peak-flow engineering request before any result is reported. It normalizes a DMS outlet and identifies the measured data and cited design inputs still required. A coordinate plus return period is insufficient: never invent a DEM-derived basin, IDF intensity, runoff coefficient, elevation drop, flow length, Tc, or peak flow. Call this first for coordinate-only watershed requests.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `location` | string | yes | Outlet location in DMS form. |
| `return_period_years` | number | yes | Requested design return period in years. |
| `dem_source` | string | no | Loaded DEM layer or authoritative DEM dataset and resolution, if available. |
| `idf_source` | string | no | Local authoritative IDF station/curve/publication, if available. |
| `runoff_coefficient` | number | no | Locally justified Rational Method runoff coefficient C, if available. |

### `calculate_rational_watershed_peak_flow`

Calculate H, main-channel slope, Kirpich channel-flow Tc, and Rational Method peak discharge from explicit measured inputs. First call it WITHOUT rainfall_intensity_mm_h to get Tc, then read the cited local IDF curve at that duration and call again with the intensity, its duration, its source and the runoff coefficient. It does not delineate a watershed and must never receive guessed area, length, elevations, intensity, or C.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `area_km2` | number | yes | Delineated watershed area in km². |
| `flow_length_km` | number | yes | Longest hydraulic flow-path/main-channel length in km; not total stream length. |
| `upstream_elevation_m` | number | yes | DEM elevation at the selected hydraulically remote upstream point in metres. |
| `outlet_elevation_m` | number | yes | DEM elevation at the snapped outlet in metres, using the same vertical datum. |
| `return_period_years` | number | yes | Design return period in years. |
| `rainfall_intensity_mm_h` | number | no | Local IDF rainfall intensity in mm/h for the return period and Tc duration. Omit on the first call to get Tc. |
| `intensity_duration_minutes` | number | no | Duration in minutes used to read/interpolate the supplied IDF intensity. |
| `intensity_source` | string | no | Authoritative local IDF station, curve, publication, and edition/date. |
| `runoff_coefficient` | number | no | Dimensionless Rational Method runoff coefficient C, locally justified. |

### `parse_dms_location`

Convert a user-supplied latitude/longitude in degrees-minutes-seconds (DMS) to an exact WGS84 decimal-degree outlet coordinate. Use this instead of manually converting DMS. This only normalizes the coordinate; it does not delineate a watershed or infer elevations.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `location` | string | yes | DMS latitude and longitude, including N/S and E/W hemispheres. |

## event_data_tools

### `fetch_ucdp_conflict_events` _(two-phase)_

Fetch organised-violence events (state-based conflict, non-state conflict, one-sided violence against civilians) from UCDP, the Uppsala Conflict Data Program's Candidate Events dataset, filtered by country name, bounding box and dates, and load them as a point layer with deaths (best, low, high estimates), conflict name, location precision and event clarity. Free, no API key; downloaded from ucdp.uu.se and cached for 12 hours. NOT live: candidate data is preliminary and lags real time by weeks, so always state the dataset's latest event date. IMPORTANT: bbox is [min_lon, min_lat, max_lon, max_lat]. Dates are 'YYYY-MM-DD'. Re-running REPLACES the layer's features. Cite UCDP (CC BY 4.0).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `country` | string | no | Country name or part of it, e.g. 'Yemen' or 'Sudan'. Omit for all countries. |
| `bbox` | array[number] | no | Optional [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees. |
| `start_date` | string | no | Earliest event date, 'YYYY-MM-DD'. |
| `end_date` | string | no | Latest event date, 'YYYY-MM-DD'. |
| `min_deaths` | integer | no | Only events with at least this many deaths (UCDP best estimate). Defaults to 0. |
| `max_events` | integer | no | Most events to load (newest first). Defaults to 1000, at most 5000. |
| `layer_name` | string | no | Name for the layer. Defaults to 'UCDP Conflict Events'. |

### `fetch_usgs_earthquakes` _(two-phase)_

Fetch recent earthquakes from the USGS (United States Geological Survey) for an optional bounding box and load them as a point layer coloured by magnitude band, with magnitude, depth, time, alert level, tsunami flag and a link per event. Free, no API key. IMPORTANT: bbox is [min_lon, min_lat, max_lon, max_lat], same convention as fetch_nasa_eonet_events. Defaults: last 7 days, magnitude 4.5 or more, up to 1000 events. Re-running REPLACES the layer's features, so it is safe to schedule.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `bbox` | array[number] | no | Optional [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees. Omit for global coverage. |
| `days` | integer | no | How many days back (1 to 365). Defaults to 7. |
| `min_magnitude` | number | no | Smallest magnitude to include. Defaults to 4.5. |
| `max_events` | integer | no | Most events to return (newest first). Defaults to 1000, at most 5000. |
| `layer_name` | string | no | Name for the layer. Defaults to 'USGS Earthquakes'. |

## fact_check_tools

### `search_fact_checks` _(network-only)_

Look up whether a CLAIM, VIDEO, PHOTO or RUMOUR has recently been fact-checked, in the published feeds of named fact-checking outlets (Snopes, PolitiFact, FactCheck.org, Full Fact, Lead Stories and the Arabic-language Fatabyyano). Use it when the user asks 'is this true', 'was this video really from <place>', 'has this been debunked' or wants to verify a social-media report before mapping it. Give the distinctive words of the claim (place, event, person), not a whole sentence. Returns each matching check with the outlet, date, link and a short summary, and ALWAYS says which outlets answered or failed and that this covers only each outlet's newest entries: no match is NOT evidence that a claim is true, false or unchecked, so never say that. Reuters, AFP, Africa Check and AP cannot be asked (they refuse automated requests). Quote the outlet's conclusion as theirs and give the link; do not add your own verdict.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | Distinctive words of the claim, e.g. 'Hodeidah port strike video' or 'Taiz protest'. |
| `days` | integer | no | Only checks published in the last N days (default 60). |
| `max_results` | integer | no | Most matches to return, 1-50 (default 15). |
| `sources` | array[string] | no | Optional subset of ['snopes', 'politifact', 'factcheck_org', 'full_fact', 'lead_stories', 'fatabyyano']; default all. |

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

## humanitarian_look_tools

### `apply_humanitarian_look`

Style a layer's analysis-result field the way humanitarian maps expect, after calculate_severity_index, calculate_population_in_need, calculate_presence_gap, calculate_damage_exposure_severity, calculate_mcda_ranking or calculate_allocation_envelope wrote it (their results carry a `map_look` hint with the exact arguments). look='severity': a 0-1 score in five equal classes yellow to dark red that match the tool's own 1-5 classes; 'people_in_need', 'exposure' or 'allocation': a count or amount in quantile classes; 'presence_gap': gap / covered / unmatched; 'rank': the top_k ranked units dark. Changes only the layer's renderer (nothing is written to the data); units with no value in the field are not drawn. Only call it when the user wants the result shown on the map or accepts the offer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | The layer that holds the result field. |
| `look` | string | yes | severity: a 0-1 composite severity score (calculate_severity_index, calculate_damage_exposure_severity): five equal-interval classes, yellow to dark red, the same classes the tools report; people_in_need: a people / population count (calculate_population_in_need): quantile classes in purple; exposure: an exposed-population count: quantile classes in orange-brown; allocation: an allocation amount (calculate_allocation_envelope): quantile classes in green; presence_gap: the gap / covered / unmatched status from calculate_presence_gap; jiaf_severity: a JIAF 2 severity PHASE 1-5 (jf_pre_sev, jf_fin_sev): phase colours 1 none/minimal to 5 catastrophic; a unit with no phase is drawn grey as not assessed; jiaf_review_pin: JIAF 2 PiN review status (jf_pin_st): which units have no flag, were closed in bulk, were decided, or still wait for the group; jiaf_review_severity: JIAF 2 severity review status (jf_sev_st): preliminary accepted, decided, pending the group, or incomplete sector coverage; jiaf_count: a small JIAF 2 count per unit (jf_npinfl, jf_nsevfl, jf_nsec40, jf_nsev45): how many flags or sectors; zero its own class; ipc_phase: an IPC acute food insecurity phase 1-5 (ipc_phase from import_humanitarian_table): the IPC phase colours; an area with no phase is grey, not phase 1; inform_risk: an INFORM score on its 0-10 scale (inf_risk, inf_haz, inf_vuln, inf_coping): the five published classes very low to very high; damage_class: UNOSAT damage classes on a point layer (destroyed, severe, moderate, possible, none), matched on the file's own wording such as 'Severe Damage'; measure: any measured number (zonal mean, road speed, impedance cost): five quantile classes light to dark blue, low to high; rank: a rank field (calculate_mcda_ranking, <prefix>_rank): the top_k units dark, the next top_k mid, the rest pale |
| `field` | string | yes | The result field to style. |
| `top_k` | integer | no | For look='rank': how many top-ranked units to emphasise. Defaults to 10. |

## impedance_tools

### `build_composite_impedance_field`

Builds a single blended per-segment speed field on a road network layer -- combining OSM highway-class baseline speed, OSM surface-condition penalty, an optional damage/passability field, and an optional DEM-derived slope penalty into one number in km/h. Feeds directly into calculate_service_area/travel_time_matrix/optimize_delivery_route's existing speed_field parameter -- run this first, then pass output_field's name as speed_field to those tools with strategy='fastest' for realistic routing that avoids unpaved/damaged/steep roads instead of treating every segment as equally fast. Requires highway_field/surface_field to already exist on the layer (e.g. from fetch_osm_features) -- a layer without them still gets a flat default speed with no penalties, not an error.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `road_network_layer` | string | yes | Line layer representing the road/path network. |
| `highway_field` | string | no | Field holding the OSM highway=* class (e.g. 'primary', 'track'). Defaults to 'highway'. |
| `surface_field` | string | no | Field holding the OSM surface=* value (e.g. 'paved', 'gravel'). Defaults to 'surface'. |
| `damage_field` | string | no | Optional numeric field, 0.0-1.0, giving each segment's passability (1.0=fully passable, 0.0=closed: the segment is removed from the network by the routing tools, e.g. from a road-status assessment). Non-numeric values default to 1.0 (unknown = assumed passable). |
| `dem_layer` | string | no | Optional DEM raster layer. When given, each segment's endpoints are sampled for elevation and a slope penalty applied -- steeper segments get a lower effective speed. |
| `output_field` | string | no | Name of the new field to write the blended speed (km/h) into. Defaults to 'impedance_cost'. |
| `dem_vertical_unit` | string | no | Vertical unit of the DEM's elevation values: 'm' (default), 'ft' or 'us_ft'. A raster does not carry it. |

## incident_search_tools

### `find_incident_reports` _(two-phase)_

Find incident and hazard reports for a country / place and a time window from a FIXED list of reliable sources, with the source, its rating and a link on every record: GDACS (UN alerts), USGS (earthquakes), NASA EONET (storms, fires, volcanoes, floods), UCDP (armed conflict events; preliminary, weeks old) and ReliefWeb (declared disasters; listed, not mapped). Records with a position are loaded as a point layer. Use this INSTEAD of search_web for 'what incidents / disasters / conflict events happened in <place>' questions. News is searched only when sources includes 'news' (unverified headlines, placed by the place named in the headline, lowest rating); fact-checkers and social media are never searched. The reply lists every source that could not be asked: always say which sources were checked and that an empty result is not proof nothing happened. Free, no keys. IMPORTANT: give a country (or place name) and/or bbox [min_lon, min_lat, max_lon, max_lat]; days is 1 to 365 (default 30). Re-running REPLACES the layer's features.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `country` | string | no | Country or place name, e.g. 'Yemen' or 'Sudan'. Matched by name against each source. |
| `bbox` | array[number] | no | Optional [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees. |
| `days` | integer | no | How many days back (1 to 365). Defaults to 30. |
| `sources` | array[string] | no | Optional subset of: gdacs, usgs, eonet, ucdp, reliefweb, news. Default: the five agency sources. Add 'news' (or use only ['news']) when the user asks for NEWS or media reports. |
| `max_reports` | integer | no | Most records to return (newest first). Defaults to 200, at most 500. |
| `layer_name` | string | no | Name for the layer. Defaults to 'Incident reports'. |

## jiaf_engine

### `compute_jiaf_preliminary`

Compute the PRELIMINARY JIAF 2 figures from sector inputs (support for the JIAF 2 process; NOT the JIAF method, not endorsed by OCHA or the IASC; never call the result JIAF-compliant or official). Per unit: the preliminary joint PiN (the highest of the eight main sectors' PiN -- the Mosaic Method; never an average, never a sum across sectors; AoRs excluded), the PiN flags 1-6 of Reference Table 3A, the preliminary intersectoral severity from the overlap of sectoral severities, and the severity flags 1-4 of Table 3B1. The national figure is the sum over units. This is not the Final PiN or the final severity: those are group decisions for flagged units, recorded later, and nothing here decides them. Intersectoral severity is per unit; there is no national severity and no PiN per severity phase. Incomplete sector coverage is never turned into phase 1: the sectors in scope (default all eight main sectors) that have no phase are missing, and if they could change the result the unit has NO preliminary severity (status incomplete_coverage, with lower and upper bounds); a severity of 0 means not-applicable unless zero_severity_as='missing'. Several flag thresholds are readings of the manual that are not verified against OCHA's worksheet formulas: they are settings, echoed in the result, to be confirmed by the analysis team. Reads the same files as import_jiaf_inputs; give previous_file_path for flag 6. Optionally writes jf_pre_pin, jf_pre_sev, jf_npinfl, jf_nsevfl to an admin layer (needs confirmation) and a per-unit CSV.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes | The sector-input file (OCHA worksheet, HXL table or sector template), as for import_jiaf_inputs. |
| `input_format` | string | no | 'auto' (default), 'ocha_worksheet', 'hxl' or 'sector_template'. |
| `sheet_name` | string | no |  |
| `previous_file_path` | string | no | Optional previous-year file of the same kind, for flag 6. |
| `previous_sheet_name` | string | no |  |
| `rules_profile` | string | no | 'ocha_worksheet_2026' (default: the flag formulas read from OCHA's official Worksheet 3A/3B) or 'manual_reading' (this tool's older interpretation of the manual, for comparison only). |
| `sectors_sev_5` | integer | no | Worksheet profile: severity flag 1 fires at this many sectors in phase 5 (and flag 4 uses it too). Default: the workbook's Thresholds cell, else 2. |
| `sectors_sev_4` | integer | no | Worksheet profile: the header-text reading of severity flag 4 (reported only, not used by the formula). Default 5. |
| `sectors_in_scope` | array[string] | no | Main sectors the HCT activated. Default: all eight. A sector in scope with no value is MISSING, never phase 1. |
| `zero_severity_as` | string | no | 'not_applicable' (default) or 'missing': what a severity of 0 means. |
| `f1_min_sectors` | integer | no | Flag 1 fires at this many sectors that are missing or zero. Worksheet profile: the workbook's zero_pin_thresh, else 2 (manual_reading: 1). |
| `f1_count_missing` | boolean | no | manual_reading profile only. Flag 1 counts sectors with NO PiN. Default true. |
| `f1_count_zero` | boolean | no | manual_reading profile only. Flag 1 counts sectors with an explicit PiN of 0. Default true. Missing and zero are different facts. |
| `f2_pct` | number | no | Flag 2 threshold as a fraction (0.30 = 30%). Default: the workbook's perc_1st_2nd, else 0.30. |
| `f3_pct` | number | no | Flag 3 threshold as a fraction. Default: the workbook's perc_1st_3rd, else 0.50. |
| `f4_subpopulation_sectors` | array[string] | no | Sectors that count a sub-population. Worksheet profile: the workbook's own list, else the template's (education). manual_reading: flag 4 is evaluated only if given. |
| `f5_share` | number | no | Flag 5 threshold as a share of population (fires at >=). Default: the workbook's flag_pin_perc, else 0.90. |
| `f6_pct` | number | no | Flag 6 threshold on the (rounded to 0.1) change from last year, up or down, as a fraction. Default: the workbook's flag_pin_historical, else 1.0. |
| `f6_min_previous_pin` | number | no | manual_reading profile only. Flag 6 is only evaluated when last year's PiN is at least this. Default 1000. |
| `s4_sector_count` | integer | no | manual_reading profile only. Severity flag 4 fires when MORE THAN this many sectors are in phase 4 (and the preliminary phase is 4). Default 4. |
| `export_csv_path` | string | no | Optional new .csv file for the per-unit table (refuses to overwrite). |
| `layer_name` | string | no |  |
| `layer_key_field` | string | no | Admin 2 P-code field on that layer. |
| `write_fields` | boolean | no | With layer_name: write jf_pre_pin, jf_pre_sev, jf_npinfl, jf_nsevfl. Needs confirmation. |

## jiaf_inputs

### `get_jiaf_setup`

Read the JIAF 2 analysis set-up and sector alignment records stored in the project by record_jiaf_setup (support for the JIAF 2 process; not endorsed by OCHA or the IASC).

_No parameters._

### `import_jiaf_inputs`

Read and validate the sector inputs for a JIAF 2 analysis (support for the JIAF 2 process; not the JIAF method, not endorsed by OCHA or the IASC, no joint PiN or severity is computed here). Reads an .xlsx/.csv of one of three kinds: the OCHA Workspace 3A/3B worksheet ('WS - 3.1 Overall PiN' + 'WS - 3.2 Intersectoral Severity'), an HXL-tagged published table (#adm2 +code, #inneed +wsh, #severity +shl ...), or the manual's per-sector template (give `sector` and `template_kind`). Reports units, sectors found, per-sector totals, and every problem: severity must be a phase 1-5 (0 is reported as not-applicable, never turned into a phase), PiN must be a non-negative number, duplicates and missing values are listed and never filled. Stored columns (Preliminary/Final PiN, Final Severity) are returned only as stored and are NOT trusted. Optionally joins to an admin layer by P-code and, after confirmation, writes the values as new numeric fields (jp_<sector> for PiN, js_<sector> for severity). Never invent a threshold or fill a missing value.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes | Absolute path to the .xlsx or .csv file. |
| `input_format` | string | no | 'auto' (default), 'ocha_worksheet', 'hxl' or 'sector_template'. |
| `sheet_name` | string | no | Sheet to read for 'hxl' or 'sector_template' (default: the first). |
| `sector` | string | no | For 'sector_template': the sector the file belongs to (cccm, education, nutrition, food_security, health, protection, shelter, wash, child_protection, gbv, mine_action, hlp). |
| `template_kind` | string | no | For 'sector_template': 'pin' or 'severity'. |
| `layer_name` | string | no | Optional admin polygon layer to join to. |
| `layer_key_field` | string | no | Field on that layer holding the Admin 2 P-code. |
| `write_fields` | boolean | no | With layer_name: write jp_<sector> (PiN) and js_<sector> (severity) fields. Needs confirmation. |

### `record_jiaf_setup`

Record the JIAF 2 analysis set-up in the project (support for the JIAF 2 process; not endorsed by OCHA or the IASC): country, planning cycle, unit of analysis (e.g. admin 2), the manual edition followed (e.g. 'July 2024'), areas and population groups in scope, whether the Humanitarian Country Team endorsed the scope, and optionally each sector's alignment self-assessment (manual Workspaces 2A/2B): whether its PiN is aligned with the joint-overall-PiN guidance, whether its severity scale is aligned or adapted, with an explanation whenever it is not aligned or is adapted, and the indicators and thresholds it used. Replaces any earlier record. Stored in the QGIS project; nothing is computed or decided.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `country` | string | yes |  |
| `planning_cycle` | string | yes | e.g. 'HPC 2026'. |
| `unit_of_analysis` | string | yes | e.g. 'admin 2' or 'admin 2 x population group'. |
| `manual_edition` | string | yes | The JIAF 2 Technical Manual edition followed, e.g. 'July 2024'. |
| `areas_in_scope` | string | no |  |
| `population_groups` | string | no |  |
| `scope_note` | string | no |  |
| `hct_endorsed_scope` | boolean | no | Whether the HCT endorsed the scope; omit if unknown. |
| `sector_alignment` | array[object] | no |  |

## jiaf_patterns

### `compute_jiaf_patterns`

Produce the JIAF 2 intersectoral pattern outputs of Workspace 3C (support for the JIAF 2 process; not the JIAF method, not endorsed by OCHA or the IASC): where the PiN is concentrated, which units have many sectors with more than 40% of the population in need, which sectors drive the PiN, the change against last year, units in severity phases 4-5 and with five or more sectors in phase 4-5, sector severity distributions, units with both high PiN and high severity, and the sector pairs whose PiN correlates above 0.7. These are lists and counts for the analysts' discussion, not conclusions. Thresholds are country-level settings (the manual's defaults where it gives one; the others are the module's and are echoed). Uses the recorded group decisions where they exist and the preliminary severity otherwise (reported). No national severity; not for ranking crises. Optionally writes jf_nsec40 and jf_nsev45 (counts per unit, for mapping) to an admin layer after confirmation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes |  |
| `input_format` | string | no |  |
| `sheet_name` | string | no |  |
| `previous_file_path` | string | no |  |
| `previous_sheet_name` | string | no |  |
| `sectors_in_scope` | array[string] | no | Main sectors the HCT activated. Default: all eight. |
| `zero_severity_as` | string | no | 'not_applicable' (default) or 'missing'. |
| `sector_population_share` | number | no | Share of a unit's population that makes a sector's PiN 'large'. Manual: 0.40. |
| `many_sectors_with_large_pin` | integer | no |  |
| `top_units` | integer | no |  |
| `high_pin_share` | number | no |  |
| `severe_phases` | array[integer] | no | Default [4, 5]. |
| `many_severe_sectors` | integer | no | Manual: 5. |
| `top_sectors` | integer | no | Manual: 3. |
| `correlation_threshold` | number | no | Manual: 0.7. |
| `group_shares` | object | no | Optional population shares per group, e.g. {'girls': 0.25}, for the extrapolated estimates. |
| `layer_name` | string | no |  |
| `layer_key_field` | string | no |  |
| `write_fields` | boolean | no | With layer_name: write jf_nsec40 and jf_nsev45. Needs confirmation. |

## jiaf_review

### `finalize_jiaf_results`

Apply the recorded JIAF 2 group decisions to the preliminary figures and report the FINAL results (support for the JIAF 2 process; NOT the JIAF method, not endorsed by OCHA or the IASC; never call the result JIAF-compliant or official). A unit with no flag keeps the preliminary figures; a flagged unit uses its recorded decision; a flagged unit with no decision is PENDING: its Final PiN is shown at the highest sectoral PiN as a provisional figure (counted and totalled separately) and its final severity is left empty. The Final PiN total is the sum over units; there is no national severity and no PiN per severity phase. bulk_accepted_flags (e.g. [1]) closes units whose only fired PiN flags are those; this is an analysis-team decision and REQUIRES bulk_rationale (why) and ideally bulk_decided_by, which are recorded in the result and against every unit closed. The flag conditions are unverified interpretations of the manual (see validation_blockers in the result): the number of pending units depends on them. Reads the same files and uses the same flag settings as compute_jiaf_preliminary. Optionally writes jf_fin_pin, jf_fin_sev, jf_pin_rk to an admin layer (needs confirmation) and a per-unit CSV with the Evidence & Comments (never overwrites).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes |  |
| `input_format` | string | no |  |
| `sheet_name` | string | no |  |
| `previous_file_path` | string | no |  |
| `previous_sheet_name` | string | no |  |
| `bulk_accepted_flags` | array[integer] | no | PiN flag numbers the team agreed to close in bulk, e.g. [1]. Needs bulk_rationale. |
| `bulk_rationale` | string | no | Why the team closed these flags in bulk (required with bulk_accepted_flags). |
| `bulk_decided_by` | string | no | Who decided, e.g. 'JIAF analysis group, 12 Oct'. |
| `rules_profile` | string | no | 'ocha_worksheet_2026' (default) or 'manual_reading' (older interpretation, comparison only). |
| `sectors_sev_5` | integer | no |  |
| `sectors_sev_4` | integer | no |  |
| `f1_min_sectors` | integer | no |  |
| `f1_count_missing` | boolean | no |  |
| `f1_count_zero` | boolean | no |  |
| `sectors_in_scope` | array[string] | no | Main sectors the HCT activated. Default: all eight; a sector with no value is missing, never phase 1. |
| `zero_severity_as` | string | no | 'not_applicable' (default) or 'missing'. |
| `f2_pct` | number | no |  |
| `f3_pct` | number | no |  |
| `f4_subpopulation_sectors` | array[string] | no |  |
| `f5_share` | number | no |  |
| `f6_pct` | number | no |  |
| `f6_min_previous_pin` | number | no |  |
| `s4_sector_count` | integer | no |  |
| `export_csv_path` | string | no | Optional new .csv file (refuses to overwrite). |
| `layer_name` | string | no |  |
| `layer_key_field` | string | no |  |
| `write_fields` | boolean | no | With layer_name: write jf_fin_pin, jf_fin_sev, jf_pin_rk. Needs confirmation. |

### `get_jiaf_decisions`

Read the JIAF 2 group decisions stored in the project by record_jiaf_decisions (support for the JIAF 2 process; not endorsed by OCHA or the IASC).

_No parameters._

### `record_jiaf_decisions`

Record the multi-partner group's JIAF 2 decisions for flagged units (support for the JIAF 2 process; not endorsed by OCHA or the IASC; this tool decides nothing, it only records what the group decided). pin_decisions: for a flagged unit, which main sector's PiN is used as the Final PiN (the manual offers the highest or second highest; any main sector is accepted and the rank of the chosen one is reported) with the rationale (required). severity_decisions: the agreed intersectoral severity phase 1-5 for a flagged unit with the evidence basis (outcome_indicators, proxy_indicators, expert_judgement or sector_overlap_accepted) and the evidence (required). Stored in the QGIS project, merged with earlier records unless replace=true. Never invent a decision; ask the team.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pin_decisions` | array[object] | no |  |
| `severity_decisions` | array[object] | no |  |
| `replace` | boolean | no | Replace all stored decisions instead of merging. |

## layout_chart_profile_tools

### `add_layout_chart`

Add a chart to a print layout: chart_type 'bar', 'line' or 'pie' of layer_name, with x_field (the categories) and y_field (the values), both plain field names. Position and size in millimetres. A chart item draws the layer's own features, so it follows the layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `layer_name` | string | yes |  |
| `chart_type` | string | no |  |
| `x_field` | string | yes |  |
| `y_field` | string | yes |  |
| `x_mm` | number | no |  |
| `y_mm` | number | no |  |
| `width_mm` | number | no |  |
| `height_mm` | number | no |  |
| `item_id` | string | no |  |

### `add_layout_elevation_profile`

Add an elevation profile to a print layout along a straight line from (start_x, start_y) to (end_x, end_y) in the project CRS. layer_names are the layers to profile; each needs elevation turned on first (set_layer_elevation). Give either start/end coordinates or along_layer, the name of a LINE layer (a road, a river): the profile then runs from the first to the last vertex of its selected feature, or its first feature. Position and size in millimetres.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `layer_names` | array[string] | yes |  |
| `start_x` | number | no |  |
| `start_y` | number | no |  |
| `end_x` | number | no |  |
| `end_y` | number | no |  |
| `x_mm` | number | no |  |
| `y_mm` | number | no |  |
| `width_mm` | number | no |  |
| `height_mm` | number | no |  |
| `item_id` | string | no |  |
| `along_layer` | string | no |  |

## layout_extra_tools

### `add_overview_map`

Show where one layout map is looking on another map (a locator or overview inset): overview_map_id is the map that draws the frame (the small inset), extent_map_id is the map whose extent the frame shows (default MAP_MAIN). To create the inset too, give inset_box {x_mm, y_mm, width_mm, height_mm}; it is zoomed out around the main map. color and width_mm style the frame.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `overview_map_id` | string | no |  |
| `extent_map_id` | string | no |  |
| `color` | string | no |  |
| `width_mm` | number | no |  |
| `inset_box` | object | no |  |

### `set_layout_atlas`

Turn a print layout into an atlas: one page per feature of coverage_layer. page_name_field names each page, sort_field orders them, filter_expression keeps only some features (a QGIS expression), hide_coverage hides the coverage layer outside the current feature, margin_percent pads the map around each feature, scaling is auto, fixed or predefined, map_item_id is the map that follows the atlas (default MAP_MAIN). disable=true switches the atlas off. Export it with export_layout_atlas.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `coverage_layer` | string | no |  |
| `page_name_field` | string | no |  |
| `sort_field` | string | no |  |
| `filter_expression` | string | no |  |
| `hide_coverage` | boolean | no |  |
| `margin_percent` | number | no |  |
| `scaling` | string | no |  |
| `map_item_id` | string | no |  |
| `disable` | boolean | no |  |

### `set_layout_guides_grid`

Set a print layout's alignment aids: guides (a list of {orientation: horizontal|vertical, position_mm}; replaces the guides on the first page), clear_guides=true to remove them, grid_mm for the snapping grid spacing, snap_to_grid and snap_to_guides to switch snapping on or off. These affect how items snap when edited; they do not print.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `guides` | array[object] | no |  |
| `clear_guides` | boolean | no |  |
| `grid_mm` | number | no |  |
| `snap_to_grid` | boolean | no |  |
| `snap_to_guides` | boolean | no |  |

## layout_item_tools

### `add_layout_item`

Add one item to a print layout that already exists (see list_layouts): a text label, a picture from a local image file (png, jpg, svg), a shape (rectangle, ellipse, triangle), an arrow, or an attribute table of a vector layer. Position and size are in millimetres from the page's top-left corner (an A4 landscape page is 297 x 210). An arrow is given by its start and end points instead of a box. Give the item an item_id to find it again; list_layout_items shows what is there. HTML frames and pictures from a web address are refused on purpose.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `kind` | string | yes | label, picture, shape, arrow or table |
| `item_id` | string | no | Letters, digits, space, - and _ (max 64). Generated if omitted. |
| `x_mm` | number | no |  |
| `y_mm` | number | no |  |
| `width_mm` | number | no |  |
| `height_mm` | number | no |  |
| `text` | string | no |  |
| `font_size` | number | no |  |
| `font_color` | string | no |  |
| `picture_path` | string | no |  |
| `shape` | string | no |  |
| `fill_color` | string | no |  |
| `outline_color` | string | no |  |
| `outline_width_mm` | number | no |  |
| `from_x_mm` | number | no |  |
| `from_y_mm` | number | no |  |
| `to_x_mm` | number | no |  |
| `to_y_mm` | number | no |  |
| `layer_name` | string | no | For a table: the vector layer. |
| `fields` | array[string] | no | For a table: the columns to show. |
| `max_rows` | integer | no | For a table: rows to show (default 10, at most 200). |

### `edit_layout_item`

Change or remove one item of a print layout by its id (list_layout_items shows the ids): move it (x_mm, y_mm), resize it (width_mm, height_mm), rotate it (rotation in degrees), switch its frame on or off (frame), or remove it (remove=true). Give only what should change.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `item_id` | string | yes |  |
| `x_mm` | number | no |  |
| `y_mm` | number | no |  |
| `width_mm` | number | no |  |
| `height_mm` | number | no |  |
| `rotation` | number | no |  |
| `frame` | boolean | no |  |
| `remove` | boolean | no |  |

### `export_layout`

Export an existing print layout to a file: .pdf, .png, .jpg, .tif (image) or .svg (vector). dpi applies to PDF and images (default 150). Replacing an existing file needs confirmation. create_print_layout can export while it builds; this exports a layout that already exists. The result lists any RESTRICTED or SENSITIVE layer the map draws and any missing title, legend, scale bar or north arrow in export_warnings: tell the user. A map that draws a RESTRICTED or SENSITIVE layer waits for the user's confirmation before it is written. purpose='publication' is for a file that will be shared outside the team: it is refused while the layout lacks a mandatory element or draws a protected layer, unless the user gives a reason (ask them; pass it as override_reason) and confirms.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `output_path` | string | yes |  |
| `dpi` | integer | no |  |
| `preset` | string | no | export purpose instead of a dpi number: 'draft' (96), 'web' (150) or 'print' (300). An explicit dpi wins. |
| `output_format` | string | no | only when output_path is a FOLDER: pdf (default), png, jpg, tif or svg; the file is then named <layout>_<date>.<format> |
| `world_file` | boolean | no | image exports: also write a world file (.pgw, .jgw, .tfw) so GIS software can place the picture |
| `geopdf` | boolean | no | pdf exports: write a georeferenced PDF (needs the GDAL PDF driver) |
| `purpose` | string | no | 'publication' only when the user says the file will be shared outside the team; omit for drafts |
| `override_reason` | string | no | with purpose='publication': the USER's stated reason for exporting despite problems. Never invent one; ask. |

### `load_layout_template`

Create a new print layout from a template file (.qpt) made by save_layout_template or QGIS. The new layout gets new_layout_name, which must not be taken. A template that contains an HTML frame is refused (it would run web content).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `template_path` | string | yes |  |
| `new_layout_name` | string | yes |  |

### `save_layout_template`

Save a print layout as a reusable template file (.qpt) that load_layout_template can turn into a new layout later, in this or another project. Replacing an existing file needs confirmation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `output_path` | string | yes | Ends in .qpt |

### `set_layout_map`

Set what a print layout's map shows: the scale (scale = the denominator, 250000 for 1:250,000), the extent (extent_layer = zoom to a layer, or bbox = [min_lon, min_lat, max_lon, max_lat] in degrees), the rotation in degrees, lock_layers=true to freeze the layers the map shows now so later changes in the project do not alter the layout, or map_theme to follow a saved map theme. Works on MAP_MAIN unless map_item_id names another map. If both an extent and a scale are given, the extent is set first and the scale applied around its centre.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `map_item_id` | string | no |  |
| `scale` | number | no |  |
| `rotation` | number | no |  |
| `extent_layer` | string | no |  |
| `bbox` | array[number] | no |  |
| `lock_layers` | boolean | no |  |
| `map_theme` | string | no |  |

### `set_layout_page`

Change a print layout's page: size (A0 to A5, Letter, Legal, Tabloid), orientation (landscape or portrait) and the number of pages (1 to 20; new pages copy the size). Items already on the page keep their positions: move them with edit_layout_item if the new size needs it.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layout_name` | string | yes |  |
| `size` | string | no |  |
| `orientation` | string | no |  |
| `pages` | integer | no |  |

## map_view_tools

### `assign_layer_crs`

Tell QGIS what CRS a layer's coordinates are ALREADY in ('Assign projection'). This does NOT move or reproject the data: choosing the wrong CRS places the layer in the wrong location. Use only when the layer's CRS is missing or known to be wrong. A preview is shown for confirmation first.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `crs` | string | yes |  |

### `create_bookmark`

Save a spatial bookmark in the project: of a layer's extent (layer_name), of an explicit extent [xmin, ymin, xmax, ymax] in crs, or of the current map view when neither is given.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes |  |
| `layer_name` | string | no |  |
| `extent` | array[number] | no |  |
| `crs` | string | no |  |

### `create_layer_group`

Create a layer group in the layer tree (optionally inside another group) and optionally move layers into it.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `group_name` | string | yes |  |
| `layer_names` | array[string] | no |  |
| `parent_group` | string | no |  |

### `go_to_bookmark`

Zoom the map to a saved spatial bookmark by name.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes |  |

### `list_bookmarks`

List the spatial bookmarks saved in the project. Read-only.

_No parameters._

### `measure_distance`

Measure on the ellipsoid along a path of points [[x, y], ...] given in crs (default EPSG:4326): total length in metres and kilometres, and for exactly two points the bearing in degrees. With close_polygon=true the points are a polygon and its area in square metres and hectares is returned too.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `points` | array[array] | yes |  |
| `crs` | string | no |  |
| `close_polygon` | boolean | no |  |

### `move_layers_to_group`

Move existing layers into an existing layer group.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `group_name` | string | yes |  |
| `layer_names` | array[string] | yes |  |

### `set_group_options`

Show or hide a whole layer group, collapse or expand it, and/or make its layers mutually exclusive (only one visible at a time).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `group_name` | string | yes |  |
| `visible` | boolean | no |  |
| `expanded` | boolean | no |  |
| `mutually_exclusive` | boolean | no |  |

### `set_map_view`

Move the map canvas: set the scale (denominator, e.g. 25000 for 1:25 000), zoom to an extent [xmin, ymin, xmax, ymax] in crs (default EPSG:4326), centre on a point [x, y] in crs, and/or rotate the map in degrees. Several can be combined.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `scale` | string | no |  |
| `extent` | array[number] | no |  |
| `center` | array[number] | no |  |
| `crs` | string | no |  |
| `rotation` | number | no |  |

### `set_project_crs`

Set the project (map) CRS, for example EPSG:3857. Layers are reprojected on the fly for display; no layer data is changed.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `crs` | string | yes |  |

### `set_project_properties`

Set the project title and/or project variables (a {name: value} object usable as @name in expressions).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `title` | string | no |  |
| `variables` | object | no |  |

## mcda_tools

### `calculate_mcda_ranking`

Rank areas (or any features) on several weighted criteria and test how much the ranking depends on the weights. For each criterion give the field, a weight and which end gets priority: direction 'higher' (a high value means higher priority, e.g. people in need) or 'lower' (a low value means higher priority, e.g. water coverage). Values are min-max scaled to 0-1, scores are the weighted sum, ranks are 1 = top priority. It then re-ranks many times with the weights randomly perturbed (default +/-20%) and returns each unit's best and worst rank and, with top_k, the share of trials it stayed in the top k -- so say which priorities are robust and which only come from the chosen weights. Units missing any criterion are excluded and listed, never imputed. The weights are the user's judgement: ask for them rather than inventing them, and report them with the ranking. Optionally writes score and rank to the layer (needs confirmation). The sensitivity check covers the weights only, not data errors or the choice of criteria.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Vector layer with the units to rank (e.g. admin polygons). |
| `criteria` | array[object] | yes | At least two criteria. |
| `unit_name_field` | string | no | Optional field used to label units in the results. |
| `top_k` | integer | no | Report, per unit, the share of weight-perturbation trials in which it stays in the top k. |
| `perturbation` | number | no | Relative weight change tested, 0 to 0.9. Default 0.2 (+/-20%). |
| `trials` | integer | no | Number of perturbation trials, default 500, maximum 5000. |
| `seed` | integer | no | Random seed for the perturbation. Omit for a generated one (returned). |
| `output_prefix` | string | no | Optional: write <prefix>_score, <prefix>_rank, <prefix>_rank_min, <prefix>_rank_max to the layer. |

## new_layer_tools

### `add_3d_tiles_layer`

Add a 3D Tiles tileset (a tileset.json, local or https) as a tiled scene layer. Only https URLs are accepted.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `source` | string | yes |  |
| `layer_name` | string | no |  |

### `add_point_cloud_layer`

Add a point cloud (.las, .laz, .copc.laz, or an EPT dataset's ept.json) from a local file as a layer. Read-only: the file is not changed.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes |  |
| `layer_name` | string | no |  |

### `add_vector_tile_layer`

Add a vector tile layer: an https XYZ service URL containing {z}/{x}/{y}, or a local .mbtiles / .vtpk file. Only https URLs are accepted.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `source` | string | yes |  |
| `layer_name` | string | no |  |
| `min_zoom` | integer | no |  |
| `max_zoom` | integer | no |  |

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

### `find_processing_algorithm`

Search the approved QGIS Processing algorithms by a few words (for example 'densify', 'polygons to lines', 'smooth') and get each match's id, name and exact parameter names with types and defaults, ready for run_allowlisted_processing_algorithm. Read-only. With algorithm_id set, returns just that algorithm's parameters.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | no |  |
| `algorithm_id` | string | no |  |
| `family` | string | no | Browse one family instead of searching: geometry, table, analysis, expression, raster, mixed, grass or mesh. Lists id, name and what each is for. |

### `run_allowlisted_processing_algorithm`

Runs one QGIS Processing algorithm from a fixed, pre-approved list -- prefer this over execute_pyqgis_script when the task is achievable via a single Processing algorithm that isn't already covered by a dedicated tool. It calls only the named, pre-approved algorithm with the given parameters and never accepts a FORMULA or EXTRA (raw backend arguments) parameter; algorithms that evaluate free-form expressions as code (such as the GDAL raster calculator) are not on the list. Only algorithms already used elsewhere in this codebase are allowed -- an unlisted algorithm id is rejected outright, not run. Output is always kept in-memory as a new project layer (auto-named), never written to a file path -- use a dedicated export tool (export_layer, export_to_csv) afterward if a file is actually needed. Don't specify the output (destination) parameters yourself -- they are set automatically and any value you give is ignored. An unknown parameter name is rejected before the algorithm runs, with the list of valid names; an algorithm with several outputs returns each as its own layer (additional_outputs); native:selectbylocation changes the selection of the existing layer instead of creating one. Any string parameter value matching a currently-loaded layer's name is automatically resolved to that layer; every other value is passed through as-is.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `alg_id` | string | yes | Processing algorithm id, e.g. 'native:buffer'. Must be an approved id; call find_processing_algorithm to search the approved list by words and see each algorithm's exact parameter names. |
| `params` | object | yes | Flat dict of algorithm parameters, e.g. {"INPUT": "my_layer", "DISTANCE": 500}. String values matching a loaded layer's name are resolved to that layer automatically. |
| `new_layer_name` | string | no | Name to give the algorithm's output layer once added to the project. Defaults to '<alg_id>_output' if omitted -- and an omitted name is treated as a signal that this output is an internal/scratch step (e.g. a reprojection before a buffer), so it's added to the project hidden (unchecked in the layer tree) rather than cluttering the visible map. Give this an explicit name whenever the output IS the deliverable you want the user to see. |

## project_ops_tools

### `add_text_annotation`

Put a text note on the map at x, y (in crs, default EPSG:4326). It is kept in the project's annotation layer.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `text` | string | yes |  |
| `x` | number | yes |  |
| `y` | number | yes |  |
| `crs` | string | no |  |

### `create_relation`

Create a 1-N relation between two layers: parent_layer.parent_field is referenced by child_layer.child_field (for example districts.pcode and schools.district_pcode). The relation is stored in the project.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes |  |
| `parent_layer` | string | yes |  |
| `parent_field` | string | yes |  |
| `child_layer` | string | yes |  |
| `child_field` | string | yes |  |

### `get_layer_metadata`

Read a layer's metadata: title, abstract, licenses, rights, keywords and contacts.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |

### `list_relations`

List the project's relations between layers.

_No parameters._

### `remove_annotations`

Remove all text annotations from the map. Destructive: a preview with the count is shown first.

_No parameters._

### `rename_layer_group`

Rename a layer group in the layer tree.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `group_name` | string | yes |  |
| `new_name` | string | yes |  |

### `set_layer_metadata`

Set a layer's metadata: title, abstract, license, rights, keywords (a list of words) and one contact (name, organization, email). Fields you leave out are kept. The metadata is stored in the project (save the project to keep it).

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `title` | string | no |  |
| `abstract` | string | no |  |
| `license` | string | no |  |
| `rights` | string | no |  |
| `keywords` | array[string] | no |  |
| `contact_name` | string | no |  |
| `contact_organization` | string | no |  |
| `contact_email` | string | no |  |

### `set_layer_temporal`

Make a vector layer time-aware: give the date or date-time field (start_field) and optionally an end_field for features that last a period. Set clear=true to switch it off. The fields must be of date or date-time type.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `start_field` | string | no |  |
| `end_field` | string | no |  |
| `clear` | boolean | no |  |

### `set_project_time_range`

Set the project's temporal range (the period the temporal controller covers). start and end are dates such as 2026-03-01 or 2026-03-01T12:00:00.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `start` | string | yes |  |
| `end` | string | yes |  |

### `set_snapping_options`

Set the project's snapping: enabled, snap_type (vertex, segment, vertex and segment, centroid, middle of segment, line endpoint, area), tolerance, units (pixels or project units), mode (all layers, active layer, advanced) and topological editing. Options you leave out are kept.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `enabled` | boolean | no |  |
| `snap_type` | string | no |  |
| `tolerance` | number | no |  |
| `units` | string | no |  |
| `mode` | string | no |  |
| `topological_editing` | boolean | no |  |

### `zoom_history`

Zoom the map canvas to the previous or the next extent in its history (like the Zoom Last / Zoom Next buttons). direction: previous or next.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `direction` | string | yes | previous or next |

## project_tidy_tools

### `tidy_project_layers`

Find and repair clutter left in a project by older Cartogen AI builds: (1) the same layer loaded more than once (identical name and data) -- the extra copies are HIDDEN, never deleted; (2) a WorldPop population raster drawn opaque black instead of with the population colour ramp -- restyled; (3) temporary scratch layers (such as origin points) that are lost when the project is closed -- saved into the project's results GeoPackage (the project must already be saved). Call with apply=false (default) to only list what it found, then apply=true to repair. It does not delete layers; use remove_layer, which asks for confirmation, to delete a hidden duplicate.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `apply` | boolean | no | false (default): report only. true: ask the user to confirm, then hide duplicate copies, restyle population rasters and save scratch layers. |

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

## raster_calculator_tool

### `raster_calculator`

Raster calculator (map algebra): computes a new raster from one or more raster layers in the project with an expression, using QGIS's own raster calculator. Write each layer as "layer name@band" in double quotes (band numbers start at 1), for example "dem@1" > 100 (a 0/1 mask of cells above 100), ("nir@1" - "red@1") / ("nir@1" + "red@1"), or "slope@1" < 15 AND "landcover@1" = 2. Allowed: numbers, + - * / ^, comparisons (< > = != <= >=), AND, OR, brackets and the functions sqrt sin cos tan asin acos atan ln log10 abs min max. Anything else is refused before QGIS runs. The first layer named sets the output extent and cell size by default. Adds a NEW raster layer (default name 'raster_calc'); no input layer is changed. Cells where any input is NoData stay NoData.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `expression` | string | yes | Raster expression, layers written as "layer name@band". |
| `new_layer_name` | string | no | Name for the result layer (default 'raster_calc'). |

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

## sampling_tools

### `design_sampling_frame`

Design a household/community survey sample (e.g. for a multi-sector needs assessment): works out how many units to survey in each stratum (admin unit, camp, host community...) for a chosen confidence level and margin of error, and draws the sample as a point layer with a recorded random seed. Draws from a layer of candidate units (households, buildings, settlements) when units_layer is given, otherwise as random points inside each stratum polygon (area-based, ignores where people live). The statistical assumptions are arguments and are echoed back: expected_proportion defaults to 0.5 (most conservative) and design_effect to 1.0, which is correct ONLY for simple random sampling -- for a cluster design the survey designer must supply the design effect, so ask rather than guess. It does not choose the survey design, and the result is only as good as the frame it is drawn from.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `strata_layer` | string | yes | Polygon layer of strata (admin units, camp / host-community areas). |
| `stratum_field` | string | no | Field naming each stratum. Omit to treat each polygon as its own stratum, named by feature id. |
| `units_layer` | string | no | Optional layer of candidate units to sample from (points, or polygons such as buildings -- their centroids are used). |
| `population_attribute` | string | no | Optional numeric field on the strata layer with the number of units (e.g. households) in the stratum. If omitted and units_layer is given, the stratum size is the number of candidate units inside it; otherwise no finite-population correction is applied. |
| `confidence` | number | no | Confidence level, e.g. 0.95 (default). |
| `margin_of_error` | number | no | Margin of error as a proportion, e.g. 0.05 (default) = +/-5 percentage points. |
| `expected_proportion` | number | no | Expected proportion of the indicator, default 0.5 (most conservative). |
| `design_effect` | number | no | Design effect, default 1.0 (simple random sampling only). Must be supplied by the survey designer for cluster designs. |
| `nonresponse_rate` | number | no | Expected non-response as a proportion, default 0. |
| `seed` | integer | no | Random seed. Omit to generate one; it is returned either way so the draw can be repeated. |
| `output_layer_name` | string | no | Name of the sample point layer. Default 'survey_sample'. |
| `plan_only` | boolean | no | true: only compute sample sizes per stratum, do not draw or create a layer. |

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

## survey_tools

### `aggregate_survey_indicator`

Summarise survey records into one figure per area (admin unit, camp, ...): the weighted share of respondents answering yes (kind='proportion') or the weighted mean of a numeric answer (kind='mean'), each with a confidence interval. Groups with fewer than min_n respondents (default 30) are SUPPRESSED -- no estimate is returned -- because a figure from a handful of households is unreliable and can identify people in a small community; the real threshold is the organisation's data-protection policy, so ask for it if it matters. Uses the survey's own weights as given (weight_field); intervals use Kish's effective sample size and IGNORE clustering and stratification, so for a cluster survey supply design_effect or treat the intervals as too narrow. Records with a missing answer or an invalid weight are excluded and counted, never imputed. Optionally creates a table layer of the results that can be joined to admin polygons.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Layer or table of survey records (one row per respondent/household). |
| `group_field` | string | yes | Field naming the area/stratum each record belongs to. |
| `indicator_field` | string | yes | Field with the answer: yes/no-style for a proportion, numeric for a mean. |
| `kind` | string | no | 'proportion' (default) or 'mean'. |
| `positive_values` | array[string] | no | For a proportion: the answers that count as 'yes' (e.g. ['No access'] to measure lack of access). Default: the usual 1/yes/true spellings. |
| `weight_field` | string | no | Optional numeric survey-weight field; omit for unweighted. |
| `min_n` | integer | no | Minimum respondents per group, default 30. Smaller groups are suppressed. |
| `confidence` | number | no | Confidence level of the intervals, default 0.95. |
| `design_effect` | number | no | Design effect from the survey design (>= 1); divides the effective sample size. Default 1 (no clustering adjustment). |
| `output_table_name` | string | no | Optional name for a results table layer. |

## symbology_extra_tools

### `apply_saved_symbol`

Give a vector layer a symbol from your personal symbol library by name. The symbol kind must fit the layer (marker for points, line for lines, fill for polygons). A layer that uses categories or graduated colours is only switched to the single symbol after confirmation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `name` | string | yes |  |

### `list_saved_symbols`

List the symbols in your personal QGIS symbol library (name and kind: marker, line or fill).

_No parameters._

### `save_symbol_to_library`

Save a vector layer's (single) symbol into your personal QGIS symbol library under a name, optionally with tags, so it can be reused on other layers and in other projects. An existing symbol with the same name is only replaced after confirmation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `name` | string | yes |  |
| `tags` | array[string] | no |  |

### `set_label_callout`

Add or change callouts (lines from a label to its feature) and a text mask (a clear halo that hides what is behind the text) on a layer that already has simple labels (apply_labels). enabled switches callouts on or off; style is simple or manhattan; color and width_mm style the line; mask and mask_size_mm control the mask.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `enabled` | boolean | no |  |
| `style` | string | no | simple or manhattan |
| `color` | string | no |  |
| `width_mm` | number | no |  |
| `mask` | boolean | no |  |
| `mask_size_mm` | number | no |  |

### `set_layer_diagram`

Draw a pie or bar diagram on every feature of a vector layer from numeric fields (kind: pie, bar or histogram; fields: 1 to 8 numeric field names; size_mm; optional colors, one per field). clear=true removes the diagrams.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `kind` | string | no |  |
| `fields` | array[string] | no |  |
| `size_mm` | number | no |  |
| `colors` | array[string] | no |  |
| `clear` | boolean | no |  |

### `set_point_marker`

Use an SVG picture or a single font character as the marker of a POINT layer. kind=svg needs svg_path (a local .svg file, or a name from QGIS's own SVG library such as arrows/Arrow_01.svg; URLs are refused); kind=font needs font_family and character. size_mm and color are optional. The layer must use a single symbol.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `kind` | string | yes | svg or font |
| `svg_path` | string | no |  |
| `font_family` | string | no |  |
| `character` | string | no |  |
| `size_mm` | number | no |  |
| `color` | string | no |  |

### `set_raster_relief`

Draw a raster (for example a DEM) as a hillshade (style=hillshade; azimuth 0-360, altitude 0-90, z_factor) or as contour lines (style=contour; interval and optional index_interval, in the raster's units). band defaults to 1. This changes how the raster is DISPLAYED, not its data: it creates no layer and no file, so these contour lines cannot be selected, measured, labelled or exported. When the user wants contour lines as data ('draw / make / create contour lines of the DEM, every 100 m') use generate_contours; use this tool for 'render / style / show the DEM as contours or hillshade'. For a hillshade FILE use the hillshade analysis tool.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `style` | string | yes | hillshade or contour |
| `azimuth` | number | no |  |
| `altitude` | number | no |  |
| `z_factor` | number | no |  |
| `interval` | number | no |  |
| `index_interval` | number | no |  |
| `band` | integer | no |  |

### `set_rule_based_labels`

Label a vector layer with RULES instead of one style: each rule has a field to show, an optional filter (a QGIS expression such as "population" > 10000), a font size and colour, and optional scales (min_scale = zoomed-out limit as a denominator, max_scale = zoomed-in limit). Up to 20 rules. This replaces the layer's current labels. clear=true removes the layer's labels (no rules needed). To get the previous labels back after a change, use undo_last_operation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `rules` | array[object] | no |  |
| `clear` | boolean | no |  |

## symbology_tools

### `set_label_style`

Style the labels already on a vector layer (add them first with apply_labels): font colour and size, bold, italic, the halo around the text (on/off, colour, size), placement (around_point, over_point, horizontal, free, curved, parallel), the scales between which labels show (visible_zoomed_out_to = the smallest scale such as 250000 for 1:250,000, visible_zoomed_in_to = the largest such as 5000), and show_labels to switch labels on or off. Give only what should change. Rule-based labeling is reported, not changed.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `font_color` | string | no |  |
| `font_size` | number | no | Points, 1 to 120. |
| `bold` | boolean | no |  |
| `italic` | boolean | no |  |
| `halo` | boolean | no | Draw a halo (buffer) round the text. |
| `halo_color` | string | no |  |
| `halo_size_mm` | number | no | 0 to 10. |
| `placement` | string | no |  |
| `visible_zoomed_out_to` | number | no | Scale denominator, e.g. 250000. |
| `visible_zoomed_in_to` | number | no | Scale denominator, e.g. 5000. |
| `show_labels` | boolean | no |  |

### `set_layer_symbol`

Change how a vector layer's symbols are drawn beyond colour: outline colour and width, line pattern (solid, dashed, dotted, dash_dot), marker shape (circle, square, diamond, triangle, star, cross, x, pentagon, hexagon, heart, arrow) and size, fill pattern (solid, none, hatch_forward, hatch_backward, horizontal, vertical, cross, diagonal_cross, dots_dense, dots_sparse) and opacity. Give only what should change; everything else stays. Colours can be hex or plain words ('dark red'). On a categorized, graduated or rule-based layer it keeps the classification colours and sizes: fill_color and marker_size_mm are refused there (use the style tool that made the classes). Only simple symbols are changed; an SVG or font marker is reported, not overwritten.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `fill_color` | string | no |  |
| `outline_color` | string | no |  |
| `outline_width_mm` | number | no | 0 to 20; 0.26 is a thin line, 1 a thick one. |
| `opacity_percent` | number | no | 0 to 100 for the whole layer. |
| `marker_shape` | string | no |  |
| `marker_size_mm` | number | no | 0.1 to 100. |
| `line_style` | string | no | Pattern of a line or of a polygon outline. |
| `fill_style` | string | no | Pattern of a polygon fill, for example hatch_forward. |

### `set_raster_style`

Change how a raster layer is displayed: mode='unique_values' gives one colour per distinct cell value (for land cover, classes, zones; refused above 256 distinct values), resampling (nearest keeps blocky cells, bilinear or cubic smooth them), opacity_percent, and no-data: nodata_min/nodata_max make cells in that range transparent (both ends are INCLUDED: for 'below 0' give nodata_max just under 0, such as -0.000001), clear_nodata=true restores the file's own no-data. Give only what should change. Display only; the cell values are not changed. For a continuous colour ramp use apply_raster_stretch.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes |  |
| `mode` | string | no | 'unique_values' |
| `resampling` | string | no | nearest, bilinear or cubic |
| `opacity_percent` | number | no |  |
| `nodata_min` | number | no |  |
| `nodata_max` | number | no |  |
| `clear_nodata` | boolean | no |  |

## table_importers

### `import_humanitarian_table`

Read a published humanitarian table from a CSV/Excel file the user supplies (typically downloaded from HDX) and validate it: kind 'ipc' (IPC area phase 1-5, population, phase 3+ population), 'inform' (INFORM Risk 0-10 scores) or 'unosat' (damage points with coordinates and damage class). Columns are matched by common names, but the layouts are UNVERIFIED against real files: the result shows the mapping used, and anything not matched or ambiguous is listed, so check it and pass an explicit `mapping` ({role: column}) if needed. Nothing is repaired or imputed: an invalid or missing value is reported and left empty (a missing IPC phase is not phase 1). For ipc and inform, giving `layer_name` and `layer_key_field` (P-code preferred) reports how the rows join to the admin layer and, with `write_fields`, writes the values to it as new numeric fields (needs confirmation); unmatched and duplicate keys are never guessed. For unosat, load the points with load_tabular_data_as_layer using the detected latitude/longitude columns. Official-source values: quote the file and its date, not this tool, as the source.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file_path` | string | yes | Absolute path to the .csv/.xlsx/.xls file. |
| `kind` | string | yes | 'ipc', 'inform' or 'unosat'. |
| `mapping` | object | no | Optional explicit {role: column}. Roles -- ipc: area_code, area_name, phase, population, phase3plus_population, period; inform: area_code, area_name, risk, hazard_exposure, vulnerability, lack_of_coping_capacity; unosat: latitude, longitude, damage_class, site_id. |
| `sheet_name` | string | no | Sheet for Excel files. Defaults to the first. |
| `delimiter` | string | no | CSV delimiter. Defaults to ','. |
| `layer_name` | string | no | Optional admin polygon layer to join to (ipc/inform). |
| `layer_key_field` | string | no | Field on that layer holding the P-code (or name when the file has no code). |
| `write_fields` | boolean | no | With layer_name: write the values to the layer as new numeric fields (ipc_phase, ipc_pop, ipc_p3plus / inf_risk, inf_haz, inf_vuln, inf_coping). Needs confirmation. |

## task_grid_tools

### `generate_mapping_task_grid`

Split an area of interest into a grid of square mapping tasks for remote or crowd mapping (Tasking Manager style), so volunteers can digitise roads and buildings without overlapping. Cells are cell_size_m wide (measured in a local metric projection) and clipped to the area. Optionally ranks tasks High / Medium / Low by how many points of priority_points_layer fall in each (e.g. damage reports, existing buildings) or by the population in population_raster_layer, so the most important cells are mapped first. Creates a polygon layer and can write the tasks as GeoJSON (EPSG:4326, properties task_id, area_km2, value, priority) for import into a tasking tool; it has NOT been checked against a specific Tasking Manager instance's import rules.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `aoi_layer` | string | yes | Polygon layer with the area of interest. |
| `cell_size_m` | number | no | Task width in metres (minimum 100). Default 2000. |
| `priority_points_layer` | string | no | Optional point (or other vector) layer; the priority value is the number of its features in each cell. |
| `population_raster_layer` | string | no | Optional population raster; the priority value is the sum of its cells in each task. Ignored if priority_points_layer is given. |
| `aoi_where` | string | no | Optional QGIS expression (e.g. "ADM1_EN" = 'Aden') limiting the area to matching features of aoi_layer. Use this instead of filtering the source layer, which would hide features from the whole project. |
| `output_layer_name` | string | no | Name of the new task layer. Default 'mapping_tasks'. |
| `export_geojson_path` | string | no | Optional file path for the GeoJSON export. Use 'auto' to write into the system temp folder. |

## tool_discovery

### `find_tools`

Look up which tools can do a step you were not given a tool for (for example 'contour lines', 'split a line by polygons', 'download elevation'). Returns the best matching tool names with a one-line description each, and makes them available for the rest of this request. Use it BEFORE writing a script. It only searches; it changes nothing.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `need` | string | yes | The operation you need, in plain English words, even when the user wrote in another language (tool names and descriptions are English, so an Arabic or French phrase finds nothing). Name the operation, not the goal: 'graduated colour style for polygons by a number', 'clip lines to polygons', 'count points in each polygon', 'turn a layer on and off'. |

### `run_steps`

Run several tool calls in order in ONE step instead of one model turn each. Use it only when you already know every argument of the whole chain (for example you choose the output layer names yourself). Each step is {tool, arguments}; an argument may be the whole-string reference "$2.layer_name" (field `layer_name` of step 2's result) or "$prev.layer_name". Steps run one at a time through the normal tool path, so confirmations and safety checks still apply; the run STOPS at the first error or the first call waiting for the user's Confirm and reports exactly which steps ran. At most 8 steps; no deleting tools; do not nest run_steps. If a later step depends on something you must look at first, make separate calls instead.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `steps` | array[object] | yes | Ordered steps. |

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

List every tool call made so far during THIS turn (this one user request), each tagged with its operation type and, when it added a new layer, whether it can be undone with undo_last_operation. Use this before undo_last_operation to see what's actually available to undo. Also lists undoable calls from the last few earlier messages (marked earlier_turn).

_No parameters._

### `undo_last_operation`

Reverse the most recent undoable tool call: one made this turn, or if there is none, the latest one from the last few earlier messages (the user just says 'undo that'; see get_turn_transaction_log to check what qualifies first). Call this tool for any 'undo' request instead of clearing or re-setting the thing by hand. Covers: a call that added a new layer (removes it); remove_layer (restores the removed layer and its data); field_calculator/calculate_area/calculate_length (restores the field's prior values, or deletes it if it didn't exist before); apply_categorized_style/apply_graduated_style/apply_graduated_symbol_style (restores the prior style); set_dataset_status/set_layer_sensitivity/set_layer_confidence/run_query/set_layer_filter (restores the prior value); labels, callouts, diagrams, point markers, raster relief, saved symbols, layer elevation and layer time settings (restores the prior setting); delete_features (puts the deleted features back); add_field (removes the new field again, but only while it is still empty: once it holds values undo refuses and says so). It cannot undo load_project or any other in-place edit not in that list -- a real, separate, still-open gap, not something this tool silently skips without saying so. Destructive action requiring UI confirmation.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `confirmed` | boolean | no | Set true only after the user has confirmed the undo. |

## trigger_tools

### `evaluate_forecast_trigger`

Evaluate an anticipatory-action trigger rule against forecast values already in a layer's attribute table: for each area, does the forecast reach the threshold within the lead window (optionally with a minimum probability)? Returns which areas are activated, with the maximum forecast value, the number of exceeding forecast rows and the first exceedance date, plus the rule restated in words. The threshold, lead window and probability cut-off MUST come from the user's own trigger protocol -- this tool has no defaults and never invents one; if the user has not given a threshold, ask for it. It evaluates a rule; it does not fetch or generate forecasts and its answer is only as good as the forecast data in the layer. Read-only.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `layer_name` | string | yes | Layer (or table) holding forecast rows: one or more per area. |
| `value_field` | string | yes | Numeric field with the forecast value (e.g. river discharge, rainfall, wind speed). |
| `threshold` | number | yes | Trigger threshold, from the user's protocol. Required. |
| `comparison` | string | no | Default '>='. |
| `unit_field` | string | no | Field identifying the area (admin name/code, station). Omit to evaluate the whole layer as one unit. |
| `date_field` | string | no | Field with the date the forecast is valid for. Required with lead_days. |
| `lead_days` | number | no | Only count forecast rows dated from as_of to as_of + lead_days. |
| `as_of` | string | no | ISO date the lead window starts from. Default today. |
| `probability_field` | string | no | Optional numeric field with the forecast probability of the value (0-1, or 0-100 with probability_scale='percent'). |
| `min_probability` | number | no | With probability_field: minimum probability for a row to count, in the same unit as the field (0-1, or 0-100 when probability_scale is 'percent', e.g. 70 for 70%). |
| `probability_scale` | string | no | 'fraction' (default): probability_field and min_probability are 0-1. 'percent': both are 0-100. |
| `min_exceedances` | integer | no | Exceeding forecast rows needed to activate a unit. Default 1. |

## watershed_tools

### `delineate_watershed`

Delineate the watershed upstream of an outlet point on a DEM in the project and MEASURE it: basin area, longest hydraulic flow path, H (elevation drop along it), main-channel slope and the Kirpich time of concentration. Adds the basin, flow path and outlet to the project. location is DMS ('32°01'47.39"N, 35°48'21.00"E') or 'lat, lon'. Needs an elevation raster that covers the point (fetch_dem first if none). It does NOT invent rainfall intensity or a runoff coefficient: the reply says which design inputs the user must give, then use calculate_rational_watershed_peak_flow for the peak flow.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `location` | string | no | Outlet as DMS or 'lat, lon'. |
| `lat` | number | no |  |
| `lon` | number | no |  |
| `dem_layer` | string | no | Name of the DEM raster; default: a raster in the project that covers the point. |
| `return_period_years` | number | no | Design return period, used to word the design-input request. |
| `radius_km` | number | no | Half-width of the window read around the outlet (default 8, at most 15). |
| `snap_distance_m` | number | no | How far the outlet may move onto the derived channel (default 300). |
| `layer_prefix` | string | no | Prefix for the new layers (default 'Watershed'). |

## web_research_tools

### `web_research` _(network-only)_

Search the internet and get back real results with their SOURCES: title, URL, outlet, date and snippet. kind='web' for pages, kind='news' for recent news articles (last 1 to 30 days). Use this whenever the user wants information from the internet 'with the source', news, or a fact you cannot know. The answer must cite the returned URLs and must not add facts the results do not contain. For a MAP of incidents from the news use find_incident_reports with sources=['news'] instead.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | What to look up, in a few clear words. |
| `kind` | string | no | 'web' (default) or 'news'. |
| `max_results` | integer | no | How many results (default 8, at most 25). |
| `days` | integer | no | For kind='news': how many days back (1 to 30, default 7). |
