"""calculate_spectral_index (PLAN-023 R3-1): NDVI, NDWI, MNDWI, NDRE, NDMI, NBR, SAVI, EVI and BSI from raster layers in the project.

One tool for the nine indices, computed with the pure formulas of raster_indices.py (hand-checked offline) on numpy arrays read through GDAL, written as
a Float32 GeoTIFF with an explicit NoData value and added to the project. Cells where an input is NoData, or where the formula divides by zero, are
NoData, never 0. The existing calculate_ndvi / calculate_ndwi / calculate_ndre keep working unchanged (they go through gdal:rastercalculator); this
tool adds the other six indices and the SAVI soil factor.

Which band is which is the caller's: `bands` maps each role of the index to a layer name, or 'layer name@3' for band 3 of a multi-band layer.
Sentinel-2 B8 is NIR and Landsat 8 band 5 is NIR, so nothing here guesses. Inputs must share one pixel grid (the existing check, with the same
align_to_first option); the raster is read into memory under the existing cell budget, so a very large raster must be clipped first.

Written without a QGIS install; tests/test_spectral_index_tool_live.py is its first execution in CI."""
import contextlib
import os
import tempfile

from . import raster_indices as ri
from . import raster_numpy as rn
from .raster_tools import _ALIGN_PARAMS, _find_layer_by_name, _grid_or_error, _with_alignment_note
from .registry import register_tool

try:
    from qgis.core import QgsProject, QgsRasterLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

NODATA = -9999.0
_ROLE_HELP = "; ".join(f"{name}: {', '.join(roles)}" for name, (roles, _f, _m) in ri.INDICES.items())


def _write_float_raster(values, ok, info, nodata=NODATA):
    """Writes `values` (2-D float32) as a Float32 GeoTIFF in a temp file with the template's georeferencing; cells where `ok` is false get `nodata`.
    Returns the path. Needs GDAL."""
    import numpy as np
    from osgeo import gdal
    fd, path = tempfile.mkstemp(suffix=".tif")
    os.close(fd)
    rows, cols = values.shape
    ds = gdal.GetDriverByName("GTiff").Create(path, cols, rows, 1, gdal.GDT_Float32)
    ds.SetGeoTransform(info["geotransform"])
    ds.SetProjection(info["projection"])
    band = ds.GetRasterBand(1)
    band.WriteArray(np.where(ok, values, np.float32(nodata)).astype(np.float32))
    band.SetNoDataValue(nodata)
    band.FlushCache()
    ds = None
    return path


@register_tool(
    "calculate_spectral_index",
    "Calculate a spectral index raster from band layers: NDVI (vegetation greenness), NDWI and MNDWI (open water), NDRE (crop chlorophyll), NDMI "
    "(vegetation moisture), NBR (burn severity), SAVI (vegetation over bare soil, with a soil factor), EVI (dense canopy, reflectance 0 to 1) and BSI "
    "(bare soil). Give `index` and `bands`: a mapping from each band role to a raster layer name, or 'layer name@3' for band 3 of a multi-band "
    "layer. Roles per index -- " + _ROLE_HELP + ". Nothing guesses which band is which: Sentinel-2 B8 is nir, B4 red, B3 green, B2 blue, B5 rededge, "
    "B11 swir1, B12 swir2; Landsat 8 band 5 is nir, 4 red, 3 green, 2 blue, 6 swir1, 7 swir2. The bands must share one pixel grid (or pass "
    "align_to_first). Cells where an input is NoData or the formula divides by zero are NoData, not 0. Adds a new single-band raster named after "
    "the index (or output_name); follow up with apply_raster_stretch for a readable ramp.",
    {"type": "object", "properties": {
        "index": {"type": "string", "enum": list(ri.INDICES), "description": "Which index to compute."},
        "bands": {"type": "object", "additionalProperties": {"type": "string"},
                  "description": "Band role -> raster layer name (or 'layer name@band'). Example for SAVI: {\"nir\": \"B8\", \"red\": \"B4\"}."},
        "output_name": {"type": "string", "description": "Name of the new layer (default: the index name)."},
        "soil_factor": {"type": "number", "description": "SAVI only: the soil brightness factor L, default 0.5 (0 gives NDVI, 1 for very sparse vegetation)."},
        **_ALIGN_PARAMS},
     "required": ["index", "bands"]},
    keywords=[
        "spectral index", "vegetation index", "savi", "evi", "ndre", "ndmi", "nbr", "mndwi", "bsi", "burn severity", "burned area",
        "bare soil index", "moisture index", "red edge", "soil adjusted vegetation", "enhanced vegetation",
    ],
)
def calculate_spectral_index(index, bands, output_name=None, soil_factor=ri.SOIL_FACTOR_DEFAULT, align_to_first=False, resampling="bilinear"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    name = ri.normalise_name(index)
    problem = ri.check_bands(index, bands)
    if problem:
        return {"error": problem}
    try:
        ell = float(soil_factor)
    except (TypeError, ValueError):
        return {"error": "soil_factor must be a number."}
    wanted = ri.INDICES[name][0]
    refs = {}
    for role in wanted:
        layer_name, band_no = ri.parse_band_ref(bands[role])
        if layer_name is None:
            return {"error": f"'{bands[role]}' is not a valid band reference for {role}: use a layer name or 'layer name@band' with band 1 or higher."}
        layer = _find_layer_by_name(layer_name)
        if layer is None:
            return {"error": f"Layer '{layer_name}' (for {role}) not found."}
        if not isinstance(layer, QgsRasterLayer):
            return {"error": f"'{layer_name}' (for {role}) is not a raster layer."}
        if band_no > layer.bandCount():
            return {"error": f"'{layer_name}' has {layer.bandCount()} band(s); band {band_no} was asked for {role}."}
        refs[role] = (layer, band_no)
    unique = list({layer.id(): layer for layer, _b in refs.values()}.values())
    used, grid_error, align_note = _grid_or_error(unique, align_to_first, resampling)
    if grid_error:
        return {"error": grid_error}
    by_id = {orig.id(): new for orig, new in zip(unique, used, strict=True)}
    arrays, valid, info, band_max = {}, None, None, 0.0
    try:
        for role, (layer, band_no) in refs.items():
            data, band_valid, band_info = rn.read_bands(by_id[layer.id()].source(), [band_no])
            arrays[role] = data[:, :, 0]
            valid = band_valid if valid is None else (valid & band_valid)
            info = info or band_info
            if band_valid.any():
                band_max = max(band_max, float(arrays[role][band_valid].max()))
        values, ok = ri.compute_index(name, arrays, valid, ell)
        path = _write_float_raster(values, ok, info)
    except ValueError as e:
        return {"error": f"{name}: {e}"}
    except Exception as e:
        return {"error": f"{name} could not be computed: {e}"}
    out_name = (output_name or "").strip() or name
    layer_out = QgsRasterLayer(path, out_name)
    if not layer_out.isValid():
        with contextlib.suppress(OSError):
            os.remove(path)
        return {"error": f"The {name} raster was written but could not be loaded: {path}"}
    QgsProject.instance().addMapLayer(layer_out)
    valid_cells = int(ok.sum())
    result = {
        "success": True, "layer_name": out_name, "index": name, "formula": ri.INDICES[name][1] + (f", L = {ell:g}" if name == "SAVI" else ""),
        "meaning": ri.INDICES[name][2],
        "inputs": {role: (layer.name() if band_no == 1 and layer.bandCount() == 1 else f"{layer.name()}@{band_no}") for role, (layer, band_no) in refs.items()},
        "valid_cells": valid_cells, "no_data_cells": int(ok.size - valid_cells), "nodata_value": NODATA,
        "limits": "The band-to-role assignment is yours, not detected. NoData where an input is NoData or the formula divides by zero. "
                  "The raster was read into memory (clip a very large one first).",
    }
    if valid_cells:
        result["value_range"] = [round(float(values[ok].min()), 4), round(float(values[ok].max()), 4)]
    note = ri.scale_note(name, band_max)
    if note:
        result["scale_note"] = note
    return _with_alignment_note(result, align_note)
