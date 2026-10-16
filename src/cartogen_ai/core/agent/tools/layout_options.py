"""Validation for the M5 layout tools (roadmap 2026-10-14). Pure Python, no QGIS, unit-tested offline.

Everything a layout request names is checked here before QGIS is touched, so a bad value returns one clear message and leaves the layout
as it was: item kinds, positions and sizes in millimetres, page sizes, picture and template paths, export formats. Two things are refused
on purpose and the reason is stated in the message: web (HTML) frames, which would run web content inside QGIS, and pictures given as a
URL, which would fetch from the network with no check."""
import os
import re

ITEM_KINDS = ("label", "picture", "shape", "arrow", "table")
REFUSED_KINDS = {
    "html": "HTML frames run web content inside QGIS, so they are not added from a chat request. Put the text in a label, or an image in a "
            "picture item.",
    "chart": "Chart items are not offered yet. Use a picture of a chart exported from a layer, or an attribute table.",
}
SHAPES = ("rectangle", "ellipse", "triangle")
PICTURE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".svg", ".gif", ".bmp", ".tif", ".tiff")
EXPORT_FORMATS = {".pdf": "pdf", ".png": "image", ".jpg": "image", ".jpeg": "image", ".tif": "image", ".tiff": "image", ".svg": "svg"}
MAX_TABLE_ROWS = 200
MAX_PAGES = 20
MAX_DIMENSION_MM = 5000.0

# width, height in millimetres, portrait
PAGE_SIZES = {
    "a0": (841, 1189), "a1": (594, 841), "a2": (420, 594), "a3": (297, 420), "a4": (210, 297), "a5": (148, 210),
    "letter": (215.9, 279.4), "legal": (215.9, 355.6), "tabloid": (279.4, 431.8),
}

_ITEM_ID = re.compile(r"^[A-Za-z0-9_\- ]{1,64}$")
_URL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")


def valid_item_id(value):
    return bool(_ITEM_ID.match(str(value or "")))


def _number(name, value, low=None, high=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"{name} must be a number."
    if low is not None and number < low:
        return None, f"{name} must be at least {low}."
    if high is not None and number > high:
        return None, f"{name} must be at most {high}."
    return number, None


def validate_geometry(x_mm=None, y_mm=None, width_mm=None, height_mm=None, need_all=False):
    """({present keys: float}, None) or (None, message). With need_all the four values are required (a new item)."""
    out = {}
    for name, value, low in (("x_mm", x_mm, -MAX_DIMENSION_MM), ("y_mm", y_mm, -MAX_DIMENSION_MM), ("width_mm", width_mm, 1.0),
                             ("height_mm", height_mm, 1.0)):
        if value is None:
            if need_all:
                return None, f"{name} is required (position and size are in millimetres on the page)."
            continue
        number, problem = _number(name, value, low, MAX_DIMENSION_MM)
        if problem:
            return None, problem
        out[name] = number
    return out, None


def page_size_mm(size, orientation="landscape"):
    """(width, height) in mm for a named page size and orientation, or (None, message)."""
    key = str(size or "").strip().lower().replace(" ", "")
    if key not in PAGE_SIZES:
        return None, f"'{size}' is not a known page size. Choose one of: {', '.join(s.upper() for s in PAGE_SIZES)}."
    orient = str(orientation or "landscape").strip().lower()
    if orient not in ("landscape", "portrait"):
        return None, "orientation must be 'landscape' or 'portrait'."
    w, h = PAGE_SIZES[key]
    return ((h, w) if orient == "landscape" else (w, h)), None


def validate_new_item(kind, **opts):
    """Kind-specific checks for add_layout_item. Returns (cleaned dict, None) or (None, message)."""
    kind = str(kind or "").strip().lower()
    if kind in REFUSED_KINDS:
        return None, REFUSED_KINDS[kind]
    if kind not in ITEM_KINDS:
        return None, f"'{kind}' is not an item kind. Choose one of: {', '.join(ITEM_KINDS)}."
    out = {"kind": kind}
    handler = {"label": _label, "picture": _picture, "shape": _shape, "arrow": _arrow, "table": _table}[kind]
    problem = handler(opts, out)
    return (None, problem) if problem else (out, None)


def _label(opts, out):
    text = opts.get("text")
    if text is None or not str(text).strip():
        return "A label needs text."
    out["text"] = str(text)
    if opts.get("font_size") is not None:
        out["font_size"], problem = _number("font_size", opts["font_size"], 1, 200)
        return problem
    return None


def _picture(opts, out):
    path = str(opts.get("picture_path") or "").strip()
    if not path:
        return "A picture needs picture_path (a local image file)."
    if _URL.match(path):
        return "Pictures must be local files. A web address is not fetched from a chat request; download the image first."
    if os.path.splitext(path)[1].lower() not in PICTURE_EXTENSIONS:
        return f"Pictures can be {', '.join(PICTURE_EXTENSIONS)}."
    out["picture_path"] = path
    return None


def _shape(opts, out):
    shape = str(opts.get("shape") or "rectangle").strip().lower()
    if shape not in SHAPES:
        return f"shape must be one of: {', '.join(SHAPES)}."
    out["shape"] = shape
    if opts.get("outline_width_mm") is not None:
        out["outline_width_mm"], problem = _number("outline_width_mm", opts["outline_width_mm"], 0, 20)
        return problem
    return None


def _arrow(opts, out):
    for name in ("from_x_mm", "from_y_mm", "to_x_mm", "to_y_mm"):
        value, problem = _number(name, opts.get(name), -MAX_DIMENSION_MM, MAX_DIMENSION_MM)
        if problem:
            return "An arrow needs from_x_mm, from_y_mm, to_x_mm and to_y_mm (millimetres on the page). " + problem
        out[name] = value
    if (out["from_x_mm"], out["from_y_mm"]) == (out["to_x_mm"], out["to_y_mm"]):
        return "An arrow's start and end must differ."
    return None


def _table(opts, out):
    layer = str(opts.get("layer_name") or "").strip()
    if not layer:
        return "A table needs layer_name (a vector layer in the project)."
    out["layer_name"] = layer
    rows, problem = _number("max_rows", opts.get("max_rows", 10), 1, MAX_TABLE_ROWS)
    if problem:
        return problem
    out["max_rows"] = int(rows)
    fields = opts.get("fields")
    if fields is not None:
        if not isinstance(fields, list) or not all(isinstance(f, str) and f for f in fields) or not fields:
            return "fields must be a non-empty list of field names."
        out["fields"] = fields
    return None


def validate_export_path(path):
    """(format_key, None) for a supported extension, else (None, message). 'pdf', 'image' or 'svg'."""
    ext = os.path.splitext(str(path or ""))[1].lower()
    if ext not in EXPORT_FORMATS:
        return None, f"Unsupported extension '{ext}'. Use {', '.join(sorted(EXPORT_FORMATS))}."
    return EXPORT_FORMATS[ext], None


def validate_template_path(path, must_exist):
    text = str(path or "").strip()
    if not text:
        return "A template path is required."
    if _URL.match(text):
        return "Templates must be local files."
    if not text.lower().endswith(".qpt"):
        return "A layout template file ends in .qpt."
    if must_exist and not os.path.isfile(text):
        return f"Template file not found: {text}"
    return None


def validate_map_options(scale=None, rotation=None, bbox=None, extent_layer=None, lock_layers=None, map_theme=None):
    out = {}
    if all(v is None for v in (scale, rotation, bbox, extent_layer, lock_layers, map_theme)):
        return None, "Nothing to change: give scale, rotation, bbox, extent_layer, lock_layers or map_theme."
    if scale is not None:
        out["scale"], problem = _number("scale", scale, 1, 1e10)
        if problem:
            return None, problem + " Use the denominator, e.g. 250000 for 1:250,000."
    if rotation is not None:
        out["rotation"], problem = _number("rotation", rotation, -360, 360)
        if problem:
            return None, problem
    if bbox is not None and extent_layer is not None:
        return None, "Give either bbox or extent_layer, not both."
    if bbox is not None:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return None, "bbox must be [min_lon, min_lat, max_lon, max_lat] in EPSG:4326."
        values = []
        for v in bbox:
            number, problem = _number("bbox", v)
            if problem:
                return None, problem
            values.append(number)
        if values[0] >= values[2] or values[1] >= values[3] or not (values[0] >= -180 and values[2] <= 180 and values[1] >= -90 and values[3] <= 90):
            return None, "bbox must be [min_lon, min_lat, max_lon, max_lat] in degrees with min below max."
        out["bbox"] = values
    if extent_layer is not None:
        if not str(extent_layer).strip():
            return None, "extent_layer is empty."
        out["extent_layer"] = str(extent_layer).strip()
    if lock_layers is not None:
        if not isinstance(lock_layers, bool):
            return None, "lock_layers must be true or false."
        out["lock_layers"] = lock_layers
    if map_theme is not None:
        out["map_theme"] = str(map_theme).strip()
    return out, None
