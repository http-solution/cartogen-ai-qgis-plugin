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
        QgsProject, QgsRasterLayer, QgsWkbTypes, QgsSingleBandGrayRenderer,
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
    {"type": "object", "properties": {"red_layer": {"type": "string"}, "nir_layer": {"type": "string"}}, "required": ["red_layer", "nir_layer"]},
)
def calculate_ndvi(red_layer, nir_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    red = _find_layer_by_name(red_layer)
    nir = _find_layer_by_name(nir_layer)
    if red is None:
        return {"error": f"Layer '{red_layer}' not found"}
    if nir is None:
        return {"error": f"Layer '{nir_layer}' not found"}
    return _run_raster_and_add(
        "gdal:rastercalculator",
        {
            "INPUT_A": nir,
            "BAND_A": 1,
            "INPUT_B": red,
            "BAND_B": 1,
            "FORMULA": "(A.astype(float)-B)/(A.astype(float)+B)",
            "NO_DATA": None,
            "RTYPE": 5,
        },
        "NDVI",
    )


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
    {"type": "object", "properties": {"green_layer": {"type": "string"}, "nir_layer": {"type": "string"}}, "required": ["green_layer", "nir_layer"]},
)
def calculate_ndwi(green_layer, nir_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    green = _find_layer_by_name(green_layer)
    nir = _find_layer_by_name(nir_layer)
    if green is None:
        return {"error": f"Layer '{green_layer}' not found"}
    if nir is None:
        return {"error": f"Layer '{nir_layer}' not found"}
    return _run_raster_and_add(
        "gdal:rastercalculator",
        {
            "INPUT_A": green,
            "BAND_A": 1,
            "INPUT_B": nir,
            "BAND_B": 1,
            "FORMULA": "(A.astype(float)-B)/(A.astype(float)+B)",
            "NO_DATA": None,
            "RTYPE": 5,
        },
        "NDWI",
    )


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
        },
        "required": ["raster_layers", "weights"],
    },
)
def weighted_overlay_analysis(raster_layers, weights):
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

    crs_set = {layer.crs().authid() for layer in layers}
    if len(crs_set) > 1:
        return {
            "error": f"Input rasters have mismatched CRS ({sorted(crs_set)}) -- reproject them to a "
            "common CRS first so pixels align; combining unaligned rasters would produce a meaningless result."
        }

    params = {"NO_DATA": None, "RTYPE": 5}
    formula_terms = []
    for letter, layer, w in zip(_OVERLAY_LETTERS, layers, normalized):
        params[f"INPUT_{letter}"] = layer
        params[f"BAND_{letter}"] = 1
        formula_terms.append(f"{letter}.astype(float)*{w}")
    params["FORMULA"] = "+".join(formula_terms)

    res = _run_raster_and_add("gdal:rastercalculator", params, "weighted_overlay")
    if isinstance(res, dict) and res.get("success"):
        res["normalized_weights"] = dict(zip(raster_layers, [round(w, 4) for w in normalized]))
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
    {"type": "object", "properties": {"red_edge_layer": {"type": "string"}, "nir_layer": {"type": "string"}}, "required": ["red_edge_layer", "nir_layer"]},
)
def calculate_ndre(red_edge_layer, nir_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    re = _find_layer_by_name(red_edge_layer)
    nir = _find_layer_by_name(nir_layer)
    if re is None:
        return {"error": f"Layer '{red_edge_layer}' not found"}
    if nir is None:
        return {"error": f"Layer '{nir_layer}' not found"}
    return _run_raster_and_add(
        "gdal:rastercalculator",
        {
            "INPUT_A": nir,
            "BAND_A": 1,
            "INPUT_B": re,
            "BAND_B": 1,
            "FORMULA": "(A.astype(float)-B)/(A.astype(float)+B)",
            "NO_DATA": None,
            "RTYPE": 5,
        },
        "NDRE",
    )


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
        if crs is None or not crs.isGeographic():
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



@register_tool("slope_analysis", "Calculate slope map from DEM layer.", {"type": "object", "properties": {"dem_layer": {"type": "string"}}, "required": ["dem_layer"]})
def slope_analysis(dem_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    dem = _find_layer_by_name(dem_layer)
    if dem is None:
        return {"error": f"Layer '{dem_layer}' not found"}
    return _run_raster_and_add(
        "native:slope",
        {"INPUT": dem, "Z_FACTOR": _geographic_z_factor(dem)},
        f"{dem_layer}_slope",
    )


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
        params = {
            "INPUT_RASTER": ras,
            "RASTER_BAND": 1,
            "INPUT_VECTOR": vec,
            "COLUMN_PREFIX": "zs_",
            "STATISTICS": [2, 3, 4],
        }
        processing.run("qgis:zonalstatistics", params)
        return {"success": True, "message": f"Zonal statistics added to '{vector_layer}'"}
    except Exception as e:
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


@register_tool("unsupervised_classification", "Unsupervised K-Means raster classification.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "num_classes": {"type": "integer"}}, "required": ["layer_name", "num_classes"]})
def unsupervised_classification(layer_name, num_classes):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    ras = _find_layer_by_name(layer_name)
    if ras is None:
        return {"error": f"Layer '{layer_name}' not found"}
    return _run_raster_and_add(
        "saga:kmeansclassificationforgrid",
        {
            "GRIDS": [ras],
            "METHOD": 0,
            "CLUSTERS": num_classes,
            "MAXITER": 10,
            "NORMALISE": False,
        },
        f"{layer_name}_classified",
        output_key="CLUSTER",
    )


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


@register_tool("histogram_equalization", "Enhance raster image contrast using histogram equalization.", {"type": "object", "properties": {"raster_layer": {"type": "string"}}, "required": ["raster_layer"]})
def histogram_equalization(raster_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    ras = _find_layer_by_name(raster_layer)
    if ras is None:
        return {"error": f"Layer '{raster_layer}' not found"}
    return _run_raster_and_add(
        "gdal:contraststretch",
        {"INPUT": ras, "BAND": 1},
        f"{raster_layer}_equalized",
    )


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
        "gdal:pansharpening",
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
        },
        "required": ["line_layer", "dem_layer"],
    },
)
def elevation_profile(line_layer, dem_layer, num_samples=100):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if num_samples < 2:
        return {"error": "num_samples must be at least 2."}

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
        length = geom.length()
        if length <= 0:
            return {"error": f"'{line_layer}'s first feature has zero length."}

        provider = dem.dataProvider()
        distances = []
        elevations = []
        for i in range(num_samples):
            fraction = i / (num_samples - 1)
            point = geom.interpolate(fraction * length).asPoint()
            value, ok = provider.sample(point, 1)
            distances.append(round(fraction * length, 2))
            elevations.append(value if ok else None)

        valid_count = sum(1 for e in elevations if e is not None)
        if valid_count == 0:
            return {"error": "No valid elevation samples -- the line may not overlap the DEM's extent."}

        return {
            "success": True,
            "line_layer": line_layer,
            "dem_layer": dem_layer,
            "total_length": round(length, 2),
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


# fetch_worldpop_population names its output layers '<ISO3>_population_<year>'
# (see add_worldpop_population_layer_main_thread_phase in humanitarian_tools.py).
_WORLDPOP_LAYER_NAME_RE = re.compile(r"^[A-Za-z]{3}_population_(\d{4})$")


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


@register_tool(
    "estimate_population_exposure",
    "Sum population within each polygon of a vector layer, using an already-loaded population "
    "raster (e.g. from fetch_worldpop_population) -- e.g. 'how many people live within 5km of "
    "this facility' (combine with buffer_analysis first to build the area), or 'population per "
    "district' (pass admin boundaries directly). Adds a 'pop_sum' field to the vector layer. "
    "Returns an ESTIMATE derived from a gridded population raster, not a verified count of people "
    "actually present -- report results as 'estimated population within <area>', never as a "
    "confirmed or affected-population figure, unless field data corroborates it.",
    {
        "type": "object",
        "properties": {
            "population_raster_layer": {"type": "string", "description": "A population-per-pixel raster layer (e.g. from fetch_worldpop_population)."},
            "area_layer": {"type": "string", "description": "Polygon layer to sum population within, one total per feature."},
        },
        "required": ["population_raster_layer", "area_layer"],
    },
)
def estimate_population_exposure(population_raster_layer, area_layer):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    raster = _find_layer_by_name(population_raster_layer)
    vector = _find_layer_by_name(area_layer)
    if raster is None:
        return {"error": f"Layer '{population_raster_layer}' not found"}
    if vector is None:
        return {"error": f"Layer '{area_layer}' not found"}
    if vector.geometryType() != QgsWkbTypes.GeometryType.PolygonGeometry:
        return {"error": "area_layer must be a polygon layer."}

    try:
        from qgis.analysis import QgsZonalStatistics
        stat_enum = getattr(QgsZonalStatistics, "Statistic", QgsZonalStatistics)
        sum_flag = getattr(stat_enum, "Sum", None)
        if sum_flag is None:
            return {"error": "Could not resolve QgsZonalStatistics.Sum in this QGIS version."}

        zonal = QgsZonalStatistics(vector, raster, "pop_", 1, sum_flag)
        zonal.calculateStatistics(None)

        if vector.fields().indexFromName("pop_sum") < 0:
            return {"error": "Zonal statistics ran but no 'pop_sum' field was created -- check area_layer overlaps the raster."}

        totals = {}
        has_name_field = vector.fields().count() > 0
        for i, feat in enumerate(vector.getFeatures()):
            key = feat.attribute(0) if has_name_field else f"feature_{i}"
            totals[str(key)] = feat.attribute("pop_sum")

        total_population = sum(v for v in totals.values() if v is not None)
        pop_source, pop_reference_year = _describe_population_raster(population_raster_layer)

        return {
            "success": True,
            "area_layer": area_layer,
            "population_raster_layer": population_raster_layer,
            "totals": totals,
            "total_population": total_population,
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
        }
    except Exception as e:
        return {"error": f"estimate_population_exposure failed: {e}"}


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
            layer.setRenderer(renderer)
            result["color_ramp"] = ramp_name

        layer.triggerRepaint()
        return result
    except Exception as e:
        return {"error": f"apply_raster_stretch failed: {e}"}
