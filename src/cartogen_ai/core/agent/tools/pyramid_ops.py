"""Raster pyramids, cell lookup and attribute-table helpers (PLAN-023 R10-4), pure Python (no QGIS, no GDAL, no numpy).

raster_inspect_tools.py does the file and GDAL work; what can be checked offline is here.

Pyramids (overviews) are smaller copies of a raster that QGIS draws when zoomed out, so a big raster draws fast. They are built NEXT TO the file in a sidecar .ovr file (GDAL opens the raster
read-only), so the raster itself is never rewritten. Default levels halve the raster (2, 4, 8, ...) while the smaller side stays at least 256 cells, at most 8 levels; a raster whose smaller
side is under 512 cells needs none. Known answers (the tests): 1024 x 1024 gives [2, 4], 4000 x 3000 gives [2, 4, 8], 300 x 300 gives []; the point (500025, 4000015) in a raster with the
origin (500000, 4000040) and 10-unit cells is column 2, row 2; a point left of the raster has no cell."""
import math

MIN_SIDE = 256
MAX_LEVELS = 8
MAX_CELLS = 100_000_000
METHODS = ("average", "nearest", "gauss", "cubic", "mode")
ROW_CAP = 200


def default_levels(width, height):
    """The overview factors for a raster of `width` x `height`: 2, 4, 8, ... while the smaller side divided by the factor is at least MIN_SIDE; at most MAX_LEVELS. Pure."""
    levels, factor = [], 2
    while len(levels) < MAX_LEVELS and min(width, height) // factor >= MIN_SIDE:
        levels.append(factor)
        factor *= 2
    return levels


def check_build(levels, method, width, height):
    """(levels to build, error text or None). `levels` None means the default for this size; an explicit list must be whole numbers of 2 or more, increasing, at most MAX_LEVELS. Pure."""
    if str(method or "average").strip().lower() not in METHODS:
        return None, f"method must be one of {', '.join(METHODS)} (mode suits classified rasters, average suits continuous ones)."
    if width * height > MAX_CELLS:
        return None, f"The raster has {width * height:,} cells, above the {MAX_CELLS:,} one request builds in the chat; use Layer Properties > Pyramids in QGIS for it."
    if levels is None:
        built = default_levels(width, height)
        if not built:
            return None, f"The raster is {width} x {height} cells; its smaller side is under {2 * MIN_SIDE}, so pyramids would not make it draw any faster."
        return built, None
    if not isinstance(levels, list) or not 1 <= len(levels) <= MAX_LEVELS:
        return None, f"levels must be a list of 1 to {MAX_LEVELS} whole numbers such as [2, 4, 8]."
    for value in levels:
        if isinstance(value, bool) or not isinstance(value, int | float) or float(value) != int(value) or int(value) < 2:
            return None, "every level must be a whole number of 2 or more (2 halves the raster, 4 quarters it)."
    ints = [int(v) for v in levels]
    if ints != sorted(set(ints)):
        return None, "levels must be increasing with no repeats."
    return ints, None


def cell_index(geotransform, x, y, width, height):
    """(column, row) of the cell that contains (x, y), or None when the point is outside the raster. `geotransform` is GDAL's (x0, dx, 0, y0, 0, dy) for a north-up raster. Pure."""
    x0, dx, _r1, y0, _r2, dy = geotransform
    if dx == 0 or dy == 0:
        return None
    col = math.floor((x - x0) / dx)
    row = math.floor((y - y0) / dy)
    return (col, row) if 0 <= col < width and 0 <= row < height else None


def rat_table(columns, rows, cap=ROW_CAP):
    """{'columns': names, 'rows': first `cap` rows as dicts, 'total_rows': n, 'truncated': bool} from a list of column names and a list of row lists. Pure."""
    shown = [dict(zip(columns, row, strict=False)) for row in rows[:cap]]
    return {"columns": list(columns), "rows": shown, "total_rows": len(rows), "truncated": len(rows) > cap}
