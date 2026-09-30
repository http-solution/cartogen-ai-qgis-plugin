# -*- coding: utf-8 -*-
"""Offer to download a request's base data once, locally, instead of fetching it live.

Why this exists (live-reported 2026-09-24/25, "Health facilities beyond one hour's travel"):
every run fetched roads and facilities live from the Overpass API. That server was failing more
than half the time that evening (measured: 5 of 12 spaced requests succeeded), each failure cost
one of the model's 20 tool calls, and the area the model asked for (1.5-2 km) was far too small
for a one-hour travel question anyway. A country extract from Geofabrik is one download (Jordan:
60 MB), has no rate limits, covers the whole area, and carries road class/speed/one-way
attributes the live query doesn't. So before such a request goes to the model, the user is asked
once whether to download local data; see chat_tab_widget.py's _ask_local_data_in_chat.

Deliberately Qt-free so it can be unit-tested without QGIS (same pattern as chat_formatting.py);
the QGIS side (downloading, extracting, loading layers) lives in local_data_loader.py.

Every source URL below was checked live on 2026-09-25 (HTTP 200, or the HDX API resolving the
dataset). HDX links are searches filled in with the country name, not guessed dataset ids:
Geofabrik only reports a 2-letter country code, and not every pattern holds everywhere (e.g.
OCHA's cod-ab-<iso3> admin boundaries exist for Pakistan but not for Jordan).
"""
import difflib
import re

GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1.json"

# Tools whose results are only meaningful on a routable line network.
ROAD_NETWORK_TOOLS = frozenset({
    "calculate_service_area", "travel_time_matrix", "optimize_delivery_route",
    "population_access_gap", "classify_facilities_by_access",
})

_HEALTH_WORDS = re.compile(r"\b(health|hospitals?|clinics?|medical|doctors?|facilit(y|ies))\b", re.I)
_ROAD_LAYER_WORDS = re.compile(r"road|street|highway|network|osm_roads|transport", re.I)
_POPULATION_WORDS = re.compile(r"\b(population|people|residents|inhabitants|households)\b", re.I)
_HEALTH_LAYER_WORDS = re.compile(r"health|hospital|clinic|medical|facilit", re.I)
# The user already said which way to go, so asking would just be an interruption.
_ONLINE_WORDS = re.compile(r"\b(online|overpass|live data|don'?t download)\b", re.I)

# A raw "X,Y" coordinate pair typed directly into a request (e.g. "... beyond one hour's
# travel 3999770.2,3743455.7"), the way this project's own starter prompts and every live
# report of this flow so far have written one. Requires a decimal point on BOTH numbers --
# tight on purpose: a thousands separator ("1,000 meters"), a plain list, or two nearby
# small integers must never be mistaken for a coordinate pair. Live-reported, 2026-09-28:
# _maybe_ask_local_data (chat_tab_widget.py) used the QGIS CANVAS'S current view centre to
# pick which Geofabrik region to offer, not the location the request actually named -- if
# the canvas hadn't been panned there yet, the offer named the wrong country ("Israel and
# Palestine" for a Jordan coordinate) or, when the canvas had no meaningful extent at all,
# literally "(0.000, 0.000)". This regex is the fix's other half (see
# local_data_loader.query_point_wgs84): prefer the coordinate the request itself names,
# falling back to the canvas centre only when the request doesn't name one.
_COORDINATE_PAIR = re.compile(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")


def extract_coordinate_pair(text):
    """The first "X,Y" pair in `text` with a decimal point on both numbers, as
    (x, y) floats -- in whatever CRS the request's own numbers are in (the
    caller is responsible for knowing/assuming that; see
    local_data_loader.query_point_wgs84). None if no such pair is present."""
    m = _COORDINATE_PAIR.search(text or "")
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))

# Geofabrik "free" shapefile layers and the classes used for each theme.
# gis_osm_pois_a_free_1 matters: in the Jordan extract 99 of 201 hospitals are mapped as building
# outlines (pois_a), not points (pois); loading only the point file would silently lose half.
HEALTH_FCLASSES = ("hospital", "clinic", "doctors", "dentist")

SOURCES = {
    "roads": [
        {"name": "Geofabrik OpenStreetMap extracts", "auto": True,
         "what": "every road in the country/region, with road class, speed limit and one-way",
         "format": "Shapefile ZIP (also .osm.pbf)", "license": "ODbL",
         "url": "https://download.geofabrik.de/"},
        {"name": "HOT OSM exports on HDX", "what": "roads per country, updated regularly",
         "format": "GeoPackage / Shapefile", "license": "ODbL",
         "url": "https://data.humdata.org/search?q=hotosm%20{country}%20roads"},
        {"name": "HOT Export Tool", "what": "OSM data for an area you draw (free OSM login)",
         "format": "GeoPackage / Shapefile / others", "license": "ODbL",
         "url": "https://export.hotosm.org/"},
        {"name": "BBBike extracts", "what": "OSM data for a custom rectangle or polygon",
         "format": "Shapefile / GeoJSON / PBF", "license": "ODbL",
         "url": "https://extract.bbbike.org/"},
        {"name": "Overture Maps (transportation)", "what": "road network merged from OSM and other sources",
         "format": "GeoParquet", "license": "ODbL",
         "url": "https://docs.overturemaps.org/getting-data/"},
    ],
    "health_facilities": [
        {"name": "Geofabrik OpenStreetMap extracts", "auto": True,
         "what": "hospitals, clinics, doctors and dentists (points and building outlines)",
         "format": "Shapefile ZIP", "license": "ODbL",
         "url": "https://download.geofabrik.de/"},
        {"name": "HOT OSM exports on HDX", "what": "health facilities per country",
         "format": "GeoPackage / Shapefile / GeoJSON", "license": "ODbL",
         "url": "https://data.humdata.org/search?q=hotosm%20{country}%20health%20facilities"},
        {"name": "healthsites.io", "what": "curated global health-facility map (also mirrored on HDX)",
         "format": "Shapefile / GeoJSON / CSV", "license": "ODbL",
         "url": "https://healthsites.io/"},
    ],
    "population": [
        {"name": "WorldPop", "what": "gridded population counts (100 m), per country",
         "format": "GeoTIFF", "license": "CC BY 4.0",
         "url": "https://hub.worldpop.org/geodata/listing?id=29"},
        {"name": "GHSL (EU JRC)", "what": "global population and built-up grids",
         "format": "GeoTIFF", "license": "CC BY 4.0",
         "url": "https://human-settlement.emergency.copernicus.eu/download.php"},
    ],
    "boundaries": [
        {"name": "geoBoundaries", "what": "admin boundaries, levels 0-4",
         "format": "GeoJSON / Shapefile", "license": "CC BY 4.0",
         "url": "https://www.geoboundaries.org/"},
        {"name": "HDX (OCHA COD-AB where available)", "what": "official humanitarian admin boundaries",
         "format": "Shapefile / GeoPackage", "license": "varies (usually CC BY-IGO)",
         "url": "https://data.humdata.org/search?q={country}%20administrative%20boundaries"},
        {"name": "GADM", "what": "admin boundaries, all levels",
         "format": "GeoPackage / Shapefile", "license": "non-commercial only",
         "url": "https://gadm.org/download_country.html"},
    ],
    "buildings": [
        {"name": "Microsoft Global ML Building Footprints", "what": "building outlines from imagery",
         "format": "GeoJSON (per tile)", "license": "ODbL",
         "url": "https://github.com/microsoft/GlobalMLBuildingFootprints"},
        {"name": "Google Open Buildings", "what": "building outlines (Africa, Asia, Latin America)",
         "format": "CSV", "license": "CC BY 4.0 / ODbL",
         "url": "https://sites.research.google/gr/open-buildings/"},
    ],
    "elevation": [
        {"name": "Copernicus DEM GLO-30", "what": "30 m elevation, e.g. for walking-time slopes",
         "format": "GeoTIFF", "license": "free, with attribution",
         "url": "https://dataspace.copernicus.eu/explore-data/data-collections/"
                "copernicus-contributing-missions/collections-description/COP-DEM"},
    ],
}

THEME_LABELS = {
    "roads": "road network", "health_facilities": "health facilities", "population": "population",
    "boundaries": "admin boundaries", "buildings": "buildings", "elevation": "elevation",
}


def themes_needed(entry, query):
    """Base-data themes this request needs, most important first. [] when none apply."""
    if not entry:
        return []
    tools = set(entry.get("tools") or [])
    themes = []
    if tools & ROAD_NETWORK_TOOLS:
        themes.append("roads")
        if _HEALTH_WORDS.search(query or "") or _HEALTH_WORDS.search(entry.get("text") or ""):
            themes.append("health_facilities")
    # Only when the user asks about people: task 7.23 lists population_access_gap among its
    # suggested tools, but "health facilities beyond one hour's travel" doesn't need a population
    # grid, and asking for one would be noise.
    if "population_access_gap" in tools and _POPULATION_WORDS.search(query or ""):
        themes.append("population")
    return themes


def themes_missing(themes, layers):
    """The themes the open project doesn't already have a usable layer for.

    `layers` is [{"name": str, "geometry": "line"|"point"|"polygon"|None}, ...]. A road theme is
    only satisfied by a LINE layer: a road network loaded as points is exactly the failure this
    module exists to avoid (BUG-2026-09-24-3)."""
    missing = []
    for t in themes:
        if t == "roads":
            have = any(lyr.get("geometry") == "line" and _ROAD_LAYER_WORDS.search(lyr.get("name") or "")
                       for lyr in layers or [])
        elif t == "health_facilities":
            have = any(lyr.get("geometry") in ("point", "polygon")
                       and _HEALTH_LAYER_WORDS.search(lyr.get("name") or "") for lyr in layers or [])
        elif t == "population":
            have = any(lyr.get("geometry") == "raster"
                       and re.search(r"pop|worldpop|ghs", lyr.get("name") or "", re.I) for lyr in layers or [])
        else:
            have = False
        if not have:
            missing.append(t)
    return missing


def should_offer(entry, query, layers, declined=False):
    """The themes to ask about, or [] to not ask at all."""
    if declined or _ONLINE_WORDS.search(query or ""):
        return []
    return themes_missing(themes_needed(entry, query), layers)


def _source_line(src, country=None):
    # No country known yet (Geofabrik's index isn't cached): the search still works without it.
    url = src["url"].format(country=(country or "").replace(" ", "%20"))
    url = url.replace("%20%20", "%20").replace("q=%20", "q=")
    return "- **%s**: %s (%s, %s): %s" % (src["name"], src["what"], src["format"], src["license"], url)


def question_text(themes, country=None):
    """The chat message asking whether to download local data, listing where it can come from."""
    labels = [THEME_LABELS.get(t, t) for t in themes]
    auto = [t for t in themes if any(s.get("auto") for s in SOURCES.get(t, []))]
    lines = [
        "This request needs **%s**, and this project doesn't have %s yet." % (
            " and ".join(labels), "it" if len(labels) == 1 else "them"),
        "",
        "I can **download the data once** into the project and work from local files: better "
        "coverage, road types and speed limits, no dependence on the busy live OpenStreetMap "
        "server, and fewer API calls. Or I can **fetch it online** each time, as before.",
        "",
    ]
    if auto:
        lines.append("If you choose download, I'll get the OpenStreetMap extract for this area "
                     "from Geofabrik (%s), tell you its size first if it's large, save it in "
                     "the project's data folder and add the layers." % ", ".join(
                         THEME_LABELS[t] for t in auto))
        lines.append("")
    lines.append("Other sources with downloadable versions, if you'd rather load your own:")
    for t in themes:
        for src in SOURCES.get(t, []):
            if not src.get("auto"):
                lines.append(_source_line(src, country))
    lines.append("")
    lines.append("Reply **download** to get local data, or **online** to continue without it.")
    return "\n".join(lines)


def all_sources_markdown(country=None):
    """Every catalogued source, grouped by theme -- for the user guide and a 'where can I get
    data' answer."""
    out = []
    for theme, srcs in SOURCES.items():
        out.append("**%s**" % THEME_LABELS[theme].capitalize())
        out.extend(_source_line(s, country) for s in srcs)
        out.append("")
    return "\n".join(out).rstrip()


_DOWNLOAD_REPLIES = {"download", "local", "yes", "y", "ok", "okay", "sure", "download it",
                     "use local", "local data", "yes download"}
_ONLINE_REPLIES = {"online", "no", "n", "fetch online", "skip", "not now", "no thanks", "continue"}


_FUZZY_CANONICAL = (("download", "download"), ("online", "online"))
_FUZZY_MIN_RATIO = 0.8


def parse_reply(text):
    """'download', 'online', or None when the reply is something else (a new request).

    Live-reported, 2026-09-28: a single-letter typo ("dowmload") missed the exact-match
    sets below entirely, so the caller (chat_tab_widget.py's send_message) treated it as
    an unrelated new message and silently dropped the pending local-data question -- the
    ORIGINAL request it was about ("Health facilities beyond one hour's travel ...") was
    then lost too, and the conversation never recovered. A close-match check against just
    the two headline single-word replies (not the whole phrase sets -- "not now"/"decline"
    are deliberate alternate phrasings, not typos to correct) closes the actual gap:
    scoped to a single token (so a real new multi-word request never gets swallowed as an
    accidental "yes") and a ratio high enough that unrelated short words ("delete",
    "cancel", "decline") don't false-positive (checked: all score well under this cutoff)."""
    t = (text or "").strip().lower().rstrip("!.?")
    if t in _DOWNLOAD_REPLIES:
        return "download"
    if t in _ONLINE_REPLIES:
        return "online"
    if t and " " not in t:
        for canonical, choice in _FUZZY_CANONICAL:
            if difflib.SequenceMatcher(None, t, canonical).ratio() >= _FUZZY_MIN_RATIO:
                return choice
    return None


# ------------------------------------------------------------ region lookup --

def _in_ring(lon, lat, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _in_geometry(lon, lat, geom):
    if not geom:
        return False
    polys = geom["coordinates"] if geom.get("type") == "MultiPolygon" else [geom.get("coordinates") or []]
    for poly in polys:
        if poly and _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, h) for h in poly[1:]):
            return True
    return False


def _bbox_area(geom):
    xs, ys = [], []
    polys = geom["coordinates"] if geom.get("type") == "MultiPolygon" else [geom.get("coordinates") or []]
    for poly in polys:
        for x, y in (poly[0] if poly else []):
            xs.append(x)
            ys.append(y)
    return (max(xs) - min(xs)) * (max(ys) - min(ys)) if xs else float("inf")


def find_region(index, lon, lat):
    """The smallest Geofabrik region containing (lon, lat) that has a shapefile download.

    Smallest, because regions nest (asia > jordan; europe > germany > bayern) and a smaller
    extract is a smaller download. Returns {"id", "name", "shp_url", "iso2"} or None."""
    best = None
    for f in (index or {}).get("features", []):
        props = f.get("properties") or {}
        url = (props.get("urls") or {}).get("shp")
        geom = f.get("geometry")
        if not url or not _in_geometry(lon, lat, geom):
            continue
        area = _bbox_area(geom)
        if best is None or area < best[0]:
            best = (area, {"id": props.get("id"), "name": props.get("name"), "shp_url": url,
                           "iso2": (props.get("iso3166-1:alpha2") or [None])[0]})
    return best[1] if best else None
