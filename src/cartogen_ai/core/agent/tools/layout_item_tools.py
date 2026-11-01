"""M5 (roadmap 2026-10-14): build and adjust print layouts item by item, set the map's scale and extent, change the page, keep templates, and
export to SVG. create_print_layout still builds the fixed standard composition; these tools work on any layout already in the project.

add_layout_item       label, picture (local file), shape, arrow, attribute table
edit_layout_item      move, resize, rotate, frame on/off, remove
set_layout_map        scale, extent from a layer or a lon/lat box, rotation, lock the layers, follow a map theme
set_layout_page       page size, orientation, number of pages
save_layout_template  .qpt file;  load_layout_template  new layout from a .qpt
export_layout         PDF, PNG/JPG/TIF or SVG

Refused on purpose (see layout_options.py): HTML frames, which run web content inside QGIS, and pictures given as a URL. A loaded template
that contains an HTML frame is not added. Written without a QGIS install: tests/test_layout_item_tools_live.py reads everything back from
real layouts (CI's first run is its first execution)."""
import os

from ._paths import resolve_output_path
from .layout_options import (valid_item_id, page_size_mm, validate_export_path, validate_geometry, validate_map_options, validate_new_item,
                             validate_template_path, MAX_PAGES)
from .registry import register_tool

try:
    from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFillSymbol, QgsLayoutExporter, QgsLayoutFrame,
                           QgsLayoutItemAttributeTable, QgsLayoutItemHtml, QgsLayoutItemLabel, QgsLayoutItemMap, QgsLayoutItemPage,
                           QgsLayoutItemPicture, QgsLayoutItemPolyline, QgsLayoutItemShape, QgsLayoutPoint, QgsLayoutSize,
                           QgsPrintLayout, QgsProject, QgsReadWriteContext, QgsRectangle, QgsVectorLayer)
    from qgis.PyQt.QtCore import QPointF, QRectF
    from qgis.PyQt.QtGui import QColor, QPolygonF
    from qgis.PyQt.QtXml import QDomDocument
    from .layout_tools import LAYOUT_MM
    from .plain_colour import resolve_colour
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _layout(name):
    from ._layout_names import lookup
    return lookup(QgsProject.instance().layoutManager(), name)


def _colour(text, default):
    colour = QColor(resolve_colour(text) or text) if text else QColor(default)
    return colour if colour.isValid() else None


def _enum(owners, name):
    """First owner (a class or scoped enum) that has `name`; used where QGIS 4 moved the enum."""
    for owner in owners:
        value = getattr(owner, name, None) if owner is not None else None
        if value is not None:
            return value
    return None


def _free_id(layout, kind):
    base, n = kind.upper(), 1
    while layout.itemById(f"{base}_{n}") is not None:
        n += 1
    return f"{base}_{n}"


def _place(layout, item, geometry):
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(geometry["x_mm"], geometry["y_mm"], LAYOUT_MM))
    item.attemptResize(QgsLayoutSize(geometry["width_mm"], geometry["height_mm"], LAYOUT_MM))


def _make_label(layout, spec, params):
    item = QgsLayoutItemLabel(layout)
    item.setText(spec["text"])
    if "font_size" in spec or params.get("font_color"):
        fmt = item.textFormat()
        if "font_size" in spec:
            fmt.setSize(spec["font_size"])
        if params.get("font_color"):
            colour = _colour(params["font_color"], "#000000")
            if colour is None:
                return None, f"Invalid font_color: {params['font_color']}."
            fmt.setColor(colour)
        item.setTextFormat(fmt)
    return item, None


def _make_picture(layout, spec, params):
    path = resolve_output_path(spec["picture_path"])
    if not os.path.isfile(path):
        return None, f"Picture file not found: {path}"
    item = QgsLayoutItemPicture(layout)
    item.setPicturePath(path)
    return item, None


def _make_shape(layout, spec, params):
    owners = (getattr(QgsLayoutItemShape, "Shape", None), QgsLayoutItemShape, getattr(Qgis, "LayoutShapeType", None))
    shape = _enum(owners, {"rectangle": "Rectangle", "ellipse": "Ellipse", "triangle": "Triangle"}[spec["shape"]])
    if shape is None:
        return None, f"This QGIS does not offer the '{spec['shape']}' shape item."
    fill = _colour(params.get("fill_color"), "#ffffff")
    outline = _colour(params.get("outline_color"), "#000000")
    if fill is None or outline is None:
        return None, "Invalid fill_color or outline_color. Use a hex code or a plain colour such as 'dark red'."
    item = QgsLayoutItemShape(layout)
    item.setShapeType(shape)
    item.setSymbol(QgsFillSymbol.createSimple({"color": fill.name(), "outline_color": outline.name(),
                                               "outline_width": str(spec.get("outline_width_mm", 0.3))}))
    return item, None


def _make_arrow(layout, spec, params):
    outline = _colour(params.get("outline_color"), "#000000")
    if outline is None:
        return None, f"Invalid outline_color: {params.get('outline_color')}."
    points = QPolygonF([QPointF(spec["from_x_mm"], spec["from_y_mm"]), QPointF(spec["to_x_mm"], spec["to_y_mm"])])
    item = QgsLayoutItemPolyline(points, layout)
    owners = (getattr(QgsLayoutItemPolyline, "MarkerMode", None), QgsLayoutItemPolyline, getattr(Qgis, "ArrowHeadMode", None))
    head = _enum(owners, "ArrowHead")
    if head is not None and hasattr(item, "setEndMarker"):
        item.setEndMarker(head)
    return item, None


def _make_table(layout, spec, params):
    layers = QgsProject.instance().mapLayersByName(spec["layer_name"])
    if not layers or not isinstance(layers[0], QgsVectorLayer):
        return None, f"Vector layer '{spec['layer_name']}' not found."
    layer = layers[0]
    if "fields" in spec:
        missing = [f for f in spec["fields"] if layer.fields().indexOf(f) < 0]
        if missing:
            return None, f"Field(s) {missing} not on '{layer.name()}'. Available: {[f.name() for f in layer.fields()]}"
    table = QgsLayoutItemAttributeTable(layout)
    table.setVectorLayer(layer)
    table.setMaximumNumberOfFeatures(spec["max_rows"])
    if "fields" in spec:
        table.setDisplayedFields(spec["fields"])
    return table, None


_MAKERS = {"label": _make_label, "picture": _make_picture, "shape": _make_shape, "arrow": _make_arrow, "table": _make_table}


@register_tool(
    "add_layout_item",
    "Add one item to a print layout that already exists (see list_layouts): a text label, a picture from a local image file (png, jpg, svg), "
    "a shape (rectangle, ellipse, triangle), an arrow, or an attribute table of a vector layer. Position and size are in millimetres from the "
    "page's top-left corner (an A4 landscape page is 297 x 210). An arrow is given by its start and end points instead of a box. Give the item "
    "an item_id to find it again; list_layout_items shows what is there. HTML frames and pictures from a web address are refused on purpose.",
    {"type": "object", "properties": {
        "layout_name": {"type": "string"},
        "kind": {"type": "string", "description": "label, picture, shape, arrow or table"},
        "item_id": {"type": "string", "description": "Letters, digits, space, - and _ (max 64). Generated if omitted."},
        "x_mm": {"type": "number"}, "y_mm": {"type": "number"}, "width_mm": {"type": "number"}, "height_mm": {"type": "number"},
        "text": {"type": "string"}, "font_size": {"type": "number"}, "font_color": {"type": "string"},
        "picture_path": {"type": "string"},
        "shape": {"type": "string"}, "fill_color": {"type": "string"}, "outline_color": {"type": "string"},
        "outline_width_mm": {"type": "number"},
        "from_x_mm": {"type": "number"}, "from_y_mm": {"type": "number"}, "to_x_mm": {"type": "number"}, "to_y_mm": {"type": "number"},
        "layer_name": {"type": "string", "description": "For a table: the vector layer."},
        "fields": {"type": "array", "items": {"type": "string"}, "description": "For a table: the columns to show."},
        "max_rows": {"type": "integer", "description": "For a table: rows to show (default 10, at most 200)."},
    }, "required": ["layout_name", "kind"]},
    keywords=[
        "add a picture to the layout", "add a logo to the layout", "add an image to the layout", "add a logo to the map",
        "add a text box", "add a label to the layout", "add a shape to the layout", "add a rectangle to the layout",
        "add an arrow", "add a table to the layout", "add an attribute table", "put a logo", "insert a picture", "insert a logo",
        "layout item",
    ],
)
def add_layout_item(layout_name, kind, item_id=None, x_mm=None, y_mm=None, width_mm=None, height_mm=None, text=None, font_size=None,
                    font_color=None, picture_path=None, shape=None, fill_color=None, outline_color=None, outline_width_mm=None,
                    from_x_mm=None, from_y_mm=None, to_x_mm=None, to_y_mm=None, layer_name=None, fields=None, max_rows=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    spec, problem = validate_new_item(kind, text=text, font_size=font_size, picture_path=picture_path, shape=shape,
                                      outline_width_mm=outline_width_mm, from_x_mm=from_x_mm, from_y_mm=from_y_mm, to_x_mm=to_x_mm,
                                      to_y_mm=to_y_mm, layer_name=layer_name, fields=fields, **({"max_rows": max_rows} if max_rows else {}))
    if problem:
        return {"error": problem}
    is_arrow = spec["kind"] == "arrow"
    geometry = None
    if not is_arrow:
        geometry, problem = validate_geometry(x_mm, y_mm, width_mm, height_mm, need_all=True)
        if problem:
            return {"error": problem}
    if item_id is not None and not valid_item_id(item_id):
        return {"error": "item_id may use letters, digits, space, - and _ (up to 64 characters)."}
    layout = _layout(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found. See list_layouts."}
    if item_id and layout.itemById(item_id) is not None:
        return {"error": f"An item with id '{item_id}' already exists in '{layout_name}'. Choose another id or use edit_layout_item."}
    item_id = item_id or _free_id(layout, spec["kind"])
    try:
        item, problem = _MAKERS[spec["kind"]](layout, spec, {"font_color": font_color, "fill_color": fill_color, "outline_color": outline_color})
        if problem:
            return {"error": problem}
        if spec["kind"] == "table":
            return _finish_table(layout, item, geometry, item_id, layout_name)
        item.setId(item_id)
        if is_arrow:
            layout.addLayoutItem(item)
        else:
            _place(layout, item, geometry)
        item.refresh()
    except Exception as e:
        return {"error": f"add_layout_item failed: {e}"}
    return {"success": True, "layout_name": layout_name, "item_id": item_id, "kind": spec["kind"]}


def _finish_table(layout, table, geometry, item_id, layout_name):
    layout.addMultiFrame(table)
    frame = QgsLayoutFrame(layout, table)
    frame.attemptSetSceneRect(QRectF(geometry["x_mm"], geometry["y_mm"], geometry["width_mm"], geometry["height_mm"]))
    frame.setId(item_id)
    table.addFrame(frame)
    return {"success": True, "layout_name": layout_name, "item_id": item_id, "kind": "table"}


@register_tool(
    "edit_layout_item",
    "Change or remove one item of a print layout by its id (list_layout_items shows the ids): move it (x_mm, y_mm), resize it (width_mm, "
    "height_mm), rotate it (rotation in degrees), switch its frame on or off (frame), or remove it (remove=true). Give only what should change.",
    {"type": "object", "properties": {
        "layout_name": {"type": "string"}, "item_id": {"type": "string"},
        "x_mm": {"type": "number"}, "y_mm": {"type": "number"}, "width_mm": {"type": "number"}, "height_mm": {"type": "number"},
        "rotation": {"type": "number"}, "frame": {"type": "boolean"}, "remove": {"type": "boolean"},
    }, "required": ["layout_name", "item_id"]},
    keywords=[
        "move the legend", "move the scale bar", "move the north arrow", "move the title", "resize the legend", "resize the map",
        "make the map bigger", "make the map smaller", "rotate the item", "remove the item from the layout",
        "delete the item from the layout", "remove the legend", "remove the north arrow", "remove the scale bar",
    ],
)
def edit_layout_item(layout_name, item_id, x_mm=None, y_mm=None, width_mm=None, height_mm=None, rotation=None, frame=None, remove=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    geometry, problem = validate_geometry(x_mm, y_mm, width_mm, height_mm)
    if problem:
        return {"error": problem}
    if not geometry and rotation is None and frame is None and not remove:
        return {"error": "Nothing to change: give x_mm, y_mm, width_mm, height_mm, rotation, frame or remove."}
    if rotation is not None:
        try:
            rotation = float(rotation)
        except (TypeError, ValueError):
            return {"error": "rotation must be a number of degrees."}
    layout = _layout(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found. See list_layouts."}
    item = layout.itemById(item_id)
    if item is None:
        return {"error": f"No item with id '{item_id}' in '{layout_name}'. See list_layout_items."}
    try:
        if remove:
            layout.removeLayoutItem(item)
            return {"success": True, "layout_name": layout_name, "item_id": item_id, "removed": True}
        if "x_mm" in geometry or "y_mm" in geometry:
            pos = item.positionWithUnits()
            item.attemptMove(QgsLayoutPoint(geometry.get("x_mm", pos.x()), geometry.get("y_mm", pos.y()), LAYOUT_MM))
        if "width_mm" in geometry or "height_mm" in geometry:
            size = item.sizeWithUnits()
            item.attemptResize(QgsLayoutSize(geometry.get("width_mm", size.width()), geometry.get("height_mm", size.height()), LAYOUT_MM))
        if rotation is not None:
            item.setItemRotation(rotation)
        if frame is not None:
            item.setFrameEnabled(bool(frame))
        item.refresh()
    except Exception as e:
        return {"error": f"edit_layout_item failed: {e}"}
    return {"success": True, "layout_name": layout_name, "item_id": item_id}


def _map_item(layout, item_id):
    if item_id:
        item = layout.itemById(item_id)
        return item if isinstance(item, QgsLayoutItemMap) else None
    item = layout.itemById("MAP_MAIN")
    if isinstance(item, QgsLayoutItemMap):
        return item
    return next((i for i in layout.items() if isinstance(i, QgsLayoutItemMap)), None)


def _target_rectangle(options, map_item):
    """(QgsRectangle in the map's CRS, None) or (None, message) from the bbox or extent_layer option."""
    project = QgsProject.instance()
    crs = map_item.crs() if hasattr(map_item, "crs") else project.crs()
    if "bbox" in options:
        rect = QgsRectangle(*options["bbox"])
        transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), crs, project)
        return transform.transformBoundingBox(rect), None
    layers = project.mapLayersByName(options["extent_layer"])
    if not layers:
        return None, f"Layer '{options['extent_layer']}' not found."
    layer = layers[0]
    rect = QgsRectangle(layer.extent())
    if layer.crs() != crs:
        rect = QgsCoordinateTransform(layer.crs(), crs, project).transformBoundingBox(rect)
    rect.scale(1.05)
    return rect, None


@register_tool(
    "set_layout_map",
    "Set what a print layout's map shows: the scale (scale = the denominator, 250000 for 1:250,000), the extent (extent_layer = zoom to a "
    "layer, or bbox = [min_lon, min_lat, max_lon, max_lat] in degrees), the rotation in degrees, lock_layers=true to freeze the layers the map "
    "shows now so later changes in the project do not alter the layout, or map_theme to follow a saved map theme. Works on MAP_MAIN unless "
    "map_item_id names another map. If both an extent and a scale are given, the extent is set first and the scale applied around its centre.",
    {"type": "object", "properties": {
        "layout_name": {"type": "string"}, "map_item_id": {"type": "string"},
        "scale": {"type": "number"}, "rotation": {"type": "number"},
        "extent_layer": {"type": "string"}, "bbox": {"type": "array", "items": {"type": "number"}},
        "lock_layers": {"type": "boolean"}, "map_theme": {"type": "string"},
    }, "required": ["layout_name"]},
    keywords=[
        "set the map scale", "scale of the layout map", "layout map scale", "zoom the layout map", "layout extent",
        "change the map extent in the layout", "rotate the layout map", "lock the layers", "freeze the layers",
        "map in the layout to", "layout to 1:",
    ],
)
def set_layout_map(layout_name, map_item_id=None, scale=None, rotation=None, extent_layer=None, bbox=None, lock_layers=None, map_theme=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = validate_map_options(scale, rotation, bbox, extent_layer, lock_layers, map_theme)
    if problem:
        return {"error": problem}
    layout = _layout(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found. See list_layouts."}
    map_item = _map_item(layout, map_item_id)
    if map_item is None:
        return {"error": "The layout has no map item" + (f" with id '{map_item_id}'." if map_item_id else ".")}
    if options.get("map_theme") and options["map_theme"] not in QgsProject.instance().mapThemeCollection().mapThemes():
        return {"error": f"No map theme named '{options['map_theme']}'. Existing: {QgsProject.instance().mapThemeCollection().mapThemes()}"}
    try:
        if "bbox" in options or "extent_layer" in options:
            rect, problem = _target_rectangle(options, map_item)
            if problem:
                return {"error": problem}
            map_item.zoomToExtent(rect)
        if "scale" in options:
            map_item.setScale(options["scale"])
        if "rotation" in options:
            map_item.setMapRotation(options["rotation"])
        if options.get("lock_layers") is True:
            map_item.setLayers(QgsProject.instance().layerTreeRoot().checkedLayers())
            map_item.setKeepLayerSet(True)
        elif options.get("lock_layers") is False:
            map_item.setKeepLayerSet(False)
        if options.get("map_theme"):
            map_item.setFollowVisibilityPreset(True)
            map_item.setFollowVisibilityPresetName(options["map_theme"])
        map_item.refresh()
    except Exception as e:
        return {"error": f"set_layout_map failed: {e}"}
    return {"success": True, "layout_name": layout_name, "scale_now": round(map_item.scale(), 2), "changed": sorted(options)}


@register_tool(
    "set_layout_page",
    "Change a print layout's page: size (A0 to A5, Letter, Legal, Tabloid), orientation (landscape or portrait) and the number of pages (1 to "
    "20; new pages copy the size). Items already on the page keep their positions: move them with edit_layout_item if the new size needs it.",
    {"type": "object", "properties": {
        "layout_name": {"type": "string"}, "size": {"type": "string"}, "orientation": {"type": "string"},
        "pages": {"type": "integer"},
    }, "required": ["layout_name"]},
    keywords=[
        "page size", "change the page size", "paper size", "a3 page", "a4 page", "a5 page", "a2 page", "a1 page", "a0 page",
        "letter page", "portrait layout", "landscape layout", "add a page", "second page", "two pages", "several pages",
        "multi-page",
    ],
)
def set_layout_page(layout_name, size=None, orientation=None, pages=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if size is None and orientation is None and pages is None:
        return {"error": "Nothing to change: give size, orientation or pages."}
    if pages is not None and not (isinstance(pages, int) and not isinstance(pages, bool) and 1 <= pages <= MAX_PAGES):
        return {"error": f"pages must be a whole number from 1 to {MAX_PAGES}."}
    layout = _layout(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found. See list_layouts."}
    collection = layout.pageCollection()
    first = collection.page(0)
    try:
        current = first.pageSize()
        if size is None:
            wh = (current.width(), current.height())
            if orientation is not None:
                wh, problem = _orient(wh, orientation)
                if problem:
                    return {"error": problem}
        else:
            wh, problem = page_size_mm(size, orientation or ("landscape" if current.width() >= current.height() else "portrait"))
            if problem:
                return {"error": problem}
        for i in range(collection.pageCount()):
            collection.page(i).setPageSize(QgsLayoutSize(wh[0], wh[1], LAYOUT_MM))
        while pages is not None and collection.pageCount() < pages:
            page = QgsLayoutItemPage(layout)
            page.setPageSize(QgsLayoutSize(wh[0], wh[1], LAYOUT_MM))
            collection.addPage(page)
        while pages is not None and collection.pageCount() > pages:
            collection.deletePage(collection.pageCount() - 1)
        layout.refresh()
    except Exception as e:
        return {"error": f"set_layout_page failed: {e}"}
    return {"success": True, "layout_name": layout_name, "page_mm": [wh[0], wh[1]], "pages": collection.pageCount()}


def _orient(wh, orientation):
    orient = str(orientation).strip().lower()
    if orient not in ("landscape", "portrait"):
        return None, "orientation must be 'landscape' or 'portrait'."
    w, h = sorted(wh)
    return ((h, w) if orient == "landscape" else (w, h)), None


@register_tool(
    "save_layout_template",
    "Save a print layout as a reusable template file (.qpt) that load_layout_template can turn into a new layout later, in this or another "
    "project. Replacing an existing file needs confirmation.",
    {"type": "object", "properties": {"layout_name": {"type": "string"}, "output_path": {"type": "string", "description": "Ends in .qpt"}},
     "required": ["layout_name", "output_path"]},
    keywords=[
        "save the layout as a template", "save layout template", "layout template", "save as a template", "export the template",
        ".qpt",
    ],
)
def save_layout_template(layout_name, output_path, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = validate_template_path(output_path, must_exist=False)
    if problem:
        return {"error": problem}
    layout = _layout(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found. See list_layouts."}
    path = resolve_output_path(output_path)
    from .export_tools import overwrite_preview, remember_written
    if not confirmed:
        preview = overwrite_preview("save_layout_template", {"layout_name": layout_name, "output_path": output_path}, path)
        if preview:
            return preview
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not layout.saveAsTemplate(path, QgsReadWriteContext()):
            return {"error": f"QGIS could not write the template to {path}."}
    except Exception as e:
        return {"error": f"save_layout_template failed: {e}"}
    remember_written(path)
    return {"success": True, "layout_name": layout_name, "output_path": path}


@register_tool(
    "load_layout_template",
    "Create a new print layout from a template file (.qpt) made by save_layout_template or QGIS. The new layout gets new_layout_name, which "
    "must not be taken. A template that contains an HTML frame is refused (it would run web content).",
    {"type": "object", "properties": {"template_path": {"type": "string"}, "new_layout_name": {"type": "string"}},
     "required": ["template_path", "new_layout_name"]},
    keywords=[
        "load a layout template", "load the template", "new layout from a template", "open the template",
        "layout from a template", "use the template",
    ],
)
def load_layout_template(template_path, new_layout_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    path = resolve_output_path(template_path)
    problem = validate_template_path(path, must_exist=True)
    if problem:
        return {"error": problem}
    name = str(new_layout_name or "").strip()
    if not name:
        return {"error": "new_layout_name is required."}
    manager = QgsProject.instance().layoutManager()
    if manager.layoutByName(name) is not None:
        return {"error": f"A layout named '{name}' already exists. Choose another name."}
    try:
        document = QDomDocument()
        with open(path, "rb") as handle:
            if not document.setContent(handle.read()):
                return {"error": "The template file is not valid."}
        layout = QgsPrintLayout(QgsProject.instance())
        layout.initializeDefaults()
        _items, ok = layout.loadFromTemplate(document, QgsReadWriteContext(), True)
        if not ok:
            return {"error": "QGIS could not read the layout from this template."}
        if any(isinstance(mf, QgsLayoutItemHtml) for mf in layout.multiFrames()):
            return {"error": "The template contains an HTML frame, which runs web content, so it was not loaded."}
        layout.setName(name)
        manager.addLayout(layout)
    except Exception as e:
        return {"error": f"load_layout_template failed: {e}"}
    return {"success": True, "layout_name": name, "items": len([i for i in layout.items() if hasattr(i, "id") and i.id()])}


@register_tool(
    "export_layout",
    "Export an existing print layout to a file: .pdf, .png, .jpg, .tif (image) or .svg (vector). dpi applies to PDF and images (default 150). "
    "Replacing an existing file needs confirmation. create_print_layout can export while it builds; this exports a layout that already exists. "
    "The result lists any RESTRICTED or SENSITIVE layer the map draws and any missing title, legend, scale bar or north arrow in export_warnings: tell the user. "
    "A map that draws a RESTRICTED or SENSITIVE layer waits for the user's confirmation before it is written. "
    "purpose='publication' is for a file that will be shared outside the team: it is refused while the layout lacks a mandatory element or draws a protected layer, "
    "unless the user gives a reason (ask them; pass it as override_reason) and confirms.",
    {"type": "object", "properties": {"layout_name": {"type": "string"}, "output_path": {"type": "string"}, "dpi": {"type": "integer"},
                                      "preset": {"type": "string", "description": "export purpose instead of a dpi number: 'draft' (96), 'web' (150) or 'print' (300). An explicit dpi wins."},
                                      "output_format": {"type": "string", "description": "only when output_path is a FOLDER: pdf (default), png, jpg, tif or svg; the file is then named <layout>_<date>.<format>"},
                                      "world_file": {"type": "boolean", "description": "image exports: also write a world file (.pgw, .jgw, .tfw) so GIS software can place the picture"},
                                      "geopdf": {"type": "boolean", "description": "pdf exports: write a georeferenced PDF (needs the GDAL PDF driver)"},
                                      "purpose": {"type": "string", "description": "'publication' only when the user says the file will be shared outside the team; omit for drafts"},
                                      "override_reason": {"type": "string", "description": "with purpose='publication': the USER's stated reason for exporting despite problems. Never invent one; ask."}},
     "required": ["layout_name", "output_path"]},
    keywords=[
        "as a png for", "export the whole thing", "export the map as an image",
        "export the layout", "export layout", "export the layout as svg", "layout to svg", "save the layout as pdf",
        "save the layout as png", "export the existing layout", "export layout to", "map as a pdf", "map as pdf", "map as a png",
        "map as an image", "map as a jpg", "map to pdf", "pdf of the map", "pdf of the layout", "pdf copy of the map",
        "printable map", "print the layout to",
    ],
)
def export_layout(layout_name, output_path, dpi=None, world_file=False, geopdf=False, purpose=None, override_reason=None, confirmed=False,
                  preset=None, output_format="pdf"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from .layout_export_checks import current_profile
    from .layout_options import export_dpi, resolve_export_target
    layout = _layout(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found. See list_layouts."}
    profile, profile_note = current_profile(layout)          # PLAN-016: the file is re-read now; PLAN-014 phase 2b: a layout made with profile=... remembers its preset and file name pattern
    output_path = resolve_export_target(output_path, layout_name, output_format, pattern=profile.get("file_name_pattern"))
    kind, problem = validate_export_path(output_path)
    if problem:
        return {"error": problem}
    dpi, problem = export_dpi(preset or profile.get("export_preset"), dpi, 150)
    if problem:
        return {"error": problem}
    if not (isinstance(dpi, int) and not isinstance(dpi, bool) and 30 <= dpi <= 1200):
        return {"error": "dpi must be a whole number from 30 to 1200."}
    from .layout_extra_options import check_export_extras
    problem = check_export_extras(kind, world_file, geopdf)
    if problem:
        return {"error": problem}
    path = resolve_output_path(output_path)
    from .export_tools import overwrite_preview, remember_written
    arguments = {"layout_name": layout_name, "output_path": output_path, "dpi": dpi, "world_file": world_file, "geopdf": geopdf}
    if purpose:
        arguments["purpose"] = purpose
    if override_reason:
        arguments["override_reason"] = override_reason
    from .layout_export_checks import gate_export
    gated = gate_export(layout, "export_layout", arguments, purpose, override_reason, confirmed, overwrite_preview("export_layout", arguments, path) is not None)
    if gated:
        return gated
    if not confirmed:
        preview = overwrite_preview("export_layout", arguments, path)
        if preview:
            return preview
    exporter = QgsLayoutExporter(layout)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if kind == "pdf":
            settings = QgsLayoutExporter.PdfExportSettings()
            settings.dpi = dpi
            if geopdf:
                settings.writeGeoPdf = True
            code = exporter.exportToPdf(path, settings)
        elif kind == "svg":
            code = exporter.exportToSvg(path, QgsLayoutExporter.SvgExportSettings())
        else:
            settings = QgsLayoutExporter.ImageExportSettings()
            settings.dpi = dpi
            if world_file:
                settings.generateWorldFile = True
            code = exporter.exportToImage(path, settings)
    except Exception as e:
        return {"error": f"export_layout failed: {e}"}
    if code != QgsLayoutExporter.ExportResult.Success:
        return {"error": f"Export to '{path}' failed (QgsLayoutExporter result code {code})."}
    remember_written(path)
    out = {"success": True, "layout_name": layout_name, "output_path": path, "format": os.path.splitext(path)[1].lower().lstrip("."), "dpi": dpi}
    if world_file:
        stem, ext = os.path.splitext(path)
        sidecar = next((stem + e for e in (ext[:2] + ext[-1] + "w", ".wld") if os.path.isfile(stem + e)), None)
        out["world_file"] = sidecar or "requested, but no world file was found next to the image (the layout needs a map item)"
    if geopdf:
        out["geopdf"] = True
    from .layout_export_checks import layout_export_report
    out.update(layout_export_report(layout))     # PLAN-011 phase A: protected layers drawn, missing mandatory elements
    if profile_note:
        out["profile_note"] = profile_note
    if str(purpose or "").lower() == "publication" and out.get("export_warnings"):
        from .layout_export_checks import write_publication_record
        record = write_publication_record(path, layout_name, out.get("export_warnings", []), override_reason)
        if record:
            out["publication_record"] = record
    return out
