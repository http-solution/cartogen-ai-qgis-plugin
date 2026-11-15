"""Spatial weights for the spatial-statistics tools (PLAN-023 R2-1), pure Python, no QGIS, no numpy.

A weights object is a list with one entry per feature: `neighbours[i]` is the list of the OTHER features it counts as near. Everything else is derived from that:
  * contiguity from polygon outlines: 'rook' = two polygons share an edge (two consecutive corner points), 'queen' = they share at least one corner point. Corner points are matched after
    rounding to a tolerance, so the outlines must be topologically clean (neighbours meet at shared corners, as admin boundaries from one source do). A T-junction (a corner of one polygon that
    lies on the middle of another's edge) is NOT detected; `islands()` lists the features left with no neighbour so the caller can say so instead of guessing;
  * k nearest neighbours from points (asymmetric: i may count j without j counting i);
  * a distance band from points, in the units of the coordinates (a projected CRS is required for that to mean metres; the tool refuses a geographic one).
`standardise()` turns neighbour lists into (j, weight) pairs: 'binary' (1 each) or 'row' (each row sums to 1; a feature with no neighbours stays an empty row, not a division by zero)."""
import math

DEFAULT_TOLERANCE = 1e-9


def _key(point, tolerance):
    return (round(point[0] / tolerance), round(point[1] / tolerance))


def _ring_edges(ring, tolerance):
    keys = [_key(p, tolerance) for p in ring]
    if keys and keys[0] == keys[-1]:
        keys = keys[:-1]
    edges = set()
    for i, a in enumerate(keys):
        b = keys[(i + 1) % len(keys)]
        if a != b:
            edges.add((a, b) if a <= b else (b, a))
    return set(keys), edges


def contiguity(polygons, mode="queen", tolerance=DEFAULT_TOLERANCE):
    """Neighbour lists from polygon outlines. `polygons` is a list (one per feature) of lists of rings; a ring is a list of (x, y) points (the outer ring and any holes, or the rings of every part of a multipart
    polygon). mode is 'queen' or 'rook'. Pure; the result is symmetric and each list is sorted. ValueError for another mode."""
    if mode not in ("queen", "rook"):
        raise ValueError("contiguity mode must be 'queen' or 'rook'")
    corners, edges = [], []
    for rings in polygons:
        c, e = set(), set()
        for ring in rings:
            rc, re_ = _ring_edges(ring, tolerance)
            c |= rc
            e |= re_
        corners.append(c)
        edges.append(e)
    index = {}
    for i, (c, e) in enumerate(zip(corners, edges, strict=True)):
        for item in (c if mode == "queen" else e):
            index.setdefault(item, []).append(i)
    neighbours = [set() for _ in polygons]
    for members in index.values():
        for a in members:
            for b in members:
                if a != b:
                    neighbours[a].add(b)
    return [sorted(n) for n in neighbours]


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def knn(points, k):
    """The k nearest other points of each point (ties broken by position). ValueError unless 1 <= k < number of points."""
    n = len(points)
    if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k < n:
        raise ValueError(f"k must be a whole number from 1 to {n - 1} for {n} features")
    out = []
    for i, p in enumerate(points):
        order = sorted((j for j in range(n) if j != i), key=lambda j: (_distance(p, points[j]), j))
        out.append(sorted(order[:k]))
    return out


def distance_band(points, distance):
    """Every other point within `distance` (inclusive) of each point. ValueError unless distance is a positive number."""
    if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not distance > 0 or math.isinf(distance):
        raise ValueError("distance must be a positive number")
    n = len(points)
    return [[j for j in range(n) if j != i and _distance(points[i], points[j]) <= distance] for i in range(n)]


def standardise(neighbours, style="row"):
    """[(j, weight), ...] per feature: 'binary' gives 1 for each neighbour, 'row' gives 1/(number of neighbours) so each non-empty row sums to 1. ValueError for another style."""
    if style not in ("binary", "row"):
        raise ValueError("style must be 'binary' or 'row'")
    return [[(j, 1.0 if style == "binary" else 1.0 / len(row)) for j in row] for row in neighbours]


def islands(neighbours):
    """Positions of the features with no neighbour at all."""
    return [i for i, row in enumerate(neighbours) if not row]


def link_count(neighbours):
    """Number of (feature, neighbour) links."""
    return sum(len(row) for row in neighbours)


def mean_neighbours(neighbours):
    return link_count(neighbours) / len(neighbours) if neighbours else 0.0


def components(neighbours):
    """Number of connected groups when links are read as undirected. A weights matrix in several groups is legal but worth telling the user about."""
    n = len(neighbours)
    adjacent = [set(row) for row in neighbours]
    for i, row in enumerate(neighbours):
        for j in row:
            adjacent[j].add(i)
    seen, groups = set(), 0
    for start in range(n):
        if start in seen:
            continue
        groups += 1
        stack = [start]
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            stack.extend(adjacent[i] - seen)
    return groups
