"""Vertex editing helpers (PLAN-023 R9-1): the request check, the nearest-vertex search and the plain geometry measures, all pure Python (no QGIS, no numpy).

The edit itself is done by QGIS's own QgsGeometry (deleteVertex, moveVertex, insertVertex) inside an edit command, see vertex_edit_tool.py; what is here is what can be
checked offline. Known answers (the tests): a square of side 10 has area 100; deleting one corner leaves a triangle of area 50; a vertex added at the midpoint of an edge does
not change the area; moving one corner of the top edge from (10, 10) to (20, 10) gives the trapezoid of area 150.

Vertex numbering is QGIS's: 0-based over the whole geometry, in the order `QgsGeometry.vertices()` yields them. A polygon ring is closed, so a square has 5 vertices and the
first and the last are the same corner."""
import itertools
import math

ACTIONS = ("add", "move", "delete")


def _number(value):
    """float(value), or None when it is not a finite number. Pure."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def check_request(action, index=None, x=None, y=None, near_x=None, near_y=None, tolerance=None):
    """Error text for a vertex request that cannot be run, else None. Pure.

    add: x and y (the new vertex goes on the nearest segment, at the closest point to x, y); no index or near.
    move: which vertex (index, or near_x and near_y) and where to (x and y).
    delete: which vertex (index, or near_x and near_y); no x and y."""
    act = str(action or "").strip().lower()
    if act not in ACTIONS:
        return f"action must be one of {', '.join(ACTIONS)}."
    has_index = index is not None
    has_near = near_x is not None or near_y is not None
    has_target = x is not None or y is not None
    if has_index and (isinstance(index, bool) or _number(index) is None or float(index) != int(float(index)) or int(float(index)) < 0):
        return "index must be a whole number, 0 or more."
    if has_near and (_number(near_x) is None or _number(near_y) is None):
        return "near_x and near_y must both be numbers."
    if has_target and (_number(x) is None or _number(y) is None):
        return "x and y must both be numbers."
    if tolerance is not None and (_number(tolerance) is None or float(tolerance) <= 0):
        return "tolerance must be a number above 0."
    if act == "add":
        if not has_target:
            return "add needs x and y: the point where the new vertex is wanted (it is placed on the nearest segment)."
        if has_index or has_near:
            return "add takes x and y only; index and near_x/near_y choose an existing vertex."
    else:
        if has_index == has_near:
            return f"{act} needs exactly one of index or near_x and near_y to choose the vertex."
        if act == "move" and not has_target:
            return "move needs x and y: where the vertex goes."
        if act == "delete" and has_target:
            return "delete takes no x and y."
    if tolerance is not None and not has_near:
        return "tolerance only applies with near_x and near_y."
    return None


def nearest_vertex(vertices, px, py, tolerance=None):
    """(index, distance) of the vertex nearest to (px, py), or None when `vertices` is empty or the nearest is farther than `tolerance`. `vertices` is a list of (x, y);
    on a tie the lowest index wins (a closed ring's first and last vertex are the same corner, so the first is returned). Pure."""
    best = None
    for i, (vx, vy) in enumerate(vertices):
        d = math.hypot(vx - px, vy - py)
        if best is None or d < best[1]:
            best = (i, d)
    if best is None or (tolerance is not None and best[1] > tolerance):
        return None
    return best


def ring_area(vertices):
    """Area of the polygon ring `vertices` (a list of (x, y); closed or not) by the shoelace formula. Pure."""
    pts = list(vertices)
    if len(pts) < 3:
        return 0.0
    total = 0.0
    for i, (x1, y1) in enumerate(pts):
        x2, y2 = pts[(i + 1) % len(pts)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def path_length(vertices):
    """Length of the line through `vertices`, a list of (x, y). Pure."""
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in itertools.pairwise(vertices))


def describe(action, index=None, x=None, y=None, near=None):
    """One sentence for the preview card: what will be done to which vertex. `near` is (x, y) when the vertex was chosen by position. Pure."""
    act = str(action).lower()
    which = f"the vertex nearest ({near[0]:g}, {near[1]:g})" if near is not None else f"vertex {index}"
    if act == "add":
        return f"Add a vertex on the segment nearest ({x:g}, {y:g})"
    if act == "move":
        return f"Move {which} to ({x:g}, {y:g})"
    return f"Delete {which}"
