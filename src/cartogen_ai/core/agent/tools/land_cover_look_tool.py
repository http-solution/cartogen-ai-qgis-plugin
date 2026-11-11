"""apply_land_cover_look (PLAN-023 R3-6): draw an environment look on a layer the user already has.

  esa_worldcover       the official ESA WorldCover class colours on a classified raster (one value per class code: 10, 20 ... 100) or on a vector field holding the class code or class name
  change_classes       loss / stable / gain (-1, 0, 1 or the words) in orange, grey and purple
  protected_area_hatch a hatch on a polygon layer that shows where protected areas (or any area layer) are, without a fill that hides what is under it

What it decides is in core/representation/style_looks.py (pure, tested offline); this file only applies it to QGIS objects, so the colours, the names and the hatch cannot drift from the registry. The legend always carries the class name and code, never colour alone. Values that are not a
class of the scheme are drawn grey, labelled 'not in ...' and listed in the reply, never silently recoloured. The QGIS part is written without a local QGIS: tests/test_land_cover_look_live.py reads every setting back from the real objects in CI, so CI's first run is its first execution."""
from ...logger import log_event
from ...representation import style_looks
from .registry import register_tool

try:
    from qgis.core import (Qgis, QgsCategorizedSymbolRenderer, QgsFillSymbol, QgsPalettedRasterRenderer, QgsProject, QgsRasterLayer, QgsRendererCategory,
                           QgsSingleSymbolRenderer, QgsSymbol, QgsVectorLayer)
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QColor
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

SCHEMES = ("esa_worldcover", "change_classes", "protected_area_hatch")
UNMATCHED_COLOUR = "#BDBDBD"
MAX_CLASSES = 60

_SCHEME_TEXT = {"esa_worldcover": ("ESA WorldCover", "the ESA WorldCover legend", style_looks.worldcover_entries, style_looks.worldcover_lookup),
                "change_classes": ("change", "the loss / stable / gain classes", style_looks.change_entries, style_looks.change_lookup)}


def _find_layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _qt_brush(name):
    scoped = getattr(getattr(Qt, "BrushStyle", None), name, None)
    return scoped if scoped is not None else getattr(Qt, name, None)


def plan_classes(values, scheme):
    """Pure. For the raw values found in a layer, the classes to draw: ([{'value', 'label', 'colour', 'matched'}], [unmatched values as text]). Several raw values that are the same class ('10' and 10) each get their own entry (so every
    value on the layer is drawn) with the same colour and label. Classes come out in the scheme's order, unmatched ones last."""
    _name, _phrase, entries_fn, lookup = _SCHEME_TEXT[scheme]
    order = {e["code"]: i for i, e in enumerate(entries_fn())}
    matched, unmatched = [], []
    for value in values:
        entry = lookup(value)
        if entry is None:
            unmatched.append(value)
        else:
            matched.append({"value": value, "label": f"{entry['label']} ({entry['code']})", "colour": entry["colour"], "matched": True, "_rank": order[entry["code"]]})
    matched.sort(key=lambda c: (c["_rank"], str(c["value"])))
    unmatched.sort(key=str)
    tail = [{"value": v, "label": _unmatched_label(v, scheme), "colour": UNMATCHED_COLOUR, "matched": False} for v in unmatched]
    for c in matched:
        c.pop("_rank")
    return matched + tail, [str(v) for v in unmatched]


def _unmatched_label(value, scheme):
    phrase = _SCHEME_TEXT[scheme][1]
    return f"no value (not in {phrase})" if value is None or str(value) in ("", "NULL") else f"{value} (not in {phrase})"


def _apply_vector(layer, scheme, field):
    if field not in [f.name() for f in layer.fields()]:
        return {"error": f"Field '{field}' not found in '{layer.name()}'. Say which field holds the class code or class name."}
    idx = layer.fields().indexOf(field)
    values = list(layer.uniqueValues(idx))
    values = [None if (hasattr(v, "isNull") and v.isNull()) else v for v in values]
    if len(values) > MAX_CLASSES:
        return {"error": f"'{field}' has {len(values)} different values; a land-cover class field has at most {MAX_CLASSES}. Pick the field with the class codes."}
    classes, unmatched = plan_classes(values, scheme)
    if not any(c["matched"] for c in classes):
        return {"error": f"No value of '{field}' is in {_SCHEME_TEXT[scheme][1]}, so nothing was restyled. Values found: {', '.join(unmatched[:10]) or 'none'}."}
    categories = []
    for c in classes:
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(QColor(c["colour"]))
        categories.append(QgsRendererCategory(c["value"], symbol, c["label"]))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))
    layer.triggerRepaint()
    return {"classes": [{"value": str(c["value"]), "label": c["label"], "colour": c["colour"]} for c in classes], "unmatched_values": unmatched}


def _apply_raster(layer, scheme):
    provider = layer.dataProvider()
    present = QgsPalettedRasterRenderer.classDataFromRaster(provider, 1)
    if not present:
        return {"error": "No cell values were found to colour."}
    if len(present) > MAX_CLASSES:
        return {"error": f"The raster has {len(present)} distinct values; a classified land-cover raster has at most {MAX_CLASSES}. Reclassify it first."}
    values = [c.value for c in present]
    classes, unmatched = plan_classes(values, scheme)
    if not any(c["matched"] for c in classes):
        return {"error": f"No cell value is in {_SCHEME_TEXT[scheme][1]}, so nothing was restyled. Values found: {', '.join(unmatched[:10]) or 'none'}."}
    palette = [QgsPalettedRasterRenderer.Class(c["value"], QColor(c["colour"]), c["label"]) for c in classes]
    layer.setRenderer(QgsPalettedRasterRenderer(provider, 1, palette))
    layer.triggerRepaint()
    return {"classes": [{"value": str(c["value"]), "label": c["label"], "colour": c["colour"]} for c in classes], "unmatched_values": unmatched}


def _apply_hatch(layer):
    spec = style_looks.HATCHES["protected_area"]
    symbol = QgsFillSymbol.createSimple({"color": spec["colour"], "outline_color": spec["outline_colour"], "outline_width": str(spec["outline_width_mm"])})
    brush = _qt_brush(spec["brush"])
    if brush is None:
        return {"error": "This QGIS does not offer the diagonal hatch brush."}
    symbol.symbolLayer(0).setBrushStyle(brush)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()
    return {"hatch": dict(spec)}


@register_tool(
    "apply_land_cover_look",
    "Colour a land-cover or change layer the way the standard does. scheme 'esa_worldcover': the official ESA WorldCover class colours on a classified raster, or on a vector field (pass field) holding the class code (10, 20 ... 100) or the class name. "
    "scheme 'change_classes': loss, stable and gain (-1, 0, 1 or those words) in orange, grey and purple, never red and green. scheme 'protected_area_hatch': a diagonal hatch with an outline on a polygon layer, so what is underneath stays visible. "
    "The legend carries each class name and code. Values that are not a class are drawn grey and named in the reply; nothing is silently recoloured. This only changes how the layer is drawn.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "scheme": {"type": "string", "enum": list(SCHEMES), "description": "esa_worldcover, change_classes or protected_area_hatch."},
            "field": {"type": "string", "description": "For a VECTOR layer with esa_worldcover or change_classes: the field holding the class code or class name. Not used for a raster or for protected_area_hatch."},
        },
        "required": ["layer_name", "scheme"],
    },
    keywords=["official land cover colours", "worldcover colours", "esa worldcover palette", "land cover palette", "colour the land cover", "color the land cover", "loss gain stable colours", "loss gain stable colors",
              "change classes colours", "change classes colors", "hatch the protected areas", "protected area hatch", "hatch pattern for protected"],
)
def apply_land_cover_look(layer_name, scheme, field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    scheme = str(scheme or "").strip().lower()
    if scheme not in SCHEMES:
        return {"error": f"Unknown scheme '{scheme}'. Choose one of: {', '.join(SCHEMES)}."}
    layer = _find_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    try:
        if scheme == "protected_area_hatch":
            if not isinstance(layer, QgsVectorLayer) or layer.geometryType() != Qgis.GeometryType.Polygon:
                return {"error": f"'{layer_name}' is not a polygon layer; the protected-area hatch is for polygons."}
            outcome = _apply_hatch(layer)
        elif isinstance(layer, QgsRasterLayer):
            outcome = _apply_raster(layer, scheme)
        elif isinstance(layer, QgsVectorLayer):
            if not field:
                return {"error": f"'{layer_name}' is a vector layer: say which field holds the class code or class name (field)."}
            outcome = _apply_vector(layer, scheme, field)
        else:
            return {"error": f"'{layer_name}' is not a raster or vector layer."}
    except Exception as e:
        log_event("apply_land_cover_look_failed", tag="Styling", error_class=type(e).__name__, error=True)
        return {"error": f"apply_land_cover_look failed: {type(e).__name__}"}
    if "error" in outcome:
        return outcome
    return {"success": True, "layer_name": layer_name, "scheme": scheme, "legend_names_included": scheme != "protected_area_hatch", **outcome}
