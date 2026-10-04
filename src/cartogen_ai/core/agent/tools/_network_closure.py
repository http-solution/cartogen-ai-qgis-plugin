# -*- coding: utf-8 -*-
"""Closed road segments for the routing tools (audit F19, #155).

A speed field cannot say "closed" to QGIS's routing algorithms: the old blocked speed was a finite 0.1 km/h, so a route or
service area could still cross a "blocked" road when there was no alternative or the limit was generous. Owner decision
(2026-10-04): a blocked road is REMOVED from the network, for every routing tool.

How a closure is marked. A segment is closed when its speed field holds a NEGATIVE number (CLOSED_SPEED_KMH, -1). Zero is NOT
a closure: in real OSM extracts `maxspeed` is 0 or empty on well over 99% of roads and means "unset" (see
logistics_tools.MIN_USABLE_SPEED_SHARE), so reading 0 as closed would delete almost every road in an ordinary network. Only
the tools that decide a closure (apply_network_barriers mode 'block', build_composite_impedance_field passability 0) write the
sentinel. NULL and non-numeric values stay "unknown", never closed.

routable_network() applies it: if any segment is closed it returns a scratch copy of the network without them (the user's layer
is never edited), and says how many were removed. The same rule applies whatever the routing strategy, because a closed road is
closed whether the user asked for the shortest or the fastest route.
"""
CLOSED_SPEED_KMH = -1.0


def is_closed(value):
    """True when a speed-field value marks the segment closed (a negative number). Pure."""
    try:
        return value is not None and float(value) < 0
    except (TypeError, ValueError):
        return False


def routable_network(network, speed_field):
    """(layer, closed_count, error). `layer` is `network` itself when nothing is closed, else a memory copy without the
    closed segments. `error` is text when EVERY segment is closed (nothing can be routed), else None. Needs QGIS."""
    if not speed_field or network.fields().indexOf(speed_field) < 0:
        return network, 0, None
    closed_ids, total = set(), 0
    for feat in network.getFeatures():
        total += 1
        if is_closed(feat[speed_field]):
            closed_ids.add(feat.id())
    if not closed_ids:
        return network, 0, None
    if len(closed_ids) >= total:
        return None, len(closed_ids), (
            f"Every road segment is closed in '{speed_field}' (negative speed), so there is no network to route on. "
            "Reopen some roads, or run apply_network_barriers / build_composite_impedance_field again with a smaller area.")
    from qgis.core import QgsFeature, QgsVectorLayer, QgsWkbTypes
    geometry = QgsWkbTypes.displayString(network.wkbType())
    scratch = QgsVectorLayer(f"{geometry}?crs={network.crs().authid()}", f"{network.name()}_open_roads", "memory")
    provider = scratch.dataProvider()
    provider.addAttributes(list(network.fields()))
    scratch.updateFields()
    kept = []
    for feat in network.getFeatures():
        if feat.id() in closed_ids:
            continue
        copy = QgsFeature(scratch.fields())
        copy.setGeometry(feat.geometry())
        copy.setAttributes(feat.attributes())
        kept.append(copy)
    provider.addFeatures(kept)
    scratch.updateExtents()
    return scratch, len(closed_ids), None
