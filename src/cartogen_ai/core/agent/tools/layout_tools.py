# -*- coding: utf-8 -*-
"""
Print Layout Composition Tools for Cartogen AI.
Generates automated QgsPrintLayout compositions with title, map item, legend, scalebar, and north arrow.
"""

import os
from .registry import register_tool

try:
    from qgis.core import (
        QgsProject, QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLegend,
        QgsLayoutItemScaleBar, QgsLayoutItemLabel, QgsLayoutItemPicture,
        QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes, QgsPageSize, QgsLayoutExporter,
        QgsApplication, QgsCoordinateTransform
    )
    from qgis.utils import iface
    try:
        from qgis.core import Qgis
    except ImportError:
        Qgis = None
    from ..qgis_compat import enum_member

    # Qt6 (QGIS 4.0) requires QGIS sip enums to be reached through their enum
    # type. QgsUnitTypes is the awkward case: these members were available
    # unscoped on QGIS 3, while current API docs give the canonical types as
    # Qgis.LayoutUnit / Qgis.DistanceUnit -- so no single spelling is safe to
    # hard-code across both majors. Resolved once here, at import.
    LAYOUT_MM = enum_member("LayoutMillimeters", QgsUnitTypes, Qgis)
    DISTANCE_KM = enum_member("DistanceKilometers", QgsUnitTypes, Qgis)
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    LAYOUT_MM = None
    DISTANCE_KM = None
    iface = None


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


def _extent_to_canvas_crs(canvas, extent, source_crs):
    """Transforms extent from source_crs into the canvas's own destination
    CRS -- see the identical helper in vector_tools.py (zoom_to_layer/
    zoom_to_feature) for the full rationale. Duplicated locally rather than
    cross-imported, matching this codebase's existing convention of each
    tools module keeping its own small _find_layer_by_name-style helpers."""
    canvas_crs = canvas.mapSettings().destinationCrs()
    if not source_crs.isValid() or source_crs == canvas_crs:
        return extent
    try:
        transform = QgsCoordinateTransform(source_crs, canvas_crs, QgsProject.instance())
        return transform.transformBoundingBox(extent)
    except Exception:
        return extent


@register_tool(
    "create_print_layout",
    "Create a map print layout composition with title, legend, scalebar, north arrow, and an "
    "optional summary text panel -- then optionally export it. Exports at output_path if given: "
    "'.pdf' for a vector PDF, '.png'/'.jpg'/'.jpeg' for a raster image at the given dpi (default "
    "300, print quality). ALWAYS use this instead of hand-writing QgsPrintLayout/QgsLayoutItemMap/"
    "QgsLayoutExporter code via execute_pyqgis_script, even for a richer composition than this tool's "
    "parameters look like they cover -- body_text accepts multi-line text (use \\n between bullets/"
    "findings for a summary panel), and the legend/scale bar/north arrow are already included, so "
    "accepting this tool's defaults for those is strongly preferred over reimplementing the "
    "object-graph by hand. Hand-written layout code has repeatedly produced silently broken exports "
    "in live testing (a blank map area with no visible error, and real PyQGIS/Qt API mistakes, e.g. "
    "QFont.Italic and QgsLegendStyle.Item are not real attributes) that this tool doesn't have. The "
    "map area captures whatever extent is currently on screen -- pass zoom_to_layer to fit a specific "
    "layer's full extent first (e.g. the national boundary layer for a country-wide sitrep map); "
    "otherwise a stale or zoomed-in canvas view produces a cropped map missing large parts of the "
    "area of interest.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "page_orientation": {"type": "string", "description": "'Landscape' (default) or 'Portrait'."},
            "output_path": {"type": "string", "description": "Where to export -- '.pdf' for a vector PDF, '.png'/'.jpg'/'.jpeg' for a raster image. Omit to create the layout in the project without exporting."},
            "dpi": {"type": "integer", "description": "Export resolution in DPI, for both PDF and image export. Defaults to 300 (print quality)."},
            "body_text": {"type": "string", "description": "Optional summary/sitrep text shown in a panel on the layout (e.g. priority findings, data sources)."},
            "zoom_to_layer": {"type": "string", "description": "Name of a layer to fit the map to its full extent before capturing it, e.g. the national boundary layer for a full-country sitrep map. Omit to use whatever extent the canvas currently shows."},
        },
        "required": ["title"],
    },
)
def create_print_layout(title: str, page_orientation: str = "Landscape", output_path: str = "", dpi: int = 300, body_text: str = "", zoom_to_layer: str = ""):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    try:
        target_layer = None
        if zoom_to_layer:
            target_layer = _find_layer_by_name(zoom_to_layer)
            if target_layer is None:
                return {"error": f"Layer '{zoom_to_layer}' not found"}

        project = QgsProject.instance()
        layout_name = f"Layout_{title.replace(' ', '_')}"
        
        # Remove existing layout if present
        layout_manager = project.layoutManager()
        for existing in layout_manager.printLayouts():
            if existing.name() == layout_name:
                layout_manager.removeLayout(existing)

        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.setName(layout_name)

        # Handle page orientation
        page = layout.pageCollection().pages()[0]
        if page_orientation.lower() == "portrait":
            page.setPageSize(QgsLayoutSize(210, 297, LAYOUT_MM))
        else:
            page.setPageSize(QgsLayoutSize(297, 210, LAYOUT_MM))

        layout_manager.addLayout(layout)

        # Main Map Item
        canvas = iface.mapCanvas() if iface else None
        map_extent = None
        if target_layer is not None and canvas:
            map_extent = _extent_to_canvas_crs(canvas, target_layer.extent(), target_layer.crs())
            canvas.setExtent(map_extent)
            canvas.refresh()
        map_item = QgsLayoutItemMap(layout)
        # A freshly constructed QgsLayoutItemMap has a zero-size rect, and
        # setExtent() on a zero-size item produces a degenerate scale --
        # QGIS then falls back to a hugely zoomed-out view, which renders as
        # a solid ocean-blue rectangle on an OSM basemap (the blank-map bug
        # seen in exported layouts). Giving the item a nonzero placeholder
        # rect before setExtent() is the documented PyQGIS cookbook order.
        map_item.setRect(20, 20, 20, 20)
        if map_extent is not None:
            map_item.setExtent(map_extent)
        elif canvas:
            map_item.setExtent(canvas.extent())
        layout.addLayoutItem(map_item)
        
        # Geometry for a two-column layout: map on the left, a fixed-width
        # legend/scalebar/summary column on the right (landscape) or stacked
        # below the map (portrait). Chosen so the right column's items never
        # cross the map's own right edge and never run past the page's own
        # margins -- a previous version placed the legend column 15mm inside
        # the map's right edge, invisible on a small/zoomed-in map but a
        # real overlap once zoom_to_layer above made full-country maps the
        # norm. Only the landscape numbers have been confirmed against a
        # live full-Yemen export; portrait is analogous but unverified.
        portrait = page_orientation.lower() == "portrait"
        if portrait:
            map_x, map_y, map_w, map_h = 15, 26, 180, 190
            col_x, col_w = 15, 180
            legend_y, legend_h = map_y + map_h + 4, 45
            scalebar_y, scalebar_h = legend_y + legend_h + 4, 10
            body_y, body_h = scalebar_y + scalebar_h + 4, 13
            north_x, north_y = 175, scalebar_y
            title_w = 180
        else:
            map_x, map_y, map_w, map_h = 15, 26, 175, 155
            col_x, col_w = 195, 95
            legend_y, legend_h = map_y, 88
            body_y, body_h = legend_y + legend_h + 4, 87
            scalebar_y, scalebar_h = map_y + map_h + 3, 12
            north_x, north_y = map_x + map_w - 12, scalebar_y
            title_w = col_x + col_w - map_x

        map_item.attemptMove(QgsLayoutPoint(map_x, map_y, LAYOUT_MM))
        map_item.attemptResize(QgsLayoutSize(map_w, map_h, LAYOUT_MM))

        # Title Label -- spans the full page width (map + side column) as a
        # masthead, rather than only over the map.
        title_label = QgsLayoutItemLabel(layout)
        title_label.setText(title)
        layout.addLayoutItem(title_label)
        title_label.attemptMove(QgsLayoutPoint(map_x, 8, LAYOUT_MM))
        title_label.attemptResize(QgsLayoutSize(title_w, 14, LAYOUT_MM))

        # Legend Item -- resizeToContents defaults to True, which always
        # expands the item to its full natural content width regardless of
        # any attemptResize() call, so a legend with long category labels
        # simply overflows past the page's right edge with no visible error
        # (a real bug seen in a live export). Disabling it first makes the
        # explicit resize below actually constrain the box, which also makes
        # QGIS wrap long labels within that width instead of overflowing.
        legend = QgsLayoutItemLegend(layout)
        legend.setLinkedMap(map_item)
        legend.setResizeToContents(False)
        layout.addLayoutItem(legend)
        legend.attemptMove(QgsLayoutPoint(col_x, legend_y, LAYOUT_MM))
        legend.attemptResize(QgsLayoutSize(col_w, legend_h, LAYOUT_MM))

        # Scalebar Item -- a fixed 1000m/segment setting only makes sense at
        # whatever single zoom level it was tuned for; at a full-country
        # extent (e.g. after zoom_to_layer above) that produces a segment
        # count/label so far off the map's actual scale that the numbers and
        # bar visibly overlap in the export (seen live). applyDefaultSize()
        # picks a sensible segment count/size FOR THE MAP'S CURRENT SCALE
        # instead of a value hand-tuned for one specific zoom level.
        scalebar = QgsLayoutItemScaleBar(layout)
        scalebar.setLinkedMap(map_item)
        scalebar.setUnits(DISTANCE_KM)
        scalebar.applyDefaultSize(DISTANCE_KM)
        layout.addLayoutItem(scalebar)
        scalebar.attemptMove(QgsLayoutPoint(map_x, scalebar_y, LAYOUT_MM))
        scalebar.attemptResize(QgsLayoutSize(min(90, map_w - 15), scalebar_h, LAYOUT_MM))

        # North Arrow Picture Item
        north_arrow = QgsLayoutItemPicture(layout)
        svg_paths = QgsApplication.svgPaths()
        default_arrow_path = ""
        if svg_paths:
            candidate = os.path.join(svg_paths[0], "arrows", "NorthArrow_02.svg")
            if os.path.exists(candidate):
                default_arrow_path = candidate

        if default_arrow_path:
            # No setMode()/ModeRaster on QgsLayoutItemPicture -- that call
            # doesn't exist on this class. setPicturePath()'s format arg
            # defaults to FormatUnknown, which auto-detects SVG vs. raster
            # from the file extension, so a single-arg call is correct here.
            north_arrow.setPicturePath(default_arrow_path)
            layout.addLayoutItem(north_arrow)
            north_arrow.attemptMove(QgsLayoutPoint(north_x, north_y, LAYOUT_MM))
            north_arrow.attemptResize(QgsLayoutSize(12, 12, LAYOUT_MM))

        # Optional summary/sitrep panel -- placed below the legend, same
        # column width, so long lines wrap within the page instead of
        # overflowing into the map. Plain QgsLayoutItemLabel default mode
        # (font text, not HTML) is used deliberately: it's what title_label
        # above already relies on working without an explicit setMode()
        # call, so this stays on the same, already-proven code path rather
        # than introducing an unverified enum reference.
        if body_text:
            body_label = QgsLayoutItemLabel(layout)
            body_label.setText(body_text)
            layout.addLayoutItem(body_label)
            body_label.attemptMove(QgsLayoutPoint(col_x, body_y, LAYOUT_MM))
            body_label.attemptResize(QgsLayoutSize(col_w, body_h, LAYOUT_MM))

        res_msg = {"success": True, "layout_name": layout_name, "orientation": page_orientation}

        if output_path:
            ext = os.path.splitext(output_path)[1].lower()
            exporter = QgsLayoutExporter(layout)
            if ext == ".pdf":
                pdf_settings = QgsLayoutExporter.PdfExportSettings()
                pdf_settings.dpi = dpi
                result = exporter.exportToPdf(output_path, pdf_settings)
            elif ext in (".png", ".jpg", ".jpeg"):
                image_settings = QgsLayoutExporter.ImageExportSettings()
                image_settings.dpi = dpi
                result = exporter.exportToImage(output_path, image_settings)
            else:
                return {"error": f"Unsupported output_path extension '{ext}' -- use .pdf, .png, .jpg, or .jpeg."}

            if result != QgsLayoutExporter.Success:
                return {"error": f"Export to '{output_path}' failed (QgsLayoutExporter result code {result})."}
            res_msg["output_path"] = output_path
            res_msg["dpi"] = dpi

        return res_msg
    except Exception as e:
        return {"error": f"create_print_layout failed: {e}"}
