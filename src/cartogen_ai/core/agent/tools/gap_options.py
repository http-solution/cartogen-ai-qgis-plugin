"""Pure (Qt-free) checks for the gap-closing tools in elevation_tools.py and layout_chart_profile_tools.py, unit-tested offline."""
import re

from .layout_options import valid_item_id

CHART_TYPES = ("bar", "line", "pie")
RASTER_ELEVATION_MODES = ("surface", "fixed_range")
VECTOR_CLAMPING = ("absolute", "relative", "terrain")
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]{0,62}$")


def _num(name, value, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"{name} must be a number."
    if number != number or not low <= number <= high:
        return None, f"{name} must be between {low} and {high}."
    return number, None


def check_box(x_mm, y_mm, width_mm, height_mm):
    """(box dict, error) for a layout item rectangle in millimetres."""
    box = {}
    for key, value, low, high in (("x_mm", x_mm, 0, 2000), ("y_mm", y_mm, 0, 2000), ("width_mm", width_mm, 10, 1000), ("height_mm", height_mm, 10, 1000)):
        box[key], problem = _num(key, value, low, high)
        if problem:
            return None, problem
    return box, None


def check_chart(layout_name, chart_type, x_field, y_field, item_id=None):
    """Options for a chart layout item: type (bar, line, pie) and the two plain field names. A field name, not an expression."""
    kind = str(chart_type or "bar").strip().lower()
    if kind not in CHART_TYPES:
        return None, f"chart_type must be one of {', '.join(CHART_TYPES)}."
    for name, value in (("x_field", x_field), ("y_field", y_field)):
        if not isinstance(value, str) or not _FIELD.match(value.strip()):
            return None, f"{name} must be a plain field name."
    if item_id is not None and not valid_item_id(item_id):
        return None, "item_id is not a valid item id."
    return {"chart_type": kind, "x_field": x_field.strip(), "y_field": y_field.strip(), "item_id": item_id}, None


def check_profile_line(start_x, start_y, end_x, end_y):
    """((x1, y1), (x2, y2)) for the profile line in the project CRS, which must have two different ends."""
    values = []
    for name, value in (("start_x", start_x), ("start_y", start_y), ("end_x", end_x), ("end_y", end_y)):
        number, problem = _num(name, value, -1e9, 1e9)
        if problem:
            return None, problem
        values.append(number)
    if values[0] == values[2] and values[1] == values[3]:
        return None, "The profile line needs two different end points."
    return ((values[0], values[1]), (values[2], values[3])), None


def line_ends(points):
    """((x1, y1), (x2, y2)) from the first and last vertex of a line given as [(x, y), ...], or (None, problem). Pure.

    rc46 hand test I6: "draw an elevation profile along the road" had no way to reach the road's coordinates, so the model listed
    layout items in a loop and never added the profile. The tool now takes a line layer and uses the ends of its (selected or first) feature."""
    pts = [(float(p[0]), float(p[1])) for p in points or ()]
    if len(pts) < 2:
        return None, "The line needs at least two vertices."
    if pts[0] == pts[-1]:
        return None, "The line starts and ends at the same point (a closed ring); give start and end coordinates instead."
    return (pts[0], pts[-1]), None


def check_layer_elevation(enabled, mode, band, z_offset, z_scale, clamping, extrusion):
    """Normalised options for set_layer_elevation, or an error. Nothing is required: only what is given is changed."""
    out = {}
    if enabled is not None:
        out["enabled"] = bool(enabled)
    if mode is not None:
        out["mode"] = str(mode).strip().lower()
        if out["mode"] not in RASTER_ELEVATION_MODES:
            return None, f"mode must be one of {', '.join(RASTER_ELEVATION_MODES)}."
    if clamping is not None:
        out["clamping"] = str(clamping).strip().lower()
        if out["clamping"] not in VECTOR_CLAMPING:
            return None, f"clamping must be one of {', '.join(VECTOR_CLAMPING)}."
    for key, value, low, high in (("band", band, 1, 1000), ("z_offset", z_offset, -20000, 20000), ("z_scale", z_scale, -1000, 1000),
                                  ("extrusion", extrusion, 0, 20000)):
        if value is not None:
            out[key], problem = _num(key, value, low, high)
            if problem:
                return None, problem
    if not out:
        return None, "Nothing to change: give at least one of enabled, mode, band, z_offset, z_scale, clamping, extrusion."
    return out, None


def check_terrain(source, offset, scale):
    """(source, offset, scale, error) for set_project_terrain: 'flat' or 'dem'."""
    kind = str(source or "").strip().lower()
    if kind not in ("flat", "dem"):
        return None, "source must be 'flat' or 'dem'."
    out = {"source": kind}
    for key, value, low, high in (("offset", offset, -20000, 20000), ("scale", scale, -1000, 1000)):
        if value is not None:
            out[key], problem = _num(key, value, low, high)
            if problem:
                return None, problem
    return out, None
