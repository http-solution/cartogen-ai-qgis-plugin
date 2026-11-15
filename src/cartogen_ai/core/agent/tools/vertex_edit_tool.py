"""edit_vertices (PLAN-023 R9-1): add, move or delete one vertex of one feature of a line or polygon layer.

The edit is done by QGIS's own QgsGeometry (insertVertex, moveVertex, deleteVertex) inside the repo's edit command (_edit_session.edit_command), so it is one undoable step in the layer's
own history (undo_manual_edit steps it back), it never takes over a layer the user already has in edit mode, and a failed edit leaves nothing applied. Like every geometry change
it first returns a PREVIEW_REQUIRED card with the exact feature and action; it applies when confirmed. A change that would turn a valid geometry invalid is refused with the reason.

Vertex numbering is QGIS's (0-based over the whole geometry; a polygon ring is closed, so a square has 5 vertices and the first and last are the same corner). A vertex is chosen by
`index` or by the position nearest it (`near_x`, `near_y`, optionally within `tolerance`). A new vertex goes on the segment nearest (x, y), at the closest point on that segment, so
adding a vertex never changes the shape. Coordinates are in the layer's CRS (degrees on a geographic layer).

Written without a QGIS install; tests/test_vertex_edit_tool_live.py is its first execution in CI."""
from . import vertex_ops as vo
from .attribute_edit_tools import _layer, _unsaved_note, preview
from .registry import register_tool

try:
    from qgis.core import QgsGeometry, QgsPointXY, QgsWkbTypes
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _measure(geometry, is_polygon):
    """(label, value) of the geometry's size: its area for a polygon, its length for a line. Needs QGIS."""
    return ("area", geometry.area()) if is_polygon else ("length", geometry.length())


@register_tool(
    "edit_vertices",
    "Add, move or delete one vertex of one feature of a line or polygon layer: action 'delete' removes a vertex, 'move' moves it to x, y, 'add' puts a new vertex on the segment nearest "
    "x, y (the shape does not change). Choose the feature by feature_id and the vertex by index (0-based; a polygon ring is closed, so a square has 5 vertices and the first and last "
    "are the same corner) or by the position nearest it (near_x, near_y, optionally within tolerance). Coordinates are in the layer's CRS. Changes geometry: a preview is shown "
    "for confirmation first, the edit is one undoable step (undo_manual_edit), and a change that would make a valid geometry invalid is refused.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string", "description": "A line or polygon layer."},
        "feature_id": {"type": "integer", "description": "The feature's id (the QGIS feature id)."},
        "action": {"type": "string", "enum": list(vo.ACTIONS), "description": "add, move or delete."},
        "index": {"type": "integer", "description": "The vertex to move or delete, 0-based over the whole geometry."},
        "near_x": {"type": "number", "description": "Instead of index: pick the vertex nearest this x (layer CRS)."},
        "near_y": {"type": "number", "description": "Instead of index: pick the vertex nearest this y (layer CRS)."},
        "tolerance": {"type": "number", "description": "With near_x/near_y: refuse if the nearest vertex is farther than this (layer units)."},
        "x": {"type": "number", "description": "move: the new x; add: the x of the point near which the vertex is added."},
        "y": {"type": "number", "description": "move: the new y; add: the y of the point near which the vertex is added."}},
     "required": ["layer_name", "feature_id", "action"]},
    keywords=["delete a vertex", "remove a vertex", "move a vertex", "add a vertex", "insert a vertex", "edit the vertices", "vertex editing", "move the corner", "reshape by vertex"],
)
def edit_vertices(layer_name, feature_id, action, index=None, near_x=None, near_y=None, tolerance=None, x=None, y=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = vo.check_request(action, index, x, y, near_x, near_y, tolerance)
    if problem:
        return {"error": problem}
    act = str(action).strip().lower()
    layer, err = _layer(layer_name)
    if err:
        return err
    kind = QgsWkbTypes.geometryType(layer.wkbType())
    if kind == QgsWkbTypes.GeometryType.PointGeometry:
        return {"error": f"'{layer_name}' is a point layer: a point has one vertex. Use transform_features to move points."}
    is_polygon = kind == QgsWkbTypes.GeometryType.PolygonGeometry
    try:
        fid = int(feature_id)
    except (TypeError, ValueError):
        return {"error": "feature_id must be a whole number."}
    feature = layer.getFeature(fid)
    if not feature.isValid() or feature.geometry().isNull():
        return {"error": f"Feature {fid} was not found in '{layer_name}' or has no geometry."}
    geometry = QgsGeometry(feature.geometry())
    vertices = [(p.x(), p.y()) for p in geometry.vertices()]
    count = len(vertices)
    chosen = None if index is None else int(float(index))
    if act in ("move", "delete"):
        if near_x is not None:
            found = vo.nearest_vertex(vertices, float(near_x), float(near_y), None if tolerance is None else float(tolerance))
            if found is None:
                return {"error": "No vertex of this feature is within the tolerance of that position." if tolerance is not None else "This feature has no vertices."}
            chosen = found[0]
        if chosen is None or chosen >= count:
            return {"error": f"Vertex {chosen} does not exist: feature {fid} has {count} vertices (numbered 0 to {count - 1})."}
    near = (float(near_x), float(near_y)) if near_x is not None else None
    sentence = vo.describe(act, chosen, None if x is None else float(x), None if y is None else float(y), near)
    if not confirmed:
        arguments = {"layer_name": layer_name, "feature_id": fid, "action": act}
        if chosen is not None:
            arguments["index"] = chosen
        if x is not None:
            arguments.update(x=float(x), y=float(y))
        method = {"add": "insertVertex", "move": "moveVertex", "delete": "deleteVertex"}[act]
        return preview("edit_vertices", arguments, f"{sentence} of feature {fid} in '{layer_name}' ({count} vertices now).",
                       f"layer.startEditing()\ngeometry = layer.getFeature({fid}).geometry()\ngeometry.{method}(...)\n"
                       "layer.changeGeometry(feature_id, geometry)\nlayer.commitChanges()")
    from ._edit_session import EditError, edit_command
    label, before = _measure(geometry, is_polygon)
    valid_before = geometry.isGeosValid()
    try:
        with edit_command(layer, f"Cartogen AI: {act} vertex") as owned:
            if act == "delete":
                done = geometry.deleteVertex(chosen)
            elif act == "move":
                done = geometry.moveVertex(float(x), float(y), chosen)
            else:
                _dist, closest, after, _side = geometry.closestSegmentWithContext(QgsPointXY(float(x), float(y)))
                if after <= 0:
                    raise EditError("this feature has no segment to add a vertex on.")
                done = geometry.insertVertex(closest.x(), closest.y(), after)
            if not done:
                raise EditError(f"QGIS refused to {act} that vertex (a polygon ring cannot go below 3 corners, a line below 2 vertices).")
            if valid_before and not geometry.isGeosValid():
                raise EditError("the result would not be a valid geometry (for example edges crossing each other).")
            if not layer.changeGeometry(fid, geometry):
                raise EditError("the layer refused the geometry change (read-only source?).")
    except EditError as e:
        return {"error": f"Nothing was changed: {e}"}
    _label, after_value = _measure(geometry, is_polygon)
    out = {"success": True, "layer_name": layer_name, "feature_id": fid, "action": act, "applied": sentence, "vertices_before": count,
           "vertices_after": len([0 for _p in geometry.vertices()]), f"{label}_before": round(before, 6), f"{label}_after": round(after_value, 6),
           "undo": "undo_manual_edit steps it back while the layer is in edit mode."}
    if act == "add":
        out["added_at"] = [round(closest.x(), 6), round(closest.y(), 6)]
    if layer.crs().isValid() and layer.crs().isGeographic():
        out["note_crs"] = f"The layer is in a geographic CRS, so the {label} is in degrees."
    note = _unsaved_note(owned)
    if note:
        out["note"] = note
    return out
