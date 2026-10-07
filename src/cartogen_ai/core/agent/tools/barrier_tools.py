# -*- coding: utf-8 -*-
"""
Road barriers for the routing tools (H1, docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md).

Destroyed bridges, checkpoints and flooded stretches are the first thing a logistics planner needs to put into a network
analysis. calculate_service_area / travel_time_matrix / optimize_delivery_route already take a `speed_field` (km/h per segment);
this tool writes such a field: every road segment within `buffer_m` metres of a barrier (points, lines or polygons such as a
flood extent) gets its speed multiplied by `penalty_factor` (block = the segment is closed and removed from the network), every other segment keeps its base speed.

What "block" means (audit F19, #155; owner decision 2026-10-04: blocked roads are removed from the network). A blocked segment is
written as _network_closure.CLOSED_SPEED_KMH (a negative speed); calculate_service_area / travel_time_matrix /
optimize_delivery_route then route on a copy of the network WITHOUT those segments, whatever the strategy, so nothing can cross
them. 'penalise' is a slow-down only and is read just like any other speed, i.e. with strategy='fastest'. Both are repeated in
the tool's result.

Distances are measured in a metric (UTM) CRS chosen from the data, never in degrees. The pure helpers are unit tested offline;
the layer work needs real QGIS and is covered by tests/test_barrier_tools_live.py in CI (written without a local QGIS).
"""
import math

from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value
from ._network_closure import CLOSED_SPEED_KMH

try:
    from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsSpatialIndex)
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_SLOW_FLOOR_KMH = 0.1         # a slowed ('penalise') segment never goes below this; same floor as impedance_tools
_DEFAULT_SPEED_KMH = 30.0     # same default as impedance_tools._DEFAULT_BASE_SPEED_KMH
MODES = ("block", "penalise")


# ---------------------------------------------------------------- pure --

def utm_epsg(lon, lat):
    """EPSG code of the UTM zone containing (lon, lat) in degrees. Pure. Polar caps (beyond 84N / 80S) fall back to the
    nearest zone, where UTM is poor; callers cannot do better without a polar CRS, which is out of scope here."""
    zone = int(math.floor((lon + 180.0) / 6.0)) % 60 + 1
    return (32600 if lat >= 0 else 32700) + zone


def effective_speed(base_speed, hit, mode, penalty_factor):
    """Speed (km/h) for one segment. Pure. A hit in 'block' mode is closed (CLOSED_SPEED_KMH); in 'penalise' mode the base speed
    times penalty_factor, never below the slow floor; a miss keeps the base speed unchanged. A segment that is already closed
    stays closed."""
    if base_speed < 0:
        return CLOSED_SPEED_KMH
    if not hit:
        return base_speed
    if mode == "block":
        return CLOSED_SPEED_KMH
    return max(_SLOW_FLOOR_KMH, base_speed * penalty_factor)


def validate_options(mode, buffer_m, penalty_factor):
    """Error text for invalid options, else None. Pure."""
    if mode not in MODES:
        return f"mode must be one of {list(MODES)}."
    try:
        if float(buffer_m) < 0:
            return "buffer_m must be zero or positive (metres)."
    except (TypeError, ValueError):
        return "buffer_m must be a number (metres)."
    if mode == "penalise":
        try:
            pf = float(penalty_factor)
        except (TypeError, ValueError):
            return "penalty_factor must be a number between 0 and 1."
        if not 0.0 < pf < 1.0:
            return "penalty_factor must be greater than 0 and less than 1 (e.g. 0.25 = a quarter of the speed)."
    return None


def _result_notes(mode, speed_field_used):
    notes = ["Pass the output field as speed_field to calculate_service_area / travel_time_matrix / optimize_delivery_route."]
    if mode == "block":
        notes.append("Blocked segments are removed from the network for any strategy ('shortest' or 'fastest'): nothing can "
                     "cross them. If every segment were blocked the routing tools report that there is no network.")
    else:
        notes.append("Slowed segments only change the result with strategy='fastest'; with 'shortest' the speed field is not "
                     "read for the cost.")
    if not speed_field_used:
        notes.append(f"No speed_field was given, so every unaffected segment is {_DEFAULT_SPEED_KMH:g} km/h. Run "
                     "build_composite_impedance_field first and pass its output as speed_field for realistic base speeds.")
    return notes


# ---------------------------------------------------------------- QGIS --

def _layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _local_metric_crs(layer):
    """A UTM CRS for the middle of the layer's extent (for metre distances)."""
    from qgis.core import QgsPointXY
    c = layer.extent().center()
    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    centre = QgsCoordinateTransform(layer.crs(), wgs, QgsProject.instance()).transform(QgsPointXY(c.x(), c.y()))
    return QgsCoordinateReferenceSystem(f"EPSG:{utm_epsg(centre.x(), centre.y())}")


def _to_crs(geom, src, dst):
    """Transformed COPY of a geometry (QgsGeometry.transform mutates in place and its return type differs across QGIS versions)."""
    from qgis.core import QgsGeometry
    out = QgsGeometry(geom)
    if src != dst:
        out.transform(QgsCoordinateTransform(src, dst, QgsProject.instance()))
    return out


def affected_feature_ids(network, barriers, buffer_m):
    """Ids of road features within buffer_m metres of any barrier geometry. A spatial index over the roads (in their own CRS) finds
    candidates cheaply; the exact test runs in a metric CRS."""
    metric = _local_metric_crs(network)
    index = QgsSpatialIndex(network.getFeatures())
    hit = set()
    for b in barriers.getFeatures():
        g = b.geometry()
        if g is None or g.isEmpty():
            continue
        g_metric = _to_crs(g, barriers.crs(), metric)
        zone = g_metric.buffer(float(buffer_m), 8) if buffer_m > 0 else g_metric
        zone_net = _to_crs(zone, metric, network.crs())
        for fid in index.intersects(zone_net.boundingBox()):
            if fid in hit:
                continue
            road = network.getFeature(fid).geometry()
            if road is None or road.isEmpty():
                continue
            if _to_crs(road, network.crs(), metric).distance(zone) <= 0.0:
                hit.add(fid)
    return hit


def _affected_layer(network, hit, mode, speed_field, name):
    """A separate layer holding only the affected road segments, drawn red (blocked) or orange (slowed), so the effect of the
    barriers is visible on the map without restyling the user's road layer. Replaces an earlier layer of the same name. Returns
    the layer name, or None (cosmetic: never fails the tool)."""
    try:
        from qgis.core import QgsFeature, QgsVectorLayer, QgsWkbTypes
        from . import logistics_tools as _lt
        # Audit A02: replace only an earlier layer of ours; a user's own layer with this name is renamed, not removed.
        _lt.set_aside_user_layers(name)
        for old in QgsProject.instance().mapLayersByName(name):
            if _lt.is_plugin_result(old):
                QgsProject.instance().removeMapLayer(old.id())
        out = QgsVectorLayer(f"{QgsWkbTypes.displayString(network.wkbType())}?crs={network.crs().authid()}"
                             f"&field=source_id:integer&field={speed_field}:double", name, "memory")
        feats = []
        for fid in sorted(hit):
            src = network.getFeature(fid)
            f = QgsFeature(out.fields())
            f.setGeometry(src.geometry())
            f.setAttributes([fid, src[speed_field]])
            feats.append(f)
        out.dataProvider().addFeatures(feats)
        out.updateExtents()
        _lt.mark_plugin_result(out)
        QgsProject.instance().addMapLayer(out)
        from .humanitarian_style import style_barrier_segments
        style_barrier_segments(out, mode)
        return name
    except Exception:
        return None


@register_tool(
    "apply_network_barriers",
    "Put blocked or degraded places into a road network for routing: destroyed bridges, checkpoints, flooded stretches or any "
    "other barrier layer (points, lines or polygons such as a flood extent). Every road segment within buffer_m metres of a "
    "barrier is blocked (mode='block') or has its speed multiplied by penalty_factor (mode='penalise'); all other segments keep "
    "their speed. Writes the result to a new numeric speed field (km/h) on the road layer, and draws the affected segments as a "
    "separate red (blocked) or orange (slowed) layer '<roads>_barrier_affected' so the effect is visible on the map; pass that field as speed_field to "
    "calculate_service_area / travel_time_matrix / optimize_delivery_route. Blocked segments are REMOVED from the network by "
    "those tools (any strategy), so nothing can cross them; slowed segments only matter with strategy='fastest'. Pass speed_field (e.g. from build_composite_impedance_field) to keep realistic base speeds; without it "
    "unaffected segments are 30 km/h.",
    {
        "type": "object",
        "properties": {
            "road_network_layer": {"type": "string", "description": "Line layer representing the road network."},
            "barrier_layer": {"type": "string", "description": "Layer of barriers: points (bridge, checkpoint), lines or polygons (flood extent)."},
            "buffer_m": {"type": "number", "description": "Distance in metres around each barrier within which roads are affected. 0 = only roads that touch/cross the barrier. Default 50."},
            "mode": {"type": "string", "enum": list(MODES), "description": "'block' (default) or 'penalise'."},
            "penalty_factor": {"type": "number", "description": "For mode='penalise': speed multiplier between 0 and 1 (e.g. 0.25). Ignored for 'block'."},
            "speed_field": {"type": "string", "description": "Optional existing numeric speed field (km/h) to start from, e.g. from build_composite_impedance_field."},
            "output_field": {"type": "string", "description": "Name of the new speed field. Default 'barrier_speed'."},
        },
        "required": ["road_network_layer", "barrier_layer"],
    },
)
def apply_network_barriers(road_network_layer, barrier_layer, buffer_m=50, mode="block", penalty_factor=0.25,
                           speed_field=None, output_field="barrier_speed"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = validate_options(mode, buffer_m, penalty_factor)
    if problem:
        return {"error": problem}
    network = _layer(road_network_layer)
    if network is None:
        return {"error": f"Layer '{road_network_layer}' not found"}
    barriers = _layer(barrier_layer)
    if barriers is None:
        return {"error": f"Layer '{barrier_layer}' not found"}
    if not hasattr(network, "fields") or not hasattr(barriers, "getFeatures"):
        return {"error": "Both layers must be vector layers."}
    if barriers.featureCount() == 0:
        return {"error": f"Barrier layer '{barrier_layer}' has no features, so there is nothing to apply."}
    if speed_field is not None and network.fields().indexOf(speed_field) < 0:
        return {"error": f"Field '{speed_field}' not found in '{road_network_layer}'"}
    if output_field == speed_field:
        return {"error": "output_field must differ from speed_field so the original speeds are kept."}

    try:
        hit = affected_feature_ids(network, barriers, float(buffer_m))
    except Exception as e:
        return {"error": f"apply_network_barriers could not measure distances: {e}"}

    non_numeric = 0
    try:
        with edit_command(network, "Cartogen AI: write " + output_field) as owned:
            out_idx = add_numeric_field(network, output_field)
            for feat in network.getFeatures():
                base = _DEFAULT_SPEED_KMH
                if speed_field is not None:
                    try:
                        base = float(feat.attribute(speed_field))
                        if base < 0:
                            pass                        # already closed by an earlier barrier run: stays closed
                        elif not base > 0:
                            raise ValueError
                    except (TypeError, ValueError):
                        non_numeric += 1
                        base = _DEFAULT_SPEED_KMH
                set_value(network, feat.id(), out_idx,
                          effective_speed(base, feat.id() in hit, mode, float(penalty_factor)))
    except EditError as e:
        return {"error": f"apply_network_barriers failed, nothing was changed: {e}"}
    except Exception as e:
        return {"error": f"apply_network_barriers failed: {e}"}

    result = {
        "success": True,
        "layer_name": road_network_layer,
        "output_field": output_field,
        "mode": mode,
        "buffer_m": float(buffer_m),
        "barrier_features": barriers.featureCount(),
        "road_segments": network.featureCount(),
        "segments_affected": len(hit),
        "notes": _result_notes(mode, speed_field is not None),
    }
    if hit:
        shown = _affected_layer(network, hit, mode, output_field, f"{road_network_layer}_barrier_affected")
        if shown:
            result["affected_layer"] = shown
    if non_numeric:
        result["warning"] = (f"{non_numeric} segment(s) had a missing, non-numeric or non-positive value in '{speed_field}' and "
                             f"were treated as {_DEFAULT_SPEED_KMH:g} km/h.")
    if not hit:
        result["warning"] = (result.get("warning", "") + " No road segment is within the buffer of any barrier -- check that the "
                             "layers overlap and that buffer_m is in metres.").strip()
    if not owned:
        result["note"] = ("The layer is already in edit mode, so the new values are in your edit session and are NOT saved: "
                          "save or discard the layer edits yourself.")
    return result
