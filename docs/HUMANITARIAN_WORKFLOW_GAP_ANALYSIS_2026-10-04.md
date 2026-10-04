# Humanitarian workflow gap analysis (2026-10-04)

Source: the owner's document "Humanitarian Mapping Workflows: From Field Operations to Strategic Orchestration" (6 workflows in two phases). Compared against the tools registered in this repo (184 in `docs/TOOLS_REFERENCE.md`) by reading their names, descriptions and the relevant code. **Static comparison only:** nothing here was run, and "covered" means a tool exists for the step, not that it was hand-tested. A dated snapshot; do not edit after the fact, supersede it with a new doc.

Legend: **Covered** = a tool does the step. **Partial** = a tool does part of it, the gap is stated. **Missing** = no tool.

## Phase I -- operational and field mapping

### 1. Rapid crisis and base mapping
| Need in the document | Status | What exists / what is missing |
|---|---|---|
| OSM base data, Geofabrik extracts | Covered | `fetch_osm_features`, `ingest_osm_features`, local Geofabrik extract lookup (`local_data_sources`) |
| Building footprints, admin boundaries | Covered | `fetch_building_footprints`, `fetch_geoboundaries`, `fetch_hdx_admin_boundaries` |
| Damage assessment from imagery | Partial | `calculate_raster_change_detection`, `calculate_damage_exposure_severity`, `extract_features_from_imagery`, `search_stac_satellite_imagery`. No ingest of a published damage product |
| UNOSAT damage / flood-extent products | Missing | Only reachable through generic `search_hdx_datasets`; no loader that normalises damage-point/polygon classes into a layer with a damage-class field |
| HOT Tasking Manager / MapSwipe: split an area into mapping tasks | Missing | No task-grid generator (grid cells over an AOI with size, ID, priority from population/damage) and no export for those platforms |
| Safe operational corridors | Partial | `score_route_incident_risk`, `optimize_delivery_route`; no tool that proposes a corridor avoiding damaged/blocked/high-incident segments |

### 2. MSNA and field data collection
| Need | Status | Notes |
|---|---|---|
| Population baseline for sampling frames | Covered (WorldPop) | `fetch_worldpop_population`, `zonal_statistics`. LandScan: missing (licensed data; a decision, not just a build) |
| Spatial sampling frame design (stratified by camp/host area, cluster sampling, sample-size per stratum) | Missing | No tool. Only generic raster random points inside classification |
| Kobo / ODK import (API pull, XLSForm geometry, repeat groups, GPS question types) | Missing | Only `load_tabular_data_as_layer` for an exported CSV/XLSX |
| Offline field collection package (QField project, form template) | Missing | None |
| Household-survey indicators aggregated to admin units (weighted % lacking service, with confidence interval, minimum-n suppression) | Partial | `aggregate_data`, `field_statistics`, `calculate_population_in_need`; no survey-weight or small-n suppression logic |
| REACH / IMPACT baseline data | Covered by search | `search_hdx_datasets` only |

### 3. Logistics, route planning, catchment analysis
| Need | Status | Notes |
|---|---|---|
| Travel-time catchments, blind spots, facility siting | Covered | `calculate_service_area`, `travel_time_matrix`, `classify_facilities_by_access`, `population_access_gap`, `optimal_hub_siting`, `location_allocation` |
| Route optimisation | Covered | `optimize_delivery_route`, `estimate_road_speeds` |
| Destroyed bridges, checkpoints, flooded roads as network constraints | Partial | `build_composite_impedance_field` is described as taking a closure/penalty input; there is no dedicated "apply barrier layer: block or penalise road segments within X m of these points/polygons" tool, and none that derives barriers from a flood extent |
| Logistics Cluster operational layers (road status, border crossings, fuel) | Missing | Not fetched; HDX search might surface static copies only |
| Supply-chain bottleneck identification | Missing | No betweenness / critical-link analysis on the road network |

## Phase II -- strategic decision-making and donor orchestration

### 4. Intersectoral severity mapping (JIAF)
| Need | Status | Notes |
|---|---|---|
| Composite severity per admin unit, class 1-5 | Partial | `calculate_severity_index` (min-max, weights, 1-5 class). It is "JIAF/INFORM-style", **not** the JIAF method: no sector-level 1-5 inputs, no People-in-Need by severity phase, no JIAF aggregation rules. Do not describe it as JIAF-compliant |
| IPC food-insecurity phases | Missing | No IPC loader / phase-1..5 population table import |
| ACLED conflict events overlay | Partial | Event-type taxonomy validation in `add_incident_point`; **no ACLED data fetch** (needs the owner's API credentials and licence terms) and no event-density-by-admin tool beyond `hotspot_analysis` |
| Cholera / outbreak surveillance data | Missing | Nothing; generic CSV load only |

### 5. Donor allocation and prioritisation
| Need | Status | Notes |
|---|---|---|
| Multi-criteria overlay | Partial | `weighted_overlay_analysis` is raster-only; there is no vector/admin-unit MCDA with weights, sensitivity testing and rank stability |
| Financial flows | Partial | `fetch_fts_funding_data` returns plan-level requirements, funding and gap; **it is not geographic** |
| "Funding orphan" map (high need, no funding) | Missing | Needs geographic funding (e.g. 3W/4W funding or FTS location data -- whether FTS exposes enough location detail is **unverified**); `calculate_presence_gap` covers presence, not money |
| Allocation envelope (split a budget by severity and population) | Missing | None |
| INFORM Risk Index import | Missing | HDX search only |

### 6. Anticipatory action and forecast-based financing
| Need | Status | Notes |
|---|---|---|
| Hazard feeds | Covered | `fetch_gdacs_disaster_alerts`, `fetch_nasa_eonet_events`, `fetch_nasa_active_fires` |
| Hydrological forecasts (GloFAS) / rainfall (CHIRPS, forecasts) | Missing | No fetch or raster ingest |
| Trigger models (threshold + lead time + return period -> activate) | Missing | `forecast_trend` is a linear trend projection, not a trigger model; `run_monitoring_workflow` / `schedule_recurring_workflow` can re-run and diff, but there is no threshold-exceedance rule or alert output |
| Exposure of forecast flood to people and assets | Partial | `estimate_population_exposure` takes a polygon; chaining from a forecast raster is manual |
| INFORM Climate Change tool | Missing | -- |
| Engineering hydrology (peak flow for a catchment) | Covered (beyond the document) | `calculate_rational_watershed_peak_flow`, see `HYDROLOGY_ENGINEERING_TOOLS_2026-10-04.md` |

## Proposed additions, in suggested order

Ordering favours what needs no external credentials and builds on existing tools. Sizes are rough guesses, not estimates from measured work.

| # | Proposed tool / task | Closes | Depends on | Notes |
|---|---|---|---|---|
| H1 | `apply_network_barriers` -- block or penalise road segments near barrier points/polygons, writing the impedance field `calculate_service_area` already accepts | W3 barriers | `build_composite_impedance_field` | Pure geometry; offline-testable core. Highest value for the logistics story |
| H2 | `generate_mapping_task_grid` -- grid of tasks over an AOI with ID, area, population/damage priority; GeoJSON export for HOT Tasking Manager | W1 | WorldPop, zonal stats | Pure, offline-testable |
| H3 | `design_sampling_frame` -- stratified / two-stage cluster sample of points or admin units, sample size per stratum, seed recorded | W2 | WorldPop | Pure; needs the owner's methodological choice (design effect, confidence level) |
| H4 | `evaluate_forecast_trigger` -- threshold + lead-time rule over a numeric field or raster statistic, returns activated / not activated per unit with the rule printed | W6 | `run_monitoring_workflow` | Pure rule evaluator first; data feeds later. Must state the thresholds are user-supplied, never invented |
| H5 | `calculate_mcda_ranking` -- vector/admin-unit MCDA with weights, direction, and a weight-perturbation stability check | W5 | `calculate_severity_index` | Distinct from the raster tool |
| H6 | Survey aggregation with weights and minimum-n suppression | W2 | `aggregate_data` | Disclosure-control relevant (small cells) |
| H7 | Importers for published tables: IPC phases, INFORM Risk, UNOSAT damage points (from HDX files the user supplies or HDX returns) | W1, W4, W5 | `search_hdx_datasets`, `load_tabular_data_as_layer` | File-based first; no new network service |
| H8 | Allocation envelope: split a budget over units by severity x population with caps | W5 | H5 | Advisory output, labelled as a calculation not a recommendation |
| H9 | Critical-link / bottleneck analysis on the road network | W3 | routing tools | Needs a performance check on national networks (an earlier network analysis took minutes) |
| H10 | Kobo API pull; ACLED fetch; GloFAS/CHIRPS fetch; Logistics Cluster layers; LandScan | various | credentials / licences | **Blocked on owner decisions** (API keys, licence terms, hosted-gateway question), not scheduled |

Not proposed: anything that would present a cholera, famine or funding figure without a supplied data source -- the existing grounding guard (#75) makes the model refuse unsupported claims, and new tools must keep to that.

## What needs the owner

1. Which of H1-H9 to build first (my suggestion: H1, H4, H2).
2. Credentials/licence decisions for H10 (Kobo, ACLED, GloFAS, Logistics Cluster, LandScan).
3. Whether `calculate_severity_index` should be renamed or documented as "JIAF-style" only, versus building a real JIAF-method tool.
