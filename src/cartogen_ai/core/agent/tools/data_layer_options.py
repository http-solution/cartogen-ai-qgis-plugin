"""Pure (Qt-free) validation for the M1 data-source tools in data_layer_tools.py, unit-tested offline.

The one security-relevant piece is the virtual-layer SQL screen. A virtual layer runs SQLite over the project's layers, and SQLite can
read and write files (ATTACH, load_extension, readfile/writefile where compiled in) and QGIS lets a query name a data source directly.
The screen accepts one SELECT (or WITH ... SELECT) over project layers and refuses everything else. It is a screen, not an SQL parser:
a legitimate query that trips it is told why so it can be rephrased."""
import os
import re

MAX_SQL_LENGTH = 4000
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,62}$")
_QUOTED = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|`[^`]*`|\[[^\]]*\]")
_WORD = re.compile(r"[A-Za-z_]+")
_FORBIDDEN = {"insert", "update", "delete", "drop", "alter", "create", "attach", "detach", "pragma", "vacuum", "reindex", "analyze",
              "load_extension", "readfile", "writefile", "edit", "fts3_tokenizer", "zipfile", "sqlar", "truncate", "begin", "commit",
              "rollback", "savepoint", "release", "explain", "virtual", "temp", "temporary"}
_SOURCE_MARKERS = ("ogr:", "file:", "http:", "https:", "ftp:", "://", ":\\", "/etc/", "..")


def virtual_sql_violation(sql):
    """Why `sql` cannot be a virtual layer query, or None."""
    if not isinstance(sql, str) or not sql.strip():
        return "The query is empty."
    if len(sql) > MAX_SQL_LENGTH:
        return f"The query is longer than {MAX_SQL_LENGTH} characters."
    text = sql.strip().rstrip(";").strip()
    lowered = sql.lower()
    for marker in _SOURCE_MARKERS:
        if marker in lowered:
            return (f"The query contains '{marker}'. A virtual layer may only read layers that are already in the project, "
                    "by their layer name; paths and URLs are not allowed.")
    bare = _QUOTED.sub("''", text)
    if bare.count("'") % 2 or bare.count('"') % 2:
        return "The query has an unbalanced quote."
    for token in (";", "--", "/*", "*/", "\x00"):
        if token in bare:
            return f"The query contains '{token}', which is not allowed (one statement, no comments)."
    words = [w.lower() for w in _WORD.findall(bare)]
    if not words or words[0] not in ("select", "with"):
        return "Only a SELECT query can define a virtual layer."
    bad = sorted(set(words) & _FORBIDDEN)
    if bad:
        return f"The query uses '{bad[0]}', which is not allowed in a virtual layer."
    return None


def identifier_violation(label, value):
    """Plain database identifier (schema, table, column): letters, digits, underscore, dollar; no quoting tricks."""
    if not isinstance(value, str) or not _IDENTIFIER.match(value):
        return f"{label} '{value}' is not a plain name (letters, digits and underscores, starting with a letter or underscore)."
    return None


def layer_definition_path_violation(path, must_exist):
    text = str(path or "").strip()
    if not text:
        return "A file path is required."
    if "://" in text:
        return "Layer definition files must be local files."
    if not text.lower().endswith(".qlr"):
        return "A layer definition file ends in .qlr."
    if must_exist and not os.path.isfile(text):
        return f"File not found: {text}"
    return None


def package_path_violation(path):
    text = str(path or "").strip()
    if not text:
        return "An output path is required."
    if "://" in text:
        return "The package must be written to a local file."
    if not text.lower().endswith(".gpkg"):
        return "An offline package is a GeoPackage: the path must end in .gpkg."
    return None
