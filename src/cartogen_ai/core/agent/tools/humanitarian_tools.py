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
from ._cache_utils import TTLCache
from ._qgis_enum_compat import resolve_qgis_enum
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
        QgsRasterLayer,
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


def fetch_geoboundaries_network_phase(iso3: str, admin_level: str = "ADM1") -> dict:
    """Pure network phase: queries the geoBoundaries API and downloads the actual
    geojson boundary file to a local temp file. No qgis.core access -- safe to
    run on a background thread. Used by agent.py's two-phase dispatch to keep
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


def fetch_hdx_admin_boundaries_network_phase(iso3: str, admin_level: str = "ADM1") -> dict:
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
    except Exception:
        pass

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
        },
        "required": ["iso3"],
    },
)
def fetch_hdx_admin_boundaries(iso3: str, admin_level: str = "ADM1"):
    """Combines both phases inline for standalone/direct callers; agent.py's
    two-phase dispatch calls the two phase functions above separately instead,
    to keep the network fetch off the QGIS main GUI thread (same pattern as
    fetch_geoboundaries)."""
    fetch_result = fetch_hdx_admin_boundaries_network_phase(iso3, admin_level)
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


def fetch_building_footprints_network_phase(country_name, bbox, max_features=5000):
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
        },
        "required": ["country_name", "bbox"],
    },
)
def fetch_building_footprints(country_name, bbox, max_features=5000):
    """Combines both phases inline for standalone/direct callers; agent.py's
    two-phase dispatch calls the two phase functions above separately
    instead, to keep the network fetch off the QGIS main GUI thread (same
    pattern as fetch_geoboundaries/fetch_hdx_admin_boundaries)."""
    fetch_result = fetch_building_footprints_network_phase(country_name, bbox, max_features)
    final = add_building_footprints_layer_main_thread_phase(fetch_result)
    local_path = fetch_result.get("local_path")
    if local_path:
        import os
        try:
            os.remove(local_path)
        except OSError:
            pass
    return final


@register_tool("fetch_geoboundaries", "Download administrative boundaries from geoBoundaries API.", {"type": "object", "properties": {"iso3": {"type": "string"}, "admin_level": {"type": "string"}}, "required": ["iso3", "admin_level"]})
def fetch_geoboundaries(iso3: str, admin_level: str = "ADM1"):
    """Queries geoBoundaries API for ISO3 country code and ADM level. Does both
    phases inline for standalone/direct callers; agent.py's two-phase dispatch
    calls the two phase functions above separately instead, to keep the network
    fetch off the QGIS main GUI thread."""
    fetch_result = fetch_geoboundaries_network_phase(iso3, admin_level)
    final = add_geoboundaries_layer_main_thread_phase(fetch_result)
    local_path = fetch_result.get("local_path")
    if local_path:
        import os
        try:
            os.remove(local_path)
        except OSError:
            pass
    return final


def fetch_worldpop_population_network_phase(iso3: str, year: str = None) -> dict:
    """Pure network phase: queries WorldPop's API for available population raster
    datasets for a country, picks the requested (or most recent) year, and
    downloads the actual GeoTIFF. These are large (100MB-1GB+ depending on
    country size), so this can take a while -- exactly why it's split out to
    run on a background thread rather than the QGIS main GUI thread. No
    qgis.core access."""
    iso3 = (iso3 or "").upper().strip()
    if len(iso3) != 3 or not iso3.isalpha():
        return {"error": "iso3 must be a 3-letter ISO country code, e.g. 'YEM'."}

    cache_key = ("worldpop", iso3, year)
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
        req2 = urllib.request.Request(file_urls[0], headers={'User-Agent': 'QGIS-AI-Assistant'})
        with _build_safe_opener().open(req2, timeout=300) as response2:
            raster_bytes = response2.read()

        import os
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix=".tif")
        with os.fdopen(fd, "wb") as f:
            f.write(raster_bytes)

        result = {
            "success": True, "iso3": iso3, "year": dataset.get("popyear"),
            "download_url": file_urls[0], "local_path": tmp_path,
        }
        _LOOKUP_CACHE.set(cache_key, result)
        return result
    except Exception as e:
        return {"error": f"WorldPop API request failed: {e}"}


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

    layer_name = f"{fetch_result['iso3']}_population_{fetch_result.get('year')}"
    layer = QgsRasterLayer(local_path, layer_name)
    if layer.isValid():
        QgsProject.instance().addMapLayer(layer)
        return {"success": True, "layer_name": layer_name, "iso3": fetch_result.get("iso3"), "year": fetch_result.get("year")}

    return {"success": True, "iso3": fetch_result.get("iso3"), "year": fetch_result.get("year")}


@register_tool(
    "fetch_worldpop_population",
    "Download a country's gridded population raster from WorldPop (open, free population data at "
    "~100m resolution) and load it as a layer -- an open-data approximation of what ArcGIS's "
    "Business Analyst extension provides with proprietary demographic data. Files are large "
    "(100MB-1GB+ depending on country size), so this can take a while. After loading, use "
    "estimate_population_exposure to sum population within a specific area.",
    {
        "type": "object",
        "properties": {
            "iso3": {"type": "string", "description": "3-letter ISO country code, e.g. 'YEM'."},
            "year": {"type": "string", "description": "Population year, e.g. '2020'. Omit to use the most recent available."},
        },
        "required": ["iso3"],
    },
)
def fetch_worldpop_population(iso3: str, year: str = None):
    """Does both phases inline for standalone/direct callers; agent.py's
    two-phase dispatch calls the two phase functions above separately instead,
    to keep the (potentially large, slow) download off the QGIS main GUI
    thread. No cleanup of the downloaded file -- see
    add_worldpop_population_layer_main_thread_phase for why."""
    fetch_result = fetch_worldpop_population_network_phase(iso3, year)
    return add_worldpop_population_layer_main_thread_phase(fetch_result)


INCIDENT_LAYER_NAME = "Incidents"

# Two optional controlled incident-coding vocabularies, alongside (not
# replacing) the existing freeform severity/category fields -- per
# docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md Section V's gap ("no controlled/
# authorized incident-coding vocabulary"). Baron's decision, 2026-09-04: support
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
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
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
                    "required": ["lat", "lon", "name"],
                },
            },
        },
        "required": ["layer_name", "points"],
    },
)
def add_point_layer(layer_name: str, points: list):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if not points:
        return {"error": "points list is empty."}

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
    errors = []
    # Both ACLED/IMSMA coding warnings and event_start/event_end ordering
    # warnings land here -- kept as one per-point aggregate list rather than
    # two, since both are advisory data-quality flags on the same point.
    data_quality_warnings = []
    layer.startEditing()
    for i, pt in enumerate(points):
        try:
            lat = float(pt["lat"])
            lon = float(pt["lon"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"Point {i}: missing or invalid lat/lon")
            continue
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            errors.append(f"Point {i}: lat/lon out of range ({lat}, {lon})")
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
        else:
            errors.append(f"Point {i}: failed to add feature")
    layer.commitChanges()
    layer.triggerRepaint()

    result = {"success": added > 0, "layer_name": layer_name, "added": added, "requested": len(points)}
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
