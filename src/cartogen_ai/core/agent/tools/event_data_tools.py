"""
Event-data tools for Cartogen AI: USGS earthquakes and UCDP organised-violence events.

Same two-phase shape and the same layer-refresh behaviour as hazard_monitoring_tools.py (a pure network phase that is safe off-thread,
then a main-thread phase that builds or REPLACES a point layer), and the same bbox convention [min_lon, min_lat, max_lon, max_lat].
Both read open data that needs no key; every fetch goes through core/net (QGIS network stack).

Verified live against the real services on 2026-10-11 (from a session with network access): USGS answered GeoJSON; the UCDP download
page listed the Candidate Events CSV and its columns. What has NOT been checked: behaviour in a running QGIS session, and the
layers' look on a map. The UCDP data is a monthly candidate release that lags real time by weeks (UCDP's own wording: candidate
events are preliminary), so the tool says so in every result. UCDP's JSON API needs an access token and is not used here.
"""
import csv
import io
import json
import os
import re
import tempfile
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from .registry import register_tool
from ._edit_session import EditError
from ._layer_checks import empty_fetch_result
from ...models.confidence import set_layer_confidence
from ._urllib_retry import urlopen_with_retry
from ...net import build_request as _net_build_request
from ...net import read_capped as _read_capped
from .hazard_monitoring_tools import (
    QGIS_AVAILABLE, _find_layer_by_name, _point_in_bbox, _replace_point_features, _stamp_fetched_at, _style_hazard, _validate_bbox,
)

if QGIS_AVAILABLE:
    from qgis.core import QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

_USER_AGENT = {"User-Agent": "QGIS-AI-Assistant"}

# --------------------------------------------------------------------------------------------------------------------------------
# USGS earthquakes
# --------------------------------------------------------------------------------------------------------------------------------
_USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
_USGS_MAX_EVENTS = 5000


def _magnitude_band(mag):
    if mag is None:
        return "unknown"
    for low, label in ((8, "M8+"), (7, "M7-8"), (6, "M6-7"), (5, "M5-6"), (4, "M4-5"), (3, "M3-4")):
        if mag >= low:
            return label
    return "below M3"


def parse_usgs_features(data, bbox=None):
    """Pure: USGS GeoJSON FeatureCollection -> list of event dicts. Skips features without a usable point."""
    events = []
    for feat in (data.get("features") or []):
        coords = ((feat.get("geometry") or {}).get("coordinates")) or []
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        if not _point_in_bbox(lon, lat, bbox):
            continue
        props = feat.get("properties") or {}
        mag = props.get("mag")
        ms = props.get("time")
        when = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if isinstance(ms, (int, float)) else ""
        events.append({
            "event_id": feat.get("id") or "", "lat": lat, "lon": lon,
            "title": props.get("place") or "", "magnitude": float(mag) if isinstance(mag, (int, float)) else None,
            "category": _magnitude_band(float(mag) if isinstance(mag, (int, float)) else None),
            "depth_km": float(coords[2]) if len(coords) > 2 and coords[2] is not None else None,
            "time": when, "alert": props.get("alert") or "", "tsunami": int(props.get("tsunami") or 0),
            "link": props.get("url") or "",
        })
    return events


def fetch_usgs_earthquakes_network_phase(bbox=None, days=7, min_magnitude=4.5, max_events=1000):
    """Pure network phase (no qgis.core): USGS FDSN event service, GeoJSON, no key."""
    bbox_error = _validate_bbox(bbox)
    if bbox_error:
        return {"error": bbox_error}
    try:
        days = int(days)
        min_magnitude = float(min_magnitude)
        max_events = int(max_events)
    except (TypeError, ValueError):
        return {"error": "days and max_events must be integers and min_magnitude a number."}
    if days < 1 or days > 365:
        return {"error": "days must be between 1 and 365."}
    max_events = max(1, min(max_events, _USGS_MAX_EVENTS))
    start = datetime.now(timezone.utc) - timedelta(days=days)
    params = {"format": "geojson", "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"), "minmagnitude": min_magnitude,
              "orderby": "time", "limit": max_events}
    if bbox:
        params.update({"minlongitude": bbox[0], "minlatitude": bbox[1], "maxlongitude": bbox[2], "maxlatitude": bbox[3]})
    url = f"{_USGS_URL}?{urllib.parse.urlencode(params)}"
    try:
        with urlopen_with_retry(_net_build_request(url, headers=_USER_AGENT), timeout=30) as response:
            data = json.loads(_read_capped(response).decode())
    except Exception as e:
        return {"error": f"USGS earthquake API request failed: {e}"}
    if not isinstance(data, dict):
        return {"error": f"USGS earthquake API returned an unexpected response shape ({type(data).__name__}, expected an object)."}
    events = parse_usgs_features(data, [float(v) for v in bbox] if bbox else None)
    return {"success": True, "days": days, "min_magnitude": min_magnitude, "events": events,
            "truncated": len(events) >= max_events,
            "source": "USGS Earthquake Hazards Program, earthquake.usgs.gov (public domain; reviewed and automatic solutions mixed)"}


def add_usgs_earthquakes_layer_main_thread_phase(fetch_result, layer_name="USGS Earthquakes"):
    if "error" in fetch_result:
        return fetch_result
    if not QGIS_AVAILABLE:
        return {"success": True, "event_count": len(fetch_result.get("events", []))}
    created = False
    layer = _find_layer_by_name(layer_name)
    if layer is None and not fetch_result.get("events"):
        return empty_fetch_result(layer_name, "earthquakes")
    if layer is None:
        layer = QgsVectorLayer(
            "Point?crs=EPSG:4326&field=event_id:string(40)&field=title:string(255)&field=category:string(30)"
            "&field=magnitude:double&field=depth_km:double&field=time:string(30)&field=alert:string(10)"
            "&field=tsunami:int&field=link:string(500)", layer_name, "memory")
        if not layer.isValid():
            return {"error": f"Failed to create layer '{layer_name}'"}
        QgsProject.instance().addMapLayer(layer)
        created = True
    rows = [dict(e, __geom__=QgsGeometry.fromPointXY(QgsPointXY(e["lon"], e["lat"]))) for e in fetch_result.get("events", [])]
    try:
        added = _replace_point_features(layer, rows)
    except EditError as e:
        return {"error": f"Could not update layer '{layer_name}': {e} The previous contents were kept."}
    if created:
        _style_hazard(layer, "eonet")          # categorised by the 'category' field; here that is the magnitude band
    set_layer_confidence(layer, "OBSERVED", reason="USGS instrument-detected earthquakes (some automatic, some reviewed)")
    _stamp_fetched_at(layer)
    note = " The result hit the maximum event count, so older events were left out." if fetch_result.get("truncated") else ""
    return {"success": True, "layer_name": layer_name, "event_count": added, "events": fetch_result.get("events", [])[:50],
            "source": fetch_result.get("source"),
            "message": f"'{layer_name}' now has {added} earthquake(s) of magnitude {fetch_result.get('min_magnitude')} or more in the last "
                       f"{fetch_result.get('days')} day(s).{note} Report this plainly and name the source."}


@register_tool(
    "fetch_usgs_earthquakes",
    "Fetch recent earthquakes from the USGS (United States Geological Survey) for an optional bounding box and load them as a point "
    "layer coloured by magnitude band, with magnitude, depth, time, alert level, tsunami flag and a link per event. Free, no API key. "
    "IMPORTANT: bbox is [min_lon, min_lat, max_lon, max_lat], same convention as fetch_nasa_eonet_events. Defaults: last 7 days, "
    "magnitude 4.5 or more, up to 1000 events. Re-running REPLACES the layer's features, so it is safe to schedule.",
    {
        "type": "object",
        "properties": {
            "bbox": {"type": "array", "items": {"type": "number"}, "description": "Optional [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees. Omit for global coverage."},
            "days": {"type": "integer", "description": "How many days back (1 to 365). Defaults to 7."},
            "min_magnitude": {"type": "number", "description": "Smallest magnitude to include. Defaults to 4.5."},
            "max_events": {"type": "integer", "description": "Most events to return (newest first). Defaults to 1000, at most 5000."},
            "layer_name": {"type": "string", "description": "Name for the layer. Defaults to 'USGS Earthquakes'."},
        },
        "required": [],
    },
    keywords=[
        "earthquake", "quake", "seismic", "magnitude", "tremor", "aftershock", "usgs",
    ],
)
def fetch_usgs_earthquakes(bbox=None, days=7, min_magnitude=4.5, max_events=1000, layer_name="USGS Earthquakes"):
    return add_usgs_earthquakes_layer_main_thread_phase(
        fetch_usgs_earthquakes_network_phase(bbox, days, min_magnitude, max_events), layer_name)


# --------------------------------------------------------------------------------------------------------------------------------
# UCDP (Uppsala Conflict Data Program) Candidate Events
# --------------------------------------------------------------------------------------------------------------------------------
_UCDP_DOWNLOADS_PAGE = "https://ucdp.uu.se/downloads/"
_UCDP_CANDIDATE_BASE = "https://ucdp.uu.se/downloads/candidateged/"
# GEDEvent_v26_0_8.csv is a single monthly release; GEDEvent_v26_01_26_06.csv (a range of months) deliberately does not match.
_UCDP_FILE_RE = re.compile(r"candidateged/(GEDEvent_v(\d+)_(\d+)_(\d+)\.csv)")
_UCDP_CACHE_HOURS = 12
_UCDP_VIOLENCE = {"1": "State-based conflict", "2": "Non-state conflict", "3": "One-sided violence"}
_UCDP_MAX_EVENTS = 5000
_UCDP_ATTRIBUTION = ("UCDP Candidate Events Dataset, Uppsala Conflict Data Program (ucdp.uu.se), licence CC BY 4.0; cite the "
                     "publications listed on the UCDP downloads page. Candidate events are preliminary and published with a delay.")


def find_latest_candidate_file(page_html):
    """Pure: the newest single-release Candidate Events CSV name on the UCDP downloads page, or None."""
    found = {tuple(int(g) for g in m.groups()[1:]): m.group(1) for m in _UCDP_FILE_RE.finditer(page_html or "")}
    return found[max(found)] if found else None


def parse_ucdp_candidate_csv(text, country=None, bbox=None, start_date=None, end_date=None, min_deaths=0):
    """Pure: Candidate Events CSV text -> (events, latest_event_date, rows_read), filtered. Dates are 'YYYY-MM-DD' strings."""
    events, latest, total = [], "", 0
    country_l = (country or "").strip().lower()
    for row in csv.DictReader(io.StringIO(text)):
        total += 1
        date = (row.get("date_start") or "")[:10]
        latest = max(latest, date)
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if country_l and country_l not in (row.get("country") or "").lower():
            continue
        if not _point_in_bbox(lon, lat, bbox):
            continue
        if (start_date and date < start_date) or (end_date and date > end_date):
            continue
        best = _int(row.get("best"))
        if best < min_deaths:
            continue
        events.append({
            "event_id": str(row.get("id") or ""), "lat": lat, "lon": lon, "date": date, "country": row.get("country") or "",
            "adm_1": row.get("adm_1") or "", "conflict_name": row.get("conflict_name") or "",
            "category": _UCDP_VIOLENCE.get(str(row.get("type_of_violence")), "Other"),
            "deaths_best": best, "deaths_low": _int(row.get("low")), "deaths_high": _int(row.get("high")),
            "location_precision": _int(row.get("where_prec")), "clarity": row.get("event_clarity") or "",
        })
    return events, latest, total


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _ucdp_cache_path(name):
    return os.path.join(tempfile.gettempdir(), "cartogen_ucdp", name)


def _download_text(url, timeout):
    with urlopen_with_retry(_net_build_request(url, headers=_USER_AGENT), timeout=timeout) as response:
        return _read_capped(response).decode("utf-8-sig", errors="replace")


def fetch_ucdp_conflict_events_network_phase(country=None, bbox=None, start_date=None, end_date=None, min_deaths=0, max_events=1000):
    """Pure network phase (no qgis.core): finds the newest UCDP Candidate Events CSV on the downloads page (file names change every
    release, so none is hard-coded), downloads it once and caches it for 12 hours, then filters it. No key."""
    bbox_error = _validate_bbox(bbox)
    if bbox_error:
        return {"error": bbox_error}
    for label, value in (("start_date", start_date), ("end_date", end_date)):
        if value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
            return {"error": f"{label} must look like 2026-03-31."}
    try:
        min_deaths, max_events = int(min_deaths), int(max_events)
    except (TypeError, ValueError):
        return {"error": "min_deaths and max_events must be integers."}
    max_events = max(1, min(max_events, _UCDP_MAX_EVENTS))
    try:
        name = find_latest_candidate_file(_download_text(_UCDP_DOWNLOADS_PAGE, 30))
    except Exception as e:
        return {"error": f"Could not read the UCDP downloads page: {e}"}
    if not name:
        return {"error": "The UCDP downloads page no longer lists a Candidate Events CSV in the expected form; the tool needs updating."}
    path = _ucdp_cache_path(name)
    text = None
    if os.path.isfile(path) and time.time() - os.path.getmtime(path) < _UCDP_CACHE_HOURS * 3600:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    if text is None:
        try:
            text = _download_text(_UCDP_CANDIDATE_BASE + name, 120)
        except Exception as e:
            return {"error": f"UCDP Candidate Events download failed: {e}"}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    bbox_f = [float(v) for v in bbox] if bbox else None
    events, latest, total = parse_ucdp_candidate_csv(text, country, bbox_f, start_date, end_date, min_deaths)
    if not total:
        return {"error": f"The UCDP file {name} had no rows."}
    events.sort(key=lambda e: e["date"], reverse=True)
    truncated = len(events) > max_events
    return {"success": True, "dataset_file": name, "latest_event_date": latest, "rows_in_file": total, "events": events[:max_events],
            "matched": len(events), "truncated": truncated, "source": _UCDP_ATTRIBUTION}


def add_ucdp_conflict_events_layer_main_thread_phase(fetch_result, layer_name="UCDP Conflict Events"):
    if "error" in fetch_result:
        return fetch_result
    if not QGIS_AVAILABLE:
        return {"success": True, "event_count": len(fetch_result.get("events", []))}
    created = False
    layer = _find_layer_by_name(layer_name)
    if layer is None and not fetch_result.get("events"):
        return empty_fetch_result(layer_name, "UCDP events")
    if layer is None:
        layer = QgsVectorLayer(
            "Point?crs=EPSG:4326&field=event_id:string(40)&field=date:string(12)&field=country:string(80)&field=adm_1:string(120)"
            "&field=conflict_name:string(255)&field=category:string(40)&field=deaths_best:int&field=deaths_low:int&field=deaths_high:int"
            "&field=location_precision:int&field=clarity:string(20)", layer_name, "memory")
        if not layer.isValid():
            return {"error": f"Failed to create layer '{layer_name}'"}
        QgsProject.instance().addMapLayer(layer)
        created = True
    rows = [dict(e, __geom__=QgsGeometry.fromPointXY(QgsPointXY(e["lon"], e["lat"]))) for e in fetch_result.get("events", [])]
    try:
        added = _replace_point_features(layer, rows)
    except EditError as e:
        return {"error": f"Could not update layer '{layer_name}': {e} The previous contents were kept."}
    if created:
        _style_hazard(layer, "eonet")          # categorised by 'category': the three UCDP types of violence
    set_layer_confidence(layer, "OBSERVED", reason="UCDP candidate events: media-reported, preliminary, coded by researchers")
    _stamp_fetched_at(layer)
    more = f" {fetch_result['matched']} events matched; the newest {added} are shown." if fetch_result.get("truncated") else ""
    return {"success": True, "layer_name": layer_name, "event_count": added, "events": fetch_result.get("events", [])[:50],
            "dataset_file": fetch_result.get("dataset_file"), "latest_event_date": fetch_result.get("latest_event_date"),
            "source": fetch_result.get("source"),
            "message": f"'{layer_name}' now has {added} UCDP event(s).{more} The newest event in the dataset is dated "
                       f"{fetch_result.get('latest_event_date')} (candidate data is preliminary and lags real time by weeks: say so). "
                       "Death counts are UCDP's best, low and high estimates. Name the source in the reply."}


@register_tool(
    "fetch_ucdp_conflict_events",
    "Fetch organised-violence events (state-based conflict, non-state conflict, one-sided violence against civilians) from UCDP, the "
    "Uppsala Conflict Data Program's Candidate Events dataset, filtered by country name, bounding box and dates, and load them as a "
    "point layer with deaths (best, low, high estimates), conflict name, location precision and event clarity. Free, no API key; "
    "downloaded from ucdp.uu.se and cached for 12 hours. NOT live: candidate data is preliminary and lags real time by weeks, so "
    "always state the dataset's latest event date. IMPORTANT: bbox is [min_lon, min_lat, max_lon, max_lat]. Dates are 'YYYY-MM-DD'. "
    "Re-running REPLACES the layer's features. Cite UCDP (CC BY 4.0).",
    {
        "type": "object",
        "properties": {
            "country": {"type": "string", "description": "Country name or part of it, e.g. 'Yemen' or 'Sudan'. Omit for all countries."},
            "bbox": {"type": "array", "items": {"type": "number"}, "description": "Optional [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees."},
            "start_date": {"type": "string", "description": "Earliest event date, 'YYYY-MM-DD'."},
            "end_date": {"type": "string", "description": "Latest event date, 'YYYY-MM-DD'."},
            "min_deaths": {"type": "integer", "description": "Only events with at least this many deaths (UCDP best estimate). Defaults to 0."},
            "max_events": {"type": "integer", "description": "Most events to load (newest first). Defaults to 1000, at most 5000."},
            "layer_name": {"type": "string", "description": "Name for the layer. Defaults to 'UCDP Conflict Events'."},
        },
        "required": [],
    },
    keywords=[
        "conflict event", "armed conflict", "political violence", "organised violence", "organized violence", "ucdp",
        "fatalities", "battle", "killed in", "violence against civilians", "conflict", "war",
    ],
)
def fetch_ucdp_conflict_events(country=None, bbox=None, start_date=None, end_date=None, min_deaths=0, max_events=1000,
                               layer_name="UCDP Conflict Events"):
    return add_ucdp_conflict_events_layer_main_thread_phase(
        fetch_ucdp_conflict_events_network_phase(country, bbox, start_date, end_date, min_deaths, max_events), layer_name)
