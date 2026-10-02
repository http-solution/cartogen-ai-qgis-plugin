# -*- coding: utf-8 -*-
"""
Deterministic coordinate handling -- pure Python, no QGIS, so it is unit-testable.

Why this exists (rc7 interactive smoke test, 2026-09-30, findings F04 and F20): the request point
EPSG:3857 (4902068, 1799912) is lon 44.036026, lat 15.958454, but the analysis origin was placed
at lat 15.970136, about 1.3 km north, and every later result was anchored there. add_point_layer
only accepted lon/lat and there was no transform tool, so the model converted the projected
numbers by hand and got the latitude wrong -- twice, silently. Coordinate conversion belongs in
code, where it is exact; the model only has to say which CRS the numbers are in.

The QGIS-dependent part (building a QgsCoordinateTransform) stays in the tool; it passes a
`transform(x, y) -> (lon, lat)` callable in, which keeps this module free of QGIS imports.
"""

import re

_GEOGRAPHIC_ALIASES = {"EPSG:4326", "4326", "WGS84", "WGS 84", "CRS:84", "CRS84", "OGC:CRS84"}


def normalize_crs(crs):
    """Canonical text for a CRS the model or user typed, or None if none was given.

    "3857" -> "EPSG:3857"; every common spelling of WGS84 geographic -> "EPSG:4326". Anything
    else (a PROJ string, "EPSG:32636") is passed through for QGIS to judge -- this module does not
    pretend to know every CRS."""
    if crs is None:
        return None
    text = str(crs).strip()
    if not text:
        return None
    upper = text.upper()
    if upper in _GEOGRAPHIC_ALIASES:
        return "EPSG:4326"
    if text.isdigit():
        return f"EPSG:{text}"
    if upper.startswith("EPSG:"):
        return "EPSG:" + upper.split(":", 1)[1].strip()
    return text


def is_geographic(normalized_crs):
    return normalized_crs is None or normalized_crs == "EPSG:4326"


def _in_degree_range(lon, lat):
    return -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0


def _as_float(value, label):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} is missing or not a number ({value!r}).")


def resolve_lon_lat(point, crs=None, transform=None):
    """(lon, lat) in WGS84 for one point dict. Raises ValueError with a message the model can act on.

    * No `crs` (or EPSG:4326): the point must already be degrees. Values that cannot be degrees are
      refused -- silently accepting them, or asking the model to convert, is exactly how the
      1.3 km error happened.
    * A projected `crs`: the easting/northing are read from `x`/`y` (or, since models put them
      there, from `lon`/`lat`) and converted by `transform(x, y) -> (lon, lat)`.
    """
    src = normalize_crs(crs)
    if is_geographic(src):
        raw_lon = point.get("lon", point.get("x"))
        raw_lat = point.get("lat", point.get("y"))
        if raw_lon is None or raw_lat is None:
            raise ValueError("point needs lon and lat (or x and y).")
        lon = _as_float(raw_lon, "lon")
        lat = _as_float(raw_lat, "lat")
        if not _in_degree_range(lon, lat):
            raise ValueError(
                f"({lon}, {lat}) cannot be degrees -- these look like projected coordinates. "
                "Pass them unchanged together with their `crs` (for example \"EPSG:3857\"); "
                "do not convert them yourself."
            )
        return lon, lat

    raw_x = point.get("x", point.get("lon"))
    raw_y = point.get("y", point.get("lat"))
    if raw_x is None or raw_y is None:
        raise ValueError("point needs x and y (easting and northing) when a projected crs is given.")
    if transform is None:
        raise ValueError(f"cannot transform from {src}: no coordinate transform is available.")
    x = _as_float(raw_x, "x")
    y = _as_float(raw_y, "y")
    lon, lat = transform(x, y)
    if not _in_degree_range(lon, lat):
        raise ValueError(f"({x}, {y}) in {src} does not transform to a valid longitude/latitude ({lon}, {lat}).")
    return float(lon), float(lat)


def crs_decision(crs, stated_by_user, project_crs):
    """Whether a projected CRS the model passed may be used as-is (rc11 smoke test, F20 step C).

    With the project CRS set to EPSG:4326 and the request "Add a point at 4902068.0, 1799912.0" (no CRS), the model chose
    EPSG:3857 on its own and the point was placed with no question. A guess that happens to land right is still a guess:
    other projected systems give numbers of the same size. Returns:
      * None                      -- proceed (the user named the CRS, or it is geographic: out-of-range degrees are
                                     refused later by resolve_lon_lat);
      * ("assumed", normalized)   -- an unstated CRS equal to the project CRS: proceed and say it was assumed;
      * ("ask", normalized)       -- an unstated CRS that is NOT the project CRS: do not place anything, ask the user.
    The model reports `stated_by_user` itself, so this guards against accidents, not against a model that misreports."""
    src = normalize_crs(crs)
    if stated_by_user or is_geographic(src):
        return None
    project = normalize_crs(project_crs)
    if project and src == project:
        return ("assumed", src)
    return ("ask", src)


def interpret_request_pair(pair, project_crs_is_geographic):
    """How to read an "X, Y" pair typed into a request (F20).

    Returns ("project_crs", x, y) when the numbers are plausible in the project's CRS, or None when
    they are not -- or cannot be told apart from degrees -- so the caller falls back to something
    safe instead of transforming garbage:
      * geographic project: the pair must be a valid lon/lat;
      * projected project: degree-sized numbers (|x|<=180 and |y|<=90) are ambiguous -- read as
        metres they land near (0, 0), read as degrees the lon/lat order is unknown.
    """
    x, y = pair
    if project_crs_is_geographic:
        return ("project_crs", x, y) if _in_degree_range(x, y) else None
    if _in_degree_range(x, y):
        return None
    return ("project_crs", x, y)


# Two numbers that read as one coordinate: decimal degrees with 3+ decimals, or 6-8 digit projected
# values. Deliberately narrow (ordinary counts, years, prices and phone numbers must pass).
_DEGREE_PAIR = re.compile(r"(?<![\d.])-?\d{1,3}\.\d{3,}(?:\s*[,;/]\s*|\s+)-?\d{1,3}\.\d{3,}(?!\d)")
_PROJECTED_PAIR = re.compile(r"(?<![\d.,])-?\d{6,8}(?:\.\d+)?(?:\s*[,;/]\s*|\s+)-?\d{6,8}(?:\.\d+)?(?![\d.,])")


def contains_coordinate_pair(text):
    """True if `text` appears to hold a coordinate pair. Used to keep coordinates out of persistent
    memory notes: they are stored with the project, fed back into later prompts, and (rc7 smoke test,
    F23) were the wrong ones."""
    if not text:
        return False
    text = str(text)
    return bool(_DEGREE_PAIR.search(text) or _PROJECTED_PAIR.search(text))
