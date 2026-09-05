# Route Optimization Strategy — Post-Disaster / Humanitarian Logistics

**Role framing:** GIS analyst / logistics specialist review of Cartogen AI's actual current routing
tools, written for the post-disaster/humanitarian scenario (mixed 4x4s, delivery trucks, and on-foot
field workers; damaged and unpaved roads; unreliable, changing conditions). Every claim about "current
behavior" below is checked against `agent/tools/logistics_tools.py` as it exists today — file:line
verifiable, same standard as this project's other reviews.

**Status: strategy + prototype script. Nothing in `agent/tools/logistics_tools.py` has been changed by
this document** — recommendations are scoped as follow-up work, not applied yet.

---

## 0. What the current routing method actually is (and isn't)

`agent/tools/logistics_tools.py`'s own module docstring is upfront about this, and it's worth
repeating rather than glossing over: `calculate_service_area` and `travel_time_matrix` are the two
road-network-aware tools, and both call QGIS's native Network Analysis processing algorithms
(`native:serviceareafrompoint`, `native:shortestpathpointtolayer` — a Dijkstra-family shortest-path
implementation over a `QgsGraphBuilder` graph). **These have never been run against a real QGIS
session in this project's development environment** — their exact parameter names are documented as
"best-effort until confirmed." Before adding sophistication, confirming the baseline actually works
is worth doing first — see §3.

Three other tools (`optimal_hub_siting`, `location_allocation`, `optimize_delivery_route`) are
explicit, by their own tool descriptions, about using **straight-line distance, not road-network
distance**. `optimize_delivery_route`'s multi-stop ordering (nearest-neighbor + 2-opt, a real,
correctly-implemented TSP heuristic) runs on that same straight-line distance matrix — there is
**no existing tool that combines multi-stop ordering with real road-network distance**; the tool's
own description says "combine with `travel_time_matrix`" but nothing actually does that combination
today.

**The concrete, code-confirmed gap behind your stated accuracy problems:** the params dict passed to
both `native:serviceareafrompoint` and `native:shortestpathpointtolayer`
(`logistics_tools.py` lines 399-407, 480-488) sets only `STRATEGY`, `DEFAULT_SPEED`, `TOLERANCE`,
`START_POINT`, and the endpoint parameter. Neither call sets `DIRECTION_FIELD` (one-way streets),
`SPEED_FIELD` (per-segment speed instead of one flat number), or any turn-penalty/entry-cost
parameter — all of which `native:shortestpathpointtolayer`/`serviceareafrompoint` support as
inputs. **A single flat `default_speed` (50 km/h) is applied to every road segment in the entire
network today**, regardless of surface, condition, or class. This is exactly the class of problem
described in your stated challenges (ignoring road quality, sending heavy vehicles down unsuitable
roads, not accounting for real conditions) — and it's fixable without a new algorithm, just by
wiring up parameters QGIS's own processing algorithm already accepts.

---

## 1. Data Enhancements

Ranked by how directly each closes the gap in §0, not just a generic wishlist:

1. **Per-segment speed/impedance field on the road network layer** (highest priority — this is the
   §0 gap). Populate a numeric field on `road_network_layer` (e.g. `speed_kmh` or `impedance_cost`)
   derived from:
   - OSM `highway` class (`fetch_osm_features`, already in this codebase) as a starting default
     speed table (motorway/trunk/primary/secondary/tertiary/track each get a different baseline).
   - OSM `surface` and `smoothness` tags — unpaved/gravel/dirt roads get a speed penalty; this is the
     single most direct way to address "sends heavy vehicles down unsuitable roads," since a
     sufficiently low effective speed makes the routing algorithm itself avoid that segment when a
     paved alternative exists.
   - A **damage/passability status field**, if available — post-disaster contexts often have this
     from OCHA/UNOSAT road-status assessments, IOM DTM, or field reports; a segment marked impassable
     should get an effectively infinite cost (or be excluded from the network layer entirely for that
     routing run), not just a slower speed.
2. **Direction/one-way field** (`DIRECTION_FIELD` in the same two processing algorithms, currently
   unused) — matters most in dense urban contexts, less in rural/post-disaster ones, but cheap to add
   once the OSM `oneway` tag is already being pulled in alongside `surface`/`highway`.
3. **A local elevation model (DEM)**, not a live weather/traffic API — matches this project's
   offline-first posture (`docs/PRODUCT_TIERS.md` §1, `docs/SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md`
   §B.4) and post-disaster reality (connectivity for a live traffic feed usually isn't available in
   exactly the scenario this tool needs to work in). Used to compute per-edge slope for a grade
   penalty — steep grade matters disproportionately for heavy cargo trucks, less for on-foot workers.
   SRTM/Copernicus DEM tiles are freely available and can be loaded like any other raster this plugin
   already handles.
4. **Vehicle profile parameters** (not a dataset, a config): max weight, width, and a
   paved-road-only flag per vehicle type (4x4 vs. heavy cargo truck vs. on-foot). None of the current
   tools take a vehicle profile at all — every route is computed as if any vehicle could use any road.
5. **Historical GPS tracking data** — covered in depth in §3, since its primary use here is
   calibration, not a routing input in itself.

**Explicitly not recommended for this context:** live traffic feeds and live weather APIs. Both
assume reliable connectivity, which is the opposite of the operating environment described — a
damage/passability field (updated periodically from field reports, not real-time) does the job that
matters here (routing around blocked/dangerous roads) without that dependency.

## 2. Algorithmic Adjustments

1. **Wire up `SPEED_FIELD` and `DIRECTION_FIELD`** in `calculate_service_area` and
   `travel_time_matrix` instead of the current flat `DEFAULT_SPEED`. This is the highest-value, lowest-
   risk change available — it's a parameter addition to an existing `processing.run()` call, not a new
   algorithm, and it directly targets the §0 gap. Recommend as a small, independent follow-up change
   to `logistics_tools.py`, not bundled with anything larger.
2. **Composite impedance, not raw distance/time.** QGIS's native network algorithms compute shortest
   path by distance or by time-from-speed — they don't have a built-in concept of "distance plus a
   damage penalty plus a slope penalty." The practical way to fold in surface/damage/slope penalties
   without reimplementing Dijkstra by hand: precompute a single blended `impedance_cost` field on the
   network layer (a preprocessing step over the road layer's attributes — surface penalty ×
   damage penalty × slope penalty × base travel time) and pass **that** field as the algorithm's cost
   basis, rather than trying to add new cost dimensions to the algorithm itself. This keeps using the
   already-integrated, real QGIS processing algorithm rather than replacing it.
3. **A real network-aware multi-stop tool is a genuine gap, not just a missing parameter.** Recommend
   a new composite tool (matching this codebase's established "thin composite over existing tools"
   pattern — the same shape as `population_access_gap`) that calls `travel_time_matrix` to build a
   real road-network distance matrix, then runs the existing `_optimize_route`
   (nearest-neighbor + 2-opt) over **that** matrix instead of straight-line distance. Small,
   independently useful, and doesn't touch the already-correct TSP heuristic itself.
4. **For real vehicle-capacity/time-window constraints (a true VRP, not just stop ordering)**: this is
   a materially bigger ask than the two items above, and worth naming honestly as such rather than
   folding it into a "small fix." The standard, well-supported approach is Google **OR-Tools**'
   routing solver (`ortools.constraint_solver`) — a real, widely-used VRP solver, not something to
   hand-roll. This would be a new optional-heavy-dependency tool following the same pattern
   `extract_features_from_imagery`/`ultralytics` already established (separate `requirements.txt`
   section, lazy import, clear degrade-if-missing error) — worth its own spec before building, the
   same discipline `SAM_IMAGERY_EXTRACTION_SPEC.md` and `PROMPT_REFINEMENT_LAYER_SPEC.md` already
   used, not scoped further here.
5. **Algorithm family stays the same on purpose.** Dijkstra (what QGIS's native algorithms already
   run) is the right choice here, not A* — A*'s advantage is a good heuristic to prune search toward a
   single known goal faster; `calculate_service_area` computes reachability in every direction (no
   single goal to heuristically aim at) and `travel_time_matrix` computes many-origins-to-many-
   destinations, where Dijkstra's shared-source computation is already efficient. Switching algorithm
   families would add complexity without addressing the actual accuracy gap, which is entirely about
   what the cost function is fed (§0), not which shortest-path algorithm computes it.

## 3. Validation Strategy (using historical GPS tracking data)

Two distinct uses for the historical GPS data — calibration input and accuracy proof — worth keeping
separate:

1. **Confirm the baseline actually runs first.** Per §0, `calculate_service_area`/`travel_time_matrix`
   have never been confirmed against a real QGIS session in this project. Before calibrating anything,
   run both against a real project with a real road network and confirm they return sane results —
   otherwise any "improvement" measured afterward is unfalsifiable.
2. **Derive real per-segment speeds from GPS traces (map-matching).** For each historical GPS trace,
   snap each point to its nearest road network segment, then compute observed average speed per
   segment from consecutive matched points' timestamps and positions. Aggregate across all available
   trips per segment (median, not mean, to reduce outlier sensitivity to a single unusually slow/fast
   trip). This produces the real `speed_kmh` field §1 recommends — calibrated from actual observed
   travel, not a guessed flat 50 km/h.
3. **Held-out accuracy test.** Split historical trips into a calibration set (used to derive
   per-segment speeds) and a held-out validation set (never used for calibration). For each held-out
   trip's real origin/destination, compute the routed travel time/distance with both the old flat-speed
   model and the new calibrated model, and compare each against that trip's actual recorded travel
   time. Report mean absolute error and % error for both — this is the concrete "prove accuracy
   improved" evidence, a specific before/after number, not a qualitative claim.
4. **Route-shape agreement, not just travel-time accuracy.** Two routes can have similar total time
   but take a completely different path — for humanitarian logistics (does the truck actually take a
   road it can physically traverse), compare the routed path's actual road segments against the GPS
   trace's actual matched segments (e.g., percentage of route length that overlaps with real recorded
   travel), not just the endpoint time/distance numbers.
5. **Recalibrate periodically, not once.** Post-disaster road conditions change (repairs, new damage,
   seasonal unpaved-road degradation) — treat the calibrated speed field as something to refresh from
   new GPS data periodically, not a one-time calculation. This is a process recommendation, not a code
   change.

## 4. Scripting/Automation

A standalone prototype script is provided at `docs/route_optimization_prototype.py`, using
`OSMnx`/`NetworkX`/`GeoPandas` as requested — a **different stack** from what Cartogen AI's shipped
tools use today (QGIS's own native processing algorithms, §0), worth being explicit about rather than
implying they're the same thing:

- **Why a different stack for this prototype:** OSMnx/NetworkX give direct, inspectable control over
  edge weights (custom Python functions, not a fixed processing-algorithm parameter set) — useful for
  prototyping exactly the kind of composite impedance §2 item 2 describes, and runnable standalone
  without a live QGIS session to test against (relevant since neither this session nor the plugin's
  own dev environment has one — see §0's own caveat).
- **What it demonstrates:** a route between two points that (1) penalizes unpaved/track-surface roads
  via OSM `surface` tags and (2) penalizes steep grade using a local DEM raster — the two example
  constraints requested, both grounded in §1's data recommendations, not arbitrary choices.
- **What it does NOT do:** call any live cloud elevation/traffic API (offline-first, matching §1's
  explicit recommendation against live feeds), or claim to be tested against a real, live-downloaded
  road network and a real DEM — no outbound access to the Overpass API or a real DEM source was
  available in this development environment.
- **What HAS actually been verified (2026-08-21):** with `osmnx`/`networkx`/`geopandas`/`rasterio`/
  `shapely`/`scikit-learn` actually installed, the script's cost function and routing logic were run
  against a small hand-built synthetic road graph and a synthetic GeoTIFF DEM (standing in for the
  live `ox.graph_from_bbox()` fetch). That run caught two real bugs, now fixed: (1) `graph_from_bbox`
  was called with the bbox tuple in the wrong element order for the installed osmnx version (2.0.7
  wants `(west, south, east, north)`, the script passed `(north, south, east, west)`) — exactly the
  risk the script's own comment had flagged without verifying; (2) `ox.distance.nearest_nodes()` on
  an unprojected lon/lat graph requires `scikit-learn`, which wasn't in the script's stated
  dependency list. Also confirmed: all 4 documented vehicle profiles construct without error, an
  unknown profile name raises `ValueError` rather than silently proceeding, a disconnected graph
  returns the documented `{"success": False, "error": ...}` shape rather than raising, and — the
  actual point of the two constraints — a synthetic route with a shorter unpaved+steep alternative
  correctly resolves to the longer paved route once the surface and slope penalties are applied
  (and still resolves correctly with only one of the two penalties active). Still NOT verified: real
  OSM data's actual tag coverage/noise, a real DEM's actual CRS and resolution, or performance on a
  large real graph. Treat this as a validated cost-function/routing-logic prototype that still needs
  a real network + real DEM run before field use — not proven end-to-end code, the same honesty this
  project's own specs (e.g. `SAM_IMAGERY_EXTRACTION_SPEC.md` §9) apply to anything not fully
  verifiable in a given environment.
- **Path to integration, if this proves out:** the composite-impedance logic here (a Python function
  computing a blended edge cost from surface + slope) is exactly the kind of preprocessing §2 item 2
  describes — the natural integration path is precomputing that same blended cost as a field on the
  QGIS `road_network_layer` and feeding it to the existing `native:shortestpathpointtolayer` call via
  `SPEED_FIELD`, not replacing QGIS's routing algorithms with OSMnx/NetworkX inside the plugin itself
  (which would mean maintaining two entirely separate network-analysis stacks for no real benefit).
