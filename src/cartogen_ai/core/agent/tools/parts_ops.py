"""Part and ring editing helpers (PLAN-023 R9-2): the request check and a small WKT reader for the shape the user hands in, all pure Python (no QGIS, no numpy).

The edit itself is done by QGIS's own QgsGeometry (addRing, deleteRing, addPartGeometry, deletePart) inside an edit command, see parts_edit_tool.py; what is here is what can be
checked offline. Known answers (the tests): a ring of side 4 inside a square of side 10 takes the area from 100 to 84; filling that hole puts it back to 100.

Numbering is QGIS's: parts are 0-based; inside one polygon ring 0 is the outer boundary and the holes are 1, 2, ...; only holes can be deleted (delete_part removes a whole
polygon part). The WKT is read as plain x y pairs: Z and M values, curves and multi-geometries are refused with the reason, so nothing is silently dropped."""
import re

from .vertex_ops import _number, ring_area

ACTIONS = ("add_part", "add_ring", "fill_ring", "delete_part", "delete_ring")
_KIND = re.compile(r"^\s*(POLYGON|LINESTRING)\s*(.*)$", re.IGNORECASE | re.DOTALL)
_GROUP = re.compile(r"\(([^()]*)\)")


def parse_wkt(text):
    """(kind, rings, error): kind is 'POLYGON' or 'LINESTRING', rings a list of lists of (x, y) (one list for a line), error text or None. Pure."""
    match = _KIND.match(str(text or ""))
    if not match:
        return None, None, "geometry_wkt must be a POLYGON((x y, ...)) or a LINESTRING(x y, ...) in the layer's CRS."
    kind, rest = match.group(1).upper(), match.group(2).strip()
    if rest[:1] in ("Z", "M", "z", "m"):
        return None, None, "geometry_wkt with Z or M values is not supported: give x and y only."
    groups = _GROUP.findall(rest)
    if not groups or (kind == "LINESTRING" and len(groups) != 1):
        return None, None, f"geometry_wkt is not a valid {kind}."
    rings = []
    for group in groups:
        points = []
        for pair in group.split(","):
            numbers = pair.split()
            if len(numbers) != 2 or any(_number(n) is None for n in numbers):
                return None, None, "every coordinate in geometry_wkt must be a pair of numbers 'x y'."
            points.append((float(numbers[0]), float(numbers[1])))
        rings.append(points)
    return kind, rings, None


def check_request(action, geometry_wkt=None, part_index=None, ring_index=None, x=None, y=None):
    """Error text for a parts-and-rings request that cannot be run, else None. Pure.

    add_part: geometry_wkt (a POLYGON, or a LINESTRING on a line layer). add_ring: geometry_wkt, one closed POLYGON ring that lies inside the feature (QGIS finds the part it is in).
    fill_ring: x and y inside the hole. delete_ring: ring_index 1 or more (and part_index). delete_part: part_index."""
    act = str(action or "").strip().lower()
    if act not in ACTIONS:
        return f"action must be one of {', '.join(ACTIONS)}."
    for name, value in (("part_index", part_index), ("ring_index", ring_index)):
        if value is not None and (isinstance(value, bool) or _number(value) is None or float(value) != int(float(value)) or int(float(value)) < 0):
            return f"{name} must be a whole number, 0 or more."
    if (x is None) != (y is None) or (x is not None and (_number(x) is None or _number(y) is None)):
        return "x and y must both be numbers."
    if act in ("add_part", "add_ring"):
        kind, rings, problem = parse_wkt(geometry_wkt)
        if problem:
            return problem
        if act == "add_ring" and (kind != "POLYGON" or len(rings) != 1):
            return "add_ring needs geometry_wkt as a POLYGON with one ring: the outline of the hole."
        if kind == "POLYGON":
            for ring in rings:
                if len(ring) < 4 or ring[0] != ring[-1]:
                    return "a polygon ring in geometry_wkt must be closed (the first and last point equal) and have at least 3 corners."
                if ring_area(ring) <= 0:
                    return "the ring in geometry_wkt has no area."
        elif len(rings[0]) < 2:
            return "a LINESTRING in geometry_wkt needs at least 2 points."
        if ring_index is not None or x is not None:
            return f"{act} takes geometry_wkt only."
        if part_index is not None:
            return f"{act} takes no part_index: add_part appends a part and QGIS finds the part a ring is in."
    elif act == "fill_ring":
        if x is None:
            return "fill_ring needs x and y: a point inside the hole to fill."
        if geometry_wkt or ring_index is not None:
            return "fill_ring takes x and y (and part_index) only."
    elif act == "delete_ring":
        if ring_index is None or int(float(ring_index)) < 1:
            return "delete_ring needs ring_index 1 or more (ring 0 is the outer boundary; use delete_part to remove a whole part)."
        if geometry_wkt or x is not None:
            return "delete_ring takes ring_index (and part_index) only."
    else:
        if part_index is None:
            return "delete_part needs part_index."
        if geometry_wkt or x is not None or ring_index is not None:
            return "delete_part takes part_index only."
    return None


def describe(action, part_index=None, ring_index=None, x=None, y=None, area=None):
    """One sentence for the preview card: what will be done. `area` is the shape's area for add_ring / add_part when known. Pure."""
    act = str(action).lower()
    part = 0 if part_index is None else int(float(part_index))
    size = "" if area is None else f" (area {area:g})"
    if act == "add_part":
        return f"Add a new part{size}"
    if act == "add_ring":
        return f"Cut a hole{size}"
    if act == "fill_ring":
        return f"Fill the hole at ({x:g}, {y:g}) in part {part}"
    if act == "delete_ring":
        return f"Delete hole {int(float(ring_index))} of part {part}"
    return f"Delete part {part}"
