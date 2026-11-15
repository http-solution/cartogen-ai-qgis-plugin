"""Pure (Qt-free) validation for the package F symbology tools in symbology_extra_tools.py, unit-tested offline.

Package F finishes M4: rule-based labels, callouts and masks, SVG and font markers, pie and bar diagrams, hillshade and contour renderers
for rasters, and a personal symbol library. Everything here checks the model's numbers, words and paths BEFORE QGIS is touched, so a bad
request returns one clear message instead of a half-changed layer."""
import os

MAX_RULES = 20
MAX_DIAGRAM_FIELDS = 8
MAX_SVG_BYTES = 2_000_000
DIAGRAM_KINDS = ("pie", "bar", "histogram")
CALLOUT_STYLES = ("simple", "manhattan")
RELIEF_STYLES = ("hillshade", "contour")
_NAME_FORBIDDEN = set('<>:"/\\|?*\x00')


def check_number(name, value, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"{name} must be a number."
    if number != number or not low <= number <= high:
        return None, f"{name} must be between {low} and {high}."
    return number, None


def check_rules(rules):
    """([{field, filter, font_size, font_color, max_scale, min_scale, description}], None) or (None, message). `filter` is left as text:
    the caller runs it through the expression screen. At least one rule, at most MAX_RULES."""
    if not isinstance(rules, list) or not rules:
        return None, "rules must be a non-empty list of {field, filter, ...} objects."
    if len(rules) > MAX_RULES:
        return None, f"At most {MAX_RULES} rules are accepted."
    out = []
    for i, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            return None, f"Rule {i} must be an object."
        field = str(rule.get("field") or "").strip()
        if not field:
            return None, f"Rule {i} needs a field to label with."
        clean = {"field": field, "filter": str(rule.get("filter") or "").strip(), "description": str(rule.get("description") or "").strip()[:80]}
        if rule.get("font_color") is not None:
            clean["font_color"] = str(rule["font_color"]).strip()
        for key, low, high in (("font_size", 1, 120), ("min_scale", 1, 1e10), ("max_scale", 1, 1e10)):
            if rule.get(key) is not None:
                clean[key], problem = check_number(f"Rule {i} {key}", rule[key], low, high)
                if problem:
                    return None, problem
        out.append(clean)
    return out, None


def check_callout(enabled=None, style=None, color=None, width_mm=None, mask=None, mask_size_mm=None):
    out = {}
    if enabled is not None:
        if not isinstance(enabled, bool):
            return None, "enabled must be true or false."
        out["enabled"] = enabled
    if style is not None:
        key = str(style).strip().lower()
        if key not in CALLOUT_STYLES:
            return None, f"style must be one of: {', '.join(CALLOUT_STYLES)}."
        out["style"] = key
    if color is not None:
        out["color"] = str(color).strip()
    if width_mm is not None:
        out["width_mm"], problem = check_number("width_mm", width_mm, 0.05, 5)
        if problem:
            return None, problem
    if mask is not None:
        if not isinstance(mask, bool):
            return None, "mask must be true or false."
        out["mask"] = mask
    if mask_size_mm is not None:
        out["mask_size_mm"], problem = check_number("mask_size_mm", mask_size_mm, 0.1, 10)
        if problem:
            return None, problem
    if not out:
        return None, "Give at least one of enabled, style, color, width_mm, mask or mask_size_mm."
    return out, None


def check_marker_source(kind, svg_path=None, font_family=None, character=None, size_mm=None, color=None):
    """Options for an SVG or font point marker. SVG: a local .svg file (checked for existence and size elsewhere via check_svg_file)."""
    word = str(kind or "").strip().lower()
    if word not in ("svg", "font"):
        return None, "kind must be svg or font."
    out = {"kind": word}
    if word == "svg":
        text = str(svg_path or "").strip()
        if not text:
            return None, "svg_path is required for an SVG marker (a local .svg file, or a name from QGIS's SVG library such as arrows/Arrow_01.svg)."
        if "://" in text:
            return None, "SVG markers must be local files; URLs are not accepted."
        if not text.lower().endswith(".svg"):
            return None, "svg_path must end in .svg."
        out["svg_path"] = text
    else:
        family = str(font_family or "").strip()
        char = str(character or "")
        if not family or len(family) > 100:
            return None, "font_family is required for a font marker (for example 'Arial')."
        if len(char) != 1:
            return None, "character must be exactly one character."
        out.update(font_family=family, character=char)
    if size_mm is not None:
        out["size_mm"], problem = check_number("size_mm", size_mm, 0.5, 100)
        if problem:
            return None, problem
    if color is not None:
        out["color"] = str(color).strip()
    return out, None


def check_svg_file(path):
    """None when `path` is a readable .svg file of a sane size, else the reason."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return f"SVG file not found: {path}"
    if size == 0 or size > MAX_SVG_BYTES:
        return f"The SVG file must be between 1 byte and {MAX_SVG_BYTES // 1_000_000} MB."
    return None


def check_diagram(kind, fields, size_mm=None, colors=None, clear=False):
    """({kind, fields, size_mm, colors}, None). `clear` needs no other option."""
    if clear:
        return {"clear": True}, None
    word = str(kind or "").strip().lower()
    if word not in DIAGRAM_KINDS:
        return None, f"kind must be one of: {', '.join(DIAGRAM_KINDS)}."
    if not isinstance(fields, list) or not fields or not all(isinstance(f, str) and f.strip() for f in fields):
        return None, "fields must be a non-empty list of numeric field names."
    if len(fields) > MAX_DIAGRAM_FIELDS or len(set(fields)) != len(fields):
        return None, f"Give 1 to {MAX_DIAGRAM_FIELDS} different fields."
    out = {"kind": word, "fields": [f.strip() for f in fields]}
    out["size_mm"], problem = check_number("size_mm", 10 if size_mm is None else size_mm, 2, 100)
    if problem:
        return None, problem
    if colors is not None:
        if not isinstance(colors, list) or len(colors) != len(fields):
            return None, "colors must be a list with one colour per field."
        out["colors"] = [str(c).strip() for c in colors]
    return out, None


def check_relief(style, azimuth=None, altitude=None, z_factor=None, interval=None, index_interval=None, band=None):
    word = str(style or "").strip().lower()
    if word not in RELIEF_STYLES:
        return None, f"style must be one of: {', '.join(RELIEF_STYLES)}."
    out = {"style": word}
    for name, value, low, high in (("azimuth", azimuth, 0, 360), ("altitude", altitude, 0, 90), ("z_factor", z_factor, 0.01, 1000),
                                   ("interval", interval, 1e-6, 1e9), ("index_interval", index_interval, 1e-6, 1e9)):
        if value is not None:
            out[name], problem = check_number(name, value, low, high)
            if problem:
                return None, problem
    if band is not None:
        try:
            out["band"] = int(band)
        except (TypeError, ValueError):
            return None, "band must be a whole number (1 is the first band)."
        if out["band"] < 1:
            return None, "band must be 1 or more."
    if word == "contour" and "index_interval" in out and "interval" in out and out["index_interval"] < out["interval"]:
        return None, "index_interval must not be smaller than interval."
    return out, None


def symbol_name(name):
    text = str(name or "").strip()
    if not text or len(text) > 80 or any(c in _NAME_FORBIDDEN for c in text):
        return None, "A symbol name is 1 to 80 characters and has no path or special characters."
    return text, None
