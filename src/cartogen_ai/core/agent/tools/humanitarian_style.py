# -*- coding: utf-8 -*-
"""
Map looks for the humanitarian tools' outputs (styling review, docs/HUMANITARIAN_TOOLS_CATALOGUE.md section "Map styling review").

The review found tools whose result arrived in QGIS's raw defaults -- a random single colour, or an unstretched grey raster --
although what the tool computed has an obvious visual meaning: the mapping-task grid's priority, the road segments a barrier
affects, the survey sample points per stratum, a GDACS alert level, a before/after difference. This module gives those layers a
look that carries that meaning. The palettes and the ordering rules are pure and unit tested offline; the QGIS half is covered by
tests/test_humanitarian_style_live.py, written without a local QGIS (its first execution is CI). Everything is best-effort
cosmetics: a styling failure returns False and never turns a successful analysis into an error, and a user's own layers are not
restyled (only layers these tools create).
"""
try:
    from qgis.core import (QgsCategorizedSymbolRenderer, QgsColorRampShader, QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol,
                           QgsRasterShader, QgsRendererCategory, QgsSingleBandPseudoColorRenderer, QgsSingleSymbolRenderer)
    from qgis.PyQt.QtGui import QColor
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# Priority runs dark (map first) to pale; an unranked task is a neutral grey outline.
PRIORITY_COLORS = {"High": "#b2182b", "Medium": "#ef8a62", "Low": "#fddbc7"}
UNRANKED_COLOR = "#d9d9d9"
# GDACS's own Green / Orange / Red alert levels.
ALERT_COLORS = {"Red": "#d7191c", "Orange": "#fdae61", "Green": "#1a9641"}
BARRIER_COLORS = {"block": "#d7191c", "penalise": "#f58231"}
# Qualitative palette for strata / event categories (colour-blind-aware ordering, cycled).
QUALITATIVE = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#a6761d", "#1f78b4", "#666666", "#b15928"]
FIRE_COLOR = "#e8590c"
LABEL_TASK_LIMIT = 150            # above this the task-id labels are a cloud


# ---------------------------------------------------------------- pure --

def qualitative_colors(values):
    """{value: colour} for the distinct values, in sorted order, cycling the palette. Pure and deterministic, so a re-run gives the
    same colours."""
    distinct = sorted({str(v) for v in values if v is not None and str(v) != ""})
    return {v: QUALITATIVE[i % len(QUALITATIVE)] for i, v in enumerate(distinct)}


def priority_categories(values):
    """[(value, colour, label)] for the priority values present, High -> Low, then 'unranked'. Pure."""
    present = {v for v in values if v in PRIORITY_COLORS}
    out = [(k, PRIORITY_COLORS[k], k) for k in ("High", "Medium", "Low") if k in present]
    if any(v is None or str(v) == "" for v in values):
        out.append(("", UNRANKED_COLOR, "unranked"))
    return out


def alert_categories(values):
    """[(value, colour, label)] for GDACS alert levels present, Red -> Green; unknown levels fall to grey. Pure."""
    present = {str(v) for v in values if v is not None and str(v) != ""}
    out = [(k, ALERT_COLORS[k], k) for k in ("Red", "Orange", "Green") if k in present]
    out += [(v, "#808080", v) for v in sorted(present - set(ALERT_COLORS))]
    return out


def diverging_stops(vmin, vmax):
    """[(value, (r,g,b,a), label)] for a before/after difference: symmetric about zero so equal gains and losses get equal
    colour strength, blue = decrease, red = increase, zero fully transparent. Pure. A flat or non-numeric range falls back to
    +/-1."""
    try:
        m = max(abs(float(vmin)), abs(float(vmax)))
    except (TypeError, ValueError):
        m = 0.0
    if not m > 0:
        m = 1.0
    colours = [(-1.0, (33, 102, 172, 255)), (-0.5, (146, 197, 222, 235)), (-0.02, (247, 247, 247, 120)),
               (0.0, (247, 247, 247, 0)), (0.02, (247, 247, 247, 120)), (0.5, (244, 165, 130, 235)), (1.0, (178, 24, 43, 255))]
    return [(f * m, rgba, f"{f * m:+.3g}" if f else "0") for f, rgba in colours]


# ---------------------------------------------------------------- QGIS --

def _categorized(layer, field, categories, symbol_factory, default_colour=None):
    """Categorized renderer; with default_colour an 'other' category catches values that appear later (a hazard layer is
    refreshed in place, so a new alert level or event category must not vanish from the map)."""
    cats = [QgsRendererCategory(value, symbol_factory(colour), label) for value, colour, label in categories]
    if default_colour:
        cats.append(QgsRendererCategory("", symbol_factory(default_colour), "other"))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field, cats))
    layer.triggerRepaint()
    return True


def _values(layer, field):
    return [f[field] for f in layer.getFeatures()]


def style_task_grid(layer):
    """Mapping-task polygons coloured by priority (High dark -> Low pale) with task ids as labels on small grids. Returns True when
    applied. Without any priority values the tasks get one neutral outline so an unranked grid does not look ranked."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        def fill(colour):
            return QgsFillSymbol.createSimple({"color": colour, "outline_color": "#ffffff", "outline_width": "0.3"})
        cats = priority_categories(_values(layer, "priority"))
        if not any(c[0] for c in cats):
            layer.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
                {"color": "255,255,255,0", "outline_color": "#555555", "outline_width": "0.4"})))
            layer.triggerRepaint()
        else:
            _categorized(layer, "priority", cats, fill)
        if layer.featureCount() <= LABEL_TASK_LIMIT:
            from .vector_tools import apply_labels
            apply_labels(layer.name(), target_field="task_id", font_size=8)
        return True
    except Exception:
        return False


def style_barrier_segments(layer, mode="block"):
    """Road segments a barrier affects: thick red (blocked) or orange (slowed) line. Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        symbol = QgsLineSymbol.createSimple({"color": BARRIER_COLORS.get(mode, BARRIER_COLORS["block"]), "width": "1.0",
                                              "capstyle": "round", "joinstyle": "round"})
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()
        return True
    except Exception:
        return False


def style_sample_points(layer, field="stratum"):
    """Survey sample points: small circles, one colour per stratum. Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        colours = qualitative_colors(_values(layer, field))

        def marker(colour):
            return QgsMarkerSymbol.createSimple({"name": "circle", "color": colour, "outline_color": "#ffffff",
                                                  "outline_width": "0.3", "size": "2.2"})
        return _categorized(layer, field, [(v, c, v) for v, c in colours.items()], marker)
    except Exception:
        return False


def style_hazard_layer(layer, kind):
    """kind 'gdacs' (by alert level), 'eonet' (by event category) or 'fires' (one small orange dot). Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        def marker(colour, size="3.2"):
            return QgsMarkerSymbol.createSimple({"name": "circle", "color": colour, "outline_color": "#333333",
                                                  "outline_width": "0.3", "size": size})
        if kind == "gdacs":
            fixed = [(k, c, k) for k, c in ALERT_COLORS.items()]       # always all three, so a later Red alert is not invisible
            return _categorized(layer, "alert_level", fixed, lambda c: marker(c, "4.2"), default_colour="#808080")
        if kind == "eonet":
            colours = qualitative_colors(_values(layer, "category"))
            return _categorized(layer, "category", [(v, c, v) for v, c in colours.items()], marker, default_colour="#808080")
        if kind == "fires":
            layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
                {"name": "circle", "color": FIRE_COLOR + "cc", "outline_color": "#7f2704", "outline_width": "0.2", "size": "2.0"})))
            layer.triggerRepaint()
            return True
        return False
    except Exception:
        return False


def style_diverging_raster(layer, band=1):
    """Before/after difference raster: blue (decrease) - transparent zero - red (increase), symmetric about zero. Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    try:
        from .raster_tools import _COLOR_RAMP_SHADER_ITEM, _RAMP_INTERPOLATED
        if _COLOR_RAMP_SHADER_ITEM is None or _RAMP_INTERPOLATED is None:
            return False
        provider = layer.dataProvider()
        stats = provider.bandStatistics(band)
        stops = diverging_stops(stats.minimumValue, stats.maximumValue)
        shader = QgsColorRampShader(stops[0][0], stops[-1][0])
        shader.setColorRampType(_RAMP_INTERPOLATED)
        shader.setColorRampItemList([_COLOR_RAMP_SHADER_ITEM(v, QColor(*rgba), label) for v, rgba, label in stops])
        from .output_style import _set_unit_legend
        _set_unit_legend(shader, {"min": "decrease", "max": "increase"})
        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(shader)
        layer.setRenderer(QgsSingleBandPseudoColorRenderer(provider, band, raster_shader))
        layer.triggerRepaint()
        from .output_style import send_under_vectors
        send_under_vectors(layer)
        return True
    except Exception:
        return False
