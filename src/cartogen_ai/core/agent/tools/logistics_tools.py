# -*- coding: utf-8 -*-
"""
Humanitarian Logistics Tools for Cartogen AI.
Hub siting, service-area, and travel-distance analysis for supply chain / last-
mile delivery planning (warehouse coverage, distribution routing). The
service-area and travel-matrix tools rely on QGIS's native Network Analysis
processing algorithms (native:serviceareafrompoint, native:shortestpathpointtolayer)
-- unlike the rest of this codebase's processing.run() calls (native:clip,
native:intersection, etc., which are exercised constantly and well-documented),
these are less commonly used and this plugin's dev environment has no real QGIS
install to verify them live against, so treat their exact parameter names as
best-effort until confirmed against a real QGIS session.

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

try:
    from qgis.core import QgsProject, QgsWkbTypes, QgsSymbol, QgsSingleSymbolRenderer
    from qgis.PyQt.QtGui import QColor
    import processing
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


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

        candidate_distances = {}
        for i, cand_feat in enumerate(candidates.getFeatures()):
            cand_geom = cand_feat.geometry()
            if cand_geom.isEmpty():
                continue
            name = cand_feat.attribute(0) if cand_feat.fields().count() else f"candidate_{i}"
            candidate_distances[str(name)] = [cand_geom.distance(dg) for dg in demand_geoms]

        if not candidate_distances:
            return {"error": f"'{candidate_layer}' has no usable point features."}

        ranked = _rank_hub_candidates(candidate_distances, max_distance)
        return {
            "success": True,
            "candidate_count": len(ranked),
            "demand_point_count": len(demand_geoms),
            "ranked_candidates": ranked,
        }
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

        candidate_distances = {}
        for i, cand_feat in enumerate(candidates.getFeatures()):
            cand_geom = cand_feat.geometry()
            if cand_geom.isEmpty():
                continue
            name = cand_feat.attribute(0) if cand_feat.fields().count() else f"candidate_{i}"
            candidate_distances[str(name)] = [cand_geom.distance(dg) for dg in demand_geoms]

        if not candidate_distances:
            return {"error": f"'{candidate_layer}' has no usable point features."}
        if num_facilities > len(candidate_distances):
            return {"error": f"num_facilities ({num_facilities}) exceeds the number of usable candidates ({len(candidate_distances)})."}

        result = _greedy_p_median(candidate_distances, demand_weights, num_facilities)
        result["success"] = True
        result["candidate_count"] = len(candidate_distances)
        result["demand_point_count"] = len(demand_geoms)
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
    "should the truck visit these 8 distribution points'. Uses straight-line distance and a "
    "standard nearest-neighbor + 2-opt heuristic to pick the *order* (not a guaranteed "
    "globally-optimal order, and not road-network-aware for ordering purposes). Without "
    "road_network_layer, the result is a stop order only -- do NOT draw a straight line between "
    "the stops and present it as a route on an operational map; it is not a routable path. Pass "
    "road_network_layer to also build an actual road-snapped route line (via QGIS's network "
    "analysis, same as calculate_service_area/travel_time_matrix), added to the project and safe "
    "to render as a real route. Not a substitute for a full commercial VRP solver with vehicle "
    "capacity/time-window constraints.",
    {
        "type": "object",
        "properties": {
            "stops_layer": {"type": "string", "description": "Point layer of stops to visit."},
            "start_stop_name": {"type": "string", "description": "Optional name (from the layer's first attribute field) of the stop to start from. Defaults to the first feature."},
            "road_network_layer": {"type": "string", "description": "Optional line layer representing the road/path network. When given, a road-snapped route line (following actual roads between stops in visiting order) is built and added to the project -- required before the output may be rendered as a route on a map."},
        },
        "required": ["stops_layer"],
    },
)
def optimize_delivery_route(stops_layer, start_stop_name=None, road_network_layer=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(stops_layer)
    if layer is None:
        return {"error": f"Layer '{stops_layer}' not found"}

    network = None
    if road_network_layer is not None:
        network = _find_layer_by_name(road_network_layer)
        if network is None:
            return {"error": f"Layer '{road_network_layer}' not found"}

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
        distance_matrix = [[geoms[i].distance(geoms[j]) for j in range(n)] for i in range(n)]

        tour, total_distance = _optimize_route(distance_matrix, start_index)
        ordered_names = [names[i] for i in tour]

        result = {
            "success": True,
            "stops_layer": stops_layer,
            "stop_count": n,
            "route_order": ordered_names,
            "total_distance": round(total_distance, 2),
        }

        if network is None:
            result["warning"] = (
                "No road_network_layer given -- total_distance is straight-line and route_order "
                "is a stop sequence only, not a routable path. Do not render a line through these "
                "stops as a delivery route; pass road_network_layer to build one."
            )
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


@register_tool(
    "calculate_service_area",
    "Calculate the reachable road-network area around one or more facilities (warehouse, clinic, "
    "distribution point) within a given travel distance or time -- e.g. 'what area can this "
    "warehouse serve within 30km by road'. Produces, per facility, both the reachable road network "
    "and an approximate coverage polygon (convex hull around it). Requires a real line layer "
    "representing the road network -- for simple straight-line/as-the-crow-flies coverage, use "
    "buffer_analysis instead.",
    {
        "type": "object",
        "properties": {
            "facility_layer": {"type": "string", "description": "Point layer with the facility/facilities to calculate service areas for."},
            "road_network_layer": {"type": "string", "description": "Line layer representing the road/path network."},
            "travel_cost": {"type": "number", "description": "Maximum travel distance (network CRS units, usually meters) or time in hours if strategy='fastest'."},
            "strategy": {"type": "string", "description": "'shortest' (distance-based, default) or 'fastest' (time-based)."},
            "default_speed": {"type": "number", "description": "Default travel speed in km/h, used only when strategy='fastest'. Defaults to 50."},
        },
        "required": ["facility_layer", "road_network_layer", "travel_cost"],
    },
)
def calculate_service_area(facility_layer, road_network_layer, travel_cost, strategy="shortest", default_speed=50):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if travel_cost <= 0:
        return {"error": "travel_cost must be positive."}
    strategy = (strategy or "shortest").lower()
    if strategy not in ("shortest", "fastest"):
        return {"error": "strategy must be 'shortest' or 'fastest'."}

    network = _find_layer_by_name(road_network_layer)
    facilities = _find_layer_by_name(facility_layer)
    if network is None:
        return {"error": f"Layer '{road_network_layer}' not found"}
    if facilities is None:
        return {"error": f"Layer '{facility_layer}' not found"}

    try:
        strategy_val = 1 if strategy == "fastest" else 0
        layers_created = []
        served_count = 0
        for i, feat in enumerate(facilities.getFeatures()):
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            point = geom.asPoint()
            params = {
                "INPUT": network,
                "STRATEGY": strategy_val,
                "DEFAULT_SPEED": default_speed,
                "TOLERANCE": 0,
                "START_POINT": f"{point.x()},{point.y()}",
                "TRAVEL_COST2": travel_cost,
                "OUTPUT_LINES": "memory:",
            }
            output = processing.run("native:serviceareafrompoint", params)
            lines_layer = output.get("OUTPUT_LINES")
            if lines_layer is None or lines_layer.featureCount() == 0:
                continue

            lines_name = f"{facility_layer}_service_area_lines_{i}"
            lines_layer.setName(lines_name)
            QgsProject.instance().addMapLayer(lines_layer)
            layers_created.append(lines_name)

            hull = processing.run("native:convexhull", {"INPUT": lines_layer, "OUTPUT": "memory:"})
            hull_layer = hull.get("OUTPUT")
            if hull_layer is not None:
                hull_name = f"{facility_layer}_service_area_{i}"
                hull_layer.setName(hull_name)
                QgsProject.instance().addMapLayer(hull_layer)
                layers_created.append(hull_name)

            served_count += 1

        if served_count == 0:
            return {"error": "Could not build a service area for any facility -- check the facility points are near the road network."}

        return {
            "success": True,
            "facility_count": served_count,
            "travel_cost": travel_cost,
            "strategy": strategy,
            "layers_created": layers_created,
        }
    except Exception as e:
        return {"error": f"calculate_service_area failed: {e}"}


@register_tool(
    "travel_time_matrix",
    "Calculate shortest-path road-network distance from each origin point to each destination "
    "point -- e.g. delivery distance from each warehouse to each distribution site. Returns a "
    "matrix of distances (network CRS units, usually meters) keyed by origin then destination. "
    "Requires a line layer representing the road network, not straight-line distance.",
    {
        "type": "object",
        "properties": {
            "origins_layer": {"type": "string", "description": "Point layer of origin locations (e.g. warehouses)."},
            "destinations_layer": {"type": "string", "description": "Point layer of destination locations (e.g. distribution sites)."},
            "road_network_layer": {"type": "string", "description": "Line layer representing the road/path network."},
        },
        "required": ["origins_layer", "destinations_layer", "road_network_layer"],
    },
)
def travel_time_matrix(origins_layer, destinations_layer, road_network_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    origins = _find_layer_by_name(origins_layer)
    destinations = _find_layer_by_name(destinations_layer)
    network = _find_layer_by_name(road_network_layer)
    if origins is None:
        return {"error": f"Layer '{origins_layer}' not found"}
    if destinations is None:
        return {"error": f"Layer '{destinations_layer}' not found"}
    if network is None:
        return {"error": f"Layer '{road_network_layer}' not found"}

    try:
        origin_features = [f for f in origins.getFeatures() if not f.geometry().isEmpty()]
        if not origin_features:
            return {"error": f"'{origins_layer}' has no usable point features."}

        matrix = {}
        for i, origin_feat in enumerate(origin_features):
            origin_id = origin_feat.attribute(0) if origin_feat.fields().count() else f"origin_{i}"
            point = origin_feat.geometry().asPoint()
            params = {
                "INPUT": network,
                "STRATEGY": 0,
                "DEFAULT_SPEED": 50,
                "TOLERANCE": 0,
                "START_POINT": f"{point.x()},{point.y()}",
                "END_POINTS": destinations,
                "OUTPUT": "memory:",
            }
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
        return {
            "success": True,
            "origins_layer": origins_layer,
            "destinations_layer": destinations_layer,
            "matrix": matrix,
        }
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
    hull_layers = [l for l in (_find_layer_by_name(n) for n in hull_names) if l is not None]
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
        matched.append({
            "incident_id": feat.id(),
            "distance_to_route_m": round(route_geom.distance(geom), 1),
            "date": str(feat[date_field]) if date_field else None,
            "weight": weight if weight_field else None,
        })

    matched.sort(key=lambda e: e["distance_to_route_m"])
    matched_capped, matched_total, truncated = _cap_entries(matched)

    return {
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
