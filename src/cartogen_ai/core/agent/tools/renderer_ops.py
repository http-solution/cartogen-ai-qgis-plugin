"""Special renderers (PLAN-023 R10-3): the request check, pure Python (no QGIS, no numpy).

set_renderer (renderer_tool.py) swaps the renderer of a layer through QGIS (QgsMergedFeatureRenderer, QgsInvertedPolygonRenderer, QgsEmbeddedSymbolRenderer, QgsNullSymbolRenderer,
Qgs25DRenderer, QgsSingleSymbolRenderer); what can be checked offline is here.

Kinds and where they apply:
  merged_features    lines and polygons: draws touching features as one shape (keeps the layer's current look as the inner renderer)
  inverted_polygons  polygons: paints everything OUTSIDE the polygons (keeps the current look as the inner renderer)
  embedded           any layer: draws each feature with the symbol stored in the data itself (as in DXF or KML files); features without one get the default symbol
  no_symbols         any layer: draws nothing (useful when only labels or a selection should show)
  2_5d               polygons: a pseudo-3D look with roof, walls and a shadow; options roof_color, wall_color, shadow (true / false)
  single_symbol      any layer: back to one default symbol (the way out of the others)
Known answers (the tests): inverted_polygons on a line layer is refused with the reason, 2_5d accepts roof_color and wall_color and nothing else, an unknown kind is refused."""
from .display_rules import _COLOR

KINDS = ("merged_features", "inverted_polygons", "embedded", "no_symbols", "2_5d", "single_symbol")
APPLIES_TO = {"merged_features": ("line", "polygon"), "inverted_polygons": ("polygon",), "2_5d": ("polygon",),
              "embedded": ("point", "line", "polygon"), "no_symbols": ("point", "line", "polygon"), "single_symbol": ("point", "line", "polygon")}
OPTIONS = {"2_5d": ("roof_color", "wall_color", "shadow")}
RENDERER_TYPES = {"merged_features": "mergedFeatureRenderer", "inverted_polygons": "invertedPolygonRenderer", "embedded": "embeddedSymbol", "no_symbols": "nullSymbol",
                  "2_5d": "25dRenderer", "single_symbol": "singleSymbol"}


def check_request(kind, options=None, geometry_kind="polygon"):
    """Error text for a set_renderer request that cannot be run, else None. `geometry_kind` is 'point', 'line' or 'polygon'. Pure."""
    name = str(kind or "").strip().lower()
    if name not in KINDS:
        return f"kind must be one of {', '.join(KINDS)}."
    if geometry_kind not in APPLIES_TO[name]:
        where = " and ".join(APPLIES_TO[name])
        return f"{name} is for {where} layers; this is a {geometry_kind} layer."
    if options is not None and not isinstance(options, dict):
        return "options must be an object."
    allowed = OPTIONS.get(name, ())
    for key, value in (options or {}).items():
        if key not in allowed:
            return f"{name} takes {'these options: ' + ', '.join(allowed) if allowed else 'no options'}; '{key}' is not one of them."
        if key == "shadow" and not isinstance(value, bool):
            return "shadow must be true or false."
        if key != "shadow" and (not isinstance(value, str) or not _COLOR.match(value.strip())):
            return f"{key}: a colour is a name (red) or a hex code (#ff0000)."
    return None
