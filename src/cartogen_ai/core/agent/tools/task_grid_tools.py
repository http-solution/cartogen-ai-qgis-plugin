# -*- coding: utf-8 -*-
"""
Mapping task grid for remote/crowd mapping (H2, docs/HUMANITARIAN_WORKFLOW_GAP_ANALYSIS_2026-10-04.md).

Splits an area of interest into square tasks so many remote mappers can work on one area without overlapping (the HOT Tasking
Manager / MapSwipe way of working). The tool builds the grid in a local metric (UTM) CRS so cells really are `cell_size_m` wide,
clips cells to the area (dropping slivers below _MIN_CELL_FRACTION of a full cell), optionally ranks them by a priority value
(a count of points from another layer, or the sum of a population raster) as High / Medium / Low terciles, and can write the
tasks as GeoJSON in EPSG:4326.

Not verified: that the exported GeoJSON imports cleanly into a particular Tasking Manager instance (its import rules were not
checked from here); it is a plain FeatureCollection of polygons with task_id / area_km2 / value / priority properties. The pure
grid, ranking and GeoJSON logic is unit tested offline; the layer work needs QGIS and has a live test (tests/test_task_grid_tools_live.py,
written without a local QGIS).
"""
import json
import math
import os
import tempfile

from .registry import register_tool

try:
    from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsGeometry,
                           QgsProject, QgsRectangle, QgsSpatialIndex, QgsVectorLayer)
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

MAX_TASKS = 5000
MIN_CELL_SIZE_M = 100.0
_MIN_CELL_FRACTION = 0.05
PRIORITY_LABELS = ("High", "Medium", "Low")


# ---------------------------------------------------------------- pure --

def validate_options(cell_size_m, max_tasks=MAX_TASKS):
    """Error text for an invalid cell size, else None. Pure."""
    try:
        size = float(cell_size_m)
    except (TypeError, ValueError):
        return "cell_size_m must be a number (metres)."
    if size < MIN_CELL_SIZE_M:
        return f"cell_size_m must be at least {MIN_CELL_SIZE_M:g} m."
    return None


def estimated_cells(width_m, height_m, cell_size_m):
    """Number of grid cells needed to cover a width x height bounding box. Pure."""
    return max(1, math.ceil(width_m / cell_size_m)) * max(1, math.ceil(height_m / cell_size_m))


def grid_cells(xmin, ymin, xmax, ymax, cell_size):
    """Square cells covering the box, row-major from the south-west corner: dicts with col, row and bounds. Pure."""
    cols = max(1, math.ceil((xmax - xmin) / cell_size))
    rows = max(1, math.ceil((ymax - ymin) / cell_size))
    return [{"col": c, "row": r,
             "bounds": (xmin + c * cell_size, ymin + r * cell_size, xmin + (c + 1) * cell_size, ymin + (r + 1) * cell_size)}
            for r in range(rows) for c in range(cols)]


def task_id(col, row):
    """Stable human-readable task id. Pure."""
    return f"r{row + 1:03d}c{col + 1:03d}"


def priority_classes(values):
    """High / Medium / Low by tercile rank of `values` (None entries get None); higher value = higher priority. Equal values
    always share a class, so a layer where everything is equal is all 'High' rather than an arbitrary split. Pure."""
    present = sorted({v for v in values if v is not None}, reverse=True)
    if not present:
        return [None] * len(values)
    ordered = sorted((v for v in values if v is not None), reverse=True)
    n = len(ordered)
    cut_high = ordered[max(0, math.ceil(n / 3) - 1)]
    cut_medium = ordered[max(0, math.ceil(2 * n / 3) - 1)]
    out = []
    for v in values:
        if v is None:
            out.append(None)
        elif v >= cut_high:
            out.append(PRIORITY_LABELS[0])
        elif v >= cut_medium:
            out.append(PRIORITY_LABELS[1])
        else:
            out.append(PRIORITY_LABELS[2])
    return out


def to_geojson(features):
    """GeoJSON FeatureCollection text from [(geometry_dict, properties_dict), ...]. Pure."""
    return json.dumps({"type": "FeatureCollection",
                       "features": [{"type": "Feature", "geometry": g, "properties": p} for g, p in features]},
                      ensure_ascii=False)


# ---------------------------------------------------------------- QGIS --

def _layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _transform(src, dst):
    return QgsCoordinateTransform(src, dst, QgsProject.instance())


def _copy_transformed(geom, src, dst):
    out = QgsGeometry(geom)
    if src != dst:
        out.transform(_transform(src, dst))
    return out


def _aoi_union(layer):
    geoms = [f.geometry() for f in layer.getFeatures() if f.geometry() is not None and not f.geometry().isEmpty()]
    return QgsGeometry.unaryUnion(geoms) if geoms else None


def _point_counts(cells_metric, points_layer, metric):
    """Number of points of points_layer inside each cell geometry (metric CRS)."""
    index = QgsSpatialIndex()
    pts = {}
    for f in points_layer.getFeatures():
        g = f.geometry()
        if g is None or g.isEmpty():
            continue
        g = _copy_transformed(g.centroid(), points_layer.crs(), metric)   # a point's centroid is the point
        feat = QgsFeature(f.id())
        feat.setGeometry(g)
        index.addFeature(feat)
        pts[f.id()] = g
    counts = []
    for cell in cells_metric:
        n = sum(1 for pid in index.intersects(cell.boundingBox()) if cell.intersects(pts[pid]))
        counts.append(float(n))
    return counts


def _raster_sums(cells_metric, raster_layer, metric):
    """Sum of a raster over each cell through native:zonalstatisticsfb. Returns a list, or raises."""
    import processing
    zones = QgsVectorLayer(f"Polygon?crs={metric.authid()}&field=i:integer", "zones", "memory")
    feats = []
    for i, g in enumerate(cells_metric):
        f = QgsFeature(zones.fields())
        f.setGeometry(g)
        f.setAttributes([i])
        feats.append(f)
    zones.dataProvider().addFeatures(feats)
    result = processing.run("native:zonalstatisticsfb", {
        "INPUT": zones, "INPUT_RASTER": raster_layer, "RASTER_BAND": 1, "COLUMN_PREFIX": "t_", "STATISTICS": [1],
        "OUTPUT": "memory:"})
    out_layer = result["OUTPUT"]
    by_i = {f["i"]: f["t_sum"] for f in out_layer.getFeatures()}
    return [None if by_i.get(i) is None else float(by_i[i]) for i in range(len(cells_metric))]


@register_tool(
    "generate_mapping_task_grid",
    "Split an area of interest into a grid of square mapping tasks for remote or crowd mapping (Tasking Manager style), so "
    "volunteers can digitise roads and buildings without overlapping. Cells are cell_size_m wide (measured in a local metric "
    "projection) and clipped to the area. Optionally ranks tasks High / Medium / Low by how many points of priority_points_layer "
    "fall in each (e.g. damage reports, existing buildings) or by the population in population_raster_layer, so the most "
    "important cells are mapped first. Creates a polygon layer and can write the tasks as GeoJSON (EPSG:4326, properties "
    "task_id, area_km2, value, priority) for import into a tasking tool; it has NOT been checked against a specific Tasking "
    "Manager instance's import rules.",
    {
        "type": "object",
        "properties": {
            "aoi_layer": {"type": "string", "description": "Polygon layer with the area of interest."},
            "cell_size_m": {"type": "number", "description": "Task width in metres (minimum 100). Default 2000."},
            "priority_points_layer": {"type": "string", "description": "Optional point (or other vector) layer; the priority value is the number of its features in each cell."},
            "population_raster_layer": {"type": "string", "description": "Optional population raster; the priority value is the sum of its cells in each task. Ignored if priority_points_layer is given."},
            "output_layer_name": {"type": "string", "description": "Name of the new task layer. Default 'mapping_tasks'."},
            "export_geojson_path": {"type": "string", "description": "Optional file path for the GeoJSON export. Use 'auto' to write into the system temp folder."},
        },
        "required": ["aoi_layer"],
    },
)
def generate_mapping_task_grid(aoi_layer, cell_size_m=2000, priority_points_layer=None, population_raster_layer=None,
                               output_layer_name="mapping_tasks", export_geojson_path=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = validate_options(cell_size_m)
    if problem:
        return {"error": problem}
    size = float(cell_size_m)
    aoi = _layer(aoi_layer)
    if aoi is None:
        return {"error": f"Layer '{aoi_layer}' not found"}
    from qgis.core import QgsWkbTypes
    if not hasattr(aoi, "getFeatures") or "Polygon" not in QgsWkbTypes.displayString(aoi.wkbType()):
        return {"error": f"'{aoi_layer}' must be a polygon layer."}
    points = raster = None
    if priority_points_layer:
        points = _layer(priority_points_layer)
        if points is None or not hasattr(points, "getFeatures"):
            return {"error": f"Vector layer '{priority_points_layer}' not found"}
    elif population_raster_layer:
        raster = _layer(population_raster_layer)
        if raster is None or not hasattr(raster, "bandCount"):
            return {"error": f"Raster layer '{population_raster_layer}' not found"}

    union = _aoi_union(aoi)
    if union is None:
        return {"error": f"'{aoi_layer}' has no usable polygons."}

    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    centre = _transform(aoi.crs(), wgs).transform(union.boundingBox().center())
    from .barrier_tools import utm_epsg
    metric = QgsCoordinateReferenceSystem(f"EPSG:{utm_epsg(centre.x(), centre.y())}")
    union_m = _copy_transformed(union, aoi.crs(), metric)
    box = union_m.boundingBox()
    needed = estimated_cells(box.width(), box.height(), size)
    if needed > MAX_TASKS * 4:
        return {"error": f"A {size:g} m grid over this area needs about {needed} cells, far above the {MAX_TASKS} task limit. "
                         "Use a larger cell_size_m."}

    full_area = size * size
    kept = []
    for cell in grid_cells(box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum(), size):
        x0, y0, x1, y1 = cell["bounds"]
        square = QgsGeometry.fromRect(QgsRectangle(x0, y0, x1, y1))
        piece = square.intersection(union_m)
        if piece is None or piece.isEmpty() or piece.area() < _MIN_CELL_FRACTION * full_area:
            continue
        kept.append((cell, piece))
    if not kept:
        return {"error": "The grid produced no tasks; check the area and cell_size_m."}
    if len(kept) > MAX_TASKS:
        return {"error": f"This would create {len(kept)} tasks, above the limit of {MAX_TASKS}. Use a larger cell_size_m."}

    pieces = [p for _c, p in kept]
    values, value_note = [None] * len(kept), None
    try:
        if points is not None:
            values = _point_counts(pieces, points, metric)
            value_note = f"number of '{priority_points_layer}' features per task"
        elif raster is not None:
            values = _raster_sums(pieces, raster, metric)
            value_note = f"sum of '{population_raster_layer}' per task"
    except Exception as e:
        values = [None] * len(kept)
        value_note = None
        priority_warning = f"Priority could not be computed ({e}); tasks are unranked."
    else:
        priority_warning = None
    classes = priority_classes(values)

    out = QgsVectorLayer("Polygon?crs=EPSG:4326&field=task_id:string&field=area_km2:double&field=value:double&field=priority:string",
                         output_layer_name, "memory")
    to_wgs = _transform(metric, wgs)
    features, geojson = [], []
    for (cell, piece), value, klass in zip(kept, values, classes):
        geom = QgsGeometry(piece)
        geom.transform(to_wgs)
        props = {"task_id": task_id(cell["col"], cell["row"]), "area_km2": round(piece.area() / 1e6, 4),
                 "value": value, "priority": klass}
        f = QgsFeature(out.fields())
        f.setGeometry(geom)
        f.setAttributes([props["task_id"], props["area_km2"], value, klass])
        features.append(f)
        geojson.append((json.loads(geom.asJson(6)), props))
    out.dataProvider().addFeatures(features)
    out.updateExtents()
    QgsProject.instance().addMapLayer(out)

    result = {
        "success": True,
        "layer_name": output_layer_name,
        "task_count": len(features),
        "cell_size_m": size,
        "metric_crs": metric.authid(),
        "note": f"Edge cells are clipped to the area; clipped slivers under {int(_MIN_CELL_FRACTION * 100)}% of a full cell are dropped.",
    }
    if value_note:
        result["priority_basis"] = value_note
    if priority_warning:
        result["warning"] = priority_warning
    if export_geojson_path:
        path = export_geojson_path
        if path == "auto":
            path = os.path.join(tempfile.gettempdir(), f"{output_layer_name}.geojson")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(to_geojson(geojson))
            result["geojson_path"] = path
            result["geojson_note"] = ("Plain GeoJSON polygons in EPSG:4326; not checked against a specific Tasking Manager "
                                      "instance's import rules.")
        except OSError as e:
            result["warning"] = (result.get("warning", "") + f" GeoJSON could not be written: {e}").strip()
    return result
