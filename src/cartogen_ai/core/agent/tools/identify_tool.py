"""identify_at_point (PLAN-023 R9-5): what is at this coordinate? The features of the vector layers under it and the cell values of the raster layers, without a map click.

The coordinate is in the CRS given (default: the project's) and is transformed to each layer's own CRS. `radius` (in that CRS's units) widens the search to a circle, which is what
point and line layers need (a coordinate is almost never exactly on one). Vector layers are tested with the real geometry (intersects), not just the bounding box. By default the
visible layers are looked at; `layers` names others. At most 50 features are returned in total and the reply says when more matched. A raster reply is the cell the point falls in,
per band; `radius` does not apply to rasters. Read-only: nothing is changed. The attributes of the matched features are returned, as get_layer_attributes already does.

Written without a QGIS install; tests/test_identify_tool_live.py is its first execution in CI."""

from . import identify_ops as io
from .registry import register_tool

try:
    from qgis.core import NULL, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsWkbTypes
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

MAX_BANDS = 16
FIND_MORE = 1          # one row beyond the cap per layer is enough to know the answer was cut


def _pick_layers(project, names):
    """([layers], error): the named layers, or every visible vector and raster layer. Needs QGIS."""
    if names:
        found = []
        for name in names:
            matches = project.mapLayersByName(name)
            if not matches or not isinstance(matches[0], QgsVectorLayer | QgsRasterLayer):
                return None, f"Layer '{name}' was not found (or is not a vector or raster layer)."
            found.append(matches[0])
        return found, None
    root = project.layerTreeRoot()
    visible = []
    for layer in project.mapLayers().values():
        node = root.findLayer(layer.id())
        if isinstance(layer, QgsVectorLayer | QgsRasterLayer) and node is not None and node.isVisible():
            visible.append(layer)
    return visible, None


def _search_shape(point_in, radius, transform):
    """The search geometry in the layer's CRS: the point, or a circle of `radius` around it; `transform` is None when the CRS is the same. Needs QGIS."""
    shape = QgsGeometry.fromPointXY(point_in)
    if radius > 0:
        shape = shape.buffer(radius, 16)
    if transform is not None:
        shape.transform(transform)
    return shape


def _vector_rows(layer, shape, cap):
    """The rows (id, attributes) of the features of `layer` whose geometry intersects `shape`, at most cap + 1. Needs QGIS."""
    box = shape.boundingBox()
    eps = 1e-9 * max(1.0, abs(box.xMinimum()), abs(box.yMinimum()))
    request = QgsFeatureRequest().setFilterRect(box.buffered(eps))
    rows = []
    for f in layer.getFeatures(request):
        if f.geometry().isNull() or not f.geometry().intersects(shape):
            continue
        attrs = {fld.name(): io.plain_value(None if f[fld.name()] == NULL else f[fld.name()]) for fld in layer.fields()}
        rows.append({"feature_id": f.id(), "attributes": attrs})
        if len(rows) >= cap + FIND_MORE:
            break
    return rows


def _raster_values(layer, point):
    """{band: value or None} for the cell under `point`, or None when the point is outside the raster. Needs QGIS."""
    if not layer.extent().contains(point):
        return None
    provider = layer.dataProvider()
    values = {}
    for band in range(1, min(layer.bandCount(), MAX_BANDS) + 1):
        value, ok = provider.sample(point, band)
        values[layer.bandName(band) or str(band)] = io.plain_value(value) if ok else None
    return values


@register_tool(
    "identify_at_point",
    "Say what is at a coordinate, as the Identify tool does on the map but without a click: the attributes of the features of the vector layers under the point and the cell value of "
    "each band of the raster layers. x and y are in `crs` (default: the project CRS). By default the visible layers are checked; `layers` names others. Give a `radius` (in the "
    "units of that CRS: metres for a projected CRS, degrees for a geographic one) to find points and lines near the coordinate: without it only features exactly under the point match. "
    "At most 50 features are returned in total and the reply says when more matched. Read-only.",
    {"type": "object", "properties": {
        "x": {"type": "number", "description": "X (longitude or easting) in `crs`."},
        "y": {"type": "number", "description": "Y (latitude or northing) in `crs`."},
        "crs": {"type": "string", "description": "The CRS of x and y, for example EPSG:4326 (default: the project CRS)."},
        "layers": {"type": "array", "items": {"type": "string"}, "description": "Layer names to look at (default: all visible layers)."},
        "radius": {"type": "number", "description": "Search radius in the CRS's units (default 0: only what is exactly under the point). Vector layers only."},
        "max_features": {"type": "integer", "description": "Fewest features wanted, 1 to 50 (default 50). 50 is the most that is ever returned."}},
     "required": ["x", "y"]},
    keywords=["what is at this point", "what is at this location", "what is at that location", "what is at this spot", "what is here", "identify at", "identify the point", "features at a coordinate", "value at a coordinate", "raster value at", "what is under",
              "query a location", "what is at these coordinates"],
)
def identify_at_point(x, y, crs=None, layers=None, radius=0, max_features=io.MAX_FEATURES):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = io.check_request(x, y, radius, layers, max_features)
    if problem:
        return {"error": problem}
    project = QgsProject.instance()
    in_crs = QgsCoordinateReferenceSystem(str(crs)) if crs else project.crs()
    if not in_crs.isValid():
        return {"error": f"'{crs}' is not a coordinate system QGIS knows (for example EPSG:4326)." if crs else "The project has no coordinate system; give crs, for example EPSG:4326."}
    reach = float(radius)
    if in_crs.isGeographic() and reach >= io.MAX_RADIUS_DEGREES:
        return {"error": f"radius {reach:g} is in degrees for this CRS (1 degree is about 111 km). Give a radius below 1, or use a projected CRS for metres."}
    chosen, why = _pick_layers(project, layers)
    if why:
        return {"error": why}
    cap = int(float(max_features))
    point_in = QgsPointXY(float(x), float(y))
    groups, rasters, skipped, near_miss = [], [], [], False
    for layer in chosen:
        same = layer.crs() == in_crs or not layer.crs().isValid()
        transform = None if same else QgsCoordinateTransform(in_crs, layer.crs(), project)
        if isinstance(layer, QgsRasterLayer):
            point = point_in if same else transform.transform(point_in)
            rasters.append({"layer": layer.name(), "cell_values": _raster_values(layer, point)})
            continue
        if QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.GeometryType.NullGeometry:
            skipped.append(layer.name())
            continue
        shape = _search_shape(point_in, reach, transform)
        rows = _vector_rows(layer, shape, cap)
        if rows:
            groups.append((layer.name(), rows))
        elif reach == 0 and QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.GeometryType.PolygonGeometry:
            near_miss = True
    kept, count, truncated = io.cap_features(groups, cap)
    result = {"success": True, "point": [float(x), float(y)], "crs": in_crs.authid(), "radius": reach, "layers_checked": len(chosen) - len(skipped),
              "features_returned": count, "vector_layers": [{"layer": name, "features": rows} for name, rows in kept],
              "raster_layers": rasters}
    if truncated:
        result["truncated"] = True
        result["note_truncated"] = f"More than {cap} features matched; only the first {cap} are returned. Narrow the search with layers or a smaller radius."
    if skipped:
        result["layers_without_geometry"] = skipped
    if not count and not any(r["cell_values"] for r in rasters):
        result["message"] = "Nothing was found at that coordinate in the layers checked."
        if near_miss:
            result["hint"] = "Point and line layers are rarely exactly under a coordinate: pass a radius to find ones nearby."
    for r in rasters:
        if r["cell_values"] is None:
            r["note"] = "The point is outside this raster."
    return result
