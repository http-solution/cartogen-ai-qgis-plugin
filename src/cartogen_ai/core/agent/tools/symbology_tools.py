"""M4 (roadmap 2026-10-14): symbol, label and raster-display controls that the older colour/opacity tools did not have.

set_layer_symbol   outline colour and width, line pattern, marker shape and size, fill pattern (hatching), opacity
set_label_style    font colour, size, bold/italic, halo, placement, the scales at which labels show, labels on/off
set_raster_style   one colour per distinct cell value, resampling, opacity, no-data values

All three change how an existing layer is DRAWN; none touches data. Colours accept the everyday words resolve_colour() knows. The QGIS part
is written without a QGIS install: tests/test_symbology_tools_live.py reads each setting back from the real objects (CI's first run is its
first execution). The enum for each option key is looked up in the scoped Qt6 form first (see _qgis_enum_compat.py)."""
import contextlib

from ._qgis_enum_compat import resolve_qgis_enum
from .plain_colour import resolve_colour
from .registry import register_tool
from .symbology_options import (LABEL_PLACEMENTS, LINE_STYLES, FILL_STYLES, MARKER_SHAPES, MAX_UNIQUE_VALUES, validate_label_options,
                                validate_raster_options, validate_symbol_options)

try:
    from qgis.core import (Qgis, QgsPalLayerSettings, QgsPalettedRasterRenderer, QgsProject, QgsRasterLayer, QgsRasterRange,
                           QgsRenderContext, QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer, QgsSimpleMarkerSymbolLayer,
                           QgsSingleSymbolRenderer, QgsUnitTypes, QgsVectorLayer)
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QColor
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _find_layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _colour(text):
    """QColor for a hex code or plain colour phrase, else None."""
    color = QColor(resolve_colour(text) or text)
    return color if color.isValid() else None


def _qt_enum(group, name):
    """Qt.PenStyle.DashLine / Qt.BrushStyle.BDiagPattern in the scoped form, falling back to the flat one."""
    scoped = getattr(getattr(Qt, group, None), name, None)
    return scoped if scoped is not None else getattr(Qt, name, None)


def _marker_shape(key):
    name = MARKER_SHAPES[key]
    for owner in (getattr(Qgis, "MarkerShape", None), getattr(QgsSimpleMarkerSymbolLayer, "Shape", None), QgsSimpleMarkerSymbolLayer):
        value = getattr(owner, name, None) if owner is not None else None
        if value is not None:
            return value
    return None


def _symbols_of(layer):
    """(symbols, is_single) for a vector layer's renderer, or (None, message)."""
    renderer = layer.renderer()
    if renderer is None:
        return None, "The layer has no renderer to change."
    if isinstance(renderer, QgsSingleSymbolRenderer):
        return [renderer.symbol()], True
    getter = getattr(renderer, "symbols", None)
    if getter is None:
        return None, f"The layer's '{renderer.type()}' renderer has no symbols to change (use apply_categorized_style or similar first)."
    return list(getter(QgsRenderContext())), False


def _apply_fill(sl, options, colours, pen, brush):
    if "fill_color" in colours:
        sl.setFillColor(colours["fill_color"])
    if "outline_color" in colours:
        sl.setStrokeColor(colours["outline_color"])
    if "outline_width_mm" in options:
        sl.setStrokeWidth(options["outline_width_mm"])
    if pen is not None:
        sl.setStrokeStyle(pen)
    if brush is not None:
        sl.setBrushStyle(brush)


def _apply_line(sl, options, colours, pen):
    if "outline_color" in colours or "fill_color" in colours:
        sl.setColor(colours.get("outline_color") or colours["fill_color"])
    if "outline_width_mm" in options:
        sl.setWidth(options["outline_width_mm"])
    if pen is not None:
        sl.setPenStyle(pen)


def _apply_marker(sl, options, colours, pen, shape):
    if "fill_color" in colours:
        sl.setColor(colours["fill_color"])
    if "outline_color" in colours:
        sl.setStrokeColor(colours["outline_color"])
    if "outline_width_mm" in options:
        sl.setStrokeWidth(options["outline_width_mm"])
    if pen is not None:
        sl.setStrokeStyle(pen)
    if shape is not None:
        sl.setShape(shape)
    if "marker_size_mm" in options:
        sl.setSize(options["marker_size_mm"])


def _apply_to_symbols(symbols, options, colours, pen, brush, shape):
    """({"fill": n, "line": n, "marker": n}, set of unsupported symbol-layer types)."""
    changed = {"fill": 0, "line": 0, "marker": 0}
    skipped = set()
    for symbol in symbols:
        for i in range(symbol.symbolLayerCount()):
            sl = symbol.symbolLayer(i)
            if isinstance(sl, QgsSimpleFillSymbolLayer):
                _apply_fill(sl, options, colours, pen, brush)
                changed["fill"] += 1
            elif isinstance(sl, QgsSimpleLineSymbolLayer):
                _apply_line(sl, options, colours, pen)
                changed["line"] += 1
            elif isinstance(sl, QgsSimpleMarkerSymbolLayer):
                _apply_marker(sl, options, colours, pen, shape)
                changed["marker"] += 1
            else:
                skipped.add(sl.layerType())
    return changed, skipped


@register_tool(
    "set_layer_symbol",
    "Change how a vector layer's symbols are drawn beyond colour: outline colour and width, line pattern (solid, dashed, dotted, dash_dot), "
    "marker shape (circle, square, diamond, triangle, star, cross, x, pentagon, hexagon, heart, arrow) and size, fill pattern (solid, none, "
    "hatch_forward, hatch_backward, horizontal, vertical, cross, diagonal_cross, dots_dense, dots_sparse) and opacity. Give only what should "
    "change; everything else stays. Colours can be hex or plain words ('dark red'). On a categorized, graduated or rule-based layer it keeps "
    "the classification colours and sizes: fill_color and marker_size_mm are refused there (use the style tool that made the classes). "
    "Only simple symbols are changed; an SVG or font marker is reported, not overwritten.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"},
        "fill_color": {"type": "string"}, "outline_color": {"type": "string"},
        "outline_width_mm": {"type": "number", "description": "0 to 20; 0.26 is a thin line, 1 a thick one."},
        "opacity_percent": {"type": "number", "description": "0 to 100 for the whole layer."},
        "marker_shape": {"type": "string"}, "marker_size_mm": {"type": "number", "description": "0.1 to 100."},
        "line_style": {"type": "string", "description": "Pattern of a line or of a polygon outline."},
        "fill_style": {"type": "string", "description": "Pattern of a polygon fill, for example hatch_forward."},
    }, "required": ["layer_name"]},
)
def set_layer_symbol(layer_name, fill_color=None, outline_color=None, outline_width_mm=None, opacity_percent=None, marker_shape=None,
                     marker_size_mm=None, line_style=None, fill_style=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = validate_symbol_options(fill_color, outline_color, outline_width_mm, opacity_percent, marker_shape, marker_size_mm,
                                               line_style, fill_style)
    if problem:
        return {"error": problem}
    layer = _find_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not isinstance(layer, QgsVectorLayer):
        return {"error": f"'{layer_name}' is not a vector layer. Use set_raster_style for rasters."}
    colours = {}
    for key in ("fill_color", "outline_color"):
        if key in options:
            colours[key] = _colour(options[key])
            if colours[key] is None:
                return {"error": f"Invalid {key}: {options[key]}. Use a hex code or a plain colour such as 'dark red'."}
    symbols, single = _symbols_of(layer)
    if symbols is None:
        return {"error": single}
    if not single:
        for key in ("fill_color", "marker_size_mm"):
            if key in options:
                return {"error": f"{key} would overwrite the classification of this layer's {layer.renderer().type()} renderer; it is "
                                 "refused here. Restyle the classes with the tool that made them."}
    pen = _qt_enum("PenStyle", LINE_STYLES[options["line_style"]]) if "line_style" in options else None
    brush = _qt_enum("BrushStyle", FILL_STYLES[options["fill_style"]]) if "fill_style" in options else None
    shape = _marker_shape(options["marker_shape"]) if "marker_shape" in options else None
    if "marker_shape" in options and shape is None:
        return {"error": f"This QGIS does not offer the '{options['marker_shape']}' marker shape."}
    try:
        changed, skipped = _apply_to_symbols(symbols, options, colours, pen, brush, shape)
        total = sum(changed.values())
        if "opacity_percent" in options:
            layer.setOpacity(options["opacity_percent"] / 100.0)
        if total == 0 and "opacity_percent" not in options:
            return {"error": "No simple symbol layer to change" + (f"; the layer uses {sorted(skipped)}." if skipped else "."),
                    "unsupported_symbol_layers": sorted(skipped)}
        layer.triggerRepaint()
        with contextlib.suppress(Exception):
            from qgis.utils import iface
            if iface is not None:
                iface.layerTreeView().refreshLayerSymbology(layer.id())
    except Exception as e:
        return {"error": f"set_layer_symbol failed: {e}"}
    result = {"success": True, "layer_name": layer_name, "changed": dict(options), "symbol_layers_changed": total}
    if skipped:
        result["not_changed"] = f"Symbol layers of type {sorted(skipped)} are not simple symbols and were left as they are."
    return result


def _label_settings(layer):
    labeling = layer.labeling()
    if labeling is None:
        return None, None, "The layer has no labels yet. Add them with apply_labels first, then style them here."
    if labeling.type() != "simple":
        return None, None, f"This layer uses '{labeling.type()}' labeling; only simple labels are styled here."
    return labeling, labeling.settings(), None


def _apply_text_format(fmt, options, colours):
    if "font_color" in colours:
        fmt.setColor(colours["font_color"])
    if "font_size" in options:
        fmt.setSize(options["font_size"])
    if "bold" in options or "italic" in options:
        font = fmt.font()
        if "bold" in options:
            font.setBold(options["bold"])
        if "italic" in options:
            font.setItalic(options["italic"])
        fmt.setFont(font)
    if any(k in options for k in ("halo", "halo_color", "halo_size_mm")):
        buffer = fmt.buffer()
        if "halo" in options:
            buffer.setEnabled(options["halo"])
        else:
            buffer.setEnabled(True)
        if "halo_color" in colours:
            buffer.setColor(colours["halo_color"])
        if "halo_size_mm" in options:
            buffer.setSize(options["halo_size_mm"])
            buffer.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMillimeters)
        fmt.setBuffer(buffer)


@register_tool(
    "set_label_style",
    "Style the labels already on a vector layer (add them first with apply_labels): font colour and size, bold, italic, the halo around "
    "the text (on/off, colour, size), placement (around_point, over_point, horizontal, free, curved, parallel), the scales between which "
    "labels show (visible_zoomed_out_to = the smallest scale such as 250000 for 1:250,000, visible_zoomed_in_to = the largest such as 5000), "
    "and show_labels to switch labels on or off. Give only what should change. Rule-based labeling is reported, not changed.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"},
        "font_color": {"type": "string"}, "font_size": {"type": "number", "description": "Points, 1 to 120."},
        "bold": {"type": "boolean"}, "italic": {"type": "boolean"},
        "halo": {"type": "boolean", "description": "Draw a halo (buffer) round the text."},
        "halo_color": {"type": "string"}, "halo_size_mm": {"type": "number", "description": "0 to 10."},
        "placement": {"type": "string"},
        "visible_zoomed_out_to": {"type": "number", "description": "Scale denominator, e.g. 250000."},
        "visible_zoomed_in_to": {"type": "number", "description": "Scale denominator, e.g. 5000."},
        "show_labels": {"type": "boolean"},
    }, "required": ["layer_name"]},
)
def set_label_style(layer_name, font_color=None, font_size=None, bold=None, italic=None, halo=None, halo_color=None, halo_size_mm=None,
                    placement=None, visible_zoomed_out_to=None, visible_zoomed_in_to=None, show_labels=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = validate_label_options(font_color, font_size, bold, italic, halo, halo_color, halo_size_mm, placement,
                                              visible_zoomed_out_to, visible_zoomed_in_to, show_labels)
    if problem:
        return {"error": problem}
    layer = _find_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not isinstance(layer, QgsVectorLayer):
        return {"error": f"'{layer_name}' is not a vector layer."}
    colours = {}
    for key in ("font_color", "halo_color"):
        if key in options:
            colours[key] = _colour(options[key])
            if colours[key] is None:
                return {"error": f"Invalid {key}: {options[key]}. Use a hex code or a plain colour such as 'dark red'."}
    only_toggle = set(options) == {"show_labels"}
    labeling, settings, why = _label_settings(layer)
    if why and not (only_toggle and layer.labeling() is not None):
        return {"error": why}
    try:
        if only_toggle:
            layer.setLabelsEnabled(options["show_labels"])
            layer.triggerRepaint()
            return {"success": True, "layer_name": layer_name, "changed": {"show_labels": options["show_labels"]}}
        fmt = settings.format()
        _apply_text_format(fmt, options, colours)
        settings.setFormat(fmt)
        if "placement" in options:
            enum = resolve_qgis_enum(QgsPalLayerSettings, "Placement", LABEL_PLACEMENTS[options["placement"]])
            if enum is None:
                return {"error": f"This QGIS does not offer the '{options['placement']}' placement."}
            settings.placement = enum
        if "visible_zoomed_out_to" in options or "visible_zoomed_in_to" in options:
            settings.scaleVisibility = True
            if "visible_zoomed_out_to" in options:
                settings.minimumScale = options["visible_zoomed_out_to"]
            if "visible_zoomed_in_to" in options:
                settings.maximumScale = options["visible_zoomed_in_to"]
        labeling.setSettings(settings)
        layer.setLabeling(labeling)
        if "show_labels" in options:
            layer.setLabelsEnabled(options["show_labels"])
        layer.triggerRepaint()
    except Exception as e:
        return {"error": f"set_label_style failed: {e}"}
    return {"success": True, "layer_name": layer_name, "changed": dict(options)}


@register_tool(
    "set_raster_style",
    "Change how a raster layer is displayed: mode='unique_values' gives one colour per distinct cell value (for land cover, classes, zones; "
    "refused above 256 distinct values), resampling (nearest keeps blocky cells, bilinear or cubic smooth them), opacity_percent, and no-data: "
    "nodata_min/nodata_max make cells in that range transparent (both ends are INCLUDED: for 'below 0' give nodata_max just under 0, such as -0.000001), clear_nodata=true restores the file's own no-data. Give only what should "
    "change. Display only; the cell values are not changed. For a continuous colour ramp use apply_raster_stretch.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"},
        "mode": {"type": "string", "description": "'unique_values'"},
        "resampling": {"type": "string", "description": "nearest, bilinear or cubic"},
        "opacity_percent": {"type": "number"},
        "nodata_min": {"type": "number"}, "nodata_max": {"type": "number"}, "clear_nodata": {"type": "boolean"},
    }, "required": ["layer_name"]},
)
def set_raster_style(layer_name, mode=None, resampling=None, opacity_percent=None, nodata_min=None, nodata_max=None, clear_nodata=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = validate_raster_options(mode, resampling, opacity_percent, nodata_min, nodata_max, clear_nodata)
    if problem:
        return {"error": problem}
    layer = _find_layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if not isinstance(layer, QgsRasterLayer):
        return {"error": f"'{layer_name}' is not a raster layer. Use set_layer_symbol for vectors."}
    provider = layer.dataProvider()
    result = {"success": True, "layer_name": layer_name, "changed": {}}
    try:
        if "nodata_min" in options:
            provider.setUseSourceNoDataValue(1, False)
            provider.setUserNoDataValue(1, [QgsRasterRange(options["nodata_min"], options["nodata_max"])])
            result["changed"]["nodata"] = [options["nodata_min"], options["nodata_max"]]
        elif options.get("clear_nodata"):
            provider.setUserNoDataValue(1, [])
            provider.setUseSourceNoDataValue(1, True)
            result["changed"]["nodata"] = "source value restored"
        if options.get("mode") == "unique_values":
            classes = QgsPalettedRasterRenderer.classDataFromRaster(provider, 1)
            if not classes:
                return {"error": "No cell values were found to colour."}
            if len(classes) > MAX_UNIQUE_VALUES:
                return {"error": f"The raster has {len(classes)} distinct values; one colour each is not readable above {MAX_UNIQUE_VALUES}. "
                                 "Use apply_raster_stretch for a continuous ramp, or reclassify it first."}
            layer.setRenderer(QgsPalettedRasterRenderer(provider, 1, classes))
            result["changed"]["mode"] = "unique_values"
            result["classes"] = len(classes)
        if "opacity_percent" in options:
            renderer = layer.renderer()
            renderer.setOpacity(options["opacity_percent"] / 100.0)
            result["changed"]["opacity_percent"] = options["opacity_percent"]
        if "resampling" in options:
            _set_resampling(layer, provider, options["resampling"])
            result["changed"]["resampling"] = options["resampling"]
        layer.triggerRepaint()
    except Exception as e:
        return {"error": f"set_raster_style failed: {e}"}
    return result


def _set_resampling(layer, provider, method):
    """The provider-level resampling API (QGIS 3.16+) first; the render-time filter if that is absent."""
    enum_owner = getattr(type(provider), "ResamplingMethod", None) or getattr(provider, "ResamplingMethod", None)
    name = {"nearest": "Nearest", "bilinear": "Bilinear", "cubic": "Cubic"}[method]
    value = getattr(enum_owner, name, None) if enum_owner is not None else None
    if value is not None and hasattr(provider, "setZoomedInResamplingMethod"):
        provider.setZoomedInResamplingMethod(value)
        provider.setZoomedOutResamplingMethod(value)
        return
    from qgis.core import QgsBilinearRasterResampler, QgsCubicRasterResampler
    flt = layer.resampleFilter()
    resampler = {"nearest": None, "bilinear": QgsBilinearRasterResampler, "cubic": QgsCubicRasterResampler}[method]
    flt.setZoomedInResampler(resampler() if resampler else None)
    flt.setZoomedOutResampler(resampler() if resampler else None)
