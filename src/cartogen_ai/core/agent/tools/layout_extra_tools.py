"""M5 (completion plan, package G): what the first M5 tools left out of print layouts.

add_overview_map      a map that shows where another layout map is looking (a locator inset with a frame), optionally creating the inset
set_layout_guides_grid  guides at chosen positions, the snapping grid and snapping
set_layout_atlas      one page per feature of a coverage layer (an atlas), ready for export_layout_atlas
export_layout (in layout_item_tools.py) also writes a world file next to an image and can write a GeoPDF

Not done, and said so in the coverage matrix: chart, 3D map and elevation-profile layout items. Those need modules this plugin cannot count on;
package H probes what the QGIS image offers before any of them is attempted. Written without a QGIS install: tests/test_layout_extra_tools_live.py
reads everything back from real layouts (CI's first run is its first execution)."""
from ...validators.expression_screen import screen_expression
from .layout_extra_options import check_atlas, check_guides_grid, check_overview
from .registry import register_tool

try:
    from qgis.core import (QgsExpression, QgsLayoutGuide, QgsLayoutItemMap, QgsLayoutItemMapOverview, QgsLayoutMeasurement, QgsProject,
                           QgsUnitTypes)
    from qgis.PyQt.QtCore import QRectF, Qt
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _layout(name):
    return QgsProject.instance().layoutManager().layoutByName(name)


def _mm(value):
    return QgsLayoutMeasurement(value, QgsUnitTypes.LayoutUnit.LayoutMillimeters)


@register_tool(
    "add_overview_map",
    "Show where one layout map is looking on another map (a locator or overview inset): overview_map_id is the map that draws the frame "
    "(the small inset), extent_map_id is the map whose extent the frame shows (default MAP_MAIN). To create the inset too, give inset_box "
    "{x_mm, y_mm, width_mm, height_mm}; it is zoomed out around the main map. color and width_mm style the frame.",
    {"type": "object", "properties": {
        "layout_name": {"type": "string"}, "overview_map_id": {"type": "string"}, "extent_map_id": {"type": "string"},
        "color": {"type": "string"}, "width_mm": {"type": "number"},
        "inset_box": {"type": "object", "properties": {"x_mm": {"type": "number"}, "y_mm": {"type": "number"},
                                                       "width_mm": {"type": "number"}, "height_mm": {"type": "number"}}}},
     "required": ["layout_name"]})
def add_overview_map(layout_name, overview_map_id=None, extent_map_id="MAP_MAIN", color=None, width_mm=None, inset_box=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = check_overview(overview_map_id, extent_map_id, color, width_mm, inset_box)
    if problem:
        return {"error": problem}
    layout = _layout(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found. See list_layouts."}
    main = layout.itemById(options["extent_map_id"])
    if not isinstance(main, QgsLayoutItemMap):
        return {"error": f"The layout has no map with id '{options['extent_map_id']}' to show on the overview."}
    inset = None
    created = False
    if options.get("overview_map_id"):
        inset = layout.itemById(options["overview_map_id"])
        if not isinstance(inset, QgsLayoutItemMap):
            return {"error": f"The layout has no map with id '{options['overview_map_id']}'."}
    if inset is None:
        box = options["inset_box"]
        inset = QgsLayoutItemMap(layout)
        inset.setId("MAP_INSET")
        layout.addLayoutItem(inset)
        inset.attemptSetSceneRect(QRectF(box["x_mm"], box["y_mm"], box["width_mm"], box["height_mm"]))
        inset.setFrameEnabled(True)
        rect = main.extent()
        rect.scale(6.0)
        inset.setExtent(rect)
        created = True
    from .layout_item_tools import _colour
    try:
        overview = QgsLayoutItemMapOverview("Overview", inset)
        inset.overviews().addOverview(overview)
        overview.setLinkedMap(main)
        overview.setEnabled(True)
        # The overview owns its frame symbol: change it in place. Passing it back through setFrameSymbol() would hand QGIS an object it
        # already owns (it deletes it, then uses it), the same mistake that crashed set_label_callout in the first live run of package F.
        symbol = overview.frameSymbol()
        if symbol is not None and ("color" in options or "width_mm" in options):
            if "color" in options:
                colour = _colour(options["color"], "#d62728")
                if colour is None:
                    return {"error": f"Invalid color: {options['color']}."}
                symbol.setColor(colour)
            if "width_mm" in options:
                symbol.setWidth(options["width_mm"])
        inset.refresh()
    except Exception as e:
        return {"error": f"add_overview_map failed: {e}"}
    return {"success": True, "layout_name": layout_name, "overview_map_id": inset.id(), "shows_extent_of": main.id(), "created_inset": created}


@register_tool(
    "set_layout_guides_grid",
    "Set a print layout's alignment aids: guides (a list of {orientation: horizontal|vertical, position_mm}; replaces the guides on the first "
    "page), clear_guides=true to remove them, grid_mm for the snapping grid spacing, snap_to_grid and snap_to_guides to switch snapping on or "
    "off. These affect how items snap when edited; they do not print.",
    {"type": "object", "properties": {
        "layout_name": {"type": "string"},
        "guides": {"type": "array", "items": {"type": "object", "properties": {"orientation": {"type": "string"}, "position_mm": {"type": "number"}}}},
        "clear_guides": {"type": "boolean"}, "grid_mm": {"type": "number"}, "snap_to_grid": {"type": "boolean"}, "snap_to_guides": {"type": "boolean"}},
     "required": ["layout_name"]})
def set_layout_guides_grid(layout_name, guides=None, clear_guides=None, grid_mm=None, snap_to_grid=None, snap_to_guides=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = check_guides_grid(guides, clear_guides, grid_mm, snap_to_grid, snap_to_guides)
    if problem:
        return {"error": problem}
    layout = _layout(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found. See list_layouts."}
    try:
        if options.get("clear_guides") or "guides" in options:
            layout.guides().clear()
        page = layout.pageCollection().page(0)
        for guide in options.get("guides", []):
            orientation = Qt.Orientation.Horizontal if guide["orientation"] == "Horizontal" else Qt.Orientation.Vertical
            layout.guides().addGuide(QgsLayoutGuide(orientation, _mm(guide["position_mm"]), page))
        if "grid_mm" in options:
            layout.gridSettings().setResolution(_mm(options["grid_mm"]))
        if "snap_to_grid" in options:
            layout.snapper().setSnapToGrid(options["snap_to_grid"])
        if "snap_to_guides" in options:
            layout.snapper().setSnapToGuides(options["snap_to_guides"])
    except Exception as e:
        return {"error": f"set_layout_guides_grid failed: {e}"}
    page = layout.pageCollection().page(0)
    guides_now = len(layout.guides().guides(Qt.Orientation.Horizontal, page)) + len(layout.guides().guides(Qt.Orientation.Vertical, page))
    return {"success": True, "layout_name": layout_name, "guides_now": guides_now, "changed": sorted(options)}


@register_tool(
    "set_layout_atlas",
    "Turn a print layout into an atlas: one page per feature of coverage_layer. page_name_field names each page, sort_field orders them, "
    "filter_expression keeps only some features (a QGIS expression), hide_coverage hides the coverage layer outside the current feature, "
    "margin_percent pads the map around each feature, scaling is auto, fixed or predefined, map_item_id is the map that follows the atlas "
    "(default MAP_MAIN). disable=true switches the atlas off. Export it with export_layout_atlas.",
    {"type": "object", "properties": {
        "layout_name": {"type": "string"}, "coverage_layer": {"type": "string"}, "page_name_field": {"type": "string"},
        "sort_field": {"type": "string"}, "filter_expression": {"type": "string"}, "hide_coverage": {"type": "boolean"},
        "margin_percent": {"type": "number"}, "scaling": {"type": "string"}, "map_item_id": {"type": "string"}, "disable": {"type": "boolean"}},
     "required": ["layout_name"]})
def set_layout_atlas(layout_name, coverage_layer=None, page_name_field=None, sort_field=None, filter_expression=None, hide_coverage=None,
                     margin_percent=None, scaling=None, map_item_id=None, disable=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = check_atlas(coverage_layer, page_name_field, sort_field, filter_expression, hide_coverage, margin_percent, scaling,
                                   map_item_id, disable)
    if problem:
        return {"error": problem}
    layout = _layout(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found. See list_layouts."}
    atlas = layout.atlas()
    if options.get("disable"):
        atlas.setEnabled(False)
        return {"success": True, "layout_name": layout_name, "atlas": "off"}
    layers = QgsProject.instance().mapLayersByName(options["coverage_layer"])
    if not layers or not hasattr(layers[0], "fields"):
        return {"error": f"Vector layer '{options['coverage_layer']}' not found."}
    layer = layers[0]
    names = layer.fields().names()
    for key in ("page_name_field", "sort_field"):
        if key in options and options[key] not in names:
            return {"error": f"{key} '{options[key]}' is not a field of '{layer.name()}'. It has: {', '.join(names)}."}
    if "filter_expression" in options:
        blocked = screen_expression(options["filter_expression"])
        if blocked:
            return {"error": blocked}
        parsed = QgsExpression(options["filter_expression"])
        if parsed.hasParserError():
            return {"error": f"Invalid filter_expression: {parsed.parserErrorString()}"}
    from .layout_item_tools import _map_item
    map_item = _map_item(layout, options.get("map_item_id"))
    if map_item is None:
        return {"error": "The layout has no map item to follow the atlas."}
    try:
        atlas.setCoverageLayer(layer)
        atlas.setEnabled(True)
        if "page_name_field" in options:
            atlas.setPageNameExpression(f'"{options["page_name_field"]}"')
        if "sort_field" in options:
            atlas.setSortFeatures(True)
            atlas.setSortExpression(f'"{options["sort_field"]}"')
        if "filter_expression" in options:
            atlas.setFilterFeatures(True)
            atlas.setFilterExpression(options["filter_expression"])
        if "hide_coverage" in options:
            atlas.setHideCoverage(options["hide_coverage"])
        map_item.setAtlasDriven(True)
        if "scaling" in options:
            mode = getattr(QgsLayoutItemMap, "AtlasScalingMode", None)
            member = getattr(mode, {"auto": "Auto", "fixed": "Fixed", "predefined": "Predefined"}[options["scaling"]], None) if mode else None
            if member is not None:
                map_item.setAtlasScalingMode(member)
        if "margin_percent" in options:
            map_item.setAtlasMargin(options["margin_percent"] / 100.0)
        atlas.updateFeatures()
        pages = atlas.count()
    except Exception as e:
        return {"error": f"set_layout_atlas failed: {e}"}
    return {"success": True, "layout_name": layout_name, "coverage_layer": layer.name(), "pages": pages, "map_item": map_item.id()}
