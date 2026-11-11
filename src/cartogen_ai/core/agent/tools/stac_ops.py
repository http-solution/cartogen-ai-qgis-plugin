"""STAC load helpers (PLAN-023 R3-2), pure Python (no QGIS, no GDAL, no network).

load_stac_assets (stac_load_tool.py) downloads WINDOWS of Sentinel-2 L2A band images from Element 84's Earth Search catalogue: only the part of each Cloud-Optimized GeoTIFF that covers the
user's area crosses the network. What is decided here, and tested offline against a real item recorded from the service on 2026-11-11:
  * which bands may be asked for and their pixel size (S2_BANDS), at most MAX_ASSETS per request, at most MAX_ITEMS scenes;
  * which addresses may be read: only https addresses on the Sentinel-2 COG bucket (ALLOWED_HOSTS). GDAL follows redirects itself, outside the plugin's own network guard, so the set of hosts is
    kept to the one data provider, as for WorldPop. Landsat and the Copernicus elevation model are listed by the same catalogue but as s3:// addresses in requester-pays buckets, which need
    AWS credentials; they are NOT supported and a request for them is refused with that reason;
  * how big a request is before anything is downloaded: window cells x bytes per cell (the satellite bands are 16-bit), compared with a hard cap;
  * what is written beside every downloaded file (provenance) so the origin, date, cloud cover and the licence notice travel with it.
Known answers (the tests): a 0.1 x 0.1 degree window at the equator on a 10 m band is 1,113 x 1,105 = 1,230,... cells, about 2.4 MB at 2 bytes; a non-https, other-host, userinfo or s3 address is
refused; 7 bands, 4 scenes, an unknown band name and a window above the cap are refused."""
import math
import re
from datetime import date
from urllib.parse import urlparse

COLLECTION = "sentinel-2-l2a"
ALLOWED_HOSTS = frozenset({"sentinel-cogs.s3.us-west-2.amazonaws.com"})
# band name in the catalogue -> pixel size in metres (Sentinel-2 L2A COG assets of Earth Search v1)
S2_BANDS = {"blue": 10, "green": 10, "red": 10, "nir": 10, "rededge1": 20, "rededge2": 20, "rededge3": 20, "nir08": 20, "nir09": 60, "swir16": 20, "swir22": 20, "scl": 20, "coastal": 60}
MAX_ASSETS = 6
MAX_ITEMS = 3
BYTES_PER_CELL = 2                 # uint16 reflectance and class bands
MAX_WINDOW_CELLS = 60_000_000      # per band image: the same cell budget the raster tools use
MAX_TOTAL_BYTES = 600 * 1024 * 1024
M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON_EQUATOR = 111_320.0
LICENCE_NOTICE = "Contains modified Copernicus Sentinel data ({year}). Source: Earth Search (Element 84) Sentinel-2 L2A Cloud-Optimized GeoTIFFs."
_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")


def check_request(bbox, start_date, end_date, assets, max_cloud, limit):
    """Error text for a request that cannot be run, else None. Pure."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox):
        return "bbox must be four numbers: min_lon, min_lat, max_lon, max_lat (WGS84 degrees)."
    if not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
        return "bbox is not a valid WGS84 box (min_lon < max_lon within -180..180, min_lat < max_lat within -90..90)."
    try:
        first, last = date.fromisoformat(str(start_date)[:10]), date.fromisoformat(str(end_date)[:10])
    except ValueError:
        return f"start_date and end_date must be dates written YYYY-MM-DD (got {start_date!r} and {end_date!r})."
    if first > last:
        return f"start_date {start_date} is after end_date {end_date}."
    if not isinstance(assets, list) or not 1 <= len(assets) <= MAX_ASSETS:
        return f"assets must be a list of 1 to {MAX_ASSETS} band names from: {', '.join(S2_BANDS)}."
    unknown = [a for a in assets if a not in S2_BANDS]
    if unknown:
        hint = " (Landsat and the elevation model are not supported: their files are in requester-pays storage that needs AWS credentials.)" if any(str(u).lower().startswith(("lan", "cop", "dem")) for u in unknown) else ""
        return f"Unknown band(s) {unknown}. Sentinel-2 L2A bands that can be loaded: {', '.join(S2_BANDS)}.{hint}"
    if len(set(assets)) != len(assets):
        return "assets lists a band more than once."
    if isinstance(max_cloud, bool) or not isinstance(max_cloud, (int, float)) or not 0 <= max_cloud <= 100:
        return "max_cloud must be a number between 0 and 100 (percent)."
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ITEMS:
        return f"limit must be a whole number from 1 to {MAX_ITEMS} (the number of scenes to load)."
    return None


def check_item_ids(item_ids):
    """Error text when the scene ids a confirmed call carries are not plain ids, else None. Pure."""
    if not isinstance(item_ids, list) or not 1 <= len(item_ids) <= MAX_ITEMS or not all(isinstance(i, str) and _ID.match(i) for i in item_ids):
        return f"item_ids must be 1 to {MAX_ITEMS} scene ids as returned by the preview."
    return None


def asset_url_ok(href):
    """True only for an https address on an allowed host, without user information or a port. Pure."""
    parts = urlparse(href or "")
    return parts.scheme == "https" and (parts.hostname or "").lower() in ALLOWED_HOSTS and not parts.username and parts.port is None


def refusal_for_href(href):
    """The reason an address may not be read, else None. Pure."""
    if asset_url_ok(href):
        return None
    if str(href or "").lower().startswith("s3://"):
        return "this file is in an s3:// bucket (requester-pays storage) that needs AWS credentials, which are not supported"
    return "this address is not on the allowed Sentinel-2 host"


def parse_items(response):
    """[{id, datetime, cloud, epsg, bbox, assets: {name: href}}] from a STAC search response (a dict). Pure."""
    out = []
    for feat in (response or {}).get("features", []) if isinstance(response, dict) else []:
        props = feat.get("properties") or {}
        out.append({"id": feat.get("id"), "datetime": props.get("datetime"), "cloud": props.get("eo:cloud_cover"), "epsg": props.get("proj:epsg"),
                    "bbox": feat.get("bbox"), "assets": {k: (v or {}).get("href") for k, v in (feat.get("assets") or {}).items() if isinstance(v, dict)}})
    return out


def bbox_overlap(a, b):
    """The overlap of two (min_lon, min_lat, max_lon, max_lat) boxes, or None when they do not overlap. Pure."""
    box = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return box if box[0] < box[2] and box[1] < box[3] else None


def window_cells(box, resolution_m):
    """Cells of a (min_lon, min_lat, max_lon, max_lat) window at `resolution_m`, with degrees turned into metres at the box's mid latitude. Pure."""
    mid = math.radians((box[1] + box[3]) / 2.0)
    width_m = (box[2] - box[0]) * M_PER_DEG_LON_EQUATOR * math.cos(mid)
    height_m = (box[3] - box[1]) * M_PER_DEG_LAT
    return max(1, math.ceil(width_m / resolution_m)) * max(1, math.ceil(height_m / resolution_m))


def human_size(nbytes):
    """'2.4 MB' style text. Pure."""
    for unit, size in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if nbytes >= size:
            return f"{nbytes / size:.1f} {unit}"
    return f"{nbytes} bytes"


def plan(items, assets, window):
    """([{item, asset, href, cells, bytes}], problems): what would be downloaded for `window` and why anything cannot be. Pure.

    A band missing from a scene, an address that may not be read, a scene whose footprint does not meet the window, a window above MAX_WINDOW_CELLS and a total above MAX_TOTAL_BYTES are problems
    (each names the scene and band) and are never silently skipped."""
    rows, problems = [], []
    for item in items:
        box = bbox_overlap(window, item["bbox"]) if item.get("bbox") else window
        if box is None:
            problems.append(f"{item['id']}: the scene does not cover the requested area")
            continue
        for name in assets:
            href = item["assets"].get(name)
            if not href:
                problems.append(f"{item['id']}: has no '{name}' band")
                continue
            why = refusal_for_href(href)
            if why:
                problems.append(f"{item['id']} {name}: {why}")
                continue
            cells = window_cells(box, S2_BANDS[name])
            if cells > MAX_WINDOW_CELLS:
                problems.append(f"{item['id']} {name}: the window is {cells:,} cells, above the limit of {MAX_WINDOW_CELLS:,}; ask for a smaller area")
                continue
            rows.append({"item": item["id"], "asset": name, "href": href, "cells": cells, "bytes": cells * BYTES_PER_CELL, "window": list(box)})
    if sum(r["bytes"] for r in rows) > MAX_TOTAL_BYTES:
        problems.append(f"the request is about {human_size(sum(r['bytes'] for r in rows))} before compression, above the limit of {human_size(MAX_TOTAL_BYTES)}; ask for fewer bands, scenes or a smaller area")
        rows = []
    return rows, problems


def provenance(item, row, retrieved_on):
    """The record written beside a downloaded file: where it came from, when, and the licence notice. Pure."""
    year = str(item.get("datetime") or retrieved_on)[:4]
    return {"source": "Earth Search (Element 84) STAC API", "collection": COLLECTION, "scene": item["id"], "scene_datetime": item.get("datetime"),
            "cloud_cover_percent": item.get("cloud"), "band": row["asset"], "source_address": row["href"], "window_wgs84": row["window"],
            "retrieved_on": retrieved_on, "licence_notice": LICENCE_NOTICE.format(year=year),
            "note": "Only the window of the band image that covers the requested area was downloaded; pixel values are the provider's own (not rescaled)."}
