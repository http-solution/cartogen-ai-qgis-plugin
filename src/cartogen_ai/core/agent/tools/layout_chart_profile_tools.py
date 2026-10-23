"""M5 leftovers (gap-closing package): the chart and elevation-profile layout items the probe showed this QGIS has.

add_layout_chart              a bar, line or pie chart of one layer's two fields, as a layout item
add_layout_elevation_profile  an elevation profile along a straight line, from layers that have elevation turned on (set_layer_elevation)

The 3D map layout item is NOT built: CI's QGIS has no QgsLayoutItem3DMap (docs/QGIS_CAPABILITY_PROBE_2026-10-16.md). Written without a QGIS install:
tests/test_layout_chart_profile_live.py builds both items on a real layout and reads them back (CI's first run is its first execution); how they
LOOK when rendered or exported has not been checked."""
from .gap_options import check_box, check_chart, check_profile_line, free_box, line_ends
from .registry import register_tool

try:
    from qgis.core import (Qgis, QgsBarChartPlot, QgsCoordinateReferenceSystem, QgsLayoutItemChart, QgsLayoutItemElevationProfile, QgsLineChartPlot,
                           QgsLineString, QgsPieChartPlot, QgsPointXY, QgsProject, QgsVectorLayer)
    from qgis.PyQt.QtCore import QRectF
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _layout(name):
    from ._layout_names import lookup
    return lookup(QgsProject.instance().layoutManager(), name)


def _line_ends_of_layer(name):
    """Ends of the selected (else first) feature of a line layer, in the project CRS."""
    found = QgsProject.instance().mapLayersByName(str(name))
    if not found or not isinstance(found[0], QgsVectorLayer):
        return None, f"Line layer '{name}' not found."
    layer = found[0]
    features = layer.selectedFeatures() or list(layer.getFeatures())[:1]
    if not features or features[0].geometry() is None or features[0].geometry().isEmpty():
        return None, f"Layer '{name}' has no line feature."
    geometry = features[0].geometry()
    if geometry.type() != Qgis.GeometryType.Line:
        return None, f"Layer '{name}' is not a line layer."
    parts = geometry.asMultiPolyline() if geometry.isMultipart() else [geometry.asPolyline()]
    line = [(p.x(), p.y()) for p in parts[0]] if parts else []
    ends, problem = line_ends(line)
    if problem:
        return None, problem
    if layer.crs() != QgsProject.instance().crs() and QgsProject.instance().crs().isValid():
        from qgis.core import QgsCoordinateTransform
        transform = QgsCoordinateTransform(layer.crs(), QgsProject.instance().crs(), QgsProject.instance())
        ends = tuple((lambda p: (p.x(), p.y()))(transform.transform(QgsPointXY(*end))) for end in ends)
    return ends, None


def _auto_box(layout, x_mm, y_mm, width_mm, height_mm):
    """(x_mm, y_mm, note): the caller's position, or when it gave none a free spot on the first page (see gap_options.free_box). note says when
    the page had no free spot and the default was used."""
    if x_mm is not None or y_mm is not None:
        return (10 if x_mm is None else x_mm), (10 if y_mm is None else y_mm), None
    try:
        size = layout.pageCollection().page(0).pageSize()
        page_w, page_h = size.width(), size.height()
        taken = []
        for existing in layout.items():
            if type(existing).__name__ == "QgsLayoutItemPage" or not hasattr(existing, "positionWithUnits"):
                continue
            where = layout.convertToLayoutUnits(existing.positionWithUnits())
            size = layout.convertToLayoutUnits(existing.sizeWithUnits())
            taken.append((where.x(), where.y(), size.width(), size.height()))
        spot = free_box(taken, page_w, page_h, float(width_mm), float(height_mm))
    except Exception:
        spot = None
    if spot is None:
        return 10, 10, "No free spot of that size was found on the page, so the item was placed at 10, 10 and may overlap another."
    return spot[0], spot[1], None


def _place(item, layout, box, item_id):
    if item_id:
        item.setId(item_id)
    layout.addLayoutItem(item)
    item.attemptSetSceneRect(QRectF(box["x_mm"], box["y_mm"], box["width_mm"], box["height_mm"]))


def _make_series(name, x_expression, y_expression):
    """A chart series, or the reason it could not be made. The first live run (QGIS 4.2.2) showed SeriesDetails does not take (name, x, y)
    as constructor arguments, so a default object is filled through whichever setters or attributes this QGIS exposes."""
    try:
        series = QgsLayoutItemChart.SeriesDetails()
    except TypeError as e:
        return f"QGIS could not create a chart series: {e}"
    for value, setter, attribute in ((name, "setName", "name"), (x_expression, "setXExpression", "xExpression"),
                                     (y_expression, "setYExpression", "yExpression")):
        if hasattr(series, setter):
            getattr(series, setter)(value)
        elif attribute in dir(series) and not callable(getattr(series, attribute)):
            setattr(series, attribute, value)
        else:
            return f"This QGIS chart series has no way to set its {attribute} ({setter} / attribute not found)."
    return series


@register_tool(
    "add_layout_chart",
    "Add a chart to a print layout: chart_type 'bar', 'line' or 'pie' of layer_name, with x_field (the categories) and y_field (the values), both "
    "plain field names. Position and size in millimetres. A chart item draws the layer's own features, so it follows the layer.",
    {"type": "object", "properties": {
        "layout_name": {"type": "string"}, "layer_name": {"type": "string"}, "chart_type": {"type": "string"}, "x_field": {"type": "string"},
        "y_field": {"type": "string"}, "x_mm": {"type": "number"}, "y_mm": {"type": "number"}, "width_mm": {"type": "number"},
        "height_mm": {"type": "number"}, "item_id": {"type": "string"}},
     "required": ["layout_name", "layer_name", "x_field", "y_field"]})
def add_layout_chart(layout_name, layer_name, x_field, y_field, chart_type="bar", x_mm=None, y_mm=None, width_mm=120, height_mm=80, item_id=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = check_chart(layout_name, chart_type, x_field, y_field, item_id)
    if problem:
        return {"error": problem}
    box, problem = check_box(0 if x_mm is None else x_mm, 0 if y_mm is None else y_mm, width_mm, height_mm)
    if problem:
        return {"error": problem}
    layout = _layout(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found. See list_layouts."}
    box["x_mm"], box["y_mm"], placement_note = _auto_box(layout, x_mm, y_mm, box["width_mm"], box["height_mm"])
    found = QgsProject.instance().mapLayersByName(layer_name)
    layer = found[0] if found and isinstance(found[0], QgsVectorLayer) else None
    if layer is None:
        return {"error": f"Vector layer '{layer_name}' not found."}
    names = {f.name() for f in layer.fields()}
    missing = [f for f in (options["x_field"], options["y_field"]) if f not in names]
    if missing:
        return {"error": f"Layer '{layer_name}' has no field(s) {missing}. Fields: {sorted(names)}."}
    plots = {"bar": QgsBarChartPlot, "line": QgsLineChartPlot, "pie": QgsPieChartPlot}
    item = QgsLayoutItemChart(layout)
    plot = plots[options["chart_type"]]()
    if options["chart_type"] != "pie":
        # rc48 A12: bar/line charts drew nothing. The QGIS 4.2 reference says series X values are converted to numbers unless the X axis is
        # Categorical, so text categories (names) came out empty; the pie reads them as labels, which is why it alone drew.
        try:
            plot.xAxis().setType(Qgis.PlotAxisType.Categorical)
        except AttributeError:
            pass
    item.setPlot(plot)
    item.setSourceLayer(layer)
    series = _make_series(options["y_field"], f'"{options["x_field"]}"', f'"{options["y_field"]}"')
    if isinstance(series, str):
        return {"error": series}
    item.setSeriesList([series])
    _place(item, layout, box, options["item_id"])
    from ._sensitivity_notes import protected_layer_notes
    out = {"success": True, "layout_name": layout_name, "item_id": item.id(), "chart_type": options["chart_type"], "layer_name": layer.name(),
           "series": len(item.seriesList()), "x_mm": box["x_mm"], "y_mm": box["y_mm"],
           "note": "The item is on the layout. How the chart renders or exports has not been checked by the plugin; look at the layout."}
    notes = protected_layer_notes([layer], "the chart shows its values and the layout's classification footer was not changed. Check the layout "
                                           "before exporting. Advisory only, nothing was blocked.")
    if notes:
        out["warning"] = " ".join(notes)
    if placement_note:
        out["placement_note"] = placement_note
    return out


@register_tool(
    "add_layout_elevation_profile",
    "Add an elevation profile to a print layout along a straight line from (start_x, start_y) to (end_x, end_y) in the project CRS. layer_names "
    "are the layers to profile; each needs elevation turned on first (set_layer_elevation). Give either start/end coordinates or along_layer, the name "
    "of a LINE layer (a road, a river): the profile then runs from the first to the last vertex of its selected feature, or its first feature. "
    "Position and size in millimetres.",
    {"type": "object", "properties": {
        "layout_name": {"type": "string"}, "layer_names": {"type": "array", "items": {"type": "string"}}, "start_x": {"type": "number"},
        "start_y": {"type": "number"}, "end_x": {"type": "number"}, "end_y": {"type": "number"}, "x_mm": {"type": "number"},
        "y_mm": {"type": "number"}, "width_mm": {"type": "number"}, "height_mm": {"type": "number"}, "item_id": {"type": "string"},
        "along_layer": {"type": "string"}},
     "required": ["layout_name", "layer_names"]})
def add_layout_elevation_profile(layout_name, layer_names, start_x=None, start_y=None, end_x=None, end_y=None, x_mm=None, y_mm=None, width_mm=180,
                                 height_mm=70, item_id=None, along_layer=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if along_layer and start_x is None and end_x is None:
        ends, problem = _line_ends_of_layer(along_layer)
        if problem:
            return {"error": problem}
        (start_x, start_y), (end_x, end_y) = ends
    elif None in (start_x, start_y, end_x, end_y):
        return {"error": "Give start_x, start_y, end_x and end_y, or along_layer (the name of a line layer)."}
    line, problem = check_profile_line(start_x, start_y, end_x, end_y)
    if problem:
        return {"error": problem}
    box, problem = check_box(0 if x_mm is None else x_mm, 0 if y_mm is None else y_mm, width_mm, height_mm)
    if problem:
        return {"error": problem}
    if not isinstance(layer_names, list) or not layer_names:
        return {"error": "layer_names must list at least one layer."}
    layout = _layout(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found. See list_layouts."}
    box["x_mm"], box["y_mm"], placement_note = _auto_box(layout, x_mm, y_mm, box["width_mm"], box["height_mm"])
    layers, missing = [], []
    for name in layer_names:
        found = QgsProject.instance().mapLayersByName(str(name))
        (layers if found else missing).append(found[0] if found else name)
    if missing:
        return {"error": f"Layer(s) not found: {missing}."}
    # a raster has an elevation switch; a vector layer has none (it always applies), so only rasters can be "off"
    off = [layer.name() for layer in layers if hasattr(layer.elevationProperties(), "isEnabled") and not layer.elevationProperties().isEnabled()]
    if off:
        return {"error": f"Elevation is not turned on for {off}. Use set_layer_elevation (enabled=true) first."}
    item = QgsLayoutItemElevationProfile(layout)
    item.setCrs(QgsProject.instance().crs() if QgsProject.instance().crs().isValid() else QgsCoordinateReferenceSystem("EPSG:4326"))
    item.setProfileCurve(QgsLineString([QgsPointXY(*line[0]), QgsPointXY(*line[1])]))
    item.setLayers(layers)
    _place(item, layout, box, item_id)
    out = {"success": True, "layout_name": layout_name, "item_id": item.id(), "layers": [layer.name() for layer in layers],
           "x_mm": box["x_mm"], "y_mm": box["y_mm"],
           "note": "The item is on the layout. How the profile renders or exports has not been checked by the plugin; look at the layout."}
    if placement_note:
        out["placement_note"] = placement_note
    return out
