"""M2 (roadmap 2026-10-14): layer groups, map view, project CRS, bookmarks, project properties and measuring.

Why: the coverage audit listed these project-and-map rows as MISSING (no group creation, no scale / extent / rotation control, no
way to set the project CRS, no bookmarks, no measure tool). Before 1.16.0-rc4 a script could do them; each is now a checked tool.

The pure helpers (extent / scale / rotation checks, group-name rules) are unit-tested offline; the tools run in
tests/test_map_view_tools_live.py, whose first CI run is its first execution (written without a QGIS install). Tools that move the
canvas need the QGIS interface and say so when there is none."""
import math

from .registry import register_tool

try:
    from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsDistanceArea, QgsPointXY, QgsProject,
                           QgsRectangle)
    from qgis.utils import iface
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    iface = None

MAX_SCALE_DENOMINATOR = 1e9


def check_scale(scale):
    """(denominator, error). 25000 or '1:25000' both mean 1:25 000."""
    try:
        text = str(scale).strip().lstrip("1").lstrip(":") if str(scale).strip().startswith("1:") else str(scale).strip()
        value = float(text)
    except (TypeError, ValueError):
        return None, f"'{scale}' is not a scale. Give the denominator, for example 25000 for 1:25 000."
    if not (0 < value <= MAX_SCALE_DENOMINATOR) or not math.isfinite(value):
        return None, f"The scale denominator must be between 0 and {MAX_SCALE_DENOMINATOR:g}."
    return value, None


def check_extent(extent):
    """([xmin, ymin, xmax, ymax], error) for a list of four numbers with min < max."""
    try:
        values = [float(v) for v in extent]
    except (TypeError, ValueError):
        return None, "extent must be four numbers: [xmin, ymin, xmax, ymax]."
    if len(values) != 4 or not all(math.isfinite(v) for v in values):
        return None, "extent must be four finite numbers: [xmin, ymin, xmax, ymax]."
    if values[0] >= values[2] or values[1] >= values[3]:
        return None, "extent needs xmin < xmax and ymin < ymax."
    return values, None


def check_rotation(degrees):
    try:
        value = float(degrees)
    except (TypeError, ValueError):
        return None, f"'{degrees}' is not an angle in degrees."
    if not math.isfinite(value):
        return None, "The rotation must be a finite number of degrees."
    return value % 360.0, None


def check_group_name(name):
    text = str(name or "").strip()
    if not text or len(text) > 120:
        return None, "A group needs a name of 1 to 120 characters."
    return text, None


def _crs(text, fallback):
    if not text:
        return fallback, None
    crs = QgsCoordinateReferenceSystem(str(text))
    return (crs, None) if crs.isValid() else (None, f"Unknown crs '{text}'. Use a code such as EPSG:4326.")


def _layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _group(root, name):
    return root.findGroup(name)


# ----------------------------------------------------------------------------------------------------------------------------------
# Layer groups
# ----------------------------------------------------------------------------------------------------------------------------------

@register_tool(
    "create_layer_group",
    "Create a layer group in the layer tree (optionally inside another group) and optionally move layers into it.",
    {"type": "object", "properties": {"group_name": {"type": "string"}, "layer_names": {"type": "array", "items": {"type": "string"}},
                                      "parent_group": {"type": "string"}}, "required": ["group_name"]},
    keywords=[
        "create a group", "new group", "make a group", "create a layer group", "group the layers", "put the layers in a group",
        "put these layers in a group", "layer group",
    ],
)
def create_layer_group(group_name, layer_names=None, parent_group=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    name, err = check_group_name(group_name)
    if err:
        return {"error": err}
    root = QgsProject.instance().layerTreeRoot()
    parent = root
    if parent_group:
        parent = _group(root, parent_group)
        if parent is None:
            return {"error": f"Group '{parent_group}' not found."}
    if _group(root, name) is not None:
        return {"error": f"A group called '{name}' already exists."}
    missing = [n for n in (layer_names or []) if _layer(n) is None]
    if missing:
        return {"error": f"Layer(s) not found: {', '.join(missing)}. Nothing was created."}
    group = parent.addGroup(name)
    moved = _move_into(root, group, layer_names or [])
    return {"success": True, "group_name": name, "layers_moved": moved}


def _move_into(root, group, layer_names):
    moved = []
    for layer_name in layer_names:
        layer = _layer(layer_name)
        node = root.findLayer(layer.id())
        if node is None:
            continue
        group.addLayer(layer)
        node.parent().removeChildNode(node)
        moved.append(layer_name)
    return moved


@register_tool(
    "move_layers_to_group",
    "Move existing layers into an existing layer group.",
    {"type": "object", "properties": {"group_name": {"type": "string"}, "layer_names": {"type": "array", "items": {"type": "string"}}},
     "required": ["group_name", "layer_names"]},
    keywords=[
        "move the layer into the group", "move layers into the group", "add the layer to the group", "move to the group",
    ],
)
def move_layers_to_group(group_name, layer_names):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    root = QgsProject.instance().layerTreeRoot()
    group = _group(root, str(group_name))
    if group is None:
        return {"error": f"Group '{group_name}' not found."}
    missing = [n for n in layer_names if _layer(n) is None]
    if missing:
        return {"error": f"Layer(s) not found: {', '.join(missing)}. Nothing was moved."}
    return {"success": True, "group_name": group_name, "layers_moved": _move_into(root, group, layer_names)}


@register_tool(
    "set_group_options",
    "Show or hide a whole layer group, collapse or expand it, and/or make its layers mutually exclusive (only one visible at a time).",
    {"type": "object", "properties": {"group_name": {"type": "string"}, "visible": {"type": "boolean"}, "expanded": {"type": "boolean"},
                                      "mutually_exclusive": {"type": "boolean"}}, "required": ["group_name"]},
    keywords=[
        "hide the group", "show the group", "collapse the group", "expand the group", "turn off the group", "turn on the group",
        "mutually exclusive", "check the whole group", "uncheck the group",
    ],
)
def set_group_options(group_name, visible=None, expanded=None, mutually_exclusive=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    group = _group(QgsProject.instance().layerTreeRoot(), str(group_name))
    if group is None:
        return {"error": f"Group '{group_name}' not found."}
    if visible is None and expanded is None and mutually_exclusive is None:
        return {"error": "Give at least one of visible, expanded, mutually_exclusive."}
    if mutually_exclusive is not None:
        group.setIsMutuallyExclusive(bool(mutually_exclusive))
    if visible is not None:
        group.setItemVisibilityCheckedRecursive(bool(visible))
    if expanded is not None:
        group.setExpanded(bool(expanded))
    return {"success": True, "group_name": group_name, "visible": group.itemVisibilityChecked(), "expanded": group.isExpanded(),
            "mutually_exclusive": group.isMutuallyExclusive()}


# ----------------------------------------------------------------------------------------------------------------------------------
# Map view
# ----------------------------------------------------------------------------------------------------------------------------------

@register_tool(
    "set_map_view",
    "Move the map canvas: set the scale (denominator, e.g. 25000 for 1:25 000), zoom to an extent [xmin, ymin, xmax, ymax] in crs "
    "(default EPSG:4326), centre on a point [x, y] in crs, and/or rotate the map in degrees. Several can be combined.",
    {"type": "object", "properties": {"scale": {"type": "string"}, "extent": {"type": "array", "items": {"type": "number"}},
                                      "center": {"type": "array", "items": {"type": "number"}}, "crs": {"type": "string"},
                                      "rotation": {"type": "number"}}, "required": []},
    keywords=[
        "zoom to scale", "set the scale", "scale of 1:", "zoom to 1:", "to 1:", "rotate the map", "map rotation", "pan to",
        "pan the map", "centre the map", "center the map", "zoom to the extent", "zoom to coordinates", "zoom to this extent",
    ],
)
def set_map_view(scale=None, extent=None, center=None, crs=None, rotation=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if scale is None and extent is None and center is None and rotation is None:
        return {"error": "Give at least one of scale, extent, center, rotation."}
    denominator = degrees = box = point = None
    if scale is not None:
        denominator, err = check_scale(scale)
        if err:
            return {"error": err}
    if rotation is not None:
        degrees, err = check_rotation(rotation)
        if err:
            return {"error": err}
    if extent is not None and center is not None:
        return {"error": "Give an extent or a centre, not both."}
    if extent is not None:
        box, err = check_extent(extent)
        if err:
            return {"error": err}
    if center is not None:
        try:
            point = [float(center[0]), float(center[1])]
            if len(center) != 2:
                raise ValueError
        except (TypeError, ValueError, IndexError):
            return {"error": "center must be two numbers: [x, y]."}
    if iface is None:
        return {"error": "QGIS interface not available"}
    canvas = iface.mapCanvas()
    source, err = _crs(crs or "EPSG:4326", None)
    if err:
        return {"error": err}
    transform = QgsCoordinateTransform(source, canvas.mapSettings().destinationCrs(), QgsProject.instance())
    try:
        if box is not None:
            canvas.setExtent(transform.transformBoundingBox(QgsRectangle(*box)))
        if point is not None:
            canvas.setCenter(transform.transform(QgsPointXY(*point)))
        if degrees is not None:
            canvas.setRotation(degrees)
        if denominator is not None:
            canvas.zoomScale(denominator)
    except Exception as e:   # a transform failure must come back as a message, not break the turn
        return {"error": f"The map view was not changed: {e}"}
    canvas.refresh()
    return {"success": True, "scale": round(canvas.scale(), 1), "rotation": round(canvas.rotation(), 2),
            "center": [round(canvas.center().x(), 6), round(canvas.center().y(), 6)],
            "map_crs": canvas.mapSettings().destinationCrs().authid()}


# ----------------------------------------------------------------------------------------------------------------------------------
# CRS
# ----------------------------------------------------------------------------------------------------------------------------------

@register_tool(
    "set_project_crs",
    "Set the project (map) CRS, for example EPSG:3857. Layers are reprojected on the fly for display; no layer data is changed.",
    {"type": "object", "properties": {"crs": {"type": "string"}}, "required": ["crs"]},
    keywords=[
        "set the project crs", "project crs", "change the project crs", "set the map crs", "change the map projection",
        "project projection", "set the project projection",
    ],
)
def set_project_crs(crs):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    target, err = _crs(crs, None)
    if err:
        return {"error": err}
    previous = QgsProject.instance().crs().authid()
    QgsProject.instance().setCrs(target)
    return {"success": True, "previous_crs": previous, "project_crs": QgsProject.instance().crs().authid(),
            "note": "Only the display CRS changed; no layer was reprojected."}


@register_tool(
    "assign_layer_crs",
    "Tell QGIS what CRS a layer's coordinates are ALREADY in ('Assign projection'). This does NOT move or reproject the data: choosing "
    "the wrong CRS places the layer in the wrong location. Use only when the layer's CRS is missing or known to be wrong. A preview "
    "is shown for confirmation first.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "crs": {"type": "string"}}, "required": ["layer_name", "crs"]},
    keywords=[
        "assign projection", "assign the crs", "assign crs", "layer has no crs", "wrong crs on the layer", "set the layer crs",
        "set the crs of the layer", "define the crs",
    ],
)
def assign_layer_crs(layer_name, crs, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found."}
    target, err = _crs(crs, None)
    if err:
        return {"error": err}
    old = layer.crs().authid() or "none"
    if not confirmed:
        from .attribute_edit_tools import preview
        return preview("assign_layer_crs", {"layer_name": layer_name, "crs": crs},
                       f"Declare that '{layer_name}' is in {target.authid()} (now {old}). The coordinates are NOT changed; if "
                       f"{target.authid()} is wrong the layer will appear in the wrong place.",
                       f"layer.setCrs(QgsCoordinateReferenceSystem('{target.authid()}'))")
    layer.setCrs(target)
    return {"success": True, "layer_name": layer_name, "previous_crs": old, "crs": layer.crs().authid()}


# ----------------------------------------------------------------------------------------------------------------------------------
# Bookmarks
# ----------------------------------------------------------------------------------------------------------------------------------

def _bookmark_manager():
    return QgsProject.instance().bookmarkManager()


@register_tool(
    "create_bookmark",
    "Save a spatial bookmark in the project: of a layer's extent (layer_name), of an explicit extent [xmin, ymin, xmax, ymax] in crs, "
    "or of the current map view when neither is given.",
    {"type": "object", "properties": {"name": {"type": "string"}, "layer_name": {"type": "string"},
                                      "extent": {"type": "array", "items": {"type": "number"}}, "crs": {"type": "string"}},
     "required": ["name"]},
    keywords=[
        "create a bookmark", "add a bookmark", "save a bookmark", "bookmark this", "bookmark the view", "new bookmark",
        "save this view",
    ],
)
def create_bookmark(name, layer_name=None, extent=None, crs=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from qgis.core import QgsBookmark, QgsReferencedRectangle
    label = str(name or "").strip()
    if not label:
        return {"error": "A bookmark needs a name."}
    if any(b.name() == label for b in _bookmark_manager().bookmarks()):
        return {"error": f"A bookmark called '{label}' already exists."}
    if layer_name and extent:
        return {"error": "Give a layer_name or an extent, not both."}
    if layer_name:
        layer = _layer(layer_name)
        if layer is None:
            return {"error": f"Layer '{layer_name}' not found."}
        rect, source = layer.extent(), layer.crs()
    elif extent:
        box, err = check_extent(extent)
        if err:
            return {"error": err}
        source, err = _crs(crs or "EPSG:4326", None)
        if err:
            return {"error": err}
        rect = QgsRectangle(*box)
    else:
        if iface is None:
            return {"error": "QGIS interface not available, so there is no current view to save."}
        rect, source = iface.mapCanvas().extent(), iface.mapCanvas().mapSettings().destinationCrs()
    bookmark = QgsBookmark()
    bookmark.setName(label)
    bookmark.setExtent(QgsReferencedRectangle(rect, source))
    _bookmark_manager().addBookmark(bookmark)
    return {"success": True, "name": label, "crs": source.authid()}


@register_tool(
    "list_bookmarks",
    "List the spatial bookmarks saved in the project. Read-only.",
    {"type": "object", "properties": {}, "required": []},
    keywords=[
        "list the bookmarks", "list bookmarks", "show the bookmarks", "my bookmarks", "what bookmarks",
    ],
)
def list_bookmarks():
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    items = [{"name": b.name(), "crs": b.extent().crs().authid()} for b in _bookmark_manager().bookmarks()]
    return {"success": True, "count": len(items), "bookmarks": items}


@register_tool(
    "go_to_bookmark",
    "Zoom the map to a saved spatial bookmark by name.",
    {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    keywords=[
        "go to the bookmark", "go to bookmark", "zoom to the bookmark", "jump to the bookmark", "open the bookmark",
    ],
)
def go_to_bookmark(name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    match = next((b for b in _bookmark_manager().bookmarks() if b.name() == str(name)), None)
    if match is None:
        return {"error": f"No bookmark called '{name}'. Saved: {', '.join(b.name() for b in _bookmark_manager().bookmarks()) or 'none'}."}
    if iface is None:
        return {"error": "QGIS interface not available"}
    canvas = iface.mapCanvas()
    rect = QgsCoordinateTransform(match.extent().crs(), canvas.mapSettings().destinationCrs(),
                                  QgsProject.instance()).transformBoundingBox(match.extent())
    canvas.setExtent(rect)
    canvas.refresh()
    return {"success": True, "name": name}


# ----------------------------------------------------------------------------------------------------------------------------------
# Project properties and measuring
# ----------------------------------------------------------------------------------------------------------------------------------

@register_tool(
    "set_project_properties",
    "Set the project title and/or project variables (a {name: value} object usable as @name in expressions).",
    {"type": "object", "properties": {"title": {"type": "string"}, "variables": {"type": "object"}}, "required": []},
    keywords=[
        "project title", "set the project title", "rename the project", "project variable", "set a project variable",
        "project properties",
    ],
)
def set_project_properties(title=None, variables=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if title is None and not variables:
        return {"error": "Give a title and/or variables."}
    from qgis.core import QgsExpressionContextUtils
    import re
    for key in (variables or {}):
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$", str(key)):
            return {"error": f"Variable name '{str(key)[:40]}' is not allowed: letters, digits and underscore, starting with a letter or underscore."}
    project = QgsProject.instance()
    if title is not None:
        project.setTitle(str(title)[:200])
    for key, value in (variables or {}).items():
        QgsExpressionContextUtils.setProjectVariable(project, str(key), str(value)[:500])
    return {"success": True, "title": project.title(), "variables_set": sorted(str(k) for k in (variables or {}))}


@register_tool(
    "measure_distance",
    "Measure on the ellipsoid along a path of points [[x, y], ...] given in crs (default EPSG:4326): total length in metres and "
    "kilometres, and for exactly two points the bearing in degrees. With close_polygon=true the points are a polygon and its area "
    "in square metres and hectares is returned too.",
    {"type": "object", "properties": {"points": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
                                      "crs": {"type": "string"}, "close_polygon": {"type": "boolean"}}, "required": ["points"]},
    keywords=[
        "measure the distance", "measure distance", "how far is", "distance between", "measure the length", "measure the area",
        "bearing between", "measure between", "what is the distance",
    ],
)
def measure_distance(points, crs=None, close_polygon=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    try:
        coords = [(float(p[0]), float(p[1])) for p in points]
    except (TypeError, ValueError, IndexError):
        return {"error": "points must be a list of [x, y] pairs."}
    if len(coords) < 2 or len(coords) > 10000:
        return {"error": "Give between 2 and 10000 points."}
    source, err = _crs(crs or "EPSG:4326", None)
    if err:
        return {"error": err}
    area = QgsDistanceArea()
    area.setSourceCrs(source, QgsProject.instance().transformContext())
    ellipsoid = QgsProject.instance().ellipsoid()
    area.setEllipsoid(ellipsoid if ellipsoid and ellipsoid != "NONE" else "WGS84")
    pts = [QgsPointXY(x, y) for x, y in coords]
    total = sum(area.measureLine(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if close_polygon:
        total += area.measureLine(pts[-1], pts[0])
    out = {"success": True, "length_m": round(total, 2), "length_km": round(total / 1000, 4), "points": len(pts),
           "ellipsoid": area.ellipsoid()}
    if len(pts) == 2 and not close_polygon:
        out["bearing_degrees"] = round((math.degrees(area.bearing(pts[0], pts[1])) + 360) % 360, 2)
    if close_polygon:
        if len(pts) < 3:
            return {"error": "A polygon needs at least 3 points."}
        from qgis.core import QgsGeometry
        square_m = area.measureArea(QgsGeometry.fromPolygonXY([pts]))
        out["area_m2"] = round(square_m, 2)
        out["area_ha"] = round(square_m / 10000, 4)
    return out
