"""identify_at_point helpers (PLAN-023 R9-5): the request check, the JSON-safe value and the result cap, pure Python (no QGIS, no numpy).

identify_at_point (identify_tool.py) does what the Identify tool does on the map, without a click: for a coordinate it lists the features of the vector layers under it and
the cell values of the raster layers. The reply holds at most MAX_FEATURES features in total and says when more matched; a request cannot raise the cap.
Known answers (the tests): 60 matching features across 2 layers give 50 kept and a truncated flag; a layer name the user gave that does not exist is an error."""
import math

MAX_FEATURES = 50
MAX_RADIUS_DEGREES = 1.0


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def check_request(x, y, radius=0, layers=None, max_features=MAX_FEATURES):
    """Error text for a request that cannot be run, else None. Pure."""
    if _number(x) is None or _number(y) is None:
        return "x and y must be numbers: the coordinate to look at."
    if _number(radius) is None or float(radius) < 0:
        return "radius must be a number, 0 or more (in the units of the coordinate's CRS)."
    if layers is not None and (not isinstance(layers, list) or not layers or any(not isinstance(n, str) or not n.strip() for n in layers)):
        return "layers must be a list of layer names (leave it out for all visible layers)."
    if _number(max_features) is None or float(max_features) != int(float(max_features)) or not 1 <= int(float(max_features)) <= MAX_FEATURES:
        return f"max_features must be a whole number from 1 to {MAX_FEATURES}."
    return None


def plain_value(value):
    """A JSON-safe copy of an attribute or cell value: None for NULL and NaN, numbers and text as they are, anything else (dates, binary) as text. `is_null` is whatever the
    caller's QGIS NULL test says; here None and NaN are the nulls. Pure."""
    if value is None:
        return None
    if isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    text = str(value)
    return None if text in ("NULL", "None", "") else text


def cap_features(groups, cap=MAX_FEATURES):
    """(kept groups, kept count, truncated): `groups` is a list of (layer name, list of rows); rows are kept in order until `cap` is reached across all layers; truncated is True when
    at least one more row existed. Layers whose rows were all cut are dropped. Pure."""
    kept, count, truncated = [], 0, False
    for name, rows in groups:
        room = cap - count
        if room <= 0:
            truncated = truncated or bool(rows)
            continue
        take = rows[:room]
        truncated = truncated or len(rows) > room
        if take:
            kept.append((name, take))
            count += len(take)
    return kept, count, truncated
