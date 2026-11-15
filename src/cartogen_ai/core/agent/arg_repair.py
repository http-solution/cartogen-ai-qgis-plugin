"""Repairs Windows paths whose backslash escapes were eaten before a tool saw them.

Why: in the 1.18.4 smoke run (row D6, 2026-10-27) the model wrote `C:\\...\\fixtures\\before_fixture.asc` with single backslashes. JSON decoding
turned `\\f` into a form feed and `\\b` into a backspace, so `calculate_raster_change_detection` was asked for "C:\\...ixturesefore_fixture.asc" and
reported the layer missing; the reply then told the user to add the rasters by hand. A control character never belongs in a file path, so putting the
backslash and letter back is safe, and only string arguments that look like Windows paths are touched.
"""
import re

_CONTROL_TO_ESCAPE = {"\x07": "\\a", "\x08": "\\b", "\x0c": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\x0b": "\\v"}
_CONTROL = re.compile("[" + "".join(_CONTROL_TO_ESCAPE) + "]")
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def repair_windows_path(value):
    """Returns `value` with eaten backslash escapes restored when it is a Windows drive path, else unchanged."""
    if not isinstance(value, str) or not _WINDOWS_PATH.match(value) or not _CONTROL.search(value):
        return value
    return _CONTROL.sub(lambda m: _CONTROL_TO_ESCAPE[m.group(0)], value)


def repair_path_arguments(args):
    """Returns a copy of a tool's argument dict with every top-level string, and every string inside a top-level list, repaired."""
    fixed = {}
    for key, value in args.items():
        if isinstance(value, list):
            fixed[key] = [repair_windows_path(item) for item in value]
        else:
            fixed[key] = repair_windows_path(value)
    return fixed
