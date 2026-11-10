"""Project-level coordinate and display settings helpers (PLAN-023 R10-5): the request checks and the word tables, pure Python (no QGIS, no numpy).

project_settings_tools.py applies them through QGIS; what can be checked offline is here. Four things, all stored in the PROJECT and none touching layer data:

* datum transformation: which of the coordinate operations PROJ offers between two CRSs the project uses (a different choice can move points by metres). Only an operation QGIS itself lists for
  that pair can be chosen; an arbitrary PROJ pipeline is never accepted.
* custom CRS: a PROJ string (+proj=...) or a WKT, validated by QGIS before it is used. It is NOT added to the user's CRS database (that is shared by every project); it is used for this project only.
* project ellipsoid, distance units and area units: what the project's measuring tools and the layout use.
* canvas decorations (title, copyright, scale bar, north arrow, grid): switched on or off and placed, with a text for the title and the copyright, through the project properties QGIS's decorations
  read. Decorations are drawn by the map canvas, which does not exist in CI, so these settings are hand-verified only, and QGIS reads them when the project is loaded.
Known answers (the tests): '+proj=utm +zone=36 +datum=WGS84' is a PROJ string, 'PROJCRS[...]' is a WKT, 'metres' and 'sq km' are understood, 'bottom_left' is placement 0 and 'top_center' is 4."""
import re

DISTANCE_UNITS = {"m": "Meters", "meter": "Meters", "meters": "Meters", "metre": "Meters", "metres": "Meters", "km": "Kilometers", "kilometer": "Kilometers", "kilometers": "Kilometers",
                  "kilometre": "Kilometers", "kilometres": "Kilometers", "ft": "Feet", "foot": "Feet", "feet": "Feet", "yd": "Yards", "yard": "Yards", "yards": "Yards", "mi": "Miles",
                  "mile": "Miles", "miles": "Miles", "nm": "NauticalMiles", "nautical miles": "NauticalMiles", "nautical mile": "NauticalMiles", "degrees": "Degrees", "degree": "Degrees"}
AREA_UNITS = {"m2": "SquareMeters", "sq m": "SquareMeters", "square meters": "SquareMeters", "square metres": "SquareMeters", "km2": "SquareKilometers", "sq km": "SquareKilometers",
              "square kilometers": "SquareKilometers", "square kilometres": "SquareKilometers", "ha": "Hectares", "hectare": "Hectares", "hectares": "Hectares", "acre": "Acres", "acres": "Acres",
              "sq ft": "SquareFeet", "square feet": "SquareFeet", "sq yd": "SquareYards", "square yards": "SquareYards", "sq mi": "SquareMiles", "square miles": "SquareMiles",
              "square degrees": "SquareDegrees"}
PLACEMENTS = {"bottom_left": 0, "top_left": 1, "top_right": 2, "bottom_right": 3, "top_center": 4, "bottom_center": 5}
DECORATIONS = {"title": "TitleLabel", "copyright": "CopyrightLabel", "scale_bar": "ScaleBar", "north_arrow": "NorthArrow", "grid": "Grid"}
TEXT_DECORATIONS = ("title", "copyright")
MAX_TEXT = 500
MAX_DEFINITION = 10000
_WKT_START = re.compile(r"^\s*(PROJCRS|GEOGCRS|GEODCRS|PROJCS|GEOGCS|COMPOUNDCRS|COMPD_CS|BOUNDCRS|VERTCRS)\s*\[", re.IGNORECASE)


def _unit(word, table):
    return table.get(" ".join(str(word or "").strip().lower().replace(".", "").split()))


def distance_unit_name(word):
    """The Qgis.DistanceUnit member name for a unit word ('metres' -> 'Meters'), or None. Pure."""
    return _unit(word, DISTANCE_UNITS)


def area_unit_name(word):
    """The Qgis.AreaUnit member name for a unit word ('sq km' -> 'SquareKilometers'), or None. Pure."""
    return _unit(word, AREA_UNITS)


def check_measurement(ellipsoid=None, distance_units=None, area_units=None):
    """Error text for a set_project_measurement request that cannot be run, else None. At least one of the three must be given. Pure."""
    if ellipsoid is None and distance_units is None and area_units is None:
        return "Give an ellipsoid, distance_units and/or area_units."
    if ellipsoid is not None and (not isinstance(ellipsoid, str) or not ellipsoid.strip() or len(ellipsoid) > 60):
        return "ellipsoid must be the name of an ellipsoid such as WGS84 or EPSG:7030 (or NONE for planimetric measurement)."
    if distance_units is not None and distance_unit_name(distance_units) is None:
        return f"distance_units '{distance_units}' is not one of: meters, kilometers, feet, yards, miles, nautical miles, degrees."
    if area_units is not None and area_unit_name(area_units) is None:
        return f"area_units '{area_units}' is not one of: square meters, square kilometers, hectares, acres, square feet, square yards, square miles, square degrees."
    return None


def definition_kind(text):
    """'proj' for a PROJ string (+proj=...), 'wkt' for a WKT CRS, None for anything else. Pure."""
    value = str(text or "").strip()
    if value.startswith("+") and re.search(r"(^|\s)\+proj=", value):
        return "proj"
    return "wkt" if _WKT_START.match(value) else None


def check_custom_crs(name, definition):
    """(kind, error): 'proj' or 'wkt' for a usable definition, else an error text. Pure."""
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        return None, "name must be text of 1 to 80 characters."
    if not isinstance(definition, str) or not definition.strip() or len(definition) > MAX_DEFINITION:
        return None, f"definition must be a PROJ string or a WKT of at most {MAX_DEFINITION} characters."
    kind = definition_kind(definition)
    if kind is None:
        return None, "definition must be a PROJ string starting with +proj= (for example '+proj=utm +zone=36 +datum=WGS84 +units=m') or a WKT starting PROJCRS[ or GEOGCRS[."
    return kind, None


def check_transform(source_crs, dest_crs, operation_id=None):
    """Error text for a set_project_transform_context request that cannot be run, else None. Without operation_id the tool only lists the operations. Pure."""
    for label, value in (("source_crs", source_crs), ("dest_crs", dest_crs)):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            return f"{label} must be a CRS such as EPSG:4326."
    if str(source_crs).strip().upper() == str(dest_crs).strip().upper():
        return "source_crs and dest_crs are the same, so no datum transformation applies."
    if operation_id is not None and (not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 2000):
        return "operation_id must be the id the listing gave (an authority code such as EPSG:1150, or the operation's PROJ text)."
    return None


def check_decoration(kind, enabled=None, placement=None, text=None):
    """Error text for a set_canvas_decoration request that cannot be run, else None. Pure."""
    if str(kind or "").strip().lower() not in DECORATIONS:
        return f"kind must be one of {', '.join(DECORATIONS)}."
    name = str(kind).strip().lower()
    if enabled is None and placement is None and text is None:
        return "Give enabled, placement and/or text."
    if enabled is not None and not isinstance(enabled, bool):
        return "enabled must be true or false."
    if placement is not None and str(placement).strip().lower() not in PLACEMENTS:
        return f"placement must be one of {', '.join(PLACEMENTS)}."
    if text is not None:
        if name not in TEXT_DECORATIONS:
            return f"text applies to {' and '.join(TEXT_DECORATIONS)} only, not to {name}."
        if not isinstance(text, str) or len(text) > MAX_TEXT:
            return f"text must be at most {MAX_TEXT} characters."
    return None
