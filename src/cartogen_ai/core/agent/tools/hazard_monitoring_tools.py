# -*- coding: utf-8 -*-
"""
Live Hazard Monitoring tools for Cartogen AI.

NASA FIRMS (active fire/thermal detections), NASA EONET (natural event tracker), and GDACS
(UN-coordinated disaster alerts) -- live, recurring-friendly hazard-data fetch tools, distinct
from humanitarian_tools.py's static reference-data fetches (HDX/geoBoundaries/WorldPop/building
footprints, which are one-shot lookups, not meant to be re-run on a schedule).

Bbox convention for all 3 tools here: [min_lon, min_lat, max_lon, max_lat] -- matches
multimodal_remote_sensing.py's search_stac_satellite_imagery, deliberately NOT
humanitarian_tools.py's fetch_building_footprints ([south, west, north, east], a real footgun
confirmed live during this project's own v1.8.3 release smoke test -- see
docs/RELEASE_SMOKE_TEST.md's Run log). Documented explicitly in every schema description below
so the model isn't caught by the same mistake twice.

Recurring-fetch layer reuse: unlike the one-shot fetch tools in humanitarian_tools.py, these are
designed to be re-run on a schedule via monitoring_tools.py's run_monitoring_workflow /
schedule_recurring_workflow. Each tool finds its own previously-created layer (by name) and
REPLACES its features in place on a repeat call, instead of creating a new layer every tick --
otherwise a 5-minute schedule would litter the project with duplicate layers within the hour.
This is new behavior humanitarian_tools.py's one-shot fetch tools don't need.
"""

import csv
import io
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

from .registry import register_tool
from ....infrastructure.auth import CredentialManager
from ...models.confidence import set_layer_confidence
# API-003, 2026-09-14 audit: these 3 fetches had no retry/backoff at all, unlike every LLM
# provider call (post_with_retry/get_with_retry since 2026-09-12) -- a single transient
# network hiccup or 5xx failed the whole tool call outright, on tools specifically designed
# to be re-run on a recurring schedule (see module docstring).
from ._urllib_retry import urlopen_with_retry

try:
    from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


from ....infrastructure.settings_keys import PROJECT_PROPERTY_FETCHED_AT

FETCHED_AT_PROPERTY_KEY = PROJECT_PROPERTY_FETCHED_AT


def _stamp_fetched_at(layer):
    layer.setCustomProperty(FETCHED_AT_PROPERTY_KEY, datetime.now(timezone.utc).isoformat())


def _validate_bbox(bbox):
    """Shared bbox validation for all 3 tools here -- [min_lon, min_lat, max_lon, max_lat].
    Returns an error string, or None if bbox is None or valid."""
    if bbox is None:
        return None
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return "bbox must be [min_lon, min_lat, max_lon, max_lat] (4 numbers)."
    try:
        min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return "bbox values must be numeric."
    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        return f"bbox longitude out of range: {bbox}"
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        return f"bbox latitude out of range: {bbox}"
    if min_lon >= max_lon or min_lat >= max_lat:
        return "bbox must have min_lon < max_lon and min_lat < max_lat -- [min_lon, min_lat, max_lon, max_lat]."
    return None


def _point_in_bbox(lon, lat, bbox):
    if bbox is None:
        return True
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def _clip_to_field_width(layer, fname, value):
    """Clip a string value to its field's declared width before setAttribute.

    Real live crash, 2026-09-16: fetch_gdacs_disaster_alerts's memory layer declares
    field=country:string(255) (mirroring a shapefile-era convention), but GDACS's own
    `country` property is a comma-joined list of every country a regional event (e.g. a
    cyclone spanning several nations) touches -- observed at 261 chars, one event, no
    user action involved. QGIS's memory provider enforces the declared width same as a
    real shapefile would, so setAttribute silently fails (Qt logs "Could not store
    attribute", the point is dropped from the layer, and nothing in this tool's own
    return value reflects that -- the model then reports success on data that partly
    never landed). Clipping defensively here, once, covers every field on every call
    into this shared writer, rather than raising the field width per-source and hoping
    the next external API happens to fit under it."""
    if not isinstance(value, str):
        return value
    # Best-effort: a test double or an unusual provider may not expose a real
    # QgsFields/.length() int -- treat anything that isn't one as unbounded
    # rather than raising or mis-clipping against a mock's identity.
    try:
        width = layer.fields().field(fname).length()
    except Exception:
        return value
    if isinstance(width, int) and width > 0 and len(value) > width:
        return value[:width]
    return value


def _replace_point_features(layer, rows, geometry_key="__geom__"):
    """Find-or-create-then-REPLACE helper shared by the 3 recurring-fetch tools below. Unlike
    humanitarian_tools.py's add_point_layer (which APPENDS to an existing layer), this REPLACES
    every existing feature -- a live-fire/disaster-alert layer re-fetched on a schedule should
    reflect only the latest fetch, not accumulate every prior run's points forever. `rows` is a
    list of dicts; each must have `geometry_key` (a QgsGeometry) plus any attribute keys matching
    the layer's field names (extra keys are ignored, matching add_point_layer's own
    forward-compatible pattern for layers created before a field existed)."""
    existing_ids = [f.id() for f in layer.getFeatures()]
    layer.startEditing()
    if existing_ids:
        layer.deleteFeatures(existing_ids)
    field_names = [f.name() for f in layer.fields()]
    added = 0
    for row in rows:
        feat = QgsFeature(layer.fields())
        feat.setGeometry(row[geometry_key])
        for fname in field_names:
            if fname in row:
                feat.setAttribute(fname, _clip_to_field_width(layer, fname, row[fname]))
        if layer.addFeature(feat):
            added += 1
    layer.commitChanges()
    layer.updateExtents()
    layer.triggerRepaint()
    return added


def _to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# NASA FIRMS -- active fire / thermal-anomaly detections
# ---------------------------------------------------------------------------

# VIIRS confidence is a string ("low"/"nominal"/"high", sometimes abbreviated "l"/"n"/"h"
# depending on the FIRMS product); MODIS confidence is 0-100 numeric. This module only requests
# VIIRS_SNPP_NRT (see fetch_nasa_active_fires_network_phase), so only the string form is ranked
# here -- an unrecognized value defaults to "nominal" rank rather than being silently dropped.
_FIRMS_CONFIDENCE_RANK = {"l": 0, "low": 0, "n": 1, "nominal": 1, "h": 2, "high": 2}


def fetch_nasa_active_fires_network_phase(bbox, days=1, min_confidence="nominal", source="VIIRS_SNPP_NRT"):
    """Pure network phase: queries NASA FIRMS's area API for active fire/thermal detections in
    bbox over the last `days` days. No qgis.core access -- safe to run on a background thread.
    Needs a free FIRMS API key (MAP_KEY), separate from any LLM provider key -- get one at
    https://firms.modaps.eosdis.nasa.gov/api/area/, then add it in Cartogen AI's Settings dialog
    ("NASA FIRMS API Key"). Stored/read via the same CredentialManager every LLM provider key
    already uses (infrastructure/auth.py), keyed by provider string "firms"."""
    bbox_error = _validate_bbox(bbox)
    if bbox_error:
        return {"error": bbox_error}
    if bbox is None:
        return {"error": "bbox is required for fetch_nasa_active_fires -- [min_lon, min_lat, max_lon, max_lat]."}
    try:
        days = int(days)
    except (TypeError, ValueError):
        return {"error": "days must be an integer."}
    if not (1 <= days <= 10):
        return {"error": "days must be between 1 and 10 (FIRMS area API's own limit)."}

    api_key = CredentialManager.get_credential("firms")
    if not api_key:
        return {
            "error": "No NASA FIRMS API key configured. Get a free key at "
            "https://firms.modaps.eosdis.nasa.gov/api/area/, then add it in Cartogen AI's "
            "Settings dialog (\"NASA FIRMS API Key\")."
        }

    min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox)
    area = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{api_key}/{source}/{area}/{days}"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'QGIS-AI-Assistant'})
        with urlopen_with_retry(req, timeout=30) as response:
            csv_text = response.read().decode()
    except Exception as e:
        return {"error": f"NASA FIRMS API request failed: {e}"}

    # FIRMS returns a plain-text error body (not CSV) for a bad key/params, per NASA's own API
    # docs -- that body has no header row a DictReader can use, so detect it up front rather than
    # surfacing a confusing "no such field" error later.
    lowered_head = csv_text[:200].lower()
    if "invalid" in lowered_head or "error" in lowered_head:
        return {"error": f"NASA FIRMS API returned an error: {csv_text[:300].strip()}"}

    reader = csv.DictReader(io.StringIO(csv_text))
    min_rank = _FIRMS_CONFIDENCE_RANK.get(str(min_confidence).strip().lower(), 1)
    detections = []
    for row in reader:
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        conf_raw = str(row.get("confidence", "")).strip().lower()
        conf_rank = _FIRMS_CONFIDENCE_RANK.get(conf_raw, 1)
        if conf_rank < min_rank:
            continue
        acq_date = row.get("acq_date", "")
        acq_time = row.get("acq_time", "")
        detections.append({
            # No stable per-detection ID in FIRMS's CSV -- lat/lon rounded to ~11m precision
            # plus the acquisition date/time is stable enough to dedupe the SAME detection across
            # runs (the satellite re-observes the same fire pixel with the same acq_date/time
            # only once), which is what run_monitoring_workflow's _diff_unit_results needs.
            "unit": f"{lat:.4f}_{lon:.4f}_{acq_date}_{acq_time}",
            "lat": lat, "lon": lon,
            "confidence": row.get("confidence", ""),
            "brightness": row.get("bright_ti4") or row.get("brightness"),
            "frp": row.get("frp"),
            "acq_date": acq_date, "acq_time": acq_time,
            "satellite": row.get("satellite", ""), "daynight": row.get("daynight", ""),
        })

    return {"success": True, "source": source, "bbox": bbox, "days": days, "detections": detections}


def add_nasa_active_fires_layer_main_thread_phase(fetch_result, layer_name="NASA Active Fires"):
    """Main-thread phase: builds/updates the point layer from already-fetched detections. Local
    operations only -- fast, safe to run through the normal main-thread-blocking dispatch."""
    if "error" in fetch_result:
        return fetch_result
    if not QGIS_AVAILABLE:
        return {"success": True, "detection_count": len(fetch_result.get("detections", []))}

    layer = _find_layer_by_name(layer_name)
    if layer is None:
        layer = QgsVectorLayer(
            "Point?crs=EPSG:4326&field=confidence:string(20)&field=brightness:double"
            "&field=frp:double&field=acq_date:string(20)&field=acq_time:string(10)"
            "&field=satellite:string(30)&field=daynight:string(5)",
            layer_name, "memory",
        )
        if not layer.isValid():
            return {"error": f"Failed to create layer '{layer_name}'"}
        QgsProject.instance().addMapLayer(layer)

    rows = [{
        "__geom__": QgsGeometry.fromPointXY(QgsPointXY(d["lon"], d["lat"])),
        "confidence": d.get("confidence", ""),
        "brightness": _to_num(d.get("brightness")),
        "frp": _to_num(d.get("frp")),
        "acq_date": d.get("acq_date", ""),
        "acq_time": d.get("acq_time", ""),
        "satellite": d.get("satellite", ""),
        "daynight": d.get("daynight", ""),
    } for d in fetch_result.get("detections", [])]

    added = _replace_point_features(layer, rows)
    set_layer_confidence(layer, "OBSERVED", reason="NASA FIRMS VIIRS/MODIS satellite thermal-anomaly detection")
    _stamp_fetched_at(layer)

    return {
        "success": True, "layer_name": layer_name, "detection_count": added,
        "detections": fetch_result.get("detections", []),
        "message": f"'{layer_name}' now has {added} active fire detection(s) and is live on the map. "
                    "Report this success plainly.",
    }


@register_tool(
    "fetch_nasa_active_fires",
    "Fetch near-real-time active fire/thermal-anomaly detections from NASA FIRMS (VIIRS satellite "
    "instrument) for a bounding box, and load them as a point layer. Needs a free NASA FIRMS API "
    "key configured in Settings -- if missing, this returns a clear error with a link to get one. "
    "IMPORTANT: bbox is [min_lon, min_lat, max_lon, max_lat] (matches "
    "search_stac_satellite_imagery's convention) -- NOT the [south, west, north, east] order "
    "fetch_building_footprints uses. Re-running this tool (e.g. via schedule_recurring_workflow) "
    "REPLACES the layer's features with the latest fetch rather than accumulating duplicates, so "
    "it's safe to schedule on a recurring interval to watch for new fire activity -- "
    "run_monitoring_workflow will then report new/disappeared detections automatically.",
    {
        "type": "object",
        "properties": {
            "bbox": {"type": "array", "items": {"type": "number"}, "description": "[min_lon, min_lat, max_lon, max_lat] in WGS84 degrees."},
            "days": {"type": "integer", "description": "How many days back to look, 1-10. Defaults to 1."},
            "min_confidence": {"type": "string", "description": "Minimum detection confidence to include: 'low', 'nominal' (default), or 'high'."},
            "layer_name": {"type": "string", "description": "Name for the layer. Defaults to 'NASA Active Fires'. Re-fetching with the same name replaces its features rather than duplicating them."},
        },
        "required": ["bbox"],
    },
)
def fetch_nasa_active_fires(bbox, days=1, min_confidence="nominal", layer_name="NASA Active Fires"):
    fetch_result = fetch_nasa_active_fires_network_phase(bbox, days, min_confidence)
    return add_nasa_active_fires_layer_main_thread_phase(fetch_result, layer_name)


# ---------------------------------------------------------------------------
# NASA EONET -- natural event tracker (wildfires, storms, volcanoes, floods, ...)
# ---------------------------------------------------------------------------

_EONET_BASE_URL = "https://eonet.gsfc.nasa.gov/api/v3/events"


def fetch_nasa_eonet_events_network_phase(bbox=None, category=None, days=20, status="open"):
    """Pure network phase: queries NASA EONET v3 for categorized natural events (wildfires,
    severe storms, volcanoes, floods, sea/lake ice, drought, dust/haze, etc). No qgis.core access
    -- safe off-thread. Free, no API key. Live-verified against the real API 2026-09-12:
    eonet.gsfc.nasa.gov's bbox filter accepted both [min_lon, min_lat, max_lon, max_lat] and
    [min_lon, max_lat, max_lon, min_lat] identically against a known active event, and appears to
    normalize internally -- this tool always sends [min_lon, min_lat, max_lon, max_lat] anyway,
    for consistency with the other 2 tools in this module, plus a client-side bbox re-check below
    as a defensive backstop since EONET's own filtering behavior across every geometry shape
    (tracks, polygons) wasn't exhaustively verified."""
    bbox_error = _validate_bbox(bbox)
    if bbox_error:
        return {"error": bbox_error}
    try:
        days = int(days)
    except (TypeError, ValueError):
        return {"error": "days must be an integer."}
    if days < 1:
        return {"error": "days must be at least 1."}
    if status not in ("open", "closed", "all"):
        return {"error": "status must be 'open', 'closed', or 'all'."}

    params = {"status": status, "days": days}
    if category:
        params["category"] = category
    if bbox:
        params["bbox"] = ",".join(str(v) for v in bbox)
    url = f"{_EONET_BASE_URL}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'QGIS-AI-Assistant'})
        with urlopen_with_retry(req, timeout=30) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        return {"error": f"NASA EONET API request failed: {e}"}
    # A real live crash traced this exact shape (2026-09-13): the request/decode above
    # only guarantees `data` is valid JSON, not that it's a dict -- an API returning a
    # bare string/list/null error body (rate limiting, a CDN error page served as JSON)
    # would otherwise reach `data.get(...)` below and crash with an uncaught
    # AttributeError, escaping all the way out of the tool-calling loop uncaught (see
    # agent_orchestrator.py's _execute_tool for the matching generic safety net added at the same
    # time -- this specific check gives a clear, attributable error instead of relying
    # on that net alone).
    if not isinstance(data, dict):
        return {"error": f"NASA EONET API returned an unexpected response shape ({type(data).__name__}, expected an object)."}

    bbox_f = [float(v) for v in bbox] if bbox else None
    events_out = []
    for ev in data.get("events", []):
        geometry = ev.get("geometry") or []
        if not geometry:
            continue
        # An event can carry a whole track (e.g. a storm's path over several days) -- use the
        # MOST RECENT geometry entry as this event's current position, not the first (earliest),
        # so a scheduled re-fetch reflects where the event is now.
        latest = geometry[-1]
        coords = latest.get("coordinates")
        if latest.get("type") != "Point" or not coords or len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        if bbox_f and not _point_in_bbox(lon, lat, bbox_f):
            continue
        categories = [c.get("title", c.get("id", "")) for c in ev.get("categories", [])]
        events_out.append({
            "unit": ev.get("id"),
            "lat": lat, "lon": lon,
            "title": ev.get("title", ""),
            "category": ", ".join(categories),
            "date": latest.get("date", ""),
            "closed": ev.get("closed"),
            "link": ev.get("link", ""),
        })

    return {"success": True, "status": status, "days": days, "events": events_out}


def add_nasa_eonet_events_layer_main_thread_phase(fetch_result, layer_name="NASA EONET Events"):
    """Main-thread phase: builds/updates the point layer from already-fetched events."""
    if "error" in fetch_result:
        return fetch_result
    if not QGIS_AVAILABLE:
        return {"success": True, "event_count": len(fetch_result.get("events", []))}

    layer = _find_layer_by_name(layer_name)
    if layer is None:
        layer = QgsVectorLayer(
            "Point?crs=EPSG:4326&field=title:string(255)&field=category:string(255)"
            "&field=date:string(30)&field=closed:string(30)&field=link:string(500)",
            layer_name, "memory",
        )
        if not layer.isValid():
            return {"error": f"Failed to create layer '{layer_name}'"}
        QgsProject.instance().addMapLayer(layer)

    rows = [{
        "__geom__": QgsGeometry.fromPointXY(QgsPointXY(e["lon"], e["lat"])),
        "title": e.get("title", ""),
        "category": e.get("category", ""),
        "date": e.get("date", ""),
        "closed": e.get("closed") or "",
        "link": e.get("link", ""),
    } for e in fetch_result.get("events", [])]

    added = _replace_point_features(layer, rows)
    set_layer_confidence(layer, "OBSERVED", reason="NASA EONET satellite/instrument-detected natural event")
    _stamp_fetched_at(layer)

    return {
        "success": True, "layer_name": layer_name, "event_count": added,
        "events": fetch_result.get("events", []),
        "message": f"'{layer_name}' now has {added} natural event(s) and is live on the map. "
                    "Report this success plainly.",
    }


@register_tool(
    "fetch_nasa_eonet_events",
    "Fetch open (or closed/all) natural events from NASA EONET -- wildfires, severe storms, "
    "volcanoes, floods, sea/lake ice, drought, dust/haze, and more -- for an optional bounding "
    "box, and load them as a point layer (each event's most recent known position). Free, no API "
    "key. IMPORTANT: bbox is [min_lon, min_lat, max_lon, max_lat], same convention as "
    "fetch_nasa_active_fires and search_stac_satellite_imagery. Re-running this tool REPLACES the "
    "layer's features with the latest fetch, so it's safe to schedule on a recurring interval.",
    {
        "type": "object",
        "properties": {
            "bbox": {"type": "array", "items": {"type": "number"}, "description": "Optional [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees. Omit for global coverage."},
            "category": {"type": "string", "description": "Optional EONET category id to filter to, e.g. 'wildfires', 'severeStorms', 'volcanoes', 'floods', 'drought'."},
            "days": {"type": "integer", "description": "How many days back to look. Defaults to 20."},
            "status": {"type": "string", "description": "'open' (default), 'closed', or 'all'."},
            "layer_name": {"type": "string", "description": "Name for the layer. Defaults to 'NASA EONET Events'. Re-fetching with the same name replaces its features rather than duplicating them."},
        },
        "required": [],
    },
)
def fetch_nasa_eonet_events(bbox=None, category=None, days=20, status="open", layer_name="NASA EONET Events"):
    fetch_result = fetch_nasa_eonet_events_network_phase(bbox, category, days, status)
    return add_nasa_eonet_events_layer_main_thread_phase(fetch_result, layer_name)


# ---------------------------------------------------------------------------
# GDACS -- UN-coordinated disaster alerts
# ---------------------------------------------------------------------------

_GDACS_EVENTLIST_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
_GDACS_ALERT_RANK = {"green": 0, "orange": 1, "red": 2}


def fetch_gdacs_disaster_alerts_network_phase(bbox=None, min_alert_level="Orange", country=None):
    """Pure network phase: queries GDACS's public event-list API for UN-coordinated disaster
    alerts (earthquakes, floods, tropical cyclones, volcanoes, wildfires, droughts), each with a
    human-assigned Green/Orange/Red severity. No qgis.core access -- safe off-thread. Free, no API
    key. Live-verified against the real API 2026-09-12: the endpoint's own bbox query parameter
    does NOT actually filter server-side (confirmed: a bbox nowhere near a known event still
    returned it) -- so this fetches the full current event list (~99 events at verification time,
    a manageable size) and filters by bbox and alert level client-side, the same
    "server doesn't reliably filter, filter after fetching" pattern fetch_building_footprints
    already uses for its own tile-crop step. GDACS's default Green ("Advisory," minor/localized
    impact) is excluded unless min_alert_level is lowered -- matches the clutter-reduction
    convention a comparable product (WorldMonitor) uses for the same source.

    country (2026-09-15, direct live report -- "my request was for yemen the client brought all
    the incidents in the world"): a request naming a place, not a bbox, previously had no way to
    scope this tool -- bbox defaults to None/"omit for global coverage", so a model that skips
    geocoding the place first (nothing forced it to) got every alert on Earth. GDACS's own feed
    already carries a per-alert `country` string (extracted into the result below, but never
    filtered on before this) -- a case-insensitive substring match against it is a second,
    independent way to scope a request by name, without requiring the model to derive a bbox
    first. bbox and country can be combined (both must match); either alone is enough to avoid
    the global-fallback case this fix closes."""
    bbox_error = _validate_bbox(bbox)
    if bbox_error:
        return {"error": bbox_error}
    min_rank = _GDACS_ALERT_RANK.get(str(min_alert_level).strip().lower(), 1)
    country_needle = str(country).strip().lower() if country else None

    try:
        req = urllib.request.Request(_GDACS_EVENTLIST_URL, headers={'User-Agent': 'QGIS-AI-Assistant'})
        with urlopen_with_retry(req, timeout=30) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        return {"error": f"GDACS API request failed: {e}"}
    # See fetch_nasa_eonet_events_network_phase's identical comment above -- same real
    # live crash, same fix, GDACS's own docs already warn its data "may require further
    # validation" so a malformed non-dict body here is a real, not hypothetical, risk.
    if not isinstance(data, dict):
        return {"error": f"GDACS API returned an unexpected response shape ({type(data).__name__}, expected an object)."}

    bbox_f = [float(v) for v in bbox] if bbox else None
    alerts = []
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        coords = geom.get("coordinates")
        if geom.get("type") != "Point" or not coords or len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        if bbox_f and not _point_in_bbox(lon, lat, bbox_f):
            continue
        country_value = props.get("country", "")
        if country_needle and country_needle not in str(country_value).strip().lower():
            continue
        alert_level = props.get("alertlevel", "")
        rank = _GDACS_ALERT_RANK.get(str(alert_level).strip().lower(), -1)
        if rank < min_rank:
            continue
        alerts.append({
            "unit": str(props.get("eventid")),
            "lat": lat, "lon": lon,
            "event_type": props.get("eventtype", ""),
            "name": props.get("eventname", props.get("name", "")),
            "description": props.get("description", ""),
            "alert_level": alert_level,
            "country": country_value,
            "from_date": props.get("fromdate", ""),
            "to_date": props.get("todate", ""),
        })

    return {"success": True, "bbox": bbox, "min_alert_level": min_alert_level, "country": country, "alerts": alerts}


def add_gdacs_disaster_alerts_layer_main_thread_phase(fetch_result, layer_name="GDACS Disaster Alerts"):
    """Main-thread phase: builds/updates the point layer from already-fetched alerts."""
    if "error" in fetch_result:
        return fetch_result
    if not QGIS_AVAILABLE:
        return {"success": True, "alert_count": len(fetch_result.get("alerts", []))}

    layer = _find_layer_by_name(layer_name)
    if layer is None:
        layer = QgsVectorLayer(
            "Point?crs=EPSG:4326&field=event_type:string(10)&field=name:string(255)"
            "&field=description:string(500)&field=alert_level:string(20)&field=country:string(255)"
            "&field=from_date:string(30)&field=to_date:string(30)",
            layer_name, "memory",
        )
        if not layer.isValid():
            return {"error": f"Failed to create layer '{layer_name}'"}
        QgsProject.instance().addMapLayer(layer)

    rows = [{
        "__geom__": QgsGeometry.fromPointXY(QgsPointXY(a["lon"], a["lat"])),
        "event_type": a.get("event_type", ""),
        "name": a.get("name", ""),
        "description": a.get("description", ""),
        "alert_level": a.get("alert_level", ""),
        "country": a.get("country", ""),
        "from_date": a.get("from_date", ""),
        "to_date": a.get("to_date", ""),
    } for a in fetch_result.get("alerts", [])]

    added = _replace_point_features(layer, rows)
    set_layer_confidence(layer, "DERIVED", reason="GDACS computed multi-input alert level, human-reviewed")
    _stamp_fetched_at(layer)

    return {
        "success": True, "layer_name": layer_name, "alert_count": added,
        "alerts": fetch_result.get("alerts", []),
        "message": f"'{layer_name}' now has {added} disaster alert(s) and is live on the map. "
                    "Report this success plainly.",
    }


@register_tool(
    "fetch_gdacs_disaster_alerts",
    "Fetch current UN-coordinated disaster alerts from GDACS (Global Disaster Alert and "
    "Coordination System) -- earthquakes, floods, tropical cyclones, volcanoes, wildfires, "
    "droughts -- each with a human-assigned Green/Orange/Red severity, and load them as a point "
    "layer. GDACS's own terms of use (verified 2026-09-12) state that its automated alerts and "
    "impact estimations 'may require further validation' and 'should not be used for decision "
    "making without prior confirmation of their validity' -- pass this caveat along if a user "
    "asks about acting on a specific alert. Free, no API key. Defaults to Orange and above (excludes minor/localized Green "
    "advisories) -- pass min_alert_level='Green' to include everything. IMPORTANT: bbox (when "
    "given) is [min_lon, min_lat, max_lon, max_lat], same convention as fetch_nasa_active_fires "
    "and fetch_nasa_eonet_events. IMPORTANT: if the user names a specific place ('the latest "
    "GDACS alerts for Yemen') rather than giving coordinates, pass country (e.g. country='Yemen') "
    "-- omitting BOTH bbox and country returns every alert worldwide, which is very rarely what a "
    "place-scoped request actually wants. Re-running this tool REPLACES the layer's features with "
    "the latest fetch, so it's safe to schedule on a recurring interval.",
    {
        "type": "object",
        "properties": {
            "bbox": {"type": "array", "items": {"type": "number"}, "description": "Optional [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees. Omit for global coverage."},
            "min_alert_level": {"type": "string", "description": "Minimum alert level to include: 'Green', 'Orange' (default), or 'Red'."},
            "country": {"type": "string", "description": "Optional country name to scope results to (case-insensitive substring match against GDACS's own per-alert country field, e.g. 'Yemen'). Use this or bbox (or both) whenever the user named a specific place -- don't leave both empty for a place-scoped request."},
            "layer_name": {"type": "string", "description": "Name for the layer. Defaults to 'GDACS Disaster Alerts'. Re-fetching with the same name replaces its features rather than duplicating them."},
        },
        "required": [],
    },
)
def fetch_gdacs_disaster_alerts(bbox=None, min_alert_level="Orange", country=None, layer_name="GDACS Disaster Alerts"):
    fetch_result = fetch_gdacs_disaster_alerts_network_phase(bbox, min_alert_level, country)
    return add_gdacs_disaster_alerts_layer_main_thread_phase(fetch_result, layer_name)


# ---------------------------------------------------------------------------
# Composite: one-call hazard situation dashboard
# ---------------------------------------------------------------------------

@register_tool(
    "generate_situation_dashboard",
    "Fetch live hazard data (NASA active fires, NASA EONET natural events, GDACS disaster "
    "alerts) for a bounding box and export it all as one interactive HTML situation dashboard in "
    "a single call -- the fastest way to answer 'what hazards are happening in this area right "
    "now'. Internally calls fetch_nasa_active_fires/fetch_nasa_eonet_events/"
    "fetch_gdacs_disaster_alerts (each skipped gracefully, not fatally, if its source errors -- "
    "e.g. no FIRMS API key configured) then generate_html_dashboard. IMPORTANT: bbox is "
    "[min_lon, min_lat, max_lon, max_lat], same convention as the 3 fetch tools it calls.",
    {
        "type": "object",
        "properties": {
            "bbox": {"type": "array", "items": {"type": "number"}, "description": "[min_lon, min_lat, max_lon, max_lat] in WGS84 degrees."},
            "output_path": {"type": "string", "description": "Optional output HTML file path."},
            "title": {"type": "string", "description": "Optional dashboard title."},
            "include_fires": {"type": "boolean", "description": "Include NASA FIRMS active fires. Defaults to true."},
            "include_eonet": {"type": "boolean", "description": "Include NASA EONET natural events. Defaults to true."},
            "include_disasters": {"type": "boolean", "description": "Include GDACS disaster alerts. Defaults to true."},
        },
        "required": ["bbox"],
    },
)
def generate_situation_dashboard(bbox, output_path=None, title=None,
                                  include_fires=True, include_eonet=True, include_disasters=True):
    bbox_error = _validate_bbox(bbox)
    if bbox_error:
        return {"error": bbox_error}
    if bbox is None:
        return {"error": "bbox is required -- [min_lon, min_lat, max_lon, max_lat]."}

    from .export_tools import generate_html_dashboard

    layers_config = []
    source_errors = []

    # .get("layer_name") rather than ["layer_name"] throughout below -- when QGIS isn't
    # available (this module's own import-time fallback, exercised by this repo's non-QGIS
    # test suite), add_*_layer_main_thread_phase returns a count-only stub with no layer_name
    # key at all rather than raising, and this composite tool must degrade the same way, not
    # KeyError on a field that was never promised outside a real QGIS session.
    if include_fires:
        fires = fetch_nasa_active_fires(bbox)
        if "error" in fires:
            source_errors.append(f"Active fires: {fires['error']}")
        elif fires.get("layer_name") and fires.get("detection_count", 0) > 0:
            layers_config.append({
                "layer_name": fires["layer_name"],
                "popup_fields": ["confidence", "brightness", "frp", "acq_date", "acq_time"],
                "popup_labels": ["Confidence", "Brightness", "Fire Radiative Power", "Date", "Time"],
            })

    if include_eonet:
        eonet = fetch_nasa_eonet_events(bbox)
        if "error" in eonet:
            source_errors.append(f"EONET events: {eonet['error']}")
        elif eonet.get("layer_name") and eonet.get("event_count", 0) > 0:
            layers_config.append({
                "layer_name": eonet["layer_name"],
                "popup_fields": ["title", "category", "date"],
                "popup_labels": ["Event", "Category", "Date"],
            })

    if include_disasters:
        disasters = fetch_gdacs_disaster_alerts(bbox)
        if "error" in disasters:
            source_errors.append(f"GDACS alerts: {disasters['error']}")
        elif disasters.get("layer_name") and disasters.get("alert_count", 0) > 0:
            layers_config.append({
                "layer_name": disasters["layer_name"],
                "popup_fields": ["name", "alert_level", "description", "country"],
                "popup_labels": ["Event", "Alert Level", "Description", "Country"],
            })

    if not layers_config:
        return {
            "error": "No hazard data available to build a dashboard -- " +
                     ("; ".join(source_errors) if source_errors else "no active hazards found in this bbox."),
        }

    result = generate_html_dashboard(layers_config, title=title or "Hazard Situation Dashboard", output_path=output_path)
    if source_errors:
        result["source_warnings"] = source_errors
    return result
