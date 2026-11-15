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
import tempfile

from ... import _chunked as _ck
from ._paths import safe_file_stem, unique_path
from .registry import register_tool
from ._layer_checks import require_valid_layer

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


_SIZE_STEPS = (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8)      # times a power of ten: round sizes a person can say, remember and plan field work around
_LARGEST_SIZE_M = 10_000_000


def size_ladder():
    """The round cell sizes (metres) a refusal may suggest, increasing from MIN_CELL_SIZE_M: 100, 150, 200, 250, 300, 400, 500, 600, 800, 1000, ... Pure."""
    sizes, power = [], 100
    while power <= _LARGEST_SIZE_M:
        sizes.extend(step * power for step in _SIZE_STEPS)
        power *= 10
    return [int(s) if float(s).is_integer() else s for s in sizes if s >= MIN_CELL_SIZE_M]


def size_text(size_m):
    """'500 m', '1 km', '2.5 km', '15 km'. Pure."""
    return f"{size_m:g} m" if size_m < 1000 else f"{size_m / 1000:g} km"


def suggest_cell_size(width_m, height_m, cell_size_m, limit=MAX_TASKS):
    """(size, cells): the smallest round size not below `cell_size_m` whose grid over a width x height box has at most `limit` cells, and that cell count; the
    size asked for when it already fits; (None, None) when no size up to the largest fits. The count is for the bounding box, so it is an upper bound for an
    irregular outline. Pure."""
    if estimated_cells(width_m, height_m, cell_size_m) <= limit:
        return cell_size_m, estimated_cells(width_m, height_m, cell_size_m)
    for size in size_ladder():
        if size >= cell_size_m:
            cells = estimated_cells(width_m, height_m, size)
            if cells <= limit:
                return size, cells
    return None, None


def suggest_size_from_count(cell_size_m, task_count, limit=MAX_TASKS):
    """(size, about how many tasks) when a grid made `task_count` tasks at `cell_size_m` and the limit is `limit`. Tasks go with one over the size squared,
    so the size must grow by the square root of the excess; the count is about, because cells along the outline do not scale exactly. (None, None) if none fits. Pure."""
    needed = cell_size_m * (task_count / limit) ** 0.5
    for size in size_ladder():
        if size >= needed and size > cell_size_m:
            return size, max(1, round(task_count * (cell_size_m / size) ** 2))
    return None, None


_PART_AT_A_TIME = "Or make the grid for part of the area at a time (aoi_where picks which features of the area layer to use)."


def too_many_cells_message(cell_size_m, needed, width_m, height_m):
    """The refusal when the bounding box alone needs far more cells than the limit, with a size that would work and the other way out. Pure."""
    size, cells = suggest_cell_size(width_m, height_m, cell_size_m)
    head = f"A {size_text(cell_size_m)} grid over this area needs about {needed:,} cells, far above the {MAX_TASKS:,} task limit. No grid was made. "
    if size is None:
        return head + "Use a larger cell_size_m. " + _PART_AT_A_TIME
    return (head + f"Use a larger cell_size_m: {size_text(size)} gives at most about {cells:,} cells (fewer once the grid is cut to the area's outline). "
            + _PART_AT_A_TIME)


def refusal_result(cell_size_m, needed, width_m, height_m):
    """The error result for too_many_cells_message, with the suggestion as numbers the assistant can offer back. Pure."""
    found = {"error": too_many_cells_message(cell_size_m, needed, width_m, height_m)}
    size, cells = suggest_cell_size(width_m, height_m, cell_size_m)
    if size is not None:
        found.update({"suggested_cell_size_m": size, "suggested_cells": cells})
    return found


def too_many_tasks_result(cell_size_m, task_count):
    """The error result when the grid, after cutting to the outline, made more than MAX_TASKS tasks. Pure."""
    size, about = suggest_size_from_count(cell_size_m, task_count)
    head = f"This would create {task_count:,} tasks, above the limit of {MAX_TASKS:,}. No grid was made. "
    if size is None:
        return {"error": head + "Use a larger cell_size_m. " + _PART_AT_A_TIME}
    return {"error": head + f"Use a larger cell_size_m: {size_text(size)} would give about {about:,} tasks. " + _PART_AT_A_TIME,
            "suggested_cell_size_m": size, "suggested_cells": about}


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


def _aoi_union(layer, where=None):
    """Union of the area's polygons; `where` (a QGIS expression) keeps only matching features so the source layer need not be filtered."""
    from qgis.core import QgsExpression
    expression = QgsExpression(where) if where else None
    if expression is not None and expression.hasParserError():
        raise ValueError(f"aoi_where is not a valid QGIS expression: {expression.parserErrorString()}")
    from qgis.core import QgsExpressionContext, QgsExpressionContextUtils
    context = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(layer)) if expression is not None else None
    geoms = []
    for f in _ck.features(layer, "Task grid: reading features"):
        if f.geometry() is None or f.geometry().isEmpty():
            continue
        if expression is not None:
            context.setFeature(f)
            if not expression.evaluate(context):
                continue
        geoms.append(f.geometry())
    return QgsGeometry.unaryUnion(geoms) if geoms else None


def _aoi_union_or_error(aoi, aoi_layer, aoi_where):
    """(union, None) or (None, {"error": ...}) so the tool body stays a straight line."""
    try:
        union = _aoi_union(aoi, aoi_where)
    except ValueError as e:
        return None, {"error": str(e)}
    if union is None:
        return None, {"error": f"'{aoi_layer}' has no usable polygons" + (f" matching {aoi_where}." if aoi_where else ".")}
    return union, None


def _point_counts(cells_metric, points_layer, metric):
    """Number of points of points_layer inside each cell geometry (metric CRS)."""
    index = QgsSpatialIndex()
    pts = {}
    for f in _ck.features(points_layer, "Task grid: reading features"):
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
    require_valid_layer(zones)
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
    by_i = {f["i"]: f["t_sum"] for f in _ck.features(out_layer, "Task grid: reading features")}
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
            "aoi_where": {"type": "string", "description": "Optional QGIS expression (e.g. \"ADM1_EN\" = 'Aden') limiting the area to matching features of aoi_layer. Use this instead of filtering the source layer, which would hide features from the whole project."},
            "output_layer_name": {"type": "string", "description": "Name of the new task layer. Default 'mapping_tasks'."},
            "export_geojson_path": {"type": "string", "description": "Optional file path for the GeoJSON export. Use 'auto' to write into the system temp folder."},
        },
        "required": ["aoi_layer"],
    },
    # Remote mapping tasks (see tools/task_grid_tools.py). No bare "grid" or "tasks": they appear in unrelated requests.
    keywords=[
        "tasking manager", "mapping task", "task grid", "mapswipe", "remote mapping", "crowd mapping", "mapathon",
        "split the area into", "divide the area into",
        "squares for the mappers", "kilometre squares", "kilometer squares", "km squares", "grid for the mappers",
    ],
)
def generate_mapping_task_grid(aoi_layer, cell_size_m=2000, priority_points_layer=None, population_raster_layer=None,
                               output_layer_name="mapping_tasks", export_geojson_path=None, aoi_where=None):
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

    union, problem = _aoi_union_or_error(aoi, aoi_layer, aoi_where)
    if problem:
        return problem

    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    centre = _transform(aoi.crs(), wgs).transform(union.boundingBox().center())
    from .barrier_tools import utm_epsg
    metric = QgsCoordinateReferenceSystem(f"EPSG:{utm_epsg(centre.x(), centre.y())}")
    union_m = _copy_transformed(union, aoi.crs(), metric)
    box = union_m.boundingBox()
    needed = estimated_cells(box.width(), box.height(), size)
    if needed > MAX_TASKS * 4:
        return refusal_result(size, needed, box.width(), box.height())

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
        return too_many_tasks_result(size, len(kept))

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
    require_valid_layer(out)
    to_wgs = _transform(metric, wgs)
    features, geojson = [], []
    for (cell, piece), value, klass in zip(kept, values, classes, strict=False):
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
    from .humanitarian_style import style_task_grid
    styled = style_task_grid(out)       # priority colours + task ids; cosmetic, never fails the tool

    result = {
        "success": True,
        "styled": styled,
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
            # PLAN-012 item 2: the layer name is model-supplied; it used to go into the path as it was, so "../x" wrote outside the temp
            # folder and a repeat run overwrote the first file.
            path = unique_path(tempfile.gettempdir(), safe_file_stem(output_layer_name, "mapping_tasks"), ".geojson")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(to_geojson(geojson))
            result["geojson_path"] = path
            result["geojson_note"] = ("Plain GeoJSON polygons in EPSG:4326; not checked against a specific Tasking Manager "
                                      "instance's import rules.")
        except OSError as e:
            result["warning"] = (result.get("warning", "") + f" GeoJSON could not be written: {e}").strip()
    return result
