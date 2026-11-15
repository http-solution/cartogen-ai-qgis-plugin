"""Pure (Qt-free) validation for the package G layout tools in layout_extra_tools.py, unit-tested offline."""
import re

from .layout_options import valid_item_id

MAX_GUIDES = 30
ATLAS_SCALING = ("auto", "fixed", "predefined")
_ORIENTATIONS = {"horizontal": "Horizontal", "h": "Horizontal", "vertical": "Vertical", "v": "Vertical"}
_FIELDISH = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]{0,62}$")


def _number(name, value, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"{name} must be a number."
    if number != number or not low <= number <= high:
        return None, f"{name} must be between {low} and {high}."
    return number, None


def check_overview(overview_map_id, extent_map_id, color=None, width_mm=None, inset_box=None):
    """Which map shows the frame (overview_map_id), whose extent the frame shows (extent_map_id), optional style, and an optional inset to
    create ({x_mm, y_mm, width_mm, height_mm}). The two ids must differ."""
    out = {}
    for name, value in (("overview_map_id", overview_map_id), ("extent_map_id", extent_map_id)):
        if value is not None and not valid_item_id(value):
            return None, f"{name} is not a valid item id."
        out[name] = value
    if out["overview_map_id"] and out["overview_map_id"] == out["extent_map_id"]:
        return None, "A map cannot show its own extent as an overview: give two different maps."
    if color is not None:
        out["color"] = str(color).strip()
    if width_mm is not None:
        out["width_mm"], problem = _number("width_mm", width_mm, 0.05, 5)
        if problem:
            return None, problem
    if inset_box is not None:
        if not isinstance(inset_box, dict):
            return None, "inset_box must be an object with x_mm, y_mm, width_mm and height_mm."
        box = {}
        for key, low, high in (("x_mm", 0, 2000), ("y_mm", 0, 2000), ("width_mm", 10, 1000), ("height_mm", 10, 1000)):
            if key not in inset_box:
                return None, f"inset_box needs {key}."
            box[key], problem = _number(f"inset_box.{key}", inset_box[key], low, high)
            if problem:
                return None, problem
        out["inset_box"] = box
    if not out.get("overview_map_id") and "inset_box" not in out:
        return None, "Give overview_map_id (an existing map) or inset_box (to create a new inset map)."
    return out, None


def check_guides_grid(guides=None, clear_guides=None, grid_mm=None, snap_to_grid=None, snap_to_guides=None, show_grid=None):
    out = {}
    if guides is not None:
        if not isinstance(guides, list) or len(guides) > MAX_GUIDES:
            return None, f"guides must be a list of at most {MAX_GUIDES} {{orientation, position_mm}} objects."
        clean = []
        for i, guide in enumerate(guides, start=1):
            if not isinstance(guide, dict):
                return None, f"Guide {i} must be an object."
            key = _ORIENTATIONS.get(str(guide.get("orientation", "")).strip().lower())
            if key is None:
                return None, f"Guide {i}: orientation must be horizontal or vertical."
            position, problem = _number(f"Guide {i} position_mm", guide.get("position_mm"), 0, 2000)
            if problem:
                return None, problem
            clean.append({"orientation": key, "position_mm": position})
        out["guides"] = clean
    if clear_guides is not None:
        if not isinstance(clear_guides, bool):
            return None, "clear_guides must be true or false."
        out["clear_guides"] = clear_guides
    if grid_mm is not None:
        out["grid_mm"], problem = _number("grid_mm", grid_mm, 1, 200)
        if problem:
            return None, problem
    for name, value in (("snap_to_grid", snap_to_grid), ("snap_to_guides", snap_to_guides), ("show_grid", show_grid)):
        if value is not None:
            if not isinstance(value, bool):
                return None, f"{name} must be true or false."
            out[name] = value
    if not out:
        return None, "Give guides, clear_guides, grid_mm, snap_to_grid, snap_to_guides or show_grid."
    return out, None


def check_atlas(coverage_layer, page_name_field=None, sort_field=None, filter_expression=None, hide_coverage=None, margin_percent=None,
                scaling=None, map_item_id=None, disable=False):
    if disable:
        return {"disable": True}, None
    if not str(coverage_layer or "").strip():
        return None, "coverage_layer is required (the layer with one feature per page)."
    out = {"coverage_layer": str(coverage_layer).strip()}
    for name, value in (("page_name_field", page_name_field), ("sort_field", sort_field)):
        if value is not None:
            if not _FIELDISH.match(str(value)):
                return None, f"{name} must be a field name."
            out[name] = str(value)
    if filter_expression is not None and str(filter_expression).strip():
        out["filter_expression"] = str(filter_expression).strip()
    if hide_coverage is not None:
        if not isinstance(hide_coverage, bool):
            return None, "hide_coverage must be true or false."
        out["hide_coverage"] = hide_coverage
    if margin_percent is not None:
        out["margin_percent"], problem = _number("margin_percent", margin_percent, 0, 200)
        if problem:
            return None, problem
    if scaling is not None:
        word = str(scaling).strip().lower()
        if word not in ATLAS_SCALING:
            return None, f"scaling must be one of: {', '.join(ATLAS_SCALING)}."
        out["scaling"] = word
    if map_item_id is not None:
        if not valid_item_id(map_item_id):
            return None, "map_item_id is not a valid item id."
        out["map_item_id"] = map_item_id
    return out, None


def check_export_extras(kind, world_file, geopdf):
    """None or a message: a world file belongs to image exports, GeoPDF to PDF."""
    if world_file and kind != "image":
        return "world_file applies to image exports (.png, .jpg, .tif) only."
    if geopdf and kind != "pdf":
        return "geopdf applies to .pdf exports only."
    return None
