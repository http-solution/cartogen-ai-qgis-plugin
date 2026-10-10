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

from .routing_style import ACCESS_STYLES

try:
    from qgis.core import (
        Qgis, QgsLayoutMeasurement, QgsLayoutSize, QgsProject, QgsTextFormat, QgsUnitTypes,
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


# --- access-map template: how the layers a service-area / access analysis leaves behind are ordered and explained.
ACCESS_PARTS = (            # (name fragment, rank, plain-language reading-guide line)
    ("_reachable_area", 0, "Shaded area: the reachable area within the chosen travel cost."),
    # calculate_service_area's own reach polygon (`<origin>_service_area_<n>`); rc11 smoke S8 (#129): with only that polygon
    # visible the guide never explained the shaded area. Same sentence, so it is listed once when both are present.
    ("_service_area_", 0, "Shaded area: the reachable area within the chosen travel cost."),
    ("_reachable_by_", 1, "Admin areas: the area reached by the facilities."),
    # Built from routing_style.ACCESS_STYLES so the guide cannot drift from the map again: it said "green" after the
    # styling moved to blue (audit F29, #165).
    ("_access_", 2, "Points: facilities " + ACCESS_STYLES["within"]["label"] + " (" + ACCESS_STYLES["within"]["colour_name"]
     + ") and " + ACCESS_STYLES["beyond"]["label"] + " (" + ACCESS_STYLES["beyond"]["colour_name"] + ")."),
    ("_roads_by_cost_", 3, "Road colour: travel cost from the origin, near (dark) to far (warm)."),
)


SITREP_MAX_FIGURES = 8
SITREP_HANDLING = ("Figures are estimates from the sources listed, not verified counts. Results are shown at area level; do not publish "
                   "exact locations of people or sensitive sites from this map.")


def normalise_key_figures(key_figures):
    """[(label, value, source-or-'')] from a list of {label, value, source?} dicts, in order, dropping anything without both a label and a
    value and keeping at most SITREP_MAX_FIGURES. Pure. The values are whatever the caller supplies: this layer never computes or
    invents a figure, so a figure on a sitrep is only as good as the tool result it was copied from."""
    out = []
    for item in key_figures or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        value = item.get("value")
        value = "" if value is None else str(value).strip()
        if label and value:
            out.append((label, value, str(item.get("source") or "").strip()))
        if len(out) >= SITREP_MAX_FIGURES:
            break
    return out


def _shorten(text, limit):
    """text cut to at most `limit` characters on a word boundary with an ellipsis; '' when limit is too small to be useful. Pure."""
    if len(text) <= limit:
        return text
    if limit < 12:
        return ""
    return text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;: ") + "\u2026"


def sitrep_body(summary="", key_figures=None, sources=None, reading_guide="", today=None, max_chars=None):
    """The text panel of the `sitrep` template: SITUATION, KEY FIGURES, HOW TO READ THIS MAP, SOURCES, HANDLING, in that order, leaving out
    any section that has no content. Pure. HANDLING and the preparation date are always present; nothing else is added on the caller's
    behalf.

    With `max_chars` (the label box's budget) the text is made to fit by giving up, in this order: the reading guide, the tail of the
    situation summary, then the last key figures. The sources and the handling note are never cut, because plain truncation would
    remove exactly them (they come last)."""
    summary = str(summary or "").strip()
    figures = list(normalise_key_figures(key_figures))
    guide = str(reading_guide or "").strip()
    src = [str(x).strip() for x in (sources or []) if str(x).strip()]
    handling = "HANDLING\n" + SITREP_HANDLING + " " + prepared_stamp(today) + "."
    sources_part = "SOURCES\n" + "; ".join(src) if src else ""

    def build(summary_text, figs, guide_text):
        parts = []
        if summary_text:
            parts.append("SITUATION\n" + summary_text)
        if figs:
            lines = [f"- {label}: {value}" + (f" ({source})" if source else "") for label, value, source in figs]
            parts.append("KEY FIGURES\n" + "\n".join(lines))
        if guide_text:
            parts.append("HOW TO READ THIS MAP\n" + guide_text)
        if sources_part:
            parts.append(sources_part)
        parts.append(handling)
        return "\n\n".join(parts)

    text = build(summary, figures, guide)
    if max_chars is None or len(text) <= max_chars:
        return text
    text = build(summary, figures, "")
    if len(text) <= max_chars:
        return text
    fixed = len(build("", figures, "")) + len("SITUATION\n") + 2
    room = max_chars - fixed
    if summary and room > 0:
        shortened = _shorten(summary, room)
        text = build(shortened, figures, "")
        if len(text) <= max_chars:
            return text
    while figures:
        figures.pop()
        text = build("", figures, "")
        if len(text) <= max_chars:
            return build(_shorten(summary, max_chars - len(text) - 12), figures, "") if summary and max_chars - len(text) > 24 else text
    return build("", [], "")


def sitrep_has_content(summary="", key_figures=None, sources=None):
    """True when the caller supplied anything beyond the standing handling note. Pure."""
    return bool(str(summary or "").strip() or normalise_key_figures(key_figures) or any(str(x).strip() for x in (sources or [])))


def resolve_masthead(hex_value):
    """(background, text) colours for the masthead. Pure. An invalid/empty value gives the default palette; a light
    background gets dark text (relative luminance, WCAG weights) so the title stays readable."""
    import re
    text = str(hex_value or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return PALETTE["masthead_bg"], PALETTE["masthead_fg"]
    r, g, b = (int(text[i:i + 2], 16) for i in (1, 3, 5))
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
    return text.lower(), ("#1f2d3a" if luminance > 0.6 else "#ffffff")


def access_rank(name):
    """Legend/zoom rank of an access-analysis layer name (lower = more important); 9 for any other layer. Pure."""
    text = str(name or "")
    for fragment, rank, _ in ACCESS_PARTS:
        if fragment in text:
            return rank
    return 9


def arrange_rank(name):
    """Draw-order tie-break inside one geometry kind: an access-analysis layer by its access rank, a road-snapped route
    ('<stops>_road_route') above the plain road network it was built from, everything else last. Pure.

    rc11 smoke test C1: the route line was drawn UNDER 'OSM Roads (Yemen)' because both are lines with no access rank."""
    rank = access_rank(name)
    if rank == 9 and str(name or "").endswith("_road_route"):
        return 4
    return rank


def order_for_access_map(ids, names_by_id):
    """`ids` re-ordered so reach polygons come first, then access points, then roads, then everything else; stable. Pure."""
    return sorted(ids, key=lambda i: access_rank(names_by_id.get(i)))


def access_reading_guide(names):
    """'How to read this map' lines for the access layers actually present, or '' when there are none. Pure."""
    lines = []
    for fragment, _rank, text in ACCESS_PARTS:
        if any(fragment in str(n or "") for n in names) and text not in lines:
            lines.append(text)
    return "\n".join(lines)


def body_text_height_mm(text, width_mm, font_pt, margin_mm=1.5, minimum_mm=8.0):
    """Height a wrapped text panel needs, in mm. Pure estimate (average glyph ~0.5 em, line height 1.35 em).

    rc11 smoke S7 (#129): the body box was as tall as the page for one or two lines of text. Slightly generous on purpose:
    a clipped last line is worse than a little spare room."""
    import math
    usable = max(1.0, float(width_mm) - 2 * 2.0)               # the panel's side margins
    chars_per_line = max(1, int(usable / (font_pt * 0.3528 * 0.5)))
    lines = 0
    for line in str(text or "").split("\n"):
        lines += max(1, math.ceil(len(line) / chars_per_line))
    return max(float(minimum_mm), lines * font_pt * 0.3528 * 1.35 + 2 * margin_mm + 1.0)


def access_zoom_layer_name(names):
    """The layer the map should fit when none was named: the best-ranked access layer, else None. Pure."""
    ranked = [(access_rank(n), n) for n in names if access_rank(n) < 9]
    return min(ranked, key=lambda t: t[0])[1] if ranked else None


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

def _configured_masthead():
    try:
        from qgis.core import QgsSettings
        from ....infrastructure.settings_keys import SETTINGS_LAYOUT_MASTHEAD_COLOR
        return QgsSettings().value(SETTINGS_LAYOUT_MASTHEAD_COLOR, "")
    except Exception:
        return ""


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


def legend_layers_on_map(layers, map_item):
    """The (id, layer) pairs from `layers` whose extent intersects what the map item shows. Needs QGIS.

    Legend "filter by map content" drops vector layers with no visible features but keeps every raster, so a DEM or image that lies
    outside a zoomed-in map was still listed (rc18 hand test R7/N8, 2026-10-06). Here a layer is kept when its extent, transformed into the
    map's CRS, intersects the map's extent. Anything that cannot be tested (no extent, no CRS, an error) is kept: a layer is never dropped on
    a guess."""
    from qgis.core import QgsCoordinateTransform
    extent = map_item.extent()
    map_crs = map_item.crs()
    context = QgsProject.instance().transformContext()
    kept = []
    for layer_id, layer in layers:
        try:
            rect = layer.extent()
            if rect is None or rect.isNull() or rect.isEmpty() or not layer.crs().isValid():
                kept.append((layer_id, layer))
                continue
            if layer.crs() != map_crs:
                rect = QgsCoordinateTransform(layer.crs(), map_crs, context).transformBoundingBox(rect)
            if rect.intersects(extent):
                kept.append((layer_id, layer))
        except Exception:
            kept.append((layer_id, layer))
    return kept


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


def apply_layout_style(layout, layout_mm, project=None, today=None, template="standard"):
    """Styles the items create_print_layout made. Returns {'warnings': [...], 'legend_layers': [names], 'classification': str}."""
    warnings = []
    if not QGIS_AVAILABLE:
        return {"warnings": ["QGIS not available"], "legend_layers": [], "classification": ""}
    project = project or QgsProject.instance()
    entries = visible_layer_entries(project)
    ids = legend_layer_ids(entries)
    if template == "access_map":
        ids = order_for_access_map(ids, {e["id"]: e["name"] for e in entries})
    by_id = {e["id"]: e["layer"] for e in entries}

    levels = []
    try:
        from ...models import sensitivity
        for e in entries:
            if e["visible"]:
                levels.append(sensitivity.get_layer_sensitivity(e["layer"]).get("level"))
    except Exception as exc:
        warnings.append(f"sensitivity lookup failed: {exc}")

    chosen = {"ids": ids}      # the layers the legend really lists (legend() may drop those that lie off the map)

    def step(name, fn):
        try:
            fn()
        except Exception as exc:
            warnings.append(f"{name}: {type(exc).__name__}: {exc}")

    def item(item_id):
        return layout.itemById(item_id)

    def title():
        label = item("TITLE")
        bg_hex, fg_hex = resolve_masthead(_configured_masthead())
        label.setTextFormat(text_format(TYPE_SCALE["title"], fg_hex, bold=True))
        label.setBackgroundEnabled(True)
        label.setBackgroundColor(QColor(bg_hex))
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
        try:   # size the panel to its text instead of leaving a page-tall empty box (#129)
            size = label.rect()
            needed = body_text_height_mm(label.text(), size.width(), TYPE_SCALE["panel"])
            if needed < size.height():
                label.attemptResize(QgsLayoutSize(size.width(), needed, layout_mm))
        except Exception:  # nosec B110 (best-effort: failure is non-fatal)
            pass

    def footer():
        label = item("FOOTER")
        label.setText(footer_text(label.text(), levels))
        label.setTextFormat(text_format(TYPE_SCALE["footer"], PALETTE["muted"], italic=True))

    def legend():
        leg = item("LEGEND")
        # an explicit model, not "every layer in the project". setAutoUpdateModel is deprecated since QGIS 4.0 (the rc11 log
        # showed a DeprecationWarning per layout); setSyncMode(Manual) is its replacement, with the old call as the fallback.
        try:
            from qgis.core import Qgis
            leg.setSyncMode(Qgis.LegendSyncMode.Manual)
        except Exception:
            leg.setAutoUpdateModel(False)
        root = leg.model().rootGroup()
        root.removeAllChildren()
        legend_ids = ids
        map_item = item("MAP_MAIN")
        if template != "access_map" and map_item is not None:
            on_map = [lid for lid, _layer in legend_layers_on_map([(i, by_id[i]) for i in ids], map_item)]
            if on_map:                      # never an empty legend because every extent test said "elsewhere"
                legend_ids = on_map
        chosen["ids"] = legend_ids
        for layer_id in legend_ids:
            root.addLayer(by_id[layer_id])
        # Only what the map extent shows -- except for the access-map template: its layers are already limited to the VISIBLE
        # ones, and the extent filter is the one step that can silently drop a visible reach polygon (rc11 smoke S8, #129: the
        # shaded reach area was on the map but not in the legend; the exact cause was not reproduced from code).
        leg.setLegendFilterByMapEnabled(template != "access_map")
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
    return {"warnings": warnings, "legend_layers": [by_id[i].name() for i in chosen["ids"]],
            "classification": classification_prefix(levels).strip(" -")}


def _legend_style_class():
    from qgis.core import QgsLegendStyle
    return QgsLegendStyle
