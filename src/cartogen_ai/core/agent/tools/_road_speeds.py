"""One table of assumed road speeds by road class, shared by every tool that needs a speed for a road that has none (D of the HU-3b decision, 2026-11-23).

Pure Python, no QGIS. Before this module two tools carried different tables: estimate_road_speeds (primary 70, secondary 60, tertiary 50, residential 40) and
build_composite_impedance_field (primary 60, secondary 50, tertiary 40, residential 30). They now read this one, so the same road class gets the same assumed
speed whichever tool asks. The numbers are an ASSUMPTION from public routing profiles, not measured on any network, and have not been checked against a known
journey (docs/DECISION_ANALYSIS_2026-11-23_HU-3b_road_speeds.md). The optional country scaling covers 15 countries only; Yemen is not among them."""

# BUG-2026-09-25-3: measured on the real Jordan Geofabrik extract, maxspeed is set on only 0.9%
# of roads (1,504 of 161,041) -- with strategy='fastest', every other road falls back to the flat
# DEFAULT_SPEED parameter, so a road network with almost no real speed data still produces a
# uniform-speed travel time, not a meaningfully differentiated one. The road CLASS is present far
# more often (fclass on a Geofabrik extract; highway on an OSM/Overpass ingest -- same OSM
# vocabulary, since Geofabrik's fclass mirrors the highway tag it was derived from). This table is
# an assumption, not measured data -- common values from public routing profiles (OSRM/GraphHopper
# car profiles), not this project's own measurement of Jordan or any other specific road network.
# Per docs/BUG_TRACKER.md's own framing, this is a judgement call that changes results and ideally
# wants checking against a known real journey. It first shipped only as the opt-in estimate_road_speeds tool. Since 2026-11-23 (owner's choice
# B of docs/DECISION_ANALYSIS_2026-11-23_HU-3b_road_speeds.md) calculate_service_area, travel_time_matrix and optimize_delivery_route also use it
# automatically, on an IN-MEMORY copy and only for strategy='fastest' with no usable speed_field; every such result states the assumption.
# analyze_critical_links does not (it keeps the flat default_speed).
ASSUMED_SPEED_BY_ROAD_CLASS_KMH = {
    "motorway": 100, "motorway_link": 80,
    "trunk": 80, "trunk_link": 60,
    "primary": 70, "primary_link": 50,
    "secondary": 60, "secondary_link": 45,
    "tertiary": 50, "tertiary_link": 40,
    "unclassified": 30,
    "residential": 40, "living_street": 20,
    "service": 20, "track": 20,
    "pedestrian": 5, "footway": 5, "path": 5, "cycleway": 15, "steps": 3,
}
ROAD_CLASS_FIELD_CANDIDATES = ("fclass", "highway")

# Optional per-country override, addressing this table's own standing limitation (a single
# global set of numbers, not this network's real legal limits) without needing a live lookup.
# Modeled on the same three-tier (urban/rural/motorway) legal-default-speed convention real
# open-source routing infrastructure already uses for exactly this gap -- see
# https://github.com/westnordost/osm-legal-default-speeds (BSD-3-Clause code, its underlying
# data is CC BY-SA 2.0 from the OpenStreetMap wiki's "Default speed limits" page) and the
# Valhalla-consumed https://github.com/OpenStreetMapSpeeds/schema dataset. Values below are a
# curated subset (not a full port of either project's much larger tag-filter-matching data
# model, which needs per-subdivision OSM tag evaluation this project has no use for at its
# current scope) verified via live web search 2026-09-28 against public references (Wikipedia's
# "Speed limits by country" and per-country articles, TyreMap, AARoads Wiki) -- national legal
# defaults, honestly approximate: many countries' real limits vary by state/province/specific
# road (the US and Australia especially), and this table cannot and does not capture that.
# tags: (urban, rural, motorway) in km/h, applied only when the caller passes a matching
# ISO 3166-1 alpha-2 `country` code -- omitting it keeps today's behavior exactly as before.
COUNTRY_SPEED_TIERS_KMH = {
    "JO": (40, 80, 110),   # Jordan
    "SA": (50, 80, 120),   # Saudi Arabia
    "AE": (60, 100, 120),  # United Arab Emirates
    "EG": (60, 100, 100),  # Egypt
    "DE": (50, 100, 130),  # Germany (130 is the advisory Autobahn limit, not a hard cap)
    "AT": (50, 100, 130),  # Austria
    "CZ": (50, 90, 130),   # Czechia
    "HU": (50, 90, 130),   # Hungary
    "FR": (50, 80, 130),   # France
    "ES": (50, 90, 120),   # Spain
    "GB": (48, 97, 113),   # United Kingdom (30/60/70 mph)
    "CA": (50, 80, 110),   # Canada
    "US": (40, 105, 113),  # United States (national default; varies heavily by state)
    "AU": (60, 100, 110),  # Australia (national default; varies by state/territory)
    "CN": (50, 80, 120),   # China
}
# Road-class tiers this table's three values map onto, and the fraction applied to a "_link"
# variant of a tiered class -- same reduction shape (~75-80%) the existing global table above
# already uses between e.g. motorway (100) and motorway_link (80).
_COUNTRY_TIER_ROAD_CLASSES = {
    "motorway": ("motorway", "trunk"),
    "rural": ("primary", "secondary", "tertiary", "unclassified"),
    "urban": ("residential", "living_street", "service", "track"),
}
_COUNTRY_LINK_FACTOR = 0.75


def country_speed_overrides(country):
    """Expand COUNTRY_SPEED_TIERS_KMH's 3 tier values into the same per-road-class shape
    ASSUMED_SPEED_BY_ROAD_CLASS_KMH uses, for one country code. Returns {} for an unknown/
    omitted country -- callers then simply fall back to the existing global table untouched."""
    tiers = COUNTRY_SPEED_TIERS_KMH.get((country or "").strip().upper())
    if not tiers:
        return {}
    urban_kmh, rural_kmh, motorway_kmh = tiers
    tier_value = {"motorway": motorway_kmh, "rural": rural_kmh, "urban": urban_kmh}
    overrides = {}
    for tier, classes in _COUNTRY_TIER_ROAD_CLASSES.items():
        value = tier_value[tier]
        for road_class in classes:
            overrides[road_class] = value
            overrides[f"{road_class}_link"] = round(value * _COUNTRY_LINK_FACTOR)
    return overrides


def speed_table(country=None):
    """(table, country_used) for an optional ISO 3166-1 alpha-2 code: the global table with that country's urban/rural/motorway overrides on top.
    `country_used` is the upper-cased code when it was recognised, else None (the generic table is used). Pure."""
    code = (country or "").strip().upper()
    overrides = country_speed_overrides(code)
    return {**ASSUMED_SPEED_BY_ROAD_CLASS_KMH, **overrides}, (code if overrides else None)


def road_class_field(field_names):
    """The first of 'fclass' (Geofabrik) or 'highway' (OSM/Overpass) present in `field_names`, else None. Pure."""
    names = list(field_names)
    return next((f for f in ROAD_CLASS_FIELD_CANDIDATES if f in names), None)


def speed_for_class(value, table, default_kmh=30.0):
    """(km/h, known): the table's speed for a road-class value (case and spaces ignored), else `default_kmh` with known False. Pure."""
    key = str(value or "").strip().lower()
    speed = table.get(key)
    return (float(speed), True) if speed is not None else (float(default_kmh), False)
