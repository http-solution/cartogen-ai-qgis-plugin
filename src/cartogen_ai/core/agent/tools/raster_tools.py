# -*- coding: utf-8 -*-
"""
Raster & Remote Sensing Processing Tools for Cartogen AI.
"""

import math
import os
import re
import tempfile
from .registry import register_tool
from ._qgis_enum_compat import resolve_qgis_enum
from ...logger import log_warning, log_error


try:
    from qgis.core import (
        QgsApplication, QgsProject, QgsRasterLayer, QgsWkbTypes, QgsSingleBandGrayRenderer,
        QgsSingleBandPseudoColorRenderer, QgsContrastEnhancement, QgsRasterShader,
        QgsColorRampShader, QgsRasterBandStats, QgsStyle,
    )
    from qgis.PyQt.QtGui import QPainter
    import qgis.core as _qgis_core_module
    import processing
    QGIS_AVAILABLE = True
    # QGIS 4.x/Qt6 nests these under a named sub-enum; QGIS 3.x/Qt5 exposes
    # them flat on the class itself. Resolved once here rather than assuming
    # one form -- see _qgis_enum_compat.py.
    # QgsRasterBandStats.Stat is deprecated since QGIS 3.40 (a WARNING with a traceback on every call in the rc10 smoke
    # log); Qgis.RasterBandStatistic replaces it. Fall back to the old spelling only when the new one is absent.
    _RBS_MIN = resolve_qgis_enum(_qgis_core_module.Qgis, "RasterBandStatistic", "Min") if hasattr(
        _qgis_core_module.Qgis, "RasterBandStatistic") else resolve_qgis_enum(QgsRasterBandStats, "Stat", "Min")
    _RBS_MAX = resolve_qgis_enum(_qgis_core_module.Qgis, "RasterBandStatistic", "Max") if hasattr(
        _qgis_core_module.Qgis, "RasterBandStatistic") else resolve_qgis_enum(QgsRasterBandStats, "Stat", "Max")
    _STRETCH_MINMAX = resolve_qgis_enum(QgsContrastEnhancement, "ContrastEnhancementAlgorithm", "StretchToMinimumMaximum")
    _RAMP_INTERPOLATED = resolve_qgis_enum(QgsColorRampShader, "Type", "Interpolated")
    # QPainter.CompositionMode.CompositionMode_Multiply (Qt6/PyQt6) vs QPainter.CompositionMode_Multiply (Qt5/PyQt5)
    _COMPOSITION_MULTIPLY = resolve_qgis_enum(QPainter, "CompositionMode", "CompositionMode_Multiply")
    # QGIS 4.x moved this from a standalone qgis.core.QgsColorRampShaderItem
    # class to a nested QgsColorRampShader.ColorRampItem -- confirmed live
    # against a real QGIS 4.2.2 install, where the old top-level import
    # raises ImportError at module load, silently taking every tool in this
    # file down to QGIS_AVAILABLE=False (invisible to the sandboxed test
    # suite, which has no real QGIS to catch it). Resolved once here rather
    # than assuming one form, same pattern as the enum members above.
    _COLOR_RAMP_SHADER_ITEM = getattr(QgsColorRampShader, "ColorRampItem", None) or getattr(
        _qgis_core_module, "QgsColorRampShaderItem", None
    )
except ImportError:
    QGIS_AVAILABLE = False
    _RBS_MIN = None
    _RBS_MAX = None
    _STRETCH_MINMAX = None
    _RAMP_INTERPOLATED = None
    _COLOR_RAMP_SHADER_ITEM = None
    _COMPOSITION_MULTIPLY = None



def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


def _temp_raster_path(suffix=".tif"):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return path


def _algorithm_available(alg_id):
    """True when the running QGIS Processing registry has this algorithm (False if it cannot be asked)."""
    try:
        return QgsApplication.processingRegistry().algorithmById(alg_id) is not None
    except Exception:
        return False


def grid_differences(signatures):
    """Reasons the rasters do not share one pixel grid; [] when they do. Pure.

    `signatures` is a list of (name, crs_key, width, height, xmin, ymax, pixel_x, pixel_y). Audit F17 (#153): the tools only
    compared CRS auth ids, so rasters with the same CRS but a different extent, origin or resolution were combined pixel by
    pixel by GDAL (which checks dimensions, not geography) into a meaningless result, and two custom CRSs both have an
    empty auth id. Compared against the first raster, with a tolerance of 1e-6 of a pixel for origin and size."""
    problems = []
    if len(signatures) < 2:
        return problems
    ref = signatures[0]
    for sig in signatures[1:]:
        reasons = []
        if sig[1] != ref[1]:
            reasons.append("a different CRS")
        if (sig[2], sig[3]) != (ref[2], ref[3]):
            reasons.append(f"a different size ({sig[2]}x{sig[3]} vs {ref[2]}x{ref[3]} pixels)")
        tol_x, tol_y = 1e-6 * abs(ref[6] or 1.0), 1e-6 * abs(ref[7] or 1.0)
        if abs(sig[6] - ref[6]) > tol_x or abs(sig[7] - ref[7]) > tol_y:
            reasons.append("a different pixel size")
        if abs(sig[4] - ref[4]) > max(tol_x, 1e-6 * abs(ref[6] or 1.0)) or abs(sig[5] - ref[5]) > tol_y:
            reasons.append("a different origin/extent")
        if reasons:
            problems.append(f"'{sig[0]}' has " + " and ".join(reasons) + f" than '{ref[0]}'")
    return problems


def _common_grid_error(layers):
    """An error message when the raster layers are not on one pixel grid, else None. Needs QGIS."""
    sigs = []
    for layer in layers:
        ext = layer.extent()
        crs = layer.crs()
        # The CRS definition itself is the key, not its auth id: two custom CRSs both have an empty one.
        sigs.append((layer.name(), crs.toWkt() if crs.isValid() else "", layer.width(), layer.height(),
                     ext.xMinimum(), ext.yMaximum(), layer.rasterUnitsPerPixelX(), layer.rasterUnitsPerPixelY()))
    problems = grid_differences(sigs)
    if not problems:
        return None
    return ("The rasters are not on the same pixel grid: " + "; ".join(problems) + ". Combining them pixel by pixel would "
            "give a meaningless result. Resample/warp them onto one grid first (e.g. the gdal:warpreproject algorithm "
            "with the same extent and resolution).")


_RESAMPLING = {"nearest": "near", "bilinear": "bilinear", "cubic": "cubic"}

_ALIGN_PARAMS = {
    "align_to_first": {"type": "boolean", "description": "If the rasters are not on one pixel grid, warp the others onto the first raster's grid (its CRS, extent and cell size) instead of refusing. The result says which raster was the reference and the resampling used. Default false: refuse."},
    "resampling": {"type": "string", "description": "With align_to_first: 'bilinear' (default, for continuous values such as reflectance), 'nearest' (for classes or counts) or 'cubic'."},
}


def align_layers_to_first(layers, resampling="bilinear"):
    """Warp every layer after the first onto the first layer's grid. Returns (aligned_layers, error, note). Needs QGIS and GDAL.

    Audit F17 (#153): mismatched grids were only refused; this is the other half, an explicit, stated alignment. The reference is the first
    layer in the call. Each other layer is resampled with the stated rule into a temporary GeoTIFF that is NOT added to the project, so the
    user's own layers are untouched. A layer whose source is not a local file (a web service) cannot be warped and is reported."""
    rule = _RESAMPLING.get(str(resampling or "bilinear").strip().lower())
    if rule is None:
        return None, f"resampling must be one of {sorted(_RESAMPLING)}, got {resampling!r}.", None
    try:
        from osgeo import gdal
    except ImportError:
        return None, "Aligning rasters needs GDAL's Python bindings, which this QGIS does not provide; warp them onto one grid first.", None
    ref = layers[0]
    ext = ref.extent()
    out = [ref]
    moved = []
    for layer in layers[1:]:
        src = layer.source()
        if not os.path.isfile(src.split("|")[0]):
            return None, f"'{layer.name()}' is not a local raster file, so it cannot be aligned automatically.", None
        path = _temp_raster_path()
        try:
            ds = gdal.Warp(path, src.split("|")[0], format="GTiff", dstSRS=ref.crs().toWkt(),
                           outputBounds=(ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum()),
                           width=ref.width(), height=ref.height(), resampleAlg=rule, dstNodata=None)
            if ds is None:
                raise RuntimeError("gdal.Warp returned no dataset")
            ds = None
        except Exception as e:
            return None, f"Could not align '{layer.name()}' to '{ref.name()}': {e}", None
        aligned = QgsRasterLayer(path, layer.name())
        if not aligned.isValid():
            return None, f"The aligned copy of '{layer.name()}' could not be loaded.", None
        out.append(aligned)
        moved.append(layer.name())
    note = (f"Aligned {', '.join(repr(n) for n in moved)} onto the grid of '{ref.name()}' (its CRS, extent and {ref.width()}x{ref.height()} cells) "
            f"with {str(resampling or 'bilinear').lower()} resampling. Temporary copies were used; no layer in the project was changed. "
            "Cells outside a layer's own extent are NoData-filled by the warp.")
    return out, None, note


def _grid_or_error(layers, align_to_first=False, resampling="bilinear"):
    """(layers_to_use, error, alignment_note). On one common grid: the layers unchanged. Otherwise: align when asked, else the refusal."""
    problem = _common_grid_error(layers)
    if not problem:
        return layers, None, None
    if not align_to_first:
        return None, problem + " Pass align_to_first=true to warp them onto the first raster's grid.", None
    aligned, error, note = align_layers_to_first(layers, resampling)
    if error:
        return None, error, None
    return aligned, None, note


def _with_alignment_note(result, note):
    if note and isinstance(result, dict) and "error" not in result:
        result["alignment"] = note
    return result


def _index_expression():
    """Normalised-difference formula with a stated rule for a zero denominator: those pixels become 0, not inf/NaN."""
    return "numpy.where((A.astype(float)+B)==0, 0, (A.astype(float)-B)/(A.astype(float)+B))"


def _run_raster_and_add(alg, params, new_name, output_key="OUTPUT"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    try:
        out_path = _temp_raster_path()
        params[output_key] = out_path
        processing.run(alg, params)
        if not os.path.exists(out_path):
            return {"error": f"{alg} failed to produce output at {out_path}"}
        new_layer = QgsRasterLayer(out_path, new_name)
        if not new_layer.isValid():
            return {"error": f"Generated raster layer is invalid: {out_path}"}
        QgsProject.instance().addMapLayer(new_layer)
        return {"success": True, "layer_name": new_name}
    except Exception as e:
        return {"error": f"{alg} failed: {e}"}


@register_tool(
    "calculate_ndvi",
    "Calculate NDVI (Normalized Difference Vegetation Index) from Red and Near-Infrared raster "
    "bands -- the standard remote-sensing measure of vegetation health/greenness/density: 'how "
    "green is this area', 'is this crop/vegetation healthy', 'vegetation health check'. Output "
    "ranges roughly -1 to 1: values near 1 indicate dense healthy vegetation, near 0 bare soil or "
    "built-up areas, negative values open water. Produces a new single-band raster layer named "
    "'NDVI' added to the project with QGIS's default (unstretched, low-contrast) rendering -- follow "
    "up with apply_raster_stretch(layer_name='NDVI') to apply a readable diverging color ramp "
    "(auto-selected for NDVI-named layers) instead of leaving it flat/unstretched.",
    {"type": "object", "properties": {"red_layer": {"type": "string"}, "nir_layer": {"type": "string"}, **_ALIGN_PARAMS}, "required": ["red_layer", "nir_layer"]},
)
def calculate_ndvi(red_layer, nir_layer, align_to_first=False, resampling="bilinear"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    red = _find_layer_by_name(red_layer)
    nir = _find_layer_by_name(nir_layer)
    if red is None:
        return {"error": f"Layer '{red_layer}' not found"}
    if nir is None:
        return {"error": f"Layer '{nir_layer}' not found"}
    used, grid_error, align_note = _grid_or_error([nir, red], align_to_first, resampling)
    if grid_error:
        return {"error": grid_error}
    nir, red = used
    return _with_alignment_note(_run_raster_and_add(
        "gdal:rastercalculator",
        {
            "INPUT_A": nir,
            "BAND_A": 1,
            "INPUT_B": red,
            "BAND_B": 1,
            "FORMULA": _index_expression(),
            "NO_DATA": None,
            "RTYPE": 5,
        },
        "NDVI",
    ), align_note)


@register_tool(
    "calculate_ndwi",
    "Calculate NDWI (Normalized Difference Water Index) from Green and Near-Infrared raster bands "
    "-- the standard remote-sensing measure of surface water/moisture: 'how much water is in this "
    "area', 'map surface water extent', 'is there flooding here'. Output ranges roughly -1 to 1: "
    "values above ~0 typically indicate open water, below ~0 vegetation/dry land. For a flood-"
    "specific before/after comparison rather than a single-image water map, use "
    "calculate_raster_change_detection instead. Produces a new single-band raster layer named "
    "'NDWI' with QGIS's default (unstretched) rendering -- follow up with "
    "apply_raster_stretch(layer_name='NDWI') to apply a readable diverging color ramp (auto-selected "
    "for NDWI-named layers) instead of leaving it flat/unstretched.",
    {"type": "object", "properties": {"green_layer": {"type": "string"}, "nir_layer": {"type": "string"}, **_ALIGN_PARAMS}, "required": ["green_layer", "nir_layer"]},
)
def calculate_ndwi(green_layer, nir_layer, align_to_first=False, resampling="bilinear"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    green = _find_layer_by_name(green_layer)
    nir = _find_layer_by_name(nir_layer)
    if green is None:
        return {"error": f"Layer '{green_layer}' not found"}
    if nir is None:
        return {"error": f"Layer '{nir_layer}' not found"}
    used, grid_error, align_note = _grid_or_error([green, nir], align_to_first, resampling)
    if grid_error:
        return {"error": grid_error}
    green, nir = used
    return _with_alignment_note(_run_raster_and_add(
        "gdal:rastercalculator",
        {
            "INPUT_A": green,
            "BAND_A": 1,
            "INPUT_B": nir,
            "BAND_B": 1,
            "FORMULA": _index_expression(),
            "NO_DATA": None,
            "RTYPE": 5,
        },
        "NDWI",
    ), align_note)


_OVERLAY_LETTERS = ["A", "B", "C", "D", "E", "F"]


def _compute_normalized_weights(weights):
    """Pure Python, no QGIS needed -- validates and normalizes a weights list
    so it sums to 1. Separated out so this logic is directly unit-testable."""
    if any(w < 0 for w in weights):
        return None, "weights must be non-negative."
    total = sum(weights)
    if total <= 0:
        return None, "weights must sum to a positive number."
    return [w / total for w in weights], None


@register_tool(
    "weighted_overlay_analysis",
    "Combine multiple rasters into a single weighted suitability/risk surface -- e.g. 'best sites "
    "for a new clinic' combining slope, distance-to-road, and population density rasters with "
    "different weights. Each input raster should already be normalized to a comparable scale (e.g. "
    "0-1 or 0-100) before combining -- this tool weights and sums them, it doesn't rescale them. "
    "All rasters must share the same CRS and cover roughly the same extent/resolution, or the "
    "result is meaningless; mismatched CRS is rejected outright rather than silently misaligned.",
    {
        "type": "object",
        "properties": {
            "raster_layers": {
                "type": "array", "items": {"type": "string"},
                "description": f"2 to {len(_OVERLAY_LETTERS)} raster layer names to combine.",
            },
            "weights": {
                "type": "array", "items": {"type": "number"},
                "description": "One weight per raster, same order as raster_layers. Don't need to sum to 1 -- normalized automatically.",
            },
            **_ALIGN_PARAMS,
        },
        "required": ["raster_layers", "weights"],
    },
)
def weighted_overlay_analysis(raster_layers, weights, align_to_first=False, resampling="bilinear"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if len(raster_layers) < 2:
        return {"error": "Provide at least 2 raster layers to combine."}
    if len(raster_layers) > len(_OVERLAY_LETTERS):
        return {"error": f"weighted_overlay_analysis supports at most {len(_OVERLAY_LETTERS)} rasters."}
    if len(weights) != len(raster_layers):
        return {"error": "weights must have exactly one entry per raster_layers entry."}

    normalized, err = _compute_normalized_weights(weights)
    if err:
        return {"error": err}

    layers = []
    for name in raster_layers:
        layer = _find_layer_by_name(name)
        if layer is None:
            return {"error": f"Layer '{name}' not found"}
        layers.append(layer)

    layers, grid_error, align_note = _grid_or_error(layers, align_to_first, resampling)
    if grid_error:
        return {"error": grid_error}

    params = {"NO_DATA": None, "RTYPE": 5}
    formula_terms = []
    for letter, layer, w in zip(_OVERLAY_LETTERS, layers, normalized):
        params[f"INPUT_{letter}"] = layer
        params[f"BAND_{letter}"] = 1
        formula_terms.append(f"{letter}.astype(float)*{w}")
    params["FORMULA"] = "+".join(formula_terms)

    res = _with_alignment_note(_run_raster_and_add("gdal:rastercalculator", params, "weighted_overlay"), align_note)
    if isinstance(res, dict) and res.get("success"):
        res["normalized_weights"] = dict(zip(raster_layers, [round(w, 4) for w in normalized]))
        # HX1b: an ordered, opaque low-to-high surface under the vectors instead of QGIS's grey stretch (best effort)
        try:
            from .output_style import style_continuous_raster
            made = QgsProject.instance().mapLayersByName("weighted_overlay")
            if made:
                res["styled"] = style_continuous_raster(made[-1], "surface")
        except Exception:
            pass
    return res


@register_tool(
    "calculate_ndre",
    "Calculate NDRE (Normalized Difference Red Edge index) from Red Edge and Near-Infrared raster "
    "bands -- a precision-agriculture vegetation index more sensitive than NDVI to chlorophyll/"
    "nitrogen status in mid-to-late-season crops: 'crop nitrogen stress', 'plant chlorophyll "
    "health', 'precision agriculture crop monitoring'. Needs a Red Edge band (not standard on "
    "every sensor -- confirm the imagery actually has one before calling this over calculate_ndvi, "
    "which only needs Red/NIR and works with far more common sensors). Produces a new single-band "
    "raster layer named 'NDRE' with QGIS's default (unstretched) rendering -- follow up with "
    "apply_raster_stretch(layer_name='NDRE') to apply a readable diverging color ramp (auto-selected "
    "for NDRE-named layers) instead of leaving it flat/unstretched.",
    {"type": "object", "properties": {"red_edge_layer": {"type": "string"}, "nir_layer": {"type": "string"}, **_ALIGN_PARAMS}, "required": ["red_edge_layer", "nir_layer"]},
)
def calculate_ndre(red_edge_layer, nir_layer, align_to_first=False, resampling="bilinear"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    re = _find_layer_by_name(red_edge_layer)
    nir = _find_layer_by_name(nir_layer)
    if re is None:
        return {"error": f"Layer '{red_edge_layer}' not found"}
    if nir is None:
        return {"error": f"Layer '{nir_layer}' not found"}
    used, grid_error, align_note = _grid_or_error([nir, re], align_to_first, resampling)
    if grid_error:
        return {"error": grid_error}
    nir, re = used
    return _with_alignment_note(_run_raster_and_add(
        "gdal:rastercalculator",
        {
            "INPUT_A": nir,
            "BAND_A": 1,
            "INPUT_B": re,
            "BAND_B": 1,
            "FORMULA": _index_expression(),
            "NO_DATA": None,
            "RTYPE": 5,
        },
        "NDRE",
    ), align_note)


def _geographic_z_factor(dem):
    """Z_FACTOR converts the DEM's vertical unit (assumed meters) into the same unit as
    its horizontal units for hillshade/slope's internal gradient math. On a projected CRS
    (meters in both directions) that's 1 -- QGIS's own default. On a geographic CRS
    (degrees), 1 vertical meter was being treated as 1 horizontal DEGREE (~111km),
    producing a completely flat, washed-out hillshade/slope. Scales by the DEM's center
    latitude since a degree of longitude shrinks by cos(latitude) while a degree of
    latitude stays ~111.32km everywhere -- an approximation (true only exactly at that
    latitude), not a full per-pixel reprojection, but far closer than the previous
    hardcoded 1."""
    try:
        crs = dem.crs()
        if crs is None:
            return 1
        if not crs.isGeographic():
            # Rc20 audit A11: "projected" is not "metres" -- a US-foot State Plane DEM has horizontal units of feet, so a metre
            # elevation needs 1/0.3048 to match them (returning 1 understated slope by ~3.28x). Convert metres into the CRS's own
            # map units; an unreadable unit keeps the old 1 rather than failing the tool.
            try:
                from qgis.core import Qgis, QgsUnitTypes
                factor = QgsUnitTypes.fromUnitToUnitFactor(Qgis.DistanceUnit.Meters, crs.mapUnits())
                return float(factor) if factor and factor > 0 else 1
            except Exception:
                return 1
        center_lat = dem.extent().center().y()
        return 1.0 / (111320.0 * math.cos(math.radians(center_lat)))
    except Exception:
        return 1


@register_tool("hillshade", "Generate hillshade surface from DEM layer.", {"type": "object", "properties": {"dem_layer": {"type": "string"}}, "required": ["dem_layer"]})
def hillshade(dem_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    dem = _find_layer_by_name(dem_layer)
    if dem is None:
        return {"error": f"Layer '{dem_layer}' not found"}
    return _run_raster_and_add(
        "native:hillshade",
        {"INPUT": dem, "Z_FACTOR": _geographic_z_factor(dem), "AZIMUTH": 315, "ALTITUDE": 45},
        f"{dem_layer}_hillshade",
    )


@register_tool(
    "create_shaded_relief",
    "Generate a publication-grade shaded relief composite from a DEM layer combining hypsometric "
    "elevation tinting with hillshade using Multiply blending (QPainter.CompositionMode_Multiply). "
    "First styles the DEM with a pseudocolor elevation color ramp (e.g. 'BrBG', 'Spectral', or 'Terrain'), "
    "generates or links the hillshade layer, and applies the Multiply blend mode so the topography modulates "
    "the elevation colors cleanly without flattening.",
    {
        "type": "object",
        "properties": {
            "dem_layer": {"type": "string", "description": "Name of the DEM/elevation raster layer."},
            "color_ramp": {"type": "string", "description": "Color ramp name for hypsometric tinting. Defaults to 'BrBG' (CVD-safe diverging ramp)."},
            "azimuth": {"type": "number", "description": "Sun azimuth angle in degrees (default 315)."},
            "altitude": {"type": "number", "description": "Sun altitude angle in degrees (default 45)."},
            "opacity": {"type": "number", "description": "Hillshade layer opacity between 0.0 and 1.0 (default 1.0)."},
        },
        "required": ["dem_layer"],
    },
)
def create_shaded_relief(dem_layer, color_ramp="BrBG", azimuth=315, altitude=45, opacity=1.0):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    dem = _find_layer_by_name(dem_layer)
    if dem is None:
        return {"error": f"Layer '{dem_layer}' not found"}

    # Validate opacity parameter
    try:
        opacity_f = float(opacity)
        if not (0.0 <= opacity_f <= 1.0):
            return {"error": f"opacity must be between 0.0 and 1.0, got {opacity}"}
    except (TypeError, ValueError):
        return {"error": f"opacity must be a valid float between 0.0 and 1.0, got '{opacity}'"}

    # 1. Apply hypsometric elevation tinting to DEM
    style_res = apply_raster_stretch(dem_layer, mode="color_ramp", color_ramp=color_ramp)
    if not style_res.get("success"):
        return {"error": f"Failed to style DEM with hypsometric tint: {style_res.get('error')}"}

    # 2. Generate hillshade layer
    hs_name = f"{dem_layer}_hillshade"
    hs_res = _run_raster_and_add(
        "native:hillshade",
        {"INPUT": dem, "Z_FACTOR": _geographic_z_factor(dem), "AZIMUTH": azimuth, "ALTITUDE": altitude},
        hs_name,
    )
    if not hs_res.get("success"):
        return {"error": f"Failed to generate hillshade: {hs_res.get('error')}"}

    # 3. Apply Multiply blend mode to the hillshade layer
    hs_layer = _find_layer_by_name(hs_name)
    if hs_layer is None:
        return {"error": f"Hillshade layer '{hs_name}' was generated but could not be retrieved from map project."}

    if _COMPOSITION_MULTIPLY is None or not hasattr(hs_layer, "setBlendMode"):
        log_error("Multiply composition mode is not supported by this QGIS/Qt environment", tag="create_shaded_relief")
        return {"error": "Multiply composition mode (QPainter.CompositionMode_Multiply) is not supported by this QGIS/Qt environment."}

    try:
        hs_layer.setBlendMode(_COMPOSITION_MULTIPLY)
    except Exception as e:
        log_error(f"Failed to set Multiply blend mode on hillshade layer: {e}", tag="create_shaded_relief")
        return {"error": f"Failed to set Multiply blend mode on hillshade layer: {e}"}

    try:
        if hasattr(hs_layer, "setOpacity"):
            hs_layer.setOpacity(opacity_f)
    except Exception as e:
        log_warning(f"Could not adjust opacity on hillshade layer: {e}", tag="create_shaded_relief")

    if hasattr(hs_layer, "triggerRepaint"):
        hs_layer.triggerRepaint()

    return {
        "success": True,
        "dem_layer": dem_layer,
        "hillshade_layer": hs_name,
        "color_ramp": style_res.get("color_ramp", color_ramp),
        "blend_mode": "Multiply",
        "opacity": opacity_f,
        "composite_pipeline": "hypsometric_tint + hillshade_multiply",
    }



_VERTICAL_UNIT_FACTORS = {
    "m": 1.0, "metre": 1.0, "metres": 1.0, "meter": 1.0, "meters": 1.0,
    "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
    "us_ft": 1200.0 / 3937.0, "us-ft": 1200.0 / 3937.0, "us_survey_foot": 1200.0 / 3937.0, "us survey foot": 1200.0 / 3937.0,
}


def vertical_unit_factor(unit):
    """Metres per DEM vertical unit, or None for an unrecognised unit. Pure. A QGIS raster layer does not carry a vertical unit, so it
    cannot be read from the layer: the tools take it as an argument (default metres) and say which they used (audit F18, #154)."""
    return _VERTICAL_UNIT_FACTORS.get(str(unit if unit is not None else "m").strip().lower())


_VERTICAL_UNIT_PARAM = {"type": "string", "description": "Vertical unit of the DEM's elevation values: 'm' (default), 'ft' or 'us_ft'. A raster does not carry its vertical unit, so say so if the DEM is in feet."}


@register_tool("slope_analysis", "Calculate slope map from DEM layer. Elevations are taken as metres unless dem_vertical_unit says 'ft' or 'us_ft'.", {"type": "object", "properties": {"dem_layer": {"type": "string"}, "dem_vertical_unit": _VERTICAL_UNIT_PARAM}, "required": ["dem_layer"]})
def slope_analysis(dem_layer, dem_vertical_unit="m"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    dem = _find_layer_by_name(dem_layer)
    if dem is None:
        return {"error": f"Layer '{dem_layer}' not found"}
    vertical = vertical_unit_factor(dem_vertical_unit)
    if vertical is None:
        return {"error": f"dem_vertical_unit must be 'm', 'ft' or 'us_ft', got {dem_vertical_unit!r}."}
    result = _run_raster_and_add(
        "native:slope",
        {"INPUT": dem, "Z_FACTOR": _geographic_z_factor(dem) * vertical},
        f"{dem_layer}_slope",
    )
    if isinstance(result, dict) and "error" not in result:
        result["vertical_unit_used"] = str(dem_vertical_unit or "m")
    return result


@register_tool("aspect_analysis", "Calculate aspect map from DEM layer.", {"type": "object", "properties": {"dem_layer": {"type": "string"}}, "required": ["dem_layer"]})
def aspect_analysis(dem_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    dem = _find_layer_by_name(dem_layer)
    if dem is None:
        return {"error": f"Layer '{dem_layer}' not found"}
    return _run_raster_and_add(
        "native:aspect",
        {"INPUT": dem},
        f"{dem_layer}_aspect",
    )


_ZONAL_FIELDS = ("zs_mean", "zs_median", "zs_stdev")


def _zonal_stats_into_layer(raster, polygon_layer):
    """Mean/median/stdev of `raster` per polygon, written into `polygon_layer` as zs_mean / zs_median / zs_stdev.

    Rc20 audit A14: the statistics (the slow part) are computed by native:zonalstatisticsfb on a geometry-only memory copy
    through the background runner, so QGIS stays responsive and Stop works; the old qgis:zonalstatistics edited the live layer
    in place on the GUI thread and cannot run on a worker. The values are then written into the real layer on the GUI thread as
    one undoable edit command. An existing zs_ field is overwritten rather than duplicated. Raises on failure."""
    from qgis.core import QgsFeature, QgsField, QgsProcessingContext, QgsVectorLayer
    from qgis.PyQt.QtCore import QVariant
    from . import _background_processing as _bg
    from ._edit_session import edit_command

    scratch = QgsVectorLayer(f"{QgsWkbTypes.displayString(polygon_layer.wkbType()) or 'Polygon'}?crs={polygon_layer.crs().authid()}"
                             "&field=src_fid:integer", "zonal_input", "memory")
    copies = []
    for feat in polygon_layer.getFeatures():
        copy = QgsFeature(scratch.fields())
        copy.setGeometry(feat.geometry())
        copy.setAttributes([int(feat.id())])
        copies.append(copy)
    scratch.dataProvider().addFeatures(copies)

    context = QgsProcessingContext()
    context.setProject(QgsProject.instance())
    params = {"INPUT": scratch, "INPUT_RASTER": raster, "RASTER_BAND": 1, "COLUMN_PREFIX": "zs_",
              "STATISTICS": [2, 3, 4], "OUTPUT": "memory:"}
    results = _bg.run_algorithm("native:zonalstatisticsfb", params, context,
                                fallback=lambda alg, prm, context=None: processing.run(alg, prm, context=context),
                                label="Zonal statistics", use_background=len(copies) >= 200)
    out_layer = results["OUTPUT"]
    values = {}
    for out_feat in out_layer.getFeatures():
        values[int(out_feat["src_fid"])] = [out_feat[name] if out_layer.fields().indexOf(name) >= 0 else None
                                            for name in _ZONAL_FIELDS]

    with edit_command(polygon_layer, "Zonal statistics"):
        for name in _ZONAL_FIELDS:
            if polygon_layer.fields().indexOf(name) < 0:
                if not polygon_layer.addAttribute(QgsField(name, QVariant.Double)):
                    raise RuntimeError(f"could not add the field {name}")
        polygon_layer.updateFields()
        indexes = [polygon_layer.fields().indexOf(name) for name in _ZONAL_FIELDS]
        for fid, stats in values.items():
            for index, value in zip(indexes, stats):
                if not polygon_layer.changeAttributeValue(fid, index, None if value is None or value != value else float(value)):
                    raise RuntimeError("a statistic could not be written to the layer")



@register_tool("zonal_statistics", "Compute zonal statistics of raster over vector polygons.", {"type": "object", "properties": {"raster_layer": {"type": "string"}, "vector_layer": {"type": "string"}}, "required": ["raster_layer", "vector_layer"]})
def zonal_statistics(raster_layer, vector_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    ras = _find_layer_by_name(raster_layer)
    vec = _find_layer_by_name(vector_layer)
    if ras is None:
        return {"error": f"Layer '{raster_layer}' not found"}
    if vec is None:
        return {"error": f"Layer '{vector_layer}' not found"}

    try:
        _zonal_stats_into_layer(ras, vec)
        result = {"success": True, "message": f"Zonal statistics added to '{vector_layer}' (fields prefixed zs_)."}
        try:
            if vec.fields().indexOf("zs_mean") >= 0:
                from .humanitarian_style import measure_hint
                result["map_looks"] = [measure_hint(vector_layer, "zs_mean", "The mean raster value per area")]
        except Exception:
            pass  # the hint is a convenience; the statistics are already written
        return result
    except Exception as e:
        from . import _background_processing as _bg
        if isinstance(e, _bg.AnalysisCancelled):
            return {"error": f"Stopped: {e}", "cancelled": True}
        return {"error": f"zonal_statistics failed: {e}"}


@register_tool("raster_clip", "Clip raster layer by vector mask layer.", {"type": "object", "properties": {"raster_layer": {"type": "string"}, "mask_layer": {"type": "string"}}, "required": ["raster_layer", "mask_layer"]})
def raster_clip(raster_layer, mask_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    ras = _find_layer_by_name(raster_layer)
    mask = _find_layer_by_name(mask_layer)
    if ras is None:
        return {"error": f"Layer '{raster_layer}' not found"}
    if mask is None:
        return {"error": f"Layer '{mask_layer}' not found"}

    return _run_raster_and_add(
        "gdal:cliprasterbymasklayer",
        {
            "INPUT": ras,
            "MASK": mask,
            "SOURCE_CRS": None,
            "TARGET_CRS": None,
            "NODATA": None,
            "ALPHA_BAND": False,
            "CROP_TO_CUTLINE": True,
            "KEEP_RESOLUTION": True,
            "SET_RESOLUTION": False,
            "X_RESOLUTION": None,
            "Y_RESOLUTION": None,
            "MULTITHREADING": False,
            "OPTIONS": "",
            "DATA_TYPE": 0,
            "EXTRA": "",
        },
        f"{raster_layer}_clipped",
    )


@register_tool("unsupervised_classification", "Unsupervised K-Means raster classification of up to the first 8 bands into num_classes spectral classes (1..num_classes; 0 = no data). Classes are statistical clusters of pixel values, NOT land-cover categories: label them yourself. Reproducible with a seed; refuses rasters over 25 million cells or 60 million cell-band values (clip first or use fewer bands).", {"type": "object", "properties": {"layer_name": {"type": "string"}, "num_classes": {"type": "integer", "description": "Number of clusters, 2 to 50."}, "seed": {"type": "integer", "description": "Random seed (default 0)."}}, "required": ["layer_name", "num_classes"]})
def unsupervised_classification(layer_name, num_classes, seed=0):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    ras = _find_layer_by_name(layer_name)
    if ras is None:
        return {"error": f"Layer '{layer_name}' not found"}
    # GitHub #162: saga:kmeansclassificationforgrid is not available (no SAGA provider in QGIS 4.2.2; CI registry diagnostic,
    # PR #175), so the clustering is computed here with numpy.
    from . import raster_numpy
    problem = raster_numpy.validate_class_count(num_classes)
    if problem:
        return {"error": problem}
    k = int(num_classes)
    try:
        values, valid, info = raster_numpy.read_bands(ras.source())
        pixels = values[valid]
        if len(pixels) < k:
            return {"error": f"Only {len(pixels)} valid cells, fewer than the {k} classes requested."}
        labels, _centres = raster_numpy.kmeans(pixels, k, seed=int(seed))
        classified = raster_numpy._np().zeros(valid.shape, dtype="uint8")
        classified[valid] = (labels + 1).astype("uint8")
        path = raster_numpy.write_single_band(classified, info, nodata=0)
        new_layer = QgsRasterLayer(path, f"{layer_name}_classified")
        if not new_layer.isValid():
            return {"error": "The classified raster could not be loaded."}
        QgsProject.instance().addMapLayer(new_layer)
        from .humanitarian_style import style_classified_raster
        styled = style_classified_raster(new_layer, k)
        return {"success": True, "layer_name": f"{layer_name}_classified", "classes": k, "styled": styled, "bands_used": info["bands_used"],
                "valid_cells": int(valid.sum()), "seed": int(seed),
                "note": "Classes are statistical clusters of the band values, not land-cover categories; name them from knowledge of the area."}
    except ValueError as e:
        return {"error": f"unsupervised_classification: {e}"}
    except ImportError:
        return {"error": "unsupervised_classification needs numpy, which this QGIS does not provide."}
    except Exception as e:
        return {"error": f"unsupervised_classification failed: {e}"}


@register_tool("supervised_classification", "Supervised classification using training polygons.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "training_layer": {"type": "string"}}, "required": ["layer_name", "training_layer"]})
def supervised_classification(layer_name, training_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    raster = _find_layer_by_name(layer_name)
    training = _find_layer_by_name(training_layer)
    if raster is None:
        return {"error": f"Layer '{layer_name}' not found"}
    if training is None:
        return {"error": f"Layer '{training_layer}' not found"}
    if not _algorithm_available("saga:supervisedclassificationforgrids"):
        # GitHub #162: the SAGA provider is not installed in QGIS 4.2.2 (CI registry diagnostic, PR #175). Say so plainly instead of
        # failing inside Processing; the unsupervised tool does not need SAGA.
        return {"error": "supervised_classification needs the SAGA Processing provider, which is not available in this QGIS. "
                         "unsupervised_classification works without it (it gives statistical clusters, not training-based classes)."}
    return _run_raster_and_add(
        "saga:supervisedclassificationforgrids",
        {
            "GRIDS": [raster],
            "TRAINING": training,
            "TRAINING_CLASS": "class",
            "METHOD": 2,
            "NORMALISE": False,
        },
        f"{layer_name}_classified",
        output_key="CLASSES",
    )


@register_tool("histogram_equalization", "Enhance raster image contrast using histogram equalization. Writes a NEW 8-bit raster (0-255) of one band; no-data cells stay no-data. A global equalisation of the band, for display and visual interpretation: the values are no longer the original measurements.", {"type": "object", "properties": {"raster_layer": {"type": "string"}, "band": {"type": "integer", "description": "Band to equalise, default 1."}}, "required": ["raster_layer"]})
def histogram_equalization(raster_layer, band=1):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    ras = _find_layer_by_name(raster_layer)
    if ras is None:
        return {"error": f"Layer '{raster_layer}' not found"}
    # GitHub #162: gdal:contraststretch is not in the QGIS 4.2.2 registry (CI registry diagnostic, PR #175), so this tool could never
    # have run there; the equalisation is computed with numpy instead.
    try:
        from . import raster_numpy
        values, valid, info = raster_numpy.read_bands(ras.source(), [int(band)])
        out = raster_numpy.equalize(values[..., 0], valid[...])
        path = raster_numpy.write_single_band(out, info, nodata=0)
        new_layer = QgsRasterLayer(path, f"{raster_layer}_equalized")
        if not new_layer.isValid():
            return {"error": "The equalised raster could not be loaded."}
        QgsProject.instance().addMapLayer(new_layer)
        return {"success": True, "layer_name": f"{raster_layer}_equalized", "band": int(band),
                "note": "Output is an 8-bit display raster (0 = no data, 1-255 equalised); original values are not preserved."}
    except ValueError as e:
        return {"error": f"histogram_equalization: {e}"}
    except ImportError:
        return {"error": "histogram_equalization needs numpy, which this QGIS does not provide."}
    except Exception as e:
        return {"error": f"histogram_equalization failed: {e}"}


@register_tool("mosaic_rasters", "Merge/mosaic multiple raster layers together.", {"type": "object", "properties": {"raster_layers_list": {"type": "array", "items": {"type": "string"}}}, "required": ["raster_layers_list"]})
def mosaic_rasters(raster_layers_list):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if not isinstance(raster_layers_list, list) or len(raster_layers_list) < 2:
        return {"error": "Provide a list of at least 2 raster layer names"}
    layers = []
    for name in raster_layers_list:
        r = _find_layer_by_name(name)
        if r is None:
            return {"error": f"Layer '{name}' not found"}
        layers.append(r)
    return _run_raster_and_add(
        "gdal:merge",
        {"INPUT": layers, "PCT": False, "SEPARATE": False},
        "mosaic_raster",
    )


@register_tool("band_composite", "Create RGB band composite from single band rasters.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "red_band": {"type": "string"}, "green_band": {"type": "string"}, "blue_band": {"type": "string"}}, "required": ["layer_name", "red_band", "green_band", "blue_band"]})
def band_composite(layer_name, red_band, green_band, blue_band):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    r = _find_layer_by_name(red_band)
    g = _find_layer_by_name(green_band)
    b = _find_layer_by_name(blue_band)
    if any(x is None for x in (r, g, b)):
        return {"error": "One or more band layers not found"}
    return _run_raster_and_add(
        "gdal:merge",
        {"INPUT": [r, g, b], "PCT": False, "SEPARATE": True},
        layer_name,
    )


@register_tool("pan_sharpening", "Pan-sharpen multispectral raster using panchromatic band.", {"type": "object", "properties": {"ms_layer": {"type": "string"}, "pan_layer": {"type": "string"}}, "required": ["ms_layer", "pan_layer"]})
def pan_sharpening(ms_layer, pan_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    ms = _find_layer_by_name(ms_layer)
    pan = _find_layer_by_name(pan_layer)
    if ms is None:
        return {"error": f"Layer '{ms_layer}' not found"}
    if pan is None:
        return {"error": f"Layer '{pan_layer}' not found"}
    return _run_raster_and_add(
        "gdal:pansharp",
        {"SPECTRAL": ms, "PANCHROMATIC": pan},
        f"{ms_layer}_pansharpened",
    )


@register_tool(
    "interpolate_surface",
    "Create a continuous raster surface from scattered point values using spatial interpolation "
    "-- e.g. estimating rainfall/elevation/population density between sample points. 'idw' "
    "(inverse distance weighting, default) is simple and fast; 'tin' (triangulated irregular "
    "network) preserves exact sample values but can look faceted at the triangle edges. Neither "
    "is a true geostatistical kriging model -- use this for a reasonable estimate, not a "
    "statistically rigorous prediction with confidence bounds.",
    {
        "type": "object",
        "properties": {
            "point_layer": {"type": "string"},
            "field": {"type": "string", "description": "Numeric field to interpolate."},
            "method": {"type": "string", "description": "'idw' (default) or 'tin'."},
            "cell_size": {"type": "number", "description": "Output raster cell size in the layer's CRS units. Defaults to a size producing roughly a 250x250 grid."},
        },
        "required": ["point_layer", "field"],
    },
)
def interpolate_surface(point_layer, field, method="idw", cell_size=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    method = (method or "idw").lower()
    if method not in ("idw", "tin"):
        return {"error": "method must be 'idw' or 'tin'."}

    layer = _find_layer_by_name(point_layer)
    if layer is None:
        return {"error": f"Layer '{point_layer}' not found"}
    field_names = [f.name() for f in layer.fields()]
    if field not in field_names:
        return {"error": f"Field '{field}' not found in '{point_layer}'"}
    field_index = field_names.index(field)

    extent = layer.extent()
    if extent.isEmpty():
        return {"error": f"'{point_layer}' has no features to interpolate from."}
    resolved_cell_size = cell_size or max(extent.width(), extent.height()) / 250
    if resolved_cell_size <= 0:
        return {"error": "cell_size must be positive."}

    try:
        # qgis:idwinterpolation / qgis:tininterpolation both take their input as
        # this specially-formatted string (source URI, field index, interpolation
        # type, input type), joined by "::~::" -- not a normal dict param, this
        # is how QGIS's interpolation providers have always taken layer input.
        interpolation_data = f"{layer.source()}::~::{field_index}::~::0::~::0"
        alg = "qgis:idwinterpolation" if method == "idw" else "qgis:tininterpolation"
        params = {
            "INTERPOLATION_DATA": interpolation_data,
            "EXTENT": extent,
            "PIXEL_SIZE": resolved_cell_size,
            "OUTPUT": "TEMPORARY_OUTPUT",
        }
        if method == "idw":
            params["DISTANCE_COEFFICIENT"] = 2
        else:
            params["METHOD"] = 0

        output = processing.run(alg, params)
        out_path = output.get("OUTPUT")
        if not out_path:
            return {"error": "interpolate_surface produced no output."}

        result_name = f"{point_layer}_{field}_{method}_surface"
        raster_layer = QgsRasterLayer(out_path, result_name)
        if not raster_layer.isValid():
            return {"error": "Generated interpolation raster is invalid."}
        QgsProject.instance().addMapLayer(raster_layer)
        try:
            from .output_style import style_continuous_raster
            style_continuous_raster(raster_layer, "surface")
        except Exception:
            pass
        return {"success": True, "layer_name": result_name, "method": method, "cell_size": resolved_cell_size}
    except Exception as e:
        return {"error": f"interpolate_surface failed: {e}"}


@register_tool(
    "elevation_profile",
    "Sample a DEM raster along a line to produce a distance/elevation profile -- e.g. terrain "
    "along a proposed route, or a valley cross-section. Returns distance-along-line and elevation "
    "arrays of equal length; feed them into generate_chart (chart_type='line') for a real "
    "elevation-profile chart.",
    {
        "type": "object",
        "properties": {
            "line_layer": {"type": "string", "description": "Line layer to sample along. Uses the first feature if it has more than one."},
            "dem_layer": {"type": "string", "description": "Raster (DEM) layer to sample elevation from."},
            "num_samples": {"type": "integer", "description": "Number of sample points along the line. Defaults to 100."},
            "dem_vertical_unit": _VERTICAL_UNIT_PARAM,
        },
        "required": ["line_layer", "dem_layer"],
    },
)
def elevation_profile(line_layer, dem_layer, num_samples=100, dem_vertical_unit="m"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if num_samples < 2:
        return {"error": "num_samples must be at least 2."}
    vertical = vertical_unit_factor(dem_vertical_unit)
    if vertical is None:
        return {"error": f"dem_vertical_unit must be 'm', 'ft' or 'us_ft', got {dem_vertical_unit!r}."}

    line = _find_layer_by_name(line_layer)
    dem = _find_layer_by_name(dem_layer)
    if line is None:
        return {"error": f"Layer '{line_layer}' not found"}
    if dem is None:
        return {"error": f"Layer '{dem_layer}' not found"}

    try:
        features = list(line.getFeatures())
        if not features:
            return {"error": f"'{line_layer}' has no features."}
        geom = features[0].geometry()
        if geom.isEmpty():
            return {"error": f"'{line_layer}'s first feature has no geometry."}
        # Audit F18 (#154): the line's coordinates were sampled in the DEM as they are, and the length was planar in the
        # line CRS's own units, so a line and DEM in different CRSs sampled the wrong places and "distance" could be degrees.
        # Sample points are now transformed into the DEM's CRS and distances are metres on the ellipsoid.
        from qgis.core import QgsCoordinateTransform, QgsDistanceArea
        context = QgsProject.instance().transformContext()
        distance_area = QgsDistanceArea()
        distance_area.setSourceCrs(line.crs(), context)
        project_ellipsoid = QgsProject.instance().ellipsoid()
        distance_area.setEllipsoid(project_ellipsoid if project_ellipsoid and project_ellipsoid != "NONE" else "WGS84")
        length = distance_area.measureLength(geom)
        if length <= 0:
            return {"error": f"'{line_layer}'s first feature has zero length."}
        to_dem = None
        if line.crs().isValid() and dem.crs().isValid() and line.crs() != dem.crs():
            to_dem = QgsCoordinateTransform(line.crs(), dem.crs(), context)

        provider = dem.dataProvider()
        distances = []
        elevations = []
        for i in range(num_samples):
            fraction = i / (num_samples - 1)
            # interpolate() works in the line's own units, so the position is a fraction of the line, not of the metres.
            point = geom.interpolate(fraction * geom.length()).asPoint()
            if to_dem is not None:
                point = to_dem.transform(point)
            value, ok = provider.sample(point, 1)
            distances.append(round(fraction * length, 2))
            elevations.append(value * vertical if ok else None)

        valid_count = sum(1 for e in elevations if e is not None)
        if valid_count == 0:
            return {"error": "No valid elevation samples -- the line may not overlap the DEM's extent."}

        return {
            "success": True,
            "line_layer": line_layer,
            "dem_layer": dem_layer,
            "total_length": round(length, 2),
            "distance_unit": "metres (ellipsoidal)",
            "elevation_unit": "metres",
            "elevation_unit_note": (f"Elevations are converted to metres from the DEM's vertical unit ({dem_vertical_unit or 'm'}). The unit is not "
                                    "stored in the raster, so it is whatever was passed; it defaults to metres."),
            "sample_count": num_samples,
            "valid_sample_count": valid_count,
            "distances": distances,
            "elevations": elevations,
        }
    except Exception as e:
        return {"error": f"elevation_profile failed: {e}"}


def _crs_to_wkt(crs_string):
    """Resolves an EPSG string (e.g. 'EPSG:4326') to WKT for GDAL's SetProjection(),
    which -- unlike SetGCPs()/gdal.Warp(dstSRS=...) -- takes WKT/PROJ text, not a bare
    EPSG string."""
    from osgeo import osr
    srs = osr.SpatialReference()
    srs.SetFromUserInput(crs_string)
    return srs.ExportToWkt()


def _solve_3x3(matrix, rhs):
    """Solves a 3x3 linear system via Cramer's rule -- pure Python, no numpy dependency
    (this codebase has none). Returns None for a singular/near-singular system (collinear
    or degenerate control points) rather than raising, so callers can turn it into a clear
    error message instead of a ZeroDivisionError."""
    def det3(m):
        return (
            m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
        )
    d = det3(matrix)
    if abs(d) < 1e-9:
        return None
    solution = []
    for col in range(3):
        replaced = [row[:] for row in matrix]
        for row in range(3):
            replaced[row][col] = rhs[row]
        solution.append(det3(replaced) / d)
    return tuple(solution)


def _fit_affine_transform(control_points):
    """Least-squares 6-parameter affine fit (independent x/y scale, shear, rotation,
    translation) -- QGIS Georeferencer's "Linear" transform. Solves two decoupled 3x3
    normal-equation systems (one for the world-X equation, one for world-Y), since neither
    shares unknowns with the other for this model:
        world_x = a*px + b*py + tx
        world_y = c*px + d*py + ty
    Returns a dict with the fitted coefficients, per-point residuals, and RMSE (the
    standard way to report alignment quality -- QGIS's own Georeferencer panel shows this
    same number), or an "error" key if fewer than 3 points or a degenerate/collinear set
    make the system unsolvable."""
    if len(control_points) < 3:
        return {"error": "At least 3 control points are required for a linear (affine) fit."}
    sxx = sxy = sx = syy = sy = n = 0.0
    sxX = syX = sX = sxY = syY = sY = 0.0
    for cp in control_points:
        x, y, X, Y = float(cp["pixel_x"]), float(cp["pixel_y"]), float(cp["lon"]), float(cp["lat"])
        sxx += x * x
        sxy += x * y
        sx += x
        syy += y * y
        sy += y
        n += 1
        sxX += x * X
        syX += y * X
        sX += X
        sxY += x * Y
        syY += y * Y
        sY += Y
    matrix = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]]
    x_coeffs = _solve_3x3(matrix, [sxX, syX, sX])
    y_coeffs = _solve_3x3(matrix, [sxY, syY, sY])
    if x_coeffs is None or y_coeffs is None:
        return {"error": "Control points are collinear or otherwise degenerate -- cannot fit a linear transform."}
    a, b, tx = x_coeffs
    c, d, ty = y_coeffs
    residuals = []
    for cp in control_points:
        x, y, X, Y = float(cp["pixel_x"]), float(cp["pixel_y"]), float(cp["lon"]), float(cp["lat"])
        px, py = a * x + b * y + tx, c * x + d * y + ty
        residuals.append(math.hypot(px - X, py - Y))
    rmse = math.sqrt(sum(r * r for r in residuals) / len(residuals))
    return {
        "geotransform": (tx, a, b, ty, c, d),  # GDAL SetGeoTransform order: origin_x, px_w, rot_x, origin_y, rot_y, px_h
        "scale_x": math.hypot(a, c), "scale_y": math.hypot(b, d),
        "rmse": rmse, "residuals": residuals,
    }


def _fit_helmert_transform(control_points):
    """Least-squares 4-parameter similarity (Helmert) fit -- QGIS Georeferencer's "Helmert"
    transform: a single uniform scale and rotation, never independent x/y scale or shear.
    Preferred over the 6-parameter affine fit when the source image is known not to be
    distorted (e.g. a clean scan of a rigid printed map) since it can't overfit noise in the
    control points into a spurious shear/skew. Model:
        world_x = a*px - b*py + tx
        world_y = b*px + a*py + ty
    with scale = sqrt(a^2 + b^2) and rotation = atan2(b, a). The closed-form least-squares
    solution below is the standard 2D Helmert fit (mean-centered points, single 2x2 solve --
    see e.g. Umeyama 1991 for the general case this specializes)."""
    if len(control_points) < 3:
        return {"error": "At least 3 control points are required for a Helmert fit."}
    n = len(control_points)
    mean_x = sum(float(cp["pixel_x"]) for cp in control_points) / n
    mean_y = sum(float(cp["pixel_y"]) for cp in control_points) / n
    mean_X = sum(float(cp["lon"]) for cp in control_points) / n
    mean_Y = sum(float(cp["lat"]) for cp in control_points) / n
    num_a = num_b = denom = 0.0
    for cp in control_points:
        dx = float(cp["pixel_x"]) - mean_x
        dy = float(cp["pixel_y"]) - mean_y
        dX = float(cp["lon"]) - mean_X
        dY = float(cp["lat"]) - mean_Y
        num_a += dx * dX + dy * dY
        num_b += dx * dY - dy * dX
        denom += dx * dx + dy * dy
    if abs(denom) < 1e-9:
        # Note: unlike the 6-parameter affine fit above, a Helmert fit (only 4 unknowns)
        # is well-determined even from collinear points -- this only trips when every
        # control point sits at the exact same pixel location.
        return {"error": "Control points are degenerate (all at the same pixel location) -- cannot fit a Helmert transform."}
    a = num_a / denom
    b = num_b / denom
    tx = mean_X - a * mean_x + b * mean_y
    ty = mean_Y - b * mean_x - a * mean_y
    residuals = []
    for cp in control_points:
        x, y, X, Y = float(cp["pixel_x"]), float(cp["pixel_y"]), float(cp["lon"]), float(cp["lat"])
        px, py = a * x - b * y + tx, b * x + a * y + ty
        residuals.append(math.hypot(px - X, py - Y))
    rmse = math.sqrt(sum(r * r for r in residuals) / len(residuals))
    return {
        "geotransform": (tx, a, -b, ty, b, a),
        "scale": math.hypot(a, b), "rotation_degrees": math.degrees(math.atan2(b, a)),
        "rmse": rmse, "residuals": residuals,
    }


@register_tool(
    "georeference_image",
    "Georeference a scanned map or unreferenced image using control points (pixel coordinates "
    "matched to real-world coordinates) -- e.g. aligning a scanned paper map to its true location "
    "and scale on the map. Needs at least 3 non-collinear control points; more (well-distributed "
    "across the image) generally gives a more accurate result than the minimum. Produces a real, "
    "spatially-referenced raster, loads it into the project, and reports the fit's RMSE (in the "
    "target CRS's units) so alignment quality can be judged -- QGIS Georeferencer shows the same "
    "number for the same reason.",
    {
        "type": "object",
        "properties": {
            "image_path": {"type": "string", "description": "Absolute path to the source image (e.g. a scanned map)."},
            "control_points": {
                "type": "array",
                "description": "At least 3 points, e.g. [{\"pixel_x\": 120, \"pixel_y\": 340, \"lon\": 35.93, \"lat\": 31.95}].",
                "items": {
                    "type": "object",
                    "properties": {
                        "pixel_x": {"type": "number"},
                        "pixel_y": {"type": "number"},
                        "lon": {"type": "number"},
                        "lat": {"type": "number"},
                    },
                    "required": ["pixel_x", "pixel_y", "lon", "lat"],
                },
            },
            "output_path": {"type": "string", "description": "Where to save the georeferenced raster (.tif)."},
            "target_crs": {"type": "string", "description": "CRS of the lon/lat control point coordinates. Defaults to EPSG:4326."},
            "transform_type": {
                "type": "string",
                "enum": ["tps", "linear", "helmert"],
                "description": (
                    "'tps' (default): thin-plate-spline rubber-sheeting -- best when the source "
                    "image itself is locally distorted (an uneven scan, a hand-drawn sketch map) "
                    "since it bends to fit every control point exactly. 'linear': a single "
                    "6-parameter affine (independent x/y scale, shear, rotation) fit by least "
                    "squares -- QGIS Georeferencer's 'Linear'. 'helmert': a single 4-parameter "
                    "similarity (one uniform scale, one rotation, no shear) fit by least squares "
                    "-- QGIS Georeferencer's 'Helmert', the right choice for a clean scan of a "
                    "rigid printed map where the true transform can't have shear."
                ),
            },
        },
        "required": ["image_path", "control_points", "output_path"],
    },
)
def georeference_image(image_path, control_points, output_path, target_crs="EPSG:4326", transform_type="tps"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if not os.path.exists(image_path):
        return {"error": f"File not found: {image_path}"}
    if len(control_points) < 3:
        return {"error": "At least 3 control points are required."}
    if transform_type not in ("tps", "linear", "helmert"):
        return {"error": f"Unknown transform_type '{transform_type}' -- expected 'tps', 'linear', or 'helmert'."}

    try:
        from osgeo import gdal
    except ImportError:
        return {"error": "GDAL Python bindings (osgeo) not available in this environment."}

    try:
        for i, cp in enumerate(control_points):
            try:
                float(cp["lon"]), float(cp["lat"]), float(cp["pixel_x"]), float(cp["pixel_y"])
            except (KeyError, TypeError, ValueError) as e:
                return {"error": f"Control point {i} is invalid: {e}"}

        src_ds = gdal.Open(image_path)
        if src_ds is None:
            return {"error": f"Could not open '{image_path}' as an image (unsupported or corrupt format)."}

        fit = None
        if transform_type == "tps":
            gcps = [gdal.GCP(float(cp["lon"]), float(cp["lat"]), 0, float(cp["pixel_x"]), float(cp["pixel_y"]))
                    for cp in control_points]
            src_ds.SetGCPs(gcps, target_crs)
            warp_options = gdal.WarpOptions(dstSRS=target_crs, tps=True, resampleAlg="bilinear", format="GTiff")
            result_ds = gdal.Warp(output_path, src_ds, options=warp_options)
            src_ds = None
            if result_ds is None:
                return {"error": "gdal.Warp failed to produce output -- check control points are correct and not collinear."}
            result_ds = None
        else:
            # linear/helmert: fit our own closed-form transform (GDAL has no built-in
            # Helmert/similarity fit, and relying on gdal.Warp's automatic polynomial-order
            # selection for "linear" would silently change behavior across GDAL versions) --
            # then set it directly as the output's geotransform rather than warping.
            fit = _fit_affine_transform(control_points) if transform_type == "linear" else _fit_helmert_transform(control_points)
            if "error" in fit:
                src_ds = None
                return fit
            driver = gdal.GetDriverByName("GTiff")
            result_ds = driver.CreateCopy(output_path, src_ds)
            src_ds = None
            if result_ds is None:
                return {"error": "Could not write output raster -- check output_path is writable."}
            result_ds.SetGeoTransform(fit["geotransform"])
            result_ds.SetProjection(_crs_to_wkt(target_crs))
            result_ds = None

        if not os.path.exists(output_path):
            return {"error": "Georeferencing completed but no output file was written."}

        layer = QgsRasterLayer(output_path, os.path.splitext(os.path.basename(output_path))[0])
        if not layer.isValid():
            return {"error": f"Georeferenced file was created at '{output_path}' but QGIS could not load it as a valid raster."}
        QgsProject.instance().addMapLayer(layer)

        result = {
            "success": True,
            "output_path": output_path,
            "layer_name": layer.name(),
            "control_point_count": len(control_points),
            "transform_type": transform_type,
        }
        if fit is not None:
            result["rmse"] = round(fit["rmse"], 6)
            if "scale" in fit:
                result["scale"] = round(fit["scale"], 6)
                result["rotation_degrees"] = round(fit["rotation_degrees"], 3)
            else:
                result["scale_x"] = round(fit["scale_x"], 6)
                result["scale_y"] = round(fit["scale_y"], 6)
        return result
    except Exception as e:
        return {"error": f"georeference_image failed: {e}"}


# fetch_worldpop_population names its output layers '<ISO3>_population_<year>' (plus '_area' when clipped; see
# add_worldpop_population_layer_main_thread_phase in humanitarian_tools.py). WorldPop's own file name is '<iso3>_ppp_<year>',
# which is what a layer loaded from the cached download is called (rc11 smoke test S4: 'yem_ppp_2020' did not match, so
# apply_raster_stretch replaced the population ramp with an opaque grey stretch that blacked out the country).
_WORLDPOP_LAYER_NAME_RE = re.compile(r"^[A-Za-z]{3}_(?:population|ppp)_(\d{4})(?:_area)?$", re.IGNORECASE)


def _describe_population_raster(layer_name):
    """Best-effort provenance for a population raster, derived only from what's
    actually knowable -- never guessed. When a layer's name matches
    fetch_worldpop_population's own naming convention exactly, we can honestly
    say it came from WorldPop and which year it represents. Any other raster
    (manually loaded, renamed, or from a different provider) gets its own layer
    name as the source label and an unknown reference year -- claiming
    'WorldPop' for a raster that might not be WorldPop data would itself be the
    kind of overclaim point 9 of
    docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md exists to prevent."""
    match = _WORLDPOP_LAYER_NAME_RE.match(layer_name or "")
    if match:
        return "WorldPop", match.group(1)
    return layer_name, None


_POPULATION_UNITS = ("people_per_cell", "people_per_km2")
_DENSITY_NAME_RE = re.compile(r"(density|[_\s-]pd[_\s-]|per[_\s-]?km|people[_\s-]per[_\s-]sq|popden)", re.I)


def population_unit_problem(layer_name, raster_unit):
    """An error string when the unit is unknown, or when the layer's NAME says it is a density raster but the unit was left at
    people_per_cell (summing densities as if they were counts overstates the population by the cell area in km2). Pure. Audit F24 (#160):
    "raster units (people/cell vs density) are not validated". A raster carries no unit, so the name is the only evidence there is; a name
    that does not look like density passes, and the unit used is always stated in the result."""
    if raster_unit not in _POPULATION_UNITS:
        return f"raster_unit must be one of {list(_POPULATION_UNITS)}, got {raster_unit!r}."
    if raster_unit == "people_per_cell" and _DENSITY_NAME_RE.search(layer_name or ""):
        return (f"'{layer_name}' looks like a population DENSITY raster (people per km2), but raster_unit is people_per_cell, so its cells "
                "would be summed as head-counts. Pass raster_unit='people_per_km2' if it is a density, or 'people_per_cell' "
                "explicitly if the name is misleading and the cells are counts.")
    return None


def _cell_area_km2(raster):
    """Area of one cell in km2 at the raster's centre (ellipsoidal when the raster is geographic). Needs QGIS."""
    from qgis.core import QgsDistanceArea, QgsGeometry, QgsRectangle
    ext = raster.extent()
    cx, cy = (ext.xMinimum() + ext.xMaximum()) / 2.0, (ext.yMinimum() + ext.yMaximum()) / 2.0
    dx, dy = raster.rasterUnitsPerPixelX() / 2.0, raster.rasterUnitsPerPixelY() / 2.0
    cell = QgsGeometry.fromRect(QgsRectangle(cx - dx, cy - dy, cx + dx, cy + dy))
    area = QgsDistanceArea()
    area.setSourceCrs(raster.crs(), QgsProject.instance().transformContext())
    ellipsoid = QgsProject.instance().ellipsoid()
    area.setEllipsoid(ellipsoid if ellipsoid and ellipsoid != "NONE" else "WGS84")
    return area.measureArea(cell) / 1e6


@register_tool(
    "estimate_population_exposure",
    "Sum population within each polygon of a vector layer, using an already-loaded population "
    "raster (e.g. from fetch_worldpop_population) -- e.g. 'how many people live within 5km of "
    "this facility' (combine with buffer_analysis first to build the area), or 'population per "
    "district' (pass admin boundaries directly). Does not modify the vector layer; returns one total per zone (keyed by "
    "name, made unique when names repeat) and says whether zones overlap. "
    "Returns an ESTIMATE derived from a gridded population raster, not a verified count of people "
    "actually present -- report results as 'estimated population within <area>', never as a "
    "confirmed or affected-population figure, unless field data corroborates it.",
    {
        "type": "object",
        "properties": {
            "population_raster_layer": {"type": "string", "description": "A population-per-pixel raster layer (e.g. from fetch_worldpop_population)."},
            "area_layer": {"type": "string", "description": "Polygon layer to sum population within, one total per feature."},
            "raster_unit": {"type": "string", "description": "'people_per_cell' (default; counts per cell, e.g. WorldPop ppp) or 'people_per_km2' (a density raster: each cell is multiplied by its area before summing). A raster does not carry its unit; a layer named like a density raster is refused unless this is set."},
            "output_layer_name": {"type": "string", "description": "Optional: also add a NEW polygon layer with this name holding each zone's estimated population (field pop_estimate), styled in exposure classes. The area layer itself is never changed."},
        },
        "required": ["population_raster_layer", "area_layer"],
    },
)
def estimate_population_exposure(population_raster_layer, area_layer, output_layer_name=None, raster_unit="people_per_cell"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    unit_problem = population_unit_problem(population_raster_layer, raster_unit)
    if unit_problem:
        return {"error": unit_problem}
    raster = _find_layer_by_name(population_raster_layer)
    vector = _find_layer_by_name(area_layer)
    if raster is None:
        return {"error": f"Layer '{population_raster_layer}' not found"}
    if vector is None:
        return {"error": f"Layer '{area_layer}' not found"}
    if vector.geometryType() != QgsWkbTypes.GeometryType.PolygonGeometry:
        return {"error": "area_layer must be a polygon layer."}

    try:
        # Audit F23/F24 (#159, #160): this used to run QgsZonalStatistics ON the caller's layer (adding pop_* fields; a
        # repeat run could add a suffixed field while the old one was read), keyed the answer by the first attribute (so
        # duplicate or NULL names overwrote each other and the total undercounted), and summed overlapping zones silently.
        # Now: statistics are computed on a detached copy, every zone is reported under its own feature id, and the
        # overlap rule is stated. Decision (owner, 2026-10-04): totals are PER ZONE; total_population is their plain sum.
        zone_sums = _zonal_sums_detached(raster, vector)
        if zone_sums is None:
            return {"error": "Zonal statistics produced no population field -- check area_layer overlaps the raster."}
        unit_note = "Cells are read as people per cell."
        if raster_unit == "people_per_km2":
            cell_km2 = _cell_area_km2(raster)
            zone_sums = {fid: (None if v is None else v * cell_km2) for fid, v in zone_sums.items()}
            unit_note = (f"Cells are read as people per km2 and multiplied by the cell area ({cell_km2:.6f} km2, measured at the raster's centre; "
                         "for a geographic raster the true cell area changes with latitude, so a large north-south extent is approximate).")

        name_field = vector.fields()[0].name() if vector.fields().count() > 0 else None
        zones = []
        for feat in vector.getFeatures():
            label = feat.attribute(name_field) if name_field else None
            zones.append({"feature_id": feat.id(), "label": None if label in (None, "") else str(label),
                          "population": zone_sums.get(feat.id())})
        keys = unique_zone_keys([(z["feature_id"], z["label"]) for z in zones])
        totals = {keys[z["feature_id"]]: z["population"] for z in zones}
        zones_without_value = [keys[z["feature_id"]] for z in zones if z["population"] is None]

        total_population = sum(v for v in totals.values() if v is not None)
        overlap_pairs = _overlapping_zone_count(vector)
        pop_source, pop_reference_year = _describe_population_raster(population_raster_layer)
        output_layer_info = _add_exposure_layer(vector, zones, keys, output_layer_name) if output_layer_name else {}

        return {
            **output_layer_info,
            "success": True,
            "area_layer": area_layer,
            "population_raster_layer": population_raster_layer,
            "totals": totals,
            "zones": zones,
            "total_population": total_population,
            "raster_unit": raster_unit,
            "raster_unit_note": unit_note,
            "zones_without_value": zones_without_value,
            "overlap_rule": ("Each zone is summed on its own. total_population is the plain sum of the zones, so people "
                             "inside two overlapping zones are counted in both."),
            "overlapping_zone_pairs": overlap_pairs,
            # Point 9 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: a
            # zonal sum of a gridded population raster is an ESTIMATE of exposure,
            # not a verified count of people actually affected. These fields make
            # that explicit (and give downstream reporting a real, machine-readable
            # basis for saying so) instead of letting a bare 'total_population'
            # number get reported as a confirmed affected-population figure.
            "pop_exposed_est": total_population,
            "pop_source": pop_source,
            "pop_reference_year": pop_reference_year,
            "analysis_resolution": {
                "pixel_width": raster.rasterUnitsPerPixelX(),
                "pixel_height": raster.rasterUnitsPerPixelY(),
                "crs": raster.crs().authid() if raster.crs() else None,
            },
            "confidence": "estimate (gridded population raster; not field-verified)",
            **_hull_area_note(area_layer),
            **_service_area_reach_figures(raster, area_layer),
        }
    except Exception as e:
        return {"error": f"estimate_population_exposure failed: {e}"}


EXPOSURE_LAYER_MARK = "estimate_population_exposure"


def _add_exposure_layer(vector, zones, keys, layer_name):
    """A NEW polygon layer (geometry copy + label + pop_estimate) styled in exposure classes, so the result can be seen on the map without
    touching the caller's layer (HX1b). A layer of the same name that this tool made earlier is replaced; one the user made is not: the
    new layer gets a numeric suffix instead. Returns result entries, or a warning entry when the layer could not be made."""
    try:
        from qgis.core import QgsFeature, QgsVectorLayer, QgsField
        from qgis.PyQt.QtCore import QVariant
        from .humanitarian_style import style_result_field
        project = QgsProject.instance()
        name = str(layer_name)
        for existing in project.mapLayersByName(name):
            if existing.customProperty("cartogen_created_by") == EXPOSURE_LAYER_MARK:
                project.removeMapLayer(existing.id())
        if project.mapLayersByName(name):
            n = 2
            while project.mapLayersByName(f"{name} ({n})"):
                n += 1
            name = f"{name} ({n})"
        layer = QgsVectorLayer(f"Polygon?crs={vector.crs().authid()}", name, "memory")
        provider = layer.dataProvider()
        provider.addAttributes([QgsField("zone", QVariant.String), QgsField("feature_id", QVariant.LongLong),
                                QgsField("pop_estimate", QVariant.Double)])
        layer.updateFields()
        by_id = {z["feature_id"]: z for z in zones}
        feats = []
        for src in vector.getFeatures():
            z = by_id.get(src.id())
            if z is None:
                continue
            f = QgsFeature(layer.fields())
            f.setGeometry(src.geometry())
            f.setAttributes([keys[src.id()], src.id(), z["population"]])
            feats.append(f)
        provider.addFeatures(feats)
        layer.updateExtents()
        layer.setCustomProperty("cartogen_created_by", EXPOSURE_LAYER_MARK)
        project.addMapLayer(layer)
        style = style_result_field(layer, "exposure", "pop_estimate")
        out = {"output_layer": name, "output_layer_note": "A new layer; the area layer was not changed. Units with no population value are not drawn."}
        if "error" in style:
            out["output_layer_style_warning"] = style["error"]
        return out
    except Exception as e:
        return {"output_layer_warning": f"The result layer could not be added: {e}"}


def unique_zone_keys(zones):
    """{feature_id: unique display key} for [(feature_id, label-or-None), ...]. Pure.

    A label that is unique is used as is; a duplicate, empty or NULL label becomes '<label> [#<id>]' / 'feature <id>', so
    two zones can never share a key and overwrite each other (#159)."""
    counts = {}
    for _fid, label in zones:
        if label:
            counts[label] = counts.get(label, 0) + 1
    keys = {}
    for fid, label in zones:
        if not label:
            keys[fid] = f"feature {fid}"
        elif counts[label] > 1:
            keys[fid] = f"{label} [#{fid}]"
        else:
            keys[fid] = label
    return keys


def _zonal_sums_detached(raster, polygon_layer):
    """{feature id of `polygon_layer`: raster sum or None} computed on a geometry-only copy, so the caller's layer gets no
    new fields and a repeat run cannot read a stale one (#160). None when the statistics could not be computed at all."""
    from qgis.analysis import QgsZonalStatistics
    from qgis.core import QgsFeature, QgsVectorLayer
    stat_enum = getattr(QgsZonalStatistics, "Statistic", QgsZonalStatistics)
    sum_flag = getattr(stat_enum, "Sum", None)
    if sum_flag is None or polygon_layer is None or polygon_layer.featureCount() == 0:
        return None
    scratch = QgsVectorLayer(f"Polygon?crs={polygon_layer.crs().authid()}", "zonal_scratch", "memory")
    if not scratch.isValid():
        return None
    original_ids, copies = [], []
    for feat in polygon_layer.getFeatures():
        copy = QgsFeature()
        copy.setGeometry(feat.geometry())
        copies.append(copy)
        original_ids.append(feat.id())
    scratch.dataProvider().addFeatures(copies)
    QgsZonalStatistics(scratch, raster, "pop_", 1, sum_flag).calculateStatistics(None)
    if scratch.fields().indexFromName("pop_sum") < 0:
        return None
    # A memory layer numbers its features in insertion order, which is how the originals are matched back.
    values = [f.attribute("pop_sum") for f in sorted(scratch.getFeatures(), key=lambda f: f.id())]
    return {fid: (None if v is None or v != v else v) for fid, v in zip(original_ids, values)}


def _zonal_population_total(raster, polygon_layer):
    """Sum a population raster inside every polygon of `polygon_layer`. Returns the total, or None when the sum could not
    be computed. Works on a detached copy: the layer is not modified."""
    sums = _zonal_sums_detached(raster, polygon_layer)
    if sums is None:
        return None
    return sum(v for v in sums.values() if v is not None)


def _overlapping_zone_count(polygon_layer, limit=2000):
    """How many pairs of zones overlap (positive-area intersection); 0 when there are more than `limit` zones, which are
    not checked. Needs QGIS."""
    try:
        from qgis.core import QgsSpatialIndex
        feats = {f.id(): f for f in polygon_layer.getFeatures()}
        if len(feats) > limit:
            return 0
        index = QgsSpatialIndex(polygon_layer.getFeatures())
        pairs = 0
        for fid, feat in feats.items():
            geom = feat.geometry()
            for other in index.intersects(geom.boundingBox()):
                if other > fid and geom.intersection(feats[other].geometry()).area() > 0:
                    pairs += 1
        return pairs
    except Exception:
        return 0


def _service_area_reach_figures(raster, area_layer):
    """#123 (rc11 smoke F09): "population within the service area" went to estimate_population_exposure on the convex hull
    and came back as ONE number (815,039), the upper bound, as the headline. When the area is a calculate_service_area hull
    and its reached-roads sibling layer is in the project, also report the concave-hull and road-buffer figures in the same
    shape as population_access_gap's reach_figures, with the concave hull as the headline and the convex hull labelled an
    upper bound. Best-effort: any failure just leaves the single (already labelled) figure. Needs real QGIS; not unit-tested
    offline beyond the name match."""
    match = _SERVICE_AREA_HULL_RE.search(str(area_layer or ""))
    if not match or not QGIS_AVAILABLE:
        return {}
    try:
        from . import logistics_tools as lt
        lines = _find_layer_by_name(str(area_layer).replace("_service_area_", "_service_area_lines_"))
        hull = _find_layer_by_name(area_layer)
        if lines is None or hull is None:
            return {}
        convex = _zonal_population_total(raster, hull)
        figures = []
        builders = (
            ("concave_hull", lambda: lt._concave_reach_polygon([lines], lt.CONCAVE_HULL_RATIO, "tmp_concave")),
            ("road_buffer", lambda: lt._road_reach_polygon([lines], 500, "tmp_road_buffer")),
        )
        for method, build in builders:
            try:
                total = _zonal_population_total(raster, build())
            except Exception:
                total = None
            if total is not None:
                figures.append({"method": method, "label": lt.REACH_LABELS[method], "population": total,
                                "is_upper_bound": False, "is_headline": method == "concave_hull"})
        if convex is not None:
            figures.append({"method": "convex_hull", "label": lt.REACH_LABELS["convex_hull"], "population": convex,
                            "is_upper_bound": True, "is_headline": False})
        if len(figures) < 2:
            return {}
        if not any(f["is_headline"] for f in figures):
            figures[0]["is_headline"] = True
        headline = next(f for f in figures if f["is_headline"])
        return {
            "reach_figures": figures,
            "headline_population": headline["population"],
            "figure_note": ("Report the headline with its range, never the convex-hull figure alone: "
                            + "; ".join(f"{f['label']}: {f['population']:,.0f}" for f in figures) + "."),
        }
    except Exception:
        return {}


_SERVICE_AREA_HULL_RE = re.compile(r"_service_area_\d+$")


def _hull_area_note(area_layer):
    """calculate_service_area's polygon (`<facility>_service_area_<n>`) is the CONVEX HULL of the reached roads, which also
    contains land and people that cannot be reached in the time. A population summed inside it is an upper bound, and the
    rc10 smoke test reported 815,039 as the catchment population with no such label (F09's three-figure range exists only
    in population_access_gap). Pure."""
    if _SERVICE_AREA_HULL_RE.search(str(area_layer or "")):
        return {"figure_kind": "upper_bound_convex_hull",
                "geometry_note": ("This area is the convex hull of the reachable roads, so the total is an UPPER BOUND on the "
                                  "people reachable in that time. Say so when reporting it; population_access_gap gives a "
                                  "concave-hull headline with a road-buffer and a convex-hull range.")}
    return {}


# Vegetation/water index layers are bounded roughly -1..1 and centered on 0 --
# a diverging ramp around that center is the standard cartographic choice for
# them, the same "match the ramp family to the data's actual shape" principle
# styling_tools.py already applies for vector choropleths (sequential vs.
# diverging vs. qualitative). Matched against the layer NAME (not the data
# itself, unlike styling_tools.py's distribution-based auto-selection) since
# a raster has no attribute table to inspect -- calculate_ndvi/ndwi/ndre's own
# fixed output names ('NDVI'/'NDWI'/'NDRE') make this a reliable signal.
_INDEX_RAMPS = {
    # BrBG (brown-blue-green), not RdYlGn (red-yellow-green) -- RdYlGn is a red-green
    # diverging ramp, the specific combination deuteranopia/protanopia (~8% of males)
    # cannot distinguish, making severe drought vs. lush vegetation look indistinguishable.
    # BrBG is a ColorBrewer diverging ramp built for CVD accessibility while keeping the
    # same "low index = one extreme, high index = the other, centered on 0" cartographic
    # meaning NDVI/NDRE need.
    "ndvi": "BrBG",
    "ndwi": "RdBu",
    "ndre": "BrBG",
}


def _auto_raster_style(layer_name, mode):
    """Pure Python, no QGIS needed -- resolves apply_raster_stretch's 'mode'
    argument ('auto'/'stretch'/'color_ramp') to a concrete mode plus a default
    color ramp name (or None for grayscale stretch mode). Separated out so
    this decision logic is directly unit-testable without a QGIS install,
    mirroring _classify_values/_compute_normalized_weights above and in
    styling_tools.py. Returns (mode, default_ramp_or_None), or (None, None)
    if mode itself is invalid."""
    mode_l = (mode or "auto").lower()
    if mode_l not in ("auto", "stretch", "color_ramp"):
        return None, None
    key = (layer_name or "").strip().lower()
    matched_ramp = None
    for index_key, ramp in _INDEX_RAMPS.items():
        if index_key in key:
            matched_ramp = ramp
            break
    if mode_l == "auto":
        return ("color_ramp", matched_ramp) if matched_ramp else ("stretch", None)
    if mode_l == "color_ramp":
        return "color_ramp", matched_ramp
    return "stretch", None


@register_tool(
    "apply_raster_stretch",
    "Apply a min/max contrast stretch or pseudocolor ramp to a single-band raster layer -- every "
    "raster-producing tool in this plugin (calculate_ndvi/calculate_ndwi/calculate_ndre, "
    "calculate_raster_change_detection, hillshade/slope_analysis/aspect_analysis, "
    "interpolate_surface, hotspot_analysis, weighted_overlay_analysis, etc.) lands on the canvas "
    "with QGIS's raw, unstretched single-band default rendering, which usually looks flat grey and "
    "unreadable until this is applied -- this plugin's vector styling toolkit (apply_graduated_style, "
    "apply_categorized_style, apply_heatmap_style) has no raster equivalent, this tool is it. Two "
    "modes: 'color_ramp' applies a QgsSingleBandPseudoColorRenderer with a named QGIS color ramp "
    "(e.g. a diverging ramp centered on 0 for a -1..1 vegetation/water index); 'stretch' applies a "
    "grayscale linear min/max contrast stretch via QgsSingleBandGrayRenderer, the usual fix for a "
    "flat-looking DEM/hillshade/panchromatic band. 'auto' (default) picks 'color_ramp' with a "
    "sensible diverging ramp for layers whose name contains 'ndvi'/'ndwi'/'ndre', 'stretch' "
    "otherwise. Min/max values default to the band's actual computed data min/max unless overridden.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "mode": {
                "type": "string",
                "description": "'auto' (default), 'stretch' (grayscale contrast stretch), or "
                "'color_ramp' (pseudocolor). 'auto' picks 'color_ramp' for layers named like "
                "NDVI/NDWI/NDRE, 'stretch' otherwise.",
            },
            "color_ramp": {
                "type": "string",
                "description": "QGIS color ramp name (e.g. 'Viridis', 'RdYlGn', 'RdBu', 'Spectral'). "
                "Only used in 'color_ramp' mode. Defaults to a diverging ramp for known vegetation/"
                "water indices, or 'Viridis' otherwise.",
            },
            "band": {"type": "integer", "description": "Raster band number to style. Defaults to 1."},
            "min_value": {"type": "number", "description": "Optional. Overrides the auto-computed stretch/ramp minimum."},
            "max_value": {"type": "number", "description": "Optional. Overrides the auto-computed stretch/ramp maximum."},
            "keep_population_ramp": {"type": "boolean", "description": "Default true: a WorldPop population layer keeps the plugin's own ramp (empty cells transparent, unit on the legend) because a generic stretch over a whole country is unreadable. Pass false only if the user explicitly asked for a different look."},
        },
        "required": ["layer_name"],
    },
)
def apply_raster_stretch(layer_name, mode="auto", color_ramp=None, band=1, min_value=None, max_value=None,
                         keep_population_ramp=True):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    # rc10 smoke test: after fetching the Yemen WorldPop raster the model called this tool, replacing the population ramp with
    # an opaque Viridis stretch (0.000152..595) that painted the whole country dark purple over the basemap and every analysis
    # layer, with no unit on the legend. Keep the population look unless the caller explicitly opts out.
    if keep_population_ramp and _describe_population_raster(layer_name)[1] is not None:
        pop_layer = _find_layer_by_name(layer_name)
        if pop_layer is not None:
            from .output_style import style_continuous_raster
            if style_continuous_raster(pop_layer, "population"):
                return {"success": True, "layer_name": layer_name, "mode": "population_ramp", "band": band,
                        "note": ("WorldPop population layers keep the plugin's population ramp (empty cells transparent, "
                                 "people/cell on the legend). Pass keep_population_ramp=false to apply a generic stretch.")}

    resolved_mode, default_ramp = _auto_raster_style(layer_name, mode)
    if resolved_mode is None:
        return {"error": "mode must be 'auto', 'stretch', or 'color_ramp'."}
    if not isinstance(band, int) or band < 1:
        return {"error": "band must be a positive integer."}
    if min_value is not None and max_value is not None and min_value >= max_value:
        return {"error": "min_value must be less than max_value."}

    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    try:
        band_count = layer.bandCount()
        if band > band_count:
            return {"error": f"'{layer_name}' has {band_count} band(s); band {band} does not exist."}

        # QGIS-005, 2026-09-14 audit: _RBS_MIN/_RBS_MAX/_STRETCH_MINMAX/_RAMP_INTERPOLATED/
        # _COLOR_RAMP_SHADER_ITEM were only ever None-safe by this function's own broad
        # except Exception below (e.g. `_RBS_MIN | _RBS_MAX` on two Nones raises TypeError,
        # caught generically) -- not by an explicit check, so a genuine resolution failure
        # would surface as a confusing raw Python exception message instead of a clear one,
        # same class of gap QGIS-004 fixed for _VFW_NO_ERROR. Today inert (every one of these
        # resolves fine on both QGIS 3.x/4.x) -- this closes a correctness gap conditional on
        # future QGIS API drift. Checked here, after the cheaper band-count validation above,
        # not before it -- ordering matters for which error message a bad call actually sees.
        if None in (_RBS_MIN, _RBS_MAX, _STRETCH_MINMAX, _RAMP_INTERPOLATED, _COLOR_RAMP_SHADER_ITEM):
            return {"error": "Could not resolve one or more required QGIS raster-styling enums in this QGIS version."}

        provider = layer.dataProvider()
        computed_min = computed_max = None
        if min_value is None or max_value is None:
            stats = provider.bandStatistics(band, _RBS_MIN | _RBS_MAX)
            computed_min, computed_max = stats.minimumValue, stats.maximumValue
        resolved_min = min_value if min_value is not None else computed_min
        resolved_max = max_value if max_value is not None else computed_max
        if resolved_min is None or resolved_max is None:
            return {"error": f"Could not compute band statistics for '{layer_name}' -- pass min_value/max_value explicitly."}
        if resolved_min >= resolved_max:
            return {"error": f"Band {band} of '{layer_name}' has no data range to stretch (min == max) -- pass min_value/max_value explicitly."}

        result = {
            "success": True,
            "layer_name": layer_name,
            "mode": resolved_mode,
            "band": band,
            "min_value": resolved_min,
            "max_value": resolved_max,
        }

        if resolved_mode == "stretch":
            renderer = QgsSingleBandGrayRenderer(provider, band)
            enhancement = QgsContrastEnhancement(provider.dataType(band))
            enhancement.setMinimumValue(resolved_min)
            enhancement.setMaximumValue(resolved_max)
            enhancement.setContrastEnhancementAlgorithm(_STRETCH_MINMAX)
            renderer.setContrastEnhancement(enhancement)
            layer.setRenderer(renderer)
        else:
            ramp_name = color_ramp or default_ramp or "Viridis"
            ramp = QgsStyle.defaultStyle().colorRamp(ramp_name)
            if ramp is None:
                return {"error": f"'{ramp_name}' is not a known QGIS color ramp name."}

            shader = QgsColorRampShader(resolved_min, resolved_max)
            shader.setColorRampType(_RAMP_INTERPOLATED)
            n_steps = 10
            items = []
            for i in range(n_steps + 1):
                fraction = i / n_steps
                value = resolved_min + fraction * (resolved_max - resolved_min)
                items.append(_COLOR_RAMP_SHADER_ITEM(value, ramp.color(fraction), f"{value:.2f}"))
            shader.setColorRampItemList(items)
            raster_shader = QgsRasterShader()
            raster_shader.setRasterShaderFunction(shader)
            renderer = QgsSingleBandPseudoColorRenderer(provider, band, raster_shader)
            from .output_style import set_renderer_range
            set_renderer_range(renderer, resolved_min, resolved_max)
            layer.setRenderer(renderer)
            result["color_ramp"] = ramp_name

        layer.triggerRepaint()
        from .humanitarian_style import refresh_legend
        refresh_legend(layer)
        return result
    except Exception as e:
        return {"error": f"apply_raster_stretch failed: {e}"}
