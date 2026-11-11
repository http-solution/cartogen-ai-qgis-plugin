"""apply_public_health_look (PLAN-023 R2-5): draw the public-health look on a layer the user already has.

  rate     a single-hue (Blues) quantile rate map on a numeric field, with small numbers drawn as a grey hatch and named in the legend ('Suppressed (n < 5)')
  cluster  a black line with a narrower white line on top, no fill and never red, for the circles of detect_spatial_clusters or any polygon outline
  lisa     the Local Moran classes of calculate_spatial_autocorrelation (HH, HL, LH, LL, not significant, no neighbours)
  hotspot  the hot and cold spot classes of analyze_hotspots_gi_star

What it decides is in core/representation/epi_look.py (pure, tested offline); this file only applies it to QGIS objects, so the classes, colours and legend words cannot drift from the registry. It only changes how
the layer is drawn. The QGIS part is written without a local QGIS: tests/test_public_health_look_live.py reads every setting back from the real renderer in CI."""
from ...logger import log_event
from ...representation import epi_look
from .registry import register_tool

try:
    from qgis.core import (Qgis, QgsCategorizedSymbolRenderer, QgsExpression, QgsFillSymbol, QgsProject, QgsRendererCategory, QgsRuleBasedRenderer, QgsSimpleFillSymbolLayer,
                           QgsSingleSymbolRenderer, QgsSymbol, QgsVectorLayer)
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QColor
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

DEFAULT_FIELDS = {"rate": "value_shown", "lisa": "lisa_class", "hotspot": "gi_class"}


def _find_layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _qt_brush(name):
    scoped = getattr(getattr(Qt, "BrushStyle", None), name, None)
    return scoped if scoped is not None else getattr(Qt, name, None)


def _class_expression(field, c, last):
    column = QgsExpression.quotedColumnRef(field)
    if c["lo"] == c["hi"]:
        return f"{column} = {c['lo']!r}"
    return f"{column} >= {c['lo']!r} AND {column} {'<=' if last else '<'} {c['hi']!r}"


def _apply_rate(layer, field, classes, per, min_cases):
    index = layer.fields().indexOf(field)
    if not layer.fields().at(index).isNumeric():
        return {"error": f"Field '{field}' is not numeric; the rate look colours a number (for example value_shown from calculate_health_rates)."}
    values = [f[field] for f in layer.getFeatures()]
    values = [None if (v is None or (hasattr(v, "isNull") and v.isNull())) else float(v) for v in values]
    try:
        plan = epi_look.rate_classes(values, classes)
    except ValueError as e:
        return {"error": str(e)}
    root = QgsRuleBasedRenderer.Rule(None)
    for i, c in enumerate(plan["classes"]):
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(QColor(c["colour"]))
        root.appendChild(QgsRuleBasedRenderer.Rule(symbol, 0, 0, _class_expression(field, c, i == len(plan["classes"]) - 1), c["label"]))
    suppressed = sum(1 for v in values if v is None)
    brush = _qt_brush(epi_look.SUPPRESSED_HATCH["brush"])
    if brush is None:
        return {"error": "This QGIS does not offer the diagonal hatch brush."}
    hatch = QgsFillSymbol.createSimple({"color": epi_look.SUPPRESSED_HATCH["colour"], "outline_color": epi_look.SUPPRESSED_HATCH["outline_colour"],
                                        "outline_width": str(epi_look.SUPPRESSED_HATCH["outline_width_mm"])})
    hatch.symbolLayer(0).setBrushStyle(brush)
    root.appendChild(QgsRuleBasedRenderer.Rule(hatch, 0, 0, f"{QgsExpression.quotedColumnRef(field)} IS NULL", f"Suppressed (n < {min_cases})"))
    layer.setRenderer(QgsRuleBasedRenderer(root))
    title = epi_look.legend_title(per, min_cases)
    layer.setCustomProperty("cartogen/legend_title", title)
    layer.triggerRepaint()
    return {"field": field, "legend_title": title, "classes": [{"label": c["label"], "colour": c["colour"], "from": c["lo"], "to": c["hi"]} for c in plan["classes"]],
            "classes_dropped": plan["dropped"], "shown": plan["shown"], "suppressed": suppressed, "suppressed_colour": epi_look.SUPPRESSED_COLOUR}


def _apply_cluster(layer):
    strokes = epi_look.CLUSTER_STROKES
    symbol = QgsFillSymbol.createSimple({"style": "no", "outline_color": strokes[0]["colour"], "outline_width": str(strokes[0]["width_mm"])})
    symbol.appendSymbolLayer(QgsSimpleFillSymbolLayer.create({"style": "no", "outline_color": strokes[1]["colour"], "outline_width": str(strokes[1]["width_mm"])}))
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()
    return {"strokes": [dict(s) for s in strokes], "fill": "none"}


def _apply_categories(layer, look, field):
    entries = epi_look.category_entries(look)
    idx = layer.fields().indexOf(field)
    present = {str(v) for v in layer.uniqueValues(idx)}
    if not present & {v for v, _c, _l in entries}:
        return {"error": f"No value of '{field}' is one of the {look} classes ({', '.join(v for v, _c, _l in entries)}), so nothing was restyled. Values found: {', '.join(sorted(present)[:10]) or 'none'}."}
    categories = []
    for value, colour, label in entries:
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(QColor(colour))
        categories.append(QgsRendererCategory(value, symbol, label))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field, categories))
    layer.triggerRepaint()
    unknown = sorted(present - {v for v, _c, _l in entries})
    return {"field": field, "classes": [{"value": v, "label": label, "colour": colour} for v, colour, label in entries], "values_not_in_the_look": unknown}


@register_tool(
    "apply_public_health_look",
    "Draw the public-health look on a layer. look 'rate': a single-hue (blue) quantile map of a rate field (default field value_shown, from calculate_health_rates), with areas whose figure is suppressed for small numbers "
    "drawn as a grey hatch labelled 'Suppressed (n < 5)'; the legend title is 'Rate per 100,000; suppressed where n < 5'. look 'cluster': a black line with a narrower white line on top and no fill, never red, for the "
    "circles from detect_spatial_clusters. look 'lisa': the Local Moran classes (field lisa_class). look 'hotspot': the Getis-Ord hot and cold spot classes (field gi_class). No class is red or green. "
    "This only changes how the layer is drawn; it never changes data.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "look": {"type": "string", "enum": list(epi_look.LOOKS), "description": "rate, cluster, lisa or hotspot."},
            "field": {"type": "string", "description": "The field to draw. Defaults: value_shown for rate, lisa_class for lisa, gi_class for hotspot. Not used for cluster."},
            "classes": {"type": "integer", "description": "For look 'rate': number of quantile classes, 2 to 5 (default 5)."},
            "per": {"type": "number", "description": "For look 'rate': the rate denominator named in the legend (default 100000)."},
            "min_cases": {"type": "integer", "description": "For look 'rate': the small-number threshold named in the legend (default 5); use the same value as calculate_health_rates."},
        },
        "required": ["layer_name", "look"],
    },
    keywords=["rate map colours", "epidemiological map colours", "public health map look", "colour the rates", "color the rates", "hatch the suppressed", "suppressed small numbers", "cluster outline",
              "outline the cluster", "colour the hot spots", "color the hot spots", "colour the lisa", "color the lisa", "hot spot colours", "cold spot colours"],
)
def apply_public_health_look(layer_name, look, field=None, classes=5, per=100000, min_cases=epi_look.DEFAULT_MIN_CASES):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    look = str(look or "").strip().lower()
    if look not in epi_look.LOOKS:
        return {"error": f"Unknown look '{look}'. Choose one of: {', '.join(epi_look.LOOKS)}."}
    layer = _find_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not isinstance(layer, QgsVectorLayer):
        return {"error": f"'{layer_name}' is not a vector layer."}
    if isinstance(min_cases, bool) or not isinstance(min_cases, int) or min_cases < 0:
        return {"error": "min_cases must be a whole number of zero or more."}
    if isinstance(per, bool) or not isinstance(per, (int, float)) or per <= 0:
        return {"error": "per must be a number above zero."}
    try:
        if look == "cluster":
            if layer.geometryType() != Qgis.GeometryType.Polygon:
                return {"error": f"'{layer_name}' is not a polygon layer; the cluster outline is for polygons (the circles from detect_spatial_clusters)."}
            outcome = _apply_cluster(layer)
        else:
            field = (field or DEFAULT_FIELDS[look]).strip()
            if layer.fields().indexOf(field) < 0:
                return {"error": f"Field '{field}' not found in '{layer_name}'. Fields: {', '.join(f.name() for f in layer.fields())}."}
            outcome = _apply_rate(layer, field, classes, per, min_cases) if look == "rate" else _apply_categories(layer, look, field)
    except Exception as e:
        log_event("apply_public_health_look_failed", tag="Styling", error_class=type(e).__name__, error=True)
        return {"error": f"apply_public_health_look failed: {type(e).__name__}"}
    if "error" in outcome:
        return outcome
    return {"success": True, "layer_name": layer_name, "look": look, **outcome}
