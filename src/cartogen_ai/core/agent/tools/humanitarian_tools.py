# -*- coding: utf-8 -*-
"""
Humanitarian Data Discovery & Fetch Tools for Cartogen AI.
Interacts with Humanitarian Data Exchange (HDX), OSM Overpass API, geoBoundaries,
and Microsoft's Global ML Building Footprints.
"""

import re
import json
import math
import urllib.request
import urllib.parse
import urllib.error
from datetime import date
from .registry import register_tool
from ...logger import log_event
from ._cache_utils import TTLCache
from ._urllib_retry import urlopen_with_retry
from ._qgis_enum_compat import resolve_qgis_enum
from .. import coordinates as _coords
# SSRF protection (vector_tools.py's add_layer_from_path/_prefetch_url_to_temp already has
# this, adversarially tested -- confirmed loopback/private/link-local/metadata addresses and
# unsafe redirect targets are rejected before any bytes are fetched). Found missing here
# entirely during a 2026-09-13 security audit (SEC-001): every function in this file that
# does a SECOND fetch using a URL taken from a FIRST API response's own body (HDX's
# resources[].url, geoBoundaries' gjDownloadURL, the Bing tile index's Url column, WorldPop's
# files[0]) was fetching that second URL with plain urllib.request.urlopen -- no hostname/IP
# validation, no redirect re-checking -- even though every one of those first responses is
# genuinely external, third-party-published content. Reused here rather than duplicated.
from .vector_tools import _is_safe_url, _build_safe_opener

def _cleanup_cached_local_path(key, value):
    """TTLCache on_evict callback (SEC-004, 2026-09-14 audit): several of this file's cached
    results carry local_path, a real temp file on disk (fetch_geoboundaries_network_phase,
    fetch_hdx_admin_boundaries_network_phase, fetch_worldpop_population_network_phase) --
    deliberately kept alive while the cache entry is live, so a repeat call within the TTL
    window reuses the already-downloaded file instead of re-fetching (see each function's own
    "never-deleted temp file" comments). Once the cache entry itself expires or is replaced,
    nothing else references that path any more, so it's safe to delete here. Not every cached
    value has a local_path (the tile-index CSV, location lookups, etc. don't) -- silently a
    no-op for those. Deliberately does NOT touch a fresh call's OWN new local_path (that's a
    different dict, only the evicted OLD one is passed in here)."""
    import os
    if isinstance(value, dict):
        local_path = value.get("local_path")
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except OSError:
                pass


# Session-scoped cache for repeated identical lookups -- HDX/OSM/geoBoundaries
# data doesn't change minute-to-minute, so a re-query with the same arguments
# within a session (e.g. the model double-checking something) costs nothing.
_LOOKUP_CACHE = TTLCache(ttl_seconds=1800, on_evict=_cleanup_cached_local_path)

try:
    from qgis.core import (
        QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
        QgsPalLayerSettings, QgsTextFormat, QgsTextBackgroundSettings,
        QgsVectorLayerSimpleLabeling, QgsSymbol, QgsSingleSymbolRenderer,
        QgsRasterLayer, QgsCoordinateTransform, QgsCoordinateReferenceSystem,
    )
    from qgis.PyQt.QtGui import QColor
    QGIS_AVAILABLE = True
    # QGIS 4.x/Qt6 scopes this under QgsTextBackgroundSettings.ShapeType.
    # ShapeRectangle; QGIS 3.x/Qt5 exposes it flat. Resolved once here rather
    # than assuming one form -- see _qgis_enum_compat.py.
    _SHAPE_RECTANGLE = resolve_qgis_enum(QgsTextBackgroundSettings, "ShapeType", "ShapeRectangle")
except ImportError:
    QGIS_AVAILABLE = False
    _SHAPE_RECTANGLE = None


@register_tool("search_hdx_datasets", "Search Humanitarian Data Exchange (HDX) for datasets by query.", {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]})
def search_hdx_datasets(query: str, limit: int = 5):
    """Queries HDX CKAN API for spatial/humanitarian datasets."""
    cache_key = ("hdx", query, limit)
    cached = _LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    encoded = urllib.parse.quote(query)
    url = f"https://data.humdata.org/api/3/action/package_search?q={encoded}&rows={limit}"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'QGIS-AI-Assistant'})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode())
            results = data.get("result", {}).get("results", [])
            output = []
            for item in results:
                resources = [
                    {"name": r.get("name"), "format": r.get("format"), "url": r.get("url")}
                    for r in item.get("resources", [])
                    if r.get("format", "").lower() in ("geojson", "csv", "shp", "zip", "kml", "gpkg")
                ]
                output.append({
                    "title": item.get("title"),
                    "name": item.get("name"),
                    "organization": item.get("organization", {}).get("title"),
                    "spatial": item.get("subnational") or item.get("groups", [{}])[0].get("title"),
                    "resources": resources,
                })
            result = {"success": True, "query": query, "datasets": output}
            _LOOKUP_CACHE.set(cache_key, result)
            return result
    except Exception as e:
        return {"error": f"HDX query failed: {e}"}


def _fts_request(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'QGIS-AI-Assistant'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode())


@register_tool(
    "fetch_fts_funding_data",
    "Fetch humanitarian funding data from OCHA's Financial Tracking Service (FTS) for a country's "
    "response plan -- requirements, funding received, coverage percentage, and the funding gap. "
    "If year/plan_id are omitted, auto-selects the most recent plan and reports that it did so; if "
    "more than one plan matches (a country can run several concurrent plans in the same year, e.g. "
    "a regional migrant response alongside the main response plan), returns the candidate list "
    "instead of guessing which one you meant -- call again with plan_id set to one of those. "
    "Funding figures are a live snapshot from FTS, not a final/certain total -- state that when "
    "presenting them, the same way you would any other point-in-time data.",
    {
        "type": "object",
        "properties": {
            "country_iso3": {"type": "string", "description": "3-letter ISO country code, e.g. 'YEM'."},
            "year": {"type": "integer", "description": "Response plan year, e.g. 2024. Omit to auto-select the most recent."},
            "plan_id": {"type": "integer", "description": "A specific FTS plan ID (from a prior call's plan list) to fetch directly."},
        },
        "required": ["country_iso3"],
    },
)
def fetch_fts_funding_data(country_iso3, year=None, plan_id=None):
    country_iso3 = (country_iso3 or "").strip().upper()
    if len(country_iso3) != 3 or not country_iso3.isalpha():
        return {"error": "country_iso3 must be a 3-letter ISO country code, e.g. 'YEM'."}

    cache_key = ("fts", country_iso3, year, plan_id)
    cached = _LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    try:
        auto_selected = False
        if plan_id is None:
            plans_data = _fts_request(f"https://api.hpc.tools/v1/public/plan/country/{country_iso3}")
            plans = plans_data.get("data", [])
            if not plans:
                return {"error": f"No FTS response plans found for '{country_iso3}' -- check the ISO3 code is correct."}

            if year:
                matches = [p for p in plans if str(year) in [str(y.get("year")) for y in p.get("years", [])]]
                if not matches:
                    return {"error": f"No FTS response plans found for {country_iso3} in {year}."}
            else:
                latest_year = max(
                    (int(y.get("year")) for p in plans for y in p.get("years", []) if y.get("year")),
                    default=None,
                )
                if latest_year is None:
                    return {"error": f"Could not determine plan years for {country_iso3} from FTS."}
                matches = [p for p in plans if str(latest_year) in [str(y.get("year")) for y in p.get("years", [])]]
                auto_selected = True

            if len(matches) > 1:
                candidates = [
                    {
                        "plan_id": p.get("id"),
                        "name": p.get("planVersion", {}).get("name"),
                        "years": [y.get("year") for y in p.get("years", [])],
                    }
                    for p in matches
                ]
                return {
                    "status": "PLAN_SUGGESTION",
                    "message": (
                        f"{len(matches)} matching FTS plans found for {country_iso3}"
                        + (f" in {year}" if year else " in the most recent year")
                        + " -- call again with plan_id set to one of these."
                    ),
                    "plans": candidates,
                }

            plan = matches[0]
            resolved_plan_id = plan.get("id")
            requirements = plan.get("revisedRequirements") or plan.get("origRequirements")
            plan_name = plan.get("planVersion", {}).get("name")
        else:
            resolved_plan_id = plan_id
            plan_data = _fts_request(f"https://api.hpc.tools/v1/public/plan/id/{plan_id}")
            plan = plan_data.get("data", {})
            if not plan:
                return {"error": f"No FTS plan found with id {plan_id}."}
            requirements = plan.get("revisedRequirements") or plan.get("origRequirements")
            plan_name = plan.get("planVersion", {}).get("name")

        if not requirements:
            return {"error": f"FTS plan {resolved_plan_id} has no requirements figure on record."}

        flow_data = _fts_request(f"https://api.hpc.tools/v1/public/fts/flow?planId={resolved_plan_id}")
        funding_received = flow_data.get("data", {}).get("incoming", {}).get("fundingTotal")
        if funding_received is None:
            return {"error": f"Could not read a funding total from FTS for plan {resolved_plan_id} -- the API response shape may have changed."}

        gap = requirements - funding_received
        coverage_percent = round((funding_received / requirements) * 100, 1)

        result = {
            "success": True,
            "country_iso3": country_iso3,
            "plan_id": resolved_plan_id,
            "plan_name": plan_name,
            "requirements_usd": requirements,
            "funding_received_usd": funding_received,
            "gap_usd": gap,
            "coverage_percent": coverage_percent,
            "auto_selected_plan": auto_selected,
            "source": "OCHA Financial Tracking Service (fts.unocha.org), live snapshot",
        }
        _LOOKUP_CACHE.set(cache_key, result)
        return result
    except Exception as e:
        return {"error": f"fetch_fts_funding_data failed: {e}"}


@register_tool("fetch_osm_features", "Fetch OpenStreetMap vector features via Overpass API for a bounding box.", {"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}, "bbox": {"type": "array", "items": {"type": "number"}}}, "required": ["key", "value", "bbox"]})
def fetch_osm_features(key: str, value: str, bbox: list):
    """Fetches OSM features (e.g. key='amenity', value='hospital', bbox=[min_lat, min_lon, max_lat, max_lon])."""
    if len(bbox) != 4:
        return {"error": "bbox must be list of 4 numbers [south, west, north, east]"}

    cache_key = ("osm", key, value, tuple(bbox))
    cached = _LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    s, w, n, e = bbox
    # Escape key and value strings for Overpass QL string literal safety
    clean_key = re.sub(r'[^a-zA-Z0-9_:-]', '', key)
    clean_value = value.replace('\\', '\\\\').replace('"', '\\"')

    overpass_ql = f'[out:json][timeout:25];(node["{clean_key}"="{clean_value}"]({s},{w},{n},{e});way["{clean_key}"="{clean_value}"]({s},{w},{n},{e}););out body;>;out skel qt;'
    url = "https://overpass-api.de/api/interpreter"

    try:
        req = urllib.request.Request(url, data=overpass_ql.encode('utf-8'), headers={'User-Agent': 'QGIS-AI-Assistant'})
        # 30s, not the usual 15s -- the query itself requests a 25s server-side
        # budget ([timeout:25] above), so a client timeout below that would abort
        # legitimate slow-but-still-running queries before the server's own limit.
        with urllib.request.urlopen(req, timeout=30) as response:
            res_json = json.loads(response.read().decode())
            elements = res_json.get("elements", [])
            nodes = [el for el in elements if el.get("type") == "node"]

            features_summary = []
            for node in nodes[:50]:
                tags = node.get("tags", {})
                features_summary.append({
                    "id": node.get("id"),
                    "name": tags.get("name", "Unnamed"),
                    "lat": node.get("lat"),
                    "lon": node.get("lon"),
                    "tags": tags,
                })

            result = {
                "success": True,
                "key": key,
                "value": value,
                "feature_count": len(nodes),
                "samples": features_summary,
            }
            _LOOKUP_CACHE.set(cache_key, result)
            return result
    except Exception as e:
        return {"error": f"Overpass API request failed: {e}"}


_OSM_LINEAR_KEYS = frozenset({"highway", "railway", "waterway", "aerialway"})
_OVERPASS_RETRIES = 3            # 4 attempts in total
_OVERPASS_BACKOFF_SECONDS = 3.0  # waits of 3, 6 and 9 s between them


def _osm_feature(elem, clean_key, clean_value, geometry):
    tags = elem.get("tags", {})
    feature_name = tags.get("name:en") or tags.get("name") or tags.get("operator") or f"{clean_key}_{elem.get('id')}"
    props = {
        "id": elem.get("id"),
        "osm_type": elem.get("type"),
        "name": str(feature_name),
        clean_key: str(tags.get(clean_key, clean_value)),
    }
    for k, v in tags.items():
        if k not in props and isinstance(v, (str, int, float, bool)):
            props[k] = v
    return {"type": "Feature", "geometry": geometry, "properties": props}


def ingest_osm_features_network_phase(
    key: str,
    value: str,
    bbox: list = None,
    center_lat: float = None,
    center_lon: float = None,
    radius_km: float = None,
    layer_name: str = None,
) -> dict:
    """Pure network phase: queries Overpass API for OSM features and dumps a GeoJSON FeatureCollection
    to a temporary local file. Safe to run on a background thread."""
    if not key or not value:
        return {"error": "'key' and 'value' parameters are required (e.g. key='amenity', value='hospital')."}

    if bbox is not None and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        s, w, n, e = [float(x) for x in bbox]
    elif center_lat is not None and center_lon is not None:
        r = float(radius_km) if (radius_km is not None and radius_km > 0) else 10.0
        lat_delta = r / 111.0
        cos_lat = math.cos(math.radians(float(center_lat)))
        lon_delta = r / (111.0 * max(0.01, abs(cos_lat)))
        s = float(center_lat) - lat_delta
        n = float(center_lat) + lat_delta
        w = float(center_lon) - lon_delta
        e = float(center_lon) + lon_delta
    else:
        return {"error": "Either 'bbox' ([south, west, north, east]) or ('center_lat', 'center_lon') must be provided."}

    if s >= n or w >= e:
        return {"error": f"Invalid bounding box: south ({s}) must be < north ({n}) and west ({w}) < east ({e})."}

    clean_key = re.sub(r'[^a-zA-Z0-9_:-]', '', key)
    clean_value = value.replace('\\', '\\\\').replace('"', '\\"')
    op = "~" if "|" in clean_value else "="

    # Only a linear key needs the ways' vertex nodes (`>; out skel`) to build lines. A point
    # layer uses each way's centre, so asking for every outline corner just made the response
    # ~4x larger (live: 100 elements vs 24 for the same hospitals) on an already overloaded server.
    recurse = '>;out skel qt;' if clean_key in _OSM_LINEAR_KEYS else ''
    overpass_ql = (
        f'[out:json][timeout:30];'
        f'('
        f'node["{clean_key}"{op}"{clean_value}"]({s},{w},{n},{e});'
        f'way["{clean_key}"{op}"{clean_value}"]({s},{w},{n},{e});'
        f');'
        f'out center body;'
        f'{recurse}'
    )
    url = "https://overpass-api.de/api/interpreter"

    # Retried here, not left to the model. Live-reported 2026-09-24: 4 back-to-back
    # ingest_osm_features calls all got 504, then the model fell back to one-by-one geocoding and
    # hit the 20-call limit. Measured the same evening: 5 of 12 requests spaced 3 s apart
    # succeeded (six 504s, one 429), and failures were scattered, not a solid outage. Four
    # attempts with growing waits cut the chance of failing to roughly 0.58^4 ~ 11%, and
    # retries here don't use up the model's tool-call budget. Other public Overpass servers were
    # checked as fallbacks: one took ~40 s, one timed out, one failed TLS verification, so none
    # was added. The query is read-only, so resending the POST is safe.
    try:
        req = urllib.request.Request(
            url,
            data=overpass_ql.encode('utf-8'),
            headers={'User-Agent': 'QGIS-AI-Assistant'}
        )
        with urlopen_with_retry(req, timeout=35, max_retries=_OVERPASS_RETRIES,
                                backoff_seconds=_OVERPASS_BACKOFF_SECONDS) as response:
            res_json = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        # HTTPError is a URLError subclass, so check the status first: a 400 (bad query) must
        # not be reported as "overloaded, try later".
        if isinstance(e, urllib.error.HTTPError):
            transient = e.code in (429, 502, 503, 504)
        else:
            transient = isinstance(e, (TimeoutError, urllib.error.URLError))
        if transient:
            return {"error": (
                f"The OpenStreetMap Overpass server is overloaded right now ({e}); tried "
                f"{_OVERPASS_RETRIES + 1} times with waits in between. Don't call ingest_osm_features "
                "again in this turn, and don't try to rebuild the data another way (e.g. geocoding "
                "places one by one). Tell the user the OSM download is temporarily unavailable and "
                "suggest trying again in a few minutes, or loading their own layer instead."
            ), "retryable_later": True}
        return {"error": f"Overpass API request failed: {e}"}

    elements = res_json.get("elements", [])

    # The query's trailing `>; out skel qt;` returns every node that makes up each matched way,
    # with coordinates but no tags. These used to go through the loop below like any other
    # element: every building-outline corner became a fake "hospital" point, and a road network
    # became one point per road vertex with no lines at all. Live-reported 2026-09-24 ("Health
    # facilities beyond one hour's travel", Amman): the Road Network layer drew as a blob of points,
    # calculate_service_area produced nothing usable on it, and the model spent the rest of its
    # tool-call budget on hand-written PyQGIS workarounds. Checked against real Overpass data at
    # that location: amenity=hospital|clinic returned 24 real facilities (15 nodes + 9 ways) plus
    # 88 untagged outline nodes, so the layer had 112 "hospitals"; highway=primary|secondary in
    # a 2 km box returned 81 ways plus 802 untagged vertices, which made 883 points and no lines.
    # The untagged nodes are now used only as coordinates for building way geometry.
    node_coords = {
        e.get("id"): (e.get("lon"), e.get("lat")) for e in elements
        if e.get("type") == "node" and e.get("lat") is not None and e.get("lon") is not None
    }

    # Keys whose ways are networks, not places: a road/rail/river must be a line to be routable
    # (native:serviceareafrompoint and friends need a line layer). Everything else, e.g. an
    # amenity mapped as a building outline, keeps the way's centre point so facility layers stay
    # one point per facility.
    line_features = []
    if clean_key in _OSM_LINEAR_KEYS:
        for elem in elements:
            if elem.get("type") != "way" or not elem.get("tags"):
                continue
            coords = [node_coords[n] for n in elem.get("nodes") or [] if n in node_coords]
            if len(coords) < 2:
                continue
            line_features.append(_osm_feature(
                elem, clean_key, clean_value,
                {"type": "LineString", "coordinates": [[float(x), float(y)] for x, y in coords]},
            ))

    features = []
    for elem in ([] if line_features else elements):
        if not elem.get("tags"):
            continue  # a way's vertex from `out skel` -- geometry only, not a matching feature
        # `or` here silently drops any feature sitting exactly on the equator/prime
        # meridian: 0.0 is falsy in Python, so `elem.get("lat") or ...` (a real bug found
        # in a code-review pass, 2026-09-20) would fall through to the center lookup for a
        # plain node with lat=0.0, find no "center" key there, and get None -- discarding a
        # genuinely valid feature at the very next `is None` check below. Explicit `is not
        # None` checks instead, so a real 0.0 stays 0.0.
        elem_lat, elem_lon = elem.get("lat"), elem.get("lon")
        center = elem.get("center") or {}
        lat = elem_lat if elem_lat is not None else center.get("lat")
        lon = elem_lon if elem_lon is not None else center.get("lon")
        if lat is None or lon is None:
            continue

        features.append(_osm_feature(
            elem, clean_key, clean_value,
            {"type": "Point", "coordinates": [float(lon), float(lat)]},
        ))

    geometry_type = "LineString" if line_features else "Point"
    features = line_features or features

    if not features:
        return {
            "error": f"No OSM features found matching {clean_key}{op}'{clean_value}' in the requested region [{s:.4f}, {w:.4f}, {n:.4f}, {e:.4f}]."
        }

    if not layer_name:
        clean_tag = re.sub(r'[^a-zA-Z0-9_]', '_', clean_value)
        layer_name = f"OSM_{clean_key}_{clean_tag}"

    import tempfile
    import os
    fd, tmp_path = tempfile.mkstemp(suffix=".geojson")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    return {
        "success": True,
        "key": clean_key,
        "value": clean_value,
        "feature_count": len(features),
        "geometry_type": geometry_type,
        "bbox": [s, w, n, e],
        "local_path": tmp_path,
        "layer_name": layer_name,
        "sample_names": [f["properties"]["name"] for f in features[:5]],
    }


def add_osm_layer_main_thread_phase(fetch_result: dict) -> dict:
    """Main-thread phase: creates the QgsVectorLayer from the temporary GeoJSON file
    and adds it to QgsProject. Local disk I/O only."""
    if "error" in fetch_result:
        return fetch_result

    local_path = fetch_result.get("local_path")
    layer_name = fetch_result.get("layer_name", "OSM_Features")
    result = {k: v for k, v in fetch_result.items() if k != "local_path"}

    if not local_path or not QGIS_AVAILABLE:
        return result

    layer = QgsVectorLayer(local_path, layer_name, "ogr")
    if layer.isValid():
        QgsProject.instance().addMapLayer(layer)
        result["layer_id"] = layer.id()
        result["layer_name"] = layer_name
        result["success"] = True
    else:
        result["error"] = f"Failed to instantiate QGIS vector layer from '{local_path}'"
        result["success"] = False

    return result


@register_tool(
    "ingest_osm_features",
    "Download OpenStreetMap vector features via Overpass API (e.g. key='amenity', value='hospital', "
    "or value='hospital|clinic|doctors', or key='highway', value='primary|secondary') for a bounding "
    "box or around a center coordinate and directly add them as a new vector layer to the active QGIS project. "
    "Use this whenever you need to ingest facilities, infrastructure, or road networks into an empty or new project.",
    {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "OSM tag key, e.g. 'amenity', 'highway', 'building'"},
            "value": {"type": "string", "description": "OSM tag value or regex pipe-separated values, e.g. 'hospital', 'hospital|clinic|doctors'"},
            "bbox": {"type": "array", "items": {"type": "number"}, "description": "Optional bounding box [south, west, north, east]"},
            "center_lat": {"type": "number", "description": "Optional center latitude for radius search"},
            "center_lon": {"type": "number", "description": "Optional center longitude for radius search"},
            "radius_km": {"type": "number", "description": "Optional search radius in km around center (default: 10 km)"},
            "layer_name": {"type": "string", "description": "Optional name for the created QGIS vector layer"}
        },
        "required": ["key", "value"]
    }
)
def ingest_osm_features(
    key: str,
    value: str,
    bbox: list = None,
    center_lat: float = None,
    center_lon: float = None,
    radius_km: float = None,
    layer_name: str = None,
) -> dict:
    """Direct standalone entrypoint: runs network fetch and main-thread layer creation."""
    fetch_result = ingest_osm_features_network_phase(
        key=key,
        value=value,
        bbox=bbox,
        center_lat=center_lat,
        center_lon=center_lon,
        radius_km=radius_km,
        layer_name=layer_name,
    )
    if "error" in fetch_result:
        return fetch_result

    local_path = fetch_result.get("local_path")
    try:
        return add_osm_layer_main_thread_phase(fetch_result)
    finally:
        if local_path:
            import os
            try:
                os.remove(local_path)
            except OSError:
                pass


# ---- asking before a large download (F22) -----------------------------------------------------------------
#
# rc7 smoke test F22: downloads started with no size shown. The OSM-extract offer, the WorldPop tool and now these
# fetch tools share one rule: when the server reports a size above the user's threshold (Settings, default 50 MB)
# the tool stops and tells the model to ask the user, and only proceeds when called again with
# allow_large_download=true. A server that does not report a size (no Content-Length) is not blocked: an unknown
# size cannot be compared with a threshold, and these datasets are normally small.

def _content_length(url, timeout=15):
    """Bytes from a HEAD request's Content-Length, or None when the server gives none or HEAD fails. Uses the
    SSRF-guarded opener, so a redirect to a private address is refused here too."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "QGIS-AI-Assistant"})
        with _build_safe_opener().open(req, timeout=timeout) as response:
            raw = response.headers.get("Content-Length")
        return int(raw) if raw not in (None, "") else None
    except Exception:
        return None


def large_download_error(label, total_bytes, threshold_bytes, allow_large_download):
    """None to go ahead, or an error dict that tells the model to ask the user first. Pure."""
    if allow_large_download or not total_bytes or total_bytes <= threshold_bytes:
        return None
    mb = total_bytes / 1e6
    return {
        "error": (f"{label} is about {mb:,.0f} MB, above the {threshold_bytes / 1e6:,.0f} MB size the user asked to be "
                  "consulted about. Tell the user the size and ask whether to download it; if they agree, call this "
                  "tool again with allow_large_download=true."),
        "requires_user_decision": True, "size_mb": round(mb, 1),
    }


def _ask_threshold_bytes():
    try:
        from ..local_data_loader import ask_threshold_bytes
        return ask_threshold_bytes()
    except Exception:
        return 50 * 1000 * 1000


def check_download_size(label, urls, allow_large_download=False):
    """large_download_error() for the combined Content-Length of `urls`; None when small, unknown or opted in."""
    if allow_large_download:
        return None
    total = 0
    for u in urls:
        size = _content_length(u)
        if size:
            total += size
    return large_download_error(label, total, _ask_threshold_bytes(), False)


def fetch_geoboundaries_network_phase(iso3: str, admin_level: str = "ADM1", allow_large_download: bool = False) -> dict:
    """Pure network phase: queries the geoBoundaries API and downloads the actual
    geojson boundary file to a local temp file. No qgis.core access -- safe to
    run on a background thread. Used by agent_orchestrator.py's two-phase dispatch to keep
    both HTTP requests off the QGIS main GUI thread; fetch_geoboundaries() below
    also calls this directly so it still works standalone."""
    iso3 = iso3.upper().strip()
    admin_level = admin_level.upper().strip()

    cache_key = ("geoboundaries", iso3, admin_level)
    cached = _LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        # The cached local_path still points at a real, never-deleted temp
        # file from the first download (see the finally-less write below), so
        # it's safe to hand out again -- avoids re-downloading the same
        # boundary file if the model queries it more than once in a session.
        return {**cached, "cached": True}

    url = f"https://www.geoboundaries.org/api/current/gbOpen/{iso3}/{admin_level}/"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'QGIS-AI-Assistant'})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
        # Same live-crash class fixed elsewhere in this file/hazard_monitoring_tools.py
        # (2026-09-13): json.loads succeeding doesn't guarantee a dict.
        if not isinstance(data, dict):
            return {"error": f"geoBoundaries API returned an unexpected response shape ({type(data).__name__}, expected an object)."}
        geojson_url = data.get("gjDownloadURL")
        boundary_name = data.get("boundaryName")

        if not geojson_url:
            result = {"success": True, "boundary": boundary_name, "download_url": None, "iso3": iso3, "admin_level": admin_level}
            _LOOKUP_CACHE.set(cache_key, result)
            return result

        # SEC-001: geojson_url is third-party content (geoBoundaries' own API response),
        # not a hardcoded endpoint -- validate before fetching it, same as any other
        # externally-sourced URL.
        unsafe_reason = _is_safe_url(geojson_url)
        if unsafe_reason:
            return {"error": f"Refusing to fetch geoBoundaries download URL: {unsafe_reason}"}
        too_big = check_download_size(f"The {iso3} {admin_level} boundary file", [geojson_url], allow_large_download)
        if too_big:
            return too_big
        req2 = urllib.request.Request(geojson_url, headers={'User-Agent': 'QGIS-AI-Assistant'})
        with _build_safe_opener().open(req2, timeout=60) as response2:
            geojson_bytes = response2.read()

        import os
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix=".geojson")
        with os.fdopen(fd, "wb") as f:
            f.write(geojson_bytes)

        result = {
            "success": True, "boundary": boundary_name, "download_url": geojson_url,
            "local_path": tmp_path, "iso3": iso3, "admin_level": admin_level,
        }
        _LOOKUP_CACHE.set(cache_key, result)
        return result
    except Exception as e:
        return {"error": f"geoBoundaries API request failed: {e}"}


def add_geoboundaries_layer_main_thread_phase(fetch_result: dict) -> dict:
    """Main-thread phase: builds the QgsVectorLayer from the already-downloaded
    local file and adds it to the project. Local disk I/O only -- fast, so it's
    fine to run through the normal main-thread-blocking tool dispatch."""
    if "error" in fetch_result:
        return fetch_result

    local_path = fetch_result.get("local_path")
    if not local_path or not QGIS_AVAILABLE:
        return {"success": True, "boundary": fetch_result.get("boundary"), "download_url": fetch_result.get("download_url")}

    layer_name = f"{fetch_result['iso3']}_{fetch_result['admin_level']}_boundary"
    layer = QgsVectorLayer(local_path, layer_name, "ogr")
    if layer.isValid():
        QgsProject.instance().addMapLayer(layer)
        return {"success": True, "layer_name": layer_name, "boundary": fetch_result.get("boundary"), "download_url": fetch_result.get("download_url")}

    return {"success": True, "boundary": fetch_result.get("boundary"), "download_url": fetch_result.get("download_url")}


def fetch_hdx_admin_boundaries_network_phase(iso3: str, admin_level: str = "ADM1", allow_large_download: bool = False) -> dict:
    """Pure network phase: looks up OCHA's Common Operational Dataset - Admin
    Boundaries (COD-AB) for a country on HDX, downloads its boundaries zip,
    and extracts just the requested admin-level GeoJSON to a local temp file.
    No qgis.core access -- safe to run on a background thread, mirroring
    fetch_geoboundaries_network_phase above.

    Unlike geoBoundaries (confirmed elsewhere in this codebase to publish no
    P-codes at all), COD-AB carries real P-codes as adm{N}_pcode attributes
    (e.g. 'YE12', 'YE1704' for Yemen) -- verified live against several
    countries' actual downloaded data, not assumed from HDX's dataset
    description. That's the reason to prefer this source over
    fetch_geoboundaries specifically when a reliable join key is needed
    (calculate_severity_index's unit_name_field, calculate_presence_gap's
    presence_admin_field) -- name-string matching across differently-sourced
    datasets is fragile in exactly the way P-codes are meant to prevent.

    HDX dataset naming for COD-AB is consistently 'cod-ab-{iso3-lowercase}',
    confirmed across multiple countries (Syria, Yemen, DR Congo, Somalia) --
    but coverage isn't universal, so a 404 here is a real "no COD-AB dataset
    for this country" outcome, not necessarily a bug."""
    iso3 = iso3.upper().strip()
    admin_level = admin_level.upper().strip()

    level_match = re.search(r"(\d+)", admin_level)
    if not level_match:
        return {"error": f"admin_level must contain a digit (e.g. 'ADM1', '1'), got '{admin_level}'."}
    level_num = level_match.group(1)

    cache_key = ("hdx_admin_boundaries", iso3, level_num)
    cached = _LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        # local_path still points at a real, never-deleted temp file from the
        # first download -- same reuse pattern as fetch_geoboundaries_network_phase.
        return {**cached, "cached": True}

    dataset_name = f"cod-ab-{iso3.lower()}"
    show_url = f"https://data.humdata.org/api/3/action/package_show?id={dataset_name}"

    try:
        req = urllib.request.Request(show_url, headers={'User-Agent': 'QGIS-AI-Assistant'})
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "error": (
                    f"No OCHA COD-AB (subnational administrative boundaries) dataset found on HDX "
                    f"for '{iso3}' -- COD-AB coverage isn't universal. Try fetch_geoboundaries instead "
                    "(broader country coverage, but no P-codes)."
                )
            }
        return {"error": f"HDX request failed: {e}"}
    except Exception as e:
        return {"error": f"HDX request failed: {e}"}
    # Same real live crash class as hazard_monitoring_tools.py's fetch_nasa_eonet_events/
    # fetch_gdacs_disaster_alerts (2026-09-13): the try/except above only guarantees valid
    # JSON, not a dict -- a CKAN error page or gateway response served with a JSON
    # content-type would otherwise reach data.get(...) below and crash uncaught.
    if not isinstance(data, dict):
        return {"error": f"HDX returned an unexpected response shape ({type(data).__name__}, expected an object)."}

    result_data = data.get("result", {})
    resources = result_data.get("resources", [])
    zip_resource = next(
        (
            r for r in resources
            if r.get("format", "").lower() == "geojson" and (r.get("url") or "").lower().endswith(".zip")
        ),
        None,
    )
    if zip_resource is None:
        return {"error": f"'{dataset_name}' on HDX has no GeoJSON boundaries resource -- it may be published in shapefile-only format."}

    zip_url = zip_resource["url"]
    # SEC-001: zip_url is a resource URL from HDX's own catalog data, published by whichever
    # organization uploaded the dataset -- third-party content, validate before fetching.
    unsafe_reason = _is_safe_url(zip_url)
    if unsafe_reason:
        return {"error": f"Refusing to fetch HDX resource URL: {unsafe_reason}"}
    too_big = check_download_size(f"The {iso3} {admin_level} HDX boundary file", [zip_url], allow_large_download)
    if too_big:
        return too_big
    try:
        req2 = urllib.request.Request(zip_url, headers={'User-Agent': 'QGIS-AI-Assistant'})
        with _build_safe_opener().open(req2, timeout=60) as response2:
            zip_bytes = response2.read()
    except Exception as e:
        return {"error": f"Failed to download '{zip_url}': {e}"}

    import io
    import zipfile
    try:
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return {"error": f"'{zip_url}' did not download as a valid zip file."}

    member_name = f"{iso3.lower()}_admin{level_num}.geojson"
    if member_name not in z.namelist():
        available = [n for n in z.namelist() if n.lower().endswith(".geojson") and "admin" in n.lower()]
        return {"error": f"'{member_name}' not found in the COD-AB boundaries zip for {iso3}. Available admin-level files: {available}"}

    geojson_bytes = z.read(member_name)

    pcode_field = None
    try:
        geojson_obj = json.loads(geojson_bytes)
        features = geojson_obj.get("features", [])
        if features:
            props = features[0].get("properties", {})
            pcode_field = next((k for k in props if k.lower() == f"adm{level_num}_pcode"), None)
    except Exception as e:
        log_event("swallowed_exception", tag="Tools", tool="hdx_pcode_field_detection",
                  error_class=type(e).__name__, error=True)

    import os
    import tempfile
    fd, tmp_path = tempfile.mkstemp(suffix=".geojson")
    with os.fdopen(fd, "wb") as f:
        f.write(geojson_bytes)

    result = {
        "success": True, "iso3": iso3, "admin_level": f"ADM{level_num}",
        "dataset_title": result_data.get("title"), "source_url": zip_url,
        "local_path": tmp_path, "pcode_field": pcode_field,
    }
    _LOOKUP_CACHE.set(cache_key, result)
    return result


def add_hdx_admin_boundaries_layer_main_thread_phase(fetch_result: dict) -> dict:
    """Main-thread phase: builds the QgsVectorLayer from the already-extracted
    local GeoJSON file and adds it to the project. Local disk I/O only -- fast,
    so it's fine to run through the normal main-thread-blocking tool dispatch."""
    if "error" in fetch_result:
        return fetch_result

    local_path = fetch_result.get("local_path")
    if not local_path or not QGIS_AVAILABLE:
        return {k: v for k, v in fetch_result.items() if k != "local_path"}

    layer_name = f"{fetch_result['iso3']}_{fetch_result['admin_level']}_boundary_hdx"
    layer = QgsVectorLayer(local_path, layer_name, "ogr")
    if layer.isValid():
        QgsProject.instance().addMapLayer(layer)
        return {
            "success": True,
            "layer_name": layer_name,
            "dataset_title": fetch_result.get("dataset_title"),
            "source_url": fetch_result.get("source_url"),
            "pcode_field": fetch_result.get("pcode_field"),
        }

    return {k: v for k, v in fetch_result.items() if k != "local_path"}


@register_tool(
    "fetch_hdx_admin_boundaries",
    "Download OCHA's Common Operational Dataset - Administrative Boundaries (COD-AB) for a country "
    "from HDX -- the authoritative humanitarian source for admin boundaries, carrying real P-codes "
    "(the OCHA/HDX standard admin-unit code, e.g. 'YE12') as an attribute, unlike fetch_geoboundaries "
    "which doesn't publish P-codes at all. Reports which attribute field holds the P-code "
    "(pcode_field in the result) so it can be passed straight to unit_name_field/presence_admin_field "
    "for a reliable join in calculate_severity_index/calculate_presence_gap instead of fragile "
    "name-string matching. COD-AB coverage isn't universal -- if no dataset exists for a country, "
    "fall back to fetch_geoboundaries (broader coverage, but no P-codes).",
    {
        "type": "object",
        "properties": {
            "iso3": {"type": "string", "description": "3-letter ISO country code, e.g. 'YEM'."},
            "admin_level": {"type": "string", "description": "Admin level, e.g. 'ADM1', 'ADM2'. Defaults to 'ADM1'."},
            "allow_large_download": {"type": "boolean", "description": "Set true ONLY after the user agreed to a download above their size threshold."},
        },
        "required": ["iso3"],
    },
)
def fetch_hdx_admin_boundaries(iso3: str, admin_level: str = "ADM1", allow_large_download: bool = False):
    """Combines both phases inline for standalone/direct callers; agent_orchestrator.py's
    two-phase dispatch calls the two phase functions above separately instead,
    to keep the network fetch off the QGIS main GUI thread (same pattern as
    fetch_geoboundaries)."""
    fetch_result = fetch_hdx_admin_boundaries_network_phase(iso3, admin_level, allow_large_download)
    final = add_hdx_admin_boundaries_layer_main_thread_phase(fetch_result)
    local_path = fetch_result.get("local_path")
    if local_path:
        import os
        try:
            os.remove(local_path)
        except OSError:
            pass
    return final


_BUILDING_FOOTPRINTS_LINKS_URL = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
_BUILDING_FOOTPRINTS_ZOOM = 9


def _lonlat_to_tile_xy(lon, lat, zoom):
    """Converts lon/lat to Bing Maps tile X/Y at the given zoom level --
    standard Bing Maps Tile System math (Web Mercator projection + pixel/tile
    quantization). Hand-rolled to avoid a new runtime dependency for what is,
    underneath, deterministic arithmetic -- but verified beforehand against
    the real `mercantile` library (the one Microsoft's own example notebook
    for this exact dataset uses) across five test points, including the
    equator, near-antimeridian, and near-max-latitude edge cases, all of
    which matched exactly."""
    lat = max(min(lat, 85.05112878), -85.05112878)
    x = (lon + 180.0) / 360.0
    sin_lat = math.sin(math.radians(lat))
    y = 0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)
    map_size = 256 << zoom
    pixel_x = int(min(max(x * map_size, 0), map_size - 1))
    pixel_y = int(min(max(y * map_size, 0), map_size - 1))
    return pixel_x // 256, pixel_y // 256


def _tile_xy_to_quadkey(tile_x, tile_y, zoom):
    """Encodes a Bing Maps tile X/Y at the given zoom into its quadkey
    string -- the partition key Microsoft's Global ML Building Footprints
    dataset is indexed by."""
    digits = []
    for i in range(zoom, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if tile_x & mask:
            digit += 1
        if tile_y & mask:
            digit += 2
        digits.append(str(digit))
    return "".join(digits)


def _quadkeys_for_bbox(south, west, north, east, zoom=_BUILDING_FOOTPRINTS_ZOOM):
    """Returns the set of quadkeys covering a bbox at the dataset's zoom
    level -- tile Y increases southward, so the north edge gives the minimum
    tile Y and the south edge gives the maximum."""
    x_min, y_min = _lonlat_to_tile_xy(west, north, zoom)
    x_max, y_max = _lonlat_to_tile_xy(east, south, zoom)
    return {
        _tile_xy_to_quadkey(tx, ty, zoom)
        for tx in range(x_min, x_max + 1)
        for ty in range(y_min, y_max + 1)
    }


def _match_building_footprints_location(country_name, known_locations):
    """Matches free-text country_name against Microsoft's dataset Location
    values (e.g. 'RepublicofYemen', 'Afghanistan') -- these are neither ISO3
    codes nor exact country names, so this normalizes both sides (letters
    only, lowercased) and checks substring containment either direction.
    Returns (location, []) on exactly one match, or (None, candidates) if
    the match is ambiguous or absent -- never guesses among ties."""
    def norm(s):
        return "".join(ch for ch in s.lower() if ch.isalpha())

    key = norm(country_name)
    if not key:
        return None, []
    matches = sorted(loc for loc in known_locations if key in norm(loc) or norm(loc) in key)
    if len(matches) == 1:
        return matches[0], []
    return None, matches


def _feature_centroid(geometry):
    """Approximate centroid (mean of all vertex coordinates) of a GeoJSON
    geometry -- used only to test whether a building footprint falls inside
    the requested bbox, not a true area-weighted centroid, but sufficient
    for a fast inside/outside check on the small polygons a single building
    footprint is."""
    if not geometry:
        return None
    coords = list(_iter_coords(geometry.get("coordinates")))
    if not coords:
        return None
    return sum(c[0] for c in coords) / len(coords), sum(c[1] for c in coords) / len(coords)


def _iter_coords(coords):
    if not coords:
        return
    if isinstance(coords[0], (int, float)):
        yield coords[0], coords[1]
        return
    for c in coords:
        yield from _iter_coords(c)


def fetch_building_footprints_network_phase(country_name, bbox, max_features=5000, allow_large_download=False):
    """Pure network phase: downloads Microsoft's Global ML Building
    Footprints tiles intersecting bbox for the matched country, crops to the
    exact bbox, and writes the combined features to a local temp GeoJSON
    file. No qgis.core access -- safe to run on a background thread,
    mirroring fetch_geoboundaries_network_phase/
    fetch_hdx_admin_boundaries_network_phase above.

    This is Microsoft's own periodic dataset refresh (baseline/global
    building footprints), not live extraction from a specific image -- good
    for in-limit digitization where no local footprint data exists, not for
    damage assessment against a specific fresh image (see
    calculate_raster_change_detection for that instead). Deliberately does
    NOT ask a vision LLM to extract building polygons directly: general-
    purpose vision models are unreliable at precise coordinate-level
    geometric extraction, a real risk for humanitarian digitization/damage
    work where geometric accuracy has real consequences -- this fetches
    already-vetted pre-computed footprints instead."""
    if len(bbox) != 4:
        return {"error": "bbox must be [south, west, north, east]."}
    south, west, north, east = bbox
    if not (-90 <= south <= 90 and -90 <= north <= 90 and -180 <= west <= 180 and -180 <= east <= 180):
        return {"error": "bbox values out of range -- expected [south, west, north, east] in WGS84 degrees."}
    if south >= north or west >= east:
        return {"error": "bbox must have south < north and west < east."}

    cache_key = ("building_footprints_links",)
    cached = _LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        links_text = cached["links_text"]
    else:
        try:
            req = urllib.request.Request(_BUILDING_FOOTPRINTS_LINKS_URL, headers={'User-Agent': 'QGIS-AI-Assistant'})
            with urllib.request.urlopen(req, timeout=30) as response:
                links_text = response.read().decode()
        except Exception as e:
            return {"error": f"Failed to fetch building footprints dataset index: {e}"}
        _LOOKUP_CACHE.set(cache_key, {"links_text": links_text})

    import csv
    import io as _io
    rows = list(csv.DictReader(_io.StringIO(links_text)))
    known_locations = sorted(set(r["Location"] for r in rows))

    location, candidates = _match_building_footprints_location(country_name, known_locations)
    if location is None:
        if candidates:
            return {
                "status": "LOCATION_SUGGESTION",
                "message": (
                    f"'{country_name}' matches multiple entries in Microsoft's Global ML Building "
                    "Footprints dataset -- call again with one of these exact names."
                ),
                "candidates": candidates,
            }
        return {
            "error": (
                f"'{country_name}' doesn't match any country/region in Microsoft's Global ML "
                "Building Footprints dataset (225 covered)."
            )
        }

    quadkeys = _quadkeys_for_bbox(south, west, north, east)
    matching_rows = [r for r in rows if r["Location"] == location and r["QuadKey"] in quadkeys]
    if not matching_rows:
        return {"error": f"No building footprint tiles found for '{location}' intersecting the given bbox."}

    uncached_urls = [r["Url"] for r in matching_rows if _LOOKUP_CACHE.get(("building_footprint_tile", r["Url"])) is None
                     and not _is_safe_url(r["Url"])]
    too_big = check_download_size(f"The {location} building-footprint tiles for this area", uncached_urls, allow_large_download)
    if too_big:
        return too_big

    import gzip
    features = []
    truncated = False
    for row in matching_rows:
        # PERF-004, 2026-09-13 audit: the tile-index CSV above was already cached via
        # _LOOKUP_CACHE, but the actual per-quadkey tile download (multi-MB, gzipped)
        # was not -- a repeated call for the same/overlapping bbox within the TTL window
        # re-downloaded and re-decompressed the same tiles every time. Cached here by
        # tile URL, same TTLCache instance and TTL as the tile-index lookup above.
        tile_cache_key = ("building_footprint_tile", row["Url"])
        tile_text = _LOOKUP_CACHE.get(tile_cache_key)
        if tile_text is None:
            # SEC-001: row["Url"] comes from Microsoft's own published tile index (fetched
            # and parsed earlier in this function), not a hardcoded endpoint -- validate
            # before fetching, same as any other externally-sourced URL.
            unsafe_reason = _is_safe_url(row["Url"])
            if unsafe_reason:
                return {"error": f"Refusing to fetch tile '{row['QuadKey']}': {unsafe_reason}"}
            try:
                req = urllib.request.Request(row["Url"], headers={'User-Agent': 'QGIS-AI-Assistant'})
                with _build_safe_opener().open(req, timeout=60) as response:
                    gz_bytes = response.read()
            except Exception as e:
                return {"error": f"Failed to download tile '{row['QuadKey']}': {e}"}

            try:
                tile_text = gzip.decompress(gz_bytes).decode("utf-8")
            except OSError as e:
                return {"error": f"Tile '{row['QuadKey']}' did not decompress as gzip: {e}"}
            _LOOKUP_CACHE.set(tile_cache_key, tile_text)

        for line in tile_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                feat = json.loads(line)
            except (ValueError, TypeError):
                continue
            # Same class of gap as this file's fetch_hdx_admin_boundaries fix above --
            # json.loads succeeding doesn't guarantee a dict; a malformed line parsing to
            # a bare number/string/bool would otherwise crash feat.get(...) uncaught.
            if not isinstance(feat, dict):
                continue
            centroid = _feature_centroid(feat.get("geometry"))
            if centroid is None:
                continue
            lon, lat = centroid
            if not (west <= lon <= east and south <= lat <= north):
                continue
            features.append(feat)
            if len(features) >= max_features:
                truncated = True
                break
        if truncated:
            break

    if not features:
        return {
            "error": (
                f"No building footprints found within the given bbox for '{location}' -- tiles were "
                "fetched, but no features fell inside the exact bbox (only within the wider tile)."
            )
        }

    import os
    import tempfile
    fd, tmp_path = tempfile.mkstemp(suffix=".geojson")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)

    return {
        "success": True,
        "location": location,
        "feature_count": len(features),
        "tiles_used": len(matching_rows),
        "truncated": truncated,
        "max_features": max_features,
        "local_path": tmp_path,
        "source": "Microsoft Global ML Building Footprints (CDLA Permissive 2.0 license)",
        # Moved here from the tool description (paid on every call where
        # ToolRouter merely selects this as a candidate, invoked or not) --
        # this is presentation guidance only needed when the tool actually
        # runs. See also BASE_SYSTEM_PROMPT rule 28, which already instructs
        # relaying this when presenting the result; this field keeps the
        # same wording machine-locatable in the tool's own output rather
        # than relying on that rule alone.
        "baseline_caveat": (
            "This is Microsoft's own periodic dataset refresh, not live extraction from a specific "
            "image -- it can lag real/current conditions by months. Never present it as evidence of "
            "current or post-event structure status."
        ),
    }


def add_building_footprints_layer_main_thread_phase(fetch_result):
    """Main-thread phase: builds the QgsVectorLayer from the already-fetched
    local GeoJSON file and adds it to the project. Local disk I/O only."""
    if "error" in fetch_result or fetch_result.get("status") == "LOCATION_SUGGESTION":
        return fetch_result

    local_path = fetch_result.get("local_path")
    if not local_path or not QGIS_AVAILABLE:
        return {k: v for k, v in fetch_result.items() if k != "local_path"}

    layer_name = f"{fetch_result['location']}_building_footprints"
    layer = QgsVectorLayer(local_path, layer_name, "ogr")
    result = {k: v for k, v in fetch_result.items() if k != "local_path"}
    if layer.isValid():
        QgsProject.instance().addMapLayer(layer)
        result["layer_name"] = layer_name
        result["success"] = True
    return result


@register_tool(
    "fetch_building_footprints",
    "Download building footprint polygons for an area of interest from Microsoft's Global ML "
    "Building Footprints dataset (1B+ buildings, 225 countries/regions, CDLA Permissive 2.0 "
    "license) -- for baseline digitization where no local building-footprint data exists (e.g. "
    "in-limit boundary work), NOT for damage assessment against a specific fresh image (use "
    "calculate_raster_change_detection for that instead; see the result's baseline_caveat for the "
    "exact wording on how current this dataset is). country_name is free text matched against the "
    "dataset's own location list (NOT an ISO3 code -- this dataset isn't indexed that way); an "
    "ambiguous or unmatched name returns candidate matches instead of guessing.",
    {
        "type": "object",
        "properties": {
            "country_name": {"type": "string", "description": "Country name, e.g. 'Yemen'. Matched against the dataset's own location names, not an ISO3 code."},
            "bbox": {"type": "array", "items": {"type": "number"}, "description": "[south, west, north, east] in WGS84 degrees -- footprints are cropped to this area, not the whole country."},
            "max_features": {"type": "integer", "description": "Safety cap on returned features. Defaults to 5000; if exceeded, results are truncated (not silently dropped) and truncated=true is reported."},
            "allow_large_download": {"type": "boolean", "description": "Set true ONLY after the user agreed to a download above their size threshold."},
        },
        "required": ["country_name", "bbox"],
    },
)
def fetch_building_footprints(country_name, bbox, max_features=5000, allow_large_download=False):
    """Combines both phases inline for standalone/direct callers; agent_orchestrator.py's
    two-phase dispatch calls the two phase functions above separately
    instead, to keep the network fetch off the QGIS main GUI thread (same
    pattern as fetch_geoboundaries/fetch_hdx_admin_boundaries)."""
    fetch_result = fetch_building_footprints_network_phase(country_name, bbox, max_features, allow_large_download)
    final = add_building_footprints_layer_main_thread_phase(fetch_result)
    local_path = fetch_result.get("local_path")
    if local_path:
        import os
        try:
            os.remove(local_path)
        except OSError:
            pass
    return final


@register_tool("fetch_geoboundaries", "Download administrative boundaries from geoBoundaries API. A file larger than the user's download-size setting is not fetched until the user agrees: then call again with allow_large_download=true.", {"type": "object", "properties": {"iso3": {"type": "string"}, "admin_level": {"type": "string"}, "allow_large_download": {"type": "boolean", "description": "Set true ONLY after the user agreed to a download above their size threshold."}}, "required": ["iso3", "admin_level"]})
def fetch_geoboundaries(iso3: str, admin_level: str = "ADM1", allow_large_download: bool = False):
    """Queries geoBoundaries API for ISO3 country code and ADM level. Does both
    phases inline for standalone/direct callers; agent_orchestrator.py's two-phase dispatch
    calls the two phase functions above separately instead, to keep the network
    fetch off the QGIS main GUI thread."""
    fetch_result = fetch_geoboundaries_network_phase(iso3, admin_level, allow_large_download)
    final = add_geoboundaries_layer_main_thread_phase(fetch_result)
    local_path = fetch_result.get("local_path")
    if local_path:
        import os
        try:
            os.remove(local_path)
        except OSError:
            pass
    return final


# ---- clipping the WorldPop download to the area that is needed (F19) --------------------------------
#
# rc7 smoke test F19 (2026-09-30): fetch_worldpop_population downloaded the WHOLE-COUNTRY raster
# (Yemen, 41.81-54.54 E x 12.11-19.00 N, 141 s) for a ~77 x 71 km catchment. The GeoTIFF can be
# read through GDAL's /vsicurl/ driver with HTTP range requests, so only the window that is asked for
# crosses the network. Clipping keeps pixel values untouched, so population sums over the area are the
# same as from the full raster.
BBOX_PAD_DEGREES = 0.02          # ~2 km: keeps the raster slightly larger than the area it serves
_WORLDPOP_HOST_SUFFIX = "worldpop.org"


def parse_bbox(value):
    """(min_lon, min_lat, max_lon, max_lat) from a 4-number list/tuple or a "a,b,c,d" string; raises
    ValueError with a message the model can act on. Pure."""
    if isinstance(value, str):
        value = [part for part in value.replace(";", ",").split(",") if part.strip()]
    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in value)
    except (TypeError, ValueError):
        raise ValueError("bbox must be four numbers: min_lon, min_lat, max_lon, max_lat (WGS84 degrees).")
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise ValueError(
            f"bbox ({min_lon}, {min_lat}, {max_lon}, {max_lat}) is not a valid WGS84 box -- expected "
            "min_lon < max_lon within -180..180 and min_lat < max_lat within -90..90. If these look like "
            "projected metres, pass extent_layer instead of converting them."
        )
    return (min_lon, min_lat, max_lon, max_lat)


def pad_bbox(bbox, margin=BBOX_PAD_DEGREES):
    min_lon, min_lat, max_lon, max_lat = bbox
    return (max(-180.0, min_lon - margin), max(-90.0, min_lat - margin),
            min(180.0, max_lon + margin), min(90.0, max_lat + margin))


def _worldpop_clip_source_allowed(url):
    """Only https URLs on worldpop.org are read through /vsicurl/: GDAL follows redirects itself, outside
    the SSRF-guarded opener the full download uses, so the set of hosts it may reach is kept to the one
    data provider."""
    from urllib.parse import urlparse
    parts = urlparse(url or "")
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host == _WORLDPOP_HOST_SUFFIX or host.endswith("." + _WORLDPOP_HOST_SUFFIX))


def _window_inside_raster(requested, raster_bounds):
    """(window, clamped): `requested` (min_lon, min_lat, max_lon, max_lat) intersected with the raster's own
    bounds, and whether that changed it. Raises RuntimeError when they do not overlap at all. Pure.

    Why: gdal.Translate(projWin=...) does NOT fail for a window outside the raster -- it writes an empty
    (nodata) raster. A bbox that misses the country would then look like a successful fetch and every
    population sum over it would silently be zero."""
    r_min_lon, r_min_lat, r_max_lon, r_max_lat = raster_bounds
    w = (max(requested[0], r_min_lon), max(requested[1], r_min_lat),
         min(requested[2], r_max_lon), min(requested[3], r_max_lat))
    if not (w[0] < w[2] and w[1] < w[3]):
        raise RuntimeError(
            f"the requested area {tuple(round(v, 4) for v in requested)} does not overlap the raster, which covers "
            f"lon {r_min_lon:.3f}..{r_max_lon:.3f}, lat {r_min_lat:.3f}..{r_max_lat:.3f}")
    return w, tuple(w) != tuple(requested)


def _clip_raster_to_bbox(source, bbox, dest_path):
    """Write the part of the GDAL-readable `source` (a local path or /vsicurl/ URL) inside `bbox` (WGS84,
    the WorldPop CRS) to a compressed GeoTIFF at dest_path. The window is clamped to the raster's own
    bounds; a window that does not overlap it, or a raster that is not geographic/north-up, raises
    RuntimeError with a readable message."""
    try:
        from osgeo import gdal, osr
    except ImportError as e:
        raise RuntimeError(f"GDAL Python bindings are not available ({e}).")
    gdal.UseExceptions()
    options = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        "GDAL_HTTP_TIMEOUT": "120", "GDAL_HTTP_MAX_RETRY": "2",
    }
    for key, val in options.items():
        gdal.SetThreadLocalConfigOption(key, val)
    try:
        src_ds = gdal.Open(source)
        gt = src_ds.GetGeoTransform()
        if gt[2] or gt[4] or gt[5] >= 0:
            raise RuntimeError("the raster is rotated or not north-up, which is not supported for clipping.")
        srs = osr.SpatialReference()
        srs.ImportFromWkt(src_ds.GetProjection() or "")
        if not srs.IsGeographic():
            raise RuntimeError("the raster is not in a geographic (lon/lat) CRS, so a WGS84 window cannot be applied.")
        x0, y0 = gt[0], gt[3]
        x1, y1 = x0 + gt[1] * src_ds.RasterXSize, y0 + gt[5] * src_ds.RasterYSize
        window, clamped = _window_inside_raster(bbox, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
        ds = gdal.Translate(dest_path, src_ds, projWin=[window[0], window[3], window[2], window[1]],
                            creationOptions=["COMPRESS=DEFLATE", "TILED=YES"])
        if ds is None:
            raise RuntimeError("GDAL returned no dataset for the requested window.")
        width, height = ds.RasterXSize, ds.RasterYSize
        ds = None
        src_ds = None
        return {"width": width, "height": height, "clamped": clamped, "window": list(window)}
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(str(e))
    finally:
        for key in options:
            gdal.SetThreadLocalConfigOption(key, None)


def worldpop_cache_dir(_unused=None):
    """Folder for whole-country WorldPop rasters: <project>/data/00_raw/worldpop, or a folder in the QGIS profile for an
    unsaved project. Needs QgsProject, so call it on the main thread."""
    import os
    from ..local_data_loader import data_dir
    base = data_dir()
    return os.path.join(os.path.dirname(base), "worldpop")


def _worldpop_cache_file(cache_dir, iso3, popyear):
    """Where the whole-country raster is kept once downloaded (or None when no cache folder is known). Pure."""
    if not cache_dir:
        return None
    import os
    return os.path.join(cache_dir, f"{iso3.lower()}_ppp_{popyear}.tif")


def _is_transport_failure(error):
    """True when a clip error is about reaching/reading the remote file, not about the requested area itself: an area that
    does not overlap the raster would fail the same way from a local copy, so it must not trigger a big download. Pure."""
    text = str(error).lower()
    return not any(marker in text for marker in ("does not overlap", "rotated", "geographic", "bindings"))


def _download_to_file(url, dest, chunk=1 << 20):
    """Streams `url` to `dest` through the SSRF-guarded opener, via a .part file so an interrupted download never
    leaves a truncated raster that later looks like a cache hit."""
    import os
    unsafe = _is_safe_url(url)
    if unsafe:
        raise RuntimeError(f"Refusing to fetch WorldPop file URL: {unsafe}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    req = urllib.request.Request(url, headers={'User-Agent': 'QGIS-AI-Assistant'})
    try:
        with _build_safe_opener().open(req, timeout=300) as response, open(part, "wb") as out:
            while True:
                block = response.read(chunk)
                if not block:
                    break
                out.write(block)
        os.replace(part, dest)
    except Exception as e:
        try:
            os.remove(part)
        except OSError:
            pass
        raise RuntimeError(f"downloading the country file failed: {e}")


def fetch_worldpop_population_network_phase(iso3: str, year: str = None, bbox=None, allow_whole_country=False,
                                            cache_dir=None) -> dict:
    """Pure network phase: queries WorldPop's API for available population raster
    datasets for a country, picks the requested (or most recent) year, and
    fetches the GeoTIFF -- the WHOLE country (100MB-1GB+, slow) when bbox is None, or
    only the window inside bbox (WGS84 min_lon, min_lat, max_lon, max_lat) when it is
    given. Split out to run on a background thread rather than the QGIS main GUI
    thread. No qgis.core access."""
    iso3 = (iso3 or "").upper().strip()
    if len(iso3) != 3 or not iso3.isalpha():
        return {"error": "iso3 must be a 3-letter ISO country code, e.g. 'YEM'."}
    window = None
    if bbox is not None:
        try:
            window = pad_bbox(parse_bbox(bbox))
        except ValueError as e:
            return {"error": str(e)}
    elif not allow_whole_country:
        # rc7 smoke test F22/F19: a whole-country raster is 100MB-1GB+ and took 141 s for Yemen, for an
        # analysis that needed a city-sized window. Refuse by default, like travel_time_matrix's size guard.
        return {"error": (
            "fetch_worldpop_population would download the WHOLE country's population raster (100 MB to over "
            "1 GB, minutes). Pass extent_layer (a layer covering the area of interest) or bbox to fetch only "
            "that area. Only if the whole country is genuinely needed, and the user has agreed to the "
            "download, call again with allow_whole_country=true."),
            "suggested_args": ["extent_layer", "bbox"]}

    cache_key = ("worldpop", iso3, year, window)
    cached = _LOOKUP_CACHE.get(cache_key)
    if cached is not None:
        # local_path still points at a real, never-deleted temp file -- see
        # add_worldpop_population_layer_main_thread_phase for why this one
        # (unlike geoBoundaries' geojson) is never cleaned up: a raster layer
        # reads its backing file lazily/on demand, not fully into memory, so
        # deleting it after loading would silently break the layer later.
        return {**cached, "cached": True}

    try:
        list_url = f"https://hub.worldpop.org/rest/data/pop/wpgp?iso3={iso3}"
        req = urllib.request.Request(list_url, headers={'User-Agent': 'QGIS-AI-Assistant'})
        with urllib.request.urlopen(req, timeout=30) as response:
            listing = json.loads(response.read().decode())
        datasets = listing.get("data", [])
        if not datasets:
            return {"error": f"No WorldPop population datasets found for '{iso3}' -- check the ISO3 code is correct."}

        if year:
            matches = [d for d in datasets if str(d.get("popyear")) == str(year)]
            if not matches:
                available = sorted({str(d.get("popyear")) for d in datasets})
                return {"error": f"No WorldPop dataset for {iso3} in {year}. Available years: {available}"}
            dataset = matches[0]
        else:
            dataset = max(datasets, key=lambda d: str(d.get("popyear", "")))

        file_urls = dataset.get("files") or []
        if not file_urls:
            return {"error": f"WorldPop dataset for {iso3} has no downloadable file listed."}

        # SEC-001: file_urls[0] comes from WorldPop's own API listing, not a hardcoded
        # endpoint -- validate before fetching, same as any other externally-sourced URL.
        unsafe_reason = _is_safe_url(file_urls[0])
        if unsafe_reason:
            return {"error": f"Refusing to fetch WorldPop file URL: {unsafe_reason}"}

        import os
        import tempfile

        if window is not None:
            if not _worldpop_clip_source_allowed(file_urls[0]):
                return {"error": (
                    "The WorldPop file is not on worldpop.org, so it will not be read remotely for clipping. "
                    "Call again without bbox/extent_layer to download the whole country instead.")}
            fd, tmp_path = tempfile.mkstemp(suffix=".tif")
            os.close(fd)
            cache_file = _worldpop_cache_file(cache_dir, iso3, dataset.get("popyear"))
            used_cache = None
            try:
                if cache_file and os.path.exists(cache_file):
                    # A whole-country file downloaded earlier: clip from disk, no network at all.
                    size = _clip_raster_to_bbox(cache_file, window, tmp_path)
                    used_cache = "reused"
                else:
                    try:
                        size = _clip_raster_to_bbox("/vsicurl/" + file_urls[0], window, tmp_path)
                    except RuntimeError as remote_error:
                        # F19: a remote window read can fail or be impractically slow (a strip-organised file, or a server
                        # that ignores range requests). With the user's consent to the whole-country download, fetch it ONCE,
                        # keep it, and clip locally -- every later area for this country is then instant.
                        if not (allow_whole_country and cache_file and _is_transport_failure(remote_error)):
                            raise
                        _download_to_file(file_urls[0], cache_file)
                        size = _clip_raster_to_bbox(cache_file, window, tmp_path)
                        used_cache = "downloaded"
            except RuntimeError as e:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                return {"error": (
                    f"Could not fetch just the requested area from WorldPop ({e}). Nothing was downloaded. "
                    "Check the bbox overlaps the country, or call again without bbox/extent_layer to "
                    "download the whole country (large and slow).")}
            result = {
                "success": True, "iso3": iso3, "year": dataset.get("popyear"),
                "download_url": file_urls[0], "local_path": tmp_path,
                "clipped_to_bbox": list(size.get("window") or window),
                "clipped_pixels": [size["width"], size["height"]],
                "bytes_on_disk": os.path.getsize(tmp_path),
            }
            if used_cache:
                result["country_file_cache"] = used_cache
                result["country_file"] = cache_file
            if size.get("clamped"):
                result["clip_clamped"] = ("Part of the requested area lies outside the country's raster; only the "
                                          "overlapping part was fetched.")
            _LOOKUP_CACHE.set(cache_key, result)
            return result

        req2 = urllib.request.Request(file_urls[0], headers={'User-Agent': 'QGIS-AI-Assistant'})
        with _build_safe_opener().open(req2, timeout=300) as response2:
            raster_bytes = response2.read()

        fd, tmp_path = tempfile.mkstemp(suffix=".tif")
        with os.fdopen(fd, "wb") as f:
            f.write(raster_bytes)

        result = {
            "success": True, "iso3": iso3, "year": dataset.get("popyear"),
            "download_url": file_urls[0], "local_path": tmp_path,
            "bytes_on_disk": len(raster_bytes),
            "note": "The WHOLE-country raster was downloaded. Pass extent_layer (or bbox) to fetch only the "
                    "area needed -- far smaller and faster.",
        }
        _LOOKUP_CACHE.set(cache_key, result)
        return result
    except Exception as e:
        return {"error": f"WorldPop API request failed: {e}"}


def resolve_extent_bbox(layer_name):
    """Main-thread helper: the WGS84 (min_lon, min_lat, max_lon, max_lat) extent of a project layer, or
    raises ValueError. Kept out of the network phase, which has no qgis.core access."""
    if not QGIS_AVAILABLE:
        raise ValueError("QGIS not available")
    layer = None
    for candidate in QgsProject.instance().mapLayersByName(layer_name or ""):
        layer = candidate
        break
    if layer is None:
        raise ValueError(f"Layer '{layer_name}' not found")
    extent = layer.extent()
    if extent.isNull() or extent.isEmpty():
        raise ValueError(f"Layer '{layer_name}' has no extent to clip to.")
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    if layer.crs().isValid() and layer.crs() != wgs84:
        extent = QgsCoordinateTransform(layer.crs(), wgs84, QgsProject.instance()).transformBoundingBox(extent)
    return (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())


def add_worldpop_population_layer_main_thread_phase(fetch_result: dict) -> dict:
    """Main-thread phase: loads the already-downloaded GeoTIFF as a raster
    layer. Deliberately does NOT delete the local temp file afterward (unlike
    add_geoboundaries_layer_main_thread_phase) -- a QgsRasterLayer keeps
    reading its backing file on demand for as long as it's in the project, so
    removing it here would make the layer silently break the next time
    something (e.g. estimate_population_exposure) actually samples it."""
    if "error" in fetch_result:
        return fetch_result

    local_path = fetch_result.get("local_path")
    if not local_path or not QGIS_AVAILABLE:
        return {"success": True, "iso3": fetch_result.get("iso3"), "year": fetch_result.get("year")}

    clipped = bool(fetch_result.get("clipped_to_bbox"))
    layer_name = f"{fetch_result['iso3']}_population_{fetch_result.get('year')}" + ("_area" if clipped else "")
    layer = QgsRasterLayer(local_path, layer_name)
    if layer.isValid():
        QgsProject.instance().addMapLayer(layer)
        out = {"success": True, "layer_name": layer_name, "iso3": fetch_result.get("iso3"), "year": fetch_result.get("year")}
        for key in ("clipped_to_bbox", "clipped_pixels", "bytes_on_disk", "note", "clip_clamped"):
            if fetch_result.get(key) is not None:
                out[key] = fetch_result[key]
        if clipped:
            out["clip_note"] = ("Only the requested area (plus a ~2 km margin) was fetched; population sums over "
                                "areas inside it match the full-country raster. Areas outside it have no data.")
        return out

    return {"success": True, "iso3": fetch_result.get("iso3"), "year": fetch_result.get("year")}


@register_tool(
    "fetch_worldpop_population",
    "Fetch a country's gridded population raster from WorldPop (open, free population data at "
    "~100m resolution) and load it as a layer -- an open-data approximation of what ArcGIS's "
    "Business Analyst extension provides with proprietary demographic data. ALWAYS pass extent_layer "
    "(a layer covering the area of interest, e.g. the catchment or admin boundary) or bbox: without "
    "either the call is refused, because the WHOLE country would be downloaded (100MB-1GB+, minutes) -- "
    "allow_whole_country=true overrides that, only after the user agreed. With one, only that area plus a ~2 km "
    "margin is fetched and the layer is named <ISO3>_population_<year>_area. After loading, use "
    "estimate_population_exposure to sum population within a specific area.",
    {
        "type": "object",
        "properties": {
            "iso3": {"type": "string", "description": "3-letter ISO country code, e.g. 'YEM'."},
            "year": {"type": "string", "description": "Population year, e.g. '2020'. Omit to use the most recent available."},
            "extent_layer": {"type": "string", "description": "Name of a project layer whose extent is the area to fetch (preferred -- handles any CRS)."},
            "bbox": {"type": "array", "items": {"type": "number"}, "description": "Alternative to extent_layer: [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees."},
            "allow_whole_country": {"type": "boolean", "description": "Set true ONLY after the user agreed to download the whole country (100 MB to over 1 GB). Without extent_layer/bbox and without this, the tool refuses."},
        },
        "required": ["iso3"],
    },
)
def fetch_worldpop_population(iso3: str, year: str = None, extent_layer: str = None, bbox=None,
                              allow_whole_country: bool = False):
    """Does both phases inline for standalone/direct callers; agent_orchestrator.py's
    two-phase dispatch calls the two phase functions above separately instead,
    to keep the (potentially large, slow) download off the QGIS main GUI
    thread. No cleanup of the downloaded file -- see
    add_worldpop_population_layer_main_thread_phase for why."""
    if extent_layer and bbox is None:
        try:
            bbox = resolve_extent_bbox(extent_layer)
        except ValueError as e:
            return {"error": str(e)}
    fetch_result = fetch_worldpop_population_network_phase(iso3, year, bbox, allow_whole_country)
    return add_worldpop_population_layer_main_thread_phase(fetch_result)


INCIDENT_LAYER_NAME = "Incidents"

# Two optional controlled incident-coding vocabularies, alongside (not
# replacing) the existing freeform severity/category fields -- per
# docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md Section V's gap ("no controlled/
# authorized incident-coding vocabulary"). Project decision, 2026-09-04: support
# both rather than picking one. Values are validated but not enforced -- an
# unrecognized value is returned as a warning, not a hard error, so a caller
# passing a still-freeform label doesn't lose the whole insert.

# ACLED's own published 6-category event taxonomy with its per-event
# sub-event list (25 sub-events total across all 6 categories).
ACLED_EVENT_TAXONOMY = {
    "Battles": ["Government regains territory", "Non-state actor overtakes territory", "Armed clash"],
    "Protests": ["Excessive force against protesters", "Protest with intervention", "Peaceful protest"],
    "Riots": ["Violent demonstration", "Mob violence"],
    "Explosions/Remote violence": [
        "Chemical weapon", "Air/drone strike", "Suicide bomb",
        "Shelling/artillery/missile attack", "Remote explosive/landmine/IED", "Grenade",
    ],
    "Violence against civilians": ["Sexual violence", "Attack", "Abduction/forced disappearance"],
    "Strategic developments": [
        "Agreement", "Arrests", "Change to group/activity", "Disrupted weapons use",
        "Headquarters or base established", "Looting/property destruction",
        "Non-violent transfer of territory", "Other",
    ],
}

# IMSMA/IMAS-style explosive-hazard classification: hazard type per IMAS
# 04.10, contamination status per IMAS 08.10 (Confirmed/Suspected Hazardous
# Area, Cleared).
IMSMA_HAZARD_TYPES = [
    "Landmine - Anti-Personnel", "Landmine - Anti-Vehicle", "Unexploded Ordnance (UXO)",
    "Abandoned Ordnance (AXO)", "Improvised Explosive Device (IED)", "Cluster Munition Remnant",
    "Booby Trap",
]
IMSMA_CONTAMINATION_STATUSES = ["Confirmed Hazardous Area", "Suspected Hazardous Area", "Cleared"]


def _validate_incident_coding(event_type=None, sub_event_type=None, hazard_type=None, contamination_status=None):
    """Checks the four optional controlled-vocabulary values against the
    ACLED-style and IMSMA-style lists above. Returns a list of warning
    strings (empty if everything given is valid or nothing was given) --
    never raises, since these are advisory fields layered on top of the
    pre-existing freeform severity/category fields."""
    warnings = []
    if event_type is not None and event_type not in ACLED_EVENT_TAXONOMY:
        warnings.append(f"event_type '{event_type}' is not one of ACLED's 6 event types: {list(ACLED_EVENT_TAXONOMY)}")
    elif event_type is not None and sub_event_type is not None:
        if sub_event_type not in ACLED_EVENT_TAXONOMY[event_type]:
            warnings.append(f"sub_event_type '{sub_event_type}' is not a valid ACLED sub-event of '{event_type}': {ACLED_EVENT_TAXONOMY[event_type]}")
    if hazard_type is not None and hazard_type not in IMSMA_HAZARD_TYPES:
        warnings.append(f"hazard_type '{hazard_type}' is not one of the IMSMA-style hazard types: {IMSMA_HAZARD_TYPES}")
    if contamination_status is not None and contamination_status not in IMSMA_CONTAMINATION_STATUSES:
        warnings.append(f"contamination_status '{contamination_status}' is not one of {IMSMA_CONTAMINATION_STATUSES}")
    return warnings


def _validate_incident_temporal(event_start=None, event_end=None):
    """Point 7 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: add_incident_point/
    add_point_layer previously captured one freeform `date` string with no way to express a
    duration (an incident lasting days, a hazard active over a period) or record when the data
    was last confirmed. event_start/event_end/last_verified are additive fields alongside the
    existing `date`, not a replacement -- `date` stays freeform for whatever single-date sources
    already use. Only checks ordering when both are given AND both parse as ISO 8601 (YYYY-MM-DD
    or longer) -- these fields stay freeform strings like `date` already is, so an unparsable
    value (a source's own date format) is silently skipped, not rejected; this is advisory
    warning, same restraint as _validate_incident_coding above, never a hard error."""
    warnings = []
    if event_start and event_end:
        try:
            start = date.fromisoformat(str(event_start)[:10])
            end = date.fromisoformat(str(event_end)[:10])
        except ValueError:
            return warnings
        if end < start:
            warnings.append(f"event_end ({event_end}) is before event_start ({event_start})")
    return warnings


def _style_incident_layer(layer):
    """Hardcoded professional cartography: red point marker, white-background/
    red-text label. Keeping this fixed in plugin code (rather than letting the
    model write ad hoc styling via execute_pyqgis_script) is what guarantees a
    consistent, professional look regardless of what the model generates."""
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    symbol.setColor(QColor("red"))
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))

    settings = QgsPalLayerSettings()
    settings.fieldName = "description"
    settings.isExpression = False

    text_format = QgsTextFormat()
    text_format.setSize(9)
    text_format.setColor(QColor("red"))

    background = QgsTextBackgroundSettings()
    background.setEnabled(True)
    background.setType(_SHAPE_RECTANGLE)
    background.setFillColor(QColor("white"))
    text_format.setBackground(background)

    settings.setFormat(text_format)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def _clip_to_field_width(layer, fname, value):
    """Clip a string value to its field's declared width before setAttribute.

    Same fix as hazard_monitoring_tools.py's identically-named helper (duplicated here
    rather than imported, matching this codebase's existing per-file-helper convention --
    see _find_layer_by_name's ~18 independent copies across agent/tools/): this file's
    Incidents/add_point_layer schemas also use fixed shapefile-era widths
    (name/description:string(255) etc.), and setAttribute on a QGIS memory-provider layer
    silently rejects (and drops) any value wider than the field's declared length rather
    than raising -- confirmed for the sibling GDACS layer via a real "Could not store
    attribute" Qt log line, 2026-09-16. Clipping defensively here covers both write sites
    below regardless of which field a future caller happens to overflow."""
    if not isinstance(value, str):
        return value
    # Best-effort: this file's own test suite stands layers in with a bare MagicMock()
    # (no real QgsFields), so .field(fname).length() there returns another MagicMock,
    # not an int -- treat anything that isn't a real QGIS field width as unbounded
    # rather than raising or mis-clipping against a mock's identity.
    try:
        width = layer.fields().field(fname).length()
    except Exception:
        return value
    if isinstance(width, int) and width > 0 and len(value) > width:
        return value[:width]
    return value


@register_tool(
    "add_incident_point",
    "Plot a single real-world incident/event as a labeled point on the map, using consistent professional "
    "styling (red marker, white-background/red-text label). Adds to a shared 'Incidents' layer, creating it "
    "on first use. Only ever call this with real, verified data -- if the coordinates or date aren't already "
    "known, use search_web/geocode_and_enrich to find them first; never invent placeholder values. Set "
    "severity when it's known (e.g. security incident classification) so apply_categorized_style/"
    "apply_graduated_symbol_style can later distinguish incident types on the map instead of every point "
    "looking identical. For conflict/security incidents, also set event_type (+ sub_event_type) using "
    "ACLED's controlled taxonomy when the source classification maps to it; for explosive-hazard incidents, "
    "set hazard_type (+ contamination_status) using the IMSMA/IMAS-style vocabulary. Both are optional and "
    "validated -- an unrecognized value comes back as a warning, not a rejected point. If the incident spans "
    "a period rather than one instant (e.g. a hazard active over days, a multi-day event), also set "
    "event_start/event_end alongside the existing date field -- additive, not a replacement, so date stays "
    "freeform for single-date sources. last_verified records when the data was last confirmed, separate "
    "from when the incident itself occurred.",
    {
        "type": "object",
        "properties": {
            "lat": {"type": "number", "description": "Latitude in decimal degrees (WGS84)."},
            "lon": {"type": "number", "description": "Longitude in decimal degrees (WGS84)."},
            "date": {"type": "string", "description": "Real, verified date of the incident (e.g. '2026-03-14')."},
            "description": {"type": "string", "description": "Short, factual description of the incident."},
            "severity": {"type": "string", "description": "Optional severity/category label, e.g. 'High', 'Security', 'Flood'. Free text -- use whatever classification the source data uses."},
            "event_type": {"type": "string", "description": f"Optional ACLED-style controlled event type: one of {list(ACLED_EVENT_TAXONOMY)}."},
            "sub_event_type": {"type": "string", "description": "Optional ACLED-style sub-event type, valid within the chosen event_type."},
            "hazard_type": {"type": "string", "description": f"Optional IMSMA/IMAS-style explosive-hazard type: one of {IMSMA_HAZARD_TYPES}."},
            "contamination_status": {"type": "string", "description": f"Optional IMSMA/IMAS-style contamination status: one of {IMSMA_CONTAMINATION_STATUSES}."},
            "event_start": {"type": "string", "description": "Optional ISO date (YYYY-MM-DD) the incident/hazard started, when it spans a period rather than one day."},
            "event_end": {"type": "string", "description": "Optional ISO date (YYYY-MM-DD) the incident/hazard ended, when it spans a period rather than one day."},
            "last_verified": {"type": "string", "description": "Optional ISO date (YYYY-MM-DD) this data was last confirmed accurate -- distinct from when the incident occurred."},
        },
        "required": ["lat", "lon", "date", "description"],
    },
)
def add_incident_point(
    lat: float, lon: float, date: str, description: str, severity: str = None,
    event_type: str = None, sub_event_type: str = None,
    hazard_type: str = None, contamination_status: str = None,
    event_start: str = None, event_end: str = None, last_verified: str = None,
):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return {"error": "lat/lon must be numeric."}
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return {"error": f"lat/lon out of range: ({lat}, {lon})"}

    existing = QgsProject.instance().mapLayersByName(INCIDENT_LAYER_NAME)
    if existing:
        layer = existing[0]
    else:
        layer = QgsVectorLayer(
            "Point?crs=EPSG:4326&field=date:string(50)&field=description:string(255)&field=severity:string(50)"
            "&field=event_type:string(50)&field=sub_event_type:string(80)"
            "&field=hazard_type:string(50)&field=contamination_status:string(50)"
            "&field=event_start:string(30)&field=event_end:string(30)&field=last_verified:string(30)",
            INCIDENT_LAYER_NAME, "memory",
        )
        if not layer.isValid():
            return {"error": "Failed to create Incidents layer"}
        QgsProject.instance().addMapLayer(layer)
        # QGIS-009, 2026-09-14 audit: _style_incident_layer used to run unguarded here -- a
        # styling failure (e.g. an enum this QGIS version doesn't resolve, currently
        # unreachable but latent, same class as QGIS-004/005) would raise past this point,
        # meaning the layer already added above never gets its incident point added either,
        # and the tool call fails outright -- even though the layer now EXISTS in the
        # project, unstyled. Every later add_incident_point call hits the `if existing:`
        # branch above and reuses that same layer, which is never styled again (styling only
        # runs here, on first creation) -- "permanently unstyled" until the project is
        # cleaned up by hand. Styling is cosmetic, not required for the feature itself to
        # work, so a failure here must not block adding the actual incident point.
        try:
            _style_incident_layer(layer)
        except Exception as e:
            print(f"[humanitarian_tools] Failed to style new Incidents layer: {e}")

    feat = QgsFeature(layer.fields())
    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
    feat.setAttribute("date", _clip_to_field_width(layer, "date", str(date)))
    feat.setAttribute("description", _clip_to_field_width(layer, "description", str(description)))
    # Older Incidents layers created before these fields existed won't have
    # them -- skip rather than raise, matching this layer's overall "reuse
    # whatever's already there" behavior above.
    for field_name, value in (
        ("severity", severity), ("event_type", event_type), ("sub_event_type", sub_event_type),
        ("hazard_type", hazard_type), ("contamination_status", contamination_status),
        ("event_start", event_start), ("event_end", event_end), ("last_verified", last_verified),
    ):
        if value is not None and layer.fields().indexFromName(field_name) >= 0:
            feat.setAttribute(field_name, _clip_to_field_width(layer, field_name, str(value)))

    layer.startEditing()
    added = layer.addFeature(feat)
    layer.commitChanges()
    layer.triggerRepaint()

    if not added:
        return {"error": "Failed to add incident feature to layer."}
    result = {
        "success": True, "layer_name": INCIDENT_LAYER_NAME, "lat": lat, "lon": lon, "date": date,
        "message": (
            f"Point added to '{INCIDENT_LAYER_NAME}' and is live on the map. Report this success plainly -- "
            "do not claim a tool/backend error occurred, and do not give the user a manual script."
        ),
    }
    coding_warnings = _validate_incident_coding(event_type, sub_event_type, hazard_type, contamination_status)
    if coding_warnings:
        result["coding_warnings"] = coding_warnings
    temporal_warnings = _validate_incident_temporal(event_start, event_end)
    if temporal_warnings:
        result["temporal_warnings"] = temporal_warnings
    return result


def _style_named_point_layer(layer):
    """Neutral, readable default styling (black text, white background label by
    'name') for general-purpose layers created via add_point_layer -- distinct
    from add_incident_point's red incident styling, since these aren't
    necessarily incidents."""
    settings = QgsPalLayerSettings()
    settings.fieldName = "name"
    settings.isExpression = False

    text_format = QgsTextFormat()
    text_format.setSize(9)

    background = QgsTextBackgroundSettings()
    background.setEnabled(True)
    background.setType(_SHAPE_RECTANGLE)
    background.setFillColor(QColor(255, 255, 255, 200))
    text_format.setBackground(background)

    settings.setFormat(text_format)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


@register_tool(
    "add_point_layer",
    "Create a new point layer (or append to an existing one with the same name) from a LIST of real, "
    "verified locations in a SINGLE call -- e.g. embassies, offices, facilities, or any set of named points "
    "of interest. Always prefer this over calling add_incident_point repeatedly when plotting more than one "
    "location -- one call per point will exhaust the agent's step limit on anything but a short list. Gather "
    "every location first (search_web/gemini_grounded_search/geocode_and_enrich), then call this once with "
    "the full list. Only ever use real, verified coordinates -- never invent placeholder values. Set "
    "category per point when it's known (e.g. incident severity/type) so apply_categorized_style can later "
    "distinguish them on the map. For conflict/security points, also set event_type (+ sub_event_type) using "
    "ACLED's controlled taxonomy when the source classification maps to it; for explosive-hazard points, set "
    "hazard_type (+ contamination_status) using the IMSMA/IMAS-style vocabulary. Both are optional and "
    "validated -- an unrecognized value comes back as a per-point warning, not a rejected point. If a point "
    "spans a period rather than one instant, also set event_start/event_end (additive alongside any date-like "
    "field in description); last_verified records when the data was last confirmed. If you're "
    "plotting incidents, threats, or other security-related points "
    "and haven't actually gathered them from a real source in this conversation (search_web/"
    "gemini_grounded_search/geocode_and_enrich/geocode_batch, or data the user supplied directly), do not "
    "call this tool with invented data -- say plainly in your chat response that you don't have verified "
    "locations for that, instead of fabricating a plausible-looking dataset. A point layer feeds directly "
    "into exported maps and reports, where fabricated content is far more likely to be trusted and acted "
    "on than the same claim in chat.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string", "description": "Name for the layer, e.g. 'Foreign Embassies'."},
            "points": {
                "type": "array",
                "description": "List of points to add, e.g. [{\"lat\": 31.95, \"lon\": 35.93, \"name\": \"Embassy of France\", \"description\": \"Amman\", \"category\": \"High\"}].",
                "items": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number", "description": "Latitude in degrees (or the northing when `crs` is a projected CRS)."},
                        "lon": {"type": "number", "description": "Longitude in degrees (or the easting when `crs` is a projected CRS)."},
                        "x": {"type": "number", "description": "Easting in `crs` (alternative to lon when `crs` is projected)."},
                        "y": {"type": "number", "description": "Northing in `crs` (alternative to lat when `crs` is projected)."},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "category": {"type": "string", "description": "Optional severity/type label, e.g. 'High', 'Security', 'Flood'. Free text."},
                        "event_type": {"type": "string", "description": f"Optional ACLED-style controlled event type: one of {list(ACLED_EVENT_TAXONOMY)}."},
                        "sub_event_type": {"type": "string", "description": "Optional ACLED-style sub-event type, valid within the chosen event_type."},
                        "hazard_type": {"type": "string", "description": f"Optional IMSMA/IMAS-style explosive-hazard type: one of {IMSMA_HAZARD_TYPES}."},
                        "contamination_status": {"type": "string", "description": f"Optional IMSMA/IMAS-style contamination status: one of {IMSMA_CONTAMINATION_STATUSES}."},
                        "event_start": {"type": "string", "description": "Optional ISO date (YYYY-MM-DD) this point's event/hazard started."},
                        "event_end": {"type": "string", "description": "Optional ISO date (YYYY-MM-DD) this point's event/hazard ended."},
                        "last_verified": {"type": "string", "description": "Optional ISO date (YYYY-MM-DD) this point's data was last confirmed accurate."},
                    },
                    "required": ["name"],
                },
            },
            "crs": {
                "type": "string",
                "description": "CRS the point coordinates are in, e.g. \"EPSG:3857\" or \"EPSG:32636\". Omit ONLY when the "
                "coordinates are already lon/lat degrees. If the user gave projected coordinates (large numbers such as "
                "4902068, 1799912), pass them UNCHANGED with their CRS (the project CRS unless the user says otherwise) -- "
                "the code converts them exactly. NEVER convert coordinates yourself.",
            },
        },
        "required": ["layer_name", "points"],
    },
)
def add_point_layer(layer_name: str, points: list, crs: str = None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if not points:
        return {"error": "points list is empty."}

    # Coordinates are converted here, in code -- never by the model. The rc7 smoke test
    # (2026-09-30, finding F04) placed an analysis origin ~1.3 km from the requested point
    # because the model converted EPSG:3857 -> WGS84 by hand.
    source_crs = _coords.normalize_crs(crs)
    transform = None
    if not _coords.is_geographic(source_crs):
        src = QgsCoordinateReferenceSystem(source_crs)
        if not src.isValid():
            return {"error": f"Unknown crs '{crs}'. Use a code such as \"EPSG:3857\"."}
        _xf = QgsCoordinateTransform(src, QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())

        def transform(x, y):
            pt = _xf.transform(QgsPointXY(x, y))
            return pt.x(), pt.y()

    existing = QgsProject.instance().mapLayersByName(layer_name)
    if existing:
        layer = existing[0]
    else:
        layer = QgsVectorLayer(
            "Point?crs=EPSG:4326&field=name:string(255)&field=description:string(500)&field=category:string(50)"
            "&field=event_type:string(50)&field=sub_event_type:string(80)"
            "&field=hazard_type:string(50)&field=contamination_status:string(50)"
            "&field=event_start:string(30)&field=event_end:string(30)&field=last_verified:string(30)",
            layer_name, "memory",
        )
        if not layer.isValid():
            return {"error": f"Failed to create layer '{layer_name}'"}
        QgsProject.instance().addMapLayer(layer)
        # QGIS-009, 2026-09-14 audit: same reasoning as add_incident_point's identical guard
        # above -- styling is cosmetic and must not block the layer's actual points from
        # being added if it fails.
        try:
            _style_named_point_layer(layer)
        except Exception as e:
            print(f"[humanitarian_tools] Failed to style new '{layer_name}' layer: {e}")

    field_names = [f.name() for f in layer.fields()]
    added = 0
    placed = []
    errors = []
    # Both ACLED/IMSMA coding warnings and event_start/event_end ordering
    # warnings land here -- kept as one per-point aggregate list rather than
    # two, since both are advisory data-quality flags on the same point.
    data_quality_warnings = []
    layer.startEditing()
    for i, pt in enumerate(points):
        try:
            lon, lat = _coords.resolve_lon_lat(pt, source_crs, transform)
        except ValueError as e:
            errors.append(f"Point {i}: {e}")
            continue

        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feat.setAttribute("name", _clip_to_field_width(layer, "name", str(pt.get("name", ""))))
        feat.setAttribute("description",
                           _clip_to_field_width(layer, "description", str(pt.get("description", ""))))
        # Older layers created before these fields existed won't have them --
        # skip rather than raise, matching the reused-existing-layer path above.
        for field_name in (
            "category", "event_type", "sub_event_type", "hazard_type", "contamination_status",
            "event_start", "event_end", "last_verified",
        ):
            if field_name in field_names and pt.get(field_name) is not None:
                feat.setAttribute(field_name, _clip_to_field_width(layer, field_name, str(pt[field_name])))
        point_warnings = _validate_incident_coding(
            pt.get("event_type"), pt.get("sub_event_type"), pt.get("hazard_type"), pt.get("contamination_status"),
        )
        point_warnings = point_warnings + _validate_incident_temporal(pt.get("event_start"), pt.get("event_end"))
        if point_warnings:
            data_quality_warnings.append(f"Point {i}: " + "; ".join(point_warnings))
        if layer.addFeature(feat):
            added += 1
            placed.append({"name": str(pt.get("name", "")), "lon": round(lon, 6), "lat": round(lat, 6)})
        else:
            errors.append(f"Point {i}: failed to add feature")
    layer.commitChanges()
    layer.triggerRepaint()

    result = {"success": added > 0, "layer_name": layer_name, "added": added, "requested": len(points)}
    if placed:
        # The exact WGS84 positions actually used -- report THESE, never numbers computed by hand.
        result["placed_wgs84"] = placed[:20]
    if source_crs and not _coords.is_geographic(source_crs):
        result["converted_from_crs"] = source_crs
    if errors:
        result["errors"] = errors
    if data_quality_warnings:
        result["coding_warnings"] = data_quality_warnings
    if added > 0:
        result["message"] = (
            f"Layer '{layer_name}' now has {added}/{len(points)} point(s) added and is live on the map. "
            "Report this success plainly -- do not claim a tool/backend error occurred, and do not give the "
            "user a manual script or workaround; the layer already exists in the project."
        )
    return result
