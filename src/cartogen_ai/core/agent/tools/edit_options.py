"""Pure (Qt-free) validation for the M3 editing tools in edit_ops_tools.py, so it is unit-tested without QGIS.

Why a separate module: the layer filter is the one place here where model-written text goes straight into the data provider's own query
language (an OGR/SQLite WHERE clause, a PostgreSQL WHERE clause), not QGIS's expression engine, so the screen has to be conservative.
It accepts a plain WHERE-clause condition only. Statement separators, comments and anything that is not a condition are refused; it is a
screen, not a SQL parser, and a legitimate filter that trips it is told why so the user can rephrase."""
import re

MAX_FILTER_LENGTH = 1000
MAX_SCALE_FACTOR = 1000.0
_FORBIDDEN_WORDS = ("select", "insert", "update", "delete", "drop", "alter", "attach", "detach", "pragma", "create", "union", "exec",
                    "execute", "truncate", "grant", "revoke", "copy", "vacuum", "replace", "load_extension", "pg_sleep", "into")
_WORD = re.compile(r"[A-Za-z_]+")
_QUOTED = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")
FIELD_CONVERSIONS = ("String", "Int", "LongLong", "Double")


def filter_violation(text):
    """Why `text` cannot be used as a layer filter, or None. Quoted strings and quoted identifiers are ignored when looking for
    keywords, so "name" = 'select' is fine; an unbalanced quote is refused."""
    if not isinstance(text, str) or not text.strip():
        return "The filter is empty; use clear=true to remove the current filter."
    if len(text) > MAX_FILTER_LENGTH:
        return f"The filter is longer than {MAX_FILTER_LENGTH} characters."
    bare = _QUOTED.sub("''", text)
    if bare.count("'") % 2 or bare.count('"') % 2:
        return "The filter has an unbalanced quote."
    for token in (";", "--", "/*", "*/", "\\", "\x00"):
        if token in bare:
            return f"The filter contains '{token}', which is not allowed in a layer filter."
    words = {w.lower() for w in _WORD.findall(bare)}
    bad = sorted(words & set(_FORBIDDEN_WORDS))
    if bad:
        return f"The filter uses '{bad[0]}', which is not allowed: a layer filter is a plain condition such as \"pop\" > 100."
    return None


def transform_options(move_x=None, move_y=None, rotate_degrees=None, scale_factor=None):
    """(clean options, error). At least one transform is needed; values must be finite numbers; scale must be > 0."""
    out = {}
    for key, value in (("move_x", move_x), ("move_y", move_y), ("rotate_degrees", rotate_degrees), ("scale_factor", scale_factor)):
        if value in (None, ""):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None, f"{key} must be a number."
        if number != number or number in (float("inf"), float("-inf")):
            return None, f"{key} must be a finite number."
        out[key] = number
    if not out:
        return None, "Give at least one of move_x, move_y, rotate_degrees or scale_factor."
    scale = out.get("scale_factor")
    if scale is not None and not 0 < scale <= MAX_SCALE_FACTOR:
        return None, f"scale_factor must be above 0 and at most {MAX_SCALE_FACTOR:g}."
    return out, None


def describe_transform(opts):
    parts = []
    if "move_x" in opts or "move_y" in opts:
        parts.append(f"move by ({opts.get('move_x', 0):g}, {opts.get('move_y', 0):g}) layer units")
    if "rotate_degrees" in opts:
        parts.append(f"rotate {opts['rotate_degrees']:g} degrees clockwise about each feature's centre")
    if "scale_factor" in opts:
        parts.append(f"scale by {opts['scale_factor']:g} about each feature's centre")
    return ", ".join(parts)


def conversion_kind(word):
    """Canonical field type word for change_field_type (String, Int, LongLong, Double) or None."""
    return {"string": "String", "text": "String", "integer": "Int", "int": "Int", "long": "LongLong", "bigint": "LongLong",
            "double": "Double", "float": "Double", "real": "Double", "decimal": "Double"}.get(str(word or "").strip().lower())


def convert_value(value, kind):
    """(converted, lossy). `lossy` is True when a non-NULL value could not be converted and becomes NULL, or loses its fraction."""
    if value is None or (not isinstance(value, str) and value != value):
        return None, False
    try:
        if kind == "String":
            return str(value), False
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return None, True
        if kind in ("Int", "LongLong"):
            whole = int(number)
            if kind == "Int" and abs(whole) > 2147483647:
                return None, True
            return whole, whole != number
        return number, False
    except (TypeError, ValueError, OverflowError):
        return None, True
