"""Plain-language symbol, label and raster-display options for the M4 tools (roadmap 2026-10-14). Qt-free, so it is unit-tested without QGIS.

The model and the user say "dashed", "thin", "star", "hatched"; QGIS wants Qt pen styles, brush styles and marker shapes. This module turns
the words into stable keys and checks every number before QGIS is touched, so a bad request returns one clear message instead of a partly
changed layer. The QGIS enum for each key is looked up in symbology_tools.py (the scoped Qt6 form first, see _qgis_enum_compat.py)."""

LINE_STYLES = {
    "solid": "SolidLine", "dashed": "DashLine", "dotted": "DotLine", "dash_dot": "DashDotLine", "dash_dot_dot": "DashDotDotLine",
    "none": "NoPen",
}
_LINE_ALIASES = {"dash": "dashed", "dot": "dotted", "dashdot": "dash_dot", "dash-dot": "dash_dot", "dash dot": "dash_dot",
                 "dashdotdot": "dash_dot_dot", "dash-dot-dot": "dash_dot_dot", "no line": "none", "no outline": "none",
                 "invisible": "none", "continuous": "solid", "line": "solid"}

FILL_STYLES = {
    "solid": "SolidPattern", "none": "NoBrush", "horizontal": "HorPattern", "vertical": "VerPattern", "cross": "CrossPattern",
    "diagonal_cross": "DiagCrossPattern", "hatch_forward": "BDiagPattern", "hatch_backward": "FDiagPattern",
    "dots_dense": "Dense6Pattern", "dots_sparse": "Dense7Pattern",
}
_FILL_ALIASES = {"hatched": "hatch_forward", "hatch": "hatch_forward", "diagonal": "hatch_forward", "stripes": "horizontal",
                 "striped": "horizontal", "crosshatch": "diagonal_cross", "cross hatch": "diagonal_cross", "grid": "cross",
                 "empty": "none", "hollow": "none", "transparent": "none", "no fill": "none", "dotted": "dots_sparse",
                 "dots": "dots_sparse"}

MARKER_SHAPES = {
    "circle": "Circle", "square": "Square", "diamond": "Diamond", "triangle": "EquilateralTriangle", "star": "Star",
    "cross": "Cross", "x": "Cross2", "pentagon": "Pentagon", "hexagon": "Hexagon", "heart": "Heart", "arrow": "Arrow",
}
_SHAPE_ALIASES = {"dot": "circle", "round": "circle", "box": "square", "cross_x": "x", "saltire": "x", "plus": "cross",
                  "pin": "circle", "five_point_star": "star"}

LABEL_PLACEMENTS = {
    "around_point": "AroundPoint", "over_point": "OverPoint", "ordered_around_point": "OrderedPositionsAroundPoint",
    "horizontal": "Horizontal", "free": "Free", "curved": "Curved", "parallel": "Line", "around_polygon": "AroundPoint",
}
_PLACEMENT_ALIASES = {"around": "around_point", "on_point": "over_point", "over": "over_point", "centered": "over_point",
                      "centre": "over_point", "center": "over_point", "along_line": "parallel", "line": "parallel",
                      "follow_line": "curved", "curve": "curved"}

RESAMPLING = ("nearest", "bilinear", "cubic")
MAX_UNIQUE_VALUES = 256


def _key(value, table, aliases):
    text = " ".join(str(value or "").strip().lower().replace("-", " ").replace("_", " ").split())
    underscored = text.replace(" ", "_")
    if underscored in table:
        return underscored
    return aliases.get(text) or aliases.get(underscored) or aliases.get(text.replace(" ", ""))


def line_style_key(value):
    return _key(value, LINE_STYLES, _LINE_ALIASES)


def fill_style_key(value):
    return _key(value, FILL_STYLES, _FILL_ALIASES)


def marker_shape_key(value):
    return _key(value, MARKER_SHAPES, _SHAPE_ALIASES)


def placement_key(value):
    return _key(value, LABEL_PLACEMENTS, _PLACEMENT_ALIASES)


def _choice_error(name, value, options):
    return f"'{value}' is not a known {name}. Choose one of: {', '.join(sorted(options))}."


def validate_symbol_options(fill_color=None, outline_color=None, outline_width_mm=None, opacity_percent=None, marker_shape=None,
                            marker_size_mm=None, line_style=None, fill_style=None):
    """({normalised options}, None) or (None, message). Keys with no value are left out, so "unchanged" is the absence of a key."""
    out = {}
    if all(v is None for v in (fill_color, outline_color, outline_width_mm, opacity_percent, marker_shape, marker_size_mm, line_style,
                               fill_style)):
        return None, ("Nothing to change: give at least one of fill_color, outline_color, outline_width_mm, opacity_percent, marker_shape, "
                      "marker_size_mm, line_style or fill_style.")
    for name, value in (("fill_color", fill_color), ("outline_color", outline_color)):
        if value is not None:
            if not str(value).strip():
                return None, f"{name} is empty."
            out[name] = str(value).strip()
    for name, value, low, high in (("outline_width_mm", outline_width_mm, 0, 20), ("marker_size_mm", marker_size_mm, 0.1, 100),
                                   ("opacity_percent", opacity_percent, 0, 100)):
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None, f"{name} must be a number."
        if not low <= number <= high:
            return None, f"{name} must be between {low} and {high}."
        out[name] = number
    if line_style is not None:
        key = line_style_key(line_style)
        if key is None:
            return None, _choice_error("line_style", line_style, LINE_STYLES)
        out["line_style"] = key
    if fill_style is not None:
        key = fill_style_key(fill_style)
        if key is None:
            return None, _choice_error("fill_style", fill_style, FILL_STYLES)
        out["fill_style"] = key
    if marker_shape is not None:
        key = marker_shape_key(marker_shape)
        if key is None:
            return None, _choice_error("marker_shape", marker_shape, MARKER_SHAPES)
        out["marker_shape"] = key
    return out, None


def validate_label_options(font_color=None, font_size=None, bold=None, italic=None, halo=None, halo_color=None, halo_size_mm=None,
                           placement=None, visible_zoomed_out_to=None, visible_zoomed_in_to=None, show_labels=None):
    out = {}
    given = (font_color, font_size, bold, italic, halo, halo_color, halo_size_mm, placement, visible_zoomed_out_to, visible_zoomed_in_to,
             show_labels)
    if all(v is None for v in given):
        return None, ("Nothing to change: give at least one label option (font_color, font_size, bold, italic, halo, halo_color, "
                      "halo_size_mm, placement, visible_zoomed_out_to, visible_zoomed_in_to, show_labels).")
    if font_color is not None:
        out["font_color"] = str(font_color).strip()
    if halo_color is not None:
        out["halo_color"] = str(halo_color).strip()
    for name, value, low, high in (("font_size", font_size, 1, 120), ("halo_size_mm", halo_size_mm, 0, 10)):
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None, f"{name} must be a number."
        if not low <= number <= high:
            return None, f"{name} must be between {low} and {high}."
        out[name] = number
    for name, value in (("bold", bold), ("italic", italic), ("halo", halo), ("show_labels", show_labels)):
        if value is not None:
            if not isinstance(value, bool):
                return None, f"{name} must be true or false."
            out[name] = value
    if placement is not None:
        key = placement_key(placement)
        if key is None:
            return None, _choice_error("placement", placement, LABEL_PLACEMENTS)
        out["placement"] = key
    for name, value in (("visible_zoomed_out_to", visible_zoomed_out_to), ("visible_zoomed_in_to", visible_zoomed_in_to)):
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None, f"{name} must be a scale denominator such as 250000 (for 1:250,000)."
        if number <= 0:
            return None, f"{name} must be above 0 (a scale denominator such as 250000)."
        out[name] = number
    far, near = out.get("visible_zoomed_out_to"), out.get("visible_zoomed_in_to")
    if far is not None and near is not None and far < near:
        return None, "visible_zoomed_out_to (the larger denominator, e.g. 250000) must not be below visible_zoomed_in_to (e.g. 5000)."
    return out, None


def validate_raster_options(mode=None, resampling=None, opacity_percent=None, nodata_min=None, nodata_max=None, clear_nodata=None):
    out = {}
    if all(v is None for v in (mode, resampling, opacity_percent, nodata_min, nodata_max, clear_nodata)):
        return None, "Nothing to change: give mode='unique_values', resampling, opacity_percent, nodata_min/nodata_max or clear_nodata."
    if mode is not None:
        if str(mode).strip().lower() not in ("unique_values", "paletted"):
            return None, "mode must be 'unique_values' (one colour per distinct cell value) or left out."
        out["mode"] = "unique_values"
    if resampling is not None:
        key = str(resampling).strip().lower()
        if key not in RESAMPLING:
            return None, _choice_error("resampling", resampling, RESAMPLING)
        out["resampling"] = key
    if opacity_percent is not None:
        try:
            number = float(opacity_percent)
        except (TypeError, ValueError):
            return None, "opacity_percent must be a number."
        if not 0 <= number <= 100:
            return None, "opacity_percent must be between 0 and 100."
        out["opacity_percent"] = number
    for name, value in (("nodata_min", nodata_min), ("nodata_max", nodata_max)):
        if value is not None:
            try:
                out[name] = float(value)
            except (TypeError, ValueError):
                return None, f"{name} must be a number."
    if "nodata_max" in out and "nodata_min" not in out:
        out["nodata_min"] = out["nodata_max"]
    if "nodata_min" in out and "nodata_max" not in out:
        out["nodata_max"] = out["nodata_min"]
    if "nodata_min" in out and out["nodata_min"] > out["nodata_max"]:
        return None, "nodata_min must not be above nodata_max."
    if clear_nodata is not None:
        if not isinstance(clear_nodata, bool):
            return None, "clear_nodata must be true or false."
        if clear_nodata and "nodata_min" in out:
            return None, "Give either nodata_min/nodata_max or clear_nodata, not both."
        out["clear_nodata"] = clear_nodata
    return out, None
