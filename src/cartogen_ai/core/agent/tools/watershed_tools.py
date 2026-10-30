"""delineate_watershed: the measuring step of a hydrology request (showcase S1), on a DEM already in the project.

The owner's request -- "determine watershed area, stream length, H, slope, return period 20 year, intensity, Tc and peak flow at this location
32°01'47.39"N, 35°48'21.00"E" -- needs a basin before any of those numbers exist. This tool reads the DEM around the outlet, runs the D8
delineation in watershed_delineation.py (tested offline on synthetic terrain), adds the basin, longest flow path and outlet to the project, and
returns every measured number plus the next step. It then hands over to the existing calculate_rational_watershed_peak_flow, which still refuses
guessed rainfall intensity or runoff coefficient: those are design inputs the user (or the local drainage standard) must supply, and this tool
tells the user exactly which and shows textbook reference ranges for C without applying them.

Limits, stated in every reply: D8 on a surface model of about 30 m (it includes buildings and trees), constant cell size over the window, the
outlet is moved onto the derived channel within the snap distance, and a basin touching the DEM edge may be truncated. The QGIS-facing part was
written without a QGIS install and is exercised by tests/test_watershed_tools_live.py (first CI run = first execution).
"""
import re

from ...models.confidence import set_layer_confidence
from . import watershed_delineation as wd
from .engineering_tools import KIRPICH_CALIBRATION_AREA_KM2, RATIONAL_AREA_LIMIT_KM2, kirpich_tc_minutes, parse_dms_location_text
from .registry import register_tool

try:
    from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsRasterLayer,
                           QgsVectorLayer)
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

MAX_CELLS = 400_000          # the pure-Python depression fill takes a few seconds at this size; larger windows are refused, not attempted
MAX_RADIUS_KM = 15.0

# Textbook ranges for the Rational Method runoff coefficient (ASCE / FHWA HDS-2 style tables). Shown to help the user CHOOSE; never applied.
REFERENCE_C_RANGES = {
    "pavement and roofs (asphalt, concrete, roofs)": "0.70-0.95",
    "business / commercial areas": "0.50-0.95",
    "dense residential": "0.40-0.75",
    "single-family residential": "0.30-0.50",
    "industrial": "0.50-0.90",
    "parks, cemeteries, playgrounds": "0.10-0.35",
    "bare or cultivated rural ground": "0.20-0.50",
    "pasture, scrub, forest": "0.10-0.40",
}


def parse_outlet(location=None, lat=None, lon=None):
    """((lon, lat), error) from a DMS string, a 'lat, lon' decimal string, or lat / lon numbers. Pure."""
    if location:
        text = str(location)
        try:
            return parse_dms_location_text(text), None
        except ValueError:
            pass
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*[,; ]\s*(-?\d+(?:\.\d+)?)\s*$", text)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
        else:
            return None, "The location could not be read. Give degrees-minutes-seconds with N/S/E/W, or 'latitude, longitude' in decimal degrees."
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None, "Give a location (DMS or 'lat, lon') or lat and lon as numbers."
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, "Latitude must be within +-90 and longitude within +-180."
    return (lon, lat), None


def design_inputs_needed(tc_minutes, return_period_years):
    """What the user must supply before a peak flow can be computed. Pure."""
    period = f"{return_period_years:g}-year" if return_period_years else "design-return-period"
    return {
        "rainfall_intensity": f"The {period} rainfall intensity in mm/h from the LOCAL IDF curve, read at a duration equal to Tc ({tc_minutes:.1f} min), with the "
                              "source (station, curve, publication and date).",
        "runoff_coefficient": "A Rational Method runoff coefficient C justified for this catchment's land cover, or tell me the land cover and I will list "
                              "the usual range for you to confirm.",
        "reference_c_ranges_not_applied": REFERENCE_C_RANGES,
        "reference_note": "General textbook ranges, shown only to help you choose; confirm against the governing local drainage standard.",
    }


def hydrology_warnings(result, dem_resolution_m):
    out = []
    area = result["area_km2"]
    if result["touches_dem_edge"]:
        out.append("The basin reaches the edge of the DEM window, so it may be cut off: the area, flow length and H are minimums. Fetch a larger DEM "
                   "(radius_km) and run again.")
    if not result["snapped_to_channel"]:
        out.append("No drainage channel was found within the snap distance: the outlet sits on the best candidate cell, not a clear stream. Check the "
                   "outlet position on the map.")
    if result["snap_moved_m"] > 150:
        out.append(f"The outlet was moved {result['snap_moved_m']:.0f} m onto the derived channel; confirm it is the intended location.")
    if area > RATIONAL_AREA_LIMIT_KM2:
        out.append(f"The basin is {area:.2f} km2, above the {RATIONAL_AREA_LIMIT_KM2} km2 limit usually quoted for the Rational Method (FHWA HDS-4); treat "
                   "the discharge as a rough screening value or use a method suited to larger catchments.")
    if area > KIRPICH_CALIBRATION_AREA_KM2:
        out.append(f"Kirpich's time of concentration was fitted to basins up to about {KIRPICH_CALIBRATION_AREA_KM2} km2; this basin is larger.")
    if result["H_m"] <= 0:
        out.append("The longest flow path has no elevation drop in the DEM (flat or noisy terrain): the slope and Tc cannot be computed.")
    out.append(f"The DEM is a surface model of about {dem_resolution_m:.0f} m (it includes buildings and trees); D8 flow directions on it are an estimate, "
               "not a survey.")
    return out


def _find_dem(name, lon, lat):
    """(layer, error): the named raster, else a raster in the project that covers the point (names with 'dem' first)."""
    project = QgsProject.instance()
    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    if name:
        layers = project.mapLayersByName(name)
        if not layers or not isinstance(layers[0], QgsRasterLayer):
            return None, f"Raster layer '{name}' not found."
        return layers[0], None
    candidates = []
    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsRasterLayer) or layer.bandCount() != 1:
            continue
        point = QgsCoordinateTransform(wgs, layer.crs(), project).transform(QgsPointXY(lon, lat))
        if layer.extent().contains(point):
            candidates.append((0 if "dem" in layer.name().lower() or layer.customProperty("cartogen/source") else 1, layer))
    if not candidates:
        return None, (f"No elevation raster in the project covers {lat:.5f}, {lon:.5f}. Call fetch_dem(lat={lat:.5f}, lon={lon:.5f}, radius_km=10) first "
                      "(Copernicus GLO-30, about 30 m, no key needed), then run this again.")
    return sorted(candidates, key=lambda t: t[0])[0][1], None


@register_tool(
    "delineate_watershed",
    "Delineate the watershed upstream of an outlet point on a DEM in the project and MEASURE it: basin area, longest hydraulic flow path, H "
    "(elevation drop along it), main-channel slope and the Kirpich time of concentration. Adds the basin, flow path and outlet to the project. "
    "location is DMS ('32°01'47.39\"N, 35°48'21.00\"E') or 'lat, lon'. Needs an elevation raster that covers the point (fetch_dem first if none). "
    "It does NOT invent rainfall intensity or a runoff coefficient: the reply says which design inputs the user must give, then use "
    "calculate_rational_watershed_peak_flow for the peak flow.",
    {"type": "object", "properties": {
        "location": {"type": "string", "description": "Outlet as DMS or 'lat, lon'."},
        "lat": {"type": "number"}, "lon": {"type": "number"},
        "dem_layer": {"type": "string", "description": "Name of the DEM raster; default: a raster in the project that covers the point."},
        "return_period_years": {"type": "number", "description": "Design return period, used to word the design-input request."},
        "radius_km": {"type": "number", "description": "Half-width of the window read around the outlet (default 8, at most 15)."},
        "snap_distance_m": {"type": "number", "description": "How far the outlet may move onto the derived channel (default 300)."},
        "layer_prefix": {"type": "string", "description": "Prefix for the new layers (default 'Watershed')."}},
     "required": []},
    keywords=[
        "watershed", "catchment", "drainage basin", "basin area", "delineate the basin", "flow path", "stream length",
        "time of concentration", "peak flow", "peak discharge", "tc ", "rational method", "return period", "pour point",
        "upstream area", "contributing area",
    ],
)
def delineate_watershed(location=None, lat=None, lon=None, dem_layer=None, return_period_years=None, radius_km=8, snap_distance_m=300,
                        layer_prefix="Watershed"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    outlet, err = parse_outlet(location, lat, lon)
    if err:
        return {"error": err}
    lon_, lat_ = outlet
    try:
        radius_km = min(max(float(radius_km), 1.0), MAX_RADIUS_KM)
        snap_distance_m = min(max(float(snap_distance_m), 0.0), 2000.0)
    except (TypeError, ValueError):
        return {"error": "radius_km and snap_distance_m must be numbers."}
    layer, err = _find_dem(dem_layer, lon_, lat_)
    if err:
        return {"error": err}
    try:
        from osgeo import gdal
    except ImportError:
        return {"error": "GDAL python bindings are not available, so the DEM cannot be read."}
    gdal.UseExceptions()
    try:
        dataset = gdal.Open(layer.source().split("|")[0])
    except Exception as e:   # any GDAL failure is reported with its own text
        return {"error": f"The DEM '{layer.name()}' could not be opened for reading ({e}). Only DEMs stored as files can be used."}
    gt = dataset.GetGeoTransform()
    band = dataset.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    project = QgsProject.instance()
    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    point = QgsCoordinateTransform(wgs, layer.crs(), project).transform(QgsPointXY(lon_, lat_))
    col, row = int((point.x() - gt[0]) / gt[1]), int((point.y() - gt[3]) / gt[5])
    if not (0 <= col < dataset.RasterXSize and 0 <= row < dataset.RasterYSize):
        return {"error": f"The outlet lies outside the DEM '{layer.name()}'."}
    dx_m, dy_m = wd.cell_size_metres(gt, lat_, layer.crs().isGeographic())
    half = max(5, round(radius_km * 1000.0 / min(dx_m, dy_m)))
    x0, y0 = max(0, col - half), max(0, row - half)
    x1, y1 = min(dataset.RasterXSize, col + half + 1), min(dataset.RasterYSize, row + half + 1)
    if (x1 - x0) * (y1 - y0) > MAX_CELLS:
        return {"error": f"That window is {(x1 - x0) * (y1 - y0):,} cells; the limit is {MAX_CELLS:,}. Use a smaller radius_km."}
    import numpy as np
    array = band.ReadAsArray(x0, y0, x1 - x0, y1 - y0).astype(np.float64)
    if nodata is not None:
        array[array == nodata] = np.nan
    result = wd.delineate(array, dx_m, dy_m, row - y0, col - x0, snap_radius_m=snap_distance_m)
    if "error" in result:
        return result

    def xy(r, c):                                  # cell centre in the DEM's CRS
        return gt[0] + (c + x0 + 0.5) * gt[1], gt[3] + (r + y0 + 0.5) * gt[5]

    runs = wd.mask_to_row_runs(result["mask"])
    rects = []
    for r, c0, c1 in runs:
        left, top = gt[0] + (c0 + x0) * gt[1], gt[3] + (r + y0) * gt[5]
        rects.append(QgsGeometry.fromRect(_rect(left, top + gt[5], left + (c1 - c0 + 1) * gt[1], top)))
    basin_geom = QgsGeometry.unaryUnion(rects)
    crs_id = layer.crs().authid()
    prefix = str(layer_prefix or "Watershed")
    made = []

    def add_layer(kind, name, fields, geometry, attrs, style):
        vl = QgsVectorLayer(f"{kind}?crs={crs_id}{fields}", name, "memory")
        feat = QgsFeature(vl.fields())
        feat.setGeometry(geometry)
        feat.setAttributes(attrs)
        vl.dataProvider().addFeatures([feat])
        vl.updateExtents()
        project.addMapLayer(vl)
        style(vl)
        set_layer_confidence(vl, "MODELED", reason="D8 delineation on a ~30 m DEM surface model; preliminary, not surveyed")
        made.append(vl.name())
        return vl

    area = result["area_km2"]
    add_layer("Polygon", f"{prefix} basin", "&field=area_km2:double&field=cells:integer&field=dem:string", basin_geom,
              [round(area, 4), result["cells"], layer.name()], _style_basin)
    path_pts = [QgsPointXY(*xy(r, c)) for r, c in result["path_rc"]]
    add_layer("LineString", f"{prefix} longest flow path", "&field=length_m:double&field=H_m:double", QgsGeometry.fromPolylineXY(path_pts),
              [round(result["longest_flow_path_m"], 1), round(result["H_m"], 2)], _style_path)
    orow, ocol = result["outlet_rc"]
    add_layer("Point", f"{prefix} outlet", "&field=kind:string&field=snapped_m:double", QgsGeometry.fromPointXY(QgsPointXY(*xy(orow, ocol))),
              ["snapped outlet", round(result["snap_moved_m"], 1)], _style_outlet)

    length_m, drop, slope = result["longest_flow_path_m"], result["H_m"], result["main_channel_slope_m_per_m"]
    measurements = {
        "watershed_area_km2": round(area, 4),
        "longest_hydraulic_flow_path_km": round(length_m / 1000.0, 4),
        "upstream_elevation_m": round(result["upstream_elevation_m"], 2),
        "outlet_elevation_m": round(result["outlet_elevation_m"], 2),
        "H_elevation_drop_m": round(drop, 2),
        "main_channel_slope_m_per_m": round(slope, 6) if slope else None,
        "main_channel_slope_percent": round(slope * 100, 4) if slope else None,
        "max_basin_elevation_m": round(result["max_basin_elevation_m"], 2),
        "mean_basin_elevation_m": round(result["mean_basin_elevation_m"], 2),
    }
    out = {"success": True, "layers_added": made, "measurements": measurements,
           "outlet": {"requested_lon": round(lon_, 6), "requested_lat": round(lat_, 6), "snapped_distance_m": round(result["snap_moved_m"], 1),
                      "snapped_to_channel": result["snapped_to_channel"]},
           "dem": {"layer": layer.name(), "crs": crs_id, "cell_size_m": [round(dx_m, 1), round(dy_m, 1)], "window_cells": int(array.size)},
           "method": "D8 flow directions after priority-flood depression filling; outlet snapped to the highest-accumulation cell within the snap distance; "
                     "longest path = greatest D8 flow distance to the outlet; H from the unfilled DEM.",
           "warnings": hydrology_warnings(result, (dx_m + dy_m) / 2)}
    if slope:
        tc = kirpich_tc_minutes(length_m, slope)
        out["time_of_concentration_kirpich_min"] = round(tc, 2)
        out["design_inputs_needed"] = design_inputs_needed(tc, return_period_years)
        out["next_step"] = ("Ask the user for the two design inputs above (once), then call calculate_rational_watershed_peak_flow with these exact "
                            "measurements: area_km2, flow_length_km, upstream_elevation_m, outlet_elevation_m, return_period_years, plus their intensity "
                            "(read at Tc), its duration, its source and C. Then present: the measurements, the equations, the inputs with their sources, "
                            "the warnings, and the map layers.")
    return out


def _rect(x0, y0, x1, y1):
    from qgis.core import QgsRectangle
    return QgsRectangle(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _style_basin(layer):
    from qgis.core import QgsFillSymbol
    layer.renderer().setSymbol(QgsFillSymbol.createSimple({"color": "30,100,200,70", "outline_color": "20,70,160", "outline_width": "0.7"}))
    layer.triggerRepaint()


def _style_path(layer):
    from qgis.core import QgsLineSymbol
    layer.renderer().setSymbol(QgsLineSymbol.createSimple({"color": "210,30,30", "width": "0.9"}))
    layer.triggerRepaint()


def _style_outlet(layer):
    from qgis.core import QgsMarkerSymbol
    layer.renderer().setSymbol(QgsMarkerSymbol.createSimple({"name": "triangle", "color": "255,200,0", "outline_color": "0,0,0", "size": "4"}))
    layer.triggerRepaint()
