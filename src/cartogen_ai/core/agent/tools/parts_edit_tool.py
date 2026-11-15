"""edit_parts_and_rings (PLAN-023 R9-2): add or delete a part, cut or fill or delete a hole in one feature of a line or polygon layer.

Like edit_vertices it is done by QGIS's own QgsGeometry (addRing, deleteRing, addPartGeometry, deletePart) inside the repo's edit command (_edit_session.edit_command), so it is one
undoable step (undo_manual_edit), it never takes over a layer the user already has in edit mode, a failed edit leaves nothing applied, and it first returns a PREVIEW_REQUIRED
card. A result that would make a valid geometry invalid (a hole outside the polygon, parts that overlap) is refused with the reason. The shape to add is given as WKT in the layer's CRS.

Numbering is QGIS's: parts 0-based; in a polygon ring 0 is the outer boundary and holes are 1, 2, ...; fill_ring finds the hole by a point inside it. add_part needs a multi-part
layer (a single-part layer cannot hold two parts); add_ring and fill_ring are for polygon layers.

Written without a QGIS install; tests/test_parts_edit_tool_live.py is its first execution in CI."""
from . import parts_ops as po
from .attribute_edit_tools import _layer, _unsaved_note, preview
from .registry import register_tool

try:
    from qgis.core import QgsGeometry, QgsPointXY, QgsWkbTypes
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _success(result):
    """True for QGIS 4's Qgis.GeometryOperationResult.Success and QGIS 3's 0."""
    return getattr(result, "name", None) == "Success" or result == 0


def _result_name(result):
    return getattr(result, "name", None) or f"code {result}"


def _polygon_parts(geometry):
    """List of parts, each a list of rings (lists of QgsPointXY); ring 0 is the outer boundary. Needs QGIS."""
    return geometry.asMultiPolygon() if geometry.isMultipart() else [geometry.asPolygon()]


def _find_hole(geometry, x, y, part_index):
    """(part, ring number) of the hole that contains (x, y), searching `part_index` or all parts; None when there is none. Needs QGIS."""
    probe = QgsGeometry.fromPointXY(QgsPointXY(x, y))
    for part_no, rings in enumerate(_polygon_parts(geometry)):
        if part_index is not None and part_no != part_index:
            continue
        for ring_no, ring in enumerate(rings):
            if ring_no >= 1 and QgsGeometry.fromPolygonXY([ring]).contains(probe):
                return part_no, ring_no
    return None


_METHOD = {"add_part": "addPartGeometry", "add_ring": "addRing", "fill_ring": "deleteRing", "delete_ring": "deleteRing", "delete_part": "deletePart"}


def _target(act, geometry, fid, parts, part, ring_no, x, y):
    """(hole, error): the (part, ring number) a ring action works on, or an error text for a part or ring that does not exist. Needs QGIS."""
    if act == "delete_part":
        if part >= parts:
            return None, f"Part {part} does not exist: feature {fid} has {parts} part(s) (numbered 0 to {parts - 1})."
        if parts == 1:
            return None, f"Feature {fid} has only one part; deleting it would leave nothing. Delete the feature instead."
    elif act == "delete_ring":
        use_part = part or 0
        rings = _polygon_parts(geometry)
        if use_part >= len(rings):
            return None, f"Part {use_part} does not exist: feature {fid} has {parts} part(s) (numbered 0 to {parts - 1})."
        if ring_no >= len(rings[use_part]):
            return None, f"Hole {ring_no} does not exist in part {use_part}: it has {len(rings[use_part]) - 1} hole(s) (numbered from 1)."
        return (use_part, ring_no), None
    elif act == "fill_ring":
        hole = _find_hole(geometry, float(x), float(y), part)
        return (hole, None) if hole else (None, "No hole of this feature contains that point.")
    return None, None


def _change(act, geometry, shape_rings, geometry_wkt, part, hole):
    """Runs the QGIS geometry call for `act` on `geometry`; raises EditError with the reason when QGIS refuses. Needs QGIS."""
    from ._edit_session import EditError
    if act == "add_ring":
        result = geometry.addRing([QgsPointXY(px, py) for px, py in shape_rings[0]])
        if not _success(result):
            raise EditError(f"QGIS could not cut that hole ({_result_name(result)}): it must be closed and lie wholly inside the polygon, away from other holes.")
    elif act == "add_part":
        result = geometry.addPartGeometry(QgsGeometry.fromWkt(str(geometry_wkt)))
        if not _success(result):
            raise EditError(f"QGIS could not add that part ({_result_name(result)}).")
    elif act == "delete_part":
        if not geometry.deletePart(part):
            raise EditError("QGIS refused to delete that part.")
    elif not geometry.deleteRing(hole[1], hole[0]):               # fill_ring and delete_ring both remove an inner ring
        raise EditError("QGIS refused to delete that hole.")


@register_tool(
    "edit_parts_and_rings",
    "Add or delete a part, or cut, fill or delete a hole (ring), in one feature of a line or polygon layer. action 'add_ring' cuts a hole given as geometry_wkt (a POLYGON "
    "inside the feature); 'fill_ring' fills the hole that contains the point x, y; 'delete_ring' deletes hole number ring_index (1, 2, ...; part_index chooses the part, default 0); "
    "'add_part' adds geometry_wkt (a POLYGON, or a LINESTRING on a line layer) as a new part and needs a multi-part layer; 'delete_part' removes part number part_index (not the last "
    "part). Coordinates are in the layer's CRS. Changes geometry: a preview is shown for confirmation first, the edit is one undoable step (undo_manual_edit), and a change that "
    "would make a valid geometry invalid is refused.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "A line or polygon layer."},
        "feature_id": {"type": "integer", "description": "The feature's id (the QGIS feature id)."},
        "action": {"type": "string", "enum": list(po.ACTIONS), "description": "add_part, add_ring, fill_ring, delete_part or delete_ring."},
        "geometry_wkt": {"type": "string", "description": "add_part / add_ring: the shape as WKT in the layer's CRS, for example POLYGON((3 3,3 7,7 7,7 3,3 3))."},
        "part_index": {"type": "integer", "description": "delete_part: the part; delete_ring / fill_ring: the part holding the hole (default 0 / any)."},
        "ring_index": {"type": "integer", "description": "delete_ring: the hole number, 1 or more (0 is the outer boundary)."},
        "x": {"type": "number", "description": "fill_ring: x of a point inside the hole (layer CRS)."},
        "y": {"type": "number", "description": "fill_ring: y of a point inside the hole (layer CRS)."}},
     "required": ["layer_name", "feature_id", "action"]},
    keywords=["cut a hole", "add a hole", "fill a hole", "fill the hole", "fill a ring", "add a ring", "delete a ring", "add a part", "delete a part", "remove a part", "donut", "island"],
)
def edit_parts_and_rings(layer_name, feature_id, action, geometry_wkt=None, part_index=None, ring_index=None, x=None, y=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = po.check_request(action, geometry_wkt, part_index, ring_index, x, y)
    if problem:
        return {"error": problem}
    act = str(action).strip().lower()
    layer, err = _layer(layer_name)
    if err:
        return err
    kind = QgsWkbTypes.geometryType(layer.wkbType())
    if kind == QgsWkbTypes.GeometryType.PointGeometry:
        return {"error": f"'{layer_name}' is a point layer: it has no parts or rings to edit here."}
    is_polygon = kind == QgsWkbTypes.GeometryType.PolygonGeometry
    if act in ("add_ring", "fill_ring", "delete_ring") and not is_polygon:
        return {"error": f"{act} is for polygon layers; '{layer_name}' is a line layer."}
    shape_kind, shape_rings, _problem = po.parse_wkt(geometry_wkt) if act in ("add_part", "add_ring") else (None, None, None)
    if act == "add_part":
        if (shape_kind == "POLYGON") != is_polygon:
            return {"error": f"'{layer_name}' is a {'polygon' if is_polygon else 'line'} layer: geometry_wkt must be a {'POLYGON' if is_polygon else 'LINESTRING'}."}
        if not QgsWkbTypes.isMultiType(layer.wkbType()):
            return {"error": f"'{layer_name}' holds single-part geometries, so it cannot take a second part. Use a multi-part (MultiPolygon or MultiLineString) layer."}
    try:
        fid = int(feature_id)
    except (TypeError, ValueError):
        return {"error": "feature_id must be a whole number."}
    feature = layer.getFeature(fid)
    if not feature.isValid() or feature.geometry().isNull():
        return {"error": f"Feature {fid} was not found in '{layer_name}' or has no geometry."}
    geometry = QgsGeometry(feature.geometry())
    parts = geometry.constGet().partCount()
    part = None if part_index is None else int(float(part_index))
    hole, why = _target(act, geometry, fid, parts, part, None if ring_index is None else int(float(ring_index)), x, y)
    if why:
        return {"error": why}
    from .vertex_ops import ring_area
    shape_area = ring_area(shape_rings[0]) if shape_kind == "POLYGON" else None
    sentence = po.describe(act, hole[0] if hole else part, hole[1] if hole else None, None if x is None else float(x), None if y is None else float(y), shape_area)
    measure = geometry.area() if is_polygon else geometry.length()
    label = "area" if is_polygon else "length"
    if not confirmed:
        arguments = {"layer_name": layer_name, "feature_id": fid, "action": act}
        if geometry_wkt:
            arguments["geometry_wkt"] = str(geometry_wkt)
        if hole is not None:                                    # the preview pins the hole it found, so Apply cannot hit a different one
            arguments.update(action="delete_ring", part_index=hole[0], ring_index=hole[1])
        elif part is not None:
            arguments["part_index"] = part
        return preview("edit_parts_and_rings", arguments, f"{sentence} of feature {fid} in '{layer_name}' ({label} now {measure:g}, {parts} part(s)).",
                       f"layer.startEditing()\ngeometry = layer.getFeature({fid}).geometry()\ngeometry.{_METHOD[act]}(...)\n"
                       "layer.changeGeometry(feature_id, geometry)\nlayer.commitChanges()")
    from ._edit_session import EditError, edit_command
    valid_before = geometry.isGeosValid()
    try:
        with edit_command(layer, f"Cartogen AI: {act}") as owned:
            _change(act, geometry, shape_rings, geometry_wkt, part, hole)
            if valid_before and not geometry.isGeosValid():
                raise EditError("the result would not be a valid geometry (for example parts that overlap).")
            if not layer.changeGeometry(fid, geometry):
                raise EditError("the layer refused the geometry change (read-only source?).")
    except EditError as e:
        return {"error": f"Nothing was changed: {e}"}
    out = {"success": True, "layer_name": layer_name, "feature_id": fid, "action": act, "applied": sentence, "parts_before": parts,
           "parts_after": geometry.constGet().partCount(), f"{label}_before": round(measure, 6),
           f"{label}_after": round(geometry.area() if is_polygon else geometry.length(), 6),
           "undo": "undo_manual_edit steps it back while the layer is in edit mode."}
    if layer.crs().isValid() and layer.crs().isGeographic():
        out["note_crs"] = f"The layer is in a geographic CRS, so the {label} is in degrees."
    note = _unsaved_note(owned)
    if note:
        out["note"] = note
    return out
