# -*- coding: utf-8 -*-
"""fetch_dem: download elevation for an area from the Copernicus DEM GLO-30 open dataset.

2026-10-09 cost investigation, scenario 4 (terrain study): no tool could obtain a DEM, so the model improvised with scripts. Source chosen
after checking it from the sandbox rather than assuming: Copernicus DEM GLO-30 as Cloud-Optimised GeoTIFFs on the AWS Open Data bucket
(anonymous, no API key; 1 degree tiles of 3600x3600 cells, about 30 m; Float32; DEFLATE; no nodata value; tiles that are entirely ocean are
ABSENT and answer 404; windowed reads through /vsicurl/ work, so only the requested window is transferred). OpenTopography needs a key and
was unreachable from the sandbox; Terrarium tiles mix several sources so a result is harder to reproduce.

What the result is, stated honestly: a DSM (surface model, includes buildings and tree canopy), not bare-earth terrain; heights are
orthometric (EGM2008); horizontal grid about 30 m, so it cannot resolve small features. Whether the attribution text below is the exact wording
the owner wants shown is for the owner to confirm. Not verified against a real QGIS session by hand."""
import datetime
import math
import os

from .registry import register_tool
from ._paths import resolve_output_path

try:
    from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsRasterLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

TILE_BASE = os.environ.get("CARTOGEN_DEM_TILE_BASE", "https://copernicus-dem-30m.s3.amazonaws.com")
PRODUCT = "Copernicus DEM GLO-30 (COG)"
CELLS_PER_DEGREE = 3600                 # 1 arc-second = about 30 m
MAX_CELLS = 40_000_000                  # about 160 MB as Float32 before compression; larger areas are refused
MAX_TILES = 16
# Licence for the use of the Copernicus WorldDEM-30 (read in full, 2026-10-09), Article 6: (b) data that has been adapted or modified -- this
# tool clips and re-encodes a window, so it is -- must carry the "produced using ..." notice; (c) anyone distributing or communicating it to
# the general public must also pass on the no-liability sentence; (d) the user must not suggest official endorsement by the Provider, the
# Licensor or the Copernicus bodies. The first two are shown with every result; (d) is a statement for whoever publishes a map made from it.
ATTRIBUTION = ("produced using Copernicus WorldDEM-30 \u00a9 DLR e.V. 2010-2014 and \u00a9 Airbus Defence and Space GmbH 2014-2018 provided "
               "under COPERNICUS by the European Union and ESA; all rights reserved.")
LIABILITY_NOTICE = ("The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any "
                    "use of the Copernicus WorldDEM-30.")
ENDORSEMENT_NOTE = "Do not present a map made from this data as officially endorsed by Copernicus, ESA, DLR or Airbus."
CAVEATS = ("Surface model (DSM): includes buildings and tree canopy, not bare earth. Heights are orthometric (EGM2008). Grid is about "
           "30 m, so it cannot show small features such as embankments or gullies; contour spacing is not terrain accuracy.")


def tile_name(lat_floor, lon_floor):
    """Copernicus tile id for the 1-degree cell whose south-west corner is (lat_floor, lon_floor). Pure."""
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    return "Copernicus_DSM_COG_10_%s%02d_00_%s%03d_00_DEM" % (ns, abs(int(lat_floor)), ew, abs(int(lon_floor)))


def tile_url(lat_floor, lon_floor, base=None):
    name = tile_name(lat_floor, lon_floor)
    return "%s/%s/%s.tif" % ((base or TILE_BASE).rstrip("/"), name, name)


def bbox_from_centre(lat, lon, radius_km):
    """(west, south, east, north) of the square around a point. Pure."""
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.01))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def validate_bbox(west, south, east, north):
    """Return an error string, or None. Pure."""
    try:
        west, south, east, north = float(west), float(south), float(east), float(north)
    except (TypeError, ValueError):
        return "The bounding box must be four numbers (west, south, east, north in degrees)."
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        return "The bounding box is invalid: need -180 <= west < east <= 180 and -90 <= south < north <= 90."
    return None


def tiles_for_bbox(west, south, east, north):
    """The (lat_floor, lon_floor) of every 1-degree tile touching the box. A box edge exactly on a tile edge does not pull in the next
    tile. Pure."""
    lats = range(int(math.floor(south)), int(math.ceil(north)))
    lons = range(int(math.floor(west)), int(math.ceil(east)))
    return [(la, lo) for la in lats for lo in lons]


def estimated_cells(west, south, east, north):
    return int(math.ceil((east - west) * CELLS_PER_DEGREE) * math.ceil((north - south) * CELLS_PER_DEGREE))


def plan_download(west, south, east, north):
    """Refusal text or None, plus the tile list. Pure."""
    problem = validate_bbox(west, south, east, north)
    if problem:
        return problem, []
    tiles = tiles_for_bbox(west, south, east, north)
    if len(tiles) > MAX_TILES:
        return f"The area touches {len(tiles)} one-degree tiles (limit {MAX_TILES}); choose a smaller area.", tiles
    cells = estimated_cells(west, south, east, north)
    if cells > MAX_CELLS:
        return f"The area is about {cells:,} cells at 30 m (limit {MAX_CELLS:,}); choose a smaller area.", tiles
    return None, tiles


def _layer_bbox(layer_name):
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        return None, f"Layer '{layer_name}' not found"
    layer = layers[0]
    rect = layer.extent()
    target = QgsCoordinateReferenceSystem("EPSG:4326")
    if layer.crs() != target:
        rect = QgsCoordinateTransform(layer.crs(), target, QgsProject.instance()).transformBoundingBox(rect)
    return (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()), None


def _open_existing(urls):
    """Tiles that answer; absent (ocean) tiles are skipped and reported."""
    from osgeo import gdal
    gdal.UseExceptions()
    found, missing = [], []
    for (la, lo), url in urls:
        try:
            ds = gdal.Open("/vsicurl/" + url)
        except RuntimeError:
            ds = None
        if ds is None:
            missing.append(tile_name(la, lo))
        else:
            ds = None
            found.append("/vsicurl/" + url)
    return found, missing


@register_tool(
    "fetch_dem",
    "Download elevation (a DEM raster) for an area from the Copernicus DEM GLO-30 open dataset (about 30 m, no account or key needed) "
    "and add it to the project. Give the area as a layer name (its extent), as a bounding box in degrees (west, south, east, north), or "
    "as a centre point (lat, lon) with radius_km. The result is a surface model (includes buildings/trees), not bare earth, about 30 m "
    "resolution; the reply records source, tiles used, retrieval date, vertical datum and the required attribution. Refuses very large "
    "areas. Use generate_contours or slope_analysis on the result.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "Name of a layer whose extent defines the area."},
        "west": {"type": "number"}, "south": {"type": "number"}, "east": {"type": "number"}, "north": {"type": "number"},
        "lat": {"type": "number", "description": "Centre latitude (with lon and radius_km)."},
        "lon": {"type": "number", "description": "Centre longitude."},
        "radius_km": {"type": "number", "description": "Half-width of the square around the centre, km."},
        "output_path": {"type": "string", "description": "Optional GeoTIFF path; relative paths are anchored to the project folder."},
        "output_name": {"type": "string", "description": "Optional layer name."}},
     "required": []},
)
def fetch_dem(layer_name=None, west=None, south=None, east=None, north=None, lat=None, lon=None, radius_km=None,
              output_path=None, output_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if layer_name:
        box, err = _layer_bbox(layer_name)
        if err:
            return {"error": err}
    elif None not in (west, south, east, north):
        box = (west, south, east, north)
    elif None not in (lat, lon, radius_km):
        try:
            box = bbox_from_centre(float(lat), float(lon), float(radius_km))
        except (TypeError, ValueError):
            return {"error": "lat, lon and radius_km must be numbers."}
    else:
        return {"error": "Give a layer_name, or west/south/east/north, or lat/lon/radius_km."}
    box = tuple(float(v) for v in box)
    refusal, tiles = plan_download(*box)
    if refusal:
        return {"error": refusal}
    try:
        from osgeo import gdal
    except ImportError:
        return {"error": "GDAL python bindings are not available."}
    found, missing = _open_existing([((la, lo), tile_url(la, lo)) for la, lo in tiles])
    if not found:
        return {"error": "No elevation tiles exist for this area (all-ocean tiles are not published) or the data host could not be "
                         "reached. Check the area and the network connection."}
    path = resolve_output_path(output_path) if output_path else None
    if not path:
        import tempfile
        path = os.path.join(tempfile.mkdtemp(prefix="cartogen_dem_"), "dem_glo30.tif")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        gdal.UseExceptions()
        vrt = gdal.BuildVRT("", found)
        out = gdal.Translate(path, vrt, projWin=[box[0], box[3], box[2], box[1]], projWinSRS="EPSG:4326",
                             creationOptions=["COMPRESS=DEFLATE", "TILED=YES"])
        if out is None:
            return {"error": "The elevation window could not be written."}
        cols, rows = out.RasterXSize, out.RasterYSize
        out = vrt = None
    except Exception as e:
        return {"error": f"Downloading the elevation window failed: {e}"}
    name = output_name or "DEM_Copernicus_GLO30"
    layer = QgsRasterLayer(path, name)
    if not layer.isValid():
        return {"error": "The downloaded DEM could not be loaded."}
    retrieved = datetime.date.today().isoformat()
    for key, value in (("cartogen/source", PRODUCT), ("cartogen/retrieved", retrieved), ("cartogen/attribution", ATTRIBUTION), ("cartogen/liability_notice", LIABILITY_NOTICE),
                       ("cartogen/caveats", CAVEATS)):
        layer.setCustomProperty(key, value)
    QgsProject.instance().addMapLayer(layer)
    result = {"success": True, "layer_name": name, "path": path, "source": PRODUCT, "retrieved": retrieved,
              "bbox_wgs84": [round(v, 5) for v in box], "columns": cols, "rows": rows, "pixel_size_m_approx": 30,
              "tiles_used": [tile_name(*t) for t in tiles if "/vsicurl/" + tile_url(*t) in found],
              "vertical_datum": "EGM2008 orthometric", "model_type": "DSM (surface, not bare earth)",
              "attribution": ATTRIBUTION, "liability_notice": LIABILITY_NOTICE, "endorsement_note": ENDORSEMENT_NOTE,
              "caveats": CAVEATS}
    if missing:
        result["tiles_absent"] = missing
        result["warning"] = "Some tiles are not published (usually open sea); those parts of the area have no elevation."
    return result
