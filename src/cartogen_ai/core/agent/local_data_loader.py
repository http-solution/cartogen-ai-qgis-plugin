# -*- coding: utf-8 -*-
"""Downloads a Geofabrik OpenStreetMap extract once and loads roads + health facilities from it.

The user-facing side (asking first, listing other sources) is local_data_sources.py and
chat_tab_widget.py's _ask_local_data_in_chat; see local_data_sources.py's docstring for why this
exists. Split the same way as the plugin's other network tools (ingest_osm_features,
fetch_geoboundaries): resolve_region/download_extract/extract_members are plain Python and safe
on a background thread; load_layers touches QgsProject and must run on the main thread.

What was verified against the real Jordan extract (2026-09-25, via HTTP range reads of the zip's
central directory and DBF headers, not assumed from docs): the shapefile members are named
gis_osm_<layer>_free_1.*; roads carry fclass/oneway/maxspeed; pois and pois_a carry fclass; and
99 of the 201 hospitals are building outlines in pois_a, which is why both files are read.
"""
import json
import os
import time
import urllib.request
import zipfile

from .local_data_sources import GEOFABRIK_INDEX_URL, HEALTH_FCLASSES, find_region
from .tools._urllib_retry import urlopen_with_retry

try:
    from qgis.core import (
        QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature,
        QgsFields, QgsField, QgsProject, QgsVectorFileWriter, QgsVectorLayer, QgsWkbTypes,
    )
    from qgis.PyQt.QtCore import QMetaType
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

_UA = {"User-Agent": "QGIS-AI-Assistant"}
INDEX_MAX_AGE_S = 30 * 24 * 3600    # region outlines barely change
EXTRACT_MAX_AGE_S = 7 * 24 * 3600   # Geofabrik rebuilds daily; a week-old copy is fine to reuse
LARGE_DOWNLOAD_BYTES = 150 * 1000 * 1000
MEMBERS = ("gis_osm_roads_free_1", "gis_osm_pois_free_1", "gis_osm_pois_a_free_1")


def data_dir():
    """Where downloads are kept: the project's data/00_raw/osm when the project is saved (the
    layout create_project_folder_structure makes), else a folder in the QGIS profile."""
    home = QgsProject.instance().homePath() if QGIS_AVAILABLE else ""
    if home:
        return os.path.join(home, "data", "00_raw", "osm")
    base = QgsApplication.qgisSettingsDirPath() if QGIS_AVAILABLE else os.path.expanduser("~")
    return os.path.join(base, "cartogen_ai", "data", "osm")


def _fresh(path, max_age_s):
    return os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_s


def load_index(cache_dir):
    """Geofabrik's region index with outlines (~3.8 MB), cached for 30 days."""
    path = os.path.join(cache_dir, "geofabrik-index-v1.json")
    if not _fresh(path, INDEX_MAX_AGE_S):
        os.makedirs(cache_dir, exist_ok=True)
        with urlopen_with_retry(urllib.request.Request(GEOFABRIK_INDEX_URL, headers=_UA), timeout=60) as r:
            body = r.read()
        json.loads(body)  # don't cache a truncated or error page
        with open(path, "wb") as f:
            f.write(body)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_region(lon, lat, cache_dir):
    """{"id", "name", "shp_url", "iso2", "size_bytes"} for the area, or {"error": ...}."""
    try:
        region = find_region(load_index(cache_dir), lon, lat)
    except Exception as e:
        return {"error": "Couldn't read Geofabrik's region list: %s" % e}
    if not region:
        return {"error": "No Geofabrik extract covers this location (%.3f, %.3f). Zoom the map to "
                         "your area of interest and try again." % (lat, lon)}
    try:
        req = urllib.request.Request(region["shp_url"], method="HEAD", headers=_UA)
        with urlopen_with_retry(req, timeout=30) as r:
            region["size_bytes"] = int(r.headers.get("Content-Length") or 0)
    except Exception:
        region["size_bytes"] = 0  # unknown size: the caller treats it as "ask first"
    return region


def download_extract(region, dest_dir, progress=None, is_cancelled=None):
    """Downloads the region's shapefile zip (reusing a copy under a week old). Returns its path.

    Streams to a .part file and renames at the end, so a cancelled or failed download never
    leaves something that looks like a finished zip for the reuse check to pick up."""
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, "%s-latest-free.shp.zip" % region["id"])
    if _fresh(path, EXTRACT_MAX_AGE_S) and zipfile.is_zipfile(path):
        return path
    part = path + ".part"
    req = urllib.request.Request(region["shp_url"], headers=_UA)
    with urlopen_with_retry(req, timeout=60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0) or region.get("size_bytes") or 0
        done = 0
        while True:
            if is_cancelled and is_cancelled():
                raise InterruptedError("Download cancelled")
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(100.0 * done / total)
    if not zipfile.is_zipfile(part):
        os.remove(part)
        raise ValueError("The download from Geofabrik isn't a valid zip file.")
    os.replace(part, path)
    return path


def extract_members(zip_path, out_dir, members=MEMBERS):
    """Unzips only the shapefiles needed (all their sidecar files), not the whole extract."""
    os.makedirs(out_dir, exist_ok=True)
    found = {}
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            stem, _ = os.path.splitext(os.path.basename(name))
            if stem in members:
                z.extract(name, out_dir)
                if name.endswith(".shp"):
                    found[stem] = os.path.join(out_dir, name)
    return found


def download_and_extract(region, dest_dir, progress=None, is_cancelled=None):
    """The whole background-thread phase. Returns {"shapefiles", "zip_path", "region"}."""
    zip_path = download_extract(region, dest_dir, progress, is_cancelled)
    shp = extract_members(zip_path, os.path.join(dest_dir, region["id"]))
    return {"shapefiles": shp, "zip_path": zip_path, "region": region}


# ----------------------------------------------------------- main thread --

def load_layers(result, themes):
    """Adds the road network and/or health facilities to the project. Main thread only.

    Returns {"layers": [{"name", "count"}], "errors": [...]}. Health facilities are written to a
    GeoPackage next to the extract (points from pois + centres of pois_a outlines), so they
    survive saving and reopening the project; a memory layer wouldn't."""
    shp = result.get("shapefiles") or {}
    region = result["region"]
    out = {"layers": [], "errors": []}
    project = QgsProject.instance()

    if "roads" in themes:
        path = shp.get("gis_osm_roads_free_1")
        lyr = QgsVectorLayer(path or "", "OSM Roads (%s)" % region["name"], "ogr")
        if path and lyr.isValid():
            project.addMapLayer(lyr)
            out["layers"].append({"name": lyr.name(), "count": lyr.featureCount()})
        else:
            out["errors"].append("The extract has no readable roads layer.")

    if "health_facilities" in themes:
        name = "Health Facilities (OSM, %s)" % region["name"]
        gpkg = os.path.join(os.path.dirname(shp.get("gis_osm_pois_free_1") or ""),
                            "health_facilities_%s.gpkg" % region["id"])
        count, error = _write_health_facilities(shp, gpkg)
        lyr = QgsVectorLayer(gpkg, name, "ogr") if not error else None
        if lyr is not None and lyr.isValid():
            project.addMapLayer(lyr)
            out["layers"].append({"name": name, "count": count})
        else:
            out["errors"].append(error or "Couldn't open the health facilities file.")
    return out


def _write_health_facilities(shp, gpkg):
    wanted = "fclass IN (%s)" % ", ".join("'%s'" % c for c in HEALTH_FCLASSES)
    fields = QgsFields()
    for fname in ("osm_id", "fclass", "name", "source_geom"):
        fields.append(QgsField(fname, QMetaType.Type.QString))
    crs = QgsCoordinateReferenceSystem("EPSG:4326")
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    writer = QgsVectorFileWriter.create(gpkg, fields, QgsWkbTypes.Type.Point, crs,
                                        QgsProject.instance().transformContext(), opts)
    if writer.hasError():
        return 0, "Couldn't write %s: %s" % (gpkg, writer.errorMessage())
    count = 0
    for stem, kind in (("gis_osm_pois_free_1", "point"), ("gis_osm_pois_a_free_1", "outline")):
        path = shp.get(stem)
        if not path:
            continue
        src = QgsVectorLayer(path, stem, "ogr")
        if not src.isValid():
            continue
        src.setSubsetString(wanted)
        for f in src.getFeatures():
            geom = f.geometry()
            if geom.isEmpty():
                continue
            if kind == "outline":
                geom = geom.pointOnSurface()  # inside the building, unlike a centroid of an L-shape
            nf = QgsFeature(fields)
            nf.setGeometry(geom)
            nf.setAttributes([str(f["osm_id"]), f["fclass"], f["name"], kind])
            writer.addFeature(nf)
            count += 1
    del writer  # flushes and closes the GeoPackage
    return count, None


def project_layer_facts():
    """[{"name", "geometry"}] for the open project, for local_data_sources.themes_missing."""
    facts = []
    if not QGIS_AVAILABLE:
        return facts
    kinds = {QgsWkbTypes.GeometryType.PointGeometry: "point",
             QgsWkbTypes.GeometryType.LineGeometry: "line",
             QgsWkbTypes.GeometryType.PolygonGeometry: "polygon"}
    for lyr in QgsProject.instance().mapLayers().values():
        if hasattr(lyr, "geometryType"):
            facts.append({"name": lyr.name(), "geometry": kinds.get(lyr.geometryType())})
        else:
            facts.append({"name": lyr.name(), "geometry": "raster"})
    return facts


def canvas_center_wgs84(canvas):
    """(lon, lat) of the map canvas centre, or None. Stays on this machine: it's only used to
    pick which Geofabrik extract to download, never sent to the LLM."""
    if canvas is None:
        return None
    try:
        center = canvas.extent().center()
        src = canvas.mapSettings().destinationCrs()
        wgs = QgsCoordinateReferenceSystem("EPSG:4326")
        if src.isValid() and src != wgs:
            center = QgsCoordinateTransform(src, wgs, QgsProject.instance()).transform(center)
        return center.x(), center.y()
    except Exception:
        return None
