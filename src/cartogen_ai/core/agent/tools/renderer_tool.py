"""set_renderer (PLAN-023 R10-3): merged features, inverted polygons, embedded symbols, no symbols, 2.5D, or back to a single symbol.

A renderer change replaces how the layer is DRAWN; it never touches the data. Two things make it safe to try: merged_features and inverted_polygons keep the layer's current look as their
inner renderer, and before any change the current style is saved in the layer's own style manager under the name 'before <kind>' (the Styles item of the layer's right-click menu, or
the style manager panel), so the previous look can be restored from there. The reply reads the new renderer type back and names the saved style. The renderer types and where each applies
are in renderer_ops.py (pure, tested offline). The layer's style is stored in the project, so the project must be saved to keep it.

Written without a QGIS install; tests/test_renderer_tool_live.py is its first execution in CI."""
from . import renderer_ops as ro
from .attribute_edit_tools import _layer
from .registry import register_tool

try:
    from qgis.core import (Qgs25DRenderer, QgsEmbeddedSymbolRenderer, QgsInvertedPolygonRenderer, QgsMergedFeatureRenderer, QgsNullSymbolRenderer, QgsSingleSymbolRenderer, QgsSymbol,
                           QgsWkbTypes)
    from qgis.PyQt.QtGui import QColor
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

WRAPPERS = ("mergedFeatureRenderer", "invertedPolygonRenderer")


def _geometry_word(layer):
    """'point', 'line' or 'polygon' for the layer, or None for a table. Needs QGIS."""
    kind = QgsWkbTypes.geometryType(layer.wkbType())
    return {QgsWkbTypes.GeometryType.PointGeometry: "point", QgsWkbTypes.GeometryType.LineGeometry: "line", QgsWkbTypes.GeometryType.PolygonGeometry: "polygon"}.get(kind)


def _inner(layer):
    """A clone of the layer's current renderer with any merged / inverted wrapper taken off. Needs QGIS."""
    current = layer.renderer().clone()
    while current.type() in WRAPPERS and current.embeddedRenderer() is not None:
        current = current.embeddedRenderer().clone()
    return current


def _save_current_style(layer, kind):
    """Keeps the current style in the layer's style manager as 'before <kind>' (numbered when taken); returns the name, or None when QGIS refused. Needs QGIS."""
    manager = layer.styleManager()
    taken = set(manager.styles())
    name, n = f"before {kind}", 1
    while name in taken:
        n += 1
        name = f"before {kind} ({n})"
    return name if manager.addStyleFromLayer(name) else None


def _make(layer, kind, options):
    """(new renderer, error text or None). Needs QGIS."""
    if kind in ("merged_features", "inverted_polygons"):
        cls = QgsMergedFeatureRenderer if kind == "merged_features" else QgsInvertedPolygonRenderer
        return cls(_inner(layer)), None
    if kind in ("embedded", "single_symbol"):
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        return (QgsEmbeddedSymbolRenderer(symbol) if kind == "embedded" else QgsSingleSymbolRenderer(symbol)), None
    if kind == "no_symbols":
        return QgsNullSymbolRenderer(), None
    renderer = Qgs25DRenderer()
    for key, setter in (("roof_color", renderer.setRoofColor), ("wall_color", renderer.setWallColor)):
        if key in options:
            colour = QColor(options[key].strip())
            if not colour.isValid():
                return None, f"{key}: '{options[key]}' is not a colour QGIS knows."
            setter(colour)
    if "shadow" in options:
        renderer.setShadowEnabled(options["shadow"])
    return renderer, None


@register_tool(
    "set_renderer",
    "Change HOW a layer is drawn with a special renderer: merged_features (touching lines or polygons drawn as one shape, keeping the current look), inverted_polygons (paint everything "
    "OUTSIDE the polygons, keeping the current look), embedded (use the symbol stored in each feature, as in DXF or KML data), no_symbols (draw nothing, so only labels or the selection show), "
    "2_5d (pseudo-3D polygons; options roof_color, wall_color, shadow) or single_symbol (back to one plain symbol). The data is never touched, and the previous style is saved in the layer's "
    "style manager as 'before <kind>' so it can be restored from the layer's Styles menu. The new renderer type is read back in the reply. Stored with the project.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "The vector layer."},
        "kind": {"type": "string", "enum": list(ro.KINDS), "description": "merged_features, inverted_polygons, embedded, no_symbols, 2_5d or single_symbol."},
        "options": {"type": "object", "description": "2_5d only: roof_color, wall_color (a name or #rrggbb), shadow (true / false)."}},
     "required": ["layer_name", "kind"]},
    keywords=["merged features renderer", "merge the features when drawing", "inverted polygons", "invert the polygons", "mask everything outside the polygons", "shade outside the polygons",
              "no symbols", "hide the symbols", "draw nothing", "2.5d", "2.5d style", "pseudo 3d", "embedded symbols", "use the symbols stored in the data", "back to a single symbol"],
)
def set_renderer(layer_name, kind, options=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name)
    if err:
        return err
    word = _geometry_word(layer)
    if word is None:
        return {"error": f"'{layer_name}' has no geometry, so there is nothing to draw differently."}
    problem = ro.check_request(kind, options, word)
    if problem:
        return {"error": problem}
    name = str(kind).strip().lower()
    renderer, why = _make(layer, name, options or {})
    if why:
        return {"error": why}
    before = layer.renderer().type()
    saved = _save_current_style(layer, name)
    layer.setRenderer(renderer)
    layer.triggerRepaint()
    now = layer.renderer()
    out = {"success": True, "layer_name": layer_name, "kind": name, "renderer_type_now": now.type(), "renderer_type_before": before,
           "note": "Only how the layer is drawn changed; the data did not. Stored with the project: save it to keep it."}
    if now.type() in WRAPPERS and now.embeddedRenderer() is not None:
        out["inner_renderer"] = now.embeddedRenderer().type()
    if saved:
        out["previous_style_saved_as"] = saved
        out["restore"] = f"Right-click the layer > Styles > '{saved}' to go back."
    else:
        out["previous_style_note"] = "QGIS would not keep the previous style, so there is no saved copy to go back to."
    return out
