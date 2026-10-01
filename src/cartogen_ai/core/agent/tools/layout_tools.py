# -*- coding: utf-8 -*-
"""
Print Layout Composition Tools for Cartogen AI.
Generates automated QgsPrintLayout compositions with title, map item, legend, scalebar, and north arrow.
"""

import math
import os
from .registry import register_tool

try:
    from qgis.core import (
        QgsProject, QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLegend,
        QgsLayoutItemScaleBar, QgsLayoutItemLabel, QgsLayoutItemPicture,
        QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes, QgsLayoutExporter,
        QgsApplication, QgsCoordinateTransform, QgsLayoutItemMapGrid,
        QgsLayoutItemMapOverview, QgsRectangle
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


# Calibrated from a real live render (QGIS 4.2.2, python-qgis.bat,
# QgsLayoutExporter.exportToImage, PNG visually inspected 2026-09-11,
# BUG-2026-09-11-1): QgsLayoutItemLabel's default font rendered one line at
# roughly 6mm tall and fit roughly 110 characters within a 180mm-wide box.
# Deliberately conservative (errs toward truncating a little early) -- not a
# generic font-metrics API call, since QgsLayoutItemLabel exposes no cheap
# way to query its actual print-DPI rendered size before drawing.
_LABEL_LINE_HEIGHT_MM = 6.0
_LABEL_CHARS_PER_MM_WIDTH = 110 / 180.0


def _fit_text_to_box(text, box_w_mm, box_h_mm):
    """Truncates text to what a QgsLayoutItemLabel-sized box can actually
    hold, by whole words, appending an ellipsis if truncated. Exists because
    QgsLayoutItemLabel does not clip content to its own box -- confirmed
    live (BUG-2026-09-11-1): body_text longer than the box's line budget
    silently overflowed downward into the standing disclaimer footer below
    it, in portrait orientation specifically. A larger box budget alone
    doesn't fix this for an unbounded caller-supplied string; bounding the
    actual text content does, regardless of exactly how generous the box
    turns out to be in either orientation."""
    max_lines = max(1, int(box_h_mm // _LABEL_LINE_HEIGHT_MM))
    max_chars = max(20, int(max_lines * box_w_mm * _LABEL_CHARS_PER_MM_WIDTH))
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return truncated + "…"


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


def _nice_interval(raw):
    """Rounds raw (a rough 'one grid line every this many map units' target) up to the
    nearest 1/2/5 x 10^n -- the same 'nice round number' convention QGIS's own scale bar
    uses, so graticule lines land on readable values (2 degrees, 0.5 degrees, 50000 meters)
    instead of an arbitrary fraction. Pure Python, no QGIS needed."""
    if raw <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(raw))
    for step in (1, 2, 5, 10):
        candidate = step * magnitude
        if candidate >= raw:
            return candidate
    return 10 * magnitude


def _format_scale_denominator(n):
    """1:1234567 -> '1:1,234,567' -- the textual representative-fraction scale
    cartographic convention expects alongside (not instead of) a graphical scale bar.

    A map item with no real extent (headless layout, empty canvas) reports a NaN/inf/zero
    scale; int(round(nan)) raises, which silently dropped the whole CRS/scale info label
    (seen in the live styling tests, 2026-10-01), so degrade to text instead."""
    try:
        if n is None or n != n or n in (float("inf"), float("-inf")) or n <= 0:
            return "unavailable"
        return f"1:{int(round(n)):,}"
    except (TypeError, ValueError, OverflowError):
        return "unavailable"


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
    "area of interest. `title` and `body_text` must only describe real, verified findings -- never "
    "invent incidents, casualties, threat assessments, severity ratings, or other real-world claims "
    "to make a report look complete. If you don't have verified data for what's being asked, say so "
    "in your chat response instead of writing placeholder or invented content into this layout -- a "
    "printed/exported layout reads as an authoritative finished document, not a draft, so anything "
    "fabricated here is far more likely to be trusted and acted on than the same claim in chat. Every "
    "export from this tool carries a standing disclaimer footer for exactly this reason, but that "
    "does not excuse writing fabricated content in the first place. Also includes a coordinate "
    "graticule, a CRS/datum + representative-fraction scale label ('1:N', alongside the graphical "
    "scale bar), and -- when include_inset_map is true -- a small locator/inset map showing where "
    "the main map sits within a wider surrounding area.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "page_orientation": {"type": "string", "description": "'Landscape' (default) or 'Portrait'."},
            "output_path": {"type": "string", "description": "Where to export -- '.pdf' for a vector PDF, '.png'/'.jpg'/'.jpeg' for a raster image. Omit to create the layout in the project without exporting."},
            "dpi": {"type": "integer", "description": "Export resolution in DPI, for both PDF and image export. Defaults to 300 (print quality)."},
            "body_text": {"type": "string", "description": "Optional summary/sitrep text shown in a panel on the layout (e.g. priority findings, data sources)."},
            "zoom_to_layer": {"type": "string", "description": "Name of a layer to fit the map to its full extent before capturing it, e.g. the national boundary layer for a full-country sitrep map. Omit to use whatever extent the canvas currently shows."},
            "template": {"type": "string", "description": "'standard' (default) or 'access_map': for the result of a service-area / facility-access analysis. Fits the map to the reach layer when zoom_to_layer is omitted, lists the reach polygon, access points and cost-graded roads first in the legend, and (when body_text is empty) adds a short 'how to read this map' guide for the layers present."},
            "include_inset_map": {"type": "boolean", "description": "Add a small locator/inset map (zoomed out ~6x from the main map, same center) showing the main map's location within its wider region. Defaults to true."},
        },
        "required": ["title"],
    },
)
def create_print_layout(title: str, page_orientation: str = "Landscape", output_path: str = "", dpi: int = 300, body_text: str = "", zoom_to_layer: str = "", include_inset_map: bool = True, template: str = "standard"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    try:
        template = "access_map" if str(template or "").lower() == "access_map" else "standard"
        if template == "access_map":
            from . import layout_style
            visible = [e["name"] for e in layout_style.visible_layer_entries() if e["visible"]]
            if not zoom_to_layer:
                zoom_to_layer = layout_style.access_zoom_layer_name(visible) or ""
            if not body_text:
                body_text = layout_style.access_reading_guide(visible)
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
        map_item.setId("MAP_MAIN")

        # Geometry for a two-column layout: map on the left, a fixed-width
        # legend/scalebar/summary column on the right (landscape) or stacked
        # below the map (portrait). Chosen so the right column's items never
        # cross the map's own right edge and never run past the page's own
        # margins -- a previous version placed the legend column 15mm inside
        # the map's right edge, invisible on a small/zoomed-in map but a
        # real overlap once zoom_to_layer above made full-country maps the
        # norm. Only the landscape numbers have been confirmed against a
        # live full-Yemen export; portrait is analogous but unverified.
        # Fixed budget for the new CRS/datum + representative-fraction-scale info row
        # (Phase 3, 2026-09-19) -- carved out of map_h in both orientations rather than
        # touching any already-live-verified footer/body position (BUG-2026-09-11-1's
        # footer-overlap history is exactly the failure mode this avoids repeating).
        INFO_ROW_H = 6
        INFO_ROW_GAP = 2

        portrait = page_orientation.lower() == "portrait"
        page_width, page_height = (210, 297) if portrait else (297, 210)
        if portrait:
            map_x, map_y, map_w, map_h = 15, 26, 180, 190 - (INFO_ROW_H + INFO_ROW_GAP)
            col_x, col_w = 15, 180
            info_y, info_h = map_y + map_h + 2, INFO_ROW_H
            # legend_h shrunk 45->35 (2026-09-11, BUG-2026-09-11-1) to help
            # fund a realistic body_h below -- still ample for the handful of
            # categories a humanitarian export's legend typically carries.
            legend_y, legend_h = info_y + info_h + 4, 35
            scalebar_y, scalebar_h = legend_y + legend_h + 4, 10
            # Footer pinned to a FIXED distance from the page bottom, not
            # derived from body_y+body_h -- BUG-2026-09-11-1, live-confirmed
            # (real QgsLayoutExporter.exportToImage PNG, visually inspected):
            # QgsLayoutItemLabel does not clip content to its own box, so the
            # old body_h=6 (roughly one line) meant ANY body_text longer than
            # that silently overflowed down and visually overlapped the
            # safety-critical disclaimer footer -- exactly the multi-line
            # "bullets/findings" usage this tool's own schema description
            # encourages. Pinning the footer here first, then giving body_h
            # whatever real room remains above it (instead of a tiny
            # hardcoded constant), fixes both: the footer always sits at the
            # same predictable page position regardless of body_text length,
            # and body gets a realistic multi-line budget. Does not fully
            # eliminate overflow for an extreme body_text (the label still
            # doesn't clip) -- see BUG-2026-09-11-1 for that residual caveat.
            footer_h = 8
            footer_margin = 6
            footer_y = page_height - footer_h - footer_margin
            body_y = scalebar_y + scalebar_h + 4
            body_h = max(6, footer_y - body_y - 4)
            north_x, north_y = 175, scalebar_y
            title_w = 180
        else:
            map_x, map_y, map_w, map_h = 15, 26, 175, 155 - (INFO_ROW_H + INFO_ROW_GAP)
            col_x, col_w = 195, 95
            legend_y, legend_h = map_y, 88
            # body_h shrunk from 87 to 78 (2026-09-02) to leave room for the
            # standing disclaimer footer below, without touching any of the
            # map/legend/scalebar/title numbers confirmed against a live
            # full-Yemen export.
            body_y, body_h = legend_y + legend_h + 4, 78
            info_y, info_h = map_y + map_h + 2, INFO_ROW_H
            scalebar_y, scalebar_h = info_y + info_h + 3, 12
            north_x, north_y = map_x + map_w - 12, scalebar_y
            title_w = col_x + col_w - map_x
            # Landscape's footer position is still derived from body_y+body_h
            # (unlike portrait's fixed pinning above) -- body_h=78 here is
            # generous enough that this has been live-confirmed not to
            # collide (2026-09-05 real chat-driven session), so left as-is
            # rather than changing a path that's already been verified live.
            footer_y = body_y + body_h + 2
            footer_h = max(4, min(8, page_height - footer_y - 2))

        map_item.attemptMove(QgsLayoutPoint(map_x, map_y, LAYOUT_MM))
        map_item.attemptResize(QgsLayoutSize(map_w, map_h, LAYOUT_MM))

        # Title Label -- spans the full page width (map + side column) as a
        # masthead, rather than only over the map.
        title_label = QgsLayoutItemLabel(layout)
        title_label.setText(title)
        layout.addLayoutItem(title_label)
        title_label.setId("TITLE")
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
        legend.setId("LEGEND")
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
        scalebar.setId("SCALEBAR")
        scalebar.attemptMove(QgsLayoutPoint(map_x, scalebar_y, LAYOUT_MM))
        scalebar.attemptResize(QgsLayoutSize(min(90, map_w - 15), scalebar_h, LAYOUT_MM))

        # CRS/datum + textual representative-fraction scale ("1:N") -- ISO 19115/OCHA
        # cartographic metadata the exported layout previously had no way to show, sitting
        # alongside (not replacing) the graphical scale bar above, which alone doesn't
        # state the CRS/datum or an exact numeric ratio. Uses the map item's own crs()/
        # scale() (set after setExtent() above, so this reflects the actual rendered
        # extent) rather than the source layer's CRS, since the map item may be
        # reprojecting on render.
        info_warning = None
        try:
            map_crs = map_item.crs()
            crs_text = f"{map_crs.authid()} ({map_crs.description()})" if map_crs and map_crs.isValid() else "CRS unknown"
            scale_text = _format_scale_denominator(map_item.scale())
            info_label = QgsLayoutItemLabel(layout)
            info_label.setText(f"{crs_text}   |   Scale {scale_text}")
            layout.addLayoutItem(info_label)
            info_label.setId("MAP_INFO")
            info_label.attemptMove(QgsLayoutPoint(map_x, info_y, LAYOUT_MM))
            info_label.attemptResize(QgsLayoutSize(map_w, info_h, LAYOUT_MM))
        except Exception as e:
            info_warning = f"Could not add the CRS/scale info label to this layout: {e}"

        # Coordinate graticule -- OCHA/humanitarian map standards call for a coordinate
        # grid for tactical navigation, which the layout previously had no way to show.
        # Interval derived from the map's own extent (roughly one line per quarter of the
        # visible width, rounded to a nice 1/2/5 value) so it's proportionate whether the
        # map is a single city or a full country. Best-effort: wrapped so a grid-API
        # mismatch on some QGIS version degrades to "no grid" rather than failing the
        # whole layout, consistent with this file's existing method is None guards
        # elsewhere for the same class of cross-version risk.
        grid_warning = None
        try:
            grid_extent = map_item.extent()
            raw_interval = max(grid_extent.width(), grid_extent.height()) / 4.0
            interval = _nice_interval(raw_interval)
            grid = QgsLayoutItemMapGrid("Graticule", map_item)
            grid.setIntervalX(interval)
            grid.setIntervalY(interval)
            grid.setEnabled(True)
            grid.setAnnotationEnabled(True)
            map_item.grids().addGrid(grid)
        except Exception as e:
            grid_warning = f"Could not add a coordinate graticule to this layout: {e}"

        # Locator/inset map -- shows where the main map sits within a wider surrounding
        # area, an OCHA-standard element the layout previously had no way to show. Zoomed
        # out from the main map's own extent (same center, ~6x wider) rather than
        # depending on a separate administrative-boundary layer being present, so this
        # works on any project. Placed in the map's own top-left corner (the north arrow
        # already occupies the top-right in both orientations) via a QgsLayoutItemMapOverview
        # linked back to the main map, which draws the "you are here" outline automatically.
        inset_warning = None
        if include_inset_map:
            try:
                main_extent = map_item.extent()
                cx, cy = main_extent.center().x(), main_extent.center().y()
                zoom_factor = 6.0
                half_w = main_extent.width() * zoom_factor / 2.0
                half_h = main_extent.height() * zoom_factor / 2.0
                inset_extent = QgsRectangle(cx - half_w, cy - half_h, cx + half_w, cy + half_h)

                inset_size = 32
                inset_map = QgsLayoutItemMap(layout)
                inset_map.setRect(20, 20, 20, 20)
                inset_map.setExtent(inset_extent)
                if map_item.crs() and map_item.crs().isValid():
                    inset_map.setCrs(map_item.crs())
                layout.addLayoutItem(inset_map)
                inset_map.setId("INSET_MAP")
                inset_map.attemptMove(QgsLayoutPoint(map_x + 2, map_y + 2, LAYOUT_MM))
                inset_map.attemptResize(QgsLayoutSize(inset_size, inset_size, LAYOUT_MM))
                inset_map.setFrameEnabled(True)

                overview = QgsLayoutItemMapOverview("Locator", inset_map)
                overview.setLinkedMap(map_item)
                inset_map.overviews().addOverview(overview)
            except Exception as e:
                inset_warning = f"Could not add a locator/inset map to this layout: {e}"

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
            north_arrow.setId("NORTH_ARROW")
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
            body_label.setText(_fit_text_to_box(body_text, col_w, body_h))
            layout.addLayoutItem(body_label)
            body_label.setId("BODY_TEXT")
            body_label.attemptMove(QgsLayoutPoint(col_x, body_y, LAYOUT_MM))
            body_label.attemptResize(QgsLayoutSize(col_w, body_h, LAYOUT_MM))

        footer_label = QgsLayoutItemLabel(layout)
        footer_label.setText("AI-generated -- verify before operational, humanitarian, or safety use.")
        layout.addLayoutItem(footer_label)
        footer_label.setId("FOOTER")
        footer_x = map_x
        footer_w = (col_x + col_w) - map_x
        # footer_y/footer_h are already set above (portrait: pinned to a
        # fixed page-bottom distance; landscape: derived from body_y+body_h,
        # unchanged) -- not recomputed here so portrait's fix above actually
        # takes effect instead of being immediately overwritten by the old
        # body-derived formula.
        footer_label.attemptMove(QgsLayoutPoint(footer_x, footer_y, LAYOUT_MM))
        footer_label.attemptResize(QgsLayoutSize(footer_w, footer_h, LAYOUT_MM))

        # Look only (positions/sizes above are untouched): typography, panels, a legend of the VISIBLE layers, the
        # preparation date and a classification prefix. See layout_style.py for what was wrong before.
        style_report = {}
        try:
            from . import layout_style
            style_report = layout_style.apply_layout_style(layout, LAYOUT_MM, template=template)
        except Exception as style_error:
            style_report = {"warnings": [f"layout styling failed: {style_error}"]}

        res_msg = {"success": True, "layout_name": layout_name, "orientation": page_orientation, "template": template}
        if style_report.get("legend_layers") is not None:
            res_msg["legend_layers"] = style_report.get("legend_layers", [])
        if style_report.get("classification"):
            res_msg["classification"] = style_report["classification"]
        if style_report.get("warnings"):
            res_msg["style_warnings"] = style_report["warnings"]
        if info_warning:
            res_msg["info_label_warning"] = info_warning
        if grid_warning:
            res_msg["grid_warning"] = grid_warning
        if inset_warning:
            res_msg["inset_warning"] = inset_warning

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


@register_tool(
    "list_layouts",
    "List the print layouts already in the current QGIS project by name -- lets the agent check "
    "what layouts exist (e.g. before deciding whether to build a new one with create_print_layout "
    "or address an existing one) instead of guessing layout names. Point 21 of "
    "docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md (a project inspector) -- covers "
    "layouts only; QGIS Map Themes are a separate concept, listed by list_map_themes instead "
    "(point 16 of the same review, project_tools.py).",
    {"type": "object", "properties": {}, "required": []},
)
def list_layouts():
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layout_manager = QgsProject.instance().layoutManager()
    return {"layouts": [layout.name() for layout in layout_manager.printLayouts()]}


def _find_layout_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    for layout in QgsProject.instance().layoutManager().printLayouts():
        if layout.name() == name:
            return layout
    return None


@register_tool(
    "export_layout_atlas",
    "Exports one file PER FEATURE of a coverage layer from an existing print layout -- e.g. one "
    "PDF per district, one PNG per health facility catchment -- using QgsLayoutAtlas. This is the "
    "full-atlas half of point 15 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md; "
    "list_layout_items/update_layout_item_text (the other half) address items within ONE layout, "
    "this generates MANY layouts (one per feature). Only works on a layout built by "
    "create_print_layout, since it re-points that layout's MAP_MAIN item to follow the atlas -- "
    "there is no addressable map item on a hand-built layout to atlas-drive. Each output file is "
    "named from filename_field's value on that feature (e.g. a district-name field), sanitized for "
    "use as a filename; a non-unique or empty field value across features will silently overwrite "
    "an earlier output with the same name, so pick a field that's actually unique per feature "
    "(a P-code, not a display name that repeats).",
    {
        "type": "object",
        "properties": {
            "layout_name": {"type": "string", "description": "An existing layout built by create_print_layout."},
            "coverage_layer_name": {"type": "string", "description": "The layer whose features drive one output page each, e.g. an admin-boundary layer."},
            "output_directory": {"type": "string", "description": "Directory to write the per-feature files into. Created if it doesn't exist."},
            "filename_field": {"type": "string", "description": "Field on coverage_layer_name whose value names each output file. Should be unique per feature."},
            "output_format": {"type": "string", "description": "'pdf' (default), 'png', 'jpg', or 'jpeg'."},
            "dpi": {"type": "integer", "description": "Export resolution in DPI. Defaults to 300 (print quality)."},
        },
        "required": ["layout_name", "coverage_layer_name", "output_directory", "filename_field"],
    },
)
def export_layout_atlas(layout_name: str, coverage_layer_name: str, output_directory: str,
                         filename_field: str, output_format: str = "pdf", dpi: int = 300):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    layout = _find_layout_by_name(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found"}

    coverage_layer = _find_layer_by_name(coverage_layer_name)
    if coverage_layer is None:
        return {"error": f"Layer '{coverage_layer_name}' not found"}

    if coverage_layer.fields().indexOf(filename_field) == -1:
        available = [f.name() for f in coverage_layer.fields()]
        return {"error": f"Field '{filename_field}' not found on '{coverage_layer_name}'. Available fields: {available}"}

    # Requires the MAP_MAIN id create_print_layout always assigns -- a
    # hand-built layout (via execute_pyqgis_script, which this tool's own
    # description on create_print_layout already discourages) has no
    # equivalent addressable map item to atlas-drive.
    map_item = layout.itemById("MAP_MAIN")
    if map_item is None or not hasattr(map_item, "setAtlasDriven"):
        return {"error": f"Layout '{layout_name}' has no MAP_MAIN map item -- only layouts built by create_print_layout can be atlas-exported."}

    output_format = output_format.lower().lstrip(".")
    if output_format not in ("pdf", "png", "jpg", "jpeg"):
        return {"error": f"Unsupported output_format '{output_format}' -- use pdf, png, jpg, or jpeg."}

    try:
        os.makedirs(output_directory, exist_ok=True)
    except OSError as e:
        return {"error": f"Could not create output_directory '{output_directory}': {e}"}

    try:
        atlas = layout.atlas()
        atlas.setCoverageLayer(coverage_layer)
        atlas.setEnabled(True)
        # QgsExpression field-reference syntax -- a bare field name in
        # double quotes -- not a Python f-string escape; matches the same
        # quoting every other tool in this codebase uses when it builds an
        # expression string from a caller-supplied field name (see
        # buffer_analysis, calculate_area).
        expr_ok, expr_err = atlas.setFilenameExpression(f'"{filename_field}"')
        if not expr_ok:
            return {"error": f"Invalid filename expression for field '{filename_field}': {expr_err}"}
        map_item.setAtlasDriven(True)

        if output_format == "pdf":
            settings = QgsLayoutExporter.PdfExportSettings()
        else:
            settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = dpi

        # No QgsLayoutExporter overload accepts (atlas, imageSettings) --
        # confirmed live, raises TypeError. exportToPdfs(atlas, ...) exists
        # but only for PDF. Manual atlas.first()/.next() iteration plus the
        # ordinary per-page exportToPdf/exportToImage overload works for
        # BOTH formats identically, confirmed live -- used uniformly here
        # rather than branching between a static atlas-aware call for PDF
        # and a manual loop only for images.
        output_files = []
        atlas.beginRender()
        try:
            has_feature = atlas.first()
            if not has_feature and atlas.count() == 0:
                return {"error": f"Coverage layer '{coverage_layer_name}' has no features -- nothing to export."}
            while has_feature:
                raw_name = atlas.currentFilename() or f"page_{len(output_files) + 1}"
                safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in raw_name).strip() or f"page_{len(output_files) + 1}"
                out_path = os.path.join(output_directory, f"{safe_name}.{output_format}")
                exporter = QgsLayoutExporter(layout)
                if output_format == "pdf":
                    result = exporter.exportToPdf(out_path, settings)
                else:
                    result = exporter.exportToImage(out_path, settings)
                if result != QgsLayoutExporter.Success:
                    return {"error": f"Atlas export failed on feature '{raw_name}' (QgsLayoutExporter result code {result})."}
                output_files.append(out_path)
                has_feature = atlas.next()
        finally:
            atlas.endRender()

        return {
            "success": True,
            "layout_name": layout_name,
            "coverage_layer_name": coverage_layer_name,
            "feature_count": len(output_files),
            "output_directory": output_directory,
            "output_files": output_files,
        }
    except Exception as e:
        return {"error": f"export_layout_atlas failed: {e}"}


@register_tool(
    "list_layout_items",
    "Lists the addressable items in a print layout -- id, type, and current text (for text "
    "items) -- so the agent can check what's actually in a layout before editing it with "
    "update_layout_item_text, instead of guessing. create_print_layout gives every item it "
    "builds a stable id (MAP_MAIN, TITLE, LEGEND, SCALEBAR, NORTH_ARROW, BODY_TEXT, FOOTER -- "
    "NORTH_ARROW/BODY_TEXT only appear when that item was actually built). Point 15 of "
    "docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md (stable item addressability -- full "
    "QgsLayoutAtlas per-feature pagination is a separate capability, export_layout_atlas).",
    {
        "type": "object",
        "properties": {"layout_name": {"type": "string"}},
        "required": ["layout_name"],
    },
)
def list_layout_items(layout_name: str):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layout = _find_layout_by_name(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found"}
    items = []
    for item in layout.items():
        # layout.items() also yields internal plumbing (the page's own
        # QGraphicsRectItem border, the QgsLayoutItemPage itself) that never
        # has a real id -- confirmed live: QGraphicsRectItem has no id()
        # method at all, QgsLayoutItemPage.id() returns "". Only surface
        # items this tool (or the caller) actually gave a stable id to.
        item_id = item.id() if hasattr(item, "id") else ""
        if not item_id:
            continue
        entry = {"id": item_id, "type": type(item).__name__}
        if hasattr(item, "text"):
            try:
                entry["text"] = item.text()
            except Exception:
                pass
        items.append(entry)
    return {"success": True, "layout_name": layout_name, "items": items}


@register_tool(
    "update_layout_item_text",
    "Updates the text of one existing item in a print layout (e.g. a stale title or summary "
    "panel) by its stable id -- without rebuilding the whole layout with create_print_layout. "
    "Use list_layout_items first to see what ids exist. Only works on text items (TITLE, "
    "BODY_TEXT, FOOTER); MAP_MAIN/LEGEND/SCALEBAR/NORTH_ARROW have no settable text. Point 15 "
    "of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.",
    {
        "type": "object",
        "properties": {
            "layout_name": {"type": "string"},
            "item_id": {"type": "string", "description": "Stable id from list_layout_items, e.g. 'TITLE'."},
            "text": {"type": "string"},
        },
        "required": ["layout_name", "item_id", "text"],
    },
)
def update_layout_item_text(layout_name: str, item_id: str, text: str):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layout = _find_layout_by_name(layout_name)
    if layout is None:
        return {"error": f"Layout '{layout_name}' not found"}
    item = layout.itemById(item_id)
    if item is None:
        return {"error": f"No item with id '{item_id}' in layout '{layout_name}'."}
    if not hasattr(item, "setText"):
        return {"error": f"Item '{item_id}' ({type(item).__name__}) has no settable text."}
    try:
        item.setText(text)
        item.refresh()
        return {"success": True, "layout_name": layout_name, "item_id": item_id}
    except Exception as e:
        return {"error": f"update_layout_item_text failed: {e}"}
