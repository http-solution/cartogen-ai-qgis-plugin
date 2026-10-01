# -*- coding: utf-8 -*-
"""How routing and reach results look on the map (visualization round 2, 2026-10-01).

Three rules, each an answer to something that read badly before:
1. Roads reached by a service area are graded by TRAVEL COST (near = dark, far = warm) in a handful of labelled bands,
   instead of one flat line colour, so the legend answers "how far is this road from the origin".
2. The reach polygons of population_access_gap (concave hull = headline, road buffer, convex hull = upper bound) get
   distinct translucent colours, are collected in ONE layer-tree group with the headline on top and visible, and the
   others hidden: the map shows the headline and the user can switch the bounds on to see the spread.
3. Facilities outside the reach are drawn in their own colour, larger, ON TOP of those inside, so the gap is the first thing
   seen rather than something buried under the reached points.

The pure half (band edges, labels, palettes) has no QGIS dependency and is unit-tested offline. The QGIS half uses the
public renderer and layer-tree API (QgsGraduatedSymbolRenderer, QgsCategorizedSymbolRenderer, QgsLayerTreeGroup) and is
exercised by tests/test_routing_style_live.py in the CI QGIS job.
"""

try:
    from qgis.core import (
        QgsCategorizedSymbolRenderer, QgsFillSymbol, QgsGraduatedSymbolRenderer, QgsLineSymbol, QgsMarkerSymbol,
        QgsProject, QgsRendererCategory, QgsRendererRange,
    )
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# Near the origin -> far from it. Dark to warm: legible on both a light basemap and the HOT style.
COST_RAMP = ("#264653", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51")
DEFAULT_BANDS = 5

# Reach polygons: (fill r,g,b,a), outline colour, outline style, width in mm.
REACH_STYLES = {
    "concave_hull": {"fill": "42,157,143,70", "outline": "42,157,143,255", "style": "solid", "width": "0.7"},
    "road_buffer": {"fill": "244,162,97,60", "outline": "230,120,40,255", "style": "solid", "width": "0.5"},
    "convex_hull": {"fill": "120,120,160,28", "outline": "90,90,140,255", "style": "dash", "width": "0.5"},
}
REACH_GROUP_PREFIX = "Reach figures"

# Facilities by access class. "beyond" is drawn above "within" (higher rendering pass) and larger.
ACCESS_STYLES = {
    "within": {"color": "#2a9d8f", "outline": "#ffffff", "size": "2.6", "pass": 0, "label": "within reach"},
    "beyond": {"color": "#d62828", "outline": "#ffffff", "size": "3.8", "pass": 1, "label": "beyond reach"},
}
ACCESS_OTHER = {"color": "#8d99ae", "outline": "#ffffff", "size": "2.6", "pass": 0, "label": "unknown"}


# ---------------------------------------------------------------- pure --

def cost_band_edges(max_cost, bands=DEFAULT_BANDS):
    """[(low, high), ...] splitting 0..max_cost into equal bands. A non-positive or non-numeric max gives one
    band so a degenerate result still renders."""
    try:
        top = float(max_cost)
    except (TypeError, ValueError):
        top = 0.0
    n = max(1, int(bands))
    if top <= 0:
        return [(0.0, 1.0)]
    step = top / n
    return [(i * step, (i + 1) * step if i < n - 1 else top) for i in range(n)]


def format_cost(value, unit):
    """'3 km' / '800 m' for metres, '45 min' / '1.5 h' for hours. Pure."""
    v = float(value)
    if unit == "hours":
        minutes = v * 60.0
        if minutes < 90:
            return f"{minutes:g} min" if abs(minutes - round(minutes)) < 0.05 else f"{minutes:.0f} min"
        return f"{v:.1f} h".replace(".0 h", " h")
    if v >= 1000:
        km = v / 1000.0
        return f"{km:.1f} km".replace(".0 km", " km")
    return f"{v:.0f} m"


def band_labels(edges, unit):
    return [f"{format_cost(lo, unit)} - {format_cost(hi, unit)}" for lo, hi in edges]


def band_colors(n):
    """n colours from COST_RAMP, evenly picked (the ramp itself when n == len(ramp))."""
    if n <= 1:
        return [COST_RAMP[0]]
    last = len(COST_RAMP) - 1
    return [COST_RAMP[round(i * last / (n - 1))] for i in range(n)]


def group_name_for(facility_layer):
    return f"{REACH_GROUP_PREFIX}: {facility_layer}"


def reach_layer_order(methods, headline):
    """Layer-tree order top to bottom: the headline first, then the bounds (tightest first). Pure."""
    rest = [m for m in ("road_buffer", "convex_hull", "concave_hull") if m in methods and m != headline]
    return ([headline] if headline in methods else []) + rest


def reach_visibility(methods, headline):
    """{method: visible}: only the headline is shown by default. Pure."""
    return {m: m == headline for m in methods}


# ----------------------------------------------------------- QGIS half --

def style_lines_by_cost(layer, field, edges, unit):
    """Graduated line renderer on `field` with one labelled band per (low, high) in `edges`. Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    colors = band_colors(len(edges))
    labels = band_labels(edges, unit)
    ranges = []
    for (lo, hi), color, label in zip(edges, colors, labels):
        symbol = QgsLineSymbol.createSimple({
            "color": color, "width": "0.8", "capstyle": "round", "joinstyle": "round"})
        ranges.append(QgsRendererRange(lo, hi, symbol, label))
    layer.setRenderer(QgsGraduatedSymbolRenderer(field, ranges))
    layer.triggerRepaint()
    return True


def style_reach_polygon(layer, method):
    """Translucent fill + outline for one reach figure (see REACH_STYLES). Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None or method not in REACH_STYLES:
        return False
    spec = REACH_STYLES[method]
    symbol = QgsFillSymbol.createSimple({
        "color": spec["fill"], "outline_color": spec["outline"],
        "outline_width": spec["width"], "outline_style": spec["style"]})
    layer.setRenderer(_single_symbol_renderer(symbol))
    layer.triggerRepaint()
    return True


def _single_symbol_renderer(symbol):
    from qgis.core import QgsSingleSymbolRenderer
    return QgsSingleSymbolRenderer(symbol)


def style_access_points(layer, field="access_class"):
    """Categorized renderer: 'beyond' red, larger and drawn above 'within' green; anything else grey. Returns True when applied."""
    if not QGIS_AVAILABLE or layer is None:
        return False
    categories = []
    for value, spec in list(ACCESS_STYLES.items()):
        categories.append(QgsRendererCategory(value, _access_symbol(spec), spec["label"]))
    categories.append(QgsRendererCategory("", _access_symbol(ACCESS_OTHER), ACCESS_OTHER["label"]))
    renderer = QgsCategorizedSymbolRenderer(field, categories)
    renderer.setUsingSymbolLevels(True)
    layer.setRenderer(renderer)
    layer.triggerRepaint()
    return True


def _access_symbol(spec):
    symbol = QgsMarkerSymbol.createSimple({
        "name": "circle", "color": spec["color"], "outline_color": spec["outline"],
        "outline_width": "0.4", "size": spec["size"]})
    symbol.symbolLayer(0).setRenderingPass(spec["pass"])
    return symbol


def group_reach_layers(layers_by_method, headline, facility_layer, extra_hidden=(), project=None):
    """Puts the reach layers in one group at the top of the layer tree: headline first and visible, the other figures
    below it and hidden. `layers_by_method` is {method: layer}; `extra_hidden` are further layers (e.g. the per-area
    intersections) that go in the group, hidden. Layers must already be in the project; they are added to the group
    without being removed from the project. Returns the group, or None outside QGIS."""
    if not QGIS_AVAILABLE:
        return None
    project = project or QgsProject.instance()
    root = project.layerTreeRoot()
    name = group_name_for(facility_layer)
    group = root.findGroup(name)
    if group is None:
        group = root.insertGroup(0, name)
    order = reach_layer_order(list(layers_by_method), headline)
    visible = reach_visibility(list(layers_by_method), headline)
    ordered_layers = [(m, layers_by_method[m], visible[m]) for m in order] + \
                     [(None, lyr, False) for lyr in extra_hidden if lyr is not None]
    for position, (method, layer, show) in enumerate(ordered_layers):
        node = group.findLayer(layer.id())
        if node is None:
            top_level = _root_level_node(root, layer.id())
            if top_level is not None:
                # The layer already has a top-level node (it was added the ordinary way). A second node for it is the
                # F07 duplicate, and removing the first is what broke live tests, so leave it where it is and only
                # set its visibility.
                top_level.setItemVisibilityChecked(bool(show))
                continue
            group.insertLayer(position, layer)
            node = group.findLayer(layer.id())
        if node is not None:
            node.setItemVisibilityChecked(bool(show))
    return group


def _root_level_node(root, layer_id):
    """The layer node sitting directly under `root` (not inside a group) for layer_id, or None."""
    for child in root.children():
        try:
            if child.layerId() == layer_id:
                return child
        except AttributeError:
            continue
    return None
