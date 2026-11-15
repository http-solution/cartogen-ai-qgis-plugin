"""Pure (Qt-free) validation for the package B project tools in project_ops_tools.py, unit-tested offline."""
import re
from datetime import datetime

MAX_TEXT = 4000
MAX_ANNOTATION = 500
SNAP_TYPES = {"vertex": "Vertex", "segment": "Segment", "vertex and segment": "VertexAndSegment", "centroid": "Centroid",
              "middle": "MiddleOfSegment", "middle of segment": "MiddleOfSegment", "endpoint": "LineEndpoint", "line endpoint": "LineEndpoint",
              "area": "Area"}
SNAP_MODES = {"all layers": "AllLayers", "all": "AllLayers", "active layer": "ActiveLayer", "active": "ActiveLayer",
              "advanced": "AdvancedConfiguration"}
SNAP_UNITS = {"pixels": "Pixels", "pixel": "Pixels", "px": "Pixels", "project units": "Project", "map units": "Project",
              "layer units": "Layer"}
_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]{0,62}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_text(label, value, limit=MAX_TEXT):
    """(text, error): a string without control characters, at most `limit` long."""
    if value is None:
        return None, None
    text = str(value).strip()
    if _CONTROL.search(text):
        return None, f"{label} contains control characters."
    if len(text) > limit:
        return None, f"{label} is longer than {limit} characters."
    return text, None


def check_metadata(title=None, abstract=None, license=None, rights=None, keywords=None, contact_name=None,  # noqa: A002
                   contact_organization=None, contact_email=None):
    """({field: cleaned value}, error). Needs at least one field. keywords is a list of words."""
    out = {}
    for label, value, limit in (("title", title, 300), ("abstract", abstract, MAX_TEXT), ("license", license, 300), ("rights", rights, 300),
                                ("contact_name", contact_name, 200), ("contact_organization", contact_organization, 200),
                                ("contact_email", contact_email, 200)):
        text, problem = clean_text(label, value, limit)
        if problem:
            return None, problem
        if text is not None:
            out[label] = text
    if contact_email and "@" not in out.get("contact_email", ""):
        return None, "contact_email is not an email address."
    if keywords is not None:
        if not isinstance(keywords, (list, tuple)) or len(keywords) > 50:
            return None, "keywords must be a list of at most 50 words."
        words = []
        for word in keywords:
            text, problem = clean_text("a keyword", word, 100)
            if problem:
                return None, problem
            if text:
                words.append(text)
        out["keywords"] = words
    if not out:
        return None, "Give at least one of title, abstract, license, rights, keywords or a contact."
    return out, None


def check_snapping(enabled=None, snap_type=None, tolerance=None, units=None, mode=None, topological=None):
    """({option: value}, error) with the QGIS member names for type, units and mode."""
    out = {}
    if enabled is not None:
        out["enabled"] = bool(enabled)
    if snap_type is not None:
        key = SNAP_TYPES.get(str(snap_type).strip().lower().replace("_", " "))
        if key is None:
            return None, f"snap_type must be one of: {', '.join(sorted(set(SNAP_TYPES)))}."
        out["type"] = key
    if mode is not None:
        key = SNAP_MODES.get(str(mode).strip().lower().replace("_", " "))
        if key is None:
            return None, f"mode must be one of: {', '.join(sorted(set(SNAP_MODES)))}."
        out["mode"] = key
    if units is not None:
        key = SNAP_UNITS.get(str(units).strip().lower().replace("_", " "))
        if key is None:
            return None, f"units must be one of: {', '.join(sorted(set(SNAP_UNITS)))}."
        out["units"] = key
    if tolerance is not None:
        try:
            value = float(tolerance)
        except (TypeError, ValueError):
            return None, "tolerance must be a number."
        if not 0 < value <= 1000:
            return None, "tolerance must be above 0 and at most 1000."
        out["tolerance"] = value
    if topological is not None:
        out["topological"] = bool(topological)
    if not out:
        return None, "Give at least one snapping option."
    return out, None


def relation_id(name):
    text = str(name or "").strip()
    if not _ID.match(text):
        return None, "The relation name must start with a letter and use letters, digits, spaces and underscores (63 characters at most)."
    return text, None


def parse_time(label, value):
    """(datetime, error) for an ISO date or date-time like 2026-03-01 or 2026-03-01T12:00:00."""
    try:
        return datetime.fromisoformat(str(value).strip()), None
    except (TypeError, ValueError):
        return None, f"{label} must be a date such as 2026-03-01 or 2026-03-01T12:00:00."


def check_time_range(start, end):
    first, problem = parse_time("start", start)
    if problem:
        return None, problem
    last, problem = parse_time("end", end)
    if problem:
        return None, problem
    if last < first:
        return None, "The end must not be before the start."
    return (first, last), None


def check_annotation_text(text):
    cleaned, problem = clean_text("The annotation text", text, MAX_ANNOTATION)
    if problem:
        return None, problem
    if not cleaned:
        return None, "The annotation text is empty."
    return cleaned, None
