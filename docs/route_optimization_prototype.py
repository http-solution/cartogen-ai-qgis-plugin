#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Route optimization prototype -- constrained shortest path for post-disaster /
humanitarian logistics, using OSMnx + NetworkX + GeoPandas + rasterio.

See docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md section 4 for full context. Read that
section before reading this file -- it explains WHY this uses a different
stack than Cartogen AI's shipped tools (agent/tools/logistics_tools.py, which
use QGIS's own native Network Analysis processing algorithms).

STATUS (updated 2026-08-21, see docs/RELEASE_SMOKE_TEST.md task history): this
has now been smoke-tested in a real Python environment with osmnx 2.0.7,
networkx, geopandas, rasterio, and shapely actually installed -- but against a
small hand-built synthetic MultiDiGraph + synthetic GeoTIFF DEM standing in
for ox.graph_from_bbox()'s live Overpass fetch (no outbound network access to
Overpass or a real DEM source was available in that environment either). That
run found and fixed two real bugs (see below) and confirmed
build_constrained_graph()'s cost function and find_constrained_route()'s
Dijkstra search do what the docstrings claim: a synthetic route with a
shorter, unpaved+steep alternative correctly prefers the longer paved route
once the surface and slope penalties are applied, and reduces to the same
preference (just less pronounced) with the slope penalty alone (dem_path
supplied) or the surface penalty alone (dem_path=None). Still NOT run against
a real downloaded road network or a real DEM -- that's the remaining gap
before this can be trusted for an actual field routing decision.

Bugs found and fixed by that smoke test:
1. build_constrained_graph() passed ox.graph_from_bbox(bbox=(north, south,
   east, west), ...) -- but osmnx 2.0.7's actual signature wants
   bbox=(west, south, east, north) ("left, bottom, right, top" per its own
   docstring). This is exactly the version-order risk this file used to flag
   without having verified it; now verified and fixed against 2.0.7.
2. find_constrained_route()'s ox.distance.nearest_nodes() call raised
   ImportError: scikit-learn must be installed as an optional dependency to
   search an unprojected graph -- scikit-learn wasn't in this file's stated
   pip install line. Added below.

Treat this as a validated cost-function/routing-logic prototype that still
needs a real network + real DEM run before field use -- not as proven-working
end-to-end code.

What this demonstrates: a route between two lon/lat points that factors in
TWO custom constraints on top of plain shortest-distance:
  1. Road surface -- unpaved/track/gravel roads get a cost penalty, so the
     algorithm prefers a paved alternative when one exists instead of being
     blind to surface quality.
  2. Elevation/slope -- steep grade (from a local DEM) gets a cost penalty,
     relevant for heavy cargo trucks in particular.

Both penalties are combined into ONE custom edge-cost field, then a standard
NetworkX Dijkstra shortest-path search is run over that cost -- deliberately
not hand-rolling a new shortest-path algorithm (see the strategy doc's
section 2, item 5: Dijkstra is the right algorithm family here, the fix is
what feeds its cost function, not which algorithm computes the result).

Dependencies (not in this plugin's requirements.txt -- this is a standalone
prototype, not a registered Cartogen AI tool):
    pip install osmnx networkx geopandas rasterio shapely scikit-learn
(scikit-learn is required by osmnx's own ox.distance.nearest_nodes() when
called on an unprojected lon/lat graph, as find_constrained_route() does --
confirmed by actually running this file; osmnx raises a clear ImportError
without it, it doesn't fail silently.)

Usage (see the __main__ block at the bottom for a runnable example):
    from route_optimization_prototype import (
        build_constrained_graph, find_constrained_route,
    )
    G = build_constrained_graph(
        north=34.85, south=34.75, east=36.75, west=36.65,  # bbox around the area of interest
        dem_path="path/to/local_dem.tif",                  # optional -- omit to skip slope penalty
        vehicle_profile="heavy_truck",
    )
    result = find_constrained_route(G, origin=(36.70, 34.80), destination=(36.72, 34.78))
    print(result["total_distance_km"], result["total_estimated_time_hours"])
    result["route_gdf"].to_file("route.geojson", driver="GeoJSON")
"""

import math

import geopandas as gpd
import networkx as nx
import osmnx as ox
from shapely.geometry import LineString, Point

try:
    import rasterio
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False


# Base speed (km/h) by OSM highway class -- a starting default table, meant to
# be REPLACED by real calibrated values once historical GPS data is available
# (see docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md section 3, item 2: derive real
# per-segment speeds from GPS traces rather than trusting this table long-term).
_DEFAULT_SPEED_KMH_BY_HIGHWAY = {
    "motorway": 90, "trunk": 80, "primary": 60, "secondary": 50,
    "tertiary": 40, "unclassified": 30, "residential": 25,
    "track": 15, "path": 8, "service": 20,
}
_FALLBACK_SPEED_KMH = 30  # used when an edge's highway tag isn't in the table above

# Surface penalty multiplier applied to travel time -- paved surfaces are
# unpenalized (1.0); unpaved/degraded surfaces cost more than their raw
# length/speed alone would suggest, so the routing algorithm prefers a paved
# alternative when one exists instead of being blind to surface quality.
_PAVED_SURFACES = {"paved", "asphalt", "concrete", "paving_stones", "sett"}
_UNPAVED_SURFACES = {"unpaved", "gravel", "dirt", "ground", "earth", "sand", "grass", "mud"}
_UNPAVED_PENALTY = 2.5
# Missing/unknown surface tags are common in post-disaster OSM data -- treated
# as a moderate, not zero, risk rather than assuming "unknown" means "fine".
# This is a deliberate, stated assumption, not a hidden default.
_UNKNOWN_SURFACE_PENALTY = 1.3

# Vehicle profiles: max acceptable grade (%) before the slope penalty kicks in
# hard, and whether unpaved roads should be excluded entirely rather than just
# penalized. Illustrative starting values -- calibrate against real vehicle
# capability, not treated as authoritative here.
VEHICLE_PROFILES = {
    "heavy_truck": {"max_grade_pct": 8.0, "exclude_unpaved": False, "steep_penalty_scale": 6.0},
    "delivery_van": {"max_grade_pct": 12.0, "exclude_unpaved": False, "steep_penalty_scale": 3.0},
    "4x4": {"max_grade_pct": 25.0, "exclude_unpaved": False, "steep_penalty_scale": 1.5},
    "on_foot": {"max_grade_pct": 40.0, "exclude_unpaved": False, "steep_penalty_scale": 1.0},
}


def _edge_base_speed_kmh(edge_data):
    """OSMnx graph edges can carry `highway` as a single string OR a list of
    strings (when OSM tags multiple classifications on one way) -- handles
    both, using the first value in the list case rather than raising."""
    highway = edge_data.get("highway", "unclassified")
    if isinstance(highway, list):
        highway = highway[0] if highway else "unclassified"
    return _DEFAULT_SPEED_KMH_BY_HIGHWAY.get(highway, _FALLBACK_SPEED_KMH)


def _surface_penalty(edge_data):
    """Same list-or-string handling as highway tags -- `surface` is an
    optional OSM tag, frequently absent, especially in less-mapped
    post-disaster areas."""
    surface = edge_data.get("surface")
    if isinstance(surface, list):
        surface = surface[0] if surface else None
    if surface is None:
        return _UNKNOWN_SURFACE_PENALTY
    surface = str(surface).lower()
    if surface in _PAVED_SURFACES:
        return 1.0
    if surface in _UNPAVED_SURFACES:
        return _UNPAVED_PENALTY
    return _UNKNOWN_SURFACE_PENALTY  # a surface value present but not in either known set


def _sample_elevation(dem_dataset, lon, lat):
    """Samples a single elevation value from an open rasterio dataset at
    (lon, lat). Assumes the DEM is in EPSG:4326 (true for SRTM/Copernicus
    DEM as commonly distributed) matching OSMnx's default graph CRS -- a
    real deployment should verify this and reproject if the DEM uses a
    different CRS; not handled here to keep this prototype's scope to what
    the strategy doc actually asked for (a working example of the two named
    constraints), not a general-purpose CRS-reprojection utility."""
    try:
        value = next(dem_dataset.sample([(lon, lat)]))[0]
        return float(value)
    except (StopIteration, IndexError, ValueError):
        return None


def _grade_percent(elev_u, elev_v, length_m):
    if elev_u is None or elev_v is None or length_m <= 0:
        return 0.0
    return abs(elev_v - elev_u) / length_m * 100.0


def build_constrained_graph(north, south, east, west, dem_path=None,
                             vehicle_profile="heavy_truck", network_type="drive"):
    """Downloads a road network for the given bounding box via OSMnx and
    computes a custom `constrained_cost` (hours) attribute on every edge,
    combining base travel time, surface penalty, and (if dem_path is given)
    a slope penalty. Returns the graph with that attribute added -- does NOT
    mutate OSMnx's own `length`/`travel_time` attributes, so the raw
    unweighted graph is still available for comparison.

    network_type="drive" excludes footpaths/trails by default (matches
    OSMnx's own convention) -- pass "walk" for on-foot field worker routing,
    which is a materially different network (footpaths become usable, not
    just a slower version of the same roads)."""
    if vehicle_profile not in VEHICLE_PROFILES:
        raise ValueError(f"Unknown vehicle_profile '{vehicle_profile}'. Choose from: {list(VEHICLE_PROFILES)}")
    profile = VEHICLE_PROFILES[vehicle_profile]

    # VERSION NOTE (confirmed 2026-08-21 against an actually-installed osmnx
    # 2.0.7, not assumed): osmnx has changed graph_from_bbox's argument
    # order/shape across major versions -- older releases took separate
    # north/south/east/west args; 2.0.7 takes a single bbox tuple in
    # (left, bottom, right, top) order, i.e. (west, south, east, north), per
    # ox.graph_from_bbox's own docstring. The original version of this line
    # passed (north, south, east, west), which is NOT what 2.0.7 wants -- that
    # was a real bug, caught by actually calling this function (via a
    # monkeypatched graph_from_bbox feeding a synthetic graph, since no live
    # Overpass access was available either) rather than by inspection alone.
    # If you're on a different osmnx version, re-verify against that version's
    # docs before trusting this line -- the order has moved before.
    G = ox.graph_from_bbox(bbox=(west, south, east, north), network_type=network_type, simplify=True)

    dem_dataset = None
    if dem_path is not None:
        if not RASTERIO_AVAILABLE:
            raise ImportError("rasterio is required for slope-aware routing (dem_path was given). "
                               "pip install rasterio, or omit dem_path to skip the slope penalty.")
        dem_dataset = rasterio.open(dem_path)

    # Cache per-node elevation lookups -- many edges share endpoints, no
    # reason to re-sample the DEM for the same coordinate repeatedly.
    elevation_cache = {}

    def node_elevation(node_id):
        if node_id in elevation_cache:
            return elevation_cache[node_id]
        node = G.nodes[node_id]
        elev = _sample_elevation(dem_dataset, node["x"], node["y"]) if dem_dataset is not None else None
        elevation_cache[node_id] = elev
        return elev

    try:
        for u, v, key, data in G.edges(keys=True, data=True):
            length_m = data.get("length", 0.0)
            speed_kmh = _edge_base_speed_kmh(data)
            base_time_hours = (length_m / 1000.0) / speed_kmh if speed_kmh > 0 else float("inf")

            surface_mult = _surface_penalty(data)
            if profile["exclude_unpaved"] and surface_mult > 1.0:
                data["constrained_cost"] = float("inf")
                continue

            slope_mult = 1.0
            if dem_dataset is not None:
                elev_u, elev_v = node_elevation(u), node_elevation(v)
                grade_pct = _grade_percent(elev_u, elev_v, length_m)
                if grade_pct > profile["max_grade_pct"]:
                    # Scales smoothly past the threshold rather than a hard
                    # cutoff -- a grade just over the limit costs a little
                    # more, a grade far over it costs much more, instead of
                    # both being clamped to the same "excluded" state.
                    excess = grade_pct - profile["max_grade_pct"]
                    slope_mult = 1.0 + (excess / 10.0) * profile["steep_penalty_scale"]

            data["constrained_cost"] = base_time_hours * surface_mult * slope_mult
            data["_base_time_hours"] = base_time_hours  # kept for the result breakdown below
    finally:
        if dem_dataset is not None:
            dem_dataset.close()

    return G


def find_constrained_route(G, origin, destination):
    """origin/destination are (lon, lat) tuples. Snaps each to its nearest
    graph node, runs NetworkX Dijkstra over the `constrained_cost` attribute
    build_constrained_graph() computed, and returns both the route and a
    breakdown against the UNPENALIZED base travel time so you can see how
    much the surface/slope penalties actually changed the outcome -- useful
    for the validation comparison docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md section 3
    describes."""
    orig_node = ox.distance.nearest_nodes(G, X=origin[0], Y=origin[1])
    dest_node = ox.distance.nearest_nodes(G, X=destination[0], Y=destination[1])

    try:
        node_path = nx.shortest_path(G, orig_node, dest_node, weight="constrained_cost")
    except nx.NetworkXNoPath:
        return {"success": False, "error": "No route found between origin and destination in this network."}

    total_distance_m = 0.0
    total_constrained_hours = 0.0
    total_base_hours = 0.0
    line_points = []

    for i in range(len(node_path) - 1):
        u, v = node_path[i], node_path[i + 1]
        # A MultiDiGraph can have multiple parallel edges between the same
        # two nodes -- take the one Dijkstra actually used (lowest
        # constrained_cost), matching what nx.shortest_path itself selected.
        edge_data = min(G.get_edge_data(u, v).values(), key=lambda d: d.get("constrained_cost", float("inf")))
        total_distance_m += edge_data.get("length", 0.0)
        total_constrained_hours += edge_data.get("constrained_cost", 0.0)
        total_base_hours += edge_data.get("_base_time_hours", 0.0)
        line_points.append((G.nodes[u]["x"], G.nodes[u]["y"]))
    last_node = node_path[-1]
    line_points.append((G.nodes[last_node]["x"], G.nodes[last_node]["y"]))

    route_gdf = gpd.GeoDataFrame(
        {"segment": ["full_route"]},
        geometry=[LineString(line_points)],
        crs="EPSG:4326",
    )

    penalty_overhead_pct = (
        round((total_constrained_hours - total_base_hours) / total_base_hours * 100, 1)
        if total_base_hours > 0 else None
    )

    return {
        "success": True,
        "node_path": node_path,
        "total_distance_km": round(total_distance_m / 1000.0, 2),
        "total_estimated_time_hours": round(total_constrained_hours, 2),
        "unpenalized_time_hours": round(total_base_hours, 2),
        "penalty_overhead_percent": penalty_overhead_pct,
        "route_gdf": route_gdf,
    }


if __name__ == "__main__":
    # Illustrative example only -- replace the bbox/coordinates/DEM path with
    # your real area of interest before running. Not executed as part of any
    # test suite; running this requires real network access to OSM's servers
    # (or a pre-downloaded .graphml, see ox.load_graphml) and, if you want the
    # slope penalty, a real local DEM GeoTIFF covering the same area.
    example_bbox = dict(north=34.85, south=34.75, east=36.75, west=36.65)

    graph = build_constrained_graph(
        **example_bbox,
        dem_path=None,  # set to a real local DEM path to enable the slope penalty
        vehicle_profile="heavy_truck",
    )

    route = find_constrained_route(
        graph,
        origin=(36.70, 34.80),
        destination=(36.72, 34.78),
    )

    if route["success"]:
        print(f"Distance: {route['total_distance_km']} km")
        print(f"Estimated time (constrained): {route['total_estimated_time_hours']} h")
        print(f"Estimated time (unpenalized baseline): {route['unpenalized_time_hours']} h")
        print(f"Penalty overhead: {route['penalty_overhead_percent']}%")
        route["route_gdf"].to_file("route_output.geojson", driver="GeoJSON")
    else:
        print(f"Routing failed: {route['error']}")
