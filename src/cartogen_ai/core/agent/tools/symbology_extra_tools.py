"""M4 (completion plan, package F): the symbology the first M4 tools left out.

set_rule_based_labels   labels chosen by filter rules (for example big towns in bold, small ones only when zoomed in)
set_label_callout       callout lines from labels to their features, and a mask that clears what is behind the text
set_point_marker        an SVG file or one font character as the point marker
set_layer_diagram       pie or bar diagrams drawn from numeric fields
set_raster_relief       a raster drawn as hillshade or as contour lines
save_symbol_to_library / list_saved_symbols / apply_saved_symbol   a personal symbol library (QGIS's own style database)

Every tool changes how a layer is DRAWN and never touches data. Filters go through the expression screen; SVG markers are local files only
(a URL is refused). Written without a QGIS install: tests/test_symbology_extra_tools_live.py reads each setting back from real objects (CI's
first run is its first execution), and the API names that moved between QGIS releases are looked up defensively."""
import os

from ...validators.expression_screen import screen_expression
from ._qgis_enum_compat import resolve_qgis_enum
from .registry import register_tool
from .symbology_extra_options import (check_callout, check_diagram, check_marker_source, check_relief, check_rules, check_svg_file,
                                      symbol_name)

try:
    from qgis.core import (Qgis, QgsApplication, QgsExpression, QgsFontMarkerSymbolLayer, QgsHillshadeRenderer, QgsPalLayerSettings,
                           QgsRasterLayer, QgsRuleBasedLabeling, QgsSimpleLineCallout, QgsSingleSymbolRenderer, QgsStyle,
                           QgsSvgMarkerSymbolLayer, QgsTextFormat, QgsVectorLayer)
    from qgis.PyQt.QtCore import QSizeF
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_PALETTE = ("#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f")


def _layer(name, kind=None):
    from .symbology_tools import _find_layer
    layer = _find_layer(name)
    if layer is None:
        return None, {"error": f"Layer '{name}' not found"}
    if kind is not None and not isinstance(layer, kind):
        return None, {"error": f"'{name}' is not a {'vector' if kind is QgsVectorLayer else 'raster'} layer."}
    return layer, None


def _colour(text):
    from .symbology_tools import _colour as colour
    return colour(text)


@register_tool(
    "set_rule_based_labels",
    "Label a vector layer with RULES instead of one style: each rule has a field to show, an optional filter (a QGIS expression such as "
    "\"population\" > 10000), a font size and colour, and optional scales (min_scale = zoomed-out limit as a denominator, max_scale = "
    "zoomed-in limit). Up to 20 rules. This replaces the layer's current labels.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"},
        "rules": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string"}, "filter": {"type": "string"}, "font_size": {"type": "number"}, "font_color": {"type": "string"},
            "min_scale": {"type": "number"}, "max_scale": {"type": "number"}, "description": {"type": "string"}}, "required": ["field"]}}},
     "required": ["layer_name", "rules"]})
def set_rule_based_labels(layer_name, rules):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    clean, problem = check_rules(rules)
    if problem:
        return {"error": problem}
    layer, err = _layer(layer_name, QgsVectorLayer)
    if err:
        return err
    names = layer.fields().names()
    root = QgsRuleBasedLabeling.Rule(QgsPalLayerSettings())
    for i, rule in enumerate(clean, start=1):
        if rule["field"] not in names:
            return {"error": f"Rule {i}: field '{rule['field']}' not found. The layer has: {', '.join(names)}."}
        if rule["filter"]:
            blocked = screen_expression(rule["filter"])
            if blocked:
                return {"error": f"Rule {i}: {blocked}"}
            parsed = QgsExpression(rule["filter"])
            if parsed.hasParserError():
                return {"error": f"Rule {i}: invalid filter: {parsed.parserErrorString()}"}
        settings = QgsPalLayerSettings()
        settings.fieldName = rule["field"]
        settings.isExpression = False
        fmt = QgsTextFormat()
        fmt.setSize(rule.get("font_size", 10))
        if "font_color" in rule:
            colour = _colour(rule["font_color"])
            if colour is None:
                return {"error": f"Rule {i}: invalid font_color '{rule['font_color']}'."}
            fmt.setColor(colour)
        settings.setFormat(fmt)
        root.appendChild(QgsRuleBasedLabeling.Rule(settings, rule.get("max_scale", 0), rule.get("min_scale", 0), rule["filter"],
                                                    rule["description"] or rule["field"]))
    layer.setLabeling(QgsRuleBasedLabeling(root))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()
    return {"success": True, "layer_name": layer_name, "rules": len(clean), "labeling": "rule-based"}


@register_tool(
    "set_label_callout",
    "Add or change callouts (lines from a label to its feature) and a text mask (a clear halo that hides what is behind the text) on a "
    "layer that already has simple labels (apply_labels). enabled switches callouts on or off; style is simple or manhattan; color and "
    "width_mm style the line; mask and mask_size_mm control the mask.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"}, "enabled": {"type": "boolean"}, "style": {"type": "string", "description": "simple or manhattan"},
        "color": {"type": "string"}, "width_mm": {"type": "number"}, "mask": {"type": "boolean"}, "mask_size_mm": {"type": "number"}},
     "required": ["layer_name"]})
def set_label_callout(layer_name, enabled=None, style=None, color=None, width_mm=None, mask=None, mask_size_mm=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = check_callout(enabled, style, color, width_mm, mask, mask_size_mm)
    if problem:
        return {"error": problem}
    layer, err = _layer(layer_name, QgsVectorLayer)
    if err:
        return err
    import qgis.core as core
    from .symbology_tools import _label_settings
    labeling, settings, why = _label_settings(layer)
    if why:
        return {"error": why}
    colour = None
    if "color" in options:
        colour = _colour(options["color"])
        if colour is None:
            return {"error": f"Invalid color: {options['color']}."}
    try:
        if {"enabled", "style", "color", "width_mm"} & set(options):
            existing = settings.callout()
            if existing is None or "style" in options:
                callout_class = QgsSimpleLineCallout
                if options.get("style") == "manhattan":
                    callout_class = getattr(core, "QgsManhattanLineCallout", None)
                    if callout_class is None:
                        return {"error": "This QGIS has no manhattan callout."}
                callout = callout_class()
                callout.setEnabled(options.get("enabled", True))
                replace = True
            else:
                callout = existing
                if "enabled" in options:
                    callout.setEnabled(options["enabled"])
                replace = False
            # The callout owns its line symbol: change it IN PLACE. Passing it back through setLineSymbol() (or an existing callout back
            # through settings.setCallout()) hands QGIS an object it already owns, so it deletes it and then uses it -- that crashed the whole
            # QGIS process (SIGSEGV) in the first live run (CI job 116925382425, test_callout_and_mask).
            line = callout.lineSymbol()
            if line is not None:
                if colour is not None:
                    line.setColor(colour)
                if "width_mm" in options:
                    line.setWidth(options["width_mm"])
            if replace:
                settings.setCallout(callout)
        if "mask" in options or "mask_size_mm" in options:
            fmt = settings.format()
            mask_settings = fmt.mask()
            mask_settings.setEnabled(options.get("mask", True))
            if "mask_size_mm" in options:
                mask_settings.setSize(options["mask_size_mm"])
            fmt.setMask(mask_settings)
            settings.setFormat(fmt)
        labeling.setSettings(settings)
        layer.setLabeling(labeling)
        layer.triggerRepaint()
    except Exception as e:
        return {"error": f"set_label_callout failed: {e}"}
    return {"success": True, "layer_name": layer_name, "changed": dict(options)}


def _resolve_svg(path):
    """The SVG as a file path: the given path if it exists, else the same name under one of QGIS's SVG folders, else the input."""
    if os.path.isfile(path):
        return path
    if not os.path.isabs(path):
        for folder in QgsApplication.svgPaths():
            candidate = os.path.join(folder, path)
            if os.path.isfile(candidate):
                return candidate
    return path


@register_tool(
    "set_point_marker",
    "Use an SVG picture or a single font character as the marker of a POINT layer. kind=svg needs svg_path (a local .svg file, or a name "
    "from QGIS's own SVG library such as arrows/Arrow_01.svg; URLs are refused); kind=font needs font_family and character. size_mm and "
    "color are optional. The layer must use a single symbol.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"}, "kind": {"type": "string", "description": "svg or font"}, "svg_path": {"type": "string"},
        "font_family": {"type": "string"}, "character": {"type": "string"}, "size_mm": {"type": "number"}, "color": {"type": "string"}},
     "required": ["layer_name", "kind"]})
def set_point_marker(layer_name, kind, svg_path=None, font_family=None, character=None, size_mm=None, color=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = check_marker_source(kind, svg_path, font_family, character, size_mm, color)
    if problem:
        return {"error": problem}
    layer, err = _layer(layer_name, QgsVectorLayer)
    if err:
        return err
    if layer.geometryType() != Qgis.GeometryType.Point:
        return {"error": f"'{layer_name}' is not a point layer."}
    renderer = layer.renderer()
    if not isinstance(renderer, QgsSingleSymbolRenderer):
        return {"error": "Only a layer with a single symbol can take a picture marker; use set_layer_symbol or apply a single style first."}
    colour = None
    if "color" in options:
        colour = _colour(options["color"])
        if colour is None:
            return {"error": f"Invalid color: {options['color']}."}
    size = options.get("size_mm", 6.0)
    if options["kind"] == "svg":
        path = _resolve_svg(options["svg_path"])
        problem = check_svg_file(path)
        if problem:
            return {"error": problem}
        symbol_layer = QgsSvgMarkerSymbolLayer(path, size)
        if colour is not None:
            symbol_layer.setFillColor(colour)
    else:
        symbol_layer = QgsFontMarkerSymbolLayer(options["font_family"], options["character"], size)
        if colour is not None:
            symbol_layer.setColor(colour)
    symbol = renderer.symbol()
    if not symbol.changeSymbolLayer(0, symbol_layer):
        return {"error": "QGIS refused to replace the marker."}
    layer.triggerRepaint()
    out = {"success": True, "layer_name": layer_name, "kind": options["kind"], "size_mm": size}
    if options["kind"] == "svg":
        out["svg_path"] = path
    return out


@register_tool(
    "set_layer_diagram",
    "Draw a pie or bar diagram on every feature of a vector layer from numeric fields (kind: pie, bar or histogram; fields: 1 to 8 numeric "
    "field names; size_mm; optional colors, one per field). clear=true removes the diagrams.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"}, "kind": {"type": "string"}, "fields": {"type": "array", "items": {"type": "string"}},
        "size_mm": {"type": "number"}, "colors": {"type": "array", "items": {"type": "string"}}, "clear": {"type": "boolean"}},
     "required": ["layer_name"]})
def set_layer_diagram(layer_name, kind=None, fields=None, size_mm=None, colors=None, clear=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = check_diagram(kind, fields, size_mm, colors, clear)
    if problem:
        return {"error": problem}
    layer, err = _layer(layer_name, QgsVectorLayer)
    if err:
        return err
    if options.get("clear"):
        layer.setDiagramRenderer(None)
        layer.triggerRepaint()
        return {"success": True, "layer_name": layer_name, "diagrams": "removed"}
    import qgis.core as core
    for field in options["fields"]:
        index = layer.fields().indexOf(field)
        if index < 0:
            return {"error": f"Field '{field}' not found. The layer has: {', '.join(layer.fields().names())}."}
        if not layer.fields().at(index).isNumeric():
            return {"error": f"Field '{field}' is not numeric, so it cannot be drawn in a diagram."}
    qcolors = []
    for i in range(len(options["fields"])):
        text = options["colors"][i] if "colors" in options else _PALETTE[i % len(_PALETTE)]
        colour = _colour(text)
        if colour is None:
            return {"error": f"Invalid colour '{text}'."}
        qcolors.append(colour)
    diagram_class = getattr(core, "QgsPieDiagram" if options["kind"] == "pie" else "QgsHistogramDiagram", None)
    if diagram_class is None:
        return {"error": "This QGIS has no diagram of that kind."}
    settings = core.QgsDiagramSettings()
    settings.categoryAttributes = list(options["fields"])
    settings.categoryLabels = list(options["fields"])
    settings.categoryColors = qcolors
    settings.size = QSizeF(options["size_mm"], options["size_mm"])
    unit = resolve_qgis_enum(Qgis, "RenderUnit", "Millimeters")
    if unit is not None:
        settings.sizeType = unit
    settings.enabled = True
    renderer = core.QgsSingleCategoryDiagramRenderer()
    renderer.setDiagram(diagram_class())
    renderer.setDiagramSettings(settings)
    layer.setDiagramRenderer(renderer)
    layer_settings = core.QgsDiagramLayerSettings()
    layer_settings.setShowAllDiagrams(True)
    layer.setDiagramLayerSettings(layer_settings)
    layer.triggerRepaint()
    return {"success": True, "layer_name": layer_name, "kind": options["kind"], "fields": options["fields"], "size_mm": options["size_mm"]}


@register_tool(
    "set_raster_relief",
    "Draw a raster (for example a DEM) as a hillshade (style=hillshade; azimuth 0-360, altitude 0-90, z_factor) or as contour lines "
    "(style=contour; interval and optional index_interval, in the raster's units). band defaults to 1. This changes how the raster is "
    "drawn, not its data; for a hillshade FILE use the hillshade analysis tool.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"}, "style": {"type": "string", "description": "hillshade or contour"}, "azimuth": {"type": "number"},
        "altitude": {"type": "number"}, "z_factor": {"type": "number"}, "interval": {"type": "number"}, "index_interval": {"type": "number"},
        "band": {"type": "integer"}}, "required": ["layer_name", "style"]})
def set_raster_relief(layer_name, style, azimuth=None, altitude=None, z_factor=None, interval=None, index_interval=None, band=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = check_relief(style, azimuth, altitude, z_factor, interval, index_interval, band)
    if problem:
        return {"error": problem}
    layer, err = _layer(layer_name, QgsRasterLayer)
    if err:
        return err
    band_number = options.get("band", 1)
    if band_number > layer.bandCount():
        return {"error": f"The raster has {layer.bandCount()} band(s); band {band_number} does not exist."}
    provider = layer.dataProvider()
    if options["style"] == "hillshade":
        renderer = QgsHillshadeRenderer(provider, band_number, options.get("azimuth", 315.0), options.get("altitude", 45.0))
        if "z_factor" in options:
            renderer.setZFactor(options["z_factor"])
    else:
        import qgis.core as core
        contour = getattr(core, "QgsRasterContourRenderer", None)
        if contour is None:
            return {"error": "This QGIS has no contour renderer for rasters."}
        if "interval" not in options:
            return {"error": "A contour style needs an interval, for example interval=10."}
        renderer = contour(provider)
        renderer.setInputBand(band_number)
        renderer.setContourInterval(options["interval"])
        if "index_interval" in options:
            renderer.setContourIndexInterval(options["index_interval"])
    layer.setRenderer(renderer)
    layer.triggerRepaint()
    return {"success": True, "layer_name": layer_name, "style": options["style"], "band": band_number}


def _symbol_of(layer):
    renderer = layer.renderer() if isinstance(layer, QgsVectorLayer) else None
    return renderer.symbol() if isinstance(renderer, QgsSingleSymbolRenderer) else None


@register_tool(
    "save_symbol_to_library",
    "Save a vector layer's (single) symbol into your personal QGIS symbol library under a name, optionally with tags, so it can be reused "
    "on other layers and in other projects. An existing symbol with the same name is only replaced after confirmation.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "name": {"type": "string"},
                                      "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["layer_name", "name"]})
def save_symbol_to_library(layer_name, name, tags=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    clean, problem = symbol_name(name)
    if problem:
        return {"error": problem}
    layer, err = _layer(layer_name, QgsVectorLayer)
    if err:
        return err
    symbol = _symbol_of(layer)
    if symbol is None:
        return {"error": "Only a layer with a single symbol can be saved to the library."}
    style = QgsStyle.defaultStyle()
    if clean in style.symbolNames() and not confirmed:
        from .attribute_edit_tools import preview
        return preview("save_symbol_to_library", {"layer_name": layer_name, "name": name, "tags": tags},
                       f"Replace the symbol '{clean}' in your symbol library with the symbol of '{layer_name}'.", "QgsStyle.addSymbol(name, symbol)")
    if not style.addSymbol(clean, symbol.clone(), True):
        return {"error": "QGIS could not save the symbol to the library."}
    tag_list = [str(t).strip() for t in (tags or []) if str(t).strip()][:10]
    if tag_list:
        entity = resolve_qgis_enum(QgsStyle, "StyleEntity", "SymbolEntity")
        if entity is not None:
            style.tagSymbol(entity, clean, tag_list)
    return {"success": True, "name": clean, "tags": tag_list}


@register_tool(
    "list_saved_symbols",
    "List the symbols in your personal QGIS symbol library (name and kind: marker, line or fill).",
    {"type": "object", "properties": {}, "required": []})
def list_saved_symbols():
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    style = QgsStyle.defaultStyle()
    rows = []
    for symbol_name_ in style.symbolNames():
        symbol = style.symbol(symbol_name_)
        rows.append({"name": symbol_name_, "kind": str(symbol.type()).split(".")[-1] if symbol is not None else "unknown"})
    return {"success": True, "count": len(rows), "symbols": rows[:200]}


@register_tool(
    "apply_saved_symbol",
    "Give a vector layer a symbol from your personal symbol library by name. The symbol kind must fit the layer (marker for points, line for "
    "lines, fill for polygons). A layer that uses categories or graduated colours is only switched to the single symbol after confirmation.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "name": {"type": "string"}}, "required": ["layer_name", "name"]})
def apply_saved_symbol(layer_name, name, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer, err = _layer(layer_name, QgsVectorLayer)
    if err:
        return err
    style = QgsStyle.defaultStyle()
    if name not in style.symbolNames():
        return {"error": f"No symbol called '{name}' in your library. Saved: {', '.join(style.symbolNames()[:20]) or 'none'}."}
    symbol = style.symbol(name)
    kind = str(symbol.type()).split(".")[-1].lower()
    wanted = {Qgis.GeometryType.Point: "marker", Qgis.GeometryType.Line: "line", Qgis.GeometryType.Polygon: "fill"}.get(layer.geometryType())
    if wanted is None or kind != wanted:
        return {"error": f"'{name}' is a {kind} symbol, but '{layer_name}' needs a {wanted or 'different'} symbol."}
    if not isinstance(layer.renderer(), QgsSingleSymbolRenderer) and not confirmed:
        from .attribute_edit_tools import preview
        return preview("apply_saved_symbol", {"layer_name": layer_name, "name": name},
                       f"'{layer_name}' is drawn with {layer.renderer().type()} styling; applying '{name}' replaces it with one symbol.",
                       "layer.setRenderer(QgsSingleSymbolRenderer(symbol))")
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()
    return {"success": True, "layer_name": layer_name, "symbol": name}

