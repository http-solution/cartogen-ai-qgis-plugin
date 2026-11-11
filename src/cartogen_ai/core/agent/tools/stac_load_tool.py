"""load_stac_assets (PLAN-023 R3-2): windows of Sentinel-2 L2A band images from Earth Search, clipped to the user's area, added to the project with a provenance record.

Why windows: each band image is a Cloud-Optimized GeoTIFF of a whole 110 km scene (100 to 200 MB per band). GDAL reads it through /vsicurl/ with HTTP range requests, so only the cells inside the
area cross the network, and the result is a small compressed GeoTIFF kept in the project's data folder (data/00_raw/stac, or a folder in the QGIS profile for an unsaved project). The helpers in
stac_ops.py (pure, tested against a real recorded item) decide which bands and addresses are allowed, size the request and write the provenance. Nothing is downloaded before the user has seen the
scenes, the bands and the estimated size on a confirmation card (the same F22 rule as the other downloads), and a confirmed call fetches exactly the scenes the card named.
Only Sentinel-2 L2A is supported: the same catalogue lists Landsat and the Copernicus elevation model as s3:// requester-pays files that need AWS credentials. No key is needed for Sentinel-2.
Written without a QGIS install; tests/test_stac_load_tool_live.py is its first execution in CI and skips (rather than fails) when the network or the service is unavailable."""
import datetime
import json
import os

from ...logger import log_event
from ...net import build_request as _net_build_request
from ...net import read_capped as _read_capped
from ...net import urlopen as _qgis_urlopen
from . import stac_ops as so
from .attribute_edit_tools import preview
from .registry import register_tool

try:
    from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsRasterLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
_QUOTA = {"count": 0}
_MAX_SEARCHES = 20


def _bbox_from_layer(layer_name):
    """((min_lon, min_lat, max_lon, max_lat), error): the WGS84 extent of a project layer. Needs QGIS."""
    layers = QgsProject.instance().mapLayersByName(layer_name)
    if not layers:
        return None, f"Layer '{layer_name}' not found."
    layer = layers[0]
    box = layer.extent()
    if box.isEmpty() or not layer.crs().isValid():
        return None, f"Layer '{layer_name}' has no usable extent or coordinate system."
    to_wgs = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
    box = to_wgs.transformBoundingBox(box)
    return (box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum()), None


def _search(bbox, start_date, end_date, max_cloud, limit, item_ids=None):
    """(items, error): scenes from the catalogue, newest first (or exactly `item_ids`). Needs the network."""
    if _QUOTA["count"] >= _MAX_SEARCHES:
        return None, f"STAC query quota exceeded for this session (max {_MAX_SEARCHES}); reload the plugin to reset."
    payload = {"collections": [so.COLLECTION], "limit": limit}
    if item_ids:
        payload["ids"] = item_ids
    else:
        payload.update(bbox=list(bbox), datetime=f"{start_date}T00:00:00Z/{end_date}T23:59:59Z", query={"eo:cloud_cover": {"lte": max_cloud}},
                       sortby=[{"field": "properties.datetime", "direction": "desc"}])
    try:
        request = _net_build_request(SEARCH_URL, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "QGIS-AI-Assistant"})
        _QUOTA["count"] += 1
        with _qgis_urlopen(request, timeout=20) as response:
            return so.parse_items(json.loads(_read_capped(response).decode())), None
    except Exception as e:
        return None, f"STAC API query failed: {e}"


def cache_dir():
    """Folder for the clipped band files: <project>/data/00_raw/stac, or a folder in the QGIS profile for an unsaved project. Needs QGIS."""
    from ..local_data_loader import data_dir
    return os.path.join(os.path.dirname(data_dir()), "stac")


def _clip_window(href, window, dest):
    """Write the part of the band image at `href` inside `window` (WGS84) to a compressed GeoTIFF at `dest`. Needs GDAL and the network. Raises RuntimeError with a readable message."""
    try:
        from osgeo import gdal
    except ImportError as e:
        raise RuntimeError(f"GDAL Python bindings are not available ({e}).") from e
    gdal.UseExceptions()
    options = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "GDAL_HTTP_TIMEOUT": "120", "GDAL_HTTP_MAX_RETRY": "2"}
    for key, value in options.items():
        gdal.SetThreadLocalConfigOption(key, value)
    try:
        source = gdal.Open("/vsicurl/" + href)
        out = gdal.Translate(dest, source, projWin=[window[0], window[3], window[2], window[1]], projWinSRS="EPSG:4326", creationOptions=["COMPRESS=DEFLATE", "TILED=YES"])
        if out is None or out.RasterXSize < 1 or out.RasterYSize < 1:
            raise RuntimeError("GDAL returned an empty window.")
        size = (out.RasterXSize, out.RasterYSize)
        out = None
        source = None
        return size
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(str(e)) from e
    finally:
        for key in options:
            gdal.SetThreadLocalConfigOption(key, None)


def prepare_request(layer_name=None, bbox=None):
    """MAIN THREAD part (it reads QgsProject): {"bbox": ..., "folder": ...} with the area from a layer when one is named, or {"error": ...}. Needs QGIS."""
    if bbox is None and layer_name:
        bbox, err = _bbox_from_layer(layer_name)
        if err:
            return {"error": err}
    return {"bbox": bbox, "folder": cache_dir()}


def load_stac_assets_network_phase(start_date, end_date, assets, bbox, folder, max_cloud=20, limit=1, item_ids=None, confirmed=False):
    """ANY-THREAD part (no QgsProject): validate, search the catalogue, plan, and either return the preview card or download the windows into `folder` and write their provenance.
    Returns {"error": ...}, a PREVIEW_REQUIRED card, or {"files": [...], ...} for add_stac_layers_main_thread_phase. Needs the network (and GDAL when confirmed)."""
    problem = so.check_request(bbox, start_date, end_date, assets, max_cloud, limit)
    if problem:
        return {"error": problem}
    if item_ids is not None and so.check_item_ids(item_ids):
        return {"error": so.check_item_ids(item_ids)}
    bbox = tuple(float(v) for v in bbox)
    items, err = _search(bbox, str(start_date)[:10], str(end_date)[:10], max_cloud, limit, item_ids)
    if err:
        return {"error": err}
    if not items:
        return {"error": "The service returned no Sentinel-2 scenes for this area, dates and cloud limit. Widen the dates or the cloud limit.", "scene_count": 0}
    rows, problems = so.plan(items, assets, bbox)
    if not rows:
        return {"error": "Nothing can be downloaded: " + "; ".join(problems), "problems": problems}
    total = sum(r["bytes"] for r in rows)
    scenes = [{"id": i["id"], "datetime": i["datetime"], "cloud_cover": i["cloud"]} for i in items if any(r["item"] == i["id"] for r in rows)]
    if not confirmed:
        arguments = {"start_date": str(start_date)[:10], "end_date": str(end_date)[:10], "assets": assets, "bbox": list(bbox), "max_cloud": max_cloud, "limit": limit,
                     "item_ids": [s["id"] for s in scenes]}
        card = preview("load_stac_assets", arguments,
                       f"Download {len(rows)} band window(s) from {len(scenes)} Sentinel-2 scene(s), about {so.human_size(total)} before compression (only your area, not the whole scene). "
                       "After you confirm, QGIS may pause until the download finishes.",
                       "# only the window crosses the network (HTTP range requests):\ngdal.Translate(dest, gdal.Open('/vsicurl/<band address>'), projWin=<your area>, projWinSRS='EPSG:4326')")
        card["is_destructive"] = False                      # adds files and layers; nothing is changed or removed
        card["scenes"], card["estimate_bytes"] = scenes, total
        if problems:
            card["not_included"] = problems
        return card
    os.makedirs(folder, exist_ok=True)
    by_id = {i["id"]: i for i in items}
    today = datetime.date.today().isoformat()
    made, failed = [], []
    for row in rows:
        name = f"{row['item']}_{row['asset']}"
        dest = os.path.join(folder, name + ".tif")
        if os.path.exists(dest):
            made.append({"layer": name, "file": dest, "reused": True})
            continue                                         # never overwritten; the same window of the same scene is the same file
        try:
            width, height = _clip_window(row["href"], row["window"], dest)
        except RuntimeError as e:
            failed.append(f"{name}: {e}")
            continue
        with open(os.path.join(folder, name + ".provenance.json"), "w", encoding="utf-8") as fh:
            json.dump(so.provenance(by_id[row["item"]], row, today), fh, indent=1)
        made.append({"layer": name, "file": dest, "width": width, "height": height, "bytes_on_disk": os.path.getsize(dest)})
    log_event("stac_load", scenes=len(scenes), bands=len(rows), loaded=len(made), failed=len(failed))
    if not made:
        return {"error": "No band could be downloaded: " + "; ".join(failed), "problems": failed}
    return {"files": made, "scenes": scenes, "folder": folder, "problems": [*failed, *problems], "today": today}


def add_stac_layers_main_thread_phase(result):
    """MAIN THREAD part: add the downloaded files to the project and build the reply. An error or a preview card passes through unchanged. Needs QGIS."""
    if "files" not in result:
        return result
    made, failed = result["files"], list(result["problems"])
    for entry in made:
        layer = QgsRasterLayer(entry["file"], entry["layer"])
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
        else:
            failed.append(f"{entry['layer']}: the file was written but QGIS could not open it")
    scenes = result["scenes"]
    out = {"success": True, "layers": made, "scenes": scenes, "folder": result["folder"],
           "licence_notice": so.LICENCE_NOTICE.format(year=str(scenes[0]["datetime"] or result["today"])[:4]),
           "note": "Each file has a .provenance.json beside it. The bands are 16-bit reflectance as the provider publishes them (scale 0.0001, offset -0.1 in the catalogue), not rescaled."}
    if failed:
        out["problems"] = failed
    return out


@register_tool(
    "load_stac_assets",
    "Download Sentinel-2 satellite band images (Earth Search, no key) for the user's AREA ONLY and add them to the project: only the part of each band image that covers the area is "
    "downloaded, so a few megabytes instead of a whole scene. Give the area as `bbox` (WGS84 min_lon, min_lat, max_lon, max_lat) or `layer_name` (that layer's extent), a date range, and the bands "
    "in `assets` (blue, green, red, nir, nir08, rededge1-3, swir16, swir22, coastal, nir09, scl; at most 6). max_cloud (percent, default 20) and limit (1 to 3 scenes, default 1, newest first). "
    "A preview lists the scenes, the bands and the estimated size first; nothing is downloaded until it is confirmed, and the confirmed call fetches exactly the scenes the preview named. Each file "
    "gets a provenance record and the Copernicus Sentinel licence notice. Landsat and the elevation model are not supported (they need AWS credentials). To only LIST scenes use "
    "search_stac_satellite_imagery.",
    {"type": "object", "properties": {
        "bbox": {"type": "array", "items": {"type": "number"}, "description": "WGS84 [min_lon, min_lat, max_lon, max_lat]; or use layer_name."},
        "layer_name": {"type": "string", "description": "A project layer whose extent is the area."},
        "start_date": {"type": "string", "description": "YYYY-MM-DD"}, "end_date": {"type": "string", "description": "YYYY-MM-DD"},
        "assets": {"type": "array", "items": {"type": "string"}, "description": "Band names such as red, nir, swir16 (1 to 6)."},
        "max_cloud": {"type": "number", "description": "Largest cloud cover in percent (default 20)."},
        "limit": {"type": "integer", "description": "Number of scenes, 1 to 3 (default 1)."}},
     "required": ["start_date", "end_date", "assets"]},
    keywords=["download sentinel-2", "load sentinel-2 bands", "get satellite imagery for my area", "download satellite images for the layer extent", "load the red and near infrared bands",
              "fetch sentinel 2 imagery for my study area", "get sentinel-2 bands for this area", "download the latest satellite scene for my area", "load satellite bands for ndvi",
              "stac assets", "download sentinel imagery clipped to my area"],
)
def load_stac_assets(start_date, end_date, assets, bbox=None, layer_name=None, max_cloud=20, limit=1, item_ids=None, confirmed=False):
    """The three phases in sequence on the calling thread: how a direct call (and the confirmed Apply button) runs. The agent loop instead runs the middle phase on its worker thread
    (TWO_PHASE_TOOLS in agent_orchestrator.py), so a search never waits on the network on QGIS's GUI thread."""
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    prepared = prepare_request(layer_name, bbox)
    if "error" in prepared:
        return prepared
    result = load_stac_assets_network_phase(start_date, end_date, assets, prepared["bbox"], prepared["folder"], max_cloud, limit, item_ids, confirmed)
    return add_stac_layers_main_thread_phase(result)
