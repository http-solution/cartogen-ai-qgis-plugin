---
description: Which external services each tool reads, what needs a key, and what each source can and cannot tell you.
---
Fetch tools call public services **directly from your machine** (through QGIS's network stack, so your proxy applies); the data is not routed through the model provider, although what a tool returns is then described to the model. See [What leaves your machine](@security/privacy).

| Source | Tools | Key needed | Notes |
|---|---|---|---|
| **HDX** (Humanitarian Data Exchange, `data.humdata.org`) | `search_hdx_datasets`, `fetch_hdx_admin_boundaries` | No | OCHA COD-AB boundaries with P-codes. Coverage is not universal; fall back to geoBoundaries. |
| **geoBoundaries** | `fetch_geoboundaries` | No | Broader country coverage, no P-codes. |
| **OpenStreetMap** via Overpass; Nominatim for geocoding | `fetch_osm_features`, `ingest_osm_features`, `geocode_and_enrich`, `geocode_batch` | No | Overpass is rate-limited; `geocode_batch` runs up to 25 lookups with pauses and stops when you press Stop. |
| **Geofabrik** extracts | local base-data loader | No | Downloaded once (roads, health facilities) instead of fetched live; the plugin offers it. Large downloads ask for confirmation. |
| **WorldPop** | `fetch_worldpop_population` | No | The fetch is clipped to the area needed; a whole-country raster is refused by default. A population raster named like a density raster is refused until you state the unit. |
| **Microsoft Global ML Building Footprints** | `fetch_building_footprints` | No | A periodic dataset refresh. |
| **Copernicus DEM GLO-30** | `fetch_dem` | No | About 30 m, a surface model, not bare earth. The result records source, tiles, date, datum and the licence's required notices. Print layouts and PDFs are not stamped with the notice: add it yourself when you publish. |
| **Satellite imagery** via a STAC API (Element84 Earth Search) | `search_stac_satellite_imagery` | No | Scene search. Imagery feature extraction needs optional packages and a model checkpoint. |
| **OCHA FTS** (`api.hpc.tools`) | `fetch_fts_funding_data` | No | Funding flows. |
| **GDACS** (UN/EC disaster alerts) | `fetch_gdacs_disaster_alerts`, `find_incident_reports` | No | **Global only**: it cannot be asked for a country, so results are filtered locally. |
| **NASA EONET** | `fetch_nasa_eonet_events`, `find_incident_reports` | No | Natural events. |
| **NASA FIRMS** | `fetch_nasa_active_fires` | **Yes**, free (Settings) | Satellite fire and thermal anomalies. Only needed for this tool. |
| **USGS earthquakes** (FDSN GeoJSON) | `fetch_usgs_earthquakes`, `find_incident_reports` | No | Bounding box, days, minimum magnitude; layer coloured by magnitude band. |
| **UCDP Candidate Events** (CC BY 4.0 download) | `fetch_ucdp_conflict_events`, `find_incident_reports` | No | **Preliminary and weeks old**; every result says so and names the newest event date. The UCDP API itself needs a token and is not used. |
| **ReliefWeb** disasters (RSS feed) | `find_incident_reports` | No | The feed has no coordinates, so items are listed rather than mapped. The structured API refuses an unregistered application name. |
| **Web search** (`ddgs`; Gemini grounded search) | `search_web`, `gemini_grounded_search` | No | General web; results are untrusted text. For incident questions use `find_incident_reports`. |

## Incident search, honestly

`find_incident_reports` answers "what incidents, disasters or conflict events happened in <place>" from a **fixed list of named sources** (GDACS, USGS, EONET, UCDP, ReliefWeb) instead of the open web, in parallel. Every record carries source, rating, date and link; records with a position become an *Incident reports* layer. Every reply names the sources that **answered**, the ones that **could not be reached**, and the ones **not searched**, so an empty result is not read as "nothing happened". It does not search:

- **News outlets and fact-checkers**: the Reuters, AFP and Full Fact pages cannot be read by a program.
- **Liveuamap**: a paid API.
- **ACLED**: needs a registered key and agreement to its terms (a credentialed integration is on the deferred list).
- **Social media**: out of scope.

## Dashboards need internet

`generate_html_dashboard` and related exports load Leaflet, Chart.js and basemap tiles from public CDNs when the file is opened, so an offline machine shows an incomplete dashboard.
