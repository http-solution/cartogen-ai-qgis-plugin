# -*- coding: utf-8 -*-
"""Typography, panels and a legend that matches the map, for create_print_layout (visualization gap analysis, 2026-10-01).

What the layout looked like before (read from create_print_layout, not assumed): every label used QGIS's default font; no
panel had a frame or background; the legend was left in AUTO-UPDATE mode, which lists every layer in the project -- including
the hidden helper layers this plugin now creates (plain reached roads, intersections, scratch outputs) and the basemap --
so a legend could name layers that are not drawn on the map; there was no preparation date and no classification line.

What this applies, per item id (TITLE, LEGEND, SCALEBAR, MAP_INFO, BODY_TEXT, FOOTER, MAP_MAIN, INSET_MAP):
- a typographic scale (masthead title, panel text, small footer) and one palette;
- thin frames and a light background on the panels, a frame on the map;
- a legend with an explicit model: ONLY the layers that are visible on the map, basemap excluded, filtered to what the map
  extent actually shows;
- the preparation date in the info row, and a classification prefix on the footer when any visible layer is tagged
  RESTRICTED or SENSITIVE.
Positions and sizes are NOT touched: the geometry carries a documented history of overlap bugs (BUG-2026-09-11-1) that was
live-verified, so this module only changes how items look. Every item is styled independently and best-effort: a failure
is reported as a warning and the layout is still produced.
"""
import datetime

try:
    from qgis.core import (
        Qgis, QgsLayoutMeasurement, QgsProject, QgsTextFormat, QgsUnitTypes,
    )
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QColor, QFont
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# One palette: the masthead is dark slate with light text; panels are near-white with a thin slate frame.
PALETTE = {
    "masthead_bg": "#1f2d3a", "masthead_fg": "#ffffff", "text": "#1f2d3a", "muted": "#5b6b78",
    "panel_bg": "#f7f8f9", "frame": "#8c99a4",
}
# Sizes in points.
TYPE_SCALE = {"title": 20.0, "panel": 9.0, "info": 8.0, "legend_title": 10.0, "legend_item": 8.0, "footer": 7.0}
FRAME_MM = {"panel": 0.3, "map": 0.5}

_SENSITIVITY_RANK = {"PUBLIC": 0, "INTERNAL": 1, "RESTRICTED": 2, "SENSITIVE": 3}
_PROTECTED = ("RESTRICTED", "SENSITIVE")


# ---------------------------------------------------------------- pure --

def legend_layer_ids(entries):
    """Ids, in tree order, of the layers that belong in the legend. Pure.

    entries: iterable of dicts {id, name, visible, provider}. Excluded: layers not visible on the map, basemaps (a web
    tile service is context, not a thematic layer) and the plugin's own analysis helpers (names containing '_lines_')."""
    keep = []
    for e in entries:
        if not e.get("visible"):
            continue
        if str(e.get("provider") or "").lower() in ("wms", "xyz", "arcgismapserver", "vectortile"):
            continue
        if "_lines_" in str(e.get("name") or ""):
            continue
        keep.append(e["id"])
    return keep


def highest_protected_level(levels):
    """The most restrictive of RESTRICTED/SENSITIVE among `levels`, or None. Pure."""
    best = None
    for level in levels or []:
        if level in _PROTECTED and (best is None or _SENSITIVITY_RANK[level] > _SENSITIVITY_RANK[best]):
            best = level
    return best


def classification_prefix(levels):
    level = highest_protected_level(levels)
    return f"CLASSIFICATION: {level} -- " if level else ""


def prepared_stamp(today=None):
    d = today or datetime.date.today()
    return f"Prepared {d.isoformat()}"


def footer_text(base, levels):
    return classification_prefix(levels) + base


def info_text(base, today=None):
    return f"{base}   |   {prepared_stamp(today)}"


# ----------------------------------------------------------- QGIS half --

def _points_unit():
    unit = getattr(getattr(Qgis, "RenderUnit", None), "Points", None)
    return unit if unit is not None else getattr(QgsUnitTypes, "RenderPoints", None)


def text_format(size_pt, color_hex, bold=False, italic=False):
    fmt = QgsTextFormat()
    font = QFont()
    font.setBold(bool(bold))
    font.setItalic(bool(italic))
    fmt.setFont(font)
    fmt.setSize(float(size_pt))
    unit = _points_unit()
    if unit is not None:
        fmt.setSizeUnit(unit)
    fmt.setColor(QColor(color_hex))
    return fmt


def _frame(item, width_mm, layout_mm):
    item.setFrameEnabled(True)
    item.setFrameStrokeColor(QColor(PALETTE["frame"]))
    item.setFrameStrokeWidth(QgsLayoutMeasurement(width_mm, layout_mm))


def _panel(item, layout_mm):
    _frame(item, FRAME_MM["panel"], layout_mm)
    item.setBackgroundEnabled(True)
    item.setBackgroundColor(QColor(PALETTE["panel_bg"]))


def visible_layer_entries(project=None):
    """[{id, name, visible, provider, layer}] in layer-tree order for the whole project."""
    project = project or QgsProject.instance()
    out = []
    for node in project.layerTreeRoot().findLayers():
        layer = node.layer()
        if layer is None:
            continue
        out.append({"id": layer.id(), "name": layer.name(), "visible": node.isVisible(),
                    "provider": layer.providerType() if hasattr(layer, "providerType") else "", "layer": layer})
    return out


def apply_layout_style(layout, layout_mm, project=None, today=None):
    """Styles the items create_print_layout made. Returns {'warnings': [...], 'legend_layers': [names], 'classification': str}."""
    warnings = []
    if not QGIS_AVAILABLE:
        return {"warnings": ["QGIS not available"], "legend_layers": [], "classification": ""}
    project = project or QgsProject.instance()
    entries = visible_layer_entries(project)
    ids = legend_layer_ids(entries)
    by_id = {e["id"]: e["layer"] for e in entries}

    levels = []
    try:
        from ...models import sensitivity
        for e in entries:
            if e["visible"]:
                levels.append(sensitivity.get_layer_sensitivity(e["layer"]).get("level"))
    except Exception as exc:
        warnings.append(f"sensitivity lookup failed: {exc}")

    def step(name, fn):
        try:
            fn()
        except Exception as exc:
            warnings.append(f"{name}: {type(exc).__name__}: {exc}")

    def item(item_id):
        return layout.itemById(item_id)

    def title():
        label = item("TITLE")
        label.setTextFormat(text_format(TYPE_SCALE["title"], PALETTE["masthead_fg"], bold=True))
        label.setBackgroundEnabled(True)
        label.setBackgroundColor(QColor(PALETTE["masthead_bg"]))
        label.setMarginX(3.0)
        label.setMarginY(1.0)
        label.setVAlign(Qt.AlignmentFlag.AlignVCenter)

    def map_frame():
        _frame(item("MAP_MAIN"), FRAME_MM["map"], layout_mm)
        inset = item("INSET_MAP")
        if inset is not None:
            _frame(inset, FRAME_MM["panel"], layout_mm)

    def info():
        label = item("MAP_INFO")
        if label is None:
            return
        label.setText(info_text(label.text(), today))
        label.setTextFormat(text_format(TYPE_SCALE["info"], PALETTE["muted"]))

    def body():
        label = item("BODY_TEXT")
        if label is None:
            return
        label.setTextFormat(text_format(TYPE_SCALE["panel"], PALETTE["text"]))
        _panel(label, layout_mm)
        label.setMarginX(2.0)
        label.setMarginY(1.5)

    def footer():
        label = item("FOOTER")
        label.setText(footer_text(label.text(), levels))
        label.setTextFormat(text_format(TYPE_SCALE["footer"], PALETTE["muted"], italic=True))

    def legend():
        leg = item("LEGEND")
        leg.setAutoUpdateModel(False)                     # an explicit model, not "every layer in the project"
        root = leg.model().rootGroup()
        root.removeAllChildren()
        for layer_id in ids:
            root.addLayer(by_id[layer_id])
        leg.setLegendFilterByMapEnabled(True)             # only what the map extent shows
        leg.setTitle("Legend")
        _panel(leg, layout_mm)

    def legend_fonts():
        leg = item("LEGEND")
        style_cls = _legend_style_class()
        for style_name, size, bold in (("Title", TYPE_SCALE["legend_title"], True), ("Group", TYPE_SCALE["legend_item"] + 1, True),
                                       ("Subgroup", TYPE_SCALE["legend_item"] + 0.5, True),
                                       ("SymbolLabel", TYPE_SCALE["legend_item"], False)):
            member = getattr(getattr(style_cls, "Style", style_cls), style_name, None)
            if member is not None:
                leg.rstyle(member).setTextFormat(text_format(size, PALETTE["text"], bold=bold))

    def scalebar():
        bar = item("SCALEBAR")
        bar.setTextFormat(text_format(TYPE_SCALE["info"], PALETTE["text"]))

    for name, fn in (("title", title), ("map frame", map_frame), ("info row", info), ("body panel", body),
                     ("footer", footer), ("legend", legend), ("legend fonts", legend_fonts), ("scale bar", scalebar)):
        step(name, fn)
    return {"warnings": warnings, "legend_layers": [by_id[i].name() for i in ids],
            "classification": classification_prefix(levels).strip(" -")}


def _legend_style_class():
    from qgis.core import QgsLegendStyle
    return QgsLegendStyle
