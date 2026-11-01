"""Where fetched data came from (PLAN-044, roadmap step C): source name and URL, licence, retrieval date and coverage, kept on the result,
on the layer and in the provenance sidecar and report, so a map made from fetched data can be cited and its licence honoured.

Pure except `tag_layer`, which writes one layer custom property and must run on the main thread. Honest limits, stated here and in the data:
  * The licence text comes from the table below, written by hand from each service's published terms. It is NOT read from the service on
    each call, so every record says `licence_checked: false`. Where the plugin does not know a single licence (HDX: it differs per dataset)
    the record says so instead of guessing one.
  * Coverage is what the call asked for (country code, admin level, box, layer extent), not what the service returned.
  * A data set that is shown to the user before a large download is a separate, later slice; nothing here changes download behaviour."""
import json
import time

from ..logger import log_event

PROPERTY_KEY = "cartogen/sources"
MAX_DEPTH = 4                            # how far back through lineage inputs to collect sources
_PER_DATASET = "differs per dataset: see the HDX page of the dataset used"

# tool name -> what the plugin knows about the service behind it. Edit with the service's published terms in hand.
SOURCES: dict[str, dict[str, str]] = {
    "fetch_geoboundaries": {"name": "geoBoundaries (gbOpen)", "url": "https://www.geoboundaries.org", "licence": "CC BY 4.0 (geoBoundaries gbOpen)",
                            "attribution": "geoBoundaries, William & Mary geoLab"},
    "fetch_hdx_admin_boundaries": {"name": "Humanitarian Data Exchange (HDX) administrative boundaries", "url": "https://data.humdata.org",
                                   "licence": _PER_DATASET, "attribution": "Humanitarian Data Exchange, UN OCHA, and the dataset's contributor"},
    "fetch_building_footprints": {"name": "Microsoft Global ML Building Footprints", "url": "https://github.com/microsoft/GlobalMLBuildingFootprints",
                                  "licence": "CDLA Permissive 2.0", "attribution": "Microsoft Global ML Building Footprints"},
    "fetch_worldpop_population": {"name": "WorldPop population rasters", "url": "https://www.worldpop.org", "licence": "CC BY 4.0 (WorldPop)",
                                  "attribution": "WorldPop, University of Southampton"},
    "ingest_osm_features": {"name": "OpenStreetMap, through the Overpass API", "url": "https://www.openstreetmap.org/copyright",
                            "licence": "ODbL 1.0", "attribution": "© OpenStreetMap contributors"},
    "fetch_nasa_active_fires": {"name": "NASA FIRMS active fire detections", "url": "https://firms.modaps.eosdis.nasa.gov",
                                "licence": "NASA open data policy (see the FIRMS terms)", "attribution": "NASA FIRMS (LANCE/ESDIS)"},
    "fetch_nasa_eonet_events": {"name": "NASA EONET natural events", "url": "https://eonet.gsfc.nasa.gov",
                                "licence": "NASA open data policy (see the EONET terms)", "attribution": "NASA EONET"},
    "fetch_gdacs_disaster_alerts": {"name": "GDACS disaster alerts", "url": "https://www.gdacs.org", "licence": "see the GDACS terms of use",
                                    "attribution": "Global Disaster Alert and Coordination System (GDACS)"},
    "fetch_usgs_earthquakes": {"name": "USGS Earthquake Hazards Program", "url": "https://earthquake.usgs.gov", "licence": "public domain (US government work)",
                               "attribution": "U.S. Geological Survey"},
    "fetch_ucdp_conflict_events": {"name": "UCDP Candidate Events Dataset", "url": "https://ucdp.uu.se", "licence": "CC BY 4.0",
                                   "attribution": "Uppsala Conflict Data Program (UCDP)"},
}


def source_tools():
    """Names of the tools whose results carry a source record. Pure."""
    return frozenset(SOURCES)


def _box(value):
    if isinstance(value, (list, tuple)) and len(value) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
        return "box " + ", ".join(f"{v:.4g}" for v in value)
    return None


def coverage_for(arguments, result):
    """A short, honest description of the area/period the call asked for, else None. Pure."""
    arguments = arguments if isinstance(arguments, dict) else {}
    result = result if isinstance(result, dict) else {}
    parts = []
    for key in ("iso3", "country", "country_name"):
        value = arguments.get(key) or result.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
            break
    level = arguments.get("admin_level")
    if isinstance(level, str) and level.strip():
        parts.append(level.strip())
    extent = arguments.get("extent_layer")
    if isinstance(extent, str) and extent.strip():
        parts.append(f"extent of layer '{extent.strip()}'")
    box = _box(arguments.get("bbox")) or _box(result.get("bbox"))
    if box:
        parts.append(box)
    for key, label in (("days", "last {} days"), ("year", "year {}"), ("start_date", "from {}"), ("end_date", "to {}")):
        value = arguments.get(key) or result.get(key)
        if value not in (None, ""):
            parts.append(label.format(value))
    return "; ".join(parts) or None


def build(tool, arguments, result, now=None):
    """The source record for a successful fetch result, else None. Pure."""
    spec = SOURCES.get(tool)
    if spec is None or not isinstance(result, dict) or "error" in result or result.get("success") is False:
        return None
    return {"tool": tool, **spec, "retrieved_at": now or time.strftime("%Y-%m-%d", time.gmtime()), "coverage": coverage_for(arguments, result),
            "licence_checked": False}


def attach(tool, arguments, result):
    """Puts the record in the result as `data_source` (not `source`: several results already use that key) and returns the result. Never raises."""
    try:
        record = build(tool, arguments, result)
        if record is not None:
            result["data_source"] = record
    except Exception as e:
        log_event("swallowed_exception", tag="Agent", tool="source_record", error_class=type(e).__name__, error=True)
    return result


def parse(raw):
    """The list stored in the layer property, tolerant of anything unreadable. Pure."""
    try:
        data = json.loads(raw) if isinstance(raw, str) and raw.strip() else []
    except ValueError:
        return []
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def merge(existing, new):
    """Existing records plus `new`, one per (tool, coverage) so a refetch replaces its own older record. Pure."""
    keyed = {(r.get("tool"), r.get("coverage")): r for r in existing}
    keyed[(new.get("tool"), new.get("coverage"))] = new
    return list(keyed.values())


def tag_layer(layer, record):
    """Stores `record` in the layer's custom property. MAIN THREAD ONLY. Returns True when written; never raises."""
    try:
        if layer is None or not isinstance(record, dict):
            return False
        layer.setCustomProperty(PROPERTY_KEY, json.dumps(merge(parse(layer.customProperty(PROPERTY_KEY, "[]")), record)))
        return True
    except Exception:
        return False


def collect(layer, lookup=None, _depth=0, _seen=None):
    """Every source record behind a layer: its own, plus those of the layers it was made from (found through lineage `sources` names with
    `lookup(name) -> layer or None`). Deduplicated; bounded by MAX_DEPTH and cycle-safe. Pure given a duck-typed layer."""
    _seen = _seen if _seen is not None else set()
    if layer is None or id(layer) in _seen or _depth > MAX_DEPTH:
        return []
    _seen.add(id(layer))
    try:
        found = parse(layer.customProperty(PROPERTY_KEY, "[]"))
    except Exception:
        found = []
    if lookup is not None:
        try:
            from .lineage import get_layer_lineage
            names = [n for entry in get_layer_lineage(layer) for n in (entry.get("sources") or []) if isinstance(n, str)]
        except Exception:
            names = []
        for name in dict.fromkeys(names):
            found.extend(collect(lookup(name), lookup, _depth + 1, _seen))
    out, keys = [], set()
    for record in found:
        key = (record.get("tool"), record.get("coverage"), record.get("retrieved_at"))
        if key not in keys:
            keys.add(key)
            out.append(record)
    return out


def describe(record):
    """One line for a report. Pure."""
    bits = [record.get("name") or record.get("tool") or "unknown source", record.get("url"), f"licence: {record.get('licence') or 'unknown'}"]
    if not record.get("licence_checked"):
        bits[-1] += " (from the plugin's table, not checked against the source)"
    bits.append(f"retrieved {record.get('retrieved_at') or 'unknown date'}")
    if record.get("coverage"):
        bits.append(f"coverage: {record['coverage']}")
    if record.get("attribution"):
        bits.append(f"credit: {record['attribution']}")
    return " | ".join(str(b) for b in bits if b)
