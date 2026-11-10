"""set_project_transform_context, define_custom_crs, set_project_measurement and set_canvas_decoration (PLAN-023 R10-5): coordinate and display settings kept in the PROJECT.

None edits layer data. See project_settings_ops.py for the policy of each (only operations QGIS itself lists can be chosen, a custom CRS is not added to the shared CRS database, units and
ellipsoid words are checked, decorations are hand-verified only). Setting a datum transformation changes how every layer is reprojected, so it shows a PREVIEW_REQUIRED card first; the others
apply directly and read their values back. The listing of transformation operations is read-only.

Written without a QGIS install; tests/test_project_settings_tools_live.py is their first execution in CI (decorations are read back from the project properties, not seen on a canvas)."""
from . import project_settings_ops as ps
from .attribute_edit_tools import preview
from .registry import register_tool

try:
    from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsDatumTransform, QgsEllipsoidUtils, QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

OPERATION_CAP = 25
PROJECT_NOTE = "Stored with the project, not in any data file: save the project to keep it."


def _crs(text):
    crs = QgsCoordinateReferenceSystem(str(text).strip())
    return (crs, None) if crs.isValid() else (None, f"'{text}' is not a coordinate system QGIS knows (for example EPSG:4326).")


def _operation_id(detail):
    authority, code = getattr(detail, "authority", ""), getattr(detail, "authId", "")
    return f"{authority}:{code}" if authority and code else detail.proj


def _describe(detail, chosen):
    return {"id": _operation_id(detail), "name": detail.name, "accuracy_m": detail.accuracy if detail.accuracy >= 0 else None, "available": bool(detail.isAvailable),
            "in_use": detail.proj == chosen}


@register_tool(
    "set_project_transform_context",
    "Choose the datum transformation the PROJECT uses between two coordinate systems, or list the choices. Without operation_id it only LISTS the coordinate operations PROJ offers between "
    "source_crs and dest_crs (name, accuracy in metres, whether its grid files are installed, and which one the project uses now); the choice can move points by metres, for example between "
    "EPSG:4326 and a local datum. With operation_id (an id from that listing) a preview is shown for confirmation first, then the project uses it for every layer. Only an operation QGIS "
    "lists for that pair is accepted. Stored with the project.",
    {"type": "object", "properties": {
        "source_crs": {"type": "string", "description": "The source CRS, for example EPSG:4326."},
        "dest_crs": {"type": "string", "description": "The destination CRS, for example EPSG:32636."},
        "operation_id": {"type": "string", "description": "An id from the listing (an authority code like EPSG:1150, or the operation's PROJ text); leave out to list."}},
     "required": ["source_crs", "dest_crs"]},
    keywords=["datum transformation", "datum transformations", "list the datum transformations", "choose a datum transformation", "coordinate operation", "transformation between", "transform context",
              "which transformation is used", "datum shift"],
)
def set_project_transform_context(source_crs, dest_crs, operation_id=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = ps.check_transform(source_crs, dest_crs, operation_id)
    if problem:
        return {"error": problem}
    source, why = _crs(source_crs)
    dest, why2 = _crs(dest_crs)
    if why or why2:
        return {"error": why or why2}
    project = QgsProject.instance()
    context = project.transformContext()
    chosen = context.coordinateOperations().get((source.authid(), dest.authid()), "")
    operations = QgsDatumTransform.operations(source, dest)
    if operation_id is None:
        return {"success": True, "source_crs": source.authid(), "dest_crs": dest.authid(), "operations": [_describe(d, chosen) for d in operations[:OPERATION_CAP]],
                "operations_total": len(operations), "chosen_in_project": chosen or None,
                "note": "Without a choice QGIS picks the most suitable operation for the area on its own. Give operation_id to pin one."}
    match = next((d for d in operations if operation_id.strip() in (_operation_id(d), d.proj)), None)
    if match is None:
        return {"error": "That is not one of the operations QGIS lists between these two systems; list them first and use an id from the list."}
    if not confirmed:
        return preview("set_project_transform_context", {"source_crs": source.authid(), "dest_crs": dest.authid(), "operation_id": _operation_id(match)},
                       f"Make the project use '{match.name}' (accuracy {match.accuracy if match.accuracy >= 0 else 'unknown'} m) to transform {source.authid()} to {dest.authid()} for every layer.",
                       "context = QgsProject.instance().transformContext()\ncontext.addCoordinateOperation(source, dest, proj)\nQgsProject.instance().setTransformContext(context)")
    if not match.isAvailable:
        return {"error": f"'{match.name}' needs grid files that are not installed on this computer, so it cannot be used here."}
    if not context.addCoordinateOperation(source, dest, match.proj):
        return {"error": "QGIS refused that coordinate operation."}
    project.setTransformContext(context)
    now = project.transformContext().coordinateOperations().get((source.authid(), dest.authid()), "")
    return {"success": True, "source_crs": source.authid(), "dest_crs": dest.authid(), "operation": match.name, "chosen_in_project_now": now, "chosen_before": chosen or None,
            "note": PROJECT_NOTE}


@register_tool(
    "define_custom_crs",
    "Check a custom coordinate system given as a PROJ string (+proj=tmerc +lat_0=0 ...) or a WKT, and optionally make it the project CRS. QGIS validates it first; an invalid definition is "
    "refused. It is used for THIS project only: it is not added to the shared custom-CRS database of the user's QGIS. The reply gives its units and whether it is geographic.",
    {"type": "object", "properties": {
        "name": {"type": "string", "description": "A label for the reply (a custom CRS has no stored name here)."},
        "definition": {"type": "string", "description": "A PROJ string starting +proj= or a WKT starting PROJCRS[ / GEOGCRS[."},
        "use_as_project_crs": {"type": "boolean", "description": "Also make it the project's CRS (default false)."}},
     "required": ["name", "definition"]},
    keywords=["custom crs", "define a custom crs", "custom coordinate system", "make a local coordinate system", "proj string", "crs from wkt", "crs from a proj string", "own coordinate system"],
)
def define_custom_crs(name, definition, use_as_project_crs=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    kind, problem = ps.check_custom_crs(name, definition)
    if problem:
        return {"error": problem}
    crs = QgsCoordinateReferenceSystem()
    if kind == "proj":
        crs.createFromProj(definition.strip())
    else:
        crs.createFromWkt(definition.strip())
    if not crs.isValid():
        return {"error": "QGIS could not read that definition as a coordinate system; check it against the PROJ or WKT syntax."}
    out = {"success": True, "name": name.strip(), "kind": kind, "valid": True, "geographic": bool(crs.isGeographic()), "units": crs.mapUnits().name if hasattr(crs.mapUnits(), "name") else str(crs.mapUnits()),
           "description": crs.description(), "authid": crs.authid() or None, "used_as_project_crs": False,
           "note": "Not added to the user's CRS database: it exists in this project only."}
    if use_as_project_crs:
        project = QgsProject.instance()
        out["project_crs_before"] = project.crs().authid() or project.crs().description()
        project.setCrs(crs)
        out["used_as_project_crs"] = True
        out["note"] += " " + PROJECT_NOTE
    return out


@register_tool(
    "set_project_measurement",
    "Set the project's ellipsoid (for example WGS84, EPSG:7030, or NONE for flat planimetric measurement), distance units and area units: what the measuring tools and the layout use. "
    "distance_units: meters, kilometers, feet, yards, miles, nautical miles or degrees. area_units: square meters, square kilometers, hectares, acres, square feet, square yards, square miles "
    "or square degrees. The values are read back. Stored with the project; no layer data changes.",
    {"type": "object", "properties": {
        "ellipsoid": {"type": "string", "description": "An ellipsoid name or code (WGS84, EPSG:7030, ...) or NONE."},
        "distance_units": {"type": "string", "description": "meters, kilometers, feet, yards, miles, nautical miles or degrees."},
        "area_units": {"type": "string", "description": "square meters, square kilometers, hectares, acres, square feet, square yards, square miles or square degrees."}},
     "required": []},
    keywords=["project ellipsoid", "set the ellipsoid", "measurement units", "set the distance units", "set the area units", "measure in hectares", "measure in kilometres", "ellipsoid for measuring",
              "project units"],
)
def set_project_measurement(ellipsoid=None, distance_units=None, area_units=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = ps.check_measurement(ellipsoid, distance_units, area_units)
    if problem:
        return {"error": problem}
    project = QgsProject.instance()
    before = {"ellipsoid": project.ellipsoid(), "distance_units": project.distanceUnits().name, "area_units": project.areaUnits().name}
    members = {}
    if distance_units is not None:
        members["distance"] = getattr(Qgis.DistanceUnit, ps.distance_unit_name(distance_units), None)
    if area_units is not None:
        members["area"] = getattr(Qgis.AreaUnit, ps.area_unit_name(area_units), None)
    if any(value is None for value in members.values()):
        return {"error": "This QGIS does not know one of those units."}
    if ellipsoid is not None:
        key = ellipsoid.strip()
        if key.upper() != "NONE" and not QgsEllipsoidUtils.ellipsoidParameters(key).valid:
            return {"error": f"'{key}' is not an ellipsoid QGIS knows. Try WGS84 or an EPSG code such as EPSG:7030, or NONE."}
        project.setEllipsoid("NONE" if key.upper() == "NONE" else key)
        if key.upper() != "NONE" and project.ellipsoid().upper() == "NONE":         # seen in CI: a project with no coordinate system read back NONE after WGS84 was set
            project.setEllipsoid(before["ellipsoid"])
            return {"error": f"QGIS did not keep the ellipsoid '{key}' (it reads back as NONE) and nothing was changed. A likely reason is that the project has no coordinate system yet: "
                             "set the project CRS first (set_project_crs) and try again."}
    if "distance" in members:
        project.setDistanceUnits(members["distance"])
    if "area" in members:
        project.setAreaUnits(members["area"])
    return {"success": True, "now": {"ellipsoid": project.ellipsoid(), "distance_units": project.distanceUnits().name, "area_units": project.areaUnits().name}, "before": before,
            "note": PROJECT_NOTE}


@register_tool(
    "set_canvas_decoration",
    "Switch a map-canvas decoration on or off and place it: kind title, copyright, scale_bar, north_arrow or grid; placement bottom_left, top_left, top_right, bottom_right, top_center or "
    "bottom_center; text for the title and the copyright. These are saved as project properties which QGIS reads when the project is opened, so save the project and reopen it (or use the "
    "View > Decorations menu) to see the change. Hand-verified only: the canvas is not available to automatic tests. No layer data changes.",
    {"type": "object", "properties": {
        "kind": {"type": "string", "enum": list(ps.DECORATIONS), "description": "title, copyright, scale_bar, north_arrow or grid."},
        "enabled": {"type": "boolean", "description": "true to show it, false to hide it."},
        "placement": {"type": "string", "enum": list(ps.PLACEMENTS), "description": "Where it sits on the canvas."},
        "text": {"type": "string", "description": "The words for the title or the copyright (those two kinds only)."}},
     "required": ["kind"]},
    keywords=["canvas decoration", "decoration on the canvas", "add a title to the map canvas", "scale bar on the canvas", "north arrow on the canvas", "copyright label", "grid on the canvas",
              "decorations"],
)
def set_canvas_decoration(kind, enabled=None, placement=None, text=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = ps.check_decoration(kind, enabled, placement, text)
    if problem:
        return {"error": problem}
    name = str(kind).strip().lower()
    scope = ps.DECORATIONS[name]
    project = QgsProject.instance()
    if enabled is not None:
        project.writeEntryBool(scope, "/Enabled", enabled)
    if placement is not None:
        project.writeEntry(scope, "/Placement", ps.PLACEMENTS[str(placement).strip().lower()])
    if text is not None:
        project.writeEntry(scope, "/Label", text)
    now = {"enabled": project.readBoolEntry(scope, "/Enabled", False)[0], "placement": project.readNumEntry(scope, "/Placement", -1)[0]}
    if name in ps.TEXT_DECORATIONS:
        now["text"] = project.readEntry(scope, "/Label", "")[0]
    return {"success": True, "kind": name, "stored_in_project_as": scope, "now": now,
            "note": PROJECT_NOTE + " QGIS reads decorations when a project is opened: save and reopen it, or use View > Decorations. Not seen on a canvas by any automatic test."}
