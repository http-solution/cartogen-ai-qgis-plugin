# -*- coding: utf-8 -*-
"""
Layer Cartography & Styling Tools for Cartogen AI.
"""

from .registry import register_tool

try:
    from qgis.core import (
        QgsProject, QgsCategorizedSymbolRenderer, QgsRendererCategory,
        QgsGraduatedSymbolRenderer, QgsRendererRange, QgsSymbol,
        QgsStyle, QgsColorRampLegendNode, QgsHeatmapRenderer,
        QgsSingleSymbolRenderer, QgsWkbTypes, QgsMapLayer, QgsRasterLayer,
        QgsGradientColorRamp,
    )
    from qgis.PyQt.QtGui import QColor
    import processing
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


# Commonly used humanitarian cluster color associations, as seen across
# ReliefWeb/Shelter Cluster/humanitarian mapping products -- keyed to the 11
# IASC global clusters. NOT a single pinned official OCHA hex-code standard:
# checked OCHA's own graphics stylebook and branding site (brand.unocha.org)
# and neither publishes per-cluster hex values, so these are a reasonable,
# widely-recognized choice rather than a verified authoritative spec --
# stated honestly in the tool description below, not oversold.
_HUMANITARIAN_CLUSTER_COLORS = {
    "camp coordination and camp management": "#14B8A6",  # teal
    "early recovery": "#B45309",                          # amber-brown
    "education": "#EC4899",                               # magenta/pink
    "emergency shelter": "#A0522D",                       # terracotta/brown
    "emergency telecommunications": "#64748B",            # blue-grey
    "food security": "#F59E0B",                           # orange
    "health": "#DC2626",                                  # red
    "logistics": "#4B5563",                               # slate grey
    "nutrition": "#EAB308",                                # gold/yellow
    "protection": "#7C3AED",                              # purple
    "wash": "#38BDF8",                                    # light blue
}

_CLUSTER_ALIASES = {
    "cccm": "camp coordination and camp management",
    "camp coordination": "camp coordination and camp management",
    "camp management": "camp coordination and camp management",
    "shelter": "emergency shelter",
    "etc": "emergency telecommunications",
    "telecoms": "emergency telecommunications",
    "telecommunications": "emergency telecommunications",
    "fsl": "food security",
    "food security and livelihoods": "food security",
    "food security & livelihoods": "food security",
    "water sanitation and hygiene": "wash",
    "water, sanitation and hygiene": "wash",
    "water sanitation hygiene": "wash",
}

_CLUSTER_PALETTE_NAMES = {"humanitarian_cluster", "ocha"}


def _match_cluster_color(value):
    """Case/whitespace-insensitive lookup of a value against the IASC global
    cluster names and common aliases/abbreviations. Pure Python, no QGIS
    needed. Returns a hex color string, or None if the value doesn't match
    any known cluster name."""
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    key = _CLUSTER_ALIASES.get(key, key)
    return _HUMANITARIAN_CLUSTER_COLORS.get(key)


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


def _classify_values(values, mode="auto"):
    """Pure-Python classification-method + color-ramp selection based on a
    field's value distribution (skewness/cardinality) -- no QGIS import, so
    this is directly unit-testable. Extracted out of apply_graduated_style
    so apply_graduated_symbol_style can reuse the exact same distribution-
    aware logic instead of a copy. Returns a QGIS-independent method NAME
    string; _resolve_classification_method (below) maps that to the real
    QgsGraduatedSymbolRenderer enum, which needs QGIS to even reference."""
    method, label = "jenks", "Jenks Natural Breaks"
    skewness = 0.0

    if len(values) > 5:
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        stddev = variance ** 0.5
        skewness = sum((x - mean) ** 3 for x in values) / (len(values) * (stddev ** 3)) if stddev > 0 else 0.0

    mode_l = (mode or "auto").lower()
    if mode_l == "equal":
        method, label = "equal_interval", "Equal Interval"
    elif mode_l == "quantile":
        method, label = "quantile", "Quantile"
    elif mode_l == "auto" and len(values) > 5:
        if abs(skewness) > 1.5:
            method, label = "jenks", "Jenks Natural Breaks (High Skew)"
        elif len(set(values)) < 10:
            method, label = "equal_interval", "Equal Interval"
        else:
            method, label = "quantile", "Quantile (Equal Count)"

    ramp = "Viridis" if abs(skewness) < 2 else "Cividis"
    return {"method": method, "method_label": label, "ramp": ramp, "skewness": round(skewness, 3)}


def _resolve_classification_method(method_name):
    """Maps _classify_values' QGIS-independent method name to the real
    QgsGraduatedSymbolRenderer enum -- kept separate so _classify_values
    itself never needs QGIS to be importable."""
    return {
        "jenks": QgsGraduatedSymbolRenderer.Jenks,
        "equal_interval": QgsGraduatedSymbolRenderer.EqualInterval,
        "quantile": QgsGraduatedSymbolRenderer.Quantile,
    }.get(method_name, QgsGraduatedSymbolRenderer.Jenks)


# Lower value = drawn on top. Points and lines are small features that a
# solid-fill polygon or raster added later (new layers land at the top of
# the layer tree by default) will otherwise completely bury -- ordering by
# geometry type keeps them visible without the model having to reason about
# a specific project's layer stack every time.
_GEOMETRY_DRAW_ORDER = {"point": 0, "line": 1, "polygon": 2, "raster": 3, "unknown": 4}


def _geometry_sort_key(geometry_kind):
    """Pure Python, no QGIS import -- see _layer_geometry_kind below for the
    QGIS-dependent classification this is applied to."""
    return _GEOMETRY_DRAW_ORDER.get(geometry_kind, _GEOMETRY_DRAW_ORDER["unknown"])


def _layer_geometry_kind(layer):
    if not QGIS_AVAILABLE:
        return "unknown"
    try:
        if layer.type() == QgsMapLayer.LayerType.RasterLayer:
            return "raster"
    except Exception:
        pass
    try:
        gt = layer.geometryType()
        if gt == QgsWkbTypes.GeometryType.PointGeometry:
            return "point"
        if gt == QgsWkbTypes.GeometryType.LineGeometry:
            return "line"
        if gt == QgsWkbTypes.GeometryType.PolygonGeometry:
            return "polygon"
    except Exception:
        pass
    return "unknown"


def _default_opacity_for_geometry(geometry_type):
    """Polygon fills are the usual culprit for burying whatever's underneath
    them -- default those to a semi-transparent value. Point/line symbols
    stay fully opaque by default; a washed-out marker is harder to read, not
    easier, and they're rarely what's doing the burying."""
    return 75 if geometry_type == QgsWkbTypes.GeometryType.PolygonGeometry else 100


def _apply_opacity(layer, opacity):
    resolved = max(0, min(100, opacity))
    layer.setOpacity(resolved / 100.0)
    return resolved


def _reorder_top_level_layers(ordered_layers):
    """Reorders layers directly under the project root to match
    ordered_layers (first = topmost). Layers is a QGIS project's layer tree
    can be filed into subgroups, but every layer-adding tool in this codebase
    uses QgsProject.instance().addMapLayer(), which always places new layers
    at the top level -- so only the top level is handled here, matching how
    layers actually get added in practice.

    Processed in reverse, each inserted at position 0: the first layer
    processed (the list's last item) starts at position 0, then each
    subsequent insert-at-0 pushes it back down, so by the end the list's
    first item ends up on top."""
    root = QgsProject.instance().layerTreeRoot()
    for layer in reversed(ordered_layers):
        node = root.findLayer(layer.id())
        if node is None or node.parent() is not root:
            continue
        root.insertChildNode(0, node.clone())
        root.removeChildNode(node)


@register_tool(
    "apply_categorized_style",
    "Apply categorized style renderer based on field values. Pass palette='humanitarian_cluster' "
    "to color categories that match a known IASC global cluster name (Health, WASH, Food Security, "
    "Protection, Emergency Shelter, Nutrition, Education, Logistics, CCCM, Early Recovery, "
    "Emergency Telecommunications, plus common aliases like 'FSL' or 'Shelter') using commonly "
    "recognized humanitarian cluster colors -- the map a field coordinator recognizes instantly "
    "instead of one they have to re-read the legend for. Categories that don't match a known "
    "cluster name keep the default qualitative color assignment.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "field": {"type": "string"},
            "opacity": {
                "type": "number",
                "description": "0-100. Defaults to 75 for polygon layers (so overlapping layers/basemap "
                "underneath stay visible) and 100 for points/lines.",
            },
            "palette": {
                "type": "string",
                "description": "Optional. 'humanitarian_cluster' (or 'ocha') colors categories matching a "
                "known IASC cluster name/alias; unmatched categories keep the default palette.",
            },
        },
        "required": ["layer_name", "field"],
    },
)
def apply_categorized_style(layer_name, field, opacity=None, palette=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{field}' not found in '{layer_name}'"}

    try:
        categories = []
        unique_values = layer.uniqueValues(layer.fields().indexOf(field))
        default_symbol = QgsSymbol.defaultSymbol(layer.geometryType())

        for val in unique_values:
            sym = default_symbol.clone() if default_symbol else QgsSymbol.defaultSymbol(layer.geometryType())
            cat = QgsRendererCategory(val, sym, str(val))
            categories.append(cat)

        renderer = QgsCategorizedSymbolRenderer(field, categories)
        style = QgsStyle.defaultStyle()
        # Categorical/nominal values (e.g. a governorate or type name) have no
        # inherent order, so a DIVERGING ramp like "Spectral" (previously used
        # here for everything) is the wrong tool -- diverging ramps encode
        # "how far above/below a midpoint", which is meaningless for unordered
        # categories, and can make unrelated categories look misleadingly
        # similar or extreme. A qualitative ColorBrewer ramp is designed
        # specifically for maximally distinguishing unordered categories.
        ramp = style.colorRamp("Set2") or style.colorRamp("Spectral")
        if ramp:
            renderer.updateColorRamp(ramp)

        cluster_matches = {}
        palette_warning = None
        if palette:
            if palette.strip().lower() in _CLUSTER_PALETTE_NAMES:
                # Applied AFTER updateColorRamp above, which reassigns colors
                # across every category -- overriding matched categories here
                # instead of before is what makes the explicit cluster colors
                # survive rather than get immediately overwritten.
                for i, cat in enumerate(renderer.categories()):
                    color_hex = _match_cluster_color(cat.value())
                    if color_hex:
                        sym = cat.symbol().clone()
                        sym.setColor(QColor(color_hex))
                        renderer.updateCategorySymbol(i, sym)
                        cluster_matches[str(cat.value())] = color_hex
            else:
                palette_warning = f"'{palette}' is not a known palette name -- used the default qualitative palette instead."

        layer.setRenderer(renderer)
        resolved_opacity = _apply_opacity(
            layer, opacity if opacity is not None else _default_opacity_for_geometry(layer.geometryType())
        )
        layer.triggerRepaint()
        result = {
            "success": True,
            "layer_name": layer_name,
            "categories_count": len(categories),
            "opacity_percent": resolved_opacity,
        }
        if palette:
            result["palette"] = palette
            result["cluster_matches"] = cluster_matches
            if palette_warning:
                result["palette_warning"] = palette_warning
        return result
    except Exception as e:
        return {"error": f"apply_categorized_style failed: {e}"}


@register_tool(
    "apply_graduated_style",
    "Apply smart graduated choropleth style analyzing field distribution for optimal breaks. Pass "
    "cluster (e.g. 'WASH', 'Health', 'Food Security') to tint the ramp toward that IASC cluster's "
    "commonly recognized color instead of the auto-selected Viridis/Cividis ramp -- e.g. a WASH "
    "coverage % choropleth rendered in WASH's color, for the map a field coordinator recognizes "
    "instantly. Unrecognized cluster names fall back to the default ramp.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "field": {"type": "string"},
            "mode": {"type": "string"},
            "opacity": {
                "type": "number",
                "description": "0-100. Defaults to 75 for polygon layers (so overlapping layers/basemap "
                "underneath stay visible) and 100 for points/lines.",
            },
            "cluster": {
                "type": "string",
                "description": "Optional IASC cluster name/alias (e.g. 'WASH', 'Health') to tint the ramp "
                "toward that cluster's color instead of the auto-selected one.",
            },
        },
        "required": ["layer_name", "field"],
    },
)
def apply_graduated_style(layer_name, field, mode="auto", opacity=None, cluster=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{field}' not found in '{layer_name}'"}

    try:
        values = [float(feat[field]) for feat in layer.getFeatures() if isinstance(feat[field], (int, float))]
        classification = _classify_values(values, mode)
        method = _resolve_classification_method(classification["method"])

        cluster_color = _match_cluster_color(cluster) if cluster else None
        cluster_warning = None
        if cluster_color:
            # Near-white to the cluster's color -- a sequential single-hue
            # ramp, the correct ramp family for ordered/graduated data
            # (matches this file's own qualitative-vs-diverging distinction
            # in apply_categorized_style above, applied here for sequential).
            color_ramp = QgsGradientColorRamp(QColor("#f7f7f7"), QColor(cluster_color))
            ramp_label = f"cluster:{cluster}"
        else:
            if cluster:
                cluster_warning = f"'{cluster}' did not match a known humanitarian cluster name -- used the default ramp instead."
            color_ramp = QgsStyle.defaultStyle().colorRamp(classification["ramp"])
            ramp_label = classification["ramp"]

        renderer = QgsGraduatedSymbolRenderer.createRenderer(
            layer,
            field,
            5,
            method,
            QgsSymbol.defaultSymbol(layer.geometryType()),
            color_ramp,
        )
        if renderer is None:
            return {"error": "Failed to create graduated renderer"}

        layer.setRenderer(renderer)
        resolved_opacity = _apply_opacity(
            layer, opacity if opacity is not None else _default_opacity_for_geometry(layer.geometryType())
        )
        layer.triggerRepaint()
        result = {
            "success": True,
            "layer_name": layer_name,
            "field": field,
            "classes": 5,
            "classification_method": classification["method_label"],
            "color_ramp": ramp_label,
            "opacity_percent": resolved_opacity,
        }
        if cluster_warning:
            result["cluster_warning"] = cluster_warning
        return result
    except Exception as e:
        return {"error": f"apply_graduated_style failed: {e}"}


@register_tool(
    "apply_graduated_symbol_style",
    "Apply a graduated (proportional) SYMBOL SIZE style to a point layer -- circles scaled from a "
    "minimum to a maximum size based on a numeric field, analyzing the field's distribution for "
    "optimal class breaks the same way apply_graduated_style does for choropleth fill color. Use "
    "this for point data (e.g. 'graduated symbol map', 'proportional circles') instead of hand-"
    "writing QgsGraduatedSymbolRenderer/QgsRendererRange code via execute_pyqgis_script.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "field": {"type": "string"},
            "min_size": {"type": "number", "description": "Smallest symbol size in mm. Defaults to 4."},
            "max_size": {"type": "number", "description": "Largest symbol size in mm. Defaults to 24."},
            "mode": {"type": "string", "description": "'auto' (default), 'equal', or 'quantile'."},
        },
        "required": ["layer_name", "field"],
    },
)
def apply_graduated_symbol_style(layer_name, field, min_size=4, max_size=24, mode="auto"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if min_size <= 0 or max_size <= min_size:
        return {"error": "min_size must be positive and less than max_size."}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{field}' not found in '{layer_name}'"}
    if layer.geometryType() != QgsWkbTypes.GeometryType.PointGeometry:
        return {"error": "apply_graduated_symbol_style only supports point layers -- use apply_graduated_style for polygon choropleths."}

    try:
        values = [float(feat[field]) for feat in layer.getFeatures() if isinstance(feat[field], (int, float))]
        if len(values) < 2:
            return {"error": f"Not enough numeric values in '{field}' to build a graduated symbol style."}

        classification = _classify_values(values, mode)
        method = _resolve_classification_method(classification["method"])
        num_classes = 5 if len(set(values)) >= 5 else max(2, len(set(values)))

        renderer = QgsGraduatedSymbolRenderer.createRenderer(
            layer,
            field,
            num_classes,
            method,
            QgsSymbol.defaultSymbol(layer.geometryType()),
            QgsStyle.defaultStyle().colorRamp(classification["ramp"]),
        )
        if renderer is None:
            return {"error": "Failed to create graduated renderer"}

        # Size (not fill color) carries the meaning here -- one consistent
        # hue across all classes, semi-transparent so overlapping large
        # circles don't fully obscure the basemap or each other.
        fixed_color = QColor("#3182bd")
        fixed_color.setAlpha(190)
        ranges = renderer.ranges()
        n = len(ranges)
        for i, rng in enumerate(ranges):
            size = min_size + (max_size - min_size) * (i / max(1, n - 1))
            sym = rng.symbol().clone()
            sym.setSize(round(size, 1))
            sym.setColor(fixed_color)
            renderer.updateRangeSymbol(i, sym)

        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return {
            "success": True,
            "layer_name": layer_name,
            "field": field,
            "classes": n,
            "classification_method": classification["method_label"],
            "size_range_mm": [min_size, max_size],
        }
    except Exception as e:
        return {"error": f"apply_graduated_symbol_style failed: {e}"}


@register_tool("apply_heatmap_style", "Apply heatmap renderer to point layer.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "field": {"type": "string"}}, "required": ["layer_name"]})
def apply_heatmap_style(layer_name, field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    try:
        renderer = QgsHeatmapRenderer()
        if field and field in [f.name() for f in layer.fields()]:
            renderer.setWeightExpression(f'"{field}"')
        renderer.setRadius(10)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return {"success": True, "layer_name": layer_name}
    except Exception as e:
        return {"error": f"Heatmap style failed: {e}"}


@register_tool(
    "hotspot_analysis",
    "Compute a kernel density estimation surface from a point layer -- a real statistical density "
    "raster (higher values = more points/higher intensity nearby), not just a visual-only renderer. "
    "apply_heatmap_style changes how a layer LOOKS on screen but produces no reusable data; this "
    "tool produces an actual raster you can run zonal_statistics against (e.g. rank districts by "
    "incident density) or feed into weighted_overlay_analysis for risk-surface analysis. Use this "
    "for real hotspot/risk-concentration analysis, apply_heatmap_style for a quick visual only.",
    {
        "type": "object",
        "properties": {
            "point_layer": {"type": "string"},
            "radius": {"type": "number", "description": "Kernel search radius in the layer's map units. Larger = smoother, less localized."},
            "pixel_size": {"type": "number", "description": "Output raster cell size in map units. Defaults to radius/10."},
            "weight_field": {"type": "string", "description": "Optional numeric field to weight points by (e.g. severity) instead of treating every point equally."},
        },
        "required": ["point_layer", "radius"],
    },
)
def hotspot_analysis(point_layer, radius, pixel_size=None, weight_field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if radius <= 0:
        return {"error": "radius must be positive."}
    layer = _find_layer_by_name(point_layer)
    if layer is None:
        return {"error": f"Layer '{point_layer}' not found"}
    if weight_field and weight_field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{weight_field}' not found in '{point_layer}'"}

    resolved_pixel_size = pixel_size or (radius / 10)
    try:
        params = {
            "INPUT": layer,
            "RADIUS": radius,
            "PIXEL_SIZE": resolved_pixel_size,
            "KERNEL": 0,
            "OUTPUT": "TEMPORARY_OUTPUT",
        }
        if weight_field:
            params["WEIGHT_FIELD"] = weight_field
        output = processing.run("qgis:heatmapkerneldensityestimation", params)
        out_path = output.get("OUTPUT")
        if not out_path:
            return {"error": "hotspot_analysis produced no output."}

        result_name = f"{point_layer}_hotspot_density"
        raster_layer = QgsRasterLayer(out_path, result_name)
        if not raster_layer.isValid():
            return {"error": "Generated density raster is invalid."}
        QgsProject.instance().addMapLayer(raster_layer)
        return {"success": True, "layer_name": result_name, "radius": radius, "pixel_size": resolved_pixel_size}
    except Exception as e:
        return {"error": f"hotspot_analysis failed: {e}"}


@register_tool(
    "change_layer_color",
    "Change layer symbol fill/line color using hex string.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "color_hex": {"type": "string"},
            "opacity": {"type": "number", "description": "Optional, 0-100. Leaves current opacity unchanged if omitted."},
        },
        "required": ["layer_name", "color_hex"],
    },
)
def change_layer_color(layer_name, color_hex, opacity=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if opacity is not None and not (0 <= opacity <= 100):
        return {"error": "opacity must be between 0 and 100."}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    color = QColor(color_hex)
    if not color.isValid():
        return {"error": f"Invalid color: {color_hex}"}
    try:
        renderer = layer.renderer()
        if renderer is None or not hasattr(renderer, "symbol"):
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(color)
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        else:
            renderer.symbol().setColor(color)
        result = {"success": True, "layer_name": layer_name, "color": color_hex}
        if opacity is not None:
            result["opacity_percent"] = _apply_opacity(layer, opacity)
        layer.triggerRepaint()
        return result
    except Exception as e:
        return {"error": f"change_layer_color failed: {e}"}


@register_tool(
    "set_layer_transparency",
    "Set a layer's overall opacity (0-100). Use this to make an area/polygon layer semi-"
    "transparent so layers or features underneath it (e.g. point markers) stay visible instead "
    "of being fully covered by a solid fill.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "opacity_percent": {"type": "number", "description": "0 (fully transparent) to 100 (fully opaque)."},
        },
        "required": ["layer_name", "opacity_percent"],
    },
)
def set_layer_transparency(layer_name, opacity_percent):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if not (0 <= opacity_percent <= 100):
        return {"error": "opacity_percent must be between 0 and 100."}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    try:
        resolved = _apply_opacity(layer, opacity_percent)
        layer.triggerRepaint()
        return {"success": True, "layer_name": layer_name, "opacity_percent": resolved}
    except Exception as e:
        return {"error": f"set_layer_transparency failed: {e}"}


@register_tool(
    "auto_arrange_layer_order",
    "Reorders every top-level layer in the project by geometry type so small features stay "
    "visible: points on top, then lines, then polygons, then rasters at the bottom. Call this "
    "after adding or styling multiple overlapping layers -- e.g. point markers plus an area/"
    "boundary polygon -- so the polygon's fill doesn't bury the points underneath it. This is "
    "the usual fix when a map with several layers looks 'messy' or a small icon layer has "
    "disappeared under a larger area layer.",
    {"type": "object", "properties": {}},
)
def auto_arrange_layer_order():
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    try:
        layers = list(QgsProject.instance().mapLayers().values())
        if not layers:
            return {"error": "No layers in the project."}
        ordered = sorted(layers, key=lambda l: _geometry_sort_key(_layer_geometry_kind(l)))
        _reorder_top_level_layers(ordered)
        return {"success": True, "order_top_to_bottom": [l.name() for l in ordered]}
    except Exception as e:
        return {"error": f"auto_arrange_layer_order failed: {e}"}


@register_tool(
    "set_layer_order",
    "Explicitly sets the draw order of the given layers, top to bottom (the first name in the "
    "list renders on top of the rest, on top of everything else in the project). Use this when "
    "auto_arrange_layer_order's point > line > polygon > raster default isn't what's needed -- "
    "e.g. two polygon layers that need a specific stacking order relative to each other.",
    {
        "type": "object",
        "properties": {
            "layer_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Layer names in the desired draw order, first = topmost.",
            },
        },
        "required": ["layer_names"],
    },
)
def set_layer_order(layer_names):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if not layer_names:
        return {"error": "layer_names must not be empty."}
    layers = []
    missing = []
    for name in layer_names:
        layer = _find_layer_by_name(name)
        if layer is None:
            missing.append(name)
        else:
            layers.append(layer)
    if missing:
        return {"error": f"Layer(s) not found: {missing}"}
    try:
        _reorder_top_level_layers(layers)
        return {"success": True, "order_top_to_bottom": [l.name() for l in layers]}
    except Exception as e:
        return {"error": f"set_layer_order failed: {e}"}
