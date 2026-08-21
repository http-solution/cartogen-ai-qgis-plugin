# Route Risk-Scoring & No-Go Zones — Specification

**Status: SHIPPED (2026-08-20) for §3.1 and §3.2; §3.3 (no-go zones) shipped as prompt guidance, not
a new tool, exactly as scoped.** `analyze_incident_trend` (`agent/tools/analysis_tools.py`) and
`score_route_incident_risk` (`agent/tools/logistics_tools.py`) implement the pipelines described
below; `_bucket_dates_by_period`'s date-bucketing math is unit-tested, along with both tools'
degrade-outside-QGIS paths. **What's NOT verified**: real behavior against a live QGIS session with
real incident/route/zone data -- neither tool has been run against a real project, and §6's own
"cannot verify without live QGIS" list is unchanged by shipping this code. The design below is left
as originally written, as the record of what was specified, matching the convention
`PROMPT_REFINEMENT_LAYER_SPEC.md`/`SAM_IMAGERY_EXTRACTION_SPEC.md` established for a shipped spec.

---

## 1. Problem

Three related gaps, all confirmed against the real code before writing this:

1. **`hotspot_analysis` is a single snapshot, not a trend.** (`agent/tools/styling_tools.py`, tool
   schema: `point_layer`, `radius`, `pixel_size`, `weight_field` — no date/time parameter at all,
   confirmed by reading the full tool definition.) It answers "where is incident density high right
   now," never "is density in this area rising or falling over the last N weeks" — the actual
   question a field-security decision usually needs answered.
2. **No tool scores a planned route against incident proximity.** `optimize_delivery_route` and
   `travel_time_matrix` (`agent/tools/logistics_tools.py`) compute routes and distances with zero
   awareness of where incidents have happened. `buffer_analysis` (`agent/tools/vector_tools.py`) and
   `hotspot_analysis` both exist and could answer "what's near this route" if composed together, but
   nothing does that composition today.
3. **No-go / security-restricted zones aren't modeled at all.** `docs/ROUTE_OPTIMIZATION_STRATEGY.md`
   §1 already recommends a damage/passability field to hard-exclude physically damaged road segments
   from routing — but that recommendation is scoped to physical road damage, not security-restricted
   areas, which operationally need the identical hard-exclude treatment (a route through a no-go zone
   is not "slower," it's not a valid route at all, the same as a route through a destroyed bridge).

`add_incident_point` (`agent/tools/humanitarian_tools.py`) already requires a `date` on every incident
and supports an optional `severity` field — both gaps above can be closed by composing what already
exists (`hotspot_analysis`, `buffer_analysis`, `difference_layers`, and `analysis_tools.py`'s existing
`_linear_regression`/`_forecast_series` trend math from `forecast_trend`) rather than inventing new
statistics or a new routing engine.

## 2. Non-goals

- **Not a live/real-time incident feed.** Same offline-first reasoning `ROUTE_OPTIMIZATION_STRATEGY.md`
  §1 already applied to rejecting live traffic/weather APIs — this works against the same
  already-loaded Incidents layer (`add_incident_point`'s shared layer) or any point layer the user
  provides, not a live external feed.
- **Not automatic re-routing.** These tools *score* a route or *exclude* a zone from the network used
  for routing — they don't silently pick a different route on the user's behalf. A scored route is
  still information for a human to act on; a no-go zone is an explicit input the user supplies, not
  something inferred automatically.
- **Not incident classification or severity prediction.** Consumes `add_incident_point`'s existing
  `severity` field as-is; does not attempt to classify incident type or predict future incident
  locations. `forecast_trend` already exists for genuine linear projection and is reused here for
  exactly that purpose (period-over-period incident counts), not extended into new predictive claims.
- **Not a replacement for `hotspot_analysis`.** The new trend tool (§3.1) is a companion, answering a
  different question (change over time vs. current density) — `hotspot_analysis` stays as-is for
  single-snapshot density.
- **Not fixed-buffer-only for the no-go concept.** A no-go zone is a real polygon (an actual
  restricted area boundary), not a buffer radius — keeps this simple and matches how such zones are
  actually communicated operationally (a named area, not "N km around a point").

## 3. Proposed tools

### 3.1 `analyze_incident_trend` — is density rising or falling

```
analyze_incident_trend(
    point_layer: str,
    date_field: str,
    zone_layer: str,
    zone_name_field: str,
    period_days: int = 30,
    periods_ahead: int = 1,
)
```

Pipeline:
1. For each feature in `zone_layer` (e.g. districts, or a hand-drawn area-of-interest polygon layer),
   count how many `point_layer` incidents fall within it per `period_days`-sized time bucket, using
   `date_field` (matches `add_incident_point`'s required `date` field directly, but works with any
   point layer carrying a date field, not just the shared Incidents layer).
2. Feed each zone's (period, count) series into `agent/tools/analysis_tools.py`'s existing
   `_forecast_series` (the same function `forecast_trend` already uses and this codebase already
   tests) — reusing real, shipped trend math instead of inventing a new statistic. This directly
   reuses `_linear_regression`'s slope/R² output, so a zone's trend comes with the same
   `fit_confidence`/`trend_direction` framing `forecast_trend`'s own output already has, and the same
   "present as a projection, not a certain fact" prompt rule (rule 20) applies unchanged.
3. Return per-zone: total incidents in the most recent period, trend direction (rising/falling/flat),
   fit confidence, and (if `periods_ahead` > 0) a projected count for future periods — explicitly
   labeled a projection, matching rule 20's existing requirement.

This is a genuinely thin composite: no new statistical method, just re-running already-tested trend
math over an incident-count series instead of a `value_field` series, and reusing zonal point-counting
(the same `QgsSpatialIndex` + centroid/contains pattern `agent/tools/imagery_extraction.py`'s
`_pixel_to_map`-adjacent counting logic and `agent/tools/analysis_tools.py`'s `_count_points_in_polygons`
already establish for `calculate_damage_exposure_severity`'s building-exposure count).

### 3.2 `score_route_incident_risk` — how close does this route pass to recent incidents

```
score_route_incident_risk(
    route_layer: str,
    incident_layer: str,
    buffer_distance: float,
    date_field: str = None,
    days_back: int = None,
    weight_field: str = None,
)
```

Pipeline:
1. Buffer `route_layer` by `buffer_distance` (reuses `buffer_analysis`'s exact processing call/pattern
   — not a new geometry algorithm, the same `native:buffer` invocation already shipped).
2. Count/list `incident_layer` points falling within that buffer, optionally filtered to
   `date_field`/`days_back` (e.g. "incidents in the last 30 days") and optionally weighted by a
   `weight_field` (e.g. a numeric severity score, if the incident layer carries one) for a weighted
   total rather than a flat count.
3. Return the incident count/list within the buffer (each with its own distance-from-route), a
   weighted risk score if `weight_field` given, and the buffer polygon itself as a new layer so it can
   be inspected/styled directly — matching this codebase's convention of adding a real inspectable
   layer, not just a JSON number, for any spatial result (`_write_scores_to_layer`'s output_field
   pattern applied conceptually, though this result is inherently spatial rather than per-admin-unit).

`route_layer` is deliberately generic (any line layer) rather than requiring a specific tool's output
format — works directly on a hand-drawn route, `travel_time_matrix`'s output, or a road-network
subset, without coupling this tool to one specific upstream source.

### 3.3 No-go zones as a routing precondition, not a new tool

Rather than a fourth new tool, this is a **usage pattern** using two tools that already exist:

1. `difference_layers(road_network_layer, restricted_zones_layer)` (`agent/tools/vector_tools.py`,
   `native:difference` under the hood — confirmed it has no line-vs-polygon geometry-type restriction,
   QGIS's own overlay algorithm handles mixed geometry types) removes any road segment intersecting a
   restricted-zone polygon, producing a new network layer with those segments physically absent.
2. Pass **that** resulting layer as `road_network_layer` to `calculate_service_area`/
   `travel_time_matrix` unchanged — those tools' own Dijkstra-based routing simply has no path through
   an absent segment, which is a genuine hard-exclude (not a high-cost penalty a sufficiently long
   detour could still traverse).

**Why not a new parameter on the existing routing tools instead:** a `restricted_zones_layer`
parameter added directly to `calculate_service_area`/`travel_time_matrix` was considered and rejected
— it would mean re-deriving the difference-and-reroute logic inside two places instead of one, when
`difference_layers` already does exactly this operation correctly today. The one-line composition
(`difference_layers` then route on the result) is simpler than adding and maintaining a new parameter
path through QGIS's native algorithm call. Worth a prompt-rule addition (§4) so the model reaches for
this composition rather than trying to hand-roll a network edit via `execute_pyqgis_script`.

## 4. Prompt guidance (new rule, once built)

Mirroring rule 25's "recognize humanitarian-logistics intent without the tool being named" pattern:
add coverage for "avoid this area," "route around the no-go zone," "how close does this route go to
recent incidents" phrasing mapping to `score_route_incident_risk` and the `difference_layers` +
routing composition in §3.3 — and an explicit line steering away from hand-rolling a network-segment
removal via `execute_pyqgis_script` when `difference_layers` already does it (matching rule 30's
existing steering-away-from-hand-written-composition pattern for print layouts).

## 5. Failure modes and fallbacks

- **No incidents in the time window** (§3.1): a real, valid zero-trend result (`{"success": true,
  "trend_direction": "flat", "total_incidents": 0, ...}`), not an error — matches this codebase's
  "empty result is different from failure" convention (`calculate_presence_gap`'s empty-match
  handling, `run_monitoring_workflow`'s no-change case).
- **Too few periods to fit a trend** (§3.1): `_forecast_series` already returns a clear error for
  under 3 data points — reused as-is, no new error-handling logic needed.
- **`route_layer`/`incident_layer` CRS mismatch** (§3.2): reuse `verify_crs_compatibility`
  (already used by `difference_layers`, `union_layers`, etc.) rather than a silent/incorrect buffer.
- **Restricted-zones layer removes the only path to a facility** (§3.3): `calculate_service_area`/
  `travel_time_matrix` already return an empty/no-path result in this case with their existing error
  handling — no new handling needed, but worth stating plainly in the response that a facility became
  unreachable specifically because of the excluded zone, not a data error, so the model doesn't
  misdiagnose it.

## 6. What can and can't be verified before shipping

**Can verify in this environment, before any live QGIS pass:**
- `_forecast_series`/`_linear_regression` reuse (§3.1) — already covered by existing tests, pure
  Python, no new logic to test beyond the period-bucketing step feeding it.
- Zonal point-counting logic (§3.1) — same shape as `_count_points_in_polygons`
  (`analysis_tools.py`), already tested for `calculate_damage_exposure_severity`.
- Degrade-gracefully-outside-QGIS paths for both new tools (same convention as every other tool).
- CRS-mismatch and empty-result handling logic.

**Cannot verify without a live QGIS session:**
- Whether `native:difference` genuinely produces a clean, routable network with no dangling/invalid
  edges after removing restricted-zone-intersecting segments (`native:shortestpathpointtolayer`'s
  graph builder may be sensitive to a network with newly-created gaps at the removal boundary — this
  is the one piece of §3.3 that's a real assumption, not just an untested-but-straightforward
  parameter pass-through).
- Real behavior of `buffer_analysis` + point-counting at genuinely large incident-layer sizes
  (performance, not correctness — no reason to expect it behaves differently from any other spatial
  join in this codebase, but not measured).

## 7. Relationship to other roadmap docs

- `docs/ROUTE_OPTIMIZATION_STRATEGY.md` §1 item 1 (damage/passability field): this spec extends that
  same hard-exclude reasoning to security-restricted areas specifically, using a different mechanism
  (`difference_layers` on the network layer) suited to a named-area input rather than a per-segment
  attribute field, since a restricted zone is communicated as an area boundary, not a road condition.
- `docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md`: not a security-of-the-plugin item (that's Part A
  of that review) — this is field/operational security, the other meaning of the word, as
  distinguished explicitly when this gap was first raised.
- `docs/HUMANITARIAN_GIS_FEATURE_REVIEW.md`: no direct dependency: this spec's tools consume
  `add_incident_point`'s existing shared Incidents layer but don't require any severity-index tool
  from that review to already be in use.
