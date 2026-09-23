# -*- coding: utf-8 -*-
"""
Humanitarian Logistics Tools for Cartogen AI.
Hub siting, service-area, and travel-distance analysis for supply chain / last-
mile delivery planning (warehouse coverage, distribution routing). The
service-area and travel-matrix tools rely on QGIS's native Network Analysis
processing algorithms (native:serviceareafrompoint, native:shortestpathpointtolayer)
-- unlike the rest of this codebase's processing.run() calls (native:clip,
native:intersection, etc., which are exercised constantly and well-documented),
these are less commonly used. Confirmed live against real QGIS 4.2.2 as of
2026-09-05 (see point 8 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md):
SPEED_FIELD/DIRECTION_FIELD/STRATEGY all behave as documented, including a
real one-way-road test (a segment tagged forward-only correctly blocked the
reverse route) and a real differential-speed test (the same segment produced
different travel times with vs. without a speed_field). travel_time_matrix
worked cleanly on every network tried; calculate_service_area's
degenerate-small-network edge case (BUG-2026-09-05-2) was fixed 2026-09-10
(GeometrySkipInvalid context for serviceareafrompoint;
_degenerate_hull_fallback for the convexhull LineString/Polygon-sink case)
and live-verified against real QGIS 4.2.2 on 2026-09-11 (collinear
1-segment, L-shaped 2-segment, and a realistic 5-segment grid regression
guard all pass) -- status `fixed-verified` in docs/BUG_TRACKER.md.

population_access_gap chains calculate_service_area with
raster_tools.estimate_population_exposure (native:mergevectorlayers,
native:dissolve, native:intersection in between) and inherits the same
unverified-live caveat, plus its own: the intermediate merge/dissolve/
intersect steps have not been run against a real QGIS session either.
"""

import datetime
from .registry import register_tool
from .vector_tools import buffer_analysis
from .analysis_tools import _parse_date, _cap_entries
from ._qgis_enum_compat import resolve_qgis_enum
from ...logger import log_event

try:
    from qgis.core import (
        QgsProject, QgsWkbTypes, QgsSymbol, QgsSingleSymbolRenderer,
        QgsGeometry, QgsVectorLayer, QgsFeature, QgsProcessingContext,
        QgsField, QgsDistanceArea,
    )
    try:
        from qgis.core import Qgis
    except ImportError:
        Qgis = None
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtCore import QVariant
    import processing
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# PERF-002, 2026-09-14 audit: optimal_hub_siting/location_allocation compute a full
# candidate x demand QgsGeometry.distance() cross product in pure Python, with no upper
# bound on input size -- since every tool call in this codebase's dispatcher runs on the
# QGIS main GUI thread (BlockingQueuedConnection), an unbounded pair count would freeze the
# whole interface for however long that loop takes. A genuine algorithm change (e.g.
# migrating to native:distancematrix) was considered and deliberately not made here -- it
# would need live-QGIS verification that its distance semantics exactly match
# QgsGeometry.distance() (planar, not ellipsoidal) across every existing test's CRS
# assumptions, a real correctness-risk rewrite this audit's own conventions say not to make
# without that evidence. This is the safe, mechanical half instead: a hard cap on the
# candidate x demand pair count, matching the same "protective bound against an unbounded,
# unattended cost" pattern already established elsewhere in this codebase (scheduler.py's
# _MIN_INTERVAL_MINUTES/_MAX_CONCURRENT_SCHEDULES, from an earlier security review). The
# exact number is a conservative estimate (not a live-measured benchmark in this sandbox):
# at a rough ~1-10 microseconds per simple point-point GEOS distance() call, 2,000,000 pairs
# is on the order of a few seconds worst case, not the tens-of-seconds-plus that would
# actually be disruptive -- comfortably above any realistic humanitarian facility-siting
# dataset (this codebase's own docs describe "tens of candidates, low hundreds of demand
# points" as typical), so no legitimate real-world call is expected to be newly rejected.
_MAX_HUB_SITING_PAIRS = 2_000_000


def _check_hub_siting_pair_count(candidate_count, demand_count, tool_name):
    pairs = candidate_count * demand_count
    if pairs > _MAX_HUB_SITING_PAIRS:
        return (
            f"{tool_name}: {candidate_count:,} candidates x {demand_count:,} demand points = "
            f"{pairs:,} distance pairs, over this tool's {_MAX_HUB_SITING_PAIRS:,}-pair safety "
            "limit (this computation runs on the QGIS main thread and would freeze the "
            "interface for its duration). Reduce candidate_layer/demand_layer to a smaller "
            "area of interest, or pre-aggregate demand points (e.g. dissolve to admin-unit "
            "centroids) before calling this tool."
        )
    return None


def _make_distance_area(layer):
    """QGIS-006 follow-up (2026-09-19): returns a configured QgsDistanceArea for real-world
    (ellipsoidal/geodesic, WGS84) distance measurement when layer's CRS is geographic, or
    None when it's already projected -- QgsGeometry.distance() is already correct there (a
    projected CRS's own linear unit, typically meters), so ellipsoidal measurement would add
    cost without changing the answer. Returns None on any setup failure too (caller falls
    back to the previous planar-degrees behavior plus its existing warning in that case --
    see optimal_hub_siting/location_allocation)."""
    try:
        if not layer.crs().isGeographic():
            return None
        da = QgsDistanceArea()
        da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
        # Live-caught 2026-09-19 (python-qgis.bat, real QGIS 4.2.2): a fresh/default
        # QgsProject.instance().ellipsoid() returns the literal string 'NONE' -- QGIS's own
        # sentinel for "no ellipsoid configured, use planar Cartesian math" -- which is
        # truthy in Python, so `or "WGS84"` never caught it and setEllipsoid("NONE") was
        # silently disabling ellipsoidal mode entirely. Confirmed live: measureLine()
        # returned the same raw-degree value as the old planar distance() call (1.0, not
        # the correct ~71km at 50N) until this was fixed to explicitly check for 'NONE'.
        project_ellipsoid = QgsProject.instance().ellipsoid()
        da.setEllipsoid(project_ellipsoid if project_ellipsoid and project_ellipsoid != "NONE" else "WGS84")
        return da
    except Exception:
        return None


def _measure_distance(distance_area, geom_a, geom_b):
    """geom_a/geom_b are point geometries -- both callers (optimal_hub_siting,
    location_allocation) require point layers, per their own tool descriptions. Returns
    real-world meters via ellipsoidal QgsDistanceArea.measureLine() when distance_area is
    given (a geographic-CRS layer, see _make_distance_area), or the previous raw
    QgsGeometry.distance() (already meters on a projected CRS, or degrees as a last-resort
    fallback if ellipsoidal measurement itself failed) otherwise. Never raises -- a slightly
    wrong distance from a fallback is far better than a crashed hub-siting call."""
    if distance_area is not None:
        try:
            return distance_area.measureLine(geom_a.asPoint(), geom_b.asPoint())
        except Exception as e:
            log_event("swallowed_exception", tag="Tools", tool="logistics_ellipsoidal_distance",
                      error_class=type(e).__name__, error=True)
    return geom_a.distance(geom_b)


def _network_direction_speed_params(network, speed_field=None, direction_field=None,
                                     value_forward="yes", value_backward="-1", value_both="no"):
    """Wires speed_field/direction_field through to native:serviceareafrompoint/
    native:shortestpathpointtolayer's real SPEED_FIELD/DIRECTION_FIELD parameters
    -- point 8 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md, §2 item 1 of
    docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md ("the highest-value, lowest-risk change
    available... a parameter addition to an existing processing.run() call, not a new
    algorithm"). Both params previously went entirely unused -- every route was computed
    on a flat DEFAULT_SPEED with no way to make one-way streets one-way or give some
    segments a different speed than others. value_forward/value_backward/value_both
    default to OSM's own standard `oneway` tag values (a way digitized in the forward
    direction is "yes"=forward-only, "-1"=backward-only, "no"/absent=both directions),
    since fetch_osm_features (humanitarian_tools.py) is this codebase's primary road-
    network source -- overridable for a direction_field with different encoding.
    DEFAULT_DIRECTION is fixed at "Both directions" (index 2) so a feature with no
    matching direction_field value still routes rather than being silently excluded.
    Returns (extra_params, error) -- error is a caller-facing string when a given field
    name doesn't actually exist on the network layer, matching the same
    validate-before-processing.run() convention this session's other new tools use (e.g.
    export_layout_atlas's filename_field check)."""
    extra = {}
    if speed_field:
        if network.fields().indexOf(speed_field) == -1:
            return None, f"speed_field '{speed_field}' not found on the road network layer."
        extra["SPEED_FIELD"] = speed_field
    if direction_field:
        if network.fields().indexOf(direction_field) == -1:
            return None, f"direction_field '{direction_field}' not found on the road network layer."
        extra["DIRECTION_FIELD"] = direction_field
        extra["VALUE_FORWARD"] = value_forward
        extra["VALUE_BACKWARD"] = value_backward
        extra["VALUE_BOTH"] = value_both
        extra["DEFAULT_DIRECTION"] = 2
    return extra, None


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


def _style_risk_buffer_layer(layer):
    """Hardcoded, consistent 'risk corridor' look for score_route_incident_risk's
    buffer output -- same reasoning as humanitarian_tools._style_incident_layer:
    fixing this in plugin code guarantees every risk-scored route reads as risk
    (translucent orange, no border) regardless of what QGIS's default random
    single-symbol color would otherwise assign, and low enough opacity that the
    route line and basemap underneath stay visible rather than getting buried
    under a solid fill (same 75%-opacity-for-overlap reasoning styling_tools.py
    already applies elsewhere, tuned down further since this sits on top of a
    route line specifically)."""
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    symbol.setColor(QColor(255, 140, 0, 90))  # translucent orange, ~35% opacity
    for i in range(symbol.symbolLayerCount()):
        sym_layer = symbol.symbolLayer(i)
        if hasattr(sym_layer, "setStrokeStyle"):
            sym_layer.setStrokeStyle(0)  # Qt.PenStyle.NoPen -- no border ring
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()


def _rank_hub_candidates(candidate_distances, max_distance=None):
    """Pure Python, no QGIS needed -- candidate_distances is
    {candidate_name: [distance_to_each_demand_point, ...]}. Ranks candidates
    by average distance to all demand points (ascending = best coverage),
    optionally also reporting how many demand points fall within
    max_distance ("served")."""
    results = []
    for name, distances in candidate_distances.items():
        if not distances:
            continue
        avg_distance = sum(distances) / len(distances)
        entry = {
            "candidate": name,
            "avg_distance": round(avg_distance, 2),
            "max_distance_to_any_demand_point": round(max(distances), 2),
        }
        if max_distance is not None:
            served = sum(1 for d in distances if d <= max_distance)
            entry["demand_points_served"] = served
            entry["demand_points_served_percent"] = round(served / len(distances) * 100, 1)
        results.append(entry)
    results.sort(key=lambda r: r["avg_distance"])
    return results


@register_tool(
    "optimal_hub_siting",
    "Rank candidate hub/warehouse/facility locations by how well they serve a set of demand points "
    "(e.g. villages, distribution sites) -- for each candidate, computes the average straight-line "
    "distance to all demand points and (if max_distance is given) how many fall within it. Returns "
    "candidates ranked best (lowest average distance) first. Use this instead of eyeballing a map "
    "when choosing between several possible hub locations. Uses straight-line distance, not road "
    "network distance -- for network-based reachability use calculate_service_area instead.",
    {
        "type": "object",
        "properties": {
            "candidate_layer": {"type": "string", "description": "Point layer of possible hub/facility locations to evaluate."},
            "demand_layer": {"type": "string", "description": "Point layer of locations needing service (villages, distribution sites)."},
            "max_distance": {"type": "number", "description": "Distance (in the layers' CRS units, usually meters) within which a demand point counts as 'served'. Omit to rank on average distance alone."},
        },
        "required": ["candidate_layer", "demand_layer"],
    },
)
def optimal_hub_siting(candidate_layer, demand_layer, max_distance=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    candidates = _find_layer_by_name(candidate_layer)
    demand = _find_layer_by_name(demand_layer)
    if candidates is None:
        return {"error": f"Layer '{candidate_layer}' not found"}
    if demand is None:
        return {"error": f"Layer '{demand_layer}' not found"}

    try:
        demand_geoms = [f.geometry() for f in demand.getFeatures() if not f.geometry().isEmpty()]
        if not demand_geoms:
            return {"error": f"'{demand_layer}' has no usable point features."}

        pair_count_error = _check_hub_siting_pair_count(
            candidates.featureCount(), len(demand_geoms), "optimal_hub_siting"
        )
        if pair_count_error:
            return {"error": pair_count_error}

        distance_area = _make_distance_area(candidates)
        candidate_distances = {}
        for i, cand_feat in enumerate(candidates.getFeatures()):
            cand_geom = cand_feat.geometry()
            if cand_geom.isEmpty():
                continue
            name = cand_feat.attribute(0) if cand_feat.fields().count() else f"candidate_{i}"
            candidate_distances[str(name)] = [_measure_distance(distance_area, cand_geom, dg) for dg in demand_geoms]

        if not candidate_distances:
            return {"error": f"'{candidate_layer}' has no usable point features."}

        ranked = _rank_hub_candidates(candidate_distances, max_distance)
        result = {
            "success": True,
            "candidate_count": len(ranked),
            "demand_point_count": len(demand_geoms),
            "ranked_candidates": ranked,
        }
        # QGIS-006, 2026-09-13 audit (fixed 2026-09-19): same CRS-unit-mismatch class
        # buffer_analysis already warns about (Point 3 of
        # docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md) -- cand_geom.distance(dg)
        # used to be a raw, unconverted CRS-unit distance (degrees on a geographic CRS,
        # despite this tool's own docstring describing values as "usually meters"). Now
        # measured via _make_distance_area/_measure_distance instead: real-world ellipsoidal
        # meters on a geographic CRS, unchanged planar meters on an already-projected one.
        # The warning below only fires if ellipsoidal setup itself failed (distance_area is
        # None on a geographic CRS) -- an honest fallback statement, not a guessed
        # reprojection, for the one case this fix doesn't cover.
        try:
            if candidates.crs().isGeographic():
                if distance_area is not None:
                    result["note"] = (
                        f"'{candidate_layer}' is in a geographic CRS ({candidates.crs().authid()}) -- "
                        "distances above are real-world meters via ellipsoidal (WGS84 geodesic) "
                        "measurement, not raw planar degrees."
                    )
                else:
                    result["warning"] = (
                        f"'{candidate_layer}' is in a geographic CRS ({candidates.crs().authid()}), but "
                        "ellipsoidal distance measurement could not be set up, so every distance value "
                        "above is in DEGREES, not meters -- reproject to a projected/UTM CRS first for "
                        "meaningful distances."
                    )
        except Exception as e:
            log_event("swallowed_exception", tag="Tools", tool="logistics_crs_warning",
                      error_class=type(e).__name__, error=True)
        return result
    except Exception as e:
        return {"error": f"optimal_hub_siting failed: {e}"}


def _greedy_p_median(candidate_distances, demand_weights, num_facilities):
    """Pure Python, no QGIS needed -- candidate_distances is {candidate_name:
    [dist_to_demand_0, dist_to_demand_1, ...]}, demand_weights is a list of
    weights per demand point (all 1.0 if unweighted). Greedily selects
    num_facilities candidates that together minimize total weighted distance
    from each demand point to its NEAREST selected facility. This is the
    standard greedy approximation to the p-median problem (exact p-median is
    NP-hard for anything but a small candidate set) -- unlike
    optimal_hub_siting, which ranks each candidate independently, this
    accounts for overlap: two candidates that are both close to the same
    demand points don't both get "credit" for covering them."""
    candidates = list(candidate_distances.keys())
    n_demand = len(next(iter(candidate_distances.values())))
    selected = []
    remaining = set(candidates)
    current_min = [float("inf")] * n_demand

    for _ in range(min(num_facilities, len(candidates))):
        best_candidate = None
        best_total = None
        best_new_min = None
        for cand in remaining:
            distances = candidate_distances[cand]
            new_min = [min(current_min[j], distances[j]) for j in range(n_demand)]
            total = sum(new_min[j] * demand_weights[j] for j in range(n_demand))
            if best_total is None or total < best_total:
                best_total = total
                best_candidate = cand
                best_new_min = new_min
        selected.append(best_candidate)
        remaining.discard(best_candidate)
        current_min = best_new_min

    total_weighted_distance = sum(current_min[j] * demand_weights[j] for j in range(n_demand))
    avg_distance = sum(current_min) / n_demand if n_demand else 0
    return {
        "selected_facilities": selected,
        "total_weighted_distance": round(total_weighted_distance, 2),
        "avg_distance_per_demand_point": round(avg_distance, 2),
    }


@register_tool(
    "location_allocation",
    "Choose the best COMBINATION of num_facilities locations (out of a larger candidate list) to "
    "collectively minimize distance to all demand points -- e.g. 'which 3 of these 10 possible "
    "warehouse sites should we actually build, together, to best cover all these villages'. "
    "Different from optimal_hub_siting, which ranks candidates independently and doesn't account "
    "for overlap between them (two candidates both close to the same villages don't both get "
    "credit for covering them here). Uses a standard greedy approximation, not a guaranteed "
    "globally-optimal solution -- exact optimization is computationally infeasible beyond a "
    "handful of candidates anyway.",
    {
        "type": "object",
        "properties": {
            "candidate_layer": {"type": "string", "description": "Point layer of possible facility locations."},
            "demand_layer": {"type": "string", "description": "Point layer of locations needing service."},
            "num_facilities": {"type": "integer", "description": "How many facilities to select."},
            "weight_field": {"type": "string", "description": "Optional numeric field on demand_layer to weight points by (e.g. population). Defaults to equal weight."},
        },
        "required": ["candidate_layer", "demand_layer", "num_facilities"],
    },
)
def location_allocation(candidate_layer, demand_layer, num_facilities, weight_field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if num_facilities < 1:
        return {"error": "num_facilities must be at least 1."}

    candidates = _find_layer_by_name(candidate_layer)
    demand = _find_layer_by_name(demand_layer)
    if candidates is None:
        return {"error": f"Layer '{candidate_layer}' not found"}
    if demand is None:
        return {"error": f"Layer '{demand_layer}' not found"}
    if weight_field and weight_field not in [f.name() for f in demand.fields()]:
        return {"error": f"Field '{weight_field}' not found in '{demand_layer}'"}

    try:
        demand_feats = [f for f in demand.getFeatures() if not f.geometry().isEmpty()]
        if not demand_feats:
            return {"error": f"'{demand_layer}' has no usable point features."}
        demand_geoms = [f.geometry() for f in demand_feats]

        if weight_field:
            demand_weights = []
            for f in demand_feats:
                try:
                    demand_weights.append(float(f[weight_field]))
                except (TypeError, ValueError):
                    demand_weights.append(0.0)
        else:
            demand_weights = [1.0] * len(demand_feats)

        pair_count_error = _check_hub_siting_pair_count(
            candidates.featureCount(), len(demand_geoms), "location_allocation"
        )
        if pair_count_error:
            return {"error": pair_count_error}

        distance_area = _make_distance_area(candidates)
        candidate_distances = {}
        for i, cand_feat in enumerate(candidates.getFeatures()):
            cand_geom = cand_feat.geometry()
            if cand_geom.isEmpty():
                continue
            name = cand_feat.attribute(0) if cand_feat.fields().count() else f"candidate_{i}"
            candidate_distances[str(name)] = [_measure_distance(distance_area, cand_geom, dg) for dg in demand_geoms]

        if not candidate_distances:
            return {"error": f"'{candidate_layer}' has no usable point features."}
        if num_facilities > len(candidate_distances):
            return {"error": f"num_facilities ({num_facilities}) exceeds the number of usable candidates ({len(candidate_distances)})."}

        result = _greedy_p_median(candidate_distances, demand_weights, num_facilities)
        result["success"] = True
        result["candidate_count"] = len(candidate_distances)
        result["demand_point_count"] = len(demand_geoms)
        # Same fix as optimal_hub_siting -- see its own comment for the full history
        # (QGIS-006, 2026-09-13 audit; fixed 2026-09-19).
        try:
            if candidates.crs().isGeographic():
                if distance_area is not None:
                    result["note"] = (
                        f"'{candidate_layer}' is in a geographic CRS ({candidates.crs().authid()}) -- "
                        "distances are real-world meters via ellipsoidal (WGS84 geodesic) measurement, "
                        "not raw planar degrees."
                    )
                else:
                    result["warning"] = (
                        f"'{candidate_layer}' is in a geographic CRS ({candidates.crs().authid()}), but "
                        "ellipsoidal distance measurement could not be set up, so every distance value "
                        "is in DEGREES, not meters -- reproject to a projected/UTM CRS first for "
                        "meaningful distances."
                    )
        except Exception as e:
            log_event("swallowed_exception", tag="Tools", tool="logistics_crs_warning",
                      error_class=type(e).__name__, error=True)
        return result
    except Exception as e:
        return {"error": f"location_allocation failed: {e}"}


def _tour_length(tour, distance_matrix):
    """Pure Python -- total length of a tour (list of indices) over a
    symmetric distance_matrix."""
    return sum(distance_matrix[tour[i]][tour[i + 1]] for i in range(len(tour) - 1))


def _tsp_nearest_neighbor(distance_matrix, start_index=0):
    """Pure Python -- builds an initial tour via the nearest-neighbor
    heuristic: starting at start_index, repeatedly jump to the closest
    unvisited stop. A standard, simple TSP construction heuristic -- not
    optimal on its own, which is why _two_opt below refines it."""
    n = len(distance_matrix)
    visited = [False] * n
    tour = [start_index]
    visited[start_index] = True
    current = start_index
    for _ in range(n - 1):
        nearest = min(
            (j for j in range(n) if not visited[j]),
            key=lambda j: distance_matrix[current][j],
        )
        tour.append(nearest)
        visited[nearest] = True
        current = nearest
    return tour


def _two_opt(tour, distance_matrix, max_iterations=2000):
    """Pure Python -- classic 2-opt local search: repeatedly tries reversing a
    segment of the tour and keeps the reversal if it shortens the total
    route. Standard, well-understood TSP improvement heuristic -- not a
    guaranteed optimal solution, but reliably improves on the raw
    nearest-neighbor tour."""
    improved = True
    iterations = 0
    n = len(tour)
    while improved and iterations < max_iterations:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                if j - i == 1:
                    continue
                new_tour = tour[:i] + tour[i:j][::-1] + tour[j:]
                if _tour_length(new_tour, distance_matrix) < _tour_length(tour, distance_matrix):
                    tour = new_tour
                    improved = True
                iterations += 1
                if iterations >= max_iterations:
                    break
            if iterations >= max_iterations:
                break
    return tour


def _optimize_route(distance_matrix, start_index=0):
    """Pure Python -- nearest-neighbor construction followed by 2-opt
    refinement. Returns (tour, total_length)."""
    tour = _tsp_nearest_neighbor(distance_matrix, start_index)
    tour = _two_opt(tour, distance_matrix)
    return tour, _tour_length(tour, distance_matrix)


@register_tool(
    "optimize_delivery_route",
    "Find a good visiting order for a set of delivery/distribution stops -- e.g. 'what order "
    "should the truck visit these 8 distribution points'. Uses a standard nearest-neighbor + "
    "2-opt heuristic to pick the *order* (not a guaranteed globally-optimal order). Without "
    "road_network_layer, ordering uses straight-line distance and the result is a stop order "
    "only -- do NOT draw a straight line between the stops and present it as a route on an "
    "operational map; it is not a routable path. Pass road_network_layer to make the ordering "
    "itself road-network-aware (real road distance between every pair of stops, not straight-line) "
    "and to build an actual road-snapped route line, added to the project and safe to render as a "
    "real route. speed_field/direction_field (same meaning as calculate_service_area's) only "
    "affect ordering when road_network_layer is given. Not a substitute for a full commercial VRP "
    "solver with vehicle capacity/time-window constraints.",
    {
        "type": "object",
        "properties": {
            "stops_layer": {"type": "string", "description": "Point layer of stops to visit."},
            "start_stop_name": {"type": "string", "description": "Optional name (from the layer's first attribute field) of the stop to start from. Defaults to the first feature."},
            "road_network_layer": {"type": "string", "description": "Optional line layer representing the road/path network. When given, visiting order uses real road-network distance (not straight-line) and a road-snapped route line is built and added to the project -- required before the output may be rendered as a route on a map."},
            "speed_field": {"type": "string", "description": "Optional numeric field on road_network_layer giving per-segment speed in km/h. Only affects ordering when road_network_layer is given."},
            "direction_field": {"type": "string", "description": "Optional field on road_network_layer marking one-way segments (e.g. OSM's 'oneway' tag). Only affects ordering when road_network_layer is given."},
            "value_forward": {"type": "string", "description": "direction_field value meaning forward-only travel. Defaults to 'yes' (OSM convention)."},
            "value_backward": {"type": "string", "description": "direction_field value meaning backward-only travel. Defaults to '-1' (OSM convention)."},
            "value_both": {"type": "string", "description": "direction_field value meaning both directions. Defaults to 'no' (OSM convention)."},
        },
        "required": ["stops_layer"],
    },
)
def optimize_delivery_route(stops_layer, start_stop_name=None, road_network_layer=None,
                             speed_field=None, direction_field=None,
                             value_forward="yes", value_backward="-1", value_both="no"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(stops_layer)
    if layer is None:
        return {"error": f"Layer '{stops_layer}' not found"}

    network = None
    extra_params = {}
    if road_network_layer is not None:
        network = _find_layer_by_name(road_network_layer)
        if network is None:
            return {"error": f"Layer '{road_network_layer}' not found"}
        extra_params, field_error = _network_direction_speed_params(
            network, speed_field, direction_field, value_forward, value_backward, value_both
        )
        if field_error:
            return {"error": field_error}

    try:
        feats = [f for f in layer.getFeatures() if not f.geometry().isEmpty()]
        if len(feats) < 2:
            return {"error": f"'{stops_layer}' needs at least 2 usable point features."}

        has_name_field = feats[0].fields().count() > 0
        names = [str(f.attribute(0)) if has_name_field else f"stop_{i}" for i, f in enumerate(feats)]
        geoms = [f.geometry() for f in feats]

        start_index = 0
        if start_stop_name is not None:
            if start_stop_name not in names:
                return {"error": f"start_stop_name '{start_stop_name}' not found among stops: {names}"}
            start_index = names.index(start_stop_name)

        n = len(geoms)
        network_aware = network is not None
        if network_aware:
            distance_matrix = _build_network_distance_matrix(network, geoms, extra_params)
        else:
            distance_area = _make_distance_area(layer)
            distance_matrix = [
                [_measure_distance(distance_area, geoms[i], geoms[j]) for j in range(n)]
                for i in range(n)
            ]

        tour, total_distance = _optimize_route(distance_matrix, start_index)
        ordered_names = [names[i] for i in tour]

        result = {
            "success": True,
            "stops_layer": stops_layer,
            "stop_count": n,
            "route_order": ordered_names,
            "total_distance": round(total_distance, 2),
            "network_aware_ordering": network_aware,
        }

        if network is None:
            warning = (
                "No road_network_layer given -- total_distance is straight-line and route_order "
                "is a stop sequence only, not a routable path. Do not render a line through these "
                "stops as a delivery route; pass road_network_layer to build one."
            )
            # QGIS-006, 2026-09-13 audit (fixed 2026-09-19): the straight-line distance_matrix
            # above now goes through _make_distance_area/_measure_distance -- real-world
            # ellipsoidal meters on a geographic CRS, unchanged planar meters on a projected
            # one. Warning only fires if ellipsoidal setup itself failed.
            try:
                if layer.crs().isGeographic():
                    if distance_area is not None:
                        warning += (
                            f" '{stops_layer}' is in a geographic CRS ({layer.crs().authid()}) -- "
                            "total_distance is real-world meters via ellipsoidal (WGS84 geodesic) "
                            "measurement, not raw planar degrees."
                        )
                    else:
                        warning += (
                            f" '{stops_layer}' is also in a geographic CRS ({layer.crs().authid()}), "
                            "but ellipsoidal distance measurement could not be set up, so "
                            "total_distance is in DEGREES, not any real distance unit -- reproject "
                            "to a projected/UTM CRS first for a meaningful figure."
                        )
            except Exception as e:
                log_event("swallowed_exception", tag="Tools", tool="logistics_route_crs_warning",
                          error_class=type(e).__name__, error=True)
            result["warning"] = warning
            return result

        route_layer_name = _build_road_snapped_route(stops_layer, network, geoms, tour)
        if route_layer_name is None:
            result["warning"] = (
                "Could not build a road-snapped route (stops may be too far from the network) -- "
                "falling back to stop order only. Do not render a line through these stops as a "
                "delivery route."
            )
        else:
            result["route_layer"] = route_layer_name
            result["road_snapped"] = True

        return result
    except Exception as e:
        return {"error": f"optimize_delivery_route failed: {e}"}


def _build_network_distance_matrix(network, geoms, extra_params=None):
    """Real road-network point-to-point distance between every ordered pair
    of stops, via native:shortestpathpointtopoint's own 'cost' output
    field -- confirmed live this is the robust way to get this, not
    travel_time_matrix: calling that tool with the stops layer as both
    origins and destinations DOES work (same layer object twice is fine),
    but its destination-side matrix keys come from an internal
    coordinate-string field on shortestpathpointtolayer's output, not any
    of the stop layer's own attributes -- confirmed live they don't match
    the origin-side keys' naming at all, so there's no reliable way to map
    a destination key back to a specific stop by name. Point-to-point's
    'cost' field has no such ambiguity: each call names its one exact
    start/end pair, so indices line up by construction.

    O(n^2) processing.run() calls for n stops -- optimize_delivery_route's
    own tool description already frames this as suited to a route-sized
    stop list ("not a substitute for a full commercial VRP solver"), not
    hundreds of stops, so this is an acceptable cost for the gap it closes
    (real road distance driving the visiting ORDER, not just the final
    drawn line).

    Unreachable/failed pairs get float('inf') so _optimize_route naturally
    routes around them (nearest-neighbor never picks an infinite-cost hop
    while a finite one is available) instead of crashing on a missing
    matrix entry."""
    n = len(geoms)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            start = geoms[i].asPoint()
            end = geoms[j].asPoint()
            params = {
                "INPUT": network,
                "STRATEGY": 0,
                "DEFAULT_SPEED": 50,
                "TOLERANCE": 0,
                "START_POINT": f"{start.x()},{start.y()}",
                "END_POINT": f"{end.x()},{end.y()}",
                "OUTPUT": "memory:",
            }
            if extra_params:
                params.update(extra_params)
            try:
                output = processing.run("native:shortestpathpointtopoint", params)
                result_layer = output.get("OUTPUT")
                feats = list(result_layer.getFeatures()) if result_layer is not None else []
                cost = feats[0]["cost"] if feats else None
                matrix[i][j] = float(cost) if cost is not None else float("inf")
            except Exception:
                matrix[i][j] = float("inf")
    return matrix


def _build_road_snapped_route(stops_layer_name, network, geoms, tour):
    """Chain native:shortestpathpointtopoint across each consecutive pair in
    visiting order and merge the segments into one line layer added to the
    project, so optimize_delivery_route's output is an actual road-snapped
    route rather than a straight line between stops (closes the gap flagged
    in docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md Section IV -- see
    docs/BUG_TRACKER.md). Same unverified-live caveat as this module's other
    native-network-analysis calls (see module docstring). Returns the new
    layer's name, or None if no segment could be built."""
    segment_layers = []
    for i in range(len(tour) - 1):
        start = geoms[tour[i]].asPoint()
        end = geoms[tour[i + 1]].asPoint()
        params = {
            "INPUT": network,
            "STRATEGY": 0,
            "DEFAULT_SPEED": 50,
            "TOLERANCE": 0,
            "START_POINT": f"{start.x()},{start.y()}",
            "END_POINT": f"{end.x()},{end.y()}",
            "OUTPUT": "memory:",
        }
        try:
            output = processing.run("native:shortestpathpointtopoint", params)
        except Exception:
            continue
        segment = output.get("OUTPUT")
        if segment is not None and segment.featureCount() > 0:
            segment_layers.append(segment)

    if not segment_layers:
        return None

    route_name = f"{stops_layer_name}_road_route"
    if len(segment_layers) == 1:
        route_layer = segment_layers[0]
    else:
        merged = processing.run(
            "native:mergevectorlayers", {"LAYERS": segment_layers, "OUTPUT": "memory:"}
        )
        route_layer = merged.get("OUTPUT")
        if route_layer is None:
            return None

    route_layer.setName(route_name)
    QgsProject.instance().addMapLayer(route_layer)
    return route_name


def _geom_usable(geom):
    """True if geom is a real, non-empty QgsGeometry -- shared by every
    None/isEmpty check in _degenerate_hull_fallback below."""
    return geom is not None and not geom.isEmpty()


def _degenerate_hull_fallback(lines_layer, travel_cost):
    """BUG-2026-09-05-2 root cause (isolated 2026-09-10, reasoned from QGIS's own
    documented Processing/GEOS behaviour -- no live QGIS available in this session
    to additionally confirm live): native:convexhull's OUTPUT sink is declared as a
    fixed Polygon geometry type regardless of what the input actually produces. The
    convex hull of a set of collinear points (a straight 1-segment road, or a
    reachable-network that happens to reduce to one straight line) is geometrically
    a line, not an area -- QgsGeometry.convexHull() correctly returns that as a
    LineString (or a Point, for a single coincident point), and the algorithm's own
    Polygon-typed sink then refuses to write it, which is exactly the recorded
    "Could not add feature with geometry type LineString to layer of type Polygon"
    error. native:convexhull has no parameter to accept a non-Polygon result, so
    this is not fixable by changing our call's parameters -- it has to be computed
    ourselves instead of delegating to that algorithm.

    Recomputes the hull directly via QgsGeometry.unaryUnion()/.convexHull() on the
    same input features. If that result is already a polygon (should not normally
    happen here, since native:convexhull would have succeeded in that case, but
    handled defensively), it is used as-is. If it is degenerate (a line or a
    point), it is buffered by a small fraction of the travel cost so the caller
    gets a thin but valid, well-formed polygon representing that degenerate
    service area instead of no hull at all. Returns None (never raises) if the
    input has no usable geometry or the hull computation itself fails -- callers
    should treat that exactly as the pre-fix behaviour: an unrecoverable skip for
    the convexhull stage.
    """
    try:
        geoms = [g for g in (f.geometry() for f in lines_layer.getFeatures()) if _geom_usable(g)]
        if not geoms:
            return None
        combined = QgsGeometry.unaryUnion(geoms)
        if not _geom_usable(combined):
            return None
        hull = combined.convexHull()
        if not _geom_usable(hull):
            return None
        if hull.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
            # Degenerate hull (collinear points): buffer it into a thin polygon
            # rather than fabricating an arbitrary area shape. The buffer distance
            # is a small fraction of travel_cost so it stays visually negligible
            # relative to the service area's own scale, in the same CRS units as
            # the network layer.
            hull = hull.buffer(max(travel_cost * 0.001, 0.01), 8)
            if not _geom_usable(hull) or hull.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
                return None
        layer = QgsVectorLayer(f"Polygon?crs={lines_layer.crs().authid()}", "service_area_hull", "memory")
        provider = layer.dataProvider()
        feat = QgsFeature()
        feat.setGeometry(hull)
        provider.addFeatures([feat])
        layer.updateExtents()
        return layer
    except Exception:
        return None


@register_tool(
    "calculate_service_area",
    "Calculate the reachable road-network area around one or more facilities (warehouse, clinic, "
    "distribution point) within a given travel distance or time -- e.g. 'what area can this "
    "warehouse serve within 30km by road'. Produces, per facility, both the reachable road network "
    "and an approximate coverage polygon (convex hull around it). Requires a real line layer "
    "representing the road network -- for simple straight-line/as-the-crow-flies coverage, use "
    "buffer_analysis instead. Without speed_field, every road segment is treated as one flat "
    "default_speed regardless of surface or condition, which overstates reachability on unpaved/"
    "damaged roads -- when the network layer has a per-segment speed or condition field (e.g. from "
    "OSM highway/surface tags), pass it as speed_field with strategy='fastest' for a more realistic "
    "area. direction_field makes one-way roads one-way instead of assuming every segment is "
    "traversable both directions. Pass travel_cost as a LIST (e.g. [15, 30, 60]) instead of a "
    "single number for a real isochrone/access-band map: builds one combined polygon layer per "
    "facility with a travel_cost_band field, one ring per value, auto-styled with a graduated "
    "renderer -- a single call instead of one per band plus manual styling.",
    {
        "type": "object",
        "properties": {
            "facility_layer": {"type": "string", "description": "Point layer with the facility/facilities to calculate service areas for."},
            "road_network_layer": {"type": "string", "description": "Line layer representing the road/path network."},
            "travel_cost": {
                "description": "Maximum travel distance (network CRS units, usually meters) or time in hours "
                "if strategy='fastest'. Pass a single number for one service area, or a list of ascending "
                "values (e.g. [15, 30, 60]) for a multi-band isochrone/access map -- one combined, "
                "auto-styled polygon layer per facility instead of separate calls.",
                "anyOf": [
                    {"type": "number"},
                    {"type": "array", "items": {"type": "number"}},
                ],
            },
            "strategy": {"type": "string", "description": "'shortest' (distance-based, default) or 'fastest' (time-based)."},
            "default_speed": {"type": "number", "description": "Default travel speed in km/h for any segment with no speed_field value, used only when strategy='fastest'. Defaults to 50."},
            "speed_field": {"type": "string", "description": "Optional numeric field on road_network_layer giving per-segment speed in km/h (e.g. derived from OSM highway/surface tags). Only affects routing when strategy='fastest'."},
            "direction_field": {"type": "string", "description": "Optional field on road_network_layer marking one-way segments (e.g. OSM's 'oneway' tag). Segments with no matching value still route both ways."},
            "value_forward": {"type": "string", "description": "direction_field value meaning forward-only travel. Defaults to 'yes' (OSM convention)."},
            "value_backward": {"type": "string", "description": "direction_field value meaning backward-only travel. Defaults to '-1' (OSM convention)."},
            "value_both": {"type": "string", "description": "direction_field value meaning both directions. Defaults to 'no' (OSM convention)."},
        },
        "required": ["facility_layer", "road_network_layer", "travel_cost"],
    },
)
def calculate_service_area(facility_layer, road_network_layer, travel_cost, strategy="shortest", default_speed=50,
                            speed_field=None, direction_field=None,
                            value_forward="yes", value_backward="-1", value_both="no"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    # v1.8.0 workstream 4: travel_cost as a list builds a real isochrone/
    # access-band map (one combined, auto-styled polygon layer per facility)
    # instead of requiring N separate calls plus manual styling. The
    # single-value path below is otherwise completely unchanged from its
    # already-live-verified behavior -- multi_band only ever adds new
    # branches, it never alters what a scalar travel_cost does.
    is_multi_band = isinstance(travel_cost, (list, tuple))
    if is_multi_band:
        if not travel_cost:
            return {"error": "travel_cost list must contain at least one value."}
        travel_costs = sorted(float(v) for v in travel_cost)
        if travel_costs[0] <= 0:
            return {"error": "travel_cost must be positive."}
    else:
        if travel_cost <= 0:
            return {"error": "travel_cost must be positive."}
        travel_costs = [travel_cost]
    strategy = (strategy or "shortest").lower()
    if strategy not in ("shortest", "fastest"):
        return {"error": "strategy must be 'shortest' or 'fastest'."}

    network = _find_layer_by_name(road_network_layer)
    facilities = _find_layer_by_name(facility_layer)
    if network is None:
        return {"error": f"Layer '{road_network_layer}' not found"}
    if facilities is None:
        return {"error": f"Layer '{facility_layer}' not found"}

    extra_params, field_error = _network_direction_speed_params(
        network, speed_field, direction_field, value_forward, value_backward, value_both
    )
    if field_error:
        return {"error": field_error}

    try:
        strategy_val = 1 if strategy == "fastest" else 0
        layers_created = []
        served_count = 0
        skipped = []
        # BUG-2026-09-05-2 fix (2026-09-08): both processing.run() calls below used to
        # sit inside one try/except that spans the whole facility loop, so a single
        # facility hitting the known small/degenerate-network edge case (a collinear
        # 1-segment network's convex hull degenerating to a LineString that a Polygon-
        # typed sink then refuses, or a 2-segment L-shaped network making
        # native:serviceareafrompoint itself raise on invalid intermediate geometry)
        # aborted the ENTIRE multi-facility request, discarding results already computed
        # for every other facility. Each stage is now isolated per facility: a failure is
        # recorded and that facility is skipped (or, if only the hull step fails, its
        # already-built reachable-network lines are still kept), so the rest of the batch
        # still comes back.
        #
        # BUG-2026-09-05-2 further fix (2026-09-10): the two failure shapes themselves
        # are now addressed, not just isolated. (1) serviceareafrompoint's own
        # "invalid geometry" abort: pass a QgsProcessingContext with
        # GeometrySkipInvalid so the algorithm skips an invalid input feature
        # internally, exactly the remedy its own error message names ("change the
        # 'Invalid features filtering' option") -- reasoned from QGIS's documented
        # Processing API, not independently re-run against live QGIS this session
        # (no live/headless QGIS available in this environment -- see docs/BUG_TRACKER.md).
        # Built once here (same setting for every facility in the batch, not per-facility
        # state) rather than reconstructed inside the loop below. The real enum lives on
        # Qgis.InvalidGeometryCheck (QgsProcessingContext.setInvalidGeometryCheck's own
        # signature is `check: Qgis.InvalidGeometryCheck`, confirmed live against QGIS
        # 4.2.2 -- not QgsProcessing, which has no such nested enum at all on that
        # install) -- resolved via resolve_qgis_enum rather than hard-coded, matching
        # this file's own QgsWkbTypes.GeometryType.* precedent for enums that moved
        # between QGIS majors.
        # (2) the convexhull LineString/Polygon-sink failure: see
        # _degenerate_hull_fallback's own docstring for the isolated root cause and fix,
        # which *is* provable without live QGIS since it follows from convex-hull
        # geometry (collinear points) rather than from QGIS-specific runtime behaviour.
        # QGIS-005, 2026-09-14 audit: was passed straight to setInvalidGeometryCheck() with no
        # explicit None check -- only "safe" by whatever this function's own outer exception
        # handling happens to do with the resulting error, not by design (QGIS-004's identical
        # class of gap). Today inert (this enum resolves fine on both QGIS 3.x/4.x).
        _invalid_geom_check = resolve_qgis_enum(Qgis, "InvalidGeometryCheck", "GeometrySkipInvalid")
        if _invalid_geom_check is None:
            return {"error": "Could not resolve QgsProcessing's InvalidGeometryCheck enum in this QGIS version."}
        context = QgsProcessingContext()
        context.setInvalidGeometryCheck(_invalid_geom_check)
        for i, feat in enumerate(facilities.getFeatures()):
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            point = geom.asPoint()

            band_hulls = []  # (band_value, hull_layer) -- only populated/used when is_multi_band
            facility_served = False
            for band in travel_costs:
                params = {
                    "INPUT": network,
                    "STRATEGY": strategy_val,
                    "DEFAULT_SPEED": default_speed,
                    "TOLERANCE": 0,
                    "START_POINT": f"{point.x()},{point.y()}",
                    "TRAVEL_COST2": band,
                    "OUTPUT_LINES": "memory:",
                }
                params.update(extra_params)
                try:
                    output = processing.run("native:serviceareafrompoint", params, context=context)
                except Exception as e:
                    skipped.append({"facility_index": i, "travel_cost": band, "stage": "serviceareafrompoint", "reason": str(e)})
                    continue
                lines_layer = output.get("OUTPUT_LINES")
                if lines_layer is None or lines_layer.featureCount() == 0:
                    continue

                lines_name = (
                    f"{facility_layer}_service_area_lines_{i}" if not is_multi_band
                    else f"{facility_layer}_service_area_lines_{i}_band_{band:g}"
                )
                lines_layer.setName(lines_name)
                QgsProject.instance().addMapLayer(lines_layer)
                layers_created.append(lines_name)
                # Matches the original single-band semantics exactly: a
                # facility/band counts as "served" once its lines layer is
                # built, regardless of whether hull-building below succeeds
                # -- the hull is a bonus output, not the served/skipped
                # criterion.
                facility_served = True

                hull_layer = None
                try:
                    hull = processing.run("native:convexhull", {"INPUT": lines_layer, "OUTPUT": "memory:"})
                    hull_layer = hull.get("OUTPUT")
                except Exception as e:
                    # Match native:convexhull's Polygon-typed-sink rejection on its own
                    # constant wording ("...to layer of type Polygon") rather than the
                    # source geometry type name -- live-confirmed against real QGIS 4.2.2
                    # that this rejection's source-type name varies by exactly how the
                    # reachable network degenerates (LineString for a collinear road,
                    # GeometryCollection for other degenerate shapes; _degenerate_hull_fallback's
                    # own docstring further documents a single-Point case) -- an earlier
                    # version of this guard matched only "LineString"/"Point" and missed the
                    # GeometryCollection variant found live.
                    if "to layer of type Polygon" in str(e):
                        hull_layer = _degenerate_hull_fallback(lines_layer, band)
                    if hull_layer is None:
                        skipped.append({"facility_index": i, "travel_cost": band, "stage": "convexhull", "reason": str(e)})

                if hull_layer is not None:
                    if is_multi_band:
                        band_hulls.append((band, hull_layer))
                    else:
                        hull_name = f"{facility_layer}_service_area_{i}"
                        hull_layer.setName(hull_name)
                        QgsProject.instance().addMapLayer(hull_layer)
                        layers_created.append(hull_name)

            if is_multi_band and band_hulls:
                merged_name = f"{facility_layer}_service_area_bands_{i}"
                merged_layer = _merge_band_hulls(band_hulls, merged_name)
                if merged_layer is not None:
                    QgsProject.instance().addMapLayer(merged_layer)
                    layers_created.append(merged_name)
                    from .styling_tools import apply_graduated_style
                    apply_graduated_style(merged_name, "travel_cost_band")

            if facility_served:
                served_count += 1

        if served_count == 0:
            return {"error": "Could not build a service area for any facility -- check the facility points are near the road network."}

        result = {
            "success": True,
            "facility_count": served_count,
            "travel_cost": travel_costs if is_multi_band else travel_costs[0],
            "strategy": strategy,
            "layers_created": layers_created,
        }
        if speed_field:
            result["speed_field"] = speed_field
        if direction_field:
            result["direction_field"] = direction_field
        if skipped:
            result["warnings"] = (
                f"{len(skipped)} facility/band combination(s) could not be fully processed -- see "
                "'skipped' for detail. Known limitation on very small/degenerate road networks "
                "(BUG-2026-09-05-2); real road datasets are very unlikely to hit this."
            )
            result["skipped"] = skipped
        return result
    except Exception as e:
        return {"error": f"calculate_service_area failed: {e}"}


def _merge_band_hulls(band_hulls, output_name):
    """Combines one facility's per-band hull polygon layers into ONE memory
    layer with a travel_cost_band field -- a legible single isochrone/
    access-band layer instead of N separately-named, separately-styled
    layers. Not a processing.run() merge (native:mergevectorlayers): these
    hull layers start with no fields at all, so building the combined layer
    directly, feature by feature, is simpler than reconciling schemas
    through an extra Processing call for what's a small number of features
    (one per band, typically 2-5). Returns None if no band produced any
    usable hull geometry (caller then adds nothing to the project for this
    facility, matching the existing single-band "hull_layer is None" case)."""
    if not band_hulls:
        return None
    crs = band_hulls[0][1].crs()
    merged = QgsVectorLayer(f"Polygon?crs={crs.authid()}", output_name, "memory")
    merged.dataProvider().addAttributes([QgsField("travel_cost_band", QVariant.Double)])
    merged.updateFields()
    feats = []
    for band, hull_layer in band_hulls:
        for hull_feat in hull_layer.getFeatures():
            geom = hull_feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            new_feat = QgsFeature(merged.fields())
            new_feat.setGeometry(geom)
            new_feat.setAttribute("travel_cost_band", band)
            feats.append(new_feat)
    if not feats:
        return None
    merged.dataProvider().addFeatures(feats)
    merged.updateExtents()
    return merged


@register_tool(
    "travel_time_matrix",
    "Calculate road-network distance or travel time from each origin point to each destination "
    "point -- e.g. delivery distance from each warehouse to each distribution site. Returns a "
    "matrix of costs (network CRS units for strategy='shortest', hours for strategy='fastest') "
    "keyed by origin then destination. Requires a line layer representing the road network, not "
    "straight-line distance. Without speed_field, every segment is treated as one flat "
    "default_speed regardless of surface or condition -- when the network layer has a per-segment "
    "speed or condition field, pass it as speed_field with strategy='fastest' for a more realistic "
    "matrix. direction_field makes one-way roads one-way instead of assuming every segment is "
    "traversable both directions.",
    {
        "type": "object",
        "properties": {
            "origins_layer": {"type": "string", "description": "Point layer of origin locations (e.g. warehouses)."},
            "destinations_layer": {"type": "string", "description": "Point layer of destination locations (e.g. distribution sites)."},
            "road_network_layer": {"type": "string", "description": "Line layer representing the road/path network."},
            "strategy": {"type": "string", "description": "'shortest' (distance-based, default) or 'fastest' (time-based)."},
            "default_speed": {"type": "number", "description": "Default travel speed in km/h for any segment with no speed_field value, used only when strategy='fastest'. Defaults to 50."},
            "speed_field": {"type": "string", "description": "Optional numeric field on road_network_layer giving per-segment speed in km/h. Only affects the matrix when strategy='fastest'."},
            "direction_field": {"type": "string", "description": "Optional field on road_network_layer marking one-way segments (e.g. OSM's 'oneway' tag). Segments with no matching value still route both ways."},
            "value_forward": {"type": "string", "description": "direction_field value meaning forward-only travel. Defaults to 'yes' (OSM convention)."},
            "value_backward": {"type": "string", "description": "direction_field value meaning backward-only travel. Defaults to '-1' (OSM convention)."},
            "value_both": {"type": "string", "description": "direction_field value meaning both directions. Defaults to 'no' (OSM convention)."},
        },
        "required": ["origins_layer", "destinations_layer", "road_network_layer"],
    },
)
def travel_time_matrix(origins_layer, destinations_layer, road_network_layer, strategy="shortest", default_speed=50,
                        speed_field=None, direction_field=None,
                        value_forward="yes", value_backward="-1", value_both="no"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    strategy = (strategy or "shortest").lower()
    if strategy not in ("shortest", "fastest"):
        return {"error": "strategy must be 'shortest' or 'fastest'."}
    origins = _find_layer_by_name(origins_layer)
    destinations = _find_layer_by_name(destinations_layer)
    network = _find_layer_by_name(road_network_layer)
    if origins is None:
        return {"error": f"Layer '{origins_layer}' not found"}
    if destinations is None:
        return {"error": f"Layer '{destinations_layer}' not found"}
    if network is None:
        return {"error": f"Layer '{road_network_layer}' not found"}

    extra_params, field_error = _network_direction_speed_params(
        network, speed_field, direction_field, value_forward, value_backward, value_both
    )
    if field_error:
        return {"error": field_error}

    try:
        origin_features = [f for f in origins.getFeatures() if not f.geometry().isEmpty()]
        if not origin_features:
            return {"error": f"'{origins_layer}' has no usable point features."}

        strategy_val = 1 if strategy == "fastest" else 0
        matrix = {}
        for i, origin_feat in enumerate(origin_features):
            origin_id = origin_feat.attribute(0) if origin_feat.fields().count() else f"origin_{i}"
            point = origin_feat.geometry().asPoint()
            params = {
                "INPUT": network,
                "STRATEGY": strategy_val,
                "DEFAULT_SPEED": default_speed,
                "TOLERANCE": 0,
                "START_POINT": f"{point.x()},{point.y()}",
                "END_POINTS": destinations,
                "OUTPUT": "memory:",
            }
            params.update(extra_params)
            output = processing.run("native:shortestpathpointtolayer", params)
            result_layer = output.get("OUTPUT")
            if result_layer is None:
                continue

            fields = [f.name() for f in result_layer.fields()]
            cost_field = next((f for f in fields if "cost" in f.lower()), None)
            dest_field = next((f for f in fields if "end" in f.lower() or "destination" in f.lower()), None)

            distances = {}
            for feat in result_layer.getFeatures():
                dest_key = feat.attribute(dest_field) if dest_field else feat.id()
                cost = feat.attribute(cost_field) if cost_field else None
                distances[str(dest_key)] = cost
            matrix[str(origin_id)] = distances

        if not matrix:
            return {"error": "Could not compute any routes -- check the origin/destination points are near the road network."}
        result = {
            "success": True,
            "origins_layer": origins_layer,
            "destinations_layer": destinations_layer,
            "strategy": strategy,
            "matrix": matrix,
        }
        if speed_field:
            result["speed_field"] = speed_field
        if direction_field:
            result["direction_field"] = direction_field
        return result
    except Exception as e:
        return {"error": f"travel_time_matrix failed: {e}"}


@register_tool(
    "population_access_gap",
    "Compute how many people, and what percentage of a population base, are BEYOND a given travel "
    "distance/time from the nearest facility -- e.g. 'X people / Y% of the population are more than "
    "30 minutes from a functioning health facility', the standard access-to-services statistic in "
    "humanitarian gap analysis and cluster reporting. A thin composite over calculate_service_area "
    "(network-based reach per facility) and estimate_population_exposure (population sum within a "
    "polygon) rather than reimplementing either -- area_layer defines the population base to check "
    "coverage for (e.g. an admin-boundary or catchment polygon) and must already have a population "
    "raster available (see fetch_worldpop_population). As a side effect of calling "
    "calculate_service_area internally, per-facility service-area polygons are also added to the "
    "project, plus the combined reachable-area layer this tool builds from them. Returns a MODELED "
    "estimate -- network-based reachability against a gridded population raster, not a verified count "
    "of people confirmed to lack access -- report it as 'an estimated N people/percent are beyond X', "
    "not as a confirmed access-gap figure.",
    {
        "type": "object",
        "properties": {
            "facility_layer": {"type": "string", "description": "Point layer of facilities (health centers, warehouses, etc.)."},
            "road_network_layer": {"type": "string", "description": "Line layer of the road/path network."},
            "population_raster_layer": {"type": "string", "description": "Population-per-pixel raster (e.g. from fetch_worldpop_population)."},
            "area_layer": {"type": "string", "description": "Polygon layer defining the population base to check coverage for."},
            "travel_cost": {"type": "number", "description": "Max travel distance (network CRS units, usually meters) or time in hours if strategy='fastest'."},
            "strategy": {"type": "string", "description": "'shortest' (distance-based, default) or 'fastest' (time-based)."},
            "default_speed": {"type": "number", "description": "Default travel speed in km/h, used only when strategy='fastest'. Defaults to 50."},
        },
        "required": ["facility_layer", "road_network_layer", "population_raster_layer", "area_layer", "travel_cost"],
    },
)
def population_access_gap(facility_layer, road_network_layer, population_raster_layer, area_layer, travel_cost, strategy="shortest", default_speed=50):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    area = _find_layer_by_name(area_layer)
    if area is None:
        return {"error": f"Layer '{area_layer}' not found"}
    if QgsWkbTypes.geometryType(area.wkbType()) != QgsWkbTypes.GeometryType.PolygonGeometry:
        return {"error": f"'{area_layer}' must be a polygon layer."}

    # Reuses calculate_service_area exactly as a normal caller would -- same
    # validation, same per-facility hull-polygon layers added to the project.
    service_result = calculate_service_area(facility_layer, road_network_layer, travel_cost, strategy, default_speed)
    if "error" in service_result:
        return service_result

    # calculate_service_area names lines layers "..._service_area_lines_{i}"
    # and hull layers "..._service_area_{i}" -- only the hulls (the actual
    # reachable-area polygons) are wanted here.
    hull_names = [n for n in service_result["layers_created"] if "_lines_" not in n]
    hull_layers = [layer for layer in (_find_layer_by_name(n) for n in hull_names) if layer is not None]
    if not hull_layers:
        return {"error": "calculate_service_area produced no reachable-area polygons to check coverage against."}

    try:
        if len(hull_layers) > 1:
            merge_result = processing.run(
                "native:mergevectorlayers",
                {"LAYERS": hull_layers, "CRS": hull_layers[0].crs().authid(), "OUTPUT": "memory:"},
            )
            merged = merge_result["OUTPUT"]
        else:
            merged = hull_layers[0]

        # Dissolve away overlaps between facilities' service areas -- a
        # location reachable from two facilities must only count once, not
        # be double-counted or need per-facility attribution here.
        dissolve_result = processing.run("native:dissolve", {"INPUT": merged, "FIELD": [], "OUTPUT": "memory:"})
        reachable = dissolve_result["OUTPUT"]
        reachable_name = f"{facility_layer}_reachable_area"
        reachable.setName(reachable_name)
        QgsProject.instance().addMapLayer(reachable)

        intersect_result = processing.run(
            "native:intersection", {"INPUT": area, "OVERLAY": reachable, "OUTPUT": "memory:"}
        )
        reachable_within_area = intersect_result["OUTPUT"]
        reachable_within_area_name = f"{area_layer}_reachable_by_{facility_layer}"
        reachable_within_area.setName(reachable_within_area_name)
        QgsProject.instance().addMapLayer(reachable_within_area)
    except Exception as e:
        return {"error": f"population_access_gap geometry processing failed: {e}"}

    from .raster_tools import estimate_population_exposure

    total_pop_result = estimate_population_exposure(population_raster_layer, area_layer)
    if "error" in total_pop_result:
        return total_pop_result
    total_population = total_pop_result["total_population"]

    # A zero-feature intersection (the facilities' reach doesn't overlap
    # area_layer at all) means literally 0 people are covered -- handled
    # explicitly here rather than trusting estimate_population_exposure's
    # zonal-statistics behavior against an empty layer, which isn't a path
    # this codebase has verified against a real QGIS session.
    if reachable_within_area.featureCount() == 0:
        reachable_population = 0.0
    else:
        reachable_pop_result = estimate_population_exposure(population_raster_layer, reachable_within_area_name)
        if "error" in reachable_pop_result:
            return reachable_pop_result
        reachable_population = reachable_pop_result["total_population"]

    # Clamped at zero: raster-vs-vector zonal statistics against a slightly
    # different (intersected) geometry than the original area_layer can, in
    # principle, disagree by a hair at the pixel level -- a negative gap from
    # that kind of noise would be a nonsensical result to hand back.
    gap_population = max(0.0, total_population - reachable_population)
    gap_pct = round(gap_population / total_population * 100, 2) if total_population > 0 else None

    return {
        "success": True,
        "facility_count": service_result["facility_count"],
        "travel_cost": travel_cost,
        "strategy": strategy,
        "total_population": total_population,
        "reachable_population": reachable_population,
        "gap_population": gap_population,
        "gap_percent": gap_pct,
        "reachable_area_layer": reachable_name,
        "reachable_within_area_layer": reachable_within_area_name,
        # Point 9 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: this
        # is a modeled gap (network reachability vs. a gridded population raster),
        # not a verified count of people confirmed to lack access -- carried
        # through from estimate_population_exposure's own estimate fields rather
        # than restated as a plain, unqualified number.
        "gap_population_est": gap_population,
        "pop_source": total_pop_result.get("pop_source"),
        "pop_reference_year": total_pop_result.get("pop_reference_year"),
        "confidence": "estimate (modeled network reachability + gridded population raster; not field-verified)",
    }


@register_tool(
    "score_route_incident_risk",
    "Score a planned route (or any line layer) against how close it passes to recent security/"
    "safety incidents -- 'does this route go near any recent incidents'. Reuses buffer_analysis's "
    "exact processing call to build a buffer around the route, then counts/lists incident_layer "
    "points falling within it, each with its own distance to the route. Optionally restrict to "
    "recent incidents only (date_field + days_back) and/or weight by a numeric field (e.g. a "
    "severity score) for a weighted risk total instead of a flat count. The buffer layer it "
    "creates is auto-styled as a translucent orange risk corridor (not QGIS's default random "
    "single-symbol color) so it reads as risk on the map without a separate styling call. Does "
    "NOT re-route or exclude anything automatically -- this scores a route for a human to act on; for a genuine "
    "hard-exclude of a security-restricted area from routing itself, use difference_layers to "
    "remove that area from the road network layer before calling calculate_service_area/"
    "travel_time_matrix, see docs/archive/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md.",
    {
        "type": "object",
        "properties": {
            "route_layer": {"type": "string", "description": "Line layer of the planned route (any line layer -- a hand-drawn route, a road-network subset, etc.)."},
            "incident_layer": {"type": "string", "description": "Point layer of incidents to check proximity against, e.g. the shared 'Incidents' layer from add_incident_point."},
            "buffer_distance": {"type": "number", "description": "How close counts as 'near' the route, in the layers' CRS units (usually meters)."},
            "date_field": {"type": "string", "description": "Optional date field on incident_layer, required if days_back is set."},
            "days_back": {"type": "integer", "description": "Optional: only count incidents from the last N days. Requires date_field."},
            "weight_field": {"type": "string", "description": "Optional numeric field on incident_layer (e.g. a severity score) to compute a weighted risk total instead of a flat count."},
        },
        "required": ["route_layer", "incident_layer", "buffer_distance"],
    },
)
def score_route_incident_risk(route_layer, incident_layer, buffer_distance, date_field=None, days_back=None, weight_field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    route = _find_layer_by_name(route_layer)
    if route is None:
        return {"error": f"Layer '{route_layer}' not found"}
    incidents = _find_layer_by_name(incident_layer)
    if incidents is None:
        return {"error": f"Layer '{incident_layer}' not found"}

    incident_fields = [f.name() for f in incidents.fields()]
    if date_field and date_field not in incident_fields:
        return {"error": f"Field '{date_field}' not found on '{incident_layer}'. Available: {incident_fields}"}
    if weight_field and weight_field not in incident_fields:
        return {"error": f"Field '{weight_field}' not found on '{incident_layer}'. Available: {incident_fields}"}
    if days_back is not None and not date_field:
        return {"error": "days_back requires date_field to also be set."}
    if buffer_distance <= 0:
        return {"error": "buffer_distance must be positive."}

    route_geom = None
    for feat in route.getFeatures():
        g = feat.geometry()
        if g is None or g.isEmpty():
            continue
        route_geom = g if route_geom is None else route_geom.combine(g)
    if route_geom is None:
        return {"error": f"'{route_layer}' has no usable geometry."}

    buffer_result = buffer_analysis(route_layer, buffer_distance)
    if "error" in buffer_result:
        return buffer_result
    # QGIS-006/QGIS-007, 2026-09-13 audit: buffer_analysis already detects and warns when
    # route_layer is in a geographic CRS (Point 3 of docs/QGIS_PRODUCTION_ARCHITECTURE_
    # REVIEW_2026-09-04.md -- distance/buffer values applied in degrees, not meters), but
    # this function used to discard that warning entirely (only checked "error" in
    # buffer_result). The SAME underlying issue also mislabels distance_to_route_m below
    # (a raw route_geom.distance(geom) in the layer's own CRS units, but the field name
    # asserts meters) -- this is the more safety-relevant of the two, since this tool
    # exists specifically to score incident proximity to a route for humanitarian/security
    # decisions. Propagate the warning and extend it to cover both.
    # Fixed 2026-09-19 (was: raw route_geom.distance(geom) in CRS units, mislabeled as
    # meters on a geographic CRS -- see the comment above). route_geom is a line, not a
    # point, so _measure_distance's point-to-point ellipsoidal path doesn't directly apply
    # here -- nearestPoint() finds the closest point ON the route to each incident first,
    # then that point and the incident (itself a point, per this tool's own "Point layer of
    # incidents" schema description) go through the same _make_distance_area/
    # _measure_distance ellipsoidal measurement optimal_hub_siting/location_allocation use.
    distance_area = _make_distance_area(route)
    crs_warning = buffer_result.get("warning")
    if crs_warning:
        if distance_area is not None:
            crs_warning += (
                " 'distance_to_route_m' values below are real-world meters via ellipsoidal "
                "(WGS84 geodesic) measurement, not raw planar degrees."
            )
        else:
            crs_warning += (
                " This also means every 'distance_to_route_m' value below is in DEGREES, not "
                "meters, despite the field name."
            )
    buffer_layer_name = buffer_result["layer_name"]
    buffer_layer = _find_layer_by_name(buffer_layer_name)
    if buffer_layer is None:
        return {"error": f"Buffer layer '{buffer_layer_name}' was created but could not be found afterward."}
    _style_risk_buffer_layer(buffer_layer)

    buffer_geom = None
    for feat in buffer_layer.getFeatures():
        g = feat.geometry()
        if g is None or g.isEmpty():
            continue
        buffer_geom = g if buffer_geom is None else buffer_geom.combine(g)
    if buffer_geom is None:
        return {"error": "Route buffer produced no usable geometry."}

    cutoff_date = None
    if days_back is not None:
        cutoff_date = datetime.date.today() - datetime.timedelta(days=days_back)

    matched = []
    total_weight = 0.0
    for feat in incidents.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty() or not buffer_geom.intersects(geom):
            continue
        if cutoff_date is not None:
            d = _parse_date(feat[date_field])
            if d is None or d < cutoff_date:
                continue
        weight = 1.0
        if weight_field:
            val = feat[weight_field]
            weight = float(val) if isinstance(val, (int, float)) else 1.0
        total_weight += weight
        nearest_on_route = route_geom.nearestPoint(geom)
        matched.append({
            "incident_id": feat.id(),
            "distance_to_route_m": round(_measure_distance(distance_area, nearest_on_route, geom), 1),
            "date": str(feat[date_field]) if date_field else None,
            "weight": weight if weight_field else None,
        })

    matched.sort(key=lambda e: e["distance_to_route_m"])
    matched_capped, matched_total, truncated = _cap_entries(matched)

    result = {
        "success": True,
        "route_layer": route_layer,
        "incident_layer": incident_layer,
        "buffer_distance": buffer_distance,
        "buffer_layer_name": buffer_layer_name,
        "days_back": days_back,
        "incident_count": matched_total,
        "total_weighted_risk": round(total_weight, 2) if weight_field else None,
        "incidents": matched_capped,
        "truncated": truncated,
    }
    if crs_warning:
        result["warning"] = crs_warning
    return result
