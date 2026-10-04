# -*- coding: utf-8 -*-
"""
Road barriers for the routing tools (H1, docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md).

Destroyed bridges, checkpoints and flooded stretches are the first thing a logistics planner needs to put into a network
analysis. calculate_service_area / travel_time_matrix / optimize_delivery_route already take a `speed_field` (km/h per segment);
this tool writes such a field: every road segment within `buffer_m` metres of a barrier (points, lines or polygons such as a
flood extent) gets its speed multiplied by `penalty_factor` (block = a near-zero speed), every other segment keeps its base speed.

What "block" really means. A routing algorithm cannot be told "closed" through a speed field; a blocked segment gets
_BLOCKED_SPEED_KMH, a finite, very slow speed (the same floor impedance_tools uses), so a route only crosses it when no other
way exists within the limit. And a speed field is only read when the downstream tool is run with strategy='fastest' -- with
'shortest' it is ignored and the barriers have NO effect. Both are repeated in the tool's result.

Distances are measured in a metric (UTM) CRS chosen from the data, never in degrees. The pure helpers are unit tested offline;
the layer work needs real QGIS and is covered by tests/test_barrier_tools_live.py in CI (written without a local QGIS).
"""
import math

from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value

try:
    from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsSpatialIndex)
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_BLOCKED_SPEED_KMH = 0.1      # same floor as impedance_tools._MIN_EFFECTIVE_SPEED_KMH
_DEFAULT_SPEED_KMH = 30.0     # same default as impedance_tools._DEFAULT_BASE_SPEED_KMH
MODES = ("block", "penalise")


# ---------------------------------------------------------------- pure --

def utm_epsg(lon, lat):
    """EPSG code of the UTM zone containing (lon, lat) in degrees. Pure. Polar caps (beyond 84N / 80S) fall back to the
    nearest zone, where UTM is poor; callers cannot do better without a polar CRS, which is out of scope here."""
    zone = int(math.floor((lon + 180.0) / 6.0)) % 60 + 1
    return (32600 if lat >= 0 else 32700) + zone


def effective_speed(base_speed, hit, mode, penalty_factor):
    """Speed (km/h) for one segment. Pure. A hit in 'block' mode gets the blocked floor; in 'penalise' mode the base speed times
    penalty_factor, never below the floor; a miss keeps the base speed unchanged."""
    if not hit:
        return base_speed
    if mode == "block":
        return _BLOCKED_SPEED_KMH
    return max(_BLOCKED_SPEED_KMH, base_speed * penalty_factor)


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
    notes = ["Pass the output field as speed_field with strategy='fastest' to calculate_service_area / travel_time_matrix / "
             "optimize_delivery_route. With strategy='shortest' the speed field is ignored and the barriers have no effect."]
    if mode == "block":
        notes.append(f"A blocked segment gets {_BLOCKED_SPEED_KMH} km/h, not a true closure: a route can still cross it if there is no "
                     "other way within the limit.")
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


@register_tool(
    "apply_network_barriers",
    "Put blocked or degraded places into a road network for routing: destroyed bridges, checkpoints, flooded stretches or any "
    "other barrier layer (points, lines or polygons such as a flood extent). Every road segment within buffer_m metres of a "
    "barrier is blocked (mode='block') or has its speed multiplied by penalty_factor (mode='penalise'); all other segments keep "
    "their speed. Writes the result to a new numeric speed field (km/h) on the road layer; pass that field as speed_field to "
    "calculate_service_area / travel_time_matrix / optimize_delivery_route with strategy='fastest'. IMPORTANT: with "
    "strategy='shortest' the speed field is ignored and barriers have no effect, and 'block' is a near-zero speed rather than "
    "a true closure. Pass speed_field (e.g. from build_composite_impedance_field) to keep realistic base speeds; without it "
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
                        if not base > 0:
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
