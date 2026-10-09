# -*- coding: utf-8 -*-
"""Corridor and terrain operations that no other tool covered: contour lines, and splitting a line by zones.

2026-10-09 cost investigation: two of five realistic humanitarian scenarios could not be completed with the shipped tools. A highway
split by security exclusion zones needs the passable length as TWO different numbers (total length outside every zone, and the longest
continuous piece outside every zone), and a terrain study needs contour lines. Processing already provides the geometry (gdal:contour,
native:difference), so these are thin, checked wrappers that add what Processing does not: a size guard, the measurements, honest
metadata, and a styled result."""
import os

from .registry import register_tool
from ._qgis_enum_compat import resolve_qgis_enum  # noqa: F401  (kept for sibling modules' symmetry)

try:
    from qgis.core import (
        QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsDistanceArea, QgsFeature,
        QgsField, QgsGeometry, QgsLineSymbol, QgsProject, QgsRasterLayer, QgsRendererCategory, QgsVectorLayer, QgsWkbTypes,
    )
    from qgis.PyQt.QtCore import QVariant
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

try:
    import processing
except ImportError:
    processing = None

MAX_DEM_CELLS = 100_000_000            # contouring a larger raster is refused rather than freezing QGIS
MAX_CONTOURS_WARN = 20000
STATUS_COLOURS = {"compromised": "#d7191c", "clear": "#1a9641"}


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def utm_epsg_for(lon, lat):
    """EPSG code of the WGS84 UTM zone containing (lon, lat). Pure."""
    zone = int((lon + 180.0) // 6.0) + 1
    zone = max(1, min(60, zone))
    return (32600 if lat >= 0 else 32700) + zone


def summarise_pieces(clear_lengths_m, compromised_lengths_m):
    """The two highway answers, kept distinct. Pure.

    total passable length = everything outside every zone; longest continuous passable segment = the longest single connected
    piece outside every zone. They differ whenever a zone interrupts the line."""
    clear = [x for x in clear_lengths_m if x > 0]
    bad = [x for x in compromised_lengths_m if x > 0]
    return {
        "total_length_km": round((sum(clear) + sum(bad)) / 1000.0, 3),
        "clear_length_km": round(sum(clear) / 1000.0, 3),
        "compromised_length_km": round(sum(bad) / 1000.0, 3),
        "clear_segment_count": len(clear),
        "compromised_segment_count": len(bad),
        "longest_clear_segment_km": round(max(clear) / 1000.0, 3) if clear else 0.0,
    }


def _metric_crs(line_layer, lines):
    crs = line_layer.crs()
    if not crs.isGeographic():
        return crs
    centre = lines.boundingBox().center()
    return QgsCoordinateReferenceSystem(f"EPSG:{utm_epsg_for(centre.x(), centre.y())}")


def _distance_area(crs):
    area = QgsDistanceArea()
    area.setSourceCrs(crs, QgsProject.instance().transformContext())
    ellipsoid = QgsProject.instance().ellipsoid()
    area.setEllipsoid(ellipsoid if ellipsoid and ellipsoid != "NONE" else "WGS84")
    return area


def _geometries(layer, to_crs):
    transform = None
    if layer.crs() != to_crs:
        transform = QgsCoordinateTransform(layer.crs(), to_crs, QgsProject.instance())
    out = []
    for feature in layer.getFeatures():
        geometry = QgsGeometry(feature.geometry())
        if geometry is None or geometry.isEmpty():
            continue
        if transform is not None:
            geometry.transform(transform)
        out.append(geometry)
    return out


def _line_parts(geometry):
    return [part for part in geometry.asGeometryCollection()
            if part is not None and not part.isEmpty() and QgsWkbTypes.geometryType(part.wkbType()) == QgsWkbTypes.GeometryType.LineGeometry]


@register_tool(
    "split_lines_by_zones",
    "Split a line layer (a road, a highway, a pipeline) by a polygon layer of zones (exclusion zones, flood areas, buffers) into "
    "compromised pieces (inside any zone) and clear pieces (outside every zone), style them red and green, and report both the "
    "total passable length in km and the longest continuous passable segment in km (they are different numbers). Lengths are "
    "ellipsoidal. Connected line features are joined first, so a road stored as many OSM segments counts as one continuous road. "
    "Creates a new layer; the inputs are not changed.",
    {"type": "object", "properties": {
        "line_layer": {"type": "string", "description": "Name of the line layer."},
        "zone_layer": {"type": "string", "description": "Name of the polygon layer (for example the checkpoint buffers)."},
        "output_name": {"type": "string", "description": "Optional name of the result layer."}},
     "required": ["line_layer", "zone_layer"]},
)
def split_lines_by_zones(line_layer, zone_layer, output_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    lines_layer, zones_layer = _find_layer_by_name(line_layer), _find_layer_by_name(zone_layer)
    if lines_layer is None:
        return {"error": f"Layer '{line_layer}' not found"}
    if zones_layer is None:
        return {"error": f"Layer '{zone_layer}' not found"}
    if lines_layer.geometryType() != QgsWkbTypes.GeometryType.LineGeometry:
        return {"error": f"'{line_layer}' is not a line layer."}
    if zones_layer.geometryType() != QgsWkbTypes.GeometryType.PolygonGeometry:
        return {"error": f"'{zone_layer}' is not a polygon layer."}
    try:
        raw_lines = _geometries(lines_layer, lines_layer.crs())
        if not raw_lines:
            return {"error": f"'{line_layer}' has no line features."}
        probe = QgsGeometry.unaryUnion(raw_lines)
        metric = _metric_crs(lines_layer, probe)
        lines = QgsGeometry.unaryUnion(_geometries(lines_layer, metric))
        lines = lines.mergeLines() if not lines.isEmpty() else lines
        zone_geoms = _geometries(zones_layer, metric)
        if not zone_geoms:
            return {"error": f"'{zone_layer}' has no zone polygons."}
        zones = QgsGeometry.unaryUnion(zone_geoms)
        clear_parts = _line_parts(lines.difference(zones))
        bad_parts = _line_parts(lines.intersection(zones))
        measure = _distance_area(metric)
        clear_len = [measure.measureLength(part) for part in clear_parts]
        bad_len = [measure.measureLength(part) for part in bad_parts]

        out_name = output_name or f"{line_layer}_by_zones"
        result_layer = QgsVectorLayer(f"LineString?crs={lines_layer.crs().authid()}", out_name, "memory")
        provider = result_layer.dataProvider()
        provider.addAttributes([QgsField("status", QVariant.String), QgsField("length_km", QVariant.Double), QgsField("segment", QVariant.Int)])
        result_layer.updateFields()
        back = QgsCoordinateTransform(metric, lines_layer.crs(), QgsProject.instance()) if metric != lines_layer.crs() else None
        features = []
        for status, parts, lengths in (("clear", clear_parts, clear_len), ("compromised", bad_parts, bad_len)):
            for index, (part, length) in enumerate(zip(parts, lengths), 1):
                geometry = QgsGeometry(part)
                if back is not None:
                    geometry.transform(back)
                feature = QgsFeature(result_layer.fields())
                feature.setGeometry(geometry)
                feature.setAttributes([status, round(length / 1000.0, 3), index])
                features.append(feature)
        provider.addFeatures(features)
        result_layer.updateExtents()
        categories = [QgsRendererCategory(key, QgsLineSymbol.createSimple({"color": colour, "width": "1.2"}), key.capitalize())
                      for key, colour in STATUS_COLOURS.items()]
        result_layer.setRenderer(QgsCategorizedSymbolRenderer("status", categories))
        QgsProject.instance().addMapLayer(result_layer)
    except Exception as e:
        return {"error": f"split_lines_by_zones failed: {e}"}
    summary = summarise_pieces(clear_len, bad_len)
    return {"success": True, "layer_name": out_name, **summary,
            "definitions": {"clear_length_km": "total length outside every zone",
                            "longest_clear_segment_km": "longest single connected piece outside every zone"},
            "measured_in": f"ellipsoidal metres, computed in {metric.authid()} and reported in km"}


@register_tool(
    "generate_contours",
    "Create vector contour lines from a DEM raster layer at a fixed elevation interval (in the DEM's own elevation units, normally "
    "metres), as a new line layer with an 'ELEV' field. The interval is the vertical spacing between lines, NOT the accuracy of "
    "the terrain: the result reports the DEM's pixel size and source so the user can judge what the lines can show. Refuses very "
    "large rasters.",
    {"type": "object", "properties": {
        "raster_layer": {"type": "string", "description": "Name of the DEM raster layer."},
        "interval": {"type": "number", "description": "Elevation step between contour lines, default 10."},
        "band": {"type": "integer", "description": "Band number, default 1."},
        "output_name": {"type": "string"}},
     "required": ["raster_layer"]},
)
def generate_contours(raster_layer, interval=10.0, band=1, output_name=None):
    if not QGIS_AVAILABLE or processing is None:
        return {"error": "QGIS not available"}
    dem = _find_layer_by_name(raster_layer)
    if dem is None:
        return {"error": f"Layer '{raster_layer}' not found"}
    if not isinstance(dem, QgsRasterLayer):
        return {"error": f"'{raster_layer}' is not a raster layer."}
    try:
        interval = float(interval)
    except (TypeError, ValueError):
        return {"error": "interval must be a number."}
    if not interval > 0:
        return {"error": "interval must be greater than zero."}
    cells = dem.width() * dem.height()
    if cells > MAX_DEM_CELLS:
        return {"error": f"The raster has {cells:,} cells, above the {MAX_DEM_CELLS:,} limit for contouring; clip it first."}
    import tempfile
    path = os.path.join(tempfile.mkdtemp(prefix="cartogen_contours_"), "contours.gpkg")
    try:
        processing.run("gdal:contour", {"INPUT": dem, "BAND": int(band), "INTERVAL": interval, "FIELD_NAME": "ELEV",
                                        "CREATE_3D": False, "IGNORE_NODATA": False, "OFFSET": 0.0, "OUTPUT": path})
    except Exception as e:
        return {"error": f"gdal:contour failed: {e}"}
    name = output_name or f"{raster_layer}_contours_{interval:g}"
    layer = QgsVectorLayer(path, name, "ogr")
    if not layer.isValid():
        return {"error": "The contour result could not be loaded."}
    QgsProject.instance().addMapLayer(layer)
    pixel = (dem.rasterUnitsPerPixelX(), dem.rasterUnitsPerPixelY())
    result = {"success": True, "layer_name": name, "contour_count": layer.featureCount(), "interval": interval,
              "dem": {"layer": raster_layer, "source": dem.source().split("|", 1)[0], "crs": dem.crs().authid(),
                      "pixel_size_x": pixel[0], "pixel_size_y": pixel[1], "pixel_size_unit": dem.crs().mapUnits().name
                      if hasattr(dem.crs().mapUnits(), "name") else str(dem.crs().mapUnits())},
              "note": ("The interval is the vertical spacing of the lines. Their horizontal detail is limited by the DEM's pixel size "
                       "and source; do not describe the contours as accurate to the interval.")}
    if layer.featureCount() > MAX_CONTOURS_WARN:
        result["warning"] = f"{layer.featureCount():,} contour lines: consider a larger interval or a smaller area."
    return result
