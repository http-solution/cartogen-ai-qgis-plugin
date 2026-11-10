"""Line editing helpers (PLAN-023 R9-3): request checks, reversing, and the end-snapping behind trim_extend_lines, all pure Python (no QGIS, no numpy).

reshape_geometry and offset_curve are done by QGIS's own QgsGeometry (reshapeGeometry, offsetCurve), see line_edit_tools.py. What is here can be checked offline.

trim_extend_lines moves the two end points of each line part to the nearest point on any OTHER line part when that point is within `tolerance` (and not already on it). A line
that stops short of another is extended to it; a line that overshoots it is trimmed back to it, because the nearest point of a line to an overshooting end is where the lines cross.
Distances are measured against the lines as they were, never the already-moved ends, so the result does not depend on the order of the features. It does not extend a line to
meet another line's end beyond `tolerance`, and it never adds or removes a vertex other than moving the end one.
Known answers (the tests): a line (0,0)-(9,0) next to a vertical line x = 10 with tolerance 1.5 is extended to (10,0); (0,0)-(11,0) is trimmed to (10,0); reversing swaps the first
and last vertex."""
import itertools
import math

JOINS = ("round", "miter", "bevel")


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def check_offset(distance, join="round", segments=8, miter_limit=2.0):
    """Error text for an offset request that cannot be run, else None. A negative distance is the other side. Pure."""
    number = _number(distance)
    if number is None or number == 0:
        return "distance must be a number other than 0 (negative offsets to the other side)."
    if str(join or "round").strip().lower() not in JOINS:
        return f"join must be one of {', '.join(JOINS)}."
    if _number(segments) is None or float(segments) != int(float(segments)) or not 1 <= int(float(segments)) <= 64:
        return "segments must be a whole number from 1 to 64."
    limit = _number(miter_limit)
    if limit is None or limit < 1:
        return "miter_limit must be a number of 1 or more."
    return None


def check_snap(tolerance):
    """Error text when the tolerance is not a number above 0, else None. Pure."""
    number = _number(tolerance)
    if number is None or number <= 0:
        return "tolerance must be a number above 0 (in the layer's units)."
    return None


def check_reshape(line_wkt):
    """(points, error): the (x, y) points of a LINESTRING(x y, ...) with at least 2 points, or an error text. Z and M values are refused. Pure."""
    from .parts_ops import parse_wkt
    kind, rings, problem = parse_wkt(line_wkt)
    if problem:
        return None, problem
    if kind != "LINESTRING":
        return None, "line_wkt must be a LINESTRING: the line that cuts the new edge."
    if len(rings[0]) < 2:
        return None, "line_wkt needs at least 2 points."
    return rings[0], None


def reverse_points(points):
    """The same vertices in the opposite order. Pure."""
    return list(reversed(list(points)))


def nearest_on_polyline(point, polyline):
    """(distance, (x, y)) of the point on `polyline` (a list of (x, y)) nearest to `point`; None for an empty line. Pure."""
    best = None
    if len(polyline) == 1:
        d = math.hypot(point[0] - polyline[0][0], point[1] - polyline[0][1])
        return d, polyline[0]
    for (x1, y1), (x2, y2) in itertools.pairwise(polyline):
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((point[0] - x1) * dx + (point[1] - y1) * dy) / length2))
        cx, cy = x1 + t * dx, y1 + t * dy
        d = math.hypot(point[0] - cx, point[1] - cy)
        if best is None or d < best[0]:
            best = (d, (cx, cy))
    return best


def snap_ends(parts, tolerance):
    """{key: (new first point or None, new last point or None)} for the line parts whose ends move. `parts` is a list of (key, points); an end moves to the nearest point on any
    part with another key when that is within `tolerance` and farther than a rounding error from the end. Pure."""
    moves = {}
    for key, points in parts:
        if len(points) < 2:
            continue
        new = []
        for end in (points[0], points[-1]):
            best = None
            for other_key, other in parts:
                if other_key == key or len(other) < 2:
                    continue
                found = nearest_on_polyline(end, other)
                if found is not None and (best is None or found[0] < best[0]):
                    best = found
            new.append(best[1] if best is not None and 1e-9 < best[0] <= tolerance else None)
        if new[0] is not None or new[1] is not None:
            moves[key] = (new[0], new[1])
    return moves
