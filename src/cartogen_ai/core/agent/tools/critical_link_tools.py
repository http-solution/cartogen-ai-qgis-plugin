# -*- coding: utf-8 -*-
"""Critical-link (bottleneck) screening on a road network (H9, docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md).

What it measures: for a set of origins and destinations, how much origin-to-destination demand has its SHORTEST path through each road
segment. A segment with a high load is one the routes depend on; closing it forces every one of those routes onto another road. It is
a screening measure of dependence, NOT a simulation of closure (that would need a re-route per segment) and NOT a traffic forecast:
- one shortest path is used per OD pair; where several are equally short the tree picks one,
- the cost is distance ('shortest') or time at the speed field / default speed ('fastest'), so it ignores congestion, convoy size,
  security and anything not in the network,
- loads count the weights the user gives (a weight field on origins and/or destinations; default 1 each), so with no weights the
  figure is a number of OD pairs, not people or tonnes.

How it stays fast (the earlier network analysis took minutes on national roads): ONE graph is built with every origin tied in (the
brute-force tie is segments x origins, so origins are capped), then one Dijkstra per origin. The load on every edge of an origin's
shortest-path tree is the weight of the destinations below it, accumulated from the leaves up in a single pass
(`accumulate_tree_load`), so there is no path walk per OD pair. Destinations are snapped to the nearest graph vertex (further than
`max_snap_m` they are left out and counted). A time budget stops between origins and says so; the partial result is labelled partial.
The graph build itself cannot be interrupted and grows with the number of roads: clip the network to the area first for national data.

Pure logic is unit tested offline; the layer work needs QGIS (tests/test_critical_link_tools_live.py, written without a local QGIS).
"""
import time

from .registry import register_tool

try:
    from qgis.core import (QgsDistanceArea, QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsProject, QgsSpatialIndex,
                           QgsVectorLayer)
    from qgis.PyQt.QtCore import QVariant
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

UNREACHABLE = 1.0e300       # QgsGraphAnalyzer.dijkstra marks an unreachable vertex with DOUBLE_MAX (~1.8e308)
MAX_ORIGINS = 200
MAX_DESTINATIONS = 5000
DEFAULT_ORIGINS = 50
DEFAULT_TIME_BUDGET_S = 120.0
_TOP_CAP = 25


# ---------------------------------------------------------------- pure --
def accumulate_tree_load(parents, costs, weights):
    """Load on every edge of one shortest-path tree.

    `parents[v]` is the vertex before v on its shortest path (-1 for the root and for unreachable vertices), `costs[v]` its cost
    (>= UNREACHABLE means unreachable), `weights` {vertex: demand ending there}. Returns (loads, reached, unreached): `loads` maps v
    to the weight carried by the edge (parents[v] -> v), i.e. the total weight of v's subtree; `reached` / `unreached` split the total
    weight by whether its vertex is reachable. Leaves-first (Kahn) so zero-length edges cannot break the order."""
    n = len(parents)
    children = [0] * n
    for v in range(n):
        p = parents[v]
        if p >= 0 and costs[v] < UNREACHABLE:
            children[p] += 1
    acc = [0.0] * n
    reached = unreached = 0.0
    for v, w in weights.items():
        if 0 <= v < n and costs[v] < UNREACHABLE:
            acc[v] += w
            reached += w
        else:
            unreached += w
    stack = [v for v in range(n) if children[v] == 0 and costs[v] < UNREACHABLE]
    loads = {}
    while stack:
        v = stack.pop()
        p = parents[v]
        if p < 0:
            continue
        loads[v] = acc[v]
        acc[p] += acc[v]
        children[p] -= 1
        if children[p] == 0:
            stack.append(p)
    return loads, reached, unreached


def edge_key(a, b):
    return (a, b) if a < b else (b, a)


def classify_loads(values, classes=5):
    """Upper bounds of `classes` equal-count (quantile) classes over the positive values, strictly increasing; fewer when the values
    do not support that many. Empty for no positive value. Pure."""
    pos = sorted(v for v in values if v > 0)
    if not pos:
        return []
    bounds = []
    for k in range(1, classes + 1):
        b = pos[min(len(pos) - 1, max(0, -(-len(pos) * k // classes) - 1))]
        if not bounds or b > bounds[-1]:
            bounds.append(b)
    return bounds


# ---------------------------------------------------------------- QGIS --
def _layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _weight(feature, field):
    if not field:
        return 1.0
    v = feature[field]
    try:
        w = float(v)
    except (TypeError, ValueError):
        return None
    return w if w == w and w >= 0 else None


def _style(layer, bounds):
    from qgis.core import QgsGraduatedSymbolRenderer, QgsLineSymbol, QgsRendererRange
    colors = ["#fdd49e", "#fdbb84", "#fc8d59", "#e34a33", "#b30000"]
    widths = [0.4, 0.7, 1.0, 1.4, 1.9]
    ranges, lo = [], 0.0
    for i, hi in enumerate(bounds):
        symbol = QgsLineSymbol.createSimple({"color": colors[i], "width": str(widths[i]), "capstyle": "round", "joinstyle": "round"})
        ranges.append(QgsRendererRange(lo, hi, symbol, f"{lo:g} - {hi:g}"))
        lo = hi
    layer.setRenderer(QgsGraduatedSymbolRenderer("load", ranges))
    layer.triggerRepaint()


@register_tool(
    "analyze_critical_links",
    "Screen a road network for bottlenecks: how much origin-to-destination demand has its shortest path through each road segment. A "
    "segment with a high load is one many routes depend on -- closing it would push all of them onto other roads. This is a SCREENING "
    "measure of dependence, not a closure simulation and not a traffic forecast: one shortest path per pair (cost = distance, or time "
    "from the speed field), no congestion, convoy size or security, and the load counts OD pairs unless weight fields are given. "
    "Origins are capped (default 50, max 200) and a time budget stops the run between origins and labels the result partial; for "
    "national road data clip the network to the area first. Closed roads (negative speed) are left out. Draws the roads graded by load "
    "in a new layer and returns the heaviest segments.",
    {
        "type": "object",
        "properties": {
            "road_network_layer": {"type": "string", "description": "Line layer with the road network."},
            "origins_layer": {"type": "string", "description": "Point layer of origins (e.g. warehouses, hubs)."},
            "destinations_layer": {"type": "string", "description": "Point layer of destinations (e.g. facilities, settlements). Default: the origins layer."},
            "strategy": {"type": "string", "description": "'shortest' (distance, default) or 'fastest' (time)."},
            "default_speed": {"type": "number", "description": "km/h for segments without a speed, used only for 'fastest'. Default 50."},
            "speed_field": {"type": "string", "description": "Optional per-segment speed (km/h). A negative value marks a closed road, which is removed."},
            "direction_field": {"type": "string", "description": "Optional one-way field."},
            "value_forward": {"type": "string", "description": "direction_field value for forward-only. Default 'yes'."},
            "value_backward": {"type": "string", "description": "direction_field value for backward-only. Default '-1'."},
            "value_both": {"type": "string", "description": "direction_field value for both ways. Default 'no'."},
            "origin_weight_field": {"type": "string", "description": "Optional non-negative numeric field weighting each origin."},
            "destination_weight_field": {"type": "string", "description": "Optional non-negative numeric field weighting each destination (e.g. population)."},
            "max_origins": {"type": "integer", "description": "Origins to use, at most 200. Default 50; more origins are left out and counted."},
            "max_snap_m": {"type": "number", "description": "A destination further than this from the road graph is left out. Default 2000 m."},
            "time_budget_s": {"type": "number", "description": "Stop between origins after this many seconds. Default 120."},
            "top_n": {"type": "integer", "description": "Heaviest segments to return. Default 10."},
            "output_layer_name": {"type": "string", "description": "Name of the output line layer. Default 'critical_links'."},
        },
        "required": ["road_network_layer", "origins_layer"],
    },
)
def analyze_critical_links(road_network_layer, origins_layer, destinations_layer=None, strategy="shortest", default_speed=50,
                           speed_field=None, direction_field=None, value_forward="yes", value_backward="-1", value_both="no",
                           origin_weight_field=None, destination_weight_field=None, max_origins=DEFAULT_ORIGINS, max_snap_m=2000.0,
                           time_budget_s=DEFAULT_TIME_BUDGET_S, top_n=10, output_layer_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from . import logistics_tools as lt
    if not lt.single_tree_costs_available():
        return {"error": "The QGIS network-analysis classes are not available, so critical links cannot be computed."}
    strategy = (strategy or "shortest").lower()
    if strategy not in ("shortest", "fastest"):
        return {"error": "strategy must be 'shortest' or 'fastest'."}
    try:
        max_origins = int(max_origins)
        top_n = max(1, min(_TOP_CAP, int(top_n)))
        max_snap_m = float(max_snap_m)
        time_budget_s = float(time_budget_s)
    except (TypeError, ValueError):
        return {"error": "max_origins, top_n, max_snap_m and time_budget_s must be numbers."}
    if max_origins < 1 or max_snap_m <= 0 or time_budget_s <= 0:
        return {"error": "max_origins, max_snap_m and time_budget_s must be above zero."}
    max_origins = min(max_origins, MAX_ORIGINS)

    network = _layer(road_network_layer)
    origins = _layer(origins_layer)
    destinations = _layer(destinations_layer) if destinations_layer else origins
    for label, lyr, nm in (("Road network", network, road_network_layer), ("Origins", origins, origins_layer),
                           ("Destinations", destinations, destinations_layer or origins_layer)):
        if lyr is None:
            return {"error": f"{label} layer '{nm}' not found"}
    geometry_error = lt._network_geometry_error(network, road_network_layer)
    if geometry_error:
        return {"error": geometry_error}
    for lyr, field in ((origins, origin_weight_field), (destinations, destination_weight_field)):
        if field and lyr.fields().indexOf(field) < 0:
            return {"error": f"Weight field '{field}' not found on '{lyr.name()}'."}
    network, closed, closed_error = lt._open_network(network, speed_field, road_network_layer)
    if closed_error:
        return {"error": closed_error}
    _extra, field_error = lt._network_direction_speed_params(network, speed_field, direction_field, value_forward, value_backward, value_both)
    if field_error:
        return {"error": field_error}

    started = time.monotonic()
    origin_feats = [f for f in origins.getFeatures() if f.hasGeometry() and not f.geometry().isEmpty()]
    origin_skipped_weight = 0
    usable = []
    for f in origin_feats:
        w = _weight(f, origin_weight_field)
        if w is None:
            origin_skipped_weight += 1
        elif w > 0:
            usable.append((f, w))
    if not usable:
        return {"error": f"'{origins_layer}' has no usable origin (needs a point and, with a weight field, a non-negative number above zero)."}
    origins_left_out = max(0, len(usable) - max_origins)
    usable = usable[:max_origins]
    dest_items, dest_skipped_weight = [], 0
    for f in destinations.getFeatures():
        if not f.hasGeometry() or f.geometry().isEmpty():
            continue
        w = _weight(f, destination_weight_field)
        if w is None:
            dest_skipped_weight += 1
        elif w > 0:
            dest_items.append((f, w))
    if not dest_items:
        return {"error": f"'{destinations_layer or origins_layer}' has no usable destination."}
    if len(dest_items) > MAX_DESTINATIONS:
        return {"error": f"{len(dest_items):,} destinations is more than the {MAX_DESTINATIONS:,} this screening accepts; filter or aggregate them first."}

    try:
        from qgis.analysis import (QgsGraphAnalyzer, QgsGraphBuilder, QgsNetworkDistanceStrategy, QgsNetworkSpeedStrategy,
                                   QgsVectorLayerDirector)
        ellipsoid = lt._network_context().ellipsoid()
        direction_idx = network.fields().indexOf(direction_field) if direction_field else -1
        director = QgsVectorLayerDirector(network, direction_idx, value_forward if direction_field else "",
                                          value_backward if direction_field else "", value_both if direction_field else "",
                                          lt._director_both_directions(QgsVectorLayerDirector))
        if strategy == "fastest":
            speed_idx = network.fields().indexOf(speed_field) if speed_field else -1
            director.addStrategy(QgsNetworkSpeedStrategy(speed_idx, float(default_speed), lt._KMH_TO_MS))
        else:
            director.addStrategy(QgsNetworkDistanceStrategy())
        origin_xys = [lt._point_xy_in_network_crs(f.geometry().asPoint(), origins.crs(), network) for f, _w in usable]
        builder = QgsGraphBuilder(network.crs(), True, 0.0, ellipsoid)
        tied = director.makeGraph(builder, [QgsPointXY(p) for p in origin_xys])
        graph = builder.graph()
    except Exception as e:
        return {"error": f"analyze_critical_links could not build the road graph: {e}"}
    n = graph.vertexCount()
    if n == 0:
        return {"error": "The road network produced an empty graph."}

    # Snap destinations to the nearest graph vertex, measured in metres (ellipsoidal) so max_snap_m means the same on any CRS.
    index = QgsSpatialIndex()
    pts = []
    for v in range(n):
        p = graph.vertex(v).point()
        pts.append(p)
        feat = QgsFeature(v)
        feat.setGeometry(QgsGeometry.fromPointXY(p))
        index.addFeature(feat)
    area = QgsDistanceArea()
    area.setSourceCrs(network.crs(), QgsProject.instance().transformContext())
    area.setEllipsoid(ellipsoid)
    dest_weight_at, snapped_far, max_snap_seen = {}, 0, 0.0
    for f, w in dest_items:
        xy = lt._point_xy_in_network_crs(f.geometry().asPoint(), destinations.crs(), network)
        best = None
        for v in index.nearestNeighbor(QgsPointXY(xy), 4):
            d = area.measureLine(QgsPointXY(xy), pts[v])
            if best is None or d < best[0]:
                best = (d, v)
        if best is None or best[0] > max_snap_m:
            snapped_far += 1
            continue
        max_snap_seen = max(max_snap_seen, best[0])
        dest_weight_at[best[1]] = dest_weight_at.get(best[1], 0.0) + w
    if not dest_weight_at:
        return {"error": f"No destination is within {max_snap_m:g} m of the road network, so there is nothing to route to."}

    load_by_edge, origins_done, reached_total, unreached_total, stopped = {}, 0, 0.0, 0.0, False
    for (feat, o_weight), t in zip(usable, tied):
        if time.monotonic() - started > time_budget_s:
            stopped = True
            break
        start = graph.findVertex(t) if t is not None else -1
        if start < 0:
            continue
        tree, costs = QgsGraphAnalyzer.dijkstra(graph, start, 0)
        parents = [(-1 if tree[v] < 0 else graph.edge(tree[v]).fromVertex()) for v in range(n)]
        loads, reached, unreached = accumulate_tree_load(parents, list(costs), dest_weight_at)
        for v, load in loads.items():
            if load > 0:
                k = edge_key(parents[v], v)
                load_by_edge[k] = load_by_edge.get(k, 0.0) + load * o_weight
        reached_total += reached * o_weight
        unreached_total += unreached * o_weight
        origins_done += 1
    if origins_done == 0:
        return {"error": "No origin could be tied into the road network, or the time budget ended before the first origin."}

    layer = QgsVectorLayer(f"LineString?crs={network.crs().authid()}", output_layer_name or "critical_links", "memory")
    layer.dataProvider().addAttributes([QgsField("load", QVariant.Double), QgsField("share", QVariant.Double)])
    layer.updateFields()
    total = max(load_by_edge.values()) if load_by_edge else 0.0
    feats = []
    for (a, b), load in load_by_edge.items():
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPolylineXY([pts[a], pts[b]]))
        f.setAttribute("load", float(load))
        f.setAttribute("share", float(load / total) if total else 0.0)
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    bounds = classify_loads(list(load_by_edge.values()))
    name = output_layer_name or "critical_links"
    if bounds:
        _style(layer, bounds)
    lt._replace_named_layer(name, layer)

    ranked = sorted(load_by_edge.items(), key=lambda kv: -kv[1])[:top_n]
    top = []
    for (a, b), load in ranked:
        top.append({"load": round(load, 4), "share_of_heaviest": round(load / total, 4) if total else 0.0,
                    "length_m": round(area.measureLine(pts[a], pts[b]), 1), "from_x": round(pts[a].x(), 6), "from_y": round(pts[a].y(), 6), "to_x": round(pts[b].x(), 6), "to_y": round(pts[b].y(), 6)})
    result = {
        "success": True,
        "screening_note": ("Shows how many shortest routes depend on each segment; it is not a closure simulation or a traffic "
                           "forecast. One shortest path per pair; no congestion, convoy size or security."),
        "layer_name": name, "strategy": strategy, "load_unit": "weighted OD pairs" if (origin_weight_field or destination_weight_field) else "OD pairs",
        "origins_used": origins_done, "origins_left_out_by_cap": origins_left_out, "origins_skipped_bad_weight": origin_skipped_weight,
        "destinations_used": len(dest_weight_at), "destinations_too_far_from_road": snapped_far, "destinations_skipped_bad_weight": dest_skipped_weight,
        "max_destination_snap_m": round(max_snap_seen, 1),
        "weight_reached": round(reached_total, 4), "weight_unreachable": round(unreached_total, 4),
        "segments_with_load": len(load_by_edge), "heaviest_segments": top,
        "elapsed_s": round(time.monotonic() - started, 1),
        "map_note": "Roads are drawn in five load classes, light to heavy; segments no route uses are not drawn.",
    }
    if stopped:
        result["partial"] = True
        result["partial_note"] = (f"The {time_budget_s:g}s time budget ended after {origins_done} of {len(usable)} origins; the loads "
                                  "cover only those origins. Raise time_budget_s, use fewer origins or clip the network.")
    if origins_left_out:
        result["cap_note"] = f"{origins_left_out} origin(s) beyond max_origins={max_origins} were left out."
    result.update(lt._closed_note(closed))
    return result
