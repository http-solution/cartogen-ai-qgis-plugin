"""
find_incident_reports: one search over a short list of named, reliable sources, with provenance on every record.

Why (owner request 2026-10-11, tracker 1.19): the general web search (`search_web`) returned nothing usable for "check the internet for
incidents": no date filter, no way to tell an agency report from a forum post. This tool does NOT search the open web. It asks a fixed list of
sources that publish structured, attributable data, in parallel, keeps only what matches the place and dates, and says for every record which
source it came from and how that source is rated. Sources that cannot be asked are listed with the reason instead of being silently skipped.

The source table below is the "reliable sources" decision, written down. Tier 1 = a UN or government agency, a scientific instrument network or
an academic conflict dataset with a published method. Nothing here is a news outlet or social media: the fact-checkers the owner listed
(Reuters, AFP, Full Fact) were checked on 2026-10-11 and none offers a feed a program may read (403, a JavaScript wall, 404), and social media
is out of scope (needs an official API and credentials per platform; posts would be unverified signals). ACLED needs a registered key and
terms; it belongs with the credentialed integrations (tracker HX4).

Every fetch is a network-phase function that touches no QGIS object (safe on a worker thread); the layer is built on the GUI thread in a second
phase, as the other hazard tools do. Verified against the live services from a development session on 2026-10-11/12; not verified in a running
QGIS session.
"""
import contextlib
import html
import re
import xml.etree.ElementTree as ElementTree  # nosec B405 -- DOCTYPE/ENTITY refused, size capped; no defusedxml in QGIS Python
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .registry import register_tool
from ._edit_session import EditError
from ...models.confidence import set_layer_confidence
from ._urllib_retry import urlopen_with_retry
from ...net import build_request as _net_build_request
from ...net import read_capped as _read_capped
from .hazard_monitoring_tools import (
    QGIS_AVAILABLE, _find_layer_by_name, _replace_point_features, _stamp_fetched_at, _style_hazard, _validate_bbox,
    fetch_gdacs_disaster_alerts_network_phase, fetch_nasa_eonet_events_network_phase,
)
from .event_data_tools import fetch_ucdp_conflict_events_network_phase, fetch_usgs_earthquakes_network_phase

if QGIS_AVAILABLE:
    from qgis.core import QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

RELIEFWEB_RSS = "https://reliefweb.int/disasters/rss.xml"

# id -> what the source is, how it is rated and what it can and cannot answer. Edit here to change the policy; the tool and its reply read it.
SOURCES = {
    "gdacs": {"name": "GDACS (UN / European Commission)", "tier": 1, "kind": "natural hazard alerts", "coverage": "global feed, filtered here by place",
              "mappable": True, "note": "Green/Orange/Red alert levels assigned by the GDACS system; the feed has no country query, so it is fetched whole and filtered locally."},
    "usgs": {"name": "USGS Earthquake Hazards Program", "tier": 1, "kind": "earthquakes", "coverage": "global",
             "mappable": True, "note": "Instrument-detected; some events are automatic and unreviewed."},
    "eonet": {"name": "NASA EONET", "tier": 1, "kind": "natural events (storms, fires, volcanoes, floods)", "coverage": "global",
              "mappable": True, "note": "Curated from agency sources; titles carry the place name, so place matching is by name."},
    "ucdp": {"name": "UCDP Candidate Events (Uppsala University)", "tier": 1, "kind": "organised violence", "coverage": "global, preliminary",
             "mappable": True, "note": "Researcher-coded from media reports; published monthly, so it lags by weeks. Not live."},
    "reliefweb": {"name": "ReliefWeb disasters (UN OCHA)", "tier": 1, "kind": "declared disasters", "coverage": "global, no coordinates",
                  "mappable": False, "note": "Disasters declared on ReliefWeb with the affected country and a link; no map position, so these are listed, not mapped."},
}

# Sources the owner named that cannot be asked, with the reason. Shown in every reply so an empty result is not read as "nothing happened".
NOT_SEARCHED = {
    "Reuters Fact Check": "no machine-readable feed (the site answers with a login / JavaScript wall)",
    "AFP Fact Check": "the site refuses automated requests (HTTP 403)",
    "Full Fact": "a fact-checker, not an incident feed: ask search_fact_checks, which reads its published feed",
    "Liveuamap": "map site; machine access is a paid API",
    "ACLED": "needs a registered access key and agreement to its terms (planned with the credentialed integrations)",
    "Social media": "out of scope: needs an official API and credentials per platform, and posts are unverified signals",
}

DEFAULT_SOURCES = ("gdacs", "usgs", "eonet", "ucdp", "reliefweb")
MAX_REPORTS = 500
_MAX_FEED_CHARS = 3_000_000
_PER_SOURCE_TIMEOUT_S = 90


# ------------------------------------------------------------------------------------------------------------------ pure helpers --

def _date10(value):
    """'YYYY-MM-DD' from the many date shapes the sources use, '' when there is none."""
    text = str(value or "").strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else ""


def _record(source, rid, kind, title, date, lat=None, lon=None, url="", detail="", country="", severity=""):
    meta = SOURCES[source]
    return {"source": source, "source_name": meta["name"], "tier": meta["tier"], "id": str(rid), "kind": kind, "title": title or "",
            "date": _date10(date), "lat": lat, "lon": lon, "url": url or "", "detail": detail or "", "country": country or "",
            "severity": severity or ""}


def from_gdacs(result):
    return [_record("gdacs", a["unit"], str(a.get("event_type") or "hazard"), a.get("name") or a.get("description", ""),
                    a.get("from_date"), a["lat"], a["lon"], "", a.get("description", ""), a.get("country", ""), a.get("alert_level", ""))
            for a in result.get("alerts", [])]


def from_usgs(result):
    return [_record("usgs", e["event_id"], "earthquake", e.get("title", ""), e.get("time"), e["lat"], e["lon"], e.get("link", ""),
                    f"magnitude {e.get('magnitude')}, depth {e.get('depth_km')} km", "", e.get("category", ""))
            for e in result.get("events", [])]


def from_eonet(result):
    return [_record("eonet", e.get("unit"), e.get("category", "natural event"), e.get("title", ""), e.get("date"), e["lat"], e["lon"],
                    e.get("link", ""), "", "", "closed" if e.get("closed") else "open")
            for e in result.get("events", [])]


def from_ucdp(result):
    return [_record("ucdp", e["event_id"], e.get("category", "organised violence"), e.get("conflict_name", ""), e.get("date"), e["lat"], e["lon"],
                    "https://ucdp.uu.se/downloads/", f"deaths best {e.get('deaths_best')} (low {e.get('deaths_low')}, high {e.get('deaths_high')}), "
                    f"{e.get('adm_1', '')}", e.get("country", ""), e.get("category", ""))
            for e in result.get("events", [])]


def parse_reliefweb_rss(xml_text, country=None, since=None):
    """Pure: ReliefWeb disasters RSS -> records (no coordinates), optionally only those whose affected country contains `country` and
    whose date is on or after `since` ('YYYY-MM-DD')."""
    out = []
    needle = (country or "").strip().lower()
    # The standard library parser expands entity declarations (the "billion laughs" attack). A feed has no reason to declare any, so a
    # document that does is refused before parsing, and the text is capped.
    if len(xml_text) > _MAX_FEED_CHARS or "<!doctype" in xml_text.lower() or "<!entity" in xml_text.lower():
        raise ValueError("the feed was too large or declared entities, so it was not parsed")
    root = ElementTree.fromstring(xml_text)  # noqa: S314  # nosec B314 -- DOCTYPE / ENTITY refused and size capped above, so no entity expansion or external reference can occur
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = html.unescape(item.findtext("description") or "")
        m = re.search(r"Affected country:\s*([^<\n]+)", description)
        affected = m.group(1).strip() if m else ""
        glide = re.search(r"Glide:\s*([^<\s]+)", description)
        date = ""
        with contextlib.suppress(Exception):
            date = parsedate_to_datetime(item.findtext("pubDate")).strftime("%Y-%m-%d")
        if needle and needle not in (affected + " " + title).lower():
            continue
        if since and date and date < since:
            continue
        out.append(_record("reliefweb", glide.group(1) if glide else link, "declared disaster", title, date, None, None, link,
                           re.sub(r"<[^>]+>", " ", description).strip()[:300], affected))
    return out


def filter_records(records, country=None, bbox=None, since=None, require_name_match=False):
    """Keep records on or after `since`; inside `bbox` when they have a position; and, for sources that cannot be filtered by place on the
    server, whose title / country / detail mention `country`."""
    needle = (country or "").strip().lower()
    out = []
    for r in records:
        if since and r["date"] and r["date"] < since:
            continue
        if bbox and r["lat"] is not None and not (bbox[0] <= r["lon"] <= bbox[2] and bbox[1] <= r["lat"] <= bbox[3]):
            continue
        if needle and require_name_match and not (r["lat"] is not None and bbox):
            hay = f"{r['title']} {r['country']} {r['detail']}".lower()
            if needle not in hay:
                continue
        out.append(r)
    return out


def merge_records(groups):
    """Newest first; one record per (source, id)."""
    seen, merged = set(), []
    for rec in (r for g in groups for r in g):
        key = (rec["source"], rec["id"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(rec)
    merged.sort(key=lambda r: (r["date"], r["tier"] * -1), reverse=True)
    return merged


def source_table():
    return [{"id": k, **{f: v[f] for f in ("name", "tier", "kind", "coverage", "mappable", "note")}} for k, v in SOURCES.items()]


# --------------------------------------------------------------------------------------------------------------- network phase --

def _fetch_reliefweb(country, since):
    req = _net_build_request(RELIEFWEB_RSS, headers={"User-Agent": "QGIS-AI-Assistant"})
    with urlopen_with_retry(req, timeout=30) as response:
        text = _read_capped(response).decode("utf-8", errors="replace")
    return {"success": True, "records": parse_reliefweb_rss(text, country, since)}


def _ask(source, country, bbox, days, since):
    """(records or None, error text or None) for one source. Never raises."""
    try:
        if source == "gdacs":
            res = fetch_gdacs_disaster_alerts_network_phase(bbox, "Green", country)
            return (from_gdacs(res), None) if "error" not in res else (None, res["error"])
        if source == "usgs":
            res = fetch_usgs_earthquakes_network_phase(bbox, min(max(days, 1), 365), 4.0, 2000)
            return (filter_records(from_usgs(res), country, bbox, since, require_name_match=True), None) if "error" not in res else (None, res["error"])
        if source == "eonet":
            res = fetch_nasa_eonet_events_network_phase(bbox, None, min(max(days, 1), 365), "all")
            return (filter_records(from_eonet(res), country, bbox, since, require_name_match=True), None) if "error" not in res else (None, res["error"])
        if source == "ucdp":
            res = fetch_ucdp_conflict_events_network_phase(country, bbox, since, None, 0, 1000)
            return (from_ucdp(res), None) if "error" not in res else (None, res["error"])
        if source == "reliefweb":
            return _fetch_reliefweb(country, since)["records"], None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    return None, "unknown source"


def find_incident_reports_network_phase(country=None, bbox=None, days=30, sources=None, max_reports=200):
    """Ask the chosen sources in parallel and return one merged, provenance-tagged list. No qgis.core access."""
    bbox_error = _validate_bbox(bbox)
    if bbox_error:
        return {"error": bbox_error}
    if not country and not bbox:
        return {"error": "Give a country (or place name) or a bounding box: asking every source for the whole world returns noise, not incidents."}
    try:
        days = int(days)
        max_reports = max(1, min(int(max_reports), MAX_REPORTS))
    except (TypeError, ValueError):
        return {"error": "days and max_reports must be whole numbers."}
    if days < 1 or days > 365:
        return {"error": "days must be between 1 and 365."}
    chosen = [s for s in (sources or DEFAULT_SOURCES) if s in SOURCES]
    if not chosen:
        return {"error": f"sources must be some of: {', '.join(SOURCES)}."}
    bbox_f = [float(v) for v in bbox] if bbox else None
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    results = {}
    with ThreadPoolExecutor(max_workers=len(chosen)) as pool:
        futures = {s: pool.submit(_ask, s, country, bbox_f, days, since) for s in chosen}
        for s, fut in futures.items():
            try:
                results[s] = fut.result(timeout=_PER_SOURCE_TIMEOUT_S)
            except Exception as e:
                results[s] = (None, f"timed out or failed: {type(e).__name__}")

    checked, failed, groups = [], [], []
    for s in chosen:
        records, error = results[s]
        if error:
            failed.append({"source": s, "name": SOURCES[s]["name"], "error": error})
        else:
            checked.append({"source": s, "name": SOURCES[s]["name"], "tier": SOURCES[s]["tier"], "records": len(records or [])})
            groups.append(records or [])
    merged = merge_records(groups)
    return {"success": True, "country": country, "bbox": bbox, "days": days, "since": since, "records": merged[:max_reports],
            "total_matched": len(merged), "truncated": len(merged) > max_reports, "sources_checked": checked, "sources_failed": failed,
            "not_searched": NOT_SEARCHED}


# ------------------------------------------------------------------------------------------------------------ main-thread phase --

WORDING_NOTE = ("Say 'reported by <source>', never 'verified'. A record's presence in USGS, GDACS, EONET, UCDP or ReliefWeb means that agency "
                "reported it; it does not mean this tool or the user's question about 'verified' incidents has been answered. Do not use "
                "'Verified' as a heading or 'verified by' for any record.")


def _reply_text(fetch_result, mapped, layer_name):
    checked = ", ".join(f"{c['name']} ({c['records']})" for c in fetch_result["sources_checked"]) or "none"
    failed = "; ".join(f"{f['name']}: {f['error'][:80]}" for f in fetch_result["sources_failed"])
    text = (f"{fetch_result['total_matched']} report(s) from the named sources since {fetch_result['since']}; {mapped} mapped on '{layer_name}'. "
            f"Sources answered: {checked}. ")
    if failed:
        text += f"Could NOT be reached: {failed}. "
    text += ("These are records from agencies, instruments and one academic dataset, each with its source and link; this tool did not verify them "
             "and did not search news outlets, fact-checkers or social media (see not_searched). If a source is missing from the answered list, "
             "an empty result for it does not mean nothing happened. UCDP data is preliminary and weeks old. Name the sources in the reply.")
    return text


def add_incident_reports_layer_main_thread_phase(fetch_result, layer_name="Incident reports"):
    if "error" in fetch_result:
        return fetch_result
    records = fetch_result.get("records", [])
    mappable = [r for r in records if r["lat"] is not None and r["lon"] is not None]
    unmapped = [r for r in records if r["lat"] is None or r["lon"] is None]
    base = {"success": True, "layer_name": layer_name, "total_matched": fetch_result["total_matched"], "truncated": fetch_result["truncated"],
            "sources_checked": fetch_result["sources_checked"], "sources_failed": fetch_result["sources_failed"],
            "not_searched": fetch_result["not_searched"], "since": fetch_result["since"],
            "reports": [{k: r[k] for k in ("source_name", "tier", "kind", "title", "date", "country", "url", "detail")} for r in records[:40]],
            "unmapped_reports": len(unmapped), "wording_note": WORDING_NOTE}
    if not QGIS_AVAILABLE:
        base["message"] = _reply_text(fetch_result, len(mappable), layer_name)
        return base
    created = False
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        layer = QgsVectorLayer(
            "Point?crs=EPSG:4326&field=source:string(60)&field=tier:int&field=category:string(60)&field=title:string(255)&field=date:string(12)"
            "&field=country:string(80)&field=severity:string(40)&field=detail:string(300)&field=url:string(500)&field=record_id:string(60)",
            layer_name, "memory")
        if not layer.isValid():
            return {"error": f"Failed to create layer '{layer_name}'"}
        QgsProject.instance().addMapLayer(layer)
        created = True
    rows = [{"__geom__": QgsGeometry.fromPointXY(QgsPointXY(r["lon"], r["lat"])), "source": r["source_name"], "tier": r["tier"],
             "category": r["kind"], "title": r["title"], "date": r["date"], "country": r["country"], "severity": r["severity"],
             "detail": r["detail"], "url": r["url"], "record_id": r["id"]} for r in mappable]
    try:
        added = _replace_point_features(layer, rows)
    except EditError as e:
        return {"error": f"Could not update layer '{layer_name}': {e} The previous contents were kept."}
    if created:
        _style_hazard(layer, "eonet")          # categorised by the 'category' field (the kind of report)
    set_layer_confidence(layer, "OBSERVED", reason="Records from named agencies, instruments and an academic dataset; not independently verified")
    _stamp_fetched_at(layer)
    base["mapped"] = added
    base["message"] = _reply_text(fetch_result, added, layer_name)
    return base


@register_tool(
    "find_incident_reports",
    "Find incident and hazard reports for a country / place and a time window from a FIXED list of reliable sources, with the source, its rating and a "
    "link on every record: GDACS (UN alerts), USGS (earthquakes), NASA EONET (storms, fires, volcanoes, floods), UCDP (armed conflict events; preliminary, "
    "weeks old) and ReliefWeb (declared disasters; listed, not mapped). Records with a position are loaded as a point layer. Use this INSTEAD of "
    "search_web for 'what incidents / disasters / conflict events happened in <place>' questions. It does not search news outlets, fact-checkers or "
    "social media, and the reply lists every source that could not be asked: always say which sources were checked and that an empty result is not proof "
    "nothing happened. Free, no keys. IMPORTANT: give a country (or place name) and/or bbox [min_lon, min_lat, max_lon, max_lat]; days is 1 to 365 "
    "(default 30). Re-running REPLACES the layer's features.",
    {
        "type": "object",
        "properties": {
            "country": {"type": "string", "description": "Country or place name, e.g. 'Yemen' or 'Sudan'. Matched by name against each source."},
            "bbox": {"type": "array", "items": {"type": "number"}, "description": "Optional [min_lon, min_lat, max_lon, max_lat] in WGS84 degrees."},
            "days": {"type": "integer", "description": "How many days back (1 to 365). Defaults to 30."},
            "sources": {"type": "array", "items": {"type": "string"}, "description": "Optional subset of: gdacs, usgs, eonet, ucdp, reliefweb. Default: all."},
            "max_reports": {"type": "integer", "description": "Most records to return (newest first). Defaults to 200, at most 500."},
            "layer_name": {"type": "string", "description": "Name for the layer. Defaults to 'Incident reports'."},
        },
        "required": [],
    },
)
def find_incident_reports(country=None, bbox=None, days=30, sources=None, max_reports=200, layer_name="Incident reports"):
    return add_incident_reports_layer_main_thread_phase(
        find_incident_reports_network_phase(country, bbox, days, sources, max_reports), layer_name)
