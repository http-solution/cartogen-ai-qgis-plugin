# -*- coding: utf-8 -*-
"""
Layer Cartography & Styling Tools for Cartogen AI.
"""

import math
import os

from .registry import register_tool
from ._qgis_enum_compat import resolve_qgis_enum
from ...logger import log_event

try:
    from qgis.core import (
        QgsProject, QgsCategorizedSymbolRenderer, QgsRendererCategory,
        QgsGraduatedSymbolRenderer, QgsRendererRange, QgsSymbol,
        QgsStyle, QgsHeatmapRenderer,
        QgsSingleSymbolRenderer, QgsWkbTypes, QgsMapLayer, QgsRasterLayer,
        QgsGradientColorRamp, QgsGradientStop, QgsUnitTypes, QgsRuleBasedRenderer, QgsExpression,
        QgsPointClusterRenderer, QgsPointDisplacementRenderer, QgsDistanceArea,
        QgsApplication,
    )
    from qgis.PyQt.QtGui import QColor
    import processing
    QGIS_AVAILABLE = True
except ImportError:
    QgsProject = None
    QgsCategorizedSymbolRenderer = None
    QgsRendererCategory = None
    QgsGraduatedSymbolRenderer = None
    QgsRendererRange = None
    QgsSymbol = None
    QgsStyle = None
    QgsHeatmapRenderer = None
    QgsSingleSymbolRenderer = None
    QgsWkbTypes = None
    QgsMapLayer = None
    QgsRasterLayer = None
    QgsGradientColorRamp = None
    QgsGradientStop = None
    QgsUnitTypes = None
    QgsRuleBasedRenderer = None
    QgsExpression = None
    QgsPointClusterRenderer = None
    QgsPointDisplacementRenderer = None
    QgsDistanceArea = None
    QgsApplication = None
    QColor = None
    processing = None
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


def _sanitize_filename(name):
    safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in str(name)).strip()
    return safe or "layer"


def _is_geopackage_layer(layer):
    """True if layer is backed by a GeoPackage (.gpkg) file via the OGR provider --
    the only case where saveStyleToDatabase (writing into the GeoPackage's own
    layer_styles table, OGC 12-128r17) is meaningful. Uses the same
    '|layername=...'-stripping convention as _derive_style_path since a
    GeoPackage layer's source() is 'C:/path/to/file.gpkg|layername=foo'."""
    try:
        if layer.providerType() != "ogr":
            return False
        source = layer.source() or ""
    except Exception:
        return False
    base_path = source.split("|", 1)[0] if source else ""
    return base_path.lower().endswith(".gpkg")


def _derive_style_path(layer, output_path):
    """Returns (path, used_desktop_fallback) for save_layer_style. Same
    convention as agent/tools/provenance_tools.py's _derive_sidecar_path:
    an explicit output_path always wins; otherwise sits the .qml beside the
    layer's own on-disk source (stripping a QGIS URI suffix like
    "|layername=..." off a GeoPackage/etc. source first) when that source
    resolves to a real file, falling back to Desktop (named after the
    layer) for a scratch/memory layer with no real file to sit beside."""
    if output_path:
        return output_path, False

    source = ""
    try:
        source = layer.source() or ""
    except Exception:
        source = ""
    base_path = source.split("|", 1)[0] if source else ""
    if base_path and os.path.isfile(base_path):
        return f"{base_path}.qml", False

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.expanduser("~")
    return os.path.join(desktop, f"{_sanitize_filename(layer.name())}.qml"), True


def _logarithmic_breaks(values, num_classes):
    """Computes num_classes-1 interior class-boundary values in log10 space, evenly
    spaced, then transforms back to the data's real units -- QGIS's own
    QgsGraduatedSymbolRenderer.Mode enum has no native 'Logarithmic' member (only
    EqualInterval/Quantile/Jenks/StdDev/Pretty), so this is computed directly in
    Python and passed through the same explicit-breaks renderer path
    apply_graduated_style already uses for caller-supplied breaks. Appropriate for
    heavily right-skewed data spanning orders of magnitude (e.g. population, income)
    where equal-interval classes would put almost every feature in the lowest class.
    Returns None if any value is <= 0 (log10 is undefined/complex there) or if every
    value is identical (nothing to subdivide)."""
    if not values or min(values) <= 0:
        return None
    lo, hi = min(values), max(values)
    if lo == hi:
        return None
    log_lo, log_hi = math.log10(lo), math.log10(hi)
    step = (log_hi - log_lo) / max(1, num_classes)
    return [10 ** (log_lo + step * i) for i in range(1, num_classes)]


def _classify_values(values, mode="auto", num_classes=5):
    """Pure-Python classification-method + color-ramp selection based on a
    field's value distribution (skewness/cardinality) -- no QGIS import, so
    this is directly unit-testable. Extracted out of apply_graduated_style
    so apply_graduated_symbol_style can reuse the exact same distribution-
    aware logic instead of a copy. Returns a QGIS-independent method NAME
    string; _resolve_classification_method (below) maps that to the real
    QgsGraduatedSymbolRenderer enum, which needs QGIS to even reference.
    'logarithmic' additionally returns 'breaks' (see _logarithmic_breaks) since
    it has no native QGIS Mode counterpart -- 'error' is set instead if the
    data can't be log-transformed (non-positive values, or all-identical)."""
    method, label = "jenks", "Jenks Natural Breaks"
    skewness = 0.0

    if len(values) > 5:
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        stddev = variance ** 0.5
        skewness = sum((x - mean) ** 3 for x in values) / (len(values) * (stddev ** 3)) if stddev > 0 else 0.0

    mode_l = (mode or "auto").lower()
    breaks = None
    error = None
    if mode_l == "equal":
        method, label = "equal_interval", "Equal Interval"
    elif mode_l == "quantile":
        method, label = "quantile", "Quantile"
    elif mode_l == "stddev":
        method, label = "stddev", "Standard Deviation"
    elif mode_l == "pretty":
        method, label = "pretty", "Pretty Breaks"
    elif mode_l == "logarithmic":
        method, label = "logarithmic", "Logarithmic Intervals"
        breaks = _logarithmic_breaks(values, num_classes)
        if breaks is None:
            error = "logarithmic mode needs all-positive, non-identical values -- got a non-positive value or a single repeated value."
    elif mode_l == "auto" and len(values) > 5:
        if abs(skewness) > 1.5:
            method, label = "jenks", "Jenks Natural Breaks (High Skew)"
        elif len(set(values)) < 10:
            method, label = "equal_interval", "Equal Interval"
        else:
            method, label = "quantile", "Quantile (Equal Count)"

    ramp = "Viridis" if abs(skewness) < 2 else "Cividis"
    result = {"method": method, "method_label": label, "ramp": ramp, "skewness": round(skewness, 3)}
    if breaks is not None:
        result["breaks"] = breaks
    if error is not None:
        result["error"] = error
    return result


def _resolve_classification_method(method_name):
    """Maps _classify_values' QGIS-independent method name to the real
    QgsGraduatedSymbolRenderer enum -- kept separate so _classify_values
    itself never needs QGIS to be importable. Resolves both the QGIS 4.x/Qt6
    scoped form (QgsGraduatedSymbolRenderer.Mode.Jenks) and the QGIS 3.x/Qt5
    flat form (QgsGraduatedSymbolRenderer.Jenks) via resolve_qgis_enum,
    rather than assuming one -- see _qgis_enum_compat.py. 'logarithmic' has
    no entry here since it's never passed to createRenderer -- see
    _logarithmic_breaks/_classify_values."""
    jenks = resolve_qgis_enum(QgsGraduatedSymbolRenderer, "Mode", "Jenks")
    return {
        "jenks": jenks,
        "equal_interval": resolve_qgis_enum(QgsGraduatedSymbolRenderer, "Mode", "EqualInterval"),
        "quantile": resolve_qgis_enum(QgsGraduatedSymbolRenderer, "Mode", "Quantile"),
        "stddev": resolve_qgis_enum(QgsGraduatedSymbolRenderer, "Mode", "StdDev"),
        "pretty": resolve_qgis_enum(QgsGraduatedSymbolRenderer, "Mode", "Pretty"),
    }.get(method_name, jenks)


def _create_graduated_renderer(layer, field, num_classes, method_name, method_enum, symbol, color_ramp):
    """Creates a QgsGraduatedSymbolRenderer.
    Prefers the modern QGIS 3.10+ / 4.x QgsClassificationMethodRegistry path
    (which avoids the QgsGraduatedSymbolRenderer.createRenderer deprecation warning),
    falling back to createRenderer() when running outside an active QgsApplication or
    in lean test environments where QgsApplication is mocked or uninitialized.
    """
    renderer = None
    if QgsApplication is not None and hasattr(QgsApplication, "classificationMethodRegistry"):
        try:
            reg = QgsApplication.classificationMethodRegistry()
            if reg is not None:
                method_id_map = {
                    "jenks": "Jenks",
                    "equal_interval": "EqualInterval",
                    "quantile": "Quantile",
                    "stddev": "StdDev",
                    "pretty": "Pretty",
                }
                method_id = method_id_map.get(method_name, "Jenks")
                method_obj = reg.method(method_id)
                if method_obj is not None:
                    renderer = QgsGraduatedSymbolRenderer(field)
                    renderer.setClassificationMethod(method_obj)
                    if symbol is not None:
                        renderer.setSourceSymbol(symbol)
                    if color_ramp is not None:
                        renderer.setSourceColorRamp(color_ramp)
                    renderer.updateClasses(layer, num_classes)
        except Exception:
            renderer = None

    if renderer is None and QgsGraduatedSymbolRenderer is not None and hasattr(QgsGraduatedSymbolRenderer, "createRenderer"):
        renderer = QgsGraduatedSymbolRenderer.createRenderer(
            layer,
            field,
            num_classes,
            method_enum,
            symbol,
            color_ramp,
        )
    return renderer


# Lower value = drawn on top. Points and lines are small features that a
# solid-fill polygon or raster added later (new layers land at the top of
# the layer tree by default) will otherwise completely bury -- ordering by
# geometry type keeps them visible without the model having to reason about
# a specific project's layer stack every time.
_GEOMETRY_DRAW_ORDER = {"point": 0, "line": 1, "polygon": 2, "raster": 3, "unknown": 4}


def _is_web_basemap(layer):
    """True for tile/web-service raster layers (the basemap), False for any other layer. Never raises."""
    try:
        return str(layer.providerType() or "").lower() in ("wms", "xyz", "arcgismapserver", "vectortile")
    except Exception:
        return False


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
    except Exception as e:
        log_event("swallowed_exception", tag="Tools", tool="layer_geometry_kind",
                  error_class=type(e).__name__, error=True)
    return "unknown"


def _default_opacity_for_geometry(geometry_type):
    """Polygon fills are the primary culprit for burying whatever's underneath
    them -- default those to a semi-transparent value. Point/line symbols
    stay fully opaque by default."""
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
        checked = node.itemVisibilityChecked()
        moved = root.insertChildNode(0, node.clone())
        root.removeChildNode(node)
        # Keep what the user (or an earlier tool) had ticked: a reorder must never show a hidden layer or hide a visible one.
        if moved is not None:
            moved.setItemVisibilityChecked(checked)


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

    # rc11 smoke test (#122): classify_facilities_by_access styles its own output (within blue, beyond red and larger,
    # on top); the model then called this tool on it and replaced that with generic categories whose size and order were
    # lost. The classified layer is already styled: say so and leave it.
    if field == "access_class" and "_access_" in layer_name:
        return {"success": True, "layer_name": layer_name, "already_styled": True,
                "message": f"'{layer_name}' was styled by the access analysis (within reach / beyond reach); left as it is."}

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
    "instantly. Unrecognized cluster names fall back to the default ramp. Pass explicit breaks "
    "(e.g. [10000, 25000, 50000, 100000]) for a fixed, mode-independent set of class boundaries -- "
    "for humanitarian decision maps, an operational threshold (e.g. response-capacity bands) often "
    "matters more than a statistically 'optimal' Jenks/quantile break, and breaks overrides mode entirely when given (point 13 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md).",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "field": {"type": "string"},
            "mode": {"type": "string", "description": "'auto' (default), 'equal', 'quantile', 'stddev' (classes centered on the mean +/- N standard deviations), 'pretty' (rounded, human-friendly breaks for a public-facing map), or 'logarithmic' (log-spaced classes for heavily right-skewed data spanning orders of magnitude, e.g. population or income -- needs all-positive, non-identical values). Ignored if breaks is given."},
            "num_classes": {"type": "integer", "description": "Number of classes to split the data into. Defaults to 5. Ignored if breaks is given."},
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
            "breaks": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Optional explicit class-boundary values (e.g. operational response "
                "thresholds), sorted ascending -- when given, these define the classes directly "
                "instead of an auto-selected classification method, overriding 'mode'. Data's actual "
                "min/max become the outer class bounds.",
            },
        },
        "required": ["layer_name", "field"],
    },
)
def apply_graduated_style(layer_name, field, mode="auto", opacity=None, cluster=None, breaks=None, num_classes=5):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if breaks is not None and len(breaks) < 1:
        return {"error": "breaks must contain at least one boundary value."}
    if num_classes < 2:
        return {"error": "num_classes must be at least 2."}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{field}' not found in '{layer_name}'"}

    try:
        values = [float(feat[field]) for feat in layer.getFeatures() if isinstance(feat[field], (int, float))]
        # Computed unconditionally (cheap, pure Python) so it's available
        # below whenever breaks is None, regardless of which ramp branch
        # runs -- a cluster-color match still needs a real classification
        # method/label, only the RAMP choice differs by branch.
        classification = _classify_values(values, mode, num_classes)
        # 'logarithmic' has no native QGIS Mode -- _classify_values computed explicit
        # breaks for it instead (or an 'error' if the data can't be log-transformed).
        # Adopting those as this call's own 'breaks' routes it through the same
        # manual-breaks renderer path as caller-supplied breaks below, rather than
        # needing a second, parallel renderer-construction branch.
        if breaks is None and classification["method"] == "logarithmic":
            if classification.get("error"):
                return {"error": classification["error"]}
            breaks = classification["breaks"]

        cluster_color = _match_cluster_color(cluster) if cluster else None
        cluster_warning = None
        if cluster_color:
            # Near-white to the cluster's color -- a sequential single-hue
            # ramp, the correct ramp family for ordered/graduated data
            # (matches this file's own qualitative-vs-diverging distinction
            # in apply_categorized_style above, applied here for sequential).
            color_ramp = QgsGradientColorRamp(QColor("#f7f7f7"), QColor(cluster_color))
            ramp_label = f"cluster:{cluster}"
        elif breaks is not None:
            # No auto-selected ramp to name yet when breaks is given --
            # a plain sequential default, since 'optimal ramp for this
            # distribution' isn't the question breaks is answering.
            if cluster:
                cluster_warning = f"'{cluster}' did not match a known humanitarian cluster name -- used the default ramp instead."
            color_ramp = QgsStyle.defaultStyle().colorRamp("Viridis")
            ramp_label = "Viridis"
        else:
            if cluster:
                cluster_warning = f"'{cluster}' did not match a known humanitarian cluster name -- used the default ramp instead."
            color_ramp = QgsStyle.defaultStyle().colorRamp(classification["ramp"])
            ramp_label = classification["ramp"]

        if breaks is not None:
            # Manual/defined-breaks classification (point 13 of
            # docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md): for
            # humanitarian decision maps an operational threshold often
            # matters more than a statistically 'optimal' class, so this
            # path builds QgsRendererRange objects directly from caller-
            # supplied boundaries instead of going through
            # QgsGraduatedSymbolRenderer.createRenderer's Jenks/equal-
            # interval/quantile modes. Not run against a live QGIS
            # session yet -- QgsRendererRange/updateColorRamp are stable,
            # long-standing PyQGIS API, but flagged per this project's own
            # convention for anything not live-verified.
            if not values:
                return {"error": f"No numeric values found in '{field}' to build breaks against."}
            sorted_breaks = sorted(breaks)
            bounds = [min(values)] + sorted_breaks + [max(values)]
            ranges = []
            for lower, upper in zip(bounds[:-1], bounds[1:]):
                label = f"{lower:,.2f} - {upper:,.2f}"
                symbol = QgsSymbol.defaultSymbol(layer.geometryType())
                ranges.append(QgsRendererRange(lower, upper, symbol, label))
            renderer = QgsGraduatedSymbolRenderer(field, ranges)
            renderer.updateColorRamp(color_ramp)
            classes = len(ranges)
            method_label = "Manual (defined breaks)"
        else:
            method = _resolve_classification_method(classification["method"])
            # QGIS-005, 2026-09-14 audit: method could be None if none of Jenks/
            # EqualInterval/Quantile resolved in this QGIS version -- previously passed
            # straight to createRenderer() below with no explicit check (see QGIS-004's
            # identical class of gap). Today inert (all 3 resolve fine currently).
            if method is None:
                return {"error": "Could not resolve a classification-mode enum in this QGIS version."}
            renderer = _create_graduated_renderer(
                layer,
                field,
                num_classes,
                classification["method"],
                method,
                QgsSymbol.defaultSymbol(layer.geometryType()),
                color_ramp,
            )
            classes = num_classes
            method_label = classification["method_label"]
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
            "classes": classes,
            "classification_method": method_label,
            "color_ramp": ramp_label,
            "opacity_percent": resolved_opacity,
        }
        if breaks is not None:
            result["breaks"] = sorted(breaks)
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
            "mode": {"type": "string", "description": "'auto' (default), 'equal', 'quantile', 'stddev', or 'pretty'."},
            "num_classes": {"type": "integer", "description": "Target number of size classes. Defaults to 5, capped down to the field's actual number of distinct values if fewer."},
            "color": {"type": "string", "description": "Hex color (e.g. '#3182bd') for every symbol -- size carries the meaning here, not color. Defaults to a semi-transparent blue."},
        },
        "required": ["layer_name", "field"],
    },
)
def apply_graduated_symbol_style(layer_name, field, min_size=4, max_size=24, mode="auto", num_classes=5, color="#3182bd"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if min_size <= 0 or max_size <= min_size:
        return {"error": "min_size must be positive and less than max_size."}
    if num_classes < 2:
        return {"error": "num_classes must be at least 2."}
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

        classification = _classify_values(values, mode, num_classes)
        if classification["method"] == "logarithmic":
            # Unlike apply_graduated_style, this function has no manual-breaks renderer
            # path to adopt _logarithmic_breaks' output into -- without this guard,
            # _resolve_classification_method would silently fall back to Jenks instead
            # of the logarithmic classes the caller actually asked for.
            return {"error": "mode='logarithmic' is not supported by apply_graduated_symbol_style -- use apply_graduated_style for log-spaced choropleth classes instead."}
        method = _resolve_classification_method(classification["method"])
        # QGIS-005, 2026-09-14 audit: see the identical guard's comment above (apply_graduated_style).
        if method is None:
            return {"error": "Could not resolve a classification-mode enum in this QGIS version."}
        num_classes = num_classes if len(set(values)) >= num_classes else max(2, len(set(values)))

        renderer = _create_graduated_renderer(
            layer,
            field,
            num_classes,
            classification["method"],
            method,
            QgsSymbol.defaultSymbol(layer.geometryType()),
            QgsStyle.defaultStyle().colorRamp(classification["ramp"]),
        )
        if renderer is None:
            return {"error": "Failed to create graduated renderer"}

        # Size (not fill color) carries the meaning here -- one consistent
        # hue across all classes, semi-transparent so overlapping large
        # circles don't fully obscure the basemap or each other. color is
        # caller-configurable (defaults to the original hardcoded blue) so
        # this can be themed per-map instead of always rendering the same
        # fixed color regardless of context.
        fixed_color = QColor(color)
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


@register_tool(
    "apply_rule_based_style",
    "Apply a rule-based renderer keyed to a controlled vocabulary of field values -- e.g. route/"
    "facility status (open/constrained/closed) -- with a FIXED color per value, rather than an "
    "auto-assigned qualitative palette (apply_categorized_style) or an auto-classified continuous "
    "gradient (apply_graduated_style). Use this when the categories carry a specific operational "
    "meaning that needs a caller-chosen color per value, not an auto-picked one. Any field value "
    "not matching one of the given rules automatically renders in a neutral gray 'Unknown / No "
    "data' class -- do not add your own catch-all rule, and never let an unassessed/missing "
    "status look the same as a real class.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "field": {"type": "string"},
            "rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string", "description": "The exact field value this rule matches."},
                        "label": {"type": "string", "description": "Legend label. Defaults to the value itself."},
                        "color_hex": {"type": "string", "description": "e.g. '#2E7D32'."},
                    },
                    "required": ["value", "color_hex"],
                },
                "description": "One entry per controlled-vocabulary value, e.g. "
                "[{\"value\": \"open\", \"label\": \"Open\", \"color_hex\": \"#2E7D32\"}, "
                "{\"value\": \"closed\", \"label\": \"Closed\", \"color_hex\": \"#B3261E\"}].",
            },
        },
        "required": ["layer_name", "field", "rules"],
    },
)
def apply_rule_based_style(layer_name, field, rules):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if not rules:
        return {"error": "rules must contain at least one entry."}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{field}' not found in '{layer_name}'"}

    try:
        col_ref = QgsExpression.quotedColumnRef(field)

        # QgsRuleBasedRenderer(symbol) is the documented PyQGIS-cookbook
        # pattern for building the first rule -- it wraps that symbol in a
        # root rule with one child, which is then edited in place; every
        # further rule is cloned from that first child rather than
        # constructed via QgsRuleBasedRenderer.Rule(...) directly, since the
        # clone-and-edit path is the same one the cookbook itself uses and
        # avoids guessing at that constructor's exact keyword-argument shape.
        first_spec = rules[0]
        first_symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        first_symbol.setColor(QColor(first_spec["color_hex"]))
        renderer = QgsRuleBasedRenderer(first_symbol)
        root_rule = renderer.rootRule()
        first_rule = root_rule.children()[0]
        first_rule.setFilterExpression(f"{col_ref} = {QgsExpression.quotedValue(str(first_spec['value']))}")
        first_rule.setLabel(first_spec.get("label") or str(first_spec["value"]))

        for spec in rules[1:]:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(QColor(spec["color_hex"]))
            rule = first_rule.clone()
            rule.setSymbol(symbol)
            rule.setFilterExpression(f"{col_ref} = {QgsExpression.quotedValue(str(spec['value']))}")
            rule.setLabel(spec.get("label") or str(spec["value"]))
            root_rule.appendChild(rule)

        # Catch-all: a QGIS rule-based renderer leaves any feature matching
        # no rule simply unrendered by default -- an explicit ELSE rule
        # makes an unassessed/missing status a visible, distinct class
        # instead of an invisible gap in the map. filterExpression("ELSE")
        # matches how QGIS Desktop's own "Add rule" dialog labels an else
        # rule's filter column; setIsElse(True) is what actually restricts
        # it to unmatched features at real render time -- live-confirmed via
        # an actual QgsMapRendererCustomPainterJob paint (not just
        # symbolsForFeature(), which by design can report a feature as
        # matching more than one rule -- rule-based rendering supports a
        # feature legitimately matching several non-else rules at once, so
        # an else rule also appearing in that query-time list does not mean
        # it double-paints; the real per-pixel render output is the only
        # trustworthy signal here, and it renders each segment in exactly
        # its one correct color).
        else_symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        else_symbol.setColor(QColor("#B0B7BD"))
        else_rule = first_rule.clone()
        else_rule.setSymbol(else_symbol)
        else_rule.setFilterExpression("ELSE")
        else_rule.setLabel("Unknown / No data")
        else_rule.setIsElse(True)
        root_rule.appendChild(else_rule)

        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return {
            "success": True,
            "layer_name": layer_name,
            "field": field,
            "rules_applied": len(rules),
            "classes": len(rules) + 1,
        }
    except Exception as e:
        return {"error": f"apply_rule_based_style failed: {e}"}


@register_tool("apply_heatmap_style", "Apply heatmap renderer to point layer with transparent zero-density baseline so basemaps remain visible.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "field": {"type": "string"}}, "required": ["layer_name"]})
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
        renderer.setRadius(12.0)
        if QgsUnitTypes is not None and hasattr(QgsUnitTypes, "RenderMillimeters"):
            renderer.setRadiusUnit(QgsUnitTypes.RenderMillimeters)

        # CRITICAL: Baseline stop (0.0) MUST have alpha = 0 (100% transparent) so
        # zero-density areas do not blot out the basemap with solid purple/dark color!
        if QColor is not None and QgsGradientColorRamp is not None and QgsGradientStop is not None:
            color1 = QColor(68, 1, 84, 0)       # 100% transparent zero stop
            color2 = QColor(253, 231, 37, 255)  # Peak yellow hotspot
            stops = [
                QgsGradientStop(0.15, QColor(65, 68, 135, 110)),
                QgsGradientStop(0.35, QColor(42, 120, 142, 170)),
                QgsGradientStop(0.60, QColor(35, 168, 119, 215)),
                QgsGradientStop(0.80, QColor(115, 208, 85, 245)),
            ]
            ramp = QgsGradientColorRamp(color1, color2, False, stops)
            renderer.setColorRamp(ramp)

        # Disable point text labels on heatmap layer: continuous density field clashes
        # with dense point label text boxes sitting directly over the hotspots
        if hasattr(layer, "setLabelsEnabled"):
            layer.setLabelsEnabled(False)

        layer.setRenderer(renderer)
        layer.triggerRepaint()

        # Focus canvas on layer extent
        from .vector_tools import zoom_to_layer
        zoom_to_layer(layer_name)

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
        try:
            from .output_style import style_continuous_raster
            style_continuous_raster(raster_layer, "density")   # a density surface in the default grey stretch was unreadable
        except Exception:
            pass
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
        # Bug found in a code-review pass (2026-09-20): this used to always apply
        # _default_opacity_for_geometry() when opacity was omitted, silently clobbering any
        # previously-configured transparency (e.g. via set_layer_transparency) even though
        # the caller never asked to touch opacity at all -- directly contradicting this
        # tool's own schema doc above ("Leaves current opacity unchanged if omitted").
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
        # Second key: an analysis output (a classified copy, a reach polygon, cost-banded roads) draws ABOVE the layer it was
        # made from. With geometry alone two point layers kept an arbitrary relative order, so the original facilities
        # covered the green/red classified copy on the rc10 smoke test and the access map looked unclassified.
        from .layout_style import arrange_rank
        # Third key: a web basemap (wms/xyz tiles) goes UNDER data rasters. Both are "raster" to the geometry key, so a fetched
        # population raster ended below the OSM basemap and was hidden by it (rc10 smoke test).
        ordered = sorted(layers, key=lambda layer: (_geometry_sort_key(_layer_geometry_kind(layer)),
                                                    1 if _is_web_basemap(layer) else 0,
                                                    arrange_rank(layer.name())))
        _reorder_top_level_layers(ordered)
        return {"success": True, "order_top_to_bottom": [layer.name() for layer in ordered]}
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
        return {"success": True, "order_top_to_bottom": [layer.name() for layer in layers]}
    except Exception as e:
        return {"error": f"set_layer_order failed: {e}"}


@register_tool(
    "save_layer_style",
    "Saves a layer's current symbology (renderer, colors, classification, labeling) to a real "
    ".qml style file on disk, so it can be reapplied later to this or another layer with "
    "load_layer_style -- for reusing a standard color scheme/classification across multiple "
    "layers or maps instead of rebuilding it with apply_categorized_style/apply_graduated_style "
    "every time. Without output_path, the file is saved beside the layer's own on-disk source "
    "(as '<source>.qml'); for a scratch/memory layer with no real source, it falls back to "
    "Desktop instead. For a GeoPackage-backed layer, the style is ALSO written into the "
    "GeoPackage's own layer_styles table (OGC 12-128r17) so it travels with the .gpkg file "
    "itself -- e.g. opening it in another QGIS install or a different GIS package that reads "
    "that table -- not just as an external sidecar that can be misplaced or left behind.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "output_path": {
                "type": "string",
                "description": "Optional explicit .qml file path. Defaults to beside the layer's own source file.",
            },
        },
        "required": ["layer_name"],
    },
)
def save_layer_style(layer_name, output_path=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    path, used_fallback = _derive_style_path(layer, output_path)
    try:
        message, ok = layer.saveNamedStyle(path)
    except Exception as e:
        return {"error": f"save_layer_style failed: {e}"}
    if not ok:
        return {"error": f"Failed to save style: {message}"}

    result = {"success": True, "layer_name": layer_name, "path": path}
    if used_fallback:
        result["warning"] = (
            "Layer has no real on-disk source (a scratch/memory layer, or one QGIS couldn't "
            "resolve a file path for) -- saved the style to Desktop instead of beside the "
            "source data."
        )

    # GeoPackage-only: also write into the file's own layer_styles table, not just the .qml
    # sidecar above. Best-effort -- a failure here doesn't undo the .qml save that already
    # succeeded, it's reported as a warning on an otherwise-successful result instead of an
    # error, since the .qml sidecar (this function's original, still-working behavior) is
    # already a real saved style even if the database write fails.
    if _is_geopackage_layer(layer):
        try:
            db_message, db_ok = layer.saveStyleToDatabase(
                layer.name(), f"Style for {layer.name()}", True, ""
            )
        except Exception as e:
            db_message, db_ok = str(e), False
        result["saved_to_geopackage_layer_styles"] = bool(db_ok)
        if not db_ok:
            result["geopackage_style_warning"] = f"Could not write to the GeoPackage's layer_styles table: {db_message}"

    return result


@register_tool(
    "load_layer_style",
    "Loads a previously saved .qml style file (from save_layer_style, or exported manually via "
    "QGIS's own Layer Properties -> Symbology -> Style -> Save Style) onto a layer, replacing "
    "its current symbology -- for reusing a standard humanitarian color scheme/classification "
    "across layers or maps instead of rebuilding it from scratch each time.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "style_path": {"type": "string", "description": "Path to the .qml style file to load."},
        },
        "required": ["layer_name", "style_path"],
    },
)
def load_layer_style(layer_name, style_path):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not os.path.isfile(style_path):
        return {"error": f"Style file not found: {style_path}"}

    try:
        message, ok = layer.loadNamedStyle(style_path)
    except Exception as e:
        return {"error": f"load_layer_style failed: {e}"}
    if not ok:
        return {"error": f"Failed to load style: {message or 'unrecognized .qml file'}"}

    layer.triggerRepaint()
    return {"success": True, "layer_name": layer_name, "style_path": style_path}


@register_tool(
    "export_layer_sld",
    "Exports a vector layer's symbology to an OGC SLD (Styled Layer Descriptor 1.1.0/1.0.0) file "
    "on disk. Use this when publishing styles to GeoServer/MapServer or sharing interoperable "
    "OGC styling with external GIS portals. Without output_path, saves beside the source file as "
    "'<source>.sld' (or to Desktop for scratch/memory layers).",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Vector layer to export styling from."},
            "output_path": {
                "type": "string",
                "description": "Optional explicit .sld file path. Defaults to beside the layer's source file.",
            },
        },
        "required": ["layer_name"],
    },
)
def export_layer_sld(layer_name, output_path=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    # Derive output path: reuse _derive_style_path logic with .sld extension
    if output_path:
        path, used_fallback = output_path, False
    else:
        source = ""
        try:
            source = layer.source() or ""
        except Exception:
            source = ""
        base_path = source.split("|", 1)[0] if source else ""
        if base_path and os.path.isfile(base_path):
            path, used_fallback = f"{base_path}.sld", False
        else:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            if not os.path.isdir(desktop):
                desktop = os.path.expanduser("~")
            path, used_fallback = os.path.join(desktop, f"{_sanitize_filename(layer.name())}.sld"), True

    try:
        # saveSldStyle returns (msg, ok) or raises depending on QGIS version
        save_res = layer.saveSldStyle(path)
        if isinstance(save_res, tuple) and len(save_res) >= 2:
            msg, ok = save_res[0], save_res[1]
        elif isinstance(save_res, bool):
            msg, ok = "", save_res
        else:
            msg, ok = "", True
    except Exception as e:
        return {"error": f"export_layer_sld failed: {e}"}

    if not ok:
        return {"error": f"Failed to export SLD: {msg or 'unknown error'}"}

    result = {"success": True, "layer_name": layer_name, "path": path}
    if used_fallback:
        result["warning"] = (
            "Layer has no real on-disk source (a scratch/memory layer, or one QGIS couldn't "
            "resolve a file path for) -- saved the SLD style to Desktop instead of beside the source data."
        )
    return result


@register_tool(
    "apply_point_cluster_style",
    "Applies a point cluster or point displacement renderer to a point layer so overlapping or densely "
    "clustered points are cleanly grouped on the map rather than drawing on top of each other. Mode 'cluster' "
    "(default) aggregates nearby points within a distance threshold into numeric cluster badges; mode "
    "'displacement' displays co-located or overlapping points arranged in a clean ring/spiral circle around "
    "the central coordinate.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Point layer to apply clustering/displacement to."},
            "mode": {
                "type": "string",
                "enum": ["cluster", "displacement"],
                "description": "'cluster' (default) for aggregate numeric count badges, 'displacement' for circle/ring offset around overlaps.",
            },
            "tolerance": {
                "type": "number",
                "description": "Cluster distance tolerance in millimeters (default 15.0 mm).",
            },
        },
        "required": ["layer_name"],
    },
)
def apply_point_cluster_style(layer_name, mode="cluster", tolerance=15.0):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    mode_l = (mode or "cluster").strip().lower()
    if mode_l not in ("cluster", "displacement"):
        return {"error": "mode must be either 'cluster' or 'displacement'."}

    try:
        current_renderer = layer.renderer()
        base_renderer = current_renderer.clone() if current_renderer else QgsSingleSymbolRenderer(QgsSymbol.defaultSymbol(layer.geometryType()))

        if mode_l == "displacement":
            renderer = QgsPointDisplacementRenderer()
            renderer.setEmbeddedRenderer(base_renderer)
            renderer.setTolerance(float(tolerance))
        else:
            renderer = QgsPointClusterRenderer()
            renderer.setEmbeddedRenderer(base_renderer)
            renderer.setTolerance(float(tolerance))

        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return {
            "success": True,
            "layer_name": layer_name,
            "mode": mode_l,
            "tolerance_mm": float(tolerance),
        }
    except Exception as e:
        return {"error": f"apply_point_cluster_style failed: {e}"}

