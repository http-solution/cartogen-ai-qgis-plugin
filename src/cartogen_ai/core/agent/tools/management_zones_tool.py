"""create_zoning_map (PLAN-023 R3-5): zones of similar index values from one or more rasters, as a polygon layer with the mean index per zone in its legend label.

The clustering, smoothing and small-zone merging are the pure, hand-checked steps of raster_zones.py; this module reads the rasters through GDAL, turns the zone grid into polygons
with GDAL's polygonize (4-connected, the same patches the merge used) and writes one feature per zone. Zones are numbered 1..n from the lowest mean of the FIRST raster, so a
sequential colour ramp reads in order. Cell areas come from the CRS (exact for a projected raster, row-by-row sphere approximation for a geographic one, as in calculate_change_matrix);
a raster whose CRS is neither is refused, because the minimum zone area cannot be applied.

The zones describe differences in the index values only: this tool gives no yield forecast and no input-rate recommendation, and says so in its reply.

Written without a QGIS install; tests/test_management_zones_tool_live.py is its first execution in CI."""
import contextlib
import os
import tempfile

from . import raster_change as rc
from . import raster_indices as ri
from . import raster_numpy as rn
from . import raster_zones as rz
from ._layer_checks import require_valid_layer
from .raster_change_tool import crs_area_kind
from .raster_tools import _ALIGN_PARAMS, _find_layer_by_name, _grid_or_error, _with_alignment_note
from .registry import register_tool

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

NOTE = ("The zones describe differences in the index values only. They are not a yield forecast and not an input-rate recommendation; this tool does not say what to do "
        "on any zone.")


def write_zone_raster(labels, info, nodata=-1):
    """Writes the zone grid (2-D ints, -1 where not valid) as an Int16 GeoTIFF in a temp file with the template's georeferencing. Returns the path. Needs GDAL."""
    import numpy as np
    from osgeo import gdal
    fd, path = tempfile.mkstemp(suffix=".tif")
    os.close(fd)
    rows, cols = labels.shape
    ds = gdal.GetDriverByName("GTiff").Create(path, cols, rows, 1, gdal.GDT_Int16)
    ds.SetGeoTransform(info["geotransform"])
    ds.SetProjection(info["projection"])
    band = ds.GetRasterBand(1)
    band.WriteArray(labels.astype(np.int16))
    band.SetNoDataValue(nodata)
    band.FlushCache()
    ds = None
    return path


def polygonize_zones(path):
    """{zone value: [WKT of each polygon]} from a zone GeoTIFF, by GDAL's polygonize (4-connected, NoData cells skipped). Needs GDAL."""
    from osgeo import gdal, ogr
    src = gdal.Open(path)
    band = src.GetRasterBand(1)
    out_ds = ogr.GetDriverByName("Memory").CreateDataSource("zones")
    layer = out_ds.CreateLayer("zones", srs=None, geom_type=ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("zone", ogr.OFTInteger))
    gdal.Polygonize(band, band.GetMaskBand(), layer, 0, [], callback=None)
    zones = {}
    layer.ResetReading()
    for feature in layer:
        zones.setdefault(int(feature.GetField("zone")), []).append(feature.GetGeometryRef().ExportToWkt())
    return zones


def legend_label(zone, means, band_names):
    """'Zone 2: NDVI mean 0.54' (one band) or 'Zone 2: NDVI mean 0.54; NDRE mean 0.31' (several). Pure."""
    parts = [f"{name} mean {mean:.3g}" for name, mean in zip(band_names, means, strict=True)]
    return f"Zone {zone}: " + "; ".join(parts)


@register_tool(
    "create_zoning_map",
    "Divide a field or area into 2 to 8 zones of similar values (3 to 5 is usual for management zones) from one or more index rasters already in the project, for example NDVI, NDRE or "
    "any single-band raster: seeded k-means on the standardised bands, an optional smoothing pass, and merging of patches smaller than min_zone_area_ha into the neighbouring zone with "
    "the nearest mean. `rasters` is a list of 1 to 5 layer names (or 'layer name@band'). Zone 1 is the lowest mean of the first raster. Adds a polygon layer with one feature per zone and "
    "the mean of each raster in its legend label. The zones describe differences in the index values only: this tool gives NO yield forecast and NO fertiliser or input-rate recommendation. "
    "The rasters must share one pixel grid (or pass align_to_first); the raster must be at most 4 million cells (clip first).",
    {"type": "object", "properties": {
        "rasters": {"type": "array", "items": {"type": "string"}, "description": "1 to 5 raster layers to cluster on (names or 'name@band')."},
        "n_zones": {"type": "integer", "description": "Number of zones, 2 to 8 (default 3)."},
        "min_zone_area_ha": {"type": "number", "description": "Patches smaller than this are merged into a neighbouring zone (default: 1 percent of the valid area; 0 keeps every patch)."},
        "smooth": {"type": "boolean", "description": "Run one 3 x 3 majority pass first to remove isolated cells (default false)."},
        "seed": {"type": "integer", "description": "Random seed for the clustering (default 0); the same seed gives the same zones."},
        "output_name": {"type": "string", "description": "Name of the polygon layer (default management_zones)."},
        **_ALIGN_PARAMS},
     "required": ["rasters"]},
    keywords=["management zones", "zoning", "field zones", "precision agriculture", "variable rate zones", "homogeneous zones", "split the field into zones", "productivity zones"],
)
def create_zoning_map(rasters, n_zones=3, min_zone_area_ha=None, smooth=False, seed=0, output_name="management_zones", align_to_first=False, resampling="bilinear"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    refs = [str(r) for r in (rasters or [])]
    problem = rz.check_request(n_zones, len(refs), 0)
    if problem:
        return {"error": problem}
    k = int(n_zones)
    try:
        min_area = None if min_zone_area_ha is None else float(min_zone_area_ha)
        seed = int(seed)
    except (TypeError, ValueError):
        return {"error": "min_zone_area_ha must be a number and seed a whole number."}
    if min_area is not None and min_area < 0:
        return {"error": "min_zone_area_ha cannot be negative."}
    layers = []
    for ref in refs:
        layer_name, band_no = ri.parse_band_ref(ref)
        if layer_name is None:
            return {"error": f"'{ref}' is not a valid raster reference: use a layer name or 'layer name@band'."}
        layer = _find_layer_by_name(layer_name)
        if layer is None:
            return {"error": f"Layer '{layer_name}' not found."}
        if not hasattr(layer, "bandCount") or not hasattr(layer, "rasterUnitsPerPixelX"):
            return {"error": f"'{layer_name}' is not a raster layer."}
        if band_no > layer.bandCount():
            return {"error": f"'{layer_name}' has {layer.bandCount()} band(s); band {band_no} was asked."}
        layers.append((layer, band_no, ref))
    unique = list({layer.id(): layer for layer, _b, _r in layers}.values())
    used, grid_error, align_note = _grid_or_error(unique, align_to_first, resampling)
    if grid_error:
        return {"error": grid_error}
    by_id = {orig.id(): new for orig, new in zip(unique, used, strict=True)}
    first = by_id[unique[0].id()]
    problem = rz.check_request(k, len(refs), first.width() * first.height())
    if problem:
        return {"error": problem}
    path = None
    try:
        import numpy as np
        stack, valid, info = [], None, None
        for layer, band_no, _ref in layers:
            data, band_valid, band_info = rn.read_bands(by_id[layer.id()].source(), [band_no])
            stack.append(data[:, :, 0].astype(np.float64))
            valid = band_valid if valid is None else (valid & band_valid)
            info = info or band_info
        values = np.stack(stack, axis=-1)
        is_geographic, metres_per_unit = crs_area_kind(info["projection"])
        row_ha = rc.row_areas_ha(info["geotransform"], values.shape[0], is_geographic, metres_per_unit)
        if row_ha is None:
            return {"error": "The raster's CRS is neither projected nor geographic, so cell areas cannot be computed and the minimum zone area cannot be applied; reproject it first."}
        labels, z = rz.cluster(values, valid, k, seed)
        if smooth:
            labels = rz.majority_filter(labels)
        total_ha = float(np.repeat(np.asarray(row_ha), values.shape[1]).reshape(valid.shape)[valid].sum())
        threshold = rz.default_min_area_ha(total_ha) if min_area is None else min_area
        labels, merged = rz.merge_small(labels, z, valid, row_ha, threshold)
        present = sorted(c for c in np.unique(labels).tolist() if c >= 0)
        renumber = {old: new for new, old in enumerate(present)}
        labels = np.where(labels >= 0, np.vectorize(lambda c: renumber.get(c, -1), otypes=[np.int32])(labels), -1)
        stats = rz.zone_stats(labels, values, valid, row_ha)
        path = write_zone_raster(np.where(labels >= 0, labels + 1, -1), info)          # polygon value = zone number 1..n (labels are 0-based, -1 stays NoData)
        polygons = polygonize_zones(path)
    except ValueError as e:
        return {"error": f"create_zoning_map: {e}"}
    except Exception as e:
        return {"error": f"The zones could not be made: {e}"}
    finally:
        if path:
            with contextlib.suppress(OSError):
                os.remove(path)
    band_names = [layer.name() if band_no == 1 and layer.bandCount() == 1 else f"{layer.name()}@{band_no}" for layer, band_no, _r in layers]
    base = (output_name or "").strip() or "management_zones"
    mean_fields = "".join(f"&field=mean_{i + 1}:double" for i in range(len(band_names)))
    out = QgsVectorLayer("Polygon?field=zone:integer&field=label:string&field=cells:integer&field=area_ha:double&field=percent:double" + mean_fields, base, "memory")
    try:
        require_valid_layer(out)
    except ValueError as e:
        return {"error": str(e)}
    out.setCrs(first.crs())
    feats = []
    for s in stats:
        wkts = polygons.get(s["zone"], [])
        if not wkts:
            continue
        f = QgsFeature(out.fields())
        f.setGeometry(QgsGeometry.collectGeometry([QgsGeometry.fromWkt(w) for w in wkts]))
        f.setAttributes([s["zone"], legend_label(s["zone"], s["means"], band_names), s["cells"], round(s["area_ha"], 4), s["percent"], *[round(m, 6) for m in s["means"]]])
        feats.append(f)
    out.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(out)
    result = {
        "success": True, "layer_name": base, "zones": len(stats), "zones_asked": k, "rasters": band_names, "seed": seed, "smoothed": bool(smooth),
        "min_zone_area_ha": round(threshold, 4), "patches_merged": merged, "total_area_ha": round(total_ha, 4),
        "per_zone": [{"zone": s["zone"], "label": legend_label(s["zone"], s["means"], band_names), "area_ha": round(s["area_ha"], 4), "percent": s["percent"],
                      "means": {name: round(m, 6) for name, m in zip(band_names, s["means"], strict=True)}} for s in stats],
        "method": "seeded k-means on the standardised bands; zone 1 is the lowest mean of the first raster; patches below the minimum area merge into the neighbouring zone "
                  "with the nearest mean",
        "area_method": ("exact for the projected CRS" if is_geographic is False else "approximate for the geographic CRS (sphere, row by row)"),
        "note": NOTE,
    }
    if len(stats) < k:
        result["zones_note"] = f"{k} zones were asked for but {len(stats)} remain after merging small patches; lower min_zone_area_ha for more."
    return _with_alignment_note(result, align_note)
