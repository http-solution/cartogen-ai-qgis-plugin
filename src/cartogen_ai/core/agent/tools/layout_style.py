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
Positions and sizes are NOT touched, with one exception: the FOOTER grows (into the bottom margin first, then upward into free
space) when the sources and disclaimer lines need more room (PLAN-011 phase C). The rest of the geometry carries a documented
history of overlap bugs (BUG-2026-09-11-1) that was live-verified, so this module otherwise only changes how items look. Every item is styled independently and best-effort: a failure
is reported as a warning and the layout is still produced.
"""
import contextlib
import datetime
import os

from .routing_style import ACCESS_STYLES

try:
    from qgis.core import (
        Qgis, QgsLayoutItemPicture, QgsLayoutMeasurement, QgsLayoutPoint, QgsLayoutSize, QgsProject, QgsTextFormat, QgsUnitTypes,
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


def _luminance(hex_value):
    r, g, b = (int(hex_value[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_ratio(hex_a, hex_b):
    """WCAG contrast ratio (1 to 21) of two #rrggbb colours. Pure."""
    la, lb = sorted((_luminance(hex_a), _luminance(hex_b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


MIN_MASTHEAD_CONTRAST = 3.0     # WCAG AA for large text; the title is large bold text


def resolve_masthead_colours(bg_hex, fg_hex=None):
    """(background, text, warning or None). The text colour a profile asks for is used only if it is readable on the background; otherwise
    the automatic dark/light choice stands and the warning says why. Pure."""
    bg, auto_fg = resolve_masthead(bg_hex)
    wanted = str(fg_hex or "").strip().lower()
    if not wanted:
        return bg, auto_fg, None
    if contrast_ratio(bg, wanted) >= MIN_MASTHEAD_CONTRAST:
        return bg, wanted, None
    return bg, auto_fg, f"masthead_text_colour {wanted} is hard to read on {bg} (contrast {contrast_ratio(bg, wanted):.1f}:1); used {auto_fg} instead"


LOGO_PAD_MM = 1.0
LOGO_MAX_ASPECT = 2.0       # logo box is at most this many times wider than tall
LOGO_MAX_SHARE = 0.25       # and at most this share of the masthead width


def masthead_split(x, y, w, h, position="left"):
    """((lx, ly, lw, lh), (tx, ty, tw, th)): the logo box and the narrowed title box inside the masthead rectangle. They never overlap. Pure."""
    lh = max(1.0, h - 2 * LOGO_PAD_MM)
    lw = min(lh * LOGO_MAX_ASPECT, w * LOGO_MAX_SHARE)
    ly = y + (h - lh) / 2
    if str(position).lower() == "right":
        return (x + w - lw - LOGO_PAD_MM, ly, lw, lh), (x, y, w - lw - 2 * LOGO_PAD_MM, h)
    return (x + LOGO_PAD_MM, ly, lw, lh), (x + lw + 2 * LOGO_PAD_MM, y, w - lw - 2 * LOGO_PAD_MM, h)


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


# PLAN-011 phase C (owner decision 2026-10-24): a neutral default; the organisation's own wording (for example the standard UN boundary text)
# is supplied through Settings, not written here.
DEFAULT_DISCLAIMER = ("Boundaries, names and designations shown do not imply official endorsement or acceptance. "
                      "Check data sensitivity before sharing.")
SOURCES_CHAR_BUDGET = 150
NOT_RECORDED = "source not recorded"


def disclaimer_text(enabled=True, custom=""):
    """The disclaimer line for the footer: '' when switched off, the organisation's wording when set, else the neutral default. Pure."""
    if not enabled:
        return ""
    return (str(custom or "").strip()) or DEFAULT_DISCLAIMER


def source_entry(name, publisher="", date="", identifier=""):
    """One layer's source text. Only what the layer's own metadata says is used; with none of it the entry says 'source not recorded'. Pure."""
    detail = "; ".join(str(x).strip() for x in (publisher, date) if x and str(x).strip())
    if not detail and identifier and str(identifier).strip():
        detail = f"file {identifier}"
    return f"{name} ({detail or NOT_RECORDED})"


def sources_line(entries, budget=SOURCES_CHAR_BUDGET):
    """'Sources: a (...); b (...)' within `budget` characters; layers that do not fit are counted ('+2 more'), never dropped silently. Pure."""
    entries = [e for e in entries if e]
    if not entries:
        return ""
    prefix = "Sources: "
    full = prefix + "; ".join(entries)
    if len(full) <= budget:
        return full
    limit = budget - len(" +99 more")
    kept, used = [], len(prefix)
    for entry in entries:
        add = len(entry) + (2 if kept else 0)
        if kept and used + add > limit:
            break
        kept.append(entry if used + add <= limit else entry[: max(10, limit - used - 1)] + "~")
        used += add
    left = len(entries) - len(kept)
    return prefix + "; ".join(kept) + (f" +{left} more" if left else "")


def footer_block(base, levels, sources, disclaimer, credit_text="", extra_lines=()):
    """The footer's full text: classification and AI note, then the sources line, the credits line (PLAN-014), the profile's own lines and
    sign-off (phase 3b), then the disclaimer; empty parts are left out. Pure."""
    return "\n".join(part for part in (footer_text(base, levels), sources, credit_text, *extra_lines, disclaimer) if part)


def profile_footer_lines(branding):
    """The footer lines a profile adds: its footer_lines, then the sign-off line. Pure."""
    from .map_profiles import sign_off_line
    lines = list((branding or {}).get("footer_lines") or [])
    sign_off = sign_off_line((branding or {}).get("sign_off"))
    return lines + ([sign_off] if sign_off else [])


FOOTER_LINE_FACTOR = 1.25      # line pitch / font size for the small footer text; a body panel uses the more generous 1.35
FOOTER_PAD_MM = 0.6            # box padding added to the wrapped lines; 1.0 left a four-line landscape footer (note, sources, credits, disclaimer) 0.4 mm short
FOOTER_CLEARANCE_MM = 0.5      # gap kept between the grown footer and the item above it


def footer_height_mm(text, width_mm, font_pt):
    """Height the footer text needs, in mm: wrapped lines times the line pitch, plus FOOTER_PAD_MM. Pure.

    CI on QGIS 4.2.2 (PLAN-014 phase 2b run): the shared body-panel estimate, which is generous on purpose, said a three-line footer needed 12 mm
    where about 10 fit, so EVERY landscape layout returned 'footer text may not fit'. The footer is small fixed text, so it gets its own,
    tighter estimate (and the gap above it is 0.5 mm, not 1.5)."""
    import math
    usable = max(1.0, float(width_mm) - 2 * 2.0)
    per_line = max(1, int(usable / (font_pt * 0.3528 * 0.5)))
    lines = sum(max(1, math.ceil(len(line) / per_line)) for line in str(text or "").split("\n"))
    return lines * font_pt * 0.3528 * FOOTER_LINE_FACTOR + FOOTER_PAD_MM


def plan_footer_growth(needed_mm, height_mm, y_mm, page_height_mm, clearance_above_mm, bottom_gap_mm=0.5):
    """(new_y, new_height, fits) for a footer that needs `needed_mm`: grow into the page margin below first, then upward into the free space above. Pure."""
    if needed_mm <= height_mm:
        return y_mm, height_mm, True
    extra = needed_mm - height_mm
    down = max(0.0, page_height_mm - bottom_gap_mm - (y_mm + height_mm))
    take_down = min(extra, down)
    extra -= take_down
    take_up = min(extra, max(0.0, clearance_above_mm))
    extra -= take_up
    return y_mm - take_up, height_mm + take_down + take_up, extra <= 1e-6


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


_ACTIVE_FONT = {"family": None}   # set by apply_layout_style for the duration of one styling run (a profile's font_family)


def text_format(size_pt, color_hex, bold=False, italic=False):
    fmt = QgsTextFormat()
    font = QFont(_ACTIVE_FONT["family"]) if _ACTIVE_FONT["family"] else QFont()
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


def layer_credit_info(entry):
    """The dict credit_entries() reads, from a visible_layer_entries() item. Never raises."""
    layer = entry["layer"]
    rights = []
    with contextlib.suppress(Exception):
        rights = [str(r) for r in layer.metadata().rights()]
    source = ""
    with contextlib.suppress(Exception):
        source = layer.source()
    return {"name": entry["name"], "provider": entry["provider"], "source": source, "rights": rights, "visible": entry["visible"]}


def layer_source_entry(layer):
    """source_entry() for a real layer, from its own metadata (organisation, publication date) and, failing that, its file name. Never raises."""
    import os
    publisher = date = identifier = ""
    with contextlib.suppress(Exception):
        md = layer.metadata()
        contacts = md.contacts()
        publisher = contacts[0].organization if contacts else ""
        for kind in ("Published", "Revised", "Created"):
            moment = md.dateTime(getattr(Qgis.MetadataDateType, kind))
            if moment.isValid():
                date = moment.toString("yyyy-MM-dd")
                break
    with contextlib.suppress(Exception):
        if str(layer.providerType()).lower() not in ("memory", "wms", "xyz", "arcgismapserver"):
            identifier = os.path.basename(str(layer.source()).split("|")[0])
    return source_entry(layer.name(), publisher, date, identifier)


def _footer_settings():
    """(disclaimer_enabled, custom_text) from the QGIS settings; the neutral default when unreadable. Never raises."""
    try:
        from qgis.core import QgsSettings
        from ....infrastructure.settings_keys import SETTINGS_LAYOUT_DISCLAIMER_ENABLED, SETTINGS_LAYOUT_DISCLAIMER_TEXT
        settings = QgsSettings()
        enabled = settings.value(SETTINGS_LAYOUT_DISCLAIMER_ENABLED, True)
        enabled = enabled not in (False, "false", "False", 0, "0")
        return enabled, str(settings.value(SETTINGS_LAYOUT_DISCLAIMER_TEXT, "") or "")
    except Exception:
        return True, ""


def installed_font(family):
    """(family or None, warning or None): the requested font if this machine has it, else None and a warning (never a silent change). """
    if not family:
        return None, None
    try:
        from qgis.PyQt.QtGui import QFontDatabase
        available = {f.lower() for f in QFontDatabase.families()}
    except Exception:
        return None, f"font '{family}' could not be checked; the default font is used"
    if family.lower() in available:
        return family, None
    return None, f"font '{family}' is not installed on this computer; the default font is used"


def apply_layout_style(layout, layout_mm, project=None, today=None, template="standard", sources=None, branding=None):
    """Styles the items create_print_layout made. `branding` is a map profile (logo, masthead colours, font). Returns
    {'warnings': [...], 'legend_layers': [names], 'classification': str}."""
    branding = branding or {}
    family, font_warning = installed_font(branding.get("font_family"))
    _ACTIVE_FONT["family"] = family
    try:
        report = _apply_layout_style(layout, layout_mm, project, today, template, sources, branding)
    finally:
        _ACTIVE_FONT["family"] = None
    if font_warning:
        report["warnings"].append(font_warning)
    return report


def _apply_layout_style(layout, layout_mm, project, today, template, sources, branding):
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
        from ..protection import effective_sensitivity
        pool = list(project.mapLayers().values())
        levels.extend(effective_sensitivity(e["layer"], pool).get("level") for e in entries if e["visible"])    # PLAN-016: a derived layer carries its source's level
    except Exception as exc:
        warnings.append(f"sensitivity lookup failed: {exc}")

    chosen = {"ids": ids}      # the layers the legend really lists (legend() may drop those that lie off the map)
    drawn = [by_id[i] for i in ids if i in by_id]
    source_entries = [str(x) for x in sources] if sources else [layer_source_entry(layer) for layer in drawn]
    footer_warnings = []
    credit_text = ""
    with contextlib.suppress(Exception):
        from .layout_credits import credit_entries, credits_line
        cod = [branding["cod_credit"]] if branding.get("cod_boundaries") and branding.get("cod_credit") else []   # first, so the budget never cuts it
        credit_text = credits_line(cod + credit_entries([layer_credit_info(e) for e in entries]))

    def step(name, fn):
        try:
            fn()
        except Exception as exc:
            warnings.append(f"{name}: {type(exc).__name__}: {exc}")

    for name, fn in (
            ("title", lambda: _style_title(layout, branding, warnings)),
            ("logo", lambda: _add_logo(layout, layout_mm, branding, warnings)),
            ("map frame", lambda: _style_map_frame(layout, layout_mm)),
            ("info row", lambda: _style_info(layout, today)),
            ("body panel", lambda: _style_body(layout, layout_mm)),
            ("footer", lambda: footer_warnings.extend(_style_footer(layout, layout_mm, levels, source_entries, credit_text, profile_footer_lines(branding)))),
            ("legend", lambda: _style_legend(layout, layout_mm, ids, by_id, template, chosen)),
            ("legend fonts", lambda: _style_legend_fonts(layout)),
            ("scale bar", lambda: _style_scalebar(layout))):
        step(name, fn)
    warnings.extend(footer_warnings)
    return {"warnings": warnings, "legend_layers": [by_id[i].name() for i in chosen["ids"]],
            "classification": classification_prefix(levels).strip(" -")}


def _style_title(layout, branding=None, warnings=None):
    label = layout.itemById("TITLE")
    branding = branding or {}
    bg_hex, fg_hex, colour_warning = resolve_masthead_colours(branding.get("masthead_colour") or _configured_masthead(),
                                                              branding.get("masthead_text_colour"))
    if colour_warning and warnings is not None:
        warnings.append(colour_warning)
    label.setTextFormat(text_format(TYPE_SCALE["title"], fg_hex, bold=True))
    label.setBackgroundEnabled(True)
    label.setBackgroundColor(QColor(bg_hex))
    label.setMarginX(3.0)
    label.setMarginY(1.0)
    label.setVAlign(Qt.AlignmentFlag.AlignVCenter)


def _add_logo(layout, layout_mm, branding, warnings):
    """Adds the organisation's logo (a local PNG/JPG named by the profile) to the masthead and narrows the title so they do not overlap.
    A missing or unreadable file leaves the layout as it was and says so."""
    path = branding.get("logo_path")
    if not path:
        return
    title = layout.itemById("TITLE")
    if title is None:
        return
    from qgis.PyQt.QtGui import QImage
    if not os.path.isfile(path) or QImage(path).isNull():
        warnings.append(f"logo: '{path}' is missing or is not a readable PNG/JPG image; the layout has no logo")
        return
    logo_rect, title_rect = masthead_split(title.x(), title.y(), title.rect().width(), title.rect().height(), branding.get("logo_position", "left"))
    pic = QgsLayoutItemPicture(layout)
    pic.setId("LOGO")
    pic.setPicturePath(path)
    layout.addLayoutItem(pic)
    pic.attemptMove(QgsLayoutPoint(logo_rect[0], logo_rect[1], layout_mm))
    pic.attemptResize(QgsLayoutSize(logo_rect[2], logo_rect[3], layout_mm))
    title.attemptMove(QgsLayoutPoint(title_rect[0], title_rect[1], layout_mm))
    title.attemptResize(QgsLayoutSize(title_rect[2], title_rect[3], layout_mm))


def _style_map_frame(layout, layout_mm):
    _frame(layout.itemById("MAP_MAIN"), FRAME_MM["map"], layout_mm)
    inset = layout.itemById("INSET_MAP")
    if inset is not None:
        _frame(inset, FRAME_MM["panel"], layout_mm)


def _style_info(layout, today):
    label = layout.itemById("MAP_INFO")
    if label is None:
        return
    label.setText(info_text(label.text(), today))
    label.setTextFormat(text_format(TYPE_SCALE["info"], PALETTE["muted"]))


def _style_body(layout, layout_mm):
    label = layout.itemById("BODY_TEXT")
    if label is None:
        return
    label.setTextFormat(text_format(TYPE_SCALE["panel"], PALETTE["text"]))
    _panel(label, layout_mm)
    label.setMarginX(2.0)
    label.setMarginY(1.5)
    with contextlib.suppress(Exception):  # size the panel to its text instead of leaving a page-tall empty box (#129)
        size = label.rect()
        needed = body_text_height_mm(label.text(), size.width(), TYPE_SCALE["panel"])
        if needed < size.height():
            label.attemptResize(QgsLayoutSize(size.width(), needed, layout_mm))


def _clearance_above(layout, label):
    """Free space (mm) between the footer and the nearest layout item above it that overlaps it horizontally. Never raises."""
    top = label.y()
    left, right = label.x(), label.x() + label.rect().width()
    bottoms = []
    for item in layout.items():
        if item is label or not (hasattr(item, "id") and item.id()):
            continue
        item_right = item.x() + item.rect().width()
        bottom = item.y() + item.rect().height()
        if item.x() < right and item_right > left and bottom <= top + 1.0:
            bottoms.append(bottom)
    return top - max(bottoms) - FOOTER_CLEARANCE_MM if bottoms else top - FOOTER_CLEARANCE_MM


MAP_RECLAIM_SHARE = 0.25   # the main map never gives up more than this share of its height to a longer footer


def _reclaim_from_map(layout, layout_mm, label, deficit_mm):
    """Shortens MAP_MAIN from the bottom by `deficit_mm` (at most MAP_RECLAIM_SHARE of it) and lifts every item that sits between the map and the
    footer (the info row, scale bar, north arrow) by the same amount, so the footer can grow upward. In landscape the footer spans the page under
    the map, so the scale bar and info row, not the map, are what limit it (PLAN-014 3b CI run 2). False, and nothing changed, when there is no
    main map or an inset map would then stick out below it."""
    if deficit_mm <= 0:
        return False
    main = layout.itemById("MAP_MAIN")
    if main is None:
        return False
    amount = min(deficit_mm + 0.2, main.rect().height() * MAP_RECLAIM_SHARE)
    map_bottom = main.y() + main.rect().height()
    inset = layout.itemById("INSET_MAP")
    if inset is not None and inset.y() + inset.rect().height() > map_bottom - amount:
        return False
    between = [item for item in layout.items()
               if item is not main and item is not label and hasattr(item, "id") and item.id() and map_bottom - 0.5 <= item.y() < label.y()]
    main.attemptResize(QgsLayoutSize(main.rect().width(), main.rect().height() - amount, layout_mm))
    for item in between:
        item.attemptMove(QgsLayoutPoint(item.x(), item.y() - amount, layout_mm))
    return True


def _style_footer(layout, layout_mm, levels, source_entries=(), credit_text="", extra_lines=()):
    """Sets the footer text (classification, AI note, sources, disclaimer) and grows the box to fit. Returns warnings."""
    label = layout.itemById("FOOTER")
    base = label.text()
    enabled, custom = _footer_settings()
    disclaimer = disclaimer_text(enabled, custom)
    label.setTextFormat(text_format(TYPE_SCALE["footer"], PALETTE["muted"], italic=True))
    page_height = layout.pageCollection().page(0).pageSize().height()
    warnings = []
    for budget in (SOURCES_CHAR_BUDGET, 60):
        text = footer_block(base, levels, sources_line(source_entries, budget), disclaimer, credit_text, extra_lines)
        label.setText(text)
        needed = footer_height_mm(text, label.rect().width(), TYPE_SCALE["footer"])
        new_y, new_h, fits = plan_footer_growth(needed, label.rect().height(), label.y(), page_height, _clearance_above(layout, label))
        if fits:
            break
    else:
        # PLAN-014 3b CI: a profile's footer lines plus sign-off make 6 to 8 lines, more than the strip under the map holds (A3: needs 31 mm, box 18).
        # The profile asked for those lines, so the map gives up the missing height from its bottom edge before anything is warned about.
        if extra_lines and _reclaim_from_map(layout, layout_mm, label, needed - new_h):
            new_y, new_h, fits = plan_footer_growth(needed, label.rect().height(), label.y(), page_height, _clearance_above(layout, label))
        if not fits:
            warnings.append("footer: the sources and disclaimer text may not fit in the space available; shorten the disclaimer in Settings")
    if new_h != label.rect().height():
        label.attemptMove(QgsLayoutPoint(label.x(), new_y, layout_mm))
        label.attemptResize(QgsLayoutSize(label.rect().width(), new_h, layout_mm))
    return warnings


def _style_legend(layout, layout_mm, ids, by_id, template, chosen):
    leg = layout.itemById("LEGEND")
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
    map_item = layout.itemById("MAP_MAIN")
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


def _style_legend_fonts(layout):
    leg = layout.itemById("LEGEND")
    style_cls = _legend_style_class()
    for style_name, size, bold in (("Title", TYPE_SCALE["legend_title"], True), ("Group", TYPE_SCALE["legend_item"] + 1, True),
                                   ("Subgroup", TYPE_SCALE["legend_item"] + 0.5, True),
                                   ("SymbolLabel", TYPE_SCALE["legend_item"], False)):
        member = getattr(getattr(style_cls, "Style", style_cls), style_name, None)
        if member is not None:
            leg.rstyle(member).setTextFormat(text_format(size, PALETTE["text"], bold=bold))


def _style_scalebar(layout):
    bar = layout.itemById("SCALEBAR")
    bar.setTextFormat(text_format(TYPE_SCALE["info"], PALETTE["text"]))


def _legend_style_class():
    from qgis.core import QgsLegendStyle
    return QgsLegendStyle
