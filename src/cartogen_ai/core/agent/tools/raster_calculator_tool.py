"""raster_calculator: map algebra on rasters in the project, through QGIS's own calculator (native:rastercalc). M7, roadmap 2026-10-14.

"dem@1 > 100", "(nir - red) / (nir + red)", "slope < 15 AND landcover = 2": the user's expression is checked by raster_expression.py (QGIS's
grammar only, nothing is evaluated as Python) and handed to native:rastercalc with the layers it names. The result is a new raster file in a
temporary location, added to the project; no input layer is changed. Cells where an input is NoData come out NoData (QGIS's rule).

Written without a QGIS install; tests/test_raster_calculator_tool_live.py is its first execution in CI."""
from .raster_expression import validate_raster_expression
from .registry import register_tool

try:
    from qgis.core import QgsProject, QgsRasterLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _raster_layers_by_name():
    """{name: [layers]} of the raster layers in the project."""
    found = {}
    for layer in QgsProject.instance().mapLayers().values():
        if isinstance(layer, QgsRasterLayer):
            found.setdefault(layer.name(), []).append(layer)
    return found


@register_tool(
    "raster_calculator",
    "Raster calculator (map algebra): computes a new raster from one or more raster layers in the project with an expression, using QGIS's own "
    "raster calculator. Write each layer as \"layer name@band\" in double quotes (band numbers start at 1), for example "
    "\"dem@1\" > 100 (a 0/1 mask of cells above 100), (\"nir@1\" - \"red@1\") / (\"nir@1\" + \"red@1\"), or \"slope@1\" < 15 AND \"landcover@1\" = 2. "
    "Allowed: numbers, + - * / ^, comparisons (< > = != <= >=), AND, OR, brackets and the functions sqrt sin cos tan asin acos atan ln log10 abs "
    "min max. Anything else is refused before QGIS runs. The first layer named sets the output extent and cell size by default. Adds a NEW "
    "raster layer (default name 'raster_calc'); no input layer is changed. Cells where any input is NoData stay NoData.",
    {"type": "object", "properties": {
        "expression": {"type": "string", "description": 'Raster expression, layers written as "layer name@band".'},
        "new_layer_name": {"type": "string", "description": "Name for the result layer (default 'raster_calc')."},
    }, "required": ["expression"]},
)
def raster_calculator(expression, new_layer_name="raster_calc"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    by_name = _raster_layers_by_name()
    check = validate_raster_expression(expression, {name: layers[0].bandCount() for name, layers in by_name.items()})
    if not check["ok"]:
        return {k: v for k, v in check.items() if k != "ok"}
    ambiguous = sorted({name for name, _band in check["refs"] if len(by_name[name]) > 1})
    if ambiguous:
        return {"error": f"More than one raster layer is named {ambiguous}; rename them so each name is unique, then ask again."}
    ordered = []
    for name, _band in check["refs"]:
        layer = by_name[name][0]
        if layer not in ordered:
            ordered.append(layer)
    crs_ids = {layer.crs().authid() or layer.crs().toWkt() for layer in ordered}
    if len(crs_ids) > 1:
        return {"error": "The rasters in this expression use different coordinate systems: " + ", ".join(
            f"'{layer.name()}' ({layer.crs().authid() or 'custom'})" for layer in ordered) + ". Reproject them to one system first."}
    from .raster_tools import _run_raster_and_add
    params = {"EXPRESSION": str(expression).strip(), "LAYERS": ordered, "CELLSIZE": None, "EXTENT": None, "CRS": None}
    result = _run_raster_and_add("native:rastercalc", params, new_layer_name or "raster_calc")
    if result.get("success"):
        result["expression"] = str(expression).strip()
        result["input_layers"] = [layer.name() for layer in ordered]
        result["note"] = ("A new raster; no input was changed. Cells where any input is NoData are NoData. Use apply_raster_stretch to "
                          "change how it is drawn.")
    return result
